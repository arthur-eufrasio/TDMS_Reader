import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector

from processor.automatic_signal_processor import AutomaticSignalProcessor


class TDMSGuiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TDMS Signal Analyzer")
        self.root.geometry("1400x900")

        self.processor = None
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
        self.group_var = tk.StringVar(value="Part Waveform")
        self.channel_var = tk.StringVar(value="Fy")

        ttk.Label(source_group, text="TDMS file/folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(source_group, textvariable=self.path_var, width=34).grid(row=1, column=0, sticky="ew", padx=(0, 4))

        btns = ttk.Frame(source_group)
        btns.grid(row=1, column=1, sticky="e")
        ttk.Button(btns, text="File", command=self._browse_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Folder", command=self._browse_folder).pack(side=tk.LEFT, padx=2)

        ttk.Label(source_group, text="Group").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(source_group, textvariable=self.group_var).grid(row=3, column=0, sticky="ew", padx=(0, 4))

        ttk.Label(source_group, text="Channel").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(source_group, textvariable=self.channel_var).grid(row=5, column=0, sticky="ew", padx=(0, 4))

        ttk.Button(source_group, text="Load Signals", command=self._load_signals).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        source_group.columnconfigure(0, weight=1)

        # File and display
        view_group = ttk.LabelFrame(self.controls_frame, text="2) View", padding=8)
        view_group.pack(fill=tk.X, pady=4)

        self.file_var = tk.StringVar()
        self.file_combo = ttk.Combobox(view_group, textvariable=self.file_var, state="readonly")
        self.file_combo.grid(row=0, column=0, sticky="ew")
        self.file_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_file_changed())

        ttk.Label(view_group, text="Display signal").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.display_signal_var = tk.StringVar(value="filtered")
        display_opts = ttk.Frame(view_group)
        display_opts.grid(row=2, column=0, sticky="w")
        for value in ["raw", "corrected", "filtered"]:
            ttk.Radiobutton(display_opts, text=value, value=value, variable=self.display_signal_var,
                            command=self.refresh_plot).pack(side=tk.LEFT, padx=(0, 8))

        self.show_auto_interval_var = tk.BooleanVar(value=True)
        self.show_manual_interval_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(view_group, text="Show auto interval", variable=self.show_auto_interval_var,
                        command=self.refresh_plot).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(view_group, text="Show manual interval", variable=self.show_manual_interval_var,
                        command=self.refresh_plot).grid(row=4, column=0, sticky="w")

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

        ttk.Label(proc_group, text="Window time (s)").grid(row=0, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.window_time_var, width=10).grid(row=0, column=1, sticky="w")

        ttk.Label(proc_group, text="Noise tolerance").grid(row=1, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.noise_tol_var, width=10).grid(row=1, column=1, sticky="w")

        ttk.Button(proc_group, text="Apply Drift Correction", command=self._apply_drift).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(4, 6)
        )

        ttk.Label(proc_group, text="Lowpass cutoff (Hz)").grid(row=3, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.cutoff_var, width=10).grid(row=3, column=1, sticky="w")

        ttk.Label(proc_group, text="Filter order").grid(row=4, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.order_var, width=10).grid(row=4, column=1, sticky="w")

        ttk.Button(proc_group, text="Apply Lowpass", command=self._apply_filter).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(4, 6)
        )

        ttk.Label(proc_group, text="Trigger threshold").grid(row=6, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.trigger_var, width=10).grid(row=6, column=1, sticky="w")

        ttk.Label(proc_group, text="Margin fraction").grid(row=7, column=0, sticky="w")
        ttk.Entry(proc_group, textvariable=self.margin_var, width=10).grid(row=7, column=1, sticky="w")

        ttk.Button(proc_group, text="Auto Compute Mean Force", command=self._auto_compute_force).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(4, 0)
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

        self.apply_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(select_group, text="Apply to all files", variable=self.apply_all_var).grid(
            row=4, column=0, columnspan=2, sticky="w"
        )

        ttk.Button(select_group, text="Manual Mean Force (Selected)", command=self._manual_compute_force).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )
        ttk.Button(select_group, text="Zero Selected Region", command=self._zero_selected_region).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )
        ttk.Button(select_group, text="Remove Selected Region", command=self._remove_selected_region).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )
        ttk.Button(select_group, text="Keep Only Selected Region", command=self._keep_only_selected_region).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(4, 0)
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
            self.path_var.set(path)

    def _browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)

    def _load_signals(self):
        path = self.path_var.get().strip()
        group = self.group_var.get().strip()
        channel = self.channel_var.get().strip()

        if not path:
            messagebox.showwarning("Missing path", "Please choose a TDMS file or folder.")
            return

        try:
            self.processor = AutomaticSignalProcessor(path=path, group_name=group, channel_name=channel)
            files = sorted(self.processor.data.keys())
            self.file_combo["values"] = files

            if files:
                self.file_var.set(files[0])
                self.current_file = files[0]

            self._log(f"Loaded {len(files)} file(s) from: {path}")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))

    def _on_file_changed(self):
        self.current_file = self.file_var.get()
        self.refresh_plot()

    def _get_target_files(self):
        if self.processor is None:
            return None
        if self.apply_all_var.get():
            return list(self.processor.data.keys())
        if self.current_file:
            return [self.current_file]
        return None

    def _on_region_selected(self, xmin, xmax):
        start = float(min(xmin, xmax))
        end = float(max(xmin, xmax))
        self.selection_start = start
        self.selection_end = end
        self.sel_start_var.set(f"{start:.6f}")
        self.sel_end_var.set(f"{end:.6f}")
        self._log(f"Selected interval: [{start:.4f}, {end:.4f}] s")
        self.refresh_plot()

    def _apply_entry_range(self):
        try:
            start = float(self.sel_start_var.get().strip())
            end = float(self.sel_end_var.get().strip())
            if end <= start:
                raise ValueError("End must be greater than start.")
            self.selection_start = start
            self.selection_end = end
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Invalid range", str(exc))

    def _apply_drift(self):
        if self.processor is None:
            return
        try:
            window_time = float(self.window_time_var.get())
            noise_tol = float(self.noise_tol_var.get())
            self.processor.drift_offset_correction(window_time=window_time, noise_tolerance=noise_tol)
            self._log("Drift correction applied to all files.")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Drift correction error", str(exc))

    def _apply_filter(self):
        if self.processor is None:
            return
        try:
            cutoff = float(self.cutoff_var.get())
            order = int(self.order_var.get())
            self.processor.apply_lowpass_filter(cutoff_freq=cutoff, order=order)
            self._log(f"Lowpass filter applied. cutoff={cutoff}, order={order}")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Filter error", str(exc))

    def _auto_compute_force(self):
        if self.processor is None:
            return
        try:
            trig = float(self.trigger_var.get())
            margin = float(self.margin_var.get())
            self.processor.compute_average_cutting_force(trigger_threshold=trig, margin_fraction=margin)
            self._log("Auto mean force computed for all files.")
            for fname, force in self.processor.get_force_results().items():
                self._log(f"  {fname}: mean_force={force:.4f}")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Auto force error", str(exc))

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
                target_files=self._get_target_files(),
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
                target_files=self._get_target_files(),
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
                target_files=self._get_target_files(),
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
                target_files=self._get_target_files(),
            )
            self._log(f"Kept only span [{self.selection_start:.4f}, {self.selection_end:.4f}] s")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Keep-only span error", str(exc))

    def _get_display_signal(self, file_data):
        requested = self.display_signal_var.get()
        if requested in file_data:
            return file_data[requested], requested

        for fallback in ("filtered", "corrected", "raw"):
            if fallback in file_data:
                return file_data[fallback], fallback
        raise ValueError("No signal found to plot.")

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

        signal, key_used = self._get_display_signal(file_data)
        t = file_data['t_full']

        self.ax.plot(t, signal, color="tab:blue", linewidth=1.0, label=f"{key_used} signal")

        if self.show_auto_interval_var.get() and 'mean_force' in file_data:
            ts = file_data['tri_start_time']
            te = file_data['tri_end_time']
            ss = file_data['steady_start_time']
            se = file_data['steady_end_time']
            mf = file_data['mean_force']

            self.ax.axvspan(ts, te, color="gray", alpha=0.12, label="auto trigger")
            self.ax.axvspan(ss, se, color="tab:green", alpha=0.18, label="auto steady")
            self.ax.plot([ss, se], [mf, mf], "r--", linewidth=2, label=f"auto mean: {mf:.3f}")

        if self.show_manual_interval_var.get() and 'mean_force_manual' in file_data:
            ss = file_data.get('manual_start_time')
            se = file_data.get('manual_end_time')
            mf = file_data.get('mean_force_manual')
            if ss is not None and se is not None and mf is not None:
                self.ax.axvspan(ss, se, color="tab:orange", alpha=0.20, label="manual interval")
                self.ax.plot([ss, se], [mf, mf], color="tab:orange", linestyle="--", linewidth=2,
                             label=f"manual mean: {mf:.3f}")

        if self.selection_start is not None and self.selection_end is not None:
            self.ax.axvspan(self.selection_start, self.selection_end, color="tab:green", alpha=0.10,
                            label="current selection")

        self.ax.set_title(f"File: {self.current_file} | Channel: {self.processor.channel_name}")
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
