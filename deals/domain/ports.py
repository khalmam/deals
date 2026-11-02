"""What the services need from a payment provider. PayPal implements these in paypal/."""
from dataclasses import dataclass
from typing import Protocol

from .money import Money


@dataclass(frozen=True)
class HoldRequest:
    order_id: str
    approve_url: str


@dataclass(frozen=True)
class Authorization:
    auth_id: str
    expires_at: str
    amount: Money
    custom_id: str | None = None


@dataclass(frozen=True)
class Capture:
    capture_id: str
    status: str
    amount: Money


@dataclass(frozen=True)
class PayoutItem:
    receiver_email: str
    amount: Money
    item_key: str
    note: str = ""


@dataclass(frozen=True)
class PayoutResult:
    batch_id: str
    status: str
    items: tuple = ()  # ((payout_item_id, transaction_status, sender_item_id), ...)


@dataclass(frozen=True)
class InvoiceRef:
    invoice_id: str
    payer_url: str


@dataclass(frozen=True)
class WebhookEvent:
    event_id: str
    event_type: str
    resource_id: str
    resource: dict


class PaymentsPort(Protocol):
    def create_hold(self, deal_ref, amount, terms_hash, return_url, cancel_url) -> HoldRequest: ...
    def authorize(self, deal_ref, order_id) -> Authorization: ...
    def get_authorization(self, auth_id) -> Authorization: ...
    def capture(self, deal_ref, auth_id, amount, final, step) -> Capture: ...
    def void(self, deal_ref, auth_id) -> None: ...
    def refund(self, deal_ref, capture_id, amount, step) -> str: ...
    def send_payout(self, batch_key, items) -> PayoutResult: ...
    def get_payout(self, batch_id) -> PayoutResult: ...


class InvoicePort(Protocol):
    def create_and_send(self, deal_ref, client_email, items, due_date, note) -> InvoiceRef: ...
    def remind(self, invoice_id, note) -> None: ...
    def get_status(self, invoice_id) -> str: ...
