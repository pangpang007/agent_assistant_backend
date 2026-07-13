
import time
import httpx
from typing import Any
from urllib.parse import urlparse

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class HTTPExecutor(BaseNodeExecutor):
    """
    HTTP 请求节点执行器：调用外部 REST API。
    
    安全限制：
    - 禁止访问内网 IP（SSRF 防护）
    - 最大响应体: 1MB
    - 最大超时: 60 秒
    - 仅支持 HTTP/HTTPS
    
    执行流程：
    1. 解析 URL、Method、Headers、Body
    2. 解析变量引用
    3. 执行 HTTP 请求
    4. 返回响应
    """

    DEFAULT_TIMEOUT = 30
    MAX_RESPONSE_SIZE = 1024 * 1024  # 1MB

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            url = config.get("url", "")
            method = config.get("method", "GET").upper()
            headers = config.get("headers", {})
            body = config.get("body")
            body_template = config.get("body_template")
            timeout = min(self._resolve_timeout(config), 60)
            auth = config.get("auth", {})

            # 解析 URL 中的变量
            url = self._resolve_template(url, input_variables)

            # SSRF 检查
            ssrf_error = self._check_ssrf(url)
            if ssrf_error:
                return NodeExecutionResult(error=ssrf_error, duration_ms=self._elapsed(start_time))

            # 解析 headers 中的变量
            resolved_headers = {}
            for k, v in headers.items():
                resolved_headers[k] = self._resolve_template(str(v), input_variables)

            # 解析认证
            if auth.get("type") == "bearer":
                token = self._resolve_template(auth.get("token", ""), input_variables)
                resolved_headers["Authorization"] = f"Bearer {token}"
            elif auth.get("type") == "api_key":
                header_name = auth.get("header_name", "X-API-Key")
                key_value = self._resolve_template(auth.get("key_value", ""), input_variables)
                resolved_headers[header_name] = key_value

            # 解析 body
            request_body = None
            if body_template:
                request_body = self._resolve_template(body_template, input_variables)
            elif body:
                if isinstance(body, str):
                    request_body = self._resolve_template(body, input_variables)
                else:
                    request_body = body

            # 执行请求
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=resolved_headers,
                    content=request_body if isinstance(request_body, str) else None,
                    json=request_body if isinstance(request_body, (dict, list)) else None,
                )

            # 检查响应体大小
            content_length = len(response.content)
            if content_length > self.MAX_RESPONSE_SIZE:
                return NodeExecutionResult(
                    error=f"Response too large: {content_length} bytes (max {self.MAX_RESPONSE_SIZE})",
                    duration_ms=self._elapsed(start_time),
                )

            # 解析响应
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text

            output_key = config.get("output_key", "http_response")
            return NodeExecutionResult(
                output={
                    output_key: response_body,
                    f"{output_key}_status": response.status_code,
                    f"{output_key}_headers": dict(response.headers),
                },
                duration_ms=self._elapsed(start_time),
            )

        except httpx.TimeoutException:
            return NodeExecutionResult(error="HTTP request timed out", duration_ms=self._elapsed(start_time))
        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    def _check_ssrf(self, url: str) -> str | None:
        """SSRF 防护检查"""
        try:
            parsed = urlparse(url)
        except Exception:
            return "Invalid URL format"

        if parsed.scheme not in ("http", "https"):
            return "Only HTTP/HTTPS protocols are allowed"

        hostname = parsed.hostname or ""
        
        # 内网 IP 检查
        import re
        private_patterns = [
            r'^10\.', r'^172\.(1[6-9]|2\d|3[01])\.',
            r'^192\.168\.', r'^127\.', r'^169\.254\.',
            r'^0\.', r'^::1$', r'^fc00:', r'^fd00:',
            r'^localhost$',
        ]
        for pattern in private_patterns:
            if re.match(pattern, hostname, re.IGNORECASE):
                return f"Access to private network address '{hostname}' is not allowed"

        return None

    def _resolve_template(self, template: str, variables: dict) -> str:
        """解析模板字符串中的变量引用"""
        import re
        pattern = re.compile(r'\$\{([^}]+)\}')
        def replacer(match):
            var_name = match.group(1)
            if var_name.startswith("env."):
                return match.group(0)
            return str(variables.get(var_name, match.group(0)))
        return pattern.sub(replacer, template)

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
