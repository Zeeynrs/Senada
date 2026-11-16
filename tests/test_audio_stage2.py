import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from senada.config import format_for_quality
from senada.crossfade import CrossfadeEngine
from senada.effects import AudioEffects, PRESETS
from senada.engine import filter_audio_devices, parse_audio_device_help
from senada.player import Player
from senada.streams import StreamResolver
from tests.test_playback_extras import FakeResolver, FakeStore, IdleEngine, SyncWorker

APP = QCoreApplication.instance() or QCoreApplication([])


SAMPLE_MPV_HELP = """List of detected audio devices:
  'auto' (Autoselect device)
  'pipewire' (Default (pipewire))
  'pipewire/alsa_output.pci-0000_00_1f.3.analog-stereo' (Built-in Audio Analog Stereo)
  'pulse/alsa_output.pci-0000_00_1f.3.analog-stereo' (Built-in Audio Analog Stereo)
  'alsa' (Default (alsa))
  'alsa/surround51:CARD=PCH,DEV=0' (HDA Intel PCH, Surround 5.1)
  'alsa/hdmi:CARD=PCH,DEV=0' (HDA Intel PCH, HDMI 0)
  'jack' (Default (jack))
  'openal' (Default (openal))
  'sdl' (Default (sdl))
"""


class AudioDeviceFilterTests(unittest.TestCase):
    def test_parses_and_filters_redundant_backends(self):
        parsed = parse_audio_device_help(SAMPLE_MPV_HELP)
        self.assertEqual(parsed[0]["name"], "auto")
        filtered = filter_audio_devices(parsed)
        ids = [d["id"] for d in filtered]
        self.assertEqual(ids, [
            "auto",
            "pipewire/alsa_output.pci-0000_00_1f.3.analog-stereo",
            "alsa/hdmi:CARD=PCH,DEV=0",
        ])

    def test_keeps_active_device_even_if_otherwise_filtered(self):
        parsed = parse_audio_device_help(SAMPLE_MPV_HELP)
        filtered = filter_audio_devices(parsed, active_id="jack")
        self.assertIn("jack", [d["id"] for d in filtered])


class FakeDeviceEngine(IdleEngine):
    def __init__(self, tag=""):
        super().__init__()
        self.tag = tag
        self._devs = []
        self._dev = "auto"
        self.set_devices_calls = []
        self.set_quality_calls = []

    def audio_devices(self):
        return list(self._devs)

    def audio_device(self):
        return self._dev

    def set_audio_device(self, dev):
        self._dev = dev
        self.set_devices_calls.append(dev)

    def set_quality(self, q):
        self.set_quality_calls.append(q)

    def set_crossfade_helper(self):
        pass


class PlayerDeviceAndQualityTests(unittest.TestCase):
    def test_transfer_persists_device_and_updates_active(self):
        settings = {"audio_quality": "high", "device_name": "Desktop"}
        engine = FakeDeviceEngine()
        engine._devs = [
            {"id": "auto", "description": "Autoselect device"},
            {"id": "pipewire/dac", "description": "USB DAC"},
        ]
        p = Player(SyncWorker(), engine, FakeResolver({}), settings, FakeStore(), None)
        p.refreshDevices()
        self.assertEqual(p.devices[0]["id"], "auto")
        self.assertTrue(p.devices[0]["active"])

        p.transfer("pipewire/dac")
        self.assertEqual(settings["audio_device"], "pipewire/dac")
        self.assertEqual(engine.set_devices_calls[-1], "pipewire/dac")
        self.assertEqual(p.state["deviceId"], "pipewire/dac")
        self.assertEqual(p.state["deviceName"], "USB DAC")
        self.assertFalse(p.devices[0]["active"])
        self.assertTrue(p.devices[1]["active"])

    def test_quality_setting_updates_streams_and_engine(self):
        settings = {"audio_quality": "best"}
        engine = FakeDeviceEngine()
        p = Player(SyncWorker(), engine, FakeResolver({}), settings, FakeStore(), None)
        p.streams._cache["vid1"] = {"url": "https://old", "expires": 9999999999, "available": 0}
        self.assertEqual(p.streams.quality, "best")
        self.assertEqual(format_for_quality("high"), "bestaudio[abr<=160]/bestaudio/best")
        self.assertEqual(format_for_quality("medium"), "bestaudio[abr<=128]/bestaudio/best")

        settings["audio_quality"] = "medium"
        p.applyAudioSettings()
        self.assertEqual(p.streams.quality, "medium")
        self.assertEqual(p.streams._cache, {})
        self.assertEqual(engine.set_quality_calls[-1], "medium")

    def test_crossfade_forwards_device_and_quality_to_all_engines(self):
        created = []

        def make(tag):
            eng = FakeDeviceEngine(tag)
            created.append(eng)
            return eng

        cf = CrossfadeEngine(make_engine=make)
        cf.set_audio_device("pipewire/dac")
        cf.set_quality("high")
        cf.set_crossfade(4)
        self.assertEqual(len(created), 2)
        for eng in created:
            self.assertEqual(eng.set_devices_calls[-1], "pipewire/dac")
            self.assertEqual(eng.set_quality_calls[-1], "high")


class CustomPresetTests(unittest.TestCase):
    def test_save_use_and_delete_custom_presets(self):
        settings = {"effects": {}}
        fx = AudioEffects(settings)
        self.assertFalse(fx.isCustomPreset("Flat"))
        self.assertFalse(fx.savePreset("Flat"))  # cannot overwrite built-in
        self.assertFalse(fx.savePreset("   "))

        fx.setBand(0, 0.75)
        fx.setBand(5, -0.4)
        self.assertTrue(fx.savePreset("Late Night"))
        self.assertEqual(fx.preset, "Late Night")
        self.assertTrue(fx.isCustomPreset("Late Night"))
        self.assertIn("Late Night", fx.presetNames)

        # Reloading from settings keeps the custom preset
        fx2 = AudioEffects(settings)
        self.assertIn("Late Night", fx2.presetNames)
        self.assertAlmostEqual(fx2.bands[0], 0.75)

        fx2.usePreset("Rock")
        self.assertEqual(fx2.preset, "Rock")
        fx2.usePreset("Late Night")
        self.assertAlmostEqual(fx2.bands[0], 0.75)
        self.assertAlmostEqual(fx2.bands[5], -0.4)

        fx2.deletePreset("Late Night")
        self.assertNotIn("Late Night", fx2.presetNames)
        self.assertEqual(fx2.preset, "Custom")
        self.assertEqual(len(fx2.presetNames), len(PRESETS))


if __name__ == "__main__":
    unittest.main()
