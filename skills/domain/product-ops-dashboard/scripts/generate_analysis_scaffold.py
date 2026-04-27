#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from derive_higher_order_insights import (
    build_cross_source_interpretation,
    build_survey_segment_comparison,
    build_voc_problem_packages,
    extract_summary_insight_cards,
)
from run_multisource_preflight import SUMMARY_DB, SURVEY_DB, TRUTH_DB, VOC_DB, collect_preflight_result, ensure_voc_compat_views, fetch_survey_waves


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate markdown scaffold after multisource preflight.")
    parser.add_argument("--category-name", default="机器人产品", help="Category label shown in scaffold")
    parser.add_argument("--spu", action="append", default=[], help="SPU id or SPU name, repeatable")
    parser.add_argument("--cohort-id", action="append", default=[], help="Cohort id from competitive truth source, repeatable")
    parser.add_argument("--market", default=None, help="Market scope filter, such as cn / eu / kr / global")
    parser.add_argument("--survey-topic", action="append", default=[], help="Survey topic filter, repeatable")
    parser.add_argument("--module", action="append", default=[], help="Requested module code, repeatable")
    parser.add_argument("--require-voc", action="store_true", help="Only keep selected SPUs that have VOC coverage")
    parser.add_argument("--analysis-title", default=None, help="Markdown title override")
    parser.add_argument("--analysis-goal", action="append", default=[], help="Analysis goal or user question, repeatable")
    parser.add_argument("--time-scope", default="待补充", help="Time scope label in report scaffold")
    parser.add_argument("--period-id", action="append", default=[], help="Optional analysis period ids, repeatable")
    parser.add_argument("--out", default=None, help="Optional markdown output path")
    return parser.parse_args()


def support_lookup(result: dict[str, object]) -> dict[str, dict[str, object]]:
    return {row["module_code"]: row for row in result["support_matrix"]}  # type: ignore[index]


def should_include(module_row: dict[str, object] | None) -> bool:
    return bool(module_row) and module_row["support_level"] != "不支持"


def source_should_include(module_row: dict[str, object] | None, source_key: str) -> bool:
    return bool(module_row) and module_row.get(source_key) != "不支持"


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def connect_voc() -> sqlite3.Connection:
    archive_dir = Path(VOC_DB).parent.parent / "archive"
    archives = sorted(archive_dir.glob("cleaning_robot_voc_feedback_log.*.db"), reverse=True)
    read_path = archives[0] if archives else Path(VOC_DB)
    conn = sqlite3.connect(f"file:{read_path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    ensure_voc_compat_views(conn)
    return conn


def connect_survey() -> sqlite3.Connection:
    conn = sqlite3.connect(SURVEY_DB)
    conn.row_factory = sqlite3.Row
    return conn


def connect_summary() -> sqlite3.Connection:
    conn = sqlite3.connect(SUMMARY_DB)
    conn.row_factory = sqlite3.Row
    return conn


def connect_truth() -> sqlite3.Connection:
    conn = sqlite3.connect(TRUTH_DB)
    conn.row_factory = sqlite3.Row
    return conn


def as_percent(numerator: float, denominator: float) -> str:
    if not denominator:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    for old in [" ", "\u3000", "-", "_", "/", "（", "）", "(", ")", "【", "】", ":", "：", ".", ",", "?", "？", "、", ";", "；"]:
        text = text.replace(old, "")
    return text


SURVEY_KEYWORDS = {
    "user_profile": ("城市", "性别", "年龄", "行业", "职业", "家庭", "宠物", "面积", "房屋类型", "户型"),
    "home_environment": ("地面材质", "地毯", "地垫", "面积", "房屋类型", "户型", "高差", "区域"),
    "pre_purchase_substitute": ("购买x8之前", "购买x11之前", "购买之前", "之前使用", "上一台", "手持洗地机", "组合清洁", "停止使用"),
    "purchase_motivation": ("购买动机", "最能打动", "吸引力", "最看重", "进一步了解"),
    "purchase_journey": ("渠道购买", "选购过程中", "品类认知", "品牌认知", "pathtopurchase", "购买决策", "购买路径"),
    "usage_journey": ("满意度", "困扰", "问题", "原因", "使用频率", "管理", "分工", "设置", "体验"),
    "concept_validation": ("想象一下", "如果科沃斯推出", "统一平台", "协同工作", "兴趣", "意愿", "担忧", "顾虑", "最有吸引力"),
    "price_willingness": ("额外付费", "购买第二台", "态度", "计划添置", "购买意愿"),
}

THEME_DEFS = [
    {"code": "cleaning_effect", "name_cn": "清洁效果与水痕污渍", "keywords": ("清洁效果", "拖地效果", "污渍", "水渍", "水痕", "顽固污渍", "不干净")},
    {"code": "edge_coverage", "name_cn": "边角与覆盖率", "keywords": ("边角", "漏扫", "漏拖", "覆盖率")},
    {"code": "navigation_obstacle", "name_cn": "避障越障与卡困", "keywords": ("避障", "越障", "台阶", "门槛", "卡困", "地毯", "脱困")},
    {"code": "noise", "name_cn": "噪音体验", "keywords": ("噪音", "噪声", "异音")},
    {"code": "maintenance", "name_cn": "维护与基站操作", "keywords": ("维护", "基站", "集尘", "洗拖布", "烘干", "加液", "尘盒", "滚刷", "主机")},
    {"code": "intelligence_control", "name_cn": "智能/App/语音/地图", "keywords": ("智能", "app", "语音", "地图", "建图", "路径", "引导", "配网", "托管")},
    {"code": "multi_robot", "name_cn": "多机协同与统一控制", "keywords": ("多机", "协同", "第二台", "统一平台", "生态系统", "跨设备", "专区专清", "接力", "分区同步")},
]
SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parent.parent
WORKSPACE_SKILLS_ROOT = SKILL_ROOT.parent
WORKSPACE_ROOT = WORKSPACE_SKILLS_ROOT.parent
OPTIFLOW_ROOT = WORKSPACE_SKILLS_ROOT / "OptiFlow"
WORKSPACE_SKILL_INVENTORY = WORKSPACE_SKILLS_ROOT / "Nexus" / "references" / "workspace_skill_inventory.json"
CAPABILITY_MATRIX_PATH = OPTIFLOW_ROOT / "references" / "current_capability_matrix.md"
MEMORY_ROOT = OPTIFLOW_ROOT / "memory"
GOAL_SPECS = [
    {
        "code": "user_profile",
        "name_cn": "用户画像",
        "keywords": ("用户画像", "画像", "人群", "persona", "profile", "是谁"),
        "feature_codes": ("demographics", "family_home", "tech_adoption"),
    },
    {
        "code": "usage_scenario",
        "name_cn": "使用场景",
        "keywords": ("场景", "工况", "在哪里用", "使用环境", "使用场景"),
        "feature_codes": ("home_environment", "usage_touchpoints", "cleaning_conditions"),
    },
    {
        "code": "pain_need",
        "name_cn": "痛点/需求",
        "keywords": ("痛点", "需求", "不满意", "问题", "need", "pain"),
        "feature_codes": ("pain_need", "trust_burden", "purchase_driver"),
    },
    {
        "code": "intelligence",
        "name_cn": "智能性",
        "keywords": ("智能", "智能性", "导航", "避障", "脱困", "语音", "ai", "主动服务"),
        "feature_codes": ("intelligence_dimensions", "predictability"),
    },
    {
        "code": "value_proposition",
        "name_cn": "价值主张",
        "keywords": ("价值主张", "价值点", "核心价值", "价值支柱", "strategy", "定位"),
        "feature_codes": ("value_opportunity", "purchase_driver", "pain_need"),
    },
]
FEATURE_SPECS = [
    {
        "code": "demographics",
        "name_cn": "年龄/性别/城市/职业/收入/教育",
        "goal_codes": ("user_profile",),
        "module_codes": ("user_profile",),
        "source_types": ("survey", "summary"),
        "lost_reason": "容易只看年龄和性别，忽略城市、职业、收入与教育层次。",
    },
    {
        "code": "family_home",
        "name_cn": "家庭结构/宠物/孩子/房屋面积/户型",
        "goal_codes": ("user_profile", "usage_scenario"),
        "module_codes": ("user_profile", "home_environment"),
        "source_types": ("survey", "summary"),
        "lost_reason": "容易遗漏家庭结构和房屋条件，导致画像偏扁平。",
    },
    {
        "code": "tech_adoption",
        "name_cn": "技术接受度/既有设备/升级换代背景",
        "goal_codes": ("user_profile", "value_proposition"),
        "module_codes": ("pre_purchase_substitute", "purchase_journey"),
        "source_types": ("survey", "summary"),
        "lost_reason": "容易只看购买动机，不看存量设备和升级背景。",
    },
    {
        "code": "home_environment",
        "name_cn": "地面材质/空间复杂度/门槛/地毯/低矮空间",
        "goal_codes": ("usage_scenario", "pain_need", "intelligence"),
        "module_codes": ("home_environment", "voc_analysis"),
        "source_types": ("survey", "summary", "voc"),
        "lost_reason": "容易漏掉地毯、门槛、低矮底部等高影响场景变量。",
    },
    {
        "code": "usage_touchpoints",
        "name_cn": "使用频次/重点区域/维护触点/家庭分工",
        "goal_codes": ("usage_scenario", "pain_need"),
        "module_codes": ("usage_journey", "home_environment"),
        "source_types": ("survey", "summary", "voc"),
        "lost_reason": "容易只看清洁结果，不看真正触发体验的使用触点。",
    },
    {
        "code": "cleaning_conditions",
        "name_cn": "污渍类型/毛发/灰尘/重污场景",
        "goal_codes": ("usage_scenario", "pain_need", "value_proposition"),
        "module_codes": ("voc_analysis", "usage_journey"),
        "source_types": ("voc", "survey", "summary"),
        "lost_reason": "容易只看一般性‘清洁效果’，忽略重污和毛发等极端场景。",
    },
    {
        "code": "pain_need",
        "name_cn": "核心痛点/核心需求",
        "goal_codes": ("pain_need", "value_proposition"),
        "module_codes": ("voc_analysis", "usage_journey", "purchase_motivation"),
        "source_types": ("voc", "survey", "summary"),
        "lost_reason": "容易把痛点和需求混成一句话，缺少拆解和排序。",
    },
    {
        "code": "trust_burden",
        "name_cn": "信任感/负担转移/是否真正解放双手",
        "goal_codes": ("pain_need", "value_proposition"),
        "module_codes": ("usage_journey", "purchase_motivation", "purchase_journey"),
        "source_types": ("survey", "summary", "voc"),
        "lost_reason": "容易忽略‘用户是否真的信任机器’这一层需求。",
    },
    {
        "code": "purchase_driver",
        "name_cn": "购买初心/替代方式/愿付费度/价值判断",
        "goal_codes": ("pain_need", "value_proposition"),
        "module_codes": ("pre_purchase_substitute", "purchase_motivation", "price_willingness"),
        "source_types": ("survey", "summary"),
        "lost_reason": "容易只看使用后的问题，不看买之前为什么买。",
    },
    {
        "code": "intelligence_dimensions",
        "name_cn": "导航/避障/脱困/交互/主动服务",
        "goal_codes": ("intelligence",),
        "module_codes": ("competition_diff", "usage_journey"),
        "source_types": ("voc", "survey", "summary"),
        "lost_reason": "最容易被一句‘智能性不足’笼统带过。",
    },
    {
        "code": "predictability",
        "name_cn": "可预测性/可信度/像工具还是像管家",
        "goal_codes": ("intelligence", "value_proposition"),
        "module_codes": ("usage_journey", "purchase_journey"),
        "source_types": ("survey", "summary", "voc"),
        "lost_reason": "容易只看功能点，不看用户对系统行为的信任。",
    },
    {
        "code": "value_opportunity",
        "name_cn": "高频场景/痛点强度/需求优先级/差异化空间",
        "goal_codes": ("value_proposition",),
        "module_codes": ("competition_diff", "purchase_motivation", "usage_journey"),
        "source_types": ("voc", "survey", "summary"),
        "lost_reason": "容易直接跳价值主张，缺少支撑价值点的证据链。",
    },
]
VALUE_PILLAR_MAP = {
    "清洁效果与水痕污渍": ("结果可信", "重污与水痕场景得到稳定处理", "减少用户对重污残留的不信任"),
    "边角与覆盖率": ("空间完成率", "边角、门槛、低矮底部也能完成清洁", "减少‘还得我补扫’的二次负担"),
    "避障越障与卡困": ("可预测的自动化", "复杂空间里减少卡困和中断", "降低人工善后与救援频次"),
    "噪音体验": ("可持续使用", "让机器进入真正可长期运行的日常时段", "减少高频打扰和家庭冲突"),
}


def fetch_voc_period_rows(conn: sqlite3.Connection, spu_ids: list[str], explicit_period_ids: list[str]) -> list[sqlite3.Row]:
    if not spu_ids:
        return []
    names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_temp_master WHERE type IN ('table', 'view')").fetchall()
    }
    names.update(
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
    )
    if "vw_spu_period_sentiment_summary" not in names:
        placeholders = ", ".join("?" for _ in spu_ids)
        rows = list(
            conn.execute(
                f"""
                SELECT
                    m.canonical_spu_id,
                    COALESCE(d.spu_name, m.canonical_spu_id) AS spu_name,
                    substr(m.posted_at, 1, 7) AS period_id,
                    substr(m.posted_at, 1, 7) AS period_name,
                    'month' AS period_type,
                    CAST(replace(substr(m.posted_at, 1, 7), '-', '') AS INTEGER) AS sort_order,
                    COUNT(*) AS message_count,
                    SUM(CASE WHEN m.sentiment = '正面' THEN 1 ELSE 0 END) AS positive_count,
                    SUM(CASE WHEN m.sentiment = '负面' THEN 1 ELSE 0 END) AS negative_count,
                    SUM(CASE WHEN m.sentiment NOT IN ('正面', '负面') THEN 1 ELSE 0 END) AS neutral_count
                FROM voc_message m
                LEFT JOIN spu_dim d
                    ON m.canonical_spu_id = d.spu_id
                WHERE m.canonical_spu_id IN ({placeholders})
                GROUP BY
                    m.canonical_spu_id,
                    COALESCE(d.spu_name, m.canonical_spu_id),
                    substr(m.posted_at, 1, 7)
                ORDER BY sort_order DESC, spu_name
                """,
                spu_ids,
            )
        )
        if explicit_period_ids:
            rows = [row for row in rows if row["period_id"] in explicit_period_ids]
        if explicit_period_ids:
            return rows
        month_rows = rows
        period_tracker: dict[str, set[str]] = {}
        for row in month_rows:
            period_tracker.setdefault(row["period_id"], set()).add(row["canonical_spu_id"])
        common_months = [pid for pid, spu_set in period_tracker.items() if len(spu_set) == len(spu_ids)]
        if common_months:
            common_months = common_months[:6]
            return [row for row in month_rows if row["period_id"] in common_months]
        return month_rows[: min(len(month_rows), 12)]
    placeholders = ", ".join("?" for _ in spu_ids)
    params: list[object] = list(spu_ids)
    sql = """
        SELECT
            s.canonical_spu_id,
            s.spu_name,
            s.period_id,
            s.period_name,
            s.period_type,
            p.sort_order,
            s.message_count,
            s.positive_count,
            s.negative_count,
            s.neutral_count
        FROM vw_spu_period_sentiment_summary s
        JOIN analysis_period_dim p
            ON s.period_id = p.period_id
        WHERE s.canonical_spu_id IN ({spu_clause})
    """.format(spu_clause=placeholders)
    if explicit_period_ids:
        period_placeholders = ", ".join("?" for _ in explicit_period_ids)
        sql += f" AND s.period_id IN ({period_placeholders})"
        params.extend(explicit_period_ids)
    sql += " ORDER BY p.sort_order DESC, s.spu_name"
    rows = list(conn.execute(sql, params))
    if explicit_period_ids:
        return rows

    selected: list[sqlite3.Row] = []
    period_tracker: dict[str, set[str]] = {}
    quarter_rows = [row for row in rows if row["period_type"] == "quarter"]
    for row in quarter_rows:
        period_tracker.setdefault(row["period_id"], set()).add(row["canonical_spu_id"])
    common_quarters = [pid for pid, spu_set in period_tracker.items() if len(spu_set) == len(spu_ids)]
    if common_quarters:
        common_quarters = common_quarters[:4]
        return [row for row in quarter_rows if row["period_id"] in common_quarters]

    month_rows = [row for row in rows if row["period_type"] == "month"]
    period_tracker = {}
    for row in month_rows:
        period_tracker.setdefault(row["period_id"], set()).add(row["canonical_spu_id"])
    common_months = [pid for pid, spu_set in period_tracker.items() if len(spu_set) == len(spu_ids)]
    if common_months:
        common_months = common_months[:6]
        return [row for row in month_rows if row["period_id"] in common_months]
    return month_rows[: min(len(month_rows), 12)]


