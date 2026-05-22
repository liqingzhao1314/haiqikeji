"""测试日志系统配置。"""

from __future__ import annotations

from logging.handlers import RotatingFileHandler

from haiqikeji.logging_config import setup_logging


def test_setup_logging_replaces_previous_managed_handlers(tmp_path):
    first_log = tmp_path / "first.log"
    second_log = tmp_path / "second.log"

    logger = setup_logging(log_file=str(first_log))
    logger = setup_logging(log_file=str(second_log))

    managed_handlers = [
        handler
        for handler in logger.handlers
        if getattr(handler, "_haiqikeji_managed_handler", False)
    ]
    file_handlers = [
        handler for handler in managed_handlers if isinstance(handler, RotatingFileHandler)
    ]

    assert len(managed_handlers) == 2
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(second_log)

    setup_logging(log_file=None)
