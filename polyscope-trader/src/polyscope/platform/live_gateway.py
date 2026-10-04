"""Live execution gateway — disabled by default, fail-closed."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


class LiveTradingForbidden(Exception):
    pass


@dataclass
class PlaceOrderResult:
    order_id: str | None
    status: str
    error: str | None = None


@dataclass
class CancelOrdersResult:
    canceled: list[str]
    not_canceled: dict[str, str]


class LiveGateway(ABC):
    @abstractmethod
    async def place_limit_order(
        self, token_id: str, side: str, price: Decimal, size: Decimal
    ) -> PlaceOrderResult:
        raise NotImplementedError

    @abstractmethod
    async def cancel_orders(self, order_ids: list[str]) -> CancelOrdersResult:
        raise NotImplementedError

    @abstractmethod
    async def send_order_heartbeat(self, heartbeat_id: str = "") -> str:
        raise NotImplementedError

    @abstractmethod
    async def reconcile_open_orders(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class DisabledLiveGateway(LiveGateway):
    def _raise(self) -> None:
        raise LiveTradingForbidden("Live trading is disabled")

    async def place_limit_order(
        self, token_id: str, side: str, price: Decimal, size: Decimal
    ) -> PlaceOrderResult:
        self._raise()
        return PlaceOrderResult(order_id=None, status="forbidden")

    async def cancel_orders(self, order_ids: list[str]) -> CancelOrdersResult:
        self._raise()
        return CancelOrdersResult(canceled=[], not_canceled={})

    async def send_order_heartbeat(self, heartbeat_id: str = "") -> str:
        self._raise()
        return ""

    async def reconcile_open_orders(self) -> list[dict[str, Any]]:
        self._raise()
        return []


class SecureLiveGateway(LiveGateway):
    """Wraps AsyncSecureClient when LIVE is armed and checks pass."""

    def __init__(self, secure_client: Any) -> None:
        self._client = secure_client
        self._last_heartbeat_id = ""

    async def place_limit_order(
        self, token_id: str, side: str, price: Decimal, size: Decimal
    ) -> PlaceOrderResult:
        from polymarket import OrderSide

        order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
        response = await self._client.place_limit_order(
            token_id=token_id,
            side=order_side,
            price=str(price),
            size=str(size),
        )
        order_id = getattr(response, "order_id", None) or getattr(response, "id", None)
        return PlaceOrderResult(order_id=str(order_id) if order_id else None, status="submitted")

    async def cancel_orders(self, order_ids: list[str]) -> CancelOrdersResult:
        result = await self._client.cancel_orders(order_ids=order_ids)
        canceled = list(getattr(result, "canceled", []) or [])
        not_canceled = dict(getattr(result, "not_canceled", {}) or {})
        return CancelOrdersResult(canceled=canceled, not_canceled=not_canceled)

    async def send_order_heartbeat(self, heartbeat_id: str = "") -> str:
        if hasattr(self._client, "send_heartbeat"):
            resp = await self._client.send_heartbeat(heartbeat_id=heartbeat_id)
            self._last_heartbeat_id = getattr(resp, "heartbeat_id", heartbeat_id)
            return self._last_heartbeat_id
        raise LiveTradingForbidden("SDK heartbeat not available — LIVE blocked")

    async def reconcile_open_orders(self) -> list[dict[str, Any]]:
        pages = self._client.list_open_orders()
        page = await pages.first_page()
        return [o.model_dump() if hasattr(o, "model_dump") else dict(o) for o in page.items]


async def create_live_gateway(
    enabled: bool, private_key: str | None
) -> LiveGateway:
    if not private_key:
        return DisabledLiveGateway()
    try:
        from polymarket import AsyncSecureClient

        client = await AsyncSecureClient.create(private_key=private_key)
        if not enabled:
            return DisabledLiveGateway()
        return SecureLiveGateway(client)
    except Exception:
        return DisabledLiveGateway()


def build_live_gateway(
    enabled: bool, private_key: str | None
) -> LiveGateway:
    return DisabledLiveGateway()
