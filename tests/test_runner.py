from pathlib import Path

import pytest

from pipeline.fakes import FakeImageGenerator, FakeTtsBackend, FakeVideoGenerator, fake_episode
from pipeline.runner import PipelineRunner
from pipeline.store import Store


class FlakyImages:
    """对指定画面描述先失败若干次的替身，用来验证换种子重试。"""

    def __init__(self, prompts_that_fail=(), failures=1):
        self.prompts_that_fail = set(prompts_that_fail)
        self.failures = failures
        self.seeds = []

    def generate_image(self, prompt, seed, dest_dir, name):
        self.seeds.append(seed)
        if prompt in self.prompts_that_fail and self.failures > 0:
            self.failures -= 1
            raise RuntimeError("显存不足")
        return FakeImageGenerator().generate_image(prompt, seed, dest_dir, name)


@pytest.fixture
def harness(tmp_path, ffmpeg):
    """建好一条 3 镜视频的状态库，返回用于装配 runner 的函数、状态库、合成调用的记录和临时目录。"""
    store = Store(tmp_path / "pipeline.db")
    store.create_episode("青丘山的九尾狐", "e1")
    store.save_script("e1", fake_episode("青丘山的九尾狐", "e1", 3))
    compose_calls = []

    def fake_compose(request):
        compose_calls.append(request)
        request.out_path.write_bytes(b"mp4")
        return request.out_path

    def build(images=None, compose_fn=fake_compose):
        return PipelineRunner(
            store=store,
            images=images or FakeImageGenerator(),
            videos=FakeVideoGenerator(ffmpeg),
            voice=FakeTtsBackend(),
            compose_fn=compose_fn,
            work_dir=tmp_path / "work",
            deliver_dir=tmp_path / "deliver",
        )

    return build, store, compose_calls, tmp_path


def test_run_episode_delivers_video_with_every_shot_voiced(harness):
    build, store, compose_calls, tmp_path = harness

    record = build().run_episode("e1")

    assert record.status == "done"
    assert (tmp_path / "deliver" / "e1.mp4").read_bytes() == b"mp4"
    shots = store.get_shots("e1")
    assert [shot.status for shot in shots] == ["voiced"] * 3
    for shot in shots:
        assert Path(shot.keyframe_path).is_file()
        assert Path(shot.clip_path).is_file()
        assert Path(shot.voice_path).is_file()
        assert shot.seed != 0
        assert shot.attempts == 1
    request = compose_calls[0]
    assert [path.name for path in request.clips] == ["shot_001.mp4", "shot_002.mp4", "shot_003.mp4"]
    assert [path.name for path in request.voices] == ["voice_001.wav", "voice_002.wav", "voice_003.wav"]
    assert request.out_path == tmp_path / "work" / "e1" / "final.mp4"


def test_run_episode_retries_failed_shot_with_a_new_seed(harness):
    build, store, _, _ = harness
    images = FlakyImages(prompts_that_fail={"测试画面2"}, failures=1)

    record = build(images=images).run_episode("e1")

    assert record.status == "done"
    assert store.get_shots("e1")[1].status == "voiced"
    assert len(images.seeds) == 4
    assert images.seeds[2] - images.seeds[1] == 1


def test_run_episode_marks_failed_shot_and_continues_with_the_rest(harness):
    build, store, compose_calls, _ = harness
    images = FlakyImages(prompts_that_fail={"测试画面2"}, failures=99)

    record = build(images=images).run_episode("e1")

    assert record.status == "failed"
    assert record.error == "这些镜头生成失败：[2]"
    assert [shot.status for shot in store.get_shots("e1")] == ["voiced", "failed", "voiced"]
    assert "重试 3 次仍失败" in store.get_shots("e1")[1].error
    assert compose_calls == []


def test_run_episode_reports_compose_failure(harness):
    build, _, _, _ = harness

    def broken_compose(request):
        raise RuntimeError("磁盘已满")

    record = build(compose_fn=broken_compose).run_episode("e1")

    assert record.status == "failed"
    assert "磁盘已满" in record.error


def test_run_episode_refuses_episode_without_script(tmp_path):
    store = Store(tmp_path / "pipeline.db")
    store.create_episode("青丘山的九尾狐", "e9")
    runner = PipelineRunner(
        store=store,
        images=FakeImageGenerator(),
        videos=None,
        voice=None,
        compose_fn=None,
        work_dir=tmp_path,
        deliver_dir=tmp_path,
    )

    record = runner.run_episode("e9")

    assert record.status == "failed"
    assert "还没有分镜脚本" in record.error


def test_run_episode_uses_the_same_seeds_for_the_same_episode_id(harness):
    build, store, _, tmp_path = harness
    first = build()
    first.run_episode("e1")
    seeds_before = [shot.seed for shot in store.get_shots("e1")]

    other_store = Store(tmp_path / "second.db")
    other_store.create_episode("青丘山的九尾狐", "e1")
    other_store.save_script("e1", fake_episode("青丘山的九尾狐", "e1", 3))
    second = PipelineRunner(
        store=other_store,
        images=FakeImageGenerator(),
        videos=first.videos,
        voice=FakeTtsBackend(),
        compose_fn=first.compose_fn,
        work_dir=tmp_path / "work-second",
        deliver_dir=tmp_path / "deliver-second",
    )
    second.run_episode("e1")

    assert [shot.seed for shot in other_store.get_shots("e1")] == seeds_before
