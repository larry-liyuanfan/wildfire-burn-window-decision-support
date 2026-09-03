# Burn-ID climatology contract

This workflow closes the spatial-level gap between the existing district
screen and the 176 official Murray Goldfields burn IDs. Restricted VicClim6
and workbook inputs remain in the authorised `punim1257/Group44` project. Only
compact, redacted evidence may leave that boundary.

## Metric definition

The prescription is evaluated at each source grid cell before spatial
aggregation. The selected class must compile to exactly eight conditions with
no unresolved or unmapped values after enabling the explicit FMC and
fuel-level-wind proxies.

For burn ID `b`, grid cell `g`, and hour `t`:

```text
w[b,g] = overlap_hectares[b,g] / sum_g(overlap_hectares[b,g])
weighted_suitable_area_fraction[b,t] = sum_g(w[b,g] * suitable[g,t])
```

Only the 351 non-zero polygon/grid intersections are represented. The weights
must sum to `1±1e-6` for every burn ID. Zero polygon coverage is a quality
failure; nearest-cell substitution is forbidden.

An hour is valid for a burn ID only when all eight condition inputs are valid
across its entire non-zero weighted area. The continuous hourly fraction is
stored in a restricted compressed annual artifact. The compact artifact keeps
the annual mean/minimum/median/maximum and the valid-hour count.

The `0.5`, `0.8`, and `1.0` cutoffs do not redefine the continuous metric.
They are descriptive sensitivity views. For each cutoff, 2-, 4-, and 6-hour
counts mean maximal continuous segments meeting at least that duration, not
rolling-window endpoints.

The limiting factor is the condition with the largest area-weighted failure
total over cell-hours where all eight inputs are valid. It is descriptive and
does not imply causality.

## Annual record schema

Every burn-ID/year record contains:

- official `burn_id` and `year`;
- `metric_hours` and `valid_hours`;
- the continuous `weighted_suitable_area_fraction` summary;
- descriptive `threshold_sensitivity`, including 2/4/6-hour segment counts;
- one `limiting_factor` with its weighted failure fraction;
- `data_sha256`, `rule_sha256`, `spatial_sha256`, and exact Git SHA;
- warnings, including the precipitation-unavailable rain-guard warning.

Aggregation rejects missing or duplicate years, missing or duplicate
burn-ID/year pairs, changed burn-ID coverage, mixed SHA contracts, failed
annual gates, missing rain-guard warnings, or any record that does not match
the compact schema.

## Read-only tool

`get_burn_unit_climatology` accepts an allowlisted artifact ID, optional burn
IDs, and an optional year range. The service operator supplies a catalog whose
artifact file is hash-pinned at startup. Callers cannot supply a filesystem
path, expression, weather array, rule override, or recomputation request.

The tool returns only precomputed annual records and the artifact's publication
boundary. Unknown artifact IDs fail closed. Unknown burn IDs are omitted with
an explicit partial-result warning.

## Spartan order

The production sequence is:

1. `sbatch --test-only` for the preflight request;
2. metadata/rule/spatial preflight;
3. 2020 sparse pilot;
4. independent 2020 per-burn direct recomputation comparison;
5. 1973–2023 annual array;
6. `afterok` compact aggregation;
7. `afterok` compact publication and service smoke test.

Annual tasks checkpoint independently. Infrastructure failures may be retried
at most twice with the identical commit and configuration. Quality failures
write `quality_failure.json` and are not automatically retried or hidden.

## Truth boundary

FMC is a dry-fuel meteorological model ensemble, and fuel-level wind is a
declared reduction-factor proxy. They are not field measurements. VicClim6 has
no precipitation field, so the FMC rain guard cannot be applied and the
warning must remain visible. The climatology and its threshold sensitivities
are not operational approval, safety evidence, causal risk reduction, observed
field outcomes, savings, or return on investment.
