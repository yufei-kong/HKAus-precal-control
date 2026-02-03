"""
Shared state module for HyperK DAQ GUI

This module persists across Streamlit reruns and provides thread-safe
storage for progress data updated by background threads.

The module is imported once and cached by Python, so modifications to
progress_data persist across Streamlit page refreshes.
"""

# Thread-safe progress tracking dictionary
# Updated by background worker threads, read by Streamlit GUI
progress_data = {
    'active': False,           # True when run is actively executing
    'scheduled': False,        # True when run is scheduled but not started
    'cancelled': False,        # Set to True to cancel scheduled run
    'progress_pct': 0,         # Progress percentage (0-100)
    'status_text': '',         # Current status message
    'position': '',            # Current position string (e.g., "θ=30°, φ=90°")
    'result': None,            # Final result dictionary when complete
    'scheduled_start': None,   # Datetime when scheduled run will start
    'delay_seconds': 0,        # Total delay in seconds for scheduled run
    'countdown_seconds': 0,    # Remaining seconds until scheduled run starts
}

# Thread-safe data for manual DAQ acquisitions
# Updated by background thread, read by Streamlit GUI
manual_acq_data = {
    'active': False,           # True when manual acquisition is running
    'progress': 0,             # Progress percentage (0-100)
    'output': [],              # List of output lines from WaveDump
    'start_time': None,        # Datetime when acquisition started
    'result': None,            # Final result dictionary when complete
}