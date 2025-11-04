#!/usr/bin/env python3
"""Backup Checker"""

import logging
from pathlib import Path
from typing import List

from utils.base_checker import BaseChecker
from utils.common import run_command, get_file_age_hours
from utils.severity import CheckResult, calculate_age_severity

logger = logging.getLogger(__name__)


class BackupChecker(BaseChecker):
    """Check backup status"""
    
    def run(self) -> List[CheckResult]:
        self.clear_results()
        self.check_recent_backups()
        self.check_external_mounts()
        self.check_logrotate_status()
        return self.get_results()
    
    def check_recent_backups(self):
        """Check for recent successful backups"""
        backup_root = self.config.get('paths', {}).get('backup_root', '/var/lib/psa/dumps')
        
        if not Path(backup_root).exists():
            self.add_warning('backups', 'Backup directory does not exist', {}, 70)
            return
        
        result = run_command(['find', backup_root, '-type', 'f', '-name', '*.xml', '-mtime', '-2'])
        if result and result.returncode == 0:
            recent_backups = [f for f in result.stdout.split('\n') if f.strip()]
            
            if not recent_backups:
                self.add_critical('recent_backups', 'No backups found in last 48 hours', {}, 90)
            else:
                self.add_ok('recent_backups', f'Found {len(recent_backups)} recent backups')
    
    def check_external_mounts(self):
        """Check external mounts (NFS, CIFS, Hetzner Storage Box etc)"""
        # Read /etc/fstab for remote mounts
        fstab_result = run_command(['cat', '/etc/fstab'])
        if not fstab_result or fstab_result.returncode != 0:
            return
        
        remote_mounts = []
        for line in fstab_result.stdout.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split()
            if len(parts) >= 3:
                device = parts[0]
                mountpoint = parts[1]
                fstype = parts[2]
                
                # Identify remote filesystems
                if fstype in ['nfs', 'nfs4', 'cifs', 'smbfs'] or ':' in device or '//' in device:
                    remote_mounts.append({
                        'device': device,
                        'mountpoint': mountpoint,
                        'fstype': fstype
                    })
        
        if len(remote_mounts) == 0:
            return
        
        # Check if remote mounts are actually mounted
        df_result = run_command(['df', '-h'])
        if not df_result or df_result.returncode != 0:
            return
        
        mounted_paths = set()
        for line in df_result.stdout.split('\n'):
            parts = line.split()
            if len(parts) >= 6:
                mounted_paths.add(parts[5])
        
        unmounted = []
        low_space = []
        
        for mount in remote_mounts:
            mountpoint = mount['mountpoint']
            
            # Check if mounted
            if mountpoint not in mounted_paths:
                unmounted.append(mount)
                continue
            
            # Check available space
            df_mount_result = run_command(['df', '-h', mountpoint])
            if df_mount_result and df_mount_result.returncode == 0:
                lines = df_mount_result.stdout.split('\n')
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 5:
                        use_percent_str = parts[4].rstrip('%')
                        try:
                            use_percent = int(use_percent_str)
                            if use_percent > 90:
                                low_space.append({
                                    **mount,
                                    'usage': use_percent
                                })
                        except ValueError:
                            pass
        
        # Report issues
        if len(unmounted) > 0:
            self.add_critical(
                'unmounted_remote_storage',
                f'{len(unmounted)} remote mounts are not mounted',
                {'unmounted': unmounted},
                90
            )
        
        if len(low_space) > 0:
            self.add_warning(
                'remote_storage_low_space',
                f'{len(low_space)} remote mounts have low space',
                {'mounts': low_space},
                70
            )
        
        if len(unmounted) == 0 and len(low_space) == 0:
            self.add_ok(
                'external_mounts',
                f'All {len(remote_mounts)} remote mounts are healthy',
                {'mount_count': len(remote_mounts)}
            )
    
    def check_logrotate_status(self):
        """Check logrotate configuration and unrotated files"""
        # Check when logrotate last ran
        logrotate_status = Path('/var/lib/logrotate/status')
        if not logrotate_status.exists():
            logrotate_status = Path('/var/lib/logrotate.status')
        
        if logrotate_status.exists():
            age_hours = get_file_age_hours(logrotate_status)
            if age_hours and age_hours > 48:
                self.add_warning(
                    'logrotate_not_running',
                    f'logrotate status file is {age_hours:.0f} hours old',
                    {'age_hours': age_hours},
                    65
                )
        
        # Check for large unrotated log files
        result = run_command(['find', '/var/log', '-name', '*.log', '-size', '+100M', '-mtime', '+7'], timeout=30)
        if result and result.returncode == 0:
            unrotated = [f.strip() for f in result.stdout.split('\n') if f.strip()]
            
            if len(unrotated) > 10:
                self.add_warning(
                    'unrotated_logs',
                    f'{len(unrotated)} large old log files not rotated',
                    {'files': unrotated[:10]},
                    60
                )
            elif len(unrotated) > 0:
                self.add_ok(
                    'unrotated_logs',
                    f'{len(unrotated)} large old logs (check logrotate)',
                    {'count': len(unrotated)}
                )
