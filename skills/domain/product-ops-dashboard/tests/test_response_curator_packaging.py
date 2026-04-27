from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_insight_bundle.py"
SCRIPT_ROOT = SCRIPT_PATH.parent
if str(SCRIPT_ROOT) in sys.path:
    sys.path.remove(str(SCRIPT_ROOT))
sys.path.insert(0, str(SCRIPT_ROOT))
for module_name in (
    "derive_higher_order_insights",
    "generate_analysis_scaffold",
    "generate_insight_bundle",
    "llm_reasoning_engine",
    "presentation_report_renderer",
    "run_multisource_preflight",
    "user_chain_dependency_registry",
):
    sys.modules.pop(module_name, None)
SPEC = importlib.util.spec_from_file_location("generate_insight_bundle", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

RESP_CURATOR_PATH = Path(__file__).resolve().parents[2] / "ResponseCurator" / "scripts" / "package_primary_artifacts.py"
HAS_RESPONSE_CURATOR = RESP_CURATOR_PATH.exists()
if HAS_RESPONSE_CURATOR:
    RESP_SPEC = importlib.util.spec_from_file_location("response_curator_packager", RESP_CURATOR_PATH)
    assert RESP_SPEC and RESP_SPEC.loader
    RESP_MODULE = importlib.util.module_from_spec(RESP_SPEC)
    RESP_SPEC.loader.exec_module(RESP_MODULE)
else:
    RESP_MODULE = MODULE


class ResponseCuratorPackagingTests(unittest.TestCase):
    def test_package_primary_artifacts_rewrites_primary_files_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            main_report = root / "main_report.md"
            presentation_report = root / "presentation_main_report.md"
            presentation_brief = root / "presentation_brief.md"
            main_report.write_text("# 旧标题\n\n## 0. 问题回答\n\n- 当前前台表达将按 某种机制 去编排。\n\n正文。\n", encoding="utf-8")
            presentation_report.write_text("# 老汇报稿\n\n- 当前前台表达将按 某种机制 去编排。\n\n## 0. 问题回答\n\n- 结论。\n", encoding="utf-8")
            presentation_brief.write_text("# 旧摘要\n\n## 0. 问题回答\n\n- 当前前台表达将按 某种机制 去编排。\n", encoding="utf-8")

            request = RESP_MODULE.build_artifact_packaging_request(
                artifact_index={
                    "main_report": str(main_report),
                    "presentation_main_report": str(presentation_report),
                    "presentation_brief": str(presentation_brief),
                },
                category_name="扫地机器人",
                market="cn",
                time_scope="2026Q1",
                analysis_goal_text="回答核心用户问题",
                bundle_mode="portfolio_full",
                style_profile={},
                higher_order_artifacts={},
            )
            result = RESP_MODULE.apply_response_curator_to_primary_artifacts(request)

            self.assertEqual(len(result["packaged_artifacts"]), 3)
            if HAS_RESPONSE_CURATOR:
                self.assertEqual(result["status"], "packaged")
                self.assertFalse(result["fallback_used"])
                self.assertEqual(result["packaged_artifacts"][0]["display_primitives_plan"]["table_intensity"], "analysis_midweight_table")
                self.assertEqual(result["packaged_artifacts"][1]["display_primitives_plan"]["table_intensity"], "analysis_midweight_table")
                self.assertEqual(result["packaged_artifacts"][2]["display_primitives_plan"]["table_intensity"], "light_summary_table")
                self.assertEqual(main_report.read_text(encoding="utf-8").splitlines()[0], "# 扫地机器人 主报告")
                self.assertEqual(presentation_report.read_text(encoding="utf-8").splitlines()[0], "# 扫地机器人 正式汇报稿")
                self.assertEqual(presentation_brief.read_text(encoding="utf-8").splitlines()[0], "# 扫地机器人 汇报摘要")
                self.assertNotIn("当前前台表达将按", main_report.read_text(encoding="utf-8"))
                self.assertNotIn("当前前台表达将按", presentation_report.read_text(encoding="utf-8"))
                self.assertIn("## 0. 元信息", main_report.read_text(encoding="utf-8"))
                self.assertIn("## 0A. 执行摘要", presentation_report.read_text(encoding="utf-8"))
                self.assertIn("## 0A. 核心摘要", presentation_brief.read_text(encoding="utf-8"))
                self.assertIn("## 0B. 边界说明", main_report.read_text(encoding="utf-8"))
                self.assertIn("## 下一步动作", main_report.read_text(encoding="utf-8"))
                self.assertIn("## 0B. 边界说明", presentation_report.read_text(encoding="utf-8"))
                self.assertIn("## 下一步动作", presentation_report.read_text(encoding="utf-8"))
            else:
                self.assertEqual(result["status"], "skipped")
                self.assertTrue(result["fallback_used"])
                self.assertEqual(main_report.read_text(encoding="utf-8").splitlines()[0], "# 旧标题")

    def test_write_manifest_includes_response_curator_packaging_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "main_report.md"
            artifact.write_text("# 主报告\n", encoding="utf-8")
            manifest_path = MODULE.write_manifest(
                root,
                [artifact],
                bundle_id="demo_bundle",
                category_name="扫地机器人",
                primary_self_spu_id="ecovacs_x11",
                primary_competitor_spu_id="roborock_g30",
                bundle_mode="portfolio_full",
                response_curator_packaging={
                    "status": "packaged",
                    "mode": "deliverable_artifact_packaging",
                    "scope": "primary_artifacts_only",
                    "packaged_artifacts": [
                        {
                            "artifact_key": "main_report",
                            "path": str(artifact),
                            "status": "packaged",
                            "fallback_used": False,
                        }
                    ],
                    "packaging_version": "2026-04-03.v1",
                    "packaged_at": "2026-04-03T10:00:00",
                    "fallback_used": False,
                    "fallback_reason": "",
                },
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("response_curator_packaging", manifest)
            self.assertEqual(manifest["response_curator_packaging"]["mode"], "deliverable_artifact_packaging")
            self.assertEqual(manifest["response_curator_packaging"]["packaged_artifacts"][0]["artifact_key"], "main_report")


if __name__ == "__main__":
    unittest.main()
