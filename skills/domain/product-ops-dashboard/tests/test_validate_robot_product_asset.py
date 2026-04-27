from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_robot_product_asset.py"
spec = importlib.util.spec_from_file_location("validate_robot_product_asset", SCRIPT_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ValidateRobotProductAssetTests(unittest.TestCase):
    def test_examples_and_harness_are_present(self) -> None:
        report = module.validate_robot_product_asset()
        self.assertTrue(report["passed"])

    def test_manifest_missing_main_report_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "artifact_manifest.json"
            manifest_path.write_text(
                json.dumps({"artifact_index": {"artifact_manifest": str(manifest_path)}}, ensure_ascii=False),
                encoding="utf-8",
            )
            report = module.validate_robot_product_asset(str(manifest_path))
        self.assertFalse(report["passed"])
        self.assertIn("bundle validation failed", report["blockers"])

    def test_manifest_missing_presentation_report_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "artifact_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "artifact_index": {
                            "main_report": str(Path(temp_dir) / "main_report.md"),
                            "artifact_manifest": str(manifest_path),
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            report = module.validate_robot_product_asset(str(manifest_path))
        self.assertFalse(report["passed"])
        self.assertIn("bundle validation failed", report["blockers"])

    def test_manifest_with_incomplete_presentation_report_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "artifact_manifest.json"
            main_report_path = Path(temp_dir) / "main_report.md"
            presentation_report_path = Path(temp_dir) / "presentation_main_report.md"
            main_report_path.write_text("# main\n", encoding="utf-8")
            presentation_report_path.write_text("# short\n\n## 0. 问题回答\n", encoding="utf-8")
            manifest_path.write_text(
                json.dumps(
                    {
                        "artifact_index": {
                            "main_report": str(main_report_path),
                            "presentation_main_report": str(presentation_report_path),
                            "artifact_manifest": str(manifest_path),
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            bundle_validation = module.validate_robot_product_bundle(str(manifest_path))
        self.assertFalse(bundle_validation["passed"])
        self.assertTrue(bundle_validation["report_blockers"])


if __name__ == "__main__":
    unittest.main()
