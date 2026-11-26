"""一条视频的数据契约：Episode 表示整条视频，Shot 表示单个镜头。"""

import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime

MAX_NARRATION_CHARS = 20
SHOT_SECONDS = 5.0


class EpisodeValidationError(ValueError):
    """分镜脚本不符合硬性约束。

    @author zxt
    @date 2026-11-25
    """


@dataclass(frozen=True)
class Shot:
    """单个镜头：一段固定 5 秒的画面及其旁白。

    @author zxt
    @date 2026-11-25
    """

    shot_no: int
    narration: str
    image_prompt: str
    motion_prompt: str
    duration_sec: float = SHOT_SECONDS


@dataclass(frozen=True)
class Episode:
    """一条完整的视频：编号、标题、主题和有序的镜头列表。

    @author zxt
    @date 2026-11-25
    """

    episode_id: str
    title: str
    topic: str
    shots: list[Shot]


def count_chars(text: str) -> int:
    """统计去掉空白后的字符数，标点计入。

    @param text: 待统计的文本
    @return: 字符数
    """
    return len("".join(text.split()))


def new_episode_id(now: datetime | None = None) -> str:
    """生成形如 20261125-143005-a1b2 的唯一编号。

    @param now: 用于编号的时间，默认取当前时间
    @return: 视频编号
    """
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


def validate_episode(episode: Episode) -> None:
    """校验分镜脚本的硬性约束，不满足时抛出 EpisodeValidationError。

    @param episode: 待校验的视频
    """
    if not count_chars(episode.title):
        raise EpisodeValidationError("title 不能为空")
    if not episode.shots:
        raise EpisodeValidationError("shots 不能为空")
    for index, shot in enumerate(episode.shots, start=1):
        where = f"第 {index} 镜"
        if shot.shot_no != index:
            raise EpisodeValidationError(f"{where}的 shot_no 应为 {index}，实际是 {shot.shot_no}")
        length = count_chars(shot.narration)
        if not 1 <= length <= MAX_NARRATION_CHARS:
            raise EpisodeValidationError(f"{where}旁白 {length} 字，必须在 1 到 {MAX_NARRATION_CHARS} 字之间")
        if not shot.image_prompt.strip():
            raise EpisodeValidationError(f"{where}的 image_prompt 不能为空")
        if not shot.motion_prompt.strip():
            raise EpisodeValidationError(f"{where}的 motion_prompt 不能为空")
        if shot.duration_sec != SHOT_SECONDS:
            raise EpisodeValidationError(f"{where}的 duration_sec 必须是 {SHOT_SECONDS}")


def _text(value: object, field: str) -> str:
    """取出必须是字符串的字段。

    @param value: JSON 里的值
    @param field: 字段名，用于报错
    @return: 原样的字符串
    """
    if not isinstance(value, str):
        raise TypeError(f"{field} 不是字符串，而是 {type(value).__name__}")
    return value


def _integer(value: object, field: str) -> int:
    """取出必须是整数的字段，布尔值不算整数。

    @param value: JSON 里的值
    @param field: 字段名，用于报错
    @return: 原样的整数
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} 不是整数，而是 {type(value).__name__}")
    return value


def _number(value: object, field: str) -> float:
    """取出必须是数字的字段，布尔值不算数字。

    @param value: JSON 里的值
    @param field: 字段名，用于报错
    @return: 转成浮点数后的值
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} 不是数字，而是 {type(value).__name__}")
    return float(value)


def episode_from_payload(payload: dict, episode_id: str, topic: str) -> Episode:
    """把脚本阶段给出的 JSON 对象转成 Episode，并校验硬性约束。

    字段类型不对时一律报"JSON 结构不合法"，不做强制转换。大模型把旁白输出成 null 或数组时，
    如果转成字符串 "None" 或 "['..']"，会通过字数校验并一路进入配音和出图。

    @param payload: 含 title 和 shots 的字典
    @param episode_id: 视频编号
    @param topic: 视频主题
    @return: 校验通过的 Episode
    """
    try:
        if not isinstance(payload, dict):
            raise TypeError(f"脚本不是 JSON 对象，而是 {type(payload).__name__}")
        items = payload["shots"]
        if not isinstance(items, list):
            raise TypeError(f"shots 不是数组，而是 {type(items).__name__}")
        shots = []
        for item in items:
            if not isinstance(item, dict):
                raise TypeError(f"shots 的元素不是对象，而是 {type(item).__name__}")
            shots.append(
                Shot(
                    shot_no=_integer(item["shot_no"], "shot_no"),
                    narration=_text(item["narration"], "narration"),
                    image_prompt=_text(item["image_prompt"], "image_prompt"),
                    motion_prompt=_text(item["motion_prompt"], "motion_prompt"),
                    duration_sec=_number(item.get("duration_sec", SHOT_SECONDS), "duration_sec"),
                )
            )
        episode = Episode(episode_id=episode_id, title=_text(payload["title"], "title"), topic=topic, shots=shots)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise EpisodeValidationError(f"JSON 结构不合法：{exc!r}") from exc
    validate_episode(episode)
    return episode


def episode_to_dict(episode: Episode) -> dict:
    """把 Episode 转成可直接 JSON 序列化的字典。

    @param episode: 视频
    @return: 字典
    """
    return asdict(episode)


def episode_to_json(episode: Episode) -> str:
    """把 Episode 序列化成 JSON 文本，用于存入状态库。

    @param episode: 视频
    @return: JSON 文本
    """
    return json.dumps(episode_to_dict(episode), ensure_ascii=False)


def episode_from_json(text: str) -> Episode:
    """从 episode_to_json 的输出还原 Episode。

    @param text: JSON 文本
    @return: 视频
    """
    data = json.loads(text)
    return Episode(
        episode_id=data["episode_id"],
        title=data["title"],
        topic=data["topic"],
        shots=[Shot(**item) for item in data["shots"]],
    )
