"""
FastAPI Device Server for Windows Machine
Exposes CAEN DT5533E HV Power Supply, Siglent SDG1032X Signal Generator, and Tama Laser

CRITICAL: This server MUST be run with 32-bit Python to support the Tama laser driver.

Run with: venv32\Scripts\activate && python device_server.py
Server will be available at: http://192.168.0.186:8000
API docs at: http://192.168.0.186:8000/docs
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import uvicorn
from loguru import logger
import sys
import os

# Add parent directory to path so we can import drivers
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

# Import device drivers
from drivers.caen_dt5533e import DT5533E
try:
    from drivers.siggen_sdg1032x import SiglentSDG1032X
    SIGGEN_AVAILABLE = True
except ImportError:
    logger.warning("Signal generator driver not available, endpoints will be disabled")
    SIGGEN_AVAILABLE = False

try:
    from drivers.laser_tama import TamaLaser
    LASER_AVAILABLE = True
except ImportError:
    logger.warning("Laser driver not available, endpoints will be disabled")
    LASER_AVAILABLE = False

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("device_server.log", rotation="10 MB", level="DEBUG")

# Verify 32-bit Python
import struct
if struct.calcsize("P") * 8 != 32:
    logger.error("⚠️  This server requires 32-bit Python for laser driver compatibility!")
    logger.error("   Current Python is 64-bit. Please use venv32 instead.")
    if not LASER_AVAILABLE:
        logger.warning("   Continuing without laser support...")
    else:
        logger.error("   Laser driver will fail! Exiting...")
        sys.exit(1)
else:
    logger.success("✓ Running with 32-bit Python")

# Device instances (global)
caen_ps: Optional[DT5533E] = None
sig_gen: Optional[Any] = None
laser: Optional[Any] = None

# Configuration
CAEN_COM_PORT = "COM3"
SIGGEN_IP = "192.168.1.101"
LASER_DLL_PATH = "C:/hyperk-daq/windows_machine/LSB-200/app/tmHIDLD.dll"


# ============================================================================
# Pydantic Models
# ============================================================================

class CAENChannelControl(BaseModel):
    """Model for CAEN channel control commands"""
    channel: int = Field(..., ge=0, le=3, description="Channel number (0-3)")
    voltage: Optional[float] = Field(None, ge=0, le=4000, description="Voltage setpoint (V)")
    current_limit: Optional[float] = Field(None, ge=0, le=3000, description="Current limit (µA)")
    power_on: Optional[bool] = Field(None, description="Power state")
    ramp_up: Optional[float] = Field(None, ge=1, le=500, description="Ramp up rate (V/s)")
    ramp_down: Optional[float] = Field(None, ge=1, le=500, description="Ramp down rate (V/s)")


class CAENChannelStatus(BaseModel):
    """Model for CAEN channel status response"""
    channel: int
    voltage_set: float
    voltage_mon: float
    current_set: float
    current_mon: float
    power_on: bool
    ramp_up: float
    ramp_down: float
    status: Optional[Dict[str, Any]] = None


class SigGenWaveform(BaseModel):
    """Model for signal generator waveform configuration"""
    channel: int = Field(..., ge=1, le=2, description="Channel number (1-2)")
    waveform: str = Field(..., description="Waveform type: SINE, SQUARE, RAMP, PULSE, NOISE, ARB, DC")
    frequency: Optional[float] = Field(None, gt=0, description="Frequency in Hz")
    amplitude: Optional[float] = Field(None, gt=0, description="Amplitude in V")
    offset: Optional[float] = Field(None, description="Offset in V")
    phase: Optional[float] = Field(None, ge=0, le=360, description="Phase in degrees")
    pulse_width: Optional[float] = Field(None, gt=0, description="Pulse width (for PULSE waveform)")
    pulse_width_unit: Optional[str] = Field('ns', description="Pulse width unit: 's', 'ms', 'us', 'ns'")


class SigGenOutput(BaseModel):
    """Model for signal generator output control"""
    channel: int = Field(..., ge=1, le=2, description="Channel number (1-2)")
    enabled: bool = Field(..., description="Output state")


class LaserPowerControl(BaseModel):
    """Model for laser power control"""
    ld_enabled: Optional[bool] = Field(None, description="Laser diode ON/OFF")
    tec_enabled: Optional[bool] = Field(None, description="Temperature control ON/OFF")


class LaserConfiguration(BaseModel):
    """Model for laser configuration"""
    temperature: Optional[float] = Field(None, ge=0, le=40, description="Target temperature (°C)")
    pulse_current: Optional[float] = Field(None, ge=0, le=200, description="Pulse current (mA)")
    bias_current: Optional[float] = Field(None, ge=0, le=200, description="Bias current (mA)")
    soa_current: Optional[float] = Field(None, ge=0, le=300, description="SOA current (mA)")


class LaserOscillator(BaseModel):
    """Model for laser oscillator control"""
    pg1_enabled: Optional[bool] = Field(None, description="PG1 oscillator (100kHz-250MHz)")
    pg2_enabled: Optional[bool] = Field(None, description="PG2 oscillator (3kHz-200kHz)")
    ext_enabled: Optional[bool] = Field(None, description="External trigger")
    pg1_frequency: Optional[int] = Field(None, ge=100_000, le=250_000_000, description="PG1 frequency (Hz)")
    pg2_frequency: Optional[int] = Field(None, ge=3_000, le=200_000, description="PG2 frequency (Hz)")


# ============================================================================
# Lifespan Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup device connections"""
    global caen_ps, sig_gen, laser
    
    logger.info("Initializing device connections...")
    
    # Initialize CAEN power supply
    try:
        caen_ps = DT5533E(com_port=CAEN_COM_PORT)
        caen_ps.connect()
        logger.info(f"✓ CAEN DT5533E connected on {CAEN_COM_PORT}")
    except Exception as e:
        logger.error(f"✗ Failed to connect CAEN DT5533E: {e}")
        caen_ps = None
    
    # Initialize signal generator
    if SIGGEN_AVAILABLE:
        try:
            sig_gen = SiglentSDG1032X(SIGGEN_IP)
            sig_gen.connect()
            logger.info(f"✓ Siglent SDG1032X connected at {SIGGEN_IP}")
        except Exception as e:
            logger.error(f"✗ Failed to connect signal generator: {e}")
            sig_gen = None
    
    # Initialize laser
    if LASER_AVAILABLE:
        try:
            laser = TamaLaser(dll_path=LASER_DLL_PATH)
            laser.connect()
            logger.info(f"✓ Tama Laser connected")
        except Exception as e:
            logger.error(f"✗ Failed to connect laser: {e}")
            laser = None
    
    yield
    
    # Cleanup
    logger.info("Shutting down device connections...")
    
    if caen_ps:
        try:
            caen_ps.disconnect()
            logger.info("CAEN DT5533E disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting CAEN: {e}")
    
    if sig_gen:
        try:
            sig_gen.disconnect()
            logger.info("Signal generator disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting signal generator: {e}")
    
    if laser:
        try:
            laser.disconnect()
            logger.info("Laser disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting laser: {e}")


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="HyperK DAQ Device Server",
    description="Control interface for CAEN DT5533E, Siglent SDG1032X, and Tama Laser",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for cross-machine communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify Linux machine IP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health Check
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with server status"""
    return {
        "status": "online",
        "server": "HyperK DAQ Device Server",
        "version": "2.0.0",
        "python_architecture": f"{struct.calcsize('P') * 8}-bit",
        "devices": {
            "caen_dt5533e": caen_ps is not None,
            "siglent_sdg1032x": sig_gen is not None,
            "tama_laser": laser is not None
        }
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    health = {
        "server": "healthy",
        "devices": {}
    }
    
    # Check CAEN
    if caen_ps:
        try:
            caen_ps.get_voltage(1)
            health["devices"]["caen_dt5533e"] = "connected"
        except Exception as e:
            health["devices"]["caen_dt5533e"] = f"error: {str(e)}"
    else:
        health["devices"]["caen_dt5533e"] = "not_initialized"
    
    # Check signal generator
    if sig_gen:
        health["devices"]["siglent_sdg1032x"] = "connected"
    else:
        health["devices"]["siglent_sdg1032x"] = "not_initialized"
    
    # Check laser
    if laser:
        try:
            laser.get_status()
            health["devices"]["tama_laser"] = "connected"
        except Exception as e:
            health["devices"]["tama_laser"] = f"error: {str(e)}"
    else:
        health["devices"]["tama_laser"] = "not_initialized"
    
    return health


# ============================================================================
# CAEN DT5533E Endpoints
# ============================================================================

@app.post("/caen/channel/control")
async def caen_control_channel(cmd: CAENChannelControl):
    """Control CAEN power supply channel parameters"""
    if not caen_ps:
        raise HTTPException(status_code=503, detail="CAEN power supply not connected")
    
    try:
        ch = cmd.channel
        
        if cmd.voltage is not None:
            caen_ps.set_voltage(ch, cmd.voltage)
            logger.info(f"CAEN Ch{ch}: Set voltage to {cmd.voltage}V")
        
        if cmd.current_limit is not None:
            caen_ps.set_current_limit(ch, cmd.current_limit)
            logger.info(f"CAEN Ch{ch}: Set current limit to {cmd.current_limit}µA")
        
        if cmd.ramp_up is not None:
            caen_ps.set_ramp_up(ch, cmd.ramp_up)
            logger.info(f"CAEN Ch{ch}: Set ramp up to {cmd.ramp_up}V/s")
        
        if cmd.ramp_down is not None:
            caen_ps.set_ramp_down(ch, cmd.ramp_down)
            logger.info(f"CAEN Ch{ch}: Set ramp down to {cmd.ramp_down}V/s")
        
        if cmd.power_on is not None:
            caen_ps.set_power(ch, cmd.power_on)
            logger.info(f"CAEN Ch{ch}: Power {'ON' if cmd.power_on else 'OFF'}")
        
        return {"status": "success", "channel": ch}
    
    except Exception as e:
        logger.error(f"CAEN control error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/caen/channel/{channel}/status")
async def caen_get_channel_status(channel: int) -> CAENChannelStatus:
    """Get CAEN channel status and measurements"""
    if not caen_ps:
        raise HTTPException(status_code=503, detail="CAEN power supply not connected")
    
    if channel < 0 or channel > 3:
        raise HTTPException(status_code=400, detail="Channel must be 0-3")
    
    try:
        status = caen_ps.get_channel_full_status(channel)
        
        if status is None:
            raise HTTPException(status_code=500, detail="Failed to read channel status")
        
        return CAENChannelStatus(
            channel=channel,
            voltage_set=status["VSet"],
            voltage_mon=status["VMon"],
            current_set=status["ISet"],
            current_mon=status["IMon"],
            power_on=status["Pw"] == 1,
            ramp_up=status["RUp"],
            ramp_down=status["RDwn"],
            status=status["Status"]
        )
    
    except Exception as e:
        logger.error(f"CAEN status read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/caen/channels/status")
async def caen_get_all_channels():
    """Get status for all CAEN channels"""
    if not caen_ps:
        raise HTTPException(status_code=503, detail="CAEN power supply not connected")
    
    try:
        channels = []
        for ch in range(4):
            try:
                status = caen_ps.get_channel_full_status(ch)
                if status is None:
                    channels.append({"channel": ch, "error": "Could not read channel"})
                    continue
                    
                channels.append({
                    "channel": ch,
                    "voltage_mon": status["VMon"],
                    "current_mon": status["IMon"],
                    "power_on": status["Pw"] == 1,
                    "status": status["Status"]
                })
            except Exception as e:
                logger.warning(f"Could not read channel {ch}: {e}")
                channels.append({"channel": ch, "error": str(e)})
        
        return {"channels": channels}
    
    except Exception as e:
        logger.error(f"CAEN multi-channel read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/caen/emergency_off")
async def caen_emergency_off():
    """Emergency shutdown - turn off all channels"""
    if not caen_ps:
        raise HTTPException(status_code=503, detail="CAEN power supply not connected")
    
    try:
        for ch in range(4):
            try:
                caen_ps.set_power(ch, False)
                logger.warning(f"EMERGENCY OFF: Channel {ch}")
            except Exception as e:
                logger.error(f"Failed to turn off channel {ch}: {e}")
        
        return {"status": "emergency_shutdown_complete"}
    
    except Exception as e:
        logger.error(f"Emergency shutdown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Signal Generator Endpoints
# ============================================================================

if SIGGEN_AVAILABLE:
    
    @app.post("/siggen/waveform")
    async def siggen_set_waveform(config: SigGenWaveform):
        """Configure signal generator waveform"""
        if not sig_gen:
            raise HTTPException(status_code=503, detail="Signal generator not connected")
        
        try:
            ch = config.channel
            
            # Set waveform type
            sig_gen.set_waveform(ch, config.waveform)
            logger.info(f"SigGen Ch{ch}: Waveform set to {config.waveform}")
            
            # Set parameters if provided
            if config.frequency is not None:
                sig_gen.set_frequency(ch, config.frequency)
                logger.info(f"SigGen Ch{ch}: Frequency set to {config.frequency} Hz")
            
            if config.amplitude is not None:
                sig_gen.set_amplitude(ch, config.amplitude)
                logger.info(f"SigGen Ch{ch}: Amplitude set to {config.amplitude} V")
            
            if config.offset is not None:
                sig_gen.set_offset(ch, config.offset)
                logger.info(f"SigGen Ch{ch}: Offset set to {config.offset} V")
            
            if config.phase is not None:
                sig_gen.set_phase(ch, config.phase)
                logger.info(f"SigGen Ch{ch}: Phase set to {config.phase}°")
            
            if config.pulse_width is not None:
                unit = config.pulse_width_unit or 'ns'
                sig_gen.set_pulse_width(ch, config.pulse_width, unit=unit)
                logger.info(f"SigGen Ch{ch}: Pulse width set to {config.pulse_width}{unit}")
            
            return {"status": "success", "channel": ch}
        
        except Exception as e:
            logger.error(f"Signal generator config error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    
    @app.post("/siggen/output")
    async def siggen_set_output(cmd: SigGenOutput):
        """Enable/disable signal generator output"""
        if not sig_gen:
            raise HTTPException(status_code=503, detail="Signal generator not connected")
        
        try:
            sig_gen.set_output(cmd.channel, cmd.enabled)
            state = "enabled" if cmd.enabled else "disabled"
            logger.info(f"SigGen Ch{cmd.channel}: Output {state}")
            
            return {"status": "success", "channel": cmd.channel, "enabled": cmd.enabled}
        
        except Exception as e:
            logger.error(f"Signal generator output control error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    
    @app.get("/siggen/channel/{channel}/status")
    async def siggen_get_status(channel: int):
        """Get signal generator channel status"""
        if not sig_gen:
            raise HTTPException(status_code=503, detail="Signal generator not connected")
        
        if channel < 1 or channel > 2:
            raise HTTPException(status_code=400, detail="Channel must be 1 or 2")
        
        try:
            status = sig_gen.get_status(channel)
            return {
                "channel": channel,
                **status
            }
        
        except Exception as e:
            logger.error(f"Signal generator status read error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Laser Endpoints
# ============================================================================

if LASER_AVAILABLE:
    
    @app.post("/laser/power")
    async def laser_set_power(cmd: LaserPowerControl):
        """Control laser power (LD and TEC)"""
        if not laser:
            raise HTTPException(status_code=503, detail="Laser not connected")
        
        try:
            if cmd.tec_enabled is not None:
                laser.set_tec_power(cmd.tec_enabled)
                logger.info(f"Laser: TEC {'ON' if cmd.tec_enabled else 'OFF'}")
            
            if cmd.ld_enabled is not None:
                laser.set_ld_power(cmd.ld_enabled)
                logger.info(f"Laser: LD {'ON' if cmd.ld_enabled else 'OFF'}")
            
            return {"status": "success"}
        
        except Exception as e:
            logger.error(f"Laser power control error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    
    @app.post("/laser/configure")
    async def laser_configure(config: LaserConfiguration):
        """Configure laser parameters"""
        if not laser:
            raise HTTPException(status_code=503, detail="Laser not connected")
        
        try:
            if config.temperature is not None:
                laser.set_temperature(config.temperature)
                logger.info(f"Laser: Temperature set to {config.temperature}°C")
            
            if config.pulse_current is not None:
                laser.set_pulse_current(config.pulse_current)
                logger.info(f"Laser: Pulse current set to {config.pulse_current} mA")
            
            if config.bias_current is not None:
                laser.set_bias_current(config.bias_current)
                logger.info(f"Laser: Bias current set to {config.bias_current} mA")
            
            if config.soa_current is not None:
                laser.set_soa_current(config.soa_current)
                logger.info(f"Laser: SOA current set to {config.soa_current} mA")
            
            return {"status": "success"}
        
        except Exception as e:
            logger.error(f"Laser configuration error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    
    @app.post("/laser/oscillator")
    async def laser_set_oscillator(config: LaserOscillator):
        """Configure laser oscillator"""
        if not laser:
            raise HTTPException(status_code=503, detail="Laser not connected")
        
        try:
            # Set oscillator state if provided
            if any([config.pg1_enabled is not None, config.pg2_enabled is not None, config.ext_enabled is not None]):
                pg1 = config.pg1_enabled if config.pg1_enabled is not None else False
                pg2 = config.pg2_enabled if config.pg2_enabled is not None else False
                ext = config.ext_enabled if config.ext_enabled is not None else False
                laser.set_oscillator(pg1, pg2, ext)
                logger.info(f"Laser: Oscillator PG1={pg1}, PG2={pg2}, EXT={ext}")
            
            # Set frequencies if provided
            if config.pg1_frequency is not None:
                laser.set_pg1_frequency(config.pg1_frequency)
                logger.info(f"Laser: PG1 frequency set to {config.pg1_frequency} Hz")
            
            if config.pg2_frequency is not None:
                laser.set_pg2_frequency(config.pg2_frequency)
                logger.info(f"Laser: PG2 frequency set to {config.pg2_frequency} Hz")
            
            return {"status": "success"}
        
        except Exception as e:
            logger.error(f"Laser oscillator control error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    
    @app.get("/laser/status")
    async def laser_get_status():
        """Get laser status and measurements"""
        if not laser:
            raise HTTPException(status_code=503, detail="Laser not connected")
        
        try:
            status = laser.get_status()
            info = laser.get_device_info()
            
            return {
                **status,
                "device_info": info
            }
        
        except Exception as e:
            logger.error(f"Laser status read error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    
    @app.post("/laser/emergency_off")
    async def laser_emergency_off():
        """Emergency shutdown - turn off laser and TEC"""
        if not laser:
            raise HTTPException(status_code=503, detail="Laser not connected")
        
        try:
            laser.set_ld_power(False)
            logger.warning("EMERGENCY OFF: Laser LD")
            laser.set_tec_power(False)
            logger.warning("EMERGENCY OFF: Laser TEC")
            
            return {"status": "emergency_shutdown_complete"}
        
        except Exception as e:
            logger.error(f"Laser emergency shutdown error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    logger.info("Starting HyperK DAQ Device Server...")
    logger.info(f"Python: {struct.calcsize('P') * 8}-bit")
    logger.info(f"CAEN COM Port: {CAEN_COM_PORT}")
    logger.info(f"Signal Generator IP: {SIGGEN_IP}")
    logger.info(f"Laser DLL: {LASER_DLL_PATH}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",  # Listen on all interfaces
        port=8000,
        log_level="info"
    )