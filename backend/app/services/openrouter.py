"""Thin async client for the OpenRouter chat-completions and models APIs.

Errors are normalized into OpenRouterError with a stable ``code`` so callers
can persist or surface a taxonomy instead of raw HTTP details.
"""

import json
import time

import httpx

from app.models import AppSettings

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_COMPLETION_TIMEOUT = 60.0
_MODELS_TIMEOUT = 15.0
_MODELS_CACHE_TTL = 300.0
_DEFAULT_REFERER = "https://acciassist.local"

_models_cache: tuple[float, list[dict]] | None = None

_STATUS_CODES = {
    401: "invalid_api_key",
    402: "insufficient_credits",
    404: "model_not_found",
    429: "rate_limited",
}


class OpenRouterError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def ai_configured(s: AppSettings) -> bool:
    return bool(s.openrouter_api_key and s.openrouter_model)


def _headers(api_key: str, referer: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": referer or _DEFAULT_REFERER,
        "X-Title": "AcciAssist",
    }


def _error_from_status(status: int, body: str) -> OpenRouterError:
    return OpenRouterError(
        _STATUS_CODES.get(status, "upstream_error"),
        f"OpenRouter returned HTTP {status}: {body[:300]}",
    )


def _price_per_million(raw: object) -> str | None:
    """OpenRouter prices are USD per token as strings; show USD per 1M tokens."""
    try:
        return f"{float(raw) * 1_000_000:g}"
    except (TypeError, ValueError):
        return None


async def fetch_models(api_key: str) -> list[dict]:
    """List available models, trimmed to what the admin UI needs. Cached for
    five minutes to avoid hammering OpenRouter while the admin browses."""
    global _models_cache
    if _models_cache is not None and time.monotonic() - _models_cache[0] < _MODELS_CACHE_TTL:
        return _models_cache[1]
    try:
        async with httpx.AsyncClient(timeout=_MODELS_TIMEOUT) as client:
            resp = await client.get(f"{OPENROUTER_BASE}/models", headers=_headers(api_key))
    except httpx.TimeoutException as exc:
        raise OpenRouterError("timeout", "OpenRouter did not respond in time") from exc
    except httpx.HTTPError as exc:
        raise OpenRouterError("upstream_error", f"Could not reach OpenRouter: {exc}") from exc
    if resp.status_code != 200:
        raise _error_from_status(resp.status_code, resp.text)
    models = []
    for m in resp.json().get("data", []):
        pricing = m.get("pricing") or {}
        models.append(
            {
                "id": m.get("id", ""),
                "name": m.get("name") or m.get("id", ""),
                "context_length": m.get("context_length"),
                "prompt_price": _price_per_million(pricing.get("prompt")),
                "completion_price": _price_per_million(pricing.get("completion")),
                "supports_structured_outputs": "structured_outputs"
                in (m.get("supported_parameters") or []),
            }
        )
    models.sort(key=lambda m: m["id"])
    _models_cache = (time.monotonic(), models)
    return models


def clear_models_cache() -> None:
    global _models_cache
    _models_cache = None


async def _get_json(path: str, api_key: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_MODELS_TIMEOUT) as client:
            resp = await client.get(f"{OPENROUTER_BASE}{path}", headers=_headers(api_key))
    except httpx.TimeoutException as exc:
        raise OpenRouterError("timeout", "OpenRouter did not respond in time") from exc
    except httpx.HTTPError as exc:
        raise OpenRouterError("upstream_error", f"Could not reach OpenRouter: {exc}") from exc
    if resp.status_code == 403:
        raise OpenRouterError(
            "credits_forbidden",
            "This key is not allowed to read the account balance",
        )
    if resp.status_code != 200:
        raise _error_from_status(resp.status_code, resp.text)
    try:
        return resp.json().get("data") or {}
    except json.JSONDecodeError as exc:
        raise OpenRouterError("upstream_error", "OpenRouter returned invalid JSON") from exc


