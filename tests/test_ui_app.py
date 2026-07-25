"""ui/app.py 导入测试

Streamlit UI 无法直接用 pytest 测试（st.* 函数只在 Streamlit 运行时中可用）。
此处仅验证模块级函数可被正确导入且 render() 是 callable。

手动验收清单参见 docs/plan-ui-app.md 第 280-291 行。
"""
from __future__ import annotations

import pytest


def test_import_render():
    """render() 函数可导入（不调用 st.*，仅验证导入路径）。"""
    from ui.app import render
    assert callable(render)


def test_import_module_level_functions():
    """验证所有模块级私有函数可导入。"""
    import ui.app as app

    # 核心函数
    assert callable(app._init_session_state)
    assert callable(app._render_sidebar)
    assert callable(app._render_step_upload)
    assert callable(app._render_step_filter)
    assert callable(app._render_api_debug)
    assert callable(app._render_filter_conditions)
    assert callable(app._execute_filter)
    assert callable(app._render_upload_previews)
    assert callable(app._validate_uploads)
    assert callable(app._load_uploaded_data)

    # Step 3 数据质量函数
    assert callable(app._check_and_store_data_quality)
    assert callable(app._render_step_data_quality)
    assert callable(app._render_missing_table)
    assert callable(app._render_issues_section)


def test_constants_exist():
    """验证必需的常量已定义且类型正确。"""
    import ui.app as app

    # 列名校验常量
    assert isinstance(app._REQUIRED_COLUMNS, dict)
    assert "employees.csv" in app._REQUIRED_COLUMNS
    assert "performance.csv" in app._REQUIRED_COLUMNS
    assert "training.csv" in app._REQUIRED_COLUMNS
    assert "evaluation_360.csv" in app._REQUIRED_COLUMNS

    # projects.json 校验常量
    assert isinstance(app._PROJECT_REQUIRED_KEYS, set)
    assert "employee_id" in app._PROJECT_REQUIRED_KEYS
    assert "project_name" in app._PROJECT_REQUIRED_KEYS

    # 会话默认值
    assert isinstance(app._SESSION_DEFAULTS, dict)
    assert "step" in app._SESSION_DEFAULTS
    assert app._SESSION_DEFAULTS["step"] == 1
    assert "employees_df" in app._SESSION_DEFAULTS
    assert "filter_result" in app._SESSION_DEFAULTS

    # 步骤配置
    assert isinstance(app._STEPS, list)
    assert len(app._STEPS) == 7
    assert app._STEPS[0] == ("①", "数据上传")
    assert app._STEPS[1] == ("②", "基础过滤")
    assert app._STEPS[2] == ("③", "数据质量")
    assert app._STEPS[3] == ("④", "文本摘要")