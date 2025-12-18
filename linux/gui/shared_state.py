"""
Shared state module for thread-safe communication.
This persists across Streamlit reruns because imported modules are cached.
"""

# Shared progress data - accessible from both main thread and background threads
progress_data = {
    'progress_pct': 0,
    'status_text': '',
    'position': '',
    'active': False,
    'result': None
}