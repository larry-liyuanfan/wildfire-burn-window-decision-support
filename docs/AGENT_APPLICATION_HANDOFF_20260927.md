# FLARE：可信领域工具 / 实际 MCP 交接（2026-09-27）

## 工作区、版本与责任

- 独占工作区：`E:/Project/_codex_worktrees/wildfire-burn-window-decision-support-flare-evidence-closeout`。
- 分支：`codex/flare-agent-application-20260927`，从最新 `origin/main`
  `d7d5962a42f9cf3ddccf97d482368ffe2f756b43` 开始；未编辑共享 main 或其他 chat 的 worktree。
- 实际 MCP 运行 SHA：`e7826458aed85ea1354dd5bad9d92d9428806ad6`；后续文档不冒充计算版本。
- 历史 51 年计算 SHA：`bf90d0afd1012f893369a2ef87f72133892d6bd9`。
- 身份仍为 **Data Science Industry Project / Vocational Placement**；行业 brief、
  团队输入、官方数据与个人工程扩展分开。没有修改课程分支或宣称团队已采纳 MCP。
- 本轮不写求职共享材料、简历、Trip/Energy/Climate 源码，不提交 GPU 或重算作业。

## 面向用户的任务与可复现交付

用户需求可表述为：“查看某个官方 burn ID 在某年的历史气候窗口、限制因素及数据缺失。”
本次由人明确提供结构化参数，不假装模型已从这句话正确规划出调用。

```text
43 类非结构化处方 → typed AST / 时空数据合同
→ 逐网格规则判定 → 稀疏面积加权 → 年度 checkpoint / compact
                                        ↓（历史计算，非每次查询）
MCP tools/list → Pydantic 参数 → allowlisted catalog / SHA 校验
→ get_burn_unit_climatology → ToolEnvelope + 数据/规则/空间来源 + 警告
```

源码入口 `src/burnwindows/mcp_server.py` 采用**官方 MCP Python SDK 1.26.0** 的
low-level Server；只提供 stdio，不监听公网。`scripts/demo_mcp_climatology.py`
使用官方 `ClientSession` / `stdio_client` 真正启动另一个 Python 进程，完成初始化、
标准 `tools/list` 和 `tools/call`。不是直接调用 Python 函数冒充协议通过。

当前 MCP 只暴露 7 个既有 typed tools 中的 `get_burn_unit_climatology`，不宣称全部
7 个都已接 MCP。Pydantic 严格输入最多 5 IDs × 5 年，禁止文件路径、任意表达式及
额外字段；catalog 路径只由操作员配置。结果透传 `ToolEnvelope`、原始 warnings、
constraints、publication boundary 和记录级 data/rule/spatial/code SHA。
未知 ID 返回 `partial` + 空结果/警告，不做 nearest fallback；非法参数和不可用目录
返回 MCP `isError=true`、无结果、`provenance=incomplete`。

本轮修复旧 HTTP 服务的窄 bug：不能仅因工具名是 compact 查询就把错误结果标成
`artifact_verified`。超时不发布晚到结果；它是只读查询 deadline，不声称强制终止后台线程。
重复查询保证数据结果一致，trace/耗时可变化；没有新增写文件、执行命令、修改处方或调度能力。

## 真实数据、账户与源边界

公开仓库原先只有 redacted execution record，并没有完整逐 burn-ID compact。
本轮没有把 fixture 当真实数据：按既有发布脚本定位 Spartan 的正式 compact，
在存储原地启动 client/server。Iris 的现有连接对该目录返回 `Permission denied`；
沿用已授权的 `spartan-flare` 密钥连接成功。未更改账户/认证、未读取私钥或密码。

以下字节身份与既有发布证据一致：

| 对象 | 已核验值 |
|---|---|
| artifact ID | `flare-murray-goldfields-burn-id-climatology-1973-2023-v1` |
| compact | 23,083,893 bytes；SHA `2f85815eb40c487456ffa3d83a0c58e8a3e6037ca103c41424b188db8c7cfbd9` |
| catalog | SHA `fb72a292a8396cb9a143ea855746cd9c625c6bea487f30417108695395b6c2b8` |
| 新协议报告 | SHA `b243df632b86c692b35ab4e8af372dfd96ea92f4f20dfd5fbe33e7afc6528b6d`，按传输后本地字节核对 |

