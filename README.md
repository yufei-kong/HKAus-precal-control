# HyperK Australia PMT Pre-Calibration Control System

Automated PMT characterization system for Hyper-Kamiokande detector development. This system provides comprehensive control of PMT testing equipment including robotic positioning, high voltage supplies, laser systems, and data acquisition.

## Overview

This distributed control system consists of:
- **Streamlit GUI** (Linux machine) - User interface for operators
- **FastAPI Server** (Windows machine) - Device control and coordination
- **Hardware Drivers** - Direct interfaces to all test equipment

The system supports:
- Dark current measurements
- Full angular response scans (θ: 0-50°, φ: 0-360°)
- Real-time device monitoring and control
- Automated data acquisition and organization

## Quick Start

### Linux Machine (GUI)
```bash
cd linux/
pip install -r requirements.txt
streamlit run gui/hyperk_daq_gui_v4.py
```
Access GUI at: `http://localhost:8501`

### Windows Machine (API Server)
```bash
cd windows/
pip install -r requirements.txt
python api_server/device_api_server.py
```
API runs at: `http://192.168.1.100:8000`

## System Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Operator Browser                                        │
│  http://linux-machine:8501                              │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Linux Machine - Streamlit GUI + Robot Control          │
│  - hyperk_daq_gui_v4.py (GUI)                           │
│  - device_api_client.py (API client)                    │
│                                                          │
│  Local Hardware:                                        │
│  • xArm robot + linear stage (Ethernet)                 │
│  • CAEN digitizer / WaveDump (USB)                      │
│  • IPS2303S SiPM supply (USB)                           │
│  • Phidget sensors/relays (USB)                         │
└────────────────────┬─────────────────────────────────────┘
                     │ HTTP/REST API
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Windows Machine - FastAPI Server                       │
│  - device_api_server.py                                 │
│  - Hardware drivers                                     │
│                                                          │
│  Connected Hardware:                                    │
│  • CAEN DT5533E HV supply (COM3)                        │
│  • Siglent SDG1032X signal generator (LAN)              │
│  • Tama LSB-200 picosecond laser (USB)                  │
└──────────────────────────────────────────────────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture.

## Hardware

### Linux Machine
- **xArm Robot**: 6-DOF industrial robot with linear stage (240-1074mm travel)
- **CAEN Digitizer**: 8-channel waveform acquisition (WaveDump software)
- **IPS2303S**: Dual-channel SiPM bias power supply  
- **Phidget Modules**: Temperature/humidity sensors and power relays

### Windows Machine  
- **CAEN DT5533E**: 4-channel PMT high voltage power supply
- **Siglent SDG1032X**: Dual-channel arbitrary waveform generator (laser trigger)
- **Tama LSB-200**: Picosecond laser with TEC and LD control

See [docs/DEVICE_SPECIFICATIONS.md](docs/DEVICE_SPECIFICATIONS.md) for full specifications.

## Features

### Run Sequences
- **Dark Current Check**: 5-minute measurement of all PMT channels without light
- **Full PMT Scan**: Complete angular characterization of both PMTs
  - Zenith angles: 0°, 10°, 20°, 30°, 40°, 50°
  - Azimuthal angles: 0°, 90°, 180°, 270°
  - Automated channel configuration per PMT
  - Data organized by PMT serial number

### Setup & Monitor
- Real-time device status monitoring
- Manual control of all equipment
- Linear stage positioning
- Robot quick positions (Initial, Intermediate, PMT Top)
- Emergency stop capability

### Data Acquisition
- Configurable acquisition parameters (record length, duration)
- Automatic file organization by run and PMT
- Waveform visualization for dark current checks
- Progress monitoring during long scans

## API Documentation

