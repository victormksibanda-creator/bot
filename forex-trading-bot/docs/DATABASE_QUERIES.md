# Common Database Queries - Forex Trading Bot

This guide contains ready-to-use SQL queries for common trading bot operations.

## 1. ACCOUNT & PERFORMANCE QUERIES

### Get User Account Overview
```sql
SELECT 
    u.user_id,
    u.username,
    u.broker_account_number,
    u.account_type,
    u.account_status,
    r.account_balance,
    r.equity,
    r.margin_level,
    r.current_drawdown,
    r.daily_realized_pnl,
    r.daily_trades_count
FROM users u
LEFT JOIN risk_management r ON u.user_id = r.user_id AND r.date_tracked = CURDATE()
WHERE u.user_id = 1;
```

### Get Daily Performance Summary
```sql
SELECT 
    DATE(close_time) as trade_date,
    COUNT(*) as total_trades,
    SUM(CASE WHEN net_profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades,
    SUM(CASE WHEN net_profit_loss < 0 THEN 1 ELSE 0 END) as losing_trades,
    SUM(net_profit_loss) as daily_pnl,
    ROUND(SUM(net_profit_loss) / COUNT(*), 2) as avg_pnl_per_trade,
    MAX(net_profit_loss) as best_trade,
    MIN(net_profit_loss) as worst_trade,
    ROUND((SUM(CASE WHEN net_profit_loss > 0 THEN 1 ELSE 0 END) / COUNT(*)) * 100, 2) as win_rate
FROM trades
WHERE user_id = 1 AND trade_status = 'closed'
GROUP BY DATE(close_time)
ORDER BY trade_date DESC
LIMIT 30;
```

### Get Monthly Performance
```sql
SELECT 
    DATE_TRUNC(close_time, MONTH) as month,
    COUNT(*) as total_trades,
    SUM(net_profit_loss) as monthly_pnl,
    ROUND(SUM(net_profit_loss) / (SELECT initial_balance FROM users WHERE user_id = 1) * 100, 2) as monthly_return_percent
FROM trades
WHERE user_id = 1 AND trade_status = 'closed'
GROUP BY DATE_TRUNC(close_time, MONTH)
ORDER BY month DESC;
```

## 2. SIGNAL ANALYSIS QUERIES

### Get All Pending Signals
```sql
SELECT 
    signal_id,
    currency_pair,
    signal_type,
    confidence_score,
    entry_level,
    stop_loss,
    take_profit,
    risk_reward_ratio,
    generated_at,
    signal_expiry,
    parameters_used
FROM trade_signals
WHERE user_id = 1 
    AND is_acted_upon = FALSE
    AND signal_expiry > NOW()
ORDER BY confidence_score DESC, generated_at DESC;
```

### Analyze Signal Quality (Hit Rate by Confidence Level)
```sql
SELECT 
    FLOOR(ts.confidence_score / 10) * 10 as confidence_bucket,
    COUNT(*) as total_signals,
    SUM(CASE WHEN t.net_profit_loss > 0 THEN 1 ELSE 0 END) as winning_signals,
    ROUND((SUM(CASE WHEN t.net_profit_loss > 0 THEN 1 ELSE 0 END) / COUNT(*)) * 100, 2) as hit_rate,
    ROUND(AVG(t.net_profit_loss), 2) as avg_pnl,
    SUM(t.net_profit_loss) as total_pnl
FROM trade_signals ts
LEFT JOIN trades t ON ts.signal_id = t.signal_id AND t.trade_status = 'closed'
WHERE ts.user_id = 1
GROUP BY FLOOR(ts.confidence_score / 10) * 10
ORDER BY confidence_bucket DESC;
```

