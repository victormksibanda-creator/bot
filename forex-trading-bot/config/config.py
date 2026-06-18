"""
Configuration Management
================================================
Centralized configuration for the trading bot.
Uses environment variables for sensitive data (security best practice).
"""

import os
from pathlib import Path
from typing import Optional
import json

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


class Config:
    """
    Configuration class for trading bot.
    
    Design Principles:
    1. Environment-based: Production vs Development configs differ
    2. Secure: Sensitive data in environment variables, never in code
    3. Overridable: Can be configured via env vars or config files
    4. Validated: Type checking and required field validation
    
    Security Practice:
    - Database passwords: USE ENVIRONMENT VARIABLES
    - API keys: USE ENVIRONMENT VARIABLES or Secrets Manager
    - Never commit credentials to version control
    - Use IAM roles in cloud deployments
    """
    
    # ========== Environment Settings ==========
    ENVIRONMENT = os.getenv('TRADING_BOT_ENV', 'development')
    DEBUG = ENVIRONMENT == 'development'
    
    # ========== Database Configuration ==========
    # Get from environment variables (REQUIRED for security)
    DB_HOST = os.getenv('DB_HOST') or os.getenv('MYSQLHOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT') or os.getenv('MYSQLPORT', '3306'))
    DB_USER = os.getenv('DB_USER') or os.getenv('MYSQLUSER', 'forex_bot_user')
    DB_PASSWORD = os.getenv('DB_PASSWORD') or os.getenv('MYSQLPASSWORD', '')  # MUST be set in production
    DB_NAME = os.getenv('DB_NAME') or os.getenv('MYSQLDATABASE', 'forex_trading_bot')
    
    # Connection pool settings
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '10'))
    DB_POOL_MAX_OVERFLOW = int(os.getenv('DB_POOL_MAX_OVERFLOW', '20'))
    DB_CONNECTION_TIMEOUT = int(os.getenv('DB_CONNECTION_TIMEOUT', '10'))
    
    # Validate database configuration
    @classmethod
    def validate_db_config(cls):
        """Validate database configuration."""
        if cls.ENVIRONMENT == 'production' and not cls.DB_PASSWORD:
            raise ValueError("DB_PASSWORD must be set for production environment")
        return True
    
    # ========== Broker Configuration ==========
    # Broker connection settings
    BROKER_NAME = os.getenv('BROKER_NAME', 'Saxo')  # e.g., Saxo, IG, Oanda
    BROKER_ACCOUNT_NUMBER = os.getenv('BROKER_ACCOUNT_NUMBER', '')
    BROKER_ACCOUNT_ID = os.getenv('BROKER_ACCOUNT_ID', '')  # OANDA account ID
    BROKER_ACCOUNT_PASSWORD = os.getenv('BROKER_ACCOUNT_PASSWORD', '')  # ENCRYPTED
    BROKER_SERVER = os.getenv('BROKER_SERVER', '')  # e.g., for MT5 connection
    BROKER_API_KEY = os.getenv('BROKER_API_KEY', '')  # For REST API access

    # ========== Trading Configuration ==========
    # Risk Management Settings
    DEFAULT_RISK_PER_TRADE_PERCENT = float(os.getenv('RISK_PER_TRADE', '2.0'))  # 2% per trade
    DEFAULT_DAILY_LOSS_LIMIT_PERCENT = float(os.getenv('DAILY_LOSS_LIMIT', '5.0'))  # 5% per day
    DEFAULT_WEEKLY_LOSS_LIMIT_PERCENT = float(os.getenv('WEEKLY_LOSS_LIMIT', '10.0'))  # 10% per week
    DEFAULT_MAX_DRAWDOWN_PERCENT = float(os.getenv('MAX_DRAWDOWN', '20.0'))  # 20% max drawdown
    DEFAULT_MAX_MARGIN_LEVEL = float(os.getenv('MAX_MARGIN_LEVEL', '50.0'))  # 50% max usage
    DEFAULT_MAX_CONCURRENT_TRADES = int(os.getenv('MAX_CONCURRENT_TRADES', '5'))
    
    # Trading hours (UTC)
    TRADING_HOURS_START = os.getenv('TRADING_HOURS_START', '00:00')  # 24-hour format UTC
    TRADING_HOURS_END = os.getenv('TRADING_HOURS_END', '23:59')
    
    # Currency pairs to trade
    ENABLED_PAIRS = os.getenv(
        'ENABLED_PAIRS',
        'EURUSD,GBPUSD,USDJPY,AUDUSD'
    ).split(',')
    
    # ========== Strategy Configuration ==========
    # Strategy Parameters (can be overridden per strategy)
    STRATEGY_TYPE = os.getenv('STRATEGY_TYPE', 'trend_following')
    STRATEGY_TIMEFRAME = os.getenv('STRATEGY_TIMEFRAME', 'H1')  # H1, D1, M15, etc.
    
    # Technical Indicator Settings
    RSI_PERIOD = int(os.getenv('RSI_PERIOD', '14'))
    RSI_OVERBOUGHT = int(os.getenv('RSI_OVERBOUGHT', '70'))
    RSI_OVERSOLD = int(os.getenv('RSI_OVERSOLD', '30'))
    
    MA_FAST_PERIOD = int(os.getenv('MA_FAST_PERIOD', '20'))
    MA_SLOW_PERIOD = int(os.getenv('MA_SLOW_PERIOD', '50'))
    
    # ========== Logging Configuration ==========
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_DIR = Path(os.getenv('LOG_DIR', './logs'))
    LOG_MAX_SIZE = int(os.getenv('LOG_MAX_SIZE', '10485760'))  # 10MB
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # Create log directory if it doesn't exist
    LOG_DIR.mkdir(exist_ok=True)
    
    # ========== API & Service Configuration ==========
    # If using REST APIs instead of MT4/MT5
    REST_API_BASE_URL = os.getenv('REST_API_BASE_URL', '')
    REST_API_TIMEOUT = int(os.getenv('REST_API_TIMEOUT', '30'))  # seconds
    
    # ========== Notification Configuration ==========
    # Email alerts for critical events
    SMTP_SERVER = os.getenv('SMTP_SERVER', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')  # Use env var
    ALERT_EMAIL = os.getenv('ALERT_EMAIL', '')
    
    # ========== Monitoring & Observability ==========
    # Enable metrics collection and monitoring
    ENABLE_METRICS = os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))
    
    # ========== Development & Testing ==========
    MOCK_BROKER = os.getenv('MOCK_BROKER', 'false').lower() == 'true'  # For testing
    BACKTESTING_MODE = os.getenv('BACKTESTING_MODE', 'false').lower() == 'true'
    
    @classmethod
    def to_dict(cls) -> dict:
        """Convert config to dictionary (safe: excludes passwords)."""
        return {
            'environment': cls.ENVIRONMENT,
            'debug': cls.DEBUG,
            'database': {
                'host': cls.DB_HOST,
                'port': cls.DB_PORT,
                'name': cls.DB_NAME,
            },
            'trading': {
                'risk_per_trade': cls.DEFAULT_RISK_PER_TRADE_PERCENT,
                'daily_loss_limit': cls.DEFAULT_DAILY_LOSS_LIMIT_PERCENT,
                'max_drawdown': cls.DEFAULT_MAX_DRAWDOWN_PERCENT,
                'max_concurrent_trades': cls.DEFAULT_MAX_CONCURRENT_TRADES,
                'enabled_pairs': cls.ENABLED_PAIRS,
            },
            'strategy': {
                'type': cls.STRATEGY_TYPE,
                'timeframe': cls.STRATEGY_TIMEFRAME,
            }
        }
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate all configuration.
        Raises ValueError if any required settings are missing.
        """
        cls.validate_db_config()
        
        if cls.ENVIRONMENT == 'production':
            assert cls.DB_PASSWORD, "DB_PASSWORD required for production"
            assert cls.BROKER_ACCOUNT_PASSWORD, "BROKER credentials required for production"
        
        return True


# ============================================================================
# Configuration by Environment
# ============================================================================

class DevelopmentConfig(Config):
    """Development environment settings."""
    DEBUG = True
    DB_HOST = 'localhost'
    DB_NAME = 'forex_trading_bot_dev'


class ProductionConfig(Config):
    """Production environment settings."""
    DEBUG = False
    # All settings from environment variables
    # No hardcoded values
    

class TestingConfig(Config):
    """Testing environment settings."""
    DEBUG = True
    DB_HOST = 'localhost'
    DB_NAME = 'forex_trading_bot_test'
    MOCK_BROKER = True


# ============================================================================
# Get appropriate config based on environment
# ============================================================================

def get_config() -> Config:
    """Get config for current environment."""
    config_class = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig,
    }.get(Config.ENVIRONMENT, Config)
    
    return config_class()


# Example usage:
# from config import get_config
# config = get_config()
# print(config.DB_HOST)  # Access configuration
