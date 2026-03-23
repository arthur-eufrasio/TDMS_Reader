import matplotlib.pyplot as plt
import numpy as np
import math
import scipy.stats as stats
import os

def plot_processed_signals(processors, target_files=None, show_raw=True, show_corrected=True, show_filtered=True):
    """
    Plots the raw, corrected, and filtered signals along with cutting intervals
    for each file processed and stored in the processor_data dictionary.
    Creates a separate figure for each processor provided.
    
    Args:
        processors (AutomaticSignalProcessor or list): A single instance or a list of processors containing the data to plot.
        target_files (str or list of str, optional): A specific filename or list of filenames to plot 
                                                     (e.g., 'cut_01.tdms'). If None, plots all files.
        show_raw (bool, optional): Whether to plot the raw signal. Defaults to True.
        show_corrected (bool, optional): Whether to plot the drift-corrected signal. Defaults to True.
        show_filtered (bool, optional): Whether to plot the low-pass filtered signal. Defaults to True.
    """
    # 1. Standardize inputs to lists so we can easily loop through them
    if not isinstance(processors, (list, tuple)):
        processors = [processors]
        
    if target_files is not None and isinstance(target_files, str):
        target_files = [target_files]

    # 2. Loop through each processor instance
    for p_idx, processor in enumerate(processors):
        # Dynamically fetch the processor's name (fallback to index if it doesn't exist)
        proc_name = getattr(processor, 'processor_name', f"Processor {p_idx + 1}")
        
        processor_data = processor.data
        all_files = list(processor_data.keys())
        
        # Filter the files based on the user's input for THIS specific processor
        if target_files is not None:
            filepaths = [f for f in target_files if f in all_files]
            if not filepaths:
                print(f"{proc_name}: None of the requested target files were found. Skipping.")
                continue
        else:
            filepaths = all_files

        num_files = len(filepaths)
        
        if num_files == 0:
            print(f"{proc_name}: No data available to plot. Skipping.")
            continue

        ncols = math.ceil(math.sqrt(num_files))
        nrows = math.ceil(num_files / ncols)        
        fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 5, nrows * 3.5))
        
        # Name the window itself if you are using a popup GUI (like Qt or Tkinter)
        if hasattr(fig.canvas.manager, 'set_window_title'):
            fig.canvas.manager.set_window_title(f"Data for {proc_name}")

        # 3. Flatten axes to a 1D array/list to handle single plots, 1D grids, and 2D grids safely
        if hasattr(axes, 'flatten'):
            axes = axes.flatten()
        elif not isinstance(axes, (list, tuple)):
            axes = [axes]

        # 4. Plot each file dynamically on its own axis
        for ax, filename in zip(axes, filepaths):
            file_data = processor_data[filename]
            time_array = file_data['t_full']
            
            # Plot signals based on the boolean toggles
            if 'raw' in file_data and show_raw:
                ax.plot(time_array, file_data['raw'], label='Raw', color='lightblue', alpha=0.5)
            
            if 'corrected' in file_data and show_corrected:
                ax.plot(time_array, file_data['corrected'], label='Corrected', color='orange', alpha=0.7)
                
            if 'filtered' in file_data and show_filtered:
                ax.plot(time_array, file_data['filtered'], label='Filtered', color='blue', alpha=1.0)
            
            # Overlay the calculated cutting intervals and mean force if available
            if 'mean_force' in file_data:
                tri_start = file_data['tri_start_time']
                tri_end = file_data['tri_end_time']
                steady_start = file_data['steady_start_time']
                steady_end = file_data['steady_end_time']
                mean_force = file_data['mean_force']
                
                # Shaded region for the full trigger cut
                ax.axvspan(tri_start, tri_end, color='gray', alpha=0.15, label='Trigger Interval')
                
                # Shaded region for the steady state cut
                ax.axvspan(steady_start, steady_end, color='green', alpha=0.25, label='Steady Interval')
                
                # Dashed red line for the mean force across the steady region
                ax.plot([steady_start, steady_end], [mean_force, mean_force], 
                        color='red', linewidth=2.5, linestyle='--', label=f"Mean: {mean_force:.1f} N")

            # Use the processor name in the subplot title
            ax.set_title(f"{proc_name} | File: {filename} | Channel: {processor.channel_name}", 
                         fontsize=5, fontweight='bold')
            ax.set_ylabel("Amplitude")
            ax.set_xlabel("Time (s)")
            ax.legend(loc="upper right", fontsize='x-small')
            ax.grid(True, linestyle='--', alpha=0.6)

        # Hide any extra empty subplots if the grid is larger than num_files
        for ax in axes[num_files:]:
            ax.set_visible(False)

        plt.tight_layout()
        
    # 5. Show all generated figures at once
    plt.show()    

def plot_and_average_forces(processor, abs_forces=False):
    """
    Extracts force results from the processor, plots a bar chart of the mean force 
    per file, and calculates the overall average of these mean forces.
    
    Args:
        processor (AutomaticSignalProcessor): An instance of the processor 
                                              that has already processed the data.
                                              
    Returns:
        float: The overall average of the mean forces across all files.
    """
    # Retrieve the dictionary of results {filepath: mean_force}
    results = processor.get_force_results()
    
    if not results:
        print("No force results found. Please ensure 'compute_average_cutting_force' was called.")
        return None
        
    filenames = []
    mean_forces = []
    
    # Extract just the filename from the path and store the forces
    for filepath, force in results.items():
        filenames.append(os.path.basename(filepath))
        if abs_forces:
            force = abs(force)
        mean_forces.append(force)
        
    # Create the bar chart
    plt.figure(figsize=(10, 6))
    bars = plt.bar(filenames, mean_forces, color='skyblue', edgecolor='black')
    
    # Formatting the plot
    plt.xlabel('File Name', fontsize=12)
    plt.ylabel('Mean Force (N)', fontsize=12)
    plt.title('Average Cutting Force per File', fontsize=14)
    plt.xticks(rotation=45, ha='right') # Rotate x-axis labels to prevent overlap
    
    # Add numerical values on top of each bar for better readability
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2, yval + (0.01 * max(mean_forces)), 
                 f'{yval:.2f}', ha='center', va='bottom', fontsize=10)
                 
    plt.tight_layout()
    plt.show()

