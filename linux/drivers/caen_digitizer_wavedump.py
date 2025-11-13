"""
CAEN Digitizer Driver (WaveDump Interface)
Manages CAEN digitizer via WaveDump command-line tool

This driver provides a clean interface to:
- Configure WaveDump parameters
- Run data acquisition
- Retrieve and organize waveform data
- Check digitizer status

Note: This uses WaveDump rather than direct CAENDigitizer library calls
for simplicity and compatibility with existing workflows.
"""

import subprocess
import shutil
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from datetime import datetime
from loguru import logger
import sys


class CAENDigitizerWaveDump:
    """
    Driver for CAEN digitizer using WaveDump tool.
    
    Supports:
    - DT5730 (8 channels, 500 MS/s, 14-bit)
    - DT5725 (8 channels, 250 MS/s, 14-bit)
    - DT5533E (8 channels, 1 GS/s, 12-bit) - if used for DAQ
    
    Typical HyperK setup:
    - Ch0: Trigger (SiPM or external)
    - Ch1: SiPM reference
    - Ch2: PMT 1
    - Ch3: PMT 2
    - Ch4: PMT 3 (monitor)
    - Ch5-7: Unused
    """
    
    def __init__(
        self,
        wavedump_path: str = "/usr/local/bin/WaveDump",
        config_template: str = "configs/WaveDumpConfig_template.txt",
        working_dir: Optional[str] = None,
        kernel_module_required: bool = True
    ):
        """
        Initialize digitizer driver.
        
        Args:
            wavedump_path: Path to WaveDump executable
            config_template: Path to template configuration file
            working_dir: Directory for temporary files (default: current dir)
            kernel_module_required: If True, check for CAENUSBdrvB module
        """
        self.wavedump_path = wavedump_path
        self.config_template = Path(config_template)
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.config_file = self.working_dir / "WaveDumpConfig.txt"
        
        # Channel configuration
        self.channel_names = {
            0: "Trigger",
            1: "SiPM",
            2: "PMT1",
            3: "PMT2",
            4: "PMT3_Monitor",
            5: "Channel5",
            6: "Channel6",
            7: "Channel7"
        }
        
        # Verify WaveDump exists
        if not Path(wavedump_path).exists():
            logger.error(f"WaveDump not found at {wavedump_path}")
            raise FileNotFoundError(f"WaveDump executable not found: {wavedump_path}")
        
        # Verify config template exists
        if not self.config_template.exists():
            logger.error(f"Config template not found: {config_template}")
            raise FileNotFoundError(f"Config template not found: {config_template}")
        
        # Check kernel module if required
        if kernel_module_required:
            self._check_kernel_module()
        
        logger.info("CAEN Digitizer driver initialized")
        logger.info(f"  WaveDump: {wavedump_path}")
        logger.info(f"  Config template: {config_template}")
        logger.info(f"  Working directory: {self.working_dir}")
    
    def _check_kernel_module(self) -> bool:
        """
        Check if CAENUSBdrvB kernel module is loaded.
        
        Returns:
            True if module is loaded
        """
        try:
            result = subprocess.run(
                ["lsmod"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if "CAENUSBdrvB" in result.stdout:
                logger.info("✓ CAENUSBdrvB kernel module loaded")
                return True
            else:
                logger.warning("⚠ CAENUSBdrvB kernel module not loaded")
                logger.info("  Run: sudo insmod ~/CAEN/.../CAENUSBdrvB.ko")
                logger.info("  Or use sourceatstart.sh script")
                return False
                
        except Exception as e:
            logger.warning(f"Could not check kernel module: {e}")
            return False
    
    def check_connection(self) -> bool:
        """
        Check if digitizer is accessible by attempting to query it.
        
        Returns:
            True if digitizer responds
        """
        try:
            # Method 1: Try running WaveDump with --version or similar
            # Note: WaveDump doesn't have a --version flag, so we'll try a different approach
            
            # Method 2: Check if USB device is present
            result = subprocess.run(
                ["lsusb"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # CAEN USB devices typically have VID 0x21e1
            if "21e1" in result.stdout.lower() or "caen" in result.stdout.lower():
                logger.info("✓ CAEN USB device detected")
                return True
            else:
                logger.warning("⚠ CAEN USB device not found")
                return False
                
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False
    
    # =========================================================================
    # Configuration
    # =========================================================================
    
    def configure(
        self,
        run_duration: int,
        channels: List[int],
        record_length: Optional[int] = None,
        post_trigger: Optional[int] = None,
        other_params: Optional[Dict[str, any]] = None
    ):
        """
        Configure WaveDump for acquisition.
        
        Args:
            run_duration: Acquisition time in seconds
            channels: List of channels to enable (0-7)
            record_length: Number of samples per waveform (default: use template)
            post_trigger: Post-trigger percentage (0-100, default: use template)
            other_params: Additional parameters to modify in config
        """
        logger.info(f"Configuring digitizer:")
        logger.info(f"  Duration: {run_duration}s")
        logger.info(f"  Channels: {channels}")
        
        # Read template
        with open(self.config_template, 'r') as f:
            lines = f.readlines()
        
        # Modify run duration (typically around line 32)
        # Find the line with RUN_DURATION
        for i, line in enumerate(lines):
            if line.strip().startswith("RUN_DURATION"):
                lines[i] = f"RUN_DURATION  {run_duration}\n"
                logger.debug(f"  Set RUN_DURATION to {run_duration}s at line {i}")
                break
        
        # Modify record length if specified
        if record_length is not None:
            for i, line in enumerate(lines):
                if line.strip().startswith("RECORD_LENGTH"):
                    lines[i] = f"RECORD_LENGTH  {record_length}\n"
                    logger.debug(f"  Set RECORD_LENGTH to {record_length}")
                    break
        
        # Modify post-trigger if specified
        if post_trigger is not None:
            for i, line in enumerate(lines):
                if line.strip().startswith("POST_TRIGGER"):
                    lines[i] = f"POST_TRIGGER  {post_trigger}\n"
                    logger.debug(f"  Set POST_TRIGGER to {post_trigger}%")
                    break
        
        # Enable/disable channels
        # This is template-specific - adjust line numbers as needed
        # Standard template has channel configs starting around line 140
        channel_line_map = self._find_channel_lines(lines)
        
        for ch in range(8):
            if ch in channel_line_map:
                line_idx = channel_line_map[ch]
                if ch in channels:
                    lines[line_idx] = "ENABLE_INPUT           YES\n"
                    logger.debug(f"  Enabled Ch{ch} ({self.channel_names[ch]})")
                else:
                    lines[line_idx] = "ENABLE_INPUT           NO\n"
        
        # Apply other parameters if provided
        if other_params:
            for param_name, param_value in other_params.items():
                for i, line in enumerate(lines):
                    if line.strip().startswith(param_name):
                        lines[i] = f"{param_name}  {param_value}\n"
                        logger.debug(f"  Set {param_name} to {param_value}")
                        break
        
        # Write active config
        with open(self.config_file, 'w') as f:
            f.writelines(lines)
        
        logger.info(f"✓ Configuration written to {self.config_file}")
    
    def _find_channel_lines(self, lines: List[str]) -> Dict[int, int]:
        """
        Find the line numbers for ENABLE_INPUT for each channel.
        
        This searches for channel markers in the config file.
        
        Args:
            lines: Config file lines
            
        Returns:
            Dict mapping channel number to ENABLE_INPUT line number
        """
        channel_lines = {}
        current_channel = None
        
        for i, line in enumerate(lines):
            # Look for channel markers like [0], [1], etc.
            if line.strip().startswith('[') and line.strip().endswith(']'):
                try:
                    current_channel = int(line.strip()[1:-1])
                except ValueError:
                    current_channel = None
            
            # If we're in a channel section and find ENABLE_INPUT
            if current_channel is not None and line.strip().startswith("ENABLE_INPUT"):
                channel_lines[current_channel] = i
                current_channel = None  # Reset to avoid duplicates
        
        return channel_lines
    
    # =========================================================================
    # Data Acquisition
    # =========================================================================
    
    def acquire(self, timeout: Optional[int] = None) -> bool:
        """
        Run data acquisition using WaveDump.
        
        Args:
            timeout: Maximum time to wait (seconds). If None, uses run_duration + 30s
            
        Returns:
            True if acquisition completed successfully
        """
        if timeout is None:
            # Default timeout: add 30 seconds buffer to configured run time
            timeout = 300  # Default 5 minutes if we can't determine
        
        logger.info(f"Starting acquisition (timeout: {timeout}s)...")
        
        try:
            result = subprocess.run(
                [self.wavedump_path, str(self.config_file)],
                cwd=str(self.working_dir),
                timeout=timeout,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("✓ Acquisition completed successfully")
                # Wait for files to be fully written
                import time
                time.sleep(1)
                return True
            else:
                logger.error(f"WaveDump failed with return code {result.returncode}")
                if result.stderr:
                    logger.error(f"Error output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Acquisition timed out after {timeout}s")
            return False
        except Exception as e:
            logger.error(f"Acquisition error: {e}")
            return False
    
    def acquire_with_progress(
        self,
        duration: int,
        progress_callback: Optional[callable] = None
    ) -> bool:
        """
        Run acquisition with progress updates.
        
        This starts WaveDump in the background and polls for completion.
        
        Args:
            duration: Expected acquisition duration (seconds)
            progress_callback: Function(progress_percent, message)
            
        Returns:
            True if successful
        """
        logger.info(f"Starting acquisition with progress tracking ({duration}s)...")
        
        import time
        
        # Start WaveDump in background
        process = subprocess.Popen(
            [self.wavedump_path, str(self.config_file)],
            cwd=str(self.working_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Poll for completion while updating progress
        start_time = time.time()
        
        try:
            while True:
                elapsed = time.time() - start_time
                
                # Check if process finished
                retcode = process.poll()
                if retcode is not None:
                    if retcode == 0:
                        logger.info("✓ Acquisition completed")
                        if progress_callback:
                            progress_callback(100, "Acquisition complete")
                        time.sleep(1)  # Let files settle
                        return True
                    else:
                        logger.error(f"WaveDump failed with code {retcode}")
                        return False
                
                # Update progress
                progress = min(int((elapsed / duration) * 100), 99)
                if progress_callback:
                    progress_callback(progress, f"Acquiring data... {elapsed:.0f}s / {duration}s")
                
                # Check for timeout
                if elapsed > duration + 30:
                    logger.error("Acquisition timeout")
                    process.kill()
                    return False
                
                time.sleep(1)  # Update every second
                
        except KeyboardInterrupt:
            logger.warning("Acquisition interrupted by user")
            process.kill()
            return False
    
    # =========================================================================
    # Data Retrieval
    # =========================================================================
    
    def get_waveform(self, channel: int) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """
        Read waveform data from wave file.
        
        Args:
            channel: Channel number (0-7)
            
        Returns:
            Tuple of (time_array, adc_array) or None if file doesn't exist
        """
        wave_file = self.working_dir / f"wave{channel}.txt"
        
        if not wave_file.exists():
            logger.debug(f"Waveform file not found: {wave_file}")
            return None
        
        try:
            # WaveDump format: two columns (time, ADC)
            data = np.loadtxt(wave_file)
            
            if len(data.shape) == 2 and data.shape[1] == 2:
                time_data = data[:, 0]
                adc_data = data[:, 1]
                logger.debug(f"Read {len(time_data)} samples from Ch{channel}")
                return time_data, adc_data
            else:
                logger.warning(f"Unexpected data format in {wave_file}")
                return None
                
        except Exception as e:
            logger.error(f"Error reading waveform Ch{channel}: {e}")
            return None
    
    def get_all_waveforms(self, channels: List[int]) -> Dict[int, Tuple[np.ndarray, np.ndarray]]:
        """
        Read waveforms for multiple channels.
        
        Args:
            channels: List of channel numbers
            
        Returns:
            Dict mapping channel -> (time_array, adc_array)
        """
        waveforms = {}
        
        for ch in channels:
            waveform = self.get_waveform(ch)
            if waveform is not None:
                waveforms[ch] = waveform
        
        logger.info(f"Retrieved waveforms for {len(waveforms)} channels")
        return waveforms
    
    # =========================================================================
    # File Organization
    # =========================================================================
    
    def organize_files(
        self,
        save_dir: str,
        prefix: str,
        channels: List[int],
        include_timestamp: bool = True
    ):
        """
        Move waveform files to organized directory structure.
        
        Args:
            save_dir: Target directory
            prefix: Filename prefix (e.g., "dark_current" or "theta10_phi90")
            channels: List of channels to organize
            include_timestamp: If True, add timestamp to directory name
        """
        # Create save directory
        save_path = Path(save_dir)
        if include_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = save_path / timestamp
        
        save_path.mkdir(parents=True, exist_ok=True)
        
        # Move waveform files
        moved_count = 0
        for ch in channels:
            wave_file = self.working_dir / f"wave{ch}.txt"
            
            if wave_file.exists():
                dest_name = f"wave{ch}_{prefix}.txt"
                dest_path = save_path / dest_name
                
                shutil.move(str(wave_file), str(dest_path))
                logger.debug(f"Moved Ch{ch} -> {dest_path}")
                moved_count += 1
        
        logger.info(f"✓ Organized {moved_count} waveform files to {save_path}")
        return save_path
    
    # =========================================================================
    # Utility Functions
    # =========================================================================
    
    def cleanup_temp_files(self):
        """Remove temporary waveform files from working directory."""
        for ch in range(8):
            wave_file = self.working_dir / f"wave{ch}.txt"
            if wave_file.exists():
                wave_file.unlink()
                logger.debug(f"Removed {wave_file}")
        
        logger.info("Cleaned up temporary files")
    
    def get_status(self) -> Dict[str, any]:
        """
        Get digitizer status.
        
        Returns:
            Dict with connection status and configuration
        """
        return {
            'connected': self.check_connection(),
            'kernel_module': self._check_kernel_module(),
            'wavedump_path': self.wavedump_path,
            'working_dir': str(self.working_dir),
            'config_file': str(self.config_file),
            'config_exists': self.config_file.exists()
        }


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Initialize digitizer
    digitizer = CAENDigitizerWaveDump(
        wavedump_path="/usr/local/bin/WaveDump",
        config_template="configs/WaveDumpConfig_template.txt"
    )
    
    # Check status
    status = digitizer.get_status()
    print(f"Digitizer status: {status}")
    
    # Configure for dark current measurement
    digitizer.configure(
        run_duration=300,  # 5 minutes
        channels=[2, 3, 4]  # PMT1, PMT2, PMT3
    )
    
    # Acquire data
    success = digitizer.acquire(timeout=330)
    
    if success:
        # Get waveforms
        waveforms = digitizer.get_all_waveforms([2, 3, 4])
        
        # Organize files
        digitizer.organize_files(
            save_dir="../WaveDumpSaves/dark_current",
            prefix="dark_current",
            channels=[2, 3, 4]
        )
        
        # Cleanup
        digitizer.cleanup_temp_files()
