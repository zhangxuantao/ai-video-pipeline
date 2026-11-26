"""不依赖显卡和 ComfyUI 的替身实现，供单元测试和 --fakes 冒烟运行使用。"""

import array
import math
import wave
from pathlib import Path

from PIL import Image

from pipeline.episode import Episode, Shot
from pipeline.ffmpeg import FFmpeg

FAKE_MOTION_PROMPT = "镜头缓慢推近"


def fake_episode(topic: str, episode_id: str, shot_count: int) -> Episode:
    """生成一条内容固定、格式合法的分镜脚本。

    @param topic: 视频主题
    @param episode_id: 视频编号
    @param shot_count: 镜头数
    @return: 可直接使用的 Episode
    """
    shots = [
        Shot(
            shot_no=number,
            narration=f"第{number}镜的测试旁白",
            image_prompt=f"测试画面{number}",
            motion_prompt=FAKE_MOTION_PROMPT,
        )
        for number in range(1, shot_count + 1)
    ]
    return Episode(episode_id=episode_id, title=f"测试片：{topic}", topic=topic, shots=shots)


class FakeImageGenerator:
    """生成纯色 PNG 的关键帧替身。

    @author zxt
    @date 2026-11-25
    """

    def __init__(self, color: tuple[int, int, int] = (120, 80, 200), size: tuple[int, int] = (64, 64)):
        """
        @param color: 画面颜色
        @param size: 画面宽高
        """
        self._color = color
        self._size = size

    def generate_image(self, prompt: str, seed: int, dest_dir: Path, name: str) -> Path:
        """
        @param prompt: 画面描述，替身不使用
        @param seed: 随机种子，替身不使用
        @param dest_dir: 输出目录
        @param name: 输出文件名，不带扩展名
        @return: 生成的图片路径
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{name}.png"
        Image.new("RGB", self._size, self._color).save(path)
        return path


class FakeVideoGenerator:
    """用 ffmpeg 生成纯色视频的镜头替身；秒数可以故意给错，用来验证补帧和裁切逻辑。

    @author zxt
    @date 2026-11-25
    """

    def __init__(self, ffmpeg: FFmpeg, seconds: float = 5.0, color: str = "gray", size: tuple[int, int] = (270, 480)):
        """
        @param ffmpeg: 命令行封装
        @param seconds: 视频秒数
        @param color: 画面颜色
        @param size: 画面宽高
        """
        self._ffmpeg = ffmpeg
        self._seconds = seconds
        self._color = color
        self._size = size

    def generate_video(self, start_image: Path, prompt: str, seed: int, dest_dir: Path, name: str) -> Path:
        """
        @param start_image: 首帧图片，替身不使用
        @param prompt: 运镜描述，替身不使用
        @param seed: 随机种子，替身不使用
        @param dest_dir: 输出目录
        @param name: 输出文件名，不带扩展名
        @return: 生成的视频片段路径
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{name}.mp4"
        width, height = self._size
        self._ffmpeg.run([
            "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={self._color}:s={width}x{height}:r=24:d={self._seconds}",
            "-r", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ])
        return path


class FakeTtsBackend:
    """生成正弦波 WAV 的配音替身；秒数可以故意给短，用来验证音频补齐逻辑。

    @author zxt
    @date 2026-11-25
    """

    def __init__(self, seconds: float = 5.0, sample_rate: int = 24000, frequency: float = 440.0):
        """
        @param seconds: 音频秒数
        @param sample_rate: 采样率
        @param frequency: 正弦波频率
        """
        self._seconds = seconds
        self._sample_rate = sample_rate
        self._frequency = frequency

    def synthesize(self, text: str, dest_dir: Path, name: str) -> Path:
        """
        @param text: 旁白文本，替身不使用
        @param dest_dir: 输出目录
        @param name: 输出文件名，不带扩展名
        @return: 生成的音频路径
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        count = int(self._seconds * self._sample_rate)
        samples = array.array(
            "h",
            (
                int(8000 * math.sin(2 * math.pi * self._frequency * index / self._sample_rate))
                for index in range(count)
            ),
        )
        path = dest_dir / f"{name}.wav"
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(self._sample_rate)
            audio.writeframes(samples.tobytes())
        return path
