# FLARE evidence closeout and role translation

## What this project is

This repository records an individual engineering extension of the University
of Melbourne FLARE **Data Science Industry Project (Vocational Placement)**.
The industry brief asked the student team to test how prescribed-burning
weather-window definitions change under alternative thresholds and to deliver
maps, graphs and tables describing frequency, variability and trends. It was
not a Research Assistant appointment, employment contract or autonomous-Agent
project.

The defensible engineering case is:

```text
private workbook rules
→ typed AST with unresolved fields preserved
→ no-lookahead temporal, unit, missing-data and spatial contracts
→ area-weighted official-polygon-to-grid mapping
→ six typed deterministic domain tools
→ response provenance, refusal states and auditable artifacts
```

The team supplied the placement context and access to the restricted workbook
and VicClim6 collection. Official plan and history geometry comes from FFMVic
public services. The compiler, contracts, tool/service boundary, reproducible
artifacts and the evidence controls in this repository are the documented
individual extension. Team deliverables are not represented as solely authored
work.

## Definition audit

| Number | Exact meaning | Evidence and limit |
|---|---|---|
| 43 | Burn-class rows in the private 43-row × 25-column `FMS-Prescriptions_2.xlsx`; the loader requires exactly 43 and compiles usable cells while retaining unresolved values. | Private-input inspection plus loader tests. It means row coverage, not 43 algorithms or operational validation. Threshold contents are not published. |
| 221 | Official current-plan GeoJSON features returned for Murray Goldfields by the FFMVic service. | The public artifact records 221 features and 220 unique plan records. Multipart or duplicate geometry means feature count is not burn-unit count. |
| 176 | Unique current-plan `TREAT_NO` burn IDs after grouping and unioning the 221 features. | Spartan overlay job `29584607` covered 176/176 IDs with 351 non-zero polygon/grid weights and zero nearest-cell fallbacks. This verifies a spatial contract, not a 51-year burn-unit climatology. |
| 51 years | Actual file-backed VicClim6 coverage from 1973 through 2023 in the restricted Group44 copy. | Arrays completed 51/51 exact-SHA annual checkpoints. The verified 51-year weather outputs are district-level; directory labels mentioning 1972–2024 do not change the observed coverage. |
| 91 tests | Collected and passing tests at merged `main` commit `5bfb760`. | This was a software regression count, not a dataset, model-evaluation or field-validation sample size. The closeout branch adds seven reliability cases and currently collects 98 tests. |

The official historical outcome adapter is a separate layer: it found 187
historical IDs and eight exact current-plan/history ID matches. Those geometry
records are not labels for the district weather series and cannot support a
causal effect, safety outcome or approval claim.

## Trusted tool boundary

The six public tools remain deterministic:

1. `find_burn_windows`
2. `explain_limiting_factors`
3. `compare_threshold_scenarios`
4. `get_region_trend`
5. `optimize_burn_schedule`
6. `derive_fuel_inputs`

Every invocation now exposes the same input JSON Schema and `ToolEnvelope` 1.1
output contract. The envelope distinguishes `ok`, `partial`, `error` and
`needs_clarification`; an error must include a machine-readable error object.
Service responses also contain a canonical validated-request hash, code SHA,
caller-supplied data version status, source references, trace ID, elapsed time,
deadline and replay state.

The reliability policy is deliberately narrow:

- undeclared parameters fail before domain code runs;
- an idempotency key is bound to the canonical validated request; a replay of
  the same request returns the cached envelope, while key reuse for different
  arguments returns HTTP 409;
- a per-request deadline returns `tool_timeout` and publishes no late result;
- runtime and domain-validation failures return typed errors rather than a
  plausible empty result;
- these six calls are stateless, so their checkpoint mode is explicitly
  `not_applicable_stateless`;
- the long artifact-backed burn-unit climatology job is separate and may resume
  only from the exact checkpoint token emitted by that failed job.

This is a safe **tool layer that an Agent could call**. A language-model planner
has not been evaluated on real task selection, so the system is not described
as an autonomous Agent.

## Fixed-load offline tool benchmark

Artifact:
[`../artifacts/public/flare_tool_service_fixture_benchmark_20260903.json`](../artifacts/public/flare_tool_service_fixture_benchmark_20260903.json)

- implementation SHA: `ff599cd7be31144131aee63444b4d86bd45bb6a2`
- canonical-JSON SHA-256: `53030e139c42f984ed9ea95588bb507c9b04614edec7653a2e388217f1674925`
- repository-normalised LF bytes SHA-256: `fe434547e2f731b4afa1ba8fd2f9b73a7a276602aed455f5a6dd56f62af74578`
  (a Windows working tree may materialise CRLF bytes, so the canonical hash is
  the cross-platform content identity)
- fixed workload: 168 hourly points for array tools, 51 annual values and 100
  seeded bootstrap samples for the trend tool, and 12 schedule candidates;
