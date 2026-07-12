import json

import pytest

from app.services import openrouter
from app.services.openrouter import OpenRouterError


class FakeResponse:
    def __init__(self, status_code: int, payload: object = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise json.JSONDecodeError("no payload", "", 0)
        return self._payload


class FakeClient:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.requests: list[tuple[str, str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None):
        self.requests.append(("GET", url, None))
        return self.responses.pop(0)

    async def post(self, url, headers=None, json=None):
        # Snapshot: the client mutates the body dict between retry attempts.
        self.requests.append(("POST", url, dict(json)))
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def _fresh_models_cache():
    openrouter.clear_models_cache()
    yield
    openrouter.clear_models_cache()


def _install(monkeypatch, fake: FakeClient) -> None:
    monkeypatch.setattr(openrouter.httpx, "AsyncClient", lambda **kwargs: fake)


MODELS_PAYLOAD = {
    "data": [
        {
            "id": "vendor/model-b",
            "name": "Model B",
            "context_length": 200000,
            "pricing": {"prompt": "0.000003", "completion": "0.000015"},
            "supported_parameters": ["structured_outputs", "temperature"],
        },
        {
            "id": "vendor/model-a",
            "name": "Model A",
            "context_length": 8192,
            "pricing": {"prompt": "bogus"},
            "supported_parameters": [],
        },
    ]
}


async def test_fetch_models_trims_sorts_and_caches(monkeypatch):
    fake = FakeClient([FakeResponse(200, MODELS_PAYLOAD)])
    _install(monkeypatch, fake)

    models = await openrouter.fetch_models("sk-or-test")
    assert [m["id"] for m in models] == ["vendor/model-a", "vendor/model-b"]
    assert models[1] == {
        "id": "vendor/model-b",
        "name": "Model B",
        "context_length": 200000,
        "prompt_price": "3",
        "completion_price": "15",
        "supports_structured_outputs": True,
    }
    assert models[0]["prompt_price"] is None

    again = await openrouter.fetch_models("sk-or-test")
    assert again == models
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "invalid_api_key"), (402, "insufficient_credits"), (429, "rate_limited"),
     (500, "upstream_error")],
)
async def test_fetch_models_error_taxonomy(monkeypatch, status, code):
    _install(monkeypatch, FakeClient([FakeResponse(status, text="nope")]))
    with pytest.raises(OpenRouterError) as exc:
        await openrouter.fetch_models("sk-or-test")
    assert exc.value.code == code


async def test_chat_completion_returns_content_and_sends_schema(monkeypatch):
    fake = FakeClient(
        [FakeResponse(200, {"choices": [{"message": {"content": "{\"x\": 1}"}}]})]
    )
    _install(monkeypatch, fake)
    content = await openrouter.chat_completion(
        "sk-or-test", "vendor/model-b", [{"role": "user", "content": "hi"}],
        json_schema={"type": "object"}, schema_name="thing",
    )
    assert content == '{"x": 1}'
    body = fake.requests[0][2]
    assert body["response_format"]["json_schema"]["name"] == "thing"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["provider"] == {"require_parameters": True}


async def test_chat_completion_retries_without_rejected_schema(monkeypatch):
    fake = FakeClient(
        [
            FakeResponse(400, text="response_format is not supported by this model"),
            FakeResponse(200, {"choices": [{"message": {"content": "plain text"}}]}),
        ]
    )
    _install(monkeypatch, fake)
    content = await openrouter.chat_completion(
        "sk-or-test", "vendor/model-a", [{"role": "user", "content": "hi"}],
        json_schema={"type": "object"},
    )
    assert content == "plain text"
    assert "response_format" in fake.requests[0][2]
    assert "response_format" not in fake.requests[1][2]
    assert "provider" not in fake.requests[1][2]


async def test_chat_completion_retries_when_no_provider_supports_parameters(monkeypatch):
    fake = FakeClient(
        [
            FakeResponse(404, text="No endpoints found that support the requested parameters"),
            FakeResponse(200, {"choices": [{"message": {"content": "plain text"}}]}),
        ]
    )
    _install(monkeypatch, fake)
    content = await openrouter.chat_completion(
        "sk-or-test", "vendor/model-a", [{"role": "user", "content": "hi"}],
        json_schema={"type": "object"},
    )
    assert content == "plain text"
    assert "provider" not in fake.requests[1][2]


async def test_chat_completion_truncated_reply_is_an_error(monkeypatch):
    fake = FakeClient(
        [
            FakeResponse(
                200,
                {"choices": [{"finish_reason": "length",
                              "message": {"content": '{"overview": "cut of'}}]},
            )
        ]
    )
    _install(monkeypatch, fake)
    with pytest.raises(OpenRouterError) as exc:
        await openrouter.chat_completion(
            "sk-or-test", "vendor/model-b", [{"role": "user", "content": "hi"}]
        )
    assert exc.value.code == "truncated"


async def test_chat_completion_error_in_200_body(monkeypatch):
    fake = FakeClient(
        [FakeResponse(200, {"error": {"code": 429, "message": "rate limited"}})]
    )
    _install(monkeypatch, fake)
    with pytest.raises(OpenRouterError) as exc:
        await openrouter.chat_completion(
            "sk-or-test", "vendor/model-b", [{"role": "user", "content": "hi"}]
        )
    assert exc.value.code == "rate_limited"


async def test_chat_completion_empty_response(monkeypatch):
    fake = FakeClient([FakeResponse(200, {"choices": []})])
    _install(monkeypatch, fake)
    with pytest.raises(OpenRouterError) as exc:
        await openrouter.chat_completion(
            "sk-or-test", "vendor/model-b", [{"role": "user", "content": "hi"}]
        )
    assert exc.value.code == "empty_response"
