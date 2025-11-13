# System Architecture

## Overview

The HyperK PMT Pre-Calibration Control System is a distributed architecture that separates the user interface from hardware control, enabling safe, reliable, and flexible operation of the PMT testing equipment.

## Design Philosophy

### Separation of Concerns
- **GUI Layer**: User interaction and visualization (Linux)
- **API Layer**: Device coordination and control (Windows)
- **Hardware Layer**: Direct device drivers (Windows)

### Why Distributed?
1. **Network Isolation**: GUI accessible from any browser on network
2. **Hardware Proximity**: API server runs on machine with USB/network connections to devices
3. **Safety**: Hardware control isolated from user interface
4. **Flexibility**: Can replace GUI without touching hardware control

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Operator Browser                          │
│                   http://linux-machine:8501                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ HTTPS (future)
                             │ HTTP (current)
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                Linux Machine (192.168.1.X)                       │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Streamlit GUI (hyperk_daq_gui_v4.py)                   │    │
│  │ • Run sequence controls                                 │    │
│  │ • Device monitoring                                     │    │
│  │ • Setup & configuration                                 │    │
│  │ • Waveform visualization                                │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                        │
│  ┌──────────────────────▼─────────────────────────────────┐    │
│  │ API Client (device_api_client.py)                      │    │
│  │ • HTTP request wrapper (to Windows)                     │    │
│  │ • Response handling                                     │    │
│  │ • Error management                                      │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                        │
│  ┌──────────────────────▼─────────────────────────────────┐    │
│  │ Local Device Drivers                                   │    │
│  │ • xArm robot control                                    │    │
│  │ • WaveDump DAQ control                                  │    │
│  │ • IPS2303S SiPM supply                                  │    │
│  └─────┬─────────┬─────────┬─────────┬─────────────────────┘    │
│        │         │         │         │                          │
└────────┼─────────┼─────────┼─────────┼──────────────────────────┘
         │         │         │         │
         │         │         │         │ REST API
         │         │         │         │ JSON payloads
         │         │         │         │
         │         │         │         ▼
┌────────▼─────────▼─────────▼────────────────────────────────────┐
│                  Linux Local Hardware                            │
│  • xArm 6-DOF Robot + Linear Stage (Ethernet: 192.168.1.244)   │
│  • CAEN Digitizer / WaveDump (USB)                              │
│  • IPS2303S SiPM Supply (USB/Serial)                            │
└──────────────────────────────────────────────────────────────────┘
         
         
         REST API to Windows ──────────────────────┐
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│              Windows Machine (192.168.1.100:8000)                │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ FastAPI Server (device_api_server.py)                  │    │
│  │ • HTTP endpoints                                        │    │
│  │ • Device state coordination                             │    │
│  │ • Status polling                                        │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                      │
│  ┌──────────────────────▼─────────────────────────────────┐    │
│  │ Device Drivers                                         │    │
│  │ • CAEN HV control (DT5533E)                            │    │
│  │ • Laser control (Tama LSB-200)                         │    │
│  │ • Signal generator (Siglent SDG1032X)                  │    │
│  │ • Phidget sensors                     │    │
│  └─────┬─────────┬─────────┬─────────────────────────────┘    │
│        │         │         │                                    │
└────────┼─────────┼─────────┼────────────────────────────────────┘
         │         │         │
         │         │         │
