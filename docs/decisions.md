# Decision log

| ID | Decision | Reason | Consequence |
|---|---|---|---|
| D001 | Treat the project as an Agent-callable deterministic tool layer | Domain rules and schedules must remain auditable | LLM planning is outside the calculation trust boundary |
| D002 | Compile every source value or mark it unresolved | Silent omission would create unsafe false confidence | Partial prescriptions return warnings |
| D003 | Preserve `<` versus `<=`; ranges are inclusive by default | Boundary choice changes suitability counts | Assumption is test-covered and visible in the AST |
| D004 | Use a 24-hour default availability lag for date-labelled daily aggregates | Same-day fill can leak future information | Zero lag requires documented availability timestamps |
| D005 | Convert units only from explicit NetCDF attributes | Inferring units from magnitude is unsafe | Unknown units produce warnings, not silent conversion |
| D006 | Keep unmapped fuel/ground-wind rules out of the core baseline | Required datasets, height conversion and semantics are unresolved | They remain typed and can be enabled when evidence arrives |
| D007 | Use Xarray/Dask lazily and benchmark chunk layouts | Full 1972–2024 grids exceed workstation memory | Results are checkpointed by year on Spartan |
| D008 | Support Kerchunk but keep references restricted | References expose source locations and inherit access controls | Reference JSON is ignored and not a public artifact by default |
| D009 | Validate every optimiser output independently | Solver success alone is not a domain feasibility proof | A failing validation aborts the run |
| D010 | Label synthetic metrics at creation time | Fixtures prove code, not project outcomes | Synthetic rates and timings are prohibited resume evidence |
| D011 | Do not publish the FMS workbook or a threshold dump | Licensing/publication permission is unclear | Workbook is supplied at runtime from restricted storage |
| D012 | Keep 6.49%, 9.04% and prior scale claims unverified | No accessible run artifact reproduces them | README records them only as historical project claims |
| D013 | Add lower-tail CVaR beside nominal and max-min schedules | A single worst scenario was conservative and did not yield stable held-out P05 improvement | Risk appetite is explicit (`alpha=0.8`); planning and held-out scenarios use independent seeds |

## Open decisions requiring supervisor or data-owner confirmation

1. authoritative window definition and minimum operational duration;
2. units, measurement height and averaging period for both wind fields;
3. Day 2/3 FDI semantics;
4. exact meaning and dates for `Fallen` and `From Summer` KBDI labels;
5. mandatory versus optional unmapped fuel-moisture constraints;
6. spatial reporting unit and completeness threshold;
7. whether the workbook and any normalized threshold representation may be published;
8. whether fire-history records are contextual evidence or a validation set.

