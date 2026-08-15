# P3 原 55 题强制 GraphRAG 公平评测

## 结论

在原 55 道普通 `rag` 问题上，强制 GraphRAG 没有优于 Hybrid。当前实现会保留基础检索的第 1 名，但把图邻居插入后续位置，因此没有提升 Top-1，却会挤掉原本位于第 2/3 名的标准来源。

这不表示 GraphRAG 本身无效；它表示不应把图扩展无条件应用于以单文档答案为主的普通 RAG 题。GraphRAG 更适合关系、依赖和多跳问题，并应由路由器选择性启用。

## 公平口径

- 问题：锁定既有 Sol 报告中的原 55 个 `rag` ID。
- Gold：`4952a87821d024099089322293b2074bea7715a2f117cef8b6d97cfa04613a1b`。
- 分块：`structured_parent_child`，child `256/48`，parent `1200`。
- 向量：Nemotron 1024 维；Milvus collection `enterprise_chunks_structured_256_48`。
- 检索：fielded native RRF、query rewrite、adaptive recall、Top-3。
- 重排：候选 20，`replace`；只测试 DeepSeek `deepseek-v4-flash` 和 Luna `gpt-5.6-luna`。
- Graph：`retrieval_mode=graph` 强制启用；两份 Graph 报告均为 `graph_used_count=55`。
- 公平控制：Graph 运行以相应 Hybrid 的 55 条 LLM 重排缓存为种子，只对新增图候选调用模型；Hybrid 也按同一当前 Gold 重跑校准。

## 结果

| 重排模型 | 检索模式 | Recall@3 | Top-1 | MRR@3 | nDCG@3 | 短答案命中 | Answer recall |
|---|---|---:|---:|---:|---:|---:|---:|
| DeepSeek | Hybrid | 47/55（85.45%） | 32/55（58.18%） | 0.7091 | 0.7379 | 31.71% | 0.4535 |
| DeepSeek | GraphRAG | 43/55（78.18%） | 32/55（58.18%） | 0.6636 | 0.6848 | 29.27% | 0.4358 |
| Luna | Hybrid | 48/55（87.27%） | 33/55（60.00%） | 0.7273 | 0.7564 | 31.71% | 0.4660 |
| Luna | GraphRAG | 42/55（76.36%） | 33/55（60.00%） | 0.6727 | 0.6820 | 29.27% | 0.4386 |

GraphRAG 相对同模型 Hybrid：

- DeepSeek：Recall@3 `-4/55`（`-7.27 pp`），Top-1 不变，MRR `-0.0455`。
- Luna：Recall@3 `-6/55`（`-10.91 pp`），Top-1 不变，MRR `-0.0546`。
- 两个模型均为 `0` 道 Top-3 rescue。
- DeepSeek 有 21/55 题返回非空图路径，最终 citation 集合改变 20/55。
- Luna 有 22/55 题返回非空图路径，最终 citation 集合改变 19/55。

延迟不用于生产性能比较：为了冻结 LLM 判断，校准运行包含大量缓存命中，会低估真实在线重排耗时。

## Graph 造成的配对退化

- DeepSeek：`rag-003`、`rag-031`、`rag-039`、`rag-051`。
- Luna：`rag-009`、`rag-025`、`rag-028`、`rag-031`、`rag-039`、`rag-051`。
- 两个模型都没有 Graph 新增命中；`rag-031`/`rag-039` 是同一 SCA 问题的两个问法。

## 未命中 Gold 的相关性审计

两份 Graph 报告的未命中并集为 15 题。逐题检查问题、标准答案、Gold 文档和实际 Top-3 文档后：没有发现明显错误的 Gold；14/15 的 Gold 明确属于最相关答案，`rag-045` 的 Gold 能支持标准答案，但问题文本信息不足，无法要求它成为唯一 Top 相关。

