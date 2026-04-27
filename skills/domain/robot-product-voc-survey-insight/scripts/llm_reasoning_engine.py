#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from derive_higher_order_insights import infer_series_code


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_token(value: Any) -> str:
    text = normalize_text(value).lower()
    for old in [
        " ",
        "\u3000",
        "-",
        "_",
        "/",
        "（",
        "）",
        "(",
        ")",
        "【",
        "】",
        ":",
        "：",
        ".",
        ",",
        "?",
        "？",
        "、",
        ";",
        "；",
        "\n",
        "\t",
    ]:
        text = text.replace(old, "")
    return text


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def dedupe_normalized_texts(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = normalize_text(value)
        normalized = normalize_token(text)
        if not text or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(text)
    return ordered


def expand_match_terms(values: list[str]) -> list[str]:
    expanded: list[str] = []
    for value in values:
        text = normalize_text(value)
        normalized = normalize_token(text)
        if not normalized:
            continue
        expanded.append(text)
        if len(normalized) >= 4:
            expanded.extend([normalized[:2], normalized[-2:]])
        if len(normalized) >= 6:
            expanded.extend([normalized[2:4], normalized[4:6]])
    return dedupe_normalized_texts(expanded)


def slugify(text: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in normalize_text(text))
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "item"


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def packet_scope_boundaries(series_family: str, user_band: str, market_scope: str) -> list[str]:
    boundaries: list[str] = []
    if series_family == "N" and user_band == "N_aes":
        boundaries.append("当前稳定自家信号主要来自海外/ALL，中国区仍缺自家稳定样本。")
    if series_family == "N" and user_band == "N_omni":
        boundaries.append("当前仍缺稳定自家 VOC 用户样本，只能保留边界与补数方向。")
    if market_scope == "海外":
        boundaries.append("该包当前优先反映海外样本，不应直接偷渡成中国区判断。")
    if not boundaries:
        boundaries.append("当前结论仍需和统计门槛、市场优先级一起使用，不应脱离事实层单独上台。")
    return boundaries


def load_llm_profiles(path: str | Path) -> dict[str, Any]:
    profile_path = Path(path).expanduser().resolve()
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), dict):
        raise ValueError(f"invalid llm profile file: {profile_path}")
    return payload


def resolve_llm_profile(path: str | Path, profile_key: str) -> dict[str, Any]:
    payload = load_llm_profiles(path)
    profile = payload["profiles"].get(profile_key)
    if not isinstance(profile, dict):
        raise KeyError(f"missing llm profile: {profile_key}")
    required = ["provider", "model", "temperature", "max_tokens", "system_prompt_id", "timeout_sec"]
    missing = [key for key in required if key not in profile]
    if missing:
        raise ValueError(f"profile `{profile_key}` missing fields: {', '.join(missing)}")
    return dict(profile)


def build_llm_prompt_envelope(
    *,
    packet: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": normalize_text(profile.get("provider")),
        "model": normalize_text(profile.get("model")),
        "system_prompt_id": normalize_text(profile.get("system_prompt_id")),
        "temperature": profile.get("temperature"),
        "max_tokens": profile.get("max_tokens"),
        "timeout_sec": profile.get("timeout_sec"),
        "base_url": normalize_text(profile.get("base_url")),
        "api_key_env": normalize_text(profile.get("api_key_env")),
        "response_format": profile.get("response_format"),
        "packet_id": normalize_text(packet.get("packet_id")),
        "reasoning_task_type": normalize_text(packet.get("reasoning_task_type")),
        "packet": packet,
    }


def extract_case_series_map(semantic_passages: dict[str, Any]) -> dict[str, str]:
    case_series: dict[str, str] = {}
    for case_payload in semantic_passages.get("cases", []) or []:
        top_passages = case_payload.get("top_passages", []) or []
        if top_passages:
            case_series[str(case_payload.get("case_title", ""))] = str(top_passages[0].get("series_code", "")) or "unknown"
    for passage in semantic_passages.get("passages", []) or []:
        case_title = str(passage.get("case_title", ""))
        if case_title and case_title not in case_series:
            case_series[case_title] = str(passage.get("series_code", "")) or "unknown"
    return case_series


def build_topic_term_lookup(problem_drilldown_packages: dict[str, Any]) -> dict[tuple[str, str], list[str]]:
    lookup: dict[tuple[str, str], list[str]] = {}
    for row in problem_drilldown_packages.get("rows", []) or []:
        topic_name = str(row.get("problem_name", ""))
        series_family = str(row.get("series_family", ""))
        if not topic_name or not series_family:
            continue
        terms = [topic_name]
        for key in ["type_breakdown", "scene_breakdown", "working_condition_breakdown", "effect_expectation_breakdown"]:
            for item in (row.get(key, []) or [])[:6]:
                label = normalize_text(item.get("label", ""))
                if label:
                    terms.append(label)
        lookup[(series_family, topic_name)] = dedupe_normalized_texts(terms)
    return lookup


def match_passages_for_topic(
    semantic_passages: dict[str, Any],
    *,
    series_family: str,
    topic_terms: list[str],
    limit: int = 6,
) -> tuple[list[str], list[dict[str, Any]]]:
    case_titles: list[str] = []
    passages: list[dict[str, Any]] = []
    normalized_terms = [normalize_token(term) for term in expand_match_terms(topic_terms) if normalize_token(term)]
    for passage in semantic_passages.get("passages", []) or []:
        if str(passage.get("series_code", "")) != series_family:
            continue
        blob = normalize_token(
            " ".join(
                [
                    str(passage.get("passage_text", "")),
                    *[str(tag) for tag in passage.get("passage_tags", []) or []],
                ]
            )
        )
        if not blob:
            continue
        if any(term in blob for term in normalized_terms):
            case_title = str(passage.get("case_title", ""))
            if case_title:
                case_titles.append(case_title)
            passages.append(
                {
                    "passage_id": str(passage.get("passage_id", "")),
                    "case_title": case_title,
                    "passage_role": str(passage.get("passage_role", "")),
                    "passage_text": str(passage.get("passage_text", "")),
                    "quality_score": passage.get("quality_score", 0.0),
                }
            )
    passages = sorted(
        passages,
        key=lambda item: (-safe_float(item.get("quality_score", 0.0)), item.get("case_title", ""), item.get("passage_id", "")),
    )[:limit]
    return dedupe_normalized_texts(case_titles), passages


def match_open_answers_for_topic(
    survey_open_answer_rows: list[dict[str, Any]],
    *,
    series_family: str,
    topic_terms: list[str],
    limit: int = 6,
) -> list[dict[str, Any]]:
    normalized_terms = [normalize_token(term) for term in expand_match_terms(topic_terms) if normalize_token(term)]
    matched: list[dict[str, Any]] = []
    for row in survey_open_answer_rows:
        if str(row.get("series_family", "")) != series_family:
            continue
        answer_text = str(row.get("answer_text", ""))
        blob = normalize_token(answer_text)
        if not blob:
            continue
        if any(term in blob for term in normalized_terms):
            matched.append(
                {
                    "wave_id": str(row.get("wave_id", "")),
                    "wave_name": str(row.get("wave_name", "")),
                    "question_id": str(row.get("question_id", "")),
                    "question_text": str(row.get("question_text", "")),
                    "response_identity_id": str(row.get("response_identity_id", "")),
                    "answer_text": answer_text,
                    "market_scope": str(row.get("market_scope", "")),
                    "survey_topic": str(row.get("survey_topic", "")),
                }
            )
    matched.sort(
        key=lambda item: (-len(normalize_token(item.get("answer_text", ""))), item.get("wave_name", ""), item.get("question_id", ""))
    )
    return matched[:limit]


