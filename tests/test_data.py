from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from soulmask_trainer.data import TrainerRepository, detect_text_encoding, read_json_object


PROFILE_TEXT = """{
\t"0":
\t{
\t\t"ExpRatio": 1,
\t\t"DamageYeShengRatio": 1.5,
\t\t"JingShenNoXiaoHao": 0
\t}
}
"""

CONFIG_TEXT = """{
\t"0":
\t{
\t\t"ExpRatio":
\t\t{
\t\t\t"Desc": "经验倍率",
\t\t\t"IsKaiGuan": false,
\t\t\t"XiShuDefaultValue": 1,
\t\t\t"XiShuMinValue": 0.1,
\t\t\t"XiShuMaxValue": 5,
\t\t\t"XiShuStep": 0,
\t\t\t"IsShow": true
\t\t},
\t\t"JingShenNoXiaoHao":
\t\t{
\t\t\t"Desc": "精神开关",
\t\t\t"IsKaiGuan": true,
\t\t\t"XiShuDefaultValue": 0,
\t\t\t"XiShuMinValue": 0,
\t\t\t"XiShuMaxValue": 1,
\t\t\t"XiShuStep": 1,
\t\t\t"IsShow": true
\t\t}
\t}
}
"""


class TrainerRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_dir = Path(self.temp_dir.name) / "WS" / "Config" / "GameplaySettings"
        self.settings_dir.mkdir(parents=True)

        (self.settings_dir / "GameXishu_Template.json").write_text(PROFILE_TEXT, encoding="utf-8")
        (self.settings_dir / "GameXishu_Template_PVP.json").write_text(PROFILE_TEXT, encoding="utf-8")
        (self.settings_dir / "GameXishuConfig_Template.json").write_text(CONFIG_TEXT, encoding="utf-16")
        (self.settings_dir / "GameXishuConfig_Template_PVP.json").write_text(CONFIG_TEXT, encoding="utf-16")

        self.repository = TrainerRepository(self.settings_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_discover_settings_dir(self) -> None:
        discovered = TrainerRepository.discover_settings_dir(Path(self.temp_dir.name))
        self.assertIsNotNone(discovered)
        self.assertTrue(discovered.samefile(self.settings_dir))

    def test_list_profiles_ignores_config_templates(self) -> None:
        profiles = [path.name for path in self.repository.list_profiles()]
        self.assertEqual(profiles, ["GameXishu_Template.json", "GameXishu_Template_PVP.json"])

    def test_load_profile_reads_values_and_metadata(self) -> None:
        loaded = self.repository.load_profile("GameXishu_Template.json")
        self.assertEqual(loaded.values["ExpRatio"], 1)
        self.assertTrue(loaded.metadata["JingShenNoXiaoHao"].is_toggle)
        self.assertEqual(loaded.config_path.name, "GameXishuConfig_Template.json")

    def test_load_pvp_profile_uses_pvp_metadata(self) -> None:
        loaded = self.repository.load_profile("GameXishu_Template_PVP.json")
        self.assertEqual(loaded.config_path.name, "GameXishuConfig_Template_PVP.json")

    def test_save_creates_backup_and_preserves_encoding(self) -> None:
        loaded = self.repository.load_profile("GameXishu_Template.json")
        updated_values = dict(loaded.values)
        updated_values["ExpRatio"] = 4

        backup_path = self.repository.save_profile(loaded, updated_values)
        payload, encoding = read_json_object(loaded.profile_path)

        self.assertTrue(backup_path.is_file())
        self.assertEqual(encoding, "utf-8")
        self.assertEqual(payload["0"]["ExpRatio"], 4)

    def test_restore_latest_backup(self) -> None:
        loaded = self.repository.load_profile("GameXishu_Template.json")
        updated_values = dict(loaded.values)
        updated_values["ExpRatio"] = 4
        self.repository.save_profile(loaded, updated_values)

        loaded.profile_path.write_text(PROFILE_TEXT.replace('"ExpRatio": 1', '"ExpRatio": 2'), encoding="utf-8")
        restored_path = self.repository.restore_latest_backup("GameXishu_Template.json")
        payload, _encoding = read_json_object(loaded.profile_path)

        self.assertTrue(restored_path.is_file())
        self.assertEqual(payload["0"]["ExpRatio"], 1)


class EncodingTests(unittest.TestCase):
    def test_detect_utf16_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            path = Path(temp_dir_name) / "utf16.json"
            path.write_text(CONFIG_TEXT, encoding="utf-16")
            self.assertEqual(detect_text_encoding(path), "utf-16")


if __name__ == "__main__":
    unittest.main()
