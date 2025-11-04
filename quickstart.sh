#!/bin/bash
# Quick Start Guide - Plesk Health Check
# Run this script to get started quickly

echo "=========================================="
echo "PLESK HEALTH CHECK - QUICK START"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "❌ Error: main.py not found. Please run from plesk-health-check directory"
    exit 1
fi

# Install dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt --quiet

echo "✅ Dependencies installed"
echo ""

# Run installation test
echo "🔍 Running installation test..."
python3 test_installation.py

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Installation test failed. Please fix errors above."
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ INSTALLATION COMPLETE!"
echo "=========================================="
echo ""
echo "📋 NEXT STEPS:"
echo ""
echo "1. Run your first health check:"
echo "   ./main.py"
echo ""
echo "2. Run with email report:"
echo "   ./main.py --email"
echo ""
echo "3. Save a baseline for comparison:"
echo "   ./main.py --save-baseline"
echo ""
echo "4. Run on Plesk server with sudo:"
echo "   sudo ./main.py --email --save-baseline"
echo ""
echo "5. Setup daily cron (add to crontab):"
echo "   0 6 * * * /path/to/main.py --email --no-terminal"
echo ""
echo "📖 For more info, see README.md"
echo "=========================================="
