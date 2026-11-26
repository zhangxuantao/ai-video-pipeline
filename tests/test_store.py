import pytest

from pipeline.episode import Episode, Shot
from pipeline.store import Store, StoreError


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "pipeline.db")


def make_episode(shot_count=2, episode_id="e1") -> Episode:
    """造一条合法视频，供各个用例按需取用。

    @param shot_count: 镜头数
    @param episode_id: 视频编号
    @return: 合法的视频
    """
    shots = [
        Shot(shot_no=number, narration=f"第{number}句旁白", image_prompt="画面", motion_prompt="推近")
        for number in range(1, shot_count + 1)
    ]
    return Episode(episode_id=episode_id, title="青丘九尾狐", topic="青丘山的九尾狐", shots=shots)


def test_create_episode_starts_in_created_state(tmp_path):
    record = make_store(tmp_path).create_episode("青丘山的九尾狐", "e1")

    assert (record.status, record.topic, record.error) == ("created", "青丘山的九尾狐", "")


def test_save_script_fills_shots_as_pending(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")

    store.save_script("e1", make_episode(2))

    assert store.get_episode("e1").status == "scripted"
    shots = store.get_shots("e1")
    assert [(shot.shot_no, shot.status, shot.narration) for shot in shots] == [(1, "pending", "第1句旁白"), (2, "pending", "第2句旁白")]


def test_save_script_twice_replaces_shots(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")
    store.save_script("e1", make_episode(2))

    store.save_script("e1", make_episode(3))

    assert [shot.shot_no for shot in store.get_shots("e1")] == [1, 2, 3]


def test_save_script_rejects_mismatched_episode_id(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")

    with pytest.raises(ValueError, match="episode_id 不一致"):
        store.save_script("other", make_episode())


def test_update_shot_changes_only_allowed_columns(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")
    store.save_script("e1", make_episode())

    store.update_shot("e1", 1, status="keyframed", keyframe_path="keyframe_001.png", seed=42, attempts=1, error="")

    shot = store.get_shots("e1")[0]
    assert (shot.status, shot.keyframe_path, shot.seed, shot.attempts) == ("keyframed", "keyframe_001.png", 42, 1)
    with pytest.raises(ValueError, match="不能更新这些列"):
        store.update_shot("e1", 1, narration="改剧本")


def test_set_episode_status_records_error(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")

    store.set_episode_status("e1", "failed", error="这些镜头生成失败：[2]")
    store.set_episode_status("e1", "rendering")

    assert store.get_episode("e1").status == "rendering"
    assert store.get_episode("e1").error == ""
    store.set_episode_status("e1", "failed", error="又失败了")
    assert store.get_episode("e1").error == "又失败了"


def test_missing_records_raise_store_error(tmp_path):
    store = make_store(tmp_path)

    with pytest.raises(StoreError, match="找不到视频"):
        store.get_episode("nope")
    with pytest.raises(StoreError, match="找不到视频"):
        store.save_script("nope", make_episode(episode_id="nope"))
    assert store.get_shots("nope") == []
    with pytest.raises(StoreError, match="找不到镜头"):
        store.update_shot("nope", 1, status="failed")


def test_list_episodes_orders_newest_first(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("第一条", "e1")
    store.create_episode("第二条", "e2")

    assert [record.episode_id for record in store.list_episodes()] == ["e2", "e1"]