真实查询使用官方 ID `LM-MGF-MRY-0374`，2020 年。client 断言记录 ID/年份准确、
规则/数据 provenance 完整、约束与缺失警告存在。受限记录只在远端进程内检查和 hash；
没有复制到本地、GitHub 或求职目录。公开报告甚至不带 warning 自由文本，只保留
固定 warning code、数量与哈希。fixture 特意注入私有路径文本，验证摘要不会带出它。

### 实际协议结果

| case | 实际结果 | 边界 |
|---|---|---|
| 有效 ID / 2020 | `ok`，1 条，artifact_verified，6 条 warnings 留在远端响应 | 真实 compact 查询，不是新天气实验 |
| 重复同一请求 | 结果 hash 相同 | 不把不同 trace/耗时要求成完全字节幂等 |
| 未知 burn ID | `partial`，0 条，unknown-ID warning | 不补猜数值或邻近网格 |
| 注入 artifact_path | `isError` / invalid_arguments | 不给 caller 文件读取能力 |
| 未登记 artifact | `isError` / tool_error | 不绕过 catalog |
| 未配置 catalog 的新 server | `isError` / catalog_unavailable，incomplete | 不报告“数据已验证” |

两次初始化 / `tools/list`，六次 `tools/call`。这是应用协议 smoke check，
不是 6 条自然语言 Agent Eval，也不是在线 SLA 或成功率估计。

## 复现命令与隔离依赖

远端采用独立项目目录和新 venv；原始 51 年数据/发布目录只读。原目录实际路径由
`spartan/publish_burn_unit_climatology.sbatch` 的发布路径约定解析，设置到
`FLARE_COMPACT_CATALOG`。不要把该变量暴露给模型作为可填写参数。

```bash
module load GCCcore/11.3.0 Python/3.11.3
python -m venv .venv-mcp
.venv-mcp/bin/python -m pip install -r requirements-mcp.lock
.venv-mcp/bin/python -m pip check
PYTHONPATH=src .venv-mcp/bin/python scripts/demo_mcp_climatology.py \
  --artifact-catalog "$FLARE_COMPACT_CATALOG" \
  --artifact-id flare-murray-goldfields-burn-id-climatology-1973-2023-v1 \
  --burn-id LM-MGF-MRY-0374 --evidence-kind real-precomputed \
  --expected-catalog-sha256 fb72a292a8396cb9a143ea855746cd9c625c6bea487f30417108695395b6c2b8 \
  --expected-artifact-sha256 2f85815eb40c487456ffa3d83a0c58e8a3e6037ca103c41424b188db8c7cfbd9 \
  --output mcp-real-redacted.json
```

手动 MCP 客户端可启动 `python -m burnwindows.mcp_server --artifact-catalog ...`。
stdout 保留给 MCP 协议，不打印调试日志。子进程只额外继承必要 `LD_LIBRARY_PATH`，
不复制所有环境或凭据。最小 lock 包括传递依赖；这是只读查询 runtime，不是完整
天气计算环境。完整开发安装可用 `pip install -e '.[dev,serve,mcp]'`。

```powershell
.venv-mcp/Scripts/python -m pytest -q tests/test_mcp_climatology.py tests/test_burn_unit_climatology.py::test_compact_artifact_service_is_allowlisted_and_read_only
.venv-mcp/Scripts/python -m mypy src/burnwindows/mcp_server.py src/burnwindows/service.py
```

