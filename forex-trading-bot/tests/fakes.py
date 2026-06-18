from datetime import datetime
from decimal import Decimal


class FakeDatabase:
    """Small in-memory database double for offline trading smoke tests."""

    def __init__(self):
        self.logs = []
        self.trades = {}
        self.next_trade_id = 1
        self.account_metrics = {
            "account_balance": Decimal("10000"),
            "available_margin": Decimal("9000"),
            "used_margin": Decimal("0"),
            "margin_level": Decimal("999999"),
        }

    def execute_query(self, query, params=None, fetch_one=False, fetch_all=True, dictionary=False):
        normalized_query = " ".join(query.lower().split())

        if "from risk_management" in normalized_query and "account_balance" in normalized_query:
            return self.account_metrics.copy()

        if "select account_status from users" in normalized_query:
            return {"account_status": "active"}

        if "count(*) as count from trades" in normalized_query:
            user_id = params[0]
            count = sum(
                1
                for trade in self.trades.values()
                if trade["user_id"] == user_id and trade["trade_status"] == "open"
            )
            return {"count": count}

        if "select trade_id from trades" in normalized_query:
            user_id = params[0]
            matching_ids = [
                trade_id
                for trade_id, trade in self.trades.items()
                if trade["user_id"] == user_id
            ]
            return {"trade_id": max(matching_ids)} if matching_ids else None

        if "select user_id, trade_type, entry_price, lot_size, entry_time" in normalized_query:
            trade_id = params[0]
            trade = self.trades.get(trade_id)
            if not trade:
                return None
            return {
                "user_id": trade["user_id"],
                "trade_type": trade["trade_type"],
                "entry_price": trade["entry_price"],
                "lot_size": trade["lot_size"],
                "entry_time": trade["entry_time"],
            }

        return None if fetch_one else []

    def execute_update(self, query, params=None):
        normalized_query = " ".join(query.lower().split())

        if normalized_query.startswith("insert into trades"):
            trade_id = self.next_trade_id
            self.next_trade_id += 1
            (
                user_id,
                signal_id,
                currency_pair,
                trade_type,
                entry_price,
                stop_loss,
                take_profit,
                lot_size,
                contract_size,
                position_value_usd,
                risk_per_trade,
                trade_status,
            ) = params
            self.trades[trade_id] = {
                "trade_id": trade_id,
                "user_id": user_id,
                "signal_id": signal_id,
                "currency_pair": currency_pair,
                "trade_type": trade_type,
                "entry_price": Decimal(str(entry_price)),
                "entry_time": datetime.now(),
                "stop_loss": Decimal(str(stop_loss)),
                "take_profit": Decimal(str(take_profit)),
                "lot_size": Decimal(str(lot_size)),
                "contract_size": contract_size,
                "position_value_usd": Decimal(str(position_value_usd)),
                "risk_per_trade": Decimal(str(risk_per_trade)),
                "trade_status": trade_status,
            }
            return 1

        if normalized_query.startswith("update trades set"):
            trade_id = params[-1]
            trade = self.trades[trade_id]
            trade.update(
                {
                    "close_price": Decimal(str(params[0])),
                    "close_time": datetime.now(),
                    "close_reason": params[1],
                    "gross_profit_loss": Decimal(str(params[2])),
                    "commission": Decimal(str(params[3])),
                    "swap_points": Decimal(str(params[4])),
                    "net_profit_loss": Decimal(str(params[5])),
                    "profit_loss_pips": Decimal(str(params[6])),
                    "trade_duration_seconds": params[7],
                    "trade_duration_label": params[8],
                    "trade_status": params[9],
                }
            )
            return 1

        return 0

    def call_procedure(self, procedure_name, args=None, fetch_all=True):
        return None

    def log_event(
        self,
        user_id,
        event_type,
        message,
        severity="INFO",
        module_name=None,
        error_code=None,
        affected_trade_id=None,
        affected_signal_id=None,
        system_state=None,
    ):
        self.logs.append(
            {
                "user_id": user_id,
                "event_type": event_type,
                "message": message,
                "severity": severity,
                "module_name": module_name,
                "error_code": error_code,
                "affected_trade_id": affected_trade_id,
                "affected_signal_id": affected_signal_id,
                "system_state": system_state,
            }
        )
        return len(self.logs)
