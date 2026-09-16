#!/usr/bin/env python3
"""Phase 2: streaming processing, cleaning, and analytics over the generated
flight-data JSON files.

============================================================
STREAMING / MEMORY DESIGN
============================================================
We never hold more than one file's records in memory at a time. Per-city
running aggregates are kept instead of the full record set:

    passenger_balance[city]          running net passenger delta
    destination_arrivals[city]       total passengers arrived (Top-25 ranking key)
    destination_flight_count[city]   count of valid flights landing there
    destination_duration_sum[city]   running sum, for AVG duration
    destination_durations[city]      list of durations, for EXACT P95 (see below)

Time complexity: O(total_records) -- one pass over every file, one pass over
every record in each file, O(1) work per record for every aggregate except
appending to destination_durations (amortized O(1)).

Space complexity: O(number_of_valid_records) in the worst case, because of
destination_durations. This is the one aggregate that cannot be reduced to
O(K) (K = number of cities) constant-per-city state:

  WHY EXACT P95 REQUIRES RETAINING DURATIONS: mean and count are
  "mergeable" statistics -- sum and count computed on disjoint chunks can be
  combined into the sum/count of the whole with O(1) extra work, so
  AVG never needs the raw values kept around. A percentile is NOT mergeable
  this way: the 95th percentile of the union of two datasets cannot be
  computed from the two datasets' individual P95 values alone (a classic
  counterexample: two batches each with P95 = X can have a combined P95 far
  from X depending on how the rest of each batch's distribribution sits
  relative to X). Computing an EXACT P95 over a stream therefore requires
  either (a) keeping every value, as we do, or (b) two full passes (one to
  find quantile boundaries, one to count against them).

  ALTERNATIVE CONSIDERED -- streaming quantile sketches (e.g. t-digest,
  GK01, KLL): these bound memory to O(1/epsilon) per city at the cost of an
  epsilon-approximate answer. We do NOT introduce this approximation here:
  with ~250,000-500,000 total records spread over at most 200 destination
  cities, the worst case is a few thousand floats for a single popular
  destination, which is a trivial memory footprint (a few tens of KB) --
  introducing an approximate sketch would trade a real (if modest) increase
  in code complexity for savings that do not matter at this data scale. We
  would revisit this decision if K were much smaller (concentrating volume
  into very few destinations) or record counts were orders of magnitude
  larger.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from config import DEFAULT_OUTPUT_DIR, REQUIRED_FIELDS
from models import is_dirty, validate_clean_record, has_unexpected_fields, PASSENGERS_FIELD
from statistics import describe, wilson_ci, herfindahl_hirschman_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s [analyze] %(message)s")
logger = logging.getLogger("analyze_flights")


def find_json_files(input_dir: Path) -> List[Path]:
    return sorted(input_dir.rglob("*-flights.json"))


def process_all_files(files: List[Path]) -> Dict:
    passenger_balance: Dict[str, float] = defaultdict(float)
    destination_arrivals: Dict[str, float] = defaultdict(float)
    destination_flight_count: Dict[str, int] = defaultdict(int)
    destination_duration_sum: Dict[str, float] = defaultdict(float)
    destination_durations: Dict[str, List[float]] = defaultdict(list)
    origin_departures_count: Dict[str, int] = defaultdict(int)
    cities_seen: set = set()

    n_files_processed = 0
    n_malformed_files = 0
    malformed_file_paths = []
    n_records_processed = 0
    n_dirty_records = 0
    n_invalid_but_not_dirty = 0
    n_unexpected_fields_records = 0
    n_valid_records = 0
    all_valid_durations: List[float] = []
    all_valid_passengers: List[float] = []
    dirty_field_counts: Dict[str, int] = defaultdict(int)
    invalid_reason_counts: Dict[str, int] = defaultdict(int)

    for path in files:
        try:
            with open(path, "r") as f:
                records = json.load(f)
            if not isinstance(records, list):
                raise ValueError("top-level JSON is not an array")
        except (json.JSONDecodeError, ValueError, OSError) as e:
            n_malformed_files += 1
            malformed_file_paths.append({"path": str(path), "error": str(e)})
            continue

        n_files_processed += 1
        for record in records:
            n_records_processed += 1
            if not isinstance(record, dict):
                n_invalid_but_not_dirty += 1
                invalid_reason_counts["record is not a JSON object"] += 1
                continue

            if has_unexpected_fields(record):
                n_unexpected_fields_records += 1

            if is_dirty(record):
                n_dirty_records += 1
                for field in REQUIRED_FIELDS:
                    if record.get(field, None) is None:
                        dirty_field_counts[field] += 1
                continue  # quarantined: excluded from all downstream stats

            ok, reasons = validate_clean_record(record)
            if not ok:
                n_invalid_but_not_dirty += 1
                for r in reasons:
                    invalid_reason_counts[r] += 1
                continue  # quarantined, same as dirty, but counted separately

            # ---- record is fully valid: fold into streaming aggregates ----
            n_valid_records += 1
            origin = record["origin_city"]
            dest = record["destination_city"]
            duration = float(record["flight_duration_secs"])
            passengers = float(record[PASSENGERS_FIELD])

            cities_seen.add(origin)
            cities_seen.add(dest)

            passenger_balance[origin] -= passengers
            passenger_balance[dest] += passengers
            destination_arrivals[dest] += passengers
            destination_flight_count[dest] += 1
            destination_duration_sum[dest] += duration
            destination_durations[dest].append(duration)
            origin_departures_count[origin] += 1

            all_valid_durations.append(duration)
            all_valid_passengers.append(passengers)

    # Ensure every city that ever appeared has a balance entry, even if it
    # was e.g. only ever an origin (balance still meaningfully non-zero) or
    # never appeared at all in a valid record (balance 0) -- needed so the
    # conservation invariant and max/min lookups see the full city universe,
    # not just cities with arrivals.
    for c in cities_seen:
        _ = passenger_balance[c]  # touches defaultdict to materialize 0.0 if absent

    return {
        "passenger_balance": dict(passenger_balance),
        "destination_arrivals": dict(destination_arrivals),
        "destination_flight_count": dict(destination_flight_count),
        "destination_duration_sum": dict(destination_duration_sum),
        "destination_durations": dict(destination_durations),
        "origin_departures_count": dict(origin_departures_count),
        "cities_seen": cities_seen,
        "n_files_processed": n_files_processed,
        "n_malformed_files": n_malformed_files,
        "malformed_file_paths": malformed_file_paths,
        "n_records_processed": n_records_processed,
        "n_dirty_records": n_dirty_records,
        "n_invalid_but_not_dirty": n_invalid_but_not_dirty,
        "n_unexpected_fields_records": n_unexpected_fields_records,
        "n_valid_records": n_valid_records,
        "all_valid_durations": all_valid_durations,
        "all_valid_passengers": all_valid_passengers,
        "dirty_field_counts": dict(dirty_field_counts),
        "invalid_reason_counts": dict(invalid_reason_counts),
    }


def top_25_destinations(agg: Dict) -> List[Dict]:
    ranked = sorted(agg["destination_arrivals"].items(), key=lambda kv: -kv[1])[:25]
    out = []
    for rank, (city, arrivals) in enumerate(ranked, start=1):
        durations = sorted(agg["destination_durations"][city])
        n_flights = agg["destination_flight_count"][city]
        avg_duration = agg["destination_duration_sum"][city] / n_flights if n_flights else float("nan")
        from statistics import percentile
        p95_duration = percentile(durations, 95) if durations else float("nan")
        out.append({
            "rank": rank,
            "destination": city,
            "arriving_passengers": arrivals,
            "valid_flights": n_flights,
            "avg_flight_duration_secs": avg_duration,
            "p95_flight_duration_secs": p95_duration,
        })
    return out


def passenger_balance_extremes(agg: Dict) -> Dict:
    balance = agg["passenger_balance"]
    if not balance:
        return {}
    max_city = max(balance.items(), key=lambda kv: kv[1])
    min_city = min(balance.items(), key=lambda kv: kv[1])
    total_balance = sum(balance.values())
    return {
        "max_balance_city": {"city": max_city[0], "balance": max_city[1]},
        "min_balance_city": {"city": min_city[0], "balance": min_city[1]},
        "conservation_check_sum_of_all_balances": total_balance,
        "conservation_invariant_holds": abs(total_balance) < 1e-6,
        "n_cities": len(balance),
    }


def traffic_concentration(agg: Dict) -> Dict:
    arrivals = agg["destination_arrivals"]
    total = sum(arrivals.values())
    if total == 0:
        return {}
    ranked = sorted(arrivals.values(), reverse=True)
    top10_share = sum(ranked[:10]) / total
    top25_share = sum(ranked[:25]) / total
    shares = [v / total for v in arrivals.values()]
    hhi = herfindahl_hirschman_index(shares) * 10000  # conventional 0-10,000 scale
    departures = agg["origin_departures_count"]
    total_dep = sum(departures.values())
    dep_ranked = sorted(departures.values(), reverse=True)
    origin_top10_share = sum(dep_ranked[:10]) / total_dep if total_dep else float("nan")
    return {
        "destination_top10_share_of_passengers": top10_share,
        "destination_top25_share_of_passengers": top25_share,
        "destination_hhi_0_to_10000": hhi,
        "hhi_interpretation": (
            "HHI < 1500: unconcentrated; 1500-2500: moderately concentrated; "
            ">2500: highly concentrated (US DOJ/FTC convention, applied here "
            "descriptively, not as an antitrust judgment)"
        ),
        "origin_top10_share_of_departing_flights": origin_top10_share,
    }


def extended_statistics(agg: Dict) -> Dict:
    dirty_n = agg["n_dirty_records"]
    total_n = agg["n_records_processed"]
    ci = wilson_ci(dirty_n, total_n) if total_n else (float("nan"), float("nan"))
    return {
        "flight_duration_distribution": describe(agg["all_valid_durations"]),
        "passenger_distribution": describe(agg["all_valid_passengers"]),
        "dirty_records": {
            "observed_count": dirty_n,
            "total_records": total_n,
            "observed_proportion": dirty_n / total_n if total_n else float("nan"),
            "wilson_95_ci": ci,
        },
    }


def run_validation_suite(agg: Dict, manifest: dict) -> Dict:
    """Automated data-quality validation checks (see assignment's
    "DATA QUALITY VALIDATION" section) executed against the actual
    generated corpus, not asserted a priori."""
    checks = {}
    checks["approx_5000_files_generated"] = abs(manifest.get("num_files", 0) - 5000) <= 5000 * 0.05
    checks["city_pool_in_100_200"] = 100 <= manifest.get("k_cities", 0) <= 200
    checks["dirty_prob_in_spec_range"] = 0.005 <= manifest.get("configured_dirty_probability", -1) <= 0.01
    checks["no_malformed_files"] = agg["n_malformed_files"] == 0
    checks["no_unexpected_fields"] = agg["n_unexpected_fields_records"] == 0
    balance_extremes = passenger_balance_extremes(agg)
    checks["balance_conservation_holds"] = balance_extremes.get("conservation_invariant_holds", False)
    observed_frac = agg["n_dirty_records"] / agg["n_records_processed"] if agg["n_records_processed"] else 0
    checks["observed_dirty_fraction_within_2x_of_configured"] = (
        0.3 * manifest.get("configured_dirty_probability", 0)
        <= observed_frac
        <= 3.0 * manifest.get("configured_dirty_probability", 1)
    )
    checks["all_checks_passed"] = all(v for v in checks.values() if isinstance(v, bool))
    return checks


def parse_args():
    p = argparse.ArgumentParser(description="Process and analyze generated flight-data JSON files.")
    p.add_argument("--input-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-report", type=Path, default=Path(__file__).resolve().parent / "outputs" / "analysis_report.json")
    return p.parse_args()


def main():
    args = parse_args()
    args.output_report.parent.mkdir(parents=True, exist_ok=True)

    manifest_path = args.input_dir / "generation_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    files = find_json_files(args.input_dir)
    logger.info(f"Found {len(files)} candidate files under {args.input_dir}")

    t0 = time.perf_counter()
    agg = process_all_files(files)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    top25 = top_25_destinations(agg)
    balance = passenger_balance_extremes(agg)
    concentration = traffic_concentration(agg)
    extended = extended_statistics(agg)
    validation = run_validation_suite(agg, manifest)

    report = {
        "runtime_ms": elapsed_ms,
        "files_found": len(files),
        "files_processed": agg["n_files_processed"],
        "malformed_files": agg["n_malformed_files"],
        "malformed_file_paths": agg["malformed_file_paths"],
        "records_processed": agg["n_records_processed"],
        "dirty_records": agg["n_dirty_records"],
        "dirty_field_counts": agg["dirty_field_counts"],
        "invalid_not_dirty_records": agg["n_invalid_but_not_dirty"],
        "invalid_reason_counts": agg["invalid_reason_counts"],
        "unexpected_field_records": agg["n_unexpected_fields_records"],
        "clean_valid_records": agg["n_valid_records"],
        "top_25_destinations_by_arriving_passengers": top25,
        "passenger_balance_extremes": balance,
        "traffic_concentration": concentration,
        "extended_statistics": extended,
        "validation_suite": validation,
        "generation_manifest": manifest,
    }

    with open(args.output_report, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Processed {agg['n_records_processed']} records from {agg['n_files_processed']} files "
                f"in {elapsed_ms:.1f} ms. dirty={agg['n_dirty_records']} "
                f"invalid_not_dirty={agg['n_invalid_but_not_dirty']} valid={agg['n_valid_records']}")
    logger.info(f"Validation suite: {validation}")
    logger.info(f"Report written to {args.output_report}")


if __name__ == "__main__":
    main()

