"""Tolerant JSON extraction from model replies (shared by all AI features)."""

import json
import logging
import re

from pydantic import ValidationError

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_THINK_BLOCK = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)


def extract_json_object(content: str) -> dict:
    """Pull a JSON object out of a model reply, tolerating code fences,
    surrounding prose, and reasoning-model <think> blocks (whose braces would
    otherwise corrupt the first-{...}-to-last-} extraction)."""
    text = _THINK_BLOCK.sub("", content).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if match is None:
            raise ValueError("no JSON object found in model response") from None
        return json.loads(match.group(0))


_REPAIR_INSTRUCTION = (
    "Your previous reply did not match the required JSON schema ({error}). "
    "Reply again with ONLY a JSON object that matches the schema exactly, "
    "using exactly the schema's field names."
)


async def call_with_schema_repair(call, messages: list[dict], parse):
    """Run ``call(messages)`` and ``parse`` the reply; on a schema mismatch,
    retry once with the validation error fed back. Some providers accept
    ``response_format`` yet let the model drift from it — reasoning models
    in particular have been seen renaming required fields."""
    content = await call(messages)
    try:
        return parse(content)
    except (ValueError, ValidationError) as exc:
        logger.warning("unusable model reply (%s); raw reply: %.1000s", exc, content)
        retry = [
            *messages,
            {"role": "assistant", "content": content},
            {"role": "user", "content": _REPAIR_INSTRUCTION.format(error=str(exc)[:500])},
        ]
        retry_content = await call(retry)
        try:
            return parse(retry_content)
        except (ValueError, ValidationError) as retry_exc:
            logger.warning(
                "repair retry also unusable (%s); raw reply: %.1000s", retry_exc, retry_content
            )
            raise
