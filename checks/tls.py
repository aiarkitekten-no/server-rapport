#!/usr/bin/env python3
"""TLS/SSL Checker - Certificate expiry and configuration"""

import logging
from pathlib import Path
from typing import List
from datetime import datetime
import ssl
import socket

from utils.base_checker import BaseChecker
from utils.common import run_command
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class TLSChecker(BaseChecker):
    """Check TLS certificates"""
    
    def run(self) -> List[CheckResult]:
        self.clear_results()
        self.check_certificate_expiry()
        self.check_weak_ciphers()
        self.check_key_cert_mismatch()
        return self.get_results()
    
    def check_certificate_expiry(self):
        """Check for expiring certificates in all vhosts"""
        # Get all domains from Plesk
        domains = []
        result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'domain', '--list'])
        if result and result.returncode == 0:
            domains = [d.strip() for d in result.stdout.split('\n') if d.strip() and not d.startswith('-')]
        
        # Scan Plesk certificate directories
        cert_dirs = [
            '/usr/local/psa/var/certificates',
            '/opt/psa/var/certificates',
            '/etc/letsencrypt/live'
        ]
        
        all_certs = {}
        expiring_soon = []
        invalid_certs = []
        
        for cert_dir in cert_dirs:
            if not Path(cert_dir).exists():
                continue
            
            result = run_command(['find', cert_dir, '-name', '*.crt', '-o', '-name', 'cert.pem'])
            if result and result.returncode == 0:
                cert_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
                
                for cert_file in cert_files:
                    # Skip if already checked (some certs are symlinks)
                    real_path = str(Path(cert_file).resolve())
                    if real_path in all_certs:
                        continue
                    
                    cert_info = self.check_cert_details(cert_file)
                    if cert_info:
                        all_certs[real_path] = cert_info
                        
                        # Check if cert is valid
                        if not cert_info.get('is_valid', True):
                            invalid_certs.append(cert_info)
                        
                        # Check expiry
                        days_left = cert_info.get('days_left')
                        if days_left is not None:
                            if days_left < 30:
                                cert_info['file'] = cert_file
                                expiring_soon.append(cert_info)
        
        thresholds = self.config.get('thresholds', {})
        warning_days = thresholds.get('tls_expiry_warning', 30)
        critical_days = thresholds.get('tls_expiry_critical', 7)
        
        # Report results
        critical_certs = [c for c in expiring_soon if c['days_left'] < critical_days]
        warning_certs = [c for c in expiring_soon if c['days_left'] >= critical_days and c['days_left'] < warning_days]
        
        if len(invalid_certs) > 0:
            self.add_critical(
                'invalid_certificates',
                f'{len(invalid_certs)} invalid/corrupted certificates found',
                {'invalid_certs': invalid_certs[:10]},
                90
            )
        
        if len(critical_certs) > 0:
            min_days = min(c['days_left'] for c in critical_certs)
            self.add_critical(
                'cert_expiry_critical',
                f'{len(critical_certs)} certificates expiring in < {critical_days} days (min: {min_days} days)',
                {'certificates': critical_certs[:10]},
                95
            )
        
        if len(warning_certs) > 0:
            self.add_warning(
                'cert_expiry_warning',
                f'{len(warning_certs)} certificates expiring in < {warning_days} days',
                {'certificates': warning_certs[:10]},
                60
            )
        
        if len(expiring_soon) == 0 and len(invalid_certs) == 0:
            self.add_ok(
                'tls_certificates',
                f'All {len(all_certs)} certificates are valid and not expiring soon'
            )
    
    def check_cert_details(self, cert_file: str) -> dict:
        """Check certificate validity and expiry"""
        try:
            result = run_command(['openssl', 'x509', '-enddate', '-noout', '-in', cert_file])
            if not result or result.returncode != 0:
                return {'file': cert_file, 'is_valid': False, 'error': 'Could not parse certificate'}
            
            # Parse expiry date: notAfter=Nov  4 12:00:00 2026 GMT
            date_str = result.stdout.strip().replace('notAfter=', '')
            expiry_date = datetime.strptime(date_str, '%b %d %H:%M:%S %Y %Z')
            days_left = (expiry_date - datetime.now()).days
            
            # Get subject (domain name)
            subject_result = run_command(['openssl', 'x509', '-subject', '-noout', '-in', cert_file])
            subject = 'unknown'
            if subject_result and subject_result.returncode == 0:
                subject = subject_result.stdout.strip().replace('subject=', '')
            
            return {
                'subject': subject,
                'expiry_date': expiry_date.strftime('%Y-%m-%d'),
                'days_left': days_left,
                'is_valid': True
            }
        except Exception as e:
            logger.debug(f'Error checking cert {cert_file}: {e}')
            return {'file': cert_file, 'is_valid': False, 'error': str(e)}
    
    def check_weak_ciphers(self):
        """Check for weak TLS ciphers and protocols"""
        # Get list of domains to test
        result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'domain', '--list'])
        if not result or result.returncode != 0:
            return
        
        domains = [d.strip() for d in result.stdout.split('\n') if d.strip() and not d.startswith('-')]
        
        weak_ciphers_found = []
        old_tls_versions = []
        
        # Weak cipher patterns to detect
        weak_patterns = ['RC4', 'DES', 'MD5', 'NULL', 'anon', 'EXPORT']
        
        for domain in domains[:10]:  # Test first 10 domains
            # Test TLS connection
            openssl_result = run_command(
                ['openssl', 's_client', '-connect', f'{domain}:443', '-showcerts'],
                timeout=10,
                input_data='\n'
            )
            
            if not openssl_result or openssl_result.returncode != 0:
                continue
            
            output = openssl_result.stdout + openssl_result.stderr if hasattr(openssl_result, 'stderr') else openssl_result.stdout
            
            # Check for weak ciphers
            for pattern in weak_patterns:
                if pattern in output:
                    weak_ciphers_found.append({
                        'domain': domain,
                        'weak_cipher': pattern
                    })
                    break
            
            # Check TLS version
            if 'TLSv1 ' in output or 'SSLv' in output:
                old_tls_versions.append(domain)
        
        # Report weak ciphers
        if len(weak_ciphers_found) > 0:
            self.add_critical(
                'weak_ciphers',
                f'{len(weak_ciphers_found)} domains using weak ciphers',
                {'domains': weak_ciphers_found[:10]},
                85
            )
        
        # Report old TLS versions
        if len(old_tls_versions) > 5:
            self.add_critical(
                'old_tls_versions',
                f'{len(old_tls_versions)} domains using TLS 1.0 or SSL',
                {'domains': old_tls_versions[:20]},
                80
            )
        elif len(old_tls_versions) > 0:
            self.add_warning(
                'old_tls_versions',
                f'{len(old_tls_versions)} domains using old TLS versions',
                {'domains': old_tls_versions},
                60
            )
    
    def check_key_cert_mismatch(self):
        """Check if private keys match their certificates"""
        cert_dirs = [
            '/usr/local/psa/var/certificates',
            '/opt/psa/var/certificates'
        ]
        
        mismatches = []
        total_checked = 0
        
        for cert_dir in cert_dirs:
            if not Path(cert_dir).exists():
                continue
            
            # Find certificate files
            cert_result = run_command(['find', cert_dir, '-name', '*.crt'])
            if not cert_result or cert_result.returncode != 0:
                continue
            
            cert_files = [f.strip() for f in cert_result.stdout.split('\n') if f.strip()]
            
            for cert_file in cert_files[:30]:  # Check first 30
                total_checked += 1
                
                # Look for corresponding private key
                key_file = cert_file.replace('.crt', '.key')
                if not Path(key_file).exists():
                    # Try .pem extension
                    key_file = cert_file.replace('.crt', '.pem')
                    if not Path(key_file).exists():
                        continue
                
                # Get certificate modulus
                cert_modulus_result = run_command(['openssl', 'x509', '-noout', '-modulus', '-in', cert_file])
                if not cert_modulus_result or cert_modulus_result.returncode != 0:
                    continue
                
                cert_modulus = cert_modulus_result.stdout.strip()
                
                # Get key modulus
                key_modulus_result = run_command(['openssl', 'rsa', '-noout', '-modulus', '-in', key_file])
                if not key_modulus_result or key_modulus_result.returncode != 0:
                    continue
                
                key_modulus = key_modulus_result.stdout.strip()
                
                # Compare moduli
                if cert_modulus != key_modulus:
                    mismatches.append({
                        'cert_file': cert_file,
                        'key_file': key_file
                    })
        
        if len(mismatches) > 0:
            self.add_critical(
                'key_cert_mismatch',
                f'{len(mismatches)} certificate/key pairs do not match',
                {'mismatches': mismatches[:10]},
                95
            )
        elif total_checked > 0:
            self.add_ok(
                'key_cert_match',
                f'All {total_checked} checked certificates match their private keys',
                {'checked': total_checked}
            )
