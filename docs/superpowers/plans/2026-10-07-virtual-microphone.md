# VoxBridge Virtual Microphone Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for native inline implementation. Use `superpowers:subagent-driven-development` only if the user explicitly chooses delegated execution.

**Goal:** Build a Windows Python GUI that clones speech with authorized samples through MiMo Voice Clone and routes the latest WAV into a selected virtual microphone endpoint.

**Architecture:** Tkinter owns the user interface and passes work to focused MiMo, virtual-microphone-routing, and global-hotkey modules. MiMo calls run off the UI thread; all status updates return through a queue. Clones are saved under `Generated`, and the latest audio is sent only to a recognized virtual microphone endpoint so another application can capture it as microphone input.

**Tech Stack:** Python 3.12, Tkinter, OpenAI Python SDK, `sounddevice`, `soundfile`, NumPy, SciPy, Windows `RegisterHotKey` via `ctypes`.

**Spec:** `docs/superpowers/specs/2026-10-07-virtual-microphone-design.md`

## Global Constraints

- Target Windows 10/11 and Python 3.12.
- Use only MiMo model `mimo-v2.5-tts-voiceclone` at `https://api.xiaomimimo.com/v1`.
- Allow only the exact authorized contents of `SourceSamples/DaiYuqiang.wav` and `SourceSamples/TiMi.wav`, verified by the SHA-256 values stored in `voxbridge.config`.
- Require nonempty user-provided speech text and emotion/delivery instruction.
- Use WAV input and `audio.format = "wav"`; reject a Base64 data URI larger than 10 MB.
- Read the API key only from the project root `key.secret`; never display, log, or persist it elsewhere.
- Register `Ctrl+Alt+6` for clone and `Ctrl+Alt+7` for sending the latest clone into the virtual microphone; retain working GUI buttons if a hotkey cannot register.
- Never route clone audio to a physical speaker or arbitrary output device; only recognized virtual microphone endpoints are selectable and accepted by the routing layer.
- Save generated audio in `Generated`; do not modify the Windows default microphone.
- Do not add or run automated tests unless the user explicitly asks for testing or verification.
- The project has no Git metadata; do not create a repository or add commit steps.

## File Structure

- `main.py`: application entry point.
- `src/voxbridge/__init__.py`: package marker.
- `src/voxbridge/config.py`: project paths, authorized sample definitions, and nonsecret device preferences.
- `src/voxbridge/mimo_client.py`: key loading and MiMo Voice Clone request.
- `src/voxbridge/audio_output.py`: virtual microphone endpoint recognition, WAV decoding, resampling, and audio-stream routing.
- `src/voxbridge/hotkeys.py`: Windows hotkey message loop and shutdown.
- `src/voxbridge/ui.py`: Tkinter controls, background tasks, state, and user-facing errors.
- `requirements.txt`: runtime Python dependencies.
- `.gitignore`: local secret, generated audio, Python cache, and virtual environment exclusions.
- `README.md`: installation, launch, virtual-cable selection, hotkeys, and troubleshooting.
- `Generated/`: created at runtime for timestamped WAV results; excluded from source control.

## Review Focus

- Missing, empty, or unreadable `key.secret`: show a clear setup error and do not include secret contents in the error.
- Empty speech text or emotion: prevent the request and identify the missing field.
- Missing, changed, unreadable, or oversized authorized WAV: reject before calling MiMo.
- MiMo request failure or response without audio: preserve the previous latest clone and show an actionable error.
- No recognized virtual microphone endpoint, unsupported output rate, or occupied hotkey: keep cloning available, prevent send, and explain the relevant driver or conflict.

---

### Task 1: Project configuration and runtime dependencies

**Files:**
- Create: `src/voxbridge/__init__.py`
- Create: `src/voxbridge/config.py`
- Create: `requirements.txt`
- Create: `.gitignore`

