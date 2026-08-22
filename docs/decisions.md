# Decision log

| ID | Decision | Reason | Consequence |
|---|---|---|---|
| D001 | Treat the project as an Agent-callable deterministic tool layer | Domain rules and schedules must remain auditable | LLM planning is outside the calculation trust boundary |
| D002 | Compile every source value or mark it unresolved | Silent omission would create unsafe false confidence | Partial prescriptions return warnings |
| D003 | Preserve `<` versus `<=`; ranges are inclusive by default | Boundary choice changes suitability counts | Assumption is test-covered and visible in the AST |
| D004 | Use a 24-hour default availability lag for date-labelled daily aggregates | Same-day fill can leak future information | Zero lag requires documented availability timestamps |
| D005 | Convert units only from explicit NetCDF attributes | Inferring units from magnitude is unsafe | Unknown units produce warnings, not silent conversion |
| D006 | Keep unmapped fuel/ground-wind rules out of the core baseline | Required datasets, height conversion and semantics are unresolved | They remain typed and can be enabled when evidence arrives |
| D007 | Use Xarray/Dask lazily and benchmark chunk layouts | The file-backed 1973–2023 grid exceeds workstation memory | Results are checkpointed by year on Spartan |
| D008 | Support Kerchunk but keep references restricted | References expose source locations and inherit access controls | Reference JSON is ignored and not a public artifact by default |
| D009 | Validate every optimiser output independently | Solver success alone is not a domain feasibility proof | A failing validation aborts the run |
| D010 | Label synthetic metrics at creation time | Fixtures prove code, not project outcomes | Synthetic rates and timings are prohibited resume evidence |
| D011 | Do not publish the FMS workbook or a threshold dump | Licensing/publication permission is unclear | Workbook is supplied at runtime from restricted storage |
| D012 | Keep 6.49%, 9.04% and prior scale claims unverified | No accessible run artifact reproduces them | README records them only as historical project claims |
| D014 | Keep anonymous ARCO-ERA5 as a bounded, independently reproducible engineering preflight | It exercises cloud Zarr/Xarray/unit derivation without restricted project access, but differs from VicClim6 in source and resolution | Publish provenance and engineering metrics; prohibit VicClim6, FFDI/KBDI, window, trend or value claims |
| D013 | Add lower-tail CVaR beside nominal and max-min schedules | A single worst scenario was conservative and did not yield stable held-out P05 improvement | Risk appetite is explicit (`alpha=0.8`); planning and held-out scenarios use independent seeds |
| D015 | Treat the actual inventory (1973–2023) as authoritative rather than the `1972-2024` directory label | All six families contain 51 years and no 1972/2024 year directories | Coverage claims and arrays use 1973–2023; 1973 starts on 2 January because prior daily state is absent |
| D016 | Use a synchronous one-worker Dask scheduler inside each concurrent annual task | Four processes each inherited the 128-core node and produced random NetCDF SIGSEGV/SIGBUS failures | One CPU per year; Slurm array parallelism supplies concurrency; mixed NetCDF formats use automatic backend selection |
| D017 | Fuse scalar reductions into one shared Dask graph and size memory from pilots | Repeated reductions reread the same 245.59-GiB collection; the first fused pilot exposed the exact OOM boundary | Formal years request 8 GiB after a 6,015,508-KiB pilot peak and preserve a semantic-hash equality gate |
| D018 | Use the official `LF_DISTRICT` ArcGIS feature for district reporting and evaluate membership at grid-cell centres | Group44 storage has no spatial mask, while substituting an LGA or inferring geography from a burn-class name would be indefensible | Exact district match, EPSG:4326, sub-grid simplification tolerance and boundary hash are mandatory; district results remain distinct from burn-unit/area claims |
| D019 | Close surface-FMC and fuel-level-wind gaps with an explicit proxy mode, not silent substitution | Published equations and wind-reduction factors make a reproducible scenario possible, while site meters/canopy calibration are unavailable | Proxy inputs are promoted only when `--derive-fuel-proxies` is explicit; rain-affected FMC is missing and every artifact says `observed_on_site=false` |
| D020 | Use official JFMP and Fire History polygons as a separate burn-unit outcome layer | Current JFMP and historical treatment geometry are publicly queryable with stable burn identifiers | De-duplicate typed records, union multipart polygons, intersect in EPSG:3577 and preserve source hashes; staged/repeated burns prohibit causal interpretation |
| D021 | Use public crew and cost figures only as transparent scenarios | Unit rosters and invoices are not public, but FFMVic publishes staffing ranges and statewide direct planned-burning investment/area | Report person-hour and AUD/ha scale proxies; never relabel them as actual unit cost, saving or return |

## Open decisions requiring supervisor or data-owner confirmation

1. authoritative window definition and minimum operational duration;
2. site-specific wind-reduction factor and field calibration for fuel-level wind;
3. Day 2/3 FDI semantics;
4. exact meaning and dates for `Fallen` and `From Summer` KBDI labels;
5. field calibration/acceptance tolerance for literature-derived fuel moisture;
6. spatial reporting unit and completeness threshold;
7. whether the workbook and any normalized threshold representation may be published;
8. whether fire-history records are contextual evidence or a validation set.

