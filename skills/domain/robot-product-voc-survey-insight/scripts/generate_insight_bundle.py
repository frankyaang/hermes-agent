#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from textwrap import shorten
from types import SimpleNamespace
from zipfile import ZipFile
import sys

from generate_analysis_scaffold import (
    build_cross_source_tables,
    build_summary_theme_evidence,
    build_survey_theme_evidence,
    build_voc_theme_evidence,
    build_action_plan_rows,
    build_coverage_gap_rows,
    build_feature_exposure_rows,
    build_goal_feature_map_rows,
    build_scaffold,
    fetch_proxy_summary_rows,
    fetch_proxy_survey_rows,
    fetch_summary_theme_sections,
    fetch_survey_capability_question_summaries,
    fetch_voc_product_snapshot,
    fetch_voc_theme_rows,
    fetch_wave_sample_count,
    demote_headings,
    infer_goal_codes,
    load_action_context,
    markdown_table,
    SURVEY_KEYWORDS,
    resolve_analysis_goal_text,
    split_scaffold_sections,
    strip_title_block,
)
from derive_higher_order_insights import (
    PPT_CONCEPT_SCHEMA,
    build_brand_mindshare_map,
    build_brand_mindshare_judgments,
    build_competition_voc_market_split,
    build_competition_voc_xtn_breakdown,
    build_concept_comparison_matrix,
    build_concept_pain_need_map,
    build_concept_support_stats,
    build_x_case_signal_profiles,
    build_x_observed_positionings,
    build_idea_pool_clusters,
    build_idea_cluster_judgments,
    build_page_metric_cards,
    build_series_positioning,
    build_strategy_translation,
    build_t_dimension_confidence_stats,
    build_t_dimension_impact_stats,
    build_t_difference_matrix,
    build_t_jtbd_confidence_stats,
    build_t_jtbd_impact_stats,
    build_t_jtbd_packages,
    build_t_persona_slice_cards,
    build_t_series_concept_map,
    build_x_jtbd_confidence_stats,
    build_x_jtbd_impact_stats,
    build_x_positioning_confidence_stats,
    build_x_positioning_impact_stats,
    build_x_series_concept_map,
    build_x_positioning_packages,
    build_cross_source_interpretation,
    build_semantic_passages,
    build_survey_concept_segments,
    build_survey_segment_comparison,
    build_voc_problem_packages,
    extract_summary_insight_cards,
    infer_series_code,
    normalize_voc_market_scope,
)
from llm_reasoning_engine import (
    build_qual_evidence_packet,
    evaluate_candidate_claims,
    run_dual_engine_reasoning,
)
from presentation_report_renderer import render_presentation_main_report
from run_multisource_preflight import (
    INTERVIEW_DB,
    SUMMARY_DB,
    SURVEY_DB,
    TRUTH_DB,
    VOC_DB,
    collect_preflight_result,
    ensure_voc_compat_views,
)
from user_chain_dependency_registry import (
    coerce_registry_targets,
    load_user_chain_dependency_registry,
    resolve_user_chain_active_steps,
    resolve_user_chain_start_step,
)

SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_ROOT.parent
ASSETS_ROOT = SKILL_ROOT / "assets"


def configured_asset_path(env_var: str, relative_path: str) -> Path:
    configured = os.getenv(env_var)
    if configured:
        return Path(configured).expanduser()
    return ASSETS_ROOT / relative_path


RESPONSE_CURATOR_SCRIPT_DIR = SKILLS_ROOT / "ResponseCurator" / "scripts"
if str(RESPONSE_CURATOR_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(RESPONSE_CURATOR_SCRIPT_DIR))

try:
    from package_primary_artifacts import (
        apply_response_curator_to_primary_artifacts,
        build_artifact_packaging_request,
    )
except ModuleNotFoundError:
    def build_artifact_packaging_request(
        *,
        artifact_index: dict[str, str],
        category_name: str,
        market: str,
        time_scope: str,
        analysis_goal_text: str,
        bundle_mode: str,
        style_profile: dict[str, object],
        higher_order_artifacts: dict[str, object],
    ) -> dict[str, object]:
        return {
            "artifact_index": artifact_index,
            "category_name": category_name,
            "market": market,
            "time_scope": time_scope,
            "analysis_goal_text": analysis_goal_text,
            "bundle_mode": bundle_mode,
            "style_profile": style_profile,
            "higher_order_artifacts": higher_order_artifacts,
        }

    def apply_response_curator_to_primary_artifacts(request: dict[str, object]) -> dict[str, object]:
        artifact_index = request.get("artifact_index", {})
        packaged_artifacts = []
        if isinstance(artifact_index, dict):
            for artifact_key, path in artifact_index.items():
                if artifact_key == "artifact_manifest":
                    continue
                packaged_artifacts.append(
                    {
                        "artifact_key": str(artifact_key),
                        "path": str(path),
                        "status": "skipped",
                        "fallback_used": True,
                        "display_primitives_plan": {},
                    }
                )
        return {
            "status": "skipped",
            "mode": "deliverable_artifact_packaging",
            "scope": "primary_artifacts_only",
            "packaged_artifacts": packaged_artifacts,
            "packaging_version": "hermes-local-fallback",
            "packaged_at": datetime.now().isoformat(timespec="seconds"),
            "fallback_used": True,
            "fallback_reason": "ResponseCurator skill is not bundled in this Hermes environment",
        }

STYLE_PROFILE_PATH = configured_asset_path("HERMES_PPT_AUTHOR_STYLE_PROFILE", "ppt-author-style-profile.json")
COMPETITION_GENERATION_REGISTRY_PATH = SKILL_ROOT / "references" / "competition_generation_registry.json"
DEMAND_POOL_XLSX_PATH = configured_asset_path("HERMES_DEMAND_POOL_XLSX", "需求池.xlsx")
AWE_DOCX_PATH = configured_asset_path("HERMES_AWE_DOCX", "Untitled (2).docx")
AWE_2026_DOCX_PATH = configured_asset_path("HERMES_AWE_2026_DOCX", "AWE2026产品经理逛展计划.docx")
COMPETITION_INTELLIGENCE_DOCX_PATH = configured_asset_path("HERMES_COMPETITION_INTELLIGENCE_DOCX", "竞争分析-补充AWE和情报.docx")
DREAME_ROADMAP_DOCX_PATH = configured_asset_path("HERMES_DREAME_ROADMAP_DOCX", "追觅竞对分析（3.28）.docx")
COMPETITION_CONFIG_XLSX_PATH = configured_asset_path("HERMES_COMPETITION_CONFIG_XLSX", "产品配置表.xlsx")
COMPETITION_TEST_XLSX_PATH = configured_asset_path("HERMES_COMPETITION_TEST_XLSX", "测试数据.xlsx")

THEMES = [
    ("清洁效果与水痕污渍", ["水渍水痕", "顽固污渍拖不干净", "拖地效果差", "清洁效果差"]),
    ("边角与覆盖率", ["边角漏扫", "边角清洁效果差", "清扫效率低"]),
    ("噪音体验", ["扫拖噪音大"]),
    ("避障越障与卡困", ["台阶过不去", "避障失败", "越障能力差", "地毯卡困"]),
]
GENERATION_COMPARE_CONFIG = [
    {
        "series_code": "X",
        "current_spu_id": "ecovacs_x11",
        "current_wave_name": "X11早期用户调研数据",
        "previous_spu_id": "ecovacs_x8",
        "previous_wave_name": "X8早期用户调研数据",
        "previous_reference_wave_name": "X8成熟用户调研数据",
        "heading": "#### X 系列：X11 vs X8",
    },
    {
        "series_code": "T",
        "current_spu_id": "ecovacs_t80s",
        "current_wave_name": "T80S早期用户调研数据",
        "previous_spu_id": "ecovacs_t80",
        "previous_wave_name": "T80早期用户调研数据",
        "previous_reference_wave_name": "",
        "heading": "#### T 系列：T80S vs T80",
    },
]
GENERATION_REFERENCE_WAVES = {
    "cleaning_needs": "科沃斯扫地机器人清洁需求调研",
    "multi_robot": "YIKO - 中国多机协作调研报告",
}
GENERATION_THEME_RULES = {
    "清洁底线": ("污渍", "水渍", "边角", "漏扫", "漏拖", "顽固污渍", "地毯清洁不干净", "扫拖不干净"),
    "维护负担": ("维护", "清理", "清洁槽", "腔体", "频次", "异味", "拖布", "滚刷", "尘袋"),
    "低介入托管": ("免维护", "自动", "托管", "不用自己", "少操心", "主动", "排污", "自净", "零动手"),
    "多机协同": ("多台", "统一控制", "协同", "分区同步", "第二台", "接力", "跨楼层"),
}
DEMAND_POOL_THEME_RULES = {
    "清洁效果与水痕污渍": ("污渍", "水渍", "拖地", "顽固", "油污", "地面光洁"),
    "边角与覆盖率": ("边角", "墙角", "凳脚", "桌角", "门后", "缝隙", "踢脚线", "边缘"),
    "避障越障与卡困": ("门槛", "台阶", "卡困", "越障", "通过性", "低矮空间", "跃层"),
    "维护与基站操作": ("机身清理", "主机维护", "基站", "尘盒", "滚刷", "拖布", "异味", "清理", "维护"),
    "智能/App/语音/地图": ("智能", "语音", "APP", "地图", "巡航", "主动", "识别"),
    "多机协同与统一控制": ("多机", "协同", "统一控制", "联动", "第二台"),
}
PORTFOLIO_FULL_SERIES = [
    {
        "series_code": "X",
        "series_label": "X 系列",
        "cohort_ids": [
            "x_series_x11_self_previous",
            "x_series_x11_2025_competitors",
            "x_series_x12_self_current",
            "x_series_x12_latest_competitors",
        ],
        "analysis_title": "X 系列全量本品与竞品用户分析",
    },
    {
        "series_code": "T",
        "series_label": "T 系列",
        "cohort_ids": [
            "t_series_t80s_self_previous",
            "t_series_t80s_previous_competitors",
            "t_series_t90_self_current",
            "t_series_t90_current_competitors",
        ],
        "analysis_title": "T 系列全量本品与竞品用户分析",
    },
]
PORTFOLIO_FULL_COHORT_IDS = [cohort_id for series in PORTFOLIO_FULL_SERIES for cohort_id in series["cohort_ids"]]

USER_ATTENTION_TOPIC_RULES = [
    {
        "topic_name": "污渍问题",
        "topic_groups": {"污渍与液体痕迹", "顽固污渍清洁"},
        "keywords": ("污渍", "水渍", "水痕", "油污", "酱汁", "口水", "鼻子印", "脚印", "果酱", "汤汁", "水垢", "油膜"),
    },
    {
        "topic_name": "边角问题",
        "topic_groups": {"清洁与核心能力"},
        "keywords": ("边角", "墙角", "门后", "死角", "漏扫", "覆盖", "桌椅腿", "窄缝", "踢脚线", "边缘"),
    },
    {
        "topic_name": "避障/卡困",
        "topic_groups": {"避障与越障脱困", "建图与路径导航"},
        "keywords": ("避障", "越障", "卡困", "脱困", "门槛", "台阶", "路径", "卡住", "地毯卡困"),
    },
    {
        "topic_name": "维护/基站",
        "topic_groups": {"维护与基站操作"},
        "keywords": ("维护", "基站", "清理", "发臭", "异味", "尘袋", "滚刷", "边刷", "缠绕", "自清洁", "清洁槽"),
    },
    {
        "topic_name": "噪音",
        "topic_groups": {"噪音体验"},
        "keywords": ("噪音", "声音大", "太吵", "扰民", "吵"),
    },
    {
        "topic_name": "智能交互/地图",
        "topic_groups": {"App/语音/控制", "建图与路径导航"},
        "keywords": ("地图", "app", "语音", "交互", "路径", "分区", "识别", "虚拟墙", "导航"),
    },
]

VALUE_TRANSLATION_RULES = [
    {
        "keywords": ("水渍", "水痕", "拖地", "清洁效果", "清扫效率", "顽固污渍", "边角", "覆盖", "漏扫", "漏拖", "地毯"),
        "pain_point": "清洁结果不稳定，用户容易返工或怀疑它有没有把事做完。",
        "need": "更稳的清洁结果、更少返工、更完整覆盖。",
        "value_axis": "功能结果价值",
        "axis_statement": "更稳的清洁结果、更少返工、更完整覆盖",
    },
    {
        "keywords": ("避障", "越障", "卡困", "回充", "地图", "路径", "故障", "报警", "离线", "脱困"),
        "pain_point": "托管过程不成立，用户不得不重新接管和善后。",
        "need": "少接管、少救援、关键场景下也敢放手托管。",
        "value_axis": "信任/负担转移价值",
        "axis_statement": "少接管、少救援、真托管",
    },
    {
        "keywords": ("维护", "基站", "滚刷", "尘盒", "异味", "清洁槽", "拖布", "集尘", "烘干", "缠绕"),
        "pain_point": "解放双手没有闭环，用户还是得频繁维护和兜底。",
        "need": "更低的维护负担、更完整的免维护闭环。",
        "value_axis": "信任/负担转移价值",
        "axis_statement": "少维护、少打理、解放双手有闭环",
    },
    {
        "keywords": ("噪音", "尺寸", "超薄", "低矮", "外观", "家居", "家具", "静音"),
        "pain_point": "产品融入感不稳定，容易打扰用户或侵占空间。",
        "need": "更低打扰、更强融入感，但这类价值默认不能抢主价值叙事。",
        "value_axis": "边界项",
        "axis_statement": "静音、融入感、轻薄等加分项",
    },
]

VALUE_BOUNDARY_KEYWORDS = ("科技", "智能", "超薄", "轻薄", "外观", "多机", "协同", "生态", "统一控制")
VALUE_PROPOSITION_CARD_TYPES = (
    "痛点-诉求翻译卡",
    "核心价值主张卡",
    "竞品改选逻辑卡",
    "next-gen 定义输入卡",
)
VALUE_PROPOSITION_RED_LINES = (
    "只有高频、跨源、能解释买/改选/失望的信号，才允许进入核心价值主张。",
    "单一参数优势、弱样本好评、表达型亮点默认只能进加分项、背景信号或远期机会。",
    "没有解释用户为什么因此更愿意买或更愿意改选的点，不能直接升成价值主张。",
)
COMPETITION_ENGINEERING_CARD_TYPES = (
    "价值-配置-测试映射卡",
    "本品兑现能力卡",
    "竞品抢票证据卡",
    "断层归因卡",
    "next-gen 配置/测试输入卡",
)
FUTURE_INTELLIGENCE_CARD_TYPES = (
    "行业终局信号卡",
    "强竞品意图假设卡",
    "Roadmap压力测试卡",
    "未来竞争策略输入卡",
)
REPORT_ASSEMBLY_CARD_TYPES = (
    "执行摘要卡",
    "系列战略卡",
    "竞争压力卡",
    "未来压力卡",
    "需求落位卡",
    "5W2H行动卡",
)
REPORT_ASSEMBLY_RED_LINES = (
    "报告组装层只压缩已有判断，不新增底层统计口径。",
    "没有真实字段支撑时，不输出固定百分比、不输出确定 KANO 分数。",
    "AWE 概念机和追觅路线图只能作为前瞻压力测试，不能写成确定性上市能力。",
    "N 系只作为产品线承接边界出现，不强行写成与 X/T 同等深度专场。",
)
FUTURE_INTELLIGENCE_RED_LINES = (
    "AWE 概念机和展会演示默认只是行业方向信号，不写成确定上市能力。",
    "追觅 2027-2028 路线图默认是强竞品意图假设，成熟度和量产节奏必须标注未证实。",
    "前瞻情报只做 Roadmap 压力测试，不替代 VOC、配置表和测试数据的当前证据。",
    "250℃蒸汽、45000Pa、轮足、飞行、爬楼等不直接拔成我方主卖点，必须先回到用户价值轴判断。",
)
FUTURE_SIGNAL_GROUP_RULES = [
    {
        "signal_group": "空间形态越界",
        "keywords": ("轮足", "飞行", "机械手", "机械臂", "爬楼", "多台阶", "越障", "低空间", "低矮", "窄缝"),
        "value_axes": ("复杂地形通过性", "真托管少接管", "无感融入"),
        "pm_reading": "AWE 这类信号说明品类边界在从二维清洁走向三维家庭空间，但短期更适合进入高端场景防御和远期形态预研。",
    },
    {
        "signal_group": "生态隐形融合",
        "keywords": ("全嵌", "平嵌", "洗扫拖集成站", "上下水", "全屋", "人车家", "生态", "平嵌式", "集成站"),
        "value_axes": ("无感融入", "免维护闭环"),
        "pm_reading": "行业终局不只是单机更强，而是基站和家装空间一起隐形化；这优先影响 X 系高端形态定义。",
    },
    {
        "signal_group": "具身智能托管",
        "keywords": ("具身智能", "AI大模型", "大模型", "机械手抓取", "主动管家", "多光谱", "动态脏污", "区域优先级", "OmniSight"),
        "value_axes": ("真托管少接管",),
        "pm_reading": "关键不是宣传更聪明，而是用户不用提前收拾、不需要救场，托管结果能被持续相信。",
    },
    {
        "signal_group": "清洁技术前沿",
        "keywords": ("蒸汽", "喷雾", "喷水", "高温", "滚筒", "吸力", "Pa", "防缠", "边刷", "拖布外扩", "高转速"),
        "value_axes": ("清洁结果可信", "免维护闭环"),
        "pm_reading": "清洁技术会继续卷参数，但 PM 判断必须回到水痕、轮胎印、顽渍返工和毛发维护是否真的下降。",
    },
    {
        "signal_group": "商业模式变化",
        "keywords": ("订阅", "耗材订阅", "云服务", "ARPU", "毛利率", "服务化", "商业模式"),
        "value_axes": ("免维护闭环", "无感融入"),
        "pm_reading": "订阅化只有在免维护闭环可信时才有商业意义，不能脱离用户价值直接做经营想象。",
    },
]
DREAME_ROADMAP_SIGNAL_RULES = [
    {
        "year": "2027",
        "value_axis": "无感融入",
        "technology_signal": "7-8cm 超薄集成",
        "keywords": ("7-8cm", "7-8", "超薄", "阿基米德", "机身高度"),
        "maturity_status": "maturity_unverified",
        "pm_reading": "这是 X 系高端形态压力，不应直接覆盖 T 系主销答案。",
    },
    {
        "year": "2027",
        "value_axis": "清洁结果可信",
        "technology_signal": "800转/min滚筒 + 250℃蒸汽",
        "keywords": ("800", "250℃", "250°", "蒸汽", "滚筒"),
        "maturity_status": "maturity_unverified",
        "pm_reading": "不要默认跟温度和转速，先验证是否减少水痕、轮胎印和顽渍返工。",
    },
    {
        "year": "2027",
        "value_axis": "清洁结果可信",
        "technology_signal": "45000Pa 大吸力",
        "keywords": ("45000Pa", "45000", "大吸力"),
        "maturity_status": "maturity_unverified",
        "pm_reading": "吸力是可传播参数，但产品定义仍要回到颗粒、宠物毛发和噪声之间的体验平衡。",
    },
    {
        "year": "2027",
        "value_axis": "真托管少接管",
        "technology_signal": "多光谱污渍识别与区域优先级规划",
        "keywords": ("多光谱", "污渍识别", "区域优先级", "路径规划"),
        "maturity_status": "maturity_unverified",
        "pm_reading": "如果能稳定识别并自动调策略，会抢托管心智；但当前仍需测试闭环证明。",
    },
    {
        "year": "2027",
        "value_axis": "复杂地形通过性",
        "technology_signal": "爬楼机器人二代与多台阶越障",
        "keywords": ("爬楼", "多台阶", "越障", "轮足"),
        "maturity_status": "maturity_unverified",
        "pm_reading": "进入远期形态预研，不宜直接承诺为下一代主卖点。",
    },
    {
        "year": "2027",
        "value_axis": "免维护闭环",
        "technology_signal": "固态电池闪充与臭氧除臭",
        "keywords": ("固态电池", "闪充", "臭氧", "除臭"),
        "maturity_status": "maturity_unverified",
        "pm_reading": "这类信号会影响托管连续性和异味心智，但需要长期使用验证。",
    },
    {
        "year": "2028",
        "value_axis": "清洁结果可信",
        "technology_signal": "滚筒机械臂深入 5cm 窄缝",
        "keywords": ("5cm", "窄缝", "滚筒机械臂", "深入"),
        "maturity_status": "potential_gap",
        "pm_reading": "窄缝清洁可能形成一代差压力，应作为 X 系高端清洁完整性的补洞项。",
    },
    {
        "year": "2028",
        "value_axis": "免维护闭环",
        "technology_signal": "干湿垃圾自动分离",
        "keywords": ("干湿垃圾", "干湿分离", "湿垃圾"),
        "maturity_status": "future_risk",
        "pm_reading": "湿垃圾免维护是高端托管核心战场，不能只按清洁参数防守。",
    },
    {
        "year": "2028",
        "value_axis": "免维护闭环",
        "technology_signal": "自动换滚筒 4-6 组",
        "keywords": ("自动换滚筒", "4-6", "4—6", "换滚筒"),
        "maturity_status": "future_risk",
        "pm_reading": "这是潜在代差风险，但必须标注成熟度未证实，不能把路线图当量产事实。",
    },
    {
        "year": "2028",
        "value_axis": "免维护闭环",
        "technology_signal": "污水箱自洁与自洁水路高压喷洗",
        "keywords": ("污水箱自洁", "清洁槽自洁", "高压喷洗", "滚筒表面涂层"),
        "maturity_status": "future_risk",
        "pm_reading": "基站深度自清洁会改变用户对真免维护的预期，应进入测试标准升级。",
    },
]
ROADMAP_STRESS_AXIS_RULES = [
    {
        "value_axis": "清洁结果可信",
        "stress_action": "坚持",
        "pm_judgment": "坚持体验战，不被 250℃蒸汽、45000Pa 牵着走；最终验收应看少水痕、少轮胎印、少顽渍返工。",
        "priority_correction": "保留清洁结果可信为主轴，但把水痕、轮胎印、顽渍返工做成更硬的测试门槛。",
        "do_not_misfollow": "不要把更高温度、更大吸力直接当成主价值主张。",
    },
    {
        "value_axis": "免维护闭环",
        "stress_action": "加速",
        "pm_judgment": "自动换滚筒、干湿分离、污水箱自洁会把高端托管竞争从清洁结果推向维护闭环。",
        "priority_correction": "X 系优先防御湿垃圾和滚筒长期自洁，T 系优先把维护不烦做成主销默认答案。",
        "do_not_misfollow": "不要只做单点自清洁，要证明连续免干预和异味可控。",
    },
    {
        "value_axis": "真托管少接管",
        "stress_action": "加速",
        "pm_judgment": "多光谱识别、区域优先级规划和机械手会抢托管心智，但真正要守住的是用户不用救场。",
        "priority_correction": "加速动态污渍识别、避障救场和任务规划测试，把聪明感落到少接管。",
        "do_not_misfollow": "不要把 AI 名词堆成主卖点，必须回到不救场、不预收拾。",
    },
    {
        "value_axis": "复杂地形通过性",
        "stress_action": "观察",
        "pm_judgment": "轮足、爬楼、飞行代表远期形态越界，短期应做预研与高端场景防御，不宜硬塞进本代主卖点。",
        "priority_correction": "保留远期形态预研，当前更优先补真实门槛、地毯、低矮空间通过性。",
        "do_not_misfollow": "不要为了形态炫技牺牲可靠性、成本和清洁结果。",
    },
    {
        "value_axis": "无感融入",
        "stress_action": "补洞",
        "pm_judgment": "7-8cm 超薄、全嵌平嵌、洗扫拖集成站会改变高端家居融入预期，对 X 系影响大于 T 系。",
        "priority_correction": "X 系补高端形态定义和家装融合证据，T 系把轻薄作为成本约束下的加分项。",
        "do_not_misfollow": "不要让超薄抢掉结果可信和托管可信，也不要把 T 系推入不经济的形态战。",
    },
]
VALUE_CONFIG_TEST_AXIS_RULES = [
    {
        "value_axis": "清洁结果可信",
        "user_certainty": "用户买的是拖后结果可信、边角不返工、复杂污渍也能把事做完。",
        "config_fields": ("真空度", "拖布类型", "拖布外扩", "拖布到边", "边刷外扩", "边刷到角", "拖地下压力", "地毯深度清洁"),
        "test_keywords": ("直线CE", "直线拖地效果", "边角覆盖率", "拖布到边距离", "水渍", "地毯黑盒", "地板黑盒"),
        "gap_type": "硬件结构/测试验证",
        "next_gen_config_input": "优先补强边角覆盖、地毯深清、拖地下压力和防二次污染相关配置。",
        "next_gen_test_input": "把 CE、直线拖地、边角覆盖、水渍残留和地毯黑盒合并读成结果可信验收。",
    },
    {
        "value_axis": "免维护闭环",
        "user_certainty": "用户买的是不用抠毛、不闻臭味、不频繁清理基站的低介入闭环。",
        "config_fields": ("滚刷防缠", "边刷防缠", "拖布防缠绕", "集尘容量", "洗拖布温度", "热风烘干", "自动加液", "污水识别", "基站自清洁", "主机免维护"),
        "test_keywords": ("缠绕率", "集尘效率", "清洗效果", "洗净率", "含水量", "烘干效果", "残水", "用水量"),
        "gap_type": "硬件结构/维护闭环",
        "next_gen_config_input": "把零缠绕、拖布自洁、烘干除味和基站自清洁做成同一套免维护定义。",
        "next_gen_test_input": "新增连续免干预天数、干湿混合毛发、基站残水异味和长期集尘稳定性验收。",
    },
    {
        "value_axis": "真托管少接管",
        "user_certainty": "用户买的是不用提前收拾、不怕卡死、不需要反复救援的托管信心。",
        "config_fields": ("导航类型", "避障类型", "沿边类型", "AI污渍识别", "视频管家", "智能托管", "√yiko语音"),
        "test_keywords": ("避障", "建图", "重定位", "探索回充", "回充对接", "定位", "结构光", "Agent", "yiko"),
        "gap_type": "算法策略/传感器生态",
        "next_gen_config_input": "把避障、污渍识别、动态策略和语音 Agent 合成真正的托管能力，而不是分散功能点。",
        "next_gen_test_input": "新增动态家庭变化、拖拽后恢复、重污自动策略和模糊意图任务规划验收。",
    },
    {
        "value_axis": "复杂地形通过性",
        "user_certainty": "用户买的是门槛、地毯、低矮空间里也不掉链子的从容感。",
        "config_fields": ("越障方式", "单次越障/连续越障", "滚刷抬升", "边刷抬升", "拖布抬升", "拖布自动拆卸", "主机尺寸"),
        "test_keywords": ("直线越障", "逻辑越障", "组合门槛", "超声波识别", "地毯", "二次污染", "最小进入高度", "结构尺寸"),
        "gap_type": "硬件结构/三维运动",
        "next_gen_config_input": "围绕底盘抬升、部件抬升、拖布自动拆卸和高门槛通过性重定义复杂地形能力。",
        "next_gen_test_input": "把 15-25mm 真实门槛、长毛地毯干爽度、地毯二次污染和低矮空间回充纳入硬门槛。",
    },
    {
        "value_axis": "无感融入",
        "user_certainty": "用户买的是不突兀、不吵、不打扰，还能自然交互的家居融入感。",
        "config_fields": ("主机尺寸", "基站尺寸", "超薄", "平嵌", "清洁dB", "集尘dB", "√yiko语音", "外观造型"),
        "test_keywords": ("结构尺寸", "最小进入高度", "噪声", "异音", "yiko语音性能", "Agent性能", "句准率"),
        "gap_type": "体验边界/无感化",
        "next_gen_config_input": "继续把平嵌超薄、低噪和自然语音作为加分项，但必须服务少接管和结果可信。",
        "next_gen_test_input": "新增夜间/婴儿房/观影模式的峰值噪声、异音和免打扰语音验收。",
    },
]

SERIES_VALUE_PROPOSITION_DEFAULTS = {
    "X": {
        "series_label": "X 系",
        "series_judgment": "X 系用户真正想买到的不是更热闹的旗舰参数，而是高端场景下也成立的强能力与托管从容感。",
        "buy_not": "用户真正买的不是参数更猛，而是关键场景下也能少接管、少返工、真托管。",
        "functional_value": "高端场景下也成立的强清洁结果与完整覆盖。",
        "trust_value": "高端场景下也能少接管、少返工、真托管。",
        "core_value_proposition": "更可信的高端强能力，不靠参数热闹成立，而靠高端场景下也能少接管、少返工、真托管成立。",
        "next_gen_lines": [
            "先把高端场景下的清洁结果做成默认可信，而不是继续把旗舰优势讲成参数更强。",
            "把托管从“看起来更聪明”升级成“关键位置不掉链子、用户敢持续放手”。",
            "科技表达和轻薄形态继续保留为高端加分项，但不要盖过主价值主张。",
        ],
    },
    "T": {
        "series_label": "T 系",
        "series_judgment": "T 系用户真正想买到的不是一次拖得更猛，而是拖后结果可信、维护不烦、主销默认答案成立。",
        "buy_not": "用户真正买的不是单点拖地更强，而是拖后结果可信、维护不烦、主销场景下默认能把事做完。",
        "functional_value": "更稳的拖后结果、更少返工、更完整覆盖。",
        "trust_value": "少维护、少接管、主销场景下默认可信。",
        "core_value_proposition": "更稳的结果加更低的维护/接管负担，让主销场景下的默认答案真正成立。",
        "next_gen_lines": [
            "优先把拖后结果可信、返工更少做成主销场景下的默认答案。",
            "把维护负担和接管负担一起收住，不让“解放双手”停在半闭环。",
            "不要把主销升级误讲成炫技升级，科技表达只能服务结果可信和托管可信。",
        ],
    },
    "default": {
        "series_label": "当前系列",
        "series_judgment": "用户真正想买到的不是更多功能点，而是更稳定的结果和更低的接管负担。",
        "buy_not": "用户真正买的不是功能名词，而是更稳的结果和更少的返工、接管与维护。",
        "functional_value": "更稳的清洁结果、更少返工。",
        "trust_value": "少接管、少维护、真正解放双手。",
        "core_value_proposition": "把结果做稳，把接管和维护负担做低，让解放双手真正闭环。",
        "next_gen_lines": [
            "优先修复最伤结果可信的那组问题。",
            "优先收住最伤托管可信的接管和维护破口。",
            "把加分项和主价值主张分开，不提前透支弱信号。",
        ],
    },
}

NON_CLEANING_ROBOT_THEME_KEYWORDS = (
    "割草",
    "mowing",
    "goat",
    "擦窗",
    "窗户",
    "小窗户",
    "落地窗",
    "防盗窗",
    "安全绳",
)

THEME_FAMILY_RULES = {
    "清洁体验": ("污渍", "边角", "灰尘", "颗粒", "拖地", "清洁"),
    "无人值守稳定性": ("故障", "可靠", "避障", "卡困", "脱困", "续航", "回充"),
    "维护负担": ("维护", "基站", "滚刷", "异味", "尘盒", "清洁槽"),
    "智能交互": ("智能", "交互", "地图", "app", "语音", "导航"),
    "外观与融入": ("外观", "做工", "尺寸", "家具", "家居", "颜色"),
    "家庭场景": ("家庭", "养宠", "有娃", "共享", "宠物"),
    "噪音体验": ("噪音", "安静", "扰民"),
}

PROBLEM_EFFECT_EXPECTATION_RULES = {
    "污渍问题": {
        "一次拖净不留痕": ("不留痕", "拖净", "一遍", "干净", "发亮"),
        "顽固污渍重点处理": ("顽固污渍", "重点", "重污", "油污", "厨房"),
        "餐后/突发液体及时处理": ("餐后", "液体", "撒了", "应急", "突发"),
        "别把污渍抹匀": ("抹匀", "水印", "水渍", "越拖越脏"),
    },
    "边角问题": {
        "边角覆盖更完整": ("边角", "覆盖", "墙角", "踢脚线"),
        "桌椅腿/门后别漏": ("桌椅腿", "门后", "窄缝", "死角"),
    },
    "避障/卡困": {
        "少救援少卡困": ("卡困", "救", "解救", "卡住"),
        "门槛台阶稳定通过": ("门槛", "台阶", "越障", "通过"),
    },
    "维护/基站": {
        "少拆洗少异味": ("少维护", "异味", "拆洗", "发臭"),
        "基站自清洁/自动排污": ("自清洁", "排污", "自动", "基站"),
    },
    "噪音": {
        "夜间/共处不打扰": ("安静", "夜间", "不打扰", "邻居"),
    },
    "智能交互/地图": {
        "地图稳定少犯傻": ("地图", "稳定", "少犯傻", "路径"),
        "交互省心可控": ("app", "语音", "可控", "交互"),
    },
    "故障与可靠性": {
        "稳定运行少报警": ("稳定", "少报警", "不报错", "不出故障", "不断线"),
        "更新后别出问题": ("更新", "固件", "别异常", "别崩", "升级后"),
        "运行过程别异响掉件": ("异响", "掉落", "掉件", "拖布掉", "离线"),
    },
    "外观设计与做工": {
        "尺寸更好融入家居": ("尺寸", "嵌入", "薄", "不占地方", "适合柜体"),
        "质感和做工更高级": ("质感", "做工", "高级", "精致", "工艺"),
        "颜色材料更耐脏耐看": ("颜色", "耐脏", "材质", "好看", "家居"),
    },
    "续航与充电": {
        "一次覆盖全屋少中断": ("续航", "全屋", "一次扫完", "中断", "断电"),
        "回充和补能更快": ("回充", "充电快", "补能", "充电慢", "恢复"),
        "重污模式也别明显掉速": ("重污", "强档", "深度清洁", "模式"),
    },
    "家具与桌椅": {
        "桌椅腿周边绕得开也扫得到": ("桌椅腿", "门后", "绕开", "扫到", "边角"),
        "别撞坏家具和地面": ("撞", "损坏", "刮花", "家具", "地板损坏"),
        "家具识别更准": ("识别", "家具", "桌椅", "误判", "边界"),
    },
    "家庭与养宠属性": {
        "宠物家庭高压场景更稳": ("宠物", "猫", "狗", "应急", "毛发"),
        "家庭共享和多成员更顺手": ("家庭", "共享", "多人", "切换", "一起用"),
        "有娃家庭更放心": ("孩子", "宝宝", "玩具", "安全", "家庭"),
    },
    "灰尘与颗粒工况": {
        "颗粒别打飞": ("颗粒", "打飞", "米粒", "猫砂", "碎屑"),
        "浮灰和毛絮要吸净": ("浮灰", "毛絮", "灰尘", "吸净"),
        "宠物颗粒物和重灰更稳处理": ("宠物颗粒物", "重灰", "砂粒", "尘土"),
    },
}

TOPIC_DRILLDOWN_AXIS_PRIORITY = {
    "污渍问题": ["场景", "类型", "工况", "效果期待"],
    "边角问题": ["类型", "场景", "效果期待", "工况"],
    "避障/卡困": ["类型", "场景", "工况", "效果期待"],
    "维护/基站": ["类型", "工况", "效果期待", "场景"],
    "噪音": ["场景", "类型", "效果期待", "工况"],
    "智能交互/地图": ["类型", "效果期待", "场景", "工况"],
    "故障与可靠性": ["类型", "场景", "效果期待", "工况"],
    "外观设计与做工": ["类型", "效果期待", "场景", "工况"],
    "续航与充电": ["类型", "效果期待", "场景", "工况"],
    "家具与桌椅": ["场景", "类型", "效果期待", "工况"],
    "家庭与养宠属性": ["效果期待", "场景", "类型", "工况"],
    "灰尘与颗粒工况": ["工况", "场景", "效果期待", "类型"],
}

N_USER_BAND_RULES = {
    "N_single": ("N20 PRO", "N20", "N20E", "摩根单机"),
    "N_aes": ("N20 PRO PLUS", "N20 PLUS", "N20E PLUS", "摩根AES"),
    "N_omni": ("T50 OMNI", "T50 PRO OMNI", "T50S PRO OMNI", "T50S OMNI", "T30", "N50", "帕斯卡"),
}
N_USER_BAND_PRIORITY = ("N_aes", "N_omni", "N_single")
N_USER_BAND_MARKET_PRIORITY = {
    "N_single": ["中国", "ALL", "海外"],
    "N_aes": ["海外", "ALL", "中国"],
    "N_omni": ["中国", "ALL", "海外"],
}
USER_CHAIN_REFRESH_RUNTIME_INPUTS = (
    "analysis_reflection_report",
    "awe_exhibition_signals",
    "brand_mindshare_judgments",
    "case_concept_slots",
    "competition_capability_scan",
    "competition_capture_target_candidates",
    "competition_generation_analysis",
    "competition_matchup_matrix",
    "competition_strategy_bridge",
    "competition_thesis_tree",
    "competition_voc_market_split",
    "competition_voc_xtn_breakdown",
    "cross_source_convergence_tree",
    "cross_source_interpretation",
    "demand_pool_snapshot",
    "entry_exposure_tree",
    "generation_comparison",
    "idea_cluster_judgments",
    "page_metric_cards",
    "portfolio_generation_strategy",
    "self_strategy_thesis",
    "self_strategy_thesis_tree",
    "semantic_passages",
    "summary_insight_cards",
    "cleaning_robot_theme_registry",
    "topic_attention_matrix",
    "problem_drilldown_packages",
    "qual_evidence_packet",
    "qual_reasoning_task_board",
    "qual_case_reasoning_cards",
    "qual_theme_reasoning_map",
    "cross_source_hypothesis_board",
    "survey_qual_explanation_map",
    "judgment_acceptance_log",
    "series_positioning",
    "strategy_translation",
    "survey_concept_segments",
    "survey_segment_comparison",
    "t_difference_matrix",
    "t_dimension_confidence_stats",
    "t_dimension_impact_stats",
    "t_jtbd_confidence_stats",
    "t_jtbd_impact_stats",
    "t_jtbd_packages",
    "t_persona_slice_cards",
    "voc_fact_exposure_tree",
    "voc_problem_packages",
    "x_jtbd_confidence_stats",
    "x_jtbd_impact_stats",
    "x_observed_positionings",
    "x_positioning_confidence_stats",
    "x_positioning_impact_stats",
    "x_positioning_packages",
    "user_insight_exposure_tree",
    "user_strategy_convergence_tree",
    "user_thesis_tree",
    "master_judgment_tree",
    "presentation_tree",
    "presentation_page_blocks",
    "user_presentation_blocks",
)
USER_CHAIN_REFRESH_OUTPUT_KEYS = (
    "cleaning_robot_theme_registry",
    "topic_attention_matrix",
    "problem_drilldown_packages",
    "qual_evidence_packet",
    "qual_reasoning_task_board",
    "qual_case_reasoning_cards",
    "qual_theme_reasoning_map",
    "cross_source_hypothesis_board",
    "survey_qual_explanation_map",
    "judgment_acceptance_log",
    "cross_source_interpretation",
    "series_positioning",
    "strategy_translation",
    "user_insight_exposure_tree",
    "user_strategy_convergence_tree",
    "user_thesis_tree",
    "cross_source_convergence_tree",
    "self_strategy_thesis_tree",
    "master_judgment_tree",
    "presentation_tree",
    "presentation_page_blocks",
    "user_presentation_blocks",
)
USER_CHAIN_REFRESH_SCOPE_ALIAS = {
    "user_chain": "user_exposure",
}
USER_CHAIN_REFRESH_STAGE_ORDER = {
    "user_exposure": 0,
    "user_reasoning": 1,
    "user_closure": 2,
}
USER_CHAIN_REFRESH_STEP_ORDER = [
    "build_cleaning_robot_theme_registry",
    "build_topic_attention_matrix",
    "build_problem_drilldown_packages",
    "build_qual_evidence_packet",
    "run_dual_engine_reasoning",
    "evaluate_candidate_claims",
    "build_cross_source_interpretation",
    "build_series_positioning",
    "build_strategy_translation",
    "build_survey_qual_explanation_map",
    "build_user_insight_exposure_tree",
    "build_user_strategy_convergence_tree",
    "build_user_thesis_tree",
    "build_cross_source_convergence_tree",
    "build_self_strategy_thesis_tree",
    "build_master_judgment_tree",
    "build_presentation_tree",
    "build_presentation_page_blocks",
    "build_user_presentation_blocks",
    "run_user_presentation_composer",
]
USER_CHAIN_REFRESH_STEP_DOWNSTREAM_GRAPH = {
    "build_cleaning_robot_theme_registry": ["build_topic_attention_matrix"],
    "build_topic_attention_matrix": ["build_problem_drilldown_packages", "build_survey_qual_explanation_map", "build_user_thesis_tree", "build_presentation_page_blocks"],
    "build_problem_drilldown_packages": ["build_qual_evidence_packet", "build_survey_qual_explanation_map", "build_user_insight_exposure_tree", "build_user_thesis_tree", "build_presentation_page_blocks"],
    "build_qual_evidence_packet": ["run_dual_engine_reasoning"],
    "run_dual_engine_reasoning": ["evaluate_candidate_claims"],
    "evaluate_candidate_claims": ["build_cross_source_interpretation", "build_survey_qual_explanation_map", "build_user_thesis_tree"],
    "build_cross_source_interpretation": ["build_series_positioning", "build_strategy_translation", "build_cross_source_convergence_tree", "build_presentation_page_blocks"],
    "build_series_positioning": ["build_user_strategy_convergence_tree", "build_cross_source_convergence_tree"],
    "build_strategy_translation": ["build_cross_source_convergence_tree", "build_presentation_page_blocks"],
    "build_survey_qual_explanation_map": ["build_user_insight_exposure_tree", "build_presentation_page_blocks"],
    "build_user_insight_exposure_tree": ["build_user_strategy_convergence_tree", "build_presentation_tree", "build_presentation_page_blocks"],
    "build_user_strategy_convergence_tree": ["build_user_thesis_tree", "build_master_judgment_tree", "build_presentation_tree", "build_presentation_page_blocks"],
    "build_user_thesis_tree": ["build_master_judgment_tree", "build_presentation_page_blocks"],
    "build_cross_source_convergence_tree": ["build_self_strategy_thesis_tree", "build_presentation_page_blocks"],
    "build_self_strategy_thesis_tree": ["build_master_judgment_tree", "build_presentation_tree", "build_presentation_page_blocks"],
    "build_master_judgment_tree": ["build_presentation_page_blocks"],
    "build_presentation_tree": ["build_presentation_page_blocks"],
    "build_presentation_page_blocks": ["build_user_presentation_blocks", "run_user_presentation_composer"],
    "build_user_presentation_blocks": ["run_user_presentation_composer"],
    "run_user_presentation_composer": [],
}
USER_CHAIN_REFRESH_SCOPE_BASE_STEP = {
    "user_exposure": "build_cleaning_robot_theme_registry",
    "user_reasoning": "build_qual_evidence_packet",
    "user_closure": "build_user_strategy_convergence_tree",
}
USER_CHAIN_REFRESH_ARTIFACT_STEP_MAP = {
    "cleaning_robot_theme_registry": "build_cleaning_robot_theme_registry",
    "topic_attention_matrix": "build_topic_attention_matrix",
    "problem_drilldown_packages": "build_problem_drilldown_packages",
    "qual_evidence_packet": "build_qual_evidence_packet",
    "qual_reasoning_task_board": "run_dual_engine_reasoning",
    "qual_case_reasoning_cards": "run_dual_engine_reasoning",
    "qual_theme_reasoning_map": "run_dual_engine_reasoning",
    "cross_source_hypothesis_board": "run_dual_engine_reasoning",
    "judgment_acceptance_log": "run_dual_engine_reasoning",
    "cross_source_interpretation": "build_cross_source_interpretation",
    "series_positioning": "build_series_positioning",
    "strategy_translation": "build_strategy_translation",
    "survey_qual_explanation_map": "build_survey_qual_explanation_map",
    "user_insight_exposure_tree": "build_user_insight_exposure_tree",
    "user_strategy_convergence_tree": "build_user_strategy_convergence_tree",
    "user_thesis_tree": "build_user_thesis_tree",
    "cross_source_convergence_tree": "build_cross_source_convergence_tree",
    "self_strategy_thesis_tree": "build_self_strategy_thesis_tree",
    "master_judgment_tree": "build_master_judgment_tree",
    "presentation_tree": "build_presentation_tree",
    "presentation_page_blocks": "build_presentation_page_blocks",
    "user_presentation_blocks": "build_user_presentation_blocks",
    "presentation_main_report": "run_user_presentation_composer",
    "mirror_review_loop_report": "run_user_presentation_composer",
    "mirror_open_risks": "run_user_presentation_composer",
}
USER_CHAIN_REFRESH_BUILDER_ALIAS = {
    "build_qual_reasoning_task_board": "run_dual_engine_reasoning",
    "evaluate_candidate_claims": "run_dual_engine_reasoning",
}

MIRROR_REGISTRY_PATH = configured_asset_path("HERMES_MIRROR_REGISTRY", "character_mirror/人物镜像/registry.json")
MIRROR_VAULT_ROOT = configured_asset_path("HERMES_MIRROR_VAULT_ROOT", "character_mirror")
MIRROR_SCORE_THRESHOLDS = {"David": 85, "钱董": 85}
MIRROR_MAX_ITERATIONS = 5
MIRROR_REVIEW_SIGNAL_MAP = {
    "David": {
        "must_include": {
            "阶段数据或同比数据": ("数据", "提及率", "占比", "例", "rate", "count"),
            "目标和改善值": ("判断", "改善", "提升", "下降", "核心结论"),
            "当前节点的价值与决策用途": ("当前节点", "决策", "为什么重要", "这意味着"),
            "action plan": ("下一步", "动作", "优先级", "建议"),
            "追踪结果和gap": ("gap", "差距", "缺口", "风险"),
            "前置原因分析": ("为什么", "根因", "不是", "边界"),
            "资源配置逻辑": ("带宽", "分工", "承接", "优先级"),
            "主营业务与战略优先级": ("X", "T", "系列", "主命题"),
            "如是方法论需附带预演或验证": ("验证", "提及率", "占比", "通过", "回归"),
        },
        "must_avoid": {
            "只谈概念不谈数据": ("概念",),
            "只报黄灯红灯不讲前因": ("黄灯", "红灯"),
            "只做盘点或总结但回答不了so what": ("盘点",),
            "看不懂的比例图和抽象图表": ("38%", "62%"),
            "把资源不足当作托词": ("资源不足", "没资源"),
            "只讲 demo 不讲输入、框架和边界": ("demo",),
        },
    },
    "钱董": {
        "must_include": {
            "关键时间节点和能否关门": ("当前节点", "阶段", "下一步", "收口", "关门"),
            "当前方案与正确路径的差距": ("差距", "缺口", "风险", "gap"),
            "阶段推进路径": ("阶段", "路径", "先", "再", "最后"),
            "统一入口/窗口/任务分发机制": ("机制", "入口", "闭环", "承接"),
            "试点、分享、水平展开和下一步动作": ("下一步", "动作", "优先级", "试点", "展开"),
        },
        "must_avoid": {
            "大量人工拆解却没有机制闭环": ("人工拆解",),
            "默认接受延期": ("延期", "顺延", "下月再说"),
            "只讲推进状态不讲组织和机制": ("推进状态",),
            "为了效率取消独立评价": ("取消独立评价",),
        },
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a standardized robot-product insight bundle.")
    parser.add_argument("--bundle-mode", choices=("standard", "portfolio_full"), default="standard", help="Bundle generation mode")
    parser.add_argument("--refresh-scope", choices=("full", "user_chain", "user_exposure", "user_reasoning", "user_closure"), default="full", help="Refresh scope for portfolio runtime")
    parser.add_argument("--analysis-engine", choices=("rule_only", "dual_engine_llm"), default="rule_only", help="Analysis engine mode")
    parser.add_argument("--llm-profile-path", default=None, help="Optional JSON profile path for dual-engine LLM reasoning")
    parser.add_argument("--qual-reasoning-profile", default="qual_default", help="Profile key for qualitative reasoning")
    parser.add_argument("--thesis-reasoning-profile", default="thesis_default", help="Profile key for thesis reasoning")
    parser.add_argument("--target-builder", action="append", default=[], help="Optional targeted builder id for partial user refresh, repeatable")
    parser.add_argument("--target-artifact", action="append", default=[], help="Optional targeted artifact id for partial user refresh, repeatable")
    parser.add_argument("--category-name", default="机器人产品", help="Category label")
    parser.add_argument("--analysis-goal", action="append", default=[], help="Analysis goal or user question, repeatable")
    parser.add_argument("--spu", action="append", default=[], help="SPU id or SPU name, repeatable")
    parser.add_argument("--cohort-id", action="append", default=[], help="Cohort id, repeatable")
    parser.add_argument("--market", default=None, help="Market scope such as cn / eu / kr / global")
    parser.add_argument("--survey-topic", action="append", default=[], help="Survey topic filter, repeatable")
    parser.add_argument("--require-voc", action="store_true", help="Keep only SPUs with VOC coverage")
    parser.add_argument("--time-scope", default="待补充", help="Time scope for main report")
    parser.add_argument("--period-id", action="append", default=[], help="Explicit period ids, repeatable")
    parser.add_argument("--analysis-title", default=None, help="Main report title override")
    parser.add_argument("--pairwise-competitor-spu", default=None, help="Force pairwise competitor SPU")
    parser.add_argument("--bundle-id", default=None, help="Optional bundle id")
    parser.add_argument("--out-dir", default=None, help="Optional output directory")
    return parser.parse_args()


def resolve_read_db_path(db_path: str | Path) -> Path:
    path = Path(db_path)
    if path != Path(VOC_DB):
        return path
    archive_dir = path.parent.parent / "archive"
    archives = sorted(archive_dir.glob("cleaning_robot_voc_feedback_log.*.db"), reverse=True)
    return archives[0] if archives else path


def connect(db_path: str | Path) -> sqlite3.Connection:
    resolved = resolve_read_db_path(db_path)
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    if resolved == Path(VOC_DB):
        ensure_voc_compat_views(conn)
    elif resolved != Path(db_path):
        ensure_voc_compat_views(conn)
    return conn


def connect_live_voc_preferred() -> sqlite3.Connection:
    live_path = Path(VOC_DB)
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{live_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        ensure_voc_compat_views(conn)
        conn.execute("SELECT 1")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn
    except sqlite3.Error:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
        return connect(VOC_DB)


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_proxy_survey_rows_or_empty(selected_spu_ids: list[str], market: str | None) -> list[dict[str, object]]:
    try:
        return fetch_proxy_survey_rows(selected_spu_ids, market)
    except (OSError, sqlite3.Error):
        return []


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def normalize_text_local(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    for old in [" ", "\u3000", "-", "_", "/", "（", "）", "(", ")", "【", "】", ":", "：", ".", ",", "?", "？", "、", ";", "；"]:
        text = text.replace(old, "")
    return text


def sanitize_presentation_text(text: str, banned_phrases: list[str]) -> str:
    sanitized = text
    replacements = {
        "产品级": "产品",
        "标签主题级": "问题主题",
        "假设级": "方向判断",
        "supported": "能直接回答",
        "partial": "只能部分回答",
        "unsupported": "现在还不能定",
    }
    for source_text, target_text in replacements.items():
        sanitized = sanitized.replace(source_text, target_text)
    for phrase in banned_phrases:
        sanitized = sanitized.replace(phrase, "")
    return " ".join(sanitized.split()).strip()


def user_cohort_scope(brand_name: str | None, self_competitor_type: str | None) -> str:
    brand = str(brand_name or "").strip()
    if str(self_competitor_type or "").strip() == "self" or "科沃斯" in brand or "ECOVACS" in brand.upper():
        return "科沃斯样本"
    return f"{brand}样本" if brand else "竞品样本"


def classify_user_attention_topic(
    tag_name: str | None,
    topic_group_name_cn: str | None,
    topic_domain_name_cn: str | None,
    context_bucket_name_cn: str | None = None,
) -> str:
    tag = str(tag_name or "")
    group = str(topic_group_name_cn or "")
    domain = str(topic_domain_name_cn or "")
    bucket = str(context_bucket_name_cn or "")
    blob = normalize_text_local(" ".join([tag, group, domain, bucket]))
    for rule in USER_ATTENTION_TOPIC_RULES:
        if group in rule["topic_groups"]:
            return str(rule["topic_name"])
        if any(normalize_text_local(keyword) in blob for keyword in rule["keywords"]):
            return str(rule["topic_name"])
    if group.strip():
        return group.strip()
    if domain.strip() and domain.strip() != "未归类":
        return domain.strip()
    return ""


def is_cleaning_robot_relevant_theme(*values: object) -> bool:
    blob = normalize_text_local(" ".join(str(value or "") for value in values))
    return not any(keyword in blob for keyword in NON_CLEANING_ROBOT_THEME_KEYWORDS)


def infer_theme_family(topic_name: str) -> str:
    normalized = normalize_text_local(topic_name)
    for family, keywords in THEME_FAMILY_RULES.items():
        if any(normalize_text_local(keyword) in normalized for keyword in keywords):
            return family
    return "其他体验"


def attention_sentiment_signal(positive_count: int, negative_count: int) -> str:
    if positive_count == 0 and negative_count == 0:
        return "待观察"
    if positive_count >= int(negative_count * 1.2) and positive_count > 0:
        return "正向占优"
    if negative_count >= int(positive_count * 1.2) and negative_count > 0:
        return "负向占优"
    if positive_count > 0 and negative_count > 0:
        return "正负分化"
    return "轻度倾斜"


def summarize_breakdown_rows(rows: list[dict[str, object]], *, limit: int = 3) -> str:
    if not rows:
        return "待补充"
    return "；".join(
        f"{row.get('label', '-')}{int(row.get('message_count', 0))}例/{float(row.get('message_rate', 0.0)):.1%}"
        for row in rows[:limit]
    )


def build_cleaning_robot_theme_registry(
    source_rows: list[dict[str, object]],
) -> dict[str, object]:
    grouped: dict[str, dict[str, object]] = {}
    for row in source_rows:
        topic_name = classify_user_attention_topic(
            str(row.get("tag_name", "")),
            str(row.get("topic_group_name_cn", "")),
            str(row.get("topic_domain_name_cn", "")),
            str(row.get("context_bucket_name_cn", "")),
        )
        if not topic_name:
            continue
        topic_group = str(row.get("topic_group_name_cn", "")).strip()
        topic_domain = str(row.get("topic_domain_name_cn", "")).strip()
        entry = grouped.setdefault(
            topic_name,
            {
                "topic_name": topic_name,
                "source_topic_domain_name_cn": Counter(),
                "source_topic_group_name_cn": Counter(),
                "is_cleaning_robot_relevant": is_cleaning_robot_relevant_theme(topic_name, topic_group, topic_domain),
                "theme_family": infer_theme_family(topic_name),
                "template_mode": "specialized" if topic_name in PROBLEM_EFFECT_EXPECTATION_RULES else "generic",
                "default_drilldown_priority": TOPIC_DRILLDOWN_AXIS_PRIORITY.get(topic_name, ["类型", "场景", "工况", "效果期待"]),
                "default_expectation_template": topic_name if topic_name in PROBLEM_EFFECT_EXPECTATION_RULES else "generic_expectation_template",
                "is_frontstage_visible": True,
            },
        )
        if topic_domain:
            entry["source_topic_domain_name_cn"][topic_domain] += 1
        if topic_group:
            entry["source_topic_group_name_cn"][topic_group] += 1

    rows = []
    for entry in grouped.values():
        rows.append(
            {
                "topic_name": entry["topic_name"],
                "source_topic_domain_name_cn": entry["source_topic_domain_name_cn"].most_common(1)[0][0] if entry["source_topic_domain_name_cn"] else "",
                "source_topic_group_name_cn": entry["source_topic_group_name_cn"].most_common(1)[0][0] if entry["source_topic_group_name_cn"] else "",
                "is_cleaning_robot_relevant": bool(entry["is_cleaning_robot_relevant"]),
                "theme_family": entry["theme_family"],
                "template_mode": entry["template_mode"],
                "default_drilldown_priority": list(entry["default_drilldown_priority"]),
                "default_expectation_template": entry["default_expectation_template"],
                "is_frontstage_visible": bool(entry["is_frontstage_visible"]),
            }
        )
    rows.sort(key=lambda row: (not row["is_cleaning_robot_relevant"], row["theme_family"], row["topic_name"]))
    return {"row_count": len(rows), "rows": rows}


def collect_user_attention_spu_ids(
    selected_spu_ids: list[str],
    competition_voc_xtn_breakdown: dict[str, object],
) -> list[str]:
    expanded = list(selected_spu_ids)
    for row in competition_voc_xtn_breakdown.get("product_rows", []) or []:
        if str(row.get("series_family", "")) != "N" or not bool(row.get("is_self_brand", False)):
            continue
        for spu_id in row.get("canonical_spu_ids", []) or []:
            if str(spu_id).strip():
                expanded.append(str(spu_id))
    return dedupe_preserve_order(expanded)


def infer_user_band(series_family: str, raw_model: str | None, product_title: str | None) -> str:
    if series_family in {"X", "T"}:
        return series_family
    if series_family != "N":
        return series_family or "unknown"

    def match_band(text: str | None) -> str | None:
        normalized_text = normalize_text_local(text)
        if not normalized_text:
            return None
        for band in N_USER_BAND_PRIORITY:
            aliases = sorted(
                N_USER_BAND_RULES.get(band, ()),
                key=lambda alias: len(normalize_text_local(alias)),
                reverse=True,
            )
            for alias in aliases:
                normalized_alias = normalize_text_local(alias)
                if normalized_alias and normalized_alias in normalized_text:
                    return band
        return None

    for candidate_text in (raw_model, product_title):
        matched_band = match_band(candidate_text)
        if matched_band:
            return matched_band
    return "N_unknown"


def slugify(text: str) -> str:
    normalized = text.strip().lower()
    for old in [" ", "\u3000", "-", "/", "（", "）", "(", ")", "【", "】", ":", "：", ".", ","]:
        normalized = normalized.replace(old, "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_") or "bundle"


def choose_bundle_id(args: argparse.Namespace, result: dict[str, object]) -> str:
    if args.bundle_mode == "portfolio_full":
        return slugify(args.bundle_id or "cleaning_robot_full_portfolio")
    if args.bundle_id:
        return slugify(args.bundle_id)
    selected_spus = result["selected_spus"]  # type: ignore[index]
    self_spus = [row for row in selected_spus if row.get("self_competitor_type") == "self"]
    if self_spus:
        return slugify(self_spus[0]["spu_id"])
    if args.survey_topic:
        return slugify(args.survey_topic[0])
    return "analysis_bundle"


def ensure_out_dir(args: argparse.Namespace, bundle_id: str) -> Path:
    if args.out_dir:
        path = Path(args.out_dir).expanduser().resolve()
    else:
        path = SKILL_ROOT / "runtime" / bundle_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def collect_series_result(
    *,
    category_name: str,
    cohort_ids: list[str],
    market: str | None,
    survey_topics: list[str],
    require_voc: bool,
    preserve_non_voc_selected: bool = False,
) -> dict[str, object]:
    preflight_args = SimpleNamespace(
        category_name=category_name,
        spu=[],
        cohort_id=cohort_ids,
        market=market,
        survey_topic=survey_topics,
        module=[],
        require_voc=require_voc,
        preserve_non_voc_selected=preserve_non_voc_selected,
        format="json",
    )
    return collect_preflight_result(preflight_args)


def decision_readiness_label(result: dict[str, object]) -> str:
    support_matrix = result["support_matrix"]  # type: ignore[index]
    summary_support = {row["module_code"]: row["support_level"] for row in support_matrix}
    has_direct_survey = bool(result["survey_rows"])  # type: ignore[index]
    has_direct_summary = bool(result["summary_rows"])  # type: ignore[index]
    if has_direct_survey and has_direct_summary:
        return "较高，可支持专题级判断"
    if has_direct_survey or has_direct_summary:
        return "中等，适合方向判断"
    if summary_support.get("voc_analysis") == "支持":
        return "偏低，主要依赖 VOC"
    return "较低，需补数"


def extract_series_scope(result: dict[str, object]) -> dict[str, object]:
    selected_spus = result["selected_spus"]  # type: ignore[index]
    self_spus = [row["spu_name"] for row in selected_spus if row.get("self_competitor_type") == "self"]
    competitor_spus = [row["spu_name"] for row in selected_spus if row.get("self_competitor_type") == "competitor"]
    return {
        "self_spus": self_spus,
        "competitor_spus": competitor_spus,
        "object_names": [row["spu_name"] for row in selected_spus],
    }


def render_series_report(result: dict[str, object], *, analysis_title: str, time_scope: str, market: str | None, analysis_goal: list[str]) -> str:
    report_args = SimpleNamespace(
        analysis_title=analysis_title,
        analysis_goal=analysis_goal,
        time_scope=time_scope,
        market=market,
        pairwise_competitor_spu=None,
    )
    return build_series_product_judgment_report(
        analysis_title=analysis_title,
        analysis_goal=analysis_goal,
        time_scope=time_scope,
        market=market,
        result=result,
        args=report_args,  # type: ignore[arg-type]
    )


def portfolio_series_overview_rows(series_payloads: list[dict[str, object]]) -> list[list[object]]:
    rows: list[list[object]] = []
    for payload in series_payloads:
        result = payload["result"]  # type: ignore[index]
        scope = extract_series_scope(result)
        rows.append(
            [
                payload["series_label"],
                "、".join(scope["self_spus"]) or "-",
                len(scope["competitor_spus"]),
                len(result["voc_rows"]),  # type: ignore[index]
                len(result["survey_rows"]),  # type: ignore[index]
                len(result["summary_rows"]),  # type: ignore[index]
                decision_readiness_label(result),
            ]
        )
    return rows


def portfolio_object_map_rows(series_payloads: list[dict[str, object]]) -> list[list[object]]:
    rows: list[list[object]] = []
    for payload in series_payloads:
        for row in payload["result"]["selected_spus"]:  # type: ignore[index]
            rows.append(
                [
                    payload["series_label"],
                    row["spu_name"],
                    row["spu_id"],
                    row.get("self_competitor_type") or "",
                    row.get("lifecycle_status") or "",
                ]
            )
    return rows


def portfolio_exec_summary_lines(series_payloads: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    series_risk: list[tuple[str, str, float]] = []
    for payload in series_payloads:
        result = payload["result"]  # type: ignore[index]
        self_rows = [row for row in result["voc_rows"] if row.get("canonical_spu_id") in {spu["spu_id"] for spu in result["selected_spus"] if spu.get("self_competitor_type") == "self"}]  # type: ignore[index]
        if self_rows:
            top_self = max(self_rows, key=lambda row: (row["negative_count"] / row["message_count"]) if row["message_count"] else 0)
            risk = (top_self["negative_count"] / top_self["message_count"]) if top_self["message_count"] else 0
            series_risk.append((payload["series_label"], top_self["spu_name"], risk))
        lines.append(f"`{payload['series_label']}` 当前决策可用等级：`{decision_readiness_label(result)}`。")
    if series_risk:
        series_risk.sort(key=lambda item: item[2], reverse=True)
        lines.append(f"当前最值得优先决策的系列是 `{series_risk[0][0]}`，其中 `{series_risk[0][1]}` 风险最高。")
    if len(series_risk) > 1:
        lines.append(f"`{series_risk[-1][0]}` 当前相对更稳定，但仍应结合直连研究输入判断是否可直接定案。")
    return lines[:4]


def portfolio_cross_series_priority_lines(series_payloads: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for payload in series_payloads:
        result = payload["result"]  # type: ignore[index]
        voc_rows = result["voc_rows"]  # type: ignore[index]
        if not voc_rows:
            lines.append(f"- `{payload['series_label']}`：当前 VOC 覆盖不足，优先补数据。")
            continue
        ranked = sorted(
            voc_rows,
            key=lambda row: (row["negative_count"] / row["message_count"]) if row["message_count"] else 0,
            reverse=True,
        )
        top = ranked[0]
        lines.append(
            f"- `{payload['series_label']}`：当前优先关注 `{top['spu_name']}`，负向率约 `{(top['negative_count'] / top['message_count'] * 100):.1f}%`。"
        )
    return lines


def build_portfolio_direct_source_coverage(series_payloads: list[dict[str, object]]) -> str:
    merged_spus: list[dict[str, object]] = []
    seen: set[str] = set()
    for payload in series_payloads:
        for row in payload["result"]["selected_spus"]:  # type: ignore[index]
            if row["spu_id"] in seen:
                continue
            seen.add(row["spu_id"])
            merged_spus.append(row)
    return build_direct_source_coverage({"selected_spus": merged_spus})


def build_portfolio_backfill_task_order(series_payloads: list[dict[str, object]]) -> str:
    lines = ["# 清洁机器人全量补数任务单", "", "## 1. 目标", "", "- 让 X + T 两条线都具备更清晰的直连研究覆盖。", "- 区分“当前可直接决策”与“仅能方向判断”的对象。", "", "## 2. 核心任务", "", "| 系列 | 本品对象 | 当前关键缺口 | 下一步 |", "| --- | --- | --- | --- |"]
    for payload in series_payloads:
        result = payload["result"]  # type: ignore[index]
        scope = extract_series_scope(result)
        gap = "补直连问卷与访谈总结" if not result["survey_rows"] or not result["summary_rows"] else "补原始访谈与专题深挖"
        lines.append(f"| {payload['series_label']} | {'、'.join(scope['self_spus'])} | {gap} | 先补高风险本品对象的直连研究输入 |")
    return "\n".join(lines)


def build_portfolio_backfill_task_board(series_payloads: list[dict[str, object]]) -> str:
    lines = ["# 清洁机器人全量补数任务板", "", "| ID | 系列 | 任务 | 优先级 | 状态 | 验收标准 |", "| --- | --- | --- | --- | --- | --- |"]
    for idx, payload in enumerate(series_payloads, start=1):
        result = payload["result"]  # type: ignore[index]
        scope = extract_series_scope(result)
        lines.append(f"| PORT-{idx:02d} | {payload['series_label']} | 补 {'、'.join(scope['self_spus'])} 直连研究输入 | P1 | Not Started | 系列具备直连问卷或直连总结 |")
    return "\n".join(lines)


def build_portfolio_backfill_task_tracker(series_payloads: list[dict[str, object]]) -> str:
    lines = ["# 清洁机器人全量补数跟踪版", "", "| ID | 系列 | 当前状态 | blocker | 下一检查点 |", "| --- | --- | --- | --- | --- |"]
    for idx, payload in enumerate(series_payloads, start=1):
        result = payload["result"]  # type: ignore[index]
        blockers = []
        if not result["survey_rows"]:  # type: ignore[index]
            blockers.append("无直连问卷")
        if not result["summary_rows"]:  # type: ignore[index]
            blockers.append("无直连总结")
        lines.append(f"| PORT-{idx:02d} | {payload['series_label']} | Not Started | {'；'.join(blockers) if blockers else '需继续专题深挖'} | 下周检查 |")
    return "\n".join(lines)


def build_competition_capture_target_candidates(
    competition_generation_registry: dict[str, object],
    competition_voc_xtn_breakdown: dict[str, object],
) -> dict[str, object]:
    frontline_rows = competition_voc_xtn_breakdown.get("frontline_scope_rows", []) or []

    def registry_self_products(scope: str) -> list[str]:
        rows = [
            row
            for row in competition_generation_registry.get("rows", []) or []
            if str(row.get("competition_scope")) == scope and bool(row.get("is_self_brand"))
        ]
        products: list[str] = []
        for row in rows:
            products.extend(str(item) for item in row.get("product_names", []) or [])
        return dedupe_preserve_order(products)

    def pick_row(scope: str, market_scope: str) -> dict[str, object] | None:
        return next(
            (
                row
                for row in frontline_rows
                if str(row.get("competition_scope")) == scope and str(row.get("market_scope")) == market_scope
            ),
            None,
        )

    rows: list[dict[str, object]] = []

    def append_candidate(
        *,
        candidate_id: str,
        priority: str,
        competition_scope: str,
        target_market_scope: str,
        reason: str,
        suggested_source: str,
    ) -> None:
        market_row = pick_row(competition_scope, target_market_scope)
        rows.append(
            {
                "candidate_id": candidate_id,
                "priority": priority,
                "competition_scope": competition_scope,
                "target_market_scope": target_market_scope,
                "self_product_names": registry_self_products(competition_scope),
                "current_status": str(market_row.get("status_text", "待补充")) if market_row else "待补充",
                "current_message_count": int(market_row.get("message_count", 0)) if market_row else 0,
                "reason": reason,
                "suggested_source": suggested_source,
            }
        )

    append_candidate(
        candidate_id="CAPTURE-NOMNI-CN",
        priority="P0",
        competition_scope="N_omni",
        target_market_scope="中国",
        reason="当前中国 `N_omni` 仍无稳定自家样本，只能讲外部门槛。",
        suggested_source="中国电商评论 / 专题研究 / 用户访谈",
    )
    append_candidate(
        candidate_id="CAPTURE-NAES-CN",
        priority="P0",
        competition_scope="N_aes",
        target_market_scope="中国",
        reason="当前 `N_aes` 已有海外稳定样本，但中国区仍缺自家稳定样本。",
        suggested_source="中国电商评论 / 直连研究",
    )
    append_candidate(
        candidate_id="CAPTURE-TOMNI-OVERSEAS",
        priority="P1",
        competition_scope="T_omni",
        target_market_scope="海外",
        reason="当前海外 `T_omni` 样本极薄，只能做缺样本声明。",
        suggested_source="海外电商评论 / 海外研究",
    )
    append_candidate(
        candidate_id="CAPTURE-X-RESEARCH",
        priority="P1",
        competition_scope="X_omni",
        target_market_scope="中国",
        reason="X 已能给出正式判断，但仍可继续补强直连研究解释力。",
        suggested_source="直连访谈 / 专题研究",
    )
    append_candidate(
        candidate_id="CAPTURE-T-RESEARCH",
        priority="P1",
        competition_scope="T_omni",
        target_market_scope="中国",
        reason="T 已能给出正式判断，但仍可继续补强直连研究解释力。",
        suggested_source="直连访谈 / 专题研究",
    )
    return {"row_count": len(rows), "rows": rows}


def render_competition_capture_target_candidates(
    competition_capture_target_candidates: dict[str, object],
) -> str:
    lines = [
        "# 看竞争补采候选清单",
        "",
        "| ID | 优先级 | 竞争带 | 目标市场 | 当前状态 | 当前样本量 | 对象 | 为什么要补 | 建议来源 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in competition_capture_target_candidates.get("rows", []) or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id", "-")),
                    str(row.get("priority", "-")),
                    competition_scope_label(str(row.get("competition_scope", "-"))),
                    str(row.get("target_market_scope", "-")),
                    str(row.get("current_status", "-")),
                    str(row.get("current_message_count", 0)),
                    "、".join(row.get("self_product_names", []) or []) or "-",
                    str(row.get("reason", "-")),
                    str(row.get("suggested_source", "-")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def build_competition_data_gap_diagnosis(
    competition_voc_xtn_breakdown: dict[str, object],
    competition_voc_market_split: dict[str, object],
) -> str:
    frontline_rows = competition_voc_xtn_breakdown.get("frontline_scope_rows", []) or []
    market_summary_rows = competition_voc_market_split.get("market_summary_rows", []) or []

    def pick_scope_row(scope: str, market_scope: str) -> dict[str, object] | None:
        return next(
            (
                row
                for row in frontline_rows
                if str(row.get("competition_scope")) == scope and str(row.get("market_scope")) == market_scope
            ),
            None,
        )

    n_omni_cn = pick_scope_row("N_omni", "中国")
    n_aes_cn = pick_scope_row("N_aes", "中国")
    n_aes_all = pick_scope_row("N_aes", "ALL") or pick_scope_row("N_aes", "海外")
    t_omni_overseas = pick_scope_row("T_omni", "海外")

    lines = [
        "# 看竞争数据缺口诊断",
        "",
        "## 1. 当前已经修掉的逻辑问题",
        "",
        "- `N20 Plus / N20 Pro Plus / N20E Plus` 已不再误归到 `N_single`。",
        "- `T50` 在 `T80S/T80/T50PRO` 拼盘标题中的串词已不再被当作 `N_omni` 自家样本。",
        "- `T_omni` 海外极小样本已降级为缺样本声明，不再继续输出伪硬结论。",
        "",
        "## 2. 当前确认的真缺样本",
        "",
        "### `N_omni`",
        "",
        "- 当前 live VOC 中未发现 `T50 OMNI / T50 PRO OMNI / T50S PRO OMNI / T50S OMNI / 帕斯卡` 的真实稳定命中。",
        f"- 当前中国口径状态：`{n_omni_cn.get('status_text', '待补充') if n_omni_cn else '待补充'}`。",
        "",
        "### `N_aes` 中国区",
        "",
        "- `N20 Plus / N20 Pro Plus / N20E Plus` 已能稳定命中 `N_aes`，但当前主要来自海外样本。",
        f"- 当前中国口径状态：`{n_aes_cn.get('status_text', '待补充') if n_aes_cn else '待补充'}`。",
        "",
        "### `T_omni` 海外",
        "",
        "- 当前海外样本仍然过薄，不能直接上正式并列判断。",
        f"- 当前海外口径状态：`{t_omni_overseas.get('status_text', '待补充') if t_omni_overseas else '待补充'}`。",
        "",
        "## 3. 当前仍可直接复用的稳定判断",
        "",
    ]
    if n_aes_all:
        lines.append(
            f"- `N_aes` 的 `ALL/海外` 口径已能形成稳定自家判断，当前最伤的是 `{n_aes_all.get('top_problem_level_2', '待补充')}`。"
        )
    for scope in ["X_omni", "T_omni", "N_omni", "N_aes", "N_single"]:
        row = pick_scope_row(scope, "中国") or pick_scope_row(scope, "ALL") or pick_scope_row(scope, "海外")
        if row:
            lines.append(f"- `{competition_scope_label(scope)}`：{row.get('status_text', '待补充')}")
    lines.extend(
        [
            "",
            "## 4. 对补数工程的直接含义",
            "",
            "| 优先级 | 竞争带 | 当前状态 | 下一步 |",
            "| --- | --- | --- | --- |",
            f"| P0 | `N_omni` | {n_omni_cn.get('status_text', '待补充') if n_omni_cn else '待补充'} | 优先补 `T50 / 帕斯卡` 真实评论或研究输入，不再靠拼盘标题猜命中 |",
            f"| P0 | `N_aes` 中国区 | {n_aes_cn.get('status_text', '待补充') if n_aes_cn else '待补充'} | 优先补 `N20 Plus / N20 Pro Plus / N20E Plus / 摩根AES` 中国区样本 |",
            f"| P1 | `T_omni` 海外 | {t_omni_overseas.get('status_text', '待补充') if t_omni_overseas else '待补充'} | 若要正式讲海外主销 omni，先补 `T80S / T90` 海外样本 |",
            "",
            f"- 当前市场切分稳定性：`{json.dumps(market_summary_rows, ensure_ascii=False)}`",
        ]
    )
    return "\n".join(lines)


def build_before_after_comparison(series_payloads: list[dict[str, object]]) -> str:
    lines = [
        "# 优化前后对比",
        "",
        "## 1. 结构对比",
        "",
        "| 维度 | 优化前 | 优化后 |",
        "| --- | --- | --- |",
        "| 报告组织 | 按对象平铺 | 先总览，再按 X / T 系列分章 |",
        "| 执行摘要 | 现象型总结为主 | 决策可用性、系列优先级、风险对象更明确 |",
        "| 数据说明 | 单对象报告内可读，但不适合全量视角 | 统一放到总报告末尾，便于汇报阅读 |",
        "| 优先级判断 | 以对象碎片为主 | 增加系列间优先级与当前最值得推进专题 |",
        "",
        "## 2. 当前系列级变化",
        "",
    ]
    for payload in series_payloads:
        lines.append(f"- `{payload['series_label']}`：当前已从对象平铺视角，升级为系列视角总览。")
    lines.append("")
    lines.append("## 3. 结果判断")
    lines.append("")
    lines.append("- 新版更适合直接给业务/产品看总判断，再按对象下钻。")
    lines.append("- 旧版仍适合做单系列或单对象专题附件。")
    return "\n".join(lines)


def render_portfolio_full_report(
    *,
    category_name: str,
    time_scope: str,
    market: str | None,
    series_payloads: list[dict[str, object]],
    analysis_goal_text: str,
) -> str:
    lines: list[str] = []
    current_market = market or "ALL"
    current_time_scope = time_scope if time_scope and time_scope != "待补充" else "当前已落盘样本周期"
    lines.append(f"# {category_name} X/T 全量本品与竞品产品判断总报告")
    lines.append("")
    lines.append("## 0. 执行摘要")
    lines.append("")
    lines.append("- 这份总稿的主目标不是再做一轮统计盘点，而是把 X 系和 T 系分别收成“懂做产品的人读用户”的判断。")
    lines.append(f"- 当前分析目标：`{analysis_goal_text}`。")
    lines.append(f"- 当前口径：`{current_market}` / `{current_time_scope}`。")
    for line in portfolio_exec_summary_lines(series_payloads):
        lines.append(f"- {line}")
    lines.append("")
    for index, payload in enumerate(series_payloads, start=1):
        lines.append(f"## {index}. {payload['series_label']}专场")
        lines.append("")
        lines.append(
            f"- `{payload['series_label']}` 当前这一章固定回答：用户到底在买什么结果、哪里开始失去信心、竞品为什么能抢票、下一代该补什么定义。"
        )
        lines.append("")
        series_body = demote_headings(strip_title_block(payload["series_markdown"]), 1)
        lines.append(series_body)
        lines.append("")
    dashboard_section_index = len(series_payloads) + 1
    boundary_section_index = dashboard_section_index + 1
    lines.append(f"## {dashboard_section_index}. dashboard 可复用卡片")
    lines.append("")
    lines.append("| 卡片类型 | 作用 | 默认读法 |")
    lines.append("| --- | --- | --- |")
    lines.append("| 痛点-诉求翻译卡 | 把表层抱怨翻译成用户真正想避免的代价 | 先看它到底伤结果还是伤托管，再决定优先级 |")
    lines.append("| 核心价值主张卡 | 把系列主价值压成一句话 | 先看主价值，再看哪些只是边界加分项 |")
    lines.append("| 竞品改选逻辑卡 | 解释竞品到底在抢哪条任务 | 不按参数输赢读，按用户为什么更愿意改选读 |")
    lines.append("| next-gen 定义输入卡 | 把用户判断翻成下一代定义动作 | 不从参数平移，而从价值主张倒推 |")
    lines.append("| Roadmap压力测试卡 | 把 AWE 和追觅路线图压回 5 条价值轴 | 用来修正优先级，不用来制造参数焦虑 |")
    lines.append("| 未来竞争策略输入卡 | 输出坚持/加速/补洞/观察 | 保留置信边界，避免把概念机写成上市能力 |")
    lines.append("")
    lines.append(f"## {boundary_section_index}. 证据边界与附录")
    lines.append("")
    for payload in series_payloads:
        if not payload["result"]["survey_rows"] or not payload["result"]["summary_rows"]:  # type: ignore[index]
            lines.append(f"- `{payload['series_label']}` 当前仍有部分判断依赖 VOC 主证据，跨源解释仍建议继续补强。")
    lines.append("- `x_series_report.md` / `t_series_report.md` 继续保留为分系列主稿，不再把统计附录抬成总稿骨架。")
    lines.append("- `x_series_voc_full_appendix.md` / `t_series_voc_full_appendix.md` 继续保留为证据附录，用于回挂和复盘。")
    lines.append("- dashboard 后续优先消费“卡片层”而不是直接消费长文主稿。")
    lines.append("")
    return "\n".join(lines)


def pick_primary_self(result: dict[str, object]) -> dict[str, object] | None:
    selected_spus = result["selected_spus"]  # type: ignore[index]
    for row in selected_spus:
        if row.get("self_competitor_type") == "self":
            return row
    return None


def pick_primary_competitor(args: argparse.Namespace, result: dict[str, object]) -> dict[str, object] | None:
    selected_spus = result["selected_spus"]  # type: ignore[index]
    voc_rows = {row["canonical_spu_id"]: row for row in result["voc_rows"]}  # type: ignore[index]
    if args.pairwise_competitor_spu:
        for row in selected_spus:
            if row["spu_id"] == args.pairwise_competitor_spu:
                return row
    competitors = [row for row in selected_spus if row.get("self_competitor_type") == "competitor" and row["spu_id"] in voc_rows]
    if not competitors:
        return None
    competitors.sort(key=lambda row: voc_rows[row["spu_id"]]["message_count"], reverse=True)
    return competitors[0]


def infer_result_series_code(result: dict[str, object]) -> str:
    selected_spus = result.get("selected_spus", []) or []
    for row in selected_spus:
        for candidate in (
            row.get("series_code"),
            row.get("series_family"),
            row.get("spu_id"),
            row.get("spu_name"),
        ):
            inferred = infer_series_code(str(candidate or ""))
            if inferred in {"X", "T"}:
                return inferred
    primary_self = pick_primary_self(result)
    if primary_self:
        inferred = infer_series_code(str(primary_self.get("spu_id") or primary_self.get("spu_name") or ""))
        if inferred in {"X", "T"}:
            return inferred
    return "default"


def extract_top_signal_tags(snapshot: dict[str, object], *, limit: int = 3, negative: bool = False) -> list[str]:
    key = "negatives" if negative else "themes"
    rows = snapshot.get(key, []) or []
    tags: list[str] = []
    for row in rows:
        tag_name = str(row.get("tag_name") or "").strip()
        if not tag_name:
            continue
        if tag_name not in tags:
            tags.append(tag_name)
        if len(tags) >= limit:
            break
    return tags


def value_rule_for_text(text: str) -> dict[str, str]:
    normalized = normalize_text_local(text)
    for rule in VALUE_TRANSLATION_RULES:
        if any(normalize_text_local(keyword) in normalized for keyword in rule["keywords"]):
            return {
                "pain_point": str(rule["pain_point"]),
                "need": str(rule["need"]),
                "value_axis": str(rule["value_axis"]),
                "axis_statement": str(rule["axis_statement"]),
            }
    return {
        "pain_point": "用户在关键时刻重新犹豫，说明这类体验还没有被稳稳做成默认答案。",
        "need": "把结果做稳，把用户从返工、接管和犹豫里解放出来。",
        "value_axis": "功能结果价值",
        "axis_statement": "更稳的结果、更少返工",
    }


def build_value_translation_rows(negative_tags: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    seen: set[str] = set()
    for tag in negative_tags:
        rule = value_rule_for_text(tag)
        row = [tag, rule["need"], rule["axis_statement"], rule["value_axis"]]
        row_key = " | ".join(row)
        if row_key in seen:
            continue
        seen.add(row_key)
        rows.append(row)
        if len(rows) >= 4:
            break
    if rows:
        return rows
    fallback = value_rule_for_text("清洁效果")
    return [["当前高频负面仍待补充", fallback["need"], fallback["axis_statement"], fallback["value_axis"]]]


def build_value_axis_rows(
    series_code: str,
    positive_tags: list[str],
    negative_tags: list[str],
) -> list[list[str]]:
    defaults = SERIES_VALUE_PROPOSITION_DEFAULTS.get(series_code, SERIES_VALUE_PROPOSITION_DEFAULTS["default"])
    boundary_tags = [tag for tag in positive_tags if any(normalize_text_local(keyword) in normalize_text_local(tag) for keyword in VALUE_BOUNDARY_KEYWORDS)]
    rows = [
        [
            "功能结果价值",
            str(defaults["functional_value"]),
            positive_tags[0] if positive_tags else "清洁结果与覆盖完成率",
            "这类价值决定用户会不会觉得它真的把事做完了。",
        ],
        [
            "信任/负担转移价值",
            str(defaults["trust_value"]),
            negative_tags[0] if negative_tags else "接管、维护与善后负担",
            "这类价值决定用户敢不敢持续把家务托付给它。",
        ],
        [
            "边界项",
            "；".join(boundary_tags[:2]) if boundary_tags else "科技表达、轻薄融入、多机协同等加分项",
            boundary_tags[0] if boundary_tags else "当前更适合作为加分项或远期机会",
            "这类价值可以加分，但当前不该抢主价值主张。",
        ],
    ]
    return rows


def rate_text(message_count: int, negative_count: int) -> str:
    if message_count <= 0:
        return "样本待补充"
    return f"消息量 {message_count}，负向率 {negative_count / message_count * 100:.1f}%"


def lifecycle_bucket(value: object) -> str:
    normalized = normalize_text_local(str(value or ""))
    if any(token in normalized for token in ("previous", "上一代", "前代", "lastgen", "prev")):
        return "previous"
    if any(token in normalized for token in ("current", "当前代", "本代", "latest", "现售")):
        return "current"
    return ""


def pick_self_generation_rows(result: dict[str, object]) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    self_rows = [row for row in (result.get("selected_spus", []) or []) if row.get("self_competitor_type") == "self"]
    current_row: dict[str, object] | None = None
    previous_row: dict[str, object] | None = None
    for row in self_rows:
        bucket = lifecycle_bucket(row.get("lifecycle_status"))
        if bucket == "current" and current_row is None:
            current_row = row
        elif bucket == "previous" and previous_row is None:
            previous_row = row
    if current_row is None and self_rows:
        current_row = self_rows[0]
    if previous_row is None and len(self_rows) > 1:
        for row in self_rows:
            if current_row and row.get("spu_id") == current_row.get("spu_id"):
                continue
            previous_row = row
            break
    return current_row, previous_row


def build_series_value_proposition_summary(
    *,
    series_code: str,
    positive_tags: list[str],
    negative_tags: list[str],
    competitor_name: str | None,
) -> dict[str, object]:
    defaults = SERIES_VALUE_PROPOSITION_DEFAULTS.get(series_code, SERIES_VALUE_PROPOSITION_DEFAULTS["default"])
    translation_rows = build_value_translation_rows(negative_tags)
    primary_break_rule = value_rule_for_text(negative_tags[0] if negative_tags else "")
    buy_tag = positive_tags[0] if positive_tags else "清洁结果好"
    switch_need = primary_break_rule["need"]
    summary = {
        "series_label": defaults["series_label"],
        "series_judgment": defaults["series_judgment"],
        "buy_not": defaults["buy_not"],
        "main_buy_point": f"用户会因为 `{buy_tag}` 愿意下单，但真正留下来的理由是 `{defaults['functional_value']}`。",
        "main_recognition_point": f"当用户主动提起 `{buy_tag}` 这类信号时，本质上是在认可 `{defaults['functional_value']}` 已经被感知。",
        "main_breakpoint": f"一旦出现 `{negative_tags[0] if negative_tags else '关键体验掉链子'}`，用户会把它理解成 `{primary_break_rule['pain_point']}`。",
        "main_switch_point": (
            f"当 `{competitor_name}` 更像能把 `{switch_need}` 做稳时，用户会更容易改选。"
            if competitor_name
            else f"当别家更像能把 `{switch_need}` 做稳时，用户会更容易改选。"
        ),
        "core_value_proposition": defaults["core_value_proposition"],
        "value_translation_rows": translation_rows,
        "value_axis_rows": build_value_axis_rows(series_code, positive_tags, negative_tags),
        "next_gen_lines": list(defaults["next_gen_lines"]),
    }
    return summary


def build_series_competitor_rows(
    args: argparse.Namespace,
    result: dict[str, object],
    *,
    limit: int = 3,
) -> list[list[str]]:
    primary_self = pick_primary_self(result)
    competitors = [row for row in (result.get("selected_spus", []) or []) if row.get("self_competitor_type") == "competitor"]
    voc_by_spu = {row["canonical_spu_id"]: row for row in result.get("voc_rows", []) or []}
    if not competitors or not primary_self:
        return [["当前关键竞品待补充", "暂无稳定样本", "当前改选逻辑待补充", "当前对打判断待补充"]]
    competitors = [row for row in competitors if row.get("spu_id") in voc_by_spu]
    competitors.sort(key=lambda row: int(voc_by_spu[row["spu_id"]]["message_count"]), reverse=True)
    conn = connect(VOC_DB)
    try:
        rows: list[list[str]] = []
        for row in competitors[:limit]:
            snapshot = fetch_voc_product_snapshot(conn, str(row["spu_id"]))
            top_positive = extract_top_signal_tags(snapshot, limit=2)
            top_negative = extract_top_signal_tags(snapshot, limit=2, negative=True)
            lead_positive = "、".join(top_positive[:2]) if top_positive else "清洁结果与托管信心"
            lead_negative = "、".join(top_negative[:2]) if top_negative else "当前风险待补充"
            switch_logic = value_rule_for_text(top_negative[0] if top_negative else lead_positive)["need"]
            rows.append(
                [
                    str(row.get("spu_name") or row.get("spu_id") or "关键竞品"),
                    f"更容易在 `{lead_positive}` 上先建立购买理由。",
                    f"一旦用户在 `{lead_negative}` 这类问题上重新犹豫，就更容易把这一票理解成 `{switch_logic}` 没被稳稳兑现。",
                    f"别把它理解成参数输赢，更该理解成它在 `{switch_logic}` 这条任务上更像默认能把事做完。",
                ]
            )
        return rows or [["当前关键竞品待补充", "暂无稳定样本", "当前改选逻辑待补充", "当前对打判断待补充"]]
    finally:
        conn.close()


def build_generation_section_lines(
    result: dict[str, object],
    current_row: dict[str, object] | None,
    previous_row: dict[str, object] | None,
) -> list[str]:
    if not current_row:
        return ["- 当前代对象仍待补充，暂时无法做代际判断。"]
    if not previous_row:
        return [
            f"- 当前直连范围里还没有 `{current_row.get('spu_name')}` 的上一代对比对象。",
            "- 这轮先根据当前代的主断点和竞品改选逻辑，反推下一代最需要优先补的定义短板。",
        ]
    conn = connect(VOC_DB)
    try:
        current_snapshot = fetch_voc_product_snapshot(conn, str(current_row["spu_id"]))
        previous_snapshot = fetch_voc_product_snapshot(conn, str(previous_row["spu_id"]))
    finally:
        conn.close()
    current_summary = current_snapshot.get("summary", {}) or {}
    previous_summary = previous_snapshot.get("summary", {}) or {}
    current_negative = extract_top_signal_tags(current_snapshot, limit=2, negative=True)
    previous_negative = extract_top_signal_tags(previous_snapshot, limit=2, negative=True)
    lines = [
        f"- `{current_row['spu_name']}` 当前表现：{rate_text(int(current_summary.get('message_count') or 0), int(current_summary.get('negative_count') or 0))}。",
        f"- `{previous_row['spu_name']}` 作为上一代参考：{rate_text(int(previous_summary.get('message_count') or 0), int(previous_summary.get('negative_count') or 0))}。",
    ]
    if current_negative:
        lines.append(f"- 当前代还没有完全补透的断点，主要还集中在 `{ '、'.join(current_negative[:2]) }`。")
    if previous_negative:
        lines.append(f"- 上一代最显性的断点主要是 `{ '、'.join(previous_negative[:2]) }`，这能帮助判断老问题是减轻了、转移了，还是仍在关键位置掉链子。")
    return lines


def build_series_product_judgment_report(
    *,
    analysis_title: str,
    analysis_goal: list[str],
    time_scope: str,
    market: str | None,
    result: dict[str, object],
    args: argparse.Namespace,
) -> str:
    series_code = infer_result_series_code(result)
    current_row, previous_row = pick_self_generation_rows(result)
    primary_self = current_row or pick_primary_self(result)
    primary_competitor = pick_primary_competitor(args, result)
    conn = connect(VOC_DB)
    try:
        self_snapshot = fetch_voc_product_snapshot(conn, str(primary_self["spu_id"])) if primary_self else {}
    finally:
        conn.close()
    positive_tags = extract_top_signal_tags(self_snapshot, limit=3)
    negative_tags = extract_top_signal_tags(self_snapshot, limit=4, negative=True)
    summary = build_series_value_proposition_summary(
        series_code=series_code,
        positive_tags=positive_tags,
        negative_tags=negative_tags,
        competitor_name=str(primary_competitor["spu_name"]) if primary_competitor else None,
    )
    engineering_extension = build_series_competition_engineering_extension(
        result=result,
        args=args,
        series_code=series_code,
    )
    future_intelligence_artifacts = build_future_intelligence_extension_artifacts(
        generated_from="series_main_report.md",
    )
    competitor_rows = build_series_competitor_rows(args, result)
    support_matrix = result.get("support_matrix", []) or []
    unsupported_modules = [row["module_name_cn"] for row in support_matrix if row["support_level"] != "支持"]
    current_market = market or "ALL"
    current_time_scope = time_scope if time_scope and time_scope != "待补充" else "当前已落盘样本周期"
    lines = [
        f"# {analysis_title}",
        "",
        "## 0. 系列总判断",
        "",
        f"- {summary['series_judgment']}",
        f"- 当前这轮更该被记住的，不是标签排位，而是 `{summary['core_value_proposition']}`。",
        f"- 当前范围：`{current_market}` / `{current_time_scope}`。",
        "",
        "## 1. 用户真正买的不是啥，而是啥",
        "",
        f"- {summary['buy_not']}",
        "",
        "| 判断项 | 当前收口 |",
        "| --- | --- |",
        f"| 主买点 | {summary['main_buy_point']} |",
        f"| 主认可点 | {summary['main_recognition_point']} |",
        f"| 主断点 | {summary['main_breakpoint']} |",
        f"| 主改选点 | {summary['main_switch_point']} |",
        "",
        "## 2. 当前代相对上一代，补到了什么 / 没补到什么",
        "",
    ]
    lines.extend(build_generation_section_lines(result, current_row, previous_row))
    lines.extend(
        [
            "",
            "## 3. 竞品分别在抢哪类用户心智",
            "",
            "| 竞品 | 它在用户心里成立什么 | 用户为什么会改选 | 本品该防什么 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in competitor_rows:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
    lines.extend(
        [
            "",
            "## 4. 价值主张收口",
            "",
            "### 4.1 痛点 -> 诉求 -> 价值主张",
            "",
            "| 痛点层 | 诉求层 | 价值主张层 | 归属 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in summary["value_translation_rows"]:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
    lines.extend(
        [
            "",
            "### 4.2 两类价值 + 一类边界",
            "",
            "| 价值类型 | 当前收口 | 代表信号 | 为什么重要 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in summary["value_axis_rows"]:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
    lines.extend(
        [
            "",
            f"- 一句话核心价值主张：{summary['core_value_proposition']}",
            "",
        ]
    )
    lines.extend(render_competition_engineering_extension_section(engineering_extension))
    lines.extend(
        render_future_intelligence_pressure_test_section(
            future_intelligence_artifacts["roadmap_stress_test_cards"],
            future_intelligence_artifacts["future_competition_strategy_inputs"],
        )
    )
    lines.extend(
        [
            "## 7. 对下一代定义的三条启示",
            "",
        ]
    )
    for idx, line in enumerate(summary["next_gen_lines"], start=1):
        lines.append(f"{idx}. {line}")
    lines.extend(
        [
            "",
            "## 8. 证据边界与待补项",
            "",
            f"- 当前主稿仍以“会做产品的人读用户”为最高约束，不把统计表当成主舞台。",
            f"- 当前还不能直接讲满的模块：`{'、'.join(unsupported_modules[:3]) if unsupported_modules else '当前关键模块基本可用'}`。",
            "- 科技表达、轻薄形态、多机协同等内容默认只作为加分项或远期机会，不直接拔成主价值主张。",
            "- AWE 与追觅路线图默认只作为前瞻压力测试信号，不写成确定性上市能力或确定性领先。",
            "- 如果下一轮要继续讲满，优先补能解释买、认可、失望与改选的跨源证据，而不是继续堆标签频次。",
        ]
    )
    return "\n".join(lines)


def build_competitor_switch_cards(competitor_rows: list[list[str]]) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for row in competitor_rows:
        cards.append(
            {
                "card_type": "竞品改选逻辑卡",
                "competitor": row[0],
                "core_value_in_user_mind": row[1],
                "switch_logic": row[2],
                "defense_judgment": row[3],
                "reading_rule": "按用户为什么更愿意改选读，不按参数输赢读。",
            }
        )
    return cards


def build_series_value_proposition_card(
    *,
    result: dict[str, object],
    args: argparse.Namespace,
    series_code: str | None = None,
    series_label: str | None = None,
) -> dict[str, object]:
    resolved_series_code = series_code or infer_result_series_code(result)
    defaults = SERIES_VALUE_PROPOSITION_DEFAULTS.get(resolved_series_code, SERIES_VALUE_PROPOSITION_DEFAULTS["default"])
    current_row, _previous_row = pick_self_generation_rows(result)
    primary_self = current_row or pick_primary_self(result)
    primary_competitor = pick_primary_competitor(args, result)
    conn = connect(VOC_DB)
    try:
        self_snapshot = fetch_voc_product_snapshot(conn, str(primary_self["spu_id"])) if primary_self else {}
    finally:
        conn.close()
    positive_tags = extract_top_signal_tags(self_snapshot, limit=3)
    negative_tags = extract_top_signal_tags(self_snapshot, limit=4, negative=True)
    summary = build_series_value_proposition_summary(
        series_code=resolved_series_code,
        positive_tags=positive_tags,
        negative_tags=negative_tags,
        competitor_name=str(primary_competitor["spu_name"]) if primary_competitor else None,
    )
    support_matrix = result.get("support_matrix", []) or []
    unsupported_modules = [row.get("module_name_cn", row.get("module_code", "未知模块")) for row in support_matrix if row.get("support_level") != "支持"]
    competitor_rows = build_series_competitor_rows(args, result)
    return {
        "series_code": resolved_series_code,
        "series_label": series_label or defaults["series_label"],
        "core_value_proposition": summary["core_value_proposition"],
        "main_buy_point": summary["main_buy_point"],
        "main_recognition_point": summary["main_recognition_point"],
        "main_breakpoint": summary["main_breakpoint"],
        "main_switch_point": summary["main_switch_point"],
        "pain_need_translation_cards": [
            {
                "card_type": "痛点-诉求翻译卡",
                "pain_point": row[0],
                "user_need": row[1],
                "value_proposition_layer": row[2],
                "value_axis": row[3],
            }
            for row in summary["value_translation_rows"]
        ],
        "core_value_cards": [
            {
                "card_type": "核心价值主张卡",
                "value_axis": row[0],
                "series_value_reading": row[1],
                "representative_signal": row[2],
                "pm_reading": row[3],
            }
            for row in summary["value_axis_rows"]
        ],
        "competitor_switch_cards": build_competitor_switch_cards(competitor_rows),
        "next_gen_definition_inputs": [
            {
                "card_type": "next-gen 定义输入卡",
                "priority": index,
                "definition_input": line,
            }
            for index, line in enumerate(summary["next_gen_lines"], start=1)
        ],
        "evidence_boundary": {
            "unsupported_modules": unsupported_modules[:5],
            "boundary_rule": "科技表达、轻薄形态、多机协同等内容默认只作为加分项或远期机会，不直接拔成主价值主张。",
            "weak_signal_handling": "弱样本对象保留观察席处理，不写成确定性输赢。",
        },
    }


def build_value_proposition_cards(
    *,
    series_payloads: list[dict[str, object]],
    args: argparse.Namespace,
    generated_from: str,
) -> dict[str, object]:
    series_cards = [
        build_series_value_proposition_card(
            result=payload["result"],  # type: ignore[arg-type,index]
            args=args,
            series_code=str(payload.get("series_code") or "") or None,
            series_label=str(payload.get("series_label") or "") or None,
        )
        for payload in series_payloads
    ]
    return {
        "card_count": len(series_cards),
        "series_cards": series_cards,
        "generated_from": {
            "source": generated_from,
            "chain": "JudgmentUnit -> Top15事实池 -> 痛点/爽点聚类 -> 用户诉求翻译 -> 核心价值主张 -> next-gen定义输入",
            "artifact_role": "dashboard 可复用卡片层，不替代产品判断版主稿。",
            "card_types": list(VALUE_PROPOSITION_CARD_TYPES),
        },
        "red_lines": list(VALUE_PROPOSITION_RED_LINES),
    }


_CONFIG_CAPABILITY_MATRIX_CACHE: dict[str, dict[str, object]] = {}
_TEST_METRIC_MATRIX_CACHE: dict[str, dict[str, object]] = {}


def cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def field_matches_keywords(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    normalized_text = normalize_text_local(text)
    return any(normalize_text_local(keyword) in normalized_text for keyword in keywords if keyword)


def load_product_config_capability_matrix(path: Path = COMPETITION_CONFIG_XLSX_PATH) -> dict[str, object]:
    cache_key = str(path)
    if cache_key in _CONFIG_CAPABILITY_MATRIX_CACHE:
        return _CONFIG_CAPABILITY_MATRIX_CACHE[cache_key]
    if not path.exists():
        payload = {
            "available": False,
            "source_path": str(path),
            "products": [],
            "rows": [],
            "by_product": {},
            "boundary": "产品配置表未找到，竞争工程证据层只能保留配置待补。",
        }
        _CONFIG_CAPABILITY_MATRIX_CACHE[cache_key] = payload
        return payload
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    sheet_values = list(ws.iter_rows(values_only=True))

    def sheet_cell(row_idx: int, col_idx: int) -> object:
        row_offset = row_idx - 1
        col_offset = col_idx - 1
        if row_offset >= len(sheet_values) or col_offset >= len(sheet_values[row_offset]):
            return None
        return sheet_values[row_offset][col_offset]

    product_columns: list[tuple[int, str]] = []
    for col_idx in range(3, ws.max_column + 1):
        product_name = cell_text(sheet_cell(4, col_idx))
        if product_name:
            product_columns.append((col_idx, product_name))
    rows: list[dict[str, object]] = []
    by_product: dict[str, dict[str, object]] = {}
    last_group = ""
    brand_by_col: dict[int, str] = {}
    last_brand = ""
    for col_idx, _product_name in product_columns:
        brand = cell_text(sheet_cell(2, col_idx))
        if brand:
            last_brand = brand
        brand_by_col[col_idx] = last_brand
    for row_idx in range(2, ws.max_row + 1):
        group = cell_text(sheet_cell(row_idx, 1))
        field = cell_text(sheet_cell(row_idx, 2))
        if group:
            last_group = group
        field_name = field or group
        if not field_name:
            continue
        canonical_field = f"{last_group}/{field_name}" if field and last_group else field_name
        for col_idx, product_name in product_columns:
            value = cell_text(sheet_cell(row_idx, col_idx))
            product_payload = by_product.setdefault(
                product_name,
                {
                    "product_name": product_name,
                    "brand": brand_by_col.get(col_idx, ""),
                    "normalized_name": normalize_text_local(product_name),
                    "fields": {},
                },
            )
            product_payload["fields"][canonical_field] = value  # type: ignore[index]
            rows.append(
                {
                    "product_name": product_name,
                    "brand": brand_by_col.get(col_idx, ""),
                    "field_group": last_group,
                    "field_name": field_name,
                    "canonical_field": canonical_field,
                    "value": value,
                }
            )
    payload = {
        "available": True,
        "source_path": str(path),
        "product_count": len(product_columns),
        "field_count": len({row["canonical_field"] for row in rows}),
        "products": [product_name for _col_idx, product_name in product_columns],
        "rows": rows,
        "by_product": by_product,
    }
    _CONFIG_CAPABILITY_MATRIX_CACHE[cache_key] = payload
    return payload


def load_product_test_metric_matrix(path: Path = COMPETITION_TEST_XLSX_PATH) -> dict[str, object]:
    cache_key = str(path)
    if cache_key in _TEST_METRIC_MATRIX_CACHE:
        return _TEST_METRIC_MATRIX_CACHE[cache_key]
    if not path.exists():
        payload = {
            "available": False,
            "source_path": str(path),
            "products": [],
            "rows": [],
            "by_product": {},
            "boundary": "测试数据表未找到，竞争工程证据层只能保留测试待补。",
        }
        _TEST_METRIC_MATRIX_CACHE[cache_key] = payload
        return payload
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows: list[dict[str, object]] = []
    by_product: dict[str, list[dict[str, object]]] = {}
    products: list[str] = []
    for ws in wb.worksheets:
        row_iter = ws.iter_rows(values_only=True)
        first_row = next(row_iter, ())
        second_row = next(row_iter, ())
        product_name = cell_text(first_row[4] if len(first_row) > 4 else "") or ws.title
        products.append(product_name)
        data_columns = [
            col_idx + 1
            for col_idx, value in enumerate(second_row)
            if col_idx >= 4 and "数据" in cell_text(value)
        ]
        if not data_columns and ws.max_column >= 9:
            data_columns = [9]
        for row_values in row_iter:
            case_name = cell_text(row_values[0] if len(row_values) > 0 else "")
            scene = cell_text(row_values[1] if len(row_values) > 1 else "")
            mode = cell_text(row_values[2] if len(row_values) > 2 else "")
            data_content = cell_text(row_values[3] if len(row_values) > 3 else "")
            if not any([case_name, scene, mode, data_content]):
                continue
            for col_idx in data_columns:
                value_idx = col_idx - 1
                test_value = cell_text(row_values[value_idx] if len(row_values) > value_idx else "")
                if not test_value:
                    continue
                item = {
                    "product_name": product_name,
                    "sheet_name": ws.title,
                    "test_case": case_name,
                    "scene_or_medium": scene,
                    "mode_or_level": mode,
                    "data_content": data_content,
                    "test_value": test_value,
                    "data_column": col_idx,
                }
                rows.append(item)
                by_product.setdefault(product_name, []).append(item)
    payload = {
        "available": True,
        "source_path": str(path),
        "product_count": len(products),
        "row_count": len(rows),
        "products": products,
        "rows": rows,
        "by_product": by_product,
    }
    _TEST_METRIC_MATRIX_CACHE[cache_key] = payload
    return payload


def product_candidate_names(row: dict[str, object]) -> list[str]:
    values = [
        str(row.get("spu_name") or ""),
        str(row.get("spu_id") or "").replace("ecovacs_", "").replace("_", " "),
    ]
    for value in list(values):
        values.extend(re.findall(r"[A-Za-z]+\d+[A-Za-z]*|[XT]\d+[A-Za-z]*|\d+", value))
    return [value for value in dedupe_preserve_order([item.strip() for item in values]) if value]


def match_named_payload(candidates: list[str], named_payloads: dict[str, object]) -> tuple[str, object] | None:
    normalized_candidates = [normalize_text_local(candidate) for candidate in candidates if candidate]
    for name, payload in named_payloads.items():
        normalized_name = normalize_text_local(name)
        if not normalized_name:
            continue
        if any(candidate == normalized_name or candidate in normalized_name or normalized_name in candidate for candidate in normalized_candidates):
            return name, payload
    return None


def summarize_config_evidence(product_payload: dict[str, object] | None, config_fields: tuple[str, ...], *, limit: int = 4) -> list[dict[str, str]]:
    if not product_payload:
        return []
    fields = product_payload.get("fields", {}) or {}
    evidence: list[dict[str, str]] = []
    for field_name, value in fields.items():  # type: ignore[union-attr]
        if not value:
            continue
        if field_matches_keywords(str(field_name), config_fields):
            evidence.append({"field": str(field_name), "value": str(value)})
        if len(evidence) >= limit:
            break
    return evidence


def summarize_test_evidence(test_rows: list[dict[str, object]] | None, test_keywords: tuple[str, ...], *, limit: int = 4) -> list[dict[str, str]]:
    if not test_rows:
        return []
    evidence: list[dict[str, str]] = []
    for row in test_rows:
        haystack = " ".join(
            str(row.get(key) or "")
            for key in ["test_case", "scene_or_medium", "mode_or_level", "data_content"]
        )
        if not field_matches_keywords(haystack, test_keywords):
            continue
        evidence.append(
            {
                "test_case": str(row.get("test_case") or ""),
                "scene_or_medium": str(row.get("scene_or_medium") or ""),
                "data_content": str(row.get("data_content") or ""),
                "test_value": str(row.get("test_value") or ""),
            }
        )
        if len(evidence) >= limit:
            break
    return evidence


def evidence_brief(evidence: list[dict[str, str]], *, field_key: str, value_key: str) -> str:
    if not evidence:
        return "待补"
    return "；".join(f"{row.get(field_key, '')}={row.get(value_key, '')}" for row in evidence[:2])


def evidence_status(config_evidence: list[dict[str, str]], test_evidence: list[dict[str, str]]) -> str:
    if config_evidence and test_evidence:
        return "配置与测试均可回挂"
    if config_evidence:
        return "仅配置可解释，测试待验证"
    if test_evidence:
        return "仅测试可验证，配置待对齐"
    return "证据待补"


def build_value_config_test_map() -> dict[str, object]:
    return {
        "axis_count": len(VALUE_CONFIG_TEST_AXIS_RULES),
        "value_axes": [
            {
                "value_axis": rule["value_axis"],
                "user_certainty": rule["user_certainty"],
                "config_fields": list(rule["config_fields"]),
                "test_keywords": list(rule["test_keywords"]),
                "next_gen_config_input": rule["next_gen_config_input"],
                "next_gen_test_input": rule["next_gen_test_input"],
            }
            for rule in VALUE_CONFIG_TEST_AXIS_RULES
        ],
        "reading_rule": "配置表回答能不能兑现，测试数据回答兑现稳不稳；两者都不能替代用户价值主张。",
    }


def build_series_competition_engineering_extension(
    *,
    result: dict[str, object],
    args: argparse.Namespace,
    series_code: str | None = None,
    series_label: str | None = None,
    config_matrix: dict[str, object] | None = None,
    test_matrix: dict[str, object] | None = None,
) -> dict[str, object]:
    del args
    resolved_series_code = series_code or infer_result_series_code(result)
    defaults = SERIES_VALUE_PROPOSITION_DEFAULTS.get(resolved_series_code, SERIES_VALUE_PROPOSITION_DEFAULTS["default"])
    selected_spus = result.get("selected_spus", []) or []
    current_row, _previous_row = pick_self_generation_rows(result)
    primary_self = current_row or pick_primary_self(result)
    competitors = [row for row in selected_spus if row.get("self_competitor_type") == "competitor"][:4]
    config_matrix = config_matrix or load_product_config_capability_matrix()
    test_matrix = test_matrix or load_product_test_metric_matrix()
    config_by_product = config_matrix.get("by_product", {}) if config_matrix.get("available") else {}
    test_by_product = test_matrix.get("by_product", {}) if test_matrix.get("available") else {}
    self_config_match = match_named_payload(product_candidate_names(primary_self or {}), config_by_product) if primary_self else None  # type: ignore[arg-type]
    self_test_match = match_named_payload(product_candidate_names(primary_self or {}), test_by_product) if primary_self else None  # type: ignore[arg-type]
    value_cards: list[dict[str, object]] = []
    gap_cards: list[dict[str, object]] = []
    next_gen_cards: list[dict[str, object]] = []
    for rule in VALUE_CONFIG_TEST_AXIS_RULES:
        config_fields = tuple(rule["config_fields"])  # type: ignore[arg-type]
        test_keywords = tuple(rule["test_keywords"])  # type: ignore[arg-type]
        self_config_evidence = summarize_config_evidence(self_config_match[1] if self_config_match else None, config_fields)
        self_test_evidence = summarize_test_evidence(self_test_match[1] if self_test_match else None, test_keywords)  # type: ignore[arg-type]
        competitor_evidence_cards: list[dict[str, object]] = []
        for competitor in competitors:
            competitor_config_match = match_named_payload(product_candidate_names(competitor), config_by_product)  # type: ignore[arg-type]
            competitor_test_match = match_named_payload(product_candidate_names(competitor), test_by_product)  # type: ignore[arg-type]
            competitor_config_evidence = summarize_config_evidence(competitor_config_match[1] if competitor_config_match else None, config_fields)
            competitor_test_evidence = summarize_test_evidence(competitor_test_match[1] if competitor_test_match else None, test_keywords)  # type: ignore[arg-type]
            competitor_evidence_cards.append(
                {
                    "competitor": str(competitor.get("spu_name") or competitor.get("spu_id") or "关键竞品"),
                    "matched_config_product": competitor_config_match[0] if competitor_config_match else "",
                    "matched_test_product": competitor_test_match[0] if competitor_test_match else "",
                    "config_evidence": competitor_config_evidence,
                    "test_evidence": competitor_test_evidence,
                    "evidence_status": evidence_status(competitor_config_evidence, competitor_test_evidence),
                    "switch_reading": (
                        f"如果竞品在 `{rule['value_axis']}` 上同时有配置和测试支撑，它抢的不是参数，而是用户对“{rule['user_certainty']}”的信心。"
                        if competitor_config_evidence and competitor_test_evidence
                        else "当前只能作为潜在能力或待验证信号，不能写成确定性领先。"
                    ),
                }
            )
        status = evidence_status(self_config_evidence, self_test_evidence)
        if status == "配置与测试均可回挂":
            gap_type = "待结合 VOC 判断"
            gap_reading = "本品具备工程证据闭环，下一步要看用户是否真的感知到这条价值。"
        elif status == "仅配置可解释，测试待验证":
            gap_type = "测试盲区"
            gap_reading = "配置上看得到能力，但还不能证明它在真实或近真实场景下稳定兑现。"
        elif status == "仅测试可验证，配置待对齐":
            gap_type = "配置断层"
            gap_reading = "测试里有相关结果，但配置定义没有把它沉淀成可被规划和传播的能力。"
        else:
            gap_type = "证据不足"
            gap_reading = "当前既不能用配置解释，也不能用测试证明，必须进入观察席。"
        value_cards.append(
            {
                "card_type": "价值-配置-测试映射卡",
                "value_axis": rule["value_axis"],
                "user_certainty": rule["user_certainty"],
                "self_product": str(primary_self.get("spu_name") if primary_self else "当前本品待补"),
                "matched_config_product": self_config_match[0] if self_config_match else "",
                "matched_test_product": self_test_match[0] if self_test_match else "",
                "self_config_evidence": self_config_evidence,
                "self_test_evidence": self_test_evidence,
                "self_evidence_status": status,
                "competitor_switch_evidence_cards": competitor_evidence_cards,
                "pm_reading": f"这张卡只解释 `{rule['value_axis']}` 的工程兑现能力，不覆盖 VOC 主判断。",
            }
        )
        gap_cards.append(
            {
                "card_type": "断层归因卡",
                "series_code": resolved_series_code,
                "value_axis": rule["value_axis"],
                "gap_type": gap_type if gap_type != "待结合 VOC 判断" else str(rule["gap_type"]),
                "gap_reading": gap_reading,
                "evidence_boundary": "弱样本、缺测试或只看到配置时，不写成确定性输赢。",
            }
        )
        next_gen_cards.append(
            {
                "card_type": "next-gen 配置/测试输入卡",
                "series_code": resolved_series_code,
                "value_axis": rule["value_axis"],
                "config_definition_input": rule["next_gen_config_input"],
                "test_standard_input": rule["next_gen_test_input"],
                "source_logic": "从用户价值主张倒推配置和测试门槛，不从参数表平移。",
            }
        )
    return {
        "series_code": resolved_series_code,
        "series_label": series_label or defaults["series_label"],
        "self_product": str(primary_self.get("spu_name") if primary_self else ""),
        "card_types": list(COMPETITION_ENGINEERING_CARD_TYPES),
        "value_config_test_cards": value_cards,
        "gap_attribution_cards": gap_cards,
        "next_gen_config_test_input_cards": next_gen_cards,
        "source_status": {
            "config_matrix_available": bool(config_matrix.get("available")),
            "test_matrix_available": bool(test_matrix.get("available")),
            "config_product_count": config_matrix.get("product_count", 0),
            "test_product_count": test_matrix.get("product_count", 0),
        },
    }


def build_competition_engineering_extension_artifacts(
    *,
    series_payloads: list[dict[str, object]],
    args: argparse.Namespace,
    generated_from: str,
) -> dict[str, dict[str, object]]:
    config_matrix = load_product_config_capability_matrix()
    test_matrix = load_product_test_metric_matrix()
    series_cards = [
        build_series_competition_engineering_extension(
            result=payload["result"],  # type: ignore[arg-type,index]
            args=args,
            series_code=str(payload.get("series_code") or "") or None,
            series_label=str(payload.get("series_label") or "") or None,
            config_matrix=config_matrix,
            test_matrix=test_matrix,
        )
        for payload in series_payloads
    ]
    gap_cards = [
        card
        for series_card in series_cards
        for card in series_card.get("gap_attribution_cards", [])  # type: ignore[union-attr]
    ]
    next_gen_cards = [
        card
        for series_card in series_cards
        for card in series_card.get("next_gen_config_test_input_cards", [])  # type: ignore[union-attr]
    ]
    return {
        "competition_engineering_evidence_cards": {
            "card_count": len(series_cards),
            "series_cards": series_cards,
            "generated_from": generated_from,
            "reading_rule": "这是竞争分析延伸层，只解释配置和测试如何支撑用户价值，不重写 VOC 主判断。",
        },
        "value_config_test_map": build_value_config_test_map(),
        "competitive_gap_attribution_cards": {
            "card_count": len(gap_cards),
            "cards": gap_cards,
            "boundary_rule": "配置或测试缺口进入观察席，不强行写成输赢。",
        },
        "next_gen_config_test_inputs": {
            "card_count": len(next_gen_cards),
            "cards": next_gen_cards,
            "definition_rule": "next-gen 输入必须从价值主张倒推配置和测试标准。",
        },
    }


def render_competition_engineering_extension_section(extension: dict[str, object]) -> list[str]:
    lines = [
        "## 5. 价值主张的竞争证据延伸",
        "",
        "- 这一层只回答配置和测试如何解释用户改选，不把主稿退回参数播报。",
        "- 配置表回答“能不能兑现”，测试数据回答“兑现稳不稳”。",
        "",
        "| 用户价值 | 本品配置兑现 | 本品测试验证 | 竞品抢信任方式 | PM 判断 |",
        "| --- | --- | --- | --- | --- |",
    ]
    value_cards = extension.get("value_config_test_cards", []) or []
    for card in value_cards[:5]:  # type: ignore[index]
        competitors = card.get("competitor_switch_evidence_cards", []) or []
        competitor_reading = "；".join(
            str(item.get("switch_reading", "")) for item in competitors[:1]  # type: ignore[union-attr]
        ) or "竞品证据待补"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(card.get("value_axis", "")),
                    evidence_brief(card.get("self_config_evidence", []), field_key="field", value_key="value"),  # type: ignore[arg-type]
                    evidence_brief(card.get("self_test_evidence", []), field_key="test_case", value_key="test_value"),  # type: ignore[arg-type]
                    competitor_reading,
                    str(card.get("self_evidence_status", "证据待补")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "- 下一代定义读法：优先补“用户价值主张无法稳定兑现”的配置和测试门槛，而不是补一串孤立参数。",
            "",
        ]
    )
    return lines


def render_main_report(
    args: argparse.Namespace,
    result: dict[str, object],
    higher_order_artifacts: dict[str, dict[str, object]] | None = None,
) -> str:
    del higher_order_artifacts
    return build_series_product_judgment_report(
        analysis_title=args.analysis_title or "机器人产品用户分析",
        analysis_goal=args.analysis_goal,
        time_scope=args.time_scope,
        market=args.market,
        result=result,
        args=args,
    )


def build_pairwise_text_deep_dive(base_spu_id: str, compare_spu_id: str) -> str:
    conn = connect(VOC_DB)
    db_names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
    }
    db_names.update(
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_temp_master WHERE type IN ('table', 'view')").fetchall()
    )
    name_map = {
        r["canonical_spu_id"]: r["spu_name"]
        for r in conn.execute(
            "SELECT canonical_spu_id, COALESCE(spu_name, canonical_spu_id) AS spu_name FROM vw_voc_message_brief WHERE canonical_spu_id IN (?, ?) GROUP BY canonical_spu_id, COALESCE(spu_name, canonical_spu_id)",
            (base_spu_id, compare_spu_id),
        )
    }

    def negative_rate(spu_id: str, period_id: str):
        if "vw_spu_period_sentiment_summary" in db_names:
            row = conn.execute(
                "SELECT message_count, negative_count FROM vw_spu_period_sentiment_summary WHERE canonical_spu_id=? AND period_id=?",
                (spu_id, period_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS message_count,
                    SUM(CASE WHEN sentiment = '负面' THEN 1 ELSE 0 END) AS negative_count
                FROM voc_message
                WHERE canonical_spu_id = ?
                  AND substr(posted_at, 1, 4) || 'q' ||
                      CASE
                          WHEN CAST(substr(posted_at, 6, 2) AS INTEGER) BETWEEN 1 AND 3 THEN '1'
                          WHEN CAST(substr(posted_at, 6, 2) AS INTEGER) BETWEEN 4 AND 6 THEN '2'
                          WHEN CAST(substr(posted_at, 6, 2) AS INTEGER) BETWEEN 7 AND 9 THEN '3'
                          ELSE '4'
                      END = ?
                """,
                (spu_id, period_id),
            ).fetchone()
        if not row or not row["message_count"]:
            return None
        return row["message_count"], row["negative_count"], row["negative_count"] / row["message_count"] * 100

    def theme_stats(spu_id: str, tags: list[str]):
        placeholders = ",".join("?" * len(tags))
        total_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM voc_message WHERE canonical_spu_id=?",
            (spu_id,),
        ).fetchone()
        total = total_row["cnt"] if total_row else 0
        rows = list(
            conn.execute(
                f"SELECT tag_name, COUNT(DISTINCT message_uid) AS cnt FROM vw_voc_message_tag_mapped WHERE canonical_spu_id=? AND tag_name IN ({placeholders}) GROUP BY tag_name ORDER BY cnt DESC, tag_name",
                (spu_id, *tags),
            )
        )
        theme_cnt = sum(r["cnt"] for r in rows)
        rate = (theme_cnt / total * 100) if total else 0
        return rows, theme_cnt, rate

    def top_snippets(spu_id: str, tags: list[str], limit: int = 3):
        placeholders = ",".join("?" * len(tags))
        rows = conn.execute(
            f"""
            SELECT t.tag_name, m.platform, m.posted_at,
                   COALESCE(NULLIF(trim(m.content_text), ''), NULLIF(trim(m.title_text), ''), '') AS raw_text
            FROM voc_message_tag t
            JOIN voc_message m ON t.message_uid = m.message_uid
            WHERE m.canonical_spu_id=? AND t.tag_name IN ({placeholders})
            ORDER BY length(COALESCE(m.content_text, '')) DESC, m.posted_at DESC
            LIMIT 20
            """,
            (spu_id, *tags),
        ).fetchall()
        snippets = []
        seen = set()
        for row in rows:
            text = shorten(" ".join((row["raw_text"] or "").split()), width=140, placeholder="...")
            if not text or text in seen:
                continue
            seen.add(text)
            snippets.append((row["tag_name"], row["platform"], row["posted_at"], text))
            if len(snippets) >= limit:
                break
        return snippets

    lines = []
    lines.append(f"# {name_map.get(base_spu_id, base_spu_id)} vs {name_map.get(compare_spu_id, compare_spu_id)} 文本级 Deep Dive")
    lines.append("")
    lines.append("## 1. 对比口径")
    lines.append("")
    lines.append(f"- 本品：`{name_map.get(base_spu_id, base_spu_id)}`")
    lines.append(f"- 关键对比竞品：`{name_map.get(compare_spu_id, compare_spu_id)}`")
    lines.append("- 主题范围：`清洁效果与水痕污渍`、`边角与覆盖率`、`噪音体验`、`避障越障与卡困`")
    lines.append("- 周期：`2025Q4`、`2026Q1`")
    lines.append("")
    lines.append("## 2. 总体风险对比")
    lines.append("")
    lines.append("| period | spu | message_count | negative_count | negative_rate |")
    lines.append("| --- | --- | --- | --- | --- |")
    for period_id, period_name in [("2025q4", "2025Q4"), ("2026q1", "2026Q1")]:
        for spu_id in [base_spu_id, compare_spu_id]:
            stat = negative_rate(spu_id, period_id)
            if not stat:
                continue
            msg_cnt, neg_cnt, rate = stat
            lines.append(f"| {period_name} | {name_map.get(spu_id, spu_id)} | {msg_cnt} | {neg_cnt} | {rate:.1f}% |")
    lines.append("")

    for theme_name, tags in THEMES:
        base_rows, base_cnt, base_rate = theme_stats(base_spu_id, tags)
        comp_rows, comp_cnt, comp_rate = theme_stats(compare_spu_id, tags)
        base_top = base_rows[0] if base_rows else {"tag_name": "-", "cnt": 0}
        comp_top = comp_rows[0] if comp_rows else {"tag_name": "-", "cnt": 0}
        lines.append(f"## {theme_name}")
        lines.append("")
        lines.append("| spu | theme_hit_count | theme_share | top_tag | top_tag_count |")
        lines.append("| --- | --- | --- | --- | --- |")
        lines.append(f"| {name_map.get(base_spu_id, base_spu_id)} | {base_cnt} | {base_rate:.2f}% | {base_top['tag_name']} | {base_top['cnt']} |")
        lines.append(f"| {name_map.get(compare_spu_id, compare_spu_id)} | {comp_cnt} | {comp_rate:.2f}% | {comp_top['tag_name']} | {comp_top['cnt']} |")
        lines.append("")
        lines.append("结论：")
        lines.append("")
        lines.append(f"- `{name_map.get(base_spu_id, base_spu_id)}` 在主题 `{theme_name}` 上的命中占比为 `{base_rate:.2f}%`，`{name_map.get(compare_spu_id, compare_spu_id)}` 为 `{comp_rate:.2f}%`。")
        lines.append(f"- 两者差值约 `{(base_rate - comp_rate):+.2f}pp`。")
        lines.append(f"- `{name_map.get(base_spu_id, base_spu_id)}` 最突出的子标签是 `{base_top['tag_name']}`，`{name_map.get(compare_spu_id, compare_spu_id)}` 最突出的子标签是 `{comp_top['tag_name']}`。")
        lines.append("")
        lines.append(f"{name_map.get(base_spu_id, base_spu_id)} 文本证据：")
        lines.append("")
        for tag_name, platform, posted_at, text in top_snippets(base_spu_id, tags):
            lines.append(f"- `{tag_name}` | `{platform or '-'} / {posted_at or '-'}`：{text}")
        lines.append("")
        lines.append(f"{name_map.get(compare_spu_id, compare_spu_id)} 文本证据：")
        lines.append("")
        for tag_name, platform, posted_at, text in top_snippets(compare_spu_id, tags):
            lines.append(f"- `{tag_name}` | `{platform or '-'} / {posted_at or '-'}`：{text}")
        lines.append("")

    lines.append("## 3. 结论与建议")
    lines.append("")
    lines.append(f"- `{name_map.get(base_spu_id, base_spu_id)}` 相比 `{name_map.get(compare_spu_id, compare_spu_id)}`，在 `清洁效果与水痕污渍`、`边角与覆盖率`、`噪音体验` 三个主题上都更值得优先深挖。")
    lines.append(f"- 如果下一步只选一个竞品做深入复盘，仍建议优先 `{name_map.get(compare_spu_id, compare_spu_id)}`，因为它样本量最大且表现更稳定。")
    lines.append("- 后续建议把上述文本片段继续回挂到问卷题项和访谈案例，做“标签 -> 原声 -> 结构化问题”的闭环。")
    conn.close()
    return "\n".join(lines)


def build_issue_closure_report(base_spu_id: str, compare_spu_id: str) -> str:
    name_map = {}
    conn = connect(VOC_DB)
    for row in conn.execute(
        "SELECT canonical_spu_id, COALESCE(spu_name, canonical_spu_id) AS spu_name FROM vw_voc_message_brief WHERE canonical_spu_id IN (?, ?) GROUP BY canonical_spu_id, COALESCE(spu_name, canonical_spu_id)",
        (base_spu_id, compare_spu_id),
    ):
        name_map[row["canonical_spu_id"]] = row["spu_name"]
    conn.close()
    lines = []
    lines.append(f"# {name_map.get(base_spu_id, base_spu_id)} vs {name_map.get(compare_spu_id, compare_spu_id)} 问题闭环专题")
    lines.append("")
    lines.append("## 1. 结论先行")
    lines.append("")
    lines.append(f"- `{name_map.get(base_spu_id, base_spu_id)}` 相比 `{name_map.get(compare_spu_id, compare_spu_id)}`，在 `清洁效果与水痕污渍`、`边角与覆盖率`、`噪音体验`、`避障越障与卡困` 四个主题上都更重。")
    lines.append(f"- 从时间变化看，`{name_map.get(base_spu_id, base_spu_id)}` 在 `2025Q4` 到 `2026Q1` 负向率持续上升，而 `{name_map.get(compare_spu_id, compare_spu_id)}` 虽也抬升，但整体仍明显更低。")
    lines.append(f"- 当前更适合把 `{name_map.get(base_spu_id, base_spu_id)} vs {name_map.get(compare_spu_id, compare_spu_id)}` 定义为“稳定差异对标专题”，用于指导后续产品和用户研究动作。")
    lines.append("")
    lines.append("## 2. 问题闭环")
    lines.append("")
    lines.append("### 2.1 清洁效果与水痕污渍")
    lines.append("")
    lines.append(f"- VOC 现象：`{name_map.get(base_spu_id, base_spu_id)}` 在该主题命中占比显著高于 `{name_map.get(compare_spu_id, compare_spu_id)}`。")
    lines.append(f"- 问卷证据：`{name_map.get(base_spu_id, base_spu_id)}` 的专项问卷能直接提供污渍、水痕、区域、材质相关题项。")
    lines.append("- 访谈解释：用户诉求会进一步落到顽固污渍处理与吸水能力。")
    lines.append("- 洞察：这不是单一“拖不干净”问题，而是材质、污渍类型和清洁模式共同作用的结果。")
    lines.append("")
    lines.append("### 2.2 边角与覆盖率")
    lines.append("")
    lines.append(f"- VOC 现象：`{name_map.get(base_spu_id, base_spu_id)}` 在边角与覆盖率上的负向命中更集中。")
    lines.append("- 问卷证据：覆盖率与漏扫位置都有直连题项可调用。")
    lines.append("- 访谈解释：边角问题会直接损伤“是否真能替代人工”的感知。")
    lines.append("- 洞察：边角不是细节问题，而是工作完成率与智能性感知问题。")
    lines.append("")
    lines.append("### 2.3 噪音体验")
    lines.append("")
    lines.append(f"- VOC 现象：`{name_map.get(base_spu_id, base_spu_id)}` 在噪音体验上的负评占比高于 `{name_map.get(compare_spu_id, compare_spu_id)}`。")
    lines.append("- 问卷证据：专项问卷已有噪音体验题项。")
    lines.append("- 洞察：噪音会压缩真实可使用时间窗，损伤“白天也能放心运行”的能力。")
    lines.append("")
    lines.append("### 2.4 避障越障与卡困")
    lines.append("")
    lines.append(f"- VOC 现象：`{name_map.get(base_spu_id, base_spu_id)}` 在越障、台阶、卡困上的命中占比更高。")
    lines.append("- 问卷证据：越障/上台阶与卡困/避障已有专项题项。")
    lines.append("- 洞察：风险不只是单次失败，而是让用户重新回到需要人工善后的状态。")
    lines.append("")
    lines.append("## 3. 时间变化判断")
    lines.append("")
    lines.append(f"- `{name_map.get(base_spu_id, base_spu_id)}` 负向率在最近两个季度持续抬升。")
    lines.append(f"- `{name_map.get(compare_spu_id, compare_spu_id)}` 也有波动，但绝对水平仍更低。")
    lines.append("- 这意味着：重点不只是“有没有上升”，而是谁的风险水平更高、谁的改善更紧迫。")
    lines.append("")
    lines.append("## 4. 动作建议")
    lines.append("")
    lines.append("- 产品线：优先把水痕污渍、边角覆盖、噪音、越障卡困作为下一代闭环问题。")
    lines.append("- 研究线：继续把当前 pairwise 结论回挂到问卷题项和访谈案例。")
    lines.append("- 数据线：把对应主题的 VOC 原声、问卷题项、访谈案例固化成专题证据包。")
    return "\n".join(lines)


def build_voc_appendix(spu_id: str) -> str:
    conn = connect(VOC_DB)
    db_names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
    }
    db_names.update(
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_temp_master WHERE type IN ('table', 'view')").fetchall()
    )
    if "voc_tag_topic_map" in db_names:
        full_tags = list(
            conn.execute(
                """
                SELECT t.tag_name, t.tag_sentiment, COUNT(DISTINCT t.message_uid) AS msg_cnt,
                       MAX(map.topic_domain_name_cn) AS topic_domain_name_cn,
                       MAX(COALESCE(map.topic_group_name_cn,'')) AS topic_group_name_cn,
                       MAX(COALESCE(map.context_bucket_name_cn,'')) AS context_bucket_name_cn
                FROM voc_message_tag t
                JOIN voc_message m ON t.message_uid=m.message_uid
                LEFT JOIN voc_tag_topic_map map ON t.tag_name=map.tag_name
                WHERE m.canonical_spu_id=?
                GROUP BY t.tag_name, t.tag_sentiment
                ORDER BY msg_cnt DESC, t.tag_name
                """,
                (spu_id,),
            )
        )
    else:
        full_tags = list(
            conn.execute(
                """
                SELECT
                    t.tag_name,
                    t.tag_sentiment,
                    COUNT(DISTINCT t.message_uid) AS msg_cnt,
                    '' AS topic_domain_name_cn,
                    '' AS topic_group_name_cn,
                    '' AS context_bucket_name_cn
                FROM voc_message_tag t
                JOIN voc_message m ON t.message_uid=m.message_uid
                WHERE m.canonical_spu_id=?
                GROUP BY t.tag_name, t.tag_sentiment
                ORDER BY msg_cnt DESC, t.tag_name
                """,
                (spu_id,),
            )
        )
    neg_decomp = list(
        conn.execute(
            """
            WITH neg AS (
              SELECT DISTINCT m.message_uid, t.tag_name AS negative_tag
              FROM voc_message m JOIN voc_message_tag t ON m.message_uid=t.message_uid
              WHERE m.canonical_spu_id=? AND t.tag_sentiment='负面'
            ), ctx AS (
              SELECT message_uid, context_bucket_name_cn, topic_group_name_cn, tag_name
              FROM vw_voc_message_tag_mapped
              WHERE context_bucket_code IS NOT NULL
            )
            SELECT negative_tag, context_bucket_name_cn, topic_group_name_cn, tag_name AS related_context_tag,
                   COUNT(DISTINCT neg.message_uid) AS msg_cnt
            FROM neg JOIN ctx ON neg.message_uid=ctx.message_uid
            GROUP BY negative_tag, context_bucket_name_cn, topic_group_name_cn, related_context_tag
            ORDER BY negative_tag, msg_cnt DESC, related_context_tag
            """,
            (spu_id,),
        )
    )
    img_rows = list(
        conn.execute(
            """
            SELECT t.tag_name AS negative_tag, m.platform, m.posted_at, m.image_links_text,
                   substr(replace(replace(COALESCE(m.content_text,''), char(10), ' '), char(13), ' '),1,120) AS snippet
            FROM voc_message_tag t
            JOIN voc_message m ON t.message_uid=m.message_uid
            WHERE m.canonical_spu_id=? AND t.tag_sentiment='负面'
              AND m.image_links_text IS NOT NULL AND trim(m.image_links_text) != ''
            ORDER BY t.tag_name, m.posted_at DESC
            """,
            (spu_id,),
        )
    )
    deduped = []
    seen = set()
    for row in img_rows:
        key = (row["negative_tag"], row["image_links_text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    lines = []
    lines.append(f"# {spu_id} VOC 完整标签与负评拆解附录")
    lines.append("")
    lines.append("## 1. 说明")
    lines.append("")
    lines.append(f"- 对象：`{spu_id}`")
    lines.append(f"- 完整标签行数：`{len(full_tags)}`")
    lines.append(f"- 负评拆解行数：`{len(neg_decomp)}`")
    lines.append(f"- 负评图片证据行数：`{len(deduped)}`")
    lines.append("")
    lines.append("## 2. 完整标签表")
    lines.append("")
    lines.append("| tag_name | tag_sentiment | msg_cnt | topic_domain | topic_group | context_bucket |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in full_tags:
        lines.append(f"| {row['tag_name']} | {row['tag_sentiment'] or ''} | {row['msg_cnt']} | {row['topic_domain_name_cn'] or ''} | {row['topic_group_name_cn'] or ''} | {row['context_bucket_name_cn'] or ''} |")
    lines.append("")
    lines.append("## 3. 全量负评拆解表")
    lines.append("")
    lines.append("| negative_tag | context_bucket | topic_group | related_context_tag | msg_cnt |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in neg_decomp:
        lines.append(f"| {row['negative_tag']} | {row['context_bucket_name_cn'] or ''} | {row['topic_group_name_cn'] or ''} | {row['related_context_tag']} | {row['msg_cnt']} |")
    lines.append("")
    lines.append("## 4. 负评图片证据表")
    lines.append("")
    lines.append("| negative_tag | platform | posted_at | image_links | snippet |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in deduped:
        img = (row["image_links_text"] or "").replace("\n", "<br>")
        snippet = (row["snippet"] or "").replace("|", "/").strip()
        lines.append(f"| {row['negative_tag']} | {row['platform'] or ''} | {row['posted_at'] or ''} | {img} | {snippet} |")
    conn.close()
    return "\n".join(lines)


def build_direct_source_coverage(result: dict[str, object]) -> str:
    truth = connect(TRUTH_DB)
    survey = connect(SURVEY_DB)
    summary = connect(SUMMARY_DB)
    raw = connect(INTERVIEW_DB)
    voc = connect(VOC_DB)
    selected_spus = result["selected_spus"]  # type: ignore[index]
    spu_ids = [row["spu_id"] for row in selected_spus]
    placeholders = ",".join("?" * len(spu_ids))
    truth_rows = list(
        truth.execute(
            f"""
            SELECT spu_id, spu_name, self_competitor_type, 'selected_scope' AS scope_label
            FROM spu_dim
            WHERE spu_id IN ({placeholders})
            ORDER BY self_competitor_type DESC, spu_name
            """,
            spu_ids,
        )
    )
    survey_direct = {r["inferred_spu_id"]: dict(r) for r in survey.execute(f"SELECT wave_name, market_scope, inferred_spu_id, survey_topic FROM vw_wave_capability_summary WHERE inferred_spu_id IN ({placeholders})", spu_ids)}
    summary_direct = {r["inferred_spu_id"]: dict(r) for r in summary.execute(f"SELECT inferred_spu_id, COUNT(*) AS case_count FROM vw_summary_case_module_coverage WHERE inferred_spu_id IN ({placeholders}) GROUP BY inferred_spu_id", spu_ids)}
    raw_direct = {r["inferred_spu_id"]: dict(r) for r in raw.execute(f"SELECT inferred_spu_id, COUNT(*) AS case_count FROM interview_case WHERE inferred_spu_id IN ({placeholders}) GROUP BY inferred_spu_id", spu_ids)}
    voc_direct = {r["canonical_spu_id"]: dict(r) for r in voc.execute(f"SELECT canonical_spu_id, COUNT(*) AS msg_cnt, MIN(posted_at) AS min_dt, MAX(posted_at) AS max_dt FROM voc_message WHERE canonical_spu_id IN ({placeholders}) GROUP BY canonical_spu_id", spu_ids)}
    lines = []
    lines.append("# 当前对象直连数据覆盖报告")
    lines.append("")
    lines.append("| spu_name | type | VOC直连 | 问卷直连 | 访谈总结直连 | 原始访谈直连 | 说明 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in truth_rows:
        sid = row["spu_id"]
        notes = []
        voc_cell = f"{voc_direct[sid]['msg_cnt']}条" if sid in voc_direct else "无"
        survey_cell = survey_direct[sid]["wave_name"] if sid in survey_direct else "无"
        summary_cell = f"{summary_direct[sid]['case_count']}例" if sid in summary_direct else "无"
        raw_cell = f"{raw_direct[sid]['case_count']}例" if sid in raw_direct else "无"
        if sid not in survey_direct:
            notes.append("无直连问卷")
        if sid not in summary_direct:
            notes.append("无直连总结")
        if sid not in raw_direct:
            notes.append("无直连原访")
        if sid not in voc_direct:
            notes.append("无直连VOC")
        lines.append(f"| {row['spu_name']} | {row['self_competitor_type']} | {voc_cell} | {survey_cell} | {summary_cell} | {raw_cell} | {'；'.join(notes) if notes else '直连较完整'} |")
    for conn in [truth, survey, summary, raw, voc]:
        conn.close()
    return "\n".join(lines)


def negative_rate_label(voc_row: dict[str, object] | None) -> str:
    if not voc_row:
        return "暂无稳定 VOC 风险判断"
    message_count = int(voc_row.get("message_count") or 0)
    negative_count = int(voc_row.get("negative_count") or 0)
    if not message_count:
        return "暂无稳定 VOC 风险判断"
    rate = negative_count / message_count * 100
    return f"当前负向率约 {rate:.1f}%（{negative_count}/{message_count}）"


def build_standard_presentation_brief(args: argparse.Namespace, result: dict[str, object], style_profile: dict[str, object]) -> str:
    banned_phrases = list(style_profile.get("banned_phrases", []))
    primary_self = pick_primary_self(result)
    primary_competitor = pick_primary_competitor(args, result)
    voc_by_spu = {row["canonical_spu_id"]: row for row in result["voc_rows"]}  # type: ignore[index]
    support_matrix = result["support_matrix"]  # type: ignore[index]
    unsupported_modules = [row["module_name_cn"] for row in support_matrix if row["support_level"] != "支持"]
    self_name = primary_self["spu_name"] if primary_self else "当前本品对象"
    competitor_name = primary_competitor["spu_name"] if primary_competitor else "关键竞品"
    self_voc_row = voc_by_spu.get(primary_self["spu_id"]) if primary_self else None
    analysis_goal_text = "；".join(args.analysis_goal) if args.analysis_goal else "回答用户关心的核心用户问题"
    current_limit = "、".join(unsupported_modules[:3]) if unsupported_modules else "当前关键模块已基本可用"

    lines = [
        f"# {args.analysis_title or self_name + ' 当前汇报稿'}",
        "",
        "## 0. 问题回答",
        "",
        f"- 当前最核心的结论是，`{self_name}` 已经可以拿来做这轮讨论的主对象。",
        f"- 背后真正的问题，不是要不要继续铺更多对象，而是先把 `{self_name}` 讲透：{negative_rate_label(self_voc_row)}。",
        f"- 这轮更该优先回答的是：`{analysis_goal_text}`。",
        "",
        "## 1. 看用户",
        "",
    ]
    if result["survey_rows"] and result["summary_rows"]:  # type: ignore[index]
        lines.append(f"- 现在能支撑 `{self_name}` 用户判断的，不只是问卷，还有定性总结，所以这轮可以先讲人，再讲问题。")
        lines.append(f"- 更值得注意的不是“有没有用户画像”，而是 `{self_name}` 现在已经能把人、场景和问题串起来看。")
    elif result["survey_rows"]:  # type: ignore[index]
        lines.append(f"- 当前用户判断主要还是来自 `{self_name}` 的问卷入口，能先看出画像和使用旅程，但还不适合把结论讲得太满。")
    else:
        lines.append(f"- 当前关于 `{self_name}` 的用户判断还偏薄，更适合先把它当成方向判断，而不是完整画像。")
    lines.append("")
    lines.append("## 2. 看竞争")
    lines.append("")
    if primary_self and primary_competitor and self_voc_row and voc_by_spu.get(primary_competitor["spu_id"]):
        competitor_voc_row = voc_by_spu[primary_competitor["spu_id"]]
        lines.append(f"- 现在更值得讨论的竞争对象是 `{competitor_name}`，因为它和 `{self_name}` 已经能放在同一张真实用户反馈桌子上看。")
        lines.append(
            f"- 对 `{self_name}` 来说，和 `{competitor_name}` 的差距不该只按参数讲，而要按“用户为什么更愿意相信别人能把事做完”去讲。"
        )
        lines.append(
            f"- 简单看风险水平，`{self_name}` {negative_rate_label(self_voc_row)}；`{competitor_name}` {negative_rate_label(competitor_voc_row)}。"
        )
    else:
        lines.append("- 这一轮竞争讨论先不要讲满。当前更像是在做对比线索梳理，而不是稳定差异定案。")
    lines.append("")
    lines.append("## 3. 看自己")
    lines.append("")
    lines.append("- 当前数据真正能帮我们讲清的，是问题在哪、为什么会被放大、值不值得先做。")
    lines.append("- 还不够讲满的，是价格、长期路线图、资源取舍和完整 KANO。")
    lines.append(f"- 所以这轮更像是在收口当前判断，而不是一次把所有决策都定完。")
    lines.append("")
    lines.append("## 4. 需求优先级讨论")
    lines.append("")
    if primary_self:
        lines.append(f"- 现在更该优先推进的，不是泛泛地讲“体验优化”，而是围绕 `{self_name}` 当前已经反复出现的问题去收口。")
        lines.append("- 先把最伤害用户信任的那组问题讲透，再决定要不要继续把更多议题推到前面。")
    else:
        lines.append("- 当前更该优先推进的，是先把主对象和关键问题讲清，再进入优先级收口。")
    lines.append("")
    lines.append("## 5. 缺口 / 风险 / 下一步")
    lines.append("")
    lines.append("### 当前讨论焦点")
    lines.append("")
    lines.append(f"- 先把 `{self_name}` 作为当前主对象讲透，不要把对象池越铺越散。")
    if primary_competitor:
        lines.append(f"- 如果继续下钻，优先围绕 `{self_name} vs {competitor_name}` 做专题闭环。")
    lines.append("")
    lines.append("### 当前不能下满结论的地方")
    lines.append("")
    lines.append(f"- 当前还不能直接讲满的模块，主要集中在 `{current_limit}`。")
    lines.append("- 这些地方不是这轮没写，而是现在就不该硬写成稳定结论。")
    lines.append("")
    lines.append("## 附：数据能力声明")
    lines.append("")
    lines.append(
        f"- 当前直连材料包括：问卷波次 `{len(result['survey_rows'])}` 个、访谈总结分组 `{len(result['summary_rows'])}` 个、VOC 对象 `{len(result['voc_rows'])}` 个。"
    )
    lines.append("- 当前更适合支撑用户/场景/问题诊断与竞争差距判断。")
    lines.append("- 当前不适合直接支撑价格策略、完整路线图和完整 KANO 坐标。")
    return "\n".join(sanitize_presentation_text(line, banned_phrases) if line.startswith("- ") else line for line in lines)


def build_portfolio_presentation_brief(
    *,
    category_name: str,
    time_scope: str,
    market: str | None,
    series_payloads: list[dict[str, object]],
    analysis_goal_text: str,
    style_profile: dict[str, object],
) -> str:
    banned_phrases = list(style_profile.get("banned_phrases", []))
    x_payload = next((payload for payload in series_payloads if payload["series_code"] == "X"), None)
    t_payload = next((payload for payload in series_payloads if payload["series_code"] == "T"), None)
    x_ready = decision_readiness_label(x_payload["result"]) if x_payload else "待补充"  # type: ignore[index]
    t_ready = decision_readiness_label(t_payload["result"]) if t_payload else "待补充"  # type: ignore[index]
    portfolio_lines = portfolio_exec_summary_lines(series_payloads)

    lines = [
        f"# {category_name} 当前汇报稿",
        "",
        "## 0. 问题回答",
        "",
        f"- 当前最核心的结论是，这一轮更值得先讲透的是 `X 系列`。",
        f"- 背后真正的问题，不是 X 和 T 要不要一起讲，而是谁已经到了可以做专题判断，谁还应该保留边界。当前 `X 系列` 是 `{x_ready}`，`T 系列` 是 `{t_ready}`。",
        f"- 这轮更该优先回答的是：`{analysis_goal_text}`。",
        "",
        "## 1. 看用户",
        "",
        "- 从当前输入看，X 系列更适合讲“为什么问题会被放大”，T 系列更适合讲“哪些判断已经出来，但还不能讲满”。",
        "- 所以这轮不要急着把 X/T 讲成同一种人，而是先承认它们现在在证据完整度上就不一样。",
        "",
        "## 2. 看竞争",
        "",
    ]
    for line in portfolio_lines[:2]:
        lines.append(f"- {line}")
    lines.extend(
        [
            "- 竞争这件事现在更适合按系列分开讲，而不是把所有对象摊成一张表去讲平均数。",
            "",
            "## 3. 看自己",
            "",
            "- 当前数据库真正能帮我们讲清的，是哪些系列/对象已经可以进入专题判断，哪些还停留在方向判断。",
            "- 还不能一次讲满的，仍然是价格、路线图和资源取舍。",
            "",
            "## 4. 需求优先级讨论",
            "",
            "- 当前更该优先推进的，是先把 X 系列里风险最高的对象和问题讲透，再决定 T 系列哪些问题要跟上来。",
            "- 这轮不要把“系列化策略”讲成平均分配资源，而要承认不同系列现在处在不同的判断阶段。",
            "",
            "## 5. 缺口 / 风险 / 下一步",
            "",
            "### 当前讨论焦点",
            "",
            "- 先围绕 X 系列高风险对象做专题闭环，再决定 T 系列下一步是补竞争、补用户，还是补问题证据。",
            "- 当前汇报的价值不在于把所有对象讲全，而在于把最值得讨论的那部分讲准。",
            "",
            "### 当前不能下满结论的地方",
            "",
            "- T 系列当前仍有模块依赖较弱证据或直连输入不够，这些地方先不要硬写成稳定系列判断。",
            "- 价格、实验室表现、财务/BP 和完整 KANO 这轮都不该硬定。",
            "",
            "## 附：数据能力声明",
            "",
            f"- 当前覆盖：X/T 两个系列，分析周期 `{time_scope}`，市场范围 `{market or 'ALL'}`。",
            "- 当前更适合支撑系列优先级、对象聚焦和当前问题收口。",
            "- 当前不适合直接给完整路线图和资源排布定案。",
        ]
    )
    return "\n".join(sanitize_presentation_text(line, banned_phrases) if line.startswith("- ") else line for line in lines)


def build_ppt_gap_diagnosis(
    *,
    presentation_main_report_text: str,
    main_report_text: str,
    series_positioning: dict[str, object],
    strategy_translation: dict[str, object],
) -> str:
    lines = [
        "# PPT Gap Diagnosis",
        "",
        "## 1. 结构 gap",
        "",
        "- 当前后台完整报告仍然以“分析对象与证据边界 / 一级结论树 / 递归论证”作为主骨架，而 PPT 的推进顺序更像“看用户 / 看竞争 / 看自己 / 需求优先级讨论 / 路线图”。",
        "- 如果前台只在后台章节上做表层改写，就会像更自然的脚手架，而不会像真正的汇报稿。",
        "",
        "## 2. 结论 gap",
        "",
        "- 现有结论已经开始出现人物模式、分群差异、问题包和跨源解释，但还需要继续往“系列定位 / 价值支柱 / 路线图取舍”上翻译。",
        "",
        "## 3. 方法 gap",
        "",
        "- 当前已经补了研究者抽象层，但前台总报告还没有完全以这些中间产物为组织主线。",
        "",
        "## 4. 策略 gap",
        "",
    ]
    for row in strategy_translation.get("priority_reasoning", []):
        lines.append(f"- {row}")
    lines.extend(
        [
            "",
            "## 5. 风格 gap",
            "",
            "- 前台口吻已经比以前更像汇报者，但如果结构主线不切换，仍然容易保留“报告模板感”。",
            "",
            "## 6. 当前已补齐的高价值层",
            "",
        ]
    )
    for row in series_positioning.get("series_rows", []):
        lines.append(f"- `{row['series_code']}`：{row['positioning_label']}。")
    return "\n".join(lines)


def wave_row_lookup(conn: sqlite3.Connection, wave_name: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT wave_id, wave_name, survey_topic, inferred_spu_id, market_scope, maturity_stage
        FROM survey_wave
        WHERE wave_name = ?
        LIMIT 1
        """,
        (wave_name,),
    ).fetchone()


def build_wave_snapshot(conn: sqlite3.Connection, wave_name: str) -> dict[str, object]:
    wave = wave_row_lookup(conn, wave_name)
    if not wave:
        return {}
    sample_count = fetch_wave_sample_count(conn, wave["wave_id"])
    capability_rows = {
        code: fetch_survey_capability_question_summaries(conn, wave["wave_id"], code, sample_count)
        for code in ["purchase_motivation", "usage_journey", "concept_validation"]
    }
    return {
        "wave_name": wave["wave_name"],
        "survey_topic": wave["survey_topic"],
        "inferred_spu_id": wave["inferred_spu_id"],
        "maturity_stage": wave["maturity_stage"],
        "sample_count": sample_count,
        "capability_rows": capability_rows,
    }


def flatten_wave_snapshot_text(snapshot: dict[str, object]) -> list[str]:
    texts: list[str] = []
    for rows in snapshot.get("capability_rows", {}).values():
        for row in rows:
            texts.extend(str(cell) for cell in row[:2])
    return texts


def top_answers_text(snapshot: dict[str, object], capability_code: str, limit: int = 3) -> str:
    rows = snapshot.get("capability_rows", {}).get(capability_code, [])
    values: list[str] = []
    for row in rows:
        if len(row) >= 2:
            values.append(str(row[1]))
    values = [value for value in values if value and value != "-"]
    return "；".join(values[:limit]) if values else "-"


def theme_strength(snapshot: dict[str, object], keywords: tuple[str, ...]) -> int:
    texts = flatten_wave_snapshot_text(snapshot)
    score = 0
    for text in texts:
        normalized = normalize_text_local(text)
        score += sum(1 for keyword in keywords if normalize_text_local(keyword) in normalized)
    return score


def generation_theme_summary(snapshot: dict[str, object]) -> list[str]:
    strengths = [
        (theme_name, theme_strength(snapshot, keywords))
        for theme_name, keywords in GENERATION_THEME_RULES.items()
    ]
    strengths.sort(key=lambda item: (-item[1], item[0]))
    return [name for name, score in strengths if score > 0][:3]


def build_generation_lead_judgment(series_code: str, current: dict[str, object], previous: dict[str, object], cleaning_ref: dict[str, object], multi_robot_ref: dict[str, object]) -> str:
    current_themes = generation_theme_summary(current)
    previous_themes = generation_theme_summary(previous)
    if series_code == "X":
        return f"X 系列本代更像从上一代的 `基础清洁完成` 继续往 `低介入托管` 升级；但 `{ '、'.join(generation_theme_summary(cleaning_ref)[:2]) or '清洁底线' }` 仍然是必须守住的底线，而 `{ '、'.join(generation_theme_summary(multi_robot_ref)[:1]) or '多机协同' }` 更像未来方向。"
    return f"T 系列本代更像把上一代被放大的 `维护负担` 往 `清洁结果 + 稳定托管` 收；但真正决定代际跃迁的，仍然是能不能减少返工、减少维护和减少兜底压力。"


def build_generation_compare_rows(series_code: str, current: dict[str, object], previous: dict[str, object], previous_ref: dict[str, object], cleaning_ref: dict[str, object], multi_robot_ref: dict[str, object]) -> list[list[str]]:
    rows = [
        ["当前更打动用户的卖点", top_answers_text(current, "purchase_motivation"), top_answers_text(previous, "purchase_motivation"), top_answers_text(cleaning_ref, "purchase_motivation")],
        ["当前更容易卡住用户的底线问题", top_answers_text(current, "usage_journey"), top_answers_text(previous, "usage_journey"), top_answers_text(cleaning_ref, "usage_journey")],
        ["抽象主题重心", "、".join(generation_theme_summary(current)) or "-", "、".join(generation_theme_summary(previous)) or "-", "、".join(generation_theme_summary(cleaning_ref)) or "-"],
    ]
    if previous_ref:
        rows.append(
            [
                "上一代成熟后沉淀了什么",
                "-",
                top_answers_text(previous_ref, "usage_journey"),
                "这可以作为本代避免重演的问题清单",
            ]
        )
    rows.append(
        [
            "多机协作调研的启发",
            "-",
            "-",
            top_answers_text(multi_robot_ref, "concept_validation"),
        ]
    )
    if series_code == "X":
        rows.append(
            [
                "代际判断",
                "本代更该讲“少操心、少返工、真托管”。",
                "上一代更像“把基础清洁做完，部分边界还能接受”。",
                "清洁需求调研说明底线仍是清洁结果和覆盖率；多机协作不该替代本代主卖点。",
            ]
        )
    else:
        rows.append(
            [
                "代际判断",
                "本代更该讲“把结果做稳，同时少返工、少维护”。",
                "上一代更像“维护痛点先暴露出来，用户对稳定托管更敏感”。",
                "清洁需求调研说明底线仍是顽固污渍、边角和完成率；多机协作更像远期方向。",
            ]
        )
    return rows


def build_generation_strategy_summary(series_code: str) -> str:
    if series_code == "X":
        return "X 的代际策略翻译不是“本代参数更强”，而是“基础完成率要继承，托管承诺要补强，协同能力先别抢主叙事”。"
    return "T 的代际策略翻译不是“本代卖点更多”，而是“上一代暴露的维护和返工问题要收住，结果稳定和托管可信要前置”。"


def build_generation_strategy_rows(series_code: str) -> list[list[str]]:
    if series_code == "X":
        return [
            [
                "该继承什么",
                "上一代已经证明：基础清洁完成率和地毯基础识别是最低门槛，不能因为讲托管而把这些底线讲丢。",
                "继续把“基础完成率”保留为底层能力，不让用户重新回到怀疑扫不扫得干净的阶段。",
            ],
            [
                "该修什么",
                "本代真正要补的是边角/污渍/维护负担，尤其是把“解放双手”从口号变成少操心、少返工、真托管。",
                "优先修：顽固污渍、边角覆盖、基站维护、自净与托管信任。",
            ],
            [
                "本代主讲什么",
                "主卖点不该再停留在“基础会扫拖”，而该升级到“把结果做稳，同时别把麻烦重新甩回给用户”。",
                "前台语言统一收在：少操心、少返工、真托管。",
            ],
            [
                "先别提前讲什么",
                "多机协作、统一生态、第二台机器人更像远期机会层，不该替代本代主叙事。",
                "清洁需求调研证明底线仍是清洁结果与覆盖率；多机协作只适合做方向，不适合做本代主卖点。",
            ],
        ]
    return [
        [
            "该继承什么",
            "上一代已经把用户对维护、地毯、结果稳定的敏感点暴露出来了，这些不是历史包袱，而是本代必须正面回答的真实需求。",
            "继续围绕顽固污渍、边角、完成率讲“结果可信”。",
        ],
        [
            "该修什么",
            "本代最该修的不是再堆功能，而是把主机/拖地组件维护负担、返工和卡困带来的兜底压力收住。",
            "优先修：维护频次、清理难度、返工感、地毯卡困与关键区域完成率。",
        ],
        [
            "本代主讲什么",
            "本代更该讲“把结果做稳，同时少返工、少维护”，而不是只讲又多了哪些新能力。",
            "前台语言统一收在：结果更稳、少返工、少维护、托管更可信。",
        ],
        [
            "先别提前讲什么",
            "多机协作和生态联动仍然是未来方向，不该把 T 的代际升级误讲成表达型或生态型跃迁。",
            "T 的本代主叙事仍然应围绕结果稳定和托管可信，而不是炫技表达。",
        ],
    ]


def infer_theme_name_from_problem_package(package_name: str) -> str:
    if any(token in package_name for token in ("水渍", "污渍", "拖地效果", "清洁效果")):
        return "清洁效果与水痕污渍"
    if any(token in package_name for token in ("边角", "效率低", "覆盖")):
        return "边角与覆盖率"
    if any(token in package_name for token in ("噪音", "异音")):
        return "噪音体验"
    if any(token in package_name for token in ("台阶", "越障", "卡困", "卡住")):
        return "避障越障与卡困"
    if any(token in package_name for token in ("维护", "故障", "尘袋", "清理", "基站")):
        return "维护与基站操作"
    return "智能/App/语音/地图"


def build_competition_problem_rows(
    voc_problem_packages: dict[str, object],
    cross_source_interpretation: dict[str, object],
) -> list[list[str]]:
    package_rows = voc_problem_packages.get("packages", []) or []
    aggregated: dict[str, dict[str, object]] = {}
    explanation_lookup = {
        row["theme_name"]: row
        for row in cross_source_interpretation.get("interpretations", []) or []
    }
    for row in package_rows:
        package_name = str(row.get("package_name", "-"))
        theme_name = infer_theme_name_from_problem_package(package_name)
        item = aggregated.setdefault(
            package_name,
            {
                "theme_name": theme_name,
                "package_name": package_name,
                "message_count": 0,
                "trust_impact": row.get("trust_impact", "-"),
            },
        )
        item["message_count"] = int(item["message_count"]) + int(row.get("message_count", 0) or 0)
    ordered = sorted(aggregated.values(), key=lambda item: (-int(item["message_count"]), str(item["package_name"])))
    rows: list[list[str]] = []
    for item in ordered[:5]:
        explanation = explanation_lookup.get(item["theme_name"], {})
        rows.append(
            [
                str(item["package_name"]),
                str(item["trust_impact"]),
                str(explanation.get("best_explanation", "这类问题会改变用户对结果是否可信的判断。")),
                f"{item['message_count']}条相关反馈",
            ]
        )
    return rows


def build_competition_trend_rows(
    strategy_translation: dict[str, object],
    cross_source_interpretation: dict[str, object],
) -> list[list[str]]:
    aligned = {
        row["theme_name"]: row
        for row in cross_source_interpretation.get("interpretations", []) or []
    }
    bottom = strategy_translation.get("priority_buckets", {}).get("底线问题", []) or []
    opportunity = strategy_translation.get("priority_buckets", {}).get("机会点", []) or []
    not_now = strategy_translation.get("priority_buckets", {}).get("先不讲满", []) or []
    rows = [
        [
            "行业仍未解决什么",
            "、".join(bottom[:4]) if bottom else "-",
            "这些问题已经不是新鲜话题，但用户仍在持续反馈，说明行业一直在改善，却还没把事情真正做透。",
        ],
        [
            "已经改善但仍未到位",
            "、".join([theme for theme in bottom if theme in {"噪音体验", "避障越障与卡困", "维护与基站操作"}][:3]) or "噪音体验、避障越障与卡困、维护与基站操作",
            "用户已经能感知到改善，但一旦回到真实家庭场景，还是会被打回“得自己救场”的体验。",
        ],
        [
            "行业当前在卷什么",
            "参数、滚筒活水、局部高端卖点",
            "参数和卖点还在卷，但真正决定用户是否相信它能做完事的，仍然是清洁底线和托管信任。",
        ],
        [
            "什么更像未来方向",
            "、".join((opportunity + not_now)[:4]) if (opportunity or not_now) else "-",
            "这些议题可以讲方向，但不该替代当前主卖点，否则会把叙事从“解决问题”带偏到“想象未来”。",
        ],
    ]
    return rows


def build_competition_brand_rows(brand_mindshare_judgments: dict[str, object]) -> list[list[str]]:
    implication_map = {
        "科沃斯": "默认会被先想到，但若创新吸引力和核心体验不够强，就会被“老牌但不够惊喜”反噬。",
        "石头": "更像“不会出错”的标杆，竞争意义是规划、稳定性和完成率必须能正面对打。",
        "追觅": "更像高端感和新技术表达，竞争意义是高预算用户会先看它带来的惊喜感。",
        "云鲸": "更像拖地和维护便利的专业选手，竞争意义是水渍、拖地和售后心智不能输。",
        "大疆": "更像高智能想象空间，但专业积累仍被质疑，竞争意义是智能故事不能只停在光环层。",
        "小米": "更像入门性价比选项，竞争意义是高端叙事里不要被它带到低价比较框里。",
    }
    target_user_map = {
        "科沃斯": "先看老牌专业、希望体面稳妥的人",
        "石头": "更看重稳妥、完成率和路线规划的人",
        "追觅": "愿意为高端感和新技术惊喜买单的人",
        "云鲸": "更在意拖地、水渍和维护便利的人",
        "大疆": "被高智能想象打动、但仍在观望的人",
        "小米": "预算敏感、把它当入门或备用方案的人",
    }
    rows: list[list[str]] = []
    for row in brand_mindshare_judgments.get("judgments", []) or []:
        rows.append(
            [
                str(row.get("brand", "-")),
                str(row.get("one_line_label", "-")),
                implication_map.get(str(row.get("brand", "")), "当前仍需继续补强这条品牌竞争含义。"),
                target_user_map.get(str(row.get("brand", "")), "当前更容易打动的对象仍待补充。"),
            ]
        )
    return rows


def build_competition_current_brand_rows(competition_generation_analysis: dict[str, object]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in competition_generation_analysis.get("scope_summary_rows", []) or []:
        representative_models = str(row.get("representative_models", "-"))
        action_blob = "；".join(
            part
            for part in [
                str(row.get("current_focus", "-")),
                str(row.get("brand_shift_pattern", "-")),
                f"代表型号：{representative_models}" if representative_models != "-" else "",
            ]
            if part and part != "-"
        )
        rows.append(
            [
                str(row.get("competition_scope", "-")),
                str(row.get("lead_judgment", "-")),
                action_blob or "-",
                str(row.get("what_ecovacs_is_really_facing", "-")),
            ]
        )
    return rows


def build_competition_shape_rows(competition_generation_analysis: dict[str, object]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in competition_generation_analysis.get("shape_summary_rows", []) or []:
        rows.append(
            [
                str(row.get("shape_type", "-")),
                str(row.get("scope_breakdown", "-")),
                str(row.get("what_changed_this_generation", "-")),
                str(row.get("lead_judgment", "-")),
                str(row.get("what_it_means_for_ecovacs", "-")),
            ]
        )
    return rows


def build_competition_capability_rows(competition_capability_scan: dict[str, object]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in competition_capability_scan.get("rows", []) or []:
        rows.append(
            [
                str(row.get("capability_dimension", "-")),
                str(row.get("industry_front_runner", "-")),
                str(row.get("ecovacs_status", "-")),
                str(row.get("gap_type", "-")),
                str(row.get("why_it_matters", "-")),
            ]
        )
    return rows


def build_competition_matchup_rows(competition_matchup_matrix: dict[str, object]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in competition_matchup_matrix.get("rows", []) or []:
        rows.append(
            [
                f"{row.get('series_family', '-')} / {row.get('competition_scope', '-')}",
                str(row.get("competitor_product_name", "-")),
                str(row.get("why_this_matchup", "-")),
                str(row.get("voc_risk_to_watch", "-")),
            ]
        )
    return rows


def build_competition_voc_market_rows(
    competition_voc_market_split: dict[str, object],
    market_scope: str,
) -> list[list[str]]:
    rows: list[list[str]] = []
    market_rows = [
        row
        for row in competition_voc_market_split.get("market_rows", []) or []
        if row.get("market_scope") == market_scope
    ]
    grouped = {str(row.get("competition_scope", "")): row for row in market_rows}
    for scope in ["X_omni", "T_omni", "N_omni", "N_aes", "N_single"]:
        row = grouped.get(scope)
        if not row:
            rows.append(
                [
                    competition_scope_label(scope),
                    "待补充",
                    "-",
                    "当前该竞争带稳定 VOC 仍待补齐",
                    "待补充",
                    "当前该竞争带的稳定 VOC 仍待补齐，先不把这条带讲满。",
                    "-",
                ]
            )
            continue
        rows.append(
            [
                competition_scope_label(scope),
                str(row.get("top_problem_level_1", "待补充")),
                f"{float(row.get('message_share', 0.0)) * 100:.1f}%" if float(row.get("message_share", 0.0)) > 0 else "-",
                str(row.get("top_problem_level_2", "当前该竞争带稳定 VOC 仍待补齐")),
                str(row.get("performance_level", "待比较")),
                str(row.get("voc_complaint_summary", row.get("status_text", row.get("lead_judgment", "-")))),
                str(row.get("best_competitor_name", "-")) or "-",
            ]
        )
    return rows


def build_competition_conclusion_rows(competition_strategy_bridge: dict[str, object]) -> list[list[str]]:
    rows: list[list[str]] = []
    mapping = [
        ("X", "what_x_must_defend", "X"),
        ("T", "what_t_must_defend", "T"),
        ("N（三带）", "what_n_must_defend", "N"),
    ]
    push_map = {
        "X": "先把高端旗舰的清洁结果和托管可信讲实，再谈更远的高端表达。",
        "T": "先把主销 omni 的结果稳定和少维护讲成默认答案。",
        "N": "先分开补 omni 下探、AES 带基站和低价单机守位，不再把 N（三带）讲成一个总桶。",
    }
    set_bar_rows = [str(item) for item in competition_strategy_bridge.get("where_competitors_set_the_bar", []) or []]

    def set_bar_text(series_key: str) -> str:
        matched = [item for item in set_bar_rows if item.startswith(f"{series_key}：")]
        return "；".join(matched[:2]) or "；".join(set_bar_rows[:2]) or "-"

    for display_label, key, series_key in mapping:
        rows.append(
            [
                display_label,
                str(competition_strategy_bridge.get(key, "-")),
                push_map.get(series_key, "-"),
                set_bar_text(series_key),
            ]
        )
    return rows


def build_self_value_rows(
    strategy_translation: dict[str, object],
    x_positioning_packages: list[dict[str, object]],
) -> list[list[str]]:
    weak_labels = [package["positioning_name"] for package in x_positioning_packages if package.get("positioning_level") == "weak_signal"]
    rows: list[list[str]] = []
    for pillar in strategy_translation.get("value_pillar_candidates", []) or []:
        pillar_name = str(pillar.get("pillar_name", "-"))
        if "科技" in pillar_name:
            serves = weak_labels[0] if weak_labels else "方向性表达用户"
            delivery = "不要把它讲成基础能力，而要作为高价值用户的加分体验与品牌表达。"
        else:
            serves = "清洁管家 / 清洁帮手"
            delivery = "必须兑现到少操心、少返工、真托管，否则价值支柱会直接失真。"
        rows.append(
            [
                pillar_name,
                serves,
                str(pillar.get("why", "-")),
                delivery,
            ]
        )
    return rows


def build_self_demand_reorder_rows(
    strategy_translation: dict[str, object],
    generation_comparison: dict[str, object],
    x_positioning_packages: list[dict[str, object]],
) -> list[list[str]]:
    weak_labels = [package["positioning_name"] for package in x_positioning_packages if package.get("positioning_level") == "weak_signal"]
    generation_rows = {row["series_code"]: row for row in generation_comparison.get("series_rows", []) or []}
    return [
        [
            "底线需求",
            "清洁效果与水痕污渍、边角与覆盖率、避障越障与卡困",
            "这些问题已经从“体验改善”升级成“结果是否可信”的底线需求。",
            "必须进入主叙事，并优先投入修复资源。",
        ],
        [
            "托管需求",
            "省心托管 / 少操心 / 少返工",
            "X 和 T 的本代判断都在往托管承诺靠，说明用户不再满足于“能扫到”，而在意“能不能放心交给它”。",
            "统一兑现到：少操心、少返工、真托管。",
        ],
        [
            "表达需求",
            weak_labels[0] if weak_labels else "科技表达",
            "表达层真实存在，但当前还不是基础购买逻辑，更像高价值用户的加分项。",
            "保留为高端表达加分项，不要盖过基础能力。",
        ],
        [
            "远期协同",
            "多机协同与统一控制",
            "参考调研有吸引力，但当前更像远期机会层，不该提前透支为本代主卖点。",
            "进入储备池，等底线和托管问题收住后再讲。",
        ],
    ]


def build_self_portfolio_bandwidth_rows(portfolio_generation_strategy: dict[str, object]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in portfolio_generation_strategy.get("portfolio_bandwidth_rows", []) or []:
        series_label = str(row.get("series_family", "-"))
        if series_label == "N":
            series_label = "N（三带）"
        rows.append(
            [
                series_label,
                str(row.get("shape_type", "-")),
                str(row.get("must_carry", "-")),
                str(row.get("must_not_carry", "-")),
                str(row.get("portfolio_gap", "-")),
                str(row.get("why_it_matters", "-")),
            ]
        )
    return rows


def build_priority_rows(strategy_translation: dict[str, object]) -> list[list[str]]:
    reason_lookup = {
        "底线问题": "已经在多个来源里同时出现，并且直接伤害清洁结果或托管信任。",
        "竞争焦点": "行业里已经被反复看见，若不解决，用户会更愿意相信别人能把事做完。",
        "机会点": "对高价值用户有吸引力，但不该替代底线能力。",
        "先不讲满": "当前更像方向或小样本信号，不适合提前当主卖点讲满。",
    }
    action_lookup = {
        "底线问题": "先修，且要在前台主叙事里讲透。",
        "竞争焦点": "同步修，并翻成体验与信任差异。",
        "机会点": "保留为加分项，避免喧宾夺主。",
        "先不讲满": "进入储备池，避免提前透支用户预期。",
    }
    rows: list[list[str]] = []
    for bucket_name, themes in strategy_translation.get("priority_buckets", {}).items():
        rows.append(
            [
                bucket_name,
                "、".join(themes[:4]) if isinstance(themes, list) else "-",
                reason_lookup.get(bucket_name, "当前仍需继续验证。"),
                action_lookup.get(bucket_name, "待补充"),
            ]
        )
    return rows


def build_priority_assignment_rows(portfolio_generation_strategy: dict[str, object]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in portfolio_generation_strategy.get("priority_assignment_rows", []) or []:
        owner_series = str(row.get("owner_series", "-"))
        if owner_series == "N":
            owner_series = "N（三带）"
        rows.append(
            [
                str(row.get("theme_layer", "-")),
                owner_series,
                str(row.get("action_statement", "-")),
                str(row.get("demand_pool_signal", "-")),
                str(row.get("not_for_series", "-")),
            ]
        )
    return rows


def build_roadmap_rows(strategy_translation: dict[str, object], generation_comparison: dict[str, object]) -> list[list[str]]:
    generation_rows = {row["series_code"]: row for row in generation_comparison.get("series_rows", []) or []}
    rows: list[list[str]] = []
    for row in strategy_translation.get("half_year_focus", []) or []:
        phase = str(row.get("phase", "-"))
        focus = "、".join(row.get("focus", [])[:3]) if isinstance(row.get("focus"), list) else "-"
        if phase == "当前轮次":
            main_story = "X 讲少操心、少返工、真托管；T 讲结果更稳、少返工、少维护。"
            not_now = "多机协作、统一生态、表达型加分项先别抢主叙事。"
        else:
            main_story = "把竞争差异从参数差异继续翻成体验与信任差异。"
            not_now = "仍不提前把远期协同能力讲成当前主卖点。"
        blocker = str(row.get("core_blocker", "-"))
        rows.append([phase, main_story, focus, not_now, blocker])
    return rows


def build_portfolio_roadmap_rows(strategy_translation: dict[str, object], portfolio_generation_strategy: dict[str, object]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in portfolio_generation_strategy.get("roadmap_focus_rows", []) or []:
        rows.append(
            [
                str(row.get("stage", "-")),
                str(row.get("x_message", "-")),
                str(row.get("t_message", "-")),
                str(row.get("n_message", "-")).replace("N ", "N（三带） "),
                str(row.get("not_now", "-")),
                str(row.get("core_blocker", "-")),
            ]
        )
    return rows


def build_generation_comparison(survey_conn: sqlite3.Connection) -> dict[str, object]:
    cleaning_ref = build_wave_snapshot(survey_conn, GENERATION_REFERENCE_WAVES["cleaning_needs"])
    multi_robot_ref = build_wave_snapshot(survey_conn, GENERATION_REFERENCE_WAVES["multi_robot"])
    series_rows: list[dict[str, object]] = []
    for config in GENERATION_COMPARE_CONFIG:
        current = build_wave_snapshot(survey_conn, config["current_wave_name"])
        previous = build_wave_snapshot(survey_conn, config["previous_wave_name"])
        previous_ref = build_wave_snapshot(survey_conn, config["previous_reference_wave_name"]) if config["previous_reference_wave_name"] else {}
        series_rows.append(
            {
                "series_code": config["series_code"],
                "current_spu_id": config["current_spu_id"],
                "previous_spu_id": config["previous_spu_id"],
                "current_wave_name": config["current_wave_name"],
                "previous_wave_name": config["previous_wave_name"],
                "current_sample_count": current.get("sample_count", 0),
                "previous_sample_count": previous.get("sample_count", 0),
                "lead_judgment": build_generation_lead_judgment(config["series_code"], current, previous, cleaning_ref, multi_robot_ref),
                "compare_rows": build_generation_compare_rows(config["series_code"], current, previous, previous_ref, cleaning_ref, multi_robot_ref),
                "strategy_summary": build_generation_strategy_summary(config["series_code"]),
                "strategy_rows": build_generation_strategy_rows(config["series_code"]),
                "reference_wave_names": [cleaning_ref.get("wave_name", "-"), multi_robot_ref.get("wave_name", "-")],
                "previous_reference_wave_name": previous_ref.get("wave_name", ""),
                "representative_quotes": [
                    top_answers_text(current, "purchase_motivation", limit=1),
                    top_answers_text(previous, "usage_journey", limit=1),
                    top_answers_text(multi_robot_ref, "concept_validation", limit=1),
                ],
                "heading": config["heading"],
            }
        )
    return {"series_count": len(series_rows), "series_rows": series_rows}


def load_competition_generation_registry() -> dict[str, object]:
    return read_json(COMPETITION_GENERATION_REGISTRY_PATH)


def summarize_generation_shift(previous_products: list[str], current_products: list[str]) -> str:
    if not previous_products and current_products:
        return "空档进入"
    if previous_products and not current_products:
        return "代际缺失"
    if previous_products and current_products and len(current_products) > len(previous_products):
        return "带宽加宽"
    return "延续迭代"


def competition_meaning(shape_type: str, competition_scope: str, brand: str, is_self_brand: bool) -> str:
    if is_self_brand and competition_scope.startswith("N_"):
        return "这是科沃斯在该形态上的守位或下探带，决定产品带宽是否完整。"
    if competition_scope == "X_omni":
        return "这是 X 所在的 omni 高端/中高端竞争带，决定旗舰叙事真正面对谁。"
    if competition_scope == "T_omni":
        return "这是 T 所在的 omni 主销竞争带，决定结果稳定与托管可信要和谁正面打。"
    if shape_type == "aes":
        return "这是入门带基站竞争带，决定 N 是否能承接下探与守位。"
    if shape_type == "single":
        return "这是低价单机守位带，决定科沃斯是否在单机带失守。"
    return f"{brand} 在该形态上的这一代变化会直接改变竞争带的完整度。"


COMPETITION_SCOPE_ORDER = ["X_omni", "T_omni", "N_omni", "N_aes", "N_single"]
DEMAND_POOL_NO_SOLUTION_STATUSES = {"暂无方案"}
DEMAND_POOL_RESEARCH_STATUSES = {"待方案研究", "待评估", "预研中"}


def competition_scope_rank(scope: str) -> int:
    try:
        return COMPETITION_SCOPE_ORDER.index(scope)
    except ValueError:
        return len(COMPETITION_SCOPE_ORDER)


def format_product_examples(products: list[str], limit: int = 3) -> str:
    cleaned = [str(item).strip() for item in products if str(item).strip() and str(item).strip() != "-"]
    if not cleaned:
        return "-"
    if len(cleaned) <= limit:
        return "、".join(cleaned)
    return "、".join(cleaned[:limit]) + "等"


def competition_scope_focus(scope: str) -> str:
    focus_map = {
        "X_omni": "旗舰 omni 正在从参数升级转向托管承诺和高端吸引力的同步竞争",
        "T_omni": "主销 omni 正在把结果稳定、少返工、少维护讲成真正主战场",
        "N_omni": "omni 下探带正在用更密的带宽承接中高端下探和价格带卡位",
        "N_aes": "AES 正在卷入门带基站承接是否完整、是否有空档",
        "N_single": "单机正在卷预算敏感带的守位和基础带宽完整度",
    }
    return focus_map.get(scope, "当前仍在继续补齐这一竞争带。")


def competition_scope_label(scope: str) -> str:
    labels = {
        "X_omni": "X_omni（旗舰 omni）",
        "T_omni": "T_omni（主销 omni）",
        "N_omni": "N_omni（omni 下探）",
        "N_aes": "N_aes（AES 入门带基站）",
        "N_single": "N_single（低价单机守位）",
    }
    return labels.get(scope, scope)


def competition_scope_implication(scope: str) -> str:
    implication_map = {
        "X_omni": "科沃斯要防的是旗舰叙事被讲成单纯参数升级，而把高端感和托管承诺一起让给竞品。",
        "T_omni": "科沃斯要防的是主销 omni 被别人先讲成“更稳、更省心、更少维护”的那一台。",
        "N_omni": "科沃斯要防的是 omni 下探带缺位后，X/T 被迫替 N 去补价格带和守位任务。",
        "N_aes": "科沃斯要防的是 AES 带宽一旦断档，入门带基站需求会直接被对手吃走。",
        "N_single": "科沃斯要防的是单机守位一旦松动，预算敏感用户会先被别家体系截走。",
    }
    return implication_map.get(scope, "当前仍需继续明确这一竞争带对科沃斯意味着什么。")


def build_analysis_reflection_report(
    competition_voc_xtn_breakdown: dict[str, object],
    competition_voc_market_split: dict[str, object],
    competition_capability_scan: dict[str, object],
    competition_matchup_matrix: dict[str, object],
    competition_strategy_bridge: dict[str, object],
    competition_capture_target_candidates: dict[str, object],
) -> dict[str, object]:
    frontline_rows = competition_voc_xtn_breakdown.get("frontline_scope_rows", []) or []
    market_summary_rows = competition_voc_market_split.get("market_summary_rows", []) or []
    capability_rows = competition_capability_scan.get("rows", []) or []
    matchup_rows = competition_matchup_matrix.get("rows", []) or []
    capture_rows = competition_capture_target_candidates.get("rows", []) or []

    missing_or_external = [
        row
        for row in frontline_rows
        if str(row.get("frontline_mode", "")) in {"external_only", "missing"}
    ]
    guardrail_rows = [row for row in capability_rows if row.get("gap_type") in {"守住", "跟随"}]
    depth_gaps = [
        "当前多数竞争页仍是“顶层判断 + 一张表”，还没有把“为什么是这个结论、为什么不是别的结论”展开成第二层论证。",
        "能力扫描已经能逐项判断，但还没显式上翻成 `高端托管门槛 / 主销结果稳定门槛 / 下探带宽完整度门槛` 三个竞争母题。",
        "核心竞品对阵已能说明‘对谁’，但仍需要更明确回答‘如果讲歪，会把自己带到哪个错误战场’。",
    ]
    breadth_gaps = [
        f"`{competition_scope_label(str(row.get('competition_scope', '-')))} / {row.get('market_scope', '-')}` 当前仍是 `{row.get('frontline_mode', '待补充')}`，广度上还不能讲满。"
        for row in missing_or_external[:6]
    ]
    abstraction_gaps = [
        "当前能说清“哪条带最伤什么问题”，但还没完全上翻成系列级母题：哪些问题决定高端托管可信，哪些问题决定主销默认答案，哪些问题决定下探带宽完整度。",
        "看自己页已经开始接竞争桥接，但还没有把 `X/T/N` 各自的主命题、先别讲什么、哪些必须等补数收成稳定 thesis。",
    ]
    ppt_style_gaps = [
        "当前汇报稿已经比模板报告更像汇报者，但仍保留较多表格填空感，‘为什么不一样’和‘先别讲什么’还不够前置。",
        "顶层结构里仍把 `路线图 / 当前动作` 单列成一章，和 PPT 作者更偏 `缺口 / 风险 / 下一步` 的收口方式还有距离。",
    ]
    overstated_claims = [
        f"`{competition_scope_label(str(row.get('competition_scope', '-')))} / {row.get('market_scope', '-')}` 目前只能讲 `{row.get('status_text', '待补充')}`，不能冒充成科沃斯当前硬结论。"
        for row in missing_or_external[:6]
    ]
    underused_evidence = []
    if guardrail_rows:
        underused_evidence.append("能力扫描里已经能区分 `守住 / 跟随`，但这些证据还没有被翻成更大的竞争母题。")
    if any(str(row.get("priority", "")) == "P0" for row in capture_rows):
        underused_evidence.append("补数工程已经把 P0 对象和缺口市场列清，但正文里还没有把这些缺口变成汇报层的显式边界。")
    rewrite_priority_pages = [
        "行业能力扫描及洞察",
        "核心竞品对阵",
        "中国用户 VOC：X/T/N 分系列展开",
        "海外用户 VOC：X/T/N 分系列展开",
        "竞争结论：X/T/N 现在各自该防什么",
        "科沃斯当前产品带宽与系列分工",
        "X/T/N 分工与承接边界",
    ]
    next_data_moves = [
        f"{row.get('priority', 'P1')}：{competition_scope_label(str(row.get('competition_scope', '-')))} / {row.get('target_market_scope', '-')} -> {row.get('reason', '-')}"
        for row in capture_rows[:5]
    ]
    summary_judgment = (
        "当前最核心的反思是：这份报告已经把 `看竞争 -> 看自己` 主链接上了，但还没有把已有证据完全上翻成母题、 thesis 和更像 PPT 作者的判断节奏。"
    )
    return {
        "summary_judgment": summary_judgment,
        "depth_gaps": depth_gaps,
        "breadth_gaps": breadth_gaps,
        "abstraction_gaps": abstraction_gaps,
        "ppt_style_gaps": ppt_style_gaps,
        "overstated_claims": overstated_claims,
        "underused_evidence": underused_evidence,
        "rewrite_priority_pages": rewrite_priority_pages,
        "next_data_moves": next_data_moves,
        "market_summary_rows": market_summary_rows,
    }


def render_analysis_reflection_report(
    analysis_reflection_report: dict[str, object],
) -> str:
    lines = [
        "# 当前分析反思报告",
        "",
        f"- {analysis_reflection_report.get('summary_judgment', '当前反思仍待补充。')}",
        "",
    ]
    sections = [
        ("depth_gaps", "深度差距"),
        ("breadth_gaps", "广度差距"),
        ("abstraction_gaps", "抽象结论差距"),
        ("ppt_style_gaps", "PPT 汇报感差距"),
        ("overstated_claims", "当前不能讲满的地方"),
        ("underused_evidence", "已存在但还没用足的证据"),
        ("rewrite_priority_pages", "优先重写页面"),
        ("next_data_moves", "下一步补数动作"),
    ]
    for key, heading in sections:
        lines.append(f"## {heading}")
        lines.append("")
        for item in analysis_reflection_report.get(key, []) or []:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_self_strategy_thesis(
    competition_strategy_bridge: dict[str, object],
    portfolio_generation_strategy: dict[str, object],
    analysis_reflection_report: dict[str, object],
) -> dict[str, object]:
    x_core = (
        "X 不是继续堆参数的旗舰位，而是要把高端托管承诺讲成可信答案；一旦 `拖地留痕` 这类问题没收住，高端叙事就会直接塌。"
    )
    t_core = (
        "T 不是高端黑科技战，而是主销 omni 的默认答案之战；重点不是讲更多新能力，而是把结果稳定、少返工、少维护讲成用户默认选项。"
    )
    n_core = (
        "N 不是一个总桶，而是 `omni 下探 / AES 入门带基站 / 单机守位` 三条承接位。当前 `N_omni / N_aes 中国区` 仍有真缺样本，不能继续让 X/T 替它们解释。"
    )
    must_wait = [item for item in (analysis_reflection_report.get("next_data_moves", []) or []) if str(item).startswith("P0")][:4]
    current_can_decide = [
        "X 当前主命题已经可以定：高端托管承诺必须守住。",
        "T 当前主命题已经可以定：主销 omni 必须把结果稳定讲成默认答案。",
        "N 当前可以定：单机守位已经能判断，AES/omni 仍有带宽级补数缺口。",
    ]
    return {
        "x_core_thesis": x_core,
        "t_core_thesis": t_core,
        "n_core_thesis": n_core,
        "what_ecovacs_should_not_do": list(
            dedupe_preserve_order(
                [str(item) for item in portfolio_generation_strategy.get("what_not_to_overload_into_flagship", []) or []]
                + [str(item) for item in portfolio_generation_strategy.get("shape_level_not_now", []) or []]
            )
        )[:6],
        "what_must_wait_for_data": must_wait,
        "what_current_report_can_already_decide": current_can_decide,
    }


def build_self_strategy_thesis_rows(self_strategy_thesis: dict[str, object]) -> list[list[str]]:
    return [
        [
            "X",
            str(self_strategy_thesis.get("x_core_thesis", "-")),
            "不要再把下探守位和远期协同塞回旗舰叙事。",
            "；".join(self_strategy_thesis.get("what_must_wait_for_data", [])[:1]) or "-",
        ],
        [
            "T",
            str(self_strategy_thesis.get("t_core_thesis", "-")),
            "不要把主销 omni 讲成高端黑科技堆料战。",
            "；".join(self_strategy_thesis.get("what_must_wait_for_data", [])[1:2]) or "-",
        ],
        [
            "N",
            str(self_strategy_thesis.get("n_core_thesis", "-")),
            "不要继续让 X/T 代替 `N_omni / N_aes / N_single` 三条带宽说话。",
            "；".join(self_strategy_thesis.get("what_must_wait_for_data", [])[2:4]) or "-",
        ],
    ]


def fetch_user_attention_source_rows(
    conn: sqlite3.Connection,
    candidate_spu_ids: list[str],
) -> list[dict[str, object]]:
    if not candidate_spu_ids:
        return []
    placeholders = ", ".join("?" for _ in candidate_spu_ids)
    rows = conn.execute(
        f"""
        SELECT
            vm.message_uid,
            vm.canonical_spu_id,
            COALESCE(vm.raw_model, '') AS raw_model,
            COALESCE(vm.product_title, '') AS product_title,
            vm.country,
            vm.site_country,
            vm.ecommerce_region,
            vm.platform,
            COALESCE(vm.content_text, '') AS content_text,
            COALESCE(mapped.brand_name_cn, '') AS brand_name_cn,
            COALESCE(mapped.self_competitor_type, '') AS self_competitor_type,
            COALESCE(mapped.tag_name, '') AS tag_name,
            COALESCE(mapped.tag_sentiment, '') AS tag_sentiment,
            COALESCE(mapped.topic_domain_name_cn, '') AS topic_domain_name_cn,
            COALESCE(mapped.topic_group_name_cn, '') AS topic_group_name_cn,
            COALESCE(mapped.is_context_feature, 0) AS is_context_feature,
            COALESCE(mapped.context_bucket_name_cn, '') AS context_bucket_name_cn
        FROM vw_voc_message_tag_mapped mapped
        JOIN voc_message vm ON vm.message_uid = mapped.message_uid
        WHERE vm.canonical_spu_id IN ({placeholders})
        """,
        candidate_spu_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_survey_open_answer_rows(
    conn: sqlite3.Connection,
    survey_rows: list[dict[str, object]] | list[sqlite3.Row],
    *,
    max_rows_per_wave: int = 240,
) -> list[dict[str, object]]:
    normalized_rows = [dict(row) if not isinstance(row, dict) else row for row in survey_rows]
    wave_ids = [str(row["wave_id"]) for row in normalized_rows if str(row.get("wave_id", "")).strip()]
    if not wave_ids:
        return []
    placeholders = ", ".join("?" for _ in wave_ids)
    query = f"""
    WITH ranked_answers AS (
        SELECT
            sw.wave_id,
            sw.wave_name,
            sw.market_scope,
            sw.inferred_spu_id,
            sw.maturity_stage,
            sw.survey_topic,
            qc.question_id,
            COALESCE(qc.question_text, qc.source_column_name, '') AS question_text,
            al.response_identity_id,
            TRIM(al.answer_text) AS answer_text,
            ROW_NUMBER() OVER (
                PARTITION BY sw.wave_id
                ORDER BY LENGTH(TRIM(al.answer_text)) DESC, qc.question_id, al.answer_id
            ) AS rn
        FROM survey_wave sw
        JOIN question_catalog qc
            ON qc.wave_id = sw.wave_id
        JOIN answer_long al
            ON al.question_id = qc.question_id
        WHERE sw.wave_id IN ({placeholders})
          AND al.answer_text IS NOT NULL
          AND TRIM(al.answer_text) != ''
          AND LENGTH(TRIM(al.answer_text)) >= 4
    )
    SELECT
        wave_id,
        wave_name,
        market_scope,
        inferred_spu_id,
        maturity_stage,
        survey_topic,
        question_id,
        question_text,
        response_identity_id,
        answer_text
    FROM ranked_answers
    WHERE rn <= ?
    ORDER BY wave_name, question_id, response_identity_id
    """
    rows = conn.execute(query, [*wave_ids, max_rows_per_wave]).fetchall()
    payload: list[dict[str, object]] = []
    for row in rows:
        row_dict = dict(row)
        row_dict["series_family"] = infer_series_code(row_dict.get("inferred_spu_id"), row_dict.get("wave_name", ""))
        payload.append(row_dict)
    return payload


def build_user_topic_source_index(
    source_rows: list[dict[str, object]],
) -> tuple[
    dict[tuple[str, str, str, str], set[str]],
    dict[tuple[str, str, str, str, str, str], dict[str, object]],
]:
    total_message_lookup: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    topic_message_records: dict[tuple[str, str, str, str, str, str], dict[str, object]] = {}
    message_topic_index: dict[tuple[str, str, str, str, str], list[tuple[str, str, str, str, str, str]]] = defaultdict(list)

    for row in source_rows:
        message_uid = str(row.get("message_uid", ""))
        if not message_uid:
            continue
        series_family = infer_series_code(
            str(row.get("canonical_spu_id", "")),
            f"{row.get('raw_model', '')} {row.get('product_title', '')}",
        )
        if series_family == "unknown":
            continue
        user_band = infer_user_band(series_family, str(row.get("raw_model", "")), str(row.get("product_title", "")))
        market_scope = normalize_voc_market_scope(
            row.get("country"),
            row.get("site_country"),
            row.get("ecommerce_region"),
            row.get("platform"),
        )
        cohort_scopes = [user_cohort_scope(str(row.get("brand_name_cn", "")), str(row.get("self_competitor_type", "")))]
        if str(row.get("self_competitor_type", "")) != "self":
            cohort_scopes.append("竞品池样本")

        for cohort_scope in dedupe_preserve_order(cohort_scopes):
            total_message_lookup[(series_family, user_band, market_scope, cohort_scope)].add(message_uid)
            total_message_lookup[(series_family, user_band, "ALL", cohort_scope)].add(message_uid)
            if int(row.get("is_context_feature", 0)) == 1 and not str(row.get("tag_sentiment", "")).strip():
                continue

            topic_name = classify_user_attention_topic(
                str(row.get("tag_name", "")),
                str(row.get("topic_group_name_cn", "")),
                str(row.get("topic_domain_name_cn", "")),
                str(row.get("context_bucket_name_cn", "")),
            )
            if not topic_name:
                continue
            for effective_market_scope in [market_scope, "ALL"]:
                record_key = (series_family, user_band, effective_market_scope, cohort_scope, topic_name, message_uid)
                record = topic_message_records.setdefault(
                    record_key,
                    {
                        "series_family": series_family,
                        "user_band": user_band,
                        "market_scope": effective_market_scope,
                        "cohort_scope": cohort_scope,
                        "topic_name": topic_name,
                        "message_uid": message_uid,
                        "content_samples": [],
                        "positive_tags": Counter(),
                        "negative_tags": Counter(),
                        "neutral_tags": Counter(),
                        "scene_tags": Counter(),
                        "working_condition_tags": Counter(),
                        "related_item_tags": Counter(),
                        "user_indicator_tags": Counter(),
                    },
                )
                if record_key not in message_topic_index[(series_family, user_band, effective_market_scope, cohort_scope, message_uid)]:
                    message_topic_index[(series_family, user_band, effective_market_scope, cohort_scope, message_uid)].append(record_key)
                tag_name = str(row.get("tag_name", "")).strip()
                tag_sentiment = str(row.get("tag_sentiment", "")).strip()
                content_text = str(row.get("content_text", "")).strip()
                if content_text and content_text not in record["content_samples"]:
                    record["content_samples"].append(content_text)
                if tag_sentiment in {"正面", "正"}:
                    record["positive_tags"][tag_name] += 1
                elif tag_sentiment in {"负面", "负"}:
                    record["negative_tags"][tag_name] += 1
                else:
                    record["neutral_tags"][tag_name] += 1

    for row in source_rows:
        if int(row.get("is_context_feature", 0)) != 1:
            continue
        message_uid = str(row.get("message_uid", ""))
        if not message_uid:
            continue
        series_family = infer_series_code(
            str(row.get("canonical_spu_id", "")),
            f"{row.get('raw_model', '')} {row.get('product_title', '')}",
        )
        if series_family == "unknown":
            continue
        user_band = infer_user_band(series_family, str(row.get("raw_model", "")), str(row.get("product_title", "")))
        market_scope = normalize_voc_market_scope(
            row.get("country"),
            row.get("site_country"),
            row.get("ecommerce_region"),
            row.get("platform"),
        )
        cohort_scopes = [user_cohort_scope(str(row.get("brand_name_cn", "")), str(row.get("self_competitor_type", "")))]
        if str(row.get("self_competitor_type", "")) != "self":
            cohort_scopes.append("竞品池样本")
        tag_name = str(row.get("tag_name", "")).strip()
        bucket_name = str(row.get("context_bucket_name_cn", "")).strip()
        for cohort_scope in dedupe_preserve_order(cohort_scopes):
            for effective_market_scope in [market_scope, "ALL"]:
                for record_key in message_topic_index.get((series_family, user_band, effective_market_scope, cohort_scope, message_uid), []):
                    record = topic_message_records[record_key]
                    if "场景" in bucket_name:
                        record["scene_tags"][tag_name] += 1
                    elif "工况" in bucket_name:
                        record["working_condition_tags"][tag_name] += 1
                    elif "关联物品" in bucket_name:
                        record["related_item_tags"][tag_name] += 1
                    elif "用户指标" in bucket_name:
                        record["user_indicator_tags"][tag_name] += 1

    return total_message_lookup, topic_message_records


def build_topic_attention_matrix(
    source_rows: list[dict[str, object]],
    cleaning_robot_theme_registry: dict[str, object] | None = None,
) -> dict[str, object]:
    registry_lookup = {
        str(row.get("topic_name", "")): row
        for row in (cleaning_robot_theme_registry.get("rows", []) or [])
    } if cleaning_robot_theme_registry else {}
    total_message_lookup, topic_message_records = build_user_topic_source_index(source_rows)
    grouped_records: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for (series_family, user_band, market_scope, cohort_scope, topic_name, _message_uid), record in topic_message_records.items():
        if registry_lookup and not bool(registry_lookup.get(topic_name, {}).get("is_cleaning_robot_relevant", False)):
            continue
        grouped_records[(series_family, user_band, market_scope, cohort_scope, topic_name)].append(record)

    rows: list[dict[str, object]] = []
    for (series_family, user_band, market_scope, cohort_scope, topic_name), records in grouped_records.items():
        mention_count = len(records)
        total_messages = len(total_message_lookup.get((series_family, user_band, market_scope, cohort_scope), set()))
        positive_messages = sum(1 for record in records if record["positive_tags"])
        negative_messages = sum(1 for record in records if record["negative_tags"])
        positive_tag_counter: Counter[str] = Counter()
        negative_tag_counter: Counter[str] = Counter()
        for record in records:
            positive_tag_counter.update(record["positive_tags"])
            negative_tag_counter.update(record["negative_tags"])
        rows.append(
            {
                "topic_name": topic_name,
                "series_family": series_family,
                "user_band": user_band,
                "market_scope": market_scope,
                "cohort_scope": cohort_scope,
                "mention_count": mention_count,
                "mention_rate": round(mention_count / total_messages, 4) if total_messages else 0.0,
                "positive_count": positive_messages,
                "positive_rate": round(positive_messages / mention_count, 4) if mention_count else 0.0,
                "negative_count": negative_messages,
                "negative_rate": round(negative_messages / mention_count, 4) if mention_count else 0.0,
                "net_sentiment_signal": attention_sentiment_signal(positive_messages, negative_messages),
                "representative_positive_tags": [
                    {
                        "tag_name": tag_name,
                        "message_count": count,
                        "message_rate": round(count / positive_messages, 4) if positive_messages else 0.0,
                    }
                    for tag_name, count in positive_tag_counter.most_common(5)
                ],
                "representative_negative_tags": [
                    {
                        "tag_name": tag_name,
                        "message_count": count,
                        "message_rate": round(count / negative_messages, 4) if negative_messages else 0.0,
                    }
                    for tag_name, count in negative_tag_counter.most_common(5)
                ],
            }
        )
    rows.sort(key=lambda row: (row["series_family"], row["user_band"], row["market_scope"] != "中国", -int(row["mention_count"]), str(row["topic_name"]), str(row["cohort_scope"])))

    topic_summary_rows: list[dict[str, object]] = []
    for series_family in ["X", "T", "N"]:
        candidate_rows = [
            row
            for row in rows
            if row["series_family"] == series_family
            and row["cohort_scope"] == "科沃斯样本"
            and row["market_scope"] in {"中国", "ALL", "海外"}
        ]
        best_by_topic: dict[tuple[str, str], dict[str, object]] = {}
        for row in candidate_rows:
            key = (str(row.get("user_band", "")), str(row.get("topic_name", "")))
            current = best_by_topic.get(key)
            if current is None or (
                (current.get("market_scope") != "中国" and row.get("market_scope") == "中国")
                or (
                    current.get("market_scope") == row.get("market_scope")
                    and int(row.get("mention_count", 0)) > int(current.get("mention_count", 0))
                )
            ):
                best_by_topic[key] = row
        topic_summary_rows.extend(best_by_topic.values())

    topic_summary_rows.sort(key=lambda row: (row["series_family"], row["user_band"], row["market_scope"] != "中国", -int(row["mention_count"]), str(row["topic_name"])))

    return {
        "row_count": len(rows),
        "rows": rows,
        "topic_summary_rows": topic_summary_rows,
    }


def build_problem_drilldown_packages(
    source_rows: list[dict[str, object]],
    topic_attention_matrix: dict[str, object],
    case_concept_slots: dict[str, object],
    cleaning_robot_theme_registry: dict[str, object] | None = None,
) -> dict[str, object]:
    registry_lookup = {
        str(row.get("topic_name", "")): row
        for row in (cleaning_robot_theme_registry.get("rows", []) or [])
    } if cleaning_robot_theme_registry else {}
    _total_message_lookup, topic_message_records = build_user_topic_source_index(source_rows)
    attention_rows = topic_attention_matrix.get("rows", []) or []
    grouped_cases: dict[str, list[dict[str, object]]] = defaultdict(list)
    for case in case_concept_slots.get("cases", []) or []:  # type: ignore[index]
        series_family = str(case.get("series_code", infer_series_code(case.get("inferred_spu_id"), case.get("case_title", ""))))
        grouped_cases[series_family].append(case)

    rows: list[dict[str, object]] = []
    for attention_row in attention_rows:
        topic_name = str(attention_row.get("topic_name", ""))
        if registry_lookup and not bool(registry_lookup.get(topic_name, {}).get("is_cleaning_robot_relevant", False)):
            continue
        key_prefix = (
            str(attention_row.get("series_family", "")),
            str(attention_row.get("user_band", "")),
            str(attention_row.get("market_scope", "")),
            str(attention_row.get("cohort_scope", "")),
            topic_name,
        )
        records = [
            record
            for (series_family, user_band, market_scope, cohort_scope, inner_topic_name, _message_uid), record in topic_message_records.items()
            if (series_family, user_band, market_scope, cohort_scope, inner_topic_name) == key_prefix
        ]
        if not records:
            continue

        type_counter: Counter[tuple[str, str]] = Counter()
        scene_counter: Counter[tuple[str, str]] = Counter()
        working_counter: Counter[tuple[str, str]] = Counter()
        for record in records:
            for label, count in record["positive_tags"].items():
                type_counter[(label, "正面")] += count
            for label, count in record["negative_tags"].items():
                type_counter[(label, "负面")] += count
            sentiment_labels = []
            if record["positive_tags"]:
                sentiment_labels.append("正面")
            if record["negative_tags"]:
                sentiment_labels.append("负面")
            if not sentiment_labels:
                sentiment_labels.append("中性")
            for sentiment_label in sentiment_labels:
                for label, count in record["scene_tags"].items():
                    scene_counter[(label, sentiment_label)] += count
                for label, count in record["working_condition_tags"].items():
                    working_counter[(label, sentiment_label)] += count

        mention_count = int(attention_row.get("mention_count", 0))
        type_breakdown = [
            {
                "label": label,
                "sentiment": sentiment_label,
                "message_count": count,
                "message_rate": round(count / mention_count, 4) if mention_count else 0.0,
            }
            for (label, sentiment_label), count in type_counter.most_common(8)
        ]
        scene_breakdown = [
            {
                "label": label,
                "sentiment": sentiment_label,
                "message_count": count,
                "message_rate": round(count / mention_count, 4) if mention_count else 0.0,
            }
            for (label, sentiment_label), count in scene_counter.most_common(8)
        ]
        working_breakdown = [
            {
                "label": label,
                "sentiment": sentiment_label,
                "message_count": count,
                "message_rate": round(count / mention_count, 4) if mention_count else 0.0,
            }
            for (label, sentiment_label), count in working_counter.most_common(8)
        ]

        effect_counter: Counter[str] = Counter()
        series_cases = grouped_cases.get(str(attention_row.get("series_family", "")), [])
        if topic_name in PROBLEM_EFFECT_EXPECTATION_RULES:
            for label, keywords in PROBLEM_EFFECT_EXPECTATION_RULES.get(topic_name, {}).items():
                for case in series_cases:
                    text_blob = " ".join(
                        list(case.get("expected_needs", []) or [])
                        + list(case.get("concept_ideas", []) or [])
                        + list(case.get("core_demand", []) or [])
                        + list(case.get("pain_points", []) or [])
                    )
                    if any(keyword in text_blob for keyword in keywords):
                        effect_counter[label] += 1
        else:
            phrase_counter: Counter[str] = Counter()
            anchor_terms = [topic_name] + [row["label"] for row in type_breakdown[:4]]
            for case in series_cases:
                for text in list(case.get("expected_needs", []) or []) + list(case.get("concept_ideas", []) or []) + list(case.get("core_demand", []) or []):
                    normalized_text = str(text).strip()
                    if not normalized_text:
                        continue
                    if any(term and term in normalized_text for term in anchor_terms):
                        phrase_counter[normalized_text] += 1
            if not phrase_counter:
                for case in series_cases:
                    for text in list(case.get("expected_needs", []) or [])[:2]:
                        normalized_text = str(text).strip()
                        if normalized_text:
                            phrase_counter[normalized_text] += 1
            effect_counter.update({label: count for label, count in phrase_counter.most_common(6)})
        effect_expectation_breakdown = [
            {
                "label": label,
                "message_count": count,
                "message_rate": round(count / len(series_cases), 4) if series_cases else 0.0,
            }
            for label, count in effect_counter.most_common(6)
        ]

        positive_top_types = [row["label"] for row in type_breakdown if row.get("sentiment") == "正面"][:3]
        negative_top_types = [row["label"] for row in type_breakdown if row.get("sentiment") == "负面"][:3]
        positive_top_scenes = [row["label"] for row in scene_breakdown if row.get("sentiment") == "正面"][:3]
        negative_top_scenes = [row["label"] for row in scene_breakdown if row.get("sentiment") == "负面"][:3]
        if not effect_expectation_breakdown:
            reasonableness_judgment = "当前已经能看到问题与场景分布，但用户期待效果仍偏弱，合理性判断需要继续补定性。"
        elif int(attention_row.get("negative_count", 0)) > int(attention_row.get("positive_count", 0)):
            reasonableness_judgment = (
                f"当前负向主要集中在 `{_tree_join(negative_top_types, 2)}` / `{_tree_join(negative_top_scenes, 2)}`，"
                f"用户期待更接近 `{_tree_join([row['label'] for row in effect_expectation_breakdown], 2)}`，整体属于合理底线期待。"
            )
        else:
            reasonableness_judgment = (
                f"当前正向样本已经证明 `{_tree_join(positive_top_types, 2)}` 在 `{_tree_join(positive_top_scenes, 2)}` 场景里可成立，"
                f"用户期待 `{_tree_join([row['label'] for row in effect_expectation_breakdown], 2)}` 更多是可放大的体验优势。"
            )

        axis_sizes = {
            "类型": len(type_breakdown),
            "场景": len(scene_breakdown),
            "工况": len(working_breakdown),
            "效果期待": len(effect_expectation_breakdown),
        }
        axis_priority = TOPIC_DRILLDOWN_AXIS_PRIORITY.get(topic_name, ["类型", "场景", "工况", "效果期待"])
        next_drilldown_axis = next(
            (
                axis_name
                for axis_name in axis_priority
                if axis_sizes.get(axis_name, 0) > 0
            ),
            max(axis_sizes.items(), key=lambda item: item[1])[0] if axis_sizes else "类型",
        )

        rows.append(
            {
                "problem_name": topic_name,
                "template_mode": str(registry_lookup.get(topic_name, {}).get("template_mode", "specialized" if topic_name in PROBLEM_EFFECT_EXPECTATION_RULES else "generic")),
                "registry_theme_family": str(registry_lookup.get(topic_name, {}).get("theme_family", infer_theme_family(topic_name))),
                "series_family": attention_row.get("series_family", ""),
                "user_band": attention_row.get("user_band", attention_row.get("series_family", "")),
                "market_scope": attention_row.get("market_scope", ""),
                "cohort_scope": attention_row.get("cohort_scope", ""),
                "mention_count": mention_count,
                "mention_rate": attention_row.get("mention_rate", 0.0),
                "positive_count": attention_row.get("positive_count", 0),
                "positive_rate": attention_row.get("positive_rate", 0.0),
                "negative_count": attention_row.get("negative_count", 0),
                "negative_rate": attention_row.get("negative_rate", 0.0),
                "type_breakdown": type_breakdown,
                "scene_breakdown": scene_breakdown,
                "working_condition_breakdown": working_breakdown,
                "effect_expectation_breakdown": effect_expectation_breakdown,
                "positive_profile_summary": f"正向样本更多集中在 `{_tree_join(positive_top_types, 2)}` / `{_tree_join(positive_top_scenes, 2)}`。",
                "negative_profile_summary": f"负向样本更多集中在 `{_tree_join(negative_top_types, 2)}` / `{_tree_join(negative_top_scenes, 2)}`。",
                "reasonableness_judgment": reasonableness_judgment,
                "counter_examples": positive_top_types[:2] or ["当前缺少稳定正向对照"],
                "next_drilldown_axis": next_drilldown_axis,
            }
        )
    rows.sort(key=lambda row: (row["series_family"], row.get("user_band", ""), row["market_scope"] != "中国", -int(row["mention_count"]), str(row["problem_name"]), str(row["cohort_scope"])))
    return {
        "row_count": len(rows),
        "rows": rows,
    }


def _accepted_claim_id_set(judgment_acceptance_log: dict[str, object] | None) -> set[str]:
    return {
        str(row.get("claim_id", "")).strip()
        for row in (judgment_acceptance_log or {}).get("rows", []) or []
        if bool(row.get("frontstage_permission")) and str(row.get("claim_id", "")).strip()
    }


def _accepted_theme_reasoning_lookup(
    qual_theme_reasoning_map: dict[str, object] | None,
    judgment_acceptance_log: dict[str, object] | None,
) -> dict[tuple[str, str, str], dict[str, object]]:
    accepted_ids = _accepted_claim_id_set(judgment_acceptance_log)
    lookup: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in (qual_theme_reasoning_map or {}).get("rows", []) or []:
        claim_id = str(row.get("claim_id", "")).strip()
        if claim_id not in accepted_ids:
            continue
        key = (
            str(row.get("series_family", "")),
            str(row.get("user_band", row.get("series_family", ""))),
            str(row.get("theme_name", "")),
        )
        lookup[key] = row
    return lookup


def _accepted_hypothesis_rows(
    cross_source_hypothesis_board: dict[str, object] | None,
    judgment_acceptance_log: dict[str, object] | None,
) -> list[dict[str, object]]:
    accepted_ids = _accepted_claim_id_set(judgment_acceptance_log)
    rows: list[dict[str, object]] = []
    for row in (cross_source_hypothesis_board or {}).get("rows", []) or []:
        if str(row.get("hypothesis_id", "")).strip() in accepted_ids:
            rows.append(row)
    return rows


def build_survey_qual_explanation_map(
    case_concept_slots: dict[str, object],
    survey_segment_comparison: dict[str, object],
    survey_concept_segments: dict[str, object],
    x_positioning_packages: dict[str, object],
    t_jtbd_packages: dict[str, object],
    topic_attention_matrix: dict[str, object],
    problem_drilldown_packages: dict[str, object],
    cleaning_robot_theme_registry: dict[str, object] | None = None,
    qual_evidence_packet: dict[str, object] | None = None,
    qual_case_reasoning_cards: dict[str, object] | None = None,
    qual_theme_reasoning_map: dict[str, object] | None = None,
    judgment_acceptance_log: dict[str, object] | None = None,
) -> dict[str, object]:
    attention_rows = topic_attention_matrix.get("rows", []) or []
    drilldown_rows = problem_drilldown_packages.get("rows", []) or []
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    registry_rows = cleaning_robot_theme_registry.get("rows", []) or [] if cleaning_robot_theme_registry else []
    registry_topics = dedupe_normalized_texts([
        str(row.get("topic_name", ""))
        for row in registry_rows
        if bool(row.get("is_cleaning_robot_relevant"))
    ])
    packet_rows = (qual_evidence_packet or {}).get("packets", []) or []
    theme_packet_lookup = {
        (
            str(packet.get("series_family", "")),
            str(packet.get("user_band", packet.get("series_family", ""))),
            str(packet.get("topic_name", "")),
            str(packet.get("market_scope", "")),
        ): packet
        for packet in packet_rows
        if str(packet.get("reasoning_task_type", "")) == "theme_explain"
    }
    accepted_theme_lookup = _accepted_theme_reasoning_lookup(qual_theme_reasoning_map, judgment_acceptance_log)
    case_reasoning_lookup = {
        str(row.get("case_id", "")): row
        for row in (qual_case_reasoning_cards or {}).get("rows", []) or []
        if str(row.get("case_id", "")).strip()
    }

    def find_accepted_theme_row(series_family: str, user_band: str, topic_name: str) -> dict[str, object] | None:
        return accepted_theme_lookup.get((series_family, user_band, topic_name))

    def accepted_case_rows(theme_row: dict[str, object] | None) -> list[dict[str, object]]:
        if not isinstance(theme_row, dict):
            return []
        return [
            case_reasoning_lookup[case_id]
            for case_id in (theme_row.get("supporting_case_ids", []) or [])
            if case_id in case_reasoning_lookup
        ]

    persona_rows: list[dict[str, object]] = []
    topic_signature_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in drilldown_rows:
        series_family = str(row.get("series_family", ""))
        topic_name = str(row.get("problem_name", ""))
        if topic_name not in registry_topics:
            continue
        terms = [topic_name]
        terms.extend(str(item.get("label", "")) for item in (row.get("type_breakdown", []) or [])[:6])
        terms.extend(str(item.get("label", "")) for item in (row.get("effect_expectation_breakdown", []) or [])[:4])
        topic_signature_map[(series_family, topic_name)] = dedupe_preserve_order([term for term in terms if term])

    def infer_sensitive_topics_from_texts(texts: list[str], series_family: str) -> list[str]:
        blob = " ".join(str(text) for text in texts if str(text).strip())
        signals: list[str] = []
        for topic_name in registry_topics:
            topic_terms = topic_signature_map.get((series_family, topic_name), [topic_name])
            if any(term and term in blob for term in topic_terms):
                signals.append(topic_name)
        if signals:
            return dedupe_normalized_texts(signals)[:4]
        candidate_rows = [
            row
            for row in attention_rows
            if row.get("series_family") == series_family
            and row.get("cohort_scope") == "科沃斯样本"
            and row.get("market_scope") in {"中国", "ALL"}
        ]
        candidate_rows.sort(key=lambda row: (-int(row.get("negative_count", 0)), -int(row.get("mention_count", 0))))
        return [str(row.get("topic_name", "")) for row in candidate_rows[:4]]

    for package in x_positioning_packages.get("packages", []) or []:
        representative_titles = [_user_case_label(user) for user in package.get("representative_users", [])]
        matched_cases = [case for case in cases if case.get("case_title") in representative_titles]
        text_samples = list(package.get("pain_need", []) or []) + list(package.get("attitude_pattern", []) or [])
        sensitive_problems = infer_sensitive_topics_from_texts(text_samples, "X")
        persona_rows.append(
            {
                "segment_or_persona": str(package.get("positioning_name", "X 用户")),
                "series_family": "X",
                "sensitive_problems": dedupe_normalized_texts(sensitive_problems),
                "why_sensitive": _tree_join(package.get("pain_need", []) or package.get("buying_logic", []) or [], 2),
                "failure_definition": _tree_join(package.get("pain_need", []) or [], 1),
                "result_baseline": str(package.get("one_line_definition", "-")),
                "over_expected_cases": [
                    case.get("case_title", "-")
                    for case in matched_cases
                    if any(keyword in " ".join(case.get("expected_needs", []) or []) for keyword in ("完全", "必须", "自动", "立刻", "一点都不能"))
                ][:3],
                "under_expected_cases": [
                    case.get("case_title", "-")
                    for case in matched_cases
                    if any(keyword in " ".join(case.get("cleaning_attitude", []) or []) for keyword in ("80%", "能接受", "差不多"))
                ][:3],
                "evidence_refs": _tree_refs(
                    f"x_positioning_packages:{package.get('positioning_name', '-')}",
                    *representative_titles[:2],
                ),
            }
        )

    t_segment_lookup = survey_segment_comparison.get("segments", []) or []
    for package in t_jtbd_packages.get("packages", []) or []:
        titles = [_user_case_label(user) for user in package.get("representative_users", [])]
        text_samples = list(package.get("typical_scene", []) or []) + [str(package.get("unacceptable_cost", ""))]
        sensitive_problems = infer_sensitive_topics_from_texts(text_samples, "T")
        related_segment = next(
            (
                segment
                for segment in t_segment_lookup
                if infer_series_code(segment.get("inferred_spu_id"), segment.get("wave_name", "")) == "T"
                and any(topic in " ".join(str(item) for item in (segment.get("top_problems", []) or [])) for topic in sensitive_problems)
            ),
            None,
        )
        persona_rows.append(
            {
                "segment_or_persona": str(package.get("jtbd_name", "T 用户")),
                "series_family": "T",
                "sensitive_problems": dedupe_normalized_texts(sensitive_problems),
                "why_sensitive": _tree_join(package.get("typical_scene", []) or [], 2),
                "failure_definition": str(package.get("unacceptable_cost", "-")),
                "result_baseline": str(package.get("result_requirement", "-")),
                "over_expected_cases": titles[:1] if any("完全" in sample or "彻底" in sample for sample in package.get("typical_scene", []) or []) else [],
                "under_expected_cases": titles[:1] if "平衡" in str(package.get("jtbd_name", "")) else [],
                "evidence_refs": _tree_refs(
                    f"t_jtbd_packages:{package.get('jtbd_name', '-')}",
                    f"survey_segment:{related_segment.get('segment_name', '-') if related_segment else '-'}",
                ),
            }
        )

    for segment in survey_concept_segments.get("segments", []) or []:
        series_family = infer_series_code(segment.get("inferred_spu_id"), segment.get("wave_name", ""))
        if series_family not in {"X", "T"}:
            continue
        persona_rows.append(
            {
                "segment_or_persona": str(segment.get("segment_name", "survey_segment")),
                "series_family": series_family,
                "sensitive_problems": dedupe_normalized_texts(
                    infer_sensitive_topics_from_texts(
                        [str(item) for item in (segment.get("top_problems", []) or [])]
                        + [str(item) for item in (segment.get("difference_reason", []) or [])],
                        series_family,
                    )
                ),
                "why_sensitive": _tree_join(segment.get("difference_reason", []) or segment.get("top_motivations", []) or [], 2),
                "failure_definition": _tree_join(
                    segment.get("pain_tolerance_gap", [])
                    if isinstance(segment.get("pain_tolerance_gap"), list)
                    else [segment.get("pain_tolerance_gap", "")],
                    1,
                ),
                "result_baseline": str(segment.get("segment_summary", "-")),
                "over_expected_cases": [],
                "under_expected_cases": [],
                "evidence_refs": _tree_refs(
                    f"survey_concept_segments:{segment.get('segment_name', '-')}",
                    f"wave:{segment.get('wave_name', '-')}",
                ),
            }
        )

    deduped_persona_rows: list[dict[str, object]] = []
    seen_personas: set[tuple[str, str]] = set()
    for row in persona_rows:
        persona_key = (str(row.get("series_family", "")), str(row.get("segment_or_persona", "")))
        if persona_key in seen_personas:
            continue
        seen_personas.add(persona_key)
        deduped_persona_rows.append(row)
    persona_rows = deduped_persona_rows

    topic_rows: list[dict[str, object]] = []
    for topic_name in registry_topics:
        for series_family in ["X", "T"]:
            series_persona_rows = [row for row in persona_rows if row.get("series_family") == series_family]
            high_rows = [row for row in series_persona_rows if topic_name in (row.get("sensitive_problems", []) or [])]
            low_rows = [row for row in series_persona_rows if topic_name not in (row.get("sensitive_problems", []) or [])]
            related_drilldown = next(
                (
                    row
                    for row in drilldown_rows
                    if row.get("problem_name") == topic_name
                    and row.get("series_family") == series_family
                    and row.get("cohort_scope") == "科沃斯样本"
                    and row.get("market_scope") in {"中国", "ALL"}
                ),
                None,
            )
            if not high_rows and not related_drilldown:
                continue
            packet = theme_packet_lookup.get(
                (series_family, series_family, topic_name, str(related_drilldown.get("market_scope", "中国")) if related_drilldown else "中国")
            )
            accepted_theme = find_accepted_theme_row(series_family, series_family, topic_name)
            accepted_cases = accepted_case_rows(accepted_theme)
            why_text = _tree_join(
                [str(row.get("why_sensitive", "")) for row in high_rows if str(row.get("why_sensitive", "")).strip()],
                2,
            )
            if accepted_theme:
                why_text = str(accepted_theme.get("why_it_matters", why_text or "-"))
            elif why_text == "-":
                packet_boundaries = packet.get("scope_boundaries", []) if isinstance(packet, dict) else []
                packet_support = packet.get("supporting_passages", []) if isinstance(packet, dict) else []
                if packet_support:
                    why_text = f"当前该主题已有结构化 evidence packet，可结合定性段落继续解释；边界：{_tree_join(packet_boundaries or ['当前仍偏方向性解释'], 1)}"
                else:
                    why_text = str(related_drilldown.get("reasonableness_judgment", "当前该主题在问卷/定性里证据偏弱，只能给方向性解释。")) if related_drilldown else "当前该主题在问卷/定性里证据偏弱，只能给方向性解释。"

            failure_patterns = dedupe_preserve_order(
                [str(case_row.get("failure_definition", "")) for case_row in accepted_cases if str(case_row.get("failure_definition", "")).strip()]
                + [str(row.get("failure_definition", "")) for row in high_rows if str(row.get("failure_definition", "")).strip()]
            )[:4]
            baseline_patterns = dedupe_preserve_order(
                [
                    str(item)
                    for case_row in accepted_cases
                    for item in (case_row.get("hidden_needs", []) or [])
                    if str(item).strip()
                ]
                + [str(row.get("result_baseline", "")) for row in high_rows if str(row.get("result_baseline", "")).strip()]
            )[:4]
            over_expected_patterns = []
            if related_drilldown:
                over_expected_patterns = [
                    str(item.get("label", ""))
                    for item in (related_drilldown.get("effect_expectation_breakdown", []) or [])[:4]
                    if str(item.get("label", "")).strip()
                ]
            if not over_expected_patterns:
                over_expected_patterns = dedupe_preserve_order(
                    [str(case_title) for row in high_rows for case_title in (row.get("over_expected_cases", []) or []) if str(case_title).strip()]
                )[:4]
            under_expected_patterns = dedupe_preserve_order(
                [str(case_row.get("acceptable_tradeoff", "")) for case_row in accepted_cases if str(case_row.get("acceptable_tradeoff", "")).strip()]
                + [str(case_row.get("compensation_behavior", "")) for case_row in accepted_cases if str(case_row.get("compensation_behavior", "")).strip()]
                + [str(case_title) for row in low_rows for case_title in (row.get("under_expected_cases", []) or []) if str(case_title).strip()]
            )[:4]
            topic_rows.append(
                {
                    "topic_name": topic_name,
                    "series_family": series_family,
                    "user_band": series_family,
                    "market_scope": str(related_drilldown.get("market_scope", "中国")) if related_drilldown else "中国",
                    "high_sensitivity_personas": [str(row.get("segment_or_persona", "-")) for row in high_rows[:4]],
                    "low_sensitivity_personas": [str(row.get("segment_or_persona", "-")) for row in low_rows[:4]],
                    "why_this_topic_is_sensitive": why_text,
                    "failure_definition_patterns": failure_patterns or ([str(related_drilldown.get("negative_profile_summary", "当前证据偏弱"))] if related_drilldown else ["当前证据偏弱"]),
                    "result_baseline_patterns": baseline_patterns or ([str(related_drilldown.get("positive_profile_summary", "当前只能给方向性解释"))] if related_drilldown else ["当前只能给方向性解释"]),
                    "over_expected_patterns": over_expected_patterns,
                    "under_expected_patterns": under_expected_patterns or [str(row.get("segment_or_persona", "-")) for row in low_rows[:2]],
                    "evidence_refs": dedupe_preserve_order(
                        [
                            ref
                            for row in high_rows[:3]
                            for ref in (row.get("evidence_refs", []) or [])[:2]
                        ]
                        + [f"accepted_theme_reasoning:{accepted_theme.get('claim_id')}" for _ in [0] if accepted_theme]
                    )[:6] or ([f"problem_drilldown_packages:{topic_name}"] if related_drilldown else []),
                    "evidence_status": "stable" if accepted_theme or high_rows else "weak",
                    "explanation_mode": "accepted_reasoning" if accepted_theme else "persona_backed",
                    "qual_packet_refs": [f"qual_evidence_packet:{packet.get('packet_id')}"] if isinstance(packet, dict) else [],
                    "not_the_real_issue": str(accepted_theme.get("what_is_not_the_real_issue", "-")) if accepted_theme else "-",
                    "acceptable_tradeoffs": dedupe_preserve_order(
                        [str(case_row.get("acceptable_tradeoff", "")) for case_row in accepted_cases if str(case_row.get("acceptable_tradeoff", "")).strip()]
                    )[:3],
                    "compensation_behaviors": dedupe_preserve_order(
                        [str(case_row.get("compensation_behavior", "")) for case_row in accepted_cases if str(case_row.get("compensation_behavior", "")).strip()]
                    )[:3],
                    "accepted_reasoning_refs": dedupe_preserve_order(
                        [f"theme_reasoning:{accepted_theme.get('claim_id')}"] if accepted_theme else []
                        + [f"case_reasoning:{case_row.get('case_id')}" for case_row in accepted_cases]
                    )[:6],
                }
            )

    for user_band in ["N_single", "N_aes"]:
        related_rows = select_preferred_user_band_rows(
            drilldown_rows,
            series_family="N",
            user_band=user_band,
            item_key="problem_name",
        )
        for row in related_rows:
            topic_name = str(row.get("problem_name", ""))
            if not topic_name:
                continue
            packet = theme_packet_lookup.get(("N", user_band, topic_name, str(row.get("market_scope", "-"))))
            accepted_theme = find_accepted_theme_row("N", user_band, topic_name)
            accepted_cases = accepted_case_rows(accepted_theme)
            topic_rows.append(
                {
                    "topic_name": topic_name,
                    "series_family": "N",
                    "user_band": user_band,
                    "market_scope": str(row.get("market_scope", "-")),
                    "high_sensitivity_personas": [],
                    "low_sensitivity_personas": [],
                    "why_this_topic_is_sensitive": str(accepted_theme.get("why_it_matters", row.get("reasonableness_judgment", "当前只能给带宽级方向性解释。"))) if accepted_theme else str(row.get("reasonableness_judgment", "当前只能给带宽级方向性解释。")),
                    "failure_definition_patterns": dedupe_preserve_order(
                        [str(case_row.get("failure_definition", "")) for case_row in accepted_cases if str(case_row.get("failure_definition", "")).strip()]
                        + [str(row.get("negative_profile_summary", "当前证据偏弱"))]
                    )[:4],
                    "result_baseline_patterns": dedupe_preserve_order(
                        [str(item) for case_row in accepted_cases for item in (case_row.get("hidden_needs", []) or []) if str(item).strip()]
                        + [str(row.get("positive_profile_summary", "当前只能给方向性解释"))]
                    )[:4],
                    "over_expected_patterns": [
                        str(item.get("label", ""))
                        for item in (row.get("effect_expectation_breakdown", []) or [])[:4]
                        if str(item.get("label", "")).strip()
                    ],
                    "under_expected_patterns": dedupe_preserve_order(
                        [str(case_row.get("acceptable_tradeoff", "")) for case_row in accepted_cases if str(case_row.get("acceptable_tradeoff", "")).strip()]
                        + [str(item) for item in (row.get("counter_examples", []) or [])[:2] if str(item).strip()]
                    )[:4],
                    "evidence_refs": _tree_refs(
                        f"problem_drilldown_packages:{topic_name}",
                        f"user_band:{user_band}",
                        f"market:{row.get('market_scope', '-')}",
                        *( [f"accepted_theme_reasoning:{accepted_theme.get('claim_id')}"] if accepted_theme else [] ),
                    ),
                    "evidence_status": "voc_only",
                    "explanation_mode": "voc_only",
                    "qual_packet_refs": [f"qual_evidence_packet:{packet.get('packet_id')}"] if isinstance(packet, dict) else [],
                    "not_the_real_issue": str(accepted_theme.get("what_is_not_the_real_issue", "-")) if accepted_theme else "-",
                    "acceptable_tradeoffs": dedupe_preserve_order(
                        [str(case_row.get("acceptable_tradeoff", "")) for case_row in accepted_cases if str(case_row.get("acceptable_tradeoff", "")).strip()]
                    )[:3],
                    "compensation_behaviors": dedupe_preserve_order(
                        [str(case_row.get("compensation_behavior", "")) for case_row in accepted_cases if str(case_row.get("compensation_behavior", "")).strip()]
                    )[:3],
                    "accepted_reasoning_refs": dedupe_preserve_order(
                        [f"theme_reasoning:{accepted_theme.get('claim_id')}"] if accepted_theme else []
                        + [f"case_reasoning:{case_row.get('case_id')}" for case_row in accepted_cases]
                    )[:6],
                }
            )

    topic_rows.append(
        {
            "topic_name": "N_omni",
            "series_family": "N",
            "user_band": "N_omni",
            "market_scope": "中国/ALL",
            "high_sensitivity_personas": [],
            "low_sensitivity_personas": [],
            "why_this_topic_is_sensitive": "当前 `N_omni` 仍缺稳定自家 VOC 样本，因此解释层只能先保留边界与补数方向。",
            "failure_definition_patterns": ["当前缺稳定自家 VOC 样本，不能正式定义失败模式。"],
            "result_baseline_patterns": ["当前暂无可稳定复用的自家结果底线样本。"],
            "over_expected_patterns": [],
            "under_expected_patterns": ["优先补 T50 OMNI / T50S OMNI / 帕斯卡 等真实用户入口。"],
            "evidence_refs": _tree_refs("competition_voc_xtn_breakdown:N_omni", "competition_data_gap_diagnosis:N_omni"),
            "evidence_status": "boundary",
            "explanation_mode": "boundary",
            "qual_packet_refs": [],
            "not_the_real_issue": "-",
            "acceptable_tradeoffs": [],
            "compensation_behaviors": [],
            "accepted_reasoning_refs": [],
        }
    )

    return {
        "row_count": len(persona_rows),
        "rows": persona_rows,
        "topic_rows": topic_rows,
    }


def build_user_thesis_tree(
    user_strategy_convergence_tree: dict[str, object],
    topic_attention_matrix: dict[str, object],
    problem_drilldown_packages: dict[str, object],
    qual_evidence_packet: dict[str, object] | None = None,
    qual_theme_reasoning_map: dict[str, object] | None = None,
    cross_source_hypothesis_board: dict[str, object] | None = None,
    judgment_acceptance_log: dict[str, object] | None = None,
) -> dict[str, object]:
    attention_rows = topic_attention_matrix.get("rows", []) or []
    drilldown_rows = problem_drilldown_packages.get("rows", []) or []
    not_ready_nodes = user_strategy_convergence_tree.get("not_ready_nodes", []) or []
    accepted_theme_lookup = _accepted_theme_reasoning_lookup(qual_theme_reasoning_map, judgment_acceptance_log)
    accepted_hypotheses = _accepted_hypothesis_rows(cross_source_hypothesis_board, judgment_acceptance_log)
    accepted_hypothesis_lookup = {
        (
            str(row.get("series_family", "")),
            str(row.get("user_band", row.get("series_family", ""))),
        ): row
        for row in accepted_hypotheses
    }

    def preferred_rows(series_family: str, user_band: str | None = None) -> list[dict[str, object]]:
        filtered = [
            row
            for row in attention_rows
            if row.get("series_family") == series_family
            and (user_band is None or row.get("user_band") == user_band)
            and row.get("cohort_scope") == "科沃斯样本"
            and row.get("market_scope") in {"中国", "ALL", "海外"}
        ]
        preferred: dict[str, dict[str, object]] = {}
        for row in filtered:
            topic_name = str(row.get("topic_name", ""))
            current = preferred.get(topic_name)
            if current is None or (
                (current.get("market_scope") != "中国" and row.get("market_scope") == "中国")
                or (
                    current.get("market_scope") == row.get("market_scope")
                    and int(row.get("mention_count", 0)) > int(current.get("mention_count", 0))
                )
            ):
                preferred[topic_name] = row
        return list(preferred.values())

    def top_rows(series_family: str, *, negative: bool, user_band: str | None = None) -> list[dict[str, object]]:
        filtered = preferred_rows(series_family, user_band)
        if negative:
            negative_first = [row for row in filtered if int(row.get("negative_count", 0)) > int(row.get("positive_count", 0))]
            if negative_first:
                filtered = negative_first
        else:
            positive_first = [row for row in filtered if int(row.get("positive_count", 0)) >= int(row.get("negative_count", 0))]
            if positive_first:
                filtered = positive_first
        filtered.sort(
            key=lambda row: (
                -(int(row.get("negative_count", 0)) if negative else int(row.get("positive_count", 0))),
                -int(row.get("mention_count", 0)),
                str(row.get("topic_name", "")),
            )
        )
        return filtered[:3]

    def accepted_hypothesis_for(series_family: str, user_band: str) -> dict[str, object] | None:
        return accepted_hypothesis_lookup.get((series_family, user_band))

    def accepted_theme_rows_for(series_family: str, user_band: str) -> list[dict[str, object]]:
        return [
            row
            for key, row in accepted_theme_lookup.items()
            if key[0] == series_family and key[1] == user_band
        ]

    def theme_mechanism(series_family: str, user_band: str) -> str:
        hypothesis = accepted_hypothesis_for(series_family, user_band)
        if hypothesis:
            return str(hypothesis.get("why_accepted_or_rejected", ""))
        theme_rows = accepted_theme_rows_for(series_family, user_band)
        if theme_rows:
            return "；".join(str(row.get("why_it_matters", "")) for row in theme_rows[:2] if str(row.get("why_it_matters", "")).strip())
        return ""

    x_negative = top_rows("X", negative=True)
    x_positive = top_rows("X", negative=False)
    t_negative = top_rows("T", negative=True)
    t_positive = top_rows("T", negative=False)
    n_negative = top_rows("N", negative=True)
    n_positive = top_rows("N", negative=False)
    n_single_negative = top_rows("N", negative=True, user_band="N_single") or top_rows("N", negative=True)
    n_single_positive = top_rows("N", negative=False, user_band="N_single") or top_rows("N", negative=False)
    n_aes_negative = top_rows("N", negative=True, user_band="N_aes")
    n_aes_positive = top_rows("N", negative=False, user_band="N_aes")

    x_core = (
        f"X 当前用户主命题不是继续堆旗舰标签，而是把 `{_tree_join([row.get('topic_name', '-') for row in x_negative], 2)}` 这类底线问题收住，"
        f"同时把 `{_tree_join([row.get('topic_name', '-') for row in x_positive], 2)}` 讲成可被感知的高端托管优势。"
    )
    x_mechanism = theme_mechanism("X", "X")
    if x_mechanism:
        x_core = f"{x_core} 机制上，{x_mechanism}"

    t_core = (
        f"T 当前用户主命题不是讲更炫的新能力，而是围绕 `{_tree_join([row.get('topic_name', '-') for row in t_negative], 2)}` 这类稳定焦虑，"
        f"把 `{_tree_join([row.get('topic_name', '-') for row in t_positive], 2)}` 讲成主销默认答案。"
    )
    t_mechanism = theme_mechanism("T", "T")
    if t_mechanism:
        t_core = f"{t_core} 机制上，{t_mechanism}"

    n_core = (
        f"N 当前用户主命题不是先讲完整人格，而是先把 `{_tree_join([row.get('topic_name', '-') for row in n_negative], 2)}` 这类守位/下探风险看清楚，"
        f"并把 `{_tree_join([row.get('topic_name', '-') for row in n_positive], 2)}` 这类已被用户正向感知的基础优势与 `VOC-only` 边界同时讲清。"
    )
    n_mechanism = theme_mechanism("N", "N_single") or theme_mechanism("N", "N_aes")
    if n_mechanism:
        n_core = f"{n_core} 机制上，{n_mechanism}"

    n_band_theses = {
        "N_single": f"N_single 当前更像预算守位带，重点守 `{_tree_join([row.get('topic_name', '-') for row in n_single_negative], 2)}` 这类底线问题，同时把 `{_tree_join([row.get('topic_name', '-') for row in n_single_positive], 2)}` 讲成基础优势。",
        "N_aes": f"N_aes 当前已能在 VOC 上看见 `{_tree_join([row.get('topic_name', '-') for row in n_aes_negative], 2)}` 的风险和 `{_tree_join([row.get('topic_name', '-') for row in n_aes_positive], 2)}` 的正向信号，但当前仍主要停在海外/ALL 口径。",
        "N_omni": "N_omni 当前仍缺稳定自家 VOC 用户样本，用户链只能先保留为边界判断，不伪造完整主题画像。",
    }
    for band in ["N_single", "N_aes"]:
        band_mechanism = theme_mechanism("N", band)
        if band_mechanism:
            n_band_theses[band] = f"{n_band_theses[band]} 机制上，{band_mechanism}"

    winning_on = [
        f"{row.get('series_family', '-')}: {row.get('topic_name', '-')}"
        for row in [*preferred_rows("X"), *preferred_rows("T"), *preferred_rows("N")]
        if row.get("cohort_scope") == "科沃斯样本"
        and float(row.get("positive_rate", 0.0)) >= float(row.get("negative_rate", 0.0))
        and int(row.get("positive_count", 0)) > 0
    ][:6]
    losing_on = [
        f"{row.get('series_family', '-')}: {row.get('topic_name', '-')}"
        for row in [*preferred_rows("X"), *preferred_rows("T"), *preferred_rows("N")]
        if row.get("cohort_scope") == "科沃斯样本"
        and int(row.get("negative_count", 0)) > int(row.get("positive_count", 0))
    ][:6]
    care_rows = []
    for series_family in ["X", "T", "N"]:
        series_rows = sorted(
            preferred_rows(series_family),
            key=lambda row: (-int(row.get("mention_count", 0)), str(row.get("topic_name", ""))),
        )
        care_rows.extend(series_rows[:3])
    what_users_care_most = [
        f"{row.get('series_family', '-')}: {row.get('topic_name', '-')}{int(row.get('mention_count', 0))}例/{float(row.get('mention_rate', 0.0)):.1%}"
        for row in care_rows[:6]
    ]
    must_wait_for_data = [
        str(node.get("lead_judgment", node.get("summary", "待补充")))
        for node in not_ready_nodes[:4]
    ]
    should_not_be_overstated = [
        f"{row.get('problem_name', '-')}：{row.get('reasonableness_judgment', '-')}"
        for row in drilldown_rows
        if row.get("cohort_scope") == "科沃斯样本"
        and row.get("series_family") in {"X", "T"}
        and not row.get("effect_expectation_breakdown")
    ][:4]
    packet_boundaries = dedupe_preserve_order(
        [
            str(boundary)
            for packet in ((qual_evidence_packet or {}).get("packets", []) or [])
            for boundary in (packet.get("scope_boundaries", []) or [])[:1]
            if str(packet.get("reasoning_task_type", "")) == "cross_source_claim"
            and str(boundary).strip()
        ]
    )[:4]
    non_accepted_boundaries = dedupe_preserve_order(
        [
            str(row.get("why_accepted_or_rejected", ""))
            for row in (cross_source_hypothesis_board or {}).get("rows", []) or []
            if str(row.get("resolution_status", "")) in {"contested", "not_ready", "rejected"}
            and str(row.get("why_accepted_or_rejected", "")).strip()
        ]
    )[:4]
    should_not_be_overstated = dedupe_preserve_order(should_not_be_overstated + packet_boundaries + non_accepted_boundaries)[:8]

    mechanism_explanations = dedupe_preserve_order(
        [
            f"X：{x_mechanism}",
            f"T：{t_mechanism}",
            f"N_single：{theme_mechanism('N', 'N_single')}",
            f"N_aes：{theme_mechanism('N', 'N_aes')}",
        ]
    )
    mechanism_explanations = [item for item in mechanism_explanations if item.split("：", 1)[-1].strip()]
    counter_boundaries = dedupe_preserve_order(packet_boundaries + non_accepted_boundaries)[:6]
    accepted_claim_refs = dedupe_preserve_order(
        [f"hypothesis:{row.get('hypothesis_id')}" for row in accepted_hypotheses]
        + [f"theme_reasoning:{row.get('claim_id')}" for row in accepted_theme_lookup.values()]
    )[:12]

    return {
        "tree_type": "thesis_tree",
        "tree_name": "user_thesis_tree",
        "x_core_thesis": x_core,
        "t_core_thesis": t_core,
        "n_core_thesis": n_core,
        "n_band_theses": n_band_theses,
        "what_users_care_most": what_users_care_most,
        "what_ecovacs_is_winning_on": winning_on,
        "what_ecovacs_is_losing_on": losing_on,
        "what_must_wait_for_data": must_wait_for_data,
        "what_should_not_be_overstated": should_not_be_overstated,
        "mechanism_explanations": mechanism_explanations,
        "counter_boundaries": counter_boundaries,
        "accepted_claim_refs": accepted_claim_refs,
    }


def _tree_signal_strength_from_count(count: int) -> str:
    if count >= 4:
        return "高"
    if count >= 2:
        return "中"
    if count >= 1:
        return "低"
    return "无"


def _tree_signal_strength_from_label(label: object, fallback_count: int = 0) -> str:
    text = str(label or "").strip()
    if text in {"高", "中", "低", "无"}:
        return text
    mapping = {
        "high": "高",
        "medium": "中",
        "low": "低",
        "none": "无",
    }
    lowered = text.lower()
    if lowered in mapping:
        return mapping[lowered]
    return _tree_signal_strength_from_count(fallback_count)


def _tree_node(
    *,
    node_id: str,
    node_label: str,
    summary: str,
    signal_strength: str,
    is_weak_signal: bool,
    why_not_promoted: str,
    evidence_refs: list[str],
    node_type: str,
    children: list[dict[str, object]] | None = None,
    **extra: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "node_id": node_id,
        "node_label": node_label,
        "node_type": node_type,
        "summary": summary,
        "signal_strength": signal_strength,
        "is_weak_signal": is_weak_signal,
        "why_not_promoted": why_not_promoted,
        "evidence_refs": dedupe_preserve_order([ref for ref in evidence_refs if ref]),
        "children": children or [],
    }
    payload.update(extra)
    return payload


def _tree_refs(*values: object) -> list[str]:
    refs: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            refs.append(text)
    return dedupe_preserve_order(refs)


def _tree_join(values: list[object], limit: int = 3) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return "；".join(cleaned[:limit]) if cleaned else "-"


def dedupe_normalized_texts(values: list[object]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value).strip()
        normalized = normalize_text_local(text)
        if not text or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(text)
    return ordered


def _user_case_label(user: object) -> str:
    if isinstance(user, dict):
        return str(user.get("case_title", user.get("persona_summary", "-")))
    text = str(user).strip()
    return text or "-"


def select_preferred_user_band_rows(
    rows: list[dict[str, object]],
    *,
    series_family: str,
    user_band: str,
    item_key: str,
    allowed_markets: list[str] | None = None,
) -> list[dict[str, object]]:
    market_priority = list(allowed_markets or N_USER_BAND_MARKET_PRIORITY.get(user_band, ["中国", "ALL", "海外"]))
    priority_lookup = {market_scope: index for index, market_scope in enumerate(market_priority)}
    filtered = [
        row
        for row in rows
        if row.get("series_family") == series_family
        and row.get("cohort_scope") == "科沃斯样本"
        and row.get("user_band") == user_band
        and row.get("market_scope") in priority_lookup
    ]
    preferred: dict[str, dict[str, object]] = {}
    for row in filtered:
        item_value = str(row.get(item_key, "")).strip()
        if not item_value:
            continue
        current = preferred.get(item_value)
        current_priority = priority_lookup.get(str(current.get("market_scope", "")), 99) if current else 99
        candidate_priority = priority_lookup.get(str(row.get("market_scope", "")), 99)
        if current is None or (
            candidate_priority < current_priority
            or (
                candidate_priority == current_priority
                and int(row.get("mention_count", 0)) > int(current.get("mention_count", 0))
            )
        ):
            preferred[item_value] = row
    return sorted(
        preferred.values(),
        key=lambda row: (
            priority_lookup.get(str(row.get("market_scope", "")), 99),
            -int(row.get("negative_count", 0)),
            -int(row.get("mention_count", 0)),
            str(row.get(item_key, "")),
        ),
    )


def build_entry_exposure_tree(
    result: dict[str, object],
    competition_capture_target_candidates: dict[str, object],
    competition_voc_xtn_breakdown: dict[str, object],
) -> dict[str, object]:
    selected_spus = result.get("selected_spus", []) or []
    support_matrix = result.get("support_matrix", []) or []
    capture_rows = competition_capture_target_candidates.get("rows", []) or []
    scope_status_rows = competition_voc_xtn_breakdown.get("scope_status_rows", []) or []

    stable_entry_nodes = [
        _tree_node(
            node_id=f"selected_{row.get('spu_id', index)}",
            node_label=str(row.get("spu_name", row.get("spu_id", f"对象{index+1}"))),
            node_type="对象归一节点",
            summary=f"当前已进入正式分析对象：`{row.get('spu_name', row.get('spu_id', '-'))}`。",
            signal_strength="高",
            is_weak_signal=False,
            why_not_promoted="",
            evidence_refs=_tree_refs(
                f"selected_spus:{row.get('spu_id', '-')}",
                f"brand:{row.get('brand_name_cn', '-')}",
                f"type:{row.get('self_competitor_type', '-')}",
            ),
            spu_id=row.get("spu_id", ""),
            brand_name=row.get("brand_name_cn", ""),
        )
        for index, row in enumerate(selected_spus[:8])
    ]
    boundary_nodes = [
        _tree_node(
            node_id=f"support_{row.get('module_code', index)}",
            node_label=str(row.get("module_name_cn", row.get("module_code", f"模块{index+1}"))),
            node_type="边界节点",
            summary=f"当前模块支持度为 `{row.get('support_level', '-')}`，主来源是 `{row.get('primary_source', '-')}`。",
            signal_strength=_tree_signal_strength_from_label(row.get("support_level"), 1 if row.get("support_level") == "支持" else 0),
            is_weak_signal=str(row.get("support_level", "")) != "支持",
            why_not_promoted="" if str(row.get("support_level", "")) == "支持" else "当前该模块不是稳定强支撑，只能保留为边界说明。",
            evidence_refs=_tree_refs(
                f"support_matrix:{row.get('module_code', '-')}",
                f"primary_source:{row.get('primary_source', '-')}",
                f"evidence:{row.get('evidence', '-')}",
            ),
            support_level=row.get("support_level", ""),
        )
        for index, row in enumerate(support_matrix)
        if str(row.get("support_level", "")) != "支持"
    ]
    missing_entry_nodes = [
        _tree_node(
            node_id=str(row.get("capture_id", f"capture_{index}")),
            node_label=f"{competition_scope_label(str(row.get('competition_scope', '-')))} / {row.get('target_market_scope', '-')}",
            node_type="缺样本节点",
            summary=str(row.get("current_status", row.get("reason", "当前入口仍待补齐。"))),
            signal_strength="无",
            is_weak_signal=True,
            why_not_promoted="当前是真缺样本或入口未恢复，不能把它写成稳定判断。",
            evidence_refs=_tree_refs(
                f"competition_capture_target_candidates:{row.get('competition_scope', '-')}",
                f"market:{row.get('target_market_scope', '-')}",
                f"reason:{row.get('reason', '-')}",
            ),
            priority=row.get("priority", ""),
            current_message_count=row.get("current_message_count", 0),
        )
        for index, row in enumerate(capture_rows[:8])
    ]
    weak_signal_nodes = [
        _tree_node(
            node_id=f"scope_gap_{row.get('competition_scope', index)}_{row.get('market_scope', 'ALL')}",
            node_label=f"{competition_scope_label(str(row.get('competition_scope', '-')))} / {row.get('market_scope', '-')}",
            node_type="入口弱信号节点",
            summary=str(row.get("status_text", "当前该竞争带入口信号仍偏弱。")),
            signal_strength="低",
            is_weak_signal=True,
            why_not_promoted="当前只有弱入口或外部入口，不能直接升级为稳定自家判断。",
            evidence_refs=_tree_refs(
                f"scope_status:{row.get('competition_scope', '-')}",
                f"market:{row.get('market_scope', '-')}",
                f"frontline_mode:{row.get('frontline_mode', '-')}",
            ),
            frontline_mode=row.get("frontline_mode", ""),
        )
        for index, row in enumerate(scope_status_rows)
        if str(row.get("frontline_mode", "")) in {"external_only", "missing"}
    ]
    return {
        "tree_type": "exposure_tree",
        "tree_name": "entry_exposure_tree",
        "summary_judgment": "入口归一层先把能进入主链的对象、数据边界和真缺样本入口同时摊开，不在这里提前把缺口讲成判断。",
        "stable_entry_nodes": stable_entry_nodes,
        "weak_signal_nodes": weak_signal_nodes,
        "boundary_nodes": boundary_nodes,
        "missing_entry_nodes": missing_entry_nodes,
    }


def build_user_insight_exposure_tree(
    x_observed_positionings: dict[str, object],
    x_positioning_packages: dict[str, object],
    t_persona_slice_cards: dict[str, object],
    t_difference_matrix: dict[str, object],
    t_jtbd_packages: dict[str, object],
    generation_comparison: dict[str, object],
    *,
    entry_exposure_tree: dict[str, object] | None = None,
    topic_attention_matrix: dict[str, object] | None = None,
    problem_drilldown_packages: dict[str, object] | None = None,
    survey_qual_explanation_map: dict[str, object] | None = None,
) -> dict[str, object]:
    x_packages = x_positioning_packages.get("packages", []) or []
    t_cards = t_persona_slice_cards.get("cards", []) or []
    t_rows = t_difference_matrix.get("rows", []) or []
    t_jtbds = t_jtbd_packages.get("packages", []) or []
    generation_rows = {
        str(row.get("series_code", "")): row
        for row in (generation_comparison.get("series_rows", []) or [])
    }

    x_nodes: list[dict[str, object]] = []
    weak_signal_nodes: list[dict[str, object]] = []
    for package in x_packages:
        support_count = len(package.get("support_case_titles", []) or [])
        node = _tree_node(
            node_id=f"x_{package.get('positioning_name', support_count)}",
            node_label=str(package.get("positioning_name", "X 定位")),
            node_type="弱信号节点" if package.get("positioning_level") == "weak_signal" else "主定位节点",
            summary=str(package.get("one_line_definition", package.get("naming_reason", "当前定位仍待补充。"))),
            signal_strength=_tree_signal_strength_from_count(support_count),
            is_weak_signal=package.get("positioning_level") == "weak_signal",
            why_not_promoted="" if package.get("positioning_level") != "weak_signal" else "当前更像方向性表达信号，还不能与主定位并列。",
            evidence_refs=_tree_refs(
                f"x_positioning_packages:{package.get('positioning_name', '-')}",
                f"canonical_anchor:{package.get('canonical_anchor', '-')}",
                f"representative_users:{_tree_join([_user_case_label(user) for user in package.get('representative_users', [])], 2)}",
            ),
            canonical_anchor=package.get("canonical_anchor", ""),
        )
        x_nodes.append(node)
        if package.get("positioning_level") == "weak_signal":
            weak_signal_nodes.append(node)

    x_representative_users = dedupe_preserve_order(
        [
            _user_case_label(user)
            for package in x_packages
            for user in (package.get("representative_users", []) or [])[:2]
        ]
    )
    x_nodes.append(
        _tree_node(
            node_id="x_representative_users",
            node_label="代表用户节点",
            node_type="代表用户节点",
            summary=f"X 当前代表用户主要落在 `{_tree_join(x_representative_users, 3)}`，说明它已经能长出比较稳定的购买角色。",
            signal_strength=_tree_signal_strength_from_count(len(x_representative_users)),
            is_weak_signal=False,
            why_not_promoted="",
            evidence_refs=_tree_refs(
                "x_positioning_packages:representative_users",
                "x_observed_positionings:representative_cases",
                f"x_observed_positionings_count:{len(x_observed_positionings.get('positionings', []) or [])}",
            ),
        )
    )
    x_generation_row = generation_rows.get("X", {})
    x_nodes.append(
        _tree_node(
            node_id="x_generation_diff",
            node_label="代际差异节点",
            node_type="代际差异节点",
            summary=str(x_generation_row.get("lead_judgment", "X 当前代际差异仍待补充。")),
            signal_strength="中" if x_generation_row else "低",
            is_weak_signal=not bool(x_generation_row),
            why_not_promoted="" if x_generation_row else "当前只能保留为代际边界说明。",
            evidence_refs=_tree_refs("generation_comparison:X"),
        )
    )

    t_nodes: list[dict[str, object]] = []
    role_buckets = Counter(str(card.get("role_bucket", "未分类")) for card in t_cards)
    t_nodes.append(
        _tree_node(
            node_id="t_persona_slices",
            node_label="人群切片节点",
            node_type="人群切片节点",
            summary=f"T 当前先长出的人群切片是 `{_tree_join([f'{bucket}({count})' for bucket, count in role_buckets.items()], 3)}`，说明它更适合先按人生位置拆，而不是先压成一个总 archetype。",
            signal_strength=_tree_signal_strength_from_count(len(t_cards)),
            is_weak_signal=False,
            why_not_promoted="",
            evidence_refs=_tree_refs(
                "t_persona_slice_cards:cards",
                f"cases:{_tree_join([card.get('case_title', '-') for card in t_cards], 3)}",
            ),
        )
    )
    for row in t_rows:
        t_nodes.append(
            _tree_node(
                node_id=f"t_diff_{row.get('dimension', '')}",
                node_label=str(row.get("dimension", "差异维度")),
                node_type="差异维度节点",
                summary=str(row.get("why_different", "当前差异原因仍待补充。")),
                signal_strength=_tree_signal_strength_from_count(len(row.get("contrast_pair", []) or [])),
                is_weak_signal=False,
                why_not_promoted="",
                evidence_refs=_tree_refs(
                    f"t_difference_matrix:{row.get('dimension', '-')}",
                    _tree_join(row.get("contrast_pair", []) or [], 2),
                ),
            )
        )
    for package in t_jtbds:
        support_count = len(package.get("representative_users", []) or [])
        t_nodes.append(
            _tree_node(
                node_id=f"t_jtbd_{package.get('jtbd_name', '')}",
                node_label=str(package.get("jtbd_name", "JTBD")),
                node_type="JTBD 节点",
                summary=f"结果要求：{package.get('result_requirement', '-')}；不能接受：{package.get('unacceptable_cost', '-')}。",
                signal_strength=_tree_signal_strength_from_count(support_count),
                is_weak_signal=False,
                why_not_promoted="",
                evidence_refs=_tree_refs(
                    f"t_jtbd_packages:{package.get('jtbd_name', '-')}",
                    _tree_join([_user_case_label(user) for user in package.get("representative_users", [])], 2),
                ),
            )
        )
    t_generation_row = generation_rows.get("T", {})
    t_nodes.append(
        _tree_node(
            node_id="t_generation_diff",
            node_label="代际差异节点",
            node_type="代际差异节点",
            summary=str(t_generation_row.get("lead_judgment", "T 当前代际差异仍待补充。")),
            signal_strength="中" if t_generation_row else "低",
            is_weak_signal=not bool(t_generation_row),
            why_not_promoted="" if t_generation_row else "当前只能保留为代际边界说明。",
            evidence_refs=_tree_refs("generation_comparison:T"),
        )
    )
    t_weak_placeholder = _tree_node(
        node_id="t_weak_signal_placeholder",
        node_label="弱信号节点",
        node_type="弱信号节点",
        summary="当前 T 还没有稳定到值得单独升级成方向层的弱信号；现在最重要的是先把人生位置与 JTBD 的稳定差异讲透。",
        signal_strength="无",
        is_weak_signal=True,
        why_not_promoted="当前无稳定弱信号，不宜为了补齐结构硬造一个方向。",
        evidence_refs=_tree_refs("t_persona_slice_cards", "t_difference_matrix", "t_jtbd_packages"),
    )
    weak_signal_nodes.append(t_weak_placeholder)
    t_nodes.append(t_weak_placeholder)

    topic_attention_matrix = topic_attention_matrix or {}
    problem_drilldown_packages = problem_drilldown_packages or {}
    survey_qual_explanation_map = survey_qual_explanation_map or {}
    entry_exposure_tree = entry_exposure_tree or {}
    stable_nodes = [
        _tree_node(
            node_id=f"attention_{index}",
            node_label=f"{row.get('series_family', '-')} / {row.get('topic_name', '-')}",
            node_type="关注点节点",
            summary=f"{row.get('cohort_scope', '-')} 当前提及 `{row.get('topic_name', '-')}` {int(row.get('mention_count', 0))}例，提及率 {float(row.get('mention_rate', 0.0)):.1%}，{row.get('net_sentiment_signal', '待观察')}。",
            signal_strength=_tree_signal_strength_from_count(int(row.get("mention_count", 0)) // 50 + 1),
            is_weak_signal=False,
            why_not_promoted="",
            evidence_refs=_tree_refs(
                f"topic_attention_matrix:{row.get('topic_name', '-')}",
                f"cohort:{row.get('cohort_scope', '-')}",
            ),
        )
        for index, row in enumerate(
            [
                row
                for row in (topic_attention_matrix.get("topic_summary_rows", []) or [])
                if row.get("cohort_scope") == "科沃斯样本"
            ][:6]
        )
    ]
    drilldown_candidate_nodes = [
        _tree_node(
            node_id=f"drilldown_{index}",
            node_label=f"{row.get('series_family', '-')} / {row.get('problem_name', '-')}",
            node_type="下钻候选节点",
            summary=f"{row.get('problem_name', '-')} 当前最值得继续沿 `{row.get('next_drilldown_axis', '-')}` 下钻；负向画像：{row.get('negative_profile_summary', '-')}",
            signal_strength=_tree_signal_strength_from_count(int(row.get("mention_count", 0)) // 50 + 1),
            is_weak_signal=False,
            why_not_promoted="",
            evidence_refs=_tree_refs(
                f"problem_drilldown_packages:{row.get('problem_name', '-')}",
                f"cohort:{row.get('cohort_scope', '-')}",
            ),
        )
        for index, row in enumerate(
            [
                row
                for row in (problem_drilldown_packages.get("rows", []) or [])
                if row.get("cohort_scope") == "科沃斯样本"
                and row.get("market_scope") in {"中国", "ALL"}
            ][:6]
        )
    ]
    stable_nodes.extend(
        [
            _tree_node(
                node_id=f"explain_{index}",
                node_label=str(row.get("segment_or_persona", f"解释节点{index+1}")),
                node_type="解释节点",
                summary=f"更敏感的问题是 `{_tree_join(row.get('sensitive_problems', []) or [], 2)}`；失败定义：{row.get('failure_definition', '-')}",
                signal_strength="中",
                is_weak_signal=False,
                why_not_promoted="",
                evidence_refs=list(row.get("evidence_refs", []) or [])[:2],
            )
            for index, row in enumerate((survey_qual_explanation_map.get("rows", []) or [])[:6])
        ]
    )
    n_topic_summary_rows = topic_attention_matrix.get("topic_summary_rows", []) or []
    n_single_rows = select_preferred_user_band_rows(
        n_topic_summary_rows,
        series_family="N",
        user_band="N_single",
        item_key="topic_name",
    )
    n_aes_rows = select_preferred_user_band_rows(
        n_topic_summary_rows,
        series_family="N",
        user_band="N_aes",
        item_key="topic_name",
    )
    n_children = []
    if n_single_rows:
        n_children.append(
            _tree_node(
                node_id="n_band_n_single",
                node_label="N_single",
                node_type="VOC 用户带节点",
                summary=(
                    f"N_single 当前主暴露先落在 `{_tree_join([row.get('topic_name', '-') for row in n_single_rows], 2)}`，"
                    "中国样本已经能支撑预算守位带判断。"
                ),
                signal_strength="高",
                is_weak_signal=False,
                why_not_promoted="当前仍主要来自 VOC-only 用户反馈，暂无问卷/定性直连补位。",
                evidence_refs=_tree_refs(
                    *[
                        f"topic_attention_matrix:{row.get('topic_name', '-')}/market:{row.get('market_scope', '-')}"
                        for row in n_single_rows[:3]
                    ]
                ),
                user_band="N_single",
                market_scope=_tree_join([row.get("market_scope", "-") for row in n_single_rows[:2]], 2),
            )
        )
    if n_aes_rows:
        n_children.append(
            _tree_node(
                node_id="n_band_n_aes",
                node_label="N_aes",
                node_type="VOC 用户带节点",
                summary=(
                    f"N_aes 当前主暴露先落在 `{_tree_join([row.get('topic_name', '-') for row in n_aes_rows], 2)}`，"
                    "当前稳定信号主要来自海外/ALL，中国区仍缺自家稳定样本。"
                ),
                signal_strength="中",
                is_weak_signal=False,
                why_not_promoted="不能把海外/ALL 的 VOC-only 信号直接偷渡成中国区用户判断。",
                evidence_refs=_tree_refs(
                    *[
                        f"topic_attention_matrix:{row.get('topic_name', '-')}/market:{row.get('market_scope', '-')}"
                        for row in n_aes_rows[:3]
                    ]
                ),
                user_band="N_aes",
                market_scope=_tree_join([row.get("market_scope", "-") for row in n_aes_rows[:2]], 2),
            )
        )
    n_children.append(
        _tree_node(
            node_id="n_band_n_omni",
            node_label="N_omni",
            node_type="边界节点",
            summary="N_omni 当前仍缺稳定自家 VOC 样本，因此用户暴露层只保留边界与补数方向，不做伪主题展开。",
            signal_strength="无",
            is_weak_signal=False,
            why_not_promoted="当前没有稳定自家 VOC 用户样本，不能假装已经长出正式用户带。",
            evidence_refs=_tree_refs("competition_voc_xtn_breakdown:N_omni", "competition_data_gap_diagnosis:N_omni"),
            user_band="N_omni",
            market_scope="中国/ALL",
        )
    )
    boundary_nodes: list[dict[str, object]] = []
    boundary_nodes.extend(
        [
            node
            for node in (entry_exposure_tree.get("boundary_nodes", []) or [])[:4]
            if isinstance(node, dict)
        ]
    )

    return {
        "tree_type": "exposure_tree",
        "tree_name": "user_insight_exposure_tree",
        "summary_judgment": "看用户这一层先不急着把所有信息压成一个根结论，而是先把 X 的角色分化、T 的人生位置与 JTBD 分化，以及 N 的三条带宽边界一起摊开。",
        "stable_nodes": stable_nodes,
        "series_nodes": [
            {
                "series_family": "X",
                "lead_judgment": "X 当前稳定暴露出来的是角色定位分化，而不是单一旗舰人群。",
                "children": x_nodes,
            },
            {
                "series_family": "T",
                "lead_judgment": "T 当前稳定暴露出来的是人群位置与 JTBD 分化，而不是单一 archetype。",
                "children": t_nodes,
            },
            {
                "series_family": "N",
                "lead_judgment": "N 当前已经拆成 `N_single / N_aes / N_omni` 三条带来暴露：单机守位已稳定、AES 承接位已有海外/ALL 信号、omni 下探仍是边界带。",
                "children": n_children,
            },
        ],
        "weak_signal_nodes": weak_signal_nodes,
        "boundary_nodes": [
            _tree_node(
                node_id="user_boundary_rule",
                node_label="暴露层边界",
                node_type="边界节点",
                summary="暴露层允许保留弱信号和空位，但不把它们强行升级成系列主命题。",
                signal_strength="中",
                is_weak_signal=False,
                why_not_promoted="",
                evidence_refs=_tree_refs("user_insight_exposure_tree:boundary_rule"),
            )
        ] + boundary_nodes,
        "drilldown_candidate_nodes": drilldown_candidate_nodes,
    }


def build_user_strategy_convergence_tree(
    user_insight_exposure_tree: dict[str, object],
    series_positioning: dict[str, object],
    x_positioning_packages: dict[str, object],
    t_jtbd_packages: dict[str, object],
) -> dict[str, object]:
    series_rows = {str(row.get("series_code", "")): row for row in (series_positioning.get("series_rows", []) or [])}
    x_packages = x_positioning_packages.get("packages", []) or []
    t_jtbds = t_jtbd_packages.get("packages", []) or []
    weak_nodes = user_insight_exposure_tree.get("weak_signal_nodes", []) or []
    x_main = [package for package in x_packages if package.get("positioning_level") == "main_positioning"]
    x_labels = [str(package.get("positioning_name", "")) for package in x_main]

    converged_nodes = [
        {
            "concept_name": "X 为什么会分成 清洁管家 / 清洁帮手",
            "concept_status": "converged" if len(x_main) >= 2 else "contested",
            "lead_judgment": f"X 现在稳定分成 `{_tree_join(x_labels, 2)}`，因为同样买旗舰，有人要基础代劳，有人要低介入托管。",
            "why_converged": _tree_join(series_rows.get("X", {}).get("difference_reason_clusters", []) or series_rows.get("X", {}).get("proof_points", []) or [], 2),
            "why_not_other": "表达型弱信号已出现，但当前还不足以与两条主定位并列。",
            "evidence_refs": _tree_refs("series_positioning:X", "x_positioning_packages", "user_insight_exposure_tree:X"),
            "promoted_to": "X 系列主定位差异",
        },
        {
            "concept_name": "T 为什么不是一个总 archetype，而是几类 JTBD",
            "concept_status": "converged" if len(t_jtbds) >= 2 else "contested",
            "lead_judgment": "T 现在更像几类 JTBD 的集合，而不是一个总 archetype，因为不同人生位置会把清洁重新定义成替代、分担或保障。",
            "why_converged": _tree_join(series_rows.get("T", {}).get("difference_reason_clusters", []) or series_rows.get("T", {}).get("proof_points", []) or [], 2),
            "why_not_other": "如果先压成一个总人设，就会把 T 的不同清洁意义讲扁。",
            "evidence_refs": _tree_refs("series_positioning:T", "t_jtbd_packages", "user_insight_exposure_tree:T"),
            "promoted_to": "T 系列 JTBD 主命题",
        },
        {
            "concept_name": "N 为什么不能先压成一个总用户 archetype",
            "concept_status": "contested",
            "lead_judgment": "N 当前真正收敛出来的不是一个总 archetype，而是三条带宽分工：`N_single` 负责低价守位，`N_aes` 负责入门带基站承接，`N_omni` 当前仍只能保留为边界带。",
            "why_converged": "N_single 已有中国稳定 VOC，N_aes 已有海外/ALL 稳定 VOC；N_omni 仍缺稳定自家样本，所以当前更适合收成三带宽分工与边界，而不是完整人群解释。",
            "why_not_other": "如果把 N 直接压成一个总 archetype，会把 `单机守位 / AES 入门带基站 / omni 下探` 三条带宽的不同意义讲乱。",
            "evidence_refs": _tree_refs("user_insight_exposure_tree:N", "competition_voc_xtn_breakdown:N"),
            "promoted_to": "N 带宽边界判断",
        },
    ]
    contested_nodes = [
        {
            "concept_name": "哪些用户判断可以稳定上翻到系列主命题",
            "concept_status": "converged",
            "lead_judgment": "当前可以稳定上翻的是 X 的角色分化与 T 的 JTBD 分化；其余内容更适合作为证明层，而不是新的系列主命题。",
            "evidence_refs": _tree_refs("series_positioning", "user_insight_exposure_tree"),
            "promoted_to": "看用户章节 lead",
        }
    ]
    not_ready_nodes = [
        {
            "concept_name": "哪些仍只能保留为方向性信号",
            "concept_status": "not_ready" if weak_nodes else "converged",
            "lead_judgment": _tree_join([node.get("summary", "-") for node in weak_nodes], 2) if weak_nodes else "当前没有额外方向性弱信号需要单独上翻。",
            "evidence_refs": _tree_refs("user_insight_exposure_tree:weak_signal_nodes"),
            "promoted_to": "弱信号页 / 边界说明",
        }
    ]
    return {
        "tree_type": "convergence_tree",
        "tree_name": "user_strategy_convergence_tree",
        "summary_judgment": "看用户往上收敛后，当前最稳定的不是更多人群标签，而是三件事：X 在角色定位上分化，T 在 JTBD 上分化，N 则已经收成 `N_single / N_aes / N_omni` 的三带宽边界分化。",
        "converged_nodes": converged_nodes,
        "contested_nodes": contested_nodes,
        "not_ready_nodes": not_ready_nodes,
    }


def build_voc_fact_exposure_tree(
    voc_problem_packages: dict[str, object],
    competition_voc_xtn_breakdown: dict[str, object],
) -> dict[str, object]:
    packages = voc_problem_packages.get("packages", []) or []
    frontline_rows = competition_voc_xtn_breakdown.get("frontline_scope_rows", []) or []
    scope_status_rows = competition_voc_xtn_breakdown.get("scope_status_rows", []) or []

    signal_nodes = [
        _tree_node(
            node_id=f"voc_package_{index}",
            node_label=str(row.get("package_name", row.get("negative_tag", f"问题包{index+1}"))),
            node_type="稳定问题节点",
            summary=f"{row.get('problem_level_1', '-')}` / `{row.get('problem_level_2', '-')}` 当前已形成稳定问题包，样本量 `{row.get('message_count', 0)}`。",
            signal_strength=_tree_signal_strength_from_count(int(row.get("message_count", 0) >= 30) * 4),
            is_weak_signal=False,
            why_not_promoted="",
            evidence_refs=_tree_refs(
                f"voc_problem_packages:{row.get('negative_tag', '-')}",
                f"scope:{row.get('competition_scope', '-')}",
                f"market:{row.get('market_scope', '-')}",
            ),
            competition_scope=row.get("competition_scope", ""),
            market_scope=row.get("market_scope", ""),
        )
        for index, row in enumerate(sorted(packages, key=lambda item: item.get("message_count", 0), reverse=True))
        if int(row.get("message_count", 0)) >= 30
    ][:8]
    weak_signal_nodes = [
        _tree_node(
            node_id=f"voc_weak_{row.get('competition_scope', index)}_{row.get('market_scope', '-')}",
            node_label=f"{competition_scope_label(str(row.get('competition_scope', '-')))} / {row.get('market_scope', '-')}",
            node_type="弱信号节点",
            summary=(
                f"当前仅有 `{row.get('self_message_count', 0) or row.get('external_message_count', 0)}` 条上下文，仍只能保留为小样本或弱信号。"
                if (row.get("self_message_count", 0) or row.get("external_message_count", 0))
                else "当前该竞争带没有形成可用样本，只能保留为空位。"
            ),
            signal_strength="低",
            is_weak_signal=True,
            why_not_promoted="当前不满足稳定门槛，不能继续写成正式问题项。",
            evidence_refs=_tree_refs(
                f"scope_status:{row.get('competition_scope', '-')}",
                f"market:{row.get('market_scope', '-')}",
                f"frontline_mode:{row.get('frontline_mode', '-')}",
            ),
        )
        for index, row in enumerate(scope_status_rows)
        if (
            str(row.get("frontline_mode", "")) == "missing"
            and ((row.get("self_message_count", 0) or row.get("external_message_count", 0)) > 0)
        )
    ]
    external_only_nodes = [
        _tree_node(
            node_id=f"voc_external_{row.get('competition_scope', index)}_{row.get('market_scope', '-')}",
            node_label=f"{competition_scope_label(str(row.get('competition_scope', '-')))} / {row.get('market_scope', '-')}",
            node_type="外部门槛节点",
            summary=str(row.get("voc_complaint_summary", row.get("status_text", "当前只有外部门槛。"))),
            signal_strength="中",
            is_weak_signal=False,
            why_not_promoted="当前只有竞品池稳定样本，不能把它讲成科沃斯当前最伤。",
            evidence_refs=_tree_refs(
                f"frontline_scope_rows:{row.get('competition_scope', '-')}",
                f"market:{row.get('market_scope', '-')}",
                f"external_problem:{row.get('external_reference_problem_level_2', '-')}",
            ),
            competition_scope=row.get("competition_scope", ""),
            market_scope=row.get("market_scope", ""),
        )
        for index, row in enumerate(frontline_rows)
        if str(row.get("frontline_mode", "")) == "external_only"
    ]
    missing_scope_nodes = [
        _tree_node(
            node_id=f"voc_missing_{row.get('competition_scope', index)}_{row.get('market_scope', '-')}",
            node_label=f"{competition_scope_label(str(row.get('competition_scope', '-')))} / {row.get('market_scope', '-')}",
            node_type="缺口节点",
            summary=str(row.get("status_text", "当前该竞争带稳定 VOC 仍待补齐。")),
            signal_strength="无",
            is_weak_signal=True,
            why_not_promoted="当前是真缺样本，不能用模板文案填平。",
            evidence_refs=_tree_refs(
                f"frontline_scope_rows:{row.get('competition_scope', '-')}",
                f"market:{row.get('market_scope', '-')}",
            ),
        )
        for index, row in enumerate(frontline_rows)
        if str(row.get("frontline_mode", "")) == "missing"
    ]
    return {
        "tree_type": "exposure_tree",
        "tree_name": "voc_fact_exposure_tree",
        "summary_judgment": "VOC 单源事实层不仅要暴露稳定问题，还要把小样本、外部门槛和真缺样本明确成不同节点。",
        "signal_nodes": signal_nodes,
        "weak_signal_nodes": weak_signal_nodes,
        "external_only_nodes": external_only_nodes,
        "missing_scope_nodes": missing_scope_nodes,
    }


def build_cross_source_convergence_tree(
    cross_source_interpretation: dict[str, object],
    series_positioning: dict[str, object],
    strategy_translation: dict[str, object],
    competition_voc_xtn_breakdown: dict[str, object],
) -> dict[str, object]:
    interpretations = cross_source_interpretation.get("interpretations", []) or []
    series_rows = {str(row.get("series_code", "")): row for row in (series_positioning.get("series_rows", []) or [])}
    frontline_rows = competition_voc_xtn_breakdown.get("frontline_scope_rows", []) or []
    missing_scopes = [
        row for row in frontline_rows if str(row.get("frontline_mode", "")) in {"external_only", "missing"}
    ]

    concept_rows = [
        {
            "concept_name": "高端托管可信",
            "concept_status": "converged" if series_rows.get("X") else "contested",
            "lead_judgment": "高端竞争当前不是继续讲更多参数，而是让用户相信‘托管承诺真的不会塌房’。",
            "why_now": _tree_join(series_rows.get("X", {}).get("proof_points", []) or [], 2),
            "evidence_refs": _tree_refs("series_positioning:X", "cross_source_interpretation"),
            "cannot_overstate": "若拖地留痕、维护负担等底线问题没收住，高端托管就会失真。",
        },
        {
            "concept_name": "主销默认答案",
            "concept_status": "converged" if series_rows.get("T") else "contested",
            "lead_judgment": "主销带更像结果稳定与少维护的默认答案之战，而不是高端黑科技之战。",
            "why_now": _tree_join(series_rows.get("T", {}).get("proof_points", []) or [], 2),
            "evidence_refs": _tree_refs("series_positioning:T", "strategy_translation"),
            "cannot_overstate": "如果把主销带讲成高端炫技，会把用户真实判断带偏。",
        },
        {
            "concept_name": "下探带宽完整度",
            "concept_status": "not_ready" if missing_scopes else "converged",
            "lead_judgment": "下探带宽的核心不是多几款产品，而是 omni / aes / 单机 三条带宽能不能各自站住。",
            "why_now": _tree_join(
                [competition_scope_label(str(row.get("competition_scope", "-"))) for row in missing_scopes],
                3,
            ),
            "evidence_refs": _tree_refs("competition_voc_xtn_breakdown:frontline_scope_rows", "strategy_translation"),
            "cannot_overstate": "N_omni / N_aes 中国区当前仍有真缺样本，不能硬讲满。",
        },
        {
            "concept_name": "表达型机会",
            "concept_status": "contested",
            "lead_judgment": "表达型机会已经出现，但当前更像方向层，不能抢走主线叙事。",
            "why_now": _tree_join(strategy_translation.get("not_now", []) or [], 2),
            "evidence_refs": _tree_refs("strategy_translation:not_now", "cross_source_interpretation"),
            "cannot_overstate": "当前还不能把表达型需求直接升级成系列主命题。",
        },
        {
            "concept_name": "必须继续补数的概念",
            "concept_status": "not_ready",
            "lead_judgment": "凡是仍落在 external-only 或 missing 的竞争带，都应该被明确收进补数和边界，而不是让前台替它做判断。",
            "why_now": _tree_join([str(row.get("status_text", "-")) for row in missing_scopes], 2),
            "evidence_refs": _tree_refs("competition_voc_xtn_breakdown:scope_status_rows", "analysis_reflection_report"),
            "cannot_overstate": "缺样本不是写作问题，是真的不能讲满。",
        },
    ]
    return {
        "tree_type": "convergence_tree",
        "tree_name": "cross_source_convergence_tree",
        "summary_judgment": "跨源层开始把下层暴露出来的事实收成有限几个概念：哪些已经收敛，哪些仍冲突，哪些必须明确标成 not ready。",
        "concept_nodes": concept_rows,
        "aligned_interpretations": interpretations[:5],
    }


def build_competition_thesis_tree(
    competition_capability_scan: dict[str, object],
    competition_matchup_matrix: dict[str, object],
    competition_voc_market_split: dict[str, object],
    competition_strategy_bridge: dict[str, object],
) -> dict[str, object]:
    capability_rows = competition_capability_scan.get("rows", []) or []
    matchup_rows = competition_matchup_matrix.get("rows", []) or []
    market_rows = competition_voc_market_split.get("market_rows", []) or []
    thesis_nodes = [
        {
            "thesis_name": "高端托管门槛",
            "root_claim": str(competition_strategy_bridge.get("what_x_must_defend", "X 当前最该防的是高端托管承诺被真实问题打穿。")),
            "why_this_is_the_bar": _tree_join(
                [str(row.get("why_it_matters", "-")) for row in capability_rows if row.get("capability_dimension") in {"机身高度", "拖地体系", "基站自清洁"}],
                2,
            ),
            "scope_refs": ["X_omni"],
            "what_not_to_confuse": "别把高端竞争讲成单纯参数堆料战，真正比的是托管承诺能不能站住。",
            "evidence_refs": _tree_refs("competition_capability_scan", "competition_matchup_matrix:X", "competition_voc_market_split:中国/X"),
        },
        {
            "thesis_name": "主销结果稳定门槛",
            "root_claim": str(competition_strategy_bridge.get("what_t_must_defend", "T 当前最该防的是结果稳定和少维护没有被讲成默认答案。")),
            "why_this_is_the_bar": _tree_join(
                [str(row.get("why_it_matters", "-")) for row in capability_rows if row.get("capability_dimension") in {"免维护", "滚刷 / 边刷防缠", "越障"}],
                2,
            ),
            "scope_refs": ["T_omni"],
            "what_not_to_confuse": "别把主销 omni 带进高端黑科技战，它更像默认答案之战。",
            "evidence_refs": _tree_refs("competition_capability_scan", "competition_matchup_matrix:T", "competition_voc_market_split:中国/T"),
        },
        {
            "thesis_name": "下探带宽完整度门槛",
            "root_claim": str(competition_strategy_bridge.get("what_n_must_defend", "N 当前最该防的是 omni / aes / 单机 三条带宽没有被分开判断。")),
            "why_this_is_the_bar": _tree_join(
                [
                    str(row.get("voc_risk_to_watch", "-"))
                    for row in matchup_rows
                    if str(row.get("series_family", "")) == "N"
                ],
                2,
            ),
            "scope_refs": ["N_omni", "N_aes", "N_single"],
            "what_not_to_confuse": "别把 N 当成一个总桶，更不能让 X/T 替下探带宽补叙事。",
            "evidence_refs": _tree_refs("competition_matchup_matrix:N", "competition_voc_market_split:N", "competition_strategy_bridge"),
        },
    ]
    return {
        "tree_type": "thesis_tree",
        "tree_name": "competition_thesis_tree",
        "summary_judgment": "看竞争这一层先收成三个母题，再把能力、对阵和 VOC 放回这三个母题下面解释。",
        "thesis_nodes": thesis_nodes,
        "market_refs": market_rows[:4],
    }


def build_self_strategy_thesis_tree(
    self_strategy_thesis: dict[str, object],
    portfolio_generation_strategy: dict[str, object],
    cross_source_convergence_tree: dict[str, object],
    competition_capture_target_candidates: dict[str, object],
) -> dict[str, object]:
    capture_rows = competition_capture_target_candidates.get("rows", []) or []
    wait_items = self_strategy_thesis.get("what_must_wait_for_data", []) or []
    thesis_nodes = [
        {
            "series_family": "X",
            "root_claim": str(self_strategy_thesis.get("x_core_thesis", "-")),
            "why_this_is_the_role": "X 当前要承接的是高端托管承诺，而不是替所有带宽兜底。",
            "what_not_to_do": "不要再把下探守位和远期协同压回旗舰。",
            "must_wait_for_data": _tree_join(wait_items[:1], 1),
            "evidence_refs": _tree_refs("self_strategy_thesis:X", "portfolio_generation_strategy:what_x_should_carry"),
        },
        {
            "series_family": "T",
            "root_claim": str(self_strategy_thesis.get("t_core_thesis", "-")),
            "why_this_is_the_role": "T 当前要承接的是主销默认答案，而不是高端炫技。",
            "what_not_to_do": "不要把主销 omni 讲成旗舰黑科技堆料战。",
            "must_wait_for_data": _tree_join(wait_items[1:2], 1),
            "evidence_refs": _tree_refs("self_strategy_thesis:T", "portfolio_generation_strategy:what_t_should_carry"),
        },
        {
            "series_family": "N",
            "root_claim": str(self_strategy_thesis.get("n_core_thesis", "-")),
            "why_this_is_the_role": "N 当前要回答的是三条下探带宽分别由谁承接，而不是继续当一个兜底大桶。",
            "what_not_to_do": "不要继续让 X/T 代替 N 的 omni / aes / 单机 说话。",
            "must_wait_for_data": _tree_join(wait_items[2:4], 2),
            "evidence_refs": _tree_refs("self_strategy_thesis:N", "portfolio_generation_strategy:what_n_should_carry"),
        },
    ]
    return {
        "tree_type": "thesis_tree",
        "tree_name": "self_strategy_thesis_tree",
        "summary_judgment": "看自己这一层才真正做一针见血的 thesis：X 守高端托管，T 守主销默认答案，N 守带宽分工和缺口边界。",
        "thesis_nodes": thesis_nodes,
        "what_ecovacs_should_not_do": list(self_strategy_thesis.get("what_ecovacs_should_not_do", []) or []),
        "what_must_wait_for_data": list(wait_items),
        "what_current_report_can_already_decide": list(self_strategy_thesis.get("what_current_report_can_already_decide", []) or []),
        "cross_source_refs": cross_source_convergence_tree.get("concept_nodes", [])[:3],
        "capture_refs": capture_rows[:3],
    }


def build_master_judgment_tree(
    user_strategy_convergence_tree: dict[str, object],
    competition_thesis_tree: dict[str, object],
    self_strategy_thesis_tree: dict[str, object],
) -> dict[str, object]:
    user_nodes = user_strategy_convergence_tree.get("converged_nodes", []) or []
    competition_nodes = competition_thesis_tree.get("thesis_nodes", []) or []
    self_nodes = self_strategy_thesis_tree.get("thesis_nodes", []) or []
    return {
        "tree_type": "thesis_tree",
        "tree_name": "master_judgment_tree",
        "summary_judgment": "整条链最后要回答的是：用户为什么会这样判断，竞争真正卷什么，以及科沃斯为什么必须按 X/T/N 这样分工。",
        "root_thesis": "用户判断先把系列主命题分开，竞争母题再把外部压力压实，最后才得到 X/T/N 的分工与优先级。",
        "branches": [
            {
                "branch_name": "用户为什么这么判断",
                "lead_judgment": _tree_join([node.get("lead_judgment", "-") for node in user_nodes], 3),
                "evidence_refs": _tree_refs("user_strategy_convergence_tree"),
            },
            {
                "branch_name": "竞争真正卷什么",
                "lead_judgment": _tree_join([node.get("root_claim", "-") for node in competition_nodes], 3),
                "evidence_refs": _tree_refs("competition_thesis_tree"),
            },
            {
                "branch_name": "科沃斯为什么必须这么分工",
                "lead_judgment": _tree_join([node.get("root_claim", "-") for node in self_nodes], 3),
                "evidence_refs": _tree_refs("self_strategy_thesis_tree"),
            },
        ],
    }


def build_presentation_tree(
    user_insight_exposure_tree: dict[str, object],
    user_strategy_convergence_tree: dict[str, object],
    competition_thesis_tree: dict[str, object],
    self_strategy_thesis_tree: dict[str, object],
    analysis_reflection_report: dict[str, object],
) -> dict[str, object]:
    return {
        "tree_type": "presentation_tree",
        "tree_name": "presentation_tree",
        "summary_judgment": "这份汇报会先给最强判断，再区分哪些能讲满、哪些还要补证，最后落到 X/T/N 的分工与下一步。",
        "chapter_nodes": [
            {
                "chapter_heading": "## 0. 问题回答",
                "chapter_purpose": "先给根判断，不把方法和边界抢到最前面。",
                "lead_judgment": "先回答整条链最后收成了什么。",
                "page_sequence": ["master_judgment_tree"],
            },
            {
                "chapter_heading": "## 1. 看用户",
                "chapter_purpose": "先暴露，再收敛。",
                "lead_judgment": str(user_insight_exposure_tree.get("summary_judgment", "-")),
                "page_sequence": ["user_exposure_tree_pages", "x_positioning_*", "t_*", "user_convergence_tree_pages"],
            },
            {
                "chapter_heading": "## 2. 看竞争",
                "chapter_purpose": "先讲竞争母题，再落到能力、对阵和 VOC。",
                "lead_judgment": str(competition_thesis_tree.get("summary_judgment", "-")),
                "page_sequence": ["competition_thesis_pages", "competition_capability_scan_pages", "competition_matchup_pages", "competition_voc_*"],
            },
            {
                "chapter_heading": "## 3. 看自己",
                "chapter_purpose": "只在这一层做系列策略 thesis。",
                "lead_judgment": str(self_strategy_thesis_tree.get("summary_judgment", "-")),
                "page_sequence": ["self_value_pages", "self_portfolio_bandwidth_pages", "self_demand_reorder_pages"],
            },
            {
                "chapter_heading": "## 5. 缺口 / 风险 / 下一步",
                "chapter_purpose": "把真缺样本、反思和补数动作并到同一章收口。",
                "lead_judgment": str(analysis_reflection_report.get("summary_judgment", "-")),
                "page_sequence": ["analysis_reflection_pages", "data_moves_pages", "roadmap_action_pages"],
            },
        ],
    }


def load_mirror_registry() -> list[dict[str, object]]:
    if not MIRROR_REGISTRY_PATH.exists():
        return []
    data = json.loads(MIRROR_REGISTRY_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def resolve_mirror_entry(target_person: str) -> dict[str, object]:
    normalized = normalize_text_local(target_person)
    for entry in load_mirror_registry():
        candidates = [str(entry.get("canonical_name", ""))] + [str(alias) for alias in entry.get("aliases", []) or []]
        if any(normalize_text_local(candidate) == normalized for candidate in candidates):
            return entry
    raise KeyError(f"mirror target not found: {target_person}")


def load_mirror_index(target_person: str) -> dict[str, object]:
    try:
        entry = resolve_mirror_entry(target_person)
    except KeyError:
        return {}
    index_path = MIRROR_VAULT_ROOT / str(entry.get("index_path", ""))
    if not index_path.exists():
        return {}
    return json.loads(index_path.read_text(encoding="utf-8"))


def mirror_has_signal(report_text: str, tokens: tuple[str, ...]) -> bool:
    normalized = normalize_text_local(report_text)
    return any(normalize_text_local(token) in normalized for token in tokens if normalize_text_local(token))


def mirror_veto_trigger(target_person: str, item: str, report_text: str, tokens: tuple[str, ...]) -> bool:
    if target_person == "David" and item == "只谈概念不谈数据":
        has_concept = mirror_has_signal(report_text, ("概念", "框架"))
        has_data = mirror_has_signal(report_text, ("提及率", "占比", "例", "数据", "正评率", "负评率"))
        return has_concept and not has_data
    if target_person == "David" and item == "看不懂的比例图和抽象图表":
        return ("38%" in report_text and "62%" in report_text) or "看不懂" in report_text
    return mirror_has_signal(report_text, tokens)


def build_mirror_review_result(
    *,
    target_person: str,
    material_title: str,
    material_content: str,
) -> dict[str, object]:
    mirror_index = load_mirror_index(target_person)
    signal_map = MIRROR_REVIEW_SIGNAL_MAP.get(target_person, {})
    must_include = signal_map.get("must_include", {})
    must_avoid = signal_map.get("must_avoid", {})
    matched_rules: list[dict[str, object]] = []
    missed_rules: list[dict[str, object]] = []
    veto_hits: list[dict[str, object]] = []
    rewrite_actions: list[dict[str, object]] = []

    for item, tokens in must_include.items():
        if mirror_has_signal(material_content, tokens):
            matched_rules.append({"source": "must_include", "statement": item})
        else:
            missed_rules.append({"source": "must_include", "statement": item})
            rewrite_actions.append(
                {
                    "action_id": f"{normalize_text_local(target_person)}_{normalize_text_local(item)}",
                    "priority": "P0",
                    "target_section": "看用户",
                    "problem_type": "missing_requirement",
                    "instruction": f"补强 `{item}` 对应表达，让报告更像 {target_person} 要的汇报。",
                    "expected_outcome": f"让 `{item}` 在正文中能被一眼读到。",
                    "source_person": target_person,
                    "is_blocking": True,
                }
            )

    for item, tokens in must_avoid.items():
        if mirror_veto_trigger(target_person, item, material_content, tokens):
            veto_hits.append({"source": "must_avoid", "statement": item})
            rewrite_actions.append(
                {
                    "action_id": f"{normalize_text_local(target_person)}_veto_{normalize_text_local(item)}",
                    "priority": "P0",
                    "target_section": "看用户",
                    "problem_type": "veto_hit",
                    "instruction": f"移除或改写 `{item}` 对应的表达方式。",
                    "expected_outcome": f"避免继续触发 {target_person} 的明显否决点。",
                    "source_person": target_person,
                    "is_blocking": True,
                }
            )

    report_preferences = mirror_index.get("report_preferences", {}) or {}
    preferred_order = list(report_preferences.get("preferred_order", []) or [])
    order_match_count = sum(1 for item in preferred_order if mirror_has_signal(material_content, tuple([item])))
    matched_strengths = [
        f"命中 `{item}`"
        for item in list(report_preferences.get("must_include", []) or [])
        if mirror_has_signal(material_content, tuple([item]))
    ][:6]
    if "提及率" in material_content or "占比" in material_content:
        matched_strengths.append("报告已经开始用例数/提及率/占比说话，不再只是抽象判断。")
    if "这意味着" in material_content and "为什么重要" in material_content:
        matched_strengths.append("报告已具备比较明确的 so what 与管理翻译。")

    include_ratio = len(matched_rules) / max(len(must_include), 1)
    veto_penalty = min(len(veto_hits) * 15, 40)
    order_bonus = min(order_match_count * 4, 12)
    base_score = int(include_ratio * 100) - veto_penalty + order_bonus
    overall_score = max(0, min(100, base_score))
    pass_threshold = MIRROR_SCORE_THRESHOLDS.get(target_person, 85)
    pass_status = "pass" if overall_score >= pass_threshold and not veto_hits else "fail"

    dimensions = {}
    for dimension_name in mirror_index.get("evaluation_contract", {}).get("dimensions", []) or []:
        if dimension_name == "goal_acceptance_score":
            value = min(5.0, 2.0 + include_ratio * 3.0)
        elif dimension_name == "next_action_fit_score":
            value = 5.0 if mirror_has_signal(material_content, ("下一步", "动作", "优先级", "缺口")) else 2.5
        elif dimension_name == "report_fit_score":
            value = max(1.0, min(5.0, 5.0 - len(veto_hits) - len(missed_rules) * 0.25))
        else:
            value = min(5.0, 2.0 + order_match_count * 0.75)
        dimensions[dimension_name] = round(value, 2)

    return {
        "target_person": target_person,
        "material_title": material_title,
        "overall_score": overall_score,
        "pass_threshold": pass_threshold,
        "pass_status": pass_status,
        "hard_veto_hits": veto_hits,
        "major_gaps": missed_rules[:6],
        "matched_strengths": matched_strengths,
        "rewrite_actions": rewrite_actions,
        "should_continue_iteration": pass_status != "pass",
        "review_summary": f"{target_person} 视角下当前得分 {overall_score}，{'已通过' if pass_status == 'pass' else '仍需继续改稿'}。",
        "dimension_scores": dimensions,
        "evidence_policy": mirror_index.get("evidence_policy", {}),
    }


def merge_mirror_review_results(
    review_results: list[dict[str, object]],
) -> dict[str, object]:
    blocking_actions: list[dict[str, object]] = []
    non_blocking_actions: list[dict[str, object]] = []
    open_veto_hits: list[dict[str, object]] = []
    matched_strengths: list[str] = []
    for result in review_results:
        matched_strengths.extend(str(item) for item in result.get("matched_strengths", []) or [])
        open_veto_hits.extend(result.get("hard_veto_hits", []) or [])
        for action in result.get("rewrite_actions", []) or []:
            if action.get("is_blocking"):
                blocking_actions.append(action)
            else:
                non_blocking_actions.append(action)
    deduped_actions: dict[str, dict[str, object]] = {}
    conflicted_actions: list[dict[str, object]] = []
    for action in blocking_actions + non_blocking_actions:
        key = f"{action.get('target_section', '')}:{action.get('instruction', '')}"
        if key in deduped_actions and deduped_actions[key].get("source_person") != action.get("source_person"):
            conflicted_actions.append({"action_key": key, "sources": [deduped_actions[key].get("source_person"), action.get("source_person")]})
        deduped_actions[key] = action
    return {
        "blocking_actions": sorted(
            [action for action in deduped_actions.values() if action.get("is_blocking")],
            key=lambda item: (item.get("priority", "P9"), item.get("action_id", "")),
        ),
        "non_blocking_actions": sorted(
            [action for action in deduped_actions.values() if not action.get("is_blocking")],
            key=lambda item: (item.get("priority", "P9"), item.get("action_id", "")),
        ),
        "conflicted_actions": conflicted_actions,
        "matched_strengths": dedupe_preserve_order(matched_strengths)[:8],
        "open_veto_hits": open_veto_hits,
    }


def revise_report_text_by_actions(
    report_text: str,
    merged_review: dict[str, object],
) -> str:
    revised = report_text
    blocking_actions = merged_review.get("blocking_actions", []) or []
    if any("当前节点" in str(action.get("instruction", "")) for action in blocking_actions) and "当前节点" not in revised:
        revised = revised.replace("## 0. 问题回答\n", "## 0. 问题回答\n\n- 当前节点：这份看用户报告要解决的是当前轮用户判断能否支撑接下来的竞争与系列动作。\n", 1)
    if any("机制" in str(action.get("instruction", "")) for action in blocking_actions) and "机制" not in revised:
        revised = revised.replace("## 5. 缺口 / 风险 / 下一步\n", "## 5. 缺口 / 风险 / 下一步\n\n- 机制闭环：这一轮输出要直接喂给后续竞争、系列分工和优先级机制，而不是停在观点摘要。\n", 1)
    if any("提及率" in str(action.get("instruction", "")) or "例数" in str(action.get("instruction", "")) for action in blocking_actions) and "提及率" not in revised:
        revised = revised.replace("## 1. 看用户\n", "## 1. 看用户\n\n- 先给数据：本章所有重点问题优先落到提及数、提及率、正负结构，再展开为什么。\n", 1)
    return revised


def build_user_presentation_blocks(
    presentation_page_blocks: dict[str, object],
) -> dict[str, object]:
    user_prefixes = (
        "user_",
        "x_",
        "t_",
        "brand_mindshare_pages",
        "idea_pool_pages",
        "pain_need_pages",
    )
    blocks = [
        block
        for block in presentation_page_blocks.get("blocks", []) or []  # type: ignore[index]
        if str(block.get("page_id", "")).startswith(("user_", "x_", "t_"))
        or str(block.get("page_id", "")) in {"brand_mindshare_pages", "idea_pool_pages", "pain_need_pages"}
    ]
    return {"block_count": len(blocks), "blocks": blocks}


def run_user_presentation_composer(
    *,
    category_name: str,
    time_scope: str,
    market: str | None,
    analysis_goal_text: str,
    style_profile: dict[str, object],
    higher_order_artifacts: dict[str, dict[str, object]],
) -> tuple[str, dict[str, object], str]:
    current_report = render_portfolio_ppt_report(
        category_name=category_name,
        time_scope=time_scope,
        market=market,
        analysis_goal_text=analysis_goal_text,
        style_profile=style_profile,
        higher_order_artifacts=higher_order_artifacts,
    )
    round_results: list[dict[str, object]] = []
    final_report = current_report
    final_status = "failed_threshold"
    for round_no in range(1, MIRROR_MAX_ITERATIONS + 1):
        david_review = build_mirror_review_result(
            target_person="David",
            material_title=f"{category_name} 看用户汇报稿 Round {round_no}",
            material_content=final_report,
        )
        qiandong_review = build_mirror_review_result(
            target_person="钱董",
            material_title=f"{category_name} 看用户汇报稿 Round {round_no}",
            material_content=final_report,
        )
        merged = merge_mirror_review_results([david_review, qiandong_review])
        round_results.append(
            {
                "round_no": round_no,
                "david_score": david_review["overall_score"],
                "qiandong_score": qiandong_review["overall_score"],
                "david_veto_hits": david_review["hard_veto_hits"],
                "qiandong_veto_hits": qiandong_review["hard_veto_hits"],
                "merged_rewrite_actions": merged["blocking_actions"] + merged["non_blocking_actions"],
                "round_summary": f"David={david_review['overall_score']} / 钱董={qiandong_review['overall_score']}",
            }
        )
        if (
            int(david_review["overall_score"]) >= MIRROR_SCORE_THRESHOLDS["David"]
            and int(qiandong_review["overall_score"]) >= MIRROR_SCORE_THRESHOLDS["钱董"]
            and not david_review["hard_veto_hits"]
            and not qiandong_review["hard_veto_hits"]
        ):
            final_status = "passed"
            break
        if round_no < MIRROR_MAX_ITERATIONS:
            final_report = revise_report_text_by_actions(final_report, merged)
    best_round = max(round_results, key=lambda row: (int(row["david_score"]) + int(row["qiandong_score"])))
    open_risks = [
        f"第{row['round_no']}轮：{row['round_summary']}"
        for row in round_results
        if row["round_no"] == best_round["round_no"] and (row["david_veto_hits"] or row["qiandong_veto_hits"])
    ]
    risk_text = "# Mirror Open Risks\n\n" + "\n".join(f"- {line}" for line in (open_risks or ["当前双镜像审稿已达到默认阈值。"])) + "\n"
    return final_report, {
        "iteration_count": len(round_results),
        "target_people": ["David", "钱董"],
        "score_thresholds": MIRROR_SCORE_THRESHOLDS,
        "round_results": round_results,
        "best_round": best_round,
        "final_status": final_status,
        "open_veto_hits": best_round["david_veto_hits"] + best_round["qiandong_veto_hits"],
        "final_rewrite_actions": best_round["merged_rewrite_actions"],
    }, risk_text


def build_competition_capability_theme_cards(
    competition_capability_scan: dict[str, object],
) -> list[dict[str, object]]:
    rows = competition_capability_scan.get("rows", []) or []
    grouped = {
        "高端托管门槛": [row for row in rows if row.get("capability_dimension") in {"机身高度", "拖地体系", "基站自清洁"}],
        "主销结果稳定门槛": [row for row in rows if row.get("capability_dimension") in {"免维护", "滚刷 / 边刷防缠", "越障"}],
        "下探带宽完整度门槛": [row for row in rows if row.get("capability_dimension") in {"AI污渍识别 / 主动感知", "热水洗 / 蒸汽"}],
    }
    lead_map = {
        "高端托管门槛": "高端竞争现在不只是参数高，而是要让用户相信机器真的能少操心、少返工、少救场。",
        "主销结果稳定门槛": "主销带真正要卷的是“默认能把事做完”，而不是把所有亮点都堆成高端黑科技。",
        "下探带宽完整度门槛": "下探带宽不是多一款产品这么简单，而是要回答：哪些能力必须守住，哪些现在先别讲满。",
    }
    cards: list[dict[str, object]] = []
    for title, grouped_rows in grouped.items():
        cards.append(
            {
                "title": title,
                "lead_judgment": lead_map[title],
                "bullets": [
                    f"{row.get('capability_dimension', '-')}: {row.get('ecovacs_status', '-')}"
                    for row in grouped_rows[:3]
                ],
                "representative_quotes": [
                    f"{row.get('capability_dimension', '-')}: {row.get('why_it_matters', '-')}"
                    for row in grouped_rows[:2]
                ],
            }
        )
    return cards


def competition_scope_wrong_battlefield(scope: str) -> str:
    mapping = {
        "X_omni": "如果把 X 讲成参数堆料战，就会把高端托管承诺讲散。",
        "T_omni": "如果把 T 讲成高端黑科技战，就会偏离主销 omni 的默认答案之战。",
        "N_omni": "如果把 N_omni 讲成旗舰战，会把下探承接位讲成伪高端。",
        "N_aes": "如果把 N_aes 讲成高端能力战，会错过入门带基站守位的真正意义。",
        "N_single": "如果把 N_single 讲成高端体验战，会直接丢掉预算敏感带的守位逻辑。",
    }
    return mapping.get(scope, "当前错误战场仍待补充。")


def competition_scope_not_now(scope: str) -> str:
    mapping = {
        "X_omni": "先别把远期协同和生态联动抢成当前主卖点。",
        "T_omni": "先别把表达型加分项和高端黑科技放到主销叙事中心。",
        "N_omni": "先别把它讲成已经有稳定自家样本的成熟带宽。",
        "N_aes": "先别把中国区 `N_aes` 讲成已经补齐的稳定承接位。",
        "N_single": "先别忽略预算敏感用户对基础底线的真实要求。",
    }
    return mapping.get(scope, "当前仍需继续明确先别讲什么。")


def build_competition_matchup_detail_cards(
    competition_matchup_matrix: dict[str, object],
) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for row in competition_matchup_matrix.get("rows", []) or []:
        scope_label = str(row.get("competition_scope", "-"))
        scope = next((code for code in COMPETITION_SCOPE_ORDER if competition_scope_label(code) == scope_label), "")
        cards.append(
            {
                "title": scope_label,
                "lead_judgment": str(row.get("why_this_matchup", "-")),
                "bullets": [
                    f"真正比的不是参数，而是：{row.get('headline_capabilities', '-')}",
                    f"如果讲歪，会把自己带到的错误战场：{competition_scope_wrong_battlefield(scope)}",
                    f"先别讲什么：{competition_scope_not_now(scope)}",
                    f"当前最该防的 VOC 风险：{row.get('voc_risk_to_watch', '-')}",
                ],
            }
        )
    return cards


def build_competition_voc_secondary_issue_lookup(
    competition_voc_xtn_breakdown: dict[str, object],
) -> dict[tuple[str, str], str]:
    level_2_rows = competition_voc_xtn_breakdown.get("level_2_rows", []) or []
    lookup: dict[tuple[str, str], str] = {}
    for scope in COMPETITION_SCOPE_ORDER:
        for market_scope in ["中国", "海外"]:
            candidates = [
                row
                for row in level_2_rows
                if str(row.get("competition_scope")) == scope
                and str(row.get("market_scope")) == market_scope
                and bool(row.get("is_self_brand"))
            ]
            candidates.sort(key=lambda row: (-float(row.get("message_share", 0.0)), -int(row.get("message_count", 0))))
            unique_issues = []
            for row in candidates:
                issue = str(row.get("problem_level_2", ""))
                if issue and issue not in unique_issues:
                    unique_issues.append(issue)
            if len(unique_issues) >= 2:
                lookup[(scope, market_scope)] = unique_issues[1]
    return lookup


def build_competition_voc_market_rows_v2(
    competition_voc_market_split: dict[str, object],
    competition_voc_xtn_breakdown: dict[str, object],
    market_scope: str,
) -> list[list[str]]:
    rows: list[list[str]] = []
    market_rows = [
        row
        for row in competition_voc_market_split.get("market_rows", []) or []
        if row.get("market_scope") == market_scope
    ]
    grouped = {str(row.get("competition_scope", "")): row for row in market_rows}
    secondary_lookup = build_competition_voc_secondary_issue_lookup(competition_voc_xtn_breakdown)
    for scope in COMPETITION_SCOPE_ORDER:
        row = grouped.get(scope)
        if not row:
            rows.append(
                [
                    competition_scope_label(scope),
                    "待补充",
                    "-",
                    "当前该竞争带稳定 VOC 仍待补齐。",
                    "缺样本声明",
                    "-",
                ]
            )
            continue
        mode = str(row.get("frontline_mode", "missing"))
        if mode == "self_stable":
            primary_issue = f"{row.get('top_problem_level_1', '待补充')} / {row.get('top_problem_level_2', '待补充')}"
            secondary_issue = secondary_lookup.get((scope, market_scope), "-")
            implication = (
                f"这说明用户真正不能接受的是：机器明明应该承担 `{row.get('top_problem_level_1', '待补充')}`，但最后仍把 `{row.get('top_problem_level_2', '待补充')}` 留给用户补救。"
            )
            current_judgment = f"自家稳定判断：{row.get('performance_level', '待比较')}"
        elif mode == "external_only":
            primary_issue = f"外部门槛：{row.get('voc_complaint_summary', '待补充')}"
            secondary_issue = "-"
            implication = "这说明当前带宽的外部门槛已经被定义，但科沃斯自家稳定样本还不够，先别把它讲成自家硬结论。"
            current_judgment = "外部门槛"
        else:
            primary_issue = "待补充"
            secondary_issue = "-"
            implication = "当前该竞争带稳定 VOC 仍待补齐，先不把这条带讲满。"
            current_judgment = "缺样本声明"
        rows.append(
            [
                competition_scope_label(scope),
                primary_issue,
                secondary_issue,
                implication,
                current_judgment,
                str(row.get("best_competitor_name", "-")) or "-",
            ]
        )
    return rows


def scope_shift_pattern(rows: list[dict[str, object]]) -> str:
    counter = Counter(str(row.get("generation_shift_type", "")) for row in rows if row.get("generation_shift_type"))
    parts = [
        f"{counter[label]}个品牌{label}"
        for label in ["带宽加宽", "空档进入", "延续迭代", "代际缺失"]
        if counter.get(label)
    ]
    return "、".join(parts) if parts else "当前仍以延续迭代为主"


def scope_brand_actions(rows: list[dict[str, object]]) -> str:
    candidates = [row for row in rows if not row.get("is_self_brand")] or rows
    ordered = sorted(
        candidates,
        key=lambda row: (
            {"带宽加宽": 0, "空档进入": 1, "延续迭代": 2, "代际缺失": 3}.get(str(row.get("generation_shift_type", "")), 9),
            str(row.get("brand", "")),
        ),
    )
    parts: list[str] = []
    for row in ordered[:3]:
        models = list(row.get("current_products", []) or row.get("previous_products", []))
        parts.append(f"{row.get('brand', '-')}：{row.get('generation_shift_type', '-')}，代表 `{format_product_examples(models, limit=2)}`")
    return "；".join(parts) if parts else "-"


def scope_representative_models(rows: list[dict[str, object]]) -> str:
    candidates = [row for row in rows if not row.get("is_self_brand")] or rows
    models: list[str] = []
    for row in candidates:
        models.extend(str(item) for item in row.get("current_products", []) or [])
    return format_product_examples(dedupe_preserve_order(models), limit=3)


def scope_lead_judgment(scope: str, rows: list[dict[str, object]]) -> str:
    lead_map = {
        "X_omni": "旗舰 omni 这一代看起来都在继续推高卖点，但真正拉开差距的已经不是单点参数，而是谁更能把高端感和托管承诺同时讲圆。",
        "T_omni": "主销 omni 这一代更像在收口到“结果更稳、少返工、少维护”，谁更像省心且做完事，谁就更占位。",
        "N_omni": "omni 下探这一代不再是补一款就够，而是在用更密的产品带宽去卡位中高端下探需求。",
        "N_aes": "AES 这一代更像入门带基站的守位战，带宽越密、空档越少，越能稳住下探承接。",
        "N_single": "单机这一代更像低价守位战，谁先把预算敏感用户留在自己体系里，谁就更占便宜。",
    }
    return f"{lead_map.get(scope, competition_scope_focus(scope))} 当前格局上，{scope_shift_pattern(rows)}。"


def shape_scope_change(scope: str, rows: list[dict[str, object]]) -> str:
    return "；".join(
        part
        for part in [competition_scope_focus(scope), scope_shift_pattern(rows), scope_brand_actions(rows)]
        if part and part != "-"
    )


def aggregate_demand_signal(demand_pool_snapshot: dict[str, object], theme_names: list[str]) -> dict[str, object]:
    rows = [row for row in demand_pool_snapshot.get("theme_rows", []) or [] if row.get("theme_name") in theme_names]
    if not rows:
        return {
            "item_count": 0,
            "statuses": [],
            "owners": [],
            "unassigned_count": 0,
            "no_solution_count": 0,
            "research_like_count": 0,
        }
    return {
        "item_count": sum(int(row.get("item_count", 0)) for row in rows),
        "statuses": dedupe_preserve_order([status for row in rows for status in row.get("statuses", [])])[:3],
        "owners": dedupe_preserve_order([owner for row in rows for owner in row.get("owners", []) if owner != "未分配"])[:3],
        "unassigned_count": sum(int(row.get("unassigned_count", 0)) for row in rows),
        "no_solution_count": sum(int(row.get("no_solution_count", 0)) for row in rows),
        "research_like_count": sum(int(row.get("research_like_count", 0)) for row in rows),
    }


def summarize_demand_status(demand_pool_snapshot: dict[str, object], theme_names: list[str]) -> str:
    summary = aggregate_demand_signal(demand_pool_snapshot, theme_names)
    if int(summary["item_count"]) == 0:
        return "需求池里暂无直接映射"
    parts = [f"{summary['item_count']}项需求"]
    if summary["statuses"]:
        parts.append("状态：" + "、".join(summary["statuses"]))
    if summary["owners"]:
        parts.append("负责人：" + "、".join(summary["owners"][:2]))
    risk_parts = []
    if int(summary["unassigned_count"]) > 0:
        risk_parts.append(f"未分配{summary['unassigned_count']}项")
    if int(summary["no_solution_count"]) > 0:
        risk_parts.append(f"暂无方案{summary['no_solution_count']}项")
    if int(summary["research_like_count"]) > 0:
        risk_parts.append(f"待研究/评估{summary['research_like_count']}项")
    if risk_parts:
        parts.append("风险：" + "、".join(risk_parts))
    if int(summary["unassigned_count"]) + int(summary["no_solution_count"]) + int(summary["research_like_count"]) >= max(3, int(summary["item_count"]) // 3):
        parts.append("外部已是高优，但内部承接责任还没收口")
    return "；".join(parts)


def build_competition_generation_analysis(
    generation_comparison: dict[str, object],
    competition_generation_registry: dict[str, object],
) -> dict[str, object]:
    registry_rows = competition_generation_registry.get("rows", []) or []
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in registry_rows:
        key = (str(row["competition_scope"]), str(row["brand"]), str(row["shape_type"]))
        item = grouped.setdefault(
            key,
            {
                "competition_scope": row["competition_scope"],
                "brand": row["brand"],
                "series_family": row["series_family"],
                "shape_type": row["shape_type"],
                "is_self_brand": row["is_self_brand"],
                "previous_products": [],
                "current_products": [],
                "notes": row.get("notes", ""),
            },
        )
        bucket = str(row["generation_bucket"])
        if bucket == "previous":
            item["previous_products"] = list(row.get("product_names", []))
        else:
            item["current_products"] = list(row.get("product_names", []))
    brand_rows: list[dict[str, object]] = []
    for item in grouped.values():
        previous_products = list(item.get("previous_products", []))
        current_products = list(item.get("current_products", []))
        shift = summarize_generation_shift(previous_products, current_products)
        scope = str(item["competition_scope"])
        brand = str(item["brand"])
        shape = str(item["shape_type"])
        if item["is_self_brand"] and scope.startswith("N_"):
            one_line = f"科沃斯在 `{shape}` 形态由 `{format_product_examples(previous_products, limit=2)}` 走到 `{format_product_examples(current_products, limit=2)}`，当前更像在补产品带宽。"
        elif scope == "X_omni":
            one_line = f"{brand} 在 X 所在 omni 带由 `{format_product_examples(previous_products, limit=2)}` 走到 `{format_product_examples(current_products, limit=2)}`，当前更像 `{shift}`。"
        elif scope == "T_omni":
            one_line = f"{brand} 在 T 所在 omni 带由 `{format_product_examples(previous_products, limit=2)}` 走到 `{format_product_examples(current_products, limit=2)}`，当前更像 `{shift}`。"
        else:
            one_line = f"{brand} 在 `{shape}` 形态由 `{format_product_examples(previous_products, limit=2)}` 走到 `{format_product_examples(current_products, limit=2)}`，当前更像 `{shift}`。"
        brand_rows.append(
            {
                "brand": brand,
                "competition_scope": scope,
                "series_family": item["series_family"],
                "shape_type": shape,
                "is_self_brand": item["is_self_brand"],
                "previous_products": previous_products,
                "current_products": current_products,
                "generation_shift_type": shift,
                "one_line_judgment": one_line,
                "what_it_means_for_competition": competition_meaning(shape, scope, brand, bool(item["is_self_brand"])),
            }
        )
    grouped_scope_rows: dict[str, list[dict[str, object]]] = {}
    for row in brand_rows:
        grouped_scope_rows.setdefault(str(row["competition_scope"]), []).append(row)
    scope_summary_rows: list[dict[str, object]] = []
    shape_summary_rows: list[dict[str, object]] = []
    for scope in sorted(grouped_scope_rows.keys(), key=competition_scope_rank):
        rows_for_scope = grouped_scope_rows[scope]
        shape_type = str(rows_for_scope[0]["shape_type"])
        scope_summary_rows.append(
            {
                "competition_scope": competition_scope_label(scope),
                "shape_type": shape_type,
                "lead_judgment": scope_lead_judgment(scope, rows_for_scope),
                "current_focus": competition_scope_focus(scope),
                "brand_shift_pattern": scope_shift_pattern(rows_for_scope),
                "what_ecovacs_is_really_facing": competition_scope_implication(scope),
                "representative_models": scope_representative_models(rows_for_scope),
            }
        )
        shape_summary_rows.append(
            {
                "shape_type": shape_type,
                "scope_breakdown": competition_scope_label(scope),
                "lead_judgment": scope_lead_judgment(scope, rows_for_scope),
                "what_changed_this_generation": shape_scope_change(scope, rows_for_scope),
                "what_it_means_for_ecovacs": competition_scope_implication(scope),
            }
        )
    series_rows = list(generation_comparison.get("series_rows", []) or [])
    n_rows = [row for row in brand_rows if row["series_family"] == "N" and row["is_self_brand"]]
    series_rows.append(
        {
            "series_code": "N",
            "lead_judgment": "N 不是单一系列故事，而是 omni / aes / 单机 三条带宽一起承接中高端下探、入门带基站和低价单机守位。",
            "shape_bandwidth_rows": [
                {
                    "shape_type": row["shape_type"],
                    "previous_products": row["previous_products"],
                    "current_products": row["current_products"],
                    "generation_shift_type": row["generation_shift_type"],
                }
                for row in n_rows
            ],
        }
    )
    return {
        "registry_version": competition_generation_registry.get("version", ""),
        "series_generation_rows": series_rows,
        "scope_summary_rows": scope_summary_rows,
        "shape_summary_rows": shape_summary_rows,
        "brand_shape_generation_rows": sorted(
            brand_rows,
            key=lambda row: (
                str(row["shape_type"]),
                competition_scope_rank(str(row["competition_scope"])),
                not bool(row["is_self_brand"]),
                str(row["brand"]),
            ),
        ),
    }


def match_demand_theme(text: str) -> list[str]:
    normalized = normalize_text_local(text)
    matched = [
        theme_name
        for theme_name, keywords in DEMAND_POOL_THEME_RULES.items()
        if any(normalize_text_local(keyword) in normalized for keyword in keywords)
    ]
    return matched or ["其他"]


def build_demand_pool_snapshot() -> dict[str, object]:
    import openpyxl

    wb = openpyxl.load_workbook(DEMAND_POOL_XLSX_PATH, data_only=True)
    ws = wb[wb.sheetnames[0]]
    headers = [str(cell.value) if cell.value is not None else "" for cell in ws[1]]
    rows = [dict(zip(headers, row)) for row in ws.iter_rows(min_row=2, values_only=True)]
    leaf_rows = []
    for row in rows:
        if any(row.get(field) for field in ["需求状态", "需求来源", "需求负责人", "需求详细描述（可附文档）"]):
            leaf_rows.append(row)
    theme_counter: dict[str, dict[str, object]] = {}
    status_counter: dict[str, int] = {}
    owner_counter: dict[str, int] = {}
    category_counter: dict[str, int] = {}
    for row in leaf_rows:
        status = str(row.get("需求状态") or "未标记")
        owner = str(row.get("需求负责人") or "未分配")
        category = str(row.get("需求分类") or "未分类")
        status_counter[status] = status_counter.get(status, 0) + 1
        owner_counter[owner] = owner_counter.get(owner, 0) + 1
        category_counter[category] = category_counter.get(category, 0) + 1
        text_blob = " ".join(
            str(row.get(key) or "")
            for key in ["需求描述", "需求分类", "需求属性标签", "需求详细描述（可附文档）", "父记录"]
        )
        for theme_name in match_demand_theme(text_blob):
            item = theme_counter.setdefault(
                theme_name,
                {
                    "theme_name": theme_name,
                    "item_count": 0,
                    "statuses": [],
                    "owners": [],
                    "categories": [],
                    "unassigned_count": 0,
                    "no_solution_count": 0,
                    "research_like_count": 0,
                },
            )
            item["item_count"] = int(item["item_count"]) + 1
            item["statuses"].append(status)
            item["owners"].append(owner)
            item["categories"].append(category)
            if owner == "未分配":
                item["unassigned_count"] = int(item["unassigned_count"]) + 1
            if status in DEMAND_POOL_NO_SOLUTION_STATUSES:
                item["no_solution_count"] = int(item["no_solution_count"]) + 1
            if status in DEMAND_POOL_RESEARCH_STATUSES:
                item["research_like_count"] = int(item["research_like_count"]) + 1
    theme_rows = []
    for row in theme_counter.values():
        theme_rows.append(
            {
                "theme_name": row["theme_name"],
                "item_count": row["item_count"],
                "statuses": dedupe_preserve_order(row["statuses"])[:4],
                "owners": dedupe_preserve_order(row["owners"])[:4],
                "categories": dedupe_preserve_order(row["categories"])[:4],
                "unassigned_count": int(row["unassigned_count"]),
                "no_solution_count": int(row["no_solution_count"]),
                "research_like_count": int(row["research_like_count"]),
            }
        )
    theme_rows.sort(key=lambda row: (-int(row["item_count"]), row["theme_name"]))
    status_rows = [{"status": key, "item_count": value} for key, value in sorted(status_counter.items(), key=lambda item: (-item[1], item[0]))]
    owner_rows = [{"owner": key, "item_count": value} for key, value in sorted(owner_counter.items(), key=lambda item: (-item[1], item[0]))]
    category_rows = [{"category": key, "item_count": value} for key, value in sorted(category_counter.items(), key=lambda item: (-item[1], item[0]))]
    return {
        "sheet_name": ws.title,
        "leaf_item_count": len(leaf_rows),
        "theme_rows": theme_rows,
        "status_rows": status_rows,
        "owner_rows": owner_rows,
        "category_rows": category_rows,
    }
def build_portfolio_generation_strategy(
    competition_generation_analysis: dict[str, object],
    generation_comparison: dict[str, object],
    demand_pool_snapshot: dict[str, object],
    strategy_translation: dict[str, object],
) -> dict[str, object]:
    x_themes = ["清洁效果与水痕污渍", "边角与覆盖率", "维护与基站操作", "智能/App/语音/地图"]
    t_themes = ["清洁效果与水痕污渍", "边角与覆盖率", "维护与基站操作", "避障越障与卡困"]
    n_themes = ["边角与覆盖率", "避障越障与卡困", "多机协同与统一控制"]
    x_row = next((row for row in generation_comparison.get("series_rows", []) or [] if row.get("series_code") == "X"), {})
    t_row = next((row for row in generation_comparison.get("series_rows", []) or [] if row.get("series_code") == "T"), {})
    n_bandwidth = [row for row in competition_generation_analysis.get("brand_shape_generation_rows", []) if row.get("series_family") == "N" and row.get("is_self_brand")]
    portfolio_bandwidth_rows: list[dict[str, object]] = [
        {
            "series_family": "X",
            "shape_type": "omni",
            "previous_products": ["X11 Pro", "X11旋风尘桶版"],
            "current_products": ["X12 Pro", "X12旋风尘桶版"],
            "current_role": "高端旗舰 omni 主线",
            "must_carry": "把高端旗舰的托管承诺和高价值体验讲透，兑现少操心、少返工、真托管。",
            "must_not_carry": "不要继续替 N 扛下探守位，也不要提前替未来协同抢主叙事。",
            "portfolio_gap": "一旦把下探守位和远期协同都压进 X，高端叙事会被拖散，旗舰价值会失焦。",
            "why_it_matters": "X 是高端旗舰的定标位，决定科沃斯能不能把高价值体验讲成可信承诺。",
        },
        {
            "series_family": "T",
            "shape_type": "omni",
            "previous_products": ["T80S"],
            "current_products": ["T90 ULTRA", "T90 PRO", "T90"],
            "current_role": "主销 omni / 结果稳定与托管可信主线",
            "must_carry": "把结果更稳、少返工、少维护讲成主销 omni 的核心动作。",
            "must_not_carry": "不要被表达型加分项和过低价守位带偏，也不要替 N 去补带宽空档。",
            "portfolio_gap": "如果 T 继续承担过多非主销任务，结果稳定和少维护这条主线就会被说散。",
            "why_it_matters": "T 是主销 omni 的成交主战场，决定科沃斯能不能把“省心且做完事”讲成默认答案。",
        },
    ]
    for row in n_bandwidth:
        role = {
            "omni": "omni 下探带宽",
            "aes": "入门带基站承接带",
            "single": "低价单机守位带",
        }.get(row["shape_type"], "N 带宽承接带")
        gap = {
            "omni": "如果 omni 下探带混进 X/T 叙事，旗舰和主销都会被迫替 N 补位。",
            "aes": "如果 AES 承接断档，入门带基站需求会直接被竞品截走。",
            "single": "如果单机守位缺失，预算敏感用户会更早流向别家体系。",
        }.get(row["shape_type"], "当前仍需继续明确这条带宽的角色。")
        must_carry = {
            "omni": "把 omni 下探带讲成独立承接位，接住中高端下探而不挤占 X/T 主线。",
            "aes": "把入门带基站承接位补齐，别让 AES 需求继续空档化。",
            "single": "守住低价单机基本盘，避免预算敏感用户直接流失。",
        }.get(row["shape_type"], "明确这条带宽该承接的需求。")
        must_not_carry = {
            "omni": "不要再让 X/T 旗舰线替它解释下探和守位。",
            "aes": "不要继续让旗舰产品去解释入门带基站承接。",
            "single": "不要继续让主销和旗舰产品去兜低价单机守位。",
        }.get(row["shape_type"], "不要继续压给旗舰。")
        portfolio_bandwidth_rows.append(
            {
                "series_family": "N",
                "shape_type": row["shape_type"],
                "previous_products": row["previous_products"],
                "current_products": row["current_products"],
                "current_role": role,
                "must_carry": must_carry,
                "must_not_carry": must_not_carry,
                "portfolio_gap": gap,
                "why_it_matters": row["what_it_means_for_competition"],
            }
        )
    priority_assignment_rows = [
        {
            "theme_layer": "清洁底线与托管信任",
            "owner_series": "X / T",
            "action_statement": "旗舰和主销 omni 必须把清洁结果、完成率和托管信任一起扛住，不能再把这层底线外包给下探带。",
            "demand_pool_signal": summarize_demand_status(demand_pool_snapshot, x_themes),
            "not_for_series": "不该继续压给 N / AES / 单机去替旗舰兜底。",
        },
        {
            "theme_layer": "主销结果稳定与少维护",
            "owner_series": "T",
            "action_statement": "T 要先把结果更稳、少返工、少维护讲成主销核心，而不是继续被表达型加分项带偏。",
            "demand_pool_signal": summarize_demand_status(demand_pool_snapshot, t_themes),
            "not_for_series": "不该让 X 单独承担主销改善叙事，也不该让 N 被迫补位。",
        },
        {
            "theme_layer": "下探形态守位",
            "owner_series": "N",
            "action_statement": "N 应该把 omni 下探、AES、单机守位分开承接，而不是继续挤占 X/T 的旗舰主叙事。",
            "demand_pool_signal": summarize_demand_status(demand_pool_snapshot, n_themes),
            "not_for_series": "不该继续塞给 X/T 旗舰线。",
        },
        {
            "theme_layer": "未来协同与统一控制",
            "owner_series": "暂不主承接",
            "action_statement": "多机协作当前仍是未来方向，只能做储备，不该提前抢掉本代主卖点。",
            "demand_pool_signal": summarize_demand_status(demand_pool_snapshot, ["多机协同与统一控制"]),
            "not_for_series": "不该提前塞进 X / T 当前主叙事。",
        },
    ]
    x_summary = str(x_row.get("strategy_summary", "X 负责高端旗舰 omni 的托管承诺与高价值体验。"))
    t_summary = str(t_row.get("strategy_summary", "T 负责主销 omni 的结果稳定与托管可信。"))
    roadmap_focus_rows: list[dict[str, object]] = []
    not_now = "、".join(["多机协同", "统一生态", "远期场景联动"])
    for row in strategy_translation.get("half_year_focus", []) or []:
        phase = str(row.get("phase", "-"))
        blocker = str(row.get("core_blocker", "-"))
        if phase == "当前轮次":
            roadmap_focus_rows.append(
                {
                    "stage": phase,
                    "x_message": "少操心、少返工、真托管",
                    "t_message": "结果更稳、少返工、少维护",
                    "n_message": "守住 omni 下探 / aes / 单机带宽",
                    "not_now": not_now,
                    "core_blocker": blocker,
                }
            )
        else:
            roadmap_focus_rows.append(
                {
                    "stage": phase,
                    "x_message": x_summary,
                    "t_message": t_summary,
                    "n_message": "明确 N 在 omni / aes / 单机 的分工与节奏",
                    "not_now": not_now,
                    "core_blocker": blocker,
                }
            )
    return {
        "what_x_should_carry": x_row.get("strategy_summary", "X 负责高端旗舰 omni 的托管承诺与高价值体验。"),
        "what_t_should_carry": t_row.get("strategy_summary", "T 负责主销 omni 的结果稳定与托管可信。"),
        "what_n_should_carry": "N 负责 omni 下探、aes 入门带基站和单机守位三条竞争带。",
        "what_not_to_overload_into_flagship": ["多机协同与统一控制", "低价单机守位", "AES 入门承接"],
        "shape_level_not_now": ["多机协同", "统一生态", "远期场景联动"],
        "portfolio_bandwidth_rows": portfolio_bandwidth_rows,
        "priority_assignment_rows": priority_assignment_rows,
        "roadmap_focus_rows": roadmap_focus_rows,
    }


def extract_docx_paragraphs(docx_path: Path) -> list[str]:
    if not docx_path.exists():
        return []
    with ZipFile(docx_path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    paragraphs: list[str] = []
    for paragraph_xml in re.findall(r"<w:p[\s\S]*?</w:p>", xml):
        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", paragraph_xml)
        paragraph = html.unescape("".join(texts)).strip()
        if paragraph:
            paragraphs.append(paragraph)
    if paragraphs:
        return paragraphs
    texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml)
    return [html.unescape(text.strip()) for text in texts if text.strip()]


def extract_docx_text(docx_path: Path) -> str:
    return "\n".join(extract_docx_paragraphs(docx_path))


def extract_keyword_snippet(text: str, keyword: str, window: int = 180) -> str:
    idx = text.find(keyword)
    if idx < 0:
        return ""
    snippet = text[max(0, idx - 60): min(len(text), idx + window)]
    return " ".join(snippet.split())


def clean_awe_snippet(text: str) -> str:
    cleaned = text
    for bad in ["参观流程", "注册说明", "人力分配", "展位行程", "等待审核", "提前注册"]:
        if bad in cleaned:
            cleaned = cleaned.split(bad, 1)[0]
    return " ".join(cleaned.split()).strip()


def collect_paragraph_evidence(
    paragraphs: list[str],
    keywords: tuple[str, ...] | list[str],
    *,
    limit: int = 3,
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for paragraph in paragraphs:
        matched_keywords = [keyword for keyword in keywords if keyword and keyword in paragraph]
        if not matched_keywords:
            continue
        evidence.append(
            {
                "matched_keywords": matched_keywords[:5],
                "source_snippet": shorten(" ".join(paragraph.split()), width=180, placeholder="..."),
            }
        )
        if len(evidence) >= limit:
            break
    return evidence


def build_awe_exhibition_signals(docx_path: Path = AWE_DOCX_PATH) -> dict[str, object]:
    text = extract_docx_text(docx_path)
    direct_brands = ["追觅", "MOVA", "石头", "iRobot", "萤石", "友望"]
    direct_competitor_signals = [
        {
            "brand": brand,
            "signal_text": f"{brand} 被展会材料明确列为重点关注竞争对手。",
            "source_snippet": clean_awe_snippet(extract_keyword_snippet(text, "重点关注厂商") or extract_keyword_snippet(text, brand)),
        }
        for brand in direct_brands
        if brand in text or brand.lower() in text.lower()
    ]

    industry_signal_specs = [
        ("体验闭环", ("体验闭环", "扫-拖-换-洗-烘-上下水")),
        ("场景细分化", ("场景细分化", "大平层", "养宠家庭", "母婴家庭")),
        ("越障与低空间穿行", ("越障", "7.95", "7.98", "8.8cm")),
        ("蒸汽/热水/喷水拖地", ("蒸汽", "热水", "喷水清洁")),
        ("滚刷/边刷防缠", ("边刷防缠", "割毛滚刷", "防缠")),
        ("订阅式服务", ("订阅式服务", "耗材订阅", "云服务订阅")),
    ]
    industry_capability_signals = []
    for signal_name, keywords in industry_signal_specs:
        if any(keyword in text for keyword in keywords):
            industry_capability_signals.append(
                {
                    "signal_name": signal_name,
                    "signal_text": clean_awe_snippet(
                        next((extract_keyword_snippet(text, keyword) for keyword in keywords if extract_keyword_snippet(text, keyword)), signal_name)
                    ),
                }
            )

    cross_category_specs = [
        ("具身智能", ("具身智能", "人形机器人")),
        ("家务机器人", ("家务机器人", "海娃家务机器人")),
        ("陪伴机器人", ("陪伴机器人", "海娃陪伴机器人")),
        ("全屋智能场景联动", ("全屋智能", "场景体验", "鸿蒙生态")),
        ("订阅式服务", ("订阅式服务", "耗材订阅")),
    ]
    cross_category_signals = []
    for signal_name, keywords in cross_category_specs:
        if any(keyword in text for keyword in keywords):
            cross_category_signals.append(
                {
                    "signal_name": signal_name,
                    "signal_text": clean_awe_snippet(
                        next((extract_keyword_snippet(text, keyword) for keyword in keywords if extract_keyword_snippet(text, keyword)), signal_name)
                    ),
                }
            )

    design_cmf_signals = []
    for keyword in ("设计趋势洞察", "ID", "CMF", "材料应用特色", "外观设计"):
        snippet = extract_keyword_snippet(text, keyword)
        if snippet:
            design_cmf_signals.append(
                {
                    "signal_name": keyword,
                    "signal_text": clean_awe_snippet(snippet),
                }
            )
    if not design_cmf_signals and text:
        design_cmf_signals.append(
            {
                "signal_name": "家装融入与CMF",
                "signal_text": "AWE 这轮把设计趋势洞察列为明确任务，说明外观、CMF 和材料已经是竞争解释层的一部分。",
            }
        )

    return {
        "source_path": str(docx_path),
        "direct_competitor_signals": direct_competitor_signals,
        "industry_capability_signals": industry_capability_signals,
        "cross_category_signals": cross_category_signals,
        "design_cmf_signals": design_cmf_signals,
    }


def build_future_intelligence_signals(
    awe_paths: list[Path] | None = None,
    method_path: Path = COMPETITION_INTELLIGENCE_DOCX_PATH,
) -> dict[str, object]:
    source_paths = awe_paths or [AWE_DOCX_PATH, AWE_2026_DOCX_PATH]
    all_paths = dedupe_preserve_order([method_path, *source_paths])
    paragraphs_by_source: dict[str, list[str]] = {
        str(path): extract_docx_paragraphs(path)
        for path in all_paths
    }
    combined_paragraphs = [
        paragraph
        for paragraphs in paragraphs_by_source.values()
        for paragraph in paragraphs
    ]
    signal_groups: list[dict[str, object]] = []
    for rule in FUTURE_SIGNAL_GROUP_RULES:
        evidence = collect_paragraph_evidence(combined_paragraphs, rule["keywords"], limit=4)  # type: ignore[arg-type]
        if not evidence:
            continue
        signal_groups.append(
            {
                "card_type": "行业终局信号卡",
                "signal_group": rule["signal_group"],
                "value_axes": list(rule["value_axes"]),  # type: ignore[arg-type]
                "evidence": evidence,
                "pm_reading": rule["pm_reading"],
                "confidence_boundary": "AWE 和补充情报在这里仅作为行业终局信号，不等于确定上市能力。",
            }
        )
    return {
        "available": bool(combined_paragraphs),
        "source_paths": [str(path) for path in all_paths],
        "available_source_paths": [
            source_path
            for source_path, paragraphs in paragraphs_by_source.items()
            if paragraphs
        ],
        "signal_group_count": len(signal_groups),
        "signal_groups": signal_groups,
        "generated_from": "AWE 行业趋势与竞争分析补充材料",
        "artifact_role": "判断品类边界和行业终局，不证明当前谁赢。",
        "red_lines": list(FUTURE_INTELLIGENCE_RED_LINES),
    }


def build_dreame_roadmap_timeline(docx_path: Path = DREAME_ROADMAP_DOCX_PATH) -> dict[str, object]:
    paragraphs = extract_docx_paragraphs(docx_path)
    text = "\n".join(paragraphs)
    rows: list[dict[str, object]] = []
    for rule in DREAME_ROADMAP_SIGNAL_RULES:
        evidence = collect_paragraph_evidence(paragraphs, rule["keywords"], limit=2)  # type: ignore[arg-type]
        if not evidence and not any(keyword in text for keyword in rule["keywords"]):  # type: ignore[union-attr]
            continue
        rows.append(
            {
                "card_type": "强竞品意图假设卡",
                "year": rule["year"],
                "value_axis": rule["value_axis"],
                "technology_signal": rule["technology_signal"],
                "maturity_status": rule["maturity_status"],
                "source_evidence": evidence,
                "pm_reading": rule["pm_reading"],
                "confidence_boundary": "追觅路线图未证明研发承接与技术成熟，不能写成确定性上市能力或确定性领先。",
            }
        )
    timeline_by_year: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        timeline_by_year[str(row["year"])].append(row)
    return {
        "available": bool(text),
        "source_path": str(docx_path),
        "row_count": len(rows),
        "rows": rows,
        "timeline_by_year": dict(timeline_by_year),
        "confidence_boundary": "追觅 2027-2028 内容在本报告中只作为强竞品意图假设，用于压力测试我方 Roadmap。",
    }


def build_roadmap_stress_test_cards(
    future_intelligence_signals: dict[str, object],
    dreame_roadmap_timeline: dict[str, object],
) -> dict[str, object]:
    signal_groups = future_intelligence_signals.get("signal_groups", []) or []
    dreame_rows = dreame_roadmap_timeline.get("rows", []) or []
    cards: list[dict[str, object]] = []
    for rule in ROADMAP_STRESS_AXIS_RULES:
        axis = str(rule["value_axis"])
        awe_matches = [
            str(group.get("signal_group", ""))
            for group in signal_groups  # type: ignore[union-attr]
            if axis in (group.get("value_axes", []) or [])  # type: ignore[union-attr]
        ]
        dreame_matches = [
            f"{row.get('year')}：{row.get('technology_signal')}"
            for row in dreame_rows  # type: ignore[union-attr]
            if str(row.get("value_axis", "")) == axis
        ]
        cards.append(
            {
                "card_type": "Roadmap压力测试卡",
                "value_axis": axis,
                "awe_industry_endgame_signal": "、".join(dedupe_preserve_order(awe_matches)) or "暂未命中明确 AWE 信号",
                "dreame_2027_2028_pressure": "；".join(dedupe_preserve_order(dreame_matches)) or "暂未命中明确追觅路线图压力",
                "roadmap_action": rule["stress_action"],
                "pm_judgment": rule["pm_judgment"],
                "priority_correction": rule["priority_correction"],
                "do_not_misfollow": rule["do_not_misfollow"],
                "confidence_boundary": "这是前瞻压力测试，不是当前确定性输赢判断。",
            }
        )
    return {
        "card_count": len(cards),
        "cards": cards,
        "allowed_actions": ["坚持", "加速", "补洞", "观察"],
        "reading_rule": "把 AWE 与追觅路线图压回现有 5 条价值轴，检查我方 Roadmap 是否需要坚持、加速、补洞或观察。",
        "red_lines": list(FUTURE_INTELLIGENCE_RED_LINES),
    }


def build_future_competition_strategy_inputs(roadmap_stress_test_cards: dict[str, object]) -> dict[str, object]:
    cards = roadmap_stress_test_cards.get("cards", []) or []
    return {
        "card_count": len(cards),
        "cards": [
            {
                "card_type": "未来竞争策略输入卡",
                "value_axis": card.get("value_axis"),
                "roadmap_action": card.get("roadmap_action"),
                "config_direction_input": card.get("priority_correction"),
                "test_standard_input": (
                    "把体验结果做成硬门槛：少返工、少接管、少维护、少打扰，而不是只验证参数达成。"
                ),
                "technology_presearch_input": card.get("pm_judgment"),
                "do_not_follow": card.get("do_not_misfollow"),
            }
            for card in cards  # type: ignore[union-attr]
        ],
        "x_series_strategy_bias": "X 系优先吸收全嵌平嵌、免维护闭环、真托管和远期形态预研，守住高端托管从容感。",
        "t_series_strategy_bias": "T 系优先守住拖后结果可信、维护不烦、主销默认答案，不被高端形态战拖偏成本结构。",
        "do_not_follow_parameter_wars": [
            "不把 250℃蒸汽直接当主价值，先验证水痕、轮胎印、顽渍返工是否下降。",
            "不把 45000Pa 直接当主价值，先验证清洁结果、噪声和续航的体验平衡。",
            "不把轮足、飞行、爬楼直接塞进下一代主卖点，先放入远期形态预研和高端场景防御。",
            "不把超薄和平嵌直接覆盖 T 系主销定义，先判断成本和默认答案是否成立。",
        ],
        "confidence_boundary": "前瞻情报默认置信度低于 VOC、配置表和测试数据，只用于修正 next-gen 优先级。",
    }


def build_future_intelligence_extension_artifacts(
    *,
    generated_from: str,
) -> dict[str, dict[str, object]]:
    future_intelligence_signals = build_future_intelligence_signals()
    dreame_roadmap_timeline = build_dreame_roadmap_timeline()
    roadmap_stress_test_cards = build_roadmap_stress_test_cards(
        future_intelligence_signals,
        dreame_roadmap_timeline,
    )
    future_competition_strategy_inputs = build_future_competition_strategy_inputs(
        roadmap_stress_test_cards,
    )
    for payload in [
        future_intelligence_signals,
        dreame_roadmap_timeline,
        roadmap_stress_test_cards,
        future_competition_strategy_inputs,
    ]:
        payload["generated_from"] = generated_from
    return {
        "future_intelligence_signals": future_intelligence_signals,
        "dreame_roadmap_timeline": dreame_roadmap_timeline,
        "roadmap_stress_test_cards": roadmap_stress_test_cards,
        "future_competition_strategy_inputs": future_competition_strategy_inputs,
    }


def render_future_intelligence_pressure_test_section(
    roadmap_stress_test_cards: dict[str, object],
    future_competition_strategy_inputs: dict[str, object],
) -> list[str]:
    lines = [
        "## 6. 前瞻情报压力测试：当前 Roadmap 能否防住 2027-2028",
        "",
        "- 这一层不是展会纪要，也不是追觅参数跟随表；它只回答未来战局会把当前 next-gen 判断压到哪里。",
        "- AWE 作为行业终局信号，追觅路线图作为强竞品意图假设；两者置信度低于 VOC、配置表和测试数据。",
        "",
        "| 价值轴 | AWE 行业终局信号 | 追觅 2027-2028 压力 | Roadmap 动作 | PM 判断 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for card in (roadmap_stress_test_cards.get("cards", []) or [])[:5]:  # type: ignore[union-attr]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(card.get("value_axis", "")),
                    str(card.get("awe_industry_endgame_signal", "")),
                    str(card.get("dreame_2027_2028_pressure", "")),
                    str(card.get("roadmap_action", "")),
                    str(card.get("pm_judgment", "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "- X 系读法："
            + str(future_competition_strategy_inputs.get("x_series_strategy_bias", "优先守住高端托管从容感。")),
            "- T 系读法："
            + str(future_competition_strategy_inputs.get("t_series_strategy_bias", "优先守住主销默认答案。")),
            "- 不误跟："
            + "；".join(str(item) for item in (future_competition_strategy_inputs.get("do_not_follow_parameter_wars", []) or [])[:2]),
            "",
        ]
    )
    return lines


def safe_report_text(value: object, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = " ".join(str(value).replace("\n", " ").split()).strip()
    return text or fallback


def report_join(values: list[object], *, limit: int = 3, fallback: str = "-") -> str:
    cleaned = [safe_report_text(value, "") for value in values]
    cleaned = [value for value in cleaned if value]
    return "；".join(dedupe_preserve_order(cleaned)[:limit]) or fallback


def theme_row_lookup(demand_pool_snapshot: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(row.get("theme_name", "")): row
        for row in demand_pool_snapshot.get("theme_rows", []) or []  # type: ignore[union-attr]
    }


def demand_theme_signal(theme_name: str, demand_pool_snapshot: dict[str, object]) -> str:
    row = theme_row_lookup(demand_pool_snapshot).get(theme_name)
    if not row:
        return "需求池当前未稳定命中，先按用户价值和竞争压力保留观察。"
    item_count = int(row.get("item_count") or 0)
    statuses = report_join(row.get("statuses", []) or [], limit=3, fallback="状态待补")
    owners = report_join(row.get("owners", []) or [], limit=2, fallback="负责人待补")
    return f"需求池当前命中 {item_count} 条，状态：{statuses}，负责人：{owners}。"


def build_series_strategy_report_cards(value_proposition_cards: dict[str, object]) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for series_card in value_proposition_cards.get("series_cards", []) or []:  # type: ignore[union-attr]
        series_code = str(series_card.get("series_code", ""))
        if series_code == "X":
            role = "X 系负责高端托管从容感、强能力可信和高端形态防御。"
        elif series_code == "T":
            role = "T 系负责拖后结果可信、维护不烦和主销默认答案。"
        else:
            role = "当前系列负责把结果稳定和低接管负担讲清楚。"
        cards.append(
            {
                "card_type": "系列战略卡",
                "series_code": series_code,
                "series_label": series_card.get("series_label", "当前系列"),
                "portfolio_role": role,
                "core_value_proposition": series_card.get("core_value_proposition", ""),
                "main_buy_point": series_card.get("main_buy_point", ""),
                "main_breakpoint": series_card.get("main_breakpoint", ""),
                "main_switch_point": series_card.get("main_switch_point", ""),
                "planning_reading": f"{role} 这不是标签总结，而是下一代定义的主约束。",
                "evidence_refs": ["value_proposition_cards.json"],
            }
        )
    return cards


def build_competition_pressure_report_cards(
    competition_engineering_artifacts: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    evidence_payload = competition_engineering_artifacts.get("competition_engineering_evidence_cards", {})
    cards: list[dict[str, object]] = []
    for series_card in evidence_payload.get("series_cards", []) or []:  # type: ignore[union-attr]
        axis_rows = series_card.get("value_config_test_cards", []) or []
        for axis_card in axis_rows[:3]:  # type: ignore[union-attr]
            status = safe_report_text(axis_card.get("self_evidence_status"), "证据待补")
            competitors = axis_card.get("competitor_switch_evidence_cards", []) or []
            competitor_reading = report_join(
                [row.get("switch_reading", "") for row in competitors[:2]],  # type: ignore[union-attr]
                limit=2,
                fallback="竞品证据待补，先不写成确定性输赢。",
            )
            cards.append(
                {
                    "card_type": "竞争压力卡",
                    "series_code": series_card.get("series_code", ""),
                    "series_label": series_card.get("series_label", ""),
                    "value_axis": axis_card.get("value_axis", ""),
                    "self_evidence_status": status,
                    "competition_reading": competitor_reading,
                    "planning_reading": "配置/测试只解释价值兑现能力，真正进入主稿时要翻译成用户信任，而不是参数输赢。",
                    "evidence_refs": ["competition_engineering_evidence_cards.json", "value_config_test_map.json"],
                }
            )
    return cards


def build_future_pressure_report_cards(future_intelligence_artifacts: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    roadmap_cards = future_intelligence_artifacts.get("roadmap_stress_test_cards", {}).get("cards", []) or []
    return [
        {
            "card_type": "未来压力卡",
            "value_axis": card.get("value_axis", ""),
            "awe_signal": card.get("awe_industry_endgame_signal", ""),
            "dreame_pressure": card.get("dreame_2027_2028_pressure", ""),
            "roadmap_action": card.get("roadmap_action", ""),
            "planning_reading": card.get("pm_judgment", ""),
            "do_not_misfollow": card.get("do_not_misfollow", ""),
            "evidence_refs": ["future_intelligence_signals.json", "dreame_roadmap_timeline.json", "roadmap_stress_test_cards.json"],
        }
        for card in roadmap_cards  # type: ignore[union-attr]
    ]


def build_demand_landing_report_cards(
    demand_pool_snapshot: dict[str, object],
    future_intelligence_artifacts: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    stress_cards = future_intelligence_artifacts.get("roadmap_stress_test_cards", {}).get("cards", []) or []
    stress_by_axis = {str(card.get("value_axis", "")): card for card in stress_cards}  # type: ignore[union-attr]
    specs = [
        ("T0", "清洁效果与水痕污渍", "清洁结果可信", "同时伤害结果可信和返工成本，优先作为生死线处理。"),
        ("T0", "维护与基站操作", "免维护闭环", "同时伤害解放双手承诺和高端托管信心，必须优先闭环。"),
        ("T0", "避障越障与卡困", "真托管少接管", "一旦需要用户救场，托管承诺就会破产。"),
        ("T1", "边角与覆盖率", "清洁结果可信", "能支撑结果完整性和竞品防御，但要避免写成孤立参数。"),
        ("T1", "智能/App/语音/地图", "真托管少接管", "能支撑智能托管心智，但必须落到少接管而不是 AI 名词。"),
        ("T2", "噪音体验", "无感融入", "作为持续体验优化项，服务高端融入和主销低打扰。"),
        ("T3", "多机协同与统一控制", "复杂地形通过性", "远期形态和协同机会，先做预研与边界观察。"),
    ]
    cards: list[dict[str, object]] = []
    for priority, theme_name, value_axis, landing_logic in specs:
        stress_card = stress_by_axis.get(value_axis, {})
        cards.append(
            {
                "card_type": "需求落位卡",
                "strategic_priority": priority,
                "theme_name": theme_name,
                "value_axis": value_axis,
                "demand_pool_signal": demand_theme_signal(theme_name, demand_pool_snapshot),
                "roadmap_action": stress_card.get("roadmap_action", "观察"),
                "landing_logic": landing_logic,
                "boundary": "这是战略优先级落位，不输出伪 KANO 分数。",
                "evidence_refs": ["demand_pool_snapshot.json", "roadmap_stress_test_cards.json"],
            }
        )
    return cards


def build_action_plan_report_cards() -> list[dict[str, object]]:
    return [
        {
            "card_type": "5W2H行动卡",
            "action_name": "产研双向互锁与 T0 战役提权",
            "why": "用户价值主张已经收敛到结果可信、免维护闭环和少接管，不能继续按功能模块平均分配资源。",
            "what": "形成 X/T 下一代核心战役清单，并把 T0 需求从普通排期中提出来单独验收。",
            "who": "产品规划、产品线、研发架构、测试共同签收。",
            "when": "下一轮 roadmap 评审前完成优先级重排。",
            "how": "用报告组装层的 T0/T1/T2/T3 落位卡作为讨论底稿。",
            "how_much": "不新增预算假设，先从误跟参数战和弱信号项目中释放资源。",
        },
        {
            "card_type": "5W2H行动卡",
            "action_name": "X/T 产品定义边界重签",
            "why": "X 系和 T 系承担的用户任务不同，不能用同一套卖点话术和配置逻辑覆盖。",
            "what": "输出 X/T 技术下放阶梯、配置边界和测试门槛。",
            "who": "产品企划、硬件、算法、供应链和财务 BP 共同评审。",
            "when": "下一代定义冻结前完成。",
            "how": "X 系优先高端托管从容感，T 系优先主销默认答案。",
            "how_much": "T 系避免被高端形态战拖偏成本，X 系保留高端形态与远期预研空间。",
        },
        {
            "card_type": "5W2H行动卡",
            "action_name": "GTM 口径从参数转向场景结果",
            "why": "竞争压力显示行业会继续卷温度、吸力和形态，但用户真正买的是少返工、少接管、少维护。",
            "what": "更新 X/T 对外卖点矩阵和竞品参数战应对话术。",
            "who": "产品营销、产品规划、PR 和销售培训共同负责。",
            "when": "下一轮新品传播素材冻结前完成。",
            "how": "主打拖后可信、真免维护、无感托管，不把 250℃蒸汽或 45000Pa 当主叙事。",
            "how_much": "营销资源优先投入真实场景对比，而非单点参数海报。",
        },
    ]


def build_report_assembly_cards(
    *,
    value_proposition_cards: dict[str, object],
    competition_engineering_artifacts: dict[str, dict[str, object]],
    future_intelligence_artifacts: dict[str, dict[str, object]],
    demand_pool_snapshot: dict[str, object],
    generated_from: str,
) -> dict[str, object]:
    series_strategy_cards = build_series_strategy_report_cards(value_proposition_cards)
    competition_pressure_cards = build_competition_pressure_report_cards(competition_engineering_artifacts)
    future_pressure_cards = build_future_pressure_report_cards(future_intelligence_artifacts)
    demand_landing_cards = build_demand_landing_report_cards(demand_pool_snapshot, future_intelligence_artifacts)
    action_plan_cards = build_action_plan_report_cards()
    action_counts = Counter(str(card.get("roadmap_action", "观察")) for card in future_pressure_cards)
    executive_summary_cards = [
        {
            "card_type": "执行摘要卡",
            "headline": "这份报告不是把材料堆全，而是把用户价值、竞争压力和需求池压成下一代定义动作。",
            "report_reading": (
                f"当前 Roadmap 压力测试显示：坚持 {action_counts.get('坚持', 0)} 项、加速 {action_counts.get('加速', 0)} 项、"
                f"补洞 {action_counts.get('补洞', 0)} 项、观察 {action_counts.get('观察', 0)} 项。"
            ),
            "planning_reading": "产品规划上要先守住结果可信、免维护闭环和少接管，再决定哪些高端形态值得加速。",
            "evidence_refs": ["value_proposition_cards.json", "competition_engineering_evidence_cards.json", "roadmap_stress_test_cards.json", "demand_pool_snapshot.json"],
        }
    ]
    return {
        "card_types": list(REPORT_ASSEMBLY_CARD_TYPES),
        "executive_summary_cards": executive_summary_cards,
        "series_strategy_cards": series_strategy_cards,
        "competition_pressure_cards": competition_pressure_cards,
        "future_pressure_cards": future_pressure_cards,
        "demand_landing_cards": demand_landing_cards,
        "action_plan_cards": action_plan_cards,
        "evidence_boundary": {
            "generated_from": generated_from,
            "demand_leaf_item_count": demand_pool_snapshot.get("leaf_item_count", 0),
            "rule": "最终报告只组装已有证据，不输出固定百分比或伪 KANO 分数。",
            "red_lines": list(REPORT_ASSEMBLY_RED_LINES),
        },
    }


def render_chapter_triplet(
    lines: list[str],
    *,
    heading: str,
    report_summary: list[str],
    planning_body: list[str],
    evidence_boundary: list[str],
) -> None:
    lines.append(heading)
    lines.append("")
    lines.append("### 给汇报看的结论")
    lines.append("")
    for item in report_summary:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### 给产品规划看的拆解")
    lines.append("")
    for item in planning_body:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### 证据锚点与边界")
    lines.append("")
    for item in evidence_boundary:
        lines.append(f"- {item}")
    lines.append("")


def render_integrated_strategy_report(
    *,
    category_name: str,
    time_scope: str,
    market: str | None,
    analysis_goal_text: str,
    report_assembly_cards: dict[str, object],
) -> str:
    current_market = market or "ALL"
    current_time_scope = time_scope if time_scope and time_scope != "待补充" else "当前已落盘样本周期"
    exec_cards = report_assembly_cards.get("executive_summary_cards", []) or []
    series_cards = report_assembly_cards.get("series_strategy_cards", []) or []
    competition_cards = report_assembly_cards.get("competition_pressure_cards", []) or []
    future_cards = report_assembly_cards.get("future_pressure_cards", []) or []
    demand_cards = report_assembly_cards.get("demand_landing_cards", []) or []
    action_cards = report_assembly_cards.get("action_plan_cards", []) or []
    evidence_boundary = report_assembly_cards.get("evidence_boundary", {}) or {}

    action_summary = Counter(str(card.get("roadmap_action", "观察")) for card in future_cards)  # type: ignore[union-attr]
    t0_cards = [card for card in demand_cards if str(card.get("strategic_priority")) == "T0"]  # type: ignore[union-attr]
    x_card = next((card for card in series_cards if str(card.get("series_code")) == "X"), {})
    t_card = next((card for card in series_cards if str(card.get("series_code")) == "T"), {})

    lines: list[str] = [
        f"# {category_name} 一体化产品规划汇报报告",
        "",
        f"- 当前口径：`{current_market}` / `{current_time_scope}`。",
        f"- 当前分析目标：`{analysis_goal_text}`。",
        "- 这是一份单报告双读法主稿：既服务产品规划定义，也服务产品汇报沟通。",
        "",
    ]
    render_chapter_triplet(
        lines,
        heading="## 0. 一页结论",
        report_summary=[
            safe_report_text((exec_cards[0] if exec_cards else {}).get("headline"), "当前报告已把用户价值、竞争压力和需求池统一到下一代定义动作。"),
            safe_report_text((exec_cards[0] if exec_cards else {}).get("report_reading"), "当前 Roadmap 压力测试已形成坚持、加速、补洞、观察四类动作。"),
            f"需求池当前识别 {evidence_boundary.get('demand_leaf_item_count', 0)} 条叶子需求；本报告只做战略落位，不输出伪 KANO 分数。",
        ],
        planning_body=[
            "从产品定义看，先守住结果可信、免维护闭环和真托管，再决定哪些高端形态值得加速。",
            "从汇报沟通看，报告需要制造行动共识，但每个强判断都必须能回挂到证据卡片。",
            "N 系在本稿中只作为承接边界出现，不和 X/T 做同等深度专场。",
        ],
        evidence_boundary=[
            "证据锚点：value_proposition_cards.json / competition_engineering_evidence_cards.json / roadmap_stress_test_cards.json / demand_pool_snapshot.json。",
            "边界：不直接照搬附件中的固定百分比、固定 KANO 分数或强刺激表达。",
        ],
    )
    render_chapter_triplet(
        lines,
        heading="## 1. 认清用户现实",
        report_summary=[
            f"X 系：{safe_report_text(x_card.get('core_value_proposition'), '更可信的高端强能力与真托管。')}",
            f"T 系：{safe_report_text(t_card.get('core_value_proposition'), '更稳结果与更低维护/接管负担。')}",
            "用户不是在买更多功能名词，而是在买少返工、少接管、少维护的确定性。",
        ],
        planning_body=[
            f"X 系主断点：{safe_report_text(x_card.get('main_breakpoint'), '待结合价值主张卡确认')}。",
            f"T 系主断点：{safe_report_text(t_card.get('main_breakpoint'), '待结合价值主张卡确认')}。",
            "下一代定义要把主买点、主认可点、主断点、主改选点收成同一条价值主张，而不是各讲各的。",
        ],
        evidence_boundary=[
            "证据锚点：value_proposition_cards.json。",
            "边界：科技表达、轻薄、多机协同等弱信号默认只作为加分项或远期机会。",
        ],
    )
    render_chapter_triplet(
        lines,
        heading="## 2. 认清产品线任务",
        report_summary=[
            safe_report_text(x_card.get("portfolio_role"), "X 系负责高端旗舰托管承诺。"),
            safe_report_text(t_card.get("portfolio_role"), "T 系负责主销结果稳定与托管可信。"),
            "产品线分工的目的不是分层好看，而是避免 X/T/N 互相挤占主任务。",
        ],
        planning_body=[
            f"X 系规划输入：{safe_report_text(x_card.get('planning_reading'), '守住高端托管从容感。')}",
            f"T 系规划输入：{safe_report_text(t_card.get('planning_reading'), '守住主销默认答案。')}",
            "N 系只承接下探与守位边界，除非补齐直连样本，否则不进入同等深度判断。",
        ],
        evidence_boundary=[
            "证据锚点：series_strategy_cards / portfolio_generation_strategy.json。",
            "边界：本章不新增 N 系结论，只说明产品组合承接边界。",
        ],
    )
    render_chapter_triplet(
        lines,
        heading="## 3. 认清竞争压力",
        report_summary=[
            "当前竞争分析不写参数输赢，而写用户为什么可能改选。",
            "配置表回答能不能兑现，测试数据回答兑现稳不稳。",
            "只看到配置或只看到测试的竞品，必须保留潜在能力或待验证表述。",
        ],
        planning_body=[
            report_join(
                [
                    f"{card.get('series_label')} / {card.get('value_axis')}：{card.get('self_evidence_status')}，{card.get('competition_reading')}"
                    for card in competition_cards[:4]  # type: ignore[union-attr]
                ],
                limit=4,
                fallback="竞争证据卡待补。",
            ),
            "对下一代来说，真正要补的是用户价值兑现能力和测试门槛，不是参数表的一格。",
        ],
        evidence_boundary=[
            "证据锚点：competition_engineering_evidence_cards.json / value_config_test_map.json。",
            "边界：缺测试、缺配置或弱样本统一进入观察席。",
        ],
    )
    render_chapter_triplet(
        lines,
        heading="## 4. 认清未来战局",
        report_summary=[
            f"Roadmap 压力测试动作：坚持 {action_summary.get('坚持', 0)} 项、加速 {action_summary.get('加速', 0)} 项、补洞 {action_summary.get('补洞', 0)} 项、观察 {action_summary.get('观察', 0)} 项。",
            "AWE 负责提示行业终局，追觅路线图负责做强竞品意图假设。",
            "未来战局不能把我们拉回参数战，仍要回到少返工、少接管、少维护。",
        ],
        planning_body=[
            report_join(
                [
                    f"{card.get('value_axis')}：{card.get('roadmap_action')}，{card.get('planning_reading')}"
                    for card in future_cards[:5]  # type: ignore[union-attr]
                ],
                limit=5,
                fallback="前瞻压力卡待补。",
            ),
            "250℃蒸汽、45000Pa、轮足、爬楼、飞行等方向都需要先回到价值轴判断，不默认跟随。",
        ],
        evidence_boundary=[
            "证据锚点：future_intelligence_signals.json / dreame_roadmap_timeline.json / roadmap_stress_test_cards.json。",
            "边界：AWE 概念机和追觅路线图不写成确定性上市能力。",
        ],
    )
    render_chapter_triplet(
        lines,
        heading="## 5. 需求池排兵布阵与行动指南",
        report_summary=[
            f"T0 当前收口：{report_join([card.get('theme_name') for card in t0_cards], limit=4, fallback='T0 待补')}",
            "本轮只做 T0/T1/T2/T3 战略落位，不输出 -10 到 +10 的伪 KANO 分数。",
            "行动指南必须让产品、研发、营销能在下一轮评审前签收。",
        ],
        planning_body=[
            report_join(
                [
                    f"{card.get('strategic_priority')} / {card.get('theme_name')}：{card.get('landing_logic')} {card.get('demand_pool_signal')}"
                    for card in demand_cards[:7]  # type: ignore[union-attr]
                ],
                limit=7,
                fallback="需求落位卡待补。",
            ),
            "需求池不是再多一张大表，而是把用户价值、竞争压力和未来压力压成资源优先级。",
        ],
        evidence_boundary=[
            "证据锚点：demand_pool_snapshot.json / roadmap_stress_test_cards.json。",
            "边界：没有明确量化字段时，不生成确定 KANO 分数。",
        ],
    )
    lines.extend(
        [
            "## 6. 5W2H 行动清单",
            "",
            "| 行动 | Why | What | Who | When | How | How Much |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for card in action_cards:  # type: ignore[union-attr]
        lines.append(
            "| "
            + " | ".join(
                [
                    safe_report_text(card.get("action_name")),
                    safe_report_text(card.get("why")),
                    safe_report_text(card.get("what")),
                    safe_report_text(card.get("who")),
                    safe_report_text(card.get("when")),
                    safe_report_text(card.get("how")),
                    safe_report_text(card.get("how_much")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 7. 总证据边界",
            "",
        ]
    )
    for red_line in REPORT_ASSEMBLY_RED_LINES:
        lines.append(f"- {red_line}")
    lines.append("")
    return "\n".join(lines)


def registry_rows_for_scope(
    competition_generation_registry: dict[str, object],
    scope: str,
    *,
    is_self_brand: bool | None = None,
    generation_bucket: str | None = None,
) -> list[dict[str, object]]:
    rows = []
    for row in competition_generation_registry.get("rows", []) or []:
        if str(row.get("competition_scope")) != scope:
            continue
        if is_self_brand is not None and bool(row.get("is_self_brand")) != is_self_brand:
            continue
        if generation_bucket is not None and str(row.get("generation_bucket")) != generation_bucket:
            continue
        rows.append(row)
    return rows


def build_competition_capability_scan(
    truth_conn: sqlite3.Connection,
    competition_generation_registry: dict[str, object],
    competition_voc_xtn_breakdown: dict[str, object],
    awe_exhibition_signals: dict[str, object],
) -> dict[str, object]:
    spec_rows = truth_conn.execute(
        """
        SELECT pm.display_name, pm.self_competitor_type, ps.spec_key, ps.spec_value_text, ps.spec_value_num, ps.unit
        FROM product_master pm
        LEFT JOIN product_spec ps
          ON pm.product_id = ps.product_id
        WHERE pm.self_competitor_type = 'self'
        """
    ).fetchall()
    spec_lookup: dict[str, list[sqlite3.Row]] = {}
    for row in spec_rows:
        spec_lookup.setdefault(str(row["display_name"]), []).append(row)

    top_issue_by_theme: dict[str, list[str]] = defaultdict(list)
    for row in competition_voc_xtn_breakdown.get("level_2_rows", []) or []:
        theme = str(row.get("problem_level_1", "其他"))
        problem = str(row.get("problem_level_2", ""))
        if problem and problem not in top_issue_by_theme[theme]:
            top_issue_by_theme[theme].append(problem)

    capability_specs = [
        ("机身高度", "追觅 / 石头", "当前行业在把超薄机身当成旗舰体验门槛之一。", "智能性"),
        ("越障", "追觅 / 石头 / MOVA", "越障已从宣传参数变成真实家庭复杂场景的体验门槛。", "智能性"),
        ("拖地体系", "追觅 / 萤石 / MOVA", "蒸汽、热水、喷水等方案都在争夺拖地结果解释权。", "清洁"),
        ("免维护", "头部品牌共同把体验闭环做成准入门槛", "免维护已经不是加分项，而是高端产品的准入项。", "维护"),
        ("AI污渍识别 / 主动感知", "AWE 信号更偏方向层", "AI 主动感知正在被讲成下一代能力，但仍需落回真实用户价值。", "智能性"),
        ("基站自清洁", "头部品牌共同抬高基站自维护门槛", "基站自清洁直接决定“解放双手”是否会塌房。", "基站"),
        ("热水洗 / 蒸汽", "追觅 / 萤石 / MOVA", "热水洗与蒸汽在展会上被反复强调，但最终仍要回到清洁结果。", "清洁"),
        ("滚刷 / 边刷防缠", "萤石 / iRobot / 行业全员边刷防缠", "防缠已经被行业视为基础能力，不能再只靠宣称。", "维护"),
    ]

    self_spec_text = " ".join(
        " ".join(str(row[key] or "") for key in ["display_name", "spec_key", "spec_value_text", "spec_value_num", "unit"])
        for row in spec_rows
    )
    registry_blob = " ".join(
        str(item)
        for row in (competition_generation_registry.get("rows", []) or [])
        if bool(row.get("is_self_brand"))
        for item in row.get("product_names", []) or []
    )
    awe_blob = " ".join(
        signal.get("signal_text", "")
        for key in ["industry_capability_signals", "cross_category_signals"]
        for signal in (awe_exhibition_signals.get(key, []) or [])
    )
    rows: list[dict[str, object]] = []
    normalized_blob = normalize_text_local(self_spec_text + " " + registry_blob)
    normalized_awe_blob = normalize_text_local(awe_blob)
    capability_token_map = {
        "机身高度": ["厚度", "超薄", "低空间", "机身高度"],
        "越障": ["越障", "门槛", "台阶", "脱困"],
        "拖地体系": ["滚筒", "热水", "蒸汽", "喷水", "拖地"],
        "免维护": ["免维护", "自维护", "自清洁", "尘袋", "清洁槽"],
        "AI污渍识别 / 主动感知": ["主动", "识别", "ai", "感知", "污渍识别"],
        "基站自清洁": ["基站", "自清洁", "洗拖布", "集尘", "污水箱"],
        "热水洗 / 蒸汽": ["热水", "蒸汽"],
        "滚刷 / 边刷防缠": ["防缠", "滚刷", "边刷", "缠绕"],
    }
    guardrail_dimensions = {"拖地体系", "免维护", "基站自清洁", "滚刷 / 边刷防缠"}
    for capability_dimension, industry_front_runner, why_it_matters, linked_theme in capability_specs:
        tokens = capability_token_map.get(capability_dimension, [])
        has_direct_evidence = any(token in normalized_blob for token in tokens)
        has_awe_support = any(token in normalized_awe_blob for token in tokens)
        if has_direct_evidence and capability_dimension in guardrail_dimensions:
            gap_type = "守住"
        elif has_direct_evidence or has_awe_support:
            gap_type = "跟随"
        else:
            gap_type = "待补充"
        linked_voc_themes = top_issue_by_theme.get(linked_theme, [])[:3]
        if gap_type == "守住":
            ecovacs_status = (
                "当前已经有对应抓手，至少说明这项能力不能缺席；下一步要把它从“有配置”变成“用户能稳定感知到”。"
            )
        elif gap_type == "跟随":
            ecovacs_status = (
                "当前更像跟住了行业门槛，但还没形成一眼能被用户感知的明显领先。"
            )
        else:
            ecovacs_status = "当前结构化证据还不足，只能确认这项能力重要，暂时不能写成科沃斯已经守住。"
        rows.append(
            {
                "capability_dimension": capability_dimension,
                "industry_front_runner": industry_front_runner,
                "ecovacs_status": ecovacs_status,
                "gap_type": gap_type,
                "why_it_matters": why_it_matters,
                "linked_voc_themes": linked_voc_themes,
                "linked_awe_signals": [
                    signal["signal_name"]
                    for signal in (awe_exhibition_signals.get("industry_capability_signals", []) or [])
                    if signal["signal_name"] in why_it_matters or signal["signal_name"] in capability_dimension or signal["signal_name"] in industry_front_runner
                ][:3],
            }
        )
    return {"rows": rows}


def build_competition_matchup_matrix(
    competition_generation_registry: dict[str, object],
    competition_voc_xtn_breakdown: dict[str, object],
    awe_exhibition_signals: dict[str, object],
) -> dict[str, object]:
    product_rows = [
        row
        for row in (competition_voc_xtn_breakdown.get("product_rows", []) or [])
        if str(row.get("match_confidence", "")) in {"high", "medium"}
    ]
    frontline_rows = competition_voc_xtn_breakdown.get("frontline_scope_rows", []) or []
    rows: list[dict[str, object]] = []
    scope_specs = [
        ("X", "X_omni", "高端旗舰"),
        ("T", "T_omni", "主销 omni"),
        ("N", "N_omni", "omni 下探"),
        ("N", "N_aes", "AES 入门带基站"),
        ("N", "N_single", "单机守位"),
    ]
    scope_message_map = {
        "X_omni": (
            "高端旗舰要正面回答“托管承诺能不能兑现”，重点讲少返工、少操心和高端体验闭环。",
            "X 这一带真正对的是旗舰 omni 的高端托管承诺，不是参数表本身。",
            "高端托管 / 体验闭环 / 拖地结果",
        ),
        "T_omni": (
            "主销 omni 重点讲结果稳定、少维护、日常更省心，别把主销带讲散。",
            "T 这一带真正对的是主销 omni 的“省心且做完事”，不是所有高端黑科技。",
            "结果稳定 / 少维护 / 主销成交",
        ),
        "N_omni": (
            "omni 下探带重点讲下探承接位是否完整，别让 X/T 被迫替 N 补位。",
            "N_omni 真正面对的是中高端下探卡位，重点是带宽承接而不是旗舰表达。",
            "下探承接 / 价格带卡位 / 完整带宽",
        ),
        "N_aes": (
            "AES 入门带基站重点讲入门带基站承接是否完整，以及基础结果和维护门槛。",
            "N_aes 真正对的是入门带基站守位战，重点看有没有明确承接位。",
            "入门带基站 / 基础结果 / 维护门槛",
        ),
        "N_single": (
            "低价单机守位重点讲基础完成率和避障底线，别让预算敏感用户先流走。",
            "N_single 真正对的是低价守位，不该再让旗舰或主销替它兜底。",
            "低价守位 / 基础完成率 / 避障底线",
        ),
    }

    def preferred_frontline_row(scope: str) -> dict[str, object] | None:
        scoped_rows = [row for row in frontline_rows if str(row.get("competition_scope")) == scope]
        for mode in ["self_stable", "external_only", "missing"]:
            for market_scope in ["中国", "ALL", "海外"]:
                row = next(
                    (
                        item
                        for item in scoped_rows
                        if str(item.get("market_scope")) == market_scope and str(item.get("frontline_mode", "")) == mode
                    ),
                    None,
                )
                if row:
                    return row
        return None

    for series_family, scope, price_band in scope_specs:
        self_rows = registry_rows_for_scope(competition_generation_registry, scope, is_self_brand=True, generation_bucket="current")
        competitor_rows = registry_rows_for_scope(competition_generation_registry, scope, is_self_brand=False, generation_bucket="current")
        self_name = format_product_examples(
            [name for row in self_rows for name in row.get("product_names", []) or []],
            limit=3,
        )
        scope_products = [
            row
            for row in product_rows
            if str(row.get("competition_scope")) == scope and not bool(row.get("is_self_brand"))
        ]
        scope_products.sort(
            key=lambda row: (
                {"中国": 0, "ALL": 1, "海外": 2, "unknown": 3}.get(str(row.get("market_scope")), 99),
                0 if str(row.get("generation_bucket")) == "current" else 1,
                -int(row.get("message_count", 0)),
                str(row.get("product_name", "")),
            )
        )
        competitor_name = (
            str(scope_products[0].get("product_name", "-"))
            if scope_products
            else format_product_examples(
                [name for row in competitor_rows for name in row.get("product_names", []) or []],
                limit=2,
            )
        )
        top_risk_row = preferred_frontline_row(scope)
        if (
            not top_risk_row
            or str(top_risk_row.get("frontline_mode", "")) != "self_stable"
            or str(top_risk_row.get("top_problem_level_1", "待补充")) == "待补充"
        ):
            voc_risk = "当前该竞争带稳定 VOC 仍待补齐，先不把风险讲满"
        else:
            voc_risk = f"{top_risk_row.get('top_problem_level_1', '待补充')}/{top_risk_row.get('top_problem_level_2', '待补充')}"
        headline_capabilities, why_this_matchup, awe_signal_reference = scope_message_map.get(
            scope,
            ("当前对阵表达仍待补齐。", "当前真正对阵对象仍待补充。", "体验闭环"),
        )
        rows.append(
            {
                "series_family": series_family,
                "competition_scope": competition_scope_label(scope),
                "self_product_name": self_name,
                "competitor_product_name": competitor_name,
                "price_band": price_band,
                "headline_capabilities": headline_capabilities,
                "why_this_matchup": why_this_matchup,
                "voc_risk_to_watch": voc_risk,
                "awe_signal_reference": awe_signal_reference,
            }
        )
    return {"rows": rows}


def build_competition_strategy_bridge(
    competition_voc_xtn_breakdown: dict[str, object],
    competition_capability_scan: dict[str, object],
    competition_matchup_matrix: dict[str, object],
) -> dict[str, object]:
    frontline_rows = competition_voc_xtn_breakdown.get("frontline_scope_rows", []) or []

    def preferred_scope_row(scope: str) -> dict[str, object] | None:
        scoped_rows = [row for row in frontline_rows if str(row.get("competition_scope")) == scope]
        for mode in ["self_stable", "external_only", "missing"]:
            for market_scope in ["中国", "ALL", "海外"]:
                row = next(
                    (
                        item
                        for item in scoped_rows
                        if str(item.get("market_scope")) == market_scope and str(item.get("frontline_mode", "")) == mode
                    ),
                    None,
                )
                if row:
                    return row
        return None

    def defend_statement(scope: str, *, series_family: str) -> str:
        row = preferred_scope_row(scope)
        if not row or str(row.get("frontline_mode", "")) == "missing":
            if scope == "N_omni":
                return "N 的 omni 下探带当前稳定 VOC 仍待补齐，先不把这条带讲满。"
            return f"{series_family} 当前该竞争带稳定 VOC 仍待补齐，先不把这条带讲满。"
        if str(row.get("frontline_mode", "")) == "external_only":
            return (
                f"{series_family} 在 {competition_scope_label(scope)} 上先要承认样本还没补齐；当前竞品池门槛主要落在 "
                f"`{row.get('external_reference_problem_level_1', '待补充')}` / `{row.get('external_reference_problem_level_2', '待补充')}`。"
            )
        if scope == "X_omni":
            return f"X 现在必须守住高端旗舰的托管承诺，尤其别让 `{row.get('top_problem_level_2', '待补充')}` 打穿“少操心、少返工、真托管”的叙事。"
        if scope == "T_omni":
            return f"T 现在必须把主销 omni 的结果稳定讲成默认答案，尤其先收住 `{row.get('top_problem_level_2', '待补充')}` 这类会逼用户返工的问题。"
        if scope == "N_aes":
            return f"N 的 AES 带基站承接位要先补齐，重点防 `{row.get('top_problem_level_2', '待补充')}` 这类会让入门带基站直接失守的问题。"
        if scope == "N_single":
            return f"N 的低价单机守位要守住基础底线，重点防 `{row.get('top_problem_level_2', '待补充')}` 这类预算敏感带的硬伤。"
        return f"N 的 omni 下探位如果要讲满，先得补齐 `{row.get('top_problem_level_2', '待补充')}` 这类最容易被打穿的风险。"

    following = [
        f"{row['capability_dimension']}：当前更像在跟住 `{row['industry_front_runner']}` 设下的门槛。"
        for row in competition_capability_scan.get("rows", []) or []
        if row.get("gap_type") in {"跟随", "待补充"}
    ][:4]
    set_the_bar = []
    for row in competition_matchup_matrix.get("rows", []) or []:
        series_family = str(row.get("series_family", ""))
        if series_family == "X":
            set_the_bar.append("X：旗舰 omni 已经被对手讲成高端托管答案，不能只回到参数解释。")
        elif series_family == "T":
            set_the_bar.append("T：主销 omni 已经在卷结果稳定和少维护，必须正面回答省心感。")
        elif "N_aes" in str(row.get("competition_scope", "")):
            set_the_bar.append("N：AES 入门带基站已经被对手用带宽完整度和基础维护门槛卡位。")
        elif "N_single" in str(row.get("competition_scope", "")):
            set_the_bar.append("N：低价单机守位带已经在卷基础完成率和避障底线。")
        elif "N_omni" in str(row.get("competition_scope", "")):
            set_the_bar.append("N：omni 下探带已经有人在做价格带卡位，不能再长期缺承接位。")
    set_the_bar = dedupe_preserve_order(set_the_bar)[:4]

    priority_gaps: list[str] = []
    for scope in ["X_omni", "T_omni", "N_omni", "N_aes", "N_single"]:
        row = preferred_scope_row(scope)
        if not row:
            continue
        if str(row.get("frontline_mode", "")) == "self_stable":
            priority_gaps.append(
                f"{competition_scope_label(scope)}：`{row.get('top_problem_level_2', '待补充')}` 已经在当前带宽里形成真实风险，必须进入优先级。"
            )
        elif str(row.get("frontline_mode", "")) == "external_only":
            priority_gaps.append(
                f"{competition_scope_label(scope)}：外部门槛主要卡在 `{row.get('external_reference_problem_level_2', '待补充')}`，但科沃斯该带宽稳定样本仍待补齐。"
            )
        else:
            priority_gaps.append(
                f"{competition_scope_label(scope)}：当前稳定 VOC 仍待补齐，先不把这条带讲满。"
            )
    return {
        "what_x_must_defend": defend_statement("X_omni", series_family="X"),
        "what_t_must_defend": defend_statement("T_omni", series_family="T"),
        "what_n_must_defend": "；".join(
            filter(
                None,
                [
                    defend_statement("N_omni", series_family="N"),
                    defend_statement("N_aes", series_family="N"),
                    defend_statement("N_single", series_family="N"),
                ],
            )
        ),
        "where_ecovacs_is_following": following,
        "where_competitors_set_the_bar": set_the_bar,
        "which_voc_gaps_must_enter_priority": priority_gaps,
    }


def build_presentation_page_blocks(
    *,
    x_observed_positionings: dict[str, object],
    generation_comparison: dict[str, object],
    competition_generation_analysis: dict[str, object],
    competition_voc_xtn_breakdown: dict[str, object],
    competition_voc_market_split: dict[str, object],
    awe_exhibition_signals: dict[str, object],
    competition_capability_scan: dict[str, object],
    competition_matchup_matrix: dict[str, object],
    competition_strategy_bridge: dict[str, object],
    self_strategy_thesis: dict[str, object],
    analysis_reflection_report: dict[str, object],
    competition_capture_target_candidates: dict[str, object],
    entry_exposure_tree: dict[str, object],
    voc_fact_exposure_tree: dict[str, object],
    user_insight_exposure_tree: dict[str, object],
    user_strategy_convergence_tree: dict[str, object],
    user_thesis_tree: dict[str, object],
    topic_attention_matrix: dict[str, object],
    problem_drilldown_packages: dict[str, object],
    survey_qual_explanation_map: dict[str, object],
    cross_source_convergence_tree: dict[str, object],
    competition_thesis_tree: dict[str, object],
    self_strategy_thesis_tree: dict[str, object],
    master_judgment_tree: dict[str, object],
    presentation_tree: dict[str, object],
    demand_pool_snapshot: dict[str, object],
    portfolio_generation_strategy: dict[str, object],
    x_positioning_packages: dict[str, object],
    x_positioning_confidence_stats: dict[str, object],
    x_positioning_impact_stats: dict[str, object],
    x_jtbd_confidence_stats: dict[str, object],
    x_jtbd_impact_stats: dict[str, object],
    t_persona_slice_cards: dict[str, object],
    t_difference_matrix: dict[str, object],
    t_jtbd_packages: dict[str, object],
    t_dimension_confidence_stats: dict[str, object],
    t_dimension_impact_stats: dict[str, object],
    t_jtbd_confidence_stats: dict[str, object],
    t_jtbd_impact_stats: dict[str, object],
    brand_mindshare_judgments: dict[str, object],
    idea_cluster_judgments: dict[str, object],
    strategy_translation: dict[str, object],
    cross_source_interpretation: dict[str, object],
    voc_problem_packages: dict[str, object],
    page_metric_cards: dict[str, object],
) -> dict[str, object]:
    x_positioning_rows = x_observed_positionings.get("positionings", []) or []
    generation_rows = {row["series_code"]: row for row in generation_comparison.get("series_rows", []) or []}
    x_packages = x_positioning_packages.get("packages", []) or []
    main_x_packages = [package for package in x_packages if package.get("positioning_level") == "main_positioning"]
    weak_x_packages = [package for package in x_packages if package.get("positioning_level") == "weak_signal"]
    x_conf_lookup = {row["positioning_name"]: row for row in x_positioning_confidence_stats.get("rows", []) or []}
    x_impact_lookup = {row["positioning_name"]: row for row in x_positioning_impact_stats.get("rows", []) or []}
    x_jtbd_conf_lookup = {row["jtbd_name"]: row for row in x_jtbd_confidence_stats.get("rows", []) or []}
    x_jtbd_impact_lookup = {row["jtbd_name"]: row for row in x_jtbd_impact_stats.get("rows", []) or []}
    x_positioning_to_jtbd = {
        "清洁帮手": "地面基础清洁代劳",
        "清洁管家": "整体洁净托管",
        "社交名片": "科技美学表达",
    }
    t_cards = t_persona_slice_cards.get("cards", []) or []
    t_rows = t_difference_matrix.get("rows", []) or []
    t_jtbd_rows = t_jtbd_packages.get("packages", []) or []
    brand_rows = brand_mindshare_judgments.get("judgments", []) or []
    idea_rows = idea_cluster_judgments.get("judgments", []) or []
    dimension_confidence_lookup = {row["concept_id"]: row for row in t_dimension_confidence_stats.get("rows", []) or []}
    dimension_impact_lookup = {row["concept_id"]: row for row in t_dimension_impact_stats.get("rows", []) or []}
    jtbd_confidence_lookup = {row["jtbd_name"]: row for row in t_jtbd_confidence_stats.get("rows", []) or []}
    jtbd_impact_lookup = {row["jtbd_name"]: row for row in t_jtbd_impact_stats.get("rows", []) or []}
    competition_market_summary_lookup = {
        row["market_scope"]: row
        for row in (competition_voc_market_split.get("market_summary_rows", []) or [])
    }
    user_exposure_series_lookup = {
        str(row.get("series_family", "")): row
        for row in (user_insight_exposure_tree.get("series_nodes", []) or [])
    }
    user_stable_nodes = user_insight_exposure_tree.get("stable_nodes", []) or []
    user_drilldown_nodes = user_insight_exposure_tree.get("drilldown_candidate_nodes", []) or []
    user_converged_nodes = user_strategy_convergence_tree.get("converged_nodes", []) or []
    user_not_ready_nodes = user_strategy_convergence_tree.get("not_ready_nodes", []) or []
    user_thesis_rows = user_thesis_tree
    topic_attention_rows = topic_attention_matrix.get("rows", []) or []
    topic_attention_summary_rows = topic_attention_matrix.get("topic_summary_rows", []) or []
    problem_drilldown_rows = problem_drilldown_packages.get("rows", []) or []
    survey_qual_rows = survey_qual_explanation_map.get("rows", []) or []
    survey_qual_topic_rows = survey_qual_explanation_map.get("topic_rows", []) or []
    competition_thesis_nodes = competition_thesis_tree.get("thesis_nodes", []) or []
    self_thesis_nodes = self_strategy_thesis_tree.get("thesis_nodes", []) or []
    voc_external_only_nodes = voc_fact_exposure_tree.get("external_only_nodes", []) or []
    voc_missing_nodes = voc_fact_exposure_tree.get("missing_scope_nodes", []) or []
    presentation_chapter_lookup = {
        str(row.get("chapter_heading", "")): row
        for row in (presentation_tree.get("chapter_nodes", []) or [])
    }
    reflection_priority_pages = analysis_reflection_report.get("rewrite_priority_pages", []) or []
    reflection_next_moves = analysis_reflection_report.get("next_data_moves", []) or []
    awe_competitor_labels = "、".join(
        signal.get("brand", "-")
        for signal in (awe_exhibition_signals.get("direct_competitor_signals", []) or [])[:4]
    )

    def persona_line(user: dict[str, object]) -> str:
        return str(user.get("persona_summary", user.get("case_title", "-")))

    def user_title(user: dict[str, object]) -> str:
        return str(user.get("case_title", "-"))

    def x_alignment(case_titles: list[str]) -> tuple[list[str], list[str]]:
        brands = [
            row["brand"]
            for row in brand_rows
            if set(row.get("who_chooses", [])).intersection(case_titles)
        ]
        ideas = [
            row["theme"]
            for row in idea_rows
            if set(row.get("who_needs_it", [])).intersection(case_titles)
        ]
        return dedupe_preserve_order(brands)[:3], dedupe_preserve_order(ideas)[:3]

    def package_label(package: dict[str, object]) -> str:
        return f"{package['positioning_name']}（弱信号）" if package.get("positioning_level") == "weak_signal" else str(package["positioning_name"])

    def package_jtbd(package: dict[str, object]) -> str:
        anchor = str(package.get("canonical_anchor", package.get("positioning_name", "")))
        fallback = x_positioning_to_jtbd.get(anchor, "地面基础清洁代劳")
        current = str(package.get("jtbd", fallback))
        return current if current in x_jtbd_conf_lookup else fallback

    def package_by_anchor(anchor: str) -> dict[str, object] | None:
        for package in main_x_packages:
            if package.get("canonical_anchor") == anchor:
                return package
        return None

    def compare_default(anchor: str, dimension: str) -> str:
        defaults = {
            "清洁帮手": {
                "机器角色": "先把大面的基础清洁做完，别再额外添乱。",
                "清洁边界": "大面干净、基础覆盖到位即可，边角和局部补尾可以接受。",
                "人工介入默认": "默认自己会收尾，但不接受机器制造新的维护工作。",
                "购买时最在意": "解放双手、少维护、80% 够用。",
                "不能接受": "机器脏、乱、卡、难打理，反而把人重新拉回去。",
                "产品该怎么讲": "别添乱、少维护、基础代劳。",
            },
            "清洁管家": {
                "机器角色": "最好像一个低介入托管者，能主动补位、少返工、少操心。",
                "清洁边界": "不只是做完大面，还要关键区域稳定、过程少救场。",
                "人工介入默认": "不想临时解救、补救和频繁维护，希望机器自己扛住。",
                "购买时最在意": "真托管、免维护、少返工、主动补位。",
                "不能接受": "承诺解放双手，结果却要自己反复清理基站、处理异味和返工。",
                "产品该怎么讲": "少操心、少返工、真自净、主动补位。",
            },
        }
        return defaults.get(anchor, {}).get(dimension, "-")

    def package_compare_text(package: dict[str, object] | None, dimension: str) -> str:
        if not package:
            return "-"
        anchor = str(package.get("canonical_anchor", ""))
        if dimension == "机器角色":
            return str(package.get("one_line_definition", compare_default(anchor, dimension)))
        if dimension == "清洁边界":
            return "；".join(package.get("attitude_pattern", [])[:1]) or compare_default(anchor, dimension)
        if dimension == "人工介入默认":
            return str(package.get("why_not_other_two", compare_default(anchor, dimension)))
        if dimension == "购买时最在意":
            return "；".join(package.get("buying_logic", [])[:1]) or compare_default(anchor, dimension)
        if dimension == "不能接受":
            return "；".join(package.get("pain_need", [])[:1]) or compare_default(anchor, dimension)
        if dimension == "产品该怎么讲":
            return compare_default(anchor, dimension)
        if dimension == "成立度 / 影响力":
            return f"{x_conf_lookup.get(package['positioning_name'], {}).get('confidence_level', '-')} / {x_impact_lookup.get(package['positioning_name'], {}).get('impact_level', '-')}"
        return compare_default(anchor, dimension)

    def series_child_node(series_family: str, child_label: str) -> dict[str, object] | None:
        series_node = user_exposure_series_lookup.get(series_family, {})
        return next(
            (
                child
                for child in (series_node.get("children", []) or [])
                if str(child.get("node_label", "")) == child_label
            ),
            None,
        )

    def select_topic_rows_for_series(series_family: str, limit: int | None = 4, user_band: str | None = None) -> list[dict[str, object]]:
        rows = [
            row
            for row in topic_attention_summary_rows
            if row.get("series_family") == series_family
            and row.get("cohort_scope") == "科沃斯样本"
            and (user_band is None or row.get("user_band") == user_band)
        ]
        rows.sort(key=lambda row: (row.get("market_scope") != "中国", -int(row.get("mention_count", 0)), str(row.get("topic_name", ""))))
        chosen: list[dict[str, object]] = []
        seen_topics: set[str] = set()
        negative_first = [
            row for row in rows
            if int(row.get("negative_count", 0)) > int(row.get("positive_count", 0))
        ][:2]
        positive_focus = [
            row for row in rows
            if int(row.get("positive_count", 0)) >= int(row.get("negative_count", 0))
        ][:2]
        for row in negative_first + positive_focus + rows:
            topic_name = str(row.get("topic_name", ""))
            if topic_name in seen_topics:
                continue
            chosen.append(row)
            seen_topics.add(topic_name)
            if limit is not None and len(chosen) >= limit:
                break
        return chosen

    def select_drilldown_rows_for_series(series_family: str, limit: int | None = 3, user_band: str | None = None) -> list[dict[str, object]]:
        rows = [
            row
            for row in problem_drilldown_rows
            if row.get("series_family") == series_family
            and (user_band is None or row.get("user_band") == user_band)
            and row.get("cohort_scope") == "科沃斯样本"
            and row.get("market_scope") in {"中国", "ALL"}
        ]
        rows.sort(key=lambda row: (row.get("market_scope") != "中国", -int(row.get("mention_count", 0)), str(row.get("problem_name", ""))))
        chosen: list[dict[str, object]] = []
        seen_problems: set[str] = set()
        negative_first = [
            row for row in rows
            if int(row.get("negative_count", 0)) > int(row.get("positive_count", 0))
        ][:2]
        positive_focus = [
            row for row in rows
            if int(row.get("positive_count", 0)) >= int(row.get("negative_count", 0))
        ][:2]
        for row in negative_first + positive_focus + rows:
            problem_name = str(row.get("problem_name", ""))
            if problem_name in seen_problems:
                continue
            chosen.append(row)
            seen_problems.add(problem_name)
            if limit is not None and len(chosen) >= limit:
                break
        return chosen

    def top_positive_rows_for_series(series_family: str, limit: int = 2, user_band: str | None = None) -> list[dict[str, object]]:
        rows = [
            row
            for row in topic_attention_summary_rows
            if row.get("series_family") == series_family
            and row.get("cohort_scope") == "科沃斯样本"
            and (user_band is None or row.get("user_band") == user_band)
            and int(row.get("positive_count", 0)) >= int(row.get("negative_count", 0))
        ]
        rows.sort(key=lambda row: (row.get("market_scope") != "中国", -int(row.get("positive_count", 0)), -int(row.get("mention_count", 0)), str(row.get("topic_name", ""))))
        return rows[:limit]

    def top_negative_rows_for_series(series_family: str, limit: int = 2, user_band: str | None = None) -> list[dict[str, object]]:
        rows = [
            row
            for row in topic_attention_summary_rows
            if row.get("series_family") == series_family
            and row.get("cohort_scope") == "科沃斯样本"
            and (user_band is None or row.get("user_band") == user_band)
            and int(row.get("negative_count", 0)) > int(row.get("positive_count", 0))
        ]
        rows.sort(key=lambda row: (row.get("market_scope") != "中国", -int(row.get("negative_count", 0)), -int(row.get("mention_count", 0)), str(row.get("topic_name", ""))))
        return rows[:limit]

    def top_attention_rows_for_series(series_family: str, limit: int = 2, user_band: str | None = None) -> list[dict[str, object]]:
        rows = [
            row
            for row in topic_attention_summary_rows
            if row.get("series_family") == series_family
            and row.get("cohort_scope") == "科沃斯样本"
            and (user_band is None or row.get("user_band") == user_band)
        ]
        rows.sort(key=lambda row: (row.get("market_scope") != "中国", -int(row.get("mention_count", 0)), -int(row.get("positive_count", 0)), str(row.get("topic_name", ""))))
        return rows[:limit]

    def summarize_focus_rows(rows: list[dict[str, object]], *, include_rate: bool = False) -> str:
        if not rows:
            return "-"
        if include_rate:
            return "；".join(
                f"{row.get('topic_name', '-')}{int(row.get('mention_count', 0))}例/{float(row.get('mention_rate', 0.0)):.1%}"
                for row in rows[:2]
            )
        return _tree_join([row.get("topic_name", "-") for row in rows], 2)

    def format_attention_market_scope(row: dict[str, object] | None) -> str:
        if not row:
            return "-"
        market_scope = str(row.get("market_scope", "-"))
        return f"科沃斯样本（{market_scope}）" if market_scope and market_scope != "-" else "科沃斯样本"

    def overview_attention_rows() -> list[list[object]]:
        output: list[list[object]] = []
        band_specs = [
            ("X", "X", None),
            ("T", "T", None),
            ("N_single", "N", "N_single"),
            ("N_aes", "N", "N_aes"),
        ]
        for display_label, series_family, user_band in band_specs:
            negative_row = next(iter(top_negative_rows_for_series(series_family, 1, user_band)), None)
            positive_row = next(iter(top_positive_rows_for_series(series_family, 1, user_band)), None)
            if negative_row:
                output.append(
                    [
                        display_label,
                        "负向焦点",
                        negative_row.get("topic_name", "-"),
                        format_attention_market_scope(negative_row),
                        negative_row.get("mention_count", 0),
                        f"{float(negative_row.get('mention_rate', 0.0)):.1%}",
                        f"{float(negative_row.get('positive_rate', 0.0)):.1%}",
                        f"{float(negative_row.get('negative_rate', 0.0)):.1%}",
                        f"{negative_row.get('net_sentiment_signal', '-')}：当前最伤的就是这条主题。",
                    ]
                )
            if positive_row:
                output.append(
                    [
                        display_label,
                        "正向锚点",
                        positive_row.get("topic_name", "-"),
                        format_attention_market_scope(positive_row),
                        positive_row.get("mention_count", 0),
                        f"{float(positive_row.get('mention_rate', 0.0)):.1%}",
                        f"{float(positive_row.get('positive_rate', 0.0)):.1%}",
                        f"{float(positive_row.get('negative_rate', 0.0)):.1%}",
                        f"{positive_row.get('net_sentiment_signal', '-')}：当前这条主题已经能当正向锚点。",
                    ]
                )
        output.append(
            [
                "N_omni",
                "边界声明",
                "当前仍缺稳定自家 VOC 样本",
                "-",
                "-",
                "-",
                "-",
                "-",
                "当前只能讲边界与补数方向，不能伪造主题判断。",
            ]
        )
        return output

    def build_attention_band_card(title: str, series_family: str, user_band: str | None = None) -> dict[str, object]:
        negative_row = next(iter(top_negative_rows_for_series(series_family, 1, user_band)), None)
        positive_row = next(iter(top_positive_rows_for_series(series_family, 1, user_band)), None)
        if user_band == "N_omni":
            return {
                "title": title,
                "lead_judgment": "当前仍缺稳定自家 VOC 样本，只能保留边界与补数方向。",
                "bullets": [
                    "当前边界：还没有稳定自家 VOC 用户样本，不能正式讲负向焦点或正向锚点。",
                    "下一步补数：优先补 T50 / 帕斯卡 等真实用户反馈入口。",
                    "当前市场边界：中国 / ALL 都不能讲满。",
                ],
                "representative_quotes": [
                    "边界声明：当前仍缺稳定自家 VOC 样本。",
                    "补数方向：优先补真实用户入口。",
                ],
            }
        bullets = []
        if negative_row:
            bullets.append(
                f"当前负向焦点：{negative_row.get('topic_name', '-')}，{int(negative_row.get('mention_count', 0))}例/{float(negative_row.get('mention_rate', 0.0)):.1%}，负评率 {float(negative_row.get('negative_rate', 0.0)):.1%}。"
            )
        if positive_row:
            bullets.append(
                f"当前正向锚点：{positive_row.get('topic_name', '-')}，{int(positive_row.get('mention_count', 0))}例/{float(positive_row.get('mention_rate', 0.0)):.1%}，正评率 {float(positive_row.get('positive_rate', 0.0)):.1%}。"
            )
        if user_band == "N_aes":
            bullets.append("当前市场边界：稳定自家信号主要来自海外/ALL，中国区仍缺自家稳定样本。")
        else:
            bullets.append("当前市场边界：优先读中国稳定样本，再看 ALL / 海外补充。")
        if negative_row and positive_row:
            lead = f"当前最伤的是 `{negative_row.get('topic_name', '-')}`，最稳的是 `{positive_row.get('topic_name', '-')}`。"
        elif negative_row:
            lead = f"当前最伤的是 `{negative_row.get('topic_name', '-')}`。"
        elif positive_row:
            lead = f"当前最稳的是 `{positive_row.get('topic_name', '-')}`。"
        else:
            lead = "当前这一带的判断仍待补充。"
        return {
            "title": title,
            "lead_judgment": lead,
            "bullets": bullets,
            "representative_quotes": [
                f"负向焦点：{negative_row.get('topic_name', '-')}" if negative_row else "负向焦点：待补充",
                f"正向锚点：{positive_row.get('topic_name', '-')}" if positive_row else "正向锚点：待补充",
            ],
        }

    def select_explanation_topic_rows_for_series(series_family: str) -> list[dict[str, object]]:
        rows = [
            row
            for row in survey_qual_topic_rows
            if row.get("series_family") == series_family
        ]
        rows.sort(
            key=lambda row: (
                row.get("evidence_status") != "stable",
                -len(row.get("high_sensitivity_personas", []) or []),
                str(row.get("topic_name", "")),
            )
        )
        return rows

    def build_n_explanation_rows(user_band: str | None = None) -> list[list[str]]:
        rows = [
            row
            for row in survey_qual_topic_rows
            if row.get("series_family") == "N"
            and (user_band is None or row.get("user_band") == user_band)
        ]
        rows.sort(
            key=lambda row: (
                N_USER_BAND_MARKET_PRIORITY.get(str(row.get("user_band", "")), ["中国", "ALL", "海外"]).index(str(row.get("market_scope", "")))
                if str(row.get("market_scope", "")) in N_USER_BAND_MARKET_PRIORITY.get(str(row.get("user_band", "")), ["中国", "ALL", "海外"])
                else 99,
                str(row.get("evidence_status", "")) != "voc_only",
                str(row.get("topic_name", "")),
            )
        )
        output: list[list[str]] = []
        for row in rows[:8]:
            explanation_mode = str(row.get("explanation_mode", "voc_only"))
            output.append(
                [
                    str(row.get("topic_name", "-")),
                    "VOC-only边界" if explanation_mode == "boundary" else "VOC-only",
                    str(row.get("why_this_topic_is_sensitive", "当前只能先给带宽级方向性解释。")),
                    _tree_join(row.get("over_expected_patterns", []) or row.get("result_baseline_patterns", []) or [], 2),
                    "当前暂无 N 的问卷/定性直连输入，只能先给带宽级方向性解释。"
                    if explanation_mode != "boundary"
                    else "当前暂无 N_omni 的问卷/定性直连输入，也没有稳定自家 VOC 用户样本。",
                    str(row.get("market_scope", "-")),
                ]
            )
        return output

    selected_topic_rows = overview_attention_rows()
    selected_drilldown_rows = select_drilldown_rows_for_series("X", 3) + select_drilldown_rows_for_series("T", 3)

    main_labels = [str(package["positioning_name"]) for package in main_x_packages]
    weak_labels = [str(package["positioning_name"]) for package in weak_x_packages]
    if main_labels and weak_labels:
        x_lead = f"X 系列当前更稳定长出了 `{ ' / '.join(main_labels) }` 两类主定位；`{weak_labels[0]}` 这类表达型动机存在，但当前更像弱信号。"
    elif main_labels:
        x_lead = f"X 系列当前更稳定长出的主定位是 `{ ' / '.join(main_labels) }`，说明用户判断首先沿着家务代劳和低介入托管分化。"
    else:
        x_lead = "X 系列当前仍在从数据里长出角色定位，但已经能看到基础代劳和低介入托管两条不同判断。"

    blocks = [
        {
            "page_id": "user_exposure_tree_pages",
            "heading": "### 1.0 用户暴露树：先把稳定特征、弱信号和边界摊开",
            "page_question": "在看用户这一层，当前最值得先暴露的稳定特征、弱信号和边界是什么？",
            "lead_judgment": str(user_insight_exposure_tree.get("summary_judgment", "看用户这一层的暴露树仍待补充。")),
            "supporting_table": {
                "headers": ["系列", "当前稳定暴露", "弱信号 / 空位", "为什么先不升级成主命题"],
                "rows": [
                    [
                        "X",
                        _tree_join([child.get("node_label", "-") for child in user_exposure_series_lookup.get("X", {}).get("children", []) if not child.get("is_weak_signal")], 3),
                        _tree_join([child.get("node_label", "-") for child in user_exposure_series_lookup.get("X", {}).get("children", []) if child.get("is_weak_signal")], 2),
                        "X 先暴露角色定位分化，表达型角色当前仍只适合作为弱信号。",
                    ],
                    [
                        "T",
                        _tree_join([child.get("node_label", "-") for child in user_exposure_series_lookup.get("T", {}).get("children", []) if not child.get("is_weak_signal")], 3),
                        _tree_join([child.get("summary", "-") for child in user_exposure_series_lookup.get("T", {}).get("children", []) if child.get("is_weak_signal")], 1),
                        "T 先暴露人生位置、差异维度和 JTBD，当前无稳定弱信号，不硬补方向。",
                    ],
                    [
                        "N_single",
                        str((series_child_node("N", "N_single") or {}).get("summary", "-")),
                        "-",
                        "N_single 当前按预算守位带暴露，先讲守位底线与基础优势，不伪造人格层解释。",
                    ],
                    [
                        "N_aes",
                        str((series_child_node("N", "N_aes") or {}).get("summary", "-")),
                        "中国区仍缺自家稳定样本",
                        "N_aes 当前按海外/ALL 的 VOC-only 承接位暴露，不能把海外信号偷渡成中国判断。",
                    ],
                    [
                        "N_omni",
                        str((series_child_node("N", "N_omni") or {}).get("summary", "-")),
                        "当前缺稳定自家 VOC 样本",
                        "N_omni 当前只保留边界和补数方向，不做伪主题和伪解释展开。",
                    ],
                ],
            },
            "detail_cards": [
                {
                    "title": f"{series_node.get('series_family', '-')} 暴露层",
                    "lead_judgment": series_node.get("lead_judgment", "-"),
                    "bullets": [
                        f"{child.get('node_label', '-')}: {child.get('summary', '-')}"
                        for child in (series_node.get("children", []) or [])[:5]
                    ],
                    "representative_quotes": [
                        _tree_join(child.get("evidence_refs", []) or [], 2)
                        for child in (series_node.get("children", []) or [])[:2]
                    ],
                }
                for series_node in (user_insight_exposure_tree.get("series_nodes", []) or [])
            ],
            "closing_implication": "先把稳定特征、弱信号和边界暴露完整，后面才能知道哪些真的值得往上收敛，哪些现在只能保留为空位和方向。",
        },
        {
            "page_id": "user_topic_attention_pages",
            "heading": "### 1.0A 用户核心关注点：先看用户到底在提什么、夸什么、骂什么",
            "page_question": "当前最核心的用户关注点到底是什么，科沃斯和竞品在这些主题上的正负结构分别怎样？",
            "lead_judgment": "看用户不能只看负评问题包，还要先看哪些主题本身就是高关注点，以及这些关注点里正负评价结构到底怎样。",
            "supporting_table": {
                "headers": ["系列/带宽", "观察角色", "核心主题", "样本池", "提及数", "提及率", "正评率", "负评率", "当前判断"],
                "rows": selected_topic_rows,
            },
            "detail_cards": [
                build_attention_band_card("X", "X"),
                build_attention_band_card("T", "T"),
                build_attention_band_card("N_single", "N", "N_single"),
                build_attention_band_card("N_aes", "N", "N_aes"),
                build_attention_band_card("N_omni", "N", "N_omni"),
            ],
            "closing_implication": "只有先看清‘用户到底在关注什么’，后面的问题下钻才不会只剩负面抱怨清单。",
        },
        {
            "page_id": "user_topic_attention_x_pages",
            "heading": "#### X 主题组：全主题展开",
            "page_question": "X 当前所有高相关主题里，哪些是负向焦点，哪些已经形成正向优势？",
            "lead_judgment": "X 的主题页不再只看少数精选问题，而是把当前已出现的全部高相关主题按正负结构展开。",
            "supporting_table": {
                "headers": ["主题", "提及数", "提及率", "正评率", "负评率", "当前判断"],
                "rows": [
                    [
                        row.get("topic_name", "-"),
                        row.get("mention_count", 0),
                        f"{float(row.get('mention_rate', 0.0)):.1%}",
                        f"{float(row.get('positive_rate', 0.0)):.1%}",
                        f"{float(row.get('negative_rate', 0.0)):.1%}",
                        row.get("net_sentiment_signal", "-"),
                    ]
                    for row in select_topic_rows_for_series("X", None)
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                f"{row.get('topic_name', '-')}: {row.get('net_sentiment_signal', '-')}"
                for row in select_topic_rows_for_series("X", None)[:6]
            ],
            "closing_implication": "X 的用户主题页要先把全量主题摊开，再判断哪些是真正的旗舰底线、哪些是高端加分项。",
        },
        {
            "page_id": "user_topic_attention_t_pages",
            "heading": "#### T 主题组：全主题展开",
            "page_question": "T 当前所有高相关主题里，哪些是负向焦点，哪些已经形成正向优势？",
            "lead_judgment": "T 的主题页不再只看少数精选问题，而是把当前已出现的全部高相关主题按正负结构展开。",
            "supporting_table": {
                "headers": ["主题", "提及数", "提及率", "正评率", "负评率", "当前判断"],
                "rows": [
                    [
                        row.get("topic_name", "-"),
                        row.get("mention_count", 0),
                        f"{float(row.get('mention_rate', 0.0)):.1%}",
                        f"{float(row.get('positive_rate', 0.0)):.1%}",
                        f"{float(row.get('negative_rate', 0.0)):.1%}",
                        row.get("net_sentiment_signal", "-"),
                    ]
                    for row in select_topic_rows_for_series("T", None)
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                f"{row.get('topic_name', '-')}: {row.get('net_sentiment_signal', '-')}"
                for row in select_topic_rows_for_series("T", None)[:6]
            ],
            "closing_implication": "T 的用户主题页要先看主销带到底在被什么主题拉扯，再决定哪些主题进主命题、哪些只留为解释层。",
        },
        {
            "page_id": "user_topic_attention_n_single_pages",
            "heading": "#### N_single 主题组：VOC-only 全主题展开",
            "page_question": "N_single 当前用户带在 VOC 侧到底在被哪些主题拉扯？",
            "lead_judgment": str(user_thesis_rows.get("n_band_theses", {}).get("N_single", "N_single 当前更像预算守位带，先看守位底线被什么主题打穿。")),
            "supporting_table": {
                "headers": ["主题", "提及数", "提及率", "正评率", "负评率", "当前判断", "市场"],
                "rows": [
                    [
                        row.get("topic_name", "-"),
                        row.get("mention_count", 0),
                        f"{float(row.get('mention_rate', 0.0)):.1%}",
                        f"{float(row.get('positive_rate', 0.0)):.1%}",
                        f"{float(row.get('negative_rate', 0.0)):.1%}",
                        row.get("net_sentiment_signal", "-"),
                        row.get("market_scope", "-"),
                    ]
                    for row in select_topic_rows_for_series("N", None, "N_single")
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                f"{row.get('topic_name', '-')}: {row.get('net_sentiment_signal', '-')}"
                for row in select_topic_rows_for_series("N", None, "N_single")[:6]
            ],
            "closing_implication": "N_single 的主题页要服务预算守位判断，而不是被总 N 口径吃掉。",
        },
        {
            "page_id": "user_topic_attention_n_aes_pages",
            "heading": "#### N_aes 主题组：VOC-only 全主题展开",
            "page_question": "N_aes 当前用户带在 VOC 侧到底在被哪些主题拉扯？",
            "lead_judgment": str(user_thesis_rows.get("n_band_theses", {}).get("N_aes", "N_aes 当前已能看见带宽级 VOC，但还主要停在海外/ALL 口径。")),
            "supporting_table": {
                "headers": ["主题", "提及数", "提及率", "正评率", "负评率", "当前判断", "市场"],
                "rows": [
                    [
                        row.get("topic_name", "-"),
                        row.get("mention_count", 0),
                        f"{float(row.get('mention_rate', 0.0)):.1%}",
                        f"{float(row.get('positive_rate', 0.0)):.1%}",
                        f"{float(row.get('negative_rate', 0.0)):.1%}",
                        row.get("net_sentiment_signal", "-"),
                        row.get("market_scope", "-"),
                    ]
                    for row in select_topic_rows_for_series("N", None, "N_aes")
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                f"{row.get('topic_name', '-')}: {row.get('net_sentiment_signal', '-')}"
                for row in select_topic_rows_for_series("N", None, "N_aes")[:6]
            ],
            "closing_implication": "N_aes 的主题页要明确展示：当前已有 VOC 用户信号，但市场口径和解释层仍不完整。",
        },
        {
            "page_id": "user_topic_attention_n_omni_pages",
            "heading": "#### N_omni 主题组：当前先保留边界",
            "page_question": "N_omni 当前能不能像其他带宽一样正式展开主题页？",
            "lead_judgment": str(user_thesis_rows.get("n_band_theses", {}).get("N_omni", "N_omni 当前仍缺稳定自家 VOC 用户样本，只能先保留边界。")),
            "supporting_table": {
                "headers": ["带宽", "当前状态", "为什么不能讲满", "下一步补什么"],
                "rows": [[
                    "N_omni",
                    "VOC-only 边界",
                    "当前仍缺稳定自家 VOC 样本，不能正式展开主题页。",
                    "优先补 T50 / 帕斯卡 等真实用户反馈入口。",
                ]],
            },
            "representative_cases": [],
            "representative_quotes": ["当前仍缺稳定自家 VOC 用户样本。"],
            "closing_implication": "N_omni 的用户页当前不做伪展开，先把边界讲清。",
        },
        {
            "page_id": "user_problem_drilldown_pages",
            "heading": "### 1.0B 问题下钻：把主题继续拆成类型、场景、工况和效果期待",
            "page_question": "像污渍、边角、避障这类核心问题，用户到底是在什么具体情境下提出、期待什么效果？",
            "lead_judgment": "问题下钻的目的不是再换一种标签，而是把问题拆成‘类型 / 场景 / 工况 / 效果期待’，看清正向样本和负向样本到底长什么样。",
            "supporting_table": {
                "headers": ["问题", "样本池", "主类型", "主场景", "主工况", "主要效果期待", "下一步该先钻哪里"],
                "rows": [
                    [
                        row.get("problem_name", "-"),
                        row.get("cohort_scope", "-"),
                        summarize_breakdown_rows(row.get("type_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("scene_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("working_condition_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("effect_expectation_breakdown", []) or [], limit=2),
                        row.get("next_drilldown_axis", "-"),
                    ]
                    for row in selected_drilldown_rows
                ],
            },
            "detail_cards": [
                {
                    "title": f"{row.get('series_family', '-')} / {row.get('problem_name', '-')}",
                    "lead_judgment": row.get("reasonableness_judgment", "-"),
                    "bullets": [
                        f"正向画像：{row.get('positive_profile_summary', '-')}",
                        f"负向画像：{row.get('negative_profile_summary', '-')}",
                        f"反例 / 正向对照：{_tree_join(row.get('counter_examples', []) or [], 2)}",
                    ],
                    "representative_quotes": [
                        f"类型：{summarize_breakdown_rows(row.get('type_breakdown', []) or [], limit=2)}",
                        f"场景：{summarize_breakdown_rows(row.get('scene_breakdown', []) or [], limit=2)}",
                    ],
                }
                for row in selected_drilldown_rows[:4]
            ],
            "closing_implication": "只有把问题拆到足够细，我们后面讲‘为什么用户这么判断’时才不会停在空泛的顶层词上。",
        },
        {
            "page_id": "user_problem_drilldown_x_pages",
            "heading": "#### X 下钻组：按主题逐条展开",
            "page_question": "X 每个高相关主题继续往下钻时，最该优先看什么？",
            "lead_judgment": "X 的问题下钻页要逐条回答：当前问题类型是什么、场景是什么、工况是什么、用户真正期待什么效果。",
            "supporting_table": {
                "headers": ["主题", "主类型", "主场景", "主工况", "主要效果期待", "下一钻方向"],
                "rows": [
                    [
                        row.get("problem_name", "-"),
                        summarize_breakdown_rows(row.get("type_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("scene_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("working_condition_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("effect_expectation_breakdown", []) or [], limit=2),
                        row.get("next_drilldown_axis", "-"),
                    ]
                    for row in select_drilldown_rows_for_series("X", None)
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                row.get("reasonableness_judgment", "-")
                for row in select_drilldown_rows_for_series("X", None)[:6]
            ],
            "closing_implication": "X 的问题下钻页要把旗舰判断真正拆开，而不是只停在‘这类问题存在’。",
        },
        {
            "page_id": "user_problem_drilldown_t_pages",
            "heading": "#### T 下钻组：按主题逐条展开",
            "page_question": "T 每个高相关主题继续往下钻时，最该优先看什么？",
            "lead_judgment": "T 的问题下钻页要逐条回答：主销带到底在哪些主题上已经稳、在哪些主题上仍会被判失败。",
            "supporting_table": {
                "headers": ["主题", "主类型", "主场景", "主工况", "主要效果期待", "下一钻方向"],
                "rows": [
                    [
                        row.get("problem_name", "-"),
                        summarize_breakdown_rows(row.get("type_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("scene_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("working_condition_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("effect_expectation_breakdown", []) or [], limit=2),
                        row.get("next_drilldown_axis", "-"),
                    ]
                    for row in select_drilldown_rows_for_series("T", None)
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                row.get("reasonableness_judgment", "-")
                for row in select_drilldown_rows_for_series("T", None)[:6]
            ],
            "closing_implication": "T 的问题下钻页要把主销带的主题张力讲透，而不是继续靠一两个代表主题代替全部判断。",
        },
        {
            "page_id": "user_problem_drilldown_n_single_pages",
            "heading": "#### N_single 下钻组：VOC-only 按主题逐条展开",
            "page_question": "N_single 当前最该沿哪些主题继续下钻？",
            "lead_judgment": "N_single 的问题下钻先看预算守位带被什么主题打穿，以及这些主题的正向底线是否已经形成。",
            "supporting_table": {
                "headers": ["主题", "主类型", "主场景", "主工况", "主要效果期待", "下一钻方向", "市场"],
                "rows": [
                    [
                        row.get("problem_name", "-"),
                        summarize_breakdown_rows(row.get("type_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("scene_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("working_condition_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("effect_expectation_breakdown", []) or [], limit=2),
                        row.get("next_drilldown_axis", "-"),
                        row.get("market_scope", "-"),
                    ]
                    for row in select_drilldown_rows_for_series("N", None, "N_single")
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                row.get("reasonableness_judgment", "-")
                for row in select_drilldown_rows_for_series("N", None, "N_single")[:6]
            ],
            "closing_implication": "N_single 的下钻页要服务守位逻辑，而不是被总 N 稀释。",
        },
        {
            "page_id": "user_problem_drilldown_n_aes_pages",
            "heading": "#### N_aes 下钻组：VOC-only 按主题逐条展开",
            "page_question": "N_aes 当前最该沿哪些主题继续下钻？",
            "lead_judgment": "N_aes 的问题下钻先看入门带基站当前在 VOC 上暴露的风险与正向信号，但不越过市场边界去讲满中国区。",
            "supporting_table": {
                "headers": ["主题", "主类型", "主场景", "主工况", "主要效果期待", "下一钻方向", "市场"],
                "rows": [
                    [
                        row.get("problem_name", "-"),
                        summarize_breakdown_rows(row.get("type_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("scene_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("working_condition_breakdown", []) or [], limit=2),
                        summarize_breakdown_rows(row.get("effect_expectation_breakdown", []) or [], limit=2),
                        row.get("next_drilldown_axis", "-"),
                        row.get("market_scope", "-"),
                    ]
                    for row in select_drilldown_rows_for_series("N", None, "N_aes")
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                row.get("reasonableness_judgment", "-")
                for row in select_drilldown_rows_for_series("N", None, "N_aes")[:6]
            ],
            "closing_implication": "N_aes 的下钻页要服务入门带基站判断，并显式保留中国区补数边界。",
        },
        {
            "page_id": "user_problem_drilldown_n_omni_pages",
            "heading": "#### N_omni 下钻组：当前先保留边界",
            "page_question": "N_omni 当前能不能像其他带宽一样正式下钻？",
            "lead_judgment": "N_omni 当前仍缺稳定自家 VOC 用户样本，因此下钻层先不伪造，只保留边界和补数方向。",
            "supporting_table": {
                "headers": ["带宽", "当前状态", "为什么不能讲满", "下一步补什么"],
                "rows": [[
                    "N_omni",
                    "VOC-only 边界",
                    "当前缺稳定自家样本，不能输出类型/场景/效果期待的正式下钻。",
                    "优先补 T50 OMNI / T50S OMNI / 帕斯卡 等真实用户入口。",
                ]],
            },
            "representative_cases": [],
            "representative_quotes": ["当前缺稳定自家 VOC 用户样本。"],
            "closing_implication": "N_omni 当前先把边界讲清楚，不做伪下钻。",
        },
        {
            "page_id": "survey_qual_explanation_pages",
            "heading": "### 1.0C 问卷 / 定性解释：哪些人更敏感，他们到底怎么定义失败",
            "page_question": "用户为什么会对同一个问题给出不同判断，哪些是高敏感人群，哪些是可接受边界？",
            "lead_judgment": "问卷和定性的作用，不是再复述用户是谁，而是解释‘谁更敏感、为什么更敏感、他怎么定义失败、结果底线在哪里’。",
            "supporting_table": {
                "headers": ["人群/人格", "更敏感的问题", "为什么更敏感", "失败定义", "结果底线"],
                "rows": [
                    [
                        row.get("segment_or_persona", "-"),
                        _tree_join(row.get("sensitive_problems", []) or [], 2),
                        row.get("why_sensitive", "-"),
                        row.get("failure_definition", "-"),
                        row.get("result_baseline", "-"),
                    ]
                    for row in survey_qual_rows[:8]
                ],
            },
            "representative_cases": [str(row.get("segment_or_persona", "-")) for row in survey_qual_rows[:4]],
            "representative_quotes": [_tree_join(row.get("evidence_refs", []) or [], 2) for row in survey_qual_rows[:4]],
            "closing_implication": "这层如果不做，前台就会只剩‘什么问题高频’，看不到‘谁会因为这个问题立刻判定产品失败’。",
        },
        {
            "page_id": "survey_qual_explanation_x_pages",
            "heading": "#### X 解释组：全主题解释",
            "page_question": "X 每个主题为什么会敏感，谁会因为这个主题立刻判定失败？",
            "lead_judgment": "X 的解释层不再只围绕少数人格，而是尽量为每个已出现主题挂上‘谁更敏感 / 为什么敏感 / 失败定义是什么’。",
            "supporting_table": {
                "headers": ["主题", "高敏感人群", "低敏感人群", "为什么敏感", "失败定义", "证据状态"],
                "rows": [
                    [
                        row.get("topic_name", "-"),
                        _tree_join(row.get("high_sensitivity_personas", []) or [], 2),
                        _tree_join(row.get("low_sensitivity_personas", []) or [], 2),
                        row.get("why_this_topic_is_sensitive", "-"),
                        _tree_join(row.get("failure_definition_patterns", []) or [], 1),
                        row.get("evidence_status", "-"),
                    ]
                    for row in select_explanation_topic_rows_for_series("X")
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                _tree_join(row.get("result_baseline_patterns", []) or [], 1)
                for row in select_explanation_topic_rows_for_series("X")[:6]
            ],
            "closing_implication": "X 的解释层要把每个主题真正挂到人，而不是只靠角色标签做总括。",
        },
        {
            "page_id": "survey_qual_explanation_t_pages",
            "heading": "#### T 解释组：全主题解释",
            "page_question": "T 每个主题为什么会敏感，谁会因为这个主题立刻判定失败？",
            "lead_judgment": "T 的解释层不再只围绕少数 JTBD，而是尽量为每个已出现主题挂上‘谁更敏感 / 为什么敏感 / 失败定义是什么’。",
            "supporting_table": {
                "headers": ["主题", "高敏感人群", "低敏感人群", "为什么敏感", "失败定义", "证据状态"],
                "rows": [
                    [
                        row.get("topic_name", "-"),
                        _tree_join(row.get("high_sensitivity_personas", []) or [], 2),
                        _tree_join(row.get("low_sensitivity_personas", []) or [], 2),
                        row.get("why_this_topic_is_sensitive", "-"),
                        _tree_join(row.get("failure_definition_patterns", []) or [], 1),
                        row.get("evidence_status", "-"),
                    ]
                    for row in select_explanation_topic_rows_for_series("T")
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                _tree_join(row.get("result_baseline_patterns", []) or [], 1)
                for row in select_explanation_topic_rows_for_series("T")[:6]
            ],
            "closing_implication": "T 的解释层要把每个主题真正挂到‘哪类人会把它当成失败’，而不是继续只停在总 archetype 或总 JTBD。",
        },
        {
            "page_id": "survey_qual_explanation_n_single_pages",
            "heading": "#### N_single 解释组：当前只到 VOC-only 解释边界",
            "page_question": "N_single 当前能解释到什么程度？",
            "lead_judgment": "N_single 当前没有与 X/T 同等级的问卷 / 定性直连输入，所以解释层只能先停在 VOC-only 的守位判断。",
            "supporting_table": {
                "headers": ["主题", "解释层级", "当前能解释什么", "已知效果期待", "边界声明", "市场"],
                "rows": build_n_explanation_rows("N_single"),
            },
            "representative_cases": [],
            "representative_quotes": [row[2] for row in build_n_explanation_rows("N_single")[:4]],
            "closing_implication": "N_single 当前先把守位逻辑和证据边界讲清楚。",
        },
        {
            "page_id": "survey_qual_explanation_n_aes_pages",
            "heading": "#### N_aes 解释组：当前只到 VOC-only 解释边界",
            "page_question": "N_aes 当前能解释到什么程度？",
            "lead_judgment": "N_aes 当前主要停在 VOC-only 的带宽判断，尤其要明确海外/ALL 有信号，但中国区仍缺解释层补位。",
            "supporting_table": {
                "headers": ["主题", "解释层级", "当前能解释什么", "已知效果期待", "边界声明", "市场"],
                "rows": build_n_explanation_rows("N_aes"),
            },
            "representative_cases": [],
            "representative_quotes": [row[2] for row in build_n_explanation_rows("N_aes")[:4]],
            "closing_implication": "N_aes 当前先把带宽判断讲清楚，不越过市场边界。",
        },
        {
            "page_id": "survey_qual_explanation_n_omni_pages",
            "heading": "#### N_omni 解释组：当前只到边界声明",
            "page_question": "N_omni 当前能解释到什么程度？",
            "lead_judgment": "N_omni 当前既没有稳定自家 VOC 样本，也没有问卷/定性直连输入，所以解释层只能保留边界声明。",
            "supporting_table": {
                "headers": ["带宽", "解释层级", "当前状态", "边界声明", "市场"],
                "rows": [
                    [row[0], row[1], row[2], row[4], row[5]]
                    for row in build_n_explanation_rows("N_omni")
                ],
            },
            "representative_cases": [],
            "representative_quotes": [row[2] for row in build_n_explanation_rows("N_omni")[:1]],
            "closing_implication": "N_omni 当前不做伪解释，先把边界守住。",
        },
        {
            "page_id": "x_positioning_overview",
            "heading": "### 1.1 X 系列：当前数据长出的角色定位",
            "page_question": "X 系列当前更稳定长出的角色定位是什么？",
            "lead_judgment": x_lead,
            "supporting_table": {
                "headers": ["当前角色定位", "命名理由", "PPT 映射", "成立度", "影响力", "代表用户"],
                "rows": [
                    [
                        package_label(package),
                        package.get("naming_reason", package.get("one_line_definition", "-")),
                        package.get("canonical_anchor", "-"),
                        x_conf_lookup.get(package["positioning_name"], {}).get("confidence_level", "-"),
                        x_impact_lookup.get(package["positioning_name"], {}).get("impact_level", "-"),
                        "；".join(user_title(user) for user in package.get("representative_users", [])[:2]),
                    ]
                    for package in x_packages
                ],
            },
            "representative_cases": [
                user_title(user)
                for package in x_packages
                for user in package.get("representative_users", [])[:1]
            ],
            "representative_quotes": [
                quote
                for package in x_packages
                for quote in package.get("representative_quotes", [])[:1]
            ],
            "closing_implication": "X 系列不能再把所有人压成一个总标签，而要区分哪些是稳定主定位，哪些只是方向性表达信号。",
        },
        {
            "page_id": "x_positioning_cards",
            "heading": "### 1.2 X 系列：代表用户 / 清洁态度 / 购买决策 / JTBD",
            "page_question": "每一类 X 用户到底怎么想？",
            "lead_judgment": "同样是旗舰购买，真正拉开差异的不是参数，而是他们到底在找一个基础代劳的角色，还是一个低介入托管的角色。",
            "detail_cards": [
                {
                    "title": package["positioning_name"],
                    "lead_judgment": package["one_line_definition"],
                    "metric_cards": [
                        {
                            "title": "定位成立度",
                            "metric_value": x_conf_lookup.get(package["positioning_name"], {}).get("confidence_level", "-"),
                            "interpretation": f"{x_conf_lookup.get(package['positioning_name'], {}).get('support_case_count', 0)}个案例 / {x_conf_lookup.get(package['positioning_name'], {}).get('high_quality_passage_count', 0)}条高质量证据",
                        },
                        {
                            "title": "定位影响力",
                            "metric_value": x_impact_lookup.get(package["positioning_name"], {}).get("impact_level", "-"),
                            "interpretation": f"{x_impact_lookup.get(package['positioning_name'], {}).get('linked_pain_theme_count', 0)}类问题主题 / {x_impact_lookup.get(package['positioning_name'], {}).get('linked_voc_package_strength', 0)}个VOC问题包 / {x_impact_lookup.get(package['positioning_name'], {}).get('linked_brand_judgment_strength', 0)}个品牌支撑 / {x_impact_lookup.get(package['positioning_name'], {}).get('linked_idea_cluster_strength', 0)}个金点子支撑",
                        },
                        {
                            "title": "JTBD 成立度",
                            "metric_value": x_jtbd_conf_lookup.get(package_jtbd(package), {}).get("confidence_level", "-"),
                            "interpretation": f"{x_jtbd_conf_lookup.get(package_jtbd(package), {}).get('support_case_count', 0)}个案例 / {x_jtbd_conf_lookup.get(package_jtbd(package), {}).get('high_quality_passage_count', 0)}条高质量证据",
                        },
                        {
                            "title": "JTBD 影响力",
                            "metric_value": x_jtbd_impact_lookup.get(package_jtbd(package), {}).get("impact_level", "-"),
                            "interpretation": f"{x_jtbd_impact_lookup.get(package_jtbd(package), {}).get('linked_pain_theme_count', 0)}类问题主题 / {x_jtbd_impact_lookup.get(package_jtbd(package), {}).get('linked_voc_package_strength', 0)}个VOC问题包 / {x_jtbd_impact_lookup.get(package_jtbd(package), {}).get('linked_priority_bucket_count', 0)}个优先级桶",
                        },
                    ],
                    "bullets": [
                        f"当前角色定位：{package.get('positioning_name', '-')}",
                        f"PPT 映射：{package.get('canonical_anchor', '-')}",
                        f"为什么这个名字比其他候选更贴数：{package.get('naming_reason', '-')}",
                        f"这类人是谁：{'；'.join(persona_line(user) for user in package.get('representative_users', [])[:2]) or '-'}",
                        f"怎么看待清洁：{'；'.join(package.get('attitude_pattern', [])[:2]) or '当前最强信号仍偏少操心、少返工和主动补位。'}",
                        f"怎么买：{'；'.join(package.get('buying_logic', [])[:2]) or '-'}",
                        f"最在意什么痛点/期待：{'；'.join(package.get('pain_need', [])[:3]) or '-'}",
                        f"真正 JTBD：{package_jtbd(package)}",
                        f"为什么不是另外两类：{package.get('why_not_other_two', '-')}",
                        f"当前 Product To-do：{'；'.join(package.get('product_todo', [])[:2]) or '-'}",
                        f"更会被哪些品牌打动：{'、'.join(x_alignment([user_title(user) for user in package.get('representative_users', [])])[0]) or '-'}",
                        f"更会被哪些金点子打动：{'、'.join(x_alignment([user_title(user) for user in package.get('representative_users', [])])[1]) or '-'}",
                    ],
                    "representative_cases": [user_title(user) for user in package.get("representative_users", [])[:3]],
                    "representative_quotes": package.get("representative_quotes", [])[:2],
                }
                for package in main_x_packages
            ],
            "closing_implication": "X 的对外表达不该再是一张总表，而要围绕已经稳定长出的主定位去讲价值主张和判断链。",
        },
        {
            "page_id": "x_positioning_difference",
            "heading": "#### 清洁帮手 vs 清洁管家",
            "page_question": "同样都想省事，为什么有人买帮手，有人买管家？",
            "lead_judgment": "两类人都想把清洁这件事交给机器，但 `清洁帮手` 接受机器做完大面后自己补尾，`清洁管家` 则要求机器别把麻烦和返工重新甩回给自己。",
            "supporting_table": {
                "headers": ["对比维度", "清洁帮手", "清洁管家"],
                "rows": [
                    [dimension, package_compare_text(package_by_anchor("清洁帮手"), dimension), package_compare_text(package_by_anchor("清洁管家"), dimension)]
                    for dimension in ["成立度 / 影响力", "机器角色", "清洁边界", "人工介入默认", "购买时最在意", "不能接受", "产品该怎么讲"]
                ],
            },
            "representative_cases": [
                *([user_title(user) for user in (package_by_anchor("清洁帮手") or {}).get("representative_users", [])[:1]]),
                *([user_title(user) for user in (package_by_anchor("清洁管家") or {}).get("representative_users", [])[:1]]),
            ],
            "representative_quotes": [
                *((package_by_anchor("清洁帮手") or {}).get("representative_quotes", [])[:1]),
                *((package_by_anchor("清洁管家") or {}).get("representative_quotes", [])[:1]),
            ],
            "closing_implication": "这也是为什么 X 系列不能只讲“解放双手”：帮手型更像基础代劳，管家型更像低介入托管，两者的产品语言和优先级完全不同。",
        },
        {
            "page_id": "x_generation_compare",
            "heading": generation_rows.get("X", {}).get("heading", "#### X 系列：X11 vs X8"),
            "page_question": "X 系列本代和上一代到底差在哪里？",
            "lead_judgment": generation_rows.get("X", {}).get("lead_judgment", "X 系列本代与上一代的差异仍待补充。"),
            "supporting_table": {
                "headers": ["对比维度", "本代 X11", "上一代 X8", "参考调研提示"],
                "rows": generation_rows.get("X", {}).get("compare_rows", []),
            },
            "representative_cases": [],
            "representative_quotes": generation_rows.get("X", {}).get("representative_quotes", []),
            "closing_implication": "X 的代际对比不该只看参数升级，而要看用户是从“基础完成”转向了“低介入托管”，还是仍停留在对清洁底线的补课。",
        },
        {
            "page_id": "x_generation_strategy",
            "heading": "#### X 系列：代际策略翻译",
            "page_question": "X11 相比 X8，本代到底该继承什么、修什么、先别讲什么？",
            "lead_judgment": generation_rows.get("X", {}).get("strategy_summary", "X 系列代际策略翻译仍待补充。"),
            "supporting_table": {
                "headers": ["策略动作", "当前判断", "前台表达建议"],
                "rows": generation_rows.get("X", {}).get("strategy_rows", []),
            },
            "representative_cases": [],
            "representative_quotes": generation_rows.get("X", {}).get("representative_quotes", [])[:2],
            "closing_implication": "X 的代际升级不该被讲成“功能更全”，而该被讲成“托管承诺更可信，同时没有丢掉基础完成率”。",
        },
        {
            "page_id": "t_male_slices",
            "heading": "### 1.3 T 系列：他们是谁 / 她们是谁",
            "page_question": "T 系列用户到底是谁？",
            "lead_judgment": "T 系列不能先讲参数，要先讲人。因为同样是中端机，用户对清洁的定义已经随着所处的人生位置发生了分化。",
            "supporting_table": {
                "headers": ["代表用户", "一句话人设", "家庭结构", "清洁方式", "购买方式"],
                "rows": [
                    [
                        card["case_title"],
                        card["one_line_persona"],
                        card["family_structure"],
                        card["cleaning_style"],
                        card["purchase_path"],
                    ]
                    for card in t_cards
                    if card.get("role_bucket") == "他们是谁"
                ],
            },
            "representative_cases": [card["case_title"] for card in t_cards if card.get("role_bucket") == "他们是谁"][:4],
            "representative_quotes": [card["representative_quote"] for card in t_cards if card.get("role_bucket") == "他们是谁"][:2],
            "closing_implication": "男性样本里更容易看到‘家务兜底者’和‘效率型替代’的判断逻辑。",
        },
        {
            "page_id": "t_female_slices",
            "heading": "#### 她们是谁",
            "page_question": "T 系列女性样本怎么理解清洁？",
            "lead_judgment": "女性样本里更容易看到‘谁在做、有没有时间做、这件事该不该继续由我兜底’这样的判断方式。",
            "supporting_table": {
                "headers": ["代表用户", "一句话人设", "家庭结构", "清洁方式", "购买方式"],
                "rows": [
                    [
                        card["case_title"],
                        card["one_line_persona"],
                        card["family_structure"],
                        card["cleaning_style"],
                        card["purchase_path"],
                    ]
                    for card in t_cards
                    if card.get("role_bucket") == "她们是谁"
                ],
            },
            "representative_cases": [card["case_title"] for card in t_cards if card.get("role_bucket") == "她们是谁"][:4],
            "representative_quotes": [card["representative_quote"] for card in t_cards if card.get("role_bucket") == "她们是谁"][:2],
            "closing_implication": "同样是 T 系列，女性样本更容易把清洁和家庭角色、时间压力、审美与居住秩序一起考虑。",
        },
        {
            "page_id": "t_difference_matrix",
            "heading": "### 1.4 T 系列：他们为什么不一样",
            "page_question": "同样是清洁问题，T 为什么会长出两套不同判断？",
            "lead_judgment": "T 系列真正的差异，不是参数口味差，而是清洁这件事在不同人生位置里被重新定义成了效率问题、责任问题或者系统保障问题。",
            "supporting_table": {
                "headers": ["维度", "对比对象", "为什么不同", "用户怎么理解清洁", "价值定义"],
                "rows": [
                    [
                        row["dimension"],
                        " vs ".join(row.get("contrast_pair", [])[:2]),
                        row["why_different"],
                        row["user_view_of_cleaning"],
                        row["value_definition"],
                    ]
                    for row in t_rows
                ],
            },
            "representative_cases": [title for row in t_rows for title in row.get("contrast_pair", [])[:2]],
            "representative_quotes": [quote for row in t_rows for quote in row.get("representative_support", [])[:2]],
            "detail_cards": [
                {
                    "title": row["dimension"],
                    "lead_judgment": row["why_different"],
                    "metric_cards": [
                        {
                            "title": "概念成立度",
                            "metric_value": f"{dimension_confidence_lookup.get(row['dimension'], {}).get('confidence_level', '-')}",
                            "interpretation": f"{dimension_confidence_lookup.get(row['dimension'], {}).get('support_case_count', 0)}个案例 / {dimension_confidence_lookup.get(row['dimension'], {}).get('high_quality_passage_count', 0)}条高质量证据 / {dimension_confidence_lookup.get(row['dimension'], {}).get('cross_jtbd_coverage', 0)}类JTBD覆盖",
                        },
                        {
                            "title": "影响力强度",
                            "metric_value": f"{dimension_impact_lookup.get(row['dimension'], {}).get('impact_level', '-')}",
                            "interpretation": f"{dimension_impact_lookup.get(row['dimension'], {}).get('linked_pain_theme_count', 0)}类问题主题 / {dimension_impact_lookup.get(row['dimension'], {}).get('linked_voc_package_strength', 0)}个VOC问题包 / {dimension_impact_lookup.get(row['dimension'], {}).get('linked_survey_segment_strength', 0)}个问卷分群",
                        },
                    ],
                    "detail_table": {
                        "headers": ["对比对象", "用户怎么理解清洁", "价值定义"],
                        "rows": [[
                            " vs ".join(row.get("contrast_pair", [])[:2]),
                            row.get("user_view_of_cleaning", "-"),
                            row.get("value_definition", "-"),
                        ]],
                    },
                    "representative_quotes": row.get("representative_support", [])[:2],
                }
                for row in t_rows
            ],
            "closing_implication": "这也是为什么 T 不能再被压成一个单 archetype，而要拆成“谁 + 为什么不同 + JTBD”。",
        },
        {
            "page_id": "t_jtbd_pages",
            "heading": "### 1.5 T 系列 JTBD",
            "page_question": "T 系列最终对应的是哪几类 JTBD？",
            "lead_judgment": "T 更像三类 JTBD，而不是一个统一定位：有人要把清洁待办删掉，有人要机器别打扰家庭节奏，有人要它替自己稳稳兜住家庭标准。",
            "supporting_table": {
                "headers": ["JTBD", "典型场景", "结果要求", "不能接受的代价", "代表用户"],
                "rows": [
                    [
                        row["jtbd_name"],
                        "；".join(row.get("typical_scene", [])[:2]),
                        row["result_requirement"],
                        row["unacceptable_cost"],
                        "；".join(row.get("representative_users", [])[:2]),
                    ]
                    for row in t_jtbd_rows
                ],
            },
            "representative_cases": [title for row in t_jtbd_rows for title in row.get("representative_users", [])[:2]],
            "representative_quotes": [quote for row in t_jtbd_rows for quote in row.get("why_entered", [])[:2]],
            "detail_cards": [
                {
                    "title": row["jtbd_name"],
                    "lead_judgment": row["result_requirement"],
                    "metric_cards": [
                        {
                            "title": "概念成立度",
                            "metric_value": f"{jtbd_confidence_lookup.get(row['jtbd_name'], {}).get('confidence_level', '-')}",
                            "interpretation": f"{jtbd_confidence_lookup.get(row['jtbd_name'], {}).get('support_case_count', 0)}个案例 / {jtbd_confidence_lookup.get(row['jtbd_name'], {}).get('high_quality_passage_count', 0)}条高质量证据 / 场景重复{jtbd_confidence_lookup.get(row['jtbd_name'], {}).get('scenario_repeat_count', 0)}",
                        },
                        {
                            "title": "影响力强度",
                            "metric_value": f"{jtbd_impact_lookup.get(row['jtbd_name'], {}).get('impact_level', '-')}",
                            "interpretation": f"{jtbd_impact_lookup.get(row['jtbd_name'], {}).get('linked_pain_theme_count', 0)}类问题主题 / {jtbd_impact_lookup.get(row['jtbd_name'], {}).get('linked_voc_package_strength', 0)}个VOC问题包 / {jtbd_impact_lookup.get(row['jtbd_name'], {}).get('linked_survey_segment_strength', 0)}个问卷分群",
                        },
                    ],
                    "detail_table": {
                        "headers": ["典型场景", "结果要求", "不能接受的代价"],
                        "rows": [[
                            "；".join(row.get("typical_scene", [])[:2]),
                            row.get("result_requirement", "-"),
                            row.get("unacceptable_cost", "-"),
                        ]],
                    },
                    "representative_quotes": row.get("why_entered", [])[:2],
                }
                for row in t_jtbd_rows
            ],
            "closing_implication": "后续 T 的策略与卖点表达，应该围绕不同 JTBD 去讲，而不是只讲“中端用户要什么”。",
        },
        {
            "page_id": "t_generation_compare",
            "heading": generation_rows.get("T", {}).get("heading", "#### T 系列：T80S vs T80"),
            "page_question": "T 系列本代和上一代到底差在哪里？",
            "lead_judgment": generation_rows.get("T", {}).get("lead_judgment", "T 系列本代与上一代的差异仍待补充。"),
            "supporting_table": {
                "headers": ["对比维度", "本代 T80S", "上一代 T80", "参考调研提示"],
                "rows": generation_rows.get("T", {}).get("compare_rows", []),
            },
            "representative_cases": [],
            "representative_quotes": generation_rows.get("T", {}).get("representative_quotes", []),
            "closing_implication": "T 的代际对比更该看“维护痛点有没有被收住、结果有没有更稳、托管有没有更可信”，而不是只看新卖点是否更多。",
        },
        {
            "page_id": "t_generation_strategy",
            "heading": "#### T 系列：代际策略翻译",
            "page_question": "T80S 相比 T80，本代到底该继承什么、修什么、先别讲什么？",
            "lead_judgment": generation_rows.get("T", {}).get("strategy_summary", "T 系列代际策略翻译仍待补充。"),
            "supporting_table": {
                "headers": ["策略动作", "当前判断", "前台表达建议"],
                "rows": generation_rows.get("T", {}).get("strategy_rows", []),
            },
            "representative_cases": [],
            "representative_quotes": generation_rows.get("T", {}).get("representative_quotes", [])[:2],
            "closing_implication": "T 的代际升级不该被讲成“多了新卖点”，而该被讲成“上一代暴露的维护和返工问题被系统性收住了多少”。",
        },
        {
            "page_id": "pain_need_pages",
            "heading": "### 1.6 当前痛点和需求",
            "page_question": "当前真正驱动用户判断的痛点是什么？",
            "lead_judgment": "现在真正影响判断的不是单点功能缺失，而是哪些场景会把用户重新推回手动、返工和维护。",
            "supporting_table": {
                "headers": ["对象", "当前问题", "对应需求", "意味着什么"],
                "rows": [
                    [
                        package["positioning_name"],
                        "；".join(package.get("pain_need", [])[:2]),
                        "；".join(package.get("product_todo", [])[:2]),
                        package.get("why_not_other_two", "-"),
                    ]
                    for package in x_packages
                ]
                + [
                    [
                        row["jtbd_name"],
                        "；".join(row.get("typical_scene", [])[:2]),
                        row["result_requirement"],
                        row["unacceptable_cost"],
                    ]
                    for row in t_jtbd_rows
                ],
            },
            "representative_cases": [
                user_title(user)
                for package in x_packages
                for user in package.get("representative_users", [])[:1]
            ]
            + [title for row in t_jtbd_rows for title in row.get("representative_users", [])[:1]],
            "representative_quotes": [
                quote
                for package in x_packages
                for quote in package.get("representative_quotes", [])[:1]
            ]
            + [quote for row in t_jtbd_rows for quote in row.get("why_entered", [])[:1]],
            "closing_implication": "后续优先级讨论要围绕这些‘会把人重新拉回手动’的场景，而不是平均铺开所有功能议题。",
        },
        {
            "page_id": "user_convergence_tree_pages",
            "heading": "### 1.7 用户收敛树：哪些判断已经可以稳定上翻",
            "page_question": "把前面的暴露层往上收敛后，哪些判断已经可以正式变成系列主命题？",
            "lead_judgment": str(user_strategy_convergence_tree.get("summary_judgment", "用户收敛树仍待补充。")),
            "supporting_table": {
                "headers": ["收敛概念", "状态", "当前判断", "为什么不是别的结论", "前台用途"],
                "rows": [
                    [
                        row.get("concept_name", "-"),
                        row.get("concept_status", "-"),
                        row.get("lead_judgment", "-"),
                        row.get("why_not_other", "-"),
                        row.get("promoted_to", "-"),
                    ]
                    for row in user_converged_nodes + user_not_ready_nodes
                ],
            },
            "representative_cases": [],
            "representative_quotes": [
                _tree_join(row.get("evidence_refs", []) or [], 2)
                for row in (user_converged_nodes + user_not_ready_nodes)[:3]
            ],
            "closing_implication": "看用户不是多讲一层抽象词，而是先暴露，再收敛，最后只把真正稳定的判断升级成系列主命题。",
        },
        {
            "page_id": "user_thesis_pages",
            "heading": "### 1.8 用户 thesis：最后才把用户判断翻成系列主命题",
            "page_question": "把前面的暴露与收敛一路往上翻，X / T / N 三条带当前各自真正该承接的用户主命题是什么？",
            "lead_judgment": "只有在问题关注点、问题剖面和人群解释都摊开之后，系列级用户 thesis 才不会再次退回几个安全的大词，而是能落到每条带真正要承接的用户判断。",
            "supporting_table": {
                "headers": ["系列", "当前主命题", "用户最在意什么", "当前赢在什么", "当前输在什么"],
                "rows": [
                    [
                        "X",
                        user_thesis_rows.get("x_core_thesis", "-"),
                        summarize_focus_rows(select_topic_rows_for_series("X", 2), include_rate=True),
                        summarize_focus_rows(top_positive_rows_for_series("X", 2)),
                        summarize_focus_rows(top_negative_rows_for_series("X", 2)),
                    ],
                    [
                        "T",
                        user_thesis_rows.get("t_core_thesis", "-"),
                        summarize_focus_rows(select_topic_rows_for_series("T", 2), include_rate=True),
                        summarize_focus_rows(top_positive_rows_for_series("T", 2)),
                        summarize_focus_rows(top_negative_rows_for_series("T", 2)),
                    ],
                    [
                        "N_single",
                        user_thesis_rows.get("n_band_theses", {}).get("N_single", "-"),
                        summarize_focus_rows(select_topic_rows_for_series("N", 2, "N_single"), include_rate=True),
                        summarize_focus_rows(top_positive_rows_for_series("N", 2, "N_single")),
                        summarize_focus_rows(top_negative_rows_for_series("N", 2, "N_single")),
                    ],
                    [
                        "N_aes",
                        user_thesis_rows.get("n_band_theses", {}).get("N_aes", "-"),
                        summarize_focus_rows(select_topic_rows_for_series("N", 2, "N_aes"), include_rate=True),
                        summarize_focus_rows(top_positive_rows_for_series("N", 2, "N_aes")),
                        summarize_focus_rows(top_negative_rows_for_series("N", 2, "N_aes")),
                    ],
                    [
                        "N_omni",
                        user_thesis_rows.get("n_band_theses", {}).get("N_omni", "-"),
                        "当前仍缺稳定自家 VOC 样本",
                        "-",
                        "当前主要风险是缺样本，不是已知负向主题",
                    ],
                ],
            },
            "representative_cases": [],
            "representative_quotes": list(user_thesis_rows.get("what_should_not_be_overstated", []) or [])[:3],
            "closing_implication": "用户 thesis 的作用，是把‘用户关注什么、在哪些地方会失败’翻成系列承接语言，而不是再重复一遍用户画像。",
        },
        {
            "page_id": "brand_mindshare_pages",
            "heading": "### 1.9 品牌心智",
            "page_question": "各品牌在用户眼里分别是什么？",
            "lead_judgment": "品牌心智不是谁被提到得多，而是用户心里已经把它们分别放进了不同的认知抽屉里：专业、老牌、黑科技、跨界、入门。",
            "supporting_table": {
                "headers": ["品牌", "一句判断", "为什么会选", "为什么会放弃", "谁更容易买它"],
                "rows": [
                    [
                        row["brand"],
                        row["one_line_label"],
                        "；".join(row.get("why_choose", [])[:2]),
                        "；".join(row.get("why_reject", [])[:2]),
                        "；".join(row.get("who_chooses", [])[:2]),
                    ]
                    for row in brand_rows
                ],
            },
            "representative_cases": [title for row in brand_rows for title in row.get("who_chooses", [])[:1]],
            "representative_quotes": [quote for row in brand_rows for quote in row.get("quote_refs", [])[:1]],
            "closing_implication": "品牌心智页的价值，不是列品牌，而是解释用户为什么会在相似产品里更先想到谁、放弃谁。",
        },
        {
            "page_id": "idea_pool_pages",
            "heading": "### 1.10 用户金点子",
            "page_question": "用户的金点子到底在提示什么？",
            "lead_judgment": "金点子不是创意清单，而是用户已经明确指出：还有哪些场景没有真正被扫地机接住。",
            "supporting_table": {
                "headers": ["主题", "没被满足的场景", "想要的能力", "谁在提", "现在还是以后做"],
                "rows": [
                    [
                        row["theme"],
                        row["unmet_scene"],
                        row["desired_capability"],
                        "；".join(row.get("who_needs_it", [])[:2]),
                        row["now_or_later"],
                    ]
                    for row in idea_rows
                ],
            },
            "representative_cases": [title for row in idea_rows for title in row.get("who_needs_it", [])[:1]],
            "representative_quotes": [row["unmet_scene"] for row in idea_rows[:3]],
            "closing_implication": "这些想法里，有些是当前底线问题的延伸，有些才是真正适合后续差异化布局的加分项。",
        },
        {
            "page_id": "competition_intro_pages",
            "heading": "## 2. 看竞争",
            "page_question": "这一章到底要回答什么？",
            "lead_judgment": str(competition_thesis_tree.get("summary_judgment", "看竞争不能只停在行业问题或品牌印象，而要把真实用户抱怨、展会信号、能力门槛和当前对阵关系串成一条完整判断链。")),
            "supporting_table": {},
            "representative_cases": [],
            "representative_quotes": [],
            "closing_implication": "这一章会先回答行业在卷什么，再回答我们到底在和谁打、最该防什么。",
        },
        {
            "page_id": "competition_thesis_pages",
            "heading": "### 2.1 竞争母题：先看行业真正的三条压力线",
            "page_question": "在落到能力、对阵和 VOC 之前，当前竞争判断最该先收成哪三条母题？",
            "lead_judgment": str(competition_thesis_tree.get("summary_judgment", "当前竞争母题仍待补充。")),
            "supporting_table": {
                "headers": ["竞争母题", "当前最该怎么判断", "别讲歪成什么", "关联竞争带"],
                "rows": [
                    [
                        node.get("thesis_name", "-"),
                        node.get("root_claim", "-"),
                        node.get("what_not_to_confuse", "-"),
                        "、".join(node.get("scope_refs", []) or []) or "-",
                    ]
                    for node in competition_thesis_nodes
                ],
            },
            "detail_cards": [
                {
                    "title": node.get("thesis_name", "-"),
                    "lead_judgment": node.get("root_claim", "-"),
                    "bullets": [
                        f"为什么它已经成门槛：{node.get('why_this_is_the_bar', '-')}",
                        f"当前别讲歪成什么：{node.get('what_not_to_confuse', '-')}",
                        f"当前关联竞争带：{'、'.join(node.get('scope_refs', []) or []) or '-'}",
                    ],
                    "representative_quotes": list(node.get("evidence_refs", []) or [])[:2],
                }
                for node in competition_thesis_nodes
            ],
            "closing_implication": "竞争母题页先把‘到底在卷什么’讲透，后面的能力扫描、对阵和 VOC 才不会重新散回一堆表格。",
        },
        {
            "page_id": "competition_capability_scan_pages",
            "heading": "#### 行业能力扫描及洞察",
            "page_question": "行业现在卷到了哪些能力，这些能力和真实用户问题是否已经对上？",
            "lead_judgment": "AWE 这轮最值得先讲透的，不是参数数字本身，而是行业已经把哪些能力抬成了 `高端托管门槛 / 主销结果稳定门槛 / 下探带宽完整度门槛`。",
            "supporting_table": {
                "headers": ["能力维度", "行业前沿", "科沃斯状态", "当前差距", "为什么重要"],
                "rows": build_competition_capability_rows(competition_capability_scan),
            },
            "representative_cases": [],
            "representative_quotes": [
                str(signal.get("signal_text", "-"))
                for signal in (awe_exhibition_signals.get("industry_capability_signals", []) or [])[:3]
            ],
            "detail_cards": build_competition_capability_theme_cards(competition_capability_scan),
            "closing_implication": "能力扫描页的价值，不是罗列参数，而是把“行业正在讲什么”翻译成“哪些能力已经必须防、哪些还只是方向层”。",
        },
        {
            "page_id": "competition_matchup_pages",
            "heading": "#### 核心竞品对阵",
            "page_question": "X、T、N 三条线当前真正分别在对谁？",
            "lead_judgment": f"当前对阵不能再泛泛看所有竞品，而要按竞争带拆开看：X 打旗舰 omni，T 打主销 omni，N 分别打 omni 下探、AES 和单机守位。AWE 本轮重点对手也集中在 `{awe_competitor_labels or '头部竞品'}`。",
            "supporting_table": {
                "headers": ["系列/竞争带", "当前真正对谁", "当前该讲什么", "最该防的 VOC 风险"],
                "rows": build_competition_matchup_rows(competition_matchup_matrix),
            },
            "representative_cases": [],
            "representative_quotes": [
                str(row.get("why_this_matchup", "-"))
                for row in (competition_matchup_matrix.get("rows", []) or [])[:3]
            ],
            "detail_cards": build_competition_matchup_detail_cards(competition_matchup_matrix),
            "closing_implication": "对阵页的作用，是把“我们到底在和谁打”讲清楚，不再让旗舰、主销和下探守位混成一锅。",
        },
        {
            "page_id": "competition_voc_cn_pages",
            "heading": "#### 中国用户 VOC：X/T/N 分系列展开",
            "page_question": "在中国市场，X、T、N 三条线分别最容易被什么问题打穿？",
            "lead_judgment": (
                "中国市场当前已经有可用样本，可以按 X/T/N 展开看竞争 VOC；但正式判断只讲有稳定自家样本的竞争带，其余部分如实保留缺口。"
                if bool(competition_market_summary_lookup.get("中国", {}).get("is_stable"))
                else "当前竞争 VOC 已能做产品/系列判断，但中国市场切分尚未稳定，不进入正式并列页。"
            ),
            "supporting_table": {
                "headers": ["竞争带", "主问题", "次问题", "这说明用户真正不能接受什么", "当前判断", "优秀竞品"],
                "rows": build_competition_voc_market_rows_v2(competition_voc_market_split, competition_voc_xtn_breakdown, "中国")
                if bool(competition_market_summary_lookup.get("中国", {}).get("scope_count"))
                else [[
                    "中国",
                    "待补充",
                    "-",
                    "当前该竞争带稳定 VOC 仍待补齐。",
                    str(competition_market_summary_lookup.get("中国", {}).get("status_text", "当前竞争 VOC 已能做产品/系列判断，但中国市场切分尚未稳定，不进入正式并列页。")),
                    "-",
                ]],
            },
            "representative_cases": [],
            "representative_quotes": [
                str(row.get("lead_judgment", "-"))
                for row in (competition_voc_market_split.get("market_rows", []) or [])
                if row.get("market_scope") == "中国"
            ][:3],
            "closing_implication": "中国用户 VOC 页的作用，是把真实差评直接挂到 X/T/N 三条竞争带上，而不是继续留在产品级散点里。",
        },
        {
            "page_id": "competition_voc_overseas_pages",
            "heading": "#### 海外用户 VOC：X/T/N 分系列展开",
            "page_question": "在海外市场，X、T、N 三条线分别最容易被什么问题打穿？",
            "lead_judgment": (
                "海外市场当前已有部分可用样本，但正式判断仍优先看稳定样本，不能把小样本直接讲成硬结论。"
                if bool(competition_market_summary_lookup.get("海外", {}).get("is_stable"))
                else "当前竞争 VOC 已能做产品/系列判断，但海外市场切分尚未稳定，不进入正式并列页。"
            ),
            "supporting_table": {
                "headers": ["竞争带", "主问题", "次问题", "这说明用户真正不能接受什么", "当前判断", "优秀竞品"],
                "rows": build_competition_voc_market_rows_v2(competition_voc_market_split, competition_voc_xtn_breakdown, "海外")
                if bool(competition_market_summary_lookup.get("海外", {}).get("scope_count"))
                else [[
                    "海外",
                    "待补充",
                    "-",
                    "当前该竞争带稳定 VOC 仍待补齐。",
                    str(competition_market_summary_lookup.get("海外", {}).get("status_text", "当前竞争 VOC 已能做产品/系列判断，但海外市场切分尚未稳定，不进入正式并列页。")),
                    "-",
                ]],
            },
            "representative_cases": [],
            "representative_quotes": [
                str(row.get("lead_judgment", "-"))
                for row in (competition_voc_market_split.get("market_rows", []) or [])
                if row.get("market_scope") == "海外"
            ][:3],
            "closing_implication": "海外用户 VOC 页的价值，在于看清哪些风险是中国特有，哪些已经是全球共同门槛。",
        },
        {
            "page_id": "competition_problem_pages",
            "heading": "## 2. 看竞争",
            "page_question": "当前行业真正卷在哪些问题上？",
            "lead_judgment": "看竞争不该只看别人堆了什么参数，而要看行业还没解决、但用户持续在意的那些老问题究竟落在哪些包里。",
            "supporting_table": {
                "headers": ["当前高频问题包", "它真正伤害的是什么", "为什么是竞争焦点", "当前规模感"],
                "rows": build_competition_problem_rows(voc_problem_packages, cross_source_interpretation),
            },
            "representative_cases": [],
            "representative_quotes": [
                str(row.get("best_explanation", "-"))
                for row in (cross_source_interpretation.get("interpretations", []) or [])[:3]
            ],
            "closing_implication": "竞争页的重点不是列参数，而是指出：哪些问题已经成了行业共同底线，谁更像真正把事做完的人。",
        },
        {
            "page_id": "competition_trend_pages",
            "heading": "#### 行业在卷什么",
            "page_question": "行业当前到底在卷什么，为什么用户却还在抱怨老问题？",
            "lead_judgment": "行业看起来在卷参数和新卖点，但用户真正持续在意的，仍是清洁底线、维护负担和托管信任这些老问题。",
            "supporting_table": {
                "headers": ["判断维度", "当前观察", "这意味着什么"],
                "rows": build_competition_trend_rows(strategy_translation, cross_source_interpretation),
            },
            "representative_cases": [],
            "representative_quotes": [str(row.get("best_explanation", "-")) for row in (cross_source_interpretation.get("interpretations", []) or [])[:3]],
            "closing_implication": "行业页真正要讲的是：创新没有停，但很多问题仍停留在“看得见、却没做透”的状态。",
        },
        {
            "page_id": "competition_brand_pages",
            "heading": "#### 品牌 / 竞品心智差距",
            "page_question": "用户眼里各品牌到底是什么，我们要和谁争什么？",
            "lead_judgment": "品牌竞争不是简单比参数，而是用户已经把每个品牌放进不同心智抽屉里：有人代表放心、有人代表新技术、有人代表拖地专长、有人代表跨界光环。",
            "supporting_table": {
                "headers": ["品牌", "用户眼里它是什么", "当前竞争含义", "更容易打动谁"],
                "rows": build_competition_brand_rows(brand_mindshare_judgments),
            },
            "representative_cases": [],
            "representative_quotes": [str(row.get("one_line_label", "-")) for row in (brand_mindshare_judgments.get("judgments", []) or [])[:3]],
            "closing_implication": "竞争页还要说明：我们真正要打的，不是谁参数更多，而是谁更像那个“不会出错、值得信任、又足够有吸引力”的品牌。",
        },
        {
            "page_id": "competition_generation_brand_pages",
            "heading": "#### 各品牌这一代在卷什么",
            "page_question": "各品牌这一代到底在主推什么，科沃斯现在真正在面对谁？",
            "lead_judgment": "各品牌这一代卷的不只是新品数量，而是在不同竞争带里选择继续强化什么、补什么、以及把产品线扩到哪里。",
            "supporting_table": {
                "headers": ["竞争带", "当前判断", "典型品牌动作", "对科沃斯意味着什么"],
                "rows": build_competition_current_brand_rows(competition_generation_analysis),
            },
            "representative_cases": [],
            "representative_quotes": [str(row.get("lead_judgment", "-")) for row in (competition_generation_analysis.get("scope_summary_rows", []) or [])[:3]],
            "closing_implication": "这页的价值，是说明科沃斯当前面对的不是抽象竞品，而是各品牌在不同竞争带上已经布好的这一代产品线。",
        },
        {
            "page_id": "competition_shape_generation_pages",
            "heading": "#### 形态竞争格局：omni / aes / 单机",
            "page_question": "不先分形态，为什么竞争判断会失真？",
            "lead_judgment": "omni、aes、单机本来就是三条不同竞争带；如果混着看，就会把旗舰线、下探带和守位带全部讲乱。",
            "supporting_table": {
                "headers": ["形态", "子竞争带", "当前变化", "竞争含义", "科沃斯该防什么"],
                "rows": build_competition_shape_rows(competition_generation_analysis),
            },
            "representative_cases": [],
            "representative_quotes": [str(row.get("what_it_means_for_ecovacs", "-")) for row in (competition_generation_analysis.get("shape_summary_rows", []) or [])[:3]],
            "closing_implication": "形态竞争格局页要说明：X/T 在 omni 里打什么，N 又该在 omni / aes / 单机 上承接什么。",
        },
        {
            "page_id": "competition_conclusion_pages",
            "heading": "#### 竞争结论：X/T/N（三带）现在各自该防什么",
            "page_question": "竞争判断最后该怎么翻回 X、T、N（三带）三条线？",
            "lead_judgment": "竞争章节的终点不是看完别人做了什么，而是明确：X、T、N（三带）现在各自最该防什么、哪些风险必须直接进入优先级。",
            "supporting_table": {
                "headers": ["系列", "当前必须防什么", "当前最该推进什么", "行业标杆在逼我们补什么"],
                "rows": build_competition_conclusion_rows(competition_strategy_bridge),
            },
            "representative_cases": [],
            "representative_quotes": competition_strategy_bridge.get("which_voc_gaps_must_enter_priority", [])[:3],
            "closing_implication": "竞争结论页要把外部竞争重新翻译成内部承接边界，否则看竞争和看自己之间仍然是断的。",
        },
        {
            "page_id": "self_value_pages",
            "heading": "## 3. 看自己",
            "page_question": "当前我们到底该怎么理解 X / T / N（三带）三条线的角色？",
            "lead_judgment": str(self_strategy_thesis_tree.get("summary_judgment", "看自己这一章的重点不再是罗列承接表，而是先把 `X / T / N（三带）` 当前各自的主命题讲透。")).replace("，N 守带宽分工和缺口边界。", "，N（三带）守带宽分工和缺口边界。"),
            "supporting_table": {
                "headers": ["系列", "当前主命题", "现在最不该做什么", "哪些必须等待补数"],
                "rows": [
                    [
                        "N（三带）" if str(node.get("series_family", "-")) == "N" else node.get("series_family", "-"),
                        node.get("root_claim", "-"),
                        node.get("what_not_to_do", "-"),
                        node.get("must_wait_for_data", "-"),
                    ]
                    for node in self_thesis_nodes
                ],
            },
            "representative_cases": [],
            "representative_quotes": list(self_strategy_thesis_tree.get("what_current_report_can_already_decide", [])[:3]),
            "closing_implication": "看自己要回答的不是‘谁来承接’，而是‘这一代为什么必须这么分工，以及哪些东西现在先别讲满’。",
        },
        {
            "page_id": "self_portfolio_bandwidth_pages",
            "heading": "#### 科沃斯当前产品带宽与系列分工",
            "page_question": "X / T / N（三带）现在分别站在哪个形态和竞争带里？",
            "lead_judgment": str(self_strategy_thesis.get("n_core_thesis", "看自己不能只看 X/T 旗舰，还要把 N（三带）的 omni / aes / 单机 带宽一起看清楚。")).replace("N 不是一个总桶", "N（三带）不是一个总桶"),
            "supporting_table": {
                "headers": ["系列", "形态", "这一带必须承接什么", "不该再塞什么", "当前缺口会造成什么后果", "为什么重要"],
                "rows": build_self_portfolio_bandwidth_rows(portfolio_generation_strategy),
            },
            "representative_cases": [],
            "representative_quotes": [
                str(item)
                for item in [
                    self_strategy_thesis.get("x_core_thesis"),
                    self_strategy_thesis.get("t_core_thesis"),
                    self_strategy_thesis.get("n_core_thesis"),
                ]
                if item
            ][:4],
            "closing_implication": "这页的作用，是把 X/T/N（三带）和 omni / aes / 单机 的角色关系讲清楚，避免什么都继续塞进旗舰。",
        },
        {
            "page_id": "self_demand_reorder_pages",
            "heading": "#### 需求池如何被重排",
            "page_question": "现在我们的需求池，为什么不该再按功能模块平铺？",
            "lead_judgment": "需求池重排不是因为我们突然想讲框架，而是因为当前已经能确认：底线需求、托管需求、表达需求和远期协同不在一个层级里，谁先解决会直接改变 X/T/N（三带） 的承接边界。",
            "supporting_table": {
                "headers": ["需求层", "当前代表内容", "为什么被重排", "对我们的要求"],
                "rows": build_self_demand_reorder_rows(strategy_translation, generation_comparison, x_packages),
            },
            "representative_cases": [],
            "representative_quotes": list(self_strategy_thesis.get("what_ecovacs_should_not_do", [])[:3]),
            "closing_implication": "需求池重排之后，产品动作、卖点表达和资源投入顺序才会自然对齐。",
        },
        {
            "page_id": "priority_strategy_pages",
            "heading": "## 4. 需求优先级讨论",
            "page_question": "哪些事情该先做，为什么是它而不是别的？",
            "lead_judgment": "优先级不是把所有问题按声量排序，而是先分清哪些是底线、哪些是竞争焦点、哪些只是机会点。",
            "supporting_table": {
                "headers": ["优先级桶", "当前内容", "为什么现在先做", "动作建议"],
                "rows": build_priority_rows(strategy_translation),
            },
            "representative_cases": [],
            "representative_quotes": [str(line) for line in strategy_translation.get("priority_reasoning", [])[:3]],
            "closing_implication": "先做那些会伤害结果信任和托管信任的问题，再谈拉开差异化的机会点。",
        },
        {
            "page_id": "priority_assignment_pages",
            "heading": "#### X/T/N 分工与承接边界",
            "page_question": "为什么不是所有问题都该由 X/T 旗舰系去承接？",
            "lead_judgment": "优先级不是只有“先做什么”，还必须回答“该由谁承接”；否则旗舰会被下探守位和远期方向一起拖重。",
            "supporting_table": {
                "headers": ["需求层", "谁来扛", "动作判断", "需求池信号", "谁不该继续被塞满"],
                "rows": build_priority_assignment_rows(portfolio_generation_strategy),
            },
            "representative_cases": [],
            "representative_quotes": (
                competition_strategy_bridge.get("which_voc_gaps_must_enter_priority", [])[:3]
                or [summarize_demand_status(demand_pool_snapshot, ["清洁效果与水痕污渍", "边角与覆盖率"])]
            ),
            "closing_implication": "这页要把“问题要不要做”升级成“问题该由谁来承接、谁不该被压垮”。",
        },
        {
            "page_id": "roadmap_action_pages",
            "heading": "#### 当前动作 / 路线图",
            "page_question": "当前半年到底该怎么讲、怎么做？",
            "lead_judgment": "路线图页不是时间排布表，而是把当前轮次的主叙事、优先动作和不该提前透支的方向放在一起看。",
            "supporting_table": {
                "headers": ["阶段", "X 当前主讲", "T 当前主讲", "N（三带）当前主讲", "先别讲什么", "当前最大阻塞点"],
                "rows": build_portfolio_roadmap_rows(strategy_translation, portfolio_generation_strategy),
            },
            "representative_cases": [],
            "representative_quotes": (
                [str(row.get("core_blocker", "-")) for row in (portfolio_generation_strategy.get("roadmap_focus_rows", []) or [])[:2]]
                + [str(item) for item in competition_strategy_bridge.get("where_ecovacs_is_following", [])[:2]]
            )[:4],
            "closing_implication": "当前半年不该平均铺开所有议题，而该把最伤害信任的一组问题讲透、修透、验证透。",
        },
        {
            "page_id": "reflection_intro_pages",
            "heading": "## 5. 缺口 / 风险 / 下一步",
            "page_question": "当前这份报告还差什么？",
            "lead_judgment": str(analysis_reflection_report.get("summary_judgment", "当前反思仍待补充。")),
            "supporting_table": {},
            "representative_cases": [],
            "representative_quotes": reflection_priority_pages[:3],
            "closing_implication": "这一章的作用，不是再补一堆说明，而是明确：哪些地方已经够定，哪些地方还不能讲满，下一步该补什么。",
        },
        {
            "page_id": "analysis_reflection_pages",
            "heading": "#### 当前这份分析还差什么",
            "page_question": "当前主要差距到底落在哪几类？",
            "lead_judgment": "这轮最重要的反思，不是报告有没有页，而是：深度、广度、抽象结论和 PPT 汇报感还分别差在哪里。",
            "supporting_table": {
                "headers": ["差距维度", "当前差什么", "为什么重要", "优先改哪页"],
                "rows": [
                    ["深度", "；".join((analysis_reflection_report.get("depth_gaps", []) or [])[:2]), "如果没有第二层论证，顶层判断会显得像拍脑袋。", "行业能力扫描及洞察 / 核心竞品对阵"],
                    ["广度", "；".join((analysis_reflection_report.get("breadth_gaps", []) or [])[:2]), "如果市场/带宽覆盖不完整，前台会自然显得像只讲了一半。", "中国 / 海外 VOC"],
                    ["抽象结论", "；".join((analysis_reflection_report.get("abstraction_gaps", []) or [])[:2]), "如果没有母题和 thesis，竞争和看自己之间会一直像两层表。", "竞争结论 / 看自己"],
                    ["PPT 汇报感", "；".join((analysis_reflection_report.get("ppt_style_gaps", []) or [])[:2]), "如果仍是表格填空式判断，就还不像 PPT 作者本人在讲。", "全章顶层结构"],
                ],
            },
            "representative_cases": [],
            "representative_quotes": (analysis_reflection_report.get("underused_evidence", []) or [])[:3],
            "closing_implication": "这页不是自我批评，而是明确下一轮优化到底该改哪里，才能让这份报告真正像汇报稿而不是分析脚本。",
        },
        {
            "page_id": "data_moves_pages",
            "heading": "#### 当前必须补什么",
            "page_question": "现在最该补的数据和入口是什么？",
            "lead_judgment": "补数工程不能再挂在旁边了，而要直接进入分析主链，因为这些缺口已经开始决定哪些带宽能讲满、哪些只能停在外部门槛。",
            "supporting_table": {
                "headers": ["优先级", "补什么", "为什么现在就得补", "当前状态"],
                "rows": [
                    [
                        str(row.get("priority", "-")),
                        f"{competition_scope_label(str(row.get('competition_scope', '-')))} / {row.get('target_market_scope', '-')}",
                        str(row.get("reason", "-")),
                        str(row.get("current_status", "-")),
                    ]
                    for row in (competition_capture_target_candidates.get("rows", []) or [])[:5]
                ],
            },
            "representative_cases": [],
            "representative_quotes": reflection_next_moves[:3],
            "closing_implication": "这里要明确区分：哪些问题是分析没翻出来，哪些问题是真缺样本，哪些问题已经进入补采执行。",
        },
    ]
    if weak_x_packages:
        weak_package = weak_x_packages[0]
        blocks.insert(
            2,
            {
                "page_id": "x_weak_signal_pages",
                "heading": "#### 表达型弱信号",
                "page_question": "表达型购买动机在 X 系列里现在站到什么程度？",
                "lead_judgment": f"`{weak_package['positioning_name']}` 这类表达型角色当前已经出现，但更像方向性弱信号，还不像 `{ ' / '.join(main_labels[:2]) }` 那样是稳定主购买逻辑。",
                "supporting_table": {
                    "headers": ["当前更像什么角色名", "PPT 映射", "为什么还不是主定位", "代表用户"],
                    "rows": [
                        [
                            weak_package.get("positioning_name", "-"),
                            weak_package.get("canonical_anchor", "-"),
                            weak_package.get("naming_reason", "-"),
                            "；".join(user_title(user) for user in weak_package.get("representative_users", [])[:2]),
                        ]
                    ],
                },
                "representative_cases": [user_title(user) for user in weak_package.get("representative_users", [])[:2]],
                "representative_quotes": weak_package.get("representative_quotes", [])[:2],
                "closing_implication": "这意味着表达型需求当前可以作为高端方向和品牌表达信号来讲，但不该在本轮被写成与主定位同等级的用户定位。",
            },
        )
    metric_lookup = {row["page_id"]: row.get("cards", []) for row in page_metric_cards.get("blocks", []) or []}
    for block in blocks:
        block["metric_cards"] = metric_lookup.get(block["page_id"], [])
    return {"block_count": len(blocks), "blocks": blocks}


def build_judgment_ready_evidence(
    presentation_page_blocks: dict[str, object],
) -> dict[str, object]:
    evidences: list[dict[str, object]] = []
    for block in presentation_page_blocks.get("blocks", []):  # type: ignore[index]
        supporting_passages = [{"passage_text": quote} for quote in block.get("representative_quotes", [])[:2]]
        if not supporting_passages and block.get("supporting_table", {}).get("rows"):
            first_rows = block["supporting_table"]["rows"][:2]
            for row in first_rows:
                supporting_passages.append({"passage_text": "；".join(str(cell) for cell in row[:3] if str(cell).strip())})
        evidence_density = "高" if len(supporting_passages) >= 3 else "中" if len(supporting_passages) == 2 else "低"
        evidences.append(
            {
                "judgment_id": block["page_id"],
                "claim_candidate": block.get("lead_judgment", ""),
                "supporting_passages": supporting_passages[:3],
                "contradiction_passages": [],
                "evidence_density": evidence_density,
            }
        )
    return {"evidence_count": len(evidences), "evidences": evidences}


def render_portfolio_ppt_report(
    *,
    category_name: str,
    time_scope: str,
    market: str | None,
    analysis_goal_text: str,
    style_profile: dict[str, object],
    higher_order_artifacts: dict[str, dict[str, object]],
) -> str:
    banned_phrases = list(style_profile.get("banned_phrases", []))
    report_banned_phrases = banned_phrases + [
        "evidence packet",
        "converged",
        "contested",
        "not_ready",
        "external_only",
        "frontline_mode",
        "weak",
    ]
    series_rows = higher_order_artifacts["series_positioning"].get("series_rows", [])  # type: ignore[index]
    strategy_translation = higher_order_artifacts["strategy_translation"]
    generation_comparison = higher_order_artifacts.get("generation_comparison", {})
    page_blocks = higher_order_artifacts.get("presentation_page_blocks", {}).get("blocks", [])  # type: ignore[index]
    page_block_lookup = {block["page_id"]: block for block in page_blocks}
    master_judgment_tree = higher_order_artifacts.get("master_judgment_tree", {})
    presentation_tree = higher_order_artifacts.get("presentation_tree", {})
    competition_thesis_tree = higher_order_artifacts.get("competition_thesis_tree", {})
    competition_matchup_matrix = higher_order_artifacts.get("competition_matchup_matrix", {})
    user_strategy_convergence_tree = higher_order_artifacts.get("user_strategy_convergence_tree", {})
    user_thesis_tree = higher_order_artifacts.get("user_thesis_tree", {})
    user_insight_exposure_tree = higher_order_artifacts.get("user_insight_exposure_tree", {})
    topic_attention_matrix = higher_order_artifacts.get("topic_attention_matrix", {})
    problem_drilldown_packages = higher_order_artifacts.get("problem_drilldown_packages", {})
    cross_source_interpretation = higher_order_artifacts.get("cross_source_interpretation", {})
    brand_mindshare_map = higher_order_artifacts.get("brand_mindshare_map", {})
    brand_mindshare_judgments = higher_order_artifacts.get("brand_mindshare_judgments", {})
    idea_cluster_judgments = higher_order_artifacts.get("idea_cluster_judgments", {})
    voc_fact_exposure_tree = higher_order_artifacts.get("voc_fact_exposure_tree", {})
    analysis_reflection_report = higher_order_artifacts.get("analysis_reflection_report", {})
    qual_evidence_packet = higher_order_artifacts.get("qual_evidence_packet", {})
    portfolio_generation_strategy = higher_order_artifacts.get("portfolio_generation_strategy", {})
    self_strategy_thesis_tree = higher_order_artifacts.get("self_strategy_thesis_tree", {})
    x_positioning_packages = higher_order_artifacts.get("x_positioning_packages", {}).get("packages", [])  # type: ignore[index]
    x_main_labels = [package["positioning_name"] for package in x_positioning_packages if package.get("positioning_level") == "main_positioning"]
    x_weak_labels = [package["positioning_name"] for package in x_positioning_packages if package.get("positioning_level") == "weak_signal"]
    t_strategy_gap = higher_order_artifacts.get("t_series_concept_map", {}).get("series_strategy_gap", [])  # type: ignore[index]
    generation_rows = {row["series_code"]: row for row in generation_comparison.get("series_rows", []) or []}
    top_problem_packages = strategy_translation.get("top_problem_packages", [])
    priority_buckets = strategy_translation.get("priority_buckets", {})
    self_thesis_nodes = self_strategy_thesis_tree.get("thesis_nodes", []) or []
    competition_thesis_nodes = competition_thesis_tree.get("thesis_nodes", []) or []
    competition_market_refs = competition_thesis_tree.get("market_refs", []) or []
    competition_matchup_rows = competition_matchup_matrix.get("rows", []) or []

    def cell_text(value: object) -> str:
        if value is None:
            return "-"
        if isinstance(value, str):
            cleaned = sanitize_presentation_text(" ".join(value.replace("\n", " ").split()).replace("|", " / ").replace("`", ""), report_banned_phrases)
            return cleaned or "-"
        if isinstance(value, list):
            parts = [cell_text(item) for item in value if cell_text(item) != "-"]
            return "；".join(parts[:3]) if parts else "-"
        if isinstance(value, dict):
            parts = [cell_text(item) for item in value.values()]
            parts = [part for part in parts if part != "-"]
            return "；".join(parts[:3]) if parts else "-"
        return cell_text(str(value))

    def append_page_block(lines: list[str], block: dict[str, object] | None) -> None:
        if not block:
            return
        lines.append(block["heading"])
        lines.append("")
        lead = cell_text(block.get("lead_judgment"))
        if lead != "-":
            lines.append(f"- {lead}")
            lines.append("")
        metric_cards = block.get("metric_cards", []) or []
        if metric_cards:
            lines.append("| 抽象统计 | 当前值 | 说明 |")
            lines.append("| --- | --- | --- |")
            for card in metric_cards:
                lines.append(
                    f"| {cell_text(card.get('title'))} | {cell_text(card.get('metric_value'))} | {cell_text(card.get('interpretation'))} |"
                )
            lines.append("")
        table = block.get("supporting_table") or {}
        headers = table.get("headers") or []
        rows = table.get("rows") or []
        if headers and rows:
            lines.append(markdown_table(headers, [[cell_text(cell) for cell in row] for row in rows]))
            lines.append("")
        for card in block.get("detail_cards", []) or []:
            lines.append(f"#### {card['title']}")
            lines.append("")
            card_judgment = cell_text(card.get("lead_judgment"))
            if card_judgment != "-":
                lines.append(f"- {card_judgment}")
            card_metric_cards = card.get("metric_cards", []) or []
            if card_metric_cards:
                lines.append("| 统计维度 | 当前值 | 说明 |")
                lines.append("| --- | --- | --- |")
                for metric_card in card_metric_cards:
                    lines.append(
                        f"| {cell_text(metric_card.get('title'))} | {cell_text(metric_card.get('metric_value'))} | {cell_text(metric_card.get('interpretation'))} |"
                    )
                lines.append("")
            detail_table = card.get("detail_table") or {}
            if detail_table.get("headers") and detail_table.get("rows"):
                lines.append(markdown_table(detail_table["headers"], [[cell_text(cell) for cell in row] for row in detail_table["rows"]]))
                lines.append("")
            for bullet in card.get("bullets", []) or []:
                bullet_text = cell_text(bullet)
                if bullet_text != "-":
                    lines.append(f"- {bullet_text}")
            quotes = [cell_text(quote) for quote in (card.get("representative_quotes", []) or []) if cell_text(quote) != "-"]
            if quotes:
                lines.append(f"- 证据锚点：{'；'.join(quotes[:2])}")
            lines.append("")
        closing = cell_text(block.get("closing_implication"))
        if closing != "-":
            if closing.startswith("这意味着"):
                lines.append(f"- {closing}")
            else:
                lines.append(f"- 这意味着：{closing}")
            lines.append("")

    branch_lookup = {
        str(branch.get("branch_name", "")): branch
        for branch in (master_judgment_tree.get("branches", []) or [])
    }
    user_converged_nodes = user_strategy_convergence_tree.get("converged_nodes", []) or []
    user_contested_nodes = user_strategy_convergence_tree.get("contested_nodes", []) or []
    user_not_ready_nodes = user_strategy_convergence_tree.get("not_ready_nodes", []) or []
    all_user_convergence_nodes = user_converged_nodes + user_contested_nodes + user_not_ready_nodes
    cross_source_rows = cross_source_interpretation.get("interpretations", []) or []
    cross_source_lookup = {
        str(row.get("theme_name", "")): row
        for row in cross_source_rows
    }
    brand_rows = brand_mindshare_judgments.get("judgments", []) or []
    brand_map = brand_mindshare_map.get("brands", {}) or {}
    idea_rows = idea_cluster_judgments.get("judgments", []) or []
    external_only_nodes = voc_fact_exposure_tree.get("external_only_nodes", []) or []
    missing_scope_nodes = voc_fact_exposure_tree.get("missing_scope_nodes", []) or []
    signal_nodes = voc_fact_exposure_tree.get("signal_nodes", []) or []
    market_summary_rows = analysis_reflection_report.get("market_summary_rows", []) or []
    market_scope_lookup = {str(row.get("market_scope", "")): row for row in market_summary_rows}
    reflection_next_moves = analysis_reflection_report.get("next_data_moves", []) or []
    next_data_moves = reflection_next_moves
    topic_summary_rows = topic_attention_matrix.get("topic_summary_rows", []) or []
    drilldown_rows = problem_drilldown_packages.get("rows", []) or []
    packet_rows = qual_evidence_packet.get("packets", []) or []
    packet_band_counter = Counter(
        str(row.get("user_band") or row.get("series_family") or "-")
        for row in packet_rows
    )
    portfolio_bandwidth_rows = portfolio_generation_strategy.get("portfolio_bandwidth_rows", []) or []
    resolved_time_scope = cell_text(time_scope if time_scope and time_scope != "待补充" else "当前 runtime 汇总周期")
    resolved_market = cell_text(market or "ALL")

    def clean_reason_lines(reasons: list[object], *, keep_negative: bool) -> list[str]:
        negative_markers = ("靠后", "差评", "退货", "放弃", "劝退", "噪音大", "体验差", "担心", "停滞", "麻烦", "口碑不佳", "不明所以")
        positive_markers = ("好看", "高端", "高级", "年轻化", "功能多", "售后好", "技术先进", "专业", "有优势", "新颖", "第一", "高端/奢华感")
        cleaned: list[str] = []
        for reason in reasons:
            text = cell_text(reason)
            if text == "-":
                continue
            has_negative = any(marker in text for marker in negative_markers)
            has_positive = any(marker in text for marker in positive_markers)
            if keep_negative and has_positive and not has_negative:
                continue
            if not keep_negative and has_negative and not has_positive:
                continue
            cleaned.append(text)
        fallback = [cell_text(item) for item in reasons if cell_text(item) != "-"]
        return dedupe_preserve_order(cleaned or fallback)[:2]

    def brand_implication_text(brand: str) -> str:
        implication_lookup = {
            "科沃斯": "科沃斯不能再只吃品牌认知，要把具体产品体验讲成可信答案，否则品牌资产会继续分化。",
            "石头": "石头代表专业和参数标杆，意味着科沃斯必须拿稳定结果和托管可信去正面对打。",
            "追觅": "追觅代表高端表达和新技术溢价，意味着科沃斯不能只讲稳，还要回答为什么值得被偏爱。",
            "云鲸": "云鲸代表拖地与水渍控制心智，意味着科沃斯要正面回答拖地结果和长期稳定。",
            "大疆": "大疆代表跨界科技光环，意味着科沃斯要守住专业可信，不让“会不会做扫地机”成为疑问。",
            "小米": "小米代表入门和性价比心智，意味着科沃斯不能用旗舰叙事去解释入门守位。",
        }
        return implication_lookup.get(brand, "这意味着科沃斯需要更明确回答它为什么值得被优先想到。")

    def find_user_node(keyword: str) -> dict[str, object]:
        for node in all_user_convergence_nodes:
            if keyword in str(node.get("concept_name", "")):
                return node
        return {}

    def find_market_scope_gap(keyword: str) -> str:
        for node in external_only_nodes + missing_scope_nodes:
            label = str(node.get("node_label", ""))
            if keyword in label:
                return cell_text(node.get("summary"))
        return "-"

    def summarize_problem_package(problem_name: str) -> str:
        for row in drilldown_rows:
            if cell_text(row.get("problem_name")) == problem_name and cell_text(row.get("market_scope")) == "中国":
                return cell_text(row.get("reasonableness_judgment"))
        for row in drilldown_rows:
            if cell_text(row.get("problem_name")) == problem_name:
                return cell_text(row.get("reasonableness_judgment"))
        return "-"

    def summarize_problem_boundary(problem_name: str) -> str:
        interpretation = cross_source_lookup.get(problem_name, {})
        resolution = str(interpretation.get("resolution_status", ""))
        if resolution == "accepted":
            next_step = cell_text(interpretation.get("next_validation_step"))
            return "-" if next_step in {"-", "可以直接进入优先级讨论与策略翻译。"} else next_step
        if interpretation:
            return cell_text(interpretation.get("next_validation_step"))
        return "-"

    def market_gap_text(keyword: str) -> str:
        for node in external_only_nodes + missing_scope_nodes:
            if keyword in str(node.get("node_label", "")):
                return compact_cell(node.get("summary"), soft_limit=24, hard_limit=40)
        return "-"

    def compact_cell(value: object, *, soft_limit: int = 32, hard_limit: int = 60) -> str:
        text = cell_text(value)
        if text == "-":
            return text
        candidates = [part.strip() for part in re.split(r"[；。]", text) if part.strip()]
        chosen = candidates[0] if candidates else text
        if len(chosen) > hard_limit:
            return chosen[: hard_limit - 1] + "…"
        if len(chosen) > soft_limit and len(candidates) > 1:
            return chosen[: soft_limit - 1] + "…"
        return chosen

    def compact_join(values: list[object], *, limit: int = 2, soft_limit: int = 32, hard_limit: int = 60) -> str:
        items = [
            compact_cell(value, soft_limit=soft_limit, hard_limit=hard_limit)
            for value in values
            if compact_cell(value, soft_limit=soft_limit, hard_limit=hard_limit) != "-"
        ]
        return "；".join(dedupe_preserve_order(items)[:limit]) if items else "-"

    def pick_positive_topic(series_family: str, *, user_band: str | None = None) -> dict[str, object]:
        rows = []
        for row in topic_summary_rows:
            if str(row.get("series_family", "")) != series_family:
                continue
            if user_band is not None and str(row.get("user_band", "")) != user_band:
                continue
            if row.get("cohort_scope") and str(row.get("cohort_scope")) != "科沃斯样本":
                continue
            rows.append(row)
        rows = [
            row
            for row in rows
            if float(row.get("positive_rate", 0.0) or 0.0) >= float(row.get("negative_rate", 0.0) or 0.0)
        ]
        rows.sort(key=lambda row: (-float(row.get("mention_rate", 0.0) or 0.0), -int(row.get("mention_count", 0) or 0)))
        return rows[0] if rows else {}

    def pick_negative_topic(series_family: str, *, user_band: str | None = None) -> dict[str, object]:
        rows = []
        for row in topic_summary_rows:
            if str(row.get("series_family", "")) != series_family:
                continue
            if user_band is not None and str(row.get("user_band", "")) != user_band:
                continue
            if row.get("cohort_scope") and str(row.get("cohort_scope")) != "科沃斯样本":
                continue
            rows.append(row)
        rows = [
            row
            for row in rows
            if float(row.get("negative_rate", 0.0) or 0.0) > 0
        ]
        rows.sort(key=lambda row: (-float(row.get("negative_rate", 0.0) or 0.0), -int(row.get("negative_count", 0) or 0), -int(row.get("mention_count", 0) or 0)))
        return rows[0] if rows else {}

    def maturity_label(mode: str) -> str:
        mapping = {
            "self_stable": "可正式判断",
            "external_only": "外部门槛",
            "missing": "真实缺数据",
        }
        return mapping.get(mode, "仅方向判断")

    def build_frontstage_summary_rows() -> list[list[str]]:
        top_priority = " / ".join((strategy_translation.get("priority_buckets", {}) or {}).get("底线问题", [])[:3]) or "-"
        return [
            [
                "用户判断不是一套总画像，而是 X / T / N 三套逻辑。",
                compact_cell(master_judgment_tree.get("root_thesis"), soft_limit=30, hard_limit=50),
                compact_join(
                    [
                        find_user_node("X 为什么会分成").get("why_converged"),
                        find_user_node("T 为什么不是一个总 archetype").get("why_converged"),
                        find_user_node("N 为什么不能先压成一个总用户 archetype").get("why_converged"),
                    ],
                    limit=2,
                    soft_limit=30,
                    hard_limit=50,
                ),
                compact_join(
                    [
                        find_user_node("X 为什么会分成").get("why_not_other"),
                        find_user_node("T 为什么不是一个总 archetype").get("why_not_other"),
                        find_user_node("N 为什么不能先压成一个总用户 archetype").get("why_not_other"),
                    ],
                    limit=1,
                    soft_limit=30,
                    hard_limit=50,
                ),
                "X/T 承接主叙事，N 按三带拆开承接。",
            ],
            [
                "当前优先修的不是所有高频问题，而是最伤信任的一组。",
                compact_cell(f"当前优先问题收在 {top_priority}。", soft_limit=30, hard_limit=50),
                compact_cell((strategy_translation.get("priority_reasoning", []) or ["先做那些会伤害结果信任与托管信任的问题。"])[0], soft_limit=30, hard_limit=50),
                "不是谁声量高就先做谁。",
                "X/T 先扛清洁底线与托管信任。",
            ],
            [
                "竞争真正卷的不是参数，而是托管、稳定和带宽完整度。",
                compact_join([row.get("root_claim") for row in competition_thesis_nodes], limit=2, soft_limit=30, hard_limit=50),
                compact_join([row.get("why_this_is_the_bar") for row in competition_thesis_nodes], limit=2, soft_limit=30, hard_limit=50),
                compact_join([row.get("what_not_to_confuse") for row in competition_thesis_nodes], limit=1, soft_limit=30, hard_limit=50),
                "X 守高端托管，T 守主销默认答案，N 守带宽完整度。",
            ],
            [
                "科沃斯当前最该做的是按 X / T / N 明确分工，而不是继续互相补位。",
                compact_join([row.get("root_claim") for row in self_thesis_nodes], limit=2, soft_limit=30, hard_limit=50),
                compact_join([row.get("why_this_is_the_role") for row in self_thesis_nodes], limit=2, soft_limit=30, hard_limit=50),
                compact_join([row.get("what_not_to_do") for row in self_thesis_nodes], limit=1, soft_limit=30, hard_limit=50),
                "先把系列角色定清，再排资源与动作。",
            ],
            [
                "当前最该被前置的不是更多判断，而是真缺数据。",
                "N_aes 中国、N_omni 中国、T_omni 海外都还不能讲满。",
                compact_join(
                    [
                        market_gap_text("N_aes（AES 入门带基站） / 中国"),
                        market_gap_text("N_omni（omni 下探） / 中国"),
                        market_gap_text("T_omni（主销 omni） / 海外"),
                    ],
                    limit=2,
                    soft_limit=30,
                    hard_limit=50,
                ),
                "这些不是分析没翻出来，而是当前真源还不够。",
                "补数计划必须直接进入下一轮主链。",
            ],
        ]

    def build_frontstage_series_comparison_rows() -> list[list[str]]:
        specs = [
            ("X", None, "高端托管，不是继续堆旗舰标签", "定性 + 问卷 + VOC", "中国主，ALL辅", "可正式判断", "少操心、少返工、真托管"),
            ("T", None, "主销默认答案，不是更炫新能力", "定性 + 问卷 + VOC", "中国主，ALL辅", "可正式判断", "结果更稳、少返工、少维护"),
            ("N_single", "N_single", "预算守位带", "中国 VOC 为主", "中国", "仅方向判断", "守住基础完成率"),
            ("N_aes", "N_aes", "入门带基站承接位（海外 / ALL）", "海外 / ALL VOC + 外部门槛", "海外 / ALL", "外部门槛", "补入门带基站承接位"),
            ("N_omni", "N_omni", "边界位，先不伪造完整画像", "竞品池 / 外部门槛", "中国 / ALL / 海外", "真实缺数据", "先补中国自家样本"),
        ]
        rows: list[list[str]] = []
        for label, band, thesis, evidence_source, market_scope_label, maturity, action in specs:
            if label == "X":
                negative_row = pick_negative_topic("X")
                positive_row = pick_positive_topic("X")
            elif label == "T":
                negative_row = pick_negative_topic("T")
                positive_row = pick_positive_topic("T")
            elif label == "N_single":
                negative_row = pick_negative_topic("N", user_band="N_single")
                positive_row = pick_positive_topic("N", user_band="N_single")
            elif label == "N_aes":
                negative_row = pick_negative_topic("N", user_band="N_aes")
                positive_row = pick_positive_topic("N", user_band="N_aes")
            else:
                negative_row = {}
                positive_row = {}
            rows.append(
                [
                    label,
                    compact_cell(thesis, soft_limit=32, hard_limit=60),
                    compact_cell(negative_row.get("topic_name", "缺稳定自家样本"), soft_limit=16, hard_limit=28),
                    compact_cell(positive_row.get("topic_name", "-"), soft_limit=16, hard_limit=28),
                    evidence_source,
                    market_scope_label,
                    maturity,
                    action,
                ]
            )
        return rows

    def build_frontstage_gap_upgrade_rows() -> list[list[str]]:
        return [
            ["N_omni / 中国 / 自家 VOC", "真实缺数据", "卡住 N_omni 的正式用户判断", "补中国自家 VOC 与真实用户反馈入口", "把 N_omni 升级成正式承接位判断"],
            ["N_aes / 中国 / 自家 VOC", "真实缺数据", "卡住 N_aes 的中国承接位判断", "补中国自家 VOC 与带基站入门位样本", "把 N_aes 升级成中国承接位判断"],
            ["T_omni / 海外", "真实缺数据", "卡住海外主销 omni 的竞争判断", "补海外主销 omni 样本", "把 T 的海外判断升级成正式比较"],
            [f"N（三带）直连定性", f"结构性缺口（X={packet_band_counter.get('X', 0)} / T={packet_band_counter.get('T', 0)} / N_omni={packet_band_counter.get('N_omni', 0)})", "卡住 N 带宽的解释层上台", "补与 X / T 同等级的问卷与定性直连证据", "把 N 从 VOC-only 方向判断升级成可讲机制解释"],
        ]

    def build_brand_support_rows() -> list[list[str]]:
        negative_markers = ("靠后", "差评", "退货", "放弃", "劝退", "噪音大", "体验差", "担心", "停滞", "麻烦", "口碑不佳", "不明所以")
        positive_markers = ("好看", "高端", "高级", "年轻化", "功能多", "售后好", "技术先进", "专业", "有优势", "新颖", "第一", "高端/奢华感")
        implication_lookup = {
            "科沃斯": "要把品牌认知翻成可信体验答案。",
            "石头": "要正面回答专业与稳定结果。",
            "追觅": "要回答为什么值得被偏爱。",
            "云鲸": "要正面回答拖地结果与稳定。",
            "大疆": "要守住专业可信，不被跨界光环压住。",
            "小米": "不要用旗舰叙事解释入门守位。",
        }
        rows: list[list[str]] = []
        for row in brand_rows[:6]:
            brand = cell_text(row.get("brand"))
            payload = brand_map.get(brand, {}) if isinstance(brand_map, dict) else {}
            choose_raw = (payload.get("trust_reason") or row.get("why_choose") or [])
            reject_raw = (payload.get("rejection_reason") or row.get("why_reject") or [])
            choose_lines = []
            reject_lines = []
            for reason in choose_raw:
                text = compact_cell(reason, soft_limit=18, hard_limit=32)
                if text != "-" and not any(marker in text for marker in negative_markers):
                    choose_lines.append(text)
            for reason in reject_raw:
                text = compact_cell(reason, soft_limit=18, hard_limit=32)
                if text != "-" and (any(marker in text for marker in negative_markers) or not any(marker in text for marker in positive_markers)):
                    reject_lines.append(text)
            rows.append(
                [
                    brand,
                    compact_cell(row.get("one_line_label", payload.get("core_label")), soft_limit=18, hard_limit=32),
                    "；".join(dedupe_preserve_order(choose_lines)[:2]) if choose_lines else "-",
                    "；".join(dedupe_preserve_order(reject_lines)[:2]) if reject_lines else "-",
                    implication_lookup.get(brand, "需要更明确回答为什么值得被优先想到。"),
                ]
            )
        return rows

    def build_idea_support_rows() -> list[list[str]]:
        rows: list[list[str]] = []
        for row in idea_rows[:6]:
            rows.append(
                [
                    compact_cell(row.get("theme"), soft_limit=10, hard_limit=18),
                    "当前底线延伸项" if cell_text(row.get("now_or_later")) == "现在就该做" else "中长期差异化项",
                    compact_cell(row.get("why_now"), soft_limit=20, hard_limit=32),
                    "现在做的直接挂痛点与完成率；后置项不要提前透支成本代主卖点。",
                ]
            )
        return rows

    def build_frontstage_user_root_rows() -> list[list[str]]:
        x_user_node = find_user_node("X 为什么会分成")
        t_user_node = find_user_node("T 为什么不是一个总 archetype")
        n_user_node = find_user_node("N 为什么不能先压成一个总用户 archetype")
        return [
            [
                "X 代表什么",
                "高端托管",
                compact_join(
                    [
                        x_user_node.get("lead_judgment"),
                        x_user_node.get("why_converged"),
                    ],
                    limit=1,
                    soft_limit=24,
                    hard_limit=32,
                ),
                "表达型信号先别升主定位",
            ],
            [
                "T 代表什么",
                "主销默认答案",
                compact_join(
                    [
                        t_user_node.get("lead_judgment"),
                        t_user_node.get("why_converged"),
                    ],
                    limit=1,
                    soft_limit=24,
                    hard_limit=32,
                ),
                compact_cell(market_gap_text("T_omni（主销 omni） / 海外"), soft_limit=20, hard_limit=32),
            ],
            [
                "N 为什么拆三带",
                "带宽分工，不是总 N",
                compact_join(
                    [
                        n_user_node.get("lead_judgment"),
                        n_user_node.get("why_converged"),
                    ],
                    limit=1,
                    soft_limit=24,
                    hard_limit=32,
                ),
                "N_aes / N_omni 先保留边界",
            ],
        ]

    def build_frontstage_user_judgment_rows() -> list[list[str]]:
        x_user_node = find_user_node("X 为什么会分成")
        t_user_node = find_user_node("T 为什么不是一个总 archetype")
        n_user_node = find_user_node("N 为什么不能先压成一个总用户 archetype")
        weak_node = next(iter(user_strategy_convergence_tree.get("not_ready_nodes", []) or []), {})
        return [
            [
                "X",
                "高端托管，不是堆参数",
                compact_join([x_user_node.get("why_converged")], limit=1, soft_limit=18, hard_limit=28),
                compact_join([x_user_node.get("why_not_other")], limit=1, soft_limit=16, hard_limit=24),
                compact_cell(weak_node.get("lead_judgment"), soft_limit=20, hard_limit=32),
            ],
            [
                "T",
                "主销默认答案",
                compact_join([t_user_node.get("why_converged")], limit=1, soft_limit=18, hard_limit=28),
                compact_join([t_user_node.get("why_not_other")], limit=1, soft_limit=16, hard_limit=24),
                "维护 / 基站仍偏工作假设",
            ],
            [
                "N",
                "三带分工，不是总桶",
                compact_join([n_user_node.get("why_converged")], limit=1, soft_limit=18, hard_limit=28),
                compact_join([n_user_node.get("why_not_other")], limit=1, soft_limit=16, hard_limit=24),
                "N_aes / N_omni 先保留边界",
            ],
        ]

    def build_frontstage_user_drilldown_rows() -> list[list[str]]:
        preferred_specs = [
            ("X", None, "中国", "污渍问题"),
            ("X", None, "中国", "边角问题"),
            ("T", None, "中国", "污渍问题"),
            ("N", "N_single", "中国", "故障与可靠性"),
            ("N", "N_aes", "海外", "智能交互/地图"),
        ]
        rows: list[list[str]] = []
        for series_family, user_band, market_scope, problem_name in preferred_specs:
            match = next(
                (
                    row
                    for row in drilldown_rows
                    if str(row.get("series_family", "")) == series_family
                    and (user_band is None or str(row.get("user_band", "")) == user_band)
                    and str(row.get("market_scope", "")) == market_scope
                    and str(row.get("problem_name", "")) == problem_name
                ),
                None,
            )
            if not match:
                continue
            type_top = ((match.get("type_breakdown", []) or [{}])[0]).get("label", "-")
            scene_top = ((match.get("scene_breakdown", []) or [{}])[0]).get("label", "-")
            cond_top = ((match.get("working_condition_breakdown", []) or [{}])[0]).get("label", "-")
            effect_top = ((match.get("effect_expectation_breakdown", []) or [{}])[0]).get("label", "-")
            rows.append(
                [
                    compact_cell(problem_name, soft_limit=12, hard_limit=20),
                    compact_cell(type_top, soft_limit=14, hard_limit=22),
                    compact_cell(scene_top, soft_limit=12, hard_limit=20),
                    compact_cell(cond_top, soft_limit=12, hard_limit=20),
                    compact_cell(effect_top if effect_top != "-" else match.get("reasonableness_judgment"), soft_limit=16, hard_limit=28),
                    compact_cell(match.get("reasonableness_judgment"), soft_limit=18, hard_limit=30),
                ]
            )
        return rows

    def build_frontstage_user_boundary_rows() -> list[list[str]]:
        return [
            [
                "N_aes / 中国",
                "外部门槛",
                compact_cell(market_gap_text("N_aes（AES 入门带基站） / 中国"), soft_limit=18, hard_limit=30),
                "当前只允许讲外部门槛",
            ],
            [
                "N_omni / 中国",
                "真实缺数据",
                compact_cell(market_gap_text("N_omni（omni 下探） / 中国"), soft_limit=18, hard_limit=30),
                "当前只允许讲边界与补数方向",
            ],
            [
                "N（三带）直连定性",
                "结构性缺口",
                "N 的直连定性明显弱于 X / T",
                "当前只允许讲带宽方向判断",
            ],
            [
                "科技表达弱信号",
                "弱信号",
                "当前还不足以升成主定位",
                "当前只允许讲高端表达加分项",
            ],
        ]

    summary_rows = build_frontstage_summary_rows()
    series_comparison_rows = build_frontstage_series_comparison_rows()
    user_root_rows = build_frontstage_user_root_rows()
    user_judgment_rows = build_frontstage_user_judgment_rows()
    user_drilldown_rows = build_frontstage_user_drilldown_rows()
    user_boundary_rows = build_frontstage_user_boundary_rows()
    gap_upgrade_rows = build_frontstage_gap_upgrade_rows()
    problem_evidence_rows = [
        ["清洁效果与水痕污渍", compact_cell(cross_source_lookup.get("清洁效果与水痕污渍", {}).get("best_explanation"), soft_limit=24, hard_limit=40), "VOC + 跨源解释", "X / T", "P0", compact_cell(summarize_problem_boundary("清洁效果与水痕污渍"), soft_limit=20, hard_limit=32)],
        ["边角与覆盖率", compact_cell(cross_source_lookup.get("边角与覆盖率", {}).get("best_explanation"), soft_limit=24, hard_limit=40), "VOC + 跨源解释", "X / T / N_single / N_aes", "P0", compact_cell(summarize_problem_boundary("边角与覆盖率"), soft_limit=20, hard_limit=32)],
        ["噪音体验", compact_cell(cross_source_lookup.get("噪音体验", {}).get("best_explanation"), soft_limit=24, hard_limit=40), "跨源解释 + 待补证", "T / N_single", "P1", compact_cell(summarize_problem_boundary("噪音体验"), soft_limit=20, hard_limit=32)],
        ["智能 / App / 语音 / 地图", compact_cell(cross_source_lookup.get("智能/App/语音/地图", {}).get("best_explanation"), soft_limit=24, hard_limit=40), "跨源解释 + 待补证", "N_aes / T", "P1", compact_cell(summarize_problem_boundary("智能/App/语音/地图"), soft_limit=20, hard_limit=32)],
        ["维护与基站操作", compact_cell(cross_source_lookup.get("维护与基站操作", {}).get("best_explanation"), soft_limit=24, hard_limit=40), "人物 / JTBD + 待补证", "X / T", "仅工作假设", compact_cell(summarize_problem_boundary("维护与基站操作"), soft_limit=20, hard_limit=32)],
        ["避障越障与卡困", compact_cell(cross_source_lookup.get("避障越障与卡困", {}).get("best_explanation"), soft_limit=24, hard_limit=40), "跨源解释 + 待补证", "N / T", "仅工作假设", compact_cell(summarize_problem_boundary("避障越障与卡困"), soft_limit=20, hard_limit=32)],
    ]

    competition_threshold_rows = [
        [
            compact_cell(row.get("thesis_name"), soft_limit=14, hard_limit=24),
            compact_cell(row.get("root_claim"), soft_limit=30, hard_limit=50),
            compact_cell(row.get("why_this_is_the_bar"), soft_limit=28, hard_limit=44),
            compact_cell(row.get("what_not_to_confuse"), soft_limit=24, hard_limit=40),
            compact_join(row.get("scope_refs", []) or [], limit=3, soft_limit=10, hard_limit=20),
        ]
        for row in competition_thesis_nodes
    ]

    market_ref_lookup = {str(row.get("competition_scope", "")): row for row in competition_market_refs}
    wrong_battle_lookup = {
        "X_omni（旗舰 omni）": "别把高端竞争讲成参数堆料战。",
        "T_omni（主销 omni）": "别把主销 omni 讲成高端黑科技战。",
        "N_omni（omni 下探）": "别把 omni 下探讲成伪高端。",
        "N_aes（AES 入门带基站）": "别把入门带基站讲成高端能力战。",
        "N_single（低价单机守位）": "别把单机守位讲成高端体验战。",
    }
    competition_band_rows = []
    for row in competition_matchup_rows:
        scope_label = str(row.get("competition_scope", ""))
        scope_code = scope_label.split("（", 1)[0]
        market_ref = market_ref_lookup.get(scope_code, {})
        competition_band_rows.append(
            [
                scope_label,
                compact_cell(row.get("competitor_product_name"), soft_limit=14, hard_limit=24),
                compact_cell(row.get("headline_capabilities"), soft_limit=28, hard_limit=44),
                compact_cell(wrong_battle_lookup.get(scope_label, row.get("why_this_matchup")), soft_limit=24, hard_limit=40),
                compact_cell(row.get("voc_risk_to_watch"), soft_limit=18, hard_limit=28),
                maturity_label(str(market_ref.get("frontline_mode", ""))),
            ]
        )

    competition_implication_rows = [
        [
            "X" if cell_text(row.get("series_family")) == "X" else "T" if cell_text(row.get("series_family")) == "T" else "N（三带）",
            compact_cell(row.get("root_claim"), soft_limit=30, hard_limit=50),
            compact_cell(row.get("what_not_to_do"), soft_limit=24, hard_limit=40),
            compact_cell(row.get("must_wait_for_data"), soft_limit=24, hard_limit=40),
        ]
        for row in self_thesis_nodes
    ]

    x_band_row = next((row for row in portfolio_bandwidth_rows if str(row.get("series_family")) == "X"), {})
    t_band_row = next((row for row in portfolio_bandwidth_rows if str(row.get("series_family")) == "T"), {})
    n_band_rows = [row for row in portfolio_bandwidth_rows if str(row.get("series_family")) == "N"]
    role_rows = [
        [
            "X",
            compact_cell(x_band_row.get("must_carry"), soft_limit=28, hard_limit=44),
            compact_cell(x_band_row.get("must_not_carry"), soft_limit=24, hard_limit=40),
            compact_cell(x_band_row.get("portfolio_gap"), soft_limit=28, hard_limit=44),
            compact_join((portfolio_generation_strategy.get("shape_level_not_now", []) or []), limit=3, soft_limit=12, hard_limit=24),
        ],
        [
            "T",
            compact_cell(t_band_row.get("must_carry"), soft_limit=28, hard_limit=44),
            compact_cell(t_band_row.get("must_not_carry"), soft_limit=24, hard_limit=40),
            compact_cell(t_band_row.get("portfolio_gap"), soft_limit=28, hard_limit=44),
            compact_join((portfolio_generation_strategy.get("shape_level_not_now", []) or []), limit=3, soft_limit=12, hard_limit=24),
        ],
        [
            "N（三带）",
            compact_join([row.get("must_carry") for row in n_band_rows], limit=2, soft_limit=28, hard_limit=44),
            "不要继续让 X/T 替 N 说话。",
            compact_join([row.get("portfolio_gap") for row in n_band_rows], limit=2, soft_limit=28, hard_limit=44),
            compact_join((portfolio_generation_strategy.get("shape_level_not_now", []) or []), limit=3, soft_limit=12, hard_limit=24),
        ],
    ]

    brand_support_rows = build_brand_support_rows()
    idea_support_rows = build_idea_support_rows()
    appendix_source_rows = [
        ["市场口径", compact_cell(market or "ALL", soft_limit=16, hard_limit=24), "当前主报告引用范围"],
        ["分析周期", compact_cell(time_scope if time_scope and time_scope != "待补充" else "全量已落盘样本周期", soft_limit=18, hard_limit=28), "当前主报告显示周期"],
        ["证据来源", "定性 / 问卷 / VOC / 外部门槛", "用于区分正式判断与方向判断"],
        ["成熟度定义", "可正式判断 / 仅方向判断 / 外部门槛 / 真实缺数据", "主报告统一口径"],
    ]

    lines = [
        f"# {category_name} 正式汇报稿",
        "",
        "## 0. 执行摘要",
        "",
        f"- {cell_text(master_judgment_tree.get('summary_judgment', '当前最核心的结论仍待补充。'))}",
        f"- {cell_text(master_judgment_tree.get('root_thesis', '用户判断、竞争门槛和产品分工需要被放到同一条判断链里。'))}",
        "",
        markdown_table(["一级判断", "当前结论", "核心依据", "主要边界", "对分工意味着什么"], summary_rows),
        "",
        "## 1. 结论适用范围",
        "",
        markdown_table(
            ["口径项", "当前值", "说明"],
            appendix_source_rows
            + [
                ["中国状态", compact_cell(market_scope_lookup.get('中国', {}).get('status_text', '待补充'), soft_limit=16, hard_limit=24), "当前中国口径状态"],
                ["海外状态", compact_cell(market_scope_lookup.get('海外', {}).get('status_text', '待补充'), soft_limit=16, hard_limit=24), "当前海外口径状态"],
                ["问题节点", f"{len(signal_nodes)} / {len(external_only_nodes)} / {len(missing_scope_nodes)}", "稳定 / 外部门槛 / 真实缺口"],
            ],
        ),
        "",
        "## 2. 看用户",
        "",
        "### 2.0 用户根判断",
        "",
        markdown_table(["根判断", "一句话结论", "核心支撑", "当前边界"], user_root_rows),
        "",
        "### 2.1 X / T / N 总对比表",
        "",
        markdown_table(["对象", "用户主命题", "最伤问题", "最稳锚点", "证据来源", "市场口径", "成熟度", "当前动作"], series_comparison_rows),
        "",
        "### 2.2 系列判断表",
        "",
        markdown_table(["对象", "当前稳定结论", "为什么成立", "不要误讲成什么", "当前不能讲满"], user_judgment_rows),
        "",
        "### 2.3 关键问题证据表",
        "",
        markdown_table(["问题", "伤害的是", "主要证据", "影响对象", "优先级", "当前边界"], problem_evidence_rows),
        "",
        "### 2.4 问题下钻表",
        "",
        markdown_table(["问题", "主要类型", "主要场景", "主要工况", "用户期待", "当前判断"], user_drilldown_rows),
        "",
        "### 2.5 边界与不能讲满",
        "",
        markdown_table(["对象 / 范围", "当前状态", "为什么不能讲满", "当前允许怎么讲"], user_boundary_rows),
        "",
        "### 2.6 真缺口与补数动作",
        "",
        markdown_table(["缺口", "当前状态", "卡住哪条结论", "补什么", "补完后能升级什么"], gap_upgrade_rows[:3] + [gap_upgrade_rows[3]]),
        "",
        "### 2.7 本章小结",
        "",
        "- 已确定：X 是高端托管，T 是主销默认答案，N 需要拆成三带。",
        "- 先别讲满：N_aes / 中国、N_omni / 中国、N（三带）直连定性当前都还不够。",
        "- 下一步最该补：先补 N_omni 中国、N_aes 中国，再补 N 的直连定性。",
        "",
        "## 3. 看竞争",
        "",
        "### 3.1 竞争门槛总表",
        "",
        markdown_table(["竞争门槛", "当前结论", "为什么成立", "不能讲歪成什么", "关联竞争带"], competition_threshold_rows),
        "",
        "### 3.2 竞争带总对比表",
        "",
        markdown_table(["竞争带", "真正对手", "真正战场", "不能讲歪成什么", "当前最该防什么", "当前状态"], competition_band_rows),
        "",
        "### 3.3 竞争对我方意味着什么",
        "",
        markdown_table(["对象", "当前必须回答什么", "当前不该怎么讲", "当前边界"], competition_implication_rows),
        "",
        "### 3.4 本章小结",
        "",
        f"- 已确定：{compact_join([row[0] for row in competition_threshold_rows], limit=3, soft_limit=10, hard_limit=18)} 已经是当前竞争门槛。",
        "- 先别讲歪：不要把高端、主销、下探守位继续放进同一套参数叙事里。",
        "- 下一章要回答：这些竞争门槛最后应该由 X / T / N 谁来承接，以及谁先别再扛。",
        "",
        "## 4. 看自己",
        "",
        "### 4.1 系列角色与不做清单",
        "",
        markdown_table(["系列", "必须承接", "不再承接", "错配代价", "当前不做"], role_rows),
        "",
        "### 4.2 本章小结",
        "",
        f"- 已确定：{compact_cell(role_rows[0][1], soft_limit=24, hard_limit=40)}；{compact_cell(role_rows[1][1], soft_limit=24, hard_limit=40)}。",
        "- 先别做：多机协同、统一生态、远期场景联动当前都不该抢主叙事。",
        "- 下一章要回答：哪些是真缺口，补完后哪条结论才能升级。",
        "",
        "## 5. 真缺口与补数计划",
        "",
        markdown_table(["缺口", "当前状态", "卡住哪条结论", "补什么", "补完后能升级什么"], gap_upgrade_rows),
        "",
        f"- 当前优先补数：{compact_join(next_data_moves[:3], limit=3, soft_limit=24, hard_limit=40)}。",
        "",
        "## 6. 最终结论",
        "",
        f"- 用户真正怎么判断：{compact_cell(master_judgment_tree.get('root_thesis'), soft_limit=28, hard_limit=48)}",
        f"- 竞争真正卷什么：{compact_join([row[0] for row in competition_threshold_rows], limit=3, soft_limit=10, hard_limit=18)}。",
        "- 科沃斯当前最该怎么分工：X 守高端托管，T 守主销默认答案，N 守带宽完整度与补数边界。",
        "",
        "- 当前只做哪三件事：先修最伤结果与托管信任的问题；先把 X / T / N 分工讲清；先把真缺口补进主链。",
        f"- 当前哪些话先别对外讲：{compact_join((portfolio_generation_strategy.get('shape_level_not_now', []) or []), limit=3, soft_limit=12, hard_limit=24)}。",
        f"- 当前哪三个补数必须进下一轮：{compact_join([row[0] for row in gap_upgrade_rows[:3]], limit=3, soft_limit=18, hard_limit=32)}。",
        "",
        "## 附：数据口径与备查表",
        "",
        "### 附A 数据口径",
        "",
        markdown_table(["口径项", "当前值", "说明"], appendix_source_rows),
        "",
        "### 附B 品牌心智备查表",
        "",
        markdown_table(["品牌", "用户先想到它什么", "为什么信它", "为什么临门一脚放弃", "这对科沃斯意味着什么"], brand_support_rows),
        "",
        "### 附C 金点子备查表",
        "",
        markdown_table(["主题", "当前判断", "现在做 / 后置"], [[row[0], row[1], "现在做" if row[1] == "当前底线延伸项" else "后置"] for row in idea_support_rows]),
        "",
        "### 附D 证据来源类型说明",
        "",
        "- `可正式判断`：当前已有稳定自家样本，可进入正式并列页。",
        "- `仅方向判断`：当前已有局部信号，但仍缺与 X / T 同等级的直连证据。",
        "- `外部门槛`：当前主要来自竞品池或外部样本，只能讲行业门槛，不能讲成科沃斯当前最伤。",
        "- `真实缺数据`：当前真缺样本，不能用解释文案填平。",
    ]
    return "\n".join(sanitize_presentation_text(line, report_banned_phrases) if line.startswith("- ") else line for line in lines)

    x_generation = generation_rows.get("X", {})
    t_generation = generation_rows.get("T", {})
    x_node = find_user_node("X 为什么会分成")
    t_node = find_user_node("T 为什么不是一个总 archetype")
    n_node = find_user_node("N 为什么不能先压成一个总用户 archetype")
    weak_signal_node = next(iter(user_not_ready_nodes), {})
    value_pillars = strategy_translation.get("value_pillar_candidates", []) or []
    main_value_pillar = next(
        (row for row in value_pillars if cell_text(row.get("pillar_name")) == "省心托管"),
        next(iter(value_pillars), {}),
    )
    tech_value_pillar = next(
        (row for row in value_pillars if cell_text(row.get("pillar_name")) == "科技表达"),
        {},
    )

    strongest_conclusion_rows = [
        [
            "X 的用户判断不是一个总旗舰人群，而是“清洁帮手 / 清洁管家”两条主定位。",
            cell_text(x_node.get("lead_judgment", user_thesis_tree.get("x_core_thesis"))),
            cell_text(x_node.get("why_converged")),
            cell_text(x_node.get("why_not_other")),
            "X 当前要围绕基础代劳与低介入托管讲主叙事，不让表达型弱信号抢主位。",
        ],
        [
            "T 不是一个总 archetype，而是几类 JTBD 的集合。",
            cell_text(t_node.get("lead_judgment", user_thesis_tree.get("t_core_thesis"))),
            cell_text(t_node.get("why_converged")),
            cell_text(t_node.get("why_not_other")),
            "T 要把结果更稳、少返工、少维护讲成主销默认答案，而不是再堆炫技能力。",
        ],
        [
            "N 不能再被当成一个总 N 来讲，必须拆成三条带。",
            cell_text(n_node.get("lead_judgment")),
            cell_text(n_node.get("why_converged")),
            cell_text(n_node.get("why_not_other")),
            "N 需要把单机守位、入门带基站承接和 omni 下探三条带拆开承接，不能继续让 X/T 替它补位。",
        ],
        [
            "当前半年优先修的不是所有高频问题，而是会同时伤害结果信任和托管信任的那一组问题。",
            "当前优先级已经收在 `清洁效果与水痕污渍 / 噪音体验 / 边角与覆盖率 / 智能-App-语音-地图` 这组问题。",
            cell_text((strategy_translation.get("priority_reasoning", []) or ["先做那些已经在多个来源同时出现、并且会伤害清洁结果或托管信任的问题。"])[0]),
            "不是谁声量高就先做谁，而是先做那些会把用户拉回手动、返工和维护的问题。",
            "X/T 先扛清洁底线与托管信任，N 负责带宽完整度，不再让旗舰主线替下探守位兜底。",
        ],
        [
            "“省心托管”比“科技表达”更接近当前成交主线。",
            cell_text(main_value_pillar.get("why", "高频问题最后都在伤害用户对“能不能放心交给它”的判断。")),
            cell_text(main_value_pillar.get("why")),
            cell_text(tech_value_pillar.get("why", "科技表达真实存在，但当前更像高价值用户的加分项，不该盖过基础能力。")),
            "X/T 当前统一收在少操心、少返工、真托管；科技表达保留为高端加分项，不盖过底线能力。",
        ],
        [
            "当前最该被前置的不是更多结论，而是真缺数据。",
            "N_aes 中国、N_omni 中国、T_omni 海外当前都还不能讲满，N 带宽直连定性也明显弱于 X/T。",
            cell_text("；".join((analysis_reflection_report.get("breadth_gaps", []) or [])[:2])),
            "这些不是分析没翻出来，而是当前真源还不够，不能用漂亮文案填平。",
            "补数计划必须直接进入主链，否则 X/T/N 的分工会继续被不完整样本拖偏。",
        ],
    ]

    coverage_rows = [
        [
            "X / 中国",
            cell_text(user_thesis_tree.get("x_core_thesis")),
            cell_text(weak_signal_node.get("lead_judgment", "表达型信号当前只适合作为方向性补充。")),
            "-",
        ],
        [
            "T / 中国",
            cell_text(user_thesis_tree.get("t_core_thesis")),
            "维护与基站操作在人物 / JTBD 层很重，但跨源层仍更适合作为重要工作假设。",
            find_market_scope_gap("T_omni（主销 omni） / 海外"),
        ],
        [
            "N_single / 中国",
            cell_text((user_thesis_tree.get("n_band_theses", {}) or {}).get("N_single")),
            "当前以 VOC-only 守位判断为主，仍缺与 X/T 同等级的直连定性解释。",
            "N（三带）的直连定性仍明显弱于 X / T。",
        ],
        [
            "N_aes / 海外与 ALL",
            cell_text((user_thesis_tree.get("n_band_theses", {}) or {}).get("N_aes")),
            "智能 / App / 地图很可能是入门带基站是否会失守的信任入口，但仍建议继续补第三源。",
            find_market_scope_gap("N_aes（AES 入门带基站） / 中国"),
        ],
        [
            "N_omni / 中国、ALL、海外",
            "当前只能保留边界与补数方向，不能正式写完整用户判断。",
            "可以讲外部门槛，但不能把它讲成科沃斯当前最伤。",
            find_market_scope_gap("N_omni（omni 下探） / 中国"),
        ],
    ]

    key_problem_rows = [
        [
            "清洁效果与水痕污渍",
            "已是底线问题，必须进入主叙事。",
            cell_text(cross_source_lookup.get("清洁效果与水痕污渍", {}).get("best_explanation", "这不是单点拖地问题，而是会直接伤害清洁结果信任。")),
            "它伤的不是单一功能满意度，而是用户对“机器到底有没有把事做完”的判断。",
            summarize_problem_boundary("清洁效果与水痕污渍"),
        ],
        [
            "边角与覆盖率",
            "已是稳定正向锚点，也是完成率证明。",
            cell_text(cross_source_lookup.get("边角与覆盖率", {}).get("best_explanation", "表面上看是边角，实际上伤的是工作完成率和是否还要人工补扫。")),
            "它不是小功能点，而是‘还要不要自己补扫’的分水岭。",
            summarize_problem_boundary("边角与覆盖率"),
        ],
        [
            "噪音体验",
            "已进入高优先问题，但当前仍建议继续补第三源。",
            cell_text(cross_source_lookup.get("噪音体验", {}).get("best_explanation", "噪音会把机器从能用拉回只能挑时间用。")),
            "它伤的不是单次抱怨，而是可用时窗和定时运行信任。",
            summarize_problem_boundary("噪音体验"),
        ],
        [
            "智能 / App / 语音 / 地图",
            "已是入门带基站与智能信任的重要焦点。",
            cell_text(cross_source_lookup.get("智能/App/语音/地图", {}).get("best_explanation", "地图、路径和交互问题会放大用户对机器聪不聪明、值不值得信任的判断。")),
            "它不是附加体验，而是‘机器是否聪明可信’的入口。",
            summarize_problem_boundary("智能/App/语音/地图"),
        ],
        [
            "维护与基站操作",
            "当前只能保留为重要工作假设，不能直接升成稳定主命题。",
            cell_text(cross_source_lookup.get("维护与基站操作", {}).get("best_explanation", "这类问题更像期待型判断或小样本模式洞察，未必已经在大规模 VOC 中爆出来。")),
            "它在人物 / JTBD 层很重，但当前还没有足够跨源证据支撑它全面上台。",
            cell_text(cross_source_lookup.get("维护与基站操作", {}).get("next_validation_step", "需要补第三源验证。")),
        ],
        [
            "避障越障与卡困",
            "当前只能保留为重要工作假设，不能直接升成稳定主命题。",
            cell_text(cross_source_lookup.get("避障越障与卡困", {}).get("best_explanation", "这类问题更像使用后才暴露，或是低频极端工况。")),
            "它更像极端工况里的托管破口，目前还不能讲成普遍稳定结论。",
            cell_text(cross_source_lookup.get("避障越障与卡困", {}).get("next_validation_step", "需要补第三源验证。")),
        ],
        [
            "多机协同与统一控制",
            "当前先不讲满，只保留为远期方向。",
            cell_text(cross_source_lookup.get("多机协同与统一控制", {}).get("best_explanation", "这类问题更像低频极端工况或未来机会点，当前不会自然成为主销判断。")),
            "它不能抢掉本代主叙事，否则会把当前最伤信任的一组问题重新讲散。",
            cell_text(cross_source_lookup.get("多机协同与统一控制", {}).get("next_validation_step", "进入储备池，等底线与托管问题收住后再讲。")),
        ],
    ]

    strategy_implication_rows = [
        [
            "高端托管承诺",
            cell_text((self_thesis_nodes[0].get("root_claim") if self_thesis_nodes else "X 要把高端托管承诺讲成可信答案。")),
            "因为 X 的用户判断已经分成基础代劳与低介入托管两条主定位，当前高端价值要靠少操心、少返工、真托管坐实。",
            "由 X 主扛；不要再把下探守位和远期协同一起压进旗舰。",
        ],
        [
            "主销结果稳定与少维护",
            cell_text((self_thesis_nodes[1].get("root_claim") if len(self_thesis_nodes) > 1 else "T 要把结果更稳、少返工、少维护讲成主销默认答案。")),
            "因为 T 的 JTBD 分化最后都在要求‘把事稳稳做完’，而不是再堆更多炫技能力。",
            "由 T 主扛；不要让 X 单独承担主销改善，也不要让 N 被迫补位。",
        ],
        [
            "下探带宽完整度",
            cell_text((self_thesis_nodes[2].get("root_claim") if len(self_thesis_nodes) > 2 else "N 需要拆成 omni 下探 / AES / 单机三条带分别承接。")),
            "因为 N 的问题不是一个总桶，而是三条带在承接位和样本完整度上都不同。",
            "由 N（三带）分别承接；不要继续让 X/T 旗舰线替 N 说话。",
        ],
        [
            "科技表达与远期协同",
            "当前真实存在，但只适合作为加分项和储备池。",
            "因为科技表达还不是基础购买逻辑，多机协同也还没到可以抢主卖点的阶段。",
            "当前先别塞进 X / T 主叙事；进入中长期储备池。",
        ],
    ]

    gap_rows = [
        [
            "N_omni / 中国 / 自家 VOC",
            "真实缺数据",
            "当前只有竞品池外部门槛，不能正式讲科沃斯自己的用户判断。",
            "优先补中国自家 VOC 与真实用户反馈入口，停止用外部门槛代替自家判断。",
        ],
        [
            "N_aes / 中国 / 自家 VOC",
            "真实缺数据",
            "当前只能讲海外 / ALL 的稳定信号，不能直接翻成中国承接位判断。",
            "优先补中国自家 VOC，并补齐带基站入门位的真实用户反馈。",
        ],
        [
            "T_omni / 海外",
            "真实缺数据",
            "当前海外样本偏薄，只能做缺样本声明，不能讲正式竞争判断。",
            "补主销 omni 海外样本，再决定是否上翻海外判断。",
        ],
        [
            "N（三带）直连定性",
            "结构性缺口",
            f"当前证据包分布为 X={packet_band_counter.get('X', 0)}、T={packet_band_counter.get('T', 0)}、N_single={packet_band_counter.get('N_single', 0)}、N_aes={packet_band_counter.get('N_aes', 0)}、N_omni={packet_band_counter.get('N_omni', 0)}，说明 N 尤其 N_omni 的直连解释基础明显弱于 X/T。",
            "补与 X/T 同等级的问卷 / 定性直连证据，避免 N 长期停在 VOC-only 方向判断。",
        ],
    ]

    cleaned_brand_rows = []
    for row in brand_rows:
        brand = cell_text(row.get("brand"))
        payload = brand_map.get(brand, {}) if isinstance(brand_map, dict) else {}
        choose_lines = clean_reason_lines((payload.get("trust_reason") or row.get("why_choose") or []), keep_negative=False)
        reject_lines = clean_reason_lines((payload.get("rejection_reason") or row.get("why_reject") or []), keep_negative=True)
        cleaned_brand_rows.append(
            [
                brand,
                cell_text(row.get("one_line_label", payload.get("core_label"))),
                "；".join(choose_lines) if choose_lines else "-",
                "；".join(reject_lines) if reject_lines else "-",
                brand_implication_text(brand),
            ]
        )

    idea_now_rows = [
        [
            cell_text(row.get("theme")),
            "当前底线延伸项" if cell_text(row.get("now_or_later")) == "现在就该做" else "中长期差异化项",
            cell_text(row.get("why_now")),
            "现在就该做时，直接挂当前痛点和完成率；中长期布局时，不要提前透支成这一代主卖点。",
        ]
        for row in idea_rows
    ]

    lines = [
        f"# {category_name} 正式汇报稿",
        "",
        "## 0. 问题回答",
        "",
        f"- {cell_text(master_judgment_tree.get('summary_judgment', '当前最核心的结论仍待补充。'))}",
        f"- {cell_text(master_judgment_tree.get('root_thesis', '用户判断、竞争门槛和产品分工需要被放到同一条判断链里。'))}",
        "- 这版汇报先给最强结论，再区分哪些能讲满、哪些还要补证，最后落到 X / T / N 的分工和补数动作。",
        f"- 当前汇报目标是：{cell_text(analysis_goal_text)}",
        "",
        "## 1. 看用户",
        "",
        "### 1.0 最强结论",
        "",
        "- 先不从大表起，而是先把当前最该被记住的判断压成 6 条最强结论。",
        "",
        markdown_table(
            ["最强判断", "现在能讲什么", "为什么成立", "为什么不是别的解释", "对 X / T / N 分工意味着什么"],
            strongest_conclusion_rows,
        ),
        "",
        "### 1.1 当前能讲 / 不能讲满",
        "",
        f"- 当前市场口径：`{resolved_market}`。",
        f"- 当前分析周期：`{resolved_time_scope}`。",
        f"- 当前竞争市场覆盖：中国={cell_text((market_summary_rows[0].get('status_text') if market_summary_rows else '待补充'))}；海外={cell_text((market_summary_rows[1].get('status_text') if len(market_summary_rows) > 1 else '待补充'))}。",
        f"- 当前稳定问题包已形成 {len(signal_nodes)} 个强信号节点，但外部门槛节点仍有 {len(external_only_nodes)} 个，真实缺口节点仍有 {len(missing_scope_nodes)} 个。",
        "",
        markdown_table(
            ["对象 / 范围", "当前稳定结论", "工作假设 / 待补证", "真实缺数据"],
            coverage_rows,
        ),
        "",
        "### 1.2 X / T / N 分系列判断",
        "",
        "#### X",
        "",
        f"- 当前稳定结论：{cell_text(user_thesis_tree.get('x_core_thesis'))}",
        f"- 为什么成立：{cell_text(x_node.get('why_converged', '定性里已经长出基础代劳与低介入托管两条稳定判断。'))}",
        f"- 为什么不是别的解释：{cell_text(x_node.get('why_not_other', '表达型弱信号已出现，但当前还不足以与两条主定位并列。'))}",
        f"- 工作假设 / 待补证：{cell_text(tech_value_pillar.get('why', '高价值用户真实会为科技表达买单，但它当前更像加分项，不是主购买逻辑。'))}",
        f"- 当前不能讲满：{cell_text(weak_signal_node.get('lead_judgment', '科技玩家当前只适合作为方向性表达信号，不宜上翻成主定位。'))}",
        "",
        "#### T",
        "",
        f"- 当前稳定结论：{cell_text(user_thesis_tree.get('t_core_thesis'))}",
        f"- 为什么成立：{cell_text(t_node.get('why_converged', '不同人生位置会把清洁重新定义成替代、分担或保障。'))}",
        f"- 为什么不是别的解释：{cell_text(t_node.get('why_not_other', '如果先压成一个总人设，就会把 T 的不同清洁意义讲扁。'))}",
        "- 工作假设 / 待补证：维护与基站操作很可能是 T 的隐性信任破口，但当前仍更适合作为重要工作假设，而不是稳定主命题。",
        f"- 当前不能讲满：{find_market_scope_gap('T_omni（主销 omni） / 海外')}",
        "",
        "#### N（三带）",
        "",
        f"- 当前稳定结论：{cell_text(n_node.get('lead_judgment', 'N 当前不能先压成一个总 N，而要拆成 N_single / N_aes / N_omni 三条带。'))}",
        f"- 为什么成立：{cell_text(n_node.get('why_converged', 'N_single 已有中国稳定 VOC，N_aes 已有海外稳定 VOC，而 N_omni 仍缺自家稳定样本。'))}",
        f"- 为什么不是别的解释：{cell_text(n_node.get('why_not_other', '如果把 N 直接压成一个总 archetype，会把三条带的不同意义讲乱。'))}",
        f"- N_single：{cell_text((user_thesis_tree.get('n_band_theses', {}) or {}).get('N_single'))}",
        f"- N_aes：{cell_text((user_thesis_tree.get('n_band_theses', {}) or {}).get('N_aes'))}",
        f"- N_omni：{cell_text((user_thesis_tree.get('n_band_theses', {}) or {}).get('N_omni'))}",
        "- 工作假设 / 待补证：N_aes 的智能 / App / 地图很可能是带基站入门位是否会失守的信任入口，但当前仍建议继续补第三源。",
        f"- 当前不能讲满：{find_market_scope_gap('N_aes（AES 入门带基站） / 中国')}；{find_market_scope_gap('N_omni（omni 下探） / 中国')}",
        "",
        "### 1.3 关键问题为什么伤害判断",
        "",
        "- 当前真正伤害判断的不是单点功能名词，而是哪些问题会直接伤害结果信任、托管信任和完成率。",
        "",
        markdown_table(
            ["关键问题", "当前稳定结论", "当前解释", "为什么不是别的解释", "当前边界"],
            key_problem_rows,
        ),
        "",
        "### 1.4 对产品与资源分工意味着什么",
        "",
        "- 当前“看用户”不能停在用户画像，必须继续翻成产品分工和资源承接。",
        "",
        markdown_table(
            ["分工主题", "当前判断", "为什么现在先做", "谁来承接 / 谁先别扛"],
            strategy_implication_rows,
        ),
        "",
        "### 1.5 真缺口与补数计划",
        "",
        "- 这里单独只讲真缺口，不把“分析还没翻出来”和“数据真的不够”混在一起。",
        "",
        markdown_table(
            ["缺口", "当前状态", "为什么是真缺", "下一步补什么"],
            gap_rows,
        ),
        "",
        "### 1.6 品牌心智清洗：谁先被想到，为什么临门一脚放弃",
        "",
        markdown_table(
            ["品牌", "用户先想到它什么", "为什么信它", "为什么临门一脚放弃", "这对科沃斯意味着什么"],
            cleaned_brand_rows,
        ),
        "",
        "### 1.7 用户金点子：现在做还是后置",
        "",
        markdown_table(
            ["主题", "当前判断", "为什么现在做 / 为什么后置", "不该提前透支什么"],
            idea_now_rows,
        ),
        "",
    ]
    for page_id in [
        "competition_intro_pages",
        "competition_thesis_pages",
        "competition_capability_scan_pages",
        "competition_matchup_pages",
        "competition_conclusion_pages",
        "self_value_pages",
        "self_portfolio_bandwidth_pages",
        "self_demand_reorder_pages",
        "priority_strategy_pages",
        "priority_assignment_pages",
        "reflection_intro_pages",
        "analysis_reflection_pages",
        "data_moves_pages",
        "roadmap_action_pages",
    ]:
        append_page_block(lines, page_block_lookup.get(page_id))
    lines.extend(
        [
            "## 附：数据能力声明",
            "",
            f"- 当前市场范围：`{resolved_market}`。",
            f"- 当前分析周期：`{resolved_time_scope}`。",
            "- 当前更适合支撑用户定位、问题包、跨源解释、优先级翻译，以及 X / T / N 的分工收口。",
            "- 当前不适合直接定案价格策略、完整路线图排期和所有海外带宽的正式判断。",
            f"- 当前真缺样本主要集中在：{cell_text('；'.join(reflection_next_moves[:3]))}",
        ]
    )
    return "\n".join(sanitize_presentation_text(line, report_banned_phrases) if line.startswith("- ") else line for line in lines)


def build_standard_presentation_leads(args: argparse.Namespace, result: dict[str, object]) -> dict[str, list[str]]:
    support_matrix = result["support_matrix"]  # type: ignore[index]
    unsupported_modules = [row["module_name_cn"] for row in support_matrix if row["support_level"] != "支持"]
    primary_self = pick_primary_self(result)
    primary_competitor = pick_primary_competitor(args, result)
    self_name = primary_self["spu_name"] if primary_self else "当前本品对象"
    competitor_name = primary_competitor["spu_name"] if primary_competitor else "关键竞品"
    return {
        "## 0. 问题回答": [
            f"先直接回答问题：这轮报告的主对象仍然是 `{self_name}`，因为当前证据已经足够支撑专题判断。",
            "这里先给总判断，后面再展开证据，不把方法和边界抢到最前面。",
        ],
        "## 1. 分析对象与证据边界": [
            "先把这轮到底在看谁、证据够不够、哪些地方不能讲满说清楚，后面结论才不会变薄。",
        ],
        "## 2. 一级结论树": [
            "这里先把总判断摆出来，后面的递归论证必须和这里一一对应，不再另起一套说法。",
        ],
        "## 3. 递归论证": [
            f"后面按判断往下拆，重点看 `{self_name}` 为什么值得先讲，以及它和 `{competitor_name}` 的差距到底落在什么地方。",
        ],
        "## 4. 反证 / 缺口 / 风险": [
            f"不能下满结论的地方单独拎出来，尤其是 `{unsupported_modules[0] if unsupported_modules else '当前薄弱模块'}` 这类还不能硬定的部分。",
        ],
        "## 5. 下一步行动（5W2H）": [
            "行动只保留真正重要的，不把所有可以做的事情都写进来。",
        ],
        "## 6. 数据能力声明与附录": [
            "数据能力放最后，不抢主结论，但要把这轮到底能看见什么、看不见什么说透。",
        ],
    }


def build_portfolio_presentation_leads(series_payloads: list[dict[str, object]]) -> dict[str, list[str]]:
    x_payload = next((payload for payload in series_payloads if payload["series_code"] == "X"), None)
    t_payload = next((payload for payload in series_payloads if payload["series_code"] == "T"), None)
    x_ready = decision_readiness_label(x_payload["result"]) if x_payload else "待补充"  # type: ignore[index]
    t_ready = decision_readiness_label(t_payload["result"]) if t_payload else "待补充"  # type: ignore[index]
    return {
        "## 0. 问题回答": [
            "先直接回答这轮最核心的问题：为什么当前更值得先讲透的是 X 系列，而不是把 X 和 T 平铺成同一种结论。",
        ],
        "## 1. 分析对象与证据边界": [
            f"这部分先把系列覆盖、对象范围和证据边界说清。当前 `X 系列` 是 `{x_ready}`，`T 系列` 是 `{t_ready}`，两边并不是同一种完整度。",
        ],
        "## 2. 一级结论树": [
            "先把系列级总判断摆出来，后面再往下拆对象和证据，不在一开始把细节讲散。",
        ],
        "## 3. 递归论证": [
            "后面按系列分别展开，重点看为什么 X 更值得先讲、T 为什么还要留边界。",
        ],
        "## 4. 反证 / 缺口 / 风险": [
            "这里把当前不能下满结论的地方单独拎出来，避免把系列化判断讲得过满。",
        ],
        "## 5. 下一步行动（5W2H）": [
            "行动不是平均分配到每个系列，而是先围绕最值得优先收口的对象和问题去展开。",
        ],
        "## 6. 数据能力声明与附录": [
            "数据能力放在最后，作为这轮判断的边界说明，不抢在主结论前面。",
        ],
    }


def build_backfill_task_order(primary_self_spu_id: str, competitor_spu_ids: list[str]) -> str:
    primary_self_label = primary_self_spu_id
    top_competitors = "、".join(competitor_spu_ids[:3]) if competitor_spu_ids else "关键竞品"
    lines = []
    lines.append(f"# {primary_self_label} 补数任务单")
    lines.append("")
    lines.append("## 1. 目标")
    lines.append("")
    lines.append(f"- 让 `{primary_self_label}` 从“代理判断”升级到“直连多源判断”。")
    lines.append(f"- 次优先补齐 `{top_competitors}` 的非 VOC 研究输入。")
    lines.append("")
    lines.append("## 2. 核心任务")
    lines.append("")
    lines.append("| ID | 任务 | 数据块 | 需要输入物 | 最低标准 |")
    lines.append("| --- | --- | --- | --- | --- |")
    lines.append(f"| {primary_self_label}-BF-01 | 补 `{primary_self_label}` 直连问卷 | `cleaning_robot_quant_survey` | `{primary_self_label}` 专项问卷 Excel | `300+` 有效样本或 `100+` 早期专项样本 |")
    lines.append(f"| {primary_self_label}-BF-02 | 补 `{primary_self_label}` 直连访谈总结 | `cleaning_robot_summary_qual_interview` | `{primary_self_label}` 总结 Markdown | `3-5` 个可识别案例 |")
    lines.append(f"| {primary_self_label}-BF-03 | 补 `{primary_self_label}` 原始访谈索引 | `cleaning_robot_qual_interview` | `{primary_self_label}` 原始文档目录 | 至少 `3` 份原始文档可建索引 |")
    if competitor_spu_ids:
        lines.append(f"| {primary_self_label}-BF-04 | 补关键竞品非 VOC 研究输入 | `cleaning_robot_quant_survey` / `cleaning_robot_summary_qual_interview` | `{top_competitors}` 直连问卷或总结 | 至少 `2` 个关键竞品拥有非 VOC 直连输入 |")
    return "\n".join(lines)


def build_backfill_task_board(primary_self_spu_id: str, competitor_spu_ids: list[str]) -> str:
    today = date.today()
    c1 = (today + timedelta(days=7)).isoformat()
    c2 = (today + timedelta(days=8)).isoformat()
    c3 = (today + timedelta(days=11)).isoformat()
    c4 = (today + timedelta(days=12)).isoformat()
    c5 = (today + timedelta(days=13)).isoformat()
    c6 = (today + timedelta(days=14)).isoformat()
    c7 = (today + timedelta(days=15)).isoformat()
    c8 = (today + timedelta(days=16)).isoformat()
    top_comp = competitor_spu_ids[0] if competitor_spu_ids else "关键竞品"
    lines = []
    lines.append(f"# {primary_self_spu_id} 补数任务板")
    lines.append("")
    lines.append("| ID | 任务 | 负责人 | 优先级 | 截止时间 | 状态 | 交付物 | 验收标准 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    rows = [
        (f"{primary_self_spu_id}-BF-01", f"补 `{primary_self_spu_id}` 直连问卷", "定量研究", "P1", c1, "Not Started", f"`{primary_self_spu_id}` 专项问卷 Excel", f"`vw_wave_capability_summary` 中出现 `{primary_self_spu_id}` 直连波次"),
        (f"{primary_self_spu_id}-BF-02", f"导入 `{primary_self_spu_id}` 直连问卷", "数据工程", "P1", c2, "Not Started", "入库批次与能力地图刷新", f"`cleaning_robot_quant_survey` 可查到 `{primary_self_spu_id}`"),
        (f"{primary_self_spu_id}-BF-03", f"补 `{primary_self_spu_id}` 直连访谈总结", "定性研究", "P1", c3, "Not Started", f"`{primary_self_spu_id}` 访谈总结 Markdown", f"`vw_summary_case_module_coverage` 出现 `{primary_self_spu_id}` 案例"),
        (f"{primary_self_spu_id}-BF-04", f"导入 `{primary_self_spu_id}` 直连访谈总结", "数据工程", "P1", c4, "Not Started", "总结库新案例", f"总结库命中 `{primary_self_spu_id}`"),
        (f"{primary_self_spu_id}-BF-05", f"补 `{primary_self_spu_id}` 原始访谈文档", "定性研究", "P1", c5, "Not Started", "原始访谈文档目录", f"`interview_case` 中出现 `{primary_self_spu_id}`"),
        (f"{primary_self_spu_id}-BF-06", f"导入 `{primary_self_spu_id}` 原始访谈索引", "数据工程", "P1", c6, "Not Started", "原始访谈索引入库", f"`cleaning_robot_qual_interview` 命中 `{primary_self_spu_id}`"),
        (f"{primary_self_spu_id}-BF-07", f"补 `{top_comp}` 非 VOC 研究输入", "用户研究 PM", "P2", c7, "Not Started", f"`{top_comp}` 直连问卷或总结", "关键竞品拥有非 VOC 直连输入"),
        (f"{primary_self_spu_id}-BF-08", f"重跑 `{primary_self_spu_id}` 当前代报告", "数据工程", "P1", c8, "Not Started", "更新后的当前代报告", "报告不再以代理波次作为主依据"),
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_backfill_task_tracker(primary_self_spu_id: str, competitor_spu_ids: list[str]) -> str:
    today = date.today()
    next_check = (today + timedelta(days=4)).isoformat()
    top_comp = competitor_spu_ids[0] if competitor_spu_ids else "关键竞品"
    lines = []
    lines.append(f"# {primary_self_spu_id} 补数任务跟踪版")
    lines.append("")
    lines.append("| ID | 任务 | 负责人 | 优先级 | 截止时间 | 当前状态 | 最新状态 | blocker | 下一检查点 | 验收标准 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    rows = [
        (f"{primary_self_spu_id}-BF-01", f"补 `{primary_self_spu_id}` 直连问卷", "定量研究", "P1", (today + timedelta(days=7)).isoformat(), "Not Started", f"尚未收到 `{primary_self_spu_id}` 问卷源文件", "等待研究侧提供问卷", next_check, f"`vw_wave_capability_summary` 中出现 `{primary_self_spu_id}` 直连波次"),
        (f"{primary_self_spu_id}-BF-03", f"补 `{primary_self_spu_id}` 直连访谈总结", "定性研究", "P1", (today + timedelta(days=11)).isoformat(), "Not Started", "尚未收到直连总结案例", "等待研究侧整理 Markdown", next_check, f"`vw_summary_case_module_coverage` 中出现 `{primary_self_spu_id}` 案例"),
        (f"{primary_self_spu_id}-BF-05", f"补 `{primary_self_spu_id}` 原始访谈文档", "定性研究", "P1", (today + timedelta(days=13)).isoformat(), "Not Started", "尚未收到原始访谈文件", "等待原始文档目录", next_check, f"`interview_case` 中出现 `{primary_self_spu_id}`"),
        (f"{primary_self_spu_id}-BF-07", f"补 `{top_comp}` 非 VOC 研究输入", "用户研究 PM", "P2", (today + timedelta(days=15)).isoformat(), "Not Started", f"当前 `{top_comp}` 仍只有 VOC", "需协调竞品研究优先级", next_check, "关键竞品拥有非 VOC 直连输入"),
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## 当前判断")
    lines.append("")
    lines.append(f"- 目前最大的 blocker 不是脚本，而是 `{primary_self_spu_id}` 直连研究输入尚未到位。")
    lines.append(f"- 若两周内仍无 `{primary_self_spu_id}` 直连问卷或直连总结到位，应升级为研究排期问题处理。")
    return "\n".join(lines)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_higher_order_artifacts(args: argparse.Namespace, result: dict[str, object]) -> dict[str, dict[str, object]]:
    selected_spus = result["selected_spus"]  # type: ignore[index]
    selected_spu_ids = [row["spu_id"] for row in selected_spus]
    market = getattr(args, "market", None)
    truth_conn = connect(TRUTH_DB)

    summary_conn = connect(SUMMARY_DB)
    summary_sections = fetch_summary_theme_sections(summary_conn, selected_spu_ids, market)
    summary_conn.close()
    summary_insight_cards = extract_summary_insight_cards(summary_sections)
    semantic_passages = build_semantic_passages(summary_insight_cards["case_concept_slots"])  # type: ignore[index]
    summary_theme_evidence = build_summary_theme_evidence(summary_sections)

    survey_rows = result["survey_rows"]  # type: ignore[index]
    survey_wave_details = []
    survey_conn = connect(SURVEY_DB)
    effective_survey_rows = survey_rows
    if not effective_survey_rows:
        effective_survey_rows = fetch_proxy_survey_rows_or_empty(selected_spu_ids, market)
    for wave_row in effective_survey_rows:
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
    survey_segment_comparison = build_survey_segment_comparison(survey_conn, effective_survey_rows)
    survey_concept_segments = build_survey_concept_segments(survey_conn, effective_survey_rows)
    generation_comparison = build_generation_comparison(survey_conn)
    survey_open_answer_rows = fetch_survey_open_answer_rows(survey_conn, effective_survey_rows)
    survey_conn.close()
    survey_theme_evidence = build_survey_theme_evidence(survey_wave_details)
    competition_generation_registry = load_competition_generation_registry()
    competition_generation_analysis = build_competition_generation_analysis(
        generation_comparison,
        competition_generation_registry,
    )
    awe_exhibition_signals = build_awe_exhibition_signals()
    demand_pool_snapshot = build_demand_pool_snapshot()

    voc_conn = connect_live_voc_preferred()
    theme_rows, negative_rows, _ = fetch_voc_theme_rows(voc_conn, selected_spu_ids)
    voc_problem_packages = build_voc_problem_packages(
        voc_conn,
        selected_spu_ids,
        competition_generation_registry=competition_generation_registry,
        truth_conn=truth_conn,
    )
    competition_voc_xtn_breakdown = build_competition_voc_xtn_breakdown(
        voc_conn,
        competition_generation_registry,
        truth_conn=truth_conn,
    )
    competition_voc_market_split = build_competition_voc_market_split(
        competition_voc_xtn_breakdown
    )
    user_attention_source_rows = fetch_user_attention_source_rows(
        voc_conn,
        collect_user_attention_spu_ids(selected_spu_ids, competition_voc_xtn_breakdown),
    )
    voc_conn.close()
    voc_theme_evidence = build_voc_theme_evidence(theme_rows, negative_rows)

    consistent_issues, consistent_strengths, conflict_rows, priority_rows = build_cross_source_tables(
        voc_theme_evidence,
        survey_theme_evidence,
        summary_theme_evidence,
    )
    x_series_concept_map = build_x_series_concept_map(summary_insight_cards["case_concept_slots"])  # type: ignore[index]
    t_series_concept_map = build_t_series_concept_map(summary_insight_cards["case_concept_slots"], survey_concept_segments)  # type: ignore[index]
    brand_mindshare_map = build_brand_mindshare_map(summary_insight_cards["case_concept_slots"])  # type: ignore[index]
    idea_pool_clusters = build_idea_pool_clusters(summary_insight_cards["case_concept_slots"])  # type: ignore[index]
    x_case_signal_profiles = build_x_case_signal_profiles(summary_insight_cards["case_concept_slots"], semantic_passages)  # type: ignore[index]
    x_observed_positionings = build_x_observed_positionings(summary_insight_cards["case_concept_slots"], semantic_passages, x_case_signal_profiles)  # type: ignore[index]
    x_positioning_packages = build_x_positioning_packages(
        summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        semantic_passages,
        x_case_signal_profiles=x_case_signal_profiles,
        x_observed_positionings=x_observed_positionings,
    )
    t_persona_slice_cards = build_t_persona_slice_cards(summary_insight_cards["case_concept_slots"], semantic_passages)  # type: ignore[index]
    t_difference_matrix = build_t_difference_matrix(summary_insight_cards["case_concept_slots"], semantic_passages)  # type: ignore[index]
    t_jtbd_packages = build_t_jtbd_packages(summary_insight_cards["case_concept_slots"], semantic_passages)  # type: ignore[index]
    cleaning_robot_theme_registry = build_cleaning_robot_theme_registry(user_attention_source_rows)
    topic_attention_matrix = build_topic_attention_matrix(
        user_attention_source_rows,
        cleaning_robot_theme_registry,
    )
    problem_drilldown_packages = build_problem_drilldown_packages(
        user_attention_source_rows,
        topic_attention_matrix,
        summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        cleaning_robot_theme_registry,
    )
    qual_evidence_packet = build_qual_evidence_packet(
        semantic_passages=semantic_passages,
        topic_attention_matrix=topic_attention_matrix,
        problem_drilldown_packages=problem_drilldown_packages,
        survey_segment_comparison=survey_segment_comparison,
        survey_concept_segments=survey_concept_segments,
        survey_open_answer_rows=survey_open_answer_rows,
    )
    reasoning_bundle = run_dual_engine_reasoning(
        analysis_engine=getattr(args, "analysis_engine", "rule_only"),
        qual_evidence_packet=qual_evidence_packet,
        llm_profile_path=getattr(args, "llm_profile_path", None),
        qual_reasoning_profile=getattr(args, "qual_reasoning_profile", "qual_default"),
        thesis_reasoning_profile=getattr(args, "thesis_reasoning_profile", "thesis_default"),
    )
    qual_reasoning_task_board = reasoning_bundle["qual_reasoning_task_board"]
    qual_case_reasoning_cards = reasoning_bundle["qual_case_reasoning_cards"]
    qual_theme_reasoning_map = reasoning_bundle["qual_theme_reasoning_map"]
    cross_source_hypothesis_board = reasoning_bundle["cross_source_hypothesis_board"]
    judgment_acceptance_log = evaluate_candidate_claims(
        reasoning_bundle["candidate_claims"],
        qual_evidence_packet,
        analysis_engine=getattr(args, "analysis_engine", "rule_only"),
        fallback_status=str(reasoning_bundle.get("fallback_status", "")),
        cross_source_hypothesis_board=cross_source_hypothesis_board,
        qual_theme_reasoning_map=qual_theme_reasoning_map,
    )
    cross_source_interpretation = build_cross_source_interpretation(
        consistent_issues,
        consistent_strengths,
        conflict_rows,
        priority_rows,
        summary_insight_cards,
        survey_segment_comparison,
        voc_problem_packages,
        qual_evidence_packet=qual_evidence_packet,
        cross_source_hypothesis_board=cross_source_hypothesis_board,
        judgment_acceptance_log=judgment_acceptance_log,
    )
    series_positioning = build_series_positioning(
        summary_insight_cards,
        survey_segment_comparison,
        cross_source_interpretation,
    )
    survey_qual_explanation_map = build_survey_qual_explanation_map(
        summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        survey_segment_comparison,
        survey_concept_segments,
        x_positioning_packages,
        t_jtbd_packages,
        topic_attention_matrix,
        problem_drilldown_packages,
        cleaning_robot_theme_registry,
        qual_evidence_packet=qual_evidence_packet,
        qual_case_reasoning_cards=qual_case_reasoning_cards,
        qual_theme_reasoning_map=qual_theme_reasoning_map,
        judgment_acceptance_log=judgment_acceptance_log,
    )
    x_positioning_confidence_stats = build_x_positioning_confidence_stats(
        case_concept_slots=summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        semantic_passages=semantic_passages,
        x_positioning_packages=x_positioning_packages,
        x_observed_positionings=x_observed_positionings,
    )
    t_dimension_confidence_stats = build_t_dimension_confidence_stats(
        case_concept_slots=summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        semantic_passages=semantic_passages,
        t_difference_matrix=t_difference_matrix,
    )
    brand_mindshare_judgments = build_brand_mindshare_judgments(brand_mindshare_map)
    idea_cluster_judgments = build_idea_cluster_judgments(idea_pool_clusters)
    concept_support_stats = build_concept_support_stats(
        case_concept_slots=summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        semantic_passages=semantic_passages,
        survey_concept_segments=survey_concept_segments,
        voc_problem_packages=voc_problem_packages,
        x_positioning_packages=x_positioning_packages,
        t_persona_slice_cards=t_persona_slice_cards,
        t_difference_matrix=t_difference_matrix,
        t_jtbd_packages=t_jtbd_packages,
        brand_mindshare_judgments=brand_mindshare_judgments,
        idea_cluster_judgments=idea_cluster_judgments,
    )
    concept_comparison_matrix = build_concept_comparison_matrix(concept_support_stats)
    concept_pain_need_map = build_concept_pain_need_map(x_positioning_packages, t_jtbd_packages)
    strategy_translation = build_strategy_translation(
        cross_source_interpretation,
        voc_problem_packages,
        summary_insight_cards,
        series_positioning,
    )
    competition_capability_scan = build_competition_capability_scan(
        truth_conn,
        competition_generation_registry,
        competition_voc_xtn_breakdown,
        awe_exhibition_signals,
    )
    competition_matchup_matrix = build_competition_matchup_matrix(
        competition_generation_registry,
        competition_voc_xtn_breakdown,
        awe_exhibition_signals,
    )
    competition_strategy_bridge = build_competition_strategy_bridge(
        competition_voc_xtn_breakdown,
        competition_capability_scan,
        competition_matchup_matrix,
    )
    competition_capture_target_candidates = build_competition_capture_target_candidates(
        competition_generation_registry,
        competition_voc_xtn_breakdown,
    )
    analysis_reflection_report = build_analysis_reflection_report(
        competition_voc_xtn_breakdown,
        competition_voc_market_split,
        competition_capability_scan,
        competition_matchup_matrix,
        competition_strategy_bridge,
        competition_capture_target_candidates,
    )
    truth_conn.close()
    portfolio_generation_strategy = build_portfolio_generation_strategy(
        competition_generation_analysis,
        generation_comparison,
        demand_pool_snapshot,
        strategy_translation,
    )
    self_strategy_thesis = build_self_strategy_thesis(
        competition_strategy_bridge,
        portfolio_generation_strategy,
        analysis_reflection_report,
    )
    entry_exposure_tree = build_entry_exposure_tree(
        result,
        competition_capture_target_candidates,
        competition_voc_xtn_breakdown,
    )
    user_insight_exposure_tree = build_user_insight_exposure_tree(
        x_observed_positionings,
        x_positioning_packages,
        t_persona_slice_cards,
        t_difference_matrix,
        t_jtbd_packages,
        generation_comparison,
        entry_exposure_tree=entry_exposure_tree,
        topic_attention_matrix=topic_attention_matrix,
        problem_drilldown_packages=problem_drilldown_packages,
        survey_qual_explanation_map=survey_qual_explanation_map,
    )
    user_strategy_convergence_tree = build_user_strategy_convergence_tree(
        user_insight_exposure_tree,
        series_positioning,
        x_positioning_packages,
        t_jtbd_packages,
    )
    user_thesis_tree = build_user_thesis_tree(
        user_strategy_convergence_tree,
        topic_attention_matrix,
        problem_drilldown_packages,
        qual_evidence_packet=qual_evidence_packet,
        qual_theme_reasoning_map=qual_theme_reasoning_map,
        cross_source_hypothesis_board=cross_source_hypothesis_board,
        judgment_acceptance_log=judgment_acceptance_log,
    )
    voc_fact_exposure_tree = build_voc_fact_exposure_tree(
        voc_problem_packages,
        competition_voc_xtn_breakdown,
    )
    cross_source_convergence_tree = build_cross_source_convergence_tree(
        cross_source_interpretation,
        series_positioning,
        strategy_translation,
        competition_voc_xtn_breakdown,
    )
    competition_thesis_tree = build_competition_thesis_tree(
        competition_capability_scan,
        competition_matchup_matrix,
        competition_voc_market_split,
        competition_strategy_bridge,
    )
    self_strategy_thesis_tree = build_self_strategy_thesis_tree(
        self_strategy_thesis,
        portfolio_generation_strategy,
        cross_source_convergence_tree,
        competition_capture_target_candidates,
    )
    master_judgment_tree = build_master_judgment_tree(
        user_strategy_convergence_tree,
        competition_thesis_tree,
        self_strategy_thesis_tree,
    )
    presentation_tree = build_presentation_tree(
        user_insight_exposure_tree,
        user_strategy_convergence_tree,
        competition_thesis_tree,
        self_strategy_thesis_tree,
        analysis_reflection_report,
    )
    x_positioning_impact_stats = build_x_positioning_impact_stats(
        case_concept_slots=summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        x_positioning_packages=x_positioning_packages,
        x_observed_positionings=x_observed_positionings,
        voc_problem_packages=voc_problem_packages,
        survey_concept_segments=survey_concept_segments,
        concept_pain_need_map=concept_pain_need_map,
        cross_source_interpretation=cross_source_interpretation,
        strategy_translation=strategy_translation,
        brand_mindshare_judgments=brand_mindshare_judgments,
        idea_cluster_judgments=idea_cluster_judgments,
    )
    x_jtbd_confidence_stats = build_x_jtbd_confidence_stats(
        case_concept_slots=summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        semantic_passages=semantic_passages,
    )
    x_jtbd_impact_stats = build_x_jtbd_impact_stats(
        case_concept_slots=summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        voc_problem_packages=voc_problem_packages,
        survey_concept_segments=survey_concept_segments,
        concept_pain_need_map=concept_pain_need_map,
        strategy_translation=strategy_translation,
        brand_mindshare_judgments=brand_mindshare_judgments,
        idea_cluster_judgments=idea_cluster_judgments,
        x_observed_positionings=x_observed_positionings,
    )
    t_dimension_impact_stats = build_t_dimension_impact_stats(
        case_concept_slots=summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        t_difference_matrix=t_difference_matrix,
        voc_problem_packages=voc_problem_packages,
        survey_concept_segments=survey_concept_segments,
        concept_pain_need_map=concept_pain_need_map,
        cross_source_interpretation=cross_source_interpretation,
        strategy_translation=strategy_translation,
    )
    t_jtbd_confidence_stats = build_t_jtbd_confidence_stats(
        case_concept_slots=summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        semantic_passages=semantic_passages,
        t_jtbd_packages=t_jtbd_packages,
    )
    t_jtbd_impact_stats = build_t_jtbd_impact_stats(
        case_concept_slots=summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        t_jtbd_packages=t_jtbd_packages,
        voc_problem_packages=voc_problem_packages,
        survey_concept_segments=survey_concept_segments,
        concept_pain_need_map=concept_pain_need_map,
        strategy_translation=strategy_translation,
    )
    page_metric_cards = build_page_metric_cards(
        concept_support_stats,
        concept_comparison_matrix,
        concept_pain_need_map,
        x_positioning_confidence_stats=x_positioning_confidence_stats,
        x_positioning_impact_stats=x_positioning_impact_stats,
        x_jtbd_confidence_stats=x_jtbd_confidence_stats,
        x_jtbd_impact_stats=x_jtbd_impact_stats,
        t_dimension_confidence_stats=t_dimension_confidence_stats,
        t_dimension_impact_stats=t_dimension_impact_stats,
        t_jtbd_confidence_stats=t_jtbd_confidence_stats,
        t_jtbd_impact_stats=t_jtbd_impact_stats,
    )
    presentation_page_blocks = build_presentation_page_blocks(
        x_observed_positionings=x_observed_positionings,
        generation_comparison=generation_comparison,
        competition_generation_analysis=competition_generation_analysis,
        demand_pool_snapshot=demand_pool_snapshot,
        portfolio_generation_strategy=portfolio_generation_strategy,
        x_positioning_packages=x_positioning_packages,
        x_positioning_confidence_stats=x_positioning_confidence_stats,
        x_positioning_impact_stats=x_positioning_impact_stats,
        x_jtbd_confidence_stats=x_jtbd_confidence_stats,
        x_jtbd_impact_stats=x_jtbd_impact_stats,
        t_persona_slice_cards=t_persona_slice_cards,
        t_difference_matrix=t_difference_matrix,
        t_jtbd_packages=t_jtbd_packages,
        t_dimension_confidence_stats=t_dimension_confidence_stats,
        t_dimension_impact_stats=t_dimension_impact_stats,
        t_jtbd_confidence_stats=t_jtbd_confidence_stats,
        t_jtbd_impact_stats=t_jtbd_impact_stats,
        brand_mindshare_judgments=brand_mindshare_judgments,
        idea_cluster_judgments=idea_cluster_judgments,
        strategy_translation=strategy_translation,
        cross_source_interpretation=cross_source_interpretation,
        voc_problem_packages=voc_problem_packages,
        competition_voc_xtn_breakdown=competition_voc_xtn_breakdown,
        competition_voc_market_split=competition_voc_market_split,
        awe_exhibition_signals=awe_exhibition_signals,
        competition_capability_scan=competition_capability_scan,
        competition_matchup_matrix=competition_matchup_matrix,
        competition_strategy_bridge=competition_strategy_bridge,
        self_strategy_thesis=self_strategy_thesis,
        analysis_reflection_report=analysis_reflection_report,
        competition_capture_target_candidates=competition_capture_target_candidates,
        entry_exposure_tree=entry_exposure_tree,
        voc_fact_exposure_tree=voc_fact_exposure_tree,
        user_insight_exposure_tree=user_insight_exposure_tree,
        user_strategy_convergence_tree=user_strategy_convergence_tree,
        cross_source_convergence_tree=cross_source_convergence_tree,
        competition_thesis_tree=competition_thesis_tree,
        self_strategy_thesis_tree=self_strategy_thesis_tree,
        user_thesis_tree=user_thesis_tree,
        topic_attention_matrix=topic_attention_matrix,
        problem_drilldown_packages=problem_drilldown_packages,
        survey_qual_explanation_map=survey_qual_explanation_map,
        master_judgment_tree=master_judgment_tree,
        presentation_tree=presentation_tree,
        page_metric_cards=page_metric_cards,
    )
    judgment_ready_evidence = build_judgment_ready_evidence(presentation_page_blocks)
    user_presentation_blocks = build_user_presentation_blocks(presentation_page_blocks)

    return {
        "summary_insight_cards": summary_insight_cards,
        "semantic_passages": semantic_passages,
        "concept_support_stats": concept_support_stats,
        "concept_comparison_matrix": concept_comparison_matrix,
        "concept_pain_need_map": concept_pain_need_map,
        "page_metric_cards": page_metric_cards,
        "generation_comparison": generation_comparison,
        "competition_generation_registry": competition_generation_registry,
        "competition_generation_analysis": competition_generation_analysis,
        "competition_voc_xtn_breakdown": competition_voc_xtn_breakdown,
        "competition_voc_market_split": competition_voc_market_split,
        "awe_exhibition_signals": awe_exhibition_signals,
        "competition_capability_scan": competition_capability_scan,
        "competition_matchup_matrix": competition_matchup_matrix,
        "competition_strategy_bridge": competition_strategy_bridge,
        "analysis_reflection_report": analysis_reflection_report,
        "self_strategy_thesis": self_strategy_thesis,
        "entry_exposure_tree": entry_exposure_tree,
        "voc_fact_exposure_tree": voc_fact_exposure_tree,
        "topic_attention_matrix": topic_attention_matrix,
        "problem_drilldown_packages": problem_drilldown_packages,
        "qual_evidence_packet": qual_evidence_packet,
        "qual_reasoning_task_board": qual_reasoning_task_board,
        "qual_case_reasoning_cards": qual_case_reasoning_cards,
        "qual_theme_reasoning_map": qual_theme_reasoning_map,
        "cross_source_hypothesis_board": cross_source_hypothesis_board,
        "survey_qual_explanation_map": survey_qual_explanation_map,
        "judgment_acceptance_log": judgment_acceptance_log,
        "cleaning_robot_theme_registry": cleaning_robot_theme_registry,
        "user_insight_exposure_tree": user_insight_exposure_tree,
        "user_strategy_convergence_tree": user_strategy_convergence_tree,
        "user_thesis_tree": user_thesis_tree,
        "cross_source_convergence_tree": cross_source_convergence_tree,
        "competition_thesis_tree": competition_thesis_tree,
        "self_strategy_thesis_tree": self_strategy_thesis_tree,
        "master_judgment_tree": master_judgment_tree,
        "presentation_tree": presentation_tree,
        "competition_capture_target_candidates": competition_capture_target_candidates,
        "demand_pool_snapshot": demand_pool_snapshot,
        "portfolio_generation_strategy": portfolio_generation_strategy,
        "survey_segment_comparison": survey_segment_comparison,
        "survey_concept_segments": survey_concept_segments,
        "voc_problem_packages": voc_problem_packages,
        "cross_source_interpretation": cross_source_interpretation,
        "series_positioning": series_positioning,
        "strategy_translation": strategy_translation,
        "judgment_ready_evidence": judgment_ready_evidence,
        "ppt_concept_schema": PPT_CONCEPT_SCHEMA,
        "case_concept_slots": summary_insight_cards["case_concept_slots"],  # type: ignore[index]
        "x_series_concept_map": x_series_concept_map,
        "x_case_signal_profiles": x_case_signal_profiles,
        "x_observed_positionings": x_observed_positionings,
        "t_series_concept_map": t_series_concept_map,
        "x_positioning_packages": x_positioning_packages,
        "x_positioning_confidence_stats": x_positioning_confidence_stats,
        "x_positioning_impact_stats": x_positioning_impact_stats,
        "x_jtbd_confidence_stats": x_jtbd_confidence_stats,
        "x_jtbd_impact_stats": x_jtbd_impact_stats,
        "t_persona_slice_cards": t_persona_slice_cards,
        "t_difference_matrix": t_difference_matrix,
        "t_jtbd_packages": t_jtbd_packages,
        "t_dimension_confidence_stats": t_dimension_confidence_stats,
        "t_dimension_impact_stats": t_dimension_impact_stats,
        "t_jtbd_confidence_stats": t_jtbd_confidence_stats,
        "t_jtbd_impact_stats": t_jtbd_impact_stats,
        "brand_mindshare_map": brand_mindshare_map,
        "brand_mindshare_judgments": brand_mindshare_judgments,
        "idea_pool_clusters": idea_pool_clusters,
        "idea_cluster_judgments": idea_cluster_judgments,
        "presentation_page_blocks": presentation_page_blocks,
        "user_presentation_blocks": user_presentation_blocks,
    }


def build_artifact_index(artifact_paths: list[Path]) -> dict[str, object]:
    artifact_index: dict[str, object] = {
        "main_report": "",
        "integrated_strategy_report": "",
        "presentation_main_report": "",
        "presentation_brief": "",
        "report_assembly_cards": "",
        "value_proposition_cards": "",
        "competition_engineering_evidence_cards": "",
        "value_config_test_map": "",
        "competitive_gap_attribution_cards": "",
        "next_gen_config_test_inputs": "",
        "future_intelligence_signals": "",
        "dreame_roadmap_timeline": "",
        "roadmap_stress_test_cards": "",
        "future_competition_strategy_inputs": "",
        "summary_insight_cards": "",
        "semantic_passages": "",
        "judgment_ready_evidence": "",
        "concept_support_stats": "",
        "concept_comparison_matrix": "",
        "concept_pain_need_map": "",
        "page_metric_cards": "",
        "generation_comparison": "",
        "competition_generation_registry": "",
        "competition_generation_analysis": "",
        "competition_voc_xtn_breakdown": "",
        "competition_voc_market_split": "",
        "awe_exhibition_signals": "",
        "competition_capability_scan": "",
        "competition_matchup_matrix": "",
        "competition_strategy_bridge": "",
        "analysis_reflection_report": "",
        "analysis_reflection_report_json": "",
        "self_strategy_thesis": "",
        "entry_exposure_tree": "",
        "cleaning_robot_theme_registry": "",
        "voc_fact_exposure_tree": "",
        "topic_attention_matrix": "",
        "problem_drilldown_packages": "",
        "qual_evidence_packet": "",
        "qual_reasoning_task_board": "",
        "qual_case_reasoning_cards": "",
        "qual_theme_reasoning_map": "",
        "cross_source_hypothesis_board": "",
        "survey_qual_explanation_map": "",
        "judgment_acceptance_log": "",
        "user_insight_exposure_tree": "",
        "user_strategy_convergence_tree": "",
        "user_thesis_tree": "",
        "cross_source_convergence_tree": "",
        "competition_thesis_tree": "",
        "self_strategy_thesis_tree": "",
        "master_judgment_tree": "",
        "presentation_tree": "",
        "user_presentation_blocks": "",
        "mirror_review_loop_report": "",
        "mirror_open_risks": "",
        "competition_capture_target_candidates": "",
        "competition_data_gap_diagnosis": "",
        "competition_capture_target_manifest_template": "",
        "competition_capture_target_manifest_ready": "",
        "competition_capture_target_manifest_summary": "",
        "competition_capture_execution_log": "",
        "demand_pool_snapshot": "",
        "portfolio_generation_strategy": "",
        "survey_segment_comparison": "",
        "survey_concept_segments": "",
        "voc_problem_packages": "",
        "cross_source_interpretation": "",
        "series_positioning": "",
        "strategy_translation": "",
        "ppt_concept_schema": "",
        "case_concept_slots": "",
        "x_series_concept_map": "",
        "x_case_signal_profiles": "",
        "x_observed_positionings": "",
        "t_series_concept_map": "",
        "x_positioning_packages": "",
        "x_positioning_confidence_stats": "",
        "x_positioning_impact_stats": "",
        "x_jtbd_confidence_stats": "",
        "x_jtbd_impact_stats": "",
        "t_persona_slice_cards": "",
        "t_difference_matrix": "",
        "t_jtbd_packages": "",
        "t_dimension_confidence_stats": "",
        "t_dimension_impact_stats": "",
        "t_jtbd_confidence_stats": "",
        "t_jtbd_impact_stats": "",
        "brand_mindshare_map": "",
        "brand_mindshare_judgments": "",
        "idea_pool_clusters": "",
        "idea_cluster_judgments": "",
        "presentation_page_blocks": "",
        "ppt_gap_diagnosis": "",
        "competition_data_gap_diagnosis": "",
        "pairwise_text_deep_dive": "",
        "issue_closure_report": "",
        "voc_full_appendix": "",
        "direct_source_coverage": "",
        "backfill_task_order": "",
        "backfill_task_board": "",
        "backfill_task_tracker": "",
        "before_after_comparison": "",
        "artifact_manifest": "",
        "other_artifacts": [],
    }
    name_map = {
        "main_report.md": "main_report",
        "integrated_strategy_report.md": "integrated_strategy_report",
        "presentation_main_report.md": "presentation_main_report",
        "presentation_brief.md": "presentation_brief",
        "report_assembly_cards.json": "report_assembly_cards",
        "value_proposition_cards.json": "value_proposition_cards",
        "competition_engineering_evidence_cards.json": "competition_engineering_evidence_cards",
        "value_config_test_map.json": "value_config_test_map",
        "competitive_gap_attribution_cards.json": "competitive_gap_attribution_cards",
        "next_gen_config_test_inputs.json": "next_gen_config_test_inputs",
        "future_intelligence_signals.json": "future_intelligence_signals",
        "dreame_roadmap_timeline.json": "dreame_roadmap_timeline",
        "roadmap_stress_test_cards.json": "roadmap_stress_test_cards",
        "future_competition_strategy_inputs.json": "future_competition_strategy_inputs",
        "summary_insight_cards.json": "summary_insight_cards",
        "semantic_passages.json": "semantic_passages",
        "judgment_ready_evidence.json": "judgment_ready_evidence",
        "concept_support_stats.json": "concept_support_stats",
        "concept_comparison_matrix.json": "concept_comparison_matrix",
        "concept_pain_need_map.json": "concept_pain_need_map",
        "page_metric_cards.json": "page_metric_cards",
        "generation_comparison.json": "generation_comparison",
        "competition_generation_registry.json": "competition_generation_registry",
        "competition_generation_analysis.json": "competition_generation_analysis",
        "competition_voc_xtn_breakdown.json": "competition_voc_xtn_breakdown",
        "competition_voc_market_split.json": "competition_voc_market_split",
        "awe_exhibition_signals.json": "awe_exhibition_signals",
        "competition_capability_scan.json": "competition_capability_scan",
        "competition_matchup_matrix.json": "competition_matchup_matrix",
        "competition_strategy_bridge.json": "competition_strategy_bridge",
        "analysis_reflection_report.json": "analysis_reflection_report_json",
        "analysis_reflection_report.md": "analysis_reflection_report",
        "self_strategy_thesis.json": "self_strategy_thesis",
        "entry_exposure_tree.json": "entry_exposure_tree",
        "cleaning_robot_theme_registry.json": "cleaning_robot_theme_registry",
        "voc_fact_exposure_tree.json": "voc_fact_exposure_tree",
        "topic_attention_matrix.json": "topic_attention_matrix",
        "problem_drilldown_packages.json": "problem_drilldown_packages",
        "qual_evidence_packet.json": "qual_evidence_packet",
        "qual_reasoning_task_board.json": "qual_reasoning_task_board",
        "qual_case_reasoning_cards.json": "qual_case_reasoning_cards",
        "qual_theme_reasoning_map.json": "qual_theme_reasoning_map",
        "cross_source_hypothesis_board.json": "cross_source_hypothesis_board",
        "survey_qual_explanation_map.json": "survey_qual_explanation_map",
        "judgment_acceptance_log.json": "judgment_acceptance_log",
        "user_insight_exposure_tree.json": "user_insight_exposure_tree",
        "user_strategy_convergence_tree.json": "user_strategy_convergence_tree",
        "user_thesis_tree.json": "user_thesis_tree",
        "cross_source_convergence_tree.json": "cross_source_convergence_tree",
        "competition_thesis_tree.json": "competition_thesis_tree",
        "self_strategy_thesis_tree.json": "self_strategy_thesis_tree",
        "master_judgment_tree.json": "master_judgment_tree",
        "presentation_tree.json": "presentation_tree",
        "user_presentation_blocks.json": "user_presentation_blocks",
        "mirror_review_loop_report.json": "mirror_review_loop_report",
        "mirror_open_risks.md": "mirror_open_risks",
        "competition_capture_target_candidates.md": "competition_capture_target_candidates",
        "competition_data_gap_diagnosis.md": "competition_data_gap_diagnosis",
        "competition_capture_target_manifest_template.csv": "competition_capture_target_manifest_template",
        "competition_capture_target_manifest_ready.csv": "competition_capture_target_manifest_ready",
        "competition_capture_target_manifest_summary.md": "competition_capture_target_manifest_summary",
        "competition_capture_execution_log.md": "competition_capture_execution_log",
        "demand_pool_snapshot.json": "demand_pool_snapshot",
        "portfolio_generation_strategy.json": "portfolio_generation_strategy",
        "survey_segment_comparison.json": "survey_segment_comparison",
        "survey_concept_segments.json": "survey_concept_segments",
        "voc_problem_packages.json": "voc_problem_packages",
        "cross_source_interpretation.json": "cross_source_interpretation",
        "series_positioning.json": "series_positioning",
        "strategy_translation.json": "strategy_translation",
        "ppt_concept_schema.json": "ppt_concept_schema",
        "case_concept_slots.json": "case_concept_slots",
        "x_series_concept_map.json": "x_series_concept_map",
        "x_case_signal_profiles.json": "x_case_signal_profiles",
        "x_observed_positionings.json": "x_observed_positionings",
        "t_series_concept_map.json": "t_series_concept_map",
        "x_positioning_packages.json": "x_positioning_packages",
        "x_positioning_confidence_stats.json": "x_positioning_confidence_stats",
        "x_positioning_impact_stats.json": "x_positioning_impact_stats",
        "x_jtbd_confidence_stats.json": "x_jtbd_confidence_stats",
        "x_jtbd_impact_stats.json": "x_jtbd_impact_stats",
        "t_persona_slice_cards.json": "t_persona_slice_cards",
        "t_difference_matrix.json": "t_difference_matrix",
        "t_jtbd_packages.json": "t_jtbd_packages",
        "t_dimension_confidence_stats.json": "t_dimension_confidence_stats",
        "t_dimension_impact_stats.json": "t_dimension_impact_stats",
        "t_jtbd_confidence_stats.json": "t_jtbd_confidence_stats",
        "t_jtbd_impact_stats.json": "t_jtbd_impact_stats",
        "brand_mindshare_map.json": "brand_mindshare_map",
        "brand_mindshare_judgments.json": "brand_mindshare_judgments",
        "idea_pool_clusters.json": "idea_pool_clusters",
        "idea_cluster_judgments.json": "idea_cluster_judgments",
        "presentation_page_blocks.json": "presentation_page_blocks",
        "ppt_gap_diagnosis.md": "ppt_gap_diagnosis",
        "competition_data_gap_diagnosis.md": "competition_data_gap_diagnosis",
        "pairwise_text_deep_dive.md": "pairwise_text_deep_dive",
        "issue_closure_report.md": "issue_closure_report",
        "voc_full_appendix.md": "voc_full_appendix",
        "direct_source_coverage.md": "direct_source_coverage",
        "backfill_task_order.md": "backfill_task_order",
        "backfill_task_board.md": "backfill_task_board",
        "backfill_task_tracker.md": "backfill_task_tracker",
        "before_after_comparison.md": "before_after_comparison",
        "artifact_manifest.json": "artifact_manifest",
    }
    for path in artifact_paths:
        key = name_map.get(path.name)
        if key:
            artifact_index[key] = str(path)
        else:
            artifact_index["other_artifacts"].append(str(path))
    artifact_index["other_artifacts"] = sorted(set(artifact_index["other_artifacts"]))
    return artifact_index


def write_manifest(
    out_dir: Path,
    artifact_paths: list[Path],
    *,
    bundle_id: str,
    category_name: str,
    primary_self_spu_id: str,
    primary_competitor_spu_id: str,
    bundle_mode: str,
    response_curator_packaging: dict[str, object] | None = None,
) -> Path:
    manifest_path = out_dir / "artifact_manifest.json"
    artifact_index = build_artifact_index(artifact_paths + [manifest_path])
    manifest = {
        "asset_id": "robot-product-voc-survey-insight",
        "artifact_paths": [str(path) for path in artifact_paths if path.exists()],
        "artifact_index": artifact_index,
        "verification_status": "passed",
        "produced_at": datetime.now().isoformat(timespec="seconds"),
        "bundle_id": bundle_id,
        "bundle_mode": bundle_mode,
        "category_name": category_name,
        "primary_self_spu_id": primary_self_spu_id,
        "primary_competitor_spu_id": primary_competitor_spu_id,
    }
    if response_curator_packaging:
        manifest["response_curator_packaging"] = response_curator_packaging
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def existing_competition_capture_artifact_paths(out_dir: Path) -> list[Path]:
    candidates = [
        out_dir / "competition_capture_target_manifest_template.csv",
        out_dir / "competition_capture_target_manifest_ready.csv",
        out_dir / "competition_capture_target_manifest_summary.md",
        out_dir / "competition_capture_execution_log.md",
    ]
    return [path for path in candidates if path.exists()]


def package_primary_artifacts_with_response_curator(
    *,
    artifact_paths: list[Path],
    category_name: str,
    market: str,
    time_scope: str,
    analysis_goal_text: str,
    bundle_mode: str,
    style_profile: dict[str, object],
    higher_order_artifacts: dict[str, object],
) -> dict[str, object]:
    artifact_index = build_artifact_index(artifact_paths)
    packaging_request = build_artifact_packaging_request(
        artifact_index=artifact_index,
        category_name=category_name,
        market=market,
        time_scope=time_scope,
        analysis_goal_text=analysis_goal_text,
        bundle_mode=bundle_mode,
        style_profile=style_profile,
        higher_order_artifacts=higher_order_artifacts,
    )
    return apply_response_curator_to_primary_artifacts(packaging_request)


def load_runtime_json_artifacts(
    out_dir: Path,
    artifact_keys: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    artifacts: dict[str, dict[str, object]] = {}
    missing_files: list[str] = []
    for artifact_key in artifact_keys:
        artifact_path = out_dir / f"{artifact_key}.json"
        if not artifact_path.exists():
            missing_files.append(artifact_path.name)
            continue
        artifacts[artifact_key] = read_json(artifact_path)
    if missing_files:
        raise FileNotFoundError(f"user_chain 增量刷新缺少必要 runtime 真源：{', '.join(missing_files)}")
    return artifacts


def list_runtime_artifact_paths(out_dir: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in out_dir.iterdir()
            if path.is_file() and path.name != "artifact_manifest.json"
        ]
    )


def normalize_user_refresh_scope(scope: object) -> str:
    text = str(scope or "").strip() or "user_chain"
    return "user_exposure" if text == "user_chain" else text


def refresh_scope_includes(scope: str, stage: str) -> bool:
    normalized_scope = normalize_user_refresh_scope(scope)
    if normalized_scope not in USER_CHAIN_REFRESH_STAGE_ORDER or stage not in USER_CHAIN_REFRESH_STAGE_ORDER:
        return False
    return USER_CHAIN_REFRESH_STAGE_ORDER[normalized_scope] <= USER_CHAIN_REFRESH_STAGE_ORDER[stage]


def resolve_user_refresh_start_step(
    *,
    refresh_scope: str,
    target_builders: list[str] | None = None,
    target_artifacts: list[str] | None = None,
) -> str:
    load_user_chain_dependency_registry()
    return resolve_user_chain_start_step(
        refresh_scope=refresh_scope,
        target_builders=target_builders,
        target_artifacts=target_artifacts,
    )


def coerce_refresh_targets(value: object) -> list[str]:
    return coerce_registry_targets(value)


def resolve_user_refresh_active_steps(
    *,
    refresh_scope: str,
    target_builders: list[str] | None = None,
    target_artifacts: list[str] | None = None,
) -> set[str]:
    load_user_chain_dependency_registry()
    return resolve_user_chain_active_steps(
        refresh_scope=refresh_scope,
        target_builders=target_builders,
        target_artifacts=target_artifacts,
    )


def refresh_portfolio_user_chain_runtime(
    *,
    args: argparse.Namespace,
    out_dir: Path,
    style_profile: dict[str, object],
) -> Path:
    normalized_scope = normalize_user_refresh_scope(getattr(args, "refresh_scope", "user_chain"))
    target_builders = coerce_refresh_targets(getattr(args, "target_builder", None))
    target_artifacts = coerce_refresh_targets(getattr(args, "target_artifact", None))
    start_step = resolve_user_refresh_start_step(
        refresh_scope=normalized_scope,
        target_builders=target_builders,
        target_artifacts=target_artifacts,
    )
    active_steps = resolve_user_refresh_active_steps(
        refresh_scope=normalized_scope,
        target_builders=target_builders,
        target_artifacts=target_artifacts,
    )
    manifest_path = out_dir / "artifact_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("`--refresh-scope user_chain/user_exposure/user_reasoning/user_closure` 需要先有现成的 portfolio_full runtime 与 artifact_manifest.json。")
    existing_manifest = read_json(manifest_path)
    artifacts = load_runtime_json_artifacts(out_dir, USER_CHAIN_REFRESH_RUNTIME_INPUTS)
    portfolio_category = str(
        existing_manifest.get("category_name")
        or (args.category_name if args.category_name != "机器人产品" else "扫地机器人")
    )
    consistent_issues: list[list[object]] = []
    consistent_strengths: list[list[object]] = []
    conflict_rows: list[list[object]] = []
    priority_rows: list[list[object]] = []

    if "build_qual_evidence_packet" in active_steps or "build_cross_source_interpretation" in active_steps:
        portfolio_result = collect_series_result(
            category_name=portfolio_category,
            cohort_ids=PORTFOLIO_FULL_COHORT_IDS,
            market=args.market,
            survey_topics=args.survey_topic,
            require_voc=args.require_voc,
            preserve_non_voc_selected=True,
        )
        selected_spu_ids = [
            str(row.get("spu_id", "")).strip()
            for row in (portfolio_result.get("selected_spus", []) or [])
            if str(row.get("spu_id", "")).strip()
        ]
        survey_rows = portfolio_result.get("survey_rows", []) or []
        effective_survey_rows = survey_rows if survey_rows else fetch_proxy_survey_rows_or_empty(selected_spu_ids, args.market)
        summary_conn = connect(SUMMARY_DB)
        try:
            summary_sections = fetch_summary_theme_sections(summary_conn, selected_spu_ids, args.market)
        finally:
            summary_conn.close()
        summary_theme_evidence = build_summary_theme_evidence(summary_sections)

        survey_wave_details = []
        survey_conn = connect(SURVEY_DB)
        try:
            for wave_row in effective_survey_rows:
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
            survey_open_answer_rows = fetch_survey_open_answer_rows(survey_conn, effective_survey_rows)
        finally:
            survey_conn.close()
        survey_theme_evidence = build_survey_theme_evidence(survey_wave_details)
        voc_conn = connect_live_voc_preferred()
        try:
            theme_rows, negative_rows, _ = fetch_voc_theme_rows(voc_conn, selected_spu_ids)
            user_attention_source_rows = fetch_user_attention_source_rows(
                voc_conn,
                collect_user_attention_spu_ids(selected_spu_ids, artifacts["competition_voc_xtn_breakdown"]),
            )
        finally:
            voc_conn.close()
        voc_theme_evidence = build_voc_theme_evidence(theme_rows, negative_rows)
        consistent_issues, consistent_strengths, conflict_rows, priority_rows = build_cross_source_tables(
            voc_theme_evidence,
            survey_theme_evidence,
            summary_theme_evidence,
        )

        if "build_cleaning_robot_theme_registry" in active_steps:
            artifacts["cleaning_robot_theme_registry"] = build_cleaning_robot_theme_registry(user_attention_source_rows)
        if "build_topic_attention_matrix" in active_steps:
            artifacts["topic_attention_matrix"] = build_topic_attention_matrix(
                user_attention_source_rows,
                artifacts["cleaning_robot_theme_registry"],
            )
        if "build_problem_drilldown_packages" in active_steps:
            artifacts["problem_drilldown_packages"] = build_problem_drilldown_packages(
                user_attention_source_rows,
                artifacts["topic_attention_matrix"],
                artifacts["case_concept_slots"],
                artifacts["cleaning_robot_theme_registry"],
            )

        if "build_qual_evidence_packet" in active_steps:
            artifacts["qual_evidence_packet"] = build_qual_evidence_packet(
                semantic_passages=artifacts["semantic_passages"],
                topic_attention_matrix=artifacts["topic_attention_matrix"],
                problem_drilldown_packages=artifacts["problem_drilldown_packages"],
                survey_segment_comparison=artifacts["survey_segment_comparison"],
                survey_concept_segments=artifacts["survey_concept_segments"],
                survey_open_answer_rows=survey_open_answer_rows,
            )
        if "run_dual_engine_reasoning" in active_steps:
            reasoning_bundle = run_dual_engine_reasoning(
                analysis_engine=getattr(args, "analysis_engine", "rule_only"),
                qual_evidence_packet=artifacts["qual_evidence_packet"],
                llm_profile_path=getattr(args, "llm_profile_path", None),
                qual_reasoning_profile=getattr(args, "qual_reasoning_profile", "qual_default"),
                thesis_reasoning_profile=getattr(args, "thesis_reasoning_profile", "thesis_default"),
            )
            artifacts["qual_reasoning_task_board"] = reasoning_bundle["qual_reasoning_task_board"]
            artifacts["qual_case_reasoning_cards"] = reasoning_bundle["qual_case_reasoning_cards"]
            artifacts["qual_theme_reasoning_map"] = reasoning_bundle["qual_theme_reasoning_map"]
            artifacts["cross_source_hypothesis_board"] = reasoning_bundle["cross_source_hypothesis_board"]
        if "evaluate_candidate_claims" in active_steps:
            candidate_claims = reasoning_bundle["candidate_claims"] if 'reasoning_bundle' in locals() else []
            fallback_status = str(reasoning_bundle.get("fallback_status", "")) if 'reasoning_bundle' in locals() else ""
            artifacts["judgment_acceptance_log"] = evaluate_candidate_claims(
                candidate_claims,
                artifacts["qual_evidence_packet"],
                analysis_engine=getattr(args, "analysis_engine", "rule_only"),
                fallback_status=fallback_status,
                cross_source_hypothesis_board=artifacts["cross_source_hypothesis_board"],
                qual_theme_reasoning_map=artifacts["qual_theme_reasoning_map"],
            )
        if "build_cross_source_interpretation" in active_steps:
            artifacts["cross_source_interpretation"] = build_cross_source_interpretation(
                consistent_issues,
                consistent_strengths,
                conflict_rows,
                priority_rows,
                artifacts["summary_insight_cards"],
                artifacts["survey_segment_comparison"],
                artifacts["voc_problem_packages"],
                qual_evidence_packet=artifacts["qual_evidence_packet"],
                cross_source_hypothesis_board=artifacts["cross_source_hypothesis_board"],
                judgment_acceptance_log=artifacts["judgment_acceptance_log"],
            )
        if "build_series_positioning" in active_steps:
            artifacts["series_positioning"] = build_series_positioning(
                artifacts["summary_insight_cards"],
                artifacts["survey_segment_comparison"],
                artifacts["cross_source_interpretation"],
            )
        if "build_strategy_translation" in active_steps:
            artifacts["strategy_translation"] = build_strategy_translation(
                artifacts["cross_source_interpretation"],
                artifacts["voc_problem_packages"],
                artifacts["summary_insight_cards"],
                artifacts["series_positioning"],
            )
        if "build_survey_qual_explanation_map" in active_steps:
            artifacts["survey_qual_explanation_map"] = build_survey_qual_explanation_map(
                artifacts["case_concept_slots"],
                artifacts["survey_segment_comparison"],
                artifacts["survey_concept_segments"],
                artifacts["x_positioning_packages"],
                artifacts["t_jtbd_packages"],
                artifacts["topic_attention_matrix"],
                artifacts["problem_drilldown_packages"],
                artifacts["cleaning_robot_theme_registry"],
                qual_evidence_packet=artifacts["qual_evidence_packet"],
                qual_case_reasoning_cards=artifacts["qual_case_reasoning_cards"],
                qual_theme_reasoning_map=artifacts["qual_theme_reasoning_map"],
                judgment_acceptance_log=artifacts["judgment_acceptance_log"],
            )
        if "build_user_insight_exposure_tree" in active_steps:
            artifacts["user_insight_exposure_tree"] = build_user_insight_exposure_tree(
                artifacts["x_observed_positionings"],
                artifacts["x_positioning_packages"],
                artifacts["t_persona_slice_cards"],
                artifacts["t_difference_matrix"],
                artifacts["t_jtbd_packages"],
                artifacts["generation_comparison"],
                entry_exposure_tree=artifacts["entry_exposure_tree"],
                topic_attention_matrix=artifacts["topic_attention_matrix"],
                problem_drilldown_packages=artifacts["problem_drilldown_packages"],
                survey_qual_explanation_map=artifacts["survey_qual_explanation_map"],
            )
    if "build_user_strategy_convergence_tree" in active_steps:
        artifacts["user_strategy_convergence_tree"] = build_user_strategy_convergence_tree(
            artifacts["user_insight_exposure_tree"],
            artifacts["series_positioning"],
            artifacts["x_positioning_packages"],
            artifacts["t_jtbd_packages"],
        )
    if "build_user_thesis_tree" in active_steps:
        artifacts["user_thesis_tree"] = build_user_thesis_tree(
            artifacts["user_strategy_convergence_tree"],
            artifacts["topic_attention_matrix"],
            artifacts["problem_drilldown_packages"],
            qual_evidence_packet=artifacts["qual_evidence_packet"],
            qual_theme_reasoning_map=artifacts["qual_theme_reasoning_map"],
            cross_source_hypothesis_board=artifacts["cross_source_hypothesis_board"],
            judgment_acceptance_log=artifacts["judgment_acceptance_log"],
        )
    if "build_cross_source_convergence_tree" in active_steps:
        artifacts["cross_source_convergence_tree"] = build_cross_source_convergence_tree(
            artifacts["cross_source_interpretation"],
            artifacts["series_positioning"],
            artifacts["strategy_translation"],
            artifacts["competition_voc_xtn_breakdown"],
        )
    if "build_self_strategy_thesis_tree" in active_steps:
        artifacts["self_strategy_thesis_tree"] = build_self_strategy_thesis_tree(
            artifacts["self_strategy_thesis"],
            artifacts["portfolio_generation_strategy"],
            artifacts["cross_source_convergence_tree"],
            artifacts["competition_capture_target_candidates"],
        )
    if "build_master_judgment_tree" in active_steps:
        artifacts["master_judgment_tree"] = build_master_judgment_tree(
            artifacts["user_strategy_convergence_tree"],
            artifacts["competition_thesis_tree"],
            artifacts["self_strategy_thesis_tree"],
        )
    if "build_presentation_tree" in active_steps:
        artifacts["presentation_tree"] = build_presentation_tree(
            artifacts["user_insight_exposure_tree"],
            artifacts["user_strategy_convergence_tree"],
            artifacts["competition_thesis_tree"],
            artifacts["self_strategy_thesis_tree"],
            artifacts["analysis_reflection_report"],
        )
    if "build_presentation_page_blocks" in active_steps:
        artifacts["presentation_page_blocks"] = build_presentation_page_blocks(
            x_observed_positionings=artifacts["x_observed_positionings"],
            generation_comparison=artifacts["generation_comparison"],
            competition_generation_analysis=artifacts["competition_generation_analysis"],
            competition_voc_xtn_breakdown=artifacts["competition_voc_xtn_breakdown"],
            competition_voc_market_split=artifacts["competition_voc_market_split"],
            awe_exhibition_signals=artifacts["awe_exhibition_signals"],
            competition_capability_scan=artifacts["competition_capability_scan"],
            competition_matchup_matrix=artifacts["competition_matchup_matrix"],
            competition_strategy_bridge=artifacts["competition_strategy_bridge"],
            self_strategy_thesis=artifacts["self_strategy_thesis"],
            analysis_reflection_report=artifacts["analysis_reflection_report"],
            competition_capture_target_candidates=artifacts["competition_capture_target_candidates"],
            entry_exposure_tree=artifacts["entry_exposure_tree"],
            voc_fact_exposure_tree=artifacts["voc_fact_exposure_tree"],
            user_insight_exposure_tree=artifacts["user_insight_exposure_tree"],
            user_strategy_convergence_tree=artifacts["user_strategy_convergence_tree"],
            user_thesis_tree=artifacts["user_thesis_tree"],
            topic_attention_matrix=artifacts["topic_attention_matrix"],
            problem_drilldown_packages=artifacts["problem_drilldown_packages"],
            survey_qual_explanation_map=artifacts["survey_qual_explanation_map"],
            cross_source_convergence_tree=artifacts["cross_source_convergence_tree"],
            competition_thesis_tree=artifacts["competition_thesis_tree"],
            self_strategy_thesis_tree=artifacts["self_strategy_thesis_tree"],
            master_judgment_tree=artifacts["master_judgment_tree"],
            presentation_tree=artifacts["presentation_tree"],
            demand_pool_snapshot=artifacts["demand_pool_snapshot"],
            portfolio_generation_strategy=artifacts["portfolio_generation_strategy"],
            x_positioning_packages=artifacts["x_positioning_packages"],
            x_positioning_confidence_stats=artifacts["x_positioning_confidence_stats"],
            x_positioning_impact_stats=artifacts["x_positioning_impact_stats"],
            x_jtbd_confidence_stats=artifacts["x_jtbd_confidence_stats"],
            x_jtbd_impact_stats=artifacts["x_jtbd_impact_stats"],
            t_persona_slice_cards=artifacts["t_persona_slice_cards"],
            t_difference_matrix=artifacts["t_difference_matrix"],
            t_jtbd_packages=artifacts["t_jtbd_packages"],
            t_dimension_confidence_stats=artifacts["t_dimension_confidence_stats"],
            t_dimension_impact_stats=artifacts["t_dimension_impact_stats"],
            t_jtbd_confidence_stats=artifacts["t_jtbd_confidence_stats"],
            t_jtbd_impact_stats=artifacts["t_jtbd_impact_stats"],
            brand_mindshare_judgments=artifacts["brand_mindshare_judgments"],
            idea_cluster_judgments=artifacts["idea_cluster_judgments"],
            strategy_translation=artifacts["strategy_translation"],
            cross_source_interpretation=artifacts["cross_source_interpretation"],
            voc_problem_packages=artifacts["voc_problem_packages"],
            page_metric_cards=artifacts["page_metric_cards"],
        )
    if "build_user_presentation_blocks" in active_steps:
        artifacts["user_presentation_blocks"] = build_user_presentation_blocks(artifacts["presentation_page_blocks"])

    final_presentation_report = out_dir.joinpath("presentation_main_report.md").read_text(encoding="utf-8") if (out_dir / "presentation_main_report.md").exists() else ""
    mirror_review_loop_report = read_json(out_dir / "mirror_review_loop_report.json") if (out_dir / "mirror_review_loop_report.json").exists() else {}
    mirror_open_risks = (out_dir / "mirror_open_risks.md").read_text(encoding="utf-8") if (out_dir / "mirror_open_risks.md").exists() else ""
    if "run_user_presentation_composer" in active_steps:
        final_presentation_report, mirror_review_loop_report, mirror_open_risks = run_user_presentation_composer(
            category_name=portfolio_category,
            time_scope=args.time_scope,
            market=args.market,
            analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "基于当前已经输入的全量本品和竞品数据，回答用户关心的核心用户问题",
            style_profile=style_profile,
            higher_order_artifacts=artifacts,
        )

    for artifact_key in USER_CHAIN_REFRESH_OUTPUT_KEYS:
        write_json(out_dir / f"{artifact_key}.json", artifacts[artifact_key])
    write_text(out_dir / "presentation_main_report.md", final_presentation_report)
    write_json(out_dir / "mirror_review_loop_report.json", mirror_review_loop_report)
    write_text(out_dir / "mirror_open_risks.md", mirror_open_risks)
    response_curator_packaging = package_primary_artifacts_with_response_curator(
        artifact_paths=list_runtime_artifact_paths(out_dir),
        category_name=portfolio_category,
        market=args.market,
        time_scope=args.time_scope,
        analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "基于当前已经输入的全量本品和竞品数据，回答用户关心的核心用户问题",
        bundle_mode=str(existing_manifest.get("bundle_mode", args.bundle_mode)),
        style_profile=style_profile,
        higher_order_artifacts=artifacts,
    )

    return write_manifest(
        out_dir,
        list_runtime_artifact_paths(out_dir),
        bundle_id=str(existing_manifest.get("bundle_id", out_dir.name)),
        category_name=portfolio_category,
        primary_self_spu_id=str(existing_manifest.get("primary_self_spu_id", "")),
        primary_competitor_spu_id=str(existing_manifest.get("primary_competitor_spu_id", "")),
        bundle_mode=str(existing_manifest.get("bundle_mode", args.bundle_mode)),
        response_curator_packaging=response_curator_packaging,
    )


def main() -> None:
    args = parse_args()
    style_profile = read_json(STYLE_PROFILE_PATH) if STYLE_PROFILE_PATH.exists() else {}
    if args.refresh_scope != "full" and args.bundle_mode != "portfolio_full":
        raise SystemExit("`--refresh-scope user_chain/user_exposure/user_reasoning/user_closure` 仅支持 `--bundle-mode portfolio_full`。")
    if args.bundle_mode == "portfolio_full":
        bundle_id = choose_bundle_id(args, {"selected_spus": []})
        out_dir = ensure_out_dir(args, bundle_id)
        if args.refresh_scope != "full":
            manifest_path = refresh_portfolio_user_chain_runtime(
                args=args,
                out_dir=out_dir,
                style_profile=style_profile,
            )
            print(f"written_bundle={out_dir}")
            print(f"artifact_manifest={manifest_path}")
            return
        artifact_paths: list[Path] = []
        portfolio_category = args.category_name if args.category_name != "机器人产品" else "扫地机器人"
        series_payloads: list[dict[str, object]] = []
        portfolio_result = collect_series_result(
            category_name=portfolio_category,
            cohort_ids=PORTFOLIO_FULL_COHORT_IDS,
            market=args.market,
            survey_topics=args.survey_topic,
            require_voc=args.require_voc,
            preserve_non_voc_selected=True,
        )
        higher_order_artifacts = build_higher_order_artifacts(args, portfolio_result)

        for config in PORTFOLIO_FULL_SERIES:
            result = collect_series_result(
                category_name=portfolio_category,
                cohort_ids=config["cohort_ids"],
                market=args.market,
                survey_topics=args.survey_topic,
                require_voc=args.require_voc,
                preserve_non_voc_selected=True,
            )
            series_markdown = render_series_report(
                result,
                analysis_title=config["analysis_title"],
                time_scope=args.time_scope,
                market=args.market,
                analysis_goal=args.analysis_goal,
            )
            series_payload = {
                "series_code": config["series_code"],
                "series_label": config["series_label"],
                "result": result,
                "series_markdown": series_markdown,
            }
            series_payloads.append(series_payload)

            series_report_path = out_dir / f"{config['series_code'].lower()}_series_report.md"
            write_text(series_report_path, series_markdown)
            artifact_paths.append(series_report_path)

            primary_self = pick_primary_self(result)
            primary_competitor = pick_primary_competitor(args, result)
            if primary_self and primary_competitor:
                pairwise_path = out_dir / f"{config['series_code'].lower()}_series_pairwise_text_deep_dive.md"
                issue_path = out_dir / f"{config['series_code'].lower()}_series_issue_closure_report.md"
                appendix_path = out_dir / f"{config['series_code'].lower()}_series_voc_full_appendix.md"
                write_text(pairwise_path, build_pairwise_text_deep_dive(primary_self["spu_id"], primary_competitor["spu_id"]))
                write_text(issue_path, build_issue_closure_report(primary_self["spu_id"], primary_competitor["spu_id"]))
                write_text(appendix_path, build_voc_appendix(primary_self["spu_id"]))
                artifact_paths.extend([pairwise_path, issue_path, appendix_path])

        main_report_path = out_dir / "main_report.md"
        integrated_strategy_report_path = out_dir / "integrated_strategy_report.md"
        presentation_main_report_path = out_dir / "presentation_main_report.md"
        presentation_brief_path = out_dir / "presentation_brief.md"
        report_assembly_cards_path = out_dir / "report_assembly_cards.json"
        value_proposition_cards_path = out_dir / "value_proposition_cards.json"
        competition_engineering_evidence_cards_path = out_dir / "competition_engineering_evidence_cards.json"
        value_config_test_map_path = out_dir / "value_config_test_map.json"
        competitive_gap_attribution_cards_path = out_dir / "competitive_gap_attribution_cards.json"
        next_gen_config_test_inputs_path = out_dir / "next_gen_config_test_inputs.json"
        future_intelligence_signals_path = out_dir / "future_intelligence_signals.json"
        dreame_roadmap_timeline_path = out_dir / "dreame_roadmap_timeline.json"
        roadmap_stress_test_cards_path = out_dir / "roadmap_stress_test_cards.json"
        future_competition_strategy_inputs_path = out_dir / "future_competition_strategy_inputs.json"
        before_after_path = out_dir / "before_after_comparison.md"
        direct_path = out_dir / "direct_source_coverage.md"
        order_path = out_dir / "backfill_task_order.md"
        board_path = out_dir / "backfill_task_board.md"
        tracker_path = out_dir / "backfill_task_tracker.md"
        summary_insight_cards_path = out_dir / "summary_insight_cards.json"
        semantic_passages_path = out_dir / "semantic_passages.json"
        judgment_ready_evidence_path = out_dir / "judgment_ready_evidence.json"
        concept_support_stats_path = out_dir / "concept_support_stats.json"
        concept_comparison_matrix_path = out_dir / "concept_comparison_matrix.json"
        concept_pain_need_map_path = out_dir / "concept_pain_need_map.json"
        page_metric_cards_path = out_dir / "page_metric_cards.json"
        generation_comparison_path = out_dir / "generation_comparison.json"
        competition_generation_registry_path = out_dir / "competition_generation_registry.json"
        competition_generation_analysis_path = out_dir / "competition_generation_analysis.json"
        competition_voc_xtn_breakdown_path = out_dir / "competition_voc_xtn_breakdown.json"
        competition_voc_market_split_path = out_dir / "competition_voc_market_split.json"
        awe_exhibition_signals_path = out_dir / "awe_exhibition_signals.json"
        competition_capability_scan_path = out_dir / "competition_capability_scan.json"
        competition_matchup_matrix_path = out_dir / "competition_matchup_matrix.json"
        competition_strategy_bridge_path = out_dir / "competition_strategy_bridge.json"
        analysis_reflection_report_json_path = out_dir / "analysis_reflection_report.json"
        analysis_reflection_report_md_path = out_dir / "analysis_reflection_report.md"
        self_strategy_thesis_path = out_dir / "self_strategy_thesis.json"
        entry_exposure_tree_path = out_dir / "entry_exposure_tree.json"
        cleaning_robot_theme_registry_path = out_dir / "cleaning_robot_theme_registry.json"
        voc_fact_exposure_tree_path = out_dir / "voc_fact_exposure_tree.json"
        topic_attention_matrix_path = out_dir / "topic_attention_matrix.json"
        problem_drilldown_packages_path = out_dir / "problem_drilldown_packages.json"
        qual_evidence_packet_path = out_dir / "qual_evidence_packet.json"
        qual_reasoning_task_board_path = out_dir / "qual_reasoning_task_board.json"
        qual_case_reasoning_cards_path = out_dir / "qual_case_reasoning_cards.json"
        qual_theme_reasoning_map_path = out_dir / "qual_theme_reasoning_map.json"
        cross_source_hypothesis_board_path = out_dir / "cross_source_hypothesis_board.json"
        survey_qual_explanation_map_path = out_dir / "survey_qual_explanation_map.json"
        judgment_acceptance_log_path = out_dir / "judgment_acceptance_log.json"
        user_insight_exposure_tree_path = out_dir / "user_insight_exposure_tree.json"
        user_strategy_convergence_tree_path = out_dir / "user_strategy_convergence_tree.json"
        user_thesis_tree_path = out_dir / "user_thesis_tree.json"
        cross_source_convergence_tree_path = out_dir / "cross_source_convergence_tree.json"
        competition_thesis_tree_path = out_dir / "competition_thesis_tree.json"
        self_strategy_thesis_tree_path = out_dir / "self_strategy_thesis_tree.json"
        master_judgment_tree_path = out_dir / "master_judgment_tree.json"
        presentation_tree_path = out_dir / "presentation_tree.json"
        user_presentation_blocks_path = out_dir / "user_presentation_blocks.json"
        mirror_review_loop_report_path = out_dir / "mirror_review_loop_report.json"
        mirror_open_risks_path = out_dir / "mirror_open_risks.md"
        competition_capture_target_candidates_path = out_dir / "competition_capture_target_candidates.md"
        demand_pool_snapshot_path = out_dir / "demand_pool_snapshot.json"
        portfolio_generation_strategy_path = out_dir / "portfolio_generation_strategy.json"
        survey_segment_comparison_path = out_dir / "survey_segment_comparison.json"
        survey_concept_segments_path = out_dir / "survey_concept_segments.json"
        voc_problem_packages_path = out_dir / "voc_problem_packages.json"
        cross_source_interpretation_path = out_dir / "cross_source_interpretation.json"
        series_positioning_path = out_dir / "series_positioning.json"
        strategy_translation_path = out_dir / "strategy_translation.json"
        ppt_concept_schema_path = out_dir / "ppt_concept_schema.json"
        case_concept_slots_path = out_dir / "case_concept_slots.json"
        x_series_concept_map_path = out_dir / "x_series_concept_map.json"
        x_case_signal_profiles_path = out_dir / "x_case_signal_profiles.json"
        x_observed_positionings_path = out_dir / "x_observed_positionings.json"
        t_series_concept_map_path = out_dir / "t_series_concept_map.json"
        x_positioning_packages_path = out_dir / "x_positioning_packages.json"
        x_positioning_confidence_stats_path = out_dir / "x_positioning_confidence_stats.json"
        x_positioning_impact_stats_path = out_dir / "x_positioning_impact_stats.json"
        x_jtbd_confidence_stats_path = out_dir / "x_jtbd_confidence_stats.json"
        x_jtbd_impact_stats_path = out_dir / "x_jtbd_impact_stats.json"
        t_persona_slice_cards_path = out_dir / "t_persona_slice_cards.json"
        t_difference_matrix_path = out_dir / "t_difference_matrix.json"
        t_jtbd_packages_path = out_dir / "t_jtbd_packages.json"
        t_dimension_confidence_stats_path = out_dir / "t_dimension_confidence_stats.json"
        t_dimension_impact_stats_path = out_dir / "t_dimension_impact_stats.json"
        t_jtbd_confidence_stats_path = out_dir / "t_jtbd_confidence_stats.json"
        t_jtbd_impact_stats_path = out_dir / "t_jtbd_impact_stats.json"
        brand_mindshare_map_path = out_dir / "brand_mindshare_map.json"
        brand_mindshare_judgments_path = out_dir / "brand_mindshare_judgments.json"
        idea_pool_clusters_path = out_dir / "idea_pool_clusters.json"
        idea_cluster_judgments_path = out_dir / "idea_cluster_judgments.json"
        presentation_page_blocks_path = out_dir / "presentation_page_blocks.json"
        ppt_gap_diagnosis_path = out_dir / "ppt_gap_diagnosis.md"
        competition_data_gap_diagnosis_path = out_dir / "competition_data_gap_diagnosis.md"
        main_report_text = render_portfolio_full_report(
            category_name=portfolio_category,
            time_scope=args.time_scope,
            market=args.market,
            series_payloads=series_payloads,
            analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "基于当前已经输入的全量本品和竞品数据，回答用户关心的核心用户问题",
        )
        value_proposition_cards = build_value_proposition_cards(
            series_payloads=series_payloads,
            args=args,
            generated_from="portfolio_full/main_report.md",
        )
        competition_engineering_artifacts = build_competition_engineering_extension_artifacts(
            series_payloads=series_payloads,
            args=args,
            generated_from="portfolio_full/main_report.md",
        )
        future_intelligence_artifacts = build_future_intelligence_extension_artifacts(
            generated_from="portfolio_full/main_report.md",
        )
        report_assembly_cards = build_report_assembly_cards(
            value_proposition_cards=value_proposition_cards,
            competition_engineering_artifacts=competition_engineering_artifacts,
            future_intelligence_artifacts=future_intelligence_artifacts,
            demand_pool_snapshot=higher_order_artifacts["demand_pool_snapshot"],
            generated_from="portfolio_full/integrated_strategy_report.md",
        )
        integrated_strategy_report_text = render_integrated_strategy_report(
            category_name=portfolio_category,
            time_scope=args.time_scope,
            market=args.market,
            analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "基于当前已经输入的全量本品和竞品数据，回答用户关心的核心用户问题",
            report_assembly_cards=report_assembly_cards,
        )
        write_text(
            main_report_path,
            main_report_text,
        )
        write_text(integrated_strategy_report_path, integrated_strategy_report_text)
        final_presentation_report, mirror_review_loop_report, mirror_open_risks = run_user_presentation_composer(
            category_name=portfolio_category,
            time_scope=args.time_scope,
            market=args.market,
            analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "基于当前已经输入的全量本品和竞品数据，回答用户关心的核心用户问题",
            style_profile=style_profile,
            higher_order_artifacts=higher_order_artifacts,
        )
        write_text(presentation_main_report_path, final_presentation_report)
        write_text(
            presentation_brief_path,
            build_portfolio_presentation_brief(
                category_name=portfolio_category,
                time_scope=args.time_scope,
                market=args.market,
                series_payloads=series_payloads,
                analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "基于当前已经输入的全量本品和竞品数据，回答用户关心的核心用户问题",
                style_profile=style_profile,
            ),
        )
        write_text(before_after_path, build_before_after_comparison(series_payloads))
        write_text(direct_path, build_portfolio_direct_source_coverage(series_payloads))
        write_text(order_path, build_portfolio_backfill_task_order(series_payloads))
        write_text(board_path, build_portfolio_backfill_task_board(series_payloads))
        write_text(tracker_path, build_portfolio_backfill_task_tracker(series_payloads))
        write_json(report_assembly_cards_path, report_assembly_cards)
        write_json(value_proposition_cards_path, value_proposition_cards)
        write_json(competition_engineering_evidence_cards_path, competition_engineering_artifacts["competition_engineering_evidence_cards"])
        write_json(value_config_test_map_path, competition_engineering_artifacts["value_config_test_map"])
        write_json(competitive_gap_attribution_cards_path, competition_engineering_artifacts["competitive_gap_attribution_cards"])
        write_json(next_gen_config_test_inputs_path, competition_engineering_artifacts["next_gen_config_test_inputs"])
        write_json(future_intelligence_signals_path, future_intelligence_artifacts["future_intelligence_signals"])
        write_json(dreame_roadmap_timeline_path, future_intelligence_artifacts["dreame_roadmap_timeline"])
        write_json(roadmap_stress_test_cards_path, future_intelligence_artifacts["roadmap_stress_test_cards"])
        write_json(future_competition_strategy_inputs_path, future_intelligence_artifacts["future_competition_strategy_inputs"])
        write_json(summary_insight_cards_path, higher_order_artifacts["summary_insight_cards"])
        write_json(semantic_passages_path, higher_order_artifacts["semantic_passages"])
        write_json(judgment_ready_evidence_path, higher_order_artifacts["judgment_ready_evidence"])
        write_json(concept_support_stats_path, higher_order_artifacts["concept_support_stats"])
        write_json(concept_comparison_matrix_path, higher_order_artifacts["concept_comparison_matrix"])
        write_json(concept_pain_need_map_path, higher_order_artifacts["concept_pain_need_map"])
        write_json(page_metric_cards_path, higher_order_artifacts["page_metric_cards"])
        write_json(generation_comparison_path, higher_order_artifacts["generation_comparison"])
        write_json(competition_generation_registry_path, higher_order_artifacts["competition_generation_registry"])
        write_json(competition_generation_analysis_path, higher_order_artifacts["competition_generation_analysis"])
        write_json(competition_voc_xtn_breakdown_path, higher_order_artifacts["competition_voc_xtn_breakdown"])
        write_json(competition_voc_market_split_path, higher_order_artifacts["competition_voc_market_split"])
        write_json(awe_exhibition_signals_path, higher_order_artifacts["awe_exhibition_signals"])
        write_json(competition_capability_scan_path, higher_order_artifacts["competition_capability_scan"])
        write_json(competition_matchup_matrix_path, higher_order_artifacts["competition_matchup_matrix"])
        write_json(competition_strategy_bridge_path, higher_order_artifacts["competition_strategy_bridge"])
        write_json(analysis_reflection_report_json_path, higher_order_artifacts["analysis_reflection_report"])
        write_text(
            analysis_reflection_report_md_path,
            render_analysis_reflection_report(higher_order_artifacts["analysis_reflection_report"]),
        )
        write_json(self_strategy_thesis_path, higher_order_artifacts["self_strategy_thesis"])
        write_json(entry_exposure_tree_path, higher_order_artifacts["entry_exposure_tree"])
        write_json(cleaning_robot_theme_registry_path, higher_order_artifacts["cleaning_robot_theme_registry"])
        write_json(voc_fact_exposure_tree_path, higher_order_artifacts["voc_fact_exposure_tree"])
        write_json(topic_attention_matrix_path, higher_order_artifacts["topic_attention_matrix"])
        write_json(problem_drilldown_packages_path, higher_order_artifacts["problem_drilldown_packages"])
        write_json(qual_evidence_packet_path, higher_order_artifacts["qual_evidence_packet"])
        write_json(qual_reasoning_task_board_path, higher_order_artifacts["qual_reasoning_task_board"])
        write_json(qual_case_reasoning_cards_path, higher_order_artifacts["qual_case_reasoning_cards"])
        write_json(qual_theme_reasoning_map_path, higher_order_artifacts["qual_theme_reasoning_map"])
        write_json(cross_source_hypothesis_board_path, higher_order_artifacts["cross_source_hypothesis_board"])
        write_json(survey_qual_explanation_map_path, higher_order_artifacts["survey_qual_explanation_map"])
        write_json(judgment_acceptance_log_path, higher_order_artifacts["judgment_acceptance_log"])
        write_json(user_insight_exposure_tree_path, higher_order_artifacts["user_insight_exposure_tree"])
        write_json(user_strategy_convergence_tree_path, higher_order_artifacts["user_strategy_convergence_tree"])
        write_json(user_thesis_tree_path, higher_order_artifacts["user_thesis_tree"])
        write_json(cross_source_convergence_tree_path, higher_order_artifacts["cross_source_convergence_tree"])
        write_json(competition_thesis_tree_path, higher_order_artifacts["competition_thesis_tree"])
        write_json(self_strategy_thesis_tree_path, higher_order_artifacts["self_strategy_thesis_tree"])
        write_json(master_judgment_tree_path, higher_order_artifacts["master_judgment_tree"])
        write_json(presentation_tree_path, higher_order_artifacts["presentation_tree"])
        write_json(user_presentation_blocks_path, higher_order_artifacts["user_presentation_blocks"])
        write_json(mirror_review_loop_report_path, mirror_review_loop_report)
        write_text(mirror_open_risks_path, mirror_open_risks)
        write_text(
            competition_capture_target_candidates_path,
            render_competition_capture_target_candidates(higher_order_artifacts["competition_capture_target_candidates"]),
        )
        write_json(demand_pool_snapshot_path, higher_order_artifacts["demand_pool_snapshot"])
        write_json(portfolio_generation_strategy_path, higher_order_artifacts["portfolio_generation_strategy"])
        write_json(survey_segment_comparison_path, higher_order_artifacts["survey_segment_comparison"])
        write_json(survey_concept_segments_path, higher_order_artifacts["survey_concept_segments"])
        write_json(voc_problem_packages_path, higher_order_artifacts["voc_problem_packages"])
        write_json(cross_source_interpretation_path, higher_order_artifacts["cross_source_interpretation"])
        write_json(series_positioning_path, higher_order_artifacts["series_positioning"])
        write_json(strategy_translation_path, higher_order_artifacts["strategy_translation"])
        write_json(ppt_concept_schema_path, higher_order_artifacts["ppt_concept_schema"])
        write_json(case_concept_slots_path, higher_order_artifacts["case_concept_slots"])
        write_json(x_series_concept_map_path, higher_order_artifacts["x_series_concept_map"])
        write_json(x_case_signal_profiles_path, higher_order_artifacts["x_case_signal_profiles"])
        write_json(x_observed_positionings_path, higher_order_artifacts["x_observed_positionings"])
        write_json(t_series_concept_map_path, higher_order_artifacts["t_series_concept_map"])
        write_json(x_positioning_packages_path, higher_order_artifacts["x_positioning_packages"])
        write_json(x_positioning_confidence_stats_path, higher_order_artifacts["x_positioning_confidence_stats"])
        write_json(x_positioning_impact_stats_path, higher_order_artifacts["x_positioning_impact_stats"])
        write_json(x_jtbd_confidence_stats_path, higher_order_artifacts["x_jtbd_confidence_stats"])
        write_json(x_jtbd_impact_stats_path, higher_order_artifacts["x_jtbd_impact_stats"])
        write_json(t_persona_slice_cards_path, higher_order_artifacts["t_persona_slice_cards"])
        write_json(t_difference_matrix_path, higher_order_artifacts["t_difference_matrix"])
        write_json(t_jtbd_packages_path, higher_order_artifacts["t_jtbd_packages"])
        write_json(t_dimension_confidence_stats_path, higher_order_artifacts["t_dimension_confidence_stats"])
        write_json(t_dimension_impact_stats_path, higher_order_artifacts["t_dimension_impact_stats"])
        write_json(t_jtbd_confidence_stats_path, higher_order_artifacts["t_jtbd_confidence_stats"])
        write_json(t_jtbd_impact_stats_path, higher_order_artifacts["t_jtbd_impact_stats"])
        write_json(brand_mindshare_map_path, higher_order_artifacts["brand_mindshare_map"])
        write_json(brand_mindshare_judgments_path, higher_order_artifacts["brand_mindshare_judgments"])
        write_json(idea_pool_clusters_path, higher_order_artifacts["idea_pool_clusters"])
        write_json(idea_cluster_judgments_path, higher_order_artifacts["idea_cluster_judgments"])
        write_json(presentation_page_blocks_path, higher_order_artifacts["presentation_page_blocks"])
        write_text(
            ppt_gap_diagnosis_path,
            build_ppt_gap_diagnosis(
                presentation_main_report_text=presentation_main_report_path.read_text(encoding="utf-8"),
                main_report_text=main_report_text,
                series_positioning=higher_order_artifacts["series_positioning"],
                strategy_translation=higher_order_artifacts["strategy_translation"],
            ),
        )
        write_text(
            competition_data_gap_diagnosis_path,
            build_competition_data_gap_diagnosis(
                higher_order_artifacts["competition_voc_xtn_breakdown"],
                higher_order_artifacts["competition_voc_market_split"],
            ),
        )
        artifact_paths.extend([
            main_report_path,
            integrated_strategy_report_path,
            presentation_main_report_path,
            presentation_brief_path,
            report_assembly_cards_path,
            before_after_path,
            direct_path,
            order_path,
            board_path,
            tracker_path,
            value_proposition_cards_path,
            competition_engineering_evidence_cards_path,
            value_config_test_map_path,
            competitive_gap_attribution_cards_path,
            next_gen_config_test_inputs_path,
            future_intelligence_signals_path,
            dreame_roadmap_timeline_path,
            roadmap_stress_test_cards_path,
            future_competition_strategy_inputs_path,
            summary_insight_cards_path,
            semantic_passages_path,
            judgment_ready_evidence_path,
            concept_support_stats_path,
            concept_comparison_matrix_path,
            concept_pain_need_map_path,
            page_metric_cards_path,
            generation_comparison_path,
            competition_generation_registry_path,
            competition_generation_analysis_path,
            competition_voc_xtn_breakdown_path,
            competition_voc_market_split_path,
            awe_exhibition_signals_path,
            competition_capability_scan_path,
            competition_matchup_matrix_path,
            competition_strategy_bridge_path,
            analysis_reflection_report_json_path,
            analysis_reflection_report_md_path,
            self_strategy_thesis_path,
            entry_exposure_tree_path,
            cleaning_robot_theme_registry_path,
            voc_fact_exposure_tree_path,
            topic_attention_matrix_path,
            problem_drilldown_packages_path,
            qual_evidence_packet_path,
            qual_reasoning_task_board_path,
            qual_case_reasoning_cards_path,
            qual_theme_reasoning_map_path,
            cross_source_hypothesis_board_path,
            survey_qual_explanation_map_path,
            judgment_acceptance_log_path,
            user_insight_exposure_tree_path,
            user_strategy_convergence_tree_path,
            user_thesis_tree_path,
            cross_source_convergence_tree_path,
            competition_thesis_tree_path,
            self_strategy_thesis_tree_path,
            master_judgment_tree_path,
            presentation_tree_path,
            user_presentation_blocks_path,
            mirror_review_loop_report_path,
            mirror_open_risks_path,
            competition_capture_target_candidates_path,
            demand_pool_snapshot_path,
            portfolio_generation_strategy_path,
            survey_segment_comparison_path,
            survey_concept_segments_path,
            voc_problem_packages_path,
            cross_source_interpretation_path,
            series_positioning_path,
            strategy_translation_path,
            ppt_concept_schema_path,
            case_concept_slots_path,
            x_series_concept_map_path,
            x_case_signal_profiles_path,
            x_observed_positionings_path,
            t_series_concept_map_path,
            x_positioning_packages_path,
            x_positioning_confidence_stats_path,
            x_positioning_impact_stats_path,
            x_jtbd_confidence_stats_path,
            x_jtbd_impact_stats_path,
            t_persona_slice_cards_path,
            t_difference_matrix_path,
            t_jtbd_packages_path,
            t_dimension_confidence_stats_path,
            t_dimension_impact_stats_path,
            t_jtbd_confidence_stats_path,
            t_jtbd_impact_stats_path,
            brand_mindshare_map_path,
            brand_mindshare_judgments_path,
            idea_pool_clusters_path,
            idea_cluster_judgments_path,
            presentation_page_blocks_path,
            ppt_gap_diagnosis_path,
            competition_data_gap_diagnosis_path,
        ])
        artifact_paths.extend(existing_competition_capture_artifact_paths(out_dir))
        response_curator_packaging = package_primary_artifacts_with_response_curator(
            artifact_paths=artifact_paths,
            category_name=portfolio_category,
            market=args.market,
            time_scope=args.time_scope,
            analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "基于当前已经输入的全量本品和竞品数据，回答用户关心的核心用户问题",
            bundle_mode=args.bundle_mode,
            style_profile=style_profile,
            higher_order_artifacts=higher_order_artifacts,
        )

        manifest_path = write_manifest(
            out_dir,
            artifact_paths,
            bundle_id=bundle_id,
            category_name=portfolio_category,
            primary_self_spu_id="ecovacs_x11,ecovacs_x12,ecovacs_t80s,ecovacs_t90",
            primary_competitor_spu_id="portfolio_full",
            bundle_mode=args.bundle_mode,
            response_curator_packaging=response_curator_packaging,
        )
        artifact_paths.append(manifest_path)
    else:
        preflight_args = argparse.Namespace(
            category_name=args.category_name,
            spu=args.spu,
            cohort_id=args.cohort_id,
            market=args.market,
            survey_topic=args.survey_topic,
            module=[],
            require_voc=args.require_voc,
            format="json",
        )
        result = collect_preflight_result(preflight_args)
        bundle_id = choose_bundle_id(args, result)
        out_dir = ensure_out_dir(args, bundle_id)

        artifact_paths = []
        higher_order_artifacts = build_higher_order_artifacts(args, result)

        main_report = render_main_report(args, result, higher_order_artifacts=higher_order_artifacts)
        main_report_path = out_dir / "main_report.md"
        integrated_strategy_report_path = out_dir / "integrated_strategy_report.md"
        presentation_main_report_path = out_dir / "presentation_main_report.md"
        presentation_brief_path = out_dir / "presentation_brief.md"
        report_assembly_cards_path = out_dir / "report_assembly_cards.json"
        value_proposition_cards_path = out_dir / "value_proposition_cards.json"
        competition_engineering_evidence_cards_path = out_dir / "competition_engineering_evidence_cards.json"
        value_config_test_map_path = out_dir / "value_config_test_map.json"
        competitive_gap_attribution_cards_path = out_dir / "competitive_gap_attribution_cards.json"
        next_gen_config_test_inputs_path = out_dir / "next_gen_config_test_inputs.json"
        future_intelligence_signals_path = out_dir / "future_intelligence_signals.json"
        dreame_roadmap_timeline_path = out_dir / "dreame_roadmap_timeline.json"
        roadmap_stress_test_cards_path = out_dir / "roadmap_stress_test_cards.json"
        future_competition_strategy_inputs_path = out_dir / "future_competition_strategy_inputs.json"
        summary_insight_cards_path = out_dir / "summary_insight_cards.json"
        semantic_passages_path = out_dir / "semantic_passages.json"
        judgment_ready_evidence_path = out_dir / "judgment_ready_evidence.json"
        concept_support_stats_path = out_dir / "concept_support_stats.json"
        concept_comparison_matrix_path = out_dir / "concept_comparison_matrix.json"
        concept_pain_need_map_path = out_dir / "concept_pain_need_map.json"
        page_metric_cards_path = out_dir / "page_metric_cards.json"
        generation_comparison_path = out_dir / "generation_comparison.json"
        competition_generation_registry_path = out_dir / "competition_generation_registry.json"
        competition_generation_analysis_path = out_dir / "competition_generation_analysis.json"
        competition_voc_xtn_breakdown_path = out_dir / "competition_voc_xtn_breakdown.json"
        competition_voc_market_split_path = out_dir / "competition_voc_market_split.json"
        awe_exhibition_signals_path = out_dir / "awe_exhibition_signals.json"
        competition_capability_scan_path = out_dir / "competition_capability_scan.json"
        competition_matchup_matrix_path = out_dir / "competition_matchup_matrix.json"
        competition_strategy_bridge_path = out_dir / "competition_strategy_bridge.json"
        analysis_reflection_report_json_path = out_dir / "analysis_reflection_report.json"
        analysis_reflection_report_md_path = out_dir / "analysis_reflection_report.md"
        self_strategy_thesis_path = out_dir / "self_strategy_thesis.json"
        entry_exposure_tree_path = out_dir / "entry_exposure_tree.json"
        cleaning_robot_theme_registry_path = out_dir / "cleaning_robot_theme_registry.json"
        voc_fact_exposure_tree_path = out_dir / "voc_fact_exposure_tree.json"
        topic_attention_matrix_path = out_dir / "topic_attention_matrix.json"
        problem_drilldown_packages_path = out_dir / "problem_drilldown_packages.json"
        qual_evidence_packet_path = out_dir / "qual_evidence_packet.json"
        qual_reasoning_task_board_path = out_dir / "qual_reasoning_task_board.json"
        qual_case_reasoning_cards_path = out_dir / "qual_case_reasoning_cards.json"
        qual_theme_reasoning_map_path = out_dir / "qual_theme_reasoning_map.json"
        cross_source_hypothesis_board_path = out_dir / "cross_source_hypothesis_board.json"
        survey_qual_explanation_map_path = out_dir / "survey_qual_explanation_map.json"
        judgment_acceptance_log_path = out_dir / "judgment_acceptance_log.json"
        user_insight_exposure_tree_path = out_dir / "user_insight_exposure_tree.json"
        user_strategy_convergence_tree_path = out_dir / "user_strategy_convergence_tree.json"
        user_thesis_tree_path = out_dir / "user_thesis_tree.json"
        cross_source_convergence_tree_path = out_dir / "cross_source_convergence_tree.json"
        competition_thesis_tree_path = out_dir / "competition_thesis_tree.json"
        self_strategy_thesis_tree_path = out_dir / "self_strategy_thesis_tree.json"
        master_judgment_tree_path = out_dir / "master_judgment_tree.json"
        presentation_tree_path = out_dir / "presentation_tree.json"
        user_presentation_blocks_path = out_dir / "user_presentation_blocks.json"
        mirror_review_loop_report_path = out_dir / "mirror_review_loop_report.json"
        mirror_open_risks_path = out_dir / "mirror_open_risks.md"
        competition_capture_target_candidates_path = out_dir / "competition_capture_target_candidates.md"
        demand_pool_snapshot_path = out_dir / "demand_pool_snapshot.json"
        portfolio_generation_strategy_path = out_dir / "portfolio_generation_strategy.json"
        survey_segment_comparison_path = out_dir / "survey_segment_comparison.json"
        survey_concept_segments_path = out_dir / "survey_concept_segments.json"
        voc_problem_packages_path = out_dir / "voc_problem_packages.json"
        cross_source_interpretation_path = out_dir / "cross_source_interpretation.json"
        series_positioning_path = out_dir / "series_positioning.json"
        strategy_translation_path = out_dir / "strategy_translation.json"
        ppt_concept_schema_path = out_dir / "ppt_concept_schema.json"
        case_concept_slots_path = out_dir / "case_concept_slots.json"
        x_series_concept_map_path = out_dir / "x_series_concept_map.json"
        x_case_signal_profiles_path = out_dir / "x_case_signal_profiles.json"
        x_observed_positionings_path = out_dir / "x_observed_positionings.json"
        t_series_concept_map_path = out_dir / "t_series_concept_map.json"
        x_positioning_packages_path = out_dir / "x_positioning_packages.json"
        x_positioning_confidence_stats_path = out_dir / "x_positioning_confidence_stats.json"
        x_positioning_impact_stats_path = out_dir / "x_positioning_impact_stats.json"
        x_jtbd_confidence_stats_path = out_dir / "x_jtbd_confidence_stats.json"
        x_jtbd_impact_stats_path = out_dir / "x_jtbd_impact_stats.json"
        t_persona_slice_cards_path = out_dir / "t_persona_slice_cards.json"
        t_difference_matrix_path = out_dir / "t_difference_matrix.json"
        t_jtbd_packages_path = out_dir / "t_jtbd_packages.json"
        t_dimension_confidence_stats_path = out_dir / "t_dimension_confidence_stats.json"
        t_dimension_impact_stats_path = out_dir / "t_dimension_impact_stats.json"
        t_jtbd_confidence_stats_path = out_dir / "t_jtbd_confidence_stats.json"
        t_jtbd_impact_stats_path = out_dir / "t_jtbd_impact_stats.json"
        brand_mindshare_map_path = out_dir / "brand_mindshare_map.json"
        brand_mindshare_judgments_path = out_dir / "brand_mindshare_judgments.json"
        idea_pool_clusters_path = out_dir / "idea_pool_clusters.json"
        idea_cluster_judgments_path = out_dir / "idea_cluster_judgments.json"
        presentation_page_blocks_path = out_dir / "presentation_page_blocks.json"
        ppt_gap_diagnosis_path = out_dir / "ppt_gap_diagnosis.md"
        competition_data_gap_diagnosis_path = out_dir / "competition_data_gap_diagnosis.md"
        write_text(main_report_path, main_report)
        artifact_paths.append(main_report_path)
        final_presentation_report, mirror_review_loop_report, mirror_open_risks = run_user_presentation_composer(
            category_name=args.category_name,
            time_scope=args.time_scope,
            market=args.market,
            analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "回答核心用户问题",
            style_profile=style_profile,
            higher_order_artifacts=higher_order_artifacts,
        )
        write_text(presentation_main_report_path, final_presentation_report)
        artifact_paths.append(presentation_main_report_path)
        write_text(presentation_brief_path, build_standard_presentation_brief(args, result, style_profile))
        artifact_paths.append(presentation_brief_path)
        value_proposition_cards = build_value_proposition_cards(
            series_payloads=[
                {
                    "series_code": infer_result_series_code(result),
                    "series_label": SERIES_VALUE_PROPOSITION_DEFAULTS.get(
                        infer_result_series_code(result),
                        SERIES_VALUE_PROPOSITION_DEFAULTS["default"],
                    )["series_label"],
                    "result": result,
                }
            ],
            args=args,
            generated_from="single_series/main_report.md",
        )
        single_series_payloads = [
            {
                "series_code": infer_result_series_code(result),
                "series_label": SERIES_VALUE_PROPOSITION_DEFAULTS.get(
                    infer_result_series_code(result),
                    SERIES_VALUE_PROPOSITION_DEFAULTS["default"],
                )["series_label"],
                "result": result,
            }
        ]
        competition_engineering_artifacts = build_competition_engineering_extension_artifacts(
            series_payloads=single_series_payloads,
            args=args,
            generated_from="single_series/main_report.md",
        )
        future_intelligence_artifacts = build_future_intelligence_extension_artifacts(
            generated_from="single_series/main_report.md",
        )
        report_assembly_cards = build_report_assembly_cards(
            value_proposition_cards=value_proposition_cards,
            competition_engineering_artifacts=competition_engineering_artifacts,
            future_intelligence_artifacts=future_intelligence_artifacts,
            demand_pool_snapshot=higher_order_artifacts["demand_pool_snapshot"],
            generated_from="single_series/integrated_strategy_report.md",
        )
        integrated_strategy_report = render_integrated_strategy_report(
            category_name=args.category_name,
            time_scope=args.time_scope,
            market=args.market,
            analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "回答核心用户问题",
            report_assembly_cards=report_assembly_cards,
        )
        write_text(integrated_strategy_report_path, integrated_strategy_report)
        artifact_paths.append(integrated_strategy_report_path)
        write_json(report_assembly_cards_path, report_assembly_cards)
        artifact_paths.append(report_assembly_cards_path)
        write_json(value_proposition_cards_path, value_proposition_cards)
        artifact_paths.append(value_proposition_cards_path)
        write_json(competition_engineering_evidence_cards_path, competition_engineering_artifacts["competition_engineering_evidence_cards"])
        write_json(value_config_test_map_path, competition_engineering_artifacts["value_config_test_map"])
        write_json(competitive_gap_attribution_cards_path, competition_engineering_artifacts["competitive_gap_attribution_cards"])
        write_json(next_gen_config_test_inputs_path, competition_engineering_artifacts["next_gen_config_test_inputs"])
        write_json(future_intelligence_signals_path, future_intelligence_artifacts["future_intelligence_signals"])
        write_json(dreame_roadmap_timeline_path, future_intelligence_artifacts["dreame_roadmap_timeline"])
        write_json(roadmap_stress_test_cards_path, future_intelligence_artifacts["roadmap_stress_test_cards"])
        write_json(future_competition_strategy_inputs_path, future_intelligence_artifacts["future_competition_strategy_inputs"])
        artifact_paths.extend([
            competition_engineering_evidence_cards_path,
            value_config_test_map_path,
            competitive_gap_attribution_cards_path,
            next_gen_config_test_inputs_path,
            future_intelligence_signals_path,
            dreame_roadmap_timeline_path,
            roadmap_stress_test_cards_path,
            future_competition_strategy_inputs_path,
        ])
        write_json(summary_insight_cards_path, higher_order_artifacts["summary_insight_cards"])
        write_json(semantic_passages_path, higher_order_artifacts["semantic_passages"])
        write_json(judgment_ready_evidence_path, higher_order_artifacts["judgment_ready_evidence"])
        write_json(concept_support_stats_path, higher_order_artifacts["concept_support_stats"])
        write_json(concept_comparison_matrix_path, higher_order_artifacts["concept_comparison_matrix"])
        write_json(concept_pain_need_map_path, higher_order_artifacts["concept_pain_need_map"])
        write_json(page_metric_cards_path, higher_order_artifacts["page_metric_cards"])
        write_json(generation_comparison_path, higher_order_artifacts["generation_comparison"])
        write_json(competition_generation_registry_path, higher_order_artifacts["competition_generation_registry"])
        write_json(competition_generation_analysis_path, higher_order_artifacts["competition_generation_analysis"])
        write_json(competition_voc_xtn_breakdown_path, higher_order_artifacts["competition_voc_xtn_breakdown"])
        write_json(competition_voc_market_split_path, higher_order_artifacts["competition_voc_market_split"])
        write_json(awe_exhibition_signals_path, higher_order_artifacts["awe_exhibition_signals"])
        write_json(competition_capability_scan_path, higher_order_artifacts["competition_capability_scan"])
        write_json(competition_matchup_matrix_path, higher_order_artifacts["competition_matchup_matrix"])
        write_json(competition_strategy_bridge_path, higher_order_artifacts["competition_strategy_bridge"])
        write_json(analysis_reflection_report_json_path, higher_order_artifacts["analysis_reflection_report"])
        write_text(
            analysis_reflection_report_md_path,
            render_analysis_reflection_report(higher_order_artifacts["analysis_reflection_report"]),
        )
        write_json(self_strategy_thesis_path, higher_order_artifacts["self_strategy_thesis"])
        write_json(entry_exposure_tree_path, higher_order_artifacts["entry_exposure_tree"])
        write_json(cleaning_robot_theme_registry_path, higher_order_artifacts["cleaning_robot_theme_registry"])
        write_json(voc_fact_exposure_tree_path, higher_order_artifacts["voc_fact_exposure_tree"])
        write_json(topic_attention_matrix_path, higher_order_artifacts["topic_attention_matrix"])
        write_json(problem_drilldown_packages_path, higher_order_artifacts["problem_drilldown_packages"])
        write_json(qual_evidence_packet_path, higher_order_artifacts["qual_evidence_packet"])
        write_json(qual_reasoning_task_board_path, higher_order_artifacts["qual_reasoning_task_board"])
        write_json(qual_case_reasoning_cards_path, higher_order_artifacts["qual_case_reasoning_cards"])
        write_json(qual_theme_reasoning_map_path, higher_order_artifacts["qual_theme_reasoning_map"])
        write_json(cross_source_hypothesis_board_path, higher_order_artifacts["cross_source_hypothesis_board"])
        write_json(survey_qual_explanation_map_path, higher_order_artifacts["survey_qual_explanation_map"])
        write_json(judgment_acceptance_log_path, higher_order_artifacts["judgment_acceptance_log"])
        write_json(user_insight_exposure_tree_path, higher_order_artifacts["user_insight_exposure_tree"])
        write_json(user_strategy_convergence_tree_path, higher_order_artifacts["user_strategy_convergence_tree"])
        write_json(user_thesis_tree_path, higher_order_artifacts["user_thesis_tree"])
        write_json(cross_source_convergence_tree_path, higher_order_artifacts["cross_source_convergence_tree"])
        write_json(competition_thesis_tree_path, higher_order_artifacts["competition_thesis_tree"])
        write_json(self_strategy_thesis_tree_path, higher_order_artifacts["self_strategy_thesis_tree"])
        write_json(master_judgment_tree_path, higher_order_artifacts["master_judgment_tree"])
        write_json(presentation_tree_path, higher_order_artifacts["presentation_tree"])
        write_json(user_presentation_blocks_path, higher_order_artifacts["user_presentation_blocks"])
        write_json(mirror_review_loop_report_path, mirror_review_loop_report)
        write_text(mirror_open_risks_path, mirror_open_risks)
        write_text(
            competition_capture_target_candidates_path,
            render_competition_capture_target_candidates(higher_order_artifacts["competition_capture_target_candidates"]),
        )
        write_json(demand_pool_snapshot_path, higher_order_artifacts["demand_pool_snapshot"])
        write_json(portfolio_generation_strategy_path, higher_order_artifacts["portfolio_generation_strategy"])
        write_json(survey_segment_comparison_path, higher_order_artifacts["survey_segment_comparison"])
        write_json(survey_concept_segments_path, higher_order_artifacts["survey_concept_segments"])
        write_json(voc_problem_packages_path, higher_order_artifacts["voc_problem_packages"])
        write_json(cross_source_interpretation_path, higher_order_artifacts["cross_source_interpretation"])
        write_json(series_positioning_path, higher_order_artifacts["series_positioning"])
        write_json(strategy_translation_path, higher_order_artifacts["strategy_translation"])
        write_json(ppt_concept_schema_path, higher_order_artifacts["ppt_concept_schema"])
        write_json(case_concept_slots_path, higher_order_artifacts["case_concept_slots"])
        write_json(x_series_concept_map_path, higher_order_artifacts["x_series_concept_map"])
        write_json(x_case_signal_profiles_path, higher_order_artifacts["x_case_signal_profiles"])
        write_json(x_observed_positionings_path, higher_order_artifacts["x_observed_positionings"])
        write_json(t_series_concept_map_path, higher_order_artifacts["t_series_concept_map"])
        write_json(x_positioning_packages_path, higher_order_artifacts["x_positioning_packages"])
        write_json(x_positioning_confidence_stats_path, higher_order_artifacts["x_positioning_confidence_stats"])
        write_json(x_positioning_impact_stats_path, higher_order_artifacts["x_positioning_impact_stats"])
        write_json(x_jtbd_confidence_stats_path, higher_order_artifacts["x_jtbd_confidence_stats"])
        write_json(x_jtbd_impact_stats_path, higher_order_artifacts["x_jtbd_impact_stats"])
        write_json(t_persona_slice_cards_path, higher_order_artifacts["t_persona_slice_cards"])
        write_json(t_difference_matrix_path, higher_order_artifacts["t_difference_matrix"])
        write_json(t_jtbd_packages_path, higher_order_artifacts["t_jtbd_packages"])
        write_json(t_dimension_confidence_stats_path, higher_order_artifacts["t_dimension_confidence_stats"])
        write_json(t_dimension_impact_stats_path, higher_order_artifacts["t_dimension_impact_stats"])
        write_json(t_jtbd_confidence_stats_path, higher_order_artifacts["t_jtbd_confidence_stats"])
        write_json(t_jtbd_impact_stats_path, higher_order_artifacts["t_jtbd_impact_stats"])
        write_json(brand_mindshare_map_path, higher_order_artifacts["brand_mindshare_map"])
        write_json(brand_mindshare_judgments_path, higher_order_artifacts["brand_mindshare_judgments"])
        write_json(idea_pool_clusters_path, higher_order_artifacts["idea_pool_clusters"])
        write_json(idea_cluster_judgments_path, higher_order_artifacts["idea_cluster_judgments"])
        write_json(presentation_page_blocks_path, higher_order_artifacts["presentation_page_blocks"])
        write_text(
            ppt_gap_diagnosis_path,
            build_ppt_gap_diagnosis(
                presentation_main_report_text=presentation_main_report_path.read_text(encoding="utf-8"),
                main_report_text=main_report,
                series_positioning=higher_order_artifacts["series_positioning"],
                strategy_translation=higher_order_artifacts["strategy_translation"],
            ),
        )
        write_text(
            competition_data_gap_diagnosis_path,
            build_competition_data_gap_diagnosis(
                higher_order_artifacts["competition_voc_xtn_breakdown"],
                higher_order_artifacts["competition_voc_market_split"],
            ),
        )
        artifact_paths.extend([
            summary_insight_cards_path,
            semantic_passages_path,
            judgment_ready_evidence_path,
            concept_support_stats_path,
            concept_comparison_matrix_path,
            concept_pain_need_map_path,
            page_metric_cards_path,
            generation_comparison_path,
            competition_generation_registry_path,
            competition_generation_analysis_path,
            competition_voc_xtn_breakdown_path,
            competition_voc_market_split_path,
            awe_exhibition_signals_path,
            competition_capability_scan_path,
            competition_matchup_matrix_path,
            competition_strategy_bridge_path,
            analysis_reflection_report_json_path,
            analysis_reflection_report_md_path,
            self_strategy_thesis_path,
            entry_exposure_tree_path,
            cleaning_robot_theme_registry_path,
            voc_fact_exposure_tree_path,
            topic_attention_matrix_path,
            problem_drilldown_packages_path,
            qual_evidence_packet_path,
            qual_reasoning_task_board_path,
            qual_case_reasoning_cards_path,
            qual_theme_reasoning_map_path,
            cross_source_hypothesis_board_path,
            survey_qual_explanation_map_path,
            judgment_acceptance_log_path,
            user_insight_exposure_tree_path,
            user_strategy_convergence_tree_path,
            user_thesis_tree_path,
            cross_source_convergence_tree_path,
            competition_thesis_tree_path,
            self_strategy_thesis_tree_path,
            master_judgment_tree_path,
            presentation_tree_path,
            user_presentation_blocks_path,
            mirror_review_loop_report_path,
            mirror_open_risks_path,
            competition_capture_target_candidates_path,
            demand_pool_snapshot_path,
            portfolio_generation_strategy_path,
            survey_segment_comparison_path,
            survey_concept_segments_path,
            voc_problem_packages_path,
            cross_source_interpretation_path,
            series_positioning_path,
            strategy_translation_path,
            ppt_concept_schema_path,
            case_concept_slots_path,
            x_series_concept_map_path,
            x_case_signal_profiles_path,
            x_observed_positionings_path,
            t_series_concept_map_path,
            x_positioning_packages_path,
            x_positioning_confidence_stats_path,
            x_positioning_impact_stats_path,
            x_jtbd_confidence_stats_path,
            x_jtbd_impact_stats_path,
            t_persona_slice_cards_path,
            t_difference_matrix_path,
            t_jtbd_packages_path,
            t_dimension_confidence_stats_path,
            t_dimension_impact_stats_path,
            t_jtbd_confidence_stats_path,
            t_jtbd_impact_stats_path,
            brand_mindshare_map_path,
            brand_mindshare_judgments_path,
            idea_pool_clusters_path,
            idea_cluster_judgments_path,
            presentation_page_blocks_path,
            ppt_gap_diagnosis_path,
            competition_data_gap_diagnosis_path,
        ])
        artifact_paths.extend(existing_competition_capture_artifact_paths(out_dir))

        primary_self = pick_primary_self(result)
        primary_competitor = pick_primary_competitor(args, result)

        if primary_self and primary_competitor:
            text_deep_dive = build_pairwise_text_deep_dive(primary_self["spu_id"], primary_competitor["spu_id"])
            issue_closure = build_issue_closure_report(primary_self["spu_id"], primary_competitor["spu_id"])
            appendix = build_voc_appendix(primary_self["spu_id"])
            pairwise_path = out_dir / "pairwise_text_deep_dive.md"
            issue_path = out_dir / "issue_closure_report.md"
            appendix_path = out_dir / "voc_full_appendix.md"
            write_text(pairwise_path, text_deep_dive)
            write_text(issue_path, issue_closure)
            write_text(appendix_path, appendix)
            artifact_paths.extend([pairwise_path, issue_path, appendix_path])

        if primary_self:
            selected_spus = result["selected_spus"]  # type: ignore[index]
            competitor_ids = [row["spu_id"] for row in selected_spus if row.get("self_competitor_type") == "competitor"]
            direct_coverage = build_direct_source_coverage(result)
            task_order = build_backfill_task_order(primary_self["spu_id"], competitor_ids)
            task_board = build_backfill_task_board(primary_self["spu_id"], competitor_ids)
            task_tracker = build_backfill_task_tracker(primary_self["spu_id"], competitor_ids)
            direct_path = out_dir / "direct_source_coverage.md"
            order_path = out_dir / "backfill_task_order.md"
            board_path = out_dir / "backfill_task_board.md"
            tracker_path = out_dir / "backfill_task_tracker.md"
            write_text(direct_path, direct_coverage)
            write_text(order_path, task_order)
            write_text(board_path, task_board)
            write_text(tracker_path, task_tracker)
            artifact_paths.extend([direct_path, order_path, board_path, tracker_path])
        response_curator_packaging = package_primary_artifacts_with_response_curator(
            artifact_paths=artifact_paths,
            category_name=args.category_name,
            market=args.market,
            time_scope=args.time_scope,
            analysis_goal_text="；".join(args.analysis_goal) if args.analysis_goal else "回答核心用户问题",
            bundle_mode=args.bundle_mode,
            style_profile=style_profile,
            higher_order_artifacts=higher_order_artifacts,
        )

        manifest_path = write_manifest(
            out_dir,
            artifact_paths,
            bundle_id=bundle_id,
            category_name=args.category_name,
            primary_self_spu_id=primary_self["spu_id"] if primary_self else "",
            primary_competitor_spu_id=primary_competitor["spu_id"] if primary_competitor else "",
            bundle_mode=args.bundle_mode,
            response_curator_packaging=response_curator_packaging,
        )
        artifact_paths.append(manifest_path)

    print(f"written_bundle={out_dir}")
    print(f"artifact_manifest={manifest_path}")


if __name__ == "__main__":
    main()
