# Interview defence map

## 90-second story

FLARE 是墨尔本大学的 Data Science Industry Project。行业方的问题是：计划燃烧的天气窗口会不会因为阈值定义变化而显著变化，并且能否把结论做成可审计交付。我负责把私有 workbook 的 43 类规则编译成 typed AST；不能可靠解释的字段不猜，而是保留为 unresolved。数据侧我实现了无未来信息泄漏的日频到小时级对齐、单位与缺测策略，并在 Spartan 对 1973–2023 的受限 VicClim6 完成 51/51 年 checkpointed district-level 处理。

随后我发现 district weather 不能直接冒充 burn-unit 结果，因此把 221 个官方 current-plan polygons 按 `TREAT_NO` 归并为 176 个 burn IDs，再用 area-weighted overlay 建立 polygon 到网格的空间合同；176/176 有覆盖，nearest fallback 为零，但我仍明确它只解决空间映射，没有宣称完成 burn-unit climatology。

最后我把规则、趋势、敏感性、燃料代理和调度封装成 6 个 typed tools，加入 request hash、provenance、timeout、幂等和 exact-checkpoint resume。98 个测试以及固定 fixture 的 6×30 调用验证了 schema 和失败恢复。最关键的取舍是：FMC 和 ground wind 仍是代理而非现场测量，所以所有输出都禁止被表述为安全批准、因果风险下降或 ROI。这段经历证明我能把复杂领域数据变成 Agent 可安全调用、可拒绝、可追溯的工具，而不是证明我训练了搜索模型或自主 Agent。

## Code evidence map

| Interview question | Evidence |
|---|---|
| How do you stop an Agent from inventing domain rules? | `models.py`, `rules.py`, `tools.py` |
| How do retries avoid duplicate or mismatched work? | canonical validated-request hash plus idempotency store in `service.py`; same request replays and changed arguments return 409 |
| What does timeout guarantee? | `service.py` and `test_service_reliability.py`; fail-closed publication, not hard termination of a running Python thread |
| Which work can resume from a checkpoint? | stateless tools declare checkpoint N/A; only the artifact-catalog climatology job accepts the exact token emitted by its failed parent |
| Is this an autonomous Agent? | No. `docs/evidence-closeout.md` documents an Agent-callable deterministic tool boundary; no real LLM task-selection evaluation exists |
| How do you prevent temporal leakage? | `alignment.py` and alignment tests |
| How are strict/inclusive boundaries handled? | `parse_threshold`, `evaluate_condition`, rule tests |
| What happens when a variable is missing? | explicit `MissingPolicy` and warning envelope |
| How is a continuous operational window defined? | `extract_windows`; irregular gaps split runs |
| How do you scale beyond memory? | `io.py`, Kerchunk builder and Spartan Slurm array |
| What real-data path was actually executed? | `io.py`, `spatial.py`, `evaluate_vicclim6_year.py`, the compact VicClim6 inventory/2020, 51-year statewide and 51-year district records plus Slurm accounting; `public_reanalysis.py` remains an independently reproducible public preflight |
| How is regional scope prevented from being mixed across years? | `spatial.py`, region hash/properties in every manifest, and `aggregate_vicclim6_years` single-spatial-contract gate |
| Why did a 93.85% cell reduction produce only an 83.74% elapsed reduction? | `performance.py`, `compare_spatial_scopes.py` and the compact scope-comparison artifact; discuss fixed I/O/alignment overhead and the non-causal comparison boundary |
| Why did four workers fail the scaling gate? | `compare_real_scaling.py`, the 1/2/4 run manifests and `vicclim6_murray_goldfields_worker_scaling_20260822.json`; distinguish identical-result verification from speedup and report 29.78% efficiency as a negative gate |
| How is threshold sensitivity made robust to one unusual year? | `sensitivity.py`, `trend.py`, `aggregate_vicclim6_years.py` and the 51-year redacted record; paired annual effects plus seeded five-year moving-block-bootstrap intervals |
| Why can KBDI show exactly zero sensitivity? | the fixed baseline/scenario contract and per-year effect record; explain an inactive bound conditional on the other mapped constraints without claiming KBDI is generally irrelevant |
| How do you prove restart does not alter results? | local property tests plus remote job `29467567`: controlled exit 75 at 168/336 hours, resume from checkpoint and exact semantic hash match against an uninterrupted 316,848-cell-hour run |
| How do you know optimisation output is valid? | MILP constraints plus independent `validate_selection` |
| Why was a candidate rejected, and what would another crew buy? | `explain_selection` plus the typed tool's discrete crew-capacity counterfactuals; both carry non-dual/non-financial boundaries |
| Why CVaR as well as max-min? | `solve_cvar_schedule` exposes a tail-risk parameter and avoids letting one worst scenario dominate |
| What is genuinely measured today? | `docs/evidence.md` and run manifests |
| How did you move from a district to real burn units? | `official_burns.py`, official ArcGIS attribute/GeoJSON hashes and the public delivery artifact; exact-ID join plus EPSG:3577 union/intersection |
| How are FMC and ground wind now handled? | `fuel_inputs.py` and `derive_fuel_inputs`; two-model FMC interval, rain guard, explicit WRF and `observed_on_site=false` |
| Where do crew and cost numbers come from? | FFMVic public 20/30/70-person scenarios and 2024–25 direct planned-burning cost/area; both remain proxies rather than unit records |
| Did the complete proxy contract run beyond a pilot? | Array `29504645`, aggregate `29504810` and `vicclim6_murray_goldfields_proxy_complete_51y_29504645.json`; 51/51 years and exact contract gates |