| ID | 未命中模型 | Gold 审计 | 对 exact-ID 指标的判断 |
|---|---|---|---|
| rag-002 | Luna | Gold 精确解释 BPM/WAS 升级后的 2035 与 component auth alias | Top-3 的中文同主题文档及 `swg21662193` 也直接解释同一根因，属于等价答案 |
| rag-003 | DeepSeek、Luna | Gold 明确回答 ReqPro 插件只提供 32 位、64 位安装不支持 | 其他 64 位/ReqPro 文档没有回答该插件支持结论，是真漏召 |
| rag-005 | DeepSeek、Luna | Gold 是题目所问 IIB/WMB Hypervisor Red Hat 安全公告 | 问题未给 CVE；Top-3 是同名、不同 CVE 批次公告，Gold 集不完整，exact-ID 过严 |
| rag-009 | DeepSeek、Luna | Gold 是 HATS 9.0 下载/安装入口 | DeepSeek 的 `swg21963975` 给出 HATS/WebFacing 下载部件号，可视为等价；Luna 结果较弱 |
| rag-011 | DeepSeek | Gold 精确给出 DWC 9.3 禁用 SSLv3、旧 TWS 默认 SSLv3 的版本兼容根因 | Top-3 是一般证书/连接故障，是真漏召 |
| rag-025 | Luna | Gold 列出集群仍执行旧 ruleset 的完整原因 | `swg21458245` 与 `swg21585251` 直接覆盖 XU 通知/热部署原因，属于等价可答证据 |
| rag-028 | Luna | Gold 精确给出 Linux `ulimit`/NOFILE 诊断与调整 | Top-3 是 BPM 文件泄漏和修复包，未回答 Portal 场景，是真漏召 |
| rag-031 | DeepSeek、Luna | Gold 给出 `SCA.recycleDestinations=false` 的直接解决方案 | `JR43392` 也是更新 SCA module 删除 destination 的高相关 APAR，但不等同于该配置解法 |
| rag-033 | DeepSeek、Luna | Gold 精确对应 NFS/挂载盘安装，结论是只装本地磁盘 | Top-3 为一般 Installation Manager 启动/依赖问题，是真漏召 |
| rag-035 | DeepSeek | Gold 同时命中题目列出的 ADMA5008E/ADMA0063E/ADMA5069E/WASX7017E，并解释旧 OSGi cache | `swg21696074` 虽也是 CF14，但异常与根因不同；Gold 更强 |
| rag-039 | DeepSeek、Luna | 与 rag-031 同一意图；Gold 是直接配置解法 | 同样召回 `JR43392` APAR，属于高相关替代但未命中精确 Gold |
| rag-045 | DeepSeek、Luna | Gold 解释 server plugin JAR 中内部类导致运行时 NoClassDefFoundError | 问题没有写出 plugin JAR 细节；Top-3 的 runtime classpath 文档也合理，Gold 唯一性不足 |
| rag-046 | DeepSeek、Luna | Gold 精确回答跨 major firmware downgrade 必须 reinitialize、直接降级不受支持 | Top-3 是 rollback 边缘问题/APAR，未回答受支持流程，是真漏召 |
| rag-051 | DeepSeek、Luna | Gold 精确说明 CCDT 与 XA connection 不受支持 | `IV32387`/`IV23924` 同样直接覆盖 XA + CCDT/queue-manager group，属于等价答案 |
| rag-059 | DeepSeek、Luna | Gold 给出 Agent 侧 `KBN_SOMA_PROTOCOL=TLSv1.2` | Top-3 只讲 DataPower 服务端 TLS、证书或一般 Agent 认证，是真漏召 |

因此，官方 exact-ID 指标应继续保留，但至少要增加一个“可接受替代来源/同簇文档”指标。按人工审计，DeepSeek 和 Luna 各有 5/6 个明确的等价证据型假阴性；`rag-045` 另列为边界题，不建议直接改 Gold，建议先补充问题上下文。

## 建议

1. 保留 GraphRAG，但继续由 router 只对关系/多跳意图启用，不要对全部普通 RAG 强制开启。
2. 将基础候选与图候选统一融合/重排，避免当前 `[base top1, graph neighbors, base remainder]` 固定插入策略挤掉第 2/3 名 Gold。
3. 为 `rag-002`、`rag-005`、`rag-009`、`rag-025`、`rag-031`、`rag-039`、`rag-051`补可接受替代来源或文档簇；单独复核 `rag-045` 的问题文本。
4. Graph 的正式价值应继续用专门的 `graph_rag` 多跳集合衡量；本报告只回答“把同一批普通 RAG 题强制走 Graph 会怎样”。
