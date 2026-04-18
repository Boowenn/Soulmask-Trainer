from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import shutil
from pathlib import Path
from typing import Any


PROFILE_PREFIX = "GameXishu_Template"
CONFIG_PREFIX = "GameXishuConfig_Template"
BACKUP_DIRECTORY_NAME = "_SoulmaskTrainerBackup"


@dataclass(frozen=True)
class SettingMeta:
    key: str
    label: str
    min_value: float | int | None
    max_value: float | int | None
    default_value: float | int | bool | None
    is_toggle: bool
    is_visible: bool
    step: float | int | None


@dataclass(frozen=True)
class LoadedProfile:
    profile_path: Path
    config_path: Path
    profile_encoding: str
    config_encoding: str
    values: dict[str, Any]
    original_values: dict[str, Any]
    metadata: dict[str, SettingMeta]


@dataclass(frozen=True)
class PresetData:
    source_profile: str
    values: dict[str, Any]


@dataclass(frozen=True)
class ValueDiff:
    key: str
    before: Any
    after: Any


class TrainerDataError(RuntimeError):
    """Raised when Soulmask gameplay settings cannot be loaded or saved."""


def get_changed_values(original_values: dict[str, Any], current_values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in current_values.items()
        if original_values.get(key) != value
    }


def build_value_diff(current_values: dict[str, Any], incoming_values: dict[str, Any]) -> list[ValueDiff]:
    return [
        ValueDiff(key=key, before=current_values.get(key), after=value)
        for key, value in incoming_values.items()
        if current_values.get(key) != value
    ]


def detect_text_encoding(path: Path) -> str:
    header = path.read_bytes()[:4]
    if header.startswith(b"\xff\xfe") or header.startswith(b"\xfe\xff"):
        return "utf-16"
    if header.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "utf-16"
    return "utf-8"


def read_json_object(path: Path) -> tuple[dict[str, Any], str]:
    encoding = detect_text_encoding(path)
    return json.loads(path.read_text(encoding=encoding)), encoding


def write_json_object(path: Path, data: dict[str, Any], encoding: str) -> None:
    text = json.dumps(data, ensure_ascii=False, indent="\t")
    path.write_text(f"{text}\n", encoding=encoding)


