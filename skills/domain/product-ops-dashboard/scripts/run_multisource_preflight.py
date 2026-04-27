#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = SKILL_ROOT.parent.parent
LOCAL_DATA_ROOT = WORKSPACE_ROOT / "local-data"

TRUTH_DB = LOCAL_DATA_ROOT / "cleaning_robot_competitive_ops_fact" / "db" / "cleaning_robot_competitive_ops_fact.db"
VOC_DB = LOCAL_DATA_ROOT / "cleaning_robot_voc_feedback_log" / "db" / "cleaning_robot_voc_feedback_log.db"
SURVEY_DB = LOCAL_DATA_ROOT / "cleaning_robot_quant_survey" / "db" / "cleaning_robot_quant_survey.db"
SUMMARY_DB = LOCAL_DATA_ROOT / "cleaning_robot_summary_qual_interview" / "db" / "cleaning_robot_summary_qual_interview.db"
INTERVIEW_DB = LOCAL_DATA_ROOT / "cleaning_robot_qual_interview" / "db" / "cleaning_robot_qual_interview.db"


@dataclass(frozen=True)
class ModuleSpec:
    code: str
    name_cn: str
    survey_col: str | None = None
    summary_col: str | None = None
    use_voc: bool = False
    use_raw_interview: bool = False


MODULE_SPECS: tuple[ModuleSpec, ...] = (
    ModuleSpec("voc_analysis", "VOC统计分析", use_voc=True),
    ModuleSpec("competition_diff", "竞品差异", use_voc=True),
    ModuleSpec("user_profile", "用户画像", survey_col="user_profile_support", summary_col="has_user_profile"),
    ModuleSpec("home_environment", "房屋与环境", survey_col="home_environment_support", summary_col="has_home_environment", use_voc=True),
    ModuleSpec("pre_purchase_substitute", "购前替代方式", survey_col="pre_purchase_substitute_support"),
    ModuleSpec("purchase_motivation", "购买动机", survey_col="purchase_motivation_support", summary_col="has_purchase_motivation"),
    ModuleSpec("purchase_journey", "购买旅程", survey_col="purchase_journey_support", summary_col="has_purchase_journey"),
    ModuleSpec("usage_journey", "使用旅程", survey_col="usage_journey_support", summary_col="has_usage_feedback", use_voc=True),
    ModuleSpec("concept_validation", "概念验证", survey_col="concept_validation_support", summary_col="has_concept_validation"),
    ModuleSpec("price_willingness", "价格与付费意愿", survey_col="price_willingness_support"),
    ModuleSpec("evidence_trace", "原始证据追溯", summary_col="has_open_discussion", use_raw_interview=True),
)


SURVEY_LEVEL_SCORE = {"不支持": 0, "部分支持": 1, "支持": 2}


def normalize_text(value: str) -> str:
    text = value.strip().lower()
    for old in [" ", "\u3000", "-", "_", "/", "（", "）", "(", ")", "【", "】", ":", "：", ".", ","]:
        text = text.replace(old, "")
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multisource preflight for robot-product analysis.")
    parser.add_argument("--category-name", default="机器人产品", help="Category label shown in preflight output")
    parser.add_argument("--spu", action="append", default=[], help="SPU id or SPU name, repeatable")
    parser.add_argument("--cohort-id", action="append", default=[], help="Cohort id from competitive truth source, repeatable")
    parser.add_argument("--market", default=None, help="Market scope filter, such as cn / eu / kr / global")
    parser.add_argument("--survey-topic", action="append", default=[], help="Survey topic filter, repeatable")
    parser.add_argument("--module", action="append", default=[], help="Requested module code, repeatable")
    parser.add_argument("--require-voc", action="store_true", help="Only keep selected SPUs that have VOC coverage")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format")
    return parser.parse_args()


def resolve_read_db_path(db_path: Path) -> Path:
    if db_path != VOC_DB:
        return db_path
    archive_dir = db_path.parent.parent / "archive"
    archives = sorted(archive_dir.glob("cleaning_robot_voc_feedback_log.*.db"), reverse=True)
    return archives[0] if archives else db_path


