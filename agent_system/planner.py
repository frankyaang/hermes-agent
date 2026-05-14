from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TaskContext:
    current_user_message: str
    reply_context: str = ""
    conversation_summary: str = ""
    mentioned_files: list[str] = field(default_factory=list)
    existing_artifacts: list[str] = field(default_factory=list)
    available_experts: list[str] = field(default_factory=list)
    available_skills: list[str] = field(default_factory=list)
    requested_output: str = ""
    platform_context: str = ""


@dataclass
class ExpertSelection:
    primary_expert_id: str
    primary_expert_source: str  # "registered" | "ephemeral"
    reason: str
    confidence: float
    candidate_experts: list[str] = field(default_factory=list)
    ephemeral_spec: dict[str, Any] | None = None


@dataclass
class TaskSpec:
    task_goal: str
    task_type: str
    input_kind: str
    output_kind: str
    requires_voc_insight: bool
    requires_existing_artifact: bool
    requires_publish: bool
    requires_status_lookup: bool
    source_artifact: str = ""
    expected_output: str = ""
    rejection_reason_for_voc_insight: str = ""


@dataclass
class DynamicPipelineSpecNode:
    node_id: str
    display_name: str
    skill_id: str
    depends_on: list[str] = field(default_factory=list)
    primary_expert: str | None = None
    secondary_experts: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    user_gate: bool = False
    optional: bool = False
    final_output: bool = False


@dataclass
class DynamicPipelineSpec:
    pipeline_id: str
    pipeline_name: str
    generated_by_primary_expert: str
    planning_source: str  # "template_reuse" | "template_adapted" | "dynamic_generated"
    nodes: list[DynamicPipelineSpecNode]
    final_output_node: str
    fallback_strategy: str = "return_partial_output"
    template_candidate: bool = False
    skipped_voc_insight_reason: str = ""
    task_context_summary: str = ""
    expert_selection: dict[str, Any] = field(default_factory=dict)
    task_spec: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

_VOC_REQUIRED_KEYWORDS = frozenset({
    "voc", "用户洞察", "用户画像", "痛点分析", "需求分析",
    "满意度", "流失", "流失原因", "调研数据", "评论", "竞品反馈",
    "用户反馈", "质量反馈", "用户调研", "入户", "质性访谈",
    "洞察结论", "洞察分析",
})

_FORMAT_PUBLISH_KEYWORDS = frozenset({
    "转成云文档", "云文档", "feishu doc", "飞书云文档", "发布",
    "转换格式", "导出", "转化为", "转成文档", "上传文档",
})

_DELIVERY_KEYWORDS = frozenset({
    "把执行结果发出来", "发给我", "发出来", "返回结果", "输出结果",
    "把结果发", "把报告发", "发送结果",
})

_STATUS_KEYWORDS = frozenset({
    "生成好了吗", "完成了吗", "还在运行吗", "进度如何", "任务状态",
    "有结果了吗", "做完了吗", "好了吗", "状态查询",
})

_REVISION_KEYWORDS = frozenset({
    "基于已有报告", "继续细化", "润色", "改写", "整理报告",
    "完善报告", "基于上次", "在此基础上", "细化分析", "补充内容",
    "修改报告", "优化报告",
})

_DASHBOARD_FROM_ARTIFACT_KEYWORDS = frozenset({
    "生成看板", "生成dashboard", "生成报告", "制作看板",
})


def _msg_contains_any(text: str, keywords: frozenset[str]) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def matches_any_task_keyword(message: str) -> bool:
    """Return True if message contains any recognized agent_system task keyword."""
    return any(
        _msg_contains_any(message, kw_set)
        for kw_set in (
            _STATUS_KEYWORDS, _DELIVERY_KEYWORDS, _FORMAT_PUBLISH_KEYWORDS,
            _DASHBOARD_FROM_ARTIFACT_KEYWORDS, _REVISION_KEYWORDS, _VOC_REQUIRED_KEYWORDS,
        )
    )


# ---------------------------------------------------------------------------
# Ephemeral expert specs
# ---------------------------------------------------------------------------

