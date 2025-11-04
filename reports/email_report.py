#!/usr/bin/env python3
"""
HTML Email Report Generator - Beautiful HTML reports
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)


def send_email_report(results: dict, config: dict, baseline_comparison: dict = None):
    """
    Generate and send HTML email report
    
    Args:
        results: All check results
        config: Configuration
        baseline_comparison: Optional baseline comparison data
    """
    html_content = generate_html_report(results, config, baseline_comparison)
    
    # Email configuration
    general_config = config.get('general', {})
    recipient = general_config.get('email_recipient', 'terje@smartesider.no')
    from_email = general_config.get('from_email', 'plesk-health@server.local')
    smtp_host = general_config.get('smtp_host', 'localhost')
    smtp_port = general_config.get('smtp_port', 25)
    
    # Determine subject based on severity
    summary = results.get('summary', {})
    critical = summary.get('critical', 0)
    warning = summary.get('warning', 0)
    
    if critical > 0:
        subject = f"🔴 CRITICAL: Plesk Health Check - {critical} critical issues"
    elif warning > 0:
        subject = f"⚠️ WARNING: Plesk Health Check - {warning} warnings"
    else:
        subject = "✅ OK: Plesk Health Check - All systems operational"
    
    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = recipient
    msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
    
    # Attach HTML
    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)
    
    # Send email
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.send_message(msg)
        logger.info(f'Email report sent to {recipient}')
    except Exception as e:
        logger.error(f'Failed to send email: {e}')


def generate_html_report(results: dict, config: dict, baseline_comparison: dict = None) -> str:
    """Generate HTML report"""
    from reports.graphs import (
        generate_severity_donut_chart,
        generate_system_metrics_chart,
        extract_metrics_from_results,
        generate_top_issues_timeline
    )
    
    summary = results.get('summary', {})
    hostname = results.get('hostname', 'Unknown')
    timestamp = results.get('timestamp', '')
    
    critical = summary.get('critical', 0)
    warning = summary.get('warning', 0)
    ok = summary.get('ok', 0)
    total = summary.get('total_checks', 0)
    
    # Extract metrics for graphs
    metrics = extract_metrics_from_results(results)
    
    # Collect issues
    critical_items = []
    warning_items = []
    
    for category, checks in results.get('checks', {}).items():
        if isinstance(checks, dict) and 'error' in checks:
            continue
        
        for check in checks:
            if isinstance(check, dict):
                status = check.get('status', 'UNKNOWN')
                severity_score = check.get('severity', 0)
                if status == 'CRITICAL':
                    critical_items.append((category, check, severity_score))
                elif status == 'WARNING':
                    warning_items.append((category, check, severity_score))
    
    # Sort by severity
    critical_items.sort(key=lambda x: x[2], reverse=True)
    warning_items.sort(key=lambda x: x[2], reverse=True)
    
    # Prepare top issues for timeline
    top_issues = []
    for cat, check, sev in (critical_items + warning_items)[:5]:
        top_issues.append({
            'name': check.get('check', 'Unknown'),
            'severity': sev,
            'message': check.get('message', '')
        })
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Plesk Health Check Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            margin-top: 0;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }}
        .summary {{
            display: table;
            width: 100%;
            margin: 20px 0;
        }}
        .summary-card {{
            display: table-cell;
            padding: 20px;
            text-align: center;
            border-radius: 6px;
            margin: 0 10px;
        }}
        .critical-card {{
            background: #fee;
            border: 2px solid #e74c3c;
        }}
        .warning-card {{
            background: #fff3cd;
            border: 2px solid #f39c12;
        }}
        .ok-card {{
            background: #d4edda;
            border: 2px solid #27ae60;
        }}
        .card-number {{
            font-size: 48px;
            font-weight: bold;
            margin: 10px 0;
        }}
        .card-label {{
            font-size: 14px;
            text-transform: uppercase;
            font-weight: 600;
        }}
        .issue {{
            background: #f8f9fa;
            border-left: 4px solid #e74c3c;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
        }}
        .issue.warning {{
            border-left-color: #f39c12;
        }}
        .issue-title {{
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 8px;
        }}
        .issue-message {{
            color: #555;
            margin-bottom: 8px;
        }}
        .issue-category {{
            display: inline-block;
            background: #3498db;
            color: white;
            padding: 3px 10px;
            border-radius: 3px;
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 600;
        }}
        .severity-score {{
            display: inline-block;
            background: #95a5a6;
            color: white;
            padding: 3px 10px;
            border-radius: 3px;
            font-size: 12px;
            margin-left: 10px;
        }}
        .actions {{
            background: #e8f4f8;
            border: 2px solid #3498db;
            border-radius: 6px;
            padding: 20px;
            margin: 20px 0;
        }}
        .actions h3 {{
            margin-top: 0;
            color: #2980b9;
        }}
        .action-item {{
            padding: 10px 0;
            border-bottom: 1px solid #bdc3c7;
        }}
        .action-item:last-child {{
            border-bottom: none;
        }}
        .action-number {{
            display: inline-block;
            background: #3498db;
            color: white;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            text-align: center;
            line-height: 24px;
            font-weight: bold;
            margin-right: 10px;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #7f8c8d;
            font-size: 14px;
        }}
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 12px;
        }}
        .badge-critical {{ background: #e74c3c; color: white; }}
        .badge-warning {{ background: #f39c12; color: white; }}
        .badge-ok {{ background: #27ae60; color: white; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🩺 Plesk Server Health Check Report</h1>
        
        <p><strong>Server:</strong> {hostname}</p>
        <p><strong>Scan Time:</strong> {timestamp}</p>
        <p><strong>Total Checks:</strong> {total}</p>
        
        <div class="summary">
            <div class="summary-card critical-card">
                <div class="card-label">Critical</div>
                <div class="card-number" style="color: #e74c3c;">{critical}</div>
            </div>
            <div class="summary-card warning-card">
                <div class="card-label">Warning</div>
                <div class="card-number" style="color: #f39c12;">{warning}</div>
            </div>
            <div class="summary-card ok-card">
                <div class="card-label">OK</div>
                <div class="card-number" style="color: #27ae60;">{ok}</div>
            </div>
        </div>
"""
    
    # Top 5 Actions
    if critical_items or warning_items:
        html += """
        </div>
"""
    
    # Baseline comparison section
    if baseline_comparison and baseline_comparison.get('has_baseline'):
        html += generate_baseline_comparison_html(baseline_comparison)
    
    # Add graphs
    html += f"""
        <div style="margin: 30px 0; text-align: center;">
            <h2>📊 Visual Overview</h2>
            <div style="display: flex; justify-content: space-around; flex-wrap: wrap; margin: 20px 0;">
                <div style="margin: 10px;">
                    <h3 style="font-size: 16px; color: #555;">Check Status Distribution</h3>
                    {generate_severity_donut_chart(critical, warning, ok)}
                </div>
                <div style="margin: 10px;">
                    <h3 style="font-size: 16px; color: #555;">System Metrics</h3>
                    {generate_system_metrics_chart(metrics)}
                </div>
            </div>
        </div>
"""
    
    # Add top issues timeline if there are issues
    if top_issues:
        html += f"""
        <div style="margin: 30px 0;">
            {generate_top_issues_timeline(top_issues)}
        </div>
"""
    
    # Top 5 Actions
    if critical_items or warning_items:
        html += """
        <div class="actions">
            <h3>🎯 Top 5 Actions Required</h3>
"""
        actions = generate_top_actions(critical_items, warning_items)
        for i, action in enumerate(actions[:5], 1):
            html += f'            <div class="action-item"><span class="action-number">{i}</span>{action}</div>\n'
        
        html += """
        </div>
"""
    
    # Critical Issues
    if critical_items:
        html += """
        <h2>🔴 Critical Issues - Immediate Action Required</h2>
"""
        for category, check, severity in critical_items:
            html += format_issue_html(category, check, is_critical=True)
    
    # Warnings
    if warning_items:
        html += """
        <h2>⚠️ Warnings - Action Recommended</h2>
"""
        for category, check, severity in warning_items:
            html += format_issue_html(category, check, is_critical=False)
    
    # All good
    if not critical_items and not warning_items:
        html += """
        <h2 style="color: #27ae60;">🎉 All Systems Operational!</h2>
        <p>No issues detected. Your Plesk server is running smoothly.</p>
"""
    
    # Footer
    html += f"""
        <div class="footer">
            <p>Report generated by Plesk Health Check System</p>
            <p>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>
"""
    
    return html


