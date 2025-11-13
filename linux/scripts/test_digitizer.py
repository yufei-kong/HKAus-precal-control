#!/usr/bin/env python3
"""
Simple test script for CAEN digitizer driver.
Tests digitizer without any robot movements.
"""

import sys
import os
from pathlib import Path

# # Add drivers to path
# sys.path.insert(0, str(Path(__file__).parent / "drivers"))

# Add parent directory to path so we can import drivers
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

from drivers.caen_digitizer_wavedump import CAENDigitizerWaveDump

def main():
    print("=" * 60)
    print("CAEN Digitizer Test")
    print("=" * 60)
    
    # Initialize digitizer
    print("\n1. Initializing digitizer...")
    try:
        digitizer = CAENDigitizerWaveDump(
            wavedump_path="/home/hyperkaus/CAEN/wavedump-3.10.6-augmented/src/wavedump",
            config_template="./configs/wavedumpconfig_template.txt",
            working_dir="."  # Current directory
        )
        print("✓ Digitizer initialized")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        return False
    
    # Check status
    print("\n2. Checking digitizer status...")
    status = digitizer.get_status()
    print(f"   Connected: {status['connected']}")
    print(f"   Kernel module loaded: {status['kernel_module']}")
    print(f"   Config file exists: {status['config_exists']}")
    
    if not status['connected']:
        print("\n⚠ Digitizer not connected!")
        print("   Check: USB cable, kernel module, device presence")
        return False
    
    if not status['kernel_module']:
        print("\n⚠ Kernel module not loaded!")
        print("   Run: source sourceatstart.sh")
        return False
    
    # Configure with trigger
    print("\n3. Configuring acquisition...")
    print("   - Duration: 5 seconds")
    print("   - Channels: 2, 3, 4 (PMT1, PMT2, Monitor)")
    print("   - Trigger: Ch4, threshold=1")
    
    try:
        digitizer.configure(
            run_duration=5,
            channels=[2, 3, 4],
            trigger_channel=4,
            trigger_threshold=1,
            channel_trigger_mode="ACQUISITION_ONLY",
            record_length=1024
        )
        print("✓ Configuration written")
    except Exception as e:
        print(f"✗ Configuration failed: {e}")
        return False
    
    # Test acquisition
    print("\n4. Running acquisition (5 seconds)...")
    print("   " + "=" * 56)
    
    try:
        success = digitizer.acquire(timeout=15, show_output=False)
        
        print("   " + "=" * 56)
        if success:
            print("✓ Acquisition completed")
        else:
            print("✗ Acquisition failed")
            return False
            
    except Exception as e:
        print(f"✗ Acquisition error: {e}")
        return False
    
    # Check for waveform files
    print("\n5. Checking for waveform files...")
    waveform_files = digitizer.get_all_waveforms([2, 3, 4])
    
    if waveform_files:
        for ch, filepath in waveform_files.items():
            filesize = filepath.stat().st_size
            print(f"   Ch{ch}: {filepath.name} ({filesize:,} bytes)")
        print(f"\n   ✓ Found {len(waveform_files)} waveform files")
        print("   Note: Waveform analysis should be done offline")
    else:
        print("   ⚠ No waveform files found!")
        return False
    
    # Test file organization
    print("\n6. Organizing files...")
    try:
        save_path = digitizer.organize_files(
            save_dir="/home/hyperkaus/WaveDumpSaves/test_acquisition",
            prefix="test",
            channels=[2, 3, 4],
            include_timestamp=True
        )
        print(f"✓ Files organized to: {save_path}")
    except Exception as e:
        print(f"✗ File organization failed: {e}")
        return False
    
    # Cleanup
    print("\n7. Cleaning up temporary files...")
    digitizer.cleanup_temp_files()
    print("✓ Cleanup complete")
    
    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED!")
    print("=" * 60)
    print(f"\nData saved to: {save_path}")
    print("\nNext steps:")
    print("  - Use wavepro or other tools for waveform analysis")
    print("  - Check saved files for format and content")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)