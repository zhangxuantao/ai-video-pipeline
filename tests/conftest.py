import pytest


@pytest.fixture
def ffmpeg():
    """返回一个可用的 ffmpeg 封装，供需要真实编码的测试使用。"""
    from pipeline.ffmpeg import FFmpeg

    return FFmpeg.resolve()
