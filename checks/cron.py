#!/usr/bin/env python3
"""Cron Checker"""

import logging
from pathlib import Path
from typing import List

from utils.base_checker import BaseChecker
from utils.common import run_command
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class CronChecker(BaseChecker):
    """Check cron jobs"""
    
    def run(self) -> List[CheckResult]:
        self.clear_results()
        self.check_cron_service()
        self.check_cron_errors()
        self.check_cron_schedules()
        return self.get_results()
    
    def check_cron_service(self):
        """Check if cron service is running"""
        result = run_command(['systemctl', 'is-active', 'cron'])
        if result and result.returncode == 0 and 'active' in result.stdout:
            self.add_ok('cron_service', 'Cron service is active')
        else:
            self.add_critical('cron_service', 'Cron service is not active', {}, 85)
    
    def check_cron_errors(self):
        """Check for failed cron jobs in logs"""
        # Check syslog for cron errors
        syslog = Path('/var/log/syslog')
        if not syslog.exists():
            syslog = Path('/var/log/messages')
        
        if not syslog.exists():
            return
        
        result = run_command(['grep', '-i', 'cron', str(syslog)])
        if not result or result.returncode != 0:
            return
        
        # Look for error indicators in cron log lines
        cron_lines = result.stdout.split('\n')[-500:]  # Last 500 cron lines
        
        errors = []
        failed_commands = []
        
        for line in cron_lines:
            line_lower = line.lower()
            if any(word in line_lower for word in ['error', 'failed', 'cannot', 'unable']):
                errors.append(line)
                # Try to extract command
                if 'CMD' in line:
                    cmd_start = line.find('CMD')
                    if cmd_start > 0:
                        cmd = line[cmd_start:cmd_start+100]
                        if cmd not in failed_commands:
                            failed_commands.append(cmd)
        
        if len(errors) > 50:
            self.add_critical(
                'cron_errors',
                f'{len(errors)} cron errors found in logs',
                {'error_count': len(errors), 'failed_commands': failed_commands[:10]},
                75
            )
        elif len(errors) > 10:
            self.add_warning(
                'cron_errors',
                f'{len(errors)} cron errors found in logs',
                {'error_count': len(errors), 'failed_commands': failed_commands[:5]},
                55
            )
        elif len(errors) > 0:
            self.add_ok(
                'cron_errors',
                f'{len(errors)} minor cron errors (normal)',
                {'error_count': len(errors)}
            )
    
    def check_cron_schedules(self):
        """Check crontab entries and verify they are scheduled correctly"""
        # Check system crontab
        crontabs_to_check = [
            '/etc/crontab',
            '/etc/cron.d',
            '/var/spool/cron/crontabs'
        ]
        
        total_jobs = 0
        disabled_jobs = []
        
        for cron_path in crontabs_to_check:
            if not Path(cron_path).exists():
                continue
            
            if Path(cron_path).is_file():
                # Single file
                content = run_command(['cat', cron_path])
                if content and content.returncode == 0:
                    for line in content.stdout.split('\n'):
                        line = line.strip()
                        if line and not line.startswith('#') and not line.startswith('@'):
                            # Count as active job
                            total_jobs += 1
                        elif line.startswith('#') and any(x in line for x in ['cron', 'job', 'task']):
                            # Might be a commented-out job
                            disabled_jobs.append(line[:100])
            else:
                # Directory of cron files
                result = run_command(['find', cron_path, '-type', 'f'])
                if result and result.returncode == 0:
                    cron_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
                    total_jobs += len(cron_files)
        
        # Check user crontabs
        result = run_command(['crontab', '-l'])
        if result and result.returncode == 0:
            user_jobs = len([l for l in result.stdout.split('\n') if l.strip() and not l.strip().startswith('#')])
            total_jobs += user_jobs
        
        if total_jobs > 0:
            details = {'total_jobs': total_jobs}
            if len(disabled_jobs) > 0:
                details['disabled_jobs'] = disabled_jobs[:10]
            
            self.add_ok(
                'cron_schedules',
                f'{total_jobs} cron jobs scheduled',
                details
            )
