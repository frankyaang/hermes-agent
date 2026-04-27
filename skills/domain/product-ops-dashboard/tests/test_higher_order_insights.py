from __future__ import annotations

import inspect
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock
from pathlib import Path
from zipfile import ZipFile

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) in sys.path:
    sys.path.remove(str(SCRIPT_ROOT))
sys.path.insert(0, str(SCRIPT_ROOT))
for module_name in (
    "derive_higher_order_insights",
    "generate_analysis_scaffold",
    "generate_insight_bundle",
    "llm_reasoning_engine",
    "presentation_report_renderer",
    "render_presentation_html",
    "run_multisource_preflight",
    "user_chain_dependency_registry",
):
    sys.modules.pop(module_name, None)

from derive_higher_order_insights import (
    build_competition_registry_index,
    build_brand_mindshare_map,
    build_brand_mindshare_judgments,
    build_competition_voc_market_split,
    build_competition_voc_xtn_breakdown,
    build_cross_source_interpretation,
    build_semantic_passages,
    build_t_jtbd_impact_stats,
    build_voc_problem_packages,
    build_x_case_signal_profiles,
    build_x_observed_positionings,
    build_x_positioning_packages,
    count_passages_for_concept,
    extract_summary_insight_cards,
    match_registry_product_entry,
)
from generate_analysis_scaffold import build_closeout_lines
import generate_insight_bundle as insight_bundle
from llm_reasoning_engine import (
    build_qual_reasoning_task_board,
    build_qual_evidence_packet,
    evaluate_candidate_claims,
    resolve_llm_profile,
    run_dual_engine_reasoning,
)
from user_chain_dependency_registry import (
    USER_CHAIN_DEPENDENCY_REGISTRY_PATH,
    build_user_chain_dependency_registry_index,
    build_user_chain_loopback_execution_plan,
    validate_user_chain_dependency_registry,
)
from render_presentation_html import (
    parse_markdown_document,
    render_report_html,
    write_html_from_markdown,
)
from generate_insight_bundle import (
    build_analysis_reflection_report,
    build_artifact_index,
    build_awe_exhibition_signals,
    build_competition_capability_scan,
    build_competition_generation_analysis,
    build_competition_matchup_matrix,
    build_competition_strategy_bridge,
    build_cleaning_robot_theme_registry,
    build_competition_thesis_tree,
    build_cross_source_convergence_tree,
    collect_user_attention_spu_ids,
    build_entry_exposure_tree,
    build_mirror_review_result,
    build_problem_drilldown_packages,
    build_portfolio_generation_strategy,
    build_presentation_tree,
    build_survey_qual_explanation_map,
    build_self_strategy_thesis,
    build_self_strategy_thesis_tree,
    build_topic_attention_matrix,
    build_user_insight_exposure_tree,
    build_user_thesis_tree,
    build_user_strategy_convergence_tree,
    build_voc_fact_exposure_tree,
    build_master_judgment_tree,
    build_presentation_page_blocks,
    merge_mirror_review_results,
    refresh_portfolio_user_chain_runtime,
    render_portfolio_ppt_report,
)


