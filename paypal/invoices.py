"""Invoices. The app needs the Invoicing feature enabled, or PayPal answers 403."""
from deals.domain.ports import InvoiceRef

from .client import PayPalClient, request_key


class PayPalInvoices:
    def __init__(self, client: PayPalClient, merchant_email):
        self._c = client
        self._merchant = merchant_email

    def create_and_send(self, deal_ref, client_email, items, due_date, note):
        """items: list of (name, Money). due_date: 'YYYY-MM-DD'."""
        currency = items[0][1].currency
        body = {
            "detail": {"currency_code": currency, "note": note,
                       "payment_term": {"term_type": "DUE_ON_DATE_SPECIFIED",
                                        "due_date": due_date}},
            "invoicer": {"email_address": self._merchant},
            "primary_recipients": [{"billing_info": {"email_address": client_email}}],
            "items": [{"name": n, "quantity": "1", "unit_amount": m.to_paypal()}
                      for n, m in items],
            "configuration": {"partial_payment": {"allow_partial_payment": False}},
        }
        created = self._c.request("POST", "/v2/invoicing/invoices", body,
                                  request_key(deal_ref, "invoice", due_date))
        invoice_id = created["href"].rstrip("/").split("/")[-1]
        self._c.request("POST", f"/v2/invoicing/invoices/{invoice_id}/send",
                        {"send_to_recipient": True, "send_to_invoicer": False},
                        request_key(deal_ref, "invoice-send", invoice_id))
        d = self._c.request("GET", f"/v2/invoicing/invoices/{invoice_id}")
        return InvoiceRef(invoice_id, d["detail"]["metadata"]["recipient_view_url"])

    def remind(self, invoice_id, note):
        self._c.request("POST", f"/v2/invoicing/invoices/{invoice_id}/remind",
                        {"subject": "Reminder", "note": note, "send_to_recipient": True})

    def get_status(self, invoice_id):
        return self._c.request("GET", f"/v2/invoicing/invoices/{invoice_id}")["status"]
