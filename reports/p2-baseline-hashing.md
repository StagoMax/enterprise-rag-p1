# P2 Graph RAG Baseline: hashing

- Documents: 1000
- Relations: 307
- Questions: 180
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Passed |
|---|---:|:--:|---:|---:|---|
| route_accuracy | 1.0000 | 0.9791–1.0000 | 180 | 0.9000 | True |
| p1_retrieval_recall_at_3 | 0.8875 | 0.7998–0.9397 | 80 | 0.8500 | True |
| p1_top1_citation_accuracy | 0.8000 | 0.6995–0.8730 | 80 | 0.9500 | False |
| graph_joint_recall_at_3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8000 | True |
| graph_target_recall_at_3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8500 | True |
| graph_path_accuracy | 1.0000 | 0.9124–1.0000 | 40 | 0.9500 | True |
| graph_recall_gain | 0.8000 | — | — | 0.1500 | True |
| graph_acl_isolation | 1.0000 | 0.8389–1.0000 | 20 | 1.0000 | True |
| permission_isolation | 1.0000 | 0.9791–1.0000 | 180 | 1.0000 | True |
| refusal_accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.9000 | True |
| tool_answer_accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.8500 | True |
| answer_span_hit_rate_fitting | 0.5905 | 0.4948–0.6797 | 105 | 0.5500 | True |

## Ranking and answer quality

- MRR@3: 0.9198
- nDCG@3: 0.9260
- Mean answer content recall: 0.6748
- Answer span hit rate, all gold spans: 0.5417 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 203.08 ms
P95 latency: 437.19 ms
Index time: 3.04 s
