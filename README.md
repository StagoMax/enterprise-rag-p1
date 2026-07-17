# Enterprise RAG P1

这是一个面向企业工作流的可运行 P1 闭环，不是“把所有数据塞进向量库”的演示。系统先判断问题应走 RAG、精确检索、只读工具还是拒答，再在检索打分前执行 ACL 过滤，并返回可追溯引用和审计记录。

## 已实现范围

- `rag`、`exact_search`、`tool`、`handoff_or_refuse` 四路路由。
- 签名测试身份，角色来自令牌；客户端不能在查询中自行声明权限。
- ACL 过滤后的 BM25 + 向量混合检索，文档级引用去重，证据不足时拒答。
- 仅允许白名单表和单条 `SELECT` 的只读 SQLite 工具。
- 查询、权限决策、引用、反馈和评测报告的审计闭环。
- 查询、知识、评测和审计四个视图的内部工作台。

## P1 数据边界

| 数据 | 实际规模 | 用法 |
|---|---:|---|
| NVIDIA TechQA-RAG-Eval 的 WebSphere 子集 | 200 篇文档 | 进入 RAG，模拟企业内部技术知识 |
| BIRD-SQL Mini-Dev 的 `financial` 数据库 | 8 张表、32 题 | 只通过只读 SQL 工具访问，不进入向量库 |
| P1 金标集 | 120 题 | 60 RAG、20 精确检索、20 工具、10 越权、10 无证据 |

通用常识、公开百科、邮件/即时通信原始流、实时状态和结构化业务明细不进入 RAG。数据集许可证和来源见 [DATASET_LICENSES.md](data/DATASET_LICENSES.md)。

## 本地运行

无需模型权重的开发模式：

```powershell
uv sync --extra dev
uv run uvicorn enterprise_rag.main:app --host 127.0.0.1 --port 8000
```

打开工作台 `http://127.0.0.1:8000/`，API 文档位于 `http://127.0.0.1:8000/docs`。

启用已经下载到本项目的 Nemotron 基线：

```powershell
$env:RAG_EMBEDDING_BACKEND = 'nemotron'
$env:RAG_NEMOTRON_MODEL_ID = 'models/nemotron-3-embed-1b'
$env:RAG_NEMOTRON_DIMENSIONS = '1024'
$env:RAG_NEMOTRON_DEVICE = 'cuda'
$env:RAG_DENSE_WEIGHT = '0.5'
uv run uvicorn enterprise_rag.main:app --host 127.0.0.1 --port 8000
```

模型目录不纳入版本控制。已验证的 Nemotron 权重 SHA256 为 `f959c3b04e66b42de280bfb97c140cb7e0bfe25e3ecb0b4464c68a8436b2d04f`；BGE-M3 对照权重 SHA256 为 `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38`。

## 评测

默认配置是 Nemotron 3 Embed 1B、1024 维、BM25/向量各 0.5、无重排器：

| 指标 | 结果 | 门槛 |
|---|---:|---:|
| 路由正确率 | 100% | 90% |
| Recall@3 | 96.25% | 85% |
| Top-1 引用正确率 | 87.5% | 95% |
| 拒答正确率 | 100% | 90% |
| 权限隔离 | 100% | 100% |
| 工具回答正确率 | 100% | 85% |
| P95 查询延迟 | 283.27 ms | 6 s |

Top-1 引用仍未达到 95%，所以它是当前开发基线，不是进入 Graph RAG 阶段的放行结论。BGE-M3 的 Recall@3 同为 96.25%，Top-1 为 85%；2048 维没有带来质量收益；MiniLM 重排器降低了 Top-1 并增加延迟，均未被选为默认项。完整结果见 [模型对照](reports/model-comparison.md) 和 [当前基线](reports/baseline-current.md)。

复现命令：

```powershell
uv sync --extra dev --extra models
uv run python scripts/evaluate_p1.py --backend nemotron --model models/nemotron-3-embed-1b --dimensions 1024 --dense-weight 0.5 --output reports/baseline-nemotron-1024-bm25.json
uv run python scripts/validate_bird_financial.py
uv run ruff check .
uv run pytest
uv run python scripts/verify_ui.py --url http://127.0.0.1:8000
```

## 项目文档

- [规划文档](docs/01-规划文档.md)
- [技术选型与架构](docs/02-技术选型与架构.md)
- [需求文档](docs/03-需求文档.md)
- [P1 执行与验收报告](docs/04-P1执行与验收报告.md)
