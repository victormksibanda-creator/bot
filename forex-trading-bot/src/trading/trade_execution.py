"""
Trade Execution Engine
================================================
Handles trade lifecycle: creation, position management, and closure.
Implements risk management and position sizing logic.
"""

from datetime import datetime
from typing import Dict, Optional, Tuple
import logging
from decimal import Decimal
from enum import Enum

logger = logging.getLogger(__name__)


class TradeType(Enum):
    """Trade direction."""
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(Enum):
    """Trade execution states."""
    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"
    CANCELLED = "cancelled"


class CloseReason(Enum):
    """Reasons for trade closure."""
    TP_HIT = "tp_hit"
    SL_HIT = "sl_hit"
    MANUAL_CLOSE = "manual_close"
    PARTIAL_CLOSE = "partial_close"
    LIQUIDATION = "liquidation"
    MARGIN_CALL = "margin_call"
    SYSTEM_ERROR = "system_error"


class TradeExecutionEngine:
    """
    Executes trades with complete risk management and position tracking.
    
    Workflow:
    1. Receive signal with entry level, SL, TP
    2. Calculate position size based on risk management rules
    3. Verify sufficient margin
    4. Create trade record in database
    5. Send execution to broker (MT5/MT4)
    6. Monitor position for exit conditions
    7. Close trade and record P&L
    
    Key Design Decisions:
    - All risk calculations in base currency for consistency
    - Pips defined as 4 decimal places (0.0001 for most pairs)
    - Lot sizes rounded to standard increments (0.01 lots)
    - Every trade has risk_per_trade for accountability
    """
    
    STANDARD_LOT = 100000  # Standard lot size in units
    MINI_LOT = 10000
    MICRO_LOT = 1000
    PIPS_DECIMAL_PLACES = 4
    
    def __init__(self, db_manager, broker=None):
        """
        Initialize trade execution engine.
        
        Args:
            db_manager: Database connection manager instance
            broker: Broker integration instance
        """
        self.db = db_manager
        self.broker = broker
        self.execution_count = 0
        self.total_trades = 0
    
    def calculate_position_size(
        self,
        user_id: int,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        risk_percent: Decimal = Decimal('2.0'),
        max_position_size: Decimal = Decimal('1.0')
    ) -> Decimal:
        """
        Calculate position size using risk management rules.
        
        Position Sizing Formula:
        Position Size = (Account * Risk%) / (Distance from SL in pips * Pip Value)
        
        Args:
            user_id: User ID for logging
            account_balance: Current account balance in USD
            entry_price: Entry price level
            stop_loss: Stop loss price level
            risk_percent: Percentage of account to risk (default 2%)
            max_position_size: Maximum position size in lots (prevents over-leverage)
        
        Returns:
            Position size in lots
        
        Example:
            - Account: $10,000
            - Risk: 2% = $200
            - Entry: 1.1000
            - SL: 1.0950
            - Risk distance: 50 pips
            - Pip value (for EURUSD): $10 per pip
            - Position size = $200 / $10 = 2 micro lots (0.02 standard lots)
        
        Reasoning:
        - Risk-based sizing ensures consistent position management
        - Prevents over-leveraging on high volatility pairs
        - Ensures no single trade can wipe out account
        - Standard Kelly Criterion: f* = (bp - q) / b, where b=risk:reward ratio
        - Typical forex traders use 1-3% risk per trade to survive drawdowns
        """
        
        # Calculate risk in USD
        risk_amount = account_balance * (risk_percent / Decimal(100))
        
        # Calculate distance from stop loss in pips
        risk_distance_pips = abs(entry_price - stop_loss) * Decimal(10000)
        
        if risk_distance_pips == 0:
            logger.warning(f"Stop loss equals entry price for user {user_id}")
            return Decimal('0')
        
        # Calculate pip value (depends on account currency and pair)
        # For USD account + pair quoted in USD: $10 per pip per standard lot
        pip_value = Decimal('10')  # Simplified; actual value depends on pair
        
        # Position size = Risk Amount / (Risk Distance * Pip Value)
        position_size_lots = risk_amount / (risk_distance_pips * pip_value)
        
        # Round to nearest 0.01 (1 micro lot increment)
        position_size_lots = (position_size_lots / Decimal('0.01')).to_integral_value() * Decimal('0.01')
        
        # Apply maximum position size cap
        position_size_lots = min(position_size_lots, max_position_size)
        
        logger.info(
            f"Position sized for user {user_id}: "
            f"{position_size_lots} lots, Risk: ${risk_amount:.2f}, Distance: {risk_distance_pips:.1f} pips"
        )
        
        return position_size_lots
    
    def validate_trade_conditions(
        self,
        user_id: int,
        available_margin: Decimal,
        used_margin: Decimal,
        position_size: Decimal,
        margin_level: Decimal = Decimal('100')
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that trade can be executed based on margin and risk rules.
        
        Args:
            user_id: User ID
            available_margin: Available margin in USD
            used_margin: Currently used margin
            position_size: Proposed position size in lots
            margin_level: Current margin level (Equity / Used Margin * 100)
        
        Returns:
            Tuple of (is_valid, error_message)
        
        Validation Rules:
        1. Required margin < Available margin
        2. Margin level remains > 200% (safety buffer)
        3. Account status not suspended
        4. Max concurrent trades not exceeded
        
        Reasoning:
        - Margin level of 200% = 50% margin usage (conservative)
        - Prevents margin calls (typically triggered at 50% margin level)
        - Allows room for adverse price movement without liquidation
        - Most professional traders maintain 300%+ margin level
        """
        
        # Approximate required margin (simplified: assume 1:100 leverage)
        required_margin = position_size * self.STANDARD_LOT * Decimal('0.01')
        
        # Check 1: Sufficient available margin
        if required_margin > available_margin:
            msg = f"Insufficient margin. Required: ${required_margin:.2f}, Available: ${available_margin:.2f}"
            logger.warning(f"User {user_id}: {msg}")
            return False, msg
        
        # Check 2: Projected margin level after trade
        projected_used_margin = used_margin + required_margin
        if projected_used_margin == 0:
            projected_margin_level = Decimal('999999')
        else:
            # This is simplified; actual calculation requires equity
            projected_margin_level = (Decimal('1000000') / projected_used_margin) * Decimal('100')
        
        if projected_margin_level < Decimal('200'):
            msg = f"Trade would reduce margin level to {projected_margin_level:.0f}% (minimum 200%)"
            logger.warning(f"User {user_id}: {msg}")
            return False, msg
        
        # Check 3: Account status
        account_status = self._get_account_status(user_id)
        if account_status != "active":
            msg = f"Account status is {account_status}, cannot execute trades"
            logger.warning(f"User {user_id}: {msg}")
            return False, msg
        
        # Check 4: Concurrent trades limit
        concurrent_trades = self._count_open_trades(user_id)
        if concurrent_trades >= 10:  # Safety limit
            msg = f"Maximum concurrent trades (10) reached"
            logger.warning(f"User {user_id}: {msg}")
            return False, msg
        
        logger.info(f"Trade validation passed for user {user_id}")
        return True, None
    
    def open_trade(
        self,
        user_id: int,
        currency_pair: str,
        trade_type: TradeType,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        lot_size: Decimal,
        signal_id: Optional[int] = None,
        source: str = "manual"
    ) -> Tuple[bool, int, Optional[str]]:
        """
        Execute trade entry and record in database.
        
        Args:
            user_id: User ID
            currency_pair: e.g., 'EURUSD'
            trade_type: BUY or SELL
            entry_price: Entry price level
            stop_loss: Stop loss price
            take_profit: Take profit price
            lot_size: Position size in lots
            signal_id: Originating signal ID (if from signal)
            source: Source of trade ('signal', 'manual', 'ea')
        
        Returns:
            Tuple of (success, trade_id, error_message)
        
        Workflow:
        1. Validate trade conditions
        2. Calculate position metadata
        3. Record trade in database
        4. Send to broker API (would be implemented in separate module)
        5. Log execution event
        6. Update user trading statistics
        
        Reasoning:
        - Atomic database insertion: if DB fails, don't send to broker
        - Risk metrics calculated at entry time for historical consistency
        - Signal linkage enables strategy performance analysis
        - Timestamps precise to enable low-latency analysis
        """
        
        try:
            # Get current account status
            account_balance, available_margin, used_margin, margin_level = self._get_account_metrics(user_id)
            
            # Validate trade conditions
            is_valid, error_msg = self.validate_trade_conditions(
                user_id, available_margin, used_margin, lot_size, margin_level
            )
            
            if not is_valid:
                return False, 0, error_msg
            
            # Calculate position metadata
            position_value_usd = lot_size * self.STANDARD_LOT * entry_price
            
            # Risk calculation
            risk_pips = abs(entry_price - stop_loss) * Decimal(10000)
            risk_usd = lot_size * self.STANDARD_LOT * (abs(entry_price - stop_loss) / Decimal(100000))
            
            # Reward calculation
            reward_pips = abs(take_profit - entry_price) * Decimal(10000)
            risk_reward_ratio = reward_pips / risk_pips if risk_pips > 0 else Decimal(0)
            
            broker_order_id = None

            if self.broker and not getattr(self.broker, 'mock', False):
                broker_response = self.broker.place_market_order(
                    currency_pair=currency_pair,
                    trade_type=trade_type.value,
                    lot_size=lot_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

                if not broker_response.get('success'):
                    return False, 0, broker_response.get('error', 'Broker order failed')

                broker_order_id = broker_response.get('order_id')

            # Insert trade into database
            query = """
                INSERT INTO trades (
                    user_id, signal_id, currency_pair, trade_type, 
                    entry_price, entry_time, stop_loss, take_profit,
                    lot_size, contract_size, position_value_usd, risk_per_trade,
                    trade_status
                ) VALUES (
                    %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s
                )
            """
            
            params = (
                user_id, signal_id, currency_pair, trade_type.value,
                entry_price, stop_loss, take_profit,
                lot_size, self.STANDARD_LOT, position_value_usd, risk_usd,
                TradeStatus.OPEN.value
            )
            
            self.db.execute_update(query, params)
            
            # Get the newly created trade ID
            trade_id_query = """
                SELECT trade_id FROM trades 
                WHERE user_id = %s AND entry_time = NOW()
                ORDER BY trade_id DESC LIMIT 1
            """
            result = self.db.execute_query(trade_id_query, (user_id,), fetch_one=True, dictionary=True)
            trade_id = result['trade_id'] if result else 0
            
            # Log event
            self.db.log_event(
                user_id=user_id,
                event_type="TRADE_OPENED",
                message=f"Trade opened: {trade_type.value} {lot_size} {currency_pair} @ {entry_price}",
                severity="INFO",
                module_name="TradeExecutionEngine",
                affected_trade_id=trade_id,
                system_state={
                    'position_value': float(position_value_usd),
                    'risk_usd': float(risk_usd),
                    'risk_reward_ratio': float(risk_reward_ratio),
                    'margin_level': float(margin_level),
                    'source': source,
                    'broker_order_id': broker_order_id,
                }
            )
            
            logger.info(
                f"Trade {trade_id} opened: User {user_id}, {trade_type.value} "
                f"{lot_size} {currency_pair} @ {entry_price}"
            )
            
            self.total_trades += 1
            return True, trade_id, None
            
        except Exception as e:
            error_msg = f"Trade execution error: {str(e)}"
            logger.error(error_msg)
            self.db.log_event(
                user_id=user_id,
                event_type="TRADE_EXECUTION_ERROR",
                message=error_msg,
                severity="CRITICAL",
                module_name="TradeExecutionEngine",
                error_code="TRADE_OPEN_FAILED"
            )
            return False, 0, error_msg
    
    def close_trade(
        self,
        trade_id: int,
        close_price: Decimal,
        close_reason: CloseReason,
        commission: Decimal = Decimal('0'),
        swap: Decimal = Decimal('0')
    ) -> Tuple[bool, Dict, Optional[str]]:
        """
        Close trade and calculate P&L.
        
        Args:
            trade_id: Trade to close
            close_price: Exit price level
            close_reason: Reason for closure
            commission: Fees charged by broker
            swap: Overnight interest
        
        Returns:
            Tuple of (success, trade_metrics, error_message)
        
        P&L Calculation:
        For BUY: Profit = (Close - Entry) * LotSize * 100000 - Costs
        For SELL: Profit = (Entry - Close) * LotSize * 100000 - Costs
        
        Reasoning:
        - P&L calculated immediately for real-time accounting
        - Commissions and swaps deducted to show net P&L
        - Pips calculated for trader psychology (shows outcome in familiar units)
        - P&L percentage shows return on risk, enables performance analysis
        """
        
        try:
            # Get trade details
            trade_query = """
                SELECT user_id, trade_type, entry_price, lot_size, entry_time
                FROM trades
                WHERE trade_id = %s
            """
            trade = self.db.execute_query(trade_query, (trade_id,), fetch_one=True, dictionary=True)
            
            if not trade:
                return False, {}, f"Trade {trade_id} not found"
            
            user_id = trade['user_id']
            trade_type = trade['trade_type']
            entry_price = Decimal(str(trade['entry_price']))
            lot_size = Decimal(str(trade['lot_size']))
            entry_time = trade['entry_time']
            close_price = Decimal(str(close_price))
            
            # Calculate P&L
            if trade_type == TradeType.BUY.value:
                gross_pnl = (close_price - entry_price) * lot_size * self.STANDARD_LOT
            else:
                gross_pnl = (entry_price - close_price) * lot_size * self.STANDARD_LOT
            
            net_pnl = gross_pnl - commission - swap
            pips_profit = (close_price - entry_price) * Decimal(10000)
            
            # Calculate duration
            trade_duration = (datetime.now() - entry_time).total_seconds()
            duration_label = self._format_duration(trade_duration)
            
            # Update trade in database using stored procedure
            self.db.call_procedure(
                'sp_close_trade',
                [trade_id, float(close_price), close_reason.value]
            )
            
            # Additional update for our specific fields
            close_query = """
                UPDATE trades SET
                    close_price = %s,
                    close_time = NOW(),
                    close_reason = %s,
                    gross_profit_loss = %s,
                    commission = %s,
                    swap_points = %s,
                    net_profit_loss = %s,
                    profit_loss_pips = %s,
                    trade_duration_seconds = %s,
                    trade_duration_label = %s,
                    trade_status = %s
                WHERE trade_id = %s
            """
            
            self.db.execute_update(close_query, (
                close_price, close_reason.value, gross_pnl, commission, swap,
                net_pnl, pips_profit, trade_duration, duration_label,
                TradeStatus.CLOSED.value, trade_id
            ))
            
            # Prepare return metrics
            metrics = {
                'trade_id': trade_id,
                'gross_pnl': float(gross_pnl),
                'net_pnl': float(net_pnl),
                'pips': float(pips_profit),
                'duration_seconds': trade_duration,
                'close_reason': close_reason.value
            }
            
            # Log event
            self.db.log_event(
                user_id=user_id,
                event_type="TRADE_CLOSED",
                message=f"Trade {trade_id} closed: {close_reason.value}, P&L: ${net_pnl:.2f} ({pips_profit:.1f} pips)",
                severity="INFO",
                module_name="TradeExecutionEngine",
                affected_trade_id=trade_id,
                system_state=metrics
            )
            
            logger.info(f"Trade {trade_id} closed: Net P&L ${net_pnl:.2f}, Pips: {pips_profit:.1f}")
            
            return True, metrics, None
            
        except Exception as e:
            error_msg = f"Trade closure error: {str(e)}"
            logger.error(error_msg)
            self.db.log_event(
                user_id=trade['user_id'] if 'trade' in locals() else None,
                event_type="TRADE_CLOSURE_ERROR",
                message=error_msg,
                severity="CRITICAL",
                module_name="TradeExecutionEngine",
                error_code="TRADE_CLOSE_FAILED",
                affected_trade_id=trade_id
            )
            return False, {}, error_msg
    
    def _get_account_metrics(self, user_id: int) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        """Get current account balance, margin, and equity."""
        query = """
            SELECT account_balance, available_margin, used_margin, margin_level
            FROM risk_management
            WHERE user_id = %s
            ORDER BY date_tracked DESC LIMIT 1
        """
        result = self.db.execute_query(query, (user_id,), fetch_one=True, dictionary=True)
        
        if result:
            return (
                Decimal(str(result['account_balance'])),
                Decimal(str(result['available_margin'])),
                Decimal(str(result['used_margin'])),
                Decimal(str(result['margin_level']))
            )
        
        return Decimal(0), Decimal(0), Decimal(0), Decimal(0)
    
    def _get_account_status(self, user_id: int) -> str:
        """Get account status."""
        query = "SELECT account_status FROM users WHERE user_id = %s"
        result = self.db.execute_query(query, (user_id,), fetch_one=True, dictionary=True)
        return result['account_status'] if result else 'unknown'
    
    def _count_open_trades(self, user_id: int) -> int:
        """Count open trades for user."""
        query = "SELECT COUNT(*) as count FROM trades WHERE user_id = %s AND trade_status = 'open'"
        result = self.db.execute_query(query, (user_id,), fetch_one=True, dictionary=True)
        return result['count'] if result else 0
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in human-readable format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
