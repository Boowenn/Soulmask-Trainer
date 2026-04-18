from __future__ import annotations

from dataclasses import dataclass
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Any

from soulmask_trainer.data import LoadedProfile, SettingMeta, TrainerDataError, TrainerRepository


@dataclass
class FieldState:
    meta: SettingMeta
    variable: tk.Variable
    original_value: Any
    row: ttk.Frame


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
        self.status_var = tk.StringVar(value="等待加载 GameplaySettings 目录。")
        self.summary_var = tk.StringVar(value="未加载配置文件。")

        self.profile_combo: ttk.Combobox | None = None
        self.field_container: ScrollableFrame | None = None

        self._build_layout()
        self._try_autoload()

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

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
        ttk.Button(toolbar, text="保存", command=self._save_profile).grid(row=1, column=3, pady=(10, 0), padx=(0, 8))
        ttk.Button(toolbar, text="恢复最近备份", command=self._restore_profile).grid(row=1, column=4, pady=(10, 0))

        content = ttk.Notebook(self)
        content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        editor_tab = ttk.Frame(content, padding=12)
        editor_tab.columnconfigure(0, weight=1)
        editor_tab.rowconfigure(2, weight=1)
        content.add(editor_tab, text="全部参数")

        ttk.Label(editor_tab, textvariable=self.summary_var, justify="left").grid(row=0, column=0, sticky="ew")

        search_frame = ttk.Frame(editor_tab)
        search_frame.grid(row=1, column=0, sticky="ew", pady=(12, 12))
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="搜索").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        search_entry.bind("<KeyRelease>", lambda _event: self._apply_filter())
        ttk.Button(search_frame, text="清空", command=self._clear_search).grid(row=0, column=2)

        self.field_container = ScrollableFrame(editor_tab)
        self.field_container.grid(row=2, column=0, sticky="nsew")

        status_bar = ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(12, 6))
        status_bar.grid(row=2, column=0, sticky="ew")

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

    def _clear_fields(self) -> None:
        self.field_states.clear()
        if self.field_container is None:
            return
        for child in self.field_container.inner.winfo_children():
            child.destroy()

    def _build_fields(self, loaded_profile: LoadedProfile) -> None:
        if self.field_container is None:
            return

        self._clear_fields()
        ordered_items = sorted(
            (
                (key, meta)
                for key, meta in loaded_profile.metadata.items()
                if meta.is_visible
            ),
            key=lambda item: (item[1].label.lower(), item[0].lower()),
        )

        for row_index, (key, meta) in enumerate(ordered_items):
            current_value = loaded_profile.values.get(key, meta.default_value)
            row = ttk.Frame(self.field_container.inner, padding=(4, 4))
            row.grid(row=row_index, column=0, sticky="ew")
            row.columnconfigure(1, weight=1)

            label = ttk.Label(row, text=meta.label, width=28)
            label.grid(row=0, column=0, sticky="w", padx=(0, 8))

            detail_text = f"{key} | 范围: {self._format_range(meta)}"
            ttk.Label(row, text=detail_text, foreground="#666666").grid(
                row=1,
                column=0,
                columnspan=3,
                sticky="w",
                padx=(0, 8),
            )

            if meta.is_toggle:
                variable: tk.Variable = tk.BooleanVar(value=bool(current_value))
                widget = ttk.Checkbutton(row, variable=variable)
                widget.grid(row=0, column=1, sticky="w")
            else:
                variable = tk.StringVar(value=self._format_value(current_value))
                widget = ttk.Entry(row, textvariable=variable, width=18)
                widget.grid(row=0, column=1, sticky="w")

            ttk.Button(
                row,
                text="还原",
                command=lambda item_key=key: self._reset_field(item_key),
            ).grid(row=0, column=2, padx=(8, 0))

            self.field_states[key] = FieldState(
                meta=meta,
                variable=variable,
                original_value=current_value,
                row=row,
            )

        self._apply_filter()

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

    def _reset_field(self, key: str) -> None:
        state = self.field_states[key]
        if state.meta.is_toggle:
            state.variable.set(bool(state.original_value))
        else:
            state.variable.set(self._format_value(state.original_value))

    def _clear_search(self) -> None:
        self.search_var.set("")
        self._apply_filter()

    def _apply_filter(self) -> None:
        keyword = self.search_var.get().strip().lower()
        for key, state in self.field_states.items():
            haystack = f"{key} {state.meta.label}".lower()
            if not keyword or keyword in haystack:
                state.row.grid()
            else:
                state.row.grid_remove()

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
