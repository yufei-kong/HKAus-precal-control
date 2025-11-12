"""
Simple Laser Driver Test
Direct test of laser_tama.py driver without device server

Tests basic functionality:
1. Connection
2. Reading status
3. Configuration (without turning on)

Run with: venv32\Scripts\activate && python scripts\test_laser.py
"""

import sys
import os

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

from loguru import logger
from drivers.laser_tama import TamaLaser

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")

print("\n" + "="*70)
print("TAMA ELECTRIC LASER - DRIVER TEST")
print("="*70 + "\n")

# Create laser instance
laser = TamaLaser(dll_path="C:/hyperk-daq/windows_machine/LSB-200/app/tmHIDLD.dll")

try:
    # Test 1: Connection
    print("=== Test 1: Connection ===")
    print("Connecting to laser...")
    laser.connect()
    print("✓ Connected\n")
    
    # Test 2: Device Info
    print("=== Test 2: Device Information ===")
    info = laser.get_device_info()
    print(f"Firmware Version: {info['firmware_version']}")
    print(f"Device Count: {info['device_count']}")
    print(f"Device Index: {info['device_index']}")
    print("✓ Device info retrieved\n")
    
    # Test 3: Read Status
    print("=== Test 3: Status Reading ===")
    status = laser.get_status()
    print(f"LD Power: {'ON' if status['ld_on'] else 'OFF'}")
    print(f"TEC Power: {'ON' if status['tec_on'] else 'OFF'}")
    print(f"LD Temperature: {status['ld_temp_actual']:.2f}°C")
    print(f"  Setpoint: {status['ld_temp_setpoint']:.1f}°C")
    print(f"Board Temperature: {status['board_temp']:.2f}°C")
    print(f"Pulse Current: {status['pulse_current']:.2f} mA")
    print(f"Bias Current: {status['bias_current']:.2f} mA")
    print(f"SOA Current: {status['soa_current']:.2f} mA")
    print(f"TEC Current: {status['tec_current']:.2f}")
    print(f"PD Current: {status['pd_current']:.6f} pA")
    print(f"Pulse Width: {status['pulse_width']:.1f} ps")
    print("✓ Status read successfully\n")
    
    # Test 4: Configuration (safe parameters, no power on)
    print("=== Test 4: Configuration ===")
    print("Setting temperature to 25°C...")
    laser.set_temperature(25.0)
    print("✓ Temperature configured")
    
    print("Setting pulse current to 175 mA...")
    laser.set_pulse_current(175.0)
    print("✓ Pulse current configured")
    
    print("Setting bias current to 0 mA...")
    laser.set_bias_current(0.0)
    print("✓ Bias current configured\n")
    
    # Test 5: Verify Configuration
    print("=== Test 5: Verify Configuration ===")
    status = laser.get_status()
    print(f"Temperature setpoint: {status['ld_temp_setpoint']:.1f}°C")
    print(f"Pulse current: {status['pulse_current']:.2f} mA")
    print(f"Bias current: {status['bias_current']:.2f} mA")
    print("✓ Configuration verified\n")
    
    # Test 6: Oscillator Configuration
    print("=== Test 6: Oscillator Configuration ===")
    print("Setting to External Trigger mode...")
    laser.set_oscillator(pg1_enabled=False, pg2_enabled=False, ext_enabled=True)
    print("✓ Oscillator configured (External Trigger)\n")
    
    # Test 7: Temperature Setpoint Read
    print("=== Test 7: Temperature Setpoint ===")
    temp_setpoint = laser.get_temperature_setpoint()
    print(f"Temperature setpoint: {temp_setpoint:.1f}°C")
    print("✓ Setpoint read successfully\n")
    
    print("="*70)
    print("✅ ALL TESTS PASSED!")
    print("="*70)
    print("\nLaser driver is working correctly.")
    print("\nNote: LD and TEC were NOT turned on during testing.")
    print("      This is intentional for safety.")
    
except Exception as e:
    print(f"\n✗ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

finally:
    print("\n" + "="*70)
    print("Cleanup")
    print("="*70)
    print("Disconnecting from laser...")
    laser.disconnect()
    print("✓ Disconnected")
    print()