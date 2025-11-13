# Linux Machine Setup

This directory contains the Streamlit GUI and API client for the HyperK PMT DAQ system.

## Contents

```
linux/
├── gui/
│   └── hyperk_daq_gui_v4.py       # Main Streamlit application
├── api_client/
│   └── device_api_client.py        # API communication library
├── drivers/
│   └── xarm_DAQ_minimal.py         # Shared driver code
├── configs/
│   ├── config_source_deployment.txt   # WaveDump template
│   └── dark_current_config.txt         # Dark current config
├── scripts/
│   └── [utility scripts]
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

## Requirements

- **OS**: Ubuntu 20.04+ or similar Linux distribution
- **Python**: 3.8 or higher
- **Network**: Access to Windows machine API server
- **Browser**: Modern browser (Chrome, Firefox recommended)

## Installation

### 1. Install Python Dependencies

```bash
cd linux/
pip install -r requirements.txt
```

**Key Dependencies**:
- `streamlit` - Web UI framework
- `requests` - HTTP client
- `pandas` - Data manipulation
- `numpy` - Numerical computing
- `plotly` - Interactive plotting (for waveforms)

### 2. Configure API Connection

Edit `api_client/device_api_client.py` and update the Windows machine IP:

```python
class DeviceAPI:
    def __init__(self, base_url: str = "http://192.168.1.100:8000"):
        # Change 192.168.1.100 to your Windows machine IP
```

Or set at runtime in GUI (if implemented).

## Running the GUI

### Start Streamlit

```bash
streamlit run gui/hyperk_daq_gui_v4.py
```

The GUI will be accessible at:
- Local: `http://localhost:8501`
- Network: `http://<linux-machine-ip>:8501`

### Access from Browser

Navigate to the URL displayed in terminal. The GUI should load showing the main interface.

## GUI Features

### Run Sequence Mode
- Select sequence type:
  - **Dark Current Check**: 5-minute measurement, displays waveforms
  - **Full PMT Scan**: Complete angular characterization
- Enter PMT serial numbers
- Monitor progress in real-time
- View waveforms (dark current only)

### Setup & Monitor Mode
- **Device Control**: Manual control of all equipment
  - Robot positions (Initial, Intermediate, PMT Top)
  - Linear stage (240-1074mm)
  - Laser control (TEC/LD)
  - Signal generator
  - SiPM supply
- **Status Monitoring**: Real-time device states
- **Emergency Stop**: Immediate motion halt

### Sidebar
- Device status indicators
  - 🟢 Green: Fully operational
  - 🟡 Yellow: Partial/transitioning
  - 🔴 Red: Off/failed
- System readiness check
- Emergency stop button

## Configuration Files

### WaveDump Template
`configs/config_source_deployment.txt` - Template for CAEN configuration

This file is sent to Windows machine when needed. Ensure it matches the version on Windows machine.

### Dark Current Config
`configs/dark_current_config.txt` - Preset for dark current measurements

## Troubleshooting

### Cannot Connect to API

**Symptom**: Error messages about connection refused

**Solutions**:
1. Verify Windows machine API server is running
2. Check IP address in `device_api_client.py`
3. Test connectivity: `curl http://192.168.1.100:8000/system/status`
4. Check firewall allows port 8000

### GUI Won't Start

**Symptom**: Streamlit fails to launch

**Solutions**:
1. Check Python version: `python --version` (need 3.8+)
2. Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`
3. Check port 8501 is available: `netstat -tuln | grep 8501`
4. Try different port: `streamlit run gui/hyperk_daq_gui_v4.py --server.port 8502`

### Waveforms Not Displaying

**Symptom**: Dark current completes but no waveforms shown

**Solutions**:
1. Check `/scan/waveforms` endpoint returns data
2. Verify plotly is installed: `pip install plotly`
3. Check browser console for JavaScript errors
4. Try refreshing the page

### Slow Performance

**Symptom**: GUI is sluggish or unresponsive

**Solutions**:
1. Reduce status polling frequency in code
2. Check network latency to Windows machine
3. Close other browser tabs
4. Restart Streamlit

## Development

### Running in Development Mode

```bash
# Enable auto-reload on code changes
streamlit run gui/hyperk_daq_gui_v4.py --server.runOnSave true
```

### Debug Mode

```bash
# Run with debug logging
streamlit run gui/hyperk_daq_gui_v4.py --server.enableCORS false --server.enableXsrfProtection false --logger.level debug
```

### Mock Mode

For testing without hardware:
1. Toggle "Mock Mode" in GUI settings (if implemented)
2. Or modify `device_api_client.py` to return mock data

## File Locations

### Logs
- Streamlit logs: `~/.streamlit/logs/`
- Application logs: Console output (can redirect to file)

### Cache
- Streamlit cache: `~/.streamlit/cache/`

### Config
- Streamlit config: `~/.streamlit/config.toml`

## Network Configuration

### Required Ports

| Port | Service | Direction |
|------|---------|-----------|
| 8501 | Streamlit GUI | Incoming (from browsers) |
| 8000 | API requests | Outgoing (to Windows) |

### Firewall Rules

```bash
# Allow incoming Streamlit
sudo ufw allow 8501/tcp

# Verify
sudo ufw status
```

## Production Deployment

### As Systemd Service

Create `/etc/systemd/system/hyperk-gui.service`:

```ini
[Unit]
Description=HyperK DAQ GUI
After=network.target

[Service]
Type=simple
User=<your-user>
WorkingDirectory=/path/to/linux
ExecStart=/usr/bin/streamlit run gui/hyperk_daq_gui_v4.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable hyperk-gui
sudo systemctl start hyperk-gui
```

### Using Screen/Tmux

```bash
# Start in screen session
screen -S hyperk-gui
streamlit run gui/hyperk_daq_gui_v4.py

# Detach: Ctrl+A, D
# Reattach: screen -r hyperk-gui
```

## Updating

### Update GUI Code

```bash
cd linux/
git pull  # If using git
```

Restart Streamlit (or it auto-reloads if configured).

### Update Dependencies

```bash
pip install -r requirements.txt --upgrade
```

## Security Notes

- Currently no authentication on GUI
- Recommend running on isolated network
- Do not expose port 8501 to public internet
- Future: Add authentication layer

## Performance Tips

- Close unused browser tabs
- Use modern browser (Chrome/Firefox)
- Ensure good network connection to Windows machine
- Monitor system resources (RAM, CPU)

## Known Issues

1. **Status polling may lag**: If many operations happen simultaneously
2. **Waveform plotting can be slow**: For very large waveforms (>10k points)
3. **No auto-reconnect**: Must refresh page if API connection lost

## Support

- Documentation: See `../docs/`
- API Reference: `../docs/API_REFERENCE.md`
- Contact: wihann@student.unimelb.edu.au
