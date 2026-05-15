"""Humanizer-zh bundled skill 的聚焦验收。"""

import json
from pathlib import Path
import shutil
from unittest.mock import patch

from agent.prompt_builder import (
    build_skills_system_prompt,
    clear_skills_system_prompt_cache,
)
from agent.skill_commands import (
    resolve_skill_command_key,
    scan_skill_commands,
)
from agent.skill_utils import extract_skill_description, parse_frontmatter
from tools.skills_sync import _read_manifest, sync_skills
from tools.skills_tool import skill_view


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "writing" / "humanizer-zh"
SKILL_MD = SKILL_DIR / "SKILL.md"


def _install_skill_into_home(tmp_path: Path) -> Path:
    target = tmp_path / "skills" / "writing" / "humanizer-zh"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SKILL_DIR, target)
    return target


def test_humanizer_zh_frontmatter_prioritizes_chinese_triggers():
    frontmatter, body = parse_frontmatter(SKILL_MD.read_text(encoding="utf-8"))

    assert frontmatter["name"] == "humanizer-zh"
    assert frontmatter["license"] == "MIT"
    assert frontmatter["metadata"]["hermes"]["homepage"] == (
        "https://github.com/op7418/Humanizer-zh"
    )

    indexed_description = extract_skill_description(frontmatter)
    assert len(indexed_description) <= 60
    assert "中文润色" in indexed_description
    assert "去AI味" in indexed_description
    assert "更自然" in indexed_description
    assert "别太AI" in indexed_description

    assert "不新增事实、承诺、责任归因" in body
    assert "Markdown" in body
    assert "代码块" in body
    assert "不协助欺骗 AI 检测器" in body
    assert "5月15日" in body
    assert "12%" in body
    assert "不要新增完成承诺" in body


def test_humanizer_zh_appears_in_skills_system_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _install_skill_into_home(tmp_path)

    clear_skills_system_prompt_cache(clear_snapshot=True)
    try:
        prompt = build_skills_system_prompt()
    finally:
        clear_skills_system_prompt_cache(clear_snapshot=True)

    assert "writing:" in prompt
    assert "- humanizer-zh:" in prompt
    assert "中文润色" in prompt
    assert "去AI味" in prompt


def test_humanizer_zh_respects_disabled_skills(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _install_skill_into_home(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "skills:\n  disabled: [humanizer-zh]\n", encoding="utf-8"
    )

    clear_skills_system_prompt_cache(clear_snapshot=True)
    try:
        prompt = build_skills_system_prompt()
    finally:
        clear_skills_system_prompt_cache(clear_snapshot=True)

    assert "humanizer-zh" not in prompt


def test_humanizer_zh_registers_slash_command(tmp_path):
    installed = _install_skill_into_home(tmp_path)

    with patch("tools.skills_tool.SKILLS_DIR", tmp_path / "skills"):
        commands = scan_skill_commands()

    assert "/humanizer-zh" in commands
    assert commands["/humanizer-zh"]["name"] == "humanizer-zh"
    assert commands["/humanizer-zh"]["skill_dir"] == str(installed)
    assert resolve_skill_command_key("humanizer_zh") == "/humanizer-zh"


def test_humanizer_zh_skill_view_loads_body(tmp_path):
    _install_skill_into_home(tmp_path)

    with patch("tools.skills_tool.SKILLS_DIR", tmp_path / "skills"):
        result = json.loads(skill_view("humanizer-zh"))

    assert result["success"] is True
    assert result["name"] == "humanizer-zh"
    assert result["skill_dir"].endswith("skills/writing/humanizer-zh")
    assert "中文自然润色" in result["content"]
    assert "不新增事实、承诺、责任归因" in result["content"]
    assert "不协助欺骗 AI 检测器" in result["content"]
    assert "Markdown" in result["content"]
    assert "代码块" in result["content"]


def test_humanizer_zh_bundled_sync_copies_skill_from_repo(tmp_path):
    skills_dir = tmp_path / "user-skills"
    manifest_file = skills_dir / ".bundled_manifest"

    with (
        patch("tools.skills_sync._get_bundled_dir", return_value=REPO_ROOT / "skills"),
        patch("tools.skills_sync.SKILLS_DIR", skills_dir),
        patch("tools.skills_sync.MANIFEST_FILE", manifest_file),
    ):
        result = sync_skills(quiet=True)
        manifest = _read_manifest()

    assert "humanizer-zh" in result["copied"]
    assert "humanizer-zh" in manifest
    assert len(manifest["humanizer-zh"]) == 32

    synced = skills_dir / "writing" / "humanizer-zh"
    assert (synced / "SKILL.md").exists()
    assert (synced / "LICENSE").exists()
    assert "中文润色" in (synced / "SKILL.md").read_text(encoding="utf-8")
