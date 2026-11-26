import pytest

from pipeline.episode import (
    Episode,
    EpisodeValidationError,
    Shot,
    count_chars,
    episode_from_json,
    episode_from_payload,
    episode_to_json,
    new_episode_id,
    validate_episode,
)


def make_episode(narrations=("东海之外有座青丘山", "山中藏着一只九尾狐")) -> Episode:
    """用给定的旁白列表造一条合法的视频。"""
    shots = [
        Shot(shot_no=index, narration=text, image_prompt="画面", motion_prompt="推近")
        for index, text in enumerate(narrations, start=1)
    ]
    return Episode(episode_id="e1", title="青丘九尾狐", topic="青丘山的九尾狐", shots=shots)


def test_count_chars_ignores_whitespace_and_keeps_punctuation():
    assert count_chars(" 东海之外，\n有座青丘山 ") == 10


def test_valid_episode_passes():
    validate_episode(make_episode())


@pytest.mark.parametrize("narration", ["", "   ", "这是一段远远超过二十个字的旁白文本，用来验证上限"])
def test_narration_must_be_1_to_20_chars(narration):
    with pytest.raises(EpisodeValidationError, match="旁白"):
        validate_episode(make_episode((narration, "山中藏着一只九尾狐")))


def test_shot_numbers_must_start_at_one_and_be_consecutive():
    shots = [Shot(shot_no=2, narration="旁白", image_prompt="画面", motion_prompt="推近")]

    with pytest.raises(EpisodeValidationError, match="shot_no 应为 1"):
        validate_episode(Episode(episode_id="e1", title="青丘九尾狐", topic="主题", shots=shots))


def test_duration_must_be_five_seconds():
    shots = [Shot(shot_no=1, narration="旁白", image_prompt="画面", motion_prompt="推近", duration_sec=5.5)]

    with pytest.raises(EpisodeValidationError, match="duration_sec"):
        validate_episode(Episode(episode_id="e1", title="青丘九尾狐", topic="主题", shots=shots))


def test_episode_without_shots_is_rejected():
    with pytest.raises(EpisodeValidationError, match="shots 不能为空"):
        validate_episode(Episode(episode_id="e1", title="青丘九尾狐", topic="主题", shots=[]))


def test_blank_title_is_rejected():
    episode = Episode(episode_id="e1", title="  ", topic="主题", shots=make_episode().shots)

    with pytest.raises(EpisodeValidationError, match="title 不能为空"):
        validate_episode(episode)


def test_blank_prompts_are_rejected():
    shots = [Shot(shot_no=1, narration="旁白", image_prompt=" ", motion_prompt="推近")]

    with pytest.raises(EpisodeValidationError, match="image_prompt"):
        validate_episode(Episode(episode_id="e1", title="青丘九尾狐", topic="主题", shots=shots))


def test_episode_from_payload_builds_validated_episode():
    payload = {
        "title": "青丘九尾狐",
        "shots": [
            {"shot_no": 1, "narration": "东海之外有座青丘山", "image_prompt": "画面", "motion_prompt": "推近", "duration_sec": 5},
            {"shot_no": 2, "narration": "山中藏着一只九尾狐", "image_prompt": "画面", "motion_prompt": "回眸"},
        ],
    }

    episode = episode_from_payload(payload, episode_id="e1", topic="青丘山")

    assert episode.episode_id == "e1"
    assert episode.topic == "青丘山"
    assert episode.shots[1].duration_sec == 5.0


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "青丘九尾狐", "shots": [{"shot_no": 1}]},
        {"title": "青丘九尾狐", "shots": ["不是对象"]},
        {"shots": []},
        {"title": None, "shots": [{"shot_no": 1, "narration": "旁白", "image_prompt": "画面", "motion_prompt": "推近"}]},
        {"title": "青丘九尾狐", "shots": [{"shot_no": 1, "narration": None, "image_prompt": "画面", "motion_prompt": "推近"}]},
        {"title": "青丘九尾狐", "shots": [{"shot_no": 1, "narration": ["第一句", "第二句"], "image_prompt": "画面", "motion_prompt": "推近"}]},
        {"title": "青丘九尾狐", "shots": [{"shot_no": 1.9, "narration": "旁白", "image_prompt": "画面", "motion_prompt": "推近"}]},
    ],
)
def test_episode_from_payload_reports_malformed_json(payload):
    with pytest.raises(EpisodeValidationError, match="JSON 结构不合法"):
        episode_from_payload(payload, episode_id="e1", topic="主题")


def test_episode_json_round_trip():
    episode = make_episode()

    assert episode_from_json(episode_to_json(episode)) == episode


def test_new_episode_id_is_unique_and_timestamped():
    first = new_episode_id()
    second = new_episode_id()

    assert first != second
    assert len(first) == len("20261125-143005-a1b2")
    assert first[:8].isdigit()
