@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

uv run python "%PROJECT_ROOT%\scripts\evaluate_p2.py" ^
  --backend nemotron ^
  --model "%PROJECT_ROOT%\models\nemotron-3-embed-1b" ^
  --dimensions 1024 ^
  --device cuda ^
  --data "%PROJECT_ROOT%\data\processed\techqa_p3" ^
  --vector-backend milvus ^
  --milvus-uri http://127.0.0.1:19530 ^
  --milvus-collection enterprise_chunks_structured ^
  --index-version p3-techqa-28481-nemotron-1024-structured-v1 ^
  --dense-weight 0.7 ^
  --search-multiplier 30 ^
  --milvus-search-mode native_rrf ^
  --fielded-search ^
  --query-rewrite ^
  --hybrid-rrf-k 60 ^
  --top-k 3 ^
  --reranker none ^
  --answer-generator extractive ^
  --candidate-diagnostics ^
  --candidate-limit 20 ^
  --category rag ^
  --gold-path "%PROJECT_ROOT%\data\processed\techqa_p3\golden_questions.curated.jsonl" ^
  --output "%PROJECT_ROOT%\reports\p3-structured-native-retrieval.json"
