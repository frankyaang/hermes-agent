#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_ROOT.parents[2]
SPU_ALIAS_RULE_PATH = WORKSPACE_ROOT / "local-data" / "cleaning_robot_competitive_ops_fact" / "metadata" / "spu_alias_rule.csv"


ARCHETYPE_RULES = [
    ("托管减负型", ("解放双手", "不想自己", "减少家务", "省心", "自动开始清洁", "自动感知", "不用手动")),
    ("工具务实型", ("80%", "够用", "工具", "日常清洁", "基本预期", "不追求极致", "自己收尾", "务实", "中规中矩", "性价比", "细致")),
    ("表达展示型", ("颜值即正义", "科技感", "软装", "社交货币", "品位", "展示品", "高端的外观设计", "情绪价值", "新潮")),
    ("责任平衡型", ("家庭责任", "顶梁柱", "孩子", "家庭抱怨", "平衡", "分担", "承担全部家务")),
    ("秩序掌控型", ("检查", "确认", "不信任", "掌控", "看得见", "可视化", "巡检")),
]

HOME_PATTERNS = [
    ("养宠家庭", ("猫", "狗", "宠物", "猫砂", "宠物毛发")),
    ("有娃家庭", ("有娃", "孩子", "小孩", "宝宝", "爬爬垫")),
    ("高压双职工", ("上班", "工作日", "下班", "出门", "公司")),
    ("精装/新房", ("新房", "精装修", "精装", "装修", "预留")),
    ("大户型", ("121平", "150", "167平", "220㎡", "三室两厅", "合院", "高层")),
]

CLEANING_ATTITUDE_RULES = [
    ("完成度优先", ("80%", "够用", "完成清洁任务", "日常维护")),
    ("清洁标准高", ("洁癖", "要求较高", "干净", "卫生标准")),
    ("介入容忍度低", ("不想自己动手", "减少家务", "不想介入", "不用我来反复检查")),
    ("维护容忍度低", ("维护麻烦", "发臭", "不想伺候机器", "拒绝半路维护")),
]

PURCHASE_TRIGGER_RULES = [
    ("新房/装修触发", ("新房", "装修", "预留位置", "开荒")),
    ("家庭责任触发", ("孩子", "家庭抱怨", "家务", "照顾孩子")),
    ("宠物场景触发", ("宠物", "猫砂", "宠物毛发", "呕吐物")),
    ("技术升级触发", ("功能不断升级", "机械臂", "高温活水", "滚筒")),
]

CHANNEL_RULES = [
    ("内容平台", ("抖音", "小红书", "YouTube", "测评")),
    ("朋友推荐", ("朋友", "姐姐家", "亲戚家", "推荐")),
    ("论坛社区", ("论坛", "Naver", "业主群")),
    ("电商下单", ("天猫", "淘宝", "京东", "coupang", "NAVER")),
    ("线下体验", ("商场", "线下", "门店")),
]

DECISION_FACTOR_RULES = [
    ("解放双手", ("解放双手", "减少家务", "省心")),
    ("颜值/家居融合", ("颜值", "外观", "软装", "家居美学")),
    ("维护便利", ("维护简单", "免维护", "发臭", "清理方便")),
    ("清洁能力", ("清洁效果", "边角", "污渍", "拖地", "吸力")),
    ("智能性/托管", ("智能", "托管", "避障", "语音", "自动")),
]

HIDDEN_NEED_RULES = [
    ("可确认的掌控感", ("不信任", "检查", "确认", "看得见", "对比")),
    ("家务负担转移", ("减少家务", "解放双手", "分担", "抱怨")),
    ("真正托管", ("不用我管", "自动", "自己知道", "从大脑中删除")),
    ("身份表达", ("品位", "科技感", "软装", "社交货币")),
]

DAMAGE_TYPE_RULES = [
    ("清洁结果受损", ("水渍水痕", "拖地效果差", "清洁效果差", "顽固污渍拖不干净")),
    ("工作完成率受损", ("边角漏扫", "边角清洁效果差", "清扫效率低")),
    ("无人值守失败", ("台阶过不去", "避障失败", "越障能力差", "地毯卡困", "桌椅腿卡困")),
    ("维护负担上升", ("故障报警多", "发臭", "维护麻烦", "集尘不干净")),
    ("使用时窗受损", ("扫拖噪音大", "噪音", "异音")),
]

TRUST_IMPACT_RULES = {
    "清洁结果受损": "伤害清洁结果信任",
    "工作完成率受损": "伤害工作完成率信任",
    "无人值守失败": "伤害省心感与托管信任",
    "维护负担上升": "伤害免维护信任",
    "使用时窗受损": "压缩可使用时窗",
}

BRAND_LABELS = ["科沃斯", "石头", "追觅", "云鲸", "大疆", "小米"]
BRAND_POSITIVE_HINTS = ("第一", "最终购买", "推荐", "高端", "专业", "标杆", "不错", "好", "匹配", "适合", "优势", "信任", "放心", "喜欢", "突出", "强")
BRAND_NEGATIVE_HINTS = ("靠后", "放弃", "排除", "担心", "一般", "不突出", "贵", "不够", "问题", "不喜欢", "玩票", "不考虑", "劝退", "直接排除", "无感", "停滞", "不放心", "糟糕", "差")
BRAND_HEADER_HINTS = ("品牌 | 受访者认知", "品牌认知", "对RVC品牌认知", "熟知品牌包括", "了解的品牌包括")

X_POSITIONING_RULES = [
    ("清洁帮手", ("80%", "工具", "够用", "自己收尾", "不添乱", "日常清洁", "完成80%的工作", "辅助", "性价比", "基础清洁", "少维护", "好用")),
    ("清洁管家", ("自动感知", "自己知道", "主动", "不用我管", "托管", "巡航清洁", "全权负责", "从大脑中删除", "无感", "家庭管家", "场景智能", "省心托管")),
    ("社交名片", ("社交货币", "软装", "品位", "展示品", "话题", "科技感", "颜值即正义", "顶尖科技", "黑科技", "新潮", "技术先锋", "社交溢价")),
]

T_ROLE_MODE_RULES = [
    ("个人优先", ("删除待办", "彻底删除", "还算干净就行", "选择个人", "效率问题", "个人时间", "轻松", "光脚自由", "不想自己动手", "有闲", "独居", "单身")),
    ("平衡共处", ("和平共处", "不影响家庭成员", "自动化保障", "不能消耗我额外的心力", "稳定输出", "独立妻子", "平衡", "分工", "不打扰", "松弛有度")),
    ("家庭投入", ("一系列清洁标准", "可调节", "可监控", "反复检查", "补救", "投入家庭", "家庭顶梁柱", "秩序守护者", "妈妈", "爸爸", "家庭为中心", "家务压力")),
]

T_DIFFERENCE_DIMENSION_RULES = [
    ("生命阶段与角色冲突", ("婚后", "丈夫角色转变", "宝宝", "孩子", "独子", "家庭责任", "新婚", "丁克", "育儿", "妈妈", "爸爸", "角色转变")),
    ("自我认同与思维模式", ("自主决策", "问题解决", "奉献", "生活品质", "个人时间", "自我判断", "人设", "精致", "女强人", "艺术", "秩序感", "价值证明")),
    ("家庭结构与权力动态", ("财政大权", "分工", "父母", "婆婆", "另一半", "谁做决策", "家庭分工", "长辈", "三代同堂", "丈夫", "妻子")),
]

X_JTBD_RULES = [
    ("地面基础清洁代劳", ("地面基础清洁", "重复性劳动", "高效可靠", "善后工作", "基础清洁", "别添乱", "少维护")),
    ("整体洁净托管", ("整体洁净", "卫生标准", "突发状况", "生活变化", "确定的洁净感", "无感服务", "从大脑中删除", "不用我管")),
    ("科技美学表达", ("科技美学装置", "科技敏感度", "生活品味", "谈资", "社交货币", "黑科技", "新鲜事物")),
]

X_ROLE_LABEL_ALLOWED_SUFFIXES = ("帮手", "管家", "搭子", "玩家", "主理", "顾问", "助手", "副手", "主理人")

X_ROLE_LABEL_SCHEMA = {
    "基础代劳信号": {
        "canonical_anchor": "清洁帮手",
        "label_candidates": ["清洁帮手", "清洁搭子", "清洁副手"],
        "role_family": "帮手系标签",
        "keywords": ("80%", "够用", "别添乱", "不添乱", "少维护", "自己收尾", "补尾", "基础清洁", "日常清洁", "辅助", "性价比", "少操心"),
        "hallmark_keywords": ("80%", "少维护", "补尾", "不添乱", "基础清洁"),
        "preferred_roles": ["人物定义", "清洁态度", "购买决策", "痛点", "期待"],
        "negative_keywords": ("黑科技", "软装", "科技感", "主动感知", "自己知道", "不用我管", "社交"),
    },
    "低介入托管信号": {
        "canonical_anchor": "清洁管家",
        "label_candidates": ["清洁管家", "清洁主理", "清洁顾问"],
        "role_family": "管家系标签",
        "keywords": ("托管", "少操心", "不用我管", "自己知道", "主动", "无感", "省心", "自动感知", "从大脑中删除", "主动补位", "免维护", "少返工", "零动手", "低介入"),
        "hallmark_keywords": ("托管", "少操心", "主动", "无感", "自己知道"),
        "preferred_roles": ["人物定义", "清洁态度", "购买决策", "痛点", "期待", "隐性需求"],
        "negative_keywords": ("80%", "自己收尾", "黑科技", "谈资", "社交货币"),
    },
    "科技表达信号": {
        "canonical_anchor": "社交名片",
        "label_candidates": ["科技玩家", "清洁玩家", "科技主理人"],
        "role_family": "玩家/表达系标签",
        "keywords": ("黑科技", "科技感", "颜值", "软装", "品位", "谈资", "新技术", "设计", "高端感", "溢价", "可被看见", "可被讨论", "生活品味"),
        "hallmark_keywords": ("黑科技", "科技感", "外观", "颜值", "设计", "高端"),
        "expression_anchor_keywords": ("软装", "品位", "生活品味", "社交", "谈资", "悦己", "实体勋章", "可被看见", "可被讨论", "高质量社交"),
        "preferred_roles": ["人物定义", "购买决策", "品牌认知", "期待", "金点子"],
        "negative_keywords": ("80%", "自己收尾", "补尾", "少维护", "不用我管"),
    },
}

T_JTBD_RULES = [
    ("个人优先", ("彻底删除", "认知和待办", "还算干净的家", "个人时间", "自己轻松", "别占用我", "光脚自由")),
    ("平衡共处", ("自动化保障机制", "稳定输出", "不影响家庭成员", "和平共处", "不打扰", "减少摩擦")),
    ("家庭投入", ("可调节", "可监控", "保证稳定和可达成", "反复检查和补救", "家庭标准", "孩子", "老人", "兜底")),
]

VALUE_DEFINITION_RULES = [
    ("替代", ("替代", "完全交给", "彻底删除", "不用再动手", "取代人工", "不用自己做")),
    ("分担 / 保障", ("分担", "保障", "兜底", "少返工", "少操心", "稳定完成", "减轻负担")),
]

DECISION_STYLE_RULES = [
    ("功能驱动", ("参数", "吸力", "越障", "清洁效果", "防缠", "性能", "功能")),
    ("省心驱动", ("省心", "解放双手", "免维护", "不用动手", "托管", "自动")),
    ("表达驱动", ("颜值", "科技感", "设计", "高端", "黑科技", "社交")),
]

TRUST_BOUNDARY_RULES = [
    ("接受 80%", ("80%", "够用", "可以接受", "还行", "差不多")),
    ("要求稳定托管", ("稳定", "托管", "无感", "不用我管", "放心", "别让我救")),
    ("对维护/细节高度敏感", ("维护", "水渍", "边角", "细节", "异味", "打理", "洁癖")),
]

IDEA_CLUSTER_RULES = {
    "顽固污渍": ("污渍", "蒸汽", "刮片"),
    "地毯": ("地毯", "拍打", "卷边"),
    "低介入": ("自动", "不用我", "不想自己"),
    "生态联动": ("联动", "灯", "油烟机", "空气净化"),
    "宠物应急": ("宠物", "呕吐", "排泄物", "猫砂"),
    "窄缝与门后": ("窄缝", "门后", "滑轨"),
    "机械臂/立面拓展": ("机械臂", "立面", "拿起来"),
}

THEME_EXPLANATIONS = {
    "清洁效果与水痕污渍": "这不是单点拖地问题，而是材质、污渍类型和区域一起作用，最后伤害的是清洁结果信任。",
    "边角与覆盖率": "表面上看是边角问题，实际上更伤的是工作完成率与是否还要人工补扫。",
    "避障越障与卡困": "这类问题真正伤害的不是一次失败，而是用户对“离家也能放心跑”的托管信任。",
    "噪音体验": "噪音会把机器从“能用”拉回“只能挑时间用”，直接压缩可用时窗。",
    "维护与基站操作": "维护问题会把“解放双手”的承诺打回原形，用户会重新觉得自己在伺候机器。",
    "智能/App/语音/地图": "地图、路径和交互问题会放大用户对机器“聪不聪明、值不值得信任”的判断。",
    "多机协同与统一控制": "这类问题更像高价值但低渗透需求，当前更适合看成方向型机会而不是规模型共识。",
}

PAIN_THEME_RULES = [
    ("清洁效果与水痕污渍", ("水渍", "水痕", "油污", "污渍", "拖地", "顽固污渍", "不干净")),
    ("边角与覆盖率", ("边角", "覆盖", "门后", "缝隙", "踢脚线", "漏扫", "漏拖")),
    ("避障越障与卡困", ("避障", "越障", "台阶", "门槛", "卡困", "卡住", "脱困")),
    ("噪音体验", ("噪音", "异音", "打扰", "噪声")),
    ("维护与基站操作", ("维护", "基站", "脏手", "发臭", "异味", "清理", "清洗", "烘干", "尘袋", "拖布")),
    ("智能/App/语音/地图", ("智能", "地图", "路径", "语音", "app", "感知", "主动", "自己知道")),
]

PPT_CONCEPT_SCHEMA = {
    "X": {
        "positioning_triptych": {
            "清洁帮手": {
                "definition": "工具属性，强调完成度、稳定性和少添乱。",
                "attribute_type": "工具属性",
                "required_slots": [
                    "representative_persona",
                    "cleaning_attitude_and_habit",
                    "purchase_style",
                    "pain_points",
                    "expected_needs",
                    "core_demand",
                    "jtbd",
                    "product_todo",
                ],
            },
            "清洁管家": {
                "definition": "服务属性，强调主动感知、托管、确定的洁净感。",
                "attribute_type": "服务属性",
                "required_slots": [
                    "representative_persona",
                    "cleaning_attitude_and_habit",
                    "purchase_style",
                    "pain_points",
                    "expected_needs",
                    "core_demand",
                    "jtbd",
                    "product_todo",
                ],
            },
            "社交名片": {
                "definition": "符号属性，强调科技感、审美表达、社交谈资和溢价。",
                "attribute_type": "符号属性",
                "required_slots": [
                    "representative_persona",
                    "cleaning_attitude_and_habit",
                    "purchase_style",
                    "pain_points",
                    "expected_needs",
                    "core_demand",
                    "jtbd",
                    "product_todo",
                ],
            },
        }
    },
    "T": {
        "people_slices": ["他们是谁", "她们是谁"],
        "difference_dimensions": ["生命阶段与角色冲突", "自我认同与思维模式", "家庭结构与权力动态"],
        "value_definition": ["替代", "分担 / 保障"],
        "jtbd_triptych": ["个人优先", "平衡共处", "家庭投入"],
        "required_sections": ["当下痛点和需求", "系列化策略差异"],
    },
    "cross_series": {
        "required_sections": ["用户产品洞察", "品牌心智", "用户金点子", "系列差异到策略"]
    },
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    for old in [" ", "\u3000", "-", "_", "/", "（", "）", "(", ")", "【", "】", ":", "：", ".", ",", "?", "？", "、", ";", "；", "`", "'", '"']:
        text = text.replace(old, "")
    return text


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(keyword) in normalized for keyword in keywords)


