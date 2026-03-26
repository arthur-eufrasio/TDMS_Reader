from __future__ import annotations

import csv
from tkinter import messagebox
from typing import List

from core.filters import SignalFilter
from core.intervals import CutDetector
from core.reader import TDMSReader
from gui.models.app_state import AppState
from gui.views.main_window import MainWindow


class MainController:
    """Coordinates UI actions with the core processing services."""

    def __init__(self, view: MainWindow) -> None:
        self.view = view
        self.state = AppState()

        self.filter_service = SignalFilter()
        self.cut_service = CutDetector()

        self._wire_events()

    def _wire_events(self) -> None:
        self.view.bind_path_selected(self.on_path_selected)
        self.view.bind_load_requested(self.on_load_requested)
        self.view.bind_group_changed(self.on_group_changed)
        self.view.bind_channel_changed(self.on_channel_changed)
        self.view.bind_files_changed(self.on_files_changed)
        self.view.bind_active_file_changed(self.on_active_file_changed)
        self.view.bind_process_requested(self.on_process_requested)
        self.view.bind_manual_force_requested(self.on_manual_force_requested)
        self.view.bind_export_requested(self.on_export_requested)
        self.view.bind_span_selected(self.on_span_selected)
        self.view.bind_apply_range_requested(self.on_apply_range_requested)
        self.view.bind_zero_span_requested(self.on_zero_span_requested)
        self.view.bind_remove_span_requested(self.on_remove_span_requested)
        self.view.bind_keep_span_requested(self.on_keep_span_requested)
        self.view.bind_plot_options_changed(self.on_plot_options_changed)

    # -------- Event handlers --------
    def on_path_selected(self, path: str) -> None:
        self.state.source_path = path
        self.view.set_path(path)
        self.view.log(f"Source selected: {path}")

    def on_load_requested(self) -> None:
        if not self.state.source_path:
            messagebox.showwarning("Missing source", "Please select a TDMS file or folder first.")
            return

        try:
            self.state.channels_by_group = TDMSReader.discover_groups_and_channels(self.state.source_path)
            groups = sorted(self.state.channels_by_group.keys())
            self.view.set_group_options(groups)
            self.view.log(f"Discovered {len(groups)} groups.")
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))

    def on_group_changed(self, group_name: str) -> None:
        self.state.current_group = group_name or None
        if not self.state.current_group:
            self.view.set_channel_options([])
            return

        channels = self.state.channels_by_group.get(self.state.current_group, [])
        self.view.set_channel_options(channels)

    def on_channel_changed(self, channel_name: str) -> None:
        self.state.current_channel = channel_name or None
        self._load_channel_records()

    def on_files_changed(self, selected_files: List[str]) -> None:
        self.state.selected_files = selected_files
        if self.state.active_file not in selected_files and selected_files:
            self.state.active_file = selected_files[0]
        self._refresh_plot()

    def on_active_file_changed(self, file_name: str) -> None:
        self.state.active_file = file_name
        span = self.state.selected_spans.get(file_name)
        self.view.set_manual_range(span[0], span[1]) if span else self.view.set_manual_range(None, None)
        self._refresh_plot()

    def on_process_requested(self) -> None:
        if not self.state.selected_files:
            messagebox.showwarning("No files", "Select at least one file to process.")
            return

        try:
            params = self.view.get_processing_params()
        except Exception as exc:
            messagebox.showerror("Invalid parameters", str(exc))
            return

        processed = 0
        for record in self.state.get_selected_records():
            try:
                self.cut_service.detect_cutting_interval_on_raw(
                    record,
                    trigger_threshold=float(params["trigger_threshold"]),
                    margin_fraction=float(params["margin_fraction"]),
                    min_cut_time_sec=float(params["min_cut_time_sec"]),
                    expansion_time_sec=float(params["expansion_time_sec"]),
                    correction_window_time=float(params["window_time"]),
                )
                self.filter_service.drift_offset_correction(
                    record,
                    window_time=float(params["window_time"]),
                    noise_tolerance=float(params["noise_tolerance"]),
                    use_detected_regions=True,
                )
                self.filter_service.apply_lowpass_filter(
                    record,
                    cutoff_freq=float(params["cutoff_freq"]),
                    order=int(params["filter_order"]),
                )
                self.cut_service.compute_average_cutting_force(
                    record,
                    use_filtered=True,
                    prefer_existing_interval=True,
                )
                processed += 1
            except Exception as exc:
                self.view.log(f"[{record.filename}] processing error: {exc}")

        self.view.log(f"Processed {processed}/{len(self.state.selected_files)} selected file(s).")
        self._refresh_plot()

    def on_span_selected(self, start: float, end: float) -> None:
        if self.state.active_file is None:
            return
        self.state.selected_spans[self.state.active_file] = (start, end)
        self.view.set_manual_range(start, end)
        self.view.log(f"Selected span [{start:.4f}, {end:.4f}] s for {self.state.active_file}")
        self._refresh_plot()

    def on_apply_range_requested(self) -> None:
        if self.state.active_file is None:
            messagebox.showwarning("No active file", "Select an active file first.")
            return
        try:
            start, end = self.view.get_manual_range()
            self.state.selected_spans[self.state.active_file] = (start, end)
            self.view.log(f"Manual span set to [{start:.4f}, {end:.4f}] s for {self.state.active_file}")
            self._refresh_plot()
        except Exception as exc:
            messagebox.showerror("Invalid range", str(exc))

    def on_manual_force_requested(self) -> None:
        record = self.state.get_active_record()
        if record is None:
            messagebox.showwarning("No active file", "Select an active file first.")
            return

        span = self.state.selected_spans.get(record.filename)
        if span is None:
            messagebox.showwarning("No span", "Select a span first using drag or entry values.")
            return

        try:
            value = self.cut_service.compute_manual_force_in_time_span(record, span[0], span[1], use_filtered=True)
            self.view.log(f"Manual mean force | {record.filename}: {value:.4f}")
            self._refresh_plot()
        except Exception as exc:
            messagebox.showerror("Manual force error", str(exc))

    def on_zero_span_requested(self) -> None:
        record = self.state.get_active_record()
        if record is None:
            messagebox.showwarning("No active file", "Select an active file first.")
            return

        span = self.state.selected_spans.get(record.filename)
        if span is None:
            messagebox.showwarning("No span", "Select a span first using drag or entry values.")
            return

        try:
            self.filter_service.zero_out_time_span(record, span[0], span[1])
            self.view.log(f"Zeroed filtered signal in [{span[0]:.4f}, {span[1]:.4f}] s for {record.filename}")
            self._refresh_plot()
        except Exception as exc:
            messagebox.showerror("Zero region error", str(exc))

    def on_remove_span_requested(self) -> None:
        record = self.state.get_active_record()
        if record is None:
            messagebox.showwarning("No active file", "Select an active file first.")
            return

        span = self.state.selected_spans.get(record.filename)
        if span is None:
            messagebox.showwarning("No span", "Select a span first using drag or entry values.")
            return

        try:
            self.filter_service.remove_time_span(record, span[0], span[1])
            self.state.selected_spans.pop(record.filename, None)
            self.view.set_manual_range(None, None)
            self.view.log(f"Removed signal span [{span[0]:.4f}, {span[1]:.4f}] s for {record.filename}")
            self._refresh_plot()
        except Exception as exc:
            messagebox.showerror("Remove region error", str(exc))

    def on_keep_span_requested(self) -> None:
        record = self.state.get_active_record()
        if record is None:
            messagebox.showwarning("No active file", "Select an active file first.")
            return

        span = self.state.selected_spans.get(record.filename)
        if span is None:
            messagebox.showwarning("No span", "Select a span first using drag or entry values.")
            return

        try:
            self.filter_service.keep_only_time_span(record, span[0], span[1])
            self.state.selected_spans.pop(record.filename, None)
            self.view.set_manual_range(None, None)
            self.view.log(f"Kept only signal span [{span[0]:.4f}, {span[1]:.4f}] s for {record.filename}")
            self._refresh_plot()
        except Exception as exc:
            messagebox.showerror("Keep-only region error", str(exc))

    def on_plot_options_changed(self) -> None:
        self._refresh_plot()

    def on_export_requested(self) -> None:
        if not self.state.records:
            messagebox.showwarning("No data", "Load and process data before exporting.")
            return

        save_path = self.view.prompt_save_csv()
        if not save_path:
            return

        files = sorted(self.state.records.keys())

        try:
            with open(save_path, "w", newline="", encoding="utf-8") as out_file:
                writer = csv.writer(out_file)
                writer.writerow(["file", "mean_force_auto", "mean_force_manual"])
                for file_name in files:
                    record = self.state.records[file_name]
                    auto = "" if record.mean_force_auto is None else f"{record.mean_force_auto:.4f}"
                    manual = "" if record.mean_force_manual is None else f"{record.mean_force_manual:.4f}"
                    writer.writerow([file_name, auto, manual])
            self.view.log(f"CSV exported: {save_path}")
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))

    # -------- Internal --------
    def _load_channel_records(self) -> None:
        if not self.state.source_path or not self.state.current_group or not self.state.current_channel:
            return

        try:
            reader = TDMSReader(group_name=self.state.current_group, channel_name=self.state.current_channel)
            records = reader.read(self.state.source_path)
        except Exception as exc:
            messagebox.showerror("Read error", str(exc))
            return

        self.state.records = {record.filename: record for record in records}
        file_names = sorted(self.state.records.keys())

        self.state.selected_files = file_names.copy()
        self.state.active_file = file_names[0] if file_names else None
        self.state.selected_spans = {}

        self.view.set_file_options(file_names)
        self.view.log(
            f"Loaded {len(file_names)} file(s) for group '{self.state.current_group}' and channel '{self.state.current_channel}'."
        )
        self._refresh_plot()

    def _refresh_plot(self) -> None:
        title = f"Group: {self.state.current_group or '-'} | Channel: {self.state.current_channel or '-'} | Files: {len(self.state.selected_files)}"
        self.view.draw_records(
            records=self.state.records,
            selected_files=self.state.selected_files,
            active_file=self.state.active_file,
            selected_spans=self.state.selected_spans,
            title_prefix=title,
        )
