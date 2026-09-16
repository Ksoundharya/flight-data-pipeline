# Task 2 Final Report — Flight Data Generation, Cleaning & Analytics

This is the detailed engineering report for Task 2 only: the requirement
traceability matrix, the full reasoning behind each non-obvious design
decision, the final quality-gate self-audit, and every number from the
actual generated run. `README.md` is the short entry point; this file is
where the "why" lives.

## Executive summary

Generated exactly 5,000 JSON flight-data files (376,624 records, K=181
cities, configured dirty probability 0.5557%) under a documented,
collision-free folder hierarchy, streamed them through a cleaning/analysis
pipeline in 1,428.8 ms without holding more than one file's records in
memory at a time, and verified every required invariant
programmatically — the Top-25-by-arriving-passengers ranking, exact
AVG/P95 flight duration, and the passenger-balance conservation invariant
(Σ balances = 0, exactly). All 29 automated tests pass.

## Requirement Traceability Matrix

| Req ID | Original Requirement | Interpretation | Implementation | Validation | Artifact | Status |
|---|---|---|---|---|---|---|
| T2-1 | ~5,000 JSON files, structured hierarchy | Exactly 5,000; nested by month-year/city | `generate_flights.py::generate` | File count assertion in validation suite | `/tmp/flights/`, `generation_manifest.json` | DONE |
| T2-2 | K cities in [100,200], M records/file in [50,100] | Randomized within spec, seeded | `config.py`, `generate_flights.py` | Range checks in tests + validation suite | `tests/test_generator.py`, `outputs/analysis_report.json` | DONE |
| T2-3 | Filename pattern with MM-YY/origin_city | Analyze collision risk explicitly, resolve safely | Sequence-numbered, city-nested filenames | Uniqueness test on 400 generated files | `generate_flights.py` module docstring | DONE (documented deviation, justified) |
| T2-4 | Dirty records at L∈[0.5%,1%], NULL fields | Independent per-record Bernoulli injection | `maybe_make_dirty` | Observed fraction + Wilson CI checked against configured L | `outputs/analysis_report.json` | DONE |
| T2-5 | Process all files, identify/clean dirty records | Quarantine policy, not imputation | `analyze_flights.py::process_all_files` | Dirty/invalid/valid counts reconciled to total | `outputs/analysis_report.json` | DONE |
| T2-6 | Report counts + runtime in ms | `time.perf_counter` around timed section | `analyze_flights.py::main` | Real measured runtime | `outputs/analysis_report.json` | DONE |
| T2-7 | Streaming architecture, no full in-memory load | Per-file streaming, O(cities) aggregates + justified exception for exact P95 | `analyze_flights.py` | Complexity analysis in module docstring | `analyze_flights.py` | DONE |
| T2-8 | Top 25 by arriving passengers, AVG/P95 duration | Explicit ranking key, percentile definition documented | `top_25_destinations` | Unit test with constructed counterexample (passengers≠flight-count ranking) | `tests/test_analysis.py::test_top_25_ranks_by_passengers_not_flight_count` | DONE |
| T2-9 | Passenger balance, max/min city | 0-initialized, updated per valid flight | `passenger_balance_extremes` | Hand-computed 3-city unit test | `tests/test_analysis.py::test_process_all_files_conservation_and_counts` | DONE |
| T2-10 | Conservation invariant, investigate if it fails | Automated check, not asserted a priori | `run_validation_suite` | Executed on real 374,535-record run: holds exactly | `outputs/analysis_report.json` | DONE |
| T2-11 | Data quality validation suite | File count, schema, ranges, ranking correctness, balance | `run_validation_suite` + full test suite | 29 automated tests, all pass; validation suite all-pass on real run | `tests/`, `outputs/analysis_report.json` | DONE |
| T2-12 | Extended statistics (mean/median/stdev/IQR/percentiles/skew/CV, dirty-rate Wilson CI, concentration/HHI) | Dependency-free stats module | `statistics.py`, `extended_statistics`, `traffic_concentration` | Computed on real data; unit-tested against hand-computed cases | `outputs/analysis_report.json`, `tests/test_analysis.py` | DONE |
| T2-13 | Automated tests incl. edge cases | Generator + analysis test suites | `tests/test_generator.py`, `tests/test_analysis.py` | 29/29 pass | `tests/` | DONE |
| T2-14 | Python 3.7+ compatible, stdlib-first | No 3.8+-only syntax, no unneeded deps | Checked via `ast.parse`; only `pytest` as a dev dependency | Manual grep for `:=`/`match` + AST parse | this file | DONE |
| T2-15 | Failure handling: malformed JSON, missing/wrong-type fields | try/except per file, per-field type checks | `process_all_files`, `models.py::validate_clean_record` | Unit test with deliberately corrupt JSON file | `tests/test_analysis.py::test_malformed_json_file_is_quarantined_not_fatal` | DONE |
| T2-16 | Reproducibility, deterministic seed | Same seed → byte-identical output | `random.Random(seed)`, no shared global state | Unit test comparing two seeded runs' files byte-for-byte | `tests/test_generator.py::test_deterministic_seed_reproducibility` | DONE |

