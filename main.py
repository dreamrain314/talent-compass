"""Talent Compass —— AI驱动的动态胜任力画像与智能人岗匹配系统

Streamlit 入口文件。启动方式：streamlit run main.py
"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 确保必要目录存在（从 config.py 移至此，防止 import 时崩溃）──
try:
    import config
    for _d in (config.RAW_DATA_DIR, config.INTERMEDIATE_DIR,
               config.LOG_DIR, config.PIPELINE_CONFIG_DIR):
        _d.mkdir(parents=True, exist_ok=True)
except OSError as e:
    print(f"[FATAL] 无法创建必要目录: {e}", file=sys.stderr)
    sys.exit(1)

# ── 渲染 Streamlit 界面 ──
# 使用 render() 函数调用模式（而非模块级 import），
# 确保每次 Streamlit 重运行时 st.* 调用都会被重新执行。
# 修复记录：import ui.app 在重运行时会命中模块缓存，导致空白页面。
from ui.app import render
render()
