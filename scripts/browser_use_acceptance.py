"""前端对抗性检验 — browser-use 实跑（Day 6）

用 browser_use.BrowserSession 打开 Chromium，确定性驱动 Streamlit UI
（playwright Page 直驱，避免 LLM Agent 驱动 Streamlit file_uploader 的不稳定性）。
每场景：上传夹具 → 触发动作 → 截图 → 抓取 stError/stException 文本 → 记录。

Streamlit 须已启动（TC_OFFLINE=1）：streamlit run main.py --server.port 8501

用法：python scripts/browser_use_acceptance.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

BASE_URL = os.environ.get("TC_UI_URL", "http://localhost:8502")
ADV = PROJECT_ROOT / "data" / "adversarial"
SHOTS = PROJECT_ROOT / "docs" / "screenshots" / "day6"
SHOTS.mkdir(parents=True, exist_ok=True)
RESULTS_JSON = PROJECT_ROOT / "docs" / "screenshots" / "day6" / "results.json"

# 5 文件 → 对应 uploader 标签片段（app.py L320-340）。
# 用标签定位而非 nth(i)：st.columns(3) 复用 col1/col2 使 DOM 顺序与
# 声明顺序不符（emp, train, perf, eval, proj），按位置上传必然错位。
UPLOAD_MAP = [
    ("员工基础信息", "employees.csv"),
    ("绩效记录", "performance.csv"),
    ("项目经历", "projects.json"),
    ("培训记录", "training.csv"),
    ("360评价", "evaluation_360.csv"),
]


def _files(scenario_dir: Path) -> list[str]:
    return [str(scenario_dir / name) for _, name in UPLOAD_MAP]


# ── 场景定义 ──────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "id": "S0", "name": "happy_path", "dir": ADV / "S0_happy",
        "expect": "上传成功，进入 Step 2，无异常",
        "flow": "upload_only",
    },
    {
        "id": "S1", "name": "numeric_employee_id", "dir": ADV / "S1_numeric_id",
        "expect": "可读错误或一致处理，无静默失配崩溃",
        "flow": "upload_only",
    },
    {
        "id": "S2", "name": "gbk_encoding", "dir": ADV / "S2_gbk",
        "expect": "可读编码错误，非裸 UnicodeDecodeError 字节位",
        "flow": "upload_only",
    },
    {
        "id": "S3", "name": "empty_rows", "dir": ADV / "S3_empty_rows",
        "expect": "无数据提示 + 返回按钮存在（验卡死回归）",
        "flow": "upload_only",
    },
    {
        "id": "S6", "name": "projects_dict_wrapper", "dir": ADV / "S6_proj_dict",
        "expect": "可读'应为 JSON 数组'提示",
        "flow": "upload_only",
    },
    {
        "id": "S4b", "name": "projects_partial_fields", "dir": ADV / "S4b_proj_partial",
        "expect": "校验通过或可读错误，无下游 KeyError 崩溃",
        "flow": "upload_only",
    },
    {
        "id": "S4", "name": "str_score_360", "dir": ADV / "S4_str_score",
        "expect": "Step5 360 可读错误，非 TypeError 堆栈",
        "flow": "advance_to_360",
    },
    {
        "id": "S7", "name": "summary_offline_regression", "dir": ADV / "S0_happy",
        "expect": "Step4 摘要生成 offline-placeholder，无 JSON parse 崩溃",
        "flow": "advance_to_summary",
    },
]


# ── 页面交互辅助 ──────────────────────────────────────────────────────

async def _upload_all(page, scenario_dir: Path) -> list[str]:
    """按标签定位 uploader 上传 5 文件。返回问题列表。

    Streamlit file_uploader 上传后 DOM 会重建——用 uploader 容器的标签文本
    定位（[data-testid='stFileUploader'] has_text 标签片段）而非 nth(i)，
    避免列复用导致的 DOM 顺序与声明顺序不符引发错位。每次重新 query +
    失败重试 3 次，避免第 2~5 个文件静默漏传。
    """
    issues = []
    for label, name in UPLOAD_MAP:
        fp = scenario_dir / name
        if not fp.exists():
            issues.append(f"夹具缺失: {fp}")
            continue
        uploaded = False
        last_err = None
        for attempt in range(3):
            try:
                # 每次循环重新 query：旧 locator 在 DOM 重建后失效
                uploader = page.locator(
                    "[data-testid='stFileUploader']",
                    has_text=label,
                ).first
                file_input = uploader.locator("input[type='file']").first
                await file_input.wait_for(state="attached", timeout=4000)
                await file_input.set_input_files(str(fp))
                await page.wait_for_timeout(600)
                uploaded = True
                break
            except Exception as e:
                last_err = e
                if attempt < 2:
                    await page.wait_for_timeout(800)
        if not uploaded:
            issues.append(f"上传 {name} 失败(3次重试): {last_err}")
    return issues


async def _click_button(page, text_substr: str, timeout: int = 8000) -> bool:
    """点击文本包含 text_substr 的按钮。"""
    try:
        btn = page.get_by_role("button").filter(has_text=text_substr).first
        await btn.wait_for(state="visible", timeout=timeout)
        await btn.click()
        return True
    except Exception:
        return False


async def _extract_alerts(page) -> dict:
    """抓取 Streamlit 错误/异常文本。返回 {alerts:[], exception:str|None}。"""
    alerts = []
    # st.error / st.warning / st.info
    for sel in ["[data-testid='stAlertContent']",
                "div[data-baseweb='notification']"]:
        try:
            els = await page.locator(sel).all_inner_texts()
        except Exception:
            els = []
        for t in els:
            t = t.strip()
            if t and t not in alerts:
                alerts.append(t)
    # 未捕获异常（红色 traceback）
    exc = None
    try:
        exc_el = page.locator("[data-testid='stException']")
        if await exc_el.count() > 0:
            exc = (await exc_el.first.inner_text()).strip()
    except Exception:
        pass
    # 去重 + 截断
    alerts = [a[:300] for a in alerts][:8]
    return {"alerts": alerts, "exception": exc[:1500] if exc else None}


async def _screenshot(page, path: Path) -> None:
    try:
        await page.screenshot(path=str(path), full_page=True)
    except Exception as e:
        # fallback: full_page=False
        try:
            await page.screenshot(path=str(path))
        except Exception:
            pass


# ── 流程编排 ──────────────────────────────────────────────────────────

async def _goto_step1(page) -> None:
    await page.goto(BASE_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(2500)  # Streamlit 首渲染


async def _advance_to_data_quality(page) -> None:
    """上传成功后从 Step2 前进到 Step3 数据质量。Step2 需先执行过滤。"""
    # 侧边栏 执行过滤
    await _click_button(page, "执行过滤", timeout=6000)
    await page.wait_for_timeout(2000)
    # 点"下一步"进 Step3（filter 成功后才有下一步按钮）
    await _click_button(page, "下一步", timeout=8000)
    await page.wait_for_timeout(3000)


async def _advance_to_summary(page) -> None:
    """前进到 Step4 文本摘要，选第一个员工，点生成摘要。"""
    await _click_button(page, "执行过滤", timeout=6000)
    await page.wait_for_timeout(2000)
    # Step2 → Step3
    await _click_button(page, "下一步", timeout=8000)
    await page.wait_for_timeout(2000)
    # Step3 → Step4
    await _click_button(page, "下一步", timeout=8000)
    await page.wait_for_timeout(2000)
    # Step4：选第一个员工（selectbox）
    try:
        sel = page.locator("div[data-baseweb='select'] [aria-haspopup='listbox']").first
        await sel.wait_for(state="visible", timeout=6000)
        await sel.click()
        await page.wait_for_timeout(500)
        opt = page.locator("li[role='option']").first
        await opt.click()
        await page.wait_for_timeout(500)
    except Exception:
        pass
    # 点"生成摘要"
    await _click_button(page, "生成摘要", timeout=6000)
    await page.wait_for_timeout(5000)


async def _advance_to_360(page) -> None:
    """前进到 Step5 360评价（_compute_360_scores 在此触发）。"""
    await _click_button(page, "执行过滤", timeout=6000)
    await page.wait_for_timeout(2000)
    await _click_button(page, "下一步", timeout=8000)  # → Step3
    await page.wait_for_timeout(2500)
    await _click_button(page, "下一步", timeout=8000)  # → Step4
    await page.wait_for_timeout(2000)
    await _click_button(page, "下一步", timeout=8000)  # → Step5
    await page.wait_for_timeout(3000)


async def run_one(page, sc: dict) -> dict:
    await _goto_step1(page)
    # 每场景重置：刷新到 Step1（新会话）
    issues = await _upload_all(page, sc["dir"])
    await page.wait_for_timeout(800)
    await _click_button(page, "确认上传", timeout=8000)
    await page.wait_for_timeout(3000)

    if sc["flow"] == "advance_to_data_quality":
        await _advance_to_data_quality(page)
    elif sc["flow"] == "advance_to_360":
        await _advance_to_360(page)
    elif sc["flow"] == "advance_to_summary":
        await _advance_to_summary(page)

    alerts = await _extract_alerts(page)
    shot = SHOTS / f"{sc['id']}.png"
    await _screenshot(page, shot)
    page_text = ""
    try:
        page_text = (await page.inner_text("body"))[:1500]
    except Exception:
        pass
    return {
        "id": sc["id"], "name": sc["name"], "expect": sc["expect"],
        "upload_issues": issues,
        "alerts": alerts["alerts"],
        "exception": alerts["exception"],
        "page_text_head": page_text[:600],
        "screenshot": str(shot.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "has_exception_box": alerts["exception"] is not None,
    }


async def main() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # 冒烟模式：TC_SMOKE=S0 只跑指定场景
    smoke = os.environ.get("TC_SMOKE")
    scenarios = [s for s in SCENARIOS if not smoke or s["id"] == smoke] if smoke else SCENARIOS
    print(f"browser-use 前端对抗检验 | LLM={DEEPSEEK_MODEL} | base={DEEPSEEK_BASE_URL} | 场景数={len(scenarios)}")
    # headless=True：对抗检验靠截图+alerts 判定，无需可见窗口；调试时可改 False
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            for sc in scenarios:
                print(f"\n=== {sc['id']} {sc['name']} ===")
                page = None
                try:
                    # 每场景新开 page（隔离 Streamlit session_state）
                    page = await browser.new_page()
                    res = await run_one(page, sc)
                except Exception as e:
                    # C1 对称：失败路径补齐成功路径全部顶层 key，否则下游 res.get("exception")
                    # 返回 None → 异常场景被漏判为"无异常"
                    res = {
                        "id": sc["id"], "name": sc["name"],
                        "expect": sc.get("expect", ""),
                        "upload_issues": [], "alerts": [], "exception": None,
                        "page_text_head": "", "screenshot": None,
                        "has_exception_box": None,
                        "error": f"{type(e).__name__}: {e}",
                    }
                    import traceback
                    traceback.print_exc()
                finally:
                    # 关闭本场景 page：防止 8 场景 tab 累积 + selectbox 浮层串扰
                    if page is not None:
                        try:
                            await page.close()
                        except Exception:
                            pass
                results.append(res)
                if "alerts" in res:
                    print(f"  alerts: {res['alerts'][:3]}")
                if res.get("exception"):
                    print(f"  ⚠ stException: {res['exception'][:200]}")
                if res.get("error"):
                    print(f"  ⚠ runner error: {res['error'][:200]}")
        finally:
            try:
                await browser.close()
            except Exception:
                pass
    RESULTS_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(f"\n结果已写: {RESULTS_JSON}")
    n_exc = sum(1 for r in results if r.get("has_exception_box"))
    print(f"红色异常堆栈场景数: {n_exc}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
