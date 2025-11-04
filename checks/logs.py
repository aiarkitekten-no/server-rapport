#!/usr/bin/env python3
"""Logs Checker - Analyze log files for patterns"""

import logging
import re
from pathlib import Path
from typing import List
from collections import Counter

from utils.base_checker import BaseChecker
from utils.common import run_command
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class LogsChecker(BaseChecker):
    """Check logs for errors and patterns"""
    
    def run(self) -> List[CheckResult]:
        self.clear_results()
        self.check_log_errors()
        self.check_response_times()
        return self.get_results()
    
    def check_log_errors(self):
        """Find top repeated errors in logs"""
        log_files = ['/var/log/syslog', '/var/log/messages']
        
        all_error_patterns = Counter()
        total_errors = 0
        
        for log_file in log_files:
            if not Path(log_file).exists():
                continue
            
            result = run_command(['tail', '-n', '2000', log_file])
            if not result or result.returncode != 0:
                continue
            
            error_lines = [
                line for line in result.stdout.split('\n') 
                if any(word in line.lower() for word in ['error', 'fatal', 'critical', 'failed'])
            ]
            
            total_errors += len(error_lines)
            
            # Extract error patterns (remove timestamps, PIDs, IPs)
            for line in error_lines:
                # Remove common variable parts
                cleaned = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', line)
                cleaned = re.sub(r'\d{2}:\d{2}:\d{2}', 'TIME', cleaned)
                cleaned = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', 'IP', cleaned)
                cleaned = re.sub(r'\[\d+\]', '[PID]', cleaned)
                cleaned = re.sub(r'/\w+/\w+/[\w\-\.]+', '/path/file', cleaned)
                
                # Extract the actual error message (usually after a colon or after ERROR/FATAL)
                match = re.search(r'(?:error|fatal|critical|failed)[:\s]+(.*)', cleaned, re.IGNORECASE)
                if match:
                    error_msg = match.group(1).strip()[:100]  # First 100 chars
                    if error_msg:
                        all_error_patterns[error_msg] += 1
            
            # Don't break - process all log files
        
        if total_errors == 0:
            self.add_ok('log_errors', 'No significant errors in system logs')
            return
        
        # Categorize by frequency
        top_errors = all_error_patterns.most_common(10)
        critical_patterns = []
        warning_patterns = []
        
        for pattern, count in top_errors:
            if count > 50:
                critical_patterns.append({'pattern': pattern, 'count': count})
            elif count > 10:
                warning_patterns.append({'pattern': pattern, 'count': count})
        
        details = {
            'total_errors': total_errors,
            'unique_patterns': len(all_error_patterns),
            'top_patterns': [{'pattern': p, 'count': c} for p, c in top_errors]
        }
        
        if len(critical_patterns) > 0:
            self.add_critical(
                'log_error_patterns',
                f'{len(critical_patterns)} repeated error patterns (total: {total_errors} errors)',
                details,
                70
            )
        elif total_errors > 200:
            self.add_warning(
                'log_errors',
                f'{total_errors} errors found in system logs',
                details,
                60
            )
        elif total_errors > 50:
            self.add_warning(
                'log_errors',
                f'{total_errors} errors found in system logs',
                details,
                45
            )
        else:
            self.add_ok(
                'log_errors',
                f'{total_errors} errors in logs (normal level)',
                {'total_errors': total_errors, 'unique_patterns': len(all_error_patterns)}
            )
    
    def check_response_times(self):
        """Check for slow HTTP responses in access logs"""
        # Nginx access log format usually includes $request_time at the end
        nginx_log = Path('/var/log/nginx/access.log')
        
        if not nginx_log.exists():
            return
        
        result = run_command(['tail', '-n', '5000', str(nginx_log)])
        if not result or result.returncode != 0:
            return
        
        slow_requests = []
        total_requests = 0
        response_times = []
        
        for line in result.stdout.split('\n'):
            if not line.strip():
                continue
            
            total_requests += 1
            
            # Try to extract response time (usually last field in custom formats)
            # Common format: ... "GET /path HTTP/1.1" 200 1234 "referer" "useragent" 0.234
            parts = line.split()
            if len(parts) > 0:
                # Response time usually last field or second-to-last
                try:
                    response_time = float(parts[-1])
                    response_times.append(response_time)
                    
                    if response_time > 5.0:  # Slower than 5 seconds
                        # Extract URL
                        url_match = re.search(r'"(?:GET|POST|HEAD)\s+(\S+)\s+HTTP', line)
                        url = url_match.group(1) if url_match else 'unknown'
                        
                        slow_requests.append({
                            'url': url,
                            'response_time': response_time
                        })
                except (ValueError, IndexError):
                    # Response time not in expected format, try alternative
                    try:
                        response_time = float(parts[-2])
                        response_times.append(response_time)
                        if response_time > 5.0:
                            url_match = re.search(r'"(?:GET|POST|HEAD)\s+(\S+)\s+HTTP', line)
                            url = url_match.group(1) if url_match else 'unknown'
                            slow_requests.append({'url': url, 'response_time': response_time})
                    except (ValueError, IndexError):
                        pass
        
        if len(response_times) == 0:
            # Response time not logged, skip check
            return
        
        # Calculate statistics
        avg_response = sum(response_times) / len(response_times) if response_times else 0
        max_response = max(response_times) if response_times else 0
        
        details = {
            'slow_requests': len(slow_requests),
            'total_requests': total_requests,
            'avg_response_time': round(avg_response, 3),
            'max_response_time': round(max_response, 2),
            'slowest': sorted(slow_requests, key=lambda x: x['response_time'], reverse=True)[:10]
        }
        
        if len(slow_requests) > 100:
            self.add_critical(
                'slow_http_responses',
                f'{len(slow_requests)} requests took >5s (avg: {avg_response:.2f}s)',
                details,
                75
            )
        elif len(slow_requests) > 20:
            self.add_warning(
                'slow_http_responses',
                f'{len(slow_requests)} requests took >5s (avg: {avg_response:.2f}s)',
                details,
                60
            )
        elif avg_response > 2.0:
            self.add_warning(
                'high_avg_response_time',
                f'Average response time is high: {avg_response:.2f}s',
                details,
                50
            )
