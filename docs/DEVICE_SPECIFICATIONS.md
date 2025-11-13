# Device Specifications

Complete hardware specifications for the HyperK PMT Pre-Calibration system.

## System Overview

| Device | Model | Connection | Location | Purpose |
|--------|-------|------------|----------|---------|
| Robot | xArm 6-DOF + Linear Stage | Ethernet (TCP/IP) | Linux | PMT positioning |
| Digitizer | CAEN Digitizer (WaveDump) | USB | Linux | Waveform acquisition |
| HV Supply | CAEN DT5533E | COM3 | Windows | PMT high voltage |
| Signal Generator | Siglent SDG1032X | LAN (SCPI) | Windows | Laser trigger |
| Laser | Tama LSB-200 | USB | Windows | Light source |
| SiPM Supply | IPS2303S | USB | Linux | SiPM bias voltage |
| Sensors | Phidget Modules | USB | Windows | Environmental monitoring |

---

## xArm 6-DOF Robot + Linear Stage

### Robot Specifications
- **Model**: xArm 6 (6 degrees of freedom)
- **Reach**: [Specify reach, e.g., 700mm]
- **Payload**: [Specify payload]
- **Repeatability**: ±0.1mm
- **Connection**: Ethernet (192.168.1.244)
- **Control**: xArm Python SDK

### Linear Stage
- **Travel Range**: 240mm - 1074mm
- **Speed**: 50 mm/s
- **Positioning**: Absolute positioning mode
- **Purpose**: Switch between PMT1 (1074mm) and PMT2 (240mm)

### Robot Positions

#### Standard Positions
```python
HOME_TRUE = [0, 0, 0, 0, 0, -135]           # Initial/safe position
HOME = [0, -116.5, 5, 0, 0, -135]           # Intermediate position
PMT_TOP = [0, -116.8, -25.2, 0, 52.0, -135] # PMT center (θ=0°)
```

#### Scan Positions (head_dist = 170mm)
| Zenith (θ) | Joint Angles [J1, J2, J3, J4, J5, J6] |
|-----------|--------------------------------------|
| 0° | [0, -116.8, -25.2, 0, 52.0, -135] |
| 10° | [0, -116.5, -42.0, 0, 78.6, -135] |
| 20° | [0, -107.5, -64.3, 0, 101.9, -135] |
| 30° | [0, -88.2, -99.3, 0, 130.7, -135] |
| 40° | [0, -87.2, -64.6, 0, -70.7, 45] |
| 50° | [0, -80.2, -85.0, 0, -43.0, 45] |

**Note**: Configuration change occurs between θ=30° and θ=40° (buffer positions required)

### Buffer Positions
Used when transitioning through robot configuration change:
```python
BUFFER_1 = [0, -100.2, -99.3, 0, 130.7, -135]
BUFFER_2 = [0, -100.2, -64.6, 0, -70.7, 45]
BUFFER_3 = [0, -87.5, -55.9, 0, -87.6, 45]
```

### Azimuthal Rotation
- Achieved by rotating base joint (J1)
- Range: 0° - 360°
- Standard positions: 0°, 90°, 180°, 270°

### Safety Features
- Software limits prevent collision with PMT assembly
- Emergency stop immediately halts all motion
- Home position required before starting scans

---

## CAEN DT5533E High Voltage Power Supply

### Specifications
- **Location**: Windows Machine (COM3)
- **Purpose**: PMT high voltage control
- **Channels**: 4 (but only 3 used for PMTs)
- **Voltage Range**: 0-4000V
- **Control**: CAENHVWrapper.dll via Python

### Channel Assignment
| Channel | Device | Voltage Range |
|---------|--------|---------------|
| 1 | PMT 1 | 800-1200V typical |
| 2 | PMT 2 | 800-1200V typical |  
| 3 | PMT 3 (Monitor) | 800-1200V typical |
| 0 | Unused | - |

### Control Interface
- Voltage setpoint
- Current limit
- Ramp up/down rates
- Power on/off per channel
- Status monitoring (voltage, current, trip status)

---

## CAEN Digitizer (WaveDump)

