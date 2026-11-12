"""The extra hosted demo providers."""
from deals.services.seed_demo import seed_more_providers
from deals.services.ui_deal import hosted_providers


def test_more_providers_are_seeded_once(db):
    first = seed_more_providers("sub@example.com")
    assert set(first.values()) == {"created"}, first
    assert set(seed_more_providers("sub@example.com").values()) == {"exists"}
    names = {a["name"] for a in hosted_providers()}
    assert {"Kora Brand Studio", "Lumen Web Works", "Meridian Data Labs",
            "Atlas Content Co."} <= names


def test_the_provider_with_a_sub_contractor_needs_an_email(db):
    result = seed_more_providers("")
    assert result["Atlas Content Co."] == "skipped"
    assert result["Kora Brand Studio"] == "created"
