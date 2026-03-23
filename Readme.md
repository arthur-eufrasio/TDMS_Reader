```markdown
# TDMS Signal Processing in Python

This project contains two Python scripts for reading, processing, and visualizing signals stored in **TDMS** files (a format commonly used by National Instruments).

The basic workflow is:

1. Read a `.tdms` file
2. Select a group and channel
3. Extract the raw signal, sampling frequency, and time vector
4. Perform drift and DC offset correction
5. Apply a Butterworth low‑pass filter
6. Plot the processed signal

---

## Project Structure

```text
.
├── processor.py   # Defines the SignalProcessor class
├── run.py         # Example script using SignalProcessor
└── README.md      # This file
```

---

## `processor.py`

This file defines the `SignalProcessor` class, which:

- Reads TDMS files using `nptdms.TdmsFile`
- Selects a group and a channel (either interactively or via arguments)
- Extracts:
  - Raw signal: `self.raw`
  - Time step `dt`: `self.ts`
  - Sampling frequency `fs = 1 / ts`: `self.fs`
  - Full time vector: `self.t_full`
- Performs linear drift and DC offset correction: `drift_offset_correction`
- Applies a zero‑phase Butterworth low‑pass filter: `apply_lowpass_filter`
- Plots a signal: `plot_signal`

### Constructor

```python
from processor import SignalProcessor

processor = SignalProcessor(
    filepath,
    group_name=None,        # optional
    channel_name=None,      # optional
    increment_key="wf_increment",
)
```

**Parameters:**

- `filepath` (str): Path to the `.tdms` file.
- `group_name` (str, optional): Name of the TDMS group to read.
  - If `None`, you will be prompted in the console to select one.
- `channel_name` (str, optional): Name of the channel to read.
  - If `None`, you will be prompted in the console to select one.
- `increment_key` (str, optional): TDMS property key containing the time step (`dt`).
  - Default: `"wf_increment"`.

The constructor:

- Reads the TDMS file
- Selects the specified (or interactive) group and channel
- Extracts the channel data to `self.raw`
- Reads the time increment `dt` from the channel properties (`self.ts`)
- Computes the sampling frequency `self.fs = 1 / self.ts`
- Creates a time vector: `self.t_full = np.arange(len(self.raw)) * self.ts`

---

### `drift_offset_correction(window_time=0.3, noise_tolerance=5.0)`

Removes linear drift and DC offset from the raw signal. It assumes that the beginning and end of the signal (within a time window) correspond to “idle” machine conditions (flat regions).

**Parameters:**

- `window_time` (float, seconds):  
  Length of the time window at the start and end of the signal used to estimate average levels and variation.  
  Default: `0.3` seconds.
- `noise_tolerance` (float):  
  Maximum allowed peak‑to‑peak variation within each window.  
  If the variation in either window exceeds this value, the function assumes there is significant activity at the edges and raises a `RuntimeError`.  
  Default: `5.0` (in the same units as the signal).

**Behavior:**

- Converts `window_time` to a number of samples using `self.fs`.
- Computes the peak‑to‑peak variation in the start and end windows.
- If either variation exceeds `noise_tolerance`, raises a `RuntimeError`.
- Otherwise:
  - Computes the mean of the start window (`y1`) and the end window (`y2`).
  - Assumes a linear drift between `y1` and `y2` over the entire signal length.
  - Subtracts this linear ramp from the signal.
  - Computes a remaining offset as the average of the (corrected) start and end segments and subtracts it to center the signal around zero.

**Returns:**

- `numpy.ndarray`: The drift‑corrected and zero‑centered signal (also stored in `self.corrected`).

---

### `apply_lowpass_filter(cutoff_freq=250, order=5)`

Applies a zero‑phase Butterworth low‑pass filter to the **corrected** signal (`self.corrected`) using `scipy.signal.filtfilt`.

**Parameters:**

- `cutoff_freq` (float, Hz):  
  Cutoff frequency of the low‑pass filter.
- `order` (int):  
  Order of the Butterworth filter.  
  Default: `5`.

**Behavior:**

- Computes the Nyquist frequency: `nyquist = 0.5 * self.fs`.
- Normalizes the cutoff: `normal_cutoff = cutoff_freq / nyquist`.
- Designs a Butterworth low‑pass filter.
- Applies zero‑phase filtering (`filtfilt`) to `self.corrected`.

**Returns:**

- `numpy.ndarray`: The filtered signal (also stored in `self.filtered`).

> **Note:** This method expects that `drift_offset_correction` has already been called. Otherwise, `self.corrected` does not exist and you will get an error.

---

### `plot_signal(signal, title="Signal", xlabel="Time (s)", ylabel="Amplitude")`

Plots a given signal vector against the time vector `self.t_full` using `matplotlib`.

**Parameters:**

- `signal` (`numpy.ndarray`): Signal to be plotted.
- `title` (str): Plot title. Default: `"Signal"`.
- `xlabel` (str): Label for the x‑axis. Default: `"Time (s)"`.
- `ylabel` (str): Label for the y‑axis. Default: `"Amplitude"`.

---

## `run.py`

This script demonstrates how to use `SignalProcessor` in a complete processing chain:

```python
from processor import SignalProcessor