def _ephemeral_doc_format_expert() -> dict[str, Any]:
    return {
        "expert_id": "doc_format_expert",
        "display_name": "文档格式化专家",
        "task_boundary": "将已有报告/Markdown转换为目标格式（飞书云文档、PDF等）",
        "callable_skills": ["artifact_resolver", "doc_publish"],
        "non_goals": ["用户洞察分析", "数据挖掘", "VOC处理"],
        "memory_write_scope": "ephemeral_only",
        "why_generated": "任务为格式转换/发布，无需注册专家，临时生成",
    }


def _ephemeral_artifact_status_expert() -> dict[str, Any]:
    return {
        "expert_id": "artifact_status_expert",
        "display_name": "产物状态查询专家",
        "task_boundary": "查询已有任务结果或产物状态",
        "callable_skills": ["artifact_resolver", "artifact_status"],
        "non_goals": ["生成新报告", "用户洞察分析"],
        "memory_write_scope": "ephemeral_only",
        "why_generated": "任务为状态查询，无需注册专家，临时生成",
    }


def _ephemeral_artifact_delivery_expert() -> dict[str, Any]:
    return {
        "expert_id": "artifact_delivery_expert",
        "display_name": "产物交付专家",
        "task_boundary": "定位并返回已有执行结果/产物路径/内容",
        "callable_skills": ["artifact_resolver", "artifact_delivery"],
        "non_goals": ["重新生成", "用户洞察分析"],
        "memory_write_scope": "ephemeral_only",
        "why_generated": "任务为产物交付，无需注册专家，临时生成",
    }


def _ephemeral_report_revision_expert() -> dict[str, Any]:
    return {
        "expert_id": "report_revision_expert",
        "display_name": "报告修订专家",
        "task_boundary": "基于已有报告做细化/改写/润色",
        "callable_skills": ["artifact_resolver", "report_revision"],
        "non_goals": ["从零生成报告", "用户洞察分析"],
        "memory_write_scope": "ephemeral_only",
        "why_generated": "任务为报告修订，无需注册专家，临时生成",
    }


# ---------------------------------------------------------------------------
# Planner engine
# ---------------------------------------------------------------------------