def ensure_voc_compat_views(conn: sqlite3.Connection) -> None:
    names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    }
    if "vw_voc_message_tag_mapped" not in names and {"voc_message", "voc_message_tag"}.issubset(names):
        conn.execute(
            """
            CREATE TEMP VIEW vw_voc_message_tag_mapped AS
            SELECT
                m.canonical_spu_id,
                t.message_uid,
                t.tag_name,
                t.tag_sentiment,
                '标签主题' AS topic_domain_name_cn,
                '' AS topic_group_name_cn,
                '' AS context_bucket_name_cn,
                'tag' AS topic_domain_code,
                '' AS context_bucket_code
            FROM voc_message_tag t
            JOIN voc_message m
                ON t.message_uid = m.message_uid
            """
        )
    temp_names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_temp_master WHERE type IN ('table', 'view')"
        ).fetchall()
    }
    if "vw_spu_context_feature_summary" not in names and "vw_spu_context_feature_summary" not in temp_names and "vw_voc_message_tag_mapped" in (names | temp_names):
        conn.execute(
            """
            CREATE TEMP VIEW vw_spu_context_feature_summary AS
            SELECT
                canonical_spu_id,
                context_bucket_name_cn,
                topic_group_name_cn,
                tag_name,
                tag_sentiment,
                COUNT(DISTINCT message_uid) AS message_count
            FROM vw_voc_message_tag_mapped
            GROUP BY
                canonical_spu_id,
                context_bucket_name_cn,
                topic_group_name_cn,
                tag_name,
                tag_sentiment
            """
        )


def connect(db_path: Path) -> sqlite3.Connection:
    resolved = resolve_read_db_path(db_path)
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    if resolved != db_path or resolved == VOC_DB:
        ensure_voc_compat_views(conn)
    return conn


def resolve_spus(conn: sqlite3.Connection, requested_tokens: list[str]) -> list[sqlite3.Row]:
    if not requested_tokens:
        return []

    rows = list(
        conn.execute(
            """
            SELECT spu_id, spu_name, brand_name_cn, self_competitor_type
            FROM spu_dim
            ORDER BY spu_name
            """
        )
    )
    by_id = {row["spu_id"]: row for row in rows}
    resolved: list[sqlite3.Row] = []
    seen: set[str] = set()

    for token in requested_tokens:
        token_norm = normalize_text(token)
        direct = by_id.get(token)
        if direct and direct["spu_id"] not in seen:
            resolved.append(direct)
            seen.add(direct["spu_id"])
            continue
        for row in rows:
            if row["spu_id"] in seen:
                continue
            if token_norm == normalize_text(row["spu_name"]) or token_norm in normalize_text(row["spu_name"]):
                resolved.append(row)
                seen.add(row["spu_id"])
                break
    return resolved


def resolve_cohort_spus(conn: sqlite3.Connection, cohort_ids: list[str]) -> tuple[list[sqlite3.Row], list[str]]:
    if not cohort_ids:
        return [], []
    placeholders = ", ".join("?" for _ in cohort_ids)
    rows = list(
        conn.execute(
            f"""
            SELECT DISTINCT
                c.cohort_id,
                c.cohort_name,
                c.member_role,
                c.priority_order,
                c.product_id,
                m.spu_id,
                s.spu_name,
                s.brand_name_cn,
                s.self_competitor_type
            FROM vw_cohort_member_brief c
            JOIN product_spu_map m
                ON c.product_id = m.product_id
            JOIN spu_dim s
                ON m.spu_id = s.spu_id
            WHERE c.cohort_id IN ({placeholders})
            ORDER BY c.cohort_id, c.priority_order
            """,
            cohort_ids,
        )
    )
    found_cohorts = sorted({row["cohort_id"] for row in rows})
    missing = [cohort_id for cohort_id in cohort_ids if cohort_id not in found_cohorts]
    cohort_order = {cohort_id: idx for idx, cohort_id in enumerate(cohort_ids)}
    rows.sort(key=lambda row: (cohort_order.get(row["cohort_id"], 999), row["priority_order"] if row["priority_order"] is not None else 999))
    deduped: list[sqlite3.Row] = []
    seen: set[str] = set()
    for row in rows:
        if row["spu_id"] in seen:
            continue
        seen.add(row["spu_id"])
        deduped.append(row)
    return deduped, missing