def build_survey_signal_rows(
    survey_segment_comparison: dict[str, Any],
    survey_concept_segments: dict[str, Any],
    *,
    series_family: str,
    topic_terms: list[str],
    limit: int = 4,
) -> list[dict[str, Any]]:
    normalized_terms = [normalize_token(term) for term in expand_match_terms(topic_terms) if normalize_token(term)]
    rows: list[dict[str, Any]] = []
    for source_row in (survey_segment_comparison.get("segments", []) or []) + (survey_concept_segments.get("segments", []) or []):
        inferred_series = infer_series_code(source_row.get("inferred_spu_id"), source_row.get("wave_name", ""))
        if inferred_series != series_family:
            continue
        blob = normalize_token(
            " ".join(
                [str(source_row.get("segment_name", "")), str(source_row.get("segment_summary", ""))]
                + [str(item) for item in (source_row.get("top_problems", []) or [])]
                + [str(item) for item in (source_row.get("difference_reason", []) or [])]
                + [str(item) for item in (source_row.get("top_motivations", []) or [])]
            )
        )
        if normalized_terms and not any(term in blob for term in normalized_terms):
            continue
        rows.append(
            {
                "segment_name": str(source_row.get("segment_name", "")),
                "wave_name": str(source_row.get("wave_name", "")),
                "top_problems": [str(item) for item in (source_row.get("top_problems", []) or [])[:3]],
                "difference_reason": [str(item) for item in (source_row.get("difference_reason", []) or [])[:2]],
                "top_motivations": [str(item) for item in (source_row.get("top_motivations", []) or [])[:2]],
            }
        )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["wave_name"], row["segment_name"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped[:limit]


def build_qual_evidence_packet(
    *,
    semantic_passages: dict[str, Any],
    topic_attention_matrix: dict[str, Any],
    problem_drilldown_packages: dict[str, Any],
    survey_segment_comparison: dict[str, Any],
    survey_concept_segments: dict[str, Any],
    survey_open_answer_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    packets: list[dict[str, Any]] = []
    case_series_map = extract_case_series_map(semantic_passages)
    topic_terms_lookup = build_topic_term_lookup(problem_drilldown_packages)
    topic_summary_rows = topic_attention_matrix.get("topic_summary_rows", []) or []

    for case_payload in semantic_passages.get("cases", []) or []:
        case_title = str(case_payload.get("case_title", ""))
        if not case_title:
            continue
        series_family = case_series_map.get(case_title, "unknown")
        top_passages = case_payload.get("top_passages", []) or []
        packets.append(
            {
                "packet_id": f"case::{slugify(case_title)}",
                "series_family": series_family,
                "user_band": series_family,
                "topic_name": "-",
                "market_scope": "ALL",
                "question_scope": "单案例深描",
                "supporting_cases": [case_title],
                "disconfirming_cases": [],
                "supporting_passages": [
                    {
                        "passage_id": str(item.get("passage_id", "")),
                        "passage_role": str(item.get("passage_role", "")),
                        "passage_text": str(item.get("passage_text", "")),
                    }
                    for item in top_passages[:6]
                ],
                "supporting_open_answers": [],
                "linked_voc_signals": [],
                "linked_survey_signals": [],
                "linked_drilldown_rows": [],
                "scope_boundaries": ["当前是单案例深描，不代表整条系列的稳定主命题。"],
                "reasoning_task_type": "case_explain",
            }
        )

    topic_rows = [
        row
        for row in topic_summary_rows
        if str(row.get("cohort_scope", "")) == "科沃斯样本" and str(row.get("series_family", "")) in {"X", "T", "N"}
    ]
    for row in topic_rows:
        series_family = str(row.get("series_family", ""))
        user_band = str(row.get("user_band", series_family))
        topic_name = str(row.get("topic_name", ""))
        market_scope = str(row.get("market_scope", "ALL"))
        terms = topic_terms_lookup.get((series_family, topic_name), [topic_name])
        supporting_cases, supporting_passages = match_passages_for_topic(
            semantic_passages,
            series_family=series_family,
            topic_terms=terms,
            limit=6,
        )
        disconfirming_cases = [
            case_title
            for case_title, case_series in case_series_map.items()
            if case_series == series_family and case_title not in supporting_cases
        ][:3]
        supporting_open_answers = match_open_answers_for_topic(
            survey_open_answer_rows,
            series_family=series_family,
            topic_terms=terms,
            limit=6,
        )
        linked_survey_signals = build_survey_signal_rows(
            survey_segment_comparison,
            survey_concept_segments,
            series_family=series_family,
            topic_terms=terms,
            limit=4,
        )
        linked_voc_signals = [
            {
                "topic_name": topic_name,
                "mention_count": safe_int(row.get("mention_count", 0)),
                "positive_count": safe_int(row.get("positive_count", 0)),
                "negative_count": safe_int(row.get("negative_count", 0)),
                "market_scope": market_scope,
                "user_band": user_band,
            }
        ]
        linked_drilldown_rows = [
            {
                "problem_name": str(item.get("problem_name", "")),
                "market_scope": str(item.get("market_scope", "")),
                "negative_profile_summary": str(item.get("negative_profile_summary", "")),
                "next_drilldown_axis": str(item.get("next_drilldown_axis", "")),
            }
            for item in (problem_drilldown_packages.get("rows", []) or [])
            if str(item.get("series_family", "")) == series_family
            and str(item.get("user_band", series_family)) == user_band
            and str(item.get("problem_name", "")) == topic_name
        ][:3]
        packets.append(
            {
                "packet_id": f"theme::{series_family}::{user_band}::{slugify(topic_name)}::{slugify(market_scope)}",
                "series_family": series_family,
                "user_band": user_band,
                "topic_name": topic_name,
                "market_scope": market_scope,
                "question_scope": "主题解释",
                "supporting_cases": supporting_cases[:6],
                "disconfirming_cases": disconfirming_cases,
                "supporting_passages": supporting_passages,
                "supporting_open_answers": supporting_open_answers,
                "linked_voc_signals": linked_voc_signals,
                "linked_survey_signals": linked_survey_signals,
                "linked_drilldown_rows": linked_drilldown_rows,
                "scope_boundaries": packet_scope_boundaries(series_family, user_band, market_scope),
                "reasoning_task_type": "theme_explain",
            }
        )

    claim_specs = [
        ("X", "X", "系列主命题"),
        ("T", "T", "系列主命题"),
        ("N", "N_single", "带宽主命题"),
        ("N", "N_aes", "带宽主命题"),
        ("N", "N_omni", "带宽主命题"),
    ]
    for series_family, user_band, question_scope in claim_specs:
        matching_rows = [
            row
            for row in topic_rows
            if str(row.get("series_family", "")) == series_family and str(row.get("user_band", series_family)) == user_band
        ]
        matching_rows.sort(key=lambda item: (-safe_int(item.get("negative_count", 0)), -safe_int(item.get("mention_count", 0))))
        top_topics = [str(row.get("topic_name", "")) for row in matching_rows[:3] if str(row.get("topic_name", "")).strip()]
        packets.append(
            {
                "packet_id": f"claim::{series_family}::{user_band}",
                "series_family": series_family,
                "user_band": user_band,
                "topic_name": "；".join(top_topics) if top_topics else "-",
                "market_scope": "ALL",
                "question_scope": question_scope,
                "supporting_cases": dedupe_normalized_texts(
                    [
                        case_title
                        for row in matching_rows[:2]
                        for case_title in next(
                            (
                                packet.get("supporting_cases", [])
                                for packet in packets
                                if packet.get("reasoning_task_type") == "theme_explain"
                                and packet.get("series_family") == series_family
                                and packet.get("user_band") == user_band
                                and packet.get("topic_name") == row.get("topic_name")
                            ),
                            [],
                        )
                    ]
                )[:6],
                "disconfirming_cases": [],
                "supporting_passages": [],
                "supporting_open_answers": [],
                "linked_voc_signals": [
                    {
                        "topic_name": str(row.get("topic_name", "")),
                        "mention_count": safe_int(row.get("mention_count", 0)),
                        "positive_count": safe_int(row.get("positive_count", 0)),
                        "negative_count": safe_int(row.get("negative_count", 0)),
                        "market_scope": str(row.get("market_scope", "")),
                    }
                    for row in matching_rows[:3]
                ],
                "linked_survey_signals": build_survey_signal_rows(
                    survey_segment_comparison,
                    survey_concept_segments,
                    series_family=series_family,
                    topic_terms=top_topics,
                    limit=4,
                ),
                "linked_drilldown_rows": [
                    {
                        "problem_name": str(item.get("problem_name", "")),
                        "market_scope": str(item.get("market_scope", "")),
                        "negative_profile_summary": str(item.get("negative_profile_summary", "")),
                        "next_drilldown_axis": str(item.get("next_drilldown_axis", "")),
                    }
                    for item in (problem_drilldown_packages.get("rows", []) or [])
                    if str(item.get("series_family", "")) == series_family
                    and str(item.get("user_band", series_family)) == user_band
                ][:4],
                "scope_boundaries": packet_scope_boundaries(series_family, user_band, "ALL"),
                "reasoning_task_type": "cross_source_claim",
            }
        )

    return {
        "artifact_type": "qual_evidence_packet",
        "generated_at": now_iso(),
        "packet_count": len(packets),
        "reasoning_task_types": sorted({str(packet.get("reasoning_task_type", "")) for packet in packets if str(packet.get("reasoning_task_type", "")).strip()}),
        "series_families": sorted({str(packet.get("series_family", "")) for packet in packets if str(packet.get("series_family", "")).strip()}),
        "packets": packets,
    }


def build_supporting_evidence_refs(packet: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    refs.extend(f"case:{case_title}" for case_title in packet.get("supporting_cases", []) or [] if normalize_text(case_title))
    refs.extend(
        f"passage:{item.get('passage_id')}"
        for item in packet.get("supporting_passages", []) or []
        if normalize_text(item.get("passage_id"))
    )
    refs.extend(
        "survey:{wave}/{question}/{resp}".format(
            wave=normalize_text(item.get("wave_id")) or "-",
            question=normalize_text(item.get("question_id")) or "-",
            resp=normalize_text(item.get("response_identity_id")) or "-",
        )
        for item in packet.get("supporting_open_answers", []) or []
    )
    refs.extend(
        f"voc:{normalize_text(packet.get('series_family'))}/{normalize_text(item.get('topic_name'))}"
        for item in packet.get("linked_voc_signals", []) or []
        if normalize_text(item.get("topic_name"))
    )
    return dedupe_preserve_order([ref for ref in refs if normalize_text(ref)])


def build_disconfirming_evidence_refs(packet: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    refs.extend(f"case:{case_title}" for case_title in packet.get("disconfirming_cases", []) or [] if normalize_text(case_title))
    return dedupe_preserve_order(refs)


def packet_is_boundary(packet: dict[str, Any]) -> bool:
    return str(packet.get("user_band", "")) == "N_omni" or any("缺稳定自家 voc" in normalize_token(boundary) for boundary in (packet.get("scope_boundaries", []) or []))


def packet_priority(packet: dict[str, Any]) -> tuple[str, str, bool]:
    task_type = str(packet.get("reasoning_task_type", ""))
    series_family = str(packet.get("series_family", ""))
    user_band = str(packet.get("user_band", series_family))
    topic_name = str(packet.get("topic_name", ""))
    linked_voc_signals = packet.get("linked_voc_signals", []) or []
    voc_negative = max((safe_int(item.get("negative_count", 0)) for item in linked_voc_signals), default=0)
    voc_positive = max((safe_int(item.get("positive_count", 0)) for item in linked_voc_signals), default=0)
    has_quant = bool(linked_voc_signals or packet.get("linked_survey_signals") or packet.get("supporting_open_answers"))
    has_qual = bool(packet.get("supporting_cases") or packet.get("supporting_passages"))

    if task_type == "cross_source_claim":
        if user_band == "N_omni":
            return "P4", "当前是缺样本边界带，只保留边界型带宽判断。", True
        if not has_quant and not has_qual:
            return "P5", "当前缺少足够跨源支撑，先后置。", False
        return "P3", "该包承接系列级 claim，需要先做跨源收敛和验真。", True

    if task_type == "theme_explain":
        if user_band == "N_omni":
            return "P4", "当前边界带不做伪主题解释。", False
        if voc_negative > max(voc_positive, 0):
            return "P1", f"`{topic_name or '该主题'}` 当前是负向焦点，优先解释为什么会打穿底线。", True
        if voc_positive > 0 and voc_positive >= voc_negative:
            return "P2", f"`{topic_name or '该主题'}` 当前是正向锚点，需要解释用户为什么愿意买单。", True
        if has_quant or has_qual:
            return "P3", f"`{topic_name or '该主题'}` 当前有局部信号，适合做方向性解释。", True
        return "P5", f"`{topic_name or '该主题'}` 当前证据太弱，先后置。", False

    if task_type == "case_explain":
        if not packet.get("supporting_cases"):
            return "P5", "当前没有明确案例标题，先跳过。", False
        return "P5", "单案例只在被高优主题引用时才进入本轮推理。", False

    return "P5", "当前不在本轮重点任务范围内。", False


def build_qual_reasoning_task_board(qual_evidence_packet: dict[str, Any]) -> dict[str, Any]:
    packets = qual_evidence_packet.get("packets", []) or []
    preliminary_rows: list[dict[str, Any]] = []
    for packet in packets:
        priority, why, ready = packet_priority(packet)
        preliminary_rows.append(
            {
                "packet_id": str(packet.get("packet_id", "")),
                "series_family": str(packet.get("series_family", "")),
                "user_band": str(packet.get("user_band", packet.get("series_family", ""))),
                "topic_name": str(packet.get("topic_name", "")),
                "market_scope": str(packet.get("market_scope", "")),
                "reasoning_task_type": str(packet.get("reasoning_task_type", "")),
                "priority": priority,
                "why_this_packet_matters": why,
                "ready_for_llm": ready,
                "skip_reason": "" if ready else why,
            }
        )

    selected_case_titles = {
        str(case_title)
        for packet in packets
        for row in preliminary_rows
        if row["packet_id"] == packet.get("packet_id")
        and row["reasoning_task_type"] in {"theme_explain", "cross_source_claim"}
        and row["priority"] in {"P1", "P2", "P3"}
        for case_title in (packet.get("supporting_cases", []) or [])[:6]
        if normalize_text(case_title)
    }

    rows: list[dict[str, Any]] = []
    for row in preliminary_rows:
        packet = next((item for item in packets if str(item.get("packet_id", "")) == row["packet_id"]), {})
        if row["reasoning_task_type"] == "case_explain":
            case_title = normalize_text((packet.get("supporting_cases", []) or [""])[0] if packet else "")
            if case_title in selected_case_titles:
                row["priority"] = "P3"
                row["why_this_packet_matters"] = "该案例被高优主题或 claim 引用，需先做案例深描。"
                row["ready_for_llm"] = True
                row["skip_reason"] = ""
            else:
                row["ready_for_llm"] = False
                row["skip_reason"] = "当前没有被 P1-P3 主题或 claim 引用，先不跑全量 case。"
        rows.append(row)

    priority_order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
    rows.sort(
        key=lambda item: (
            priority_order.get(str(item.get("priority", "P5")), 99),
            str(item.get("reasoning_task_type", "")),
            str(item.get("series_family", "")),
            str(item.get("user_band", "")),
            str(item.get("topic_name", "")),
            str(item.get("packet_id", "")),
        )
    )
    return {
        "artifact_type": "qual_reasoning_task_board",
        "generated_at": now_iso(),
        "row_count": len(rows),
        "rows": rows,
    }


def build_reasoning_confidence(
    *,
    supporting_case_count: int,
    survey_support_count: int,
    voc_support_count: int,
    boundary_count: int,
) -> str:
    if supporting_case_count >= 2 and (survey_support_count > 0 or voc_support_count > 0):
        return "high"
    if supporting_case_count >= 1 and (survey_support_count > 0 or voc_support_count > 0):
        return "medium"
    if supporting_case_count >= 1 or voc_support_count > 0 or survey_support_count > 0:
        return "low" if boundary_count == 0 else "weak"
    return "weak"


def join_topic_names(packet: dict[str, Any]) -> list[str]:
    topic_name = str(packet.get("topic_name", ""))
    return [part.strip() for part in topic_name.split("；") if part.strip() and part.strip() != "-"]


def keyword_in_packet(packet: dict[str, Any], *keywords: str) -> bool:
    blob = normalize_token(
        " ".join(
            [
                str(packet.get("topic_name", "")),
                *[str(item.get("passage_text", "")) for item in (packet.get("supporting_passages", []) or [])],
                *[str(item.get("answer_text", "")) for item in (packet.get("supporting_open_answers", []) or [])],
                *[str(item.get("problem_name", "")) for item in (packet.get("linked_drilldown_rows", []) or [])],
            ]
        )
    )
    return any(normalize_token(keyword) in blob for keyword in keywords if normalize_token(keyword))


def infer_hidden_need(packet: dict[str, Any]) -> str:
    if keyword_in_packet(packet, "返工", "水渍", "不留痕", "拖净", "污渍"):
        return "用户真正要的不是单次拖地动作，而是结果可确认且不用自己返工。"
    if keyword_in_packet(packet, "边角", "漏扫", "覆盖", "踢脚线"):
        return "用户在意的不是名义覆盖率，而是高频可见区域别留下明显漏扫。"
    if keyword_in_packet(packet, "卡困", "避障", "门槛", "脱困", "地图"):
        return "用户真正要的是运行过程可预测，不希望自己重新回到救援位。"
    if keyword_in_packet(packet, "维护", "基站", "滚刷", "异味", "尘袋"):
        return "用户并不是反对维护本身，而是反对把托管承诺转嫁成隐性体力活。"
    if keyword_in_packet(packet, "噪音", "安静", "扰民"):
        return "用户在意的不是分贝数字本身，而是机器能否融入共处场景。"
    if keyword_in_packet(packet, "续航", "充电", "回充", "中断"):
        return "用户真正担心的是一次任务无法闭环，导致清洁要被人重新接管。"
    if keyword_in_packet(packet, "外观", "做工", "质感", "尺寸"):
        return "用户在意的是产品能否自然融入家，而不是单独看工业设计参数。"
    if keyword_in_packet(packet, "宠物", "家庭", "有娃", "毛发"):
        return "用户真正看重的是高压家庭工况下依然稳，而不是单点功能点。"
    return "用户要的是稳定、少返工、少救援的真实托管体验。"


def infer_failure_definition(packet: dict[str, Any]) -> str:
    passages = packet.get("supporting_passages", []) or []
    for passage in passages:
        role = normalize_text(passage.get("passage_role", ""))
        text = normalize_text(passage.get("passage_text", ""))
        if role in {"痛点", "不满", "吐槽"} and text:
            return text
    open_answers = packet.get("supporting_open_answers", []) or []
    for answer in open_answers:
        text = normalize_text(answer.get("answer_text", ""))
        if text:
            return text
    drilldown_rows = packet.get("linked_drilldown_rows", []) or []
    if drilldown_rows:
        return normalize_text(drilldown_rows[0].get("negative_profile_summary", "")) or "一旦核心体验失守，用户就会认为机器没有兑现承诺。"
    return "只要关键结果不稳定，用户就会认为这台机器不值得继续信任。"


def infer_acceptable_tradeoff(packet: dict[str, Any]) -> str:
    blob = normalize_token(
        " ".join(
            [
                *[str(item.get("passage_text", "")) for item in (packet.get("supporting_passages", []) or [])],
                *[str(item.get("answer_text", "")) for item in (packet.get("supporting_open_answers", []) or [])],
            ]
        )
    )
    if "80%" in blob or "差不多" in blob or "能接受" in blob:
        return "可以接受不是每次都满分，但不能接受需要频繁返工或救援。"
    if keyword_in_packet(packet, "噪音", "声音大", "夜间"):
        return "可以接受短时间工作声，但不能接受持续打扰共处空间。"
    if keyword_in_packet(packet, "维护", "滚刷", "清洁槽"):
        return "可以接受低频可预期维护，但不能接受每次都要脏手补位。"
    return "可以接受局部妥协，但不能接受核心结果不稳定。"


def infer_compensation_behavior(packet: dict[str, Any]) -> str:
    failure = normalize_token(infer_failure_definition(packet))
    if any(keyword in failure for keyword in ("返工", "再拖", "重拖", "自己拖")):
        return "一旦结果不稳，用户会自己返工或追加人工兜底。"
    if any(keyword in failure for keyword in ("卡", "救", "门槛", "脱困", "救援")):
        return "一旦运行过程不可预测，用户会减少使用频次并在关键任务前人工清场。"
    if any(keyword in failure for keyword in ("维护", "清理", "异味", "滚刷", "尘袋")):
        return "一旦维护负担超出预期，用户会拖延维护甚至降低使用意愿。"
    return "一旦核心承诺失守，用户会转向人工检查、分区兜底或降低使用信任。"


def infer_counter_hypotheses(packet: dict[str, Any]) -> list[str]:
    hypotheses: list[str] = []
    if packet.get("supporting_open_answers"):
        hypotheses.append("这不一定是单纯的硬件能力不足，也可能是用户对结果确认感异常敏感。")
    if packet.get("linked_survey_signals"):
        hypotheses.append("这不只是单一场景抱怨，还可能和人群任务压力差异有关。")
    if packet.get("linked_voc_signals"):
        hypotheses.append("高频提及不等于全部都是负向抱怨，仍需区分负向焦点与正向锚点。")
    if not hypotheses:
        hypotheses.append("当前更像方向性解释，还不能排除样本阶段差异。")
    return dedupe_preserve_order(hypotheses)[:3]


def build_case_reasoning_card_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    case_title = normalize_text((packet.get("supporting_cases", []) or [""])[0])
    passages = packet.get("supporting_passages", []) or []
    explicit_needs = dedupe_normalized_texts(
        [item.get("passage_text", "") for item in passages if normalize_text(item.get("passage_role", "")) in {"期待", "需求", "购买动机"}]
    )[:3]
    if not explicit_needs:
        explicit_needs = dedupe_normalized_texts([item.get("passage_text", "") for item in passages[:2]])[:2]
    purchase_trigger_chain = dedupe_normalized_texts(explicit_needs + [infer_hidden_need(packet)])[:3]
    failure_definition = infer_failure_definition(packet)
    hidden_need = infer_hidden_need(packet)
    return {
        "case_id": normalize_text(packet.get("packet_id")) or f"case::{slugify(case_title)}",
        "case_title": case_title or "-",
        "series_family": normalize_text(packet.get("series_family")) or "unknown",
        "source_mode": "summary_case",
        "persona_thesis": f"{case_title or '该案例'} 本质上在要一台能把关键结果守住、且别把用户重新拉回兜底位的机器。",
        "explicit_needs": explicit_needs,
        "hidden_needs": [hidden_need],
        "failure_definition": failure_definition,
        "trust_breaker": failure_definition,
        "acceptable_tradeoff": infer_acceptable_tradeoff(packet),
        "compensation_behavior": infer_compensation_behavior(packet),
        "purchase_trigger_chain": purchase_trigger_chain,
        "counter_hypotheses": infer_counter_hypotheses(packet),
        "disconfirming_signals": build_disconfirming_evidence_refs(packet),
        "evidence_passage_ids": dedupe_preserve_order(
            [normalize_text(item.get("passage_id", "")) for item in passages if normalize_text(item.get("passage_id", ""))]
        )[:6],
        "reasoning_confidence": build_reasoning_confidence(
            supporting_case_count=1 if case_title else 0,
            survey_support_count=0,
            voc_support_count=0,
            boundary_count=len(packet.get("scope_boundaries", []) or []),
        ),
    }


def build_theme_reasoning_row_from_packet(
    packet: dict[str, Any],
    case_cards_by_title: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    topic_name = normalize_text(packet.get("topic_name")) or "-"
    supporting_case_ids = [case_cards_by_title[title]["case_id"] for title in packet.get("supporting_cases", []) or [] if title in case_cards_by_title]
    supporting_case_titles = [title for title in packet.get("supporting_cases", []) or [] if normalize_text(title)]
    survey_segments = [normalize_text(item.get("segment_name", "")) for item in packet.get("linked_survey_signals", []) or [] if normalize_text(item.get("segment_name", ""))]
    voc_topics = [normalize_text(item.get("topic_name", "")) for item in packet.get("linked_voc_signals", []) or [] if normalize_text(item.get("topic_name", ""))]
    linked_drilldown_rows = packet.get("linked_drilldown_rows", []) or []
    negative_profile = normalize_text(linked_drilldown_rows[0].get("negative_profile_summary", "")) if linked_drilldown_rows else ""
    next_axis = normalize_text(linked_drilldown_rows[0].get("next_drilldown_axis", "")) if linked_drilldown_rows else ""
    hidden_need = infer_hidden_need(packet)
    claim_id = f"theme_claim::{slugify(normalize_text(packet.get('packet_id')))}"
    candidate_claim = f"{topic_name} 真正承载的不是单点功能抱怨，而是 `{hidden_need}`"
    return {
        "theme_name": topic_name,
        "series_family": normalize_text(packet.get("series_family")) or "unknown",
        "user_band": normalize_text(packet.get("user_band")) or normalize_text(packet.get("series_family")) or "unknown",
        "market_scope": normalize_text(packet.get("market_scope")) or "ALL",
        "who_cares": dedupe_normalized_texts(survey_segments + supporting_case_titles)[:4],
        "why_it_matters": negative_profile or infer_failure_definition(packet),
        "what_users_really_mean": hidden_need,
        "what_is_not_the_real_issue": infer_counter_hypotheses(packet)[0],
        "supporting_case_ids": supporting_case_ids,
        "disconfirming_case_ids": build_disconfirming_evidence_refs(packet),
        "open_questions": dedupe_normalized_texts([next_axis] + list(packet.get("scope_boundaries", []) or []))[:3],
        "reasoning_confidence": build_reasoning_confidence(
            supporting_case_count=len(supporting_case_ids),
            survey_support_count=len(packet.get("supporting_open_answers", []) or []) + len(packet.get("linked_survey_signals", []) or []),
            voc_support_count=len(voc_topics),
            boundary_count=len(packet.get("scope_boundaries", []) or []),
        ),
        "packet_id": normalize_text(packet.get("packet_id")),
        "claim_id": claim_id,
        "candidate_claim": candidate_claim,
        "supporting_evidence_refs": build_supporting_evidence_refs(packet),
        "disconfirming_evidence_refs": build_disconfirming_evidence_refs(packet),
    }


def build_cross_source_hypothesis_row_from_packet(
    packet: dict[str, Any],
    theme_rows_by_packet: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    topics = join_topic_names(packet)
    related_theme_rows = [
        row
        for row in theme_rows_by_packet.values()
        if row.get("series_family") == packet.get("series_family")
        and row.get("user_band") == packet.get("user_band")
        and row.get("theme_name") in topics
    ]
    support_from_voc = [
        {
            "topic_name": normalize_text(item.get("topic_name", "")),
            "mention_count": safe_int(item.get("mention_count", 0)),
            "positive_count": safe_int(item.get("positive_count", 0)),
            "negative_count": safe_int(item.get("negative_count", 0)),
        }
        for item in (packet.get("linked_voc_signals", []) or [])
    ]
    support_from_survey = [
        {
            "segment_name": normalize_text(item.get("segment_name", "")),
            "wave_name": normalize_text(item.get("wave_name", "")),
        }
        for item in (packet.get("linked_survey_signals", []) or [])
        if normalize_text(item.get("segment_name", "")) or normalize_text(item.get("wave_name", ""))
    ]
    support_from_qual = [
        {
            "theme_name": normalize_text(item.get("theme_name", "")),
            "claim_id": normalize_text(item.get("claim_id", "")),
            "reasoning_confidence": normalize_text(item.get("reasoning_confidence", "")),
        }
        for item in related_theme_rows
    ]
    conflict_signals: list[str] = []
    for signal in support_from_voc:
        if safe_int(signal.get("positive_count", 0)) > 0 and safe_int(signal.get("negative_count", 0)) > 0:
            conflict_signals.append(f"{signal.get('topic_name', '-')}: 正负信号并存，需避免只按单一情绪解释。")
    conflict_signals.extend(list(packet.get("scope_boundaries", []) or [])[:2])

    hypothesis_id = f"hypothesis::{slugify(normalize_text(packet.get('packet_id')))}"
    claim = ""
    if packet.get("user_band") == "N_omni":
        claim = "N_omni 当前不能讲成稳定用户带宽主命题，优先结论仍是缺样本边界。"
        resolution_status = "not_ready"
        why = "当前缺稳定自家 VOC 样本，因此只能保留边界判断与补数方向。"
    else:
        claim = (
            f"{normalize_text(packet.get('user_band')) or normalize_text(packet.get('series_family'))} 当前更应该围绕 "
            f"`{' / '.join(topics[:2]) or '核心用户焦点'}` 组织用户主命题，而不是泛泛讲一串功能点。"
        )
        if len(support_from_qual) >= 2 and (support_from_voc or support_from_survey):
            resolution_status = "accepted"
            why = "当前定性解释已经和 VOC/问卷形成同向支撑，可以进入正式 thesis 收敛。"
        elif len(support_from_qual) >= 1 and (support_from_voc or support_from_survey):
            resolution_status = "accepted"
            why = "当前已经形成跨源同向支撑，但仍需继续补反证边界。"
        elif support_from_qual and conflict_signals:
            resolution_status = "contested"
            why = "当前已有方向性解释，但跨源里仍有未解冲突，不应直接上台讲满。"
        else:
            resolution_status = "not_ready"
            why = "当前还不足以构成系列级稳定主命题。"

    return {
        "hypothesis_id": hypothesis_id,
        "series_family": normalize_text(packet.get("series_family")) or "unknown",
        "user_band": normalize_text(packet.get("user_band")) or normalize_text(packet.get("series_family")) or "unknown",
        "claim": claim,
        "support_from_voc": support_from_voc,
        "support_from_survey": support_from_survey,
        "support_from_qual": support_from_qual,
        "conflict_signals": dedupe_normalized_texts(conflict_signals)[:4],
        "resolution_status": resolution_status,
        "why_accepted_or_rejected": why,
        "packet_id": normalize_text(packet.get("packet_id")),
        "candidate_claim": claim,
        "supporting_evidence_refs": build_supporting_evidence_refs(packet),
        "disconfirming_evidence_refs": build_disconfirming_evidence_refs(packet),
    }


def _json_response_format(profile: dict[str, Any]) -> Any:
    response_format = profile.get("response_format")
    if response_format is None or response_format == "":
        return {"type": "json_object"}
    return response_format


def _build_openai_messages(
    *,
    task_label: str,
    packet: dict[str, Any],
    draft_payload: dict[str, Any],
    extra_context: dict[str, Any] | None = None,
    system_prompt_id: str,
) -> list[dict[str, str]]:
    user_payload = {
        "task_label": task_label,
        "system_prompt_id": system_prompt_id,
        "packet": packet,
        "draft_payload": draft_payload,
        "extra_context": extra_context or {},
    }
    return [
        {
            "role": "system",
            "content": (
                "你是扫地机器人用户研究定性推理器。"
                "只能基于给定 packet 和 extra_context 生成结构化 JSON。"
                "不要发散引用未提供的事实，不要输出 Markdown，不要遗漏 evidence 字段。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False),
        },
    ]


def _call_openai_compatible(profile: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
    base_url = normalize_text(profile.get("base_url"))
    api_key_env = normalize_text(profile.get("api_key_env"))
    if not base_url:
        raise ValueError("openai_compatible profile missing base_url")
    if not api_key_env:
        raise ValueError("openai_compatible profile missing api_key_env")
    api_key = normalize_text(os.environ.get(api_key_env))
    if not api_key:
        raise ValueError(f"openai_compatible env `{api_key_env}` is empty")
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": normalize_text(profile.get("model")),
        "temperature": profile.get("temperature"),
        "max_tokens": profile.get("max_tokens"),
        "messages": messages,
        "response_format": _json_response_format(profile),
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    timeout = max(1, safe_int(profile.get("timeout_sec", 90)))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # pragma: no cover - exercised in live runtime only
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"http_error:{exc.code}:{body[:300]}") from exc
    payload = json.loads(raw)
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        text_parts = [str(item.get("text", "")) for item in content if isinstance(item, dict)]
        content = "\n".join(part for part in text_parts if part)
    if not isinstance(content, str):
        raise ValueError("openai_compatible response missing string content")
    return json.loads(content)


def _merge_with_draft(result: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    merged = dict(draft)
    for key, value in result.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _run_case_reasoning(
    *,
    packet: dict[str, Any],
    profile: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    draft = build_case_reasoning_card_from_packet(packet)
    if profile is None:
        return draft, ""
    provider = normalize_text(profile.get("provider"))
    if provider == "deterministic_stub":
        return draft, ""
    if provider != "openai_compatible":
        return draft, f"unsupported_provider:{provider}"
    try:
        result = _call_openai_compatible(
            profile,
            _build_openai_messages(
                task_label="qual_case_reasoning_card",
                packet=packet,
                draft_payload=draft,
                extra_context=None,
                system_prompt_id=normalize_text(profile.get("system_prompt_id")),
            ),
        )
        return _merge_with_draft(result, draft), ""
    except Exception as exc:  # pragma: no cover - live runtime fallback
        return draft, f"provider_error:{exc}"


def _run_theme_reasoning(
    *,
    packet: dict[str, Any],
    case_cards_by_title: dict[str, dict[str, Any]],
    profile: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    draft = build_theme_reasoning_row_from_packet(packet, case_cards_by_title)
    if profile is None:
        return draft, ""
    provider = normalize_text(profile.get("provider"))
    if provider == "deterministic_stub":
        return draft, ""
    if provider != "openai_compatible":
        return draft, f"unsupported_provider:{provider}"
    extra_context = {
        "case_cards": [case_cards_by_title[title] for title in packet.get("supporting_cases", []) or [] if title in case_cards_by_title],
    }
    try:
        result = _call_openai_compatible(
            profile,
            _build_openai_messages(
                task_label="qual_theme_reasoning_map",
                packet=packet,
                draft_payload=draft,
                extra_context=extra_context,
                system_prompt_id=normalize_text(profile.get("system_prompt_id")),
            ),
        )
        return _merge_with_draft(result, draft), ""
    except Exception as exc:  # pragma: no cover - live runtime fallback
        return draft, f"provider_error:{exc}"


def _run_cross_source_reasoning(
    *,
    packet: dict[str, Any],
    theme_rows_by_packet: dict[str, dict[str, Any]],
    profile: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    draft = build_cross_source_hypothesis_row_from_packet(packet, theme_rows_by_packet)
    if profile is None:
        return draft, ""
    provider = normalize_text(profile.get("provider"))
    if provider == "deterministic_stub":
        return draft, ""
    if provider != "openai_compatible":
        return draft, f"unsupported_provider:{provider}"
    extra_context = {
        "theme_rows": [
            row
            for row in theme_rows_by_packet.values()
            if row.get("series_family") == packet.get("series_family") and row.get("user_band") == packet.get("user_band")
        ],
    }
    try:
        result = _call_openai_compatible(
            profile,
            _build_openai_messages(
                task_label="cross_source_hypothesis_board",
                packet=packet,
                draft_payload=draft,
                extra_context=extra_context,
                system_prompt_id=normalize_text(profile.get("system_prompt_id")),
            ),
        )
        return _merge_with_draft(result, draft), ""
    except Exception as exc:  # pragma: no cover - live runtime fallback
        return draft, f"provider_error:{exc}"


def empty_reasoning_bundle(
    *,
    analysis_engine: str,
    fallback_status: str,
    task_board: dict[str, Any],
) -> dict[str, Any]:
    return {
        "analysis_engine": analysis_engine,
        "fallback_status": fallback_status,
        "qual_reasoning_task_board": task_board,
        "qual_case_reasoning_cards": {
            "artifact_type": "qual_case_reasoning_cards",
            "generated_at": now_iso(),
            "row_count": 0,
            "rows": [],
        },
        "qual_theme_reasoning_map": {
            "artifact_type": "qual_theme_reasoning_map",
            "generated_at": now_iso(),
            "row_count": 0,
            "rows": [],
        },
        "cross_source_hypothesis_board": {
            "artifact_type": "cross_source_hypothesis_board",
            "generated_at": now_iso(),
            "row_count": 0,
            "rows": [],
        },
        "candidate_claims": [],
    }


def run_dual_engine_reasoning(
    *,
    analysis_engine: str,
    qual_evidence_packet: dict[str, Any],
    llm_profile_path: str | Path | None,
    qual_reasoning_profile: str,
    thesis_reasoning_profile: str,
) -> dict[str, Any]:
    task_board = build_qual_reasoning_task_board(qual_evidence_packet)
    if analysis_engine != "dual_engine_llm":
        return empty_reasoning_bundle(
            analysis_engine=analysis_engine,
            fallback_status="analysis_engine=rule_only",
            task_board=task_board,
        )
    if not llm_profile_path:
        return empty_reasoning_bundle(
            analysis_engine=analysis_engine,
            fallback_status="dual_engine_llm_missing_profile_path",
            task_board=task_board,
        )

    try:
        qual_profile = resolve_llm_profile(llm_profile_path, qual_reasoning_profile)
        thesis_profile = resolve_llm_profile(llm_profile_path, thesis_reasoning_profile)
        if qual_evidence_packet.get("packets"):
            _ = build_llm_prompt_envelope(packet=(qual_evidence_packet.get("packets", []) or [{}])[0], profile=qual_profile)
            _ = build_llm_prompt_envelope(packet=(qual_evidence_packet.get("packets", []) or [{}])[0], profile=thesis_profile)
    except Exception as exc:  # pragma: no cover - deterministic in tests
        return empty_reasoning_bundle(
            analysis_engine=analysis_engine,
            fallback_status=f"dual_engine_llm_profile_error:{exc}",
            task_board=task_board,
        )

    packets_by_id = {str(packet.get("packet_id", "")): packet for packet in qual_evidence_packet.get("packets", []) or []}
    task_rows = task_board.get("rows", []) or []
    provider_errors: list[str] = []

    case_rows: list[dict[str, Any]] = []
    case_cards_by_title: dict[str, dict[str, Any]] = {}
    for task in task_rows:
        if task.get("reasoning_task_type") != "case_explain" or not task.get("ready_for_llm"):
            continue
        packet = packets_by_id.get(str(task.get("packet_id", "")), {})
        row, error = _run_case_reasoning(packet=packet, profile=qual_profile)
        if error:
            provider_errors.append(f"{task.get('packet_id')}:{error}")
        case_rows.append(row)
        case_cards_by_title[normalize_text(row.get("case_title", ""))] = row

    theme_rows: list[dict[str, Any]] = []
    theme_rows_by_packet: dict[str, dict[str, Any]] = {}
    for task in task_rows:
        if task.get("reasoning_task_type") != "theme_explain" or not task.get("ready_for_llm"):
            continue
        packet = packets_by_id.get(str(task.get("packet_id", "")), {})
        row, error = _run_theme_reasoning(packet=packet, case_cards_by_title=case_cards_by_title, profile=qual_profile)
        if error:
            provider_errors.append(f"{task.get('packet_id')}:{error}")
        theme_rows.append(row)
        theme_rows_by_packet[str(row.get("packet_id", ""))] = row

    hypothesis_rows: list[dict[str, Any]] = []
    for task in task_rows:
        if task.get("reasoning_task_type") != "cross_source_claim" or not task.get("ready_for_llm"):
            continue
        packet = packets_by_id.get(str(task.get("packet_id", "")), {})
        row, error = _run_cross_source_reasoning(packet=packet, theme_rows_by_packet=theme_rows_by_packet, profile=thesis_profile)
        if error:
            provider_errors.append(f"{task.get('packet_id')}:{error}")
        hypothesis_rows.append(row)

    candidate_claims = [
        {
            "claim_id": str(row.get("claim_id", "")),
            "packet_id": str(row.get("packet_id", "")),
            "claim_scope": f"{row.get('series_family', '-')}/{row.get('user_band', '-')}/{row.get('theme_name', '-')}",
            "claim_source": "theme_reasoning",
            "candidate_claim": str(row.get("candidate_claim", "")),
            "supporting_evidence_refs": list(row.get("supporting_evidence_refs", []) or []),
            "disconfirming_evidence_refs": list(row.get("disconfirming_evidence_refs", []) or []),
        }
        for row in theme_rows
        if normalize_text(row.get("candidate_claim", ""))
    ]
    candidate_claims.extend(
        {
            "claim_id": str(row.get("hypothesis_id", "")),
            "packet_id": str(row.get("packet_id", "")),
            "claim_scope": f"{row.get('series_family', '-')}/{row.get('user_band', '-')}/series_claim",
            "claim_source": "cross_source_hypothesis",
            "candidate_claim": str(row.get("candidate_claim", "")),
            "supporting_evidence_refs": list(row.get("supporting_evidence_refs", []) or []),
            "disconfirming_evidence_refs": list(row.get("disconfirming_evidence_refs", []) or []),
        }
        for row in hypothesis_rows
        if normalize_text(row.get("candidate_claim", ""))
    )

    fallback_status = ""
    if provider_errors:
        fallback_status = "dual_engine_llm_provider_fallback:" + " | ".join(provider_errors[:8])

    return {
        "analysis_engine": analysis_engine,
        "fallback_status": fallback_status,
        "qual_reasoning_task_board": {
            **task_board,
            "generated_at": now_iso(),
        },
        "qual_case_reasoning_cards": {
            "artifact_type": "qual_case_reasoning_cards",
            "generated_at": now_iso(),
            "row_count": len(case_rows),
            "rows": case_rows,
        },
        "qual_theme_reasoning_map": {
            "artifact_type": "qual_theme_reasoning_map",
            "generated_at": now_iso(),
            "row_count": len(theme_rows),
            "rows": theme_rows,
        },
        "cross_source_hypothesis_board": {
            "artifact_type": "cross_source_hypothesis_board",
            "generated_at": now_iso(),
            "row_count": len(hypothesis_rows),
            "rows": hypothesis_rows,
        },
        "candidate_claims": candidate_claims,
    }


def evidence_grade_from_refs(
    *,
    supporting_evidence_refs: list[str],
) -> str:
    case_count = len([ref for ref in supporting_evidence_refs if ref.startswith("case:")])
    survey_count = len([ref for ref in supporting_evidence_refs if ref.startswith("survey:")])
    voc_count = len([ref for ref in supporting_evidence_refs if ref.startswith("voc:")])
    if case_count >= 2 and (survey_count > 0 or voc_count > 0):
        return "A"
    if case_count >= 1 and (survey_count > 0 or voc_count > 0):
        return "B"
    if case_count >= 1:
        return "C"
    if supporting_evidence_refs:
        return "weak_signal"
    return "not_ready"


def evaluate_candidate_claims(
    candidate_claims: list[dict[str, Any]],
    qual_evidence_packet: dict[str, Any],
    *,
    analysis_engine: str,
    fallback_status: str = "",
    cross_source_hypothesis_board: dict[str, Any] | None = None,
    qual_theme_reasoning_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet_lookup = {str(packet.get("packet_id", "")): packet for packet in qual_evidence_packet.get("packets", []) or []}
    theme_claim_lookup = {
        str(row.get("claim_id", "")): row for row in (qual_theme_reasoning_map or {}).get("rows", []) or [] if normalize_text(row.get("claim_id", ""))
    }
    hypothesis_lookup = {
        str(row.get("hypothesis_id", "")): row for row in (cross_source_hypothesis_board or {}).get("rows", []) or [] if normalize_text(row.get("hypothesis_id", ""))
    }
    log_rows: list[dict[str, Any]] = []

    if fallback_status:
        log_rows.append(
            {
                "claim_id": "engine_status",
                "claim_scope": "runtime",
                "claim_source": "engine_status",
                "candidate_claim": fallback_status,
                "accept_status": "demoted",
                "demotion_reason": fallback_status,
                "evidence_grade": "not_ready",
                "frontstage_permission": False,
                "supporting_evidence_refs": [],
                "disconfirming_evidence_refs": [],
            }
        )

    for claim in candidate_claims:
        claim_id = normalize_text(claim.get("claim_id"))
        packet_id = normalize_text(claim.get("packet_id"))
        claim_scope = normalize_text(claim.get("claim_scope")) or packet_id or "unknown_scope"
        candidate_text = normalize_text(claim.get("candidate_claim"))
        packet = packet_lookup.get(packet_id, {})
        has_boundary = bool(packet.get("scope_boundaries"))

        supporting_refs = dedupe_preserve_order(
            [normalize_text(ref) for ref in (claim.get("supporting_evidence_refs", []) or []) if normalize_text(ref)]
        ) or build_supporting_evidence_refs(packet)
        disconfirming_refs = dedupe_preserve_order(
            [normalize_text(ref) for ref in (claim.get("disconfirming_evidence_refs", []) or []) if normalize_text(ref)]
        ) or build_disconfirming_evidence_refs(packet)

        evidence_grade = evidence_grade_from_refs(supporting_evidence_refs=supporting_refs)
        theme_row = theme_claim_lookup.get(claim_id, {})
        hypothesis_row = hypothesis_lookup.get(claim_id, {})
        resolution_status = normalize_text(hypothesis_row.get("resolution_status", ""))
        conflict_signals = list(hypothesis_row.get("conflict_signals", []) or [])
        claim_source = normalize_text(claim.get("claim_source")) or "cross_source_hypothesis"

        if resolution_status in {"rejected", "not_ready"}:
            accept_status = "rejected"
            demotion_reason = normalize_text(hypothesis_row.get("why_accepted_or_rejected")) or "当前 hypothesis 未达到正式判断条件。"
            frontstage_permission = False
            evidence_grade = "not_ready"
        elif evidence_grade in {"A", "B"} and has_boundary and resolution_status != "contested":
            accept_status = "accepted"
            demotion_reason = ""
            frontstage_permission = True
        elif evidence_grade == "C":
            accept_status = "demoted"
            demotion_reason = "当前只有定性单源支持，需降级为 direction_only。"
            frontstage_permission = False
        elif resolution_status == "contested" or conflict_signals:
            accept_status = "demoted"
            demotion_reason = normalize_text(hypothesis_row.get("why_accepted_or_rejected")) or "当前仍有未解冲突，不允许直接上前台。"
            frontstage_permission = False
            if evidence_grade == "not_ready":
                evidence_grade = "weak_signal"
        elif evidence_grade == "not_ready":
            accept_status = "rejected"
            demotion_reason = "当前缺少足够支持证据，不能进入正式判断。"
            frontstage_permission = False
        elif not has_boundary:
            accept_status = "demoted"
            demotion_reason = "缺少足够边界说明，当前不允许直接上前台。"
            frontstage_permission = False
            if evidence_grade in {"A", "B"}:
                evidence_grade = "weak_signal"
        elif evidence_grade == "weak_signal":
            accept_status = "demoted"
            demotion_reason = "当前支持证据偏弱，只能保留方向性判断。"
            frontstage_permission = False
        else:
            accept_status = "rejected"
            demotion_reason = "当前缺少足够支持证据，不能进入正式判断。"
            frontstage_permission = False

        if theme_row and not theme_row.get("supporting_case_ids") and accept_status == "accepted":
            accept_status = "demoted"
            demotion_reason = "缺少稳定案例支撑，不应直接上前台。"
            frontstage_permission = False
            evidence_grade = "weak_signal"

        log_rows.append(
            {
                "claim_id": claim_id or f"claim::{slugify(claim_scope)}",
                "claim_scope": claim_scope,
                "claim_source": claim_source,
                "candidate_claim": candidate_text,
                "accept_status": accept_status,
                "demotion_reason": demotion_reason,
                "evidence_grade": evidence_grade,
                "frontstage_permission": frontstage_permission,
                "supporting_evidence_refs": supporting_refs,
                "disconfirming_evidence_refs": disconfirming_refs,
            }
        )

    return {
        "artifact_type": "judgment_acceptance_log",
        "generated_at": now_iso(),
        "analysis_engine": analysis_engine,
        "fallback_status": fallback_status,
        "row_count": len(log_rows),
        "rows": log_rows,
    }
