# VoxBridge 虚拟麦克风模拟器设计规格

日期：2026-10-07  
状态：已通过用户审阅（2026-10-07）  
目标平台：Windows 10/11，Python 3.12

## 目标

提供一个 Windows 桌面程序，让用户输入要朗读的文案和情绪/语气，使用 MiMo V2.5 Voice Clone 模型和已授权样本生成 WAV，然后将最近生成的 WAV 送入虚拟麦克风端点，让目标程序从对应录音端把它作为麦克风输入采集。VoxBridge 不向普通扬声器发送克隆语音。

本项目当前确认授权的样本为：

- `SourceSamples/DaiYuqiang.wav` (SHA-256 `b73e348cdfe80df582db038522e3133e6bb786ea76818137b04c4749d6ee91b8`)
- `SourceSamples/TiMi.wav` (SHA-256 `7f21758305f5bbd0ac51a33523d7336083fa0c6dc5c45f467f4f9527dbea90bc`)

应用仅集成 MiMo Voice Clone，不提供其他 TTS 服务或预置音色模式。

## 用户流程

1. 启动桌面 GUI。程序读取项目根目录的 `key.secret` 到内存，不在界面、日志、配置文件或错误信息中显示密钥。
2. 用户选择上述两个样本之一，输入非空的朗读文案和情绪/语气，并选择一个已识别的虚拟麦克风发送端。
3. 点击“克隆”或按 `Ctrl+Alt+6`。程序在后台提交合成请求，GUI 保持响应。
4. 成功响应的 WAV 保存到项目根目录 `Generated` 下的带时间戳文件，并成为最近一次克隆。
5. 点击“送入虚拟麦克风”或按 `Ctrl+Alt+7`，程序把最近一次克隆的 WAV 音频流写入所选虚拟麦克风发送端。
6. 在需要使用虚拟麦克风的目标程序中，用户自行选择虚拟音频线对应的录音端，例如 VB-CABLE 的 `CABLE Output`，或 Steam 的 `Microphone (Steam Streaming Microphone)`。VoxBridge 不修改 Windows 默认麦克风。

应用启动时检查 `Generated` 中的 WAV，并把最近一个文件作为最近克隆，因此快捷键 7 可在重启后继续把上次结果送入虚拟麦克风。

## 方案与组件

### 桌面界面

使用 Python 标准库 Tkinter，避免额外 GUI 框架依赖。界面包含样本选择、文案多行输入、情绪/语气输入、虚拟麦克风端点选择、克隆与送入按钮、快捷键提示和状态区域。设备只通过 Windows WASAPI 枚举；不显示 MME 或 DirectSound 提供的重复条目，也不在 WASAPI 不可用时回退到其他接口。只列出识别到的虚拟麦克风发送端（名称匹配 `CABLE Input`、`VB-Audio`、`VoiceMeeter`、`Virtual Audio Cable` / `Virtual Microphone` 或 `Steam Streaming Microphone`）；普通扬声器不可选择。主内容区可纵向滚动并响应鼠标滚轮，状态区固定在窗口底部；文案框有自己的滚动条，文案较长时滚轮优先滚动文案，到达边缘后滚动主页面。提供刷新设备列表的入口。没有识别到 WASAPI 或虚拟麦克风端点时显示明确的驱动/设备提示，禁用送入按钮。

### MiMo 合成

通过已安装的 OpenAI Python SDK 调用兼容端点 `https://api.xiaomimimo.com/v1`，模型固定为 `mimo-v2.5-tts-voiceclone`。样本仅从确认授权的两条路径中选择，读取 WAV 后构造 `data:audio/wav;base64,...`。请求使用 `audio.format = "wav"`；情绪/语气作为 `user` 消息的自然语言指令，朗读文案放在 `assistant` 消息。采用非流式调用，直接解码响应中的 WAV 数据。

发送前验证文案、情绪、样本文件存在性、样本内容 SHA-256、WAV 声明帧数与实际数据完整性，以及 Base64 后数据 URI 大小不超过 MiMo 文档列出的 10 MB 上限。密钥只从 `key.secret` 读取；API 错误在界面中显示可操作的简短说明，不显示请求头、密钥或样本 Base64。

### 虚拟麦克风音频路由

使用 `sounddevice` 的 Windows WASAPI 主机接口枚举可写入的音频渲染端点，并只允许识别到的虚拟麦克风注入端；不枚举 MME/DirectSound，也不作接口回退。使用 `soundfile` 解码、`scipy` 按所选虚拟端点默认采样率重采样 WAV。音频流只送入虚拟端点，不提供普通扬声器目标，不捕获系统音频，也不修改系统音频设置。送入前停止已由本应用启动的上一段音频流，避免叠音。

