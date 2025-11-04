#!/usr/bin/env python3
"""
Common utilities for Plesk Health Check
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Union
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


def run_command(
    cmd: Union[str, List[str]], 
    timeout: int = 30, 
    check: bool = False,
    shell: bool = False,
    input_data: Optional[str] = None
) -> Optional[subprocess.CompletedProcess]:
    """
    Run a system command safely with timeout and error handling.
    
    Args:
        cmd: Command to run (list for safe execution, str only if shell=True)
        timeout: Timeout in seconds
        check: Raise CalledProcessError on non-zero exit
        shell: Use shell execution (avoid when possible)
        input_data: Optional string to send to stdin
    
    Returns:
        CompletedProcess object or None on error
    """
    try:
        if isinstance(cmd, str) and not shell:
            logger.warning(f"String command without shell=True: {cmd[:50]}")
            cmd = cmd.split()
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
            shell=shell,
            input=input_data
        )
        return result
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {cmd}")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {cmd}, Exit code: {e.returncode}")
        logger.error(f"stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        logger.error(f"Command not found: {cmd}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error running command {cmd}: {e}")
        return None


def safe_read_file(filepath: Union[str, Path], max_lines: Optional[int] = None) -> Optional[str]:
    """
    Safely read a file with error handling.
    
    Args:
        filepath: Path to file
        max_lines: Maximum number of lines to read (None = all)
    
    Returns:
        File contents as string or None on error
    """
    try:
        path = Path(filepath)
        if not path.exists():
            logger.warning(f"File not found: {filepath}")
            return None
        
        if not path.is_file():
            logger.warning(f"Not a file: {filepath}")
            return None
        
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            if max_lines:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
                return ''.join(lines)
            else:
                return f.read()
    except PermissionError:
        logger.error(f"Permission denied reading: {filepath}")
        return None
    except Exception as e:
        logger.error(f"Error reading file {filepath}: {e}")
        return None


def parse_human_time(time_str: str) -> Optional[timedelta]:
    """
    Parse human-readable time strings like '2 days', '3h 20m', etc.
    
    Args:
        time_str: Time string to parse
    
    Returns:
        timedelta object or None if parsing fails
    """
    try:
        # Simple parsing for common formats
        time_str = time_str.lower().strip()
        
        # Handle formats like "up 2 days, 3:45"
        total_seconds = 0
        
        if 'day' in time_str:
            days = int(time_str.split('day')[0].split()[-1])
            total_seconds += days * 86400
        
        if 'hour' in time_str or 'hr' in time_str or 'h' in time_str:
            # Extract hours
            for part in time_str.split():
                if 'h' in part or 'hour' in part:
                    hours = int(''.join(filter(str.isdigit, part)))
                    total_seconds += hours * 3600
        
        if 'min' in time_str or 'm' in time_str:
            for part in time_str.split():
                if 'm' in part or 'min' in part:
                    mins = int(''.join(filter(str.isdigit, part)))
                    total_seconds += mins * 60
        
        if total_seconds > 0:
            return timedelta(seconds=total_seconds)
        
        return None
    except Exception as e:
        logger.debug(f"Failed to parse time string '{time_str}': {e}")
        return None


def format_bytes(bytes_val: int) -> str:
    """
    Format bytes into human-readable string.
    
    Args:
        bytes_val: Number of bytes
    
    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"


def format_percentage(value: float, total: float) -> float:
    """
    Calculate percentage safely.
    
    Args:
        value: Current value
        total: Total value
    
    Returns:
        Percentage as float (0-100)
    """
    if total == 0:
        return 0.0
    return round((value / total) * 100, 2)


def load_json_file(filepath: Union[str, Path]) -> Optional[dict]:
    """
    Load JSON file safely.
    
    Args:
        filepath: Path to JSON file
    
    Returns:
        Dictionary or None on error
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"JSON file not found: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading JSON {filepath}: {e}")
        return None


def save_json_file(data: dict, filepath: Union[str, Path]) -> bool:
    """
    Save dictionary to JSON file.
    
    Args:
        data: Dictionary to save
        filepath: Path to save to
    
    Returns:
        True on success, False on error
    """
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving JSON to {filepath}: {e}")
        return False


def is_plesk_installed() -> bool:
    """
    Check if Plesk is installed on this system.
    
    Returns:
        True if Plesk is installed, False otherwise
    """
    # Check multiple Plesk indicators
    plesk_paths = [
        '/usr/local/psa/bin/plesk',
        '/usr/local/psa/version',
        '/usr/local/psa',
        '/opt/psa',
        '/etc/sw/keys/keys'  # Plesk license keys
    ]
    
    for path in plesk_paths:
        if Path(path).exists():
            logger.debug(f'Plesk detected at: {path}')
            return True
    
    # Also check for plesk command in PATH
    result = run_command(['which', 'plesk'], timeout=5)
    if result and result.returncode == 0 and result.stdout.strip():
        logger.debug(f'Plesk found in PATH: {result.stdout.strip()}')
        return True
    
    return False


def get_file_age_hours(filepath: Union[str, Path]) -> Optional[float]:
    """
    Get age of file in hours.
    
    Args:
        filepath: Path to file
    
    Returns:
        Age in hours or None if file doesn't exist
    """
    try:
        path = Path(filepath)
        if not path.exists():
            return None
        
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        age = datetime.now() - mtime
        return age.total_seconds() / 3600
    except Exception as e:
        logger.error(f"Error getting file age for {filepath}: {e}")
        return None
