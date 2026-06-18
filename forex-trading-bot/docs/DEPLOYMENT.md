# Deployment Guide - Forex Trading Bot

## Quick Start

### Prerequisites

- Linux VPS (Ubuntu 20.04+) or Windows Server
- Python 3.9+
- MySQL 8.0+
- MetaTrader 5/4 (for broker integration)
- 2GB+ RAM
- Stable internet connection

### Step 1: Setup VPS

#### On Ubuntu 20.04 LTS:

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python
sudo apt-get install python3.10 python3-pip python3-venv -y

# Install MySQL
sudo apt-get install mysql-server -y

# Install git
sudo apt-get install git -y

# Install supervisor (for process management)
sudo apt-get install supervisor -y
```

### Step 2: Clone & Setup Project

```bash
# Clone repository (or upload files to VPS)
cd ~
git clone https://github.com/yourusername/forex-trading-bot.git
cd forex-trading-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your configuration
nano .env  # Fill in DB credentials, broker account, etc.
```

### Step 3: Setup MySQL Database

```bash
# Connect to MySQL
mysql -u root -p

# Create database user
CREATE USER 'forex_bot_user'@'localhost' IDENTIFIED BY 'strong_password';
GRANT ALL PRIVILEGES ON forex_trading_bot.* TO 'forex_bot_user'@'localhost';
FLUSH PRIVILEGES;

# Exit MySQL
exit

# Create schema (run SQL script)
mysql -u forex_bot_user -p forex_trading_bot < scripts/001_create_database_schema.sql
```

### Step 4: Test Database Connection

```python
# Create test_connection.py
from src.database.db_connection import DatabaseManager
from config.config import get_config

config = get_config()

try:
    db = DatabaseManager(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME
    )
    
    if db.health_check():
        print("✓ Database connection successful!")
    else:
        print("✗ Database connection failed!")
        
except Exception as e:
    print(f"✗ Error: {e}")
```

### Step 5: Run Trading Bot

```bash
# Activate virtual environment
source venv/bin/activate

# Run main bot
python main.py

# Or run specific module
python -m src.trading.trade_execution
```

---

## Production Deployment (Supervisor)

### Setup Supervisor Configuration

```bash
# Create supervisor configuration
sudo nano /etc/supervisor/conf.d/forex-trading-bot.conf
```

**Configuration:**
```ini
[program:forex-trading-bot]
; Directory where the program runs
directory=/home/trader/forex-trading-bot
; Command to run
command=/home/trader/forex-trading-bot/venv/bin/python main.py
; User to run as
user=trader
; Auto-restart on crash
autorestart=true
; Restart after 10 seconds if crashed
startsecs=10
; Number of retry attempts
autostart=true
; Log files
stdout_logfile=/home/trader/forex-trading-bot/logs/supervisor_out.log
stderr_logfile=/home/trader/forex-trading-bot/logs/supervisor_err.log
; Environment variables
environment=TRADING_BOT_ENV=production,DB_HOST=localhost,DB_USER=forex_bot_user,DB_PASSWORD=your_password
```

### Start Service

```bash
# Reload supervisor
sudo supervisorctl reread
sudo supervisorctl update

# Start bot
sudo supervisorctl start forex-trading-bot

# Check status
sudo supervisorctl status forex-trading-bot

