"""英华平台 HTTP 会话配置与创建。"""

from __future__ import annotations

import requests

from haiqikeji.session import create_session_with_retry


def create_session() -> requests.Session:
    """创建并配置英华平台的 requests.Session。

    复用公共重试策略，自动处理网络抖动和 5xx 错误。

    Returns:
        配置好的 Session 对象。
    """
    return create_session_with_retry()
