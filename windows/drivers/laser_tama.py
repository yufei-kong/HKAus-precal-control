"""
Tama Electric Laser Driver (LSB-200)
Python wrapper for tmHIDLD.dll using pythonnet

CRITICAL: This driver requires 32-bit Python to match the laser's USB HID interface.
The DLL uses .NET Framework 4.0+ for USB HID communication.

Usage:
    from drivers.laser_tama import TamaLaser
    
    laser = TamaLaser(dll_path="C:/LSB-200/app/tmHIDLD.dll")
    laser.connect()
    
    # Control laser
    laser.set_tec_power(True)  # Turn on temperature control first
    laser.set_temperature(25.0)
    laser.set_pulse_current(175.0)
    laser.set_ld_power(True)   # Turn on laser
    
    # Read status
    status = laser.get_status()
    
    laser.disconnect()
"""

from typing import Optional, Dict, Any
from loguru import logger
import sys
import os

try:
    import clr  # pythonnet
    PYTHONNET_AVAILABLE = True
except ImportError:
    logger.error("pythonnet not installed. Install with: pip install pythonnet==3.0.3")
    PYTHONNET_AVAILABLE = False


class TamaLaser:
    """
    Driver for Tama Electric LSB-200 Picosecond Laser
    
    Provides control over LD (laser diode), TEC (temperature control),
    and pulse parameters via USB HID interface using .NET DLL.
    
    IMPORTANT: Requires 32-bit Python!
    """
    
    def __init__(self, dll_path: str = "C:/LSB-200/app/tmHIDLD.dll", device_index: int = 0):
        """
        Initialize Tama laser driver
        
        Args:
            dll_path: Path to tmHIDLD.dll
            device_index: Device index if multiple lasers connected (default 0)
        """
        if not PYTHONNET_AVAILABLE:
            raise ImportError("pythonnet library not available")
        
        # Verify Python is 32-bit
        import struct
        if struct.calcsize("P") * 8 != 32:
            raise RuntimeError("This driver requires 32-bit Python. Current Python is 64-bit.")
        
        self.dll_path = dll_path
        self.device_index = device_index
        self.device = None
        self._connected = False
        
        # Verify DLL exists
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"DLL not found at: {dll_path}")
        
        logger.info(f"TamaLaser driver initialized for DLL: {dll_path}")
    
    def connect(self):
        """Connect to the laser"""
        if self._connected:
            logger.warning("Already connected")
            return
        
        try:
            # Load the .NET DLL
            clr.AddReference(self.dll_path)
            from tmHIDLD import tmHIDLD
            
            # Create device instance (True = USB mode)
            self.device = tmHIDLD(True)
            
            # Set UseUnit (from config file: UseUnit = 1)
            self.device.UseUnit = 1
            
            # Check for USB devices
            self.device.CheckUSB()
            
            # Verify device was found
            dev_count = self.device.DevCount
            if dev_count == 0:
                raise RuntimeError("No laser devices found on USB")
            
            if self.device_index >= dev_count:
                raise RuntimeError(f"Device index {self.device_index} out of range (found {dev_count} devices)")
            
            self._connected = True
            logger.success(f"Connected to Tama Laser (Device {self.device_index + 1}/{dev_count})")
            
        except Exception as e:
            logger.error(f"Failed to connect to laser: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from the laser"""
        if not self._connected:
            return
        
        try:
            # Safety: Turn off LD and TEC before disconnecting
            self.set_ld_power(False)
            self.set_tec_power(False)
            
            self.device = None
            self._connected = False
            logger.info("Disconnected from laser")
            
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
    
    def _ensure_connected(self):
        """Internal helper to ensure device is connected"""
        if not self._connected or self.device is None:
            raise RuntimeError("Laser not connected. Call connect() first.")
    
    def _poll_device(self):
        """
        Poll device to refresh all sensor readings
        
        CRITICAL: Must call GetPD() before reading any status properties.
        GetPD() triggers a bulk read from the device and caches all values.
        """
        self._ensure_connected()
        try:
            # GetPD(device_index) polls the device and returns PD current
            # As a side effect, it updates all cached properties
            self.device.GetPD(self.device_index)
        except Exception as e:
            logger.error(f"Failed to poll device: {e}")
            raise
    
    # ========================================================================
    # Power Control
    # ========================================================================
    
    def set_ld_power(self, enabled: bool):
        """
        Turn laser diode ON or OFF
        
        Args:
            enabled: True to turn on, False to turn off
        """
        self._ensure_connected()
        
        try:
            cmd = 1 if enabled else 0
            self.device.LDOnOFF(cmd, self.device_index)
            state = "ON" if enabled else "OFF"
            logger.info(f"LD power: {state}")
        except Exception as e:
            logger.error(f"Failed to set LD power: {e}")
            raise
    
    def set_tec_power(self, enabled: bool):
        """
        Turn temperature control ON or OFF
        
        Args:
            enabled: True to turn on, False to turn off
        """
        self._ensure_connected()
        
        try:
            cmd = 1 if enabled else 0
            self.device.TECOnOFF(cmd, self.device_index)
            state = "ON" if enabled else "OFF"
            logger.info(f"TEC power: {state}")
        except Exception as e:
            logger.error(f"Failed to set TEC power: {e}")
            raise
    
    # ========================================================================
    # Temperature Control
    # ========================================================================
    
    def set_temperature(self, temp_celsius: float):
        """
        Set target LD temperature
        
        Args:
            temp_celsius: Target temperature in Celsius (0-40°C for tmHIDLD40.dll)
        """
        self._ensure_connected()
        
        if not 0 <= temp_celsius <= 40:
            raise ValueError("Temperature must be between 0 and 40°C")
        
        try:
            self.device.SetTemp(self.device_index, temp_celsius)
            logger.info(f"Temperature setpoint: {temp_celsius}°C")
        except Exception as e:
            logger.error(f"Failed to set temperature: {e}")
            raise
    
    def get_temperature_setpoint(self) -> float:
        """Get current temperature setpoint"""
        self._ensure_connected()
        
        try:
            return self.device.GetTemp(self.device_index)
        except Exception as e:
            logger.error(f"Failed to get temperature setpoint: {e}")
            raise
    
    # ========================================================================
    # Current Control
    # ========================================================================
    
    def set_pulse_current(self, current_ma: float):
        """
        Set pulse current
        
        Args:
            current_ma: Pulse current in mA (0-200 mA)
        """
        self._ensure_connected()
        
        if not 0 <= current_ma <= 200:
            raise ValueError("Pulse current must be between 0 and 200 mA")
        
        try:
            self.device.SetLDCurrent(self.device_index, current_ma)
            logger.info(f"Pulse current: {current_ma} mA")
        except Exception as e:
            logger.error(f"Failed to set pulse current: {e}")
            raise
    
    def set_bias_current(self, current_ma: float):
        """
        Set bias current
        
        Args:
            current_ma: Bias current in mA (0-200 mA)
        """
        self._ensure_connected()
        
        if not 0 <= current_ma <= 200:
            raise ValueError("Bias current must be between 0 and 200 mA")
        
        try:
            self.device.SetBias(self.device_index, current_ma)
            logger.info(f"Bias current: {current_ma} mA")
        except Exception as e:
            logger.error(f"Failed to set bias current: {e}")
            raise
    
    def set_soa_current(self, current_ma: float):
        """
        Set SOA (Semiconductor Optical Amplifier) DC current
        
        Args:
            current_ma: SOA current in mA (0-300 mA)
        """
        self._ensure_connected()
        
        if not 0 <= current_ma <= 300:
            raise ValueError("SOA current must be between 0 and 300 mA")
        
        try:
            self.device.SetDCCurrent(self.device_index, current_ma)
            logger.info(f"SOA current: {current_ma} mA")
        except Exception as e:
            logger.error(f"Failed to set SOA current: {e}")
            raise
    
    # ========================================================================
    # Oscillator Control
    # ========================================================================
    
    def set_oscillator(self, pg1_enabled: bool = False, pg2_enabled: bool = False, 
                      ext_enabled: bool = False):
        """
        Control pattern generator oscillators
        
        Args:
            pg1_enabled: Enable PG1 (100kHz - 250MHz)
            pg2_enabled: Enable PG2 (3kHz - 200kHz)
            ext_enabled: Enable external trigger
        """
        self._ensure_connected()
        
        try:
            self.device.SetPGOnOff(self.device_index, pg1_enabled, pg2_enabled, ext_enabled)
            logger.info(f"Oscillator: PG1={pg1_enabled}, PG2={pg2_enabled}, EXT={ext_enabled}")
        except Exception as e:
            logger.error(f"Failed to set oscillator: {e}")
            raise
    
    def set_pg1_frequency(self, frequency_hz: int):
        """Set PG1 repetition frequency (100kHz - 250MHz)"""
        self._ensure_connected()
        
        if not 100_000 <= frequency_hz <= 250_000_000:
            raise ValueError("PG1 frequency must be between 100kHz and 250MHz")
        
        try:
            self.device.SetPG1Repetition(self.device_index, frequency_hz)
            logger.info(f"PG1 frequency: {frequency_hz} Hz")
        except Exception as e:
            logger.error(f"Failed to set PG1 frequency: {e}")
            raise
    
    def set_pg2_frequency(self, frequency_hz: int):
        """Set PG2 repetition frequency (3kHz - 200kHz)"""
        self._ensure_connected()
        
        if not 3_000 <= frequency_hz <= 200_000:
            raise ValueError("PG2 frequency must be between 3kHz and 200kHz")
        
        try:
            self.device.SetPG2Repetition(self.device_index, frequency_hz)
            logger.info(f"PG2 frequency: {frequency_hz} Hz")
        except Exception as e:
            logger.error(f"Failed to set PG2 frequency: {e}")
            raise
    
    # ========================================================================
    # Status Queries
    # ========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get complete laser status
        
        Returns:
            Dictionary with all status parameters
        """
        self._ensure_connected()
        
        try:
            # CRITICAL: Poll device first to refresh all readings
            self._poll_device()
            
            # Now read cached properties
            status = {
                'ld_on': bool(self.device.LDOn),
                'tec_on': bool(self.device.TECOn),
                'ld_temp_actual': float(self.device.LD_Temp),
                'board_temp': float(self.device.BD_Temp),
                'pulse_current': float(self.device.Pulse),
                'bias_current': float(self.device.Bias),
                'soa_current': float(self.device.SOA_current),
                'tec_current': float(self.device.TEC_current),
                'pd_current': float(self.device.PD_current),
                'pulse_width': float(self.device.PulseWidthB),
                'ld_temp_setpoint': self.get_temperature_setpoint(),
            }
            
            logger.debug(f"Laser status: {status}")
            return status
            
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            raise
    
    def get_device_info(self) -> Dict[str, Any]:
        """
        Get device information
        
        Returns:
            Dictionary with device info
        """
        self._ensure_connected()
        
        try:
            return {
                'firmware_version': self.device.getFirmVersion(self.device_index),
                'device_count': self.device.DevCount,
                'device_index': self.device_index,
            }
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            raise
    
    # ========================================================================
    # Context Manager Support
    # ========================================================================
    
    def __enter__(self):
        """Enable context manager usage"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup when exiting context"""
        self.disconnect()
    
    def __repr__(self):
        """String representation"""
        status = "connected" if self._connected else "disconnected"
        return f"TamaLaser({self.dll_path}, {status})"


# ============================================================================
# Example Usage & Testing
# ============================================================================

if __name__ == "__main__":
    # Configure logger for testing
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    print("\n=== Testing Tama Electric Laser Driver ===\n")
    
    laser = TamaLaser(dll_path="C:/hyperk-daq/windows_machine/LSB-200/app/tmHIDLD.dll")
    
    try:
        # Connect
        print("Connecting to laser...")
        laser.connect()
        print("✓ Connected\n")
        
        # Get device info
        print("Device Information:")
        info = laser.get_device_info()
        print(f"  Firmware: {info['firmware_version']}")
        print(f"  Devices: {info['device_count']}\n")
        
        # Get status
        print("Reading status...")
        status = laser.get_status()
        print(f"  LD Power: {'ON' if status['ld_on'] else 'OFF'}")
        print(f"  TEC Power: {'ON' if status['tec_on'] else 'OFF'}")
        print(f"  LD Temp: {status['ld_temp_actual']:.2f}°C (setpoint: {status['ld_temp_setpoint']:.1f}°C)")
        print(f"  Board Temp: {status['board_temp']:.2f}°C")
        print(f"  Pulse Current: {status['pulse_current']:.2f} mA")
        print(f"  PD Current: {status['pd_current']:.3f} pA")
        print("✓ Status read successfully\n")
        
        print("=== All Tests Passed! ===")
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        print("\nDisconnecting...")
        laser.disconnect()
        print("✓ Disconnected")