#!/usr/bin/env python
"""
Integration test for Augur Trading Dashboard.
Tests backend API, WebSocket connection, and trading operations.
"""

import asyncio
import json
import aiohttp
import websockets
from datetime import datetime

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/dashboard"

async def test_health_check():
    """Test health check endpoint"""
    print("\n🏥 Testing health check...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/api/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Health check passed: {data}")
                    return True
                else:
                    print(f"❌ Health check failed: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False


async def test_portfolio_endpoint():
    """Test portfolio REST endpoint"""
    print("\n📊 Testing portfolio endpoint...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/api/portfolio") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Portfolio endpoint working")
                    print(f"   Account Equity: ${data['account_equity']:,.2f}")
                    print(f"   Total P&L: ${data['total_pnl']:,.2f}")
                    print(f"   Positions: {len(data['positions'])}")
                    print(f"   Recent Trades: {len(data['recent_trades'])}")
                    return True
                else:
                    print(f"❌ Portfolio endpoint failed: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Portfolio endpoint error: {e}")
        return False


async def test_positions_endpoint():
    """Test positions REST endpoint"""
    print("\n📍 Testing positions endpoint...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/api/positions") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Positions endpoint working")
                    print(f"   Total positions: {len(data)}")
                    for pos in data:
                        print(f"   - {pos['symbol']}: {pos['quantity']} @ ${pos['current_price']:.2f}")
                    return True
                else:
                    print(f"❌ Positions endpoint failed: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Positions endpoint error: {e}")
        return False


async def test_command_parsing():
    """Test natural language command parsing"""
    print("\n💬 Testing command parsing...")
    test_commands = [
        "sell AAPL at $150",
        "close position",
        "adjust size to 100",
        "show portfolio summary",
    ]
    
    try:
        async with aiohttp.ClientSession() as session:
            for cmd in test_commands:
                payload = {"text": cmd}
                async with session.post(
                    f"{BASE_URL}/api/command",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        understood = "✅" if data.get("understood") else "❌"
                        print(f"{understood} '{cmd}' → {data.get('reasoning')}")
                    else:
                        print(f"❌ Command failed: {cmd} - {response.status}")
        return True
    except Exception as e:
        print(f"❌ Command parsing error: {e}")
        return False


async def test_websocket_connection():
    """Test WebSocket connection and real-time updates"""
    print("\n🔗 Testing WebSocket connection...")
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("✅ WebSocket connected")
            
            # Receive portfolio update
            print("📡 Waiting for portfolio update...")
            message = await asyncio.wait_for(websocket.recv(), timeout=5)
            data = json.loads(message)
            
            if data.get("type") == "portfolio_update":
                print("✅ Received portfolio update")
                portfolio = data.get("data", {})
                print(f"   Account Equity: ${portfolio.get('account_equity', 0):,.2f}")
                print(f"   Positions: {len(portfolio.get('positions', []))}")
            
            return True
    except asyncio.TimeoutError:
        print("❌ WebSocket timeout - no message received within 5 seconds")
        return False
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        return False


async def test_position_close_action():
    """Test closing a position"""
    print("\n🔴 Testing position close action...")
    try:
        # First get current positions
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/api/positions") as response:
                if response.status != 200:
                    print("❌ Could not get positions")
                    return False
                
                positions = await response.json()
                if not positions:
                    print("⚠️  No positions to close")
                    return False
                
                first_position = positions[0]
                symbol = first_position["symbol"]
                
                # Try to close the position
                action_payload = {
                    "type": "CLOSE_POSITION",
                    "symbol": symbol,
                    "params": {}
                }
                
                async with session.post(
                    f"{BASE_URL}/api/action",
                    json=action_payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ Position closed: {symbol}")
                        print(f"   P&L: ${data.get('pnl', 0):.2f}")
                        return True
                    else:
                        print(f"❌ Close action failed: {response.status}")
                        return False
    except Exception as e:
        print(f"❌ Position close error: {e}")
        return False


async def test_price_updates():
    """Test real-time price updates via WebSocket"""
    print("\n💹 Testing real-time price updates...")
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("Connected, waiting for price updates...")
            
            # Collect updates for a few seconds
            updates_received = 0
            start_time = datetime.now()
            
            while (datetime.now() - start_time).total_seconds() < 5:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1)
                    data = json.loads(message)
                    
                    if data.get("type") == "portfolio_update":
                        updates_received += 1
                        positions = data.get("data", {}).get("positions", [])
                        if positions:
                            print(f"📡 Update #{updates_received}: {len(positions)} position(s)")
                except asyncio.TimeoutError:
                    continue
            
            if updates_received > 0:
                print(f"✅ Received {updates_received} portfolio updates")
                return True
            else:
                print("❌ No updates received")
                return False
    except Exception as e:
        print(f"❌ Price update error: {e}")
        return False


async def run_all_tests():
    """Run all integration tests"""
    print("=" * 70)
    print("🧪 AUGUR TRADING DASHBOARD - INTEGRATION TESTS")
    print("=" * 70)
    print(f"Backend URL: {BASE_URL}")
    print(f"WebSocket URL: {WS_URL}")
    print("=" * 70)
    
    results = {}
    
    # Run tests
    results["health_check"] = await test_health_check()
    results["portfolio"] = await test_portfolio_endpoint()
    results["positions"] = await test_positions_endpoint()
    results["command_parsing"] = await test_command_parsing()
    results["websocket"] = await test_websocket_connection()
    results["price_updates"] = await test_price_updates()
    results["close_position"] = await test_position_close_action()
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_flag in results.items():
        status = "✅ PASS" if passed_flag else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("=" * 70)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 70)
    
    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
