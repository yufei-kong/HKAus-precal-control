"""
HyperK PMT DAQ Control System - MOCK VERSION
For development/testing without hardware

Usage:
    streamlit run hyperk_daq_gui_MOCK.py
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import random

# Page config
st.set_page_config(
    page_title="HyperK PMT DAQ Control [MOCK]",
    page_icon="🎭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS - same as real GUI
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
    
    /* Progress bar */
    .stProgress > div > div {
        background-color: var(--accent-green) !important;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions
def status_dot(status: str) -> str:
    """Generate HTML status indicator"""
    return f'<span class="status-indicator status-{status}"></span>'

def check_password(password: str) -> bool:
    """Simple password check"""
    return password == "hyperk2025"

# ============================================================================
# MOCK DATA GENERATORS
# ============================================================================

def mock_ramp_voltage(current_v: float, target_v: float, ramp_rate: float = 50.0) -> float:
    """Simulate voltage ramping"""
    if abs(current_v - target_v) < 1:
        return target_v
    elif current_v < target_v:
        return min(current_v + ramp_rate * 2.0, target_v)  # 2s refresh interval
    else:
        return max(current_v - ramp_rate * 2.0, target_v)

def mock_current_reading(power_on: bool) -> float:
    """Simulate current reading with small fluctuations"""
    if power_on:
        return random.uniform(1.8, 2.2)  # µA
    return 0.0

def mock_temperature(target: float, current: float) -> float:
    """Simulate temperature approaching target"""
    if abs(current - target) < 0.1:
        return target + random.uniform(-0.05, 0.05)
    elif current < target:
        return current + 0.5
    else:
        return current - 0.5

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'mode' not in st.session_state:
    st.session_state.mode = 'Run Sequence'
if 'run_active' not in st.session_state:
    st.session_state.run_active = False
if 'run_progress' not in st.session_state:
    st.session_state.run_progress = 0

# MOCK: Always "connected"
if 'api_connected' not in st.session_state:
    st.session_state.api_connected = True
if 'sipm_connected' not in st.session_state:
    st.session_state.sipm_connected = True
if 'digitizer_connected' not in st.session_state:
    st.session_state.digitizer_connected = True

# CAEN HV mock state (channels 1-3)
if 'caen_channels' not in st.session_state:
    st.session_state.caen_channels = {
        1: {'voltage_set': 1000, 'voltage_mon': 0, 'current_mon': 0, 'current_set': 50.0,
            'ramp_up': 50, 'ramp_down': 100, 'power_on': False, 'ramping': False},
        2: {'voltage_set': 1100, 'voltage_mon': 0, 'current_mon': 0, 'current_set': 50.0,
            'ramp_up': 50, 'ramp_down': 100, 'power_on': False, 'ramping': False},
        3: {'voltage_set': 950, 'voltage_mon': 0, 'current_mon': 0, 'current_set': 50.0,
            'ramp_up': 50, 'ramp_down': 100, 'power_on': False, 'ramping': False},
    }

# History for graphs (current only for CAEN HV)
if 'caen_current_history' not in st.session_state:
    st.session_state.caen_current_history = {
        'ch1': [], 'ch2': [], 'ch3': [], 'timestamps': []
    }

# SiPM mock state
if 'sipm_output_on' not in st.session_state:
    st.session_state.sipm_output_on = False
if 'sipm_voltage_history' not in st.session_state:
    st.session_state.sipm_voltage_history = {'ch1': [], 'ch2': [], 'timestamps': []}
if 'sipm_current_history' not in st.session_state:
    st.session_state.sipm_current_history = {'ch1': [], 'ch2': [], 'timestamps': []}

# Laser mock state
if 'laser_ld_on' not in st.session_state:
    st.session_state.laser_ld_on = False
if 'laser_tec_on' not in st.session_state:
    st.session_state.laser_tec_on = False
if 'laser_temp' not in st.session_state:
    st.session_state.laser_temp = 22.0
if 'laser_temp_set' not in st.session_state:
    st.session_state.laser_temp_set = 25.0
if 'laser_board_temp' not in st.session_state:
    st.session_state.laser_board_temp = 28.0  # Board typically warmer than LD
if 'laser_temp_history' not in st.session_state:
    st.session_state.laser_temp_history = {'ld': [], 'board': [], 'timestamps': []}

# Robot mock state
if 'robot_position' not in st.session_state:
    st.session_state.robot_position = 'home'
if 'linear_stage_pos' not in st.session_state:
    st.session_state.linear_stage_pos = 657

# Device enabled state
if 'device_enabled' not in st.session_state:
    st.session_state.device_enabled = {
        'pmt_hv': False, 'sipm': False, 'siggen': False, 'laser': False
    }

# PMT serial numbers
if 'pmt_serial_number' not in st.session_state:
    st.session_state.pmt_serial_number = {"pmt1": "", "pmt2": ""}

if 'emergency_stop_confirm' not in st.session_state:
    st.session_state.emergency_stop_confirm = False

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.title("HyperK PMT DAQ")
    st.success("🎭 **MOCK MODE**")
    st.caption("Development version - no hardware")
    st.markdown("---")
    
    # Mode Selection
    st.subheader("Control Mode")
    
    previous_mode = st.session_state.get('previous_mode', 'Run Sequence')
    
    mode = st.radio(
        "Select Mode:",
        ["Run Sequence", "Setup & Monitor"],
        key='mode_selector',
        help="Run Sequence: Automated scans | Setup & Monitor: Expert control (password required)"
    )
    
    # Lock Setup & Monitor when switching away
    if previous_mode == "Setup & Monitor" and mode != "Setup & Monitor":
        st.session_state.authenticated = False
    
    st.session_state.mode = mode
    st.session_state.previous_mode = mode
    
    st.markdown("---")
    
    # System Status Summary
    st.subheader("System Status")
    
    # Check if systems are ready
    pmt_ready = any(st.session_state.caen_channels[i]['power_on'] for i in [1,2,3])
    laser_ready = st.session_state.laser_ld_on and st.session_state.laser_tec_on
    robot_ready = st.session_state.robot_position == 'home'
    
    all_systems_ready = pmt_ready and laser_ready and robot_ready and st.session_state.device_enabled['sipm']
    
    if all_systems_ready:
        st.markdown(f"{status_dot('green')} All Systems Ready", unsafe_allow_html=True)
    else:
        st.markdown(f"{status_dot('yellow')} System Not Ready", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Individual device status
    st.caption("**Device Status:**")
    
    # PMT HV
    pmt_status = 'green' if pmt_ready else 'red'
    st.markdown(f"{status_dot(pmt_status)} PMT HV System", unsafe_allow_html=True)
    if any(st.session_state.caen_channels[i]['ramping'] for i in [1,2,3]):
        st.caption("  ↳ Ramping...")
    
    # SiPM
    sipm_status = 'green' if st.session_state.sipm_output_on else 'red'
    st.markdown(f"{status_dot(sipm_status)} SiPM Supply", unsafe_allow_html=True)
    
    # Signal Gen
    siggen_status = 'green' if st.session_state.device_enabled['siggen'] else 'red'
    st.markdown(f"{status_dot(siggen_status)} Signal Generator", unsafe_allow_html=True)
    
    # Laser
    laser_status = 'green' if laser_ready else ('yellow' if (st.session_state.laser_ld_on or st.session_state.laser_tec_on) else 'red')
    st.markdown(f"{status_dot(laser_status)} Laser System", unsafe_allow_html=True)
    if st.session_state.laser_tec_on and not st.session_state.laser_ld_on:
        st.caption("  ↳ TEC only")
    
    # Robot
    robot_status = 'green' if robot_ready else 'yellow'
    st.markdown(f"{status_dot(robot_status)} Robot System", unsafe_allow_html=True)
    if not robot_ready:
        st.caption(f"  ↳ At {st.session_state.robot_position}")
    
    # Digitizer
    st.markdown(f"{status_dot('green')} CAEN Digitizer", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Emergency Stop
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
                for i in [1,2,3]:
                    st.session_state.caen_channels[i]['power_on'] = False
                    st.session_state.caen_channels[i]['ramping'] = False
                st.session_state.laser_ld_on = False
                st.session_state.laser_tec_on = False
                st.session_state.run_active = False
                st.session_state.device_enabled = {k: False for k in st.session_state.device_enabled}
                st.session_state.emergency_stop_confirm = False
                st.error("[MOCK] EMERGENCY STOP ACTIVATED!")
                time.sleep(1)
                st.rerun()
        with col2:
            if st.button("✗ NO", key='emergency_no'):
                st.session_state.emergency_stop_confirm = False
                st.rerun()
    
    st.markdown("---")
    st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

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
        st.info("**Note:** Password is `hyperk2025` (this is mock mode)")
        st.stop()

    # Auto-refresh every 2 seconds in Setup mode
    count = st_autorefresh(interval=2000, debounce=True, key="setup_autorefresh")
    
    # UPDATE MOCK DATA (simulate ramping, temperature changes, etc)
    for i in [1, 2, 3]:
        if st.session_state.caen_channels[i]['power_on']:
            current_v = st.session_state.caen_channels[i]['voltage_mon']
            target_v = st.session_state.caen_channels[i]['voltage_set']
            ramp_rate = st.session_state.caen_channels[i]['ramp_up']
            new_v = mock_ramp_voltage(current_v, target_v, ramp_rate)
            st.session_state.caen_channels[i]['voltage_mon'] = new_v
            st.session_state.caen_channels[i]['current_mon'] = mock_current_reading(True)
            st.session_state.caen_channels[i]['ramping'] = abs(new_v - target_v) > 10
        else:
            st.session_state.caen_channels[i]['voltage_mon'] = 0
            st.session_state.caen_channels[i]['current_mon'] = 0
            st.session_state.caen_channels[i]['ramping'] = False
    
    # Update laser temperature
    if st.session_state.laser_tec_on:
        st.session_state.laser_temp = mock_temperature(
            st.session_state.laser_temp_set,
            st.session_state.laser_temp
        )
    
    # Authenticated - show controls
    st.title("Setup & Monitor Mode")
    st.caption("⚠️ Expert mode - Manual control of all devices")
    
    col1, col2 = st.columns([6, 1])
    with col2:
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
        
        # PMT channel controls (channels 1-3)
        for i in range(1, 4):
            with st.expander(f"Channel {i} (PMT {i})", expanded=(i==1)):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    st.markdown("**Setpoints:**")
                    
                    voltage = st.number_input(
                        "Voltage (V)", 
                        min_value=0, 
                        max_value=2000, 
                        value=int(st.session_state.caen_channels[i]['voltage_set']),
                        step=50,
                        key=f'pmt_v_{i}',
                        help="Target voltage setpoint"
                    )
                    current_limit = st.number_input(
                        "Current Limit (µA)", 
                        min_value=0.0, 
                        max_value=3000.0, 
                        value=st.session_state.caen_channels[i]['current_set'],
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
                            value=int(st.session_state.caen_channels[i]['ramp_up']),
                            step=10,
                            key=f'pmt_ramp_up_{i}',
                            help="Voltage increase rate"
                        )
                    with col_ramp2:
                        ramp_down = st.number_input(
                            "Ramp Down (V/s)",
                            min_value=1,
                            max_value=500,
                            value=int(st.session_state.caen_channels[i]['ramp_down']),
                            step=10,
                            key=f'pmt_ramp_down_{i}',
                            help="Voltage decrease rate"
                        )
                    
                    # Apply configuration button
                    if st.button("Apply Config", key=f'pmt_apply_{i}', use_container_width=True):
                        st.session_state.caen_channels[i]['voltage_set'] = voltage
                        st.session_state.caen_channels[i]['current_set'] = current_limit
                        st.session_state.caen_channels[i]['ramp_up'] = ramp_up
                        st.session_state.caen_channels[i]['ramp_down'] = ramp_down
                        st.success(f"✓ [MOCK] Channel {i} configured")
                        time.sleep(0.5)
                        st.rerun()
                
                with col2:
                    st.markdown("**Monitoring:**")
                    
                    power_on = st.session_state.caen_channels[i]['power_on']
                    is_ramping = st.session_state.caen_channels[i]['ramping']
                    v_mon = st.session_state.caen_channels[i]['voltage_mon']
                    v_set = st.session_state.caen_channels[i]['voltage_set']
                    i_mon = st.session_state.caen_channels[i]['current_mon']
                    
                    if power_on:
                        if is_ramping:
                            status_text = f"{status_dot('yellow')} Ramping"
                        else:
                            status_text = f"{status_dot('green')} On"
                    else:
                        status_text = f"{status_dot('grey')} Off"
                    
                    st.markdown(status_text, unsafe_allow_html=True)
                    
                    col_v, col_i = st.columns(2)
                    with col_v:
                        st.metric("Voltage (V)", f"{v_mon:.1f}")
                        st.caption(f"Set: {v_set:.0f}V")
                    with col_i:
                        st.metric("Current (µA)", f"{i_mon:.2f}")
                        st.caption(f"Limit: {st.session_state.caen_channels[i]['current_set']:.0f}µA")
                    
                    # Overcurrent warning
                    if i_mon > st.session_state.caen_channels[i]['current_set'] * 0.9:
                        st.warning("⚠️ Approaching current limit!")
                
                with col3:
                    st.markdown("**Control:**")
                    st.write(" ")
                    
                    if not power_on:
                        if st.button(f"Turn ON", key=f'pmt_on_{i}', use_container_width=True):
                            st.session_state.caen_channels[i]['power_on'] = True
                            st.session_state.caen_channels[i]['ramping'] = True
                            st.session_state.device_enabled['pmt_hv'] = True
                            st.rerun()
                    else:
                        if st.button(f"Turn OFF", key=f'pmt_off_{i}', use_container_width=True):
                            st.session_state.caen_channels[i]['power_on'] = False
                            st.session_state.caen_channels[i]['ramping'] = False
                            st.session_state.device_enabled['pmt_hv'] = any(
                                st.session_state.caen_channels[j]['power_on'] for j in [1,2,3]
                            )
                            st.rerun()
        
        # Current monitoring graphs
        st.markdown("---")
        st.markdown("### 📊 Current Monitoring")
        
        # Display current graphs if we have data
        if len(st.session_state.caen_current_history['timestamps']) > 0:
            import pandas as pd
            
            col1, col2, col3 = st.columns(3)
            
            for idx, col in enumerate([col1, col2, col3], start=1):
                with col:
                    st.markdown(f"**Ch{idx} Current**")
                    i_df = pd.DataFrame({
                        'Time': st.session_state.caen_current_history['timestamps'],
                        'Current (µA)': st.session_state.caen_current_history[f'ch{idx}']
                    })
                    st.line_chart(i_df.set_index('Time'), height=200)
            
            # Clear button
            if st.button("🗑️ Clear History", key="clear_caen_history"):
                st.session_state.caen_current_history = {
                    'ch1': [], 'ch2': [], 'ch3': [], 'timestamps': []
                }
                st.rerun()
        else:
            st.info("📈 Turn on any channel to start monitoring current")
    
    # TAB 2: SiPM Supply
    with tabs[1]:
        st.subheader("IPS-2303S SiPM Power Supply")
        
        # Mock voltage/current values
        if st.session_state.sipm_output_on:
            ch1_v = random.uniform(4.98, 5.02)
            ch1_i = random.uniform(0.98, 1.02)
            ch2_v = random.uniform(4.97, 5.03)
            ch2_i = random.uniform(0.97, 1.03)
            
            # Collect history
            now = datetime.now()
            max_points = 100
            
            st.session_state.sipm_voltage_history['ch1'].append(ch1_v)
            st.session_state.sipm_voltage_history['ch2'].append(ch2_v)
            st.session_state.sipm_voltage_history['timestamps'].append(now)
            
            st.session_state.sipm_current_history['ch1'].append(ch1_i * 1000)  # mA
            st.session_state.sipm_current_history['ch2'].append(ch2_i * 1000)
            st.session_state.sipm_current_history['timestamps'].append(now)
            
            # Trim
            if len(st.session_state.sipm_voltage_history['timestamps']) > max_points:
                for history in [st.session_state.sipm_voltage_history, st.session_state.sipm_current_history]:
                    history['ch1'] = history['ch1'][-max_points:]
                    history['ch2'] = history['ch2'][-max_points:]
                    history['timestamps'] = history['timestamps'][-max_points:]
        else:
            ch1_v = ch1_i = ch2_v = ch2_i = 0.0
        
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            st.markdown("**Channel 1:**")
            st.text("Set Voltage: 5.00 V")
            st.text("Set Current: 1.00 A")
            st.metric("Measured V", f"{ch1_v:.3f} V")
            st.metric("Measured I", f"{ch1_i*1000:.2f} mA")
        
        with col2:
            st.markdown("**Channel 2:**")
            st.text("Set Voltage: 5.00 V")
            st.text("Set Current: 1.00 A")
            st.metric("Measured V", f"{ch2_v:.3f} V")
            st.metric("Measured I", f"{ch2_i*1000:.2f} mA")
        
        with col3:
            st.markdown("**Output Control:**")
            st.write(" ")
            
            if st.session_state.sipm_output_on:
                st.markdown(f"{status_dot('green')} Output ON", unsafe_allow_html=True)
            else:
                st.markdown(f"{status_dot('grey')} Output OFF", unsafe_allow_html=True)
            
            st.write(" ")
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Turn ON", key="sipm_enable", use_container_width=True, 
                           disabled=st.session_state.sipm_output_on):
                    st.session_state.sipm_output_on = True
                    st.session_state.device_enabled['sipm'] = True
                    st.success("✓ [MOCK] Output enabled")
                    time.sleep(0.5)
                    st.rerun()
            
            with col_b:
                if st.button("Turn OFF", key="sipm_disable", use_container_width=True,
                           disabled=not st.session_state.sipm_output_on):
                    st.session_state.sipm_output_on = False
                    st.session_state.device_enabled['sipm'] = False
                    st.info("✓ [MOCK] Output disabled")
                    time.sleep(0.5)
                    st.rerun()
        
        st.markdown("---")
        st.markdown("### 📊 Real-time Monitoring")
        
        if len(st.session_state.sipm_voltage_history['timestamps']) > 0:
            # Voltage graphs
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
            
            # Current graphs
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
            
            if st.button("🗑️ Clear History", key="clear_sipm_history"):
                st.session_state.sipm_voltage_history = {'ch1': [], 'ch2': [], 'timestamps': []}
                st.session_state.sipm_current_history = {'ch1': [], 'ch2': [], 'timestamps': []}
                st.rerun()
        else:
            st.info("📈 Turn output ON to start collecting data for graphs")
    
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
                    st.success("[MOCK] Output enabled")
                    st.rerun()
            with col_b:
                if st.button("Disable Output", key="sig_disable", use_container_width=True):
                    st.session_state.device_enabled['siggen'] = False
                    st.info("[MOCK] Output disabled")
                    st.rerun()
        
        if st.button("Apply Configuration", key="sig_apply", use_container_width=True):
            st.success("[MOCK] Signal generator configured")
    
    # TAB 4: Laser Control
    with tabs[3]:
        st.subheader("Tama Electric LSB-200 Picosecond Laser Driver")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Temperature Controller (TEC):**")
            
            tec_setpoint = st.number_input("Temperature Setpoint (°C)", 
                                          min_value=15.0, 
                                          max_value=30.0, 
                                          value=st.session_state.laser_temp_set, 
                                          step=0.1,
                                          key="tec_temp")
            
            if tec_setpoint != st.session_state.laser_temp_set:
                st.session_state.laser_temp_set = tec_setpoint
            
            # Update board temp (simulated as warmer than ambient/LD)
            if st.session_state.laser_tec_on or st.session_state.laser_ld_on:
                # Board warms up when devices on
                target_board = 30.0 + (3.0 if st.session_state.laser_ld_on else 0)
                st.session_state.laser_board_temp = mock_temperature(
                    target_board, st.session_state.laser_board_temp
                )
            else:
                # Cool down to ambient
                st.session_state.laser_board_temp = mock_temperature(
                    22.0, st.session_state.laser_board_temp
                )
            
            col_temp1, col_temp2 = st.columns(2)
            with col_temp1:
                if st.session_state.laser_tec_on:
                    st.metric("LD Temp", f"{st.session_state.laser_temp:.1f} °C")
                    st.markdown(f"{status_dot('green')} TEC ON", unsafe_allow_html=True)
                else:
                    st.metric("LD Temp", "22.0 °C")
                    st.markdown(f"{status_dot('grey')} TEC OFF", unsafe_allow_html=True)
            
            with col_temp2:
                st.metric("Board Temp", f"{st.session_state.laser_board_temp:.1f} °C")
                if st.session_state.laser_board_temp > 35:
                    st.caption("⚠️ High")
                elif st.session_state.laser_board_temp > 30:
                    st.caption("Normal")
                else:
                    st.caption("Cool")
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("TEC ON", key="tec_on", use_container_width=True):
                    st.session_state.laser_tec_on = True
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
            
            trigger_mode = st.selectbox("Trigger Mode:", ["EXT", "PG1", "PG2"], key="laser_trig_mode")
            
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
            
            stage_min = 240
            stage_max = 1074
            stage_range = stage_max - stage_min
            stage_progress = (st.session_state.linear_stage_pos - stage_min) / stage_range
            
            st.progress(stage_progress)
            st.caption(f"Position: {st.session_state.linear_stage_pos} mm")
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("📍 PMT1 (1074mm)", key="stage_pmt1", use_container_width=True):
                    st.session_state.linear_stage_pos = 1074
                    st.session_state.robot_position = 'pmt1'
                    st.info("[MOCK] Moving to PMT1...")
                    st.rerun()
            with col_b:
                if st.button("📍 PMT2 (240mm)", key="stage_pmt2", use_container_width=True):
                    st.session_state.linear_stage_pos = 240
                    st.session_state.robot_position = 'pmt2'
                    st.info("[MOCK] Moving to PMT2...")
                    st.rerun()
            
            new_pos = st.slider("Manual Position (mm)", 
                               min_value=stage_min, 
                               max_value=stage_max, 
                               value=st.session_state.linear_stage_pos,
                               key="stage_manual")
            if st.button("Move to Position", key="stage_move"):
                st.session_state.linear_stage_pos = new_pos
                st.info(f"[MOCK] Moving to {new_pos} mm...")
                st.rerun()
        
        with col2:
            st.markdown("**xArm Robot:**")
            
            st.markdown(f"""
            **Current Position:**
            - Status: {st.session_state.robot_position}
            - Linear Stage: {st.session_state.linear_stage_pos} mm
            """)
            
            st.markdown("**Quick Positions:**")
            
            if st.button("🏠 Initial (Home)", key="robot_home", use_container_width=True):
                st.session_state.robot_position = 'home'
                st.info("[MOCK] Moving to Home...")
                st.rerun()
            
            if st.button("🔄 Intermediate", key="robot_inter", use_container_width=True):
                st.session_state.robot_position = 'intermediate'
                st.info("[MOCK] Moving to Intermediate...")
                st.rerun()
            
            if st.button("📍 PMT Top", key="robot_top", use_container_width=True):
                st.session_state.robot_position = 'pmt_top'
                st.info("[MOCK] Moving to PMT Top...")
                st.rerun()
        
        st.markdown("---")
        
        robot_status_text = {
            'home': f"{status_dot('green')} At Initial Position",
            'intermediate': f"{status_dot('yellow')} At Intermediate",
            'pmt_top': f"{status_dot('yellow')} At PMT Top",
            'pmt1': f"{status_dot('yellow')} At PMT1",
            'pmt2': f"{status_dot('yellow')} At PMT2"
        }
        st.markdown(f"**Robot Status:** {robot_status_text.get(st.session_state.robot_position, 'Unknown')}", 
                   unsafe_allow_html=True)
    
    # TAB 6: DAQ Control
    with tabs[5]:
        st.subheader("Manual Data Acquisition")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Acquisition Settings:**")
            
            acq_duration = st.number_input("Duration (seconds)", min_value=1, max_value=3600, value=5, step=1)
            
            available_channels = {
                0: "Ch0 (Trigger)",
                1: "Ch1 (SiPM)",
                2: "Ch2 (PMT1)",
                3: "Ch3 (PMT2)",
                4: "Ch4 (PMT3/Monitor)",
            }
            
            channels = st.multiselect(
                "Channels to Record",
                options=list(available_channels.keys()),
                default=[2, 3, 4],
                format_func=lambda x: available_channels[x]
            )
            
            record_length = st.number_input("Record Length (samples)", min_value=128, max_value=8192, value=1024, step=128)
        
        with col2:
            st.markdown("**Trigger Settings:**")
            
            trigger_channel = st.selectbox("Trigger Channel", options=list(available_channels.keys()), index=4, 
                                          format_func=lambda x: available_channels[x])
            
            trigger_threshold = st.number_input("Trigger Threshold (ADC counts)", min_value=1, max_value=4095, value=1, step=1)
            
            trigger_mode = st.selectbox("Trigger Mode", options=["ACQUISITION_ONLY", "ACQUISITION_AND_TRGOUT", "DISABLED"])
        
        st.markdown("---")
        st.markdown("**Output Settings:**")
        
        output_dir = st.text_input("Output Directory", value="../WaveDumpSaves/manual_acquisition")
        file_prefix = st.text_input("File Prefix", value="manual")
        
        col_a, col_b = st.columns([2, 1])
        
        with col_a:
            if st.button("▶ Start Acquisition", type="primary", use_container_width=True):
                with st.spinner(f"[MOCK] Acquiring data for {acq_duration}s..."):
                    time.sleep(2)  # Simulate acquisition
                    st.success(f"✓ [MOCK] Acquisition complete! Files saved to: {output_dir}")
                    st.text(f"Channels recorded: {', '.join(map(str, channels))}")

else:
    # ========================================================================
    # RUN SEQUENCE MODE (Default)
    # ========================================================================
    
    # Auto-refresh every 2 seconds in Run Sequence mode
    count = st_autorefresh(
        interval=2000,
        debounce=True,
        key="run_autorefresh"
    )
    
    st.title("Run Sequence Mode")
    st.caption("Automated measurement sequences with coordinated device control")
    
    # PMT Serial Number Input
    st.subheader("PMT Configuration")
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        pmt1_serial = st.text_input("PMT1 Serial Number:", 
                                   value=st.session_state.pmt_serial_number["pmt1"],
                                   placeholder="e.g., ZE1234")
        st.session_state.pmt_serial_number["pmt1"] = pmt1_serial
    
    with col2:
        pmt2_serial = st.text_input("PMT2 Serial Number:", 
                                   value=st.session_state.pmt_serial_number["pmt2"],
                                   placeholder="e.g., ZE5678")
        st.session_state.pmt_serial_number["pmt2"] = pmt2_serial
    
    with col3:
        st.write(" ")
        if pmt1_serial and pmt2_serial:
            st.info(f"📁 PMT1: `/data/runs/{pmt1_serial}/` | PMT2: `/data/runs/{pmt2_serial}/`")
        else:
            st.warning("⚠️ Please enter PMT serial numbers before starting measurements")
    
    st.markdown("---")
    
    # Device controls
    st.subheader("System Control")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button(f"{'✓' if st.session_state.device_enabled['pmt_hv'] else '○'} PMT HV", use_container_width=True):
            st.session_state.device_enabled['pmt_hv'] = not st.session_state.device_enabled['pmt_hv']
            for i in [1,2,3]:
                st.session_state.caen_channels[i]['power_on'] = st.session_state.device_enabled['pmt_hv']
            st.rerun()
    
    with col2:
        if st.button(f"{'✓' if st.session_state.device_enabled['sipm'] else '○'} SiPM", use_container_width=True):
            st.session_state.device_enabled['sipm'] = not st.session_state.device_enabled['sipm']
            st.session_state.sipm_output_on = st.session_state.device_enabled['sipm']
            st.rerun()
    
    with col3:
        if st.button(f"{'✓' if st.session_state.device_enabled['siggen'] else '○'} Sig Gen", use_container_width=True):
            st.session_state.device_enabled['siggen'] = not st.session_state.device_enabled['siggen']
            st.rerun()
    
    with col4:
        if st.button(f"{'✓' if st.session_state.device_enabled['laser'] else '○'} Laser", use_container_width=True):
            st.session_state.device_enabled['laser'] = not st.session_state.device_enabled['laser']
            st.session_state.laser_tec_on = st.session_state.device_enabled['laser']
            st.session_state.laser_ld_on = st.session_state.device_enabled['laser']
            st.rerun()
    
    # Real-time monitoring section
    st.markdown("---")
    st.subheader("📊 Real-time Monitoring")
    
    # Collect history data if devices are on
    any_caen_on = any(st.session_state.caen_channels[i]['power_on'] for i in [1,2,3])
    
    if any_caen_on or st.session_state.sipm_output_on or st.session_state.laser_tec_on:
        now = datetime.now()
        max_points = 100
        
        # CAEN current history
        if any_caen_on:
            st.session_state.caen_current_history['timestamps'].append(now)
            for i in [1, 2, 3]:
                st.session_state.caen_current_history[f'ch{i}'].append(
                    st.session_state.caen_channels[i]['current_mon']
                )
            
            # Trim
            if len(st.session_state.caen_current_history['timestamps']) > max_points:
                for key in st.session_state.caen_current_history:
                    st.session_state.caen_current_history[key] = st.session_state.caen_current_history[key][-max_points:]
        
        # SiPM current history
        if st.session_state.sipm_output_on:
            st.session_state.sipm_current_history['timestamps'].append(now)
            st.session_state.sipm_current_history['ch1'].append(random.uniform(0.98, 1.02))
            st.session_state.sipm_current_history['ch2'].append(random.uniform(0.98, 1.02))
            
            # Trim
            if len(st.session_state.sipm_current_history['timestamps']) > max_points:
                for key in st.session_state.sipm_current_history:
                    st.session_state.sipm_current_history[key] = st.session_state.sipm_current_history[key][-max_points:]
        
        # Laser temperature history
        if st.session_state.laser_tec_on or st.session_state.laser_ld_on:
            st.session_state.laser_temp_history['timestamps'].append(now)
            st.session_state.laser_temp_history['ld'].append(st.session_state.laser_temp)
            st.session_state.laser_temp_history['board'].append(st.session_state.laser_board_temp)
            
            # Trim
            if len(st.session_state.laser_temp_history['timestamps']) > max_points:
                for key in st.session_state.laser_temp_history:
                    st.session_state.laser_temp_history[key] = st.session_state.laser_temp_history[key][-max_points:]
    
    # Display graphs
    st.markdown("**CAEN HV Current (3 PMT Channels)**")
    col1, col2, col3 = st.columns(3)
    
    if len(st.session_state.caen_current_history['timestamps']) > 0:
        import pandas as pd
        
        with col1:
            st.caption("Ch1 (PMT1)")
            df1 = pd.DataFrame({
                'Time': st.session_state.caen_current_history['timestamps'],
                'Current (µA)': st.session_state.caen_current_history['ch1']
            })
            st.line_chart(df1.set_index('Time'), height=200)
        
        with col2:
            st.caption("Ch2 (PMT2)")
            df2 = pd.DataFrame({
                'Time': st.session_state.caen_current_history['timestamps'],
                'Current (µA)': st.session_state.caen_current_history['ch2']
            })
            st.line_chart(df2.set_index('Time'), height=200)
        
        with col3:
            st.caption("Ch3 (PMT3/Monitor)")
            df3 = pd.DataFrame({
                'Time': st.session_state.caen_current_history['timestamps'],
                'Current (µA)': st.session_state.caen_current_history['ch3']
            })
            st.line_chart(df3.set_index('Time'), height=200)
    else:
        with col1:
            st.info("Enable PMT HV")
        with col2:
            st.write("")
        with col3:
            st.write("")
    
    st.markdown("**SiPM Current (2 Channels)**")
    col4, col5, col6 = st.columns(3)
    
    if len(st.session_state.sipm_current_history['timestamps']) > 0:
        import pandas as pd
        
        with col4:
            st.caption("SiPM Ch1")
            df_s1 = pd.DataFrame({
                'Time': st.session_state.sipm_current_history['timestamps'],
                'Current (A)': st.session_state.sipm_current_history['ch1']
            })
            st.line_chart(df_s1.set_index('Time'), height=200)
        
        with col5:
            st.caption("SiPM Ch2")
            df_s2 = pd.DataFrame({
                'Time': st.session_state.sipm_current_history['timestamps'],
                'Current (A)': st.session_state.sipm_current_history['ch2']
            })
            st.line_chart(df_s2.set_index('Time'), height=200)
        
        with col6:
            st.write("")  # Empty column for alignment
    else:
        with col4:
            st.info("Enable SiPM")
        with col5:
            st.write("")
        with col6:
            st.write("")
    
    st.markdown("**Laser Temperature**")
    col7, col8, col9 = st.columns(3)
    
    if len(st.session_state.laser_temp_history['timestamps']) > 0:
        with col7:
            st.metric("LD Temp", f"{st.session_state.laser_temp:.1f}°C")
        with col8:
            st.metric("Board Temp", f"{st.session_state.laser_board_temp:.1f}°C")
            if st.session_state.laser_board_temp > 35:
                st.caption("⚠️ High")
        with col9:
            st.write("")  # Empty for alignment
    else:
        with col7:
            st.info("Enable Laser")
        with col8:
            st.write("")
        with col9:
            st.write("")
    
    st.markdown("---")
    
    # Run Selection
    st.subheader("Select Measurement Sequence")
    
    sequence_type = st.selectbox(
        "Sequence Type:",
        ["Dark Current Check (5 min)", "Single PMT Test (10 min)", "Full PMT Scan (2 hours)"]
    )
    
    if "Dark Current" in sequence_type:
        st.info("""
        **Dark Current Check:**
        1. Powers on all PMTs
        2. Waits for stabilization (5 min)
        3. Records baseline without signal
        4. Checks for excessive dark current
        """)
    elif "Full PMT Scan" in sequence_type:
        st.info("""
        **Full PMT Scan:**
        - Dark current check (5 min)
        - Scan PMT1 and PMT2 at multiple angles
        - Estimated time: 2 hours
        """)
    
    st.markdown("---")
    
    # Run Control
    all_systems_ready = (
        any(st.session_state.caen_channels[i]['power_on'] for i in [1,2,3]) and
        st.session_state.laser_ld_on and st.session_state.laser_tec_on and
        st.session_state.robot_position == 'home' and
        st.session_state.device_enabled['sipm'] and
        bool(pmt1_serial) and bool(pmt2_serial)
    )
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if not st.session_state.run_active:
            if st.button("▶ Start Run", use_container_width=True, type="primary", disabled=not all_systems_ready):
                st.session_state.run_active = True
                st.session_state.run_progress = 0
                st.success("[MOCK] Run started!")
                st.rerun()
    
    with col2:
        if st.session_state.run_active:
            if st.button("⏸ Pause", use_container_width=True):
                st.warning("[MOCK] Run paused")
    
    with col3:
        if st.session_state.run_active:
            if st.button("⏹ Stop", use_container_width=True):
                st.session_state.run_active = False
                st.session_state.run_progress = 0
                st.info("[MOCK] Run stopped")
                st.rerun()
    
    if not all_systems_ready:
        reasons = []
        if not any(st.session_state.caen_channels[i]['power_on'] for i in [1,2,3]):
            reasons.append("Enable PMT HV")
        if not (st.session_state.laser_ld_on and st.session_state.laser_tec_on):
            reasons.append("Enable Laser")
        if not st.session_state.device_enabled['sipm']:
            reasons.append("Enable SiPM")
        if not (pmt1_serial and pmt2_serial):
            reasons.append("Enter PMT serial numbers")
        
        st.warning(f"⚠️ System not ready: {', '.join(reasons)}")
    
    # Progress Display
    if st.session_state.run_active:
        st.markdown("---")
        st.subheader("Run Progress")
        
        # Simulate progress
        if st.session_state.run_progress < 100:
            st.session_state.run_progress += 2
            time.sleep(0.1)
            st.rerun()
        
        progress = st.session_state.run_progress / 100
        st.progress(progress)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Progress", f"{st.session_state.run_progress}%")
        with col2:
            st.metric("Current Position", "[MOCK] PMT 2, Z=30°")
        with col3:
            st.metric("Events Recorded", f"{random.randint(15000, 16000)}")
        
        if pmt1_serial and pmt2_serial:
            st.caption(f"📁 PMT1: `/data/runs/{pmt1_serial}/` | PMT2: `/data/runs/{pmt2_serial}/`")

# Footer
st.markdown("---")
st.caption("HyperK PMT DAQ Control System - MOCK VERSION | University of Melbourne | 2025")