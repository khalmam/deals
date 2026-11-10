"""Saves and merges the chat on a deal page. Chat is kept apart from the ledger."""
from deals.models import ChatMessage

CAP = 50


def record_chat(deal, client_text, reply):
    """Save the client's message and the freelancer's reply, unless the deal is at its cap."""
    if ChatMessage.objects.filter(deal=deal).count() >= CAP:
        return False
    last = deal.ledger.order_by("-seq").values_list("seq", flat=True).first()
    after = -1 if last is None else last
    ChatMessage.objects.bulk_create([
        ChatMessage(deal=deal, after_seq=after, who="client", text=client_text[:500]),
        ChatMessage(deal=deal, after_seq=after, who="freelancer", text=reply[:500]),
    ])
    return True


def merge_chat(rows, deal):
    """Put chat rows into the transcript. Each ledger row carries its entry's seq; a chat
    message goes right after the entries up to its after_seq."""
    chat = [{"who": "Client" if m.who == "client" else "Freelancer", "price": "",
             "currency": "", "message": m.text, "walked_away": False, "source": "",
             "notes": [], "chat": True, "seq": m.after_seq} for m in deal.chat.all()]
    if not chat:
        return rows
    keyed = [((r["seq"], 0, i), r) for i, r in enumerate(rows)]
    keyed += [((r["seq"], 1, i), r) for i, r in enumerate(chat)]
    return [r for _, r in sorted(keyed, key=lambda k: k[0])]


def recent_turns(deal, limit=6):
    """The last few things said on the deal, oldest first, as 'Client: ...' lines for the
    model's prompt. Offers come from the ledger, small talk from the chat table."""
    rows = []
    for e in deal.ledger.filter(kind__in=("OFFER_MADE", "COUNTER_MADE")).order_by("seq"):
        p = e.payload
        who = "Freelancer" if p.get("by") == "freelancer" else "Client"
        said = p.get("message") or f"{p.get('price', '')} {p.get('currency', '')}".strip()
        rows.append(((e.seq, 0), f"{who}: {said}"))
    for m in deal.chat.all():
        who = "Client" if m.who == "client" else "Freelancer"
        rows.append(((m.after_seq, 1), f"{who}: {m.text}"))
    rows.sort(key=lambda r: r[0])
    return "\n".join(line for _, line in rows[-limit:])
