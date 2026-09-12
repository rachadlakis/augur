"""
Technical indicators for trading signals.
Includes RSI, MACD, Moving Averages.
"""

import math
from typing import List, Dict, Tuple, Optional


class TechnicalIndicators:
    """Calculate technical indicators from price history"""
    
    @staticmethod
    def compute_rsi(prices: List[float], period: int = 14) -> List[Optional[float]]:
        """
        Compute RSI (Relative Strength Index) using Wilder's smoothing.
        Returns list of RSI values, same length as prices.
        """
        if len(prices) < period + 1:
            return [None] * len(prices)
        
        rsi_values = [None] * len(prices)
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        # Initial average gain/loss
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi_values[period] = 100 - (100 / (1 + rs)) if rs != float('inf') else 0
        
        # Wilder's smoothing for remaining values
        for i in range(period + 1, len(prices)):
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
            
            rs = avg_gain / avg_loss if avg_loss != 0 else 0
            rsi_values[i] = 100 - (100 / (1 + rs)) if rs != float('inf') else 0
        
        return rsi_values
    
    @staticmethod
    def compute_ema(prices: List[float], span: int) -> List[Optional[float]]:
        """
        Compute EMA (Exponential Moving Average).
        """
        if len(prices) < span:
            return [None] * len(prices)
        
        ema_values = [None] * len(prices)
        multiplier = 2 / (span + 1)
        
        # First EMA is simple average
        ema_values[span - 1] = sum(prices[:span]) / span
        
        # Calculate EMA for remaining values
        for i in range(span, len(prices)):
            ema_values[i] = prices[i] * multiplier + ema_values[i - 1] * (1 - multiplier)
        
        return ema_values
    
    @staticmethod
    def compute_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
        """
        Compute MACD (Moving Average Convergence Divergence).
        Returns: (macd_line, signal_line, histogram)
        """
        if len(prices) < slow + signal:
            return (
                [None] * len(prices),
                [None] * len(prices),
                [None] * len(prices)
            )
        
        # Compute EMAs
        ema_fast = TechnicalIndicators.compute_ema(prices, fast)
        ema_slow = TechnicalIndicators.compute_ema(prices, slow)
        
        # Compute MACD line
        macd_line = []
        for i in range(len(prices)):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                macd_line.append(ema_fast[i] - ema_slow[i])
            else:
                macd_line.append(None)
        
        # Compute signal line (EMA of MACD)
        signal_line = TechnicalIndicators.compute_ema(macd_line, signal)
        
        # Compute histogram
        histogram = []
        for i in range(len(macd_line)):
            if macd_line[i] is not None and signal_line[i] is not None:
                histogram.append(macd_line[i] - signal_line[i])
            else:
                histogram.append(None)
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def compute_sma(prices: List[float], period: int) -> List[Optional[float]]:
        """
        Compute SMA (Simple Moving Average).
        """
        if len(prices) < period:
            return [None] * len(prices)
        
        sma_values = [None] * period
        for i in range(period - 1, len(prices)):
            sma_values.append(sum(prices[i - period + 1:i + 1]) / period)
        
        return sma_values[:len(prices)]


