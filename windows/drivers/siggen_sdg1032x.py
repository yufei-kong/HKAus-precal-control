"""
Siglent SDG1032X Signal Generator Driver
Wrapper around pysdg1032x library for consistent interface

Usage:
    from drivers.siggen_sdg1032x import SiglentSDG1032X
    
    siggen = SiglentSDG1032X("192.168.1.101")
    siggen.connect()
    
    # Configure waveform
    siggen.set_waveform(1, "SINE")
    siggen.set_frequency(1, 1000.0)
    siggen.set_amplitude(1, 1.0)
    siggen.set_output(1, True)
    
    siggen.disconnect()
"""

from typing import Optional, Union
from loguru import logger

# Fix for pysdg1032x library bug: it calls display() which doesn't exist
# outside of Jupyter notebooks. Create a dummy function to work around this.
import builtins
if not hasattr(builtins, 'display'):
    builtins.display = lambda *args, **kwargs: None

# Now try to import the library
try:
    from sdg1032x.sdg1032x import SDG1032X
    PYSDG1032X_AVAILABLE = True
except ImportError:
    logger.error("pysdg1032x not installed. Install with: pip install pysdg1032x or pip install -e ./SDG1032x/pysdg1032x")
    PYSDG1032X_AVAILABLE = False


class SiglentSDG1032X:
    """
    Driver wrapper for Siglent SDG1032X dual-channel signal generator
    
    Provides a clean interface matching other project drivers while wrapping
    the pysdg1032x library functionality.
    """
    
    def __init__(self, ip_address: str):
        """
        Initialize signal generator driver
        
        Args:
            ip_address: IP address of the signal generator (e.g., "192.168.1.101")
        """
        if not PYSDG1032X_AVAILABLE:
            raise ImportError("pysdg1032x library not available")
        
        self.ip_address = ip_address
        self.device: Optional[SDG1032X] = None
        self._connected = False
        
        logger.info(f"SiglentSDG1032X driver initialized for {ip_address}")
    
    def connect(self):
        """Connect to the signal generator"""
        if self._connected:
            logger.warning("Already connected")
            return
        
        try:
            self.device = SDG1032X(self.ip_address)
            self._connected = True
            logger.info(f"Connected to Siglent SDG1032X at {self.ip_address}")
        except Exception as e:
            logger.error(f"Failed to connect to signal generator: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from the signal generator"""
        if not self._connected:
            return
        
        try:
            # pysdg1032x doesn't have explicit disconnect, but we track state
            self.device = None
            self._connected = False
            logger.info("Disconnected from signal generator")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
    
    def _ensure_connected(self):
        """Internal helper to ensure device is connected"""
        if not self._connected or self.device is None:
            raise RuntimeError("Signal generator not connected. Call connect() first.")
    
    def _extract_value(self, value, default=''):
        """
        Extract value from list if needed
        getCurrentParams() returns all values as single-element lists
        """
        if isinstance(value, list) and len(value) > 0:
            return value[0]
        elif isinstance(value, list):
            return default
        return value
    
    # ========================================================================
    # Waveform Configuration
    # ========================================================================
    
    def set_waveform(self, channel: int, waveform: str):
        """
        Set waveform type for channel
        
        Args:
            channel: Channel number (1 or 2)
            waveform: Waveform type - SINE, SQUARE, RAMP, PULSE, NOISE, ARB, DC
        """
        self._ensure_connected()
        
        waveform = waveform.upper()
        valid_waveforms = ["SINE", "SQUARE", "RAMP", "PULSE", "NOISE", "ARB", "DC"]
        
        if waveform not in valid_waveforms:
            raise ValueError(f"Invalid waveform. Must be one of: {', '.join(valid_waveforms)}")
        
        try:
            self.device.setWaveType(waveform, channel=channel)
            logger.debug(f"Ch{channel}: Set waveform to {waveform}")
        except Exception as e:
            logger.error(f"Failed to set waveform: {e}")
            raise
    
    def set_frequency(self, channel: int, frequency: float):
        """
        Set frequency for channel
        
        Args:
            channel: Channel number (1 or 2)
            frequency: Frequency in Hz (device range: 1µHz to 30MHz)
        """
        self._ensure_connected()
        
        try:
            self.device.setWaveFrequency(frequency, channel=channel)
            logger.debug(f"Ch{channel}: Set frequency to {frequency} Hz")
        except Exception as e:
            logger.error(f"Failed to set frequency: {e}")
            raise
    
    def set_amplitude(self, channel: int, amplitude: float):
        """
        Set amplitude for channel
        
        Args:
            channel: Channel number (1 or 2)
            amplitude: Amplitude in Volts (device range depends on load)
        """
        self._ensure_connected()
        
        try:
            self.device.setWaveAmplitude(amplitude, channel=channel)
            logger.debug(f"Ch{channel}: Set amplitude to {amplitude} V")
        except Exception as e:
            logger.error(f"Failed to set amplitude: {e}")
            raise
    
    def set_offset(self, channel: int, offset: float):
        """
        Set DC offset for channel
        
        Args:
            channel: Channel number (1 or 2)
            offset: DC offset in Volts
        """
        self._ensure_connected()
        
        try:
            self.device.setWaveOffset(offset, channel=channel)
            logger.debug(f"Ch{channel}: Set offset to {offset} V")
        except Exception as e:
            logger.error(f"Failed to set offset: {e}")
            raise
    
    def set_phase(self, channel: int, phase: float):
        """
        Set phase for channel
        
        Args:
            channel: Channel number (1 or 2)
            phase: Phase in degrees (0-360)
        """
        self._ensure_connected()
        
        if not 0 <= phase <= 360:
            raise ValueError("Phase must be between 0 and 360 degrees")
        
        try:
            # Note: Need to verify if setPhase or similar method exists
            if hasattr(self.device, 'setPhase'):
                self.device.setPhase(phase, channel=channel)
                logger.debug(f"Ch{channel}: Set phase to {phase}°")
            else:
                logger.warning(f"Phase setting not supported by this library version")
        except Exception as e:
            logger.error(f"Failed to set phase: {e}")
            raise
    
    def set_pulse_width(self, channel: int, width: float, unit: str = 'ns'):
        """
        Set pulse width for PULSE waveform
        
        Args:
            channel: Channel number (1 or 2)
            width: Pulse width value
            unit: Time unit ('s', 'ms', 'us', 'ns') - default 'ns'
        """
        self._ensure_connected()
        
        try:
            self.device.setPulseWidth(width, unit=unit, channel=channel)
            logger.debug(f"Ch{channel}: Set pulse width to {width}{unit}")
        except Exception as e:
            logger.error(f"Failed to set pulse width: {e}")
            raise
    
    # ========================================================================
    # Output Control
    # ========================================================================
    
    def set_output(self, channel: int, enabled: bool):
        """
        Enable or disable channel output
        
        Args:
            channel: Channel number (1 or 2)
            enabled: True to enable output, False to disable
        """
        self._ensure_connected()
        
        try:
            if enabled:
                self.device.outputEnable(channel=channel)
            else:
                self.device.outputDisable(channel=channel)
            state = "enabled" if enabled else "disabled"
            logger.info(f"Ch{channel}: Output {state}")
        except Exception as e:
            logger.error(f"Failed to set output state: {e}")
            raise
    
    # ========================================================================
    # Status Queries
    # ========================================================================

    def query_output_state(self, channel: int) -> bool:
        """
        Query the actual output state from device using SCPI command.
        
        Args:
            channel: Channel number (1 or 2)
            
        Returns:
            True if output is ON, False if OFF
        """
        self._ensure_connected()
        
        try:
            # Send SCPI query command
            if channel == 1:
                reply = self.device.internal_socketSend(b'C1:OUTP?')
            elif channel == 2:
                reply = self.device.internal_socketSend(b'C2:OUTP?')
            else:
                raise ValueError("Channel must be 1 or 2")
            
            # Parse reply - format: "C1:OUTP OFF,..." or "C1:OUTP ON,..."
            reply_str = reply.decode('ascii').strip().upper()
            
            # The output state is right after "OUTP "
            if 'OUTP ON' in reply_str.split(',')[0]:
                return True
            elif 'OUTP OFF' in reply_str.split(',')[0]:
                return False
            else:
                logger.warning(f"Unexpected reply format: {reply_str}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to query output state: {e}")
            raise
        
    def get_current_params(self, channel: int) -> dict:
        """
        Get all current parameters for channel from the device
        
        Returns:
            Dict with parameter values from getCurrentParams()
        """
        self._ensure_connected()
        try:
            channel_name, params = self.device.getCurrentParams(channel=channel)
            return params
        except Exception as e:
            logger.error(f"Failed to get current params: {e}")
            raise
    
    def get_waveform(self, channel: int) -> str:
        """Get current waveform type for channel"""
        params = self.get_current_params(channel)
        wvtp = params.get('WVTP', ['UNKNOWN'])
        return self._extract_value(wvtp, 'UNKNOWN')
    
    def get_frequency(self, channel: int) -> float:
        """Get current frequency for channel"""
        params = self.get_current_params(channel)
        freq_list = params.get('FRQ', ['0'])
        freq_str = self._extract_value(freq_list, '0')
        
        # Parse frequency - may have unit suffix (HZ, KHZ, MHZ)
        try:
            freq_str = freq_str.upper()
            if 'HZ' in freq_str:
                freq_str = freq_str.replace('HZ', '')
                if 'M' in freq_str:
                    return float(freq_str.replace('M', '')) * 1e6
                elif 'K' in freq_str:
                    return float(freq_str.replace('K', '')) * 1e3
                else:
                    return float(freq_str)
            return float(freq_str)
        except:
            return 0.0
    
    def get_amplitude(self, channel: int) -> float:
        """Get current amplitude for channel"""
        params = self.get_current_params(channel)
        amp_list = params.get('AMP', ['0V'])
        amp_str = self._extract_value(amp_list, '0V')
        
        # Parse amplitude - remove 'V' suffix
        try:
            return float(amp_str.replace('V', ''))
        except:
            return 0.0
    
    def get_offset(self, channel: int) -> float:
        """Get current offset for channel"""
        params = self.get_current_params(channel)
        offset_list = params.get('OFST', ['0V'])
        offset_str = self._extract_value(offset_list, '0V')
        
        # Parse offset - remove 'V' suffix
        try:
            return float(offset_str.replace('V', ''))
        except:
            return 0.0
    
    def get_output_state(self, channel: int) -> bool:
        """Get current output state for channel"""
        return self.query_output_state(channel)
    
    def get_status(self, channel: int) -> dict:
        """
        Get complete status for channel
        
        Returns:
            Dict with all channel parameters
        """
        self._ensure_connected()
        
        try:
            return {
                "waveform": self.get_waveform(channel),
                "frequency": self.get_frequency(channel),
                "amplitude": self.get_amplitude(channel),
                "offset": self.get_offset(channel),
                "output_enabled": self.get_output_state(channel)
            }
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
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
        return f"SiglentSDG1032X({self.ip_address}, {status})"