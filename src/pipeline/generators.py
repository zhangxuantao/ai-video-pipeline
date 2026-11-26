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