### Specifications
- **Location**: Linux Machine (USB)
- **Software**: WaveDump 3.10.6 (augmented version)
- **Channels**: 8 (0-7)
- **Resolution**: [Specify bits, typically 12-14 bit]
- **Sampling Rate**: [Specify MHz, e.g., 500 MS/s]
- **Input Range**: [Specify voltage range]
- **Control**: Command-line executable with config file

### Channel Assignment

#### PMT1 Configuration (Linear Stage at 1074mm)
| Channel | Device | Purpose |
|---------|--------|---------|
| 0 | Trigger | Signal generator sync |
| 1 | SiPM | Silicon photomultiplier signal |
| 2 | PMT1 | Primary PMT under test |
| 3 | - | Disabled |
| 4 | PMT3 | Monitor PMT |
| 5-7 | - | Unused |

#### PMT2 Configuration (Linear Stage at 240mm)
| Channel | Device | Purpose |
|---------|--------|---------|
| 0 | Trigger | Signal generator sync |
| 1 | SiPM | Silicon photomultiplier signal |
| 2 | - | Disabled |
| 3 | PMT2 | Primary PMT under test |
| 4 | PMT3 | Monitor PMT |
| 5-7 | - | Unused |

#### Dark Current Configuration
| Channel | Device | Purpose |
|---------|--------|---------|
| 0-1 | - | Disabled |
| 2 | PMT1 | Dark current measurement |
| 3 | PMT2 | Dark current measurement |
| 4 | PMT3 | Dark current measurement |
| 5-7 | - | Disabled |

### Acquisition Parameters
- **Record Length**: 1024 samples (configurable: 256-4096)
- **Run Duration**: 5-600 seconds per point
- **Max Events**: 1,000,000 per acquisition
- **Post Trigger**: 512 samples
- **Trigger Mode**: External (from signal generator)

### Configuration File
- Template: `linux/configs/config_source_deployment.txt`
- Runtime config: Generated dynamically by controller
- Parameters modified: record length, run duration, enabled channels

---

## Siglent SDG1032X Signal Generator

### Specifications
- **Channels**: 2
- **Frequency Range**: [Specify range, e.g., 1 μHz - 30 MHz]
- **Waveforms**: Sine, square, ramp, pulse, noise, arbitrary
- **Connection**: USB (VISA/SCPI)
- **Control**: PyVISA + SCPI commands

### Usage
- **Channel 1**: Laser trigger signal
  - Waveform: Square/pulse
  - Frequency: [Specify, e.g., 10 Hz]
  - Output: Trigger to CAEN channel 0 and laser

### SCPI Commands (Examples)
```
:OUTPut1:STATe ON          # Enable output
:SOURce1:FREQuency 10      # Set 10 Hz
:SOURce1:VOLTage 3.3       # Set 3.3V amplitude
```

---

## Tama LSB-200 Picosecond Laser

### Specifications
- **Type**: Picosecond pulsed laser
- **Wavelength**: [Specify, e.g., 405 nm]
- **Pulse Width**: [Specify, e.g., <100 ps]
- **Connection**: USB Serial (COM port)
- **Control**: .NET DLL via pythonnet (requires 32-bit Python)

### Components
1. **TEC (Thermoelectric Cooler)**
   - Temperature control for laser diode
   - Must be enabled first
   - Stabilization time: ~30 seconds

2. **LD (Laser Diode)**
   - Light output
   - Can only be enabled after TEC
   - Current control for intensity

### Safety Interlocks
⚠️ **CRITICAL**: TEC must be on before enabling LD
- Software enforces this in driver and GUI
- Prevents damage to laser diode
- System prevents enabling LD if TEC is off

### Driver Details
- **Location**: `windows/drivers/laser_tama.py`
- **Requirements**: 32-bit Python 3.8
- **Dependencies**: pythonnet, Windows only
- **DLL Path**: `windows/LSB-200/app/`

### Control Interface
- Enable/disable TEC
- Enable/disable LD
- Set LD current
- Read temperature
- Monitor status

---

## IPS2303S SiPM Power Supply

