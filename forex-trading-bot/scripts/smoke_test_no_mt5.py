"""
Offline smoke test for the trading engine.

This uses the built-in MockBroker and an in-memory fake database, so it does not
need MetaTrader, OANDA credentials, or a MySQL server.
"""

import logging
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import TestingConfig
from src.trading.broker import BrokerFactory
from src.trading.trade_execution import CloseReason, TradeExecutionEngine, TradeType
from tests.fakes import FakeDatabase


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger = logging.getLogger("no-mt5-smoke")

    config = TestingConfig()
    broker = BrokerFactory.create(config, logger)
    db = FakeDatabase()
    engine = TradeExecutionEngine(db, broker)

    broker_ok = broker.verify_connection()
    lot_size = engine.calculate_position_size(
        user_id=1,
        account_balance=Decimal("10000"),
        entry_price=Decimal("1.1010"),
        stop_loss=Decimal("1.0960"),
        risk_percent=Decimal("2.0"),
        max_position_size=Decimal("1.0"),
    )

    opened, trade_id, open_error = engine.open_trade(
        user_id=1,
        currency_pair="EURUSD",
        trade_type=TradeType.BUY,
        entry_price=Decimal("1.1010"),
        stop_loss=Decimal("1.0960"),
        take_profit=Decimal("1.1110"),
        lot_size=lot_size,
        source="offline_smoke_test",
    )

    if not opened:
        print(f"FAILED: trade did not open: {open_error}")
        return 1

    closed, metrics, close_error = engine.close_trade(
        trade_id=trade_id,
        close_price=Decimal("1.1110"),
        close_reason=CloseReason.TP_HIT,
        commission=Decimal("0"),
        swap=Decimal("0"),
    )

    if not closed:
        print(f"FAILED: trade did not close: {close_error}")
        return 1

    print("NO-MT5 SMOKE TEST PASSED")
    print(f"Broker mode: {'mock' if broker.mock else 'real'}")
    print(f"Broker verification: {broker_ok}")
    print(f"Calculated lot size: {lot_size}")
    print(f"Trade ID: {trade_id}")
    print(f"Closed P&L: ${metrics['net_pnl']:.2f}")
    print(f"Closed pips: {metrics['pips']:.1f}")
    print(f"Events logged: {len(db.logs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
