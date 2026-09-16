"""Record-level validation for flight data. Kept separate from
analyze_flights.py so it can be unit tested in isolation.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Tuple

from config import (
    REQUIRED_FIELDS, MIN_FLIGHT_DURATION_SECS, MAX_FLIGHT_DURATION_SECS,
    MAX_PASSENGERS,
)

PASSENGERS_FIELD = "#_of_passengers_on_board"


def is_dirty(record: Dict[str, Any]) -> bool:
    """A record is 'dirty' iff one or more REQUIRED fields is present with a
    NULL value, or the field is missing entirely (treated the same as NULL,
    since a missing key and an explicit null carry the same information
    once the record reaches analysis: "we don't know this value")."""
    for field in REQUIRED_FIELDS:
        if record.get(field, None) is None:
            return True
    return False


def is_valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate_clean_record(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a record that has already passed is_dirty()==False (i.e. no
    NULLs). Checks semantic validity beyond "not null": correct types,
    origin != destination, positive duration, non-negative passengers, and
    a parseable ISO date. Returns (is_valid, list_of_reasons_if_invalid).

    This is intentionally a SEPARATE category from "dirty": a record with
    non-null but semantically wrong values (e.g. origin == destination, or
    a negative duration produced by a corrupted upstream feed) is not what
    the assignment defines as "dirty" (NULL-valued), but it is still not
    safe to fold into passenger-balance or duration statistics without
    distorting them. We call this category "invalid" and quarantine it
    exactly like dirty records, but count and report it separately so the
    two failure modes are not conflated in the final report.
    """
    reasons = []
    origin = record.get("origin_city")
    dest = record.get("destination_city")
    duration = record.get("flight_duration_secs")
    passengers = record.get(PASSENGERS_FIELD)
    date = record.get("date")

    if not isinstance(origin, str) or not origin:
        reasons.append("origin_city not a non-empty string")
    if not isinstance(dest, str) or not dest:
        reasons.append("destination_city not a non-empty string")
    if isinstance(origin, str) and isinstance(dest, str) and origin == dest:
        reasons.append("origin_city == destination_city")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        reasons.append("flight_duration_secs not numeric")
    elif duration <= 0:
        reasons.append("flight_duration_secs <= 0")
    if not isinstance(passengers, (int, float)) or isinstance(passengers, bool):
        reasons.append(f"{PASSENGERS_FIELD} not numeric")
    elif passengers < 0:
        reasons.append(f"{PASSENGERS_FIELD} < 0")
    if not is_valid_date(date):
        reasons.append("date not a valid ISO date")

    return (len(reasons) == 0, reasons)


def has_unexpected_fields(record: Dict[str, Any]) -> bool:
    return not set(record.keys()).issubset(set(REQUIRED_FIELDS))