def fetch_voc_theme_rows(conn: sqlite3.Connection, spu_ids: list[str]) -> tuple[list[sqlite3.Row], list[sqlite3.Row], list[sqlite3.Row]]:
    if not spu_ids:
        return [], [], []
    placeholders = ", ".join("?" for _ in spu_ids)
    params = list(spu_ids)
    total_messages = conn.execute(
        f"SELECT COUNT(DISTINCT message_uid) FROM voc_message WHERE canonical_spu_id IN ({placeholders})",
        params,
    ).fetchone()[0]
    theme_sql = f"""
        SELECT
            topic_domain_name_cn,
            COALESCE(topic_group_name_cn, '') AS topic_group_name_cn,
            tag_name,
            tag_sentiment,
            COUNT(DISTINCT message_uid) AS message_count
        FROM vw_voc_message_tag_mapped
        WHERE canonical_spu_id IN ({placeholders})
          AND topic_domain_code <> 'unknown'
        GROUP BY topic_domain_name_cn, COALESCE(topic_group_name_cn, ''), tag_name, tag_sentiment
        ORDER BY message_count DESC, tag_name
        LIMIT 12
    """
    negative_sql = f"""
        SELECT
            topic_domain_name_cn,
            COALESCE(topic_group_name_cn, '') AS topic_group_name_cn,
            tag_name,
            COUNT(DISTINCT message_uid) AS message_count
        FROM vw_voc_message_tag_mapped
        WHERE canonical_spu_id IN ({placeholders})
          AND tag_sentiment = '负面'
        GROUP BY topic_domain_name_cn, COALESCE(topic_group_name_cn, ''), tag_name
        ORDER BY message_count DESC, tag_name
        LIMIT 12
    """
    scene_negative_sql = f"""
        SELECT
            topic_group_name_cn,
            tag_name,
            COUNT(DISTINCT message_uid) AS message_count
        FROM vw_voc_message_tag_mapped
        WHERE canonical_spu_id IN ({placeholders})
          AND context_bucket_code = 'scene'
          AND tag_sentiment = '负面'
        GROUP BY topic_group_name_cn, tag_name
        ORDER BY message_count DESC, tag_name
        LIMIT 12
    """
    theme_rows = list(conn.execute(theme_sql, params))
    negative_rows = list(conn.execute(negative_sql, params))
    scene_negative_rows = list(conn.execute(scene_negative_sql, params))
    theme_rows = [dict(row, penetration=as_percent(row["message_count"], total_messages)) for row in theme_rows]  # type: ignore[misc]
    negative_rows = [dict(row, penetration=as_percent(row["message_count"], total_messages)) for row in negative_rows]  # type: ignore[misc]
    return theme_rows, negative_rows, scene_negative_rows


def fetch_voc_product_snapshot(conn: sqlite3.Connection, spu_id: str) -> dict[str, object]:
    base_row = conn.execute(
        """
        SELECT
            canonical_spu_id,
            spu_name,
            COUNT(*) AS message_count,
            SUM(CASE WHEN sentiment = '负面' THEN 1 ELSE 0 END) AS negative_count,
            MIN(posted_at) AS first_posted_at,
            MAX(posted_at) AS last_posted_at
        FROM vw_voc_message_brief
        WHERE canonical_spu_id = ?
        GROUP BY canonical_spu_id, spu_name
        """,
        (spu_id,),
    ).fetchone()
    if not base_row:
        return {}
    total_messages = base_row["message_count"]
    theme_rows = list(
        conn.execute(
            """
            SELECT
                topic_domain_name_cn,
                COALESCE(topic_group_name_cn, '') AS topic_group_name_cn,
                tag_name,
                tag_sentiment,
                COUNT(DISTINCT message_uid) AS message_count
            FROM vw_voc_message_tag_mapped
            WHERE canonical_spu_id = ?
              AND topic_domain_code <> 'unknown'
            GROUP BY topic_domain_name_cn, COALESCE(topic_group_name_cn, ''), tag_name, tag_sentiment
            ORDER BY message_count DESC, tag_name
            LIMIT 8
            """,
            (spu_id,),
        )
    )
    negative_rows = list(
        conn.execute(
            """
            SELECT
                topic_domain_name_cn,
                COALESCE(topic_group_name_cn, '') AS topic_group_name_cn,
                tag_name,
                COUNT(DISTINCT message_uid) AS message_count
            FROM vw_voc_message_tag_mapped
            WHERE canonical_spu_id = ?
              AND tag_sentiment = '负面'
            GROUP BY topic_domain_name_cn, COALESCE(topic_group_name_cn, ''), tag_name
            ORDER BY message_count DESC, tag_name
            LIMIT 8
            """,
            (spu_id,),
        )
    )
    context_rows = list(
        conn.execute(
            """
            SELECT
                context_bucket_name_cn,
                topic_group_name_cn,
                tag_name,
                tag_sentiment,
                message_count
            FROM vw_spu_context_feature_summary
            WHERE canonical_spu_id = ?
            ORDER BY message_count DESC, tag_name
            LIMIT 8
            """,
            (spu_id,),
        )
    )
    return {
        "summary": dict(base_row),
        "themes": [dict(row, penetration=as_percent(row["message_count"], total_messages)) for row in theme_rows],  # type: ignore[misc]
        "negatives": [dict(row, penetration=as_percent(row["message_count"], total_messages)) for row in negative_rows],  # type: ignore[misc]
        "contexts": [dict(row) for row in context_rows],
    }


def fetch_voc_diff_rows(conn: sqlite3.Connection, selected_spus: list[dict[str, object]], voc_rows: list[dict[str, object]], period_rows: list[sqlite3.Row]) -> tuple[list[list[object]], list[list[object]], list[str]]:
    if len(selected_spus) != 2:
        return [], [], []
    base_spu = selected_spus[0]["spu_id"]
    compare_spu = selected_spus[1]["spu_id"]
    totals = {row["canonical_spu_id"]: row["message_count"] for row in voc_rows}
    placeholders = ", ".join("?" for _ in [base_spu, compare_spu])
    diff_sql = f"""
        SELECT
            canonical_spu_id,
            spu_name,
            context_bucket_name_cn,
            topic_group_name_cn,
            tag_name,
            SUM(message_count) AS message_count
        FROM vw_spu_context_feature_summary
        WHERE canonical_spu_id IN ({placeholders})
        GROUP BY canonical_spu_id, spu_name, context_bucket_name_cn, topic_group_name_cn, tag_name
    """
    rows = list(conn.execute(diff_sql, [base_spu, compare_spu]))
    by_tag: dict[tuple[str, str, str], dict[str, float]] = {}
    by_name: dict[str, str] = {}
    for row in rows:
        key = (row["context_bucket_name_cn"] or "", row["topic_group_name_cn"] or "", row["tag_name"])
        by_tag.setdefault(key, {})
        by_tag[key][row["canonical_spu_id"]] = row["message_count"]
        by_name[row["canonical_spu_id"]] = row["spu_name"]

    diff_table: list[list[object]] = []
    ranked: list[tuple[float, list[object]]] = []
    for (bucket, group_name, tag_name), counts in by_tag.items():
        base_count = counts.get(base_spu, 0)
        compare_count = counts.get(compare_spu, 0)
        base_rate = (base_count / totals.get(base_spu, 1)) * 100 if totals.get(base_spu) else 0
        compare_rate = (compare_count / totals.get(compare_spu, 1)) * 100 if totals.get(compare_spu) else 0
        delta_pp = base_rate - compare_rate
        if abs(delta_pp) < 1.0:
            continue
        ranked.append(
            (
                abs(delta_pp),
                [
                    bucket,
                    group_name,
                    tag_name,
                    f"{base_rate:.1f}%",
                    f"{compare_rate:.1f}%",
                    f"{delta_pp:+.1f}pp",
                ],
            )
        )
    ranked.sort(key=lambda item: item[0], reverse=True)
    diff_table = [item[1] for item in ranked[:12]]

    period_lookup: dict[str, dict[str, tuple[int, int]]] = {}
    for row in period_rows:
        period_lookup.setdefault(row["period_name"], {})
        period_lookup[row["period_name"]][row["canonical_spu_id"]] = (row["message_count"], row["negative_count"])
    period_diff_table: list[list[object]] = []
    for period_name, counts in period_lookup.items():
        if base_spu not in counts or compare_spu not in counts:
            continue
        base_msg, base_neg = counts[base_spu]
        compare_msg, compare_neg = counts[compare_spu]
        base_rate = (base_neg / base_msg) * 100 if base_msg else 0
        compare_rate = (compare_neg / compare_msg) * 100 if compare_msg else 0
        period_diff_table.append(
            [
                period_name,
                by_name.get(base_spu, base_spu),
                base_msg,
                f"{base_rate:.1f}%",
                by_name.get(compare_spu, compare_spu),
                compare_msg,
                f"{compare_rate:.1f}%",
                f"{(base_rate - compare_rate):+.1f}pp",
            ]
        )
    insights: list[str] = []
    if period_diff_table:
        latest = period_diff_table[-1]
        insights.append(f"{latest[0]} 中 {latest[1]} 负向率 {latest[3]}，较 {latest[4]} 的 {latest[6]} 高 {latest[7]}")
    if diff_table:
        top = diff_table[0]
        insights.append(f"上下文差异最大标签是 `{top[2]}`，两者渗透率差约 {top[5]}")
    return diff_table, period_diff_table, insights


