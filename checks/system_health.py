#!/usr/bin/env python3
"""
System Health Checker
Monitors: uptime, load, CPU, RAM, swap, disk, I/O, SMART, RAID, kernel, dmesg
"""

import logging
import re
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta

from utils.base_checker import BaseChecker
from utils.common import run_command, safe_read_file, format_bytes, format_percentage
from utils.severity import CheckResult, SeverityLevel, calculate_disk_severity, calculate_count_severity

logger = logging.getLogger(__name__)


class SystemHealthChecker(BaseChecker):
    """Check system health metrics"""
    
    def run(self) -> List[CheckResult]:
        """Run all system health checks"""
        self.clear_results()
        
        self.check_uptime()
        self.check_load_average()
        self.check_cpu_info()
        self.check_memory()
        self.check_swap()
        self.check_disk_space()
        self.check_inode_usage()
        self.check_disk_io()
        self.check_smart_status()
        self.check_raid_status()
        self.check_file_changes()
        self.check_reboot_required()
        self.check_kernel_version()
        self.check_dmesg_errors()
        
        return self.get_results()
    
    def check_uptime(self):
        """Check system uptime and last reboot"""
        result = run_command(['uptime', '-s'])
        if result and result.returncode == 0:
            boot_time_str = result.stdout.strip()
            try:
                boot_time = datetime.strptime(boot_time_str, '%Y-%m-%d %H:%M:%S')
                uptime_delta = datetime.now() - boot_time
                days = uptime_delta.days
                
                self.add_ok(
                    'uptime',
                    f'System uptime: {days} days',
                    {'boot_time': boot_time_str, 'uptime_days': days}
                )
            except ValueError:
                self.add_unknown('uptime', 'Could not parse boot time')
        else:
            self.add_unknown('uptime', 'Could not determine uptime')
    
    def check_load_average(self):
        """Check system load average"""
        result = run_command(['cat', '/proc/loadavg'])
        if not result or result.returncode != 0:
            self.add_unknown('load_average', 'Could not read load average')
            return
        
        try:
            parts = result.stdout.strip().split()
            load_1 = float(parts[0])
            load_5 = float(parts[1])
            load_15 = float(parts[2])
            
            # Get CPU count
            cpu_result = run_command(['nproc'])
            cpu_count = 1
            if cpu_result and cpu_result.returncode == 0:
                cpu_count = int(cpu_result.stdout.strip())
            
            # Calculate load per CPU
            load_per_cpu = load_5 / cpu_count
            
            thresholds = self.config.get('thresholds', {})
            warning_threshold = thresholds.get('load_per_cpu_warning', 2.0)
            critical_threshold = thresholds.get('load_per_cpu_critical', 4.0)
            
            details = {
                'load_1min': load_1,
                'load_5min': load_5,
                'load_15min': load_15,
                'cpu_count': cpu_count,
                'load_per_cpu': round(load_per_cpu, 2)
            }
            
            if load_per_cpu >= critical_threshold:
                score = 85
                self.add_critical(
                    'load_average',
                    f'High load: {load_5:.2f} (load per CPU: {load_per_cpu:.2f})',
                    details,
                    score
                )
            elif load_per_cpu >= warning_threshold:
                score = 50
                self.add_warning(
                    'load_average',
                    f'Elevated load: {load_5:.2f} (load per CPU: {load_per_cpu:.2f})',
                    details,
                    score
                )
            else:
                self.add_ok(
                    'load_average',
                    f'Load normal: {load_5:.2f} (load per CPU: {load_per_cpu:.2f})',
                    details
                )
        except (ValueError, IndexError) as e:
            self.add_unknown('load_average', f'Error parsing load: {e}')
    
    def check_cpu_info(self):
        """Check CPU temperature and throttling"""
        # Try to read temperature from thermal zones
        thermal_path = Path('/sys/class/thermal')
        temps = []
        
        if thermal_path.exists():
            for zone in thermal_path.glob('thermal_zone*/temp'):
                try:
                    temp_millic = int(zone.read_text().strip())
                    temp_c = temp_millic / 1000
                    temps.append(temp_c)
                except Exception:
                    continue
        
        if temps:
            max_temp = max(temps)
            avg_temp = sum(temps) / len(temps)
            
            thresholds = self.config.get('thresholds', {})
            warning = thresholds.get('cpu_temp_warning', 75)
            critical = thresholds.get('cpu_temp_critical', 85)
            
            details = {
                'max_temp_c': round(max_temp, 1),
                'avg_temp_c': round(avg_temp, 1),
                'sensor_count': len(temps)
            }
            
            if max_temp >= critical:
                self.add_critical(
                    'cpu_temperature',
                    f'CPU temperature critical: {max_temp:.1f}°C',
                    details,
                    90
                )
            elif max_temp >= warning:
                self.add_warning(
                    'cpu_temperature',
                    f'CPU temperature high: {max_temp:.1f}°C',
                    details,
                    60
                )
            else:
                self.add_ok(
                    'cpu_temperature',
                    f'CPU temperature normal: {max_temp:.1f}°C',
                    details
                )
        else:
            # Temperature sensors not available, not an error
            logger.debug('No CPU temperature sensors found')
    
    def check_memory(self):
        """Check RAM usage"""
        result = run_command(['free', '-b'])
        if not result or result.returncode != 0:
            self.add_unknown('memory', 'Could not read memory info')
            return
        
        try:
            lines = result.stdout.strip().split('\n')
            mem_line = lines[1].split()
            
            total = int(mem_line[1])
            used = int(mem_line[2])
            available = int(mem_line[6]) if len(mem_line) > 6 else int(mem_line[3])
            
            used_percent = format_percentage(used, total)
            
            thresholds = self.config.get('thresholds', {})
            warning = thresholds.get('memory_usage_warning', 85)
            critical = thresholds.get('memory_usage_critical', 95)
            
            details = {
                'total_bytes': total,
                'used_bytes': used,
                'available_bytes': available,
                'used_percent': used_percent,
                'total_human': format_bytes(total),
                'used_human': format_bytes(used),
                'available_human': format_bytes(available)
            }
            
            # Check for OOM kills
            oom_count = self.count_oom_kills()
            if oom_count > 0:
                details['oom_kills_24h'] = oom_count
            
            score = calculate_disk_severity(used_percent, warning, critical)
            
            if used_percent >= critical:
                self.add_critical(
                    'memory_usage',
                    f'Critical memory usage: {used_percent}% ({format_bytes(used)}/{format_bytes(total)})',
                    details,
                    score
                )
            elif used_percent >= warning:
                self.add_warning(
                    'memory_usage',
                    f'High memory usage: {used_percent}% ({format_bytes(used)}/{format_bytes(total)})',
                    details,
                    score
                )
            else:
                self.add_ok(
                    'memory_usage',
                    f'Memory usage normal: {used_percent}% ({format_bytes(used)}/{format_bytes(total)})',
                    details
                )
        except (ValueError, IndexError) as e:
            self.add_unknown('memory', f'Error parsing memory info: {e}')
    
    def count_oom_kills(self) -> int:
        """Count OOM kills in last 24 hours from journal"""
        result = run_command(['journalctl', '--since', '24 hours ago', '--no-pager'], timeout=10)
        if result and result.returncode == 0:
            return result.stdout.count('Out of memory') + result.stdout.count('oom-kill')
        return 0
    
    def check_swap(self):
        """Check swap usage"""
        result = run_command(['free', '-b'])
        if not result or result.returncode != 0:
            self.add_unknown('swap', 'Could not read swap info')
            return
        
        try:
            lines = result.stdout.strip().split('\n')
            if len(lines) < 3:
                self.add_ok('swap', 'No swap configured', {'swap_enabled': False})
                return
            
            swap_line = lines[2].split()
            total = int(swap_line[1])
            
            if total == 0:
                self.add_ok('swap', 'No swap configured', {'swap_enabled': False})
                return
            
            used = int(swap_line[2])
            used_percent = format_percentage(used, total)
            
            thresholds = self.config.get('thresholds', {})
            warning = thresholds.get('swap_usage_warning', 50)
            critical = thresholds.get('swap_usage_critical', 80)
            
            details = {
                'total_bytes': total,
                'used_bytes': used,
                'used_percent': used_percent,
                'total_human': format_bytes(total),
                'used_human': format_bytes(used)
            }
            
            score = calculate_disk_severity(used_percent, warning, critical)
            
            if used_percent >= critical:
                self.add_critical(
                    'swap_usage',
                    f'Critical swap usage: {used_percent}%',
                    details,
                    score
                )
            elif used_percent >= warning:
                self.add_warning(
                    'swap_usage',
                    f'High swap usage: {used_percent}%',
                    details,
                    score
                )
            else:
                if used_percent > 0:
                    self.add_ok(
                        'swap_usage',
                        f'Swap usage: {used_percent}%',
                        details
                    )
                else:
                    self.add_ok('swap', 'Swap not in use', details)
        except (ValueError, IndexError) as e:
            self.add_unknown('swap', f'Error parsing swap info: {e}')
    
    def check_disk_space(self):
        """Check disk space usage"""
        result = run_command(['df', '-B1'])
        if not result or result.returncode != 0:
            self.add_unknown('disk_space', 'Could not read disk info')
            return
        
        thresholds = self.config.get('thresholds', {})
        warning = thresholds.get('disk_usage_warning', 75)
        critical = thresholds.get('disk_usage_critical', 90)
        
        lines = result.stdout.strip().split('\n')[1:]  # Skip header
        issues_found = False
        
        for line in lines:
            parts = line.split()
            if len(parts) < 6:
                continue
            
            filesystem = parts[0]
            size = int(parts[1])
            used = int(parts[2])
            available = int(parts[3])
            use_percent = int(parts[4].rstrip('%'))
            mount = parts[5]
            
            # Skip tmpfs, devtmpfs, and other virtual filesystems
            if filesystem.startswith(('tmpfs', 'devtmpfs', 'none', 'udev')):
                continue
            
            # Skip very small filesystems
            if size < 100 * 1024 * 1024:  # < 100 MB
                continue
            
            details = {
                'filesystem': filesystem,
                'mount': mount,
                'size_bytes': size,
                'used_bytes': used,
                'available_bytes': available,
                'use_percent': use_percent,
                'size_human': format_bytes(size),
                'used_human': format_bytes(used),
                'available_human': format_bytes(available)
            }
            
            score = calculate_disk_severity(use_percent, warning, critical)
            
            if use_percent >= critical:
                issues_found = True
                self.add_critical(
                    f'disk_space_{mount.replace("/", "_")}',
                    f'Critical disk space on {mount}: {use_percent}% used',
                    details,
                    score
                )
            elif use_percent >= warning:
                issues_found = True
                self.add_warning(
                    f'disk_space_{mount.replace("/", "_")}',
                    f'Low disk space on {mount}: {use_percent}% used',
                    details,
                    score
                )
        
        if not issues_found:
            self.add_ok('disk_space', 'All filesystems have adequate space')
    
    def check_inode_usage(self):
        """Check inode usage"""
        result = run_command(['df', '-i'])
        if not result or result.returncode != 0:
            self.add_unknown('inodes', 'Could not read inode info')
            return
        
        thresholds = self.config.get('thresholds', {})
        warning = thresholds.get('inode_usage_warning', 75)
        critical = thresholds.get('inode_usage_critical', 90)
        
        lines = result.stdout.strip().split('\n')[1:]
        issues_found = False
        
        for line in lines:
            parts = line.split()
            if len(parts) < 6:
                continue
            
            filesystem = parts[0]
            use_percent_str = parts[4]
            mount = parts[5]
            
            # Skip virtual filesystems
            if filesystem.startswith(('tmpfs', 'devtmpfs', 'none', 'udev')):
                continue
            
            if use_percent_str == '-':
                continue
            
            try:
                use_percent = int(use_percent_str.rstrip('%'))
            except ValueError:
                continue
            
            details = {
                'filesystem': filesystem,
                'mount': mount,
                'use_percent': use_percent
            }
            
            score = calculate_disk_severity(use_percent, warning, critical)
            
            if use_percent >= critical:
                issues_found = True
                self.add_critical(
                    f'inodes_{mount.replace("/", "_")}',
                    f'Critical inode usage on {mount}: {use_percent}%',
                    details,
                    score
                )
            elif use_percent >= warning:
                issues_found = True
                self.add_warning(
                    f'inodes_{mount.replace("/", "_")}',
                    f'High inode usage on {mount}: {use_percent}%',
                    details,
                    score
                )
        
        if not issues_found:
            self.add_ok('inodes', 'Inode usage is normal on all filesystems')
    
    def check_disk_io(self):
        """Check disk I/O statistics using iostat if available"""
        result = run_command(['which', 'iostat'])
        if not result or result.returncode != 0:
            logger.debug('iostat not available, skipping I/O check')
            return
        
        result = run_command(['iostat', '-x', '1', '2'])
        if not result or result.returncode != 0:
            return
        
        # Parse iostat output - this is complex, so we'll just check for high await times
        lines = result.stdout.split('\n')
        high_latency_devices = []
        
        for line in lines:
            if not line.strip() or line.startswith('Linux') or line.startswith('Device') or line.startswith('avg-cpu'):
                continue
            
            parts = line.split()
            if len(parts) < 10:
                continue
            
            try:
                device = parts[0]
                await_ms = float(parts[9])  # await column
                
                if await_ms > 100:  # > 100ms is concerning
                    high_latency_devices.append((device, await_ms))
            except (ValueError, IndexError):
                continue
        
        if high_latency_devices:
            details = {'devices': [{'device': d, 'await_ms': a} for d, a in high_latency_devices]}
            worst_latency = max(a for d, a in high_latency_devices)
            
            if worst_latency > 500:
                self.add_critical(
                    'disk_io_latency',
                    f'Very high disk I/O latency detected (up to {worst_latency:.1f}ms)',
                    details,
                    80
                )
            else:
                self.add_warning(
                    'disk_io_latency',
                    f'High disk I/O latency detected (up to {worst_latency:.1f}ms)',
                    details,
                    55
                )
        else:
            self.add_ok('disk_io_latency', 'Disk I/O latency is normal')
    
    def check_smart_status(self):
        """Check SMART status of disks"""
        # Check if smartctl is available
        result = run_command(['which', 'smartctl'])
        if not result or result.returncode != 0:
            logger.debug('smartctl not available, skipping SMART check')
            return
        
        # Find all block devices
        devices_result = run_command(['lsblk', '-nd', '-o', 'NAME,TYPE'])
        if not devices_result or devices_result.returncode != 0:
            return
        
        disks = []
        for line in devices_result.stdout.split('\n'):
            parts = line.split()
            if len(parts) >= 2 and parts[1] == 'disk':
                disks.append(f'/dev/{parts[0]}')
        
        issues_found = False
        
        for disk in disks:
            result = run_command(['smartctl', '-H', disk], timeout=10)
            if not result:
                continue
            
            if 'PASSED' in result.stdout:
                continue
            elif 'FAILED' in result.stdout or 'FAILING' in result.stdout:
                issues_found = True
                self.add_critical(
                    f'smart_{disk.replace("/", "_")}',
                    f'SMART health check FAILED for {disk}',
                    {'device': disk, 'status': 'FAILED'},
                    95
                )
            elif result.returncode != 0:
                # May not support SMART
                logger.debug(f'SMART not supported or error for {disk}')
        
        if disks and not issues_found:
            self.add_ok('smart_health', f'SMART health check passed for all disks ({len(disks)} checked)')
    
    def check_raid_status(self):
        """Check RAID status (mdadm, ZFS, LVM)"""
        # Check mdadm
        if Path('/proc/mdstat').exists():
            mdstat = safe_read_file('/proc/mdstat')
            if mdstat:
                if 'FAILED' in mdstat or '_' in mdstat:  # _ indicates failed disk
                    self.add_critical(
                        'raid_mdadm',
                        'RAID degraded or failed (mdadm)',
                        {'mdstat': mdstat[:500]},
                        95
                    )
                elif 'active' in mdstat:
                    self.add_ok('raid_mdadm', 'RAID arrays are healthy (mdadm)')
        
        # Check ZFS
        result = run_command(['which', 'zpool'])
        if result and result.returncode == 0:
            status_result = run_command(['zpool', 'status', '-x'])
            if status_result:
                if 'all pools are healthy' in status_result.stdout.lower():
                    self.add_ok('raid_zfs', 'All ZFS pools are healthy')
                else:
                    self.add_critical(
                        'raid_zfs',
                        'ZFS pool issues detected',
                        {'status': status_result.stdout[:500]},
                        90
                    )
    
    def check_file_changes(self):
        """Check for rapidly growing files (logs, dumps)"""
        # We need to track file sizes over time using baseline
        baseline_path = Path('baselines/file_sizes.json')
        current_sizes = {}
        
        # Paths to monitor for rapid growth
        monitor_paths = [
            '/var/log',
            '/tmp',
            '/var/crash',
            '/var/lib/psa/dumps'
        ]
        
        # Get current sizes of large files
        for path in monitor_paths:
            if not Path(path).exists():
                continue
            
            result = run_command(['find', path, '-type', 'f', '-size', '+100M', '-ls'], timeout=30)
            if result and result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if not line.strip():
                        continue
                    
                    parts = line.split()
                    if len(parts) >= 11:
                        size_bytes = int(parts[6])
                        filepath = ' '.join(parts[10:])
                        current_sizes[filepath] = size_bytes
        
        # Load previous baseline if it exists
        from utils.common import load_json_file, save_json_file
        previous_sizes = load_json_file(baseline_path) if baseline_path.exists() else {}
        
        # Find files that have grown significantly (>500MB growth)
        rapidly_growing = []
        for filepath, current_size in current_sizes.items():
            if filepath in previous_sizes:
                previous_size = previous_sizes[filepath]
                growth = current_size - previous_size
                
                if growth > 500 * 1024 * 1024:  # 500MB growth
                    growth_mb = growth / (1024 * 1024)
                    rapidly_growing.append({
                        'file': filepath,
                        'growth_mb': round(growth_mb, 1),
                        'current_size_mb': round(current_size / (1024 * 1024), 1)
                    })
        
        # Save current state for next run
        if not self.config.get('general', {}).get('read_only', True):
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            save_json_file(baseline_path, current_sizes)
        
        # Report rapidly growing files
        if len(rapidly_growing) > 5:
            self.add_critical(
                'rapidly_growing_files',
                f'{len(rapidly_growing)} files growing rapidly',
                {'files': rapidly_growing[:10]},
                75
            )
        elif len(rapidly_growing) > 0:
            self.add_warning(
                'rapidly_growing_files',
                f'{len(rapidly_growing)} files growing rapidly',
                {'files': rapidly_growing},
                60
            )
        
        # Also check for very large log files (static check)
        result = run_command(['find', '/var/log', '-type', 'f', '-size', '+1G'], timeout=30)
        if result and result.returncode == 0:
            large_files = [f for f in result.stdout.split('\n') if f.strip()]
            if len(large_files) > 0:
                self.add_warning(
                    'large_log_files',
                    f'Found {len(large_files)} log files larger than 1GB',
                    {'files': large_files[:10]},
                    45
                )
    
    def check_reboot_required(self):
        """Check if system reboot is required"""
        if Path('/var/run/reboot-required').exists():
            reason = safe_read_file('/var/run/reboot-required.pkgs')
            packages = []
            if reason:
                packages = [p.strip() for p in reason.split('\n') if p.strip()]
            
            self.add_warning(
                'reboot_required',
                'System reboot required',
                {'packages': packages},
                60
            )
        else:
            self.add_ok('reboot_required', 'No reboot required')
    
    def check_kernel_version(self):
        """Check kernel version and EOL status"""
        result = run_command(['uname', '-r'])
        if not result or result.returncode != 0:
            return
        
        kernel_version = result.stdout.strip()
        
        # Get kernel base version (e.g., "5.15" from "5.15.0-91-generic")
        import re
        match = re.match(r'(\d+\.\d+)', kernel_version)
        if not match:
            self.add_ok('kernel_version', f'Running kernel: {kernel_version}', {'version': kernel_version})
            return
        
        base_version = match.group(1)
        major, minor = map(int, base_version.split('.'))
        
        # EOL kernel database (based on kernel.org LTS/mainline status as of Nov 2025)
        eol_kernels = {
            '4.4': {'eol': True, 'eol_date': '2022-02'},
            '4.9': {'eol': True, 'eol_date': '2023-01'},
            '4.14': {'eol': True, 'eol_date': '2024-01'},
            '4.19': {'eol': False, 'eol_date': '2024-12'},  # Still supported
            '5.4': {'eol': False, 'eol_date': '2025-12'},   # LTS
            '5.10': {'eol': False, 'eol_date': '2026-12'},  # LTS
            '5.15': {'eol': False, 'eol_date': '2027-10'},  # LTS
            '6.1': {'eol': False, 'eol_date': '2026-12'},   # LTS
            '6.6': {'eol': False, 'eol_date': '2029-12'},   # LTS
        }
        
        details = {
            'version': kernel_version,
            'base_version': base_version,
            'major': major,
            'minor': minor
        }
        
        # Check if kernel is EOL
        if base_version in eol_kernels:
            kernel_info = eol_kernels[base_version]
            details['eol_date'] = kernel_info['eol_date']
            
            if kernel_info['eol']:
                self.add_critical(
                    'kernel_eol',
                    f'Kernel {base_version} is EOL (ended {kernel_info["eol_date"]})',
                    details,
                    85
                )
            else:
                self.add_ok(
                    'kernel_version',
                    f'Running kernel: {kernel_version} (LTS, EOL: {kernel_info["eol_date"]})',
                    details
                )
        else:
            # Unknown kernel version - might be too old or too new
            if major < 4 or (major == 4 and minor < 4):
                self.add_critical(
                    'kernel_very_old',
                    f'Kernel {base_version} is very old and likely EOL',
                    details,
                    90
                )
            elif major >= 6 and minor > 6:
                # Newer than our database, probably fine
                self.add_ok(
                    'kernel_version',
                    f'Running kernel: {kernel_version} (newer than EOL database)',
                    details
                )
            else:
                self.add_warning(
                    'kernel_unknown',
                    f'Kernel {base_version} EOL status unknown',
                    details,
                    40
                )
    
    def check_dmesg_errors(self):
        """Check dmesg for recent errors"""
        result = run_command(['dmesg', '-l', 'err,crit,alert,emerg', '-T'], timeout=10)
        if not result or result.returncode != 0:
            return
        
        recent_errors = []
        for line in result.stdout.split('\n')[-50:]:  # Last 50 error lines
            if line.strip():
                recent_errors.append(line)
        
        if len(recent_errors) > 10:
            self.add_warning(
                'dmesg_errors',
                f'Found {len(recent_errors)} recent kernel errors',
                {'recent_errors': recent_errors[:10]},
                50
            )
        elif len(recent_errors) > 0:
            self.add_ok(
                'dmesg_errors',
                f'Found {len(recent_errors)} kernel errors (within normal range)'
            )
