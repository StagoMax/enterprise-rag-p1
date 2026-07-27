@echo off
set RAG_EMBEDDING_BACKEND=nemotron
set RAG_NEMOTRON_MODEL_ID=J:\Project\RAG\models\nemotron-3-embed-1b
set RAG_NEMOTRON_DIMENSIONS=1024
set RAG_NEMOTRON_DEVICE=cuda
set RAG_DENSE_WEIGHT=0.5
set RAG_GRAPH_ENABLED=true
set RAG_INDEX_VERSION=p2-techqa-1000-v1
set RAG_CORPUS_PATH=J:\Project\RAG\data\processed\techqa_p2\documents.jsonl
set RAG_RELATIONS_PATH=J:\Project\RAG\data\processed\techqa_p2\relations.jsonl
set RAG_GOLD_PATH=J:\Project\RAG\data\processed\techqa_p2\golden_questions.jsonl
set RAG_EVALUATION_REPORT_PATH=J:\Project\RAG\reports\p2-baseline-current.json
.venv\Scripts\python.exe -m uvicorn enterprise_rag.main:app --host 127.0.0.1 --port 8000
