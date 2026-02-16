"""
Test Script for Windows Device API Client
Tests cross-machine communication for CAEN HV, Signal Generator, and Laser

Usage:
    cd ~/hyperk-daq/linux_machine
    source venv/bin/activate
    python scripts/test_api_client.py
"""

from loguru import logger
import sys
import os

# Add parent directory to path so we can import drivers
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

from api_client.device_api_client import WindowsDeviceClient

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("test_api_client.log", rotation="1 day")

def test_caen(client):
    """Test CAEN HV control"""
    print("\n=== Testing CAEN HV ===")
    try:
        # Configure channel 1
        print("Setting channel 1 to 1000V...")
        client.caen_configure_channel(
            channel=1,
            voltage=1000.0,
            current_limit=300.0,
            ramp_up=50.0,
            ramp_down=100.0
        )
        print("✓ Configuration sent")
        
        # Read back status
        print("\nReading channel 1 status...")
        ch1_status = client.caen_get_status(1)
        print(f"  Voltage: {ch1_status['voltage_mon']:.1f}V (set: {ch1_status['voltage_set']:.1f}V)")
        print(f"  Current: {ch1_status['current_mon']:.3f}µA")
        print(f"  Power: {'ON' if ch1_status['power_on'] else 'OFF'}")
        
        # Get all channels
        print("\nAll channels:")
        all_channels = client.caen_get_all_channels()
        for ch in all_channels:
            if "error" not in ch:
                print(f"  Ch{ch['channel']}: {ch['voltage_mon']:.1f}V, "
                      f"{ch['current_mon']:.3f}µA, "
                      f"{'ON' if ch['power_on'] else 'OFF'}")
        
        print("\n✓ CAEN HV tests passed")
        return True
    
    except Exception as e:
        print(f"\n✗ CAEN HV test failed: {e}")
        logger.exception("CAEN test failed")
        return False

def test_siggen(client):
    """Test signal generator control"""
    print("\n=== Testing Signal Generator ===")
    try:
        # Configure PULSE waveform
        print("Setting channel 1 to 1kHz PULSE wave...")
        client.siggen_set_waveform(
            channel=1,
            waveform="PULSE",
            frequency=1e3,
            amplitude=5.5,
            offset=2.0,
            pulse_width=32.6,
            pulse_width_unit='ns'
        )
        print("✓ Configuration sent")
        
        # Read back status
        print("\nReading channel 1 status...")
        sg_status = client.siggen_get_status(1)
        print(f"  Waveform: {sg_status['waveform']}")
        print(f"  Frequency: {sg_status['frequency']:.1f} Hz")
        print(f"  Amplitude: {sg_status['amplitude']:.2f} V")
        print(f"  Offset: {sg_status['offset']:.2f} V")
        print(f"  Output: {'ON' if sg_status['output_enabled'] else 'OFF'}")
        
        print("\n✓ Signal generator tests passed")
        return True
    
    except Exception as e:
        print(f"\n✗ Signal generator test failed: {e}")
        logger.exception("Signal generator test failed")
        return False

def test_laser(client):
    """Test laser control"""
    print("\n=== Testing Laser ===")
    try:
        # Get initial status
        print("Reading laser status...")
        status = client.laser_get_status()
        print(f"  LD Power: {'ON' if status['ld_on'] else 'OFF'}")
        print(f"  TEC Power: {'ON' if status['tec_on'] else 'OFF'}")
        print(f"  LD Temperature: {status['ld_temp_actual']:.2f}°C")
        print(f"  Board Temperature: {status['board_temp']:.2f}°C")
        print(f"  Pulse Current: {status['pulse_current']:.2f} mA")
        print(f"  Firmware: {status['device_info']['firmware_version']}")
        
        # Configure parameters (without turning on)
        print("\nConfiguring laser parameters...")
        client.laser_configure(
            temperature=25.0,
            pulse_current=175.0,
            bias_current=0.0
        )
        print("✓ Configuration sent")
        
        # Set oscillator
        # print("\nConfiguring oscillator to PG1 @ 1MHz...")
        print("\nConfiguring oscillator to EXT")
        client.laser_set_oscillator(
            pg1_enabled=False,
            pg2_enabled=False,
            ext_enabled=True,
            # pg1_frequency=1_000_000
        )
        print("✓ Oscillator configured")
        
        # Verify configuration
        print("\nVerifying configuration...")
        status = client.laser_get_status()
        print(f"  Temperature setpoint: {status['ld_temp_setpoint']:.1f}°C")
        print(f"  Pulse current: {status['pulse_current']:.2f} mA")
        print(f"  Bias current: {status['bias_current']:.2f} mA")
        
        # Ensure laser is off (safety)
        print("\nEnsuring laser is OFF (safety check)...")
        client.laser_emergency_off()
        print("✓ Laser confirmed OFF")
        
        print("\n✓ Laser tests passed")
        print("\nNote: Laser was not turned ON during testing for safety.")
        print("      Use GUI for actual laser operation.")
        return True
    
    except Exception as e:
        print(f"\n✗ Laser test failed: {e}")
        logger.exception("Laser test failed")
        return False

if __name__ == "__main__":
    print("\n" + "="*70)
    print("Windows Device API Client Test Script")
    print("="*70)
    
    # Initialize client
    client = WindowsDeviceClient("192.168.0.186")
    
    # Test connection
    print("\n=== Testing Connection ===")
    if client.check_connection():
        print("✓ Server connection OK")
    else:
        print("✗ Server connection failed")
        sys.exit(1)
    
    print("\n=== Server Status ===")
    status = client.get_server_status()
    print(f"Server: {status['server']}")
    print(f"Python: {status.get('python_architecture', 'unknown')}")
    print(f"Devices: {status['devices']}")
    
    # Run device tests
    results = {}
    
    if status['devices'].get('caen_dt5533e') == 'connected':
        results['CAEN HV'] = test_caen(client)
    else:
        print("\n⊘ Skipping CAEN HV tests (not connected)")
        results['CAEN HV'] = None
    
    if status['devices'].get('siglent_sdg1032x') == 'connected':
        results['Signal Generator'] = test_siggen(client)
    else:
        print("\n⊘ Skipping Signal Generator tests (not connected)")
        results['Signal Generator'] = None
    
    if status['devices'].get('tama_laser') == 'connected':
        results['Laser'] = test_laser(client)
    else:
        print("\n⊘ Skipping Laser tests (not connected)")
        results['Laser'] = None
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for device, result in results.items():
        if result is None:
            status_str = "⊘ SKIPPED"
        elif result:
            status_str = "✓ PASS"
        else:
            status_str = "✗ FAIL"
        print(f"{status_str:12s} {device}")
    
    # Count results
    tested = [r for r in results.values() if r is not None]
    if tested:
        passed = sum(tested)
        total = len(tested)
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n🎉 ALL TESTS PASSED!")
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
    else:
        print("\n⚠️  No devices available for testing")
    
    print("="*70 + "\n")