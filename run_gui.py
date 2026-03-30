import os
import glob
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
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

        ttk.Label(merged_group, text="Files to view").grid(row=6, column=0, sticky="w", pady=(6, 0))
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

        # 3) Export and output
        out_group = ttk.LabelFrame(self.controls_frame, text="3) Output", padding=8)
        out_group.pack(fill=tk.BOTH, expand=True, pady=4)

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
                't_full': file_data['t_full'].copy()
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

        self.refresh_plot()

    def _on_active_file_changed(self):
        self.current_file = self.active_file_var.get().strip() or None
        self.refresh_plot()

    def _on_view_files_changed(self):
        sel = self._get_view_files()
        if sel:
            # Keep the first viewed file as active if active file is outside selection
            if self.current_file not in sel:
                self.current_file = sel[0]
                self.active_file_var.set(sel[0])
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

            if 'raw' in fdata:
                ax.plot(t, fdata['raw'], color='tab:gray', linewidth=0.9, label='raw')

            ax.set_title(fname, fontsize=9)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            ax.grid(True, linestyle='--', alpha=0.4)
            ax.legend(loc='upper right', fontsize='x-small')

        for ax in axes[len(files):]:
            ax.set_visible(False)

        # Keep active file synced with first viewed file
        if files and self.current_file not in files:
            self.current_file = files[0]
            self.active_file_var.set(files[0])

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
