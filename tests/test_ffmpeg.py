import pytest

from pipeline.fakes import FakeVideoGenerator
from pipeline.ffmpeg import FFmpeg, MediaError


def test_resolve_returns_a_usable_executable():
    assert FFmpeg.resolve().run(["-version"])


def test_resolve_rejects_missing_configured_path():
    with pytest.raises(MediaError, match="ffmpeg 路径不存在"):
        FFmpeg.resolve("Z:/no/such/ffmpeg.exe")


def test_run_reports_failed_command(ffmpeg, tmp_path):
    with pytest.raises(MediaError, match="ffmpeg 失败"):
        ffmpeg.run(["-loglevel", "error", "-i", str(tmp_path / "missing.mp4"), "-f", "null", "-"])


def test_duration_reads_seconds(ffmpeg, tmp_path):
    clip = FakeVideoGenerator(ffmpeg, seconds=3).generate_video(tmp_path / "none.png", "运镜", 1, tmp_path, "shot_001")

    assert abs(ffmpeg.duration(clip) - 3.0) < 0.1