Full API reference available at [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

### Key Endpoints

**Run Sequences:**
- `POST /scan/dark_current` - Start dark current measurement
- `POST /scan/full_scan` - Start complete angular scan
- `GET /scan/status` - Get scan progress
- `GET /scan/waveforms` - Retrieve waveform data

**Device Control:**
- `POST /robot/move_linear_stage` - Position linear stage
- `POST /robot/move_{position}` - Move to predefined positions
- `POST /caen/configure` - Configure digitizer
- `POST /laser/enable_{tec|ld}` - Control laser systems

## Project Structure

```
HKAus-precal-control/
├── linux/                  # Linux machine components
│   ├── gui/               # Streamlit GUI
│   ├── api_client/        # API client library
│   ├── drivers/           # Shared driver code
│   └── configs/           # Configuration files
│
├── windows/               # Windows machine components
│   ├── api_server/        # FastAPI server
│   ├── drivers/           # Hardware drivers
│   └── scripts/           # Test scripts
│
└── docs/                  # Documentation
    ├── ARCHITECTURE.md
    ├── DEVICE_SPECIFICATIONS.md
    ├── API_REFERENCE.md
    └── DEPLOYMENT.md
```

## File structure

```
HKAus-precal-control/
├── docs
│   ├── API_REFERENCE.md
│   ├── ARCHITECTURE.md
│   └── DEVICE_SPECIFICATIONS.md
├── linux
│   ├── api_client
│   │   └── device_api_client.py
│   ├── configs
│   │   ├── config_source_deployment.txt
│   │   ├── dark_current_config.txt
│   │   └── wavedumpconfig_template.txt
│   ├── drivers
│   │   ├── caen_digitizer_wavedump.py
│   │   ├── sipm_ips2303s.py
│   │   ├── system_coordinator.py
│   │   └── xarm_pmt_controller.py
│   ├── gui
│   │   └── hyperk_daq_gui.py
│   ├── README.md
│   ├── requirements.txt
│   └── scripts
│       ├── test_api_client.py
│       ├── test_digitizer.py
│       └── test_sipm_firmware_bug.py
├── README.md
└── windows
    ├── api_server
    │   └── device_api_server.py
    ├── drivers
    │   ├── caen_dt5533e.py
    │   ├── __init__.py
    │   ├── laser_tama.py
    │   ├── phidget_sensors.py
    │   └── siggen_sdg1032x.py
    ├── LSB-200
    │   ├── app
    │   └── manuals
    ├── pysdg1032x
    │   ├── dist
    │   ├── LICENSE.md
    │   ├── pyproject.toml
    │   ├── README.md
    │   ├── setup.cfg
    │   └── src
    ├── README.md
    ├── requirements32.txt
    └── scripts
        ├── test_caen.py
        ├── test_laser.py
        └── test_siggen.py
```

## Configuration

### Network Setup
Update IP addresses in:
- `linux/api_client/device_api_client.py` - Windows machine IP
- `windows/api_server/device_api_server.py` - xArm robot IP

### Device Configuration
- **CAEN**: Edit channel mapping in `drivers/caen_dt5533e.py`
- **Robot**: Adjust joint angles in `drivers/xarm_DAQ_minimal.py`
- **Laser**: Configure COM port in `drivers/laser_tama.py`

## Safety

- **Emergency Stop**: Available in GUI sidebar, immediately halts all motion
- **Laser Safety**: System enforces TEC-before-LD startup sequence
- **Robot Limits**: Software limits prevent collisions with PMT assembly
- **Interlock Monitoring**: Phidget sensors monitor environmental conditions

## Data Output

Data is organized as:
```
WaveDumpSaves/
├── dark_current_YYYYMMDD_HHMMSS/
│   └── wave{channel}_dark_current.txt
│
└── scan_YYYYMMDD_HHMMSS/
    ├── PMT1_SERIAL/
    │   └── theta{θ}_phi{φ}/
    │       └── wave{channel}_theta{θ}_phi{φ}.txt
    └── PMT2_SERIAL/
        └── theta{θ}_phi{φ}/
            └── wave{channel}_theta{θ}_phi{φ}.txt
```

## Development

### Testing
```bash
# Test individual drivers
cd windows/scripts/
python test_caen.py
python test_laser.py
python test_siggen.py
```

### Mock Mode
The GUI includes a mock mode for testing without hardware:
```python
# In GUI, toggle "Mock Mode" to test interface without API connection
```

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed deployment instructions.

## Requirements

### Linux Machine
- Python 3.8+
- Streamlit
- Requests
- See `linux/requirements.txt`

### Windows Machine
- Python 3.8+ (64-bit for main code)
- Python 3.8 (32-bit for laser driver)
- FastAPI, Uvicorn
- Hardware driver libraries
- See `windows/requirements.txt`

## Contributors

- Wi Han Ng (wihann@student.unimelb.edu.au)
- University of Melbourne - HyperK Australia Group

## License

[Add license information]

## Acknowledgments

Developed for the Hyper-Kamiokande experiment pre-calibration program at the University of Melbourne.
