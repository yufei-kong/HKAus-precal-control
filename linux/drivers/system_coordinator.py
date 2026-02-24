"""
HyperK DAQ System Coordinator
High-level control and safety coordination across all subsystems

This class coordinates:
- Linux machine: Robot (xArm) + DAQ (CAEN Digitizer)
- Windows machine: HV (CAEN DT5533E) + Signal Gen + Laser
"""

from typing import Optional, Callable, Dict, Any
from datetime import datetime
import time
import os
import sys
from loguru import logger

# Add parent directory to path so we can import drivers
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)
# Local imports
from drivers.xarm_pmt_controller import XArmPMTController
from drivers.caen_digitizer_wavedump import CAENDigitizerWaveDump
from api_client.device_api_client import WindowsDeviceClient


class HyperKSystemCoordinator:
    """
    System-level coordinator for the entire HyperK DAQ setup.
    Handles cross-system operations like emergency stops and full scans.
    """
    
    def __init__(
        self,
        robot_controller: Optional[XArmPMTController] = None,
        api_client: Optional[WindowsDeviceClient] = None
    ):
        """
        Initialize system coordinator.
        
        Args:
            robot_controller: HyperKController instance (robot + DAQ)
            api_client: WindowsDeviceClient instance (HV + SigGen + Laser)
        """
        self.robot = robot_controller
        self.api = api_client
        
        logger.info("HyperK System Coordinator initialized")
        if robot_controller:
            logger.info("  ✓ Robot controller connected")
        if api_client:
            logger.info("  ✓ Windows device API connected")
    
    # =========================================================================
    # SAFETY: EMERGENCY SHUTDOWN
    # =========================================================================
    
    def emergency_shutdown_all(self, reason: str = "Emergency stop requested") -> Dict[str, Any]:
        """
        EMERGENCY: Immediate shutdown of all systems.
        
        This function attempts to safely stop all hardware:
        1. Robot motion (highest priority - prevent collisions)
        2. High voltage supplies (prevent damage/safety)
        3. Laser (prevent damage)
        
        Args:
            reason: Description of why emergency stop was triggered
            
        Returns:
            Dict with status of each shutdown attempt
        """
        logger.critical(f"🚨 EMERGENCY SHUTDOWN: {reason}")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'reason': reason,
            'robot': None,
            'caen_hv': None,
            'laser': None,
            'overall_success': False
        }
        
        # 1. STOP ROBOT IMMEDIATELY (highest priority)
        if self.robot:
            try:
                self.robot.emergency_stop()
                results['robot'] = {'status': 'success', 'message': 'Robot motion halted'}
                logger.warning("✓ Robot emergency stop executed")
            except Exception as e:
                results['robot'] = {'status': 'error', 'message': str(e)}
                logger.error(f"✗ Robot E-Stop failed: {e}")
        else:
            results['robot'] = {'status': 'skipped', 'message': 'Robot not connected'}
        
        # 2. SHUTDOWN HIGH VOLTAGE (safety critical)
        if self.api:
            try:
                response = self.api.caen_emergency_off()
                results['caen_hv'] = {'status': 'success', 'message': 'HV shutdown initiated'}
                logger.warning("✓ CAEN HV emergency shutdown executed")
            except Exception as e:
                results['caen_hv'] = {'status': 'error', 'message': str(e)}
                logger.error(f"✗ CAEN HV E-Stop failed: {e}")
        else:
            results['caen_hv'] = {'status': 'skipped', 'message': 'API not connected'}
        
        # 3. SHUTDOWN LASER (equipment protection)
        if self.api:
            try:
                response = self.api.laser_emergency_off()
                results['laser'] = {'status': 'success', 'message': 'Laser shutdown initiated'}
                logger.warning("✓ Laser emergency shutdown executed")
            except Exception as e:
                results['laser'] = {'status': 'error', 'message': str(e)}
                logger.error(f"✗ Laser E-Stop failed: {e}")
        else:
            results['laser'] = {'status': 'skipped', 'message': 'API not connected'}
        
        # Determine overall success
        errors = [k for k, v in results.items() 
                 if isinstance(v, dict) and v.get('status') == 'error']
        
        results['overall_success'] = len(errors) == 0
        
        if results['overall_success']:
            logger.warning("✓ All systems emergency stopped successfully")
        else:
            logger.error(f"⚠ Emergency stop completed with {len(errors)} errors: {errors}")
        
        return results
    
    # =========================================================================
    # SYSTEM STATUS CHECKS
    # =========================================================================
    
    def check_all_systems(self) -> Dict[str, Any]:
        """
        Check status of all connected systems.
        
        Returns:
            Dict with status of each subsystem
        """
        status = {
            'timestamp': datetime.now().isoformat(),
            'robot': None,
            'caen_digitizer': None,
            'caen_hv': None,
            'signal_generator': None,
            'laser': None,
            'overall_ready': False
        }
        
        # Check robot
        if self.robot:
            try:
                position = self.robot.get_current_position()
                status['robot'] = {
                    'connected': True,
                    'position': position
                }
            except Exception as e:
                status['robot'] = {'connected': False, 'error': str(e)}
        
        # Check digitizer
        if self.robot:
            try:
                digitizer_ok = self.robot.check_digitizer_status()
                status['caen_digitizer'] = {'connected': digitizer_ok}
            except Exception as e:
                status['caen_digitizer'] = {'connected': False, 'error': str(e)}
        
        # Check Windows devices
        if self.api:
            try:
                health = self.api.get_server_status()
                status['caen_hv'] = health['devices']['caen_dt5533e']
                status['signal_generator'] = health['devices']['siglent_sdg1032x']
                status['laser'] = health['devices'].get('tama_laser', 'not_available')
            except Exception as e:
                logger.error(f"Failed to get Windows device status: {e}")
        
        # Determine overall readiness
        status['overall_ready'] = (
            status.get('robot', {}).get('connected', False) and
            status.get('caen_digitizer', {}).get('connected', False) and
            status.get('caen_hv') == 'connected'
        )
        
        return status
    
    # =========================================================================
    # HIGH-LEVEL RUN SEQUENCES
    # =========================================================================
    
    def run_dark_current_check(
        self,
        pmt1_serial: str,
        pmt2_serial: str,
        duration: int = 300,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Execute dark current check sequence.
        
        This is a wrapper that adds system-level coordination and error handling.
        
        Args:
            pmt1_serial: PMT1 serial number
            pmt2_serial: PMT2 serial number
            duration: Acquisition time in seconds
            progress_callback: Optional callback(progress_pct, message)
            
        Returns:
            Dict with waveform data and run info
        """
        if not self.robot:
            raise RuntimeError("Robot controller not initialized")
        
        logger.info(f"Starting dark current check: {pmt1_serial}, {pmt2_serial}")
        
        try:
            # Run the dark current check
            waveforms = self.robot.dark_current_check(
                pmt1_serial=pmt1_serial,
                pmt2_serial=pmt2_serial,
                duration=duration,
                progress_callback=progress_callback
            )
            
            logger.info("Dark current check completed successfully")
            
            return {
                'status': 'success',
                'waveforms': waveforms,
                'pmt1_serial': pmt1_serial,
                'pmt2_serial': pmt2_serial,
                'duration': duration
            }
            
        except Exception as e:
            logger.error(f"Dark current check failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'pmt1_serial': pmt1_serial,
                'pmt2_serial': pmt2_serial,
                'duration': duration
            }
    
    def run_full_scan(
        self,
        pmt1_serial: str,
        pmt2_serial: str,
        zeniths: list = [0, 10, 20, 30, 40, 50],
        azimuths: list = [0, 90, 180, 270],
        daq_runtime: int = 5,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Execute full PMT scan sequence (both PMTs).
        
        Args:
            pmt1_serial: PMT1 serial number
            pmt2_serial: PMT2 serial number
            zeniths: Zenith angles to scan
            azimuths: Azimuthal angles to scan
            daq_runtime: Acquisition time per point (seconds)
            progress_callback: Optional callback(progress_pct, message, position)
            
        Returns:
            Dict with run status and info
        """
        if not self.robot:
            raise RuntimeError("Robot controller not initialized")
        
        logger.info(f"Starting full scan: {pmt1_serial}, {pmt2_serial}")
        logger.info(f"  Zeniths: {zeniths}")
        logger.info(f"  Azimuths: {azimuths}")
        logger.info(f"  Runtime per point: {daq_runtime}s")
        
        try:
            # Run the scan
            self.robot.full_pmt_scan(
                pmt1_serial=pmt1_serial,
                pmt2_serial=pmt2_serial,
                zeniths=zeniths,
                azimuths=azimuths,
                daq_runtime=daq_runtime,
                progress_callback=progress_callback
            )
            
            logger.info("Full scan completed successfully")
            
            return {
                'status': 'success',
                'pmt1_serial': pmt1_serial,
                'pmt2_serial': pmt2_serial,
                'total_positions': (1 + ((len(zeniths)-1) * len(azimuths))) * 2
            }
            
        except Exception as e:
            logger.error(f"Full scan failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'pmt1_serial': pmt1_serial,
                'pmt2_serial': pmt2_serial
            }
    
    def run_single_pmt_scan(
        self,
        pmt_number: int,
        serial: str,
        zeniths: list = [0, 10, 20, 30, 40, 50],
        azimuths: list = [0, 90, 180, 270],
        daq_runtime: int = 5,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Execute single PMT scan sequence.
        
        Args:
            pmt_number: PMT number (1 or 2)
            serial: PMT serial number
            zeniths: Zenith angles to scan
            azimuths: Azimuthal angles to scan
            daq_runtime: Acquisition time per point (seconds)
            progress_callback: Optional callback(progress_pct, message, position)
            
        Returns:
            Dict with run status and info
        """
        if not self.robot:
            raise RuntimeError("Robot controller not initialized")
        
        logger.info(f"Starting single PMT scan: PMT{pmt_number} ({serial})")
        
        try:
            # Run the scan
            self.robot.scan_single_pmt(
                pmt_number=pmt_number,
                serial=serial,
                zeniths=zeniths,
                azimuths=azimuths,
                daq_runtime=daq_runtime,
                progress_callback=progress_callback
            )
            
            logger.info("Single PMT scan completed successfully")
            
            return {
                'status': 'success',
                'pmt_number': pmt_number,
                'serial': serial,
                'total_positions': 1 + ((len(zeniths)-1) * len(azimuths))
            }
            
        except Exception as e:
            logger.error(f"Single PMT scan failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'pmt_number': pmt_number,
                'serial': serial
            }
    
    # =========================================================================
    # CONTEXT MANAGER SUPPORT
    # =========================================================================
    
    def __enter__(self):
        """Enable context manager usage"""
        logger.info("HyperK System Coordinator context entered")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup on context exit"""
        if exc_type is not None:
            logger.error(f"Exception in coordinator context: {exc_val}")
            # Emergency stop on any exception
            try:
                self.emergency_shutdown_all(reason=f"Exception: {exc_val}")
            except:
                pass
        
        logger.info("HyperK System Coordinator context exited")


# ============================================================================
# Example Usage
# ============================================================================

# if __name__ == "__main__":
#     from xarm.wrapper import XArmAPI
    
#     # Initialize components
#     arm = XArmAPI('192.168.1.xxx')
#     arm.connect()
    
#     robot_controller = HyperKController(
#         arm=arm,
#         wavedump_path="/usr/local/bin/WaveDump",
#         config_template="configs/WaveDumpConfig_template.txt"
#     )
    
#     api_client = WindowsDeviceClient("192.168.0.186")
    
#     # Create system coordinator
#     with HyperKSystemCoordinator(robot_controller, api_client) as system:
#         # Check all systems
#         status = system.check_all_systems()
#         print(f"System status: {status}")
        
#         # Run dark current check
#         system.run_dark_current_check(
#             pmt1_serial="ZE1234",
#             pmt2_serial="ZE1235",
#             duration=300
#         )
