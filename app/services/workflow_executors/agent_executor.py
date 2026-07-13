
import time
import httpx
from typing import Any, Optional

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext
from app.core.encryption import decrypt_value


class AgentExecutor(BaseNodeExecutor):
    """
    Agent 节点执行器：调用 LLM API 执行 Agent 逻辑。
    
    执行流程：
    1. 根据 config.agent_id 从数据库查询 Agent 配置
    2. 查询 Agent 关联的 Model + Provider
    3. 解密 Provider 的 API Key
    4. 构建 messages（system_prompt + 用户输入）
    5. 调用 LLM API（根据 provider_type 选择不同 SDK）
    6. 返回 LLM 输出 + Token 统计
    """

    DEFAULT_TIMEOUT = 120  # Agent 调用 LLM 超时更长

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            # 1. 获取 Agent 配置
            agent_id = config.get("agent_id")
            if not agent_id:
                return NodeExecutionResult(error="agent_id is required", duration_ms=self._elapsed(start_time))

            agent = await self._get_agent(context, agent_id)
            if not agent:
                return NodeExecutionResult(error=f"Agent {agent_id} not found", duration_ms=self._elapsed(start_time))

            # 2. 获取模型和供应商
            model, provider = await self._get_model_and_provider(context, agent)
            if not model or not provider:
                return NodeExecutionResult(error="Model or Provider not configured", duration_ms=self._elapsed(start_time))

            # 3. 解密 API Key
            api_key = decrypt_value(provider.api_key_encrypted)

            # 4. 解析输入变量
            input_mapping = config.get("input_mapping", {})
            resolved_inputs = self._resolve_variables(input_mapping, input_variables)
            user_input = " ".join(str(v) for v in resolved_inputs.values())

            # 5. 构建 messages
            messages = []
            if agent.system_prompt:
                messages.append({"role": "system", "content": agent.system_prompt})
            messages.append({"role": "user", "content": user_input})

            # 6. 调用 LLM API
            llm_result = await self._call_llm(
                provider_type=provider.provider_type,
                api_key=api_key,
                base_url=provider.base_url,
                model_name=model.model_name,
                messages=messages,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
                timeout=self._resolve_timeout(config),
            )

            output_key = config.get("output_key", "result")
            duration_ms = self._elapsed(start_time)

            return NodeExecutionResult(
                output={output_key: llm_result["content"]},
                duration_ms=duration_ms,
                tokens_used=llm_result.get("total_tokens"),
            )

        except httpx.TimeoutException:
            return NodeExecutionResult(error="LLM API call timed out", duration_ms=self._elapsed(start_time))
        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    async def _call_llm(
        self,
        provider_type: str,
        api_key: str,
        base_url: Optional[str],
        model_name: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        timeout: int,
    ) -> dict:
        """
        根据 provider_type 调用不同的 LLM API。
        统一返回格式：{"content": str, "total_tokens": int}
        """
        if provider_type == "openai" or provider_type == "custom":
            return await self._call_openai_compatible(
                api_key=api_key,
                base_url=base_url or "https://api.openai.com/v1",
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        elif provider_type == "anthropic":
            return await self._call_anthropic(
                api_key=api_key,
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        elif provider_type == "google":
            return await self._call_google(
                api_key=api_key,
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    async def _call_openai_compatible(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        timeout: int,
    ) -> dict:
        """调用 OpenAI 兼容 API（OpenAI 官方 + 自定义兼容接口）"""
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return {
            "content": data["choices"][0]["message"]["content"],
            "total_tokens": data.get("usage", {}).get("total_tokens", 0),
        }

    async def _call_anthropic(self, api_key, model_name, messages, temperature, max_tokens, timeout) -> dict:
        """调用 Anthropic Claude API"""
        # 提取 system prompt
        system_prompt = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                chat_messages.append(msg)

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "max_tokens": max_tokens,
            "messages": chat_messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return {
            "content": data["content"][0]["text"],
            "total_tokens": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0),
        }

    async def _call_google(self, api_key, model_name, messages, temperature, max_tokens, timeout) -> dict:
        """调用 Google Gemini API"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

        # 转换 messages 为 Gemini 格式
        contents = []
        system_instruction = None
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = {"parts": {"text": msg["content"]}}
            else:
                contents.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [{"text": msg["content"]}],
                })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["candidates"][0]["content"]["parts"][0]["text"]
        total_tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)

        return {"content": content, "total_tokens": total_tokens}

    async def _get_agent(self, context, agent_id):
        """从数据库查询 Agent"""
        from sqlalchemy import select
        from app.models.agent import Agent
        result = await context.db_session.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()

    async def _get_model_and_provider(self, context, agent):
        """查询 Agent 关联的模型和供应商"""
        from sqlalchemy import select
        from app.models.model_provider import LLMModel, ModelProvider
        
        if not agent.model_id:
            return None, None

        result = await context.db_session.execute(
            select(LLMModel).where(LLMModel.id == agent.model_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None, None

        result = await context.db_session.execute(
            select(ModelProvider).where(ModelProvider.id == model.provider_id)
        )
        provider = result.scalar_one_or_none()

        return model, provider

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
