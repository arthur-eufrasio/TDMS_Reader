import os
import glob
import numpy as np
from scipy.signal import butter, filtfilt
from nptdms import TdmsFile

class AutomaticSignalProcessor:
    """
    A class to automatically read, process, and extract signal data from one or multiple TDMS files.

    This class parses a given TDMS file (or all TDMS files in a folder) using predefined 
    arguments, extracting the raw signal data, sampling frequency, and a corresponding 
    time vector without requiring user interaction. 
    
    Data arrays are stored in dictionaries where the keys are the individual file paths.

    Attributes:
        path (str): The path to the TDMS file or directory containing TDMS files.
        filepaths (list): A list of TDMS file paths being processed.
        group_name (str): The name of the target group.
        channel_name (str): The name of the target channel.
        increment_key (str): The property key used to find the time increment (dt).
        data (dict): A nested dictionary storing all extracted and processed signals. 
            Structured as: `data[filename] = {'raw': ..., 'fs': ..., 'ts': ..., 't_full': ..., 'corrected': ..., 'filtered': ...}`
    """
    def __init__(self, path, group_name='Device-1', channel_name=None, increment_key="wf_increment"):
        """
        Initializes the AutomaticSignalProcessor, discovers the TDMS files, and extracts the signal data.

        Args:
            path (str): Path to a single .tdms file or a directory containing .tdms files.
            group_name (str): The name of the group to read. Defaults to 'Device-1'.
            channel_name (str): The name of the channel to read.
            increment_key (str, optional): The TDMS property key containing the sampling 
                interval. Defaults to "wf_increment".
        """
        self.processor_name = os.path.basename(os.path.normpath(path)) if os.path.isdir(path) else os.path.basename(path)
        self.path = path
        self.group_name = group_name
        self.channel_name = channel_name
        self.increment_key = increment_key
        
        if os.path.isfile(self.path):
            self.filepaths = [self.path]
        elif os.path.isdir(self.path):
            self.filepaths = glob.glob(os.path.join(self.path, "*.tdms"))
            if not self.filepaths:
                raise FileNotFoundError(f"No TDMS files found in directory: {self.path}")
        else:
            raise FileNotFoundError(f"Path does not exist: {self.path}")

        self.data = {}
        
        for fp in self.filepaths:
            file_name = os.path.basename(fp)
            raw, fs, ts = self._read_data(fp)
            self.data[file_name] = {
                'raw': raw,
                'fs': fs,
                'ts': ts,
                't_full': np.arange(len(raw)) * ts
            }

    def _normalize_target_files(self, target_files=None):
        """
        Normalizes user input for file selection.

        Args:
            target_files (None, str, or list[str]): Target files.

        Returns:
            list[str]: Existing filenames in self.data.
        """
        if target_files is None:
            return list(self.data.keys())
        if isinstance(target_files, str):
            target_files = [target_files]
        return [f for f in target_files if f in self.data]

    def _rebuild_time_axis(self, file_data):
        """
        Rebuilds t_full after any edit that changes signal length.
        """
        length = len(file_data['raw'])
        file_data['t_full'] = np.arange(length) * file_data['ts']

    def _read_data(self, filepath):
        """
        Extracts the group, channel, raw data, sampling frequency, and time step for a specific file.
        Validates the existence of the provided group, channel, and increment key.

        Args:
            filepath (str): The path to the specific TDMS file being read.

        Returns:
            tuple: A tuple containing:
                - data (numpy.ndarray): The raw signal data.
                - fs_val (float): The sampling frequency (1 / time step).
                - ts_val (float): The time step increment.

        Raises:
            KeyError: If the specified group, channel, or `increment_key` is not found.
        """
        tdms = TdmsFile.read(filepath)
        filename = os.path.basename(filepath)

        try:
            group = tdms[self.group_name]
        except KeyError:
            available_groups = [g.name for g in tdms.groups()]
            raise KeyError(
                f"[{filename}] Group '{self.group_name}' not found in the TDMS file. "
                f"Available groups are: {available_groups}"
            )

        try:
            channel_obj = group[self.channel_name]
        except KeyError:
            available_channels = [c.name for c in group.channels()]
            raise KeyError(
                f"[{filename}] Channel '{self.channel_name}' not found in group '{self.group_name}'. "
                f"Available channels are: {available_channels}"
            )

        data = np.asarray(channel_obj[:])
        
        try:
            ts_val = channel_obj.properties[self.increment_key]
        except KeyError:
            available_props = list(channel_obj.properties.keys())
            raise KeyError(
                f"[{filename}] Channel '{self.channel_name}' does not have the '{self.increment_key}' property. "
                f"Available properties are: {available_props}"
            )
            
        fs_val = 1 / ts_val
        return data, fs_val, ts_val
    
    def drift_offset_correction(self, window_time=0.3, noise_tolerance=5.0, target_files=None):
        """
        Removes linear drift and DC offset from the raw signals across all files.
        
        Evaluates the variation in the edge windows (based on time) to ensure 
        the machine is idle (flat curve) before applying the correction.

        Args:
            window_time (float, optional): Time window in seconds to average at the edges. Defaults to 0.3.
            noise_tolerance (float, optional): Maximum allowed peak-to-peak variation 
                                               inside the window. Defaults to 5.0.
            
        Raises:
            RuntimeError: If the edges show cutting activity or a signal is too short.
        """
        filenames = self._normalize_target_files(target_files)
        if not filenames:
            raise ValueError("No valid target files provided for drift correction.")

        for filename in filenames:
            file_data = self.data[filename]
            raw_data = file_data['raw']
            fs = file_data['fs']
            window = int(window_time * fs)
            
            start_window = raw_data[:window]
            end_window = raw_data[-window:]
            
            start_variation = np.max(start_window) - np.min(start_window)
            end_variation = np.max(end_window) - np.min(end_window)
            
            if start_variation > noise_tolerance or end_variation > noise_tolerance:
                raise RuntimeError(
                    f"[{filename}] Cannot apply drift correction: The signal is not flat at the edges. "
                    f"Start variation: {start_variation:.2f}, End variation: {end_variation:.2f} "
                    f"(Tolerance is {noise_tolerance})."
                )

            corrected = raw_data.copy()
            
            y1 = np.mean(corrected[:window])
            y2 = np.mean(corrected[-window:])
            
            dy = y2 - y1
            dx = len(corrected) - 1
            dy_incr = dy / dx

            indices = np.arange(len(corrected))
            corrected -= indices * dy_incr

            offset = (np.mean(corrected[:window]) + np.mean(corrected[-window:])) / 2
            corrected -= offset

            self.data[filename]['corrected'] = corrected
            
    def apply_lowpass_filter(self, cutoff_freq=250, order=5, target_files=None):
        """
        Applies a zero-phase Butterworth low-pass filter to all corrected signals.
        
        Note: The `drift_offset_correction` method must be called before applying 
        this filter, as it relies on the 'corrected' key being present in the data dict.

        Args:
            cutoff_freq (float): The cutoff frequency for the filter in Hz. Defaults to 250.
            order (int, optional): The order of the Butterworth filter. Defaults to 5.
            
        Raises:
            AttributeError: If `corrected` data does not exist for a file.
        """
        filenames = self._normalize_target_files(target_files)
        if not filenames:
            raise ValueError("No valid target files provided for filtering.")

        if not any('corrected' in self.data[f] for f in filenames):
            raise AttributeError("No 'corrected' data found for selected files. Call 'drift_offset_correction' first.")

        for filename in filenames:
            file_data = self.data[filename]
            if 'corrected' not in file_data:
                continue
                
            fs = file_data['fs']
            nyquist = 0.5 * fs
            normal_cutoff = cutoff_freq / nyquist
            
            b, a = butter(order, normal_cutoff, btype='low', analog=False)
            self.data[filename]['filtered'] = filtfilt(b, a, file_data['corrected'])

    def zero_out_time_span(self, start_time, end_time, target_files=None):
        """
        Sets the amplitude of the 'filtered' signal to exactly zero within a specified time span.
        Useful for manually muting sensor anomalies or known noise intervals.

        Args:
            start_time (float): The beginning of the time span in seconds.
            end_time (float): The end of the time span in seconds.
            target_files (str or list of str, optional): A specific filename or list of filenames 
                                                         (e.g., 'cut_01.tdms'). If None, applies to all files.
        """
        for filename in self._normalize_target_files(target_files):
            file_data = self.data[filename]
            
            if 'filtered' not in file_data:
                print(f"Warning: No 'filtered' signal found for '{filename}'. Run 'apply_lowpass_filter' first. Skipping.")
                continue
                
            fs = file_data['fs']
            signal_length = len(file_data['filtered'])
            
            # Convert the requested seconds into array indices
            start_idx = max(0, int(start_time * fs))
            end_idx = min(signal_length, int(end_time * fs))
            
            if start_idx >= end_idx:
                print(f"Warning: Invalid time span [{start_time}s to {end_time}s] for '{filename}'. Skipping.")
                continue
                
            # Set the span to zero
            file_data['filtered'][start_idx:end_idx] = 0.0

    def compute_manual_force_in_time_span(self, start_time, end_time, target_files=None, use_filtered=True):
        """
        Computes the mean force directly from a user-defined time interval.

        This does not depend on trigger detection. Useful for GUI/manual workflows
        where the user selects the force evaluation region interactively.

        Args:
            start_time (float): Interval start in seconds.
            end_time (float): Interval end in seconds.
            target_files (str or list[str], optional): Files to process. If None, all files are used.
            use_filtered (bool): Prefer 'filtered' signal when available.

        Returns:
            dict: {filename: mean_force_manual}
        """
        if end_time <= start_time:
            raise ValueError("end_time must be greater than start_time.")

        results = {}
        for filename in self._normalize_target_files(target_files):
            file_data = self.data[filename]

            if use_filtered and 'filtered' in file_data:
                signal = file_data['filtered']
            elif 'corrected' in file_data:
                signal = file_data['corrected']
            else:
                signal = file_data['raw']

            fs = file_data['fs']
            start_idx = max(0, int(start_time * fs))
            end_idx = min(len(signal), int(end_time * fs))

            if start_idx >= end_idx:
                raise ValueError(
                    f"[{filename}] Invalid interval [{start_time}, {end_time}] after bounds clipping."
                )

            segment = signal[start_idx:end_idx]
            mean_force = float(np.mean(segment))

            file_data['manual_start_idx'] = start_idx
            file_data['manual_end_idx'] = end_idx
            file_data['manual_start_time'] = float(file_data['t_full'][start_idx])
            file_data['manual_end_time'] = float(file_data['t_full'][end_idx - 1])
            file_data['mean_force_manual'] = mean_force

            results[filename] = mean_force

        return results

    def keep_only_time_span(self, start_time, end_time, target_files=None):
        """
        Trims each target file so only the selected time span remains.

        The method slices all available signal representations ('raw', 'corrected',
        and 'filtered') and rebuilds the time axis from zero.
        """
        if end_time <= start_time:
            raise ValueError("end_time must be greater than start_time.")

        signal_keys = ('raw', 'corrected', 'filtered')

        for filename in self._normalize_target_files(target_files):
            file_data = self.data[filename]
            start_idx = max(0, int(start_time * file_data['fs']))
            end_idx = min(len(file_data['raw']), int(end_time * file_data['fs']))

            if start_idx >= end_idx:
                raise ValueError(f"[{filename}] Invalid interval [{start_time}, {end_time}].")

            for key in signal_keys:
                if key in file_data:
                    file_data[key] = file_data[key][start_idx:end_idx]

            self._rebuild_time_axis(file_data)

    def remove_time_span(self, start_time, end_time, target_files=None):
        """
        Removes a selected interval and stitches the remaining signal together.

        The method edits 'raw', 'corrected', and 'filtered' when present, then
        rebuilds the time axis from zero for consistency.
        """
        if end_time <= start_time:
            raise ValueError("end_time must be greater than start_time.")

        signal_keys = ('raw', 'corrected', 'filtered')

        for filename in self._normalize_target_files(target_files):
            file_data = self.data[filename]
            start_idx = max(0, int(start_time * file_data['fs']))
            end_idx = min(len(file_data['raw']), int(end_time * file_data['fs']))

            if start_idx >= end_idx:
                raise ValueError(f"[{filename}] Invalid interval [{start_time}, {end_time}].")

            for key in signal_keys:
                if key in file_data:
                    file_data[key] = np.concatenate((file_data[key][:start_idx], file_data[key][end_idx:]))

            self._rebuild_time_axis(file_data)

    def _detect_cutting_interval(self, signal, t_full, trigger_threshold, margin_fraction, filename, min_gap_sec=1.0):
        """
        Auxiliary method to find the indices and times of the FIRST active cutting interval
        and its steady-state segment, ignoring any subsequent cuts in the same file.
        
        Args:
            signal (numpy.ndarray): The signal array to evaluate.
            t_full (numpy.ndarray): The corresponding time array.
            trigger_threshold (float): Amplitude threshold in N to detect cutting.
            margin_fraction (float): Fraction of the cut to discard at the edges.
            filename (str): The name of the file being processed (for error reporting).
            min_gap_sec (float): Minimum time in seconds below the threshold to be considered 
                                 the end of a cut. Defaults to 1.0s.
            
        Returns:
            dict: A dictionary containing the start/end indices and times for the 
                  FIRST trigger interval and its steady-state interval.
        """
        active_idx = np.where(np.abs(signal) > trigger_threshold)[0]

        if active_idx.size == 0:
            raise RuntimeError(
                f"[{filename}] No cutting interval found with trigger_threshold={trigger_threshold}."
            )
            
        fs = 1.0 / (t_full[1] - t_full[0])
        min_gap_samples = int(min_gap_sec * fs)
        
        gaps = np.where(np.diff(active_idx) > min_gap_samples)[0]
        
        tri_start_idx = int(active_idx[0])
        
        if gaps.size > 0:
            first_cut_end_idx_in_active = gaps[0]
            tri_end_idx = int(active_idx[first_cut_end_idx_in_active])
        else:
            tri_end_idx = int(active_idx[-1])

        cut_len = tri_end_idx - tri_start_idx + 1
        margin = int(margin_fraction * cut_len)

        steady_start_idx = tri_start_idx + margin
        steady_end_idx = tri_end_idx - margin

        if steady_end_idx <= steady_start_idx:
            raise RuntimeError(
                f"[{filename}] The first cut is too short for margin_fraction={margin_fraction:.2f}."
            )

        return {
            'tri_start_idx': tri_start_idx,
            'tri_end_idx': tri_end_idx,
            'steady_start_idx': steady_start_idx,
            'steady_end_idx': steady_end_idx,
            'tri_start_time': float(t_full[tri_start_idx]),
            'tri_end_time': float(t_full[tri_end_idx]),
            'steady_start_time': float(t_full[steady_start_idx]),
            'steady_end_time': float(t_full[steady_end_idx])
        }
            
    def compute_average_cutting_force(self,
                                      trigger_threshold=20.0,
                                      margin_fraction=0.2,
                                      use_filtered=True,
                                      target_files=None):
        """
        Detects the cutting interval via a simple amplitude threshold ('trigger')
        and computes the average cutting force in the central (steady-state)
        part of the cut for each file using an auxiliary detection method.

        Args:
            trigger_threshold (float): Amplitude threshold in N used to detect
                when cutting is active. Defaults to 20.0.
            margin_fraction (float): Fraction of the trigger-to-trigger interval
                to discard at the start and end. Defaults to 0.2.
            use_filtered (bool): If True and a 'filtered' signal exists, use it;
                otherwise fall back to 'corrected'. Defaults to True.
        """
        if not (0.0 <= margin_fraction < 0.5):
            raise ValueError("margin_fraction must be in [0.0, 0.5).")

        filenames = self._normalize_target_files(target_files)
        if not filenames:
            raise ValueError("No valid target files provided for force computation.")

        for filename in filenames:
            file_data = self.data[filename]
            if use_filtered and 'filtered' in file_data:
                signal = file_data['filtered']
            elif 'corrected' in file_data:
                signal = file_data['corrected']
            else:
                raise AttributeError(
                    f"[{filename}] No 'filtered' or 'corrected' signal available. "
                    "Run 'drift_offset_correction' (and optionally 'apply_lowpass_filter') first."
                )

            interval_data = self._detect_cutting_interval(
                signal=signal, 
                t_full=file_data['t_full'], 
                trigger_threshold=trigger_threshold, 
                margin_fraction=margin_fraction, 
                filename=filename
            )

            steady_segment = signal[interval_data['steady_start_idx']:interval_data['steady_end_idx']]
            mean_force = float(np.mean(steady_segment))

            self.data[filename].update(interval_data)
            self.data[filename]['mean_force'] = mean_force

    def get_force_results(self):
        """
        Retrieves the mean force for all processed files.

        Returns:
            dict: A dictionary where each key is a file path and the value is the mean_force.
        """
        results = {}
        for filename, file_data in self.data.items():
            if 'mean_force' in file_data:
                results[filename] = file_data['mean_force']
        return results

    def merge_cutting_signals(self, trigger_threshold=20.0, margin_fraction=0.2, use_filtered=True):
        """
        Merges the STEADY-STATE portions of the signals from all processed files 
        into a single, continuous signal to analyze long-term trends (e.g., tool wear).

        The files are sorted alphabetically by filename to ensure chronological 
        concatenation (assuming sequential naming like 'cut_01.tdms', 'cut_02.tdms').
        Only the data between 'steady_start_idx' and 'steady_end_idx' is kept.
        If the indices have not been computed yet, this method will calculate them.

        Args:
            trigger_threshold (float): Amplitude threshold in N to detect cutting (used if not already computed).
            margin_fraction (float): Fraction of the cut to discard at the edges (used if not already computed).
            use_filtered (bool): If True, uses the 'filtered' signal for merging. 
                                 Otherwise, uses 'corrected'. Defaults to True.

        Returns:
            dict: The merged data dictionary containing the combined steady-state signal and time vector.
        """
        merged_segments = []
        
        sorted_filenames = sorted(self.data.keys(), key=lambda x: int(x.split('_')[1].split('.')[0]))
        
        if not sorted_filenames:
            raise ValueError("No data available to merge.")
            
        fs = self.data[sorted_filenames[0]]['fs']

        for filename in sorted_filenames:
            file_data = self.data[filename]
            
            if use_filtered and 'filtered' in file_data:
                signal = file_data['filtered']
            elif 'corrected' in file_data:
                signal = file_data['corrected']
            else:
                raise AttributeError(f"[{filename}] No valid signal found to merge. Run 'drift_offset_correction' first.")

            if 'steady_start_idx' not in file_data or 'steady_end_idx' not in file_data:
                interval_data = self._detect_cutting_interval(
                    signal=signal, 
                    t_full=file_data['t_full'], 
                    trigger_threshold=trigger_threshold, 
                    margin_fraction=margin_fraction, 
                    filename=filename
                )
                self.data[filename].update(interval_data)

            start_idx = file_data['steady_start_idx']
            end_idx = file_data['steady_end_idx']
            
            steady_segment = signal[start_idx:end_idx]
            merged_segments.append(steady_segment)

        merged_signal = np.concatenate(merged_segments)
        
        t_merged = np.arange(len(merged_signal)) / fs

        self.merged_data = {
            'signal': merged_signal,
            't_full': t_merged,
            'fs': fs,
            'source_files': sorted_filenames
        }
        
        return self.merged_data