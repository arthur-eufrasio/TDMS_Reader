from __future__ import annotations

import glob
import os
from typing import Dict, List, Tuple

import numpy as np
from nptdms import TdmsFile

from .models import SignalRecord


class TDMSReader:
    """Read TDMS files and materialize them as SignalRecord objects."""

    def __init__(self, group_name: str, channel_name: str, increment_key: str = "wf_increment") -> None:
        self.group_name = group_name
        self.channel_name = channel_name
        self.increment_key = increment_key

    @staticmethod
    def resolve_tdms_paths(path: str) -> List[str]:
        if os.path.isfile(path):
            return [path]
        if os.path.isdir(path):
            files = sorted(glob.glob(os.path.join(path, "*.tdms")))
            return files
        raise FileNotFoundError(f"Path does not exist: {path}")

    @staticmethod
    def discover_groups_and_channels(path: str) -> Dict[str, List[str]]:
        channels_by_group: Dict[str, set[str]] = {}
        filepaths = TDMSReader.resolve_tdms_paths(path)

        if not filepaths:
            raise FileNotFoundError(f"No TDMS files found at: {path}")

        for filepath in filepaths:
            tdms = TdmsFile.read(filepath)
            for group in tdms.groups():
                channels_by_group.setdefault(group.name, set())
                for channel in group.channels():
                    channels_by_group[group.name].add(channel.name)

        return {group: sorted(list(channels)) for group, channels in channels_by_group.items()}

    def read(self, path: str) -> List[SignalRecord]:
        filepaths = self.resolve_tdms_paths(path)
        if not filepaths:
            raise FileNotFoundError(f"No TDMS files found at: {path}")

        records: List[SignalRecord] = []
        for filepath in filepaths:
            raw, fs, ts = self._read_data(filepath)
            filename = os.path.basename(filepath)
            t_full = np.arange(len(raw), dtype=float) * ts
            records.append(
                SignalRecord(
                    filename=filename,
                    fs=float(fs),
                    ts=float(ts),
                    raw=raw,
                    t_full=t_full,
                )
            )
        return records

    def _read_data(self, filepath: str) -> Tuple[np.ndarray, float, float]:
        tdms = TdmsFile.read(filepath)
        filename = os.path.basename(filepath)

        try:
            group = tdms[self.group_name]
        except KeyError as exc:
            available_groups = [g.name for g in tdms.groups()]
            raise KeyError(
                f"[{filename}] Group '{self.group_name}' not found. Available groups: {available_groups}"
            ) from exc

        try:
            channel_obj = group[self.channel_name]
        except KeyError as exc:
            available_channels = [c.name for c in group.channels()]
            raise KeyError(
                f"[{filename}] Channel '{self.channel_name}' not found in group '{self.group_name}'. "
                f"Available channels: {available_channels}"
            ) from exc

        raw = np.asarray(channel_obj[:], dtype=float)

        try:
            ts = float(channel_obj.properties[self.increment_key])
        except KeyError as exc:
            available_props = list(channel_obj.properties.keys())
            raise KeyError(
                f"[{filename}] Channel '{self.channel_name}' does not have property "
                f"'{self.increment_key}'. Available properties: {available_props}"
            ) from exc

        if ts <= 0:
            raise ValueError(f"[{filename}] Invalid sampling interval '{ts}'.")

        fs = 1.0 / ts
        return raw, fs, ts
