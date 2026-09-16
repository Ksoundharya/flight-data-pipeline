import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from generate_flights import (
    build_city_pool, make_clean_record, maybe_make_dirty, generate,
    random_date_in_month, CITY_NAME_POOL,
)
from config import REQUIRED_FIELDS, current_month_year_tag
import random


def test_build_city_pool_size_and_uniqueness():
    rng = random.Random(1)
    pool = build_city_pool(150, rng)
    assert len(pool) == 150
    assert len(set(pool)) == 150


def test_build_city_pool_rejects_oversized_request():
    rng = random.Random(1)
    with pytest.raises(ValueError):
        build_city_pool(len(CITY_NAME_POOL) + 1, rng)


def test_clean_record_has_all_required_fields():
    rng = random.Random(2)
    cities = build_city_pool(120, rng)
    rec = make_clean_record(cities, current_month_year_tag(), rng, cities[0])
    assert set(rec.keys()) == set(REQUIRED_FIELDS)


def test_clean_record_origin_never_equals_destination():
    rng = random.Random(3)
    cities = build_city_pool(120, rng)
    for _ in range(500):
        rec = make_clean_record(cities, current_month_year_tag(), rng, cities[0])
        assert rec["origin_city"] != rec["destination_city"]


def test_clean_record_bounds():
    rng = random.Random(4)
    cities = build_city_pool(120, rng)
    from config import MIN_FLIGHT_DURATION_SECS, MAX_FLIGHT_DURATION_SECS, MAX_PASSENGERS
    for _ in range(500):
        rec = make_clean_record(cities, current_month_year_tag(), rng, cities[0])
        assert MIN_FLIGHT_DURATION_SECS <= rec["flight_duration_secs"] <= MAX_FLIGHT_DURATION_SECS
        assert 0 <= rec["#_of_passengers_on_board"] <= MAX_PASSENGERS
        assert rec["flight_duration_secs"] > 0


def test_random_date_is_valid_iso_and_in_current_month():
    import datetime
    rng = random.Random(5)
    tag = current_month_year_tag()
    now = datetime.datetime.now()
    for _ in range(200):
        d = random_date_in_month(tag, rng)
        parsed = datetime.date.fromisoformat(d)
        assert parsed.year == now.year
        assert parsed.month == now.month


def test_dirty_probability_configuration_at_extremes():
    rng = random.Random(6)
    cities = build_city_pool(120, rng)
    rec = make_clean_record(cities, current_month_year_tag(), rng, cities[0])

    rec0, dirty0 = maybe_make_dirty(rec, 0.0, random.Random(7))
    assert dirty0 is False
    assert rec0 == rec

    rec1, dirty1 = maybe_make_dirty(rec, 1.0, random.Random(8))
    assert dirty1 is True
    assert any(v is None for v in rec1.values())


def test_dirty_record_only_nulls_required_fields():
    rng = random.Random(9)
    cities = build_city_pool(120, rng)
    rec = make_clean_record(cities, current_month_year_tag(), rng, cities[0])
    dirty_rec, was_dirty = maybe_make_dirty(rec, 1.0, random.Random(10))
    nulled = [k for k, v in dirty_rec.items() if v is None]
    assert 1 <= len(nulled) <= 2
    assert all(k in REQUIRED_FIELDS for k in nulled)


def test_filename_uniqueness_no_overwrites(tmp_path):
    manifest = generate(tmp_path, num_files=400, k_cities=100, dirty_prob=0.007, seed=11)
    files = list(tmp_path.rglob("*-flights.json"))
    assert len(files) == manifest["num_files"] == 400
    # uniqueness: no two files share a path (guaranteed by filesystem, but
    # also verify no filename string collides across different directories)
    names = [f.name for f in files]
    assert len(names) == len(set(names))


def test_records_per_file_within_spec(tmp_path):
    from config import RECORDS_PER_FILE_MIN, RECORDS_PER_FILE_MAX
    generate(tmp_path, num_files=60, k_cities=100, dirty_prob=0.007, seed=12)
    for f in tmp_path.rglob("*-flights.json"):
        records = json.loads(f.read_text())
        assert RECORDS_PER_FILE_MIN <= len(records) <= RECORDS_PER_FILE_MAX


def test_deterministic_seed_reproducibility(tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    m1 = generate(out1, num_files=50, k_cities=110, dirty_prob=0.006, seed=99)
    m2 = generate(out2, num_files=50, k_cities=110, dirty_prob=0.006, seed=99)
    assert m1["total_records"] == m2["total_records"]
    assert m1["total_dirty_records"] == m2["total_dirty_records"]

    files1 = sorted(p.relative_to(out1) for p in out1.rglob("*-flights.json"))
    files2 = sorted(p.relative_to(out2) for p in out2.rglob("*-flights.json"))
    assert [str(f) for f in files1] == [str(f) for f in files2]
    for f1, f2 in zip(files1, files2):
        assert json.loads((out1 / f1).read_text()) == json.loads((out2 / f2).read_text())


def test_manifest_dirty_fraction_close_to_configured(tmp_path):
    manifest = generate(tmp_path, num_files=2000, k_cities=150, dirty_prob=0.01, seed=13)
    observed = manifest["total_dirty_records"] / manifest["total_records"]
    # With ~150,000+ records at p=0.01, the binomial standard error is tiny;
    # allow a generous 30% relative tolerance to avoid test flakiness while
    # still catching a badly broken dirty-injection implementation.
    assert abs(observed - 0.01) / 0.01 < 0.3
