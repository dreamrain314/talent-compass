"""结构化 JSON 日志工具

每条日志输出为 JSON 格式，包含 trace_id、agent_name、timestamp 等字段。
同时输出到文件和控制台。
"""
import json
import logging
import os
import time
import secrets
from datetime import datetime, timezone
from pathlib import Path


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "trace_id": getattr(record, "trace_id", "-"),
            "agent_name": getattr(record, "agent_name", "-"),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        return json.dumps(log_entry, ensure_ascii=False)


def generate_trace_id() -> str:
    today = datetime.now().strftime("%Y%m%d")
    ms = int(time.time() * 1000) % 1_000_000
    rand = secrets.token_hex(2)
    return f"TC-{today}-{ms:06d}-{rand}"


def setup_logger(
    log_dir: str | None = None,
    log_level: int = logging.DEBUG,
    force: bool = False,
) -> logging.Logger:
    if log_dir is None:
        from config import LOG_DIR  # late import to avoid circular dependency

        log_dir = str(LOG_DIR)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("talent_compass")
    root_logger.setLevel(log_level)
    if root_logger.handlers and not force:
        return root_logger
    if force:
        root_logger.handlers.clear()
        root_logger.setLevel(log_level)

    json_formatter = JSONFormatter()

    date_str = datetime.now().strftime("%Y%m%d")
    file_handler = logging.FileHandler(
        log_path / f"talent_compass_{date_str}.jsonl", encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(json_formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(json_formatter)
    root_logger.addHandler(console_handler)

    return root_logger
