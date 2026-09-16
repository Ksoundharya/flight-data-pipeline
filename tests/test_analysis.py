import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import is_dirty, validate_clean_record, has_unexpected_fields
from analyze_flights import (
    process_all_files, top_25_destinations, passenger_balance_extremes,
    traffic_concentration, run_validation_suite,
)
from statistics import percentile, wilson_ci, describe, herfindahl_hirschman_index


# ---------------- schema / record-level checks ----------------

def make_record(**overrides):
    base = {
        "date": "2026-09-01",
        "origin_city": "Austin",
        "destination_city": "Denver",
        "flight_duration_secs": 7200,
        "#_of_passengers_on_board": 120,
    }
    base.update(overrides)
    return base


def test_is_dirty_detects_null_field():
    assert is_dirty(make_record(date=None)) is True
    assert is_dirty(make_record()) is False


def test_is_dirty_treats_missing_key_as_dirty():
    rec = make_record()
    del rec["flight_duration_secs"]
    assert is_dirty(rec) is True


def test_validate_clean_record_flags_same_origin_destination():
    ok, reasons = validate_clean_record(make_record(destination_city="Austin"))
    assert ok is False
    assert any("origin_city == destination_city" in r for r in reasons)


def test_validate_clean_record_flags_nonpositive_duration():
    ok, reasons = validate_clean_record(make_record(flight_duration_secs=0))
    assert ok is False


def test_validate_clean_record_flags_negative_passengers():
    ok, reasons = validate_clean_record(make_record(**{"#_of_passengers_on_board": -5}))
    assert ok is False


def test_validate_clean_record_flags_bad_date():
    ok, reasons = validate_clean_record(make_record(date="not-a-date"))
    assert ok is False


def test_validate_clean_record_accepts_well_formed_record():
    ok, reasons = validate_clean_record(make_record())
    assert ok is True
    assert reasons == []


def test_has_unexpected_fields():
    rec = make_record()
    assert has_unexpected_fields(rec) is False
    rec["extra_field"] = "surprise"
    assert has_unexpected_fields(rec) is True


# ---------------- statistics helpers ----------------

def test_percentile_matches_known_values():
    data = sorted([10, 20, 30, 40, 50])
    assert percentile(data, 50) == 30
    assert percentile(data, 0) == 10
    assert percentile(data, 100) == 50


def test_wilson_ci_contains_point_estimate_and_is_ordered():
    lo, hi = wilson_ci(50, 10000)
    assert lo < 50 / 10000 < hi


def test_wilson_ci_narrows_with_more_data():
    lo1, hi1 = wilson_ci(100, 10000)
    lo2, hi2 = wilson_ci(1000, 100000)
    assert (hi2 - lo2) < (hi1 - lo1)


def test_describe_basic_stats():
    d = describe([1, 2, 3, 4, 5])
    assert d["n"] == 5
    assert d["mean"] == 3
    assert d["median"] == 3
    assert d["min"] == 1
    assert d["max"] == 5


def test_hhi_bounds():
    assert herfindahl_hirschman_index([1.0]) == 1.0  # single actor = maximal concentration
    n = 10
    even = herfindahl_hirschman_index([1 / n] * n)
    assert abs(even - 1 / n) < 1e-9


# ---------------- end-to-end analysis over synthetic files ----------------

def write_file(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records))


def test_process_all_files_conservation_and_counts(tmp_path):
    f1 = tmp_path / "a-flights.json"
    f2 = tmp_path / "b-flights.json"
    write_file(f1, [
        make_record(origin_city="A", destination_city="B", **{"#_of_passengers_on_board": 100}),
        make_record(origin_city="B", destination_city="A", **{"#_of_passengers_on_board": 40}),
        make_record(date=None),  # dirty
    ])
    write_file(f2, [
        make_record(origin_city="A", destination_city="C", **{"#_of_passengers_on_board": 10}),
        make_record(origin_city="A", destination_city="A"),  # invalid, not dirty
    ])

    agg = process_all_files([f1, f2])
    assert agg["n_records_processed"] == 5
    assert agg["n_dirty_records"] == 1
    assert agg["n_invalid_but_not_dirty"] == 1
    assert agg["n_valid_records"] == 3

    balance = passenger_balance_extremes(agg)
    assert balance["conservation_invariant_holds"] is True
    # A: -100 (to B) + 40 (from B) - 10 (to C) = -70
    assert agg["passenger_balance"]["A"] == -70
    assert agg["passenger_balance"]["B"] == 60   # +100 - 40
    assert agg["passenger_balance"]["C"] == 10


def test_top_25_ranks_by_passengers_not_flight_count(tmp_path):
    f = tmp_path / "x-flights.json"
    # City "Big" gets 1 flight with huge passenger count; "Small" gets many
    # flights with tiny passenger counts. Ranking must favor "Big".
    records = [make_record(origin_city="Z", destination_city="Big", **{"#_of_passengers_on_board": 900})]
    for _ in range(20):
        records.append(make_record(origin_city="Z", destination_city="Small", **{"#_of_passengers_on_board": 1}))
    write_file(f, records)
    agg = process_all_files([f])
    top25 = top_25_destinations(agg)
    assert top25[0]["destination"] == "Big"
    assert top25[0]["arriving_passengers"] == 900


def test_malformed_json_file_is_quarantined_not_fatal(tmp_path):
    good = tmp_path / "good-flights.json"
    bad = tmp_path / "bad-flights.json"
    write_file(good, [make_record()])
    bad.write_text("{not valid json,,,")
    agg = process_all_files([good, bad])
    assert agg["n_malformed_files"] == 1
    assert agg["n_files_processed"] == 1
    assert agg["n_valid_records"] == 1


def test_validation_suite_flags_out_of_range_manifest():
    agg = {
        "n_malformed_files": 0, "n_unexpected_fields_records": 0,
        "passenger_balance": {"A": 0.0}, "n_dirty_records": 5, "n_records_processed": 1000,
    }
    manifest = {"num_files": 5000, "k_cities": 250, "configured_dirty_probability": 0.005}
    result = run_validation_suite(agg, manifest)
    assert result["city_pool_in_100_200"] is False
    assert result["all_checks_passed"] is False
