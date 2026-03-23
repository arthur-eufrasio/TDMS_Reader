import os
from processor.automatic_signal_processor import AutomaticSignalProcessor
from utils.visualization import *

base_path = 'C:\\Users\\adam-jd1r2h3ttnmecz9\\Desktop\\arthur\\temp\\tmds_files\\ivo\\test'

processor = AutomaticSignalProcessor(
    path=base_path, 
    group_name='Part Waveform', 
    channel_name='Fy'
)

processor.drift_offset_correction(window_time=0.3, noise_tolerance=26.0)
processor.apply_lowpass_filter(cutoff_freq=10, order=5)
processor.zero_out_time_span(start_time=0.0, end_time=2.09)
processor.compute_average_cutting_force(trigger_threshold=5.0,margin_fraction=0.1)

plot_processed_signals(processor)
