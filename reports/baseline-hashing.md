# P1 Baseline: hashing

- Model: `hashing-384`
- Documents: 200
- Questions: 120
- Passed: no

| Metric | Result | Threshold | Passed |
|---|---:|---:|---|
| route_accuracy | 1.0000 | 0.9000 | True |
| retrieval_recall_at_3 | 0.7625 | 0.8500 | False |
| citation_accuracy | 0.5875 | 0.9500 | False |
| refusal_accuracy | 1.0000 | 0.9000 | True |
| permission_isolation | 1.0000 | 1.0000 | True |
| tool_answer_accuracy | 1.0000 | 0.8500 | True |

P50 latency: 9.09 ms
P95 latency: 225.02 ms
Index time: 0.69 s
