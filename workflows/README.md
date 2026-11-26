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