class HigherOrderInsightTests(unittest.TestCase):
    def test_parse_markdown_document_builds_heading_list_and_table_structure(self) -> None:
        markdown = """# 示例报告

## 1. 看用户

### 1.0 总览

- 第一条
- 第二条

| 列1 | 列2 |
| --- | --- |
| A | B |

#### 子卡片

普通段落，包含 `代码`。
"""
        title, root = parse_markdown_document(markdown)
        self.assertEqual(title, "示例报告")
        self.assertEqual(len(root.children), 1)
        h2 = root.children[0]
        self.assertEqual(h2.title, "1. 看用户")
        self.assertEqual(h2.children[0].title, "1.0 总览")
        overview_blocks = h2.children[0].blocks
        self.assertEqual(overview_blocks[0].block_type, "list")
        self.assertEqual(overview_blocks[1].block_type, "table")
        self.assertEqual(overview_blocks[1].headers, ["列1", "列2"])
        self.assertEqual(h2.children[0].children[0].title, "子卡片")
        self.assertEqual(h2.children[0].children[0].blocks[0].block_type, "paragraph")

    def test_render_report_html_contains_sidebar_and_table_wrapper(self) -> None:
        html_text = render_report_html(
            "# 示例报告\n\n## 1. 看用户\n\n### 1.0 总览\n\n- 证据锚点：A\n\n| 列1 | 列2 |\n| --- | --- |\n| A | B |\n\n#### N_aes 主题组：VOC-only 全主题展开\n",
            source_path="/tmp/presentation_main_report.md",
            generated_at="2026-04-01T12:00:00",
        )
        self.assertIn("<title>示例报告</title>", html_text)
        self.assertIn("目录导航", html_text)
        self.assertIn("table-wrapper", html_text)
        self.assertIn("N_aes 主题组：VOC-only 全主题展开", html_text)
        self.assertIn("证据锚点", html_text)

    def test_write_html_from_markdown_writes_single_file_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "presentation_main_report.md"
            output_path = root / "presentation_main_report.html"
            report_path.write_text(
                "# 示例报告\n\n## 1. 看用户\n\n### 1.0 总览\n\n| 系列 | 当前判断 |\n| --- | --- |\n| N_omni | 当前仍缺稳定自家 VOC 样本 |\n\n#### N_aes 主题组：VOC-only 全主题展开\n",
                encoding="utf-8",
            )
            written = write_html_from_markdown(report_path, output_path)
            self.assertEqual(written, output_path)
            self.assertTrue(output_path.exists())
            html_text = output_path.read_text(encoding="utf-8")
            self.assertIn("<html", html_text)
            self.assertIn("N_omni", html_text)
            self.assertIn("N_aes 主题组：VOC-only 全主题展开", html_text)
            self.assertIn("table-wrapper", html_text)

    def test_extract_summary_insight_cards_pulls_archetype_and_hidden_need(self) -> None:
        rows = [
            {
                "summary_case_id": "case_1",
                "case_title": "case_1",
                "study_name": "2026年1月 中国",
                "batch_market_scope": "cn",
                "period_label": "2026-01",
                "inferred_spu_id": "ecovacs_x11",
                "analysis_module_code": "user_profile",
                "analysis_module_name_cn": "用户画像",
                "canonical_section_name_cn": "用户画像",
                "section_title": "用户画像",
                "section_text": "39岁，有娃家庭，工作日很忙，希望解放双手，不想自己动手做家务。",
            },
            {
                "summary_case_id": "case_1",
                "case_title": "case_1",
                "study_name": "2026年1月 中国",
                "batch_market_scope": "cn",
                "period_label": "2026-01",
                "inferred_spu_id": "ecovacs_x11",
                "analysis_module_code": "open_discussion",
                "analysis_module_name_cn": "开放讨论与补充",
                "canonical_section_name_cn": "开放讨论与补充",
                "section_title": "开放讨论",
                "section_text": "用户会反复检查清洁结果，本质上是不信任机器，希望有可视化对比来确认结果。",
            },
        ]

        payload = extract_summary_insight_cards(rows)
        self.assertEqual(payload["card_count"], 1)
        card = payload["cards"][0]
        self.assertIn("托管减负型", card["persona_archetype"])
        self.assertIn("可确认的掌控感", card["hidden_need"])

    def test_build_cross_source_interpretation_explains_conflict_and_alignment(self) -> None:
        payload = build_cross_source_interpretation(
            consistent_issues=[["清洁效果与水痕污渍", "VOC:水渍水痕(100)", "Survey:20", "Summary:5", "2+ 源一致，建议优先关注"]],
            consistent_strengths=[],
            conflict_rows=[["多机协同与统一控制", "VOC:0", "Survey:18", "Summary:4", "其他源有信号，但 VOC 暂无明显规模性反馈"]],
            priority_rows=[["清洁效果与水痕污渍", 3, 100, 20, 5, "P1"]],
            summary_insights={},
            survey_segments={},
            voc_packages={},
        )
        interpretations = payload["interpretations"]
        self.assertTrue(any(row["alignment_type"] == "一致" for row in interpretations))
        self.assertTrue(any(row["alignment_type"] == "冲突" for row in interpretations))

    def test_build_cross_source_interpretation_prefers_accepted_hypothesis_explanation(self) -> None:
        payload = build_cross_source_interpretation(
            consistent_issues=[],
            consistent_strengths=[],
            conflict_rows=[],
            priority_rows=[["污渍问题", 3, 100, 20, 5, "P1"]],
            summary_insights={},
            survey_segments={},
            voc_packages={},
            cross_source_hypothesis_board={
                "rows": [
                    {
                        "hypothesis_id": "hypothesis::x::x",
                        "series_family": "X",
                        "user_band": "X",
                        "support_from_voc": [{"topic_name": "污渍问题"}],
                        "conflict_signals": ["不是单纯的污渍类型问题，更是结果确认感问题。"],
                        "resolution_status": "accepted",
                        "why_accepted_or_rejected": "当前定性解释已经和 VOC/问卷形成同向支撑，可以进入正式 thesis 收敛。",
                    }
                ]
            },
            judgment_acceptance_log={
                "rows": [
                    {"claim_id": "hypothesis::x::x", "frontstage_permission": True},
                ]
            },
        )
        row = payload["interpretations"][0]
        self.assertEqual(row["resolution_status"], "accepted")
        self.assertIn("同向支撑", row["best_explanation"])
        self.assertTrue(row["accepted_claim_refs"])

    def test_build_closeout_lines_handles_single_ranked_object(self) -> None:
        can_conclude, cannot_conclude, next_steps = build_closeout_lines(
            voc_rows=[{"spu_name": "X11", "negative_count": 12, "message_count": 100}],
            priority_rows=[],
            conflict_rows=[],
            support_matrix=[],
        )
        self.assertTrue(can_conclude)
        self.assertIn("X11", can_conclude[0])
        self.assertIn("对象池还不够宽", can_conclude[0])
        self.assertTrue(next_steps)

    def test_build_voc_problem_packages_groups_negative_with_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "voc.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE vw_voc_message_tag_mapped (
                    canonical_spu_id TEXT,
                    message_uid TEXT,
                    tag_name TEXT,
                    tag_sentiment TEXT,
                    topic_domain_name_cn TEXT,
                    topic_group_name_cn TEXT,
                    context_bucket_name_cn TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE voc_message (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    raw_model TEXT,
                    product_title TEXT,
                    product_url TEXT,
                    country TEXT,
                    site_country TEXT,
                    ecommerce_region TEXT,
                    platform TEXT
                )
                """
            )
            rows = [
                ("ecovacs_x11", "m1", "水渍水痕", "负面", "工况", "污渍与液体痕迹", "工况"),
                ("ecovacs_x11", "m1", "地板", "", "场景", "地面材质与覆盖物", "场景"),
                ("ecovacs_x11", "m1", "客厅", "", "场景", "空间位置", "场景"),
                ("ecovacs_x11", "m1", "拖地效果差", "负面", "能力反馈", "清洁与核心能力", None),
            ]
            conn.executemany("INSERT INTO vw_voc_message_tag_mapped VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            conn.executemany(
                "INSERT INTO voc_message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("m1", "ecovacs_x11", "X11Pro", "科沃斯 X11Pro", "https://x11", None, "中国", "国内电商", "京东"),
                ],
            )
            conn.commit()
            payload = build_voc_problem_packages(conn, ["ecovacs_x11"])
            conn.close()

        self.assertGreaterEqual(payload["package_count"], 1)
        package = next(item for item in payload["packages"] if item["negative_tag"] == "水渍水痕")
        self.assertEqual(package["damage_type"], "清洁结果受损")
        self.assertEqual(package["market_scope"], "中国")

    def test_build_competition_voc_xtn_breakdown_builds_scope_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "voc.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE voc_message (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    raw_model TEXT,
                    product_title TEXT,
                    product_url TEXT,
                    country TEXT,
                    site_country TEXT,
                    ecommerce_region TEXT,
                    platform TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE vw_voc_message_tag_mapped (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    spu_name TEXT,
                    brand_name_cn TEXT,
                    self_competitor_type TEXT,
                    platform TEXT,
                    source_data_type TEXT,
                    channel_family TEXT,
                    posted_at TEXT,
                    year_month TEXT,
                    tag_name TEXT,
                    tag_intent TEXT,
                    tag_sentiment TEXT,
                    topic_domain_code TEXT,
                    topic_domain_name_cn TEXT,
                    topic_group_code TEXT,
                    topic_group_name_cn TEXT,
                    is_context_feature INTEGER,
                    context_bucket_code TEXT,
                    context_bucket_name_cn TEXT,
                    match_confidence REAL,
                    match_method TEXT,
                    rule_version TEXT
                )
                """
            )
            voc_messages = [
                ("mx1", "ecovacs_x11", "X11Pro", "科沃斯 X11Pro", "https://x11", None, "中国", "国内电商", "京东"),
                ("mx2", "roborock_g30", "G30", "石头 G30", "https://g30", None, "中国", "国内电商", "京东"),
                ("mt1", "ecovacs_t80s", "T80S", "科沃斯 T80S", "https://t80s", None, "中国", "国内电商", "京东"),
                ("mn1", "our_brand_spun20_4b652c54", "N20", "科沃斯 N20", "https://n20", None, "中国", "国内电商", "京东"),
            ]
            conn.executemany("INSERT INTO voc_message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", voc_messages)
            mapped_rows = [
                ("mx1", "ecovacs_x11", "X11", "科沃斯", "self", "京东", "review", "ecom", "2026-03-01", "2026-03", "水渍水痕", "", "负面", "", "工况", "", "污渍与液体痕迹", 0, "", "工况", 1.0, "rule", "v1"),
                ("mx2", "roborock_g30", "G30", "石头", "competitor", "京东", "review", "ecom", "2026-03-01", "2026-03", "边角漏扫", "", "负面", "", "能力反馈", "", "清洁与核心能力", 0, "", "场景", 1.0, "rule", "v1"),
                ("mt1", "ecovacs_t80s", "T80S", "科沃斯", "self", "京东", "review", "ecom", "2026-03-01", "2026-03", "扫拖噪音大", "", "负面", "", "能力反馈", "", "噪音", 0, "", "工况", 1.0, "rule", "v1"),
                ("mn1", "our_brand_spun20_4b652c54", "N20", "科沃斯", "self", "京东", "review", "ecom", "2026-03-01", "2026-03", "滚刷缠绕", "", "负面", "", "能力反馈", "", "维护", 0, "", "关联物品", 1.0, "rule", "v1"),
            ]
            conn.executemany(
                "INSERT INTO vw_voc_message_tag_mapped VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                mapped_rows,
            )
            registry = {
                "rows": [
                    {"competition_scope": "X_omni", "brand": "科沃斯", "series_family": "X", "shape_type": "omni", "generation_bucket": "current", "product_names": ["X11"], "is_self_brand": True},
                    {"competition_scope": "X_omni", "brand": "石头", "series_family": "external", "shape_type": "omni", "generation_bucket": "current", "product_names": ["G30"], "is_self_brand": False},
                    {"competition_scope": "T_omni", "brand": "科沃斯", "series_family": "T", "shape_type": "omni", "generation_bucket": "current", "product_names": ["T80S"], "is_self_brand": True},
                    {"competition_scope": "N_single", "brand": "科沃斯", "series_family": "N", "shape_type": "single", "generation_bucket": "current", "product_names": ["N20"], "is_self_brand": True},
                ]
            }
            payload = build_competition_voc_xtn_breakdown(conn, registry)
            conn.close()

        scopes = {row["competition_scope"] for row in payload["scope_rows"]}
        self.assertIn("X_omni", scopes)
        self.assertIn("T_omni", scopes)
        self.assertIn("N_single", scopes)
        self.assertTrue(payload["level_1_rows"])
        self.assertTrue(payload["level_2_rows"])
        self.assertIn("match_confidence", payload["product_rows"][0])
        self.assertIn("frontline_scope_rows", payload)
        self.assertIn("scope_status_rows", payload)
        self.assertIn("source_db_path", payload)

    def test_build_competition_voc_xtn_breakdown_avoids_short_alias_false_positive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "voc.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE voc_message (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    raw_model TEXT,
                    product_title TEXT,
                    product_url TEXT,
                    country TEXT,
                    site_country TEXT,
                    ecommerce_region TEXT,
                    platform TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE vw_voc_message_tag_mapped (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    spu_name TEXT,
                    brand_name_cn TEXT,
                    self_competitor_type TEXT,
                    platform TEXT,
                    source_data_type TEXT,
                    channel_family TEXT,
                    posted_at TEXT,
                    year_month TEXT,
                    tag_name TEXT,
                    tag_intent TEXT,
                    tag_sentiment TEXT,
                    topic_domain_code TEXT,
                    topic_domain_name_cn TEXT,
                    topic_group_code TEXT,
                    topic_group_name_cn TEXT,
                    is_context_feature INTEGER,
                    context_bucket_code TEXT,
                    context_bucket_name_cn TEXT,
                    match_confidence REAL,
                    match_method TEXT,
                    rule_version TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO voc_message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("m1", "ecovacs_x11", "X11Pro", "科沃斯 X11Pro", "https://x11", None, "中国", "国内电商", "京东"),
            )
            conn.execute(
                "INSERT INTO vw_voc_message_tag_mapped VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("m1", "ecovacs_x11", "X11", "科沃斯", "self", "京东", "review", "ecom", "2026-03-01", "2026-03", "水渍水痕", "", "负面", "", "工况", "", "污渍与液体痕迹", 0, "", "工况", 1.0, "rule", "v1"),
            )
            registry = {
                "rows": [
                    {"competition_scope": "N_aes", "brand": "Eufy", "series_family": "external", "shape_type": "aes", "generation_bucket": "current", "product_names": ["C10"], "is_self_brand": False},
                    {"competition_scope": "X_omni", "brand": "科沃斯", "series_family": "X", "shape_type": "omni", "generation_bucket": "current", "product_names": ["X11 Pro"], "is_self_brand": True},
                ]
            }
            payload = build_competition_voc_xtn_breakdown(conn, registry)
            conn.close()

        c10_rows = [row for row in payload["product_rows"] if row["product_name"] == "C10"]
        self.assertFalse(c10_rows)

    def test_match_registry_product_entry_prefers_specific_n_aes_alias_over_aggregate_canonical(self) -> None:
        registry = {
            "rows": [
                {"competition_scope": "N_single", "brand": "科沃斯", "series_family": "N", "shape_type": "single", "generation_bucket": "previous", "product_names": ["N20"], "is_self_brand": True},
                {"competition_scope": "N_aes", "brand": "科沃斯", "series_family": "N", "shape_type": "aes", "generation_bucket": "previous", "product_names": ["N20 Plus"], "is_self_brand": True},
            ]
        }
        registry_index = build_competition_registry_index(registry)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "voc.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE voc_message (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    raw_model TEXT,
                    product_title TEXT,
                    product_url TEXT,
                    country TEXT,
                    site_country TEXT,
                    ecommerce_region TEXT,
                    platform TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO voc_message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "m1",
                    "our_brand_spun20_4b652c54",
                    "N20 Plus",
                    "ECOVACS DEEBOT N20 Plus Robot Vacuum Cleaner and Mop",
                    "https://amazon.com/example",
                    None,
                    "美国",
                    "海外电商",
                    "Amazon",
                ),
            )
            row = conn.execute("SELECT canonical_spu_id, raw_model, product_title, product_url FROM voc_message").fetchone()
            matched = match_registry_product_entry(row, registry_index)
            conn.close()

        self.assertIsNotNone(matched)
        self.assertEqual(matched["competition_scope"], "N_aes")
        self.assertTrue(matched["used_specific_alias_override"])
        self.assertEqual(matched["matched_alias_value"], "N20 Plus")

    def test_match_registry_product_entry_keeps_n20_in_n_single(self) -> None:
        registry = {
            "rows": [
                {"competition_scope": "N_single", "brand": "科沃斯", "series_family": "N", "shape_type": "single", "generation_bucket": "previous", "product_names": ["N20"], "is_self_brand": True},
                {"competition_scope": "N_aes", "brand": "科沃斯", "series_family": "N", "shape_type": "aes", "generation_bucket": "previous", "product_names": ["N20 Plus"], "is_self_brand": True},
            ]
        }
        registry_index = build_competition_registry_index(registry)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "voc.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE voc_message (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    raw_model TEXT,
                    product_title TEXT,
                    product_url TEXT,
                    country TEXT,
                    site_country TEXT,
                    ecommerce_region TEXT,
                    platform TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO voc_message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "m1",
                    "our_brand_spun20_4b652c54",
                    "N20",
                    "ECOVACS DEEBOT N20 Robot Vacuum Cleaner",
                    "https://amazon.com/example",
                    None,
                    "美国",
                    "海外电商",
                    "Amazon",
                ),
            )
            row = conn.execute("SELECT canonical_spu_id, raw_model, product_title, product_url FROM voc_message").fetchone()
            matched = match_registry_product_entry(row, registry_index)
            conn.close()

        self.assertIsNotNone(matched)
        self.assertEqual(matched["competition_scope"], "N_single")
        self.assertFalse(matched["used_specific_alias_override"])

    def test_match_registry_product_entry_ignores_t50_token_in_t80s_bundle_title(self) -> None:
        registry = {
            "rows": [
                {"competition_scope": "T_omni", "brand": "科沃斯", "series_family": "T", "shape_type": "omni", "generation_bucket": "previous", "product_names": ["T80S"], "is_self_brand": True},
                {"competition_scope": "N_omni", "brand": "科沃斯", "series_family": "N", "shape_type": "omni", "generation_bucket": "previous", "product_names": ["T50 PRO OMNI"], "is_self_brand": True},
            ]
        }
        registry_index = build_competition_registry_index(registry)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "voc.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE voc_message (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    raw_model TEXT,
                    product_title TEXT,
                    product_url TEXT,
                    country TEXT,
                    site_country TEXT,
                    ecommerce_region TEXT,
                    platform TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO voc_message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "m1",
                    "ecovacs_t80s",
                    "T80S",
                    "【政府补贴15%】科沃斯T80S/T80/T50PRO滚筒扫地洗地扫地机器人",
                    "https://tmall.com/example",
                    None,
                    "中国",
                    "国内电商",
                    "天猫",
                ),
            )
            row = conn.execute("SELECT canonical_spu_id, raw_model, product_title, product_url FROM voc_message").fetchone()
            matched = match_registry_product_entry(row, registry_index)
            conn.close()

        self.assertIsNotNone(matched)
        self.assertEqual(matched["competition_scope"], "T_omni")

    def test_build_competition_voc_xtn_breakdown_marks_external_only_scope_as_waiting_for_self_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "voc.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE voc_message (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    raw_model TEXT,
                    product_title TEXT,
                    product_url TEXT,
                    country TEXT,
                    site_country TEXT,
                    ecommerce_region TEXT,
                    platform TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE vw_voc_message_tag_mapped (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    spu_name TEXT,
                    brand_name_cn TEXT,
                    self_competitor_type TEXT,
                    platform TEXT,
                    source_data_type TEXT,
                    channel_family TEXT,
                    posted_at TEXT,
                    year_month TEXT,
                    tag_name TEXT,
                    tag_intent TEXT,
                    tag_sentiment TEXT,
                    topic_domain_code TEXT,
                    topic_domain_name_cn TEXT,
                    topic_group_code TEXT,
                    topic_group_name_cn TEXT,
                    is_context_feature INTEGER,
                    context_bucket_code TEXT,
                    context_bucket_name_cn TEXT,
                    match_confidence REAL,
                    match_method TEXT,
                    rule_version TEXT
                )
                """
            )
            voc_messages = []
            mapped_rows = []
            for i in range(30):
                message_uid = f"m{i}"
                voc_messages.append(
                    (message_uid, "xiaomi_spuh40_31bc78a1", "H40", "米家 H40", "https://h40", None, "中国", "国内电商", "京东")
                )
                mapped_rows.append(
                    (message_uid, "xiaomi_spuh40_31bc78a1", "H40", "小米", "competitor", "京东", "review", "ecom", "2026-03-01", "2026-03", "边角漏扫", "", "负面", "", "能力反馈", "", "清洁与核心能力", 0, "", "场景", 1.0, "rule", "v1")
                )
            conn.executemany("INSERT INTO voc_message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", voc_messages)
            conn.executemany(
                "INSERT INTO vw_voc_message_tag_mapped VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                mapped_rows,
            )
            registry = {
                "rows": [
                    {"competition_scope": "N_aes", "brand": "科沃斯", "series_family": "N", "shape_type": "aes", "generation_bucket": "previous", "product_names": ["N20 Plus"], "is_self_brand": True},
                    {"competition_scope": "N_aes", "brand": "小米", "series_family": "external", "shape_type": "aes", "generation_bucket": "current", "product_names": ["H40"], "is_self_brand": False},
                ]
            }
            payload = build_competition_voc_xtn_breakdown(conn, registry)
            conn.close()

        frontline_row = next(
            row
            for row in payload["frontline_scope_rows"]
            if row["competition_scope"] == "N_aes" and row["market_scope"] == "中国"
        )
        self.assertEqual(frontline_row["frontline_mode"], "external_only")
        self.assertEqual(frontline_row["top_problem_level_1"], "待补充")
        self.assertIn("外部门槛", frontline_row["voc_complaint_summary"])

    def test_build_competition_voc_xtn_breakdown_small_sample_scope_stays_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "voc.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE voc_message (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    raw_model TEXT,
                    product_title TEXT,
                    product_url TEXT,
                    country TEXT,
                    site_country TEXT,
                    ecommerce_region TEXT,
                    platform TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE vw_voc_message_tag_mapped (
                    message_uid TEXT,
                    canonical_spu_id TEXT,
                    spu_name TEXT,
                    brand_name_cn TEXT,
                    self_competitor_type TEXT,
                    platform TEXT,
                    source_data_type TEXT,
                    channel_family TEXT,
                    posted_at TEXT,
                    year_month TEXT,
                    tag_name TEXT,
                    tag_intent TEXT,
                    tag_sentiment TEXT,
                    topic_domain_code TEXT,
                    topic_domain_name_cn TEXT,
                    topic_group_code TEXT,
                    topic_group_name_cn TEXT,
                    is_context_feature INTEGER,
                    context_bucket_code TEXT,
                    context_bucket_name_cn TEXT,
                    match_confidence REAL,
                    match_method TEXT,
                    rule_version TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO voc_message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("m1", "ecovacs_t80s", "T80S", "ECOVACS T80S", "https://t80s", None, "美国", "海外电商", "Amazon"),
            )
            conn.execute(
                "INSERT INTO vw_voc_message_tag_mapped VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("m1", "ecovacs_t80s", "T80S", "科沃斯", "self", "Amazon", "review", "ecom", "2026-03-01", "2026-03", "水箱容量小", "", "负面", "", "能力反馈", "", "其他", 0, "", "工况", 1.0, "rule", "v1"),
            )
            registry = {
                "rows": [
                    {"competition_scope": "T_omni", "brand": "科沃斯", "series_family": "T", "shape_type": "omni", "generation_bucket": "previous", "product_names": ["T80S"], "is_self_brand": True},
                ]
            }
            payload = build_competition_voc_xtn_breakdown(conn, registry)
            conn.close()

        frontline_row = next(
            row
            for row in payload["frontline_scope_rows"]
            if row["competition_scope"] == "T_omni" and row["market_scope"] == "海外"
        )
        self.assertEqual(frontline_row["top_problem_level_1"], "待补充")
        self.assertEqual(frontline_row["performance_level"], "待比较")

    def test_build_competition_strategy_bridge_uses_action_language(self) -> None:
        payload = build_competition_strategy_bridge(
            {
                "frontline_scope_rows": [
                    {
                        "competition_scope": "X_omni",
                        "market_scope": "中国",
                        "frontline_mode": "self_stable",
                        "top_problem_level_1": "清洁",
                        "top_problem_level_2": "拖地留痕",
                    },
                    {
                        "competition_scope": "T_omni",
                        "market_scope": "中国",
                        "frontline_mode": "self_stable",
                        "top_problem_level_1": "清洁",
                        "top_problem_level_2": "清洁效果",
                    },
                    {
                        "competition_scope": "N_aes",
                        "market_scope": "中国",
                        "frontline_mode": "external_only",
                        "external_reference_problem_level_1": "清洁",
                        "external_reference_problem_level_2": "边角清洁效果",
                    },
                    {
                        "competition_scope": "N_aes",
                        "market_scope": "ALL",
                        "frontline_mode": "self_stable",
                        "top_problem_level_1": "其他",
                        "top_problem_level_2": "智能交互/地图",
                    },
                    {
                        "competition_scope": "N_single",
                        "market_scope": "中国",
                        "frontline_mode": "self_stable",
                        "top_problem_level_1": "智能性",
                        "top_problem_level_2": "避障能力",
                    },
                ]
            },
            {
                "rows": [
                    {"capability_dimension": "机身高度", "industry_front_runner": "追觅 / 石头", "gap_type": "跟随"},
                    {"capability_dimension": "基站自清洁", "industry_front_runner": "头部品牌", "gap_type": "待补充"},
                ]
            },
            {
                "rows": [
                    {"series_family": "X", "competition_scope": "X_omni（旗舰 omni）"},
                    {"series_family": "T", "competition_scope": "T_omni（主销 omni）"},
                    {"series_family": "N", "competition_scope": "N_aes（AES 入门带基站）"},
                ]
            },
        )
        joined = json.dumps(payload, ensure_ascii=False)
        self.assertIn("必须守住", payload["what_x_must_defend"])
        self.assertIn("智能交互/地图", payload["what_n_must_defend"])
        self.assertNotIn("N_aes/", joined)

    def test_build_competition_voc_market_split_maps_cn_and_overseas(self) -> None:
        payload = build_competition_voc_market_split(
            {
                "scope_rows": [
                    {"competition_scope": "X_omni", "series_family": "X", "market_scope": "中国", "message_count": 800, "top_problem_level_1": "清洁", "top_problem_level_2": "拖地留痕", "best_competitor_name": "石头", "lead_judgment": "x"},
                    {"competition_scope": "T_omni", "series_family": "T", "market_scope": "中国", "message_count": 700, "top_problem_level_1": "维护", "top_problem_level_2": "滚刷组件维护", "best_competitor_name": "云鲸", "lead_judgment": "t"},
                    {"competition_scope": "X_omni", "series_family": "X", "market_scope": "海外", "message_count": 650, "top_problem_level_1": "清洁", "top_problem_level_2": "边角清洁效果", "best_competitor_name": "追觅", "lead_judgment": "x_overseas"},
                    {"competition_scope": "N_aes", "series_family": "N", "market_scope": "海外", "message_count": 610, "top_problem_level_1": "噪音", "top_problem_level_2": "噪音体验", "best_competitor_name": "小米", "lead_judgment": "n_overseas"},
                ]
            }
        )
        summary = {row["market_scope"]: row for row in payload["market_summary_rows"]}
        self.assertTrue(summary["中国"]["is_stable"])
        self.assertTrue(summary["海外"]["is_stable"])

    def test_build_awe_exhibition_signals_filters_operational_noise(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docx_path = Path(temp_dir) / "awe.docx"
            xml = """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>展会整体及趋势概述</w:t></w:r></w:p>
                <w:p><w:r><w:t>扫地机行业：从参数比拼转向体验闭环，越障/超薄/蒸汽/热水/防缠继续上探。</w:t></w:r></w:p>
                <w:p><w:r><w:t>竞争对手：追觅、MOVA、石头、iRobot、萤石、友望</w:t></w:r></w:p>
                <w:p><w:r><w:t>家务机器人与具身智能值得跟踪。</w:t></w:r></w:p>
                <w:p><w:r><w:t>参观流程：提前注册，等待审核。</w:t></w:r></w:p>
              </w:body>
            </w:document>
            """
            with ZipFile(docx_path, "w") as zf:
                zf.writestr("[Content_Types].xml", "")
                zf.writestr("word/document.xml", xml)
            payload = build_awe_exhibition_signals(docx_path)

        self.assertTrue(payload["direct_competitor_signals"])
        self.assertTrue(payload["industry_capability_signals"])
        self.assertTrue(payload["cross_category_signals"])
        joined = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("参观流程", joined)

    def test_build_competition_capability_scan_uses_sparse_truth_as_v1(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "truth.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("CREATE TABLE product_master (product_id TEXT, display_name TEXT, self_competitor_type TEXT)")
            conn.execute("CREATE TABLE product_spec (product_id TEXT, spec_key TEXT, spec_value_text TEXT, spec_value_num REAL, unit TEXT)")
            conn.executemany(
                "INSERT INTO product_master VALUES (?, ?, ?)",
                [("p1", "X11", "self"), ("p2", "T80S", "self")],
            )
            conn.executemany(
                "INSERT INTO product_spec VALUES (?, ?, ?, ?, ?)",
                [("p1", "body_thickness", "超薄", 7.95, "cm"), ("p2", "cleaning_system", "恒压滚筒活水洗地", None, None)],
            )
            payload = build_competition_capability_scan(
                conn,
                {"rows": []},
                {"level_2_rows": [{"problem_level_1": "清洁", "problem_level_2": "拖地留痕"}]},
                {"industry_capability_signals": [{"signal_name": "体验闭环", "signal_text": "体验闭环"}], "cross_category_signals": []},
            )
            conn.close()

        self.assertTrue(payload["rows"])
        self.assertTrue(any(row["gap_type"] in {"跟随", "缺位", "待补充"} for row in payload["rows"]))

    def test_build_analysis_reflection_report_contains_required_fields(self) -> None:
        payload = build_analysis_reflection_report(
            {
                "frontline_scope_rows": [
                    {"competition_scope": "N_omni", "market_scope": "中国", "frontline_mode": "external_only", "status_text": "当前只有竞品池稳定样本，可讲外部门槛，但不能把它讲成科沃斯当前最伤。"},
                    {"competition_scope": "T_omni", "market_scope": "海外", "frontline_mode": "missing", "status_text": "当前该竞争带稳定 VOC 仍待补齐，先不把这条带讲满。"},
                ]
            },
            {"market_summary_rows": [{"market_scope": "中国", "is_stable": True}]},
            {"rows": [{"capability_dimension": "拖地体系", "gap_type": "守住"}]},
            {"rows": [{"competition_scope": "X_omni（旗舰 omni）"}]},
            {"what_x_must_defend": "x"},
            {"rows": [{"priority": "P0", "competition_scope": "N_omni", "target_market_scope": "中国", "reason": "补样本"}]},
        )
        for key in [
            "depth_gaps",
            "breadth_gaps",
            "abstraction_gaps",
            "ppt_style_gaps",
            "overstated_claims",
            "underused_evidence",
            "rewrite_priority_pages",
            "next_data_moves",
        ]:
            self.assertIn(key, payload)
            self.assertTrue(isinstance(payload[key], list))

    def test_build_self_strategy_thesis_returns_series_level_conclusions(self) -> None:
        payload = build_self_strategy_thesis(
            {
                "what_x_must_defend": "X 现在必须守住高端托管。",
                "what_t_must_defend": "T 现在必须把主销默认答案讲透。",
                "what_n_must_defend": "N 现在必须分开讲三条带宽。",
            },
            {
                "what_not_to_overload_into_flagship": ["多机协同", "低价守位"],
                "shape_level_not_now": ["远期场景联动"],
            },
            {
                "next_data_moves": ["P0：N_omni / 中国 -> 补样本", "P0：N_aes / 中国 -> 补样本"],
            },
        )
        self.assertIn("x_core_thesis", payload)
        self.assertIn("t_core_thesis", payload)
        self.assertIn("n_core_thesis", payload)
        self.assertTrue(payload["what_ecovacs_should_not_do"])
        self.assertTrue(payload["what_must_wait_for_data"])

    def test_build_entry_exposure_tree_marks_missing_capture_targets(self) -> None:
        payload = build_entry_exposure_tree(
            {
                "selected_spus": [{"spu_id": "ecovacs_x11", "spu_name": "X11", "brand_name_cn": "科沃斯", "self_competitor_type": "self"}],
                "support_matrix": [{"module_code": "raw", "module_name_cn": "原始访谈", "support_level": "部分支持", "primary_source": "summary", "evidence": "summary=1 group"}],
            },
            {
                "rows": [
                    {
                        "capture_id": "CAPTURE-NOMNI-CN",
                        "priority": "P0",
                        "competition_scope": "N_omni",
                        "target_market_scope": "中国",
                        "reason": "入口仍待恢复",
                    }
                ]
            },
            {
                "scope_status_rows": [
                    {"competition_scope": "N_omni", "market_scope": "中国", "frontline_mode": "external_only", "status_text": "当前只有外部门槛。"}
                ]
            },
        )
        self.assertEqual(payload["tree_type"], "exposure_tree")
        self.assertTrue(payload["stable_entry_nodes"])
        self.assertTrue(payload["missing_entry_nodes"])
        self.assertTrue(payload["weak_signal_nodes"])

    def test_build_user_insight_exposure_tree_preserves_weak_signal_and_t_placeholder(self) -> None:
        payload = build_user_insight_exposure_tree(
            {"positionings": [{"display_label": "清洁管家"}]},
            {
                "packages": [
                    {
                        "positioning_name": "清洁管家",
                        "canonical_anchor": "清洁管家",
                        "positioning_level": "main_positioning",
                        "one_line_definition": "少操心、少返工、主动补位。",
                        "support_case_titles": ["A", "B", "C"],
                        "representative_users": [{"case_title": "案例A"}],
                    },
                    {
                        "positioning_name": "科技玩家",
                        "canonical_anchor": "社交名片",
                        "positioning_level": "weak_signal",
                        "one_line_definition": "更看重科技表达。",
                        "support_case_titles": ["B"],
                        "representative_users": [{"case_title": "案例B"}],
                    },
                ]
            },
            {"cards": [{"case_title": "T案例", "role_bucket": "他们是谁"}]},
            {"rows": [{"dimension": "家庭结构", "contrast_pair": ["A", "B"], "why_different": "家庭结构不同导致判断不同。"}]},
            {
                "packages": [
                    {
                        "jtbd_name": "个人优先",
                        "result_requirement": "删掉清洁待办",
                        "unacceptable_cost": "多维护",
                        "representative_users": [{"case_title": "T案例"}],
                    }
                ]
            },
            {"series_rows": [{"series_code": "X", "lead_judgment": "X 代际差异。"}, {"series_code": "T", "lead_judgment": "T 代际差异。"}]},
            topic_attention_matrix={
                "topic_summary_rows": [
                    {
                        "series_family": "N",
                        "user_band": "N_single",
                        "cohort_scope": "科沃斯样本",
                        "market_scope": "中国",
                        "topic_name": "维护/基站",
                        "mention_count": 50,
                        "negative_count": 30,
                        "positive_count": 10,
                        "net_sentiment_signal": "负向占优",
                    },
                    {
                        "series_family": "N",
                        "user_band": "N_aes",
                        "cohort_scope": "科沃斯样本",
                        "market_scope": "海外",
                        "topic_name": "智能交互/地图",
                        "mention_count": 22,
                        "negative_count": 12,
                        "positive_count": 4,
                        "net_sentiment_signal": "负向占优",
                    }
                ]
            },
            problem_drilldown_packages={
                "rows": [
                    {
                        "series_family": "N",
                        "user_band": "N_single",
                        "cohort_scope": "科沃斯样本",
                        "market_scope": "中国",
                        "problem_name": "维护/基站",
                        "mention_count": 50,
                        "negative_profile_summary": "当前主要卡在维护。",
                    },
                    {
                        "series_family": "N",
                        "user_band": "N_aes",
                        "cohort_scope": "科沃斯样本",
                        "market_scope": "海外",
                        "problem_name": "智能交互/地图",
                        "mention_count": 22,
                        "negative_profile_summary": "当前主要卡在地图与交互。",
                    }
                ]
            },
        )
        self.assertEqual(payload["tree_type"], "exposure_tree")
        self.assertEqual(len(payload["series_nodes"]), 3)
        self.assertTrue(any(node["node_label"] == "科技玩家" for node in payload["weak_signal_nodes"]))
        self.assertTrue(any(node["node_id"] == "t_weak_signal_placeholder" for node in payload["weak_signal_nodes"]))
        self.assertTrue(any(row["series_family"] == "N" for row in payload["series_nodes"]))
        n_series = next(row for row in payload["series_nodes"] if row["series_family"] == "N")
        self.assertEqual([child["node_label"] for child in n_series["children"]], ["N_single", "N_aes", "N_omni"])

    def test_collect_user_attention_spu_ids_expands_with_n_self_products(self) -> None:
        payload = collect_user_attention_spu_ids(
            ["ecovacs_x11", "ecovacs_t80s"],
            {
                "product_rows": [
                    {
                        "series_family": "N",
                        "is_self_brand": True,
                        "canonical_spu_ids": ["our_brand_spun20_4b652c54"],
                    }
                ]
            },
        )
        self.assertIn("ecovacs_x11", payload)
        self.assertIn("ecovacs_t80s", payload)
        self.assertIn("our_brand_spun20_4b652c54", payload)

    def test_infer_user_band_prefers_specific_n_aes_alias_over_n_single_substring(self) -> None:
        self.assertEqual(
            insight_bundle.infer_user_band("N", "N20 Pro Plus", "ECOVACS DEEBOT N20 Pro Plus"),
            "N_aes",
        )
        self.assertEqual(
            insight_bundle.infer_user_band("N", "N20E Plus", "ECOVACS DEEBOT N20E Plus"),
            "N_aes",
        )
        self.assertEqual(
            insight_bundle.infer_user_band("N", "N20 Pro", "ECOVACS DEEBOT N20 Pro"),
            "N_single",
        )

    def test_build_topic_attention_matrix_captures_positive_and_negative(self) -> None:
        source_rows = [
                {
                    "message_uid": "m1",
                    "canonical_spu_id": "ecovacs_x11",
                    "raw_model": "X11",
                    "product_title": "X11",
                    "country": None,
                    "site_country": "中国",
                    "ecommerce_region": "国内电商",
                    "platform": "京东",
                    "brand_name_cn": "科沃斯",
                    "self_competitor_type": "self",
                    "tag_name": "油污",
                    "tag_sentiment": "正面",
                    "topic_domain_name_cn": "能力反馈",
                    "topic_group_name_cn": "污渍与液体痕迹",
                    "is_context_feature": 0,
                    "context_bucket_name_cn": "",
                    "content_text": "能把油污擦掉",
                },
                {
                    "message_uid": "m2",
                    "canonical_spu_id": "dreame_x50pro_track",
                    "raw_model": "X50",
                    "product_title": "X50",
                    "country": None,
                    "site_country": "中国",
                    "ecommerce_region": "国内电商",
                    "platform": "京东",
                    "brand_name_cn": "追觅",
                    "self_competitor_type": "competitor",
                    "tag_name": "水渍水痕",
                    "tag_sentiment": "负面",
                    "topic_domain_name_cn": "能力反馈",
                    "topic_group_name_cn": "污渍与液体痕迹",
                    "is_context_feature": 0,
                    "context_bucket_name_cn": "",
                    "content_text": "会留下水渍",
                },
            ]
        registry = build_cleaning_robot_theme_registry(source_rows)
        payload = build_topic_attention_matrix(source_rows, registry)
        rows = payload["rows"]
        self.assertTrue(any(row["topic_name"] == "污渍问题" for row in rows))
        ecovacs_row = next(row for row in rows if row["cohort_scope"] == "科沃斯样本")
        self.assertEqual(ecovacs_row["positive_count"], 1)
        dreame_row = next(row for row in rows if row["cohort_scope"] == "追觅样本")
        self.assertEqual(dreame_row["negative_count"], 1)

    def test_build_topic_attention_matrix_splits_n_single_and_n_aes_from_aggregate_spu(self) -> None:
        source_rows = [
            {
                "message_uid": "m1",
                "canonical_spu_id": "our_brand_spun20_4b652c54",
                "raw_model": "N20 Pro Plus",
                "product_title": "ECOVACS DEEBOT N20 Pro Plus",
                "country": None,
                "site_country": "美国",
                "ecommerce_region": "海外电商",
                "platform": "Amazon",
                "brand_name_cn": "科沃斯",
                "self_competitor_type": "self",
                "tag_name": "地图乱跑",
                "tag_sentiment": "负面",
                "topic_domain_name_cn": "能力反馈",
                "topic_group_name_cn": "智能交互与地图",
                "is_context_feature": 0,
                "context_bucket_name_cn": "",
                "content_text": "N20 Pro Plus 地图还是会乱跑",
            },
            {
                "message_uid": "m2",
                "canonical_spu_id": "our_brand_spun20_4b652c54",
                "raw_model": "N20 Pro",
                "product_title": "ECOVACS DEEBOT N20 Pro",
                "country": None,
                "site_country": "中国",
                "ecommerce_region": "国内电商",
                "platform": "京东",
                "brand_name_cn": "科沃斯",
                "self_competitor_type": "self",
                "tag_name": "滚刷缠绕",
                "tag_sentiment": "负面",
                "topic_domain_name_cn": "能力反馈",
                "topic_group_name_cn": "维护",
                "is_context_feature": 0,
                "context_bucket_name_cn": "",
                "content_text": "N20 Pro 滚刷容易缠绕",
            },
        ]
        registry = build_cleaning_robot_theme_registry(source_rows)
        payload = build_topic_attention_matrix(source_rows, registry)
        n_rows = [row for row in payload["rows"] if row["series_family"] == "N" and row["cohort_scope"] == "科沃斯样本"]
        self.assertTrue(any(row["user_band"] == "N_aes" for row in n_rows))
        self.assertTrue(any(row["user_band"] == "N_single" for row in n_rows))
        n_aes_row = next(row for row in n_rows if row["user_band"] == "N_aes")
        self.assertEqual(n_aes_row["topic_name"], "智能交互/地图")
        n_single_row = next(row for row in n_rows if row["user_band"] == "N_single")
        self.assertEqual(n_single_row["topic_name"], "维护/基站")

    def test_build_cleaning_robot_theme_registry_filters_cross_category_topics(self) -> None:
        payload = build_cleaning_robot_theme_registry(
            [
                {
                    "tag_name": "故障报警多",
                    "topic_group_name_cn": "故障与可靠性",
                    "topic_domain_name_cn": "系统与可靠性",
                    "context_bucket_name_cn": "",
                },
                {
                    "tag_name": "综合擦窗效果好",
                    "topic_group_name_cn": "综合擦窗效果",
                    "topic_domain_name_cn": "清洁能力",
                    "context_bucket_name_cn": "",
                },
            ]
        )
        rows = {row["topic_name"]: row for row in payload["rows"]}
        self.assertTrue(rows["故障与可靠性"]["is_cleaning_robot_relevant"])
        self.assertFalse(rows["综合擦窗效果"]["is_cleaning_robot_relevant"])

    def test_build_problem_drilldown_packages_breaks_down_stain_type_scene_and_expectation(self) -> None:
        source_rows = [
            {
                "message_uid": "m1",
                "canonical_spu_id": "ecovacs_x11",
                "raw_model": "X11",
                "product_title": "X11",
                "country": None,
                "site_country": "中国",
                "ecommerce_region": "国内电商",
                "platform": "京东",
                "brand_name_cn": "科沃斯",
                "self_competitor_type": "self",
                "tag_name": "水渍水痕",
                "tag_sentiment": "负面",
                "topic_domain_name_cn": "能力反馈",
                "topic_group_name_cn": "污渍与液体痕迹",
                "is_context_feature": 0,
                "context_bucket_name_cn": "",
                "content_text": "地板上有水印",
            },
            {
                "message_uid": "m1",
                "canonical_spu_id": "ecovacs_x11",
                "raw_model": "X11",
                "product_title": "X11",
                "country": None,
                "site_country": "中国",
                "ecommerce_region": "国内电商",
                "platform": "京东",
                "brand_name_cn": "科沃斯",
                "self_competitor_type": "self",
                "tag_name": "地板",
                "tag_sentiment": "",
                "topic_domain_name_cn": "场景",
                "topic_group_name_cn": "地面材质与覆盖物",
                "is_context_feature": 1,
                "context_bucket_name_cn": "场景",
                "content_text": "地板上有水印",
            },
            {
                "message_uid": "m1",
                "canonical_spu_id": "ecovacs_x11",
                "raw_model": "X11",
                "product_title": "X11",
                "country": None,
                "site_country": "中国",
                "ecommerce_region": "国内电商",
                "platform": "京东",
                "brand_name_cn": "科沃斯",
                "self_competitor_type": "self",
                "tag_name": "油污",
                "tag_sentiment": "正面",
                "topic_domain_name_cn": "能力反馈",
                "topic_group_name_cn": "污渍与液体痕迹",
                "is_context_feature": 0,
                "context_bucket_name_cn": "",
                "content_text": "油污能擦掉",
            },
        ]
        registry = build_cleaning_robot_theme_registry(source_rows)
        attention = build_topic_attention_matrix(source_rows, registry)
        payload = build_problem_drilldown_packages(
            source_rows,
            attention,
            {
                "cases": [
                    {
                        "series_code": "X",
                        "expected_needs": ["希望一次拖净不留痕"],
                        "concept_ideas": ["顽固污渍重点处理"],
                        "core_demand": [],
                        "pain_points": [],
                    }
                ]
            },
            registry,
        )
        self.assertTrue(payload["rows"])
        row = payload["rows"][0]
        self.assertEqual(row["problem_name"], "污渍问题")
        self.assertTrue(row["type_breakdown"])
        self.assertTrue(row["scene_breakdown"])
        self.assertTrue(row["effect_expectation_breakdown"])

    def test_build_problem_drilldown_packages_supports_long_tail_topic_template(self) -> None:
        source_rows = [
            {
                "message_uid": "m1",
                "canonical_spu_id": "ecovacs_x11",
                "raw_model": "X11",
                "product_title": "X11",
                "country": None,
                "site_country": "中国",
                "ecommerce_region": "国内电商",
                "platform": "京东",
                "brand_name_cn": "科沃斯",
                "self_competitor_type": "self",
                "tag_name": "故障报警多",
                "tag_sentiment": "负面",
                "topic_domain_name_cn": "系统与可靠性",
                "topic_group_name_cn": "故障与可靠性",
                "is_context_feature": 0,
                "context_bucket_name_cn": "",
                "content_text": "经常报警，更新后异常",
            },
            {
                "message_uid": "m1",
                "canonical_spu_id": "ecovacs_x11",
                "raw_model": "X11",
                "product_title": "X11",
                "country": None,
                "site_country": "中国",
                "ecommerce_region": "国内电商",
                "platform": "京东",
                "brand_name_cn": "科沃斯",
                "self_competitor_type": "self",
                "tag_name": "地板",
                "tag_sentiment": "",
                "topic_domain_name_cn": "场景",
                "topic_group_name_cn": "地面材质与覆盖物",
                "is_context_feature": 1,
                "context_bucket_name_cn": "场景",
                "content_text": "经常报警，更新后异常",
            },
        ]
        registry = build_cleaning_robot_theme_registry(source_rows)
        attention = build_topic_attention_matrix(source_rows, registry)
        payload = build_problem_drilldown_packages(
            source_rows,
            attention,
            {
                "cases": [
                    {
                        "series_code": "X",
                        "expected_needs": ["希望稳定运行少报警"],
                        "concept_ideas": ["更新后别出问题"],
                        "core_demand": [],
                        "pain_points": [],
                    }
                ]
            },
            registry,
        )
        row = next(item for item in payload["rows"] if item["problem_name"] == "故障与可靠性")
        self.assertTrue(row["effect_expectation_breakdown"])
        self.assertEqual(row["next_drilldown_axis"], "类型")

    def test_build_survey_qual_explanation_map_links_people_and_sensitive_problems(self) -> None:
        payload = build_survey_qual_explanation_map(
            {
                "cases": [
                    {
                        "series_code": "X",
                        "case_title": "案例A",
                        "inferred_spu_id": "ecovacs_x11",
                        "expected_needs": ["希望一次拖净不留痕"],
                        "concept_ideas": [],
                        "core_demand": [],
                        "pain_points": ["不接受水渍"],
                        "cleaning_attitude": ["能接受80%不行"],
                    }
                ]
            },
            {"segments": []},
            {"segments": []},
            {
                "packages": [
                    {
                        "positioning_name": "清洁管家",
                        "pain_need": ["不接受水渍"],
                        "buying_logic": ["要少返工"],
                        "one_line_definition": "少操心",
                        "representative_users": [{"case_title": "案例A"}],
                    }
                ]
            },
            {"packages": []},
            {"rows": [{"series_family": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "污渍问题", "negative_count": 10, "mention_count": 20}]},
            {"rows": []},
            {"rows": [{"topic_name": "污渍问题", "is_cleaning_robot_relevant": True}]},
        )
        self.assertTrue(payload["rows"])
        self.assertIn("污渍问题", payload["rows"][0]["sensitive_problems"])
        self.assertIn("topic_rows", payload)

    def test_build_survey_qual_explanation_map_adds_topic_rows(self) -> None:
        payload = build_survey_qual_explanation_map(
            {"cases": []},
            {"segments": []},
            {"segments": []},
            {"packages": []},
            {"packages": []},
            {
                "rows": [
                    {"series_family": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "故障与可靠性", "negative_count": 10, "mention_count": 20},
                    {"series_family": "T", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "续航与充电", "negative_count": 4, "mention_count": 10},
                    {"series_family": "N", "user_band": "N_single", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "维护/基站", "negative_count": 12, "mention_count": 18},
                    {"series_family": "N", "user_band": "N_aes", "cohort_scope": "科沃斯样本", "market_scope": "海外", "topic_name": "智能交互/地图", "negative_count": 8, "mention_count": 14},
                ]
            },
            {
                "rows": [
                    {"problem_name": "故障与可靠性", "series_family": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "reasonableness_judgment": "可靠性是底线。", "negative_profile_summary": "负向画像", "positive_profile_summary": "正向画像", "effect_expectation_breakdown": [{"label": "稳定运行少报警"}]},
                    {"problem_name": "续航与充电", "series_family": "T", "cohort_scope": "科沃斯样本", "market_scope": "中国", "reasonableness_judgment": "续航影响全屋完成率。", "negative_profile_summary": "负向画像", "positive_profile_summary": "正向画像", "effect_expectation_breakdown": [{"label": "一次覆盖全屋少中断"}]},
                    {"problem_name": "维护/基站", "series_family": "N", "user_band": "N_single", "cohort_scope": "科沃斯样本", "market_scope": "中国", "reasonableness_judgment": "维护是预算守位底线。", "negative_profile_summary": "滚刷维护会直接破坏守位。", "positive_profile_summary": "基础维护底线已经能成立。", "effect_expectation_breakdown": [{"label": "少缠绕少手洗"}], "counter_examples": ["当前缺少稳定反例"]},
                    {"problem_name": "智能交互/地图", "series_family": "N", "user_band": "N_aes", "cohort_scope": "科沃斯样本", "market_scope": "海外", "reasonableness_judgment": "地图与交互会直接决定入门带基站是否可用。", "negative_profile_summary": "地图乱跑会直接打穿承接位。", "positive_profile_summary": "基础交互已经能成立。", "effect_expectation_breakdown": [{"label": "地图稳定少犯傻"}], "counter_examples": ["当前缺少稳定反例"]},
                ]
            },
            {"rows": [{"topic_name": "故障与可靠性", "is_cleaning_robot_relevant": True}, {"topic_name": "续航与充电", "is_cleaning_robot_relevant": True}, {"topic_name": "维护/基站", "is_cleaning_robot_relevant": True}, {"topic_name": "智能交互/地图", "is_cleaning_robot_relevant": True}]},
        )
        self.assertTrue(payload["topic_rows"])
        topics = {row["topic_name"] for row in payload["topic_rows"]}
        self.assertIn("故障与可靠性", topics)
        self.assertIn("续航与充电", topics)
        n_single_row = next(row for row in payload["topic_rows"] if row.get("user_band") == "N_single")
        self.assertEqual(n_single_row["explanation_mode"], "voc_only")
        self.assertEqual(n_single_row["evidence_status"], "voc_only")
        n_omni_row = next(row for row in payload["topic_rows"] if row.get("user_band") == "N_omni")
        self.assertEqual(n_omni_row["explanation_mode"], "boundary")
        self.assertEqual(n_omni_row["evidence_status"], "boundary")

    def test_build_user_thesis_tree_turns_attention_and_drilldown_into_series_claims(self) -> None:
        payload = build_user_thesis_tree(
            {"not_ready_nodes": [{"lead_judgment": "表达型机会仍待观察"}]},
            {
                "rows": [
                    {"series_family": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "污渍问题", "mention_count": 20, "mention_rate": 0.2, "positive_count": 5, "negative_count": 10, "positive_rate": 0.25, "negative_rate": 0.5},
                    {"series_family": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "维护/基站", "mention_count": 10, "mention_rate": 0.1, "positive_count": 8, "negative_count": 2, "positive_rate": 0.8, "negative_rate": 0.2},
                    {"series_family": "T", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "边角问题", "mention_count": 18, "mention_rate": 0.18, "positive_count": 3, "negative_count": 9, "positive_rate": 0.17, "negative_rate": 0.5},
                    {"series_family": "T", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "噪音", "mention_count": 8, "mention_rate": 0.08, "positive_count": 6, "negative_count": 1, "positive_rate": 0.75, "negative_rate": 0.12},
                ]
            },
            {"rows": [{"problem_name": "污渍问题", "cohort_scope": "科沃斯样本", "series_family": "X", "effect_expectation_breakdown": [], "reasonableness_judgment": "需要继续补定性。"}]},
        )
        self.assertEqual(payload["tree_type"], "thesis_tree")
        self.assertIn("X 当前用户主命题", payload["x_core_thesis"])
        self.assertTrue(payload["what_users_care_most"])

    def test_build_mirror_review_result_and_merge_support_dual_review_loop(self) -> None:
        report = """
        ## 0. 问题回答
        - 当前节点：这份报告要回答什么。
        - 当前最核心的结论是污渍问题与边角问题。
        - 数据上已经能看到提及率、占比和例数。
        ## 1. 看用户
        - 为什么重要：这会影响当前决策。
        ## 5. 缺口 / 风险 / 下一步
        - 下一步动作：继续补 gap 与优先级。
        - 机制闭环：围绕阶段路径和承接动作推进。
        """
        david = build_mirror_review_result(target_person="David", material_title="report", material_content=report)
        qiandong = build_mirror_review_result(target_person="钱董", material_title="report", material_content=report)
        merged = merge_mirror_review_results([david, qiandong])
        self.assertIn("overall_score", david)
        self.assertIn("pass_status", qiandong)
        self.assertIn("blocking_actions", merged)
        self.assertIn("matched_strengths", merged)

    def test_build_voc_fact_exposure_tree_separates_signal_external_and_missing(self) -> None:
        payload = build_voc_fact_exposure_tree(
            {
                "packages": [
                    {
                        "package_name": "水渍问题包",
                        "negative_tag": "水渍水痕",
                        "problem_level_1": "清洁",
                        "problem_level_2": "拖地留痕",
                        "message_count": 50,
                        "competition_scope": "X_omni",
                        "market_scope": "中国",
                    }
                ]
            },
            {
                "frontline_scope_rows": [
                    {
                        "competition_scope": "N_aes",
                        "market_scope": "中国",
                        "frontline_mode": "external_only",
                        "voc_complaint_summary": "当前只有外部门槛。",
                        "external_reference_problem_level_2": "边角清洁效果",
                    },
                    {
                        "competition_scope": "T_omni",
                        "market_scope": "海外",
                        "frontline_mode": "missing",
                        "status_text": "当前稳定 VOC 仍待补齐。",
                    },
                ],
                "scope_status_rows": [
                    {
                        "competition_scope": "T_omni",
                        "market_scope": "海外",
                        "frontline_mode": "missing",
                        "self_message_count": 1,
                        "external_message_count": 0,
                    }
                ],
            },
        )
        self.assertTrue(payload["signal_nodes"])
        self.assertTrue(payload["external_only_nodes"])
        self.assertTrue(payload["missing_scope_nodes"])
        self.assertTrue(payload["weak_signal_nodes"])

    def test_build_judgment_trees_chain_user_competition_and_self(self) -> None:
        user_convergence = build_user_strategy_convergence_tree(
            {
                "weak_signal_nodes": [{"summary": "表达型信号仍偏弱。"}],
            },
            {
                "series_rows": [
                    {"series_code": "X", "difference_reason_clusters": ["基础代劳 vs 低介入托管"]},
                    {"series_code": "T", "difference_reason_clusters": ["替代 vs 分担"]},
                ]
            },
            {
                "packages": [
                    {"positioning_name": "清洁帮手", "positioning_level": "main_positioning"},
                    {"positioning_name": "清洁管家", "positioning_level": "main_positioning"},
                ]
            },
            {
                "packages": [
                    {"jtbd_name": "个人优先"},
                    {"jtbd_name": "家庭投入"},
                ]
            },
        )
        cross_source = build_cross_source_convergence_tree(
            {"interpretations": [{"theme_name": "清洁底线"}]},
            {"series_rows": [{"series_code": "X", "proof_points": ["托管"]}, {"series_code": "T", "proof_points": ["稳定"]}]},
            {"not_now": ["表达型机会先别讲满"]},
            {"frontline_scope_rows": [{"competition_scope": "N_omni", "frontline_mode": "missing", "status_text": "待补数"}]},
        )
        competition_thesis = build_competition_thesis_tree(
            {"rows": [{"capability_dimension": "机身高度", "why_it_matters": "更像托管门槛"}, {"capability_dimension": "免维护", "why_it_matters": "更像默认答案门槛"}]},
            {"rows": [{"series_family": "N", "voc_risk_to_watch": "下探风险"}]},
            {"market_rows": [{"market_scope": "中国"}]},
            {
                "what_x_must_defend": "X 必须守住高端托管。",
                "what_t_must_defend": "T 必须守住主销默认答案。",
                "what_n_must_defend": "N 必须守住带宽完整度。",
            },
        )
        self_tree = build_self_strategy_thesis_tree(
            {
                "x_core_thesis": "X thesis",
                "t_core_thesis": "T thesis",
                "n_core_thesis": "N thesis",
                "what_ecovacs_should_not_do": ["不要乱塞"],
                "what_must_wait_for_data": ["P0：N_omni / 中国 -> 补样本"],
                "what_current_report_can_already_decide": ["X 可以定"],
            },
            {},
            cross_source,
            {"rows": [{"competition_scope": "N_omni"}]},
        )
        master = build_master_judgment_tree(user_convergence, competition_thesis, self_tree)
        presentation = build_presentation_tree(
            {"summary_judgment": "先暴露再收敛。"},
            user_convergence,
            competition_thesis,
            self_tree,
            {"summary_judgment": "还差补数。"},
        )
        self.assertEqual(cross_source["tree_type"], "convergence_tree")
        self.assertEqual(competition_thesis["tree_type"], "thesis_tree")
        self.assertEqual(self_tree["tree_type"], "thesis_tree")
        self.assertIn("root_thesis", master)
        self.assertEqual(presentation["tree_type"], "presentation_tree")
        self.assertTrue(presentation["chapter_nodes"])

    def test_render_portfolio_ppt_report_uses_gap_and_appendix_structure(self) -> None:
        report = render_portfolio_ppt_report(
            category_name="扫地机器人",
            time_scope="2025H2-2026Q1",
            market="ALL",
            analysis_goal_text="回答核心问题",
            style_profile={"banned_phrases": []},
            higher_order_artifacts={
                "series_positioning": {"series_rows": [{"series_code": "X", "positioning_label": "清洁帮手"}, {"series_code": "T", "positioning_label": "个人优先"}]},
                "strategy_translation": {
                    "priority_buckets": {
                        "底线问题": ["清洁效果与水痕污渍", "噪音体验", "边角与覆盖率", "智能/App/语音/地图"],
                        "先不讲满": ["多机协同与统一控制", "维护与基站操作", "避障越障与卡困"],
                    },
                    "priority_reasoning": ["先做那些已经在多个来源同时出现、并且会伤害清洁结果或托管信任的问题。"],
                    "value_pillar_candidates": [
                        {"pillar_name": "省心托管", "why": "高频问题最后都在伤害用户对“能不能放心交给它”的判断。"},
                        {"pillar_name": "科技表达", "why": "科技表达真实存在，但当前更像高价值用户的加分项。"},
                    ],
                    "top_problem_packages": [],
                },
                "generation_comparison": {"series_rows": []},
                "presentation_page_blocks": {
                    "blocks": [
                        {"page_id": "competition_intro_pages", "heading": "## 2. 看竞争", "lead_judgment": "看竞争", "supporting_table": {}},
                        {"page_id": "competition_thesis_pages", "heading": "### 2.1 竞争母题：先看行业真正的三条压力线", "lead_judgment": "竞争母题", "supporting_table": {}},
                        {"page_id": "competition_capability_scan_pages", "heading": "#### 行业能力扫描及洞察", "lead_judgment": "能力扫描", "supporting_table": {}},
                        {"page_id": "competition_matchup_pages", "heading": "#### 核心竞品对阵", "lead_judgment": "对阵", "supporting_table": {}},
                        {"page_id": "competition_conclusion_pages", "heading": "#### 竞争结论：X/T/N（三带）现在各自该防什么", "lead_judgment": "竞争结论", "supporting_table": {}},
                        {"page_id": "self_value_pages", "heading": "## 3. 看自己", "lead_judgment": "看自己", "supporting_table": {}},
                        {"page_id": "self_portfolio_bandwidth_pages", "heading": "#### 科沃斯当前产品带宽与系列分工", "lead_judgment": "产品带宽", "supporting_table": {}},
                        {"page_id": "self_demand_reorder_pages", "heading": "#### 需求池如何被重排", "lead_judgment": "需求重排", "supporting_table": {}},
                        {"page_id": "priority_strategy_pages", "heading": "## 4. 需求优先级讨论", "lead_judgment": "优先级", "supporting_table": {}},
                        {"page_id": "priority_assignment_pages", "heading": "#### X/T/N 分工与承接边界", "lead_judgment": "承接边界", "supporting_table": {}},
                        {"page_id": "reflection_intro_pages", "heading": "## 5. 缺口 / 风险 / 下一步", "lead_judgment": "缺口", "supporting_table": {}},
                        {"page_id": "analysis_reflection_pages", "heading": "#### 当前这份分析还差什么", "lead_judgment": "分析反思", "supporting_table": {}},
                        {"page_id": "data_moves_pages", "heading": "#### 当前必须补什么", "lead_judgment": "补数动作", "supporting_table": {}},
                        {"page_id": "roadmap_action_pages", "heading": "#### 当前动作 / 路线图", "lead_judgment": "路线图", "supporting_table": {}},
                    ]
                },
                "x_positioning_packages": {"packages": []},
                "t_series_concept_map": {},
                "master_judgment_tree": {
                    "summary_judgment": "总判断",
                    "root_thesis": "root thesis",
                    "branches": [
                        {"branch_name": "用户为什么这么判断", "lead_judgment": "用户判断分成 X / T / N 三条线。"},
                        {"branch_name": "竞争真正卷什么", "lead_judgment": "竞争真正卷的是结果信任和托管信任。"},
                        {"branch_name": "科沃斯为什么必须这么分工", "lead_judgment": "科沃斯必须按 X / T / N 分工。"},
                    ],
                },
                "presentation_tree": {"summary_judgment": "先给结论，再区分边界。"},
                "user_strategy_convergence_tree": {
                    "converged_nodes": [
                        {
                            "concept_name": "X 为什么会分成 清洁管家 / 清洁帮手",
                            "lead_judgment": "X 现在稳定分成清洁管家和清洁帮手。",
                            "why_converged": "基础代劳与低介入托管两条判断都已稳定出现。",
                            "why_not_other": "表达型信号还不足以并列成主定位。",
                        },
                        {
                            "concept_name": "T 为什么不是一个总 archetype，而是几类 JTBD",
                            "lead_judgment": "T 现在更像几类 JTBD 的集合。",
                            "why_converged": "不同人生位置会把清洁重新定义成替代、分担或保障。",
                            "why_not_other": "如果先压成总人设，就会把不同清洁意义讲扁。",
                        },
                    ],
                    "contested_nodes": [
                        {
                            "concept_name": "N 为什么不能先压成一个总用户 archetype",
                            "lead_judgment": "N 当前更适合收成三条带宽分工，而不是一个总 N。",
                            "why_converged": "N_single、N_aes、N_omni 的样本完整度和承接意义都不同。",
                            "why_not_other": "如果直接压成一个总 N，会把三条带混讲。",
                        }
                    ],
                    "not_ready_nodes": [
                        {
                            "concept_name": "哪些仍只能保留为方向性信号",
                            "lead_judgment": "科技表达当前更像方向性加分项，不是稳定主定位。",
                        }
                    ],
                },
                "user_thesis_tree": {
                    "x_core_thesis": "X 要把低介入托管讲成可信答案。",
                    "t_core_thesis": "T 要把结果更稳、少返工、少维护讲成主销默认答案。",
                    "n_band_theses": {
                        "N_single": "N_single 更像预算守位带。",
                        "N_aes": "N_aes 当前主要停在海外 / ALL 口径。",
                        "N_omni": "N_omni 当前只能保留为边界判断。",
                    },
                },
                "cross_source_interpretation": {
                    "interpretations": [
                        {"theme_name": "清洁效果与水痕污渍", "best_explanation": "它最后伤害的是清洁结果信任。", "resolution_status": "accepted", "next_validation_step": "可以直接进入优先级讨论与策略翻译。"},
                        {"theme_name": "边角与覆盖率", "best_explanation": "它真正伤的是工作完成率与是否还要人工补扫。", "resolution_status": "accepted", "next_validation_step": "可以直接进入优先级讨论与策略翻译。"},
                        {"theme_name": "噪音体验", "best_explanation": "它会压缩机器可用时窗。", "resolution_status": "accepted", "next_validation_step": "优先补第三源，确认它是稳定结论还是阶段性放大。"},
                        {"theme_name": "智能/App/语音/地图", "best_explanation": "它会放大用户对机器聪不聪明的判断。", "resolution_status": "accepted", "next_validation_step": "优先补第三源，确认它是稳定结论还是阶段性放大。"},
                        {"theme_name": "维护与基站操作", "best_explanation": "这类问题更像期待型判断或小样本模式洞察。", "resolution_status": "contested", "next_validation_step": "其他源有信号，但 VOC 暂无明显规模性反馈"},
                        {"theme_name": "避障越障与卡困", "best_explanation": "这类问题更像低频极端工况。", "resolution_status": "contested", "next_validation_step": "其他源有信号，但 VOC 暂无明显规模性反馈"},
                        {"theme_name": "多机协同与统一控制", "best_explanation": "这类问题更像远期机会层。", "resolution_status": "contested", "next_validation_step": "其他源有信号，但 VOC 暂无明显规模性反馈"},
                    ]
                },
                "brand_mindshare_map": {
                    "brands": {
                        "科沃斯": {
                            "trust_reason": ["科沃斯：智能化技术先进。", "科沃斯：扫地机专业。"],
                            "rejection_reason": ["科沃斯：机器好看。", "科沃斯：体验差，靠后。"],
                        }
                    }
                },
                "brand_mindshare_judgments": {
                    "judgments": [
                        {
                            "brand": "科沃斯",
                            "one_line_label": "老牌大厂，品牌认知高，但口碑会随着具体产品体验明显分化。",
                            "why_choose": ["科沃斯：智能化技术先进。", "科沃斯：扫地机专业。"],
                            "why_reject": ["科沃斯：机器好看。", "科沃斯：体验差，靠后。"],
                        }
                    ]
                },
                "idea_cluster_judgments": {
                    "judgments": [
                        {
                            "theme": "低介入",
                            "now_or_later": "现在就该做",
                            "why_now": "这类想法已经直接贴近当前痛点和完成率问题。",
                        },
                        {
                            "theme": "生态联动",
                            "now_or_later": "更适合中长期布局",
                            "why_now": "这类能力更适合作为后续的差异化加分项。",
                        },
                    ]
                },
                "voc_fact_exposure_tree": {
                    "signal_nodes": [{"node_label": "稳定问题", "summary": "已形成稳定问题包。"}],
                    "external_only_nodes": [
                        {"node_label": "N_aes（AES 入门带基站） / 中国", "summary": "当前只有竞品池稳定样本，不能把它讲成科沃斯当前最伤。"},
                        {"node_label": "N_omni（omni 下探） / 中国", "summary": "当前只有竞品池稳定样本，不能把它讲成科沃斯当前最伤。"},
                    ],
                    "missing_scope_nodes": [
                        {"node_label": "T_omni（主销 omni） / 海外", "summary": "当前该竞争带稳定 VOC 仍待补齐，先不把这条带讲满。"},
                    ],
                },
                "analysis_reflection_report": {
                    "market_summary_rows": [
                        {"market_scope": "中国", "status_text": "稳定，可进入正式并列页"},
                        {"market_scope": "海外", "status_text": "稳定，可进入正式并列页"},
                    ],
                    "breadth_gaps": ["N_aes / 中国 当前还不能讲满。", "N_omni / 中国 当前还不能讲满。"],
                    "next_data_moves": ["P0：N_omni / 中国", "P0：N_aes / 中国", "P1：T_omni / 海外"],
                },
                "qual_evidence_packet": {
                    "packets": [
                        {"user_band": "X"},
                        {"user_band": "X"},
                        {"user_band": "T"},
                        {"user_band": "N_single"},
                        {"user_band": "N_aes"},
                        {"user_band": "N_omni"},
                    ]
                },
                "self_strategy_thesis_tree": {
                    "thesis_nodes": [
                        {
                            "series_family": "X",
                            "root_claim": "X 要把高端托管承诺讲成可信答案。",
                            "why_this_is_the_role": "X 当前要承接的是高端托管承诺。",
                            "what_not_to_do": "不要再把下探守位和远期协同压回旗舰。",
                            "must_wait_for_data": "P0：N_omni / 中国",
                        },
                        {
                            "series_family": "T",
                            "root_claim": "T 要把结果更稳、少返工、少维护讲成主销默认答案。",
                            "why_this_is_the_role": "T 当前要承接的是主销默认答案。",
                            "what_not_to_do": "不要把主销 omni 讲成旗舰黑科技堆料战。",
                            "must_wait_for_data": "P0：N_aes / 中国",
                        },
                        {
                            "series_family": "N",
                            "root_claim": "N 要拆成 omni 下探 / AES / 单机三条带分别承接。",
                            "why_this_is_the_role": "N 当前要回答的是三条下探带宽分别由谁承接。",
                            "what_not_to_do": "不要继续让 X/T 代替 N 说话。",
                            "must_wait_for_data": "-",
                        },
                    ]
                },
                "competition_thesis_tree": {
                    "thesis_nodes": [
                        {
                            "thesis_name": "高端托管门槛",
                            "root_claim": "X 必须守住高端托管承诺。",
                            "why_this_is_the_bar": "超薄与拖地结果已经成门槛。",
                            "what_not_to_confuse": "别把高端竞争讲成参数堆料战。",
                            "scope_refs": ["X_omni"],
                        },
                        {
                            "thesis_name": "主销结果稳定门槛",
                            "root_claim": "T 必须把结果稳定讲成默认答案。",
                            "why_this_is_the_bar": "越障和免维护已经成门槛。",
                            "what_not_to_confuse": "别把主销 omni 讲成高端黑科技战。",
                            "scope_refs": ["T_omni"],
                        },
                        {
                            "thesis_name": "下探带宽完整度门槛",
                            "root_claim": "N 必须回答下探带宽完整度问题。",
                            "why_this_is_the_bar": "下探承接与带基站守位都已经被竞品卡位。",
                            "what_not_to_confuse": "别把 N 当成一个总桶。",
                            "scope_refs": ["N_omni", "N_aes", "N_single"],
                        },
                    ],
                    "market_refs": [
                        {"competition_scope": "X_omni", "frontline_mode": "self_stable"},
                        {"competition_scope": "T_omni", "frontline_mode": "self_stable"},
                        {"competition_scope": "N_omni", "frontline_mode": "external_only"},
                        {"competition_scope": "N_aes", "frontline_mode": "external_only"},
                        {"competition_scope": "N_single", "frontline_mode": "self_stable"},
                    ],
                },
                "competition_matchup_matrix": {
                    "rows": [
                        {
                            "competition_scope": "X_omni（旗舰 omni）",
                            "competitor_product_name": "G30S Pro",
                            "headline_capabilities": "高端旗舰要正面回答托管承诺能不能兑现。",
                            "why_this_matchup": "X 真正对的是旗舰 omni 的高端托管承诺。",
                            "voc_risk_to_watch": "清洁/拖地留痕",
                        },
                        {
                            "competition_scope": "T_omni（主销 omni）",
                            "competitor_product_name": "P20 活水版",
                            "headline_capabilities": "主销 omni 要讲结果稳定与少维护。",
                            "why_this_matchup": "T 真正对的是主销 omni 的默认答案之战。",
                            "voc_risk_to_watch": "清洁/拖地留痕",
                        },
                        {
                            "competition_scope": "N_omni（omni 下探）",
                            "competitor_product_name": "P20",
                            "headline_capabilities": "omni 下探带重点讲承接位是否完整。",
                            "why_this_matchup": "N_omni 真正面对的是中高端下探卡位。",
                            "voc_risk_to_watch": "当前该竞争带稳定 VOC 仍待补齐",
                        },
                        {
                            "competition_scope": "N_aes（AES 入门带基站）",
                            "competitor_product_name": "H40",
                            "headline_capabilities": "AES 入门带基站重点讲承接是否完整。",
                            "why_this_matchup": "N_aes 真正对的是入门带基站守位战。",
                            "voc_risk_to_watch": "其他/智能交互/地图",
                        },
                        {
                            "competition_scope": "N_single（低价单机守位）",
                            "competitor_product_name": "3C增强版",
                            "headline_capabilities": "低价单机守位重点讲基础完成率。",
                            "why_this_matchup": "N_single 真正对的是低价守位。",
                            "voc_risk_to_watch": "噪音/噪音体验",
                        },
                    ]
                },
                "portfolio_generation_strategy": {
                    "shape_level_not_now": ["多机协同", "统一生态", "远期场景联动"],
                    "portfolio_bandwidth_rows": [
                        {
                            "series_family": "X",
                            "must_carry": "把高端旗舰的托管承诺和高价值体验讲透。",
                            "must_not_carry": "不要继续替 N 扛下探守位。",
                            "portfolio_gap": "一旦把下探守位压进 X，高端叙事会被拖散。",
                        },
                        {
                            "series_family": "T",
                            "must_carry": "把结果更稳、少返工、少维护讲成主销核心动作。",
                            "must_not_carry": "不要替 N 去补带宽空档。",
                            "portfolio_gap": "如果 T 承担过多非主销任务，主线会被说散。",
                        },
                        {
                            "series_family": "N",
                            "must_carry": "把入门带基站承接位补齐。",
                            "portfolio_gap": "如果 AES 承接断档，入门带基站需求会被竞品截走。",
                        },
                        {
                            "series_family": "N",
                            "must_carry": "把 omni 下探带讲成独立承接位。",
                            "portfolio_gap": "如果 omni 下探混进 X/T 叙事，旗舰和主销都会被迫补位。",
                        },
                        {
                            "series_family": "N",
                            "must_carry": "守住低价单机基本盘。",
                            "portfolio_gap": "如果单机守位缺失，预算敏感用户会更早流走。",
                        },
                    ],
                },
            },
        )
        self.assertIn("## 0. 执行摘要", report)
        self.assertIn("## 1. 结论适用范围", report)
        self.assertIn("## 2. 看用户", report)
        self.assertIn("### 2.0 用户根判断", report)
        self.assertIn("### 2.1 X / T / N 总对比表", report)
        self.assertIn("### 2.2 系列判断表", report)
        self.assertIn("### 2.3 关键问题证据表", report)
        self.assertIn("### 2.4 问题下钻表", report)
        self.assertIn("### 2.5 边界与不能讲满", report)
        self.assertIn("### 2.6 真缺口与补数动作", report)
        self.assertIn("### 2.7 本章小结", report)
        self.assertIn("## 3. 看竞争", report)
        self.assertIn("### 3.1 竞争门槛总表", report)
        self.assertIn("### 3.2 竞争带总对比表", report)
        self.assertIn("### 3.4 本章小结", report)
        self.assertIn("## 4. 看自己", report)
        self.assertIn("### 4.1 系列角色与不做清单", report)
        self.assertIn("### 4.2 本章小结", report)
        self.assertIn("## 5. 真缺口与补数计划", report)
        self.assertIn("## 6. 最终结论", report)
        self.assertIn("## 附：数据口径与备查表", report)
        self.assertIn("| 一级判断 | 当前结论 | 核心依据 | 主要边界 | 对分工意味着什么 |", report)
        self.assertIn("| 根判断 | 一句话结论 | 核心支撑 | 当前边界 |", report)
        self.assertIn("| 对象 | 用户主命题 | 最伤问题 | 最稳锚点 | 证据来源 | 市场口径 | 成熟度 | 当前动作 |", report)
        self.assertIn("| 对象 | 当前稳定结论 | 为什么成立 | 不要误讲成什么 | 当前不能讲满 |", report)
        self.assertIn("| 问题 | 伤害的是 | 主要证据 | 影响对象 | 优先级 | 当前边界 |", report)
        self.assertIn("| 问题 | 主要类型 | 主要场景 | 主要工况 | 用户期待 | 当前判断 |", report)
        self.assertIn("| 对象 / 范围 | 当前状态 | 为什么不能讲满 | 当前允许怎么讲 |", report)
        self.assertIn("| 竞争带 | 真正对手 | 真正战场 | 不能讲歪成什么 | 当前最该防什么 | 当前状态 |", report)
        self.assertIn("| 系列 | 必须承接 | 不再承接 | 错配代价 | 当前不做 |", report)
        self.assertIn("| 缺口 | 当前状态 | 卡住哪条结论 | 补什么 | 补完后能升级什么 |", report)
        self.assertNotIn("### 2.3 品牌心智 / 金点子（支持判断）", report)
        self.assertIn("### 附B 品牌心智备查表", report)
        self.assertIn("### 附C 金点子备查表", report)
        self.assertNotIn("converged", report)
        self.assertNotIn("contested", report)
        self.assertNotIn("not_ready", report)
        self.assertNotIn("evidence packet", report)
        self.assertNotIn("external_only", report)
        self.assertNotIn("frontline_mode", report)
        self.assertNotIn("前台表达层", report)
        self.assertNotIn("这章先回答", report)
        self.assertNotIn("这意味着", report)
        self.assertNotIn("待补充", report)
        self.assertNotIn("当前 runtime 汇总周期", report)
        self.assertNotIn("品牌心智和金点子继续保留", report)

    def test_build_artifact_index_includes_reflection_capture_and_tree_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = [
                root / "analysis_reflection_report.json",
                root / "analysis_reflection_report.md",
                root / "self_strategy_thesis.json",
                root / "entry_exposure_tree.json",
                root / "cleaning_robot_theme_registry.json",
                root / "voc_fact_exposure_tree.json",
                root / "topic_attention_matrix.json",
                root / "problem_drilldown_packages.json",
                root / "qual_evidence_packet.json",
                root / "qual_reasoning_task_board.json",
                root / "qual_case_reasoning_cards.json",
                root / "qual_theme_reasoning_map.json",
                root / "cross_source_hypothesis_board.json",
                root / "survey_qual_explanation_map.json",
                root / "judgment_acceptance_log.json",
                root / "user_insight_exposure_tree.json",
                root / "user_strategy_convergence_tree.json",
                root / "user_thesis_tree.json",
                root / "cross_source_convergence_tree.json",
                root / "competition_thesis_tree.json",
                root / "self_strategy_thesis_tree.json",
                root / "master_judgment_tree.json",
                root / "presentation_tree.json",
                root / "user_presentation_blocks.json",
                root / "mirror_review_loop_report.json",
                root / "mirror_open_risks.md",
                root / "competition_capture_target_manifest_template.csv",
                root / "competition_capture_target_manifest_ready.csv",
                root / "competition_capture_target_manifest_summary.md",
                root / "competition_capture_execution_log.md",
            ]
            for path in paths:
                path.write_text("x", encoding="utf-8")
            payload = build_artifact_index(paths)
        self.assertTrue(payload["analysis_reflection_report"])
        self.assertTrue(payload["analysis_reflection_report_json"])
        self.assertTrue(payload["self_strategy_thesis"])
        self.assertTrue(payload["entry_exposure_tree"])
        self.assertTrue(payload["cleaning_robot_theme_registry"])
        self.assertTrue(payload["voc_fact_exposure_tree"])
        self.assertTrue(payload["topic_attention_matrix"])
        self.assertTrue(payload["problem_drilldown_packages"])
        self.assertTrue(payload["qual_evidence_packet"])
        self.assertTrue(payload["qual_reasoning_task_board"])
        self.assertTrue(payload["qual_case_reasoning_cards"])
        self.assertTrue(payload["qual_theme_reasoning_map"])
        self.assertTrue(payload["cross_source_hypothesis_board"])
        self.assertTrue(payload["survey_qual_explanation_map"])
        self.assertTrue(payload["judgment_acceptance_log"])
        self.assertTrue(payload["user_insight_exposure_tree"])
        self.assertTrue(payload["user_strategy_convergence_tree"])
        self.assertTrue(payload["user_thesis_tree"])
        self.assertTrue(payload["cross_source_convergence_tree"])
        self.assertTrue(payload["competition_thesis_tree"])
        self.assertTrue(payload["self_strategy_thesis_tree"])
        self.assertTrue(payload["master_judgment_tree"])
        self.assertTrue(payload["presentation_tree"])
        self.assertTrue(payload["user_presentation_blocks"])
        self.assertTrue(payload["mirror_review_loop_report"])
        self.assertTrue(payload["mirror_open_risks"])
        self.assertTrue(payload["competition_capture_target_manifest_template"])
        self.assertTrue(payload["competition_capture_target_manifest_ready"])
        self.assertTrue(payload["competition_capture_target_manifest_summary"])
        self.assertTrue(payload["competition_capture_execution_log"])

    def test_user_chain_dependency_registry_is_valid(self) -> None:
        payload = json.loads(USER_CHAIN_DEPENDENCY_REGISTRY_PATH.read_text(encoding="utf-8"))
        report = validate_user_chain_dependency_registry(payload)
        self.assertTrue(report["valid"])
        self.assertGreater(report["step_count"], 0)

    def test_build_user_chain_loopback_execution_plan_reads_registry_override(self) -> None:
        plan = build_user_chain_loopback_execution_plan(
            loopback_target="loopback_exposure",
            affected_artifact="problem_drilldown_packages",
            runtime_dir="/tmp/runtime",
            auto_round=0,
        )
        self.assertEqual(plan["mapped_refresh_scope"], "user_exposure")
        self.assertIn("problem_drilldown_packages", plan["target_artifacts"])
        self.assertIn("build_problem_drilldown_packages", plan["target_builders"])

    def test_build_user_chain_dependency_registry_index_exposes_builder_and_artifact_maps(self) -> None:
        index = build_user_chain_dependency_registry_index()
        self.assertEqual(index["artifact_to_step"]["cross_source_interpretation"], "build_cross_source_interpretation")
        self.assertEqual(index["builder_aliases"]["evaluate_candidate_claims"], "run_dual_engine_reasoning")

    def test_build_semantic_passages_filters_noise_and_keeps_judgment_sentences(self) -> None:
        rows = [
            {
                "summary_case_id": "case_2",
                "case_title": "202601-中国上海-张先生-X50",
                "study_name": "2026年1月 中国",
                "batch_market_scope": "cn",
                "period_label": "2026-01",
                "inferred_spu_id": "dreame_x50pro_track",
                "analysis_module_code": "user_profile",
                "analysis_module_name_cn": "用户画像",
                "canonical_section_name_cn": "用户画像",
                "section_title": "PART 1: 他们是谁？消费者人设",
                "section_text": "一句话：34岁，家庭顶梁柱，希望解放双手。",
            },
            {
                "summary_case_id": "case_2",
                "case_title": "202601-中国上海-张先生-X50",
                "study_name": "2026年1月 中国",
                "batch_market_scope": "cn",
                "period_label": "2026-01",
                "inferred_spu_id": "dreame_x50pro_track",
                "analysis_module_code": "open_discussion",
                "analysis_module_name_cn": "开放讨论与补充",
                "canonical_section_name_cn": "开放讨论",
                "section_title": "入户小组成员",
                "section_text": "入户洞察参与者：A、B、C",
            },
            {
                "summary_case_id": "case_2",
                "case_title": "202601-中国上海-张先生-X50",
                "study_name": "2026年1月 中国",
                "batch_market_scope": "cn",
                "period_label": "2026-01",
                "inferred_spu_id": "dreame_x50pro_track",
                "analysis_module_code": "user_needs",
                "analysis_module_name_cn": "用户诉求",
                "canonical_section_name_cn": "用户诉求",
                "section_title": "4.2 用户诉求",
                "section_text": "1. 智能性的显性化：\n优化路径规划算法，减少卡顿打转。",
            },
        ]
        payload = extract_summary_insight_cards(rows)
        semantic = build_semantic_passages(payload["case_concept_slots"])
        texts = [row["passage_text"] for row in semantic["passages"]]
        self.assertTrue(any("34岁" in text for text in texts))
        self.assertTrue(any("优化路径规划算法" in text for text in texts))
        self.assertFalse(any("入户洞察参与者" in text for text in texts))

    def test_build_qual_evidence_packet_collects_support_disconfirm_and_boundaries(self) -> None:
        payload = build_qual_evidence_packet(
            semantic_passages={
                "cases": [
                    {
                        "summary_case_id": "case_1",
                        "case_title": "案例A",
                        "top_passages": [
                            {"passage_id": "p1", "series_code": "X", "passage_role": "痛点", "passage_text": "不接受水渍和返工", "quality_score": 0.9},
                            {"passage_id": "p2", "series_code": "X", "passage_role": "期待", "passage_text": "希望少返工更托管", "quality_score": 0.8},
                        ],
                    },
                    {
                        "summary_case_id": "case_2",
                        "case_title": "案例B",
                        "top_passages": [
                            {"passage_id": "p3", "series_code": "X", "passage_role": "痛点", "passage_text": "顽固污渍拖不干净会失望", "quality_score": 0.85},
                        ],
                    },
                ],
                "passages": [
                    {"passage_id": "p1", "case_title": "案例A", "series_code": "X", "passage_role": "痛点", "passage_text": "不接受水渍和返工", "quality_score": 0.9, "passage_tags": ["污渍问题"]},
                    {"passage_id": "p2", "case_title": "案例A", "series_code": "X", "passage_role": "期待", "passage_text": "希望少返工更托管", "quality_score": 0.8, "passage_tags": ["污渍问题"]},
                    {"passage_id": "p3", "case_title": "案例B", "series_code": "X", "passage_role": "痛点", "passage_text": "顽固污渍拖不干净会失望", "quality_score": 0.85, "passage_tags": ["污渍问题"]},
                    {"passage_id": "p4", "case_title": "案例C", "series_code": "X", "passage_role": "期待", "passage_text": "边角扫干净就行", "quality_score": 0.75, "passage_tags": ["边角问题"]},
                ],
            },
            topic_attention_matrix={
                "topic_summary_rows": [
                    {"series_family": "X", "user_band": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "污渍问题", "mention_count": 40, "positive_count": 0, "negative_count": 40, "mention_rate": 0.4},
                ]
            },
            problem_drilldown_packages={
                "rows": [
                    {
                        "series_family": "X",
                        "user_band": "X",
                        "cohort_scope": "科沃斯样本",
                        "market_scope": "中国",
                        "problem_name": "污渍问题",
                        "type_breakdown": [{"label": "水渍水痕"}, {"label": "顽固污渍拖不干净"}],
                        "scene_breakdown": [{"label": "厨房"}],
                        "working_condition_breakdown": [{"label": "油污"}],
                        "effect_expectation_breakdown": [{"label": "一次拖净不留痕"}],
                        "negative_profile_summary": "会因为污渍返工。",
                        "next_drilldown_axis": "场景",
                    }
                ]
            },
            survey_segment_comparison={
                "segments": [
                    {
                        "segment_name": "要求稳定托管",
                        "wave_name": "X11早期用户调研数据",
                        "inferred_spu_id": "ecovacs_x11",
                        "top_problems": ["污渍问题"],
                        "difference_reason": ["对返工非常敏感"],
                    }
                ]
            },
            survey_concept_segments={"segments": []},
            survey_open_answer_rows=[
                {
                    "wave_id": "wave_x11",
                    "wave_name": "X11早期用户调研数据",
                    "market_scope": "中国",
                    "series_family": "X",
                    "question_id": "q1",
                    "question_text": "最不能接受什么",
                    "response_identity_id": "resp_1",
                    "answer_text": "最不能接受拖完还有水渍，要自己返工。",
                    "survey_topic": "cleaning_needs",
                }
            ],
        )
        self.assertEqual(payload["artifact_type"], "qual_evidence_packet")
        self.assertTrue(payload["packets"])
        theme_packet = next(item for item in payload["packets"] if item["reasoning_task_type"] == "theme_explain")
        self.assertEqual(theme_packet["topic_name"], "污渍问题")
        self.assertTrue(theme_packet["supporting_cases"])
        self.assertTrue(theme_packet["supporting_passages"])
        self.assertTrue(theme_packet["supporting_open_answers"])
        self.assertTrue(theme_packet["linked_voc_signals"])
        self.assertTrue(theme_packet["linked_survey_signals"])
        self.assertTrue(theme_packet["scope_boundaries"])

    def test_build_qual_reasoning_task_board_prioritizes_focus_and_skips_n_omni_theme(self) -> None:
        payload = build_qual_reasoning_task_board(
            {
                "packets": [
                    {
                        "packet_id": "case::a",
                        "series_family": "X",
                        "user_band": "X",
                        "topic_name": "-",
                        "market_scope": "ALL",
                        "reasoning_task_type": "case_explain",
                        "supporting_cases": ["案例A"],
                        "supporting_passages": [{"passage_id": "p1"}],
                    },
                    {
                        "packet_id": "theme::x::stain",
                        "series_family": "X",
                        "user_band": "X",
                        "topic_name": "污渍问题",
                        "market_scope": "中国",
                        "reasoning_task_type": "theme_explain",
                        "supporting_cases": ["案例A"],
                        "linked_voc_signals": [{"topic_name": "污渍问题", "negative_count": 10, "positive_count": 1}],
                    },
                    {
                        "packet_id": "theme::n::omni",
                        "series_family": "N",
                        "user_band": "N_omni",
                        "topic_name": "智能交互/地图",
                        "market_scope": "中国",
                        "reasoning_task_type": "theme_explain",
                        "supporting_cases": [],
                        "scope_boundaries": ["当前仍缺稳定自家 VOC 用户样本，只能保留边界与补数方向。"],
                    },
                    {
                        "packet_id": "claim::n::omni",
                        "series_family": "N",
                        "user_band": "N_omni",
                        "topic_name": "-",
                        "market_scope": "ALL",
                        "reasoning_task_type": "cross_source_claim",
                        "scope_boundaries": ["当前仍缺稳定自家 VOC 用户样本，只能保留边界与补数方向。"],
                    },
                ]
            }
        )
        rows = {row["packet_id"]: row for row in payload["rows"]}
        self.assertEqual(rows["theme::x::stain"]["priority"], "P1")
        self.assertTrue(rows["theme::x::stain"]["ready_for_llm"])
        self.assertEqual(rows["case::a"]["priority"], "P3")
        self.assertTrue(rows["case::a"]["ready_for_llm"])
        self.assertFalse(rows["theme::n::omni"]["ready_for_llm"])
        self.assertEqual(rows["claim::n::omni"]["priority"], "P4")
        self.assertTrue(rows["claim::n::omni"]["ready_for_llm"])

    def test_run_dual_engine_reasoning_returns_reasoning_bundle_for_deterministic_stub(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "profiles.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "qual_default": {
                                "provider": "deterministic_stub",
                                "model": "stub-qual",
                                "temperature": 0.2,
                                "max_tokens": 4000,
                                "system_prompt_id": "qual_reasoning_v1",
                                "timeout_sec": 30,
                            },
                            "thesis_default": {
                                "provider": "deterministic_stub",
                                "model": "stub-thesis",
                                "temperature": 0.1,
                                "max_tokens": 4000,
                                "system_prompt_id": "thesis_reasoning_v1",
                                "timeout_sec": 30,
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            bundle = run_dual_engine_reasoning(
                analysis_engine="dual_engine_llm",
                qual_evidence_packet={
                    "packets": [
                        {
                            "packet_id": "case::a",
                            "series_family": "X",
                            "user_band": "X",
                            "topic_name": "-",
                            "market_scope": "ALL",
                            "reasoning_task_type": "case_explain",
                            "supporting_cases": ["案例A"],
                            "supporting_passages": [
                                {"passage_id": "p1", "passage_role": "痛点", "passage_text": "不接受水渍返工"},
                                {"passage_id": "p2", "passage_role": "期待", "passage_text": "希望拖净不留痕"},
                            ],
                            "scope_boundaries": ["当前是单案例深描，不代表整条系列的稳定主命题。"],
                        },
                        {
                            "packet_id": "theme::x::stain",
                            "series_family": "X",
                            "user_band": "X",
                            "topic_name": "污渍问题",
                            "market_scope": "中国",
                            "reasoning_task_type": "theme_explain",
                            "supporting_cases": ["案例A"],
                            "supporting_passages": [{"passage_id": "p1", "passage_role": "痛点", "passage_text": "不接受水渍返工"}],
                            "supporting_open_answers": [{"wave_id": "w1", "question_id": "q1", "response_identity_id": "r1", "answer_text": "拖完有水渍要返工"}],
                            "linked_voc_signals": [{"topic_name": "污渍问题", "negative_count": 12, "positive_count": 1}],
                            "linked_survey_signals": [{"segment_name": "要求稳定托管", "wave_name": "X11早期用户调研数据"}],
                            "linked_drilldown_rows": [{"negative_profile_summary": "会因为污渍返工。", "next_drilldown_axis": "场景"}],
                            "scope_boundaries": ["当前结论仍需和统计门槛、市场优先级一起使用，不应脱离事实层单独上台。"],
                        },
                        {
                            "packet_id": "claim::x::x",
                            "series_family": "X",
                            "user_band": "X",
                            "topic_name": "污渍问题",
                            "market_scope": "ALL",
                            "reasoning_task_type": "cross_source_claim",
                            "supporting_cases": ["案例A"],
                            "linked_voc_signals": [{"topic_name": "污渍问题", "mention_count": 20, "negative_count": 12, "positive_count": 1}],
                            "linked_survey_signals": [{"segment_name": "要求稳定托管", "wave_name": "X11早期用户调研数据"}],
                            "scope_boundaries": ["当前结论仍需和统计门槛、市场优先级一起使用，不应脱离事实层单独上台。"],
                        },
                    ]
                },
                llm_profile_path=profile_path,
                qual_reasoning_profile="qual_default",
                thesis_reasoning_profile="thesis_default",
            )
        self.assertEqual(bundle["fallback_status"], "")
        self.assertTrue(bundle["qual_reasoning_task_board"]["rows"])
        self.assertTrue(bundle["qual_case_reasoning_cards"]["rows"])
        self.assertTrue(bundle["qual_theme_reasoning_map"]["rows"])
        self.assertTrue(bundle["cross_source_hypothesis_board"]["rows"])
        self.assertTrue(bundle["candidate_claims"])

    def test_evaluate_candidate_claims_marks_accepted_demoted_and_rejected(self) -> None:
        packet = {
            "packets": [
                {
                    "packet_id": "theme::accepted",
                    "supporting_cases": ["案例A", "案例B"],
                    "disconfirming_cases": [],
                    "supporting_open_answers": [],
                    "linked_voc_signals": [{"topic_name": "污渍问题"}],
                    "scope_boundaries": ["当前需结合市场边界使用。"],
                },
                {
                    "packet_id": "theme::demoted",
                    "supporting_cases": ["案例C"],
                    "disconfirming_cases": [],
                    "supporting_open_answers": [],
                    "linked_voc_signals": [],
                    "scope_boundaries": ["当前需结合市场边界使用。"],
                },
                {
                    "packet_id": "theme::rejected",
                    "supporting_cases": [],
                    "disconfirming_cases": ["案例D"],
                    "supporting_open_answers": [],
                    "linked_voc_signals": [],
                    "scope_boundaries": [],
                },
            ]
        }
        payload = evaluate_candidate_claims(
            [
                {"claim_id": "c1", "packet_id": "theme::accepted", "claim_scope": "X/污渍问题", "claim_source": "theme_reasoning", "candidate_claim": "accepted claim"},
                {"claim_id": "c2", "packet_id": "theme::demoted", "claim_scope": "X/边角问题", "claim_source": "theme_reasoning", "candidate_claim": "demoted claim"},
                {"claim_id": "c3", "packet_id": "theme::rejected", "claim_scope": "X/地图", "claim_source": "theme_reasoning", "candidate_claim": "rejected claim"},
            ],
            packet,
            analysis_engine="dual_engine_llm",
            fallback_status="",
        )
        rows = {row["claim_id"]: row for row in payload["rows"]}
        self.assertEqual(rows["c1"]["accept_status"], "accepted")
        self.assertTrue(rows["c1"]["frontstage_permission"])
        self.assertEqual(rows["c2"]["accept_status"], "demoted")
        self.assertFalse(rows["c2"]["frontstage_permission"])
        self.assertEqual(rows["c3"]["accept_status"], "rejected")
        self.assertFalse(rows["c3"]["frontstage_permission"])

    def test_build_survey_qual_explanation_map_prefers_accepted_reasoning(self) -> None:
        payload = build_survey_qual_explanation_map(
            {"cases": []},
            {"segments": []},
            {"segments": []},
            {"packages": []},
            {"packages": []},
            {
                "rows": [
                    {"series_family": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "污渍问题", "negative_count": 10, "mention_count": 20},
                ]
            },
            {
                "rows": [
                    {
                        "problem_name": "污渍问题",
                        "series_family": "X",
                        "cohort_scope": "科沃斯样本",
                        "market_scope": "中国",
                        "reasonableness_judgment": "结果底线不能失守。",
                        "negative_profile_summary": "会返工。",
                        "positive_profile_summary": "拖净不留痕。",
                        "effect_expectation_breakdown": [{"label": "一次拖净不留痕"}],
                    }
                ]
            },
            {"rows": [{"topic_name": "污渍问题", "is_cleaning_robot_relevant": True}]},
            qual_case_reasoning_cards={
                "rows": [
                    {
                        "case_id": "case::a",
                        "case_title": "案例A",
                        "failure_definition": "拖完还有水渍就等于没解决问题。",
                        "hidden_needs": ["结果可确认且不用返工。"],
                        "acceptable_tradeoff": "可以接受偶尔多跑一遍，但不能留下明显水痕。",
                        "compensation_behavior": "会自己返工并重新检查结果。",
                    }
                ]
            },
            qual_theme_reasoning_map={
                "rows": [
                    {
                        "theme_name": "污渍问题",
                        "series_family": "X",
                        "user_band": "X",
                        "claim_id": "theme_claim::x::stain",
                        "why_it_matters": "污渍问题一旦失守，用户会立刻返工并质疑托管承诺。",
                        "what_is_not_the_real_issue": "这不只是脏污强度问题，更是结果确认感问题。",
                        "supporting_case_ids": ["case::a"],
                    }
                ]
            },
            judgment_acceptance_log={
                "rows": [
                    {"claim_id": "theme_claim::x::stain", "frontstage_permission": True},
                ]
            },
        )
        row = next(item for item in payload["topic_rows"] if item["topic_name"] == "污渍问题")
        self.assertEqual(row["explanation_mode"], "accepted_reasoning")
        self.assertIn("托管承诺", row["why_this_topic_is_sensitive"])
        self.assertTrue(row["accepted_reasoning_refs"])
        self.assertIn("结果确认感问题", row["not_the_real_issue"])

    def test_build_user_thesis_tree_adds_mechanism_and_accepted_claim_refs(self) -> None:
        payload = build_user_thesis_tree(
            {"not_ready_nodes": [{"lead_judgment": "表达型机会仍待观察"}]},
            {
                "rows": [
                    {"series_family": "X", "user_band": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "污渍问题", "mention_count": 20, "mention_rate": 0.2, "positive_count": 5, "negative_count": 10, "positive_rate": 0.25, "negative_rate": 0.5},
                    {"series_family": "X", "user_band": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "维护/基站", "mention_count": 10, "mention_rate": 0.1, "positive_count": 8, "negative_count": 2, "positive_rate": 0.8, "negative_rate": 0.2},
                ]
            },
            {"rows": [{"problem_name": "污渍问题", "cohort_scope": "科沃斯样本", "series_family": "X", "effect_expectation_breakdown": [], "reasonableness_judgment": "需要继续补定性。"}]},
            qual_theme_reasoning_map={
                "rows": [
                    {
                        "theme_name": "污渍问题",
                        "series_family": "X",
                        "user_band": "X",
                        "claim_id": "theme_claim::x::stain",
                        "why_it_matters": "污渍问题会直接打穿结果底线。",
                    }
                ]
            },
            cross_source_hypothesis_board={
                "rows": [
                    {
                        "hypothesis_id": "hypothesis::x::x",
                        "series_family": "X",
                        "user_band": "X",
                        "resolution_status": "accepted",
                        "why_accepted_or_rejected": "当前定性解释已经和 VOC/问卷形成同向支撑，可以进入正式 thesis 收敛。",
                    }
                ]
            },
            judgment_acceptance_log={
                "rows": [
                    {"claim_id": "theme_claim::x::stain", "frontstage_permission": True},
                    {"claim_id": "hypothesis::x::x", "frontstage_permission": True},
                ]
            },
        )
        self.assertTrue(payload["mechanism_explanations"])
        self.assertTrue(payload["accepted_claim_refs"])
        self.assertIn("机制上", payload["x_core_thesis"])

    def test_resolve_llm_profile_validates_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "profiles.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "qual_default": {
                                "provider": "openai_compatible",
                                "model": "demo-model",
                                "temperature": 0.2,
                                "max_tokens": 4000,
                                "system_prompt_id": "qual_reasoning_v1",
                                "timeout_sec": 90,
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            payload = resolve_llm_profile(profile_path, "qual_default")
            self.assertEqual(payload["model"], "demo-model")

    def test_build_x_positioning_packages_prefers_distinct_representative_users(self) -> None:
        case_concept_slots = {
            "cases": [
                {
                    "summary_case_id": "x1",
                    "case_title": "case_help",
                    "series_code": "X",
                    "persona_notes": ["一句话：希望扫地机解决80%的工作，别添乱。"],
                    "cleaning_attitude": ["扫地机能帮我解决80%的清洁工作就行。"],
                    "purchase_trigger": ["解放双手"],
                    "purchase_decision": ["性价比高，别添乱"],
                    "pain_points": ["维护麻烦会影响判断"],
                    "expected_needs": ["少维护"],
                    "concept_ideas": [],
                    "brand_evaluation": [],
                },
                {
                    "summary_case_id": "x2",
                    "case_title": "case_butler",
                    "series_code": "X",
                    "persona_notes": ["一句话：希望机器自己知道哪里脏。"],
                    "cleaning_attitude": ["希望扫地机无感、主动、托管。"],
                    "purchase_trigger": ["省心托管"],
                    "purchase_decision": ["主动感知和托管最重要"],
                    "pain_points": ["不够无感"],
                    "expected_needs": ["自己知道什么时候脏"],
                    "concept_ideas": ["主动清洁"],
                    "brand_evaluation": [],
                },
                {
                    "summary_case_id": "x3",
                    "case_title": "case_social",
                    "series_code": "X",
                    "persona_notes": ["一句话：愿意为黑科技和科技感付溢价。"],
                    "cleaning_attitude": ["科技感和社交谈资很重要。"],
                    "purchase_trigger": ["黑科技"],
                    "purchase_decision": ["颜值和社交货币"],
                    "pain_points": ["没有足够新鲜感"],
                    "expected_needs": ["更强黑科技表达"],
                    "concept_ideas": ["机械臂"],
                    "brand_evaluation": [],
                },
            ]
        }
        semantic = build_semantic_passages(case_concept_slots)
        payload = build_x_positioning_packages(case_concept_slots, semantic)
        top_titles = [
            row["representative_users"][0]["case_title"]
            for row in payload["packages"]
            if row["representative_users"]
        ]
        self.assertEqual(len(top_titles), len(set(top_titles)))

    def test_build_x_observed_positionings_uses_role_style_and_can_mark_weak_signal(self) -> None:
        case_concept_slots = {
            "cases": [
                {
                    "summary_case_id": "x1",
                    "case_title": "case_help_a",
                    "series_code": "X",
                    "persona_notes": ["一句话：希望扫地机解决80%的工作，别添乱。"],
                    "cleaning_attitude": ["扫地机能帮我解决80%的清洁工作就行。"],
                    "purchase_trigger": ["解放双手"],
                    "purchase_decision": ["性价比高，别添乱"],
                    "pain_points": ["维护麻烦会影响判断"],
                    "expected_needs": ["少维护"],
                    "concept_ideas": [],
                    "brand_evaluation": [],
                    "hidden_needs": ["家务负担转移"],
                },
                {
                    "summary_case_id": "x2",
                    "case_title": "case_help_b",
                    "series_code": "X",
                    "persona_notes": ["一句话：能做完大面就行，剩下自己补。"],
                    "cleaning_attitude": ["基础清洁完成80%即可，自己收尾。"],
                    "purchase_trigger": ["少维护"],
                    "purchase_decision": ["别添乱，少维护"],
                    "pain_points": ["边角需要自己补尾"],
                    "expected_needs": ["不添乱"],
                    "concept_ideas": [],
                    "brand_evaluation": [],
                    "hidden_needs": ["家务负担转移"],
                },
                {
                    "summary_case_id": "x3",
                    "case_title": "case_butler_a",
                    "series_code": "X",
                    "persona_notes": ["一句话：希望机器自己知道哪里脏。"],
                    "cleaning_attitude": ["希望扫地机少操心、主动、托管。"],
                    "purchase_trigger": ["省心托管"],
                    "purchase_decision": ["主动感知和托管最重要"],
                    "pain_points": ["不够无感"],
                    "expected_needs": ["自己知道什么时候脏"],
                    "concept_ideas": ["主动清洁"],
                    "brand_evaluation": [],
                    "hidden_needs": ["真正托管"],
                },
                {
                    "summary_case_id": "x4",
                    "case_title": "case_butler_b",
                    "series_code": "X",
                    "persona_notes": ["一句话：想把清洁从脑子里删掉。"],
                    "cleaning_attitude": ["希望不用我管，稳定托管。"],
                    "purchase_trigger": ["少操心"],
                    "purchase_decision": ["主动补位和稳定托管最重要"],
                    "pain_points": ["返工会破坏信任"],
                    "expected_needs": ["少返工"],
                    "concept_ideas": ["自动感知"],
                    "brand_evaluation": [],
                    "hidden_needs": ["真正托管"],
                },
                {
                    "summary_case_id": "x5",
                    "case_title": "case_expr",
                    "series_code": "X",
                    "persona_notes": ["一句话：愿意为科技感和设计感买单。"],
                    "cleaning_attitude": ["科技感和外观更重要。"],
                    "purchase_trigger": ["黑科技"],
                    "purchase_decision": ["外观和设计感先过关"],
                    "pain_points": ["没有新鲜感"],
                    "expected_needs": ["更强科技感表达"],
                    "concept_ideas": ["机械臂"],
                    "brand_evaluation": ["高端外观有科技感"],
                    "hidden_needs": ["身份表达"],
                },
            ]
        }
        semantic = build_semantic_passages(case_concept_slots)
        signal_profiles = build_x_case_signal_profiles(case_concept_slots, semantic)
        observed = build_x_observed_positionings(case_concept_slots, semantic, signal_profiles)

        labels = [row["display_label"] for row in observed["positionings"]]
        self.assertIn("清洁帮手", labels)
        self.assertIn("清洁管家", labels)
        self.assertNotIn("社交名片", labels)
        weak_rows = [row for row in observed["positionings"] if row["positioning_level"] == "weak_signal"]
        self.assertTrue(any("玩家" in row["display_label"] for row in weak_rows))

    def test_build_brand_mindshare_map_avoids_multi_brand_blob_pollution(self) -> None:
        case_concept_slots = {
            "cases": [
                {
                    "case_title": "case_a",
                    "brand_evaluation": [
                        "早期种草后，妻子推荐石头品牌，去朋友家了解到云鲸水箱版有异味，抖音对科沃斯评价不佳，对追觅高端机型评价较好。",
                        "科沃斯：老牌，但创新吸引力不足。",
                        "石头：路线规划很规整，是不会出错的标杆。",
                        "追觅：高端感和黑科技表达更强。",
                    ],
                },
                {
                    "case_title": "case_b",
                    "brand_evaluation": [
                        "云鲸：拖地更强，但担心异味和退货机。",
                        "大疆：跨界科技感强，但不愿意当小白鼠。",
                    ],
                },
            ]
        }
        payload = build_brand_mindshare_map(case_concept_slots)
        ecovacs = payload["brands"]["科沃斯"]
        self.assertTrue(any(line.startswith("科沃斯") for line in ecovacs["trust_reason"]))
        self.assertFalse(any("石头品牌" in line or "云鲸水箱版" in line for line in ecovacs["trust_reason"]))
        self.assertTrue(all(len(line) < 40 for line in ecovacs["trust_reason"]))

    def test_build_brand_mindshare_judgments_keeps_compat_fields(self) -> None:
        brand_map = {
            "brands": {
                "科沃斯": {
                    "core_label": "老牌大厂，品牌认知高，但口碑会随着具体产品体验明显分化。",
                    "trust_reason": ["科沃斯：老牌专业，品牌认知高。"],
                    "rejection_reason": ["科沃斯：创新吸引力不足。"],
                    "representative_quotes": ["科沃斯：老牌专业，品牌认知高。"],
                    "who_prefers_it": ["case_a"],
                    "who_rejects_it": ["case_b"],
                }
            }
        }
        payload = build_brand_mindshare_judgments(brand_map)
        row = payload["judgments"][0]
        self.assertEqual(row["why_choose"], row["trust_reason"])
        self.assertEqual(row["why_reject"], row["rejection_reason"])
        self.assertEqual(row["quote_refs"], row["representative_quotes"])

    def test_build_competition_generation_analysis_has_brand_shape_rows(self) -> None:
        generation_comparison = {
            "series_rows": [
                {"series_code": "X", "lead_judgment": "x"},
                {"series_code": "T", "lead_judgment": "t"},
            ]
        }
        registry = {
            "version": "test",
            "rows": [
                {
                    "competition_scope": "X_omni",
                    "brand": "科沃斯",
                    "series_family": "X",
                    "shape_type": "omni",
                    "generation_bucket": "previous",
                    "product_names": ["X11 Pro"],
                    "is_self_brand": True,
                    "notes": "",
                },
                {
                    "competition_scope": "X_omni",
                    "brand": "科沃斯",
                    "series_family": "X",
                    "shape_type": "omni",
                    "generation_bucket": "current",
                    "product_names": ["X12 Pro"],
                    "is_self_brand": True,
                    "notes": "",
                },
                {
                    "competition_scope": "N_aes",
                    "brand": "科沃斯",
                    "series_family": "N",
                    "shape_type": "aes",
                    "generation_bucket": "current",
                    "product_names": ["摩根AES"],
                    "is_self_brand": True,
                    "notes": "",
                },
                {
                    "competition_scope": "T_omni",
                    "brand": "云鲸",
                    "series_family": "external",
                    "shape_type": "omni",
                    "generation_bucket": "current",
                    "product_names": ["P20 MAX"],
                    "is_self_brand": False,
                    "notes": "",
                },
                {
                    "competition_scope": "N_omni",
                    "brand": "石头",
                    "series_family": "external",
                    "shape_type": "omni",
                    "generation_bucket": "current",
                    "product_names": ["P20"],
                    "is_self_brand": False,
                    "notes": "",
                },
            ],
        }
        payload = build_competition_generation_analysis(generation_comparison, registry)
        self.assertTrue(payload["brand_shape_generation_rows"])
        self.assertTrue(any(row["series_code"] == "N" for row in payload["series_generation_rows"]))
        self.assertTrue(payload["scope_summary_rows"])
        self.assertTrue(payload["shape_summary_rows"])
        self.assertIn("X_omni（旗舰 omni）", [row["competition_scope"] for row in payload["scope_summary_rows"]])
        self.assertTrue(any(row["scope_breakdown"] == "X_omni（旗舰 omni）" for row in payload["shape_summary_rows"]))
        self.assertTrue(any(row["scope_breakdown"] == "T_omni（主销 omni）" for row in payload["shape_summary_rows"]))
        self.assertTrue(any(row["scope_breakdown"] == "N_omni（omni 下探）" for row in payload["shape_summary_rows"]))

    def test_build_portfolio_generation_strategy_returns_structured_rows(self) -> None:
        payload = build_portfolio_generation_strategy(
            competition_generation_analysis={
                "brand_shape_generation_rows": [
                    {
                        "series_family": "N",
                        "shape_type": "aes",
                        "is_self_brand": True,
                        "previous_products": ["N20 Plus"],
                        "current_products": ["摩根AES"],
                        "what_it_means_for_competition": "这是科沃斯在该形态上的守位或下探带，决定产品带宽是否完整。",
                    }
                ]
            },
            generation_comparison={
                "series_rows": [
                    {"series_code": "X", "strategy_summary": "X 负责高端旗舰 omni 的托管承诺与高价值体验。"},
                    {"series_code": "T", "strategy_summary": "T 负责主销 omni 的结果稳定与托管可信。"},
                ]
            },
            demand_pool_snapshot={
                "theme_rows": [
                    {
                        "theme_name": "清洁效果与水痕污渍",
                        "item_count": 20,
                        "statuses": ["待方案研究", "暂无方案"],
                        "owners": ["未分配", "陈茂勇"],
                        "unassigned_count": 8,
                        "no_solution_count": 5,
                        "research_like_count": 7,
                    },
                    {
                        "theme_name": "边角与覆盖率",
                        "item_count": 10,
                        "statuses": ["待评估"],
                        "owners": ["未分配"],
                        "unassigned_count": 6,
                        "no_solution_count": 0,
                        "research_like_count": 4,
                    },
                ]
            },
            strategy_translation={
                "half_year_focus": [
                    {"phase": "当前轮次", "core_blocker": "先把最伤害信任的一组问题讲透。"},
                    {"phase": "下一轮", "core_blocker": "把竞争差异翻成体验与信任差异。"},
                ]
            },
        )
        self.assertIsInstance(payload["portfolio_bandwidth_rows"][0], dict)
        self.assertIsInstance(payload["priority_assignment_rows"][0], dict)
        self.assertIsInstance(payload["roadmap_focus_rows"][0], dict)
        self.assertIn("外部已是高优，但内部承接责任还没收口", payload["priority_assignment_rows"][0]["demand_pool_signal"])

    def test_generate_insight_bundle_has_single_builder_definitions(self) -> None:
        source = inspect.getsource(insight_bundle)
        self.assertEqual(source.count("def build_competition_generation_analysis("), 1)
        self.assertEqual(source.count("def build_demand_pool_snapshot("), 1)
        self.assertEqual(source.count("def build_portfolio_generation_strategy("), 1)

    def test_count_passages_for_concept_empty_case_titles_returns_empty(self) -> None:
        semantic_passages = {
            "passages": [
                {
                    "case_title": "case_a",
                    "passage_role": "人物定义",
                    "passage_text": "case_a text",
                    "quality_score": 0.9,
                }
            ]
        }
        result = count_passages_for_concept(semantic_passages, case_titles=[])
        self.assertEqual(result, [])

    def test_build_t_jtbd_impact_stats_only_uses_t_series_voc(self) -> None:
        payload = build_t_jtbd_impact_stats(
            case_concept_slots={
                "cases": [
                    {
                        "case_title": "t_case",
                        "series_code": "T",
                        "inferred_spu_id": "ecovacs_t80s",
                        "persona_notes": [],
                        "cleaning_attitude": [],
                        "purchase_trigger": [],
                        "expected_needs": [],
                    }
                ]
            },
            t_jtbd_packages={
                "packages": [
                    {
                        "jtbd_name": "家庭投入",
                        "typical_scene": ["边角漏扫，反复补救，不能掉链子"],
                        "why_entered": [],
                    }
                ]
            },
            voc_problem_packages={
                "packages": [
                    {
                        "spu_id": "ecovacs_t80s",
                        "negative_tag": "边角漏扫",
                        "package_name": "边角边角漏扫问题包",
                        "damage_type": "工作完成率受损",
                        "trust_impact": "伤害工作完成率信任",
                    },
                    {
                        "spu_id": "ecovacs_x11",
                        "negative_tag": "边角漏扫",
                        "package_name": "边角边角漏扫问题包",
                        "damage_type": "工作完成率受损",
                        "trust_impact": "伤害工作完成率信任",
                    },
                ]
            },
            survey_concept_segments={"segments": []},
            concept_pain_need_map={"rows": [{"concept_id": "家庭投入", "pain_theme": "边角与覆盖率"}]},
            strategy_translation={"priority_buckets": {"底线问题": ["边角与覆盖率"]}},
        )
        row = payload["rows"][0]
        self.assertEqual(row["linked_voc_package_strength"], 1)

    def test_refresh_portfolio_user_chain_runtime_updates_manifest_and_outputs(self) -> None:
        class DummyConn:
            def close(self) -> None:
                return None

        runtime_artifacts = {
            "analysis_reflection_report": {"summary_judgment": "还差补数。"},
            "awe_exhibition_signals": {"direct_competitor_signals": []},
            "brand_mindshare_judgments": {"judgments": []},
            "case_concept_slots": {"cases": []},
            "cleaning_robot_theme_registry": {"rows": []},
            "competition_capability_scan": {"rows": []},
            "competition_capture_target_candidates": {"rows": []},
            "competition_generation_analysis": {"rows": []},
            "competition_matchup_matrix": {"rows": []},
            "competition_strategy_bridge": {},
            "competition_thesis_tree": {"thesis_nodes": []},
            "competition_voc_market_split": {"market_rows": []},
            "competition_voc_xtn_breakdown": {"product_rows": []},
            "cross_source_convergence_tree": {"concept_nodes": []},
            "cross_source_interpretation": {"interpretations": []},
            "demand_pool_snapshot": {},
            "entry_exposure_tree": {"boundary_nodes": []},
            "generation_comparison": {"series_rows": []},
            "idea_cluster_judgments": {"judgments": []},
            "page_metric_cards": {"rows": []},
            "portfolio_generation_strategy": {},
            "problem_drilldown_packages": {"rows": []},
            "qual_case_reasoning_cards": {"rows": []},
            "qual_evidence_packet": {"packets": []},
            "qual_reasoning_task_board": {"rows": []},
            "qual_theme_reasoning_map": {"rows": []},
            "self_strategy_thesis": {},
            "self_strategy_thesis_tree": {"thesis_nodes": []},
            "semantic_passages": {"cases": [], "passages": []},
            "summary_insight_cards": {"cards": [], "case_concept_slots": {"cases": []}},
            "series_positioning": {"series_rows": []},
            "strategy_translation": {},
            "survey_qual_explanation_map": {"rows": [], "topic_rows": []},
            "survey_concept_segments": {"segments": []},
            "survey_segment_comparison": {"segments": []},
            "t_difference_matrix": {"rows": []},
            "t_dimension_confidence_stats": {"rows": []},
            "t_dimension_impact_stats": {"rows": []},
            "t_jtbd_confidence_stats": {"rows": []},
            "t_jtbd_impact_stats": {"rows": []},
            "t_jtbd_packages": {"packages": []},
            "t_persona_slice_cards": {"cards": []},
            "topic_attention_matrix": {"rows": [], "topic_summary_rows": []},
            "cross_source_hypothesis_board": {"rows": []},
            "judgment_acceptance_log": {"rows": []},
            "voc_fact_exposure_tree": {"external_only_nodes": [], "missing_scope_nodes": []},
            "voc_problem_packages": {"packages": []},
            "user_insight_exposure_tree": {"series_nodes": [], "summary_judgment": "u", "stable_nodes": [], "weak_signal_nodes": [], "boundary_nodes": [], "drilldown_candidate_nodes": []},
            "user_strategy_convergence_tree": {"converged_nodes": [], "contested_nodes": [], "not_ready_nodes": []},
            "user_thesis_tree": {"n_band_theses": {}},
            "master_judgment_tree": {"summary_judgment": "m", "root_thesis": "r", "branches": []},
            "presentation_tree": {"summary_judgment": "p", "chapter_nodes": []},
            "presentation_page_blocks": {"blocks": []},
            "user_presentation_blocks": {"block_count": 0, "blocks": []},
            "x_jtbd_confidence_stats": {"rows": []},
            "x_jtbd_impact_stats": {"rows": []},
            "x_observed_positionings": {"positionings": []},
            "x_positioning_confidence_stats": {"rows": []},
            "x_positioning_impact_stats": {"rows": []},
            "x_positioning_packages": {"packages": []},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            (out_dir / "artifact_manifest.json").write_text(
                json.dumps(
                    {
                        "bundle_id": "cleaning_robot_full_portfolio_ppt_aligned",
                        "bundle_mode": "portfolio_full",
                        "category_name": "扫地机器人",
                        "primary_self_spu_id": "ecovacs_x11",
                        "primary_competitor_spu_id": "portfolio_full",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (out_dir / "main_report.md").write_text("# main\n", encoding="utf-8")
            args = mock.Mock(
                bundle_mode="portfolio_full",
                refresh_scope="user_chain",
                analysis_engine="dual_engine_llm",
                llm_profile_path=None,
                qual_reasoning_profile="qual_default",
                thesis_reasoning_profile="thesis_default",
                category_name="机器人产品",
                market=None,
                survey_topic=[],
                require_voc=False,
                time_scope="待补充",
                analysis_goal=[],
            )
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(insight_bundle, "load_runtime_json_artifacts", return_value=runtime_artifacts))
                stack.enter_context(mock.patch.object(insight_bundle, "collect_series_result", return_value={"selected_spus": [{"spu_id": "ecovacs_x11"}]}))
                stack.enter_context(mock.patch.object(insight_bundle, "connect", return_value=DummyConn()))
                stack.enter_context(mock.patch.object(insight_bundle, "connect_live_voc_preferred", return_value=DummyConn()))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_summary_theme_sections", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "build_summary_theme_evidence", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_wave_sample_count", return_value=10))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_survey_capability_question_summaries", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "build_survey_theme_evidence", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_voc_theme_rows", return_value=([], [], [])))
                stack.enter_context(mock.patch.object(insight_bundle, "build_voc_theme_evidence", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_tables", return_value=([], [], [], [])))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_user_attention_source_rows", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_survey_open_answer_rows", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cleaning_robot_theme_registry", return_value={"rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_topic_attention_matrix", return_value={"rows": [], "topic_summary_rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_problem_drilldown_packages", return_value={"rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_interpretation", return_value={"interpretations": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_series_positioning", return_value={"series_rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_strategy_translation", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_survey_qual_explanation_map", return_value={"rows": [], "topic_rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_insight_exposure_tree", return_value={"series_nodes": [], "summary_judgment": "u", "stable_nodes": [], "weak_signal_nodes": [], "boundary_nodes": [], "drilldown_candidate_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_strategy_convergence_tree", return_value={"converged_nodes": [], "contested_nodes": [], "not_ready_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_thesis_tree", return_value={"n_band_theses": {}}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_convergence_tree", return_value={"concept_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_self_strategy_thesis_tree", return_value={"thesis_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_master_judgment_tree", return_value={"summary_judgment": "m", "root_thesis": "r", "branches": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_presentation_tree", return_value={"summary_judgment": "p", "chapter_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_presentation_page_blocks", return_value={"blocks": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_presentation_blocks", return_value={"block_count": 0, "blocks": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "run_user_presentation_composer", return_value=("# report\n", {"final_status": "passed", "iteration_count": 1}, "# risks\n")))
                manifest_path = refresh_portfolio_user_chain_runtime(
                    args=args,
                    out_dir=out_dir,
                    style_profile={"banned_phrases": []},
                )

            self.assertTrue((out_dir / "topic_attention_matrix.json").exists())
            self.assertTrue((out_dir / "qual_evidence_packet.json").exists())
            self.assertTrue((out_dir / "qual_reasoning_task_board.json").exists())
            self.assertTrue((out_dir / "qual_case_reasoning_cards.json").exists())
            self.assertTrue((out_dir / "qual_theme_reasoning_map.json").exists())
            self.assertTrue((out_dir / "cross_source_hypothesis_board.json").exists())
            self.assertTrue((out_dir / "judgment_acceptance_log.json").exists())
            self.assertTrue((out_dir / "presentation_main_report.md").exists())
            self.assertTrue((out_dir / "mirror_review_loop_report.json").exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("T", manifest["produced_at"])
            self.assertEqual(manifest["artifact_index"]["topic_attention_matrix"], str(out_dir / "topic_attention_matrix.json"))
            self.assertEqual(manifest["artifact_index"]["qual_evidence_packet"], str(out_dir / "qual_evidence_packet.json"))
            self.assertEqual(manifest["artifact_index"]["qual_reasoning_task_board"], str(out_dir / "qual_reasoning_task_board.json"))
            self.assertEqual(manifest["artifact_index"]["qual_case_reasoning_cards"], str(out_dir / "qual_case_reasoning_cards.json"))
            self.assertEqual(manifest["artifact_index"]["qual_theme_reasoning_map"], str(out_dir / "qual_theme_reasoning_map.json"))
            self.assertEqual(manifest["artifact_index"]["cross_source_hypothesis_board"], str(out_dir / "cross_source_hypothesis_board.json"))
            self.assertEqual(manifest["artifact_index"]["judgment_acceptance_log"], str(out_dir / "judgment_acceptance_log.json"))
            self.assertEqual(manifest["artifact_index"]["presentation_main_report"], str(out_dir / "presentation_main_report.md"))

    def test_refresh_portfolio_user_chain_runtime_user_reasoning_skips_exposure_rebuild(self) -> None:
        class DummyConn:
            def close(self) -> None:
                return None

        runtime_artifacts = {
            "analysis_reflection_report": {"summary_judgment": "还差补数。"},
            "awe_exhibition_signals": {"direct_competitor_signals": []},
            "brand_mindshare_judgments": {"judgments": []},
            "case_concept_slots": {"cases": []},
            "cleaning_robot_theme_registry": {"rows": [{"topic_name": "污渍问题"}]},
            "competition_capability_scan": {"rows": []},
            "competition_capture_target_candidates": {"rows": []},
            "competition_generation_analysis": {"rows": []},
            "competition_matchup_matrix": {"rows": []},
            "competition_strategy_bridge": {},
            "competition_thesis_tree": {"thesis_nodes": []},
            "competition_voc_market_split": {"market_rows": []},
            "competition_voc_xtn_breakdown": {"product_rows": []},
            "cross_source_convergence_tree": {"concept_nodes": []},
            "cross_source_hypothesis_board": {"rows": []},
            "cross_source_interpretation": {"interpretations": []},
            "demand_pool_snapshot": {},
            "entry_exposure_tree": {"boundary_nodes": []},
            "generation_comparison": {"series_rows": []},
            "idea_cluster_judgments": {"judgments": []},
            "judgment_acceptance_log": {"rows": []},
            "page_metric_cards": {"rows": []},
            "portfolio_generation_strategy": {},
            "problem_drilldown_packages": {"rows": []},
            "qual_case_reasoning_cards": {"rows": []},
            "qual_evidence_packet": {"packets": []},
            "qual_reasoning_task_board": {"rows": []},
            "qual_theme_reasoning_map": {"rows": []},
            "self_strategy_thesis": {},
            "self_strategy_thesis_tree": {"thesis_nodes": []},
            "semantic_passages": {"cases": [], "passages": []},
            "summary_insight_cards": {"cards": [], "case_concept_slots": {"cases": []}},
            "series_positioning": {"series_rows": []},
            "strategy_translation": {},
            "survey_concept_segments": {"segments": []},
            "survey_segment_comparison": {"segments": []},
            "survey_qual_explanation_map": {"rows": [], "topic_rows": []},
            "t_difference_matrix": {"rows": []},
            "t_dimension_confidence_stats": {"rows": []},
            "t_dimension_impact_stats": {"rows": []},
            "t_jtbd_confidence_stats": {"rows": []},
            "t_jtbd_impact_stats": {"rows": []},
            "t_jtbd_packages": {"packages": []},
            "t_persona_slice_cards": {"cards": []},
            "topic_attention_matrix": {"rows": [], "topic_summary_rows": []},
            "user_insight_exposure_tree": {"series_nodes": [], "summary_judgment": "u", "stable_nodes": [], "weak_signal_nodes": [], "boundary_nodes": [], "drilldown_candidate_nodes": []},
            "user_presentation_blocks": {"block_count": 0, "blocks": []},
            "user_strategy_convergence_tree": {"converged_nodes": [], "contested_nodes": [], "not_ready_nodes": []},
            "user_thesis_tree": {"n_band_theses": {}},
            "voc_fact_exposure_tree": {"external_only_nodes": [], "missing_scope_nodes": []},
            "voc_problem_packages": {"packages": []},
            "x_jtbd_confidence_stats": {"rows": []},
            "x_jtbd_impact_stats": {"rows": []},
            "x_observed_positionings": {"positionings": []},
            "x_positioning_confidence_stats": {"rows": []},
            "x_positioning_impact_stats": {"rows": []},
            "x_positioning_packages": {"packages": []},
            "master_judgment_tree": {"summary_judgment": "m", "root_thesis": "r", "branches": []},
            "presentation_tree": {"summary_judgment": "p", "chapter_nodes": []},
            "presentation_page_blocks": {"blocks": []},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            (out_dir / "artifact_manifest.json").write_text(
                json.dumps(
                    {
                        "bundle_id": "cleaning_robot_full_portfolio_ppt_aligned",
                        "bundle_mode": "portfolio_full",
                        "category_name": "扫地机器人",
                        "primary_self_spu_id": "ecovacs_x11",
                        "primary_competitor_spu_id": "portfolio_full",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = mock.Mock(
                bundle_mode="portfolio_full",
                refresh_scope="user_reasoning",
                analysis_engine="dual_engine_llm",
                llm_profile_path=None,
                qual_reasoning_profile="qual_default",
                thesis_reasoning_profile="thesis_default",
                category_name="机器人产品",
                market=None,
                survey_topic=[],
                require_voc=False,
                time_scope="待补充",
                analysis_goal=[],
            )
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(insight_bundle, "load_runtime_json_artifacts", return_value=runtime_artifacts))
                stack.enter_context(mock.patch.object(insight_bundle, "collect_series_result", return_value={"selected_spus": [{"spu_id": "ecovacs_x11"}]}))
                stack.enter_context(mock.patch.object(insight_bundle, "connect", return_value=DummyConn()))
                stack.enter_context(mock.patch.object(insight_bundle, "connect_live_voc_preferred", return_value=DummyConn()))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_summary_theme_sections", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "build_summary_theme_evidence", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_wave_sample_count", return_value=10))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_survey_capability_question_summaries", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "build_survey_theme_evidence", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_voc_theme_rows", return_value=([], [], [])))
                stack.enter_context(mock.patch.object(insight_bundle, "build_voc_theme_evidence", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_tables", return_value=([], [], [], [])))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_user_attention_source_rows", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_survey_open_answer_rows", return_value=[]))
                clean_mock = stack.enter_context(mock.patch.object(insight_bundle, "build_cleaning_robot_theme_registry", return_value={"rows": []}))
                topic_mock = stack.enter_context(mock.patch.object(insight_bundle, "build_topic_attention_matrix", return_value={"rows": [], "topic_summary_rows": []}))
                drilldown_mock = stack.enter_context(mock.patch.object(insight_bundle, "build_problem_drilldown_packages", return_value={"rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_interpretation", return_value={"interpretations": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_series_positioning", return_value={"series_rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_strategy_translation", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_survey_qual_explanation_map", return_value={"rows": [], "topic_rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_insight_exposure_tree", return_value={"series_nodes": [], "summary_judgment": "u", "stable_nodes": [], "weak_signal_nodes": [], "boundary_nodes": [], "drilldown_candidate_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_strategy_convergence_tree", return_value={"converged_nodes": [], "contested_nodes": [], "not_ready_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_thesis_tree", return_value={"n_band_theses": {}}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_convergence_tree", return_value={"concept_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_self_strategy_thesis_tree", return_value={"thesis_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_master_judgment_tree", return_value={"summary_judgment": "m", "root_thesis": "r", "branches": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_presentation_tree", return_value={"summary_judgment": "p", "chapter_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_presentation_page_blocks", return_value={"blocks": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_presentation_blocks", return_value={"block_count": 0, "blocks": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "run_user_presentation_composer", return_value=("# report\n", {"final_status": "passed", "iteration_count": 1}, "# risks\n")))
                refresh_portfolio_user_chain_runtime(
                    args=args,
                    out_dir=out_dir,
                    style_profile={"banned_phrases": []},
                )
            clean_mock.assert_not_called()
            topic_mock.assert_not_called()
            drilldown_mock.assert_not_called()

    def test_refresh_portfolio_user_chain_runtime_user_closure_skips_lower_recomputation(self) -> None:
        runtime_artifacts = {
            "analysis_reflection_report": {"summary_judgment": "还差补数。"},
            "awe_exhibition_signals": {"direct_competitor_signals": []},
            "brand_mindshare_judgments": {"judgments": []},
            "case_concept_slots": {"cases": []},
            "cleaning_robot_theme_registry": {"rows": []},
            "competition_capability_scan": {"rows": []},
            "competition_capture_target_candidates": {"rows": []},
            "competition_generation_analysis": {"rows": []},
            "competition_matchup_matrix": {"rows": []},
            "competition_strategy_bridge": {},
            "competition_thesis_tree": {"thesis_nodes": []},
            "competition_voc_market_split": {"market_rows": []},
            "competition_voc_xtn_breakdown": {"product_rows": []},
            "cross_source_convergence_tree": {"concept_nodes": []},
            "cross_source_hypothesis_board": {"rows": []},
            "cross_source_interpretation": {"interpretations": []},
            "demand_pool_snapshot": {},
            "entry_exposure_tree": {"boundary_nodes": []},
            "generation_comparison": {"series_rows": []},
            "idea_cluster_judgments": {"judgments": []},
            "judgment_acceptance_log": {"rows": []},
            "page_metric_cards": {"rows": []},
            "portfolio_generation_strategy": {},
            "problem_drilldown_packages": {"rows": []},
            "qual_case_reasoning_cards": {"rows": []},
            "qual_evidence_packet": {"packets": []},
            "qual_reasoning_task_board": {"rows": []},
            "qual_theme_reasoning_map": {"rows": []},
            "self_strategy_thesis": {},
            "self_strategy_thesis_tree": {"thesis_nodes": []},
            "semantic_passages": {"cases": [], "passages": []},
            "summary_insight_cards": {"cards": [], "case_concept_slots": {"cases": []}},
            "series_positioning": {"series_rows": []},
            "strategy_translation": {},
            "survey_concept_segments": {"segments": []},
            "survey_segment_comparison": {"segments": []},
            "survey_qual_explanation_map": {"rows": [], "topic_rows": []},
            "t_difference_matrix": {"rows": []},
            "t_dimension_confidence_stats": {"rows": []},
            "t_dimension_impact_stats": {"rows": []},
            "t_jtbd_confidence_stats": {"rows": []},
            "t_jtbd_impact_stats": {"rows": []},
            "t_jtbd_packages": {"packages": []},
            "t_persona_slice_cards": {"cards": []},
            "topic_attention_matrix": {"rows": [], "topic_summary_rows": []},
            "user_insight_exposure_tree": {"series_nodes": [], "summary_judgment": "u", "stable_nodes": [], "weak_signal_nodes": [], "boundary_nodes": [], "drilldown_candidate_nodes": []},
            "user_presentation_blocks": {"block_count": 0, "blocks": []},
            "user_strategy_convergence_tree": {"converged_nodes": [], "contested_nodes": [], "not_ready_nodes": []},
            "user_thesis_tree": {"n_band_theses": {}},
            "voc_fact_exposure_tree": {"external_only_nodes": [], "missing_scope_nodes": []},
            "voc_problem_packages": {"packages": []},
            "x_jtbd_confidence_stats": {"rows": []},
            "x_jtbd_impact_stats": {"rows": []},
            "x_observed_positionings": {"positionings": []},
            "x_positioning_confidence_stats": {"rows": []},
            "x_positioning_impact_stats": {"rows": []},
            "x_positioning_packages": {"packages": []},
            "master_judgment_tree": {"summary_judgment": "m", "root_thesis": "r", "branches": []},
            "presentation_tree": {"summary_judgment": "p", "chapter_nodes": []},
            "presentation_page_blocks": {"blocks": []},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            (out_dir / "artifact_manifest.json").write_text(
                json.dumps(
                    {
                        "bundle_id": "cleaning_robot_full_portfolio_ppt_aligned",
                        "bundle_mode": "portfolio_full",
                        "category_name": "扫地机器人",
                        "primary_self_spu_id": "ecovacs_x11",
                        "primary_competitor_spu_id": "portfolio_full",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = mock.Mock(
                bundle_mode="portfolio_full",
                refresh_scope="user_closure",
                analysis_engine="dual_engine_llm",
                llm_profile_path=None,
                qual_reasoning_profile="qual_default",
                thesis_reasoning_profile="thesis_default",
                category_name="机器人产品",
                market=None,
                survey_topic=[],
                require_voc=False,
                time_scope="待补充",
                analysis_goal=[],
            )
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(insight_bundle, "load_runtime_json_artifacts", return_value=runtime_artifacts))
                stack.enter_context(mock.patch.object(insight_bundle, "collect_series_result", side_effect=AssertionError("user_closure should not collect series result")))
                stack.enter_context(mock.patch.object(insight_bundle, "connect", side_effect=AssertionError("user_closure should not connect db")))
                stack.enter_context(mock.patch.object(insight_bundle, "connect_live_voc_preferred", side_effect=AssertionError("user_closure should not connect voc db")))
                exposure_mock = stack.enter_context(mock.patch.object(insight_bundle, "build_user_insight_exposure_tree", return_value={"series_nodes": [], "summary_judgment": "u", "stable_nodes": [], "weak_signal_nodes": [], "boundary_nodes": [], "drilldown_candidate_nodes": []}))
                packet_mock = stack.enter_context(mock.patch.object(insight_bundle, "build_qual_evidence_packet", return_value={"packets": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_strategy_convergence_tree", return_value={"converged_nodes": [], "contested_nodes": [], "not_ready_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_thesis_tree", return_value={"n_band_theses": {}}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_convergence_tree", return_value={"concept_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_self_strategy_thesis_tree", return_value={"thesis_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_master_judgment_tree", return_value={"summary_judgment": "m", "root_thesis": "r", "branches": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_presentation_tree", return_value={"summary_judgment": "p", "chapter_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_presentation_page_blocks", return_value={"blocks": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_presentation_blocks", return_value={"block_count": 0, "blocks": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "run_user_presentation_composer", return_value=("# report\n", {"final_status": "passed", "iteration_count": 1}, "# risks\n")))
                refresh_portfolio_user_chain_runtime(
                    args=args,
                    out_dir=out_dir,
                    style_profile={"banned_phrases": []},
                )
            exposure_mock.assert_not_called()
            packet_mock.assert_not_called()

    def test_refresh_portfolio_user_chain_runtime_target_builder_can_start_inside_user_reasoning(self) -> None:
        class DummyConn:
            def close(self) -> None:
                return None

        runtime_artifacts = {
            "analysis_reflection_report": {"summary_judgment": "还差补数。"},
            "awe_exhibition_signals": {"direct_competitor_signals": []},
            "brand_mindshare_judgments": {"judgments": []},
            "case_concept_slots": {"cases": []},
            "cleaning_robot_theme_registry": {"rows": []},
            "competition_capability_scan": {"rows": []},
            "competition_capture_target_candidates": {"rows": []},
            "competition_generation_analysis": {"rows": []},
            "competition_matchup_matrix": {"rows": []},
            "competition_strategy_bridge": {},
            "competition_thesis_tree": {"thesis_nodes": []},
            "competition_voc_market_split": {"market_rows": []},
            "competition_voc_xtn_breakdown": {"product_rows": []},
            "cross_source_convergence_tree": {"concept_nodes": []},
            "cross_source_hypothesis_board": {"rows": []},
            "cross_source_interpretation": {"interpretations": []},
            "demand_pool_snapshot": {},
            "entry_exposure_tree": {"boundary_nodes": []},
            "generation_comparison": {"series_rows": []},
            "idea_cluster_judgments": {"judgments": []},
            "judgment_acceptance_log": {"rows": []},
            "page_metric_cards": {"rows": []},
            "portfolio_generation_strategy": {},
            "problem_drilldown_packages": {"rows": []},
            "qual_case_reasoning_cards": {"rows": []},
            "qual_evidence_packet": {"packets": []},
            "qual_reasoning_task_board": {"rows": []},
            "qual_theme_reasoning_map": {"rows": []},
            "self_strategy_thesis": {},
            "self_strategy_thesis_tree": {"thesis_nodes": []},
            "semantic_passages": {"cases": [], "passages": []},
            "summary_insight_cards": {"cards": [], "case_concept_slots": {"cases": []}},
            "series_positioning": {"series_rows": []},
            "strategy_translation": {},
            "survey_concept_segments": {"segments": []},
            "survey_segment_comparison": {"segments": []},
            "survey_qual_explanation_map": {"rows": [], "topic_rows": []},
            "t_difference_matrix": {"rows": []},
            "t_dimension_confidence_stats": {"rows": []},
            "t_dimension_impact_stats": {"rows": []},
            "t_jtbd_confidence_stats": {"rows": []},
            "t_jtbd_impact_stats": {"rows": []},
            "t_jtbd_packages": {"packages": []},
            "t_persona_slice_cards": {"cards": []},
            "topic_attention_matrix": {"rows": [], "topic_summary_rows": []},
            "user_insight_exposure_tree": {"series_nodes": [], "summary_judgment": "u", "stable_nodes": [], "weak_signal_nodes": [], "boundary_nodes": [], "drilldown_candidate_nodes": []},
            "user_presentation_blocks": {"block_count": 0, "blocks": []},
            "user_strategy_convergence_tree": {"converged_nodes": [], "contested_nodes": [], "not_ready_nodes": []},
            "user_thesis_tree": {"n_band_theses": {}},
            "voc_fact_exposure_tree": {"external_only_nodes": [], "missing_scope_nodes": []},
            "voc_problem_packages": {"packages": []},
            "x_jtbd_confidence_stats": {"rows": []},
            "x_jtbd_impact_stats": {"rows": []},
            "x_observed_positionings": {"positionings": []},
            "x_positioning_confidence_stats": {"rows": []},
            "x_positioning_impact_stats": {"rows": []},
            "x_positioning_packages": {"packages": []},
            "master_judgment_tree": {"summary_judgment": "m", "root_thesis": "r", "branches": []},
            "presentation_tree": {"summary_judgment": "p", "chapter_nodes": []},
            "presentation_page_blocks": {"blocks": []},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            (out_dir / "artifact_manifest.json").write_text(
                json.dumps(
                    {
                        "bundle_id": "cleaning_robot_full_portfolio_ppt_aligned",
                        "bundle_mode": "portfolio_full",
                        "category_name": "扫地机器人",
                        "primary_self_spu_id": "ecovacs_x11",
                        "primary_competitor_spu_id": "portfolio_full",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = mock.Mock(
                bundle_mode="portfolio_full",
                refresh_scope="user_reasoning",
                target_builder=["build_cross_source_interpretation"],
                target_artifact=[],
                analysis_engine="dual_engine_llm",
                llm_profile_path=None,
                qual_reasoning_profile="qual_default",
                thesis_reasoning_profile="thesis_default",
                category_name="机器人产品",
                market=None,
                survey_topic=[],
                require_voc=False,
                time_scope="待补充",
                analysis_goal=[],
            )
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(insight_bundle, "load_runtime_json_artifacts", return_value=runtime_artifacts))
                stack.enter_context(mock.patch.object(insight_bundle, "collect_series_result", return_value={"selected_spus": [{"spu_id": "ecovacs_x11"}]}))
                stack.enter_context(mock.patch.object(insight_bundle, "connect", return_value=DummyConn()))
                stack.enter_context(mock.patch.object(insight_bundle, "connect_live_voc_preferred", return_value=DummyConn()))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_summary_theme_sections", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "build_summary_theme_evidence", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_wave_sample_count", return_value=10))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_survey_capability_question_summaries", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "build_survey_theme_evidence", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_voc_theme_rows", return_value=([], [], [])))
                stack.enter_context(mock.patch.object(insight_bundle, "build_voc_theme_evidence", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_tables", return_value=([], [], [], [])))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_user_attention_source_rows", return_value=[]))
                stack.enter_context(mock.patch.object(insight_bundle, "fetch_survey_open_answer_rows", return_value=[]))
                packet_mock = stack.enter_context(mock.patch.object(insight_bundle, "build_qual_evidence_packet", return_value={"packets": []}))
                reasoning_mock = stack.enter_context(mock.patch.object(insight_bundle, "run_dual_engine_reasoning", return_value={"qual_reasoning_task_board": {"rows": []}, "qual_case_reasoning_cards": {"rows": []}, "qual_theme_reasoning_map": {"rows": []}, "cross_source_hypothesis_board": {"rows": []}, "candidate_claims": [], "fallback_status": ""}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_interpretation", return_value={"interpretations": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_series_positioning", return_value={"series_rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_strategy_translation", return_value={}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_survey_qual_explanation_map", return_value={"rows": [], "topic_rows": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_insight_exposure_tree", return_value={"series_nodes": [], "summary_judgment": "u", "stable_nodes": [], "weak_signal_nodes": [], "boundary_nodes": [], "drilldown_candidate_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_strategy_convergence_tree", return_value={"converged_nodes": [], "contested_nodes": [], "not_ready_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_thesis_tree", return_value={"n_band_theses": {}}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_cross_source_convergence_tree", return_value={"concept_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_self_strategy_thesis_tree", return_value={"thesis_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_master_judgment_tree", return_value={"summary_judgment": "m", "root_thesis": "r", "branches": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_presentation_tree", return_value={"summary_judgment": "p", "chapter_nodes": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_presentation_page_blocks", return_value={"blocks": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "build_user_presentation_blocks", return_value={"block_count": 0, "blocks": []}))
                stack.enter_context(mock.patch.object(insight_bundle, "run_user_presentation_composer", return_value=("# report\n", {"final_status": "passed", "iteration_count": 1}, "# risks\n")))
                refresh_portfolio_user_chain_runtime(
                    args=args,
                    out_dir=out_dir,
                    style_profile={"banned_phrases": []},
                )
            packet_mock.assert_not_called()
            reasoning_mock.assert_not_called()

    def test_main_dispatches_user_chain_refresh_for_portfolio_full(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            with mock.patch.object(insight_bundle, "read_json", return_value={"banned_phrases": []}), \
                mock.patch.object(insight_bundle, "choose_bundle_id", return_value="bundle"), \
                mock.patch.object(insight_bundle, "ensure_out_dir", return_value=out_dir), \
                mock.patch.object(insight_bundle, "refresh_portfolio_user_chain_runtime", return_value=out_dir / "artifact_manifest.json") as refresh_mock, \
                mock.patch.object(sys, "argv", ["generate_insight_bundle.py", "--bundle-mode", "portfolio_full", "--refresh-scope", "user_chain", "--out-dir", temp_dir]):
                insight_bundle.main()
            refresh_mock.assert_called_once()

    def test_build_presentation_page_blocks_surfaces_n_bands_in_top_user_pages(self) -> None:
        payload = build_presentation_page_blocks(
            x_observed_positionings={"positionings": []},
            generation_comparison={"series_rows": []},
            competition_generation_analysis={},
            competition_voc_xtn_breakdown={},
            competition_voc_market_split={"market_summary_rows": []},
            awe_exhibition_signals={"direct_competitor_signals": []},
            competition_capability_scan={"rows": []},
            competition_matchup_matrix={"rows": []},
            competition_strategy_bridge={},
            self_strategy_thesis={},
            analysis_reflection_report={"rewrite_priority_pages": [], "next_data_moves": []},
            competition_capture_target_candidates={"rows": []},
            entry_exposure_tree={"boundary_nodes": []},
            voc_fact_exposure_tree={"external_only_nodes": [], "missing_scope_nodes": []},
            user_insight_exposure_tree={
                "summary_judgment": "用户暴露树",
                "series_nodes": [
                    {"series_family": "X", "children": [], "lead_judgment": "X"},
                    {"series_family": "T", "children": [], "lead_judgment": "T"},
                    {
                        "series_family": "N",
                        "children": [
                            {"node_label": "N_single", "summary": "N_single 当前主暴露先落在 `边角问题；维护/基站`。"},
                            {"node_label": "N_aes", "summary": "N_aes 当前主暴露先落在 `智能交互/地图；边角问题`。"},
                            {"node_label": "N_omni", "summary": "N_omni 当前仍缺稳定自家 VOC 样本。"},
                        ],
                        "lead_judgment": "N 已拆成三带。",
                    },
                ],
                "stable_nodes": [],
                "weak_signal_nodes": [],
                "boundary_nodes": [],
                "drilldown_candidate_nodes": [],
            },
            user_strategy_convergence_tree={"converged_nodes": [], "not_ready_nodes": [], "summary_judgment": "收敛树"},
            user_thesis_tree={
                "x_core_thesis": "X thesis",
                "t_core_thesis": "T thesis",
                "n_band_theses": {
                    "N_single": "N_single thesis",
                    "N_aes": "N_aes thesis",
                    "N_omni": "N_omni thesis",
                },
                "what_users_care_most": [],
                "what_ecovacs_is_winning_on": [],
                "what_ecovacs_is_losing_on": [],
                "what_should_not_be_overstated": [],
            },
            topic_attention_matrix={
                "rows": [],
                "topic_summary_rows": [
                    {"series_family": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "污渍问题", "mention_count": 10, "mention_rate": 0.1, "positive_count": 0, "negative_count": 10, "positive_rate": 0.0, "negative_rate": 1.0, "net_sentiment_signal": "负向占优"},
                    {"series_family": "X", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "边角问题", "mention_count": 40, "mention_rate": 0.4, "positive_count": 35, "negative_count": 3, "positive_rate": 0.875, "negative_rate": 0.075, "net_sentiment_signal": "正向占优"},
                    {"series_family": "T", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "边角问题", "mention_count": 12, "mention_rate": 0.12, "positive_count": 10, "negative_count": 2, "positive_rate": 0.8, "negative_rate": 0.2, "net_sentiment_signal": "正向占优"},
                    {"series_family": "T", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "污渍问题", "mention_count": 8, "mention_rate": 0.08, "positive_count": 0, "negative_count": 8, "positive_rate": 0.0, "negative_rate": 1.0, "net_sentiment_signal": "负向占优"},
                    {"series_family": "N", "user_band": "N_single", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "维护/基站", "mention_count": 16, "mention_rate": 0.16, "positive_count": 6, "negative_count": 9, "positive_rate": 0.375, "negative_rate": 0.5625, "net_sentiment_signal": "负向占优"},
                    {"series_family": "N", "user_band": "N_single", "cohort_scope": "科沃斯样本", "market_scope": "中国", "topic_name": "边角问题", "mention_count": 30, "mention_rate": 0.3, "positive_count": 24, "negative_count": 3, "positive_rate": 0.8, "negative_rate": 0.1, "net_sentiment_signal": "正向占优"},
                    {"series_family": "N", "user_band": "N_aes", "cohort_scope": "科沃斯样本", "market_scope": "海外", "topic_name": "智能交互/地图", "mention_count": 14, "mention_rate": 0.14, "positive_count": 3, "negative_count": 8, "positive_rate": 0.214, "negative_rate": 0.571, "net_sentiment_signal": "负向占优"},
                    {"series_family": "N", "user_band": "N_aes", "cohort_scope": "科沃斯样本", "market_scope": "海外", "topic_name": "避障/卡困", "mention_count": 18, "mention_rate": 0.18, "positive_count": 12, "negative_count": 2, "positive_rate": 0.667, "negative_rate": 0.111, "net_sentiment_signal": "正向占优"},
                ],
            },
            problem_drilldown_packages={"rows": []},
            survey_qual_explanation_map={"rows": [], "topic_rows": []},
            cross_source_convergence_tree={"concept_nodes": []},
            competition_thesis_tree={"thesis_nodes": []},
            self_strategy_thesis_tree={
                "thesis_nodes": [
                    {"series_family": "X", "root_claim": "X root", "what_not_to_do": "X no", "must_wait_for_data": "-"},
                    {"series_family": "T", "root_claim": "T root", "what_not_to_do": "T no", "must_wait_for_data": "-"},
                    {"series_family": "N", "root_claim": "N root", "what_not_to_do": "N no", "must_wait_for_data": "-"},
                ]
            },
            master_judgment_tree={"summary_judgment": "master", "root_thesis": "root", "branches": []},
            presentation_tree={"chapter_nodes": []},
            demand_pool_snapshot={},
            portfolio_generation_strategy={
                "roadmap_focus_rows": [
                    {"stage": "当前轮次", "x_message": "X 主讲", "t_message": "T 主讲", "n_message": "N 主讲 omni / aes / single", "not_now": "先别讲", "core_blocker": "阻塞"}
                ]
            },
            x_positioning_packages={"packages": []},
            x_positioning_confidence_stats={"rows": []},
            x_positioning_impact_stats={"rows": []},
            x_jtbd_confidence_stats={"rows": []},
            x_jtbd_impact_stats={"rows": []},
            t_persona_slice_cards={"cards": []},
            t_difference_matrix={"rows": []},
            t_jtbd_packages={"packages": []},
            t_dimension_confidence_stats={"rows": []},
            t_dimension_impact_stats={"rows": []},
            t_jtbd_confidence_stats={"rows": []},
            t_jtbd_impact_stats={"rows": []},
            brand_mindshare_judgments={"judgments": []},
            idea_cluster_judgments={"judgments": []},
            strategy_translation={"priority_buckets": {}, "top_problem_packages": []},
            cross_source_interpretation={"interpretations": []},
            voc_problem_packages={"packages": []},
            page_metric_cards={"rows": []},
        )
        topic_block = next(block for block in payload["blocks"] if block["page_id"] == "user_topic_attention_pages")
        thesis_block = next(block for block in payload["blocks"] if block["page_id"] == "user_thesis_pages")
        exposure_block = next(block for block in payload["blocks"] if block["page_id"] == "user_exposure_tree_pages")
        competition_conclusion_block = next(block for block in payload["blocks"] if block["page_id"] == "competition_conclusion_pages")
        self_value_block = next(block for block in payload["blocks"] if block["page_id"] == "self_value_pages")
        roadmap_block = next(block for block in payload["blocks"] if block["page_id"] == "roadmap_action_pages")
        topic_labels = [row[0] for row in topic_block["supporting_table"]["rows"]]
        topic_roles = [row[1] for row in topic_block["supporting_table"]["rows"]]
        self.assertIn("N_single", topic_labels)
        self.assertIn("N_aes", topic_labels)
        self.assertIn("N_omni", topic_labels)
        self.assertIn("负向焦点", topic_roles)
        self.assertIn("正向锚点", topic_roles)
        self.assertIn("边界声明", topic_roles)
        self.assertEqual(topic_block["supporting_table"]["headers"][0], "系列/带宽")
        thesis_labels = [row[0] for row in thesis_block["supporting_table"]["rows"]]
        self.assertIn("N_single", thesis_labels)
        self.assertIn("N_aes", thesis_labels)
        self.assertIn("N_omni", thesis_labels)
        exposure_labels = [row[0] for row in exposure_block["supporting_table"]["rows"]]
        self.assertIn("N_single", exposure_labels)
        self.assertIn("N_aes", exposure_labels)
        self.assertIn("N_omni", exposure_labels)
        self.assertIn("N（三带）", competition_conclusion_block["heading"])
        self.assertIn("N（三带）", roadmap_block["supporting_table"]["headers"][3])
        self.assertTrue(any(row[0] == "N（三带）" for row in self_value_block["supporting_table"]["rows"]))


if __name__ == "__main__":
    unittest.main()