### Specifications
- **Model**: RS PRO IPS-2303S
- **Location**: Linux Machine (USB/Serial)
- **Channels**: 2
- **Voltage Range**: 0-30V per channel
- **Current Range**: 0-3A per channel
- **Connection**: USB Serial (/dev/ttyUSB*)
- **Control**: Serial commands via pyserial

### Channel Assignment
- **Channel 1**: SiPM 1
- **Channel 2**: SiPM 2 (or unused)

### Usage
- Provides bias voltage for silicon photomultipliers
- Used as reference light detector
- Monitoring capability for stability checks

### Driver
- **Location**: `linux/drivers/` (Operate.py or similar)
- **Protocol**: Serial SCPI-like commands
- **Baud Rate**: 115200 or 57600

---

## Phidget Sensor Modules (not added yet)

### Temperature/Humidity Sensor
- **Model**: [Specify Phidget model]
- **Purpose**: Environmental monitoring
- **Measurements**: 
  - Temperature (°C)
  - Relative humidity (%)
- **Update Rate**: [Specify, e.g., 1 Hz]

### Power Relay
- **Model**: [Specify Phidget relay model]
- **Purpose**: Remote power cycling of devices
- **Capability**: On/off control via USB
- **Use Case**: Reset devices without physical access

### Connection
- **Protocol**: USB via Phidget22 Python library
- **Discovery**: Automatic device detection
- **Reliability**: Reconnection handling implemented

---

## Network Configuration

### IP Addresses
```
xArm Robot:      192.168.1.244
Windows Machine: 192.168.1.100:8000 (API)
Linux Machine:   192.168.1.X:8501 (GUI)
```

### Network Requirements
- Subnet: 192.168.1.0/24
- No DHCP for robot (static IP required)
- Firewall exceptions for ports 8000, 8501

---

## Power Requirements

[Add power specifications for each device]

---

## Physical Setup

### Coordinate System
- **Robot Base**: Origin reference
- **X-axis**: [Specify direction]
- **Y-axis**: [Specify direction]
- **Z-axis**: Vertical (up positive)

### PMT Geometry
- **Head Distance**: 170mm (distance from robot TCP to PMT face)
- **PMT Spacing**: 834mm (PMT1 at 1074mm, PMT2 at 240mm)
- **Confidential Parameters**: Additional geometry stored separately

### Measurement Conventions
- **Zenith (θ)**: 0° = normal incidence, 90° = edge
- **Azimuth (φ)**: 0° = reference direction, rotates in base frame

---

## Calibration Data

### Robot Calibration
- Joint offsets: Factory calibrated
- TCP offset: [Specify if custom tool defined]
- Last calibration: [Date]

### CAEN Calibration
- Channel calibration: [Method/date]
- Timing calibration: [Details]

### Laser Calibration
- Output power: [Measurement/date]
- Pulse characteristics: [Details]

---

## Maintenance Schedule

| Device | Maintenance | Frequency |
|--------|-------------|-----------|
| Robot | Lubrication check | Quarterly |
| Robot | Calibration verification | Semi-annually |
| Laser | TEC performance check | Monthly |
| CAEN | Channel calibration | Annually |
| All | Visual inspection | Weekly |

---

## Known Limitations

### Robot
- Configuration change required between θ=30° and θ=40°
- Buffer positions add ~15 seconds to scan time
- Azimuth=0° requires home approach for all zenith angles

### CAEN
- USB connection can timeout on long acquisitions (handled in driver)
- File writing is synchronous (no parallel acquisition)

### Laser
- Requires 32-bit Python (DLL limitation)
- COM port assignment can change (needs manual check)
- Thermal stabilization required before consistent output

### System
- Single concurrent scan only
- Local file storage (no network storage yet)
- Manual PMT serial number entry

---

## Future Upgrades

- [ ] Additional linear stage positions
- [ ] Automated PMT identification
- [ ] Network storage integration
- [ ] Parallel data processing
- [ ] Enhanced CAEN triggering modes
- [ ] Laser power monitoring
- [ ] Automated calibration routines
- [ ] System health monitoring from remote
- [ ] Addition of Phidget connection
