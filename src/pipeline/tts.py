"""配音阶段：把旁白文本合成为 WAV。"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf

KOKORO_SAMPLE_RATE = 24000


class TtsBackend(Protocol):
    """配音后端的接口约定。

    @author zxt
    @date 2026-11-25
    """

    def synthesize(self, text: str, dest_dir: Path, name: str) -> Path:
        """
        @param text: 旁白文本
        @param dest_dir: 输出目录
        @param name: 输出文件名，不带扩展名
        @return: 生成的音频路径
        """
        ...


class TtsError(RuntimeError):
    """配音合成失败。

    @author zxt
    @date 2026-11-25
    """


class KokoroTtsBackend:
    """用 Kokoro 在本机合成中文旁白；它很小，跑在 CPU 上，不和视频模型抢显存。

    @author zxt
    @date 2026-11-25
    """

    def __init__(
        self,
        voice: str = "zm_yunjian",
        speed: float = 1.0,
        hf_endpoint: str = "https://hf-mirror.com",
        pipeline_factory: Callable[[], object] | None = None,
    ):
        """
        @param voice: 音色名
        @param speed: 语速
        @param hf_endpoint: 模型下载地址，国内用镜像
        @param pipeline_factory: 创建 Kokoro 流水线的函数，默认真实创建；测试时注入替身
        """
        self._voice = voice
        self._speed = speed
        self._hf_endpoint = hf_endpoint
        self._pipeline_factory = pipeline_factory or self._build_pipeline
        self._pipeline: object | None = None

    def synthesize(self, text: str, dest_dir: Path, name: str) -> Path:
        """合成一段旁白。Kokoro 会按句子把文本切块，这里把各块首尾相接成一个文件。

        @param text: 旁白文本
        @param dest_dir: 输出目录
        @param name: 输出文件名，不带扩展名
        @return: 生成的音频路径
        """
        if self._pipeline is None:
            self._pipeline = self._pipeline_factory()
        chunks = [chunk[2] for chunk in self._pipeline(text, voice=self._voice, speed=self._speed)]
        if not chunks:
            raise TtsError(f"没有合成出任何音频：{text}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{name}.wav"
        sf.write(str(path), np.concatenate(chunks), KOKORO_SAMPLE_RATE)
        return path

    def _build_pipeline(self) -> object:
        """
        @return: Kokoro 的中文流水线
        """
        os.environ.setdefault("HF_ENDPOINT", self._hf_endpoint)
        # 延迟导入：kokoro 会拉起 torch，不需要配音的场景不必加载
        from kokoro import KPipeline

        return KPipeline(lang_code="z")
