# Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-v3
- Dense weight: 0.7
- Milvus search multiplier: 30
- Documents: 28481
- Relations: 7600
- Questions: 180
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Passed |
|---|---:|:--:|---:|---:|---|
| route_accuracy | 1.0000 | 0.9791–1.0000 | 180 | 0.9000 | True |
| p1_retrieval_recall_at_3 | 0.6375 | 0.5281–0.7343 | 80 | 0.8500 | False |
| p1_top1_citation_accuracy | 0.6250 | 0.5155–0.7231 | 80 | 0.9500 | False |
| graph_joint_recall_at_3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8000 | True |
| graph_target_recall_at_3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8500 | True |
| graph_path_accuracy | 1.0000 | 0.9124–1.0000 | 40 | 0.9500 | True |
| graph_recall_gain | 0.6500 | — | — | 0.1500 | True |
| graph_acl_isolation | 1.0000 | 0.8389–1.0000 | 20 | 1.0000 | True |
| permission_isolation | 1.0000 | 0.9791–1.0000 | 180 | 1.0000 | True |
| refusal_accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.9000 | True |
| tool_answer_accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.8500 | True |
| answer_span_hit_rate_fitting | 0.5619 | 0.4665–0.6530 | 105 | 0.5500 | True |

## Ranking and answer quality

- MRR@3: 0.8146
- nDCG@3: 0.8156
- Mean answer content recall: 0.6482
- Answer span hit rate, all gold spans: 0.5250 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 689.6 ms
P95 latency: 1195.1 ms
Index time: 48.4 s