def plot_merged_signal(processors, labels=None, title="Merged Steady-State Signals", plot_envelope=True):
    """
    Plots the steady-state portions of the merged cutting signals for one or multiple processors.
    If multiple processors are provided and plot_envelope is True, it overlays a 95% 
    Confidence Interval envelope calculated using the Student's t-distribution.
    
    Args:
        processors (AutomaticSignalProcessor or list): A single instance or a list of instances 
                                                       that have already run 'merge_cutting_signals'.
        labels (list of str, optional): A list of labels for the legend corresponding to each processor.
        title (str, optional): The title of the plot. Defaults to "Merged Steady-State Signals".
        plot_envelope (bool, optional): Whether to calculate and plot the 95% CI envelope. Defaults to True.
    """
    if not isinstance(processors, (list, tuple)):
        processors = [processors]
        
    if labels is not None and len(labels) != len(processors):
        print("Warning: The number of labels provided does not match the number of processors. Ignoring labels.")
        labels = None

    plt.figure(figsize=(14, 6))
    colors = plt.cm.tab10.colors 
    
    # Store arrays to calculate Confidence Interval later
    all_t = []
    all_sig = []
        
    for p_idx, processor in enumerate(processors):
        if not hasattr(processor, 'merged_data') or processor.merged_data is None:
            print(f"Error: Merged data not found for processor index {p_idx}. Please run 'merge_cutting_signals()' first.")
            continue
            
        t_merged = processor.merged_data['t_full']
        signal = processor.merged_data['signal']
        source_files = processor.merged_data['source_files']
        
        all_t.append(t_merged)
        all_sig.append(signal)
                
        current_color = colors[p_idx % len(colors)]
        proc_name = getattr(processor, 'processor_name', f"Processor {p_idx + 1}")
        current_idx = 0
        
        # Make lines transparent ONLY if we are actually drawing the envelope over them
        line_alpha = 0.3 if (len(processors) > 1 and plot_envelope) else 0.8
        
        for i, filename in enumerate(source_files):
            file_data = processor.data[filename]
            
            start_idx = file_data['steady_start_idx']
            end_idx = file_data['steady_end_idx']
            
            chunk_len = end_idx - start_idx
            
            t_chunk = t_merged[current_idx : current_idx + chunk_len]
            sig_chunk = signal[current_idx : current_idx + chunk_len]
            
            # Label only the first chunk of each processor so it shows up neatly in the legend
            label_to_apply = proc_name if i == 0 else None
            
            plt.plot(t_chunk, sig_chunk, color=current_color, linewidth=1.0, label=label_to_apply, alpha=line_alpha)
            current_idx += chunk_len

    # --- 95% Confidence Interval Envelope Calculation ---
    if len(all_t) > 1 and plot_envelope:
        # 1. Create a common time grid using the highest sampling frequency
        fs = processors[0].merged_data['fs']
        t_max = max([t[-1] for t in all_t])
        t_common = np.arange(0, t_max, 1/fs)
        
        # 2. Interpolate all signals onto the common grid
        aligned_sigs = []
        for t, sig in zip(all_t, all_sig):
            # Pad with NaNs for points beyond the maximum time of a specific processor
            aligned_sig = np.interp(t_common, t, sig, right=np.nan)
            aligned_sigs.append(aligned_sig)
            
        aligned_sigs = np.array(aligned_sigs)
        
        # 3. Calculate dynamic statistics (ignoring NaNs from shorter tests)
        n_points = np.sum(~np.isnan(aligned_sigs), axis=0)
        
        with np.errstate(divide='ignore', invalid='ignore'):
            mean_sig = np.nanmean(aligned_sigs, axis=0)
            std_sig = np.nanstd(aligned_sigs, axis=0, ddof=1)
            
            # Standard Error
            se_sig = std_sig / np.sqrt(n_points)
            
            # Student's t-distribution critical value for 95% CI (two-tailed, alpha=0.05)
            # Degrees of freedom = n - 1
            t_crit = stats.t.ppf(0.975, df=n_points - 1)
            ci_margin = t_crit * se_sig
            
            # Mask out CI where n < 2 (impossible to calculate standard deviation)
            ci_margin[n_points < 2] = np.nan
            
        upper_bound = mean_sig + ci_margin
        lower_bound = mean_sig - ci_margin
        
        # 4. Plot Mean and CI Envelope
        plt.plot(t_common, mean_sig, color='black', linewidth=1.5, label='True Average (Mean)')
        plt.fill_between(t_common, lower_bound, upper_bound, color='black', alpha=0.3, 
                         label='95% Confidence Interval (Student t-dist)')

    # Add "(with 95% CI)" to the title dynamically if the envelope is turned on
    final_title = f"{title} (with 95% CI)" if (len(all_t) > 1 and plot_envelope) else title
    plt.title(final_title, fontsize=14, fontweight='bold')
    
    plt.xlabel("Cumulative Time (s)", fontsize=12)
    plt.ylabel("Amplitude", fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend(loc="upper right")
    
    plt.tight_layout()
    plt.show()