if __name__ == "__main__":
    filepath = "K:/TF/Abteilung I/All/++ Modellierung und Bewertung/10_AML - Abaqus Modeling Landscape/Arthur Eufrasio/TDMS_Files/MSNG_AP_1-5_swi_RCGX_FTur_Y2_s1_lc344.tdms"

    processor = SignalProcessor(
        filepath,
        increment_key="wf_increment",
        group_name="Device1",
        channel_name="Fx - Vorschubskraft",
    )

    processor.drift_offset_correction(window_time=0.3, noise_tolerance=5.0)
    processor.apply_lowpass_filter(cutoff_freq=50, order=5)
    processor.plot_signal(
        processor.filtered,
        title="Filtered Signal",
        xlabel="Time (s)",
        ylabel="Amplitude",
    )
```

You should adjust:

- `filepath` to point to your own `.tdms` file.
- `group_name` and `channel_name` to valid names present in your file.
- Parameters of `drift_offset_correction` and `apply_lowpass_filter` as needed for your data.

---

## Dependencies

This project uses the following Python packages:

- [`numpy`](https://numpy.org/)
- [`matplotlib`](https://matplotlib.org/)
- [`scipy`](https://scipy.org/) (specifically `scipy.signal`)
- [`nptdms`](https://nptdms.readthedocs.io/) (for reading TDMS files)

Recommended Python version: **3.9+** (should also work on 3.8+).

### Installing Dependencies

You can install the dependencies with:

```bash
pip install numpy matplotlib scipy nptdms
```

Alternatively, create a `requirements.txt`:

```text
numpy
matplotlib
scipy
nptdms
```

and then run:

```bash
pip install -r requirements.txt
```

---

## How to Run

1. Edit `run.py` and set the path to your TDMS file:

   ```python
   filepath = "path/to/your_file.tdms"
   ```

2. Optionally, adjust:

   - `group_name`
   - `channel_name`
   - `window_time`, `noise_tolerance`
   - `cutoff_freq`, `order`

3. Run the script from the command line:

   ```bash
   python run.py
   ```

A matplotlib window will open showing the filtered signal versus time.

---

## Interactive Usage (Optional)

You can also use the `SignalProcessor` interactively in a Python shell or Jupyter notebook:

```python
from processor import SignalProcessor

# If group_name and channel_name are omitted, the script will prompt you in the console
processor = SignalProcessor("path/to/your_file.tdms")

corrected = processor.drift_offset_correction(window_time=0.3, noise_tolerance=5.0)
filtered = processor.apply_lowpass_filter(cutoff_freq=50, order=5)

processor.plot_signal(filtered, title="Filtered Signal")
```

---

## Notes and Limitations

- The drift/offset correction assumes:
  - The first and last `window_time` seconds of the signal are “flat” (no cutting activity).
  - Any difference in average level between these windows is due to **linear drift**, which should be removed.
- If the edges contain real process activity (or if the signal is very short), the correction may:
  - Raise a `RuntimeError`, or
  - Remove physically meaningful baseline changes.

Make sure these assumptions match your specific measurement scenario.
