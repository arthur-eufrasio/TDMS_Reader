from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class SignalRecord:
    """Container for all signal data and derived processing metadata for one TDMS file."""

    # Identity
    filename: str

    # Base signal data
    fs: float
    ts: float
    raw: np.ndarray
    t_full: np.ndarray

    # Processed signals
    corrected: Optional[np.ndarray] = None
    filtered: Optional[np.ndarray] = None

    # Trigger/cut interval indices
    tri_start_idx: Optional[int] = None
    tri_end_idx: Optional[int] = None
    steady_start_idx: Optional[int] = None
    steady_end_idx: Optional[int] = None
    expanded_start_idx: Optional[int] = None
    expanded_end_idx: Optional[int] = None

    # Drift-correction support windows (indices)
    corr_left_start_idx: Optional[int] = None
    corr_left_end_idx: Optional[int] = None
    corr_right_start_idx: Optional[int] = None
    corr_right_end_idx: Optional[int] = None

    # Trigger/cut interval times
    tri_start_time: Optional[float] = None
    tri_end_time: Optional[float] = None
    steady_start_time: Optional[float] = None
    steady_end_time: Optional[float] = None
    expanded_start_time: Optional[float] = None
    expanded_end_time: Optional[float] = None

    # Drift-correction support windows (times)
    corr_left_start_time: Optional[float] = None
    corr_left_end_time: Optional[float] = None
    corr_right_start_time: Optional[float] = None
    corr_right_end_time: Optional[float] = None

    # Manual selection metadata
    manual_start_idx: Optional[int] = None
    manual_end_idx: Optional[int] = None
    manual_start_time: Optional[float] = None
    manual_end_time: Optional[float] = None

    # Computed force values
    mean_force_auto: Optional[float] = None
    mean_force_manual: Optional[float] = None

    # Backward compatibility with current processor naming
    mean_force: Optional[float] = None

    # Detection/correction parameters persisted per file
    correction_window_time: Optional[float] = None
    min_cut_time_sec: Optional[float] = None
    expansion_time_sec: Optional[float] = None

    def get_active_signal(self) -> np.ndarray:
        """Return the best available signal representation.

        Priority: filtered -> corrected -> raw.
        """
        if self.filtered is not None:
            return self.filtered
        if self.corrected is not None:
            return self.corrected
        return self.raw
