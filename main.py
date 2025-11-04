#!/usr/bin/env python3
"""
Plesk Health Check - Comprehensive Server Health Monitoring
Author: AI Assistant for Terje
Date: 2025-11-04

A comprehensive diagnostic tool for Plesk servers that checks system health,
security, backups, and generates beautiful reports.
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import List
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    load_json_file, 
    save_json_file, 
    is_plesk_installed,
    SeverityLevel,
    aggregate_severity
)
from utils.base_checker import BaseChecker
from utils.baseline import BaselineManager


# Setup logging
def setup_logging(verbose: bool = False, log_file: str = None):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )


def load_config(config_path: str = 'config.json') -> dict:
    """
    Load configuration file
    
    Args:
        config_path: Path to config.json
        
    Returns:
        Configuration dictionary
    """
    script_dir = Path(__file__).parent
    config_file = script_dir / config_path
    
    config = load_json_file(config_file)
    if config is None:
        logging.error(f"Failed to load config from {config_file}")
        sys.exit(1)
    
    return config


def initialize_checkers(config: dict, read_only: bool) -> List[BaseChecker]:
    """
    Initialize all enabled health checkers
    
    Args:
        config: Configuration dictionary
        read_only: Whether to run in read-only mode
        
    Returns:
        List of initialized checker instances
    """
    checkers = []
    enabled_checks = config.get('checks', {}).get('enabled', {})
    
    # Import and initialize checkers based on what's enabled
    # We'll add these as we create each module
    
    if enabled_checks.get('system_health', False):
        try:
            from checks.system_health import SystemHealthChecker
            checkers.append(SystemHealthChecker(config, read_only))
        except ImportError:
            logging.warning("SystemHealthChecker not yet implemented")
    
    if enabled_checks.get('packages', False):
        try:
            from checks.packages import PackagesChecker
            checkers.append(PackagesChecker(config, read_only))
        except ImportError:
            logging.warning("PackagesChecker not yet implemented")
    
    if enabled_checks.get('network', False):
        try:
            from checks.network import NetworkChecker
            checkers.append(NetworkChecker(config, read_only))
        except ImportError:
            logging.warning("NetworkChecker not yet implemented")
    
    if enabled_checks.get('security', False):
        try:
            from checks.security import SecurityChecker
            checkers.append(SecurityChecker(config, read_only))
        except ImportError:
            logging.warning("SecurityChecker not yet implemented")
    
    if enabled_checks.get('plesk', False):
        try:
            from checks.plesk import PleskChecker
            checkers.append(PleskChecker(config, read_only))
        except ImportError:
            logging.warning("PleskChecker not yet implemented")
    
    if enabled_checks.get('webapp', False):
        try:
            from checks.webapp import WebAppChecker
            checkers.append(WebAppChecker(config, read_only))
        except ImportError:
            logging.warning("WebAppChecker not yet implemented")
    
    if enabled_checks.get('database', False):
        try:
            from checks.database import DatabaseChecker
            checkers.append(DatabaseChecker(config, read_only))
        except ImportError:
            logging.warning("DatabaseChecker not yet implemented")
    
    if enabled_checks.get('cron', False):
        try:
            from checks.cron import CronChecker
            checkers.append(CronChecker(config, read_only))
        except ImportError:
            logging.warning("CronChecker not yet implemented")
    
    if enabled_checks.get('email', False):
        try:
            from checks.email import EmailChecker
            checkers.append(EmailChecker(config, read_only))
        except ImportError:
            logging.warning("EmailChecker not yet implemented")
    
    if enabled_checks.get('clamav', False):
        try:
            from checks.clamav import ClamAVChecker
            checkers.append(ClamAVChecker(config, read_only))
        except ImportError:
            logging.warning("ClamAVChecker not yet implemented")
    
    if enabled_checks.get('backup', False):
        try:
            from checks.backup import BackupChecker
            checkers.append(BackupChecker(config, read_only))
        except ImportError:
            logging.warning("BackupChecker not yet implemented")
    
    if enabled_checks.get('logs', False):
        try:
            from checks.logs import LogsChecker
            checkers.append(LogsChecker(config, read_only))
        except ImportError:
            logging.warning("LogsChecker not yet implemented")
    
    if enabled_checks.get('tls', False):
        try:
            from checks.tls import TLSChecker
            checkers.append(TLSChecker(config, read_only))
        except ImportError:
            logging.warning("TLSChecker not yet implemented")
    
    if enabled_checks.get('processes', False):
        try:
            from checks.processes import ProcessesChecker
            checkers.append(ProcessesChecker(config, read_only))
        except ImportError:
            logging.warning("ProcessesChecker not yet implemented")
    
    return checkers


def run_all_checks(checkers: List[BaseChecker]) -> dict:
    """
    Run all health checks
    
    Args:
        checkers: List of checker instances
        
    Returns:
        Dictionary with all results
    """
    all_results = {
        'timestamp': datetime.now().isoformat(),
        'hostname': None,
        'checks': {},
        'summary': {}
    }
    
    # Get hostname
    try:
        from utils.common import run_command
        result = run_command(['hostname', '-f'])
        if result:
            all_results['hostname'] = result.stdout.strip()
    except Exception:
        pass
    
    total_critical = 0
    total_warning = 0
    total_ok = 0
    
    for checker in checkers:
        logging.info(f"Running {checker.category} checks...")
        try:
            results = checker.run()
            
            # Convert results to dict for JSON serialization
            results_dict = [r.to_dict() for r in results]
            all_results['checks'][checker.category] = results_dict
            
            # Count statuses
            for r in results:
                if r.is_critical():
                    total_critical += 1
                elif r.is_warning():
                    total_warning += 1
                elif r.is_ok():
                    total_ok += 1
            
            logging.info(f"  Completed {checker.category}: {len(results)} checks")
            
        except Exception as e:
            logging.error(f"Error running {checker.category}: {e}", exc_info=True)
            all_results['checks'][checker.category] = {
                'error': str(e)
            }
    
    # Add summary
    all_results['summary'] = {
        'total_checks': total_critical + total_warning + total_ok,
        'critical': total_critical,
        'warning': total_warning,
        'ok': total_ok,
        'has_issues': total_critical > 0 or total_warning > 0
    }
    
    return all_results


def generate_reports(results: dict, config: dict, args, baseline_comparison: dict = None):
    """
    Generate terminal and email reports
    
    Args:
        results: All check results
        config: Configuration
        args: Command line arguments
        baseline_comparison: Optional baseline comparison data
    """
    # Terminal report
    if not args.no_terminal:
        try:
            from reports.terminal_report import generate_terminal_report
            generate_terminal_report(results, config, baseline_comparison)
        except ImportError:
            logging.warning("Terminal report generator not yet implemented")
            # Simple fallback
            print(f"\n{'='*60}")
            print(f"PLESK HEALTH CHECK SUMMARY")
            print(f"{'='*60}")
            print(f"Timestamp: {results['timestamp']}")
            print(f"Hostname: {results.get('hostname', 'Unknown')}")
            print(f"\nTotal Checks: {results['summary']['total_checks']}")
            print(f"🔴 Critical: {results['summary']['critical']}")
            print(f"⚠️  Warning: {results['summary']['warning']}")
            print(f"✅ OK: {results['summary']['ok']}")
            
            # Show baseline comparison if available
            if baseline_comparison and baseline_comparison.get('has_baseline'):
                print(f"\n{'─'*60}")
                print(f"BASELINE COMPARISON")
                print(f"{'─'*60}")
                
                if baseline_comparison.get('new_issues'):
                    print(f"\n🆕 New Issues ({len(baseline_comparison['new_issues'])}):")
                    for issue in baseline_comparison['new_issues'][:5]:
                        print(f"  • {issue['status']}: {issue['name']}")
                
                if baseline_comparison.get('resolved_issues'):
                    print(f"\n✅ Resolved Issues ({len(baseline_comparison['resolved_issues'])}):")
                    for issue in baseline_comparison['resolved_issues'][:5]:
                        print(f"  • {issue['name']}")
                
                if baseline_comparison.get('degraded_checks'):
                    print(f"\n📉 Degraded Checks ({len(baseline_comparison['degraded_checks'])}):")
                    for check in baseline_comparison['degraded_checks'][:5]:
                        print(f"  • {check['name']}: {check['baseline_score']} → {check['current_score']}")
                
                if baseline_comparison.get('improved_checks'):
                    print(f"\n📈 Improved Checks ({len(baseline_comparison['improved_checks'])}):")
                    for check in baseline_comparison['improved_checks'][:5]:
                        print(f"  • {check['name']}: {check['baseline_score']} → {check['current_score']}")
            
            print(f"{'='*60}\n")
    
    # Email report
    if args.email or (config.get('general', {}).get('send_email', False) and not args.no_email):
        try:
            from reports.email_report import send_email_report
            send_email_report(results, config, baseline_comparison)
        except ImportError:
            logging.warning("Email report generator not yet implemented")


def save_baseline(results: dict, baseline_dir: str = 'data/baselines'):
    """
    Save current results as baseline for future comparison
    
    Args:
        results: Check results
        baseline_dir: Directory to save baselines
    """
    try:
        baseline_manager = BaselineManager(baseline_dir)
        if baseline_manager.save_baseline(results):
            logging.info(f"Baseline saved to {baseline_dir}")
        else:
            logging.error("Failed to save baseline")
    except Exception as e:
        logging.error(f"Failed to save baseline: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Plesk Health Check - Comprehensive Server Health Monitoring',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                          # Run with default settings
  %(prog)s --verbose                # Verbose logging
  %(prog)s --email                  # Force send email report
  %(prog)s --no-terminal            # Skip terminal output
  %(prog)s --save-baseline          # Save results as baseline
  %(prog)s --config custom.json     # Use custom config file
        '''
    )
    
    parser.add_argument(
        '--config',
        default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose logging output'
    )
    
    parser.add_argument(
        '--log-file',
        help='Save logs to file'
    )
    
    parser.add_argument(
        '--email',
        action='store_true',
        help='Force send email report'
    )
    
    parser.add_argument(
        '--no-email',
        action='store_true',
        help='Do not send email report'
    )
    
    parser.add_argument(
        '--no-terminal',
        action='store_true',
        help='Do not print terminal report'
    )
    
    parser.add_argument(
        '--save-baseline',
        action='store_true',
        help='Save current results as baseline'
    )
    
    parser.add_argument(
        '--compare-baseline',
        action='store_true',
        help='Compare current results with baseline (default: True)'
    )
    
    parser.add_argument(
        '--no-baseline-compare',
        action='store_true',
        help='Skip baseline comparison'
    )
    
    parser.add_argument(
        '--check-only',
        choices=['system', 'plesk', 'security', 'email', 'all'],
        help='Run only specific category of checks'
    )
    
    parser.add_argument(
        '--json-output',
        help='Save results to JSON file'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose, args.log_file)
    
    logging.info("="*60)
    logging.info("Plesk Health Check Starting")
    logging.info("="*60)
    
    # Load configuration
    config = load_config(args.config)
    
    # Check if this is a Plesk server
    if not is_plesk_installed():
        logging.warning("Plesk does not appear to be installed on this server")
        logging.warning("Some checks will be skipped")
    
    # Get read-only mode from config
    read_only = config.get('general', {}).get('read_only', True)
    if not read_only:
        logging.warning("Read-only mode is DISABLED - some checks may make changes")
    
    # Initialize checkers
    checkers = initialize_checkers(config, read_only)
    
    if not checkers:
        logging.error("No checkers initialized! Check your configuration.")
        sys.exit(1)
    
    logging.info(f"Initialized {len(checkers)} checkers")
    
    # Run all checks
    results = run_all_checks(checkers)
    
    # Compare with baseline (unless disabled)
    baseline_comparison = None
    if not args.no_baseline_compare:
        try:
            baseline_manager = BaselineManager()
            baseline_comparison = baseline_manager.compare_with_baseline(results)
            
            if baseline_comparison.get('has_baseline'):
                logging.info("Baseline comparison completed")
                
                # Log key changes
                if baseline_comparison.get('new_issues'):
                    logging.warning(f"Found {len(baseline_comparison['new_issues'])} new issues since baseline")
                if baseline_comparison.get('resolved_issues'):
                    logging.info(f"Resolved {len(baseline_comparison['resolved_issues'])} issues since baseline")
                if baseline_comparison.get('degraded_checks'):
                    logging.warning(f"Found {len(baseline_comparison['degraded_checks'])} degraded checks")
                if baseline_comparison.get('improved_checks'):
                    logging.info(f"Found {len(baseline_comparison['improved_checks'])} improved checks")
            else:
                logging.info("No baseline available for comparison (run with --save-baseline to create one)")
        except Exception as e:
            logging.error(f"Error comparing with baseline: {e}")
    
    # Save baseline if requested
    if args.save_baseline:
        save_baseline(results)
    
    # Save JSON output if requested
    if args.json_output:
        # Include baseline comparison in JSON output
        output_data = results.copy()
        if baseline_comparison:
            output_data['baseline_comparison'] = baseline_comparison
        
        save_json_file(output_data, args.json_output)
        logging.info(f"Results saved to {args.json_output}")
    
    # Generate reports
    generate_reports(results, config, args, baseline_comparison)
    
    logging.info("="*60)
    logging.info("Plesk Health Check Completed")
    logging.info("="*60)
    
    # Exit code based on results
    if results['summary']['critical'] > 0:
        sys.exit(2)  # Critical issues found
    elif results['summary']['warning'] > 0:
        sys.exit(1)  # Warnings found
    else:
        sys.exit(0)  # All OK


if __name__ == '__main__':
    main()