┌────────▼─────────▼─────────▼────────────────────────────────────┐
│                Windows Local Hardware                            │
│  • CAEN DT5533E HV Power Supply (COM3)                           │
│  • Tama LSB-200 Laser (USB, requires 32-bit Python)              │
│  • Siglent SDG1032X Signal Generator (LAN: 192.168.1.101)        │
│  • Phidget Sensors/Relays (USB) (future addition)                │
└──────────────────────────────────────────────────────────────────┘
```

## Component Details

### GUI Layer (Linux)

**Technology**: Streamlit
**Port**: 8501
**Responsibilities**:
- User interface rendering
- Input validation
- Status visualization
- Waveform plotting
- Progress monitoring

**Key Files**:
- `linux/gui/hyperk_daq_gui_v4.py` - Main GUI application
- `linux/api_client/device_api_client.py` - API communication

**State Management**:
- Uses Streamlit session_state for UI state
- Polls API for hardware state
- No direct hardware access

### API Layer (Windows)

**Technology**: FastAPI + Uvicorn
**Port**: 8000
**Responsibilities**:
- HTTP endpoint routing
- Background task management
- Device state coordination
- Error handling
- Status aggregation

**Key Files**:
- `windows/api_server/device_api_server.py` - Main API server
- `windows/drivers/hyperk_controller.py` - Device coordinator

**Concurrency Model**:
- Async endpoints for fast responses
- Background tasks for long-running operations (scans)
- Thread-safe device access

### Hardware Layer - Split Between Machines

#### Windows Hardware Control
**Technology**: Python device drivers  
**Responsibilities**:
- PMT high voltage control
- Laser control (TEC/LD)
- Signal generator (trigger pulses)
- Environmental monitoring

**Key Files**:
- `windows/drivers/caen_dt5533e.py` - CAEN HV power supply
- `windows/drivers/laser_tama.py` - Laser control (32-bit Python)
- `windows/drivers/siggen_sdg1032x.py` - Signal generator
- Phidget drivers - Sensors/relays (future addition)

#### Linux Hardware Control
**Technology**: Python device drivers + subprocess  
**Responsibilities**:
- Robot positioning
- Waveform acquisition (WaveDump)
- SiPM power supply

**Key Files**:
- `linux/drivers/xarm_DAQ_minimal.py` - Robot control
- WaveDump executable - CAEN digitizer control
- IPS2303S driver - SiPM supply (Operate.py or similar)

## Communication Protocols

### GUI ↔ API

**Protocol**: HTTP/REST
**Format**: JSON
**Pattern**: Request/Response + Polling

**Example Flow - Dark Current Measurement**:
```
1. GUI → API: POST /scan/dark_current
   {
     "pmt1_serial": "ZE1234",
     "pmt2_serial": "ZE5678",
     "duration": 300
   }

2. API → GUI: Response
   {
     "status": "started",
     "pmts": ["ZE1234", "ZE5678"]
   }

3. GUI polls: GET /scan/status (every 2 seconds)
   Response:
   {
     "running": true,
     "progress": 45,
     "message": "Acquiring dark current..."
   }

4. When complete: GET /scan/waveforms
   Returns waveform data for visualization
