"""ffmpeg 命令行封装：定位可执行文件、执行命令、读取媒体时长。"""

import re
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

DURATION_PATTERN = re.compile(r"Duration: (\d+):(\d+):(\d+\.\d+)")


class MediaError(RuntimeError):
    """ffmpeg 执行失败，或读不到需要的信息。

    @author zxt
    @date 2026-11-25
    """


class FFmpeg:
    """ffmpeg 命令行封装。

    @author zxt
    @date 2026-11-25
    """

    def __init__(self, exe: str, timeout: float = 1800.0):
        """
        @param exe: ffmpeg 可执行文件路径
        @param timeout: 单条命令的默认超时秒数
        """
        self._exe = exe
        self._timeout = timeout

    @classmethod
    def resolve(cls, configured: str = "") -> "FFmpeg":
        """定位 ffmpeg：优先用配置里指定的路径，其次是 PATH 上的，最后退到 pip 包自带的。

        @param configured: 配置里指定的路径，空串表示没有指定
        @return: 可用的 FFmpeg 实例
        """
        if configured:
            if not Path(configured).is_file():
                raise MediaError(f"配置的 ffmpeg 路径不存在：{configured}")
            return cls(configured)
        return cls(shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe())

    def run(self, args: list[str], timeout: float | None = None) -> str:
        """执行一条 ffmpeg 命令。

        @param args: ffmpeg 的参数列表，不含可执行文件名
        @param timeout: 超时秒数，默认取构造时的值
        @return: ffmpeg 的标准输出和标准错误合并后的内容；媒体信息打在标准错误，版本信息打在标准输出
        """
        result = subprocess.run(
            [self._exe, "-hide_banner", "-y", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or self._timeout,
        )
        if result.returncode != 0:
            raise MediaError(f"ffmpeg 失败（退出码 {result.returncode}）：{result.stderr.strip()[-800:]}")
        return result.stdout + result.stderr

    def duration(self, media: Path) -> float:
        """读取媒体文件的时长。

        @param media: 媒体文件路径
        @return: 时长，单位秒
        """
        stderr = self.run(["-loglevel", "info", "-i", str(media), "-map", "0", "-f", "null", "-"])
        match = DURATION_PATTERN.search(stderr)
        if not match:
            raise MediaError(f"读不到时长：{media}")
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