def build_in_clause(values: list[str]) -> tuple[str, list[str]]:
    placeholders = ", ".join("?" for _ in values)
    return f"({placeholders})", values


def fetch_voc_stats(conn: sqlite3.Connection, spu_ids: list[str]) -> list[sqlite3.Row]:
    sql = """
        SELECT
            canonical_spu_id,
            COALESCE(spu_name, canonical_spu_id) AS spu_name,
            COUNT(*) AS message_count,
            SUM(CASE WHEN sentiment = '负面' THEN 1 ELSE 0 END) AS negative_count,
            MIN(posted_at) AS first_posted_at,
            MAX(posted_at) AS last_posted_at
        FROM vw_voc_message_brief
    """
    params: list[str] = []
    if spu_ids:
        clause, params = build_in_clause(spu_ids)
        sql += f" WHERE canonical_spu_id IN {clause}"
    sql += " GROUP BY canonical_spu_id, COALESCE(spu_name, canonical_spu_id) ORDER BY message_count DESC"
    return list(conn.execute(sql, params))


def filter_spus_by_voc(selected_spus: list[dict[str, object]], voc_rows: list[sqlite3.Row]) -> list[dict[str, object]]:
    voc_spu_ids = {row["canonical_spu_id"] for row in voc_rows}
    return [row for row in selected_spus if row["spu_id"] in voc_spu_ids]


def fetch_survey_waves(conn: sqlite3.Connection, spu_ids: list[str], market: str | None, survey_topics: list[str]) -> list[sqlite3.Row]:
    sql = """
        SELECT
            w.wave_id,
            v.wave_name,
            v.market_scope,
            v.inferred_spu_id,
            v.survey_topic,
            v.user_profile_support,
            v.home_environment_support,
            v.pre_purchase_substitute_support,
            v.purchase_motivation_support,
            v.purchase_journey_support,
            v.usage_journey_support,
            v.concept_validation_support,
            v.price_willingness_support
        FROM vw_wave_capability_summary v
        JOIN survey_wave w
            ON v.wave_name = w.wave_name
        WHERE 1=1
    """
    params: list[str] = []
    if spu_ids:
        clause, values = build_in_clause(spu_ids)
        sql += f" AND (v.inferred_spu_id IN {clause})"
        params.extend(values)
    if market:
        sql += " AND v.market_scope = ?"
        params.append(market)
    if survey_topics:
        clause, values = build_in_clause(survey_topics)
        sql += f" AND v.survey_topic IN {clause}"
        params.extend(values)
    sql += " ORDER BY v.wave_name"
    return list(conn.execute(sql, params))


def fetch_summary_coverage(conn: sqlite3.Connection, spu_ids: list[str], market: str | None) -> list[sqlite3.Row]:
    sql = """
        SELECT
            study_name,
            batch_market_scope,
            inferred_spu_id,
            COUNT(*) AS case_count,
            SUM(has_user_profile) AS has_user_profile,
            SUM(has_home_environment) AS has_home_environment,
            SUM(has_purchase_cognition) AS has_purchase_cognition,
            SUM(has_purchase_motivation) AS has_purchase_motivation,
            SUM(has_purchase_journey) AS has_purchase_journey,
            SUM(has_usage_feedback) AS has_usage_feedback,
            SUM(has_user_needs) AS has_user_needs,
            SUM(has_concept_validation) AS has_concept_validation,
            SUM(has_open_discussion) AS has_open_discussion
        FROM vw_summary_case_module_coverage
        WHERE 1=1
    """
    params: list[str] = []
    if spu_ids:
        clause, values = build_in_clause(spu_ids)
        sql += f" AND inferred_spu_id IN {clause}"
        params.extend(values)
    if market:
        sql += " AND batch_market_scope = ?"
        params.append(market)
    sql += " GROUP BY study_name, batch_market_scope, inferred_spu_id ORDER BY study_name, case_count DESC"
    return list(conn.execute(sql, params))


