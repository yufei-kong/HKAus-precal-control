"""
HyperK PMT DAQ Control System - GUI v4
Final refinements from November 2025

This is a PREVIEW/MOCKUP - no real devices connected

Usage:
    streamlit run hyperk_daq_gui_v4.py
"""

import streamlit as st
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json
import sys
import os
from pathlib import Path

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

# Page config
st.set_page_config(
    page_title="HyperK PMT DAQ Control",
    page_icon="⚛️",
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
        "Dark Current Check (5 min)",
        "Single PMT Test (10 min)", 
        "Full PMT Scan (2 hours)",
    ]
    
    if 'custom_sequences' in st.session_state and st.session_state.custom_sequences:
        custom_sequences = [f"Custom: {name}" for name in st.session_state.custom_sequences.keys()]
        return default_sequences + custom_sequences + ["Create New Custom Scan..."]
    else:
        return default_sequences + ["Create New Custom Scan..."]

# # Initialize hardware (add this section)
# if 'system' not in st.session_state and not st.session_state.get('mock_mode', False):
#     try:
#         # Import required modules
#         from xarm.wrapper import XArmAPI
#         from drivers.xarm_pmt_controller import XArmPMTController
#         from drivers.caen_digitizer_wavedump import CAENDigitizerWaveDump
#         from drivers.system_coordinator import HyperKSystemCoordinator
#         from api_client.device_api_client import WindowsDeviceClient
        
#         # Connect to robot
#         arm = XArmAPI('192.168.1.xxx')  # ← YOUR ROBOT IP HERE
#         arm.connect()
        
#         # Initialize digitizer
#         digitizer = CAENDigitizerWaveDump(
#             wavedump_path="/usr/local/bin/WaveDump",
#             config_template="configs/WaveDumpConfig_template.txt"
#         )
        
#         # Initialize robot controller
#         robot = XArmPMTController(arm=arm, digitizer=digitizer)
        
#         # Initialize API client for Windows devices
#         api_client = WindowsDeviceClient("192.168.0.186")  # ← YOUR WINDOWS IP HERE
        
#         # Create system coordinator
#         st.session_state.system = HyperKSystemCoordinator(
#             robot_controller=robot,
#             api_client=api_client
#         )
        
#         st.success("✓ All systems initialized")
        
#     except Exception as e:
#         st.error(f"Initialization failed: {e}")
#         st.session_state.system = None

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
        except Exception as e:
            st.session_state.sipm_supply = None
            st.session_state.sipm_connected = False
            print(f"SiPM initialization failed: {e}")
    else:
        st.session_state.sipm_supply = None
        st.session_state.sipm_connected = False

# SiPM output state
if 'sipm_output_on' not in st.session_state:
    st.session_state.sipm_output_on = False


# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'mode' not in st.session_state:
    st.session_state.mode = 'Run Sequence'
if 'run_active' not in st.session_state:
    st.session_state.run_active = False
if 'run_progress' not in st.session_state:
    st.session_state.run_progress = 0
if 'pmt_voltages' not in st.session_state:
    st.session_state.pmt_voltages = [1000, 1100, 950]
if 'pmt_power' not in st.session_state:
    st.session_state.pmt_power = [False, False, False]
if 'pmt_ramping' not in st.session_state:
    st.session_state.pmt_ramping = [False, False, False]
if 'scheduled_start' not in st.session_state:
    st.session_state.scheduled_start = None
if 'laser_ld_on' not in st.session_state:
    st.session_state.laser_ld_on = False
if 'laser_tec_on' not in st.session_state:
    st.session_state.laser_tec_on = False
if 'robot_position' not in st.session_state:
    st.session_state.robot_position = 'home'
if 'linear_stage_pos' not in st.session_state:
    st.session_state.linear_stage_pos = 657  # Middle position
if 'robot_coords' not in st.session_state:
    st.session_state.robot_coords = {'x': 200, 'y': 0, 'z': 300, 'roll': 0, 'pitch': 0, 'yaw': 0}
if 'device_enabled' not in st.session_state:
    st.session_state.device_enabled = {
        'pmt_hv': False,
        'sipm': False,
        'siggen': False,
        'laser': False,
        'robot': False
    }
if 'emergency_stop_confirm' not in st.session_state:
    st.session_state.emergency_stop_confirm = False
if 'custom_sequences' not in st.session_state:
    st.session_state.custom_sequences = {}
if 'pmt_serial_number' not in st.session_state:
    st.session_state.pmt_serial_number = {"pmt1": "", "pmt2": ""}
if 'laser_trigger_mode' not in st.session_state:
    st.session_state.laser_trigger_mode = "EXT"
