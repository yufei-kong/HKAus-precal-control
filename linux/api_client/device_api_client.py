"""
API Client for Windows Device Server
Use this on Linux machine to control CAEN HV, Signal Generator, and Laser remotely

Usage:
    from drivers.api_client import WindowsDeviceClient
    
    client = WindowsDeviceClient("192.168.0.186")
    
    # Control CAEN HV
    client.caen_set_voltage(1, 1000.0)
    client.caen_set_power(1, True)
    
    # Control Signal Generator
    client.siggen_set_waveform(1, "SINE", frequency=1000, amplitude=1.0)
    client.siggen_enable_output(1, True)
    
    # Control Laser
    client.laser_set_temperature(25.0)
    client.laser_set_pulse_current(175.0)
    client.laser_set_tec_power(True)
    status = client.laser_get_status()
"""

import requests
from typing import Dict, Any, Optional, List
from loguru import logger
import sys


class WindowsDeviceClient:
    """
    Client for communicating with Windows device server
    Provides simple Python interface to control remote devices
    """
    
    def __init__(self, server_ip: str = "192.168.0.186", port: int = 8000, timeout: int = 10):
        """
        Initialize client
        
        Args:
            server_ip: IP address of Windows machine
            port: Server port (default: 8000)
            timeout: Request timeout in seconds
        """
        self.base_url = f"http://{server_ip}:{port}"
        self.timeout = timeout
        logger.info(f"WindowsDeviceClient initialized: {self.base_url}")
    
    def _get(self, endpoint: str) -> Dict[str, Any]:
        """Make GET request"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"GET {endpoint} failed: {e}")
            raise
    
    def _post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.post(url, json=data, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"POST {endpoint} failed: {e}")
            raise
    
    # ========================================================================
    # Server Health
    # ========================================================================
    
    def check_connection(self) -> bool:
        """
        Check if server is reachable and devices are connected
        
        Returns:
            True if server is healthy, False otherwise
        """
        try:
            response = self._get("/health")
            caen_ok = response["devices"]["caen_dt5533e"] == "connected"
            siggen_ok = response["devices"]["siglent_sdg1032x"] == "connected"
            laser_ok = response["devices"].get("tama_laser") == "connected"
            
            if not caen_ok:
                logger.warning("CAEN HV not connected")
            if not siggen_ok:
                logger.warning("Signal generator not connected")
            if not laser_ok:
                logger.warning("Laser not connected")
            
            return caen_ok or siggen_ok or laser_ok  # At least one device should work
        except Exception as e:
            logger.error(f"Server connection check failed: {e}")
            return False
    
    def get_server_status(self) -> Dict[str, Any]:
        """Get detailed server and device status"""
        return self._get("/health")
    
    # ========================================================================
    # CAEN DT5533E Control
    # ========================================================================
    
    def caen_set_voltage(self, channel: int, voltage: float) -> Dict[str, Any]:
        """
        Set CAEN channel voltage
        
        Args:
            channel: Channel number (0-3)
            voltage: Voltage in V (0-4000)
        
        Returns:
            Response dict with status
        """
        data = {"channel": channel, "voltage": voltage}
        return self._post("/caen/channel/control", data)
    
    def caen_set_current_limit(self, channel: int, current: float) -> Dict[str, Any]:
        """
        Set CAEN channel current limit
        
        Args:
            channel: Channel number (0-3)
            current: Current limit in µA (0-3000)
        
        Returns:
            Response dict with status
        """
        data = {"channel": channel, "current_limit": current}
        return self._post("/caen/channel/control", data)
    
    def caen_set_power(self, channel: int, power_on: bool) -> Dict[str, Any]:
        """
        Turn CAEN channel on or off
        
        Args:
            channel: Channel number (0-3)
            power_on: True to turn on, False to turn off
        
        Returns:
            Response dict with status
        """
        data = {"channel": channel, "power_on": power_on}
        return self._post("/caen/channel/control", data)
    
    def caen_set_ramp_up(self, channel: int, rate: float) -> Dict[str, Any]:
        """
        Set CAEN channel ramp up rate
        
        Args:
            channel: Channel number (0-3)
            rate: Ramp up rate in V/s (1-500)
        
        Returns:
            Response dict with status
        """
        data = {"channel": channel, "ramp_up": rate}
        return self._post("/caen/channel/control", data)
    
    def caen_set_ramp_down(self, channel: int, rate: float) -> Dict[str, Any]:
        """
        Set CAEN channel ramp down rate
        
        Args:
            channel: Channel number (0-3)
            rate: Ramp down rate in V/s (1-500)
        
        Returns:
            Response dict with status
        """
        data = {"channel": channel, "ramp_down": rate}
        return self._post("/caen/channel/control", data)
    
    def caen_configure_channel(
        self,
        channel: int,
        voltage: Optional[float] = None,
        current_limit: Optional[float] = None,
        ramp_up: Optional[float] = None,
        ramp_down: Optional[float] = None,
        power_on: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Configure multiple CAEN channel parameters at once
        
        Args:
            channel: Channel number (0-3)
            voltage: Voltage in V (0-4000)
            current_limit: Current limit in µA (0-3000)
            ramp_up: Ramp up rate in V/s (1-500)
            ramp_down: Ramp down rate in V/s (1-500)
            power_on: Power state
        
        Returns:
            Response dict with status
        """
        data = {"channel": channel}
        if voltage is not None:
            data["voltage"] = voltage
        if current_limit is not None:
            data["current_limit"] = current_limit
        if ramp_up is not None:
            data["ramp_up"] = ramp_up
        if ramp_down is not None:
            data["ramp_down"] = ramp_down
        if power_on is not None:
            data["power_on"] = power_on
        
        return self._post("/caen/channel/control", data)
    
    def caen_get_status(self, channel: int) -> Dict[str, Any]:
        """
        Get CAEN channel status and measurements
        
        Args:
            channel: Channel number (0-3)
        
        Returns:
            Dict with voltage_mon, current_mon, power_on, status flags, etc.
        """
        return self._get(f"/caen/channel/{channel}/status")
    
    def caen_get_voltage(self, channel: int) -> float:
        """Get monitored voltage for channel (convenience method)"""
        status = self.caen_get_status(channel)
        return status["voltage_mon"]
    
    def caen_get_current(self, channel: int) -> float:
        """Get monitored current for channel (convenience method)"""
        status = self.caen_get_status(channel)
        return status["current_mon"]
    
    def caen_get_all_channels(self) -> List[Dict[str, Any]]:
        """
        Get status for all CAEN channels
        
        Returns:
            List of channel status dicts
        """
        response = self._get("/caen/channels/status")
        return response["channels"]
    
    def caen_emergency_off(self) -> Dict[str, Any]:
        """
        Emergency shutdown - turn off all CAEN channels immediately
        
        Returns:
            Response dict with status
        """
        logger.warning("EMERGENCY OFF: Shutting down all CAEN channels")
        return self._post("/caen/emergency_off", {})
    
    # ========================================================================
    # Signal Generator Control
    # ========================================================================
    
    def siggen_set_waveform(
        self,
        channel: int,
        waveform: str,
        frequency: Optional[float] = None,
        amplitude: Optional[float] = None,
        offset: Optional[float] = None,
        phase: Optional[float] = None,
        pulse_width: Optional[float] = None,
        pulse_width_unit: str = 'ns'
    ) -> Dict[str, Any]:
        """
        Configure signal generator waveform
        
        Args:
            channel: Channel number (1-2)
            waveform: Waveform type (SINE, SQUARE, RAMP, PULSE, NOISE, ARB, DC)
            frequency: Frequency in Hz
            amplitude: Amplitude in V
            offset: Offset in V
            phase: Phase in degrees (0-360)
            pulse_width: Pulse width (for PULSE waveform)
            pulse_width_unit: Unit for pulse width ('s', 'ms', 'us', 'ns') - default 'ns'
        
        Returns:
            Response dict with status
        """
        data = {"channel": channel, "waveform": waveform.upper()}
        if frequency is not None:
            data["frequency"] = frequency
        if amplitude is not None:
            data["amplitude"] = amplitude
        if offset is not None:
            data["offset"] = offset
        if phase is not None:
            data["phase"] = phase
        if pulse_width is not None:
            data["pulse_width"] = pulse_width
            data["pulse_width_unit"] = pulse_width_unit
        
        return self._post("/siggen/waveform", data)
    
    def siggen_enable_output(self, channel: int, enabled: bool) -> Dict[str, Any]:
        """
        Enable or disable signal generator output
        
        Args:
            channel: Channel number (1-2)
            enabled: True to enable, False to disable
        
        Returns:
            Response dict with status
        """
        data = {"channel": channel, "enabled": enabled}
        return self._post("/siggen/output", data)
    
    def siggen_get_status(self, channel: int) -> Dict[str, Any]:
        """
        Get signal generator channel status
        
        Args:
            channel: Channel number (1-2)
        
        Returns:
            Dict with waveform, frequency, amplitude, offset, output_enabled
        """
        return self._get(f"/siggen/channel/{channel}/status")
    
    # ========================================================================
    # Laser Control
    # ========================================================================
    
    def laser_set_ld_power(self, enabled: bool) -> Dict[str, Any]:
        """
        Turn laser diode ON or OFF
        
        Args:
            enabled: True to turn on, False to turn off
        
        Returns:
            Response dict with status
        """
        data = {"ld_enabled": enabled}
        return self._post("/laser/power", data)
    
    def laser_set_tec_power(self, enabled: bool) -> Dict[str, Any]:
        """
        Turn temperature control ON or OFF
        
        Args:
            enabled: True to turn on, False to turn off
        
        Returns:
            Response dict with status
        """
        data = {"tec_enabled": enabled}
        return self._post("/laser/power", data)
    
    def laser_set_power(self, ld_enabled: Optional[bool] = None, 
                       tec_enabled: Optional[bool] = None) -> Dict[str, Any]:
        """
        Control both LD and TEC power
        
        Args:
            ld_enabled: True to turn on LD, False to turn off
            tec_enabled: True to turn on TEC, False to turn off
        
        Returns:
            Response dict with status
        """
        data = {}
        if ld_enabled is not None:
            data["ld_enabled"] = ld_enabled
        if tec_enabled is not None:
            data["tec_enabled"] = tec_enabled
        
        return self._post("/laser/power", data)
    
    def laser_set_temperature(self, temp_celsius: float) -> Dict[str, Any]:
        """
        Set laser temperature setpoint
        
        Args:
            temp_celsius: Target temperature in Celsius (0-40°C)
        
        Returns:
            Response dict with status
        """
        data = {"temperature": temp_celsius}
        return self._post("/laser/configure", data)
    
    def laser_set_pulse_current(self, current_ma: float) -> Dict[str, Any]:
        """
        Set laser pulse current
        
        Args:
            current_ma: Pulse current in mA (0-200)
        
        Returns:
            Response dict with status
        """
        data = {"pulse_current": current_ma}
        return self._post("/laser/configure", data)
    
    def laser_set_bias_current(self, current_ma: float) -> Dict[str, Any]:
        """
        Set laser bias current
        
        Args:
            current_ma: Bias current in mA (0-200)
        
        Returns:
            Response dict with status
        """
        data = {"bias_current": current_ma}
        return self._post("/laser/configure", data)
    
    def laser_set_soa_current(self, current_ma: float) -> Dict[str, Any]:
        """
        Set laser SOA current
        
        Args:
            current_ma: SOA current in mA (0-300)
        
        Returns:
            Response dict with status
        """
        data = {"soa_current": current_ma}
        return self._post("/laser/configure", data)
    
    def laser_configure(
        self,
        temperature: Optional[float] = None,
        pulse_current: Optional[float] = None,
        bias_current: Optional[float] = None,
        soa_current: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Configure multiple laser parameters at once
        
        Args:
            temperature: Target temperature in Celsius (0-40°C)
            pulse_current: Pulse current in mA (0-200)
            bias_current: Bias current in mA (0-200)
            soa_current: SOA current in mA (0-300)
        
        Returns:
            Response dict with status
        """
        data = {}
        if temperature is not None:
            data["temperature"] = temperature
        if pulse_current is not None:
            data["pulse_current"] = pulse_current
        if bias_current is not None:
            data["bias_current"] = bias_current
        if soa_current is not None:
            data["soa_current"] = soa_current
        
        return self._post("/laser/configure", data)
    
    def laser_set_oscillator(
        self,
        pg1_enabled: Optional[bool] = None,
        pg2_enabled: Optional[bool] = None,
        ext_enabled: Optional[bool] = None,
        pg1_frequency: Optional[int] = None,
        pg2_frequency: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Configure laser oscillator
        
        Args:
            pg1_enabled: Enable PG1 (100kHz - 250MHz)
            pg2_enabled: Enable PG2 (3kHz - 200kHz)
            ext_enabled: Enable external trigger
            pg1_frequency: PG1 frequency in Hz (100000 - 250000000)
            pg2_frequency: PG2 frequency in Hz (3000 - 200000)
        
        Returns:
            Response dict with status
        """
        data = {}
        if pg1_enabled is not None:
            data["pg1_enabled"] = pg1_enabled
        if pg2_enabled is not None:
            data["pg2_enabled"] = pg2_enabled
        if ext_enabled is not None:
            data["ext_enabled"] = ext_enabled
        if pg1_frequency is not None:
            data["pg1_frequency"] = pg1_frequency
        if pg2_frequency is not None:
            data["pg2_frequency"] = pg2_frequency
        
        return self._post("/laser/oscillator", data)
    
    def laser_get_status(self) -> Dict[str, Any]:
        """
        Get laser status and measurements
        
        Returns:
            Dict with all laser parameters including temperatures, currents, power states
        """
        return self._get("/laser/status")
    
    def laser_get_temperature(self) -> float:
        """Get current LD temperature (convenience method)"""
        status = self.laser_get_status()
        return status["ld_temp_actual"]
    
    def laser_get_pulse_current(self) -> float:
        """Get current pulse current (convenience method)"""
        status = self.laser_get_status()
        return status["pulse_current"]
    
    def laser_emergency_off(self) -> Dict[str, Any]:
        """
        Emergency shutdown - turn off laser LD and TEC immediately
        
        Returns:
            Response dict with status
        """
        logger.warning("EMERGENCY OFF: Shutting down laser")
        return self._post("/laser/emergency_off", {})
    
    # ========================================================================
    # Context Manager Support
    # ========================================================================
    
    def __enter__(self):
        """Enable context manager usage"""
        if not self.check_connection():
            raise ConnectionError("Could not connect to device server")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup when exiting context"""
        pass


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example: Quick test
    client = WindowsDeviceClient("192.168.0.186")
    
    if client.check_connection():
        print("✓ Connected to device server")
        
        # Get status of all devices
        status = client.get_server_status()
        print(f"Devices: {status['devices']}")
    else:
        print("✗ Could not connect to device server")