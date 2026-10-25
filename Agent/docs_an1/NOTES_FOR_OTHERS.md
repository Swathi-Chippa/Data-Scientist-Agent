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

## P4 anomaly compatibility notes

Compared with commit `65262dc`, the legacy Anomaly wrapper now fetches all
states once and selects the requested target in the pure core. The temporary
Olist window starts at `2017-01-16`, the first observed SP week after which
weekly volume remains at least 30; this is temporary, Olist-specific.

Legacy verdict changes:

- The successful verdict strings `Statistically Unusual Anomaly Confirmed`
  and `Within Normal Historical Variation` remain.
- `Insufficient history` and `Volume guard triggered` are no longer emitted
  as verdict strings; insufficient results have an empty verdict and put the
  reason in the summary/caveat path.
- `Data Quality Issue Suspected` is now possible when the pure DQ gate finds a
  severe failure.

Legacy output field changes:

- Metrics retain `region`, `metric`, and `median_baseline`; they now also
  expose computed `expected`, `actual`, `deviation_pct`, `expected_range`,
  `robust_score`, `history_periods_used`, `peer_rank`, `correction_used`,
  `persistence`, `change_point`, and `data_quality`.
- The old `lower_bound_95`, `upper_bound_95`, `anomalies_count`,
  `is_sustained_level_shift`, and `fdr_alpha` metrics are not emitted.
- The time-series table now contains the fetched contract rows rather than
  the old per-row `actual`, `expected`, `lower_bound`, `upper_bound`, and
  `is_anomaly` table.
- Evidence claims are generated from the V2 computed fields and can be empty
  for insufficient evidence; the old fixed two-claim layout is not retained.
- Freshness is now `unknown` but non-severe for the static Olist dataset; the
  pure DQ gate receives an explicit `as_of` timestamp and does not read the
  clock.

The orchestrator does not branch on these metric or table fields. It stores
the full model dump under `anomaly_output`, uses the legacy `verdict` for a
step note, and passes the context to later analysts/advisor. The field names
above are therefore not directly read by `src/orchestrator.py`.

### P4 interval decision

The calibrated anomaly interval is now C5 with `k=1.05`: one 3.5-MAD-sigma
screen on log1p history followed by a screened Student-t prediction interval.
It is used for every baseline with at least 10 events; the former separate
count-interval branch is removed. The volume guard for fewer than 10 events is
unchanged. The implementation also records the Sidak/consecutive window route
and the history periods removed by the screen in flags; the legacy summary
renders those computed period names.

### P4 verdict and interval consistency

`expected_range` is the unchanged interval used by the decision. It is no
longer widened to contain a normal actual or narrowed to force an unusual
actual outside the interval. Verdicts therefore agree with the interval
validator: unusual means the actual is outside the reported interval, while
within-normal means it is inside.

For an explicitly requested single unit, the unit's own interval and window
rule determine the verdict; Benjamini-Hochberg correction is not applied.
`correction_used` is reported as `not applied: single unit requested`, while
peer multiplicity remains available through the peer-rank sentence. BH remains
available for multi-unit scans. The window route is `none` for within-normal or
insufficient results; a non-`none` route corresponds to an unusual result or a
severe data-quality result.