### Get Best Performing Indicator/Strategy
```sql
SELECT 
    ts.signal_source as strategy,
    COUNT(*) as total_trades,
    SUM(CASE WHEN t.net_profit_loss > 0 THEN 1 ELSE 0 END) as wins,
    ROUND((SUM(CASE WHEN t.net_profit_loss > 0 THEN 1 ELSE 0 END) / COUNT(*)) * 100, 2) as win_rate,
    ROUND(SUM(t.net_profit_loss), 2) as total_pnl,
    ROUND(AVG(t.net_profit_loss), 2) as avg_pnl_per_trade,
    ROUND(SUM(CASE WHEN t.net_profit_loss > 0 THEN t.net_profit_loss ELSE 0 END) / 
          ABS(SUM(CASE WHEN t.net_profit_loss < 0 THEN t.net_profit_loss ELSE 0 END)), 2) as profit_factor
FROM trade_signals ts
LEFT JOIN trades t ON ts.signal_id = t.signal_id AND t.trade_status = 'closed'
WHERE ts.user_id = 1 AND t.trade_id IS NOT NULL
GROUP BY ts.signal_source
ORDER BY total_pnl DESC;
```

## 3. TRADE ANALYSIS QUERIES

### Get Active Trades with Current Status
```sql
SELECT 
    t.trade_id,
    t.currency_pair,
    t.trade_type,
    t.entry_price,
    t.entry_time,
    t.lot_size,
    t.stop_loss,
    t.take_profit,
    t.risk_per_trade,
    TIMESTAMPDIFF(MINUTE, t.entry_time, NOW()) as duration_minutes,
    -- Would need real-time market data to calculate:
    -- (current_price - entry_price) * lot_size * 100000 as unrealized_pnl
    -- (current_price - entry_price) * 10000 as unrealized_pips
    CASE 
        WHEN t.trade_type = 'BUY' THEN 'Long'
        WHEN t.trade_type = 'SELL' THEN 'Short'
    END as position_type
FROM trades t
WHERE t.user_id = 1 AND t.trade_status = 'open'
ORDER BY t.entry_time DESC;
```

### Analyze Closed Trades by Pair
```sql
SELECT 
    currency_pair,
    COUNT(*) as total_trades,
    SUM(CASE WHEN net_profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades,
    SUM(CASE WHEN net_profit_loss < 0 THEN 1 ELSE 0 END) as losing_trades,
    ROUND((SUM(CASE WHEN net_profit_loss > 0 THEN 1 ELSE 0 END) / COUNT(*)) * 100, 2) as win_rate,
    SUM(net_profit_loss) as total_pnl,
    ROUND(AVG(net_profit_loss), 2) as avg_pnl,
    ROUND(AVG(profit_loss_pips), 2) as avg_pips,
    MAX(net_profit_loss) as best_trade,
    MIN(net_profit_loss) as worst_trade
FROM trades
WHERE user_id = 1 AND trade_status = 'closed'
GROUP BY currency_pair
ORDER BY total_pnl DESC;
```

### Get Top Performing Days
```sql
SELECT 
    DATE(close_time) as trade_date,
    COUNT(*) as trade_count,
    SUM(net_profit_loss) as daily_pnl,
    ROUND(SUM(net_profit_loss) / (SELECT initial_balance FROM users WHERE user_id = 1) * 100, 2) as daily_return,
    SUM(CASE WHEN net_profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades
FROM trades
WHERE user_id = 1 AND trade_status = 'closed'
GROUP BY DATE(close_time)
ORDER BY daily_pnl DESC
LIMIT 20;
```

### Analyze Trade Duration Impact
```sql
SELECT 
    CASE 
        WHEN trade_duration_seconds < 60 THEN '< 1 min'
        WHEN trade_duration_seconds < 300 THEN '1-5 min'
        WHEN trade_duration_seconds < 900 THEN '5-15 min'
        WHEN trade_duration_seconds < 3600 THEN '15 min - 1 hour'
        WHEN trade_duration_seconds < 86400 THEN '1-24 hours'
        ELSE '> 24 hours'
    END as duration_category,
    COUNT(*) as total_trades,
    ROUND(AVG(net_profit_loss), 2) as avg_pnl,
    ROUND(SUM(net_profit_loss), 2) as total_pnl,
    ROUND((SUM(CASE WHEN net_profit_loss > 0 THEN 1 ELSE 0 END) / COUNT(*)) * 100, 2) as win_rate
FROM trades
WHERE user_id = 1 AND trade_status = 'closed'
GROUP BY duration_category
ORDER BY trade_duration_seconds;
```

