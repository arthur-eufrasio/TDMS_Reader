import os
import glob
import csv
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
        self.root.geometry("1450x920")

        self.source_path = None
        self.available_paths = []
        self.channels_by_group = {}

        # Loaded processors for each (group, channel)
        self.processor_map = {}

        # Comprehensive per (group, channel, file) state
        self.channel_file_state = {}
        # Channel-level flags per (group, channel)
        self.channel_state = {}

        self.default_param_template = {
            'window_time': 0.3,
            'noise_tolerance': 20.0,
            'cutoff_freq': 10.0,
            'filter_order': 5,
            'trigger_threshold': 5.0,
            'margin_fraction': 0.1,
        }

        self.current_group = None
        self.current_channel = None
        self.current_file = None

        self.selection_start = None
        self.selection_end = None
        self.span_selector = None

        self._build_ui()

    # --------------------------- UI BUILD ---------------------------
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
        # 1) Data source
        source_group = ttk.LabelFrame(self.controls_frame, text="1) Load Data", padding=8)
        source_group.pack(fill=tk.X, pady=4)

        self.path_var = tk.StringVar()
        self.group_var = tk.StringVar(value="")
        self.channel_var = tk.StringVar(value="")

        ttk.Label(source_group, text="TDMS file/folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(source_group, textvariable=self.path_var, width=36, state="readonly").grid(
            row=1, column=0, sticky="ew", padx=(0, 4)
        )

        btns = ttk.Frame(source_group)
        btns.grid(row=1, column=1, sticky="e")
        ttk.Button(btns, text="File", command=self._browse_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Folder", command=self._browse_folder).pack(side=tk.LEFT, padx=2)

        source_group.columnconfigure(0, weight=1)

        # 2) View
        view_group = ttk.LabelFrame(self.controls_frame, text="2) View Raw / Results", padding=8)
        view_group.pack(fill=tk.X, pady=4)

        ttk.Label(view_group, text="File").grid(row=0, column=0, sticky="w")
        self.file_var = tk.StringVar()
        self.file_combo = ttk.Combobox(view_group, textvariable=self.file_var, state="readonly")
        self.file_combo.grid(row=1, column=0, sticky="ew")
        self.file_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_file_changed())

        ttk.Label(view_group, text="Group").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.group_combo = ttk.Combobox(view_group, textvariable=self.group_var, state="readonly")
        self.group_combo.grid(row=3, column=0, sticky="ew")
        self.group_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_group_changed())

        ttk.Label(view_group, text="Channel").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.channel_combo = ttk.Combobox(view_group, textvariable=self.channel_var, state="readonly")
        self.channel_combo.grid(row=5, column=0, sticky="ew")
        self.channel_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_channel_changed())

        ttk.Label(view_group, text="Display signals").grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.show_raw_var = tk.BooleanVar(value=True)
        self.show_corrected_var = tk.BooleanVar(value=True)
        self.show_filtered_var = tk.BooleanVar(value=True)

        display_opts = ttk.Frame(view_group)
        display_opts.grid(row=7, column=0, sticky="w")

        self.chk_raw = ttk.Checkbutton(display_opts, text="raw", variable=self.show_raw_var, command=self.refresh_plot)
        self.chk_corrected = ttk.Checkbutton(display_opts, text="corrected", variable=self.show_corrected_var, command=self.refresh_plot)
        self.chk_filtered = ttk.Checkbutton(display_opts, text="filtered", variable=self.show_filtered_var, command=self.refresh_plot)

        self.chk_raw.pack(side=tk.LEFT, padx=(0, 8))
        # corrected and filtered appear only after automatic pipeline for the selected channel

        view_group.columnconfigure(0, weight=1)

        # 3) Processing
        proc_group = ttk.LabelFrame(self.controls_frame, text="3) Parameters + Automatic Pipeline", padding=8)
        proc_group.pack(fill=tk.BOTH, expand=True, pady=4)

        proc_group.rowconfigure(1, weight=1)
        proc_group.columnconfigure(2, weight=1)

        self.window_time_var = tk.StringVar(value="0.3")
        self.noise_tol_var = tk.StringVar(value="20.0")
        self.cutoff_var = tk.StringVar(value="10")
        self.order_var = tk.StringVar(value="5")
        self.trigger_var = tk.StringVar(value="5.0")
        self.margin_var = tk.StringVar(value="0.1")
        self.process_all_var = tk.BooleanVar(value=True)

        ttk.Label(proc_group, text="Target files for adjust").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(proc_group, text="All files", variable=self.process_all_var).grid(row=0, column=1, sticky="w")

        files_frame = ttk.Frame(proc_group)
        files_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(2, 6))
        self.process_file_listbox = tk.Listbox(files_frame, selectmode=tk.EXTENDED, height=8, exportselection=False)
        self.process_file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.process_file_listbox.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.process_file_listbox.configure(yscrollcommand=list_scroll.set)

        ttk.Label(proc_group, text="Window time (s)").grid(row=2, column=0, sticky="w")
        self.window_entry = ttk.Entry(proc_group, textvariable=self.window_time_var, width=10)
        self.window_entry.grid(row=2, column=1, sticky="w")

        ttk.Label(proc_group, text="Noise tolerance").grid(row=3, column=0, sticky="w")
        self.noise_entry = ttk.Entry(proc_group, textvariable=self.noise_tol_var, width=10)
        self.noise_entry.grid(row=3, column=1, sticky="w")

        self.btn_apply_drift = ttk.Button(proc_group, text="Apply Drift Correction (Adjust)", command=self._apply_drift)
        self.btn_apply_drift.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 6))

        ttk.Label(proc_group, text="Lowpass cutoff (Hz)").grid(row=5, column=0, sticky="w")
        self.cutoff_entry = ttk.Entry(proc_group, textvariable=self.cutoff_var, width=10)
        self.cutoff_entry.grid(row=5, column=1, sticky="w")

        ttk.Label(proc_group, text="Filter order").grid(row=6, column=0, sticky="w")
        self.order_entry = ttk.Entry(proc_group, textvariable=self.order_var, width=10)
        self.order_entry.grid(row=6, column=1, sticky="w")

        self.btn_apply_filter = ttk.Button(proc_group, text="Apply Lowpass (Adjust)", command=self._apply_filter)
        self.btn_apply_filter.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(4, 6))

        ttk.Label(proc_group, text="Trigger threshold (auto step)").grid(row=8, column=0, sticky="w")
        self.trigger_entry = ttk.Entry(proc_group, textvariable=self.trigger_var, width=10)
        self.trigger_entry.grid(row=8, column=1, sticky="w")

        ttk.Label(proc_group, text="Margin fraction (auto step)").grid(row=9, column=0, sticky="w")
        self.margin_entry = ttk.Entry(proc_group, textvariable=self.margin_var, width=10)
        self.margin_entry.grid(row=9, column=1, sticky="w")

        self.btn_auto_compute = ttk.Button(proc_group, text="Auto Compute Mean Force", command=self._auto_compute_force)
        self.btn_auto_compute.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        self.btn_pipeline = tk.Button(
            proc_group,
            text="Run Automatic Pipeline",
            command=self._run_automatic_pipeline,
            bg="#1f6aa5",
            fg="white",
            activebackground="#2b7bbb",
            activeforeground="white",
            relief=tk.RAISED,
            font=("Segoe UI", 10, "bold"),
        )
        self.btn_pipeline.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(14, 0), ipady=4)

        ttk.Button(proc_group, text="Export Mean Forces CSV", command=self._export_force_csv).grid(
            row=12, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        # 4) Region selection
        select_group = ttk.LabelFrame(self.controls_frame, text="4) Region Selection (Adjust)", padding=8)
        select_group.pack(fill=tk.X, pady=4)

        ttk.Label(select_group, text="Drag on chart to select region").grid(row=0, column=0, columnspan=3, sticky="w")

        self.sel_start_var = tk.StringVar(value="")
        self.sel_end_var = tk.StringVar(value="")

        ttk.Label(select_group, text="Start (s)").grid(row=1, column=0, sticky="w")
        ttk.Entry(select_group, textvariable=self.sel_start_var, width=10).grid(row=1, column=1, sticky="w")

        ttk.Label(select_group, text="End (s)").grid(row=2, column=0, sticky="w")
        ttk.Entry(select_group, textvariable=self.sel_end_var, width=10).grid(row=2, column=1, sticky="w")

        ttk.Button(select_group, text="Use Entry Range", command=self._apply_entry_range).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(4, 6)
        )

        ttk.Button(select_group, text="Manual Mean Force (Selected)", command=self._manual_compute_force).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )
        ttk.Button(select_group, text="Zero Selected Region", command=self._zero_selected_region).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )
        ttk.Button(select_group, text="Remove Selected Region", command=self._remove_selected_region).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )
        ttk.Button(select_group, text="Keep Only Selected Region", command=self._keep_only_selected_region).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )

        # 5) Output
        log_group = ttk.LabelFrame(self.controls_frame, text="5) Output", padding=8)
        log_group.pack(fill=tk.BOTH, expand=True, pady=4)

        self.log_text = ScrolledText(log_group, height=12)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _build_plot(self):
        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Amplitude")
        self.ax.grid(True, linestyle="--", alpha=0.4)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame)
        toolbar.update()

        self.span_selector = SpanSelector(
            self.ax,
            self._on_region_selected,
            "horizontal",
            useblit=True,
            interactive=True,
            drag_from_anywhere=True,
            props=dict(alpha=0.2, facecolor="tab:green")
        )

    # --------------------------- SCROLL HELPERS ---------------------------
    def _on_controls_frame_configure(self, _event):
        self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox('all'))

    def _on_controls_canvas_configure(self, event):
        self.controls_canvas.itemconfig(self.controls_window, width=event.width)

    def _on_mouse_wheel(self, event):
        try:
            self.controls_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        except Exception:
            pass

    # --------------------------- STATE HELPERS ---------------------------
    def _state_key(self, group_name, channel_name, file_name):
        return (group_name, channel_name, file_name)

    def _channel_key(self, group_name, channel_name):
        return (group_name, channel_name)

    def _ensure_channel_state(self, group_name, channel_name):
        key = self._channel_key(group_name, channel_name)
        if key not in self.channel_state:
            self.channel_state[key] = {
                'auto_pipeline_done': False,
                'trigger_threshold': self.default_param_template['trigger_threshold'],
                'margin_fraction': self.default_param_template['margin_fraction'],
            }
        return self.channel_state[key]

    def _ensure_file_channel_state(self, group_name, channel_name, file_name, file_data):
        key = self._state_key(group_name, channel_name, file_name)
        if key not in self.channel_file_state:
            self.channel_file_state[key] = {
                # Immutable raw load context
                'group': group_name,
                'channel': channel_name,
                'file': file_name,
                'fs': file_data['fs'],
                'ts': file_data['ts'],
                'raw': file_data['raw'].copy(),
                't_full_raw': file_data['t_full'].copy(),

                # Adjustable parameters
                'window_time': self.default_param_template['window_time'],
                'noise_tolerance': self.default_param_template['noise_tolerance'],
                'cutoff_freq': self.default_param_template['cutoff_freq'],
                'filter_order': self.default_param_template['filter_order'],

                # Auto-step parameters (channel-level defaults copied here for traceability)
                'trigger_threshold': self.default_param_template['trigger_threshold'],
                'margin_fraction': self.default_param_template['margin_fraction'],

                # Regions and computed values
                'tri_start_time': None,
                'tri_end_time': None,
                'steady_start_time': None,
                'steady_end_time': None,
                'mean_force_auto': None,
                'manual_start_time': None,
                'manual_end_time': None,
                'mean_force_manual': None,

                # Processed signals snapshots
                'corrected': None,
                'filtered': None,
                't_full_processed': None,

                # Status
                'drift_applied': False,
                'filter_applied': False,
                'auto_force_applied': False,
                'manual_force_applied': False,
                'last_error': None,
            }
        return self.channel_file_state[key]

    def _get_active_processor(self):
        if not self.current_group or not self.current_channel:
            return None
        return self.processor_map.get(self._channel_key(self.current_group, self.current_channel))

    def _get_active_state(self):
        if not self.current_group or not self.current_channel or not self.current_file:
            return None
        key = self._state_key(self.current_group, self.current_channel, self.current_file)
        return self.channel_file_state.get(key)

    def _sync_ui_from_active_state(self):
        state = self._get_active_state()
        if state is None:
            return

        self.window_time_var.set(str(state['window_time']))
        self.noise_tol_var.set(str(state['noise_tolerance']))
        self.cutoff_var.set(str(state['cutoff_freq']))
        self.order_var.set(str(int(state['filter_order'])))

        ch_state = self._ensure_channel_state(self.current_group, self.current_channel)
        self.trigger_var.set(str(ch_state['trigger_threshold']))
        self.margin_var.set(str(ch_state['margin_fraction']))

        self.selection_start = state['manual_start_time']
        self.selection_end = state['manual_end_time']
        self.sel_start_var.set("" if state['manual_start_time'] is None else f"{state['manual_start_time']:.6f}")
        self.sel_end_var.set("" if state['manual_end_time'] is None else f"{state['manual_end_time']:.6f}")

        self._update_phase_controls()

    def _save_ui_to_selected_states(self, target_files, include_manual=False):
        if not self.current_group or not self.current_channel:
            return

        window_time = float(self.window_time_var.get())
        noise_tolerance = float(self.noise_tol_var.get())
        cutoff_freq = float(self.cutoff_var.get())
        filter_order = int(self.order_var.get())

        for file_name in target_files:
            key = self._state_key(self.current_group, self.current_channel, file_name)
            state = self.channel_file_state.get(key)
            if state is None:
                continue

            state['window_time'] = window_time
            state['noise_tolerance'] = noise_tolerance
            state['cutoff_freq'] = cutoff_freq
            state['filter_order'] = filter_order
            if include_manual:
                state['manual_start_time'] = self.selection_start
                state['manual_end_time'] = self.selection_end

    def _save_ui_auto_channel_params(self):
        if not self.current_group or not self.current_channel:
            return

        ch_state = self._ensure_channel_state(self.current_group, self.current_channel)
        ch_state['trigger_threshold'] = float(self.trigger_var.get())
        ch_state['margin_fraction'] = float(self.margin_var.get())

        for file_name in self._get_channel_files(self.current_group, self.current_channel):
            key = self._state_key(self.current_group, self.current_channel, file_name)
            state = self.channel_file_state.get(key)
            if state:
                state['trigger_threshold'] = ch_state['trigger_threshold']
                state['margin_fraction'] = ch_state['margin_fraction']

    def _get_channel_files(self, group_name, channel_name):
        proc = self.processor_map.get(self._channel_key(group_name, channel_name))
        if not proc:
            return []
        return sorted(proc.data.keys())

    # --------------------------- LOAD ALL DATA ---------------------------
    def _browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("TDMS files", "*.tdms"), ("All files", "*.*")])
        if path:
            self._set_source_path(path)

    def _browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self._set_source_path(path)

    def _resolve_tdms_paths(self, source_path):
        if os.path.isfile(source_path):
            return [source_path]
        if os.path.isdir(source_path):
            return sorted(glob.glob(os.path.join(source_path, "*.tdms")))
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

        channels_by_group = {g: sorted(list(chs)) for g, chs in channels_by_group.items()}
        return sorted(list(groups)), channels_by_group

    def _set_source_path(self, path):
        self.source_path = path
        self.path_var.set(path)

        self.processor_map = {}
        self.channel_file_state = {}
        self.channel_state = {}
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

            # Load ALL group-channel data in AutomaticSignalProcessor instances (raw only)
            load_count = 0
            fail_count = 0
            for group_name in groups:
                for channel_name in channels_by_group.get(group_name, []):
                    try:
                        proc = AutomaticSignalProcessor(path=path, group_name=group_name, channel_name=channel_name)
                        self.processor_map[self._channel_key(group_name, channel_name)] = proc
                        self._ensure_channel_state(group_name, channel_name)

                        for file_name, file_data in proc.data.items():
                            self._ensure_file_channel_state(group_name, channel_name, file_name, file_data)

                        load_count += 1
                    except Exception as exc:
                        fail_count += 1
                        self._log(f"Skip {group_name}/{channel_name}: {exc}")

            self.group_combo['values'] = groups
            if groups:
                self.group_var.set(groups[0])
                self.current_group = groups[0]
                self._update_channel_options()

            self._log(f"Loaded source: {path}")
            self._log(f"Files: {len(tdms_paths)} | Groups: {len(groups)} | Group-channel streams loaded: {load_count} | Failed: {fail_count}")
        except Exception as exc:
            messagebox.showerror("Metadata error", str(exc))

    def _update_channel_options(self):
        group_name = self.group_var.get().strip()
        self.current_group = group_name if group_name else None

        channels = self.channels_by_group.get(group_name, [])
        self.channel_combo['values'] = channels

        if channels:
            self.channel_var.set(channels[0])
            self.current_channel = channels[0]
            self._on_channel_changed()
        else:
            self.channel_var.set("")
            self.current_channel = None
            self.refresh_plot()

    def _on_group_changed(self):
        self._update_channel_options()

    def _on_channel_changed(self):
        self.current_channel = self.channel_var.get().strip() or None

        if not self.current_group or not self.current_channel:
            self.refresh_plot()
            return

        files = self._get_channel_files(self.current_group, self.current_channel)
        self.file_combo['values'] = files
        self.process_file_listbox.delete(0, tk.END)
        for file_name in files:
            self.process_file_listbox.insert(tk.END, file_name)

        if files:
            self.current_file = files[0]
            self.file_var.set(files[0])
        else:
            self.current_file = None
            self.file_var.set("")

        self._sync_ui_from_active_state()
        self.refresh_plot()

    def _on_file_changed(self):
        prev = self.current_file
        if prev and self.current_group and self.current_channel:
            self._save_ui_to_selected_states([prev], include_manual=True)

        self.current_file = self.file_var.get().strip() or None
        self._sync_ui_from_active_state()
        self.refresh_plot()

    # --------------------------- PHASE CONTROL ---------------------------
    def _update_phase_controls(self):
        if not self.current_group or not self.current_channel:
            return

        ch_state = self._ensure_channel_state(self.current_group, self.current_channel)
        auto_done = ch_state['auto_pipeline_done']

        if auto_done:
            self.trigger_entry.configure(state='disabled')
            self.margin_entry.configure(state='disabled')
            self.btn_auto_compute.configure(state='disabled')
            if not self.chk_corrected.winfo_ismapped():
                self.chk_corrected.pack(side=tk.LEFT, padx=(0, 8))
            if not self.chk_filtered.winfo_ismapped():
                self.chk_filtered.pack(side=tk.LEFT, padx=(0, 8))
        else:
            self.trigger_entry.configure(state='normal')
            self.margin_entry.configure(state='normal')
            self.btn_auto_compute.configure(state='normal')
            if self.chk_corrected.winfo_ismapped():
                self.chk_corrected.pack_forget()
            if self.chk_filtered.winfo_ismapped():
                self.chk_filtered.pack_forget()
            self.show_corrected_var.set(False)
            self.show_filtered_var.set(False)
            self.show_raw_var.set(True)

    # --------------------------- PROCESSING ---------------------------
    def _get_target_files(self):
        if self.process_all_var.get() and self.current_group and self.current_channel:
            return self._get_channel_files(self.current_group, self.current_channel)

        idxs = list(self.process_file_listbox.curselection())
        if idxs:
            return [self.process_file_listbox.get(i) for i in idxs]

        if self.current_file:
            return [self.current_file]

        return []

    def _apply_drift(self):
        proc = self._get_active_processor()
        if proc is None:
            return

        try:
            target_files = self._get_target_files()
            self._save_ui_to_selected_states(target_files)

            for file_name in target_files:
                state = self.channel_file_state[self._state_key(self.current_group, self.current_channel, file_name)]
                proc.drift_offset_correction(
                    window_time=state['window_time'],
                    noise_tolerance=state['noise_tolerance'],
                    target_files=[file_name],
                )
                state['drift_applied'] = 'corrected' in proc.data[file_name]
                state['corrected'] = proc.data[file_name].get('corrected').copy() if 'corrected' in proc.data[file_name] else None
                state['t_full_processed'] = proc.data[file_name]['t_full'].copy()

            self._log(f"Drift correction applied to {len(target_files)} file(s).")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Drift correction error", str(exc))

    def _apply_filter(self):
        proc = self._get_active_processor()
        if proc is None:
            return

        try:
            target_files = self._get_target_files()
            self._save_ui_to_selected_states(target_files)

            for file_name in target_files:
                state = self.channel_file_state[self._state_key(self.current_group, self.current_channel, file_name)]
                proc.apply_lowpass_filter(
                    cutoff_freq=state['cutoff_freq'],
                    order=state['filter_order'],
                    target_files=[file_name],
                )
                state['filter_applied'] = 'filtered' in proc.data[file_name]
                state['filtered'] = proc.data[file_name].get('filtered').copy() if 'filtered' in proc.data[file_name] else None
                state['t_full_processed'] = proc.data[file_name]['t_full'].copy()

            self._log(f"Lowpass filter applied to {len(target_files)} file(s).")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Filter error", str(exc))

    def _auto_compute_force(self):
        proc = self._get_active_processor()
        if proc is None:
            return

        try:
            ch_state = self._ensure_channel_state(self.current_group, self.current_channel)
            ch_state['trigger_threshold'] = float(self.trigger_var.get())
            ch_state['margin_fraction'] = float(self.margin_var.get())

            target_files = self._get_target_files()
            for file_name in target_files:
                state = self.channel_file_state[self._state_key(self.current_group, self.current_channel, file_name)]
                state['trigger_threshold'] = ch_state['trigger_threshold']
                state['margin_fraction'] = ch_state['margin_fraction']

            proc.compute_average_cutting_force(
                trigger_threshold=ch_state['trigger_threshold'],
                margin_fraction=ch_state['margin_fraction'],
                target_files=target_files,
            )

            for file_name in target_files:
                fdata = proc.data[file_name]
                state = self.channel_file_state[self._state_key(self.current_group, self.current_channel, file_name)]
                state['auto_force_applied'] = True
                state['mean_force_auto'] = fdata.get('mean_force')
                state['tri_start_time'] = fdata.get('tri_start_time')
                state['tri_end_time'] = fdata.get('tri_end_time')
                state['steady_start_time'] = fdata.get('steady_start_time')
                state['steady_end_time'] = fdata.get('steady_end_time')

            self._log(f"Auto mean force computed for {len(target_files)} file(s).")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Auto force error", str(exc))

    def _run_automatic_pipeline(self):
        proc = self._get_active_processor()
        if proc is None:
            return

        try:
            all_files = self._get_channel_files(self.current_group, self.current_channel)
            self._save_ui_to_selected_states(all_files)
            self._save_ui_auto_channel_params()

            ch_state = self._ensure_channel_state(self.current_group, self.current_channel)

            self._log("Running automatic pipeline: drift -> lowpass -> auto force...")
            for file_name in all_files:
                state = self.channel_file_state[self._state_key(self.current_group, self.current_channel, file_name)]
                try:
                    proc.drift_offset_correction(
                        window_time=state['window_time'],
                        noise_tolerance=state['noise_tolerance'],
                        target_files=[file_name],
                    )
                    state['drift_applied'] = 'corrected' in proc.data[file_name]
                    state['corrected'] = proc.data[file_name].get('corrected').copy() if 'corrected' in proc.data[file_name] else None

                    proc.apply_lowpass_filter(
                        cutoff_freq=state['cutoff_freq'],
                        order=state['filter_order'],
                        target_files=[file_name],
                    )
                    state['filter_applied'] = 'filtered' in proc.data[file_name]
                    state['filtered'] = proc.data[file_name].get('filtered').copy() if 'filtered' in proc.data[file_name] else None

                    proc.compute_average_cutting_force(
                        trigger_threshold=ch_state['trigger_threshold'],
                        margin_fraction=ch_state['margin_fraction'],
                        target_files=[file_name],
                    )

                    fdata = proc.data[file_name]
                    state['auto_force_applied'] = True
                    state['mean_force_auto'] = fdata.get('mean_force')
                    state['tri_start_time'] = fdata.get('tri_start_time')
                    state['tri_end_time'] = fdata.get('tri_end_time')
                    state['steady_start_time'] = fdata.get('steady_start_time')
                    state['steady_end_time'] = fdata.get('steady_end_time')
                    state['t_full_processed'] = fdata.get('t_full').copy() if 't_full' in fdata else None
                    state['last_error'] = None
                except Exception as per_file_exc:
                    state['last_error'] = str(per_file_exc)
                    self._log(f"  {file_name}: pipeline failed -> {per_file_exc}")

            ch_state['auto_pipeline_done'] = True
            self._update_phase_controls()
            self._log("Automatic pipeline complete for current channel.")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Pipeline error", str(exc))

    # --------------------------- REGION / MANUAL ---------------------------
    def _on_region_selected(self, xmin, xmax):
        self.selection_start = float(min(xmin, xmax))
        self.selection_end = float(max(xmin, xmax))
        self.sel_start_var.set(f"{self.selection_start:.6f}")
        self.sel_end_var.set(f"{self.selection_end:.6f}")

        if self.current_file:
            self._save_ui_to_selected_states([self.current_file], include_manual=True)

        self._manual_compute_force()

    def _apply_entry_range(self):
        try:
            start = float(self.sel_start_var.get().strip())
            end = float(self.sel_end_var.get().strip())
            if end <= start:
                raise ValueError("End must be greater than start.")

            self.selection_start = start
            self.selection_end = end
            if self.current_file:
                self._save_ui_to_selected_states([self.current_file], include_manual=True)

            self._manual_compute_force()
        except Exception as exc:
            messagebox.showerror("Invalid range", str(exc))

    def _manual_compute_force(self):
        proc = self._get_active_processor()
        if proc is None:
            return
        if self.selection_start is None or self.selection_end is None:
            return
        if not self.current_file:
            return

        try:
            result = proc.compute_manual_force_in_time_span(
                self.selection_start,
                self.selection_end,
                target_files=[self.current_file],
                use_filtered=True,
            )
            mean_val = result.get(self.current_file)

            state = self._get_active_state()
            if state is not None:
                state['manual_start_time'] = self.selection_start
                state['manual_end_time'] = self.selection_end
                state['manual_force_applied'] = True
                state['mean_force_manual'] = mean_val

            self._log(f"Manual mean force | {self.current_file}: {mean_val:.4f}")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Manual force error", str(exc))

    def _zero_selected_region(self):
        proc = self._get_active_processor()
        if proc is None:
            return
        if self.selection_start is None or self.selection_end is None or not self.current_file:
            messagebox.showwarning("No selection", "Select a region in the chart first.")
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
        if proc is None:
            return
        if self.selection_start is None or self.selection_end is None or not self.current_file:
            messagebox.showwarning("No selection", "Select a region in the chart first.")
            return

        try:
            proc.remove_time_span(self.selection_start, self.selection_end, target_files=[self.current_file])
            self._refresh_state_from_processor_file(self.current_file)
            self._log(f"Removed signal span [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Remove span error", str(exc))

    def _keep_only_selected_region(self):
        proc = self._get_active_processor()
        if proc is None:
            return
        if self.selection_start is None or self.selection_end is None or not self.current_file:
            messagebox.showwarning("No selection", "Select a region in the chart first.")
            return

        try:
            proc.keep_only_time_span(self.selection_start, self.selection_end, target_files=[self.current_file])
            self._refresh_state_from_processor_file(self.current_file)
            self._log(f"Kept only span [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Keep-only span error", str(exc))

    def _refresh_state_from_processor_file(self, file_name):
        proc = self._get_active_processor()
        state = self._get_active_state()
        if proc is None or state is None or file_name not in proc.data:
            return

        fdata = proc.data[file_name]
        state['fs'] = fdata['fs']
        state['ts'] = fdata['ts']
        state['raw'] = fdata['raw'].copy()
        state['t_full_raw'] = fdata['t_full'].copy()
        state['corrected'] = fdata.get('corrected').copy() if 'corrected' in fdata else None
        state['filtered'] = fdata.get('filtered').copy() if 'filtered' in fdata else None
        state['t_full_processed'] = fdata['t_full'].copy()

    # --------------------------- EXPORT CSV ---------------------------
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
            cl = ch.strip().lower()
            if cl in canonical and canonical[cl] is None:
                canonical[cl] = ch

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
                proc = self.processor_map.get(self._channel_key(group_name, channel_name))
                if proc is None:
                    proc = AutomaticSignalProcessor(path=self.source_path, group_name=group_name, channel_name=channel_name)

                ch_state = self._ensure_channel_state(group_name, channel_name)

                for file_name in sorted(proc.data.keys()):
                    key = self._state_key(group_name, channel_name, file_name)
                    state = self.channel_file_state.get(key)
                    if state is None:
                        state = self._ensure_file_channel_state(group_name, channel_name, file_name, proc.data[file_name])

                    value = state.get('mean_force_manual') if state.get('manual_force_applied') else state.get('mean_force_auto')

                    if value is None:
                        # Fallback run for missing result
                        proc.drift_offset_correction(
                            window_time=state['window_time'],
                            noise_tolerance=state['noise_tolerance'],
                            target_files=[file_name],
                        )
                        proc.apply_lowpass_filter(
                            cutoff_freq=state['cutoff_freq'],
                            order=state['filter_order'],
                            target_files=[file_name],
                        )
                        proc.compute_average_cutting_force(
                            trigger_threshold=ch_state['trigger_threshold'],
                            margin_fraction=ch_state['margin_fraction'],
                            target_files=[file_name],
                        )
                        value = proc.data[file_name].get('mean_force')

                    rows[file_name][axis] = '' if value is None else f"{value:.4f}"

            with open(save_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['file', 'fx', 'fy', 'fz'])
                for file_name in files:
                    writer.writerow([file_name, rows[file_name]['fx'], rows[file_name]['fy'], rows[file_name]['fz']])

            self._log(f"CSV exported: {save_path}")
        except Exception as exc:
            messagebox.showerror("CSV export error", str(exc))

    # --------------------------- PLOT ---------------------------
    def refresh_plot(self):
        self.ax.clear()
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Amplitude")
        self.ax.grid(True, linestyle="--", alpha=0.4)

        state = self._get_active_state()
        proc = self._get_active_processor()
        if state is None or proc is None or self.current_file not in proc.data:
            self.ax.set_title("Load data, choose group/channel/file")
            self.canvas.draw_idle()
            return

        file_data = proc.data[self.current_file]
        t = file_data['t_full']

        ch_state = self._ensure_channel_state(self.current_group, self.current_channel)
        self._update_phase_controls()

        plotted = False

        if self.show_raw_var.get() and 'raw' in file_data:
            self.ax.plot(t, file_data['raw'], color='tab:gray', linewidth=1.0, label='raw')
            plotted = True

        if ch_state['auto_pipeline_done']:
            if self.show_corrected_var.get() and 'corrected' in file_data:
                self.ax.plot(t, file_data['corrected'], color='tab:orange', linewidth=1.0, label='corrected')
                plotted = True

            if self.show_filtered_var.get() and 'filtered' in file_data:
                self.ax.plot(t, file_data['filtered'], color='tab:blue', linewidth=1.0, label='filtered')
                plotted = True

        if not plotted and 'raw' in file_data:
            self.ax.plot(t, file_data['raw'], color='tab:gray', linewidth=1.0, label='raw')

        # Simpler interval view: manual takes priority over auto
        if state.get('manual_force_applied') and state.get('manual_start_time') is not None and state.get('manual_end_time') is not None:
            ss = state['manual_start_time']
            se = state['manual_end_time']
            mf = state.get('mean_force_manual')
            self.ax.axvspan(ss, se, color='tab:orange', alpha=0.20, label='manual region')
            if mf is not None:
                self.ax.plot([ss, se], [mf, mf], color='tab:orange', linestyle='--', linewidth=2, label=f"manual mean: {mf:.3f}")
        elif state.get('auto_force_applied') and state.get('steady_start_time') is not None and state.get('steady_end_time') is not None:
            ss = state['steady_start_time']
            se = state['steady_end_time']
            mf = state.get('mean_force_auto')
            self.ax.axvspan(ss, se, color='tab:green', alpha=0.20, label='auto steady')
            if mf is not None:
                self.ax.plot([ss, se], [mf, mf], 'r--', linewidth=2, label=f"auto mean: {mf:.3f}")

        title = (
            f"File: {self.current_file} | Group: {self.current_group} | Channel: {self.current_channel}"
            f"\nwindow={state['window_time']:.3f}s noise={state['noise_tolerance']:.3f} "
            f"cutoff={state['cutoff_freq']:.3f}Hz order={int(state['filter_order'])} "
            f"trigger={state['trigger_threshold']:.3f} margin={state['margin_fraction']:.3f}"
        )
        self.ax.set_title(title)
        self.ax.legend(loc='upper right')
        self.figure.tight_layout()
        self.canvas.draw_idle()

    # --------------------------- LOG ---------------------------
    def _log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = TDMSGuiApp(root)
    root.mainloop()
