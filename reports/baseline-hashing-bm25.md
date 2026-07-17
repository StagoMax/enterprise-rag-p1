# P1 Baseline: hashing

- Model: `hashing-384`
- Documents: 200
- Questions: 120
- Passed: no

| Metric | Result | Threshold | Passed |
|---|---:|---:|---|
| route_accuracy | 1.0000 | 0.9000 | True |
| retrieval_recall_at_3 | 0.8750 | 0.8500 | True |
| citation_accuracy | 0.7875 | 0.9500 | False |
| refusal_accuracy | 1.0000 | 0.9000 | True |
| permission_isolation | 1.0000 | 1.0000 | True |
| tool_answer_accuracy | 1.0000 | 0.8500 | True |

P50 latency: 9.89 ms
P95 latency: 212.34 ms
Index time: 0.64 s