def fetch_raw_interview_coverage(conn: sqlite3.Connection, spu_ids: list[str], market: str | None) -> list[sqlite3.Row]:
    sql = """
        SELECT
            ic.inferred_spu_id,
            CASE
                WHEN sb.study_name LIKE '%中国%' THEN 'cn'
                WHEN sb.study_name LIKE '%韩国%' THEN 'kr'
                WHEN sb.study_name LIKE '%德法%' THEN 'eu'
                ELSE ic.country_scope
            END AS market_scope,
            COUNT(*) AS case_count,
            SUM(CASE WHEN ic.extraction_status = 'pending_decoder' THEN 1 ELSE 0 END) AS pending_decoder_cases,
            SUM(CASE WHEN ic.paragraph_count > 0 THEN 1 ELSE 0 END) AS decoded_cases
        FROM interview_case ic
        JOIN study_batch sb
            ON ic.study_batch_id = sb.study_batch_id
        WHERE 1=1
    """
    params: list[str] = []
    if spu_ids:
        clause, values = build_in_clause(spu_ids)
        sql += f" AND ic.inferred_spu_id IN {clause}"
        params.extend(values)
    if market:
        sql += " AND (CASE WHEN sb.study_name LIKE '%中国%' THEN 'cn' WHEN sb.study_name LIKE '%韩国%' THEN 'kr' WHEN sb.study_name LIKE '%德法%' THEN 'eu' ELSE ic.country_scope END) = ?"
        params.append(market)
    sql += " GROUP BY ic.inferred_spu_id, market_scope ORDER BY case_count DESC"
    return list(conn.execute(sql, params))


def aggregate_survey_support(waves: list[sqlite3.Row], survey_col: str | None) -> tuple[str, list[str]]:
    if not survey_col:
        return "不支持", []
    levels = [row[survey_col] for row in waves if row[survey_col] is not None]
    if not levels:
        return "不支持", []
    if any(level == "支持" for level in levels):
        return "支持", [row["wave_name"] for row in waves if row[survey_col] == "支持"]
    if any(level == "部分支持" for level in levels):
        return "部分支持", [row["wave_name"] for row in waves if row[survey_col] == "部分支持"]
    return "不支持", []


def aggregate_summary_support(summary_rows: list[sqlite3.Row], summary_col: str | None) -> tuple[str, list[str]]:
    if not summary_col:
        return "不支持", []
    matched_studies: list[str] = []
    total = 0
    for row in summary_rows:
        value = row[summary_col]
        if value and int(value) > 0:
            total += int(value)
            matched_studies.append(f"{row['study_name']}:{row['inferred_spu_id'] or 'generic'}")
    if total > 0:
        return "部分支持", matched_studies
    return "不支持", []


def aggregate_voc_support(voc_rows: list[sqlite3.Row], module_code: str, selected_spu_count: int) -> tuple[str, str | None]:
    if not voc_rows:
        return "不支持", None
    if module_code == "voc_analysis":
        return "支持", f"spu_count={len(voc_rows)}"
    if module_code == "competition_diff":
        qualified = [row for row in voc_rows if int(row["message_count"]) >= 300]
        if selected_spu_count >= 2 and len(qualified) >= 2:
            return "支持", f"qualified_spu={len(qualified)}"
        if len(voc_rows) >= 1:
            return "部分支持", f"qualified_spu={len(qualified)}"
        return "不支持", None
    if module_code in {"home_environment", "usage_journey"}:
        qualified = [row for row in voc_rows if int(row["message_count"]) >= 100]
        if qualified:
            return "部分支持", f"qualified_spu={len(qualified)}"
    return "不支持", None


def aggregate_raw_interview_support(raw_rows: list[sqlite3.Row]) -> tuple[str, str | None]:
    if not raw_rows:
        return "不支持", None
    decoded_cases = sum(int(row["decoded_cases"]) for row in raw_rows if row["decoded_cases"] is not None)
    case_count = sum(int(row["case_count"]) for row in raw_rows if row["case_count"] is not None)
    if decoded_cases > 0:
        return "支持", f"decoded_cases={decoded_cases}"
    if case_count > 0:
        return "部分支持", f"indexed_cases={case_count}"
    return "不支持", None


