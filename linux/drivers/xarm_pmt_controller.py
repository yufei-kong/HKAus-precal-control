"""
xArm Robot Controller for HyperK PMT Scanning
Focused on robot positioning and movement - delegates DAQ to digitizer driver

This is a cleaner separation:
- Robot control: This file
- DAQ operations: caen_digitizer_wavedump.py
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List
from loguru import logger
import sys
import os

# Add parent directory to path so we can import drivers
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

# Import digitizer driver
from drivers.caen_digitizer_wavedump import CAENDigitizerWaveDump


class XArmPMTController:
    """
    Robot controller for PMT angular scanning.
    
    Manages:
    - xArm robot positioning
    - Linear stage movement
    - Predefined scan positions
    - Movement sequences
    """
    
    def __init__(self, arm, digitizer: Optional[CAENDigitizerWaveDump] = None):
        """
        Initialize robot controller.
        
        Args:
            arm: XArmAPI instance
            digitizer: Optional CAENDigitizerWaveDump instance
        """
        self.arm = arm
        self.digitizer = digitizer
        
        # Robot positions (in degrees)
        self.HOME_TRUE = [0, 0, 0, 0, 0, -135]  # True home (vertical)
        self.HOME = [0, -116.5, 5, 0, 0, -135]  # Safe intermediate position
        self.PMT_TOP = [-0.0, -116.812436, -25.177883, 0.0, 51.990269, -135.0]
        
        # Pre-computed joint angles for each zenith angle (d=170mm from PMT)
        self.joint_angles = {
            0:  [-0.0, -116.812436, -25.177883, 0.0, 51.990269, -135.0],
            10: [-0.0, -116.526562, -42.036077, 0.0, 78.562588, -135.0],
            20: [0.0, -107.540290, -64.342738, 0.0, 101.882979, -135.0],
            30: [-0.0, -88.178555, -99.281852, -0.000079, 130.695388, -135.0],
            40: [-0.0, -87.153400, -64.601500, 0.0, -70.653100, 45.0],
            50: [0.0, -80.245856, -84.987522, -0.0, -43.007671, 45.0]
        }
        
        # Buffer positions for safe transitions (used for zenith >= 40°)
        self.buffer_positions = [
            [-0.0, -100.178555, -99.281852, -0.000079, 130.695388, -135.0],
            [-0.0, -100.178555, -64.601500, 0.0, -70.653100, 45.0],
            [-0.0, -87.46, -55.908, 0.0, -87.638, 45.0]
        ]
        
        # PMT positions on linear stage (mm)
        self.PMT_POSITIONS = {
            1: 1074,  # PMT1 at far end
            2: 240    # PMT2 at near end
        }
        
        logger.info("xArm PMT Controller initialized")
    
    # =========================================================================
    # LINEAR STAGE CONTROL
    # =========================================================================
    
    def move_linear_stage(self, position: int, wait: bool = True) -> int:
        """
        Move linear stage to position.
        
        Args:
            position: Position in mm (240-1074)
            wait: Wait for movement to complete
            
        Returns:
            Return code from xArm
        """
        if position < 240 or position > 1074:
            logger.warning(f"Linear stage position {position}mm out of range [240, 1074]")
        
        code = self.arm.set_linear_track_pos(position, wait=wait)
        logger.info(f"Linear stage -> {position}mm (code: {code})")
        
        return code
    
    def move_to_pmt(self, pmt_number: int, wait: bool = True) -> int:
        """
        Move linear stage to PMT position.
        
        Args:
            pmt_number: PMT number (1 or 2)
            wait: Wait for movement to complete
            
        Returns:
            Return code from xArm
        """
        if pmt_number not in [1, 2]:
            raise ValueError("PMT number must be 1 or 2")
        
        position = self.PMT_POSITIONS[pmt_number]
        logger.info(f"Moving to PMT{pmt_number} position ({position}mm)")
        
        return self.move_linear_stage(position, wait=wait)
    
    # =========================================================================
    # ROBOT POSITIONING
    # =========================================================================
    
    def move_to_position(self, joint_angles: List[float], speed: int = 10, wait: bool = True):
        """
        Move robot to specific joint angles.
        
        Args:
            joint_angles: List of 6 joint angles in degrees
            speed: Movement speed (degrees/s)
            wait: Wait for movement to complete
        """
        self.arm.set_servo_angle(angle=joint_angles, speed=speed, wait=wait)
        logger.debug(f"Robot moved to {joint_angles}")
    
    def move_to_initial(self):
        """Move to initial/home position (vertical)."""
        logger.info("Moving to initial position (vertical)")
        self.move_to_position(self.HOME_TRUE)
    
    def move_to_intermediate(self):
        """Move to safe intermediate position."""
        logger.info("Moving to intermediate position")
        self.move_to_position(self.HOME)
    
    def move_to_pmt_top(self):
        """Move to PMT top position (zenith=0)."""
        logger.info("Moving to PMT top position")
        self.move_to_position(self.PMT_TOP)
    
    def get_current_position(self) -> List[float]:
        """
        Get current robot joint angles.
        
        Returns:
            List of current joint angles in degrees
        """
        code, angles = self.arm.get_servo_angle()
        return angles
    
    # =========================================================================
    # SCAN POSITIONING
    # =========================================================================
    
    def _rotate_base(self, angles: List[float], azimuth: float) -> List[float]:
        """
        Rotate base joint to set azimuth angle.
        
        Args:
            angles: Base joint angles
            azimuth: Desired azimuth in degrees (0-360)
            
        Returns:
            Modified angles with new azimuth
        """
        rotated = angles.copy()
        rotated[0] = azimuth % 360
        return rotated
    
    def _move_through_buffers(self, azimuth: float, reverse: bool = False):
        """
        Move through buffer positions for safe transitions.
        
        Used when moving to/from high zenith angles (>= 35°) to avoid
        singularities and collisions.
        
        Args:
            azimuth: Target azimuth angle
            reverse: If True, move through buffers in reverse order
        """
        positions = reversed(self.buffer_positions) if reverse else self.buffer_positions
        
        for buffer in positions:
            rotated = self._rotate_base(buffer, azimuth)
            self.move_to_position(rotated)
    
    def move_to_scan_point(self, zenith: float, azimuth: float):
        """
        Move to specific (zenith, azimuth) scan point.
        
        This handles the complexity of moving through buffer positions
        for high zenith angles.
        
        Args:
            zenith: Zenith angle in degrees (0, 10, 20, 30, 40, 50)
            azimuth: Azimuthal angle in degrees (0-360)
        """
        if zenith not in self.joint_angles:
            raise ValueError(f"No joint angles defined for zenith={zenith}°")
        
        logger.info(f"Moving to scan point: θ={zenith}°, φ={azimuth}°")
        
        # Move to target position
        target_angles = self._rotate_base(self.joint_angles[zenith], azimuth)
        self.move_to_position(target_angles)
        
        # Stabilization delay (let vibrations settle)
        time.sleep(3)
        
        logger.info(f"✓ At scan point: θ={zenith}°, φ={azimuth}°")
    
    # =========================================================================
    # SAFETY
    # =========================================================================
    
    def emergency_stop(self):
        """Emergency stop - halt all robot motion immediately."""
        logger.critical("🚨 ROBOT EMERGENCY STOP")
        self.arm.emergency_stop()
    
    # =========================================================================
    # HIGH-LEVEL SCAN SEQUENCES
    # =========================================================================
    
    def dark_current_check(
        self,
        pmt1_serial: str,
        pmt2_serial: str,
        duration: int = 600,
        progress_callback: Optional[Callable] = None
    ) -> dict:
        """
        Perform dark current measurement for all three PMTs.
        
        Args:
            pmt1_serial: PMT1 serial number (for file organization)
            pmt2_serial: PMT2 serial number (for file organization)
            duration: Acquisition time in seconds
            progress_callback: Optional callback(progress_pct, message)
            
        Returns:
            Dict with waveform data and metadata
        """
        if not self.digitizer:
            raise RuntimeError("No digitizer configured")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Starting dark current check ({duration}s)")
        
        # # Move robot to safe position
        # if progress_callback:
        #     progress_callback(10, "Moving to safe position...")
        # self.move_to_intermediate()
        
        # Configure DAQ for all PMT channels
        if progress_callback:
            progress_callback(20, "Configuring digitizer...")
        
        channels = [2, 3, 4]  # PMT1, PMT2, PMT3 (monitor)
        self.digitizer.configure(
            run_duration=duration,
            channels=channels,
            trigger_channel=channels,
            trigger_threshold=5,
            channel_trigger_mode='ACQUISITION_ONLY'
        )
        
        # Acquire data
        if progress_callback:
            progress_callback(30, "Acquiring dark current data...")
        
        success = self.digitizer.acquire_with_progress(
            duration=duration,
            progress_callback=lambda pct, msg: progress_callback(
                30 + int(pct * 0.5), msg  # Scale to 30-80% range
            ) if progress_callback else None
        )
        
        if not success:
            raise RuntimeError("Dark current acquisition failed")
        
        # Retrieve waveforms
        if progress_callback:
            progress_callback(85, "Reading waveform data...")
        
        waveforms = self.digitizer.get_all_wavefiles(channels)
        
        # Organize files
        if progress_callback:
            progress_callback(90, "Organizing files...")
        
        save_dir = f"/home/hyperkaus/WaveDumpSaves/dark_current_{timestamp}"
        self.digitizer.organize_files(
            save_dir=save_dir,
            prefix="dark_current",
            channels=channels,
            include_timestamp=False
        )
        
        if progress_callback:
            progress_callback(100, "Dark current check complete!")
        
        logger.info(f"✓ Dark current check complete: {save_dir}")
        
        return {
            'status': 'success',
            'timestamp': timestamp,
            'duration': duration,
            'waveforms': waveforms,
            'save_dir': save_dir,
            'pmt1_serial': pmt1_serial,
            'pmt2_serial': pmt2_serial
        }
    
    def scan_single_pmt(
        self,
        pmt_number: int,
        serial: str,
        zeniths: List[float] = [0, 10, 20, 30, 40, 50],
        azimuths: List[float] = [0, 90, 180, 270],
        daq_runtime: int = 300,
        progress_callback: Optional[Callable] = None
    ) -> dict:
        """
        Scan a single PMT at specified angles.
        
        Args:
            pmt_number: PMT number (1 or 2)
            serial: PMT serial number for file organization
            zeniths: List of zenith angles to scan
            azimuths: List of azimuthal angles to scan
            daq_runtime: Acquisition time per point (seconds)
            progress_callback: Optional callback(progress_pct, message, position)
            
        Returns:
            Dict with scan metadata
        """
        if not self.digitizer:
            raise RuntimeError("No digitizer configured")
        
        if pmt_number not in [1, 2]:
            raise ValueError("PMT number must be 1 or 2")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Starting PMT{pmt_number} scan: {serial}")
        logger.info(f"  Zeniths: {zeniths}")
        logger.info(f"  Azimuths: {azimuths}")
        logger.info(f"  Runtime per point: {daq_runtime}s")
        
        # Determine channels based on PMT
        if pmt_number == 1:
            channels = [0, 1, 2, 4]  # Trigger, SiPM, PMT1, Monitor
        else:
            channels = [0, 1, 3, 4]  # Trigger, SiPM, PMT2, Monitor
        
        # Move to PMT position
        if progress_callback:
            progress_callback(0, f"Moving to PMT{pmt_number}...", "")
        
        self.move_to_pmt(pmt_number)
        self.move_to_intermediate()
        
        # Scan loop
        total_points = (len(zeniths[1:]) * len(azimuths))+1
        current_point = 0
        visited_zero = False
        
        Urob_change = 35  # Robot configuration change angle (degrees)

        for i, azimuth in enumerate(azimuths):
            # Alternate zenith direction for efficiency
            zen_list = zeniths if i % 2 == 0 else list(reversed(zeniths))
            
            passed_rob_change = False  # Reset flag for each azimuth
            
            for zenith in zen_list:
                # Skip duplicate zenith=0 (independent of azimuth)
                if zenith == 0:
                    if visited_zero:
                        current_point += 1
                        continue
                    visited_zero = True
                
                # Check if crossing robot configuration threshold (only once per azimuth)
                if i % 2 == 0:  # Even index: going UP (0 -> 10 -> 20 -> 30 -> 35 -> 40 -> 50)
                    if zenith >= Urob_change and not passed_rob_change:
                        passed_rob_change = True
                        logger.info(f"Crossing robot config threshold (going up) at θ={zenith}°, φ={azimuth}°")
                        # Use buffer positions (forward order)
                        for buffer in self.buffer_positions:
                            rotated_buffer = self._rotate_base(buffer, azimuth)
                            self.move_to_position(rotated_buffer)
                else:  # Odd index: going DOWN (50 -> 40 -> 35 -> 30 -> 20 -> 10 -> 0)
                    if zenith <= Urob_change and not passed_rob_change:
                        passed_rob_change = True
                        logger.info(f"Crossing robot config threshold (going down) at θ={zenith}°, φ={azimuth}°")
                        # Use buffer positions (reverse order)
                        for buffer in reversed(self.buffer_positions):
                            rotated_buffer = self._rotate_base(buffer, azimuth)
                            self.move_to_position(rotated_buffer)
                
                # Move to scan point (without automatic buffer handling)
                position_name = f"θ={zenith}°, φ={azimuth}°"
                if progress_callback:
                    progress_pct = int((current_point / total_points) * 100)
                    progress_callback(progress_pct, f"PMT{pmt_number} - {position_name}", position_name)
                
                # Move directly to target position
                target_angles = self._rotate_base(self.joint_angles[zenith], azimuth)
                self.move_to_position(target_angles)
                
                # Stabilization delay
                time.sleep(3)
                
                logger.debug(f"✓ At scan point: θ={zenith}°, φ={azimuth}°")
                
                # Configure and acquire
                self.digitizer.configure(run_duration=daq_runtime, channels=channels)
                self.digitizer.acquire()  # No timeout - augmented WaveDump handles timing
                
                # Organize files
                save_dir = f"/home/hyperkaus/WaveDumpSaves/scan_{timestamp}/{serial}"
                self.digitizer.organize_files(
                    save_dir=save_dir,
                    prefix=f"theta{zenith}_phi{azimuth}",
                    channels=channels,
                    include_timestamp=False
                )
                
                current_point += 1
        
        # Safe return to home - simple 3-step process
        logger.info("Returning to home via safe path...")
        if progress_callback:
            progress_callback(95, "Returning to home...", "Retracing")
        
        # Step 1: Move to zenith=0 (PMT_TOP) at current azimuth
        logger.info("Step 1: Moving to θ=0° at current azimuth...")
        current_angles = self.arm.get_servo_angle()[1]  # Get current position
        current_azimuth = current_angles[0]  # Current base rotation
        
        # Move to PMT_TOP position rotated to current azimuth
        pmt_top_at_current_az = self._rotate_base(self.PMT_TOP, current_azimuth)
        self.move_to_position(pmt_top_at_current_az)
        
        # Step 2: Rotate to azimuth=0 while at zenith=0
        logger.info("Step 2: Rotating to φ=0° at θ=0°...")
        self.move_to_position(self.PMT_TOP)  # PMT_TOP is already at azimuth=0
        
        # Step 3: Move to intermediate then home
        logger.info("Step 3: Moving to intermediate then home...")
        self.move_to_intermediate()
        self.move_to_initial()
        
        if progress_callback:
            progress_callback(100, "Scan complete!", "Home")
        
        logger.info(f"✓ PMT{pmt_number} scan complete")
        
        return {
            'status': 'success',
            'pmt_number': pmt_number,
            'serial': serial,
            'timestamp': timestamp,
            'total_points': total_points,
            'save_dir': save_dir
        }
    
    def full_pmt_scan(
        self,
        pmt1_serial: str,
        pmt2_serial: str,
        zeniths: List[float] = [0, 10, 20, 30, 40, 50],
        azimuths: List[float] = [0, 90, 180, 270],
        daq_runtime: int = 300,
        progress_callback: Optional[Callable] = None
    ) -> dict:
        """
        Scan both PMTs at specified angles.
        
        This is more efficient than calling scan_single_pmt twice because
        it coordinates the movements.
        
        Args:
            pmt1_serial: PMT1 serial number
            pmt2_serial: PMT2 serial number
            zeniths: List of zenith angles to scan
            azimuths: List of azimuthal angles to scan
            daq_runtime: Acquisition time per point (seconds)
            progress_callback: Optional callback(progress_pct, message, position)
            
        Returns:
            Dict with scan metadata
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Scan PMT1
        if progress_callback:
            progress_callback(0, "Starting PMT1 scan...", "")
        
        result1 = self.scan_single_pmt(
            pmt_number=1,
            serial=pmt1_serial,
            zeniths=zeniths,
            azimuths=azimuths,
            daq_runtime=daq_runtime,
            progress_callback=lambda pct, msg, pos: progress_callback(
                int(pct * 0.5), f"PMT1: {msg}", pos
            ) if progress_callback else None
        )
        
        # Scan PMT2
        if progress_callback:
            progress_callback(50, "Starting PMT2 scan...", "")
        
        result2 = self.scan_single_pmt(
            pmt_number=2,
            serial=pmt2_serial,
            zeniths=zeniths,
            azimuths=azimuths,
            daq_runtime=daq_runtime,
            progress_callback=lambda pct, msg, pos: progress_callback(
                50 + int(pct * 0.5), f"PMT2: {msg}", pos
            ) if progress_callback else None
        )
        
        logger.info("✓ Both PMTs scan complete")
        
        return {
            'status': 'success',
            'timestamp': timestamp,
            'pmt1': result1,
            'pmt2': result2
        }


# ============================================================================
# Example Usage
# ============================================================================

# if __name__ == "__main__":
#     from xarm.wrapper import XArmAPI
    
#     # Initialize components
#     arm = XArmAPI('192.168.1.xxx')
#     arm.connect()
    
#     digitizer = CAENDigitizerWaveDump(
#         wavedump_path="/usr/local/bin/WaveDump",
#         config_template="configs/WaveDumpConfig_template.txt"
#     )
    
#     # Create controller
#     controller = XArmPMTController(arm=arm, digitizer=digitizer)
    
#     # Check status
#     print(f"Robot position: {controller.get_current_position()}")
#     print(f"Digitizer status: {digitizer.get_status()}")
    
#     # Run dark current check
#     controller.dark_current_check(
#         pmt1_serial="ZE1234",
#         pmt2_serial="ZE1235",
#         duration=300
#     )