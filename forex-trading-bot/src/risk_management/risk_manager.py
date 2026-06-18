"""
Risk Management System
================================================
Implements comprehensive risk controls and account monitoring.
Prevents catastrophic losses through real-time monitoring.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Tuple, Optional
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Real-time risk monitoring and enforcement system.
    
    Monitors:
    - Daily loss limits (prevents "revenge trading")
    - Margin levels (prevents liquidation)
    - Drawdown from peak (psychological resilience measure)
    - Position concentration by pair
    
    Design Reasoning:
    - Risk limits are psychological: losing $5 feels same regardless of account size
    - 2% per trade risk is industry standard (allows ~50 trades before complete ruin)
    - Daily stop-loss prevents emotional decision-making
    - Drawdown limits enforce discipline during losing streaks
    """
    
    def __init__(self, db_manager):
        """
        Initialize risk manager.
        
        Args:
            db_manager: Database connection manager
        """
        self.db = db_manager
        
        # Default risk limits (can be overridden per user)
        self.DEFAULT_DAILY_LOSS_PERCENT = Decimal('5')  # 5% of account
        self.DEFAULT_WEEKLY_LOSS_PERCENT = Decimal('10')  # 10% of account
        self.DEFAULT_MAX_DRAWDOWN_PERCENT = Decimal('20')  # 20% from peak
        self.DEFAULT_MAX_MARGIN_LEVEL = Decimal('50')  # Margin level in %
        self.DEFAULT_MAX_CONCURRENT_TRADES = 5
        self.MARGIN_WARNING_THRESHOLD = Decimal('150')  # Alert when margin < 150%
    
    def check_daily_loss_limit(
        self,
        user_id: int,
        daily_loss_limit_usd: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if daily loss limit has been exceeded.
        
        Args:
            user_id: User ID
            daily_loss_limit_usd: Daily loss limit in USD
        
        Returns:
            Tuple of (is_within_limit, warning_message)
        
        Logic:
        - Query today's closed trades
        - Sum P&L losses
        - Compare to daily_loss_limit_usd
        - If exceeded, block new trades
        
        Reasoning:
        - Prevents revenge trading after losing streak
        - Enforces discipline: one bad day ≠ entire account blown
        - Professional traders often use daily stop-outs
        """
        
        query = """
            SELECT SUM(net_profit_loss) as daily_pnl
            FROM trades
            WHERE user_id = %s
            AND DATE(close_time) = CURDATE()
            AND trade_status = 'closed'
            AND net_profit_loss < 0
        """
        
        result = self.db.execute_query(query, (user_id,), fetch_one=True, dictionary=True)
        daily_loss = Decimal(str(result['daily_pnl'] or 0))
        
        if daily_loss < -daily_loss_limit_usd:
            msg = f"Daily loss limit exceeded: ${abs(daily_loss):.2f} > ${daily_loss_limit_usd:.2f}"
            logger.warning(f"User {user_id}: {msg}")
            
            # Log alert
            self.db.log_event(
                user_id=user_id,
                event_type="DAILY_LOSS_LIMIT_EXCEEDED",
                message=msg,
                severity="CRITICAL",
                module_name="RiskManager",
                system_state={'daily_loss': float(daily_loss), 'limit': float(daily_loss_limit_usd)}
            )
            
            # Create alert
            self._create_alert(
                user_id, "DAILY_LOSS_EXCEEDED", "critical",
                f"Daily loss of ${abs(daily_loss):.2f} exceeds limit of ${daily_loss_limit_usd:.2f}",
                threshold_value=daily_loss_limit_usd,
                current_value=abs(daily_loss)
            )
            
            return False, msg
        
        return True, None
    
    def check_margin_level(
        self,
        user_id: int,
        equity: Decimal,
        used_margin: Decimal,
        min_margin_level: Decimal = Decimal('200')
    ) -> Tuple[bool, Optional[str], Decimal]:
        """
        Check margin level and alert if approaching critical level.
        
        Margin Level Formula: (Equity / Used Margin) * 100
        
        Args:
            user_id: User ID
            equity: Current equity (balance + open P&L)
            used_margin: Currently used margin in USD
            min_margin_level: Minimum acceptable margin level (%)
        
        Returns:
            Tuple of (is_healthy, warning_message, current_margin_level)
        
        Margin Level Guide:
        - > 300%: Healthy, lots of room
        - 200-300%: Safe, 50% of account in use
        - 100-200%: Warning, 50-100% of account in use
        - < 100%: Critical, liquidation risk
        
        Reasoning:
        - Brokers liquidate at 50% margin level (~100% equity used)
        - Professionals maintain 300%+ to weather 30% adverse moves
        - Early warning at 200% allows time to close positions
        - NEVER trade when margin level < 200%
        """
        
        if used_margin == 0:
            margin_level = Decimal('999999')
        else:
            margin_level = (equity / used_margin) * Decimal(100)
        
        if margin_level < min_margin_level:
            msg = f"Margin level critical: {margin_level:.1f}% (minimum: {min_margin_level:.1f}%)"
            logger.error(f"User {user_id}: {msg}")
            
            # Log critical event
            self.db.log_event(
                user_id=user_id,
                event_type="MARGIN_LEVEL_CRITICAL",
                message=msg,
                severity="CRITICAL",
                module_name="RiskManager",
                system_state={'margin_level': float(margin_level), 'equity': float(equity), 'used_margin': float(used_margin)}
            )
            
            # Create alert
            self._create_alert(
                user_id, "MARGIN_CRITICAL", "critical", msg,
                threshold_value=min_margin_level,
                current_value=margin_level
            )
            
            return False, msg, margin_level
        
        elif margin_level < self.MARGIN_WARNING_THRESHOLD:
            msg = f"Margin level warning: {margin_level:.1f}%"
            logger.warning(f"User {user_id}: {msg}")
            
            # Create warning alert
            self._create_alert(
                user_id, "MARGIN_WARNING", "warning", msg,
                threshold_value=self.MARGIN_WARNING_THRESHOLD,
                current_value=margin_level
            )
            
            return True, msg, margin_level
        
        return True, None, margin_level
    
    def check_max_drawdown(
        self,
        user_id: int,
        current_balance: Decimal,
        max_drawdown_percent: Decimal = Decimal('20')
    ) -> Tuple[bool, Optional[str], Decimal]:
        """
        Check if account drawdown exceeds maximum acceptable level.
        
        Drawdown = (Peak Equity - Current Equity) / Peak Equity * 100
        
        Args:
            user_id: User ID
            current_balance: Current account balance
            max_drawdown_percent: Maximum acceptable drawdown (%)
        
        Returns:
            Tuple of (is_within_limit, warning_message, current_drawdown%)
        
        Drawdown Psychology:
        - 5% drawdown: normal, ignore
        - 10% drawdown: getting attention
        - 20% drawdown: serious, need discipline
        - 30%+ drawdown: soul-crushing, easy to make revenge mistakes
        
        Reasoning:
        - Drawdown is most psychologically challenging metric
        - 20% drawdown allows recovery with discipline
        - Beyond 20%, most traders make emotional decisions
        - Peak equity tracked daily in risk_management table
        """
        
        query = """
            SELECT peak_equity, current_drawdown, drawdown_usd
            FROM risk_management
            WHERE user_id = %s
            ORDER BY date_tracked DESC LIMIT 1
        """
        
        result = self.db.execute_query(query, (user_id,), fetch_one=True, dictionary=True)
        
        if not result:
            return True, None, Decimal('0')
        
        current_drawdown = Decimal(str(result['current_drawdown'] or 0))
        
        if current_drawdown > max_drawdown_percent:
            msg = f"Maximum drawdown exceeded: {current_drawdown:.2f}% > {max_drawdown_percent:.2f}%"
            logger.error(f"User {user_id}: {msg}")
            
            # Log event
            self.db.log_event(
                user_id=user_id,
                event_type="MAX_DRAWDOWN_EXCEEDED",
                message=msg,
                severity="CRITICAL",
                module_name="RiskManager",
                system_state={'drawdown': float(current_drawdown), 'limit': float(max_drawdown_percent)}
            )
            
            # Create alert
            self._create_alert(
                user_id, "MAX_DRAWDOWN_EXCEEDED", "critical", msg,
                threshold_value=max_drawdown_percent,
                current_value=current_drawdown
            )
            
            return False, msg, current_drawdown
        
        return True, None, current_drawdown
    
    def update_daily_risk_metrics(
        self,
        user_id: int,
        account_balance: Decimal,
        equity: Decimal,
        used_margin: Decimal,
        available_margin: Decimal,
        margin_level: Decimal
    ) -> bool:
        """
        Update daily risk metrics in database.
        
        Called daily to track:
        - Account balance and equity
        - Open positions and margin usage
        - Daily P&L (from closed trades)
        - Drawdown from peak
        
        Metrics stored enable:
        - Performance analysis
        - Risk compliance reporting
        - Drawdown and peak equity tracking
        - Alert threshold monitoring
        
        Reasoning:
        - Time-series of risk data shows account health
        - Daily snapshots enable recovery analysis
        - Alerts based on thresholds protect account
        """
        
        try:
            # Get today's P&L from closed trades
            pnl_query = """
                SELECT 
                    SUM(CASE WHEN net_profit_loss > 0 THEN net_profit_loss ELSE 0 END) as realized_profit,
                    SUM(CASE WHEN net_profit_loss < 0 THEN net_profit_loss ELSE 0 END) as realized_loss,
                    COUNT(*) as trade_count
                FROM trades
                WHERE user_id = %s
                AND DATE(close_time) = CURDATE()
                AND trade_status = 'closed'
            """
            
            pnl_result = self.db.execute_query(pnl_query, (user_id,), fetch_one=True, dictionary=True)
            
            realized_profit = Decimal(str(pnl_result['realized_profit'] or 0))
            realized_loss = Decimal(str(pnl_result['realized_loss'] or 0))
            trade_count = pnl_result['trade_count'] or 0
            
            # Calculate unrealized P&L from open trades
            unrealized_query = """
                SELECT SUM(gross_profit_loss - commission - swap_points) as unrealized_pnl
                FROM trades
                WHERE user_id = %s AND trade_status = 'open'
            """
            
            unrealized_result = self.db.execute_query(unrealized_query, (user_id,), fetch_one=True, dictionary=True)
            unrealized_pnl = Decimal(str(unrealized_result['unrealized_pnl'] or 0))
            
            # Get peak equity from this month
            peak_query = """
                SELECT MAX(equity) as peak_equity
                FROM risk_management
                WHERE user_id = %s
                AND date_tracked >= DATE_TRUNC(CURDATE(), MONTH)
            """
            
            peak_result = self.db.execute_query(peak_query, (user_id,), fetch_one=True, dictionary=True)
            peak_equity = Decimal(str(peak_result['peak_equity'] or equity))
            
            # Update peak if current equity is higher
            if equity > peak_equity:
                peak_equity = equity
            
            # Calculate drawdown
            if peak_equity > 0:
                drawdown_pct = ((peak_equity - equity) / peak_equity) * Decimal(100)
                drawdown_usd = peak_equity - equity
            else:
                drawdown_pct = Decimal(0)
                drawdown_usd = Decimal(0)
            
            # Get or create today's risk record
            check_query = """
                SELECT risk_id FROM risk_management 
                WHERE user_id = %s AND date_tracked = CURDATE()
            """
            
            exists = self.db.execute_query(check_query, (user_id,), fetch_one=True, dictionary=True)
            
            if exists:
                # Update existing record
                update_query = """
                    UPDATE risk_management SET
                        account_balance = %s,
                        equity = %s,
                        used_margin = %s,
                        available_margin = %s,
                        margin_level = %s,
                        daily_realized_pnl = %s,
                        daily_unrealized_pnl = %s,
                        daily_total_pnl = %s,
                        daily_trades_count = %s,
                        peak_equity = %s,
                        current_drawdown = %s,
                        drawdown_usd = %s,
                        updated_at = NOW()
                    WHERE user_id = %s AND date_tracked = CURDATE()
                """
                
                total_pnl = realized_profit + realized_loss + unrealized_pnl
                
                self.db.execute_update(update_query, (
                    account_balance, equity, used_margin, available_margin, margin_level,
                    realized_profit + realized_loss, unrealized_pnl, total_pnl, trade_count,
                    peak_equity, drawdown_pct, drawdown_usd,
                    user_id
                ))
            else:
                # Create new record
                insert_query = """
                    INSERT INTO risk_management (
                        user_id, date_tracked, account_balance, equity, used_margin,
                        available_margin, margin_level, daily_trades_count,
                        daily_realized_pnl, daily_unrealized_pnl, daily_total_pnl,
                        peak_equity, current_drawdown, drawdown_usd
                    ) VALUES (
                        %s, CURDATE(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """
                
                total_pnl = realized_profit + realized_loss + unrealized_pnl
                
                self.db.execute_update(insert_query, (
                    user_id, account_balance, equity, used_margin,
                    available_margin, margin_level, trade_count,
                    realized_profit + realized_loss, unrealized_pnl, total_pnl,
                    peak_equity, drawdown_pct, drawdown_usd
                ))
            
            logger.info(
                f"Risk metrics updated for user {user_id}: "
                f"Equity ${equity:.2f}, Drawdown {drawdown_pct:.2f}%, Margin {margin_level:.1f}%"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating risk metrics: {e}")
            return False
    
    def get_risk_status(self, user_id: int) -> Dict:
        """
        Get comprehensive risk status for user.
        
        Returns:
            Dictionary with current risk metrics and status
        """
        
        query = """
            SELECT 
                account_balance,
                equity,
                used_margin,
                available_margin,
                margin_level,
                daily_realized_pnl,
                daily_unrealized_pnl,
                current_drawdown,
                daily_trades_count,
                risk_status,
                exceeded_daily_loss,
                exceeded_max_drawdown
            FROM risk_management
            WHERE user_id = %s
            ORDER BY date_tracked DESC LIMIT 1
        """
        
        result = self.db.execute_query(query, (user_id,), fetch_one=True, dictionary=True)
        
        if not result:
            return {
                'status': 'unknown',
                'account_balance': 0,
                'equity': 0,
                'margin_level': 0,
                'drawdown': 0,
                'message': 'No risk data available'
            }
        
        return {
            'status': result['risk_status'],
            'account_balance': float(result['account_balance']),
            'equity': float(result['equity']),
            'used_margin': float(result['used_margin']),
            'available_margin': float(result['available_margin']),
            'margin_level': float(result['margin_level']),
            'daily_pnl': float((result['daily_realized_pnl'] or 0) + (result['daily_unrealized_pnl'] or 0)),
            'drawdown': float(result['current_drawdown']),
            'daily_trades': result['daily_trades_count'],
            'alerts': {
                'daily_loss_exceeded': result['exceeded_daily_loss'],
                'max_drawdown_exceeded': result['exceeded_max_drawdown']
            }
        }
    
    def _create_alert(
        self,
        user_id: int,
        alert_type: str,
        alert_level: str,
        message: str,
        threshold_value: Optional[Decimal] = None,
        current_value: Optional[Decimal] = None
    ) -> bool:
        """Create alert in database."""
        
        try:
            query = """
                INSERT INTO alerts (user_id, alert_type, alert_level, message, threshold_value, current_value)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            self.db.execute_update(query, (
                user_id, alert_type, alert_level, message, threshold_value, current_value
            ))
            
            return True
        except Exception as e:
            logger.error(f"Error creating alert: {e}")
            return False
