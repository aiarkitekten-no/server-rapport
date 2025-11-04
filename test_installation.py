#!/usr/bin/env python3
"""
Quick test script to verify installation
"""

import sys
from pathlib import Path

print("Testing Plesk Health Check Installation...")
print("=" * 60)

# Test Python version
print(f"✓ Python version: {sys.version.split()[0]}")

# Test imports
errors = []

try:
    import json
    print("✓ json module available")
except ImportError as e:
    errors.append(f"✗ json: {e}")

try:
    import subprocess
    print("✓ subprocess module available")
except ImportError as e:
    errors.append(f"✗ subprocess: {e}")

try:
    import logging
    print("✓ logging module available")
except ImportError as e:
    errors.append(f"✗ logging: {e}")

try:
    from pathlib import Path
    print("✓ pathlib module available")
except ImportError as e:
    errors.append(f"✗ pathlib: {e}")

try:
    import colorama
    print("✓ colorama installed")
except ImportError as e:
    print("⚠ colorama not installed (optional, for colored output)")
    print("  Install with: pip3 install colorama")

try:
    import dns.resolver
    print("✓ dnspython installed")
except ImportError as e:
    print("⚠ dnspython not installed (optional, for RBL checks)")
    print("  Install with: pip3 install dnspython")

# Test project structure
print("\nChecking project structure...")

required_dirs = [
    'checks',
    'utils',
    'reports',
    'data',
    'data/baselines',
    'AI-learned'
]

for dir_path in required_dirs:
    if Path(dir_path).is_dir():
        print(f"✓ {dir_path}/ exists")
    else:
        errors.append(f"✗ {dir_path}/ missing")

required_files = [
    'main.py',
    'config.json',
    'requirements.txt',
    'README.md',
    'utils/common.py',
    'utils/severity.py',
    'utils/base_checker.py'
]

for file_path in required_files:
    if Path(file_path).is_file():
        print(f"✓ {file_path} exists")
    else:
        errors.append(f"✗ {file_path} missing")

# Test configuration
print("\nChecking configuration...")
try:
    with open('config.json', 'r') as f:
        import json
        config = json.load(f)
    print("✓ config.json is valid JSON")
    
    if 'general' in config:
        print("✓ config.json has 'general' section")
    if 'thresholds' in config:
        print("✓ config.json has 'thresholds' section")
    if 'checks' in config:
        print("✓ config.json has 'checks' section")
        
except Exception as e:
    errors.append(f"✗ config.json error: {e}")

# Summary
print("\n" + "=" * 60)
if errors:
    print(f"❌ Found {len(errors)} error(s):")
    for error in errors:
        print(f"  {error}")
    print("\nPlease fix errors before running.")
    sys.exit(1)
else:
    print("✅ All checks passed!")
    print("\nYou can now run: ./main.py --help")
    sys.exit(0)
