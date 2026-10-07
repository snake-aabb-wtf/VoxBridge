# MiMo V2.5 TTS 调用与使用参考

本文是对小米 MiMo 官方语音合成文档的中文操作摘要，便于本项目后续集成、生成语音和排查调用参数。接口行为可能更新；真正调用前，若遇到本文没有覆盖或与线上不一致的部分，应以官方文档为准。

- 官方文档：[语音合成（MiMo-V2.5-TTS 系列）](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5)
- 官方页面标注更新时间：2026-07-15
- 本地整理日期：2026-10-05

## 1. 模型与能力

| 模型 ID | 用途 | 音色来源 | 主要限制 |
| --- | --- | --- | --- |
| `mimo-v2.5-tts` | 使用预置音色合成 | 预置音色 ID | 支持唱歌模式；不支持音色设计和音色复刻 |
| `mimo-v2.5-tts-voicedesign` | 用文字描述设计音色 | user 消息中的音色描述 | 不支持唱歌、预置音色和音色复刻 |
| `mimo-v2.5-tts-voiceclone` | 用音频样本复刻音色 | audio.voice 中的 Base64 音频数据 | 不支持唱歌、预置音色和音色设计 |

## 2. 接口与准备

MiMo 接口兼容 OpenAI Python SDK 的 Chat Completions 用法。SDK 的 base URL 使用 `https://api.xiaomimimo.com/v1`。合成文本应放在 `assistant` 消息里；不能只把要朗读的文本放在 `user` 消息中。

`user` 消息用于风格/情绪指令或对话上下文，普通预置音色和音色复刻场景下可省略；使用音色设计模型时必须提供。音色设计模型开启 `optimize_text_preview=True` 时，可以不传 `assistant` 消息，由服务端润色目标播报文本。

安装 Python SDK：

~~~powershell
python -m pip install openai
~~~

以下示例假定脚本从 Windows 项目目录运行。项目 Key 保存在根目录 `key.secret`；代码读取时只在内存中使用，不要打印它：

~~~python
from pathlib import Path
from openai import OpenAI

key_path = Path(r"E:\Projects\MiMo AI TTS\key.secret")
api_key = key_path.read_text(encoding="utf-8").strip()

client = OpenAI(
    api_key=api_key,
    base_url="https://api.xiaomimimo.com/v1",
)
~~~

## 3. 预置音色合成

预置音色通过 `audio.voice` 选择，仅适用于 `mimo-v2.5-tts`。

| 音色名 | Voice ID | 语言 | 页面列出的性别 |
| --- | --- | --- | --- |
| MiMo 默认 | `mimo_default` | 随部署集群而异 | 中国集群默认为冰糖，其他集群默认为 Mia |
| 冰糖 | `冰糖` | 中文 | 女性 |
| 茉莉 | `茉莉` | 中文 | 女性 |
| 苏打 | `苏打` | 中文 | 男性 |
| 白桦 | `白桦` | 中文 | 男性 |
| Mia | `Mia` | 英文 | 女性 |
| Chloe | `Chloe` | 英文 | 女性 |
| Milo | `Milo` | 英文 | 男性 |
| Dean | `Dean` | 英文 | 男性 |

非流式合成用 `wav`，响应中的 Base64 音频解码后写入文件：

~~~python
import base64

completion = client.chat.completions.create(
    model="mimo-v2.5-tts",
    messages=[
        {"role": "user", "content": "请用温暖、平静的语气播报。"},
        {"role": "assistant", "content": "欢迎回来，今天也辛苦了。"},
    ],
    audio={"format": "wav", "voice": "冰糖"},
)

audio_data = completion.choices[0].message.audio.data
audio_bytes = base64.b64decode(audio_data)
with open("output.wav", "wb") as audio_file:
    audio_file.write(audio_bytes)
~~~

## 4. 控制语气、情绪和表达

### 自然语言指令

将风格描述放在 `user` 消息中，合成文本仍在 `assistant` 消息中。可以用自然语言描述整体基调、语速、停顿、重音、情绪和说话场景；同一条指令可组合多个要求。

### 音频标签

标签控制放在 `assistant` 消息的播报文本中。文本开头可加整体风格标签，中间可插入细粒度表达标签；文档接受半角圆括号、全角圆括号或方括号，例如：

~~~text
(温柔 慵懒)再让我睡五分钟……（叹气）真的，最后一次。
~~~

推荐的整体风格包括基础/复合情绪（开心、悲伤、委屈、释然等）、整体语调（温柔、活泼、严肃、慵懒等）、音色定位（磁性、清亮、沙哑等）、人设腔调和方言。标签列表不是封闭词表，也可以尝试自定义风格。

细粒度标签可以描述吸气、叹气、喘息、紧张、疲惫、撒娇、颤抖、气声、笑、抽泣等表达。标签可以出现在句中合适的位置，用于控制局部语气或停顿。

唱歌时，在目标文本最开头加 `(唱歌)`，例如 `(唱歌)这里是歌词……`。官方文档也列出 `sing` 和 `singing` 作为等效标签；唱歌模式只用于 `mimo-v2.5-tts`。

## 5. 文本设计音色

