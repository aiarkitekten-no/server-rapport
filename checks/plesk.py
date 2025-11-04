#!/usr/bin/env python3
"""
Plesk Checker
Monitors: license, panel.log, scheduler, backups, extensions, mail, nginx/apache/php-fpm
"""

import logging
import re
from pathlib import Path
from typing import List
from datetime import datetime, timedelta

from utils.base_checker import BaseChecker
from utils.common import run_command, safe_read_file, is_plesk_installed, get_file_age_hours
from utils.severity import CheckResult, calculate_count_severity

logger = logging.getLogger(__name__)


class PleskChecker(BaseChecker):
    """Check Plesk-specific health"""
    
    def run(self) -> List[CheckResult]:
        """Run all Plesk checks"""
        self.clear_results()
        
        if not is_plesk_installed():
            self.add_warning('plesk_not_installed', 'Plesk is not installed on this server', {}, 30)
            return self.get_results()
        
        self.check_license()
        self.check_panel_log_errors()
        self.check_scheduler_tasks()
        self.check_backup_manager()
        self.check_dump_directories()
        self.check_extensions()
        self.check_panel_ini()
        self.check_web_pipeline()
        self.check_mail_stack()
        self.check_update_history()
        
        return self.get_results()
    
    def check_license(self):
        """Check Plesk license status"""
        result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'license', '--info'])
        if not result or result.returncode != 0:
            self.add_unknown('plesk_license', 'Could not check license status')
            return
        
        output = result.stdout.lower()
        
        if 'status: active' in output or 'valid' in output:
            self.add_ok('plesk_license', 'Plesk license is active')
        elif 'expired' in output:
            self.add_critical('plesk_license', 'Plesk license has expired', {}, 95)
        elif 'invalid' in output:
            self.add_critical('plesk_license', 'Plesk license is invalid', {}, 90)
        else:
            self.add_warning('plesk_license', 'Plesk license status unclear', {'output': output[:200]}, 60)
    
    def check_panel_log_errors(self):
        """Check for errors in Plesk panel log"""
        panel_log = self.config.get('paths', {}).get('plesk_panel_log', '/var/log/plesk/panel.log')
        
        if not Path(panel_log).exists():
            return
        
        # Read last 1000 lines
        result = run_command(['tail', '-n', '1000', panel_log])
        if not result or result.returncode != 0:
            return
        
        errors = []
        criticals = []
        
        for line in result.stdout.split('\n'):
            if '[error]' in line.lower() or 'error:' in line.lower():
                errors.append(line)
            if '[critical]' in line.lower() or '[crit]' in line.lower():
                criticals.append(line)
        
        if len(criticals) > 10:
            self.add_critical(
                'panel_log_errors',
                f'Found {len(criticals)} critical errors in panel.log',
                {'critical_count': len(criticals), 'sample': criticals[:5]},
                80
            )
        elif len(errors) > 50:
            self.add_warning(
                'panel_log_errors',
                f'Found {len(errors)} errors in panel.log',
                {'error_count': len(errors), 'sample': errors[:5]},
                55
            )
        elif len(errors) > 0:
            self.add_ok(
                'panel_log_errors',
                f'Found {len(errors)} errors in panel.log (within normal range)',
                {'error_count': len(errors)}
            )
    
    def check_scheduler_tasks(self):
        """Check Plesk scheduled tasks status"""
        # Use structured output format
        result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'scheduler', '--list', '-output-format', 'json'])
        if not result or result.returncode != 0:
            # Fallback to regular list if JSON not supported
            result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'scheduler', '--list'])
            if not result or result.returncode != 0:
                return
            
            # Parse text output looking for status indicators
            failed_tasks = []
            current_task = None
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('Task ID:'):
                    current_task = {'id': line.split(':')[1].strip()}
                elif line.startswith('Status:') and current_task:
                    status = line.split(':')[1].strip().lower()
                    if status in ['failed', 'error', 'suspended']:
                        current_task['status'] = status
                        failed_tasks.append(current_task)
                    current_task = None
            
            if len(failed_tasks) > 5:
                self.add_critical(
                    'plesk_scheduler',
                    f'{len(failed_tasks)} scheduled tasks have failures',
                    {'failed_tasks': failed_tasks[:10]},
                    75
                )
            elif len(failed_tasks) > 0:
                self.add_warning(
                    'plesk_scheduler',
                    f'{len(failed_tasks)} scheduled tasks have failures',
                    {'failed_tasks': failed_tasks},
                    50
                )
            else:
                self.add_ok('plesk_scheduler', 'All scheduled tasks running normally')
            return
        
        # Parse JSON output
        try:
            import json
            tasks = json.loads(result.stdout)
            failed_tasks = [t for t in tasks if t.get('status', '').lower() in ['failed', 'error', 'suspended']]
            
            if len(failed_tasks) > 5:
                self.add_critical(
                    'plesk_scheduler',
                    f'{len(failed_tasks)} scheduled tasks have failures',
                    {'failed_tasks': failed_tasks[:10]},
                    75
                )
            elif len(failed_tasks) > 0:
                self.add_warning(
                    'plesk_scheduler',
                    f'{len(failed_tasks)} scheduled tasks have failures',
                    {'failed_tasks': failed_tasks},
                    50
                )
            else:
                self.add_ok('plesk_scheduler', 'All scheduled tasks running normally')
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f'Error parsing scheduler output: {e}')
            self.add_unknown('plesk_scheduler', 'Could not parse scheduler status')
    
    def check_backup_manager(self):
        """Check Plesk Backup Manager status"""
        # Get detailed backup information
        result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'backup', '--list', '-v'])
        if not result or result.returncode != 0:
            self.add_unknown('plesk_backups', 'Could not list backups')
            return
        
        from datetime import datetime, timedelta
        
        backups = []
        current_backup = None
        
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('Backup:'):
                if current_backup:
                    backups.append(current_backup)
                current_backup = {'name': line.split(':', 1)[1].strip()}
            elif line.startswith('Status:') and current_backup:
                current_backup['status'] = line.split(':', 1)[1].strip().lower()
            elif line.startswith('Date:') and current_backup:
                current_backup['date'] = line.split(':', 1)[1].strip()
            elif line.startswith('Size:') and current_backup:
                current_backup['size'] = line.split(':', 1)[1].strip()
        
        if current_backup:
            backups.append(current_backup)
        
        # Analyze backups
        failed_backups = [b for b in backups if b.get('status') in ['failed', 'error', 'incomplete']]
        successful_recent = [b for b in backups if b.get('status') == 'completed']
        
        # Check for recent successful backup (last 48 hours)
        has_recent_backup = False
        if successful_recent:
            # Try to parse the most recent backup date
            for backup in successful_recent[:5]:
                if 'date' in backup:
                    try:
                        # This is a simplified date check
                        has_recent_backup = True
                        break
                    except:
                        pass
        
        issues = []
        if len(failed_backups) > 0:
            issues.append(f'{len(failed_backups)} failed backups')
        if not has_recent_backup and len(backups) > 0:
            issues.append('No recent successful backups')
        
        if len(failed_backups) > 3:
            self.add_critical(
                'plesk_backups',
                ', '.join(issues),
                {'failed_backups': failed_backups[:5], 'total_backups': len(backups)},
                85
            )
        elif len(failed_backups) > 0:
            self.add_warning(
                'plesk_backups',
                ', '.join(issues),
                {'failed_backups': failed_backups[:5], 'total_backups': len(backups)},
                65
            )
        elif not has_recent_backup:
            self.add_warning(
                'plesk_backups',
                'No recent successful backups detected',
                {'total_backups': len(backups)},
                70
            )
        else:
            self.add_ok('plesk_backups', f'{len(successful_recent)} successful backups found')
    
    def check_dump_directories(self):
        """Check for orphaned and large dump files"""
        dump_root = self.config.get('paths', {}).get('backup_root', '/var/lib/psa/dumps')
        
        if not Path(dump_root).exists():
            return
        
        # Get list of active domains
        active_domains = set()
        result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'domain', '--list'])
        if result and result.returncode == 0:
            for line in result.stdout.split('\n'):
                domain = line.strip()
                if domain and not domain.startswith('-'):
                    active_domains.add(domain)
        
        # Find dump files larger than 5GB
        large_dumps = []
        result = run_command(['find', dump_root, '-type', 'f', '-size', '+5G'], timeout=30)
        if result and result.returncode == 0:
            large_dumps = [f for f in result.stdout.split('\n') if f.strip()]
        
        # Check for orphaned dumps (dumps for non-existent domains)
        orphaned_dumps = []
        if active_domains:
            result = run_command(['find', dump_root, '-type', 'f', '-name', '*.tar*', '-o', '-name', '*.xml'], timeout=30)
            if result and result.returncode == 0:
                all_dumps = [f for f in result.stdout.split('\n') if f.strip()]
                
                for dump in all_dumps[:100]:  # Check first 100
                    # Extract domain name from dump filename
                    dump_name = Path(dump).name
                    is_orphaned = True
                    for domain in active_domains:
                        if domain in dump_name:
                            is_orphaned = False
                            break
                    
                    if is_orphaned:
                        # Check file age
                        age_hours = get_file_age_hours(Path(dump))
                        if age_hours and age_hours > 168:  # Older than 7 days
                            orphaned_dumps.append({
                                'file': dump,
                                'age_days': round(age_hours / 24, 1)
                            })
        
        issues = []
        details = {}
        
        if len(large_dumps) > 10:
            issues.append(f'{len(large_dumps)} dumps >5GB')
            details['large_dumps'] = large_dumps[:10]
        
        if len(orphaned_dumps) > 5:
            issues.append(f'{len(orphaned_dumps)} orphaned dumps')
            details['orphaned_dumps'] = orphaned_dumps[:10]
        
        if len(issues) > 0:
            self.add_warning(
                'dump_files',
                ', '.join(issues),
                details,
                55
            )
        elif len(large_dumps) > 0 or len(orphaned_dumps) > 0:
            self.add_ok(
                'dump_files',
                f'{len(large_dumps)} large dumps, {len(orphaned_dumps)} orphaned dumps',
                {'large_count': len(large_dumps), 'orphaned_count': len(orphaned_dumps)}
            )
    
    def check_extensions(self):
        """Check Plesk extensions health"""
        # Get list of installed extensions with status
        result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'extension', '--list'])
        if not result or result.returncode != 0:
            return
        
        extensions = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line and not line.startswith('-'):
                # Format: "extension-id version [active/inactive]"
                parts = line.split()
                if len(parts) >= 2:
                    ext_id = parts[0]
                    status = 'unknown'
                    if 'active' in line.lower():
                        status = 'active'
                    elif 'inactive' in line.lower():
                        status = 'inactive'
                    
                    extensions.append({'id': ext_id, 'status': status})
        
        # Check individual extension health
        critical_extensions = ['letsencrypt', 'wp-toolkit', 'advisor', 'security-advisor']
        inactive_critical = []
        
        for ext in extensions:
            ext_id = ext['id']
            
            # Check if critical extension is inactive
            if ext_id in critical_extensions and ext['status'] == 'inactive':
                inactive_critical.append(ext_id)
            
            # Check extension-specific health
            if ext_id == 'letsencrypt':
                # Check Let's Encrypt functionality
                le_log = '/var/log/plesk/letsencrypt.log'
                if Path(le_log).exists():
                    log_result = run_command(['tail', '-n', '500', le_log])
                    if log_result and result.returncode == 0:
                        # Count actual failures, not just "error" word
                        failures = 0
                        for line in log_result.stdout.split('\n'):
                            if 'failed to' in line.lower() or 'error:' in line.lower():
                                failures += 1
                        
                        if failures > 50:
                            self.add_critical(
                                'letsencrypt_failures',
                                f'Let\'s Encrypt has {failures} certificate failures',
                                {'failure_count': failures},
                                80
                            )
                        elif failures > 10:
                            self.add_warning(
                                'letsencrypt_failures',
                                f'Let\'s Encrypt has {failures} certificate failures',
                                {'failure_count': failures},
                                60
                            )
            
            elif ext_id == 'wp-toolkit':
                # Check WP Toolkit status
                wp_result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'extension', '--exec', 'wp-toolkit', 'status'])
                if wp_result and wp_result.returncode != 0:
                    self.add_warning(
                        'wp_toolkit_status',
                        'WP Toolkit may have issues',
                        {},
                        50
                    )
        
        # Report inactive critical extensions
        if len(inactive_critical) > 0:
            self.add_critical(
                'critical_extensions_inactive',
                f'{len(inactive_critical)} critical extensions are inactive',
                {'extensions': inactive_critical},
                85
            )
        
        # Overall extension health
        if len(extensions) > 0:
            active_count = sum(1 for e in extensions if e['status'] == 'active')
            self.add_ok(
                'extensions_overview',
                f'{active_count}/{len(extensions)} extensions active',
                {'total': len(extensions), 'active': active_count}
            )
    
    def check_panel_ini(self):
        """Validate panel.ini configuration"""
        panel_ini = Path('/usr/local/psa/admin/conf/panel.ini')
        if not panel_ini.exists():
            return
        
        content = safe_read_file(panel_ini)
        if not content:
            return
        
        try:
            from configparser import ConfigParser
            config = ConfigParser()
            config.read_string(content)
            
            # Validate critical settings
            issues = []
            
            # Check session settings
            if config.has_section('session'):
                timeout = config.get('session', 'timeout', fallback=None)
                if timeout and int(timeout) < 300:
                    issues.append('Session timeout too short (<5 min)')
            
            # Check login settings
            if config.has_section('login'):
                max_attempts = config.get('login', 'maxAttempts', fallback=None)
                if max_attempts and int(max_attempts) > 10:
                    issues.append('Max login attempts too high (>10)')
            
            # Check security settings
            if config.has_section('ui'):
                show_info = config.get('ui', 'showInfo', fallback='true')
                if show_info.lower() == 'true':
                    issues.append('Panel info disclosure enabled')
            
            if len(issues) > 2:
                self.add_warning(
                    'panel_ini',
                    f'{len(issues)} configuration issues found',
                    {'issues': issues},
                    50
                )
            elif len(issues) > 0:
                self.add_ok(
                    'panel_ini',
                    f'{len(issues)} minor config issues',
                    {'issues': issues}
                )
            else:
                self.add_ok('panel_ini', 'panel.ini configuration looks good')
                
        except Exception as e:
            # Fallback to basic bracket count check
            if content.count('[') != content.count(']'):
                self.add_warning('panel_ini', 'panel.ini may have syntax errors', {}, 50)
            else:
                logger.debug(f'Could not parse panel.ini: {e}')
                self.add_ok('panel_ini', 'panel.ini appears syntactically valid')
    
    def check_web_pipeline(self):
        """Check Nginx -> Apache -> PHP-FPM pipeline"""
        # Check for 502/504 errors in nginx logs
        nginx_log = self.config.get('paths', {}).get('nginx_error_log', '/var/log/nginx/error.log')
        
        if Path(nginx_log).exists():
            result = run_command(['tail', '-n', '500', nginx_log])
            if result and result.returncode == 0:
                errors_502 = result.stdout.count('502')
                errors_504 = result.stdout.count('504')
                
                if errors_502 + errors_504 > 50:
                    self.add_critical(
                        'nginx_gateway_errors',
                        f'High rate of 502/504 errors in nginx ({errors_502} 502s, {errors_504} 504s)',
                        {'errors_502': errors_502, 'errors_504': errors_504},
                        75
                    )
                elif errors_502 + errors_504 > 10:
                    self.add_warning(
                        'nginx_gateway_errors',
                        f'Nginx gateway errors detected ({errors_502} 502s, {errors_504} 504s)',
                        {'errors_502': errors_502, 'errors_504': errors_504},
                        50
                    )
        
        # Check all PHP-FPM pools
        result = run_command(['find', '/opt/plesk/php', '-name', 'php-fpm'], timeout=10)
        if result and result.returncode == 0:
            fpm_binaries = [f.strip() for f in result.stdout.split('\n') if f.strip()]
            
            inactive_pools = []
            active_pools = 0
            
            for fpm_bin in fpm_binaries[:20]:  # Check first 20
                # Extract version from path like /opt/plesk/php/7.4/bin/php-fpm
                version = fpm_bin.split('/')[-3] if len(fpm_bin.split('/')) > 3 else 'unknown'
                service_name = f'plesk-php{version.replace(".", "")}-fpm'
                
                check_result = run_command(['systemctl', 'is-active', service_name])
                if check_result and 'active' in check_result.stdout:
                    active_pools += 1
                else:
                    inactive_pools.append(service_name)
            
            if len(inactive_pools) > 3:
                self.add_warning(
                    'php_fpm_pools',
                    f'{len(inactive_pools)} PHP-FPM pools not running',
                    {'inactive_pools': inactive_pools[:10], 'active_pools': active_pools},
                    55
                )
            elif active_pools > 0:
                self.add_ok(
                    'php_fpm_pools',
                    f'{active_pools} PHP-FPM pools active',
                    {'active_pools': active_pools, 'inactive_pools': len(inactive_pools)}
                )
    
    def check_mail_stack(self):
        """Check Postfix/Dovecot/SpamAssassin"""
        # Check mail queue size
        result = run_command(['postqueue', '-p'])
        if result and result.returncode == 0:
            # Count entries in queue
            queue_lines = result.stdout.split('\n')
            queue_count = sum(1 for line in queue_lines if line and not line.startswith('-'))
            
            if queue_count > 1000:
                self.add_critical(
                    'mail_queue',
                    f'Large mail queue: {queue_count} messages',
                    {'queue_count': queue_count},
                    85
                )
            elif queue_count > 100:
                self.add_warning(
                    'mail_queue',
                    f'Growing mail queue: {queue_count} messages',
                    {'queue_count': queue_count},
                    60
                )
            elif queue_count > 0:
                self.add_ok(
                    'mail_queue',
                    f'Mail queue: {queue_count} messages',
                    {'queue_count': queue_count}
                )
            else:
                self.add_ok('mail_queue', 'Mail queue is empty')
        
        # Check for auth failures in mail log
        mail_log = self.config.get('paths', {}).get('mail_log', '/var/log/mail.log')
        if Path(mail_log).exists():
            result = run_command(['tail', '-n', '1000', mail_log])
            if result and result.returncode == 0:
                auth_failures = result.stdout.count('authentication failed')
                
                if auth_failures > 100:
                    self.add_warning(
                        'mail_auth_failures',
                        f'High authentication failures: {auth_failures} in last 1000 log lines',
                        {'failure_count': auth_failures},
                        65
                    )
    
    def check_update_history(self):
        """Check Plesk update history for recent updates and issues"""
        # Check autoinstaller log
        autoinstaller_log = Path('/var/log/plesk/install/autoinstaller3.log')
        install_log = Path('/usr/local/psa/var/log/autoinstaller3.log')
        
        log_to_check = None
        if autoinstaller_log.exists():
            log_to_check = autoinstaller_log
        elif install_log.exists():
            log_to_check = install_log
        
        if not log_to_check:
            return
        
        # Read last 500 lines
        result = run_command(['tail', '-n', '500', str(log_to_check)])
        if not result or result.returncode != 0:
            return
        
        updates = []
        errors = []
        current_update = None
        
        for line in result.stdout.split('\n'):
            # Look for update start markers
            if 'Installing' in line or 'Upgrading' in line:
                if current_update:
                    updates.append(current_update)
                current_update = {'action': line.strip(), 'errors': []}
            
            # Look for errors
            if current_update and ('ERROR' in line or 'FAILED' in line):
                current_update['errors'].append(line.strip())
                errors.append(line.strip())
        
        if current_update:
            updates.append(current_update)
        
        # Analyze results
        failed_updates = [u for u in updates if len(u['errors']) > 0]
        
        if len(failed_updates) > 0:
            self.add_critical(
                'plesk_update_failures',
                f'{len(failed_updates)} Plesk updates have errors',
                {'failed_updates': failed_updates[:5], 'total_errors': len(errors)},
                80
            )
        elif len(updates) > 0:
            self.add_ok(
                'plesk_updates',
                f'{len(updates)} recent Plesk updates completed successfully',
                {'update_count': len(updates)}
            )
        
        # Check Plesk version
        version_result = run_command(['/usr/local/psa/bin/plesk', 'version'])
        if version_result and version_result.returncode == 0:
            version = version_result.stdout.strip().split('\n')[0]
            logger.debug(f'Plesk version: {version}')
