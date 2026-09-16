#!/usr/bin/env python3
"""Generate ~5,000 JSON files of synthetic flight data under a structured
folder hierarchy, per the Task 2 Phase 1 specification.

============================================================
FILENAME-COLLISION FINDING (documented per the assignment's explicit
instruction not to silently ignore this)
============================================================

The required path template is:

    /tmp/flights/%MM-YY%-%origin_city%-flights.json

"%MM-YY%" is "the current month and year" -- evaluated ONCE per generation
run, not once per file. Combined with "%origin_city%" drawn from a pool of
only K in [100, 200] cities, the template has at most K distinct values
during a single run. Since the spec also asks for approximately 5,000
files, this is a direct conflict: with K <= 200 possible names and 5,000
files requested, the pigeonhole principle guarantees at least
ceil(5000/200) = 25 files would collide on name and silently overwrite one
another if the template were implemented literally.

We do not ignore this. We implement the closest safe interpretation that
preserves the required naming concept (month-year prefix, origin city
component, "-flights.json" suffix) while guaranteeing uniqueness: a
zero-padded per-(month-year, origin_city) sequence number is inserted
before the suffix:

    /tmp/flights/<MM-YY>/<MM-YY>-<origin_city>-<00001..NNNNN>-flights.json

We additionally nest files one directory per origin city under the month-
year directory, both to keep any single directory listing to a manageable
size (a flat directory with ~5,000 files is legal but needlessly slow to
list/`ls` on many filesystems) and because "a structured folder hierarchy"
is explicitly requested and a single flat folder is not a hierarchy.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import string
import time
from pathlib import Path
from typing import List, Tuple

from config import (
    TARGET_NUM_FILES, CITY_POOL_MIN, CITY_POOL_MAX, RECORDS_PER_FILE_MIN,
    RECORDS_PER_FILE_MAX, DIRTY_PROB_MIN, DIRTY_PROB_MAX, DEFAULT_OUTPUT_DIR,
    REQUIRED_FIELDS, MIN_FLIGHT_DURATION_SECS, MAX_FLIGHT_DURATION_SECS,
    MAX_PASSENGERS, current_month_year_tag,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [generate] %(message)s")
logger = logging.getLogger("generate_flights")

# A generous, real-world city name list so that "realistic" city names are
# used rather than synthetic placeholders like "City_042". Drawn from major
# world airports/metro areas; deliberately longer than CITY_POOL_MAX so
# sampling K from it still looks like plausible airline route data.
CITY_NAME_POOL = [
    "New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
    "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville",
    "Fort Worth", "Columbus", "Charlotte", "San Francisco", "Indianapolis",
    "Seattle", "Denver", "Washington", "Boston", "Nashville", "Detroit",
    "Portland", "Memphis", "Oklahoma City", "Las Vegas", "Louisville",
    "Baltimore", "Milwaukee", "Albuquerque", "Tucson", "Fresno", "Sacramento",
    "Kansas City", "Mesa", "Atlanta", "Omaha", "Colorado Springs", "Raleigh",
    "Miami", "Long Beach", "Virginia Beach", "Oakland", "Minneapolis",
    "Tulsa", "Tampa", "Arlington", "New Orleans", "Wichita", "Cleveland",
    "Bakersfield", "Aurora", "Anaheim", "Honolulu", "Santa Ana", "Riverside",
    "Corpus Christi", "Lexington", "Stockton", "Henderson", "Saint Paul",
    "St. Louis", "Cincinnati", "Pittsburgh", "Greensboro", "Anchorage",
    "Plano", "Lincoln", "Orlando", "Irvine", "Newark", "Toledo", "Durham",
    "Chula Vista", "Fort Wayne", "Jersey City", "St. Petersburg", "Laredo",
    "Madison", "Chandler", "Buffalo", "Lubbock", "Scottsdale", "Reno",
    "Glendale", "Gilbert", "Winston-Salem", "North Las Vegas", "Norfolk",
    "Chesapeake", "Garland", "Irving", "Hialeah", "Fremont", "Boise",
    "Richmond", "Baton Rouge", "Spokane", "Des Moines", "Tacoma", "San Bernardino",
    "Modesto", "Fontana", "Santa Clarita", "Birmingham", "Oxnard", "Fayetteville",
    "Moreno Valley", "Rochester", "Glendale AZ", "Huntington Beach", "Salt Lake City",
    "Grand Rapids", "Amarillo", "Yonkers", "Aurora IL", "Montgomery", "Akron",
    "Little Rock", "Huntsville", "Augusta", "Port St. Lucie", "Grand Prairie",
    "Columbus GA", "Tallahassee", "Overland Park", "Tempe", "McKinney",
    "Mobile", "Cape Coral", "Shreveport", "Frisco", "Knoxville", "Worcester",
    "Brownsville", "Vancouver WA", "Fort Lauderdale", "Sioux Falls", "Ontario",
    "Chattanooga", "Providence", "Newport News", "Rancho Cucamonga", "Santa Rosa",
    "Oceanside", "Salem", "Elk Grove", "Garden Grove", "Pembroke Pines",
    "Peoria", "Eugene", "Corona", "Cary", "Springfield", "Fort Collins",
    "Jackson", "Alexandria", "Hayward", "Lancaster", "Lakewood", "Clarksville",
    "Palmdale", "Salinas", "Springfield MO", "Hollywood", "Pasadena", "Sunnyvale",
    "Macon", "Pomona", "Killeen", "Escondido", "Pasadena TX", "Naperville",
    "Bellevue", "Joliet", "Murfreesboro", "Rockford", "Paterson", "Savannah",
    "Bridgeport", "Torrance", "McAllen", "Syracuse", "Surprise", "Denton",
]


def build_city_pool(k: int, rng: random.Random) -> List[str]:
    if k > len(CITY_NAME_POOL):
        raise ValueError(
            f"Requested city pool size {k} exceeds the {len(CITY_NAME_POOL)} "
            "distinct real city names available; extend CITY_NAME_POOL."
        )
    return rng.sample(CITY_NAME_POOL, k)


def random_date_in_month(month_year_tag: str, rng: random.Random) -> str:
    """Return an ISO date (YYYY-MM-DD) within the generation month, using the
    real current year (the %MM-YY% tag uses a 2-digit year for the path, but
    the record's own `date` field is a full ISO date, so we recover the
    4-digit year from the current date rather than guessing a century)."""
    import datetime
    now = datetime.datetime.now()
    year, month = now.year, now.month
    if month == 2:
        day_max = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
    elif month in (4, 6, 9, 11):
        day_max = 30
    else:
        day_max = 31
    day = rng.randint(1, day_max)
    return f"{year:04d}-{month:02d}-{day:02d}"


def make_clean_record(cities: List[str], month_year_tag: str, rng: random.Random, origin_city: str) -> dict:
    destination = origin_city
    while destination == origin_city:
        destination = rng.choice(cities)
    return {
        "date": random_date_in_month(month_year_tag, rng),
        "origin_city": origin_city,
        "destination_city": destination,
        "flight_duration_secs": rng.randint(MIN_FLIGHT_DURATION_SECS, MAX_FLIGHT_DURATION_SECS),
        "#_of_passengers_on_board": rng.randint(0, MAX_PASSENGERS),
    }


def maybe_make_dirty(record: dict, dirty_prob: float, rng: random.Random) -> Tuple[dict, bool]:
    """With probability `dirty_prob`, null out one or more required fields.

    The number of nulled fields (1 to 2) and which field(s) are chosen
    uniformly at random, independently per record, so the generator itself
    does not bias which field tends to go missing.
    """
    if rng.random() >= dirty_prob:
        return record, False
    record = dict(record)
    n_fields_to_null = rng.choice([1, 1, 1, 2])  # mostly single-field corruption
    fields = rng.sample(REQUIRED_FIELDS, n_fields_to_null)
    for f in fields:
        record[f] = None
    return record, True


def generate(
    output_dir: Path,
    num_files: int,
    k_cities: int,
    dirty_prob: float,
    seed: int,
) -> dict:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    month_year_tag = current_month_year_tag()
    cities = build_city_pool(k_cities, rng)

    month_dir = output_dir / month_year_tag
    month_dir.mkdir(parents=True, exist_ok=True)

    # Spread files as evenly as possible across the city pool: assign each
    # file a "round-robin + shuffled" origin city rather than pure uniform
    # random choice, so that with 5,000 files over up to 200 cities every
    # city gets a comparable number of origin files (uniform random alone
    # can leave some cities with very few files purely by chance).
    origin_sequence = []
    while len(origin_sequence) < num_files:
        batch = cities[:]
        rng.shuffle(batch)
        origin_sequence.extend(batch)
    origin_sequence = origin_sequence[:num_files]

    per_city_seq = {c: 0 for c in cities}
    total_records = 0
    total_dirty = 0
    files_written = []

    for origin_city in origin_sequence:
        per_city_seq[origin_city] += 1
        seq = per_city_seq[origin_city]
        city_slug = origin_city.replace(" ", "_")
        city_dir = month_dir / city_slug
        city_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{month_year_tag}-{city_slug}-{seq:05d}-flights.json"
        filepath = city_dir / filename

        m = rng.randint(RECORDS_PER_FILE_MIN, RECORDS_PER_FILE_MAX)
        records = []
        for _ in range(m):
            rec = make_clean_record(cities, month_year_tag, rng, origin_city)
            rec, is_dirty = maybe_make_dirty(rec, dirty_prob, rng)
            records.append(rec)
            total_dirty += int(is_dirty)
        total_records += m

        with open(filepath, "w") as f:
            json.dump(records, f)
        files_written.append(str(filepath))

    manifest = {
        "num_files": len(files_written),
        "k_cities": k_cities,
        "configured_dirty_probability": dirty_prob,
        "total_records": total_records,
        "total_dirty_records": total_dirty,
        "actual_dirty_fraction": total_dirty / total_records if total_records else 0.0,
        "month_year_tag": month_year_tag,
        "output_dir": str(month_dir),
        "seed": seed,
    }
    with open(output_dir / "generation_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def parse_args():
    p = argparse.ArgumentParser(description="Generate synthetic flight-data JSON files.")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--num-files", type=int, default=TARGET_NUM_FILES)
    p.add_argument("--k-cities", type=int, default=None,
                   help=f"Number of origin cities; random in [{CITY_POOL_MIN},{CITY_POOL_MAX}] if omitted.")
    p.add_argument("--dirty-prob", type=float, default=None,
                   help=f"Per-record dirty probability; random in [{DIRTY_PROB_MIN},{DIRTY_PROB_MAX}] if omitted.")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main():
    args = parse_args()
    seed_rng = random.Random(args.seed)
    k_cities = args.k_cities if args.k_cities is not None else seed_rng.randint(CITY_POOL_MIN, CITY_POOL_MAX)
    dirty_prob = args.dirty_prob if args.dirty_prob is not None else seed_rng.uniform(DIRTY_PROB_MIN, DIRTY_PROB_MAX)

    logger.info(f"Generating {args.num_files} files, K={k_cities} cities, "
                f"L={dirty_prob:.5f} dirty probability, seed={args.seed}")
    t0 = time.perf_counter()
    manifest = generate(args.output_dir, args.num_files, k_cities, dirty_prob, args.seed)
    elapsed = time.perf_counter() - t0
    manifest["generation_runtime_sec"] = elapsed
    with open(args.output_dir / "generation_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"Done in {elapsed:.1f}s. {json.dumps(manifest)}")


if __name__ == "__main__":
    main()
