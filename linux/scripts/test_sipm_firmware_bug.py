#!/usr/bin/env python3
"""
Test script to verify IPS-2303S firmware bug workaround

This script tests that the driver correctly handles the backwards
SCPI commands in the IPS-2303S firmware.

Before running:
1. Set hardware to known values (e.g., 5.0V, 1.0A on both channels)
2. Turn output OFF
3. Connect USB cable
"""

import sys
from pathlib import Path
import os

# Add paths
script_dir = Path(__file__).parent  # gui/
linux_dir = script_dir.parent        # linux/

# Add linux directory to path so we can do "import drivers.xxx"
sys.path.insert(0, str(linux_dir))

from drivers.sipm_ips2303s import IPS2303s

def test_driver():
    print("=" * 60)
    print("IPS-2303S Firmware Bug Workaround Test")
    print("=" * 60)
    
    # Expected values (set these on hardware first!)
    EXPECTED_V = 5.0
    EXPECTED_I = 1.0
    
    print(f"\nExpected hardware settings:")
    print(f"  Ch1: {EXPECTED_V}V / {EXPECTED_I}A")
    print(f"  Ch2: {EXPECTED_V}V / {EXPECTED_I}A")
    print(f"  Output: OFF")
    
    try:
        # Connect
        print("\n1. Connecting to device...")
        device = IPS2303s()
        
        # Test Ch1
        print("\n2. Testing Channel 1...")
        v1_set = device.get_voltage_setpoint(1)
        i1_set = device.get_current_setpoint(1)
        v1_act = device.get_voltage(1)
        i1_act = device.get_current(1)
        
        print(f"   Set: {v1_set:.2f}V / {i1_set:.3f}A")
        print(f"   Actual: {v1_act:.3f}V / {i1_act:.3f}A")
        
        # Test Ch2
        print("\n3. Testing Channel 2...")
        v2_set = device.get_voltage_setpoint(2)
        i2_set = device.get_current_setpoint(2)
        v2_act = device.get_voltage(2)
        i2_act = device.get_current(2)
        
        print(f"   Set: {v2_set:.2f}V / {i2_set:.3f}A")
        print(f"   Actual: {v2_act:.3f}V / {i2_act:.3f}A")
        
        # Verify
        print("\n4. Verification:")
        errors = []
        
        # Check setpoints
        if abs(v1_set - EXPECTED_V) > 0.1:
            errors.append(f"Ch1 voltage setpoint wrong: {v1_set:.2f}V (expected {EXPECTED_V}V)")
        if abs(i1_set - EXPECTED_I) > 0.1:
            errors.append(f"Ch1 current setpoint wrong: {i1_set:.3f}A (expected {EXPECTED_I}A)")
        
        if abs(v2_set - EXPECTED_V) > 0.1:
            errors.append(f"Ch2 voltage setpoint wrong: {v2_set:.2f}V (expected {EXPECTED_V}V)")
        if abs(i2_set - EXPECTED_I) > 0.1:
            errors.append(f"Ch2 current setpoint wrong: {i2_set:.3f}A (expected {EXPECTED_I}A)")
        
        # Check actuals (should be ~0 since output is OFF)
        if v1_act > 0.5:
            errors.append(f"Ch1 actual voltage too high with output OFF: {v1_act:.3f}V")
        if v2_act > 0.5:
            errors.append(f"Ch2 actual voltage too high with output OFF: {v2_act:.3f}V")
        
        if errors:
            print("\n❌ ERRORS FOUND:")
            for err in errors:
                print(f"   - {err}")
            print("\nCheck:")
            print("  1. Are hardware setpoints correct?")
            print("  2. Is output OFF?")
            print("  3. Try running device.Get() to see raw values")
        else:
            print("   ✅ All tests passed!")
        
        # Test print methods
        print("\n5. Raw command output (for debugging):")
        device.Get()
        
        device.close()
        print("\n✓ Test complete")
        
        return len(errors) == 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_driver()
    sys.exit(0 if success else 1)