# View logs
tail -f /home/trader/forex-trading-bot/logs/supervisor_out.log
```

---

## Production Checklist

### Database Security
- [ ] Changed MySQL root password
- [ ] Created limited-permission user for bot
- [ ] Enabled SSL for database connection
- [ ] Set up automated backups (daily)
- [ ] Tested backup restoration
- [ ] Verified incremental binary log backups
- [ ] Stored backup encryption key securely

### Application Security  
- [ ] All credentials in environment variables (.env not committed)
- [ ] SQL injection prevention (parameterized queries)
- [ ] Passwords hashed with bcrypt
- [ ] API keys encrypted with Fernet
- [ ] HTTPS enabled for all external API calls
- [ ] Rate limiting on broker API calls (if applicable)

### Monitoring & Logging
- [ ] Structured logging enabled (JSON format)
- [ ] Log rotation configured (10MB per file, keep 5)
- [ ] Critical events alert via email/SMS
- [ ] Health checks automated (database, broker connection)
- [ ] Performance metrics collected (query times, trade execution times)
- [ ] Audit log of all trades and account changes

### Risk Management
- [ ] Daily loss limits configured
- [ ] Maximum drawdown limits set
- [ ] Margin level monitoring enabled
- [ ] Position size limits enforced
- [ ] Trading hours restrictions set
- [ ] Demo account testing completed (at least 100 trades)

### Operational
- [ ] VPS firewall configured (only required ports open)
- [ ] SSH key authentication enabled (password auth disabled)
- [ ] Fail2Ban installed and running
- [ ] System updates automated
- [ ] Disk space monitoring (free space alerts)
- [ ] Uptime monitoring configured
- [ ] Incident response plan documented

---

## Monitoring & Maintenance

### Health Checks

```bash
# Create health check script
cat > ~/health_check.sh << 'EOF'
#!/bin/bash

# Check if bot is running
ps aux | grep "python main.py" | grep -v grep > /dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: Trading bot not running"
    systemctl restart forex-trading-bot
    exit 1
fi

# Check database connection
mysql -u forex_bot_user -p$DB_PASSWORD -e "SELECT 1" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "ERROR: Database connection failed"
    exit 1
fi

# Check disk space
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 90 ]; then
    echo "WARNING: Disk usage at $DISK_USAGE%"
fi

# Check log file size (should rotate, not grow indefinitely)
LOG_SIZE=$(du -sh ~/logs/trading_bot.log | cut -f1)
echo "Log file size: $LOG_SIZE"

echo "OK: All health checks passed"
EOF

chmod +x ~/health_check.sh

# Run health check every hour
(crontab -l 2>/dev/null; echo "0 * * * * /home/trader/health_check.sh") | crontab -
```

### Backup Verification

```bash
# Backup script (run daily via cron)
cat > ~/backup_database.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/backups/forex_trading_bot"
DATE=$(date +"%Y%m%d_%H%M%S")

mkdir -p $BACKUP_DIR

# Full backup
mysqldump -u forex_bot_user -p$DB_PASSWORD \
    --single-transaction \
    --quick \
    --lock-tables=false \
    forex_trading_bot > $BACKUP_DIR/forex_trading_bot_$DATE.sql

# Compress
gzip $BACKUP_DIR/forex_trading_bot_$DATE.sql

# Verify backup
if [ -f "$BACKUP_DIR/forex_trading_bot_$DATE.sql.gz" ]; then
    echo "Backup completed successfully"
    
    # Upload to S3 (optional)
    aws s3 cp $BACKUP_DIR/forex_trading_bot_$DATE.sql.gz \
        s3://my-backups/forex-trading-bot/ \
        --region us-east-1
else
    echo "Backup failed!"
    exit 1
fi

# Keep only 30 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
EOF

chmod +x ~/backup_database.sh

# Schedule for 2 AM daily
(crontab -l 2>/dev/null; echo "0 2 * * * /home/trader/backup_database.sh") | crontab -
```

---

## Scaling Strategy

### Phase 1: Single Instance (Starting)
- 1 bot instance
- 4-5 currency pairs
- M5-H1 timeframes
- Can handle: 100-500 trades per day

### Phase 2: Multiple Instances (Growing)
- 2-3 bot instances
- 15-20 currency pairs
- Different timeframes per instance
- Read replicas for database
- Can handle: 1000-5000 trades per day

### Phase 3: Distributed System (Advanced)
- 5-10 bot instances across multiple VPS
- 50+ currency pairs
- Specialized instances (scalping, swing trading)
- Database sharding by user
- Can handle: 10,000+ trades per day

---

## Troubleshooting

### Bot Crashes

**Symptom:** "Process exited unexpectedly"

**Solution:**
```bash
# Check logs
tail -100 ~/logs/trading_bot.log | grep ERROR

