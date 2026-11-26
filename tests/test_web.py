import threading
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from pipeline.compose import compose
from pipeline.fakes import FakeImageGenerator, FakeTtsBackend, FakeVideoGenerator, fake_episode
from pipeline.runner import PipelineRunner
from pipeline.store import Store
from pipeline.web import create_app


def wait_until_finished(client, episode_id, timeout=120):
    """轮询直到这条视频离开渲染中的状态。

    @param client: 测试用的接口客户端
    @param episode_id: 视频编号
    @param timeout: 最长等待秒数
    @return: 这条视频最后一份状态
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/episodes/{episode_id}").json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(0.2)
    raise AssertionError(f"等待 {episode_id} 超时，最后的状态是 {data}")


def test_submission_runs_to_done_and_serves_video(tmp_path, ffmpeg):
    store = Store(tmp_path / "pipeline.db")

    def submit(episode_id, topic, shot_count):
        runner = PipelineRunner(
            store=store,
            images=FakeImageGenerator(),
            videos=FakeVideoGenerator(ffmpeg),
            voice=FakeTtsBackend(),
            compose_fn=lambda request: compose(request.clips, request.voices, request.out_path, ffmpeg, width=128, height=224),
            work_dir=tmp_path / "work",
            deliver_dir=tmp_path / "deliver",
        )
        runner.store.save_script(episode_id, fake_episode(topic, episode_id, shot_count))
        runner.run_episode(episode_id)

    app = create_app(store, tmp_path / "work", submit)
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "AI 视频管线" in page.text

        created = client.post("/api/episodes", json={"topic": "青丘山的九尾狐", "shot_count": 2})
        assert created.status_code == 202
        episode_id = created.json()["episode_id"]

        data = wait_until_finished(client, episode_id)

        assert data["status"] == "done", data
        assert data["topic"] == "青丘山的九尾狐"
        assert [shot["status"] for shot in data["shots"]] == ["voiced", "voiced"]
        assert [record["episode_id"] for record in client.get("/api/episodes").json()] == [episode_id]

        video = client.get(f"/api/episodes/{episode_id}/video")
        assert video.status_code == 200
        assert video.headers["content-type"].startswith("video/mp4")
        assert b"ftyp" in video.content[:16]


def test_blank_topic_is_rejected(tmp_path):
    app = create_app(Store(tmp_path / "pipeline.db"), tmp_path / "work", lambda *args: None)
    with TestClient(app) as client:
        response = client.post("/api/episodes", json={"topic": "   "})

        assert response.status_code == 400


def test_second_submission_is_rejected_while_pipeline_is_busy(tmp_path):
    started = threading.Event()
    release = threading.Event()

    def submit(episode_id, topic, shot_count):
        started.set()
        release.wait(timeout=10)

    app = create_app(Store(tmp_path / "pipeline.db"), tmp_path / "work", submit)
    with TestClient(app) as client:
        assert client.post("/api/episodes", json={"topic": "青丘山的九尾狐"}).status_code == 202
        assert started.wait(timeout=5)

        busy = client.post("/api/episodes", json={"topic": "烛龙"})

        assert busy.status_code == 409
        release.set()


def test_background_failure_is_recorded_as_failed_status(tmp_path):
    store = Store(tmp_path / "pipeline.db")

    def submit(episode_id, topic, shot_count):
        raise RuntimeError("后台出了意外")

    app = create_app(store, tmp_path / "work", submit)
    with TestClient(app) as client:
        episode_id = client.post("/api/episodes", json={"topic": "青丘山的九尾狐"}).json()["episode_id"]

        data = wait_until_finished(client, episode_id)

        assert data["status"] == "failed"
        assert "后台出了意外" in data["error"]


def test_unknown_episode_and_missing_video_return_404(tmp_path):
    app = create_app(Store(tmp_path / "pipeline.db"), tmp_path / "work", lambda *args: None)
    with TestClient(app) as client:
        assert client.get("/api/episodes/20261125-143005-a1b2").status_code == 404
        assert client.get("/api/episodes/not-an-id").status_code == 404
        assert client.get("/api/episodes/20261125-143005-a1b2/video").status_code == 404


def test_lock_is_released_when_the_record_cannot_be_created(tmp_path):
    store = Store(tmp_path / "pipeline.db")
    app = create_app(store, tmp_path / "work", lambda *args: None)
    with TestClient(app) as client:
        with patch.object(store, "create_episode", side_effect=RuntimeError("数据库只读")):
            failed = client.post("/api/episodes", json={"topic": "青丘山的九尾狐"})

        assert failed.status_code == 500
        assert "提交失败" in failed.json()["detail"]

        # 记录没建成时锁必须已经还回去，下一次提交不能被误判成"管线正忙"
        assert client.post("/api/episodes", json={"topic": "青丘山的九尾狐"}).status_code == 202
