#!/usr/bin/env python3
"""
Package Management Checker
Monitors: apt updates, unattended-upgrades, dpkg status
"""

import logging
from pathlib import Path
from typing import List
from datetime import datetime, timedelta

from utils.base_checker import BaseChecker
from utils.common import run_command, safe_read_file, get_file_age_hours
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class PackagesChecker(BaseChecker):
    """Check package management status"""
    
    def run(self) -> List[CheckResult]:
        """Run all package checks"""
        self.clear_results()
        
        self.check_apt_updates()
        self.check_unattended_upgrades()
        self.check_dpkg_status()
        self.check_held_packages()
        
        return self.get_results()
    
    def check_apt_updates(self):
        """Check for available APT updates"""
        # Check for available updates (don't run apt-get update without sudo)
        result = run_command(['apt', 'list', '--upgradable'], timeout=30)
        if not result or result.returncode != 0:
            self.add_unknown('apt_updates', 'Could not check for updates')
            return
        
        # Count upgradable packages (skip the header line)
        upgradable_lines = [l for l in result.stdout.split('\n') if l.strip() and not l.startswith('Listing')]
        upgradable_count = len(upgradable_lines)
        
        # Count security updates
        security_count = sum(1 for line in upgradable_lines if 'security' in line.lower())
        
        details = {
            'total_updates': upgradable_count,
            'security_updates': security_count,
            'packages': upgradable_lines[:20]  # First 20
        }
        
        if security_count > 10:
            self.add_critical(
                'apt_updates',
                f'{security_count} security updates available (total: {upgradable_count})',
                details,
                85
            )
        elif security_count > 0:
            self.add_warning(
                'apt_updates',
                f'{security_count} security updates available (total: {upgradable_count})',
                details,
                60
            )
        elif upgradable_count > 50:
            self.add_warning(
                'apt_updates',
                f'{upgradable_count} package updates available',
                details,
                45
            )
        elif upgradable_count > 0:
            self.add_ok(
                'apt_updates',
                f'{upgradable_count} package updates available',
                details
            )
        else:
            self.add_ok('apt_updates', 'System is up to date')
    
    def check_unattended_upgrades(self):
        """Check if unattended-upgrades is active and working"""
        # Check if installed
        result = run_command(['dpkg', '-l', 'unattended-upgrades'])
        if not result or 'ii' not in result.stdout:
            self.add_warning(
                'unattended_upgrades',
                'unattended-upgrades package not installed',
                {},
                40
            )
            return
        
        # Check if enabled
        config_file = Path('/etc/apt/apt.conf.d/20auto-upgrades')
        if not config_file.exists():
            self.add_warning(
                'unattended_upgrades',
                'unattended-upgrades not configured',
                {},
                50
            )
            return
        
        # Check last run (handle permission errors gracefully)
        log_file = Path('/var/log/unattended-upgrades/unattended-upgrades.log')
        try:
            if log_file.exists():
                age_hours = get_file_age_hours(log_file)
                if age_hours and age_hours > 48:
                    self.add_warning(
                        'unattended_upgrades',
                        f'unattended-upgrades log not updated in {age_hours:.1f} hours',
                        {'last_update_hours': age_hours},
                        55
                    )
                else:
                    self.add_ok(
                        'unattended_upgrades',
                        'unattended-upgrades is active',
                        {'last_update_hours': age_hours}
                    )
            else:
                self.add_ok('unattended_upgrades', 'unattended-upgrades is configured')
        except PermissionError:
            logger.debug('Permission denied checking unattended-upgrades log')
            self.add_ok('unattended_upgrades', 'unattended-upgrades is configured (log not accessible)')
    
    def check_dpkg_status(self):
        """Check for dpkg errors and partially installed packages"""
        # Check for dpkg lock files (indicates interrupted operation)
        lock_files = [
            '/var/lib/dpkg/lock',
            '/var/lib/apt/lists/lock',
            '/var/cache/apt/archives/lock'
        ]
        
        # Check dpkg status
        result = run_command(['dpkg', '--audit'])
        if result and result.returncode == 0:
            if result.stdout.strip():
                # There are issues
                self.add_critical(
                    'dpkg_status',
                    'dpkg audit found issues',
                    {'audit_output': result.stdout[:500]},
                    75
                )
            else:
                self.add_ok('dpkg_status', 'dpkg database is healthy')
        else:
            self.add_unknown('dpkg_status', 'Could not run dpkg audit')
        
        # Check for packages in bad state
        result = run_command(['dpkg', '-l'])
        if result and result.returncode == 0:
            bad_packages = []
            for line in result.stdout.split('\n'):
                if line.startswith('iU') or line.startswith('iF') or line.startswith('iH'):
                    bad_packages.append(line.split()[1])
            
            if bad_packages:
                self.add_warning(
                    'dpkg_bad_packages',
                    f'{len(bad_packages)} packages in bad state',
                    {'packages': bad_packages},
                    65
                )
    
    def check_held_packages(self):
        """Check for held packages that might need updates"""
        result = run_command(['apt-mark', 'showhold'])
        if result and result.returncode == 0:
            held_packages = [p.strip() for p in result.stdout.split('\n') if p.strip()]
            
            if held_packages:
                self.add_ok(
                    'held_packages',
                    f'{len(held_packages)} packages on hold',
                    {'packages': held_packages}
                )
