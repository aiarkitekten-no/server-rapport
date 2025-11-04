#!/usr/bin/env python3
"""
Terminal Report Generator - Beautiful colored console output
"""

import logging
from typing import Dict, List
from datetime import datetime

try:
    from colorama import Fore, Back, Style, init
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # Fallback definitions
    class Fore:
        RED = GREEN = YELLOW = CYAN = WHITE = RESET = ''
    class Style:
        BRIGHT = RESET_ALL = ''

from utils.severity import SeverityLevel, aggregate_severity

logger = logging.getLogger(__name__)


def generate_terminal_report(results: dict, config: dict, baseline_comparison: dict = None):
    """
    Generate beautiful colored terminal report
    
    Args:
        results: All check results
        config: Configuration
        baseline_comparison: Optional baseline comparison data
    """
    if not COLORAMA_AVAILABLE:
        logger.warning('colorama not available, output will not be colored')
    
    print()
    print_header("PLESK SERVER HEALTH CHECK REPORT")
    print()
    
    # Summary section
    print_section_header("📊 EXECUTIVE SUMMARY")
    print_summary(results)
    print()
    
    # Baseline comparison section
    if baseline_comparison and baseline_comparison.get('has_baseline'):
        print_section_header("📈 BASELINE COMPARISON")
        print_baseline_comparison(baseline_comparison)
        print()
    
    # Only show categories with issues
    critical_items = []
    warning_items = []
    
    for category, checks in results.get('checks', {}).items():
        if isinstance(checks, dict) and 'error' in checks:
            continue
        
        for check in checks:
            if isinstance(check, dict):
                status = check.get('status', 'UNKNOWN')
                if status == 'CRITICAL':
                    critical_items.append((category, check))
                elif status == 'WARNING':
                    warning_items.append((category, check))
    
    # Critical issues
    if critical_items:
        print_section_header("🔴 CRITICAL ISSUES - IMMEDIATE ACTION REQUIRED")
        for category, check in critical_items:
            print_check_result(category, check, show_details=True)
        print()
    
    # Warnings
    if warning_items:
        print_section_header("⚠️  WARNINGS - ATTENTION NEEDED")
        for category, check in warning_items:
            print_check_result(category, check, show_details=False)
        print()
    
    # Top 5 actions
    if critical_items or warning_items:
        print_section_header("🎯 TOP 5 RECOMMENDED ACTIONS")
        print_top_actions(critical_items, warning_items)
        print()
    
    # Footer
    print_footer(results)
    print()


def print_header(text: str):
    """Print report header"""
    width = 80
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * width}")
    print(f"{text.center(width)}")
    print(f"{'=' * width}{Style.RESET_ALL}")


def print_section_header(text: str):
    """Print section header"""
    print(f"{Fore.YELLOW}{Style.BRIGHT}{text}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{'-' * len(text)}{Style.RESET_ALL}")


def print_summary(results: dict):
    """Print summary statistics"""
    summary = results.get('summary', {})
    hostname = results.get('hostname', 'Unknown')
    timestamp = results.get('timestamp', '')
    
    print(f"  {Fore.CYAN}Server:{Style.RESET_ALL} {hostname}")
    print(f"  {Fore.CYAN}Scan Time:{Style.RESET_ALL} {timestamp}")
    print(f"  {Fore.CYAN}Total Checks:{Style.RESET_ALL} {summary.get('total_checks', 0)}")
    print()
    
    critical = summary.get('critical', 0)
    warning = summary.get('warning', 0)
    ok = summary.get('ok', 0)
    
    if critical > 0:
        print(f"  {Fore.RED}{Style.BRIGHT}🔴 CRITICAL: {critical}{Style.RESET_ALL}")
    if warning > 0:
        print(f"  {Fore.YELLOW}⚠️  WARNING: {warning}{Style.RESET_ALL}")
    if ok > 0:
        print(f"  {Fore.GREEN}✅ OK: {ok}{Style.RESET_ALL}")
    
    if critical == 0 and warning == 0:
        print(f"\n  {Fore.GREEN}{Style.BRIGHT}🎉 ALL SYSTEMS OPERATIONAL!{Style.RESET_ALL}")


def print_check_result(category: str, check: dict, show_details: bool = False):
    """Print individual check result"""
    name = check.get('name', 'Unknown')
    status = check.get('status', 'UNKNOWN')
    message = check.get('message', '')
    severity_score = check.get('severity_score', 0)
    
    # Color based on status
    if status == 'CRITICAL':
        color = Fore.RED
        icon = '🔴'
    elif status == 'WARNING':
        color = Fore.YELLOW
        icon = '⚠️ '
    elif status == 'OK':
        color = Fore.GREEN
        icon = '✅'
    else:
        color = Fore.CYAN
        icon = '❓'
    
    print(f"  {icon} {color}{Style.BRIGHT}[{category.upper()}]{Style.RESET_ALL} {message}")
    
    if show_details:
        details = check.get('details', {})
        if details:
            print(f"     {Fore.CYAN}Details:{Style.RESET_ALL}")
            for key, value in list(details.items())[:5]:  # Max 5 details
                if isinstance(value, (list, dict)):
                    print(f"       • {key}: {str(value)[:100]}...")
                else:
                    print(f"       • {key}: {value}")
    
    print(f"     {Fore.CYAN}Severity Score: {severity_score}/100{Style.RESET_ALL}")
    print()


