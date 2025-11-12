"""
CAEN DT5533E Desktop HV Power Supply Driver
Complete implementation based on DT55xxE User Manual Rev.14

For Windows machine controlling 3 PMT channels via USB VCP
"""

import ctypes
from ctypes import c_int, c_short, c_ushort, c_char_p, c_void_p, POINTER, byref
from typing import List, Dict, Optional
from loguru import logger
import time


# Constants from CAEN manual
CAENHV_OK = 0x0
SYSTEM_TYPE_DT55XXE = 11
LINKTYPE_USB_VCP = 5


class DT5533E:
    """
    Driver for CAEN DT5533E Desktop HV Power Supply.
    
    Features:
    - 4 channels, 4kV/3mA (4W) per channel
    - Voltage monitoring
    - Current monitoring and limiting
    - Programmable ramp rates
    - Status monitoring with 13 different flags
    - Trip protection
    """
    
    def __init__(self, com_port: str = "COM3", baudrate: int = 115200):
        """
        Initialize DT5533E driver.
        
        Args:
            com_port: COM port (e.g., "COM3")
            baudrate: Baud rate (default 115200)
        """
        self.com_port = com_port
        self.baudrate = baudrate
        self.handle = c_int(-1)
        self.connected = False
        self.slot = 0  # Desktop units use slot 0
        
        # Load DLL
        # dll_path = r"C:\Program Files\CAEN\HV\CAENHVWrapper\bin\x86_64\CAENHVWrapper.dll"
        dll_path = r"C:\Program Files (x86)\CAEN\CAENGECO2020\CAENHVWrapper.dll"
        try:
            self.lib = ctypes.WinDLL(dll_path)
            logger.info(f"Loaded CAENHVWrapper.dll")
        except Exception as e:
            logger.error(f"Failed to load DLL: {e}")
            raise
        
        self._setup_functions()
        
    def _setup_functions(self):
        """Define C function prototypes."""
        
        # InitSystem
        self.lib.CAENHV_InitSystem.argtypes = [
            c_int, c_int, c_void_p, c_char_p, c_char_p, POINTER(c_int)
        ]
        self.lib.CAENHV_InitSystem.restype = c_int
        
        # DeinitSystem
        self.lib.CAENHV_DeinitSystem.argtypes = [c_int]
        self.lib.CAENHV_DeinitSystem.restype = c_int
        
        # GetCrateMap
        self.lib.CAENHV_GetCrateMap.argtypes = [
            c_int, POINTER(c_ushort), POINTER(POINTER(c_ushort)),
            POINTER(c_char_p), POINTER(c_char_p), POINTER(POINTER(c_ushort)),
            POINTER(POINTER(ctypes.c_ubyte)), POINTER(POINTER(ctypes.c_ubyte))
        ]
        self.lib.CAENHV_GetCrateMap.restype = c_int
        
        # GetChParam
        self.lib.CAENHV_GetChParam.argtypes = [
            c_int, c_ushort, c_char_p, c_ushort, POINTER(c_ushort), c_void_p
        ]
        self.lib.CAENHV_GetChParam.restype = c_int
        
        # SetChParam
        self.lib.CAENHV_SetChParam.argtypes = [
            c_int, c_ushort, c_char_p, c_ushort, POINTER(c_ushort), c_void_p
        ]
        self.lib.CAENHV_SetChParam.restype = c_int
    
    def connect(self) -> bool:
        """Connect to the DT5533E."""
        if self.connected:
            logger.warning("Already connected")
            return True
        
        # Build connection string
        arg_str = f"{self.com_port}_{self.baudrate}_8_1_N_0"
        arg_bytes = arg_str.encode('ascii')
        
        logger.info(f"Connecting to DT5533E on {self.com_port}...")
        
        result = self.lib.CAENHV_InitSystem(
            SYSTEM_TYPE_DT55XXE,
            LINKTYPE_USB_VCP,
            arg_bytes,
            b"",  # No username
            b"",  # No password
            byref(self.handle)
        )
        
        if result == CAENHV_OK:
            self.connected = True
            logger.success(f"Connected! Handle: {self.handle.value}")
            self._get_device_info()
            return True
        else:
            logger.error(f"Connection failed: {result:#x}")
            return False
    
    def disconnect(self):
        """Disconnect from the DT5533E."""
        if not self.connected:
            return
        
        result = self.lib.CAENHV_DeinitSystem(self.handle)
        if result == CAENHV_OK:
            self.connected = False
            logger.info("Disconnected")
        else:
            logger.error(f"Disconnect failed: {result:#x}")
    
    def _get_device_info(self):
        """Get and log device information."""
        nr_slots = c_ushort()
        nr_ch_list = POINTER(c_ushort)()
        model_list = c_char_p()
        desc_list = c_char_p()
        ser_num_list = POINTER(c_ushort)()
        fmw_min = POINTER(ctypes.c_ubyte)()
        fmw_max = POINTER(ctypes.c_ubyte)()
        
        result = self.lib.CAENHV_GetCrateMap(
            self.handle, byref(nr_slots), byref(nr_ch_list),
            byref(model_list), byref(desc_list), byref(ser_num_list),
            byref(fmw_min), byref(fmw_max)
        )
        
        if result == CAENHV_OK and model_list:
            model = model_list.value.decode('ascii')
            logger.info(f"Model: {model}, Channels: {nr_ch_list[0]}")
    
    # ==================== Control Functions ====================
    
    def set_voltage(self, channel: int, voltage: float) -> bool:
        """
        Set target voltage.
        
        Args:
            channel: Channel number (0-3)
            voltage: Voltage in Volts (0-4000V for DT5533E)
        """
        if not self.connected:
            logger.error("Not connected")
            return False
        
        ch_list = (c_ushort * 1)(channel)
        values = (ctypes.c_float * 1)(voltage)
        
        result = self.lib.CAENHV_SetChParam(
            self.handle, self.slot, b"VSet", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        if result == CAENHV_OK:
            logger.info(f"Ch{channel}: Voltage set to {voltage}V")
            return True
        else:
            logger.error(f"Ch{channel}: Failed to set voltage ({result:#x})")
            return False
    
    def set_current_limit(self, channel: int, current: float) -> bool:
        """
        Set current limit.
        
        Args:
            channel: Channel number (0-3)
            current: Current in microamps (µA), max 3000µA for DT5533E
        """
        if not self.connected:
            logger.error("Not connected")
            return False
        
        ch_list = (c_ushort * 1)(channel)
        values = (ctypes.c_float * 1)(current)
        
        result = self.lib.CAENHV_SetChParam(
            self.handle, self.slot, b"ISet", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        if result == CAENHV_OK:
            logger.info(f"Ch{channel}: Current limit set to {current}µA")
            return True
        else:
            logger.error(f"Ch{channel}: Failed to set current ({result:#x})")
            return False
    
    def set_power(self, channel: int, state: bool) -> bool:
        """
        Turn channel on or off.
        
        Args:
            channel: Channel number (0-3)
            state: True=ON, False=OFF
        """
        if not self.connected:
            logger.error("Not connected")
            return False
        
        ch_list = (c_ushort * 1)(channel)
        # Pw parameter takes 1 for ON, 0 for OFF
        values = (ctypes.c_uint * 1)(1 if state else 0)
        
        result = self.lib.CAENHV_SetChParam(
            self.handle, self.slot, b"Pw", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        if result == CAENHV_OK:
            logger.info(f"Ch{channel}: Power {'ON' if state else 'OFF'}")
            return True
        else:
            logger.error(f"Ch{channel}: Failed to set power ({result:#x})")
            return False
    
    def set_ramp_up(self, channel: int, rate: float) -> bool:
        """
        Set ramp-up rate.
        
        Args:
            channel: Channel number (0-3)
            rate: Ramp rate in V/s (1-500 V/s for DT5533E)
        """
        if not self.connected:
            logger.error("Not connected")
            return False
        
        ch_list = (c_ushort * 1)(channel)
        values = (ctypes.c_float * 1)(rate)
        
        result = self.lib.CAENHV_SetChParam(
            self.handle, self.slot, b"RUp", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        if result == CAENHV_OK:
            logger.info(f"Ch{channel}: Ramp-up set to {rate}V/s")
            return True
        else:
            logger.error(f"Ch{channel}: Failed to set ramp-up ({result:#x})")
            return False
    
    def set_ramp_down(self, channel: int, rate: float) -> bool:
        """
        Set ramp-down rate.
        
        Args:
            channel: Channel number (0-3)
            rate: Ramp rate in V/s (1-500 V/s for DT5533E)
        """
        if not self.connected:
            logger.error("Not connected")
            return False
        
        ch_list = (c_ushort * 1)(channel)
        values = (ctypes.c_float * 1)(rate)
        
        result = self.lib.CAENHV_SetChParam(
            self.handle, self.slot, b"RDwn", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        if result == CAENHV_OK:
            logger.info(f"Ch{channel}: Ramp-down set to {rate}V/s")
            return True
        else:
            logger.error(f"Ch{channel}: Failed to set ramp-down ({result:#x})")
            return False
    
    def set_trip_time(self, channel: int, seconds: float) -> bool:
        """
        Set overcurrent trip time.
        
        Args:
            channel: Channel number (0-3)
            seconds: Trip time (0-999.9s, >=1000 = infinite)
        """
        if not self.connected:
            logger.error("Not connected")
            return False
        
        ch_list = (c_ushort * 1)(channel)
        values = (ctypes.c_float * 1)(seconds)
        
        result = self.lib.CAENHV_SetChParam(
            self.handle, self.slot, b"Trip", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        if result == CAENHV_OK:
            logger.info(f"Ch{channel}: Trip time set to {seconds}s")
            return True
        else:
            logger.error(f"Ch{channel}: Failed to set trip time ({result:#x})")
            return False
    
    # ==================== Monitoring Functions ====================
    
    def get_voltage(self, channel: int) -> Optional[float]:
        """Read actual output voltage (VMon)."""
        if not self.connected:
            return None
        
        ch_list = (c_ushort * 1)(channel)
        values = (ctypes.c_float * 1)()
        
        result = self.lib.CAENHV_GetChParam(
            self.handle, self.slot, b"VMon", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        return values[0] if result == CAENHV_OK else None
    
    def get_voltage_set(self, channel: int) -> Optional[float]:
        """Read voltage setpoint (VSet)."""
        if not self.connected:
            return None
        
        ch_list = (c_ushort * 1)(channel)
        values = (ctypes.c_float * 1)()
        
        result = self.lib.CAENHV_GetChParam(
            self.handle, self.slot, b"VSet", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        return values[0] if result == CAENHV_OK else None
    
    def get_current(self, channel: int) -> Optional[float]:
        """Read actual output current (IMon) in µA."""
        if not self.connected:
            return None
        
        ch_list = (c_ushort * 1)(channel)
        values = (ctypes.c_float * 1)()
        
        result = self.lib.CAENHV_GetChParam(
            self.handle, self.slot, b"IMon", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        return values[0] if result == CAENHV_OK else None
    
    def get_status(self, channel: int) -> Optional[Dict[str, bool]]:
        """
        Read channel status.
        
        Returns dict with status flags from DT55xxE manual page 17:
        - on, ramp_up, ramp_down
        - overcurrent, overvoltage, undervoltage
        - max_voltage, trip, max_power
        - temperature_warning, over_temperature
        - killed, interlock
        """
        if not self.connected:
            logger.error("get_status: Not connected")
            return None
        
        ch_list = (c_ushort * 1)(channel)
        values = (ctypes.c_uint * 1)()
        
        result = self.lib.CAENHV_GetChParam(
            self.handle, self.slot, b"ChStatus", 1, ch_list,
            ctypes.cast(values, c_void_p)
        )
        
        if result != CAENHV_OK:
            logger.error(f"get_status: Ch{channel} failed with error code {result:#x}")
            return None
        
        bits = values[0]
        logger.debug(f"get_status: Ch{channel} status bits = {bits:#x}")
        return {
            'on': bool(bits & 0x1),
            'ramp_up': bool(bits & 0x2),
            'ramp_down': bool(bits & 0x4),
            'overcurrent': bool(bits & 0x8),
            'overvoltage': bool(bits & 0x10),
            'undervoltage': bool(bits & 0x20),
            'max_voltage': bool(bits & 0x40),
            'trip': bool(bits & 0x80),
            'max_power': bool(bits & 0x100),
            'temperature_warning': bool(bits & 0x200),
            'over_temperature': bool(bits & 0x400),
            'killed': bool(bits & 0x800),
            'interlock': bool(bits & 0x1000),
        }
    
    def get_all_channels(self, num_channels: int = 3) -> List[Dict]:
        """
        Get comprehensive data for all channels.
        
        Args:
            num_channels: Number of channels to read (default 3 PMTs)
        """
        data = []
        for ch in range(num_channels):
            data.append({
                'channel': ch,
                'voltage_set': self.get_voltage_set(ch),
                'voltage_mon': self.get_voltage(ch),
                'current': self.get_current(ch),
                'status': self.get_status(ch)
            })
        return data
    
    def get_channel_full_status(self, channel: int) -> Optional[Dict]:
        """
        Get complete status for a single channel including all parameters.
        This is a convenience method that combines multiple parameter reads.
        
        Returns dict with:
            - VSet: Voltage setpoint
            - VMon: Monitored voltage
            - ISet: Current limit
            - IMon: Monitored current
            - Pw: Power state (0=OFF, 1=ON)
            - RUp: Ramp up rate
            - RDwn: Ramp down rate
            - Status: Status flags dict
        """
        if not self.connected:
            return None
        
        # Read power state
        ch_list = (c_ushort * 1)(channel)
        pw_value = (ctypes.c_uint * 1)()
        
        result = self.lib.CAENHV_GetChParam(
            self.handle, self.slot, b"Pw", 1, ch_list,
            ctypes.cast(pw_value, c_void_p)
        )
        power_on = pw_value[0] if result == CAENHV_OK else 0
        
        # Read ramp rates
        ramp_up_value = (ctypes.c_float * 1)()
        result = self.lib.CAENHV_GetChParam(
            self.handle, self.slot, b"RUp", 1, ch_list,
            ctypes.cast(ramp_up_value, c_void_p)
        )
        ramp_up = ramp_up_value[0] if result == CAENHV_OK else 0.0
        
        ramp_down_value = (ctypes.c_float * 1)()
        result = self.lib.CAENHV_GetChParam(
            self.handle, self.slot, b"RDwn", 1, ch_list,
            ctypes.cast(ramp_down_value, c_void_p)
        )
        ramp_down = ramp_down_value[0] if result == CAENHV_OK else 0.0
        
        # Read current limit
        iset_value = (ctypes.c_float * 1)()
        result = self.lib.CAENHV_GetChParam(
            self.handle, self.slot, b"ISet", 1, ch_list,
            ctypes.cast(iset_value, c_void_p)
        )
        current_set = iset_value[0] if result == CAENHV_OK else 0.0
        
        # Get status flags (use empty dict if None)
        status_flags = self.get_status(channel)
        if status_flags is None:
            status_flags = {}
        
        return {
            'VSet': self.get_voltage_set(channel) or 0.0,
            'VMon': self.get_voltage(channel) or 0.0,
            'ISet': current_set,
            'IMon': self.get_current(channel) or 0.0,
            'Pw': power_on,
            'RUp': ramp_up,
            'RDwn': ramp_down,
            'Status': status_flags
        }
    
    # ==================== Context Manager ====================
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()