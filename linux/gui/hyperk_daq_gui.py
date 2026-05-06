"""
HyperK PMT DAQ Control System - GUI v4
Final refinements from November 2025

This is a PREVIEW/MOCKUP - no real devices connected

Usage:
    streamlit run hyperk_daq_gui_v4.py
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import time
import threading
from datetime import datetime, timedelta
import pandas as pd
import altair as alt
import numpy as np
import json
import sys
import os
from pathlib import Path
import atexit
from loguru import logger
import warnings

# Import shared state module (persists across Streamlit reruns)
import shared_state

# Suppress annoying ScriptRunContext warnings from threading
warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')
warnings.filterwarnings('ignore', category=UserWarning, module='streamlit')

# Add paths
script_dir = Path(__file__).parent  # gui/
linux_dir = script_dir.parent        # linux/

# Add linux directory to path so we can do "import drivers.xxx"
sys.path.insert(0, str(linux_dir))

# Add xArm SDK to path
xarm_sdk_path = linux_dir / "xArm-Python-SDK"
sys.path.insert(0, str(xarm_sdk_path))

# Library imports
try:
    from drivers.xarm_pmt_controller import XArmPMTController
    XARM_CONTROLLER_AVAILABLE = True
except ImportError as e:
    XARM_CONTROLLER_AVAILABLE = False
    print(f"⚠ xArm PMT Controller not available: {e}")

try:
    from drivers.system_coordinator import HyperKSystemCoordinator
    SYSTEM_COORDINATOR_AVAILABLE = True
except ImportError as e:
    SYSTEM_COORDINATOR_AVAILABLE = False
    print(f"⚠ System Coordinator not available: {e}")

try:
    from drivers.caen_digitizer_wavedump import CAENDigitizerWaveDump
    DIGITIZER_AVAILABLE = True
except ImportError as e:
    DIGITIZER_AVAILABLE = False
    print(f"⚠ Digitizer driver not available: {e}")

try:
    from drivers.sipm_ips2303s import IPS2303s
    SIPM_AVAILABLE = True
except ImportError as e:
    SIPM_AVAILABLE = False
    print(f"⚠ SiPM driver not available: {e}")

try:
    from api_client.device_api_client import WindowsDeviceClient
    API_CLIENT_AVAILABLE = True
except ImportError as e:
    API_CLIENT_AVAILABLE = False
    print(f"⚠ Windows API client not available: {e}")

# ============================================================================
# MODULE-LEVEL GLOBALS (for cleanup without Streamlit context)
# ============================================================================
_sipm_supply = None
_digitizer = None
_system_coordinator = None
_robot_controller = None

# Use shared_state module for persistent data across reruns
# This module is imported once and cached by Python

# ============================================================================
# THREADING HELPER FUNCTIONS FOR RUN SEQUENCES
# ============================================================================

def progress_callback(progress_pct, message, position=""):
    """
    Progress callback function called by robot controller during scan.
    Updates shared progress dictionary (thread-safe).
    
    Args:
        progress_pct: Progress percentage (0-100)
        message: Status message describing current action
        position: Current position string (e.g., "θ=30°, φ=90°"), optional
    """
    # Access the global persistent dict
    shared_state.progress_data['progress_pct'] = int(progress_pct)
    shared_state.progress_data['status_text'] = message
    shared_state.progress_data['position'] = position
    
    # Print with or without position
    if position:
        print(f"[PROGRESS] {progress_pct}% - {message} @ {position}")
    else:
        print(f"[PROGRESS] {progress_pct}% - {message}")

def log_run_completion(run_name, sequence_type, pmt_serials, pmt_voltages, status, start_time, end_time):
    """
    Log completed run to run_log.txt file.
    
    Args:
        run_name: Name of the run
        sequence_type: Type of sequence that was run
        pmt_serials: String of PMT serial numbers (e.g., "ZE1234, ZE5678")
        pmt_voltages: String of PMT voltages (e.g., "1500V, 1600V")
        status: Run status ('success', 'failed', 'cancelled')
        start_time: Datetime when run started
        end_time: Datetime when run ended
    """
    try:
        log_file = Path("run_log.txt")
        
        # Calculate duration in seconds
        duration_seconds = int((end_time - start_time).total_seconds())
        
        # Format duration string
        if duration_seconds >= 3600:
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            seconds = duration_seconds % 60
            duration_str = f"{hours}h {minutes}m {seconds}s"
        elif duration_seconds >= 60:
            minutes = duration_seconds // 60
            seconds = duration_seconds % 60
            duration_str = f"{minutes}m {seconds}s"
        else:
            duration_str = f"{duration_seconds}s"
        
        # Format log entry
        log_entry = (
            f"[{end_time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"Run: {run_name} | "
            f"Type: {sequence_type.split(' (')[0]} | "
            f"PMTs: {pmt_serials} | "
            f"HV: {pmt_voltages} | "
            f"Status: {status.upper()} | "
            f"Duration: {duration_str}\n"
        )
        
        # Append to log file
        with open(log_file, 'a') as f:
            f.write(log_entry)
        
        print(f"[RUN_LOG] {log_entry.strip()}")
        logger.info(f"Run logged: {run_name} - {status}")
        
    except Exception as e:
        print(f"[RUN_LOG] Error logging run: {e}")
        logger.error(f"Failed to log run completion: {e}")


def scheduled_start_worker(coordinator, sequence_type, params, delay_seconds):
    """
    Waits for specified delay then starts the run sequence.
    Updates countdown in shared_state during waiting period.
    
    Args:
        coordinator: SystemCoordinator instance
        sequence_type: Type of sequence to run
        params: Parameters for the sequence
        delay_seconds: How many seconds to wait before starting
    """
    import warnings
    warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')
    
    try:
        print(f"[SCHEDULER] Waiting {delay_seconds}s before starting {sequence_type}")
        
        # Mark as scheduled (not active yet)
        shared_state.progress_data['scheduled'] = True
        shared_state.progress_data['active'] = False
        shared_state.progress_data['scheduled_start'] = datetime.now() + timedelta(seconds=delay_seconds)
        shared_state.progress_data['delay_seconds'] = delay_seconds
        shared_state.progress_data['cancelled'] = False
        
        # Countdown loop - check every second for cancellation
        for remaining in range(delay_seconds, 0, -1):
            # Check if cancelled
            if shared_state.progress_data.get('cancelled', False):
                print(f"[SCHEDULER] Scheduled run cancelled by user")
                shared_state.progress_data['scheduled'] = False
                shared_state.progress_data['result'] = {'status': 'cancelled', 'message': 'Scheduled start cancelled by user'}
                return
            
            # Update countdown
            shared_state.progress_data['countdown_seconds'] = remaining
            time.sleep(1)
        
        # Delay complete - check one more time for cancellation
        if shared_state.progress_data.get('cancelled', False):
            print(f"[SCHEDULER] Scheduled run cancelled at last second")
            shared_state.progress_data['scheduled'] = False
            shared_state.progress_data['result'] = {'status': 'cancelled', 'message': 'Scheduled start cancelled'}
            return
        
        print(f"[SCHEDULER] Delay complete, starting {sequence_type} now")
        shared_state.progress_data['scheduled'] = False
        
        # Now run the actual sequence
        run_sequence_worker(coordinator, sequence_type, params)
        
    except Exception as e:
        print(f"[SCHEDULER] ERROR: {e}")
        shared_state.progress_data['scheduled'] = False
        shared_state.progress_data['result'] = {'status': 'error', 'error': str(e)}


def run_sequence_worker(coordinator, sequence_type, params):
    """
    Worker function that runs in background thread.
    Executes the run sequence and updates session state when complete.
    
    Args:
        coordinator: SystemCoordinator instance
        sequence_type: Type of sequence ("Dark Current", "Single PMT", etc.)
        params: Dictionary of parameters for the sequence
    """
    # Suppress ScriptRunContext warnings from thread
    import warnings
    warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')
    
    try:
        # Record actual start time (excludes any delay time)
        actual_start_time = datetime.now()
        shared_state.progress_data['actual_start_time'] = actual_start_time
        
        print(f"[THREAD] Starting {sequence_type} sequence")
        
        # Mark as active in global dict
        shared_state.progress_data['active'] = True
        
        if "Dark Current" in sequence_type:
            result = coordinator.run_dark_current_check(
                pmt1_serial=params['pmt1_serial'],
                pmt2_serial=params['pmt2_serial'],
                duration=params['duration'],
                progress_callback=progress_callback
            )
            
        elif "Single PMT" in sequence_type:
            result = coordinator.run_single_pmt_scan(
                pmt_number=params['pmt_num'],
                serial=params['serial'],
                zeniths=params['zeniths'],
                azimuths=params['azimuths'],
                daq_runtime=params['daq_runtime'],
                progress_callback=progress_callback
            )
            
        elif "Full PMT Scan" in sequence_type:
            result = coordinator.run_full_scan(
                pmt1_serial=params['pmt1_serial'],
                pmt2_serial=params['pmt2_serial'],
                zeniths=params['zeniths'],
                azimuths=params['azimuths'],
                daq_runtime=params['daq_runtime'],
                progress_callback=progress_callback
            )
        else:
            result = {'status': 'error', 'error': f'Unknown sequence type: {sequence_type}'}
        
        # Store result in global dict
        shared_state.progress_data['result'] = result
        shared_state.progress_data['active'] = False
        
        print(f"[THREAD] {sequence_type} completed: {result.get('status')}")
        
        # Log run completion directly from worker thread
        try:
            metadata = shared_state.progress_data.get('run_metadata')
            if metadata:
                print(f"[DEBUG] Worker thread logging run: {metadata['run_name']}")
                
                # Determine status
                if result.get('status') == 'success':
                    status = 'success'
                elif result.get('status') == 'cancelled':
                    status = 'cancelled'
                else:
                    status = 'failed'
                
                # Get actual start time (excludes delay)
                actual_start = shared_state.progress_data.get('actual_start_time', metadata['start_time'])
                
                # Log to file
                log_run_completion(
                    run_name=metadata['run_name'],
                    sequence_type=metadata['sequence_type'],
                    pmt_serials=metadata['pmt_serials'],
                    pmt_voltages=metadata['pmt_voltages'],
                    status=status,
                    start_time=actual_start,
                    end_time=datetime.now()
                )
                
                # Clear metadata after logging
                if 'run_metadata' in shared_state.progress_data:
                    del shared_state.progress_data['run_metadata']
            else:
                print(f"[DEBUG] Worker thread: No metadata found - run not logged")
        except Exception as e:
            print(f"[DEBUG] Worker thread logging failed: {e}")
        
    except Exception as e:
        print(f"[THREAD] ERROR: {e}")
        shared_state.progress_data['result'] = {'status': 'error', 'error': str(e)}
        shared_state.progress_data['active'] = False

# Logger
def setup_logging():
    """Setup loguru logging to both console and file"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"hyperk_daq_{timestamp}.log"
    
    # Remove default handler (to avoid duplicates on reruns)
    logger.remove()
    
    # Add console handler (like before)
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <5}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG"
    )
    
    # Add file handler
    logger.add(
        str(log_file),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <5} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="500 MB",  # Rotate if file gets too big
        retention="30 days"  # Keep logs for 30 days
    )
    
    logger.info(f"Logging to file: {log_file}")
    return log_file

# Call once at startup
if 'log_file' not in st.session_state:
    st.session_state.log_file = setup_logging()

