from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


_SKILL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_EXPERT_NAME_PATTERN = re.compile(r"^[a-z][A-Za-z0-9_]*$")
_SCHEDULER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_USER_ID_PATTERN = re.compile(r"^[a-z][A-Za-z0-9_]*$")
_MEMORY_ID_PATTERN = re.compile(r"^[a-z][A-Za-z0-9_]*$")
_GENERATION_ID_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


@dataclass
class HermesSkill:
    name: str
    display_name: str
    description: str
    type: str
    pipeline: str
    private_memory: bool
    root: str


@dataclass
class HermesExpert:
    name: str
    display_name: str
    description: str
    skills: list[str]
    private_memory: bool
    root: str


@dataclass
class HermesScheduler:
    name: str
    display_name: str
    description: str
    supervised_modules: list[str]
    exception_handling: str
    decision_logging: bool
    root: str


@dataclass
class HermesUser:
    user_id: str
    display_name: str
    description: str
    root: str


class HermesSkillManager:
    """Minimal local SDK for bootstrapping the example agent_system skills."""

    def __init__(self, project_name: str, root_dir: str | Path | None = None) -> None:
        self.project_name = project_name
        self.project_root = Path(root_dir) if root_dir else Path(__file__).resolve().parent
        self.skills_root = self.project_root / "skills"
        self.skills_root.mkdir(parents=True, exist_ok=True)

    def create_skill(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        type: str,
        pipeline: str,
        private_memory: bool,
    ) -> HermesSkill:
        self._validate_skill_name(name)

        skill_root = self.skills_root / name
        pipeline_root = skill_root / "pipeline"
        memory_root = skill_root / "skill_mem"

        pipeline_root.mkdir(parents=True, exist_ok=True)
        if private_memory:
            memory_root.mkdir(parents=True, exist_ok=True)

        skill = HermesSkill(
            name=name,
            display_name=display_name,
            description=description,
            type=type,
            pipeline=pipeline,
            private_memory=private_memory,
            root=str(skill_root.relative_to(self.project_root)),
        )

        self._write_metadata(skill_root, skill)
        self._write_skill_doc(skill_root, skill)
        self._write_pipeline_stub(pipeline_root, pipeline)
        if private_memory:
            self._write_memory_stub(memory_root, skill)

        return skill

    def list_skills(self) -> list[HermesSkill]:
        skills: list[HermesSkill] = []
        for metadata_path in sorted(self.skills_root.glob("*/skill.json")):
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            skills.append(HermesSkill(**payload))

        for skill in skills:
            print(
                f"{skill.name}\t{skill.display_name}\t"
                f"type={skill.type}\tpipeline={skill.pipeline}"
            )
        return skills

    @staticmethod
    def _validate_skill_name(name: str) -> None:
        if not _SKILL_NAME_PATTERN.match(name):
            raise ValueError(
                "Skill name must be lowercase snake_case and start with a letter: "
                f"{name!r}"
            )

    @staticmethod
    def _write_metadata(skill_root: Path, skill: HermesSkill) -> None:
        metadata_path = skill_root / "skill.json"
        metadata_path.write_text(
            json.dumps(asdict(skill), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_skill_doc(skill_root: Path, skill: HermesSkill) -> None:
        doc_path = skill_root / "SKILL.md"
        doc_path.write_text(
            "\n".join(
                [
                    f"# {skill.display_name}",
                    "",
                    f"- English name: `{skill.name}`",
                    f"- 中文名：{skill.display_name}",
                    f"- Type: `{skill.type}`",
                    f"- Default pipeline: `{skill.pipeline}`",
                    f"- Private memory: `{str(skill.private_memory).lower()}`",
                    "",
                    skill.description,
                    "",
                    "## Pipeline",
                    "",
                    f"默认执行入口记录在 `pipeline/{skill.pipeline}.json`。",
                    "",
                    "## Memory",
                    "",
                    "私域经验记录在 `skill_mem/`，用于沉淀该 Skill 自己的经验。",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _write_pipeline_stub(pipeline_root: Path, pipeline: str) -> None:
        pipeline_path = pipeline_root / f"{pipeline}.json"
        payload = {
            "name": pipeline,
            "version": 1,
            "steps": [],
            "status": "empty_example_pipeline",
        }
        pipeline_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_memory_stub(memory_root: Path, skill: HermesSkill) -> None:
        memory_path = memory_root / "MEMORY.md"
        if memory_path.exists():
            return
        memory_path.write_text(
            "\n".join(
                [
                    f"# {skill.display_name} 私域经验",
                    "",
                    "这里记录该 Skill 的示例经验、偏好和可复用执行线索。",
                    "",
                ]
            ),
            encoding="utf-8",
        )


class HermesSchedulerManager:
    """Minimal local SDK for bootstrapping the example agent_system scheduler."""

    def __init__(self, project_name: str, root_dir: str | Path | None = None) -> None:
        self.project_name = project_name
        self.project_root = Path(root_dir) if root_dir else Path(__file__).resolve().parent
        self.scheduler_root = self.project_root / "scheduler"
        self.skills_root = self.project_root / "skills"
        self.experts_root = self.project_root / "experts"
        self.scheduler_root.mkdir(parents=True, exist_ok=True)

    def create_scheduler(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        supervised_modules: list[str],
        exception_handling: str,
        decision_logging: bool,
    ) -> HermesScheduler:
        self._validate_scheduler_name(name)
        self._validate_supervised_modules(supervised_modules)

        scheduler_path = self.scheduler_root / name
        scheduler_path.mkdir(parents=True, exist_ok=True)

        scheduler = HermesScheduler(
            name=name,
            display_name=display_name,
            description=description,
            supervised_modules=supervised_modules,
            exception_handling=exception_handling,
            decision_logging=decision_logging,
            root=str(scheduler_path.relative_to(self.project_root)),
        )

        self._write_metadata(scheduler_path, scheduler)
        self._write_scheduler_doc(scheduler_path, scheduler)
        if decision_logging:
            self._write_decision_log_stub(scheduler_path, scheduler)

        return scheduler

    def initialize_routes(
        self,
        *,
        scheduler_name: str,
        pipelines: list[dict],
    ) -> Path:
        self._validate_scheduler_name(scheduler_name)
        scheduler_path = self.scheduler_root / scheduler_name
        if not (scheduler_path / "scheduler.json").exists():
            raise FileNotFoundError(f"Scheduler does not exist: {scheduler_name}")

        self._validate_pipeline_routes(pipelines)
        routes_path = scheduler_path / "routes.json"
        payload = {
            "scheduler": scheduler_name,
            "version": 1,
            "pipelines": pipelines,
        }
        routes_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return routes_path

    def list_schedulers(self) -> list[HermesScheduler]:
        schedulers: list[HermesScheduler] = []
        for metadata_path in sorted(self.scheduler_root.glob("*/scheduler.json")):
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            schedulers.append(HermesScheduler(**payload))

        for scheduler in schedulers:
            print(
                f"{scheduler.name}\t{scheduler.display_name}\t"
                f"modules={','.join(scheduler.supervised_modules)}\t"
                f"exception={scheduler.exception_handling}"
            )
        return schedulers

    def list_routes(self, scheduler_name: str) -> list[dict]:
        self._validate_scheduler_name(scheduler_name)
        routes_path = self.scheduler_root / scheduler_name / "routes.json"
        if not routes_path.exists():
            raise FileNotFoundError(f"Routes do not exist for scheduler: {scheduler_name}")

        payload = json.loads(routes_path.read_text(encoding="utf-8"))
        routes = payload.get("pipelines", [])
        for route in routes:
            supervision = route.get("supervision", {})
            primary = supervision.get("primary_expert")
            pipeline_id = route.get("pipeline_id", "default")
            priority = route.get("priority", "normal")
            step = route.get("step", "-")
            print(
                f"{pipeline_id}\tstep={step}\tpriority={priority}\t"
                f"{route.get('node')}\t{route.get('display_name')}\t"
                f"user_gate={route.get('user_gate')}\tprimary_expert={primary}"
            )
        return routes

    @staticmethod
    def _validate_scheduler_name(name: str) -> None:
        if not _SCHEDULER_NAME_PATTERN.match(name):
            raise ValueError(
                "Scheduler name must be lowercase snake_case and start with a letter: "
                f"{name!r}"
            )

    @staticmethod
    def _validate_supervised_modules(supervised_modules: list[str]) -> None:
        supported = {"experts", "skills"}
        unknown = sorted(set(supervised_modules) - supported)
        if unknown:
            raise ValueError(
                "Unsupported supervised modules: " + ", ".join(unknown)
            )

    def _validate_pipeline_routes(self, pipelines: list[dict]) -> None:
        if not pipelines:
            raise ValueError("Scheduler routes must include at least one pipeline node")

        for index, route in enumerate(pipelines, start=1):
            node = route.get("node")
            if not node:
                raise ValueError(f"Route #{index} is missing node")
            if not (self.skills_root / node / "skill.json").exists():
                raise FileNotFoundError(f"Route references missing skill: {node}")

            constraints = route.get("constraints") or {}
            max_runtime = constraints.get("max_runtime")
            if not isinstance(max_runtime, int) or max_runtime <= 0:
                raise ValueError(
                    f"Route {node!r} must define a positive integer max_runtime"
                )

            supervision = route.get("supervision") or {}
            primary = supervision.get("primary_expert")
            secondary = supervision.get("secondary_experts") or []
            expert_required = bool(supervision.get("expert_required"))
            if expert_required and not primary:
                raise ValueError(f"Route {node!r} requires a primary expert")

            expert_names = [name for name in [primary, *secondary] if name]
            missing_experts = [
                name
                for name in expert_names
                if not (self.experts_root / name / "expert.json").exists()
            ]
            if missing_experts:
                raise FileNotFoundError(
                    "Route references missing experts: " + ", ".join(missing_experts)
                )

    @staticmethod
    def _write_metadata(scheduler_path: Path, scheduler: HermesScheduler) -> None:
        metadata_path = scheduler_path / "scheduler.json"
        metadata_path.write_text(
            json.dumps(asdict(scheduler), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_scheduler_doc(scheduler_path: Path, scheduler: HermesScheduler) -> None:
        doc_path = scheduler_path / "SCHEDULER.md"
        module_display_names = {
            "experts": "专家层",
            "skills": "技能层",
        }
        modules = [
            f"- `{module}`（{module_display_names.get(module, module)}）"
            for module in scheduler.supervised_modules
        ]
        doc_path.write_text(
            "\n".join(
                [
                    f"# {scheduler.display_name}",
                    "",
                    f"- English name: `{scheduler.name}`",
                    f"- 中文名：{scheduler.display_name}",
                    f"- Exception handling: `{scheduler.exception_handling}`",
                    f"- Decision logging: `{str(scheduler.decision_logging).lower()}`",
                    "",
                    scheduler.description,
                    "",
                    "## Supervised Modules",
                    "",
                    *modules,
                    "",
                    "## Routes",
                    "",
                    "Pipeline 节点、约束和监督关系记录在 `routes.json`。",
                    "",
                    "## Decision Log",
                    "",
                    "调度决策记录在 `decision_log.md`。",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _write_decision_log_stub(
        scheduler_path: Path,
        scheduler: HermesScheduler,
    ) -> None:
        log_path = scheduler_path / "decision_log.md"
        if log_path.exists():
            return
        log_path.write_text(
            "\n".join(
                [
                    f"# {scheduler.display_name} 决策日志",
                    "",
                    "| 时间 | 节点 | 决策 | 原因 |",
                    "| --- | --- | --- | --- |",
                    "",
                ]
            ),
            encoding="utf-8",
        )

class HermesExpertManager:
    """Minimal local SDK for bootstrapping the example agent_system experts."""

    def __init__(self, project_name: str, root_dir: str | Path | None = None) -> None:
        self.project_name = project_name
        self.project_root = Path(root_dir) if root_dir else Path(__file__).resolve().parent
        self.experts_root = self.project_root / "experts"
        self.skills_root = self.project_root / "skills"
        self.experts_root.mkdir(parents=True, exist_ok=True)

    def create_expert(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        skills: list[str],
        private_memory: bool,
    ) -> HermesExpert:
        self._validate_expert_name(name)
        self._validate_skills(skills)

        expert_root = self.experts_root / name
        pipeline_root = expert_root / "pipeline"
        memory_root = expert_root / "expert_mem"

        pipeline_root.mkdir(parents=True, exist_ok=True)
        if private_memory:
            memory_root.mkdir(parents=True, exist_ok=True)

        expert = HermesExpert(
            name=name,
            display_name=display_name,
            description=description,
            skills=skills,
            private_memory=private_memory,
            root=str(expert_root.relative_to(self.project_root)),
        )

        self._write_metadata(expert_root, expert)
        self._write_expert_doc(expert_root, expert)
        self._write_pipeline_stub(pipeline_root, expert)
        if private_memory:
            self.initialize_private_memory(name)

        return expert

    def initialize_private_memory(self, expert_name: str) -> Path:
        self._validate_expert_name(expert_name)
        expert_root = self.experts_root / expert_name
        if not expert_root.exists():
            raise FileNotFoundError(f"Expert does not exist: {expert_name}")

        memory_root = expert_root / "expert_mem"
        memory_root.mkdir(parents=True, exist_ok=True)
        memory_path = memory_root / "MEMORY.md"
        if not memory_path.exists():
            memory_path.write_text(
                "\n".join(
                    [
                        f"# {expert_name} 私域经验",
                        "",
                        "这里记录该专家的示例经验、任务偏好和跨 Skill 协同线索。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        return memory_root

    def create_pipeline(
        self,
        *,
        expert_name: str,
        pipeline_nodes: list[dict],
        pipeline_name: str = "default_pipeline",
    ) -> Path:
        self._validate_expert_name(expert_name)
        expert_root = self.experts_root / expert_name
        metadata_path = expert_root / "expert.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Expert does not exist: {expert_name}")

        expert = HermesExpert(**json.loads(metadata_path.read_text(encoding="utf-8")))
        self._validate_pipeline_nodes(pipeline_nodes, expert)

        pipeline_root = expert_root / "pipeline"
        pipeline_root.mkdir(parents=True, exist_ok=True)
        pipeline_path = pipeline_root / f"{pipeline_name}.json"
        payload = {
            "name": pipeline_name,
            "version": 1,
            "expert": expert.name,
            "skills": expert.skills,
            "nodes": pipeline_nodes,
            "status": "example_pipeline_defined",
        }
        pipeline_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return pipeline_path

    def list_experts(self) -> list[HermesExpert]:
        experts: list[HermesExpert] = []
        for metadata_path in sorted(self.experts_root.glob("*/expert.json")):
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            experts.append(HermesExpert(**payload))

        for expert in experts:
            print(
                f"{expert.name}\t{expert.display_name}\t"
                f"skills={','.join(expert.skills)}"
            )
        return experts

    @staticmethod
    def _validate_expert_name(name: str) -> None:
        if not _EXPERT_NAME_PATTERN.match(name):
            raise ValueError(
                "Expert name must start with a letter and contain only "
                f"letters, digits, or underscores: {name!r}"
            )

    def _validate_skills(self, skills: list[str]) -> None:
        if not skills:
            raise ValueError("Expert must reference at least one skill")

        missing = [
            skill_name
            for skill_name in skills
            if not (self.skills_root / skill_name / "skill.json").exists()
        ]
        if missing:
            raise FileNotFoundError(
                "Expert references missing skills: " + ", ".join(missing)
            )

    def _validate_pipeline_nodes(
        self,
        pipeline_nodes: list[dict],
        expert: HermesExpert,
    ) -> None:
        if not pipeline_nodes:
            raise ValueError("Expert pipeline must contain at least one node")

        for index, pipeline_node in enumerate(pipeline_nodes, start=1):
            node_name = pipeline_node.get("node")
            if not node_name:
                raise ValueError(f"Pipeline node #{index} is missing 'node'")
            if not (self.skills_root / node_name / "skill.json").exists():
                raise FileNotFoundError(f"Pipeline node references missing skill: {node_name}")
            if node_name not in expert.skills:
                raise ValueError(
                    f"Pipeline node {node_name!r} is not callable by expert {expert.name!r}"
                )

            primary_expert = pipeline_node.get("primary_expert")
            if primary_expert and not (self.experts_root / primary_expert / "expert.json").exists():
                raise FileNotFoundError(
                    f"Pipeline node references missing primary expert: {primary_expert}"
                )

            secondary_experts = pipeline_node.get("secondary_experts", [])
            if not isinstance(secondary_experts, list):
                raise TypeError("Pipeline node 'secondary_experts' must be a list")
            missing_secondary = [
                secondary_expert
                for secondary_expert in secondary_experts
                if not (self.experts_root / secondary_expert / "expert.json").exists()
            ]
            if missing_secondary:
                raise FileNotFoundError(
                    "Pipeline node references missing secondary experts: "
                    + ", ".join(missing_secondary)
                )

    @staticmethod
    def _write_metadata(expert_root: Path, expert: HermesExpert) -> None:
        metadata_path = expert_root / "expert.json"
        metadata_path.write_text(
            json.dumps(asdict(expert), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _write_expert_doc(self, expert_root: Path, expert: HermesExpert) -> None:
        doc_path = expert_root / "EXPERT.md"
        skill_rows = []
        base_weights = [90, 80, 70, 60, 50]
        purpose_by_type = {
            "analysis": "输入盘点 / 分析",
            "report_generation": "生成 / 输出整理",
            "ui_render": "渲染 / 交付呈现",
            "analysis_assist": "复杂判断 / 辅助复核",
            "status_report": "过程汇报 / 仿人汇报",
            "audit": "审计 / 核查",
        }
        for index, skill_name in enumerate(expert.skills):
            metadata_path = self.skills_root / skill_name / "skill.json"
            display_name = skill_name
            skill_type = ""
            if metadata_path.exists():
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                display_name = payload.get("display_name", skill_name)
                skill_type = payload.get("type", "")
            base_weight = base_weights[index] if index < len(base_weights) else 50
            purpose = purpose_by_type.get(skill_type, "分析 / 生成 / 核查")
            if index == 0:
                strategy = "高权重默认加载"
            elif skill_type == "audit":
                strategy = "关键节点默认加载"
            elif skill_type == "status_report":
                strategy = "仿人汇报触发加载"
            elif base_weight >= 70:
                strategy = "条件满足时加载"
            else:
                strategy = "辅助或观察加载"
            status = "active" if base_weight >= 70 else "watch"
            skill_rows.append(
                f"| `{skill_name}` | {display_name} | {base_weight} | {purpose} | {strategy} | {status} |"
            )
        template_path = self.project_root / "EXPERT_LAYER_TEMPLATE.md"
        if template_path.exists():
            content = template_path.read_text(encoding="utf-8")
        else:
            content = "\n".join(
                [
                    "# Hermes Agent System 专家层模板",
                    "",
                    "## 职责边界",
                    "",
                    "| 项目 | 内容 |",
                    "| --- | --- |",
                    "| 专家 ID | `[expert_id]` |",
                    "| 专家名称 | `[expert_display_name]` |",
                    "| 业务范围 | `[business_scope]` |",
                    "",
                    "## 默认 Skill 多重加载",
                    "",
                    "| Skill ID | Skill 名称 | Base Weight | 默认用途 | 加载策略 | 当前状态 |",
                    "| --- | --- | --- | --- | --- | --- |",
                    "| `[skill_id]` | `[skill_name]` | 90 | 分析 / 生成 / 核查 | 高权重默认加载 | active |",
                    "",
                    "### 权重公式",
                    "",
                    "```text",
                    "Skill_Weight = Base_Weight + Success_Rate * 0.4 + Output_Quality * 0.3 - Exception_Count * 0.2 + Dynamic_Coverage_Frequency * -0.1",
                    "```",
                    "",
                ]
            )

        content = re.sub(r"^# .+$", f"# {expert.display_name}", content, count=1, flags=re.MULTILINE)
        content = content.replace("[expert_id]", expert.name)
        content = content.replace("[expert_display_name]", expert.display_name)
        content = content.replace("[business_scope]", expert.description)
        content = content.replace(
            "[primary_skill_id]",
            expert.skills[0] if expert.skills else "skill_id",
        )
        content = content.replace(
            "[private_memory_status]",
            f"{'启用' if expert.private_memory else '未启用'}，记录在 `expert_mem/`",
        )

        table_pattern = (
            r"(\| Skill ID \| Skill 名称 \| Base Weight \| 默认用途 \| 加载策略 \| 当前状态 \|\n"
            r"\| --- \| --- \| --- \| --- \| --- \| --- \|\n)"
            r"(?:\|.*\|\n)+"
            r"(?=\n### (?:3|4)\.1 权重公式)"
        )
        replacement = r"\1" + "\n".join(skill_rows) + "\n"
        content, replacements = re.subn(table_pattern, replacement, content, count=1)
        if replacements != 1:
            skill_table = "\n".join(
                [
                    "## 默认 Skill 多重加载",
                    "",
                    "| Skill ID | Skill 名称 | Base Weight | 默认用途 | 加载策略 | 当前状态 |",
                    "| --- | --- | --- | --- | --- | --- |",
                    *skill_rows,
                    "",
                ]
            )
            content = content.rstrip() + "\n\n" + skill_table

        doc_path.write_text(content.rstrip() + "\n", encoding="utf-8")

    @staticmethod
    def _write_pipeline_stub(pipeline_root: Path, expert: HermesExpert) -> None:
        pipeline_path = pipeline_root / "default_pipeline.json"
        payload = {
            "name": "default_pipeline",
            "version": 1,
            "expert": expert.name,
            "skills": expert.skills,
            "steps": [],
            "status": "empty_example_pipeline",
        }
        pipeline_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


class HermesMemoryManager:
    """Minimal local SDK for bootstrapping user-specific memory examples."""

    def __init__(self, project_name: str, root_dir: str | Path | None = None) -> None:
        self.project_name = project_name
        self.project_root = Path(root_dir) if root_dir else Path(__file__).resolve().parent
        self.memory_root = self.project_root / "memory"
        self.users_root = self.memory_root / "user_mem"
        self.skills_root = self.project_root / "skills"
        self.users_root.mkdir(parents=True, exist_ok=True)

    def create_user(
        self,
        *,
        user_id: str,
        display_name: str,
        description: str = "",
    ) -> HermesUser:
        self._validate_user_id(user_id)

        user_root = self.users_root / user_id
        user_root.mkdir(parents=True, exist_ok=True)

        user = HermesUser(
            user_id=user_id,
            display_name=display_name,
            description=description,
            root=str(user_root.relative_to(self.project_root)),
        )

        self._write_user_metadata(user_root, user)
        self._write_user_doc(user_root, user)
        return user

    def initialize_private_memory(self, user_id: str) -> Path:
        user_root = self._require_user(user_id)
        memories_root = user_root / "memories"
        memories_root.mkdir(parents=True, exist_ok=True)

        memory_path = user_root / "MEMORY.md"
        if not memory_path.exists():
            memory_path.write_text(
                "\n".join(
                    [
                        f"# {user_id} 用户私域经验",
                        "",
                        "这里记录该用户的对话记忆、偏好和个体差异化线索。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        return memories_root

    def update_user_preferences(self, *, user_id: str, preferences: dict) -> Path:
        user_root = self._require_user(user_id)
        self._validate_preferences(preferences)

        preferences_path = user_root / "preferences.json"
        payload = {
            "user_id": user_id,
            "version": 1,
            "preferences": preferences,
        }
        preferences_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return preferences_path

    def add_memory(
        self,
        *,
        user_id: str,
        memory_id: str,
        content: str,
        timestamp: str,
        version: int | None = None,
        weight: float | None = None,
        **extra_fields,
    ) -> Path:
        self._validate_memory_id(memory_id)
        self._validate_timestamp(timestamp)
        memories_root = self.initialize_private_memory(user_id=user_id)

        memory_path = memories_root / f"{memory_id}.json"
        payload = {
            "user_id": user_id,
            "memory_id": memory_id,
            "content": content,
            "timestamp": timestamp,
        }
        if version is not None:
            payload["version"] = version
        if weight is not None:
            payload["weight"] = weight
        payload.update(extra_fields)
        memory_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if version is not None:
            self._write_memory_version(memories_root, payload)
        return memory_path

    def archive_memory_versions(
        self,
        *,
        user_id: str,
        memory_id: str,
        keep_latest: int,
    ) -> list[Path]:
        self._validate_memory_id(memory_id)
        if keep_latest < 1:
            raise ValueError("keep_latest must be greater than zero")

        user_root = self._require_user(user_id)
        versions_root = user_root / "versions" / memory_id
        if not versions_root.exists():
            return []

        version_files = sorted(
            versions_root.glob("v*.json"),
            key=self._version_sort_key,
            reverse=True,
        )
        archive_root = user_root / "archive" / memory_id
        archive_root.mkdir(parents=True, exist_ok=True)

        archived_paths: list[Path] = []
        for version_path in version_files[keep_latest:]:
            archive_path = archive_root / version_path.name
            version_path.replace(archive_path)
            archived_paths.append(archive_path)
        return archived_paths

    def log_memory_operation(
        self,
        *,
        user_id: str,
        memory_id: str,
        action_type: str,
        metadata: dict | None = None,
    ) -> Path:
        self._require_user(user_id)
        self._validate_memory_id(memory_id)
        supported_actions = {"add", "update", "delete", "archive", "recall"}
        if action_type not in supported_actions:
            raise ValueError(
                f"action_type must be one of {sorted(supported_actions)}: "
                f"{action_type!r}"
            )

        log_root = self.memory_root / "operation_logs"
        log_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat()
        log_path = log_root / f"{user_id}_{memory_id}_{action_type}_{timestamp}.json"
        payload = {
            "user_id": user_id,
            "memory_id": memory_id,
            "action": action_type,
            "timestamp": timestamp,
            "metadata": metadata or {},
        }
        log_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return log_path

    def list_users(self) -> list[HermesUser]:
        users: list[HermesUser] = []
        for metadata_path in sorted(self.users_root.glob("*/user.json")):
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            users.append(HermesUser(**payload))

        for user in users:
            print(f"{user.user_id}\t{user.display_name}\troot={user.root}")
        return users

    def list_user_memory(self, user_id: str) -> list[dict]:
        user_root = self._require_user(user_id)
        memories: list[dict] = []
        for memory_path in sorted((user_root / "memories").glob("*.json")):
            memories.append(json.loads(memory_path.read_text(encoding="utf-8")))

        for memory in memories:
            print(
                f"{memory.get('memory_id')}\t{memory.get('timestamp')}\t"
                f"{memory.get('content')}"
            )
        return memories

    def get_user_preferences(self, *, user_id: str) -> dict:
        user_root = self._require_user(user_id)
        preferences_path = user_root / "preferences.json"
        if not preferences_path.exists():
            print("{}")
            return {}

        payload = json.loads(preferences_path.read_text(encoding="utf-8"))
        preferences = payload.get("preferences", {})
        print(json.dumps(preferences, ensure_ascii=False, indent=2))
        return preferences

    def _require_user(self, user_id: str) -> Path:
        self._validate_user_id(user_id)
        user_root = self.users_root / user_id
        if not (user_root / "user.json").exists():
            raise FileNotFoundError(f"User does not exist: {user_id}")
        return user_root

    @staticmethod
    def _validate_user_id(user_id: str) -> None:
        if not _USER_ID_PATTERN.match(user_id):
            raise ValueError(
                "User id must start with a letter and contain only "
                f"letters, digits, or underscores: {user_id!r}"
            )

    @staticmethod
    def _validate_memory_id(memory_id: str) -> None:
        if not _MEMORY_ID_PATTERN.match(memory_id):
            raise ValueError(
                "Memory id must start with a letter and contain only "
                f"letters, digits, or underscores: {memory_id!r}"
            )

    @staticmethod
    def _validate_timestamp(timestamp: str) -> None:
        try:
            datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ValueError(f"Timestamp must use ISO format: {timestamp!r}") from exc

    def _validate_preferences(self, preferences: dict) -> None:
        if not isinstance(preferences, dict):
            raise TypeError("User preferences must be a dictionary")

        preferred_skills = preferences.get("preferred_skills", [])
        if not isinstance(preferred_skills, list):
            raise TypeError("Preference 'preferred_skills' must be a list")

        missing_skills = [
            skill_name
            for skill_name in preferred_skills
            if not (self.skills_root / skill_name / "skill.json").exists()
        ]
        if missing_skills:
            raise FileNotFoundError(
                "User preferences reference missing skills: "
                + ", ".join(missing_skills)
            )

    @staticmethod
    def _write_memory_version(memories_root: Path, payload: dict) -> None:
        memory_id = payload["memory_id"]
        version = int(payload["version"])
        versions_root = memories_root.parent / "versions" / memory_id
        versions_root.mkdir(parents=True, exist_ok=True)
        version_path = versions_root / f"v{version:03d}.json"
        version_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _version_sort_key(version_path: Path) -> int:
        match = re.search(r"v(\d+)\.json$", version_path.name)
        if not match:
            return 0
        return int(match.group(1))

    @staticmethod
    def _write_user_metadata(user_root: Path, user: HermesUser) -> None:
        metadata_path = user_root / "user.json"
        metadata_path.write_text(
            json.dumps(asdict(user), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_user_doc(user_root: Path, user: HermesUser) -> None:
        doc_path = user_root / "USER.md"
        doc_path.write_text(
            "\n".join(
                [
                    f"# {user.display_name}",
                    "",
                    f"- User ID: `{user.user_id}`",
                    "",
                    user.description,
                    "",
                    "## Preferences",
                    "",
                    "用户偏好记录在 `preferences.json`。",
                    "",
                    "## Memory",
                    "",
                    "用户私域经验记录在 `MEMORY.md` 和 `memories/`。",
                    "",
                ]
            ),
            encoding="utf-8",
        )


class HermesAuditManager:
    """Minimal local SDK for storing and reading generation audit logs."""

    REQUIRED_LOG_FIELDS = {
        "generation_id",
        "module",
        "display_name",
        "step",
        "status",
        "input",
        "output",
        "expert_feedback",
        "user_gate",
        "scheduler_monitor",
        "errors",
    }

    def __init__(self, project_name: str, root_dir: str | Path | None = None) -> None:
        self.project_name = project_name
        self.project_root = Path(root_dir) if root_dir else Path(__file__).resolve().parent
        self.audit_root = self.project_root / "audit"
        self.logs_root = self.audit_root / "logs"
        self.skills_root = self.project_root / "skills"
        self.experts_root = self.project_root / "experts"
        self.logs_root.mkdir(parents=True, exist_ok=True)

    def save_log(self, log_entry: dict) -> Path:
        self._validate_log_entry(log_entry)
        generation_id = log_entry["generation_id"]
        log_path = self.logs_root / f"{generation_id}.json"

        payload = {
            "version": 1,
            **log_entry,
        }
        log_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._update_index(payload)
        return log_path

    def list_logs(self) -> list[dict]:
        logs: list[dict] = []
        for log_path in sorted(self.logs_root.glob("*.json")):
            logs.append(json.loads(log_path.read_text(encoding="utf-8")))

        for log in logs:
            print(
                f"{log.get('generation_id')}\t{log.get('module')}\t"
                f"step={log.get('step')}\tstatus={log.get('status')}"
            )
        return logs

    def get_log(self, generation_id: str) -> dict:
        self._validate_generation_id(generation_id)
        log_path = self.logs_root / f"{generation_id}.json"
        if not log_path.exists():
            raise FileNotFoundError(f"Audit log does not exist: {generation_id}")

        payload = json.loads(log_path.read_text(encoding="utf-8"))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload

    def _validate_log_entry(self, log_entry: dict) -> None:
        if not isinstance(log_entry, dict):
            raise TypeError("Audit log entry must be a dictionary")

        missing_fields = sorted(self.REQUIRED_LOG_FIELDS - set(log_entry))
        if missing_fields:
            raise ValueError(
                "Audit log entry is missing required fields: "
                + ", ".join(missing_fields)
            )

        generation_id = log_entry["generation_id"]
        self._validate_generation_id(generation_id)

        module_name = log_entry["module"]
        if not (self.skills_root / module_name / "skill.json").exists():
            raise FileNotFoundError(f"Audit log references missing module skill: {module_name}")

        status = log_entry["status"]
        supported_statuses = {"success", "failed", "running", "blocked", "skipped"}
        if status not in supported_statuses:
            raise ValueError(
                f"Audit log status must be one of {sorted(supported_statuses)}: {status!r}"
            )

        for field_name in ("input", "output", "expert_feedback"):
            if not isinstance(log_entry[field_name], dict):
                raise TypeError(f"Audit log field {field_name!r} must be a dictionary")

        for field_name in ("user_gate", "scheduler_monitor"):
            if not isinstance(log_entry[field_name], bool):
                raise TypeError(f"Audit log field {field_name!r} must be a boolean")

        errors = log_entry["errors"]
        if not isinstance(errors, list):
            raise TypeError("Audit log field 'errors' must be a list")

        self._validate_expert_feedback(log_entry["expert_feedback"])

    def _validate_expert_feedback(self, expert_feedback: dict) -> None:
        primary = expert_feedback.get("primary")
        secondary = expert_feedback.get("secondary", [])

        if primary and not (self.experts_root / primary / "expert.json").exists():
            raise FileNotFoundError(
                f"Audit log references missing primary expert: {primary}"
            )
        if not isinstance(secondary, list):
            raise TypeError("Audit log expert_feedback.secondary must be a list")

        missing_secondary = [
            expert_name
            for expert_name in secondary
            if not (self.experts_root / expert_name / "expert.json").exists()
        ]
        if missing_secondary:
            raise FileNotFoundError(
                "Audit log references missing secondary experts: "
                + ", ".join(missing_secondary)
            )

    @staticmethod
    def _validate_generation_id(generation_id: str) -> None:
        if not _GENERATION_ID_PATTERN.match(generation_id):
            raise ValueError(
                "Generation id must start with an uppercase letter and contain only "
                f"letters, digits, or underscores: {generation_id!r}"
            )

    def _update_index(self, log_payload: dict) -> None:
        index_path = self.audit_root / "index.json"
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
        else:
            index = {"version": 1, "logs": []}

        summary = {
            "generation_id": log_payload["generation_id"],
            "module": log_payload["module"],
            "display_name": log_payload["display_name"],
            "step": log_payload["step"],
            "status": log_payload["status"],
            "user_gate": log_payload["user_gate"],
            "scheduler_monitor": log_payload["scheduler_monitor"],
        }
        index["logs"] = [
            item
            for item in index.get("logs", [])
            if item.get("generation_id") != summary["generation_id"]
        ]
        index["logs"].append(summary)
        index["logs"].sort(key=lambda item: item["generation_id"])
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
