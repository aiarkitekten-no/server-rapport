#!/usr/bin/env python3
"""Email Checker - SPF, DKIM, DMARC"""

import logging
import socket
from typing import List

from utils.base_checker import BaseChecker
from utils.common import run_command
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class EmailChecker(BaseChecker):
    """Check email configuration"""
    
    def run(self) -> List[CheckResult]:
        self.clear_results()
        self.check_mail_service()
        self.check_mail_connectivity()
        self.check_spf_dkim_dmarc()
        self.check_mail_reputation()
        return self.get_results()
    
    def check_mail_service(self):
        """Check mail services"""
        # Postfix
        result = run_command(['systemctl', 'is-active', 'postfix'])
        if result and 'active' in result.stdout:
            self.add_ok('postfix', 'Postfix is active')
        else:
            self.add_critical('postfix', 'Postfix is not active', {}, 80)
        
        # Dovecot
        result = run_command(['systemctl', 'is-active', 'dovecot'])
        if result and 'active' in result.stdout:
            self.add_ok('dovecot', 'Dovecot is active')
    
    def check_mail_connectivity(self):
        """Test basic mail server connectivity"""
        # Try to connect to SMTP port
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('localhost', 25))
            sock.close()
            
            if result == 0:
                # Try to get banner
                smtp_result = run_command(['telnet', 'localhost', '25'], timeout=3)
                if smtp_result and '220' in smtp_result.stdout:
                    self.add_ok('smtp_connectivity', 'SMTP port 25 responding')
                else:
                    self.add_ok('smtp_connectivity', 'SMTP port 25 open')
            else:
                self.add_critical(
                    'smtp_connectivity',
                    'SMTP port 25 not responding',
                    {},
                    80
                )
        except Exception as e:
            logger.debug(f'SMTP connectivity test failed: {e}')
            self.add_warning(
                'smtp_connectivity',
                'Could not test SMTP connectivity',
                {},
                50
            )
        
        # Try to connect to IMAP port
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('localhost', 143))
            sock.close()
            
            if result == 0:
                self.add_ok('imap_connectivity', 'IMAP port 143 responding')
            else:
                self.add_warning(
                    'imap_connectivity',
                    'IMAP port 143 not responding',
                    {},
                    60
                )
        except Exception as e:
            logger.debug(f'IMAP connectivity test failed: {e}')
    
    def check_spf_dkim_dmarc(self):
        """Check SPF, DKIM, and DMARC DNS records"""
        import dns.resolver
        
        # Get list of domains
        result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'domain', '--list'])
        if not result or result.returncode != 0:
            return
        
        domains = [d.strip() for d in result.stdout.split('\n') if d.strip() and not d.startswith('-')]
        
        missing_spf = []
        missing_dmarc = []
        missing_dkim = []
        
        for domain in domains[:30]:  # Check first 30 domains
            # Check SPF
            try:
                resolver = dns.resolver.Resolver()
                resolver.timeout = 3
                resolver.lifetime = 3
                
                answers = resolver.resolve(domain, 'TXT')
                has_spf = False
                for rdata in answers:
                    txt = str(rdata).strip('"')
                    if txt.startswith('v=spf1'):
                        has_spf = True
                        break
                
                if not has_spf:
                    missing_spf.append(domain)
            except:
                missing_spf.append(domain)
            
            # Check DMARC (_dmarc subdomain)
            try:
                dmarc_domain = f'_dmarc.{domain}'
                answers = resolver.resolve(dmarc_domain, 'TXT')
                has_dmarc = False
                for rdata in answers:
                    txt = str(rdata).strip('"')
                    if txt.startswith('v=DMARC1'):
                        has_dmarc = True
                        break
                
                if not has_dmarc:
                    missing_dmarc.append(domain)
            except:
                missing_dmarc.append(domain)
            
            # Check DKIM (common selectors)
            dkim_selectors = ['default', 'mail', 'dkim', 'k1', 'selector1', 'selector2']
            has_dkim = False
            for selector in dkim_selectors:
                try:
                    dkim_domain = f'{selector}._domainkey.{domain}'
                    answers = resolver.resolve(dkim_domain, 'TXT')
                    for rdata in answers:
                        txt = str(rdata).strip('"')
                        if 'v=DKIM1' in txt or 'p=' in txt:
                            has_dkim = True
                            break
                    if has_dkim:
                        break
                except:
                    continue
            
            if not has_dkim:
                missing_dkim.append(domain)
        
        # Report results
        total_checked = min(len(domains), 30)
        
        if len(missing_spf) > total_checked * 0.5:
            self.add_critical(
                'missing_spf',
                f'{len(missing_spf)}/{total_checked} domains missing SPF records',
                {'domains': missing_spf[:20]},
                80
            )
        elif len(missing_spf) > 0:
            self.add_warning(
                'missing_spf',
                f'{len(missing_spf)}/{total_checked} domains missing SPF records',
                {'domains': missing_spf[:20]},
                60
            )
        
        if len(missing_dmarc) > total_checked * 0.5:
            self.add_warning(
                'missing_dmarc',
                f'{len(missing_dmarc)}/{total_checked} domains missing DMARC records',
                {'domains': missing_dmarc[:20]},
                55
            )
        
        if len(missing_dkim) > total_checked * 0.5:
            self.add_warning(
                'missing_dkim',
                f'{len(missing_dkim)}/{total_checked} domains missing DKIM records',
                {'domains': missing_dkim[:20]},
                50
            )
        
        if len(missing_spf) == 0 and len(missing_dmarc) == 0:
            self.add_ok(
                'email_authentication',
                f'All {total_checked} domains have SPF and DMARC',
                {'checked': total_checked}
            )
    
    def check_mail_reputation(self):
        """Check for mail rejection patterns (554/550 errors)"""
        from pathlib import Path
        
        mail_log = Path('/var/log/mail.log')
        if not mail_log.exists():
            mail_log = Path('/var/log/maillog')
        
        if not mail_log.exists():
            return
        
        result = run_command(['tail', '-n', '5000', str(mail_log)])
        if not result or result.returncode != 0:
            return
        
        # Count rejection patterns
        rejections_554 = result.stdout.count('554 ')
        rejections_550 = result.stdout.count('550 ')
        blocked = result.stdout.count('blocked')
        blacklisted = result.stdout.count('blacklist')
        
        total_rejections = rejections_554 + rejections_550
        
        details = {
            '554_rejections': rejections_554,
            '550_rejections': rejections_550,
            'blocked_count': blocked,
            'blacklist_mentions': blacklisted
        }
        
        if total_rejections > 500 or blacklisted > 10:
            self.add_critical(
                'mail_reputation',
                f'High mail rejection rate: {total_rejections} rejections, {blacklisted} blacklist mentions',
                details,
                85
            )
        elif total_rejections > 100:
            self.add_warning(
                'mail_reputation',
                f'Elevated mail rejection rate: {total_rejections} rejections',
                details,
                65
            )
        elif total_rejections > 0:
            self.add_ok(
                'mail_reputation',
                f'{total_rejections} mail rejections (normal level)',
                details
            )
