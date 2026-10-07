# VoxBridge 虚拟麦克风模拟器

VoxBridge 是一个 Windows Python 桌面应用。它使用 MiMo V2.5 Voice Clone，根据你输入的文案和情绪生成 WAV，再把最近生成的音频送入虚拟麦克风通道，让其他程序把它当作麦克风输入采集。

目前只允许选择已授权的两个样本：

- `SourceSamples/DaiYuqiang.wav`
- `SourceSamples/TiMi.wav`

TTS 服务固定为 `mimo-v2.5-tts-voiceclone`，不支持其他服务或预置音色。项目根目录的 `key.secret` 需要填入 MiMo API 密钥；程序启动时只将密钥读入内存，不会在界面显示或写入配置。若启动时文件缺失，可以补好文件后直接重试克隆。

窗口较矮时，可在主内容区使用鼠标滚轮上下滚动；底部状态区保持可见。

## 快速开始（Windows 10/11）

### 1. 注册 MiMo API 并创建 API Key

1. 打开 [Xiaomi MiMo API 开放平台](https://platform.xiaomimimo.com/)，使用小米账号登录。没有小米账号时，可以从控制台注册，或先到 [id.mi.com](https://id.mi.com/) 注册。
2. 登录后进入控制台的 **API Keys** 页面，创建一个**按量付费 API Key** 并复制保存。VoxBridge 使用 `https://api.xiaomimimo.com/v1`，通常使用 `sk-` 开头的按量付费密钥。Token Plan 密钥需要专属 Base URL，本应用目前不使用该套餐端点。
3. 本应用固定调用 `mimo-v2.5-tts-voiceclone`。如果请求提示无权限，请在 MiMo 控制台确认账号状态、模型权限和可用额度。API 用量和价格可能变化，使用前请查看 [MiMo 官方定价](https://mimo.mi.com/docs/price/pay-as-you-go)。

官方操作说明：[首次调用 API](https://mimo.mi.com/docs/zh-CN/quick-start/summary/first-api-call) · [API Key 获取与接入](https://mimo.mi.com/docs/zh-CN/quick-start/faq/api-integration)

### 2. 下载项目并填写密钥

可以用 Git 克隆仓库，也可以下载并解压 GitHub 提供的源码 ZIP。若使用 Git，在 PowerShell 中运行：

```powershell
git clone https://github.com/snake-aabb-wtf/VoxBridge.git
cd VoxBridge
```

在项目根目录复制密钥模板并编辑副本：

```powershell
Copy-Item .\key.secret.example .\key.secret
notepad .\key.secret
```

把 `PASTE_YOUR_MIMO_API_KEY_HERE` 替换成刚创建的 API Key。文件只放一行原始密钥，不要写 `API_KEY=`，也不要加引号。`.gitignore` 已排除 `key.secret`，请勿把真实密钥提交或分享；模板文件 `key.secret.example` 可以安全保留。

### 3. 安装并启动

需要 Windows 10/11 和 Python 3.12。在项目根目录的 PowerShell 中运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

依赖安装完成后，也可以双击 `start.bat` 启动。打开界面后，选择一个已授权样本，填写朗读文案和情绪/语气，按 `Ctrl+Alt+6` 生成；选择虚拟麦克风发送端后，按 `Ctrl+Alt+7` 将最近生成的音频送入该通道。首次生成会把所选样本、文案和情绪/语气发送给 MiMo API，并消耗账户额度。

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
├─ key.secret.example   MiMo API 密钥模板
├─ UNLICENSE            仅适用于代码的 Unlicense 声明
├─ settings.json        本地设备偏好（选择设备后创建）
└─ key.secret           本地 MiMo API 密钥（由 .gitignore 排除）
```

## 许可证

本项目代码按 The Unlicense 发布，正文见根目录 [`UNLICENSE`](UNLICENSE)。该声明仅适用于代码，不适用于或重新授权 `SourceSamples/DaiYuqiang.wav` 与 `SourceSamples/TiMi.wav` 两段声音，也不扩大这两段声音原有的授权范围。

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

## CI 与发布

推送到 `master`、向 `master` 提交 Pull Request，或手动运行 CI 时，GitHub Actions 会在 Windows + Python 3.12 环境安装依赖并运行离线测试。CI 不设置 `VOXBRIDGE_RUN_LIVE_MIMO`，不会调用 MiMo 或消耗额度。

推送 `v*` 格式的标签会先运行同一套测试；测试通过后，自动创建带生成说明的 GitHub Release。GitHub 会为源码提供 ZIP 和 tar.gz 下载包；当前工作流不构建独立 EXE。首次发布版本为 `v0.1.0`。后续版本可按此方式发布：

```powershell
git tag v0.1.1
git push origin v0.1.1
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