def print_top_actions(critical_items: list, warning_items: list):
    """Print top 5 recommended actions"""
    actions = []
    
    # Prioritize critical items
    for category, check in critical_items[:3]:
        action = generate_action(category, check)
        if action:
            actions.append(action)
    
    # Add warnings if we have room
    for category, check in warning_items[:5-len(actions)]:
        action = generate_action(category, check)
        if action:
            actions.append(action)
    
    for i, action in enumerate(actions[:5], 1):
        print(f"  {Fore.CYAN}{i}.{Style.RESET_ALL} {action}")


def generate_action(category: str, check: dict) -> str:
    """Generate recommended action for a check"""
    name = check.get('name', '')
    message = check.get('message', '')
    
    # Map checks to actions
    action_map = {
        'disk_space': 'Clean up disk space or expand storage',
        'memory_usage': 'Investigate high memory usage and restart services if needed',
        'swap_usage': 'Add more RAM or investigate memory leaks',
        'rbl_status': 'Request delisting from RBL and investigate spam source',
        'plesk_license': 'Renew Plesk license immediately',
        'mail_queue': 'Process mail queue and check for delivery issues',
        'cert_expiry': 'Renew SSL certificates before expiration',
        'recent_backups': 'Verify and run backup immediately',
        'world_writable_files': 'Fix file permissions for security',
        'apt_updates': 'Apply security updates',
    }
    
    for key, action in action_map.items():
        if key in name.lower():
            return f"{action} ({category}: {message})"
    
    return f"Address {category}: {message}"


def print_baseline_comparison(comparison: dict):
    """Print baseline comparison section"""
    baseline_ts = comparison.get('baseline_timestamp', 'Unknown')
    current_ts = comparison.get('current_timestamp', 'Unknown')
    
    print(f"  Baseline: {Fore.CYAN}{baseline_ts}{Style.RESET_ALL}")
    print(f"  Current:  {Fore.CYAN}{current_ts}{Style.RESET_ALL}")
    print()
    
    # New issues
    new_issues = comparison.get('new_issues', [])
    if new_issues:
        print(f"  {Fore.RED}🆕 NEW ISSUES ({len(new_issues)}):{Style.RESET_ALL}")
        for issue in new_issues[:10]:  # Show top 10
            status_color = Fore.RED if issue['status'] == 'CRITICAL' else Fore.YELLOW
            print(f"    {status_color}• [{issue['status']}]{Style.RESET_ALL} {issue['category']}: {issue['name']}")
            if issue.get('message'):
                print(f"      → {issue['message'][:100]}")
        if len(new_issues) > 10:
            print(f"    ... and {len(new_issues) - 10} more")
        print()
    
    # Resolved issues
    resolved = comparison.get('resolved_issues', [])
    if resolved:
        print(f"  {Fore.GREEN}✅ RESOLVED ISSUES ({len(resolved)}):{Style.RESET_ALL}")
        for issue in resolved[:10]:
            print(f"    {Fore.GREEN}• {issue['category']}: {issue['name']}{Style.RESET_ALL}")
        if len(resolved) > 10:
            print(f"    ... and {len(resolved) - 10} more")
        print()
    
    # Degraded checks
    degraded = comparison.get('degraded_checks', [])
    if degraded:
        print(f"  {Fore.YELLOW}📉 DEGRADED CHECKS ({len(degraded)}):{Style.RESET_ALL}")
        for check in degraded[:10]:
            delta = check['current_score'] - check['baseline_score']
            print(f"    {Fore.YELLOW}• {check['category']}: {check['name']}{Style.RESET_ALL}")
            print(f"      Score: {check['baseline_score']} → {check['current_score']} ({delta:+d})")
        if len(degraded) > 10:
            print(f"    ... and {len(degraded) - 10} more")
        print()
    
    # Improved checks
    improved = comparison.get('improved_checks', [])
    if improved:
        print(f"  {Fore.GREEN}📈 IMPROVED CHECKS ({len(improved)}):{Style.RESET_ALL}")
        for check in improved[:10]:
            delta = check['current_score'] - check['baseline_score']
            print(f"    {Fore.GREEN}• {check['category']}: {check['name']}{Style.RESET_ALL}")
            print(f"      Score: {check['baseline_score']} → {check['current_score']} ({delta:+d})")
        if len(improved) > 10:
            print(f"    ... and {len(improved) - 10} more")
        print()
    
    # Overall changes
    changes = comparison.get('changes', [])
    if changes:
        print(f"  {Fore.CYAN}📝 SUMMARY CHANGES:{Style.RESET_ALL}")
        for change in changes:
            print(f"    • {change}")
        print()
    
    if not new_issues and not resolved and not degraded and not improved:
        print(f"  {Fore.GREEN}✓ No significant changes since baseline{Style.RESET_ALL}")
        print()

def print_footer(results: dict):
    """Print report footer"""
    print(f"{Fore.CYAN}{'-' * 80}{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}For detailed HTML report, check your email{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'-' * 80}{Style.RESET_ALL}")