## 4. RISK MANAGEMENT QUERIES

### Monitor Daily Risk Status
```sql
SELECT 
    date_tracked,
    account_balance,
    equity,
    margin_level,
    daily_realized_pnl,
    daily_unrealized_pnl,
    daily_total_pnl,
    current_drawdown,
    peak_equity,
    CASE 
        WHEN exceeded_daily_loss = TRUE THEN 'ALERT: Daily Loss Exceeded'
        WHEN exceeded_max_drawdown = TRUE THEN 'ALERT: Max Drawdown Exceeded'
        WHEN margin_level < 200 THEN 'WARNING: Margin Low'
        WHEN margin_level < 150 THEN 'CRITICAL: Margin Critical'
        WHEN risk_status = 'critical' THEN 'CRITICAL'
        WHEN risk_status = 'warning' THEN 'WARNING'
        ELSE 'NORMAL'
    END as status
FROM risk_management
WHERE user_id = 1
ORDER BY date_tracked DESC
LIMIT 30;
```

### Get Drawdown History (Last 90 Days)
```sql
SELECT 
    date_tracked,
    peak_equity,
    equity,
    ROUND(current_drawdown, 2) as drawdown_percent,
    ROUND(drawdown_usd, 2) as drawdown_usd,
    daily_realized_pnl,
    margin_level
FROM risk_management
WHERE user_id = 1 
    AND date_tracked >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
ORDER BY date_tracked DESC;
```

### Calculate Sharpe Ratio
```sql
-- Sharpe Ratio = (Average Return - Risk-Free Rate) / Standard Deviation
WITH daily_returns AS (
    SELECT 
        DATE(close_time) as trade_date,
        SUM(net_profit_loss) as daily_pnl
    FROM trades
    WHERE user_id = 1 AND trade_status = 'closed'
        AND close_time >= DATE_SUB(NOW(), INTERVAL 90 DAY)
    GROUP BY DATE(close_time)
)
SELECT 
    ROUND(AVG(daily_pnl), 2) as avg_daily_return,
    ROUND(STDDEV(daily_pnl), 2) as daily_volatility,
    ROUND((AVG(daily_pnl) - (0.02 / 252)) / STDDEV(daily_pnl) * SQRT(252), 4) as sharpe_ratio_annualized
FROM daily_returns;
```

### Max Consecutive Wins/Losses
```sql
WITH trade_results AS (
    SELECT 
        trade_id,
        close_time,
        CASE WHEN net_profit_loss > 0 THEN 'WIN' ELSE 'LOSS' END as result,
        ROW_NUMBER() OVER (ORDER BY close_time) - 
        ROW_NUMBER() OVER (ORDER BY close_time 
                           PARTITION BY CASE WHEN net_profit_loss > 0 THEN 'WIN' ELSE 'LOSS' END) 
        as streak_group
    FROM trades
    WHERE user_id = 1 AND trade_status = 'closed'
)
SELECT 
    result,
    COUNT(*) as streak_length
FROM trade_results
GROUP BY streak_group, result
ORDER BY streak_length DESC
LIMIT 1;
```

## 5. SYSTEM & LOGGING QUERIES

### Get Recent System Events
```sql
SELECT 
    log_id,
    created_at,
    event_type,
    severity_level,
    module_name,
    message,
    error_code,
    performance_ms
FROM system_logs
WHERE user_id = 1
    AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY created_at DESC
LIMIT 100;
```

### Find Errors by Type
```sql
SELECT 
    error_code,
    event_type,
    COUNT(*) as occurrences,
    MIN(created_at) as first_occurrence,
    MAX(created_at) as last_occurrence,
    ROUND(AVG(performance_ms), 2) as avg_performance_ms
FROM system_logs
WHERE severity_level IN ('ERROR', 'CRITICAL')
GROUP BY error_code, event_type
ORDER BY occurrences DESC;
```

