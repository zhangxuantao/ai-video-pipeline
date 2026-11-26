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
