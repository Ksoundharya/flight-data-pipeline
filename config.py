"""Shared configuration and constants for the flight data generator/analyzer.

Python 3.7+ compatible: no walrus-in-default-args, no dataclass field
defaults requiring 3.8+, no positional-only params.
"""
import datetime
from pathlib import Path

# ---- Generation-scale requirements (from the assignment spec) ----
TARGET_NUM_FILES = 5000
CITY_POOL_MIN = 100
CITY_POOL_MAX = 200
RECORDS_PER_FILE_MIN = 50
RECORDS_PER_FILE_MAX = 100
DIRTY_PROB_MIN = 0.005
DIRTY_PROB_MAX = 0.01

DEFAULT_OUTPUT_DIR = Path("/tmp/flights")

REQUIRED_FIELDS = [
    "date",
    "origin_city",
    "destination_city",
    "flight_duration_secs",
    "#_of_passengers_on_board",
]

# Realistic bounds used both by the generator (to produce plausible values)
# and by the validator (to flag anything outside these bounds as suspicious,
# separate from a NULL-valued dirty field).
MIN_FLIGHT_DURATION_SECS = 20 * 60       # 20 minutes: shortest realistic scheduled flight
MAX_FLIGHT_DURATION_SECS = 20 * 60 * 60  # 20 hours: longest realistic nonstop flight
MAX_PASSENGERS = 850                     # above the largest passenger aircraft in service


def current_month_year_tag(now=None):
    """Return the %MM-YY% tag used in the required filename pattern.

    NOTE ON THE FILENAME-COLLISION FINDING (see generate_flights.py module
    docstring for the full analysis): this tag is constant for an entire
    generation run, since "current month and year" is evaluated once, not
    per file.
    """
    now = now or datetime.datetime.now()
    return now.strftime("%m-%y")
