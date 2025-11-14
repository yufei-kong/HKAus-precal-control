"""
IPS-2303S SiPM Power Supply Driver
Based on original Operate.py with additions for GUI integration
"""

import serial
import time 
import os
import re

class IPS2303s():
    """
    Driver for IPS-2303S dual-channel power supply.
    Used for SiPM bias voltage control.
    """
    
    def __init__(self, name='IPS2303s', port='/dev/ttyUSB0', baud=115200):
        """
        Initialize connection to IPS-2303S power supply.
        
        Args:
            name: Device name for identification
            port: Serial port (e.g., '/dev/ttyUSB0')
            baud: Baud rate (115200 or 57600)
        
        Raises:
            Exception if connection fails
        """
        self.name = name
        self.port = port
        self.baud = baud
        self.connected = False
        
        try:
            self._readDevice(self.port, self.baud)
            self.connected = True
            print(f"✓ Connected to {name} on {port}")
        except Exception as e:
            print(f"✗ Failed to connect to {name}: {e}")
            self.connected = False
            raise
    
    def close(self):
        """Close serial connection"""
        if hasattr(self, 'ser') and self.ser.is_open:
            self.ser.close()
            self.connected = False
    
    def sendCmd(self, cmd):
        """
        Send command to device and return response.
        
        Args:
            cmd: Command string
            
        Returns:
            Response string from device
        """
        self.ser.write((cmd + '\r\n').encode())
        response = self.ser.read_all().decode().strip()
        time.sleep(0.5)
        return response
    
    # =======================================================================
    # Voltage and Current Setpoints (not used in GUI - set on hardware)
    # =======================================================================
    
    def vSet(self, ch, val):
        """Set voltage for channel (normally not used - set on hardware)"""
        cmd = f'VSET{int(ch)}:{val}'
        self.sendCmd(cmd)
        print(f"Sent: {cmd}")
        return
    
    def iSet(self, ch, val):
        """Set current limit for channel (normally not used - set on hardware)"""
        cmd = f'ISET{int(ch)}:{val}'
        self.sendCmd(cmd)
        print(f"Sent: {cmd}")
        return
    
    # =======================================================================
    # Output Control (main functions for GUI)
    # =======================================================================
    
    def ON(self):
        """Turn output ON for both channels"""
        self.sendCmd('OUT1')
        print("✓ Output enabled")
        return
    
    def OFF(self):
        """Turn output OFF for both channels"""
        self.sendCmd('OUT0')
        print("✓ Output disabled")
        return
    
    # =======================================================================
    # Monitoring Functions (for GUI display)
    # =======================================================================
    
    def get_voltage(self, ch):
        """
        Get actual output voltage for channel.
        
        Args:
            ch: Channel number (1 or 2)
            
        Returns:
            Voltage as float (V)
        """
        try:
            response = self.sendCmd(f"VOUT{int(ch)}?")
            response = re.findall(r'[0-9.]+|\D', response)[0]
            return float(response)
        except Exception as e:
            print(f"Error reading voltage Ch{ch}: {e}")
            return 0.0
    
    def get_current(self, ch):
        """
        Get actual output current for channel.
        
        Args:
            ch: Channel number (1 or 2)
            
        Returns:
            Current as float (A) - multiply by 1000 for mA
        """
        try:
            response = self.sendCmd(f"IOUT{int(ch)}?")
            response = re.findall(r'[0-9.]+|\D', response)[0]
            return float(response)
        except Exception as e:
            print(f"Error reading current Ch{ch}: {e}")
            return 0.0
    
    def get_voltage_setpoint(self, ch):
        """Get voltage setpoint for channel"""
        try:
            response = self.sendCmd(f"VSET{int(ch)}?")
            response = re.findall(r'[0-9.]+|\D', response)[0]
            return float(response)
        except:
            return 0.0
    
    def get_current_setpoint(self, ch):
        """Get current limit setpoint for channel"""
        try:
            response = self.sendCmd(f"ISET{int(ch)}?")
            response = re.findall(r'[0-9.]+|\D', response)[0]
            return float(response)
        except:
            return 0.0
    
    def get_output_status(self):
        """
        Check if output is ON by trying to read voltage.
        If we can read voltage, output is likely on.
        """
        try:
            # Try to read output - if it responds, we're connected
            v = self.sendCmd('VOUT1?')
            if v and len(v) > 0:
                return True
            return False
        except:
            return False

    def get_status(self):
        """
        Get device status for GUI display.
        Uses individual queries instead of STATUS? command.
        
        Returns:
            Dictionary with connection and output status
        """
        if not self.connected:
            return {'connected': False}
        
        try:
            # Check if we can communicate
            v1 = self.get_voltage(1)
            v2 = self.get_voltage(2)
            
            # If voltage > 0.1V, output is probably on
            output_on = v2 > 0.1
            
            return {
                'connected': True,
                'output_on': output_on,
                'ch1_v': v1,
                'ch2_v': v2
            }
        except Exception as e:
            print(f"Error getting status: {e}")
            return {
                'connected': False,
                'output_on': False
            }
    
    # =======================================================================
    # Original Print Methods (for debugging)
    # =======================================================================
    
    def vGet(self, ch):
        """Print voltage info for channel"""
        print(f'Channel: {ch} || SetVoltage: {self.sendCmd(f"VSET{int(ch)}?")} || Actual: {self.sendCmd(f"VOUT{int(ch)}?")}')
    
    def iGet(self, ch):
        """Print current info for channel"""
        print(f'Channel: {ch} || SetCurrent: {self.sendCmd(f"ISET{int(ch)}?")} || Actual: {self.sendCmd(f"IOUT{int(ch)}?")}')
    
    def Get(self):
        """Print all info for both channels"""
        for ch in [1, 2]:
            print(f'Channel: {ch} || SetCurrent: {self.sendCmd(f"ISET{int(ch)}?")} || Actual: {self.sendCmd(f"IOUT{int(ch)}?")}')
            print(f'Channel: {ch} || SetVoltage: {self.sendCmd(f"VSET{int(ch)}?")} || Actual: {self.sendCmd(f"VOUT{int(ch)}?")}')
    
    # =======================================================================
    # System Functions
    # =======================================================================
    
    def _readDevice(self, port, baud, timeout=1):
        """Initialize serial connection"""
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self.ser.setDTR(True)
        self.ser.setRTS(True)
        time.sleep(0.2)
    
    def checkErr(self):
        """Check for errors"""
        err = self.sendCmd('ERR?')
        return err
    
    # def systemStatus(self):
    #     """
    #     Get system status.
        
    #     Returns:
    #         Dictionary with status fields
    #     """
    #     response = self.sendCmd('STATUS?')
    #     resp = {}
    #     resp['CH1'] = response[0]
    #     resp['CH2'] = response[1]
    #     resp['Tracking'] = response[2:4]
    #     resp['Beep'] = response[4]
    #     resp['Output'] = response[6]
    #     resp['BaudRate'] = response[7]
    #     return resp


# =======================================================================
# Standalone Testing
# =======================================================================

def check_devices():
    """Check for USB devices (run with sudo)"""
    print(os.system("dmesg | grep tty"))


if __name__ == '__main__':
    print("IPS-2303S SiPM Power Supply Driver Test")
    print("=" * 50)
    
    check_devices()
    
    try:
        print("\nConnecting to device...")
        device = IPS2303s()
        
        print("\nDevice Status:")
        status = device.get_status()
        print(f"  Connected: {status['connected']}")
        print(f"  Output ON: {status['output_on']}")
        
        print("\nChannel Readings:")
        device.vGet(1)
        device.iGet(1)
        device.vGet(2)
        device.iGet(2)
        
        print("\nGetting values programmatically:")
        print(f"Ch1: {device.get_voltage(1):.3f} V, {device.get_current(1)*1000:.2f} mA")
        print(f"Ch2: {device.get_voltage(2):.3f} V, {device.get_current(2)*1000:.2f} mA")
        
        print("\n✓ Connection successful!")
        
        device.close()
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()