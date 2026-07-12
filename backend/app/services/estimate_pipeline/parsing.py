"""Tolerant JSON extraction from model replies (shared by all AI features)."""

import json
import re

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
