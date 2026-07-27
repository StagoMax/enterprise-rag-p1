# Enterprise RAG P2 Experimental

面向企业工作流的 ACL-first Graph RAG 实验实现。系统不会把所有数据放进向量库：企业专属稳定知识走 Hybrid/Graph RAG，编号和版本走精确检索，实时结构化事实走只读 SQL/API，无权限、无证据或执行请求则拒答或转交。

## P2 已实现

- `rag`、`exact_search`、`tool`、`handoff_or_refuse` 四路路由。
- `auto`、`hybrid`、`graph` 三种检索模式。
- ACL 过滤后的 BM25 + Nemotron 混合检索。
- 在已授权文档子图内执行最多两跳的 `REFERENCES` 扩展。
- 引用返回 `retrieval_mode`、`graph_path`、文档版本和锚点。
- 文档索引和关系图使用同一版本发布，支持运行期成对回滚。
- JWT 测试身份、只读 SQL、审计、反馈、固定金标评测和内部工作台。

## 数据边界

| 数据 | 规模 | 用法 |
|---|---:|---|
| NVIDIA TechQA-RAG-Eval | 1,000 篇 | 模拟企业技术知识，进入 Hybrid/Graph RAG |
| 显式文档引用 | 307 条 | 只从正文中的 `swg...` 引用生成，不自动臆造事实边 |
| BIRD-SQL `financial` | 8 表、32 题 | 只通过只读 SQL 工具访问，不进入向量库 |
| P2 金标 | 180 题 | P1 120 + 跨文档 40 + 图越权 20 |

通用常识、公开百科、邮件/即时通信原始流、实时状态和结构化业务明细仍不进入 RAG。数据来源和许可证见 [DATASET_LICENSES.md](data/DATASET_LICENSES.md)。

## 默认模型与结果

默认实验基线为 Nemotron 3 Embed 1B、1024 维、BM25/向量各 0.5、无重排器。

| 指标 | 结果 | 95% CI | n |
|---|---:|:--:|---:|
| P1 Recall@3 | 95% | 87.8–98.0% | 80 |
| P1 Top-1 引用 | 86.25% | 77.0–92.2% | 80 |
| MRR@3 / nDCG@3 | 95.10% / 95.72% | — | 140 |
| Graph 联合/目标 Recall@3 | 100% / 100% | 91.2–100% | 40 |
| Graph 路径正确率 | 100% | 91.2–100% | 40 |
| Hybrid 同题目标 Recall@3 | 17.5% | 8.8–31.9% | 40 |
| Graph 召回增益 | +82.5 个百分点 | — | 40 |
| Graph / 整体权限隔离 | 100% / 100% | 83.9–100% / 97.9–100% | 20 / 180 |
| 拒答正确率 | 100% | 83.9–100% | 20 |
| 工具答案正确率 | 100% | 83.9–100% | 20 |
| 答案命中率（长度可控子集） | 61.90% | 52.4–70.6% | 105 |
| P50 / P95 | 322.62 / 876.74 ms | — | 180 |
| 1,000 文档索引时间 | 204.95 s | — | — |

Graph 专项门槛全部通过，但整体仍未放行，因为 P1 Top-1 低于 95%。

注意小样本切片：多个 100% 建立在 n=20 上，其 95% 置信区间下界只到 83.9%，不能读成「已证明无泄漏」。答案命中率 61.90% 是本轮新增指标暴露的短板——检索选对了文档，但用户看到的答案文本未必包含金标答案内容，主因是生成器每条摘录截断在 360 字符。完整结论见 [P2 执行与验收报告](docs/05-P2执行与验收报告.md) 和 [P2 当前基线](reports/p2-baseline-current.md)。

## 准备与评测

项目已经包含准备后的 P2 数据。重新生成和评测：