def format_issue_html(category: str, check: dict, is_critical: bool = True) -> str:
    """Format single issue as HTML"""
    name = check.get('name', 'Unknown')
    message = check.get('message', '')
    severity = check.get('severity_score', 0)
    details = check.get('details', {})
    
    css_class = 'issue' if is_critical else 'issue warning'
    
    html = f"""
        <div class="{css_class}">
            <div class="issue-title">{message}</div>
            <div>
                <span class="issue-category">{category}</span>
                <span class="severity-score">Severity: {severity}/100</span>
            </div>
"""
    
    # Add some details if available
    if details:
        detail_items = []
        for key, value in list(details.items())[:3]:
            if not isinstance(value, (list, dict)):
                detail_items.append(f"<li><strong>{key}:</strong> {value}</li>")
        
        if detail_items:
            html += "            <ul style='margin: 10px 0; padding-left: 20px;'>\n"
            html += "\n".join(detail_items)
            html += "\n            </ul>\n"
    
    html += """
        </div>
"""
    
    return html


def generate_top_actions(critical_items: list, warning_items: list) -> list:
    """Generate top recommended actions"""
    actions = []
    
    action_map = {
        'disk_space': '💾 Clean up disk space or expand storage',
        'memory_usage': '🧠 Investigate high memory usage and restart services if needed',
        'swap_usage': '💿 Add more RAM or investigate memory leaks',
        'rbl_status': '📧 Request delisting from RBL and investigate spam source',
        'plesk_license': '📜 Renew Plesk license immediately',
        'mail_queue': '📬 Process mail queue and check for delivery issues',
        'cert_expiry': '🔒 Renew SSL certificates before expiration',
        'recent_backups': '💾 Verify and run backup immediately',
        'world_writable_files': '🔐 Fix file permissions for security',
        'apt_updates': '🔄 Apply security updates',
        'high_cpu': '⚡ Investigate high CPU usage processes',
        'zombie': '🧟 Clean up zombie processes',
    }
    
    # Process critical first
    for category, check, severity in critical_items[:3]:
        name = check.get('name', '')
        message = check.get('message', '')
        
        for key, action in action_map.items():
            if key in name.lower():
                actions.append(f"{action} - {message}")
                break
        else:
            actions.append(f"Address {category}: {message}")
    
    # Add warnings
    for category, check, severity in warning_items[:5-len(actions)]:
        name = check.get('name', '')
        message = check.get('message', '')
        
        for key, action in action_map.items():
            if key in name.lower():
                actions.append(f"{action} - {message}")
                break
        else:
            actions.append(f"Address {category}: {message}")
    
    return actions


