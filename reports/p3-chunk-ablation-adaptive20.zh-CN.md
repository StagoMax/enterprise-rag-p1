# P3 分块参数自适应 Top20 消融

## 结论

三个独立索引均包含 28,481 个唯一文档并已发布到隔离 alias。无 DeepSeek 时，按预先固定的 `Recall@20 → Recall@3 → Top1` 规则，`256/48` 排名第一；只对前两名 `256/48`、`384/64` 运行 DeepSeek `replace` 后，两组 Recall@3 同为 46/55，`384/64` 以 Top1 33/55 对 32/55 略胜。

## 公平检索契约

- 同一份 55 道 curated RAG 金标、Nemotron 1024 维 embedding、dense weight 0.7、native RRF、fielded search、query rewrite。
- `min_retrieval_score=0`，每题必须返回恰好 20 个不同 `document_id`。
- Top20 诊断和 DeepSeek 重排都从 `20 × search_multiplier(30) = 600` 个 chunk 候选起步；不足 20 个不同文档时自适应倍增，最多 4,096 chunks，仍不足则直接失败。
- 三组报告均为 `all_queries_full=true`、`minimum_unique_documents=20`。
- 原生阶段 `reranker=none`；选组完成前没有调用 DeepSeek。

## 独立索引与原生结果

| 子块参数 | Alias | Chunks | Recall@20 | Recall@3 | Top1 | 原生排名 |
|---|---|---:|---:|---:|---:|---:|
| 384/64 | `enterprise_chunks_structured` | 82,228 | 52/55（94.55%） | 36/55（65.45%） | 26/55（47.27%） | 2 |
| 320/48 | `enterprise_chunks_structured_320_48` | 97,288 | 51/55（92.73%） | 36/55（65.45%） | 25/55（45.45%） | 3 |
| 256/48 | `enterprise_chunks_structured_256_48` | 119,467 | 52/55（94.55%） | 39/55（70.91%） | 23/55（41.82%） | 1 |

`320/48` 三项均未超过另外两组，因此没有调用 DeepSeek。

## DeepSeek replace（仅原生前两名）

| 子块参数 | Recall@3 | Top1 | 相对原生 Recall@3 | 相对原生 Top1 |
|---|---:|---:|---:|---:|
| 384/64 | 46/55（83.64%） | 33/55（60.00%） | +10 题 | +7 题 |
| 256/48 | 46/55（83.64%） | 32/55（58.18%） | +7 题 | +9 题 |

两组均为 55 次逻辑调用、55 次外部调用、零降级；最终 `fair` cache 共 55 行，每行严格包含 20 个候选分数。早期使用 90-chunk 基础池的初步结果已废弃并删除对应 cache，不纳入本报告。

## 建议

如果当前目标是 DeepSeek 重排后的 Top3/Top1 综合表现，保留 `384/64` 更合适：它与 `256/48` 的 Recall@3 持平、Top1 多 1 题，同时索引规模少 37,239 chunks（约 31%）。如果未来不使用 LLM 重排、优先原生 Recall@3，则 `256/48` 更好，但会承担更大的索引与构建成本。
