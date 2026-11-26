# AI 视频管线 里程碑 1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付里程碑 1 的最小端到端管线：给一个主题，无人值守产出一条带旁白的成片（2 个镜头、10 秒），并能在家里电脑上接真实的 DeepSeek、ComfyUI、本地配音跑通。

**Architecture:** 一条视频是一个 Episode，按"脚本 → 关键帧 → 镜头 → 配音 → 合成 → 交付"顺序推进，每个阶段先对所有镜头跑完再进入下一阶段。ComfyUI 通过 HTTP 对接，工作流用"API 格式模板 + 参数绑定表"描述，不在代码里写节点编号。所有外部依赖（生图、生视频、配音、合成）都藏在接口后面，测试和 `--fakes` 冒烟用替身，不需要显卡。

**Tech Stack:** Python 3.12、uv、httpx、pydantic-settings、FastAPI、ffmpeg（pip 包 imageio-ffmpeg 自带，不用单独安装）、Kokoro（中文配音）、pytest。依赖在 pyproject.toml 里声明，`uv sync` 安装和管理 `.venv`，`uv.lock` 进版本库。

**Spec:** docs/superpowers/specs/2026-11-25-ai-video-pipeline-design.md

## Global Constraints

- 每镜固定 5 秒，旁白每镜不超过 20 字（标点计入，空白不计）。
- 按阶段批量：先出全部关键帧，再出全部镜头，再配音，最后合成。
- 发布永远手动，管线不接任何平台的发布接口。
- ComfyUI 和管线服务只监听本机地址，不对外暴露。
- 模型权重、素材、成片、`.env` 不进仓库。
- 全程中文：文档、注释、报错信息。
- 注释规范（来自项目的 agents.local.md）：每个新建类写一段含 `@author zxt` 和 `@date 2026-11-25` 的说明；每个新增函数或方法写说明，有参数的逐个写 `@param 参数名: 说明`，有返回值的写 `@return: 说明`；测试函数本身不写注释。
- 环境与命令（来自项目的 agents.local.md，2026-11-25 修订版）：新建的 Python 项目用 uv 管理；依赖声明在 pyproject.toml 的 `[project]` 和 `[dependency-groups]` 里；`uv sync` 安装（会管理项目根目录的 `.venv`，必要时自动下载 Python）；命令一律写 `uv run ...`；镜像在 pyproject 的 `[[tool.uv.index]]` 里配成阿里云；`uv.lock` 进版本库；禁止装到全局环境；Python 固定 3.12。
- 计划里的所有命令都在仓库根目录、以 `uv run ...` 的形式执行。
- 测试统一用 pytest，不直接执行测试文件，也不手工拼 sys.path。验证时安静地跑，通过了就直接交付，只有失败才输出错误日志。
- 提交纪律（来自用户的全局约定，覆盖本技能模板里"每个任务提交一次"的做法）：整个计划只在最后一个任务提交一次，之前任何任务都不执行 `git add` 和 `git commit`。设计文档和实施计划各有一次单独的提交，不属于本计划的实施提交。
- 当前分支是 `feature/ai-video-pipeline-20261125`，不要切换到 `main`。
- 单元测试默认不运行标记为 `integration` 的测试。
- 本计划只覆盖里程碑 1。以下内容留给里程碑 2 的计划，本计划不实现：多候选与自动评分、单镜重做、断点续跑、显存不足时降级重试、字幕配乐片头片尾、AI 显式标识、标题简介标签、管线服务开机自启。

---

## 文件结构

```
pyproject.toml                          项目定义、依赖声明、入口、uv 镜像、pytest 配置
uv.lock                                 依赖的实际版本，由 uv sync 生成，进版本库
.env.example                            配置样例
.gitignore                              追加模型、媒体、本地数据的忽略规则
src/pipeline/__init__.py
src/pipeline/config.py                  Settings：全部配置项
src/pipeline/episode.py                 Episode、Shot 数据契约与校验
src/pipeline/script.py                  DeepSeek 客户端与脚本阶段
src/pipeline/comfy.py                   工作流绑定、ComfyUI 客户端
src/pipeline/generators.py              文生图、图生视频生成器
src/pipeline/fakes.py                   替身实现，供测试和 --fakes 冒烟使用
src/pipeline/ffmpeg.py                  ffmpeg 命令行封装
src/pipeline/compose.py                 合成阶段
src/pipeline/tts.py                     配音后端
src/pipeline/store.py                   SQLite 状态库
src/pipeline/runner.py                  流程编排
src/pipeline/web.py                     本机网页的接口
src/pipeline/templates/index.html       本机网页
src/pipeline/__main__.py                命令行入口
workflows/README.md                     如何导出工作流并填写绑定表
workflows/keyframe.binding.example.json 文生图绑定表样例
workflows/wan_i2v.binding.example.json      Wan 的图生视频绑定表样例
workflows/minimax_i2v.binding.example.json  MiniMax 的图生视频绑定表样例
tests/conftest.py
tests/fixtures/workflows/*.json         合成的小工作流模板，专供测试
tests/test_*.py
```

---

### Task 1: 工程脚手架与配置

**Files:**
- Create: `pyproject.toml`
- Delete: `requirements.txt`（仓库里现有的是早期用 pip 方案时留下的，依赖全部并入 pyproject）
- Modify: `.gitignore`（在文件末尾追加）
- Create: `.env.example`
- Create: `src/pipeline/__init__.py`
- Create: `src/pipeline/config.py`
- Create: `tests/conftest.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `pipeline.config.Settings`，字段名见下方代码；后续所有任务通过它读取配置。
- Produces: pytest 夹具 `ffmpeg`，返回 `pipeline.ffmpeg.FFmpeg` 实例（Task 6 实现该类后才可用）。

- [ ] **Step 1: 写 pyproject.toml**

```toml
[project]
name = "ai-video-pipeline"
version = "0.1.0"
description = "依托 ComfyUI 的视频生成流水线"
readme = "README.md"
requires-python = ">=3.12,<3.13"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.8",
    "pydantic-settings>=2.4",
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "pillow>=10.4",
    "soundfile>=0.12",
    "numpy>=1.26",
    "imageio-ffmpeg>=0.5",
    "kokoro>=0.9.4",
    "misaki[zh]>=0.9.4",
]

[project.scripts]
pipeline = "pipeline.__main__:main"

