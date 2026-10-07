from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
import wave
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from voxbridge.config import AUTHORIZED_SAMPLES
from voxbridge.mimo_client import clone_audio


@unittest.skipUnless(
    os.environ.get("VOXBRIDGE_RUN_LIVE_MIMO") == "1",
    "Set VOXBRIDGE_RUN_LIVE_MIMO=1 to make one paid MiMo Voice Clone request using key.secret.",
)
class LiveMiMoSmokeTests(unittest.TestCase):
    def test_voiceclone_request_with_project_key_returns_valid_wav(self) -> None:
        audio = clone_audio(
            AUTHORIZED_SAMPLES[0],
            "这是一条用于检查 MiMo 语音合成连接的短句。",
            "平静、清晰",
        )

        with wave.open(io.BytesIO(audio), "rb") as wav_file:
            self.assertGreater(wav_file.getnchannels(), 0)
            self.assertGreater(wav_file.getnframes(), 0)
            self.assertGreater(wav_file.getframerate(), 0)


if __name__ == "__main__":
    unittest.main()
