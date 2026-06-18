import logging
from decimal import Decimal
from typing import Any, Dict

from config.config import Config


class BrokerInterface:
    mock = False

    def verify_connection(self) -> bool:
        raise NotImplementedError()

    def place_market_order(
        self,
        currency_pair: str,
        trade_type: str,
        lot_size: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
    ) -> Dict[str, Any]:
        raise NotImplementedError()


class MockBroker(BrokerInterface):
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.mock = True

    def verify_connection(self) -> bool:
        self.logger.info("Mock broker enabled; skipping real broker verification.")
        return True

    def place_market_order(
        self,
        currency_pair: str,
        trade_type: str,
        lot_size: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
    ) -> Dict[str, Any]:
        self.logger.info(
            f"Mock order placed: {trade_type} {lot_size} {currency_pair} "
            f"SL={stop_loss} TP={take_profit}"
        )
        return {
            "success": True,
            "order_id": "MOCK_ORDER_1",
            "message": "Mock order submitted successfully.",
        }


class OandaBroker(BrokerInterface):
    def __init__(self, config: Config, logger: logging.Logger):
        try:
            import requests
        except ImportError as exc:
            raise ImportError(
                "OANDA broker mode requires the 'requests' package. "
                "Use MOCK_BROKER=true for offline tests."
            ) from exc

        self.config = config
        self.logger = logger
        self.mock = False
        self.account_id = config.BROKER_ACCOUNT_NUMBER or config.BROKER_ACCOUNT_ID
        self.requests = requests

        if not self.account_id:
            raise ValueError("OANDA configuration requires BROKER_ACCOUNT_NUMBER or BROKER_ACCOUNT_ID")
        if not config.BROKER_API_KEY:
            raise ValueError("OANDA configuration requires BROKER_API_KEY")
        if not config.REST_API_BASE_URL:
            raise ValueError("OANDA configuration requires REST_API_BASE_URL")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.BROKER_API_KEY}",
                "Content-Type": "application/json",
            }
        )
        self.timeout = config.REST_API_TIMEOUT

    def _normalize_instrument(self, currency_pair: str) -> str:
        if "_" in currency_pair:
            return currency_pair
        return f"{currency_pair[:3]}_{currency_pair[3:]}"

    def verify_connection(self) -> bool:
        url = f"{self.config.REST_API_BASE_URL.rstrip('/')}/accounts/{self.account_id}/summary"
        self.logger.info(f"Verifying OANDA account {self.account_id} via {url}")

        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code != 200:
                self.logger.error(
                    f"OANDA verification failed: {response.status_code} {response.text}"
                )
                return False

            data = response.json()
            if "account" in data:
                self.logger.info(
                    f"OANDA account verified: {data['account'].get('alias', self.account_id)}"
                )
                return True

            self.logger.error("OANDA response did not contain account summary")
            return False

        except self.requests.RequestException as exc:
            self.logger.error(f"OANDA verification error: {exc}")
            return False

    def place_market_order(
        self,
        currency_pair: str,
        trade_type: str,
        lot_size: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
    ) -> Dict[str, Any]:
        instrument = self._normalize_instrument(currency_pair)
        units = int(lot_size * Decimal("100000"))
        if trade_type.lower() == "sell":
            units = -units

        order_payload = {
            "order": {
                "instrument": instrument,
                "units": str(units),
                "type": "MARKET",
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {"price": str(stop_loss)},
                "takeProfitOnFill": {"price": str(take_profit)},
            }
        }

        url = f"{self.config.REST_API_BASE_URL.rstrip('/')}/accounts/{self.account_id}/orders"
        self.logger.info(f"Sending OANDA market order to {url}")

        try:
            response = self.session.post(url, json=order_payload, timeout=self.timeout)
            payload = response.json()
            if response.status_code not in (200, 201):
                self.logger.error(
                    f"OANDA order failed: {response.status_code} {response.text}"
                )
                return {
                    "success": False,
                    "error": payload.get("errorMessage", response.text),
                    "response": payload,
                }

            order_id = payload.get("orderCreateTransaction", {}).get("id")
            self.logger.info(f"OANDA order submitted successfully: {order_id}")
            return {
                "success": True,
                "order_id": order_id,
                "response": payload,
            }

        except self.requests.RequestException as exc:
            self.logger.error(f"OANDA order submission exception: {exc}")
            return {
                "success": False,
                "error": str(exc),
            }


class BrokerFactory:
    @staticmethod
    def create(config: Config, logger: logging.Logger) -> BrokerInterface:
        if config.MOCK_BROKER:
            return MockBroker(config, logger)

        if config.BROKER_NAME.lower() == "oanda":
            return OandaBroker(config, logger)

        logger.warning(
            f"Broker '{config.BROKER_NAME}' is not supported; using mock broker instead."
        )
        return MockBroker(config, logger)
