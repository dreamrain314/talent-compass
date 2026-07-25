"""pytest conftest — 全局 fixtures 与测试环境清理"""
import logging
import pytest


@pytest.fixture(autouse=True)
def _suppress_zombie_thread_logs():
    """测试 tearDown 后出现的僵尸线程日志不再写入已关闭的 stderr。

    当测试中的 Agent 线程在 pytest 进程 tearDown 后仍在运行并尝试写日志时，
    logging.StreamHandler 会因 stderr 已关闭而抛 ValueError。
    此 fixture 移除 root logger 的 StreamHandler，保留 FileHandler。
    """
    root = logging.getLogger("talent_compass")
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler):
            root.removeHandler(h)
    yield