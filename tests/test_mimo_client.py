from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx2
import openai

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from voxbridge import mimo_client
from voxbridge.config import AuthorizedSample


def make_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24_000)
        wav_file.writeframes(b"\x00\x00" * 240)
    return buffer.getvalue()


class CloneAudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.sample_dir.cleanup)

        sample_bytes = make_wav()
        self.sample_path = Path(self.sample_dir.name) / "test-sample.wav"
        self.sample_path.write_bytes(sample_bytes)
        self.sample = AuthorizedSample(
            label="test-sample.wav",
            path=self.sample_path,
            sha256=hashlib.sha256(sample_bytes).hexdigest(),
        )
        self.authorized_samples_patch = patch.object(
            mimo_client,
            "AUTHORIZED_SAMPLES",
            (self.sample,),
        )
        self.authorized_samples_patch.start()
        self.addCleanup(self.authorized_samples_patch.stop)

    def test_clone_audio_sends_documented_voiceclone_request_and_decodes_wav(self) -> None:
        expected_wav = make_wav()
        audio_message = SimpleNamespace(
            audio=SimpleNamespace(data=base64.b64encode(expected_wav).decode("ascii"))
        )
        completion = SimpleNamespace(choices=[SimpleNamespace(message=audio_message)])
        client = Mock()
        client.chat.completions.create.return_value = completion

        with patch.object(openai, "OpenAI", return_value=client):
            result = mimo_client.clone_audio(
                self.sample,
                "你好，这是合成测试。",
                "温柔、自然",
                api_key="unit-test-key",
            )

        self.assertEqual(result, expected_wav)
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "mimo-v2.5-tts-voiceclone")
        self.assertEqual(
            request["messages"],
            [
                {"role": "user", "content": "请用温柔、自然的情绪和语气自然地表达。"},
                {"role": "assistant", "content": "你好，这是合成测试。"},
            ],
        )
        self.assertEqual(request["audio"]["format"], "wav")
        voice_data_uri = request["audio"]["voice"]
        self.assertTrue(voice_data_uri.startswith("data:audio/wav;base64,"))
        decoded_sample = base64.b64decode(voice_data_uri.split(",", 1)[1])
        self.assertEqual(decoded_sample, self.sample.path.read_bytes())

    def test_clone_audio_preserves_safe_mimo_error_detail_without_leaking_key(self) -> None:
        api_key = "unit-test-secret-key"
        provider_detail = (
            f"invalid voice sample; diagnostic={api_key} "
            "data:audio/wav;base64,QUJD"
        )
        request = httpx2.Request("POST", f"{mimo_client.BASE_URL}/chat/completions")
        body = {"error": {"message": provider_detail}}
        response = httpx2.Response(400, request=request, json=body)
        provider_error = openai.BadRequestError(
            "request rejected",
            response=response,
            body=body,
        )
        client = Mock()
        client.chat.completions.create.side_effect = provider_error

        with patch.object(openai, "OpenAI", return_value=client):
            with self.assertRaises(mimo_client.MiMoError) as caught:
                mimo_client.clone_audio(
                    self.sample,
                    "你好。",
                    "自然",
                    api_key=api_key,
                )

        message = str(caught.exception)
        self.assertIn("400", message)
        self.assertIn("invalid voice sample", message)
        self.assertIn("[音频样本已隐藏]", message)
        self.assertNotIn(api_key, message)
        self.assertNotIn("QUJD", message)

    def test_clone_audio_identifies_local_sdk_error_without_leaking_request_data(self) -> None:
        api_key = "unit-test-secret-key"
        client = Mock()
        client.chat.completions.create.side_effect = RuntimeError(
            f"SDK serialization failed with {api_key} data:audio/wav;base64,QUJD"
        )

        with patch.object(openai, "OpenAI", return_value=client):
            with self.assertRaises(mimo_client.MiMoError) as caught:
                mimo_client.clone_audio(
                    self.sample,
                    "你好。",
                    "自然",
                    api_key=api_key,
                )

        message = str(caught.exception)
        self.assertIn("RuntimeError", message)
        self.assertIn("SDK serialization failed", message)
        self.assertIn("[密钥已隐藏]", message)
        self.assertIn("[音频样本已隐藏]", message)
        self.assertNotIn(api_key, message)
        self.assertNotIn("QUJD", message)


if __name__ == "__main__":
    unittest.main()
