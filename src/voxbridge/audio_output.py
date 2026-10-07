"""Windows virtual-microphone render-endpoint discovery and WAV routing."""

from __future__ import annotations

import ctypes
import math
import re
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator


class AudioOutputError(RuntimeError):
    """An actionable error safe to show in the desktop UI."""


_PLAY_LOCK = threading.Lock()
_VIRTUAL_MIC_SINK_NAME = re.compile(
    r"CABLE(?:[-\s]*[A-D])?\s*Input|VB-Audio|Virtual(?:\s+Audio)?\s+(?:Cable|Mic(?:rophone)?)|VoiceMeeter|Steam Streaming Microphone",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AudioOutputDevice:
    id: int
    name: str
    max_channels: int
    default_samplerate: float


def is_virtual_mic_sink(device: AudioOutputDevice) -> bool:
    """Recognize virtual render endpoints intended to feed a microphone input."""

    return bool(_VIRTUAL_MIC_SINK_NAME.search(device.name))


def _audio_libraries():
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        from scipy.signal import resample_poly
    except ImportError as exc:
        missing_module = exc.name or "音频库"
        raise AudioOutputError(
            f"缺少音频依赖 {missing_module}，请运行 python -m pip install -r requirements.txt。"
        ) from None
    except OSError:
        raise AudioOutputError(
            "音频依赖的本机组件无法加载，请在当前 Python 环境重新安装 requirements.txt。"
        ) from None
    return np, sd, sf, resample_poly


@contextmanager
def _com_initialized_for_audio_thread() -> Iterator[None]:
    """Initialize COM on the calling thread while opening a Windows audio stream."""

    if sys.platform != "win32":
        yield
        return

    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None

    hresult = int(ole32.CoInitializeEx(None, 0))  # COINIT_MULTITHREADED
    already_initialized_in_other_mode = -2147417850  # RPC_E_CHANGED_MODE
    if hresult < 0 and hresult != already_initialized_in_other_mode:
        unsigned_hresult = hresult & 0xFFFFFFFF
        raise AudioOutputError(
            f"无法初始化 Windows 音频线程（COM HRESULT 0x{unsigned_hresult:08X}）。"
        )

    initialized_here = hresult != already_initialized_in_other_mode
    try:
        yield
    finally:
        if initialized_here:
            ole32.CoUninitialize()


def list_output_devices() -> list[AudioOutputDevice]:
    """Return render-capable Windows WASAPI endpoints only."""

    _, sd, _, _ = _audio_libraries()
    try:
        raw_hostapis = sd.query_hostapis()
        raw_devices = sd.query_devices()
    except Exception:
        raise AudioOutputError("无法枚举音频设备，请检查 Windows 音频服务和驱动。") from None

    wasapi_hostapi_ids = {
        hostapi_id
        for hostapi_id, hostapi in enumerate(raw_hostapis)
        if str(hostapi.get("name", "")).strip().casefold() == "windows wasapi"
    }
    if not wasapi_hostapi_ids:
        raise AudioOutputError("未检测到 Windows WASAPI 音频接口，请检查音频驱动或服务后刷新设备。")

    devices: list[AudioOutputDevice] = []
    for device_id, device in enumerate(raw_devices):
        try:
            hostapi_id = int(device.get("hostapi", -1))
        except (TypeError, ValueError):
            continue
        if hostapi_id not in wasapi_hostapi_ids:
            continue
        max_channels = int(device.get("max_output_channels", 0))
        if max_channels < 1:
            continue
        devices.append(
            AudioOutputDevice(
                id=device_id,
                name=str(device.get("name", f"音频设备 {device_id}")),
                max_channels=max_channels,
                default_samplerate=float(device.get("default_samplerate", 0.0)),
            )
        )
    return devices


def send_wav_to_virtual_mic(path: Path, device_id: int) -> None:
    """Send a WAV stream into a supported virtual microphone render endpoint."""

    np, sd, sf, resample_poly = _audio_libraries()
    try:
        with _com_initialized_for_audio_thread():
            selected_device = next(
                (device for device in list_output_devices() if device.id == device_id),
                None,
            )
            if selected_device is None:
                raise AudioOutputError("所选虚拟音频线已不可用，请刷新设备列表后重试。")
            if not is_virtual_mic_sink(selected_device):
                raise AudioOutputError("已阻止向普通播放设备发送音频；请选择虚拟麦克风端点。")
            if selected_device.default_samplerate <= 0:
                raise AudioOutputError("所选虚拟音频线没有有效的默认采样率。")

            audio, input_rate = sf.read(str(path), dtype="float32", always_2d=True)
            input_rate = int(round(input_rate))
            output_rate = int(round(selected_device.default_samplerate))
            if input_rate <= 0 or output_rate <= 0:
                raise AudioOutputError("WAV 或虚拟音频线的采样率无效。")

            if audio.shape[1] > selected_device.max_channels:
                if selected_device.max_channels == 1:
                    audio = np.mean(audio, axis=1, keepdims=True, dtype=np.float32)
                else:
                    audio = audio[:, : selected_device.max_channels]
            elif audio.shape[1] == 1 and selected_device.max_channels >= 2:
                audio = np.repeat(audio, 2, axis=1)

            if input_rate != output_rate:
                divisor = math.gcd(input_rate, output_rate)
                audio = resample_poly(
                    audio,
                    output_rate // divisor,
                    input_rate // divisor,
                    axis=0,
                )
            audio = audio.astype(np.float32, copy=False)

            with _PLAY_LOCK:
                sd.stop()
                sd.play(
                    audio,
                    samplerate=output_rate,
                    device=selected_device.id,
                    blocking=False,
                    loop=False,
                )
    except AudioOutputError:
        raise
    except FileNotFoundError:
        raise AudioOutputError("找不到最近一次克隆的 WAV 文件。") from None
    except Exception as exc:
        detail = " ".join(str(exc).split()) or "没有更多错误信息"
        if len(detail) > 240:
            detail = detail[:237] + "..."
        diagnostic = f"{type(exc).__name__}: {detail}"
        raise AudioOutputError(
            f"无法向虚拟麦克风端点送入 WAV（{diagnostic}）。请确认驱动端点可用。"
        ) from None


def stop_virtual_mic_stream() -> None:
    """Stop the virtual-microphone audio stream started by this application."""

    try:
        _, sd, _, _ = _audio_libraries()
        with _PLAY_LOCK:
            sd.stop()
    except Exception:
        # Shutdown must still close the window if audio support is unavailable.
        return
