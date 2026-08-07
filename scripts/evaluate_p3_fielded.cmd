@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

set "STRATEGY=%~1"
if "%STRATEGY%"=="" set "STRATEGY=replace"
if /I "%STRATEGY%"=="replace" set "STRATEGY=replace"
if /I "%STRATEGY%"=="weighted_rrf" set "STRATEGY=weighted_rrf"
if not "%STRATEGY%"=="replace" if not "%STRATEGY%"=="weighted_rrf" (
  echo Strategy must be replace or weighted_rrf.
  exit /b 2
)

set "CACHE_MODE=replay"
if "%STRATEGY%"=="replace" set "CACHE_MODE=record"

uv run python "%PROJECT_ROOT%\scripts\evaluate_p2.py" ^
  --backend nemotron ^
  --model "%PROJECT_ROOT%\models\nemotron-3-embed-1b" ^
  --dimensions 1024 ^
  --device cuda ^
  --data "%PROJECT_ROOT%\data\processed\techqa_p3" ^
  --vector-backend milvus ^
  --milvus-uri http://127.0.0.1:19530 ^
  --milvus-collection enterprise_chunks ^
  --index-version p3-techqa-28481-nemotron-1024-fielded-v1 ^
  --dense-weight 0.7 ^
  --search-multiplier 30 ^
  --milvus-search-mode native_rrf ^
  --fielded-search ^
  --query-rewrite ^
  --hybrid-rrf-k 60 ^
  --top-k 3 ^
  --reranker llm ^
  --rerank-candidates 20 ^
  --rerank-strategy %STRATEGY% ^
  --reranker-weight 0.5 ^
  --rerank-rrf-k 60 ^
  --reranker-cache-mode %CACHE_MODE% ^
  --reranker-cache-path "%PROJECT_ROOT%\artifacts\p3-fielded-reranker-cache-deepseek-v4-flash.jsonl" ^
  --answer-generator extractive ^
  --category rag ^
  --gold-path "%PROJECT_ROOT%\data\processed\techqa_p3\golden_questions.curated.jsonl" ^
  --output "%PROJECT_ROOT%\reports\p3-fielded-native-deepseek-v4-flash-%STRATEGY%.json"
