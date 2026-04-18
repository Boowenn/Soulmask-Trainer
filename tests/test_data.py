from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from soulmask_trainer.data import (
    TrainerRepository,
    build_full_value_diff,
    build_value_diff,
    detect_text_encoding,
    get_changed_values,
    read_json_object,
    sanitize_file_component,
    snapshot_matches_keyword,
)


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

    def test_save_profiles_updates_multiple_targets(self) -> None:
        backup_paths = self.repository.save_profiles(
            ["GameXishu_Template.json", "GameXishu_Template_PVP.json"],
            {"ExpRatio": 9},
        )
        pve_payload, _ = read_json_object(self.settings_dir / "GameXishu_Template.json")
        pvp_payload, _ = read_json_object(self.settings_dir / "GameXishu_Template_PVP.json")

        self.assertEqual(set(backup_paths.keys()), {"GameXishu_Template.json", "GameXishu_Template_PVP.json"})
        self.assertEqual(pve_payload["0"]["ExpRatio"], 9)
        self.assertEqual(pvp_payload["0"]["ExpRatio"], 9)

    def test_export_and_import_preset_round_trip(self) -> None:
        preset_path = self.settings_dir / "my-preset.json"
        values = {"ExpRatio": 7, "JingShenNoXiaoHao": 1}

        self.repository.export_preset(preset_path, "GameXishu_Template.json", values)
        imported = self.repository.import_preset(preset_path)
        raw_payload = json.loads(preset_path.read_text(encoding="utf-8"))

        self.assertEqual(imported.source_profile, "GameXishu_Template.json")
        self.assertEqual(imported.values, values)
        self.assertEqual(raw_payload["values"], values)
        self.assertEqual(raw_payload["schema_version"], 1)

    def test_recent_presets_keep_latest_existing_entries(self) -> None:
        first_preset = self.settings_dir / "preset-a.json"
        second_preset = self.settings_dir / "preset-b.json"
        self.repository.export_preset(first_preset, "GameXishu_Template.json", {"ExpRatio": 3})
        self.repository.export_preset(second_preset, "GameXishu_Template.json", {"ExpRatio": 4})

        self.repository.record_recent_preset(first_preset, "GameXishu_Template.json", "导出")
        self.repository.record_recent_preset(second_preset, "GameXishu_Template.json", "导入")
        recent_entries = self.repository.list_recent_presets(limit=5)

        self.assertEqual([entry.path.name for entry in recent_entries], ["preset-b.json", "preset-a.json"])
        self.assertEqual(recent_entries[0].action, "导入")

        second_preset.unlink()
        filtered_entries = self.repository.list_recent_presets(limit=5)
        self.assertEqual([entry.path.name for entry in filtered_entries], ["preset-a.json"])

    def test_recent_presets_support_remove_cleanup_and_clear(self) -> None:
        first_preset = self.settings_dir / "preset-a.json"
        second_preset = self.settings_dir / "preset-b.json"
        self.repository.export_preset(first_preset, "GameXishu_Template.json", {"ExpRatio": 3})
        self.repository.export_preset(second_preset, "GameXishu_Template.json", {"ExpRatio": 4})

        self.repository.record_recent_preset(first_preset, "GameXishu_Template.json", "export")
        self.repository.record_recent_preset(second_preset, "GameXishu_Template.json", "import")

        self.assertTrue(self.repository.remove_recent_preset(first_preset))
        self.assertEqual(
            [entry.path.name for entry in self.repository.list_recent_presets(limit=5)],
            ["preset-b.json"],
        )

        second_preset.unlink()
        self.assertEqual(self.repository.cleanup_missing_recent_presets(), 1)
        self.assertEqual(self.repository.list_recent_presets(limit=5), [])

        self.repository.export_preset(first_preset, "GameXishu_Template.json", {"ExpRatio": 5})
        self.repository.record_recent_preset(first_preset, "GameXishu_Template.json", "export")
        self.assertEqual(self.repository.clear_recent_presets(), 1)
        self.assertEqual(self.repository.list_recent_presets(limit=5), [])

    def test_create_and_list_snapshots(self) -> None:
        first_snapshot = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 2},
            "开荒档",
        )
        second_snapshot = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 6, "JingShenNoXiaoHao": 1},
            "毕业档",
        )

        loaded_snapshot = self.repository.load_snapshot(first_snapshot)
        listed_snapshots = self.repository.list_snapshots("GameXishu_Template.json", limit=5)

        self.assertEqual(loaded_snapshot.snapshot_name, "开荒档")
        self.assertEqual(loaded_snapshot.values["ExpRatio"], 2)
        self.assertEqual([snapshot.path.name for snapshot in listed_snapshots], [second_snapshot.name, first_snapshot.name])
        self.assertEqual(listed_snapshots[0].snapshot_name, "毕业档")

    def test_rename_snapshot_updates_metadata_and_filename(self) -> None:
        snapshot_path = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 2},
            "开荒档",
        )

        renamed_path = self.repository.rename_snapshot(snapshot_path, "终局档")
        renamed_snapshot = self.repository.load_snapshot(renamed_path)

        self.assertNotEqual(renamed_path.name, snapshot_path.name)
        self.assertFalse(snapshot_path.exists())
        self.assertTrue(renamed_path.is_file())
        self.assertEqual(renamed_snapshot.snapshot_name, "终局档")

    def test_delete_snapshot_removes_file_and_empty_directory(self) -> None:
        snapshot_path = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 2},
            "临时档",
        )
        snapshot_dir = snapshot_path.parent

        self.repository.delete_snapshot(snapshot_path)

        self.assertFalse(snapshot_path.exists())
        self.assertFalse(snapshot_dir.exists())


    def test_snapshot_notes_persist_and_update(self) -> None:
        snapshot_path = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 2},
            "Boss Prep",
            "Before first boss",
        )

        loaded_snapshot = self.repository.load_snapshot(snapshot_path)
        self.assertEqual(loaded_snapshot.snapshot_note, "Before first boss")
        self.assertTrue(snapshot_matches_keyword(loaded_snapshot, "boss"))
        self.assertTrue(snapshot_matches_keyword(loaded_snapshot, "first boss"))
        self.assertFalse(snapshot_matches_keyword(loaded_snapshot, "farming"))

        updated_snapshot = self.repository.update_snapshot_note(snapshot_path, "Before arena retry")
        self.assertEqual(updated_snapshot.snapshot_note, "Before arena retry")
        self.assertEqual(self.repository.load_snapshot(snapshot_path).snapshot_note, "Before arena retry")

    def test_rename_snapshot_preserves_note(self) -> None:
        snapshot_path = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 2},
            "Named Snapshot",
            "Keep this note",
        )

        renamed_path = self.repository.rename_snapshot(snapshot_path, "Renamed Snapshot")
        renamed_snapshot = self.repository.load_snapshot(renamed_path)

        self.assertEqual(renamed_snapshot.snapshot_note, "Keep this note")


    def test_snapshot_category_and_favorite_persist_and_update(self) -> None:
        snapshot_path = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 2},
            "Boss Prep",
            "Before first boss",
            "Boss",
            True,
        )

        loaded_snapshot = self.repository.load_snapshot(snapshot_path)
        self.assertEqual(loaded_snapshot.snapshot_category, "Boss")
        self.assertTrue(loaded_snapshot.is_favorite)
        self.assertTrue(snapshot_matches_keyword(loaded_snapshot, "boss"))

        updated_category = self.repository.update_snapshot_category(snapshot_path, "Arena")
        self.assertEqual(updated_category.snapshot_category, "Arena")
        self.assertTrue(snapshot_matches_keyword(updated_category, "arena"))

        unfavorited_snapshot = self.repository.set_snapshot_favorite(snapshot_path, False)
        self.assertFalse(unfavorited_snapshot.is_favorite)

    def test_rename_snapshot_preserves_category_and_favorite(self) -> None:
        snapshot_path = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 2},
            "Named Snapshot",
            "Keep this note",
            "Builds",
            True,
        )

        renamed_path = self.repository.rename_snapshot(snapshot_path, "Renamed Snapshot")
        renamed_snapshot = self.repository.load_snapshot(renamed_path)

        self.assertEqual(renamed_snapshot.snapshot_category, "Builds")
        self.assertTrue(renamed_snapshot.is_favorite)

    def test_duplicate_snapshot_preserves_metadata_and_values(self) -> None:
        snapshot_path = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 7, "JingShenNoXiaoHao": 1},
            "Boss Prep",
            "Before final push",
            "Boss",
            True,
        )

        duplicate_path = self.repository.duplicate_snapshot(snapshot_path)
        original_snapshot = self.repository.load_snapshot(snapshot_path)
        duplicate_snapshot = self.repository.load_snapshot(duplicate_path)

        self.assertNotEqual(duplicate_path, snapshot_path)
        self.assertTrue(duplicate_path.is_file())
        self.assertEqual(duplicate_snapshot.snapshot_name, "Boss Prep-copy")
        self.assertEqual(duplicate_snapshot.snapshot_note, original_snapshot.snapshot_note)
        self.assertEqual(duplicate_snapshot.snapshot_category, original_snapshot.snapshot_category)
        self.assertEqual(duplicate_snapshot.is_favorite, original_snapshot.is_favorite)
        self.assertEqual(duplicate_snapshot.values, original_snapshot.values)

    def test_duplicate_snapshot_supports_custom_name(self) -> None:
        snapshot_path = self.repository.create_snapshot(
            "GameXishu_Template.json",
            {"ExpRatio": 2},
            "Starter Build",
        )

        duplicate_path = self.repository.duplicate_snapshot(snapshot_path, "Arena Retry")
        duplicate_snapshot = self.repository.load_snapshot(duplicate_path)

        self.assertEqual(duplicate_snapshot.snapshot_name, "Arena Retry")
        self.assertEqual(duplicate_snapshot.values["ExpRatio"], 2)


