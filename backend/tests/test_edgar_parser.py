"""Parse tiny in-memory Form 4 documents without fetching filings."""

import pytest

from app.services.edgar import _parse_xml


FILE_DATE = "2024-03-05"


def transaction(code="P", shares="100", price="100", trade_date="2024-03-01"):
    return f"""<nonDerivativeTransaction>
      <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionDate><value>{trade_date}</value></transactionDate>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>"""


def filing(transactions, ticker=" acme ", officer="1", director="1", owner="0", title="CEO"):
    return f"""<ownershipDocument>
      <issuer><issuerTradingSymbol>{ticker}</issuerTradingSymbol><issuerName>Example</issuerName></issuer>
      <reportingOwner><reportingOwnerId><rptOwnerName>Example Owner</rptOwnerName>
        <rptOwnerCik> 123 </rptOwnerCik></reportingOwnerId>
        <reportingOwnerRelationship><isOfficer>{officer}</isOfficer>
          <isDirector>{director}</isDirector><isTenPercentOwner>{owner}</isTenPercentOwner>
          <officerTitle>{title}</officerTitle></reportingOwnerRelationship>
      </reportingOwner><nonDerivativeTable>{transactions}</nonDerivativeTable>
    </ownershipDocument>"""


def test_purchase_at_exact_threshold_and_sale_keep_values_and_direction():
    rows = _parse_xml(filing(transaction() + transaction("S", "200", "125.25")), FILE_DATE)
    assert len(rows) == 2
    assert rows[0] == {
        "trader_name": "Example Owner", "insider_cik": "123", "trader_role": "CEO",
        "company": "Example", "ticker": "ACME", "transaction_type": "buy",
        "trade_date": "2024-03-01", "disclosure_date": FILE_DATE,
        "amount_est": 10000, "amount_str": "$10,000", "shares": 100,
        "price_per_share": 100, "chamber": "Corporate Insider",
    }
    assert rows[1]["transaction_type"] == "sell"
    assert rows[1]["amount_est"] == 25050
    assert rows[1]["shares"] == 200
    assert rows[1]["price_per_share"] == 125.25


@pytest.mark.parametrize("changes", [
    {"code": "A"}, {"code": ""}, {"shares": "99.99"},
    {"shares": "0"}, {"price": "0"}, {"shares": "-100", "price": "-100"},
    {"shares": "invalid"}, {"price": "invalid"},
])
def test_one_corrupted_transaction_is_rejected_without_losing_valid_neighbor(changes):
    rows = _parse_xml(filing(transaction(**changes) + transaction("S")), FILE_DATE)
    assert len(rows) == 1
    assert rows[0]["transaction_type"] == "sell"


@pytest.mark.parametrize("xml", [
    "", "<ownershipDocument>", filing(transaction())[:-20],
    filing(transaction(), ticker=""),
    "<ownershipDocument><nonDerivativeTable/></ownershipDocument>",
])
def test_truncated_or_missing_identity_document_is_rejected(xml):
    assert _parse_xml(xml, FILE_DATE) == []


@pytest.mark.parametrize("tag", ["transactionShares", "transactionPricePerShare", "transactionCode"])
def test_missing_required_transaction_field_is_rejected(tag):
    import xml.etree.ElementTree as ET

    root = ET.fromstring(filing(transaction()))
    for parent in root.iter():
        for child in list(parent):
            if child.tag == tag:
                parent.remove(child)
    assert _parse_xml(ET.tostring(root, encoding="unicode"), FILE_DATE) == []


@pytest.mark.parametrize("officer,director,owner,title,expected", [
    ("TRUE", "1", "1", "", "Officer"),
    ("0", "true", "1", "", "Director"),
    ("0", "0", "true", "", "10%+ Owner"),
    ("0", "0", "0", "", "Insider"),
])
def test_role_precedence_and_missing_transaction_date(officer, director, owner, title, expected):
    xml = filing(transaction(trade_date=""), officer=officer, director=director, owner=owner, title=title)
    row, = _parse_xml(xml, FILE_DATE)
    assert row["trader_role"] == expected
    assert row["trade_date"] == FILE_DATE
