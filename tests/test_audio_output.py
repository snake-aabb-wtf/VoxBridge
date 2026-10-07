from __future__ import annotations

import ctypes
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from voxbridge import audio_output


class ListOutputDevicesTests(unittest.TestCase):
    def _fake_sounddevice(self, hostapis: list[dict[str, str]], devices: list[dict[str, object]]) -> Mock:
        sounddevice = Mock()
        sounddevice.query_hostapis.return_value = hostapis
        sounddevice.query_devices.return_value = devices
        return sounddevice

    def test_lists_render_devices_from_wasapi_only(self) -> None:
        sounddevice = self._fake_sounddevice(
            [
                {"name": "MME"},
                {"name": "Windows DirectSound"},
                {"name": "Windows WASAPI"},
            ],
            [
                {"name": "CABLE Input", "hostapi": 0, "max_output_channels": 2, "default_samplerate": 44100},
                {"name": "CABLE Input", "hostapi": 1, "max_output_channels": 2, "default_samplerate": 44100},
                {"name": "CABLE Input", "hostapi": 2, "max_output_channels": 2, "default_samplerate": 48000},
                {"name": "Microphone", "hostapi": 2, "max_output_channels": 0, "default_samplerate": 48000},
                {"name": "Speakers", "hostapi": 2, "max_output_channels": 2, "default_samplerate": 48000},
            ],
        )

        with patch.object(
            audio_output,
            "_audio_libraries",
            return_value=(None, sounddevice, None, None),
        ):
            devices = audio_output.list_output_devices()

        self.assertEqual([(device.id, device.name) for device in devices], [(2, "CABLE Input"), (4, "Speakers")])

    def test_does_not_fall_back_to_other_host_apis_without_wasapi(self) -> None:
        sounddevice = self._fake_sounddevice(
            [{"name": "MME"}, {"name": "Windows DirectSound"}],
            [
                {"name": "CABLE Input", "hostapi": 0, "max_output_channels": 2, "default_samplerate": 44100},
                {"name": "CABLE Input", "hostapi": 1, "max_output_channels": 2, "default_samplerate": 44100},
            ],
        )

        with patch.object(
            audio_output,
            "_audio_libraries",
            return_value=(None, sounddevice, None, None),
        ):
            with self.assertRaisesRegex(audio_output.AudioOutputError, "WASAPI"):
                audio_output.list_output_devices()


class SendWavTests(unittest.TestCase):
    def test_exposes_underlying_audio_backend_error_instead_of_generic_message(self) -> None:
        sounddevice = Mock()
        sounddevice.query_hostapis.return_value = [{"name": "Windows WASAPI"}]
        sounddevice.query_devices.return_value = [
            {
                "name": "CABLE Input (VB-Audio Virtual Cable)",
                "hostapi": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000,
            }
        ]
        sounddevice.play.side_effect = OSError("WASAPI shared stream failed\nendpoint busy")
        soundfile = Mock()
        soundfile.read.return_value = (np.zeros((4, 2), dtype=np.float32), 48000)

        with patch.object(
            audio_output,
            "_audio_libraries",
            return_value=(np, sounddevice, soundfile, None),
        ):
            with self.assertRaises(audio_output.AudioOutputError) as caught:
                audio_output.send_wav_to_virtual_mic(Path("clone.wav"), 0)

        message = str(caught.exception)
        self.assertIn("OSError", message)
        self.assertIn("WASAPI shared stream failed endpoint busy", message)

    @unittest.skipUnless(sys.platform == "win32", "Windows COM is required")
    def test_send_initializes_com_on_worker_thread_before_opening_stream(self) -> None:
        ole32 = ctypes.WinDLL("ole32")
        ole32.CoGetApartmentType.argtypes = [
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        ole32.CoGetApartmentType.restype = ctypes.c_long
        sounddevice = Mock()
        sounddevice.query_hostapis.return_value = [{"name": "Windows WASAPI"}]
        sounddevice.query_devices.return_value = [
            {
                "name": "CABLE Input (VB-Audio Virtual Cable)",
                "hostapi": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000,
            }
        ]
        stream_apartment_status: list[int] = []
        worker_result: list[str] = []

        def verify_com_initialized_before_play(*_args: object, **_kwargs: object) -> None:
            apartment = ctypes.c_int()
            qualifier = ctypes.c_int()
            stream_apartment_status.append(
                int(ole32.CoGetApartmentType(ctypes.byref(apartment), ctypes.byref(qualifier)))
            )

        sounddevice.play.side_effect = verify_com_initialized_before_play
        soundfile = Mock()
        soundfile.read.return_value = (np.zeros((4, 2), dtype=np.float32), 48000)

        def send_on_worker_thread() -> None:
            try:
                audio_output.send_wav_to_virtual_mic(Path("clone.wav"), 0)
            except Exception as exc:
                worker_result.append(str(exc))

        with patch.object(
            audio_output,
            "_audio_libraries",
            return_value=(np, sounddevice, soundfile, None),
        ):
            worker = threading.Thread(target=send_on_worker_thread)
            worker.start()
            worker.join()

        self.assertEqual(worker_result, [])
        self.assertEqual(stream_apartment_status, [0])


if __name__ == "__main__":
    unittest.main()
