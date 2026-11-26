"""管线配置：全部来自环境变量或 .env 文件。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

VIDEO_ENGINES = ("wan", "minimax")


class Settings(BaseSettings):
    """管线配置，字段与 .env 中同名的全大写变量一一对应。

    @author zxt
    @date 2026-11-25
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    comfyui_url: str = "http://127.0.0.1:8188"
    data_dir: Path = Path("data")
    workflows_dir: Path = Path("workflows")
    deliver_dir: Path = Path("data/deliver")
    ffmpeg_path: str = ""
    hf_endpoint: str = "https://hf-mirror.com"
    tts_voice: str = "zm_yunjian"
    shot_count: int = 24
    style_guide: str = ""
    prompt_language: str = "中文"
    keyframe_negative_prompt: str = ""
    keyframe_width: int = 704
    keyframe_height: int = 1280
    i2v_negative_prompt: str = ""
    i2v_width: int = 720
    i2v_height: int = 1280
    i2v_frames: int = 121
    video_engine: str = "wan"
