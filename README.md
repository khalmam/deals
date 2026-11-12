# Deals

Two parties, or their AI agents, negotiate a deal, and PayPal handles everything after
agreement: the payment hold, capture on confirmed delivery, payouts to sub-contractors, invoices,
and webhook-driven status. Built for the PayPal AI Hackathon.

**Status:** working sandbox prototype. Negotiation, PayPal hold/capture/void/refund, payouts,
webhooks, the tamper-evident ledger, the web UI and a Render deployment are all implemented
and covered by 383 tests.

- **Live demo:** <YOUR RENDER URL> (the free instance sleeps; the first load can take a minute)
- **Demo video:** <YOUR YOUTUBE URL>

## What it does
Two parties, or their AI agents, negotiate an agreement and back it with a PayPal payment.
When both accept, the terms are sealed and fingerprinted, and that hash travels with the PayPal
hold in `custom_id`. Funds are authorized, captured on confirmed delivery, and every webhook is
signature-verified and stored once, so the payment trail cannot be forged or replayed.

## Tools used
| Tool | Used for |
|---|---|
| **PayPal Sandbox** (Orders AUTHORIZE, capture, void, refund; Payouts; Invoicing; Webhooks) | The payment hold, capture on delivery, sub-contractor payouts, invoices, verified status updates |
| **Claude** (Anthropic API, or Amazon Bedrock when deployed) | The buyer and provider negotiating agents: counter-offers and message wording |
| Rules engine (`engine/`) | Checks every offer against budget, private floor and protocol rules. The AI proposes, the rules decide. Without a model key it runs the negotiation alone. |
| Django, PostgreSQL, Render | App, storage, hosting |

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

## State machines
Every lifecycle (deal, negotiation, turn-taking, deal stage, payout items, webhook outcome) is a
table in `deals/domain/`, read by the services, the pages, the JSON API and the agents. See
`docs/STATE_MACHINES.md` for diagrams, the new agent-facing fields and known gaps. After editing
a table, run `python manage.py machines --write docs/STATE_MACHINES.md`.

## Run it yourself

Requires Python 3.12. The fastest path uses SQLite and needs no accounts. The negotiation runs
on the rules engine alone, and the PayPal steps need sandbox credentials (see below).

```sh
git clone <YOUR GITHUB URL> && cd deals-app
pip install -r requirements-dev.txt
export DJANGO_SETTINGS_MODULE=config.settings.dev
export DATABASE_URL=sqlite:///db.sqlite3
export DEMO_SUB_EMAIL=<sandbox personal account email>   # receives the demo payout
python manage.py migrate
python manage.py seed_demo          # creates the demo providers
python manage.py runserver 8000
```

Open http://localhost:8000/negotiate/ and run a negotiation. Check `/healthz` answers `{"ok": true}`.
Run the tests with `python -m pytest -q`.

**Full flow with PayPal and Claude.** The app reads real environment variables, not a `.env` file,
so run `cp .env.example .env`, fill it in, then `set -a; source .env; set +a` in every terminal.

| Variable | Needed for |
|---|---|
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | Sandbox app credentials (PayPal developer dashboard) |
| `PAYPAL_WEBHOOK_ID` | Webhook verification; webhooks need a public URL (the Render deployment) |
| `ANTHROPIC_API_KEY` (or `LLM_PROVIDER=bedrock` with AWS credentials) | LLM-powered agents |
| `DEMO_SUB_EMAIL` | Sandbox personal account that receives the sub-contractor payout |

Then: open `/negotiate/`, run a negotiation, approve the hold with a sandbox buyer account,
confirm delivery (capture and payout), and open the receipt to see the ledger check.
Everything runs against the PayPal **sandbox**; no real money moves.

## Credits
The tamper-evident hash chain is adapted from my earlier project, Paper Trail.

## Agent identity and discovery (Milestone 1)

Deals now supports persistent provider and buyer agent profiles, a public directory, and
one-time bearer credentials for external agents. Credential tokens are shown once; only
SHA-256 digests are stored. Public directory responses deliberately omit owner email,
private mandates, endpoint URLs and credential data.

Create an agent from a trusted operator environment:

```sh
python manage.py migrate
python manage.py register_agent \
  --name "Northstar Backend" \
  --type PROVIDER \
  --owner-name "Ibrahim Imam" \
  --owner-email "owner@example.com" \
  --description "Django and API development" \
  --capabilities '["Django", "Django REST Framework", "PostgreSQL"]' \
  --services '[{"name":"REST API development","currency":"USD"}]'
```

The command prints a `dl_` bearer token once. Store it securely. The initial integration
surface is read-only identity verification and public discovery:

- `GET /api/agents?q=django&type=PROVIDER` — public agent directory.
- `GET /api/agents/me` — authenticated agent identity; send `Authorization: Bearer <token>`.

Buyer agents also receive the `deals:negotiate` scope. Payment scopes are not issued yet. Do
not expose the provisioning command as an unauthenticated public endpoint. Money steps that
need a human, such as approving the hold on PayPal, stay with the owner.

## Agent-to-agent negotiation (Milestone 2)

