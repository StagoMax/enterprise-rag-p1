# Enterprise RAG P3 Scale Experimental

面向企业工作流的 ACL-first Hybrid / Graph RAG 实验实现。系统不会把所有数据放进向量库：企业专属稳定知识走 Hybrid/Graph RAG，编号和版本走精确检索，实时结构化事实走只读 SQL/API，无权限、无证据或执行请求则拒答或转交。

当前阶段是在公开代理语料上验证全量索引、持久化版本、权限下推和大规模检索，不代表已经完成真实企业部门试点。

## 当前已实现

- `rag`、`exact_search`、`tool`、`handoff_or_refuse` 四路可审计路由。
- `auto`、`hybrid`、`graph` 三种检索模式。
- Nemotron 3 Embed 1B、Milvus 原生 BM25 与稠密向量双路召回。
- ACL 作为 Milvus 检索表达式前置执行，结果侧再做一次防御性复核。
- 在已授权文档子图内执行最多两跳的 `REFERENCES` 扩展。
- 严格返回 Top-3 不同文档，避免同一长文档的相邻分块占满引用。
- 每个索引版本使用独立 Milvus collection，通过 alias 原子发布和持久化回滚。
- 全量索引支持分段写入、断点续传，完整写入后才切换线上 alias。
- OpenAI-compatible 受引用约束生成、失败重试和摘录式降级能力。
- Docling 优先的 PDF/Office/HTML/Markdown/文本解析、表格分流与 OCR 降级框架。
- JWT 测试身份、只读 SQL、审计、反馈、固定金标评测和内部工作台。

## 当前数据和索引

| 工件 | 当前 P3 规模 | 用法 |
|---|---:|---|
| NVIDIA TechQA-RAG-Eval | 28,481 篇 | 全量公开代理技术知识，进入 Hybrid/Graph RAG |
| 文档分块 | 147,358 | Nemotron 1024 维稠密向量 + Milvus BM25 |
| 显式文档引用 | 7,600 条 | 只从正文中的 `swg...` 引用生成 |
| P3 金标 | 180 题 | 普通检索、精确检索、工具、Graph、越权和无证据 |
| BIRD-SQL `financial` | 8 表、32 题 | 只通过只读 SQL 工具访问，不进入向量库 |

通用常识、公开百科、邮件/即时通信原始流、实时状态和结构化业务明细仍不进入 RAG。数据来源和许可证见 [DATASET_LICENSES.md](data/DATASET_LICENSES.md)。

## 当前 P3 基线

正式配置：Milvus Standalone、索引 `p3-techqa-28481-nemotron-1024-v3`、Nemotron 1024 维、稠密权重 0.70、候选扩展倍数 30、严格 Top-3 不同文档、无重排器、摘录式回答。

| 指标 | 结果 | 95% CI | 门槛 |
|---|---:|:--:|---:|
| 路由正确率 | 100% | 97.91–100% | 90% |
| 基础检索 Recall@3 | 65.00% | 54.08–74.55% | 85% |
| 基础检索 Top-1 | 62.50% | 51.55–72.31% | 95% |
| MRR@3 / nDCG@3 | 81.67% / 81.87% | - | 观察项 |
| Graph 联合 / 目标 Recall@3 | 100% / 100% | 91.24–100% | 80% / 85% |
| Graph 路径正确率 | 100% | 91.24–100% | 95% |
| Graph 相对 Hybrid 增益 | +32.5 个百分点 | - | +15 个百分点 |
| Graph / 整体权限隔离 | 100% / 100% | 83.89–100% / 97.91–100% | 100% |
| 拒答 / 工具答案正确率 | 100% / 100% | 83.89–100% | 90% / 85% |
| 长度可容纳答案片段命中率 | 55.24% | 45.71–64.40% | 55% |
| P50 / P95 | 697.18 / 1,576.22 ms | - | 实验基线 |

P3 整体仍未通过发布门槛。主要阻断项是普通语义检索扩展至 28,481 文档后，Recall@3 和 Top-1 明显下降；Graph、权限、拒答和工具专项继续通过。完整结论见 [P3 执行与验收报告](docs/07-P3执行与验收报告.md) 和 [优化后机器报告](reports/p3-milvus-nemotron-1024-optimized.json)。

## 构建 P3 数据

项目已包含处理后的 P3 数据。需要从原始 TechQA 重新生成时：

```powershell
.venv\Scripts\python.exe scripts\prepare_p2_data.py `
  --output data\processed\techqa_p3 `
  --documents 28481
```

## 启动 Milvus 和建立索引

启动 Milvus Standalone、etcd 和 MinIO：

