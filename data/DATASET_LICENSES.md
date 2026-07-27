# Dataset Sources and Licenses

## TechQA-RAG-Eval

- Source: [NVIDIA TechQA-RAG-Eval](https://huggingface.co/datasets/nvidia/TechQA-RAG-Eval)
- Upstream: [IBM TechQA](https://github.com/IBM/techqa)
- License: Apache-2.0, according to the NVIDIA dataset card.
- Local use: `techqa_websphere` is the 200-document P1 proxy; `techqa_p2` is the 1,000-document P2 proxy for enterprise technical-support knowledge and explicit document references.
- P1 selection: records and contexts containing `WebSphere`, capped at 200 unique documents.
- P2 selection: all P1 documents, TechQA training contexts, their explicit in-corpus reference targets, then deterministic fillers to 1,000 documents. The 307 graph edges come only from document IDs explicitly present in source text.

The raw 46 MB evaluation archive and source JSON are excluded from version control. The generated manifest records the source identifier and content checksum for every selected document.

## BIRD-SQL Mini-Dev

- Source: [BIRD Mini-Dev](https://github.com/bird-bench/mini_dev)
- Local subset: the `financial` SQLite database, its eight schema-description CSV files, and 32 corresponding questions.
- License: CC BY-SA 4.0 according to the official repository and Hugging Face dataset card.
- Local use: read-only SQL validation and tool-routing evaluation. Database rows are never copied into the RAG index.

## Nemotron 3 Embed

- Model: [NVIDIA Nemotron-3-Embed-1B-BF16](https://huggingface.co/nvidia/Nemotron-3-Embed-1B-BF16)
- License: OpenMDW-1.1 according to the model card.
- Production use requires an independent legal review even though the model card states that the model is ready for commercial use.
