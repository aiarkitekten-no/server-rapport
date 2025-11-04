#!/usr/bin/env python3
"""
Security Checker
Monitors: world-writable files, RBL status, UID 0 users, sensitive files
"""

import logging
import socket
from pathlib import Path
from typing import List
import dns.resolver
import dns.reversename

from utils.base_checker import BaseChecker
from utils.common import run_command
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class SecurityChecker(BaseChecker):
    """Check security issues"""
    
    def run(self) -> List[CheckResult]:
        """Run all security checks"""
        self.clear_results()
        
        self.check_world_writable_files()
        self.check_rbl_status()
        self.check_uid_zero_users()
        self.check_sensitive_files()
        self.check_rkhunter_status()
        self.check_lynis_audit()
        self.check_clamav_status()
        
        return self.get_results()
    
    def check_world_writable_files(self):
        """Check for world-writable files in /var/www/vhosts"""
        vhosts_root = self.config.get('paths', {}).get('vhosts_root', '/var/www/vhosts')
        
        if not Path(vhosts_root).exists():
            logger.debug(f'{vhosts_root} does not exist, skipping')
            return
        
        # Find world-writable files (limit search depth and time)
        result = run_command(
            ['find', vhosts_root, '-maxdepth', '5', '-type', 'f', '-perm', '-002', '-ls'],
            timeout=60
        )
        
        if not result or result.returncode != 0:
            self.add_unknown('world_writable_files', 'Could not check for world-writable files')
            return
        
        writable_files = [line for line in result.stdout.split('\n') if line.strip()]
        
        if len(writable_files) > 100:
            self.add_critical(
                'world_writable_files',
                f'Found {len(writable_files)} world-writable files in {vhosts_root}',
                {'count': len(writable_files), 'sample': writable_files[:10]},
                90
            )
        elif len(writable_files) > 10:
            self.add_warning(
                'world_writable_files',
                f'Found {len(writable_files)} world-writable files in {vhosts_root}',
                {'count': len(writable_files), 'sample': writable_files[:10]},
                65
            )
        elif len(writable_files) > 0:
            self.add_warning(
                'world_writable_files',
                f'Found {len(writable_files)} world-writable files in {vhosts_root}',
                {'files': writable_files},
                45
            )
        else:
            self.add_ok('world_writable_files', 'No world-writable files found in vhosts')
    
    def check_rbl_status(self):
        """Check if server IP is listed in RBL databases"""
        # Get server's public IP
        ip = self.get_public_ip()
        if not ip:
            self.add_unknown('rbl_check', 'Could not determine public IP')
            return
        
        rbl_servers = self.config.get('rbl_servers', [
            'zen.spamhaus.org',
            'bl.spamcop.net',
            'b.barracudacentral.org',
            'dnsbl.sorbs.net'
        ])
        
        listed_on = []
        
        for rbl in rbl_servers:
            if self.check_rbl(ip, rbl):
                listed_on.append(rbl)
        
        if listed_on:
            self.add_critical(
                'rbl_status',
                f'Server IP {ip} is listed on {len(listed_on)} RBL(s)',
                {'ip': ip, 'rbl_servers': listed_on},
                95
            )
        else:
            self.add_ok(
                'rbl_status',
                f'Server IP {ip} is not listed on any RBL',
                {'ip': ip, 'checked_rbls': len(rbl_servers)}
            )
    
    def get_public_ip(self) -> str:
        """Get server's public IP address"""
        try:
            # Try to get from hostname
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            
            # Check if it's a public IP (not private)
            if not ip.startswith(('10.', '172.16.', '172.17.', '172.18.', '172.19.', 
                                  '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
                                  '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
                                  '172.30.', '172.31.', '192.168.', '127.')):
                return ip
            
            # Try ip route
            result = run_command(['ip', 'route', 'get', '8.8.8.8'])
            if result and result.returncode == 0:
                for part in result.stdout.split():
                    if '.' in part and part.count('.') == 3:
                        try:
                            socket.inet_aton(part)
                            return part
                        except socket.error:
                            continue
        except Exception as e:
            logger.error(f'Error getting public IP: {e}')
        
        return ''
    
    def check_rbl(self, ip: str, rbl_server: str) -> bool:
        """Check if IP is listed on specific RBL"""
        try:
            # Reverse the IP
            reversed_ip = '.'.join(reversed(ip.split('.')))
            query = f'{reversed_ip}.{rbl_server}'
            
            # Perform DNS lookup
            resolver = dns.resolver.Resolver()
            resolver.timeout = 5
            resolver.lifetime = 5
            
            try:
                answers = resolver.resolve(query, 'A')
                # Check the actual return code - Spamhaus uses specific codes
                for rdata in answers:
                    ip_result = str(rdata)
                    # 127.0.0.x = actual listing (x varies by list type)
                    # 127.255.255.254 = "Spamhaus query limit" - NOT a listing
                    # 127.255.255.255 = Error/invalid query
                    if ip_result.startswith('127.0.0.'):
                        logger.info(f'{ip} is listed on {rbl_server}: {ip_result}')
                        return True
                    elif ip_result.startswith('127.255.255.'):
                        logger.warning(f'RBL query issue for {rbl_server}: {ip_result} (query limit or error)')
                        return False
                return False
            except dns.resolver.NXDOMAIN:
                # Not listed
                return False
            except dns.resolver.Timeout:
                logger.warning(f'Timeout checking {rbl_server}')
                return False
            except Exception as e:
                logger.debug(f'Error checking {rbl_server}: {e}')
                return False
        except Exception as e:
            logger.error(f'Error in RBL check: {e}')
            return False
    
    def check_uid_zero_users(self):
        """Check for users with UID 0 (root equivalent)"""
        passwd_content = run_command(['cat', '/etc/passwd'])
        if not passwd_content or passwd_content.returncode != 0:
            self.add_unknown('uid_zero_users', 'Could not read /etc/passwd')
            return
        
        uid_zero_users = []
        for line in passwd_content.stdout.split('\n'):
            if not line.strip():
                continue
            
            parts = line.split(':')
            if len(parts) >= 3:
                username = parts[0]
                uid = parts[2]
                
                if uid == '0' and username != 'root':
                    uid_zero_users.append(username)
        
        if uid_zero_users:
            self.add_critical(
                'uid_zero_users',
                f'Found {len(uid_zero_users)} non-root user(s) with UID 0',
                {'users': uid_zero_users},
                95
            )
        else:
            self.add_ok('uid_zero_users', 'Only root has UID 0')
        
        # Also check for new sudo users
        sudo_result = run_command(['cat', '/etc/sudoers'])
        if sudo_result and sudo_result.returncode == 0:
            # Just log that we checked it
            logger.debug('Checked sudoers file')
    
    def check_sensitive_files(self):
        """Check for world-readable sensitive files"""
        vhosts_root = self.config.get('paths', {}).get('vhosts_root', '/var/www/vhosts')
        
        if not Path(vhosts_root).exists():
            return
        
        # Look for .env files, config files with passwords, private keys
        sensitive_patterns = [
            '-name', '.env',
            '-o', '-name', '.env.*',
            '-o', '-name', '*config*.php',
            '-o', '-name', '*.key',
            '-o', '-name', '*.pem',
            '-o', '-name', '*password*',
            '-o', '-name', '*secret*'
        ]
        
        result = run_command(
            ['find', vhosts_root, '-maxdepth', '6', '-type', 'f', '('] + sensitive_patterns + [')', '-perm', '-004'],
            timeout=60
        )
        
        if result and result.returncode == 0:
            readable_files = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            
            if len(readable_files) > 50:
                self.add_critical(
                    'sensitive_files_readable',
                    f'Found {len(readable_files)} world-readable sensitive files',
                    {'count': len(readable_files), 'sample': readable_files[:10]},
                    85
                )
            elif len(readable_files) > 10:
                self.add_warning(
                    'sensitive_files_readable',
                    f'Found {len(readable_files)} world-readable sensitive files',
                    {'count': len(readable_files), 'sample': readable_files[:10]},
                    70
                )
            elif len(readable_files) > 0:
                self.add_warning(
                    'sensitive_files_readable',
                    f'Found {len(readable_files)} world-readable sensitive files',
                    {'files': readable_files},
                    55
                )
            else:
                self.add_ok('sensitive_files_readable', 'No world-readable sensitive files found')
    
    def check_rkhunter_status(self):
        """Check rkhunter scan results and status"""
        # Check if rkhunter is installed
        which_result = run_command(['which', 'rkhunter'])
        if not which_result or which_result.returncode != 0:
            logger.debug('rkhunter not installed, skipping check')
            return
        
        # Parse rkhunter log file
        log_file = Path('/var/log/rkhunter.log')
        if not log_file.exists():
            # Try alternative location
            log_file = Path('/var/log/rkhunter/rkhunter.log')
        
        if not log_file.exists():
            self.add_warning(
                'rkhunter_status',
                'rkhunter is installed but no log file found',
                {'message': 'Run: rkhunter --check to generate initial scan'},
                40
            )
            return
        
        try:
            # Read last 1000 lines to get latest scan results
            result = run_command(['tail', '-n', '1000', str(log_file)])
            if not result or result.returncode != 0:
                self.add_unknown('rkhunter_status', 'Could not read rkhunter log')
                return
            
            log_content = result.stdout
            
            # Find last scan timestamp
            import re
            scan_start_pattern = r'\[ Rootkit Hunter version [\d.]+ \].*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
            matches = list(re.finditer(scan_start_pattern, log_content))
            
            last_scan_time = None
            if matches:
                last_scan_str = matches[-1].group(1)
                try:
                    from datetime import datetime
                    last_scan_time = datetime.strptime(last_scan_str, '%Y-%m-%d %H:%M:%S')
                    days_since_scan = (datetime.now() - last_scan_time).days
                except Exception as e:
                    logger.debug(f'Could not parse rkhunter timestamp: {e}')
            
            # Count warnings and infections
            warning_count = log_content.count('Warning:')
            infection_count = log_content.count('Infection:')
            rootkit_count = log_content.count('[Found]')
            
            # Check for specific issues
            issues = []
            if 'Rootkit' in log_content and '[Found]' in log_content:
                issues.append('Possible rootkit detected')
            if 'hidden process' in log_content.lower():
                issues.append('Hidden processes detected')
            if 'promiscuous' in log_content.lower() and 'found' in log_content.lower():
                issues.append('Network interfaces in promiscuous mode')
            if 'system command' in log_content.lower() and 'changed' in log_content.lower():
                issues.append('System command integrity issues')
            
            # Determine severity
            if infection_count > 0 or rootkit_count > 0 or issues:
                self.add_critical(
                    'rkhunter_status',
                    f'rkhunter detected {len(issues)} security issue(s)',
                    {
                        'issues': issues,
                        'warnings': warning_count,
                        'infections': infection_count,
                        'last_scan': last_scan_str if matches else 'Unknown'
                    },
                    95
                )
            elif warning_count > 5:
                self.add_warning(
                    'rkhunter_status',
                    f'rkhunter found {warning_count} warnings',
                    {
                        'warnings': warning_count,
                        'last_scan': last_scan_str if matches else 'Unknown',
                        'message': 'Review /var/log/rkhunter.log for details'
                    },
                    60
                )
            elif last_scan_time and days_since_scan > 7:
                self.add_warning(
                    'rkhunter_status',
                    f'rkhunter scan is {days_since_scan} days old',
                    {
                        'last_scan': last_scan_str,
                        'days_old': days_since_scan,
                        'message': 'Run: rkhunter --check --sk'
                    },
                    45
                )
            else:
                self.add_ok(
                    'rkhunter_status',
                    'rkhunter scan passed with no issues',
                    {
                        'warnings': warning_count,
                        'last_scan': last_scan_str if matches else 'Unknown'
                    }
                )
        
        except Exception as e:
            logger.error(f'Error checking rkhunter status: {e}')
            self.add_unknown('rkhunter_status', f'Error checking rkhunter: {str(e)}')
    
    def check_lynis_audit(self):
        """Check Lynis audit score and hardening recommendations"""
        # Check if lynis is installed
        which_result = run_command(['which', 'lynis'])
        if not which_result or which_result.returncode != 0:
            logger.debug('lynis not installed, skipping check')
            return
        
        # Run lynis audit in quick mode (read-only, no updates)
        # Use --quick to skip time-consuming tests
        # Use --quiet to reduce output
        result = run_command(
            ['lynis', 'audit', 'system', '--quick', '--quiet'],
            timeout=120
        )
        
        if not result or result.returncode not in [0, 1]:  # lynis returns 1 even on success sometimes
            self.add_unknown('lynis_audit', 'Could not run lynis audit')
            return
        
        output = result.stdout
        
        # Parse hardening index
        import re
        hardening_match = re.search(r'Hardening index\s*:\s*(\d+)', output)
        hardening_score = int(hardening_match.group(1)) if hardening_match else None
        
        # Parse suggestions count
        suggestions_match = re.search(r'Suggestions\s*:\s*(\d+)', output)
        suggestions_count = int(suggestions_match.group(1)) if suggestions_match else 0
        
        # Parse warnings
        warnings_match = re.search(r'Warnings\s*:\s*(\d+)', output)
        warnings_count = int(warnings_match.group(1)) if warnings_match else 0
        
        # Extract top suggestions (look for "Suggestion:" lines)
        suggestions = []
        for line in output.split('\n'):
            if 'Suggestion:' in line or 'suggestion' in line.lower():
                clean = line.strip()
                if clean and len(suggestions) < 5:  # Top 5 suggestions
                    suggestions.append(clean)
        
        # Determine severity based on hardening score
        data = {
            'hardening_score': hardening_score,
            'suggestions_count': suggestions_count,
            'warnings_count': warnings_count,
            'top_suggestions': suggestions[:3]  # Top 3
        }
        
        if hardening_score is not None:
            if hardening_score >= 80:
                self.add_ok(
                    'lynis_audit',
                    f'Lynis hardening score: {hardening_score}/100 (Excellent)',
                    data
                )
            elif hardening_score >= 65:
                self.add_ok(
                    'lynis_audit',
                    f'Lynis hardening score: {hardening_score}/100 (Good)',
                    data
                )
            elif hardening_score >= 50:
                self.add_warning(
                    'lynis_audit',
                    f'Lynis hardening score: {hardening_score}/100 (Fair)',
                    data,
                    55
                )
            else:
                self.add_warning(
                    'lynis_audit',
                    f'Lynis hardening score: {hardening_score}/100 (Needs improvement)',
                    data,
                    70
                )
        else:
            # Couldn't parse score, just report suggestions
            if warnings_count > 10:
                self.add_warning(
                    'lynis_audit',
                    f'Lynis found {warnings_count} warnings and {suggestions_count} suggestions',
                    data,
                    60
                )
            else:
                self.add_ok(
                    'lynis_audit',
                    f'Lynis audit completed ({suggestions_count} suggestions)',
                    data
                )
    
    def check_clamav_status(self):
        """Enhanced ClamAV check - scan status, coverage, signature freshness"""
        # Check if ClamAV is installed
        which_result = run_command(['which', 'clamscan'])
        if not which_result or which_result.returncode != 0:
            logger.debug('ClamAV not installed, skipping check')
            return
        
        issues = []
        warnings = []
        
        # 1. Check virus signature database age
        db_paths = [
            '/var/lib/clamav/daily.cvd',
            '/var/lib/clamav/daily.cld',
            '/var/lib/clamav/main.cvd'
        ]
        
        newest_db_age_days = None
        for db_path in db_paths:
            if Path(db_path).exists():
                result = run_command(['stat', '-c', '%Y', db_path])
                if result and result.returncode == 0:
                    try:
                        timestamp = int(result.stdout.strip())
                        from datetime import datetime
                        age_days = (datetime.now().timestamp() - timestamp) / 86400
                        if newest_db_age_days is None or age_days < newest_db_age_days:
                            newest_db_age_days = age_days
                    except Exception as e:
                        logger.debug(f'Error checking ClamAV DB age: {e}')
        
        if newest_db_age_days is not None:
            if newest_db_age_days > 7:
                issues.append(f'Virus signatures are {int(newest_db_age_days)} days old (run freshclam)')
            elif newest_db_age_days > 3:
                warnings.append(f'Virus signatures are {int(newest_db_age_days)} days old')
        
        # 2. Check recent scan logs for infections
        log_file = Path('/var/log/clamav/clamav.log')
        if not log_file.exists():
            log_file = Path('/var/log/clamav.log')
        
        infected_files = []
        scan_info = None
        
        if log_file.exists():
            try:
                result = run_command(['tail', '-n', '500', str(log_file)])
                if result and result.returncode == 0:
                    log_content = result.stdout
                    
                    # Look for infected files
                    for line in log_content.split('\n'):
                        if 'FOUND' in line and 'Infected files:' not in line:
                            infected_files.append(line.strip())
                    
                    # Get scan summary
                    import re
                    infected_match = re.search(r'Infected files:\s*(\d+)', log_content)
                    scanned_match = re.search(r'Scanned files:\s*(\d+)', log_content)
                    
                    if infected_match or scanned_match:
                        scan_info = {
                            'infected': int(infected_match.group(1)) if infected_match else 0,
                            'scanned': int(scanned_match.group(1)) if scanned_match else 0
                        }
            except Exception as e:
                logger.debug(f'Error reading ClamAV log: {e}')
        
        # 3. Check if clamd daemon is running (for on-access scanning)
        clamd_running = False
        result = run_command(['pgrep', '-x', 'clamd'])
        if result and result.returncode == 0:
            clamd_running = True
        else:
            warnings.append('clamd daemon not running (no real-time protection)')
        
        # 4. Determine overall status
        data = {
            'signature_age_days': int(newest_db_age_days) if newest_db_age_days else None,
            'clamd_running': clamd_running,
            'infected_files_count': len(infected_files),
            'infected_files_sample': infected_files[:5],
            'scan_info': scan_info,
            'issues': issues,
            'warnings': warnings
        }
        
        if infected_files:
            self.add_critical(
                'clamav_status',
                f'ClamAV detected {len(infected_files)} infected file(s)',
                data,
                90
            )
        elif issues:
            self.add_warning(
                'clamav_status',
                f'ClamAV has {len(issues)} issue(s): {", ".join(issues)}',
                data,
                65
            )
        elif warnings:
            self.add_warning(
                'clamav_status',
                f'ClamAV warnings: {", ".join(warnings)}',
                data,
                50
            )
        else:
            self.add_ok(
                'clamav_status',
                'ClamAV is operational with up-to-date signatures',
                data
            )