def combine_support_levels(*levels: str) -> str:
    if "支持" in levels:
        return "支持"
    if "部分支持" in levels:
        return "部分支持"
    return "不支持"


def preferred_sources(module: ModuleSpec, survey_level: str, summary_level: str, voc_level: str, raw_level: str) -> tuple[str, str]:
    primary: list[str] = []
    secondary: list[str] = []
    if survey_level == "支持":
        primary.append("统一问卷")
    elif survey_level == "部分支持":
        secondary.append("统一问卷")
    if module.use_voc:
        if voc_level == "支持":
            if "VOC" not in primary:
                primary.append("VOC")
        elif voc_level == "部分支持":
            secondary.append("VOC")
    if summary_level == "部分支持":
        secondary.append("访谈总结")
    if raw_level == "支持":
        secondary.append("原始访谈")
    elif raw_level == "部分支持":
        secondary.append("原始访谈索引")
    return " + ".join(primary) or "-", " + ".join(dict.fromkeys(secondary)) or "-"


def humanize_evidence(
    survey_evidence: list[str],
    summary_evidence: list[str],
    voc_evidence: str | None,
    raw_evidence: str | None,
) -> str:
    parts: list[str] = []
    if survey_evidence:
        preview = "、".join(survey_evidence[:2])
        suffix = " 等" if len(survey_evidence) > 2 else ""
        parts.append(f"问卷：{len(survey_evidence)} 个可用波次（{preview}{suffix}）")
    if summary_evidence:
        preview = "、".join(summary_evidence[:2])
        suffix = " 等" if len(summary_evidence) > 2 else ""
        parts.append(f"访谈总结：{len(summary_evidence)} 组案例覆盖（{preview}{suffix}）")
    if voc_evidence:
        if voc_evidence.startswith("spu_count="):
            count = voc_evidence.split("=", 1)[1]
            parts.append(f"VOC：{count} 个对象有可用覆盖")
        elif voc_evidence.startswith("qualified_spu="):
            count = voc_evidence.split("=", 1)[1]
            parts.append(f"VOC：{count} 个对象达到稳定样本门槛")
        else:
            parts.append(f"VOC：{voc_evidence}")
    if raw_evidence:
        if raw_evidence.startswith("indexed_cases="):
            count = raw_evidence.split("=", 1)[1]
            parts.append(f"原始访谈：{count} 个可追溯案例索引")
        elif raw_evidence.startswith("decoded_cases="):
            count = raw_evidence.split("=", 1)[1]
            parts.append(f"原始访谈：{count} 个已解码案例")
        else:
            parts.append(f"原始访谈：{raw_evidence}")
    return "；".join(parts) if parts else "-"


