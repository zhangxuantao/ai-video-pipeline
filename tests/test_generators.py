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
