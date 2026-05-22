"""日志系统配置。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

DEFAULT_LOG_FILE = "haiqikeji.log"
_MANAGED_HANDLER_ATTR = "_haiqikeji_managed_handler"


def _replace_managed_handlers(root_logger: logging.Logger) -> None:
    """移除本模块创建的旧 handler，避免重复输出。"""
    for handler in root_logger.handlers[:]:
        if getattr(handler, _MANAGED_HANDLER_ATTR, False):
            root_logger.removeHandler(handler)
            handler.close()


def setup_logging(
    log_level: int = logging.INFO, log_file: str | None = DEFAULT_LOG_FILE
) -> logging.Logger:
    """配置根日志记录器。

    始终添加一个 StreamHandler 输出到控制台。
    默认额外添加一个 RotatingFileHandler 写入 haiqikeji.log。

    Args:
        log_level: 日志级别，默认 INFO。
        log_file: 日志文件路径（None 表示仅控制台输出）。

    Returns:
        配置好的根日志记录器。
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    _replace_managed_handlers(root_logger)

    # 控制台 handler
    console_handler = logging.StreamHandler()
    setattr(console_handler, _MANAGED_HANDLER_ATTR, True)
    console_handler.setLevel(log_level)
    console_format = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # 文件 handler（如果指定了日志文件）
    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        setattr(file_handler, _MANAGED_HANDLER_ATTR, True)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s [%(levelname)-7s] %(funcName)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志记录器。

    Args:
        name: 日志记录器名称，通常使用 __name__。

    Returns:
        日志记录器实例。
    """
    return logging.getLogger(name)
