# Windows Machine Setup

This directory contains the FastAPI server and hardware drivers for the HyperK PMT DAQ system.

## Contents

```
windows/
├── api_server/
│   └── device_api_server.py        # FastAPI application
├── drivers/
│   ├── caen_dt5533e.py            # CAEN HV power supply driver
│   ├── laser_tama.py              # Tama laser driver (32-bit Python!)
│   ├── siggen_sdg1032x.py         # Signal generator driver
│   └── __init__.py
├── LSB-200/
│   ├── app/                        # Laser DLLs
│   └── manuals/
├── scripts/
│   ├── test_caen.py               # Test CAEN connection
│   ├── test_laser.py              # Test laser (32-bit Python!)
│   └── test_siggen.py             # Test signal generator
├── requirements.txt                # 64-bit Python dependencies
├── requirements32.txt              # 32-bit Python dependencies (laser only)
└── README.md                       # This file
```

## Requirements

- **OS**: Windows 10/11 (64-bit)
- **Python**: 
  - 3.8+ (64-bit) - Main application
  - 3.8 (32-bit) - Laser driver ONLY
- **Hardware**: All devices connected via USB/Ethernet
- **Network**: Static IP configuration

## Installation

### 1. Install Python (64-bit) - Main Environment

Download from python.org and install 64-bit version.

```cmd
cd windows\
pip install -r requirements.txt
```

**Key Dependencies**:
- `fastapi` - API framework
- `uvicorn` - ASGI server
- `pyvisa` - SCPI instrument communication (signal generator)
- `pythonnet` - .NET interop (for laser)

### 2. Install Python (32-bit) - Laser Only

**CRITICAL**: Tama laser driver requires 32-bit Python due to DLL architecture.

1. Download Python 3.8 (32-bit) from python.org
2. Install to `C:\Python38-32\` (or similar)
3. Install dependencies:

```cmd
C:\Python38-32\python.exe -m pip install -r requirements32.txt
```

**Laser Dependencies**:
- `pythonnet` - .NET interop
- `numpy` - Array handling

### 3. Install Device Drivers

#### CAEN DT5533E HV Supply
- Download and install CAEN HV software
- Install CAENHVWrapper.dll (should be in drivers/ folder)
- Connect via COM3 (or note your COM port)

#### Siglent SDG1032X
- Install NI-VISA or Keysight IO Libraries
- Verify device appears in VISA Device Manager
- Note device IP address for configuration

#### Tama Laser
- No driver installation needed (uses USB HID)
- Requires .NET Framework 4.0+
- DLL files in LSB-200/app/ folder

## Configuration

### 1. Network Setup

Set static IP for Windows machine:
```
IP: 192.168.1.100
Subnet: 255.255.255.0
Gateway: 192.168.1.1
```

Verify robot connectivity:
```cmd
ping 192.168.1.244
```

### 2. Update API Server Configuration

Edit `api_server/device_api_server.py`:

```python
# Line ~35: Update xArm IP
arm = XArmAPI('192.168.1.244')  # Change if needed

# Line ~42: Update WaveDump path
wavedump_path="C:/CAEN/wavedump-3.10.6-augmented/src/wavedump"

# Line ~43: Update config template path
config_template="./config_source_deployment.txt"
```

### 3. Configure Laser Driver

Edit `drivers/laser_tama.py`:

```python
# Update COM port (check in Device Manager)
self.port = "COM3"  # Change to your port

# Update DLL path if needed
dll_path = "LSB-200/app/tmHIDLD.dll"
```

**Finding COM Port**:
1. Open Device Manager
2. Expand "Ports (COM & LPT)"
3. Look for USB Serial Device
4. Note COM number (e.g., COM3, COM4)

### 4. Configure CAEN

Edit template: `config_source_deployment.txt`

Update channel enable lines (around line 143-191) if your hardware has different channel assignments.

## Running the API Server

### Start Server

```cmd
cd windows\
python api_server\device_api_server.py
```

Server will start at: `http://192.168.1.100:8000`

Verify startup in console:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
✓ Hardware initialized
```

### Access API Documentation

While server is running, visit:
- Swagger UI: `http://192.168.1.100:8000/docs`
- ReDoc: `http://192.168.1.100:8000/redoc`

### Stop Server

Press `Ctrl+C` in terminal.

## Testing Hardware

Test each device individually before running full system.

### Test CAEN Digitizer

```cmd
python scripts\test_caen.py
```

Expected output:
```
✓ CAEN connection OK
✓ Configuration generated
✓ Test acquisition complete
```

### Test Laser (32-bit Python!)

```cmd
C:\Python38-32\python.exe scripts\test_laser.py
```

Expected output:
```
✓ Laser DLL loaded
✓ TEC enabled
✓ LD enabled
✓ Laser test complete
```

### Test Signal Generator

```cmd
python scripts\test_siggen.py
```

Expected output:
```
✓ Signal generator found: SIGLENT,SDG1032X,...
✓ Output enabled
✓ Frequency set to 10 Hz
```

## Troubleshooting

### API Server Won't Start

**Symptom**: Error on startup

