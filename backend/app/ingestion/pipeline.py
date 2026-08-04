"""
Ingestion Pipeline
==================
Orchestrates normalise → validate → deduplicate → upsert for both trade
disclosures and price records.
"""

from decimal import Decimal
import logging

from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.models.price import Price
from app.ingestion.normalizer import normalise_record, parse_date_flexible
from app.ingestion.validator import validate_normalised_record, validate_price_record

logger = logging.getLogger(__name__)


def ingest_trades(db: Session, raw_records: list[dict]) -> dict:
    """Full pipeline for trade disclosure records."""
    inserted = skipped = errors = 0

    for raw in raw_records:
        try:
            normalised = normalise_record(raw)
            if normalised is None:
                errors += 1
                continue

            ok, reason = validate_normalised_record(normalised)
            if not ok:
                errors += 1
                continue

            exists = (
                db.query(Trade)
                .filter(
                    Trade.trader_id == normalised["trader_id"],
                    Trade.asset_symbol == normalised["asset_symbol"],
                    Trade.trade_date == normalised["trade_date"],
                    Trade.transaction_type == normalised["transaction_type"],
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(Trade(**normalised))
            inserted += 1

        except Exception as exc:
            logger.exception("Unexpected error processing record: %s", exc)
            errors += 1

    db.commit()
    return {"inserted": inserted, "skipped": skipped, "errors": errors}


def ingest_prices(db: Session, raw_records: list[dict]) -> dict:
    """Full pipeline for OHLCV price records."""
    inserted = updated = errors = 0

    for raw in raw_records:
        try:
            ok, reason = validate_price_record(raw)
            if not ok:
                errors += 1
                continue

            symbol = raw["asset_symbol"].strip().upper()
            price_date = parse_date_flexible(raw["date"])
            if not price_date:
                errors += 1
                continue

            existing = (
                db.query(Price)
                .filter(Price.asset_symbol == symbol, Price.date == price_date)
                .first()
            )

            if existing:
                existing.closing_price = Decimal(str(raw["closing_price"]))
                updated += 1
            else:
                db.add(
                    Price(
                        asset_symbol=symbol,
                        date=price_date,
                        closing_price=Decimal(str(raw["closing_price"])),
                        open_price=Decimal(str(raw["open"])) if raw.get("open") else None,
                        high_price=Decimal(str(raw["high"])) if raw.get("high") else None,
                        low_price=Decimal(str(raw["low"])) if raw.get("low") else None,
                        volume=Decimal(str(raw["volume"])) if raw.get("volume") else None,
                    )
                )
                inserted += 1

        except Exception as exc:
            logger.exception("Price ingestion error: %s", exc)
            errors += 1

    db.commit()
    return {"inserted": inserted, "updated": updated, "errors": errors}
