# Deals

An agent negotiates a freelance deal with a client's agent, and PayPal handles everything after
agreement: the payment hold, capture on confirmed delivery, payouts to sub-contractors, invoices,
and webhook-driven status. Built for the PayPal AI Hackathon.

**Status (Oct 29):** foundation only. The PayPal adapter and the domain core are done and tested;
negotiation, ledger persistence, UI and deployment are in progress.

## How it works with PayPal
- **Hold:** an Order with intent AUTHORIZE. The client approves on PayPal. Valid up to 29 days.
  This is a payment hold, not escrow.
- **Capture** on confirmed delivery (partial captures supported), **void** if terms change, **refund**.
- **Payouts** to approved sub-contractors after capture.
- **Invoices** for balances, with reminders. The PayPal app needs the Invoicing feature enabled.
- The hash of the agreed terms is stored in the hold's `custom_id`, so the commitment also lives
  in PayPal's records.
- Sandbox only. The FX rate-lock API is not available to ordinary apps, so local-currency figures
  are labeled estimates.

## Architecture rules (enforced by `tests/test_architecture.py`)
Rules decide, the AI proposes. Inner layers never import outer ones.

| Layer | Folder | May not import |
|---|---|---|
| Pure domain | `deals/domain` | Django, httpx, PayPal, engine, agents, web |
| Rules engine | `engine` | Django, httpx, PayPal, agents, web |
| Agent contract | `agents` | Django, PayPal, engine, web |
| PayPal adapter | `paypal` | Django, engine, agents, web, models, services |
| Rendering | `render` | everything else |
| Persistence | `deals/models` | PayPal, engine, agents, web, services |
| Use cases | `deals/services` | PayPal (it uses the port), web |
| Web | `web` | PayPal, engine, agents, models |

Also enforced: no file over 200 lines, every Python folder has `__init__.py`, no floats in money
code, environment variables read only in `config/env.py`.

## Run
```
cp .env.example .env      # fill in sandbox credentials
make install
make test
make run
```

## Credits
The tamper-evident hash chain is adapted from my earlier project, Paper Trail.
