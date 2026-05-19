"""
BoundaryMemory → prompt block formatter。

纯函数，无副作用，无 LLM 调用。
空列表返回空字符串，不污染 system prompt。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.understanding.schemas import BoundaryMemory


def format_boundary_block(boundaries: "list[BoundaryMemory]") -> str:
    """
    将 session 内积累的 BoundaryMemory 列表格式化为 prompt block。

    Returns:
        非空字符串（包含 block header）或空字符串（boundaries 为空时）。
    """
    if not boundaries:
        return ""

    lines: list[str] = []
    for bm in boundaries:
        lines.append(bm.to_prompt_line())

    return "【理解边界】\n" + "\n".join(lines)
