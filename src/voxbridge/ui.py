"""Tkinter interface for cloning speech and routing it to a virtual cable."""

from __future__ import annotations

import queue
import re
import struct
import threading
import wave
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from .audio_output import (
    AudioOutputDevice,
    AudioOutputError,
    is_virtual_mic_sink,
    list_output_devices,
    send_wav_to_virtual_mic,
    stop_virtual_mic_stream,
)
from .config import (
    AUTHORIZED_SAMPLES,
    GENERATED_DIR,
    AuthorizedSample,
    load_settings,
    save_settings,
)
from .hotkeys import HotkeyError, HotkeyManager
from .mimo_client import MiMoError, clone_audio, load_api_key


def _latest_valid_clone() -> Path | None:
    """Find the newest nonempty WAV saved by VoxBridge."""

    try:
        candidates = sorted(
            GENERATED_DIR.glob("clone_*.wav"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None

    for candidate in candidates:
        try:
            with wave.open(str(candidate), "rb") as wav_file:
                channels = wav_file.getnchannels()
                frames = wav_file.getnframes()
                width = wav_file.getsampwidth()
                rate = wav_file.getframerate()
                if (
                    channels > 0
                    and frames > 0
                    and width > 0
                    and rate > 0
                    and wav_file.getcomptype() == "NONE"
                    and len(wav_file.readframes(frames)) == frames * channels * width
                ):
                    return candidate
        except (EOFError, OSError, struct.error, wave.Error):
            continue
    return None


class VirtualMicApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("VoxBridge · 虚拟麦克风")
        self.root.geometry("790x760")
        self.root.minsize(700, 520)
        self.root.configure(background="#f4f6f9")

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.samples_by_label = {sample.label: sample for sample in AUTHORIZED_SAMPLES}
        self.devices_by_label: dict[str, AudioOutputDevice] = {}
        self.latest_clone = _latest_valid_clone()
        self.clone_in_progress = False
        self.closed = False
        self.device_status = ""
        self.hotkey_errors: tuple[str, ...] = ()
        self.api_key: str | None = None
        self.key_status = ""
        try:
            self.api_key = load_api_key()
        except MiMoError as error:
            self.key_status = str(error)

        self.sample_var = tk.StringVar(value=AUTHORIZED_SAMPLES[0].label)
        self.emotion_var = tk.StringVar()
        self.output_device_var = tk.StringVar()
        self.status_var = tk.StringVar(value="正在准备音频设备…")
        self.latest_var = tk.StringVar()

        self._configure_styles()
        self._build_ui()
        self._refresh_devices(initial=True)
        self._register_hotkeys()
        self._update_idle_status()
        self._update_latest_label()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._drain_events)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("App.TFrame", background="#f4f6f9")
        style.configure("Card.TLabelframe", background="#ffffff", padding=16)
        style.configure(
            "Card.TLabelframe.Label",
            background="#ffffff",
            foreground="#172033",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure("Title.TLabel", background="#f4f6f9", foreground="#101828", font=("Segoe UI", 21, "bold"))
        style.configure("Subtitle.TLabel", background="#f4f6f9", foreground="#5b6473", font=("Segoe UI", 10))
        style.configure("Hint.TLabel", background="#ffffff", foreground="#626d7e", font=("Segoe UI", 9))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 10))
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(12, 9))

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=(24, 16))
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        scroll_frame = ttk.Frame(shell, style="App.TFrame")
        scroll_frame.grid(row=0, column=0, sticky="nsew")
        scroll_frame.columnconfigure(0, weight=1)
        scroll_frame.rowconfigure(0, weight=1)

        self.content_canvas = tk.Canvas(
            scroll_frame,
            background="#f4f6f9",
            highlightthickness=0,
            borderwidth=0,
        )
        self.content_scrollbar = ttk.Scrollbar(
            scroll_frame,
            orient="vertical",
            command=self.content_canvas.yview,
        )
        self.content_canvas.configure(yscrollcommand=self.content_scrollbar.set)
        self.content_canvas.grid(row=0, column=0, sticky="nsew")
        self.content_scrollbar.grid(row=0, column=1, sticky="ns")

        self.scroll_content = ttk.Frame(self.content_canvas, style="App.TFrame")
        self.content_window = self.content_canvas.create_window(
            (0, 0),
            window=self.scroll_content,
            anchor="nw",
        )
        self.scroll_content.bind("<Configure>", self._update_scroll_region)
        self.content_canvas.bind("<Configure>", self._resize_scroll_content)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        page = self.scroll_content

        ttk.Label(page, text="VoxBridge", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            page,
            text="克隆授权音色，并把生成语音送入虚拟音频线。",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 18))

        voice_card = ttk.LabelFrame(page, text="语音内容", style="Card.TLabelframe")
        voice_card.pack(fill="x", pady=(0, 14))
        voice_card.columnconfigure(0, weight=1)

        ttk.Label(voice_card, text="授权样本").grid(row=0, column=0, sticky="w")
        self.sample_combo = ttk.Combobox(
            voice_card,
            textvariable=self.sample_var,
            values=[sample.label for sample in AUTHORIZED_SAMPLES],
            state="readonly",
        )
        self.sample_combo.grid(row=1, column=0, sticky="ew", pady=(5, 13))

        ttk.Label(voice_card, text="朗读文案").grid(row=2, column=0, sticky="w")
        text_frame = ttk.Frame(voice_card)
        text_frame.grid(row=3, column=0, sticky="nsew", pady=(5, 13))
        text_frame.columnconfigure(0, weight=1)
        self.text_input = tk.Text(
            text_frame,
            height=8,
            wrap="word",
            undo=True,
            font=("Segoe UI", 11),
            background="#ffffff",
            foreground="#172033",
            insertbackground="#172033",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=9,
        )
        self.text_input.grid(row=0, column=0, sticky="nsew")
        self.text_input.bind("<MouseWheel>", self._on_text_mousewheel, add="+")
        text_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text_input.yview)
        text_scroll.grid(row=0, column=1, sticky="ns")
        self.text_input.configure(yscrollcommand=text_scroll.set)

        ttk.Label(voice_card, text="情绪 / 语气").grid(row=4, column=0, sticky="w")
        self.emotion_entry = ttk.Entry(voice_card, textvariable=self.emotion_var)
        self.emotion_entry.grid(row=5, column=0, sticky="ew", pady=(5, 3))
        ttk.Label(
            voice_card,
            text="自由描述，例如：温柔平静、兴奋热情、严肃坚定。",
            style="Hint.TLabel",
        ).grid(row=6, column=0, sticky="w")

        output_card = ttk.LabelFrame(page, text="虚拟麦克风通道", style="Card.TLabelframe")
        output_card.pack(fill="x", pady=(0, 14))
        output_card.columnconfigure(0, weight=1)
        ttk.Label(output_card, text="音频送入的虚拟端点").grid(row=0, column=0, sticky="w")
        output_row = ttk.Frame(output_card)
        output_row.grid(row=1, column=0, sticky="ew", pady=(5, 9))
        output_row.columnconfigure(0, weight=1)
        self.output_combo = ttk.Combobox(
            output_row,
            textvariable=self.output_device_var,
            state="readonly",
        )
        self.output_combo.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.output_combo.bind("<<ComboboxSelected>>", self._on_output_selected)
        ttk.Button(
            output_row,
            text="刷新设备",
            style="Secondary.TButton",
            command=lambda: self._refresh_devices(initial=False),
        ).grid(row=0, column=1)
        ttk.Label(
            output_card,
            text="这里只列出 Windows WASAPI 下的虚拟麦克风端点。VB-CABLE：CABLE Input → CABLE Output；Steam：Speakers (Steam Streaming Microphone) → Microphone (Steam Streaming Microphone)。",
            style="Hint.TLabel",
            wraplength=660,
        ).grid(row=2, column=0, sticky="w")

        action_row = ttk.Frame(page, style="App.TFrame")
        action_row.pack(fill="x", pady=(2, 12))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)
        self.clone_button = ttk.Button(
            action_row,
            text="生成克隆   Ctrl + Alt + 6",
            style="Accent.TButton",
            command=self._start_clone,
        )
        self.clone_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.send_button = ttk.Button(
            action_row,
            text="送入虚拟麦克风   Ctrl + Alt + 7",
            style="Secondary.TButton",
            command=self._start_send,
        )
        self.send_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        result_card = ttk.LabelFrame(page, text="最近生成", style="Card.TLabelframe")
        result_card.pack(fill="x", pady=(0, 14))
        ttk.Label(result_card, textvariable=self.latest_var, style="Hint.TLabel", wraplength=660).pack(anchor="w")
        ttk.Label(
            result_card,
            text="生成的 WAV 保存在项目目录的 Generated 文件夹中。",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        status_card = ttk.Frame(shell, padding=(14, 11), style="App.TFrame")
        status_card.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(status_card, text="状态", font=("Segoe UI", 9, "bold"), style="Subtitle.TLabel").pack(anchor="w")
        ttk.Label(
            status_card,
            textvariable=self.status_var,
            style="Subtitle.TLabel",
            wraplength=690,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))

    def _update_scroll_region(self, _event: tk.Event) -> None:
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_scroll_content(self, event: tk.Event) -> None:
        self.content_canvas.itemconfigure(self.content_window, width=event.width)

    @staticmethod
    def _wheel_steps(event: tk.Event) -> int:
        return max(1, abs(int(event.delta)) // 120)

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        try:
            event_toplevel = event.widget.winfo_toplevel()
        except (AttributeError, tk.TclError):
            return None
        if event_toplevel is not self.root:
            return None
        if not event.delta:
            return "break"
        direction = -1 if event.delta > 0 else 1
        self.content_canvas.yview_scroll(direction * self._wheel_steps(event), "units")
        return "break"

    def _on_text_mousewheel(self, event: tk.Event) -> str:
        if not event.delta:
            return "break"
        direction = -1 if event.delta > 0 else 1
        steps = self._wheel_steps(event)
        first, last = self.text_input.yview()
        text_can_scroll = (direction < 0 and first > 0) or (direction > 0 and last < 1)
        if text_can_scroll:
            self.text_input.yview_scroll(direction * steps, "units")
        else:
            self.content_canvas.yview_scroll(direction * steps, "units")
        return "break"

    def _register_hotkeys(self) -> None:
        self.hotkeys = HotkeyManager(self._enqueue_action)
        try:
            self.hotkey_errors = self.hotkeys.start()
        except HotkeyError as error:
            self.hotkey_errors = (str(error),)

    def _enqueue_action(self, action: str) -> None:
        self.events.put(("action", action))

    def _refresh_devices(self, initial: bool) -> None:
        current_device = self.devices_by_label.get(self.output_device_var.get())
        current_name = current_device.name if current_device else None
        try:
            devices = [device for device in list_output_devices() if is_virtual_mic_sink(device)]
        except AudioOutputError as error:
            devices = []
            self.device_status = str(error)
        else:
            self.device_status = ""

        self.devices_by_label = {
            f"{device.id} · {device.name}": device for device in devices
        }
        choices = list(self.devices_by_label)
        self.output_combo.configure(values=choices)

        preferred_name = load_settings().get("output_device_name")
        selected_label = ""
        if current_name:
            selected_label = next(
                (label for label, device in self.devices_by_label.items() if device.name == current_name),
                "",
            )
        if not selected_label and preferred_name:
            selected_label = next(
                (label for label, device in self.devices_by_label.items() if device.name == preferred_name),
                "",
            )
        if not selected_label:
            cable_input_match = re.compile(r"CABLE(?:[-\s]*[A-D])?\s*Input", re.IGNORECASE)
            selected_label = next(
                (label for label, device in self.devices_by_label.items() if cable_input_match.search(device.name)),
                next(iter(self.devices_by_label), ""),
            )

        self.output_device_var.set(selected_label)
        if not self.device_status:
            if selected_label:
                self.device_status = f"已选择虚拟麦克风端点：{self.devices_by_label[selected_label].name}。"
            else:
                self.device_status = "未检测到受支持的虚拟麦克风端点。启用虚拟音频驱动（如 Steam 或 VB-CABLE）后刷新；普通扬声器不会作为目标。克隆仍可生成。"
        if not initial:
            self._update_idle_status()
        self._update_send_button()

    def _on_output_selected(self, _event: object = None) -> None:
        device = self.devices_by_label.get(self.output_device_var.get())
        if device is None:
            return
        try:
            save_settings({"output_device_name": device.name})
        except OSError:
            self.status_var.set(f"已选择 {device.name}，但无法保存设备偏好。")
            return
        self.device_status = f"已选择虚拟麦克风端点：{device.name}。"
        self.status_var.set(self.device_status)
        self._update_send_button()

    def _update_idle_status(self) -> None:
        parts = [*self.hotkey_errors, self.key_status, self.device_status]
        parts = [part for part in parts if part]
        if self.hotkey_errors:
            parts.append("GUI 按钮仍可使用。")
        if not parts:
            parts.append("就绪。Ctrl+Alt+6 生成克隆，Ctrl+Alt+7 送入虚拟麦克风。")
        self.status_var.set(" ".join(parts))

    def _selected_sample(self) -> AuthorizedSample | None:
        return self.samples_by_label.get(self.sample_var.get())

    def _start_clone(self) -> None:
        if self.clone_in_progress:
            self.status_var.set("MiMo 正在生成，请等待当前请求完成。")
            return

        sample = self._selected_sample()
        if sample is None:
            self.status_var.set("请选择一个已授权样本。")
            return
        text = self.text_input.get("1.0", "end-1c").strip()
        emotion = self.emotion_var.get().strip()
        if not text:
            self.status_var.set("请先输入要朗读的文案。")
            self.text_input.focus_set()
            return
        if not emotion:
            self.status_var.set("请先输入情绪或语气。")
            self.emotion_entry.focus_set()
            return
        if self.api_key is None:
            try:
                self.api_key = load_api_key()
                self.key_status = ""
            except MiMoError as error:
                self.key_status = str(error)
                self.status_var.set(self.key_status)
                return

        self.clone_in_progress = True
        self.clone_button.configure(state="disabled")
        self.status_var.set("正在请求 MiMo 合成，完成后会保存为最近一次克隆…")
        threading.Thread(
            target=self._clone_worker,
            args=(sample, text, emotion, self.api_key),
            name="VoxBridgeMiMoClone",
            daemon=True,
        ).start()

    def _clone_worker(
        self,
        sample: AuthorizedSample,
        text: str,
        emotion: str,
        api_key: str,
    ) -> None:
        try:
            audio_bytes = clone_audio(sample, text, emotion, api_key)
            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            filename = datetime.now().strftime("clone_%Y%m%d_%H%M%S_%f.wav")
            final_path = GENERATED_DIR / filename
            temporary_path = GENERATED_DIR / f".{filename}.tmp"
            temporary_path.write_bytes(audio_bytes)
            temporary_path.replace(final_path)
        except MiMoError as error:
            self.events.put(("clone_error", str(error)))
        except OSError:
            self.events.put(("clone_error", "合成已返回，但无法保存 WAV；请检查 Generated 文件夹权限。"))
        except Exception:
            self.events.put(("clone_error", "克隆失败，最近一次成功结果未被覆盖。请稍后重试。"))
        else:
            self.events.put(("clone_success", final_path))

    def _start_send(self) -> None:
        if self.latest_clone is None or not self.latest_clone.is_file():
            self.status_var.set("还没有可送入虚拟麦克风的克隆音频，请先生成一次。")
            self._update_send_button()
            return
        device = self.devices_by_label.get(self.output_device_var.get())
        if device is None:
            self.status_var.set("没有可用的虚拟麦克风端点；不会向普通扬声器发送音频。")
            return

        path = self.latest_clone
        self.status_var.set(f"正在把最近一次克隆送入虚拟麦克风端点 {device.name}…")
        threading.Thread(
            target=self._send_worker,
            args=(path, device),
            name="VoxBridgeVirtualMicSend",
            daemon=True,
        ).start()

    def _send_worker(self, path: Path, device: AudioOutputDevice) -> None:
        try:
            send_wav_to_virtual_mic(path, device.id)
        except AudioOutputError as error:
            self.events.put(("send_error", str(error)))
        else:
            self.events.put(("send_success", device.name))

    def _update_send_button(self) -> None:
        selected_virtual_endpoint = self.devices_by_label.get(self.output_device_var.get())
        available = (
            self.latest_clone is not None
            and self.latest_clone.is_file()
            and selected_virtual_endpoint is not None
        )
        self.send_button.configure(state="normal" if available else "disabled")

    def _update_latest_label(self) -> None:
        if self.latest_clone is None:
            self.latest_var.set("暂无克隆音频。生成一次后可按 Ctrl+Alt+7 送入虚拟麦克风。")
        else:
            self.latest_var.set(f"{self.latest_clone.name}  ·  {self.latest_clone.parent}")
        self._update_send_button()

    def _drain_events(self) -> None:
        if self.closed:
            return
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "action":
                if payload == "clone":
                    self._start_clone()
                elif payload == "send":
                    self._start_send()
            elif event == "clone_success":
                self.clone_in_progress = False
                self.clone_button.configure(state="normal")
                self.latest_clone = payload if isinstance(payload, Path) else Path(str(payload))
                self._update_latest_label()
                self.status_var.set(f"克隆完成并已保存：{self.latest_clone.name}")
            elif event == "clone_error":
                self.clone_in_progress = False
                self.clone_button.configure(state="normal")
                self.status_var.set(str(payload))
            elif event == "send_success":
                self.status_var.set(
                    f"已将最近一次克隆送入 {payload}。请在目标程序中选择对应的虚拟麦克风录音端。"
                )
            elif event == "send_error":
                self.status_var.set(str(payload))

        self.root.after(100, self._drain_events)

    def _close(self) -> None:
        self.closed = True
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        finally:
            stop_virtual_mic_stream()
            self.api_key = None
            self.root.destroy()


def run_app() -> None:
    root = tk.Tk()
    VirtualMicApp(root)
    root.mainloop()
