# ai-video-pipeline
依托 ComfyUI 的 视频生成流水线

## 开发与运行

需要 uv（`uv --version` 能打印版本即可，没装的话见 https://docs.astral.sh/uv/ ）。ffmpeg 不用单独安装，由 pip 包 imageio-ffmpeg 提供。所有命令在仓库根目录执行。

```bash
uv sync                    # 首次：安装依赖，uv 会管理 .venv 和 Python 版本，较慢
uv run pytest tests/ -v    # 运行单元测试
uv run pipeline run --topic "青丘山的九尾狐" --shot-count 2 --fakes   # 不需要显卡的冒烟
uv run pipeline check-workflows                # 校验工作流模板和参数绑定
uv run pipeline serve                          # 启动本机网页，http://127.0.0.1:8000
```

真实运行前要准备三件事：复制 `.env.example` 为 `.env`，填写 DeepSeek 密钥和交付目录，并选好 `VIDEO_ENGINE`（关键帧模型不识中文时把 `PROMPT_LANGUAGE` 设为英文）；按 `workflows/README.md` 导出 ComfyUI 工作流（keyframe 加至少一个引擎的 i2v）并填写绑定表；启动 ComfyUI。
