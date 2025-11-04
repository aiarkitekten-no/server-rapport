#!/usr/bin/env python3
"""
Severity classification and scoring for health checks
"""

from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass


class SeverityLevel(Enum):
    """Severity levels for health check results"""
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class CheckResult:
    """
    Standard result format for all health checks
    """
    name: str
    status: SeverityLevel
    message: str
    details: Dict[str, Any]
    severity_score: int  # 0-100
    category: str
    timestamp: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'name': self.name,
            'status': self.status.value,
            'message': self.message,
            'details': self.details,
            'severity_score': self.severity_score,
            'category': self.category,
            'timestamp': self.timestamp
        }
    
    def is_ok(self) -> bool:
        """Check if result is OK"""
        return self.status == SeverityLevel.OK
    
    def is_warning(self) -> bool:
        """Check if result is WARNING"""
        return self.status == SeverityLevel.WARNING
    
    def is_critical(self) -> bool:
        """Check if result is CRITICAL"""
        return self.status == SeverityLevel.CRITICAL


def classify_severity(score: int) -> SeverityLevel:
    """
    Classify severity based on score.
    
    Args:
        score: Severity score (0-100)
    
    Returns:
        SeverityLevel enum
    """
    if score < 0 or score > 100:
        return SeverityLevel.UNKNOWN
    
    if score <= 30:
        return SeverityLevel.OK
    elif score <= 70:
        return SeverityLevel.WARNING
    else:
        return SeverityLevel.CRITICAL


def calculate_disk_severity(usage_percent: float, warning: float = 75, critical: float = 90) -> int:
    """
    Calculate severity score for disk usage.
    
    Args:
        usage_percent: Disk usage percentage (0-100)
        warning: Warning threshold
        critical: Critical threshold
    
    Returns:
        Severity score (0-100)
    """
    if usage_percent >= critical:
        # Critical: map 90-100% to score 71-100
        return int(71 + ((usage_percent - critical) / (100 - critical)) * 29)
    elif usage_percent >= warning:
        # Warning: map 75-90% to score 31-70
        return int(31 + ((usage_percent - warning) / (critical - warning)) * 39)
    else:
        # OK: map 0-75% to score 0-30
        return int((usage_percent / warning) * 30)


def calculate_age_severity(age_hours: float, warning_hours: float, critical_hours: float) -> int:
    """
    Calculate severity score based on age (e.g., backup age, log age).
    
    Args:
        age_hours: Age in hours
        warning_hours: Warning threshold in hours
        critical_hours: Critical threshold in hours
    
    Returns:
        Severity score (0-100)
    """
    if age_hours >= critical_hours:
        # Critical: beyond critical threshold
        excess = min(age_hours - critical_hours, critical_hours)  # Cap excess
        return int(71 + (excess / critical_hours) * 29)
    elif age_hours >= warning_hours:
        # Warning: between warning and critical
        return int(31 + ((age_hours - warning_hours) / (critical_hours - warning_hours)) * 39)
    else:
        # OK: within acceptable range
        return int((age_hours / warning_hours) * 30)


def calculate_count_severity(count: int, warning: int, critical: int) -> int:
    """
    Calculate severity based on count (errors, processes, etc.).
    
    Args:
        count: Current count
        warning: Warning threshold
        critical: Critical threshold
    
    Returns:
        Severity score (0-100)
    """
    if count >= critical:
        # Critical
        excess = min(count - critical, critical)
        return int(71 + (excess / critical) * 29)
    elif count >= warning:
        # Warning
        return int(31 + ((count - warning) / (critical - warning)) * 39)
    else:
        # OK
        if warning == 0:
            return 0
        return int((count / warning) * 30)


def aggregate_severity(results: list) -> tuple:
    """
    Aggregate severity from multiple check results.
    
    Args:
        results: List of CheckResult objects
    
    Returns:
        Tuple of (overall_status, max_score, critical_count, warning_count)
    """
    if not results:
        return (SeverityLevel.UNKNOWN, 0, 0, 0)
    
    max_score = 0
    critical_count = 0
    warning_count = 0
    
    for result in results:
        if isinstance(result, CheckResult):
            score = result.severity_score
            status = result.status
        elif isinstance(result, dict):
            score = result.get('severity_score', 0)
            status_str = result.get('status', 'UNKNOWN')
            status = SeverityLevel(status_str) if status_str in [s.value for s in SeverityLevel] else SeverityLevel.UNKNOWN
        else:
            continue
        
        max_score = max(max_score, score)
        
        if status == SeverityLevel.CRITICAL:
            critical_count += 1
        elif status == SeverityLevel.WARNING:
            warning_count += 1
    
    overall_status = classify_severity(max_score)
    
    return (overall_status, max_score, critical_count, warning_count)


def get_severity_color(severity: SeverityLevel) -> str:
    """
    Get terminal color code for severity level.
    
    Args:
        severity: SeverityLevel enum
    
    Returns:
        Color name for colorama
    """
    color_map = {
        SeverityLevel.OK: 'GREEN',
        SeverityLevel.WARNING: 'YELLOW',
        SeverityLevel.CRITICAL: 'RED',
        SeverityLevel.UNKNOWN: 'CYAN'
    }
    return color_map.get(severity, 'WHITE')


def get_severity_emoji(severity: SeverityLevel) -> str:
    """
    Get emoji for severity level (for HTML reports).
    
    Args:
        severity: SeverityLevel enum
    
    Returns:
        Emoji string
    """
    emoji_map = {
        SeverityLevel.OK: '✅',
        SeverityLevel.WARNING: '⚠️',
        SeverityLevel.CRITICAL: '🔴',
        SeverityLevel.UNKNOWN: '❓'
    }
    return emoji_map.get(severity, '❔')