**Interfaces:**
- Produces `PROJECT_ROOT`, `KEY_PATH`, `SAMPLES_DIR`, `GENERATED_DIR`, and `SETTINGS_PATH` as `pathlib.Path` constants.
- Produces frozen `AuthorizedSample(label: str, path: Path, sha256: str)` records and `AUTHORIZED_SAMPLES`, containing exactly the two authorized sample paths and their approved content digests.
- Produces `load_settings() -> dict[str, str]` and `save_settings(settings: dict[str, str]) -> None`; settings may contain the selected virtual-microphone render endpoint name and must not contain credentials.

- [x] Add the path constants and fixed authorized-sample records in `src/voxbridge/config.py`.
- [x] Add tolerant JSON settings load/save using `SETTINGS_PATH`; missing or malformed settings should return an empty preference dictionary without exposing file contents.
- [x] Declare `openai`, `sounddevice`, `soundfile`, `numpy`, and `scipy` in `requirements.txt`.
- [x] Ignore `key.secret`, `Generated/`, `settings.json`, Python bytecode/cache, and `.venv/` in `.gitignore`.

### Task 2: MiMo Voice Clone client

**Files:**
- Create: `src/voxbridge/mimo_client.py`

**Interfaces:**
- Consumes `AuthorizedSample`, `AUTHORIZED_SAMPLES`, and `KEY_PATH` from `voxbridge.config`.
- Produces `load_api_key() -> str` and `clone_audio(sample: AuthorizedSample, text: str, emotion: str, api_key: str | None = None) -> bytes`; an omitted key is loaded from `KEY_PATH`.
- `clone_audio` returns decoded WAV bytes or raises a user-safe `MiMoError` whose text contains no key or sample payload.

- [x] Implement key loading from `KEY_PATH`, rejecting missing or whitespace-only keys with a concise `MiMoError`.
- [x] Validate nonempty speech text and emotion, then validate the selected sample is one of `AUTHORIZED_SAMPLES`, exists, has the expected SHA-256, contains complete uncompressed PCM frames in a readable WAV, and encodes to no more than the documented 10 MB data URI limit.
- [x] Implement the nonstreaming OpenAI SDK call with the fixed base URL and model; put the emotion/delivery instruction in a `user` message and exact speech text in an `assistant` message.
- [x] Decode `choices[0].message.audio.data` and reject missing or empty audio with a safe error.

### Task 3: Virtual-microphone endpoint discovery and routing

**Files:**
- Create: `src/voxbridge/audio_output.py`

**Interfaces:**
- Produces frozen `AudioOutputDevice(id: int, name: str, max_channels: int, default_samplerate: float)`.
- Produces `list_output_devices() -> list[AudioOutputDevice]`, `is_virtual_mic_sink(device: AudioOutputDevice) -> bool`, `send_wav_to_virtual_mic(path: Path, device_id: int) -> None`, and `stop_virtual_mic_stream() -> None`.

- [x] Enumerate Windows WASAPI devices with at least one output channel using `sounddevice`; include each device's default sample rate and identify supported virtual microphone endpoints by name, including VB-CABLE, VoiceMeeter, Virtual Audio Cable, and Steam Streaming Microphone. Exclude MME/DirectSound duplicates and do not fall back when WASAPI is unavailable.
- [x] Decode WAV with `soundfile`, convert data to float32, and resample to the selected device's default rate with `scipy.signal.resample_poly` when needed; translate missing imports and native-library load failures into GUI-safe errors.
- [x] Reject non-virtual devices at the routing boundary, stop the prior app stream, and send the WAV to the exact selected virtual microphone endpoint with `sounddevice`.
- [x] Expose `stop_virtual_mic_stream()` to stop the active virtual-microphone stream on application shutdown.
- [x] Convert missing device, file, decode, and device-open failures into concise exceptions the GUI can display.

### Task 4: Global Windows hotkeys

