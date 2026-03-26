from __future__ import annotations

import argparse
from typing import List

from core.filters import SignalFilter
from core.intervals import CutDetector
from core.models import SignalRecord
from core.reader import TDMSReader


def process_records(records: List[SignalRecord], args: argparse.Namespace) -> None:
    signal_filter = SignalFilter()
    detector = CutDetector()

    for record in records:
        detector.detect_cutting_interval_on_raw(
            record,
            trigger_threshold=args.trigger_threshold,
            margin_fraction=args.margin_fraction,
            min_cut_time_sec=args.min_cut_time_sec,
            expansion_time_sec=args.expansion_time_sec,
            correction_window_time=args.window_time,
        )

        signal_filter.drift_offset_correction(
            record,
            window_time=args.window_time,
            noise_tolerance=args.noise_tolerance,
            use_detected_regions=True,
        )

        signal_filter.apply_lowpass_filter(record, cutoff_freq=args.cutoff_freq, order=args.filter_order)

        if args.zero_start is not None and args.zero_end is not None:
            signal_filter.zero_out_time_span(record, args.zero_start, args.zero_end)

        detector.compute_average_cutting_force(
            record,
            trigger_threshold=args.trigger_threshold,
            margin_fraction=args.margin_fraction,
            use_filtered=True,
            min_cut_time_sec=args.min_cut_time_sec,
            expansion_time_sec=args.expansion_time_sec,
            correction_window_time=args.window_time,
            prefer_existing_interval=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Process TDMS files using modular SRP/MVC-ready core services.")
    parser.add_argument("path", help="Path to a TDMS file or a folder containing TDMS files.")
    parser.add_argument("--group", required=True, help="TDMS group name.")
    parser.add_argument("--channel", required=True, help="TDMS channel name.")
    parser.add_argument("--increment-key", default="wf_increment", help="Property name containing sampling increment.")

    parser.add_argument("--window-time", type=float, default=0.3)
    parser.add_argument("--noise-tolerance", type=float, default=10.0)
    parser.add_argument("--cutoff-freq", type=float, default=50.0)
    parser.add_argument("--filter-order", type=int, default=5)
    parser.add_argument("--trigger-threshold", type=float, default=5.0)
    parser.add_argument("--margin-fraction", type=float, default=0.1)
    parser.add_argument("--min-cut-time-sec", type=float, default=1.0)
    parser.add_argument("--expansion-time-sec", type=float, default=0.3)
    parser.add_argument("--zero-start", type=float, default=None, help="Optional start time for zeroing filtered signal.")
    parser.add_argument("--zero-end", type=float, default=None, help="Optional end time for zeroing filtered signal.")

    args = parser.parse_args()

    reader = TDMSReader(group_name=args.group, channel_name=args.channel, increment_key=args.increment_key)
    records = reader.read(args.path)
    if not records:
        print("No TDMS records found.")
        return

    process_records(records, args)

    print(f"Processed {len(records)} record(s):")
    for record in records:
        mean = "n/a" if record.mean_force_auto is None else f"{record.mean_force_auto:.4f}"
        print(f"- {record.filename}: mean_force_auto={mean}")


if __name__ == "__main__":
    main()
