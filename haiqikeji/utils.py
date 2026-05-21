"""工具函数：进度判断、时长解析、课程过滤等。"""

from __future__ import annotations

from datetime import date
from typing import Any


def is_unexpired_course(course: dict[str, Any], today: date) -> bool:
    """判断课程是否未过期。

    比较课程的 endDate 与今天日期，endDate >= today 视为未过期。
    缺少 endDate 字段的课程视为已过期（无法确定有效期）。

    Args:
        course: 课程信息字典，需包含 endDate 字段。
        today: 当前日期。

    Returns:
        True 表示课程仍在有效期内。
    """
    end_date = course.get("endDate")
    if not end_date:
        return False
    return date.fromisoformat(end_date) >= today


def course_matches(course: dict[str, Any], course_id: int | None, course_name: str | None) -> bool:
    """判断课程是否匹配用户指定的过滤条件。

    两个过滤条件为"与"关系：同时满足才返回 True。
    course_name 匹配不区分大小写，使用子串包含而非精确匹配。

    Args:
        course: 课程信息字典。
        course_id: 指定的课程 ID（None 表示不过滤）。
        course_name: 指定的课程名关键词（None 表示不过滤）。

    Returns:
        True 表示课程满足所有过滤条件。
    """
    if course_id is not None and course.get("id") != course_id:
        return False
    if course_name:
        name = str(course.get("courseName") or "")
        if course_name.casefold() not in name.casefold():
            return False
    return True


def coerce_percentage(value: Any) -> float | None:
    """将平台进度数值解析为浮点数。

    仅接受真实接口中使用的数字值：int、float 或可直接解析为数字的字符串。
    布尔值、空字符串、带百分号字符串和其他类型均返回 None。

    Args:
        value: 进度数值或数字字符串。

    Returns:
        解析后的浮点数，无法解析时返回 None。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def coerce_duration_seconds(value: Any) -> float | None:
    """将平台 videoDuration 秒数转换为浮点数。

    Args:
        value: 章节节点里的 videoDuration，单位为秒。

    Returns:
        有效秒数（必须 > 0），否则返回 None。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return float(value)
    return None


def build_node_progress_map(progress_data: Any) -> dict[int, dict[str, Any]]:
    """从课程进度接口 data 构建小节进度映射。"""
    if not isinstance(progress_data, dict):
        return {}

    progress_map: dict[int, dict[str, Any]] = {}
    for item in progress_data.get("nodeProgressList") or []:
        if not isinstance(item, dict):
            continue
        node_id = item.get("nodeId")
        if isinstance(node_id, int) and not isinstance(node_id, bool):
            progress_map[node_id] = item
    return progress_map


def get_resume_progress_percent(progress: Any) -> float:
    """计算断点续刷的起始进度百分比。

    支持两个真实来源：
    - /api/user/last_progress 的 data 字符串，格式如 "0.60"，表示 60%。
    - /api/user/get_study_progress 的 nodeProgressList 字典，读取 progressRatio 或 progressPercent。

    返回值限制在 [0, 99] 范围内，避免直接跳到 100 导致心跳循环跳过。

    Args:
        progress: 最新进度字符串或 nodeProgressList 中的小节进度字典。

    Returns:
        续刷起始进度百分比（0.0 ~ 99.0）。
    """

    def clamp_percentage(value: float) -> float:
        return min(99.0, max(0.0, value))

    if isinstance(progress, str):
        ratio = coerce_percentage(progress)
        if ratio is not None:
            return clamp_percentage(ratio * 100.0)
        return 0.0

    if not isinstance(progress, dict):
        return 0.0

    ratio = coerce_percentage(progress.get("progressRatio"))
    if ratio is not None:
        return clamp_percentage(ratio * 100.0)

    percentage = coerce_percentage(progress.get("progressPercent"))
    if percentage is not None:
        return clamp_percentage(percentage)

    return 0.0


def is_complete_progress(progress: Any) -> bool:
    """判断小节的学习进度是否已完成。

    平台进度记录来自 nodeProgressList，常见字段包括 state、statusText、
    progressPercent 和 progressRatio。仅按这些真实字段判断完成状态。

    Args:
        progress: 小节进度记录字典。

    Returns:
        True 表示该小节已完成学习。
    """
    if not isinstance(progress, dict):
        return False

    state = progress.get("state")
    if isinstance(state, int) and not isinstance(state, bool) and state == 1:
        return True

    if progress.get("statusText") == "已完成":
        return True

    progress_percent = progress.get("progressPercent")
    if not isinstance(progress_percent, bool):
        percentage = coerce_percentage(progress_percent)
        if percentage is not None and percentage >= 100:
            return True

    progress_ratio = progress.get("progressRatio")
    if not isinstance(progress_ratio, bool):
        ratio = coerce_percentage(progress_ratio)
        if ratio is not None and ratio >= 1.0:
            return True

    return False
