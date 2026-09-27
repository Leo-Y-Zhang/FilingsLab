"""
Signal engine: role conviction
==============================
``_conviction_score`` ranks insiders by role, on the documented basis that
officers' trades carry more signal than directors' (Lakonishok & Lee 2001, cited
in the module docstring). It matched role keys as substrings, and "director"
contains "cto": every plain Director scored as a CTO, 15 against an officer's
13, which inverted the ordering the table encodes. Director is the role
``edgar._parse_xml`` assigns to every non-officer board member, so this reached
a large share of the live feed and every score the auto-trader acts on.

At $50k the size multiplier is 1.0 and one insider is no cluster, so the score
is the role's base value exactly. Watched failing first: Director scored 15.0
and "Coordinator" 16.0 (a COO).
"""
import pytest

from app.services.signal_engine import _conviction_score

_NEUTRAL_AMOUNT = 50_000


@pytest.mark.parametrize(
    "role,base",
    [
        ("Director", 9.0),
        ("CTO", 15.0),
        ("EVP, CTO", 15.0),
        ("President & CEO", 18.0),      # first key in table order wins, as before
        ("Chief Executive Officer", 13.0),
        ("Director, Chief Operating Officer", 13.0),
        ("10%+ Owner", 8.0),
        ("Insider", 7.0),
        ("Coordinator", 7.0),           # not a COO
        ("", 7.0),
    ],
)
def test_role_base_is_matched_on_whole_words(role, base):
    assert _conviction_score(role, _NEUTRAL_AMOUNT) == pytest.approx(base)


def test_an_officer_outranks_a_director():
    assert _conviction_score("Officer", _NEUTRAL_AMOUNT) > _conviction_score("Director", _NEUTRAL_AMOUNT)
