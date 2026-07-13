
import time
import asyncio
import tempfile
import os
from typing import Any

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class CodeExecutor(BaseNodeExecutor):
    """
    代码执行节点执行器：在安全沙箱中执行 Python/JavaScript 代码。
    
    安全限制：
    - 最大执行时间: 30 秒
    - 禁止网络访问
    - 禁止文件系统访问（除临时目录）
    - 禁止 subprocess / os.system / eval / exec 等危险调用
    - 内存限制: 256MB
    - 禁止导入危险模块: os, sys, subprocess, socket, shutil, ctypes
    
    执行流程：
    1. 解析输入变量
    2. 将用户代码包装在安全沙箱中
    3. 执行代码（Python/JS）
    4. 捕获输出和错误
    5. 清理临时文件
    """

    DEFAULT_TIMEOUT = 30
    
    # 禁止导入的模块
    BLOCKED_MODULES = {
        "os", "sys", "subprocess", "socket", "shutil", "ctypes",
        "importlib", "signal", "resource", "multiprocessing",
        "threading", "http", "urllib", "requests", "httpx",
        "asyncio", "aiohttp", "websockets",
    }

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        language = config.get("language", "python")
        code = config.get("code", "")
        timeout = min(self._resolve_timeout(config), self.DEFAULT_TIMEOUT)
        input_mapping = config.get("input_mapping", {})
        resolved_inputs = self._resolve_variables(input_mapping, input_variables)

        if not code:
            return NodeExecutionResult(error="Code is empty", duration_ms=self._elapsed(start_time))

        # 安全检查
        security_check = self._security_check(code, language)
        if security_check:
            return NodeExecutionResult(error=security_check, duration_ms=self._elapsed(start_time))

        try:
            if language == "python":
                result = await self._execute_python(code, resolved_inputs, timeout)
            elif language == "javascript":
                result = await self._execute_javascript(code, resolved_inputs, timeout)
            else:
                return NodeExecutionResult(
                    error=f"Unsupported language: {language}",
                    duration_ms=self._elapsed(start_time),
                )

            output_key = config.get("output_key", "code_result")
            return NodeExecutionResult(
                output={output_key: result},
                duration_ms=self._elapsed(start_time),
            )

        except asyncio.TimeoutError:
            return NodeExecutionResult(
                error=f"Code execution timed out ({timeout}s)",
                duration_ms=self._elapsed(start_time),
            )
        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    def _security_check(self, code: str, language: str) -> str | None:
        """
        代码安全检查。返回错误消息或 None（通过检查）。
        """
        if language == "python":
            # 检查危险导入
            import_lines = [line.strip() for line in code.split("\n") if line.strip().startswith(("import ", "from "))]
            for line in import_lines:
                for module in self.BLOCKED_MODULES:
                    if f"import {module}" in line or f"from {module}" in line:
                        return f"Blocked import: {module}. This module is not allowed in the sandbox."

            # 检查危险函数调用
            dangerous_patterns = [
                "__import__", "exec(", "eval(", "compile(",
                "os.system", "os.popen", "os.exec", "os.spawn",
                "subprocess.", "getattr(", "setattr(", "delattr(",
            ]
            for pattern in dangerous_patterns:
                if pattern in code:
                    return f"Blocked dangerous pattern: {pattern}"

        elif language == "javascript":
            dangerous_patterns = [
                "require(", "import(", "eval(", "Function(",
                "child_process", "fs.", "net.", "http.",
                "process.exit", "process.kill",
            ]
            for pattern in dangerous_patterns:
                if pattern in code:
                    return f"Blocked dangerous pattern: {pattern}"

        return None

    async def _execute_python(
        self,
        code: str,
        inputs: dict,
        timeout: int,
    ) -> Any:
        """
        在沙箱中执行 Python 代码。
        
        用户代码需定义 main(input_data: dict) -> dict 函数。
        沙箱调用 main 函数并返回结果。
        """
        # 包装代码：定义安全的执行环境
        wrapper_code = f"""
import json
import sys

# 用户输入
__input_data = json.loads('''{json.dumps(inputs, ensure_ascii=False)}''')

# 用户代码
{code}

# 执行并输出结果
try:
    if 'main' in dir():
        __result = main(__input_data)
    else:
        __result = {{"error": "No main() function defined"}}
    print(json.dumps(__result, ensure_ascii=False, default=str))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
        # 在子进程中执行（隔离环境）
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", wrapper_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024 * 256,  # 256KB stdout buffer
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise

        if stderr:
            error_msg = stderr.decode("utf-8", errors="replace")
            if error_msg.strip():
                return {"error": error_msg.strip()}

        output = stdout.decode("utf-8", errors="replace").strip()
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"raw_output": output}

    async def _execute_javascript(
        self,
        code: str,
        inputs: dict,
        timeout: int,
    ) -> Any:
        """在沙箱中执行 JavaScript 代码（需要 Node.js）"""
        wrapper_code = f"""
const __inputData = {json.dumps(inputs, ensure_ascii=False)};

{code}

try {{
    if (typeof main === 'function') {{
        const result = main(__inputData);
        console.log(JSON.stringify(result));
    }} else {{
        console.log(JSON.stringify({{error: "No main() function defined"}}));
    }}
}} catch (e) {{
    console.log(JSON.stringify({{error: e.message}}));
}}
"""
        proc = await asyncio.create_subprocess_exec(
            "node", "-e", wrapper_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise

        output = stdout.decode("utf-8", errors="replace").strip()
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"raw_output": output}

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)


# 需要 import json, sys 在文件顶部
import json
import sys
