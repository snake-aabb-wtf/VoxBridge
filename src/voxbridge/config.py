"""Project paths and non-secret application settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
KEY_PATH = PROJECT_ROOT / "key.secret"
SAMPLES_DIR = PROJECT_ROOT / "SourceSamples"
GENERATED_DIR = PROJECT_ROOT / "Generated"
SETTINGS_PATH = PROJECT_ROOT / "settings.json"


@dataclass(frozen=True)
class AuthorizedSample:
    """A voice sample explicitly authorized for use by this application."""

    label: str
    path: Path
    sha256: str


AUTHORIZED_SAMPLES: tuple[AuthorizedSample, ...] = (
    AuthorizedSample(
        "DaiYuqiang.wav",
        SAMPLES_DIR / "DaiYuqiang.wav",
        "b73e348cdfe80df582db038522e3133e6bb786ea76818137b04c4749d6ee91b8",
    ),
    AuthorizedSample(
        "TiMi.wav",
        SAMPLES_DIR / "TiMi.wav",
        "7f21758305f5bbd0ac51a33523d7336083fa0c6dc5c45f467f4f9527dbea90bc",
    ),
)


def load_settings() -> dict[str, str]:
    """Load the selected output device preference, ignoring invalid settings."""

    try:
        value = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}

    if not isinstance(value, dict):
        return {}

    device_name = value.get("output_device_name")
    if not isinstance(device_name, str) or not device_name.strip():
        return {}
    return {"output_device_name": device_name}


def save_settings(settings: dict[str, str]) -> None:
    """Save only the supported, non-secret output device preference."""

    device_name = settings.get("output_device_name")
    payload: dict[str, str] = {}
    if isinstance(device_name, str) and device_name.strip():
        payload["output_device_name"] = device_name

    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = SETTINGS_PATH.with_name(f"{SETTINGS_PATH.name}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(SETTINGS_PATH)
