# P1 Baseline: nemotron

- Model: `models\nemotron-3-embed-1b`
- Documents: 200
- Questions: 120
- Passed: no

| Metric | Result | Threshold | Passed |
|---|---:|---:|---|
| route_accuracy | 1.0000 | 0.9000 | True |
| retrieval_recall_at_3 | 0.9000 | 0.8500 | True |
| citation_accuracy | 0.8750 | 0.9500 | False |
| refusal_accuracy | 1.0000 | 0.9000 | True |
| permission_isolation | 1.0000 | 1.0000 | True |
| tool_answer_accuracy | 1.0000 | 0.8500 | True |

P50 latency: 73.98 ms
P95 latency: 303.78 ms
Index time: 87.23 s