def build_voc_conclusions(voc_rows: list[dict[str, object]], theme_rows: list[dict[str, object]], negative_rows: list[dict[str, object]], diff_insights: list[str]) -> list[str]:
    conclusions: list[str] = []
    if voc_rows:
        top = voc_rows[0]
        weakest = max(
            voc_rows,
            key=lambda row: (row["negative_count"] / row["message_count"]) if row["message_count"] else 0,
        )
        conclusions.append(f"当前样本量最高的对象是 `{top['spu_name']}`，消息量 `{top['message_count']}`。")
        weakest_rate = as_percent(weakest["negative_count"], weakest["message_count"])
        conclusions.append(f"当前负向率最高的对象是 `{weakest['spu_name']}`，约 `{weakest_rate}`。")
    if theme_rows:
        conclusions.append(f"高频主题以 `{theme_rows[0]['tag_name']}`、`{theme_rows[1]['tag_name'] if len(theme_rows) > 1 else theme_rows[0]['tag_name']}` 为主。")
    if negative_rows:
        conclusions.append(f"高频负面标签主要集中在 `{negative_rows[0]['tag_name']}`、`{negative_rows[1]['tag_name'] if len(negative_rows) > 1 else negative_rows[0]['tag_name']}`。")
    conclusions.extend(diff_insights[:2])
    return conclusions[:5]


def build_pool_period_compare(period_rows: list[sqlite3.Row]) -> list[list[object]]:
    return [
        [
            row["period_name"],
            row["spu_name"],
            row["message_count"],
            as_percent(row["negative_count"], row["message_count"]),
        ]
        for row in sorted(period_rows, key=lambda item: (item["sort_order"], item["spu_name"]))
    ]


def build_voc_product_conclusions(snapshot: dict[str, object]) -> list[str]:
    if not snapshot:
        return ["当前产品暂无 VOC 覆盖。"]
    summary = snapshot["summary"]  # type: ignore[index]
    themes = snapshot["themes"]  # type: ignore[index]
    negatives = snapshot["negatives"]  # type: ignore[index]
    conclusions = [
        f"`{summary['spu_name']}` 当前消息量 `{summary['message_count']}`，负向率 `{as_percent(summary['negative_count'], summary['message_count'])}`。",
    ]
    if themes:
        conclusions.append(f"高频主题以 `{themes[0]['tag_name']}` 为主。")
    if negatives:
        conclusions.append(f"高频负面标签以 `{negatives[0]['tag_name']}` 为主。")
    return conclusions


def build_pool_feature_overview(product_snapshots: list[dict[str, object]]) -> list[list[object]]:
    rows: list[list[object]] = []
    for snapshot in product_snapshots:
        if not snapshot:
            continue
        summary = snapshot["summary"]  # type: ignore[index]
        themes = snapshot["themes"]  # type: ignore[index]
        negatives = snapshot["negatives"]  # type: ignore[index]
        contexts = snapshot["contexts"]  # type: ignore[index]
        rows.append(
            [
                summary["spu_name"],
                themes[0]["tag_name"] if themes else "-",
                negatives[0]["tag_name"] if negatives else "-",
                contexts[0]["tag_name"] if contexts else "-",
            ]
        )
    return rows


def fetch_wave_sample_count(conn: sqlite3.Connection, wave_id: str) -> int:
    row = conn.execute("SELECT COUNT(DISTINCT response_identity_id) FROM response_instance WHERE wave_id = ?", (wave_id,)).fetchone()
    return int(row[0] if row and row[0] is not None else 0)


def theme_matches(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(keyword) in normalized for keyword in keywords)


