"""
UserQualityFunction — 从 UnderstandingState + BoundaryMemory 派生质量要求。
纯函数，无 LLM 调用，无副作用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.understanding.schemas import BoundaryMemory, UnderstandingState

_SYSTEM_LAYER_RE = re.compile(r"新(的)?系统层|新层级|机制层|结构化层|新模块|新能力层")
_AGENT_SYS_RE = re.compile(r"agent.{0,4}system|智能体系统|pipeline.{0,4}节点|skill.{0,4}node|workflow.{0,4}节点")


@dataclass
class UserQualityFunction:
    must_separate_questions: bool = False
    must_keep_generalized_scope: bool = False
    must_avoid_negative_boundaries: list[str] = field(default_factory=list)
    must_avoid_synonym_paraphrase: bool = False
    must_add_new_system_layer: bool = False
    must_use_agent_system_mechanism: bool = False


def derive_quality_function(
    understanding_state: "UnderstandingState",
    boundary_memory: "list[BoundaryMemory]",
) -> UserQualityFunction:
    """从 UnderstandingState + BoundaryMemory 派生质量要求。"""
    qf = UserQualityFunction()
    qf.must_separate_questions = understanding_state.split_frame
    qf.must_keep_generalized_scope = understanding_state.widen_scope
    qf.must_avoid_synonym_paraphrase = understanding_state.confidence > 0.9

    neg_contents = [
        bm.content for bm in boundary_memory
        if bm.boundary_type == "negative"
    ]
    qf.must_avoid_negative_boundaries = neg_contents

    all_content = " ".join(neg_contents + list(understanding_state.negative_boundaries))
    qf.must_add_new_system_layer = bool(_SYSTEM_LAYER_RE.search(all_content))
    qf.must_use_agent_system_mechanism = bool(_AGENT_SYS_RE.search(all_content))

    return qf