## Expected deep questions

1. Why is a date-labelled daily aggregate delayed by 24 hours?
2. When is forward fill scientifically valid, and what maximum age is safe?
3. Why are seasonal AST leaves neutral outside their active season?
4. How would you resolve overlapping KBDI seasonal rules?
5. Why is a wind-reduction factor a scenario rather than a site measurement?
6. What is lost when only window endpoints are counted in a full grid run?
7. How would chunk shape change for time-series versus map queries?
8. What does Kerchunk virtualise, and what access risks remain?
9. Why compare an exact solver with two greedy baselines?
10. What does the scheduling objective measure, and why is it not money?
11. How would you add spatial crew travel constraints?
12. How would you validate suitability against realised burns without treating unburned windows as negative labels?
13. Which fields remain unresolved in the FMS workbook and why?
14. How can Dask produce correct results but poor performance?
15. What evidence is needed before claiming a worker-scaling result?
16. How do retries/checkpoints avoid double-counting annual outputs?
17. What deterministic outputs should an LLM be allowed to summarise?
18. How are raw data licences separated from code publication?
19. What would make a sensitivity result operationally actionable?
20. Why do historical percentages remain unverified even if they appear in an earlier presentation?
21. How does the CVaR linearisation work, and why are planning and held-out scenarios separately seeded?
22. Why can a positive mean P05 lift coexist with 60% unchanged policies?
23. Why is the discrete crew-capacity objective delta not a shadow price?
24. When can a local blocking-set explanation disagree with a globally optimal counterfactual?
25. Why is the ERA5 pass rate a necessary-condition upper bound rather than a burn-window rate?
26. Which state must cross a chunk boundary so 2/4/6-hour runs are not double-counted or split?
27. Why compare semantic payload hashes instead of raw JSON file hashes after resume?
28. What additional evidence is required before feeding public-weather candidates into a real scheduling or economic claim?
29. Why is an official fire-management district still not a burn-unit or treatable-area mask?
30. How do you interpret a positive Theil–Sen slope whose block-bootstrap interval excludes zero without making a causal claim?
31. Why did masking 6.15% of grid centres reduce annual runtime and MaxRSS, and which operations still scale with time rather than space?
32. Why is the statewide-vs-district comparison not a 1→4 worker benchmark or an Amdahl serial-fraction estimate?
33. Why is the one-worker run the denominator for parallel efficiency, and why does identical output not prove useful scaling?
34. Why use a moving-block bootstrap for annual threshold effects instead of an IID bootstrap?
35. How would you distinguish a genuinely inactive KBDI bound from a unit-conversion or scenario-wiring bug?
36. Why are the all-mapped wider/narrower effects not the sum of the one-factor effects?
37. Why do you union duplicate/multipart plan polygons before computing area?
38. Why can historical treated geometry lie almost entirely inside a current plan while covering only 38% of it?
39. Why is AUD/ha an expenditure-scale proxy rather than a savings estimate?
40. What held-out field data would be needed to calibrate the FMC ensemble and WRF?