def top_labels(text_blob: str, rules: list[tuple[str, tuple[str, ...]]], limit: int = 3) -> list[str]:
    scored: list[tuple[str, int]] = []
    for label, keywords in rules:
        score = sum(1 for keyword in keywords if contains_any(text_blob, (keyword,)))
        if score > 0:
            scored.append((label, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [label for label, _ in scored[:limit]]


def guess_difference_reason(archetypes: list[str], hidden_needs: list[str], decision_factors: list[str]) -> str:
    if "表达展示型" in archetypes:
        return "他/她把扫地机当成科技与审美表达的一部分，不只是清洁工具。"
    if "责任平衡型" in archetypes:
        return "他/她需要的不是更炫功能，而是能稳定替自己分担家庭责任。"
    if "托管减负型" in archetypes or "真正托管" in hidden_needs:
        return "他/她真正要的不是功能更多，而是更少介入、更少操心。"
    if "秩序掌控型" in archetypes or "可确认的掌控感" in hidden_needs:
        return "他/她在意的不是参数更强，而是结果可确认、过程可掌控。"
    if "维护便利" in decision_factors:
        return "他/她更容易因为维护负担变化而改变产品判断，而不是因为单一功能卖点。"
    return "同样是清洁问题，不同人会给出不同判断，根因往往在于生活重心、责任结构和对机器的信任边界不同。"


def clean_markdown_text(text: str) -> str:
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text or "")
    cleaned = cleaned.replace("<br>", "\n").replace("<br/>", "\n").replace("&nbsp;", " ").replace("\xa0", " ")
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = cleaned.replace("暂时无法在E-Link文档外展示此内容", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = normalize_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(item.strip())
    return result


def text_matches_any(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    return any(normalize_text(keyword) in normalize_text(text) for keyword in keywords if keyword)


def split_text_units(text: str) -> list[str]:
    cleaned = clean_markdown_text(text)
    units: list[str] = []
    noise_keywords = (
        "入户洞察参与者",
        "入户小组成员",
        "入户行程安排",
        "暂时无法在e-link文档外展示此内容",
        "body",
        "source url",
        "page title",
    )
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if set(line) <= {"|", "-", " "}:
            continue
        if line.count("|") >= 2:
            cells = [re.sub(r"[*`#>-]", "", cell).strip() for cell in line.split("|") if cell.strip(" |-")]
            cells = [cell for cell in cells if cell and cell != "---"]
            if len(cells) >= 2:
                line = " | ".join(cells[:4])
            elif cells:
                line = cells[0]
        line = re.sub(r"\s+", " ", line).strip(" -")
        if text_matches_any(line, noise_keywords):
            continue
        if len(line) >= 2:
            units.append(line)
    return dedupe_preserve_order(units)


def collect_units_from_entries(
    entries: list[dict[str, object]],
    *,
    modules: tuple[str, ...] = (),
    title_keywords: tuple[str, ...] = (),
    content_keywords: tuple[str, ...] = (),
    limit: int = 6,
) -> list[str]:
    selected: list[str] = []
    for entry in entries:
        header = " ".join(
            str(entry.get(key, "") or "")
            for key in ("analysis_module_code", "canonical_section_name_cn", "section_title")
        )
        if text_matches_any(header, ("入户小组成员", "入户洞察参与者", "行程安排", "body")):
            continue
        module_hit = bool(modules) and entry.get("analysis_module_code") in modules
        title_hit = bool(title_keywords) and text_matches_any(header, title_keywords)
        if modules and title_keywords:
            if not (module_hit or title_hit):
                continue
        elif modules and not module_hit:
            continue
        elif title_keywords and not title_hit:
            continue
        units = entry.get("units") or []
        if not units:
            clean_text = str(entry.get("clean_text", "") or "")
            units = [clean_text[:280]] if clean_text else []
        for unit in units:  # type: ignore[assignment]
            candidate = str(unit)
            if content_keywords and not (text_matches_any(candidate, content_keywords) or text_matches_any(header, content_keywords)):
                continue
            selected.append(candidate)
            if len(dedupe_preserve_order(selected)) >= limit:
                return dedupe_preserve_order(selected)[:limit]
    return dedupe_preserve_order(selected)[:limit]


def infer_gender_bucket(case_title: str, external_identity: list[str]) -> str:
    combined = " ".join([case_title] + external_identity)
    if any(keyword in combined for keyword in ("先生", "男性", "爸爸", "丈夫", "老公", "男主人")):
        return "他们是谁"
    if any(keyword in combined for keyword in ("女士", "女性", "妈妈", "妻子", "女主人", "小姐姐")):
        return "她们是谁"
    return "他们是谁"


def extract_case_concept_slots(summary_sections: list[sqlite3.Row]) -> dict[str, object]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in summary_sections:
        record = dict(row)
        case = grouped.setdefault(
            record["summary_case_id"],
            {
                "summary_case_id": record["summary_case_id"],
                "case_title": record["case_title"],
                "study_name": record["study_name"],
                "market_scope": record["batch_market_scope"],
                "period_label": record["period_label"],
                "sections": [],
                "inferred_spu_id": record.get("inferred_spu_id"),
            },
        )
        case["sections"].append(
            {
                "analysis_module_code": record["analysis_module_code"],
                "analysis_module_name_cn": record["analysis_module_name_cn"],
                "canonical_section_name_cn": record["canonical_section_name_cn"],
                "section_title": record["section_title"],
                "section_text": record["section_text"],
            }
        )

    case_slots: list[dict[str, object]] = []

    for case in grouped.values():
        section_entries: list[dict[str, object]] = []
        section_map: dict[str, list[dict[str, object]]] = defaultdict(list)
        module_map: dict[str, list[str]] = defaultdict(list)
        for section in case["sections"]:
            clean_text = clean_markdown_text(section["section_text"])
            entry = {
                **section,
                "clean_text": clean_text,
                "units": split_text_units(clean_text),
            }
            section_entries.append(entry)
            section_map[section["analysis_module_code"]].append(entry)
            if clean_text:
                module_map[section["analysis_module_code"]].append(clean_text)
        full_text = "\n".join(entry["clean_text"] for entry in section_entries if entry.get("clean_text"))
        archetype_text = " ".join(
            [case["case_title"]]
            + collect_units_from_entries(section_entries, modules=("user_profile", "purchase_motivation", "purchase_journey", "usage_feedback"), limit=14)
        )
        home_text = " ".join(collect_units_from_entries(section_entries, modules=("user_profile", "home_environment", "open_discussion"), limit=20))
        attitude_text = " ".join(collect_units_from_entries(section_entries, modules=("usage_feedback", "user_needs", "home_environment", "open_discussion"), limit=20))
        purchase_text = " ".join(collect_units_from_entries(section_entries, modules=("purchase_motivation", "purchase_journey", "purchase_cognition", "open_discussion"), limit=20))
        hidden_text = " ".join(collect_units_from_entries(section_entries, modules=("user_needs", "open_discussion", "usage_feedback", "concept_validation"), limit=20))

        persona_summary_lines = collect_units_from_entries(
            section_entries,
            title_keywords=("一句话总结", "TA印象", "消费者人设", "识别外展示层", "他们是谁", "她们是谁"),
            limit=4,
        )
        external_identity = collect_units_from_entries(
            section_entries,
            title_keywords=("身份与家庭结构", "对外可见的角色", "他们是谁", "她们是谁", "消费者人设", "识别外展示层"),
            limit=6,
        )
        family_and_home = collect_units_from_entries(
            section_entries,
            modules=("home_environment", "user_profile"),
            title_keywords=("走进被访者的家", "房屋情况", "装修背景", "装修风格", "地面材质", "家居空间", "家庭结构", "家与生活"),
            limit=8,
        )
        life_focus = collect_units_from_entries(
            section_entries,
            title_keywords=("生活魔法棒", "典型节奏", "生活状态", "生活评价", "兴趣", "满意", "一句话总结"),
            limit=6,
        )
        cleaning_attitude_slots = dedupe_preserve_order(
            collect_units_from_entries(
                section_entries,
                modules=("home_environment", "usage_feedback"),
                title_keywords=("清洁态度", "使用感受", "地面清洁态度", "态度与习惯"),
                content_keywords=("干净", "省心", "解放双手", "不想自己", "无感", "洁癖", "标准", "不添乱", "托管", "肉眼可见"),
                limit=8,
            )
            + collect_units_from_entries(
                section_entries,
                title_keywords=("地面清洁态度与习惯特征总结", "态度与习惯特征总结", "Problem/Solution"),
                content_keywords=("核心特征", "解放双手", "省心", "不追求极致", "托管", "高容忍度", "无感", "家务"),
                limit=6,
            )
        )[:8]
        cleaning_habit = dedupe_preserve_order(
            collect_units_from_entries(
                section_entries,
                modules=("home_environment", "usage_feedback"),
                title_keywords=("清洁行为", "问题全景图", "使用感受", "使用体验"),
                content_keywords=("每天", "每周", "扫地机", "洗地机", "吸尘器", "手动", "分区", "场景", "频率", "预约"),
                limit=8,
            )
            + collect_units_from_entries(
                section_entries,
                title_keywords=("清洁频率与覆盖范围", "启动方式及习惯", "地面清洁问题全景图", "Problem/Solution"),
                content_keywords=("每天", "每周", "场景", "区域", "扫地机", "预约", "语音", "app", "手动"),
                limit=6,
            )
        )[:8]
        purchase_trigger_lines = collect_units_from_entries(
            section_entries,
            modules=("purchase_motivation",),
            title_keywords=("购买动机", "Motivation", "购买驱动"),
            limit=6,
        )
        purchase_path = collect_units_from_entries(
            section_entries,
            title_keywords=("Path-to-Purch", "购买决策旅程", "AIPL", "购买旅程", "think/feel/do"),
            content_keywords=("京东", "小红书", "抖音", "B站", "门店", "线下", "线上", "比价", "Awareness", "Interest", "Purchase", "Loyalty", "YouTube"),
            limit=6,
        )
        purchase_decision = collect_units_from_entries(
            section_entries,
            modules=("purchase_journey", "purchase_cognition"),
            title_keywords=("决定因素", "品牌认知", "品类认知", "购买旅程"),
            content_keywords=("价格", "售后", "技术", "外观", "清洁", "避障", "品牌", "口碑", "维护", "性价比", "黑科技"),
            limit=6,
        )
        brand_evaluation = collect_units_from_entries(
            section_entries,
            modules=("purchase_journey", "purchase_cognition"),
            title_keywords=("品牌认知", "think/feel/do", "Path-to-Purch", "购买旅程"),
            content_keywords=tuple(BRAND_LABELS + ["品牌", "小米", "大疆", "云鲸", "石头", "追觅", "科沃斯"]),
            limit=10,
        )
        pain_points = collect_units_from_entries(
            section_entries,
            modules=("usage_feedback", "user_needs", "home_environment"),
            title_keywords=("问题总结", "使用感受", "Problem / Solution", "问题全景图"),
            content_keywords=("卡", "困", "噪音", "水渍", "边角", "漏扫", "异味", "维护", "麻烦", "避障", "越障", "不方便", "拖不干净", "拖地", "补救"),
            limit=8,
        )
        expected_needs = collect_units_from_entries(
            section_entries,
            modules=("user_needs", "concept_validation"),
            title_keywords=("用户诉求", "未被言明的需求", "产品利益点探索", "Must Have", "Very Attractive", "Nice to Have", "产品洞察"),
            content_keywords=("希望", "需要", "诉求", "想要", "应该", "最好", "需求", "愿意", "吸引力", "必须有"),
            limit=10,
        )
        concept_ideas = collect_units_from_entries(
            section_entries,
            modules=("concept_validation", "user_needs", "open_discussion"),
            title_keywords=("产品洞察", "产品利益点探索", "用户诉求", "未被言明的需求", "开放讨论"),
            content_keywords=("机械臂", "窄缝", "立面", "联动", "摄像头", "主动", "老人", "宠物", "踢脚线", "多楼层", "湿垃圾", "油污", "低噪", "空气净化", "开门", "关门", "智能"),
            limit=10,
        )
        value_definition_lines = collect_units_from_entries(
            section_entries,
            modules=("purchase_motivation", "purchase_cognition", "user_profile", "home_environment"),
            title_keywords=("购买动机", "品类认知", "一句话总结", "产品洞察"),
            content_keywords=("解放双手", "分担", "保障", "替代", "价值", "光脚", "省心", "不想自己动手", "托管", "证明", "家务"),
            limit=6,
        )

        archetypes = top_labels(archetype_text, ARCHETYPE_RULES, limit=2)
        home_patterns = top_labels(home_text, HOME_PATTERNS, limit=4)
        cleaning_attitudes = top_labels(attitude_text, CLEANING_ATTITUDE_RULES, limit=3)
        triggers = top_labels(purchase_text, PURCHASE_TRIGGER_RULES, limit=3)
        channels = top_labels(purchase_text, CHANNEL_RULES, limit=3)
        decision_factors = top_labels(purchase_text, DECISION_FACTOR_RULES, limit=3)
        hidden_needs = top_labels(hidden_text, HIDDEN_NEED_RULES, limit=3)
        difference_reason = guess_difference_reason(archetypes, hidden_needs, decision_factors)
        x_positioning_candidates = top_labels(" ".join([case["case_title"], full_text, " ".join(persona_summary_lines), " ".join(purchase_decision), " ".join(concept_ideas)]), X_POSITIONING_RULES, limit=3)
        t_jtbd_candidates = top_labels(" ".join([full_text, " ".join(pain_points), " ".join(expected_needs), " ".join(value_definition_lines)]), T_JTBD_RULES, limit=3)
        t_difference_dimensions = top_labels(" ".join([full_text, " ".join(family_and_home), " ".join(life_focus), " ".join(purchase_decision)]), T_DIFFERENCE_DIMENSION_RULES, limit=3)
        value_definition_candidates = top_labels(" ".join(value_definition_lines + expected_needs + pain_points), VALUE_DEFINITION_RULES, limit=2)

        case_slots.append(
            {
                "summary_case_id": case["summary_case_id"],
                "case_title": case["case_title"],
                "study_name": case["study_name"],
                "market_scope": case["market_scope"],
                "period_label": case["period_label"],
                "inferred_spu_id": case.get("inferred_spu_id"),
                "series_code": infer_series_code(case.get("inferred_spu_id"), case["case_title"]),
                "persona_summary": case["case_title"],
                "persona_notes": persona_summary_lines,
                "external_identity": external_identity,
                "family_and_home": family_and_home,
                "life_focus": life_focus,
                "cleaning_attitude": cleaning_attitude_slots,
                "cleaning_habit": cleaning_habit,
                "purchase_trigger": purchase_trigger_lines or triggers,
                "purchase_path": purchase_path,
                "purchase_decision": purchase_decision or decision_factors,
                "brand_evaluation": brand_evaluation,
                "pain_points": pain_points,
                "expected_needs": expected_needs,
                "core_demand": dedupe_preserve_order(hidden_needs + value_definition_candidates)[:4],
                "hidden_needs": hidden_needs,
                "concept_ideas": concept_ideas,
                "value_definition": value_definition_lines,
                "persona_archetype": archetypes,
                "home_life_pattern": home_patterns,
                "cleaning_attitude_labels": cleaning_attitudes,
                "purchase_logic": {
                    "trigger_signals": triggers,
                    "channel_signals": channels,
                    "decision_factors": decision_factors,
                },
                "hidden_need": hidden_needs,
                "difference_reason": difference_reason,
                "x_positioning_candidates": x_positioning_candidates,
                "t_jtbd_candidates": t_jtbd_candidates,
                "t_difference_dimensions": t_difference_dimensions,
                "value_definition_candidates": value_definition_candidates,
                "gender_bucket": infer_gender_bucket(case["case_title"], external_identity),
                "evidence_sections": {
                    "user_profile": "\n".join(module_map.get("user_profile", [])),
                    "home_environment": "\n".join(module_map.get("home_environment", [])),
                    "purchase_motivation": "\n".join(module_map.get("purchase_motivation", [])),
                    "purchase_cognition": "\n".join(module_map.get("purchase_cognition", [])),
                    "purchase_journey": "\n".join(module_map.get("purchase_journey", [])),
                    "usage_feedback": "\n".join(module_map.get("usage_feedback", [])),
                    "user_needs": "\n".join(module_map.get("user_needs", [])),
                    "concept_validation": "\n".join(module_map.get("concept_validation", [])),
                    "open_discussion": "\n".join(module_map.get("open_discussion", [])),
                },
                "source_texts": {
                    "archetype_text": archetype_text,
                    "purchase_text": purchase_text,
                    "hidden_text": hidden_text,
                    "full_text": full_text,
                    "section_titles": " | ".join(str(entry["section_title"]) for entry in section_entries),
                },
            }
        )

    case_slots.sort(key=lambda item: (item["study_name"], item["case_title"]))
    return {"case_count": len(case_slots), "cases": case_slots}


def extract_summary_insight_cards(summary_sections: list[sqlite3.Row]) -> dict[str, object]:
    payload = extract_case_concept_slots(summary_sections)
    case_slots = payload["cases"]  # type: ignore[index]
    cards: list[dict[str, object]] = []
    archetype_counter: Counter[str] = Counter()
    hidden_need_counter: Counter[str] = Counter()

    for case in case_slots:
        for item in case.get("persona_archetype", []):
            archetype_counter[item] += 1
        for item in case.get("hidden_needs", []):
            hidden_need_counter[item] += 1
        cards.append(case)

    return {
        "card_count": len(cards),
        "cards": cards,
        "case_concept_slots": payload,
        "top_archetypes": [[label, count] for label, count in archetype_counter.most_common(6)],
        "top_hidden_needs": [[label, count] for label, count in hidden_need_counter.most_common(6)],
    }


PASSAGE_ROLE_FIELD_MAP = {
    "persona_notes": "人物定义",
    "external_identity": "人物定义",
    "family_and_home": "人物定义",
    "life_focus": "人物定义",
    "cleaning_attitude": "清洁态度",
    "cleaning_habit": "清洁态度",
    "purchase_trigger": "购买决策",
    "purchase_path": "购买决策",
    "purchase_decision": "购买决策",
    "pain_points": "痛点",
    "expected_needs": "期待",
    "core_demand": "隐性需求",
    "hidden_needs": "隐性需求",
    "difference_reason": "差异解释",
    "brand_evaluation": "品牌认知",
    "concept_ideas": "金点子",
    "value_definition": "隐性需求",
}

GENERIC_PREFIXES = {
    "一句话",
    "满意点",
    "抱怨点",
    "当前状态",
    "用户诉求期待",
    "智能提升",
    "代表用户卡片",
    "品牌认知",
    "购买决策",
    "购买路径",
    "购买驱动",
    "使用频率总结",
    "问题总结",
    "住房类型",
    "装修细节",
    "房屋性质",
    "房屋情况",
    "项目",
    "维度",
    "功能",
    "主题",
}


def normalize_passage_text(text: str) -> str:
    cleaned = clean_markdown_text(text).replace("|", " / ")
    cleaned = re.sub(r"[*`#_]+", "", cleaned)
    cleaned = re.sub(r"^[\-\s]+", "", cleaned).strip()
    for _ in range(2):
        match = re.match(r"^(?:\d+[、.)]?\s*)?([^：:]{0,18})[：:]\s*(.+)$", cleaned)
        if not match:
            break
        prefix = normalize_text(match.group(1))
        suffix = match.group(2).strip()
        if suffix and (prefix in GENERIC_PREFIXES or len(prefix) <= 8):
            cleaned = suffix
            continue
        break
    cleaned = re.sub(r"^(?:\d+[、.)]\s*)+", "", cleaned).strip(" -/;；:：")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    if len(normalize_text(cleaned)) < 8:
        return ""
    if text_matches_any(
        cleaned,
        (
            "入户洞察参与者",
            "入户小组成员",
            "入户行程安排",
            "暂时无法在e-link文档外展示此内容",
            "source url",
            "page title",
            "exported at",
        ),
    ):
        return ""
    if cleaned.endswith(("：", ":")):
        return ""
    return cleaned


def score_passage_quality(text: str, role: str) -> float:
    if not text:
        return 0.0
    score = 0.2
    normalized_len = len(normalize_text(text))
    score += min(normalized_len / 60, 1.0) * 0.35
    if re.search(r"[，。；！？]", text):
        score += 0.15
    if text_matches_any(text, ("认为", "希望", "需要", "期待", "担心", "愿意", "不想", "核心", "真正", "本质", "意味着")):
        score += 0.15
    if role in {"痛点", "期待", "差异解释", "品牌认知"}:
        score += 0.1
    if text.count("/") >= 3 and not re.search(r"[。；！？]", text):
        score -= 0.2
    if len(text) <= 10:
        score -= 0.2
    return round(max(0.0, min(score, 1.0)), 3)


def build_passage_tags(text: str) -> list[str]:
    tags: list[str] = []
    for rules in (
        ARCHETYPE_RULES,
        HIDDEN_NEED_RULES,
        X_POSITIONING_RULES,
        T_JTBD_RULES,
        T_DIFFERENCE_DIMENSION_RULES,
        DECISION_FACTOR_RULES,
    ):
        tags.extend(top_labels(text, rules, limit=2))
    for brand in BRAND_LABELS:
        if brand in text:
            tags.append(brand)
    if text_matches_any(text, ("智能", "路径", "避障", "越障", "语音", "污渍识别")):
        tags.append("智能性")
    return dedupe_preserve_order(tags)[:6]


def build_semantic_passages(case_concept_slots: dict[str, object]) -> dict[str, object]:
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    case_payloads: list[dict[str, object]] = []
    passages: list[dict[str, object]] = []
    for case in cases:
        case_passages: list[dict[str, object]] = []
        for field_name, role in PASSAGE_ROLE_FIELD_MAP.items():
            raw_value = case.get(field_name)
            raw_items: list[str] = []
            if isinstance(raw_value, list):
                raw_items = [str(item) for item in raw_value]
            elif isinstance(raw_value, str):
                raw_items = [raw_value]
            else:
                continue
            for raw_item in raw_items:
                passage_text = normalize_passage_text(raw_item)
                if not passage_text:
                    continue
                quality = score_passage_quality(passage_text, role)
                if quality < 0.4:
                    continue
                passage_id = f"{case['summary_case_id']}_{len(case_passages) + 1:03d}"
                passage = {
                    "passage_id": passage_id,
                    "summary_case_id": case["summary_case_id"],
                    "case_title": case["case_title"],
                    "series_code": case.get("series_code"),
                    "source_section": field_name,
                    "passage_role": role,
                    "passage_text": passage_text,
                    "quality_score": quality,
                    "passage_tags": build_passage_tags(passage_text),
                }
                case_passages.append(passage)
                passages.append(passage)
        case_passages.sort(key=lambda item: (-float(item["quality_score"]), item["passage_role"], item["passage_text"]))
        case_payloads.append(
            {
                "summary_case_id": case["summary_case_id"],
                "case_title": case["case_title"],
                "passage_ids": [item["passage_id"] for item in case_passages],
                "top_passages": case_passages[:12],
            }
        )
    passages.sort(key=lambda item: (item["case_title"], -float(item["quality_score"]), item["passage_role"]))
    return {
        "case_count": len(case_payloads),
        "passage_count": len(passages),
        "cases": case_payloads,
        "passages": passages,
    }


def pick_passages(
    semantic_passages: dict[str, object],
    *,
    case_titles: list[str] | None = None,
    roles: list[str] | None = None,
    keywords: list[str] | None = None,
    limit: int = 3,
) -> list[dict[str, object]]:
    case_set = set(case_titles or [])
    role_set = set(roles or [])
    result: list[dict[str, object]] = []
    for passage in semantic_passages.get("passages", []):  # type: ignore[index]
        if case_set and passage["case_title"] not in case_set:
            continue
        if role_set and passage["passage_role"] not in role_set:
            continue
        if keywords and not any(text_matches_any(passage["passage_text"], [keyword]) for keyword in keywords):
            continue
        result.append(passage)
    result.sort(key=lambda item: (-float(item["quality_score"]), item["case_title"], item["passage_role"]))
    unique: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in result:
        key = normalize_text(item["passage_text"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def parse_area_bucket(answer_text: str) -> str | None:
    matches = re.findall(r"(\d+)", answer_text)
    if not matches:
        return None
    first_value = int(matches[0])
    if first_value <= 90:
        return "小户型"
    if first_value >= 120:
        return "大户型"
    return "中户型"


def pick_question_ids(conn: sqlite3.Connection, wave_id: str, keywords: tuple[str, ...]) -> list[str]:
    rows = conn.execute(
        """
        SELECT question_id, question_text
        FROM question_catalog
        WHERE wave_id = ?
          AND field_type != 'system'
        """,
        (wave_id,),
    ).fetchall()
    matched = [row["question_id"] for row in rows if any(normalize_text(keyword) in normalize_text(row["question_text"]) for keyword in keywords)]
    return matched


def fetch_wave_answer_map(conn: sqlite3.Connection, wave_id: str) -> dict[str, dict[str, list[str]]]:
    rows = conn.execute(
        """
        SELECT
            al.response_identity_id,
            qc.question_text,
            al.answer_text
        FROM answer_long al
        JOIN question_catalog qc
            ON al.question_id = qc.question_id
        WHERE qc.wave_id = ?
          AND qc.field_type != 'system'
          AND al.answer_text IS NOT NULL
          AND trim(al.answer_text) != ''
        """,
        (wave_id,),
    ).fetchall()
    result: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        result[row["response_identity_id"]][row["question_text"]].append(row["answer_text"])
    return result


def classify_segment_members(answer_map: dict[str, dict[str, list[str]]]) -> dict[str, set[str]]:
    segments: dict[str, set[str]] = defaultdict(set)

    def values_for_question(answers: dict[str, list[str]], keywords: tuple[str, ...]) -> list[str]:
        result: list[str] = []
        for question_text, values in answers.items():
            if contains_any(question_text, keywords):
                result.extend(values)
        return result

    for response_id, answers in answer_map.items():
        prev_use_values = values_for_question(answers, ("购买", "之前", "使用过扫地机"))
        family_values = values_for_question(answers, ("家庭和生活状态", "几口人共同居住"))
        pet_values = values_for_question(answers, ("宠物", "猫猫或狗狗", "带毛宠物"))
        carpet_values = values_for_question(answers, ("地毯", "地垫"))
        area_values = values_for_question(answers, ("家庭面积", "居住的家庭面积", "使用扫地机的家庭面积"))
        water_values = values_for_question(answers, ("未选择购买上下水基站的原因", "无法放在预期位置", "期望的上下水基站"))

        prev_use_text = " ".join(prev_use_values)
        family_text = " ".join(family_values)
        pet_text = " ".join(pet_values)
        carpet_text = " ".join(carpet_values)
        area_text = " ".join(area_values)
        water_text = " ".join(water_values)

        if contains_any(prev_use_text, ("未使用过",)):
            segments["首购"].add(response_id)
        elif contains_any(prev_use_text, ("使用过", "搭配", "弃用")):
            segments["非首购"].add(response_id)
        if contains_any(family_text, ("有娃", "孩子", "宝宝", "三口", "四口")):
            segments["有娃"].add(response_id)
        if contains_any(pet_text, ("没有养宠物", "无宠物", "没有养")):
            segments["不养宠"].add(response_id)
        elif contains_any(pet_text, ("宠物", "猫", "狗")):
            segments["养宠"].add(response_id)
        if contains_any(carpet_text, ("没有任何地毯", "没有地毯", "没有地垫")):
            segments["无地毯"].add(response_id)
        elif contains_any(carpet_text, ("地毯", "地垫")):
            segments["有地毯"].add(response_id)
        if contains_any(water_text, ("没有合适的安装位置", "未预留水源", "无法放在预期位置")):
            segments["上下水不可装"].add(response_id)
        if contains_any(water_text, ("有合适的安装位置", "期望的上下水基站")):
            segments["上下水可装"].add(response_id)
        area_bucket = parse_area_bucket(area_text)
        if area_bucket:
            segments[area_bucket].add(response_id)
    return segments


def classify_concept_segment_members(answer_map: dict[str, dict[str, list[str]]]) -> dict[str, set[str]]:
    profiles = build_response_concept_profiles(answer_map)
    segments: dict[str, set[str]] = defaultdict(set)
    for response_id, profile in profiles.items():
        decision_style = profile.get("decision_style")
        trust_boundary = profile.get("trust_boundary")
        if decision_style:
            segments[str(decision_style)].add(response_id)
        if trust_boundary:
            segments[str(trust_boundary)].add(response_id)
    return segments


def build_response_concept_profiles(answer_map: dict[str, dict[str, list[str]]]) -> dict[str, dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}

    def choose_segment(score_map: dict[str, int], minimum_score: int) -> tuple[str | None, dict[str, int]]:
        ranked = sorted(score_map.items(), key=lambda item: (-item[1], item[0]))
        if not ranked or ranked[0][1] < minimum_score:
            return None, score_map
        if len(ranked) == 1:
            return ranked[0][0], score_map
        if ranked[0][1] == ranked[1][1]:
            return None, score_map
        if ranked[0][1] < int(ranked[1][1] * 1.15):
            return None, score_map
        return ranked[0][0], score_map

    for response_id, answers in answer_map.items():
        decision_scores = {label: 0 for label, _ in DECISION_STYLE_RULES}
        trust_scores = {label: 0 for label, _ in TRUST_BOUNDARY_RULES}

        for question_text, values in answers.items():
            answer_text = " ".join(values)
            qa_text = f"{question_text} {answer_text}"
            if contains_any(question_text, ("购买扫地机的动机", "最能打动", "进一步了解", "有印象的产品", "产品功能卖点")):
                if text_matches_any(answer_text, ("没有足够的时间做家务", "不想不喜欢做家务", "代替我", "帮我", "体力做家务", "解放双手")):
                    decision_scores["省心驱动"] += 5
                if text_matches_any(answer_text, ("恒压活水洗地", "超充", "BLAST", "越障", "吸力", "清洁", "滚刷", "顽固污渍", "毛发细尘")):
                    decision_scores["功能驱动"] += 5
                if text_matches_any(answer_text, ("尝试新的技术", "生活更智能", "小科智能体", "新生活方式", "讨论相关话题", "新的技术")):
                    decision_scores["表达驱动"] += 4
                if text_matches_any(answer_text, ("全能基站", "双仓双清洁液", "智能切换", "基站")):
                    decision_scores["省心驱动"] += 4

            if contains_any(question_text, ("满意度", "问题", "困扰", "地面水渍", "维护", "地图", "避障", "越障", "运行噪音", "集尘", "洗拖布", "烘干")):
                if text_matches_any(answer_text, ("满意", "非常满意", "运行流畅", "一次性能完成全屋清洁", "满足我的需求", "清洁效果好")):
                    trust_scores["要求稳定托管"] += 3
                if text_matches_any(answer_text, ("一般", "可接受", "基本满意", "没注意过", "不需要", "时间短可以接受", "够日常维护使用")):
                    trust_scores["接受 80%"] += 3
                if text_matches_any(answer_text, ("边角扫拖不干净", "污渍扫拖不干净", "水渍", "明显痕迹", "缠毛", "脏污", "异味", "噪音高", "失望", "卡住", "过不去", "地图问题", "反复清洗", "烘干时间长", "漏液")):
                    trust_scores["对维护/细节高度敏感"] += 4
                if contains_any(question_text, ("地图", "避障", "越障", "续航")) and text_matches_any(answer_text, ("满意", "运行流畅", "没有什么问题", "一次性能完成全屋清洁")):
                    trust_scores["要求稳定托管"] += 2
                if contains_any(question_text, ("地图", "避障", "越障", "维护", "地面水渍", "清洁覆盖率")) and text_matches_any(answer_text, ("一般", "可接受")):
                    trust_scores["接受 80%"] += 2

            if contains_any(question_text, ("新手引导", "智能语音")):
                if text_matches_any(answer_text, ("清晰", "及时", "回复都有回应", "正确执行")):
                    trust_scores["要求稳定托管"] += 2
                if text_matches_any(answer_text, ("听不懂", "不灵敏", "响应慢", "不清晰")):
                    trust_scores["对维护/细节高度敏感"] += 2

            if qa_text:
                if text_matches_any(qa_text, ("外观", "科技感", "设计", "颜值", "高端")):
                    decision_scores["表达驱动"] += 1
                if text_matches_any(qa_text, ("省心", "自动", "托管", "不用我管", "无感")):
                    decision_scores["省心驱动"] += 1
                if text_matches_any(qa_text, ("边角", "越障", "避障", "清洁", "续航", "水渍")):
                    decision_scores["功能驱动"] += 1

        decision_style, _ = choose_segment(decision_scores, minimum_score=3)
        trust_boundary, _ = choose_segment(trust_scores, minimum_score=3)
        profiles[response_id] = {
            "decision_style": decision_style,
            "trust_boundary": trust_boundary,
            "decision_style_score": decision_scores,
            "trust_boundary_score": trust_scores,
        }
    return profiles


def count_top_negative_tags_for_segment(conn: sqlite3.Connection, wave_id: str, member_ids: set[str], limit: int = 3) -> list[dict[str, object]]:
    if not member_ids:
        return []
    placeholders = ", ".join("?" for _ in member_ids)
    rows = conn.execute(
        f"""
        SELECT
            tn.level_3_name AS tag_name,
            COUNT(DISTINCT rtf.response_identity_id) AS respondent_count
        FROM response_tag_fact rtf
        JOIN tag_node tn
            ON rtf.tag_id = tn.tag_id
        WHERE rtf.wave_id = ?
          AND rtf.response_identity_id IN ({placeholders})
          AND COALESCE(tn.sentiment, '') = '负面'
        GROUP BY tn.level_3_name
        ORDER BY respondent_count DESC, tn.level_3_name
        LIMIT ?
        """,
        (wave_id, *member_ids, limit),
    ).fetchall()
    return [dict(row) for row in rows]


NEGATIVE_QUESTION_KEYWORDS = (
    "主要问题",
    "满意度",
    "困扰",
    "原因",
    "现象",
    "不干净",
    "噪音",
    "卡困",
    "避障",
    "越障",
    "地图",
    "地毯",
)
NEGATIVE_ANSWER_HINTS = (
    "不干净",
    "噪音",
    "异响",
    "过不去",
    "卡困",
    "卡住",
    "漏扫",
    "漏拖",
    "发臭",
    "水渍",
    "水痕",
    "清洗速度慢",
    "缠绕",
    "边角",
    "拖地效果差",
    "清扫效率低",
    "无法",
    "不灵敏",
    "困难",
    "麻烦",
    "费劲",
    "卷地毯",
    "推移地毯",
)
NEGATIVE_ANSWER_EXCLUDES = (
    "非常满意",
    "很满意",
    "满意",
    "基本满意",
    "没有注意过",
    "可接受",
    "流畅",
    "满足",
)


def count_top_problem_answers_for_segment(conn: sqlite3.Connection, wave_id: str, member_ids: set[str], limit: int = 3) -> list[dict[str, object]]:
    if not member_ids:
        return []
    question_ids = pick_question_ids(conn, wave_id, NEGATIVE_QUESTION_KEYWORDS)
    if not question_ids:
        return []
    q_placeholders = ", ".join("?" for _ in question_ids)
    member_placeholders = ", ".join("?" for _ in member_ids)
    rows = conn.execute(
        f"""
        SELECT answer_text, COUNT(DISTINCT response_identity_id) AS respondent_count
        FROM answer_long
        WHERE question_id IN ({q_placeholders})
          AND response_identity_id IN ({member_placeholders})
          AND answer_text IS NOT NULL
          AND trim(answer_text) != ''
        GROUP BY answer_text
        ORDER BY respondent_count DESC, answer_text
        """,
        (*question_ids, *member_ids),
    ).fetchall()
    candidates: list[dict[str, object]] = []
    for row in rows:
        answer_text = row["answer_text"]
        if any(exclude in answer_text for exclude in NEGATIVE_ANSWER_EXCLUDES):
            continue
        if not any(hint in answer_text for hint in NEGATIVE_ANSWER_HINTS):
            continue
        candidates.append({"tag_name": answer_text, "respondent_count": row["respondent_count"]})
        if len(candidates) >= limit:
            break
    return candidates


def count_top_motivations_for_segment(conn: sqlite3.Connection, wave_id: str, member_ids: set[str], limit: int = 3) -> list[dict[str, object]]:
    if not member_ids:
        return []
    question_ids = pick_question_ids(conn, wave_id, ("购买动机", "最能打动", "吸引力", "最看重", "进一步了解"))
    if not question_ids:
        return []
    q_placeholders = ", ".join("?" for _ in question_ids)
    member_placeholders = ", ".join("?" for _ in member_ids)
    rows = conn.execute(
        f"""
        SELECT ao.option_value AS answer_text, COUNT(DISTINCT al.response_identity_id) AS respondent_count
        FROM answer_option_long ao
        JOIN answer_long al
            ON ao.answer_id = al.answer_id
        WHERE al.question_id IN ({q_placeholders})
          AND al.response_identity_id IN ({member_placeholders})
        GROUP BY ao.option_value
        ORDER BY respondent_count DESC, ao.option_value
        LIMIT ?
        """,
        (*question_ids, *member_ids, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def compare_segment_vs_rest(
    conn: sqlite3.Connection,
    wave_id: str,
    segment_name: str,
    member_ids: set[str],
    all_ids: set[str],
) -> list[str]:
    other_ids = all_ids - member_ids
    if not member_ids or not other_ids:
        return []

    def problem_share(target_ids: set[str]) -> dict[str, float]:
        top_tags = count_top_problem_answers_for_segment(conn, wave_id, target_ids, limit=5)
        if not top_tags:
            top_tags = count_top_negative_tags_for_segment(conn, wave_id, target_ids, limit=5)
        return {row["tag_name"]: row["respondent_count"] / len(target_ids) for row in top_tags if target_ids}

    def motivation_share(target_ids: set[str]) -> dict[str, float]:
        top_answers = count_top_motivations_for_segment(conn, wave_id, target_ids, limit=5)
        return {row["answer_text"]: row["respondent_count"] / len(target_ids) for row in top_answers if target_ids}

    segment_problem_share = problem_share(member_ids)
    other_problem_share = problem_share(other_ids)
    segment_motivation_share = motivation_share(member_ids)
    other_motivation_share = motivation_share(other_ids)

    differences: list[tuple[str, float, str]] = []
    for key, value in segment_problem_share.items():
        delta = value - other_problem_share.get(key, 0.0)
        differences.append((f"问题 `{key}`", delta, "problem"))
    for key, value in segment_motivation_share.items():
        delta = value - other_motivation_share.get(key, 0.0)
        differences.append((f"动机 `{key}`", delta, "motivation"))
    differences.sort(key=lambda item: abs(item[1]), reverse=True)
    lines: list[str] = []
    for label, delta, _ in differences[:3]:
        direction = "更高" if delta > 0 else "更低"
        lines.append(f"{segment_name} 对 {label} 的集中度{direction}，差值约 {delta * 100:+.1f}pp。")
    return lines


def build_profile_summary(segment_name: str, member_ids: set[str], sample_count: int) -> str:
    return f"{segment_name} 当前样本量 {sample_count}，这不是总人群平均值，而是一类更有共同判断逻辑的人。"


def build_survey_segment_comparison(conn: sqlite3.Connection, survey_rows: list[dict[str, object]]) -> dict[str, object]:
    segment_cards: list[dict[str, object]] = []
    for wave in survey_rows:
        wave_id = wave["wave_id"]
        answer_map = fetch_wave_answer_map(conn, wave_id)
        segments = classify_segment_members(answer_map)
        all_ids = set(answer_map.keys())
        for segment_name in ["首购", "非首购", "有娃", "养宠", "有地毯", "无地毯", "大户型", "小户型", "上下水可装", "上下水不可装"]:
            member_ids = segments.get(segment_name, set())
            if len(member_ids) < 30:
                continue
            segment_cards.append(
                {
                    "wave_name": wave["wave_name"],
                    "inferred_spu_id": wave.get("inferred_spu_id"),
                    "segment_name": segment_name,
                    "sample_count": len(member_ids),
                    "profile_summary": build_profile_summary(segment_name, member_ids, len(member_ids)),
                    "top_problems": count_top_problem_answers_for_segment(conn, wave_id, member_ids) or count_top_negative_tags_for_segment(conn, wave_id, member_ids),
                    "top_motivations": count_top_motivations_for_segment(conn, wave_id, member_ids),
                    "difference_lines": compare_segment_vs_rest(conn, wave_id, segment_name, member_ids, all_ids),
                }
            )
    segment_cards.sort(key=lambda item: (item["wave_name"], -item["sample_count"], item["segment_name"]))
    return {"segment_count": len(segment_cards), "segments": segment_cards}


def build_survey_concept_segments(conn: sqlite3.Connection, survey_rows: list[dict[str, object]]) -> dict[str, object]:
    segment_cards: list[dict[str, object]] = []
    for wave in survey_rows:
        wave_id = wave["wave_id"]
        answer_map = fetch_wave_answer_map(conn, wave_id)
        concept_profiles = build_response_concept_profiles(answer_map)
        concept_segments = classify_concept_segment_members(answer_map)
        all_ids = set(answer_map.keys())
        for segment_name in [
            "功能驱动",
            "省心驱动",
            "表达驱动",
            "接受 80%",
            "要求稳定托管",
            "对维护/细节高度敏感",
        ]:
            member_ids = concept_segments.get(segment_name, set())
            if len(member_ids) < 15:
                continue
            segment_share = len(member_ids) / len(all_ids) if all_ids else 0.0
            if segment_share >= 0.8 or segment_share <= 0.05:
                continue
            top_problems = count_top_problem_answers_for_segment(conn, wave_id, member_ids) or count_top_negative_tags_for_segment(conn, wave_id, member_ids)
            top_motivations = count_top_motivations_for_segment(conn, wave_id, member_ids)
            difference_lines = compare_segment_vs_rest(conn, wave_id, segment_name, member_ids, all_ids)
            if not top_problems and not top_motivations:
                continue
            if not difference_lines and segment_share > 0.55:
                continue
            decision_scores = []
            trust_scores = []
            for response_id in member_ids:
                profile = concept_profiles.get(response_id, {})
                if segment_name in {label for label, _ in DECISION_STYLE_RULES}:
                    decision_scores.append(profile.get("decision_style_score", {}).get(segment_name, 0))
                else:
                    trust_scores.append(profile.get("trust_boundary_score", {}).get(segment_name, 0))
            segment_cards.append(
                {
                    "wave_name": wave["wave_name"],
                    "inferred_spu_id": wave.get("inferred_spu_id"),
                    "segment_name": segment_name,
                    "sample_count": len(member_ids),
                    "sample_share": round(segment_share, 4),
                    "segment_summary": build_profile_summary(segment_name, member_ids, len(member_ids)),
                    "top_problems": top_problems,
                    "top_motivations": top_motivations,
                    "pain_tolerance_gap": [row["tag_name"] for row in top_problems[:3]],
                    "buying_logic_gap": [row["answer_text"] for row in top_motivations[:3]],
                    "difference_reason": difference_lines[:3],
                    "decision_style_score": round(sum(decision_scores) / len(decision_scores), 2) if decision_scores else 0.0,
                    "trust_boundary_score": round(sum(trust_scores) / len(trust_scores), 2) if trust_scores else 0.0,
                }
            )
    segment_cards.sort(key=lambda item: (item["wave_name"], -item["sample_count"], item["segment_name"]))
    return {"segment_count": len(segment_cards), "segments": segment_cards}


def derive_damage_type(negative_tag: str) -> str:
    for label, keywords in DAMAGE_TYPE_RULES:
        if contains_any(negative_tag, keywords):
            return label
    return "体验边界模糊"


def derive_trust_impact(damage_type: str) -> str:
    return TRUST_IMPACT_RULES.get(damage_type, "需要进一步判断其最终伤害的是哪类信任")


def build_package_name(trigger_scene: str, negative_tag: str, damage_type: str) -> str:
    if trigger_scene and trigger_scene != "-":
        return f"{trigger_scene}{negative_tag}问题包"
    return f"{damage_type}：{negative_tag}"


def build_voc_problem_packages(
    conn: sqlite3.Connection,
    selected_spu_ids: list[str],
    competition_generation_registry: dict[str, object] | None = None,
    truth_conn: sqlite3.Connection | None = None,
) -> dict[str, object]:
    if not selected_spu_ids:
        return {"package_count": 0, "packages": []}
    conn.row_factory = sqlite3.Row
    placeholders = ", ".join("?" for _ in selected_spu_ids)
    negative_rows = conn.execute(
        f"""
        SELECT canonical_spu_id, tag_name AS negative_tag, COUNT(DISTINCT message_uid) AS message_count
        FROM vw_voc_message_tag_mapped
        WHERE canonical_spu_id IN ({placeholders})
          AND tag_sentiment = '负面'
        GROUP BY canonical_spu_id, tag_name
        ORDER BY canonical_spu_id, message_count DESC, tag_name
        """,
        selected_spu_ids,
    ).fetchall()
    grouped_negatives: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in negative_rows:
        grouped_negatives[row["canonical_spu_id"]].append(row)

    has_voc_message_table = bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='voc_message' LIMIT 1"
        ).fetchone()
    )
    product_totals: dict[str, int] = {}
    market_lookup: dict[str, str] = {}
    if has_voc_message_table:
        total_rows = conn.execute(
            f"""
            SELECT canonical_spu_id, COUNT(DISTINCT message_uid) AS total_messages
            FROM voc_message
            WHERE canonical_spu_id IN ({placeholders})
            GROUP BY canonical_spu_id
            """,
            selected_spu_ids,
        ).fetchall()
        product_totals = {
            str(row["canonical_spu_id"]): int(row["total_messages"] or 0)
            for row in total_rows
        }
        market_rows = conn.execute(
            f"""
            SELECT
                canonical_spu_id,
                country,
                site_country,
                ecommerce_region,
                platform,
                COUNT(DISTINCT message_uid) AS message_count
            FROM voc_message
            WHERE canonical_spu_id IN ({placeholders})
            GROUP BY canonical_spu_id, country, site_country, ecommerce_region, platform
            ORDER BY canonical_spu_id, message_count DESC
            """,
            selected_spu_ids,
        ).fetchall()
        for row in market_rows:
            spu_id = str(row["canonical_spu_id"])
            if spu_id in market_lookup:
                continue
            market_lookup[spu_id] = normalize_voc_market_scope(
                row["country"],
                row["site_country"],
                row["ecommerce_region"],
                row["platform"],
            )

    registry_index = build_competition_registry_index(competition_generation_registry or {})
    packages: list[dict[str, object]] = []
    for spu_id, rows in grouped_negatives.items():
        total_messages = product_totals.get(spu_id, 0)
        registry_entry = infer_registry_entry_for_spu(spu_id, registry_index)
        for row in rows[:5]:
            negative_tag = row["negative_tag"]
            related_rows = conn.execute(
                f"""
                WITH neg AS (
                    SELECT message_uid
                    FROM vw_voc_message_tag_mapped
                    WHERE canonical_spu_id = ?
                      AND tag_sentiment = '负面'
                      AND tag_name = ?
                )
                SELECT
                    COALESCE(context_bucket_name_cn, topic_domain_name_cn, '') AS bucket_name,
                    COALESCE(topic_group_name_cn, '') AS topic_group_name_cn,
                    tag_name,
                    COUNT(DISTINCT mapped.message_uid) AS message_count
                FROM vw_voc_message_tag_mapped mapped
                JOIN neg
                    ON mapped.message_uid = neg.message_uid
                WHERE mapped.tag_name != ?
                GROUP BY bucket_name, topic_group_name_cn, tag_name
                ORDER BY message_count DESC, tag_name
                LIMIT 12
                """,
                (spu_id, negative_tag, negative_tag),
            ).fetchall()

            trigger_scene = "-"
            working_condition = "-"
            related_items = "-"
            for related in related_rows:
                bucket_name = related["bucket_name"] or ""
                tag_name = related["tag_name"]
                topic_group_name = related["topic_group_name_cn"] or ""
                if trigger_scene == "-" and any(token in bucket_name for token in ("场景", "空间")):
                    trigger_scene = tag_name
                if (working_condition == "-" and any(token in bucket_name for token in ("工况",))) or any(token in topic_group_name for token in ("污渍", "毛发", "灰尘")):
                    working_condition = tag_name
                if related_items == "-" and any(token in bucket_name for token in ("关联物品", "用户指标")):
                    related_items = tag_name

            damage_type = derive_damage_type(negative_tag)
            problem_level_1 = classify_problem_level_1(negative_tag, damage_type, related_items, trigger_scene)
            problem_level_2 = classify_problem_level_2(negative_tag, damage_type, related_items, trigger_scene, working_condition)
            message_count = int(row["message_count"] or 0)
            packages.append(
                {
                    "spu_id": spu_id,
                    "negative_tag": negative_tag,
                    "package_name": build_package_name(trigger_scene, negative_tag, damage_type),
                    "trigger_scene": trigger_scene,
                    "working_condition": working_condition,
                    "related_items": related_items,
                    "damage_type": damage_type,
                    "trust_impact": derive_trust_impact(damage_type),
                    "message_count": message_count,
                    "message_share": round(message_count / total_messages, 4) if total_messages else 0.0,
                    "series_family": infer_series_code(spu_id, negative_tag),
                    "competition_scope": infer_competition_scope_from_registry_entry(registry_entry) or infer_default_competition_scope(spu_id, negative_tag),
                    "problem_level_1": problem_level_1,
                    "problem_level_2": problem_level_2,
                    "performance_level": "待比较",
                    "best_competitor_spu_id": "",
                    "best_competitor_name": "",
                    "market_scope": market_lookup.get(spu_id, "unknown"),
                }
            )

    packages.sort(key=lambda item: (item["spu_id"], -int(item["message_count"]), item["negative_tag"]))
    return {"package_count": len(packages), "packages": packages}


def normalize_voc_market_scope(
    country: object | None,
    site_country: object | None,
    ecommerce_region: object | None,
    platform: object | None,
) -> str:
    text = " ".join(str(value or "") for value in [country, site_country, ecommerce_region, platform])
    normalized = normalize_text(text)
    if any(token in normalized for token in ("中国", "cn", "国内电商", "京东", "天猫", "淘宝", "抖音小店")):
        return "中国"
    if any(
        token in normalized
        for token in (
            "美国",
            "德国",
            "法国",
            "意大利",
            "西班牙",
            "英国",
            "韩国",
            "日本",
            "澳大利亚",
            "新加坡",
            "海外电商",
            "亚马逊国际",
            "coupang",
            "naver",
            "rakuten",
            "bestbuy",
            "lazada",
        )
    ):
        return "海外"
    return "unknown"


def classify_problem_level_1(
    negative_tag: str,
    damage_type: str,
    related_items: str,
    trigger_scene: str,
) -> str:
    blob = normalize_text(" ".join([negative_tag, damage_type, related_items, trigger_scene]))
    if "噪音" in blob or damage_type == "使用时窗受损":
        return "噪音"
    if any(token in blob for token in ("基站", "洗抹布", "集尘", "烘干", "污水箱", "清洁槽", "补水", "尘袋")):
        return "基站"
    if any(token in blob for token in ("避障", "越障", "地图", "路径", "脱困", "台阶", "门槛")) or damage_type == "无人值守失败":
        return "智能性"
    if any(token in blob for token in ("维护", "滚刷", "边刷", "异味", "发臭", "缠绕")) or damage_type == "维护负担上升":
        return "维护"
    if damage_type in {"清洁结果受损", "工作完成率受损"} or any(token in blob for token in ("清洁", "污渍", "边角", "覆盖", "拖地", "水渍", "水痕")):
        return "清洁"
    return "其他"


def classify_problem_level_2(
    negative_tag: str,
    damage_type: str,
    related_items: str,
    trigger_scene: str,
    working_condition: str,
) -> str:
    blob = normalize_text(" ".join([negative_tag, damage_type, related_items, trigger_scene, working_condition]))
    mapping = [
        ("拖地留痕", ("水渍", "水痕", "印迹", "轮子印", "滚筒印")),
        ("边角清洁效果", ("边角", "桌角", "墙角", "踢脚线", "漏扫", "漏拖", "覆盖")),
        ("避障能力", ("避障", "误识别", "碰撞", "绕障")),
        ("越障/卡困", ("越障", "台阶", "门槛", "卡困", "卡住", "脱困", "卷地毯")),
        ("基站自清洁", ("基站", "洗抹布", "集尘", "烘干", "污水箱", "补水", "尘袋", "清洁槽")),
        ("滚刷组件维护", ("滚刷", "边刷", "缠绕", "发臭", "异味", "维护", "清理")),
        ("噪音体验", ("噪音", "异响", "刮地板", "咯吱")),
        ("智能交互/地图", ("地图", "路径", "语音", "app", "建图", "导航")),
    ]
    for label, keywords in mapping:
        if any(keyword in blob for keyword in keywords):
            return label
    if damage_type == "清洁结果受损":
        return "清洁效果"
    if damage_type == "工作完成率受损":
        return "覆盖率/完成率"
    if damage_type == "维护负担上升":
        return "维护负担"
    return negative_tag


COMPETITION_FRONTLINE_SCOPES = ("X_omni", "T_omni", "N_omni", "N_aes", "N_single")
COMPETITION_SCOPE_ALIAS_OVERRIDES = {
    "N_aes": ("N20 Plus", "N20 Pro Plus", "N20E Plus", "摩根AES"),
    "N_single": ("N20", "N20 Pro", "N20e", "摩根单机"),
    "N_omni": ("T50 OMNI", "T50 PRO OMNI", "T50S PRO OMNI", "T50S OMNI", "T30", "N50", "帕斯卡"),
}
CANONICAL_AGGREGATE_HINTS = {
    "our_brand_spun20_4b652c54",
}
MARKET_SCOPE_PRIORITY = {"中国": 0, "ALL": 1, "海外": 2, "unknown": 3}
STABLE_SCOPE_MESSAGE_THRESHOLD = 30


def strip_invisible_tokens(value: str | None) -> str:
    text = value or ""
    for token in ("\u200e", "\u200f", "\ufeff", "\u2060"):
        text = text.replace(token, "")
    return text


def normalize_match_text(value: str | None) -> str:
    return normalize_text(strip_invisible_tokens(value))


def entry_alias_priority(entry: dict[str, object]) -> int:
    priorities = [int(rule.get("priority_order", 999)) for rule in entry.get("alias_rules", []) or []]
    return min(priorities) if priorities else 999


def match_scope_alias_override(raw_model: str, product_title: str) -> dict[str, object] | None:
    candidates: list[dict[str, object]] = []
    for scope, aliases in COMPETITION_SCOPE_ALIAS_OVERRIDES.items():
        for alias_text in aliases:
            alias_rule = {
                "match_value": alias_text,
                "normalized_match_value": normalize_match_text(alias_text),
                "match_type": "contains",
            }
            if alias_rule_matches_text(raw_model, alias_rule):
                candidates.append(
                    {
                        "competition_scope": scope,
                        "matched_alias_value": alias_text,
                        "matched_on": "raw_model",
                        "specificity": len(normalize_match_text(alias_text)),
                    }
                )
            elif not raw_model.strip() and alias_rule_matches_text(product_title, alias_rule):
                candidates.append(
                    {
                        "competition_scope": scope,
                        "matched_alias_value": alias_text,
                        "matched_on": "product_title",
                        "specificity": len(normalize_match_text(alias_text)),
                    }
                )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-int(item["specificity"]), str(item["competition_scope"]), str(item["matched_alias_value"])))
    return candidates[0]


def get_connection_source_path(conn: sqlite3.Connection) -> str:
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except sqlite3.Error:
        return ""
    for row in rows:
        if len(row) >= 3 and str(row[1]) == "main":
            return str(row[2])
    if rows and len(rows[0]) >= 3:
        return str(rows[0][2])
    return ""


def load_spu_alias_rules(path: Path = SPU_ALIAS_RULE_PATH) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    active_rows: list[dict[str, object]] = []
    for row in rows:
        if str(row.get("is_active", "1")) != "1":
            continue
        match_field = str(row.get("match_field", "")).strip().lower()
        if match_field and match_field != "model":
            continue
        match_value = str(row.get("match_value", "")).strip()
        if not match_value:
            continue
        active_rows.append(
            {
                "rule_id": str(row.get("rule_id", "")),
                "spu_id": str(row.get("spu_id", "")),
                "match_field": match_field or "model",
                "match_type": str(row.get("match_type", "contains")).strip().lower(),
                "match_value": match_value,
                "normalized_match_value": normalize_text(match_value),
                "priority_order": int(str(row.get("priority_order", "999") or "999")),
                "is_active": True,
                "notes": str(row.get("notes", "")),
            }
        )
    active_rows.sort(key=lambda item: (int(item["priority_order"]), str(item["spu_id"]), str(item["match_value"])))
    return active_rows


def build_spu_alias_index(alias_rules: list[dict[str, object]]) -> dict[str, object]:
    by_spu: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in alias_rules:
        by_spu[str(row["spu_id"])].append(row)
    return {"rules": alias_rules, "by_spu": dict(by_spu)}


def build_competition_registry_index(competition_generation_registry: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    alias_rules = load_spu_alias_rules()
    entries: list[dict[str, object]] = []
    spu_entry_map: dict[str, dict[str, object]] = {}

    def entry_rank(entry: dict[str, object]) -> tuple[int, int]:
        generation_rank = 0 if str(entry.get("generation_bucket")) == "current" else 1
        self_rank = 0 if bool(entry.get("is_self_brand")) else 1
        return (generation_rank, self_rank)

    for row in competition_generation_registry.get("rows", []) or []:
        for product_name in row.get("product_names", []) or []:
            normalized_alias = normalize_match_text(str(product_name))
            if not normalized_alias:
                continue
            matched_alias_rules: list[dict[str, object]] = []
            for alias_rule in alias_rules:
                alias_value = normalize_match_text(str(alias_rule.get("normalized_match_value", "")))
                if not alias_value:
                    continue
                if len(normalized_alias) <= 4 or len(alias_value) <= 4:
                    if normalized_alias == alias_value:
                        matched_alias_rules.append(alias_rule)
                elif normalized_alias == alias_value or normalized_alias in alias_value or alias_value in normalized_alias:
                    matched_alias_rules.append(alias_rule)
            candidate_spu_ids = dedupe_preserve_order([str(item["spu_id"]) for item in matched_alias_rules if str(item.get("spu_id", ""))])
            entries.append(
                {
                    "normalized_alias": normalized_alias,
                    "display_name": str(product_name),
                    "competition_scope": str(row.get("competition_scope", "")),
                    "series_family": str(row.get("series_family", "")),
                    "generation_bucket": str(row.get("generation_bucket", "")),
                    "is_self_brand": bool(row.get("is_self_brand")),
                    "alias_rules": matched_alias_rules,
                    "candidate_spu_ids": candidate_spu_ids,
                    "alias_priority": min((int(item.get("priority_order", 999)) for item in matched_alias_rules), default=999),
                }
            )
            current_entry = entries[-1]
            for candidate_spu_id in candidate_spu_ids:
                existing = spu_entry_map.get(candidate_spu_id)
                if existing is None or entry_rank(current_entry) < entry_rank(existing):
                    spu_entry_map[candidate_spu_id] = current_entry
    return {
        "entries": entries,
        "spu_alias_rules": alias_rules,
        "spu_alias_index": build_spu_alias_index(alias_rules),
        "spu_entry_map": spu_entry_map,
    }


def infer_registry_entry_for_spu(spu_id: str, registry_index: dict[str, list[dict[str, object]]]) -> dict[str, object] | None:
    normalized_spu = normalize_text(spu_id)
    direct_entry = registry_index.get("spu_entry_map", {}).get(spu_id) or registry_index.get("spu_entry_map", {}).get(normalized_spu)
    if direct_entry:
        return direct_entry
    best_entry: dict[str, object] | None = None
    best_score = -1
    best_len = -1
    for entry in registry_index.get("entries", []):
        candidate_spu_ids = [normalize_match_text(str(item)) for item in entry.get("candidate_spu_ids", [])]
        score = -1
        if normalized_spu and normalized_spu in candidate_spu_ids:
            score = 100
        else:
            alias = str(entry.get("normalized_alias", ""))
            if alias and (alias in normalized_spu or normalized_spu in alias):
                score = 40
        if score > best_score or (score == best_score and len(str(entry.get("normalized_alias", ""))) > best_len):
            best_entry = entry
            best_score = score
            best_len = len(str(entry.get("normalized_alias", "")))
    return best_entry


def infer_competition_scope_from_registry_entry(entry: dict[str, object] | None) -> str:
    if not entry:
        return ""
    return str(entry.get("competition_scope", ""))


def infer_default_competition_scope(spu_id: str | None, text_hint: str = "") -> str:
    series_family = infer_series_code(spu_id, text_hint)
    if series_family == "X":
        return "X_omni"
    if series_family == "T":
        return "T_omni"
    if series_family == "N":
        return "N_omni"
    return "unknown"


def build_competition_voc_xtn_breakdown(
    conn: sqlite3.Connection,
    competition_generation_registry: dict[str, object],
    truth_conn: sqlite3.Connection | None = None,
) -> dict[str, object]:
    conn.row_factory = sqlite3.Row
    has_voc_message = bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='voc_message' LIMIT 1"
        ).fetchone()
    )
    if not has_voc_message:
        return {
            "scope_rows": [],
            "product_rows": [],
            "level_1_rows": [],
            "level_2_rows": [],
            "self_scope_rows": [],
            "external_scope_rows": [],
            "frontline_scope_rows": [],
            "scope_status_rows": [],
            "source_db_path": get_connection_source_path(conn),
            "scope_match_diagnostics": [],
            "low_confidence_match_count": 0,
            "filtered_product_count": 0,
        }

    registry_index = build_competition_registry_index(competition_generation_registry)
    candidate_spu_ids = dedupe_preserve_order(
        [
            str(spu_id)
            for entry in registry_index.get("entries", [])
            for spu_id in entry.get("candidate_spu_ids", []) or []
            if str(spu_id).strip()
        ]
    )
    candidate_raw_models = dedupe_preserve_order(
        [
            str(item).strip()
            for entry in registry_index.get("entries", [])
            for item in [entry.get("display_name", "")]
            + [rule.get("match_value", "") for rule in entry.get("alias_rules", []) or []]
            if str(item).strip()
        ]
    )
    occurrence_candidate_filters: list[str] = []
    negative_candidate_filters: list[str] = []
    candidate_filter_params: list[object] = []
    if candidate_spu_ids:
        occurrence_candidate_filters.append(f"canonical_spu_id IN ({', '.join('?' for _ in candidate_spu_ids)})")
        negative_candidate_filters.append(f"vm.canonical_spu_id IN ({', '.join('?' for _ in candidate_spu_ids)})")
        candidate_filter_params.extend(candidate_spu_ids)
    if candidate_raw_models:
        occurrence_candidate_filters.append(f"COALESCE(raw_model, '') IN ({', '.join('?' for _ in candidate_raw_models)})")
        negative_candidate_filters.append(f"COALESCE(vm.raw_model, '') IN ({', '.join('?' for _ in candidate_raw_models)})")
        candidate_filter_params.extend(candidate_raw_models)
    occurrence_candidate_filter_sql = f"WHERE {' OR '.join(occurrence_candidate_filters)}" if occurrence_candidate_filters else ""
    negative_candidate_filter_sql = f"({' OR '.join(negative_candidate_filters)})" if negative_candidate_filters else "1=1"
    occurrence_rows = conn.execute(
        f"""
        SELECT
            canonical_spu_id,
            COALESCE(raw_model, '') AS raw_model,
            COALESCE(product_title, '') AS product_title,
            COALESCE(product_url, '') AS product_url,
            country,
            site_country,
            ecommerce_region,
            platform,
            COUNT(DISTINCT message_uid) AS message_count
        FROM voc_message
        {occurrence_candidate_filter_sql}
        GROUP BY canonical_spu_id, raw_model, product_title, product_url, country, site_country, ecommerce_region, platform
        """
        ,
        candidate_filter_params,
    ).fetchall()

    matched_occurrence_lookup: dict[tuple[str, str, str, str, str, str, str, str], dict[str, object]] = {}
    product_rows_map: dict[tuple[str, str, str, str], dict[str, object]] = {}
    low_confidence_match_count = 0
    for row in occurrence_rows:
        entry = match_registry_product_entry(row, registry_index)
        if not entry:
            continue
        market_scope = normalize_voc_market_scope(
            row["country"],
            row["site_country"],
            row["ecommerce_region"],
            row["platform"],
        )
        occurrence_key = (
            str(row["canonical_spu_id"] or ""),
            str(row["raw_model"] or ""),
            str(row["product_title"] or ""),
            str(row["product_url"] or ""),
            str(row["country"] or ""),
            str(row["site_country"] or ""),
            str(row["ecommerce_region"] or ""),
            str(row["platform"] or ""),
        )
        matched_occurrence_lookup[occurrence_key] = {
            "competition_scope": entry["competition_scope"],
            "series_family": entry["series_family"],
            "product_name": entry["display_name"],
            "generation_bucket": entry["generation_bucket"],
            "is_self_brand": entry["is_self_brand"],
            "market_scope": market_scope,
            "match_confidence": entry.get("match_confidence", "low"),
            "match_reason": entry.get("match_reason", ""),
            "matched_alias_value": entry.get("matched_alias_value"),
            "matched_alias_priority": entry.get("matched_alias_priority"),
            "used_specific_alias_override": entry.get("used_specific_alias_override", False),
        }
        if entry.get("match_confidence") == "low":
            low_confidence_match_count += 1
        product_key = (
            str(entry["competition_scope"]),
            str(entry["series_family"]),
            str(entry["display_name"]),
            market_scope,
        )
        product_row = product_rows_map.setdefault(
            product_key,
            {
                "competition_scope": entry["competition_scope"],
                "series_family": entry["series_family"],
                "product_name": entry["display_name"],
                "generation_bucket": entry["generation_bucket"],
                "is_self_brand": entry["is_self_brand"],
                "market_scope": market_scope,
                "canonical_spu_ids": [],
                "message_count": 0,
                "match_confidence": entry.get("match_confidence", "low"),
                "match_reason": entry.get("match_reason", ""),
                "low_confidence_match_count": 0,
                "matched_alias_value": entry.get("matched_alias_value"),
                "matched_alias_priority": entry.get("matched_alias_priority"),
                "used_specific_alias_override": entry.get("used_specific_alias_override", False),
            },
        )
        canonical_spu_id = str(row["canonical_spu_id"] or "")
        if canonical_spu_id and canonical_spu_id not in product_row["canonical_spu_ids"]:
            product_row["canonical_spu_ids"].append(canonical_spu_id)
        product_row["message_count"] = int(product_row["message_count"]) + int(row["message_count"] or 0)
        if entry.get("match_confidence") == "low":
            product_row["low_confidence_match_count"] = int(product_row["low_confidence_match_count"]) + 1
        elif entry.get("match_confidence") == "high":
            product_row["match_confidence"] = "high"
            product_row["match_reason"] = entry.get("match_reason", "")
        elif product_row.get("match_confidence") != "high":
            product_row["match_confidence"] = "medium"
            product_row["match_reason"] = entry.get("match_reason", "")

    matched_spu_ids = dedupe_preserve_order(
        [
            canonical_spu_id
            for row in product_rows_map.values()
            for canonical_spu_id in row["canonical_spu_ids"]
        ]
    )
    base_packages = build_voc_problem_packages(conn, matched_spu_ids) if matched_spu_ids else {"packages": []}
    base_package_lookup = {
        (str(row["spu_id"]), str(row["negative_tag"])): row
        for row in base_packages.get("packages", []) or []
    }

    negative_rows = conn.execute(
        f"""
        SELECT
            vm.canonical_spu_id,
            COALESCE(vm.raw_model, '') AS raw_model,
            COALESCE(vm.product_title, '') AS product_title,
            COALESCE(vm.product_url, '') AS product_url,
            vm.country,
            vm.site_country,
            vm.ecommerce_region,
            vm.platform,
            mapped.tag_name AS negative_tag,
            COUNT(DISTINCT mapped.message_uid) AS message_count
        FROM vw_voc_message_tag_mapped mapped
        JOIN voc_message vm
          ON mapped.message_uid = vm.message_uid
        WHERE mapped.tag_sentiment = '负面'
          AND {negative_candidate_filter_sql}
        GROUP BY
            vm.canonical_spu_id,
            vm.raw_model,
            vm.product_title,
            vm.product_url,
            vm.country,
            vm.site_country,
            vm.ecommerce_region,
            vm.platform,
            mapped.tag_name
        """
        ,
        candidate_filter_params,
    ).fetchall()

    level_2_rows_map: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
    filtered_product_count = 0
    for row in negative_rows:
        occurrence_key = (
            str(row["canonical_spu_id"] or ""),
            str(row["raw_model"] or ""),
            str(row["product_title"] or ""),
            str(row["product_url"] or ""),
            str(row["country"] or ""),
            str(row["site_country"] or ""),
            str(row["ecommerce_region"] or ""),
            str(row["platform"] or ""),
        )
        matched = matched_occurrence_lookup.get(occurrence_key)
        if not matched:
            continue
        if matched.get("match_confidence") not in {"high", "medium"}:
            filtered_product_count += 1
            continue
        canonical_spu_id = str(row["canonical_spu_id"] or "")
        negative_tag = str(row["negative_tag"])
        base_package = base_package_lookup.get((canonical_spu_id, negative_tag), {})
        problem_level_1 = str(
            base_package.get("problem_level_1")
            or classify_problem_level_1(
                negative_tag,
                str(base_package.get("damage_type", derive_damage_type(negative_tag))),
                str(base_package.get("related_items", "-")),
                str(base_package.get("trigger_scene", "-")),
            )
        )
        problem_level_2 = str(
            base_package.get("problem_level_2")
            or classify_problem_level_2(
                negative_tag,
                str(base_package.get("damage_type", derive_damage_type(negative_tag))),
                str(base_package.get("related_items", "-")),
                str(base_package.get("trigger_scene", "-")),
                str(base_package.get("working_condition", "-")),
            )
        )
        row_key = (
            str(matched["competition_scope"]),
            str(matched["market_scope"]),
            str(matched["product_name"]),
            problem_level_1,
            problem_level_2,
        )
        item = level_2_rows_map.setdefault(
            row_key,
            {
                "competition_scope": matched["competition_scope"],
                "series_family": matched["series_family"],
                "product_name": matched["product_name"],
                "market_scope": matched["market_scope"],
                "is_self_brand": matched["is_self_brand"],
                "problem_level_1": problem_level_1,
                "problem_level_2": problem_level_2,
                "negative_tags": [],
                "damage_type": str(base_package.get("damage_type", derive_damage_type(negative_tag))),
                "trust_impact": str(base_package.get("trust_impact", derive_trust_impact(derive_damage_type(negative_tag)))),
                "complaint_summaries": [],
                "message_count": 0,
                "canonical_spu_id": canonical_spu_id,
            },
        )
        item["message_count"] = int(item["message_count"]) + int(row["message_count"] or 0)
        if negative_tag not in item["negative_tags"]:
            item["negative_tags"].append(negative_tag)
        complaint_summary = str(base_package.get("package_name") or negative_tag)
        if complaint_summary not in item["complaint_summaries"]:
            item["complaint_summaries"].append(complaint_summary)

    product_total_lookup = {
        (
            str(row["competition_scope"]),
            str(row["market_scope"]),
            str(row["product_name"]),
        ): int(row["message_count"])
        for row in product_rows_map.values()
    }
    grouped_best_lookup: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in level_2_rows_map.values():
        product_total = product_total_lookup.get(
            (str(row["competition_scope"]), str(row["market_scope"]), str(row["product_name"])),
            0,
        )
        row["message_share"] = round(int(row["message_count"]) / product_total, 4) if product_total else 0.0
        best_key = (
            str(row["competition_scope"]),
            str(row["market_scope"]),
            str(row["problem_level_2"]),
        )
        if row.get("is_self_brand") or product_total < 50:
            continue
        current_best = grouped_best_lookup.get(best_key)
        if current_best is None or float(row["message_share"]) < float(current_best["message_share"]):
            grouped_best_lookup[best_key] = row

    level_2_rows: list[dict[str, object]] = []
    for row in level_2_rows_map.values():
        best_key = (
            str(row["competition_scope"]),
            str(row["market_scope"]),
            str(row["problem_level_2"]),
        )
        best_row = grouped_best_lookup.get(best_key)
        best_name = str(best_row["product_name"]) if best_row else ""
        best_spu_id = str(best_row.get("canonical_spu_id", "")) if best_row else ""
        if row.get("is_self_brand") and best_row and float(row["message_share"]) > float(best_row["message_share"]) * 1.05:
            performance_level = "弱于当前行业第一"
        elif best_row:
            performance_level = "持平 / 优于当前行业第一"
        else:
            performance_level = "待比较"
        level_2_rows.append(
            {
                **row,
                "message_share": row["message_share"],
                "performance_level": performance_level,
                "best_competitor_spu_id": best_spu_id,
                "best_competitor_name": best_name,
                "negative_tag": "、".join(row["negative_tags"][:3]),
                "voc_complaint_summary": "；".join(row["complaint_summaries"][:2]),
            }
        )

    level_1_rows_map: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in level_2_rows:
        level_1_key = (
            str(row["competition_scope"]),
            str(row["market_scope"]),
            str(row["problem_level_1"]),
        )
        level_1_item = level_1_rows_map.setdefault(
            level_1_key,
            {
                "competition_scope": row["competition_scope"],
                "series_family": row["series_family"],
                "market_scope": row["market_scope"],
                "problem_level_1": row["problem_level_1"],
                "message_count": 0,
                "top_problem_level_2": "",
                "top_problem_share": 0.0,
                "best_competitor_name": row["best_competitor_name"],
            },
        )
        level_1_item["message_count"] = int(level_1_item["message_count"]) + int(row["message_count"])
        if float(row["message_share"]) > float(level_1_item["top_problem_share"]):
            level_1_item["top_problem_share"] = row["message_share"]
            level_1_item["top_problem_level_2"] = row["problem_level_2"]
            level_1_item["best_competitor_name"] = row["best_competitor_name"]

    def aggregate_scope_layer(is_self_brand: bool) -> list[dict[str, object]]:
        scope_rows_map: dict[tuple[str, str], dict[str, object]] = {}
        for row in level_2_rows:
            if bool(row.get("is_self_brand")) != is_self_brand:
                continue
            scope_key = (str(row["competition_scope"]), str(row["market_scope"]))
            scope_item = scope_rows_map.setdefault(
                scope_key,
                {
                    "competition_scope": row["competition_scope"],
                    "series_family": row["series_family"],
                    "market_scope": row["market_scope"],
                    "message_count": 0,
                    "product_names": set(),
                    "top_problem_level_1": "",
                    "top_problem_level_2": "",
                    "top_problem_share": 0.0,
                    "performance_level": "待比较",
                    "best_competitor_name": "",
                    "best_competitor_spu_id": "",
                    "voc_complaint_summary": "",
                    "top_product_name": "",
                    "top_product_spu_id": "",
                },
            )
            scope_item["message_count"] = int(scope_item["message_count"]) + int(row["message_count"])
            scope_item["product_names"].add(str(row["product_name"]))
            current_share = float(row.get("message_share", 0.0))
            if (
                current_share > float(scope_item["top_problem_share"])
                or (
                    current_share == float(scope_item["top_problem_share"])
                    and int(row.get("message_count", 0)) > int(scope_item["message_count"])
                )
            ):
                scope_item["top_problem_share"] = current_share
                scope_item["top_problem_level_1"] = str(row.get("problem_level_1", ""))
                scope_item["top_problem_level_2"] = str(row.get("problem_level_2", ""))
                scope_item["performance_level"] = str(row.get("performance_level", "待比较"))
                scope_item["best_competitor_name"] = (
                    str(row.get("best_competitor_name", ""))
                    if is_self_brand
                    else str(row.get("product_name", ""))
                )
                scope_item["best_competitor_spu_id"] = (
                    str(row.get("best_competitor_spu_id", ""))
                    if is_self_brand
                    else str(row.get("canonical_spu_id", ""))
                )
                scope_item["voc_complaint_summary"] = str(row.get("voc_complaint_summary", ""))
                scope_item["top_product_name"] = str(row.get("product_name", ""))
                scope_item["top_product_spu_id"] = str(row.get("canonical_spu_id", ""))

        layer_rows: list[dict[str, object]] = []
        for scope_item in scope_rows_map.values():
            product_count = len(scope_item["product_names"])
            has_problem = bool(scope_item["top_problem_level_1"] and scope_item["top_problem_level_2"])
            is_stable = (
                int(scope_item["message_count"]) >= STABLE_SCOPE_MESSAGE_THRESHOLD
                and product_count >= 1
                and has_problem
            )
            if is_stable:
                lead_judgment = (
                    f"{scope_item['competition_scope']} 当前最伤的是 `{scope_item['top_problem_level_1']}`，具体落在 `{scope_item['top_problem_level_2']}`。"
                    if is_self_brand
                    else f"{scope_item['competition_scope']} 当前竞品池主要在抱怨 `{scope_item['top_problem_level_1']}`，外部门槛主要卡在 `{scope_item['top_problem_level_2']}`。"
                )
            else:
                lead_judgment = (
                    f"{scope_item['competition_scope']} 当前该竞争带稳定 VOC 仍待补齐，先不把这条带讲满。"
                    if is_self_brand
                    else f"{scope_item['competition_scope']} 当前竞品池稳定样本仍待补齐，先不把外部门槛讲满。"
                )
            layer_rows.append(
                {
                    "competition_scope": scope_item["competition_scope"],
                    "series_family": scope_item["series_family"],
                    "market_scope": scope_item["market_scope"],
                    "message_count": int(scope_item["message_count"]),
                    "product_count": product_count,
                    "top_problem_level_1": str(scope_item["top_problem_level_1"] or "待补充"),
                    "top_problem_level_2": str(scope_item["top_problem_level_2"] or "当前该竞争带稳定 VOC 仍待补齐"),
                    "message_share": float(scope_item["top_problem_share"]),
                    "performance_level": str(scope_item["performance_level"]),
                    "best_competitor_spu_id": str(scope_item["best_competitor_spu_id"]),
                    "best_competitor_name": str(scope_item["best_competitor_name"]),
                    "voc_complaint_summary": str(scope_item["voc_complaint_summary"] or "当前该竞争带稳定样本仍待补齐，先不把这条带讲满。"),
                    "top_product_name": str(scope_item["top_product_name"]),
                    "top_product_spu_id": str(scope_item["top_product_spu_id"]),
                    "is_self_brand": is_self_brand,
                    "is_stable": is_stable,
                    "lead_judgment": lead_judgment,
                }
            )

        aggregate_rows: list[dict[str, object]] = []
        grouped_by_scope: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in layer_rows:
            grouped_by_scope[str(row["competition_scope"])].append(row)
        for scope, rows_for_scope in grouped_by_scope.items():
            total_messages = sum(int(item.get("message_count", 0)) for item in rows_for_scope)
            product_names = dedupe_preserve_order(
                [str(item.get("top_product_name", "")) for item in rows_for_scope if str(item.get("top_product_name", ""))]
            )
            top_row = sorted(
                rows_for_scope,
                key=lambda item: (
                    -float(item.get("message_share", 0.0)),
                    -int(item.get("message_count", 0)),
                    MARKET_SCOPE_PRIORITY.get(str(item.get("market_scope", "unknown")), 99),
                ),
            )[0]
            is_stable = any(bool(item.get("is_stable")) for item in rows_for_scope) and total_messages >= STABLE_SCOPE_MESSAGE_THRESHOLD
            aggregate_rows.append(
                {
                    **top_row,
                    "market_scope": "ALL",
                    "message_count": total_messages,
                    "product_count": len(product_names) or int(top_row.get("product_count", 0)),
                    "is_stable": is_stable,
                }
            )
        return sorted(
            layer_rows + aggregate_rows,
            key=lambda item: (
                str(item.get("competition_scope", "")),
                MARKET_SCOPE_PRIORITY.get(str(item.get("market_scope", "unknown")), 99),
            ),
        )

    self_scope_rows = aggregate_scope_layer(True)
    external_scope_rows = aggregate_scope_layer(False)
    self_scope_lookup = {
        (str(row["competition_scope"]), str(row["market_scope"])): row
        for row in self_scope_rows
    }
    external_scope_lookup = {
        (str(row["competition_scope"]), str(row["market_scope"])): row
        for row in external_scope_rows
    }

    scope_status_rows: list[dict[str, object]] = []
    frontline_scope_rows: list[dict[str, object]] = []
    for scope, series_family in [("X_omni", "X"), ("T_omni", "T"), ("N_omni", "N"), ("N_aes", "N"), ("N_single", "N")]:
        if not any(str(item.get("competition_scope")) == scope for item in competition_generation_registry.get("rows", []) or []):
            continue
        for market_scope in ["中国", "海外", "ALL"]:
            self_row = self_scope_lookup.get((scope, market_scope))
            external_row = external_scope_lookup.get((scope, market_scope))
            self_is_stable = bool(self_row and self_row.get("is_stable"))
            external_is_stable = bool(external_row and external_row.get("is_stable"))
            if self_is_stable and self_row:
                frontline_mode = "self_stable"
                frontline_row = {
                    **self_row,
                    "frontline_mode": frontline_mode,
                    "status_text": "已有科沃斯稳定竞争 VOC，可进入正式判断。",
                    "external_reference_problem_level_1": external_row.get("top_problem_level_1", "") if external_row else "",
                    "external_reference_problem_level_2": external_row.get("top_problem_level_2", "") if external_row else "",
                }
            elif external_is_stable and external_row:
                frontline_mode = "external_only"
                frontline_row = {
                    "competition_scope": scope,
                    "series_family": series_family,
                    "market_scope": market_scope,
                    "message_count": int(external_row.get("message_count", 0)),
                    "product_count": int(external_row.get("product_count", 0)),
                    "top_problem_level_1": "待补充",
                    "top_problem_level_2": "当前该竞争带稳定 VOC 仍待补齐",
                    "message_share": 0.0,
                    "performance_level": "待比较",
                    "best_competitor_spu_id": str(external_row.get("top_product_spu_id", "")),
                    "best_competitor_name": str(external_row.get("top_product_name", "")),
                    "voc_complaint_summary": f"当前该竞争带外部门槛主要落在 `{external_row.get('top_problem_level_1', '待补充')}` / `{external_row.get('top_problem_level_2', '待补充')}`，但科沃斯该竞争带稳定样本仍待补齐，先不把这条带讲满。",
                    "is_self_brand": True,
                    "is_stable": False,
                    "lead_judgment": f"{scope} 当前外部门槛主要落在 `{external_row.get('top_problem_level_1', '待补充')}` / `{external_row.get('top_problem_level_2', '待补充')}`，但科沃斯该竞争带稳定 VOC 仍待补齐。",
                    "frontline_mode": frontline_mode,
                    "status_text": "当前只有竞品池稳定样本，可讲外部门槛，但不能把它讲成科沃斯当前最伤。",
                    "external_reference_problem_level_1": external_row.get("top_problem_level_1", ""),
                    "external_reference_problem_level_2": external_row.get("top_problem_level_2", ""),
                }
            else:
                frontline_mode = "missing"
                frontline_row = {
                    "competition_scope": scope,
                    "series_family": series_family,
                    "market_scope": market_scope,
                    "message_count": int(self_row.get("message_count", 0) if self_row else 0),
                    "product_count": int(self_row.get("product_count", 0) if self_row else 0),
                    "top_problem_level_1": "待补充",
                    "top_problem_level_2": "当前该竞争带稳定 VOC 仍待补齐",
                    "message_share": 0.0,
                    "performance_level": "待比较",
                    "best_competitor_spu_id": str(external_row.get("top_product_spu_id", "")) if external_row else "",
                    "best_competitor_name": str(external_row.get("top_product_name", "")) if external_row else "",
                    "voc_complaint_summary": "当前该竞争带稳定样本仍待补齐，先不把这条带讲满。",
                    "is_self_brand": True,
                    "is_stable": False,
                    "lead_judgment": f"{scope} 当前该竞争带稳定 VOC 仍待补齐，先不把这条带讲满。",
                    "frontline_mode": frontline_mode,
                    "status_text": "当前该竞争带稳定 VOC 仍待补齐，先不把这条带讲满。",
                    "external_reference_problem_level_1": external_row.get("top_problem_level_1", "") if external_row else "",
                    "external_reference_problem_level_2": external_row.get("top_problem_level_2", "") if external_row else "",
                }
            scope_status_rows.append(
                {
                    "competition_scope": scope,
                    "series_family": series_family,
                    "market_scope": market_scope,
                    "self_message_count": int(self_row.get("message_count", 0)) if self_row else 0,
                    "self_product_count": int(self_row.get("product_count", 0)) if self_row else 0,
                    "self_is_stable": self_is_stable,
                    "external_message_count": int(external_row.get("message_count", 0)) if external_row else 0,
                    "external_product_count": int(external_row.get("product_count", 0)) if external_row else 0,
                    "external_is_stable": external_is_stable,
                    "frontline_mode": frontline_mode,
                    "status_text": str(frontline_row.get("status_text", "")),
                }
            )
            frontline_scope_rows.append(frontline_row)

    level_1_rows: list[dict[str, object]] = []
    for row in level_1_rows_map.values():
        scope_total = sum(
            int(item["message_count"])
            for item in level_1_rows_map.values()
            if item["competition_scope"] == row["competition_scope"] and item["market_scope"] == row["market_scope"]
        )
        row["message_share"] = round(int(row["message_count"]) / scope_total, 4) if scope_total else 0.0
        level_1_rows.append(row)

    scope_rows = sorted(
        self_scope_rows + external_scope_rows,
        key=lambda row: (
            str(row.get("competition_scope", "")),
            MARKET_SCOPE_PRIORITY.get(str(row.get("market_scope", "unknown")), 99),
            not bool(row.get("is_self_brand")),
        ),
    )
    existing_scope_keys = {
        (str(row["competition_scope"]), str(row["market_scope"]), bool(row.get("is_self_brand")))
        for row in scope_rows
    }
    for scope, series_family in [("X_omni", "X"), ("T_omni", "T"), ("N_omni", "N"), ("N_aes", "N"), ("N_single", "N")]:
        for is_self_brand in [True, False]:
            if (scope, "ALL", is_self_brand) in existing_scope_keys:
                continue
            scope_rows.append(
                {
                    "competition_scope": scope,
                    "series_family": series_family if is_self_brand else "external",
                    "market_scope": "ALL",
                    "message_count": 0,
                    "product_count": 0,
                    "top_problem_level_1": "待补充",
                    "top_problem_level_2": "当前该竞争带稳定 VOC 仍待补齐",
                    "message_share": 0.0,
                    "performance_level": "待比较",
                    "best_competitor_spu_id": "",
                    "best_competitor_name": "",
                    "voc_complaint_summary": "当前该竞争带稳定样本仍待补齐，先不把这条带讲满。",
                    "top_product_name": "",
                    "top_product_spu_id": "",
                    "is_self_brand": is_self_brand,
                    "is_stable": False,
                    "lead_judgment": (
                        f"{scope} 当前该竞争带稳定 VOC 仍待补齐，先不把这条带讲满。"
                        if is_self_brand
                        else f"{scope} 当前竞品池稳定样本仍待补齐，先不把外部门槛讲满。"
                    ),
                }
            )

    product_rows = sorted(
        product_rows_map.values(),
        key=lambda row: (
            str(row["competition_scope"]),
            MARKET_SCOPE_PRIORITY.get(str(row["market_scope"]), 99),
            not bool(row["is_self_brand"]),
            -int(row["message_count"]),
            str(row["product_name"]),
        ),
    )
    level_1_rows.sort(key=lambda row: (str(row["competition_scope"]), MARKET_SCOPE_PRIORITY.get(str(row["market_scope"]), 99), -float(row["message_share"])))
    level_2_rows.sort(key=lambda row: (str(row["competition_scope"]), MARKET_SCOPE_PRIORITY.get(str(row["market_scope"]), 99), -float(row["message_share"]), str(row["product_name"])))
    scope_rows.sort(key=lambda row: (str(row["competition_scope"]), MARKET_SCOPE_PRIORITY.get(str(row["market_scope"]), 99), not bool(row.get("is_self_brand"))))
    frontline_scope_rows.sort(key=lambda row: (str(row["competition_scope"]), MARKET_SCOPE_PRIORITY.get(str(row["market_scope"]), 99)))
    scope_status_rows.sort(key=lambda row: (str(row["competition_scope"]), MARKET_SCOPE_PRIORITY.get(str(row["market_scope"]), 99)))

    scope_match_diagnostics: list[dict[str, object]] = []
    for scope in COMPETITION_FRONTLINE_SCOPES:
        relevant_rows = [row for row in product_rows if str(row.get("competition_scope")) == scope]
        if not relevant_rows:
            continue
        scope_match_diagnostics.append(
            {
                "competition_scope": scope,
                "source_db_path": get_connection_source_path(conn),
                "total_product_count": len(relevant_rows),
                "high_medium_product_count": sum(1 for row in relevant_rows if str(row.get("match_confidence")) in {"high", "medium"}),
                "low_confidence_product_count": sum(1 for row in relevant_rows if str(row.get("match_confidence")) == "low"),
                "self_product_examples": [str(row.get("product_name", "")) for row in relevant_rows if bool(row.get("is_self_brand"))][:5],
                "external_product_examples": [str(row.get("product_name", "")) for row in relevant_rows if not bool(row.get("is_self_brand"))][:5],
            }
        )
    return {
        "scope_rows": scope_rows,
        "product_rows": product_rows,
        "level_1_rows": level_1_rows,
        "level_2_rows": level_2_rows,
        "self_scope_rows": self_scope_rows,
        "external_scope_rows": external_scope_rows,
        "frontline_scope_rows": frontline_scope_rows,
        "scope_status_rows": scope_status_rows,
        "source_db_path": get_connection_source_path(conn),
        "scope_match_diagnostics": scope_match_diagnostics,
        "low_confidence_match_count": low_confidence_match_count,
        "filtered_product_count": filtered_product_count,
    }


def registry_alias_pattern(alias_text: str) -> re.Pattern[str] | None:
    cleaned = alias_text.strip()
    if not cleaned:
        return None
    escaped = re.escape(cleaned)
    escaped = escaped.replace(r"\ ", r"\s*")
    if re.search(r"[A-Za-z0-9]", cleaned):
        pattern = rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
        return re.compile(pattern, re.IGNORECASE)
    return re.compile(escaped)


def alias_rule_matches_text(text: str, alias_rule: dict[str, object]) -> bool:
    if not text:
        return False
    raw_text = strip_invisible_tokens(text).strip()
    normalized_text = normalize_match_text(raw_text)
    match_value = str(alias_rule.get("match_value", "")).strip()
    normalized_value = normalize_match_text(str(alias_rule.get("normalized_match_value", "") or match_value))
    if not match_value or not normalized_value:
        return False
    pattern = registry_alias_pattern(match_value)
    match_type = str(alias_rule.get("match_type", "contains"))
    if match_type == "exact":
        if normalized_text == normalized_value:
            return True
        return bool(pattern and pattern.fullmatch(raw_text))
    if len(normalized_value) <= 4:
        return bool(pattern and pattern.search(raw_text))
    return normalized_value in normalized_text or bool(pattern and pattern.search(raw_text))


def score_alias_rule_against_text(
    text: str,
    alias_rule: dict[str, object],
    *,
    source_field: str,
) -> tuple[int, str] | None:
    if not text:
        return None
    raw_text = strip_invisible_tokens(text).strip()
    normalized_text = normalize_match_text(raw_text)
    match_value = str(alias_rule.get("match_value", "")).strip()
    normalized_value = normalize_match_text(str(alias_rule.get("normalized_match_value", "") or match_value))
    if not raw_text or not match_value or not normalized_value:
        return None
    pattern = registry_alias_pattern(match_value)
    if normalized_text == normalized_value or (pattern and pattern.fullmatch(raw_text)):
        base = 320 if source_field == "raw_model" else 290 if source_field == "product_title" else 90
        return base + len(normalized_value), "exact"
    if pattern and pattern.search(raw_text):
        base = 300 if source_field == "raw_model" else 270 if source_field == "product_title" else 80
        return base + len(normalized_value), "boundary"
    if len(normalized_value) >= 6 and normalized_value in normalized_text:
        base = 280 if source_field == "raw_model" else 250 if source_field == "product_title" else 70
        return base + len(normalized_value), "contains"
    return None


def match_registry_product_entry(
    row: sqlite3.Row,
    registry_index: dict[str, list[dict[str, object]]],
) -> dict[str, object] | None:
    raw_model = str(row["raw_model"] or "")
    product_title = str(row["product_title"] or "")
    product_url = str(row["product_url"] or "")
    canonical_spu_id = str(row["canonical_spu_id"] or "")
    normalized_spu = normalize_match_text(canonical_spu_id)
    canonical_entry = registry_index.get("spu_entry_map", {}).get(canonical_spu_id) or registry_index.get("spu_entry_map", {}).get(normalized_spu)
    scope_override = match_scope_alias_override(raw_model, product_title)
    candidate_entries = list(registry_index.get("entries", []))
    if scope_override:
        candidate_entries = [
            entry
            for entry in candidate_entries
            if str(entry.get("competition_scope", "")) == str(scope_override.get("competition_scope", ""))
        ]
        if not candidate_entries:
            candidate_entries = list(registry_index.get("entries", []))
    best_entry: dict[str, object] | None = None
    best_score = -1
    best_specificity = -1
    best_confidence = "low"
    best_reason = ""
    best_alias_value = ""
    best_alias_priority = 999
    best_override_used = False
    conflict = False
    for entry in candidate_entries:
        alias = str(entry.get("normalized_alias", ""))
        display_name = str(entry.get("display_name", ""))
        if not alias:
            continue
        score = -1
        confidence = "low"
        reason = ""
        matched_alias_value = ""
        matched_alias_priority = entry_alias_priority(entry)
        override_used = False
        candidate_spu_ids = [normalize_match_text(str(item)) for item in entry.get("candidate_spu_ids", [])]
        alias_specificity = len(alias)
        aggregate_canonical = normalized_spu in {normalize_match_text(item) for item in CANONICAL_AGGREGATE_HINTS}
        canonical_conflicts = bool(
            normalized_spu
            and candidate_spu_ids
            and normalized_spu not in candidate_spu_ids
        )
        best_alias_match: tuple[int, dict[str, object], str] | None = None
        for alias_rule in entry.get("alias_rules", []) or []:
            raw_match = score_alias_rule_against_text(raw_model, alias_rule, source_field="raw_model")
            if not raw_match:
                continue
            candidate = (raw_match[0], alias_rule, raw_match[1])
            if best_alias_match is None or candidate[0] > best_alias_match[0]:
                best_alias_match = candidate
        if best_alias_match:
            score = best_alias_match[0]
            confidence = "high"
            reason = f"raw_model_alias_rule:{best_alias_match[1]['match_value']}:{best_alias_match[2]}"
            matched_alias_value = str(best_alias_match[1]["match_value"])
            matched_alias_priority = int(best_alias_match[1].get("priority_order", 999))
        if score < 0:
            best_alias_match = None
            for alias_rule in entry.get("alias_rules", []) or []:
                title_match = score_alias_rule_against_text(product_title, alias_rule, source_field="product_title")
                if not title_match:
                    continue
                candidate = (title_match[0], alias_rule, title_match[1])
                if best_alias_match is None or candidate[0] > best_alias_match[0]:
                    best_alias_match = candidate
            if best_alias_match:
                score = best_alias_match[0]
                confidence = "medium"
                reason = f"product_title_alias_rule:{best_alias_match[1]['match_value']}:{best_alias_match[2]}"
                matched_alias_value = str(best_alias_match[1]["match_value"])
                matched_alias_priority = int(best_alias_match[1].get("priority_order", 999))
        if score < 0 and not canonical_conflicts:
            best_alias_match = None
            for alias_rule in entry.get("alias_rules", []) or []:
                if len(normalize_match_text(alias_rule.get("match_value", ""))) < 6:
                    continue
                url_match = score_alias_rule_against_text(product_url, alias_rule, source_field="product_url")
                if not url_match:
                    continue
                candidate = (url_match[0], alias_rule, url_match[1])
                if best_alias_match is None or candidate[0] > best_alias_match[0]:
                    best_alias_match = candidate
            if best_alias_match:
                score = best_alias_match[0]
                confidence = "low"
                reason = f"product_url_alias_rule:{best_alias_match[1]['match_value']}:{best_alias_match[2]}"
                matched_alias_value = str(best_alias_match[1]["match_value"])
                matched_alias_priority = int(best_alias_match[1].get("priority_order", 999))
        if score < 0 and normalized_spu and normalized_spu in candidate_spu_ids:
            score = (180 if aggregate_canonical else 220) + alias_specificity
            confidence = "medium" if aggregate_canonical else "high"
            reason = "canonical_spu_id_direct_hit_aggregate" if aggregate_canonical else "canonical_spu_id_direct_hit"
        if score < 0:
            alias_pattern = registry_alias_pattern(display_name)
            if alias_pattern and alias_pattern.fullmatch(strip_invisible_tokens(raw_model).strip()):
                score = 240 + alias_specificity
                confidence = "high"
                reason = "raw_model_display_exact"
            elif not canonical_conflicts and alias_pattern and alias_pattern.search(strip_invisible_tokens(raw_model).strip()):
                score = 225 + alias_specificity
                confidence = "medium"
                reason = "raw_model_display_boundary"
            elif not canonical_conflicts and alias_pattern and alias_pattern.search(strip_invisible_tokens(product_title).strip()):
                score = 210 + alias_specificity
                confidence = "medium"
                reason = "product_title_display_boundary"
            elif not canonical_conflicts and len(alias) >= 8 and alias in normalize_match_text(product_url):
                score = 95 + alias_specificity
                confidence = "low"
                reason = "product_url_display_contains"
            elif len(alias) >= 6 and alias in normalized_spu:
                score = 90 + alias_specificity
                confidence = "low"
                reason = "canonical_spu_id_contains_alias"
        if matched_alias_value and canonical_entry and str(canonical_entry.get("competition_scope", "")) != str(entry.get("competition_scope", "")):
            override_used = True
        elif (
            matched_alias_value
            and canonical_spu_id in CANONICAL_AGGREGATE_HINTS
            and reason.startswith(("raw_model_alias_rule", "product_title_alias_rule"))
            and len(normalize_match_text(matched_alias_value)) > len(str(canonical_entry.get("normalized_alias", "")) if canonical_entry else "")
        ):
            override_used = True
        if canonical_conflicts and score >= 0 and not reason.startswith("raw_model_alias_rule") and not reason.startswith("product_title_alias_rule"):
            continue
        if score < 0:
            continue
        if score == best_score and best_entry and best_entry is not entry and alias_specificity == best_specificity:
            conflict = True
        if (
            score > best_score
            or (score == best_score and alias_specificity > best_specificity)
            or (
                score == best_score
                and alias_specificity == best_specificity
                and matched_alias_priority < best_alias_priority
            )
        ):
            best_entry = entry
            best_score = score
            best_specificity = alias_specificity
            best_confidence = confidence
            best_reason = reason
            best_alias_value = matched_alias_value
            best_alias_priority = matched_alias_priority
            best_override_used = override_used
            conflict = False
    if not best_entry:
        return None
    payload = dict(best_entry)
    if conflict:
        payload["match_confidence"] = "low"
        payload["match_reason"] = "conflict_same_score"
    else:
        payload["match_confidence"] = best_confidence
    payload["match_reason"] = best_reason
    if not best_alias_value and scope_override:
        best_alias_value = str(scope_override.get("matched_alias_value", ""))
    payload["matched_alias_value"] = best_alias_value
    payload["matched_alias_priority"] = best_alias_priority if best_alias_value else None
    scope_override_used = bool(
        scope_override
        and str(best_entry.get("competition_scope", "")) == str(scope_override.get("competition_scope", ""))
        and str(scope_override.get("competition_scope", "")) != "N_single"
    )
    payload["used_specific_alias_override"] = best_override_used or scope_override_used
    return payload


def build_competition_voc_market_split(
    competition_voc_xtn_breakdown: dict[str, object],
) -> dict[str, object]:
    market_rows: list[dict[str, object]] = []
    market_summary_rows: list[dict[str, object]] = []
    scope_status_rows = [
        row
        for row in (competition_voc_xtn_breakdown.get("scope_status_rows", []) or [])
        if str(row.get("market_scope")) in {"中国", "海外"}
    ]
    frontline_rows = competition_voc_xtn_breakdown.get("frontline_scope_rows", []) or []
    if not frontline_rows:
        frontline_rows = competition_voc_xtn_breakdown.get("scope_rows", []) or []
    for market_scope in ["中国", "海外"]:
        scope_rows = [
            row
            for row in frontline_rows
            if row.get("market_scope") == market_scope
        ]
        total_messages = sum(int(row.get("message_count", 0)) for row in scope_rows)
        stable_scope_count = sum(
            1
            for row in scope_rows
            if row.get("frontline_mode") in {"self_stable", "external_only"}
            or row.get("is_stable")
            or (
                int(row.get("message_count", 0)) >= STABLE_SCOPE_MESSAGE_THRESHOLD
                and str(row.get("top_problem_level_1", "")) not in {"", "-", "待补充"}
            )
        )
        stable = total_messages >= 500 and stable_scope_count >= 2
        market_summary_rows.append(
            {
                "market_scope": market_scope,
                "scope_count": len(scope_rows),
                "message_count": total_messages,
                "stable_scope_count": stable_scope_count,
                "is_stable": stable,
                "status_text": "稳定，可进入正式并列页" if stable else "当前切分尚未稳定，不进入正式并列页",
            }
        )
        for row in scope_rows:
            market_rows.append(
                {
                    "market_scope": market_scope,
                    "competition_scope": row["competition_scope"],
                    "series_family": row["series_family"],
                    "lead_judgment": row["lead_judgment"],
                    "top_problem_level_1": row["top_problem_level_1"],
                    "top_problem_level_2": row["top_problem_level_2"],
                    "message_share": row.get("message_share", 0.0),
                    "performance_level": row.get("performance_level", "待比较"),
                    "best_competitor_name": row["best_competitor_name"],
                    "voc_complaint_summary": row.get("voc_complaint_summary", ""),
                    "message_count": row["message_count"],
                    "frontline_mode": row.get("frontline_mode", "legacy"),
                    "status_text": row.get("status_text", ""),
                }
            )
    return {
        "market_rows": market_rows,
        "market_summary_rows": market_summary_rows,
        "scope_status_rows": scope_status_rows,
    }


def build_cross_source_interpretation(
    consistent_issues: list[list[object]],
    consistent_strengths: list[list[object]],
    conflict_rows: list[list[object]],
    priority_rows: list[list[object]],
    summary_insights: dict[str, object],
    survey_segments: dict[str, object],
    voc_packages: dict[str, object],
    qual_evidence_packet: dict[str, object] | None = None,
    cross_source_hypothesis_board: dict[str, object] | None = None,
    judgment_acceptance_log: dict[str, object] | None = None,
) -> dict[str, object]:
    interpretations: list[dict[str, object]] = []
    package_lookup = defaultdict(list)
    for package in voc_packages.get("packages", []):
        package_lookup[package["spu_id"]].append(package)
    qual_packet_refs_by_theme: dict[str, list[str]] = defaultdict(list)
    if qual_evidence_packet:
        for packet in qual_evidence_packet.get("packets", []) or []:
            if str(packet.get("reasoning_task_type", "")) != "theme_explain":
                continue
            topic_name = str(packet.get("topic_name", "")).strip()
            if not topic_name:
                continue
            qual_packet_refs_by_theme[topic_name].append(f"qual_evidence_packet:{packet.get('packet_id')}")
    accepted_claim_ids = {
        str(row.get("claim_id", "")).strip()
        for row in (judgment_acceptance_log or {}).get("rows", []) or []
        if bool(row.get("frontstage_permission")) and str(row.get("claim_id", "")).strip()
    }
    hypothesis_rows = (cross_source_hypothesis_board or {}).get("rows", []) or []
    hypothesis_rows_by_theme: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in hypothesis_rows:
        related_topics = [
            str(item.get("topic_name", "")).strip()
            for item in (row.get("support_from_voc", []) or [])
            if str(item.get("topic_name", "")).strip()
        ]
        if not related_topics:
            claim_text = str(row.get("claim", ""))
            related_topics = [claim_text] if claim_text else []
        for theme in dedupe_preserve_order(related_topics):
            hypothesis_rows_by_theme[theme].append(row)

    def confidence_from_source_count(source_count: int) -> str:
        if source_count >= 3:
            return "高"
        if source_count == 2:
            return "中"
        return "低"

    def hypothesis_context(theme: str) -> tuple[str, str, list[str], list[str]]:
        rows = hypothesis_rows_by_theme.get(str(theme), [])
        if not rows:
            return "", "", [], []
        accepted_rows = [row for row in rows if str(row.get("hypothesis_id", "")).strip() in accepted_claim_ids]
        target_row = accepted_rows[0] if accepted_rows else rows[0]
        resolution_status = str(target_row.get("resolution_status", "")).strip()
        accepted_refs = [
            f"cross_source_hypothesis:{row.get('hypothesis_id')}"
            for row in accepted_rows
            if str(row.get("hypothesis_id", "")).strip()
        ][:3]
        conflict_signals = [str(item).strip() for item in (target_row.get("conflict_signals", []) or []) if str(item).strip()]
        return (
            str(target_row.get("why_accepted_or_rejected", "")).strip(),
            resolution_status,
            conflict_signals[:3],
            accepted_refs,
        )

    if not priority_rows and not conflict_rows and hypothesis_rows:
        derived_priority_rows: list[list[object]] = []
        derived_conflict_rows: list[list[object]] = []
        for row in hypothesis_rows:
            topics = [
                str(item.get("topic_name", "")).strip()
                for item in (row.get("support_from_voc", []) or [])
                if str(item.get("topic_name", "")).strip()
            ]
            resolution_status = str(row.get("resolution_status", "")).strip()
            for topic in dedupe_preserve_order(topics or [str(row.get("claim", "")).strip()]):
                if not topic:
                    continue
                if resolution_status == "contested":
                    derived_conflict_rows.append([topic, "VOC:derived", "Survey:derived", "Summary:derived", str(row.get("why_accepted_or_rejected", "")).strip() or "继续补验证"])
                else:
                    derived_priority_rows.append([
                        topic,
                        3 if resolution_status == "accepted" else 1,
                        1,
                        1,
                        1,
                        "P1" if resolution_status == "accepted" else "待验证",
                    ])
        priority_rows = derived_priority_rows
        conflict_rows = derived_conflict_rows

    for theme, source_count, voc_negative_count, survey_hit_count, summary_hit_count, priority in priority_rows:
        hypothesis_explanation, resolution_status, conflict_signals, accepted_claim_refs = hypothesis_context(str(theme))
        if source_count >= 3:
            alignment_type = "一致"
            explanation = THEME_EXPLANATIONS.get(theme, "三个来源都在指向同一类问题，已经可以视为稳定结论。")
            next_step = "可以直接进入优先级讨论与策略翻译。"
        elif source_count == 2 and voc_negative_count:
            alignment_type = "一致"
            explanation = THEME_EXPLANATIONS.get(theme, "这类问题已在两个来源同时出现，说明它不是单点抱怨。")
            next_step = "优先补第三源，确认它是稳定结论还是阶段性放大。"
        elif source_count == 1 and voc_negative_count:
            alignment_type = "单源信号"
            explanation = "当前主要由使用后反馈暴露，可能是使用中才显现的问题，也可能是低渗透但高痛感场景。"
            next_step = "优先去问卷和定性中补同类场景验证。"
        else:
            alignment_type = "单源信号"
            explanation = "当前更像期待型或模式型洞察，量化验证仍不足。"
            next_step = "优先补问卷样本或更多案例。"
        if hypothesis_explanation:
            explanation = hypothesis_explanation
        if resolution_status == "contested":
            alignment_type = "冲突"
        interpretations.append(
            {
                "theme_name": theme,
                "alignment_type": alignment_type,
                "best_explanation": explanation,
                "confidence": confidence_from_source_count(int(source_count)),
                "next_validation_step": next_step,
                "priority_hint": priority,
                "qual_packet_refs": dedupe_preserve_order(qual_packet_refs_by_theme.get(str(theme), []))[:3],
                "resolution_status": resolution_status or ("accepted" if alignment_type == "一致" else "not_ready"),
                "why_not_other_explanation": "；".join(conflict_signals) if conflict_signals else "",
                "accepted_claim_refs": accepted_claim_refs,
            }
        )

    for theme, voc_signal, survey_signal, summary_signal, judgment in conflict_rows:
        hypothesis_explanation, resolution_status, conflict_signals, accepted_claim_refs = hypothesis_context(str(theme))
        explanation = "三源口径没有对齐，优先判断是样本差异、场景差异，还是阶段差异。"
        if "VOC" in voc_signal and "Survey:0" in survey_signal:
            explanation = "这类问题更像使用后才暴露，或者是低频极端工况，问卷未必会自然提到。"
        elif "VOC:0" in voc_signal and ("Survey:" in survey_signal or "Summary:" in summary_signal):
            explanation = "这类问题更像期待型判断或小样本模式洞察，未必已经在大规模 VOC 中爆出来。"
        if hypothesis_explanation:
            explanation = hypothesis_explanation
        interpretations.append(
            {
                "theme_name": theme,
                "alignment_type": "冲突",
                "best_explanation": explanation,
                "confidence": "中",
                "next_validation_step": judgment,
                "priority_hint": "待验证",
                "qual_packet_refs": dedupe_preserve_order(qual_packet_refs_by_theme.get(str(theme), []))[:3],
                "resolution_status": resolution_status or "contested",
                "why_not_other_explanation": "；".join(conflict_signals) if conflict_signals else "",
                "accepted_claim_refs": accepted_claim_refs,
            }
        )

    return {"interpretation_count": len(interpretations), "interpretations": interpretations}


def infer_series_code(spu_id: str | None, text_hint: str = "") -> str:
    normalized = normalize_text(f"{spu_id or ''} {text_hint}")
    x_markers = ("ecovacsx", "x11", "x12", "g30", "x50", "x60", "z60", "z70", "002", "003", "逍遥")
    t_markers = ("ecovacst", "t80", "t90", "p20", "p60", "p70", "j6", "jx", "s60")
    n_markers = (
        "ecovacsn",
        "n20",
        "n50",
        "t50",
        "t30",
        "帕斯卡",
        "摩根",
        "p10",
        "q10",
        "q7",
        "d20",
        "d10",
        "e20",
        "e30",
        "e40",
        "m30",
        "m40",
        "x10",
        "x20",
        "h40",
        "s20",
        "s40",
        "l60",
        "c10",
        "roomba105",
        "roomba104",
    )
    if any(marker in normalized for marker in x_markers):
        return "X"
    if any(marker in normalized for marker in t_markers):
        return "T"
    if any(marker in normalized for marker in n_markers):
        return "N"
    return "unknown"


def summarize_series_concepts(series_code: str, cards: list[dict[str, object]], segments: list[dict[str, object]]) -> dict[str, object]:
    text_blob = " ".join(
        [card.get("case_title", "") for card in cards]
        + [json.dumps(card.get("source_texts", {}), ensure_ascii=False) for card in cards]
    )
    segment_blob = " ".join(
        [segment.get("segment_name", "") for segment in segments]
        + [json.dumps(segment.get("difference_lines", []), ensure_ascii=False) for segment in segments]
    )
    if series_code == "X":
        positioning_candidates = top_labels(text_blob, X_POSITIONING_RULES, limit=3)
        jtbd_candidates = top_labels(text_blob, X_JTBD_RULES, limit=3)
        return {
            "positioning_candidates": positioning_candidates,
            "jtbd_candidates": jtbd_candidates,
            "difference_reason_clusters": [],
        }
    role_modes = top_labels(text_blob, T_ROLE_MODE_RULES, limit=3)
    difference_dimensions = top_labels(text_blob + " " + segment_blob, T_DIFFERENCE_DIMENSION_RULES, limit=3)
    jtbd_candidates = top_labels(text_blob, T_JTBD_RULES, limit=3)
    return {
        "positioning_candidates": role_modes,
        "jtbd_candidates": jtbd_candidates,
        "difference_reason_clusters": difference_dimensions,
    }


def gather_case_field_samples(cases: list[dict[str, object]], field_name: str, limit: int = 6) -> list[str]:
    samples: list[str] = []
    for case in cases:
        value = case.get(field_name, [])
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    samples.append(item)
    return dedupe_preserve_order(samples)[:limit]


def is_valid_x_role_label(label: str) -> bool:
    if not (2 <= len(label) <= 6):
        return False
    return any(label.endswith(suffix) for suffix in X_ROLE_LABEL_ALLOWED_SUFFIXES)


def x_signal_schema(signal_name: str) -> dict[str, object]:
    return X_ROLE_LABEL_SCHEMA[signal_name]


def x_signal_case_text_rows(case: dict[str, object]) -> list[str]:
    rows: list[str] = [str(case.get("case_title", ""))]
    for field_name in [
        "persona_notes",
        "cleaning_attitude",
        "purchase_trigger",
        "purchase_decision",
        "pain_points",
        "expected_needs",
        "concept_ideas",
        "brand_evaluation",
        "hidden_needs",
        "value_definition",
    ]:
        value = case.get(field_name, [])
        if isinstance(value, list):
            rows.extend(str(item) for item in value if str(item).strip())
    return rows


def x_signal_hidden_need_boost(case: dict[str, object], signal_name: str) -> int:
    hidden_needs = set(case.get("hidden_needs", []) or [])
    if signal_name == "低介入托管信号" and "真正托管" in hidden_needs:
        return 6
    if signal_name == "科技表达信号" and "身份表达" in hidden_needs:
        return 4
    if signal_name == "基础代劳信号" and "家务负担转移" in hidden_needs:
        return 2
    return 0


def build_x_signal_case_score(
    case: dict[str, object],
    semantic_passages: dict[str, object],
    signal_name: str,
) -> dict[str, object]:
    schema = x_signal_schema(signal_name)
    case_title = str(case.get("case_title", "-"))
    text_rows = x_signal_case_text_rows(case)
    keyword_score = sum(score_text_against_keywords(text, schema["keywords"]) for text in text_rows)  # type: ignore[index]
    support_passages = pick_passages(
        semantic_passages,
        case_titles=[case_title],
        roles=list(schema["preferred_roles"]),  # type: ignore[arg-type]
        keywords=list(schema["keywords"]),  # type: ignore[arg-type]
        limit=4,
    )
    high_quality_support_count = sum(1 for row in support_passages if float(row.get("quality_score", 0.0)) >= 0.75)
    negative_score = sum(score_text_against_keywords(text, schema["negative_keywords"]) for text in text_rows)  # type: ignore[index]
    hidden_need_boost = x_signal_hidden_need_boost(case, signal_name)
    hallmark_signals = [
        keyword
        for keyword in schema["hallmark_keywords"]  # type: ignore[index]
        if any(text_matches_any(text, [keyword]) for text in text_rows)
    ]
    expression_anchor_hits = 0
    if signal_name == "科技表达信号":
        expression_anchor_hits = sum(
            1
            for keyword in schema["expression_anchor_keywords"]  # type: ignore[index]
            if any(text_matches_any(text, [keyword]) for text in text_rows)
        )
    contradiction_passages = pick_passages(
        semantic_passages,
        case_titles=[case_title],
        roles=list(schema["preferred_roles"]),  # type: ignore[arg-type]
        keywords=list(schema["negative_keywords"]),  # type: ignore[arg-type]
        limit=2,
    )
    signal_score = keyword_score + len(support_passages) * 2 + hidden_need_boost + high_quality_support_count - min(negative_score, 3)
    if signal_name == "科技表达信号":
        if hidden_need_boost == 0:
            signal_score -= 4
        if expression_anchor_hits == 0:
            signal_score -= 6
        elif expression_anchor_hits == 1 and hidden_need_boost == 0:
            signal_score -= 2
        if len(hallmark_signals) <= 1:
            signal_score -= 2
    if signal_score >= 8 and high_quality_support_count >= 2:
        naming_readiness = "高"
    elif signal_score >= 4:
        naming_readiness = "中"
    else:
        naming_readiness = "低"
    return {
        "signal_name": signal_name,
        "canonical_anchor": schema["canonical_anchor"],
        "keyword_score": keyword_score,
        "hidden_need_boost": hidden_need_boost,
        "negative_score": negative_score,
        "score": signal_score,
        "supporting_passages": support_passages,
        "contradicting_passages": contradiction_passages,
        "high_quality_support_count": high_quality_support_count,
        "hallmark_signals": hallmark_signals,
        "expression_anchor_hits": expression_anchor_hits,
        "naming_readiness": naming_readiness,
    }


def rank_x_signal_scores(
    case: dict[str, object],
    semantic_passages: dict[str, object],
) -> list[dict[str, object]]:
    scored = [
        build_x_signal_case_score(case, semantic_passages, signal_name)
        for signal_name in X_ROLE_LABEL_SCHEMA
    ]
    scored.sort(key=lambda item: (-int(item["score"]), -int(item["high_quality_support_count"]), str(item["signal_name"])))
    return scored


def choose_x_role_label(
    signal_name: str,
    hallmark_signals: list[str],
    representative_quotes: list[str],
) -> str:
    schema = x_signal_schema(signal_name)
    candidates = list(schema["label_candidates"])  # type: ignore[index]
    quote_blob = " ".join(representative_quotes + hallmark_signals)
    if signal_name == "科技表达信号":
        if any(keyword in quote_blob for keyword in ("科技感", "黑科技", "高端")):
            return "科技玩家"
        if any(keyword in quote_blob for keyword in ("颜值", "外观", "设计")):
            return "清洁玩家"
    if signal_name == "低介入托管信号":
        if any(keyword in quote_blob for keyword in ("托管", "主动", "少操心", "无感")):
            return "清洁管家"
    if signal_name == "基础代劳信号":
        if any(keyword in quote_blob for keyword in ("80%", "补尾", "别添乱", "少维护")):
            return "清洁帮手"
    for candidate in candidates:
        if is_valid_x_role_label(candidate):
            return candidate
    return candidates[0]


def default_x_jtbd_for_anchor(canonical_anchor: str) -> str:
    if canonical_anchor == "清洁帮手":
        return "地面基础清洁代劳"
    if canonical_anchor == "清洁管家":
        return "整体洁净托管"
    return "科技美学表达"


def build_x_label_reason(display_label: str, canonical_anchor: str, hallmark_signals: list[str], positioning_level: str) -> str:
    signal_text = "、".join(hallmark_signals[:3]) if hallmark_signals else "当前最稳定的用户判断"
    if canonical_anchor == "清洁帮手":
        reason = f"这类人更像在找一个把基础清洁做完、但别添乱的 `{display_label}`，核心证据集中在 `{signal_text}`。"
    elif canonical_anchor == "清洁管家":
        reason = f"这类人更像在找一个能少操心、少返工、主动补位的 `{display_label}`，核心证据集中在 `{signal_text}`。"
    else:
        reason = f"这类人更像在找一个能承载科技感和设计表达的 `{display_label}`，核心证据集中在 `{signal_text}`。"
    if positioning_level == "weak_signal":
        reason += " 但当前它更像方向性表达信号，还不像前两类那样是稳定主定位。"
    return reason


def build_x_not_other_reason(canonical_anchor: str) -> str:
    if canonical_anchor == "清洁帮手":
        return "这类人首先在买基础代劳和少维护，不是在买主动托管，也不是在买可被看见的科技表达。"
    if canonical_anchor == "清洁管家":
        return "这类人首先在买低介入托管和少返工，不是在买‘80% 够用’，也不是先在买设计表达。"
    return "这类人首先在买科技感、设计感和悦己表达，不是在买基础代劳，也不是在买完整托管。"


def build_x_case_signal_profiles(
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
) -> dict[str, object]:
    profiles: list[dict[str, object]] = []
    cases = [case for case in case_concept_slots.get("cases", []) if case.get("series_code") == "X"]  # type: ignore[index]
    for case in cases:
        ranked = rank_x_signal_scores(case, semantic_passages)
        profiles.append(
            {
                "case_title": case["case_title"],
                "canonical_spu_id": case.get("inferred_spu_id"),
                "signal_scores": {
                    row["signal_name"]: {
                        "canonical_anchor": row["canonical_anchor"],
                        "score": row["score"],
                        "keyword_score": row["keyword_score"],
                        "high_quality_support_count": row["high_quality_support_count"],
                        "hallmark_signals": row["hallmark_signals"],
                    }
                    for row in ranked
                },
                "dominant_signals": [row["signal_name"] for row in ranked if int(row["score"]) > 0][:3],
                "supporting_passages": [
                    {
                        "signal_name": ranked[0]["signal_name"],
                        "passage_text": row["passage_text"],
                        "quality_score": row["quality_score"],
                    }
                    for row in ranked[0]["supporting_passages"][:3]
                ] if ranked else [],
                "contradicting_passages": [
                    {
                        "signal_name": row["signal_name"],
                        "passage_text": passage["passage_text"],
                        "quality_score": passage["quality_score"],
                    }
                    for row in ranked[1:2]
                    for passage in row["supporting_passages"][:2]
                ],
                "naming_readiness": ranked[0]["naming_readiness"] if ranked else "低",
            }
        )
    return {"profile_count": len(profiles), "profiles": profiles}


def explain_x_positioning(positioning_name: str) -> str:
    if positioning_name == "清洁帮手":
        return "这类人默认接受机器先把基础地面清洁做完，但不接受它把维护和返工重新甩回给自己。"
    if positioning_name == "清洁管家":
        return "这类人期待的不是多一个清洁工具，而是把地面清洁这件事从日常注意力里删除。"
    return "这类人买的不只是清洁结果，也在买可被看见、可被讨论的科技表达与生活方式。"


def fallback_x_positioning(case: dict[str, object]) -> list[str]:
    hidden_needs = case.get("hidden_needs", []) or []
    if "身份表达" in hidden_needs:
        return ["科技表达信号", "基础代劳信号"]
    if "真正托管" in hidden_needs:
        return ["低介入托管信号", "基础代劳信号"]
    return ["基础代劳信号"]


def build_x_observed_positionings(
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
    x_case_signal_profiles: dict[str, object],
) -> dict[str, object]:
    cases = {case["case_title"]: case for case in case_concept_slots.get("cases", []) if case.get("series_code") == "X"}  # type: ignore[index]
    profiles = x_case_signal_profiles.get("profiles", []) or []
    rows: list[dict[str, object]] = []
    for signal_name in X_ROLE_LABEL_SCHEMA:
        schema = x_signal_schema(signal_name)
        dominant_profiles = [
            profile
            for profile in profiles
            if profile.get("dominant_signals") and profile["dominant_signals"][0] == signal_name
        ]
        if not dominant_profiles:
            continue
        ordered_profiles = sorted(
            dominant_profiles,
            key=lambda profile: (
                -int(profile.get("signal_scores", {}).get(signal_name, {}).get("score", 0)),
                -int(profile.get("signal_scores", {}).get(signal_name, {}).get("high_quality_support_count", 0)),
                str(profile.get("case_title", "")),
            ),
        )
        support_case_titles = [str(profile["case_title"]) for profile in ordered_profiles]
        support_case_count = len(support_case_titles)
        high_quality_passage_count = sum(
            int(profile.get("signal_scores", {}).get(signal_name, {}).get("high_quality_support_count", 0))
            for profile in ordered_profiles
        )
        hallmark_signals = dedupe_preserve_order(
            [
                str(keyword)
                for profile in ordered_profiles
                for keyword in profile.get("signal_scores", {}).get(signal_name, {}).get("hallmark_signals", [])
            ]
        )
        representative_quotes = [
            row["passage_text"]
            for profile in ordered_profiles[:3]
            for row in pick_passages(
                semantic_passages,
                case_titles=[str(profile["case_title"])],
                roles=list(schema["preferred_roles"]),  # type: ignore[arg-type]
                keywords=list(schema["keywords"]),  # type: ignore[arg-type]
                limit=2,
            )
        ]
        display_label = choose_x_role_label(signal_name, hallmark_signals, representative_quotes)
        hallmark_group_count = len(hallmark_signals[:3])
        if signal_name == "科技表达信号":
            positioning_level = "main_positioning" if support_case_count >= 3 and high_quality_passage_count >= 3 and hallmark_group_count >= 2 else "weak_signal"
        else:
            positioning_level = "main_positioning" if support_case_count >= 2 and high_quality_passage_count >= 2 and hallmark_group_count >= 1 else "weak_signal"
        jtbd_candidates = [default_x_jtbd_for_anchor(str(schema["canonical_anchor"]))]
        rows.append(
            {
                "signal_name": signal_name,
                "display_label": display_label,
                "canonical_anchor": schema["canonical_anchor"],
                "positioning_level": positioning_level,
                "support_case_count": support_case_count,
                "support_case_titles": support_case_titles,
                "high_quality_passage_count": high_quality_passage_count,
                "hallmark_signals": hallmark_signals[:4],
                "representative_cases": support_case_titles[:4],
                "jtbd_candidates": jtbd_candidates,
                "label_candidates": list(schema["label_candidates"]),  # type: ignore[index]
                "why_this_label": build_x_label_reason(display_label, str(schema["canonical_anchor"]), hallmark_signals[:4], positioning_level),
                "why_not_other_labels": build_x_not_other_reason(str(schema["canonical_anchor"])),
                "representative_quotes": dedupe_preserve_order(representative_quotes)[:3],
            }
        )
    rows.sort(key=lambda row: (row["positioning_level"] != "main_positioning", -int(row["support_case_count"]), str(row["display_label"])))
    main_rows = [row for row in rows if row["positioning_level"] == "main_positioning"]
    weak_rows = [row for row in rows if row["positioning_level"] == "weak_signal"]
    return {
        "positioning_count": len(rows),
        "main_positionings": main_rows,
        "weak_signal_clusters": weak_rows,
        "positionings": rows,
    }


def fallback_t_jtbd(case: dict[str, object]) -> list[str]:
    combined = " ".join(
        [case.get("case_title", "")]
        + list(case.get("family_and_home", []) or [])
        + list(case.get("life_focus", []) or [])
        + list(case.get("pain_points", []) or [])
    )
    if any(keyword in combined for keyword in ("妈妈", "爸爸", "孩子", "家庭", "顶梁柱", "秩序")):
        return ["家庭投入"]
    if any(keyword in combined for keyword in ("独立", "个人", "单身", "小姐姐", "艺术", "自己")):
        return ["个人优先"]
    return ["平衡共处"]


def build_x_series_concept_map(case_concept_slots: dict[str, object]) -> dict[str, object]:
    semantic_passages = build_semantic_passages(case_concept_slots)
    x_case_signal_profiles = build_x_case_signal_profiles(case_concept_slots, semantic_passages)
    x_observed_positionings = build_x_observed_positionings(case_concept_slots, semantic_passages, x_case_signal_profiles)
    cases = {
        case["case_title"]: case
        for case in case_concept_slots.get("cases", [])
        if case.get("series_code") == "X"
    }  # type: ignore[index]
    positioning_rows: list[dict[str, object]] = []
    for positioning in x_observed_positionings.get("positionings", []) or []:
        matched = [cases[case_title] for case_title in positioning.get("support_case_titles", []) if case_title in cases]
        positioning_name = str(positioning["display_label"])
        canonical_anchor = str(positioning["canonical_anchor"])
        case_cards = []
        for case in matched[:4]:
            jtbd_candidates = top_labels(
                " ".join(
                    [case.get("case_title", "")]
                    + list(case.get("purchase_trigger", []) or [])
                    + list(case.get("expected_needs", []) or [])
                    + list(case.get("concept_ideas", []) or [])
                ),
                X_JTBD_RULES,
                limit=2,
            )
            case_cards.append(
                {
                    "case_title": case["case_title"],
                    "persona_summary": case.get("persona_summary", case["case_title"]),
                    "cleaning_attitude": (case.get("cleaning_attitude") or ["-"])[0],
                    "purchase_decision": (case.get("purchase_decision") or ["-"])[0],
                    "pain_point": (case.get("pain_points") or ["-"])[0],
                    "expected_need": (case.get("expected_needs") or ["-"])[0],
                    "jtbd": jtbd_candidates[0] if jtbd_candidates else (case.get("x_positioning_candidates") or [positioning_name])[0],
                }
            )
        jtbd_signals: list[str] = []
        for case in matched[:4]:
            jtbd_signals.extend(top_labels(" ".join(case.get("source_texts", {}).values()), X_JTBD_RULES, limit=2))  # type: ignore[arg-type]
        positioning_rows.append(
            {
                "positioning_name": positioning_name,
                "canonical_anchor": canonical_anchor,
                "positioning_level": positioning["positioning_level"],
                "definition": positioning["why_this_label"],
                "attribute_type": PPT_CONCEPT_SCHEMA["X"]["positioning_triptych"][canonical_anchor]["attribute_type"],
                "case_count": len(matched),
                "why_this_positioning": positioning["why_this_label"],
                "representative_cases": [case["case_title"] for case in matched[:4]],
                "representative_personas": [case["case_title"] for case in matched[:4]],
                "cleaning_attitude_and_habit": gather_case_field_samples(matched, "cleaning_attitude"),
                "purchase_style": [
                    {
                        "case_title": case["case_title"],
                        "trigger": (case.get("purchase_trigger") or ["-"])[0],
                        "decision_factors": case.get("purchase_decision") or ["-"],
                    }
                    for case in matched[:4]
                ],
                "pain_points": gather_case_field_samples(matched, "pain_points"),
                "expected_needs": gather_case_field_samples(matched, "expected_needs"),
                "core_demand": gather_case_field_samples(matched, "core_demand"),
                "jtbd": dedupe_preserve_order(jtbd_signals)[:4],
                "product_todo": gather_case_field_samples(matched, "concept_ideas"),
                "case_cards": case_cards,
                "ppt_mapping": canonical_anchor,
            }
        )
    return {"series_code": "X", "positioning_rows": positioning_rows}


def build_t_series_concept_map(
    case_concept_slots: dict[str, object],
    survey_concept_segments: dict[str, object],
) -> dict[str, object]:
    cases = [case for case in case_concept_slots.get("cases", []) if case.get("series_code") == "T"]  # type: ignore[index]
    segments = [segment for segment in survey_concept_segments.get("segments", []) if infer_series_code(segment.get("inferred_spu_id"), segment.get("wave_name", "")) == "T"]  # type: ignore[index]

    people_slices: dict[str, list[dict[str, object]]] = {"他们是谁": [], "她们是谁": []}
    for group_name in ["他们是谁", "她们是谁"]:
        matched = [case for case in cases if case.get("gender_bucket") == group_name]
        for case in matched[:4]:
            people_slices[group_name].append(
                {
                    "case_title": case["case_title"],
                    "persona_summary": case["case_title"],
                    "family_and_home": (case.get("family_and_home") or ["-"])[:2],
                    "life_focus": (case.get("life_focus") or ["-"])[:2],
                    "cleaning_habit": (case.get("cleaning_habit") or ["-"])[:2],
                    "purchase_path": (case.get("purchase_path") or ["-"])[:2],
                    "representative_quote": (case.get("pain_points") or case.get("expected_needs") or ["-"])[0],
                }
            )

    difference_dimensions: list[dict[str, object]] = []
    dimension_explanations = {
        "生命阶段与角色冲突": "同样是买扫地机，有的人是在新婚、育儿或角色转变后被迫接住新增家务，有的人则是在生活阶段变化里重新分配自己的精力。",
        "自我认同与思维模式": "用户对清洁的要求，背后其实是对自己如何生活、如何证明自己、如何维持秩序的不同理解。",
        "家庭结构与权力动态": "谁承担家务、谁做购买决策、谁负责兜底，会直接改变对清洁标准、维护频次和预算的容忍边界。",
    }
    for dimension_name, keywords in T_DIFFERENCE_DIMENSION_RULES:
        matched = [case for case in cases if dimension_name in (case.get("t_difference_dimensions") or []) or contains_any(" ".join(case.get("source_texts", {}).values()), keywords)]
        supporting_quotes = gather_case_field_samples(matched, "family_and_home", limit=3) + gather_case_field_samples(matched, "life_focus", limit=3)
        if not matched and dimension_name in dimension_explanations:
            matched = cases[:2]
        difference_dimensions.append(
            {
                "dimension": dimension_name,
                "explanation": dimension_explanations.get(dimension_name, "这是一条当前能解释 T 系列差异判断的核心维度。"),
                "representative_cases": [case["case_title"] for case in matched[:4]],
                "supporting_quotes": dedupe_preserve_order(supporting_quotes)[:4],
            }
        )

    jtbd_clusters: dict[str, dict[str, object]] = {}
    jtbd_defaults = {
        "个人优先": {
            "result_requirement": "先把地面基础清洁稳定完成，让清洁这件事不再抢占自己的时间和精力。",
            "unacceptable_cost": "不能为了机器再做额外维护、反复返工或增加新的待办。",
        },
        "平衡共处": {
            "result_requirement": "在家庭成员并行生活的状态下稳定运转，不打扰、不制造新的冲突。",
            "unacceptable_cost": "不能影响家人作息，也不能把家务重新变成情绪摩擦。",
        },
        "家庭投入": {
            "result_requirement": "把家庭标准下的清洁结果稳定做出来，并尽量减少检查和补救。",
            "unacceptable_cost": "不能清洁不稳定、不能高频返工，更不能在关键区域掉链子。",
        },
    }
    for label in ["个人优先", "平衡共处", "家庭投入"]:
        matched = []
        for case in cases:
            candidates = case.get("t_jtbd_candidates") or fallback_t_jtbd(case)
            if label in candidates:
                matched.append(case)
        jtbd_clusters[label] = {
            "representative_cases": [case["case_title"] for case in matched[:4]],
            "typical_scenarios": gather_case_field_samples(matched, "cleaning_habit", limit=4),
            "result_requirement": jtbd_defaults[label]["result_requirement"],
            "unacceptable_cost": jtbd_defaults[label]["unacceptable_cost"],
        }

    value_definition = {
        label: [case["case_title"] for case in cases if label in (case.get("value_definition_candidates") or [])][:4]
        for label, _ in VALUE_DEFINITION_RULES
    }
    if not any(value_definition.values()):
        value_definition = {
            "替代": [case["case_title"] for case in cases[:2]],
            "分担 / 保障": [case["case_title"] for case in cases[2:4]],
        }

    pain_theme_rules = {
        "噪音": ("噪音", "异味", "打扰"),
        "越障": ("越障", "门槛", "台阶", "过不去"),
        "防缠": ("缠", "头发", "猫毛", "滚刷"),
        "清洁死角": ("边角", "死角", "窄缝", "桌椅腿"),
        "稳定运行": ("卡困", "回充", "故障", "返工"),
        "控制感": ("检查", "看得见", "确认", "虚拟墙", "分区"),
    }
    pain_and_needs: list[dict[str, object]] = []
    for theme_name, keywords in pain_theme_rules.items():
        matched_cases = [
            case for case in cases if any(text_matches_any(sample, keywords) for sample in (case.get("pain_points") or []) + (case.get("expected_needs") or []))
        ]
        if not matched_cases:
            continue
        pain_and_needs.append(
            {
                "theme_name": theme_name,
                "representative_cases": [case["case_title"] for case in matched_cases[:4]],
                "pain_points": gather_case_field_samples(matched_cases, "pain_points", limit=4),
                "expected_needs": gather_case_field_samples(matched_cases, "expected_needs", limit=4),
            }
        )

    series_strategy_gap = [
        "T 系列首先是把清洁结果稳定做出来，而不是先讲黑科技感知。",
        "T 系列对智能的要求更接近“不犯傻的自动化”，不能因为功能更复杂反而增加返工与维护。",
        "T 系列更容易被生命阶段、家庭分工和谁承担家务压力所驱动，策略上要先讲谁在兜底、机器能替掉什么。",
    ]
    if segments:
        for segment in segments[:3]:
            if segment.get("difference_reason"):
                series_strategy_gap.append("；".join(segment["difference_reason"][:2]))

    return {
        "series_code": "T",
        "people_slices": people_slices,
        "difference_dimensions": difference_dimensions,
        "jtbd_clusters": jtbd_clusters,
        "value_definition": value_definition,
        "pain_and_needs": pain_and_needs,
        "series_strategy_gap": dedupe_preserve_order(series_strategy_gap)[:6],
    }


def build_brand_mindshare_map(case_concept_slots: dict[str, object]) -> dict[str, object]:
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    brand_map: dict[str, dict[str, object]] = {}
    brand_defaults = {
        "科沃斯": "老牌大厂，品牌认知高，但口碑会随着具体产品体验明显分化。",
        "石头": "专业、主流、参数强，是很多用户天然会拉来对比的标杆品牌。",
        "追觅": "高端感和黑科技表达更强，容易吸引愿意为新技术溢价的人。",
        "云鲸": "拖地和水渍控制心智突出，但用户会继续比较其长期稳定性与售后。",
        "大疆": "跨界科技感强，用户对它的智能与避障期待高，但担心扫地机专业积累不足。",
        "小米": "高性价比、入门和基础功能心智强，但高端用户容易质疑其专业性。",
    }

    def brand_mentions(text: str) -> list[str]:
        return [candidate for candidate in BRAND_LABELS if candidate in text]

    def is_brand_header_line(text: str) -> bool:
        return any(token in text for token in BRAND_HEADER_HINTS)

    def shorten_brand_line(text: str, brand: str) -> str:
        cleaned = normalize_passage_text(text) or text.strip()
        cleaned = re.sub(rf"^\**{re.escape(brand)}\s*[：:|/]\s*", "", cleaned).strip()
        if not cleaned:
            return ""
        if any(other in cleaned for other in BRAND_LABELS if other != brand):
            return ""
        sentence_parts = [part.strip(" -/") for part in re.split(r"[；。]", cleaned) if part.strip(" -/")]
        target = next(
            (
                part
                for part in sentence_parts
                if any(token in part for token in BRAND_POSITIVE_HINTS + BRAND_NEGATIVE_HINTS)
            ),
            sentence_parts[0] if sentence_parts else cleaned,
        )
        clause_parts = [part.strip(" -/") for part in re.split(r"[，,]", target) if part.strip(" -/")]
        kept: list[str] = []
        for part in clause_parts:
            if any(other in part for other in BRAND_LABELS if other != brand):
                continue
            kept.append(part)
            joined = "，".join(kept)
            if len(normalize_text(joined)) >= 26 or len(kept) >= 2:
                break
        summary = "，".join(kept) if kept else target.strip(" -/")
        summary = re.sub(r"^(?:该品牌|这个品牌|用户认为)", "", summary).strip("，,；;：: ")
        if not summary:
            return ""
        if len(summary) > 36:
            summary = summary[:36].rstrip("，,；; ")
        if not summary.endswith(("。", "！", "？")):
            summary += "。"
        return f"{brand}：{summary}"

    def extract_brand_specific_lines(case: dict[str, object], brand: str) -> list[str]:
        lines: list[str] = []
        for raw in case.get("brand_evaluation", []):
            text = str(raw).strip()
            if not text:
                continue
            if is_brand_header_line(text):
                continue
            mentions = brand_mentions(text)
            if brand not in mentions:
                continue
            if len(set(mentions)) > 1:
                continue
            if text.startswith(f"{brand}：") or text.startswith(f"{brand}:") or text.startswith(f"{brand} |") or text.startswith(f"**{brand}：**") or f" {brand} |" in text:
                lines.append(text)
                continue
            if len(set(mentions)) == 1 and any(token in text for token in BRAND_POSITIVE_HINTS + BRAND_NEGATIVE_HINTS):
                lines.append(text)
        return dedupe_preserve_order(lines)

    def classify_brand_line(line: str) -> str:
        explicit_reject = any(token in line for token in ("靠后", "放弃", "排除", "不考虑", "劝退", "直接排除"))
        explicit_choose = any(token in line for token in ("第一", "最终购买", "推荐", "标杆", "放心", "匹配"))
        if explicit_reject:
            return "reject"
        if explicit_choose:
            return "choose"
        if any(token in line for token in BRAND_NEGATIVE_HINTS):
            return "reject"
        if any(token in line for token in BRAND_POSITIVE_HINTS):
            return "choose"
        return "neutral"

    for brand in BRAND_LABELS:
        choose_lines: list[str] = []
        reject_lines: list[str] = []
        neutral_lines: list[str] = []
        who_prefers: list[str] = []
        who_rejects: list[str] = []
        for case in cases:
            brand_lines = extract_brand_specific_lines(case, brand)
            if not brand_lines:
                continue
            line_types = {classify_brand_line(line) for line in brand_lines}
            if "choose" in line_types and case["case_title"] not in who_prefers:
                who_prefers.append(case["case_title"])
            if "reject" in line_types and case["case_title"] not in who_rejects:
                who_rejects.append(case["case_title"])
            for line in brand_lines:
                label = classify_brand_line(line)
                short_line = shorten_brand_line(line, brand)
                if not short_line:
                    continue
                if label == "choose":
                    choose_lines.append(short_line)
                elif label == "reject":
                    reject_lines.append(short_line)
                else:
                    neutral_lines.append(short_line)
        if not choose_lines and not reject_lines and not neutral_lines:
            continue
        trust_reason = dedupe_preserve_order(choose_lines or neutral_lines)[:3]
        rejection_reason = dedupe_preserve_order(reject_lines)[:3]
        representative_quotes = dedupe_preserve_order((choose_lines + reject_lines + neutral_lines))[:3]
        brand_map[brand] = {
            "core_label": brand_defaults.get(brand, f"{brand} 在用户心里有稳定但分化的品牌心智。"),
            "trust_reason": trust_reason,
            "rejection_reason": rejection_reason,
            "who_prefers_it": who_prefers[:3],
            "who_rejects_it": who_rejects[:3],
            "representative_quotes": representative_quotes,
            "why_choose": trust_reason,
            "why_reject": rejection_reason,
            "quote_refs": representative_quotes,
        }
    return {"brand_count": len(brand_map), "brands": brand_map}


def build_idea_pool_clusters(case_concept_slots: dict[str, object]) -> dict[str, object]:
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    clusters: list[dict[str, object]] = []
    for cluster_name, keywords in IDEA_CLUSTER_RULES.items():
        examples = []
        for case in cases:
            for text in case.get("concept_ideas", []):
                if any(keyword in text for keyword in keywords):
                    examples.append(
                        {
                            "case_title": case["case_title"],
                            "idea_text": text,
                            "series_code": case.get("series_code"),
                            "positioning_hint": (case.get("x_positioning_candidates") or case.get("t_jtbd_candidates") or ["-"])[0],
                        }
                    )
        if not examples:
            continue
        which_positioning = dedupe_preserve_order([str(example["positioning_hint"]) for example in examples])[:2]
        now_or_later = "现在就该做" if cluster_name in {"顽固污渍", "地毯", "低介入", "窄缝与门后"} else "更适合中长期布局"
        clusters.append(
            {
                "theme_name": cluster_name,
                "idea_examples": examples[:6],
                "why_user_wants_it": f"用户希望在 `{cluster_name}` 相关场景中进一步减少介入、减少返工，或者把当前做不好的区域真正交给机器。",
                "which_positioning_it_belongs_to": " / ".join(which_positioning) if which_positioning else "待补充",
                "is_now_or_later": now_or_later,
            }
        )
    return {"cluster_count": len(clusters), "clusters": clusters}


def score_text_against_keywords(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if contains_any(text, (keyword,)))


def rank_x_positionings_for_case(case: dict[str, object]) -> list[str]:
    semantic_passages = build_semantic_passages({"cases": [case]})
    ranked = rank_x_signal_scores(case, semantic_passages)
    anchors = [str(row["canonical_anchor"]) for row in ranked if int(row["score"]) > 0]
    if not anchors:
        fallback = fallback_x_positioning(case)
        anchors = [str(x_signal_schema(signal_name)["canonical_anchor"]) for signal_name in fallback]
    return dedupe_preserve_order(anchors)[:3]


def choose_case_persona(case: dict[str, object], semantic_passages: dict[str, object]) -> str:
    case_title = case["case_title"]
    notes = [normalize_passage_text(str(note)) for note in (case.get("persona_notes") or [])]
    notes = [note for note in notes if note]
    if notes:
        return notes[0]
    passages = pick_passages(
        semantic_passages,
        case_titles=[case_title],
        roles=["人物定义"],
        keywords=["一句话", "家庭", "生活", "顶梁柱", "女强人", "妈妈", "爸爸", "精致", "单身", "独居"],
        limit=1,
    )
    if passages:
        return passages[0]["passage_text"]
    fallback_fields = [case.get("external_identity") or [], case.get("life_focus") or []]
    for field in fallback_fields:
        normalized = [normalize_passage_text(str(item)) for item in field]
        normalized = [item for item in normalized if item]
        if normalized:
            return normalized[0]
    return case_title


def choose_case_quote(case_title: str, semantic_passages: dict[str, object], roles: list[str], keywords: list[str], fallback: str) -> str:
    passages = pick_passages(semantic_passages, case_titles=[case_title], roles=roles, keywords=keywords, limit=1)
    if passages:
        return passages[0]["passage_text"]
    return fallback


def default_x_package_definition(display_label: str, canonical_anchor: str, positioning_level: str) -> str:
    if canonical_anchor == "清洁帮手":
        text = f"把它当成一个能稳定完成基础清洁、但别额外添乱的 `{display_label}`。"
    elif canonical_anchor == "清洁管家":
        text = f"期待它像 `{display_label}` 一样少操心、少返工、主动补位。"
    else:
        text = f"买的不只是清洁结果，也在买 `{display_label}` 所代表的科技感、设计感和悦己表达。"
    if positioning_level == "weak_signal":
        text += " 当前它更像方向性表达信号，而不是稳定主定位。"
    return text


def fallback_package_samples(
    selected_cases: list[dict[str, object]],
    *,
    field_names: list[str],
    limit: int,
) -> list[str]:
    samples: list[str] = []
    for case in selected_cases:
        for field_name in field_names:
            value = case.get(field_name, [])
            if isinstance(value, list):
                samples.extend(str(item) for item in value if str(item).strip())
    return dedupe_preserve_order(samples)[:limit]


def build_x_positioning_packages(
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
    x_case_signal_profiles: dict[str, object] | None = None,
    x_observed_positionings: dict[str, object] | None = None,
) -> dict[str, object]:
    cases = {
        case["case_title"]: case
        for case in case_concept_slots.get("cases", [])
        if case.get("series_code") == "X"
    }  # type: ignore[index]
    if x_case_signal_profiles is None:
        x_case_signal_profiles = build_x_case_signal_profiles(case_concept_slots, semantic_passages)
    if x_observed_positionings is None:
        x_observed_positionings = build_x_observed_positionings(case_concept_slots, semantic_passages, x_case_signal_profiles)
    packages: list[dict[str, object]] = []
    for positioning in x_observed_positionings.get("positionings", []) or []:
        label = str(positioning["display_label"])
        canonical_anchor = str(positioning["canonical_anchor"])
        selected = [cases[case_title] for case_title in positioning.get("support_case_titles", []) if case_title in cases][:3]
        representative_users = [
            {
                "case_title": case["case_title"],
                "persona_summary": choose_case_persona(case, semantic_passages),
            }
            for case in selected
        ]
        case_titles = [case["case_title"] for case in selected]
        schema = x_signal_schema(str(positioning["signal_name"]))
        attitude_pattern = [
            row["passage_text"]
            for row in pick_passages(
                semantic_passages,
                case_titles=case_titles,
                roles=["清洁态度", "痛点", "期待", "隐性需求"],
                keywords=list(schema["keywords"]) + list(schema["hallmark_keywords"]),  # type: ignore[arg-type]
                limit=4,
            )
        ]
        if not attitude_pattern:
            attitude_pattern = fallback_package_samples(
                selected,
                field_names=["cleaning_attitude", "pain_points", "expected_needs"],
                limit=3,
            )
        buying_logic = [
            row["passage_text"]
            for row in pick_passages(
                semantic_passages,
                case_titles=case_titles,
                roles=["购买决策", "品牌认知", "人物定义"],
                keywords=list(schema["keywords"]) + ["朋友", "抖音", "免维护", "解放双手", "尺寸", "售后"],  # type: ignore[list-item]
                limit=4,
            )
        ]
        if not buying_logic:
            buying_logic = fallback_package_samples(
                selected,
                field_names=["purchase_trigger", "purchase_decision", "brand_evaluation"],
                limit=3,
            )
        pain_need = [row["passage_text"] for row in pick_passages(semantic_passages, case_titles=case_titles, roles=["痛点", "期待"], keywords=list(schema["keywords"]) + ["维护", "边角", "水渍", "智能", "避障"], limit=4)]
        if not pain_need:
            pain_need = fallback_package_samples(
                selected,
                field_names=["pain_points", "expected_needs"],
                limit=4,
            )
        representative_quotes = list(positioning.get("representative_quotes", []))[:2]
        if not representative_quotes:
            representative_quotes = [row["passage_text"] for row in pick_passages(semantic_passages, case_titles=case_titles, roles=["清洁态度", "期待", "购买决策", "品牌认知"], keywords=list(schema["hallmark_keywords"]), limit=2)]  # type: ignore[arg-type]
        jtbd = positioning.get("jtbd_candidates", [default_x_jtbd_for_anchor(canonical_anchor)])[0]
        product_todo = [row["passage_text"] for row in pick_passages(semantic_passages, case_titles=case_titles, roles=["金点子", "期待"], keywords=["机械臂", "窄缝", "油污", "主动", "宠物", "联动", "立面", "设计"], limit=3)]
        if not product_todo:
            product_todo = fallback_package_samples(
                selected,
                field_names=["concept_ideas", "expected_needs"],
                limit=3,
            )
        packages.append(
            {
                "positioning_name": label,
                "canonical_anchor": canonical_anchor,
                "positioning_level": positioning["positioning_level"],
                "label_candidates": positioning.get("label_candidates", []),
                "naming_reason": positioning["why_this_label"],
                "one_line_definition": default_x_package_definition(label, canonical_anchor, str(positioning["positioning_level"])),
                "representative_users": representative_users,
                "support_case_titles": positioning.get("support_case_titles", []),
                "attitude_pattern": attitude_pattern,
                "buying_logic": buying_logic,
                "pain_need": pain_need,
                "jtbd": jtbd,
                "product_todo": product_todo,
                "why_not_other_two": positioning["why_not_other_labels"],
                "representative_quotes": representative_quotes,
            }
        )
    return {"package_count": len(packages), "packages": packages}


def x_positioning_case_titles(
    case_concept_slots: dict[str, object],
    positioning_name: str,
    x_observed_positionings: dict[str, object] | None = None,
) -> list[str]:
    if x_observed_positionings is not None:
        for row in x_observed_positionings.get("positionings", []) or []:
            if row.get("display_label") == positioning_name:
                return dedupe_preserve_order([str(title) for title in row.get("support_case_titles", [])])
    cases = [case for case in case_concept_slots.get("cases", []) if case.get("series_code") == "X"]  # type: ignore[index]
    titles: list[str] = []
    for case in cases:
        ranked = rank_x_positionings_for_case(case)
        if positioning_name in ranked:
            titles.append(case["case_title"])
    return dedupe_preserve_order(titles)


def build_x_positioning_confidence_stats(
    *,
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
    x_positioning_packages: dict[str, object],
    x_observed_positionings: dict[str, object] | None = None,
) -> dict[str, object]:
    package_lookup = {row["positioning_name"]: row for row in x_positioning_packages.get("packages", []) or []}
    rows: list[dict[str, object]] = []
    observed_rows = (x_observed_positionings or {}).get("positionings", []) or list(package_lookup.values())
    for observed in observed_rows:
        positioning_name = observed.get("display_label", observed.get("positioning_name"))
        canonical_anchor = observed.get("canonical_anchor", package_lookup.get(positioning_name, {}).get("canonical_anchor", positioning_name))
        case_titles = x_positioning_case_titles(case_concept_slots, str(positioning_name), x_observed_positionings)
        keywords = concept_keywords(str(canonical_anchor), "x_positioning")
        passages = count_passages_for_concept(
            semantic_passages,
            case_titles=case_titles,
            roles=["人物定义", "清洁态度", "购买决策", "痛点", "期待"],
            keywords=keywords,
            min_quality=0.6,
        )
        high_quality = [row for row in passages if float(row["quality_score"]) >= 0.75]
        package = package_lookup.get(str(positioning_name), {})
        buying_logic_uniqueness = len(dedupe_preserve_order(package.get("buying_logic", [])))
        pain_need_uniqueness = len(dedupe_preserve_order(package.get("pain_need", [])))
        cross_case_repeat_count = max(0, len(case_titles) - 1)
        confidence_level = summarize_concept_confidence(
            support_case_count=len(case_titles),
            high_quality_passage_count=len(high_quality),
            cross_case_repeat_count=cross_case_repeat_count,
            extra_strength=(1 if buying_logic_uniqueness >= 2 else 0) + (1 if pain_need_uniqueness >= 2 else 0),
        )
        confidence_level = cap_confidence_for_weak_signal(str(observed.get("positioning_level", "main_positioning")), confidence_level)
        rows.append(
            {
                "positioning_name": positioning_name,
                "display_label": positioning_name,
                "canonical_anchor": canonical_anchor,
                "positioning_level": observed.get("positioning_level", package.get("positioning_level", "main_positioning")),
                "support_case_count": len(case_titles),
                "high_quality_passage_count": len(high_quality),
                "cross_case_repeat_count": cross_case_repeat_count,
                "buying_logic_uniqueness": buying_logic_uniqueness,
                "pain_need_uniqueness": pain_need_uniqueness,
                "confidence_level": confidence_level,
            }
        )
    return {"row_count": len(rows), "rows": rows}


def build_x_jtbd_confidence_stats(
    *,
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
) -> dict[str, object]:
    cases = [case for case in case_concept_slots.get("cases", []) if case.get("series_code") == "X"]  # type: ignore[index]
    rows: list[dict[str, object]] = []
    for jtbd_name, keywords in X_JTBD_RULES:
        matched_cases = [
            case for case in cases
            if jtbd_name in top_labels(" ".join(case.get("source_texts", {}).values()), X_JTBD_RULES, limit=3)  # type: ignore[arg-type]
            or contains_any(" ".join(case.get("expected_needs", []) + case.get("concept_ideas", [])), keywords)
        ]
        case_titles = dedupe_preserve_order([case["case_title"] for case in matched_cases])
        passages = count_passages_for_concept(
            semantic_passages,
            case_titles=case_titles,
            roles=["人物定义", "清洁态度", "购买决策", "痛点", "期待", "金点子"],
            keywords=keywords,
            min_quality=0.6,
        )
        high_quality = [row for row in passages if float(row["quality_score"]) >= 0.75]
        confidence_level = summarize_concept_confidence(
            support_case_count=len(case_titles),
            high_quality_passage_count=len(high_quality),
            cross_case_repeat_count=max(0, len(case_titles) - 1),
            extra_strength=1 if len(case_titles) >= 2 else 0,
        )
        rows.append(
            {
                "jtbd_name": jtbd_name,
                "support_case_count": len(case_titles),
                "high_quality_passage_count": len(high_quality),
                "cross_case_repeat_count": max(0, len(case_titles) - 1),
                "confidence_level": confidence_level,
            }
        )
    return {"row_count": len(rows), "rows": rows}


def build_x_positioning_impact_stats(
    *,
    case_concept_slots: dict[str, object],
    x_positioning_packages: dict[str, object],
    x_observed_positionings: dict[str, object] | None = None,
    voc_problem_packages: dict[str, object],
    survey_concept_segments: dict[str, object],
    concept_pain_need_map: dict[str, object],
    cross_source_interpretation: dict[str, object],
    strategy_translation: dict[str, object],
    brand_mindshare_judgments: dict[str, object],
    idea_cluster_judgments: dict[str, object],
) -> dict[str, object]:
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    package_lookup = {row["positioning_name"]: row for row in x_positioning_packages.get("packages", []) or []}
    survey_rows = survey_concept_segments.get("segments", []) or []
    voc_rows = voc_problem_packages.get("packages", []) or []
    pain_rows = concept_pain_need_map.get("rows", []) or []
    priority_buckets = strategy_translation.get("priority_buckets", {}) or {}
    brand_rows = brand_mindshare_judgments.get("judgments", []) or []
    idea_rows = idea_cluster_judgments.get("judgments", []) or []
    rows: list[dict[str, object]] = []

    observed_rows = (x_observed_positionings or {}).get("positionings", []) or []
    if not observed_rows:
        observed_rows = [
            {
                "display_label": row["positioning_name"],
                "canonical_anchor": row.get("canonical_anchor", row["positioning_name"]),
                "positioning_level": row.get("positioning_level", "main_positioning"),
            }
            for row in x_positioning_packages.get("packages", []) or []
        ]

    for observed in observed_rows:
        positioning_name = str(observed["display_label"])
        canonical_anchor = str(observed.get("canonical_anchor", positioning_name))
        case_titles = x_positioning_case_titles(case_concept_slots, positioning_name, x_observed_positionings)
        related_cases = [case for case in cases if case["case_title"] in case_titles]
        related_spu_ids = dedupe_preserve_order([str(case.get("inferred_spu_id")) for case in related_cases if case.get("inferred_spu_id")])
        package = package_lookup.get(positioning_name, {})
        linked_pain_themes = [row["pain_theme"] for row in pain_rows if row["concept_id"] == positioning_name]
        linked_pain_themes = dedupe_preserve_order(linked_pain_themes)
        if not linked_pain_themes:
            linked_pain_themes = detect_pain_themes(list(package.get("pain_need", [])) + list(package.get("product_todo", [])))
        if not linked_pain_themes:
            if canonical_anchor == "清洁帮手":
                linked_pain_themes = ["边角与覆盖率", "清洁效果与水痕污渍", "维护与基站操作"]
            elif canonical_anchor == "清洁管家":
                linked_pain_themes = ["智能/App/语音/地图", "避障越障与卡困", "维护与基站操作"]
            else:
                linked_pain_themes = ["智能/App/语音/地图"]

        linked_voc_packages = [
            row for row in voc_rows
            if (
                (related_spu_ids and row.get("spu_id") in related_spu_ids)
                or (not related_spu_ids and infer_series_code(row.get("spu_id"), row.get("package_name", "")) == "X")
            )
            and set(voc_package_pain_themes(row)).intersection(linked_pain_themes)
        ]

        if canonical_anchor == "社交名片":
            linked_survey_segments = [
                row for row in survey_rows
                if infer_series_code(row.get("inferred_spu_id"), row.get("wave_name", "")) == "X"
                and text_matches_any(json.dumps(row, ensure_ascii=False), ("科技", "表达", "新技术", "智能体", "想尝试新的技术"))
            ]
        else:
            preferred_segment = "要求稳定托管" if canonical_anchor == "清洁管家" else "接受 80%"
            linked_survey_segments = [
                row for row in survey_rows
                if infer_series_code(row.get("inferred_spu_id"), row.get("wave_name", "")) == "X"
                and row.get("segment_name") == preferred_segment
            ]

        linked_priority_bucket_count = sum(1 for themes in priority_buckets.values() if any(theme in themes for theme in linked_pain_themes))
        linked_trust_damage_count = len({row.get("trust_impact") for row in linked_voc_packages if row.get("trust_impact")})
        linked_brand_judgment_strength = sum(
            1
            for row in brand_rows
            if set(row.get("who_chooses", [])).intersection(case_titles)
        )
        linked_idea_cluster_strength = sum(
            1
            for row in idea_rows
            if set(row.get("who_needs_it", [])).intersection(case_titles)
        )
        impact_score = linked_brand_judgment_strength + linked_idea_cluster_strength
        if canonical_anchor == "社交名片":
            expression_support = linked_brand_judgment_strength + linked_idea_cluster_strength + len(linked_survey_segments)
            if expression_support >= 5:
                impact_level = "高"
            elif expression_support >= 3:
                impact_level = "中"
            else:
                impact_level = "低"
        else:
            impact_level = summarize_impact_level(
                linked_pain_theme_count=len(linked_pain_themes),
                linked_voc_package_strength=len(linked_voc_packages) + impact_score,
                linked_survey_segment_strength=len(linked_survey_segments),
                linked_priority_bucket_count=linked_priority_bucket_count,
                linked_trust_damage_count=linked_trust_damage_count,
            )
        impact_level = cap_impact_for_weak_signal(str(observed.get("positioning_level", "main_positioning")), impact_level)
        rows.append(
            {
                "positioning_name": positioning_name,
                "display_label": positioning_name,
                "canonical_anchor": canonical_anchor,
                "positioning_level": observed.get("positioning_level", "main_positioning"),
                "linked_pain_theme_count": len(linked_pain_themes),
                "linked_voc_package_strength": len(linked_voc_packages),
                "linked_survey_segment_strength": len(linked_survey_segments),
                "linked_priority_bucket_count": linked_priority_bucket_count,
                "linked_trust_damage_count": linked_trust_damage_count,
                "linked_brand_judgment_strength": linked_brand_judgment_strength,
                "linked_idea_cluster_strength": linked_idea_cluster_strength,
                "impact_level": impact_level,
                "linked_pain_themes": linked_pain_themes,
            }
        )
    return {"row_count": len(rows), "rows": rows}


def build_x_jtbd_impact_stats(
    *,
    case_concept_slots: dict[str, object],
    voc_problem_packages: dict[str, object],
    survey_concept_segments: dict[str, object],
    concept_pain_need_map: dict[str, object],
    strategy_translation: dict[str, object],
    brand_mindshare_judgments: dict[str, object],
    idea_cluster_judgments: dict[str, object],
    x_observed_positionings: dict[str, object] | None = None,
) -> dict[str, object]:
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    survey_rows = survey_concept_segments.get("segments", []) or []
    voc_rows = voc_problem_packages.get("packages", []) or []
    pain_rows = concept_pain_need_map.get("rows", []) or []
    priority_buckets = strategy_translation.get("priority_buckets", {}) or {}
    brand_rows = brand_mindshare_judgments.get("judgments", []) or []
    idea_rows = idea_cluster_judgments.get("judgments", []) or []
    rows: list[dict[str, object]] = []

    anchor_to_label = {
        row.get("canonical_anchor"): row.get("display_label")
        for row in (x_observed_positionings or {}).get("positionings", []) or []
    }
    jtbd_to_positioning = {
        "地面基础清洁代劳": anchor_to_label.get("清洁帮手", "清洁帮手"),
        "整体洁净托管": anchor_to_label.get("清洁管家", "清洁管家"),
        "科技美学表达": anchor_to_label.get("社交名片", "科技玩家"),
    }
    for jtbd_name, keywords in X_JTBD_RULES:
        matched_cases = [
            case for case in cases
            if case.get("series_code") == "X"
            and (
                jtbd_name in top_labels(" ".join(case.get("source_texts", {}).values()), X_JTBD_RULES, limit=3)  # type: ignore[arg-type]
                or contains_any(" ".join(case.get("expected_needs", []) + case.get("concept_ideas", [])), keywords)
            )
        ]
        case_titles = dedupe_preserve_order([case["case_title"] for case in matched_cases])
        related_spu_ids = dedupe_preserve_order([str(case.get("inferred_spu_id")) for case in matched_cases if case.get("inferred_spu_id")])
        linked_pain_themes = [row["pain_theme"] for row in pain_rows if row["concept_id"] == jtbd_to_positioning[jtbd_name]]
        linked_pain_themes = dedupe_preserve_order(linked_pain_themes)
        if not linked_pain_themes:
            text_pool: list[str] = []
            for case in matched_cases:
                text_pool.extend(case.get("pain_points", []) or [])
                text_pool.extend(case.get("expected_needs", []) or [])
            linked_pain_themes = detect_pain_themes(text_pool)
        linked_voc_packages = [
            row for row in voc_rows
            if (
                (related_spu_ids and row.get("spu_id") in related_spu_ids)
                or (not related_spu_ids and infer_series_code(row.get("spu_id"), row.get("package_name", "")) == "X")
            )
            and set(voc_package_pain_themes(row)).intersection(linked_pain_themes)
        ]
        if jtbd_name == "科技美学表达":
            linked_survey_segments = [
                row for row in survey_rows
                if infer_series_code(row.get("inferred_spu_id"), row.get("wave_name", "")) == "X"
                and text_matches_any(json.dumps(row, ensure_ascii=False), ("科技", "表达", "新技术", "生活更智能"))
            ]
        else:
            preferred_segment = "要求稳定托管" if jtbd_name == "整体洁净托管" else "接受 80%"
            linked_survey_segments = [
                row for row in survey_rows
                if infer_series_code(row.get("inferred_spu_id"), row.get("wave_name", "")) == "X"
                and row.get("segment_name") == preferred_segment
            ]
        linked_priority_bucket_count = sum(1 for themes in priority_buckets.values() if any(theme in themes for theme in linked_pain_themes))
        linked_trust_damage_count = len({row.get("trust_impact") for row in linked_voc_packages if row.get("trust_impact")})
        linked_brand_judgment_strength = sum(1 for row in brand_rows if set(row.get("who_chooses", [])).intersection(case_titles))
        linked_idea_cluster_strength = sum(1 for row in idea_rows if set(row.get("who_needs_it", [])).intersection(case_titles))
        impact_level = summarize_impact_level(
            linked_pain_theme_count=len(linked_pain_themes),
            linked_voc_package_strength=len(linked_voc_packages) + linked_brand_judgment_strength + linked_idea_cluster_strength,
            linked_survey_segment_strength=len(linked_survey_segments),
            linked_priority_bucket_count=linked_priority_bucket_count,
            linked_trust_damage_count=linked_trust_damage_count,
        )
        rows.append(
            {
                "jtbd_name": jtbd_name,
                "linked_pain_theme_count": len(linked_pain_themes),
                "linked_voc_package_strength": len(linked_voc_packages),
                "linked_survey_segment_strength": len(linked_survey_segments),
                "linked_priority_bucket_count": linked_priority_bucket_count,
                "linked_trust_damage_count": linked_trust_damage_count,
                "linked_brand_judgment_strength": linked_brand_judgment_strength,
                "linked_idea_cluster_strength": linked_idea_cluster_strength,
                "impact_level": impact_level,
                "linked_pain_themes": linked_pain_themes,
            }
        )
    return {"row_count": len(rows), "rows": rows}


def infer_t_primary_jtbd(case: dict[str, object]) -> str:
    text_blob = " ".join(
        [case.get("case_title", "")]
        + list(case.get("persona_notes", []) or [])
        + list(case.get("cleaning_attitude", []) or [])
        + list(case.get("purchase_trigger", []) or [])
        + list(case.get("expected_needs", []) or [])
    )
    scored = [(label, score_text_against_keywords(text_blob, keywords)) for label, keywords in T_JTBD_RULES]
    scored.sort(key=lambda item: (-item[1], item[0]))
    if scored and scored[0][1] > 0:
        return scored[0][0]
    return fallback_t_jtbd(case)[0]


def build_t_persona_slice_cards(
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
) -> dict[str, object]:
    cases = [case for case in case_concept_slots.get("cases", []) if case.get("series_code") == "T"]  # type: ignore[index]
    cards: list[dict[str, object]] = []
    for case in cases:
        case_title = case["case_title"]
        default_family = (case.get("family_and_home") or [case_title])[0]
        default_life = (case.get("life_focus") or [case_title])[0]
        default_style = (case.get("cleaning_attitude") or [case_title])[0]
        default_path = (case.get("purchase_path") or [case_title])[0]
        default_quote = (case.get("pain_points") or case.get("expected_needs") or [case_title])[0]
        cards.append(
            {
                "case_title": case_title,
                "role_bucket": case.get("gender_bucket", "他们是谁"),
                "one_line_persona": choose_case_persona(case, semantic_passages),
                "family_structure": choose_case_quote(case_title, semantic_passages, ["人物定义"], ["家庭", "同住", "独居", "两代", "三代", "新婚", "孩子", "父母"], default_family),
                "life_focus": choose_case_quote(case_title, semantic_passages, ["人物定义"], ["工作", "家庭", "个人", "自由", "品质", "秩序", "享乐"], default_life),
                "cleaning_style": choose_case_quote(case_title, semantic_passages, ["清洁态度"], ["清洁", "省心", "标准", "手动", "分区", "频率"], default_style),
                "purchase_path": choose_case_quote(case_title, semantic_passages, ["购买决策"], ["小红书", "京东", "抖音", "门店", "参数", "比价"], default_path),
                "representative_quote": choose_case_quote(case_title, semantic_passages, ["痛点", "期待", "清洁态度"], ["希望", "觉得", "不想", "需要", "担心", "期待"], default_quote),
                "primary_jtbd": infer_t_primary_jtbd(case),
            }
        )
    cards.sort(key=lambda item: (item["role_bucket"], item["case_title"]))
    return {"card_count": len(cards), "cards": cards}


def build_t_jtbd_packages(
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
) -> dict[str, object]:
    cases = [case for case in case_concept_slots.get("cases", []) if case.get("series_code") == "T"]  # type: ignore[index]
    defaults = {
        "个人优先": ("把清洁待办从个人时间里删掉，不要再占用我额外精力。", "不能为了机器多维护、多返工。"),
        "平衡共处": ("在家庭成员共处的状态下稳定运转，不打扰也不制造摩擦。", "不能影响家人作息，也不能把家务变成冲突。"),
        "家庭投入": ("在家庭标准下稳定把结果做出来，让负责家务的人不用持续兜底。", "不能掉链子，不能高频补救。"),
    }
    packages: list[dict[str, object]] = []
    for label in ["个人优先", "平衡共处", "家庭投入"]:
        selected = [case for case in cases if infer_t_primary_jtbd(case) == label][:3]
        case_titles = [case["case_title"] for case in selected]
        packages.append(
            {
                "jtbd_name": label,
                "typical_scene": [row["passage_text"] for row in pick_passages(semantic_passages, case_titles=case_titles, roles=["清洁态度", "痛点"], keywords=["每天", "每周", "油污", "门槛", "孩子", "猫毛", "分区", "手动"], limit=3)],
                "result_requirement": defaults[label][0],
                "unacceptable_cost": defaults[label][1],
                "representative_users": case_titles,
                "why_entered": [row["passage_text"] for row in pick_passages(semantic_passages, case_titles=case_titles, roles=["人物定义", "购买决策", "清洁态度"], keywords=["个人", "家庭", "分工", "责任", "效率", "平衡"], limit=2)],
            }
        )
    return {"package_count": len(packages), "packages": packages}


def build_t_difference_matrix(
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
) -> dict[str, object]:
    cases = [case for case in case_concept_slots.get("cases", []) if case.get("series_code") == "T"]  # type: ignore[index]
    if not cases:
        return {"row_count": 0, "rows": []}

    def pick_case(include_keywords: tuple[str, ...], exclude_titles: set[str] | None = None) -> dict[str, object]:
        exclude_titles = exclude_titles or set()
        scored = []
        for case in cases:
            if case["case_title"] in exclude_titles:
                continue
            blob = " ".join(
                [case["case_title"]]
                + list(case.get("persona_notes", []) or [])
                + list(case.get("family_and_home", []) or [])
                + list(case.get("life_focus", []) or [])
                + list(case.get("cleaning_attitude", []) or [])
            )
            scored.append((case, score_text_against_keywords(blob, include_keywords)))
        scored.sort(key=lambda item: (-item[1], item[0]["case_title"]))
        return scored[0][0] if scored else cases[0]

    rows: list[dict[str, object]] = []
    dimension_specs = [
        (
            "生命阶段与角色冲突",
            ("新婚", "育儿", "孩子", "妈妈", "爸爸", "丈夫"),
            ("单身", "独居", "个人"),
            "同样在买扫地机，但有的人是在家庭角色突然加重后被推着进场，有的人则是在生活节奏变化时主动把清洁从自己时间里剥离出去。",
        ),
        (
            "自我认同与思维模式",
            ("精致", "审美", "品质", "观点特别", "女强人", "艺术"),
            ("务实", "性价比", "酒店店长", "爸爸", "问题解决"),
            "有人把清洁看成生活秩序和自我表达的一部分，有人则把它视为应该被高效解决的问题，这会直接改变他们对机器的期待。",
        ),
        (
            "家庭结构与权力动态",
            ("父母", "婆婆", "妻子", "孩子", "三代", "两代"),
            ("独居", "单身", "自己"),
            "谁掌握预算、谁承担家务、谁在关键时刻兜底，决定了用户到底把扫地机当成替代、分担还是保障工具。",
        ),
    ]
    for dimension_name, lhs_keywords, rhs_keywords, explanation in dimension_specs:
        left = pick_case(lhs_keywords)
        right = pick_case(rhs_keywords, exclude_titles={left["case_title"]})
        left_quote = choose_case_quote(left["case_title"], semantic_passages, ["清洁态度", "购买决策", "痛点"], ["家庭", "孩子", "父母", "自己", "时间", "责任", "分工"], (left.get("persona_notes") or [left["case_title"]])[0])
        right_quote = choose_case_quote(right["case_title"], semantic_passages, ["清洁态度", "购买决策", "痛点"], ["家庭", "孩子", "父母", "自己", "时间", "责任", "分工"], (right.get("persona_notes") or [right["case_title"]])[0])
        left_value = "替代" if "替代" in (left.get("value_definition_candidates") or []) else "分担 / 保障"
        right_value = "替代" if "替代" in (right.get("value_definition_candidates") or []) else "分担 / 保障"
        rows.append(
            {
                "dimension": dimension_name,
                "contrast_pair": [left["case_title"], right["case_title"]],
                "why_different": explanation,
                "user_view_of_cleaning": f"{left['case_title']} 更把清洁当 `{infer_t_primary_jtbd(left)}`，而 {right['case_title']} 更把清洁当 `{infer_t_primary_jtbd(right)}`。",
                "value_definition": f"{left['case_title']} 更像 `{left_value}`，{right['case_title']} 更像 `{right_value}`。",
                "representative_support": [left_quote, right_quote],
            }
        )
    return {"row_count": len(rows), "rows": rows}


def build_brand_mindshare_judgments(
    brand_mindshare_map: dict[str, object],
) -> dict[str, object]:
    judgments: list[dict[str, object]] = []
    for brand, payload in (brand_mindshare_map.get("brands", {}) or {}).items():
        why_choose = list(payload.get("why_choose", payload.get("trust_reason", [])))[:2]
        why_reject = list(payload.get("why_reject", payload.get("rejection_reason", [])))[:2]
        quote_refs = list(payload.get("quote_refs", payload.get("representative_quotes", [])))[:2]
        judgments.append(
            {
                "brand": brand,
                "one_line_label": payload.get("core_label", f"{brand} 在用户眼里有清晰心智。"),
                "why_choose": why_choose,
                "why_reject": why_reject,
                "who_chooses": payload.get("who_prefers_it", [])[:3],
                "who_rejects": payload.get("who_rejects_it", [])[:3],
                "quote_refs": quote_refs,
                "trust_reason": why_choose,
                "rejection_reason": why_reject,
                "representative_quotes": quote_refs,
            }
        )
    return {"judgment_count": len(judgments), "judgments": judgments}


def build_idea_cluster_judgments(
    idea_pool_clusters: dict[str, object],
) -> dict[str, object]:
    judgments: list[dict[str, object]] = []
    desired_capability_map = {
        "顽固污渍": "把干涸和黏性污渍真正从“人工预处理”改成“机器直接处理”。",
        "地毯": "让地毯深清不再停留在识别和抬拖，而是提升深层处理能力。",
        "低介入": "把用户从启动、确认、补救和维护里继续往外拿。",
        "生态联动": "让清洁触发从‘我下指令’升级成‘家里状态变化后自动发生’。",
        "宠物应急": "把宠物呕吐物、排泄物、猫砂这类高压力场景变成有明确处置逻辑的模式。",
        "窄缝与门后": "把当前最典型的人工补扫区域真正纳入任务完成定义。",
        "机械臂/立面拓展": "把‘拿起来-清洁-放回去’或立面清洁变成下一代差异化能力。",
    }
    for cluster in idea_pool_clusters.get("clusters", []):
        examples = cluster.get("idea_examples", [])
        unmet_scene = examples[0]["idea_text"] if examples else cluster.get("theme_name", "")
        judgments.append(
            {
                "theme": cluster.get("theme_name"),
                "unmet_scene": unmet_scene,
                "desired_capability": desired_capability_map.get(cluster.get("theme_name", ""), "把当前未被满足的场景能力正式产品化。"),
                "who_needs_it": dedupe_preserve_order([example["case_title"] for example in examples])[:3],
                "now_or_later": cluster.get("is_now_or_later", "待判断"),
                "why_now": "这类想法已经直接贴近当前痛点和完成率问题。" if cluster.get("is_now_or_later") == "现在就该做" else "这类能力更适合作为后续的差异化加分项。",
            }
        )
    return {"judgment_count": len(judgments), "judgments": judgments}


def concept_keywords(concept_id: str, concept_type: str) -> tuple[str, ...]:
    if concept_type == "x_positioning":
        for schema in X_ROLE_LABEL_SCHEMA.values():
            canonical_anchor = str(schema["canonical_anchor"])
            label_candidates = set(schema["label_candidates"])  # type: ignore[arg-type]
            if concept_id == canonical_anchor or concept_id in label_candidates:
                return tuple(schema["keywords"])  # type: ignore[return-value]
        for label, keywords in X_POSITIONING_RULES:
            if label == concept_id:
                return keywords
    if concept_type == "t_jtbd":
        for label, keywords in T_JTBD_RULES:
            if label == concept_id:
                return keywords
    if concept_type == "t_difference_dimension":
        for label, keywords in T_DIFFERENCE_DIMENSION_RULES:
            if label == concept_id:
                return keywords
    if concept_type == "brand_mindshare":
        return (concept_id,)
    if concept_type == "idea_cluster":
        return IDEA_CLUSTER_RULES.get(concept_id, (concept_id,))
    if concept_type == "t_persona_slice":
        return ("男性", "女性", "妈妈", "爸爸", "独居", "家庭") if concept_id in {"他们是谁", "她们是谁"} else (concept_id,)
    return (concept_id,)


def count_passages_for_concept(
    semantic_passages: dict[str, object],
    *,
    case_titles: list[str] | None = None,
    roles: list[str] | None = None,
    keywords: tuple[str, ...] = (),
    min_quality: float = 0.0,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    if case_titles is not None and len(case_titles) == 0:
        return result
    case_set = set(case_titles or [])
    role_set = set(roles or [])
    for passage in semantic_passages.get("passages", []):  # type: ignore[index]
        if case_set and passage["case_title"] not in case_set:
            continue
        if role_set and passage["passage_role"] not in role_set:
            continue
        if keywords and not contains_any(passage["passage_text"], keywords):
            continue
        if float(passage.get("quality_score", 0.0)) < min_quality:
            continue
        result.append(passage)
    return result


def measure_signal_strength(text_rows: list[str], keywords: tuple[str, ...]) -> int:
    if not keywords:
        return 0
    score = 0
    for text in text_rows:
        score += score_text_against_keywords(text, keywords)
    return score


def judge_confidence(support_case_count: int, high_quality_passage_count: int, survey_signal_strength: int, voc_signal_strength: int) -> str:
    score = support_case_count + high_quality_passage_count + survey_signal_strength + voc_signal_strength
    if support_case_count >= 3 and high_quality_passage_count >= 3 and score >= 8:
        return "高"
    if support_case_count >= 2 and high_quality_passage_count >= 2:
        return "中"
    return "低"


def summarize_density(support_case_count: int, high_quality_passage_count: int, survey_signal_strength: int, voc_signal_strength: int) -> str:
    total = support_case_count + high_quality_passage_count + survey_signal_strength + voc_signal_strength
    if total >= 10:
        return "高"
    if total >= 5:
        return "中"
    return "低"


def cap_confidence_for_weak_signal(level: str, confidence: str) -> str:
    if level == "weak_signal" and confidence == "高":
        return "中"
    return confidence


def cap_impact_for_weak_signal(level: str, impact: str) -> str:
    if level == "weak_signal" and impact == "高":
        return "中"
    return impact


def build_concept_support_stats(
    *,
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
    survey_concept_segments: dict[str, object],
    voc_problem_packages: dict[str, object],
    x_positioning_packages: dict[str, object],
    t_persona_slice_cards: dict[str, object],
    t_difference_matrix: dict[str, object],
    t_jtbd_packages: dict[str, object],
    brand_mindshare_judgments: dict[str, object],
    idea_cluster_judgments: dict[str, object],
) -> dict[str, object]:
    total_cases = len(case_concept_slots.get("cases", []) or [])
    survey_text_rows = [json.dumps(row, ensure_ascii=False) for row in survey_concept_segments.get("segments", []) or []]
    voc_text_rows = [json.dumps(row, ensure_ascii=False) for row in voc_problem_packages.get("packages", []) or []]
    rows: list[dict[str, object]] = []

    for package in x_positioning_packages.get("packages", []) or []:
        concept_id = package["positioning_name"]
        case_titles = package.get("support_case_titles", []) or [row["case_title"] for row in package.get("representative_users", [])]
        keywords = concept_keywords(package.get("canonical_anchor", concept_id), "x_positioning")
        passages = count_passages_for_concept(semantic_passages, case_titles=case_titles, keywords=keywords)
        high_quality = [row for row in passages if float(row["quality_score"]) >= 0.75]
        survey_signal = measure_signal_strength(survey_text_rows, keywords)
        voc_signal = measure_signal_strength(voc_text_rows, keywords)
        overlap_ratio = 0.0
        if len(case_titles) > 1:
            overlap_ratio = max(0.0, (len(package.get("representative_users", [])) - len(set(case_titles))) / len(case_titles))
        differentiation_score = round(max(0.2, 1.0 - overlap_ratio) * 0.6 + min(survey_signal + voc_signal, 6) / 10, 3)
        rows.append(
            {
                "concept_id": concept_id,
                "concept_type": "x_positioning",
                "support_case_count": len(set(case_titles)),
                "support_case_share": round(len(set(case_titles)) / total_cases, 4) if total_cases else 0.0,
                "support_passage_count": len(passages),
                "high_quality_passage_count": len(high_quality),
                "survey_signal_strength": survey_signal,
                "voc_signal_strength": voc_signal,
                "evidence_density": summarize_density(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
                "differentiation_score": differentiation_score,
                "confidence": judge_confidence(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
            }
        )

    role_groups = defaultdict(list)
    for card in t_persona_slice_cards.get("cards", []) or []:
        role_groups[card["role_bucket"]].append(card["case_title"])
    for concept_id, case_titles in role_groups.items():
        keywords = concept_keywords(concept_id, "t_persona_slice")
        passages = count_passages_for_concept(semantic_passages, case_titles=case_titles, roles=["人物定义"], keywords=keywords)
        high_quality = [row for row in passages if float(row["quality_score"]) >= 0.75]
        survey_signal = measure_signal_strength(survey_text_rows, keywords)
        voc_signal = measure_signal_strength(voc_text_rows, keywords)
        rows.append(
            {
                "concept_id": concept_id,
                "concept_type": "t_persona_slice",
                "support_case_count": len(set(case_titles)),
                "support_case_share": round(len(set(case_titles)) / total_cases, 4) if total_cases else 0.0,
                "support_passage_count": len(passages),
                "high_quality_passage_count": len(high_quality),
                "survey_signal_strength": survey_signal,
                "voc_signal_strength": voc_signal,
                "evidence_density": summarize_density(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
                "differentiation_score": round(min(len(set(case_titles)), 4) / 4, 3),
                "confidence": judge_confidence(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
            }
        )

    for row in t_difference_matrix.get("rows", []) or []:
        concept_id = row["dimension"]
        case_titles = row.get("contrast_pair", [])
        keywords = concept_keywords(concept_id, "t_difference_dimension")
        passages = count_passages_for_concept(semantic_passages, case_titles=case_titles, keywords=keywords)
        high_quality = [item for item in passages if float(item["quality_score"]) >= 0.75]
        survey_signal = measure_signal_strength(survey_text_rows, keywords)
        voc_signal = measure_signal_strength(voc_text_rows, keywords)
        rows.append(
            {
                "concept_id": concept_id,
                "concept_type": "t_difference_dimension",
                "support_case_count": len(set(case_titles)),
                "support_case_share": round(len(set(case_titles)) / total_cases, 4) if total_cases else 0.0,
                "support_passage_count": len(passages),
                "high_quality_passage_count": len(high_quality),
                "survey_signal_strength": survey_signal,
                "voc_signal_strength": voc_signal,
                "evidence_density": summarize_density(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
                "differentiation_score": round(0.7 + min(survey_signal, 3) * 0.05, 3),
                "confidence": judge_confidence(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
            }
        )

    for package in t_jtbd_packages.get("packages", []) or []:
        concept_id = package["jtbd_name"]
        case_titles = package.get("representative_users", [])
        keywords = concept_keywords(concept_id, "t_jtbd")
        passages = count_passages_for_concept(semantic_passages, case_titles=case_titles, keywords=keywords)
        high_quality = [row for row in passages if float(row["quality_score"]) >= 0.75]
        survey_signal = measure_signal_strength(survey_text_rows, keywords)
        voc_signal = measure_signal_strength(voc_text_rows, keywords)
        rows.append(
            {
                "concept_id": concept_id,
                "concept_type": "t_jtbd",
                "support_case_count": len(set(case_titles)),
                "support_case_share": round(len(set(case_titles)) / total_cases, 4) if total_cases else 0.0,
                "support_passage_count": len(passages),
                "high_quality_passage_count": len(high_quality),
                "survey_signal_strength": survey_signal,
                "voc_signal_strength": voc_signal,
                "evidence_density": summarize_density(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
                "differentiation_score": round(min(len(set(case_titles)), 4) / 4 + min(survey_signal, 4) / 10, 3),
                "confidence": judge_confidence(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
            }
        )

    for row in brand_mindshare_judgments.get("judgments", []) or []:
        concept_id = row["brand"]
        case_titles = dedupe_preserve_order((row.get("who_chooses", []) or []) + (row.get("who_rejects", []) or []))
        keywords = concept_keywords(concept_id, "brand_mindshare")
        passages = count_passages_for_concept(semantic_passages, case_titles=case_titles, roles=["品牌认知"], keywords=keywords)
        high_quality = [item for item in passages if float(item["quality_score"]) >= 0.75]
        survey_signal = 0
        voc_signal = 0
        rows.append(
            {
                "concept_id": concept_id,
                "concept_type": "brand_mindshare",
                "support_case_count": len(set(case_titles)),
                "support_case_share": round(len(set(case_titles)) / total_cases, 4) if total_cases else 0.0,
                "support_passage_count": len(passages),
                "high_quality_passage_count": len(high_quality),
                "survey_signal_strength": survey_signal,
                "voc_signal_strength": voc_signal,
                "evidence_density": summarize_density(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
                "differentiation_score": round(min(len(row.get("why_choose", [])) + len(row.get("why_reject", [])), 4) / 4 + min(len(set(case_titles)), 4) / 10, 3),
                "confidence": judge_confidence(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
            }
        )

    for row in idea_cluster_judgments.get("judgments", []) or []:
        concept_id = row["theme"]
        case_titles = row.get("who_needs_it", [])
        keywords = concept_keywords(concept_id, "idea_cluster")
        passages = count_passages_for_concept(semantic_passages, case_titles=case_titles, roles=["金点子", "期待"], keywords=keywords)
        high_quality = [item for item in passages if float(item["quality_score"]) >= 0.75]
        survey_signal = measure_signal_strength(survey_text_rows, keywords)
        voc_signal = measure_signal_strength(voc_text_rows, keywords)
        rows.append(
            {
                "concept_id": concept_id,
                "concept_type": "idea_cluster",
                "support_case_count": len(set(case_titles)),
                "support_case_share": round(len(set(case_titles)) / total_cases, 4) if total_cases else 0.0,
                "support_passage_count": len(passages),
                "high_quality_passage_count": len(high_quality),
                "survey_signal_strength": survey_signal,
                "voc_signal_strength": voc_signal,
                "evidence_density": summarize_density(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
                "differentiation_score": round(min(len(set(case_titles)), 4) / 4 + (0.2 if row.get("now_or_later") == "现在就该做" else 0.1), 3),
                "confidence": judge_confidence(len(set(case_titles)), len(high_quality), survey_signal, voc_signal),
            }
        )

    rows.sort(key=lambda item: (item["concept_type"], -item["support_case_count"], item["concept_id"]))
    return {"stat_count": len(rows), "stats": rows}


def build_concept_comparison_matrix(concept_support_stats: dict[str, object]) -> dict[str, object]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in concept_support_stats.get("stats", []):  # type: ignore[index]
        grouped[row["concept_type"]].append(row)
    matrix_rows: list[dict[str, object]] = []
    for concept_type, rows in grouped.items():
        ordered = sorted(rows, key=lambda item: (-float(item["differentiation_score"]), -int(item["support_case_count"]), item["concept_id"]))
        matrix_rows.append(
            {
                "concept_type": concept_type,
                "concept_ids": [row["concept_id"] for row in ordered],
                "top_concept": ordered[0]["concept_id"] if ordered else "-",
                "comparison_rows": [
                    {
                        "concept_id": row["concept_id"],
                        "support_case_count": row["support_case_count"],
                        "support_passage_count": row["support_passage_count"],
                        "differentiation_score": row["differentiation_score"],
                        "confidence": row["confidence"],
                    }
                    for row in ordered
                ],
            }
        )
    return {"group_count": len(matrix_rows), "rows": matrix_rows}


def build_concept_pain_need_map(
    x_positioning_packages: dict[str, object],
    t_jtbd_packages: dict[str, object],
) -> dict[str, object]:
    mappings: list[dict[str, object]] = []
    theme_rules = [
        ("清洁效果与水痕污渍", ("水渍", "油污", "拖地", "污渍", "顽固")),
        ("边角与覆盖率", ("边角", "缝隙", "覆盖", "门后", "踢脚线")),
        ("避障越障与卡困", ("避障", "越障", "卡困", "门槛", "台阶")),
        ("维护与基站操作", ("维护", "异味", "基站", "脏手", "清理")),
        ("智能/App/语音/地图", ("智能", "路径", "地图", "语音", "主动", "感知")),
    ]
    for package in x_positioning_packages.get("packages", []) or []:
        pain_blob = " ".join(package.get("pain_need", []) + package.get("product_todo", []))
        for pain_theme, keywords in theme_rules:
            if not contains_any(pain_blob, keywords):
                continue
            mappings.append(
                {
                    "concept_id": package["positioning_name"],
                    "pain_theme": pain_theme,
                    "need_theme": package["jtbd"],
                    "damage_type": derive_damage_type(pain_blob),
                    "is_baseline_extension": pain_theme in {"清洁效果与水痕污渍", "边角与覆盖率", "避障越障与卡困"},
                    "support_strength": len(package.get("pain_need", [])),
                }
            )
    for package in t_jtbd_packages.get("packages", []) or []:
        pain_blob = " ".join(package.get("typical_scene", []) + package.get("why_entered", []))
        for pain_theme, keywords in theme_rules:
            if not contains_any(pain_blob, keywords):
                continue
            mappings.append(
                {
                    "concept_id": package["jtbd_name"],
                    "pain_theme": pain_theme,
                    "need_theme": package["result_requirement"],
                    "damage_type": derive_damage_type(pain_blob),
                    "is_baseline_extension": pain_theme in {"清洁效果与水痕污渍", "边角与覆盖率", "避障越障与卡困"},
                    "support_strength": len(package.get("typical_scene", [])),
                }
            )
    return {"row_count": len(mappings), "rows": mappings}


def detect_pain_themes(texts: list[str]) -> list[str]:
    matched: list[str] = []
    joined = " ".join(texts)
    for theme_name, keywords in PAIN_THEME_RULES:
        if contains_any(joined, keywords):
            matched.append(theme_name)
    return dedupe_preserve_order(matched)


def voc_package_pain_themes(package: dict[str, object]) -> list[str]:
    texts = [
        str(package.get("negative_tag", "")),
        str(package.get("package_name", "")),
        str(package.get("trigger_scene", "")),
        str(package.get("working_condition", "")),
        str(package.get("damage_type", "")),
        str(package.get("trust_impact", "")),
    ]
    return detect_pain_themes(texts)


def survey_segment_pain_themes(segment: dict[str, object]) -> list[str]:
    texts: list[str] = []
    for row in segment.get("top_problems", []) or []:
        texts.append(str(row.get("tag_name", "")))
    for row in segment.get("top_motivations", []) or []:
        texts.append(str(row.get("answer_text", "")))
    texts.extend(segment.get("difference_reason", []) or [])
    return detect_pain_themes(texts)


def summarize_concept_confidence(
    *,
    support_case_count: int,
    high_quality_passage_count: int,
    cross_case_repeat_count: int,
    extra_strength: int,
) -> str:
    score = 0
    if support_case_count >= 3:
        score += 2
    elif support_case_count >= 2:
        score += 1
    if high_quality_passage_count >= 4:
        score += 2
    elif high_quality_passage_count >= 2:
        score += 1
    if cross_case_repeat_count >= 2:
        score += 1
    score += extra_strength
    if score >= 5:
        return "高"
    if score >= 3:
        return "中"
    return "低"


def summarize_impact_level(
    *,
    linked_pain_theme_count: int,
    linked_voc_package_strength: int,
    linked_survey_segment_strength: int,
    linked_priority_bucket_count: int,
    linked_trust_damage_count: int,
) -> str:
    score = linked_pain_theme_count + linked_priority_bucket_count + linked_trust_damage_count
    if linked_voc_package_strength >= 3:
        score += 2
    elif linked_voc_package_strength >= 1:
        score += 1
    if linked_survey_segment_strength >= 2:
        score += 2
    elif linked_survey_segment_strength >= 1:
        score += 1
    if score >= 7:
        return "高"
    if score >= 4:
        return "中"
    return "低"


def build_t_dimension_confidence_stats(
    *,
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
    t_difference_matrix: dict[str, object],
) -> dict[str, object]:
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    rows: list[dict[str, object]] = []
    for matrix_row in t_difference_matrix.get("rows", []) or []:
        concept_id = matrix_row["dimension"]
        keywords = concept_keywords(concept_id, "t_difference_dimension")
        case_titles_in_support = {
            passage["case_title"]
            for passage in pick_passages(
                semantic_passages,
                roles=["人物定义", "清洁态度", "购买决策", "差异解释"],
                keywords=list(keywords),
                limit=200,
            )
        }
        matched_cases = [
            case for case in cases
            if case.get("series_code") == "T"
            and (
                concept_id in (case.get("t_difference_dimensions") or [])
                or case["case_title"] in matrix_row.get("contrast_pair", [])
                or case["case_title"] in case_titles_in_support
            )
        ]
        support_case_count = len({case["case_title"] for case in matched_cases})
        passages = count_passages_for_concept(
            semantic_passages,
            case_titles=[case["case_title"] for case in matched_cases],
            roles=["人物定义", "清洁态度", "购买决策", "差异解释"],
            min_quality=0.6,
        )
        high_quality = [row for row in passages if float(row["quality_score"]) >= 0.75]
        cross_jtbd_coverage = len({infer_t_primary_jtbd(case) for case in matched_cases})
        value_definition_split_strength = len({("替代" if "替代" in (case.get("value_definition_candidates") or []) else "分担 / 保障") for case in matched_cases})
        cross_case_repeat_count = max(0, support_case_count - len(matrix_row.get("contrast_pair", [])) + 1)
        confidence_level = summarize_concept_confidence(
            support_case_count=support_case_count,
            high_quality_passage_count=len(high_quality),
            cross_case_repeat_count=cross_case_repeat_count,
            extra_strength=(1 if cross_jtbd_coverage >= 2 else 0) + (1 if value_definition_split_strength >= 2 else 0),
        )
        rows.append(
            {
                "concept_id": concept_id,
                "contrast_pair_count": 1 if matrix_row.get("contrast_pair") else 0,
                "support_case_count": support_case_count,
                "high_quality_passage_count": len(high_quality),
                "cross_case_repeat_count": cross_case_repeat_count,
                "cross_jtbd_coverage": cross_jtbd_coverage,
                "value_definition_split_strength": value_definition_split_strength,
                "confidence_level": confidence_level,
            }
        )
    return {"row_count": len(rows), "rows": rows}


def build_t_dimension_impact_stats(
    *,
    case_concept_slots: dict[str, object],
    t_difference_matrix: dict[str, object],
    voc_problem_packages: dict[str, object],
    survey_concept_segments: dict[str, object],
    concept_pain_need_map: dict[str, object],
    cross_source_interpretation: dict[str, object],
    strategy_translation: dict[str, object],
) -> dict[str, object]:
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    voc_rows = voc_problem_packages.get("packages", []) or []
    survey_rows = survey_concept_segments.get("segments", []) or []
    pain_rows = concept_pain_need_map.get("rows", []) or []
    interpretation_rows = cross_source_interpretation.get("interpretations", []) or []
    priority_buckets = strategy_translation.get("priority_buckets", {}) or {}
    rows: list[dict[str, object]] = []

    for matrix_row in t_difference_matrix.get("rows", []) or []:
        concept_id = matrix_row["dimension"]
        case_titles = matrix_row.get("contrast_pair", [])
        matched_cases = [case for case in cases if case["case_title"] in case_titles]
        related_spu_ids = dedupe_preserve_order([str(case.get("inferred_spu_id")) for case in matched_cases if case.get("inferred_spu_id")])
        related_jtbds = dedupe_preserve_order([infer_t_primary_jtbd(case) for case in matched_cases])
        linked_pain_themes = [row["pain_theme"] for row in pain_rows if row["concept_id"] in related_jtbds]
        if not linked_pain_themes:
            text_pool = []
            for case in matched_cases:
                text_pool.extend(case.get("pain_points", []) or [])
                text_pool.extend(case.get("expected_needs", []) or [])
            linked_pain_themes = detect_pain_themes(text_pool)
        linked_pain_themes = dedupe_preserve_order(linked_pain_themes)
        linked_need_theme_count = len(set(linked_pain_themes))
        linked_voc_packages = [
            row for row in voc_rows
            if (
                (related_spu_ids and row.get("spu_id") in related_spu_ids)
                or (not related_spu_ids and infer_series_code(row.get("spu_id"), row.get("package_name", "")) == "T")
            )
            and set(voc_package_pain_themes(row)).intersection(linked_pain_themes)
        ]
        linked_survey_segments = [
            row for row in survey_rows
            if infer_series_code(row.get("inferred_spu_id"), row.get("wave_name", "")) == "T"
            and row.get("difference_reason")
            and set(survey_segment_pain_themes(row)).intersection(linked_pain_themes)
        ]
        linked_trust_damage = len({row.get("trust_impact") for row in linked_voc_packages if row.get("trust_impact")})
        priority_relevance = []
        for bucket_name, themes in priority_buckets.items():
            if any(theme in themes for theme in linked_pain_themes):
                priority_relevance.append(bucket_name)
        if not priority_relevance:
            for interp in interpretation_rows:
                if interp.get("theme_name") in linked_pain_themes:
                    priority_relevance.append(interp.get("priority_hint", "待验证"))
        impact_level = summarize_impact_level(
            linked_pain_theme_count=len(linked_pain_themes),
            linked_voc_package_strength=len(linked_voc_packages),
            linked_survey_segment_strength=len(linked_survey_segments),
            linked_priority_bucket_count=len(set(priority_relevance)),
            linked_trust_damage_count=linked_trust_damage,
        )
        rows.append(
            {
                "concept_id": concept_id,
                "linked_pain_theme_count": len(linked_pain_themes),
                "linked_need_theme_count": linked_need_theme_count,
                "linked_voc_package_strength": len(linked_voc_packages),
                "linked_survey_segment_strength": len(linked_survey_segments),
                "linked_trust_damage_count": linked_trust_damage,
                "priority_relevance": dedupe_preserve_order([str(item) for item in priority_relevance]),
                "impact_level": impact_level,
                "linked_pain_themes": linked_pain_themes,
                "linked_jtbds": related_jtbds,
                "linked_spu_ids": related_spu_ids,
            }
        )
    return {"row_count": len(rows), "rows": rows}


def build_t_jtbd_confidence_stats(
    *,
    case_concept_slots: dict[str, object],
    semantic_passages: dict[str, object],
    t_jtbd_packages: dict[str, object],
) -> dict[str, object]:
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    rows: list[dict[str, object]] = []
    for package in t_jtbd_packages.get("packages", []) or []:
        jtbd_name = package["jtbd_name"]
        matched_cases = [case for case in cases if case.get("series_code") == "T" and infer_t_primary_jtbd(case) == jtbd_name]
        passages = count_passages_for_concept(
            semantic_passages,
            case_titles=[case["case_title"] for case in matched_cases],
            roles=["人物定义", "清洁态度", "购买决策", "痛点", "期待"],
            min_quality=0.6,
        )
        high_quality = [row for row in passages if float(row["quality_score"]) >= 0.75]
        scenario_repeat_count = len(package.get("typical_scene", []))
        result_requirement_clarity = 1 if len(normalize_text(package.get("result_requirement", ""))) >= 12 else 0
        unacceptable_cost_clarity = 1 if len(normalize_text(package.get("unacceptable_cost", ""))) >= 12 else 0
        confidence_level = summarize_concept_confidence(
            support_case_count=len(matched_cases),
            high_quality_passage_count=len(high_quality),
            cross_case_repeat_count=scenario_repeat_count,
            extra_strength=result_requirement_clarity + unacceptable_cost_clarity,
        )
        rows.append(
            {
                "jtbd_name": jtbd_name,
                "support_case_count": len(matched_cases),
                "high_quality_passage_count": len(high_quality),
                "scenario_repeat_count": scenario_repeat_count,
                "result_requirement_clarity": result_requirement_clarity,
                "unacceptable_cost_clarity": unacceptable_cost_clarity,
                "confidence_level": confidence_level,
            }
        )
    return {"row_count": len(rows), "rows": rows}


def build_t_jtbd_impact_stats(
    *,
    case_concept_slots: dict[str, object],
    t_jtbd_packages: dict[str, object],
    voc_problem_packages: dict[str, object],
    survey_concept_segments: dict[str, object],
    concept_pain_need_map: dict[str, object],
    strategy_translation: dict[str, object],
) -> dict[str, object]:
    cases = case_concept_slots.get("cases", []) or []  # type: ignore[index]
    voc_rows = voc_problem_packages.get("packages", []) or []
    survey_rows = survey_concept_segments.get("segments", []) or []
    pain_rows = concept_pain_need_map.get("rows", []) or []
    priority_buckets = strategy_translation.get("priority_buckets", {}) or {}
    rows: list[dict[str, object]] = []
    for package in t_jtbd_packages.get("packages", []) or []:
        jtbd_name = package["jtbd_name"]
        related_cases = [case for case in cases if case.get("series_code") == "T" and infer_t_primary_jtbd(case) == jtbd_name]
        related_spu_ids = dedupe_preserve_order([str(case.get("inferred_spu_id")) for case in related_cases if case.get("inferred_spu_id")])
        text_pool = list(package.get("typical_scene", [])) + list(package.get("why_entered", []))
        linked_pain_themes = detect_pain_themes(text_pool)
        if not linked_pain_themes:
            linked_pain_themes = [row["pain_theme"] for row in pain_rows if row["concept_id"] == jtbd_name]
        linked_voc_packages = [
            row for row in voc_rows
            if (
                (related_spu_ids and row.get("spu_id") in related_spu_ids)
                or (not related_spu_ids and infer_series_code(row.get("spu_id"), row.get("package_name", "")) == "T")
            )
            and set(voc_package_pain_themes(row)).intersection(linked_pain_themes)
        ]
        linked_survey_segments = [
            row for row in survey_rows
            if infer_series_code(row.get("inferred_spu_id"), row.get("wave_name", "")) == "T"
            and row.get("difference_reason")
            and set(survey_segment_pain_themes(row)).intersection(linked_pain_themes)
        ]
        linked_priority_bucket_count = sum(1 for themes in priority_buckets.values() if any(theme in themes for theme in linked_pain_themes))
        impact_level = summarize_impact_level(
            linked_pain_theme_count=len(set(linked_pain_themes)),
            linked_voc_package_strength=len(linked_voc_packages),
            linked_survey_segment_strength=len(linked_survey_segments),
            linked_priority_bucket_count=linked_priority_bucket_count,
            linked_trust_damage_count=len({row.get("trust_impact") for row in linked_voc_packages if row.get("trust_impact")}),
        )
        rows.append(
            {
                "jtbd_name": jtbd_name,
                "linked_pain_theme_count": len(set(linked_pain_themes)),
                "linked_voc_package_strength": len(linked_voc_packages),
                "linked_survey_segment_strength": len(linked_survey_segments),
                "linked_priority_bucket_count": linked_priority_bucket_count,
                "impact_level": impact_level,
                "linked_pain_themes": dedupe_preserve_order(linked_pain_themes),
                "linked_spu_ids": related_spu_ids,
            }
        )
    return {"row_count": len(rows), "rows": rows}


def build_page_metric_cards(
    concept_support_stats: dict[str, object],
    concept_comparison_matrix: dict[str, object],
    concept_pain_need_map: dict[str, object],
    x_positioning_confidence_stats: dict[str, object] | None = None,
    x_positioning_impact_stats: dict[str, object] | None = None,
    x_jtbd_confidence_stats: dict[str, object] | None = None,
    x_jtbd_impact_stats: dict[str, object] | None = None,
    t_dimension_confidence_stats: dict[str, object] | None = None,
    t_dimension_impact_stats: dict[str, object] | None = None,
    t_jtbd_confidence_stats: dict[str, object] | None = None,
    t_jtbd_impact_stats: dict[str, object] | None = None,
) -> dict[str, object]:
    stats = concept_support_stats.get("stats", []) or []
    stats_by_id = {f"{row['concept_type']}::{row['concept_id']}": row for row in stats}

    def card_for(concept_type: str, concept_id: str, title: str) -> dict[str, object] | None:
        row = stats_by_id.get(f"{concept_type}::{concept_id}")
        if not row:
            return None
        metric_value = f"{row['support_case_count']}个案例 / {row['high_quality_passage_count']}条高质量证据 / 区分度{row['differentiation_score']}"
        return {
            "title": title,
            "metric_value": metric_value,
            "interpretation": f"当前证据密度{row['evidence_density']}，置信度{row['confidence']}。",
        }

    blocks = []
    if x_positioning_confidence_stats and x_positioning_impact_stats:
        x_conf = {row["positioning_name"]: row for row in x_positioning_confidence_stats.get("rows", []) or []}
        x_impact = {row["positioning_name"]: row for row in x_positioning_impact_stats.get("rows", []) or []}
        ordered_labels = [row["positioning_name"] for row in x_positioning_confidence_stats.get("rows", []) or []]
        blocks.append(
            {
                "page_id": "x_positioning_overview",
                "cards": [
                    {
                        "title": f"{positioning_name}（弱信号）" if x_conf.get(positioning_name, {}).get("positioning_level") == "weak_signal" else positioning_name,
                        "metric_value": f"成立度{x_conf.get(positioning_name, {}).get('confidence_level', '-')} / 影响力{x_impact.get(positioning_name, {}).get('impact_level', '-')}",
                        "interpretation": f"{x_conf.get(positioning_name, {}).get('support_case_count', 0)}个案例 / {x_impact.get(positioning_name, {}).get('linked_voc_package_strength', 0)}个相关VOC问题包 / {x_impact.get(positioning_name, {}).get('linked_brand_judgment_strength', 0)}个品牌支撑 / {x_impact.get(positioning_name, {}).get('linked_idea_cluster_strength', 0)}个金点子支撑",
                    }
                    for positioning_name in ordered_labels
                ],
            }
        )
    else:
        blocks.append(
            {
                "page_id": "x_positioning_overview",
                "cards": [card for card in [
                    card_for("x_positioning", "清洁帮手", "清洁帮手强度"),
                    card_for("x_positioning", "清洁管家", "清洁管家强度"),
                    card_for("x_positioning", "社交名片", "社交名片强度"),
                ] if card],
            }
        )
    if t_dimension_confidence_stats and t_dimension_impact_stats:
        dim_conf = {row["concept_id"]: row for row in t_dimension_confidence_stats.get("rows", []) or []}
        dim_impact = {row["concept_id"]: row for row in t_dimension_impact_stats.get("rows", []) or []}
        blocks.append(
            {
                "page_id": "t_difference_matrix",
                "cards": [
                    {
                        "title": concept_id,
                        "metric_value": f"成立度{dim_conf.get(concept_id, {}).get('confidence_level', '-')} / 影响力{dim_impact.get(concept_id, {}).get('impact_level', '-')}",
                        "interpretation": f"{dim_conf.get(concept_id, {}).get('support_case_count', 0)}个案例 / {dim_impact.get(concept_id, {}).get('linked_voc_package_strength', 0)}个相关VOC问题包",
                    }
                    for concept_id in ["生命阶段与角色冲突", "自我认同与思维模式", "家庭结构与权力动态"]
                ],
            }
        )
    else:
        blocks.append(
            {
                "page_id": "t_difference_matrix",
                "cards": [card for card in [
                    card_for("t_difference_dimension", "生命阶段与角色冲突", "生命阶段强度"),
                    card_for("t_difference_dimension", "自我认同与思维模式", "自我认同强度"),
                    card_for("t_difference_dimension", "家庭结构与权力动态", "家庭结构强度"),
                ] if card],
            }
        )
    if t_jtbd_confidence_stats and t_jtbd_impact_stats:
        jtbd_conf = {row["jtbd_name"]: row for row in t_jtbd_confidence_stats.get("rows", []) or []}
        jtbd_impact = {row["jtbd_name"]: row for row in t_jtbd_impact_stats.get("rows", []) or []}
        blocks.append(
            {
                "page_id": "t_jtbd_pages",
                "cards": [
                    {
                        "title": jtbd_name,
                        "metric_value": f"成立度{jtbd_conf.get(jtbd_name, {}).get('confidence_level', '-')} / 影响力{jtbd_impact.get(jtbd_name, {}).get('impact_level', '-')}",
                        "interpretation": f"{jtbd_conf.get(jtbd_name, {}).get('support_case_count', 0)}个案例 / {jtbd_impact.get(jtbd_name, {}).get('linked_voc_package_strength', 0)}个相关VOC问题包",
                    }
                    for jtbd_name in ["个人优先", "平衡共处", "家庭投入"]
                ],
            }
        )
    else:
        blocks.append(
            {
                "page_id": "t_jtbd_pages",
                "cards": [card for card in [
                    card_for("t_jtbd", "个人优先", "个人优先强度"),
                    card_for("t_jtbd", "平衡共处", "平衡共处强度"),
                    card_for("t_jtbd", "家庭投入", "家庭投入强度"),
                ] if card],
            }
        )
    brand_cards = []
    for row in concept_comparison_matrix.get("rows", []) or []:
        if row["concept_type"] != "brand_mindshare":
            continue
        for item in row.get("comparison_rows", [])[:3]:
            stat = stats_by_id.get(f"brand_mindshare::{item['concept_id']}")
            if not stat:
                continue
            brand_cards.append(
                {
                    "title": f"{item['concept_id']}心智稳定度",
                    "metric_value": f"{stat['support_case_count']}个相关案例 / 区分度{stat['differentiation_score']}",
                    "interpretation": f"证据密度{stat['evidence_density']}。",
                }
            )
    blocks.append({"page_id": "brand_mindshare_pages", "cards": brand_cards[:4]})

    idea_cards = []
    for row in concept_comparison_matrix.get("rows", []) or []:
        if row["concept_type"] != "idea_cluster":
            continue
        for item in row.get("comparison_rows", [])[:3]:
            stat = stats_by_id.get(f"idea_cluster::{item['concept_id']}")
            if not stat:
                continue
            idea_cards.append(
                {
                    "title": f"{item['concept_id']}热度",
                    "metric_value": f"{stat['support_case_count']}个相关案例 / {stat['support_passage_count']}条支持段",
                    "interpretation": f"当前更像{'底线延伸' if any(map_row['concept_id'] == item['concept_id'] and map_row['is_baseline_extension'] for map_row in concept_pain_need_map.get('rows', [])) else '未来加分项'}。",
                }
            )
    blocks.append({"page_id": "idea_pool_pages", "cards": idea_cards[:4]})

    pain_rows = concept_pain_need_map.get("rows", []) or []
    pain_cards = []
    for pain_theme in ["清洁效果与水痕污渍", "边角与覆盖率", "避障越障与卡困", "维护与基站操作", "智能/App/语音/地图"]:
        related = [row for row in pain_rows if row["pain_theme"] == pain_theme]
        if not related:
            continue
        concept_ids = dedupe_preserve_order([row["concept_id"] for row in related])[:3]
        pain_cards.append(
            {
                "title": pain_theme,
                "metric_value": f"{len(related)}条概念映射 / 主要落在{'、'.join(concept_ids)}",
                "interpretation": "这些问题已经在抽象层里被证明会影响判断，不再只是零散功能点。",
            }
        )
    blocks.append({"page_id": "pain_need_pages", "cards": pain_cards[:5]})

    return {"block_count": len(blocks), "blocks": blocks}


def build_series_positioning(
    summary_insight_cards: dict[str, object],
    survey_segment_comparison: dict[str, object],
    cross_source_interpretation: dict[str, object],
) -> dict[str, object]:
    cards = summary_insight_cards.get("cards", []) or []
    segments = survey_segment_comparison.get("segments", []) or []
    interpretations = cross_source_interpretation.get("interpretations", []) or []
    grouped_cards: dict[str, list[dict[str, object]]] = defaultdict(list)
    for card in cards:
        grouped_cards[infer_series_code(card.get("inferred_spu_id"), card.get("case_title", ""))].append(card)  # type: ignore[arg-type]
    grouped_segments: dict[str, list[dict[str, object]]] = defaultdict(list)
    for segment in segments:
        grouped_segments[infer_series_code(segment.get("inferred_spu_id"), segment.get("wave_name", ""))].append(segment)  # type: ignore[arg-type]

    interpretations_by_priority = [row for row in interpretations if row.get("priority_hint") in {"P1", "P2"}]
    top_themes = [row["theme_name"] for row in interpretations_by_priority[:3]]

    series_rows: list[dict[str, object]] = []
    for series_code in ["X", "T"]:
        series_cards = grouped_cards.get(series_code, [])
        series_segments = grouped_segments.get(series_code, [])
        concept_summary = summarize_series_concepts(series_code, series_cards, series_segments)
        archetype_counter: Counter[str] = Counter()
        hidden_need_counter: Counter[str] = Counter()
        reason_counter: Counter[str] = Counter()
        brand_counter: Counter[str] = Counter()
        for card in series_cards:
            for label in card.get("persona_archetype", []):
                archetype_counter[label] += 1
            for label in card.get("hidden_need", []):
                hidden_need_counter[label] += 1
            reason_counter[card.get("difference_reason", "")] += 1
            evidence_blob = json.dumps(card.get("evidence_sections", {}), ensure_ascii=False)
            for brand in BRAND_LABELS:
                if brand in evidence_blob:
                    brand_counter[brand] += 1
        top_archetype = archetype_counter.most_common(1)[0][0] if archetype_counter else "待补充"
        top_hidden_need = hidden_need_counter.most_common(1)[0][0] if hidden_need_counter else "待补充"
        top_reason = reason_counter.most_common(1)[0][0] if reason_counter else "待补充"
        representative_persona = series_cards[0]["case_title"] if series_cards else "待补充"
        top_segment = series_segments[0]["segment_name"] if series_segments else "待补充"
        brand_mindshare = [label for label, _ in brand_counter.most_common(3)]
        positioning_candidates = concept_summary.get("positioning_candidates", []) or []
        jtbd_candidates = concept_summary.get("jtbd_candidates", []) or []
        difference_reason_clusters = concept_summary.get("difference_reason_clusters", []) or []

        if series_code == "X":
            positioning_label = positioning_candidates[0] if positioning_candidates else "清洁帮手"
            positioning_type = " / ".join(positioning_candidates[:2]) if positioning_candidates else "工具型 + 托管型"
            if jtbd_candidates and jtbd_candidates[0] == "科技美学表达":
                core_job_to_be_done = "作为科技表达与生活方式的一部分，被看见、被谈论，同时还能把清洁这件事做得足够省心。"
            elif jtbd_candidates and jtbd_candidates[0] == "整体洁净托管":
                core_job_to_be_done = "不只是完成清洁，而是主动维持整体洁净，让用户把打扫这件事从注意力里移走。"
            else:
                core_job_to_be_done = "把地面基础清洁稳定完成，同时尽量不制造新的维护负担。"
        else:
            positioning_label = positioning_candidates[0] if positioning_candidates else "家庭投入"
            positioning_type = " / ".join(positioning_candidates[:2]) if positioning_candidates else "个人优先 + 平衡共处 + 家庭投入"
            if jtbd_candidates and jtbd_candidates[0] == "家庭投入":
                core_job_to_be_done = "在家庭标准下稳定把清洁做出来，不要让我反复检查、补救和兜底。"
            elif jtbd_candidates and jtbd_candidates[0] == "平衡共处":
                core_job_to_be_done = "让家庭清洁稳定运转，但不要打扰家人节奏，也不要制造新的情绪摩擦。"
            elif jtbd_candidates and jtbd_candidates[0] == "个人优先":
                core_job_to_be_done = "把清洁待办从自己的时间里删掉，让机器先把基础结果稳定做完。"
            else:
                core_job_to_be_done = "稳定地把地面清洁做好，尽量少返工、少操心、少额外维护。"

        proof_points = [
            f"定性里最鲜明的人物模式是 `{top_archetype}`。",
            f"反复出现的隐性需求是 `{top_hidden_need}`。",
            f"问卷里更容易出现差异判断的人群是 `{top_segment}`。",
        ]
        if brand_mindshare:
            proof_points.append(f"当前对比心智里被反复提及的品牌包括 `{ '、'.join(brand_mindshare) }`。")

        series_rows.append(
            {
                "series_code": series_code,
                "positioning_label": positioning_label,
                "positioning_type": positioning_type,
                "representative_persona": representative_persona,
                "core_job_to_be_done": core_job_to_be_done,
                "proof_points": proof_points,
                "counter_examples": [],
                "difference_reason_cluster": top_reason,
                "difference_reason_clusters": difference_reason_clusters,
                "positioning_candidates": positioning_candidates,
                "jtbd_candidates": jtbd_candidates,
                "brand_mindshare": brand_mindshare,
                "priority_themes": top_themes,
            }
        )

    return {"series_count": len(series_rows), "series_rows": series_rows}


def build_strategy_translation(
    cross_source_interpretation: dict[str, object],
    voc_problem_packages: dict[str, object],
    summary_insight_cards: dict[str, object],
    series_positioning: dict[str, object],
) -> dict[str, object]:
    interpretations = cross_source_interpretation.get("interpretations", []) or []
    packages = voc_problem_packages.get("packages", []) or []
    series_rows = series_positioning.get("series_rows", []) or []

    priority_buckets = {
        "底线问题": [row["theme_name"] for row in interpretations if row.get("priority_hint") == "P1"][:4],
        "竞争焦点": [row["theme_name"] for row in interpretations if row.get("alignment_type") == "一致"][:4],
        "机会点": [row["theme_name"] for row in interpretations if row.get("priority_hint") == "P2"][:4],
        "先不讲满": [row["theme_name"] for row in interpretations if row.get("alignment_type") == "冲突"][:4],
    }
    top_package_names = [row["package_name"] for row in packages[:6]]

    half_year_focus = [
        {
            "phase": "当前轮次",
            "focus": priority_buckets["底线问题"][:2],
            "core_blocker": "先把最伤害信任的一组问题讲透，而不是平均摊开所有议题。",
        },
        {
            "phase": "下一轮",
            "focus": priority_buckets["竞争焦点"][:2],
            "core_blocker": "把竞争差异从参数差异翻成体验与信任差异。",
        },
    ]

    value_pillar_candidates = [
        {
            "pillar_name": "省心托管",
            "why": "高频问题最后都在伤害用户对“能不能放心交给它”的判断。",
            "supporting_themes": [theme for theme in priority_buckets["底线问题"] if theme in {"清洁效果与水痕污渍", "避障越障与卡困", "维护与基站操作", "边角与覆盖率"}],
        },
        {
            "pillar_name": "科技表达",
            "why": "部分高价值用户不是只买清洁结果，也在买科技感、品位和新鲜感。",
            "supporting_themes": [theme for theme in priority_buckets["机会点"] if theme],
        },
    ]

    priority_reasoning = [
        "先做那些已经在多个来源同时出现、并且会伤害清洁结果或托管信任的问题。",
        "再做那些能够拉开竞争感知差距、但当前仍需要补第三源验证的问题。",
        "最后才处理低渗透、低频、更多依赖创意表达的机会点。",
    ]

    not_now = priority_buckets["先不讲满"]
    core_blockers = [item["core_blocker"] for item in half_year_focus]

    return {
        "priority_buckets": priority_buckets,
        "value_pillar_candidates": value_pillar_candidates,
        "priority_reasoning": priority_reasoning,
        "half_year_focus": half_year_focus,
        "core_blockers": core_blockers,
        "not_now": not_now,
        "top_problem_packages": top_package_names,
        "series_positioning_summary": [
            {
                "series_code": row["series_code"],
                "positioning_label": row["positioning_label"],
                "priority_themes": row["priority_themes"],
            }
            for row in series_rows
        ],
    }
