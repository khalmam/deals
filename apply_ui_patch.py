#!/usr/bin/env python3
"""Run once from the repo root:  python3 apply_ui_patch.py

New intro and a tidier start page (and the same intro treatment on /negotiate/).
  * Intro: "Choose a provider, negotiate the price in your own words, then approve and pay
    with PayPal", with a three-step strip (1 Choose, 2 Negotiate, 3 Approve and pay).
  * Provider cards are compact: name, a two-line description, up to three capability tags and
    one line "From 1000 USD · 2 services", instead of every service listed. Three across.
  * The Start button sits in a bar that stays at the bottom of the screen and shows who is
    selected, so you no longer scroll past every card to find it.
  * The closing note on /start/ becomes three short trust points.
Nothing is written unless every edit matches exactly once."""
import os
import sys

PARTIAL = "web/templates/web/_provider_cards.html"
TEST = "tests/test_ui_polish.py"
if os.path.exists(TEST):
    sys.exit(f"STOP: {TEST} already exists. If you already ran this script, that is why.")
if not os.path.isdir("tests"):
    sys.exit("STOP: no tests folder here. Run this from the repo root (the folder with manage.py).")

CARDS = '''{% if cards or sample %}
<style>
form[data-neg], form[data-start] { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1rem; align-items: end; max-width: 100%; }
form[data-neg] label, form[data-start] label { display: flex; flex-direction: column; gap: .35rem; }
form[data-neg] button, form[data-start] button { justify-self: start; }
form[data-start] { position: sticky; bottom: 0; z-index: 5; margin-top: 1rem; padding: 1rem 0; background: var(--bg, #f5f5f7); border-top: 1px solid rgba(0, 0, 0, .09); }
.pick-selected { display: flex; flex-direction: column; gap: .15rem; }
[data-detail] { display: none !important; }
.flow { display: flex; flex-wrap: wrap; gap: .5rem 1.75rem; list-style: none; padding: 0; margin: 1rem 0 0; color: var(--mute, #6e6e73); font-size: .95rem; }
.flow b { display: inline-grid; place-items: center; width: 1.5rem; height: 1.5rem; margin-right: .5rem; border-radius: 50%; background: #1d1d1f; color: #fff; font-size: .8rem; }
.pick-set { border: 0; padding: 0; margin: 1.75rem 0 1rem; min-width: 0; }
.pick-set legend { font-weight: 600; margin-bottom: .75rem; padding: 0; }
.pick-set .agent-grid { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
.pick { position: relative; cursor: pointer; display: flex; flex-direction: column; border: 1px solid #d2d2d7; }
.pick input { position: absolute; opacity: 0; pointer-events: none; }
.pick.is-picked { border-color: #1d1d1f; box-shadow: 0 0 0 2px #1d1d1f; }
.pick-off { opacity: .55; cursor: not-allowed; }
.pick-desc { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.pick-foot { margin-top: auto; padding-top: .75rem; }
.pick-note { font-size: .85rem; }
.trust-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; list-style: none; padding: 0; margin: 2rem 0 0; color: var(--mute, #6e6e73); font-size: .9rem; }
.trust-row li { border-top: 1px solid rgba(0, 0, 0, .09); padding-top: .75rem; }
</style>
<ol class="flow">
  <li><b>1</b>Choose a provider</li>
  <li><b>2</b>Negotiate the price</li>
  <li><b>3</b>Approve and pay with PayPal</li>
</ol>
<fieldset class="pick-set" data-cards>
  <legend>Choose who you negotiate with</legend>
  <div class="agent-grid">
  {% if sample %}
    <label class="card agent-card pick">
      <input type="radio" name="provider-card" value="">
      <div class="agent-card-top"><span class="agent-mark">S</span><span class="agent-status"><i></i> Demo</span></div>
      <h3>Sample freelancer</h3>
      <p class="agent-description pick-desc">A brand-design freelancer with a built-in rate card. The quickest way to try the whole flow.</p>
      <p class="meta pick-foot">Built-in rate card</p>
    </label>
  {% endif %}
  {% for p in cards %}
    <label class="card agent-card pick{% if not p.hosted %} pick-off{% endif %}">
      <input type="radio" name="provider-card" value="{{ p.slug }}"{% if not p.hosted %} disabled{% endif %}>
      <div class="agent-card-top"><span class="agent-mark">{{ p.name|slice:":1"|upper }}</span>{% if p.hosted %}<span class="agent-status"><i></i> Available now</span>{% endif %}</div>
      <h3>{{ p.name }}</h3>
      <p class="agent-description pick-desc">{{ p.description|default:"This provider has not added a description yet." }}</p>
      {% if p.capabilities %}<div class="agent-tags">{% for c in p.capabilities|slice:":3" %}<span>{{ c }}</span>{% endfor %}</div>{% endif %}
      <p class="meta pick-foot">From {{ p.from_price }} {{ p.from_currency }} · {{ p.service_count }} service{{ p.service_count|pluralize }}</p>
      {% if not p.hosted %}<p class="meta pick-note">Runs its own agent. Negotiate with it through the API.</p>{% endif %}
    </label>
  {% endfor %}
  </div>
</fieldset>
<script>
document.addEventListener('DOMContentLoaded', function () {
  var grid = document.querySelector('[data-cards]'); if (!grid) return;
  var psel = document.querySelector('[data-provider]');
  var radios = grid.querySelectorAll('input[type=radio]');
  function mark() {
    grid.querySelectorAll('.pick').forEach(function (c) {
      c.classList.toggle('is-picked', c.querySelector('input').checked);
    });
    var on = grid.querySelector('input:checked');
    document.querySelectorAll('[data-selected]').forEach(function (el) {
      el.textContent = on ? on.closest('.pick').querySelector('h3').textContent : '';
    });
  }
  var current = psel ? psel.value : '';
  radios.forEach(function (r) {
    r.checked = (r.value === current) && !r.disabled;
    r.addEventListener('change', function () {
      if (psel) { psel.value = r.value; psel.dispatchEvent(new Event('change')); }
      mark();
    });
  });
  if (psel && psel.closest('label')) { psel.closest('label').style.display = 'none'; }
  if (!grid.querySelector('input:checked')) {
    var first = grid.querySelector('input:not(:disabled)'); if (first) { first.checked = true; }
  }
  mark();
});
</script>
{% endif %}
'''

