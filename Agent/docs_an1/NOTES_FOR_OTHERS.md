# Grain notes for P3

The current pipeline sets analyst `time_grain` in `src/orchestrator.py` to
`week` for anomaly routes and `month` otherwise. The metric registry defaults
are `week` for orders and `month` for revenue. `src/sql/compiler.py` also
recognizes `weekly`, `monthly`, `last_year`, `2018`, and `2017` as time-window
inputs, but normalizes them to week/month SQL; it does not produce quarter or
year from those aliases. The analyst fetchers additionally support DuckDB
`quarter` and `year` grains because legacy callers can supply those values.

Other observed grain values: `day` is supported by the temporary fetcher;
`decade` and injection-like strings are rejected by the legacy wrappers as
insufficient evidence.
