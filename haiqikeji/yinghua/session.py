"""英华平台 HTTP 会话配置与创建。"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session() -> requests.Session:
    """创建并配置英华平台的 requests.Session。

    挂载带重试策略的 HTTPAdapter，自动处理网络抖动和 5xx 错误。

    Returns:
        配置好的 Session 对象。
    """
    session = requests.Session()

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
