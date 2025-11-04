#!/usr/bin/env python3
"""
Database Checker - Monitor MariaDB/MySQL health
"""

import logging
import re
from typing import List

from utils.base_checker import BaseChecker
from utils.common import run_command
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class DatabaseChecker(BaseChecker):
    """Check database health"""
    
    def run(self) -> List[CheckResult]:
        self.clear_results()
        
        self.check_mysql_status()
        return self.get_results()
    
    def check_mysql_status(self):
        """Check MySQL/MariaDB status"""
        result = run_command(['mysqladmin', 'status'])
        if not result or result.returncode != 0:
            # Try with credentials
            result = run_command(['mysql', '-e', 'SHOW STATUS'])
            if not result or result.returncode != 0:
                self.add_unknown('mysql_status', 'Could not connect to MySQL')
                return
        
        # Get connection stats and limits
        result = run_command(['mysql', '-e', "SHOW VARIABLES LIKE 'max_connections'; SHOW STATUS LIKE '%connection%'"])
        if not result or result.returncode != 0:
            return
        
        lines = result.stdout.split('\n')
        max_connections = 0
        max_used_connections = 0
        threads_connected = 0
        connections = 0
        aborted_connects = 0
        
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                if 'max_connections' in line:
                    max_connections = int(parts[1])
                elif 'Max_used_connections' in line:
                    max_used_connections = int(parts[1])
                elif 'Threads_connected' in line:
                    threads_connected = int(parts[1])
                elif parts[0] == 'Connections':
                    connections = int(parts[1])
                elif 'Aborted_connects' in line:
                    aborted_connects = int(parts[1])
        
        if max_connections == 0:
            return
        
        # Calculate usage percentage
        usage_percent = (max_used_connections / max_connections) * 100
        current_usage = (threads_connected / max_connections) * 100
        
        thresholds = self.config.get('thresholds', {})
        warning = thresholds.get('mysql_connections_warning', 70)
        critical = thresholds.get('mysql_connections_critical', 90)
        
        details = {
            'max_connections': max_connections,
            'max_used_connections': max_used_connections,
            'threads_connected': threads_connected,
            'total_connections': connections,
            'aborted_connects': aborted_connects,
            'usage_percent': round(usage_percent, 1),
            'current_usage_percent': round(current_usage, 1)
        }
        
        # Check for high aborted connections (possible attack or config issue)
        if connections > 0:
            abort_rate = (aborted_connects / connections) * 100
            if abort_rate > 10:
                self.add_warning(
                    'mysql_aborted_connections',
                    f'High rate of aborted connections: {abort_rate:.1f}%',
                    {'abort_rate': abort_rate, 'aborted_connects': aborted_connects},
                    65
                )
        
        # Check connection usage
        if usage_percent >= critical:
            self.add_critical(
                'mysql_connections',
                f'MySQL connection limit nearly reached: {max_used_connections}/{max_connections} ({usage_percent:.0f}%)',
                details,
                85
            )
        elif usage_percent >= warning:
            self.add_warning(
                'mysql_connections',
                f'High MySQL connection usage: {max_used_connections}/{max_connections} ({usage_percent:.0f}%)',
                details,
                60
            )
        else:
            self.add_ok(
                'mysql_connections',
                f'MySQL connections: {max_used_connections}/{max_connections} peak ({usage_percent:.0f}%)',
                details
            )
