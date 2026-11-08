"""The loops behind the demo commands. Plain functions so they can be tested without a server
process: pass any client, a printer and a sleep."""
import time


def own_slug(client, given=""):
    """The slug the server knows this token by. A mismatched --slug is an error, not a guess."""
    actual = client.me()["slug"]
    if given and given != actual:
        raise ValueError(f"--slug {given} does not match this token, which belongs to {actual}")
    return actual


def _show(view, seen, out):
    for m in view["messages"]:
        if m["version"] in seen:
            continue
        seen.add(m["version"])
        price = (m["terms"].get("price") or {}).get("amount", "")
        out(f"  v{m['version']}  {m['from']:<22} {m['type']:<8} {price}".rstrip())


def run_procurement(agent, provider, bundle, out=print, interval=2, limit=60, sleep=time.sleep):
    """Open a negotiation and keep answering until it ends. Returns the verified view."""
    seen = set()
    out(f"{agent.slug} opens a negotiation with {provider} for '{bundle}'")
    _show(agent.start(provider, bundle), seen, out)
    for _ in range(limit):
        view = agent.client.get(agent.negotiation_id)
        _show(view, seen, out)
        if view["status"] != "OPEN":
            break
        if agent.step() == "acted":
            continue
        sleep(interval)
    final = agent.client.get(agent.negotiation_id, verify=True)
    _show(final, seen, out)
    return final


def run_provider(provider, out=print, interval=2, once=False, limit=None, sleep=time.sleep):
    """Answer incoming proposals forever (or once). The floor never leaves this process."""
    out(f"{provider.slug} is listening; its floor stays on this machine")
    done = 0
    while limit is None or done < limit:
        for nid, reply in provider.step():
            out(f"  answered {nid[:8]} with {reply}")
        done += 1
        if once:
            return
        sleep(interval)
