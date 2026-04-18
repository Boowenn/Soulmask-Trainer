from __future__ import annotations

import unittest

from soulmask_trainer.catalog import MODULES, normalize_preset_value
from soulmask_trainer.data import SettingMeta


class CatalogTests(unittest.TestCase):
    def test_experience_module_is_registered(self) -> None:
        keys = [module.key for module in MODULES]
        self.assertIn("experience", keys)
        self.assertIn("combat", keys)
        self.assertIn("drops", keys)

    def test_numeric_preset_values_are_clamped(self) -> None:
        meta = SettingMeta(
            key="ExpRatio",
            label="经验倍率",
            min_value=0.1,
            max_value=5,
            default_value=1,
            is_toggle=False,
            is_visible=True,
            step=0,
        )
        self.assertEqual(normalize_preset_value(meta, 50), 5)
        self.assertEqual(normalize_preset_value(meta, 0), 0.1)

    def test_toggle_preset_values_map_to_integer_switches(self) -> None:
        meta = SettingMeta(
            key="JingShenNoXiaoHao",
            label="精神开关",
            min_value=0,
            max_value=1,
            default_value=0,
            is_toggle=True,
            is_visible=True,
            step=1,
        )
        self.assertEqual(normalize_preset_value(meta, True), 1)
        self.assertEqual(normalize_preset_value(meta, False), 0)


if __name__ == "__main__":
    unittest.main()