[dependency-groups]
dev = ["pytest>=8.3"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pipeline"]

[[tool.uv.index]]
name = "aliyun"
url = "https://mirrors.aliyun.com/pypi/simple/"
default = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q -m 'not integration'"
markers = ["integration: 需要真实模型、显卡或 ComfyUI 的测试，默认不运行"]
```

`requires-python` 上限写成 `<3.13`，因为 kokoro 0.9.4 不支持 3.13。`misaki[zh]` 不能省：kokoro 自身只带英文前端，中文前端依赖的 cn2an、jieba、ordered-set、pypinyin、pypinyin-dict 都在这个附加项里。实际解析到的版本由 `uv sync` 记进 `uv.lock`，那个文件要提交，各机器的版本才一致。

- [ ] **Step 2: 删除 requirements.txt**

Run: `rm -f requirements.txt`
说明: 本项目改用 pyproject 声明依赖。文件不存在时这条命令不报错；如果仓库里还有这个文件，删掉，避免两份依赖声明打架。

- [ ] **Step 3: 在 .gitignore 末尾追加忽略规则**

```gitignore

# 本项目：模型权重、素材、成片、本地数据一律不进仓库
data/
models/
*.safetensors
*.ckpt
*.gguf
*.onnx
*.pth
*.mp4
*.webm
*.mov
*.wav
*.m4a
```

- [ ] **Step 4: 写 .env.example**

```
# 复制为 .env 并填入真实值；.env 已被 .gitignore 忽略
# 注意：.env 是按"当前目录"找的，命令必须在仓库根目录下运行，否则读不到这里的内容
DEEPSEEK_API_KEY=sk-替换为你的密钥
COMFYUI_URL=http://127.0.0.1:8188
# 生视频用哪个引擎的工作流：wan 或 minimax，对应文件是 workflows/<引擎>_i2v_api.json 和同名 .binding.json
# 临时切换不必改这里，直接在命令前加环境变量：VIDEO_ENGINE=minimax uv run pipeline run --topic "..."
VIDEO_ENGINE=wan
# 成片会复制到这个目录，建议设为网盘的同步目录
DELIVER_DIR=D:/Sync/AiPipeline
# 以下都是可选项，去掉行首的 # 并按需修改
# 配音音色；用 uv run pipeline tts-sample 试听，名字见 Kokoro 的 voices 目录
# TTS_VOICE=zm_yunjian
# 图生视频的帧数；只有绑定表里绑了 length 才会发出去。默认 121（约 5 秒/24 帧），要覆盖模板默认值时取消注释改成你要的数字
# I2V_FRAMES=121
# 关键帧的宽高，和视频保持同样的 9:16
# KEYFRAME_WIDTH=704
# KEYFRAME_HEIGHT=1280
# 视频的宽高；只有绑定表里绑了 width 和 height 才会发出去。默认 720x1280
# I2V_WIDTH=720
# I2V_HEIGHT=1280
# 负向提示词；模板里有负向词输入时才需要设置，留空会把模板里调好的负向词覆盖成空
# KEYFRAME_NEGATIVE_PROMPT=
# I2V_NEGATIVE_PROMPT=
# ffmpeg 的路径；不填时依次找 PATH 上的 ffmpeg 和 pip 包自带的那个。PATH 上的版本不完整时用它指回去
# FFMPEG_PATH=
```

- [ ] **Step 5: 写包入口 src/pipeline/__init__.py**

```python
"""依托 ComfyUI 的视频生成流水线。"""
```

- [ ] **Step 6: 写失败的测试 tests/test_config.py**

```python
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
```

- [ ] **Step 7: 写 tests/conftest.py**

导入放在夹具函数内部，这样在 Task 6 实现 `FFmpeg` 之前，其余测试文件不会因为加载这个文件而报错。

```python
import pytest


@pytest.fixture
def ffmpeg():
    """返回一个可用的 ffmpeg 封装，供需要真实编码的测试使用。"""
    from pipeline.ffmpeg import FFmpeg

    return FFmpeg.resolve()
```

- [ ] **Step 8: 安装依赖，并确认测试失败**

Run: `uv sync`
说明: uv 会创建或复用项目根目录的 `.venv`，按 pyproject 装好依赖（需要 Python 3.12 时自动下载），并生成 `uv.lock`。首次耗时几分钟，因为要下载 torch。如果卡在下载 Python，设置环境变量 `UV_PYTHON_INSTALL_MIRROR` 指向一个 GitHub 加速镜像后重试。

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.config'`。

- [ ] **Step 9: 写 src/pipeline/config.py**

```python
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
```

- [ ] **Step 10: 确认测试通过**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS，2 个用例。

---

### Task 2: 数据契约 Episode 与 Shot

**Files:**
- Create: `src/pipeline/episode.py`
- Test: `tests/test_episode.py`

**Interfaces:**
- Produces: 常量 `MAX_NARRATION_CHARS = 20`、`SHOT_SECONDS = 5.0`。
- Produces: 异常 `EpisodeValidationError(ValueError)`。
- Produces: 冻结数据类 `Shot(shot_no: int, narration: str, image_prompt: str, motion_prompt: str, duration_sec: float = 5.0)` 和 `Episode(episode_id: str, title: str, topic: str, shots: list[Shot])`。
- Produces: `count_chars(text: str) -> int`、`new_episode_id(now: datetime | None = None) -> str`、`validate_episode(episode: Episode) -> None`、`episode_from_payload(payload: dict, episode_id: str, topic: str) -> Episode`、`episode_to_dict(episode: Episode) -> dict`、`episode_to_json(episode: Episode) -> str`、`episode_from_json(text: str) -> Episode`。

- [ ] **Step 1: 写失败的测试 tests/test_episode.py**

```python
import pytest

from pipeline.episode import (
    Episode,
    EpisodeValidationError,
    Shot,
    count_chars,
    episode_from_json,
    episode_from_payload,
    episode_to_json,
    new_episode_id,
    validate_episode,
)


def make_episode(narrations=("东海之外有座青丘山", "山中藏着一只九尾狐")) -> Episode:
    """用给定的旁白列表造一条合法的视频。"""
    shots = [
        Shot(shot_no=index, narration=text, image_prompt="画面", motion_prompt="推近")
        for index, text in enumerate(narrations, start=1)
    ]
    return Episode(episode_id="e1", title="青丘九尾狐", topic="青丘山的九尾狐", shots=shots)


def test_count_chars_ignores_whitespace_and_keeps_punctuation():
    assert count_chars(" 东海之外，\n有座青丘山 ") == 10


def test_valid_episode_passes():
    validate_episode(make_episode())


@pytest.mark.parametrize("narration", ["", "   ", "这是一段远远超过二十个字的旁白文本，用来验证上限"])
def test_narration_must_be_1_to_20_chars(narration):
    with pytest.raises(EpisodeValidationError, match="旁白"):
        validate_episode(make_episode((narration, "山中藏着一只九尾狐")))


def test_shot_numbers_must_start_at_one_and_be_consecutive():
    shots = [Shot(shot_no=2, narration="旁白", image_prompt="画面", motion_prompt="推近")]

    with pytest.raises(EpisodeValidationError, match="shot_no 应为 1"):
        validate_episode(Episode(episode_id="e1", title="青丘九尾狐", topic="主题", shots=shots))


def test_duration_must_be_five_seconds():
    shots = [Shot(shot_no=1, narration="旁白", image_prompt="画面", motion_prompt="推近", duration_sec=5.5)]

    with pytest.raises(EpisodeValidationError, match="duration_sec"):
        validate_episode(Episode(episode_id="e1", title="青丘九尾狐", topic="主题", shots=shots))


def test_episode_without_shots_is_rejected():
    with pytest.raises(EpisodeValidationError, match="shots 不能为空"):
        validate_episode(Episode(episode_id="e1", title="青丘九尾狐", topic="主题", shots=[]))


def test_blank_title_is_rejected():
    episode = Episode(episode_id="e1", title="  ", topic="主题", shots=make_episode().shots)

    with pytest.raises(EpisodeValidationError, match="title 不能为空"):
        validate_episode(episode)


def test_blank_prompts_are_rejected():
    shots = [Shot(shot_no=1, narration="旁白", image_prompt=" ", motion_prompt="推近")]

    with pytest.raises(EpisodeValidationError, match="image_prompt"):
        validate_episode(Episode(episode_id="e1", title="青丘九尾狐", topic="主题", shots=shots))


def test_episode_from_payload_builds_validated_episode():
    payload = {
        "title": "青丘九尾狐",
        "shots": [
            {"shot_no": 1, "narration": "东海之外有座青丘山", "image_prompt": "画面", "motion_prompt": "推近", "duration_sec": 5},
            {"shot_no": 2, "narration": "山中藏着一只九尾狐", "image_prompt": "画面", "motion_prompt": "回眸"},
        ],
    }

    episode = episode_from_payload(payload, episode_id="e1", topic="青丘山")

    assert episode.episode_id == "e1"
    assert episode.topic == "青丘山"
    assert episode.shots[1].duration_sec == 5.0


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "青丘九尾狐", "shots": [{"shot_no": 1}]},
        {"title": "青丘九尾狐", "shots": ["不是对象"]},
        {"shots": []},
        {"title": None, "shots": [{"shot_no": 1, "narration": "旁白", "image_prompt": "画面", "motion_prompt": "推近"}]},
        {"title": "青丘九尾狐", "shots": [{"shot_no": 1, "narration": None, "image_prompt": "画面", "motion_prompt": "推近"}]},
        {"title": "青丘九尾狐", "shots": [{"shot_no": 1, "narration": ["第一句", "第二句"], "image_prompt": "画面", "motion_prompt": "推近"}]},
        {"title": "青丘九尾狐", "shots": [{"shot_no": 1.9, "narration": "旁白", "image_prompt": "画面", "motion_prompt": "推近"}]},
    ],
)
def test_episode_from_payload_reports_malformed_json(payload):
    with pytest.raises(EpisodeValidationError, match="JSON 结构不合法"):
        episode_from_payload(payload, episode_id="e1", topic="主题")


def test_episode_json_round_trip():
    episode = make_episode()

    assert episode_from_json(episode_to_json(episode)) == episode


def test_new_episode_id_is_unique_and_timestamped():
    first = new_episode_id()
    second = new_episode_id()

    assert first != second
    assert len(first) == len("20261125-143005-a1b2")
    assert first[:8].isdigit()
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_episode.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.episode'`。

- [ ] **Step 3: 写 src/pipeline/episode.py**

```python
"""一条视频的数据契约：Episode 表示整条视频，Shot 表示单个镜头。"""

import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime

MAX_NARRATION_CHARS = 20
SHOT_SECONDS = 5.0


class EpisodeValidationError(ValueError):
    """分镜脚本不符合硬性约束。

    @author zxt
    @date 2026-11-25
    """


@dataclass(frozen=True)
class Shot:
    """单个镜头：一段固定 5 秒的画面及其旁白。

    @author zxt
    @date 2026-11-25
    """

    shot_no: int
    narration: str
    image_prompt: str
    motion_prompt: str
    duration_sec: float = SHOT_SECONDS


@dataclass(frozen=True)
class Episode:
    """一条完整的视频：编号、标题、主题和有序的镜头列表。

    @author zxt
    @date 2026-11-25
    """

    episode_id: str
    title: str
    topic: str
    shots: list[Shot]


def count_chars(text: str) -> int:
    """统计去掉空白后的字符数，标点计入。

    @param text: 待统计的文本
    @return: 字符数
    """
    return len("".join(text.split()))


def new_episode_id(now: datetime | None = None) -> str:
    """生成形如 20261125-143005-a1b2 的唯一编号。

    @param now: 用于编号的时间，默认取当前时间
    @return: 视频编号
    """
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


def validate_episode(episode: Episode) -> None:
    """校验分镜脚本的硬性约束，不满足时抛出 EpisodeValidationError。

    @param episode: 待校验的视频
    """
    if not count_chars(episode.title):
        raise EpisodeValidationError("title 不能为空")
    if not episode.shots:
        raise EpisodeValidationError("shots 不能为空")
    for index, shot in enumerate(episode.shots, start=1):
        where = f"第 {index} 镜"
        if shot.shot_no != index:
            raise EpisodeValidationError(f"{where}的 shot_no 应为 {index}，实际是 {shot.shot_no}")
        length = count_chars(shot.narration)
        if not 1 <= length <= MAX_NARRATION_CHARS:
            raise EpisodeValidationError(f"{where}旁白 {length} 字，必须在 1 到 {MAX_NARRATION_CHARS} 字之间")
        if not shot.image_prompt.strip():
            raise EpisodeValidationError(f"{where}的 image_prompt 不能为空")
        if not shot.motion_prompt.strip():
            raise EpisodeValidationError(f"{where}的 motion_prompt 不能为空")
        if shot.duration_sec != SHOT_SECONDS:
            raise EpisodeValidationError(f"{where}的 duration_sec 必须是 {SHOT_SECONDS}")


def _text(value: object, field: str) -> str:
    """取出必须是字符串的字段。

    @param value: JSON 里的值
    @param field: 字段名，用于报错
    @return: 原样的字符串
    """
    if not isinstance(value, str):
        raise TypeError(f"{field} 不是字符串，而是 {type(value).__name__}")
    return value


def _integer(value: object, field: str) -> int:
    """取出必须是整数的字段，布尔值不算整数。

    @param value: JSON 里的值
    @param field: 字段名，用于报错
    @return: 原样的整数
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} 不是整数，而是 {type(value).__name__}")
    return value


def _number(value: object, field: str) -> float:
    """取出必须是数字的字段，布尔值不算数字。

    @param value: JSON 里的值
    @param field: 字段名，用于报错
    @return: 转成浮点数后的值
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} 不是数字，而是 {type(value).__name__}")
    return float(value)


def episode_from_payload(payload: dict, episode_id: str, topic: str) -> Episode:
    """把脚本阶段给出的 JSON 对象转成 Episode，并校验硬性约束。

    字段类型不对时一律报"JSON 结构不合法"，不做强制转换。大模型把旁白输出成 null 或数组时，
    如果转成字符串 "None" 或 "['..']"，会通过字数校验并一路进入配音和出图。

    @param payload: 含 title 和 shots 的字典
    @param episode_id: 视频编号
    @param topic: 视频主题
    @return: 校验通过的 Episode
    """
    try:
        if not isinstance(payload, dict):
            raise TypeError(f"脚本不是 JSON 对象，而是 {type(payload).__name__}")
        items = payload["shots"]
        if not isinstance(items, list):
            raise TypeError(f"shots 不是数组，而是 {type(items).__name__}")
        shots = []
        for item in items:
            if not isinstance(item, dict):
                raise TypeError(f"shots 的元素不是对象，而是 {type(item).__name__}")
            shots.append(
                Shot(
                    shot_no=_integer(item["shot_no"], "shot_no"),
                    narration=_text(item["narration"], "narration"),
                    image_prompt=_text(item["image_prompt"], "image_prompt"),
                    motion_prompt=_text(item["motion_prompt"], "motion_prompt"),
                    duration_sec=_number(item.get("duration_sec", SHOT_SECONDS), "duration_sec"),
                )
            )
        episode = Episode(episode_id=episode_id, title=_text(payload["title"], "title"), topic=topic, shots=shots)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise EpisodeValidationError(f"JSON 结构不合法：{exc!r}") from exc
    validate_episode(episode)
    return episode

def episode_to_dict(episode: Episode) -> dict:
    """把 Episode 转成可直接 JSON 序列化的字典。

    @param episode: 视频
    @return: 字典
    """
    return asdict(episode)


def episode_to_json(episode: Episode) -> str:
    """把 Episode 序列化成 JSON 文本，用于存入状态库。

    @param episode: 视频
    @return: JSON 文本
    """
    return json.dumps(episode_to_dict(episode), ensure_ascii=False)


def episode_from_json(text: str) -> Episode:
    """从 episode_to_json 的输出还原 Episode。

    @param text: JSON 文本
    @return: 视频
    """
    data = json.loads(text)
    return Episode(
        episode_id=data["episode_id"],
        title=data["title"],
        topic=data["topic"],
        shots=[Shot(**item) for item in data["shots"]],
    )
```

- [ ] **Step 4: 确认测试通过**

Run: `uv run pytest tests/test_episode.py -v`
Expected: PASS，20 个用例（含参数化）。

---

### Task 3: 脚本阶段与 DeepSeek 客户端

**Files:**
- Create: `src/pipeline/script.py`
- Test: `tests/test_script.py`

**Interfaces:**
- Consumes: `pipeline.episode` 的 `MAX_NARRATION_CHARS`、`Episode`、`EpisodeValidationError`、`episode_from_payload`。
- Produces: 异常 `ScriptError(RuntimeError)`。
- Produces: `DeepSeekClient(api_key: str, base_url: str = "https://api.deepseek.com", model: str = "deepseek-chat", http: httpx.Client | None = None, max_attempts: int = 3, backoff_seconds: float = 1.0)`，方法 `complete_json(messages: list[dict[str, str]]) -> dict`。
- Produces: `generate_episode(client: DeepSeekClient, topic: str, episode_id: str, shot_count: int, style_guide: str = "", prompt_language: str = "中文") -> Episode`。

- [ ] **Step 1: 写失败的测试 tests/test_script.py**

```python
import json

import httpx
import pytest

from pipeline.script import MAX_ATTEMPTS, DeepSeekClient, ScriptError, generate_episode

VALID_PAYLOAD = {
    "title": "青丘九尾狐",
    "shots": [
        {"shot_no": 1, "narration": "东海之外有座青丘山", "image_prompt": "云海中的青丘山", "motion_prompt": "镜头缓缓推近", "duration_sec": 5},
        {"shot_no": 2, "narration": "山中藏着一只九尾狐", "image_prompt": "山洞中的九尾狐", "motion_prompt": "九尾狐回眸", "duration_sec": 5},
    ],
}
TOO_LONG_NARRATION = {
    "title": "青丘九尾狐",
    "shots": [
        dict(VALID_PAYLOAD["shots"][0], narration="这是一段远远超过二十个字的旁白文本，用来验证上限"),
        VALID_PAYLOAD["shots"][1],
    ],
}


def make_client(handler, **options) -> DeepSeekClient:
    """用替身传输层构造 DeepSeek 客户端，不发生真实网络请求。"""
    return DeepSeekClient(
        api_key="sk-test",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        backoff_seconds=0,
        **options,
    )


def chat_response(payload) -> httpx.Response:
    """构造一次正常的对话响应；payload 是字典时序列化成 JSON 文本，是字符串时原样返回。"""
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_generate_episode_returns_validated_episode():
    requests = []

    def handler(request):
        requests.append(request)
        return chat_response(VALID_PAYLOAD)

    episode = generate_episode(make_client(handler), "青丘山的九尾狐", "e1", shot_count=2)

    assert episode.episode_id == "e1"
    assert [shot.shot_no for shot in episode.shots] == [1, 2]
    body = json.loads(requests[0].content)
    assert requests[0].headers["authorization"] == "Bearer sk-test"
    assert body["response_format"] == {"type": "json_object"}
    assert "正好有 2 个元素" in body["messages"][0]["content"]
    assert "主题：青丘山的九尾狐" in body["messages"][1]["content"]


def test_generate_episode_asks_for_rewrite_until_output_is_valid():
    outputs = [TOO_LONG_NARRATION, VALID_PAYLOAD]
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return chat_response(outputs.pop(0))

    episode = generate_episode(make_client(handler), "青丘山的九尾狐", "e1", shot_count=2)

    assert episode.shots[0].narration == "东海之外有座青丘山"
    assert "不符合要求" in requests[1]["messages"][1]["content"]
    assert "旁白" in requests[1]["messages"][1]["content"]


def test_generate_episode_rejects_wrong_shot_count_then_gives_up():
    calls = []

    def handler(request):
        calls.append(request)
        return chat_response({"title": "青丘九尾狐", "shots": VALID_PAYLOAD["shots"]})

    with pytest.raises(ScriptError, match=f"连续 {MAX_ATTEMPTS} 次"):
        generate_episode(make_client(handler), "青丘山的九尾狐", "e1", shot_count=3)

    assert len(calls) == MAX_ATTEMPTS


def test_client_retries_on_server_error():
    statuses = [503, 200]

    def handler(request):
        return httpx.Response(503, text="busy") if statuses.pop(0) == 503 else chat_response(VALID_PAYLOAD)

    assert make_client(handler).complete_json([{"role": "user", "content": "你好"}]) == VALID_PAYLOAD


def test_client_fails_fast_on_auth_error():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(ScriptError, match="401"):
        make_client(handler).complete_json([{"role": "user", "content": "你好"}])

    assert len(calls) == 1


def test_client_gives_up_after_repeated_server_errors():
    with pytest.raises(ScriptError, match="连续 3 次"):
        make_client(lambda request: httpx.Response(500, text="boom")).complete_json(
            [{"role": "user", "content": "你好"}]
        )


def test_client_rejects_output_that_is_not_json():
    with pytest.raises(ScriptError, match="不是合法 JSON"):
        make_client(lambda request: chat_response("抱歉，我无法输出 JSON")).complete_json(
            [{"role": "user", "content": "你好"}]
        )


def test_client_reports_malformed_response_body():
    with pytest.raises(ScriptError, match="响应结构不合法"):
        make_client(lambda request: httpx.Response(200, json={"choices": []})).complete_json(
            [{"role": "user", "content": "你好"}]
        )


def test_client_reports_content_that_is_not_text():
    body = {"choices": [{"message": {"content": None}}]}

    with pytest.raises(ScriptError, match="响应结构不合法"):
        make_client(lambda request: httpx.Response(200, json=body)).complete_json(
            [{"role": "user", "content": "你好"}]
        )


def test_client_can_be_created_when_proxy_settings_do_not_parse(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "[::1]")

    assert DeepSeekClient(api_key="sk-test")._http is not None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_script.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.script'`。

- [ ] **Step 3: 写 src/pipeline/script.py**

```python
"""脚本阶段：调用 DeepSeek 生成分镜脚本，并强制校验硬性约束。"""

import json
import time

import httpx

from pipeline.episode import MAX_NARRATION_CHARS, Episode, EpisodeValidationError, episode_from_payload

MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

SYSTEM_PROMPT_TEMPLATE = """你是短视频《AI 经典奇谈》的分镜编剧。题材取自《山海经》和中国古代神话志怪，基调是奇观与想象，不涉及灵异恐怖、血腥暴力。
只输出一个 JSON 对象，不要输出任何解释，也不要加代码块标记。JSON 结构如下：
{{"title": "片名", "shots": [{{"shot_no": 1, "narration": "本镜旁白", "image_prompt": "画面描述", "motion_prompt": "运镜描述", "duration_sec": 5}}]}}
硬性要求：
1. shots 必须正好有 {shot_count} 个元素，shot_no 从 1 开始连续编号。
2. 每镜 narration 是不超过 {max_chars} 个字的中文旁白，标点计入字数；口语化，有悬念。
3. image_prompt 用{prompt_language}描述这一镜的静态画面，必须体现这种画风：{style_guide}。画面里不要出现文字、水印、明星以及影视和游戏里的角色。
4. motion_prompt 用{prompt_language}描述这 5 秒内的镜头运动和画面中事物的动作。
5. 相邻镜头的画面差异要明显，整条片子讲一个完整的小故事。"""


class ScriptError(RuntimeError):
    """脚本阶段失败。

    @author zxt
    @date 2026-11-25
    """


def _new_http_client(timeout: httpx.Timeout) -> httpx.Client:
    """新建 HTTP 客户端，环境里的代理设置能用就用。

    @param timeout: 超时配置
    @return: 可用的 HTTP 客户端
    """
    try:
        return httpx.Client(timeout=timeout)
    except httpx.InvalidURL:
        # 有的环境把 NO_PROXY 写成 [::1] 这类 httpx 解析不了的形式，这种环境里的代理设置不可信，改为完全不读环境变量
        return httpx.Client(timeout=timeout, trust_env=False)


class DeepSeekClient:
    """DeepSeek 对话接口的最小封装，只负责发请求并取回 JSON 对象。

    @author zxt
    @date 2026-11-25
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        http: httpx.Client | None = None,
        max_attempts: int = MAX_ATTEMPTS,
        backoff_seconds: float = 1.0,
    ):
        """
        @param api_key: 接口密钥
        @param base_url: 接口地址
        @param model: 模型名
        @param http: 用于发请求的 HTTP 客户端，默认新建；测试时注入替身
        @param max_attempts: 单次请求的最大尝试次数
        @param backoff_seconds: 重试间隔的基数，按指数增长
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http = http or _new_http_client(httpx.Timeout(120.0, connect=10.0))
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    def complete_json(self, messages: list[dict[str, str]]) -> dict:
        """发送一轮对话并返回模型输出的 JSON 对象。

        网络错误和限流自动重试；鉴权失败等客户端错误直接报错，不重试。

        @param messages: 对话消息列表
        @return: 模型输出的 JSON 对象
        """
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return self._request_once(messages)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in RETRYABLE_STATUS:
                    raise ScriptError(f"DeepSeek 返回 {exc.response.status_code}：{exc.response.text[:300]}") from exc
                last_error = exc
            except httpx.TransportError as exc:
                last_error = exc
            if attempt < self._max_attempts:
                time.sleep(self._backoff_seconds * 2 ** (attempt - 1))
        raise ScriptError(f"DeepSeek 连续 {self._max_attempts} 次请求失败，最后一次：{last_error}") from last_error

    def _request_once(self, messages: list[dict[str, str]]) -> dict:
        """
        @param messages: 对话消息列表
        @return: 模型输出的 JSON 对象
        """
        response = self._http.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": messages,
                "temperature": 1.0,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError(f"content 不是字符串，而是 {type(content).__name__}")
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise ScriptError(f"DeepSeek 响应结构不合法：{exc!r}") from exc
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ScriptError(f"模型输出不是合法 JSON：{content[:200]}") from exc
        if not isinstance(payload, dict):
            raise ScriptError("模型输出的 JSON 不是对象")
        return payload


def generate_episode(
    client: DeepSeekClient,
    topic: str,
    episode_id: str,
    shot_count: int,
    style_guide: str = "",
    prompt_language: str = "中文",
) -> Episode:
    """生成分镜脚本；输出不满足硬性约束时带着错误信息重写，直到通过或用尽次数。

    @param client: DeepSeek 客户端
    @param topic: 视频主题
    @param episode_id: 视频编号
    @param shot_count: 镜头数
    @param style_guide: 画风描述，会写进每镜的画面要求
    @param prompt_language: 画面描述和运镜描述使用的语言
    @return: 校验通过的 Episode
    """
    system = SYSTEM_PROMPT_TEMPLATE.format(
        shot_count=shot_count,
        max_chars=MAX_NARRATION_CHARS,
        style_guide=style_guide or "统一的中国古典志怪绘画风格",
        prompt_language=prompt_language,
    )
    errors: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        user = f"主题：{topic}"
        if errors:
            user += "\n\n上一次的输出不符合要求，请全部重新输出，不要解释：\n" + "\n".join(errors)
        payload = client.complete_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        try:
            episode = episode_from_payload(payload, episode_id, topic)
            if len(episode.shots) != shot_count:
                raise EpisodeValidationError(f"shots 必须正好有 {shot_count} 个元素，实际是 {len(episode.shots)} 个")
        except EpisodeValidationError as exc:
            errors = [str(exc)]
            continue
        return episode
    raise ScriptError(f"分镜脚本连续 {MAX_ATTEMPTS} 次不满足要求，最后一次的错误：{errors[-1]}")
```

- [ ] **Step 4: 确认测试通过**

Run: `uv run pytest tests/test_script.py -v`
Expected: PASS，10 个用例。

---

### Task 4: 工作流模板与参数绑定

**Files:**
- Create: `tests/fixtures/workflows/keyframe_api.json`、`tests/fixtures/workflows/keyframe.binding.json`、`tests/fixtures/workflows/wan_i2v_api.json`、`tests/fixtures/workflows/wan_i2v.binding.json`、`tests/fixtures/workflows/minimax_i2v_api.json`、`tests/fixtures/workflows/minimax_i2v.binding.json`
- Create: `src/pipeline/comfy.py`（本任务只写绑定部分，Task 5 往同一个文件追加客户端）
- Test: `tests/test_comfy.py`（本任务只写绑定相关的用例，Task 5 往同一个文件追加）

**Interfaces:**
- Produces: 异常 `WorkflowError(ValueError)`。
- Produces: 冻结数据类 `WorkflowSpec(template: dict, binding: dict[str, tuple[str, str]])`。
- Produces: `load_workflow(workflows_dir: Path, name: str) -> WorkflowSpec`，读取 `<name>_api.json` 与 `<name>.binding.json`。
- Produces: `render_workflow(spec: WorkflowSpec, params: Mapping[str, object]) -> dict`。
- Produces: `describe_binding(spec: WorkflowSpec) -> list[str]`。

- [ ] **Step 1: 写测试夹具（六个合成的迷你工作流，不是真实模板：关键帧两个，两个引擎的图生视频各两个）**

`tests/fixtures/workflows/keyframe_api.json`：

```json
{
  "3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 20, "cfg": 6.0}},
  "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
  "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["4", 1]}},
  "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["4", 1]}},
  "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ComfyUI"}}
}
```

`tests/fixtures/workflows/keyframe.binding.json`：

```json
{
  "positive_prompt": ["6", "text"],
  "negative_prompt": ["7", "text"],
  "seed": ["3", "seed"],
  "width": ["5", "width"],
  "height": ["5", "height"]
}
```

`tests/fixtures/workflows/wan_i2v_api.json`：

```json
{
  "3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 20}},
  "5": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": 1280, "height": 720, "length": 81, "batch_size": 1}},
  "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
  "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
  "10": {"class_type": "LoadImage", "inputs": {"image": "example.png"}},
  "11": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "wanvideo"}}
}
```

`tests/fixtures/workflows/wan_i2v.binding.json`：

```json
{
  "start_image": ["10", "image"],
  "positive_prompt": ["6", "text"],
  "negative_prompt": ["7", "text"],
  "seed": ["3", "seed"],
  "width": ["5", "width"],
  "height": ["5", "height"],
  "length": ["5", "length"]
}
```

`tests/fixtures/workflows/minimax_i2v_api.json`（模拟一个只暴露提示词和首帧的模板）：

```json
{
  "1": {"class_type": "LoadImage", "inputs": {"image": "example.png"}},
  "2": {"class_type": "MiniMaxVideo", "inputs": {"prompt": ""}},
  "3": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "minimax"}}
}
```

`tests/fixtures/workflows/minimax_i2v.binding.json`：

```json
{
  "start_image": ["1", "image"],
  "positive_prompt": ["2", "prompt"]
}
```

- [ ] **Step 2: 写失败的绑定测试 tests/test_comfy.py**

```python
import json
from pathlib import Path

import httpx
import pytest

from pipeline.comfy import WorkflowError, describe_binding, load_workflow, render_workflow

FIXTURES = Path(__file__).parent / "fixtures" / "workflows"


def test_render_workflow_fills_bound_inputs_without_touching_template():
    spec = load_workflow(FIXTURES, "keyframe")

    workflow = render_workflow(
        spec,
        {"positive_prompt": "云海中的青丘山", "negative_prompt": "模糊", "seed": 42, "width": 704, "height": 1280},
    )

    assert workflow["6"]["inputs"]["text"] == "云海中的青丘山"
    assert workflow["7"]["inputs"]["text"] == "模糊"
    assert workflow["3"]["inputs"]["seed"] == 42
    assert (workflow["5"]["inputs"]["width"], workflow["5"]["inputs"]["height"]) == (704, 1280)
    assert workflow["3"]["inputs"]["steps"] == 20
    assert spec.template["3"]["inputs"]["seed"] == 0


def test_render_workflow_rejects_params_missing_from_binding():
    with pytest.raises(WorkflowError, match="没有这些参数"):
        render_workflow(load_workflow(FIXTURES, "keyframe"), {"prompt": "名字写错了"})


def test_load_workflow_reports_binding_to_missing_node(tmp_path):
    (tmp_path / "keyframe_api.json").write_text((FIXTURES / "keyframe_api.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "keyframe.binding.json").write_text('{"seed": ["99", "seed"]}', encoding="utf-8")

    with pytest.raises(WorkflowError, match="不存在的节点 99"):
        load_workflow(tmp_path, "keyframe")


def test_load_workflow_reports_binding_to_missing_input(tmp_path):
    (tmp_path / "keyframe_api.json").write_text((FIXTURES / "keyframe_api.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "keyframe.binding.json").write_text('{"seed": ["3", "not_an_input"]}', encoding="utf-8")

    with pytest.raises(WorkflowError, match="不存在的输入 not_an_input"):
        load_workflow(tmp_path, "keyframe")


def test_load_workflow_reports_missing_file(tmp_path):
    with pytest.raises(WorkflowError, match="读不到工作流文件"):
        load_workflow(tmp_path, "keyframe")


def test_describe_binding_names_node_class():
    lines = describe_binding(load_workflow(FIXTURES, "keyframe"))

    assert "seed -> 节点 3（KSampler）.seed" in lines
```

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_comfy.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.comfy'`。

- [ ] **Step 4: 写 src/pipeline/comfy.py 的绑定部分**

```python
"""ComfyUI 对接：工作流模板的参数绑定，以及提交任务、轮询结果、取回文件。"""

import copy
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx

CLIENT_ID = "ai-video-pipeline"


class WorkflowError(ValueError):
    """工作流模板或参数绑定有问题。

    @author zxt
    @date 2026-11-25
    """


@dataclass(frozen=True)
class WorkflowSpec:
    """一份 API 格式的工作流模板，加上"逻辑参数到节点输入"的绑定表。

    @author zxt
    @date 2026-11-25
    """

    template: dict
    binding: dict[str, tuple[str, str]]


def load_workflow(workflows_dir: Path, name: str) -> WorkflowSpec:
    """读取 <name>_api.json 和 <name>.binding.json，并检查每个绑定都指向模板里存在的节点输入。

    @param workflows_dir: 工作流目录
    @param name: 工作流名，例如 keyframe 或 i2v
    @return: 工作流规格
    """
    try:
        template = json.loads((workflows_dir / f"{name}_api.json").read_text(encoding="utf-8"))
        raw_binding = json.loads((workflows_dir / f"{name}.binding.json").read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorkflowError(f"读不到工作流文件：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"工作流文件不是合法 JSON：{exc}") from exc
    if not isinstance(template, dict):
        raise WorkflowError(f"{name}_api.json 的顶层必须是一个 JSON 对象")
    if not isinstance(raw_binding, dict):
        raise WorkflowError(f"{name}.binding.json 的顶层必须是一个 JSON 对象")
    binding: dict[str, tuple[str, str]] = {}
    for param, target in raw_binding.items():
        if not isinstance(target, list) or len(target) != 2:
            raise WorkflowError(f"参数 {param} 的绑定格式不正确，应为 [节点编号, 输入名]")
        node, input_name = str(target[0]), str(target[1])
        if node not in template:
            raise WorkflowError(f"参数 {param} 绑定到了不存在的节点 {node}")
        if input_name not in template[node].get("inputs", {}):
            raise WorkflowError(f"参数 {param} 绑定到了节点 {node} 上不存在的输入 {input_name}")
        binding[param] = (node, input_name)
    return WorkflowSpec(template=template, binding=binding)


def render_workflow(spec: WorkflowSpec, params: Mapping[str, object]) -> dict:
    """返回填好参数的工作流副本，模板本身不被修改。

    @param spec: 工作流规格
    @param params: 逻辑参数；出现绑定表里没有的参数直接报错，避免绑定名写错后静默失效
    @return: 可直接提交给 ComfyUI 的工作流
    """
    unknown = sorted(set(params) - set(spec.binding))
    if unknown:
        raise WorkflowError(f"绑定表里没有这些参数：{unknown}")
    workflow = copy.deepcopy(spec.template)
    for param, value in params.items():
        node, input_name = spec.binding[param]
        workflow[node]["inputs"][input_name] = value
    return workflow


def describe_binding(spec: WorkflowSpec) -> list[str]:
    """生成便于人眼核对的多行说明。

    @param spec: 工作流规格
    @return: 每个参数一行，形如 seed -> 节点 3（KSampler）.seed
    """
    lines = []
    for param in sorted(spec.binding):
        node, input_name = spec.binding[param]
        lines.append(f"{param} -> 节点 {node}（{spec.template[node].get('class_type', '?')}）.{input_name}")
    return lines
```

- [ ] **Step 5: 确认测试通过**

Run: `uv run pytest tests/test_comfy.py -v`
Expected: PASS，6 个用例。

---

### Task 5: ComfyUI 客户端

**Files:**
- Modify: `src/pipeline/comfy.py`（在文件末尾追加）
- Test: `tests/test_comfy.py`（在文件末尾追加，并修改 import 行）

**Interfaces:**
- Consumes: Task 4 的 `WorkflowSpec` 等同文件内容。
- Produces: 冻结数据类 `OutputFile(filename: str, subfolder: str, type: str)`。
- Produces: 异常 `ComfyError(RuntimeError)`。
- Produces: `extract_output_files(entry: dict) -> list[OutputFile]`。
- Produces: `ComfyClient(base_url: str, http: httpx.Client | None = None, poll_interval: float = 1.0, timeout: float = 14400.0)`，方法 `run(workflow: dict, dest_dir: Path, prefix: str) -> list[Path]`、`queue_prompt(workflow: dict) -> str`、`wait_for_outputs(prompt_id: str) -> list[OutputFile]`、`download(file: OutputFile, dest: Path) -> Path`、`upload_image(image: Path) -> str`。

- [ ] **Step 1: 把 tests/test_comfy.py 的 import 行改成下面这样，并在文件末尾追加用例**

```python
from pipeline.comfy import (
    ComfyClient,
    ComfyError,
    OutputFile,
    WorkflowError,
    describe_binding,
    extract_output_files,
    load_workflow,
    render_workflow,
)
```

追加的用例：

```python
HISTORY_SUCCESS = {
    "pid-1": {
        "outputs": {"9": {"images": [{"filename": "ComfyUI_00001_.png", "subfolder": "", "type": "output"}]}},
        "status": {"status_str": "success"},
    }
}
HISTORY_ERROR = {
    "pid-2": {
        "outputs": {},
        "status": {"status_str": "error", "messages": [["execution_error", "CUDA out of memory"]]},
    }
}


def make_client(handler, **options) -> ComfyClient:
    """用替身传输层构造 ComfyUI 客户端，不发生真实网络请求。"""
    return ComfyClient("http://comfy", http=httpx.Client(transport=httpx.MockTransport(handler)), poll_interval=0, **options)


def test_extract_output_files_collects_every_output_list():
    entry = {
        "outputs": {
            "9": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]},
            "11": {"gifs": [{"filename": "b.webm", "subfolder": "sub", "type": "output"}, {"filename": "c.webm"}]},
            "12": "不是字典",
        }
    }

    files = extract_output_files(entry)

    assert [(f.filename, f.subfolder, f.type) for f in files] == [
        ("a.png", "", "output"),
        ("b.webm", "sub", "output"),
        ("c.webm", "", "output"),
    ]


def test_run_downloads_every_output(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "pid-1"})
        if request.url.path == "/history/pid-1":
            return httpx.Response(200, json=HISTORY_SUCCESS)
        if request.url.path == "/view":
            return httpx.Response(200, content=b"PNGDATA")
        raise AssertionError(f"意外的请求：{request.url.path}")

    paths = make_client(handler).run({"1": {}}, tmp_path, "keyframe_001")

    assert [path.name for path in paths] == ["keyframe_001_0.png"]
    assert paths[0].read_bytes() == b"PNGDATA"
    assert json.loads(seen[0].content) == {"prompt": {"1": {}}, "client_id": "ai-video-pipeline"}
    assert seen[2].url.params["filename"] == "ComfyUI_00001_.png"
    assert seen[2].url.params["type"] == "output"


def test_run_raises_when_execution_failed():
    def handler(request):
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "pid-2"})
        return httpx.Response(200, json=HISTORY_ERROR)

    with pytest.raises(ComfyError, match="CUDA out of memory"):
        make_client(handler).run({"1": {}}, Path("unused"), "x")


def test_queue_prompt_reports_rejected_workflow():
    with pytest.raises(ComfyError, match="参数绑定填错了"):
        make_client(lambda request: httpx.Response(400, text="prompt_outputs_failed_validation")).queue_prompt({"1": {}})


def test_queue_prompt_reports_unreachable_server():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ComfyError, match="连不上 ComfyUI"):
        make_client(handler).queue_prompt({"1": {}})


def test_wait_for_outputs_times_out():
    with pytest.raises(ComfyError, match="超"):
        make_client(lambda request: httpx.Response(200, json={}), timeout=0).wait_for_outputs("pid-9")


def test_upload_image_returns_name(tmp_path):
    image = tmp_path / "keyframe_001.png"
    image.write_bytes(b"PNGDATA")

    def handler(request):
        assert b"PNGDATA" in request.content
        return httpx.Response(200, json={"name": "keyframe_001.png", "subfolder": "", "type": "input"})

    assert make_client(handler).upload_image(image) == "keyframe_001.png"


def test_wait_for_outputs_polls_until_the_task_appears():
    replies = [{}, HISTORY_SUCCESS]

    def handler(request):
        return httpx.Response(200, json=replies.pop(0))

    files = make_client(handler).wait_for_outputs("pid-1")

    assert [file.filename for file in files] == ["ComfyUI_00001_.png"]


def test_run_raises_when_no_output_was_produced(tmp_path):
    def handler(request):
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "pid-3"})
        return httpx.Response(200, json={"pid-3": {"outputs": {}, "status": {"status_str": "success"}}})

    with pytest.raises(ComfyError, match="没有产生任何输出文件"):
        make_client(handler).run({"1": {}}, tmp_path, "x")


def test_run_ignores_temporary_outputs(tmp_path):
    history = {
        "pid-1": {
            "outputs": {
                "9": {"images": [{"filename": "preview.png", "subfolder": "", "type": "temp"}]},
                "10": {"images": [{"filename": "final.png", "subfolder": "", "type": "output"}]},
            },
            "status": {"status_str": "success"},
        }
    }

    def handler(request):
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "pid-1"})
        if request.url.path == "/history/pid-1":
            return httpx.Response(200, json=history)
        return httpx.Response(200, content=b"PNGDATA")

    paths = make_client(handler).run({"1": {}}, tmp_path, "keyframe_001")

    assert [path.name for path in paths] == ["keyframe_001_0.png"]


def test_queue_prompt_reports_response_without_prompt_id():
    with pytest.raises(ComfyError, match="没有返回 prompt_id"):
        make_client(lambda request: httpx.Response(200, json={})).queue_prompt({"1": {}})


def test_http_failures_are_reported_as_comfy_error(tmp_path):
    image = tmp_path / "keyframe_001.png"
    image.write_bytes(b"PNGDATA")
    client = make_client(lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(ComfyError, match="返回了 500"):
        client.wait_for_outputs("pid-1")
    with pytest.raises(ComfyError, match="返回了 500"):
        client.download(OutputFile("a.png", "", "output"), tmp_path / "a.png")
    with pytest.raises(ComfyError, match="返回了 500"):
        client.upload_image(image)


def test_connection_failures_are_reported_as_comfy_error(tmp_path):
    image = tmp_path / "keyframe_001.png"
    image.write_bytes(b"PNGDATA")

    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    client = make_client(handler)

    with pytest.raises(ComfyError, match="连不上 ComfyUI"):
        client.wait_for_outputs("pid-1")
    with pytest.raises(ComfyError, match="连不上 ComfyUI"):
        client.download(OutputFile("a.png", "", "output"), tmp_path / "a.png")
    with pytest.raises(ComfyError, match="连不上 ComfyUI"):
        client.upload_image(image)


def test_upload_image_reports_response_without_name(tmp_path):
    image = tmp_path / "keyframe_001.png"
    image.write_bytes(b"PNGDATA")

    with pytest.raises(ComfyError, match="没有返回文件名"):
        make_client(lambda request: httpx.Response(200, json={})).upload_image(image)


def test_default_client_ignores_environment_proxies():
    assert ComfyClient("http://127.0.0.1:8188")._http.trust_env is False
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_comfy.py -v`
Expected: FAIL，报 `ImportError: cannot import name 'ComfyClient' from 'pipeline.comfy'`。

- [ ] **Step 3: 在 src/pipeline/comfy.py 末尾追加客户端**

```python
@dataclass(frozen=True)
class OutputFile:
    """ComfyUI 输出的一个文件在服务端的定位信息。

    @author zxt
    @date 2026-11-25
    """

    filename: str
    subfolder: str
    type: str


class ComfyError(RuntimeError):
    """ComfyUI 任务失败，或返回了无法理解的内容。

    @author zxt
    @date 2026-11-25
    """


def extract_output_files(entry: dict) -> list[OutputFile]:
    """从 /history 的一条记录里收集全部输出文件，不依赖具体节点的输出字段名。

    @param entry: /history 中以任务编号为键的那一项
    @return: 输出文件列表
    """
    files: list[OutputFile] = []
    for node_output in entry.get("outputs", {}).values():
        if not isinstance(node_output, dict):
            continue
        for value in node_output.values():
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict) and "filename" in item:
                    files.append(
                        OutputFile(
                            filename=item["filename"],
                            subfolder=item.get("subfolder", ""),
                            type=item.get("type", "output"),
                        )
                    )
    return files


class ComfyClient:
    """ComfyUI HTTP 接口的最小客户端：提交任务、轮询历史、上传和下载文件。

    @author zxt
    @date 2026-11-25
    """

    def __init__(self, base_url: str, http: httpx.Client | None = None, poll_interval: float = 1.0, timeout: float = 4 * 3600.0):
        """
        @param base_url: ComfyUI 地址，例如 http://127.0.0.1:8188
        @param http: 用于发请求的 HTTP 客户端，默认新建；测试时注入替身
        @param poll_interval: 轮询历史的间隔秒数
        @param timeout: 等待单个任务的最长秒数
        """
        self._base_url = base_url.rstrip("/")
        # 只连本机回环地址，不读环境里的代理设置，免得被奇怪的 NO_PROXY 或系统代理拦住
        self._http = http or httpx.Client(timeout=httpx.Timeout(300.0, connect=5.0), trust_env=False)
        self._poll_interval = poll_interval
        self._timeout = timeout

    def run(self, workflow: dict, dest_dir: Path, prefix: str) -> list[Path]:
        """提交工作流，等它跑完，把正式输出文件下载到 dest_dir。预览图之类的临时输出不下载。

        @param workflow: API 格式的工作流
        @param dest_dir: 下载目录
        @param prefix: 下载文件名的前缀
        @return: 下载后的本地文件列表，不会是空列表
        """
        prompt_id = self.queue_prompt(workflow)
        files = [file for file in self.wait_for_outputs(prompt_id) if file.type == "output"]
        if not files:
            raise ComfyError(f"任务 {prompt_id} 执行成功，但没有产生任何输出文件")
        dest_dir.mkdir(parents=True, exist_ok=True)
        return [
            self.download(file, dest_dir / f"{prefix}_{index}{Path(file.filename).suffix}")
            for index, file in enumerate(files)
        ]

    def queue_prompt(self, workflow: dict) -> str:
        """提交工作流。

        @param workflow: API 格式的工作流
        @return: 任务编号
        """
        response = self._request("POST", "/prompt", json={"prompt": workflow, "client_id": CLIENT_ID})
        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            raise ComfyError(f"ComfyUI 没有返回 prompt_id：{response.text[:300]}")
        return prompt_id

    def wait_for_outputs(self, prompt_id: str) -> list[OutputFile]:
        """轮询 /history 直到任务出现；任务出错或超时则抛异常。

        @param prompt_id: 任务编号
        @return: 该任务的输出文件列表
        """
        deadline = time.monotonic() + self._timeout
        while True:
            entry = self._request("GET", f"/history/{prompt_id}").json().get(prompt_id)
            if entry is not None:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyError(
                        f"ComfyUI 执行出错：{json.dumps(status.get('messages', []), ensure_ascii=False)[:800]}"
                    )
                return extract_output_files(entry)
            if time.monotonic() >= deadline:
                raise ComfyError(f"等待 ComfyUI 任务 {prompt_id} 超过 {self._timeout:.0f} 秒仍未完成")
            time.sleep(self._poll_interval)

    def download(self, file: OutputFile, dest: Path) -> Path:
        """下载一个输出文件。

        @param file: 输出文件在服务端的定位信息
        @param dest: 本地保存路径
        @return: 本地保存路径
        """
        response = self._request(
            "GET",
            "/view",
            params={"filename": file.filename, "subfolder": file.subfolder, "type": file.type},
        )
        dest.write_bytes(response.content)
        return dest

    def upload_image(self, image: Path) -> str:
        """把本地图片上传到 ComfyUI 的输入目录。

        @param image: 本地图片路径
        @return: LoadImage 节点要填的文件名
        """
        response = self._request(
            "POST",
            "/upload/image",
            files={"image": (image.name, image.read_bytes(), "image/png")},
            data={"overwrite": "true"},
        )
        name = response.json().get("name")
        if not name:
            raise ComfyError("ComfyUI 收下了图片，但没有返回文件名")
        return name

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """发一次请求，把连不上和非 2xx 统一转成 ComfyError，调用方只需要认这一种异常。

        @param method: HTTP 方法
        @param path: 接口路径
        @param kwargs: 交给 httpx 的其余参数，例如 json、params、files、data
        @return: 2xx 的响应
        """
        try:
            response = self._http.request(method, f"{self._base_url}{path}", **kwargs)
        except httpx.TransportError as exc:
            raise ComfyError(f"连不上 ComfyUI（{self._base_url}），请确认它已经启动：{exc}") from exc
        if response.status_code == 400 and path == "/prompt":
            raise ComfyError(f"ComfyUI 拒绝了这个工作流，多半是参数绑定填错了：{response.text[:800]}")
        if response.status_code >= 400:
            raise ComfyError(f"ComfyUI 的 {path} 返回了 {response.status_code}：{response.text[:300]}")
        return response
```

- [ ] **Step 4: 确认测试通过**

Run: `uv run pytest tests/test_comfy.py -v`
Expected: PASS，21 个用例。

---

### Task 6: ffmpeg 封装与合成

**Files:**
- Create: `src/pipeline/ffmpeg.py`
- Create: `src/pipeline/compose.py`
- Test: `tests/test_ffmpeg.py`、`tests/test_compose.py`

**Interfaces:**
- Consumes: Task 2 的 `SHOT_SECONDS`。
- Produces: 异常 `MediaError(RuntimeError)`。
- Produces: `FFmpeg(exe: str, timeout: float = 1800.0)`，类方法 `resolve(configured: str = "") -> FFmpeg`，方法 `run(args: list[str], timeout: float | None = None) -> str`、`duration(media: Path) -> float`。
- Produces: `build_command(clips: list[Path], voices: list[Path], out_path: Path, shot_seconds: float, fps: int, width: int, height: int) -> list[str]`。
- Produces: `compose(clips: list[Path], voices: list[Path], out_path: Path, ffmpeg: FFmpeg, shot_seconds: float = 5.0, fps: int = 24, width: int = 720, height: int = 1280) -> Path`。

说明：ffmpeg 不要求单独安装。`FFmpeg.resolve` 依次尝试配置里指定的路径、PATH 上的 ffmpeg、pip 包 imageio-ffmpeg 自带的那个。已在本机验证过：pip 包自带的版本支持 H.264 和 AAC 编码，下面的滤镜写法能把一个 5 秒多、一个 2 秒的镜头和一段 5 秒、一段 1 秒的配音合成为精确 10.0 秒的成片。

- [ ] **Step 1: 写失败的测试 tests/test_ffmpeg.py**

```python
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
```

`tests/test_ffmpeg.py` 里用到的 `FakeVideoGenerator` 在 Task 7 才实现，所以这个文件要等 Task 7 完成后才能全部通过。本任务先写它，Task 7 结束时一起跑。

- [ ] **Step 2: 写失败的测试 tests/test_compose.py**

```python
import pytest

from pipeline.compose import build_command, compose
from pipeline.fakes import FakeTtsBackend, FakeVideoGenerator


def make_media(ffmpeg, tmp_path, clip_seconds, voice_seconds):
    """按给定的秒数造出镜头片段和旁白音频。"""
    clips = [
        FakeVideoGenerator(ffmpeg, seconds=seconds).generate_video(tmp_path / "none.png", "运镜", 1, tmp_path, f"shot_{index:03d}")
        for index, seconds in enumerate(clip_seconds, start=1)
    ]
    voices = [
        FakeTtsBackend(seconds=seconds).synthesize("旁白", tmp_path, f"voice_{index:03d}")
        for index, seconds in enumerate(voice_seconds, start=1)
    ]
    return clips, voices


def test_compose_aligns_every_shot_to_five_seconds(ffmpeg, tmp_path):
    clips, voices = make_media(ffmpeg, tmp_path, clip_seconds=[5.5, 2], voice_seconds=[5, 1])
    out = tmp_path / "final.mp4"

    assert compose(clips, voices, out, ffmpeg, width=128, height=224) == out

    assert abs(ffmpeg.duration(out) - 10.0) < 0.1
    assert "128x224" in ffmpeg.run(["-loglevel", "info", "-i", str(out), "-map", "0", "-f", "null", "-"])


def test_compose_rejects_mismatched_counts(ffmpeg, tmp_path):
    clips, voices = make_media(ffmpeg, tmp_path, clip_seconds=[5, 5], voice_seconds=[5])

    with pytest.raises(ValueError, match="数量必须一致"):
        compose(clips, voices, tmp_path / "final.mp4", ffmpeg, width=128, height=224)


def test_compose_rejects_empty_input(ffmpeg, tmp_path):
    with pytest.raises(ValueError, match="没有镜头可以合成"):
        compose([], [], tmp_path / "final.mp4", ffmpeg)


def test_build_command_rejects_odd_dimensions(tmp_path):
    with pytest.raises(ValueError, match="偶数"):
        build_command([tmp_path / "a.mp4"], [tmp_path / "a.wav"], tmp_path / "out.mp4", 5.0, 24, 127, 224)


def test_build_command_labels_streams_in_order(tmp_path):
    command = build_command(
        [tmp_path / "a.mp4", tmp_path / "b.mp4"],
        [tmp_path / "a.wav", tmp_path / "b.wav"],
        tmp_path / "out.mp4",
        5.0,
        24,
        128,
        224,
    )

    filters = command[command.index("-filter_complex") + 1].split(";")
    assert filters[0].startswith("[0:v]fps=24,scale=128:224")
    assert filters[1].startswith("[1:v]fps=24")
    assert filters[2].startswith("[2:a]aresample=44100")
    assert filters[3].startswith("[3:a]aresample=44100")
    assert filters[4] == "[v0][v1]concat=n=2:v=1:a=0[vout]"
    assert filters[5] == "[a0][a1]concat=n=2:v=0:a=1[aout]"
    assert command[-1] == str(tmp_path / "out.mp4")
```

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_compose.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.compose'`。

- [ ] **Step 4: 写 src/pipeline/ffmpeg.py**

```python
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
```

- [ ] **Step 5: 写 src/pipeline/compose.py**

```python
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
```

- [ ] **Step 6: 确认实现可导入**

Run: `uv run python -c "from pipeline.compose import build_command, compose; from pipeline.ffmpeg import FFmpeg; print(FFmpeg.resolve().run(['-version']).splitlines()[0])"`
Expected: 打印一行 ffmpeg 版本信息，不报错。

两个测试文件此时都会在收集阶段报 `ModuleNotFoundError: No module named 'pipeline.fakes'`，这是预期的，Task 7 实现替身后一起运行。

---

### Task 7: 生成器与替身

**Files:**
- Create: `src/pipeline/generators.py`
- Create: `src/pipeline/fakes.py`
- Test: `tests/test_generators.py`、`tests/test_fakes.py`

**Interfaces:**
- Consumes: Task 4、5 的 `ComfyClient`、`WorkflowSpec`、`render_workflow`；Task 2 的 `Episode`、`Shot`；Task 6 的 `FFmpeg`。
- Produces: 协议 `ImageGenerator`，方法 `generate_image(prompt: str, seed: int, dest_dir: Path, name: str) -> Path`。
- Produces: 协议 `VideoGenerator`，方法 `generate_video(start_image: Path, prompt: str, seed: int, dest_dir: Path, name: str) -> Path`。
- Produces: `ComfyImageGenerator(client: ComfyClient, spec: WorkflowSpec, negative_prompt: str, width: int, height: int)`。
- Produces: `ComfyVideoGenerator(client: ComfyClient, spec: WorkflowSpec, negative_prompt: str, width: int, height: int, frames: int)`。
- Produces: `fake_episode(topic: str, episode_id: str, shot_count: int) -> Episode`、`FakeImageGenerator()`、`FakeVideoGenerator(ffmpeg: FFmpeg, seconds: float = 5.0, color: str = "gray", size: tuple[int, int] = (270, 480))`、`FakeTtsBackend(seconds: float = 5.0, sample_rate: int = 24000, frequency: float = 440.0)`，后两者分别实现 `VideoGenerator` 和 `TtsBackend`（`TtsBackend` 在 Task 8 定义，这里的 `synthesize(text: str, dest_dir: Path, name: str) -> Path` 签名与它一致）。

- [ ] **Step 1: 写失败的测试 tests/test_generators.py**

```python
from pathlib import Path

import pytest

from pipeline.comfy import WorkflowError, load_workflow, render_workflow
from pipeline.generators import ComfyImageGenerator, ComfyVideoGenerator

FIXTURES = Path(__file__).parent / "fixtures" / "workflows"


class RecordingClient:
    """记录提交的工作流，并按给定文件名伪造输出。"""

    def __init__(self, output_names):
        self.workflows = []
        self.uploads = []
        self.output_names = output_names

    def run(self, workflow, dest_dir, prefix):
        self.workflows.append(workflow)
        paths = []
        for index, name in enumerate(self.output_names):
            path = dest_dir / f"{prefix}_{index}{Path(name).suffix}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
            paths.append(path)
        return paths

    def upload_image(self, image):
        self.uploads.append(image)
        return image.name


def test_image_generator_fills_prompt_and_size(tmp_path):
    client = RecordingClient(["ComfyUI_00001_.png"])
    generator = ComfyImageGenerator(client, load_workflow(FIXTURES, "keyframe"), negative_prompt="模糊", width=704, height=1280)

    path = generator.generate_image("云海中的青丘山", 42, tmp_path, "keyframe_001")

    assert path == tmp_path / "keyframe_001.png"
    assert path.read_bytes() == b"data"
    workflow = client.workflows[0]
    assert (workflow["6"]["inputs"]["text"], workflow["7"]["inputs"]["text"]) == ("云海中的青丘山", "模糊")
    assert (workflow["3"]["inputs"]["seed"], workflow["5"]["inputs"]["width"], workflow["5"]["inputs"]["height"]) == (42, 704, 1280)


def test_video_generator_uploads_start_frame_and_keeps_real_suffix(tmp_path):
    client = RecordingClient(["wanvideo_00001.webm", "wanvideo_00001_preview.webm"])
    generator = ComfyVideoGenerator(client, load_workflow(FIXTURES, "wan_i2v"), negative_prompt="", width=720, height=1280, frames=121)
    start_image = tmp_path / "keyframe_001.png"
    start_image.write_bytes(b"png")

    path = generator.generate_video(start_image, "镜头缓缓推近", 7, tmp_path / "clips", "shot_001")

    assert client.uploads == [start_image]
    assert path == tmp_path / "clips" / "shot_001.webm"
    assert not (tmp_path / "clips" / "shot_001_1.webm").exists()
    workflow = client.workflows[0]
    assert workflow["10"]["inputs"]["image"] == "keyframe_001.png"
    assert (workflow["6"]["inputs"]["text"], workflow["3"]["inputs"]["seed"]) == ("镜头缓缓推近", 7)
    assert (workflow["5"]["inputs"]["width"], workflow["5"]["inputs"]["height"], workflow["5"]["inputs"]["length"]) == (720, 1280, 121)


def test_generator_skips_params_that_the_template_does_not_expose(tmp_path):
    (tmp_path / "keyframe_api.json").write_text((FIXTURES / "keyframe_api.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "keyframe.binding.json").write_text(
        '{"positive_prompt": ["6", "text"], "seed": ["3", "seed"]}',
        encoding="utf-8",
    )
    client = RecordingClient(["a.png"])
    generator = ComfyImageGenerator(client, load_workflow(tmp_path, "keyframe"), "模糊", 704, 1280)

    path = generator.generate_image("画面", 1, tmp_path / "out", "keyframe_001")

    assert path == tmp_path / "out" / "keyframe_001.png"
    workflow = client.workflows[0]
    assert workflow["6"]["inputs"]["text"] == "画面"
    assert workflow["3"]["inputs"]["seed"] == 1
    assert workflow["5"]["inputs"]["width"] == 512
    with pytest.raises(WorkflowError, match="没有这些参数"):
        render_workflow(load_workflow(tmp_path, "keyframe"), {"negative_prompt": "模糊"})


def test_video_generator_skips_params_that_the_template_does_not_expose(tmp_path):
    (tmp_path / "wan_i2v_api.json").write_text((FIXTURES / "wan_i2v_api.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "wan_i2v.binding.json").write_text(
        '{"start_image": ["10", "image"], "positive_prompt": ["6", "text"]}',
        encoding="utf-8",
    )
    client = RecordingClient(["wanvideo_00001.webm"])
    generator = ComfyVideoGenerator(client, load_workflow(tmp_path, "wan_i2v"), "", 720, 1280, 121)
    start_image = tmp_path / "keyframe_001.png"
    start_image.write_bytes(b"png")

    path = generator.generate_video(start_image, "镜头缓缓推近", 7, tmp_path, "shot_001")

    assert path == tmp_path / "shot_001.webm"
    workflow = client.workflows[0]
    assert workflow["10"]["inputs"]["image"] == "keyframe_001.png"
    assert workflow["6"]["inputs"]["text"] == "镜头缓缓推近"
    assert workflow["5"]["inputs"]["width"] == 1280


def test_generators_require_their_required_bindings(tmp_path):
    (tmp_path / "keyframe_api.json").write_text((FIXTURES / "keyframe_api.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "keyframe.binding.json").write_text('{"seed": ["3", "seed"]}', encoding="utf-8")
    image_generator = ComfyImageGenerator(RecordingClient(["a.png"]), load_workflow(tmp_path, "keyframe"), "", 704, 1280)

    with pytest.raises(WorkflowError, match="keyframe 的绑定表缺少必填参数 \\['positive_prompt'\\]"):
        image_generator.generate_image("画面", 1, tmp_path, "keyframe_001")

    (tmp_path / "wan_i2v_api.json").write_text((FIXTURES / "wan_i2v_api.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "wan_i2v.binding.json").write_text('{"positive_prompt": ["6", "text"]}', encoding="utf-8")
    video_generator = ComfyVideoGenerator(RecordingClient(["a.webm"]), load_workflow(tmp_path, "wan_i2v"), "", 720, 1280, 121)
    start_image = tmp_path / "keyframe_001.png"
    start_image.write_bytes(b"png")

    with pytest.raises(WorkflowError, match="i2v 的绑定表缺少必填参数 \\['start_image'\\]"):
        video_generator.generate_video(start_image, "运镜", 1, tmp_path, "shot_001")
```

- [ ] **Step 2: 写失败的测试 tests/test_fakes.py**

```python
import soundfile as sf
from PIL import Image

from pipeline.episode import validate_episode
from pipeline.fakes import FakeImageGenerator, FakeTtsBackend, FakeVideoGenerator, fake_episode


def test_fake_episode_passes_validation_for_any_shot_count():
    validate_episode(fake_episode("青丘山的九尾狐", "e1", 1))
    validate_episode(fake_episode("青丘山的九尾狐", "e2", 24))


def test_fake_image_is_a_real_png(tmp_path):
    path = FakeImageGenerator().generate_image("画面", 1, tmp_path, "keyframe_001")

    with Image.open(path) as image:
        assert (image.format, image.size) == ("PNG", (64, 64))


def test_fake_video_has_requested_duration(ffmpeg, tmp_path):
    path = FakeVideoGenerator(ffmpeg, seconds=2).generate_video(tmp_path / "none.png", "运镜", 1, tmp_path, "shot_001")

    assert abs(ffmpeg.duration(path) - 2.0) < 0.1


def test_fake_voice_has_requested_duration(tmp_path):
    path = FakeTtsBackend(seconds=3).synthesize("旁白", tmp_path, "voice_001")

    data, sample_rate = sf.read(path)
    assert sample_rate == 24000
    assert abs(len(data) / sample_rate - 3.0) < 0.01
```

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_generators.py tests/test_fakes.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.generators'`。

- [ ] **Step 4: 写 src/pipeline/generators.py**

```python
"""接在 ComfyUI 上的两个生成器：文生图出关键帧，图生视频出镜头。"""

from pathlib import Path
from typing import Protocol

from pipeline.comfy import ComfyClient, WorkflowError, WorkflowSpec, render_workflow


class ImageGenerator(Protocol):
    """关键帧生成器的接口约定。

    @author zxt
    @date 2026-11-25
    """

    def generate_image(self, prompt: str, seed: int, dest_dir: Path, name: str) -> Path:
        """
        @param prompt: 画面描述
        @param seed: 随机种子
        @param dest_dir: 输出目录
        @param name: 输出文件名，不带扩展名
        @return: 生成的图片路径
        """
        ...


class VideoGenerator(Protocol):
    """镜头生成器的接口约定。

    @author zxt
    @date 2026-11-25
    """

    def generate_video(self, start_image: Path, prompt: str, seed: int, dest_dir: Path, name: str) -> Path:
        """
        @param start_image: 首帧图片
        @param prompt: 运镜和动作描述
        @param seed: 随机种子
        @param dest_dir: 输出目录
        @param name: 输出文件名，不带扩展名
        @return: 生成的视频片段路径
        """
        ...


def _render_bound(spec: WorkflowSpec, candidates: dict[str, object]) -> dict:
    """只绑定模板里存在的参数：不同的模型和工作流暴露的输入不一样。

    @param spec: 工作流规格
    @param candidates: 生成器想填进去的全部参数
    @return: 可直接提交给 ComfyUI 的工作流
    """
    return render_workflow(spec, {key: value for key, value in candidates.items() if key in spec.binding})


def _require_bound(spec: WorkflowSpec, required: tuple[str, ...], workflow_name: str) -> None:
    """确认必填参数都出现在绑定表里。

    @param spec: 工作流规格
    @param required: 必填的参数名
    @param workflow_name: 工作流名，用于报错
    """
    missing = [param for param in required if param not in spec.binding]
    if missing:
        raise WorkflowError(f"{workflow_name} 的绑定表缺少必填参数 {missing}")


def _keep_first_output(outputs: list[Path], dest_dir: Path, name: str) -> Path:
    """只保留第一个输出并改成调用方给定的名字，其余的删掉；扩展名保留 ComfyUI 给的，避免内容和容器不符。

    @param outputs: ComfyUI 客户端下载到的文件
    @param dest_dir: 输出目录
    @param name: 目标文件名，不带扩展名
    @return: 重命名后的文件路径
    """
    first = outputs[0]
    target = dest_dir / f"{name}{first.suffix}"
    if first != target:
        first.replace(target)
    for extra in outputs[1:]:
        extra.unlink(missing_ok=True)
    return target


class ComfyImageGenerator:
    """用文生图工作流生成一张关键帧。

    @author zxt
    @date 2026-11-25
    """

    def __init__(self, client: ComfyClient, spec: WorkflowSpec, negative_prompt: str, width: int, height: int):
        """
        @param client: ComfyUI 客户端
        @param spec: 文生图工作流规格
        @param negative_prompt: 负向提示词
        @param width: 图片宽度
        @param height: 图片高度
        """
        self._client = client
        self._spec = spec
        self._negative_prompt = negative_prompt
        self._width = width
        self._height = height

    def generate_image(self, prompt: str, seed: int, dest_dir: Path, name: str) -> Path:
        """
        @param prompt: 画面描述
        @param seed: 随机种子
        @param dest_dir: 输出目录
        @param name: 输出文件名，不带扩展名
        @return: 生成的图片路径
        """
        candidates = {
            "positive_prompt": prompt,
            "negative_prompt": self._negative_prompt,
            "seed": seed,
            "width": self._width,
            "height": self._height,
        }
        _require_bound(self._spec, ("positive_prompt",), "keyframe")
        workflow = _render_bound(self._spec, candidates)
        return _keep_first_output(self._client.run(workflow, dest_dir, name), dest_dir, name)


class ComfyVideoGenerator:
    """用图生视频工作流，从一张关键帧生成一段镜头。

    @author zxt
    @date 2026-11-25
    """

    def __init__(self, client: ComfyClient, spec: WorkflowSpec, negative_prompt: str, width: int, height: int, frames: int):
        """
        @param client: ComfyUI 客户端
        @param spec: 图生视频工作流规格
        @param negative_prompt: 负向提示词
        @param width: 视频宽度
        @param height: 视频高度
        @param frames: 帧数
        """
        self._client = client
        self._spec = spec
        self._negative_prompt = negative_prompt
        self._width = width
        self._height = height
        self._frames = frames

    def generate_video(self, start_image: Path, prompt: str, seed: int, dest_dir: Path, name: str) -> Path:
        """
        @param start_image: 首帧图片
        @param prompt: 运镜和动作描述
        @param seed: 随机种子
        @param dest_dir: 输出目录
        @param name: 输出文件名，不带扩展名
        @return: 生成的视频片段路径
        """
        image_name = self._client.upload_image(start_image)
        candidates = {
            "start_image": image_name,
            "positive_prompt": prompt,
            "negative_prompt": self._negative_prompt,
            "seed": seed,
            "width": self._width,
            "height": self._height,
            "length": self._frames,
        }
        _require_bound(self._spec, ("start_image", "positive_prompt"), "i2v")
        workflow = _render_bound(self._spec, candidates)
        return _keep_first_output(self._client.run(workflow, dest_dir, name), dest_dir, name)
```

- [ ] **Step 5: 写 src/pipeline/fakes.py**

```python
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
```

- [ ] **Step 6: 确认测试通过，并补跑 Task 6 的测试**

Run: `uv run pytest tests/test_generators.py tests/test_fakes.py tests/test_ffmpeg.py tests/test_compose.py -v`
Expected: PASS，共 18 个用例（5 + 4 + 4 + 5）。

---

### Task 8: 配音后端

**Files:**
- Create: `src/pipeline/tts.py`
- Test: `tests/test_tts.py`

**Interfaces:**
- Consumes: 无。
- Produces: 协议 `TtsBackend`，方法 `synthesize(text: str, dest_dir: Path, name: str) -> Path`。
- Produces: 异常 `TtsError(RuntimeError)`。
- Produces: `KokoroTtsBackend(voice: str = "zm_yunjian", speed: float = 1.0, hf_endpoint: str = "https://hf-mirror.com", pipeline_factory: Callable[[], object] | None = None)`，实现 `TtsBackend`，输出 24000 采样的单声道 WAV。

选型说明：里程碑 1 的配音用 Kokoro。已核实三点：它支持 Python 3.12，Windows 上的依赖都有安装包，`KPipeline(lang_code="z")` 是它的中文入口。它只有 82M 参数，跑在 CPU 上，不和视频模型抢 16G 显存。它只适合用来打通管线，成片最终用什么音色留到里程碑 2 按试听结果决定。首次使用会从模型仓库下载权重，国内通过 `hf_endpoint` 指向镜像。kokoro 自身只带英文前端，中文前端要靠 pyproject 依赖里的 `misaki[zh]`，少了它 `KPipeline(lang_code="z")` 会在导入时报 `No module named 'ordered_set'`。

许可提醒：这份计划只核实了 Kokoro 能在 Windows 和 Python 3.12 上安装、接口可用，没有核实它的权重许可和训练数据对商用的限制。里程碑 1 的成片不对外发布，所以不阻塞；但在用它的声音发布任何内容之前，必须先读一遍模型仓库的许可说明，或者换成许可明确的方案。

- [ ] **Step 1: 写失败的测试 tests/test_tts.py**

```python
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from pipeline.tts import KokoroTtsBackend, TtsError


class FakePipeline:
    """按调用参数返回固定音频块的 Kokoro 流水线替身。"""

    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def __call__(self, text, voice, speed):
        self.calls.append({"text": text, "voice": voice, "speed": speed})
        return [("文", "拼音", chunk) for chunk in self.chunks]


def test_synthesize_joins_chunks_into_one_wav(tmp_path):
    pipeline = FakePipeline([np.zeros(2400), np.full(2400, 0.5)])

    path = KokoroTtsBackend(voice="zm_yunxi", speed=1.1, pipeline_factory=lambda: pipeline).synthesize(
        "东海之外，有座青丘山。", tmp_path, "voice_001"
    )

    data, sample_rate = sf.read(path)
    assert path == tmp_path / "voice_001.wav"
    assert (sample_rate, len(data)) == (24000, 4800)
    assert data[2400] == pytest.approx(0.5, abs=1e-3)
    assert pipeline.calls == [{"text": "东海之外，有座青丘山。", "voice": "zm_yunxi", "speed": 1.1}]


def test_pipeline_is_built_once_and_reused(tmp_path):
    built = []
    pipeline = FakePipeline([np.zeros(2400)])
    backend = KokoroTtsBackend(pipeline_factory=lambda: built.append(1) or pipeline)

    backend.synthesize("第一句", tmp_path, "voice_001")
    backend.synthesize("第二句", tmp_path, "voice_002")

    assert built == [1]


def test_synthesize_fails_when_nothing_is_generated(tmp_path):
    backend = KokoroTtsBackend(pipeline_factory=lambda: FakePipeline([]))

    with pytest.raises(TtsError, match="没有合成出任何音频"):
        backend.synthesize("旁白", tmp_path, "voice_001")


def test_real_pipeline_uses_chinese_frontend_and_mirror(monkeypatch):
    created = {}

    def fake_pipeline(**options):
        created.update(options)
        return FakePipeline([np.zeros(2400)])

    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KPipeline=fake_pipeline))
    backend = KokoroTtsBackend(hf_endpoint="https://hf-mirror.com")

    assert backend._build_pipeline() is not None

    assert created == {"lang_code": "z"}
    assert os.environ["HF_ENDPOINT"] == "https://hf-mirror.com"


@pytest.mark.integration
def test_real_kokoro_speaks_chinese(tmp_path):
    path = KokoroTtsBackend().synthesize("东海之外，有一座青丘山。", tmp_path, "voice_001")

    data, sample_rate = sf.read(path)
    assert len(data) / sample_rate > 1.0
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_tts.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.tts'`。

- [ ] **Step 3: 写 src/pipeline/tts.py**

```python
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
```

- [ ] **Step 4: 确认测试通过**

Run: `uv run pytest tests/test_tts.py -v`
Expected: PASS，4 个用例通过，1 个标记为 `integration` 的用例被排除。

- [ ] **Step 5: 用真实模型验证 Kokoro 能在本机说中文**

Run: `uv run pytest tests/test_tts.py -v -m integration`
Expected: PASS，1 个用例。首次运行会下载模型权重，需要几分钟。

如果这一步因为模型下载失败而失败，先确认能否访问 `https://hf-mirror.com`，再重试。如果因为安装问题失败，把安装依赖时的报错原样带给计划作者，不要自行更换配音方案。

---

### Task 9: 状态库

**Files:**
- Create: `src/pipeline/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: Task 2 的 `Episode`、`episode_to_json`。
- Produces: 异常 `StoreError(LookupError)`。
- Produces: 冻结数据类 `EpisodeRecord(episode_id: str, topic: str, status: str, spec_json: str, error: str, created_at: str, updated_at: str)`。
- Produces: 冻结数据类 `ShotRecord(shot_no: int, narration: str, image_prompt: str, motion_prompt: str, status: str, keyframe_path: str, clip_path: str, voice_path: str, seed: int, attempts: int, error: str)`。
- Produces: `Store(db_path: Path)`，方法 `create_episode(topic: str, episode_id: str) -> EpisodeRecord`、`save_script(episode_id: str, episode: Episode) -> None`、`get_episode(episode_id: str) -> EpisodeRecord`、`list_episodes() -> list[EpisodeRecord]`、`get_shots(episode_id: str) -> list[ShotRecord]`、`update_shot(episode_id: str, shot_no: int, **fields) -> None`、`set_episode_status(episode_id: str, status: str, error: str = "") -> None`。
- 状态取值约定：视频为 `created`、`scripted`、`rendering`、`done`、`failed`；镜头为 `pending`、`keyframed`、`video_done`、`voiced`、`failed`。

- [ ] **Step 1: 写失败的测试 tests/test_store.py**

```python
import pytest

from pipeline.episode import Episode, Shot
from pipeline.store import Store, StoreError


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "pipeline.db")