class PlannerEngine:
    def __init__(self, project_root: Path, routes_payload: dict[str, Any]) -> None:
        self.project_root = project_root
        self.routes_payload = routes_payload
        self._registered_experts = self._load_registered_experts()
        self._available_skills = self._load_available_skills()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_task_context(
        self,
        user_message: str,
        reply_context: str = "",
    ) -> TaskContext:
        mentioned_files = re.findall(r"(?:\/[\w/.-]+\.(?:md|json|csv|txt|html|pdf))", user_message)
        existing_artifacts = [f for f in mentioned_files if Path(f).exists()]
        return TaskContext(
            current_user_message=user_message,
            reply_context=reply_context,
            mentioned_files=mentioned_files,
            existing_artifacts=existing_artifacts,
            available_experts=list(self._registered_experts),
            available_skills=list(self._available_skills),
        )

    def select_primary_expert(self, ctx: TaskContext) -> ExpertSelection:
        msg = ctx.current_user_message

        if _msg_contains_any(msg, _STATUS_KEYWORDS):
            return ExpertSelection(
                primary_expert_id="artifact_status_expert",
                primary_expert_source="ephemeral",
                reason="任务为状态查询，生成临时专家",
                confidence=0.95,
                candidate_experts=[],
                ephemeral_spec=_ephemeral_artifact_status_expert(),
            )

        if _msg_contains_any(msg, _DELIVERY_KEYWORDS):
            return ExpertSelection(
                primary_expert_id="artifact_delivery_expert",
                primary_expert_source="ephemeral",
                reason="任务为产物交付，生成临时专家",
                confidence=0.95,
                candidate_experts=[],
                ephemeral_spec=_ephemeral_artifact_delivery_expert(),
            )

        if _msg_contains_any(msg, _FORMAT_PUBLISH_KEYWORDS):
            return ExpertSelection(
                primary_expert_id="doc_format_expert",
                primary_expert_source="ephemeral",
                reason="任务为格式转换/文档发布，生成临时专家",
                confidence=0.92,
                candidate_experts=[],
                ephemeral_spec=_ephemeral_doc_format_expert(),
            )

        has_existing = bool(ctx.existing_artifacts)
        # Dashboard from existing artifact takes priority over plain revision
        if _msg_contains_any(msg, _DASHBOARD_FROM_ARTIFACT_KEYWORDS) and has_existing:
            if "ops_expert" in self._registered_experts:
                return ExpertSelection(
                    primary_expert_id="ops_expert",
                    primary_expert_source="registered",
                    reason="基于已有产物生成看板，选择运营专家（跳过VOC洞察）",
                    confidence=0.88,
                    candidate_experts=["ops_expert"],
                )

        if _msg_contains_any(msg, _REVISION_KEYWORDS):
            return ExpertSelection(
                primary_expert_id="report_revision_expert",
                primary_expert_source="ephemeral",
                reason="任务为基于已有报告修订，生成临时专家",
                confidence=0.90,
                candidate_experts=[],
                ephemeral_spec=_ephemeral_report_revision_expert(),
            )

        if _msg_contains_any(msg, _VOC_REQUIRED_KEYWORDS):
            if "user_analyst" in self._registered_experts:
                return ExpertSelection(
                    primary_expert_id="user_analyst",
                    primary_expert_source="registered",
                    reason="任务含VOC/用户洞察关键词，选择用户分析专家",
                    confidence=0.95,
                    candidate_experts=["user_analyst"],
                )

        # Default: if VOC keywords appear in reply_context but NOT in current_user_message,
        # do not let reply_context hijack the expert selection.
        if "ops_expert" in self._registered_experts:
            return ExpertSelection(
                primary_expert_id="ops_expert",
                primary_expert_source="registered",
                reason="无明确任务类型，默认选择运营专家",
                confidence=0.60,
                candidate_experts=list(self._registered_experts),
            )
        if self._registered_experts:
            first = next(iter(self._registered_experts))
            return ExpertSelection(
                primary_expert_id=first,
                primary_expert_source="registered",
                reason="无明确任务类型，选择首个注册专家",
                confidence=0.50,
                candidate_experts=list(self._registered_experts),
            )
        return ExpertSelection(
            primary_expert_id="generic_expert",
            primary_expert_source="ephemeral",
            reason="无注册专家，生成通用临时专家",
            confidence=0.40,
            candidate_experts=[],
        )

    def plan_task(self, ctx: TaskContext, selection: ExpertSelection) -> TaskSpec:
        msg = ctx.current_user_message

        if _msg_contains_any(msg, _STATUS_KEYWORDS):
            return TaskSpec(
                task_goal="查询任务/产物状态",
                task_type="status_lookup",
                input_kind="user_message",
                output_kind="status_report",
                requires_voc_insight=False,
                requires_existing_artifact=True,
                requires_publish=False,
                requires_status_lookup=True,
                rejection_reason_for_voc_insight="任务为状态查询，不需要VOC分析",
            )

        if _msg_contains_any(msg, _DELIVERY_KEYWORDS):
            return TaskSpec(
                task_goal="返回已有执行结果或产物",
                task_type="artifact_delivery",
                input_kind="user_message",
                output_kind="artifact_content",
                requires_voc_insight=False,
                requires_existing_artifact=True,
                requires_publish=False,
                requires_status_lookup=False,
                rejection_reason_for_voc_insight="任务为产物交付，不需要VOC分析",
            )

        if _msg_contains_any(msg, _FORMAT_PUBLISH_KEYWORDS):
            return TaskSpec(
                task_goal="转换已有报告格式或发布到平台",
                task_type="doc_format",
                input_kind="existing_report",
                output_kind="formatted_document",
                requires_voc_insight=False,
                requires_existing_artifact=True,
                requires_publish=True,
                requires_status_lookup=False,
                rejection_reason_for_voc_insight="任务为格式转换/发布，不需要重新运行VOC分析",
            )

        has_existing = bool(ctx.existing_artifacts)
        # Dashboard from existing artifact takes priority over plain revision
        if _msg_contains_any(msg, _DASHBOARD_FROM_ARTIFACT_KEYWORDS) and has_existing:
            return TaskSpec(
                task_goal="基于已有产物生成运营看板",
                task_type="dashboard_from_artifact",
                input_kind="existing_report",
                output_kind="dashboard",
                requires_voc_insight=False,
                requires_existing_artifact=True,
                requires_publish=False,
                requires_status_lookup=False,
                rejection_reason_for_voc_insight="基于已有报告生成看板，existing_artifacts中已有洞察结论",
            )

        if _msg_contains_any(msg, _REVISION_KEYWORDS):
            return TaskSpec(
                task_goal="基于已有报告进行修订/细化",
                task_type="report_revision",
                input_kind="existing_report",
                output_kind="revised_report",
                requires_voc_insight=False,
                requires_existing_artifact=True,
                requires_publish=False,
                requires_status_lookup=False,
                rejection_reason_for_voc_insight="任务基于已有报告，不需要重新运行VOC分析",
            )

        if _msg_contains_any(msg, _VOC_REQUIRED_KEYWORDS):
            return TaskSpec(
                task_goal="分析VOC/用户反馈，输出用户洞察",
                task_type="voc_analysis",
                input_kind="voc_data",
                output_kind="insight_report",
                requires_voc_insight=True,
                requires_existing_artifact=False,
                requires_publish=False,
                requires_status_lookup=False,
            )

        return TaskSpec(
            task_goal=msg[:80],
            task_type="generic",
            input_kind="unknown",
            output_kind="unknown",
            requires_voc_insight=False,
            requires_existing_artifact=False,
            requires_publish=False,
            requires_status_lookup=False,
            rejection_reason_for_voc_insight="未识别到需要VOC分析的明确信号",
        )

    def generate_pipeline(
        self,
        ctx: TaskContext,
        selection: ExpertSelection,
        spec: TaskSpec,
    ) -> DynamicPipelineSpec:
        template_match = self._find_template(spec)

        if template_match:
            pipeline_id, nodes, source = template_match
            pipeline_name = self._template_name(pipeline_id)
            is_candidate = False
        else:
            pipeline_id, nodes, source = self._build_dynamic_dag(selection, spec)
            pipeline_name = f"dynamic_{spec.task_type}"
            is_candidate = True

        final_node = nodes[-1].node_id if nodes else ""
        rejection_reason = spec.rejection_reason_for_voc_insight if not spec.requires_voc_insight else ""

        return DynamicPipelineSpec(
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
            generated_by_primary_expert=selection.primary_expert_id,
            planning_source=source,
            nodes=nodes,
            final_output_node=final_node,
            template_candidate=is_candidate,
            skipped_voc_insight_reason=rejection_reason,
            task_context_summary=ctx.current_user_message[:120],
            expert_selection=asdict(selection),
            task_spec=asdict(spec),
        )

    def validate_dynamic_pipeline(
        self,
        pipeline: DynamicPipelineSpec,
        spec: TaskSpec,
    ) -> list[str]:
        errors: list[str] = []
        if not spec.requires_voc_insight:
            voc_nodes = [n.node_id for n in pipeline.nodes if n.skill_id == "voc_insight"]
            if voc_nodes:
                errors.append(
                    f"VALIDATION_ERROR: requires_voc_insight=false 但 pipeline 包含 voc_insight 节点 "
                    f"{voc_nodes}。原因：{spec.rejection_reason_for_voc_insight}"
                )
        if not pipeline.nodes:
            errors.append("VALIDATION_ERROR: pipeline 没有任何节点")
        return errors

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_registered_experts(self) -> dict[str, dict[str, Any]]:
        experts: dict[str, dict[str, Any]] = {}
        experts_root = self.project_root / "experts"
        if not experts_root.exists():
            return experts
        for path in sorted(experts_root.glob("*/expert.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                experts[data["name"]] = data
            except Exception:
                pass
        return experts

    def _load_available_skills(self) -> dict[str, dict[str, Any]]:
        skills: dict[str, dict[str, Any]] = {}
        skills_root = self.project_root / "skills"
        if not skills_root.exists():
            return skills
        for path in sorted(skills_root.glob("*/skill.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                skills[data["name"]] = data
            except Exception:
                pass
        return skills

    def _find_template(
        self,
        spec: TaskSpec,
    ) -> tuple[str, list[DynamicPipelineSpecNode], str] | None:
        type_to_pipeline: dict[str, str] = {
            "status_lookup": "artifact_status_flow",
            "artifact_delivery": "artifact_delivery_flow",
            "doc_format": "doc_publish_flow",
            "report_revision": "report_revision_flow",
            "dashboard_from_artifact": "dashboard_from_artifact_flow",
            "voc_analysis": "insight_flow",
        }
        pipeline_id = type_to_pipeline.get(spec.task_type)
        if pipeline_id is None:
            return None
        pipelines = self.routes_payload.get("pipelines", [])
        matching = [r for r in pipelines if r.get("pipeline_id") == pipeline_id]
        if not matching:
            return None
        nodes = [self._route_to_spec_node(r) for r in matching]
        return pipeline_id, nodes, "template_reuse"

    def _route_to_spec_node(self, route: dict[str, Any]) -> DynamicPipelineSpecNode:
        supervision = route.get("supervision") or {}
        return DynamicPipelineSpecNode(
            node_id=route["node"],
            display_name=route.get("display_name", route["node"]),
            skill_id=route["node"],
            depends_on=self._normalize_deps(route),
            primary_expert=supervision.get("primary_expert"),
            secondary_experts=list(supervision.get("secondary_experts") or []),
            constraints=dict(route.get("constraints") or {}),
            user_gate=bool(route.get("user_gate")),
            optional=bool(route.get("optional")),
            final_output=bool(route.get("final_output")),
        )

    @staticmethod
    def _normalize_deps(route: dict[str, Any]) -> list[str]:
        deps: list[str] = []
        for key in ("depends_on", "trigger"):
            val = route.get(key, [])
            if isinstance(val, str):
                val = [val]
            deps.extend(val or [])
        return list(dict.fromkeys(deps))

    def _build_dynamic_dag(
        self,
        selection: ExpertSelection,
        spec: TaskSpec,
    ) -> tuple[str, list[DynamicPipelineSpecNode], str]:
        expert_id = selection.primary_expert_id
        ephemeral = selection.ephemeral_spec or {}
        callable_skills: list[str] = []
        if selection.primary_expert_source == "ephemeral":
            callable_skills = ephemeral.get("callable_skills", [])
        else:
            expert_data = self._registered_experts.get(expert_id, {})
            callable_skills = list(expert_data.get("skills", []))

        available = set(self._available_skills)
        nodes: list[DynamicPipelineSpecNode] = []
        prev: str | None = None
        for i, skill_id in enumerate(callable_skills):
            if skill_id not in available:
                continue
            is_last = i == len(callable_skills) - 1
            node = DynamicPipelineSpecNode(
                node_id=skill_id,
                display_name=self._available_skills.get(skill_id, {}).get("display_name", skill_id),
                skill_id=skill_id,
                depends_on=[prev] if prev else [],
                primary_expert=expert_id if selection.primary_expert_source == "registered" else None,
                constraints={"max_runtime": 120},
                final_output=is_last,
            )
            nodes.append(node)
            prev = skill_id

        if not nodes:
            nodes = [DynamicPipelineSpecNode(
                node_id="briefing",
                display_name="过程汇报",
                skill_id="briefing",
                constraints={"max_runtime": 60},
                final_output=True,
            )]

        pipeline_id = f"dynamic_{spec.task_type}_{expert_id}"
        return pipeline_id, nodes, "dynamic_generated"

    def _template_name(self, pipeline_id: str) -> str:
        for route in self.routes_payload.get("pipelines", []):
            if route.get("pipeline_id") == pipeline_id:
                return route.get("pipeline_name", pipeline_id)
        return pipeline_id
