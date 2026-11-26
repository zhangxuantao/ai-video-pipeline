"""脚本阶段：调用 DeepSeek 生成分镜脚本，并强制校验硬性约束。"""

import json
import time

import httpx

from pipeline.episode import MAX_NARRATION_CHARS, Episode, EpisodeValidationError, episode_from_payload

MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

SYSTEM_PROMPT_TEMPLATE = """你是短视频《AI 经典奇谈》的分镜编剧。题材取自《山海经》和中国古代神话志怪，基调是奇观与想象，不涉及灵异恐怖、血腥暴力。
只输出一个 JSON 对象，不要输出任何解释，也不要加代码块标记。JSON 结构如下：
{{"title": "片名", "shots": [{{"shot_no": 1, "narration": "本镜旁白", "image_prompt": "画面描述", "motion_prompt": "运镜描述", "duration_sec": 5}}]}}
硬性要求：
1. shots 必须正好有 {shot_count} 个元素，shot_no 从 1 开始连续编号。
2. 每镜 narration 是不超过 {max_chars} 个字的中文旁白，标点计入字数；口语化，有悬念。
3. image_prompt 用{prompt_language}描述这一镜的静态画面，必须体现这种画风：{style_guide}。画面里不要出现文字、水印、明星以及影视和游戏里的角色。
4. motion_prompt 用{prompt_language}描述这 5 秒内的镜头运动和画面中事物的动作。
5. 相邻镜头的画面差异要明显，整条片子讲一个完整的小故事。"""


class ScriptError(RuntimeError):
    """脚本阶段失败。

    @author zxt
    @date 2026-11-25
    """


def _new_http_client(timeout: httpx.Timeout) -> httpx.Client:
    """新建 HTTP 客户端，环境里的代理设置能用就用。

    @param timeout: 超时配置
    @return: 可用的 HTTP 客户端
    """
    try:
        return httpx.Client(timeout=timeout)
    except httpx.InvalidURL:
        # 有的环境把 NO_PROXY 写成 [::1] 这类 httpx 解析不了的形式，这种环境里的代理设置不可信，改为完全不读环境变量
        return httpx.Client(timeout=timeout, trust_env=False)


class DeepSeekClient:
    """DeepSeek 对话接口的最小封装，只负责发请求并取回 JSON 对象。

    @author zxt
    @date 2026-11-25
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        http: httpx.Client | None = None,
        max_attempts: int = MAX_ATTEMPTS,
        backoff_seconds: float = 1.0,
    ):
        """
        @param api_key: 接口密钥
        @param base_url: 接口地址
        @param model: 模型名
        @param http: 用于发请求的 HTTP 客户端，默认新建；测试时注入替身
        @param max_attempts: 单次请求的最大尝试次数
        @param backoff_seconds: 重试间隔的基数，按指数增长
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http = http or _new_http_client(httpx.Timeout(120.0, connect=10.0))
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    def complete_json(self, messages: list[dict[str, str]]) -> dict:
        """发送一轮对话并返回模型输出的 JSON 对象。

        网络错误和限流自动重试；鉴权失败等客户端错误直接报错，不重试。

        @param messages: 对话消息列表
        @return: 模型输出的 JSON 对象
        """
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return self._request_once(messages)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in RETRYABLE_STATUS:
                    raise ScriptError(f"DeepSeek 返回 {exc.response.status_code}：{exc.response.text[:300]}") from exc
                last_error = exc
            except httpx.TransportError as exc:
                last_error = exc
            if attempt < self._max_attempts:
                time.sleep(self._backoff_seconds * 2 ** (attempt - 1))
        raise ScriptError(f"DeepSeek 连续 {self._max_attempts} 次请求失败，最后一次：{last_error}") from last_error

    def _request_once(self, messages: list[dict[str, str]]) -> dict:
        """
        @param messages: 对话消息列表
        @return: 模型输出的 JSON 对象
        """
        response = self._http.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": messages,
                "temperature": 1.0,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError(f"content 不是字符串，而是 {type(content).__name__}")
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise ScriptError(f"DeepSeek 响应结构不合法：{exc!r}") from exc
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ScriptError(f"模型输出不是合法 JSON：{content[:200]}") from exc
        if not isinstance(payload, dict):
            raise ScriptError("模型输出的 JSON 不是对象")
        return payload


def generate_episode(
    client: DeepSeekClient,
    topic: str,
    episode_id: str,
    shot_count: int,
    style_guide: str = "",
    prompt_language: str = "中文",
) -> Episode:
    """生成分镜脚本；输出不满足硬性约束时带着错误信息重写，直到通过或用尽次数。

    @param client: DeepSeek 客户端
    @param topic: 视频主题
    @param episode_id: 视频编号
    @param shot_count: 镜头数
    @param style_guide: 画风描述，会写进每镜的画面要求
    @param prompt_language: 画面描述和运镜描述使用的语言
    @return: 校验通过的 Episode
    """
    system = SYSTEM_PROMPT_TEMPLATE.format(
        shot_count=shot_count,
        max_chars=MAX_NARRATION_CHARS,
        style_guide=style_guide or "统一的中国古典志怪绘画风格",
        prompt_language=prompt_language,
    )
    errors: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        user = f"主题：{topic}"
        if errors:
            user += "\n\n上一次的输出不符合要求，请全部重新输出，不要解释：\n" + "\n".join(errors)
        payload = client.complete_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        try:
            episode = episode_from_payload(payload, episode_id, topic)
            if len(episode.shots) != shot_count:
                raise EpisodeValidationError(f"shots 必须正好有 {shot_count} 个元素，实际是 {len(episode.shots)} 个")
        except EpisodeValidationError as exc:
            errors = [str(exc)]
            continue
        return episode
    raise ScriptError(f"分镜脚本连续 {MAX_ATTEMPTS} 次不满足要求，最后一次的错误：{errors[-1]}")
