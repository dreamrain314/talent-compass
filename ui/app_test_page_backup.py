"""Talent Compass - 测试页面（备份）

⚠️ 此文件是 ui/app.py 在 Step 1-2 过滤层界面重构前的原始测试页面备份。
   当前 ui/app.py 已改为 render() 函数模式，此备份仅供历史参考。

原始用途：API 连通性测试
最后有效版本：2026-07-21（第四轮修复前）

修复记录：
- 第四轮修复 (2026-07-22)：将模块级代码封装为 render() 函数，
  修复 Streamlit 重运行时的模块缓存导致空白页面问题。
"""
from __future__ import annotations

import os

import streamlit as st

# 页面配置
st.set_page_config(
    page_title="Talent Compass",
    page_icon="🧭",
    layout="wide",
)

# 页面标题
st.title("Talent Compass - 测试页面")

# ── 侧边栏：API 配置 ──
with st.sidebar:
    st.markdown("### ⚙️ API 配置")
    api_key = st.text_input(
        "DeepSeek API Key",
        type="password",
        value=os.getenv("DEEPSEEK_API_KEY", ""),
        help="输入你的 DeepSeek API Key，修改后点击应用",
    )
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key

    if st.button("🔄 应用 Key 变更", use_container_width=True):
        try:
            from utils.llm_client import reset_client
            reset_client()
            st.success("已切换到新 Key")
        except Exception as exc:
            st.error(f"切换失败: {exc}")

    if api_key:
        masked = "..." + str(api_key)[-4:] if len(str(api_key)) > 4 else str(api_key)
        st.caption(f"当前 Key: {masked}")
    else:
        st.caption("未设置 API Key")

# ── 主区域：API 测试 ──
st.markdown("### 💬 API 连通性测试")
user_input = st.text_area(
    "💬 测试消息",
    placeholder="输入你想发给AI的消息...",
    height=150,
)

if st.button("🚀 发送", type="primary"):
    if not os.getenv("DEEPSEEK_API_KEY", ""):
        st.error("请先设置 API Key")
    elif not user_input:
        st.warning("请输入测试消息")
    else:
        with st.spinner("正在调用 API..."):
            try:
                from utils.llm_client import call_llm
                result = call_llm(
                    prompt=user_input,
                    system_prompt="你是一个HR领域的AI助手。请用中文简洁回答用户的问题。",
                )
                if result.get("error"):
                    st.error(f"API 调用失败: {result['error']}")
                elif result.get("error") is None:
                    st.success("API 调用成功")
                    if result.get("content"):
                        st.markdown("### AI 回复")
                        st.info(result["content"])
                    else:
                        st.caption("（AI 返回了空内容）")
                    st.caption(
                        f"模型：{result.get('model', 'N/A')}  |  "
                        f"Prompt Token：{result.get('usage', {}).get('prompt_tokens', 0)}  |  "
                        f"Completion Token：{result.get('usage', {}).get('completion_tokens', 0)}"
                    )
                else:
                    st.warning(f"未知响应: {result}")
            except Exception as e:
                import traceback
                st.error(f"调用异常: {e}")
                with st.expander("详细错误信息"):
                    st.code(traceback.format_exc())

# ── 页脚 ──
from datetime import datetime
st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  模型: DeepSeek V4-Flash")