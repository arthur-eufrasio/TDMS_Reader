from __future__ import annotations

import numpy as np

from .models import SignalRecord


class CutDetector:
    """Detect cutting regions and compute force metrics on SignalRecord objects."""

    def _detect_cutting_interval(
        self,
        signal: np.ndarray,
        t_full: np.ndarray,
        trigger_threshold: float,
        margin_fraction: float,
        filename: str,
        min_cut_time_sec: float = 0.1,
        expansion_time_sec: float = 0.0,
        correction_window_time: float = 0.3,
    ) -> dict[str, float | int]:
        active_idx = np.where(np.abs(signal) > trigger_threshold)[0]
        if active_idx.size == 0:
            raise RuntimeError(f"[{filename}] No cutting interval found with trigger_threshold={trigger_threshold}.")

        if len(t_full) < 2:
            raise RuntimeError(f"[{filename}] Signal is too short for interval detection.")

        fs = 1.0 / float(t_full[1] - t_full[0])
        min_gap_samples = 1
        min_cut_samples = max(1, int(min_cut_time_sec * fs))
        expansion_samples = int(expansion_time_sec * fs)
        corr_window_samples = max(2, int(correction_window_time * fs))

        gaps = np.where(np.diff(active_idx) > min_gap_samples)[0]

        trigger_regions: list[tuple[int, int]] = []
        seg_start_pos = 0
        for gap_pos in gaps:
            seg_end_pos = int(gap_pos)
            s_idx = int(active_idx[seg_start_pos])
            e_idx = int(active_idx[seg_end_pos])
            trigger_regions.append((s_idx, e_idx))
            seg_start_pos = int(gap_pos + 1)

        trigger_regions.append((int(active_idx[seg_start_pos]), int(active_idx[-1])))

        tri_start_idx = None
        tri_end_idx = None
        for s_idx, e_idx in trigger_regions:
            if (e_idx - s_idx + 1) >= min_cut_samples:
                tri_start_idx = s_idx
                tri_end_idx = e_idx
                break

        if tri_start_idx is None or tri_end_idx is None:
            raise RuntimeError(f"[{filename}] No cutting interval found with minimum cut time {min_cut_time_sec}s.")

        cut_len = tri_end_idx - tri_start_idx + 1
        margin = int(margin_fraction * cut_len)

        steady_start_idx = tri_start_idx + margin
        steady_end_idx = tri_end_idx - margin
        if steady_end_idx <= steady_start_idx:
            raise RuntimeError(f"[{filename}] The first cut is too short for margin_fraction={margin_fraction:.2f}.")

        expanded_start_idx = max(0, tri_start_idx - expansion_samples)
        expanded_end_idx = min(len(signal) - 1, tri_end_idx + expansion_samples)

        if (expanded_end_idx - expanded_start_idx + 1) < 2 * corr_window_samples:
            raise RuntimeError(
                f"[{filename}] Expanded interval is too short for correction_window_time={correction_window_time}s."
            )

        corr_left_start_idx = expanded_start_idx
        corr_left_end_idx = expanded_start_idx + corr_window_samples
        corr_right_end_idx = expanded_end_idx + 1
        corr_right_start_idx = corr_right_end_idx - corr_window_samples

        return {
            "tri_start_idx": tri_start_idx,
            "tri_end_idx": tri_end_idx,
            "steady_start_idx": steady_start_idx,
            "steady_end_idx": steady_end_idx,
            "tri_start_time": float(t_full[tri_start_idx]),
            "tri_end_time": float(t_full[tri_end_idx]),
            "steady_start_time": float(t_full[steady_start_idx]),
            "steady_end_time": float(t_full[steady_end_idx]),
            "expanded_start_idx": expanded_start_idx,
            "expanded_end_idx": expanded_end_idx,
            "expanded_start_time": float(t_full[expanded_start_idx]),
            "expanded_end_time": float(t_full[expanded_end_idx]),
            "corr_left_start_idx": corr_left_start_idx,
            "corr_left_end_idx": corr_left_end_idx,
            "corr_right_start_idx": corr_right_start_idx,
            "corr_right_end_idx": corr_right_end_idx,
            "corr_left_start_time": float(t_full[corr_left_start_idx]),
            "corr_left_end_time": float(t_full[corr_left_end_idx - 1]),
            "corr_right_start_time": float(t_full[corr_right_start_idx]),
            "corr_right_end_time": float(t_full[corr_right_end_idx - 1]),
            "min_cut_time_sec": float(min_cut_time_sec),
            "expansion_time_sec": float(expansion_time_sec),
            "correction_window_time": float(correction_window_time),
        }

    def detect_cutting_interval_on_raw(
        self,
        record: SignalRecord,
        trigger_threshold: float = 20.0,
        margin_fraction: float = 0.2,
        min_cut_time_sec: float = 0.0,
        expansion_time_sec: float = 0.0,
        correction_window_time: float = 0.3,
    ) -> None:
        if not (0.0 <= margin_fraction < 0.5):
            raise ValueError("margin_fraction must be in [0.0, 0.5).")

        interval_data = self._detect_cutting_interval(
            signal=record.raw,
            t_full=record.t_full,
            trigger_threshold=trigger_threshold,
            margin_fraction=margin_fraction,
            filename=record.filename,
            min_cut_time_sec=min_cut_time_sec,
            expansion_time_sec=expansion_time_sec,
            correction_window_time=correction_window_time,
        )

        for key, value in interval_data.items():
            setattr(record, key, value)

    def compute_average_cutting_force(
        self,
        record: SignalRecord,
        trigger_threshold: float = 20.0,
        margin_fraction: float = 0.2,
        use_filtered: bool = True,
        min_cut_time_sec: float = 0.0,
        expansion_time_sec: float = 0.0,
        correction_window_time: float = 0.3,
        prefer_existing_interval: bool = True,
    ) -> float:
        if not (0.0 <= margin_fraction < 0.5):
            raise ValueError("margin_fraction must be in [0.0, 0.5).")

        if use_filtered and record.filtered is not None:
            signal = record.filtered
        elif record.corrected is not None:
            signal = record.corrected
        else:
            signal = record.raw

        has_existing = record.steady_start_idx is not None and record.steady_end_idx is not None
        if has_existing and prefer_existing_interval:
            steady_start_idx = int(record.steady_start_idx)
            steady_end_idx = int(record.steady_end_idx)
        else:
            interval_data = self._detect_cutting_interval(
                signal=signal,
                t_full=record.t_full,
                trigger_threshold=trigger_threshold,
                margin_fraction=margin_fraction,
                filename=record.filename,
                min_cut_time_sec=min_cut_time_sec,
                expansion_time_sec=expansion_time_sec,
                correction_window_time=correction_window_time,
            )
            for key, value in interval_data.items():
                setattr(record, key, value)
            steady_start_idx = int(record.steady_start_idx)
            steady_end_idx = int(record.steady_end_idx)

        steady_segment = signal[steady_start_idx:steady_end_idx]
        mean_force = float(np.mean(steady_segment))

        record.mean_force_auto = mean_force
        record.mean_force = mean_force
        return mean_force

    def compute_manual_force_in_time_span(
        self,
        record: SignalRecord,
        start_time: float,
        end_time: float,
        use_filtered: bool = True,
    ) -> float:
        if end_time <= start_time:
            raise ValueError("end_time must be greater than start_time.")

        if use_filtered and record.filtered is not None:
            signal = record.filtered
        elif record.corrected is not None:
            signal = record.corrected
        else:
            signal = record.raw

        start_idx = max(0, int(start_time * record.fs))
        end_idx = min(len(signal), int(end_time * record.fs))
        if start_idx >= end_idx:
            raise ValueError(f"[{record.filename}] Invalid interval [{start_time}, {end_time}] after clipping.")

        segment = signal[start_idx:end_idx]
        mean_force = float(np.mean(segment))

        record.manual_start_idx = start_idx
        record.manual_end_idx = end_idx
        record.manual_start_time = float(record.t_full[start_idx])
        record.manual_end_time = float(record.t_full[end_idx - 1])
        record.mean_force_manual = mean_force

        return mean_force
