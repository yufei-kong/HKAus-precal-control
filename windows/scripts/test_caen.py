"""
Test Script for CAEN DT5533E HV Power Supply
Standalone testing utility - run this to verify the driver works

Usage:
    cd C:\hyperk-daq\windows_machine
    venv\Scripts\activate
    python scripts\test_caen.py
"""

import time
from loguru import logger
import sys
import os

# Add parent directory to path so we can import drivers
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)
from drivers.caen_dt5533e import DT5533E

# Configure logger
logger.add("test_caen.log", rotation="1 day")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("CAEN DT5533E HV Power Supply Test Script")
    print("="*70)
    
    with DT5533E(com_port="COM3") as ps:
        # Configure channels 1, 2, 3 (your PMTs)
        channels = [1, 2, 3]
        voltages = [500.0, 500.0, 500.0]  # Test voltages for each channel
        
        print("\n" + "="*70)
        print("Configuring DT5533E...")
        print("="*70)
        
        for i, ch in enumerate(channels):
            print(f"\nConfiguring Channel {ch}:")
            ps.set_voltage(ch, voltages[i])
            ps.set_current_limit(ch, 350.0)
            ps.set_ramp_up(ch, 50.0)
            ps.set_ramp_down(ch, 100.0)
            ps.set_trip_time(ch, 3.0)
            print(f"  ✓ VSet={voltages[i]}V, ILimit=50µA, RampUp=50V/s, RampDown=100V/s")
        
        # Turn on
        print("\n" + "="*70)
        print("Turning ON channels...")
        print("="*70)
        for ch in channels:
            ps.set_power(ch, True)
            print(f"  ✓ Channel {ch} ON")
        
        # Monitor - loop until user confirms shutdown
        print("\nWaiting 5 seconds for ramp-up...")
        time.sleep(5)
        
        while True:
            print("\n" + "="*70)
            print("PMT Status:")
            print("="*70)
            
            # Get data for channels 1, 2, 3
            for ch in channels:
                print(f"\n📍 Channel {ch}:")
                
                v_set = ps.get_voltage_set(ch)
                v_mon = ps.get_voltage(ch)
                current = ps.get_current(ch)
                status = ps.get_status(ch)
                
                if v_set is not None:
                    print(f"   Voltage Set:  {v_set:7.1f} V")
                if v_mon is not None:
                    print(f"   Voltage Mon:  {v_mon:7.1f} V")
                if current is not None:
                    print(f"   Current:      {current:7.3f} µA")
                
                if status:
                    flags = []
                    if status['on']:
                        flags.append("ON")
                    if status['ramp_up']:
                        flags.append("Ramping ⬆")
                    if status['ramp_down']:
                        flags.append("Ramping ⬇")
                    if status['overcurrent']:
                        flags.append("⚠️ OVC")
                    if status['trip']:
                        flags.append("⚠️ TRIP")
                    if status['interlock']:
                        flags.append("🔒 INTLCK")
                    
                    if flags:
                        print(f"   Status:       {', '.join(flags)}")
            
            # Ask user if they want to turn off
            print("\n" + "="*70)
            user_input = input("Turn off all channels? (y/n): ").strip().lower()
            
            if user_input == 'y':
                print("\n" + "="*70)
                print("Turning OFF channels...")
                print("="*70)
                for ch in channels:
                    ps.set_power(ch, False)
                    print(f"  ✓ Channel {ch} OFF")
                print("\n✅ All channels OFF")
                break
            elif user_input == 'n':
                print("\n⟳ Keeping channels on. Refreshing status...")
                time.sleep(2)  # Wait a moment before showing status again
                continue
            else:
                print("⚠️ Invalid input. Please enter 'y' or 'n'")
                time.sleep(1)
    
    print("\n" + "="*70)
    print("Test Complete - Driver Disconnected")
    print("="*70 + "\n")
