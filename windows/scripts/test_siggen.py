"""
Test Script for Siglent SDG1032X Signal Generator
Standalone testing utility - run this to verify the driver works

Usage:
    cd C:\hyperk-daq\windows_machine
    venv\Scripts\activate
    python scripts\test_siggen.py
"""

import time
from loguru import logger
import sys
import os

# Add parent directory to path so we can import drivers
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)
from drivers.siggen_sdg1032x import SiglentSDG1032X

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("test_siggen.log", rotation="1 day")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("Siglent SDG1032X Signal Generator Test Script")
    print("="*70)
    
    # Create driver instance
    siggen = SiglentSDG1032X("192.168.1.101")
    
    try:
        # Connect
        print("\nConnecting to signal generator...")
        siggen.connect()
        print("✓ Connected\n")
        
        print("="*70)
        print("Configuring Channel 1 with PULSE Waveform")
        print("="*70)
        
        # Configure channel 1 with PULSE waveform (matching your working script)
        print("\nSetting parameters:")
        print("  • Waveform: PULSE")
        siggen.set_waveform(1, "PULSE")
        
        print("  • Frequency: 1 kHz")
        siggen.set_frequency(1, 1e3)
        
        print("  • Amplitude: 5.5 V")
        siggen.set_amplitude(1, 5.5)
        
        print("  • Offset: 2.0 V")
        siggen.set_offset(1, 2.0)
        
        print("  • Pulse Width: 32.6 ns")
        siggen.set_pulse_width(1, 32.6, unit='ns')
        
        print("\n✓ Channel 1 configured\n")
        
        # Read back settings
        print("="*70)
        print("Reading Channel 1 Status")
        print("="*70)
        
        status = siggen.get_status(1)
        print(f"\n  Waveform:       {status['waveform']}")
        print(f"  Frequency:      {status['frequency']:.2f} Hz")
        print(f"  Amplitude:      {status['amplitude']:.3f} V")
        print(f"  Offset:         {status['offset']:.3f} V")
        print(f"  Output:         {'ON' if status['output_enabled'] else 'OFF'}")
        
        print("\n✓ Status read successfully\n")
        
        # Enable output
        print("="*70)
        print("Enabling Output")
        print("="*70)
        
        siggen.set_output(1, True)
        print("\n✓ Output ENABLED")
        print("\n⚡ Signal generator is now outputting!")
        
        # Wait with countdown
        duration = 10
        print(f"\nOutput will remain on for {duration} seconds...")
        for i in range(duration, 0, -1):
            print(f"  {i} seconds remaining...", end='\r')
            time.sleep(1)
        print()  # New line after countdown
        
        # Disable output
        print("\n" + "="*70)
        print("Disabling Output")
        print("="*70)
        
        siggen.set_output(1, False)
        print("\n✓ Output DISABLED")
        
        print("\n" + "="*70)
        print("✅ All Tests Passed!")
        print("="*70 + "\n")
    
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        logger.exception("Test failed with exception")
        sys.exit(1)
    
    finally:
        # Cleanup
        print("Disconnecting from signal generator...")
        siggen.disconnect()
        print("✓ Disconnected\n")