def generate_baseline_comparison_html(comparison: dict) -> str:
    """Generate HTML for baseline comparison section"""
    baseline_ts = comparison.get('baseline_timestamp', 'Unknown')
    current_ts = comparison.get('current_timestamp', 'Unknown')
    
    html = f"""
        <h2>📈 Baseline Comparison</h2>
        <div style="background: #f8f9fa; padding: 15px; border-radius: 6px; margin: 15px 0;">
            <p><strong>Baseline:</strong> {baseline_ts}</p>
            <p><strong>Current:</strong> {current_ts}</p>
        </div>
"""
    
    # New issues
    new_issues = comparison.get('new_issues', [])
    if new_issues:
        html += f"""
        <div style="margin: 20px 0;">
            <h3 style="color: #e74c3c;">🆕 New Issues ({len(new_issues)})</h3>
"""
        for issue in new_issues[:10]:
            status_color = '#e74c3c' if issue['status'] == 'CRITICAL' else '#f39c12'
            html += f"""
            <div style="background: #f8f9fa; border-left: 4px solid {status_color}; padding: 10px; margin: 10px 0; border-radius: 4px;">
                <div style="font-weight: 600;"><span class="status-badge badge-{issue['status'].lower()}">{issue['status']}</span> {issue['category']}: {issue['name']}</div>
                <div style="color: #555; margin-top: 5px;">{issue.get('message', '')[:150]}</div>
            </div>
"""
        if len(new_issues) > 10:
            html += f"<p><em>... and {len(new_issues) - 10} more</em></p>"
        html += "</div>"
    
    # Resolved issues
    resolved = comparison.get('resolved_issues', [])
    if resolved:
        html += f"""
        <div style="margin: 20px 0;">
            <h3 style="color: #27ae60;">✅ Resolved Issues ({len(resolved)})</h3>
"""
        for issue in resolved[:10]:
            html += f"""
            <div style="background: #d4edda; border-left: 4px solid #27ae60; padding: 10px; margin: 10px 0; border-radius: 4px;">
                <div style="font-weight: 600;">{issue['category']}: {issue['name']}</div>
                <div style="color: #555; margin-top: 5px;">Was: {issue.get('was_status', 'UNKNOWN')}</div>
            </div>
"""
        if len(resolved) > 10:
            html += f"<p><em>... and {len(resolved) - 10} more</em></p>"
        html += "</div>"
    
    # Degraded checks
    degraded = comparison.get('degraded_checks', [])
    if degraded:
        html += f"""
        <div style="margin: 20px 0;">
            <h3 style="color: #f39c12;">📉 Degraded Checks ({len(degraded)})</h3>
"""
        for check in degraded[:10]:
            delta = check['current_score'] - check['baseline_score']
            html += f"""
            <div style="background: #fff3cd; border-left: 4px solid #f39c12; padding: 10px; margin: 10px 0; border-radius: 4px;">
                <div style="font-weight: 600;">{check['category']}: {check['name']}</div>
                <div style="color: #555; margin-top: 5px;">Score: {check['baseline_score']} → {check['current_score']} ({delta:+d})</div>
                <div style="color: #777; font-size: 14px;">{check.get('message', '')[:150]}</div>
            </div>
"""
        if len(degraded) > 10:
            html += f"<p><em>... and {len(degraded) - 10} more</em></p>"
        html += "</div>"
    
    # Improved checks
    improved = comparison.get('improved_checks', [])
    if improved:
        html += f"""
        <div style="margin: 20px 0;">
            <h3 style="color: #27ae60;">📈 Improved Checks ({len(improved)})</h3>
"""
        for check in improved[:10]:
            delta = check['current_score'] - check['baseline_score']
            html += f"""
            <div style="background: #d4edda; border-left: 4px solid #27ae60; padding: 10px; margin: 10px 0; border-radius: 4px;">
                <div style="font-weight: 600;">{check['category']}: {check['name']}</div>
                <div style="color: #555; margin-top: 5px;">Score: {check['baseline_score']} → {check['current_score']} ({delta:+d})</div>
            </div>
"""
        if len(improved) > 10:
            html += f"<p><em>... and {len(improved) - 10} more</em></p>"
        html += "</div>"
    
    # Overall changes
    changes = comparison.get('changes', [])
    if changes:
        html += """
        <div style="margin: 20px 0;">
            <h3>📝 Summary Changes</h3>
            <ul>
"""
        for change in changes:
            html += f"                <li>{change}</li>\n"
        html += """
            </ul>
        </div>
"""
    
    if not new_issues and not resolved and not degraded and not improved:
        html += """
        <div style="background: #d4edda; padding: 15px; border-radius: 6px; margin: 15px 0; text-align: center;">
            <strong style="color: #27ae60;">✓ No significant changes since baseline</strong>
        </div>
"""
    
    return html
