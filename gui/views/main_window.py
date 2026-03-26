from __future__ import annotations

import math
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable, Dict, List, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector

from core.models import SignalRecord


class MainWindow:
    """Tkinter view: owns widgets and rendering only."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TDMS Reader - MVC")
        self.root.geometry("1500x920")

        self._on_path_selected: Optional[Callable[[str], None]] = None
        self._on_load_requested: Optional[Callable[[], None]] = None
        self._on_group_changed: Optional[Callable[[str], None]] = None
        self._on_channel_changed: Optional[Callable[[str], None]] = None
        self._on_files_changed: Optional[Callable[[List[str]], None]] = None
        self._on_active_file_changed: Optional[Callable[[str], None]] = None
        self._on_process_requested: Optional[Callable[[], None]] = None
        self._on_manual_force_requested: Optional[Callable[[], None]] = None
        self._on_export_requested: Optional[Callable[[], None]] = None
        self._on_span_selected: Optional[Callable[[float, float], None]] = None
        self._on_apply_range_requested: Optional[Callable[[], None]] = None
        self._on_zero_span_requested: Optional[Callable[[], None]] = None
        self._on_remove_span_requested: Optional[Callable[[], None]] = None
        self._on_keep_span_requested: Optional[Callable[[], None]] = None
        self._on_plot_options_changed: Optional[Callable[[], None]] = None

        self.path_var = tk.StringVar(value="")
        self.group_var = tk.StringVar(value="")
        self.channel_var = tk.StringVar(value="")
        self.active_file_var = tk.StringVar(value="")

        self.window_time_var = tk.StringVar(value="0.3")
        self.noise_tol_var = tk.StringVar(value="10.0")
        self.cutoff_var = tk.StringVar(value="50.0")
        self.order_var = tk.StringVar(value="5")
        self.trigger_var = tk.StringVar(value="5.0")
        self.margin_var = tk.StringVar(value="0.1")
        self.min_cut_var = tk.StringVar(value="1.0")
        self.expand_var = tk.StringVar(value="0.3")

        self.sel_start_var = tk.StringVar(value="")
        self.sel_end_var = tk.StringVar(value="")

        self.show_raw_var = tk.BooleanVar(value=True)
        self.show_corrected_var = tk.BooleanVar(value=True)
        self.show_filtered_var = tk.BooleanVar(value=True)
        self.show_trigger_region_var = tk.BooleanVar(value=True)
        self.show_steady_region_var = tk.BooleanVar(value=True)
        self.show_corr_windows_var = tk.BooleanVar(value=True)
        self.show_manual_region_var = tk.BooleanVar(value=True)
        self.show_auto_mean_var = tk.BooleanVar(value=True)
        self.show_manual_mean_var = tk.BooleanVar(value=True)

        self.span_selector: Optional[SpanSelector] = None

        self._build_ui()

    # -------- Binders --------
    def bind_path_selected(self, callback: Callable[[str], None]) -> None:
        self._on_path_selected = callback

    def bind_load_requested(self, callback: Callable[[], None]) -> None:
        self._on_load_requested = callback

    def bind_group_changed(self, callback: Callable[[str], None]) -> None:
        self._on_group_changed = callback

    def bind_channel_changed(self, callback: Callable[[str], None]) -> None:
        self._on_channel_changed = callback

    def bind_files_changed(self, callback: Callable[[List[str]], None]) -> None:
        self._on_files_changed = callback

    def bind_active_file_changed(self, callback: Callable[[str], None]) -> None:
        self._on_active_file_changed = callback

    def bind_process_requested(self, callback: Callable[[], None]) -> None:
        self._on_process_requested = callback

    def bind_manual_force_requested(self, callback: Callable[[], None]) -> None:
        self._on_manual_force_requested = callback

    def bind_export_requested(self, callback: Callable[[], None]) -> None:
        self._on_export_requested = callback

    def bind_span_selected(self, callback: Callable[[float, float], None]) -> None:
        self._on_span_selected = callback

    def bind_apply_range_requested(self, callback: Callable[[], None]) -> None:
        self._on_apply_range_requested = callback

    def bind_zero_span_requested(self, callback: Callable[[], None]) -> None:
        self._on_zero_span_requested = callback

    def bind_remove_span_requested(self, callback: Callable[[], None]) -> None:
        self._on_remove_span_requested = callback

    def bind_keep_span_requested(self, callback: Callable[[], None]) -> None:
        self._on_keep_span_requested = callback

    def bind_plot_options_changed(self, callback: Callable[[], None]) -> None:
        self._on_plot_options_changed = callback

    # -------- Public UI helpers --------
    def set_path(self, path: str) -> None:
        self.path_var.set(path)

    def set_group_options(self, groups: List[str]) -> None:
        self.group_combo["values"] = groups
        if groups:
            self.group_var.set(groups[0])
            if self._on_group_changed:
                self._on_group_changed(groups[0])
        else:
            self.group_var.set("")

    def set_channel_options(self, channels: List[str]) -> None:
        self.channel_combo["values"] = channels
        if channels:
            self.channel_var.set(channels[0])
            if self._on_channel_changed:
                self._on_channel_changed(channels[0])
        else:
            self.channel_var.set("")

    def set_file_options(self, files: List[str]) -> None:
        self.active_file_combo["values"] = files
        self.view_files_listbox.delete(0, tk.END)
        for file_name in files:
            self.view_files_listbox.insert(tk.END, file_name)

        if files:
            self.active_file_var.set(files[0])
            self.active_file_combo.current(0)
            self.select_all_files()
        else:
            self.active_file_var.set("")

    def select_all_files(self) -> None:
        if self.view_files_listbox.size() == 0:
            return
        self.view_files_listbox.selection_set(0, tk.END)
        self._emit_files_changed()

    def get_selected_files(self) -> List[str]:
        return [self.view_files_listbox.get(i) for i in self.view_files_listbox.curselection()]

    def get_active_file(self) -> Optional[str]:
        value = self.active_file_var.get().strip()
        return value or None

    def set_manual_range(self, start: Optional[float], end: Optional[float]) -> None:
        self.sel_start_var.set("" if start is None else f"{start:.6f}")
        self.sel_end_var.set("" if end is None else f"{end:.6f}")

    def get_manual_range(self) -> Tuple[float, float]:
        start = float(self.sel_start_var.get().strip())
        end = float(self.sel_end_var.get().strip())
        if end <= start:
            raise ValueError("End time must be greater than start time.")
        return start, end

    def get_processing_params(self) -> Dict[str, float | int]:
        return {
            "window_time": float(self.window_time_var.get()),
            "noise_tolerance": float(self.noise_tol_var.get()),
            "cutoff_freq": float(self.cutoff_var.get()),
            "filter_order": int(self.order_var.get()),
            "trigger_threshold": float(self.trigger_var.get()),
            "margin_fraction": float(self.margin_var.get()),
            "min_cut_time_sec": float(self.min_cut_var.get()),
            "expansion_time_sec": float(self.expand_var.get()),
        }

    def get_plot_options(self) -> Dict[str, bool]:
        return {
            "show_raw": bool(self.show_raw_var.get()),
            "show_corrected": bool(self.show_corrected_var.get()),
            "show_filtered": bool(self.show_filtered_var.get()),
            "show_trigger_region": bool(self.show_trigger_region_var.get()),
            "show_steady_region": bool(self.show_steady_region_var.get()),
            "show_corr_windows": bool(self.show_corr_windows_var.get()),
            "show_manual_region": bool(self.show_manual_region_var.get()),
            "show_auto_mean": bool(self.show_auto_mean_var.get()),
            "show_manual_mean": bool(self.show_manual_mean_var.get()),
        }

    def prompt_save_csv(self) -> str:
        return filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="mean_forces_summary.csv",
        )

    def log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def draw_records(
        self,
        records: Dict[str, SignalRecord],
        selected_files: List[str],
        active_file: Optional[str],
        selected_spans: Dict[str, Tuple[float, float]],
        title_prefix: str,
    ) -> None:
        self.figure.clear()
        plot_options = self.get_plot_options()

        if not records or not selected_files:
            ax = self.figure.add_subplot(111)
            ax.set_title("Load TDMS path, choose group/channel, then process files")
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            ax.grid(True, linestyle="--", alpha=0.4)
            self._set_span_selector(None)
            self.canvas.draw_idle()
            return

        rows, cols = self._grid_shape(len(selected_files))
        axes = self.figure.subplots(rows, cols)
        if hasattr(axes, "flatten"):
            axes = axes.flatten()
        elif not isinstance(axes, (list, tuple)):
            axes = [axes]

        for ax, file_name in zip(axes, selected_files):
            record = records.get(file_name)
            if record is None:
                ax.set_visible(False)
                continue

            if plot_options["show_raw"]:
                ax.plot(record.t_full, record.raw, color="tab:gray", linewidth=0.9, label="raw")
            if plot_options["show_corrected"] and record.corrected is not None:
                ax.plot(record.t_full, record.corrected, color="tab:orange", linewidth=0.9, label="corrected")
            if plot_options["show_filtered"] and record.filtered is not None:
                ax.plot(record.t_full, record.filtered, color="tab:blue", linewidth=0.9, label="filtered")

            if plot_options["show_trigger_region"] and record.tri_start_time is not None and record.tri_end_time is not None:
                ax.axvspan(record.tri_start_time, record.tri_end_time, color="gray", alpha=0.12, label="trigger")
            if plot_options["show_steady_region"] and record.steady_start_time is not None and record.steady_end_time is not None:
                ax.axvspan(record.steady_start_time, record.steady_end_time, color="tab:green", alpha=0.16, label="steady")
            if plot_options["show_corr_windows"] and record.corr_left_start_time is not None and record.corr_left_end_time is not None:
                ax.axvspan(record.corr_left_start_time, record.corr_left_end_time, color="gold", alpha=0.12, label="corr start")
            if plot_options["show_corr_windows"] and record.corr_right_start_time is not None and record.corr_right_end_time is not None:
                ax.axvspan(record.corr_right_start_time, record.corr_right_end_time, color="gold", alpha=0.12, label="corr end")

            span = selected_spans.get(file_name)
            if plot_options["show_manual_region"] and span is not None:
                ax.axvspan(span[0], span[1], color="tab:purple", alpha=0.12, label="manual")

            if (
                plot_options["show_auto_mean"]
                and record.mean_force_auto is not None
                and record.steady_start_time is not None
                and record.steady_end_time is not None
            ):
                ax.plot(
                    [record.steady_start_time, record.steady_end_time],
                    [record.mean_force_auto, record.mean_force_auto],
                    color="red",
                    linestyle="--",
                    linewidth=1.8,
                    label=f"auto mean: {record.mean_force_auto:.2f}",
                )

            if plot_options["show_manual_mean"] and record.mean_force_manual is not None and span is not None:
                ax.plot(
                    [span[0], span[1]],
                    [record.mean_force_manual, record.mean_force_manual],
                    color="tab:purple",
                    linestyle="--",
                    linewidth=1.8,
                    label=f"manual mean: {record.mean_force_manual:.2f}",
                )

            ax.set_title(file_name, fontsize=9)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            ax.grid(True, linestyle="--", alpha=0.4)
            ax.legend(loc="upper right", fontsize="x-small")

        for ax in axes[len(selected_files):]:
            ax.set_visible(False)

        if len(selected_files) == 1 and active_file == selected_files[0]:
            self._set_span_selector(axes[0])
        else:
            self._set_span_selector(None)

        self.figure.suptitle(title_prefix, fontsize=11, fontweight="bold")
        self.figure.tight_layout(rect=[0, 0.01, 1, 0.97])
        self.canvas.draw_idle()

    # -------- Internal UI wiring --------
    def _build_ui(self) -> None:
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main_pane)
        right = ttk.Frame(main_pane, padding=10)
        main_pane.add(left, weight=1)
        main_pane.add(right, weight=3)

        # Scrollable controls column to keep all actions accessible on smaller windows.
        controls_canvas = tk.Canvas(left, highlightthickness=0)
        controls_scrollbar = ttk.Scrollbar(left, orient=tk.VERTICAL, command=controls_canvas.yview)
        controls_canvas.configure(yscrollcommand=controls_scrollbar.set)

        controls_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        controls_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        controls_root = ttk.Frame(controls_canvas, padding=10)
        controls_window = controls_canvas.create_window((0, 0), window=controls_root, anchor="nw")

        def _sync_scroll_region(_event=None) -> None:
            controls_canvas.configure(scrollregion=controls_canvas.bbox("all"))

        def _sync_inner_width(event) -> None:
            controls_canvas.itemconfigure(controls_window, width=event.width)

        controls_root.bind("<Configure>", _sync_scroll_region)
        controls_canvas.bind("<Configure>", _sync_inner_width)

        def _on_mousewheel(event) -> None:
            controls_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        controls_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        load_group = ttk.LabelFrame(controls_root, text="1) Source", padding=8)
        load_group.pack(fill=tk.X, pady=4)

        ttk.Entry(load_group, textvariable=self.path_var, state="readonly", width=42).grid(row=0, column=0, columnspan=3, sticky="ew")
        ttk.Button(load_group, text="File", command=self._browse_file).grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(load_group, text="Folder", command=self._browse_folder).grid(row=1, column=1, sticky="ew", pady=(6, 0), padx=4)
        ttk.Button(load_group, text="Load", command=self._request_load).grid(row=1, column=2, sticky="ew", pady=(6, 0))
        load_group.columnconfigure(0, weight=1)
        load_group.columnconfigure(1, weight=1)
        load_group.columnconfigure(2, weight=1)

        channel_group = ttk.LabelFrame(controls_root, text="2) Stream Selection", padding=8)
        channel_group.pack(fill=tk.X, pady=4)

        ttk.Label(channel_group, text="Group").grid(row=0, column=0, sticky="w")
        self.group_combo = ttk.Combobox(channel_group, textvariable=self.group_var, state="readonly")
        self.group_combo.grid(row=1, column=0, sticky="ew")
        self.group_combo.bind("<<ComboboxSelected>>", lambda _e: self._emit_group_changed())

        ttk.Label(channel_group, text="Channel").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.channel_combo = ttk.Combobox(channel_group, textvariable=self.channel_var, state="readonly")
        self.channel_combo.grid(row=3, column=0, sticky="ew")
        self.channel_combo.bind("<<ComboboxSelected>>", lambda _e: self._emit_channel_changed())

        ttk.Label(channel_group, text="Active file").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.active_file_combo = ttk.Combobox(channel_group, textvariable=self.active_file_var, state="readonly")
        self.active_file_combo.grid(row=5, column=0, sticky="ew")
        self.active_file_combo.bind("<<ComboboxSelected>>", lambda _e: self._emit_active_file_changed())
        channel_group.columnconfigure(0, weight=1)

        files_group = ttk.LabelFrame(controls_root, text="3) Files", padding=8)
        files_group.pack(fill=tk.BOTH, expand=True, pady=4)
        self.view_files_listbox = tk.Listbox(files_group, selectmode=tk.EXTENDED, exportselection=False, height=9)
        self.view_files_listbox.pack(fill=tk.BOTH, expand=True)
        self.view_files_listbox.bind("<<ListboxSelect>>", lambda _e: self._emit_files_changed())
        ttk.Button(files_group, text="Select All", command=self.select_all_files).pack(fill=tk.X, pady=(6, 0))

        display_group = ttk.LabelFrame(controls_root, text="4) Display Options", padding=8)
        display_group.pack(fill=tk.X, pady=4)
        display_signals = ttk.Frame(display_group)
        display_signals.pack(fill=tk.X)
        ttk.Checkbutton(display_signals, text="raw", variable=self.show_raw_var, command=self._emit_plot_options_changed).pack(side=tk.LEFT)
        ttk.Checkbutton(display_signals, text="corrected", variable=self.show_corrected_var, command=self._emit_plot_options_changed).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(display_signals, text="filtered", variable=self.show_filtered_var, command=self._emit_plot_options_changed).pack(side=tk.LEFT, padx=(8, 0))

        display_regions = ttk.Frame(display_group)
        display_regions.pack(fill=tk.X, pady=(4, 0))
        ttk.Checkbutton(display_regions, text="trigger", variable=self.show_trigger_region_var, command=self._emit_plot_options_changed).pack(side=tk.LEFT)
        ttk.Checkbutton(display_regions, text="steady", variable=self.show_steady_region_var, command=self._emit_plot_options_changed).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(display_regions, text="corr windows", variable=self.show_corr_windows_var, command=self._emit_plot_options_changed).pack(side=tk.LEFT, padx=(8, 0))

        display_metrics = ttk.Frame(display_group)
        display_metrics.pack(fill=tk.X, pady=(4, 0))
        ttk.Checkbutton(display_metrics, text="manual region", variable=self.show_manual_region_var, command=self._emit_plot_options_changed).pack(side=tk.LEFT)
        ttk.Checkbutton(display_metrics, text="auto mean", variable=self.show_auto_mean_var, command=self._emit_plot_options_changed).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(display_metrics, text="manual mean", variable=self.show_manual_mean_var, command=self._emit_plot_options_changed).pack(side=tk.LEFT, padx=(8, 0))

        params_group = ttk.LabelFrame(controls_root, text="5) Parameters", padding=8)
        params_group.pack(fill=tk.X, pady=4)
        self._add_param_row(params_group, 0, "Window(s)", self.window_time_var)
        self._add_param_row(params_group, 1, "Noise tol", self.noise_tol_var)
        self._add_param_row(params_group, 2, "Cutoff(Hz)", self.cutoff_var)
        self._add_param_row(params_group, 3, "Order", self.order_var)
        self._add_param_row(params_group, 4, "Trigger", self.trigger_var)
        self._add_param_row(params_group, 5, "Margin", self.margin_var)
        self._add_param_row(params_group, 6, "Min cut(s)", self.min_cut_var)
        self._add_param_row(params_group, 7, "Expand(s)", self.expand_var)
        ttk.Button(params_group, text="Process Selected Files", command=self._request_process).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        manual_group = ttk.LabelFrame(controls_root, text="6) Manual Span", padding=8)
        manual_group.pack(fill=tk.X, pady=4)
        self._add_param_row(manual_group, 0, "Start (s)", self.sel_start_var)
        self._add_param_row(manual_group, 1, "End (s)", self.sel_end_var)
        ttk.Button(manual_group, text="Use Entry Range", command=self._request_apply_range).grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(manual_group, text="Manual Mean (Active File)", command=self._request_manual_force).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(manual_group, text="Zero Selected Region", command=self._request_zero_span).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(manual_group, text="Remove Selected Region", command=self._request_remove_span).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(manual_group, text="Keep Only Selected Region", command=self._request_keep_span).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        export_group = ttk.LabelFrame(controls_root, text="7) Export", padding=8)
        export_group.pack(fill=tk.X, pady=4)
        ttk.Button(export_group, text="Export Mean Forces CSV", command=self._request_export).pack(fill=tk.X)

        log_group = ttk.LabelFrame(controls_root, text="Log", padding=8)
        log_group.pack(fill=tk.BOTH, expand=True, pady=4)
        self.log_text = ScrolledText(log_group, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=right)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas, right)
        toolbar.update()

    def _add_param_row(self, parent: ttk.LabelFrame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(parent, textvariable=variable, width=12).grid(row=row, column=1, sticky="ew", pady=(0, 4), padx=(6, 0))
        parent.columnconfigure(1, weight=1)

    def _grid_shape(self, n: int) -> Tuple[int, int]:
        if n <= 0:
            return 1, 1
        if n <= 9:
            cols = int(math.ceil(math.sqrt(n)))
            rows = int(math.ceil(n / cols))
            return rows, cols
        cols = 3
        rows = int(math.ceil(n / cols))
        return rows, cols

    def _set_span_selector(self, ax) -> None:
        if self.span_selector is not None:
            try:
                self.span_selector.set_active(False)
            except Exception:
                pass
            self.span_selector = None

        if ax is not None:
            self.span_selector = SpanSelector(
                ax,
                self._emit_span_selected,
                "horizontal",
                useblit=True,
                interactive=True,
                drag_from_anywhere=True,
                props={"alpha": 0.2, "facecolor": "tab:green"},
            )

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("TDMS files", "*.tdms"), ("All files", "*.*")])
        if path and self._on_path_selected:
            self._on_path_selected(path)

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory()
        if path and self._on_path_selected:
            self._on_path_selected(path)

    def _request_load(self) -> None:
        if self._on_load_requested:
            self._on_load_requested()

    def _emit_group_changed(self) -> None:
        if self._on_group_changed:
            self._on_group_changed(self.group_var.get().strip())

    def _emit_channel_changed(self) -> None:
        if self._on_channel_changed:
            self._on_channel_changed(self.channel_var.get().strip())

    def _emit_files_changed(self) -> None:
        if self._on_files_changed:
            self._on_files_changed(self.get_selected_files())

    def _emit_active_file_changed(self) -> None:
        if self._on_active_file_changed:
            active = self.get_active_file()
            if active is not None:
                self._on_active_file_changed(active)

    def _request_process(self) -> None:
        if self._on_process_requested:
            self._on_process_requested()

    def _request_manual_force(self) -> None:
        if self._on_manual_force_requested:
            self._on_manual_force_requested()

    def _request_export(self) -> None:
        if self._on_export_requested:
            self._on_export_requested()

    def _emit_span_selected(self, xmin: float, xmax: float) -> None:
        if self._on_span_selected:
            start = float(min(xmin, xmax))
            end = float(max(xmin, xmax))
            self._on_span_selected(start, end)

    def _request_apply_range(self) -> None:
        if self._on_apply_range_requested:
            self._on_apply_range_requested()

    def _request_zero_span(self) -> None:
        if self._on_zero_span_requested:
            self._on_zero_span_requested()

    def _request_remove_span(self) -> None:
        if self._on_remove_span_requested:
            self._on_remove_span_requested()

    def _request_keep_span(self) -> None:
        if self._on_keep_span_requested:
            self._on_keep_span_requested()

    def _emit_plot_options_changed(self) -> None:
        if self._on_plot_options_changed:
            self._on_plot_options_changed()
