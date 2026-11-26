import json
from pathlib import Path

import httpx
import pytest

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
