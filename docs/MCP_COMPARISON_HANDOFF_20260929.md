# FLARE：真实 compact 比较与解释交接（2026-09-29）

## 结果先行

已有只读 MCP 工具 `get_burn_unit_climatology` 新增 `view="compare"`，在
Spartan 原地完成三组真实预计算数据案例、六次真实 stdio MCP 调用；独立客户端
以 Decimal 重算并完成 **58 项算术/来源断言**。返回年度表、有效小时加权汇总、
差值及带规则来源的确定性解释。不是增加第二个工具，也不是 LLM 自主决策测试。

| 真实案例 | 年度记录返回数 | 客户端核验数 | 比较工具内 elapsed_ms |
|---|---:|---:|---:|
| 同一官方 burn ID，2020 对比 2021 | 2 | 13 | 1.445 |
| 两个 catalog 确认的 burn IDs，2020 | 2 | 17 | 1.266 |
| 同一 burn ID，2019–2023，以 2019 为参考 | 5 | 28 | 1.222 |

共9条返回记录包含案例之间的重复，不是9个新单元或9条自然语言任务。
每案先调用 records，再调用 compare；官方 ClientSession 启动独立 server 进程。
第二个 ID 由已确认的2020 catalog ID排序后确定，不虚构单元。数值表、ID请求及
模板解释保存在源存储；公开报告只保留计数、状态、哈希与脱敏 warning codes。

上述耗时是**服务内部已加载 compact 的单次查询计时**，不包含初始化、catalog
加载或完整 stdio 往返，样本仅3，不能推导 P95、吞吐或在线 SLA。本包未新增内存
性能实验或失败恢复率；原协议异常/幂等测试与历史领域计算性能分别保留。

## 可追溯版本

- 分支：`codex/flare-agent-application-20260927`；基线 `f88ed4fc6228d8b2ce12657a7223479805e9ee81`。
- 真实执行代码：`f1341c086a756f6e70a8aab1021e066acb95c992`。
- catalog SHA-256：`fb72a292a8396cb9a143ea855746cd9c625c6bea487f30417108695395b6c2b8`。
- compact SHA-256：`2f85815eb40c487456ffa3d83a0c58e8a3e6037ca103c41424b188db8c7cfbd9`。
- 脱敏报告：[flare_mcp_comparison_20260929.json](../artifacts/public/flare_mcp_comparison_20260929.json)，
  SHA-256 `7bf6a20d60b89e46bc16690ff2395dff11fd49d60d6716bfccb02b4fa5401e36`；LF字节保留。
- 历史数据仍为既有176 IDs × 51年 = 8,976条年度 compact；本次没有新建天气数据。
- 运行账户沿用已有授权 `spartan-flare`；未更改认证、使用GPU、触碰其他项目或重扫NetCDF。

真实执行后只读 review 提出的两个问题已另加防护和回归测试：①禁止脱敏/详细结果
路径重合及覆盖既有文件；②任一比较侧有效小时为0，窗口小时差返回 null，解释
明确缺测而非“0小时合格”。实际执行使用不同新路径且覆盖有效，因此保留原报告，
不将后续修复提交冒充已运行代码。精确修复版本见此文所在提交的 Git history。

## 从源字段到可解释结果

1. 参数仅接受最多5 IDs × 5年、既有0.5/0.8/1.0面积比例阈值及2/4/6小时段；
   阈值选择仅描述已计算统计，不能重写处方、提供路径或执行表达式。
2. 比较要求所有记录 data/rule/spatial/code SHA一致；重复ID-year、partial/空结果、
   非有限比例、缺失参考或不一致小时/段计数均失败，不做 nearest fallback。
3. 周期均值为 `Σ(annual_mean × valid_hours) / Σ(valid_hours)`，不是年度均值的
   简单平均；小时比例同样保留分母。年度完整性使用 metric_hours，不假设都是8760。
4. 均值差乘100表示**百分点**；原始小时差同时展示双方有效小时及同分母标志。
   有效小时为0时差值不可得。年度最大连续段计数仅相加，不跨12月/1月拼接。
