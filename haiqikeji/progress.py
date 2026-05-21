"""终端进度条渲染。"""

from __future__ import annotations

import sys

# 进度条旋转箭头帧序列，终端不支持 Unicode 时降级为 ASCII
_SPINNERS_UNICODE = ("↗", "→", "↘", "↓", "↙", "←", "↖", "↑")
_SPINNERS_ASCII = ("|", "/", "-", "\\", "|", "/", "-", "\\")


def _get_spinners() -> tuple[str, ...]:
    try:
        "↗".encode(sys.stdout.encoding or "utf-8")
        return _SPINNERS_UNICODE
    except (UnicodeEncodeError, LookupError):
        return _SPINNERS_ASCII


_SPINNERS = _get_spinners()
_BAR_WIDTH = 80
# 进度条行最大长度（时间标签25 + 括号2 + bar），用于清除残留字符
_BAR_CLEAR_WIDTH = 25 + _BAR_WIDTH + 5


def _format_time(seconds: float) -> str:
    """将秒数格式化为 HH:MM:SS 字符串。"""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _render_progress_bar(
    elapsed_seconds: float,
    total_seconds: float,
    frame: int,
    bar_width: int = _BAR_WIDTH,
) -> str:
    """渲染一行视频播放进度条。

    格式: 00:02:15 / 00:10:30 [------↗____________________________]

    Args:
        elapsed_seconds: 已播放秒数。
        total_seconds: 视频总秒数。
        frame: 当前帧号（用于选择旋转箭头）。
        bar_width: 进度条字符宽度。

    Returns:
        用 \\r 结尾的进度条字符串。
    """
    bar_width = max(bar_width, 2)
    elapsed = _format_time(elapsed_seconds)
    total = _format_time(total_seconds)
    spinner = _SPINNERS[frame % len(_SPINNERS)]

    ratio = 0.0 if total_seconds <= 0 else min(1.0, elapsed_seconds / total_seconds)
    filled = int(ratio * bar_width)
    bar = "-" * filled + spinner + "_" * (bar_width - filled - 1)
    return f"\r  {elapsed} / {total} [{bar}]"
