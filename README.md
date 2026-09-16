# Task 2 — Flight Data Generation, Cleaning, and Analytics

Generates ~5,000 synthetic flight-record JSON files across a pool of
100-200 cities, then streams through them (never loading the full corpus
into memory) to produce cleaned analytics: Top-25 destinations by arriving
passengers, per-destination duration percentiles, a passenger-balance
conservation check, dirty/invalid record quarantine with a Wilson
confidence interval on the dirty rate, and a traffic-concentration (HHI)
summary.

For the full engineering reasoning — the filename-collision analysis, the
dirty-vs-invalid quarantine rationale, the streaming/complexity analysis,
every number from the actual generated run, the validation-suite results,
and the requirement traceability matrix — see **`FINAL_REPORT.md`**. This
file is just the short entry point.

## Key advanced work

* **Filename-collision fix, not a workaround**: the spec's literal path
  template only has ≤200 distinct values per run, which pigeonholes into
  guaranteed overwrites at 5,000 files. Resolved with a documented
  per-(month-year, city) sequence number and one subdirectory per city,
  preserving every required path component while making collisions
  impossible. See `generate_flights.py`'s module docstring and
  `FINAL_REPORT.md` for the full write-up.
* **Streaming, single-pass analysis**: `analyze_flights.py` never holds
  more than one file's records in memory; only the one metric that can't
  be computed exactly without raw values (P95 duration) retains a
  per-city list, everything else is an O(#cities) running aggregate.
* **Dirty vs. invalid, quarantined separately**: null/missing required
  fields ("dirty") and non-null-but-impossible values ("invalid", e.g.
  same origin/destination) are excluded from analytics and reported
  separately, rather than imputed or silently merged — imputing would
  distort the exact conservation and ranking checks below.
* **Exactly-verified invariants**: global passenger balance sums to
  `0.0` exactly (not "close to zero"), checked programmatically by
  `run_validation_suite`, not just asserted by inspection.
* **Deterministic generation**: seeded `random.Random` instances (no
  shared global state) give byte-for-byte reproducible runs.
* **29 passing tests** covering schema/bounds validation, dirty-rate
  behavior at the p=0/p=1 edges, filename uniqueness, deterministic-seed
  reproducibility, percentile/Wilson-CI/HHI correctness against
  hand-computed cases, and malformed-file isolation.

## Results snapshot (seed=42, actual run)

```
Files generated     : 5,000        Total records    : 376,624
Dirty records       : 2,089 (0.5547%, 95% CI [0.5314%, 0.5789%])
Clean valid records : 374,535      Malformed files  : 0
Top destination     : Columbus GA (946,697 arriving passengers)
Passenger balance   : sums to 0.0 exactly across all 181 cities
Traffic HHI         : 55.3 / 10,000 (essentially unconcentrated, as
                       expected from a uniform-random destination draw)
```

Full tables and every other number are in `FINAL_REPORT.md` and
`outputs/analysis_report.json`.

## Setup and reproduction

Only the Python 3.7+ standard library is used at runtime — no third-party
dependency (`pytest` is dev/test-only).

```bash
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install pytest                                    # only needed for tests

python3 generate_flights.py \
    --output-dir /tmp/flights \
    --num-files 5000 \
    --seed 42

python3 analyze_flights.py \
    --input-dir /tmp/flights \
    --output-report outputs/analysis_report.json

pytest tests/ -v
```

Both scripts default to these values, so `python3 generate_flights.py`
and `python3 analyze_flights.py` alone reproduce the run above.
`config.py` centralizes every tunable constant.
