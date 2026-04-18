from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from soulmask_trainer.data import SettingMeta


@dataclass(frozen=True)
class ModulePreset:
    name: str
    description: str
    values: dict[str, Any]


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    title: str
    description: str
    fields: tuple[str, ...]
    presets: tuple[ModulePreset, ...] = ()


def normalize_preset_value(meta: SettingMeta, value: Any) -> float | int:
    if meta.is_toggle:
        return 1 if bool(value) else 0

    numeric_value = float(value)
    if meta.min_value is not None:
        numeric_value = max(float(meta.min_value), numeric_value)
    if meta.max_value is not None:
        numeric_value = min(float(meta.max_value), numeric_value)

    numeric_markers = [marker for marker in (meta.default_value, meta.min_value, meta.max_value) if marker is not None]
    is_integer_field = bool(numeric_markers) and all(
        not isinstance(marker, bool) and float(marker).is_integer()
        for marker in numeric_markers
    )
    if is_integer_field:
        return int(round(numeric_value))
    return numeric_value


MODULES: tuple[ModuleDefinition, ...] = (
    ModuleDefinition(
        key="experience",
        title="经验与等级",
        description="聚焦成长效率相关参数，方便快速升级、训练和满级体验。",
        fields=(
            "ExpRatio",
            "ChengZhangExpRatio",
            "MJExpRatio",
            "ShuLianDuExpRatio",
            "CaiJiExpRatio",
            "ZhiZuoExpRatio",
            "ShaGuaiExpRatio",
            "QiTaExpRatio",
            "TrainingExpRatio",
            "MaxLevel",
        ),
        presets=(
            ModulePreset(
                name="快速成长",
                description="经验倍率整体拉高，适合前期加速。",
                values={
                    "ExpRatio": 5,
                    "ChengZhangExpRatio": 5,
                    "MJExpRatio": 5,
                    "ShuLianDuExpRatio": 5,
                    "CaiJiExpRatio": 5,
                    "ZhiZuoExpRatio": 5,
                    "ShaGuaiExpRatio": 5,
                    "QiTaExpRatio": 5,
                    "TrainingExpRatio": 10,
                },
            ),
            ModulePreset(
                name="极速升级",
                description="把可编辑经验项推到更高区间，适合快速开档。",
                values={
                    "ExpRatio": 20,
                    "ChengZhangExpRatio": 20,
                    "MJExpRatio": 20,
                    "ShuLianDuExpRatio": 20,
                    "CaiJiExpRatio": 20,
                    "ZhiZuoExpRatio": 20,
                    "ShaGuaiExpRatio": 20,
                    "QiTaExpRatio": 20,
                    "TrainingExpRatio": 50,
                },
            ),
            ModulePreset(
                name="满级体验",
                description="直接把等级上限拉满，并尽量提升成长速度。",
                values={
                    "ExpRatio": 50,
                    "ChengZhangExpRatio": 50,
                    "MJExpRatio": 50,
                    "ShuLianDuExpRatio": 50,
                    "CaiJiExpRatio": 50,
                    "ZhiZuoExpRatio": 50,
                    "ShaGuaiExpRatio": 50,
                    "QiTaExpRatio": 50,
                    "TrainingExpRatio": 999,
                    "MaxLevel": 60,
                },
            ),
        ),
    ),
)
