@echo off
REM Quick start script for Augur Trading Dashboard (Windows)
REM Run this to get the dashboard up and running

echo.
echo =========================================
echo  AUGUR TRADING DASHBOARD - QUICK START
echo =========================================
echo.

REM Step 1: Install dependencies
echo 📦 Step 1: Installing dependencies...
echo.

echo Installing Python packages...
pip install -r requirements.txt

echo.
echo Installing Node packages...
cd ui
call npm install
cd ..

echo.
echo ✅ Dependencies installed!
echo.

REM Step 2: Instructions
echo 🚀 Step 2: Start the services
echo.
echo Open 3 PowerShell/Command Prompt windows and run:
echo.
echo Terminal 1 ^(Backend^):
echo   python dashboard_api.py
echo.
echo Terminal 2 ^(Frontend^):
echo   cd ui
echo   npm run dev
echo.
echo Terminal 3 ^(Optional - Trading System^):
echo   python demo_trading_system.py
echo.

REM Step 3: Access dashboard
echo 🌐 Step 3: Access the dashboard
echo.
echo Open your browser to:
echo   http://localhost:5173/
echo.

REM Further instructions
echo 📚 Next steps:
echo   1. Read DASHBOARD_SETUP.md for quick overview
echo   2. Read DASHBOARD_INTEGRATION.md for wiring to trading system
echo   3. Read DASHBOARD_COMPLETE.md for full feature list
echo.

echo Need help? Check the documentation files above! 📖
echo.

pause