class SignalDetector:
    """Detect entry and exit signals based on indicators"""
    
    WINDOW_SIZE = 5  # Bars to look back for signal correlation
    
    @staticmethod
    def detect_entry_signals(
        prices: List[float],
        rsi_values: List[Optional[float]],
        macd_line: List[Optional[float]],
        signal_line: List[Optional[float]],
        ma_fast: List[Optional[float]],
        ma_mid: List[Optional[float]],
        ma_slow: List[Optional[float]]
    ) -> Dict[str, any]:
        """
        Detect entry signals based on RSI oversold bounce + MACD golden cross + uptrend.
        
        Entry conditions:
        - Must be in uptrend (MA_FAST > MA_MID > MA_SLOW)
        - RSI oversold bounce (RSI < 30 → RSI > 30)
        - MACD golden cross (MACD crosses above signal line)
        - Both signals within WINDOW_SIZE bars
        """
        if len(prices) < 2:
            return {"signal": None, "strength": 0, "reasons": []}
        
        current_idx = len(prices) - 1
        prev_idx = current_idx - 1
        
        reasons = []
        score = 0
        
        # Check uptrend
        if (ma_fast[current_idx] is not None and 
            ma_mid[current_idx] is not None and 
            ma_slow[current_idx] is not None):
            in_uptrend = (ma_fast[current_idx] > ma_mid[current_idx] and 
                         ma_mid[current_idx] > ma_slow[current_idx])
            if in_uptrend:
                reasons.append("In uptrend (50>100>200)")
                score += 25
            else:
                reasons.append("Not in uptrend")
                return {"signal": None, "strength": 0, "reasons": reasons}
        
        # Check RSI oversold bounce
        rsi_bounce_bar = None
        if (rsi_values[prev_idx] is not None and rsi_values[current_idx] is not None and
            rsi_values[prev_idx] < 30 and rsi_values[current_idx] > 30):
            rsi_bounce_bar = current_idx
            reasons.append(f"RSI oversold bounce (was {rsi_values[prev_idx]:.1f}→{rsi_values[current_idx]:.1f})")
            score += 35
        
        # Check MACD golden cross
        macd_cross_bar = None
        if (macd_line[prev_idx] is not None and signal_line[prev_idx] is not None and
            macd_line[current_idx] is not None and signal_line[current_idx] is not None and
            macd_line[prev_idx] < signal_line[prev_idx] and 
            macd_line[current_idx] > signal_line[current_idx]):
            macd_cross_bar = current_idx
            reasons.append("MACD golden cross")
            score += 40
        
        # Check signal correlation within window
        if rsi_bounce_bar is not None and macd_cross_bar is not None:
            if abs(rsi_bounce_bar - macd_cross_bar) <= SignalDetector.WINDOW_SIZE:
                reasons.append(f"Signals aligned within {SignalDetector.WINDOW_SIZE} bars")
                score += 20
                return {"signal": "BUY", "strength": min(100, score), "reasons": reasons}
        
        return {"signal": None, "strength": score, "reasons": reasons}
    
    @staticmethod
    def detect_exit_signals(
        prices: List[float],
        rsi_values: List[Optional[float]],
        macd_line: List[Optional[float]],
        signal_line: List[Optional[float]]
    ) -> Dict[str, any]:
        """
        Detect exit signals based on RSI overbought retreat + MACD death cross or centerline drop.
        
        Exit conditions:
        - RSI overbought retreat (RSI > 70 → RSI < 65)
        - MACD death cross (MACD crosses below signal) OR centerline drop (MACD > 0 → MACD < 0)
        - Both signals within WINDOW_SIZE bars
        """
        if len(prices) < 2:
            return {"signal": None, "strength": 0, "reasons": []}
        
        current_idx = len(prices) - 1
        prev_idx = current_idx - 1
        
        reasons = []
        score = 0
        
        # Check RSI overbought retreat
        rsi_retreat_bar = None
        if (rsi_values[prev_idx] is not None and rsi_values[current_idx] is not None and
            rsi_values[prev_idx] > 70 and rsi_values[current_idx] < 65):
            rsi_retreat_bar = current_idx
            reasons.append(f"RSI overbought retreat (was {rsi_values[prev_idx]:.1f}→{rsi_values[current_idx]:.1f})")
            score += 35
        
        # Check MACD death cross
        macd_death_bar = None
        if (macd_line[prev_idx] is not None and signal_line[prev_idx] is not None and
            macd_line[current_idx] is not None and signal_line[current_idx] is not None and
            macd_line[prev_idx] > signal_line[prev_idx] and 
            macd_line[current_idx] < signal_line[current_idx]):
            macd_death_bar = current_idx
            reasons.append("MACD death cross")
            score += 40
        
        # Check MACD centerline drop
        macd_centerline_bar = None
        if (macd_line[prev_idx] is not None and macd_line[current_idx] is not None and
            macd_line[prev_idx] > 0 and macd_line[current_idx] < 0):
            macd_centerline_bar = current_idx
            reasons.append("MACD centerline drop")
            score += 30
        
        # Check signal correlation within window
        if rsi_retreat_bar is not None and (macd_death_bar is not None or macd_centerline_bar is not None):
            macd_bar = macd_death_bar if macd_death_bar is not None else macd_centerline_bar
            if abs(rsi_retreat_bar - macd_bar) <= SignalDetector.WINDOW_SIZE:
                reasons.append(f"Exit signals aligned within {SignalDetector.WINDOW_SIZE} bars")
                score += 20
                return {"signal": "SELL", "strength": min(100, score), "reasons": reasons}
        
        return {"signal": None, "strength": score, "reasons": reasons}


class PositionSizer:
    """Calculate position size based on risk management"""
    
    @staticmethod
    def calculate_position_size(
        account_equity: float,
        risk_percent: float = 0.02,
        entry_price: float = 100.0,
        stop_price: Optional[float] = None,
        max_position_value: Optional[float] = None
    ) -> Dict[str, any]:
        """
        Calculate position size based on risk percentage and stop loss.
        
        Args:
            account_equity: Current account equity
            risk_percent: Max risk per trade (default 2%)
            entry_price: Entry price per share
            stop_price: Stop loss price (if None, uses default 2% below entry)
            max_position_value: Max value to allocate (if None, uses buying power)
        
        Returns:
            dict with quantity, risk_amount, position_value
        """
        if entry_price <= 0:
            return {"quantity": 0, "risk_amount": 0, "position_value": 0, "error": "Invalid entry price"}
        
        # Calculate risk amount
        risk_amount = account_equity * risk_percent
        
        # Calculate stop distance
        if stop_price is None:
            stop_distance = entry_price * 0.02  # Default 2% below entry
        else:
            stop_distance = entry_price - stop_price
        
        if stop_distance <= 0:
            return {"quantity": 0, "risk_amount": 0, "position_value": 0, "error": "Invalid stop price"}
        
        # Calculate quantity based on risk
        quantity = int(risk_amount / stop_distance)
        
        # Apply max position value limit if specified
        if max_position_value:
            max_qty = int(max_position_value / entry_price)
            quantity = min(quantity, max_qty)
        
        position_value = quantity * entry_price
        actual_risk = quantity * stop_distance
        
        return {
            "quantity": quantity,
            "risk_amount": actual_risk,
            "position_value": position_value,
            "stop_distance": stop_distance
        }
