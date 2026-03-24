import os
import glob
import csv
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from nptdms import TdmsFile

from processor.automatic_signal_processor import AutomaticSignalProcessor


class TDMSGuiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TDMS Signal Analyzer")
        self.root.geometry("1500x940")

        self.source_path = None
        self.available_paths = []
        self.channels_by_group = {}

        self.processor_map = {}
        self.state_map = {}

        self.current_group = None
        self.current_channel = None
        self.current_file = None

        self.selection_start = None
        self.selection_end = None
        self.span_selector = None

        self.default_params = {
            'window_time': 0.1,
            'noise_tolerance': 10.0,
            'cutoff_freq': 50.0,
            'filter_order': 5,
            'trigger_threshold': 5.0,
            'margin_fraction': 0.1,
            'min_gap_sec': 1.0,
            'min_cut_time_sec': 0.4,
            'expansion_time_sec': 0.3,
        }

        self._build_ui()

    # ----------------------------- UI -----------------------------
    def _build_ui(self):
        self.main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        self.controls_container = ttk.Frame(self.main_pane)
        self.controls_canvas = tk.Canvas(self.controls_container, highlightthickness=0)
        self.controls_scrollbar = ttk.Scrollbar(self.controls_container, orient=tk.VERTICAL, command=self.controls_canvas.yview)
        self.controls_canvas.configure(yscrollcommand=self.controls_scrollbar.set)

        self.controls_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.controls_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.controls_frame = ttk.Frame(self.controls_canvas, padding=10)
        self.controls_window = self.controls_canvas.create_window((0, 0), window=self.controls_frame, anchor='nw')

        self.controls_frame.bind('<Configure>', self._on_controls_frame_configure)
        self.controls_canvas.bind('<Configure>', self._on_controls_canvas_configure)
        self.controls_canvas.bind_all('<MouseWheel>', self._on_mouse_wheel)

        self.plot_frame = ttk.Frame(self.main_pane, padding=10)

        self.main_pane.add(self.controls_container, weight=1)
        self.main_pane.add(self.plot_frame, weight=3)

        self._build_controls()
        self._build_plot()

    def _build_controls(self):
        # 1) Load
        source_group = ttk.LabelFrame(self.controls_frame, text="1) Load Data", padding=8)
        source_group.pack(fill=tk.X, pady=4)

        self.path_var = tk.StringVar()
        self.group_var = tk.StringVar(value="")
        self.channel_var = tk.StringVar(value="")
        self.active_file_var = tk.StringVar(value="")

        ttk.Label(source_group, text="TDMS file/folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(source_group, textvariable=self.path_var, width=36, state="readonly").grid(row=1, column=0, sticky="ew", padx=(0, 4))

        btns = ttk.Frame(source_group)
        btns.grid(row=1, column=1, sticky="e")
        ttk.Button(btns, text="File", command=self._browse_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Folder", command=self._browse_folder).pack(side=tk.LEFT, padx=2)

        source_group.columnconfigure(0, weight=1)

        # 2) View + Adjust (merged)
        merged_group = ttk.LabelFrame(self.controls_frame, text="2) View + Adjust", padding=8)
        merged_group.pack(fill=tk.BOTH, expand=True, pady=4)

        merged_group.columnconfigure(0, weight=1)

        ttk.Label(merged_group, text="Group").grid(row=0, column=0, sticky="w")
        self.group_combo = ttk.Combobox(merged_group, textvariable=self.group_var, state="readonly")
        self.group_combo.grid(row=1, column=0, sticky="ew")
        self.group_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_group_changed())

        ttk.Label(merged_group, text="Channel").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.channel_combo = ttk.Combobox(merged_group, textvariable=self.channel_var, state="readonly")
        self.channel_combo.grid(row=3, column=0, sticky="ew")
        self.channel_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_channel_changed())

        ttk.Label(merged_group, text="Active file for region tool").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.active_file_combo = ttk.Combobox(merged_group, textvariable=self.active_file_var, state="readonly")
        self.active_file_combo.grid(row=5, column=0, sticky="ew")
        self.active_file_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_active_file_changed())

        ttk.Label(merged_group, text="Files to view and adjust").grid(row=6, column=0, sticky="w", pady=(6, 0))
        files_frame = ttk.Frame(merged_group)
        files_frame.grid(row=7, column=0, sticky="nsew")
        merged_group.rowconfigure(7, weight=1)

        self.view_files_listbox = tk.Listbox(files_frame, selectmode=tk.EXTENDED, height=8, exportselection=False)
        self.view_files_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.view_files_listbox.bind('<<ListboxSelect>>', lambda _e: self._on_view_files_changed())

        list_scroll = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.view_files_listbox.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.view_files_listbox.configure(yscrollcommand=list_scroll.set)

        file_btns = ttk.Frame(merged_group)
        file_btns.grid(row=8, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(file_btns, text="Select All Files", command=self._select_all_view_files).pack(side=tk.LEFT)
        ttk.Button(file_btns, text="Clear Selection", command=self._clear_view_files_selection).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(merged_group, text="Display signals").grid(row=9, column=0, sticky="w", pady=(8, 0))
        self.show_raw_var = tk.BooleanVar(value=True)
        self.show_corrected_var = tk.BooleanVar(value=True)
        self.show_filtered_var = tk.BooleanVar(value=True)
        self.show_trigger_region_var = tk.BooleanVar(value=True)
        self.show_steady_region_var = tk.BooleanVar(value=True)
        self.show_corr_windows_var = tk.BooleanVar(value=True)
        self.show_manual_region_var = tk.BooleanVar(value=True)
        self.show_auto_mean_var = tk.BooleanVar(value=True)
        self.show_manual_mean_var = tk.BooleanVar(value=True)

        display_opts = ttk.Frame(merged_group)
        display_opts.grid(row=10, column=0, sticky="w")
        ttk.Checkbutton(display_opts, text="raw", variable=self.show_raw_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(display_opts, text="corrected", variable=self.show_corrected_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(display_opts, text="filtered", variable=self.show_filtered_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))

        display_overlays = ttk.Frame(merged_group)
        display_overlays.grid(row=11, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(display_overlays, text="trigger region", variable=self.show_trigger_region_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(display_overlays, text="steady region", variable=self.show_steady_region_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(display_overlays, text="correction windows", variable=self.show_corr_windows_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))

        display_means = ttk.Frame(merged_group)
        display_means.grid(row=12, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(display_means, text="manual region", variable=self.show_manual_region_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(display_means, text="auto mean", variable=self.show_auto_mean_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(display_means, text="manual mean", variable=self.show_manual_mean_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))

        # Adjustable parameters used for viewed files
        self.window_time_var = tk.StringVar(value=str(self.default_params['window_time']))
        self.noise_tol_var = tk.StringVar(value=str(self.default_params['noise_tolerance']))
        self.cutoff_var = tk.StringVar(value=str(self.default_params['cutoff_freq']))
        self.order_var = tk.StringVar(value=str(self.default_params['filter_order']))
        self.trigger_var = tk.StringVar(value=str(self.default_params['trigger_threshold']))
        self.margin_var = tk.StringVar(value=str(self.default_params['margin_fraction']))
        self.min_gap_var = tk.StringVar(value=str(self.default_params['min_gap_sec']))
        self.min_cut_var = tk.StringVar(value=str(self.default_params['min_cut_time_sec']))
        self.expand_var = tk.StringVar(value=str(self.default_params['expansion_time_sec']))

        params_frame = ttk.Frame(merged_group)
        params_frame.grid(row=13, column=0, sticky="ew", pady=(8, 0))

        ttk.Label(params_frame, text="Window(s)").grid(row=0, column=0, sticky="w")
        ttk.Entry(params_frame, textvariable=self.window_time_var, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(params_frame, text="Noise tol").grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Entry(params_frame, textvariable=self.noise_tol_var, width=8).grid(row=0, column=3, sticky="w")

        ttk.Label(params_frame, text="Cutoff(Hz)").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(params_frame, textvariable=self.cutoff_var, width=8).grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Label(params_frame, text="Order").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(4, 0))
        ttk.Entry(params_frame, textvariable=self.order_var, width=8).grid(row=1, column=3, sticky="w", pady=(4, 0))

        ttk.Label(params_frame, text="Trigger").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(params_frame, textvariable=self.trigger_var, width=8).grid(row=2, column=1, sticky="w", pady=(4, 0))
        ttk.Label(params_frame, text="Margin").grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(4, 0))
        ttk.Entry(params_frame, textvariable=self.margin_var, width=8).grid(row=2, column=3, sticky="w", pady=(4, 0))

        ttk.Label(params_frame, text="Min gap(s)").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(params_frame, textvariable=self.min_gap_var, width=8).grid(row=3, column=1, sticky="w", pady=(4, 0))
        ttk.Label(params_frame, text="Min cut(s)").grid(row=3, column=2, sticky="w", padx=(8, 0), pady=(4, 0))
        ttk.Entry(params_frame, textvariable=self.min_cut_var, width=8).grid(row=3, column=3, sticky="w", pady=(4, 0))

        ttk.Label(params_frame, text="Expand(s)").grid(row=4, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(params_frame, textvariable=self.expand_var, width=8).grid(row=4, column=1, sticky="w", pady=(4, 0))

        ttk.Button(merged_group, text="Apply Parameters To Viewed Files", command=self._apply_params_to_viewed_files).grid(
            row=14, column=0, sticky="ew", pady=(8, 0)
        )

        # 3) Region selection
        select_group = ttk.LabelFrame(self.controls_frame, text="3) Region Selection", padding=8)
        select_group.pack(fill=tk.X, pady=4)

        ttk.Label(select_group, text="Drag in plot (single-file view) or enter range").grid(row=0, column=0, columnspan=3, sticky="w")

        self.sel_start_var = tk.StringVar(value="")
        self.sel_end_var = tk.StringVar(value="")

        ttk.Label(select_group, text="Start (s)").grid(row=1, column=0, sticky="w")
        ttk.Entry(select_group, textvariable=self.sel_start_var, width=10).grid(row=1, column=1, sticky="w")

        ttk.Label(select_group, text="End (s)").grid(row=2, column=0, sticky="w")
        ttk.Entry(select_group, textvariable=self.sel_end_var, width=10).grid(row=2, column=1, sticky="w")

        ttk.Button(select_group, text="Use Entry Range", command=self._apply_entry_range).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 6))
        tk.Button(
            select_group,
            text="Manual Mean Force (Active File)",
            command=self._manual_compute_force,
            bg="#1f6aa5",
            fg="white",
            activebackground="#2b7bbb",
            activeforeground="white",
            relief=tk.RAISED,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0), ipady=2)
        ttk.Button(select_group, text="Zero Selected Region", command=self._zero_selected_region).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(select_group, text="Remove Selected Region", command=self._remove_selected_region).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(select_group, text="Keep Only Selected Region", command=self._keep_only_selected_region).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # 4) Export and output
        out_group = ttk.LabelFrame(self.controls_frame, text="4) Export + Output", padding=8)
        out_group.pack(fill=tk.BOTH, expand=True, pady=4)

        ttk.Button(out_group, text="Export Mean Forces CSV", command=self._export_force_csv).pack(fill=tk.X)

        self.log_text = ScrolledText(out_group, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

    def _build_plot(self):
        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame)
        toolbar.update()

    # ----------------------------- SCROLL -----------------------------
    def _on_controls_frame_configure(self, _event):
        self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox('all'))

    def _on_controls_canvas_configure(self, event):
        self.controls_canvas.itemconfig(self.controls_window, width=event.width)

    def _on_mouse_wheel(self, event):
        try:
            self.controls_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        except Exception:
            pass

    # ----------------------------- KEYS/STATE -----------------------------
    def _channel_key(self, group_name, channel_name):
        return (group_name, channel_name)

    def _state_key(self, group_name, channel_name, file_name):
        return (group_name, channel_name, file_name)

    def _ensure_state(self, group_name, channel_name, file_name, file_data):
        key = self._state_key(group_name, channel_name, file_name)
        if key not in self.state_map:
            self.state_map[key] = {
                'group': group_name,
                'channel': channel_name,
                'file': file_name,
                'fs': file_data['fs'],
                'ts': file_data['ts'],
                'raw': file_data['raw'].copy(),
                't_full': file_data['t_full'].copy(),

                # Adjustable params
                'window_time': self.default_params['window_time'],
                'noise_tolerance': self.default_params['noise_tolerance'],
                'cutoff_freq': self.default_params['cutoff_freq'],
                'filter_order': self.default_params['filter_order'],
                'trigger_threshold': self.default_params['trigger_threshold'],
                'margin_fraction': self.default_params['margin_fraction'],
                'min_gap_sec': self.default_params['min_gap_sec'],
                'min_cut_time_sec': self.default_params['min_cut_time_sec'],
                'expansion_time_sec': self.default_params['expansion_time_sec'],

                # Regions and results
                'tri_start_time': None,
                'tri_end_time': None,
                'steady_start_time': None,
                'steady_end_time': None,
                'expanded_start_time': None,
                'expanded_end_time': None,
                'corr_left_start_time': None,
                'corr_left_end_time': None,
                'corr_right_start_time': None,
                'corr_right_end_time': None,
                'mean_force_auto': None,
                'manual_start_time': None,
                'manual_end_time': None,
                'mean_force_manual': None,

                'corrected': None,
                'filtered': None,
                'last_error': None,
            }
        return self.state_map[key]

    def _get_active_processor(self):
        if not self.current_group or not self.current_channel:
            return None
        return self.processor_map.get(self._channel_key(self.current_group, self.current_channel))

    def _get_active_state(self):
        if not self.current_group or not self.current_channel or not self.current_file:
            return None
        return self.state_map.get(self._state_key(self.current_group, self.current_channel, self.current_file))

    def _channel_files(self, group_name, channel_name):
        proc = self.processor_map.get(self._channel_key(group_name, channel_name))
        if not proc:
            return []
        return sorted(proc.data.keys())

    def _load_ui_from_active_state(self):
        state = self._get_active_state()
        if state is None:
            return

        self.window_time_var.set(str(state['window_time']))
        self.noise_tol_var.set(str(state['noise_tolerance']))
        self.cutoff_var.set(str(state['cutoff_freq']))
        self.order_var.set(str(int(state['filter_order'])))
        self.trigger_var.set(str(state['trigger_threshold']))
        self.margin_var.set(str(state['margin_fraction']))
        self.min_gap_var.set(str(state['min_gap_sec']))
        self.min_cut_var.set(str(state['min_cut_time_sec']))
        self.expand_var.set(str(state['expansion_time_sec']))

        self.selection_start = state['manual_start_time']
        self.selection_end = state['manual_end_time']
        self.sel_start_var.set("" if state['manual_start_time'] is None else f"{state['manual_start_time']:.6f}")
        self.sel_end_var.set("" if state['manual_end_time'] is None else f"{state['manual_end_time']:.6f}")

    def _save_ui_to_states(self, file_names, include_manual=False):
        if not self.current_group or not self.current_channel:
            return

        window_time = float(self.window_time_var.get())
        noise_tolerance = float(self.noise_tol_var.get())
        cutoff_freq = float(self.cutoff_var.get())
        filter_order = int(self.order_var.get())
        trigger_threshold = float(self.trigger_var.get())
        margin_fraction = float(self.margin_var.get())
        min_gap_sec = float(self.min_gap_var.get())
        min_cut_time_sec = float(self.min_cut_var.get())
        expansion_time_sec = float(self.expand_var.get())

        for file_name in file_names:
            key = self._state_key(self.current_group, self.current_channel, file_name)
            state = self.state_map.get(key)
            if state is None:
                continue

            state['window_time'] = window_time
            state['noise_tolerance'] = noise_tolerance
            state['cutoff_freq'] = cutoff_freq
            state['filter_order'] = filter_order
            state['trigger_threshold'] = trigger_threshold
            state['margin_fraction'] = margin_fraction
            state['min_gap_sec'] = min_gap_sec
            state['min_cut_time_sec'] = min_cut_time_sec
            state['expansion_time_sec'] = expansion_time_sec
            if include_manual:
                state['manual_start_time'] = self.selection_start
                state['manual_end_time'] = self.selection_end

    # ----------------------------- LOAD DATA -----------------------------
    def _browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("TDMS files", "*.tdms"), ("All files", "*.*")])
        if path:
            self._set_source_path(path)

    def _browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self._set_source_path(path)

    def _resolve_tdms_paths(self, path):
        if os.path.isfile(path):
            return [path]
        if os.path.isdir(path):
            return sorted(glob.glob(os.path.join(path, "*.tdms")))
        return []

    def _discover_metadata(self, tdms_paths):
        groups = set()
        channels_by_group = {}

        for fp in tdms_paths:
            tdms = TdmsFile.read(fp)
            for grp in tdms.groups():
                gname = grp.name
                groups.add(gname)
                channels_by_group.setdefault(gname, set())
                for ch in grp.channels():
                    channels_by_group[gname].add(ch.name)

        return sorted(list(groups)), {g: sorted(list(v)) for g, v in channels_by_group.items()}

    def _set_source_path(self, path):
        self.source_path = path
        self.path_var.set(path)

        self.processor_map = {}
        self.state_map = {}
        self.selection_start = None
        self.selection_end = None

        tdms_paths = self._resolve_tdms_paths(path)
        if not tdms_paths:
            messagebox.showwarning("No files", "No TDMS files found in selected location.")
            return

        self.available_paths = tdms_paths

        try:
            groups, channels_by_group = self._discover_metadata(tdms_paths)
            self.channels_by_group = channels_by_group

            loaded = 0
            failed = 0
            for group_name in groups:
                for channel_name in channels_by_group.get(group_name, []):
                    try:
                        proc = AutomaticSignalProcessor(path=path, group_name=group_name, channel_name=channel_name)
                        self.processor_map[self._channel_key(group_name, channel_name)] = proc
                        for fname, fdata in proc.data.items():
                            self._ensure_state(group_name, channel_name, fname, fdata)
                        loaded += 1
                    except Exception as exc:
                        failed += 1
                        self._log(f"Skip {group_name}/{channel_name}: {exc}")

            self._log("Running automatic detection/process for all channels and files...")
            self._auto_process_all_channels()

            self.group_combo['values'] = groups
            if groups:
                self.group_var.set(groups[0])
                self.current_group = groups[0]
                self._on_group_changed()

            self._log(f"Loaded source: {path}")
            self._log(f"Files={len(tdms_paths)} groups={len(groups)} streams loaded={loaded} failed={failed}")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))

    def _auto_process_all_channels(self):
        for (group_name, channel_name), proc in self.processor_map.items():
            files = sorted(proc.data.keys())
            self._process_files(group_name, channel_name, files)

    # ----------------------------- NAVIGATION -----------------------------
    def _on_group_changed(self):
        self.current_group = self.group_var.get().strip() or None
        channels = self.channels_by_group.get(self.current_group, []) if self.current_group else []
        self.channel_combo['values'] = channels

        if channels:
            self.channel_var.set(channels[0])
            self._on_channel_changed()
        else:
            self.channel_var.set("")
            self.current_channel = None
            self.refresh_plot()

    def _on_channel_changed(self):
        self.current_channel = self.channel_var.get().strip() or None
        if not self.current_group or not self.current_channel:
            self.refresh_plot()
            return

        files = self._channel_files(self.current_group, self.current_channel)

        self.active_file_combo['values'] = files
        if files:
            self.current_file = files[0]
            self.active_file_var.set(files[0])
        else:
            self.current_file = None
            self.active_file_var.set("")

        self.view_files_listbox.delete(0, tk.END)
        for fname in files:
            self.view_files_listbox.insert(tk.END, fname)

        if files:
            self.view_files_listbox.selection_set(0)

        self._load_ui_from_active_state()
        self.refresh_plot()

    def _on_active_file_changed(self):
        self.current_file = self.active_file_var.get().strip() or None
        self._load_ui_from_active_state()
        self.refresh_plot()

    def _on_view_files_changed(self):
        sel = self._get_view_files()
        if sel:
            # Keep the first viewed file as active if active file is outside selection
            if self.current_file not in sel:
                self.current_file = sel[0]
                self.active_file_var.set(sel[0])
                self._load_ui_from_active_state()
        self.refresh_plot()

    def _select_all_view_files(self):
        count = self.view_files_listbox.size()
        if count == 0:
            return
        self.view_files_listbox.selection_set(0, count - 1)
        self._on_view_files_changed()

    def _clear_view_files_selection(self):
        self.view_files_listbox.selection_clear(0, tk.END)
        self.refresh_plot()

    def _get_view_files(self):
        idxs = list(self.view_files_listbox.curselection())
        if idxs:
            return [self.view_files_listbox.get(i) for i in idxs]
        if self.current_file:
            return [self.current_file]
        return []

    # ----------------------------- PROCESSING -----------------------------
    def _process_files(self, group_name, channel_name, file_names):
        proc = self.processor_map.get(self._channel_key(group_name, channel_name))
        if proc is None:
            return

        for fname in file_names:
            key = self._state_key(group_name, channel_name, fname)
            state = self.state_map.get(key)
            if state is None:
                continue

            try:
                proc.detect_cutting_intervals_on_raw(
                    trigger_threshold=state['trigger_threshold'],
                    margin_fraction=state['margin_fraction'],
                    min_gap_sec=state['min_gap_sec'],
                    min_cut_time_sec=state['min_cut_time_sec'],
                    expansion_time_sec=state['expansion_time_sec'],
                    correction_window_time=state['window_time'],
                    target_files=[fname],
                )

                proc.drift_offset_correction(
                    window_time=state['window_time'],
                    noise_tolerance=state['noise_tolerance'],
                    target_files=[fname],
                    use_detected_regions=True,
                )

                proc.apply_lowpass_filter(
                    cutoff_freq=state['cutoff_freq'],
                    order=state['filter_order'],
                    target_files=[fname],
                )

                proc.compute_average_cutting_force(
                    use_filtered=True,
                    target_files=[fname],
                    prefer_existing_interval=True,
                )

                fdata = proc.data[fname]
                state['corrected'] = fdata.get('corrected').copy() if 'corrected' in fdata else None
                state['filtered'] = fdata.get('filtered').copy() if 'filtered' in fdata else None

                state['tri_start_time'] = fdata.get('tri_start_time')
                state['tri_end_time'] = fdata.get('tri_end_time')
                state['steady_start_time'] = fdata.get('steady_start_time')
                state['steady_end_time'] = fdata.get('steady_end_time')
                state['expanded_start_time'] = fdata.get('expanded_start_time')
                state['expanded_end_time'] = fdata.get('expanded_end_time')
                state['corr_left_start_time'] = fdata.get('corr_left_start_time')
                state['corr_left_end_time'] = fdata.get('corr_left_end_time')
                state['corr_right_start_time'] = fdata.get('corr_right_start_time')
                state['corr_right_end_time'] = fdata.get('corr_right_end_time')
                state['mean_force_auto'] = fdata.get('mean_force')
                state['last_error'] = None
            except Exception as exc:
                state['last_error'] = str(exc)

    def _apply_params_to_viewed_files(self):
        if not self.current_group or not self.current_channel:
            return

        files = self._get_view_files()
        if not files:
            messagebox.showwarning("No files", "Select one or more files to process.")
            return

        try:
            self._save_ui_to_states(files)
            self._process_files(self.current_group, self.current_channel, files)
            self._log(f"Applied parameters and recalculated {len(files)} viewed file(s).")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Apply error", str(exc))

    # ----------------------------- REGION TOOLS -----------------------------
    def _set_span_selector(self, ax):
        if self.span_selector is not None:
            try:
                self.span_selector.set_active(False)
            except Exception:
                pass
            self.span_selector = None

        if ax is not None:
            self.span_selector = SpanSelector(
                ax,
                self._on_region_selected,
                'horizontal',
                useblit=True,
                interactive=True,
                drag_from_anywhere=True,
                props=dict(alpha=0.2, facecolor='tab:green'),
            )

    def _on_region_selected(self, xmin, xmax):
        if not self.current_file:
            return

        self.selection_start = float(min(xmin, xmax))
        self.selection_end = float(max(xmin, xmax))

        self.sel_start_var.set(f"{self.selection_start:.6f}")
        self.sel_end_var.set(f"{self.selection_end:.6f}")

        self._save_ui_to_states([self.current_file], include_manual=True)
        self._log(f"Selected region for active file [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
        self.refresh_plot()

    def _apply_entry_range(self):
        try:
            start = float(self.sel_start_var.get().strip())
            end = float(self.sel_end_var.get().strip())
            if end <= start:
                raise ValueError("End must be greater than start.")

            self.selection_start = start
            self.selection_end = end
            if self.current_file:
                self._save_ui_to_states([self.current_file], include_manual=True)
            self._log(f"Set region for active file [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Invalid range", str(exc))

    def _manual_compute_force(self):
        proc = self._get_active_processor()
        state = self._get_active_state()
        if proc is None or state is None or not self.current_file:
            return
        if self.selection_start is None or self.selection_end is None:
            return

        try:
            result = proc.compute_manual_force_in_time_span(
                self.selection_start,
                self.selection_end,
                target_files=[self.current_file],
                use_filtered=True,
            )
            value = result.get(self.current_file)
            state['manual_start_time'] = self.selection_start
            state['manual_end_time'] = self.selection_end
            state['mean_force_manual'] = value
            self._log(f"Manual mean force | {self.current_file}: {value:.4f}")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Manual force error", str(exc))

    def _zero_selected_region(self):
        proc = self._get_active_processor()
        if proc is None or not self.current_file:
            return
        if self.selection_start is None or self.selection_end is None:
            messagebox.showwarning("No selection", "Select a region first.")
            return

        try:
            proc.zero_out_time_span(self.selection_start, self.selection_end, target_files=[self.current_file])
            state = self._get_active_state()
            if state is not None and 'filtered' in proc.data[self.current_file]:
                state['filtered'] = proc.data[self.current_file]['filtered'].copy()
            self._log(f"Zeroed filtered signal in [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Zero region error", str(exc))

    def _remove_selected_region(self):
        proc = self._get_active_processor()
        if proc is None or not self.current_file:
            return
        if self.selection_start is None or self.selection_end is None:
            messagebox.showwarning("No selection", "Select a region first.")
            return

        try:
            proc.remove_time_span(self.selection_start, self.selection_end, target_files=[self.current_file])
            self._sync_state_from_processor_file(self.current_file)
            self._log(f"Removed signal span [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Remove span error", str(exc))

    def _keep_only_selected_region(self):
        proc = self._get_active_processor()
        if proc is None or not self.current_file:
            return
        if self.selection_start is None or self.selection_end is None:
            messagebox.showwarning("No selection", "Select a region first.")
            return

        try:
            proc.keep_only_time_span(self.selection_start, self.selection_end, target_files=[self.current_file])
            self._sync_state_from_processor_file(self.current_file)
            self._log(f"Kept only span [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Keep-only span error", str(exc))

    def _sync_state_from_processor_file(self, file_name):
        proc = self._get_active_processor()
        state = self._get_active_state()
        if proc is None or state is None or file_name not in proc.data:
            return

        fdata = proc.data[file_name]
        state['raw'] = fdata['raw'].copy()
        state['t_full'] = fdata['t_full'].copy()
        state['corrected'] = fdata.get('corrected').copy() if 'corrected' in fdata else None
        state['filtered'] = fdata.get('filtered').copy() if 'filtered' in fdata else None

    # ----------------------------- EXPORT -----------------------------
    def _export_force_csv(self):
        if not self.source_path:
            messagebox.showwarning("Missing source", "Load source data first.")
            return

        group_name = self.group_var.get().strip()
        if not group_name:
            messagebox.showwarning("Missing group", "Select a group before exporting.")
            return

        channels = self.channels_by_group.get(group_name, [])
        canonical = {'fx': None, 'fy': None, 'fz': None}
        for ch in channels:
            lc = ch.strip().lower()
            if lc in canonical and canonical[lc] is None:
                canonical[lc] = ch

        if not all(canonical.values()):
            messagebox.showerror("Missing channels", "Could not map Fx/Fy/Fz channels in selected group.")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('CSV files', '*.csv')],
            initialfile='mean_forces_summary.csv',
        )
        if not save_path:
            return

        files = sorted([os.path.basename(p) for p in self._resolve_tdms_paths(self.source_path)])
        rows = {f: {'fx': '', 'fy': '', 'fz': ''} for f in files}

        try:
            for axis in ('fx', 'fy', 'fz'):
                channel_name = canonical[axis]
                for fname in files:
                    key = self._state_key(group_name, channel_name, fname)
                    state = self.state_map.get(key)
                    if state is None:
                        continue

                    val = state['mean_force_manual'] if state['mean_force_manual'] is not None else state['mean_force_auto']
                    rows[fname][axis] = '' if val is None else f"{val:.4f}"

            with open(save_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['file', 'fx', 'fy', 'fz'])
                for fname in files:
                    writer.writerow([fname, rows[fname]['fx'], rows[fname]['fy'], rows[fname]['fz']])

            self._log(f"CSV exported: {save_path}")
        except Exception as exc:
            messagebox.showerror("CSV export error", str(exc))

    # ----------------------------- PLOT -----------------------------
    def _grid_shape(self, n):
        if n <= 0:
            return 1, 1
        if n <= 9:
            cols = int(math.ceil(math.sqrt(n)))
            rows = int(math.ceil(n / cols))
            return rows, cols
        cols = 3
        rows = int(math.ceil(n / cols))
        return rows, cols

    def refresh_plot(self):
        self.figure.clear()

        proc = self._get_active_processor()
        files = self._get_view_files()

        if proc is None or not files:
            ax = self.figure.add_subplot(111)
            ax.set_title("Load data, choose group/channel/files")
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            ax.grid(True, linestyle='--', alpha=0.4)
            self._set_span_selector(None)
            self.canvas.draw_idle()
            return

        rows, cols = self._grid_shape(len(files))
        axes = self.figure.subplots(rows, cols)
        if hasattr(axes, 'flatten'):
            axes = axes.flatten()
        elif not isinstance(axes, (list, tuple)):
            axes = [axes]

        for ax, fname in zip(axes, files):
            fdata = proc.data.get(fname)
            state = self.state_map.get(self._state_key(self.current_group, self.current_channel, fname))
            if fdata is None or state is None:
                ax.set_visible(False)
                continue

            t = fdata['t_full']

            plotted = False
            if self.show_raw_var.get() and 'raw' in fdata:
                ax.plot(t, fdata['raw'], color='tab:gray', linewidth=0.9, label='raw')
                plotted = True
            if self.show_corrected_var.get() and 'corrected' in fdata:
                ax.plot(t, fdata['corrected'], color='tab:orange', linewidth=0.9, label='corrected')
                plotted = True
            if self.show_filtered_var.get() and 'filtered' in fdata:
                ax.plot(t, fdata['filtered'], color='tab:blue', linewidth=0.9, label='filtered')
                plotted = True
            if not plotted and 'raw' in fdata:
                ax.plot(t, fdata['raw'], color='tab:gray', linewidth=0.9, label='raw')

            # Detection regions
            if self.show_trigger_region_var.get() and state['tri_start_time'] is not None and state['tri_end_time'] is not None:
                ax.axvspan(state['tri_start_time'], state['tri_end_time'], color='gray', alpha=0.12, label='trigger')
            if self.show_steady_region_var.get() and state['steady_start_time'] is not None and state['steady_end_time'] is not None:
                ax.axvspan(state['steady_start_time'], state['steady_end_time'], color='tab:green', alpha=0.18, label='steady')
            if self.show_corr_windows_var.get() and state['corr_left_start_time'] is not None and state['corr_left_end_time'] is not None:
                ax.axvspan(state['corr_left_start_time'], state['corr_left_end_time'], color='gold', alpha=0.18, label='corr start')
            if self.show_corr_windows_var.get() and state['corr_right_start_time'] is not None and state['corr_right_end_time'] is not None:
                ax.axvspan(state['corr_right_start_time'], state['corr_right_end_time'], color='gold', alpha=0.18, label='corr end')

            if self.show_manual_region_var.get() and state['manual_start_time'] is not None and state['manual_end_time'] is not None:
                ax.axvspan(state['manual_start_time'], state['manual_end_time'], color='tab:purple', alpha=0.16, label='manual')

            if self.show_manual_mean_var.get() and state['mean_force_manual'] is not None and state['manual_start_time'] is not None and state['manual_end_time'] is not None:
                ax.plot(
                    [state['manual_start_time'], state['manual_end_time']],
                    [state['mean_force_manual'], state['mean_force_manual']],
                    color='tab:purple',
                    linestyle='--',
                    linewidth=1.8,
                    label=f"manual mean: {state['mean_force_manual']:.2f}",
                )

            if self.show_auto_mean_var.get() and state['mean_force_auto'] is not None and state['steady_start_time'] is not None and state['steady_end_time'] is not None:
                ax.plot(
                    [state['steady_start_time'], state['steady_end_time']],
                    [state['mean_force_auto'], state['mean_force_auto']],
                    color='red',
                    linestyle='--',
                    linewidth=1.8,
                    label=f"auto mean: {state['mean_force_auto']:.2f}",
                )

            ax.set_title(fname, fontsize=9)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            ax.grid(True, linestyle='--', alpha=0.4)
            ax.legend(loc='upper right', fontsize='x-small')

        for ax in axes[len(files):]:
            ax.set_visible(False)

        # Span selector only in single-file view
        if len(files) == 1:
            self._set_span_selector(axes[0])
        else:
            self._set_span_selector(None)

        # Keep active file synced with first viewed file
        if files and self.current_file not in files:
            self.current_file = files[0]
            self.active_file_var.set(files[0])
            self._load_ui_from_active_state()

        self.figure.suptitle(
            f"Group: {self.current_group} | Channel: {self.current_channel} | Viewed files: {len(files)}",
            fontsize=11,
            fontweight='bold',
        )
        self.figure.tight_layout(rect=[0, 0.01, 1, 0.97])
        self.canvas.draw_idle()

    # ----------------------------- LOG -----------------------------
    def _log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = TDMSGuiApp(root)
    root.mainloop()
