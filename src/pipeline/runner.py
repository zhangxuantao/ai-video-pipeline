"""流程编排：按阶段推进一条视频，并持续把进度写进状态库。"""

import logging
import random
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pipeline.episode import episode_from_json
from pipeline.generators import ImageGenerator, VideoGenerator
from pipeline.store import EpisodeRecord, ShotRecord, Store
from pipeline.tts import TtsBackend

logger = logging.getLogger(__name__)

Step = Callable[[ShotRecord, int], Path]


@dataclass(frozen=True)
class ComposeRequest:
    """交给合成函数的一组素材。

    @author zxt
    @date 2026-11-25
    """

    clips: list[Path]
    voices: list[Path]
    out_path: Path


class PipelineRunner:
    """一条视频的完整流程：关键帧、镜头、配音、合成、交付。

    每个阶段先对所有镜头跑完再进入下一阶段，这样一条视频只需要切换两次模型。
    单个镜头失败不影响其余镜头，最后统一汇报失败的是哪几镜。

    @author zxt
    @date 2026-11-25
    """

    def __init__(
        self,
        store: Store,
        images: ImageGenerator,
        videos: VideoGenerator,
        voice: TtsBackend,
        compose_fn: Callable[[ComposeRequest], Path],
        work_dir: Path,
        deliver_dir: Path,
        max_attempts: int = 3,
    ):
        """
        @param store: 状态库
        @param images: 关键帧生成器
        @param videos: 镜头生成器
        @param voice: 配音后端
        @param compose_fn: 合成函数
        @param work_dir: 工作目录，每条视频一个子目录
        @param deliver_dir: 成片的交付目录
        @param max_attempts: 单个镜头的最大尝试次数，每次换一个随机种子
        """
        self.store = store
        self.videos = videos
        self.compose_fn = compose_fn
        self._images = images
        self._voice = voice
        self._work_dir = work_dir
        self._deliver_dir = deliver_dir
        self._max_attempts = max_attempts

    def run_episode(self, episode_id: str) -> EpisodeRecord:
        """跑完一条视频的全流程。任何失败都会落成 failed 状态并写明原因，不向外抛业务异常。

        @param episode_id: 视频编号
        @return: 这条视频的最新状态
        """
        try:
            return self._run(episode_id)
        except Exception as exc:
            logger.exception("视频 %s 失败", episode_id)
            self.store.set_episode_status(episode_id, "failed", error=str(exc)[:1000])
            return self.store.get_episode(episode_id)

    def _run(self, episode_id: str) -> EpisodeRecord:
        """
        @param episode_id: 视频编号
        @return: 这条视频的最新状态
        """
        episode = self.store.get_episode(episode_id)
        if not episode.spec_json:
            raise RuntimeError(f"视频 {episode_id} 还没有分镜脚本")
        episode_from_json(episode.spec_json)
        work = self._work_dir / episode_id
        seed_root = random.Random(episode_id).randrange(1, 1_000_000)
        self.store.set_episode_status(episode_id, "rendering")

        self._run_stage(episode_id, "pending", self._keyframe_step(work), "keyframed", "keyframe_path", seed_root)
        self._run_stage(episode_id, "keyframed", self._video_step(work), "video_done", "clip_path", seed_root)
        self._run_stage(episode_id, "video_done", self._voice_step(work), "voiced", "voice_path", seed_root)

        shots = self.store.get_shots(episode_id)
        failed = [shot.shot_no for shot in shots if shot.status == "failed"]
        if failed:
            self.store.set_episode_status(episode_id, "failed", error=f"这些镜头生成失败：{failed}")
            return self.store.get_episode(episode_id)

        final = work / "final.mp4"
        self.compose_fn(
            ComposeRequest(
                clips=[Path(shot.clip_path) for shot in shots],
                voices=[Path(shot.voice_path) for shot in shots],
                out_path=final,
            )
        )
        self._deliver_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(final, self._deliver_dir / f"{episode_id}.mp4")
        self.store.set_episode_status(episode_id, "done")
        return self.store.get_episode(episode_id)

    def _run_stage(
        self,
        episode_id: str,
        start_status: str,
        step: Step,
        done_status: str,
        path_field: str,
        seed_root: int,
    ) -> None:
        """对一个阶段里的所有镜头依次执行 step，单镜失败不影响其余镜头。

        @param episode_id: 视频编号
        @param start_status: 只有处于这个状态的镜头才处理
        @param step: 对单个镜头执行一步，第二个参数是随机种子，返回产物路径
        @param done_status: 成功后写入的状态
        @param path_field: 成功后写入产物路径的列
        @param seed_root: 这条视频的种子基数
        """
        for shot in self.store.get_shots(episode_id):
            if shot.status != start_status:
                continue
            last_error: Exception | None = None
            started = time.perf_counter()
            for attempt in range(1, self._max_attempts + 1):
                seed = seed_root + shot.shot_no * 100 + attempt - 1
                try:
                    path = step(shot, seed)
                except Exception as exc:
                    last_error = exc
                    self.store.update_shot(episode_id, shot.shot_no, attempts=attempt, error=str(exc)[:500])
                    continue
                self.store.update_shot(
                    episode_id,
                    shot.shot_no,
                    status=done_status,
                    **{path_field: str(path), "seed": seed, "attempts": attempt, "error": ""},
                )
                logger.info(
                    "视频 %s 第 %d 镜 %s 完成，第 %d 次尝试，用时 %.1f 秒",
                    episode_id,
                    shot.shot_no,
                    done_status,
                    attempt,
                    time.perf_counter() - started,
                )
                break
            else:
                error = f"重试 {self._max_attempts} 次仍失败，最后一次：{last_error}"
                self.store.update_shot(episode_id, shot.shot_no, status="failed", error=error)
                logger.error("视频 %s 第 %d 镜 %s", episode_id, shot.shot_no, error)

    def _keyframe_step(self, work: Path) -> Step:
        """
        @param work: 这条视频的工作目录
        @return: 关键帧阶段对单镜执行的函数
        """

        def step(shot: ShotRecord, seed: int) -> Path:
            return self._images.generate_image(shot.image_prompt, seed, work / "keyframes", f"keyframe_{shot.shot_no:03d}")

        return step

    def _video_step(self, work: Path) -> Step:
        """
        @param work: 这条视频的工作目录
        @return: 镜头阶段对单镜执行的函数
        """

        def step(shot: ShotRecord, seed: int) -> Path:
            return self.videos.generate_video(
                Path(shot.keyframe_path), shot.motion_prompt, seed, work / "clips", f"shot_{shot.shot_no:03d}"
            )

        return step

    def _voice_step(self, work: Path) -> Step:
        """
        @param work: 这条视频的工作目录
        @return: 配音阶段对单镜执行的函数
        """

        def step(shot: ShotRecord, _seed: int) -> Path:
            return self._voice.synthesize(shot.narration, work / "voices", f"voice_{shot.shot_no:03d}")

        return step
