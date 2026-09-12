#!/usr/bin/env bash

# Quick start script for Augur Trading Dashboard
# Run this to get the dashboard up and running in 3 steps

echo "🎯 AUGUR TRADING DASHBOARD - QUICK START"
echo "======================================="
echo ""

# Step 1: Install dependencies
echo "📦 Step 1: Installing dependencies..."
echo ""

# Install Python deps
echo "Installing Python packages..."
pip install -r requirements.txt

# Install Node deps  
echo "Installing Node packages..."
cd ui
npm install
cd ..

echo ""
echo "✅ Dependencies installed!"
echo ""

# Step 2: Instructions
echo "🚀 Step 2: Start the services"
echo ""
echo "Open 3 terminal windows and run:"
echo ""
echo "Terminal 1 (Backend):"
echo "  python src/dashboard_api.py"
echo ""
echo "Terminal 2 (Frontend):"
echo "  cd ui && npm run dev"
echo ""
echo "Terminal 3 (Optional - Trading System):"
echo "  python scripts/demo_trading_system.py"
echo ""

# Step 3: Access dashboard
echo "🌐 Step 3: Access the dashboard"
echo ""
echo "Open your browser to:"
echo "  http://localhost:5173/"
echo ""

# Further instructions
echo "📚 Next steps:"
echo "  1. Read DASHBOARD_SETUP.md for quick overview"
echo "  2. Read DASHBOARD_INTEGRATION.md for wiring to trading system"
echo "  3. Read DASHBOARD_COMPLETE.md for full feature list"
echo ""

echo "Need help? Check the documentation files above! 📖"
echo ""
