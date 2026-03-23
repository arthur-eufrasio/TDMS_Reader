import os
import glob
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
        self.root.geometry("1400x900")

        self.processor = None
        self.source_path = None
        self.available_paths = []
        self.channels_by_group = {}
        self.current_file = None
        self.selection_start = None
        self.selection_end = None
        self.span_selector = None

        self._build_ui()

    def _build_ui(self):
        self.main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        self.controls_frame = ttk.Frame(self.main_pane, padding=10)
        self.plot_frame = ttk.Frame(self.main_pane, padding=10)

        self.main_pane.add(self.controls_frame, weight=1)
        self.main_pane.add(self.plot_frame, weight=3)

        self._build_controls()
        self._build_plot()

    def _build_controls(self):
        # Data source
        source_group = ttk.LabelFrame(self.controls_frame, text="1) Data Source", padding=8)
        source_group.pack(fill=tk.X, pady=4)

        self.path_var = tk.StringVar()
        self.group_var = tk.StringVar(value="")
        self.channel_var = tk.StringVar(value="")

        ttk.Label(source_group, text="TDMS file/folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(source_group, textvariable=self.path_var, width=34, state="readonly").grid(
            row=1, column=0, sticky="ew", padx=(0, 4)
        )

        btns = ttk.Frame(source_group)
        btns.grid(row=1, column=1, sticky="e")
        ttk.Button(btns, text="File", command=self._browse_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Folder", command=self._browse_folder).pack(side=tk.LEFT, padx=2)

        source_group.columnconfigure(0, weight=1)

        # File and display
        view_group = ttk.LabelFrame(self.controls_frame, text="2) View", padding=8)
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
        self.show_raw_var = tk.BooleanVar(value=False)
        self.show_corrected_var = tk.BooleanVar(value=True)
        self.show_filtered_var = tk.BooleanVar(value=True)
        display_opts = ttk.Frame(view_group)
        display_opts.grid(row=7, column=0, sticky="w")
        ttk.Checkbutton(display_opts, text="raw", variable=self.show_raw_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(display_opts, text="corrected", variable=self.show_corrected_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(display_opts, text="filtered", variable=self.show_filtered_var, command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))

        view_group.columnconfigure(0, weight=1)

        # Processing controls
        proc_group = ttk.LabelFrame(self.controls_frame, text="3) Processing", padding=8)
        proc_group.pack(fill=tk.X, pady=4)

        self.window_time_var = tk.StringVar(value="0.3")
        self.noise_tol_var = tk.StringVar(value="20.0")
        self.cutoff_var = tk.StringVar(value="10")
        self.order_var = tk.StringVar(value="5")
        self.trigger_var = tk.StringVar(value="5.0")
        self.margin_var = tk.StringVar(value="0.1")
        self.process_all_var = tk.BooleanVar(value=True)

        ttk.Label(proc_group, text="Target files").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(proc_group, text="All files", variable=self.process_all_var).grid(row=0, column=1, sticky="w")

        files_frame = ttk.Frame(proc_group)
        files_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        self.process_file_listbox = tk.Listbox(files_frame, selectmode=tk.EXTENDED, height=4, exportselection=False)
        self.process_file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.process_file_listbox.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.process_file_listbox.configure(yscrollcommand=list_scroll.set)

        ttk.Label(proc_group, text="Window time (s)").grid(row=2, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.window_time_var, width=10).grid(row=2, column=1, sticky="w")

        ttk.Label(proc_group, text="Noise tolerance").grid(row=3, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.noise_tol_var, width=10).grid(row=3, column=1, sticky="w")

        ttk.Button(proc_group, text="Apply Drift Correction", command=self._apply_drift).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(4, 6)
        )

        ttk.Label(proc_group, text="Lowpass cutoff (Hz)").grid(row=5, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.cutoff_var, width=10).grid(row=5, column=1, sticky="w")

        ttk.Label(proc_group, text="Filter order").grid(row=6, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.order_var, width=10).grid(row=6, column=1, sticky="w")

        ttk.Button(proc_group, text="Apply Lowpass", command=self._apply_filter).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(4, 6)
        )

        ttk.Label(proc_group, text="Trigger threshold").grid(row=8, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.trigger_var, width=10).grid(row=8, column=1, sticky="w")

        ttk.Label(proc_group, text="Margin fraction").grid(row=9, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.margin_var, width=10).grid(row=9, column=1, sticky="w")

        ttk.Button(proc_group, text="Auto Compute Mean Force", command=self._auto_compute_force).grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )

        ttk.Button(proc_group, text="Run Automatic Pipeline", command=self._run_automatic_pipeline).grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )

        # Selection and editing tools
        select_group = ttk.LabelFrame(self.controls_frame, text="4) Region Selection", padding=8)
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

        # Log output
        log_group = ttk.LabelFrame(self.controls_frame, text="5) Output", padding=8)
        log_group.pack(fill=tk.BOTH, expand=True, pady=4)

        self.log_text = ScrolledText(log_group, height=10)
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
        self.selection_start = None
        self.selection_end = None

        tdms_paths = self._resolve_tdms_paths(path)
        if not tdms_paths:
            messagebox.showwarning("No files", "No TDMS files found in selected location.")
            return

        self.available_paths = tdms_paths
        self.file_combo["values"] = [os.path.basename(p) for p in tdms_paths]
        if tdms_paths:
            self.file_var.set(os.path.basename(tdms_paths[0]))
            self.current_file = os.path.basename(tdms_paths[0])

        try:
            groups, channels_by_group = self._discover_metadata(tdms_paths)
            self.channels_by_group = channels_by_group
            self.group_combo["values"] = groups

            if groups:
                self.group_var.set(groups[0])
                self._update_channel_options()

            self._log(f"Loaded source: {path}")
            self._log(f"Found {len(tdms_paths)} TDMS file(s), {len(groups)} group(s).")
        except Exception as exc:
            messagebox.showerror("Metadata error", str(exc))

    def _update_channel_options(self):
        group = self.group_var.get().strip()
        channels = self.channels_by_group.get(group, [])
        self.channel_combo["values"] = channels

        if channels:
            self.channel_var.set(channels[0])
            self._reload_processor(auto_run=True)
        else:
            self.channel_var.set("")
            self.processor = None
            self.refresh_plot()

    def _on_group_changed(self):
        self._update_channel_options()

    def _on_channel_changed(self):
        self._reload_processor(auto_run=True)

    def _reload_processor(self, auto_run=True):
        if not self.source_path:
            return

        group = self.group_var.get().strip()
        channel = self.channel_var.get().strip()
        if not group or not channel:
            return

        try:
            self.processor = AutomaticSignalProcessor(path=self.source_path, group_name=group, channel_name=channel)
            files = sorted(self.processor.data.keys())
            self.file_combo["values"] = files

            self.process_file_listbox.delete(0, tk.END)
            for name in files:
                self.process_file_listbox.insert(tk.END, name)

            if files:
                self.current_file = files[0]
                self.file_var.set(files[0])

            self._log(f"Signal loaded for Group='{group}', Channel='{channel}' ({len(files)} file(s)).")

            if auto_run:
                self._run_automatic_pipeline()
            else:
                self.refresh_plot()
        except Exception as exc:
            self.processor = None
            messagebox.showerror("Load error", str(exc))

    def _on_file_changed(self):
        self.current_file = self.file_var.get()
        self.refresh_plot()

    def _get_target_files(self):
        if self.processor is None:
            return []
        if self.process_all_var.get():
            return list(self.processor.data.keys())

        selected_idx = list(self.process_file_listbox.curselection())
        if selected_idx:
            return [self.process_file_listbox.get(i) for i in selected_idx]

        if self.current_file:
            return [self.current_file]
        return []

    def _on_region_selected(self, xmin, xmax):
        start = float(min(xmin, xmax))
        end = float(max(xmin, xmax))
        self.selection_start = start
        self.selection_end = end
        self.sel_start_var.set(f"{start:.6f}")
        self.sel_end_var.set(f"{end:.6f}")
        self._log(f"Selected interval: [{start:.4f}, {end:.4f}] s")
        self._manual_compute_force()

    def _apply_entry_range(self):
        try:
            start = float(self.sel_start_var.get().strip())
            end = float(self.sel_end_var.get().strip())
            if end <= start:
                raise ValueError("End must be greater than start.")
            self.selection_start = start
            self.selection_end = end
            self._manual_compute_force()
        except Exception as exc:
            messagebox.showerror("Invalid range", str(exc))

    def _apply_drift(self):
        if self.processor is None:
            return
        try:
            window_time = float(self.window_time_var.get())
            noise_tol = float(self.noise_tol_var.get())
            target_files = self._get_target_files()
            self.processor.drift_offset_correction(
                window_time=window_time,
                noise_tolerance=noise_tol,
                target_files=target_files,
            )
            self._log(f"Drift correction applied to {len(target_files)} file(s).")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Drift correction error", str(exc))

    def _apply_filter(self):
        if self.processor is None:
            return
        try:
            cutoff = float(self.cutoff_var.get())
            order = int(self.order_var.get())
            target_files = self._get_target_files()
            self.processor.apply_lowpass_filter(
                cutoff_freq=cutoff,
                order=order,
                target_files=target_files,
            )
            self._log(f"Lowpass filter applied to {len(target_files)} file(s). cutoff={cutoff}, order={order}")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Filter error", str(exc))

    def _auto_compute_force(self):
        if self.processor is None:
            return
        try:
            trig = float(self.trigger_var.get())
            margin = float(self.margin_var.get())
            target_files = self._get_target_files()
            self.processor.compute_average_cutting_force(
                trigger_threshold=trig,
                margin_fraction=margin,
                target_files=target_files,
            )
            self._log(f"Auto mean force computed for {len(target_files)} file(s).")
            for fname, force in self.processor.get_force_results().items():
                self._log(f"  {fname}: mean_force={force:.4f}")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Auto force error", str(exc))

    def _run_automatic_pipeline(self):
        if self.processor is None:
            return

        window_time = float(self.window_time_var.get())
        noise_tol = float(self.noise_tol_var.get())
        cutoff = float(self.cutoff_var.get())
        order = int(self.order_var.get())
        trig = float(self.trigger_var.get())
        margin = float(self.margin_var.get())

        self._log("Running automatic pipeline per file (drift -> filter -> auto force)...")
        for filename in self.processor.data.keys():
            try:
                self.processor.drift_offset_correction(
                    window_time=window_time,
                    noise_tolerance=noise_tol,
                    target_files=[filename],
                )
                self.processor.apply_lowpass_filter(
                    cutoff_freq=cutoff,
                    order=order,
                    target_files=[filename],
                )
                self.processor.compute_average_cutting_force(
                    trigger_threshold=trig,
                    margin_fraction=margin,
                    target_files=[filename],
                )
            except Exception as exc:
                self._log(f"  {filename}: auto pipeline failed -> {exc}")

        self._log("Automatic pipeline done.")
        self.refresh_plot()

    def _manual_compute_force(self):
        if self.processor is None:
            return
        if self.selection_start is None or self.selection_end is None:
            messagebox.showwarning("No selection", "Select a region in the chart first.")
            return

        try:
            results = self.processor.compute_manual_force_in_time_span(
                self.selection_start,
                self.selection_end,
                target_files=[self.current_file] if self.current_file else None,
                use_filtered=True,
            )
            for fname, force in results.items():
                self._log(f"Manual mean force | {fname}: {force:.4f}")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Manual force error", str(exc))

    def _zero_selected_region(self):
        if self.processor is None:
            return
        if self.selection_start is None or self.selection_end is None:
            messagebox.showwarning("No selection", "Select a region in the chart first.")
            return

        try:
            self.processor.zero_out_time_span(
                self.selection_start,
                self.selection_end,
                target_files=[self.current_file] if self.current_file else None,
            )
            self._log(f"Zeroed filtered signal in [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Zero region error", str(exc))

    def _remove_selected_region(self):
        if self.processor is None:
            return
        if self.selection_start is None or self.selection_end is None:
            messagebox.showwarning("No selection", "Select a region in the chart first.")
            return

        try:
            self.processor.remove_time_span(
                self.selection_start,
                self.selection_end,
                target_files=[self.current_file] if self.current_file else None,
            )
            self._log(f"Removed signal span [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Remove span error", str(exc))

    def _keep_only_selected_region(self):
        if self.processor is None:
            return
        if self.selection_start is None or self.selection_end is None:
            messagebox.showwarning("No selection", "Select a region in the chart first.")
            return

        try:
            self.processor.keep_only_time_span(
                self.selection_start,
                self.selection_end,
                target_files=[self.current_file] if self.current_file else None,
            )
            self._log(f"Kept only span [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Keep-only span error", str(exc))

    def refresh_plot(self):
        self.ax.clear()
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Amplitude")
        self.ax.grid(True, linestyle="--", alpha=0.4)

        if self.processor is None:
            self.ax.set_title("Load TDMS files to start")
            self.canvas.draw_idle()
            return

        if not self.current_file:
            self.canvas.draw_idle()
            return

        file_data = self.processor.data.get(self.current_file)
        if file_data is None:
            self.canvas.draw_idle()
            return

        t = file_data['t_full']

        plotted = False
        signal_styles = [
            ("raw", self.show_raw_var.get(), "tab:gray"),
            ("corrected", self.show_corrected_var.get(), "tab:orange"),
            ("filtered", self.show_filtered_var.get(), "tab:blue"),
        ]

        for key, enabled, color in signal_styles:
            if enabled and key in file_data:
                self.ax.plot(t, file_data[key], color=color, linewidth=1.0, label=f"{key} signal")
                plotted = True

        if not plotted:
            for key, _, color in signal_styles:
                if key in file_data:
                    self.ax.plot(t, file_data[key], color=color, linewidth=1.0, label=f"{key} signal")
                    break

        if 'mean_force_manual' in file_data and 'manual_start_time' in file_data and 'manual_end_time' in file_data:
            ss = file_data['manual_start_time']
            se = file_data['manual_end_time']
            mf = file_data['mean_force_manual']
            self.ax.axvspan(ss, se, color="tab:orange", alpha=0.20, label="selected region")
            self.ax.plot([ss, se], [mf, mf], color="tab:orange", linestyle="--", linewidth=2,
                         label=f"mean force: {mf:.3f}")
        elif 'mean_force' in file_data:
            ss = file_data['steady_start_time']
            se = file_data['steady_end_time']
            mf = file_data['mean_force']
            self.ax.axvspan(ss, se, color="tab:green", alpha=0.20, label="auto region")
            self.ax.plot([ss, se], [mf, mf], "r--", linewidth=2, label=f"auto mean: {mf:.3f}")

        self.ax.set_title(
            f"File: {self.current_file} | Group: {self.processor.group_name} | Channel: {self.processor.channel_name}"
        )
        self.ax.legend(loc="upper right")
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = TDMSGuiApp(root)
    root.mainloop()
