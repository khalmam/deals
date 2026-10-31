# Learning log: Deals

Notes on what we built and why. Written as we go, so it doubles as source material for the
README and the demo narration.

## 1. Sandbox and tokens
The sandbox is a fake PayPal with fake accounts. A client ID and secret are exchanged for a
short-lived access token (OAuth client credentials). `paypal/client.py` caches it and refreshes
a minute early. Sandbox accounts behave like real accounts of their country, so ours are US.

## 2. Authorize, capture, void
Authorizing sets money aside, capturing takes it, voiding releases it. A hold is valid up to 29
days and guaranteed for 3, so it is a payment hold, not escrow. PayPal allows one
reauthorization between day 4 and 29. The spike proved partial capture, void, refund, and that
`custom_id` stores a note on the hold.

## 3. Idempotency
Every money call carries a `PayPal-Request-Id`. A retry with the same id returns the original
result instead of charging twice. `request_key(deal, step)` makes the id stable.

## 4. Webhooks and tunnels
A webhook is PayPal calling our server. A laptop has no public address, so a tunnel (outbound
connection to Cloudflare) borrows one. We verify each event by sending its headers back to
PayPal's verify endpoint, because anyone could POST to a public URL.

## 5. Layers (ports and adapters)
Inner layers are pure Python and know nothing of Django or PayPal. `PaymentsPort` is the
contract; PayPal is one implementation and tests use a fake. `tests/test_architecture.py` reads
every file's imports and fails on a violation. We proved it by breaking the rules on purpose.

## 6. State machine
A deal moves only along allowed edges, so capture before delivery or void after capture is
refused before PayPal is touched.

## 7. The service pattern
Check the move is legal, call PayPal, then write the database and ledger in one transaction.
PayPal goes first because a database change can be undone and a captured payment cannot. If the
database write fails afterwards, a retry reuses the idempotency key.

## 8. The ledger
Each entry's hash covers its content and the previous hash, so editing, removing or reordering
any entry breaks the chain after it. This detects tampering. A Postgres trigger also prevents
ordinary edits, and the chain catches an admin who disables the trigger. The terms hash is also
stored in PayPal's `custom_id`, and `confirm_hold` compares PayPal's record with ours.

## 9. Sealed receipt and the tamper demo
`build_receipt` gathers plain data; `render/sealed_receipt.py` turns it into text or HTML and
escapes every value. `python manage.py receipt` prints it, `--html FILE` writes a page and
`--check-paypal` asks PayPal whether its stored hash matches. `tamper_demo` edits a ledger row
inside a transaction, shows the break, then rolls back so nothing is lost.

## Habits worth keeping
- Heredocs (`cat > file <<'EOF'`) write files exactly as typed.
- `set -a; source .env; set +a` loads variables into the shell.
- `pytest` uses SQLite; add `--ds=config.settings.dev` to run against Postgres.
- Do not put comments after commands in a pasted terminal block; zsh treats `#` as text.

## Not yet verified
Live webhook event names, the MCP tool list, the invoice late-fee option, and reauthorization
returning a new id (it cannot be tested before day 4 of a hold).
