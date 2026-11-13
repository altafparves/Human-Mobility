"""
Role 1: Temporal Cleaning & Coverage Audit Lead (Bronze -> Silver Layer)
------------------------------------------------------------------------
Responsibilities:
- Parse dates and standardize timestamps to WIB (UTC+7).
- Flag anomalous dates (e.g., 2022-03-08) and define sampling periods.
- Build full expected cell-date calendar and calculate weekday/weekend publication coverage.
- Apply >= 90% coverage filter (with 80% and 95% sensitivity flags) and export Silver Parquet tables.
"""