本地定向 **10 passed**；changed-file Ruff、两模块 mypy 通过。远端新隔离环境
`pip check` 和真实 stdio 演示通过。GitHub [quality run 36304625743](https://github.com/larry-liyuanfan/wildfire-burn-window-decision-support/actions/runs/36304625743)
在运行 SHA 上 **116 passed**，lint 与两组类型检查通过；没有占用本地全量验证槽位。
新增/修改文件 secret/PII patterns 检查通过。全仓复用扫描器报告旧测试文件中的 Iris
账户字面量（基线已有，非凭据）；没有将这次全仓扫描写成“全部通过”，也未改其他历史文件。

官方实现依据：
[MCP Python SDK v1.26.0 README](https://github.com/modelcontextprotocol/python-sdk/blob/v1.26.0/README.md)、
[MCP server guide](https://modelcontextprotocol.io/docs/develop/build-server)。
锁定已验证 1.x SDK，不将最新 main 的不同 API 冒充本次实现。

## 历史研究证据与本轮能力分开

- AST 基础设施覆盖43类；compact 使用选定处方的8条件及显式 FMC/燃料层风代理，
  不是43类×所有单元的全组合结果。
- 221 polygon features / 220 unique plan records 按 burn ID 归并176个；稀疏351权重、
  230网格；176×51 = 8,976 ID-year records，1973–2023。2020 direct/CSR 最大差0。
- 先 grid-level 规则判定再加权，不以 district weather 或 nearest cell 替代 burn unit；
  current-plan polygons 叠历史气候不等于历史实际燃烧面积/结果。
- FMC、ground wind 仍是文献代理，降水缺失且 rain guard 未应用；无安全批准、风险
  下降、因果效应、真实成本节省、调度收益或 ROI。
- 前6工具既有30-call fixture性能/恢复记录不扩大到第7工具或本 MCP，更不称线上SLA。

## 框架/完成状态盘点

| 状态 | 内容 |
|---|---|
| 既有 | Pydantic AST、Xarray/Dask研究链、稀疏聚合、7 typed tools、FastAPI、hash-pinned catalog |
| 本轮新增且运行 | 官方 MCP Server/ClientSession/stdio；只读第7工具；真实compact协议检查；错误provenance修复；自由文本不外传 |
| 未确认 | 真实LLM选工具、自然语言端到端成功率、团队采纳、生产部署、现场安全或经济效果 |

没有新增向量库、聊天机器人、LangChain/LangGraph 工作流或微调；MCP是接口协议，
不是 Agent 自主性证据。独立只读 review 的两处建议（模块库路径、warning脱敏）均已实施。

## 两条候选简历 bullet（辅助经历，通常只选一条）

- **可信领域工具：**将燃烧处方编译为 typed AST，以网格级规则与稀疏面积加权形成 **176个 burn ID、51年**可审计统计；通过官方 MCP 暴露只读查询，完成真实预计算数据的有效/异常协议验证，保留代理与缺失限制。
- **工程交付：**构建 **7个 typed tools** 及带数据/规则/空间来源的结果合同，将年度计算与 Agent 查询解耦；为预计算查询实现标准 MCP schema、白名单与失败封装，阻止越权参数、未知来源和错误验证状态进入下游。

不能写“7个MCP工具”“自主Agent”“实测安全收益”。搜索岗位仅作复杂数据、typed tools、
可信工程的辅助；Agent应用方向可作为工具协议案例，不与Trip/Climate争核心算法版面。

## 90 秒面试故事

“FLARE是行业项目，行业方要了解计划燃烧天气窗口对阈值定义的敏感性。我负责的个人
工程扩展先把处方转成typed AST，明确时间、空间和缺失合同，不能直接用district统计
回答某个burn unit。于是先在网格判规则，再用polygon相交面积做稀疏聚合，形成176个
ID的51年年度结果，并用独立direct方法核对2020结果。为了让上层Agent能够使用，
我没有再加一个无关聊天机器人，而是用官方MCP SDK把已有预计算查询变成标准工具。
真实客户端在Spartan通过stdio查询官方ID的一年记录，重复结果一致；非法参数、未知
artifact和缺失catalog都返回明确失败。我还修复了一个失败响应却标记数据已验证的
问题。完整数据不离开存储，公开只留哈希与检查摘要。它证明复杂计算可以受控供Agent
调用，但没有证明模型会自主规划，更不能把FMC/风的代理或历史天气窗口当安全批准。”
