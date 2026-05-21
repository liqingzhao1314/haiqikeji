"""HTTP 会话配置与创建。"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from haiqikeji.api import DEFAULT_COOKIES, DEFAULT_HEADERS


def create_session() -> requests.Session:
    """创建并配置一个模拟浏览器的 requests.Session。

    预设请求头（User-Agent、Sec-CH-UA 等）和 Cookie，
    使后续请求看起来像是从 Chrome 浏览器发出的。
    同时挂载带重试策略的 HTTPAdapter，自动处理网络抖动和 5xx 错误。

    Returns:
        配置好的 Session 对象。
    """
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.cookies.update(DEFAULT_COOKIES)

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=20,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session