## Filename-collision finding (documented, not silently patched)

The spec's required path template, `/tmp/flights/%MM-YY%-%origin_city%-flights.json`,
has at most K ≤ 200 distinct values per run because "current month and year"
is evaluated once per run, not once per file. Requesting ~5,000 files against
≤200 possible names guarantees collisions (pigeonhole: ≥25 files per name on
average) if implemented literally — this would silently overwrite files.

**Resolution implemented** (`generate_flights.py`, see its module docstring
for the full reasoning): a per-(month-year, origin-city) zero-padded
sequence number is inserted before the suffix, and files are nested one
directory per origin city under the month-year directory, giving:

```
/tmp/flights/<MM-YY>/<origin_city>/<MM-YY>-<origin_city>-<00001..NNNNN>-flights.json
```

This preserves every component the naming requirement asked for
(month-year prefix, origin city, `-flights.json` suffix) while guaranteeing
no two files ever collide, and keeps any single directory listing bounded
to roughly `num_files / k_cities` entries (about 25-50 in a 5,000-file /
150-200-city run) instead of one flat directory of 5,000 files.

## Dirty-record policy

A record is **dirty** if any of its 5 required fields is `null` or missing.
Dirty records are **quarantined, not imputed**: they are counted (globally
and per-field) but excluded from every downstream aggregate. We chose
exclusion over imputation because imputing, say, a missing
`#_of_passengers_on_board` with a mean/median would fabricate a number that
directly feeds the passenger-balance conservation invariant and the Top-25
ranking — silently distorting exactly the two calculations the assignment
asks us to get right. A record with non-null but semantically impossible
values (e.g. `origin_city == destination_city`, a non-positive duration) is
a **separate, second quarantine category** we call "invalid" — the
assignment's own dirty-record definition (NULL-valued fields) does not
cover it, but leaving such records in the valid pool would be just as
distorting, so it is excluded and reported separately rather than silently
merged into either bucket. In the actual generated corpus this category is
empty (0 records) because the generator does not currently produce that
failure mode independent of the null-injection path — the validator and
its tests (`test_validate_clean_record_flags_*`) exist and are exercised
regardless, so the pipeline is defended against upstream data that does
exhibit it.

## Streaming architecture

See the module docstring in `analyze_flights.py` for the full memory/time
complexity analysis. In one sentence: the pipeline never materializes more
than one file's records at a time, keeps O(#cities) running aggregates for
everything that is mathematically "mergeable" (sums, counts), and keeps
O(#valid records) raw duration values only for the one aggregate that
cannot be computed exactly without them — the P95 percentile — because
percentiles are not mergeable across chunks the way sums/counts are. At
this dataset's scale (hundreds of thousands of records over ≤200
destinations) that is at most a few thousand floats per city, which we
judged not worth trading for an approximate quantile sketch (t-digest/GK01)
that would add real code complexity for no measurable benefit here.

## Results from the actual generated run (seed=42)

```
K (cities)              : 181
Configured dirty prob L : 0.005557
Files generated         : 5,000
Total records           : 376,624
Generation runtime      : 2.7s
Analysis runtime        : 1,428.8 ms   (time.perf_counter, timed section = process_all_files)
Dirty records           : 2,089  (0.5547% observed; 95% Wilson CI [0.5314%, 0.5789%], contains L)
Invalid-not-dirty       : 0
Clean valid records     : 374,535
Malformed files         : 0
```

**Top 5 of 25 destinations by total arriving passengers** (ranked by
passengers, not flight count or duration — see `top_25_destinations()`):

| Rank | Destination | Arriving passengers | Valid flights | AVG duration (s) | P95 duration (s) |
|---:|---|---:|---:|---:|---:|
| 1 | Columbus GA | 946,697 | 2,184 | 37,079 | 68,853 |
| 2 | San Jose | 930,887 | 2,203 | 36,749 | 68,272 |
| 3 | Henderson | 926,954 | 2,227 | 36,077 | 67,797 |
| 4 | Oxnard | 923,107 | 2,180 | 37,358 | 68,613 |
| 5 | Gilbert | 923,065 | 2,145 | 36,754 | 68,666 |

