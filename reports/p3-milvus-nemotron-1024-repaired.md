# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-v3
- Dense weight: 0.7
- Milvus search multiplier: 30
- Reranker: none (none)
- Answer generator: extractive (EvidenceAnswerGenerator)
- Documents: 28481
- Relations: 7600
- Gold rows total: 180
- Questions scored: 175
- Questions excluded from scoring: 5
- Point-estimate checks passed: no
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Point | CI lower |
|---|---:|:--:|---:|---:|---|---|
| Route accuracy | 1.0000 | 0.9785–1.0000 | 175 | 0.9000 | True | True |
| Base retrieval Recall@3 | 0.7733 | 0.6666–0.8534 | 75 | 0.8500 | False | n/a |
| Base retrieval Top-1 citation accuracy | 0.6933 | 0.5817–0.7861 | 75 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.6909 | 0.5597–0.7972 | 55 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.5818 | 0.4503–0.7026 | 55 | 0.9500 | False | False |
| Graph joint Recall@3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8000 | True | True |
| Graph target Recall@3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8500 | True | True |
| Graph path accuracy | 1.0000 | 0.9124–1.0000 | 40 | 0.9500 | True | False |
| Graph recall gain | 0.2250 | — | — | 0.1500 | True | n/a |
| Graph ACL isolation | 1.0000 | 0.8389–1.0000 | 20 | 1.0000 | True | n/a |
| Permission isolation | 1.0000 | 0.9785–1.0000 | 175 | 1.0000 | True | n/a |
| Refusal accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.9000 | True | False |
| Tool answer accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.8500 | True | False |
| Fitting answer-span hit rate | 0.6000 | 0.5020–0.6906 | 100 | 0.5500 | True | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.6909 | 0.5818 | 55 |
| Exact search | 1.0000 | 1.0000 | 20 |

Candidate diagnostics: enabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.8677
- nDCG@3: 0.8710
- Mean answer content recall: 0.6513
- Answer span hit rate, all gold spans: 0.5391 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 789.04 ms
P95 latency: 1548.72 ms
Index time: 32.58 s
