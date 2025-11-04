#!/usr/bin/env python3
"""
Baseline System - Track and compare system state over time
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from utils.common import load_json_file, save_json_file

logger = logging.getLogger(__name__)


class BaselineManager:
    """Manage baseline data and comparisons"""
    
    def __init__(self, baseline_dir: str = 'data/baselines'):
        self.baseline_dir = Path(baseline_dir)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
    
    def save_baseline(self, results: dict) -> bool:
        """
        Save current results as baseline
        
        Args:
            results: Check results dictionary
            
        Returns:
            True if saved successfully
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        baseline_file = self.baseline_dir / f'baseline_{timestamp}.json'
        
        # Save timestamped version
        if not save_json_file(results, baseline_file):
            return False
        
        # Also save as latest
        latest_file = self.baseline_dir / 'baseline_latest.json'
        return save_json_file(results, latest_file)
    
    def load_latest_baseline(self) -> Dict:
        """Load the most recent baseline"""
        latest_file = self.baseline_dir / 'baseline_latest.json'
        return load_json_file(latest_file) or {}
    
    def compare_with_baseline(self, current_results: dict) -> Dict[str, Any]:
        """
        Compare current results with baseline
        
        Args:
            current_results: Current check results
            
        Returns:
            Dictionary with comparison results
        """
        baseline = self.load_latest_baseline()
        
        if not baseline:
            return {
                'has_baseline': False,
                'message': 'No baseline available for comparison'
            }
        
        comparison = {
            'has_baseline': True,
            'baseline_timestamp': baseline.get('timestamp'),
            'current_timestamp': current_results.get('timestamp'),
            'changes': [],
            'new_issues': [],
            'resolved_issues': [],
            'degraded_checks': [],
            'improved_checks': []
        }
        
        # Compare summaries
        baseline_summary = baseline.get('summary', {})
        current_summary = current_results.get('summary', {})
        
        baseline_critical = baseline_summary.get('critical', 0)
        current_critical = current_summary.get('critical', 0)
        
        if current_critical > baseline_critical:
            comparison['changes'].append(
                f"Critical issues increased from {baseline_critical} to {current_critical}"
            )
        elif current_critical < baseline_critical:
            comparison['changes'].append(
                f"Critical issues decreased from {baseline_critical} to {current_critical}"
            )
        
        # Compare individual checks
        baseline_checks = baseline.get('checks', {})
        current_checks = current_results.get('checks', {})
        
        for category in set(list(baseline_checks.keys()) + list(current_checks.keys())):
            baseline_cat = baseline_checks.get(category, [])
            current_cat = current_checks.get(category, [])
            
            if isinstance(baseline_cat, dict) or isinstance(current_cat, dict):
                continue
            
            # Create lookup by check name
            baseline_map = {c.get('name'): c for c in baseline_cat if isinstance(c, dict)}
            current_map = {c.get('name'): c for c in current_cat if isinstance(c, dict)}
            
            for check_name in set(list(baseline_map.keys()) + list(current_map.keys())):
                baseline_check = baseline_map.get(check_name)
                current_check = current_map.get(check_name)
                
                if not baseline_check and current_check:
                    # New check appeared
                    if current_check.get('status') in ['CRITICAL', 'WARNING']:
                        comparison['new_issues'].append({
                            'category': category,
                            'name': check_name,
                            'status': current_check.get('status'),
                            'message': current_check.get('message')
                        })
                
                elif baseline_check and not current_check:
                    # Check resolved
                    if baseline_check.get('status') in ['CRITICAL', 'WARNING']:
                        comparison['resolved_issues'].append({
                            'category': category,
                            'name': check_name,
                            'was_status': baseline_check.get('status')
                        })
                
                elif baseline_check and current_check:
                    # Compare severity
                    baseline_score = baseline_check.get('severity_score', 0)
                    current_score = current_check.get('severity_score', 0)
                    
                    if current_score > baseline_score + 10:  # Degraded by > 10 points
                        comparison['degraded_checks'].append({
                            'category': category,
                            'name': check_name,
                            'baseline_score': baseline_score,
                            'current_score': current_score,
                            'message': current_check.get('message')
                        })
                    
                    elif current_score < baseline_score - 10:  # Improved by > 10 points
                        comparison['improved_checks'].append({
                            'category': category,
                            'name': check_name,
                            'baseline_score': baseline_score,
                            'current_score': current_score
                        })
        
        return comparison
    
    def get_baseline_history(self, limit: int = 10) -> List[Dict]:
        """
        Get list of historical baselines
        
        Args:
            limit: Maximum number of baselines to return
            
        Returns:
            List of baseline metadata
        """
        baselines = []
        
        for baseline_file in sorted(self.baseline_dir.glob('baseline_*.json'), reverse=True)[:limit]:
            if baseline_file.name == 'baseline_latest.json':
                continue
            
            baseline = load_json_file(baseline_file)
            if baseline:
                baselines.append({
                    'file': baseline_file.name,
                    'timestamp': baseline.get('timestamp'),
                    'summary': baseline.get('summary', {})
                })
        
        return baselines
