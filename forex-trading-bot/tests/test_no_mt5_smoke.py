import logging
from decimal import Decimal
import unittest

from config.config import TestingConfig
from src.trading.broker import BrokerFactory
from src.trading.trade_execution import CloseReason, TradeExecutionEngine, TradeType
from tests.fakes import FakeDatabase


class NoMT5SmokeTest(unittest.TestCase):
    def test_trading_engine_smoke_test_runs_without_mt5_or_mysql(self):
        logger = logging.getLogger("test-no-mt5")
        broker = BrokerFactory.create(TestingConfig(), logger)
        db = FakeDatabase()
        engine = TradeExecutionEngine(db, broker)

        self.assertTrue(broker.mock)
        self.assertTrue(broker.verify_connection())

        lot_size = engine.calculate_position_size(
            user_id=1,
            account_balance=Decimal("10000"),
            entry_price=Decimal("1.1010"),
            stop_loss=Decimal("1.0960"),
            risk_percent=Decimal("2.0"),
            max_position_size=Decimal("1.0"),
        )

        self.assertEqual(lot_size, Decimal("0.40"))

        opened, trade_id, open_error = engine.open_trade(
            user_id=1,
            currency_pair="EURUSD",
            trade_type=TradeType.BUY,
            entry_price=Decimal("1.1010"),
            stop_loss=Decimal("1.0960"),
            take_profit=Decimal("1.1110"),
            lot_size=lot_size,
            source="unittest",
        )

        self.assertTrue(opened)
        self.assertEqual(trade_id, 1)
        self.assertIsNone(open_error)
        self.assertEqual(db.trades[trade_id]["trade_status"], "open")

        closed, metrics, close_error = engine.close_trade(
            trade_id=trade_id,
            close_price=Decimal("1.1110"),
            close_reason=CloseReason.TP_HIT,
        )

        self.assertTrue(closed)
        self.assertIsNone(close_error)
        self.assertEqual(metrics["net_pnl"], 400.0)
        self.assertEqual(metrics["pips"], 100.0)
        self.assertEqual(db.trades[trade_id]["trade_status"], "closed")
        self.assertEqual(
            [event["event_type"] for event in db.logs],
            ["TRADE_OPENED", "TRADE_CLOSED"],
        )


if __name__ == "__main__":
    unittest.main()