def build_voc_theme_evidence(theme_rows: list[dict[str, object]], negative_rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for theme in THEME_DEFS:
        pos_matches = [row for row in theme_rows if theme_matches(str(row["tag_name"]), theme["keywords"])]
        neg_matches = [row for row in negative_rows if theme_matches(str(row["tag_name"]), theme["keywords"])]
        result[theme["code"]] = {
            "theme_name_cn": theme["name_cn"],
            "positive_rows": pos_matches,
            "negative_rows": neg_matches,
            "positive_count": sum(int(row["message_count"]) for row in pos_matches),
            "negative_count": sum(int(row["message_count"]) for row in neg_matches),
        }
    return result


def build_survey_theme_evidence(survey_wave_details: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for theme in THEME_DEFS:
        matched_rows: list[tuple[str, str, str, object, object]] = []
        unique_question_hits: set[tuple[str, str]] = set()
        for detail in survey_wave_details:
            wave = detail["wave"]
            for capability_rows in detail["capability_tables"].values():
                for question_text, answer_text, count, share in capability_rows:
                    combined = f"{question_text} {answer_text}"
                    if theme_matches(combined, theme["keywords"]):
                        matched_rows.append((wave["wave_name"], question_text, answer_text, count, share))
                        unique_question_hits.add((wave["wave_name"], question_text))
        result[theme["code"]] = {
            "theme_name_cn": theme["name_cn"],
            "rows": matched_rows,
            "count": len(unique_question_hits),
        }
    return result


def fetch_summary_theme_sections(conn: sqlite3.Connection, selected_spu_ids: list[str], market: str | None) -> list[sqlite3.Row]:
    sql = """
        SELECT
            vsn.summary_case_id,
            vsn.study_name,
            vsn.batch_market_scope,
            vsn.period_label,
            vsn.case_title,
            sc.inferred_spu_id,
            vsn.analysis_module_code,
            vsn.analysis_module_name_cn,
            vsn.canonical_section_name_cn,
            vsn.section_title,
            vsn.section_text
        FROM vw_summary_section_normalized vsn
        JOIN summary_case sc
            ON vsn.summary_case_id = sc.summary_case_id
        WHERE 1=1
    """
    params: list[object] = []
    if selected_spu_ids:
        placeholders = ", ".join("?" for _ in selected_spu_ids)
        sql += f" AND vsn.summary_case_id IN (SELECT summary_case_id FROM summary_case WHERE inferred_spu_id IN ({placeholders}))"
        params.extend(selected_spu_ids)
    if market:
        sql += " AND batch_market_scope = ?"
        params.append(market)
    return list(conn.execute(sql, params))


def build_summary_theme_evidence(summary_sections: list[sqlite3.Row]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for theme in THEME_DEFS:
        matched_rows = []
        unique_cases: set[tuple[str, str]] = set()
        for row in summary_sections:
            combined = f"{row['canonical_section_name_cn']} {row['section_text']}"
            if theme_matches(combined, theme["keywords"]):
                matched_rows.append((row["study_name"], row["case_title"], row["canonical_section_name_cn"]))
                unique_cases.add((row["study_name"], row["case_title"]))
        result[theme["code"]] = {
            "theme_name_cn": theme["name_cn"],
            "rows": matched_rows,
            "count": len(unique_cases),
        }
    return result


def build_cross_source_tables(voc_theme_evidence: dict[str, dict[str, object]], survey_theme_evidence: dict[str, dict[str, object]], summary_theme_evidence: dict[str, dict[str, object]]) -> tuple[list[list[object]], list[list[object]], list[list[object]], list[list[object]]]:
    consistent_issues: list[list[object]] = []
    consistent_strengths: list[list[object]] = []
    conflict_rows: list[list[object]] = []
    priority_rows: list[list[object]] = []

    for theme in THEME_DEFS:
        code = theme["code"]
        voc = voc_theme_evidence[code]
        survey = survey_theme_evidence[code]
        summary = summary_theme_evidence[code]
        source_count_issue = sum(
            1
            for value in [
                voc["negative_count"] > 0,
                survey["count"] > 0,
                summary["count"] > 0,
            ]
            if value
        )
        source_count_strength = sum(
            1
            for value in [
                voc["positive_count"] > 0,
                survey["count"] > 0,
                summary["count"] > 0,
            ]
            if value
        )

        if voc["negative_count"] > 0 and source_count_issue >= 2:
            top_neg = voc["negative_rows"][0]["tag_name"] if voc["negative_rows"] else "-"
            consistent_issues.append(
                [
                    theme["name_cn"],
                    f"VOC:{top_neg} ({voc['negative_count']})",
                    f"Survey:{survey['count']}",
                    f"Summary:{summary['count']}",
                    "2+ 源一致，建议优先关注",
                ]
            )
            severity = int(voc["negative_count"])
            priority = "P1" if source_count_issue >= 3 or severity >= 150 else "P2"
            priority_rows.append([theme["name_cn"], source_count_issue, severity, survey["count"], summary["count"], priority])

        if voc["positive_count"] > 0 and source_count_strength >= 2:
            top_pos = voc["positive_rows"][0]["tag_name"] if voc["positive_rows"] else "-"
            consistent_strengths.append(
                [
                    theme["name_cn"],
                    f"VOC:{top_pos} ({voc['positive_count']})",
                    f"Survey:{survey['count']}",
                    f"Summary:{summary['count']}",
                    "2+ 源支持，可视为稳定优势或机会",
                ]
            )

        if voc["negative_count"] >= 50 and survey["count"] == 0 and summary["count"] == 0:
            top_neg = voc["negative_rows"][0]["tag_name"] if voc["negative_rows"] else "-"
            conflict_rows.append(
                [
                    theme["name_cn"],
                    f"VOC:{top_neg} ({voc['negative_count']})",
                    "Survey:0",
                    "Summary:0",
                    "VOC 有明显信号，但其他源暂无直接验证，需补数",
                ]
            )
        elif voc["negative_count"] == 0 and (survey["count"] > 0 or summary["count"] > 0):
            conflict_rows.append(
                [
                    theme["name_cn"],
                    "VOC:0",
                    f"Survey:{survey['count']}",
                    f"Summary:{summary['count']}",
                    "其他源有信号，但 VOC 暂无明显规模性反馈",
                ]
            )

    priority_rows.sort(key=lambda row: (row[5], -row[2], -row[1], -row[3], -row[4]))
    consistent_issues.sort(key=lambda row: row[0])
    consistent_strengths.sort(key=lambda row: row[0])
    conflict_rows.sort(key=lambda row: row[0])
    return consistent_issues[:12], consistent_strengths[:12], conflict_rows[:12], priority_rows[:12]


def build_exec_summary_lines(
    voc_rows: list[dict[str, object]],
    survey_wave_details: list[dict[str, object]],
    priority_rows: list[list[object]],
    conflict_rows: list[list[object]],
) -> list[str]:
    lines: list[str] = []
    if voc_rows:
        highest_risk = max(voc_rows, key=lambda row: (row["negative_count"] / row["message_count"]) if row["message_count"] else 0)
        lines.append(f"`{highest_risk['spu_name']}` 是当前池子里风险最高的对象，负向率约 `{as_percent(highest_risk['negative_count'], highest_risk['message_count'])}`。")
    if priority_rows:
        top_p1 = [row[0] for row in priority_rows if row[5] == "P1"]
        if top_p1:
            lines.append(f"跨源一致的一类重点问题集中在 `{ '、'.join(top_p1[:3]) }`。")
    if survey_wave_details:
        first_wave = survey_wave_details[0]["wave"]
        lines.append(f"当前最可用的问卷入口是 `{first_wave['wave_name']}`，适合先补用户画像、动机与使用旅程。")
    if conflict_rows:
        lines.append(f"当前仍需补数验证的主题包括 `{ '、'.join(row[0] for row in conflict_rows[:2]) }`。")
    return lines[:3]


def build_survey_wave_conclusions(survey_wave_details: list[dict[str, object]]) -> tuple[str, str, str]:
    if not survey_wave_details:
        return "[待填]", "[待填]", "[待填]"
    wave_names = [detail["wave"]["wave_name"] for detail in survey_wave_details]
    selected = "、".join(wave_names[:3]) + (" 等" if len(wave_names) > 3 else "")
    support_map = {
        "用户画像": "user_profile_support",
        "房屋与环境": "home_environment_support",
        "购前替代方式": "pre_purchase_substitute_support",
        "购买动机": "purchase_motivation_support",
        "购买旅程": "purchase_journey_support",
        "使用旅程": "usage_journey_support",
        "概念验证": "concept_validation_support",
        "价格与付费意愿": "price_willingness_support",
    }
    supported: list[str] = []
    unsupported: list[str] = []
    for label, key in support_map.items():
        levels = [detail["wave"][key] for detail in survey_wave_details]
        if any(level == "支持" for level in levels):
            supported.append(label)
        elif all(level == "不支持" for level in levels):
            unsupported.append(label)
    return selected, "、".join(supported) if supported else "暂无", "、".join(unsupported) if unsupported else "暂无"


def build_summary_examples(summary_sections: list[sqlite3.Row], module_name: str, limit: int = 2) -> list[str]:
    seen: list[str] = []
    for row in summary_sections:
        if row["analysis_module_name_cn"] != module_name:
            continue
        title = row["case_title"]
        if title not in seen:
            seen.append(title)
        if len(seen) >= limit:
            break
    return seen


def build_summary_conclusion_lines(summary_sections: list[sqlite3.Row]) -> tuple[str, str, str]:
    profile_examples = build_summary_examples(summary_sections, "用户画像")
    purchase_examples = build_summary_examples(summary_sections, "购买动机") + build_summary_examples(summary_sections, "购买旅程")
    need_examples = build_summary_examples(summary_sections, "用户诉求") + build_summary_examples(summary_sections, "开放讨论与补充")
    profile_line = f"当前典型人设案例主要来自 `{ '、'.join(profile_examples[:2]) }`。" if profile_examples else "[待填]"
    purchase_line = f"决策链路可优先下钻 `{ '、'.join(purchase_examples[:2]) }`。" if purchase_examples else "[待填]"
    need_line = f"隐性需求与开放讨论可优先查看 `{ '、'.join(need_examples[:2]) }`。" if need_examples else "[待填]"
    return profile_line, purchase_line, need_line


def build_summary_module_example_lines(summary_sections: list[sqlite3.Row]) -> dict[str, str]:
    def fmt(module_names: list[str], fallback: str = "当前暂无对应案例") -> str:
        examples: list[str] = []
        for module_name in module_names:
            examples.extend(build_summary_examples(summary_sections, module_name, limit=3))
        deduped: list[str] = []
        for item in examples:
            if item not in deduped:
                deduped.append(item)
        return f"`{'、'.join(deduped[:2])}`" if deduped else fallback

    return {
        "profile": fmt(["用户画像"]),
        "home": fmt(["家居环境与清洁行为"]),
        "purchase": fmt(["购买动机", "购买旅程"]),
        "usage": fmt(["产品使用与反馈"]),
        "needs": fmt(["用户诉求", "开放讨论与补充"]),
        "concept": fmt(["概念与利益点验证"]),
    }


def fetch_proxy_previous_generation_spu_ids(selected_spu_ids: list[str]) -> list[str]:
    if not selected_spu_ids:
        return []
    conn = connect_truth()
    proxy_ids: list[str] = []
    rows = list(
        conn.execute(
            f"""
            SELECT spu_id, series_code, self_competitor_type, lifecycle_status
            FROM spu_dim
            WHERE spu_id IN ({", ".join("?" for _ in selected_spu_ids)})
            """,
            selected_spu_ids,
        )
    )
    for row in rows:
        if row["self_competitor_type"] != "self" or row["lifecycle_status"] != "on_sale":
            continue
        prev = conn.execute(
            """
            SELECT spu_id
            FROM spu_dim
            WHERE self_competitor_type = 'self'
              AND lifecycle_status = 'previous_generation'
              AND series_code = ?
            ORDER BY spu_name DESC
            LIMIT 1
            """,
            (row["series_code"],),
        ).fetchone()
        if prev and prev["spu_id"] not in proxy_ids:
            proxy_ids.append(prev["spu_id"])
    conn.close()
    return proxy_ids


def fetch_proxy_survey_rows(selected_spu_ids: list[str], market: str | None) -> list[dict[str, object]]:
    conn = connect_survey()
    proxy_rows: list[dict[str, object]] = []
    seen_wave_names: set[str] = set()
    previous_proxy_ids = fetch_proxy_previous_generation_spu_ids(selected_spu_ids)

    def add_rows(rows: list[sqlite3.Row], reason: str) -> None:
        for row in rows:
            if row["wave_name"] in seen_wave_names:
                continue
            item = dict(row)
            item["proxy_reason"] = reason
            proxy_rows.append(item)
            seen_wave_names.add(row["wave_name"])

    if previous_proxy_ids:
        add_rows(fetch_survey_waves(conn, previous_proxy_ids, market, []), "同系列上一代本品问卷代理")
    add_rows(fetch_survey_waves(conn, [], market, ["cleaning_needs"]), "品类通用清洁需求问卷代理")
    add_rows(fetch_survey_waves(conn, [], market, ["yiko_multi_robot"]), "生态/多机协同主题问卷代理")
    conn.close()
    return proxy_rows


def fetch_proxy_summary_rows(market: str | None) -> list[dict[str, object]]:
    conn = connect_summary()
    rows = list(
        conn.execute(
            """
            SELECT
                study_name,
                batch_market_scope,
                inferred_spu_id,
                COUNT(*) AS case_count,
                SUM(has_user_profile) AS has_user_profile,
                SUM(has_purchase_motivation) AS has_purchase_motivation,
                SUM(has_purchase_journey) AS has_purchase_journey,
                SUM(has_usage_feedback) AS has_usage_feedback,
                SUM(has_concept_validation) AS has_concept_validation
            FROM vw_summary_case_module_coverage
            WHERE batch_market_scope = COALESCE(?, batch_market_scope)
            GROUP BY study_name, batch_market_scope, inferred_spu_id
            ORDER BY study_name DESC, case_count DESC
            LIMIT 8
            """,
            (market,),
        )
    )
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["proxy_reason"] = "同市场最新定性总结案例代理"
        result.append(item)
    return result


def build_closeout_lines(
    voc_rows: list[dict[str, object]],
    priority_rows: list[list[object]],
    conflict_rows: list[list[object]],
    support_matrix: list[dict[str, object]],
) -> tuple[list[str], list[str], list[str]]:
    can_conclude: list[str] = []
    cannot_conclude: list[str] = []
    next_steps: list[str] = []
    if voc_rows:
        ranked = sorted(voc_rows, key=lambda row: (row["negative_count"] / row["message_count"]) if row["message_count"] else 0, reverse=True)
        if len(ranked) >= 2:
            can_conclude.append(f"`{ranked[0]['spu_name']}` 当前是整池高风险对象，`{ranked[1]['spu_name']}` 是第二梯队风险对象。")
        else:
            can_conclude.append(f"`{ranked[0]['spu_name']}` 当前是这轮样本里的主要高风险对象，但当前对象池还不够宽，不能再硬拉第二梯队。")
    if priority_rows:
        can_conclude.append(f"跨源优先事项已经收敛到 `{ '、'.join(row[0] for row in priority_rows[:3]) }`。")
    unsupported = [row["module_name_cn"] for row in support_matrix if row["support_level"] == "不支持"]
    if unsupported:
        cannot_conclude.append(f"当前无法稳定下结论的模块包括 `{ '、'.join(unsupported) }`。")
    if conflict_rows:
        cannot_conclude.append(f"当前仍需补数验证的主题包括 `{ '、'.join(row[0] for row in conflict_rows[:3]) }`。")
    if priority_rows:
        next_steps.append(f"建议先对 `{priority_rows[0][0]}` 做 pairwise 深挖，并围绕高风险对象补竞品对比。")
    next_steps.append("建议补齐价格/付费意愿或原始访谈解码，再继续收敛商业判断。")
    return can_conclude[:3], cannot_conclude[:3], next_steps[:3]


def fetch_survey_capability_question_summaries(conn: sqlite3.Connection, wave_id: str, capability_code: str, sample_count: int) -> list[list[object]]:
    keywords = SURVEY_KEYWORDS.get(capability_code, ())
    if not keywords:
        return []
    questions = list(
        conn.execute(
            """
            SELECT question_id, question_text, source_column_name, field_type, is_multi_choice
            FROM question_catalog
            WHERE wave_id = ?
              AND field_type != 'system'
            ORDER BY source_column_name
            """,
            (wave_id,),
        )
    )
    matched_questions = [
        row for row in questions if any(normalize_text(keyword) in normalize_text(row["question_text"] or "") for keyword in keywords)
    ]
    rows: list[list[object]] = []
    min_count = max(3, int(sample_count * 0.03)) if sample_count else 3
    for row in matched_questions[:4]:
        if row["is_multi_choice"]:
            option_rows = list(
                conn.execute(
                    """
                    SELECT ao.option_value, COUNT(DISTINCT al.response_identity_id) AS cnt
                    FROM answer_option_long ao
                    JOIN answer_long al
                        ON ao.answer_id = al.answer_id
                    WHERE al.question_id = ?
                    GROUP BY ao.option_value
                    ORDER BY cnt DESC, ao.option_value
                    LIMIT 3
                    """,
                    (row["question_id"],),
                )
            )
            for option_value, cnt in option_rows:
                if cnt < min_count:
                    continue
                rows.append([row["question_text"], option_value, cnt, as_percent(cnt, sample_count)])
        else:
            answer_rows = list(
                conn.execute(
                    """
                    SELECT answer_text, COUNT(DISTINCT response_identity_id) AS cnt
                    FROM answer_long
                    WHERE question_id = ?
                      AND answer_text IS NOT NULL
                      AND trim(answer_text) != ''
                    GROUP BY answer_text
                    ORDER BY cnt DESC, answer_text
                    LIMIT 3
                    """,
                    (row["question_id"],),
                )
            )
            for answer_text, cnt in answer_rows:
                if cnt < min_count:
                    continue
                rows.append([row["question_text"], answer_text, cnt, as_percent(cnt, sample_count)])
    return rows


def resolve_analysis_goal_text(args: argparse.Namespace) -> str:
    goals = [str(item).strip() for item in getattr(args, "analysis_goal", []) if str(item).strip()]
    if goals:
        return "；".join(goals)
    if getattr(args, "analysis_title", None):
        return str(args.analysis_title)
    return f"{args.category_name}用户分析"


def infer_goal_codes(analysis_goal_text: str) -> list[str]:
    normalized = normalize_text(analysis_goal_text)
    matched = [
        spec["code"]
        for spec in GOAL_SPECS
        if any(normalize_text(keyword) in normalized for keyword in spec["keywords"])
    ]
    if matched:
        return matched
    return [spec["code"] for spec in GOAL_SPECS]


def goal_name(goal_code: str) -> str:
    for spec in GOAL_SPECS:
        if spec["code"] == goal_code:
            return spec["name_cn"]
    return goal_code


def feature_name(feature_code: str) -> str:
    for spec in FEATURE_SPECS:
        if spec["code"] == feature_code:
            return spec["name_cn"]
    return feature_code


def max_support_level(levels: list[str]) -> str:
    if "支持" in levels:
        return "支持"
    if "部分支持" in levels:
        return "部分支持"
    return "不支持"


def derive_feature_evidence_strength(
    feature_spec: dict[str, object],
    support_map: dict[str, dict[str, object]],
    *,
    has_direct_survey: bool,
    has_direct_summary: bool,
    has_direct_raw: bool,
    has_direct_voc: bool,
    has_proxy_survey: bool,
    has_proxy_summary: bool,
) -> tuple[str, str, str]:
    module_rows = [support_map[code] for code in feature_spec["module_codes"] if code in support_map]
    levels = [str(row.get("support_level", "不支持")) for row in module_rows]
    support_level = max_support_level(levels)
    source_tokens: list[str] = []
    for row in module_rows:
        for token in (row.get("primary_source"), row.get("secondary_source")):
            text = str(token or "").strip()
            if text and text != "-" and text not in source_tokens:
                source_tokens.append(text)
    source_text = " + ".join(source_tokens) if source_tokens else "-"
    evidence_text = "；".join(
        [str(row.get("evidence", "")).strip() for row in module_rows if str(row.get("evidence", "")).strip() and str(row.get("evidence", "")).strip() != "-"]
    ) or "-"

    if has_direct_survey and any(str(row.get("survey_level")) == "支持" for row in module_rows):
        return "直连强证据", source_text, evidence_text
    if has_direct_voc and any(str(row.get("voc_level")) == "支持" for row in module_rows):
        return "直连强证据", source_text, evidence_text
    if has_direct_summary and any(str(row.get("summary_level")) in {"支持", "部分支持"} for row in module_rows):
        return "直连弱证据", source_text, evidence_text
    if has_direct_raw and any(str(row.get("raw_level")) in {"支持", "部分支持"} for row in module_rows):
        return "直连弱证据", source_text, evidence_text
    if has_direct_survey and any(str(row.get("survey_level")) == "部分支持" for row in module_rows):
        return "直连弱证据", source_text, evidence_text
    if has_direct_voc and any(str(row.get("voc_level")) == "部分支持" for row in module_rows):
        return "直连弱证据", source_text, evidence_text
    if "survey" in feature_spec["source_types"] and has_proxy_survey:
        return "代理证据", source_text if source_text != "-" else "统一问卷代理", evidence_text if evidence_text != "-" else "当前依赖代理问卷波次"
    if "summary" in feature_spec["source_types"] and has_proxy_summary:
        return "代理证据", source_text if source_text != "-" else "访谈总结代理", evidence_text if evidence_text != "-" else "当前依赖代理定性总结"
    return "无证据", source_text, evidence_text


def build_goal_feature_map_rows(goal_codes: list[str]) -> list[list[object]]:
    rows: list[list[object]] = []
    for goal_code in goal_codes:
        spec = next((item for item in GOAL_SPECS if item["code"] == goal_code), None)
        if not spec:
            continue
        rows.append(
            [
                spec["name_cn"],
                "、".join(feature_name(code) for code in spec["feature_codes"]),
            ]
        )
    return rows


def build_feature_exposure_rows(
    goal_codes: list[str],
    support_map: dict[str, dict[str, object]],
    *,
    has_direct_survey: bool,
    has_direct_summary: bool,
    has_direct_raw: bool,
    has_direct_voc: bool,
    has_proxy_survey: bool,
    has_proxy_summary: bool,
) -> list[list[object]]:
    rows: list[list[object]] = []
    for spec in FEATURE_SPECS:
        if not set(spec["goal_codes"]) & set(goal_codes):
            continue
        strength, source_text, evidence_text = derive_feature_evidence_strength(
            spec,
            support_map,
            has_direct_survey=has_direct_survey,
            has_direct_summary=has_direct_summary,
            has_direct_raw=has_direct_raw,
            has_direct_voc=has_direct_voc,
            has_proxy_survey=has_proxy_survey,
            has_proxy_summary=has_proxy_summary,
        )
        support_levels = [
            str(support_map[module_code]["support_level"])
            for module_code in spec["module_codes"]
            if module_code in support_map
        ]
        rows.append(
            [
                "、".join(goal_name(code) for code in spec["goal_codes"]),
                spec["name_cn"],
                max_support_level(support_levels),
                source_text,
                strength,
                evidence_text,
            ]
        )
    return rows


def build_coverage_gap_rows(feature_exposure_rows: list[list[object]]) -> list[list[object]]:
    rows: list[list[object]] = []
    for goal_text, feature_text, support_level, source_text, strength, evidence_text in feature_exposure_rows:
        if strength == "直连强证据":
            continue
        gap_reason = "当前只有代理或弱证据，结论不宜写满。" if strength in {"直连弱证据", "代理证据"} else "当前暂无可直接支撑该特征的证据。"
        rows.append([goal_text, feature_text, strength, gap_reason, evidence_text])
    return rows


def build_lost_feature_watchlist_rows(feature_exposure_rows: list[list[object]]) -> list[list[object]]:
    rows: list[list[object]] = []
    for spec in FEATURE_SPECS:
        exposure = next((row for row in feature_exposure_rows if row[1] == spec["name_cn"]), None)
        if not exposure:
            continue
        rows.append([spec["name_cn"], exposure[4], spec["lost_reason"]])
    return rows[:8]


def fetch_voc_intelligence_rows(conn: sqlite3.Connection, spu_ids: list[str]) -> list[sqlite3.Row]:
    if not spu_ids:
        return []
    placeholders = ", ".join("?" for _ in spu_ids)
    return list(
        conn.execute(
            f"""
            SELECT
                CASE
                    WHEN tag_name LIKE '%语音%' OR tag_name LIKE '%YIKO%' THEN '人机交互'
                    WHEN tag_name LIKE '%避障%' OR tag_name LIKE '%越障%' OR tag_name LIKE '%脱困%' OR tag_name LIKE '%台阶%' OR tag_name LIKE '%门槛%' THEN '避障与脱困'
                    WHEN tag_name LIKE '%地图%' OR tag_name LIKE '%建图%' OR tag_name LIKE '%路径%' OR tag_name LIKE '%漏扫%' THEN '导航与路径规划'
                    WHEN tag_name LIKE '%智能%' OR tag_name LIKE '%托管%' OR tag_name LIKE '%AI%' THEN '主动服务/智能托管'
                    ELSE '其他智能相关'
                END AS intelligence_dimension,
                tag_name,
                MAX(COALESCE(tag_sentiment, '')) AS tag_sentiment,
                COUNT(DISTINCT message_uid) AS message_count
            FROM vw_voc_message_tag_mapped
            WHERE canonical_spu_id IN ({placeholders})
              AND (
                tag_name LIKE '%智能%' OR tag_name LIKE '%语音%' OR tag_name LIKE '%YIKO%'
                OR tag_name LIKE '%地图%' OR tag_name LIKE '%建图%' OR tag_name LIKE '%路径%'
                OR tag_name LIKE '%避障%' OR tag_name LIKE '%越障%' OR tag_name LIKE '%脱困%'
                OR tag_name LIKE '%台阶%' OR tag_name LIKE '%门槛%' OR tag_name LIKE '%托管%'
              )
            GROUP BY intelligence_dimension, tag_name
            ORDER BY intelligence_dimension, message_count DESC, tag_name
            LIMIT 16
            """,
            spu_ids,
        )
    )


def build_question_answer_lines(
    analysis_goal_text: str,
    exec_summary_lines: list[str],
    can_conclude_lines: list[str],
    feature_exposure_rows: list[list[object]],
    summary_insight_cards: dict[str, object] | None = None,
    survey_segment_comparison: dict[str, object] | None = None,
    voc_problem_packages: dict[str, object] | None = None,
    cross_source_interpretation: dict[str, object] | None = None,
) -> list[str]:
    lines = [f"本轮通查要回答的问题是：`{analysis_goal_text}`。"]
    if exec_summary_lines:
        lines.append(f"当前最核心的总结性回答是：{exec_summary_lines[0]}")
    if can_conclude_lines:
        lines.append(f"在现有证据下，已经可以稳定支持的判断包括：{can_conclude_lines[0]}")
    if summary_insight_cards and summary_insight_cards.get("top_archetypes"):
        top_archetype = summary_insight_cards["top_archetypes"][0][0]  # type: ignore[index]
        lines.append(f"从定性总结看，当前最鲜明的一类用户模式是 `{top_archetype}`。")
    if survey_segment_comparison and survey_segment_comparison.get("segments"):
        segment = survey_segment_comparison["segments"][0]  # type: ignore[index]
        lines.append(f"问卷分群里已经能看到 `{segment['segment_name']}` 这类人与其他人做出不同判断。")
    if voc_problem_packages and voc_problem_packages.get("packages"):
        package = voc_problem_packages["packages"][0]  # type: ignore[index]
        lines.append(f"VOC 里最值得继续下钻的不是单标签，而是 `{package['package_name']}` 这一类问题包。")
    if cross_source_interpretation and cross_source_interpretation.get("interpretations"):
        interpretation = cross_source_interpretation["interpretations"][0]  # type: ignore[index]
        lines.append(f"跨源最可信的一类解释是：{interpretation['best_explanation']}")
    weak_or_proxy = [row[1] for row in feature_exposure_rows if row[4] in {"直连弱证据", "代理证据", "无证据"}]
    if weak_or_proxy:
        lines.append(f"但以下特征仍会限制结论写满：`{'、'.join(weak_or_proxy[:4])}`。")
    return lines


def build_argument_tree_rows(
    goal_codes: list[str],
    feature_exposure_rows: list[list[object]],
    exec_summary_lines: list[str],
    summary_profile_line: str,
    summary_purchase_line: str,
    summary_need_line: str,
    priority_rows: list[list[object]],
    intelligence_rows: list[sqlite3.Row],
    summary_insight_cards: dict[str, object] | None = None,
    survey_segment_comparison: dict[str, object] | None = None,
    voc_problem_packages: dict[str, object] | None = None,
    cross_source_interpretation: dict[str, object] | None = None,
) -> list[list[object]]:
    strength_lookup = {row[1]: row[4] for row in feature_exposure_rows}
    rows: list[list[object]] = []
    top_archetype = (
        summary_insight_cards["top_archetypes"][0][0]  # type: ignore[index]
        if summary_insight_cards and summary_insight_cards.get("top_archetypes")
        else None
    )
    top_segment = (
        survey_segment_comparison["segments"][0]["segment_name"]  # type: ignore[index]
        if survey_segment_comparison and survey_segment_comparison.get("segments")
        else None
    )
    top_package = (
        voc_problem_packages["packages"][0]["package_name"]  # type: ignore[index]
        if voc_problem_packages and voc_problem_packages.get("packages")
        else None
    )
    top_interpretation = (
        cross_source_interpretation["interpretations"][0]["best_explanation"]  # type: ignore[index]
        if cross_source_interpretation and cross_source_interpretation.get("interpretations")
        else None
    )
    if "user_profile" in goal_codes:
        rows.append(
            [
                "用户画像与核心人群",
                (
                    f"当前至少已经浮出一类鲜明人群模式：`{top_archetype}`；{summary_profile_line}"
                    if top_archetype and summary_profile_line != "[待填]"
                    else summary_profile_line if summary_profile_line != "[待填]" else "当前用户主体可做初步刻画，但仍需更完整直连画像数据。"
                ),
                "年龄/性别/城市/职业/收入/教育；家庭结构/宠物/孩子/房屋面积/户型",
                strength_lookup.get("年龄/性别/城市/职业/收入/教育", "无证据"),
                "可",
            ]
        )
    if "usage_scenario" in goal_codes:
        scenario_text = exec_summary_lines[1] if len(exec_summary_lines) > 1 else "当前场景与工况主要集中在地面材质、重污、毛发与重点区域。"
        rows.append(
            [
                "场景与工况",
                f"{scenario_text} 当前最值得继续下钻的问题包是 `{top_package}`。" if top_package else scenario_text,
                "地面材质/空间复杂度/门槛/地毯/低矮空间；使用频次/重点区域/维护触点/家庭分工",
                strength_lookup.get("地面材质/空间复杂度/门槛/地毯/低矮空间", "无证据"),
                "可",
            ]
        )
    if "pain_need" in goal_codes:
        top_issue = priority_rows[0][0] if priority_rows else "待补充"
        rows.append(
            [
                "痛点与需求",
                (
                    f"当前最强的一类用户矛盾集中在 `{top_issue}`，背后真正伤害的是 `{top_interpretation}`。"
                    if top_issue != "待补充" and top_interpretation
                    else f"当前最强的一类用户矛盾集中在 `{top_issue}`。" if top_issue != "待补充" else summary_need_line
                ),
                "核心痛点/核心需求；信任感/负担转移/是否真正解放双手",
                strength_lookup.get("核心痛点/核心需求", "无证据"),
                "可",
            ]
        )
    if "intelligence" in goal_codes:
        top_dim = intelligence_rows[0]["intelligence_dimension"] if intelligence_rows else "待补充"
        rows.append(
            [
                "智能性判断",
                f"当前‘智能性’不能只看总词，最主要的用户感知维度是 `{top_dim}`。" if top_dim != "待补充" else "当前智能性只能做初步拆维。",
                "导航/避障/脱困/交互/主动服务；可预测性/可信度/像工具还是像管家",
                strength_lookup.get("导航/避障/脱困/交互/主动服务", "无证据"),
                "可",
            ]
        )
    if "value_proposition" in goal_codes:
        pillar = priority_rows[0][0] if priority_rows else "待补充"
        rows.append(
            [
                "价值支柱判断",
                (
                    f"当前更值得优先放大的价值支柱应围绕 `{pillar}` 展开，而且 `{top_segment}` 这类人会更明显地拉高这件事的重要性。"
                    if pillar != "待补充" and top_segment
                    else f"当前更值得优先放大的价值支柱应围绕 `{pillar}` 展开。" if pillar != "待补充" else summary_purchase_line
                ),
                "高频场景/痛点强度/需求优先级/差异化空间",
                strength_lookup.get("高频场景/痛点强度/需求优先级/差异化空间", "无证据"),
                "可",
            ]
        )
    return rows


def load_action_context() -> dict[str, object]:
    skill_names: list[str] = []
    if WORKSPACE_SKILL_INVENTORY.exists():
        try:
            payload = json.loads(WORKSPACE_SKILL_INVENTORY.read_text(encoding="utf-8"))
            skill_names = [row["skill_name"] for row in payload.get("skills", []) if isinstance(row, dict) and row.get("skill_name")]
        except Exception:  # noqa: BLE001
            skill_names = []
    memory_hints: list[str] = []
    if MEMORY_ROOT.exists():
        memory_files = sorted(MEMORY_ROOT.glob("20*.md"))[-2:]
        for path in memory_files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("- ") and any(keyword in line for keyword in ("机器人", "bundle", "直连", "前台", "质量闸门", "总报告", "portfolio_full")):
                    memory_hints.append(line[2:].strip())
    return {
        "skill_names": skill_names,
        "memory_hints": memory_hints[:6],
        "knowledge_bases": [
            "cleaning_robot_voc_feedback_log",
            "cleaning_robot_quant_survey",
            "cleaning_robot_summary_qual_interview",
            "cleaning_robot_qual_interview",
            "cleaning_robot_analysis_hub_ops_fact",
        ],
    }


def build_action_plan_rows(
    priority_rows: list[list[object]],
    conflict_rows: list[list[object]],
    support_matrix: list[dict[str, object]],
    action_context: dict[str, object],
) -> list[list[object]]:
    rows: list[list[object]] = []
    skill_text = "、".join(
        [name for name in action_context.get("skill_names", []) if name in {"OptiFlow", "Nexus", "product-ops-dashboard", "excel-xlsx"}]
    ) or "OptiFlow、Nexus、product-ops-dashboard"
    kb_text = "、".join(action_context["knowledge_bases"])  # type: ignore[index]
    if priority_rows:
        top_theme = priority_rows[0][0]
        rows.append(
            [
                f"`{top_theme}` 已经是当前最强的一类跨源结论，继续放大它最能增强报告的解释力。",
                f"围绕 `{top_theme}` 生成专题级问题闭环包，并补齐对应的用户原声与题项证据。",
                f"产品经理 + 看用户Agent（{skill_text}）",
                "本周内",
                f"`main_report` / 专题附件 / `{kb_text}`",
                f"复用当前技能链，先从现有 bundle 下钻，再把专题证据回挂到问卷、VOC、访谈三源。",
                "至少覆盖 2 个直连数据源；若只有 1 个直连源则不得写成最终定案。",
            ]
        )
    unsupported = [row["module_name_cn"] for row in support_matrix if row["support_level"] != "支持"]
    if unsupported:
        rows.append(
            [
                f"`{'、'.join(unsupported[:3])}` 仍是当前最限制结论写满的模块。",
                f"补强 `{unsupported[0]}` 对应的直连问卷/总结/原始访谈输入。",
                "用户研究团队 + 数据工程 + Nexus",
                "下一轮研究排期前",
                f"`{kb_text}`",
                "优先补直连输入，再重跑当前分析 bundle，不再依赖代理证据硬写结论。",
                "问卷建议 300+ 有效样本；定性建议 3-5 个可识别案例；原始访谈至少 3 份可追溯文档。",
            ]
        )
    if conflict_rows:
        conflict_theme = conflict_rows[0][0]
        rows.append(
            [
                f"`{conflict_theme}` 当前存在明显冲突或缺口，不先处理会让结论显得单薄。",
                f"为 `{conflict_theme}` 增加反证与缺口验证专题，区分直连结论和方向判断。",
                "看用户Agent + 用户研究 PM",
                "下一次汇报前",
                "`coverage_gap_table` / `argument_tree` / 专题证据包",
                "先明确冲突来自样本差异、代理证据还是数据口径，再决定是否继续扩大结论。",
                "至少形成一页反证说明；若冲突无法解释，则结论层级自动降级。",
            ]
        )
    rows.append(
        [
            "当前系统已经具备前台入口、质量闸门和总报告生成能力，应让行动建议更像执行方案而不是普通建议。",
            "持续维护 5W2H 行动表，并让每条行动绑定当前能力、知识库与责任主体。",
            "OptiFlow + Nexus + 相关技能",
            "每次重跑报告时",
            "报告正文最后一节",
            f"复用当前 memory 提示和 skill inventory，把 Who/How 明确绑定到真实系统能力，而不是抽象建议。最近记忆提示：{'；'.join(action_context.get('memory_hints', [])[:3]) or '当前已具备前台入口与质量闸门'}。",
            "每轮至少保留 1 条面向研究、1 条面向产品、1 条面向系统/智能体的行动。",
        ]
    )
    return rows


def build_scaffold(args: argparse.Namespace, result: dict[str, object]) -> str:
    module_map = support_lookup(result)
    selected_spus = result["selected_spus"]  # type: ignore[assignment]
    voc_rows = result["voc_rows"]  # type: ignore[assignment]
    survey_rows = result["survey_rows"]  # type: ignore[assignment]
    summary_rows = result["summary_rows"]  # type: ignore[assignment]
    raw_rows = result["raw_rows"]  # type: ignore[assignment]
    title = args.analysis_title or f"{args.category_name}多源用户分析脚手架"
    selected_spu_ids = [row["spu_id"] for row in selected_spus]
    voc_conn = connect_voc()
    period_rows = fetch_voc_period_rows(voc_conn, selected_spu_ids, args.period_id)
    theme_rows, negative_rows, scene_negative_rows = fetch_voc_theme_rows(voc_conn, selected_spu_ids)
    intelligence_rows = fetch_voc_intelligence_rows(voc_conn, selected_spu_ids)
    diff_table, period_diff_table, diff_insights = fetch_voc_diff_rows(voc_conn, selected_spus, voc_rows, period_rows)
    pool_period_compare = build_pool_period_compare(period_rows)
    product_snapshots = [fetch_voc_product_snapshot(voc_conn, spu_id) for spu_id in selected_spu_ids]
    pool_feature_overview = build_pool_feature_overview(product_snapshots)
    voc_conclusions = build_voc_conclusions(voc_rows, theme_rows, negative_rows, diff_insights)
    voc_conn.close()
    survey_conn = connect_survey()
    survey_wave_details = []
    for wave_row in survey_rows:
        sample_count = fetch_wave_sample_count(survey_conn, wave_row["wave_id"])
        capability_tables = {}
        for capability_code in SURVEY_KEYWORDS:
            capability_tables[capability_code] = fetch_survey_capability_question_summaries(
                survey_conn,
                wave_row["wave_id"],
                capability_code,
                sample_count,
            )
        survey_wave_details.append({"wave": wave_row, "sample_count": sample_count, "capability_tables": capability_tables})
    survey_segment_comparison = build_survey_segment_comparison(survey_conn, survey_rows)
    survey_conn.close()
    survey_proxy_rows = []
    if not survey_rows:
        survey_proxy_rows = fetch_proxy_survey_rows(selected_spu_ids, args.market)
        survey_conn = connect_survey()
        for wave_row in survey_proxy_rows:
            sample_count = fetch_wave_sample_count(survey_conn, wave_row["wave_id"])
            capability_tables = {}
            for capability_code in SURVEY_KEYWORDS:
                capability_tables[capability_code] = fetch_survey_capability_question_summaries(
                    survey_conn,
                    wave_row["wave_id"],
                    capability_code,
                    sample_count,
                )
            survey_wave_details.append({"wave": wave_row, "sample_count": sample_count, "capability_tables": capability_tables, "is_proxy": True})
        survey_segment_comparison = build_survey_segment_comparison(survey_conn, survey_proxy_rows)
        survey_conn.close()
    effective_survey_rows = survey_rows if survey_rows else survey_proxy_rows
    summary_conn = connect_summary()
    summary_sections = fetch_summary_theme_sections(summary_conn, selected_spu_ids, args.market)
    summary_theme_evidence = build_summary_theme_evidence(summary_sections)
    summary_insight_cards = extract_summary_insight_cards(summary_sections)
    summary_conn.close()
    summary_proxy_rows = []
    if not summary_rows:
        summary_proxy_rows = fetch_proxy_summary_rows(args.market)
        proxy_spu_ids = [row["inferred_spu_id"] for row in summary_proxy_rows if row.get("inferred_spu_id")]
        if proxy_spu_ids:
            summary_conn = connect_summary()
            summary_sections = fetch_summary_theme_sections(summary_conn, proxy_spu_ids, args.market)
            summary_theme_evidence = build_summary_theme_evidence(summary_sections)
            summary_insight_cards = extract_summary_insight_cards(summary_sections)
            summary_conn.close()
    effective_summary_rows = summary_rows if summary_rows else summary_proxy_rows
    voc_conn = connect_voc()
    voc_problem_packages = build_voc_problem_packages(voc_conn, selected_spu_ids)
    voc_conn.close()
    voc_theme_evidence = build_voc_theme_evidence(theme_rows, negative_rows)
    survey_theme_evidence = build_survey_theme_evidence(survey_wave_details)
    consistent_issues, consistent_strengths, conflict_rows, priority_rows = build_cross_source_tables(
        voc_theme_evidence, survey_theme_evidence, summary_theme_evidence
    )
    cross_source_interpretation = build_cross_source_interpretation(
        consistent_issues,
        consistent_strengths,
        conflict_rows,
        priority_rows,
        summary_insight_cards,
        survey_segment_comparison,
        voc_problem_packages,
    )
    exec_summary_lines = build_exec_summary_lines(voc_rows, survey_wave_details, priority_rows, conflict_rows)
    selected_wave_text, survey_supported_text, survey_unsupported_text = build_survey_wave_conclusions(survey_wave_details)
    summary_profile_line, summary_purchase_line, summary_need_line = build_summary_conclusion_lines(summary_sections)
    summary_module_example_lines = build_summary_module_example_lines(summary_sections)
    can_conclude_lines, cannot_conclude_lines, next_step_lines = build_closeout_lines(
        voc_rows,
        priority_rows,
        conflict_rows,
        result["support_matrix"],  # type: ignore[index]
    )
    analysis_goal_text = resolve_analysis_goal_text(args)
    force_all_goal_codes = bool(getattr(args, "force_full_goal_codes", False))
    goal_codes = [spec["code"] for spec in GOAL_SPECS] if force_all_goal_codes else infer_goal_codes(analysis_goal_text)
    support_map = support_lookup(result)
    feature_exposure_rows = build_feature_exposure_rows(
        goal_codes,
        support_map,
        has_direct_survey=bool(survey_rows),
        has_direct_summary=bool(summary_rows),
        has_direct_raw=bool(raw_rows),
        has_direct_voc=bool(voc_rows),
        has_proxy_survey=bool(survey_proxy_rows),
        has_proxy_summary=bool(summary_proxy_rows),
    )
    goal_feature_rows = build_goal_feature_map_rows(goal_codes)
    coverage_gap_rows = build_coverage_gap_rows(feature_exposure_rows)
    lost_feature_rows = build_lost_feature_watchlist_rows(feature_exposure_rows)
    question_answer_lines = build_question_answer_lines(
        analysis_goal_text,
        exec_summary_lines,
        can_conclude_lines,
        feature_exposure_rows,
        summary_insight_cards,
        survey_segment_comparison,
        voc_problem_packages,
        cross_source_interpretation,
    )
    argument_tree_rows = build_argument_tree_rows(
        goal_codes,
        feature_exposure_rows,
        exec_summary_lines,
        summary_profile_line,
        summary_purchase_line,
        summary_need_line,
        priority_rows,
        intelligence_rows,
        summary_insight_cards,
        survey_segment_comparison,
        voc_problem_packages,
        cross_source_interpretation,
    )
    action_plan_rows = build_action_plan_rows(
        priority_rows,
        conflict_rows,
        result["support_matrix"],  # type: ignore[index]
        load_action_context(),
    )

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 0. 问题回答")
    lines.append("")
    lines.append(f"- 用户所问的问题：`{analysis_goal_text}`")
    for line in question_answer_lines:
        lines.append(f"- {line}")
    lines.append("")
    lines.append("## 1. 分析对象与证据边界")
    lines.append("")
    lines.append(
        markdown_table(
            ["字段", "当前内容"],
            [
                ["分析目标", analysis_goal_text],
                ["分析对象", "、".join(row["spu_name"] for row in selected_spus) if selected_spus else "待补充"],
                ["分析周期", args.time_scope],
                ["市场范围", args.market or "ALL"],
                ["当前数据源", "VOC / 统一问卷 / 访谈总结 / 原始访谈"],
            ],
        )
    )
    lines.append("")
    lines.append("### 1.1 目标展开后的特征图")
    lines.append("")
    lines.append(
        markdown_table(
            ["分析目标", "展开后的关键特征簇"],
            goal_feature_rows if goal_feature_rows else [["待补充", "待补充"]],
        )
    )
    lines.append("")
    lines.append("### 1.2 特征暴露表")
    lines.append("")
    lines.append(
        markdown_table(
            ["对应目标", "特征簇", "支持度", "主来源", "证据强度", "当前覆盖"],
            feature_exposure_rows if feature_exposure_rows else [["待补充", "-", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("### 1.3 缺口与易遗漏特征")
    lines.append("")
    lines.append("特征覆盖缺口表：")
    lines.append("")
    lines.append(
        markdown_table(
            ["对应目标", "特征簇", "当前证据状态", "为什么会限制结论", "当前覆盖说明"],
            coverage_gap_rows if coverage_gap_rows else [["当前关键特征已基本被覆盖", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("易遗漏特征观察表：")
    lines.append("")
    lines.append(
        markdown_table(
            ["特征簇", "当前证据状态", "为什么不能漏"],
            lost_feature_rows if lost_feature_rows else [["待补充", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("## 2. 一级结论树")
    lines.append("")
    lines.append(
        markdown_table(
            ["一级结论", "当前回答", "关键支撑特征", "证据强度", "是否可继续下钻"],
            argument_tree_rows if argument_tree_rows else [["待补充", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("## 3. 递归论证")
    lines.append("")

    if should_include(module_map.get("voc_analysis")) or should_include(module_map.get("competition_diff")):
        lines.append("### 3.1 VOC 单源证据与论证")
        lines.append("")
        lines.append("一级分结论：")
        lines.append("")
        if voc_conclusions:
            for line in voc_conclusions[:3]:
                lines.append(f"- {line}")
        else:
            lines.append("- 当前 VOC 只能提供有限补充。")
        lines.append("")
        if product_snapshots:
            lines.append("#### 3.1.1 按产品独立分析")
            lines.append("")
            for idx, snapshot in enumerate(product_snapshots, start=1):
                if not snapshot:
                    continue
                summary = snapshot["summary"]  # type: ignore[index]
                themes = snapshot["themes"]  # type: ignore[index]
                negatives = snapshot["negatives"]  # type: ignore[index]
                contexts = snapshot["contexts"]  # type: ignore[index]
                lines.append(f"##### 3.1.1.{idx} `{summary['spu_name']}`")
                lines.append("")
                lines.append(
                    markdown_table(
                        ["spu_name", "message_count", "negative_count", "negative_rate", "first_posted_at", "last_posted_at"],
                        [[summary["spu_name"], summary["message_count"], summary["negative_count"], as_percent(summary["negative_count"], summary["message_count"]), summary["first_posted_at"], summary["last_posted_at"]]],
                    )
                )
                lines.append("")
                lines.append("高频主题表：")
                lines.append("")
                lines.append(
                    markdown_table(
                        ["topic_domain", "topic_group", "tag_name", "tag_sentiment", "message_count", "penetration"],
                        [
                            [row["topic_domain_name_cn"], row["topic_group_name_cn"], row["tag_name"], row["tag_sentiment"] or "", row["message_count"], row["penetration"]]
                            for row in themes
                        ] if themes else [["待补充", "-", "-", "-", "-", "-"]],
                    )
                )
                lines.append("")
                lines.append("负面标签表：")
                lines.append("")
                lines.append(
                    markdown_table(
                        ["topic_domain", "topic_group", "tag_name", "message_count", "penetration"],
                        [
                            [row["topic_domain_name_cn"], row["topic_group_name_cn"], row["tag_name"], row["message_count"], row["penetration"]]
                            for row in negatives
                        ] if negatives else [["待补充", "-", "-", "-", "-"]],
                    )
                )
                lines.append("")
                lines.append("上下文标签表：")
                lines.append("")
                lines.append(
                    markdown_table(
                        ["context_bucket", "topic_group", "tag_name", "tag_sentiment", "message_count"],
                        [
                            [row["context_bucket_name_cn"], row["topic_group_name_cn"], row["tag_name"], row["tag_sentiment"] or "", row["message_count"]]
                            for row in contexts
                        ] if contexts else [["待补充", "-", "-", "-", "-"]],
                    )
                )
                lines.append("")
                lines.append("结论：")
                lines.append("")
                for conclusion in build_voc_product_conclusions(snapshot):
                    lines.append(f"- {conclusion}")
                lines.append("")
        if should_include(module_map.get("competition_diff")):
            lines.append("#### 3.1.2 跨品差异分析")
            lines.append("")
            if pool_feature_overview:
                lines.append("表 1：按产品 VOC 特征概览")
                lines.append("")
                lines.append(
                    markdown_table(
                        ["spu_name", "top_feature", "top_risk", "top_context"],
                        pool_feature_overview,
                    )
                )
                lines.append("")
            if len(selected_spus) == 2 and period_diff_table:
                lines.append("表 2：同周期情感差异表")
                lines.append("")
                lines.append(
                    markdown_table(
                        ["period_name", "base_spu", "base_message_count", "base_negative_rate", "compare_spu", "compare_message_count", "compare_negative_rate", "delta_pp"],
                        period_diff_table,
                    )
                )
                lines.append("")
            elif len(selected_spus) > 2 and pool_period_compare:
                lines.append("表 2：同周期对象横向表")
                lines.append("")
                lines.append(
                    markdown_table(
                        ["period_name", "spu_name", "message_count", "negative_rate"],
                        pool_period_compare,
                    )
                )
                lines.append("")
            if len(selected_spus) == 2 and diff_table:
                lines.append("表 3：上下文标签差异表")
                lines.append("")
                lines.append(
                    markdown_table(
                        ["context_bucket", "topic_group", "tag_name", "base_rate", "compare_rate", "delta_pp"],
                        diff_table,
                    )
                )
                lines.append("")
            if len(selected_spus) == 2:
                lines.append("- 前后代差异表：当前脚手架未自动填充，需要显式指定上一代对象后补齐。")
                lines.append("- 同价格带差异表：当前脚手架未自动填充，需要补充同价格带对象集后补齐。")
            else:
                lines.append("- 成对标签差异表：当前为整池扫描，建议后续按关键 pair 再下钻。")
                lines.append("- 前后代差异表：当前脚手架未自动填充，需要显式指定代际 pair 后补齐。")
            lines.append("")
            lines.append("结论：")
            lines.append("")
            if diff_insights:
                for insight in diff_insights:
                    lines.append(f"- {insight}")
            elif len(selected_spus) > 2 and voc_rows:
                ranked = sorted(
                    voc_rows,
                    key=lambda row: (row["negative_count"] / row["message_count"]) if row["message_count"] else 0,
                    reverse=True,
                )
                top_risk = ranked[0]
                lines.append(f"- 当前整池负向率最高的对象是 `{top_risk['spu_name']}`，约 `{as_percent(top_risk['negative_count'], top_risk['message_count'])}`。")
                if len(ranked) > 1:
                    second = ranked[1]
                    lines.append(f"- 第二高风险对象是 `{second['spu_name']}`，约 `{as_percent(second['negative_count'], second['message_count'])}`。")
            else:
                lines.append("- 当前差异表尚不足以给出稳定竞品差异结论。")
            lines.append("")

    survey_modules = [
        "user_profile",
        "home_environment",
        "pre_purchase_substitute",
        "purchase_motivation",
        "purchase_journey",
        "usage_journey",
        "concept_validation",
        "price_willingness",
    ]
    if any(should_include(module_map.get(code)) for code in survey_modules) or survey_proxy_rows:
        lines.append("### 3.2 调研问卷证据与论证")
        lines.append("")
        lines.append("一级分结论：")
        lines.append("")
        lines.append(f"- 本次优先使用的问卷波次：`{selected_wave_text}`。")
        lines.append(f"- 问卷当前可稳定回答的问题：`{survey_supported_text}`。")
        lines.append(f"- 问卷当前不能稳定回答的问题：`{survey_unsupported_text}`。")
        lines.append("")
        lines.append("#### 3.2.1 问卷波次选择")
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
                    for row in effective_survey_rows[:16]
                ] if effective_survey_rows else [["待补充", "-", "-", "-", "-", "-", "-", "-", "-"]],
            )
        )
        lines.append("")
        lines.append("结论：")
        lines.append("")
        lines.append(f"- 本次优先使用的问卷波次：`{selected_wave_text}`。")
        lines.append(f"- 问卷当前可稳定回答的问题：`{survey_supported_text}`。")
        lines.append(f"- 问卷当前不能稳定回答的问题：`{survey_unsupported_text}`。")
        if survey_proxy_rows:
            lines.append("- 当前无直连问卷，以上为代理波次，应用于方向判断而非最终结论。")
        lines.append("")
        if survey_wave_details:
            lines.append("#### 3.2.2 按波次/产品独立分析")
            lines.append("")
            for idx, detail in enumerate(survey_wave_details, start=1):
                wave = detail["wave"]
                sample_count = detail["sample_count"]
                capability_tables = detail["capability_tables"]
                lines.append(f"##### 3.2.2.{idx} `{wave['wave_name']}`")
                lines.append("")
                if detail.get("is_proxy"):
                    lines.append(f"- 代理说明：`{wave.get('proxy_reason', '代理波次')}`")
                    lines.append("")
                lines.append(
                    markdown_table(
                        ["wave_name", "market_scope", "inferred_spu_id", "survey_topic", "sample_count"],
                        [[wave["wave_name"], wave["market_scope"], wave["inferred_spu_id"] or "", wave["survey_topic"] or "", sample_count]],
                    )
                )
                lines.append("")
                capability_sections = [
                    ("user_profile", "用户画像关键统计"),
                    ("home_environment", "房屋与环境关键统计"),
                    ("pre_purchase_substitute", "购前替代方式关键统计"),
                    ("purchase_motivation", "购买动机关键统计"),
                    ("purchase_journey", "购买旅程关键统计"),
                    ("usage_journey", "使用旅程关键统计"),
                    ("concept_validation", "概念验证关键统计"),
                    ("price_willingness", "价格与付费意愿关键统计"),
                ]
                for capability_code, title_cn in capability_sections:
                    if wave.get(f"{capability_code}_support") == "不支持":
                        continue
                    table_rows = capability_tables.get(capability_code, [])
                    lines.append(f"{title_cn}：")
                    lines.append("")
                    lines.append(
                        markdown_table(
                            ["question_text", "top_answer", "count", "share"],
                            table_rows if table_rows else [["待补充", "-", "-", "-"]],
                        )
                    )
                    lines.append("")
                lines.append("结论：")
                lines.append("")
                conclusions = []
                for capability_code in ("user_profile", "purchase_motivation", "usage_journey", "concept_validation"):
                    table_rows = capability_tables.get(capability_code, [])
                    if table_rows:
                        q, answer, count, share = table_rows[0]
                        conclusions.append(f"`{q}` 的高频回答是 `{answer}`（{share}）。")
                if conclusions:
                    for conclusion in conclusions[:4]:
                        lines.append(f"- {conclusion}")
                else:
                    lines.append("- 当前该波次多为开放题或自由文本，需要进一步清洗后再自动汇总。")
                lines.append("")

    if summary_rows or summary_proxy_rows:
        lines.append("### 3.3 定性访谈证据与论证")
        lines.append("")
        lines.append("一级分结论：")
        lines.append("")
        lines.append(f"- 典型人设画像：{summary_profile_line}")
        lines.append(f"- 决策心理链路：{summary_purchase_line}")
        lines.append(f"- 隐性需求：{summary_need_line}")
        lines.append("")
        lines.append("#### 3.3.1 案例覆盖")
        lines.append("")
        lines.append(
            markdown_table(
                ["study_name", "batch_market_scope", "inferred_spu_id", "case_count", "has_user_profile", "has_purchase_journey", "has_concept_validation"],
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
                    for row in effective_summary_rows[:16]
                ],
            )
        )
        lines.append("")
        if summary_proxy_rows and not summary_rows:
            lines.append("- 当前无直连定性总结，以上为同市场最新案例代理。")
            lines.append("")
        lines.append("#### 3.3.2 深描模块")
        lines.append("")
        lines.append(f"- 典型人设案例：{summary_module_example_lines['profile']}")
        lines.append(f"- 家居环境与清洁行为案例：{summary_module_example_lines['home']}")
        lines.append(f"- 购买动机 / 购买旅程案例：{summary_module_example_lines['purchase']}")
        lines.append(f"- 产品使用反馈案例：{summary_module_example_lines['usage']}")
        lines.append(f"- 用户诉求 / 未被言明需求案例：{summary_module_example_lines['needs']}")
        lines.append(f"- 概念与利益点验证案例：{summary_module_example_lines['concept']}")
        lines.append("")
        lines.append("结论：")
        lines.append("")
        lines.append(f"- 典型人设画像：{summary_profile_line}")
        lines.append(f"- 决策心理链路：{summary_purchase_line}")
        lines.append(f"- 隐性需求：{summary_need_line}")
        lines.append("")
        if summary_insight_cards.get("cards"):
            lines.append("#### 3.3.3 人物模式与购买逻辑提炼")
            lines.append("")
            lines.append(
                markdown_table(
                    ["case_title", "persona_archetype", "home_life_pattern", "cleaning_attitude", "hidden_need", "difference_reason"],
                    [
                        [
                            card["case_title"],
                            "、".join(card["persona_archetype"]) or "-",
                            "、".join(card["home_life_pattern"]) or "-",
                            "、".join(card["cleaning_attitude"]) or "-",
                            "、".join(card["hidden_need"]) or "-",
                            card["difference_reason"],
                        ]
                        for card in summary_insight_cards["cards"][:8]  # type: ignore[index]
                    ],
                )
            )
            lines.append("")
            if summary_insight_cards.get("top_archetypes"):
                lines.append("结论：")
                lines.append("")
                top_archetype = summary_insight_cards["top_archetypes"][0][0]  # type: ignore[index]
                lines.append(f"- 当前最鲜明的一类人物模式是 `{top_archetype}`。")
                if summary_insight_cards.get("top_hidden_needs"):
                    top_hidden = summary_insight_cards["top_hidden_needs"][0][0]  # type: ignore[index]
                    lines.append(f"- 当前反复出现的一类隐性需求是 `{top_hidden}`。")
                lines.append("")

    if "intelligence" in goal_codes:
        lines.append("### 3.4 智能性拆维论证")
        lines.append("")
        lines.append("一级分结论：")
        lines.append("")
        if intelligence_rows:
            top_dim = intelligence_rows[0]["intelligence_dimension"]
            lines.append(f"- 当前‘智能性’不能只看一个总词，最突出的问题维度是 `{top_dim}`。")
        else:
            lines.append("- 当前智能性相关证据仍偏弱，需要结合更多直连题项和专题案例。")
        lines.append("")
        lines.append(
            markdown_table(
                ["智能维度", "tag_name", "tag_sentiment", "message_count"],
                [
                    [row["intelligence_dimension"], row["tag_name"], row["tag_sentiment"] or "", row["message_count"]]
                    for row in intelligence_rows
                ] if intelligence_rows else [["待补充", "-", "-", "-"]],
            )
        )
        lines.append("")
        lines.append("子结论：")
        lines.append("")
        if intelligence_rows:
            dim_seen: list[str] = []
            for row in intelligence_rows:
                if row["intelligence_dimension"] in dim_seen:
                    continue
                dim_seen.append(row["intelligence_dimension"])
                lines.append(f"- `{row['intelligence_dimension']}` 是当前智能性判断里必须单独看的维度。")
                if len(dim_seen) >= 4:
                    break
        else:
            lines.append("- 当前只能从少量标签和体验反馈中推断智能性，不宜写成满结论。")
        lines.append("")

    lines.append("### 3.5 跨源综合证据与论证")
    lines.append("")
    lines.append("一级分结论：")
    lines.append("")
    if priority_rows:
        p1s = [row[0] for row in priority_rows if row[5] == "P1"]
        if p1s:
            lines.append(f"- 当前最强的一类一级结论集中在 `{', '.join(p1s[:3])}`。")
    if conflict_rows:
        lines.append(f"- 当前仍需补数验证的问题包括 `{', '.join(row[0] for row in conflict_rows[:3])}`。")
    if survey_proxy_rows or summary_proxy_rows:
        lines.append("- 当前跨源综合含代理证据，适合做方向判断，不宜直接做最终商业定案。")
    lines.append("")
    lines.append("跨源一致问题表：")
    lines.append("")
    lines.append(
        markdown_table(
            ["theme", "voc_evidence", "survey_evidence", "summary_evidence", "judgment"],
            consistent_issues if consistent_issues else [["待补充", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("跨源一致优势表：")
    lines.append("")
    lines.append(
        markdown_table(
            ["theme", "voc_evidence", "survey_evidence", "summary_evidence", "judgment"],
            consistent_strengths if consistent_strengths else [["待补充", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("冲突/缺口信号表：")
    lines.append("")
    lines.append(
        markdown_table(
            ["theme", "voc_signal", "survey_signal", "summary_signal", "judgment"],
            conflict_rows if conflict_rows else [["待补充", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("优先级矩阵：")
    lines.append("")
    lines.append(
        markdown_table(
            ["theme", "source_count", "voc_negative_count", "survey_hit_count", "summary_hit_count", "priority"],
            priority_rows if priority_rows else [["待补充", "-", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    if survey_segment_comparison.get("segments"):
        lines.append("#### 3.5.1 问卷分群差异与为什么不一样")
        lines.append("")
        lines.append(
            markdown_table(
                ["wave_name", "segment_name", "sample_count", "top_problem", "top_motivation", "difference_hint"],
                [
                    [
                        row["wave_name"],
                        row["segment_name"],
                        row["sample_count"],
                        row["top_problems"][0]["tag_name"] if row["top_problems"] else "-",
                        row["top_motivations"][0]["answer_text"] if row["top_motivations"] else "-",
                        row["difference_lines"][0] if row["difference_lines"] else "-",
                    ]
                    for row in survey_segment_comparison["segments"][:10]  # type: ignore[index]
                ],
            )
        )
        lines.append("")
    if voc_problem_packages.get("packages"):
        lines.append("#### 3.5.2 VOC 场景问题包")
        lines.append("")
        lines.append(
            markdown_table(
                ["spu_id", "package_name", "trigger_scene", "working_condition", "related_items", "damage_type", "trust_impact", "message_count"],
                [
                    [
                        row["spu_id"],
                        row["package_name"],
                        row["trigger_scene"],
                        row["working_condition"],
                        row["related_items"],
                        row["damage_type"],
                        row["trust_impact"],
                        row["message_count"],
                    ]
                    for row in voc_problem_packages["packages"][:12]  # type: ignore[index]
                ],
            )
        )
        lines.append("")
    if cross_source_interpretation.get("interpretations"):
        lines.append("#### 3.5.3 当前最可信解释")
        lines.append("")
        lines.append(
            markdown_table(
                ["theme_name", "alignment_type", "best_explanation", "confidence", "next_validation_step", "priority_hint"],
                [
                    [
                        row["theme_name"],
                        row["alignment_type"],
                        row["best_explanation"],
                        row["confidence"],
                        row["next_validation_step"],
                        row["priority_hint"],
                    ]
                    for row in cross_source_interpretation["interpretations"][:10]  # type: ignore[index]
                ],
            )
        )
        lines.append("")
    lines.append("结论：")
    lines.append("")
    if priority_rows:
        p1s = [row[0] for row in priority_rows if row[5] == "P1"]
        p2s = [row[0] for row in priority_rows if row[5] == "P2"]
        if p1s:
            lines.append(f"- 一级优先事项：`{', '.join(p1s)}`。")
        if p2s:
            lines.append(f"- 二级优化事项：`{', '.join(p2s[:3])}`。")
    else:
        lines.append("- 一级优先事项：[待填]")
        lines.append("- 二级优化事项：[待填]")
    if conflict_rows:
        lines.append(f"- 需要补数据的问题：`{', '.join(row[0] for row in conflict_rows[:3])}`。")
    else:
        lines.append("- 需要补数据的问题：[待填]")
    if survey_proxy_rows or summary_proxy_rows:
        lines.append("- 当前跨源综合含代理证据，适合做方向判断，不宜直接做最终商业定案。")
    lines.append("")

    lines.append("## 4. 反证 / 缺口 / 风险")
    lines.append("")
    lines.append("### 4.1 现在不能下满结论的地方")
    lines.append("")
    if cannot_conclude_lines:
        for line in cannot_conclude_lines:
            lines.append(f"- {line}")
    else:
        lines.append("- 当前主要结论已有一定支撑，但仍需持续补数验证。")
    lines.append("")
    lines.append("### 4.2 冲突与风险表")
    lines.append("")
    lines.append(
        markdown_table(
            ["theme", "voc_signal", "survey_signal", "summary_signal", "judgment"],
            conflict_rows if conflict_rows else [["当前未发现明显冲突", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("## 5. 下一步行动（5W2H）")
    lines.append("")
    lines.append(
        markdown_table(
            ["Why", "What", "Who", "When", "Where", "How", "How much / 预期投入或样本门槛"],
            action_plan_rows if action_plan_rows else [["待补充", "-", "-", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("## 6. 数据能力声明与附录")
    lines.append("")
    lines.append("### 6.1 数据能力声明")
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
                for row in result["support_matrix"]  # type: ignore[index]
            ],
        )
    )
    lines.append("")
    lines.append("### 6.2 VOC 样本说明")
    lines.append("")
    lines.append(
        markdown_table(
            ["spu_name", "message_count", "negative_count", "negative_rate", "first_posted_at", "last_posted_at"],
            [
                [
                    row["spu_name"],
                    row["message_count"],
                    row["negative_count"],
                    as_percent(row["negative_count"], row["message_count"]),
                    row["first_posted_at"],
                    row["last_posted_at"],
                ]
                for row in voc_rows[:12]
            ] if voc_rows else [["待补充", "-", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    if period_rows:
        lines.append(
            markdown_table(
                ["period_name", "spu_name", "message_count", "negative_rate"],
                pool_period_compare if pool_period_compare else [["待补充", "-", "-", "-"]],
            )
        )
        lines.append("")

    if raw_rows:
        lines.append("### 6.3 原始证据追溯")
        lines.append("")
        lines.append(
            markdown_table(
                ["inferred_spu_id", "market_scope", "case_count", "pending_decoder_cases", "decoded_cases"],
                [
                    [
                        row["inferred_spu_id"] or "",
                        row["market_scope"] or "",
                        row["case_count"],
                        row["pending_decoder_cases"],
                        row["decoded_cases"],
                    ]
                    for row in raw_rows[:12]
                ],
            )
        )
        lines.append("")
        lines.append("- 当前原始访谈可追溯但大多未解码，主要用于证据索引：[待填]")
        lines.append("")
    lines.append("### 6.4 现在可以下结论的事")
    lines.append("")
    if can_conclude_lines:
        for line in can_conclude_lines:
            lines.append(f"- {line}")
    else:
        lines.append("- [待填]")
    lines.append("")
    return "\n".join(lines)


def strip_title_block(markdown: str) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def demote_headings(markdown: str, levels: int = 1) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("#"):
            prefix = len(line) - len(line.lstrip("#"))
            lines.append("#" * min(prefix + levels, 6) + line[prefix:])
        else:
            lines.append(line)
    return "\n".join(lines)


def split_scaffold_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "__preamble__"
    sections[current] = []
    for line in markdown.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            current = line.lstrip("#").strip()
            sections.setdefault(current, []).append(line)
        else:
            sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items() if "\n".join(value).strip()}


def main() -> None:
    args = parse_args()
    preflight_args = SimpleNamespace(
        category_name=args.category_name,
        spu=args.spu,
        cohort_id=args.cohort_id,
        market=args.market,
        survey_topic=args.survey_topic,
        module=args.module,
        require_voc=args.require_voc,
        format="json",
    )
    result = collect_preflight_result(preflight_args)
    scaffold = build_scaffold(args, result)
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(scaffold, encoding="utf-8")
        print(f"written={out_path}")
    else:
        print(scaffold)


if __name__ == "__main__":
    main()