虚拟麦克风驱动通常提供一对端点。Windows 把注入端列在音频输出/渲染端点中，例如 VB-CABLE 的 `CABLE Input`，或 Steam 的 `Speakers (Steam Streaming Microphone)`；VoxBridge 只会把 WAV 写入这些已识别的虚拟端点。驱动再把音频送到配对的录音端，供目标程序选择为麦克风，例如 `CABLE Output` 或 `Microphone (Steam Streaming Microphone)`。这里使用的是操作系统的渲染接口向虚拟驱动写入数据，不会选择或播放到普通扬声器。

### 全局快捷键与线程

使用 Windows `RegisterHotKey` 注册 `Ctrl+Alt+6`（启动克隆）和 `Ctrl+Alt+7`（送入最近克隆）。若注册失败（例如快捷键已被占用），状态区提示原因，GUI 按钮仍可用。窗口关闭时解除快捷键注册并停止本应用的音频流。

MiMo 网络请求在后台线程执行；工作线程通过线程安全队列把状态和结果交给 Tkinter 主线程更新界面。热键回调只投递任务，不直接访问 Tkinter 控件。

## 文件结构

- `main.py`：应用入口。
- `src/voxbridge/ui.py`：Tkinter 界面、输入校验、状态更新和任务队列。
- `src/voxbridge/mimo_client.py`：密钥读取、样本 allowlist、MiMo Voice Clone 请求与 WAV 解码。
- `src/voxbridge/audio_output.py`：虚拟麦克风发送端识别、WAV 音频流送入和重采样。
- `src/voxbridge/hotkeys.py`：Windows 全局快捷键注册与消息线程。
- `src/voxbridge/config.py`：项目路径和非敏感的设备偏好设置。
- `requirements.txt`：MiMo SDK 和音频运行依赖。
- `README.md`：安装、启动、虚拟音频线配置和常见错误说明。
- `.gitignore`：忽略密钥、生成音频、Python 缓存和本地虚拟环境。
- `Generated/`：运行时保存的克隆 WAV；不纳入源码或版本控制。

## 错误处理与限制

- 找不到 `key.secret`、密钥为空、样本不可读、输入为空、API 请求失败或响应没有音频时，显示清晰状态，并允许用户修正后重试。
- 样本读取仅限 allowlist 中的两个 WAV；不接受用户任意路径，以保持本次授权范围明确。
- 没有识别到虚拟麦克风端点或设备打开失败时，显示驱动提示并阻止发送到普通扬声器；不安装虚拟音频驱动。
- 全局快捷键不可注册时，GUI 按钮仍可执行相同操作。
- 当前版本面向 Windows；不承诺跨平台热键和音频设备支持。

## 依赖与配置

运行环境为 Python 3.12。依赖通过 `requirements.txt` 声明，使用 `openai`、`sounddevice`、`soundfile`、`numpy` 和 `scipy`。MiMo 密钥保存在项目根目录的 `key.secret`；`Generated` 与密钥均应由 `.gitignore` 排除。

## 验收标准

1. GUI 能启动并展示两个授权样本、文案/情绪输入框、输出设备列表和状态。
2. 一次克隆请求只调用 `mimo-v2.5-tts-voiceclone`，使用所选 WAV、用户填写的情绪和文案。
3. 合成完成后 WAV 按时间戳保存，并成为最近克隆；应用重启后仍能找到最近克隆。
4. `Ctrl+Alt+6` 与 GUI 克隆按钮触发相同的后台克隆流程；`Ctrl+Alt+7` 与 GUI 送入按钮把同一份最近 WAV 写入已选虚拟麦克风端点。
5. `Ctrl+Alt+7` 或送入按钮只向识别到的虚拟麦克风发送端写入 WAV；普通扬声器不可选，目标应用可把对应录音端作为麦克风输入。
6. 密钥不会出现在 UI、日志或配置文件中；API 请求期间 GUI 保持响应。

## 验证范围

实现时做代码审查和必要的启动/设备检查。本次任务不增加或运行自动化测试，除非用户另行要求测试或验证。

## 设计自审

- 两个 WAV 均由用户确认为已授权，规格使用固定 allowlist，不会自动纳入目录中新添加的样本。
- 情绪与文案分置于 MiMo `user` 与 `assistant` 消息，符合本地 MiMo 参考文档。
- Voice Clone 使用非流式 WAV 响应，未假设该模型提供低延迟 PCM 流。
- 应用只把克隆音频流送入已识别的虚拟麦克风端点，由目标程序选择对应录音端；应用不自动更改 Windows 默认麦克风。
- 文件职责、密钥位置、热键冲突、设备不可用和 API 失败均已说明。
- 项目目录没有 Git 元数据，无法提交规格文档；不初始化 Git 仓库。
