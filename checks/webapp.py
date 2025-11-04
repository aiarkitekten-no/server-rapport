#!/usr/bin/env python3
"""WebApp Checker - HTTP errors, HSTS, mixed content, 404s"""

import logging
import re
from pathlib import Path
from typing import List
from collections import Counter

from utils.base_checker import BaseChecker
from utils.common import run_command
from utils.severity import CheckResult

logger = logging.getLogger(__name__)


class WebAppChecker(BaseChecker):
    """Check web application health"""
    
    def run(self) -> List[CheckResult]:
        self.clear_results()
        self.check_http_errors_per_site()
        self.check_404_floods()
        self.check_hsts_mixed_content()
        return self.get_results()
    
    def check_http_errors_per_site(self):
        """Check for HTTP 5xx errors per vhost"""
        vhosts_root = self.config.get('paths', {}).get('vhosts_root', '/var/www/vhosts')
        
        if not Path(vhosts_root).exists():
            return
        
        # Find all access logs in vhosts
        result = run_command(['find', vhosts_root, '-name', 'access_log', '-o', '-name', 'access.log'], timeout=30)
        if not result or result.returncode != 0:
            return
        
        log_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
        
        site_errors = {}
        
        for log_file in log_files[:50]:  # Limit to 50 sites
            # Extract domain from path like /var/www/vhosts/domain.com/logs/access_log
            domain = 'unknown'
            parts = log_file.split('/')
            for i, part in enumerate(parts):
                if part == 'vhosts' and i + 1 < len(parts):
                    domain = parts[i + 1]
                    break
            
            # Count 5xx errors in last 2000 lines
            tail_result = run_command(['tail', '-n', '2000', log_file])
            if tail_result and tail_result.returncode == 0:
                errors_500 = tail_result.stdout.count(' 500 ')
                errors_502 = tail_result.stdout.count(' 502 ')
                errors_503 = tail_result.stdout.count(' 503 ')
                errors_504 = tail_result.stdout.count(' 504 ')
                
                total_5xx = errors_500 + errors_502 + errors_503 + errors_504
                
                if total_5xx > 10:
                    site_errors[domain] = {
                        'total_5xx': total_5xx,
                        '500': errors_500,
                        '502': errors_502,
                        '503': errors_503,
                        '504': errors_504
                    }
        
        # Report sites with errors
        if len(site_errors) > 0:
            worst_sites = sorted(site_errors.items(), key=lambda x: x[1]['total_5xx'], reverse=True)[:10]
            total_errors = sum(e['total_5xx'] for e in site_errors.values())
            
            if total_errors > 500:
                self.add_critical(
                    'http_5xx_per_site',
                    f'{len(site_errors)} sites with 5xx errors (total: {total_errors})',
                    {'sites': [{'domain': d, **e} for d, e in worst_sites]},
                    80
                )
            elif total_errors > 100:
                self.add_warning(
                    'http_5xx_per_site',
                    f'{len(site_errors)} sites with 5xx errors (total: {total_errors})',
                    {'sites': [{'domain': d, **e} for d, e in worst_sites]},
                    60
                )
            else:
                self.add_ok(
                    'http_5xx_per_site',
                    f'{len(site_errors)} sites with minor 5xx errors',
                    {'site_count': len(site_errors), 'total_errors': total_errors}
                )
    
    def check_404_floods(self):
        """Check for 404 floods and identify top referers"""
        nginx_log = '/var/log/nginx/access.log'
        
        try:
            if not Path(nginx_log).exists():
                return
        except PermissionError:
            logger.debug('Permission denied checking nginx log')
            return
        
        result = run_command(['tail', '-n', '10000', nginx_log])
        if not result or result.returncode != 0:
            return
        
        # Parse 404 errors and collect URLs and referers
        error_404_urls = Counter()
        referers = Counter()
        
        for line in result.stdout.split('\n'):
            if ' 404 ' in line:
                # Extract URL (between "GET/POST and HTTP/1")
                match = re.search(r'"(?:GET|POST|HEAD)\s+(\S+)\s+HTTP', line)
                if match:
                    url = match.group(1)
                    error_404_urls[url] += 1
                
                # Extract referer
                ref_match = re.search(r'"([^"]*)" "([^"]*)"$', line)
                if ref_match and ref_match.group(1) != '-':
                    referer = ref_match.group(1)
                    referers[referer] += 1
        
        total_404 = sum(error_404_urls.values())
        
        if total_404 > 1000:
            top_urls = error_404_urls.most_common(10)
            top_referers = referers.most_common(5)
            
            self.add_critical(
                '404_flood',
                f'{total_404} 404 errors detected',
                {
                    'total_404': total_404,
                    'top_urls': [{'url': u, 'count': c} for u, c in top_urls],
                    'top_referers': [{'referer': r, 'count': c} for r, c in top_referers]
                },
                75
            )
        elif total_404 > 200:
            top_urls = error_404_urls.most_common(5)
            
            self.add_warning(
                '404_errors',
                f'{total_404} 404 errors detected',
                {'total_404': total_404, 'top_urls': [{'url': u, 'count': c} for u, c in top_urls]},
                50
            )
    
    def check_hsts_mixed_content(self):
        """Check HSTS headers and scan for mixed content warnings"""
        # Get list of domains
        result = run_command(['/usr/local/psa/bin/plesk', 'bin', 'domain', '--list'])
        if not result or result.returncode != 0:
            return
        
        domains = [d.strip() for d in result.stdout.split('\n') if d.strip() and not d.startswith('-')]
        
        no_hsts = []
        mixed_content_sites = []
        
        for domain in domains[:20]:  # Check first 20 domains
            # Check HSTS header via curl
            curl_result = run_command(['curl', '-sI', '-m', '5', f'https://{domain}'], timeout=6)
            if curl_result and curl_result.returncode == 0:
                has_hsts = 'strict-transport-security' in curl_result.stdout.lower()
                
                if not has_hsts:
                    no_hsts.append(domain)
                
                # Check for mixed content by fetching page
                content_result = run_command(['curl', '-sL', '-m', '10', f'https://{domain}'], timeout=11)
                if content_result and content_result.returncode == 0:
                    # Look for http:// resources in HTML
                    html = content_result.stdout
                    http_resources = re.findall(r'src=["\']http://[^"\']+["\']', html)
                    http_resources += re.findall(r'href=["\']http://[^"\']+["\']', html)
                    
                    if len(http_resources) > 5:
                        mixed_content_sites.append({
                            'domain': domain,
                            'http_resources': len(http_resources),
                            'samples': http_resources[:3]
                        })
        
        # Report HSTS issues
        if len(no_hsts) > 10:
            self.add_warning(
                'missing_hsts',
                f'{len(no_hsts)} sites missing HSTS headers',
                {'domains': no_hsts[:20]},
                55
            )
        elif len(no_hsts) > 0:
            self.add_ok(
                'missing_hsts',
                f'{len(no_hsts)} sites without HSTS (consider enabling)',
                {'count': len(no_hsts)}
            )
        
        # Report mixed content
        if len(mixed_content_sites) > 0:
            self.add_warning(
                'mixed_content',
                f'{len(mixed_content_sites)} sites have mixed content (HTTP resources on HTTPS)',
                {'sites': mixed_content_sites[:10]},
                60
            )
