# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-fielded-v1
- Dense weight: 0.7
- Milvus search multiplier: 30
- Milvus search mode: native_rrf
- Fielded search: True
- Query rewrite: True
- Reranker: llm (deepseek-v4-flash)
- Rerank strategy: replace
- Reranker cache mode: record
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: 55
- Reranker degraded calls: 0
- Reranker external calls: 55
- Reranker cache hits: 0
- Reranker deterministic calls: 0
- Reranker HTTP attempts: 55
- Reranker judgement digest: ab44612de3b14434b98f827ea82ae21f8be3a533df1e96b0587b4ea325e52c12
- Documents: 28481
- Relations: 7600
- Gold rows total: 180
- Evaluation categories: rag
- Questions scored: 55
- Questions excluded from scoring: 5
- Point-estimate checks passed: no
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Point | CI lower |
|---|---:|:--:|---:|---:|---|---|
| Route accuracy | 1.0000 | 0.9347–1.0000 | 55 | 0.9000 | True | True |
| Permission isolation | 1.0000 | 0.9347–1.0000 | 55 | 1.0000 | True | n/a |
| Base retrieval Recall@3 | 0.8182 | 0.6967–0.8981 | 55 | 0.8500 | False | n/a |
| Base retrieval Top-1 citation accuracy | 0.7091 | 0.5786–0.8123 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.8182 | 0.6967–0.8981 | 55 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.7091 | 0.5786–0.8123 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.4250 | 0.2851–0.5781 | 40 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.8182 | 0.7091 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.7606
- nDCG@3: 0.7685
- Mean answer content recall: 0.4794
- Answer span hit rate, all gold spans: 0.3455 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 5732.92 ms
P95 latency: 8539.42 ms
Latency note: includes live reranker latency when reranking is enabled.
Index time: 20.44 s