(Full 25-row table in `outputs/analysis_report.json` →
`top_25_destinations_by_arriving_passengers`.) Percentile definition: linear
interpolation between order statistics (NumPy's default `"linear"` method),
implemented in `statistics.py::percentile`, applied to the exact sorted list
of that destination's valid flight durations.

**Passenger balance** (every city starts at 0; `balance[origin] -= passengers`,
`balance[destination] += passengers`, over all 374,535 valid flights):

| | City | Balance |
|---|---|---:|
| Maximum | Columbus GA | +144,609 |
| Minimum | Wichita | −139,144 |

**Conservation invariant**: `sum(balance.values()) == 0.0` — holds exactly
(verified programmatically in `run_validation_suite`, not asserted by
inspection). This must hold for any closed accounting of transfers because
every valid flight's passenger count is added to exactly one city's balance
and subtracted from exactly one other city's balance, so the grand total
change over all flights is a telescoping sum of `(+p - p)` terms that
cancels to zero regardless of how the flights are distributed across
cities.

**Traffic concentration:** Top-10 destinations hold 5.81% of all arriving
passengers, Top-25 hold 14.37%, HHI = 55.3 (out of 10,000) — i.e. traffic is
essentially unconcentrated. This is the expected and correct signature of a
uniform-random destination generator over ~181 cities, not a finding about
real-world air-traffic concentration; it is reported here as a sanity check
on the generator's own uniformity as much as a descriptive statistic.

## Data quality validation suite (`run_validation_suite`, executed, not asserted)

| Check | Result |
|---|---|
| ~5,000 files generated (within 5%) | PASS |
| City pool K in [100, 200] | PASS (K=181) |
| Dirty probability L in [0.5%, 1%] | PASS (L=0.5557%) |
| No malformed files | PASS |
| No unexpected fields in any record | PASS |
| Passenger-balance conservation (Σbalance = 0) | PASS |
| Observed dirty fraction within 3x of configured L | PASS |
| **All checks passed** | **PASS** |

## Testing

29 automated tests across `tests/test_generator.py` (city-pool sizing,
record schema/bounds, origin≠destination, dirty-probability behavior at
p=0 and p=1, filename uniqueness under 400 generated files, records-per-file
bounds, deterministic-seed byte-for-byte reproducibility, dirty-fraction
convergence) and `tests/test_analysis.py` (dirty/invalid record
classification, percentile/Wilson-CI/HHI correctness on hand-computed
cases, an end-to-end 5-record conservation check with a known expected
balance per city, Top-25-by-passengers-not-flight-count on a constructed
counterexample, and malformed-JSON-file isolation). All 29 pass
(`pytest tests/ -v`).

## Final Quality Gate — self-audit against the assignment's checklist (Task 2 items)

- [x] Approximately 5,000 JSON files generated — exactly 5,000.
- [x] 50–100 records/file — enforced by generator, unit-tested.
- [x] 100–200 cities — K=181 in the real run.
- [x] 0.5–1% dirty probability — configured L=0.5557%, observed 0.5547% (Wilson CI contains L).
- [x] Required JSON schema followed — exact field names/types per spec.
- [x] Total records reported — 376,624.
- [x] Dirty records reported — 2,089, plus per-field breakdown.
- [x] Analysis runtime reported in milliseconds — 1,428.8 ms via `time.perf_counter`.
- [x] Top 25 ranked by arriving PASSENGERS — verified with a constructed counterexample unit test, not just by inspection.
- [x] AVG duration calculated — per destination, real data.
- [x] P95 duration calculated — exact (not approximated), with the reasoning for exactness documented.
- [x] Maximum passenger-balance city reported — Columbus GA, +144,609.
- [x] Minimum passenger-balance city reported — Wichita, −139,144.
- [x] Global passenger balance = 0 — verified exactly (0.0), not approximately.
- [x] Unit tests pass — 29/29 (`tests/`).
- [x] Python 3.7 compatibility checked — AST-parsed, no 3.8+-only syntax, stdlib-only runtime (`requirements.txt` has `pytest` as the only, dev-only, dependency).
- [x] README contains reproducible commands — see `README.md`.
- [x] No fabricated numbers/results — every number above was produced by a real execution captured during development, not hand-typed.
- [x] Filename-collision risk documented and resolved rather than silently patched — see above.

## Known limitations

* The generator draws destinations uniformly at random from the city pool,
  which is why the concentration metrics above show an unconcentrated
  network — a real airline route network is not uniform (hub-and-spoke
  concentration is the norm). This is a property of the synthetic
  generator, not a bug; it was not asked to model real route topology.
* Subgroup/error-slicing analysis (as in Task 1) was not requested for
  Task 2 and is not included; the Extended Analysis section in
  `outputs/analysis_report.json` covers the specific statistics the
  assignment lists (mean/median/stdev/variance/IQR/P5-P99/skew/CV on
  duration and passenger distributions, dirty-rate Wilson CI, traffic
  concentration).
