#!/usr/bin/env python3
"""
Network Checker
Monitors: network errors, NTP sync
"""

import logging
import re
from pathlib import Path
from typing import List

from utils.base_checker import BaseChecker
from utils.common import run_command
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class NetworkChecker(BaseChecker):
    """Check network health"""
    
    def run(self) -> List[CheckResult]:
        """Run all network checks"""
        self.clear_results()
        
        self.check_network_errors()
        self.check_ntp_sync()
        
        return self.get_results()
    
    def check_network_errors(self):
        """Check for network interface errors"""
        result = run_command(['ip', '-s', 'link'])
        if not result or result.returncode != 0:
            self.add_unknown('network_errors', 'Could not read network stats')
            return
        
        interfaces_with_errors = []
        current_interface = None
        
        lines = result.stdout.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Interface line
            if re.match(r'^\d+:', line):
                parts = line.split(':')
                if len(parts) >= 2:
                    current_interface = parts[1].strip().split('@')[0]
            
            # RX errors line
            elif 'RX:' in line and 'errors' in line.lower():
                i += 1
                if i < len(lines):
                    stats_line = lines[i].strip()
                    parts = stats_line.split()
                    if len(parts) >= 3:
                        try:
                            errors = int(parts[2])
                            if errors > 100 and current_interface:
                                interfaces_with_errors.append({
                                    'interface': current_interface,
                                    'rx_errors': errors
                                })
                        except ValueError:
                            pass
            
            # TX errors line
            elif 'TX:' in line and 'errors' in line.lower():
                i += 1
                if i < len(lines):
                    stats_line = lines[i].strip()
                    parts = stats_line.split()
                    if len(parts) >= 3:
                        try:
                            errors = int(parts[2])
                            if errors > 100 and current_interface:
                                # Check if already added for RX errors
                                existing = next((x for x in interfaces_with_errors if x['interface'] == current_interface), None)
                                if existing:
                                    existing['tx_errors'] = errors
                                else:
                                    interfaces_with_errors.append({
                                        'interface': current_interface,
                                        'tx_errors': errors
                                    })
                        except ValueError:
                            pass
            
            i += 1
        
        if interfaces_with_errors:
            total_errors = sum(
                item.get('rx_errors', 0) + item.get('tx_errors', 0) 
                for item in interfaces_with_errors
            )
            
            if total_errors > 10000:
                self.add_critical(
                    'network_errors',
                    f'High network errors detected on {len(interfaces_with_errors)} interface(s)',
                    {'interfaces': interfaces_with_errors},
                    80
                )
            else:
                self.add_warning(
                    'network_errors',
                    f'Network errors detected on {len(interfaces_with_errors)} interface(s)',
                    {'interfaces': interfaces_with_errors},
                    50
                )
        else:
            self.add_ok('network_errors', 'No significant network errors detected')
    
    def check_ntp_sync(self):
        """Check NTP synchronization"""
        # Try timedatectl first (systemd)
        result = run_command(['timedatectl', 'status'])
        if result and result.returncode == 0:
            output = result.stdout.lower()
            
            if 'ntp service: active' in output or 'system clock synchronized: yes' in output:
                self.add_ok('ntp_sync', 'System clock is synchronized')
            elif 'ntp service: inactive' in output:
                self.add_warning(
                    'ntp_sync',
                    'NTP service is inactive',
                    {},
                    60
                )
            else:
                self.add_warning(
                    'ntp_sync',
                    'Clock synchronization status unclear',
                    {'output': output[:200]},
                    45
                )
            return
        
        # Try ntpq (classic NTP)
        result = run_command(['ntpq', '-p'])
        if result and result.returncode == 0:
            # Check if any peer is selected (has * in front)
            if '*' in result.stdout:
                self.add_ok('ntp_sync', 'NTP is synchronized')
            else:
                self.add_warning(
                    'ntp_sync',
                    'NTP configured but not synchronized',
                    {},
                    55
                )
            return
        
        # Try chronyc (Chrony)
        result = run_command(['chronyc', 'tracking'])
        if result and result.returncode == 0:
            if 'leap status     : normal' in result.stdout.lower():
                self.add_ok('ntp_sync', 'Chrony is synchronized')
            else:
                self.add_warning('ntp_sync', 'Chrony status unclear', {}, 50)
            return
        
        # No NTP found
        self.add_warning(
            'ntp_sync',
            'No NTP service detected',
            {},
            65
        )
