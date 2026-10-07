"""MiMo V2.5 Voice Clone integration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import re
import struct
import wave

from .config import AUTHORIZED_SAMPLES, KEY_PATH, AuthorizedSample


BASE_URL = "https://api.xiaomimimo.com/v1"
MODEL_ID = "mimo-v2.5-tts-voiceclone"
MAX_DATA_URI_BYTES = 10 * 1024 * 1024
VOICE_DATA_PREFIX = "data:audio/wav;base64,"
MAX_SAMPLE_BYTES = ((MAX_DATA_URI_BYTES - len(VOICE_DATA_PREFIX)) // 4) * 3


class MiMoError(RuntimeError):
    """An actionable error safe to show in the desktop UI."""


def load_api_key() -> str:
    """Read the MiMo key from the project root without exposing its contents."""

    try:
        api_key = KEY_PATH.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise MiMoError("找不到可读取的项目根目录 key.secret，请确认密钥文件存在。") from None

    if not api_key:
        raise MiMoError("项目根目录 key.secret 为空，请填入 MiMo API 密钥。")
    return api_key


def _validate_wav(audio_bytes: bytes, label: str) -> None:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            channel_count = wav_file.getnchannels()
            frame_count = wav_file.getnframes()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            if (
                channel_count < 1
                or frame_count < 1
                or sample_width < 1
                or sample_rate < 1
                or wav_file.getcomptype() != "NONE"
            ):
                raise MiMoError(f"{label} WAV 格式不受支持或没有可用音频数据。")
            expected_bytes = frame_count * channel_count * sample_width
            if len(wav_file.readframes(frame_count)) != expected_bytes:
                raise MiMoError(f"{label} WAV 音频数据不完整。")
    except (wave.Error, EOFError, OSError, struct.error):
        raise MiMoError(f"{label} 无法读取为有效 WAV 文件。") from None


def _sanitize_error_detail(detail: str, api_key: str) -> str:
    """Remove request secrets and voice sample data from a user-facing detail."""

    safe_detail = " ".join(detail.split())
    if api_key:
        safe_detail = safe_detail.replace(api_key, "[密钥已隐藏]")
    safe_detail = re.sub(
        r"data:[^,\s;]+;base64,[A-Za-z0-9+/=_-]+",
        "[音频样本已隐藏]",
        safe_detail,
    )
    if len(safe_detail) > 300:
        safe_detail = safe_detail[:297] + "..."
    return safe_detail


def _format_status_error(error: object, api_key: str) -> str:
    """Return the provider's actionable HTTP error without exposing credentials."""

    status_code = getattr(error, "status_code", None)
    body = getattr(error, "body", None)
    detail: object = None
    if isinstance(body, dict):
        provider_error = body.get("error", body)
        if isinstance(provider_error, dict):
            detail = provider_error.get("message") or provider_error.get("detail")
        elif isinstance(provider_error, str):
            detail = provider_error

    prefix = f"MiMo 请求失败（HTTP {status_code}）"
    if isinstance(detail, str) and detail.strip():
        safe_detail = _sanitize_error_detail(detail, api_key)
        return f"{prefix}：{safe_detail}"
    return f"{prefix}，请检查模型权限、请求参数和账户状态。"


def _format_local_error(error: Exception, api_key: str) -> str:
    """Expose a short local SDK error while redacting credentials and sample data."""

    detail = _sanitize_error_detail(str(error), api_key)
    return f"MiMo 本地请求错误（{type(error).__name__}）：{detail or '无详细信息'}"


def clone_audio(
    sample: AuthorizedSample,
    text: str,
    emotion: str,
    api_key: str | None = None,
) -> bytes:
    """Generate and return a MiMo Voice Clone WAV response."""

    if not text.strip():
        raise MiMoError("请先输入要朗读的文案。")
    if not emotion.strip():
        raise MiMoError("请先输入情绪或语气。")
    if sample not in AUTHORIZED_SAMPLES:
        raise MiMoError("所选样本不在已授权样本列表中。")

    try:
        if sample.path.stat().st_size > MAX_SAMPLE_BYTES:
            raise MiMoError("授权样本文件超过 MiMo 10 MB Base64 上限。")
        sample_bytes = sample.path.read_bytes()
    except MiMoError:
        raise
    except OSError:
        raise MiMoError(f"无法读取授权样本 {sample.label}，请检查文件是否存在。") from None
    actual_sha256 = hashlib.sha256(sample_bytes).hexdigest()
    if not hmac.compare_digest(actual_sha256, sample.sha256):
        raise MiMoError(f"授权样本 {sample.label} 内容已变化，请恢复已确认的原始文件。")
    _validate_wav(sample_bytes, "授权样本")

    sample_base64 = base64.b64encode(sample_bytes).decode("ascii")
    voice_data_uri = f"{VOICE_DATA_PREFIX}{sample_base64}"
    if len(voice_data_uri.encode("ascii")) > MAX_DATA_URI_BYTES:
        raise MiMoError("授权样本编码后超过 MiMo 10 MB 上限。")

    api_key = api_key if api_key is not None else load_api_key()
    if not api_key.strip():
        raise MiMoError("MiMo API 密钥为空，请检查项目根目录的 key.secret。")
    try:
        from openai import (
            APIConnectionError,
            APIStatusError,
            AuthenticationError,
            OpenAI,
            RateLimitError,
        )
    except ImportError:
        raise MiMoError("缺少 openai 依赖，请运行 python -m pip install -r requirements.txt。") from None

    try:
        client = OpenAI(api_key=api_key, base_url=BASE_URL)
        completion = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "user", "content": f"请用{emotion.strip()}的情绪和语气自然地表达。"},
                {"role": "assistant", "content": text.strip()},
            ],
            audio={"format": "wav", "voice": voice_data_uri},
        )
    except AuthenticationError:
        raise MiMoError("MiMo 认证失败，请检查项目根目录的 key.secret。") from None
    except RateLimitError:
        raise MiMoError("MiMo 暂时拒绝了请求，请检查账户额度或稍后重试。") from None
    except APIConnectionError:
        raise MiMoError("无法连接 MiMo，请检查网络连接后重试。") from None
    except APIStatusError as error:
        raise MiMoError(_format_status_error(error, api_key)) from None
    except Exception as error:
        raise MiMoError(_format_local_error(error, api_key)) from None

    try:
        message = completion.choices[0].message
        audio_value = getattr(message, "audio", None)
        if isinstance(audio_value, dict):
            audio_base64 = audio_value.get("data")
        else:
            audio_base64 = getattr(audio_value, "data", None)
        if not isinstance(audio_base64, str) or not audio_base64:
            raise MiMoError("MiMo 响应中没有合成音频，请稍后重试。")
        audio_bytes = base64.b64decode(audio_base64, validate=True)
    except MiMoError:
        raise
    except Exception:
        raise MiMoError("无法读取 MiMo 返回的音频数据，请稍后重试。") from None

    _validate_wav(audio_bytes, "MiMo 返回的音频")
    return audio_bytes
