# Flight Data Pipeline

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![pytest](https://img.shields.io/badge/tests-29%20passing-0A8F5B)
![Status](https://img.shields.io/badge/status-public-success)

A Python project that generates large-scale synthetic flight data, processes it through a streaming pipeline, and validates the results with a careful analytics workflow.

This project was built to solve a practical data-engineering problem: creating realistic data at scale without compromising reliability, reproducibility, or quality. The pipeline processes files efficiently, keeps memory usage low, and verifies key invariants before publishing the results.

## Overview

The project combines data generation, quality validation, and analysis into one end-to-end workflow.

- Creates synthetic flight files across a city pool of 100–200 destinations
- Streams data instead of loading the full dataset into memory
- Separates dirty records from invalid records to preserve analytical integrity
- Checks passenger balance, duration statistics, and traffic concentration
- Produces a reproducible report from a fixed seed
- Includes automated tests covering edge cases and validation logic

## What I implemented

- Robust synthetic flight generation with deterministic seeding
- Safe file naming and collision prevention for large output sets
- Data-quality checks for missing values, impossible values, and malformed records
- Statistical summaries including percentiles and Wilson confidence intervals
- Passenger-flow conservation checks and HHI-based concentration analysis
- A clean, automated validation suite for regression protection

## Skills demonstrated

- Python data processing
- Synthetic data generation
- Data quality validation
- Statistical analysis
- Streaming pipeline design
- Test-driven validation

## Results

The seeded run produced the following outcomes:

- 5,000 generated files
- 376,624 total records
- 2,089 dirty records
- 374,535 clean valid records
- 0 malformed files
- Top destination: Columbus GA with 946,697 arriving passengers
- Passenger balance sums to exactly 0.0 across all cities
- Traffic concentration remains low and consistent with the expected random distribution

The full methodology, engineering decisions, and final analysis are documented in [FINAL_REPORT.md](FINAL_REPORT.md).

## Project structure

- `generate_flights.py` — generates the synthetic flight records
- `analyze_flights.py` — reads and processes the generated data stream
- `models.py` — record validation and quality checks
- `statistics.py` — percentiles, confidence intervals, and concentration metrics
- `config.py` — central configuration values
- `tests/` — validation and regression tests
- `outputs/analysis_report.json` — generated analytics report

## Run it locally

```bash
python generate_flights.py
python analyze_flights.py
pytest tests/ -q
```

## Validation

This project includes 29 passing tests covering:

- schema validation
- dirty and invalid record handling
- filename uniqueness and collision prevention
- reproducibility across seeded runs
- percentile and confidence-interval logic
- passenger-balance and HHI checks
- malformed-file quarantine behavior

This project is public, reproducible, and ready to explore.
