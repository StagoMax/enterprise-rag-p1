# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-structured-256-48-v1
- Dense weight: 0.7
- Milvus search multiplier: 30
- Milvus search mode: native_rrf
- Fielded search: True
- Query rewrite: True
- Reranker: llm (gpt-5.6-sol)
- Rerank strategy: replace
- Reranker cache mode: record
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: 115
- Reranker degraded calls: 0
- Reranker external calls: 113
- Reranker cache hits: 2
- Reranker deterministic calls: 0
- Reranker HTTP attempts: 113
- Reranker judgement digest: cbd44204067652bd03a3b57c5a6647a6b227e27efcf8063cafab3d3b0c8ffdc1
- Documents: 28481
- Relations: 7600
- Gold rows total: 240
- Evaluation categories: rag
- Questions scored: 115
- Questions excluded from scoring: 5
- Point-estimate checks passed: no
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Point | CI lower |
|---|---:|:--:|---:|---:|---|---|
| Route accuracy | 1.0000 | 0.9677–1.0000 | 115 | 0.9000 | True | True |
| Permission isolation | 1.0000 | 0.9677–1.0000 | 115 | 1.0000 | True | n/a |
| Base retrieval Recall@3 | 0.8783 | 0.8060–0.9261 | 115 | 0.8500 | True | n/a |
| Base retrieval Top-1 citation accuracy | 0.6609 | 0.5704–0.7409 | 115 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.8783 | 0.8060–0.9261 | 115 | 0.8500 | True | False |
| Semantic RAG Top-1 citation accuracy | 0.6609 | 0.5704–0.7409 | 115 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.3735 | 0.2772–0.4810 | 83 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.8783 | 0.6609 | 115 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.7638
- nDCG@3: 0.7872
- Mean answer content recall: 0.4797
- Answer span hit rate, all gold spans: 0.3043 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 15433.93 ms
P95 latency: 24154.0 ms
Latency note: includes live reranker latency when reranking is enabled.
Index time: 21.27 s
