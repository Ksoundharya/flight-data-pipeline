# Flight Data Pipeline

A Python project that generates large-scale synthetic flight data, processes it in a streaming pipeline, and verifies the results with a strong validation and analytics workflow.

This project was designed to solve a real engineering problem: building a dataset that was large enough to feel realistic, but careful enough to remain clean, deterministic, and trustworthy. Instead of loading everything into memory, the pipeline streams through files and computes summary metrics efficiently while keeping the data quality checks strict.

## What I built

- Synthetic flight-data generation across a large city pool
- Streaming analysis for large-scale data processing
- Validation of record integrity and dirty vs invalid data handling
- Passenger-balance and traffic-concentration checks
- Reproducible seeded output for consistent testing and reporting
- A full automated test suite to verify correctness

## Why this project is useful

The value here is not only in generating data, but in how the pipeline is engineered:

- filenames are handled safely to avoid collisions
- malformed files are isolated instead of crashing the pipeline
- invalid records are separated from dirty records for accurate analysis
- summary metrics are validated with exact checks rather than rough approximations
- the system remains reproducible from a fixed seed

## Results achieved

The seeded run produced the following outcomes:

- 5,000 generated files
- 376,624 total records
- 2,089 dirty records
- 374,535 clean valid records
- 0 malformed files
- Top destination: Columbus GA with 946,697 arriving passengers
- Passenger balance sums to exactly 0.0 across all cities
- Traffic concentration remains low and consistent with the expected random distribution

The full engineering notes, validation details, and final analysis can be found in [FINAL_REPORT.md](FINAL_REPORT.md).

## Project structure

- `generate_flights.py` — generates the synthetic flight records
- `analyze_flights.py` — processes the generated data stream
- `models.py` — record validation and data-quality checks
- `statistics.py` — percentiles, confidence intervals, and concentration metrics
- `config.py` — central configuration and constants
- `tests/` — automated checks and regression tests
- `outputs/analysis_report.json` — generated output report

## How to run

```bash
python generate_flights.py
python analyze_flights.py
pytest tests/ -q
```

The project is set up to run with default configuration values, and the logic stays centralized in `config.py`.

## Validation summary

The project includes 29 passing tests covering:

- schema validation
- dirty and invalid record handling
- filename uniqueness and collision prevention
- deterministic generation across seeded runs
- percentile and Wilson confidence interval checks
- passenger-balance and HHI validation
- malformed-file quarantine behavior

This is a clean, reproducible, and public-ready data engineering project.
