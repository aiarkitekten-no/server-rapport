#!/usr/bin/env python3
"""ClamAV Checker"""

import logging
from typing import List
from pathlib import Path

from utils.base_checker import BaseChecker
from utils.common import run_command, get_file_age_hours
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class ClamAVChecker(BaseChecker):
    """Check ClamAV antivirus"""
    
    def run(self) -> List[CheckResult]:
        self.clear_results()
        
        result = run_command(['which', 'clamd'])
        if not result or result.returncode != 0:
            return self.get_results()
        
        self.check_clamd_status()
        self.check_freshclam()
        
        return self.get_results()
    
    def check_clamd_status(self):
        """Check ClamAV daemon status"""
        result = run_command(['systemctl', 'is-active', 'clamav-daemon'])
        if result and 'active' in result.stdout:
            self.add_ok('clamd', 'ClamAV daemon is active')
        else:
            self.add_warning('clamd', 'ClamAV daemon is not active', {}, 45)
    
    def check_freshclam(self):
        """Check virus definition updates"""
        db_path = Path('/var/lib/clamav/daily.cvd')
        if db_path.exists():
            age = get_file_age_hours(db_path)
            if age and age > 48:
                self.add_warning('clamav_definitions', f'Virus definitions are {age:.0f} hours old', {'age_hours': age}, 55)
            else:
                self.add_ok('clamav_definitions', 'Virus definitions are up to date')