SELECTED = ('    <div class="pick-selected"><span class="meta">Selected</span>'
            '<strong data-selected></strong></div>\n')
START_INTRO_OLD = ('  <p class="state">You play the client. Choose who you negotiate with, or keep the '
                   'sample freelancer, whose agent opens with the Standard brand package at 1800.00 '
                   'USD. Haggle in your own words, approve the hold in PayPal’s sandbox, confirm '
                   'delivery, and watch the money move.</p>\n')
START_INTRO_NEW = ('  <p class="state">Choose a provider, negotiate the price in your own words, then '
                   'approve the payment with PayPal. AI agents do the haggling, Deals records every '
                   'move, and PayPal handles the money.</p>\n')
START_LEDE_OLD = ('  <p class="lede">The agent can never go below its floor. Whatever you type, the '
                  'rules engine decides and every move goes in the sealed ledger.</p>\n')
START_LEDE_NEW = ('  <ul class="trust-row">\n'
                  '    <li>The provider’s agent never goes below its floor price.</li>\n'
                  '    <li>Every move is recorded in a hash-linked ledger.</li>\n'
                  '    <li>PayPal handles payment, and only after you confirm delivery.</li>\n'
                  '  </ul>\n')
NEG_INTRO_OLD = ('  <p class="state">Choose a provider, set the most you will pay and the price you '
                 'would be happy with. A buyer agent negotiates for you within those limits, using '
                 'the same protocol any outside agent would. Then you approve the PayPal hold '
                 'yourself.</p>\n')
NEG_INTRO_NEW = ('  <p class="state">Set the most you will pay and the price you would be happy with. '
                 'A buyer agent negotiates for you within those limits, using the same protocol any '
                 'outside agent would. Then you approve the PayPal payment yourself.</p>\n')

EDITS = {
    "deals/services/ui_deal.py": [
        ("import secrets\n", "import secrets\nfrom decimal import Decimal\n"),
        ('    return sorted(found, key=lambda a: (not a["hosted"], a["name"].lower()))\n',
         '    for a in found:  # what the pick cards show: the lowest price and how many services\n'
         '        priced = [s for s in a["services"] if s.get("list_price")]\n'
         '        low = min(priced, key=lambda s: Decimal(str(s["list_price"])))\n'
         '        a["from_price"] = f"{Decimal(str(low[\'list_price\'])):.0f}"\n'
         '        a["from_currency"], a["service_count"] = low.get("currency", ""), len(priced)\n'
         '    return sorted(found, key=lambda a: (not a["hosted"], a["name"].lower()))\n')],
    "web/templates/web/start.html": [
        (START_INTRO_OLD, START_INTRO_NEW),
        ("  <form class=\"say\" data-start>\n", "  <form class=\"say\" data-start>\n" + SELECTED),
        (START_LEDE_OLD, START_LEDE_NEW)],
    "web/templates/web/negotiate.html": [
        (NEG_INTRO_OLD, NEG_INTRO_NEW),
        ("  <form class=\"say\" data-neg>\n", "  <form class=\"say\" data-neg>\n" + SELECTED)],
}
TESTS = '''"""The new intro, the compact provider cards and the selection bar."""


def test_start_page_has_the_new_intro_and_compact_cards(client, parties):
    page = client.get("/start/").content.decode()
    assert "Choose a provider" in page and "Approve and pay with PayPal" in page
    assert "From " in page and "data-selected" in page


def test_negotiate_page_has_the_selection_bar(client, parties):
    page = client.get("/negotiate/").content.decode()
    assert "From " in page and "data-selected" in page
'''
FILES = {}
for path, pairs in EDITS.items():
    try:
        text = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        sys.exit(f"STOP: {path} not found. Run this from the repo root (the folder with manage.py).")
    for old, new in pairs:
        n = text.count(old)
        if n != 1:
            sys.exit(f"STOP: {path}: expected 1 match, found {n}, for:\n{old[:160]}\n"
                     "Nothing was changed. If you already ran this script, that is why.")
        text = text.replace(old, new)
    FILES[path] = text
try:
    current = open(PARTIAL, encoding="utf-8").read()
except FileNotFoundError:
    sys.exit(f"STOP: {PARTIAL} not found. Apply apply_cards_patch.py first.")
if "data-cards" not in current or "pick-set" not in current:
    sys.exit(f"STOP: {PARTIAL} is not the version this script replaces. Nothing was changed.")
FILES[PARTIAL], FILES[TEST] = CARDS, TESTS
for path, body in FILES.items():
    if path.endswith(".py"):
        try:
            compile(body, path, "exec")
        except SyntaxError as exc:
            sys.exit(f"STOP: {path} would not compile ({exc}). Nothing was changed.")
for path, body in FILES.items():
    open(path, "w", encoding="utf-8").write(body)
    print("wrote", path)
print("\nDone. Next: pytest -q, then reload /start/ and /negotiate/.")