5. 限制因素展示每年已存 winner。它不包含所有条件逐年分量，故不能推断整个
   五年期间的主因或因果效应；仅能计“年度winner出现年数”。
6. `rule_sha256` 经源实现核验是**处方 workbook 文件SHA**，不是 AST SHA。
   条件键来自 `field:index`。compact没有原始单元格位置，明确标记缺失，不捏造引用。
7. 原 warnings、constraints、publication boundary保留；公式和解释不读取模型。
   FMC及燃料层风是文献代理，雨量缺失、rain guard未应用，不能变成现场测量或批准。

## 入口、测试与复现

- 实现：`src/burnwindows/climatology_comparison.py`、`src/burnwindows/mcp_server.py`。
- 真实协议和独立算术核验：`scripts/demo_mcp_comparison.py`。
- 回归：`tests/test_climatology_comparison.py`；包含覆盖加权、百分点、无观测、来源
  不一致、边界拒绝、输出路径冲突及实际 MCP fixture 客户端。fixture不混入上表。
- 沿用 `requirements-mcp.lock` 的官方 MCP SDK 1.26.0和隔离venv。
- 本地定向24项回归通过（含实际stdio fixture往返）；新增代码Ruff与两模块mypy
  单独核验。全量质量检查交由本分支GitHub CI，不冒称本地跑过全量。

```bash
module load GCCcore/11.3.0 Python/3.11.3
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv-mcp/bin/python scripts/demo_mcp_comparison.py \
  --artifact-catalog "$FLARE_COMPACT_CATALOG" \
  --artifact-id flare-murray-goldfields-burn-id-climatology-1973-2023-v1 \
  --burn-id LM-MGF-MRY-0374 \
  --expected-catalog-sha256 fb72a292a8396cb9a143ea855746cd9c625c6bea487f30417108695395b6c2b8 \
  --expected-artifact-sha256 2f85815eb40c487456ffa3d83a0c58e8a3e6037ca103c41424b188db8c7cfbd9 \
  --evidence-kind real-precomputed --output "$NEW_REDACTED_REPORT" \
  --restricted-detail-output "$NEW_GROUP44_DETAIL_FILE"
```

详细文件必须在已授权 Group44 outputs 中，两个输出均须为不同的新文件；操作员
设置路径，不向模型暴露此权限。只复制脱敏报告到GitHub。当前main/共享求职材料
及简历未修改，由求职单写入者核验后决定采用哪些内容。

## 岗位转译（候选，不自动改简历）

**简历一条：**将43类燃烧处方转为 typed AST，通过网格规则与稀疏面积加权形成
176个 burn ID、51年可审计统计；以只读MCP封装跨年/跨单元比较及规则溯源，在
真实预计算数据上通过三组协议与独立算术核验，为上层Agent提供确定性领域工具。

43类是规则基础设施覆盖；176×51 compact使用选定处方，不暗示全组合。身份仍是
Vocational Placement；行业方任务、团队输入、官方数据与个人扩展见
[原交接](AGENT_APPLICATION_HANDOFF_20260927.md)。不宣称团队已采用或生产部署。

**90秒故事：**“行业方需要比较计划燃烧窗口的阈值敏感性。我负责的工程扩展先把
非结构化处方编译为typed AST，按时间和空间合同计算年度结果，再让上层系统查询。
难点是不能把district天气直接当burn-unit结果，也不能用最近网格填空。我按polygon
相交面积聚合网格规则，形成176个ID的51年统计。最近把已有只读查询接入官方MCP，
增加跨年和跨单元比较：按有效小时加权，差值用百分点，规则解释引用workbook哈希。
三个真实数据案例经过六次协议调用和独立算术核验。复核还发现零观测可能被说成窗口
减少，因此比较返回不可得，并保留缺失警告。结果是可审计的行业分析工具，不是
自主Agent，也不能把天气代理说成安全批准或实际经济收益。”

搜索岗位中仅承担复杂数据、typed tools与可信工程辅助证据，不与Trip/Climate争夺
核心算法版面。没有新增聊天机器人、向量数据库、大模型微调或现场ROI主张。