# Common causes:
# 1. Database connection lost
#    → Check MySQL is running: systemctl status mysql
# 2. MetaTrader5 connection lost
#    → Restart MetaTrader5 terminal
# 3. Out of memory
#    → Check available RAM: free -h
#    → Reduce bot instances if needed
# 4. API rate limit
#    → Add delays between requests
```

### Slow Queries

**Symptom:** "Market data collection slow, missing candles"

**Solution:**
```bash
# Check slow query log
mysql -u root -p -e "SET GLOBAL slow_query_log = 'ON'; SET GLOBAL long_query_time = 2;"

tail -f /var/log/mysql/slow.log

# Common causes:
# 1. Missing index
#    → Add index for frequently queried columns
# 2. Lock contention
#    → Multiple threads accessing same rows
#    → Increase connection pool size
# 3. Large table scan
#    → Add WHERE clause with indexed column
```

### Database Size Growing Too Fast

**Symptom:** Disk space filling up

**Solution:**
```bash
# Check table sizes
mysql -u root -p -e "
SELECT 
    table_name,
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
FROM information_schema.tables
WHERE table_schema = 'forex_trading_bot'
ORDER BY data_length DESC;
"

# Archive old data
# Option 1: Delete old records (be careful!)
DELETE FROM market_data WHERE timestamp < DATE_SUB(NOW(), INTERVAL 2 YEAR);

# Option 2: Move to archive table
CREATE TABLE market_data_2024 LIKE market_data;
INSERT INTO market_data_2024 SELECT * FROM market_data WHERE YEAR(timestamp) = 2024;
DELETE FROM market_data WHERE YEAR(timestamp) = 2024;

# Optimize table
OPTIMIZE TABLE market_data;

# Check partitions
SHOW PARTITIONS FROM market_data;
```

---

## Cost Optimization

### VPS Selection

| Provider | Instance | Specs | Price/mo |
|----------|----------|-------|----------|
| Linode | Nanode | 1 vCPU, 1GB RAM | $5 |
| DigitalOcean | Basic | 1 vCPU, 1GB RAM | $4 |
| AWS | t3.micro | 1 vCPU, 1GB RAM | $8 |
| Vultr | Cloud Compute | 1 vCPU, 512MB RAM | $2.50 |

**Recommendation:**
- Start with 1-2GB RAM instance ($5-10/month)
- Add second instance when trading 10+ pairs ($15-20/month total)
- Growth to 3-5 instances at $50-100/month

### Database Optimization

```sql
-- Archive old data regularly
DELETE FROM market_data WHERE timestamp < DATE_SUB(NOW(), INTERVAL 3 YEAR);
DELETE FROM system_logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 1 YEAR);

-- Compress backups
gzip /backups/*.sql
# Reduces 500MB dump to 50MB

-- Use archive storage for backups > 1 year old
aws s3 cp s3://forex-backups/ s3://forex-backups-archive/ \
    --storage-class GLACIER
```

---

## Maintenance Windows

**Weekly Maintenance (30 minutes):**
- Backup verification
- Log rotation check
- Database index optimization

**Monthly Maintenance (2 hours):**
- System updates (`apt-get upgrade`)
- Database optimization (`OPTIMIZE TABLE`)
- Backup to archive storage
- Performance review

**Quarterly Maintenance (4 hours):**
- Security audit
- Disaster recovery test (restore from backup)
- Strategy performance review
- Infrastructure upgrade planning

---

## Post-Deployment

### 1. Verify All Systems

```bash
# Test trading signals
python -m tests.test_signal_generation

# Test trade execution
python -m tests.test_trade_execution

# Test risk management
python -m tests.test_risk_management

# Run full test suite
python -m pytest tests/ -v
```

### 2. Monitor First Week

- Watch for database connection issues
- Monitor for execution delays
- Check P&L calculations accuracy
- Verify position sizing logic
- Test margin level monitoring

### 3. Gradual Rollout

- Day 1-3: Demo account only
- Day 4-7: Live account with micro lots (0.01 standard lot)
- Day 8-14: Increase to mini lots (0.1 standard lot)
- Day 15+: Full position sizes

---

This deployment guide covers production-ready setup. Always test thoroughly before trading real capital!
