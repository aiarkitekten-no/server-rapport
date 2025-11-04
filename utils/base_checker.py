#!/usr/bin/env python3
"""
Base checker class that all health check modules inherit from
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
import logging

from utils.severity import CheckResult, SeverityLevel, classify_severity

logger = logging.getLogger(__name__)


class BaseChecker(ABC):
    """
    Abstract base class for all health checkers.
    
    All checker modules must inherit from this class and implement
    the run() method.
    """
    
    def __init__(self, config: dict, read_only: bool = True):
        """
        Initialize the checker.
        
        Args:
            config: Configuration dictionary
            read_only: Whether to run in read-only mode (no changes)
        """
        self.config = config
        self.read_only = read_only
        self.results: List[CheckResult] = []
        self.category = self.__class__.__name__.replace('Checker', '')
        
    @abstractmethod
    def run(self) -> List[CheckResult]:
        """
        Run the health checks.
        
        Returns:
            List of CheckResult objects
        """
        pass
    
    def add_result(
        self,
        name: str,
        status: SeverityLevel,
        message: str,
        details: dict = None,
        severity_score: int = 0
    ) -> CheckResult:
        """
        Add a check result.
        
        Args:
            name: Name of the check
            status: SeverityLevel enum
            message: Human-readable message
            details: Additional details dictionary
            severity_score: Severity score (0-100)
        
        Returns:
            The created CheckResult
        """
        if details is None:
            details = {}
        
        # Auto-classify if score provided but status is wrong
        if severity_score > 0:
            auto_status = classify_severity(severity_score)
            if status != auto_status:
                logger.debug(f"Status mismatch for {name}: {status} vs {auto_status}, using {auto_status}")
                status = auto_status
        
        result = CheckResult(
            name=name,
            status=status,
            message=message,
            details=details,
            severity_score=severity_score,
            category=self.category,
            timestamp=datetime.now().isoformat()
        )
        
        self.results.append(result)
        return result
    
    def add_ok(self, name: str, message: str, details: dict = None) -> CheckResult:
        """Convenience method to add OK result"""
        return self.add_result(name, SeverityLevel.OK, message, details, 0)
    
    def add_warning(self, name: str, message: str, details: dict = None, score: int = 50) -> CheckResult:
        """Convenience method to add WARNING result"""
        return self.add_result(name, SeverityLevel.WARNING, message, details, score)
    
    def add_critical(self, name: str, message: str, details: dict = None, score: int = 85) -> CheckResult:
        """Convenience method to add CRITICAL result"""
        return self.add_result(name, SeverityLevel.CRITICAL, message, details, score)
    
    def add_unknown(self, name: str, message: str, details: dict = None) -> CheckResult:
        """Convenience method to add UNKNOWN result"""
        return self.add_result(name, SeverityLevel.UNKNOWN, message, details, 0)
    
    def get_results(self) -> List[CheckResult]:
        """
        Get all check results.
        
        Returns:
            List of CheckResult objects
        """
        return self.results
    
    def get_critical_results(self) -> List[CheckResult]:
        """Get only critical results"""
        return [r for r in self.results if r.is_critical()]
    
    def get_warning_results(self) -> List[CheckResult]:
        """Get only warning results"""
        return [r for r in self.results if r.is_warning()]
    
    def get_ok_results(self) -> List[CheckResult]:
        """Get only OK results"""
        return [r for r in self.results if r.is_ok()]
    
    def has_issues(self) -> bool:
        """Check if there are any warnings or critical issues"""
        return any(not r.is_ok() for r in self.results)
    
    def get_max_severity_score(self) -> int:
        """Get the highest severity score"""
        if not self.results:
            return 0
        return max(r.severity_score for r in self.results)
    
    def clear_results(self):
        """Clear all results"""
        self.results = []
    
    def __str__(self) -> str:
        """String representation"""
        return f"{self.category}Checker ({len(self.results)} results)"
    
    def __repr__(self) -> str:
        """Debug representation"""
        critical = len(self.get_critical_results())
        warning = len(self.get_warning_results())
        ok = len(self.get_ok_results())
        return f"<{self.category}Checker: {critical} critical, {warning} warning, {ok} ok>"
