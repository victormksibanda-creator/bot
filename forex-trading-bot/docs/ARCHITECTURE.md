# Forex Trading Bot - Architecture & Database Design Guide

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Database Schema](#database-schema)
3. [Key Design Decisions](#key-design-decisions)
4. [Workflow & Execution Flow](#workflow--execution-flow)
5. [Security Best Practices](#security-best-practices)
6. [Backup & Recovery Strategy](#backup--recovery-strategy)
7. [Scalability Recommendations](#scalability-recommendations)
8. [Performance Optimization](#performance-optimization)

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Market Data Feed (MT5/MT4)                    │
│              Real-time candles, tick data, news feeds             │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│              Trading Bot Core Engine (Python)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐          │
│  │   Market     │  │   Signal     │  │   Trade       │          │
│  │   Data       │  │   Generator  │  │   Execution   │          │
│  │   Collector  │  │   (Technical │  │   Engine      │          │
│  │              │  │    Analysis) │  │               │          │
│  └──────────────┘  └──────────────┘  └───────────────┘          │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Risk Management System                         │ │
│  │  • Daily/Weekly loss tracking   • Margin monitoring         │ │
│  │  • Position sizing              • Drawdown limits           │ │
│  └────────────────────────────────────────────────────────────┘ │
└────┬─────────────┬──────────────┬──────────────┬────────────────┘
     │             │              │              │
     ▼             ▼              ▼              ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
│ MySQL    │ │ Logging  │ │ Alerts   │ │ Performance  │
│ Database │ │ System   │ │ Manager  │ │ Metrics      │
└──────────┘ └──────────┘ └──────────┘ └──────────────┘
```

### Technology Stack

| Component | Technology | Reasoning |
|-----------|-----------|-----------|
| **Programming** | Python 3.9+ | Fast development, rich libraries, good ML integration |
| **Database** | MySQL 8.0+ | Reliable, ACID transactions, proven for trading |
| **Broker Integration** | MetaTrader5 | Industry standard, powerful API, real market connection |
| **Deployment** | Linux VPS or Windows | 24/7 uptime, low latency to brokers |
| **Data Analysis** | Pandas, NumPy | Fast calculations, industry standard for finance |
| **Indicators** | TA-Lib | C-based implementation, very fast indicator calculations |

---

## Database Schema

### 1. Users Table
Stores trader and account information.

**Key Fields:**
- `user_id`: Primary identifier
- `broker_account_number`: Unique per broker
- `account_type`: Demo or Live (prevents accidental live trades)
- `account_status`: active, paused, suspended, closed
- `initial_balance`: Tracks account starting point

**Why This Design:**
- Separates user identity from trading data
- Supports multi-broker setups
- Account status prevents trading after suspension/margin call
- Initial balance enables ROI calculations

**Indexes:**
- PRIMARY KEY: `user_id`
- UNIQUE: `broker_account_number` (prevent duplicates)
- INDEX: `email`, `username`, `account_status` (for lookups)

### 2. Market Data Table
OHLCV (Open, High, Low, Close, Volume) candle data.

**Key Fields:**
- `currency_pair`, `timeframe`, `timestamp`: Composite unique key
- `open_price`, `high_price`, `low_price`, `close_price`: Price levels
- `volume`, `tick_volume`: Trading activity
- `is_confirmed`: Whether candle is closed (not still forming)

**Why This Design:**
- One row per candle per pair per timeframe
- Partitioned by year for fast queries and archival
- Unique constraint prevents duplicates
- `is_confirmed` flag handles incomplete (current) candles

**Why Partitioning:**
- Table can grow to millions of rows
- Year partitions mean each partition is ~1-3GB (manageable)
- Old years can be archived/deleted without affecting current data
- SELECT on recent data stays fast

**Indexes:**
- UNIQUE: `(user_id, currency_pair, timeframe, timestamp)`
- INDEX: `(user_id, currency_pair, timestamp DESC)` - Latest candles
- INDEX: `(currency_pair, timeframe, timestamp)` - Signal generation
- INDEX: `timestamp` - Time-based queries

**Example Query Performance:**
```sql
-- Get last 50 5-minute candles for EURUSD
SELECT * FROM market_data 
WHERE currency_pair = 'EURUSD' AND timeframe = 'M5'
ORDER BY timestamp DESC LIMIT 50;
-- Uses index on (currency_pair, timeframe, timestamp)
-- Returns in <1ms
```

### 3. Trade Signals Table
Generated signals from technical indicators.

**Key Fields:**
- `signal_type`: BUY, SELL, HOLD
- `confidence_score`: 0-100% confidence level
- `entry_level`, `stop_loss`, `take_profit`: Price levels
- `risk_reward_ratio`: TP distance / SL distance
- `is_acted_upon`: Whether signal resulted in trade

**Why This Design:**
- Complete audit trail of signal generation
- Links signals to actual trades for backtesting analysis
- Confidence score enables filtering low-quality signals
- Risk/reward ratio ensures edge before trading

**Why Store All Signals:**
- Enables analysis: which signal type/confidence level is profitable?
- Backtesting: test signal quality before deploying
- Performance tracking: measure signal accuracy over time
- Legal compliance: audit trail for regulatory reviews

**Indexes:**
- INDEX: `(user_id, currency_pair)` - All signals for pair
- INDEX: `(generated_at DESC)` - Recent signals
- INDEX: `(confidence_score DESC)` - High-confidence signals
- INDEX: `is_acted_upon` - Signals not yet acted on

### 4. Trades Table (Core)
Every executed trade with complete P&L tracking.

**Key Fields:**
- Entry side: `trade_type`, `entry_price`, `entry_time`
- Exit side: `close_price`, `close_time`, `close_reason`
- Position: `lot_size`, `position_value_usd`, `contract_size`
- Risk: `stop_loss`, `take_profit`, `risk_per_trade`
- P&L: `gross_profit_loss`, `commission`, `swap_points`, `net_profit_loss`
- Metrics: `profit_loss_pips`, `trade_duration_seconds`

**Why Denormalized P&L:**
Storing calculated P&L fields (not just prices) is denormalization, but:
- Speeds up analytics (no recalculation)
- Provides audit trail of P&L at time of closure
- Prevents database errors if formulas change
- Snapshot matches historical broker statements

**Real-World P&L Calculation Example:**

```
BUY 1 standard lot EURUSD @ 1.1000, SL 1.0950, TP 1.1050

Entry:
- Entry price: 1.1000
- Lot size: 1.0 (standard lot = 100,000 units)
- Position value: 1.0 * 100,000 * 1.1000 = $110,000

Exit (close at 1.1025):
- Exit price: 1.1025
- Price movement: 1.1025 - 1.1000 = 0.0025 (25 pips)
- Gross P&L: 0.0025 * 100,000 = $250
- Commission: $5 (typical $5 per standard lot)
- Overnight swap: $1 (depends on interest rates)
- Net P&L: $250 - $5 - $1 = $244

Pips: 0.0025 * 10,000 = 25 pips
Return %: 244 / 110,000 * 100 = 0.22%
```

**Indexes:**
- INDEX: `(user_id, currency_pair)` - Pair-specific analysis
- INDEX: `(entry_time DESC)` - Recent trades
- INDEX: `(close_time DESC)` - Closed trades
- INDEX: `status` - Open vs closed separation
- INDEX: `(user_id, trade_status, close_time)` - Closed trades for user
- INDEX: `net_profit_loss` - P&L analysis

### 5. Risk Management Table
Daily aggregated risk metrics and account snapshots.

**Key Fields:**
- Account: `account_balance`, `equity`, `margin_level`
- Daily P&L: `daily_realized_pnl`, `daily_unrealized_pnl`
- Risk: `daily_risk_usd`, `max_margin_level`, `max_drawdown_limit`
- Alerts: `exceeded_daily_loss`, `exceeded_weekly_loss`, `exceeded_max_drawdown`

**Why Daily Table:**
- Snapshots at end of day enable drawdown tracking
- `peak_equity` field tracks highest equity (needed for drawdown%)
- Time-series data shows account health trajectory
- Enables compliance reporting (daily P&L audit trails)

**Drawdown Calculation:**
```
Peak equity this month: $10,000
Current equity: $8,500
Current drawdown: (10,000 - 8,500) / 10,000 * 100 = 15%
```

**CRITICAL: Equity vs Balance**
- **Balance**: Actual money in account (fixed until withdrawal)
- **Equity**: Balance + open position P&L (changes with every price move)
- **Margin Level**: Equity / Used Margin * 100%

Example:
```
Balance: $10,000
Open trade position P&L: -$500 (currently losing)
Equity: $10,000 - $500 = $9,500
Used margin: $5,000 (10% of position)
Margin level: $9,500 / $5,000 * 100 = 190%
Status: WARNING (getting close to 100% liquidation level)
```

### 6. System Logs Table
Audit trail for debugging and compliance.

**Key Fields:**
- `event_type`: TRADE_OPENED, API_ERROR, SIGNAL_GENERATED, etc.
- `severity_level`: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `module_name`: TradeExecutionEngine, RiskManager, SignalGenerator
- `error_code`: For categorizing errors
- `stack_trace`: Exception details
- `system_state`: JSON snapshot of relevant state

**Why System State Snapshot:**
When error occurs, save what was happening:
```json
{
  "user_id": 1,
  "open_trades": 3,
  "margin_level": 185.5,
  "account_equity": 9500,
  "last_signal": "BUY EURUSD",
  "market_price": 1.1015,
  "api_latency_ms": 450
}
```

Enables quick problem diagnosis without re-running scenarios.

**Indexes:**
- INDEX: `(severity_level, created_at DESC)` - Error alerts
- INDEX: `(user_id, created_at DESC)` - User event history
- INDEX: `(error_code, created_at DESC)` - Error frequency analysis

---

## Key Design Decisions

### Decision 1: Immutable Core Tables
**Trades, Market Data, Trade Signals are immutable** (no UPDATE after INSERT).

**Reasoning:**
- Audit compliance: Final P&L must match broker statement
- Backtesting: Can't change historical data accidentally
- Debugging: Traces are frozen, prevent investigation confusion
- Correction: If error, INSERT correction record, don't UPDATE

**Example:**
If trade closes with wrong P&L:
```sql
-- WRONG: Never do this
UPDATE trades SET net_profit_loss = -50 WHERE trade_id = 123;

-- RIGHT: Create correction record
INSERT INTO system_logs (...) 
VALUES ('TRADE_PL_CORRECTION', 'Manual correction for trade 123', ...);
-- Then close trade cleanly through API, start fresh
```

### Decision 2: Decimal Over Float
**All money values use `DECIMAL(12, 2)` not FLOAT**.

**Reasoning:**
```python
# Float arithmetic is imprecise
balance = 100.0
for i in range(100):
    balance -= 0.1
print(balance)  # Outputs 9.99999999999998, not 10.0!

# This causes:
# - P&L miscalculations
# - Margin level wrong
# - Account closing with pennies missing
```

MySQL DECIMAL stores exact decimal values, preventing these errors.

### Decision 3: Partitioning on Time
**Market Data, Trades, Logs tables partitioned by YEAR**.

**Reasoning:**
- Each partition ~1-3GB (manageable size)
- Old data (2024) in old partition, recent (2026) in recent partition
- SELECT on 2026 data doesn't scan 2024 data
- Can archive/delete old partitions without affecting new data
- Query performance stays fast even with 10+ years of data

**Example:**
```sql
-- Query only scans p_2026 partition
SELECT * FROM market_data 
WHERE timestamp > '2026-01-01' 
ORDER BY timestamp DESC LIMIT 100;
-- Execution: <1ms (only scans current year)

-- If no partitioning, would scan all rows
-- Execution: 100ms+ (scans 10 years of data)
```

### Decision 4: Denormalization for Performance
**Risk Management table denormalizes daily metrics** instead of calculating from Trades.

**Reasoning:**
```sql
-- NORMALIZED: Calculate every time (SLOW)
SELECT 
    SUM(net_profit_loss) as daily_pnl
FROM trades
WHERE user_id = 1 AND DATE(close_time) = CURDATE();
-- For large accounts: scans 1000s of rows, takes 100+ms

-- DENORMALIZED: Lookup (FAST)
SELECT daily_realized_pnl, daily_unrealized_pnl
FROM risk_management
WHERE user_id = 1 AND date_tracked = CURDATE();
-- Looks up 1 row, takes <1ms

-- For real-time trading, 100ms delay = potential missed signals
```

### Decision 5: Cascade Deletes (Careful!)
**Foreign key cascade deletes only on user deletion**.

**Reasoning:**
- Traders rarely delete accounts
- When they do, delete everything (trades, signals, logs)
- NEVER cascade delete on Risk Management → could delete P&L history
- NEVER cascade delete on Trades → audit trail integrity

```sql
FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;
-- If user deleted, all their trades deleted too (acceptable)

FOREIGN KEY (signal_id) REFERENCES trade_signals(signal_id) ON DELETE SET NULL;
-- If signal deleted, trade remains but signal_id becomes NULL
-- (uncommon: signals rarely deleted)
```

---

## Workflow & Execution Flow

### Trade Execution Workflow

```
1. SIGNAL GENERATION (Indicator Analysis)
   ├─ Get last 50 candles for EURUSD M5
   ├─ Calculate RSI(14), MA(20), MA(50)
   ├─ Detect crossover: MA(20) crosses above MA(50)
   ├─ RSI > 50 but < 70 (confirming strength without overbought)
   └─ INSERT into trade_signals
      {signal_id: 4521, signal_type: 'BUY', confidence: 85%, ...}

2. SIGNAL VALIDATION
   ├─ Check confidence >= 70% (only trade high-quality signals)
   ├─ Check risk_reward_ratio >= 1.5 (reward at least 1.5x risk)
   ├─ Check entry within recent price action
   └─ If all pass, proceed; else skip signal

3. RISK CHECKS (Before executing)
   ├─ Get user's current risk metrics
   ├─ Check daily_loss_limit
   │  └─ If already lost 4% today (limit 5%), can only risk $200
   ├─ Check margin_level > 200%
   │  └─ If margin 150%, can't open new trades
   ├─ Check max_concurrent_trades < limit
   │  └─ If 5 open trades (limit 5), can't open new trade
   └─ If any fail, create alert and skip trade

4. POSITION SIZING
   ├─ Get account balance: $10,000
   ├─ Risk percent: 2%
   ├─ Risk amount: $10,000 * 2% = $200
   ├─ Entry: 1.1010, SL: 1.0960
   ├─ Risk distance: 50 pips
   ├─ Position size: $200 / (50 pips * $10/pip) = 0.4 standard lots
   └─ Use 0.4 lots for this trade

5. TRADE EXECUTION
   ├─ Validate trade conditions passed
   ├─ INSERT into trades table
   │  {user_id: 1, pair: 'EURUSD', entry: 1.1010, ...}
   ├─ Send order to MetaTrader5 API
   ├─ MetaTrader5 returns: trade_id = 98765 (broker's ID)
   ├─ UPDATE trades.mt5_trade_id = 98765
   └─ Log event: "TRADE_OPENED, Trade 98765"

6. POSITION MONITORING (Continuous Loop)
   ├─ Every tick, update trade's current P&L
   ├─ Check if stop_loss or take_profit hit
   ├─ Monitor trailing stop (if enabled)
   ├─ Update margin_level (equity might be changing)
   └─ Check for liquidation risk

7. TRADE CLOSURE
   ├─ Stop Loss Hit: Price touches 1.0960
   │  ├─ Call close_trade(trade_id, close_price=1.0960, reason='sl_hit')
   │  ├─ P&L: -$200 (exactly at risk limit)
   │  └─ Log: "TRADE_CLOSED, SL Hit"
   │
   ├─ Take Profit Hit: Price touches 1.1060
   │  ├─ Call close_trade(trade_id, close_price=1.1060, reason='tp_hit')
   │  ├─ P&L: +$200 (exactly at reward target)
   │  └─ Log: "TRADE_CLOSED, TP Hit"
   │
   └─ Manual Close: Trader closes position
      ├─ Reason: 'manual_close'
      ├─ P&L: Depends on exit price
      └─ Log: "TRADE_CLOSED, Manual"

8. DAILY RECONCILIATION (End of Day)
   ├─ Sum all closed trades P&L: $420.50 (net profit)
   ├─ Get unrealized P&L from open trades: -$50
   ├─ Total daily P&L: $370.50
   ├─ Check against daily_loss_limit: +$370.50 is well within
   ├─ UPDATE risk_management with daily metrics
   ├─ Check drawdown: No exceeded limits
   └─ Send summary email to trader
```

### Real-World Example Trade Execution

**Setup:**
- Trader: John
- Account: $10,000, USD
- Risk per trade: 2% = $200

**Signal:**
- EUR/USD at 1.1010
- Buy signal with 85% confidence
- Entry: 1.1010
- Stop Loss: 1.0960 (50 pips below entry)
- Take Profit: 1.1060 (50 pips above entry)

**Position Sizing:**
```
Risk Amount = $10,000 * 2% = $200
Risk Distance = 50 pips
Pip Value (EURUSD) = $10 per pip per standard lot
Position Size = $200 / (50 * $10) = 0.4 standard lots = 40,000 units
Position Value at Entry = 40,000 * 1.1010 = $44,040
```

**Execution:**

1. **Trade Opens at 1.1010**
   ```
   INSERT INTO trades VALUES (
       user_id: 1,
       currency_pair: 'EURUSD',
       trade_type: 'BUY',
       entry_price: 1.1010,
       entry_time: 2026-06-12 14:30:00,
       stop_loss: 1.0960,
       take_profit: 1.1060,
       lot_size: 0.4,
       position_value_usd: 44040,
       risk_per_trade: 200,
       trade_status: 'open'
   )
   ```

2. **Price Action (every tick)**
   - 14:31: Price goes to 1.1015 (+5 pips)
     - Current P&L: +5 * $10 * 0.4 = +$20
   - 14:32: Price goes to 1.1025 (+15 pips)
     - Current P&L: +15 * $10 * 0.4 = +$60
   - 14:45: Price goes to 1.1050 (+40 pips)
     - Current P&L: +40 * $10 * 0.4 = +$160

3. **Price Moves to 1.1060 (TP Hit!)**
   ```
   CALL sp_close_trade(
       trade_id: 1,
       close_price: 1.1060,
       close_reason: 'tp_hit'
   )
   
   Calculations:
   - Gross P&L: (1.1060 - 1.1010) * 0.4 * 100,000 = +$200
   - Commission: $5 (typical)
   - Swap: $0 (intraday)
   - Net P&L: $200 - $5 = +$195
   - Pips: (1.1060 - 1.1010) * 10,000 = 50 pips
   - Duration: 15 minutes
   
   UPDATE trades SET
       close_price: 1.1060,
       close_time: NOW(),
       gross_profit_loss: 200,
       commission: 5,
       net_profit_loss: 195,
       profit_loss_pips: 50,
       trade_duration_seconds: 900,
       trade_status: 'closed'
   ```

4. **Trade Summary:**
   - Entry: 1.1010 @ 14:30
   - Exit: 1.1060 @ 14:45
   - Duration: 15 minutes
   - Result: **+50 pips, +$195 net P&L**
   - New account balance: $10,195
   - Daily P&L: +$195
   - Daily return: 1.95%

---

## Security Best Practices

### 1. Credentials & Secrets Management

**NEVER:**
```python
# WRONG: Hardcoded credentials
conn = mysql.connector.connect(
    host='localhost',
    user='forex_bot',
    password='SuperSecretPassword123',  # EXPOSED in code!
    database='forex_trading_bot'
)
```

**DO:**
```python
# RIGHT: Load from environment variables
import os
conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),  # Protected in secrets manager
    database=os.getenv('DB_NAME')
)
```

**Production Deployment:**
- AWS: Use AWS Secrets Manager
- Google Cloud: Use Google Secret Manager  
- Azure: Use Azure Key Vault
- VPS: Use HashiCorp Vault or environment variables set by orchestration

### 2. Password Hashing

**Broker Credentials:**
```python
import bcrypt

# When storing broker password
broker_password = "BrokerPass123"
hashed = bcrypt.hashpw(broker_password.encode(), bcrypt.gensalt(12))
# Store hashed value in database

# When retrieving for API connection
retrieved_hash = db.get_broker_password_hash(user_id)
if bcrypt.checkpw(broker_password.encode(), retrieved_hash):
    # Password is correct, connect to broker
```

### 3. Encryption for Sensitive Data

```python
from cryptography.fernet import Fernet

# Generate key (store in secrets manager, NOT in code)
key = Fernet.generate_key()

# Encrypt broker API key before storing
cipher_suite = Fernet(key)
api_key = "saxo_api_key_12345"
encrypted_key = cipher_suite.encrypt(api_key.encode())
# Store encrypted_key in database

# Decrypt when needed
decrypted_key = cipher_suite.decrypt(encrypted_key).decode()
# Use decrypted_key to connect to broker API
```

### 4. SQL Injection Prevention

**WRONG:**
```python
# VULNERABLE to SQL injection
query = f"SELECT * FROM users WHERE username = '{username}'"
cursor.execute(query)

# If username = "admin' OR '1'='1", would return all users!
```

**RIGHT:**
```python
# SAFE: Parameterized query
query = "SELECT * FROM users WHERE username = %s"
cursor.execute(query, (username,))

# The username value is properly escaped/parameterized
# Even if username = "admin' OR '1'='1", it's treated as literal value
```

### 5. HTTPS & SSL Encryption

**Database Connection:**
```python
# Enable SSL encryption for database connection
ssl_config = {
    'ca': '/path/to/ca.pem',
    'cert': '/path/to/client-cert.pem',
    'key': '/path/to/client-key.pem'
}

conn = mysql.connector.connect(
    host='mysql.example.com',
    user='forex_bot',
    password=os.getenv('DB_PASSWORD'),
    database='forex_trading_bot',
    ssl_disabled=False,
    ssl_ca=ssl_config['ca'],
    ssl_cert=ssl_config['cert'],
    ssl_key=ssl_config['key']
)
```

**Broker API:**
```python
# Always use HTTPS for broker API calls
import requests

# Requests library uses HTTPS by default
response = requests.post(
    'https://api.saxobank.com/openapi/trade/v2/accounts/me',
    headers={'Authorization': f'Bearer {api_key}'},
    json=order_data,
    verify=True  # Verify SSL certificate
)
```

### 6. Database User Permissions

**Create limited database user:**
```sql
-- Create user for trading bot
CREATE USER 'forex_bot_app'@'localhost' IDENTIFIED BY 'strong_password';

-- Grant only necessary permissions
GRANT SELECT, INSERT, UPDATE ON forex_trading_bot.* TO 'forex_bot_app'@'localhost';

-- NEVER grant DELETE or DROP permissions to application user
-- Only DBA should have those permissions

-- Remove all administrative privileges
REVOKE ALL PRIVILEGES ON *.* FROM 'forex_bot_app'@'localhost';

-- Apply changes
FLUSH PRIVILEGES;
```

**Why Limited Permissions:**
- If app is hacked, attacker can only INSERT/UPDATE specific tables
- Can't DROP tables or TRUNCATE data
- Can't access other databases
- Minimizes damage from security breach

### 7. Audit Logging

**Every important action logged:**
```sql
-- When trade opens
INSERT INTO system_logs (
    user_id, event_type, message, severity_level,
    module_name, affected_trade_id, system_state
) VALUES (
    1, 'TRADE_OPENED',
    'Trade 98765 opened: BUY 0.4 EURUSD @ 1.1010',
    'INFO', 'TradeExecutionEngine', 98765,
    JSON_OBJECT('entry': 1.1010, 'sl': 1.0960, 'tp': 1.1060)
);
```

**Enable for:**
- Trade execution/closure
- Account balance changes
- API errors
- Password changes
- Risk limit modifications

### 8. VPS Security Hardening

**For Linux VPS hosting the bot:**
```bash
# Firewall: Only allow specific ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 3306/tcp    # MySQL (if on same server)
sudo ufw allow 443/tcp     # HTTPS

# Fail2Ban: Block brute force attempts
sudo apt-get install fail2ban
# Blocks IP after 5 failed SSH attempts

# SSH Key Authentication: Disable password auth
PasswordAuthentication no
PubkeyAuthentication yes

# Keep system updated
sudo apt-get update && sudo apt-get upgrade -y

# Monitor running processes
ps aux | grep python  # Should only see trading bot, not suspicious processes
```

---

## Backup & Recovery Strategy

### Backup Types

**1. Full Database Backup (Daily)**
```bash
#!/bin/bash
# Full backup every night at 2 AM

BACKUP_DIR="/backups/mysql"
DATE=$(date +"%Y%m%d_%H%M%S")

mysqldump -u$DB_USER -p$DB_PASSWORD $DB_NAME \
    --single-transaction \
    --quick \
    --lock-tables=false \
    > $BACKUP_DIR/forex_trading_bot_full_$DATE.sql

# Compress to save space
gzip $BACKUP_DIR/forex_trading_bot_full_$DATE.sql

# Keep only last 30 days
find $BACKUP_DIR -name "*_full_*.sql.gz" -mtime +30 -delete
```

**Flags Explained:**
- `--single-transaction`: Read consistent snapshot without locking
- `--quick`: Stream data directly to file (doesn't buffer in memory)
- `--lock-tables=false`: No locks (important for 24/7 trading)

**2. Incremental Backups (Every 6 hours)**
```bash
#!/bin/bash
# Incremental backups using binary logs

BACKUP_DIR="/backups/mysql/incremental"
DATE=$(date +"%Y%m%d_%H%M%S")

# Enable binary logging in MySQL config:
# [mysqld]
# log_bin = /var/log/mysql/mysql-bin.log

# Flush logs to rotate binary log files
mysql -u$DB_USER -p$DB_PASSWORD -e "FLUSH LOGS"

# Copy binary log to backup dir
cp /var/log/mysql/mysql-bin.* $BACKUP_DIR/

# Cleanup old binary logs (older than 7 days)
mysql -u$DB_USER -p$DB_PASSWORD \
    -e "PURGE BINARY LOGS BEFORE DATE_SUB(NOW(), INTERVAL 7 DAY);"
```

**Benefits of Binary Logs:**
- Only new changes are logged (small files)
- Can replay transactions to any point in time
- Recovery granularity down to seconds (not hours)

**3. Cross-Region Backup (Weekly)**
```bash
#!/bin/bash
# Upload backup to cloud storage for disaster recovery

LATEST_BACKUP=$(ls -t /backups/mysql/*.sql.gz | head -1)

# Upload to AWS S3
aws s3 cp $LATEST_BACKUP \
    s3://my-forex-bot-backups/$(date +%Y/%m/%d)/ \
    --region us-east-1 \
    --storage-class GLACIER  # Cheaper long-term storage

# Or upload to Google Cloud
gsutil cp $LATEST_BACKUP \
    gs://my-forex-bot-backups/$(date +%Y/%m/%d)/
```

### Recovery Scenarios

**Scenario 1: Single Table Corruption**

```bash
# If only risk_management table is corrupted

# Option 1: Restore from backup
mysql -u$DB_USER -p$DB_PASSWORD $DB_NAME < /backups/forex_trading_bot_full_20260610.sql
# But this restores EVERYTHING to June 10 (losing June 11-12 data)

# Option 2: Restore single table (better)
# 1. Extract risk_management table from backup
mysql -u$DB_USER -p$DB_PASSWORD $DB_NAME \
    -e "DROP TABLE risk_management;"

mysql -u$DB_USER -p$DB_PASSWORD $DB_NAME \
    < /backups/risk_management_backup.sql

# Option 3: Rebuild from trades table (best)
# Recalculate daily metrics from actual trades
# Write query to insert into risk_management from trades...
```

**Scenario 2: Complete Database Loss**

```bash
# Restore from full backup
mysql -u$DB_USER -p$DB_PASSWORD < /backups/forex_trading_bot_full_20260610.sql

# Apply incremental backups to catch up to lost time
mysql -u$DB_USER -p$DB_PASSWORD --one-database $DB_NAME \
    < /backups/mysql/incremental/mysql-bin.000123

# Verify restore worked
mysql -u$DB_USER -p$DB_PASSWORD $DB_NAME \
    -e "SELECT COUNT(*) FROM trades; SELECT COUNT(*) FROM risk_management;"

# Check data consistency
mysql -u$DB_USER -p$DB_PASSWORD $DB_NAME \
    -e "SELECT * FROM trades WHERE close_time IS NULL LIMIT 5;"
```

**Scenario 3: Point-in-Time Recovery**

If you need data as of exactly June 12 at 14:30:00:

```bash
# 1. Restore full backup from June 12 morning
mysql -u$DB_USER -p$DB_PASSWORD < /backups/forex_trading_bot_full_20260612_0200.sql

# 2. Replay binary logs only up to 14:30
mysqlbinlog /var/log/mysql/mysql-bin.000125 \
    --stop-datetime="2026-06-12 14:30:00" \
    | mysql -u$DB_USER -p$DB_PASSWORD $DB_NAME

# Database now contains all data from before 14:30, nothing after
```

### Backup Verification

**Don't just backup—verify you can restore!**

```bash
#!/bin/bash
# Weekly backup verification script

# 1. Restore latest backup to test server
mysql -u$DB_USER -p$DB_PASSWORD forex_trading_bot_test < \
    /backups/forex_trading_bot_full_latest.sql

# 2. Run consistency checks
mysql -u$DB_USER -p$DB_PASSWORD forex_trading_bot_test << EOF
-- Check for orphaned records (trades without users)
SELECT COUNT(*) as orphaned_trades
FROM trades t
WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.user_id = t.user_id);

-- Check for negative balances (should never happen)
SELECT COUNT(*) as negative_balances
FROM risk_management
WHERE account_balance < 0;

-- Check for closed trades without P&L
SELECT COUNT(*) as incomplete_trades
FROM trades
WHERE trade_status = 'closed' AND net_profit_loss IS NULL;
EOF

# 3. Compare row counts with production
PROD_TRADES=$(mysql -u$DB_USER -p$DB_PASSWORD $DB_NAME \
    -se "SELECT COUNT(*) FROM trades;")
TEST_TRADES=$(mysql -u$DB_USER -p$DB_PASSWORD forex_trading_bot_test \
    -se "SELECT COUNT(*) FROM trades;")

if [ "$PROD_TRADES" -eq "$TEST_TRADES" ]; then
    echo "✓ Backup verification PASSED"
else
    echo "✗ BACKUP VERIFICATION FAILED"
    echo "  Production trades: $PROD_TRADES"
    echo "  Backup trades: $TEST_TRADES"
fi
```

### Backup Storage Strategy

| Backup Type | Frequency | Retention | Storage | Cost |
|------------|-----------|-----------|---------|------|
| Full Daily | 1x daily | 30 days | Local SSD | Medium |
| Incremental | 6-hourly | 7 days | Local SSD | Low |
| Offsite Weekly | 1x weekly | 12 months | Cloud (Glacier) | Low |
| Cross-region Monthly | 1x monthly | 5 years | Cloud (Archive) | Minimal |

**Rationale:**
- Local backups for fast recovery (SSD not tape)
- Offsite for disaster recovery (fire, theft, etc.)
- Long-term archive for regulatory compliance

---

## Scalability Recommendations

### Horizontal Scaling

**Problem:** Single bot instance can only trade a few pairs efficiently.

**Solution: Distributed bot instances**

```
┌─────────────────────────────────────────────────────┐
│           Load Balancer / Job Queue                  │
│         (Redis + Celery for task distribution)       │
└────────────┬─────────────────────┬──────────────────┘
             │                     │
    ┌────────▼────────┐   ┌───────▼────────┐
    │ Bot Instance 1  │   │ Bot Instance 2 │
    │ (4 pairs)       │   │ (4 pairs)      │
    │ M5-H1           │   │ H1-D1          │
    └─────────┬───────┘   └────────┬───────┘
              │                    │
              └────────┬───────────┘
                       │
              ┌────────▼─────────┐
              │  Shared MySQL    │
              │  Database        │
              └──────────────────┘
```

**Implementation:**
```python
# Instance 1: EUR pairs, Asian session
from config import Config
config = Config()
config.ENABLED_PAIRS = ['EURUSD', 'EURGBP', 'EURJPY', 'EURAUD']
config.STRATEGY_TIMEFRAME = 'H1'  # Hourly timeframe

# Instance 2: GBP pairs, US session
config.ENABLED_PAIRS = ['GBPUSD', 'GBPJPY', 'GBPAUD', 'GBPCHF']
config.STRATEGY_TIMEFRAME = 'H1'

# Both instances share same MySQL database
# Market data collected once, used by all instances
# Risk management centralized
```

**Benefits:**
- Each instance handles 4-5 pairs efficiently
- Parallel market data collection
- Distributed computational load
- Single point of failure (database) mitigated by replication

### Vertical Scaling

**Optimize single instance:**

```python
# Use connection pooling efficiently
DB_POOL_SIZE = 20  # More concurrent connections
DB_POOL_MAX_OVERFLOW = 10  # Allow temporary overflow

# Cache market data in memory (Redis)
import redis
cache = redis.Redis(host='localhost', port=6379, db=0)

# Cache latest 100 candles for each pair
candles = cache.get(f'market_data:EURUSD:H1')
if not candles:
    # Fetch from database if not in cache
    candles = db.get_last_100_candles('EURUSD', 'H1')
    cache.set(f'market_data:EURUSD:H1', candles, ex=3600)  # 1 hour TTL
```

**Performance Gain:**
- Memory access: 1 microsecond
- Database query: 5-10 milliseconds
- 10,000x faster for repeated queries

### Database Scaling

**Problem:** Single MySQL server becomes bottleneck at high throughput.

**Solution: Read Replicas + Sharding**

```
┌──────────────────────────────────────┐
│     Primary (Write) MySQL             │
│  - Master instance                    │
│  - Receives all writes (trades, etc.) │
│  - Processes INSERT/UPDATE/DELETE     │
└─────────┬──────────┬──────────────────┘
          │          │
    ┌─────▼──┐  ┌───▼─────┐
    │ Replica│  │ Replica │  
    │ (Read) │  │ (Read)  │
    └────────┘  └─────────┘
       ↑             ↑
    SELECT         SELECT
    Queries        Queries
```

**Configuration:**
```sql
-- On Primary (writes)
[mysqld]
server-id = 1
log_bin = /var/log/mysql/mysql-bin.log
binlog_format = ROW

-- On Replica (reads)
[mysqld]
server-id = 2
relay-log = /var/log/mysql/mysql-relay-bin
read_only = ON
```

**Python Usage:**
```python
# Write operations to primary
db_write = DatabaseManager(host='primary-mysql.local', ...)
db_write.execute_update(
    "INSERT INTO trades (...) VALUES (...)",
    (...)
)

# Read operations to replica (faster, doesn't block writes)
db_read = DatabaseManager(host='replica-mysql.local', ...)
trades = db_read.execute_query(
    "SELECT * FROM trades WHERE user_id = %s",
    (user_id,)
)
```

**Benefit:**
- Primary handles 5,000 writes/sec
- Replicas handle 50,000 reads/sec each
- Read workload doesn't interfere with write workload

---

## Performance Optimization

### Index Optimization

**Good Index (Used):**
```sql
-- Query: Get open trades for user
SELECT * FROM trades 
WHERE user_id = 1 AND trade_status = 'open';

-- Index:
INDEX idx_user_status (user_id, trade_status)

-- Why: Index is (user_id, trade_status)
-- WHERE clause matches (user_id, trade_status)
-- Performance: 1ms (index lookup)
```

**Bad Index (Not Used):**
```sql
-- Same query, but different index order
INDEX idx_status_user (trade_status, user_id)

-- Why: WHERE clause is (user_id, trade_status)
-- Index is (trade_status, user_id) - wrong order
-- MySQL might not use this index
-- Performance: 100ms+ (full table scan)

-- LESSON: Index column order matters!
-- Index order should match WHERE clause order
```

### Query Optimization Examples

**Before (SLOW - 5 seconds):**
```python
# Get all trades for user, calculate average P&L
all_trades = db.execute_query(
    "SELECT * FROM trades WHERE user_id = 1"  # Returns 1000 rows
)

avg_pnl = sum(t['net_profit_loss'] for t in all_trades) / len(all_trades)
```

**After (FAST - <1ms):**
```python
# Let database calculate average
result = db.execute_query(
    "SELECT AVG(net_profit_loss) as avg_pnl FROM trades WHERE user_id = 1",
    fetch_one=True,
    dictionary=True
)
avg_pnl = result['avg_pnl']
```

**Why Faster:**
- SLOW: Transfers 1000 rows from database to Python (network latency)
- FAST: Database calculates aggregate, returns 1 row

### Connection Pool Optimization

```python
# DON'T: Create new connection for each query
for i in range(100):
    conn = mysql.connector.connect(host, user, password)  # Slow!
    cursor = conn.cursor()
    cursor.execute(...)
    conn.close()

# DO: Use connection pool
db = DatabaseManager(host, user, password, pool_size=10)

for i in range(100):
    with db.get_connection() as conn:  # Reuse pooled connection
        cursor = conn.cursor()
        cursor.execute(...)
        # Connection returned to pool when exiting context
```

**Performance Difference:**
- Creating connection: 100ms per connection
- Using pooled connection: <1ms per operation
- 100 operations: 10 seconds (new) vs 0.1 seconds (pooled)

### Caching Strategy

```python
from functools import lru_cache
import redis

# Cache at Python level (in-process)
@lru_cache(maxsize=128)
def get_user_config(user_id: int):
    """Get user config, cache in memory."""
    return db.execute_query(
        "SELECT * FROM strategy_configurations WHERE user_id = %s",
        (user_id,),
        fetch_one=True,
        dictionary=True
    )

# Cache at Redis level (distributed)
cache = redis.Redis(host='localhost', port=6379, db=0)

def get_latest_market_data(pair: str):
    # Check Redis first
    cached = cache.get(f'market_data:{pair}')
    if cached:
        return json.loads(cached)
    
    # If not cached, query database
    data = db.execute_query(
        "SELECT * FROM market_data WHERE currency_pair = %s ORDER BY timestamp DESC LIMIT 1",
        (pair,),
        fetch_one=True,
        dictionary=True
    )
    
    # Cache for 1 minute
    cache.set(f'market_data:{pair}', json.dumps(data), ex=60)
    return data
```

---

## Summary

This design emphasizes:

1. **Reliability**: ACID transactions, audit trails, backup/recovery
2. **Performance**: Indexing, partitioning, connection pooling, caching
3. **Security**: Encryption, parameterized queries, limited permissions
4. **Scalability**: Distributed instances, read replicas, sharding
5. **Compliance**: Complete audit log, immutable core tables

The forex trading bot is now production-ready to handle real capital and real risk.
