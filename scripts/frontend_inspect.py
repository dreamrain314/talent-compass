"""Playwright 驱动的前端检验脚本。

逐 Step 导航 Streamlit 应用，对复杂界面截图，
记录构造状况到 results.json。

[ALLOWED-OPS: Bash, Read]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP_URL = os.environ.get("TC_APP_URL", "http://localhost:8765/")
SHOT_DIR = ROOT / "docs" / "screenshots" / "inspect"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

RAW = ROOT / "data" / "raw"
# 按上传器标签匹配 — st.columns 布局会打乱 DOM 顺序，不能按 nth 索引
UPLOADERS = [
    ("员工基础信息", RAW / "employees.csv"),
    ("绩效记录", RAW / "performance.csv"),
    ("项目经历", RAW / "projects.json"),
    ("培训记录", RAW / "training.csv"),
    ("360评价", RAW / "evaluation_360.csv"),
]


def shot(page: Page, name: str, full: bool = True) -> str:
    p = SHOT_DIR / f"{name}.png"
    page.screenshot(path=str(p), full_page=full)
    print(f"  📸 {p.name}")
    return str(p)


def wait_idle(page: Page, timeout: int = 20000):
    """等 Streamlit 完成重运行：先等 networkidle，再等运行状态消失。"""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    # Streamlit 重运行时会在右上角显示 status widget / spinner skeleton
    try:
        page.wait_for_function(
            """() => {
                const sk = document.querySelectorAll('[data-testid="stSkeleton"]');
                const spin = document.querySelectorAll('[data-testid="stSpinner"]');
                const running = document.querySelector('[data-testid="stStatusWidget"]');
                return sk.length === 0 && spin.length === 0 && !running;
            }""",
            timeout=timeout,
        )
    except Exception:
        page.wait_for_timeout(1500)


def click_btn(page: Page, label: str):
    # Streamlit 1.51 button label is plain <button>inner_text</button>
    el = page.locator(f'button:has-text("{label}")').last
    el.wait_for(state="visible", timeout=10000)
    el.click()
    wait_idle(page)


def main():
    results: dict = {"url": APP_URL, "steps": [], "issues": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()

        try:
            page.goto(APP_URL, wait_until="domcontentloaded")
            wait_idle(page)
            page.wait_for_timeout(2000)

            # ── Step 1: 数据上传 ───────────────────────────────
            print("\n=== Step 1: 数据上传 ===")
            results["steps"].append({"step": 1, "name": "数据上传-初始表单",
                                     "shot": shot(page, "S1_01_initial")})

            inputs = page.locator('input[type="file"]')
            n = inputs.count()
            print(f"  file inputs: {n}")
            if n < 5:
                results["issues"].append(f"Step1: 仅 {n} 个 file input，期望 5")

            for label_text, fp in UPLOADERS:
                if not fp.exists():
                    results["issues"].append(f"Step1: 数据文件缺失 {fp}")
                    continue
                # 按标签定位 uploader，再在其内部找 input
                uploader = page.locator(
                    f'[data-testid="stFileUploader"]:has-text("{label_text}")'
                ).first
                inp = uploader.locator('input[type="file"]').first
                inp.set_input_files(str(fp))
                wait_idle(page)
                print(f"  uploaded {fp.name} → {label_text}")

            page.wait_for_timeout(800)
            results["steps"].append({"step": 1, "name": "数据上传-已加载",
                                     "shot": shot(page, "S1_02_loaded")})

            try:
                click_btn(page, "确认上传")
                print("  → Step 2")
            except Exception as e:
                results["issues"].append(f"Step1→2: 确认上传失败: {e}")

            # ── Step 2: 基础过滤 ───────────────────────────────
            print("\n=== Step 2: 基础过滤 ===")
            results["steps"].append({"step": 2, "name": "过滤-初始",
                                     "shot": shot(page, "S2_01_filter_initial")})
            try:
                click_btn(page, "执行过滤")
                results["steps"].append({"step": 2, "name": "过滤-结果",
                                         "shot": shot(page, "S2_02_filter_result")})
                print("  执行过滤完成")
            except Exception as e:
                results["issues"].append(f"Step2: 执行过滤失败: {e}")

            try:
                click_btn(page, "下一步 → 数据质量报告")
                print("  → Step 3")
            except Exception as e:
                results["issues"].append(f"Step2→3: 下一步失败: {e}")

            # ── Step 3: 数据质量 ───────────────────────────────
            print("\n=== Step 3: 数据质量 ===")
            results["steps"].append({"step": 3, "name": "数据质量报告",
                                     "shot": shot(page, "S3_01_quality")})
            try:
                expanders = page.locator('[data-testid="stExpander"] details')
                cnt = expanders.count()
                print(f"  expanders: {cnt}")
                for i in range(cnt):
                    summary = expanders.nth(i).locator("summary")
                    if summary.is_visible():
                        try:
                            summary.click(timeout=1000)
                        except Exception:
                            pass
                page.wait_for_timeout(800)
                results["steps"].append({"step": 3, "name": "数据质量-展开",
                                         "shot": shot(page, "S3_02_expanded")})
            except Exception as e:
                results["issues"].append(f"Step3: 展开 expander 失败: {e}")

            try:
                click_btn(page, "下一步 → 文本摘要")
                print("  → Step 4")
            except Exception as e:
                results["issues"].append(f"Step3→4: 下一步失败: {e}")

            # ── Step 4: 文本摘要（offline 占位符）────────────
            print("\n=== Step 4: 文本摘要 ===")
            results["steps"].append({"step": 4, "name": "文本摘要-初始",
                                     "shot": shot(page, "S4_01_summary_initial")})
            try:
                gen = page.locator('button:has-text("生成摘要")').first
                if gen.count():
                    gen.click()
                    wait_idle(page)
                    results["steps"].append({"step": 4, "name": "文本摘要-已生成",
                                             "shot": shot(page, "S4_02_summary_generated")})
                    print("  生成摘要完成（offline 占位符）")
            except Exception as e:
                results["issues"].append(f"Step4: 生成摘要失败: {e}")

            try:
                click_btn(page, "下一步 → 360评价")
                print("  → Step 5")
            except Exception as e:
                results["issues"].append(f"Step4→5: 下一步失败: {e}")

            # ── Step 5: 360 评价 ───────────────────────────────
            print("\n=== Step 5: 360 评价 ===")
            results["steps"].append({"step": 5, "name": "360评价",
                                     "shot": shot(page, "S5_01_360")})

            # Step 6-8 为 Day1-5 未实现的预留位
            for s, label in [(6, "画像生成"), (7, "岗位匹配"), (8, "推荐结果")]:
                moved = False
                for txt in [f"下一步 → {label}", "下一步"]:
                    btn = page.locator(f'button:has-text("{txt}")').first
                    if btn.count():
                        try:
                            btn.click()
                            wait_idle(page)
                            results["steps"].append({"step": s, "name": label,
                                                     "shot": shot(page, f"S{s}_01_{label}")})
                            print(f"  → Step {s}")
                            moved = True
                            break
                        except Exception:
                            continue
                if not moved:
                    results["steps"].append({"step": s, "name": label, "shot": None,
                                             "note": "无可达入口（Day1-5 未实现）"})
                    print(f"  Step {s} 无入口（预留位）")

            # ── 侧边栏 ────────────────────────────────────────
            print("\n=== 侧边栏 ===")
            try:
                sidebar = page.locator('[data-testid="stSidebar"]')
                if sidebar.count():
                    results["steps"].append({"step": 0, "name": "侧边栏",
                                             "shot": shot(page, "S0_sidebar", full=False)})
            except Exception as e:
                results["issues"].append(f"侧边栏截图失败: {e}")

        finally:
            browser.close()

    out = SHOT_DIR / "results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 完成: {out} ===")
    print(f"截图目录: {SHOT_DIR}")
    print(f"问题数: {len(results['issues'])}")
    for i in results["issues"]:
        print(f"  ⚠️ {i}")


if __name__ == "__main__":
    main()