**Solutions**:
1. Check port 8000 is available:
   ```cmd
   netstat -an | find "8000"
   ```
2. Verify Python version: `python --version` (should be 3.8+ 64-bit)
3. Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`
4. Check hardware connections (USB devices plugged in)

### xArm Connection Failed

**Symptom**: "Cannot connect to robot at 192.168.1.244"

**Solutions**:
1. Verify robot is powered on
2. Check network cable connection
3. Ping robot: `ping 192.168.1.244`
4. Verify IP is correct in config
5. Check firewall isn't blocking connection

### CAEN Not Working

**Symptom**: WaveDump errors or timeouts

**Solutions**:
1. Verify USB connection
2. Check WaveDump path in config
3. Test manually:
   ```cmd
   C:\CAEN\wavedump\wavedump.exe config.txt
   ```
4. Update CAEN drivers from caen.it

### Laser Driver Issues

**Symptom**: DLL load errors or COM port errors

**Solutions**:
1. **CRITICAL**: Must use 32-bit Python!
   ```cmd
   C:\Python38-32\python.exe --version
   ```
   Should show "32 bit"

2. Verify DLL path exists:
   ```cmd
   dir LSB-200\app\LSB200_NET.dll
   ```

3. Check COM port in Device Manager

4. Install .NET Framework 4.7.2+ if not present

5. Run as Administrator (DLL loading sometimes requires elevation)

### Signal Generator Not Found

**Symptom**: VISA errors or device not found

**Solutions**:
1. Install VISA libraries (NI-VISA or Keysight)
2. Open NI MAX or Keysight Connection Expert
3. Verify device is detected
4. Note VISA resource string (e.g., `USB0::0xF4EC::...::INSTR`)
5. Update in driver if needed

### Phidget Connection Issues

**Symptom**: Device not found errors

**Solutions**:
1. Install Phidget22 drivers
2. Open Phidget Control Panel
3. Verify devices are detected
4. Check USB hub is powered (if using hub)

## Production Deployment

### As Windows Service

Use NSSM (Non-Sucking Service Manager):

1. Download NSSM from nssm.cc
2. Install service:
   ```cmd
   nssm install HyperKAPI "C:\Python38\python.exe" "C:\path\to\api_server\device_api_server.py"
   ```
3. Configure:
   ```cmd
   nssm set HyperKAPI AppDirectory C:\path\to\windows
   nssm set HyperKAPI Start SERVICE_AUTO_START
   ```
4. Start service:
   ```cmd
   nssm start HyperKAPI
   ```

### Using Task Scheduler

Alternative to Windows Service:
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: At startup
4. Action: Start program
   - Program: `python.exe`
   - Arguments: `api_server\device_api_server.py`
   - Start in: `C:\path\to\windows`

### Startup Script

Create `start_server.bat`:
```batch
@echo off
cd C:\path\to\windows
python api_server\device_api_server.py
pause
```

Place shortcut in Startup folder: `shell:startup`

## File Locations

### Logs
- API Server: Console output (redirect to file if needed)
- WaveDump output: Current working directory

### Data Output
- Default: `../WaveDumpSaves/`
- Configure in hyperk_controller.py

### Config Files
- WaveDump template: `config_source_deployment.txt`
- Generated config: `WaveDumpConfig.txt` (temporary)

## Performance Tips

- Use SSD for WaveDump data output
- Close unnecessary programs during scans
- Disable Windows Update during measurements
- Use wired network (not WiFi) for robot
- Keep antivirus exceptions for working directories

## Security Notes

- API server listens on all interfaces (0.0.0.0)
- No authentication currently implemented
- Recommend isolated network
- Add firewall rules to limit access:
  ```cmd
  netsh advfirewall firewall add rule name="HyperK API" dir=in action=allow protocol=TCP localport=8000
  ```

## Known Issues

1. **Laser requires 32-bit Python**: Cannot use main environment
2. **WaveDump timeout on long acquisitions**: Handled in driver with retry
3. **Phidget reconnection**: May need power cycle if connection lost
4. **Linear stage initialization**: Requires homing on first power-on

## Maintenance

### Weekly Checks
- Verify all USB devices connected
- Test emergency stop
- Check disk space for data storage

### Monthly Checks
- Test all individual drivers (scripts/)
- Verify robot calibration
- Check laser temperature stability

### Updates

```cmd
# Update Python packages
pip install -r requirements.txt --upgrade

# Update xArm SDK
pip install xarm-python-sdk --upgrade
```

## Development

### Add New Device Driver

1. Create driver in `drivers/new_device.py`
2. Implement standard interface:
   ```python
   class NewDevice:
       def __init__(self):
           pass
       
       def connect(self):
           pass
       
       def disconnect(self):
           pass
       
       def get_status(self):
           pass
   ```
3. Add to `device_api_server.py`
4. Create test script in `scripts/`

### Debug Mode

Run with verbose logging:
```cmd
python api_server\device_api_server.py --log-level debug
```

## Support

- Documentation: See `../docs/`
- API Reference: `../docs/API_REFERENCE.md`
- Hardware Specs: `../docs/DEVICE_SPECIFICATIONS.md`
- Contact: wihann@student.unimelb.edu.au