def build_support_matrix(
    module_specs: list[ModuleSpec],
    voc_rows: list[sqlite3.Row],
    survey_rows: list[sqlite3.Row],
    summary_rows: list[sqlite3.Row],
    raw_rows: list[sqlite3.Row],
    selected_spu_count: int,
) -> list[dict[str, object]]:
    matrix: list[dict[str, object]] = []
    for spec in module_specs:
        survey_level, survey_evidence = aggregate_survey_support(survey_rows, spec.survey_col)
        summary_level, summary_evidence = aggregate_summary_support(summary_rows, spec.summary_col)
        voc_level, voc_evidence = aggregate_voc_support(voc_rows, spec.code, selected_spu_count) if spec.use_voc else ("不支持", None)
        raw_level, raw_evidence = aggregate_raw_interview_support(raw_rows) if spec.use_raw_interview else ("不支持", None)
        overall_level = combine_support_levels(survey_level, summary_level, voc_level, raw_level)
        primary_source, secondary_source = preferred_sources(spec, survey_level, summary_level, voc_level, raw_level)
        evidence_parts: list[str] = []
        if survey_evidence:
            evidence_parts.append(f"survey={len(survey_evidence)} wave")
        if summary_evidence:
            evidence_parts.append(f"summary={len(summary_evidence)} group")
        if voc_evidence:
            evidence_parts.append(voc_evidence)
        if raw_evidence:
            evidence_parts.append(raw_evidence)
        matrix.append(
            {
                "module_code": spec.code,
                "module_name_cn": spec.name_cn,
                "support_level": overall_level,
                "primary_source": primary_source,
                "secondary_source": secondary_source,
                "survey_level": survey_level,
                "summary_level": summary_level,
                "voc_level": voc_level,
                "raw_level": raw_level,
                "evidence": humanize_evidence(survey_evidence, summary_evidence, voc_evidence, raw_evidence),
            }
        )
    return matrix


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def render_markdown(
    category_name: str,
    selected_spus: list[dict[str, object]],
    unresolved_spu_tokens: list[str],
    unresolved_cohort_ids: list[str],
    market: str | None,
    survey_topics: list[str],
    voc_rows: list[sqlite3.Row],
    survey_rows: list[sqlite3.Row],
    summary_rows: list[sqlite3.Row],
    raw_rows: list[sqlite3.Row],
    support_matrix: list[dict[str, object]],
) -> str:
    lines: list[str] = []
    lines.append("## 多源 Preflight")
    lines.append("")
    lines.append(f"- 品类：`{category_name}`")
    lines.append(f"- 市场过滤：`{market or 'ALL'}`")
    lines.append(f"- SPU 过滤：`{', '.join(row['spu_id'] for row in selected_spus) if selected_spus else 'ALL'}`")
    lines.append(f"- Survey Topic 过滤：`{', '.join(survey_topics) if survey_topics else 'ALL'}`")
    if unresolved_spu_tokens:
        lines.append(f"- 未匹配 SPU：`{', '.join(unresolved_spu_tokens)}`")
    if unresolved_cohort_ids:
        lines.append(f"- 未命中 Cohort：`{', '.join(unresolved_cohort_ids)}`")
    lines.append("")

    if selected_spus:
        lines.append("### 对象归一")
        lines.append("")
        lines.append(
            markdown_table(
                ["spu_id", "spu_name", "brand_name_cn", "self_competitor_type"],
                [[row["spu_id"], row["spu_name"], row["brand_name_cn"], row["self_competitor_type"]] for row in selected_spus],
            )
        )
        lines.append("")

    lines.append("### 数据源状态")
    lines.append("")
    lines.append(
        markdown_table(
            ["数据源", "记录数", "备注"],
            [
                ["VOC", len(voc_rows), "按 SPU 聚合后的对象数"],
                ["统一问卷波次", len(survey_rows), "经过市场/SPU/topic 过滤后的 wave 数"],
                ["访谈总结分组", len(summary_rows), "study + spu 聚合后的分组数"],
                ["原始访谈分组", len(raw_rows), "spu + market 聚合后的分组数"],
            ],
        )
    )
    lines.append("")

    if voc_rows:
        lines.append("### VOC 覆盖")
        lines.append("")
        lines.append(
            markdown_table(
                ["spu_name", "message_count", "negative_count", "first_posted_at", "last_posted_at"],
                [[row["spu_name"], row["message_count"], row["negative_count"], row["first_posted_at"], row["last_posted_at"]] for row in voc_rows[:12]],
            )
        )
        lines.append("")

    if survey_rows:
        lines.append("### 问卷能力")
        lines.append("")
        lines.append(
            markdown_table(
                ["wave_name", "market_scope", "inferred_spu_id", "survey_topic", "user_profile", "purchase_motivation", "purchase_journey", "concept_validation", "price_willingness"],
                [
                    [
                        row["wave_name"],
                        row["market_scope"],
                        row["inferred_spu_id"] or "",
                        row["survey_topic"] or "",
                        row["user_profile_support"],
                        row["purchase_motivation_support"],
                        row["purchase_journey_support"],
                        row["concept_validation_support"],
                        row["price_willingness_support"],
                    ]
                    for row in survey_rows[:12]
                ],
            )
        )
        lines.append("")

    if summary_rows:
        lines.append("### 访谈总结覆盖")
        lines.append("")
        lines.append(
            markdown_table(
                ["study_name", "batch_market_scope", "inferred_spu_id", "case_count", "user_profile_cases", "purchase_journey_cases", "concept_validation_cases"],
                [
                    [
                        row["study_name"],
                        row["batch_market_scope"],
                        row["inferred_spu_id"] or "",
                        row["case_count"],
                        row["has_user_profile"],
                        row["has_purchase_journey"],
                        row["has_concept_validation"],
                    ]
                    for row in summary_rows[:12]
                ],
            )
        )
        lines.append("")

    lines.append("### 支持度判断")
    lines.append("")
    lines.append(
        markdown_table(
            ["模块", "支持度", "主来源", "辅来源", "证据"],
            [
                [
                    row["module_name_cn"],
                    row["support_level"],
                    row["primary_source"],
                    row["secondary_source"],
                    row["evidence"],
                ]
                for row in support_matrix
            ],
        )
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    result = collect_preflight_result(args)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            render_markdown(
                args.category_name,
                result["selected_spus"],
                result["unresolved_spu_tokens"],
                result["unresolved_cohort_ids"],
                args.market,
                args.survey_topic,
                result["voc_rows"],
                result["survey_rows"],
                result["summary_rows"],
                result["raw_rows"],
                result["support_matrix"],
            )
        )


