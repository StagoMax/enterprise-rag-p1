@echo off
setlocal

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

set RAG_VECTOR_BACKEND=milvus
set RAG_MILVUS_URI=http://127.0.0.1:19530
set RAG_MILVUS_COLLECTION=enterprise_chunks
set RAG_INDEX_VERSION=p3-techqa-28481-nemotron-1024-v3
set RAG_CORPUS_PATH=%PROJECT_ROOT%\data\processed\techqa_p3\documents.jsonl
set RAG_RELATIONS_PATH=%PROJECT_ROOT%\data\processed\techqa_p3\relations.jsonl
set RAG_GOLD_PATH=%PROJECT_ROOT%\data\processed\techqa_p3\golden_questions.jsonl
set RAG_GRAPH_STATE_PATH=%PROJECT_ROOT%\data\p3-nemotron-graph-state.json
set RAG_EVALUATION_REPORT_PATH=%PROJECT_ROOT%\reports\p3-milvus-nemotron-1024-optimized.json

set RAG_EMBEDDING_BACKEND=nemotron
set RAG_NEMOTRON_MODEL_ID=%PROJECT_ROOT%\models\nemotron-3-embed-1b
set RAG_NEMOTRON_DIMENSIONS=1024
set RAG_NEMOTRON_DEVICE=cuda
set RAG_DENSE_WEIGHT=0.7
set RAG_MILVUS_SEARCH_MULTIPLIER=30
set RAG_TOP_K=3
set RAG_LLM_BACKEND=extractive

"%PROJECT_ROOT%\.venv\Scripts\python.exe" -m uvicorn enterprise_rag.main:app --host 127.0.0.1 --port 8000