if 'selected_sequence' not in st.session_state:
    st.session_state.selected_sequence = "Dark Current Check (5 min)"

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
    
    # PMT HV - green only when ALL are on and NOT ramping
    pmt_status = 'green' if pmt_ready else ('yellow' if any(st.session_state.pmt_power) or any(st.session_state.pmt_ramping) else 'red')
    st.markdown(f"{status_dot(pmt_status)} PMT HV System", unsafe_allow_html=True)
    if any(st.session_state.pmt_ramping):
        st.caption("  ↳ Ramping...")
    
    # SiPM
    if st.session_state.get('sipm_connected', False):
        if st.session_state.sipm_output_on:
            sipm_status = 'green'
        else:
            sipm_status = 'red'
    else:
        sipm_status = 'grey'

    st.markdown(f"{status_dot(sipm_status)} SiPM Supply", unsafe_allow_html=True)
    
    # Signal Gen
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
                # Execute emergency stop
                st.session_state.pmt_power = [False, False, False]
                st.session_state.pmt_ramping = [False, False, False]
                st.session_state.laser_ld_on = False
                st.session_state.laser_tec_on = False
                st.session_state.run_active = False
                st.session_state.device_enabled = {k: False for k in st.session_state.device_enabled}
                st.session_state.emergency_stop_confirm = False
                st.error("EMERGENCY STOP ACTIVATED!")
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
    
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("🔒 Lock", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()
    
    # Quick Actions
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("⚡ Power On All PMTs", use_container_width=True):
            st.session_state.pmt_power = [True, True, True]
            st.session_state.pmt_ramping = [True, True, True]
            st.session_state.device_enabled['pmt_hv'] = True
            st.success("All PMTs ramping up...")
            st.rerun()
    
    with col2:
        if st.button("🏠 Robot to Home", use_container_width=True):
            st.session_state.robot_position = 'home'
            st.session_state.linear_stage_pos = 657
            st.info("Robot moving to home...")
            st.rerun()
    
    with col3:
        if st.button("🔌 Power Off All", use_container_width=True):
            st.session_state.pmt_power = [False, False, False]
            st.session_state.pmt_ramping = [False, False, False]
            st.session_state.laser_ld_on = False
            st.session_state.laser_tec_on = False
            st.session_state.device_enabled = {k: False for k in st.session_state.device_enabled}
            st.warning("Powering down all devices...")
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
        
        for i in range(3):
            with st.expander(f"Channel {i+1} (PMT {i+1})", expanded=(i==0)):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    st.markdown("**Setpoints:**")
                    voltage = st.number_input(
                        "Voltage (V)", 
                        min_value=0, 
                        max_value=2000, 
                        value=st.session_state.pmt_voltages[i],
                        step=50,
                        key=f'pmt_v_{i}'
                    )
                    current_limit = st.number_input(
                        "Current Limit (µA)", 
                        min_value=0.0, 
                        max_value=3000.0, 
                        value=50.0,
                        step=10.0,
                        key=f'pmt_i_{i}'
                    )
                    ramp_rate = st.number_input(
                        "Ramp Rate (V/s)",
                        min_value=1,
                        max_value=100,
                        value=50,
                        step=10,
                        key=f'pmt_ramp_{i}'
                    )
                
                with col2:
                    st.markdown("**Monitoring:**")
                    
                    # Mock monitoring with ramping behavior
                    if st.session_state.pmt_power[i]:
                        if st.session_state.pmt_ramping[i]:
                            v_mon = voltage * 0.75  # Simulating ramping
                            status_text = f"{status_dot('yellow')} Ramping Up"
                        else:
                            v_mon = voltage * 0.98
                            status_text = f"{status_dot('green')} On"
                    else:
                        v_mon = 0
                        status_text = f"{status_dot('grey')} Off"
                    
                    st.markdown(status_text, unsafe_allow_html=True)
                    st.metric("Voltage (V)", f"{v_mon:.1f}")
                    st.metric("Current (µA)", f"{2.3 if st.session_state.pmt_power[i] else 0:.1f}")
                
                with col3:
                    st.markdown("**Control:**")
                    st.write(" ")
                    
                    if not st.session_state.pmt_power[i]:
                        if st.button(f"Turn ON", key=f'pmt_on_{i}', use_container_width=True):
                            st.session_state.pmt_power[i] = True
                            st.session_state.pmt_ramping[i] = True
                            st.session_state.pmt_voltages[i] = voltage
                            st.session_state.device_enabled['pmt_hv'] = any(st.session_state.pmt_power)
                            st.rerun()
                    else:
                        if st.button(f"Turn OFF", key=f'pmt_off_{i}', use_container_width=True):
                            st.session_state.pmt_power[i] = False
                            st.session_state.pmt_ramping[i] = False
                            st.session_state.device_enabled['pmt_hv'] = any(st.session_state.pmt_power)
                            st.rerun()
                    
                    if st.session_state.pmt_ramping[i]:
                        if st.button(f"✓ Done", key=f'pmt_done_{i}', use_container_width=True):
                            st.session_state.pmt_ramping[i] = False
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
                    set_i1 = 1000.0
                
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
                    set_i2 = 1000.0
                
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
                            st.success("✓ Output enabled")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
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
                            st.info("✓ Output disabled")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to disable output: {e}")
            
            st.markdown("---")
            
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
        st.subheader("Siglent SDG2122X Signal Generator")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Waveform Configuration:**")
            waveform = st.selectbox("Waveform:", ["PULSE", "SINE", "SQUARE", "RAMP"], key="wave_type")
            frequency = st.number_input("Frequency (Hz)", min_value=1, max_value=120000000, value=1000, key="freq")
            amplitude = st.number_input("Amplitude (V)", min_value=0.0, max_value=10.0, value=3.3, step=0.1, key="amp")
            offset = st.number_input("Offset (V)", min_value=-5.0, max_value=5.0, value=0.0, step=0.1, key="offset")
            
            if waveform == "PULSE":
                pulse_width = st.number_input("Pulse Width (ns)", min_value=8, max_value=1000000, value=100, key="pulse_width")
        
        with col2:
            st.markdown("**Output Configuration:**")
            impedance = st.selectbox("Load Impedance:", ["50Ω", "High-Z"], key="sig_imp")
            polarity = st.selectbox("Polarity:", ["Normal", "Inverted"], key="sig_pol")
            
            st.markdown("---")
            st.markdown("**Status:**")
            if st.session_state.device_enabled['siggen']:
                st.markdown(f"{status_dot('green')} Output ON", unsafe_allow_html=True)
            else:
                st.markdown(f"{status_dot('grey')} Output OFF", unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("**Control:**")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Enable Output", key="sig_enable", use_container_width=True):
                    st.session_state.device_enabled['siggen'] = True
                    st.success("Output enabled")
                    st.rerun()
            with col_b:
                if st.button("Disable Output", key="sig_disable", use_container_width=True):
                    st.session_state.device_enabled['siggen'] = False
                    st.info("Output disabled")
                    st.rerun()
        
        if st.button("Apply Configuration", key="sig_apply", use_container_width=True):
            st.success("Signal generator configured")
    
    # TAB 4: Laser Control
    with tabs[3]:
        st.subheader("Tama Electric LSB-200 Picosecond Laser Driver")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Temperature Controller (TEC):**")
            
            tec_setpoint = st.number_input("Temperature Setpoint (°C)", 
                                          min_value=15.0, 
                                          max_value=30.0, 
                                          value=25.0, 
                                          step=0.1,
                                          key="tec_temp")
            
            if st.session_state.laser_tec_on:
                st.metric("Current Temp", "24.8 °C")
                st.markdown(f"{status_dot('green')} TEC ON", unsafe_allow_html=True)
            else:
                st.metric("Current Temp", "22.1 °C")
                st.markdown(f"{status_dot('grey')} TEC OFF", unsafe_allow_html=True)
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("TEC ON", key="tec_on", use_container_width=True):
                    st.session_state.laser_tec_on = True
                    # Update device_enabled if both TEC and LD are on
                    if st.session_state.laser_tec_on and st.session_state.laser_ld_on:
                        st.session_state.device_enabled['laser'] = True
                    st.rerun()
            with col_b:
                if st.button("TEC OFF", key="tec_off", use_container_width=True):
                    st.session_state.laser_tec_on = False
                    st.session_state.device_enabled['laser'] = False
                    st.rerun()
        
        with col2:
            st.markdown("**Laser Diode (LD):**")
            
            ld_current = st.number_input("LD Current (mA)", 
                                        min_value=0.0, 
                                        max_value=100.0, 
                                        value=50.0, 
                                        step=1.0,
                                        key="ld_current")
            
            # Trigger mode selection
            trigger_mode = st.selectbox("Trigger Mode:", 
                                       ["EXT", "PG1", "PG2"],
                                       index=["EXT", "PG1", "PG2"].index(st.session_state.laser_trigger_mode),
                                       key="laser_trig_mode")
            
            st.session_state.laser_trigger_mode = trigger_mode
            
            # Only show pulse rate if PG1 or PG2 selected
            if trigger_mode in ["PG1", "PG2"]:
                pulse_rate = st.number_input("Pulse Rate (kHz)",
                                            min_value=0.1,
                                            max_value=100.0,
                                            value=10.0,
                                            step=0.1,
                                            key="ld_rate")
            else:
                st.caption("Pulse rate controlled externally")
            
            if st.session_state.laser_ld_on:
                st.markdown(f"{status_dot('green')} LD ON", unsafe_allow_html=True)
            else:
                st.markdown(f"{status_dot('grey')} LD OFF", unsafe_allow_html=True)
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("LD ON", key="ld_on", use_container_width=True):
                    if st.session_state.laser_tec_on:
                        st.session_state.laser_ld_on = True
                        # Update device_enabled to sync with Run Sequence page
                        if st.session_state.laser_tec_on and st.session_state.laser_ld_on:
                            st.session_state.device_enabled['laser'] = True
                        st.rerun()
                    else:
                        st.error("Enable TEC first!")
            with col_b:
                if st.button("LD OFF", key="ld_off", use_container_width=True):
                    st.session_state.laser_ld_on = False
                    st.session_state.device_enabled['laser'] = False
                    st.rerun()
        
        st.markdown("---")
        st.warning("⚠️ **Safety:** Always enable TEC before turning on LD")
    
    # TAB 5: Robot Control
    with tabs[4]:
        st.subheader("xArm + Linear Stage Control")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("**Linear Stage:**")
            
            # Progress bar for linear stage position
            stage_min = 240  # PMT2
            stage_max = 1074  # PMT1
            stage_range = stage_max - stage_min
            stage_progress = (st.session_state.linear_stage_pos - stage_min) / stage_range
            
            st.progress(stage_progress)
            st.caption(f"Position: {st.session_state.linear_stage_pos} mm")
            
            # Quick position buttons
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("📍 PMT1 (1074mm)", key="stage_pmt1", use_container_width=True):
                    st.session_state.linear_stage_pos = 1074
                    st.session_state.robot_position = 'pmt1'
                    st.info("Moving to PMT1...")
                    st.rerun()
            with col_b:
                if st.button("📍 PMT2 (240mm)", key="stage_pmt2", use_container_width=True):
                    st.session_state.linear_stage_pos = 240
                    st.session_state.robot_position = 'pmt2'
                    st.info("Moving to PMT2...")
                    st.rerun()
            
            # Manual position slider
            new_pos = st.slider("Manual Position (mm)", 
                               min_value=stage_min, 
                               max_value=stage_max, 
                               value=st.session_state.linear_stage_pos,
                               key="stage_manual")
            if st.button("Move to Position", key="stage_move"):
                st.session_state.linear_stage_pos = new_pos
                st.info(f"Moving to {new_pos} mm...")
                st.rerun()
        
        with col2:
            st.markdown("**xArm Robot:**")
            
            # Display current position
            coords = st.session_state.robot_coords
            st.markdown(f"""
            **Current Position:**
            - X: {coords['x']} mm
            - Y: {coords['y']} mm  
            - Z: {coords['z']} mm
            - Roll: {coords['roll']}°
            - Pitch: {coords['pitch']}°
            - Yaw: {coords['yaw']}°
            """)
            
            # Quick positions
            st.markdown("**Quick Positions:**")
            
            if st.button("🏠 Initial (Home)", key="robot_home", use_container_width=True):
                st.session_state.robot_position = 'home'
                st.session_state.robot_coords = {'x': 200, 'y': 0, 'z': 300, 'roll': 0, 'pitch': 0, 'yaw': 0}
                st.info("Moving to Home...")
                st.rerun()
            
            if st.button("🔄 Intermediate", key="robot_inter", use_container_width=True):
                st.session_state.robot_position = 'intermediate'
                st.session_state.robot_coords = {'x': 150, 'y': 100, 'z': 400, 'roll': 0, 'pitch': 45, 'yaw': 0}
                st.info("Moving to Intermediate...")
                st.rerun()
            
            if st.button("🔝 PMT Top", key="robot_top", use_container_width=True):
                st.session_state.robot_position = 'pmt_top'
                st.session_state.robot_coords = {'x': 100, 'y': 150, 'z': 500, 'roll': 0, 'pitch': 90, 'yaw': 0}
                st.info("Moving to PMT Top...")
                st.rerun()
        
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
            
            # Configuration
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Acquisition Settings:**")
                
                acq_duration = st.number_input(
                    "Duration (seconds)",
                    min_value=1,
                    max_value=3600,
                    value=5,
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
                    default=[2, 3, 4],
                    format_func=lambda x: available_channels[x],
                    key="manual_acq_channels"
                )
                
                record_length = st.number_input(
                    "Record Length (samples)",
                    min_value=128,
                    max_value=8192,
                    value=1024,
                    step=128,
                    key="manual_record_length"
                )
            
            with col2:
                st.markdown("**Trigger Settings:**")
                
                trigger_channel = st.selectbox(
                    "Trigger Channel",
                    options=list(available_channels.keys()),
                    index=4,  # Default to Ch4
                    format_func=lambda x: available_channels[x],
                    key="manual_trigger_ch"
                )
                
                trigger_threshold = st.number_input(
                    "Trigger Threshold (ADC counts)",
                    min_value=1,
                    max_value=4095,
                    value=1,
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
            
            output_dir = st.text_input(
                "Output Directory",
                value="../WaveDumpSaves/manual_acquisition",
                key="manual_output_dir",
                help="Where to save organized files"
            )
            
            file_prefix = st.text_input(
                "File Prefix",
                value="manual",
                key="manual_file_prefix",
                help="Prefix for saved files"
    )
            
            # Acquisition controls
            col_a, col_b, col_c = st.columns([2, 1, 1])
            
            with col_a:
                if st.button(
                    "▶ Start Acquisition",
                    type="primary",
                    use_container_width=True,
                    disabled=not digitizer_ready or st.session_state.run_active,
                    key="start_manual_acq"
                ):
                    if digitizer_ready and channels:
                        with st.spinner(f"Acquiring data for {acq_duration}s..."):
                            try:
                                # Configure digitizer
                                st.session_state.digitizer.configure(
                                    run_duration=acq_duration,
                                    channels=channels,
                                    trigger_channel=trigger_channel,
                                    trigger_threshold=trigger_threshold,
                                    channel_trigger_mode=trigger_mode,
                                    record_length=record_length
                                )
                                
                                # Acquire data
                                success = st.session_state.digitizer.acquire(
                                    timeout=acq_duration + 30,
                                    show_output=False  # Don't show WaveDump output in GUI
                                )
                                
                                if success:
                                    # Check what files were created (before organizing)
                                    waveform_files = st.session_state.digitizer.get_all_waveforms(channels)
                                    num_files = len(waveform_files)
                                    
                                    # Organize files
                                    try:
                                        # Use prefix or default to "data" if empty
                                        prefix = file_prefix.strip() if file_prefix.strip() else "data"
                                        
                                        save_path = st.session_state.digitizer.organize_files(
                                            save_dir=output_dir,
                                            prefix=prefix,
                                            channels=channels,
                                            include_timestamp=True
                                        )
                                        
                                        # Save info about acquisition
                                        st.session_state.last_acquisition = {
                                            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                            'duration': acq_duration,
                                            'channels': channels,
                                            'num_files': num_files,
                                            'save_path': save_path,
                                            'prefix': prefix
                                        }
                                        
                                        st.success(f"✓ Acquisition complete! Files saved to:")
                                        st.code(str(save_path))
                                        
                                        # Show organized files (use new paths)
                                        for ch in channels:
                                            filename = f"{prefix}_wave{ch}.txt"
                                            st.text(f"  Ch{ch}: {filename}")
                                        
                                    except Exception as e:
                                        st.error(f"File organization failed: {e}")
                                        import traceback
                                        st.text(traceback.format_exc())
                                    
                                    # Update digitizer status
                                    st.session_state.digitizer_status = st.session_state.digitizer.get_status()
                                    
                                else:
                                    st.error("❌ Acquisition failed - check WaveDump output")
                            
                            except Exception as e:
                                st.error(f"❌ Acquisition error: {e}")
                                import traceback
                                st.text(traceback.format_exc())
                    else:
                        if not channels:
                            st.error("⚠ Please select at least one channel")
            
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
    
    # PMT Serial Number Input - Two PMTs
    st.subheader("PMT Configuration")
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        pmt1_serial = st.text_input("PMT1 Serial Number:", 
                                   value=st.session_state.pmt_serial_number["pmt1"],
                                   placeholder="e.g., ZE1234",
                                   key="pmt1_serial_input",
                                   help="Serial number for PMT at position 1")
        st.session_state.pmt_serial_number["pmt1"] = pmt1_serial
    
    with col2:
        pmt2_serial = st.text_input("PMT2 Serial Number:", 
                                   value=st.session_state.pmt_serial_number["pmt2"],
                                   placeholder="e.g., ZE5678",
                                   key="pmt2_serial_input",
                                   help="Serial number for PMT at position 2")
        st.session_state.pmt_serial_number["pmt2"] = pmt2_serial
    
    with col3:
        st.write(" ")  # Spacer
        if pmt1_serial and pmt2_serial:
            st.info(f"📁 PMT1: `/data/runs/{pmt1_serial}/` | PMT2: `/data/runs/{pmt2_serial}/`")
        elif pmt1_serial or pmt2_serial:
            if pmt1_serial:
                st.info(f"📁 PMT1: `/data/runs/{pmt1_serial}/` | ⚠️ PMT2: Not set")
            else:
                st.info(f"⚠️ PMT1: Not set | 📁 PMT2: `/data/runs/{pmt2_serial}/`")
        else:
            st.warning("⚠️ Please enter PMT serial numbers before starting measurements")
    
    st.markdown("---")
    
    # Device ON/OFF controls on main page - synced with Setup & Monitor
    st.subheader("System Control")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button(
            f"{'✓' if st.session_state.device_enabled['pmt_hv'] else '○'} PMT HV",
            use_container_width=True,
            key='toggle_pmt'
        ):
            st.session_state.device_enabled['pmt_hv'] = not st.session_state.device_enabled['pmt_hv']
            if st.session_state.device_enabled['pmt_hv']:
                st.session_state.pmt_power = [True, True, True]
            else:
                st.session_state.pmt_power = [False, False, False]
            st.rerun()
    
    with col2:
        if st.button(
            f"{'✓' if st.session_state.device_enabled['sipm'] else '○'} SiPM",
            use_container_width=True,
            key='toggle_sipm'
        ):
            st.session_state.device_enabled['sipm'] = not st.session_state.device_enabled['sipm']
            st.rerun()
    
    with col3:
        if st.button(
            f"{'✓' if st.session_state.device_enabled['siggen'] else '○'} Sig Gen",
            use_container_width=True,
            key='toggle_siggen'
        ):
            st.session_state.device_enabled['siggen'] = not st.session_state.device_enabled['siggen']
            st.rerun()
    
    with col4:
        if st.button(
            f"{'✓' if st.session_state.device_enabled['laser'] else '○'} Laser",
            use_container_width=True,
            key='toggle_laser'
        ):
            st.session_state.device_enabled['laser'] = not st.session_state.device_enabled['laser']
            if st.session_state.device_enabled['laser']:
                st.session_state.laser_tec_on = True
                st.session_state.laser_ld_on = True
            else:
                st.session_state.laser_tec_on = False
                st.session_state.laser_ld_on = False
            st.rerun()
    
    st.markdown("---")
    
    # Run Selection
    st.subheader("Select Measurement Sequence")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Get available sequences (includes custom ones)
        available_sequences = get_sequence_list()
        
        sequence_type = st.selectbox(
            "Sequence Type:",
            available_sequences,
            index=available_sequences.index(st.session_state.selected_sequence) if st.session_state.selected_sequence in available_sequences else 0,
            key='sequence_selector'
        )
        
        # Update session state when selection changes
        if sequence_type != st.session_state.selected_sequence:
            st.session_state.selected_sequence = sequence_type
        
        # Use session state value for display
        sequence_type = st.session_state.selected_sequence
        
        # Show sequence details
        if "Dark Current" in sequence_type:
            st.info("""
            **Dark Current Check:**
            1. Powers on all PMTs
            2. Waits for stabilization (5 min)
            3. Records baseline without signal
            4. Checks for excessive dark current
            """)
            
            # Option to view waveforms during dark current check
            view_waveforms = st.checkbox("Enable waveform viewing during acquisition")
            if view_waveforms:
                st.caption("💡 Waveforms will be displayed in real-time during the dark current check")
        
        elif "Single PMT" in sequence_type:
            # Only PMT1 and PMT2 are accessible (PMT3 is monitor only)
            pmt_select = st.selectbox("Select PMT:", ["PMT 1", "PMT 2"])
            st.info(f"""
            **Single PMT Test - {pmt_select}:**
            1. Powers on selected PMT
            2. Moves robot to position
            3. Configures signal generator & laser
            4. Acquires data for specified runtime
            5. Analyzes waveforms
            
            Note: PMT3 is a monitor PMT and not accessible by robot
            """)
        
        elif "Full PMT Scan" in sequence_type:
            st.info("""
            **Full PMT Scan:**
            1. Dark current check (5 min)
            2. For each accessible PMT (1, 2):
               - Move robot to position
               - Configure signal generator & laser
               - Scan zenith: 0°, 30°, 60°, 90°
               - Scan azimuth: 0°, 90°, 180°, 270°
               - Record data at each position
            3. Return robot to home
            4. Power down safely
            
            **Total positions:** 24 (2 PMTs × 4 zenith × 3 azimuth)
            **Estimated time:** 2 hours
            
            Note: PMT3 operates as monitor only
            """)
        
        elif "Custom:" in sequence_type:
            # Load saved custom sequence
            custom_name = sequence_type.replace("Custom: ", "")
            config = st.session_state.custom_sequences[custom_name]
            
            st.success(f"Loaded custom sequence: **{custom_name}**")
            st.json(config)
            
            if st.button("🗑️ Delete This Sequence", key="delete_custom"):
                del st.session_state.custom_sequences[custom_name]
                st.success(f"Deleted sequence: {custom_name}")
                st.rerun()
        
        elif "Create New Custom" in sequence_type:
            st.markdown("**Create Custom Scan:**")
            
            # Name the custom sequence
            custom_seq_name = st.text_input("Sequence Name:", 
                                           placeholder="e.g., Quick Zenith Scan",
                                           key="custom_name")
            
            col_a, col_b = st.columns(2)
            with col_a:
                # Only PMT1 and PMT2 selectable
                pmts_to_scan = st.multiselect("PMTs:", ["PMT 1", "PMT 2"], default=["PMT 1"])
                st.caption("PMT 3 is monitor-only")
                zenith_angles = st.text_input("Zenith (°):", value="0, 30, 60, 90")
            with col_b:
                azimuth_angles = st.text_input("Azimuth (°):", value="0, 90, 180, 270")
                runtime_per_pos = st.number_input("Runtime/Position (s):", value=60, step=10)
            
            # Calculate estimated time
            n_pmts = len(pmts_to_scan)
            n_zenith = len([x.strip() for x in zenith_angles.split(',') if x.strip()])
            n_azimuth = len([x.strip() for x in azimuth_angles.split(',') if x.strip()])
            total_positions = n_pmts * n_zenith * n_azimuth
            estimated_time_min = (runtime_per_pos * total_positions) / 60
            
            st.info(f"""
            **Estimated scan:**
            - Total positions: {total_positions}
            - Time per position: {runtime_per_pos}s
            - Estimated total time: {estimated_time_min:.1f} minutes
            """)
    
    with col2:
        st.markdown("**Run Configuration:**")
        
        run_name = st.text_input("Run Name:", 
                                value=f"run_{datetime.now().strftime('%Y%m%d_%H%M')}")
        
        # Scheduled start
        schedule_run = st.checkbox("Schedule Start Time")
        
        if schedule_run:
            delay_hours = st.number_input("Delay (hours):", 
                                         min_value=0, 
                                         max_value=24, 
                                         value=2)
            delay_minutes = st.number_input("Delay (minutes):", 
                                           min_value=0, 
                                           max_value=59, 
                                           value=0)
            
            scheduled_time = datetime.now() + timedelta(hours=delay_hours, minutes=delay_minutes)
            st.info(f"⏱️ {scheduled_time.strftime('%Y-%m-%d %H:%M')}")
            
            if st.button("Schedule Run", use_container_width=True):
                st.session_state.scheduled_start = scheduled_time
                st.success(f"Scheduled!")
        else:
            st.session_state.scheduled_start = None
    
    st.markdown("---")
    
    # Run Control - Start only enabled when all systems ready
    col1, col2, col3, col4 = st.columns(4)
    
    # Check if all required systems are ready AND both PMT serial numbers are entered
    can_start = all_systems_ready and bool(st.session_state.pmt_serial_number["pmt1"]) and bool(st.session_state.pmt_serial_number["pmt2"])
    
    with col1:
        if not st.session_state.run_active:
            if st.button("▶ Start Run", 
                        use_container_width=True, 
                        type="primary",
                        disabled=not can_start):
                if can_start:
                    st.session_state.run_active = True
                    st.session_state.run_progress = 0
                    st.success("Run started!")
                    st.rerun()
                else:
                    st.error("Check system status and PMT serial number!")
    
    with col2:
        if st.session_state.run_active:
            if st.button("⏸ Pause", use_container_width=True):
                st.warning("Run paused")
    
    with col3:
        if st.session_state.run_active:
            if st.button("⏹ Stop", use_container_width=True):
                st.session_state.run_active = False
                st.session_state.run_progress = 0
                st.info("Run stopped")
                st.rerun()
    
    with col4:
        # Save custom sequence - only show for custom scans
        if "Create New Custom" in sequence_type:
            if st.button("💾 Save Sequence", use_container_width=True):
                if custom_seq_name:
                    # Save the custom sequence configuration
                    config = {
                        'pmts': pmts_to_scan,
                        'zenith': zenith_angles,
                        'azimuth': azimuth_angles,
                        'runtime_per_pos': runtime_per_pos,
                        'created': datetime.now().strftime('%Y-%m-%d %H:%M')
                    }
                    save_custom_sequence(custom_seq_name, config)
                    st.success(f"Saved: {custom_seq_name}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Please enter a sequence name")
    
    if not can_start and not st.session_state.run_active:
        reasons = []
        if not all_systems_ready:
            reasons.append("Enable all required devices")
        if not st.session_state.pmt_serial_number["pmt1"]:
            reasons.append("Enter PMT1 serial number")
        if not st.session_state.pmt_serial_number["pmt2"]:
            reasons.append("Enter PMT2 serial number")
        
        st.warning(f"⚠️ System not ready: {', '.join(reasons)}")
    
    # Progress Display
    if st.session_state.run_active or st.session_state.run_progress > 0:
        st.markdown("---")
        st.subheader("Run Progress")
        
        # Simulate progress
        if st.session_state.run_active and st.session_state.run_progress < 100:
            st.session_state.run_progress += 2
        
        progress = st.session_state.run_progress / 100
        st.progress(progress)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Progress", f"{st.session_state.run_progress}%")
        with col2:
            st.metric("Current Position", "PMT 2, Z=30°")
        with col3:
            st.metric("Events Recorded", "15,420")
        
        # Show PMT-specific output paths
        if st.session_state.pmt_serial_number["pmt1"] or st.session_state.pmt_serial_number["pmt2"]:
            paths = []
            if st.session_state.pmt_serial_number["pmt1"]:
                paths.append(f"PMT1: `/data/runs/{st.session_state.pmt_serial_number['pmt1']}/{run_name}/`")
            if st.session_state.pmt_serial_number["pmt2"]:
                paths.append(f"PMT2: `/data/runs/{st.session_state.pmt_serial_number['pmt2']}/{run_name}/`")
            st.caption(f"📁 Saving to: {' | '.join(paths)}")
        
        # Live log
        with st.expander("Live Log", expanded=False):
            pmt_info = []
            if st.session_state.pmt_serial_number["pmt1"]:
                pmt_info.append(f"PMT1: {st.session_state.pmt_serial_number['pmt1']}")
            if st.session_state.pmt_serial_number["pmt2"]:
                pmt_info.append(f"PMT2: {st.session_state.pmt_serial_number['pmt2']}")
            pmt_log = " | ".join(pmt_info) if pmt_info else "No PMT serial numbers set"
            
            st.text(f"""
[{datetime.now().strftime('%H:%M:%S')}] Run started: {run_name}
[{datetime.now().strftime('%H:%M:%S')}] {pmt_log}
[{datetime.now().strftime('%H:%M:%S')}] All devices ready
[{datetime.now().strftime('%H:%M:%S')}] Dark current check completed
[{datetime.now().strftime('%H:%M:%S')}] Moving to PMT 1, Zenith 0°
[{datetime.now().strftime('%H:%M:%S')}] Acquiring data...
[{datetime.now().strftime('%H:%M:%S')}] Position complete, organizing files by PMT serial number
[{datetime.now().strftime('%H:%M:%S')}] Moving to next position...
            """)
        
        # Waveform viewer for Dark Current Check
        if "Dark Current" in sequence_type and view_waveforms:
            with st.expander("📊 Live Waveforms", expanded=True):
                # Mock waveform display
                st.caption("Real-time waveform display during dark current measurement")
                
                # Generate mock waveform data
                x = np.linspace(0, 1000, 1000)
                noise = np.random.normal(0, 5, 1000)
                baseline = np.zeros(1000) + 100
                waveform = baseline + noise
                
                # Create simple chart
                chart_data = pd.DataFrame({
                    'Time (ns)': x,
                    'ADC': waveform
                })
                st.line_chart(chart_data.set_index('Time (ns)'))
                
                st.caption("Mean: 100.2 ADC | RMS: 4.8 ADC | Events: 1,234")
    
    st.markdown("---")
    
    # Recent Runs
    st.subheader("Recent Runs")
    
    recent_runs = pd.DataFrame({
        'Run Name': ['run_20251105_001', 'run_20251104_003', 'run_20251104_002'],
        'PMT S/N': ['ZE1234', 'ZE1235', 'ZE1234'],
        'Type': ['Full Scan', 'Single PMT (PMT1)', 'Dark Current'],
        'Status': ['Complete', 'Complete', 'Complete'],
        'Events': [36000, 5000, 500],
        'Duration': ['2h 15m', '12m', '5m'],
    })
    
    st.dataframe(recent_runs, use_container_width=True, hide_index=True)

# Footer
st.markdown("---")
st.caption("HyperK PMT DAQ Control System | University of Melbourne | 2025")