def collect_preflight_result(args: argparse.Namespace) -> dict[str, object]:
    truth_conn = connect(TRUTH_DB)
    voc_conn = connect(VOC_DB)
    survey_conn = connect(SURVEY_DB)
    summary_conn = connect(SUMMARY_DB)
    interview_conn = connect(INTERVIEW_DB)

    selected_spus_from_name = [dict(row) for row in resolve_spus(truth_conn, args.spu)]
    cohort_spus, unresolved_cohort_ids = resolve_cohort_spus(truth_conn, args.cohort_id)
    selected_spus = selected_spus_from_name[:]
    seen_spu_ids = {row["spu_id"] for row in selected_spus}
    for row in cohort_spus:
        row_dict = dict(row)
        if row_dict["spu_id"] in seen_spu_ids:
            continue
        seen_spu_ids.add(row_dict["spu_id"])
        selected_spus.append(row_dict)

    resolved_ids = [row["spu_id"] for row in selected_spus]
    unresolved_tokens = [token for token in args.spu if token not in resolved_ids and all(token != row["spu_name"] for row in selected_spus)]

    requested_modules = {spec.code for spec in MODULE_SPECS}
    if args.module:
        requested_modules = set(args.module)
    module_specs = [spec for spec in MODULE_SPECS if spec.code in requested_modules]

    voc_rows = fetch_voc_stats(voc_conn, resolved_ids)
    preserve_non_voc_selected = bool(getattr(args, "preserve_non_voc_selected", False))
    if args.require_voc and selected_spus and not preserve_non_voc_selected:
        selected_spus = filter_spus_by_voc(selected_spus, voc_rows)
        resolved_ids = [row["spu_id"] for row in selected_spus]
        voc_rows = fetch_voc_stats(voc_conn, resolved_ids)
    survey_rows = fetch_survey_waves(survey_conn, resolved_ids, args.market, args.survey_topic)
    summary_rows = fetch_summary_coverage(summary_conn, resolved_ids, args.market)
    raw_rows = fetch_raw_interview_coverage(interview_conn, resolved_ids, args.market)
    support_matrix = build_support_matrix(module_specs, voc_rows, survey_rows, summary_rows, raw_rows, len(resolved_ids))

    result = {
        "category_name": args.category_name,
        "market": args.market,
        "selected_spus": selected_spus,
        "unresolved_spu_tokens": unresolved_tokens,
        "selected_cohort_ids": args.cohort_id,
        "unresolved_cohort_ids": unresolved_cohort_ids,
        "survey_topics": args.survey_topic,
        "voc_rows": [dict(row) for row in voc_rows],
        "survey_rows": [dict(row) for row in survey_rows],
        "summary_rows": [dict(row) for row in summary_rows],
        "raw_rows": [dict(row) for row in raw_rows],
        "support_matrix": support_matrix,
    }

    truth_conn.close()
    voc_conn.close()
    survey_conn.close()
    summary_conn.close()
    interview_conn.close()
    return result


if __name__ == "__main__":
    main()
