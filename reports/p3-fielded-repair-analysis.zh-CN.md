# TechQA P3 字段化检索修复与归因报告

## 结论

字段化 Milvus 索引、原生 Hybrid Search 消融以及 `replace`/`weighted_rrf` 严格 A/B 均已完成。最终重排使用 `.env` 中的 `https://api.deepseek.com / deepseek-v4-flash`：record 55 次外部判断、零降级；replay 55 次缓存命中、零外部 HTTP，判断序列摘要完全相同。

当前可以确认：原生 Hybrid Search 在这 55 道 RAG 题上没有提高无重排质量，Recall@3 持平、Top-1 少 1 题，但明显降低了检索延迟。DeepSeek 纯重排把 native 检索的 Recall@3 从 0.6727 提升到 0.8364，Top-1 从 0.4364 提升到 0.7273；在当前 `weight=0.5, k=60` 下，基础名次融合反而显著拉低结果，因此应采用 `replace`。

## 已完成的修复

1. 查询改写与并行召回

   保留原始问题，同时生成一个确定性的聚焦查询。聚焦查询使用标题以及识别出的产品、组件、错误码和版本号；原查询和改写查询并行召回，避免只用改写问题丢失上下文。

2. 字段化检索

   新索引同时保存 `dense`、正文/综合 `sparse`、`title_sparse` 和错误码/版本/产品等特征的 `feature_sparse`。这不是 Milvus 自动决定的字段设计，而是应用侧定义 Schema、提取特征并组织查询；Milvus 负责保存字段、BM25 Function、ANN 检索和融合执行。

3. 原生 Milvus Hybrid Search

   使用 `hybrid_search` 和 RRF Ranker 一次执行多路 dense/BM25 检索，同时保留旧的 separate 模式用于消融。每一个 `AnnSearchRequest` 都带相同的 tenant、状态和角色过滤，结果返回后再次做 tenant、ACL 和候选文档集合校验。

4. 文档级聚合与重排

   先合并同一文档的多个高分 chunk，再让重排器比较 20 个不同文档，防止一个长文档的多个 chunk 挤占候选池。支持两种策略：`replace` 只采用模型排序；`weighted_rrf` 融合基础检索名次与模型名次。

5. 严格的重排 A/B

   `replace` 负责 record 外部模型判断，`weighted_rrf` 只 replay 完全相同的判断。缓存键覆盖模型、提示词、问题、候选全文及顺序；报告记录调用序列摘要，并校验两次运行的候选与分数完全一致。0/1 候选、重复缓存键、HTTP 实际尝试次数和 replay miss 也纳入检查。record 支持安全断点续跑，外部失败或不可解析输出会立即停止，不再静默生成伪对照。

6. ACL 与表达式安全

   - 校验 `candidate_document_ids` 后才拼接 Milvus 表达式，并在结果侧精确限制候选集合，修复表达式注入。
   - 使用十六进制 `roles_key` 做角色过滤，修复 Milvus `LIKE` 中下划线被当作单字符通配符的问题。
   - tenant 在 API、JWT、检索表达式和返回结果四层校验；缺失或空 tenant 不再回退到 `demo`。
   - 角色、tenant、文档 ID 均采用完整匹配验证。

7. 索引发布完整性

   断点索引按文档边界提交，禁止向已由 alias 发布的版本继续 append。切换 alias 前验证目标 Collection 的文档 ID 集合与本次 28,481 篇语料完全相等，而不再只检查行数或非空。

8. 外部模型配置

   配置优先级修正为 `RAG_LLM_* > DEEPSEEK_* > NOWCODING_* > OPENTOPIA_*`，兼容 `.env` 里的 `DEEPSEEKMODEL`。本次已验证实际使用 `https://api.deepseek.com` 和 `deepseek-v4-flash`。DeepSeek 与此前 NowCoding 使用独立缓存，结构化供应商错误也会保留错误码，便于区分额度、认证和服务故障。

## 索引验收

- alias：`enterprise_chunks`
- 版本：`p3-techqa-28481-nemotron-1024-fielded-v1`
- 文档：28,481
- chunk 行数：147,358
- 语料文档 ID 与 Collection 文档 ID：完全相等
- 已验证字段：`dense`、`sparse`、`title_sparse`、`feature_sparse`、`roles_key`
- 已验证 Milvus Standalone 2.5.5 的原生 Hybrid、tenant、ACL、角色下划线和候选限制

## 原生 Hybrid 消融

两次运行使用同一个字段化索引、同一份 55 题 curated gold、同样的原始+改写查询、Top-3、候选深度和无重排配置。Gold SHA256 为 `add680e5be945fd9b2aee07c25b6a0d103228a9f7432896fea0746a5c162d74c`。

| 指标 | separate | native RRF | native - separate |
|---|---:|---:|---:|
| Recall@3 | 0.6727（37/55） | 0.6727（37/55） | 0 |
| Top-1 | 0.4545（25/55） | 0.4364（24/55） | -0.0181 |
| MRR@3 | 0.5394 | 0.5303 | -0.0091 |
| nDCG@3 | 0.5565 | 0.5533 | -0.0032 |
| Fitting answer hit | 0.2750 | 0.2750 | 0 |
| Answer content recall | 0.4377 | 0.4377 | 0 |
| P50 | 1355.66 ms | 797.46 ms | -41.2% |
| P95 | 2552.57 ms | 1263.45 ms | -50.5% |
| Gold 进入真实 Top-20 | 51/55 | 51/55 | 0 |

