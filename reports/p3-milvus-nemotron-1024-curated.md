# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-v3
- Dense weight: 0.7
- Milvus search multiplier: 30
- Documents: 28481
- Relations: 7600
- Gold rows total: 180
- Questions scored: 175
- Questions excluded from scoring: 5
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Passed |
|---|---:|:--:|---:|---:|---|
| Route accuracy | 1.0000 | 0.9785–1.0000 | 175 | 0.9000 | True |
| Base retrieval Recall@3 | 0.7333 | 0.6237–0.8202 | 75 | 0.8500 | False |
| Base retrieval Top-1 citation accuracy | 0.7067 | 0.5956–0.7976 | 75 | 0.9500 | False |
| Graph joint Recall@3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8000 | True |
| Graph target Recall@3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8500 | True |
| Graph path accuracy | 1.0000 | 0.9124–1.0000 | 40 | 0.9500 | True |
| Graph recall gain | 0.3250 | — | — | 0.1500 | True |
| Graph ACL isolation | 1.0000 | 0.8389–1.0000 | 20 | 1.0000 | True |
| Permission isolation | 1.0000 | 0.9785–1.0000 | 175 | 1.0000 | True |
| Refusal accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.9000 | True |
| Tool answer accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.8500 | True |
| Fitting answer-span hit rate | 0.5900 | 0.4920–0.6813 | 100 | 0.5500 | True |

## Ranking and answer quality

- MRR@3: 0.8624
- nDCG@3: 0.8620
- Mean answer content recall: 0.6583
- Answer span hit rate, all gold spans: 0.5391 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 313.94 ms
P95 latency: 710.43 ms
Index time: 16.83 s
