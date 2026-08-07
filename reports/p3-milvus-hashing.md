# Graph RAG Evaluation: hashing on milvus

- Index version: p3-techqa-28481-v1
- Documents: 28481
- Relations: 7600
- Questions: 180
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Passed |
|---|---:|:--:|---:|---:|---|
| route_accuracy | 0.9556 | 0.9148–0.9773 | 180 | 0.9000 | True |
| p1_retrieval_recall_at_3 | 0.5125 | 0.4049–0.6189 | 80 | 0.8500 | False |
| p1_top1_citation_accuracy | 0.4625 | 0.3575–0.5710 | 80 | 0.9500 | False |
| graph_joint_recall_at_3 | 0.9000 | 0.7695–0.9604 | 40 | 0.8000 | True |
| graph_target_recall_at_3 | 0.9000 | 0.7695–0.9604 | 40 | 0.8500 | True |
| graph_path_accuracy | 0.8250 | 0.6805–0.9125 | 40 | 0.9500 | False |
| graph_recall_gain | 0.6250 | — | — | 0.1500 | True |
| graph_acl_isolation | 1.0000 | 0.8389–1.0000 | 20 | 1.0000 | True |
| permission_isolation | 1.0000 | 0.9791–1.0000 | 180 | 1.0000 | True |
| refusal_accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.9000 | True |
| tool_answer_accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.8500 | True |
| answer_span_hit_rate_fitting | 0.5048 | 0.4107–0.5985 | 105 | 0.5500 | False |

## Ranking and answer quality

- MRR@3: 0.7406
- nDCG@3: 0.7349
- Mean answer content recall: 0.5612
- Answer span hit rate, all gold spans: 0.4500 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 1558.07 ms
P95 latency: 3558.02 ms
Index time: 41.82 s
