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
