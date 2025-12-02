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
        wavedump_path="/home/hyperkaus/CAEN/wavedump-3.10.6-augmented/src/wavedump",
        config_template="./configs/wavedumpconfig_template.txt",
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
        output_format: str = 'ASCII',  # 'ASCII' or 'BINARY'
        record_length: Optional[int] = None,
        post_trigger: Optional[int] = None,
        trigger_channel: Optional[int] = None,
        trigger_threshold: Optional[int] = None,
        channel_trigger_mode: Optional[str] = None,
        other_params: Optional[Dict[str, any]] = None
    ):
        """
        Configure WaveDump for acquisition.
        
        Args:
            run_duration: Acquisition time in seconds
            channels: List of channels to enable (0-7)
            record_length: Number of samples per waveform (default: use template)
            post_trigger: Post-trigger percentage (0-100, default: use template)
            trigger_channel: Channel to use for triggering (0-7, default: no change)
            trigger_threshold: Trigger threshold in ADC counts (default: no change)
            channel_trigger_mode: Trigger mode per channel: 'DISABLED', 'ACQUISITION_ONLY', 
                                  'ACQUISITION_AND_TRGOUT' (default: no change)
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

        # Set output file format
        for i, line in enumerate(lines):
            if 'OUTPUT_FILE_FORMAT' in line:
                lines[i] = f"OUTPUT_FILE_FORMAT    {output_format}\n"
                logger.info(f"Set output format to {output_format}")
                break
                
        # Enable/disable channels and set trigger parameters
        channel_sections = self._find_channel_sections(lines)
        
        for ch in range(8):
            if ch in channel_sections:
                section_start, section_end = channel_sections[ch]
                
                # Enable/disable channel
                for i in range(section_start, section_end):
                    if lines[i].strip().startswith("ENABLE_INPUT"):
                        if ch in channels:
                            lines[i] = "ENABLE_INPUT           YES\n"
                            logger.debug(f"  Enabled Ch{ch} ({self.channel_names[ch]})")
                        else:
                            lines[i] = "ENABLE_INPUT           NO\n"
                        break
                
                # Set trigger threshold for specific channel if specified
                if trigger_channel is not None and ch == trigger_channel and trigger_threshold is not None:
                    for i in range(section_start, section_end):
                        if lines[i].strip().startswith("TRIGGER_THRESHOLD"):
                            lines[i] = f"TRIGGER_THRESHOLD      {trigger_threshold}\n"
                            logger.debug(f"  Set Ch{ch} TRIGGER_THRESHOLD to {trigger_threshold}")
                            break
                
                # Set channel trigger mode for specific channel if specified
                if trigger_channel is not None and ch == trigger_channel and channel_trigger_mode is not None:
                    for i in range(section_start, section_end):
                        if lines[i].strip().startswith("CHANNEL_TRIGGER"):
                            lines[i] = f"CHANNEL_TRIGGER        {channel_trigger_mode}\n"
                            logger.debug(f"  Set Ch{ch} CHANNEL_TRIGGER to {channel_trigger_mode}")
                            break
        
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
    
    def _find_channel_sections(self, lines: List[str]) -> Dict[int, Tuple[int, int]]:
        """
        Find the line range for each channel's configuration section.
        
        This searches for channel markers like [0], [1], etc. and finds
        the start and end of each channel's configuration block.
        
        Args:
            lines: Config file lines
            
        Returns:
            Dict mapping channel number to (start_line, end_line) tuple
        """
        channel_sections = {}
        current_channel = None
        section_start = None
        
        for i, line in enumerate(lines):
            # Look for channel markers like [0], [1], etc.
            stripped = line.strip()
            if stripped.startswith('[') and stripped.endswith(']'):
                # Save previous channel section
                if current_channel is not None and section_start is not None:
                    channel_sections[current_channel] = (section_start, i-1)
                
                # Start new channel section
                try:
                    current_channel = int(stripped[1:-1])
                    section_start = i
                except ValueError:
                    current_channel = None
                    section_start = None
        
        # Don't forget the last channel
        if current_channel is not None and section_start is not None:
            channel_sections[current_channel] = (section_start, len(lines))
        
        return channel_sections
    
    # =========================================================================
    # Data Acquisition
    # =========================================================================
    
    def acquire(self, timeout: Optional[int] = None, show_output: bool = True) -> bool:
        """
        Run data acquisition using WaveDump.
        
        Args:
            timeout: Maximum time to wait (seconds). If None, uses run_duration + 30s
            show_output: If True, print WaveDump output to console
            
        Returns:
            True if acquisition completed successfully
        """
        if timeout is None:
            # Default timeout: add 30 seconds buffer to configured run time
            timeout = 300  # Default 5 minutes if we can't determine
        
        logger.info(f"Starting acquisition (timeout: {timeout}s)...")
        
        try:
            if show_output:
                # Show output in real-time
                result = subprocess.run(
                    [self.wavedump_path, str(self.config_file)],
                    cwd=str(self.working_dir),
                    timeout=timeout
                )
            else:
                # Capture output (old behavior)
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
                if not show_output and result.stderr:
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
    
    def get_wavefile(self, channel: int) -> Optional[Path]:
        """
        Get waveform file for a specific channel.
        Checks for both ASCII (.txt) and binary (.dat) formats.
        
        Args:
            channel: Channel number
            
        Returns:
            Path to waveform file, or None if not found
        """
        # Try both ASCII and binary formats
        txt_file = self.working_dir / f"wave{channel}.txt"
        dat_file = self.working_dir / f"wave{channel}.dat"
        
        if txt_file.exists():
            return txt_file
        elif dat_file.exists():
            return dat_file
        else:
            logger.warning(f"Waveform file for channel {channel} not found (tried .txt and .dat)")
            return None
    
    def get_all_wavefiles(self, channels: List[int]) -> Dict[int, Path]:
        """
        Check which waveform files exist for given channels.
        
        Returns paths to files, not actual data. Analysis should be done offline.
        
        Args:
            channels: List of channel numbers
            
        Returns:
            Dict mapping channel -> Path to waveform file (only for channels with files)
        """
        waveform_files = {}
        
        for ch in channels:
            wave_file = self.get_wavefile(ch)
            if wave_file is not None:
                waveform_files[ch] = wave_file
        
        logger.info(f"Found waveform files for {len(waveform_files)} channels")
        return waveform_files
    
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
        waveforms = digitizer.get_all_wavefiles([2, 3, 4])
        
        # Organize files
        digitizer.organize_files(
            save_dir="../WaveDumpSaves/dark_current",
            prefix="dark_current",
            channels=[2, 3, 4]
        )
        
        # Cleanup
        digitizer.cleanup_temp_files()