class EncodingTests(unittest.TestCase):
    def test_detect_utf16_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            path = Path(temp_dir_name) / "utf16.json"
            path.write_text(CONFIG_TEXT, encoding="utf-16")
            self.assertEqual(detect_text_encoding(path), "utf-16")


class ValueDiffTests(unittest.TestCase):
    def test_get_changed_values_returns_only_modified_entries(self) -> None:
        original = {"ExpRatio": 1, "JingShenNoXiaoHao": 0, "DamageYeShengRatio": 1.5}
        current = {"ExpRatio": 5, "JingShenNoXiaoHao": 0, "DamageYeShengRatio": 0.5}

        changed = get_changed_values(original, current)

        self.assertEqual(changed, {"ExpRatio": 5, "DamageYeShengRatio": 0.5})

    def test_build_value_diff_skips_equal_values(self) -> None:
        current = {"ExpRatio": 1, "JingShenNoXiaoHao": 0}
        incoming = {"ExpRatio": 3, "JingShenNoXiaoHao": 0, "NewField": 9}

        diff = build_value_diff(current, incoming)

        self.assertEqual(len(diff), 2)
        self.assertEqual(diff[0].key, "ExpRatio")
        self.assertEqual(diff[0].before, 1)
        self.assertEqual(diff[0].after, 3)
        self.assertEqual(diff[1].key, "NewField")
        self.assertIsNone(diff[1].before)
        self.assertEqual(diff[1].after, 9)

    def test_build_full_value_diff_reports_removed_and_added_keys(self) -> None:
        before = {"ExpRatio": 2, "MaxLevel": 40}
        after = {"ExpRatio": 4, "TrainingExpRatio": 8}

        diff = build_full_value_diff(before, after)

        self.assertEqual(
            [(item.key, item.before, item.after) for item in diff],
            [
                ("ExpRatio", 2, 4),
                ("MaxLevel", 40, None),
                ("TrainingExpRatio", None, 8),
            ],
        )

    def test_sanitize_file_component_replaces_windows_unsafe_characters(self) -> None:
        sanitized = sanitize_file_component('毕业档: Build/Final?*', 'snapshot')
        self.assertEqual(sanitized, "毕业档_ Build_Final__")


if __name__ == "__main__":
    unittest.main()
