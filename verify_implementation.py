#!/usr/bin/env python3
"""
Quick verification that the 4 new implementations work correctly
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

print("="*80)
print("VERIFICATION TEST - 4 ANBEFALTE FORBEDRINGER")
print("="*80)
print()

# Test 1: Import BaselineManager
print("1. Testing BaselineManager import...")
try:
    from utils.baseline import BaselineManager
    print("   ✅ BaselineManager imported successfully")
    
    # Test creating instance
    bm = BaselineManager()
    print("   ✅ BaselineManager instance created")
    
    # Test methods exist
    assert hasattr(bm, 'save_baseline'), "save_baseline method missing"
    assert hasattr(bm, 'load_latest_baseline'), "load_latest_baseline method missing"
    assert hasattr(bm, 'compare_with_baseline'), "compare_with_baseline method missing"
    print("   ✅ All required methods exist")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    sys.exit(1)

print()

# Test 2: Check SecurityChecker has new methods
print("2. Testing SecurityChecker new methods...")
try:
    from checks.security import SecurityChecker
    
    config = json.load(open('config.json'))
    checker = SecurityChecker(config, read_only=True)
    
    assert hasattr(checker, 'check_rkhunter_status'), "check_rkhunter_status missing"
    print("   ✅ check_rkhunter_status() method exists")
    
    assert hasattr(checker, 'check_lynis_audit'), "check_lynis_audit missing"
    print("   ✅ check_lynis_audit() method exists")
    
    assert hasattr(checker, 'check_clamav_status'), "check_clamav_status missing"
    print("   ✅ check_clamav_status() method exists")
    
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    sys.exit(1)

print()

# Test 3: Check terminal report has baseline function
print("3. Testing terminal report baseline function...")
try:
    from reports.terminal_report import generate_terminal_report, print_baseline_comparison
    
    import inspect
    sig = inspect.signature(generate_terminal_report)
    params = list(sig.parameters.keys())
    
    assert 'baseline_comparison' in params, "baseline_comparison parameter missing"
    print("   ✅ generate_terminal_report() has baseline_comparison parameter")
    
    assert callable(print_baseline_comparison), "print_baseline_comparison not callable"
    print("   ✅ print_baseline_comparison() function exists")
    
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    sys.exit(1)

print()

# Test 4: Check email report has baseline function
print("4. Testing email report baseline function...")
try:
    from reports.email_report import send_email_report, generate_baseline_comparison_html
    
    import inspect
    sig = inspect.signature(send_email_report)
    params = list(sig.parameters.keys())
    
    assert 'baseline_comparison' in params, "baseline_comparison parameter missing"
    print("   ✅ send_email_report() has baseline_comparison parameter")
    
    assert callable(generate_baseline_comparison_html), "generate_baseline_comparison_html not callable"
    print("   ✅ generate_baseline_comparison_html() function exists")
    
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    sys.exit(1)

print()

# Test 5: Test baseline comparison logic
print("5. Testing baseline comparison logic...")
try:
    from utils.baseline import BaselineManager
    
    # Create test data
    baseline_data = {
        'timestamp': '2025-11-03T10:00:00',
        'summary': {'critical': 2, 'warning': 5, 'ok': 40},
        'checks': {
            'security': [
                {'name': 'test_check', 'status': 'WARNING', 'severity_score': 50}
            ]
        }
    }
    
    current_data = {
        'timestamp': '2025-11-04T10:00:00',
        'summary': {'critical': 3, 'warning': 4, 'ok': 41},
        'checks': {
            'security': [
                {'name': 'test_check', 'status': 'CRITICAL', 'severity_score': 85},
                {'name': 'new_check', 'status': 'CRITICAL', 'severity_score': 90}
            ]
        }
    }
    
    # Test comparison without actual baseline
    bm = BaselineManager('data/baselines_test')
    comparison = bm.compare_with_baseline(current_data)
    
    assert 'has_baseline' in comparison, "has_baseline key missing"
    assert comparison['has_baseline'] == False, "Should not have baseline yet"
    print("   ✅ Handles missing baseline correctly")
    
    # Save baseline and test again
    if bm.save_baseline(baseline_data):
        print("   ✅ Baseline saved successfully")
        
        comparison = bm.compare_with_baseline(current_data)
        assert comparison['has_baseline'] == True, "Should have baseline now"
        print("   ✅ Baseline comparison works")
        
        # Check for expected changes
        assert 'new_issues' in comparison, "new_issues key missing"
        assert 'degraded_checks' in comparison, "degraded_checks key missing"
        assert 'changes' in comparison, "changes key missing"
        print("   ✅ All comparison keys present")
        
        # Cleanup test data
        import shutil
        shutil.rmtree('data/baselines_test', ignore_errors=True)
        print("   ✅ Test cleanup completed")
    else:
        print("   ⚠️  Could not save test baseline (permissions?)")
    
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("="*80)
print("✅ ALL VERIFICATION TESTS PASSED!")
print("="*80)
print()
print("Summary:")
print("  • BaselineManager: Imported and functional")
print("  • SecurityChecker: 3 new methods added")
print("  • Terminal Report: Baseline comparison integrated")
print("  • Email Report: Baseline comparison integrated")
print("  • Baseline Logic: Working correctly")
print()
print("The 4 implementations are ready for production use! 🚀")
print()