### Performance Analysis (Slow Operations)
```sql
SELECT 
    module_name,
    event_type,
    COUNT(*) as total_events,
    ROUND(AVG(performance_ms), 2) as avg_ms,
    MAX(performance_ms) as max_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY performance_ms) as p95_ms
FROM system_logs
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    AND performance_ms IS NOT NULL
GROUP BY module_name, event_type
HAVING avg_ms > 100
ORDER BY avg_ms DESC;
```

## 6. MARKET DATA QUERIES

### Get Latest Candles for Technical Analysis
```sql
SELECT 
    timestamp,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    tick_volume
FROM market_data
WHERE user_id = 1 
    AND currency_pair = 'EURUSD'
    AND timeframe = 'H1'
ORDER BY timestamp DESC
LIMIT 50;
```

### Calculate Moving Averages
```sql
SELECT 
    timestamp,
    close_price,
    ROUND(AVG(close_price) OVER (ORDER BY timestamp ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 5) as ma_20,
    ROUND(AVG(close_price) OVER (ORDER BY timestamp ROWS BETWEEN 49 PRECEDING AND CURRENT ROW), 5) as ma_50,
    ROUND(AVG(close_price) OVER (ORDER BY timestamp ROWS BETWEEN 199 PRECEDING AND CURRENT ROW), 5) as ma_200
FROM market_data
WHERE user_id = 1 
    AND currency_pair = 'EURUSD'
    AND timeframe = 'D1'
ORDER BY timestamp DESC
LIMIT 200;
```

### High/Low Price Levels (Support/Resistance)
```sql
SELECT 
    MONTH(timestamp) as month,
    MAX(high_price) as monthly_high,
    MIN(low_price) as monthly_low,
    FIRST_VALUE(open_price) OVER (PARTITION BY MONTH(timestamp) ORDER BY timestamp) as month_open,
    LAST_VALUE(close_price) OVER (PARTITION BY MONTH(timestamp) ORDER BY timestamp) as month_close
FROM market_data
WHERE user_id = 1 AND currency_pair = 'EURUSD' AND timeframe = 'D1'
GROUP BY MONTH(timestamp)
ORDER BY timestamp DESC;
```

## 7. ALERT & COMPLIANCE QUERIES

### Get Unresolved Alerts
```sql
SELECT 
    alert_id,
    alert_type,
    alert_level,
    message,
    affected_pair,
    threshold_value,
    current_value,
    created_at
FROM alerts
WHERE user_id = 1 AND is_resolved = FALSE
ORDER BY alert_level DESC, created_at DESC;
```

### Alert Statistics
```sql
SELECT 
    DATE(created_at) as alert_date,
    alert_level,
    COUNT(*) as alert_count
FROM alerts
WHERE user_id = 1
    AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(created_at), alert_level
ORDER BY alert_date DESC, alert_level;
```

## 8. USAGE EXAMPLES

### Track P&L Over Time (for charting)
```sql
SELECT 
    DATE(close_time) as date,
    SUM(SUM(net_profit_loss)) OVER (ORDER BY DATE(close_time)) as cumulative_pnl
FROM trades
WHERE user_id = 1 AND trade_status = 'closed'
GROUP BY DATE(close_time)
ORDER BY date;
```

### Export Trade Journal (for tax purposes)
```sql
SELECT 
    trade_id,
    DATE(entry_time) as entry_date,
    entry_time,
    currency_pair,
    trade_type,
    entry_price,
    lot_size,
    close_price,
    close_time,
    TIMESTAMPDIFF(DAY, entry_time, close_time) as holding_days,
    net_profit_loss,
    commission,
    CASE WHEN net_profit_loss > 0 THEN 'Win' ELSE 'Loss' END as result
FROM trades
WHERE user_id = 1 AND trade_status = 'closed'
    AND YEAR(close_time) = YEAR(CURDATE())
ORDER BY close_time;
```

---

**Note**: All queries use user_id = 1 as example. Replace with actual user ID.

See [ARCHITECTURE.md](ARCHITECTURE.md) for database schema details.
