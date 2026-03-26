from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt

from .models import SignalRecord


class SignalFilter:
    """Apply signal correction and filtering operations to SignalRecord objects."""

    @staticmethod
    def _rebuild_time_axis(record: SignalRecord) -> None:
        record.t_full = np.arange(len(record.raw), dtype=float) * record.ts

    def drift_offset_correction(
        self,
        record: SignalRecord,
        window_time: float = 0.3,
        noise_tolerance: float = 5.0,
        use_detected_regions: bool = True,
    ) -> np.ndarray:
        window = int(window_time * record.fs)
        if window < 2:
            raise RuntimeError(f"[{record.filename}] window_time={window_time} is too small for fs={record.fs:.3f}.")

        if (
            use_detected_regions
            and record.corr_left_start_idx is not None
            and record.corr_left_end_idx is not None
            and record.corr_right_start_idx is not None
            and record.corr_right_end_idx is not None
        ):
            left_start = int(record.corr_left_start_idx)
            left_end = int(record.corr_left_end_idx)
            right_start = int(record.corr_right_start_idx)
            right_end = int(record.corr_right_end_idx)
        else:
            left_start = 0
            left_end = window
            right_start = max(0, len(record.raw) - window)
            right_end = len(record.raw)

        if left_end <= left_start or right_end <= right_start:
            raise RuntimeError(f"[{record.filename}] Invalid correction windows.")

        start_window = record.raw[left_start:left_end]
        end_window = record.raw[right_start:right_end]

        start_variation = float(np.max(start_window) - np.min(start_window))
        end_variation = float(np.max(end_window) - np.min(end_window))
        if start_variation > noise_tolerance or end_variation > noise_tolerance:
            raise RuntimeError(
                f"[{record.filename}] Cannot apply drift correction: edge windows are not flat. "
                f"Start variation={start_variation:.2f}, end variation={end_variation:.2f}, "
                f"tolerance={noise_tolerance}."
            )

        y1 = float(np.mean(start_window))
        y2 = float(np.mean(end_window))
        x1 = 0.5 * (left_start + left_end - 1)
        x2 = 0.5 * (right_start + right_end - 1)
        if x2 <= x1:
            raise RuntimeError(f"[{record.filename}] Invalid correction anchor points.")

        indices = np.arange(len(record.raw), dtype=float)
        slope = (y2 - y1) / (x2 - x1)
        trend = y1 + slope * (indices - x1)

        corrected = record.raw - trend
        offset = (float(np.mean(corrected[left_start:left_end])) + float(np.mean(corrected[right_start:right_end]))) / 2.0
        corrected = corrected - offset

        record.corrected = corrected
        record.correction_window_time = float(window_time)
        return corrected

    def apply_lowpass_filter(self, record: SignalRecord, cutoff_freq: float = 250.0, order: int = 5) -> np.ndarray:
        if record.corrected is None:
            raise AttributeError(
                f"[{record.filename}] No corrected signal. Run drift_offset_correction before filtering."
            )

        nyquist = 0.5 * record.fs
        normal_cutoff = cutoff_freq / nyquist
        if not 0.0 < normal_cutoff < 1.0:
            raise ValueError(
                f"[{record.filename}] cutoff_freq={cutoff_freq} must be between 0 and Nyquist ({nyquist})."
            )

        b, a = butter(order, normal_cutoff, btype="low", analog=False)
        record.filtered = filtfilt(b, a, record.corrected)
        return record.filtered

    def zero_out_time_span(self, record: SignalRecord, start_time: float, end_time: float) -> None:
        if record.filtered is None:
            raise AttributeError(f"[{record.filename}] No filtered signal. Run apply_lowpass_filter first.")
        if end_time <= start_time:
            raise ValueError("end_time must be greater than start_time.")

        start_idx = max(0, int(start_time * record.fs))
        end_idx = min(len(record.filtered), int(end_time * record.fs))
        if start_idx >= end_idx:
            raise ValueError(f"[{record.filename}] Invalid interval [{start_time}, {end_time}].")

        record.filtered[start_idx:end_idx] = 0.0

    def keep_only_time_span(self, record: SignalRecord, start_time: float, end_time: float) -> None:
        if end_time <= start_time:
            raise ValueError("end_time must be greater than start_time.")

        start_idx = max(0, int(start_time * record.fs))
        end_idx = min(len(record.raw), int(end_time * record.fs))
        if start_idx >= end_idx:
            raise ValueError(f"[{record.filename}] Invalid interval [{start_time}, {end_time}].")

        record.raw = record.raw[start_idx:end_idx]
        if record.corrected is not None:
            record.corrected = record.corrected[start_idx:end_idx]
        if record.filtered is not None:
            record.filtered = record.filtered[start_idx:end_idx]

        self._rebuild_time_axis(record)

    def remove_time_span(self, record: SignalRecord, start_time: float, end_time: float) -> None:
        if end_time <= start_time:
            raise ValueError("end_time must be greater than start_time.")

        start_idx = max(0, int(start_time * record.fs))
        end_idx = min(len(record.raw), int(end_time * record.fs))
        if start_idx >= end_idx:
            raise ValueError(f"[{record.filename}] Invalid interval [{start_time}, {end_time}].")

        record.raw = np.concatenate((record.raw[:start_idx], record.raw[end_idx:]))
        if record.corrected is not None:
            record.corrected = np.concatenate((record.corrected[:start_idx], record.corrected[end_idx:]))
        if record.filtered is not None:
            record.filtered = np.concatenate((record.filtered[:start_idx], record.filtered[end_idx:]))

        self._rebuild_time_axis(record)
