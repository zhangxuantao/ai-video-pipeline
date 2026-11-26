import json

import httpx
import pytest

from pipeline.script import MAX_ATTEMPTS, DeepSeekClient, ScriptError, generate_episode

VALID_PAYLOAD = {
    "title": "青丘九尾狐",
    "shots": [
        {"shot_no": 1, "narration": "东海之外有座青丘山", "image_prompt": "云海中的青丘山", "motion_prompt": "镜头缓缓推近", "duration_sec": 5},
        {"shot_no": 2, "narration": "山中藏着一只九尾狐", "image_prompt": "山洞中的九尾狐", "motion_prompt": "九尾狐回眸", "duration_sec": 5},
    ],
}
TOO_LONG_NARRATION = {
    "title": "青丘九尾狐",
    "shots": [
        dict(VALID_PAYLOAD["shots"][0], narration="这是一段远远超过二十个字的旁白文本，用来验证上限"),
        VALID_PAYLOAD["shots"][1],
    ],
}


def make_client(handler, **options) -> DeepSeekClient:
    """用替身传输层构造 DeepSeek 客户端，不发生真实网络请求。"""
    return DeepSeekClient(
        api_key="sk-test",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        backoff_seconds=0,
        **options,
    )


def chat_response(payload) -> httpx.Response:
    """构造一次正常的对话响应；payload 是字典时序列化成 JSON 文本，是字符串时原样返回。"""
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_generate_episode_returns_validated_episode():
    requests = []

    def handler(request):
        requests.append(request)
        return chat_response(VALID_PAYLOAD)

    episode = generate_episode(make_client(handler), "青丘山的九尾狐", "e1", shot_count=2)

    assert episode.episode_id == "e1"
    assert [shot.shot_no for shot in episode.shots] == [1, 2]
    body = json.loads(requests[0].content)
    assert requests[0].headers["authorization"] == "Bearer sk-test"
    assert body["response_format"] == {"type": "json_object"}
    assert "正好有 2 个元素" in body["messages"][0]["content"]
    assert "主题：青丘山的九尾狐" in body["messages"][1]["content"]


def test_generate_episode_asks_for_rewrite_until_output_is_valid():
    outputs = [TOO_LONG_NARRATION, VALID_PAYLOAD]
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return chat_response(outputs.pop(0))

    episode = generate_episode(make_client(handler), "青丘山的九尾狐", "e1", shot_count=2)

    assert episode.shots[0].narration == "东海之外有座青丘山"
    assert "不符合要求" in requests[1]["messages"][1]["content"]
    assert "旁白" in requests[1]["messages"][1]["content"]


def test_generate_episode_rejects_wrong_shot_count_then_gives_up():
    calls = []

    def handler(request):
        calls.append(request)
        return chat_response({"title": "青丘九尾狐", "shots": VALID_PAYLOAD["shots"]})

    with pytest.raises(ScriptError, match=f"连续 {MAX_ATTEMPTS} 次"):
        generate_episode(make_client(handler), "青丘山的九尾狐", "e1", shot_count=3)

    assert len(calls) == MAX_ATTEMPTS


def test_client_retries_on_server_error():
    statuses = [503, 200]

    def handler(request):
        return httpx.Response(503, text="busy") if statuses.pop(0) == 503 else chat_response(VALID_PAYLOAD)

    assert make_client(handler).complete_json([{"role": "user", "content": "你好"}]) == VALID_PAYLOAD


def test_client_fails_fast_on_auth_error():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(ScriptError, match="401"):
        make_client(handler).complete_json([{"role": "user", "content": "你好"}])

    assert len(calls) == 1


def test_client_gives_up_after_repeated_server_errors():
    with pytest.raises(ScriptError, match="连续 3 次"):
        make_client(lambda request: httpx.Response(500, text="boom")).complete_json(
            [{"role": "user", "content": "你好"}]
        )


def test_client_rejects_output_that_is_not_json():
    with pytest.raises(ScriptError, match="不是合法 JSON"):
        make_client(lambda request: chat_response("抱歉，我无法输出 JSON")).complete_json(
            [{"role": "user", "content": "你好"}]
        )


def test_client_reports_malformed_response_body():
    with pytest.raises(ScriptError, match="响应结构不合法"):
        make_client(lambda request: httpx.Response(200, json={"choices": []})).complete_json(
            [{"role": "user", "content": "你好"}]
        )


def test_client_reports_content_that_is_not_text():
    body = {"choices": [{"message": {"content": None}}]}

    with pytest.raises(ScriptError, match="响应结构不合法"):
        make_client(lambda request: httpx.Response(200, json=body)).complete_json(
            [{"role": "user", "content": "你好"}]
        )


def test_client_can_be_created_when_proxy_settings_do_not_parse(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "[::1]")

    assert DeepSeekClient(api_key="sk-test")._http is not None
