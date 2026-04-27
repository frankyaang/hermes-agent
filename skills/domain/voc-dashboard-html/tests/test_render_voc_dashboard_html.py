#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "render_voc_dashboard_html.py"
SPEC = importlib.util.spec_from_file_location("render_voc_dashboard_html", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = renderer
SPEC.loader.exec_module(renderer)


class RenderVocDashboardHtmlTest(unittest.TestCase):
    def test_preserves_wide_top15_table_and_marks_explicit_risk(self) -> None:
        markdown = """# 科沃斯与核心竞品 VOC 深度交叉洞察报告

1. **X 系：清洁结果不达标需要优先关注。**
2. **T 系：基站与避障体验继续作为核心观察项。**
3. **服务链路：售后与客服需要进入周度复盘。**

**PM 总结提炼：** X 系风险聚焦在清洁结果，T 系风险聚焦在售后与客服。

## 【分】第二部分：X 系专场

### 模块1：X 系 Top15 指标穿透与时间序列风险

**📋 表1：X系Top15场景穿透与时间序列风险**
| Top15 核心指标 | 当前代提及率 | 周度变化 | 一级产品维度 | 用户任务翻译 | 强关联场景 | 强关联物品 | PM 场景破译与风险定性 | 真实 VOC 原声与定义输入 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 清洁效果好 | 57条 / 37.3% | 【回落】这周主动提起少了一些，更像口碑热度回落，不直接等于体验退步。 | 清洁结果 | 重污与高强度场景能力 | 厨房 / 门槛 | 家具 / 玩具 | 用户提这类好评，不是在泛泛夸一句干净。 | “打扫得很干净。” |

### 模块4：T 系 FRR / FFR 风险校正

| 关键退换风险 | FRR 原始数据支撑 | 走势判定 | 评论侧对应情况 | PM 风险研判与动作 |
| --- | --- | --- | --- | --- |
| 清洁结果不达标 | 产品类退换TOP项「颗粒物扫不...」：本期 0.72% | 截至第40天FRR 10.45% | 用户侧已经开始稳定抱怨这个问题 | 这条问题正在从体验摩擦升级成真实流失风险。 |

## 【分】第五部分：跨品牌行动建议

### X 系优先动作
- **清洁结果不达标：** 继续跟踪厨房、门槛等场景。

### T 系优先动作
- **售后与客服：** 继续跟踪维修体验。

### 服务链路动作
- **退换与维修：** 继续跟踪真实流失风险。

#### 数据边界说明
- 本报告仅基于正式 Markdown 内容生成，不增删正文。
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_md = root / "report.md"
            output_html = root / "dashboard.html"
            manifest = root / "manifest.json"
            audit = root / "audit.json"
            input_md.write_text(markdown, encoding="utf-8")

            audit_payload = renderer.render_dashboard(
                input_md=input_md,
                output_html=output_html,
                manifest_path=manifest,
                audit_path=audit,
                strict=True,
                theme="ai_studio",
            )

            html = output_html.read_text(encoding="utf-8")
            self.assertTrue(audit_payload["strict_passed"])
            self.assertTrue(audit_payload["visible_text_matches"])
            self.assertIn("<th>强关联场景</th>", html)
            self.assertIn("<th>强关联物品</th>", html)
            self.assertIn("<th>PM 场景破译与风险定性</th>", html)
            self.assertIn("清洁结果不达标", html)
            self.assertIn("risk-negative", html)
            self.assertIn('<span class="tag tag-blue">【回落】</span>这周主动提起少了一些', html)
            self.assertNotIn('class="risk-negative">【回落】', html)
            for css_marker in (
                ".sidebar",
                ".main-content",
                ".container",
                ".summary-grid",
                ".summary-card",
                ".pm-insight",
                ".action-grid",
                ".tag-red",
            ):
                self.assertIn(css_marker, html)

    def test_formal_report_fixture_remains_lossless_when_available(self) -> None:
        fixture = Path(__file__).resolve().parent / "fixtures" / "cross_brand_voc_report_2026-04-10.md"
        if not fixture.exists():
            self.skipTest("formal VOC report fixture is not available")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_payload = renderer.render_dashboard(
                input_md=fixture,
                output_html=root / "dashboard.html",
                manifest_path=root / "manifest.json",
                audit_path=root / "audit.json",
                strict=True,
                theme="ai_studio",
            )
            html = (root / "dashboard.html").read_text(encoding="utf-8")

            self.assertTrue(audit_payload["strict_passed"])
            self.assertTrue(audit_payload["visible_text_matches"])
            self.assertEqual(audit_payload["source_block_count"], 75)
            self.assertEqual(audit_payload["table_count"], 14)
            self.assertEqual(audit_payload["missing_block_ids"], [])
            self.assertEqual(audit_payload["table_column_mismatches"], [])
            self.assertIn("<th>强关联场景</th>", html)
            self.assertIn("<th>强关联物品</th>", html)
            self.assertIn("<th>PM 场景破译与风险定性</th>", html)

    def test_strict_mode_fails_on_table_column_mismatch(self) -> None:
        markdown = """# 报告

| A | B | C |
| --- | --- | --- |
| 1 | 2 |
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_md = root / "bad.md"
            input_md.write_text(markdown, encoding="utf-8")
            with self.assertRaises(SystemExit):
                renderer.render_dashboard(
                    input_md=input_md,
                    output_html=root / "bad.html",
                    manifest_path=root / "manifest.json",
                    audit_path=root / "audit.json",
                    strict=True,
                )


if __name__ == "__main__":
    unittest.main()