def make_episode(shot_count=2, episode_id="e1") -> Episode:
    """造一条合法视频，供各个用例按需取用。

    @param shot_count: 镜头数
    @param episode_id: 视频编号
    @return: 合法的视频
    """
    shots = [
        Shot(shot_no=number, narration=f"第{number}句旁白", image_prompt="画面", motion_prompt="推近")
        for number in range(1, shot_count + 1)
    ]
    return Episode(episode_id=episode_id, title="青丘九尾狐", topic="青丘山的九尾狐", shots=shots)


def test_create_episode_starts_in_created_state(tmp_path):
    record = make_store(tmp_path).create_episode("青丘山的九尾狐", "e1")

    assert (record.status, record.topic, record.error) == ("created", "青丘山的九尾狐", "")


def test_save_script_fills_shots_as_pending(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")

    store.save_script("e1", make_episode(2))

    assert store.get_episode("e1").status == "scripted"
    shots = store.get_shots("e1")
    assert [(shot.shot_no, shot.status, shot.narration) for shot in shots] == [(1, "pending", "第1句旁白"), (2, "pending", "第2句旁白")]


def test_save_script_twice_replaces_shots(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")
    store.save_script("e1", make_episode(2))

    store.save_script("e1", make_episode(3))

    assert [shot.shot_no for shot in store.get_shots("e1")] == [1, 2, 3]


def test_save_script_rejects_mismatched_episode_id(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")

    with pytest.raises(ValueError, match="episode_id 不一致"):
        store.save_script("other", make_episode())


def test_update_shot_changes_only_allowed_columns(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")
    store.save_script("e1", make_episode())

    store.update_shot("e1", 1, status="keyframed", keyframe_path="keyframe_001.png", seed=42, attempts=1, error="")

    shot = store.get_shots("e1")[0]
    assert (shot.status, shot.keyframe_path, shot.seed, shot.attempts) == ("keyframed", "keyframe_001.png", 42, 1)
    with pytest.raises(ValueError, match="不能更新这些列"):
        store.update_shot("e1", 1, narration="改剧本")


def test_set_episode_status_records_error(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("青丘山的九尾狐", "e1")

    store.set_episode_status("e1", "failed", error="这些镜头生成失败：[2]")
    store.set_episode_status("e1", "rendering")

    assert store.get_episode("e1").status == "rendering"
    assert store.get_episode("e1").error == ""
    store.set_episode_status("e1", "failed", error="又失败了")
    assert store.get_episode("e1").error == "又失败了"


def test_missing_records_raise_store_error(tmp_path):
    store = make_store(tmp_path)

    with pytest.raises(StoreError, match="找不到视频"):
        store.get_episode("nope")
    with pytest.raises(StoreError, match="找不到视频"):
        store.save_script("nope", make_episode(episode_id="nope"))
    assert store.get_shots("nope") == []
    with pytest.raises(StoreError, match="找不到镜头"):
        store.update_shot("nope", 1, status="failed")


def test_list_episodes_orders_newest_first(tmp_path):
    store = make_store(tmp_path)
    store.create_episode("第一条", "e1")
    store.create_episode("第二条", "e2")

    assert [record.episode_id for record in store.list_episodes()] == ["e2", "e1"]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.store'`。

- [ ] **Step 3: 写 src/pipeline/store.py**

```python
"""状态库：用 SQLite 记录每条视频和每个镜头的阶段状态。"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pipeline.episode import Episode, episode_to_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    topic      TEXT NOT NULL,
    status     TEXT NOT NULL,
    spec_json  TEXT NOT NULL DEFAULT '',
    error      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shots (
    episode_id    TEXT NOT NULL REFERENCES episodes(episode_id),
    shot_no       INTEGER NOT NULL,
    narration     TEXT NOT NULL,
    image_prompt  TEXT NOT NULL,
    motion_prompt TEXT NOT NULL,
    status        TEXT NOT NULL,
    keyframe_path TEXT NOT NULL DEFAULT '',
    clip_path     TEXT NOT NULL DEFAULT '',
    voice_path    TEXT NOT NULL DEFAULT '',
    seed          INTEGER NOT NULL DEFAULT 0,
    attempts      INTEGER NOT NULL DEFAULT 0,
    error         TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (episode_id, shot_no)
);
"""

SHOT_COLUMNS = ("status", "keyframe_path", "clip_path", "voice_path", "seed", "attempts", "error")


class StoreError(LookupError):
    """状态库里找不到对应的记录。

    @author zxt
    @date 2026-11-25
    """


@dataclass(frozen=True)
class EpisodeRecord:
    """一条视频在状态库里的当前状态。

    @author zxt
    @date 2026-11-25
    """

    episode_id: str
    topic: str
    status: str
    spec_json: str
    error: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ShotRecord:
    """一个镜头在状态库里的当前状态。

    @author zxt
    @date 2026-11-25
    """

    shot_no: int
    narration: str
    image_prompt: str
    motion_prompt: str
    status: str
    keyframe_path: str
    clip_path: str
    voice_path: str
    seed: int
    attempts: int
    error: str


def _now() -> str:
    """
    @return: 当前时间，形如 2026-11-25 14:30:05
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Store:
    """SQLite 状态库。每次操作独立建立连接，后台线程和 Web 请求线程可以安全共用。

    @author zxt
    @date 2026-11-25
    """

    def __init__(self, db_path: Path):
        """
        @param db_path: 数据库文件路径，不存在时自动创建
        """
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        """
        @return: 新建的数据库连接
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        # SQLite 默认不检查外键，表结构里声明的引用不会生效，这里每次连接都打开
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_episode(self, topic: str, episode_id: str) -> EpisodeRecord:
        """新建一条处于 created 状态的视频记录。

        @param topic: 视频主题
        @param episode_id: 视频编号
        @return: 新建的视频记录
        """
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO episodes (episode_id, topic, status, created_at, updated_at) VALUES (?, ?, 'created', ?, ?)",
                (episode_id, topic, now, now),
            )
        return self.get_episode(episode_id)

    def save_script(self, episode_id: str, episode: Episode) -> None:
        """保存分镜脚本：写入整条 JSON，并重建它的镜头行。重复调用以最后一次为准。

        @param episode_id: 视频编号
        @param episode: 分镜脚本
        """
        if episode.episode_id != episode_id:
            raise ValueError(f"episode_id 不一致：路径上是 {episode_id}，脚本里是 {episode.episode_id}")
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE episodes SET spec_json = ?, status = 'scripted', error = '', updated_at = ? WHERE episode_id = ?",
                (episode_to_json(episode), _now(), episode_id),
            )
            if cursor.rowcount == 0:
                raise StoreError(f"找不到视频 {episode_id}")
            conn.execute("DELETE FROM shots WHERE episode_id = ?", (episode_id,))
            conn.executemany(
                "INSERT INTO shots (episode_id, shot_no, narration, image_prompt, motion_prompt, status) "
                "VALUES (?, ?, ?, ?, ?, 'pending')",
                [
                    (episode_id, shot.shot_no, shot.narration, shot.image_prompt, shot.motion_prompt)
                    for shot in episode.shots
                ],
            )

    def get_episode(self, episode_id: str) -> EpisodeRecord:
        """
        @param episode_id: 视频编号
        @return: 视频记录
        """
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,)).fetchone()
        if row is None:
            raise StoreError(f"找不到视频 {episode_id}")
        return EpisodeRecord(**dict(row))

    def list_episodes(self) -> list[EpisodeRecord]:
        """
        @return: 全部视频记录，新创建的排在前面
        """
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM episodes ORDER BY created_at DESC, rowid DESC").fetchall()
        return [EpisodeRecord(**dict(row)) for row in rows]

    def get_shots(self, episode_id: str) -> list[ShotRecord]:
        """查询一条视频的全部镜头。

        shots 表比 ShotRecord 多一个 episode_id 列，所以这里按列名查询，不用 SELECT *。

        @param episode_id: 视频编号
        @return: 该视频的全部镜头，按镜号升序
        """
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT shot_no, narration, image_prompt, motion_prompt, status, keyframe_path, "
                "clip_path, voice_path, seed, attempts, error FROM shots WHERE episode_id = ? ORDER BY shot_no",
                (episode_id,),
            ).fetchall()
        return [ShotRecord(**dict(row)) for row in rows]

    def update_shot(self, episode_id: str, shot_no: int, **fields) -> None:
        """更新镜头的若干列，只允许改状态、产物路径、种子、尝试次数和错误信息。

        @param episode_id: 视频编号
        @param shot_no: 镜号
        @param fields: 要更新的列和值
        """
        unknown = sorted(set(fields) - set(SHOT_COLUMNS))
        if unknown:
            raise ValueError(f"不能更新这些列：{unknown}")
        if not fields:
            return
        assignments = ", ".join(f"{column} = ?" for column in fields)
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                f"UPDATE shots SET {assignments} WHERE episode_id = ? AND shot_no = ?",
                (*fields.values(), episode_id, shot_no),
            )
            if cursor.rowcount == 0:
                raise StoreError(f"找不到镜头：视频 {episode_id} 第 {shot_no} 镜")

    def set_episode_status(self, episode_id: str, status: str, error: str = "") -> None:
        """更新视频的状态；不传 error 时会把之前的错误信息清空。

        @param episode_id: 视频编号
        @param status: 新状态
        @param error: 错误信息，没有则为空串
        """
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE episodes SET status = ?, error = ?, updated_at = ? WHERE episode_id = ?",
                (status, error, _now(), episode_id),
            )
            if cursor.rowcount == 0:
                raise StoreError(f"找不到视频 {episode_id}")
```

- [ ] **Step 4: 确认测试通过**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS，8 个用例。

---

### Task 10: 流程编排

**Files:**
- Create: `src/pipeline/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: Task 2 的 `episode_from_json`；Task 7 的 `ImageGenerator`、`VideoGenerator`；Task 8 的 `TtsBackend`；Task 9 的 `Store`、`EpisodeRecord`、`ShotRecord`。
- Produces: 冻结数据类 `ComposeRequest(clips: list[Path], voices: list[Path], out_path: Path)`。
- Produces: `PipelineRunner(store: Store, images: ImageGenerator, videos: VideoGenerator, voice: TtsBackend, compose_fn: Callable[[ComposeRequest], Path], work_dir: Path, deliver_dir: Path, max_attempts: int = 3)`，公开属性 `store`，方法 `run_episode(episode_id: str) -> EpisodeRecord`。
- 行为约定：`run_episode` 不向外抛业务异常，任何失败都落成 `failed` 状态并写明原因；某个镜头重试后仍失败时，其余镜头继续处理，最后在视频的 `error` 里列出失败的镜号。所有镜头成功时，成片写入 `<work_dir>/<视频编号>/final.mp4`，并复制为 `<deliver_dir>/<视频编号>.mp4`。
- 每个镜头的随机种子是 `种子基数 + 镜号 * 100 + 第几次尝试 - 1`，同一条视频的种子基数由视频编号决定，所以重跑同一条视频时种子可复现。

- [ ] **Step 1: 写失败的测试 tests/test_runner.py**

```python
from pathlib import Path

import pytest

from pipeline.fakes import FakeImageGenerator, FakeTtsBackend, FakeVideoGenerator, fake_episode
from pipeline.runner import PipelineRunner
from pipeline.store import Store


class FlakyImages:
    """对指定画面描述先失败若干次的替身，用来验证换种子重试。"""

    def __init__(self, prompts_that_fail=(), failures=1):
        self.prompts_that_fail = set(prompts_that_fail)
        self.failures = failures
        self.seeds = []

    def generate_image(self, prompt, seed, dest_dir, name):
        self.seeds.append(seed)
        if prompt in self.prompts_that_fail and self.failures > 0:
            self.failures -= 1
            raise RuntimeError("显存不足")
        return FakeImageGenerator().generate_image(prompt, seed, dest_dir, name)


@pytest.fixture
def harness(tmp_path, ffmpeg):
    """建好一条 3 镜视频的状态库，返回用于装配 runner 的函数、状态库、合成调用的记录和临时目录。"""
    store = Store(tmp_path / "pipeline.db")
    store.create_episode("青丘山的九尾狐", "e1")
    store.save_script("e1", fake_episode("青丘山的九尾狐", "e1", 3))
    compose_calls = []

    def fake_compose(request):
        compose_calls.append(request)
        request.out_path.write_bytes(b"mp4")
        return request.out_path

    def build(images=None, compose_fn=fake_compose):
        return PipelineRunner(
            store=store,
            images=images or FakeImageGenerator(),
            videos=FakeVideoGenerator(ffmpeg),
            voice=FakeTtsBackend(),
            compose_fn=compose_fn,
            work_dir=tmp_path / "work",
            deliver_dir=tmp_path / "deliver",
        )

    return build, store, compose_calls, tmp_path


def test_run_episode_delivers_video_with_every_shot_voiced(harness):
    build, store, compose_calls, tmp_path = harness

    record = build().run_episode("e1")

    assert record.status == "done"
    assert (tmp_path / "deliver" / "e1.mp4").read_bytes() == b"mp4"
    shots = store.get_shots("e1")
    assert [shot.status for shot in shots] == ["voiced"] * 3
    for shot in shots:
        assert Path(shot.keyframe_path).is_file()
        assert Path(shot.clip_path).is_file()
        assert Path(shot.voice_path).is_file()
        assert shot.seed != 0
        assert shot.attempts == 1
    request = compose_calls[0]
    assert [path.name for path in request.clips] == ["shot_001.mp4", "shot_002.mp4", "shot_003.mp4"]
    assert [path.name for path in request.voices] == ["voice_001.wav", "voice_002.wav", "voice_003.wav"]
    assert request.out_path == tmp_path / "work" / "e1" / "final.mp4"


def test_run_episode_retries_failed_shot_with_a_new_seed(harness):
    build, store, _, _ = harness
    images = FlakyImages(prompts_that_fail={"测试画面2"}, failures=1)

    record = build(images=images).run_episode("e1")

    assert record.status == "done"
    assert store.get_shots("e1")[1].status == "voiced"
    assert len(images.seeds) == 4
    assert images.seeds[2] - images.seeds[1] == 1


def test_run_episode_marks_failed_shot_and_continues_with_the_rest(harness):
    build, store, compose_calls, _ = harness
    images = FlakyImages(prompts_that_fail={"测试画面2"}, failures=99)

    record = build(images=images).run_episode("e1")

    assert record.status == "failed"
    assert record.error == "这些镜头生成失败：[2]"
    assert [shot.status for shot in store.get_shots("e1")] == ["voiced", "failed", "voiced"]
    assert "重试 3 次仍失败" in store.get_shots("e1")[1].error
    assert compose_calls == []


def test_run_episode_reports_compose_failure(harness):
    build, _, _, _ = harness

    def broken_compose(request):
        raise RuntimeError("磁盘已满")

    record = build(compose_fn=broken_compose).run_episode("e1")

    assert record.status == "failed"
    assert "磁盘已满" in record.error


def test_run_episode_refuses_episode_without_script(tmp_path):
    store = Store(tmp_path / "pipeline.db")
    store.create_episode("青丘山的九尾狐", "e9")
    runner = PipelineRunner(
        store=store,
        images=FakeImageGenerator(),
        videos=None,
        voice=None,
        compose_fn=None,
        work_dir=tmp_path,
        deliver_dir=tmp_path,
    )

    record = runner.run_episode("e9")

    assert record.status == "failed"
    assert "还没有分镜脚本" in record.error


def test_run_episode_uses_the_same_seeds_for_the_same_episode_id(harness):
    build, store, _, tmp_path = harness
    first = build()
    first.run_episode("e1")
    seeds_before = [shot.seed for shot in store.get_shots("e1")]

    other_store = Store(tmp_path / "second.db")
    other_store.create_episode("青丘山的九尾狐", "e1")
    other_store.save_script("e1", fake_episode("青丘山的九尾狐", "e1", 3))
    second = PipelineRunner(
        store=other_store,
        images=FakeImageGenerator(),
        videos=first.videos,
        voice=FakeTtsBackend(),
        compose_fn=first.compose_fn,
        work_dir=tmp_path / "work-second",
        deliver_dir=tmp_path / "deliver-second",
    )
    second.run_episode("e1")

    assert [shot.seed for shot in other_store.get_shots("e1")] == seeds_before
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.runner'`。

- [ ] **Step 3: 写 src/pipeline/runner.py**

```python
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
```

- [ ] **Step 4: 确认测试通过**

Run: `uv run pytest tests/test_runner.py -v`
Expected: PASS，6 个用例。

---

### Task 11: 本机网页

**Files:**
- Create: `src/pipeline/web.py`
- Create: `src/pipeline/templates/index.html`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: Task 2 的 `new_episode_id`；Task 9 的 `Store`、`EpisodeRecord`、`StoreError`。
- Produces: `create_app(store: Store, work_dir: Path, submit: Callable[[str, str, int], None]) -> FastAPI`。
- 接口约定：`GET /` 返回页面；`POST /api/episodes` 收 `{"topic": "...", "shot_count": 2}`，返回 202 和 `{"episode_id": "..."}`，主题为空返回 400，上一条还没跑完返回 409；`GET /api/episodes` 返回全部视频的状态列表；`GET /api/episodes/{episode_id}` 返回单条状态；`GET /api/episodes/{episode_id}/video` 返回成片，没有成片时 404。
- 单条状态的结构：`{"episode_id", "topic", "status", "error", "shots": [{"shot_no", "status", "error"}]}`。
- `submit` 在后台线程里执行，参数是（视频编号, 主题, 镜头数）。同一时间只允许一条视频在跑，因为显卡只有一块。

- [ ] **Step 1: 写失败的测试 tests/test_web.py**

```python
import threading
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from pipeline.compose import compose
from pipeline.fakes import FakeImageGenerator, FakeTtsBackend, FakeVideoGenerator, fake_episode
from pipeline.runner import PipelineRunner
from pipeline.store import Store
from pipeline.web import create_app


def wait_until_finished(client, episode_id, timeout=120):
    """轮询直到这条视频离开渲染中的状态。

    @param client: 测试用的接口客户端
    @param episode_id: 视频编号
    @param timeout: 最长等待秒数
    @return: 这条视频最后一份状态
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/episodes/{episode_id}").json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(0.2)
    raise AssertionError(f"等待 {episode_id} 超时，最后的状态是 {data}")


def test_submission_runs_to_done_and_serves_video(tmp_path, ffmpeg):
    store = Store(tmp_path / "pipeline.db")

    def submit(episode_id, topic, shot_count):
        runner = PipelineRunner(
            store=store,
            images=FakeImageGenerator(),
            videos=FakeVideoGenerator(ffmpeg),
            voice=FakeTtsBackend(),
            compose_fn=lambda request: compose(request.clips, request.voices, request.out_path, ffmpeg, width=128, height=224),
            work_dir=tmp_path / "work",
            deliver_dir=tmp_path / "deliver",
        )
        runner.store.save_script(episode_id, fake_episode(topic, episode_id, shot_count))
        runner.run_episode(episode_id)

    app = create_app(store, tmp_path / "work", submit)
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "AI 视频管线" in page.text

        created = client.post("/api/episodes", json={"topic": "青丘山的九尾狐", "shot_count": 2})
        assert created.status_code == 202
        episode_id = created.json()["episode_id"]

        data = wait_until_finished(client, episode_id)

        assert data["status"] == "done", data
        assert data["topic"] == "青丘山的九尾狐"
        assert [shot["status"] for shot in data["shots"]] == ["voiced", "voiced"]
        assert [record["episode_id"] for record in client.get("/api/episodes").json()] == [episode_id]

        video = client.get(f"/api/episodes/{episode_id}/video")
        assert video.status_code == 200
        assert video.headers["content-type"].startswith("video/mp4")
        assert b"ftyp" in video.content[:16]


def test_blank_topic_is_rejected(tmp_path):
    app = create_app(Store(tmp_path / "pipeline.db"), tmp_path / "work", lambda *args: None)
    with TestClient(app) as client:
        response = client.post("/api/episodes", json={"topic": "   "})

        assert response.status_code == 400


def test_second_submission_is_rejected_while_pipeline_is_busy(tmp_path):
    started = threading.Event()
    release = threading.Event()

    def submit(episode_id, topic, shot_count):
        started.set()
        release.wait(timeout=10)

    app = create_app(Store(tmp_path / "pipeline.db"), tmp_path / "work", submit)
    with TestClient(app) as client:
        assert client.post("/api/episodes", json={"topic": "青丘山的九尾狐"}).status_code == 202
        assert started.wait(timeout=5)

        busy = client.post("/api/episodes", json={"topic": "烛龙"})

        assert busy.status_code == 409
        release.set()


def test_background_failure_is_recorded_as_failed_status(tmp_path):
    store = Store(tmp_path / "pipeline.db")

    def submit(episode_id, topic, shot_count):
        raise RuntimeError("后台出了意外")

    app = create_app(store, tmp_path / "work", submit)
    with TestClient(app) as client:
        episode_id = client.post("/api/episodes", json={"topic": "青丘山的九尾狐"}).json()["episode_id"]

        data = wait_until_finished(client, episode_id)

        assert data["status"] == "failed"
        assert "后台出了意外" in data["error"]


def test_unknown_episode_and_missing_video_return_404(tmp_path):
    app = create_app(Store(tmp_path / "pipeline.db"), tmp_path / "work", lambda *args: None)
    with TestClient(app) as client:
        assert client.get("/api/episodes/20261125-143005-a1b2").status_code == 404
        assert client.get("/api/episodes/not-an-id").status_code == 404
        assert client.get("/api/episodes/20261125-143005-a1b2/video").status_code == 404


def test_lock_is_released_when_the_record_cannot_be_created(tmp_path):
    store = Store(tmp_path / "pipeline.db")
    app = create_app(store, tmp_path / "work", lambda *args: None)
    with TestClient(app) as client:
        with patch.object(store, "create_episode", side_effect=RuntimeError("数据库只读")):
            failed = client.post("/api/episodes", json={"topic": "青丘山的九尾狐"})

        assert failed.status_code == 500
        assert "提交失败" in failed.json()["detail"]

        # 记录没建成时锁必须已经还回去，下一次提交不能被误判成"管线正忙"
        assert client.post("/api/episodes", json={"topic": "青丘山的九尾狐"}).status_code == 202
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_web.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'pipeline.web'`。

- [ ] **Step 3: 写 src/pipeline/web.py**

```python
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
```

- [ ] **Step 4: 写 src/pipeline/templates/index.html**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>AI 视频管线</title>
  <style>
    body { font-family: system-ui, "Microsoft YaHei", sans-serif; max-width: 760px; margin: 24px auto; padding: 0 16px; color: #222; }
    form { display: flex; gap: 8px; }
    input[type=text] { flex: 1; padding: 8px; }
    input[type=number] { width: 90px; padding: 8px; }
    button { padding: 8px 16px; }
    .status { margin-top: 16px; padding: 8px 12px; background: #f3f4f6; border-radius: 6px; white-space: pre-wrap; }
    ul { padding-left: 20px; }
    video { width: 100%; max-width: 360px; margin-top: 16px; background: #000; }
  </style>
</head>
<body>
  <h1>AI 视频管线</h1>
  <form id="form">
    <input id="topic" type="text" placeholder="输入主题，例如：青丘山的九尾狐" required>
    <input id="shots" type="number" min="1" max="40" placeholder="镜头数，必填" required>
    <button type="submit">生成</button>
  </form>
  <div id="message" class="status">输入主题后点击生成，页面会自动刷新进度。</div>
  <ul id="shot-list"></ul>
  <video id="player" controls hidden></video>
  <script>
    const form = document.getElementById('form');
    const message = document.getElementById('message');
    const shots = document.getElementById('shot-list');
    const player = document.getElementById('player');
    let timer = null;

    async function submit(event) {
      event.preventDefault();
      const shotCount = Number(document.getElementById('shots').value) || 0;
      const response = await fetch('/api/episodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: document.getElementById('topic').value, shot_count: shotCount }),
      });
      const data = await response.json();
      if (!response.ok) {
        message.textContent = data.detail;
        return;
      }
      player.hidden = true;
      clearInterval(timer);
      timer = setInterval(() => refresh(data.episode_id), 2000);
      await refresh(data.episode_id);
    }

    async function refresh(episodeId) {
      const response = await fetch('/api/episodes/' + episodeId);
      if (!response.ok) {
        clearInterval(timer);
        message.textContent = '查询失败：' + response.status;
        return;
      }
      const data = await response.json();
      message.textContent = '状态：' + data.status + (data.error ? '\n' + data.error : '');
      shots.replaceChildren(...data.shots.map((shot) => {
        const item = document.createElement('li');
        item.textContent = '第 ' + shot.shot_no + ' 镜：' + shot.status + (shot.error ? '（' + shot.error + '）' : '');
        return item;
      }));
      if (data.status === 'done' || data.status === 'failed') {
        clearInterval(timer);
        if (data.status === 'done') {
          player.src = '/api/episodes/' + episodeId + '/video';
          player.hidden = false;
        }
      }
    }

    form.addEventListener('submit', submit);
  </script>
</body>
</html>
```

- [ ] **Step 5: 确认测试通过**

Run: `uv run pytest tests/test_web.py -v`
Expected: PASS，6 个用例。

- [ ] **Step 6: 在浏览器里实际走一遍页面**

单元测试只验证了接口，页面的交互要亲眼看。这一步需要命令行入口，放在 Task 12 完成后做，见 Task 12 的 Step 6。

---

### Task 12: 命令行入口与工作流说明

**Files:**
- Create: `src/pipeline/__main__.py`
- Create: `workflows/README.md`、`workflows/keyframe.binding.example.json`、`workflows/wan_i2v.binding.example.json`、`workflows/minimax_i2v.binding.example.json`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: 前面全部任务的对外的类和函数。
- Produces: `build_runner(settings: Settings, fakes: bool) -> PipelineRunner`、`build_script_writer(settings: Settings, fakes: bool) -> Callable[[str, str, int], Episode]`、`make_submit(settings: Settings, fakes: bool) -> Callable[[str, str, int], None]`、`main(argv: list[str] | None = None) -> int`。
- Produces: 命令行入口，通过 `uv run pipeline <子命令>` 调用，四个子命令：`run --topic <主题> [--shot-count N] [--fakes]`、`serve [--port 8000] [--fakes]`、`check-workflows`、`tts-sample [--text ...] [--out ...]`。
- 真实运行需要的文件（Task 14 在家里电脑上生成，本任务只放样例和说明）：`workflows/keyframe_api.json`、`workflows/keyframe.binding.json`，加上至少一个引擎的 `<引擎>_i2v_api.json` 和同名 `.binding.json`（引擎是 wan 或 minimax，用哪个由 `.env` 的 `VIDEO_ENGINE` 决定）。`check-workflows` 会校验 keyframe 和所有已存在的引擎文件，`VIDEO_ENGINE` 指向的那份必须提供。

- [ ] **Step 1: 写失败的测试 tests/test_cli.py**

```python
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pipeline.__main__ as entry
from pipeline.tts import TtsError

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflows"


def run_pipeline(cwd, *args, extra_env=None):
    """在指定目录下运行命令行入口，返回跑完的进程。"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **(extra_env or {})}
    return subprocess.run(
        [sys.executable, "-m", "pipeline", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )


def test_fakes_run_delivers_a_real_video(tmp_path):
    result = run_pipeline(tmp_path, "run", "--topic", "青丘山的九尾狐", "--shot-count", "2", "--fakes")

    assert result.returncode == 0, result.stdout + result.stderr
    episode_id, status = result.stdout.strip().splitlines()[-1].split()
    assert status == "done"
    delivered = tmp_path / "data" / "deliver" / f"{episode_id}.mp4"
    assert delivered.is_file()
    assert delivered.stat().st_size > 1000


def test_run_fails_cleanly_without_api_key(tmp_path):
    result = run_pipeline(tmp_path, "run", "--topic", "青丘山的九尾狐", extra_env={"DEEPSEEK_API_KEY": ""})

    assert result.returncode == 1
    assert "DEEPSEEK_API_KEY" in result.stderr


def test_check_workflows_accepts_fixture_workflows(tmp_path):
    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(FIXTURES)})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "seed -> 节点 3（KSampler）.seed" in result.stdout


def test_check_workflows_reports_broken_binding(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "wan_i2v_api.json", "wan_i2v.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)
    (workflows / "keyframe.binding.json").write_text('{"seed": ["99", "seed"]}', encoding="utf-8")

    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows)})

    assert result.returncode == 1
    assert "不存在的节点 99" in result.stderr


def test_check_workflows_reports_missing_required_binding(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "wan_i2v_api.json", "keyframe.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)
    (workflows / "wan_i2v.binding.json").write_text(
        '{"positive_prompt": ["6", "text"], "negative_prompt": ["7", "text"], "seed": ["3", "seed"], '
        '"width": ["5", "width"], "height": ["5", "height"], "length": ["5", "length"]}',
        encoding="utf-8",
    )

    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows)})

    assert result.returncode == 1
    assert "缺少必填参数 ['start_image']" in result.stderr


def test_check_workflows_lists_optional_params_that_are_not_bound(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "wan_i2v_api.json", "wan_i2v.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)
    (workflows / "keyframe.binding.json").write_text('{"positive_prompt": ["6", "text"]}', encoding="utf-8")

    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows)})

    assert result.returncode == 0
    assert "未绑定的可选参数" in result.stdout
    assert "negative_prompt" in result.stdout


def test_check_workflows_rejects_unknown_binding_keys(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "wan_i2v_api.json", "wan_i2v.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)
    (workflows / "keyframe.binding.json").write_text(
        '{"positive_prompt": ["6", "text"], "noise_seed": ["3", "seed"]}',
        encoding="utf-8",
    )

    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows)})

    assert result.returncode == 1
    assert "不认识的参数名 ['noise_seed']" in result.stderr


def test_check_workflows_requires_the_configured_engine(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "keyframe.binding.json", "minimax_i2v_api.json", "minimax_i2v.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)

    missing = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows), "VIDEO_ENGINE": "wan"})
    ok = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows), "VIDEO_ENGINE": "minimax"})

    assert missing.returncode == 1
    assert "wan_i2v" in missing.stderr
    assert "必须提供" in missing.stderr
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_run_rejects_unknown_video_engine(tmp_path):
    result = run_pipeline(tmp_path, "run", "--topic", "青丘山的九尾狐", "--fakes", extra_env={"VIDEO_ENGINE": "bogus"})

    assert result.returncode == 1
    assert "VIDEO_ENGINE 只能是" in result.stderr


def test_run_reports_setup_failure_without_traceback(tmp_path):
    result = run_pipeline(tmp_path, "run", "--topic", "青丘山的九尾狐", extra_env={"DEEPSEEK_API_KEY": "sk-test"})

    assert result.returncode == 1
    assert result.stdout.strip().endswith("failed")
    assert "读不到工作流文件" in result.stderr
    assert "Traceback" not in result.stderr


def test_tts_sample_reports_failure_in_chinese(tmp_path, monkeypatch, capsys):
    def broken_backend(*args, **kwargs):
        raise TtsError("没有这个音色")

    monkeypatch.setattr(entry, "KokoroTtsBackend", broken_backend)

    code = entry.main(["tts-sample", "--out", str(tmp_path / "sample.wav")])

    assert code == 1
    assert "配音示例失败" in capsys.readouterr().err
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL，全部用例都因为 `No module named pipeline.__main__` 而返回非零退出码（包含新加的 2 个）。

- [ ] **Step 3: 写 src/pipeline/__main__.py**

```python
"""命令行入口：run 生成一条视频，serve 启动本机网页，check-workflows 校验工作流绑定，tts-sample 试听配音。"""

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from pipeline.comfy import ComfyClient, WorkflowError, describe_binding, load_workflow
from pipeline.compose import compose
from pipeline.config import VIDEO_ENGINES, Settings
from pipeline.episode import Episode, new_episode_id
from pipeline.fakes import FakeImageGenerator, FakeTtsBackend, FakeVideoGenerator, fake_episode
from pipeline.ffmpeg import FFmpeg
from pipeline.generators import ComfyImageGenerator, ComfyVideoGenerator
from pipeline.runner import PipelineRunner
from pipeline.script import DeepSeekClient, generate_episode
from pipeline.store import Store
from pipeline.tts import KokoroTtsBackend
from pipeline.web import create_app

WORKFLOW_NAMES = ("keyframe",) + tuple(f"{engine}_i2v" for engine in VIDEO_ENGINES)
REQUIRED_BINDINGS = {"keyframe": {"positive_prompt"}}
OPTIONAL_BINDINGS = {"keyframe": ("negative_prompt", "seed", "width", "height")}
for _engine in VIDEO_ENGINES:
    REQUIRED_BINDINGS[f"{_engine}_i2v"] = {"start_image", "positive_prompt"}
    OPTIONAL_BINDINGS[f"{_engine}_i2v"] = ("negative_prompt", "seed", "width", "height", "length")
ALLOWED_BINDINGS = {name: REQUIRED_BINDINGS[name] | set(OPTIONAL_BINDINGS[name]) for name in WORKFLOW_NAMES}
logger = logging.getLogger(__name__)


def build_runner(settings: Settings, fakes: bool) -> PipelineRunner:
    """按配置装配 runner。

    @param settings: 配置
    @param fakes: 为 True 时全部使用替身，不需要显卡和 ComfyUI
    @return: 装配好的 runner
    """
    ffmpeg = FFmpeg.resolve(settings.ffmpeg_path)
    if fakes:
        images, videos, voice = FakeImageGenerator(), FakeVideoGenerator(ffmpeg), FakeTtsBackend()
    else:
        client = ComfyClient(settings.comfyui_url)
        images = ComfyImageGenerator(
            client,
            load_workflow(settings.workflows_dir, "keyframe"),
            settings.keyframe_negative_prompt,
            settings.keyframe_width,
            settings.keyframe_height,
        )
        videos = ComfyVideoGenerator(
            client,
            load_workflow(settings.workflows_dir, f"{settings.video_engine}_i2v"),
            settings.i2v_negative_prompt,
            settings.i2v_width,
            settings.i2v_height,
            settings.i2v_frames,
        )
        voice = KokoroTtsBackend(settings.tts_voice, hf_endpoint=settings.hf_endpoint)
    return PipelineRunner(
        store=Store(settings.data_dir / "pipeline.db"),
        images=images,
        videos=videos,
        voice=voice,
        compose_fn=lambda request: compose(request.clips, request.voices, request.out_path, ffmpeg),
        work_dir=settings.data_dir / "episodes",
        deliver_dir=settings.deliver_dir,
    )


def build_script_writer(settings: Settings, fakes: bool) -> Callable[[str, str, int], Episode]:
    """返回脚本阶段的函数。

    @param settings: 配置
    @param fakes: 为 True 时返回产出固定内容的替身
    @return: 函数，参数为（主题, 视频编号, 镜头数），返回分镜脚本
    """
    if fakes:
        return lambda topic, episode_id, shot_count: fake_episode(topic, episode_id, shot_count or settings.shot_count)
    client = DeepSeekClient(settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model)

    def write(topic: str, episode_id: str, shot_count: int) -> Episode:
        """
        @param topic: 视频主题
        @param episode_id: 视频编号
        @param shot_count: 镜头数，0 表示用配置里的默认值
        @return: 分镜脚本
        """
        return generate_episode(
            client,
            topic,
            episode_id,
            shot_count or settings.shot_count,
            settings.style_guide,
            settings.prompt_language,
        )

    return write


def make_submit(settings: Settings, fakes: bool) -> Callable[[str, str, int], None]:
    """返回后台回调：写脚本，再跑完整流程。装配或脚本阶段失败时把这条视频标为 failed。

    @param settings: 配置
    @param fakes: 是否使用替身
    @return: 函数，参数为（视频编号, 主题, 镜头数）
    """
    if not fakes and not settings.deepseek_api_key:
        raise RuntimeError("没有配置 DEEPSEEK_API_KEY：请复制 .env.example 为 .env 并填写")
    write_script = build_script_writer(settings, fakes)

    def submit(episode_id: str, topic: str, shot_count: int) -> None:
        """
        @param episode_id: 视频编号
        @param topic: 视频主题
        @param shot_count: 镜头数，0 表示用配置里的默认值
        """
        try:
            runner = build_runner(settings, fakes)
            runner.store.save_script(episode_id, write_script(topic, episode_id, shot_count))
        except Exception as exc:
            # 装配或脚本阶段失败：把这条视频标成失败并写明原因，命令行和网页都不需要再兜底
            Store(settings.data_dir / "pipeline.db").set_episode_status(episode_id, "failed", error=str(exc)[:1000])
            return
        runner.run_episode(episode_id)

    return submit


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    @param argv: 参数列表，默认取进程参数
    @return: 退出码，0 表示成功
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="pipeline", description="依托 ComfyUI 的视频生成流水线")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="生成一条视频")
    run.add_argument("--topic", required=True, help="视频主题")
    run.add_argument("--shot-count", type=int, default=0, help="镜头数，0 表示用配置里的默认值")
    run.add_argument("--fakes", action="store_true", help="用替身代替模型和 ComfyUI，用于冒烟")

    serve = commands.add_parser("serve", help="启动本机网页")
    serve.add_argument("--port", type=int, default=8000, help="端口")
    serve.add_argument("--fakes", action="store_true", help="用替身代替模型和 ComfyUI")

    commands.add_parser("check-workflows", help="校验两份工作流模板及其参数绑定")

    tts = commands.add_parser("tts-sample", help="用真实配音模型合成一段试听音频")
    tts.add_argument("--text", default="东海之外，有一座青丘山。山中藏着一只九尾狐。", help="试听的文本")
    tts.add_argument("--out", default="data/tts_sample.wav", help="输出文件")

    args = parser.parse_args(argv)
    settings = Settings()
    if settings.video_engine not in VIDEO_ENGINES:
        print(f"配置错误：VIDEO_ENGINE 只能是 {'、'.join(VIDEO_ENGINES)}，当前是 {settings.video_engine}", file=sys.stderr)
        return 1

    if args.command == "run":
        store = Store(settings.data_dir / "pipeline.db")
        try:
            # 先装配再建记录：配置有问题时不留一条停在 created 的记录，也不会先去联网
            submit = make_submit(settings, args.fakes)
            episode_id = new_episode_id()
            store.create_episode(args.topic, episode_id)
            submit(episode_id, args.topic, args.shot_count)
        except Exception as exc:
            print(f"运行失败：{exc}", file=sys.stderr)
            return 1
        record = store.get_episode(episode_id)
        print(f"{episode_id} {record.status}")
        if record.error:
            print(record.error, file=sys.stderr)
        return 0 if record.status == "done" else 1

    if args.command == "serve":
        import uvicorn

        try:
            submit = make_submit(settings, args.fakes)
        except Exception as exc:
            print(f"启动失败：{exc}", file=sys.stderr)
            return 1
        app = create_app(Store(settings.data_dir / "pipeline.db"), settings.data_dir / "episodes", submit)
        uvicorn.run(app, host="127.0.0.1", port=args.port)
        return 0

    if args.command == "check-workflows":
        problems: list[str] = []
        default_i2v = f"{settings.video_engine}_i2v"
        for name in WORKFLOW_NAMES:
            api_path = settings.workflows_dir / f"{name}_api.json"
            if not api_path.exists():
                # 文件不存在：keyframe 和当前引擎是必须的，另一个引擎可以晚点再导出
                if name == "keyframe" or name == default_i2v:
                    problems.append(f"{name}：缺少工作流文件 {api_path}（必须提供）")
                else:
                    print(f"[{name}] 未提供，需要时再导出")
                continue
            try:
                spec = load_workflow(settings.workflows_dir, name)
            except WorkflowError as exc:
                problems.append(f"{name}：{exc}")
                continue
            unknown = sorted(set(spec.binding) - ALLOWED_BINDINGS[name])
            if unknown:
                problems.append(f"{name}：绑定表里有管线不认识的参数名 {unknown}")
                continue
            missing = sorted(REQUIRED_BINDINGS[name] - set(spec.binding))
            if missing:
                problems.append(f"{name}：绑定表里缺少必填参数 {missing}")
                continue
            print(f"[{name}]")
            optional_missing = [param for param in OPTIONAL_BINDINGS[name] if param not in spec.binding]
            if optional_missing:
                print(f"  未绑定的可选参数（模板里没有对应输入就不用绑）：{'、'.join(optional_missing)}")
            print("\n".join("  " + line for line in describe_binding(spec)))
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1
        return 0

    out = Path(args.out)
    try:
        path = KokoroTtsBackend(settings.tts_voice, hf_endpoint=settings.hf_endpoint).synthesize(args.text, out.parent, out.stem)
    except Exception as exc:
        # 这个子命令是用来第一次验证配音环境的，失败是常态路径：终端里留完整回溯，方便原样带回去排查
        logger.exception("配音示例合成失败")
        print(f"配音示例失败：{exc}。请检查网络、模型下载，以及 .env 里的 TTS_VOICE 是不是有效的音色名。", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    # 通过 python -m pipeline 启动时才执行入口，返回值作为进程退出码
    sys.exit(main())
```

- [ ] **Step 4: 写 workflows/keyframe.binding.example.json**

```json
{
  "positive_prompt": ["6", "text"],
  "negative_prompt": ["7", "text"],
  "seed": ["3", "seed"],
  "width": ["5", "width"],
  "height": ["5", "height"]
}
```

- [ ] **Step 5: 写两个图生视频绑定表样例**

`workflows/wan_i2v.binding.example.json`（Wan 类模板，参数比较全）：

```json
{
  "start_image": ["10", "image"],
  "positive_prompt": ["6", "text"],
  "negative_prompt": ["7", "text"],
  "seed": ["3", "seed"],
  "width": ["5", "width"],
  "height": ["5", "height"],
  "length": ["5", "length"]
}
```

`workflows/minimax_i2v.binding.example.json`（只暴露提示词和首帧的模板，其余参数不绑）：

```json
{
  "start_image": ["1", "image"],
  "positive_prompt": ["2", "prompt"]
}
```

上面样例里的节点编号只是示意，来自测试用的迷你模板，和真实模板对不上。真实模板的编号按下一步的说明填写。

- [ ] **Step 6: 写 workflows/README.md**

````markdown
# 工作流模板

管线通过 ComfyUI 的 HTTP 接口提交"API 格式"的工作流。文件分三组：

| 文件 | 作用 |
|---|---|
| `keyframe_api.json` | 文生图工作流，给每个镜头出一张关键帧（两个引擎共用） |
| `keyframe.binding.json` | 告诉管线：提示词、种子、宽高分别填到模板的哪个节点的哪个输入 |
| `wan_i2v_api.json` / `wan_i2v.binding.json` | Wan 2.2 的图生视频工作流和绑定表 |
| `minimax_i2v_api.json` / `minimax_i2v.binding.json` | MiniMax 的图生视频工作流和绑定表 |

图生视频两份至少导出一份。用哪份由 `.env` 的 `VIDEO_ENGINE` 决定（`wan` 或 `minimax`）；临时切换不必改配置，在命令前加环境变量即可，例如 `VIDEO_ENGINE=minimax uv run pipeline run --topic "..."`。

真实文件在家里电脑上生成，见实施计划的 Task 14。`*.binding.example.json` 只是格式样例。

## 一、导出 API 格式的工作流

1. 在 ComfyUI 里把工作流调到能正常出结果。
2. 打开设置，启用 Dev Mode（开发者模式）。
3. 在工作流菜单里选 Export (API)。普通导出保存的是界面格式，管线不能用。
4. 文生图的存为 `keyframe_api.json`；图生视频按引擎存为 `wan_i2v_api.json` 或 `minimax_i2v_api.json`，都放在本目录。

两条对所有模板都适用的要求：

- 模板末尾必须有把结果写进输出目录的节点：文生图是 Save Image，图生视频是 Save Video。只有 Preview Image 的模板只产生临时输出，管线会把这一镜当成没有产出而报错。
- 被旁路（bypass）的节点不会被导出。导出前确认要用到的节点都处于启用状态。

不管你用哪个视频模型（Wan、MiniMax 或别的），导出前先弄清两件事：首帧图片从哪个节点的哪个输入传进去（它就是绑定表里的 `start_image`），结果由哪个节点写进输出目录。以下是 Wan 2.2 官方模板的两个常见坑，供参照：

- 它的 Load Image 节点默认是旁路状态，画布上那一组的标题写着 "For i2v, use Ctrl + B to enable"。先选中 Load Image 节点，按 Ctrl+B 取消旁路，再上传图片。
- 不取消旁路的话，运行得到的是纯文生视频，和上传的图片毫无关系；而且导出的 JSON 里没有 LoadImage 节点，下一步校验会报 `start_image 绑定到了不存在的节点`。
- 取消旁路后运行一次，确认视频的第一帧和你上传的图片一致，再导出。

首帧图片不需要手动准备：运行时由管线上传后填进 Load Image 节点。

## 二、填写绑定表

绑定表的每一项是 `"参数名": ["节点编号", "输入名"]`。管线只认识下面这些参数名：

| 参数名 | 填到哪里 |
|---|---|
| `positive_prompt` | 正向提示词编码节点的 `text` |
| `negative_prompt` | 负向提示词编码节点的 `text` |
| `seed` | 采样器或随机噪声节点的种子输入，名字可能是 `seed` 或 `noise_seed` |
| `width`、`height` | latent 节点的宽高输入。文生图模板里它是名称以 `Empty` 开头的节点；Wan 2.2 官方图生视频模板里叫 `Wan22ImageToVideoLatent` |
| `start_image` | Load Image 节点的 `image`（只有 `i2v` 需要） |
| `length` | 和宽高同一个节点的帧数输入（只有 `i2v` 需要） |

必填的参数：`keyframe` 只要 `positive_prompt`；`i2v` 是 `positive_prompt` 和 `start_image`。其余参数（负向提示词、种子、宽高、帧数）要看你的模板暴露了哪些输入：有就绑，没有就不绑，校验命令会把未绑定的可选参数列出来供你核对。管线不认识的参数名也会被校验命令报出来，防止把参数名拼错后静默失效。

查节点编号的办法：在 ComfyUI 的设置里搜索 Node ID，把节点编号角标设为显示，画布上每个节点标题旁就会带上它的编号。也可以直接在导出的 JSON 里按 `class_type` 找：顶层每个键就是节点编号，`CLIPTextEncode` 是提示词节点；latent 节点在文生图模板里名称以 `Empty` 开头，在 Wan 2.2 图生视频模板里是 `Wan22ImageToVideoLatent`。

复制样例为正式文件再改，不要直接改样例：

```bash
cp workflows/keyframe.binding.example.json workflows/keyframe.binding.json
cp workflows/wan_i2v.binding.example.json workflows/wan_i2v.binding.json
cp workflows/minimax_i2v.binding.example.json workflows/minimax_i2v.binding.json
```

## 三、校验

```bash
uv run pipeline check-workflows
```

它会打印每个参数实际绑定到的节点和节点类型，并在绑定指向不存在的节点或输入、缺少必填参数、或者出现管线不认识的参数名时报错。它校验 keyframe 和所有已存在的引擎文件；`VIDEO_ENGINE` 指向的那份必须提供。
````

- [ ] **Step 7: 确认测试通过**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS，11 个用例。

- [ ] **Step 8: 跑一遍全部测试**

Run: `uv run pytest tests/ -v`
Expected: PASS，106 个用例通过，1 个标记为 `integration` 的用例被排除。

- [ ] **Step 9: 在浏览器里实际走一遍页面**

单元测试只验证了接口。页面的交互要在浏览器里亲眼看一次。

Run（在单独的终端里保持运行）: `uv run pipeline serve --fakes --port 8000`
然后用浏览器打开 `http://127.0.0.1:8000/`，按下面的清单逐项确认：

- 页面标题是"AI 视频管线"，有主题输入框、镜头数输入框和"生成"按钮。
- 输入主题"青丘山的九尾狐"，镜头数填 2，点"生成"。
- 进度区先显示"状态：rendering"，下方两条镜头的状态从 pending 依次变成 keyframed、video_done、voiced。
- 十几秒后状态变成 done，页面下方出现视频，时长 10 秒，画面是紫色，有持续的提示音。
- 不填主题直接点"生成"，浏览器自身会拦住，因为输入框是必填的。
- 再提交一条，等它跑完后页面上的视频换成新的一条。
- 看完按 Ctrl+C 停掉服务。

如果执行者没有可用的浏览器，把这一步标记为"需要用户人工确认"并写明原因，不要当作已完成。

---

### Task 13: 开发机全量验证并打包

**Files:**
- 无新增源码。生成一个源码压缩包，放在仓库之外。

**Interfaces:**
- Consumes: Task 1 到 12 的全部产物。
- Produces: `<仓库的上一级目录>/ai-video-pipeline-src.tgz`，供家里电脑解压使用。

为什么不直接推到 GitHub 再在家里拉取：本计划的提交纪律规定只在最后提交一次，而家里电脑的真实运行可能暴露需要修改的问题。用压缩包传递，代码可以保持未提交状态，等全部验收通过后再做那一次提交。

- [ ] **Step 1: 跑全部测试**

Run: `uv run pytest tests/ -v`
Expected: PASS，106 个用例通过，1 个 `integration` 用例被排除。

- [ ] **Step 2: 用命令行跑一次替身模式的完整流程**

Run: `uv run pipeline run --topic "青丘山的九尾狐" --shot-count 2 --fakes`
Expected: 退出码 0，标准输出的最后一行是 `<视频编号> done`；`data/deliver/` 下出现一个大小超过 1000 字节的 mp4。

- [ ] **Step 3: 清理刚才产生的本地数据**

Run: `rm -rf data`
Expected: 没有输出。`data/` 本来就在 `.gitignore` 里，删掉只是不让它进压缩包。

- [ ] **Step 4: 确认没有不该进仓库的东西**

Run: `git status --porcelain`
Expected: 只出现这些条目，且都以 `??` 开头：`docs/`、`src/`、`tests/`、`workflows/`、`.env.example`、`.gitignore`、`pyproject.toml`、`uv.lock`。其中 `.gitignore` 以 ` M` 开头。不能出现 `.env`、`.venv/`、`data/`、任何 mp4 或 wav。

- [ ] **Step 5: 打包**

Run: `tar --exclude=.git --exclude=.superpowers --exclude=.venv --exclude=data --exclude=.env --exclude=__pycache__ --exclude=.pytest_cache --exclude='*.pyc' -czf ../ai-video-pipeline-src.tgz .`
说明: 压缩包生成在仓库的上一级目录。`agents.local.md` 会一起打进去，它是项目约定，家里电脑上也用得上。

Run: `tar -tzf ../ai-video-pipeline-src.tgz | grep -c -E "\.mp4$|\.wav$|(^|/)\.env$|\.venv/|\.pyc$|\.pytest_cache/"`
Expected: `0`。模式里 `(^|/)\.env$` 的括号不能省：包内成员名带 `./` 前缀，只写 `^\.env$` 匹配不到。

---

### Task 14: 家里电脑的环境、里程碑 0、工作流导出与绑定

**Files:**
- Create（在家里电脑的仓库副本里，Task 16 会拷回开发机提交）：`workflows/keyframe_api.json`、`workflows/keyframe.binding.json`，以及你导出的一到两个引擎的 `<引擎>_i2v_api.json` 和同名 `.binding.json`
- Create（同上）：`docs/notes/2026-11-25-m0-m1-实测记录.md`，本任务只填里程碑 0 和配音两部分，Task 15 补其余部分。
- Create（不进仓库）：`.env`

**Interfaces:**
- Consumes: Task 13 的压缩包；Task 12 的 `pipeline check-workflows` 和 `pipeline tts-sample`。
- Produces: 一台能运行管线的家里电脑，以及四个可供提交的工作流文件。

这个任务全部在家里电脑上手工完成，通过远程桌面操作。命令在该电脑的 Git Bash 里、仓库目录的根目录下执行。

每新开一个终端，先做两件事，后面的命令才不会出问题：

```bash
cd /d/ai-video-pipeline      # 换成你解压源码的目录。新开的终端默认落在用户主目录，不在仓库目录里就读不到 .env，也找不到 workflows/
export PYTHONUTF8=1          # Git Bash 里 Python 的输出默认按系统代码页编码，中文的日志和报错会是乱码
```

用 PowerShell 的话不需要第二条，`cd` 也要换成 PowerShell 的写法，例如 `cd D:\ai-video-pipeline`。

- [ ] **Step 1: 准备家里电脑**

- 电源设置里把睡眠改成"从不"。管线跑一条片子要很久，电脑不能中途睡过去。
- 新建目录 `D:\ai-video-pipeline`。路径里不要有中文和空格。
- 把 `ai-video-pipeline-src.tgz` 通过网盘传到家里电脑，解压到这个目录。

- [ ] **Step 2: 安装 uv**

Run（PowerShell）: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
说明：官方脚本下载失败的话，改用 `pip install uv`。装完重新打开终端。

Run: `uv --version`
Expected: 打印出版本号。

- [ ] **Step 3: 写配置**

Run: `cp .env.example .env`
然后编辑 `.env`，填三项：`DEEPSEEK_API_KEY` 填你的密钥；`DELIVER_DIR` 填网盘的同步目录，例如 `D:/Sync/AiPipeline`；`COMFYUI_URL` 保持 `http://127.0.0.1:8188`，除非你的 ComfyUI 用了别的端口。

- [ ] **Step 4: 安装依赖**

Run: `uv sync`
Expected: 结束时没有报错。uv 会为管线单独创建 `.venv`（需要 Python 3.12 时自动下载），按 pyproject 装好依赖，并生成 `uv.lock`。首次要下载 torch 等依赖，耗时较长。ComfyUI 自带的 Python 不受影响。

如果卡在下载 Python，设置环境变量 `UV_PYTHON_INSTALL_MIRROR` 指向一个 GitHub 加速镜像后重试；如果下载依赖很慢，过一会儿重跑一次 `uv sync`，已下载的部分有缓存，会快很多。

- [ ] **Step 5: 确认测试在家里电脑上也全部通过**

Run: `uv run pytest tests/ -v`
Expected: PASS，通过的用例数和 Task 13 记下的一致。

- [ ] **Step 6: 验证配音链路**

Run: `uv run pytest tests/test_tts.py -m integration`
Expected: PASS。首次运行会从镜像下载 Kokoro 的模型权重。

Run: `uv run pipeline tts-sample --out data/tts_sample.wav`
Expected: 打印出 `data/tts_sample.wav`。打开听一遍。

对音色不满意就换。先列出可选的中文音色：

Run: `uv run python -c "import os; os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com'); from huggingface_hub import list_repo_files; print('\n'.join(f for f in list_repo_files('hexgrad/Kokoro-82M', repo_type='model') if f.startswith('voices/z')))"`
说明：列出来的是 `voices/` 下的文件名，音色名是去掉目录和 `.pt` 后缀的部分。

在 `.env` 里加一行 `TTS_VOICE=<音色名>`，重新运行 `tts-sample` 试听。把最终选定的音色记进实测记录。

如果这一步的安装或模型下载失败，把安装依赖或测试的报错原样带回给计划作者，不要自行更换配音方案。

- [ ] **Step 7: 里程碑 0，在自己的生视频模型上实测**

你在家里电脑上已经跑通了文生图、文生视频和图生视频，生视频用的是本地部署的 MiniMax 模型。这一步不是从零开始，而是把你的模型纳入管线的约束里实测。

1. 启动 ComfyUI。
2. 打开你跑通过的那份图生视频工作流，确认三件事：首帧图片从哪个节点的哪个输入传进去（通常是 Load Image 的 image，它就是后面绑定表里的 start_image）；运行时首帧确实生效，生成的视频第一帧就是你给的图；结果由哪个节点写进输出目录，Save Video 或等价的保存节点，只有预览节点的不行。
3. 宽高和时长以你的模型支持为准。管线会把每镜裁到固定 5 秒，模型输出更长没关系；如果模型只能输出小于 5 秒，把这一条带回给计划作者。分辨率也同理，模板里能设多少就设多少，竖版 9:16 优先。
4. 连续运行 10 次，每次记下耗时。运行期间打开任务管理器的性能页，看 GPU 的"专用 GPU 内存"最高到多少。
5. 验收：10 次全部成功。

把平均耗时、最长耗时、显存峰值、模型文件名填进 `docs/notes/2026-11-25-m0-m1-实测记录.md`，文件模板见 Task 15 的 Step 5。

如果 10 次里有失败：把 ComfyUI 控制台的报错记下来。报错提到显存不足的话，把宽高或帧数降一档再跑 10 次，并记下新的数字。

- [ ] **Step 8: 导出两份 API 格式的工作流**

按 `workflows/README.md` 的第一节操作，产出 `workflows/keyframe_api.json`，以及至少一份 `wan_i2v_api.json` 或 `minimax_i2v_api.json`，想两个引擎都试就各导一份。

图生视频这份就用你昨晚跑通的那份工作流。导出前确认首帧图片所在的节点没有被旁路，被旁路的节点不会被导出；结果由保存节点写进输出目录。如果你参照的是 ComfyUI 自带的 Wan 2.2 模板，它的 Load Image 默认是旁路状态，先按 Ctrl+B 取消旁路；用你自己的 MiniMax 模板就以你的模板为准。

文生图那份用你现成的工作流，导出前把空 latent 节点的宽高改成竖版尺寸，默认配置对应的是 704x1280。如果你用的模型不支持这个尺寸，在 `.env` 里设 `KEYFRAME_WIDTH` 和 `KEYFRAME_HEIGHT` 为它支持的相近尺寸，保持宽高比是 9:16。关键帧的比例必须和图生视频的比例一致，否则首帧会被拉伸。

- [ ] **Step 9: 填写绑定表并校验**

按 `workflows/README.md` 的第二节填写 `keyframe.binding.json`，以及你导出的引擎的绑定表（`wan_i2v.binding.json` 或 `minimax_i2v.binding.json`）。在 `.env` 里把 `VIDEO_ENGINE` 设成你默认要用的引擎。你的模板暴露了哪些参数就绑哪些：

- 必填：`positive_prompt`；图生视频另加 `start_image`（首帧图片的输入）。
- 有就绑：`negative_prompt`、`seed`、`width`、`height`、`length`。

Run: `uv run pipeline check-workflows`
Expected: 退出码 0，打印两张绑定表；模板没暴露的可选参数会单独列出来。

逐行核对打印出来的节点类型：`positive_prompt` 指向文本编码节点；`start_image` 指向承载首帧图片的那个输入；其余绑上的参数指向符合直觉的节点。指向不对就回去改绑定表。

如果这里报 `start_image 绑定到了不存在的节点`，说明导出时首帧节点是旁路状态或者在模板里叫别的名字，JSON 里没有这个节点。回到上一步检查后重新导出。

---

### Task 15: 家里电脑上的真实运行验收

**Files:**
- Modify（家里电脑）：`docs/notes/2026-11-25-m0-m1-实测记录.md`，补全里程碑 1 的部分。

**Interfaces:**
- Consumes: Task 14 的全部产物。
- Produces: 一条用真实的 DeepSeek、ComfyUI、本地配音跑出来的 10 秒成片，以及实测记录。

验收标准来自设计文档：2 个镜头、最低画质、每镜 1 个候选，一条 10 秒的片子无人值守跑完。

- [ ] **Step 1: 启动服务**

确认 ComfyUI 在运行。新开的终端先 `cd` 到仓库根目录，并执行 `export PYTHONUTF8=1`，原因见 Task 14 开头的说明。

Run（保持运行的终端）: `uv run pipeline serve`
Expected: 打印出 Uvicorn 的启动信息，地址是 `http://127.0.0.1:8000`。

- [ ] **Step 2: 提交并等它自己跑完**

浏览器打开 `http://127.0.0.1:8000/`。主题填"青丘山的九尾狐"，镜头数填 2，点"生成"。然后不要操作，等它跑完。

Expected: 状态最终变成 done，页面下方出现一段 10 秒的视频，画面是两个不同的神话场景，旁白和画面对应。

如果状态变成 failed，按错误信息对号入座：

| 错误信息 | 原因 | 处理 |
|---|---|---|
| `连不上 ComfyUI` | ComfyUI 没启动，或端口和 `.env` 不一致 | 启动 ComfyUI，或改 `COMFYUI_URL` |
| `ComfyUI 拒绝了这个工作流` | 绑定表填错 | 回 Task 14 的 Step 9 |
| `ComfyUI 执行出错` | 模型文件缺失或显存不足 | 看 ComfyUI 控制台的完整报错 |
| `没有配置 DEEPSEEK_API_KEY`，或启动时报 `启动失败：…`、`运行失败：…` | `.env` 没填；或者当前目录不是仓库根目录，`.env` 和 `workflows/` 都是按当前目录找的 | 回 Task 14 的 Step 3 填写 `.env`；并在仓库根目录下运行命令 |
| `DeepSeek 返回 401` | 密钥不对 | 检查 `.env` |
| `分镜脚本连续 3 次不满足要求` | 模型多次输出不合格的脚本 | 把终端日志带回给计划作者 |
| `执行成功，但没有产生任何输出文件` | 模板末尾没有 Save Image 或 Save Video 这类写入输出目录的节点，只有预览 | 给模板加上保存节点，重新导出，回 Task 14 的 Step 8 |
| 视频的第一帧和关键帧对不上，画面像随机生成 | 图生视频模板里的 Load Image 导出时是旁路状态，实际跑的是文生视频 | 回 Task 14 的 Step 8，取消旁路后重新导出 |
| 仍然报 `httpx.InvalidURL`（提示 `Invalid port` 或类似） | 环境变量 `NO_PROXY` 里有 `[::1]` 这类 httpx 解析不了的内容。管线自己已经会绕开这种情况，所以它只可能来自别的程序 | 把 `NO_PROXY` 改成不带方括号的写法，例如 `localhost,127.0.0.1,::1`，或者删掉这个环境变量 |

- [ ] **Step 3: 记录各阶段耗时**

终端里每个镜头每个阶段完成时都有一行日志，形如 `视频 20261125-143005-a1b2 第 1 镜 keyframed 完成，第 1 次尝试，用时 12.3 秒`。把这些数字填进实测记录。

- [ ] **Step 4: 确认成片到了交付目录**

Expected: `.env` 里 `DELIVER_DIR` 指向的目录下出现 `<视频编号>.mp4`；在手机的网盘 App 里能看到它并且能播放。

- [ ] **Step 5: 写实测记录**

新建 `docs/notes/2026-11-25-m0-m1-实测记录.md`，Task 14 已经填了前两部分，这里补全后两部分。完整结构如下：

```markdown
# 里程碑 0 和 1 实测记录

日期：2026-11-25
电脑：Ultra 9 285K、RTX 5080 16G

## 里程碑 0：图生视频

| 项目 | 结果 |
|---|---|
| 使用的模板 | |
| 模型文件 | |
| 分辨率和帧数 | 720x1280，121 帧 |
| 帧率 | |
| 10 次运行成功次数 | |
| 单镜头平均耗时 | |
| 单镜头最长耗时 | |
| 显存峰值 | |

## 配音

| 项目 | 结果 |
|---|---|
| 选定的音色 | |
| 试听结论 | |

## 里程碑 1：真实运行

| 阶段 | 第 1 镜 | 第 2 镜 |
|---|---|---|
| 关键帧 | | |
| 镜头 | | |
| 配音 | | |

合成耗时：
脚本阶段耗时：
全程人工介入次数：
成片是否出现在交付目录：

## 结论和留给里程碑 2 的问题

```

- [ ] **Step 6: 把家里电脑上产生的文件拷回开发机**

通过网盘把这五个文件拷回开发机仓库的对应位置：

- `workflows/` 目录下你导出的 keyframe 文件，以及一到两个引擎的 i2v 文件（`*_api.json` 和同名 `.binding.json`）。
- `docs/notes/2026-11-25-m0-m1-实测记录.md`，放到开发机的 `docs/notes/` 目录。

`.env` 不要拷。

- [ ] **Step 7: 如果需要改代码才能跑通**

不要在家里电脑上改代码。把现象、终端日志和涉及的文件带回开发机，在开发机上先补一个能复现问题的测试，再修复，然后从 Task 13 重新打包，回到本任务验收。

---

### Task 16: 收尾，README 与一次性提交

**Files:**
- Modify: `README.md`（在现有内容之后追加）

**Interfaces:**
- Consumes: Task 15 拷回的工作流文件和实测记录。
- Produces: 仓库里的一次提交，包含全部源码、测试、工作流文件、实测记录和 README。

设计文档和本实施计划各有一次单独的提交，那两次提交什么时候做由用户决定，不属于这个任务。这个任务只提交实现。

- [ ] **Step 1: 确认拷回的文件都在**

Run: `ls workflows/ docs/notes/`
Expected: `workflows/` 下有 `README.md`、三个 `*.binding.example.json`，以及你导出的 keyframe 的 `*_api.json` 和 `*.binding.json`，外加一到两个引擎的 `<引擎>_i2v_api.json` 和同名 `.binding.json`（按实际导出情况对账）。`docs/notes/` 下有 `2026-11-25-m0-m1-实测记录.md`。

Run: `uv run pipeline check-workflows`
Expected: 退出码 0，keyframe 和你导出的引擎的绑定表与 Task 14 里看到的一致。

- [ ] **Step 2: 把下面一节追加到 README.md 末尾`

````markdown
## 开发与运行

需要 uv（`uv --version` 能打印版本即可，没装的话见 https://docs.astral.sh/uv/ ）。ffmpeg 不用单独安装，由 pip 包 imageio-ffmpeg 提供。所有命令在仓库根目录执行。

```bash
uv sync                    # 首次：安装依赖，uv 会管理 .venv 和 Python 版本，较慢
uv run pytest tests/ -v    # 运行单元测试
uv run pipeline run --topic "青丘山的九尾狐" --shot-count 2 --fakes   # 不需要显卡的冒烟
uv run pipeline check-workflows                # 校验工作流模板和参数绑定
uv run pipeline serve                          # 启动本机网页，http://127.0.0.1:8000
```

真实运行前要准备三件事：复制 `.env.example` 为 `.env`，填写 DeepSeek 密钥和交付目录，并选好 `VIDEO_ENGINE`；按 `workflows/README.md` 导出 ComfyUI 工作流（keyframe 加至少一个引擎的 i2v）并填写绑定表；启动 ComfyUI。
````

- [ ] **Step 3: 再跑一次全部测试**

Run: `uv run pytest tests/ -v`
Expected: PASS，和 Task 13 的用例数一致。

- [ ] **Step 4: 提交前检查暂存内容**

Run: `git add pyproject.toml uv.lock .gitignore .env.example README.md src/ tests/ workflows/ docs/notes/`
Run: `git status --porcelain`
Expected: 每一行都以 `A` 或 `M` 开头，没有 `??`。逐行看一遍，不能有 `.env`、`.venv/`、`data/`、mp4、wav、模型权重文件。

如果看到不该提交的文件，用 `git restore --staged <文件>` 把它移出暂存区，不要提交。

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(pipeline): 实现里程碑 1 的最小端到端视频管线"
```

- [ ] **Step 6: 确认提交结果**

Run: `git status -sb`
Expected: 第一行是 `## feature/ai-video-pipeline-20261125`，下面没有未提交的文件。

Run: `git log --oneline -5`
Expected: 最上面一条就是刚才的提交。

不要推送。推送需要用户明确要求，而且本机目前还没有配置推送用的凭据。

---

## 与设计文档的对应关系

| 设计文档的内容 | 由哪里实现 |
|---|---|
| 4.2 的阶段 1 到 5：脚本、关键帧、镜头、配音、合成 | Task 3、Task 7、Task 8、Task 6、Task 10 |
| 4.3 每镜 5 秒、旁白不超过 20 字 | Task 2 的校验，Task 6 的合成，Task 3 的提示词与重试 |
| 4.3 按阶段批量 | Task 10 的 `_run_stage` |
| 4.3 生成失败换种子重试 | Task 10 |
| 4.1 只监听本机地址 | Task 12 的 `uvicorn.run` 绑定 `127.0.0.1` |
| 4.1 成片放进网盘同步目录 | Task 10 复制到 `deliver_dir`，Task 14 配置 `DELIVER_DIR` |
| 5 的模块划分和 EpisodeSpec 契约 | Task 2 定义契约，Task 3 到 Task 11 按模块实现 |
| 6 的队列与单镜失败不影响其余镜头 | Task 9、Task 10 |
| 7 的测试策略：工作流模板、合成、脚本、端到端冒烟 | Task 4、Task 6、Task 3、Task 12 |
| 8 的里程碑 0 | Task 14 的 Step 7 |
| 8 的里程碑 1 | Task 1 到 Task 15 |
| 8 的产能校准 | Task 15 的实测记录 |
| 10 的仓库约定 | 全局的提交纪律，Task 1 的 `.gitignore`，Task 16 |

以下设计文档里的内容按计划留给里程碑 2，本计划没有对应的任务：多候选与自动评分、单镜重做、断点续跑、显存不足时降级重试、字幕配乐片头片尾和 AI 显式标识、标题简介和话题标签、管线服务开机自启、ComfyUI 崩溃后自动拉起。其中"ComfyUI 崩溃后拉起"在里程碑 1 表现为：连接失败时任务报错并写明原因，重启 ComfyUI 后重新提交。
