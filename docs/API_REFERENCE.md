# API Reference

Complete reference for the HyperK PMT DAQ REST API.

**Base URL**: `http://192.168.1.100:8000`

**Format**: JSON

**Authentication**: None (internal network only)

---

## Table of Contents

1. [Scan Endpoints](#scan-endpoints)
2. [Robot Control](#robot-control)
3. [CAEN Digitizer](#caen-digitizer)
4. [Laser Control](#laser-control)
5. [Signal Generator](#signal-generator)
6. [SiPM Supply](#sipm-supply)
7. [Environmental Sensors](#environmental-sensors)
8. [System Status](#system-status)
9. [Error Handling](#error-handling)

---

## Scan Endpoints

### Start Dark Current Check

Start a dark current measurement for all PMTs without light source.

**Endpoint**: `POST /scan/dark_current`

**Request Body**:
```json
{
  "pmt1_serial": "string",
  "pmt2_serial": "string",
  "duration": 300
}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| pmt1_serial | string | Yes | PMT1 serial number |
| pmt2_serial | string | Yes | PMT2 serial number |
| duration | integer | No | Acquisition time (seconds), default: 300 |

**Response** (200 OK):
```json
{
  "status": "started",
  "pmts": ["ZE1234", "ZE5678"],
  "duration": 300
}
```

**Response** (400 Bad Request):
```json
{
  "error": "Hardware not initialized"
}
```

**Response** (409 Conflict):
```json
{
  "error": "Scan already running"
}
```

**Notes**:
- Runs in background
- Configures CAEN for channels 2, 3, 4 (PMT1, PMT2, PMT3)
- Returns waveform data for GUI visualization
- Poll `/scan/status` for progress
- Retrieve waveforms from `/scan/waveforms` when complete

---

### Start Full PMT Scan

Start complete angular characterization of both PMTs.

**Endpoint**: `POST /scan/full_scan`

**Request Body**:
```json
{
  "pmt1_serial": "string",
  "pmt2_serial": "string",
  "zeniths": [0, 10, 20, 30, 40, 50],
  "azimuths": [0, 90, 180, 270],
  "daq_runtime": 5
}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| pmt1_serial | string | Yes | PMT1 serial number |
| pmt2_serial | string | Yes | PMT2 serial number |
| zeniths | array[int] | No | Zenith angles (degrees), default: [0,10,20,30,40,50] |
| azimuths | array[int] | No | Azimuthal angles (degrees), default: [0,90,180,270] |
| daq_runtime | integer | No | Acquisition time per point (seconds), default: 5 |

**Response** (200 OK):
```json
{
  "status": "started",
  "pmts": ["ZE1234", "ZE5678"],
  "estimated_time": 7200
}
```

**Notes**:
- Runs in background
- Automatically switches between PMT1 (1074mm) and PMT2 (240mm)
- PMT1: Uses CAEN channels 0, 1, 2, 4
- PMT2: Uses CAEN channels 0, 1, 3, 4
- Skips duplicate θ=0° positions
- Files organized by PMT serial number
- Poll `/scan/status` for progress

---

### Get Scan Status

Get current scan progress and status.

**Endpoint**: `GET /scan/status`

**Response** (200 OK):
```json
{
  "running": true,
  "progress": 45,
  "message": "PMT1 - θ=20°, φ=90°",
  "position": "θ=20°, φ=90°"
}
```

**Fields**:
| Field | Type | Description |
|-------|------|-------------|
| running | boolean | True if scan in progress |
| progress | integer | Progress percentage (0-100) |
| message | string | Current operation description |
| position | string | Current robot position |

**Polling Recommendations**:
- Poll every 2 seconds during active scan
- Stop polling when `running: false`

---

### Get Waveforms

Retrieve waveform data from dark current check for GUI display.

**Endpoint**: `GET /scan/waveforms`

**Response** (200 OK):
```json
{
  "2": {
    "time": [0.0, 1.0, 2.0, ...],
    "adc": [2048, 2050, 2045, ...]
  },
  "3": {
    "time": [0.0, 1.0, 2.0, ...],
    "adc": [2050, 2048, 2052, ...]
  },
  "4": {
    "time": [0.0, 1.0, 2.0, ...],
    "adc": [2047, 2049, 2048, ...]
  }
}
```

**Notes**:
- Only available after dark current check completes
- Returns empty object `{}` if no data available
- Channel numbers as keys
- Arrays converted from numpy for JSON serialization

---

## Robot Control

### Move Linear Stage

Move linear stage to specified position.

**Endpoint**: `POST /robot/move_linear_stage`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| position | integer | Yes | Position in mm (240-1074) |

**Example**: `/robot/move_linear_stage?position=1074`

**Response** (200 OK):
```json
{
  "position": 1074,
  "code": 0
}
```

**Response** (400 Bad Request):
```json
{
  "error": "Position out of range (240-1074)"
}
```

**Notes**:
- 240mm = PMT2 position
- 1074mm = PMT1 position
- Movement takes 10-20 seconds
- Blocks until complete

---

### Move to Initial Position

Move robot to safe initial position (all joints at zero except J6).

**Endpoint**: `POST /robot/move_initial`

**Response** (200 OK):
```json
{
  "status": "At initial position"
}
```

**Joint Angles**: `[0, 0, 0, 0, 0, -135]`

---

### Move to Intermediate Position

Move robot to intermediate home position.

**Endpoint**: `POST /robot/move_intermediate`

**Response** (200 OK):
```json
{
  "status": "At intermediate position"
}
```

**Joint Angles**: `[0, -116.5, 5, 0, 0, -135]`

**Use Case**: Safe position for configuration changes, between scans

---

### Move to PMT Top

Move robot to PMT center position (θ=0°).

**Endpoint**: `POST /robot/move_pmt_top`

**Response** (200 OK):
```json
{
  "status": "At PMT top"
}
```

**Joint Angles**: `[0, -116.8, -25.2, 0, 52.0, -135]`

---

### Get Robot Position

Get current robot joint angles and position name.

**Endpoint**: `GET /robot/position`

**Response** (200 OK):
```json
{
  "joint_angles": [0.0, -116.5, 5.0, 0.0, 0.0, -135.0],
  "position_name": "Intermediate"
}
```

---

### Emergency Stop

Immediately halt all robot motion.

**Endpoint**: `POST /robot/emergency_stop`

**Response** (200 OK):
```json
{
  "status": "Emergency stop executed"
}
```

**Effect**:
- Stops robot immediately
- Cancels any running scan
- Sets `scan_running: false`
- Requires manual recovery

⚠️ **Use only in emergency situations**

---

## CAEN Digitizer

### Configure CAEN

Configure digitizer acquisition parameters.

**Endpoint**: `POST /caen/configure`

**Request Body**:
```json
{
  "run_duration": 60,
  "channels": [0, 1, 2, 4],
  "record_length": 1024
}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| run_duration | integer | Yes | Acquisition time (seconds) |
| channels | array[int] | Yes | Enabled channels (0-7) |
| record_length | integer | No | Samples per waveform, default: 1024 |

**Response** (200 OK):
```json
{
  "status": "configured",
  "config_path": "/path/to/WaveDumpConfig.txt"
}
```

**Notes**:
- Generates WaveDumpConfig.txt from template
- Must be called before data acquisition
- Automatically called by scan endpoints

---

### Start Acquisition

Manually trigger data acquisition (advanced use).

**Endpoint**: `POST /caen/acquire`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| timeout | integer | No | Max wait time (seconds), default: 70 |

**Response** (200 OK):
```json
{
  "status": "complete",
  "files": ["wave0.txt", "wave2.txt"]
}
```

**Notes**:
- Blocks until acquisition completes or timeout
- Files written to current working directory
- Use scan endpoints for normal operation

---

## Laser Control

### Enable TEC

Enable laser thermoelectric cooler.

**Endpoint**: `POST /laser/enable_tec`

**Response** (200 OK):
```json
{
  "status": "TEC enabled",
  "temperature": 25.5
}
```

**Notes**:
- Must be enabled before laser diode
- Requires ~30 seconds for thermal stabilization
- Monitor temperature via status endpoint

---

### Disable TEC

Disable laser thermoelectric cooler.

**Endpoint**: `POST /laser/disable_tec`

**Response** (200 OK):
```json
{
  "status": "TEC disabled"
}
```

**Notes**:
- Automatically disables LD if enabled

---

### Enable Laser Diode

Enable laser diode output.

**Endpoint**: `POST /laser/enable_ld`

**Response** (200 OK):
```json
{
  "status": "LD enabled",
  "current": 50.0
}
```

**Response** (400 Bad Request):
```json
{
  "error": "TEC must be enabled first"
}
```

⚠️ **Safety**: TEC must be on before LD

---

### Disable Laser Diode

Disable laser diode output.

**Endpoint**: `POST /laser/disable_ld`

**Response** (200 OK):
```json
{
  "status": "LD disabled"
}
```

---

### Set LD Current

Set laser diode drive current.

**Endpoint**: `POST /laser/set_ld_current`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| current | float | Yes | Current in mA |

**Example**: `/laser/set_ld_current?current=50.0`

**Response** (200 OK):
```json
{
  "current": 50.0,
  "status": "Current set"
}
```

---

### Get Laser Status

Get current laser state.

**Endpoint**: `GET /laser/status`

**Response** (200 OK):
```json
{
  "tec_enabled": true,
  "ld_enabled": true,
  "temperature": 25.5,
  "ld_current": 50.0
}
```

---

## Signal Generator

### Enable Output

Enable signal generator output.

**Endpoint**: `POST /siggen/enable`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| channel | integer | Yes | Channel number (1 or 2) |

**Example**: `/siggen/enable?channel=1`

**Response** (200 OK):
```json
{
  "channel": 1,
  "status": "enabled"
}
```

---

### Disable Output

Disable signal generator output.

**Endpoint**: `POST /siggen/disable`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| channel | integer | Yes | Channel number (1 or 2) |

**Response** (200 OK):
```json
{
  "channel": 1,
  "status": "disabled"
}
```

---

### Set Frequency

Set output frequency.

**Endpoint**: `POST /siggen/set_frequency`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| channel | integer | Yes | Channel number (1 or 2) |
| frequency | float | Yes | Frequency in Hz |

**Example**: `/siggen/set_frequency?channel=1&frequency=10.0`

**Response** (200 OK):
```json
{
  "channel": 1,
  "frequency": 10.0
}
```

---

### Set Amplitude

Set output amplitude.

**Endpoint**: `POST /siggen/set_amplitude`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| channel | integer | Yes | Channel number (1 or 2) |
| amplitude | float | Yes | Amplitude in V |

**Example**: `/siggen/set_amplitude?channel=1&amplitude=3.3`

**Response** (200 OK):
```json
{
  "channel": 1,
  "amplitude": 3.3
}
```

---

## SiPM Supply

### Enable Output

Enable SiPM bias voltage.

**Endpoint**: `POST /sipm/enable`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| channel | integer | Yes | Channel number (1 or 2) |

**Response** (200 OK):
```json
{
  "channel": 1,
  "status": "enabled"
}
```

---

### Disable Output

Disable SiPM bias voltage.

**Endpoint**: `POST /sipm/disable`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| channel | integer | Yes | Channel number (1 or 2) |

**Response** (200 OK):
```json
{
  "channel": 1,
  "status": "disabled"
}
```

---

### Set Voltage

Set SiPM bias voltage.

**Endpoint**: `POST /sipm/set_voltage`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| channel | integer | Yes | Channel number (1 or 2) |
| voltage | float | Yes | Voltage in V |

**Example**: `/sipm/set_voltage?channel=1&voltage=28.5`

**Response** (200 OK):
```json
{
  "channel": 1,
  "voltage": 28.5
}
```

---

## Environmental Sensors

### Get Temperature/Humidity

Get current environmental readings.

**Endpoint**: `GET /sensors/environment`

**Response** (200 OK):
```json
{
  "temperature": 22.5,
  "humidity": 45.2,
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

### Power Cycle Device

Remote power cycle via Phidget relay.

**Endpoint**: `POST /sensors/power_cycle`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| device | string | Yes | Device identifier |

**Example**: `/sensors/power_cycle?device=laser`

**Response** (200 OK):
```json
{
  "device": "laser",
  "status": "power cycled"
}
```

---

## System Status

### Get Overall Status

Get complete system status.

**Endpoint**: `GET /system/status`

**Response** (200 OK):
```json
{
  "initialized": true,
  "scan_running": false,
  "scan_progress": 0,
  "scan_message": "",
  "current_position": "Home",
  "linear_stage_position": 657,
  "robot_position": [0, -116.5, 5, 0, 0, -135],
  "devices": {
    "robot": "ready",
    "caen": "ready",
    "laser": "tec_only",
    "siggen": "off",
    "sipm": "on"
  }
}
```

---

## Error Handling

### Error Response Format

All errors return consistent format:

```json
{
  "error": "Description of error",
  "details": "Optional additional details",
  "code": "ERROR_CODE"
}
```

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 200 | Success | Request completed successfully |
| 400 | Bad Request | Invalid parameters, out of range |
| 404 | Not Found | Invalid endpoint |
| 409 | Conflict | Operation already in progress |
| 500 | Internal Error | Hardware communication failure |
| 503 | Service Unavailable | Hardware not initialized |

### Common Error Codes

| Code | Description |
|------|-------------|
| HARDWARE_NOT_INIT | Hardware not initialized at startup |
| SCAN_RUNNING | Cannot start new scan while one is running |
| DEVICE_ERROR | Device communication failure |
| INVALID_PARAMETER | Parameter out of valid range |
| SAFETY_INTERLOCK | Safety check failed (e.g., TEC before LD) |
| TIMEOUT | Operation exceeded timeout limit |

### Retry Strategy

For transient errors (500, 503):
- Retry up to 3 times
- Exponential backoff: 1s, 2s, 4s
- If still failing, alert user

For client errors (400, 409):
- Do not retry
- Fix request parameters
- Check system state

---

## Rate Limiting

**Current Implementation**: None

**Recommended**:
- Status polling: Max 1 request/second
- Control commands: No more than 10/minute
- Emergency stop: No limit

---

## API Versioning

**Current Version**: v1 (implicit)

**Future**: May add `/v1/` prefix to all endpoints

**Breaking Changes**: Will be communicated via system status endpoint

---

## WebSocket Support

**Status**: Not currently implemented

**Future Enhancement**: Real-time status updates via WebSocket
- `/ws/status` - System status stream
- `/ws/waveforms` - Live waveform data
- `/ws/scan` - Scan progress updates

---

## Authentication

**Current**: None (internal network only)

**Future Production**:
- API key authentication
- Per-user access control
- Audit logging

---

## Complete Example: Full Scan Workflow

```python
import requests
import time

base_url = "http://192.168.1.100:8000"

# 1. Check system status
status = requests.get(f"{base_url}/system/status").json()
if not status['initialized']:
    print("System not ready")
    exit()

# 2. Start full scan
response = requests.post(f"{base_url}/scan/full_scan", json={
    "pmt1_serial": "ZE1234",
    "pmt2_serial": "ZE5678",
    "zeniths": [0, 10, 20, 30, 40, 50],
    "azimuths": [0, 90, 180, 270],
    "daq_runtime": 5
})
print(response.json())

# 3. Poll for progress
while True:
    status = requests.get(f"{base_url}/scan/status").json()
    print(f"Progress: {status['progress']}% - {status['message']}")
    
    if not status['running']:
        break
    
    time.sleep(2)

print("Scan complete!")
```

---

## API Client Libraries

### Python (Recommended)

See `linux/api_client/device_api_client.py` for complete client implementation.

```python
from device_api_client import DeviceAPI

api = DeviceAPI(base_url="http://192.168.1.100:8000")

# Start scan
api.start_full_scan("ZE1234", "ZE5678")

# Get status
status = api.get_scan_status()
```

### CURL Examples

```bash
# Start dark current
curl -X POST http://192.168.1.100:8000/scan/dark_current \
  -H "Content-Type: application/json" \
  -d '{"pmt1_serial": "ZE1234", "pmt2_serial": "ZE5678", "duration": 300}'

# Get status
curl http://192.168.1.100:8000/scan/status

# Emergency stop
curl -X POST http://192.168.1.100:8000/robot/emergency_stop
```

---

## Support

For API issues or questions:
- Check system logs: `/var/log/hyperk-api.log` (if configured)
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for system design
- Contact: wihann@student.unimelb.edu.au