```

### API ↔ Hardware

**Communication Patterns**:

#### Linux → Windows (via REST API)
- **CAEN HV**: HTTP POST to `/caen/*` endpoints
- **Laser**: HTTP POST to `/laser/*` endpoints  
- **Signal Gen**: HTTP POST to `/siggen/*` endpoints
- **Phidget**: HTTP POST to `/phidget/*` endpoints (future addition)

#### Linux → Local Hardware (direct)
- **xArm**: TCP/IP via xArm SDK (192.168.1.244)
- **CAEN Digitizer**: Subprocess call to WaveDump executable
- **IPS2303S**: Serial commands via pyserial (/dev/ttyUSB*)

#### Windows → Local Hardware (direct)
- **CAEN DT5533E**: COM3 via CAENHVWrapper.dll
- **Laser**: USB via .NET DLL (tmHIDLD.dll, requires 32-bit Python)
- **Signal Gen**: LAN via VISA/SCPI (192.168.1.101)
- **Phidget**: USB via Phidget22 Python library (future addition)

## Data Flow

### Scan Sequence

```
1. User clicks "Start Run" in GUI (Linux)
2. GUI validates inputs (PMT serials, parameters)
3. Linux sends configuration to Windows API
4. Linux controls robot locally, coordinates with Windows for HV/Laser
5. Scan execution (coordinated between machines):
   
   Linux side:
   a. Move linear stage to PMT1 (1074mm)
   b. For each scan point:
      - Move robot to (θ, φ)
      - Configure WaveDump (channels 0,1,2,4 for PMT1)
      - Trigger acquisition locally
      - Wait for completion
      - Organize files by PMT serial
      - Update progress
   
   Windows side (via API):
   c. Set PMT voltages via CAEN HV
   d. Configure laser/signal generator for triggers
   e. Monitor device status
   
   f. Repeat for PMT2 (move stage to 240mm, channels 0,1,3,4)
   g. Return robot to home
6. GUI polls status from both local and Windows, updates progress bar
7. On completion, scan files organized by PMT serial on Linux
```

### File Organization

```
WaveDump → Temporary files (wave0.txt, wave2.txt, etc.)
           ↓
Controller → Move & rename to organized structure
           ↓
WaveDumpSaves/
├── scan_{timestamp}/
│   ├── {PMT1_SERIAL}/
│   │   └── theta{θ}_phi{φ}/
│   │       └── wave{ch}_theta{θ}_phi{φ}.txt
│   └── {PMT2_SERIAL}/
│       └── theta{θ}_phi{φ}/
```

## State Management

### API Server State
```python
status = {
    'initialized': bool,        # Hardware ready
    'scan_running': bool,       # Scan in progress
    'scan_progress': int,       # 0-100%
    'scan_message': str,        # Current operation
    'current_position': str,    # Robot position
    'linear_stage_position': int,  # mm
    'robot_position': list[float],  # Joint angles
    'waveforms': dict          # Temp storage for dark current
}
```

### GUI Session State
```python
st.session_state = {
    'mode': str,                    # 'run_sequence' or 'setup_monitor'
    'run_active': bool,             # Scan running
    'pmt_serial_number': dict,      # PMT IDs
    'device_enabled': dict,         # Device states
    'pmt_power': list[bool],        # PMT HV status
    'laser_tec_on': bool,           # Laser TEC
    'laser_ld_on': bool,            # Laser LD
    # ... other device states
}
```

## Error Handling

### Levels of Error Handling

1. **Hardware Driver Level**:
   - Device communication errors
   - Timeout handling
   - Invalid parameter checking

2. **API Server Level**:
   - HTTP error responses (400, 500 series)
   - Background task exception catching
   - Status updates on failures

3. **GUI Level**:
   - Display error messages to user
   - Disable invalid operations
   - Provide recovery options

### Error Flow Example
```
Hardware Error → Driver Exception → API catches → 
Updates status with error → GUI polls → Displays error message
```

## Safety Mechanisms

### Software Interlocks
- Laser: TEC must be on before LD
- Robot: Soft limits prevent PMT collisions
- CAEN: Valid channel configuration required

### Emergency Stop
- GUI sidebar button
- Immediate API call: POST /robot/emergency_stop
- Halts all robot motion
- Resets scan_running flag

### Status Monitoring
- Continuous polling of device states
- Visual indicators in GUI sidebar
- Warning states (yellow) for partial configurations
- Error states (red) for off/failed devices

## Scalability Considerations

### Current Limitations
- Single concurrent scan
- Synchronous device operations
- Local file storage only

### Future Enhancements
- Multiple PMT stations (parallel scans)
- Asynchronous device operations
- Database integration for metadata
- Remote file storage (cloud/network)
- Authentication/authorization
- HTTPS with proper certificates

## Network Configuration

### Current Setup
```
Linux Machine:  192.168.1.X:8501 (Streamlit)
Windows Machine: 192.168.1.100:8000 (API)
xArm Robot:     192.168.1.244
```

### Firewall Requirements
- Allow incoming on Linux:8501
- Allow incoming on Windows:8000
- Allow outgoing from Windows to robot

## Deployment Model

### Development
- Both machines on local network
- Direct file access for debugging
- Hot reload enabled

### Production
- Isolated network segment
- Systemd/Windows service for API
- Log rotation configured
- Automated backups

## Technology Stack Summary

| Component | Technology | Purpose |
|-----------|-----------|---------|
| GUI | Streamlit | Web-based interface |
| API Server | FastAPI + Uvicorn | REST API endpoints |
| HTTP Client | Requests | API communication |
| Robot Control | xArm Python SDK | Robot motion |
| DAQ | CAEN WaveDump | Waveform acquisition |
| Laser | pythonnet + .NET DLL | Laser driver interface |
| Signal Gen | PyVISA | SCPI communication |
| Sensors | Phidget22 Python | Environmental monitoring |

## Performance Characteristics

### Typical Operation Times
- Dark current check: 5 minutes (acquisition) + 10 seconds (setup)
- Full scan: ~2 hours (46 points × 5 min/point) + transitions
- Robot movement: 5-30 seconds per point
- Linear stage: 10-20 seconds per move
- CAEN configuration: <1 second

### Network Latency
- GUI → API: <50ms (local network)
- API response: <100ms (command endpoints)
- Status polling: 2 second interval

## Monitoring and Logging

### GUI Logging
- Streamlit console output
- User action history in session

### API Logging
- FastAPI access logs
- Device operation logs
- Error tracking

### Recommended Future Additions
- Centralized logging service
- Performance metrics collection
- Alert system for failures
