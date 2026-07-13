"""工具测试调用的安全限制。"""

import re
from urllib.parse import urlparse

from app.core.config import settings
from app.core.exceptions import AppException


def validate_tool_url(url: str) -> None:
    """校验工具 URL 安全性。"""
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise AppException(
            code="INVALID_TOOL_URL",
            message="仅支持 HTTP/HTTPS 协议",
            status_code=400,
        )

    hostname = parsed.hostname or ""

    if settings.app_env == "production":
        if parsed.scheme != "https":
            raise AppException(
                code="INVALID_TOOL_URL",
                message="生产环境仅支持 HTTPS",
                status_code=400,
            )

        private_patterns = [
            r"^10\.",
            r"^172\.(1[6-9]|2\d|3[01])\.",
            r"^192\.168\.",
            r"^127\.",
            r"^169\.254\.",
            r"^0\.",
            r"^::1$",
            r"^fc00:",
            r"^fd00:",
        ]
        for pattern in private_patterns:
            if re.match(pattern, hostname):
                raise AppException(
                    code="INVALID_TOOL_URL",
                    message="不允许访问内网地址",
                    status_code=400,
                )


def check_timeout(timeout: int) -> None:
    """校验超时设置。"""
    if timeout > settings.tool_test_timeout_seconds:
        raise AppException(
            code="TIMEOUT_TOO_LARGE",
            message=f"超时时间不能超过 {settings.tool_test_timeout_seconds} 秒",
            status_code=400,
        )
