# Deploying to Render

Sandbox only: the PayPal base URL is fixed to the sandbox, and nothing here moves real money.

1. **Push** this repository (including `render.yaml`) to GitHub.
2. In Render: **New → Blueprint**, pick the repository. It creates the web service `deals` and
   the Postgres database `deals-db`. When prompted, enter:
   - `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`: your **sandbox** app credentials.
   - `DEMO_SUB_EMAIL`: the sandbox personal account that receives the demo payout.
   - `PAYPAL_WEBHOOK_ID`: type `pending` for now; step 4 replaces it.
3. Wait for the first deploy. Open `https://<your-service>.onrender.com/healthz`; it should
   answer `{"ok": true}`. The first request after idle can take about a minute on the free plan.
4. **Register the webhook.** In the PayPal developer dashboard, open your sandbox app, add a
   webhook with the URL `https://<your-service>.onrender.com/webhooks/paypal/`, subscribe to
   the payment capture and payout events, copy its **Webhook ID**, and set `PAYPAL_WEBHOOK_ID`
   in Render. The service restarts.
5. **Check it**: `python manage.py smoke_hosted --base-url https://<your-service>.onrender.com`
6. Open `/negotiate/`, run a negotiation, approve the hold as the sandbox buyer, and confirm
   delivery. This is the real test.

## Things to know

- **Free web services sleep** after about 15 minutes without traffic. Open the site a minute
  before a demo or a judge's visit.
- **Free Postgres expires 30 days after creation.** A deployment made on Nov 10 expires around
  Dec 10, inside the judging period. Upgrade the database plan in Render before then, or accept
  that the demo data resets: a fresh database re-creates the demo provider on start.
- **Rate limits:** the public negotiate endpoint allows 12 runs per client and 120 overall per
  10 minutes (`UI_NEGOTIATE_*` in `config/settings/base.py`).
- **The app reads real environment variables, not a `.env` file.** Locally run
  `set -a; source .env; set +a` first.