```powershell
docker compose -f docker-compose.milvus.yml up -d
```

全量 Nemotron 索引支持断点续传，默认每段处理 800 篇：

```powershell
scripts\index_p3_nemotron.cmd
```

脚本将数据写入未发布 collection；只有 28,481 篇全部完成后才把 `enterprise_chunks` alias 切换到新版本。当前已发布 collection 包含 147,358 个分块。

字段化检索实验使用独立索引版本，增加正文、标题、错误码/版本三个 BM25 分支，并启用“原问题 + 聚焦问题”并行召回：

```powershell
scripts\index_p3_fielded.cmd
```

结构感知父子分块使用独立的 `enterprise_chunks_structured` alias，不会切换上面的旧索引。
子块用于召回和重排，命中后展开到同一逻辑章节回答：

```powershell
scripts\index_p3_structured.cmd
scripts\evaluate_p3_structured.cmd
```

默认参数为子块 384 tokens、重叠 64 tokens、父章节 1,200 tokens；索引报告会记录完整
分块契约。`scripts\index_milvus.py --chunk-strategy legacy` 可复现旧字符分块基线。

先在无重排条件下对比应用侧分支合并与 Milvus 原生 Hybrid，并保留 Top-20 候选诊断：

```powershell
scripts\evaluate_p3_retrieval_ablation.cmd separate
scripts\evaluate_p3_retrieval_ablation.cmd native_rrf
```

原生 Hybrid + DeepSeek V4 Flash 重排保留两种受控策略。`replace` 首次运行从 `.env` 的 DeepSeek 端点取得判分并写入独立缓存，`weighted_rrf` 严格回放同一批判分；两次运行除最终排序策略外配置相同：

```powershell
scripts\evaluate_p3_fielded.cmd replace
scripts\evaluate_p3_fielded.cmd weighted_rrf

.venv\Scripts\python.exe scripts\compare_rerank_strategies.py `
  reports\p3-fielded-native-deepseek-v4-flash-replace.json `
  reports\p3-fielded-native-deepseek-v4-flash-weighted_rrf.json `
  --output reports\p3-fielded-deepseek-v4-flash-rerank-comparison.json
```

只有 `replace` 记录阶段会使用 `.env` 中的 OpenAI-compatible 端点处理公开 TechQA 问题和候选片段，并产生相应 API 调用费用。比较器会核对调用数、候选与判分序列摘要；任何 cache miss、降级或序列漂移都会中止比较。`weighted_rrf` 回放阶段的延迟不代表生产外部调用延迟。

## 正式评测和启动服务

```powershell
scripts\evaluate_p3_nemotron.cmd
scripts\run_p3_nemotron_server.cmd
```

工作台位于 `http://127.0.0.1:8000/`，API 文档位于 `http://127.0.0.1:8000/docs`。

当前 P3 启动脚本显式使用 `RAG_LLM_BACKEND=extractive`，所以正式报告评测的是可复现的摘录式回答。若配置 OpenAI-compatible 模型、地址和密钥，服务可切换为受引用约束生成；模型不可用时自动降级为摘录，不允许凭空生成。

## 快速开发检查

```powershell
.venv\Scripts\ruff.exe check .
.venv\Scripts\pytest.exe -p no:cacheprovider
.venv\Scripts\python.exe scripts\verify_ui.py --url http://127.0.0.1:8000
```

对比新旧评测，指标下滑时以非零码阻断：

```powershell
.venv\Scripts\python.exe scripts\compare_reports.py `
  reports\p3-milvus-nemotron-1024-optimized.json `
  reports\new-run.json `
  --tolerance 0.02
```

## 主要接口

| 接口 | 用途 |
|---|---|
| `POST /v1/query` | Hybrid/Graph/精确/工具查询 |
| `GET /v1/graph` | 图版本、关系类型和数量 |
| `GET /v1/index` | 当前文档、分块、关系和版本 |
| `POST /v1/index/publish` | 同版本发布文档与关系增量 |
| `POST /v1/index/rollback/{version}` | 检索索引和关系图成对回滚 |
| `GET /v1/evaluation` | 当前实验基线 |

## 文档

- [规划文档](docs/01-规划文档.md)
- [技术选型与架构](docs/02-技术选型与架构.md)
- [需求文档](docs/03-需求文档.md)
- [P1 执行与验收报告](docs/04-P1执行与验收报告.md)
- [P2 执行与验收报告](docs/05-P2执行与验收报告.md)
- [端到端实现原理与教学](docs/06-端到端实现原理与教学.md)
- [P3 执行与验收报告](docs/07-P3执行与验收报告.md)
