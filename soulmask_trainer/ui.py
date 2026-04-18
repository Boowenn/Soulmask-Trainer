from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk
from pathlib import Path
from typing import Any

from soulmask_trainer.catalog import EASY_FIELDS, EASY_PRESETS, EasyPreset, MODULES, ModuleDefinition, ModulePreset, normalize_preset_value
from soulmask_trainer.data import (
    LoadedProfile,
    RecentPresetEntry,
    SettingMeta,
    SnapshotData,
    TrainerDataError,
    TrainerRepository,
    ValueDiff,
    build_full_value_diff,
    build_value_diff,
    get_changed_values,
    sanitize_file_component,
    snapshot_matches_keyword,
)


@dataclass
class FieldState:
    meta: SettingMeta
    variable: tk.Variable
    original_value: Any
    rows: list[ttk.Frame]


class ScrollableFrame(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")


class SoulmaskTrainerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Soulmask Trainer")
        self.geometry("1180x760")
        self.minsize(1020, 680)

        self.repository: TrainerRepository | None = None
        self.loaded_profile: LoadedProfile | None = None
        self.field_states: dict[str, FieldState] = {}

        self.settings_dir_var = tk.StringVar()
        self.selected_profile_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.changed_only_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="等待加载 GameplaySettings 目录。")
        self.summary_var = tk.StringVar(value="未加载配置文件。")
        self.change_summary_var = tk.StringVar(value="当前没有未保存改动。")
        self._window_icon: tk.PhotoImage | None = None

        self.profile_combo: ttk.Combobox | None = None
        self.notebook: ttk.Notebook | None = None
        self.field_container: ScrollableFrame | None = None
        self.searchable_rows: dict[str, ttk.Frame] = {}
        self._change_refresh_pending = False

        self._apply_window_icon()
        self._configure_styles()
        self._build_layout()
        self._try_autoload()

    def _asset_path(self, relative_path: str) -> Path:
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        return base_dir / relative_path

    def _apply_window_icon(self) -> None:
        icon_path = self._asset_path("assets/app-icon.ico")
        if icon_path.is_file():
            try:
                self.iconbitmap(default=str(icon_path))
                return
            except tk.TclError:
                pass

        png_icon_path = self._asset_path("assets/app-icon.png")
        if not png_icon_path.is_file():
            return

        try:
            self._window_icon = tk.PhotoImage(file=str(png_icon_path))
            self.iconphoto(True, self._window_icon)
        except tk.TclError:
            self._window_icon = None

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
        except tk.TclError:
            return

        hero_font = default_font.copy()
        hero_font.configure(size=max(default_font.cget("size") + 5, 16), weight="bold")
        title_font = default_font.copy()
        title_font.configure(size=max(default_font.cget("size") + 2, 11), weight="bold")
        note_font = default_font.copy()
        note_font.configure(size=max(default_font.cget("size") - 1, 9))

        style.configure("HomeHero.TLabel", font=hero_font)
        style.configure("HomeCardTitle.TLabel", font=title_font)
        style.configure("HomeNote.TLabel", font=note_font)
        style.configure("HomeAction.TButton", padding=(18, 16))
        style.configure("HomeQuick.TButton", padding=(16, 12))

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(self, padding=12)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="GameplaySettings").grid(row=0, column=0, sticky="w")
        ttk.Entry(toolbar, textvariable=self.settings_dir_var).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(8, 8),
        )
        ttk.Button(toolbar, text="浏览", command=self._choose_settings_dir).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(toolbar, text="刷新", command=self._refresh_profiles).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(toolbar, text="打开文件夹", command=self._open_settings_dir).grid(row=0, column=4)

        ttk.Label(toolbar, text="配置模板").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.profile_combo = ttk.Combobox(
            toolbar,
            state="readonly",
            textvariable=self.selected_profile_var,
        )
        self.profile_combo.grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(10, 0))
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _event: self._load_selected_profile())
        ttk.Button(toolbar, text="重新载入", command=self._load_selected_profile).grid(row=1, column=2, pady=(10, 0))
        ttk.Button(toolbar, text="保存到游戏", command=self._save_profile).grid(row=1, column=3, pady=(10, 0), padx=(0, 8))
        ttk.Button(toolbar, text="恢复最近备份", command=self._restore_profile).grid(row=1, column=4, pady=(10, 0))
        ttk.Label(toolbar, text="复用操作").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Button(toolbar, text="打开预设/快照中心", command=self._open_reuse_center).grid(
            row=2,
            column=1,
            sticky="w",
            padx=(8, 8),
            pady=(10, 0),
        )
        ttk.Button(toolbar, text="导出当前预设", command=self._export_preset).grid(row=2, column=2, pady=(10, 0))
        ttk.Button(toolbar, text="导入现成预设", command=self._import_preset).grid(row=2, column=3, pady=(10, 0), padx=(0, 8))
        ttk.Button(toolbar, text="批量套用", command=self._open_batch_apply_dialog).grid(row=2, column=4, pady=(10, 0))

        guide_frame = ttk.LabelFrame(self, text="怎么用", padding=(12, 8))
        guide_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        guide_frame.columnconfigure(0, weight=1)
        ttk.Label(
            guide_frame,
            text=(
                "1. 先确认上面的 GameplaySettings 路径和配置模板。"
                " 2. 主要在“傻瓜版”里点一键组合或改常用项。"
                " 3. 改完点“保存到游戏”。"
                " 4. 想导入历史方案、管理快照、复制快照，就点“打开预设/快照中心”。"
            ),
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 8))

        status_bar = ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(12, 6))
        status_bar.grid(row=3, column=0, sticky="ew")

        self._build_home_tab()

    def _build_home_tab(self, loaded_profile: LoadedProfile | None = None) -> None:
        if self.notebook is None:
            return

        home_tab = ttk.Frame(self.notebook, padding=18)
        home_tab.columnconfigure(0, weight=1)
        home_tab.rowconfigure(4, weight=1)
        self.notebook.add(home_tab, text="首页")

        current_path = self.settings_dir_var.get().strip()
        profile_name = loaded_profile.profile_path.name if loaded_profile is not None else ""
        profile_count = 0
        if self.profile_combo is not None:
            profile_values = self.profile_combo.cget("values")
            profile_count = len(profile_values) if profile_values else 0

        if loaded_profile is None:
            hero_text = "先选目录，再选模板。加载成功后，下面的大卡片会带你一步一步改。"
            hero_note = "当前还没进入可编辑状态，所以需要先完成前两步。"
            mode_title = "当前模式：官方 GameplaySettings 配置编辑"
            mode_note = "当前版本不做进程注入、内存改写或反作弊相关功能。"
        else:
            hero_text = f"当前模板已加载：{loaded_profile.profile_path.name}"
            hero_note = "建议先打开傻瓜版点一个一键组合，再微调，最后保存到游戏。"
            mode_title = "当前模式：配置编辑 + 预设/快照复用"
            mode_note = "当前版本修改 JSON 配置、预设和快照，不做实时注入。"

        hero_frame = ttk.LabelFrame(home_tab, text="开始使用", padding=16)
        hero_frame.grid(row=0, column=0, sticky="ew")
        hero_frame.columnconfigure(0, weight=1)
        hero_frame.columnconfigure(1, weight=1)
        ttk.Label(hero_frame, text=hero_text, style="HomeHero.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(hero_frame, text=hero_note, style="HomeNote.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))

        mode_frame = ttk.LabelFrame(hero_frame, text="能力范围", padding=12)
        mode_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(18, 0))
        ttk.Label(mode_frame, text=mode_title, style="HomeCardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(mode_frame, text=mode_note, justify="left", wraplength=360).grid(row=1, column=0, sticky="w", pady=(8, 0))

        steps_frame = ttk.LabelFrame(home_tab, text="四步开始", padding=14)
        steps_frame.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        steps_frame.columnconfigure(0, weight=1)
        steps_frame.columnconfigure(1, weight=1)

        steps = [
            (
                "第 1 步 选择目录",
                "先定位到 Soulmask 的 GameplaySettings 目录。选对之后才能扫描模板。",
                "选择游戏目录",
                self._choose_settings_dir,
                "normal",
            ),
            (
                "第 2 步 扫描模板",
                "把当前目录里的 GameXishu_Template*.json 扫出来，准备进入编辑。",
                "扫描可用模板",
                self._refresh_profiles,
                "normal",
            ),
            (
                "第 3 步 傻瓜版开改",
                "新手最适合从傻瓜版开始，先点一键组合，再微调常用项。",
                "打开傻瓜版",
                lambda: self._select_tab("傻瓜版"),
                "normal" if loaded_profile is not None else "disabled",
            ),
            (
                "第 4 步 保存或复用",
                "改完保存到游戏；如果想留方案，就去预设/快照中心做导出、复制和分类。",
                "打开预设/快照中心",
                self._open_reuse_center,
                "normal" if loaded_profile is not None else "disabled",
            ),
        ]
        for index, (title, description, button_text, command, state) in enumerate(steps):
            card = ttk.LabelFrame(steps_frame, text=title, padding=14)
            row = index // 2
            column = index % 2
            card.grid(row=row, column=column, sticky="nsew", padx=(0, 10) if column == 0 else (10, 0), pady=(0, 12))
            card.columnconfigure(0, weight=1)
            ttk.Label(card, text=description, justify="left", wraplength=360).grid(row=0, column=0, sticky="w")
            ttk.Button(
                card,
                text=button_text,
                command=command,
                style="HomeAction.TButton",
                state=state,
            ).grid(row=1, column=0, sticky="ew", pady=(14, 0))

        quick_frame = ttk.LabelFrame(home_tab, text="常用大按钮", padding=14)
        quick_frame.grid(row=2, column=0, sticky="ew")
        quick_frame.columnconfigure(0, weight=1)
        quick_frame.columnconfigure(1, weight=1)
        quick_frame.columnconfigure(2, weight=1)
        quick_frame.columnconfigure(3, weight=1)
        quick_buttons = [
            ("保存到游戏", self._save_profile),
            ("恢复最近备份", self._restore_profile),
            ("导出当前预设", self._export_preset),
            ("批量套用", self._open_batch_apply_dialog),
        ]
        for index, (label, command) in enumerate(quick_buttons):
            ttk.Button(
                quick_frame,
                text=label,
                command=command,
                style="HomeQuick.TButton",
                state="normal" if loaded_profile is not None else "disabled",
            ).grid(row=0, column=index, sticky="ew", padx=(0, 8) if index < len(quick_buttons) - 1 else 0)

        status_frame = ttk.LabelFrame(home_tab, text="当前状态", padding=14)
        status_frame.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        status_frame.columnconfigure(1, weight=1)
        ttk.Label(status_frame, text="目录").grid(row=0, column=0, sticky="nw")
        ttk.Label(
            status_frame,
            text=current_path or "还没选。请先点上面的“选择游戏目录”。",
            justify="left",
            wraplength=850,
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(status_frame, text="模板").grid(row=1, column=0, sticky="nw", pady=(10, 0))
        ttk.Label(
            status_frame,
            text=profile_name or "还没加载。先扫描模板，再从顶部下拉框选择。",
            justify="left",
        ).grid(row=1, column=1, sticky="w", pady=(10, 0))
        ttk.Label(status_frame, text="可用模板数").grid(row=2, column=0, sticky="nw", pady=(10, 0))
        ttk.Label(status_frame, text=str(profile_count), justify="left").grid(row=2, column=1, sticky="w", pady=(10, 0))

        capability_frame = ttk.LabelFrame(home_tab, text="这个修改器能改什么", padding=14)
        capability_frame.grid(row=4, column=0, sticky="nsew", pady=(14, 0))
        capability_frame.columnconfigure(0, weight=1)
        capability_frame.columnconfigure(1, weight=1)
        capability_cards = (
            ("经验与等级", "升级倍率、训练经验、等级上限"),
            ("战斗系统", "输出、承伤、拆建筑、部分 PVP 系数"),
            ("掉落与物品", "采集、宝箱、怪物掉落、自动化产出"),
            ("生存与恢复", "生命、体力、食物、精神、气息消耗"),
            ("制造与生产", "制作时间、转化效率、矿场、索道、船员"),
            ("建筑 / NPC / 动物 / 耐久", "建造限制、招募、成长、腐坏、耐久"),
        )
        for index, (title, description) in enumerate(capability_cards):
            card = ttk.Frame(capability_frame, padding=12)
            row = index // 2
            column = index % 2
            card.grid(row=row, column=column, sticky="nsew", padx=(0, 10) if column == 0 else (10, 0), pady=(0, 10))
            ttk.Label(card, text=title, style="HomeCardTitle.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(card, text=description, justify="left", wraplength=360).grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _select_tab(self, title: str) -> None:
        if self.notebook is None:
            return
        for tab_id in self.notebook.tabs():
            if self.notebook.tab(tab_id, "text") == title:
                self.notebook.select(tab_id)
                return

    def _try_autoload(self) -> None:
        detected = TrainerRepository.discover_settings_dir(Path.cwd())
        if detected is None:
            self.status_var.set("未自动检测到 GameplaySettings，请手动选择。")
            return

        self.settings_dir_var.set(str(detected))
        self._refresh_profiles()

    def _choose_settings_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="选择 Soulmask GameplaySettings 目录",
            mustexist=True,
            initialdir=self.settings_dir_var.get() or str(Path.cwd()),
        )
        if not selected:
            return

        self.settings_dir_var.set(selected)
        self._refresh_profiles()

    def _open_settings_dir(self) -> None:
        current = self.settings_dir_var.get().strip()
        if not current:
            return
        subprocess.Popen(["explorer", current])

    def _refresh_profiles(self) -> None:
        settings_dir_text = self.settings_dir_var.get().strip()
        if not settings_dir_text:
            messagebox.showwarning("路径为空", "请先选择 GameplaySettings 目录。")
            return

        repository = TrainerRepository(Path(settings_dir_text))
        try:
            profiles = repository.list_profiles()
        except TrainerDataError as error:
            messagebox.showerror("目录无效", str(error))
            self.status_var.set(str(error))
            return

        self.repository = repository
        profile_names = [path.name for path in profiles]
        if self.profile_combo is not None:
            self.profile_combo["values"] = profile_names

        if not profile_names:
            self.selected_profile_var.set("")
            self._clear_fields()
            self.summary_var.set("当前目录没有找到任何 GameXishu_Template*.json。")
            self.status_var.set("未发现可编辑的配置模板。")
            return

        if self.selected_profile_var.get() not in profile_names:
            self.selected_profile_var.set(profile_names[0])

        self.status_var.set(f"已发现 {len(profile_names)} 个配置模板。")
        self._load_selected_profile()

    def _load_selected_profile(self) -> None:
        if self.repository is None:
            return

        profile_name = self.selected_profile_var.get().strip()
        if not profile_name:
            return

        try:
            loaded_profile = self.repository.load_profile(profile_name)
        except TrainerDataError as error:
            messagebox.showerror("加载失败", str(error))
            self.status_var.set(str(error))
            return

        self.loaded_profile = loaded_profile
        self.summary_var.set(
            "\n".join(
                [
                    f"当前模板: {loaded_profile.profile_path.name}",
                    f"配置编码: {loaded_profile.profile_encoding}",
                    f"元数据模板: {loaded_profile.config_path.name}",
                    f"可显示参数: {sum(1 for meta in loaded_profile.metadata.values() if meta.is_visible)}",
                ]
            )
        )
        self._build_fields(loaded_profile)
        self.status_var.set(f"已加载 {profile_name}。")

    def _clear_fields(self, loaded_profile: LoadedProfile | None = None) -> None:
        self.field_states.clear()
        self.searchable_rows.clear()
        self.field_container = None
        self.loaded_profile = loaded_profile
        if self.notebook is None:
            return
        for tab_id in self.notebook.tabs():
            self.notebook.forget(tab_id)
        self._build_home_tab(loaded_profile)

    def _ensure_field_state(self, key: str, meta: SettingMeta, current_value: Any) -> FieldState:
        state = self.field_states.get(key)
        if state is not None:
            return state

        if meta.is_toggle:
            variable: tk.Variable = tk.BooleanVar(value=bool(current_value))
        else:
            variable = tk.StringVar(value=self._format_value(current_value))

        state = FieldState(
            meta=meta,
            variable=variable,
            original_value=current_value,
            rows=[],
        )
        variable.trace_add("write", self._schedule_change_refresh)
        self.field_states[key] = state
        return state

    def _build_fields(self, loaded_profile: LoadedProfile) -> None:
        if self.notebook is None:
            return

        self._clear_fields(loaded_profile)
        self.search_var.set("")
        self.changed_only_var.set(False)
        self._build_easy_mode_tab(loaded_profile)
        self._build_all_settings_tab(loaded_profile)
        for module in MODULES:
            self._build_module_tab(loaded_profile, module)
        self._refresh_change_summary()
        self._apply_filter()
        self._select_tab("首页")

    def _build_easy_mode_tab(self, loaded_profile: LoadedProfile) -> None:
        assert self.notebook is not None

        easy_tab = ttk.Frame(self.notebook, padding=12)
        easy_tab.columnconfigure(0, weight=1)
        easy_tab.rowconfigure(4, weight=1)
        self.notebook.add(easy_tab, text="傻瓜版")

        ttk.Label(
            easy_tab,
            text=(
                "先在顶部选好模板，再点这里的一键组合或微调常用项；"
                "改完点击顶部“保存到游戏”。想导入预设或管理快照，可以点顶部或这里的“打开预设/快照中心”。"
            ),
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        capability_frame = ttk.LabelFrame(easy_tab, text="这个修改器现在能改什么", padding=10)
        capability_frame.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        capability_frame.columnconfigure(0, weight=1)
        capability_frame.columnconfigure(1, weight=1)

        capability_items = (
            "经验与等级：升级倍率、训练经验、等级上限",
            "战斗系统：输出、承伤、拆建筑、部分 PVP 系数",
            "掉落与物品：采集、宝箱、怪物掉落、自动化产出",
            "生存与恢复：生命、体力、食物、精神、气息消耗",
            "制造与生产：制作时间、转化效率、矿场/索道/船员",
            "建筑/NPC/动物/耐久：建造限制、招募、成长、腐坏",
        )
        for index, item in enumerate(capability_items):
            ttk.Label(
                capability_frame,
                text=f"{index + 1}. {item}",
                justify="left",
            ).grid(
                row=index // 2,
                column=index % 2,
                sticky="w",
                padx=(0, 18) if index % 2 == 0 else 0,
                pady=(0, 6),
            )

        change_frame = ttk.LabelFrame(easy_tab, text="当前改动", padding=10)
        change_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        change_frame.columnconfigure(0, weight=1)
        ttk.Label(change_frame, textvariable=self.change_summary_var, justify="left").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Button(
            change_frame,
            text="保存当前快照",
            command=self._save_snapshot,
        ).grid(row=0, column=1, padx=(12, 0))
        ttk.Button(
            change_frame,
            text="撤销未保存修改",
            command=self._reset_unsaved_changes,
        ).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(
            change_frame,
            text="只导出改动项",
            command=lambda: self._export_preset(changed_only=True),
        ).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(
            change_frame,
            text="打开预设/快照中心",
            command=self._open_reuse_center,
        ).grid(row=0, column=4, padx=(8, 0))

        preset_frame = ttk.LabelFrame(easy_tab, text="一键组合", padding=10)
        preset_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for index, preset in enumerate(EASY_PRESETS):
            button = ttk.Button(
                preset_frame,
                text=preset.name,
                command=lambda selected_preset=preset: self._apply_easy_preset(selected_preset),
            )
            button.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            ttk.Label(preset_frame, text=preset.description, foreground="#666666").grid(
                row=index,
                column=1,
                sticky="w",
                padx=(12, 0),
                pady=(0, 8),
            )

        content = ScrollableFrame(easy_tab)
        content.grid(row=4, column=0, sticky="nsew")

        visible_fields = [
            key
            for key in EASY_FIELDS
            if key in loaded_profile.metadata and loaded_profile.metadata[key].is_visible
        ]
        for row_index, key in enumerate(visible_fields):
            meta = loaded_profile.metadata[key]
            current_value = loaded_profile.values.get(key, meta.default_value)
            state = self._ensure_field_state(key, meta, current_value)
            row = self._create_field_row(content.inner, key, state)
            row.grid(row=row_index, column=0, sticky="ew")

    def _build_all_settings_tab(self, loaded_profile: LoadedProfile) -> None:
        assert self.notebook is not None

        editor_tab = ttk.Frame(self.notebook, padding=12)
        editor_tab.columnconfigure(0, weight=1)
        editor_tab.rowconfigure(2, weight=1)
        self.notebook.add(editor_tab, text="全部参数")

        ttk.Label(editor_tab, textvariable=self.summary_var, justify="left").grid(row=0, column=0, sticky="ew")

        search_frame = ttk.Frame(editor_tab)
        search_frame.grid(row=1, column=0, sticky="ew", pady=(12, 12))
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="搜索").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        search_entry.bind("<KeyRelease>", lambda _event: self._apply_filter())
        ttk.Button(search_frame, text="清空", command=self._clear_search).grid(row=0, column=2)
        ttk.Checkbutton(
            search_frame,
            text="只看已改动",
            variable=self.changed_only_var,
            command=self._apply_filter,
        ).grid(row=0, column=3, padx=(12, 0))

        self.field_container = ScrollableFrame(editor_tab)
        self.field_container.grid(row=2, column=0, sticky="nsew")

        ordered_items = sorted(
            ((key, meta) for key, meta in loaded_profile.metadata.items() if meta.is_visible),
            key=lambda item: (item[1].label.lower(), item[0].lower()),
        )
        for row_index, (key, meta) in enumerate(ordered_items):
            current_value = loaded_profile.values.get(key, meta.default_value)
            state = self._ensure_field_state(key, meta, current_value)
            row = self._create_field_row(self.field_container.inner, key, state)
            row.grid(row=row_index, column=0, sticky="ew")
            self.searchable_rows[key] = row

    def _build_module_tab(self, loaded_profile: LoadedProfile, module: ModuleDefinition) -> None:
        assert self.notebook is not None

        module_tab = ttk.Frame(self.notebook, padding=12)
        module_tab.columnconfigure(0, weight=1)
        module_tab.rowconfigure(2, weight=1)
        self.notebook.add(module_tab, text=module.title)

        ttk.Label(module_tab, text=module.description, justify="left").grid(row=0, column=0, sticky="ew")

        preset_frame = ttk.Frame(module_tab)
        preset_frame.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        preset_frame.columnconfigure(0, weight=1)
        ttk.Label(preset_frame, text="快捷预设").grid(row=0, column=0, sticky="w")

        for column_index, preset in enumerate(module.presets, start=1):
            ttk.Button(
                preset_frame,
                text=preset.name,
                command=lambda selected_module=module, selected_preset=preset: self._apply_preset(selected_module, selected_preset),
            ).grid(row=0, column=column_index, padx=(8, 0))

        scrollable = ScrollableFrame(module_tab)
        scrollable.grid(row=2, column=0, sticky="nsew")

        visible_fields = [
            key
            for key in module.fields
            if key in loaded_profile.metadata and loaded_profile.metadata[key].is_visible
        ]

        if not visible_fields:
            ttk.Label(scrollable.inner, text="当前模板没有这些可编辑字段。").grid(row=0, column=0, sticky="w")
            return

        for row_index, key in enumerate(visible_fields):
            meta = loaded_profile.metadata[key]
            current_value = loaded_profile.values.get(key, meta.default_value)
            state = self._ensure_field_state(key, meta, current_value)
            row = self._create_field_row(scrollable.inner, key, state)
            row.grid(row=row_index, column=0, sticky="ew")

    def _create_field_row(self, parent: ttk.Frame, key: str, state: FieldState) -> ttk.Frame:
        row = ttk.Frame(parent, padding=(4, 4))
        row.columnconfigure(1, weight=1)

        label = ttk.Label(row, text=state.meta.label, width=28)
        label.grid(row=0, column=0, sticky="w", padx=(0, 8))

        detail_text = f"{key} | 范围: {self._format_range(state.meta)}"
        ttk.Label(row, text=detail_text, foreground="#666666").grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            padx=(0, 8),
        )

        if state.meta.is_toggle:
            widget = ttk.Checkbutton(row, variable=state.variable)
            widget.grid(row=0, column=1, sticky="w")
        else:
            widget = ttk.Entry(row, textvariable=state.variable, width=18)
            widget.grid(row=0, column=1, sticky="w")

        ttk.Button(
            row,
            text="还原",
            command=lambda item_key=key: self._reset_field(item_key),
        ).grid(row=0, column=2, padx=(8, 0))

        state.rows.append(row)
        return row

    def _format_range(self, meta: SettingMeta) -> str:
        if meta.is_toggle:
            return "开/关"
        return f"{self._format_value(meta.min_value)} ~ {self._format_value(meta.max_value)}"

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "开" if value else "关"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            return f"{value:.4f}".rstrip("0").rstrip(".")
        return str(value)

    @staticmethod
    def _format_timestamp(timestamp: str) -> str:
        if not timestamp:
            return "-"
        return timestamp.replace("T", " ")

    @staticmethod
    def _shorten_text(value: str, limit: int = 28) -> str:
        if len(value) <= limit:
            return value
        return f"{value[: limit - 3]}..."

    def _format_recent_preset_entry(self, entry: RecentPresetEntry) -> str:
        return (
            f"[{entry.action}] {entry.path.name}"
            f" | 模板: {entry.source_profile}"
            f" | 时间: {self._format_timestamp(entry.recorded_at)}"
        )

    def _format_snapshot_entry(self, snapshot: SnapshotData) -> str:
        return (
            f"{snapshot.snapshot_name}"
            f" | {self._format_timestamp(snapshot.created_at)}"
            f" | {len(snapshot.values)} 项"
        )

    def _format_snapshot_entry(self, snapshot: SnapshotData) -> str:
        parts = [
            snapshot.snapshot_name,
            self._format_timestamp(snapshot.created_at),
            f"{len(snapshot.values)} 项",
        ]
        if snapshot.snapshot_note:
            parts.append(f"备注: {self._shorten_text(snapshot.snapshot_note)}")
        return " | ".join(parts)

    def _format_snapshot_entry(self, snapshot: SnapshotData) -> str:
        parts = [
            snapshot.snapshot_name,
            self._format_timestamp(snapshot.created_at),
            f"{len(snapshot.values)} 项",
        ]
        if snapshot.is_favorite:
            parts.append("收藏")
        if snapshot.snapshot_category:
            parts.append(f"分类: {snapshot.snapshot_category}")
        if snapshot.snapshot_note:
            parts.append(f"备注: {self._shorten_text(snapshot.snapshot_note)}")
        return " | ".join(parts)

    def _reset_field(self, key: str) -> None:
        state = self.field_states[key]
        if state.meta.is_toggle:
            state.variable.set(bool(state.original_value))
        else:
            state.variable.set(self._format_value(state.original_value))

    def _clear_search(self) -> None:
        self.search_var.set("")
        self._apply_filter()

    def _schedule_change_refresh(self, *_args: str) -> None:
        if self._change_refresh_pending:
            return
        self._change_refresh_pending = True
        self.after_idle(self._refresh_change_summary)

    def _refresh_change_summary(self) -> None:
        self._change_refresh_pending = False
        if self.loaded_profile is None:
            self.change_summary_var.set("当前没有未保存改动。")
            return

        changed_keys = self._get_changed_keys()
        if not changed_keys:
            self.change_summary_var.set("当前没有未保存改动。\n可以先点一键组合，再微调常用项。")
            self._apply_filter()
            return

        changed_labels = [
            self.field_states[key].meta.label
            for key in sorted(changed_keys, key=lambda item: self.field_states[item].meta.label.lower())
            if key in self.field_states
        ]
        preview_labels = "、".join(changed_labels[:5])
        if len(changed_labels) > 5:
            preview_labels = f"{preview_labels} 等 {len(changed_labels)} 项"

        self.change_summary_var.set(
            f"当前有 {len(changed_keys)} 项未保存改动。\n主要改动: {preview_labels}"
        )
        self._apply_filter()

    def _collect_values_for_change_detection(self) -> dict[str, Any]:
        if self.loaded_profile is None:
            return {}

        merged_values = dict(self.loaded_profile.values)
        for key, state in self.field_states.items():
            meta = state.meta
            raw_value = state.variable.get()

            if meta.is_toggle:
                merged_values[key] = 1 if bool(raw_value) else 0
                continue

            text = str(raw_value).strip()
            try:
                merged_values[key] = self._parse_numeric_value(meta, text)
            except TrainerDataError:
                merged_values[key] = text

        return merged_values

    def _get_changed_keys(self) -> list[str]:
        if self.loaded_profile is None:
            return []
        current_values = self._collect_values_for_change_detection()
        return list(get_changed_values(self.loaded_profile.original_values, current_values).keys())

    def _collect_changed_values(self) -> dict[str, Any]:
        if self.loaded_profile is None:
            return {}
        current_values = self._collect_values()
        return get_changed_values(self.loaded_profile.original_values, current_values)

    def _apply_filter(self) -> None:
        keyword = self.search_var.get().strip().lower()
        changed_keys: set[str] | None = None
        if self.changed_only_var.get():
            changed_keys = set(self._get_changed_keys())
        for key, row in self.searchable_rows.items():
            state = self.field_states[key]
            haystack = f"{key} {state.meta.label}".lower()
            matches_keyword = not keyword or keyword in haystack
            matches_changed = changed_keys is None or key in changed_keys
            if matches_keyword and matches_changed:
                row.grid()
            else:
                row.grid_remove()

    def _apply_preset(self, module: ModuleDefinition, preset: ModulePreset) -> None:
        updated_count = self._apply_values_to_fields(preset.values)
        self.status_var.set(f"已应用预设“{preset.name}”，更新 {updated_count} 个字段。")

    def _apply_easy_preset(self, preset: EasyPreset) -> None:
        updated_count = self._apply_values_to_fields(preset.values)
        self.status_var.set(f"已应用傻瓜版方案“{preset.name}”，更新 {updated_count} 个字段。")

    def _apply_values_to_fields(self, values: dict[str, Any]) -> int:
        updated_count = 0
        for key, value in values.items():
            state = self.field_states.get(key)
            if state is None:
                continue

            normalized_value = normalize_preset_value(state.meta, value)
            if state.meta.is_toggle:
                state.variable.set(bool(normalized_value))
            else:
                state.variable.set(self._format_value(normalized_value))
            updated_count += 1
        self._schedule_change_refresh()
        return updated_count

    def _normalize_preset_values(self, values: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        normalized_values: dict[str, Any] = {}
        skipped_keys: list[str] = []
        for key, value in values.items():
            state = self.field_states.get(key)
            if state is None:
                skipped_keys.append(key)
                continue

            try:
                normalized_values[key] = normalize_preset_value(state.meta, value)
            except (TypeError, ValueError) as error:
                raise TrainerDataError(f"预设字段 {key} 的值无效: {value}") from error
        return normalized_values, skipped_keys

    def _format_diff_line(
        self,
        diff: ValueDiff,
        before_label: str = "当前",
        after_label: str = "导入后",
    ) -> str:
        state = self.field_states.get(diff.key)
        label = state.meta.label if state is not None else diff.key
        return (
            f"{label} ({diff.key})"
            f" | {before_label}: {self._format_value(diff.before)}"
            f" -> {after_label}: {self._format_value(diff.after)}"
        )

    def _open_apply_preview_dialog(
        self,
        source_name: str,
        normalized_values: dict[str, Any],
        diff_items: list[ValueDiff],
        skipped_keys: list[str],
        source_kind: str,
        source_path: Path | None = None,
    ) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("导入预览" if source_kind == "预设" else "套用快照预览")
        dialog.geometry("760x520")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        summary_lines = [
            f"来源: {source_name}",
            f"可识别字段: {len(normalized_values)} 项",
            f"即将改动: {len(diff_items)} 项",
        ]
        if skipped_keys:
            summary_lines.append(f"已忽略当前模板不存在的字段: {len(skipped_keys)} 项")

        ttk.Label(
            dialog,
            text="\n".join(summary_lines),
            justify="left",
            padding=(12, 12, 12, 0),
        ).grid(row=0, column=0, sticky="ew")

        list_frame = ttk.Frame(dialog, padding=12)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        listbox = tk.Listbox(list_frame)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=scrollbar.set)

        for diff in diff_items:
            listbox.insert(tk.END, self._format_diff_line(diff))

        if skipped_keys:
            listbox.insert(tk.END, "")
            listbox.insert(tk.END, f"以下字段未导入: {', '.join(skipped_keys[:10])}")
            if len(skipped_keys) > 10:
                listbox.insert(tk.END, f"... 以及其他 {len(skipped_keys) - 10} 项")

        action_frame = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        action_frame.grid(row=2, column=0, sticky="ew")
        ttk.Button(action_frame, text="取消", command=dialog.destroy).grid(row=0, column=0)
        ttk.Button(
            action_frame,
            text="确认导入" if source_kind == "预设" else "确认套用",
            command=lambda: self._confirm_apply_values(
                dialog,
                source_name,
                normalized_values,
                skipped_keys,
                source_kind,
                source_path,
            ),
        ).grid(row=0, column=1, padx=(8, 0))

    def _confirm_apply_values(
        self,
        dialog: tk.Toplevel,
        source_name: str,
        normalized_values: dict[str, Any],
        skipped_keys: list[str],
        source_kind: str,
        source_path: Path | None = None,
    ) -> None:
        updated_count = self._apply_values_to_fields(normalized_values)
        dialog.destroy()
        skipped_text = f"，忽略 {len(skipped_keys)} 个不适用字段" if skipped_keys else ""
        if self.repository is not None and source_kind == "预设" and source_path is not None:
            try:
                self.repository.record_recent_preset(source_path, source_name, "导入")
            except OSError:
                pass

        if source_kind == "预设":
            self.status_var.set(f"已导入预设“{source_name}”，更新 {updated_count} 个字段{skipped_text}。")
        else:
            self.status_var.set(f"已套用快照“{source_name}”，更新 {updated_count} 个字段{skipped_text}。")

    def _open_snapshot_compare_dialog(self, snapshot: SnapshotData, diff_items: list[ValueDiff]) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("快照差异预览")
        dialog.geometry("760x520")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        summary_lines = [
            f"快照名称: {snapshot.snapshot_name}",
            f"创建时间: {self._format_timestamp(snapshot.created_at)}",
            f"与当前差异: {len(diff_items)} 项",
        ]
        ttk.Label(
            dialog,
            text="\n".join(summary_lines),
            justify="left",
            padding=(12, 12, 12, 0),
        ).grid(row=0, column=0, sticky="ew")

        list_frame = ttk.Frame(dialog, padding=12)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        listbox = tk.Listbox(list_frame)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=scrollbar.set)

        for diff in diff_items:
            listbox.insert(tk.END, self._format_diff_line(diff, before_label="快照", after_label="当前"))

        action_frame = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        action_frame.grid(row=2, column=0, sticky="ew")
        ttk.Button(action_frame, text="关闭", command=dialog.destroy).grid(row=0, column=0)
        ttk.Button(
            action_frame,
            text="从此快照恢复",
            command=lambda: self._apply_snapshot_from_data(dialog, snapshot),
        ).grid(row=0, column=1, padx=(8, 0))

    def _open_snapshot_pair_compare_dialog(
        self,
        left_snapshot: SnapshotData,
        right_snapshot: SnapshotData,
        diff_items: list[ValueDiff],
    ) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("快照对比")
        dialog.geometry("860x560")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        summary_lines = [
            f"快照A: {left_snapshot.snapshot_name} | {self._format_timestamp(left_snapshot.created_at)}",
            f"快照B: {right_snapshot.snapshot_name} | {self._format_timestamp(right_snapshot.created_at)}",
            f"快照差异: {len(diff_items)} 项",
        ]
        ttk.Label(
            dialog,
            text="\n".join(summary_lines),
            justify="left",
            padding=(12, 12, 12, 0),
        ).grid(row=0, column=0, sticky="ew")

        list_frame = ttk.Frame(dialog, padding=12)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        listbox = tk.Listbox(list_frame)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=scrollbar.set)

        for diff in diff_items:
            listbox.insert(tk.END, self._format_diff_line(diff, before_label="快照A", after_label="快照B"))

        action_frame = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        action_frame.grid(row=2, column=0, sticky="ew")
        ttk.Button(action_frame, text="关闭", command=dialog.destroy).grid(row=0, column=0)
        ttk.Button(
            action_frame,
            text="套用快照A",
            command=lambda: self._apply_snapshot_from_data(dialog, left_snapshot),
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(
            action_frame,
            text="套用快照B",
            command=lambda: self._apply_snapshot_from_data(dialog, right_snapshot),
        ).grid(row=0, column=2, padx=(8, 0))

    def _rename_snapshot(self, snapshot: SnapshotData, parent: tk.Misc | None = None) -> Path | None:
        if self.repository is None:
            return None

        new_name = simpledialog.askstring(
            "重命名快照",
            "输入新的快照名称：",
            initialvalue=snapshot.snapshot_name,
            parent=parent or self,
        )
        if new_name is None:
            return None

        try:
            renamed_path = self.repository.rename_snapshot(snapshot.path, new_name)
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("重命名失败", str(error), parent=parent or self)
            self.status_var.set(str(error))
            return None

        self.status_var.set(f"已重命名快照为 {renamed_path.name}。")
        return renamed_path

    def _edit_snapshot_note(self, snapshot: SnapshotData, parent: tk.Misc | None = None) -> SnapshotData | None:
        if self.repository is None:
            return None

        updated_note = simpledialog.askstring(
            "快照备注",
            "输入快照备注，可留空清空：",
            initialvalue=snapshot.snapshot_note,
            parent=parent or self,
        )
        if updated_note is None:
            return None

        try:
            updated_snapshot = self.repository.update_snapshot_note(snapshot.path, updated_note)
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("保存备注失败", str(error), parent=parent or self)
            self.status_var.set(str(error))
            return None

        if updated_snapshot.snapshot_note:
            self.status_var.set(f"已更新快照备注：{updated_snapshot.snapshot_name}")
        else:
            self.status_var.set(f"已清空快照备注：{updated_snapshot.snapshot_name}")
        return updated_snapshot

    def _batch_edit_snapshot_note(
        self,
        snapshots: list[SnapshotData],
        parent: tk.Misc | None = None,
    ) -> list[SnapshotData]:
        if self.repository is None or not snapshots:
            return []

        initial_value = snapshots[0].snapshot_note if len(snapshots) == 1 else ""
        updated_note = simpledialog.askstring(
            "批量备注",
            "输入统一备注，可留空清空所选快照的备注：",
            initialvalue=initial_value,
            parent=parent or self,
        )
        if updated_note is None:
            return []

        updated_snapshots: list[SnapshotData] = []
        try:
            for snapshot in snapshots:
                updated_snapshots.append(self.repository.update_snapshot_note(snapshot.path, updated_note))
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("批量备注失败", str(error), parent=parent or self)
            self.status_var.set(str(error))
            return []

        self.status_var.set(f"已批量更新 {len(updated_snapshots)} 个快照的备注。")
        return updated_snapshots

    def _batch_edit_snapshot_category(
        self,
        snapshots: list[SnapshotData],
        parent: tk.Misc | None = None,
    ) -> list[SnapshotData]:
        if self.repository is None or not snapshots:
            return []

        initial_value = snapshots[0].snapshot_category if len(snapshots) == 1 else ""
        updated_category = simpledialog.askstring(
            "快照分类",
            "输入分类，可留空清空分类：",
            initialvalue=initial_value,
            parent=parent or self,
        )
        if updated_category is None:
            return []

        updated_snapshots: list[SnapshotData] = []
        try:
            for snapshot in snapshots:
                updated_snapshots.append(self.repository.update_snapshot_category(snapshot.path, updated_category))
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("保存分类失败", str(error), parent=parent or self)
            self.status_var.set(str(error))
            return []

        if updated_category.strip():
            self.status_var.set(f"已为 {len(updated_snapshots)} 个快照设置分类：{updated_category.strip()}")
        else:
            self.status_var.set(f"已清空 {len(updated_snapshots)} 个快照的分类。")
        return updated_snapshots

    def _toggle_snapshot_favorite(
        self,
        snapshots: list[SnapshotData],
        parent: tk.Misc | None = None,
    ) -> list[SnapshotData]:
        if self.repository is None or not snapshots:
            return []

        target_value = any(not snapshot.is_favorite for snapshot in snapshots)
        updated_snapshots: list[SnapshotData] = []
        try:
            for snapshot in snapshots:
                updated_snapshots.append(self.repository.set_snapshot_favorite(snapshot.path, target_value))
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("收藏操作失败", str(error), parent=parent or self)
            self.status_var.set(str(error))
            return []

        status_text = "已收藏" if target_value else "已取消收藏"
        self.status_var.set(f"{status_text} {len(updated_snapshots)} 个快照。")
        return updated_snapshots

    def _delete_snapshots(self, snapshots: list[SnapshotData], parent: tk.Misc | None = None) -> bool:
        if self.repository is None or not snapshots:
            return False

        names_preview = "、".join(snapshot.snapshot_name for snapshot in snapshots[:3])
        if len(snapshots) > 3:
            names_preview = f"{names_preview} 等 {len(snapshots)} 个快照"
        confirmed = messagebox.askyesno(
            "删除快照",
            f"确定要删除 {names_preview} 吗？这个操作不能撤销。",
            parent=parent or self,
        )
        if not confirmed:
            return False

        try:
            for snapshot in snapshots:
                self.repository.delete_snapshot(snapshot.path)
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("删除快照失败", str(error), parent=parent or self)
            self.status_var.set(str(error))
            return False

        self.status_var.set(f"已删除 {len(snapshots)} 个快照。")
        return True

    def _apply_snapshot_from_data(self, dialog: tk.Toplevel | None, snapshot: SnapshotData) -> None:
        try:
            current_values = self._collect_values()
            normalized_values, skipped_keys = self._normalize_preset_values(snapshot.values)
            diff_items = build_value_diff(current_values, normalized_values)
        except (TrainerDataError, OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("套用快照失败", str(error))
            self.status_var.set(str(error))
            return

        if not normalized_values:
            messagebox.showinfo("没有可套用的字段", "这个快照与当前模板不匹配。")
            self.status_var.set("快照没有可应用到当前模板的字段。")
            return
        if not diff_items:
            messagebox.showinfo("快照没有变化", "这个快照与当前数值一致。")
            self.status_var.set("快照没有带来新的改动。")
            return

        if dialog is not None:
            dialog.destroy()
        self._open_apply_preview_dialog(
            snapshot.snapshot_name,
            normalized_values,
            diff_items,
            skipped_keys,
            source_kind="快照",
        )

    def _collect_values(self) -> dict[str, Any]:
        if self.loaded_profile is None:
            raise TrainerDataError("No profile is currently loaded.")

        merged_values = dict(self.loaded_profile.values)
        for key, state in self.field_states.items():
            meta = state.meta
            raw_value = state.variable.get()

            if meta.is_toggle:
                merged_values[key] = 1 if bool(raw_value) else 0
                continue

            parsed_value = self._parse_numeric_value(meta, raw_value)
            merged_values[key] = parsed_value

        return merged_values

    def _parse_numeric_value(self, meta: SettingMeta, raw_value: Any) -> float | int:
        text = str(raw_value).strip()
        if not text:
            raise TrainerDataError(f"{meta.label} 不能为空。")

        numeric_value = float(text)
        if meta.min_value is not None and numeric_value < float(meta.min_value):
            raise TrainerDataError(f"{meta.label} 不能小于 {self._format_value(meta.min_value)}。")
        if meta.max_value is not None and numeric_value > float(meta.max_value):
            raise TrainerDataError(f"{meta.label} 不能大于 {self._format_value(meta.max_value)}。")

        if isinstance(meta.default_value, int) and not isinstance(meta.default_value, bool):
            return int(round(numeric_value))
        if numeric_value.is_integer() and meta.step == 1:
            return int(numeric_value)
        return numeric_value

    def _save_profile(self) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        try:
            values = self._collect_values()
            backup_path = self.repository.save_profile(self.loaded_profile, values)
        except TrainerDataError as error:
            messagebox.showerror("保存失败", str(error))
            self.status_var.set(str(error))
            return

        self.status_var.set(f"已保存 {self.loaded_profile.profile_path.name}，备份位于 {backup_path}.")
        self._load_selected_profile()

    def _export_preset(self, changed_only: bool = False) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        try:
            values = self._collect_changed_values() if changed_only else self._collect_values()
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("导出失败", str(error))
            self.status_var.set(str(error))
            return

        if changed_only and not values:
            messagebox.showinfo("没有可导出的改动", "当前没有未保存改动，暂时没有内容可以导出。")
            self.status_var.set("当前没有未保存改动。")
            return

        preset_name = Path(self.loaded_profile.profile_path.name).stem
        default_name = f"{preset_name}-changes.json" if changed_only else f"{preset_name}-preset.json"
        destination = filedialog.asksaveasfilename(
            title="导出改动预设" if changed_only else "导出当前预设",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            initialfile=default_name,
        )
        if not destination:
            return

        try:
            self.repository.export_preset(Path(destination), self.loaded_profile.profile_path.name, values)
            try:
                self.repository.record_recent_preset(
                    Path(destination),
                    self.loaded_profile.profile_path.name,
                    "导出",
                )
            except OSError:
                pass
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("导出失败", str(error))
            self.status_var.set(str(error))
            return

        if changed_only:
            self.status_var.set(f"已导出 {len(values)} 项改动到 {destination}。")
        else:
            self.status_var.set(f"已导出预设到 {destination}。")

    def _import_preset(self) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        source = filedialog.askopenfilename(
            title="导入预设",
            filetypes=[("JSON 文件", "*.json")],
            initialdir=str(Path.cwd()),
        )
        if not source:
            return

        self._import_preset_from_path(Path(source))

    def _import_preset_from_path(self, preset_path: Path) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        try:
            preset = self.repository.import_preset(preset_path)
            current_values = self._collect_values()
            normalized_values, skipped_keys = self._normalize_preset_values(preset.values)
            diff_items = build_value_diff(current_values, normalized_values)
        except (TrainerDataError, OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("导入失败", str(error))
            self.status_var.set(str(error))
            return

        if not normalized_values:
            messagebox.showinfo("没有可导入的字段", "这个预设里的字段与当前模板不匹配。")
            self.status_var.set("导入的预设没有可应用到当前模板的字段。")
            return
        if not diff_items:
            ignored_text = f"，忽略 {len(skipped_keys)} 个不适用字段" if skipped_keys else ""
            messagebox.showinfo("预设没有变化", f"这个预设与当前数值一致{ignored_text}。")
            self.status_var.set(f"预设没有带来新的改动{ignored_text}。")
            return

        self._open_apply_preview_dialog(
            preset.source_profile,
            normalized_values,
            diff_items,
            skipped_keys,
            source_kind="预设",
            source_path=preset_path,
        )

    def _save_snapshot(self) -> Path | None:
        if self.repository is None or self.loaded_profile is None:
            return None

        try:
            values = self._collect_values()
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("保存快照失败", str(error))
            self.status_var.set(str(error))
            return None

        snapshot_name = simpledialog.askstring(
            "保存当前快照",
            "给这次快照起个名字，可留空自动命名：",
            parent=self,
        )
        if snapshot_name is None:
            return None

        try:
            snapshot_path = self.repository.create_snapshot(
                self.loaded_profile.profile_path.name,
                values,
                snapshot_name=snapshot_name or None,
            )
        except (TrainerDataError, OSError) as error:
            messagebox.showerror("保存快照失败", str(error))
            self.status_var.set(str(error))
            return None

        self.status_var.set(f"已保存当前快照到 {snapshot_path}。")
        return snapshot_path

    def _open_reuse_center(self) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        dialog = tk.Toplevel(self)
        dialog.title("预设 / 快照中心")
        dialog.geometry("980x560")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=1)
        dialog.rowconfigure(1, weight=1)

        ttk.Label(
            dialog,
            text="这里集中管理最近预设和当前模板快照。双击列表项也可以直接操作。",
            justify="left",
            padding=(12, 12, 12, 0),
        ).grid(row=0, column=0, columnspan=2, sticky="ew")

        recent_presets: list[RecentPresetEntry] = []
        snapshots: list[SnapshotData] = []

        preset_frame = ttk.LabelFrame(dialog, text="最近预设", padding=12)
        preset_frame.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=12)
        preset_frame.columnconfigure(0, weight=1)
        preset_frame.rowconfigure(0, weight=1)

        preset_listbox = tk.Listbox(preset_frame)
        preset_listbox.grid(row=0, column=0, sticky="nsew")
        preset_scrollbar = ttk.Scrollbar(preset_frame, orient="vertical", command=preset_listbox.yview)
        preset_scrollbar.grid(row=0, column=1, sticky="ns")
        preset_listbox.configure(yscrollcommand=preset_scrollbar.set)

        preset_action_frame = ttk.Frame(preset_frame)
        preset_action_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        snapshot_frame = ttk.LabelFrame(dialog, text="当前模板快照", padding=12)
        snapshot_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=12)
        snapshot_frame.columnconfigure(0, weight=1)
        snapshot_frame.rowconfigure(0, weight=1)

        snapshot_listbox = tk.Listbox(snapshot_frame, selectmode=tk.EXTENDED)
        snapshot_listbox.grid(row=0, column=0, sticky="nsew")
        snapshot_scrollbar = ttk.Scrollbar(snapshot_frame, orient="vertical", command=snapshot_listbox.yview)
        snapshot_scrollbar.grid(row=0, column=1, sticky="ns")
        snapshot_listbox.configure(yscrollcommand=snapshot_scrollbar.set)

        snapshot_action_frame = ttk.Frame(snapshot_frame)
        snapshot_action_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        def refresh_lists() -> None:
            nonlocal recent_presets, snapshots
            recent_presets = self.repository.list_recent_presets(limit=10)
            snapshots = self.repository.list_snapshots(self.loaded_profile.profile_path.name, limit=12)

            preset_listbox.delete(0, tk.END)
            for entry in recent_presets:
                preset_listbox.insert(tk.END, self._format_recent_preset_entry(entry))
            if not recent_presets:
                preset_listbox.insert(tk.END, "暂无最近预设。先导出或导入一次预设即可出现在这里。")

            snapshot_listbox.delete(0, tk.END)
            for snapshot in snapshots:
                snapshot_listbox.insert(tk.END, self._format_snapshot_entry(snapshot))
            if not snapshots:
                snapshot_listbox.insert(tk.END, "当前模板还没有快照。点击下方按钮先保存一个。")

        def apply_selected_preset() -> None:
            selection = preset_listbox.curselection()
            if not selection or not recent_presets:
                messagebox.showwarning("未选择预设", "请先选择一个最近预设。", parent=dialog)
                return
            selected_entry = recent_presets[selection[0]]
            self._import_preset_from_path(selected_entry.path)

        def get_selected_snapshots(min_count: int = 1, max_count: int | None = None) -> list[SnapshotData]:
            selection = list(snapshot_listbox.curselection())
            if not selection or not snapshots:
                messagebox.showwarning("未选择快照", "请先选择快照。", parent=dialog)
                return []

            selected_items = [snapshots[index] for index in selection]
            if len(selected_items) < min_count:
                messagebox.showwarning("选择数量不足", f"请至少选择 {min_count} 个快照。", parent=dialog)
                return []
            if max_count is not None and len(selected_items) > max_count:
                messagebox.showwarning("选择过多", f"请最多选择 {max_count} 个快照。", parent=dialog)
                return []
            return selected_items

        def compare_selected_snapshot() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return
            selected_snapshot = selected_items[0]
            try:
                current_values = self._collect_values()
            except TrainerDataError as error:
                messagebox.showerror("对比失败", str(error), parent=dialog)
                self.status_var.set(str(error))
                return

            diff_items = build_full_value_diff(selected_snapshot.values, current_values)
            if not diff_items:
                messagebox.showinfo("没有差异", "当前数值与这个快照完全一致。", parent=dialog)
                self.status_var.set("当前数值与所选快照一致。")
                return

            self._open_snapshot_compare_dialog(selected_snapshot, diff_items)

        def compare_two_snapshots() -> None:
            selected_items = get_selected_snapshots(min_count=2, max_count=2)
            if not selected_items:
                return

            left_snapshot, right_snapshot = selected_items
            diff_items = build_full_value_diff(left_snapshot.values, right_snapshot.values)
            if not diff_items:
                messagebox.showinfo("没有差异", "这两个快照完全一致。", parent=dialog)
                self.status_var.set("所选两个快照完全一致。")
                return

            self._open_snapshot_pair_compare_dialog(left_snapshot, right_snapshot, diff_items)

        def apply_selected_snapshot() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return
            self._apply_snapshot_from_data(dialog, selected_items[0])

        def rename_selected_snapshot() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return
            renamed_path = self._rename_snapshot(selected_items[0], parent=dialog)
            if renamed_path is not None:
                refresh_lists()

        def delete_selected_snapshots() -> None:
            selected_items = get_selected_snapshots(min_count=1)
            if not selected_items:
                return
            if self._delete_snapshots(selected_items, parent=dialog):
                refresh_lists()

        def save_snapshot_and_refresh() -> None:
            snapshot_path = self._save_snapshot()
            if snapshot_path is not None:
                refresh_lists()

        ttk.Button(preset_action_frame, text="套用选中预设", command=apply_selected_preset).grid(row=0, column=0)
        ttk.Button(preset_action_frame, text="刷新列表", command=refresh_lists).grid(row=0, column=1, padx=(8, 0))

        ttk.Button(snapshot_action_frame, text="保存当前快照", command=save_snapshot_and_refresh).grid(row=0, column=0)
        ttk.Button(snapshot_action_frame, text="对比当前", command=compare_selected_snapshot).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="比较两个快照", command=compare_two_snapshots).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="套用选中快照", command=apply_selected_snapshot).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="重命名快照", command=rename_selected_snapshot).grid(row=0, column=4, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="删除快照", command=delete_selected_snapshots).grid(row=0, column=5, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="刷新列表", command=refresh_lists).grid(row=0, column=6, padx=(8, 0))

        preset_listbox.bind("<Double-Button-1>", lambda _event: apply_selected_preset())
        snapshot_listbox.bind("<Double-Button-1>", lambda _event: compare_selected_snapshot())

        refresh_lists()

    def _open_reuse_center(self) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        dialog = tk.Toplevel(self)
        dialog.title("预设 / 快照中心")
        dialog.geometry("1120x640")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=1)
        dialog.rowconfigure(1, weight=1)

        ttk.Label(
            dialog,
            text="左边整理最近预设，右边搜索和管理快照。双击列表项也可以直接操作，尽量做到不用记流程。",
            justify="left",
            padding=(12, 12, 12, 0),
        ).grid(row=0, column=0, columnspan=2, sticky="ew")

        recent_presets: list[RecentPresetEntry] = []
        visible_recent_presets: list[RecentPresetEntry] = []
        snapshots: list[SnapshotData] = []
        visible_snapshots: list[SnapshotData] = []
        snapshot_search_var = tk.StringVar()
        snapshot_hint_var = tk.StringVar(value="可按快照名称或备注搜索。")

        preset_frame = ttk.LabelFrame(dialog, text="最近预设", padding=12)
        preset_frame.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=12)
        preset_frame.columnconfigure(0, weight=1)
        preset_frame.rowconfigure(0, weight=1)

        preset_listbox = tk.Listbox(preset_frame)
        preset_listbox.grid(row=0, column=0, sticky="nsew")
        preset_scrollbar = ttk.Scrollbar(preset_frame, orient="vertical", command=preset_listbox.yview)
        preset_scrollbar.grid(row=0, column=1, sticky="ns")
        preset_listbox.configure(yscrollcommand=preset_scrollbar.set)

        preset_action_frame = ttk.Frame(preset_frame)
        preset_action_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        snapshot_frame = ttk.LabelFrame(dialog, text="当前模板快照", padding=12)
        snapshot_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=12)
        snapshot_frame.columnconfigure(0, weight=1)
        snapshot_frame.rowconfigure(2, weight=1)

        snapshot_search_frame = ttk.Frame(snapshot_frame)
        snapshot_search_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        snapshot_search_frame.columnconfigure(1, weight=1)
        ttk.Label(snapshot_search_frame, text="搜索").grid(row=0, column=0, sticky="w")
        ttk.Entry(snapshot_search_frame, textvariable=snapshot_search_var).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(8, 8),
        )
        ttk.Button(snapshot_search_frame, text="清空", command=lambda: snapshot_search_var.set("")).grid(row=0, column=2)

        ttk.Label(snapshot_frame, textvariable=snapshot_hint_var, foreground="#666666").grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8),
        )

        snapshot_listbox = tk.Listbox(snapshot_frame, selectmode=tk.EXTENDED)
        snapshot_listbox.grid(row=2, column=0, sticky="nsew")
        snapshot_scrollbar = ttk.Scrollbar(snapshot_frame, orient="vertical", command=snapshot_listbox.yview)
        snapshot_scrollbar.grid(row=2, column=1, sticky="ns")
        snapshot_listbox.configure(yscrollcommand=snapshot_scrollbar.set)

        snapshot_action_frame = ttk.Frame(snapshot_frame)
        snapshot_action_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        def refresh_recent_preset_list() -> None:
            nonlocal visible_recent_presets
            visible_recent_presets = list(recent_presets)
            preset_listbox.delete(0, tk.END)
            for entry in visible_recent_presets:
                preset_listbox.insert(tk.END, self._format_recent_preset_entry(entry))
            if not visible_recent_presets:
                preset_listbox.insert(tk.END, "最近预设列表为空。导出或导入过的预设会显示在这里。")

        def refresh_snapshot_list() -> None:
            nonlocal visible_snapshots
            keyword = snapshot_search_var.get().strip()
            visible_snapshots = [
                snapshot
                for snapshot in snapshots
                if snapshot_matches_keyword(snapshot, keyword)
            ]

            snapshot_listbox.delete(0, tk.END)
            for snapshot in visible_snapshots:
                snapshot_listbox.insert(tk.END, self._format_snapshot_entry(snapshot))

            if not snapshots:
                snapshot_hint_var.set("当前模板还没有快照，先保存一个就能在这里管理。")
                snapshot_listbox.insert(tk.END, "当前模板还没有快照。")
                return

            if keyword and visible_snapshots:
                snapshot_hint_var.set(f"已筛到 {len(visible_snapshots)} / {len(snapshots)} 个快照。")
            elif keyword:
                snapshot_hint_var.set("没有匹配的快照，试试名称、备注或更短的关键词。")
                snapshot_listbox.insert(tk.END, "没有匹配的快照。")
            else:
                snapshot_hint_var.set(f"共 {len(snapshots)} 个快照，可按名称或备注搜索。")

        def refresh_lists() -> None:
            nonlocal recent_presets, snapshots
            recent_presets = self.repository.list_recent_presets(limit=12)
            snapshots = self.repository.list_snapshots(self.loaded_profile.profile_path.name, limit=50)
            refresh_recent_preset_list()
            refresh_snapshot_list()

        def get_selected_recent_preset() -> RecentPresetEntry | None:
            selection = list(preset_listbox.curselection())
            if not selection or not visible_recent_presets:
                messagebox.showwarning("未选择预设", "请先选择一个最近预设。", parent=dialog)
                return None
            return visible_recent_presets[selection[0]]

        def apply_selected_preset() -> None:
            selected_entry = get_selected_recent_preset()
            if selected_entry is None:
                return
            self._import_preset_from_path(selected_entry.path)

        def remove_selected_recent_preset() -> None:
            selected_entry = get_selected_recent_preset()
            if selected_entry is None:
                return

            confirmed = messagebox.askyesno(
                "移除最近预设",
                f"要从最近预设列表里移除 {selected_entry.path.name} 吗？\n这不会删除实际的预设文件。",
                parent=dialog,
            )
            if not confirmed:
                return

            removed = self.repository.remove_recent_preset(selected_entry.path)
            if removed:
                self.status_var.set(f"已移除最近预设记录：{selected_entry.path.name}")
            refresh_lists()

        def cleanup_recent_presets() -> None:
            removed_count = self.repository.cleanup_missing_recent_presets()
            if removed_count:
                self.status_var.set(f"已清理 {removed_count} 条失效的最近预设记录。")
            else:
                self.status_var.set("最近预设里没有失效记录。")
            refresh_lists()

        def clear_all_recent_presets() -> None:
            confirmed = messagebox.askyesno(
                "清空最近预设",
                "要清空最近预设列表吗？\n这不会删除任何实际的预设文件。",
                parent=dialog,
            )
            if not confirmed:
                return

            cleared_count = self.repository.clear_recent_presets()
            self.status_var.set(f"已清空最近预设列表，共移除 {cleared_count} 条记录。")
            refresh_lists()

        def get_selected_snapshots(min_count: int = 1, max_count: int | None = None) -> list[SnapshotData]:
            selection = list(snapshot_listbox.curselection())
            if not selection or not visible_snapshots:
                messagebox.showwarning("未选择快照", "请先选择快照。", parent=dialog)
                return []

            selected_items = [visible_snapshots[index] for index in selection]
            if len(selected_items) < min_count:
                messagebox.showwarning("选择数量不足", f"请至少选择 {min_count} 个快照。", parent=dialog)
                return []
            if max_count is not None and len(selected_items) > max_count:
                messagebox.showwarning("选择过多", f"请最多选择 {max_count} 个快照。", parent=dialog)
                return []
            return selected_items

        def compare_selected_snapshot() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return
            selected_snapshot = selected_items[0]
            try:
                current_values = self._collect_values()
            except TrainerDataError as error:
                messagebox.showerror("对比失败", str(error), parent=dialog)
                self.status_var.set(str(error))
                return

            diff_items = build_full_value_diff(selected_snapshot.values, current_values)
            if not diff_items:
                messagebox.showinfo("没有差异", "当前数值与这个快照完全一致。", parent=dialog)
                self.status_var.set("当前数值与所选快照一致。")
                return

            self._open_snapshot_compare_dialog(selected_snapshot, diff_items)

        def compare_two_snapshots() -> None:
            selected_items = get_selected_snapshots(min_count=2, max_count=2)
            if not selected_items:
                return

            left_snapshot, right_snapshot = selected_items
            diff_items = build_full_value_diff(left_snapshot.values, right_snapshot.values)
            if not diff_items:
                messagebox.showinfo("没有差异", "这两个快照完全一致。", parent=dialog)
                self.status_var.set("所选两个快照完全一致。")
                return

            self._open_snapshot_pair_compare_dialog(left_snapshot, right_snapshot, diff_items)

        def apply_selected_snapshot() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return
            self._apply_snapshot_from_data(dialog, selected_items[0])

        def edit_selected_snapshot_note() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return
            updated_snapshot = self._edit_snapshot_note(selected_items[0], parent=dialog)
            if updated_snapshot is not None:
                refresh_lists()

        def rename_selected_snapshot() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return
            renamed_path = self._rename_snapshot(selected_items[0], parent=dialog)
            if renamed_path is not None:
                refresh_lists()

        def delete_selected_snapshots() -> None:
            selected_items = get_selected_snapshots(min_count=1)
            if not selected_items:
                return
            if self._delete_snapshots(selected_items, parent=dialog):
                refresh_lists()

        def save_snapshot_and_refresh() -> None:
            snapshot_path = self._save_snapshot()
            if snapshot_path is not None:
                refresh_lists()

        snapshot_search_var.trace_add("write", lambda *_args: refresh_snapshot_list())

        ttk.Button(preset_action_frame, text="套用选中", command=apply_selected_preset).grid(row=0, column=0)
        ttk.Button(preset_action_frame, text="移除记录", command=remove_selected_recent_preset).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(preset_action_frame, text="清理失效", command=cleanup_recent_presets).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(preset_action_frame, text="清空列表", command=clear_all_recent_presets).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(preset_action_frame, text="刷新列表", command=refresh_lists).grid(row=0, column=4, padx=(8, 0))

        ttk.Button(snapshot_action_frame, text="保存当前快照", command=save_snapshot_and_refresh).grid(row=0, column=0)
        ttk.Button(snapshot_action_frame, text="备注快照", command=edit_selected_snapshot_note).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="对比当前", command=compare_selected_snapshot).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="比较两个快照", command=compare_two_snapshots).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="套用选中快照", command=apply_selected_snapshot).grid(row=1, column=0, pady=(8, 0))
        ttk.Button(snapshot_action_frame, text="重命名快照", command=rename_selected_snapshot).grid(row=1, column=1, padx=(8, 0), pady=(8, 0))
        ttk.Button(snapshot_action_frame, text="删除快照", command=delete_selected_snapshots).grid(row=1, column=2, padx=(8, 0), pady=(8, 0))
        ttk.Button(snapshot_action_frame, text="刷新列表", command=refresh_lists).grid(row=1, column=3, padx=(8, 0), pady=(8, 0))

        preset_listbox.bind("<Double-Button-1>", lambda _event: apply_selected_preset())
        snapshot_listbox.bind("<Double-Button-1>", lambda _event: compare_selected_snapshot())

        refresh_lists()

    def _open_reuse_center(self) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        dialog = tk.Toplevel(self)
        dialog.title("预设 / 快照中心")
        dialog.geometry("1180x700")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=1)
        dialog.rowconfigure(1, weight=1)

        ttk.Label(
            dialog,
            text="左边整理最近预设，右边按搜索、分类、收藏状态筛选快照。单个和多个快照都能直接批量操作。",
            justify="left",
            padding=(12, 12, 12, 0),
        ).grid(row=0, column=0, columnspan=2, sticky="ew")

        recent_presets: list[RecentPresetEntry] = []
        visible_recent_presets: list[RecentPresetEntry] = []
        snapshots: list[SnapshotData] = []
        visible_snapshots: list[SnapshotData] = []
        snapshot_search_var = tk.StringVar()
        snapshot_filter_var = tk.StringVar(value="全部")
        snapshot_category_var = tk.StringVar(value="全部分类")
        snapshot_sort_var = tk.StringVar(value="最新优先")
        snapshot_hint_var = tk.StringVar(value="可按名称、备注或分类搜索。")

        preset_frame = ttk.LabelFrame(dialog, text="最近预设", padding=12)
        preset_frame.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=12)
        preset_frame.columnconfigure(0, weight=1)
        preset_frame.rowconfigure(0, weight=1)

        preset_listbox = tk.Listbox(preset_frame)
        preset_listbox.grid(row=0, column=0, sticky="nsew")
        preset_scrollbar = ttk.Scrollbar(preset_frame, orient="vertical", command=preset_listbox.yview)
        preset_scrollbar.grid(row=0, column=1, sticky="ns")
        preset_listbox.configure(yscrollcommand=preset_scrollbar.set)

        preset_action_frame = ttk.Frame(preset_frame)
        preset_action_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        snapshot_frame = ttk.LabelFrame(dialog, text="当前模板快照", padding=12)
        snapshot_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=12)
        snapshot_frame.columnconfigure(0, weight=1)
        snapshot_frame.rowconfigure(3, weight=1)

        filter_frame = ttk.Frame(snapshot_frame)
        filter_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        filter_frame.columnconfigure(1, weight=1)
        ttk.Label(filter_frame, text="搜索").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(filter_frame, textvariable=snapshot_search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Label(filter_frame, text="排序").grid(row=0, column=2, sticky="e")
        sort_combo = ttk.Combobox(
            filter_frame,
            state="readonly",
            textvariable=snapshot_sort_var,
            values=["最新优先", "最早优先", "名称排序", "收藏优先", "分类排序"],
            width=18,
        )
        sort_combo.grid(row=0, column=3, sticky="w")
        ttk.Button(filter_frame, text="清空", command=lambda: snapshot_search_var.set("")).grid(row=0, column=4, padx=(8, 0))

        ttk.Label(filter_frame, text="筛选").grid(row=1, column=0, sticky="w", pady=(8, 0))
        filter_combo = ttk.Combobox(
            filter_frame,
            state="readonly",
            textvariable=snapshot_filter_var,
            values=["全部", "仅收藏", "仅有备注", "仅有分类"],
        )
        filter_combo.grid(row=1, column=1, sticky="w", padx=(8, 8), pady=(8, 0))

        ttk.Label(filter_frame, text="分类").grid(row=1, column=2, sticky="e", pady=(8, 0))
        category_combo = ttk.Combobox(
            filter_frame,
            state="readonly",
            textvariable=snapshot_category_var,
            values=["全部分类"],
            width=20,
        )
        category_combo.grid(row=1, column=3, sticky="w", pady=(8, 0))

        ttk.Label(snapshot_frame, textvariable=snapshot_hint_var, foreground="#666666").grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8),
        )

        ttk.Label(
            snapshot_frame,
            text="提示：先在列表里选中快照，再点下面按钮。复制适合留分支版本，导出成预设适合跨模板复用。",
            foreground="#666666",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))

        snapshot_listbox = tk.Listbox(snapshot_frame, selectmode=tk.EXTENDED)
        snapshot_listbox.grid(row=3, column=0, sticky="nsew")
        snapshot_scrollbar = ttk.Scrollbar(snapshot_frame, orient="vertical", command=snapshot_listbox.yview)
        snapshot_scrollbar.grid(row=3, column=1, sticky="ns")
        snapshot_listbox.configure(yscrollcommand=snapshot_scrollbar.set)

        snapshot_action_frame = ttk.Frame(snapshot_frame)
        snapshot_action_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        def snapshot_visible(snapshot: SnapshotData) -> bool:
            keyword = snapshot_search_var.get().strip()
            filter_mode = snapshot_filter_var.get().strip()
            selected_category = snapshot_category_var.get().strip()

            if not snapshot_matches_keyword(snapshot, keyword):
                return False
            if filter_mode == "仅收藏" and not snapshot.is_favorite:
                return False
            if filter_mode == "仅有备注" and not snapshot.snapshot_note:
                return False
            if filter_mode == "仅有分类" and not snapshot.snapshot_category:
                return False
            if selected_category and selected_category != "全部分类" and snapshot.snapshot_category != selected_category:
                return False
            return True

        def refresh_recent_preset_list() -> None:
            nonlocal visible_recent_presets
            visible_recent_presets = list(recent_presets)
            preset_listbox.delete(0, tk.END)
            for entry in visible_recent_presets:
                preset_listbox.insert(tk.END, self._format_recent_preset_entry(entry))
            if not visible_recent_presets:
                preset_listbox.insert(tk.END, "最近预设列表为空。导出或导入过的预设会显示在这里。")

        def refresh_snapshot_filters() -> None:
            categories = sorted({snapshot.snapshot_category for snapshot in snapshots if snapshot.snapshot_category})
            category_values = ["全部分类", *categories]
            category_combo["values"] = category_values
            if snapshot_category_var.get() not in category_values:
                snapshot_category_var.set("全部分类")

        def sort_snapshots(items: list[SnapshotData]) -> list[SnapshotData]:
            sort_mode = snapshot_sort_var.get().strip()
            newest_first = sorted(
                items,
                key=lambda snapshot: (snapshot.created_at, snapshot.snapshot_name.casefold()),
                reverse=True,
            )
            if sort_mode == "最早优先":
                return list(reversed(newest_first))
            if sort_mode == "名称排序":
                return sorted(
                    newest_first,
                    key=lambda snapshot: (
                        snapshot.snapshot_name.casefold(),
                        snapshot.created_at,
                    ),
                )
            if sort_mode == "收藏优先":
                return sorted(
                    newest_first,
                    key=lambda snapshot: (
                        not snapshot.is_favorite,
                        snapshot.snapshot_name.casefold(),
                    ),
                )
            if sort_mode == "分类排序":
                return sorted(
                    newest_first,
                    key=lambda snapshot: (
                        snapshot.snapshot_category == "",
                        (snapshot.snapshot_category or "未分类").casefold(),
                        snapshot.snapshot_name.casefold(),
                    ),
                )
            return newest_first

        def refresh_snapshot_list() -> None:
            nonlocal visible_snapshots
            visible_snapshots = sort_snapshots([snapshot for snapshot in snapshots if snapshot_visible(snapshot)])

            snapshot_listbox.delete(0, tk.END)
            for snapshot in visible_snapshots:
                snapshot_listbox.insert(tk.END, self._format_snapshot_entry(snapshot))

            if not snapshots:
                snapshot_hint_var.set("当前模板还没有快照，先保存一个就能在这里管理。")
                snapshot_listbox.insert(tk.END, "当前模板还没有快照。")
                return

            if not visible_snapshots:
                snapshot_hint_var.set("没有匹配的快照，试试放宽筛选条件。")
                snapshot_listbox.insert(tk.END, "没有匹配的快照。")
                return

            favorite_count = sum(1 for snapshot in snapshots if snapshot.is_favorite)
            category_count = sum(1 for snapshot in snapshots if snapshot.snapshot_category)
            note_count = sum(1 for snapshot in snapshots if snapshot.snapshot_note)
            snapshot_hint_var.set(
                f"已显示 {len(visible_snapshots)} / {len(snapshots)} 个快照，收藏 {favorite_count} 个，已分类 {category_count} 个，有备注 {note_count} 个，当前排序：{snapshot_sort_var.get()}。"
            )

        def refresh_lists() -> None:
            nonlocal recent_presets, snapshots
            recent_presets = self.repository.list_recent_presets(limit=12)
            snapshots = self.repository.list_snapshots(self.loaded_profile.profile_path.name, limit=80)
            refresh_recent_preset_list()
            refresh_snapshot_filters()
            refresh_snapshot_list()

        def get_selected_recent_preset() -> RecentPresetEntry | None:
            selection = list(preset_listbox.curselection())
            if not selection or not visible_recent_presets:
                messagebox.showwarning("未选择预设", "请先选择一个最近预设。", parent=dialog)
                return None
            return visible_recent_presets[selection[0]]

        def get_selected_snapshots(min_count: int = 1, max_count: int | None = None) -> list[SnapshotData]:
            selection = list(snapshot_listbox.curselection())
            if not selection or not visible_snapshots:
                messagebox.showwarning("未选择快照", "请先选择快照。", parent=dialog)
                return []

            selected_items = [visible_snapshots[index] for index in selection]
            if len(selected_items) < min_count:
                messagebox.showwarning("选择数量不足", f"请至少选择 {min_count} 个快照。", parent=dialog)
                return []
            if max_count is not None and len(selected_items) > max_count:
                messagebox.showwarning("选择过多", f"请最多选择 {max_count} 个快照。", parent=dialog)
                return []
            return selected_items

        def apply_selected_preset() -> None:
            selected_entry = get_selected_recent_preset()
            if selected_entry is None:
                return
            self._import_preset_from_path(selected_entry.path)

        def remove_selected_recent_preset() -> None:
            selected_entry = get_selected_recent_preset()
            if selected_entry is None:
                return

            confirmed = messagebox.askyesno(
                "移除最近预设",
                f"要从最近预设列表里移除 {selected_entry.path.name} 吗？\n这不会删除实际的预设文件。",
                parent=dialog,
            )
            if not confirmed:
                return

            if self.repository.remove_recent_preset(selected_entry.path):
                self.status_var.set(f"已移除最近预设记录：{selected_entry.path.name}")
            refresh_lists()

        def cleanup_recent_presets() -> None:
            removed_count = self.repository.cleanup_missing_recent_presets()
            if removed_count:
                self.status_var.set(f"已清理 {removed_count} 条失效的最近预设记录。")
            else:
                self.status_var.set("最近预设里没有失效记录。")
            refresh_lists()

        def clear_all_recent_presets() -> None:
            confirmed = messagebox.askyesno(
                "清空最近预设",
                "要清空最近预设列表吗？\n这不会删除任何实际的预设文件。",
                parent=dialog,
            )
            if not confirmed:
                return

            cleared_count = self.repository.clear_recent_presets()
            self.status_var.set(f"已清空最近预设列表，共移除 {cleared_count} 条记录。")
            refresh_lists()

        def compare_selected_snapshot() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return

            selected_snapshot = selected_items[0]
            try:
                current_values = self._collect_values()
            except TrainerDataError as error:
                messagebox.showerror("对比失败", str(error), parent=dialog)
                self.status_var.set(str(error))
                return

            diff_items = build_full_value_diff(selected_snapshot.values, current_values)
            if not diff_items:
                messagebox.showinfo("没有差异", "当前数值与这个快照完全一致。", parent=dialog)
                self.status_var.set("当前数值与所选快照一致。")
                return

            self._open_snapshot_compare_dialog(selected_snapshot, diff_items)

        def compare_two_snapshots() -> None:
            selected_items = get_selected_snapshots(min_count=2, max_count=2)
            if not selected_items:
                return

            left_snapshot, right_snapshot = selected_items
            diff_items = build_full_value_diff(left_snapshot.values, right_snapshot.values)
            if not diff_items:
                messagebox.showinfo("没有差异", "这两个快照完全一致。", parent=dialog)
                self.status_var.set("所选两个快照完全一致。")
                return

            self._open_snapshot_pair_compare_dialog(left_snapshot, right_snapshot, diff_items)

        def apply_selected_snapshot() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return
            self._apply_snapshot_from_data(dialog, selected_items[0])

        def duplicate_selected_snapshots() -> None:
            selected_items = get_selected_snapshots(min_count=1)
            if not selected_items:
                return

            try:
                duplicate_paths = [self.repository.duplicate_snapshot(snapshot.path) for snapshot in selected_items]
                duplicate_names = [self.repository.load_snapshot(path).snapshot_name for path in duplicate_paths]
            except (TrainerDataError, OSError) as error:
                messagebox.showerror("复制快照失败", str(error), parent=dialog)
                self.status_var.set(str(error))
                return

            refresh_lists()
            if len(duplicate_names) == 1:
                self.status_var.set(f"已复制快照：{duplicate_names[0]}")
            else:
                self.status_var.set(f"已复制 {len(duplicate_names)} 个快照，名称已自动追加 -copy。")

        def export_selected_snapshot_as_preset() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return

            selected_snapshot = selected_items[0]
            default_name = f"{sanitize_file_component(selected_snapshot.snapshot_name, 'snapshot')}-preset.json"
            destination = filedialog.asksaveasfilename(
                title="把快照导出成预设",
                defaultextension=".json",
                filetypes=[("JSON 文件", "*.json")],
                initialfile=default_name,
                initialdir=self.settings_dir_var.get() or str(Path.cwd()),
                parent=dialog,
            )
            if not destination:
                return

            destination_path = Path(destination)
            try:
                self.repository.export_preset(destination_path, selected_snapshot.source_profile, selected_snapshot.values)
                try:
                    self.repository.record_recent_preset(
                        destination_path,
                        selected_snapshot.source_profile,
                        "导出",
                    )
                except OSError:
                    pass
            except (TrainerDataError, OSError) as error:
                messagebox.showerror("导出失败", str(error), parent=dialog)
                self.status_var.set(str(error))
                return

            refresh_lists()
            self.status_var.set(f"已把快照“{selected_snapshot.snapshot_name}”导出为预设：{destination}")

        def rename_selected_snapshot() -> None:
            selected_items = get_selected_snapshots(min_count=1, max_count=1)
            if not selected_items:
                return
            if self._rename_snapshot(selected_items[0], parent=dialog) is not None:
                refresh_lists()

        def edit_selected_snapshot_notes() -> None:
            selected_items = get_selected_snapshots(min_count=1)
            if not selected_items:
                return
            if self._batch_edit_snapshot_note(selected_items, parent=dialog):
                refresh_lists()

        def edit_selected_snapshot_categories() -> None:
            selected_items = get_selected_snapshots(min_count=1)
            if not selected_items:
                return
            if self._batch_edit_snapshot_category(selected_items, parent=dialog):
                refresh_lists()

        def toggle_selected_snapshot_favorite() -> None:
            selected_items = get_selected_snapshots(min_count=1)
            if not selected_items:
                return
            if self._toggle_snapshot_favorite(selected_items, parent=dialog):
                refresh_lists()

        def delete_selected_snapshots() -> None:
            selected_items = get_selected_snapshots(min_count=1)
            if not selected_items:
                return
            if self._delete_snapshots(selected_items, parent=dialog):
                refresh_lists()

        def save_snapshot_and_refresh() -> None:
            snapshot_path = self._save_snapshot()
            if snapshot_path is not None:
                refresh_lists()

        snapshot_search_var.trace_add("write", lambda *_args: refresh_snapshot_list())
        snapshot_filter_var.trace_add("write", lambda *_args: refresh_snapshot_list())
        snapshot_category_var.trace_add("write", lambda *_args: refresh_snapshot_list())
        snapshot_sort_var.trace_add("write", lambda *_args: refresh_snapshot_list())

        ttk.Button(preset_action_frame, text="套用选中", command=apply_selected_preset).grid(row=0, column=0)
        ttk.Button(preset_action_frame, text="移除记录", command=remove_selected_recent_preset).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(preset_action_frame, text="清理失效", command=cleanup_recent_presets).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(preset_action_frame, text="清空列表", command=clear_all_recent_presets).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(preset_action_frame, text="刷新列表", command=refresh_lists).grid(row=0, column=4, padx=(8, 0))

        ttk.Button(snapshot_action_frame, text="保存当前快照", command=save_snapshot_and_refresh).grid(row=0, column=0)
        ttk.Button(snapshot_action_frame, text="收藏/取消收藏", command=toggle_selected_snapshot_favorite).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="设置分类", command=edit_selected_snapshot_categories).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="批量备注", command=edit_selected_snapshot_notes).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(snapshot_action_frame, text="对比当前", command=compare_selected_snapshot).grid(row=0, column=4, padx=(8, 0))

        ttk.Button(snapshot_action_frame, text="比较两个快照", command=compare_two_snapshots).grid(row=1, column=0, pady=(8, 0))
        ttk.Button(snapshot_action_frame, text="套用选中快照", command=apply_selected_snapshot).grid(row=1, column=1, padx=(8, 0), pady=(8, 0))
        ttk.Button(snapshot_action_frame, text="复制快照", command=duplicate_selected_snapshots).grid(row=1, column=2, padx=(8, 0), pady=(8, 0))
        ttk.Button(snapshot_action_frame, text="导出成预设", command=export_selected_snapshot_as_preset).grid(row=1, column=3, padx=(8, 0), pady=(8, 0))
        ttk.Button(snapshot_action_frame, text="重命名快照", command=rename_selected_snapshot).grid(row=1, column=4, padx=(8, 0), pady=(8, 0))

        ttk.Button(snapshot_action_frame, text="删除快照", command=delete_selected_snapshots).grid(row=2, column=0, pady=(8, 0))
        ttk.Button(snapshot_action_frame, text="刷新列表", command=refresh_lists).grid(row=2, column=1, padx=(8, 0), pady=(8, 0))

        preset_listbox.bind("<Double-Button-1>", lambda _event: apply_selected_preset())
        snapshot_listbox.bind("<Double-Button-1>", lambda _event: compare_selected_snapshot())
        search_entry.focus_set()
        refresh_lists()

    def _open_batch_apply_dialog(self) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        profile_names = [path.name for path in self.repository.list_profiles()]
        dialog = tk.Toplevel(self)
        dialog.title("批量应用到多个模板")
        dialog.geometry("520x520")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        ttk.Label(
            dialog,
            text="选择要套用当前数值的模板。保存前会为每个模板分别创建备份。",
            justify="left",
            padding=(12, 12, 12, 0),
        ).grid(row=0, column=0, sticky="ew")

        list_frame = ttk.Frame(dialog, padding=12)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=scrollbar.set)

        for profile_name in profile_names:
            listbox.insert(tk.END, profile_name)

        try:
            current_index = profile_names.index(self.loaded_profile.profile_path.name)
            listbox.selection_set(current_index)
            listbox.see(current_index)
        except ValueError:
            pass

        action_frame = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        action_frame.grid(row=2, column=0, sticky="ew")
        ttk.Button(action_frame, text="全选", command=lambda: listbox.selection_set(0, tk.END)).grid(row=0, column=0)
        ttk.Button(action_frame, text="清空", command=lambda: listbox.selection_clear(0, tk.END)).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(action_frame, text="取消", command=dialog.destroy).grid(row=0, column=2, padx=(16, 0))
        ttk.Button(
            action_frame,
            text="应用当前数值",
            command=lambda: self._apply_batch_selection(dialog, listbox, profile_names),
        ).grid(row=0, column=3, padx=(8, 0))

    def _apply_batch_selection(self, dialog: tk.Toplevel, listbox: tk.Listbox, profile_names: list[str]) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        selected_indices = listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("未选择模板", "请至少选择一个模板。", parent=dialog)
            return

        selected_profiles = [profile_names[index] for index in selected_indices]
        try:
            values = self._collect_values()
            backup_paths = self.repository.save_profiles(selected_profiles, values)
        except TrainerDataError as error:
            messagebox.showerror("批量应用失败", str(error), parent=dialog)
            self.status_var.set(str(error))
            return

        dialog.destroy()
        self.status_var.set(
            f"已批量应用到 {len(selected_profiles)} 个模板，最后一个备份位于 {list(backup_paths.values())[-1]}。"
        )
        self._load_selected_profile()

    def _reset_unsaved_changes(self) -> None:
        if self.loaded_profile is None:
            return

        changed_keys = self._get_changed_keys()
        if not changed_keys:
            self.status_var.set("当前没有未保存改动。")
            return

        confirmed = messagebox.askyesno(
            "撤销未保存修改",
            f"确定要撤销当前 {len(changed_keys)} 项未保存改动吗？",
        )
        if not confirmed:
            return

        for key in changed_keys:
            self._reset_field(key)

        self.status_var.set(f"已撤销 {len(changed_keys)} 项未保存改动。")
        self._refresh_change_summary()

    def _restore_profile(self) -> None:
        if self.repository is None or self.loaded_profile is None:
            return

        try:
            backup_path = self.repository.restore_latest_backup(self.loaded_profile.profile_path.name)
        except TrainerDataError as error:
            messagebox.showerror("恢复失败", str(error))
            self.status_var.set(str(error))
            return

        self.status_var.set(f"已恢复最近备份: {backup_path}.")
        self._load_selected_profile()


def main() -> None:
    app = SoulmaskTrainerApp()
    app.mainloop()
