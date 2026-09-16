# Flight Data Pipeline

This project builds a realistic synthetic airline traffic dataset, processes it in a memory-safe streaming pipeline, and validates the output with a full analytics and testing workflow.

The goal was to create a reliable data-generation system that could handle a large number of flight records without loading everything into memory, while also making sure the generated data remained valid, traceable, and statistically sound.

## What this project achieved

- Generated 5,000 synthetic JSON flight files across a city pool of 100–200 destinations
- Built a streaming analysis pipeline that processed the data efficiently without holding the full dataset in memory
- Separated dirty data from invalid data so the analytics stayed accurate and trustworthy
- Verified passenger conservation, traffic concentration, and duration statistics against real checks
- Produces a structured output report with final analytics and validation results
- Included a test suite covering generation logic, record validation, deterministic behavior, and edge-case handling

## Why it matters

This was not just a data-generation exercise. The real value was in the engineering discipline behind it:

- making sure file generation did not overwrite unrelated records
- handling malformed and invalid input without breaking the pipeline
- keeping generation deterministic for reproducible results
- validating every key invariant programmatically instead of relying on assumptions

## Results summary

Using the seeded run, the project produced:

- 5,000 generated files
- 376,624 total records
- 2,089 dirty records
- 374,535 clean valid records
- 0 malformed files
- Top destination: Columbus GA with 946,697 arriving passengers
- Passenger balance sums to exactly 0.0 across all cities
- Traffic concentration remains low and consistent with the expected random destination distribution

The full results, methodology, and engineering notes are documented in [FINAL_REPORT.md](FINAL_REPORT.md).

## Project structure

- `generate_flights.py` — creates the synthetic flight files
- `analyze_flights.py` — reads and processes the generated data stream
- `models.py` — validation and record-level checks
- `statistics.py` — percentile, confidence interval, and concentration calculations
- `config.py` — central configuration values
- `tests/` — validation and regression tests
- `outputs/analysis_report.json` — generated analytics output

## How to run it

```bash
python generate_flights.py
python analyze_flights.py
pytest tests/ -q
```

The scripts are designed to run with default settings, and the configuration is centralized in `config.py`.

## Validation

The project includes a passing test suite with 29 checks covering:

- schema validation
- dirty and invalid record handling
- filename uniqueness and collision prevention
- reproducibility across seeded runs
- percentile and Wilson interval calculations
- passenger balance and HHI validation
- malformed-file quarantine behavior

This project is fully public and ready to explore.
