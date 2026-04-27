"""Tests for Feishu tools — registration, schema validation, and doc fallback behavior."""

import importlib
import json
import unittest
from unittest.mock import Mock, patch

import tools.feishu_doc_tool as feishu_doc_tool
from tools.registry import registry

# Trigger tool discovery so feishu tools get registered
importlib.import_module("tools.feishu_doc_tool")
importlib.import_module("tools.feishu_drive_tool")
importlib.import_module("tools.feishu_sheet_tool")


class TestFeishuToolRegistration(unittest.TestCase):
    """Verify feishu tools are registered and have valid schemas."""

    EXPECTED_TOOLS = {
        "feishu_doc_read": "feishu_doc",
        "feishu_sheet_read": "feishu_sheet",
        "feishu_sheet_write": "feishu_sheet",
        "feishu_drive_list_comments": "feishu_drive",
        "feishu_drive_list_comment_replies": "feishu_drive",
        "feishu_drive_reply_comment": "feishu_drive",
        "feishu_drive_add_comment": "feishu_drive",
    }

    def test_all_tools_registered(self):
        for tool_name, toolset in self.EXPECTED_TOOLS.items():
            entry = registry.get_entry(tool_name)
            self.assertIsNotNone(entry, f"{tool_name} not registered")
            self.assertEqual(entry.toolset, toolset)

    def test_schemas_have_required_fields(self):
        for tool_name in self.EXPECTED_TOOLS:
            entry = registry.get_entry(tool_name)
            schema = entry.schema
            self.assertIn("name", schema)
            self.assertEqual(schema["name"], tool_name)
            self.assertIn("description", schema)
            self.assertIn("parameters", schema)
            self.assertIn("type", schema["parameters"])
            self.assertEqual(schema["parameters"]["type"], "object")

    def test_handlers_are_callable(self):
        for tool_name in self.EXPECTED_TOOLS:
            entry = registry.get_entry(tool_name)
            self.assertTrue(callable(entry.handler))

    def test_doc_read_schema_params(self):
        entry = registry.get_entry("feishu_doc_read")
        props = entry.schema["parameters"].get("properties", {})
        self.assertIn("doc_token", props)

    def test_drive_tools_require_file_token(self):
        for tool_name in self.EXPECTED_TOOLS:
            if tool_name in {"feishu_doc_read", "feishu_sheet_read", "feishu_sheet_write"}:
                continue
            entry = registry.get_entry(tool_name)
            props = entry.schema["parameters"].get("properties", {})
            self.assertIn("file_token", props, f"{tool_name} missing file_token param")
            self.assertIn("file_type", props, f"{tool_name} missing file_type param")


class TestFeishuDocReadFallback(unittest.TestCase):
    """Verify short doc bodies fall back to blocks and embedded sheet previews."""

    def test_prefers_raw_content_when_body_is_already_rich(self):
        client = Mock()
        request_calls = []

        def fake_do_request(_client, method, uri, paths=None, queries=None, body=None):
            request_calls.append((method, uri, paths, queries, body))
            self.assertEqual(uri, feishu_doc_tool._RAW_CONTENT_URI)
            return 0, "success", {
                "content": (
                    "标题\n"
                    "正文第一段，内容足够长，已经包含明确的业务背景、目标范围和当前判断。\n"
                    "正文第二段，继续补充上下文，包括约束条件、风险提示和后续动作建议。"
                )
            }

        with patch.object(feishu_doc_tool, "get_client", return_value=client), \
             patch.object(feishu_doc_tool, "_do_request", side_effect=fake_do_request):
            result = json.loads(
                feishu_doc_tool._handle_feishu_doc_read({"doc_token": "doc_123"}, task_id="task-1")
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["content"], result["raw_content"])
        self.assertFalse(result["blocks_fallback_used"])
        self.assertEqual(result["embedded_resources"], [])
        self.assertEqual(len(request_calls), 1)

    def test_short_doc_body_includes_embedded_sheet_preview(self):
        client = Mock()
        request_calls = []

        blocks_payload = [
            {
                "block_id": "doc_123",
                "block_type": 1,
                "page": {"elements": [{"text_run": {"content": "AI看板建设启动 副本"}}]},
            },
            {
                "block_id": "head_1",
                "block_type": 3,
                "heading1": {
                    "elements": [{"text_run": {"content": "智能体业务建设需求表（模块级）"}}]
                },
                "parent_id": "doc_123",
            },
            {
                "block_id": "sheet_1",
                "block_type": 30,
                "sheet": {"token": "RX8hsMOachgMz2tL2TrcIcKEnjg_5cfRcx"},
                "parent_id": "doc_123",
            },
        ]

        def fake_do_request(_client, method, uri, paths=None, queries=None, body=None):
            request_calls.append((method, uri, paths, queries, body))
            if uri == feishu_doc_tool._RAW_CONTENT_URI:
                return 0, "success", {
                    "content": "AI看板建设启动 副本\n智能体业务建设需求表（模块级）"
                }
            if uri == feishu_doc_tool._BLOCKS_URI:
                return 0, "success", {"has_more": False, "items": blocks_payload}
            raise AssertionError(f"unexpected uri: {uri}")

        fake_sheet_preview = {
            "type": "sheet",
            "raw_token": "RX8hsMOachgMz2tL2TrcIcKEnjg_5cfRcx",
            "spreadsheet_token": "RX8hsMOachgMz2tL2TrcIcKEnjg",
            "sheet_id": "5cfRcx",
            "spreadsheet_title": "",
            "sheet_title": "",
            "selected_range": "5cfRcx!A1:H10",
            "values": [
                ["层级", "模块", "核心指标/分析维度", "周期"],
                ["生", "产品规划", "VOC分析（电商VOC）", "一期（5月底）"],
            ],
        }

        with patch.object(feishu_doc_tool, "get_client", return_value=client), \
             patch.object(feishu_doc_tool, "_do_request", side_effect=fake_do_request), \
             patch.object(
                 feishu_doc_tool,
                 "_read_embedded_sheet_preview",
                 return_value=fake_sheet_preview,
             ) as mock_sheet_preview:
            result = json.loads(
                feishu_doc_tool._handle_feishu_doc_read({"doc_token": "doc_123"}, task_id="task-1")
            )

        self.assertTrue(result["success"])
        self.assertTrue(result["blocks_fallback_used"])
        self.assertIn("VOC分析（电商VOC）", result["content"])
        self.assertIn("预览范围: 5cfRcx!A1:H10", result["content"])
        self.assertEqual(result["blocks_summary"]["by_type"]["sheet"], 1)
        self.assertEqual(len(result["embedded_resources"]), 1)
        mock_sheet_preview.assert_called_once_with(
            "RX8hsMOachgMz2tL2TrcIcKEnjg_5cfRcx",
            task_id="task-1",
        )
        self.assertEqual(len(request_calls), 2)


if __name__ == "__main__":
    unittest.main()
