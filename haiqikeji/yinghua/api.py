"""英华平台 API 请求函数和常量定义。

包含英华平台所有 API 端点的请求函数。
该平台部分接口返回 HTML 页面（需 XPath 解析），
部分接口返回 JSON（{status, result: {data: ...}} 结构）。

英华平台有多个域名，运行时通过 base_url 参数指定。
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

# ====================
# 默认基础地址
# ====================

DEFAULT_BASE_URL = "https://scauzj.tuozhikj.com"

# HTML 错误页中嵌入的 JSON 数据模式
_EMBEDDED_JSON_RE = re.compile(r"var\s+data\s*=\s*(\{.*?})\s*;", re.DOTALL)


def _parse_response(response: requests.Response) -> dict[str, Any]:
    """解析接口响应，兼容 JSON 和 HTML 错误页两种格式。

    正常接口返回 JSON；章节未解锁等错误场景返回 HTML 错误页，
    其中 <script> 标签内嵌 JSON（var data = {...};）。

    Args:
        response: HTTP 响应对象。

    Returns:
        解析后的字典。JSON 解析失败时尝试从 HTML 提取嵌入 JSON，
        均失败时返回 {"status": False, "msg": 原始响应文本前200字符}。
    """
    # 优先尝试直接 JSON 解析
    try:
        return response.json()
    except ValueError:
        pass

    # 尝试从 HTML 中提取嵌入的 JSON
    text = response.text
    match = _EMBEDDED_JSON_RE.search(text)
    if match:
        import json

        try:
            return json.loads(match.group(1))
        except ValueError:
            pass

    # 兜底：返回原始文本摘要
    return {"status": False, "msg": text[:200]}


# ====================
# XPath 路径常量（与 base_url 无关）
# ====================

# 课程列表容器
COURSE_LIST_XPATH = "/html/body/div[3]/div[2]/div[2]/div[1]/div[4]"
# 课程标题
COURSE_TITLE_XPATH = "./div/div/div[2]/div[1]/a/text()"
# 课程链接（含 courseId）
COURSE_URL_XPATH = "./div/div/div[2]/div[1]/a/@href"
# 课程进度百分比文本
COURSE_PROGRESS_XPATH = "./div/div/div[2]/div[3]/div[3]/text()"

# 进度完成标识
PROGRESS_COMPLETE = "100%"

# ====================
# 浏览器请求头模板
# ====================


def _login_headers(base_url: str) -> dict[str, str]:
    """生成登录请求头，origin 和 referer 指向 base_url。"""
    return {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": base_url,
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": f"{base_url}/user/login",
        "sec-ch-ua": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"
        ),
        "x-requested-with": "XMLHttpRequest",
    }


def _page_headers(referer_url: str) -> dict[str, str]:
    """生成页面请求头，引用来源为 referer_url。"""
    return {
        "accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": referer_url,
        "sec-ch-ua": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"
        ),
    }


# ====================
# 验证码相关
# ====================

# 缓存 OCR 引擎实例，避免每次识别都加载 ONNX 模型
_ocr_engine: Any = None


def get_captcha_image(session: requests.Session, base_url: str = DEFAULT_BASE_URL) -> bytes:
    """下载验证码图片。

    Args:
        session: 已配置的 HTTP 会话。
        base_url: 英华平台基础地址。

    Returns:
        验证码图片的原始字节数据。

    Raises:
        requests.RequestException: 网络请求失败。
    """
    response = session.get(
        f"{base_url}/service/code",
        headers=_login_headers(base_url),
        timeout=15,
    )
    response.raise_for_status()
    return response.content


def recognize_captcha(image_bytes: bytes) -> str:
    """使用 ddddocr 识别验证码图片。

    Args:
        image_bytes: 验证码图片的原始字节数据。

    Returns:
        识别出的验证码文本。

    Raises:
        ImportError: 未安装 ddddocr。
    """
    global _ocr_engine

    if _ocr_engine is None:
        import ddddocr

        _ocr_engine = ddddocr.DdddOcr(show_ad=False)
    return _ocr_engine.classification(image_bytes)


# ====================
# 登录函数
# ====================


def login_with_captcha(
    session: requests.Session,
    username: str,
    password: str,
    captcha_code: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """使用账号密码和验证码登录英华平台。

    Args:
        session: 已配置的 HTTP 会话。
        username: 登录用户名/学号。
        password: 登录密码。
        captcha_code: 验证码文本。
        base_url: 英华平台基础地址。

    Returns:
        登录接口返回的 JSON 字典，status 字段表示是否成功。

    Raises:
        requests.RequestException: 网络请求失败。
    """
    response = session.post(
        f"{base_url}/user/login",
        data={"username": username, "password": password, "code": captcha_code},
        headers=_login_headers(base_url),
        timeout=15,
    )
    response.raise_for_status()
    return _parse_response(response)


def get_api_token(
    session: requests.Session,
    username: str,
    password: str,
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    """获取英华平台 API 访问令牌。

    该令牌用于后续的学习进度查询和学时提交。

    Args:
        session: 已配置的 HTTP 会话。
        username: 登录用户名/学号。
        password: 登录密码。
        base_url: 英华平台基础地址。

    Returns:
        API 令牌字符串。

    Raises:
        requests.RequestException: 网络请求失败。
        KeyError: 响应中找不到 token 字段。
    """
    response = session.post(
        f"{base_url}/api/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    response.raise_for_status()
    result = response.json()
    return result["result"]["data"]["token"]


# ====================
# 课程列表（HTML 解析）
# ====================


def get_incomplete_course_ids(
    session: requests.Session,
    base_url: str = DEFAULT_BASE_URL,
) -> list[dict[str, str]]:
    """从用户主页抓取未完成课程列表。

    通过解析 HTML 页面获取课程信息，包括 ID、标题和进度。

    Args:
        session: 已登录的 HTTP 会话（需保存了登录 Cookie）。
        base_url: 英华平台基础地址。

    Returns:
        未完成课程列表，每项包含 courseId、title 字段。

    Raises:
        requests.RequestException: 网络请求失败。
        ImportError: 未安装 lxml。
    """
    from lxml import etree

    url = f"{base_url}/user/index"
    headers = _page_headers(url)
    response = session.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    html_tree = etree.HTML(response.text)
    course_elements = html_tree.xpath(COURSE_LIST_XPATH)

    incomplete: list[dict[str, str]] = []

    for course_element in course_elements:
        titles = course_element.xpath(COURSE_TITLE_XPATH)
        urls = course_element.xpath(COURSE_URL_XPATH)
        progresses = course_element.xpath(COURSE_PROGRESS_XPATH)

        for title, course_url, progress in zip(titles, urls, progresses, strict=True):
            if PROGRESS_COMPLETE not in progress:
                if "Id=" not in course_url:
                    continue
                course_id = course_url.split("Id=")[1]
                incomplete.append({"courseId": course_id, "title": title})

    return incomplete


# ====================
# 学习记录查询
# ====================


def get_study_records(
    session: requests.Session,
    course_id: str,
    base_url: str = DEFAULT_BASE_URL,
) -> list[dict[str, Any]]:
    """获取指定课程的学习记录（分页拉取所有记录）。

    Args:
        session: 已登录的 HTTP 会话。
        course_id: 课程 ID。
        base_url: 英华平台基础地址。

    Returns:
        学习记录列表，每项为原始 JSON 记录字典。

    Raises:
        requests.RequestException: 网络请求失败。
    """
    headers = _page_headers(base_url)
    headers["accept"] = "application/json, text/javascript, */*; q=0.01"

    all_records: list[dict[str, Any]] = []
    page = 1

    while True:
        params = {
            "courseId": course_id,
            "_": str(int(time.time() * 1000)),
            "page": page,
        }
        response = session.get(
            f"{base_url}/user/study_record.json",
            params=params,
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("status", False):
            return all_records

        page_info = result.get("pageInfo", {})
        records = result.get("list", [])
        all_records.extend(records)

        if page >= page_info.get("pageCount", 1):
            break
        page += 1

    return all_records


# ====================
# 视频进度和学时提交
# ====================


def get_video_progress(
    session: requests.Session,
    token: str,
    node_id: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """获取指定节点的视频进度信息。

    Args:
        session: 已登录的 HTTP 会话。
        token: API 令牌。
        node_id: 章节 nodeId。
        base_url: 英华平台基础地址。

    Returns:
        接口返回的 JSON 字典，result.data 包含 videoDuration、study_total 等。

    Raises:
        requests.RequestException: 网络请求失败。
    """
    response = session.post(
        f"{base_url}/api/node/video",
        data={"token": token, "nodeId": node_id},
        headers=_page_headers(base_url),
        timeout=15,
    )
    response.raise_for_status()
    return _parse_response(response)


def submit_study_time(
    session: requests.Session,
    token: str,
    node_id: str,
    study_time: int,
    study_id: int,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """提交单次学习时长。

    Args:
        session: 已登录的 HTTP 会话。
        token: API 令牌。
        node_id: 章节 nodeId。
        study_time: 累计学习时长（秒）。
        study_id: 学习 ID（首次为 0，后续使用接口返回的值）。
        base_url: 英华平台基础地址。

    Returns:
        接口返回的 JSON 字典，status 字段表示是否成功。

    Raises:
        requests.RequestException: 网络请求失败。
    """
    response = session.post(
        f"{base_url}/api/node/study",
        data={
            "token": token,
            "nodeId": node_id,
            "studyTime": study_time,
            "studyId": study_id,
        },
        timeout=15,
    )
    response.raise_for_status()
    return _parse_response(response)
