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


@dataclass(frozen=True)
class EasyPreset:
    name: str
    description: str
    values: dict[str, Any]


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


EASY_FIELDS: tuple[str, ...] = (
    "ExpRatio",
    "TrainingExpRatio",
    "MaxLevel",
    "DamageYeShengRatio",
    "BeDamageByYeShengRatio",
    "CaiJiDiaoLuoRatio",
    "BaoXiangDropRatio",
    "TiLiHuiFuRatio",
    "ShiWuXiaoHaoRatio",
    "JingShenNoXiaoHao",
    "ZhiZuoTimeRatio",
    "JianZhuFuLanKaiGuan",
    "XiuLiXuYaoCaiLiaoRatio",
    "AddRenKeDuRatio",
    "GongHuiMaxZhaoMuCount",
    "DongWuShengZhangRatio",
    "DongWuChuZhanCount",
    "NaiJiuXiShu",
)


EASY_PRESETS: tuple[EasyPreset, ...] = (
    EasyPreset(
        name="轻松开荒",
        description="适合新档上手，兼顾升级、掉落、恢复与制作速度。",
        values={
            "ExpRatio": 5,
            "TrainingExpRatio": 10,
            "CaiJiDiaoLuoRatio": 3,
            "BaoXiangDropRatio": 3,
            "TiLiHuiFuRatio": 5,
            "ShiWuXiaoHaoRatio": 0.5,
            "ZhiZuoTimeRatio": 3,
            "AddRenKeDuRatio": 5,
        },
    ),
    EasyPreset(
        name="无双单人",
        description="偏战斗的单人爽玩方案，减伤更低、输出更高、装备更耐用。",
        values={
            "DamageYeShengRatio": 5,
            "BeDamageByYeShengRatio": 0.2,
            "TiLiHuiFuRatio": 10,
            "JingShenNoXiaoHao": 1,
            "NaiJiuXiShu": 0,
            "DongWuChuZhanCount": 20,
        },
    ),
    EasyPreset(
        name="基建创造",
        description="偏建造和生产，减少材料压力并放大基地效率。",
        values={
            "ZhiZuoTimeRatio": 5,
            "JianZhuFuLanKaiGuan": 0,
            "XiuLiXuYaoCaiLiaoRatio": 0,
            "ShiWuXiaoHaoRatio": 0.2,
            "GongHuiMaxZhaoMuCount": 200,
        },
    ),
    EasyPreset(
        name="养老种田",
        description="更轻松的生存节奏，偏向养殖、储存和低消耗。",
        values={
            "ShiWuXiaoHaoRatio": 0,
            "JingShenNoXiaoHao": 1,
            "TiLiHuiFuRatio": 10,
            "DongWuShengZhangRatio": 20,
            "CaiJiDiaoLuoRatio": 3,
            "BaoXiangDropRatio": 3,
            "NaiJiuXiShu": 0.2,
        },
    ),
    EasyPreset(
        name="部落领主",
        description="适合部落经营，强化招募、动物规模与成长节奏。",
        values={
            "AddRenKeDuRatio": 10,
            "GongHuiMaxZhaoMuCount": 500,
            "DongWuShengZhangRatio": 50,
            "DongWuChuZhanCount": 50,
            "MaxLevel": 60,
            "ExpRatio": 10,
        },
    ),
)


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
    ModuleDefinition(
        key="drops",
        title="掉落与物品",
        description="集中调节采集、怪物、宝箱和自动化产出倍率。",
        fields=(
            "CaiJiDiaoLuoRatio",
            "FaMuDiaoLuoRatio",
            "CaiKuangDiaoLuoRatio",
            "DongWuShiTiDiaoLuoRatio",
            "DongWuShiTiZhongYaoDiaoLuoRatio",
            "PuTongRenDiaoLuoRatio",
            "JingYingRenDiaoLuoRatio",
            "BossRenDiaoLuoRatio",
            "ZuoWuDropRatio",
            "BaoXiangDropRatio",
            "CaiJiShengChanJianZhuDiaoLuoRatio",
        ),
        presets=(
            ModulePreset(
                name="丰收模式",
                description="整体提升到温和的高收益区间。",
                values={
                    "CaiJiDiaoLuoRatio": 3,
                    "FaMuDiaoLuoRatio": 3,
                    "CaiKuangDiaoLuoRatio": 3,
                    "DongWuShiTiDiaoLuoRatio": 3,
                    "DongWuShiTiZhongYaoDiaoLuoRatio": 3,
                    "PuTongRenDiaoLuoRatio": 3,
                    "JingYingRenDiaoLuoRatio": 3,
                    "BossRenDiaoLuoRatio": 3,
                    "ZuoWuDropRatio": 3,
                    "BaoXiangDropRatio": 3,
                    "CaiJiShengChanJianZhuDiaoLuoRatio": 3,
                },
            ),
            ModulePreset(
                name="海量掉落",
                description="对常见掉落项目施加更激进的倍率。",
                values={
                    "CaiJiDiaoLuoRatio": 10,
                    "FaMuDiaoLuoRatio": 10,
                    "CaiKuangDiaoLuoRatio": 10,
                    "DongWuShiTiDiaoLuoRatio": 10,
                    "DongWuShiTiZhongYaoDiaoLuoRatio": 10,
                    "PuTongRenDiaoLuoRatio": 10,
                    "JingYingRenDiaoLuoRatio": 10,
                    "BossRenDiaoLuoRatio": 10,
                    "ZuoWuDropRatio": 10,
                    "BaoXiangDropRatio": 10,
                    "CaiJiShengChanJianZhuDiaoLuoRatio": 10,
                },
            ),
            ModulePreset(
                name="无尽财富",
                description="一键拉满所有掉落项，超出范围部分会自动裁剪。",
                values={
                    "CaiJiDiaoLuoRatio": 50,
                    "FaMuDiaoLuoRatio": 50,
                    "CaiKuangDiaoLuoRatio": 50,
                    "DongWuShiTiDiaoLuoRatio": 50,
                    "DongWuShiTiZhongYaoDiaoLuoRatio": 50,
                    "PuTongRenDiaoLuoRatio": 50,
                    "JingYingRenDiaoLuoRatio": 50,
                    "BossRenDiaoLuoRatio": 50,
                    "ZuoWuDropRatio": 50,
                    "BaoXiangDropRatio": 50,
                    "CaiJiShengChanJianZhuDiaoLuoRatio": 50,
                },
            ),
        ),
    ),
    ModuleDefinition(
        key="survival",
        title="生存与恢复",
        description="统一调整生命、体力、气息、精神与各类消耗倍率。",
        fields=(
            "ShengMingHuiFuRatio",
            "TiLiHuiFuRatio",
            "QiXiHuiFuRatio",
            "MentalRecoveryRate",
            "PhysicalRecoveryIntervalRate",
            "FuHuaSpeed",
            "ShiWuXiaoHaoRatio",
            "ShuiXiaoHaoRatio",
            "ZuoWuShuiXiaoHaoRatio",
            "ZuoWuFeiLiaoXiaoHaoRatio",
            "DongWuXiaoHaoShiWuRatio",
            "DongWuXiaoHaoShuiRatio",
            "QiXiXiaoHaoRatio",
            "RanLiaoXiaoHaoRatio",
            "JingShenNoXiaoHao",
        ),
        presets=(
            ModulePreset(
                name="铁人模式",
                description="整体提升恢复，同时显著降低日常消耗。",
                values={
                    "ShengMingHuiFuRatio": 5,
                    "TiLiHuiFuRatio": 5,
                    "QiXiHuiFuRatio": 5,
                    "MentalRecoveryRate": 5,
                    "FuHuaSpeed": 5,
                    "ShiWuXiaoHaoRatio": 0.2,
                    "ShuiXiaoHaoRatio": 0.2,
                    "DongWuXiaoHaoShiWuRatio": 0.2,
                    "DongWuXiaoHaoShuiRatio": 0.2,
                    "QiXiXiaoHaoRatio": 0.2,
                    "RanLiaoXiaoHaoRatio": 0.2,
                },
            ),
            ModulePreset(
                name="无饥无渴",
                description="把常见生存消耗压到最低，并关闭精神消耗。",
                values={
                    "ShiWuXiaoHaoRatio": 0,
                    "ShuiXiaoHaoRatio": 0,
                    "ZuoWuShuiXiaoHaoRatio": 0,
                    "ZuoWuFeiLiaoXiaoHaoRatio": 0,
                    "DongWuXiaoHaoShiWuRatio": 0,
                    "DongWuXiaoHaoShuiRatio": 0,
                    "QiXiXiaoHaoRatio": 0,
                    "RanLiaoXiaoHaoRatio": 0,
                    "JingShenNoXiaoHao": 1,
                },
            ),
            ModulePreset(
                name="永恒体力",
                description="重点强化体力、气息和精神恢复。",
                values={
                    "TiLiHuiFuRatio": 50,
                    "QiXiHuiFuRatio": 50,
                    "MentalRecoveryRate": 10,
                    "PhysicalRecoveryIntervalRate": 0,
                    "JingShenNoXiaoHao": 1,
                },
            ),
        ),
    ),
    ModuleDefinition(
        key="production",
        title="制造与生产",
        description="调节制作、转化、矿场、索道与船员效率相关参数。",
        fields=(
            "ZhiZuoTimeRatio",
            "ConverPropsSpeedRatio",
            "MaxConvertCount",
            "MaxConveyorCount",
            "MaxDiCiCount",
            "MaxDongLiKuangChangCount",
            "CrewCountRatio",
        ),
        presets=(
            ModulePreset(
                name="瞬间制造",
                description="尽量把制作和转化推到当前配置允许的最高区间。",
                values={
                    "ZhiZuoTimeRatio": 5,
                    "ConverPropsSpeedRatio": 10,
                    "MaxConvertCount": 10,
                },
            ),
            ModulePreset(
                name="工业帝国",
                description="显著放宽索道、矿场和陷阱等建造上限。",
                values={
                    "MaxConveyorCount": 10000,
                    "MaxDiCiCount": 1000,
                    "MaxDongLiKuangChangCount": 1000,
                    "CrewCountRatio": 10,
                },
            ),
            ModulePreset(
                name="全自动基地",
                description="兼顾制造速度、转化数量和船员效率的综合方案。",
                values={
                    "ZhiZuoTimeRatio": 3,
                    "ConverPropsSpeedRatio": 10,
                    "MaxConvertCount": 10,
                    "CrewCountRatio": 10,
                },
            ),
        ),
    ),
    ModuleDefinition(
        key="building",
        title="建筑系统",
        description="集中处理腐烂、修理、限高、传送门和平台建造限制。",
        fields=(
            "JianZhuFuLanMul",
            "JianZhuXiuLiMul",
            "JianZhuFuLanKaiGuan",
            "JianZhuAroundNumLimit",
            "JianZhuBeDamageLimit",
            "JianZhuGaoDuLimit",
            "JianZhuChuanSongMenPlusKaiGuan",
            "MaxPingTaiJianZhuNumMul",
            "PingTaiBuildRangeLimit",
            "MaxChuanSongMenNumber",
            "XiuLiXuYaoCaiLiaoRatio",
            "XiuLiJiangNaiJiuShangXianRatio",
            "ShipBlueprintBuildConsumeSwitch",
        ),
        presets=(
            ModulePreset(
                name="永恒城堡",
                description="关闭腐烂并强化修理，适合长期据点。",
                values={
                    "JianZhuFuLanMul": 0,
                    "JianZhuXiuLiMul": 10,
                    "JianZhuFuLanKaiGuan": 0,
                    "XiuLiXuYaoCaiLiaoRatio": 0,
                    "XiuLiJiangNaiJiuShangXianRatio": 0,
                },
            ),
            ModulePreset(
                name="无限建造",
                description="关闭常见建筑限制并放宽平台和传送门数量。",
                values={
                    "JianZhuAroundNumLimit": 0,
                    "JianZhuBeDamageLimit": 0,
                    "JianZhuGaoDuLimit": 0,
                    "PingTaiBuildRangeLimit": 0,
                    "MaxPingTaiJianZhuNumMul": 10,
                    "MaxChuanSongMenNumber": 100,
                },
            ),
            ModulePreset(
                name="创造模式",
                description="同时提供免费修理、免费船只和更自由的运输建筑。",
                values={
                    "JianZhuFuLanKaiGuan": 0,
                    "JianZhuChuanSongMenPlusKaiGuan": 1,
                    "JianZhuGaoDuLimit": 0,
                    "XiuLiXuYaoCaiLiaoRatio": 0,
                    "ShipBlueprintBuildConsumeSwitch": 0,
                    "MaxChuanSongMenNumber": 100,
                },
            ),
        ),
    ),
    ModuleDefinition(
        key="recruitment",
        title="NPC与招募",
        description="强化驯服速度、族人与动物上限、公会规模和营火数量。",
        fields=(
            "AddRenKeDuRatio",
            "GeRenMaxZhaoMuCount",
            "GeRenMaxZhaoMuCount_Two",
            "GeRenMaxZhaoMuCount_Three",
            "GongHuiMaxZhaoMuCount",
            "GeRenMaxDongWuCount",
            "GongHuiMaxDongWuCount",
            "AnimalFollowerMaxCount",
            "GongHuiMaxMember",
            "MaxGenRenYingHuoNumber",
            "MaxGongHuiYingHuoNumber",
            "ShuaXinNPCKaiGuan",
        ),
        presets=(
            ModulePreset(
                name="驯服大师",
                description="让招募和驯服流程更快，并提升个人招募容量。",
                values={
                    "AddRenKeDuRatio": 10,
                    "GeRenMaxZhaoMuCount": 10,
                    "GeRenMaxZhaoMuCount_Two": 20,
                    "GeRenMaxZhaoMuCount_Three": 100,
                },
            ),
            ModulePreset(
                name="部落扩编",
                description="显著提升公会人数、族人和营火上限。",
                values={
                    "GongHuiMaxZhaoMuCount": 1000,
                    "GongHuiMaxMember": 50,
                    "MaxGenRenYingHuoNumber": 100,
                    "MaxGongHuiYingHuoNumber": 100,
                },
            ),
            ModulePreset(
                name="动物军团",
                description="放宽个人和公会的动物总量与跟随数量。",
                values={
                    "GeRenMaxDongWuCount": 100,
                    "GongHuiMaxDongWuCount": 100,
                    "AnimalFollowerMaxCount": 100,
                    "ShuaXinNPCKaiGuan": 1,
                },
            ),
        ),
    ),
    ModuleDefinition(
        key="creatures",
        title="动物与成长",
        description="集中调整动物品质、生长、产出、繁殖和出战规模。",
        fields=(
            "DongWuPinZhiRatio",
            "ManRenPinZhiRatio",
            "DongWuShengZhangRatio",
            "DongWuChanChuRatio",
            "DongWuShengChanJianGeRatio",
            "FanZhiJianGeRatio",
            "DongWuBeiDongYiJiShuXingRatio",
            "DongWuZhuDongYiJiShuXingRatio",
            "DongWuErJiShuXingRatio",
            "MaRenBeiDongYiJiShuXingRatio",
            "MaRenZhuDongYiJiShuXingRatio",
            "DongWuChuZhanCount",
            "ManRenChuZhanCount",
            "JiQiChuZhanKaiGuan",
        ),
        presets=(
            ModulePreset(
                name="极品驯养",
                description="抬高动物与蛮人品质，并提升升级属性收益。",
                values={
                    "DongWuPinZhiRatio": 5,
                    "ManRenPinZhiRatio": 5,
                    "DongWuBeiDongYiJiShuXingRatio": 3,
                    "DongWuZhuDongYiJiShuXingRatio": 3,
                    "DongWuErJiShuXingRatio": 3,
                    "MaRenBeiDongYiJiShuXingRatio": 3,
                    "MaRenZhuDongYiJiShuXingRatio": 3,
                },
            ),
            ModulePreset(
                name="高产牧场",
                description="偏向养殖效率，提升生长、产出和繁殖速度。",
                values={
                    "DongWuShengZhangRatio": 100,
                    "DongWuChanChuRatio": 3,
                    "DongWuShengChanJianGeRatio": 5,
                    "FanZhiJianGeRatio": 5,
                },
            ),
            ModulePreset(
                name="战兽军团",
                description="大幅放宽动物与蛮人的出战数量，并保留机械开关。",
                values={
                    "DongWuChuZhanCount": 100,
                    "ManRenChuZhanCount": 100,
                    "JiQiChuZhanKaiGuan": 1,
                    "DongWuPinZhiRatio": 5,
                    "ManRenPinZhiRatio": 5,
                },
            ),
        ),
    ),
    ModuleDefinition(
        key="durability",
        title="耐久与腐坏",
        description="控制装备耐久、物品腐坏和死亡包裹销毁时间。",
        fields=(
            "NaiJiuXiShu",
            "WuPinFuHuaiRatio",
            "WuPinXiaoHuiTime",
            "BossEquipDurabilityCorrection",
            "EliteEquipDurabilityCorrection",
            "NormalEquipDurabilityCorrection",
        ),
        presets=(
            ModulePreset(
                name="永不磨损",
                description="让耐久消耗趋近于零，并提升掉落装备耐久。",
                values={
                    "NaiJiuXiShu": 0,
                    "BossEquipDurabilityCorrection": 5,
                    "EliteEquipDurabilityCorrection": 5,
                    "NormalEquipDurabilityCorrection": 5,
                },
            ),
            ModulePreset(
                name="长效物资",
                description="延长物品腐坏和死亡包裹消失所需时间。",
                values={
                    "WuPinFuHuaiRatio": 5,
                    "WuPinXiaoHuiTime": 5,
                },
            ),
            ModulePreset(
                name="仓储友好",
                description="综合降低耐久压力并延长物资保存时间。",
                values={
                    "NaiJiuXiShu": 0.2,
                    "WuPinFuHuaiRatio": 5,
                    "WuPinXiaoHuiTime": 5,
                    "BossEquipDurabilityCorrection": 3,
                    "EliteEquipDurabilityCorrection": 3,
                    "NormalEquipDurabilityCorrection": 3,
                },
            ),
        ),
    ),
)
