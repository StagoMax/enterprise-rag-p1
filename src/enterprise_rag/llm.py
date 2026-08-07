import re
import time
from typing import Protocol

import httpx

# 推理型模型（如 GLM）会把思维链放在 <think> 块里；引用约束校验和最终答案都不应看到它。
_THINK_BLOCK = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"<think>.*\Z", flags=re.DOTALL | re.IGNORECASE)
_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class LlmUnavailableError(RuntimeError):
    """生成后端不可用；调用方应降级到摘录式回答而不是编造内容。"""


def strip_reasoning(text: str) -> str:
    """移除思维链标记。未闭合的 <think> 说明输出被 max_tokens 截断，同样丢弃。"""
    without_blocks = _THINK_BLOCK.sub("", text)
    return _UNCLOSED_THINK.sub("", without_blocks).strip()


class ChatModel(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class OpenAiCompatibleChatModel:
    """OpenAI 兼容 /chat/completions 适配器，可指向 vLLM、托管网关或本地服务。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 90.0,
        max_tokens: int = 1200,
        temperature: float = 0.0,
        max_retries: int = 2,
        disable_thinking: bool = True,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url or not model:
            raise ValueError("LLM base_url 和 model 不能为空")
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_retries = max(max_retries, 0)
        self._disable_thinking = disable_thinking
        self._owns_client = client is None
        self.request_count = 0
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _payload(
        self, system_prompt: str, user_prompt: str, *, thinking: bool
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if not thinking:
            # GLM 系列专有开关，可显著减少输出 token；其他后端可能拒绝，见下方降级逻辑。
            payload["thinking"] = {"type": "disabled"}
        return payload

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        thinking_disabled = self._disable_thinking
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                self.request_count += 1
                response = self._client.post(
                    "/chat/completions",
                    json=self._payload(
                        system_prompt, user_prompt, thinking=not thinking_disabled
                    ),
                )
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if response.status_code == 400 and thinking_disabled:
                    # 后端不认识 thinking 参数，去掉后重试一次，不消耗退避次数。
                    thinking_disabled = False
                    continue
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = LlmUnavailableError(
                        self._error_description(response, retryable=True)
                    )
                elif response.is_error:
                    raise LlmUnavailableError(self._error_description(response))
                else:
                    return self._extract(response.json())

            if attempt < self._max_retries:
                time.sleep(0.5 * (2**attempt))

        raise LlmUnavailableError(f"生成后端在重试后仍不可用：{last_error}")

    @staticmethod
    def _error_description(response: httpx.Response, *, retryable: bool = False) -> str:
        prefix = "生成后端返回可重试状态" if retryable else "生成后端返回"
        detail = ""
        try:
            body = response.json()
        except (ValueError, TypeError):
            body = None
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                message = error.get("message")
                parts = [
                    f"code={code}" if isinstance(code, str) and code else "",
                    " ".join(message.split())[:300]
                    if isinstance(message, str) and message
                    else "",
                ]
                detail = "; ".join(part for part in parts if part)
        suffix = f" ({detail})" if detail else ""
        return f"{prefix} {response.status_code}{suffix}"

    @staticmethod
    def _extract(body: dict[str, object]) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlmUnavailableError("生成后端响应缺少 choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise LlmUnavailableError("生成后端响应缺少 message.content")
        answer = strip_reasoning(content)
        if not answer:
            # 思维链占满了 max_tokens，正文为空。宁可降级也不返回空答案。
            raise LlmUnavailableError("生成后端只返回了思维链，正文为空")
        return answer
