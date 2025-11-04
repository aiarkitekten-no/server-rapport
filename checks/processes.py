#!/usr/bin/env python3
"""Process Checker - Monitor zombie processes and resource hogs"""

import logging
from typing import List

from utils.base_checker import BaseChecker
from utils.common import run_command
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class ProcessesChecker(BaseChecker):
    """Check process health"""
    
    def run(self) -> List[CheckResult]:
        self.clear_results()
        
        self.check_zombie_processes()
        self.check_high_cpu_processes()
        
        return self.get_results()
    
    def check_zombie_processes(self):
        """Check for zombie processes and identify parents"""
        # Get zombie processes with parent info
        result = run_command(['ps', 'axo', 'pid,ppid,stat,comm'])
        if not result or result.returncode != 0:
            return
        
        zombies = []
        parent_pids = {}
        
        for line in result.stdout.split('\n')[1:]:  # Skip header
            parts = line.split(None, 3)
            if len(parts) >= 4:
                pid, ppid, stat, comm = parts
                if 'Z' in stat or '<defunct>' in comm:
                    zombies.append({
                        'pid': pid,
                        'ppid': ppid,
                        'command': comm
                    })
                    parent_pids[ppid] = parent_pids.get(ppid, 0) + 1
        
        if len(zombies) == 0:
            return
        
        # Get parent process info
        parent_info = []
        for ppid, count in parent_pids.items():
            result = run_command(['ps', '-p', ppid, '-o', 'pid,comm'])
            if result and result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    parent_info.append({
                        'pid': ppid,
                        'zombie_children': count,
                        'command': lines[1].split(None, 1)[1] if len(lines[1].split(None, 1)) > 1 else 'unknown'
                    })
        
        details = {
            'zombie_count': len(zombies),
            'zombies': zombies[:20],
            'problematic_parents': parent_info
        }
        
        # Generate recommendations
        recommendations = []
        if parent_info:
            for parent in parent_info:
                recommendations.append(f"Kill/restart PID {parent['pid']} ({parent['command']}) which has {parent['zombie_children']} zombie children")
        
        details['recommendations'] = recommendations
        
        if len(zombies) > 50:
            self.add_critical(
                'zombie_processes',
                f'{len(zombies)} zombie processes detected',
                details,
                70
            )
        elif len(zombies) > 10:
            self.add_warning(
                'zombie_processes',
                f'{len(zombies)} zombie processes detected',
                details,
                55
            )
        else:
            self.add_ok(
                'zombie_processes',
                f'{len(zombies)} zombie processes (normal)',
                {'count': len(zombies), 'parents': len(parent_info)}
            )
    
    def check_high_cpu_processes(self):
        """Check for processes consuming excessive CPU"""
        result = run_command(['ps', 'aux', '--sort=-%cpu'])
        if not result or result.returncode != 0:
            return
        
        thresholds = self.config.get('thresholds', {})
        cpu_threshold = thresholds.get('high_cpu_threshold', 90)
        
        lines = result.stdout.split('\n')[1:11]  # Top 10
        high_cpu = []
        
        for line in lines:
            parts = line.split(None, 10)
            if len(parts) > 10:
                try:
                    cpu = float(parts[2])
                    if cpu > cpu_threshold:
                        high_cpu.append({
                            'user': parts[0],
                            'pid': parts[1],
                            'cpu': cpu,
                            'mem': float(parts[3]),
                            'vsz': parts[4],
                            'rss': parts[5],
                            'command': parts[10][:100]
                        })
                except (ValueError, IndexError):
                    pass
        
        if not high_cpu:
            return
        
        # Check if these are long-running or transient
        details = {
            'high_cpu_processes': high_cpu,
            'threshold': cpu_threshold
        }
        
        if len(high_cpu) > 3:
            self.add_critical(
                'high_cpu_processes',
                f'{len(high_cpu)} processes using >{cpu_threshold}% CPU',
                details,
                75
            )
        else:
            self.add_warning(
                'high_cpu_processes',
                f'{len(high_cpu)} processes using >{cpu_threshold}% CPU',
                details,
                60
            )