- protocol: three warm-ups and 30 measured loopback invocations per tool, each
  tool isolated in a child process;
- result: 30/30 successful calls and one deterministic result hash for every
  tool; all six explicit failure/recovery cases passed.

| Tool | Service execution P50 / P95 | Loopback P95 | Peak process RSS |
|---|---:|---:|---:|
| `compare_threshold_scenarios` | 5.60 / 6.14 ms | 13.12 ms | 96.9 MiB |
| `derive_fuel_inputs` | 2.46 / 2.66 ms | 12.05 ms | 102.4 MiB |
| `explain_limiting_factors` | 1.87 / 2.05 ms | 8.32 ms | 97.0 MiB |
| `find_burn_windows` | 6.40 / 6.80 ms | 16.14 ms | 97.9 MiB |
| `get_region_trend` | 1,314.72 / 1,337.36 ms | 1,345.84 ms | 96.2 MiB |
| `optimize_burn_schedule` | 35.73 / 36.56 ms | 42.21 ms | 129.8 MiB |

This is a Windows loopback **deterministic-fixture/domain-tool benchmark**. It
is not a VicClim6 run, production SLA, concurrency test, model/Agent evaluation,
field validation or evidence of operational safety. The result makes the
quality–latency boundary visible: seeded trend uncertainty dominates latency;
the optimiser has the highest resident-memory envelope; the other four tools
are low-millisecond operations on this fixed fixture.

## Failure stories and publication gates

### District weather is not burn-unit outcome

The restricted 51-year chain used an official district mask. Treating its cell
counts as burn-unit results would be a spatial-level error. The fix was to make
the spatial contract part of each manifest and build a separate area-weighted
overlay for 176 unique official burn IDs. The overlay closes geometry only; a
separate burn-unit climatology has not been run.

### Nearest fallback can create false coverage

Substituting the nearest grid centre for a zero-overlap polygon would produce a
plausible value for a unit with no demonstrated support. The contract therefore
retains zero coverage as an explicit failure. The verified overlay happened to
cover 176/176 units with zero fallbacks; the refusal behaviour remains required.

### A proxy is not an on-site measurement

FMC is derived from a literature-model ensemble and ground wind from a declared
10-m wind-reduction scenario. They remain proxies because they were not
site-calibrated; precipitation was unavailable for the restricted run's rain
guard. The service carries this in warnings and provenance instead of promoting
the values to observed fuel moisture, safe conditions or operational approval.

### Stop a plausible but invalid result from being published

Annual aggregation rejects missing/duplicate years, mixed code SHAs, mixed rule
or spatial contracts and non-real artifacts. The service separately rejects
undeclared fields, mismatched idempotency keys, invalid checkpoint tokens and
timed-out computations. These controls turn uncertainty into a visible refusal
or warning rather than a silently usable number.

## Search-role translation

Suggested single resume bullet:

> 将 43 类非结构化计划燃烧规则编译为 typed AST，构建无前视时空合同、area-weighted polygon→grid 聚合与 6 个可审计工具；在 1973–2023 VicClim6 上完成 51/51 年 checkpointed district chain，并将 221 个官方 polygons 归并为 176 个 burn IDs、实现 176/176 覆盖且零 nearest fallback。

This project should occupy an auxiliary position for search roles. It proves
complex-data contracts, typed tools, deterministic execution and evidence-safe
failure handling. Trip and Climate remain the primary evidence for retrieval,
ranking, representation learning and search evaluation.

## 90-second interview story

> FLARE 是墨尔本大学的 Data Science Industry Project。行业方的问题是：计划燃烧的天气窗口会不会因为阈值定义变化而显著变化，并且能否把结论做成可审计交付。我负责把私有 workbook 的 43 类规则编译成 typed AST；不能可靠解释的字段不猜，而是保留为 unresolved。数据侧我实现了无未来信息泄漏的日频到小时级对齐、单位与缺测策略，并在 Spartan 对 1973–2023 的受限 VicClim6 完成 51/51 年 checkpointed district-level 处理。后来我发现 district weather 不能直接冒充 burn-unit 结果，因此把 221 个官方 current-plan polygons 按 `TREAT_NO` 归并为 176 个 burn IDs，再用 area-weighted overlay 建立 polygon 到网格的空间合同；176/176 有覆盖，nearest fallback 为零，但我仍明确它只解决空间映射，没有宣称完成 burn-unit climatology。最后我把规则、趋势、敏感性、燃料代理和调度封装成 6 个 typed tools，加入 request hash、provenance、timeout、幂等和 exact-checkpoint resume。98 个测试以及固定 fixture 的 6×30 调用验证了 schema 和失败恢复。最关键的取舍是：FMC 和 ground wind 仍是代理而非现场测量，所以所有输出都禁止被表述为安全批准、因果风险下降或 ROI。这段经历证明我能把复杂领域数据变成 Agent 可安全调用、可拒绝、可追溯的工具，而不是证明我训练了搜索模型。
