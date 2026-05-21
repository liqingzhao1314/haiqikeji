"""API 请求函数和全局常量定义。

包含平台所有 API 端点的 URL、请求头、Cookie 以及对应的 HTTP 请求函数。
所有接口返回 {code, msg, data} 结构，code == 200 表示成功。
认证通过 authorization 请求头传递 JWT token。
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


# ============================
# 全局常量定义
# ============================

# 平台 API 基础地址，所有接口路径均基于此 URL 拼接
BASE_URL = "https://scauzj.haiqikeji.com"

# --- API 端点 ---
# 登录接口：通过账号密码获取 token
LOGIN_URL = f"{BASE_URL}/api/user/login"
# 获取当前登录用户的学生信息（含 student_id）
USER_INFO_URL = f"{BASE_URL}/api/user/yee_student_info"
# 获取当前学生的课程列表
COURSE_LIST_URL = f"{BASE_URL}/api/user/yee_my_course_list"
# 获取指定章节下的小节（节点）列表
CHAPTER_NODE_URL = f"{BASE_URL}/api/user/yee_node_select"
# 获取指定课程的学习进度（包含每个小节的完成状态）
COURSE_PROGRESS_URL = f"{BASE_URL}/api/user/get_study_progress"
# 学习会话：开始观看一个小节
STUDY_SESSION_START_URL = f"{BASE_URL}/api/user/study_session_start"
# 学习会话：周期性心跳上报观看进度
STUDY_SESSION_HEARTBEAT_URL = f"{BASE_URL}/api/user/study_session_heartbeat"
# 学习会话：结束观看
STUDY_SESSION_END_URL = f"{BASE_URL}/api/user/study_session_end"
# 获取指定小节的最新学习进度（用于断点续刷）
NODE_PROGRESS_URL = f"{BASE_URL}/api/user/last_progress"

# 模拟 Chrome 浏览器的请求头，用于绕过基本的反爬检测
DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "cache-control": "no-cache",
    "dnt": "1",
    "pragma": "no-cache",
    "referer": "https://scauzj.haiqikeji.com/student/login",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

# 预设 Cookie，模拟已访问过平台首页的状态
DEFAULT_COOKIES = {
    "__root_domain_v": ".haiqikeji.com",
    "_qddaz": "QD.451574695864699",
    "_qdda": "3-1.1",
    "_qddab": "3-dmh59z.mna83i5m",
}


def login(session: requests.Session, number: str, password: str, school_id: int) -> dict[str, Any]:
    """调用登录接口，通过账号密码获取认证 token。

    登录接口实际上是一个 GET 请求，将凭据作为查询参数传递。

    Args:
        session: 已配置的 HTTP 会话。
        number: 登录账号/学号。
        password: 登录密码。
        school_id: 学校 ID（默认 10）。

    Returns:
        登录接口返回的 JSON 响应字典。
    """
    response = session.get(
        LOGIN_URL,
        params={
            "number": number,
            "password": password,
            "schoolId": school_id,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def extract_token(login_result: dict[str, Any]) -> str:
    """从登录响应中提取认证 token。

    Args:
        login_result: 登录接口返回的 JSON 字典。

    Returns:
        提取到的 token 字符串。

    Raises:
        ValueError: 所有已知格式中均未找到 token。
    """
    data = login_result.get("data")

    if isinstance(data, str) and data.strip():
        return data.strip()

    raise ValueError("登录成功，但未找到 token 字段")


def get_user_info(session: requests.Session, token: str) -> dict[str, Any]:
    """获取当前登录用户的学生信息。

    用于验证 token 是否有效，同时从响应中提取 student_id。
    如果 token 失效，接口会返回非 200 的 code。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌，通过 authorization 请求头传递。

    Returns:
        用户信息接口返回的 JSON 字典。
    """
    response = session.get(
        USER_INFO_URL,
        headers={"authorization": token},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_course_list(
    session: requests.Session, token: str, school_id: int, student_id: int
) -> dict[str, Any]:
    """获取当前学生的课程列表。

    一次性拉取最多 1000 条课程记录（pageSize=1000）。
    type=0 表示获取所有类型的课程。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        school_id: 学校 ID。
        student_id: 学生 ID。

    Returns:
        课程列表接口返回的 JSON 字典，data 字段为课程数组。
    """
    response = session.get(
        COURSE_LIST_URL,
        params={
            "schoolId": school_id,
            "studentId": student_id,
            "type": 0,
            "pageNum": 1,
            "pageSize": 1000,
        },
        headers={
            "authorization": token,
            "referer": "https://scauzj.haiqikeji.com/student/home",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_course_chapter_tree(
    session: requests.Session,
    token: str,
    school_id: int,
    course_id: int,
    student_id: int,
) -> dict[str, Any]:
    """获取课程的章节-小节树形结构。

    一次调用返回全部章节，每个章节的 children 字段包含其下的小节（节点）列表。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        school_id: 学校 ID。
        course_id: 课程 ID。
        student_id: 学生 ID。

    Returns:
        接口返回的 JSON 字典，data 为章节数组，每项含 children（小节数组）。
    """
    response = session.get(
        CHAPTER_NODE_URL,
        params={
            "courseId": course_id,
            "schoolId": school_id,
            "studentId": student_id,
        },
        headers={
            "authorization": token,
            "referer": f"{BASE_URL}/student/course-study?id={course_id}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_course_progress(
    session: requests.Session, token: str, school_id: int, user_id: int, course_id: int
) -> dict[str, Any]:
    """获取指定课程的学习进度。

    返回的 data.nodeProgressList 包含每个小节的完成状态，
    用于判断哪些小节已看完（可跳过）以及断点续刷的进度。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        school_id: 学校 ID。
        user_id: 用户/学生 ID。
        course_id: 课程 ID。

    Returns:
        进度接口返回的 JSON 字典，data.nodeProgressList 为进度数组。
    """
    response = session.get(
        COURSE_PROGRESS_URL,
        params={
            "schoolId": school_id,
            "userId": user_id,
            "courseId": course_id,
        },
        headers={
            "authorization": token,
            "referer": f"{BASE_URL}/student/course-study-record?id={course_id}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_node_progress(
    session: requests.Session,
    token: str,
    school_id: int,
    user_id: int,
    node_id: int,
) -> dict[str, Any]:
    """获取指定小节的最新学习进度（用于断点续刷）。

    在每次观看前调用此接口，获取该小节的最新进度百分比。
    返回值 data 为字符串格式，如 "0.60" 表示 60% 进度。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        school_id: 学校 ID。
        user_id: 用户/学生 ID。
        node_id: 小节/节点 ID。

    Returns:
        进度接口返回的 JSON 字典，data 为进度字符串（如 "0.60"）。
    """
    response = session.get(
        NODE_PROGRESS_URL,
        params={
            "nodeId": node_id,
            "userId": user_id,
            "schoolId": school_id,
        },
        headers={
            "authorization": token,
            "referer": f"{BASE_URL}/student/course-study",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def study_session_start(
    session: requests.Session,
    token: str,
    school_id: int,
    user_id: int,
    course_id: int,
    node_id: int,
    terminal: str = "web",
) -> dict[str, Any]:
    """开始一个学习会话（开始观看小节）。

    调用成功后会返回一个 sessionId，后续的心跳和结束请求都需要
    携带此 sessionId 以标识同一个学习会话。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        school_id: 学校 ID。
        user_id: 用户/学生 ID。
        course_id: 课程 ID。
        node_id: 要学习的小节（节点）ID。
        terminal: 终端类型，默认 "web"。

    Returns:
        学习会话启动接口返回的 JSON 字典，data 字段为 sessionId。
    """
    response = session.post(
        STUDY_SESSION_START_URL,
        json={
            "schoolId": school_id,
            "userId": user_id,
            "courseId": course_id,
            "nodeId": node_id,
            "terminal": terminal,
        },
        headers={
            "authorization": token,
            "origin": BASE_URL,
            "content-type": "application/json",
            "referer": f"{BASE_URL}/student/course-study?id={course_id}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def study_session_heartbeat(
    session: requests.Session,
    token: str,
    session_id: str,
    progress: int,
    course_id: int,
) -> dict[str, Any]:
    """发送学习会话心跳，上报当前观看进度。

    需要周期性调用（如每 25 秒一次），progress 从 0 递增到 100。
    平台通过 sessionId 将心跳关联到对应的学习会话。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        session_id: 学习会话 ID（由 study_session_start 返回）。
        progress: 当前进度百分比（0-100 的整数）。
        course_id: 课程 ID（用于拼接 referer）。

    Returns:
        心跳接口返回的 JSON 字典。
    """
    response = session.post(
        STUDY_SESSION_HEARTBEAT_URL,
        json={
            "sessionId": session_id,
            "progress": str(progress),
        },
        headers={
            "authorization": token,
            "origin": BASE_URL,
            "content-type": "application/json",
            "referer": f"{BASE_URL}/student/course-study?id={course_id}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def study_session_end(
    session: requests.Session,
    token: str,
    session_id: str,
    course_id: int,
) -> dict[str, Any]:
    """结束学习会话。

    在所有心跳发送完毕（进度达到 100%）后调用，
    通知平台本次学习已完成。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        session_id: 学习会话 ID（由 study_session_start 返回）。
        course_id: 课程 ID（用于拼接 referer）。

    Returns:
        学习会话结束接口返回的 JSON 字典。
    """
    response = session.post(
        STUDY_SESSION_END_URL,
        json={
            "sessionId": session_id,
        },
        headers={
            "authorization": token,
            "origin": BASE_URL,
            "content-type": "application/json",
            "referer": f"{BASE_URL}/student/course-study?id={course_id}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
