# P1 Baseline: hashing

- Model: `hashing-384`
- Documents: 200
- Questions: 120
- Passed: no

| Metric | Result | Threshold | Passed |
|---|---:|---:|---|
| route_accuracy | 1.0000 | 0.9000 | True |
| retrieval_recall_at_3 | 0.9375 | 0.8500 | True |
| citation_accuracy | 0.8250 | 0.9500 | False |
| refusal_accuracy | 1.0000 | 0.9000 | True |
| permission_isolation | 1.0000 | 1.0000 | True |
| tool_answer_accuracy | 1.0000 | 0.8500 | True |

P50 latency: 6.64 ms
P95 latency: 171.53 ms
Index time: 1.09 s