A provider publishes its rate card in `services` (entries with `id`, `items` and `floor` are
bundles; other entries are labels) and its payout rules in `mandate`. A buyer's `mandate` holds
its budget: `{"max_deal": "1500", "currency": "USD"}`.

```sh
python manage.py register_agent --name "Acme Buyer" --type BUYER --owner-name "Ada" \
  --owner-email ada@example.com --mandate '{"max_deal": "1400", "currency": "USD"}'
python manage.py run_buyer --token-file ~/.acme.token --provider northstar-backend --budget 1400
```

- `POST /api/deals` with a bearer token and `{"provider": slug, "bundle": id}` opens a deal
  priced from that provider's profile. Without a token it opens the original demo deal.
- Offers, advance, delivery, cancel and refresh on an agent's deal need that agent's token.
- A price above the buyer's budget is refused before it reaches the negotiation, and the
  provider's floor price is still enforced by the rules engine.


## Structured negotiation protocol

Agents negotiate by exchanging immutable, hash-linked messages. Deals authenticates, validates,
orders and records them; each agent decides its own strategy. Hosted and external providers
use the same routes and the same checks.

| Route | Who | Purpose |
|---|---|---|
| `POST /api/negotiations` | buyer | Open with a PROPOSE to a named provider |
| `POST /api/negotiations/<id>/messages` | either party | COUNTER, ACCEPT, REJECT or WITHDRAW |
| `GET /api/negotiations/<id>?verify=1` | either party | History, head, and an integrity check |
| `GET /api/negotiations` | either party | Your negotiations |

Every POST needs `Authorization: Bearer ...` (scope `deals:negotiate`) and an
`Idempotency-Key` header. Retrying with the same key and body returns the original result;
the same key with a different body is `422 IDEMPOTENCY_CONFLICT`.

- **Message type and negotiation status are separate.** Messages are PROPOSE, COUNTER,
  ACCEPT, REJECT or WITHDRAW. The negotiation is OPEN, AGREED, REJECTED, WITHDRAWN or EXPIRED.
- **Terms** are a bundle, a price, `delivery_days`, `payment.net_days` and
  `late.fee_pct` / `late.grace_days`. Omitted optional fields take explicit defaults; null,
  floats, unknown fields and hidden rounding are refused.
- **Hashing** uses one canonical form: sorted keys, no whitespace, NFC text, UTF-8, normalised
  decimals. `terms_hash` covers the terms; `message_hash` covers the whole envelope and the
  previous message's hash.
- **ACCEPT carries no terms.** It names the head with `in_reply_to` and quotes its
  `terms_hash`; a stale head is `409 STALE`, and a different hash is `409 TERMS_MISMATCH`.
- **Atomic.** A message, its `PROPOSAL_MADE` ledger entry, the head update and (for ACCEPT)
  the agreed terms commit together or not at all.
- **Floors are private.** A provider may publish no floor and keep it in its own agent
  (see `agents/negotiating_provider.py`). If it does give Deals a floor, that is used only to
  refuse the provider's own sends, the error goes only to the provider, and nothing public or
  sent to a buyer ever carries it.
- **Budget** is the buyer's own limit: it cannot propose or accept above its `max_deal`.
- Register a hosted provider with `--hosted`; its rate card must state a floor.


## Two-process demo

An independent provider and a buyer agent negotiate through Deals, each in its own terminal.
The provider's floor lives in a local file and is never sent to the server.

```sh
# 1. Register both agents. The provider publishes no floor. Save each printed token once.
python manage.py register_agent --name "Northstar Backend" --type PROVIDER \
  --owner-name Ibrahim --owner-email owner@example.com \
  --services '[{"id":"standard","name":"Standard","items":[{"name":"Logo","rate":900},{"name":"Art","rate":500,"sub_id":"illustrator","sub_pct":50},{"name":"Social","rate":400}]}]' \
  --mandate '{"allow_hold":true,"allow_capture":true,"allow_void":true,"allow_payouts":true,"approved_subs":{"illustrator":"SANDBOX_SUB_EMAIL"}}'
python manage.py register_agent --name "Amanah Procurement" --type BUYER \
  --owner-name Amanah --owner-email buyer@example.com \
  --mandate '{"max_deal":"1400","currency":"USD"}'
umask 077; echo 1037 > ~/.northstar.floor   # then put each token in its own file, chmod 600

# 2. Terminal A: the provider listens.
python manage.py run_provider --slug northstar-backend --list-price 1800 \
  --floor-file ~/.northstar.floor --token-file ~/.northstar.token

# 3. Terminal B: the buyer negotiates within its limits.
python manage.py run_procurement --slug amanah-procurement --provider northstar-backend \
  --token-file ~/.amanah.token --max-price 1400 --target-price 1300
```

Check a deployment with `python manage.py smoke_hosted --base-url https://YOUR-APP.onrender.com`.
Add `--token-file`, `--slug` and `--provider` to also run a full negotiation against it.


## Deploying

See `DEPLOY.md` for the Render steps (a `render.yaml` Blueprint, the PayPal webhook, and the
smoke test). The app is sandbox-only.
