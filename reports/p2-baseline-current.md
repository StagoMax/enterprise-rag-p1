# P2 Graph RAG Baseline: nemotron

- Documents: 1000
- Relations: 307
- Questions: 180
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Passed |
|---|---:|:--:|---:|---:|---|
| route_accuracy | 1.0000 | 0.9791–1.0000 | 180 | 0.9000 | True |
| p1_retrieval_recall_at_3 | 0.9500 | 0.8784–0.9804 | 80 | 0.8500 | True |
| p1_top1_citation_accuracy | 0.8625 | 0.7703–0.9215 | 80 | 0.9500 | False |
| graph_joint_recall_at_3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8000 | True |
| graph_target_recall_at_3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8500 | True |
| graph_path_accuracy | 1.0000 | 0.9124–1.0000 | 40 | 0.9500 | True |
| graph_recall_gain | 0.8250 | — | — | 0.1500 | True |
| graph_acl_isolation | 1.0000 | 0.8389–1.0000 | 20 | 1.0000 | True |
| permission_isolation | 1.0000 | 0.9791–1.0000 | 180 | 1.0000 | True |
| refusal_accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.9000 | True |
| tool_answer_accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.8500 | True |
| answer_span_hit_rate_fitting | 0.6190 | 0.5235–0.7062 | 105 | 0.5500 | True |

## Ranking and answer quality

- MRR@3: 0.9510
- nDCG@3: 0.9572
- Mean answer content recall: 0.6838
- Answer span hit rate, all gold spans: 0.5667 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 322.62 ms
P95 latency: 876.74 ms
Index time: 204.95 s
