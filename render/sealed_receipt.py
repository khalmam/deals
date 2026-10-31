"""Sealed receipt: plain data in, text or HTML out. Pure, standard library only."""
from html import escape

FIELDS = [("deal", "deal_id"), ("title", "title"), ("state", "state"), ("total", "total"),
          ("terms hash", "terms_hash"), ("head hash", "head_hash")]
PAYPAL = [("PayPal order", "order_id"), ("PayPal authorization", "authorization_id"),
          ("PayPal capture", "capture_id")]


def verdict(d):
    if d.get("intact"):
        return "ledger: intact"
    return f"ledger: BROKEN at entry {d.get('broken_seq')}"


def anchor_line(d):
    a = d.get("anchor")
    if a is None:
        return "anchored in PayPal: not checked"
    return "anchored in PayPal: yes" if a else "anchored in PayPal: NO, hash differs"


def receipt_text(d):
    lines = ["DEAL SEALED RECEIPT", ""]
    lines += [f"{label:<22}{d.get(key, '')}" for label, key in FIELDS]
    pp = d.get("paypal", {})
    lines += [f"{label:<22}{pp.get(key, '')}" for label, key in PAYPAL]
    lines += ["", "ledger entries:"]
    lines += [f"  {e['seq']:>2}  {e['kind']:<22}{e['hash'][:12]}  {e['ts']}"
              for e in d.get("entries", [])]
    return "\n".join(lines + ["", verdict(d), anchor_line(d)])


def _row(label, value):
    return f"<tr><th>{escape(label)}</th><td><code>{escape(str(value))}</code></td></tr>"


def receipt_html(d):
    pp = d.get("paypal", {})
    rows = "".join(_row(label, d.get(key, "")) for label, key in FIELDS)
    rows += "".join(_row(label, pp.get(key, "")) for label, key in PAYPAL)
    entries = "".join(
        f"<tr><td>{e['seq']}</td><td>{escape(e['kind'])}</td>"
        f"<td><code>{escape(e['hash'][:12])}</code></td><td>{escape(e['ts'])}</td></tr>"
        for e in d.get("entries", []))
    cls = "ok" if d.get("intact") else "bad"
    return f"""<!doctype html>
<meta charset="utf-8"><title>Deal sealed receipt</title>
<style>body{{font:15px system-ui;max-width:760px;margin:2rem auto;padding:0 1rem}}
th{{text-align:left;padding-right:1rem}}table{{border-collapse:collapse;margin:1rem 0}}
td,th{{padding:.25rem .5rem;border-bottom:1px solid #8884}}
.ok{{color:#0a7a3d}}.bad{{color:#c0262d}}</style>
<h1>Deal sealed receipt</h1><table>{rows}</table>
<h2>Ledger</h2><table><tr><th>#</th><th>event</th><th>hash</th><th>time</th></tr>{entries}</table>
<p class="{cls}"><strong>{escape(verdict(d))}</strong></p><p>{escape(anchor_line(d))}</p>"""
