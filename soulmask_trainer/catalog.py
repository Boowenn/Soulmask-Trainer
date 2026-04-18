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
    ModuleDefinition(
        key="combat",
        title="战斗系统",
        description="调节玩家、野生动物、蛮人和建筑相关伤害，并附带 PVP 系数入口。",
        fields=(
            "DamageYeShengRatio",
            "BeDamageByYeShengRatio",
            "DongWuDamageRatio",
            "DongWuTiLiDamageRatio",
            "DongWuTenacityDamageRatio",
            "MaRenDamageRatio",
            "ManRenTiLiDamageRatio",
            "ManRenTenacityDamageRatio",
            "CaiJiDamageRatio",
            "GongJiJianZhuDamageRatio",
            "PVP_GAPVPDamageRatio",
            "PVP_ShangHaiRatio_JinZhan",
            "PVP_ShangHaiRatio_YuanCheng",
            "PVP_ShangHaiRatio_PlayerToPlayer_DiFang",
            "PVP_ShangHaiRatio_PlayerToPlayer_YouFang",
            "WanJiaBeiXiaoRenRatio",
            "WanJiaBeiXiaoTiRatio",
        ),
        presets=(
            ModulePreset(
                name="无双模式",
                description="显著提高输出，并把承伤压到极低。",
                values={
                    "DamageYeShengRatio": 10,
                    "BeDamageByYeShengRatio": 0.1,
                    "DongWuDamageRatio": 0.5,
                    "MaRenDamageRatio": 0.5,
                    "CaiJiDamageRatio": 10,
                    "GongJiJianZhuDamageRatio": 10,
                    "PVP_GAPVPDamageRatio": 5,
                    "PVP_ShangHaiRatio_JinZhan": 1,
                    "PVP_ShangHaiRatio_YuanCheng": 1,
                    "PVP_ShangHaiRatio_PlayerToPlayer_DiFang": 5,
                    "PVP_ShangHaiRatio_PlayerToPlayer_YouFang": 0,
                },
            ),
            ModulePreset(
                name="真实战斗",
                description="略微拉高双方伤害，保留更多博弈感。",
                values={
                    "DamageYeShengRatio": 1.5,
                    "BeDamageByYeShengRatio": 1.5,
                    "DongWuDamageRatio": 1.5,
                    "MaRenDamageRatio": 1.5,
                    "PVP_ShangHaiRatio_JinZhan": 0.8,
                    "PVP_ShangHaiRatio_YuanCheng": 0.8,
                    "PVP_ShangHaiRatio_PlayerToPlayer_DiFang": 1.5,
                },
            ),
            ModulePreset(
                name="据点攻坚",
                description="偏向打据点和拆建筑的数值组合。",
                values={
                    "DamageYeShengRatio": 5,
                    "CaiJiDamageRatio": 5,
                    "GongJiJianZhuDamageRatio": 10,
                    "PVP_GAPVPDamageRatio": 5,
                    "PVP_ShangHaiRatio_JinZhan": 1,
                    "PVP_ShangHaiRatio_YuanCheng": 1,
                    "PVP_ShangHaiRatio_PlayerToPlayer_DiFang": 3,
                    "PVP_ShangHaiRatio_PlayerToPlayer_YouFang": 0,
                },
            ),
        ),
    ),
)
