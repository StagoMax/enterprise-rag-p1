# P1 Baseline: bge_m3

- Model: `models\bge-m3`
- Documents: 200
- Questions: 120
- Passed: no

| Metric | Result | Threshold | Passed |
|---|---:|---:|---|
| route_accuracy | 1.0000 | 0.9000 | True |
| retrieval_recall_at_3 | 0.9625 | 0.8500 | True |
| citation_accuracy | 0.8500 | 0.9500 | False |
| refusal_accuracy | 1.0000 | 0.9000 | True |
| permission_isolation | 1.0000 | 1.0000 | True |
| tool_answer_accuracy | 1.0000 | 0.8500 | True |

P50 latency: 65.01 ms
P95 latency: 245.36 ms
Index time: 84.76 s
