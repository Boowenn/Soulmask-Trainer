# Soulmask Trainer

`Soulmask Trainer` is a desktop editor for Soulmask's `GameplaySettings` JSON files.

This project intentionally focuses on the game's built-in configuration files for single-player and self-hosted servers. It does not attempt live memory editing or anti-cheat bypassing.

## Features

- Auto-detect the `WS/Config/GameplaySettings` directory
- Load official `GameXishu_Template*.json` profiles
- Read the matching `GameXishuConfig_Template*.json` metadata files
- Edit visible settings through a desktop UI
- Dedicated "经验与等级" tab with quick presets
- Dedicated "战斗系统" tab with quick presets
- Dedicated "掉落与物品" tab with quick presets
- Dedicated "生存与恢复" tab with quick presets
- Create timestamped backups before every save
- Restore the latest backup for the selected profile

## Run

```powershell
python main.py
```

## Build EXE

```powershell
.\build.ps1
```

The packaged executable is written to `dist/SoulmaskTrainer.exe`.

## CI

- Pushes and pull requests run unit tests plus a compile smoke test.
- Version tags like `v0.1.0` build the Windows executable and publish a GitHub Release asset automatically.

## Notes

- The game ships a mix of UTF-8 and UTF-16 JSON files. The editor preserves the source encoding when saving.
- Backups are stored under `WS\Config\GameplaySettings\_SoulmaskTrainerBackup`.