```powershell
.venv\Scripts\python.exe scripts\prepare_p2_data.py
.venv\Scripts\python.exe scripts\evaluate_p2.py --backend hashing --output reports\p2-baseline-hashing.json
.venv\Scripts\python.exe scripts\evaluate_p2.py --backend nemotron --model models\nemotron-3-embed-1b --dimensions 1024 --output reports\p2-baseline-nemotron-1024.json
.venv\Scripts\ruff.exe check .
.venv\Scripts\pytest.exe -p no:cacheprovider
```

对比两次评测，任一指标下滑即以非零码退出，CI 用它来拦截回归：

```powershell
.venv\Scripts\python.exe scripts\compare_reports.py reports\p2-baseline-hashing.json reports\new-run.json --tolerance 0.02
```

### 评测指标

| 指标 | 含义 |
|---|---|
| `route_accuracy` | 四路路由是否选对 |
| `p1_retrieval_recall_at_3` / `p1_top1_citation_accuracy` | 前三条引用命中金标文档 / 首条即命中 |
| `mrr_at_3`、`ndcg_at_3` | 引用排序质量，区分「命中但排第三」和「排第一」 |
| `graph_*` | 图召回、路径正确率，以及相对 Hybrid 的召回增益 |
| `answer_span_hit_rate_fitting` | 用户看到的答案文本是否真的包含金标答案内容 |
| `tool_answer_accuracy` | 只读 SQL 返回值是否等于金标值 |
| `*_isolation`、`refusal_accuracy` | 越权证据是否泄漏、该拒答时是否拒答 |

报告里每个比率都附 95% Wilson 置信区间和样本量。部分切片只有 20 题，`1.0000` 的点估计其区间下界仅约 0.84，看区间比看点估计更可靠。

答案质量指标分两个：`answer_span_hit_rate` 覆盖全部 120 条金标答案，但它会随金标长度单调下降——生成器每条摘录上限 `EXCERPT_CHARS`（360 字符），超长金标答案再好的检索也无法完整呈现。因此门槛只卡长度可控的子集 `answer_span_hit_rate_fitting`，全量值仅作参考。

已验证 Nemotron 权重 SHA256：`f959c3b04e66b42de280bfb97c140cb7e0bfe25e3ecb0b4464c68a8436b2d04f`。

## 启动工作台

快速启动 Hashing 开发后端：

```powershell
.venv\Scripts\uvicorn.exe enterprise_rag.main:app --host 127.0.0.1 --port 8000
```

启动正式 Nemotron P2 基线：

```powershell
$env:RAG_EMBEDDING_BACKEND = 'nemotron'
$env:RAG_NEMOTRON_MODEL_ID = 'models/nemotron-3-embed-1b'
$env:RAG_NEMOTRON_DIMENSIONS = '1024'
$env:RAG_NEMOTRON_DEVICE = 'cuda'
$env:RAG_INDEX_VERSION = 'p2-techqa-1000-v1'
.venv\Scripts\uvicorn.exe enterprise_rag.main:app --host 127.0.0.1 --port 8000
```

首次 Nemotron 启动需要约 5-6 分钟建立 1,000 文档索引。工作台位于 `http://127.0.0.1:8000/`，API 文档位于 `http://127.0.0.1:8000/docs`。

## 主要接口

| 接口 | 用途 |
|---|---|
| `POST /v1/query` | Hybrid/Graph/工具查询 |
| `GET /v1/graph` | 图版本、关系类型和数量 |
| `GET /v1/index` | 当前文档、分块、关系和版本 |
| `POST /v1/index/publish` | 同版本发布文档与关系增量 |
| `POST /v1/index/rollback/{version}` | 检索索引和关系图成对回滚 |
| `GET /v1/evaluation` | 当前 P2 基线 |

## 文档

- [规划文档](docs/01-规划文档.md)
- [技术选型与架构](docs/02-技术选型与架构.md)
- [需求文档](docs/03-需求文档.md)
- [P1 执行与验收报告](docs/04-P1执行与验收报告.md)
- [P2 执行与验收报告](docs/05-P2执行与验收报告.md)
- [端到端实现原理与教学](docs/06-端到端实现原理与教学.md)