使用 `mimo-v2.5-tts-voicedesign`，把音色描述放在必需的 `user` 消息中。描述可以覆盖性别与年龄、音色质感、情绪语气、语速节奏，也可加入角色、场景和说话习惯。中文和英文均可。

描述建议控制在 1–4 句，写具体且彼此一致的特征；避免互相冲突的要求，也不要用混响、EQ、压缩等后期效果来描述音色。`assistant` 中的播报文本最好与设定音色和情境相配。

~~~python
import base64

completion = client.chat.completions.create(
    model="mimo-v2.5-tts-voicedesign",
    messages=[
        {
            "role": "user",
            "content": "一位三十多岁的男声，低沉但清晰，语速从容，像纪录片旁白一样沉稳。",
        },
        {"role": "assistant", "content": "清晨的光线，慢慢越过山脊。"},
    ],
    audio={"format": "wav"},
)

audio_bytes = base64.b64decode(completion.choices[0].message.audio.data)
with open("designed_voice.wav", "wb") as audio_file:
    audio_file.write(audio_bytes)
~~~

可选参数 `optimize_text_preview=True` 用于智能润色目标播报文本；开启时可不传 `assistant` 消息。只有在确实希望服务端润色/补全文本时才使用该模式。

## 6. 音色复刻

使用 `mimo-v2.5-tts-voiceclone`，将 MP3 或 WAV 样本转成 Base64，并将 `audio.voice` 设为带 MIME 类型的数据 URI。Base64 编码字符串大小上限为 10 MB。MIME 类型可用 `audio/mpeg`（或 `audio/mp3`）和 `audio/wav`。

~~~python
import base64

sample_path = "voice_sample.mp3"
sample_bytes = open(sample_path, "rb").read()
sample_base64 = base64.b64encode(sample_bytes).decode("ascii")

completion = client.chat.completions.create(
    model="mimo-v2.5-tts-voiceclone",
    messages=[
        {"role": "user", "content": "请自然、亲切地表达。"},
        {"role": "assistant", "content": "你好，欢迎收听今天的节目。"},
    ],
    audio={
        "format": "wav",
        "voice": f"data:audio/mpeg;base64,{sample_base64}",
    },
)

audio_bytes = base64.b64decode(completion.choices[0].message.audio.data)
with open("cloned_voice.wav", "wb") as audio_file:
    audio_file.write(audio_bytes)
~~~

若样本是 WAV，数据 URI 前缀应相应改为 `data:audio/wav;base64,`。不要把示例中的文件名、MIME 类型或占位数据误当成真实样本。

## 7. 流式输出

流式请求需将 `audio.format` 设为 `pcm16`。官方示例把流式数据描述为 24 kHz、PCM16LE、单声道。每个返回 chunk 的 `delta.audio.data` 是 Base64 编码的音频片段；解码后按返回顺序拼接，再封装成 WAV。不要把 PCM 数据直接当成带 WAV 头的文件。

~~~python
import base64
import wave

stream = client.chat.completions.create(
    model="mimo-v2.5-tts",
    messages=[
        {"role": "user", "content": "轻快地播报，语速稍快。"},
        {"role": "assistant", "content": "新的一天开始了，祝你一切顺利！"},
    ],
    audio={"format": "pcm16", "voice": "Mia"},
    stream=True,
)

pcm_chunks = []
for chunk in stream:
    if not chunk.choices:
        continue
    audio = getattr(chunk.choices[0].delta, "audio", None)
    if audio and audio.get("data"):
        pcm_chunks.append(base64.b64decode(audio["data"]))

with wave.open("streamed_output.wav", "wb") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)  # PCM16 = 每个样本 2 字节
    wav_file.setframerate(24000)
    wav_file.writeframes(b"".join(pcm_chunks))
~~~

按官方页面当前说明，`mimo-v2.5-tts` 的低延迟流式输出已上线；`mimo-v2.5-tts-voicedesign` 和 `mimo-v2.5-tts-voiceclone` 尚无低延迟流式输出，其 `stream=True` 目前是兼容模式，只会在推理完成后以流式格式返回一次结果。若只是要完整文件，这两类模型优先使用非流式调用。

## 8. 计费与调用检查

官方页面（更新时间 2026-07-15）当时标注为“限时免费”，并提示在小米 MiMo 控制台账单明细中查看用量。价格和活动可能变更，实际使用前应查看控制台的最新说明。

调用前快速确认：

1. 模型 ID 与所需音色能力匹配。
2. 目标朗读文本位于 `assistant` 消息。
3. 普通预置音色调用已设置正确的 `audio.voice`；流式调用使用 `pcm16`。
4. 音色复刻使用支持的 MP3/WAV，数据 URI 的 MIME 类型与文件格式匹配，Base64 不超过 10 MB。
5. 输出文件格式与解码流程相符：`wav` 响应直接 Base64 解码保存；`pcm16` 流需拼接后按 24 kHz、单声道、16-bit PCM 封装。

## 9. 参考链接

- [MiMo V2.5 TTS 官方调用文档](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5)
- [MiMo 官方文档中心](https://mimo.mi.com/docs/zh-CN)
