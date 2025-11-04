#!/usr/bin/env python3
"""
SVG Graph Generator for Email Reports
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def generate_severity_donut_chart(critical: int, warning: int, ok: int) -> str:
    """Generate SVG donut chart for check status distribution"""
    total = critical + warning + ok
    if total == 0:
        total = 1  # Avoid division by zero
    
    # Calculate percentages
    critical_pct = (critical / total) * 100
    warning_pct = (warning / total) * 100
    ok_pct = (ok / total) * 100
    
    # Calculate angles for donut segments
    critical_angle = (critical / total) * 360
    warning_angle = (warning / total) * 360
    ok_angle = (ok / total) * 360
    
    # SVG donut chart
    svg = f'''
    <svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
        <circle cx="100" cy="100" r="80" fill="none" stroke="#e0e0e0" stroke-width="40"/>
        {_donut_segment(100, 100, 80, 40, 0, critical_angle, "#dc3545") if critical > 0 else ""}
        {_donut_segment(100, 100, 80, 40, critical_angle, critical_angle + warning_angle, "#ffc107") if warning > 0 else ""}
        {_donut_segment(100, 100, 80, 40, critical_angle + warning_angle, 360, "#28a745") if ok > 0 else ""}
        <text x="100" y="95" text-anchor="middle" font-size="24" font-weight="bold" fill="#333">{total}</text>
        <text x="100" y="115" text-anchor="middle" font-size="12" fill="#666">checks</text>
    </svg>
    '''
    return svg


def _donut_segment(cx, cy, r, width, start_angle, end_angle, color):
    """Helper to create a donut segment"""
    import math
    
    # Convert to radians
    start_rad = (start_angle - 90) * math.pi / 180
    end_rad = (end_angle - 90) * math.pi / 180
    
    # Calculate outer points
    outer_r = r + width / 2
    inner_r = r - width / 2
    
    x1 = cx + outer_r * math.cos(start_rad)
    y1 = cy + outer_r * math.sin(start_rad)
    x2 = cx + outer_r * math.cos(end_rad)
    y2 = cy + outer_r * math.sin(end_rad)
    
    x3 = cx + inner_r * math.cos(end_rad)
    y3 = cy + inner_r * math.sin(end_rad)
    x4 = cx + inner_r * math.cos(start_rad)
    y4 = cy + inner_r * math.sin(start_rad)
    
    # Large arc flag
    large_arc = 1 if (end_angle - start_angle) > 180 else 0
    
    path = f'''
    <path d="M {x1},{y1}
             A {outer_r},{outer_r} 0 {large_arc},1 {x2},{y2}
             L {x3},{y3}
             A {inner_r},{inner_r} 0 {large_arc},0 {x4},{y4}
             Z"
          fill="{color}" opacity="0.9"/>
    '''
    return path


def generate_disk_usage_bar(usage_pct: float, label: str = "Disk") -> str:
    """Generate horizontal bar chart for disk usage"""
    color = "#28a745"  # Green
    if usage_pct > 90:
        color = "#dc3545"  # Red
    elif usage_pct > 75:
        color = "#ffc107"  # Yellow
    
    svg = f'''
    <svg width="300" height="40" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="10" width="300" height="20" fill="#e9ecef" rx="3"/>
        <rect x="0" y="10" width="{usage_pct * 3}" height="20" fill="{color}" rx="3"/>
        <text x="5" y="25" font-size="12" fill="#fff" font-weight="bold">{label}: {usage_pct:.1f}%</text>
    </svg>
    '''
    return svg


def generate_system_metrics_chart(metrics: Dict) -> str:
    """Generate combined system metrics chart"""
    ram_usage = metrics.get('ram_usage', 0)
    swap_usage = metrics.get('swap_usage', 0)
    disk_usage = metrics.get('disk_usage', 0)
    cpu_load = metrics.get('cpu_load', 0)
    
    svg = f'''
    <svg width="400" height="250" xmlns="http://www.w3.org/2000/svg">
        <style>
            .bar {{ fill-opacity: 0.8; }}
            .label {{ font-size: 12px; fill: #333; }}
            .value {{ font-size: 14px; font-weight: bold; fill: #333; }}
        </style>
        
        <!-- Background -->
        <rect width="400" height="250" fill="#f8f9fa" rx="5"/>
        
        <!-- Title -->
        <text x="200" y="25" text-anchor="middle" font-size="16" font-weight="bold" fill="#333">
            System Metrics
        </text>
        
        <!-- RAM -->
        <text x="20" y="65" class="label">RAM</text>
        <rect x="80" y="50" width="300" height="20" fill="#e9ecef" rx="2"/>
        <rect x="80" y="50" width="{min(ram_usage * 3, 300)}" height="20" class="bar" fill="{_get_color(ram_usage)}" rx="2"/>
        <text x="385" y="65" class="value" text-anchor="end">{ram_usage:.1f}%</text>
        
        <!-- Swap -->
        <text x="20" y="105" class="label">Swap</text>
        <rect x="80" y="90" width="300" height="20" fill="#e9ecef" rx="2"/>
        <rect x="80" y="90" width="{min(swap_usage * 3, 300)}" height="20" class="bar" fill="{_get_color(swap_usage)}" rx="2"/>
        <text x="385" y="105" class="value" text-anchor="end">{swap_usage:.1f}%</text>
        
        <!-- Disk -->
        <text x="20" y="145" class="label">Disk</text>
        <rect x="80" y="130" width="300" height="20" fill="#e9ecef" rx="2"/>
        <rect x="80" y="130" width="{min(disk_usage * 3, 300)}" height="20" class="bar" fill="{_get_color(disk_usage)}" rx="2"/>
        <text x="385" y="145" class="value" text-anchor="end">{disk_usage:.1f}%</text>
        
        <!-- CPU Load -->
        <text x="20" y="185" class="label">CPU Load</text>
        <rect x="80" y="170" width="300" height="20" fill="#e9ecef" rx="2"/>
        <rect x="80" y="170" width="{min(cpu_load * 30, 300)}" height="20" class="bar" fill="{_get_load_color(cpu_load)}" rx="2"/>
        <text x="385" y="185" class="value" text-anchor="end">{cpu_load:.2f}</text>
        
        <!-- Legend -->
        <text x="20" y="220" font-size="10" fill="#666">
            <tspan fill="#28a745">● OK</tspan>
            <tspan x="80" fill="#ffc107">● Warning</tspan>
            <tspan x="160" fill="#dc3545">● Critical</tspan>
        </text>
    </svg>
    '''
    return svg


def _get_color(percentage: float) -> str:
    """Get color based on percentage"""
    if percentage > 90:
        return "#dc3545"  # Red
    elif percentage > 75:
        return "#ffc107"  # Yellow
    else:
        return "#28a745"  # Green


def _get_load_color(load: float) -> str:
    """Get color for CPU load"""
    if load > 4.0:
        return "#dc3545"  # Red
    elif load > 2.0:
        return "#ffc107"  # Yellow
    else:
        return "#28a745"  # Green


def generate_top_issues_timeline(issues: List[Dict]) -> str:
    """Generate timeline of top issues"""
    if not issues or len(issues) == 0:
        return ""
    
    height = 50 + len(issues) * 40
    
    svg = f'<svg width="500" height="{height}" xmlns="http://www.w3.org/2000/svg">'
    svg += '<rect width="500" height="{height}" fill="#f8f9fa" rx="5"/>'
    svg += '<text x="250" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#333">Top Priority Issues</text>'
    
    y = 60
    for i, issue in enumerate(issues[:5], 1):
        severity = issue.get('severity', 50)
        name = issue.get('name', 'Unknown')[:40]
        
        color = _get_color(severity)
        
        svg += f'<circle cx="30" cy="{y}" r="8" fill="{color}"/>'
        svg += f'<text x="50" y="{y + 5}" font-size="12" fill="#333">{i}. {name}</text>'
        svg += f'<text x="480" y="{y + 5}" text-anchor="end" font-size="11" fill="#666">Severity: {severity}</text>'
        
        y += 40
    
    svg += '</svg>'
    return svg


def extract_metrics_from_results(results: Dict) -> Dict:
    """Extract key metrics from check results for graphs"""
    metrics = {
        'ram_usage': 0,
        'swap_usage': 0,
        'disk_usage': 0,
        'cpu_load': 0
    }
    
    checks = results.get('checks', {})
    
    # Extract from system_health
    if 'system_health' in checks:
        for check in checks['system_health']:
            if not isinstance(check, dict):
                continue
            
            details = check.get('details', {})
            
            if check.get('name') == 'memory_usage':
                metrics['ram_usage'] = details.get('used_percent', 0)
            elif check.get('name') == 'swap_usage':
                metrics['swap_usage'] = details.get('used_percent', 0)
            elif check.get('name').startswith('disk_space_'):
                # Take highest disk usage
                usage = details.get('use_percent', 0)
                if usage > metrics['disk_usage']:
                    metrics['disk_usage'] = usage
            elif check.get('name') == 'load_average':
                metrics['cpu_load'] = details.get('load_per_cpu', 0)
    
    return metrics
