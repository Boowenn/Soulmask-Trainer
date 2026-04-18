# Soulmask Trainer

`Soulmask Trainer` is a desktop editor for Soulmask's `GameplaySettings` JSON files.

This project intentionally focuses on the game's built-in configuration files for single-player and self-hosted servers. It does not attempt live memory editing or anti-cheat bypassing.

## Features

- Auto-detect the `WS/Config/GameplaySettings` directory
- Load official `GameXishu_Template*.json` profiles
- Read the matching `GameXishuConfig_Template*.json` metadata files
- Beginner-friendly `傻瓜版` page with one-click combinations and a short list of common settings
- Edit visible settings through a desktop UI
- Export the current setup as a reusable JSON preset
- Export only the unsaved changes as a lightweight preset
- Import a preset JSON and apply it to the current template
- Preview preset differences before importing
- Remember recently imported/exported presets for one-click reuse
- Batch-apply the current setup to multiple templates in one pass
- Save the current template as a named snapshot
- Add short notes to snapshots for later recall
- Compare the current setup with a saved snapshot before restoring it
- Compare two saved snapshots side by side
- Search snapshots by name or note in the snapshot center
- Rename or delete snapshots directly from the snapshot center
- Open a simple preset/snapshot center for reuse workflows
- Remove single recent preset records, clean invalid history, or clear the recent list
- Filter the full parameter list down to changed items only
- Undo all unsaved edits for the current template in one click
- Dedicated "经验与等级" tab with quick presets
- Dedicated "战斗系统" tab with quick presets
- Dedicated "掉落与物品" tab with quick presets
- Dedicated "生存与恢复" tab with quick presets
- Dedicated "制造与生产" tab with quick presets
- Dedicated "建筑系统" tab with quick presets
- Dedicated "NPC与招募" tab with quick presets
- Dedicated "动物与成长" tab with quick presets
- Dedicated "耐久与腐坏" tab with quick presets
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
- Version tags like `v0.1.0` build the Windows executable, verify the EXE and ZIP contents, and publish a GitHub Release automatically.

## Notes

- The game ships a mix of UTF-8 and UTF-16 JSON files. The editor preserves the source encoding when saving.
- Backups are stored under `WS\Config\GameplaySettings\_SoulmaskTrainerBackup`.
- Snapshots are stored under `WS\Config\GameplaySettings\_SoulmaskTrainerSnapshots`.
- Recent preset history is stored in `WS\Config\GameplaySettings\_SoulmaskTrainerRecentPresets.json`.
