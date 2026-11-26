"""合成阶段：把镜头和旁白拼成一条成片，每镜严格对齐到固定秒数。"""

from pathlib import Path

from pipeline.episode import SHOT_SECONDS
from pipeline.ffmpeg import FFmpeg

AUDIO_SAMPLE_RATE = 44100


def build_command(
    clips: list[Path],
    voices: list[Path],
    out_path: Path,
    shot_seconds: float,
    fps: int,
    width: int,
    height: int,
) -> list[str]:
    """生成 ffmpeg 的参数列表。

    每个镜头先统一帧率和尺寸，再裁到固定秒数；不足的部分用最后一帧补齐。旁白同理，不足的部分补静音。

    @param clips: 镜头片段，按播放顺序
    @param voices: 旁白音频，与 clips 一一对应
    @param out_path: 成片输出路径
    @param shot_seconds: 每镜的固定秒数
    @param fps: 成片帧率
    @param width: 成片宽度，必须是偶数
    @param height: 成片高度，必须是偶数
    @return: ffmpeg 参数列表，不含可执行文件名
    """
    if width % 2 or height % 2:
        raise ValueError("成片的宽和高必须是偶数")
    count = len(clips)
    inputs: list[str] = []
    for clip in clips:
        inputs += ["-i", str(clip)]
    for voice in voices:
        inputs += ["-i", str(voice)]
    filters: list[str] = []
    for index in range(count):
        filters.append(
            f"[{index}:v]fps={fps},scale={width}:{height},format=yuv420p,"
            f"tpad=stop_mode=clone:stop_duration={shot_seconds},"
            f"trim=duration={shot_seconds},setpts=PTS-STARTPTS[v{index}]"
        )
    for index in range(count):
        filters.append(
            f"[{count + index}:a]aresample={AUDIO_SAMPLE_RATE},aformat=channel_layouts=stereo,"
            f"apad=whole_dur={shot_seconds},atrim=duration={shot_seconds},asetpts=PTS-STARTPTS[a{index}]"
        )
    video_labels = "".join(f"[v{index}]" for index in range(count))
    audio_labels = "".join(f"[a{index}]" for index in range(count))
    filters.append(f"{video_labels}concat=n={count}:v=1:a=0[vout]")
    filters.append(f"{audio_labels}concat=n={count}:v=0:a=1[aout]")
    return [
        "-loglevel", "error",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(out_path),
    ]


def compose(
    clips: list[Path],
    voices: list[Path],
    out_path: Path,
    ffmpeg: FFmpeg,
    shot_seconds: float = SHOT_SECONDS,
    fps: int = 24,
    width: int = 720,
    height: int = 1280,
) -> Path:
    """把镜头列表和旁白列表合成为一条成片。

    @param clips: 镜头片段，按播放顺序
    @param voices: 旁白音频，与 clips 一一对应
    @param out_path: 成片输出路径
    @param ffmpeg: 命令行封装
    @param shot_seconds: 每镜的固定秒数
    @param fps: 成片帧率
    @param width: 成片宽度
    @param height: 成片高度
    @return: 成片路径
    """
    if len(clips) != len(voices):
        raise ValueError(f"镜头有 {len(clips)} 个，旁白有 {len(voices)} 段，数量必须一致")
    if not clips:
        raise ValueError("没有镜头可以合成")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(build_command(clips, voices, out_path, shot_seconds, fps, width, height))
    return out_path