class TrainerRepository:
    def __init__(self, settings_dir: Path) -> None:
        self.settings_dir = settings_dir

    @staticmethod
    def discover_settings_dir(start_dir: Path | None = None) -> Path | None:
        candidate_roots: list[Path] = []
        if start_dir is not None:
            candidate_roots.append(start_dir)
        candidate_roots.append(Path.cwd())
        candidate_roots.append(Path(__file__).resolve().parents[2])

        visited: set[Path] = set()
        for root in candidate_roots:
            root = root.resolve()
            if root in visited:
                continue
            visited.add(root)

            direct_match = root / "WS" / "Config" / "GameplaySettings"
            if direct_match.is_dir():
                return direct_match

            for parent in [root, *root.parents]:
                nested = parent / "WS" / "Config" / "GameplaySettings"
                if nested.is_dir():
                    return nested

                for child_name in ("Soulmask", "Soulmask-Trainer"):
                    child_match = parent / child_name / "WS" / "Config" / "GameplaySettings"
                    if child_match.is_dir():
                        return child_match

        return None

    def validate(self) -> None:
        if not self.settings_dir.is_dir():
            raise TrainerDataError(f"GameplaySettings directory not found: {self.settings_dir}")

    def list_profiles(self) -> list[Path]:
        self.validate()
        profiles = sorted(
            path
            for path in self.settings_dir.glob(f"{PROFILE_PREFIX}*.json")
            if path.is_file()
        )
        return profiles

    def resolve_profile(self, profile_name: str) -> Path:
        profile_path = self.settings_dir / profile_name
        if not profile_path.is_file():
            raise TrainerDataError(f"Profile does not exist: {profile_name}")
        return profile_path

    def get_config_template_path(self, profile_name: str) -> Path:
        suffix = ""
        lowered = profile_name.lower()
        if "_action" in lowered:
            suffix = "_Action"
        elif "_management" in lowered:
            suffix = "_Management"
        elif "_pvp" in lowered:
            suffix = "_PVP"
        config_path = self.settings_dir / f"{CONFIG_PREFIX}{suffix}.json"
        if not config_path.is_file():
            raise TrainerDataError(f"Metadata file is missing for {profile_name}: {config_path.name}")
        return config_path

    def load_profile(self, profile_name: str) -> LoadedProfile:
        profile_path = self.resolve_profile(profile_name)
        config_path = self.get_config_template_path(profile_name)

        profile_payload, profile_encoding = read_json_object(profile_path)
        config_payload, config_encoding = read_json_object(config_path)

        values = dict(profile_payload["0"])
        metadata_payload = config_payload["0"]
        metadata = {
            key: SettingMeta(
                key=key,
                label=str(raw_value.get("Desc") or key),
                min_value=raw_value.get("XiShuMinValue"),
                max_value=raw_value.get("XiShuMaxValue"),
                default_value=raw_value.get("XiShuDefaultValue"),
                is_toggle=bool(raw_value.get("IsKaiGuan")),
                is_visible=bool(raw_value.get("IsShow")),
                step=raw_value.get("XiShuStep"),
            )
            for key, raw_value in metadata_payload.items()
        }

        return LoadedProfile(
            profile_path=profile_path,
            config_path=config_path,
            profile_encoding=profile_encoding,
            config_encoding=config_encoding,
            values=values,
            original_values=dict(values),
            metadata=metadata,
        )

    def create_backup(self, profile_path: Path) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = self.settings_dir / BACKUP_DIRECTORY_NAME / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / profile_path.name
        shutil.copy2(profile_path, backup_path)
        return backup_path

    def latest_backup_for(self, profile_name: str) -> Path | None:
        backup_root = self.settings_dir / BACKUP_DIRECTORY_NAME
        if not backup_root.is_dir():
            return None

        matches = sorted(backup_root.glob(f"*\\{profile_name}"))
        if not matches:
            return None
        return matches[-1]

    def save_profile(self, loaded_profile: LoadedProfile, values: dict[str, Any]) -> Path:
        backup_path = self.create_backup(loaded_profile.profile_path)
        payload = {"0": values}
        write_json_object(loaded_profile.profile_path, payload, loaded_profile.profile_encoding)
        return backup_path

    def save_profiles(self, profile_names: list[str], values: dict[str, Any]) -> dict[str, Path]:
        backup_paths: dict[str, Path] = {}
        for profile_name in profile_names:
            loaded_profile = self.load_profile(profile_name)
            merged_values = dict(loaded_profile.values)
            merged_values.update(values)
            backup_paths[profile_name] = self.save_profile(loaded_profile, merged_values)
        return backup_paths

    def export_preset(self, destination_path: Path, source_profile: str, values: dict[str, Any]) -> None:
        payload = {
            "schema_version": 1,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "source_profile": source_profile,
            "values": values,
        }
        destination_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def import_preset(self, preset_path: Path) -> PresetData:
        payload = json.loads(preset_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "values" in payload and isinstance(payload["values"], dict):
            source_profile = str(payload.get("source_profile") or preset_path.stem)
            values = dict(payload["values"])
            return PresetData(source_profile=source_profile, values=values)
        if isinstance(payload, dict):
            return PresetData(source_profile=preset_path.stem, values=dict(payload))
        raise TrainerDataError(f"Preset file format is invalid: {preset_path}")

    def restore_latest_backup(self, profile_name: str) -> Path:
        latest_backup = self.latest_backup_for(profile_name)
        if latest_backup is None:
            raise TrainerDataError(f"No backup found for {profile_name}")

        profile_path = self.resolve_profile(profile_name)
        shutil.copy2(latest_backup, profile_path)
        return latest_backup
