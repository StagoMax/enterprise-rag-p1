# P3 intelligent knowledge-graph build readiness

## Status

- Pipeline version: `p3-knowledge-terra-v5-2026-08-10`
- Required model: Nowcoding `gpt-5.6-terra`
- Corpus: 28,481 documents
- Full-corpus status: blocked by `insufficient_user_quota`
- Recoverable v4 cache: 2,454 documents and 2,648 successful model reviews
- The v4 cache is diagnostic only. It is not production graph data because deterministic-rule
  review coverage was 51.038% before the v5 completeness fix.

## Intelligent stages

Every review unit uses Terra for all of the following stages:

1. document structure and section-type review;
2. node-type identification;
3. deterministic-candidate acceptance/rejection plus missing-entity extraction;
4. canonical entity naming and alias normalization;
5. intelligent checking of deterministic relation proposals;
6. intelligent relation extraction and final document-level validation.

The engine also applies deterministic evidence, endpoint-type, and self-relation guards after
Terra. These guards can reject an unsafe model result but cannot create an unreviewed relation.

## v5 completeness guarantees

- Equivalent deterministic rule proposals are compacted into one review row, with the Terra
  decision explicitly mapped back to every member rule ID.
- The accepted/corrected/rejected entity-ID sets must cover every proposed entity ID.
- The accepted/rejected rule-ID sets must cover every proposed rule row.
- Missing section, entity, or rule reviews trigger up to two targeted Terra completion passes.
- Per-document `intelligence_audit` records proposed and reviewed counts for every stage.
- Final reports aggregate stage coverage and expose any value below 100%.
- JSONL caching is checksum- and extraction-version-aware, so interrupted runs resume safely.

## Resume after Nowcoding balance is restored

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe scripts\build_p3_knowledge_graph.py `
  --workers 256 `
  --max-retries 5 `
  --document-retries 2
```

Do not promote `artifacts/p3-knowledge-v4-partial2454` to the serving path. The v5 full build
must finish with zero failed documents and 100% coverage for structure, entity, rule, and
validation-unit audits before retrieval integration and graph evaluation.