**Files:**
- Create: `src/voxbridge/hotkeys.py`

**Interfaces:**
- Produces `HotkeyManager(callback: Callable[[str], None])` with `start() -> tuple[str, ...]` and `stop() -> None`; `start()` returns safe descriptions for registrations that failed.
- Calls `callback("clone")` for `Ctrl+Alt+6` and `callback("send")` for `Ctrl+Alt+7`.

- [x] Register the two combinations with Windows `RegisterHotKey` using distinct IDs and the top-row virtual-key codes for 6 and 7; return a safe error description for each failed registration.
- [x] Dispatch `WM_HOTKEY` events on the hotkey thread without invoking Tkinter APIs.
- [x] Report registration conflicts without preventing the manager from reporting which hotkeys registered; unregister successful registrations and stop the message thread during shutdown.

### Task 5: Tkinter application and user documentation

**Files:**
- Create: `main.py`
- Create: `src/voxbridge/ui.py`
- Create: `README.md`
- Create at runtime: `Generated/`
- Create at runtime: `settings.json`

**Interfaces:**
- `main.py` calls `run_app() -> None` from `voxbridge.ui`.
- `VirtualMicApp` owns the Tkinter widgets, a thread-safe action/status queue, selected sample and virtual microphone endpoint, current latest clone path, the in-memory API key, and `HotkeyManager`.
- The GUI exposes `run_app() -> None` and uses the exact client and audio interfaces from Tasks 2 and 3.

- [x] Create the GUI with a fixed authorized-sample selector, speech-text editor, emotion/delivery field, virtual microphone endpoint selector with refresh, clone/send buttons, hotkey hints, status display, and a mouse-wheel scrollable main content area.
- [x] Load `key.secret` at startup into memory only; show a safe setup error when unavailable and reload on clone if the user fixes the file while the app is open.
- [x] Validate required text and selections before clone; run `clone_audio` in a worker thread and marshal completion/errors to Tkinter using a queue polled with `.after()`.
- [x] Save successful WAV bytes atomically under timestamped names in `Generated`; update the latest clone only after a successful save and load the newest generated WAV with complete PCM frames at startup.
- [x] Connect GUI buttons and hotkey actions to the same clone/send paths; show returned registration failures in the status area and keep buttons usable if one or both hotkeys fail.
- [x] Persist only the selected virtual-microphone endpoint name in `settings.json`; on startup restore it if present, otherwise prefer a matching virtual-cable endpoint name.
- [x] On close, stop the hotkey manager and call `stop_virtual_mic_stream()`, then destroy the Tkinter window.
- [x] Document `python -m pip install -r requirements.txt`, `python main.py`, how generated audio enters the virtual line and is captured from its recording endpoint, and common key/API/device/hotkey errors in `README.md`.
- [x] Review all files against the approved spec and confirm no path writes or log messages expose the API key.

## Plan Self-Review

- Spec coverage: GUI fields and buttons, two-sample allowlist, MiMo Voice Clone payload, API key handling, asynchronous API work, timestamped/persistent latest clone, virtual-line endpoint selection/routing/resampling, global hotkeys, virtual-cable setup, error states, settings, and README all map to Tasks 1–5.
- Step scan: every unchecked item creates or changes a named artifact or one named behavior; no test commands or commit actions are included because the project has no Git metadata and the current task does not request tests.
- Interface consistency: `AuthorizedSample` is defined in Task 1 and consumed in Task 2; virtual-microphone render-endpoint and send interfaces are defined in Task 3; hotkey actions are exact strings from Task 4 and consumed by Task 5.
- Review focus: all five identified failure groups map to the responsible client, audio, hotkey, or GUI task.
- Shutdown cleanup: the approved spec's close behavior maps to the `stop_virtual_mic_stream()` interface and Task 5.
- Proportion: five focused tasks mirror the spec's five code responsibilities; the plan records implementation decisions without duplicating implementation bodies.