async def fetch_credits(api_key: str) -> dict:
    """Account-wide balance: ``{"total_credits": float, "total_usage": float}``.
    OpenRouter may require a management/provisioning key for this endpoint."""
    return await _get_json("/credits", api_key)


async def fetch_key_info(api_key: str) -> dict:
    """Info about the key itself (``usage``, ``limit``, ``limit_remaining``…) —
    works with a plain inference key, unlike /credits."""
    return await _get_json("/key", api_key)


def _structured_output_rejected(status: int, body: str) -> bool:
    lowered = body.lower()
    if status not in (400, 404, 422):
        return False
    if "response_format" in lowered or "structured" in lowered or "json_schema" in lowered:
        return True
    # OpenRouter's routing error when require_parameters finds no provider,
    # e.g. "No endpoints found that support the requested parameters".
    return "parameter" in lowered and ("endpoint" in lowered or "support" in lowered)


async def _post_completion(client: httpx.AsyncClient, headers: dict, body: dict) -> httpx.Response:
    try:
        return await client.post(
            f"{OPENROUTER_BASE}/chat/completions", headers=headers, json=body
        )
    except httpx.TimeoutException as exc:
        raise OpenRouterError("timeout", "The AI model did not respond in time") from exc
    except httpx.HTTPError as exc:
        raise OpenRouterError("upstream_error", f"Could not reach OpenRouter: {exc}") from exc


async def chat_completion(
    api_key: str,
    model: str,
    messages: list[dict],
    json_schema: dict | None = None,
    schema_name: str = "response",
    referer: str | None = None,
    temperature: float | None = None,
    plugins: list[dict] | None = None,
    timeout: float = _COMPLETION_TIMEOUT,
    require_parameters: bool = True,
    return_annotations: bool = False,
) -> str | tuple[str, list]:
    """Run one non-streaming completion and return the assistant content.

    When ``json_schema`` is given, strict structured output is requested first;
    if the model/provider rejects the parameter, the request is retried once
    without it (the caller is expected to parse JSON out of free text).
    ``require_parameters=False`` skips the provider-routing constraint — needed
    for web-plugin calls, where the combination often routes to no provider.
    With ``return_annotations=True`` the return value is ``(content,
    annotations)`` where annotations are OpenRouter web-citation entries.
    """
    headers = _headers(api_key, referer)
    body: dict = {"model": model, "messages": messages}
    if temperature is not None:
        body["temperature"] = temperature
    if plugins is not None:
        body["plugins"] = plugins
    if json_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": json_schema},
        }
        # Route only to providers that actually enforce response_format —
        # some hosts accept the parameter and silently ignore it, which
        # surfaces downstream as an unparseable reply.
        if require_parameters:
            body["provider"] = {"require_parameters": True}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await _post_completion(client, headers, body)
        if (
            resp.status_code != 200
            and json_schema is not None
            and _structured_output_rejected(resp.status_code, resp.text)
        ):
            body.pop("response_format")
            body.pop("provider", None)
            resp = await _post_completion(client, headers, body)
    if resp.status_code != 200:
        raise _error_from_status(resp.status_code, resp.text)
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise OpenRouterError("upstream_error", "OpenRouter returned invalid JSON") from exc
    # OpenRouter can return 200 with an error object in the body.
    if isinstance(data.get("error"), dict):
        err = data["error"]
        raise _error_from_status(int(err.get("code") or 500), str(err.get("message") or ""))
    choices = data.get("choices") or []
    if choices and choices[0].get("finish_reason") == "length":
        raise OpenRouterError(
            "truncated",
            "The model's reply was cut off before it finished; "
            "try a model with a larger output limit",
        )
    message = (choices[0].get("message") or {}) if choices else {}
    content = message.get("content")
    if not content:
        raise OpenRouterError("empty_response", "The AI model returned an empty response")
    if return_annotations:
        annotations = message.get("annotations")
        return content, annotations if isinstance(annotations, list) else []
    return content