# Page config
st.set_page_config(
    page_title="HyperK PMT DAQ Control",
    page_icon="🦾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS - Grafana-inspired dark theme with better visibility
st.markdown("""
<style>
    /* Grafana-inspired color scheme with improved visibility */
    :root {
        --bg-primary: #111217;
        --bg-secondary: #181b1f;
        --bg-tertiary: #27272d;
        --text-primary: #d8d9da;
        --text-secondary: #c7d0d9;
        --text-muted: #9fa1a4;
        --accent-green: #73bf69;
        --accent-red: #f2495c;
        --accent-yellow: #ff9830;
        --accent-blue: #5794f2;
        --border-color: #3d3d42;
    }
    
    /* Override Streamlit defaults */
    .stApp {
        background-color: var(--bg-primary);
        color: var(--text-primary);
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: var(--bg-secondary) !important;
    }
    
    [data-testid="stSidebar"] * {
        color: var(--text-secondary) !important;
    }
    
    /* Make all text more visible */
    .stMarkdown, .stText, p, span, div {
        color: var(--text-secondary) !important;
    }
    
    h1, h2, h3, h4, h5, h6 {
        color: var(--text-primary) !important;
    }
    
    /* Subheader styling */
    .stMarkdown h2, .stMarkdown h3 {
        color: var(--text-primary) !important;
        font-weight: 600 !important;
    }
    
    /* Caption text */
    .stCaption {
        color: var(--text-muted) !important;
    }
    
    /* Input fields - force dark theme */
    .stTextInput input, .stNumberInput input {
        background-color: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
    }
    
    /* Selectbox - aggressive dark mode override */
    .stSelectbox > div > div {
        background-color: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
    }
    
    .stSelectbox [data-baseweb="select"] {
        background-color: var(--bg-tertiary) !important;
    }
    
    .stSelectbox [data-baseweb="select"] > div {
        background-color: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
        border-color: var(--border-color) !important;
    }
    
    /* Dropdown menu styling */
    [data-baseweb="popover"] {
        background-color: var(--bg-tertiary) !important;
    }
    
    [role="listbox"] {
        background-color: var(--bg-tertiary) !important;
    }
    
    [role="option"] {
        background-color: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
    }
    
    [role="option"]:hover {
        background-color: var(--bg-secondary) !important;
        color: var(--accent-blue) !important;
    }
    
    /* Text area */
    .stTextArea textarea {
        background-color: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
    }
    
    /* Slider */
    .stSlider {
        color: var(--text-secondary) !important;
    }
    
    /* Multi-select */
    .stMultiSelect [data-baseweb="select"] {
        background-color: var(--bg-tertiary) !important;
    }
    
    .stMultiSelect [data-baseweb="tag"] {
        background-color: var(--accent-blue) !important;
    }
    
    /* Buttons */
    .stButton>button {
        width: 100%;
        background-color: var(--bg-tertiary);
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color);
    }
    
    .stButton>button:hover {
        border-color: var(--accent-blue);
        color: var(--accent-blue) !important;
    }
    
    /* Primary button */
    .stButton>button[kind="primary"] {
        background-color: var(--accent-green) !important;
        color: white !important;
    }
    
    .stButton>button[kind="primary"]:hover {
        background-color: #5aa84f !important;
    }
    
    /* Disabled button */
    .stButton>button:disabled {
        background-color: var(--bg-tertiary) !important;
        color: var(--text-muted) !important;
        opacity: 0.5;
    }
    
    /* Status indicators */
    .status-indicator {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 8px;
    }
    
    .status-green { background-color: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); }
    .status-red { background-color: var(--accent-red); box-shadow: 0 0 8px var(--accent-red); }
    .status-yellow { background-color: var(--accent-yellow); box-shadow: 0 0 8px var(--accent-yellow); }
    .status-grey { background-color: #6e6e6e; }
    
    /* Device cards */
    .device-card {
        background-color: var(--bg-secondary);
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        border: 1px solid var(--border-color);
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        background-color: var(--bg-secondary);
    }
    
    .stTabs [data-baseweb="tab"] {
        color: var(--text-muted) !important;
    }
    
    .stTabs [aria-selected="true"] {
        color: var(--accent-blue) !important;
        border-bottom-color: var(--accent-blue);
    }
    
    /* Metrics */
    [data-testid="stMetricValue"] {
        color: var(--text-primary) !important;
        font-size: 1.8rem !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: var(--text-secondary) !important;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background-color: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
    }
    
    /* Dataframe */
    .stDataFrame {
        background-color: var(--bg-secondary) !important;
    }
    
    /* Info/Warning/Error boxes */
    .stAlert {
        background-color: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
    }
    
    /* Checkbox */
    .stCheckbox {
        color: var(--text-secondary) !important;
    }
    
    /* Radio buttons */
    .stRadio label {
        color: var(--text-secondary) !important;
    }
    
    /* Progress bar */
    .stProgress > div > div {
        background-color: var(--accent-green) !important;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions
def status_dot(status: str) -> str:
    """Generate HTML status indicator
    Args:
        status: 'green', 'red', 'yellow', or 'grey'
    """
    return f'<span class="status-indicator status-{status}"></span>'

def check_password(password: str) -> bool:
    """Simple password check (in production, use proper auth)"""
    return password == "hyperk2025"

def save_custom_sequence(name: str, config: dict):
    """Save a custom sequence configuration"""
    if 'custom_sequences' not in st.session_state:
        st.session_state.custom_sequences = {}
    st.session_state.custom_sequences[name] = config

def get_sequence_list():
    """Get list of available sequences including custom ones"""
    default_sequences = [
        "Dark Current Check (10 min)",
        "Single PMT Test (3.5 hours)", 
        "Full PMT Scan (7 hours)",
    ]
    
    if 'custom_sequences' in st.session_state and st.session_state.custom_sequences:
        custom_sequences = [f"Custom: {name}" for name in st.session_state.custom_sequences.keys()]
        return default_sequences + custom_sequences + ["Create New Custom Scan..."]
    else:
        return default_sequences + ["Create New Custom Scan..."]

# # Initialize hardware

# Initialize digitizer
if 'digitizer' not in st.session_state:
    if DIGITIZER_AVAILABLE:
        try:
            digitizer = CAENDigitizerWaveDump(
                wavedump_path="/home/hyperkaus/CAEN/wavedump-3.10.6-augmented/src/wavedump",
                config_template="./configs/wavedumpconfig_template.txt",
                working_dir="."
            )
            st.session_state.digitizer = digitizer
            st.session_state.digitizer_connected = True
            st.session_state.digitizer_status = digitizer.get_status()

            _digitizer = digitizer

        except Exception as e:
            st.session_state.digitizer = None
            st.session_state.digitizer_connected = False
            st.session_state.digitizer_error = str(e)
    else:
        st.session_state.digitizer = None
        st.session_state.digitizer_connected = False

# Initialize acquisition state
if 'last_acquisition' not in st.session_state:
    st.session_state.last_acquisition = None


# Initialize SiPM power supply
if 'sipm_supply' not in st.session_state:
    if SIPM_AVAILABLE:
        try:
            sipm = IPS2303s(port='/dev/ttyUSB0', baud=115200)
            st.session_state.sipm_supply = sipm
            st.session_state.sipm_connected = True

            # Store globally for cleanup
            _sipm_supply = sipm

        except Exception as e:
            st.session_state.sipm_supply = None
            st.session_state.sipm_connected = False
            print(f"SiPM initialization failed: {e}")
    else:
        st.session_state.sipm_supply = None
        st.session_state.sipm_connected = False

# SiPM output state - Query actual device state on startup
if 'sipm_output_on' not in st.session_state:
    if st.session_state.get('sipm_connected', False):
        try:
            # Query actual output state from device
            actual_state = st.session_state.sipm_supply.get_output_status()
            st.session_state.sipm_output_on = actual_state
            logger.info(f"✓ SiPM output state detected: {'ON' if actual_state else 'OFF'}")
        except Exception as e:
            # If query fails, assume OFF for safety
            st.session_state.sipm_output_on = False
            print(f"⚠ Could not query SiPM state, defaulting to OFF: {e}")
    else:
        # Not connected, default to OFF
        st.session_state.sipm_output_on = False

# CAEN HV channel history (for graphs)
if 'caen_voltage_history' not in st.session_state:
    st.session_state.caen_voltage_history = {
        'ch0': [], 'ch1': [], 'ch2': [], 'ch3': [],
        'timestamps': []
    }

if 'caen_current_history' not in st.session_state:
    st.session_state.caen_current_history = {
        'ch0': [], 'ch1': [], 'ch2': [], 'ch3': [],
        'timestamps': []
    }

# Initialize SiPM current history
if 'sipm_current_history' not in st.session_state:
    st.session_state.sipm_current_history = {
        'ch1': [], 'ch2': [],
        'timestamps': []
    }

# Initialize Windows API client
if 'api_client' not in st.session_state:
    if API_CLIENT_AVAILABLE:
        try:
            # Connect to Windows machine
            api_client = WindowsDeviceClient("192.168.0.186", port=8000)
            
            # Test connection
            if api_client.check_connection():
                st.session_state.api_client = api_client
                st.session_state.api_connected = True
                
                # Store globally for cleanup
                _api_client = api_client
                
                logger.info("✓ Connected to Windows API server")
            else:
                st.session_state.api_client = None
                st.session_state.api_connected = False
                logger.warning("✗ Windows API server not responding")
                
        except Exception as e:
            st.session_state.api_client = None
            st.session_state.api_connected = False
            print(f"Windows API initialization failed: {e}")
    else:
        st.session_state.api_client = None
        st.session_state.api_connected = False

# Initialize Robot Controller and System Coordinator
if 'robot_controller' not in st.session_state:
    if XARM_CONTROLLER_AVAILABLE and SYSTEM_COORDINATOR_AVAILABLE:
        try:
            # Import xArm SDK
            from xarm.wrapper import XArmAPI
            
            # Connect to xArm
            arm = XArmAPI('192.168.1.243')
            # arm.connect()
            arm.motion_enable(enable=True)
            arm.set_mode(0) #0
            arm.set_state(state=0)
                        
            # Create robot controller
            robot_controller = XArmPMTController(arm=arm, digitizer=digitizer)
            st.session_state.robot_controller = robot_controller
            
            # Create system coordinator (combines robot + Windows API)
            system_coordinator = HyperKSystemCoordinator(
                robot_controller=robot_controller,
                api_client=st.session_state.api_client if 'api_client' in st.session_state else None
            )
            st.session_state.system_coordinator = system_coordinator
            
            # Store in module-level variables for cleanup (already at module scope, no global needed)
            _robot_controller = robot_controller
            _system_coordinator = system_coordinator
            
            logger.info("✓ Robot controller and system coordinator initialized")
            
        except Exception as e:
            st.session_state.robot_controller = None
            st.session_state.system_coordinator = None
            print(f"Robot controller initialization failed: {e}")
    else:
        st.session_state.robot_controller = None
        st.session_state.system_coordinator = None

# Initialize CAEN HV session state
if 'caen_channels' not in st.session_state:
    st.session_state.caen_channels = {}
    for ch in range(4):  # 4 channels (0-3), but we use 1-3 for PMTs
        st.session_state.caen_channels[ch] = {
            'voltage_set': 0.0,
            'voltage_mon': 0.0,
            'current_set': 50.0,  # Default 50µA
            'current_mon': 0.0,
            'power_on': False,
            'ramp_up': 50.0,  # Default 50 V/s
            'ramp_down': 100.0,  # Default 100 V/s
            'ramping': False,
            'status': {}
        }

# Initialize Signal Generator session state
if 'siggen_enabled' not in st.session_state:
    if st.session_state.get('siggen_connected', False):
        try:
            # Query actual output state from device via Windows API
            status = st.session_state.api_client.siggen_get_status()
            actual_state = status.get('output_enabled', False)
            st.session_state.siggen_enabled = actual_state
            logger.info(f"✓ Signal generator output state detected: {'ON' if actual_state else 'OFF'}")
        except Exception as e:
            # If query fails, assume OFF for safety
            st.session_state.siggen_enabled = False
            print(f"⚠ Could not query signal generator state, defaulting to OFF: {e}")
    else:
        st.session_state.siggen_enabled = False

# Initialize Laser session state
if 'laser_tec_on' not in st.session_state:
    st.session_state.laser_tec_on = False
if 'laser_ld_on' not in st.session_state:
    st.session_state.laser_ld_on = False
if 'laser_trigger_mode' not in st.session_state:
    st.session_state.laser_trigger_mode = "EXT"

# Initialize laser history for graphs
if 'laser_history' not in st.session_state:
    st.session_state.laser_history = {
        'ld_temp': [],
        'board_temp': [],
        'pulse_current': [],
        'pd_current': [],
        'timestamps': []
    }

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'mode' not in st.session_state:
    st.session_state.mode = 'Run Sequence'
if 'run_active' not in st.session_state:
    st.session_state.run_active = False
if 'run_progress' not in st.session_state:
    st.session_state.run_progress = 0
if 'run_thread' not in st.session_state:
    st.session_state.run_thread = None
if 'run_result' not in st.session_state:
    st.session_state.run_result = None
if 'run_position' not in st.session_state:
    st.session_state.run_position = ""
if 'run_status_text' not in st.session_state:
    st.session_state.run_status_text = ""
if 'stop_requested' not in st.session_state:
    st.session_state.stop_requested = False
if 'run_scheduled' not in st.session_state:
    st.session_state.run_scheduled = False  # Track if waiting for scheduled start
if 'delay_hours' not in st.session_state:
    st.session_state.delay_hours = 0  # Scheduled delay hours
if 'delay_minutes' not in st.session_state:
    st.session_state.delay_minutes = 0  # Scheduled delay minutes
if 'pmt_voltages' not in st.session_state:
    st.session_state.pmt_voltages = [None, None, 1760]
if 'pmt_power' not in st.session_state:
    st.session_state.pmt_power = [False, False, False]
if 'pmt_ramping' not in st.session_state:
    st.session_state.pmt_ramping = [False, False, False]
if 'scheduled_start' not in st.session_state:
    st.session_state.scheduled_start = None
if 'laser_ld_on' not in st.session_state:
    # Query actual laser state from Windows API if available
    if st.session_state.get('api_connected', False):
        try:
            print(f"DEBUG: Attempting to query laser state on initialization...")
            status = st.session_state.api_client.laser_get_status()
            st.session_state.laser_tec_on = status.get('tec_on', False)
            st.session_state.laser_ld_on = status.get('ld_on', False)
            logger.info(f"✓ Laser state detected: TEC={'ON' if st.session_state.laser_tec_on else 'OFF'}, LD={'ON' if st.session_state.laser_ld_on else 'OFF'}")
        except Exception as e:
            # If query fails, default to OFF for safety
            st.session_state.laser_tec_on = False
            st.session_state.laser_ld_on = False
            print(f"⚠ Could not query laser state, defaulting to OFF: {e}")
    else:
        print(f"DEBUG: API not connected (api_connected={st.session_state.get('api_connected', 'NOT SET')}), defaulting laser to OFF")
        # API not connected, default to OFF
        st.session_state.laser_tec_on = False
        st.session_state.laser_ld_on = False
elif 'laser_tec_on' not in st.session_state:
    # Edge case: LD was set but TEC wasn't, query again
    if st.session_state.get('api_connected', False):
        try:
            status = st.session_state.api_client.laser_get_status()
            st.session_state.laser_tec_on = status.get('tec_on', False)
            logger.info(f"✓ Laser TEC state detected: {'ON' if st.session_state.laser_tec_on else 'OFF'}")
        except Exception as e:
            st.session_state.laser_tec_on = False
            print(f"⚠ Could not query laser TEC state, defaulting to OFF: {e}")
    else:
        st.session_state.laser_tec_on = False
if 'robot_position' not in st.session_state:
    # Query actual robot position from robot if available
    if st.session_state.get('robot_controller') is not None:
        try:
            # Get current joint angles (returns 7 elements, we only need first 6)
            angles = st.session_state.robot_controller.get_current_position()[:6]
            
            # Define known positions with CORRECT naming:
            # HOME = true vertical home position
            # INTERMEDIATE = safe intermediate position (was called HOME in old code)
            HOME = [0, 0, 0, 0, 0, -135]  # True home (vertical)
            INTERMEDIATE = [0, -116.5, 5, 0, 0, -135]  # Safe intermediate position
            PMT_TOP = [-0.0, -116.812436, -25.177883, 0.0, 51.990269, -135.0]
            
            # Helper function to check if angles match (within tolerance)
            def angles_match(a1, a2, tolerance=1.0):
                """Check if two angle arrays match within tolerance (degrees)"""
                if a1 is None or a2 is None or len(a1) != len(a2):
                    return False
                return all(abs(a1[i] - a2[i]) < tolerance for i in range(len(a1)))
            
            # Detect position (check most specific first)
            if angles_match(angles, PMT_TOP):
                st.session_state.robot_position = 'pmt_top'
                logger.info(f"✓ Robot position detected: PMT Top")
            elif angles_match(angles, INTERMEDIATE):
                st.session_state.robot_position = 'intermediate'
                logger.info(f"✓ Robot position detected: Intermediate")
            elif angles_match(angles, HOME):
                st.session_state.robot_position = 'home'
                logger.info(f"✓ Robot position detected: Home")
            else:
                # Unknown position, default to home for safety
                st.session_state.robot_position = 'home'
                print(f"⚠ Robot at unknown position, defaulting to 'home'")
                
        except Exception as e:
            # Exception during query, default to home
            st.session_state.robot_position = 'home'
            print(f"⚠ Error querying robot position, defaulting to 'home': {e}")
    else:
        # Robot not connected, default to home
        st.session_state.robot_position = 'home'
if 'linear_stage_pos' not in st.session_state:
    # Query actual linear stage position from robot if available
    if st.session_state.get('robot_controller') is not None:
        try:
            code, pos = st.session_state.robot_controller.arm.get_linear_track_pos()
            if code == 0:  # Success
                st.session_state.linear_stage_pos = int(pos)  # pos is a number, not array
                logger.info(f"✓ Linear stage position detected: {st.session_state.linear_stage_pos}mm")
            else:
                # Query failed, default to PMT1 position
                st.session_state.linear_stage_pos = 1074
                print(f"⚠ Could not query linear stage position (code={code}), defaulting to 1074mm")
        except Exception as e:
            # Exception during query, default to PMT1 position
            st.session_state.linear_stage_pos = 1074
            print(f"⚠ Error querying linear stage position, defaulting to 1074mm: {e}")
    else:
        # Robot not connected, default to PMT1 position
        st.session_state.linear_stage_pos = 1074
if 'system_coordinator' not in st.session_state:
    st.session_state.system_coordinator = None
if 'robot_controller' not in st.session_state:
    st.session_state.robot_controller = None
if 'device_enabled' not in st.session_state:
    st.session_state.device_enabled = {
        'pmt_hv': False,
        'sipm': False,
        'siggen': False,
        'laser': False,
        'robot': False
    }

# Sync device states from actual hardware on first load (AFTER device_enabled exists)
if 'device_states_synced' not in st.session_state:
    st.session_state.device_states_synced = False
    
    # Sync signal generator state from device
    if st.session_state.get('api_client'):
        try:
            status = st.session_state.api_client.siggen_get_status(1)
            st.session_state.device_enabled['siggen'] = status.get('output_enabled', False)
            logger.info(f"Synced siggen state: {st.session_state.device_enabled['siggen']}")
        except Exception as e:
            print(f"Failed to sync siggen state: {e}")
            st.session_state.device_enabled['siggen'] = False
        
        # Sync PMT HV state from device
        try:
            for ch in range(1, 4):
                status = st.session_state.api_client.caen_get_status(ch)
                st.session_state.pmt_power[ch-1] = status.get('power_on', False)
            
            any_on = any(st.session_state.pmt_power)
            st.session_state.device_enabled['pmt_hv'] = any_on
            
            pmt_count = sum(st.session_state.pmt_power)
            logger.info(f"Synced PMT HV state: device_enabled={any_on}, {pmt_count}/3 PMTs on")
        except Exception as e:
            print(f"Failed to sync PMT HV state: {e}")
            st.session_state.device_enabled['pmt_hv'] = False
        
        # Sync laser state from device
        try:
            status = st.session_state.api_client.laser_get_status()
            st.session_state.laser_tec_on = status.get('tec_on', False)
            st.session_state.laser_ld_on = status.get('ld_on', False)
            laser_on = st.session_state.laser_tec_on and st.session_state.laser_ld_on
            st.session_state.device_enabled['laser'] = laser_on
            logger.info(f"Synced laser state: device_enabled={laser_on}, TEC={st.session_state.laser_tec_on}, LD={st.session_state.laser_ld_on}")
        except Exception as e:
            print(f"Failed to sync laser state: {e}")
            st.session_state.laser_tec_on = False
            st.session_state.laser_ld_on = False
            st.session_state.device_enabled['laser'] = False
    
    # Sync SiPM state from device
    if st.session_state.get('sipm_connected', False):
        try:
            sipm_on = st.session_state.sipm_supply.get_output_status()
            st.session_state.device_enabled['sipm'] = sipm_on
            logger.info(f"Synced SiPM state: {st.session_state.device_enabled['sipm']}")
        except Exception as e:
            print(f"Failed to sync SiPM state: {e}")
            st.session_state.device_enabled['sipm'] = False
    
    st.session_state.device_states_synced = True

if 'emergency_stop_confirm' not in st.session_state:
    st.session_state.emergency_stop_confirm = False
if 'custom_sequences' not in st.session_state:
    st.session_state.custom_sequences = {}
if 'pmt_serial_number' not in st.session_state:
    st.session_state.pmt_serial_number = {"pmt1": "", "pmt2": ""}
if 'laser_trigger_mode' not in st.session_state:
    st.session_state.laser_trigger_mode = "EXT"

if 'cleanup_registered' not in st.session_state:
    
    def cleanup_devices():
        """Cleanup software resources on exit - does NOT shut down hardware"""
        global _sipm_supply, _digitizer, _system_coordinator, _robot_controller
        
        print("\n" + "="*60)
        print("GUI CLOSING - Cleaning up software resources...")
        print("="*60)
        
        cleaned = []
        
        # Only close connections - do NOT turn off hardware
        # Hardware should remain in its current state
        
        if _sipm_supply is not None:
            try:
                _sipm_supply.close()  # Close connection only, do NOT turn OFF
                cleaned.append("✓ SiPM supply: Connection closed (output state unchanged)")
            except Exception as e:
                cleaned.append(f"⚠ SiPM: {e}")
        
        if _digitizer is not None:
            try:
                _digitizer.cleanup_temp_files()
                cleaned.append("✓ Digitizer: Temp files cleaned")
            except Exception as e:
                cleaned.append(f"⚠ Digitizer: {e}")

        if _robot_controller is not None:
            try:
                _robot_controller.arm.disconnect()
                cleaned.append("✓ xArm: Connection closed (position unchanged)")
            except Exception as e:
                cleaned.append(f"⚠ xArm: {e}")
        
        # Note: Robot, HV, laser, etc. remain in current state
        # Use Emergency Stop button if you need to shut down hardware
        
        if cleaned:
            for msg in cleaned:
                print(f"  {msg}")
        
        print("="*60)
        print("Cleanup complete. Hardware remains in current state.")
        print("Use Emergency Stop button if hardware shutdown needed.")
        print("="*60 + "\n")
        
        print("="*60)
        print("Cleanup complete. Safe to exit.")
        print("="*60 + "\n")
        sys.stdout.flush()
    
    atexit.register(cleanup_devices)
    st.session_state.cleanup_registered = True

# Device state sync is handled by:
# - First load: one-time sync block above (line ~973)
# - Run Sequence callbacks: optimistic state update + background API command  
# - Setup & Monitor: direct queries in each device tab

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.title("HyperK PMT DAQ")
    st.markdown("---")
    
    # Mode Selection
    st.subheader("Control Mode")
    
    # Auto-lock when switching away from Setup & Monitor
    previous_mode = st.session_state.get('previous_mode', 'Run Sequence')
    
    mode = st.radio(
        "Select Mode:",
        ["Run Sequence", "Setup & Monitor"],
        key='mode_selector',
        help="Run Sequence: Automated scans | Setup & Monitor: Expert control (password required)"
    )
    
    # Lock Setup & Monitor when switching away from it
    if previous_mode == "Setup & Monitor" and mode != "Setup & Monitor":
        st.session_state.authenticated = False
    
    st.session_state.mode = mode
    st.session_state.previous_mode = mode
    
    st.markdown("---")
    
    # System Status Summary
    st.subheader("System Status")
    
    # Overall system ready check
    pmt_ready = all(st.session_state.pmt_power) and not any(st.session_state.pmt_ramping)
    laser_ready = st.session_state.laser_ld_on and st.session_state.laser_tec_on
    robot_ready = st.session_state.robot_position == 'home'
    
    # Robot is always on, so don't check device_enabled['robot']
    all_systems_ready = (
        pmt_ready and 
        laser_ready and 
        robot_ready and 
        st.session_state.device_enabled['sipm'] and
        st.session_state.device_enabled['siggen']
    )
    
    if all_systems_ready:
        st.markdown(f"{status_dot('green')} All Systems Ready", unsafe_allow_html=True)
    else:
        st.markdown(f"{status_dot('yellow')} System Not Ready", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Individual device status
    st.caption("**Device Status:**")
    
    # PMT HV - Three-tier status:
    # - Green: All 3 PMTs on and not ramping
    # - Yellow/Orange: Some (but not all) PMTs on, OR any ramping
    # - Red: No PMTs on
    pmt_count_on = sum(st.session_state.pmt_power)
    if pmt_ready:  # All 3 on and not ramping
        pmt_status = 'green'
    elif any(st.session_state.pmt_ramping) or pmt_count_on > 0:  # Ramping or some on
        pmt_status = 'yellow'
    else:  # None on
        pmt_status = 'red'
    
    st.markdown(f"{status_dot(pmt_status)} PMT HV System", unsafe_allow_html=True)
    if any(st.session_state.pmt_ramping):
        st.caption("  ↳ Ramping...")
    elif pmt_count_on > 0 and pmt_count_on < 3:
        st.caption(f"  ↳ {pmt_count_on}/3 PMTs on")
    
    # SiPM
    if st.session_state.get('sipm_connected', False):
        if st.session_state.sipm_output_on:
            sipm_status = 'green'
        else:
            sipm_status = 'red'
    else:
        sipm_status = 'grey'

    st.markdown(f"{status_dot(sipm_status)} SiPM Supply", unsafe_allow_html=True)
    
    # Signal Gen - use session state (synced on changes)
    siggen_status = 'green' if st.session_state.device_enabled['siggen'] else 'red'
    st.markdown(f"{status_dot(siggen_status)} Signal Generator", unsafe_allow_html=True)
    
    # Laser - green only when BOTH TEC and LD are on
    laser_status = 'green' if laser_ready else ('yellow' if (st.session_state.laser_ld_on or st.session_state.laser_tec_on) else 'red')
    st.markdown(f"{status_dot(laser_status)} Laser System", unsafe_allow_html=True)
    if st.session_state.laser_tec_on and not st.session_state.laser_ld_on:
        st.caption("  ↳ TEC only")
    elif st.session_state.laser_ld_on and not st.session_state.laser_tec_on:
        st.caption("  ↳ LD only (unsafe!)")
    
    # Robot - green only at home
    robot_status = 'green' if robot_ready else 'yellow'
    st.markdown(f"{status_dot(robot_status)} Robot System", unsafe_allow_html=True)
    if not robot_ready:
        st.caption(f"  ↳ At {st.session_state.robot_position}")
    
    # Digitizer Status
    if st.session_state.get('digitizer_connected', False):
        status = st.session_state.get('digitizer_status', {})
        if status.get('connected') and status.get('kernel_module'):
            st.markdown(f"{status_dot('green')} CAEN Digitizer", unsafe_allow_html=True)
        elif status.get('connected'):
            st.markdown(f"{status_dot('yellow')} CAEN Digitizer", unsafe_allow_html=True)
            st.caption("  ↳ Module not loaded")
        else:
            st.markdown(f"{status_dot('red')} CAEN Digitizer", unsafe_allow_html=True)
    else:
        st.markdown(f"{status_dot('grey')} CAEN Digitizer", unsafe_allow_html=True)

    st.markdown("---")
    
    # Emergency Stop with confirmation
    st.error("**EMERGENCY CONTROLS**")
    
    if not st.session_state.emergency_stop_confirm:
        if st.button("🛑 EMERGENCY STOP", key='emergency_1'):
            st.session_state.emergency_stop_confirm = True
            st.rerun()
    else:
        st.warning("⚠️ Confirm Emergency Stop?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✓ YES", key='emergency_yes'):
                # Execute emergency stop using system coordinator
                if st.session_state.system_coordinator is not None:
                    try:
                        result = st.session_state.system_coordinator.emergency_shutdown_all(
                            reason="Emergency stop button pressed in GUI"
                        )
                        if result['overall_success']:
                            st.error("🚨 EMERGENCY STOP ACTIVATED - All systems shut down")
                        else:
                            st.error(f"⚠️ Emergency stop completed with errors: {result}")
                    except Exception as e:
                        st.error(f"Emergency stop failed: {e}")
                
                # Also update GUI state
                st.session_state.pmt_power = [False, False, False]
                st.session_state.pmt_ramping = [False, False, False]
                st.session_state.laser_ld_on = False
                st.session_state.laser_tec_on = False
                st.session_state.run_active = False
                st.session_state.device_enabled = {k: False for k in st.session_state.device_enabled}
                st.session_state.emergency_stop_confirm = False
                logger.warning("[EMERGENCY] All devices shut down via emergency stop button")
                time.sleep(1)
                st.rerun()
        with col2:
            if st.button("✗ NO", key='emergency_no'):
                st.session_state.emergency_stop_confirm = False
                st.rerun()
    
    st.markdown("---")
    
    # Quick Info
    st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if st.session_state.scheduled_start:
        remaining = (st.session_state.scheduled_start - datetime.now()).total_seconds()
        if remaining > 0:
            st.caption(f"⏱️ Scheduled: {int(remaining/3600)}h {int((remaining%3600)/60)}m")


# ============================================================================
# MAIN CONTENT
# ============================================================================

if st.session_state.mode == "Setup & Monitor":
    # ========================================================================
    # SETUP MODE - PASSWORD PROTECTED
    # ========================================================================
    
    if not st.session_state.authenticated:
        st.title("🔒 Setup & Monitor Mode")
        st.warning("This mode requires authentication. Please enter the password.")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            # Use form so Enter key works
            with st.form("auth_form"):
                password = st.text_input("Password:", type="password", key="auth_password")
                submit_button = st.form_submit_button("Unlock", use_container_width=True)
                
                if submit_button:
                    if check_password(password):
                        st.session_state.authenticated = True
                        st.success("Access granted!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Incorrect password")
        
        st.markdown("---")
        st.info("**Note:** This mode provides direct control over all hardware. Only authorized personnel should access this mode.")
        st.stop()

    # Authenticated - show controls
    st.title("Setup & Monitor Mode")
    st.caption("⚠️ Expert mode - Manual control of all devices")
    
    col1, col2, col3 = st.columns([5, 1, 1])
    with col2:
        if st.button("🔄 Refresh", use_container_width=True, key="manual_refresh_setup"):
            st.rerun()
    with col3:
        if st.button("🔒 Lock", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()
    
    st.markdown("---")
    
    # Device Control Tabs
    tabs = st.tabs([
        "PMT High Voltage", 
        "SiPM Supply", 
        "Signal Generator", 
        "Laser Control",
        "Robot Control",
        "DAQ Control"
    ])
    
    # TAB 1: PMT HV
    with tabs[0]:
        st.subheader("CAEN DT5533E - PMT High Voltage")
        
        if not st.session_state.get('api_connected', False):
            st.error("❌ Windows API server not connected")
            st.info("Check that device_api_server.py is running on Windows machine")
            st.code("python device_api_server.py", language="bash")
        else:
            # Mode-level auto-refresh handles updates
            
            # PMT channel mapping (channels 1-3 for PMT1-3, channel 0 unused)
            for i in range(1, 4):  # Channels 1, 2, 3
                with st.expander(f"Channel {i} (PMT {i})", expanded=(i==1)):
                    # Get real-time status from API
                    try:
                        channel_status = st.session_state.api_client.caen_get_status(i)
                        st.session_state.caen_channels[i]['voltage_mon'] = channel_status['voltage_mon']
                        st.session_state.caen_channels[i]['current_mon'] = channel_status['current_mon']
                        st.session_state.caen_channels[i]['power_on'] = channel_status['power_on']
                        st.session_state.caen_channels[i]['voltage_set'] = channel_status['voltage_set']
                        st.session_state.caen_channels[i]['current_set'] = channel_status.get('current_set', 50.0)
                        st.session_state.caen_channels[i]['ramp_up'] = channel_status['ramp_up']
                        st.session_state.caen_channels[i]['ramp_down'] = channel_status['ramp_down']
                        st.session_state.caen_channels[i]['status'] = channel_status.get('status', {})
                        
                        # Determine if ramping (voltage not at setpoint)
                        v_mon = channel_status['voltage_mon']
                        v_set = channel_status['voltage_set']
                        is_ramping = channel_status['power_on'] and abs(v_mon - v_set) > 10  # 10V tolerance
                        st.session_state.caen_channels[i]['ramping'] = is_ramping
                        
                    except Exception as e:
                        st.error(f"Failed to read channel {i}: {e}")
                        v_mon = st.session_state.caen_channels[i]['voltage_mon']
                        is_ramping = st.session_state.caen_channels[i]['ramping']
                    
                    col1, col2, col3 = st.columns([2, 2, 1])
                    
                    with col1:
                        st.markdown("**Setpoints:**")
                        
                        # Get current values from session state
                        current_v_set = st.session_state.caen_channels[i]['voltage_set']
                        current_i_set = st.session_state.caen_channels[i]['current_set']
                        current_ramp_up = st.session_state.caen_channels[i]['ramp_up']
                        current_ramp_down = st.session_state.caen_channels[i]['ramp_down']
                        
                        voltage = st.number_input(
                            "Voltage (V)", 
                            min_value=0, 
                            max_value=2000, 
                            value=int(current_v_set),
                            step=50,
                            key=f'pmt_v_{i}',
                            help="Target voltage setpoint"
                        )
                        current_limit = st.number_input(
                            "Current Limit (µA)", 
                            min_value=0.0, 
                            max_value=3000.0, 
                            value=current_i_set,
                            step=10.0,
                            key=f'pmt_i_{i}',
                            help="Overcurrent protection limit"
                        )
                        
                        col_ramp1, col_ramp2 = st.columns(2)
                        with col_ramp1:
                            ramp_up = st.number_input(
                                "Ramp Up (V/s)",
                                min_value=1,
                                max_value=500,
                                value=int(current_ramp_up),
                                step=10,
                                key=f'pmt_ramp_up_{i}',
                                help="Voltage increase rate"
                            )
                        with col_ramp2:
                            ramp_down = st.number_input(
                                "Ramp Down (V/s)",
                                min_value=1,
                                max_value=500,
                                value=int(current_ramp_down),
                                step=10,
                                key=f'pmt_ramp_down_{i}',
                                help="Voltage decrease rate"
                            )
                        
                        # Apply configuration button
                        if st.button("Apply Config", key=f'pmt_apply_{i}', use_container_width=True):
                            try:
                                st.session_state.api_client.caen_configure_channel(
                                    channel=i,
                                    voltage=voltage,
                                    current_limit=current_limit,
                                    ramp_up=ramp_up,
                                    ramp_down=ramp_down
                                )
                                st.success(f"✓ Channel {i} configured")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Configuration failed: {e}")
                    
                    with col2:
                        st.markdown("**Monitoring:**")
                        
                        # Status with proper color coding
                        power_on = st.session_state.caen_channels[i]['power_on']
                        
                        if power_on:
                            if is_ramping:
                                status_text = f"{status_dot('yellow')} Ramping"
                            else:
                                status_text = f"{status_dot('green')} On"
                        else:
                            status_text = f"{status_dot('grey')} Off"
                        
                        st.markdown(status_text, unsafe_allow_html=True)
                        
                        # Real-time metrics
                        v_mon = st.session_state.caen_channels[i]['voltage_mon']
                        i_mon = st.session_state.caen_channels[i]['current_mon']
                        
                        col_v, col_i = st.columns(2)
                        with col_v:
                            st.metric("Voltage (V)", f"{v_mon:.1f}")
                            st.caption(f"Set: {current_v_set:.0f}V")
                        with col_i:
                            st.metric("Current (µA)", f"{i_mon:.2f}")
                            st.caption(f"Limit: {current_i_set:.0f}µA")
                        
                        # Status flags (if available)
                        status_flags = st.session_state.caen_channels[i]['status']
                        if status_flags:
                            warnings = []
                            if status_flags.get('overcurrent'):
                                warnings.append("⚠️ Overcurrent")
                            if status_flags.get('overvoltage'):
                                warnings.append("⚠️ Overvoltage")
                            if status_flags.get('trip'):
                                warnings.append("🛑 Tripped")
                            
                            if warnings:
                                for warning in warnings:
                                    st.warning(warning)
                    
                    with col3:
                        st.markdown("**Control:**")
                        st.write(" ")
                        
                        if not power_on:
                            if st.button(f"Turn ON", key=f'pmt_on_{i}', use_container_width=True):
                                try:
                                    st.session_state.api_client.caen_set_power(i, True)
                                    st.session_state.caen_channels[i]['power_on'] = True
                                    st.session_state.caen_channels[i]['ramping'] = True
                                    st.session_state.device_enabled['pmt_hv'] = True
                                    logger.info(f"[PMT_HV] Channel {i} turned ON (Setup & Monitor)")
                                    st.success(f"✓ Channel {i} ON")
                                    time.sleep(0.3)
                                    st.rerun()
                                except Exception as e:
                                    logger.error(f"[PMT_HV] Channel {i} ON failed: {e}")
                                    st.error(f"Power on failed: {e}")
                        else:
                            if st.button(f"Turn OFF", key=f'pmt_off_{i}', use_container_width=True):
                                try:
                                    st.session_state.api_client.caen_set_power(i, False)
                                    st.session_state.caen_channels[i]['power_on'] = False
                                    st.session_state.caen_channels[i]['ramping'] = False
                                    
                                    # Update overall device status
                                    any_on = any(st.session_state.caen_channels[ch]['power_on'] for ch in range(1, 4))
                                    st.session_state.device_enabled['pmt_hv'] = any_on
                                    logger.info(f"[PMT_HV] Channel {i} turned OFF, any_on={any_on} (Setup & Monitor)")
                                    
                                    st.info(f"✓ Channel {i} OFF")
                                    time.sleep(0.3)
                                    st.rerun()
                                except Exception as e:
                                    logger.error(f"[PMT_HV] Channel {i} OFF failed: {e}")
                                    st.error(f"Power off failed: {e}")
            
            st.markdown("---")
            
            # Real-time current monitoring graphs
            st.markdown("### 📊 Current Monitoring")
            
            # Collect history data (only when any channel is powered)
            any_powered = any(st.session_state.caen_channels[ch]['power_on'] for ch in range(1, 4))
            
            if any_powered:
                from datetime import datetime
                now = datetime.now()
                max_points = 100
                
                # Add current readings to history
                for ch_num in range(1, 4):
                    i_mon = st.session_state.caen_channels[ch_num]['current_mon']
                    st.session_state.caen_current_history[f'ch{ch_num}'].append(i_mon)
                
                st.session_state.caen_current_history['timestamps'].append(now)
                
                # Trim to max points
                if len(st.session_state.caen_current_history['timestamps']) > max_points:
                    for key in st.session_state.caen_current_history:
                        st.session_state.caen_current_history[key] = st.session_state.caen_current_history[key][-max_points:]
            
            if len(st.session_state.caen_current_history['timestamps']) > 0:
                
                col1, col2, col3 = st.columns(3)
                
                for idx, col in enumerate([col1, col2, col3], start=1):
                    with col:
                        st.markdown(f"**Ch{idx} Current**")
                        i_df = pd.DataFrame({
                            'Time': st.session_state.caen_current_history['timestamps'],
                            'Current (µA)': st.session_state.caen_current_history[f'ch{idx}']
                        })
                        st.line_chart(i_df.set_index('Time'), height=200)
                
                # Clear and refresh buttons
                col_clear, col_refresh = st.columns(2)
                with col_clear:
                    if st.button("🗑️ Clear History", key="clear_caen_history"):
                        st.session_state.caen_current_history = {
                            'ch1': [], 'ch2': [], 'ch3': [], 'timestamps': []
                        }
                        st.rerun()
                with col_refresh:
                    if st.button("🔄 Update", key="refresh_caen_manual"):
                        st.rerun()
            else:
                st.info("📈 Turn on any channel to start monitoring current")
                if st.button("🔄 Update", key="refresh_caen_manual_nodata"):
                    st.rerun()
            
    # TAB 2: SiPM Supply
    with tabs[1]:
        st.subheader("IPS-2303S SiPM Power Supply")
        
        if not st.session_state.get('sipm_connected', False):
            st.error("❌ SiPM supply not connected")
            st.info("Check USB connection and permissions")
        else:
            # Get real-time values
            if st.session_state.sipm_output_on:
                try:
                    ch1_v = st.session_state.sipm_supply.get_voltage(1)
                    ch1_i = st.session_state.sipm_supply.get_current(1)
                    ch2_v = st.session_state.sipm_supply.get_voltage(2)
                    ch2_i = st.session_state.sipm_supply.get_current(2)
                except:
                    ch1_v = ch1_i = ch2_v = ch2_i = 0.0
            else:
                ch1_v = ch1_i = ch2_v = ch2_i = 0.0
            
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                st.markdown("**Channel 1:**")
                
                # Get actual setpoints from hardware
                try:
                    set_v1 = st.session_state.sipm_supply.get_voltage_setpoint(1)
                    set_i1 = st.session_state.sipm_supply.get_current_setpoint(1)
                except:
                    set_v1 = 5.0
                    set_i1 = 1.0
                
                st.text(f"Set Voltage: {set_v1:.2f} V")
                st.text(f"Set Current: {set_i1:.3f} A")
                
                st.metric("Measured V", f"{ch1_v:.3f} V")
                st.metric("Measured I", f"{ch1_i*1000:.2f} mA")  # Convert A to mA

            with col2:
                st.markdown("**Channel 2:**")
                
                # Get actual setpoints from hardware
                try:
                    set_v2 = st.session_state.sipm_supply.get_voltage_setpoint(2)
                    set_i2 = st.session_state.sipm_supply.get_current_setpoint(2)
                except:
                    set_v2 = 5.0
                    set_i2 = 1.0
                
                st.text(f"Set Voltage: {set_v2:.2f} V")
                st.text(f"Set Current: {set_i2:.3f} A")
                
                st.metric("Measured V", f"{ch2_v:.3f} V")
                st.metric("Measured I", f"{ch2_i*1000:.2f} mA")  # Convert A to mA
            
            with col3:
                st.markdown("**Output Control:**")
                st.write(" ")
                
                # Status indicator
                if st.session_state.sipm_output_on:
                    st.markdown(f"{status_dot('green')} Output ON", unsafe_allow_html=True)
                else:
                    st.markdown(f"{status_dot('grey')} Output OFF", unsafe_allow_html=True)
                
                st.write(" ")
                st.write(" ")
                
                # Output control buttons
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button(
                        "Turn ON",
                        key="sipm_real_enable",
                        use_container_width=True,
                        disabled=st.session_state.sipm_output_on
                    ):
                        try:
                            st.session_state.sipm_supply.ON()
                            st.session_state.sipm_output_on = True
                            st.session_state.device_enabled['sipm'] = True
                            logger.info("[SiPM] Output turned ON (Setup & Monitor)")
                            st.success("✓ Output enabled")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            logger.error(f"[SiPM] ON failed: {e}")
                            st.error(f"Failed to enable output: {e}")
                
                with col_b:
                    if st.button(
                        "Turn OFF",
                        key="sipm_real_disable",
                        use_container_width=True,
                        disabled=not st.session_state.sipm_output_on
                    ):
                        try:
                            st.session_state.sipm_supply.OFF()
                            st.session_state.sipm_output_on = False
                            st.session_state.device_enabled['sipm'] = False
                            logger.info("[SiPM] Output turned OFF (Setup & Monitor)")
                            st.info("✓ Output disabled")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            logger.error(f"[SiPM] OFF failed: {e}")
                            st.error(f"Failed to disable output: {e}")
            
            st.markdown("---")

            # Initialize session state for graph data
            if 'sipm_voltage_history' not in st.session_state:
                st.session_state.sipm_voltage_history = {
                    'ch1': [],
                    'ch2': [],
                    'timestamps': []
                }

            if 'sipm_current_history' not in st.session_state:
                st.session_state.sipm_current_history = {
                    'ch1': [],
                    'ch2': [],
                    'timestamps': []
                }

            # Collect data when output is ON
            if st.session_state.get('sipm_connected', False) and st.session_state.sipm_output_on:
                try:
                    from datetime import datetime
                    now = datetime.now()
                    
                    # Limit to last 100 points
                    max_points = 100
                    
                    # Add voltage data
                    st.session_state.sipm_voltage_history['ch1'].append(ch1_v)
                    st.session_state.sipm_voltage_history['ch2'].append(ch2_v)
                    st.session_state.sipm_voltage_history['timestamps'].append(now)
                    
                    # Add current data (convert to mA)
                    st.session_state.sipm_current_history['ch1'].append(ch1_i * 1000)
                    st.session_state.sipm_current_history['ch2'].append(ch2_i * 1000)
                    st.session_state.sipm_current_history['timestamps'].append(now)
                    
                    # Trim to max points
                    if len(st.session_state.sipm_voltage_history['timestamps']) > max_points:
                        for history in [st.session_state.sipm_voltage_history, 
                                    st.session_state.sipm_current_history]:
                            history['ch1'] = history['ch1'][-max_points:]
                            history['ch2'] = history['ch2'][-max_points:]
                            history['timestamps'] = history['timestamps'][-max_points:]
                except:
                    pass

            st.markdown("---")
            st.markdown("### 📊 Real-time Monitoring")

            # Show graphs if we have data
            if len(st.session_state.sipm_voltage_history['timestamps']) > 0:
                
                # Voltage graphs (side by side)
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Channel 1 Voltage**")
                    v_df_ch1 = pd.DataFrame({
                        'Time': st.session_state.sipm_voltage_history['timestamps'],
                        'Voltage (V)': st.session_state.sipm_voltage_history['ch1']
                    })
                    st.line_chart(v_df_ch1.set_index('Time'), height=200)
                
                with col2:
                    st.markdown("**Channel 2 Voltage**")
                    v_df_ch2 = pd.DataFrame({
                        'Time': st.session_state.sipm_voltage_history['timestamps'],
                        'Voltage (V)': st.session_state.sipm_voltage_history['ch2']
                    })
                    st.line_chart(v_df_ch2.set_index('Time'), height=200)
                
                # Current graphs (side by side)
                col3, col4 = st.columns(2)
                
                with col3:
                    st.markdown("**Channel 1 Current**")
                    i_df_ch1 = pd.DataFrame({
                        'Time': st.session_state.sipm_current_history['timestamps'],
                        'Current (mA)': st.session_state.sipm_current_history['ch1']
                    })
                    st.line_chart(i_df_ch1.set_index('Time'), height=200)
                
                with col4:
                    st.markdown("**Channel 2 Current**")
                    i_df_ch2 = pd.DataFrame({
                        'Time': st.session_state.sipm_current_history['timestamps'],
                        'Current (mA)': st.session_state.sipm_current_history['ch2']
                    })
                    st.line_chart(i_df_ch2.set_index('Time'), height=200)
                
                # Control buttons
                col_clear, col_refresh = st.columns([1, 1])
                with col_clear:
                    if st.button("🗑️ Clear History", key="clear_sipm_history"):
                        st.session_state.sipm_voltage_history = {'ch1': [], 'ch2': [], 'timestamps': []}
                        st.session_state.sipm_current_history = {'ch1': [], 'ch2': [], 'timestamps': []}
                        st.rerun()
                
                with col_refresh:
                    if st.button("🔄 Update Reading", key="refresh_sipm_manual"):
                        st.rerun()

            else:
                st.info("📈 Turn output ON to start collecting data for graphs")
                if st.button("🔄 Update Reading", key="refresh_sipm_manual_nodata"):
                    st.rerun()
            
            # Optional: Show system status
            with st.expander("📊 System Status Details"):
                try:
                    status = st.session_state.sipm_supply.get_status()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text(f"CH1 Voltage: {status.get('ch1_v', 0):.3f} V")
                        st.text(f"CH2 Voltage: {status.get('ch2_v', 0):.3f} V")
                    with col2:
                        st.text(f"Output: {'ON' if status.get('output_on') else 'OFF'}")
                        st.text(f"Connected: {'Yes' if status.get('connected') else 'No'}")
                except Exception as e:
                    st.error(f"Could not read status: {e}")
                
    # TAB 3: Signal Generator
    with tabs[2]:
        st.subheader("Siglent SDG1032X Signal Generator")
        
        if not st.session_state.get('api_client'):
            st.error("⚠️ Windows API not connected")
            st.info("Check that device_api_server.py is running on Windows machine")
        else:
            try:
                channel = 1  # We typically use channel 1
                
                # Refresh status after any changes
                status = st.session_state.api_client.siggen_get_status(channel)
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown("**Waveform Configuration:**")
                    
                    # Map device waveform to selectbox index
                    waveform_options = ["SINE", "SQUARE", "PULSE", "RAMP", "NOISE"]
                    current_waveform = status.get('waveform', 'PULSE')
                    try:
                        waveform_index = waveform_options.index(current_waveform)
                    except ValueError:
                        waveform_index = 2  # Default to PULSE if unknown
                    
                    waveform = st.selectbox(
                        "Waveform:",
                        waveform_options,
                        index=waveform_index,  # Use actual device value
                        key="siggen_wave_type"
                    )
                    
                    frequency = st.number_input(
                        "Frequency (Hz)",
                        min_value=1.0,
                        max_value=30000000.0,
                        value=float(status.get('frequency', 1000.0)),  # Use actual device value
                        format="%.1f",
                        key="siggen_freq"
                    )
                    
                    amplitude = st.number_input(
                        "Amplitude (V)",
                        min_value=0.0,
                        max_value=10.0,
                        value=float(status.get('amplitude', 5.5)),  # Use actual device value
                        step=0.1,
                        key="siggen_amp"
                    )
                    
                    offset = st.number_input(
                        "Offset (V)",
                        min_value=-5.0,
                        max_value=5.0,
                        value=float(status.get('offset', 2.0)),  # Use actual device value
                        step=0.1,
                        key="siggen_offset"
                    )
                    
                    if waveform == "PULSE":
                        pulse_width = st.number_input(
                            "Pulse Width (ns)",
                            min_value=8.0,
                            max_value=1000000.0,
                            value=32.6,
                            step=1.0,
                            key="siggen_pulse_width"
                        )
                        
                        pulse_unit = st.selectbox(
                            "Unit:",
                            ["ns", "us", "ms", "s"],
                            index=0,
                            key="siggen_pulse_unit"
                        )
                
                with col2:
                    st.markdown("**Status:**")
                    st.write(" ")
                    
                    # Get fresh output status from API
                    output_on = status.get('output_enabled', False)
                    if output_on:
                        st.markdown(f"{status_dot('green')} Output ON", unsafe_allow_html=True)
                    else:
                        st.markdown(f"{status_dot('grey')} Output OFF", unsafe_allow_html=True)
                    
                    st.write(" ")
                    st.write(" ")
                    
                    # Output control
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button(
                            "Turn ON",
                            key="siggen_enable",
                            use_container_width=True,
                            disabled=output_on
                        ):
                            try:
                                st.session_state.api_client.siggen_enable_output(channel, True)
                                st.session_state.device_enabled['siggen'] = True  # Sync session state
                                logger.info(f"[SIGGEN] Output turned ON, channel={channel} (Setup & Monitor)")
                                time.sleep(1.0)  # Wait for device to update
                                st.success("✓ Output enabled")
                                st.rerun()
                            except Exception as e:
                                logger.error(f"[SIGGEN] ON failed: {e}")
                                st.error(f"Failed to enable: {e}")
                    
                    with col_b:
                        if st.button(
                            "Turn OFF",
                            key="siggen_disable",
                            use_container_width=True,
                            disabled=not output_on
                        ):
                            try:
                                st.session_state.api_client.siggen_enable_output(channel, False)
                                st.session_state.device_enabled['siggen'] = False  # Sync session state
                                logger.info(f"[SIGGEN] Output turned OFF, channel={channel} (Setup & Monitor)")
                                time.sleep(1.0)  # Wait for device to update
                                st.info("✓ Output disabled")
                                st.rerun()
                            except Exception as e:
                                logger.error(f"[SIGGEN] OFF failed: {e}")
                                st.error(f"Failed to disable: {e}")
                
                st.markdown("---")
                
                # Apply configuration button
                if st.button("📝 Apply Configuration", key="siggen_apply", use_container_width=True):
                    try:
                        # Build configuration
                        config = {
                            'waveform': waveform,
                            'frequency': frequency,
                            'amplitude': amplitude,
                            'offset': offset
                        }
                        
                        # Add pulse width if PULSE waveform
                        if waveform == "PULSE":
                            config['pulse_width'] = pulse_width
                            config['pulse_width_unit'] = pulse_unit
                        
                        # Apply to device
                        st.session_state.api_client.siggen_set_waveform(channel, **config)
                        st.success("✓ Configuration applied")
                        time.sleep(0.5)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Configuration failed: {e}")
                
                # Manual refresh button
                if st.button("🔄 Refresh Status", key="siggen_refresh_manual"):
                    st.rerun()
            
            except Exception as e:
                st.error(f"Failed to communicate with signal generator: {e}")
                st.info("Check Windows API server connection")
    
    # TAB 4: Laser Control
    with tabs[3]:
        st.subheader("Tama Electric LSB-200 Picosecond Laser")
        
        if not st.session_state.get('api_client'):
            st.error("⚠️ Windows API not connected")
        else:
            try:
                status = st.session_state.api_client.laser_get_status()
                
                # Store in session state
                st.session_state.laser_tec_on = status.get('tec_on', False)
                st.session_state.laser_ld_on = status.get('ld_on', False)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Temperature Controller (TEC):**")
                    
                    # Temperature setpoint
                    temp_setpoint = st.number_input(
                        "Temperature Setpoint (°C)",
                        min_value=15.0,
                        max_value=35.0,
                        value=float(status.get('ld_temp_setpoint', 25.0)),
                        step=0.1,
                        key="laser_temp_set"
                    )
                    
                    # Current readings
                    actual_temp = status.get('ld_temp_actual', 0)
                    board_temp = status.get('board_temp', 0)
                    
                    col_t1, col_t2 = st.columns(2)
                    with col_t1:
                        # Color-code temperature based on stability
                        temp_diff = abs(actual_temp - temp_setpoint)
                        if st.session_state.laser_tec_on:
                            if temp_diff < 0.5:
                                temp_color = "normal"  # Green
                            else:
                                temp_color = "off"  # Yellow/warming up
                        else:
                            temp_color = "normal"
                        
                        st.metric(
                            "LD Temp", 
                            f"{actual_temp:.2f} °C",
                            delta=f"{temp_diff:.2f}°C from set" if st.session_state.laser_tec_on else None
                        )
                    with col_t2:
                        st.metric("Board Temp", f"{board_temp:.2f} °C")
                        if board_temp > 42:
                            st.caption("⚠️ High")
                        elif board_temp > 30:
                            st.caption("Normal")
                        else:
                            st.caption("Cool")
                    
                    # TEC status with stability indicator
                    if st.session_state.laser_tec_on:
                        temp_stable = abs(actual_temp - temp_setpoint) < 0.5
                        if temp_stable:
                            st.markdown(f"{status_dot('green')} TEC ON (Stable ✓)", unsafe_allow_html=True)
                        else:
                            st.markdown(f"{status_dot('yellow')} TEC ON (Δ{temp_diff:.2f}°C)", unsafe_allow_html=True)
                            st.caption(f"Stabilizing... ({temp_diff:.2f}°C from setpoint)")
                    else:
                        st.markdown(f"{status_dot('grey')} TEC OFF", unsafe_allow_html=True)
                    
                    # TEC controls
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button(
                            "TEC ON",
                            key="laser_tec_on_btn",
                            use_container_width=True,
                            disabled=st.session_state.laser_tec_on
                        ):
                            try:
                                st.session_state.api_client.laser_set_temperature(temp_setpoint)
                                st.session_state.api_client.laser_set_tec_power(True)
                                st.session_state.laser_tec_on = True
                                logger.info(f"[LASER] TEC turned ON, setpoint={temp_setpoint}°C (Setup & Monitor)")
                                st.success("✓ TEC enabled - waiting for stabilization...")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                logger.error(f"[LASER] TEC ON failed: {e}")
                                st.error(f"Failed to enable TEC: {e}")
                    
                    with col_b:
                        if st.button(
                            "TEC OFF",
                            key="laser_tec_off_btn",
                            use_container_width=True,
                            disabled=not st.session_state.laser_tec_on
                        ):
                            try:
                                # Turn off LD first if it's on
                                if st.session_state.laser_ld_on:
                                    st.session_state.api_client.laser_set_ld_power(False)
                                    st.session_state.laser_ld_on = False
                                    logger.info("[LASER] LD turned OFF (safety shutdown before TEC OFF)")
                                
                                st.session_state.api_client.laser_set_tec_power(False)
                                st.session_state.laser_tec_on = False
                                st.session_state.device_enabled['laser'] = False
                                logger.info("[LASER] TEC turned OFF (Setup & Monitor)")
                                st.info("✓ TEC disabled")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                logger.error(f"[LASER] TEC OFF failed: {e}")
                                st.error(f"Failed to disable TEC: {e}")
                
                with col2:
                    st.markdown("**Laser Diode (LD):**")
                    
                    # Current settings
                    pulse_current = st.number_input(
                        "Pulse Current (mA)",
                        min_value=0.0,
                        max_value=200.0,
                        value=float(status.get('pulse_current', 50.0)),
                        step=1.0,
                        key="laser_pulse_current"
                    )
                    
                    bias_current = st.number_input(
                        "Bias Current (mA)",
                        min_value=0.0,
                        max_value=200.0,
                        value=float(status.get('bias_current', 0.0)),
                        step=1.0,
                        key="laser_bias_current"
                    )
                    
                    # Trigger mode
                    trigger_mode = st.selectbox(
                        "Trigger Mode:",
                        ["EXT", "PG1", "PG2"],
                        index=["EXT", "PG1", "PG2"].index(st.session_state.get('laser_trigger_mode', 'EXT')),
                        key="laser_trigger_select"
                    )
                    st.session_state.laser_trigger_mode = trigger_mode
                    
                    # Current readings
                    col_c1, col_c2 = st.columns(2)
                    with col_c1:
                        st.metric("Pulse I", f"{status.get('pulse_current', 0):.1f} mA")
                    with col_c2:
                        st.metric("PD Current", f"{status.get('pd_current', 0):.3f} pA")
                    
                    # LD status
                    if st.session_state.laser_ld_on:
                        st.markdown(f"{status_dot('green')} LD ON", unsafe_allow_html=True)
                    else:
                        st.markdown(f"{status_dot('grey')} LD OFF", unsafe_allow_html=True)
                    
                    # LD controls with safety check
                    col_a, col_b = st.columns(2)
                    with col_a:
                        # Safety check: TEC must be on AND temperature stable
                        tec_ready = st.session_state.laser_tec_on and abs(actual_temp - temp_setpoint) < 0.5
                        
                        if st.button(
                            "LD ON",
                            key="laser_ld_on_btn",
                            use_container_width=True,
                            disabled=st.session_state.laser_ld_on or not tec_ready
                        ):
                            try:
                                # Configure currents
                                st.session_state.api_client.laser_configure(
                                    pulse_current=pulse_current,
                                    bias_current=bias_current
                                )
                                
                                # Set trigger mode
                                if trigger_mode == "EXT":
                                    st.session_state.api_client.laser_set_oscillator(
                                        pg1_enabled=False,
                                        pg2_enabled=False,
                                        ext_enabled=True
                                    )
                                
                                # Enable LD
                                st.session_state.api_client.laser_set_ld_power(True)
                                st.session_state.laser_ld_on = True
                                st.session_state.device_enabled['laser'] = True
                                logger.info(f"[LASER] LD turned ON, pulse_current={pulse_current}mA, bias_current={bias_current}mA, trigger={trigger_mode} (Setup & Monitor)")
                                st.success("✓ LD enabled")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                logger.error(f"[LASER] LD ON failed: {e}")
                                st.error(f"Failed to enable LD: {e}")
                        
                        # Show why LD can't be enabled
                        if not tec_ready and not st.session_state.laser_ld_on:
                            if not st.session_state.laser_tec_on:
                                st.caption("⚠️ Enable TEC first")
                            else:
                                temp_diff = abs(actual_temp - temp_setpoint)
                                st.caption(f"⚠️ Wait for temp stability ({temp_diff:.2f}°C)")
                    
                    with col_b:
                        if st.button(
                            "LD OFF",
                            key="laser_ld_off_btn",
                            use_container_width=True,
                            disabled=not st.session_state.laser_ld_on
                        ):
                            try:
                                st.session_state.api_client.laser_set_ld_power(False)
                                st.session_state.laser_ld_on = False
                                logger.info("[LASER] LD turned OFF (Setup & Monitor)")
                                st.info("✓ LD disabled")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                logger.error(f"[LASER] LD OFF failed: {e}")
                                st.error(f"Failed to disable LD: {e}")
                
                st.markdown("---")
                
                # Apply configuration
                if st.button("📝 Apply Configuration", key="laser_apply", use_container_width=True):
                    try:
                        st.session_state.api_client.laser_configure(
                            temperature=temp_setpoint,
                            pulse_current=pulse_current,
                            bias_current=bias_current
                        )
                        st.success("✓ Configuration applied")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Configuration failed: {e}")
                
                # Initialize history if needed
                if 'laser_history' not in st.session_state:
                    st.session_state.laser_history = {
                        'ld_temp': [],
                        'board_temp': [],
                        'pulse_current': [],
                        'pd_current': [],
                        'timestamps': []
                    }
            
            except Exception as e:
                st.error(f"Failed to communicate with laser: {e}")
                st.info("Check Windows API server connection")
    
    # TAB 5: Robot Control
    with tabs[4]:
        st.subheader("xArm + Linear Stage Control")
        
        # Controller Status
        if st.session_state.robot_controller is not None:
            st.success("✅ Robot controller connected")
        else:
            st.error("❌ Robot controller not connected - check startup logs")
        
        st.markdown("---")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("**Linear Stage:**")
            
            # Progress bar for linear stage position
            stage_min = 240  # PMT2
            stage_max = 1074  # PMT1
            stage_range = stage_max - stage_min
            stage_progress = (st.session_state.linear_stage_pos - stage_min) / stage_range
            
            st.progress(max(0.0, min(1.0, stage_progress)))
            st.caption(f"Position: {st.session_state.linear_stage_pos} mm")
            
            # Quick position buttons
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("📍 PMT1 (1074mm)", key="stage_pmt1", use_container_width=True):
                    if st.session_state.robot_controller is not None:
                        try:
                            st.session_state.robot_controller.move_to_pmt(1)
                            st.session_state.linear_stage_pos = 1074
                            st.success("✓ Moved to PMT1")
                        except Exception as e:
                            st.error(f"Failed to move to PMT1: {e}")
                    else:
                        st.warning("⚠️ Robot controller not initialized")
                    st.rerun()
            with col_b:
                if st.button("📍 PMT2 (240mm)", key="stage_pmt2", use_container_width=True):
                    if st.session_state.robot_controller is not None:
                        try:
                            st.session_state.robot_controller.move_to_pmt(2)
                            st.session_state.linear_stage_pos = 240
                            st.success("✓ Moved to PMT2")
                        except Exception as e:
                            st.error(f"Failed to move to PMT2: {e}")
                    else:
                        st.warning("⚠️ Robot controller not initialized")
                    st.rerun()
            
            # Manual position slider
            new_pos = st.slider("Manual Position (mm)", 
                               min_value=stage_min, 
                               max_value=stage_max, 
                               value=st.session_state.linear_stage_pos,
                               key="stage_manual")
            if st.button("Move to Position", key="stage_move"):
                if st.session_state.robot_controller is not None:
                    try:
                        st.session_state.robot_controller.move_linear_stage(new_pos)
                        st.session_state.linear_stage_pos = new_pos
                        st.success(f"✓ Moved to {new_pos} mm")
                    except Exception as e:
                        st.error(f"Failed to move stage: {e}")
                else:
                    st.warning("⚠️ Robot controller not initialized")
                st.rerun()
        
        with col2:
            st.markdown("**xArm Robot:**")
            
            # Display current position
            current_pos = st.session_state.robot_position
            
            # Position sequence: home -> intermediate -> pmt_top
            position_info = {
                'home': {'name': 'Initial (Home)', 'icon': '🏠', 'next': 'intermediate', 'prev': None},
                'intermediate': {'name': 'Intermediate', 'icon': '🔄', 'next': 'pmt_top', 'prev': 'home'},
                'pmt_top': {'name': 'PMT Top', 'icon': '🔝', 'next': None, 'prev': 'intermediate'}
            }
            
            # Joint angles from xarm_pmt_controller.py
            ROBOT_JOINT_ANGLES = {
                'home': [0, 0, 0, 0, 0, -135],              # HOME_TRUE (vertical)
                'intermediate': [0, -116.5, 5, 0, 0, -135], # HOME (safe intermediate)
                'pmt_top': [-0.0, -116.812436, -25.177883, 0.0, 51.990269, -135.0]  # PMT_TOP
            }
            
            # Show current position prominently
            if current_pos in position_info:
                st.markdown(f"### {position_info[current_pos]['icon']} {position_info[current_pos]['name']}")
            else:
                st.markdown(f"### ❓ Unknown Position")
            
            # Show joint angles for current position
            if current_pos in ROBOT_JOINT_ANGLES:
                angles = ROBOT_JOINT_ANGLES[current_pos]
                st.caption(f"Joint angles: [{angles[0]:.1f}, {angles[1]:.1f}, {angles[2]:.1f}, {angles[3]:.1f}, {angles[4]:.1f}, {angles[5]:.1f}]")
            
            st.markdown("---")
            st.markdown("**Sequential Position Control:**")
            st.caption("⚠️ Must move through positions in order for safety")
            
            # Position buttons with sequential logic
            col_a, col_b = st.columns(2)
            
            with col_a:
                # Home button - always accessible
                if st.button(
                    "🏠 Initial",
                    key="robot_home",
                    use_container_width=True,
                    disabled=(current_pos == 'home')
                ):
                    if st.session_state.robot_controller is not None:
                        try:
                            st.session_state.robot_controller.move_to_initial()
                            st.session_state.robot_position = 'home'
                            st.success("✓ Moved to Initial position")
                        except Exception as e:
                            st.error(f"Failed to move to Initial: {e}")
                    else:
                        st.warning("⚠️ Robot controller not initialized")
                    st.rerun()
                
                if current_pos == 'home':
                    st.caption("✓ At Home")
                else:
                    st.caption("⚠️ Return here first")
            
            with col_b:
                # Intermediate button - only from home or pmt_top
                can_intermediate = current_pos in ['home', 'pmt_top']
                
                if st.button(
                    "🔄 Intermediate",
                    key="robot_inter",
                    use_container_width=True,
                    disabled=(current_pos == 'intermediate' or not can_intermediate)
                ):
                    if st.session_state.robot_controller is not None:
                        try:
                            st.session_state.robot_controller.move_to_intermediate()
                            st.session_state.robot_position = 'intermediate'
                            st.success("✓ Moved to Intermediate position")
                        except Exception as e:
                            st.error(f"Failed to move to Intermediate: {e}")
                    else:
                        st.warning("⚠️ Robot controller not initialized")
                    st.rerun()
                
                if current_pos == 'intermediate':
                    st.caption("✓ At Intermediate")
                elif can_intermediate:
                    st.caption("→ Next position")
                else:
                    st.caption("⊗ Not accessible")
            
            # PMT Top button - only from intermediate
            can_pmt_top = (current_pos == 'intermediate')
            
            if st.button(
                "🔝 PMT Top",
                key="robot_top",
                use_container_width=True,
                disabled=(current_pos == 'pmt_top' or not can_pmt_top)
            ):
                if st.session_state.robot_controller is not None:
                    try:
                        st.session_state.robot_controller.move_to_pmt_top()
                        st.session_state.robot_position = 'pmt_top'
                        st.success("✓ Moved to PMT Top position")
                    except Exception as e:
                        st.error(f"Failed to move to PMT Top: {e}")
                else:
                    st.warning("⚠️ Robot controller not initialized")
                st.rerun()
            
            if current_pos == 'pmt_top':
                st.caption("✓ At PMT Top")
            elif can_pmt_top:
                st.caption("→ Final position")
            else:
                st.caption("⊗ Must be at Intermediate first")
            
            st.markdown("---")
            
            # Position sequence diagram
            st.markdown("**Position Sequence:**")
            st.code("Home → Intermediate → PMT Top → Intermediate → Home", language="text")
            
            st.info("ℹ️ Robot uses safe joint angles (not Cartesian coordinates)")
        
        st.markdown("---")
        
        # Robot status
        robot_status_text = {
            'home': f"{status_dot('green')} At Initial Position",
            'intermediate': f"{status_dot('yellow')} At Intermediate",
            'pmt_top': f"{status_dot('yellow')} At PMT Top",
            'pmt1': f"{status_dot('yellow')} At PMT1",
            'pmt2': f"{status_dot('yellow')} At PMT2"
        }
        st.markdown(f"**Robot Status:** {robot_status_text.get(st.session_state.robot_position, 'Unknown')}", 
                   unsafe_allow_html=True)
        
        st.info("ℹ️ Manual position control removed for safety with PMT present")
    
    # TAB 6: Manual Acquisition
    with tabs[5]:
        st.subheader("Manual Data Acquisition")
        
        if not st.session_state.get('digitizer_connected', False):
            st.error("❌ Digitizer not connected - cannot acquire data")
            st.info("Check digitizer status in System Status tab")
        else:
            # Check if digitizer is ready
            status = st.session_state.digitizer_status
            digitizer_ready = status['connected'] and status['kernel_module']
            
            if not digitizer_ready:
                st.warning("⚠ Digitizer not ready")
                if not status['kernel_module']:
                    st.error("Kernel module not loaded. Run: `source sourceatstart.sh`")
                if not status['connected']:
                    st.error("USB device not detected. Check connection.")
                
                # # Add reset button for "Can't open digitizer" errors
                # st.markdown("---")
                # st.markdown("**Troubleshooting:**")
                # st.info("If you see 'Can't open the digitizer' errors, the USB device may be locked from a previous run.")
                
                # if st.button("🔄 Reset CAEN Driver", key="reset_caen_driver"):
                #     with st.spinner("Resetting CAEN USB driver..."):
                #         try:
                #             if st.session_state.digitizer.reset_driver():
                #                 st.success("✓ Driver reset successfully! Try acquisition again.")
                #                 st.rerun()
                #             else:
                #                 st.error("❌ Driver reset failed. Check terminal for errors.")
                #         except Exception as e:
                #             st.error(f"❌ Reset failed: {e}")
                
                # st.caption("Note: Reset requires sudo privileges (passwordless sudo recommended)")
            
            # Configuration
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Acquisition Settings:**")
                
                acq_duration = st.number_input(
                    "Duration (seconds)",
                    min_value=1,
                    max_value=3600,
                    value=300,
                    step=1,
                    key="manual_acq_duration"
                )
                
                # Channel selection
                available_channels = {
                    0: "Ch0 (Trigger)",
                    1: "Ch1 (SiPM)",
                    2: "Ch2 (PMT1)",
                    3: "Ch3 (PMT2)",
                    4: "Ch4 (PMT3/Monitor)",
                    5: "Ch5",
                    6: "Ch6",
                    7: "Ch7"
                }
                
                channels = st.multiselect(
                    "Channels to Record",
                    options=list(available_channels.keys()),
                    default=[0, 1, 2],
                    format_func=lambda x: available_channels[x],
                    key="manual_acq_channels"
                )
                
                record_length = st.number_input(
                    "Record Length (samples)",
                    min_value=128,
                    max_value=8192,
                    value=256,
                    step=128,
                    key="manual_record_length"
                )
            
            with col2:
                st.markdown("**Trigger Settings:**")
                
                trigger_channel = st.selectbox(
                    "Trigger Channel",
                    options=list(available_channels.keys()),
                    index=0,  # Default to Ch4
                    format_func=lambda x: available_channels[x],
                    key="manual_trigger_ch"
                )
                
                trigger_threshold = st.number_input(
                    "Trigger Threshold (ADC counts)",
                    min_value=1,
                    max_value=4095,
                    value=100,
                    step=1,
                    help="Lower = more sensitive",
                    key="manual_trigger_thresh"
                )
                
                trigger_mode = st.selectbox(
                    "Trigger Mode",
                    options=["ACQUISITION_ONLY", "ACQUISITION_AND_TRGOUT", "DISABLED"],
                    index=0,
                    key="manual_trigger_mode"
                )
            
            st.markdown("---")
            st.markdown("**Output Settings:**")
            
            col_out1, col_out2 = st.columns(2)
            
            with col_out1:
                output_dir = st.text_input(
                    "Output Directory",
                    value="/home/hyperkaus/WaveDumpSaves/manual_acquisition",
                    key="manual_output_dir",
                    help="Where to save organized files"
                )
                
                file_prefix = st.text_input(
                    "File Prefix",
                    value="manual",
                    key="manual_file_prefix",
                    help="Prefix for saved files"
                )
            
            with col_out2:
                st.markdown("**Display Options:**")
                show_wavedump_output = st.checkbox(
                    "Show WaveDump Terminal Output",
                    value=False,
                    key="show_wavedump_output",
                    help="Display real-time WaveDump output below"
                )
            
            # Manual acquisition state is in shared_state.manual_acq_data (thread-safe)
            # No need to initialize - it's already defined in shared_state.py
            
            # Acquisition controls
            col_a, col_b, col_c = st.columns([2, 1, 1])
            
            with col_a:
                if st.button(
                    "▶ Start Acquisition",
                    type="primary",
                    use_container_width=True,
                    disabled=not digitizer_ready or shared_state.manual_acq_data['active'] or st.session_state.run_active,
                    key="start_manual_acq"
                ):
                    if digitizer_ready and channels:
                        # Reset state in shared_state (thread-safe)
                        shared_state.manual_acq_data['active'] = True
                        shared_state.manual_acq_data['progress'] = 0
                        shared_state.manual_acq_data['output'] = []
                        shared_state.manual_acq_data['start_time'] = datetime.now()
                        shared_state.manual_acq_data['result'] = None
                        
                        # Configure digitizer
                        st.session_state.digitizer.configure(
                            run_duration=acq_duration,
                            channels=channels,
                            trigger_channel=trigger_channel,
                            trigger_threshold=trigger_threshold,
                            channel_trigger_mode=trigger_mode,
                            record_length=record_length
                        )
                        
                        # Get references to pass to thread (can't access session_state from thread)
                        digitizer = st.session_state.digitizer
                        
                        # Start acquisition in background thread
                        def manual_acq_worker(digitizer_obj, channels_list, duration, out_dir, prefix_str):
                            import warnings
                            warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')
                            
                            try:
                                # Acquire data with progress tracking
                                import subprocess
                                import time
                                import select
                                import sys
                                
                                # Start WaveDump with stdbuf to force unbuffered output for live streaming
                                # stdbuf -o0 disables stdout buffering, making output appear immediately
                                process = subprocess.Popen(
                                    ['stdbuf', '-o0', digitizer_obj.wavedump_path, str(digitizer_obj.config_file)],
                                    cwd=str(digitizer_obj.working_dir),
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    bufsize=0  # Unbuffered on Python side too
                                )
                                
                                start_time = time.time()
                                output_buffer = ""
                                
                                # Poll for output with non-blocking reads
                                while True:
                                    # Check if process has finished
                                    retcode = process.poll()
                                    
                                    # Use select to check if there's data available (non-blocking)
                                    if sys.platform != 'win32':  # Linux/Mac
                                        ready, _, _ = select.select([process.stdout], [], [], 0.1)
                                        if ready:
                                            # Read available data
                                            try:
                                                chunk = process.stdout.read(1024).decode('utf-8', errors='ignore')
                                                if chunk:
                                                    output_buffer += chunk
                                                    # Split by newlines and process complete lines
                                                    while '\n' in output_buffer:
                                                        line, output_buffer = output_buffer.split('\n', 1)
                                                        if line.strip():
                                                            shared_state.manual_acq_data['output'].append(line.strip())
                                                            # Keep only last 100 lines
                                                            if len(shared_state.manual_acq_data['output']) > 100:
                                                                shared_state.manual_acq_data['output'] = shared_state.manual_acq_data['output'][-100:]
                                            except:
                                                pass
                                    else:  # Windows fallback
                                        # On Windows, try non-blocking read
                                        try:
                                            line = process.stdout.readline()
                                            if line:
                                                shared_state.manual_acq_data['output'].append(line.strip())
                                                if len(shared_state.manual_acq_data['output']) > 100:
                                                    shared_state.manual_acq_data['output'] = shared_state.manual_acq_data['output'][-100:]
                                        except:
                                            pass
                                    
                                    # Update progress
                                    elapsed = time.time() - start_time
                                    progress = min(int((elapsed / duration) * 100), 99)
                                    shared_state.manual_acq_data['progress'] = progress
                                    
                                    # Exit loop if process finished
                                    if retcode is not None:
                                        # Read any remaining output
                                        try:
                                            remaining = process.stdout.read().decode('utf-8', errors='ignore')
                                            if remaining:
                                                for line in remaining.split('\n'):
                                                    if line.strip():
                                                        shared_state.manual_acq_data['output'].append(line.strip())
                                        except:
                                            pass
                                        break
                                    
                                    # Small sleep to prevent CPU spinning
                                    time.sleep(0.1)
                                
                                # Process finished
                                retcode = process.returncode if process.returncode is not None else process.wait()
                                
                                # Final progress
                                shared_state.manual_acq_data['progress'] = 100
                                
                                if retcode == 0:
                                    # Success - organize files
                                    time.sleep(1)  # Let files settle
                                    
                                    waveform_files = digitizer_obj.get_all_wavefiles(channels_list)
                                    prefix = prefix_str.strip() if prefix_str.strip() else "data"
                                    
                                    save_path = digitizer_obj.organize_files(
                                        save_dir=out_dir,
                                        prefix=prefix,
                                        channels=channels_list,
                                        include_timestamp=True
                                    )
                                    
                                    # Save result in shared_state
                                    shared_state.manual_acq_data['result'] = {
                                        'timestamp': shared_state.manual_acq_data['start_time'].strftime("%Y-%m-%d %H:%M:%S"),
                                        'duration': duration,
                                        'channels': channels_list,
                                        'num_files': len(waveform_files),
                                        'save_path': save_path,
                                        'prefix': prefix,
                                        'status': 'success'
                                    }
                                    shared_state.manual_acq_data['output'].append(f"✓ Files saved to: {save_path}")
                                else:
                                    shared_state.manual_acq_data['result'] = {
                                        'status': 'failed',
                                        'error': f'WaveDump exited with code {retcode}'
                                    }
                                    shared_state.manual_acq_data['output'].append(f"❌ Acquisition failed (exit code {retcode})")
                                
                            except Exception as e:
                                shared_state.manual_acq_data['result'] = {
                                    'status': 'error',
                                    'error': str(e)
                                }
                                shared_state.manual_acq_data['output'].append(f"❌ Error: {e}")
                            finally:
                                shared_state.manual_acq_data['active'] = False
                        
                        # Start thread with parameters
                        import threading
                        thread = threading.Thread(
                            target=manual_acq_worker,
                            args=(digitizer, channels, acq_duration, output_dir, file_prefix),
                            daemon=True
                        )
                        thread.start()
                        st.rerun()
                    else:
                        if not channels:
                            st.error("⚠ Please select at least one channel")
            
            # Progress display (when acquisition is active)
            if shared_state.manual_acq_data['active']:
                st.markdown("---")
                st.markdown("### Acquisition in Progress")
                
                # Progress bar
                progress = shared_state.manual_acq_data['progress']
                st.progress(max(0.0, min(1.0, progress / 100.0)))
                
                # Countdown/elapsed time
                if shared_state.manual_acq_data['start_time']:
                    elapsed = (datetime.now() - shared_state.manual_acq_data['start_time']).total_seconds()
                    remaining = max(0, acq_duration - elapsed)
                    
                    col_time1, col_time2, col_time3 = st.columns(3)
                    with col_time1:
                        st.metric("Progress", f"{progress}%")
                    with col_time2:
                        st.metric("Elapsed", f"{int(elapsed)}s")
                    with col_time3:
                        st.metric("Remaining", f"{int(remaining)}s")
                
                # Manual refresh button instead of auto-refresh
                if st.button("🔄 Refresh Progress", key="manual_acq_refresh_btn"):
                    st.rerun()
            
            # Live terminal output (if enabled)
            # Live terminal output (if enabled) - Always show section when checkbox is enabled
            if show_wavedump_output:
                st.markdown("---")
                st.markdown("### WaveDump Output")
                
                num_lines = len(shared_state.manual_acq_data['output'])
                st.caption(f"📝 Captured {num_lines} lines")
                
                if num_lines > 0:
                    output_text = "\n".join(shared_state.manual_acq_data['output'][-50:])  # Last 50 lines
                    st.code(output_text, language="text")
                else:
                    st.info("💡 No output captured yet. WaveDump output will appear here during acquisition.")
                    st.caption("Note: If output doesn't appear, WaveDump may be buffering its output. Check terminal for live output.")
            
            # Show last acquisition results
            if shared_state.manual_acq_data['result']:
                if not shared_state.manual_acq_data['active']:  # Only show when not running
                    st.markdown("---")
                    st.markdown("### Last Acquisition")
                    
                    acq = shared_state.manual_acq_data['result']
                    if acq.get('status') == 'success':
                        st.success(f"✓ Acquisition complete! Files saved to:")
                        st.code(str(acq['save_path']))
                        
                        # Show organized files
                        for ch in acq['channels']:
                            filename = f"{acq['prefix']}_wave{ch}.txt"
                            st.text(f"  Ch{ch}: {filename}")
                    elif acq.get('status') == 'failed':
                        st.error(f"❌ Acquisition failed: {acq.get('error', 'Unknown error')}")
                    elif acq.get('status') == 'error':
                        st.error(f"❌ Error: {acq.get('error', 'Unknown error')}")
            
            with col_b:
                if st.button(
                    "🗑️ Clear Files",
                    use_container_width=True,
                    help="Remove temporary wave*.txt files",
                    key="clear_wave_files"
                ):
                    try:
                        st.session_state.digitizer.cleanup_temp_files()
                        st.success("✓ Temporary files cleared")
                    except Exception as e:
                        st.error(f"Cleanup error: {e}")
            
            with col_c:
                if st.button(
                    "🔄 Refresh",
                    use_container_width=True,
                    key="refresh_daq_tab"
                ):
                    st.session_state.digitizer_status = st.session_state.digitizer.get_status()
                    st.rerun()
            
            # Show last acquisition details
            if st.session_state.last_acquisition:
                st.markdown("---")
                st.markdown("### Last Acquisition Results")
                
                last_acq = st.session_state.last_acquisition
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Time", last_acq['timestamp'].split()[1])
                with col2:
                    st.metric("Duration", f"{last_acq['duration']}s")
                with col3:
                    st.metric("Channels", len(last_acq['channels']))
                with col4:
                    st.metric("Files", last_acq['num_files'])
                
                # Show file details in expander
                with st.expander("📁 View File Details"):
                    st.text(f"Saved to: {last_acq['save_path']}")
                    st.text(f"Prefix: {last_acq['prefix']}")
                    st.text(f"Channels: {', '.join(map(str, last_acq['channels']))}")
                    st.text(f"\nFiles:")
                    for ch in last_acq['channels']:
                        filename = f"{last_acq['prefix']}_wave{ch}.txt"
                        st.text(f"  • {filename}")
                
                # Note about analysis
                st.info("💡 Use wavepro or other offline tools to analyze waveforms")

else:
    # ========================================================================
    # RUN SEQUENCE MODE (Default - No password)
    # ========================================================================
    
    st.title("Run Sequence Mode")
    st.caption("Automated measurement sequences with coordinated device control")
    
    # Auto-refresh when run is active OR scheduled to update progress/countdown display
    if st.session_state.run_active or st.session_state.run_scheduled:
        count = st_autorefresh(interval=1000, key="run_sequence_autorefresh")  # 1 second for countdown
    
    # Sync progress data from thread-safe dictionary to session state
    # (Background thread updates shared_state.progress_data, we copy to session_state on each rerun)
    
    # Check if scheduled run transitioned to active
    if shared_state.progress_data.get('scheduled', False):
        st.session_state.run_scheduled = True
        st.session_state.run_active = False
    elif shared_state.progress_data.get('active', False):
        st.session_state.run_scheduled = False
        st.session_state.run_active = True
    
    # Update progress from active run
    if shared_state.progress_data['active'] or shared_state.progress_data['progress_pct'] > 0:
        st.session_state.run_progress = shared_state.progress_data['progress_pct']
        st.session_state.run_status_text = shared_state.progress_data['status_text']
        st.session_state.run_position = shared_state.progress_data['position']
    
    # Check if thread completed or was cancelled - trigger rerun for logging
    if shared_state.progress_data['result'] is not None:
        # Sync result to session state
        has_run_result = hasattr(st.session_state, 'run_result')
        
        if not has_run_result or st.session_state.run_result != shared_state.progress_data['result']:
            st.session_state.run_result = shared_state.progress_data['result']
            st.session_state.run_active = False
            st.session_state.run_scheduled = False
            shared_state.progress_data['active'] = False
            shared_state.progress_data['scheduled'] = False
            # Trigger rerun so the thread cleanup check (below) can log the run
            st.rerun()
        else:
            # Result already synced, don't rerun again
            st.session_state.run_result = shared_state.progress_data['result']
            st.session_state.run_active = False
            st.session_state.run_scheduled = False
    
    # PMT Serial Number Input - Two PMTs
    st.subheader("PMT Configuration")
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        pmt1_serial = st.text_input("PMT1 Serial Number:", 
                                   value=st.session_state.pmt_serial_number["pmt1"],
                                   placeholder="e.g., EL5150-B",
                                   key="pmt1_serial_input",
                                   help="Serial number for PMT at position 1")
        st.session_state.pmt_serial_number["pmt1"] = pmt1_serial
    
    with col2:
        pmt2_serial = st.text_input("PMT2 Serial Number:", 
                                   value=st.session_state.pmt_serial_number["pmt2"],
                                   placeholder="e.g., EL7370-A",
                                   key="pmt2_serial_input",
                                   help="Serial number for PMT at position 2")
        st.session_state.pmt_serial_number["pmt2"] = pmt2_serial
    
    with col3:
        st.write(" ")  # Spacer
        if pmt1_serial and pmt2_serial:
            st.info(f"📁 PMT1: `/home/hyperkaus/WaveDumpSaves/scan_<timestamp>/{pmt1_serial}/` | PMT2: `/home/hyperkaus/WaveDumpSaves/scan_<timestamp>/{pmt2_serial}/`")
        elif pmt1_serial or pmt2_serial:
            if pmt1_serial:
                st.info(f"📁 PMT1: `/home/hyperkaus/WaveDumpSaves/scan_<timestamp>/{pmt1_serial}/` | ⚠️ PMT2: Not set")
            else:
                st.info(f"⚠️ PMT1: Not set | 📁 PMT2: `/home/hyperkaus/WaveDumpSaves/scan_<timestamp>/{pmt2_serial}/`")
        else:
            st.warning("⚠️ Please enter PMT serial numbers before starting measurements")

    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        pmt1_voltage = st.number_input("PMT1 Voltage (V):",
                                       min_value=0,
                                       max_value=2000,
                                       value=st.session_state.pmt_voltages[0],
                                       key="pmt1_voltage_input",
                                       help="High Voltage value for PMT at position 1")
        st.session_state.pmt_voltages[0] = pmt1_voltage
    
    with col2:
        pmt2_voltage = st.number_input("PMT2 Voltage (V):",
                                       min_value=0,
                                       max_value=2000,
                                       value=st.session_state.pmt_voltages[1],
                                       key="pmt2_voltage_input",
                                       help="High Voltage value for PMT at position 2")
        st.session_state.pmt_voltages[1] = pmt2_voltage
    
    with col3:
        st.write(" ")  # Spacer
        if pmt1_voltage and pmt2_voltage:
            st.info(f"EBB (at 1E+07) for PMT1: {pmt1_voltage}V | PMT2: {pmt2_voltage}V")

        else:
            st.warning("⚠️ Please enter PMT high voltage value before starting measurements")
    
    st.markdown("---")
    
    # Device ON/OFF controls on main page - synced with Setup & Monitor
    # Using on_click callbacks so state changes happen BEFORE the render cycle,
    # avoiding race conditions with st_autorefresh triggering concurrent reruns.
    st.subheader("System Control")
    
    def _toggle_pmt_hv():
        """Callback: optimistic state update + background API command."""
        if not st.session_state.get('api_client'):
            return
        new_state = not st.session_state.device_enabled['pmt_hv']
        logger.info(f"[PMT_HV] Toggle: setting to {new_state} (Run Sequence)")
        # Optimistic state update (instant, before render)
        updated = dict(st.session_state.device_enabled)
        updated['pmt_hv'] = new_state
        st.session_state.device_enabled = updated
        st.session_state.pmt_power = [new_state, new_state, new_state]
        # Fire API command in background thread
        api = st.session_state.api_client
        voltages = list(st.session_state.pmt_voltages)
        def _cmd():
            try:
                if new_state:
                    for ch in range(1, 4):
                        api.caen_set_voltage(ch, voltages[ch-1])
                        api.caen_set_power(ch, True)
                else:
                    for ch in range(1, 4):
                        api.caen_set_power(ch, False)
                logger.info(f"[PMT_HV] Background command completed")
            except Exception as e:
                logger.error(f"[PMT_HV] Background command failed: {e}")
        threading.Thread(target=_cmd, daemon=True).start()
    
    def _toggle_sipm():
        """Callback: SiPM is local serial (fast), runs inline."""
        if not st.session_state.get('sipm_connected', False):
            return
        try:
            new_state = not st.session_state.device_enabled['sipm']
            logger.info(f"[SiPM] Toggle: setting to {new_state} (Run Sequence)")
            if new_state:
                st.session_state.sipm_supply.ON()
            else:
                st.session_state.sipm_supply.OFF()
            # Update state (serial is fast, so this always completes)
            updated = dict(st.session_state.device_enabled)
            updated['sipm'] = new_state
            st.session_state.device_enabled = updated
            st.session_state.sipm_output_on = new_state
            logger.info(f"[SiPM] Toggle complete")
        except Exception as e:
            logger.error(f"[SiPM] Toggle failed: {e}")
            st.session_state._toggle_error = f"SiPM control failed: {e}"
    
    def _toggle_siggen():
        """Callback: optimistic state update + background API command."""
        if not st.session_state.get('api_client'):
            return
        new_state = not st.session_state.device_enabled['siggen']
        logger.info(f"[SIGGEN] Toggle: setting to {new_state} (Run Sequence)")
        # Optimistic state update (instant, before render)
        updated = dict(st.session_state.device_enabled)
        updated['siggen'] = new_state
        st.session_state.device_enabled = updated
        # Fire API command in background thread
        api = st.session_state.api_client
        def _cmd():
            try:
                api.siggen_enable_output(1, new_state)
                logger.info(f"[SIGGEN] Background command completed")
            except Exception as e:
                logger.error(f"[SIGGEN] Background command failed: {e}")
        threading.Thread(target=_cmd, daemon=True).start()
    
    def _toggle_laser():
        """Callback: optimistic state update + background API command."""
        if not st.session_state.get('api_client'):
            return
        new_state = not st.session_state.device_enabled['laser']
        logger.info(f"[LASER] Toggle: setting to {new_state} (Run Sequence)")
        # Optimistic state update (instant, before render)
        updated = dict(st.session_state.device_enabled)
        updated['laser'] = new_state
        st.session_state.device_enabled = updated
        st.session_state.laser_tec_on = new_state
        st.session_state.laser_ld_on = new_state
        # Fire API command in background thread
        api = st.session_state.api_client
        def _cmd():
            try:
                if new_state:
                    api.laser_set_power(tec_enabled=True)
                    time.sleep(0.5)
                    api.laser_set_power(ld_enabled=True)
                else:
                    api.laser_set_power(ld_enabled=False, tec_enabled=False)
                logger.info(f"[LASER] Background command completed")
            except Exception as e:
                logger.error(f"[LASER] Background command failed: {e}")
        threading.Thread(target=_cmd, daemon=True).start()
    
    # Show any toggle errors from previous callback
    if st.session_state.get('_toggle_error'):
        st.error(st.session_state._toggle_error)
        del st.session_state._toggle_error
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.button(
            f"{'✓' if st.session_state.device_enabled['pmt_hv'] else '○'} PMT HV",
            use_container_width=True,
            key='toggle_pmt',
            on_click=_toggle_pmt_hv
        )
    
    with col2:
        st.button(
            f"{'✓' if st.session_state.device_enabled['sipm'] else '○'} SiPM",
            use_container_width=True,
            key='toggle_sipm',
            on_click=_toggle_sipm
        )
    
    with col3:
        st.button(
            f"{'✓' if st.session_state.device_enabled['siggen'] else '○'} Sig Gen",
            use_container_width=True,
            key='toggle_siggen',
            on_click=_toggle_siggen
        )
    
    with col4:
        st.button(
            f"{'✓' if st.session_state.device_enabled['laser'] else '○'} Laser",
            use_container_width=True,
            key='toggle_laser',
            on_click=_toggle_laser
        )
    
    st.markdown("---")
    
    # Real-time monitoring section with auto-refresh
    st.subheader("📊 Real-time Monitoring")
    
    def _padded_chart(times, values, y_label, height=150, min_pad=1.0):
        """Create an Altair line chart with y-axis padded around the data range."""
        df = pd.DataFrame({'Time': times, y_label: values})
        if len(values) > 0:
            y_min = min(values)
            y_max = max(values)
            y_range = y_max - y_min
            pad = max(y_range * 0.15, min_pad)
            domain = [y_min - pad, y_max + pad]
        else:
            domain = [0, 1]
        chart = alt.Chart(df).mark_line().encode(
            x=alt.X('Time:T', axis=alt.Axis(format='%H:%M:%S', title=None)),
            y=alt.Y(f'{y_label}:Q', scale=alt.Scale(domain=domain))
        ).properties(height=height)
        st.altair_chart(chart, use_container_width=True)
    
    # Auto-refresh only in Run Sequence mode (not in Setup & Monitor)
    if st.session_state.mode == 'Run Sequence':
        count = st_autorefresh(interval=2000, key="run_monitor_refresh")
    
    # Collect data when devices are enabled OR ramping down
    # Continue monitoring even after turn-off to see ramp-down
    collect_data = (
        st.session_state.device_enabled.get('pmt_hv', False) or  # HV is on
        len(st.session_state.caen_current_history['timestamps']) > 0  # Or we have history (ramping down)
    )
    
    if collect_data:
        from datetime import datetime
        now = datetime.now()
        max_points = 100
        
        # Query actual device currents and voltages before collecting
        if st.session_state.get('api_client'):
            try:
                for ch_num in range(1, 4):
                    channel_status = st.session_state.api_client.caen_get_status(ch_num)
                    st.session_state.caen_channels[ch_num]['current_mon'] = channel_status['current_mon']
                    st.session_state.caen_channels[ch_num]['voltage_mon'] = channel_status['voltage_mon']
                    st.session_state.caen_channels[ch_num]['power_on'] = channel_status['power_on']
            except:
                pass  # Use existing session state values if query fails
        
        # Collect CAEN current and voltage data
        for ch_num in range(1, 4):
            i_mon = st.session_state.caen_channels[ch_num]['current_mon']
            v_mon = st.session_state.caen_channels[ch_num]['voltage_mon']
            
            st.session_state.caen_current_history[f'ch{ch_num}'].append(i_mon)
            st.session_state.caen_voltage_history[f'ch{ch_num}'].append(v_mon)
        
        st.session_state.caen_current_history['timestamps'].append(now)
        st.session_state.caen_voltage_history['timestamps'].append(now)
        
        # Trim to max points
        if len(st.session_state.caen_current_history['timestamps']) > max_points:
            for key in st.session_state.caen_current_history:
                st.session_state.caen_current_history[key] = st.session_state.caen_current_history[key][-max_points:]
            for key in st.session_state.caen_voltage_history:
                st.session_state.caen_voltage_history[key] = st.session_state.caen_voltage_history[key][-max_points:]
        
        # Stop collecting if HV is off and voltages/currents are near zero
        if not st.session_state.device_enabled.get('pmt_hv', False):
            all_near_zero = True
            for ch_num in range(1, 4):
                v_mon = st.session_state.caen_channels[ch_num]['voltage_mon']
                i_mon = st.session_state.caen_channels[ch_num]['current_mon']
                if v_mon > 10 or i_mon > 1.0:  # Still ramping down
                    all_near_zero = False
                    break
            
            # Clear history if everything is at zero
            if all_near_zero and len(st.session_state.caen_current_history['timestamps']) > 10:
                st.session_state.caen_current_history = {
                    'ch0': [], 'ch1': [], 'ch2': [], 'ch3': [],
                    'timestamps': []
                }
                st.session_state.caen_voltage_history = {
                    'ch0': [], 'ch1': [], 'ch2': [], 'ch3': [],
                    'timestamps': []
                }
    
    if st.session_state.device_enabled.get('sipm', False) and st.session_state.get('sipm_connected', False):
        from datetime import datetime
        now = datetime.now()
        max_points = 100
        
        # Collect SiPM current data
        try:
            ch1_i = st.session_state.sipm_supply.get_current(1)
            ch2_i = st.session_state.sipm_supply.get_current(2)
            
            st.session_state.sipm_current_history['ch1'].append(ch1_i)
            st.session_state.sipm_current_history['ch2'].append(ch2_i)
            st.session_state.sipm_current_history['timestamps'].append(now)
            
            # Trim to max points
            if len(st.session_state.sipm_current_history['timestamps']) > max_points:
                for key in st.session_state.sipm_current_history:
                    st.session_state.sipm_current_history[key] = st.session_state.sipm_current_history[key][-max_points:]
        except:
            pass
    
    # Display CAEN HV current monitoring
    st.markdown("**CAEN HV Current:**")
    if len(st.session_state.caen_current_history['timestamps']) > 0:
        
        col1, col2, col3 = st.columns(3)
        
        for idx, col in enumerate([col1, col2, col3], start=1):
            with col:
                latest_i = st.session_state.caen_channels[idx]['current_mon']
                st.markdown(f"*Ch{idx}* — **{latest_i:.2f} µA**")
                _padded_chart(
                    st.session_state.caen_current_history['timestamps'],
                    st.session_state.caen_current_history[f'ch{idx}'],
                    'Current (µA)', min_pad=20
                )
    else:
        st.info("Enable PMT HV to start monitoring")
    
    # Display CAEN HV voltage monitoring
    st.markdown("**CAEN HV Voltage:**")
    if len(st.session_state.caen_voltage_history['timestamps']) > 0:
        
        col1, col2, col3 = st.columns(3)
        
        for idx, col in enumerate([col1, col2, col3], start=1):
            with col:
                latest_v = st.session_state.caen_channels[idx]['voltage_mon']
                st.markdown(f"*Ch{idx}* — **{latest_v:.1f} V**")
                _padded_chart(
                    st.session_state.caen_voltage_history['timestamps'],
                    st.session_state.caen_voltage_history[f'ch{idx}'],
                    'Voltage (V)', min_pad=20
                )
    else:
        st.info("Enable PMT HV to start monitoring")
    
    # Display SiPM current monitoring
    st.markdown("**SiPM Current:**")
    if len(st.session_state.sipm_current_history['timestamps']) > 0:
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            latest_ch1 = st.session_state.sipm_current_history['ch1'][-1] * 1000 if st.session_state.sipm_current_history['ch1'] else 0
            st.markdown(f"*Ch1* — **{latest_ch1:.2f} mA**")
            _padded_chart(
                st.session_state.sipm_current_history['timestamps'],
                [x * 1000 for x in st.session_state.sipm_current_history['ch1']],
                'Current (mA)', min_pad=5
            )
        
        with col2:
            latest_ch2 = st.session_state.sipm_current_history['ch2'][-1] * 1000 if st.session_state.sipm_current_history['ch2'] else 0
            st.markdown(f"*Ch2* — **{latest_ch2:.2f} mA**")
            _padded_chart(
                st.session_state.sipm_current_history['timestamps'],
                [x * 1000 for x in st.session_state.sipm_current_history['ch2']],
                'Current (mA)', min_pad=2
            )
        
        # col3 intentionally left empty for alignment
    else:
        st.info("Enable SiPM to start monitoring")
    
    # Display Laser monitoring
    st.markdown("**Laser:**")
    if st.session_state.get('api_client') and (st.session_state.laser_tec_on or st.session_state.laser_ld_on):
        try:
            from datetime import datetime
            status = st.session_state.api_client.laser_get_status()
            
            # Collect laser history data
            now = datetime.now()
            max_points = 100
            st.session_state.laser_history['ld_temp'].append(status.get('ld_temp_actual', 0))
            st.session_state.laser_history['board_temp'].append(status.get('board_temp', 0))
            st.session_state.laser_history['timestamps'].append(now)
            
            # Trim to max points
            if len(st.session_state.laser_history['timestamps']) > max_points:
                for key in st.session_state.laser_history:
                    st.session_state.laser_history[key] = st.session_state.laser_history[key][-max_points:]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                ld_temp = status.get('ld_temp_actual', 0)
                st.markdown(f"*LD Temp* — **{ld_temp:.2f} °C**")
                if len(st.session_state.laser_history['timestamps']) > 1:
                    _padded_chart(
                        st.session_state.laser_history['timestamps'],
                        st.session_state.laser_history['ld_temp'],
                        'LD Temp (°C)', min_pad=1
                    )
            
            with col2:
                board_temp = status.get('board_temp', 0)
                if board_temp > 42:
                    temp_status = "⚠️"
                else:
                    temp_status = ""
                st.markdown(f"*Board Temp* — **{board_temp:.2f} °C** {temp_status}")
                if len(st.session_state.laser_history['timestamps']) > 1:
                    _padded_chart(
                        st.session_state.laser_history['timestamps'],
                        st.session_state.laser_history['board_temp'],
                        'Board Temp (°C)', min_pad=1
                    )
            
            # col3 intentionally left empty for alignment
        except:
            st.info("Could not read laser status")
    else:
        # Clear history when laser is off
        if len(st.session_state.laser_history['timestamps']) > 0 and not st.session_state.laser_tec_on:
            st.session_state.laser_history = {
                'ld_temp': [], 'board_temp': [], 'pulse_current': [],
                'pd_current': [], 'timestamps': []
            }
        st.info("Enable Laser to start monitoring")
    
    st.markdown("---")
    
    # Run Selection
    st.subheader("Select Measurement Sequence")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Simple sequence selection (no custom for now)
        sequence_options = [
            "Dark Current Check (10 min)",
            "Single PMT Scan (3.5 hours)",
            "Full PMT Scan (7 hours)"
        ]
        
        sequence_type = st.selectbox(
            "Sequence Type:",
            sequence_options,
            key='sequence_selector'
        )
        
        # Show sequence details
        if "Dark Current" in sequence_type:
            st.info("""
            **Dark Current Check:**
            - Measures baseline noise for all 3 PMTs
            - Duration: 5 minutes
            - No light source (laser off)
            """)
        
        elif "Single PMT" in sequence_type:
            pmt_select = st.selectbox("Select PMT:", ["PMT 1", "PMT 2"], key="single_pmt_select")
            st.session_state.selected_pmt = pmt_select  # Store in session state
            st.info(f"""
            **Single PMT Scan - {pmt_select}:**
            - Scans one PMT at multiple angles
            - Robot moves through zenith/azimuth positions
            - Estimated time: ~3.5 hours
            """)
        
        elif "Full PMT Scan" in sequence_type:
            st.info("""
            **Full PMT Scan:**
            - Scans both PMT1 and PMT2
            - Complete angular characterization
            - Estimated time: ~7 hours
            """)
    
    with col2:
        st.markdown("**Run Configuration:**")
        
        run_name = st.text_input("Run Name:", 
                                value=f"run_{datetime.now().strftime('%Y%m%d_%H%M')}")
        
        # Scheduled start - improved implementation
        st.markdown("##### Scheduled Start (Optional)")
        col_delay1, col_delay2 = st.columns(2)
        
        with col_delay1:
            delay_hours = st.number_input(
                "Hours:",
                min_value=0,
                max_value=48,
                value=st.session_state.delay_hours,
                key='delay_hours_input',
                help="Delay run start by this many hours"
            )
            st.session_state.delay_hours = delay_hours
        
        with col_delay2:
            delay_minutes = st.number_input(
                "Minutes:", 
                min_value=0,
                max_value=59,
                value=st.session_state.delay_minutes,
                key='delay_minutes_input',
                help="Delay run start by this many minutes"
            )
            st.session_state.delay_minutes = delay_minutes
        
        total_delay_seconds = delay_hours * 3600 + delay_minutes * 60
        if total_delay_seconds > 0:
            start_time = datetime.now() + timedelta(seconds=total_delay_seconds)
            st.info(f"🕐 Run will start at: **{start_time.strftime('%H:%M:%S')}**")
        else:
            st.caption("Set hours/minutes above to schedule a delayed start")
    
    st.markdown("---")
    
    # Run Control - Use built-in functions
    st.subheader("Run Control")

    # Check if all required systems are ready
    system_ready = (
        st.session_state.system_coordinator is not None and
        bool(st.session_state.pmt_serial_number["pmt1"]) and
        bool(st.session_state.pmt_serial_number["pmt2"]) and
        bool(st.session_state.pmt_voltages[0]) and
        bool(st.session_state.pmt_voltages[1])
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        use_custom_scan_angles = st.checkbox("Use custom scan angles", value = Felse)

        zenith_input = st.text_input(
            "Zenith angles (comma separated)",
            value = "0,10,20,30,40,50",
            help = "allowed values: 0,10,20,30,40,50"
        )

        azimuth_input = st.text_input(
            "Azimuth angles (comma separated)",
            value = "0,90,180,270",
            help = "allowed values: 0,90,180,270"
        )

        def parse_angles(s):
            return [float(x.strip()) for x in s.split(",") if x.strip()]

        # Show different button text based on state
        if st.session_state.run_scheduled:
            button_text = "Waiting (Scheduled)"
            button_disabled = True
            button_type = "secondary"
        elif st.session_state.run_active:
            button_text = "▶ Running..."
            button_disabled = True
            button_type = "secondary"
        else:
            total_delay = st.session_state.delay_hours * 3600 + st.session_state.delay_minutes * 60
            if total_delay > 0:
                button_text = f"▶ Schedule Start ({st.session_state.delay_hours}h {st.session_state.delay_minutes}m)"
            else:
                button_text = "▶ Start Run Now"
            button_disabled = not system_ready
            button_type = "primary"
        
        if st.button(button_text, 
                    use_container_width=True, 
                    type=button_type,
                    disabled=button_disabled,
                    key="start_run_button"):
            if system_ready:
                if use_custom_scan_angles:
                    try:
                        zeniths = parse_angles(zenith_input)
                        azimuths = parse_angles(azimuth_input)
                    except:
                        st.error("Invalid angle input")
                        st.stop()

                    if not zeniths or not azimuths:
                        st.error("Angles cannot be empty")
                        st.stop()

            else:
                zeniths = [0, 10, 20, 30, 40, 50]
                azimuths = [0, 90, 180, 270]

                # Calculate delay
                delay_seconds = st.session_state.delay_hours * 3600 + st.session_state.delay_minutes * 60
                
                # Reset state
                st.session_state.run_active = False  # Not active yet if scheduled
                st.session_state.run_scheduled = (delay_seconds > 0)  # Scheduled if delay > 0
                st.session_state.run_progress = 0
                st.session_state.run_result = None
                st.session_state.run_position = ""
                st.session_state.run_status_text = "Scheduled..." if delay_seconds > 0 else "Initializing..."
                st.session_state.stop_requested = False
                
                # Store run metadata for logging (both in session_state and shared_state)
                metadata = {
                    'run_name': run_name,
                    'sequence_type': sequence_type,
                    'pmt_serials': f"{st.session_state.pmt_serial_number['pmt1']}, {st.session_state.pmt_serial_number['pmt2']}",
                    'pmt_voltages': f"{st.session_state.pmt_voltages[0]}V, {st.session_state.pmt_voltages[1]}V",
                    'start_time': datetime.now()
                }
                st.session_state.run_metadata = metadata
                shared_state.progress_data['run_metadata'] = metadata  # Persist across restarts
                
                # Reset shared progress dictionary
                shared_state.progress_data['progress_pct'] = 0
                shared_state.progress_data['status_text'] = 'Scheduled...' if delay_seconds > 0 else 'Initializing...'
                shared_state.progress_data['position'] = ''
                shared_state.progress_data['active'] = False  # Not active yet if scheduled
                shared_state.progress_data['scheduled'] = (delay_seconds > 0)
                shared_state.progress_data['result'] = None
                shared_state.progress_data['cancelled'] = False
               
                # Prepare parameters based on sequence type
                params = {}
                
                if "Dark Current" in sequence_type:
                    params = {
                        'pmt1_serial': st.session_state.pmt_serial_number["pmt1"],
                        'pmt2_serial': st.session_state.pmt_serial_number["pmt2"],
                        'duration': 300  # 5 minutes
                    }
                
                elif "Single PMT" in sequence_type:
                    pmt_num = 1 if st.session_state.get('selected_pmt', 'PMT 1') == "PMT 1" else 2
                    params = {
                        'pmt_num': pmt_num,
                        'serial': st.session_state.pmt_serial_number[f"pmt{pmt_num}"],
                        'zeniths': zeniths,
                        'azimuths': azimuths,
                        'daq_runtime': 600
                    }
                
                elif "Full PMT Scan" in sequence_type:
                    params = {
                        'pmt1_serial': st.session_state.pmt_serial_number["pmt1"],
                        'pmt2_serial': st.session_state.pmt_serial_number["pmt2"],
                        'zeniths': zeniths,
                        'azimuths': azimuths,
                        'daq_runtime': 600
                    }
                
                # Start background thread - use scheduled start worker if delay, otherwise normal worker
                if delay_seconds > 0:
                    # Scheduled start
                    thread = threading.Thread(
                        target=scheduled_start_worker,
                        args=(st.session_state.system_coordinator, sequence_type, params, delay_seconds),
                        daemon=True,
                        name="ScheduledStartThread"
                    )
                    print(f"[GUI] Scheduled {sequence_type} to start in {delay_seconds}s ({st.session_state.delay_hours}h {st.session_state.delay_minutes}m)")
                else:
                    # Immediate start
                    st.session_state.run_active = True  # Mark as active immediately
                    shared_state.progress_data['active'] = True
                    thread = threading.Thread(
                        target=run_sequence_worker,
                        args=(st.session_state.system_coordinator, sequence_type, params),
                        daemon=True,
                        name="RunSequenceThread"
                    )
                    print(f"[GUI] Started {sequence_type} immediately in background thread")
                
                thread.start()
                st.session_state.run_thread = thread
                st.rerun()

    with col2:
        if st.session_state.run_active:
            if st.button("⏸ Pause", use_container_width=True, disabled=True):
                st.caption("⚠️ Pause not supported")

    with col3:
        # Show stop button for both scheduled and active runs
        if st.session_state.run_active or st.session_state.run_scheduled:
            button_label = "⏹ Cancel Scheduled Start" if st.session_state.run_scheduled else "⏹ Stop"
            if st.button(button_label, use_container_width=True, type="secondary"):
                if st.session_state.run_scheduled:
                    # Cancel scheduled start
                    shared_state.progress_data['cancelled'] = True
                    st.session_state.run_scheduled = False
                    st.session_state.run_active = False
                    st.session_state.run_progress = 0
                    st.warning("⏹ Scheduled start cancelled")
                else:
                    # Stop running sequence
                    st.session_state.run_active = False
                    st.session_state.run_progress = 0
                    st.warning("⏹ Run marked as stopped (actual scan may continue)")
                st.rerun()

    with col4:
        # View Logs button (not functional without subprocess)
        if st.session_state.run_active:
            if st.button("📋 View Logs", use_container_width=True, disabled=True):
                st.caption("⚠️ Logs not available (no subprocess)")
    
    # Check thread status and display result if complete
    if st.session_state.run_thread is not None:
        is_alive = st.session_state.run_thread.is_alive()
        if not is_alive:
            # Thread finished!
            st.session_state.run_active = False
            st.session_state.run_scheduled = False
            
            result = st.session_state.run_result
            if result:
                # Worker thread already logged the run - just display status message
                
                # Clear metadata from session state (worker already cleared from shared_state)
                if hasattr(st.session_state, 'run_metadata'):
                    del st.session_state.run_metadata
                
                # Show status message (worker thread already logged)
                if result.get('status') == 'success':
                    st.success(f"✓ {st.session_state.run_metadata.get('sequence_type', 'Run') if hasattr(st.session_state, 'run_metadata') else 'Run'} completed successfully!")
                    st.balloons()
                elif result.get('status') == 'cancelled':
                    st.info(f"⏹ {result.get('message', 'Scheduled start was cancelled')}")
                else:
                    st.error(f"✗ Run failed: {result.get('error', 'Unknown error')}")
            
            # Clear thread reference
            st.session_state.run_thread = None
            st.rerun()

    # Show readiness status
    if not system_ready and not st.session_state.run_active:
        reasons = []
        if st.session_state.system_coordinator is None:
            reasons.append("System coordinator not initialized")
        if not st.session_state.pmt_serial_number["pmt1"]:
            reasons.append("Enter PMT1 serial number")
        if not st.session_state.pmt_serial_number["pmt2"]:
            reasons.append("Enter PMT2 serial number")
        if not st.session_state.pmt_voltages[0]:
            reasons.append("Enter PMT1 High Voltage")
        if not st.session_state.pmt_voltages[1]:
            reasons.append("Enter PMT2 High Voltage")
        
        st.warning(f"⚠️ System not ready: {', '.join(reasons)}")
    
    # Scheduled Start Countdown Display
    if st.session_state.run_scheduled:
        st.markdown("---")
        st.subheader("⏰ Scheduled Start - Waiting")
        
        # Get countdown from shared state
        countdown_seconds = shared_state.progress_data.get('countdown_seconds', 0)
        scheduled_time = shared_state.progress_data.get('scheduled_start', datetime.now())
        
        # Format countdown as HH:MM:SS
        hours = countdown_seconds // 3600
        minutes = (countdown_seconds % 3600) // 60
        seconds = countdown_seconds % 60
        countdown_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Time Until Start", countdown_str)
        with col2:
            st.metric("Scheduled For", scheduled_time.strftime('%H:%M:%S'))
        with col3:
            st.metric("Sequence", sequence_type.split(' (')[0])  # Remove duration from display
        
        # Progress bar showing time elapsed
        total_delay = shared_state.progress_data.get('delay_seconds', countdown_seconds)
        if total_delay > 0:
            progress = 1.0 - (countdown_seconds / total_delay)
            st.progress(max(0.0, min(1.0, progress)))
        
        st.info("💡 The run will start automatically when the countdown reaches zero. Press 'Cancel Scheduled Start' to abort.")
    
    # Live status display when running
    if st.session_state.run_active:
        st.markdown("---")
        st.subheader("Run Status")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Script", st.session_state.get('run_script', 'Unknown'))
        with col2:
            st.metric("Status", "Running")
        with col3:
            # Check if process still alive
            if hasattr(st.session_state, 'run_process'):
                if st.session_state.run_process.poll() is None:
                    st.metric("Process", "Active")
                else:
                    st.metric("Process", "Complete")
                    st.session_state.run_active = False
        
        # Show live logs if requested
        if st.session_state.get('show_logs', False):
            with st.expander("📋 Live Output", expanded=True):
                if hasattr(st.session_state, 'run_process'):
                    # Read available output
                    import select
                    try:
                        # Non-blocking read
                        if select.select([st.session_state.run_process.stdout], [], [], 0)[0]:
                            output = st.session_state.run_process.stdout.readline()
                            if output:
                                st.text(output.strip())
                    except:
                        st.caption("No output available")
                
                if st.button("✖ Close Logs"):
                    st.session_state.show_logs = False
                    st.rerun()
    
    # Progress Display
    if st.session_state.run_active or st.session_state.run_progress > 0:
        st.markdown("---")
        st.subheader("Run Progress")
        
        # Display real progress from callback
        progress = st.session_state.run_progress / 100
        st.progress(max(0.0, min(1.0, progress)))
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Progress", f"{st.session_state.run_progress}%")
        with col2:
            st.metric("Current Position", st.session_state.run_position or "Initializing...")
        with col3:
            st.metric("Status", st.session_state.run_status_text or "Starting...")
        
        # Show PMT-specific output paths
        if st.session_state.pmt_serial_number["pmt1"] or st.session_state.pmt_serial_number["pmt2"]:
            paths = []
            if st.session_state.pmt_serial_number["pmt1"]:
                paths.append(f"PMT1: `/home/hyperkaus/WaveDumpSaves/{run_name}/{st.session_state.pmt_serial_number['pmt1']}/`")
            if st.session_state.pmt_serial_number["pmt2"]:
                paths.append(f"PMT2: `/home/hyperkaus/WaveDumpSaves/{run_name}/{st.session_state.pmt_serial_number['pmt2']}/`")
            st.caption(f"📁 Saving to: {' | '.join(paths)}")
        
        # Live log - capture recent terminal output
        with st.expander("Live Log", expanded=False):
            # Read recent lines from log file if it exists
            log_lines = []
            if hasattr(st.session_state, 'log_file') and st.session_state.log_file.exists():
                try:
                    with open(st.session_state.log_file, 'r') as f:
                        # Get last 50 lines
                        all_lines = f.readlines()
                        log_lines = all_lines[-50:] if len(all_lines) > 50 else all_lines
                except Exception as e:
                    log_lines = [f"Error reading log: {e}\n"]
            else:
                log_lines = ["No log file available yet. Logs will appear after starting a run.\n"]
            
            # Display in monospace
            st.code("".join(log_lines), language="log")
    
    st.markdown("---")
    
    # Run Log Information
    st.subheader("Run Log")
    
    log_file_path = Path("run_log.txt").absolute()
    
    st.info(f"📝 All completed runs are automatically logged to: `{log_file_path}`")
    
    # Show last few entries if file exists
    if log_file_path.exists():
        try:
            with open(log_file_path, 'r') as f:
                lines = f.readlines()
            
            if lines:
                # Show last 5 entries
                recent_lines = lines[-5:] if len(lines) >= 5 else lines
                st.text_area(
                    "Recent entries (last 5):", 
                    value="".join(recent_lines),
                    height=150,
                    disabled=True
                )
                st.caption(f"Total runs logged: {len(lines)}")
            else:
                st.caption("No runs logged yet. Complete a run to see it here.")
        except Exception as e:
            st.warning(f"Could not read log file: {e}")
    else:
        st.caption("Log file will be created after first run completes.")


# Footer
st.markdown("---")
st.caption("HyperK PMT DAQ Control System | University of Melbourne | 2025")
