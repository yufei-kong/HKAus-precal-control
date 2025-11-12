"""
Minimal xArm + DAQ Driver - Just what we need for the GUI
No overengineering, just the bare essentials
"""

import numpy as np
import time
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable


class HyperKController:
    """Single controller for both robot and DAQ"""
    
    def __init__(self, arm, wavedump_path: str, config_template: str):
        self.arm = arm
        self.wavedump_path = wavedump_path
        self.config_template = config_template
        self.cwd = os.getcwd()
        
        # Robot positions
        self.HOME_TRUE = [0, 0, 0, 0, 0, -135]
        self.HOME = [0, -116.5, 5, 0, 0, -135]
        self.PMT_TOP = [-0.0, -116.812436, -25.177883, 0.0, 51.990269, -135.0]
        
        # Pre-computed joint angles for d=170
        self.joint_angles = {
            0: [-0.0, -116.812436, -25.177883, 0.0, 51.990269, -135.0],
            10: [-0.0, -116.526562, -42.036077, 0.0, 78.562588, -135.0],
            20: [0.0, -107.540290, -64.342738, 0.0, 101.882979, -135.0],
            30: [-0.0, -88.178555, -99.281852, -0.000079, 130.695388, -135.0],
            40: [-0.0, -87.153400, -64.601500, 0.0, -70.653100, 45.0],
            50: [0.0, -80.245856, -84.987522, -0.0, -43.007671, 45.0]
        }
        
        # Buffer positions for robot config changes
        self.buffer_positions = [
            [-0.0, -100.178555, -99.281852, -0.000079, 130.695388, -135.0],
            [-0.0, -100.178555, -64.601500, 0.0, -70.653100, 45.0],
            [-0.0, -87.46, -55.908, 0.0, -87.638, 45.0]
        ]
    
    # =========================================================================
    # DAQ Configuration
    # =========================================================================
    
    def configure_daq(self, run_duration: int, channels: list):
        """
        Configure WaveDump.
        
        Args:
            run_duration: Acquisition time in seconds
            channels: List of channels to enable (e.g. [0, 1, 2, 4])
        """
        with open(self.config_template, 'r') as f:
            lines = f.readlines()
        
        # Set run duration (line 32 in your template)
        lines[32] = f"RUN_DURATION  {run_duration}\n"
        
        # Enable/disable channels (lines 149, 155, 161, 167, 173, 179, 185, 191)
        # Adjust these line numbers based on your actual config!
        channel_lines = {
            0: 143,  # Trigger channel
            1: 149,  # SiPM
            2: 155,  # PMT1
            3: 161,  # PMT2
            4: 167,  # PMT3/Monitor
            5: 173,
            6: 179,
            7: 185
        }
        
        for ch, line_idx in channel_lines.items():
            if ch in channels:
                lines[line_idx] = "ENABLE_INPUT           YES\n"
            else:
                lines[line_idx] = "ENABLE_INPUT           NO\n"
        
        # Write config
        config_path = Path(self.cwd) / "WaveDumpConfig.txt"
        with open(config_path, 'w') as f:
            f.writelines(lines)
    
    def acquire_data(self, timeout: int = 70):
        """
        Run WaveDump to acquire data.
        
        Args:
            timeout: Max time to wait (seconds)
            
        Returns:
            True if successful
        """
        config_path = Path(self.cwd) / "WaveDumpConfig.txt"
        
        try:
            subprocess.run(
                [self.wavedump_path, str(config_path)],
                cwd=self.cwd,
                timeout=timeout,
                check=True
            )
            time.sleep(1)  # Let files settle
            return True
        except Exception as e:
            print(f"Acquisition error: {e}")
            return False
    
    def get_waveform_data(self, channel: int):
        """
        Read waveform data from wave file for display.
        
        Args:
            channel: Channel number
            
        Returns:
            (time_array, adc_array) or (None, None) if file doesn't exist
        """
        wave_file = Path(self.cwd) / f"wave{channel}.txt"
        
        if not wave_file.exists():
            return None, None
        
        try:
            # Read wave file (format: time, ADC)
            data = np.loadtxt(wave_file)
            if len(data.shape) == 2:
                return data[:, 0], data[:, 1]
            else:
                return None, None
        except:
            return None, None
    
    def organize_files(self, save_dir: str, prefix: str, channels: list):
        """
        Move wave files to organized directory.
        
        Args:
            save_dir: Target directory
            prefix: Filename prefix (e.g. "dark_current" or "theta10_phi90")
            channels: Channels to organize
        """
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        
        for ch in channels:
            wave_file = Path(self.cwd) / f"wave{ch}.txt"
            if wave_file.exists():
                dest = save_path / f"wave{ch}_{prefix}.txt"
                shutil.move(str(wave_file), str(dest))
    
    # =========================================================================
    # Robot Movement
    # =========================================================================
    
    def move_linear_stage(self, position: int):
        """
        Move linear stage to position.
        
        Args:
            position: Position in mm (240-1074)
        """
        code = self.arm.set_linear_track_pos(position, wait=True)
        print(f"Linear stage at {position}mm, code={code}")
        return code
    
    def move_to_position(self, joint_angles: list, speed: int = 10):
        """Move robot to specific joint angles"""
        self.arm.set_servo_angle(angle=joint_angles, speed=speed, wait=True)
    
    def move_to_initial(self):
        """Move to initial position"""
        self.move_to_position(self.HOME_TRUE)
    
    def move_to_intermediate(self):
        """Move to intermediate position"""
        self.move_to_position(self.HOME)
    
    def move_to_pmt_top(self):
        """Move to PMT top"""
        self.move_to_position(self.PMT_TOP)
    
    def _rotate_base(self, angles: list, azimuth: float) -> list:
        """Rotate base to azimuth"""
        rotated = angles.copy()
        rotated[0] = azimuth % 360
        return rotated
    
    def _move_through_buffers(self, azimuth: float, reverse: bool = False):
        """Move through buffer positions"""
        positions = reversed(self.buffer_positions) if reverse else self.buffer_positions
        for buffer in positions:
            rotated = self._rotate_base(buffer, azimuth)
            self.move_to_position(rotated)
    
    def move_to_scan_point(self, zenith: float, azimuth: float):
        """
        Move to scan point.
        
        Args:
            zenith: Zenith angle (degrees)
            azimuth: Azimuthal angle (degrees)
        """
        if zenith not in self.joint_angles:
            raise ValueError(f"No joint angles for zenith={zenith}")
        
        # Handle buffer positions for large zenith angles
        if zenith >= 40:
            self._move_through_buffers(azimuth, reverse=(azimuth % 180 != 0))
        
        # Move to target
        target = self._rotate_base(self.joint_angles[zenith], azimuth)
        self.move_to_position(target)
        
        # Stabilization
        time.sleep(3)
    
    # =========================================================================
    # High-Level Scan Functions
    # =========================================================================
    
    def dark_current_check(self, pmt1_serial: str, pmt2_serial: str, 
                          duration: int = 300,
                          progress_callback: Optional[Callable] = None):
        """
        Dark current check for all three PMTs.
        
        Args:
            pmt1_serial: PMT1 serial number
            pmt2_serial: PMT2 serial number
            duration: Acquisition time (seconds)
            progress_callback: Optional callback(progress_pct, message)
            
        Returns:
            Dict with waveform data for each channel
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Move robot to safe position
        self.move_to_intermediate()
        
        if progress_callback:
            progress_callback(10, "Configuring DAQ...")
        
        # Configure for channels 2, 3, 4 (PMT1, PMT2, PMT3)
        self.configure_daq(run_duration=duration, channels=[2, 3, 4])
        
        if progress_callback:
            progress_callback(20, "Acquiring dark current...")
        
        # Acquire
        self.acquire_data(timeout=duration + 10)
        
        if progress_callback:
            progress_callback(80, "Reading waveforms...")
        
        # Get waveform data for GUI display
        waveforms = {}
        for ch in [2, 3, 4]:
            time_data, adc_data = self.get_waveform_data(ch)
            if time_data is not None:
                waveforms[ch] = {'time': time_data, 'adc': adc_data}
        
        if progress_callback:
            progress_callback(90, "Organizing files...")
        
        # Organize files
        save_dir = f"../WaveDumpSaves/dark_current_{timestamp}"
        self.organize_files(save_dir, "dark_current", [0, 1, 2, 3, 4])
        
        if progress_callback:
            progress_callback(100, "Complete!")
        
        return waveforms
    
    def full_pmt_scan(self, pmt1_serial: str, pmt2_serial: str,
                     zeniths: list = [0, 10, 20, 30, 40, 50],
                     azimuths: list = [0, 90, 180, 270],
                     daq_runtime: int = 5,  # 5 sec for testing, 600 for real
                     progress_callback: Optional[Callable] = None):
        """
        Full PMT scan - both PMTs at all angles.
        
        Args:
            pmt1_serial: PMT1 serial number
            pmt2_serial: PMT2 serial number
            zeniths: Zenith angles to scan
            azimuths: Azimuthal angles to scan
            daq_runtime: Acquisition time per point (seconds)
            progress_callback: Optional callback(progress_pct, message, position)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        total_points = len(zeniths) * len(azimuths) * 2  # x2 for both PMTs
        current_point = 0
        
        visited_zero = False
        
        # ===== Scan PMT1 =====
        if progress_callback:
            progress_callback(0, "Moving to PMT1...", "")
        
        # Move linear stage to PMT1 (1074mm)
        self.move_linear_stage(1074)
        
        # Configure for PMT1 (channels 0, 1, 2, 4)
        self.configure_daq(run_duration=daq_runtime, channels=[0, 1, 2, 4])
        
        # Move to home
        self.move_to_intermediate()
        
        for i, azimuth in enumerate(azimuths):
            # Alternate zenith direction for efficiency
            zen_list = zeniths if i % 2 == 0 else zeniths[::-1]
            
            for zenith in zen_list:
                # Skip duplicate zenith=0
                if zenith == 0:
                    if visited_zero:
                        current_point += 1
                        continue
                    visited_zero = True
                
                # Move to point
                position_name = f"θ={zenith}°, φ={azimuth}°"
                if progress_callback:
                    progress = int((current_point / total_points) * 100)
                    progress_callback(progress, f"PMT1 - {position_name}", position_name)
                
                self.move_to_scan_point(zenith, azimuth)
                
                # Acquire
                self.acquire_data(timeout=daq_runtime + 10)
                
                # Organize files
                save_dir = f"../WaveDumpSaves/scan_{timestamp}/{pmt1_serial}"
                self.organize_files(save_dir, f"theta{zenith}_phi{azimuth}", [0, 1, 2, 4])
                
                current_point += 1
        
        # Return to home
        self.move_to_intermediate()
        
        # Reset for PMT2
        visited_zero = False
        
        # ===== Scan PMT2 =====
        if progress_callback:
            progress_callback(50, "Moving to PMT2...", "")
        
        # Move linear stage to PMT2 (240mm)
        self.move_linear_stage(240)
        
        # Configure for PMT2 (channels 0, 1, 3, 4)
        self.configure_daq(run_duration=daq_runtime, channels=[0, 1, 3, 4])
        
        # Move to home
        self.move_to_intermediate()
        
        for i, azimuth in enumerate(azimuths):
            zen_list = zeniths if i % 2 == 0 else zeniths[::-1]
            
            for zenith in zen_list:
                # Skip duplicate zenith=0
                if zenith == 0:
                    if visited_zero:
                        current_point += 1
                        continue
                    visited_zero = True
                
                # Move to point
                position_name = f"θ={zenith}°, φ={azimuth}°"
                if progress_callback:
                    progress = int((current_point / total_points) * 100)
                    progress_callback(progress, f"PMT2 - {position_name}", position_name)
                
                self.move_to_scan_point(zenith, azimuth)
                
                # Acquire
                self.acquire_data(timeout=daq_runtime + 10)
                
                # Organize files
                save_dir = f"../WaveDumpSaves/scan_{timestamp}/{pmt2_serial}"
                self.organize_files(save_dir, f"theta{zenith}_phi{azimuth}", [0, 1, 3, 4])
                
                current_point += 1
        
        # Return to home
        self.move_to_intermediate()
        self.move_to_initial()
        
        if progress_callback:
            progress_callback(100, "Scan complete!", "Home")
    
    def get_current_position(self):
        """Get current robot position"""
        return self.arm.get_servo_angle()[1]
    
    def emergency_stop(self):
        """Emergency stop"""
        self.arm.emergency_stop()
