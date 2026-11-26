from pathlib import Path

from pipeline.config import Settings


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("COMFYUI_URL", "http://192.168.1.10:8188")
    monkeypatch.setenv("DELIVER_DIR", "D:/Sync/AiPipeline")
    monkeypatch.setenv("VIDEO_ENGINE", "minimax")

    settings = Settings(_env_file=None)

    assert settings.deepseek_api_key == "sk-test"
    assert settings.comfyui_url == "http://192.168.1.10:8188"
    assert settings.deliver_dir == Path("D:/Sync/AiPipeline")
    assert settings.video_engine == "minimax"


def test_settings_have_production_defaults(monkeypatch):
    for name in ("SHOT_COUNT", "I2V_FRAMES", "KEYFRAME_WIDTH", "KEYFRAME_HEIGHT"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.shot_count == 24
    assert settings.i2v_frames == 121
    assert (settings.keyframe_width, settings.keyframe_height) == (704, 1280)
