"""本机操作页的接口：提交主题、查看进度、看成片。"""

import re
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline.episode import new_episode_id
from pipeline.store import EpisodeRecord, Store, StoreError

TEMPLATE = Path(__file__).parent / "templates" / "index.html"
EPISODE_ID_PATTERN = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")


class TopicRequest(BaseModel):
    """提交一条视频的请求。

    @author zxt
    @date 2026-11-25
    """

    topic: str
    shot_count: int = 0


def _episode_payload(store: Store, record: EpisodeRecord) -> dict:
    """把一条视频的状态整理成接口返回的字典。

    @param store: 状态库
    @param record: 视频记录
    @return: 含状态和各镜头进度的字典
    """
    shots = store.get_shots(record.episode_id)
    return {
        "episode_id": record.episode_id,
        "topic": record.topic,
        "status": record.status,
        "error": record.error,
        "shots": [{"shot_no": shot.shot_no, "status": shot.status, "error": shot.error} for shot in shots],
    }


def create_app(store: Store, work_dir: Path, submit: Callable[[str, str, int], None]) -> FastAPI:
    """创建 Web 应用。

    @param store: 状态库
    @param work_dir: 工作目录，成片在其中的 <视频编号>/final.mp4
    @param submit: 后台回调，参数为（视频编号, 主题, 镜头数），负责写脚本并跑完整流程
    @return: FastAPI 应用
    """
    app = FastAPI()
    worker_lock = threading.Lock()

    @app.get("/")
    def index() -> FileResponse:
        """返回操作页面。"""
        return FileResponse(TEMPLATE, media_type="text/html")

    @app.get("/api/episodes")
    def list_episodes() -> list[dict]:
        """
        @return: 全部视频的状态，新创建的排在前面
        """
        return [_episode_payload(store, record) for record in store.list_episodes()]

    @app.post("/api/episodes", status_code=202)
    def create_episode(request: TopicRequest) -> dict:
        """创建一条视频并交给后台线程去跑；同一时间只允许一条在跑。

        @param request: 主题和镜头数
        @return: 新视频的编号
        """
        topic = request.topic.strip()
        if not topic:
            raise HTTPException(status_code=400, detail="主题不能为空")
        if request.shot_count < 0:
            raise HTTPException(status_code=400, detail="镜头数不能是负数")
        # 非阻塞抢锁：抢不到说明上一条视频还在跑，显卡只有一块，不能并行
        if not worker_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="管线正忙，等当前这条跑完再提交")
        try:
            episode_id = new_episode_id()
            store.create_episode(topic, episode_id)
        except Exception as exc:
            # 记录没建成时后台线程不会启动，锁只能在这里还回去，否则之后的提交一直被拒
            worker_lock.release()
            raise HTTPException(status_code=500, detail=f"提交失败：{exc}") from exc

        def run_in_background() -> None:
            """在后台线程里跑完这条视频，无论成败都把锁还回去。"""
            try:
                submit(episode_id, topic, request.shot_count)
            except Exception as exc:
                store.set_episode_status(episode_id, "failed", error=str(exc)[:1000])
            finally:
                worker_lock.release()

        try:
            threading.Thread(target=run_in_background, daemon=True).start()
        except Exception as exc:
            worker_lock.release()
            store.set_episode_status(episode_id, "failed", error=f"后台线程启动失败：{exc}")
            raise HTTPException(status_code=500, detail=f"提交失败：{exc}") from exc
        return {"episode_id": episode_id}

    @app.get("/api/episodes/{episode_id}")
    def get_episode(episode_id: str) -> dict:
        """
        @param episode_id: 视频编号
        @return: 这条视频的状态
        """
        if not EPISODE_ID_PATTERN.fullmatch(episode_id):
            raise HTTPException(status_code=404, detail="视频编号格式不对")
        try:
            return _episode_payload(store, store.get_episode(episode_id))
        except StoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/episodes/{episode_id}/video")
    def get_video(episode_id: str) -> FileResponse:
        """
        @param episode_id: 视频编号
        @return: 成片文件
        """
        # 先校验编号格式，防止用路径片段拼出工作目录之外的文件
        if not EPISODE_ID_PATTERN.fullmatch(episode_id):
            raise HTTPException(status_code=404, detail="视频编号格式不对")
        video = work_dir / episode_id / "final.mp4"
        if not video.is_file():
            raise HTTPException(status_code=404, detail="这条视频还没有成片")
        return FileResponse(video, media_type="video/mp4")

    return app
