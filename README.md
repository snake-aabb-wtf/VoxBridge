# VoxBridge 虚拟麦克风模拟器

VoxBridge 是一个 Windows Python 桌面应用。它使用 MiMo V2.5 Voice Clone，根据你输入的文案和情绪生成 WAV，再把最近生成的音频送入虚拟麦克风通道，让其他程序把它当作麦克风输入采集。

目前只允许选择已授权的两个样本：

- `SourceSamples/DaiYuqiang.wav`
- `SourceSamples/TiMi.wav`

TTS 服务固定为 `mimo-v2.5-tts-voiceclone`，不支持其他服务或预置音色。项目根目录的 `key.secret` 需要填入 MiMo API 密钥；程序启动时只将密钥读入内存，不会在界面显示或写入配置。若启动时文件缺失，可以补好文件后直接重试克隆。

窗口较矮时，可在主内容区使用鼠标滚轮上下滚动；底部状态区保持可见。

## 目录结构

```text
VoxBridge/
├─ src/voxbridge/       应用源码
├─ docs/                MiMo 参考文档、设计规格和实施计划
├─ SourceSamples/       已授权的克隆样本
├─ .superpowers/        本地实施进度记录
├─ .venv/               Python 虚拟环境
├─ Generated/           克隆生成的 WAV（首次成功生成后创建）
├─ main.py              应用入口
├─ requirements.txt     Python 依赖清单
├─ settings.json        本地设备偏好（选择设备后创建）
└─ key.secret          本地 MiMo API 密钥
```

## 安装和启动

需要 Windows 10/11 与 Python 3.12。PowerShell 中运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

如果执行策略阻止虚拟环境激活，可以直接用虚拟环境中的 Python 启动：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

依赖安装完成后，也可以双击项目根目录的 `start.bat` 启动。

## 测试

运行离线回归测试（默认不调用 MiMo）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

如需验证真实 MiMo 连接，可显式运行一次在线冒烟测试。它会从 `key.secret` 读取密钥、使用一个已授权样本，并发起一条短语音合成请求；请求会消耗账户额度，返回音频只在内存中检查，不会保存到 `Generated`：

```powershell
$env:VOXBRIDGE_RUN_LIVE_MIMO = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_mimo_live.py -v
Remove-Item Env:VOXBRIDGE_RUN_LIVE_MIMO
```

## 虚拟麦克风输入通道

VoxBridge 只通过 Windows WASAPI 枚举设备，并只显示识别到的虚拟麦克风注入端；MME 和 DirectSound 下重复出现的条目不会显示，WASAPI 不可用时也不会改用其他接口。应用不会把语音送到普通扬声器。虚拟驱动会把写入端接到对应的麦克风录音端：VB-CABLE 通常是 `CABLE Input` → `CABLE Output`；Steam Remote Play 可使用 `Speakers (Steam Streaming Microphone)` → `Microphone (Steam Streaming Microphone)`。在需要接收语音的目标程序中，把麦克风设置为对应的录音端。名称不同的独立端点（例如不同通道数的 CABLE 端点）仍会分别显示。

VoxBridge 不安装驱动，也不修改 Windows 默认麦克风。如果没有识别到 Windows WASAPI 接口或虚拟麦克风端点，检查 Windows 音频服务和驱动，启用驱动后点击“刷新设备”。当前识别 VB-CABLE / VB-Audio、VoiceMeeter、名称包含 `Virtual Audio Cable` / `Virtual Microphone` 的端点，以及 `Steam Streaming Microphone`；其他驱动若使用不同名称，不会出现在列表中。

## 克隆与送入虚拟麦克风

1. 选择 `DaiYuqiang.wav` 或 `TiMi.wav`。
2. 输入朗读文案和情绪/语气，例如“轻松温柔”或“激动热情”。两项都不能为空。
3. 点击“生成克隆”或按 `Ctrl+Alt+6`。合成会在后台进行。
4. 合成成功后，WAV 会保存到 `Generated`，并成为最近一次克隆。
5. 选择识别到的虚拟麦克风端点后，点击“送入虚拟麦克风”或按 `Ctrl+Alt+7`。目标程序从对应录音端采集这段音频。应用重启后也会自动找到最近一个有效结果。

每次克隆都会保留为带时间戳的独立 WAV 文件。再次送入不会重新请求 MiMo。

## 常见问题

- **缺少音频依赖**：在激活的虚拟环境中运行 `python -m pip install -r requirements.txt`。
- **找不到密钥或认证失败**：确认项目根目录存在 `key.secret`，文件中只有正确的 MiMo API 密钥。
- **没有虚拟麦克风通道**：确认虚拟音频线驱动已启用，并点击“刷新设备”；普通扬声器不会显示为发送目标。
- **快捷键不能用**：快捷键可能已被其他应用占用；VoxBridge 会在状态区提示，仍可使用 GUI 按钮。
- **目标程序没有收到声音**：确认 VoxBridge 选择了虚拟麦克风发送端，并确认目标程序选择了对应的录音端作为麦克风。
- **MiMo 请求失败**：检查网络、账户额度、API 密钥和 Voice Clone 模型权限。生成失败不会覆盖此前最近一次克隆。
- **SOCKS 代理连接失败**：重新运行 `python -m pip install -r requirements.txt`，安装项目声明的 SOCKS 传输支持后重试。