因此原生 Hybrid 的价值目前是减少多次客户端往返和本地合并开销，不是提升排序质量。4 道题的正确文档没有进入 Top-20，任何只重排现有 20 个候选的方案都无法修复；其余错误才可能通过重排或基础排序调权改善。

## 与历史结果的关系

同一组 55 个 RAG ID 的历史结果如下，但旧报告没有保存 gold SHA256，因此这里只作为桥接对照：

| 指标 | 历史无重排 | 历史 NowCoding 重排 |
|---|---:|---:|
| Recall@3 | 0.6909（38/55） | 0.8364（46/55） |
| Top-1 | 0.5818（32/55） | 0.6727（37/55） |
| MRR@3 | 0.6273 | 0.7424 |
| nDCG@3 | 0.6365 | 0.7476 |
| Fitting answer hit | 0.3000 | 0.3500 |
| Answer content recall | 0.4344 | 0.4535 |
| P50 | 707.34 ms | 8452.48 ms |
| P95 | 1123.93 ms | 13063.83 ms |

历史结果说明 LLM 重排有潜力，但不能直接推出新字段化方案也会达到相同提升。新旧运行改变了索引、查询改写、字段、融合路径和运行时间；没有单变量实验时，只能把差异归因给组合方案。当前新方案在“无重排”口径下反而比历史无重排低 1 道 Recall@3、低 7–8 道 Top-1，说明字段权重和应用层二次打分仍需调优。

## DeepSeek 严格重排 A/B

| 指标 | replace | weighted RRF | weighted - replace |
|---|---:|---:|---:|
| Recall@3 | 0.8364（46/55） | 0.7636（42/55） | -0.0728 |
| Top-1 | 0.7273（40/55） | 0.5091（28/55） | -0.2182 |
| MRR@3 | 0.7727 | 0.6242 | -0.1485 |
| nDCG@3 | 0.7758 | 0.6470 | -0.1288 |
| Fitting answer hit | 0.4000 | 0.3500 | -0.0500 |
| Answer content recall | 0.4902 | 0.4540 | -0.0362 |

配对结果同样明确：Recall@3 有 42 题两者都对、4 题仅 replace 对、0 题仅 weighted 对；Top-1 有 28 题两者都对、12 题仅 replace 对、0 题仅 weighted 对。基础检索名次本身较弱，0.5 权重把一部分 DeepSeek 已经排对的文档重新拉低，因此当前配置应采用纯 `replace`。这只否定当前融合参数，不代表所有权重都无效；如果继续研究，可单独扫描更高模型权重，例如 0.7、0.8、0.9，但不能用本轮指标声称它们会更好。

record 统计为 55 次逻辑调用、55 次外部 HTTP、零降级；replay 为 55 次调用、55 次 cache hit、0 次外部 HTTP。两份报告的 judgement digest 均为 `ca0c5e6bd9558170fb66c796a1a54c5dc74f6289408ca032b280d1b6bb578cda`。比较器已通过全部受控实验检查。replay 延迟不包含外部 API，不能与 replace 延迟直接比较。

## 结构化父子分块复测

真正的 `structured-parent-child-v1` 使用独立的 `enterprise_chunks_structured` Collection，共 82,228 个 384-token 子块和 32,219 个最大 1,200-token 父块。相同 DeepSeek `replace` 下，旧字符分块为 Recall@3 0.8364、Top-1 0.7273；结构化分块为 Recall@3 0.8000、Top-1 0.6545，分别少 2 题和 4 题。

结构化分块的 Gold Top-20 覆盖从 51/55 提升到 52/55，但进入候选后未排进 Top-3 的题目从 5 增加到 8。当前父块只在最终 Top-3 排完后补取，DeepSeek 实际判断的仍是受字符预算限制的子块，因此新策略改善了召回池，却与现有重排输入不匹配。当前不应切换 alias；详细结果见 `reports/p3-structured-deepseek-evaluation.zh-CN.md`。

## 评测门槛说明

当前 RAG 子集只有 55 题。即使 Top-1 达到 55/55，Wilson 95% 下界也约为 0.9347，仍低于 0.95 的置信下界门槛；至少需要约 73 道全部命中样本，才可能跨过该门槛。因此应同时报告点估计是否达标与置信区间检查，不能把 `report.passed=false` 简化解释为系统功能失败。

## 父块重排兼容性修复

结构化索引此前只在最终 Top-3 排定后补取父块，DeepSeek 实际看不到父块上下文。现已把父块补取前移到文档候选聚合之后、重排之前，并按 `parent_id` 去重读取；每个文档的重排输入仍限制为 680 字符，避免提示词体积失控。旧索引没有父块时保持原有子块回退路径。

修复后 structured + DeepSeek `replace` 的 Recall@3 从 44/55 提升到 46/55，Top-1 从 36/55 变为 35/55；`weighted_rrf` 为 Recall@3 41/55、Top-1 31/55。这验证了父块进入重排能修复一部分候选内排序损失，但旧字符分块 + `replace` 仍以 40/55 的 Top-1 保持综合最优，所以暂不切换生产 alias。
