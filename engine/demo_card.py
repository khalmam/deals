"""The sample rate card used by the demo: a brand-design freelancer. Pure."""
from deals.domain.money import Money

from .catalog import Bundle, LineItem, RateCard


def usd(value):
    return Money.of(value, "USD")


def demo_card():
    logo = LineItem("Logo and identity system", usd(900))
    art = LineItem("Illustration set", usd(500), sub_id="illustrator", sub_pct=50)
    social = LineItem("Social media kit", usd(400))
    return RateCard(bundles=(
        Bundle("basic", "Basic", (LineItem("Logo concept and design", usd(400)),
                                  LineItem("Colour palette and type", usd(200))), usd(500)),
        Bundle("standard", "Standard", (logo, art, social), usd(1500)),
        Bundle("premium", "Premium", (
            LineItem("Full identity system", usd(1400)),
            LineItem("Illustration set", usd(800), sub_id="illustrator", sub_pct=50),
            social,
            LineItem("Landing page design", usd(900), sub_id="webdev", sub_pct=40),
        ), usd(2900)),
    ))
