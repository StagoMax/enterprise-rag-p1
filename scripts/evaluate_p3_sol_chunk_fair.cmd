@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

set "VARIANT=%~1"
if "%VARIANT%"=="" (
  echo Variant must be legacy, 384_64, or 256_48.
  exit /b 2
)

if /I "%VARIANT%"=="legacy" (
  set "COLLECTION=enterprise_chunks"
  set "VERSION=p3-techqa-28481-nemotron-1024-fielded-v1"
  set "CHUNK_ARGS=--chunking-version legacy-characters-v1"
  set "RAG_CHUNKING_STRATEGY=legacy"
  set "CACHE=%PROJECT_ROOT%\artifacts\p3-chunk-legacy-900-100-adaptive20-fair-nowcoding-gpt-5.6-sol-replace.jsonl"
  set "OUTPUT=%PROJECT_ROOT%\reports\p3-chunk-legacy-900-100-adaptive20-nowcoding-gpt-5.6-sol-replace.json"
)
if /I "%VARIANT%"=="384_64" (
  set "COLLECTION=enterprise_chunks_structured"
  set "VERSION=p3-techqa-28481-nemotron-1024-structured-v1"
  set "CHUNK_ARGS=--chunk-max-tokens 384 --chunk-overlap-tokens 64 --chunk-parent-max-tokens 1200 --chunking-version structured-parent-child-v1"
  set "RAG_CHUNKING_STRATEGY=structured_parent_child"
  set "CACHE=%PROJECT_ROOT%\artifacts\p3-chunk-384-64-adaptive20-fair-nowcoding-gpt-5.6-sol-replace.jsonl"
  set "OUTPUT=%PROJECT_ROOT%\reports\p3-chunk-384-64-adaptive20-nowcoding-gpt-5.6-sol-replace.json"
)
if /I "%VARIANT%"=="256_48" (
  set "COLLECTION=enterprise_chunks_structured_256_48"
  set "VERSION=p3-techqa-28481-nemotron-1024-structured-256-48-v1"
  set "CHUNK_ARGS=--chunk-max-tokens 256 --chunk-overlap-tokens 48 --chunk-parent-max-tokens 1200 --chunking-version structured-parent-child-256-48-v1"
  set "RAG_CHUNKING_STRATEGY=structured_parent_child"
  set "CACHE=%PROJECT_ROOT%\artifacts\p3-chunk-256-48-adaptive20-fair-nowcoding-gpt-5.6-sol-replace.jsonl"
  set "OUTPUT=%PROJECT_ROOT%\reports\p3-chunk-256-48-adaptive20-nowcoding-gpt-5.6-sol-replace.json"
)
if not defined COLLECTION (
  echo Variant must be legacy, 384_64, or 256_48.
  exit /b 2
)

rem Sol must use the NowCoding endpoint even when DeepSeek has higher .env priority.
set "RAG_LLM_BASE_URL="
set "RAG_LLM_API_KEY="
if defined NOWCODING_BASE_URL set "RAG_LLM_BASE_URL=%NOWCODING_BASE_URL%"
if defined NOWCODING_KEY set "RAG_LLM_API_KEY=%NOWCODING_KEY%"
if not defined RAG_LLM_BASE_URL if exist "%PROJECT_ROOT%\.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%PROJECT_ROOT%\.env") do if /I "%%A"=="NOWCODING_BASE_URL" set "RAG_LLM_BASE_URL=%%B"
)
if not defined RAG_LLM_API_KEY if exist "%PROJECT_ROOT%\.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%PROJECT_ROOT%\.env") do if /I "%%A"=="NOWCODING_KEY" set "RAG_LLM_API_KEY=%%B"
)
if not defined RAG_LLM_BASE_URL (
  echo Missing RAG_LLM_BASE_URL or NOWCODING_BASE_URL in .env.
  exit /b 2
)
if not defined RAG_LLM_API_KEY (
  echo Missing RAG_LLM_API_KEY or NOWCODING_KEY in .env.
  exit /b 2
)

uv run python "%PROJECT_ROOT%\scripts\evaluate_p2.py" ^
  --backend nemotron ^
  --model "%PROJECT_ROOT%\models\nemotron-3-embed-1b" ^
  --dimensions 1024 ^
  --device cuda ^
  --data "%PROJECT_ROOT%\data\processed\techqa_p3" ^
  --vector-backend milvus ^
  --milvus-uri http://127.0.0.1:19530 ^
  --milvus-collection %COLLECTION% ^
  --index-version %VERSION% ^
  %CHUNK_ARGS% ^
  --dense-weight 0.7 ^
  --search-multiplier 30 ^
  --adaptive-recall ^
  --adaptive-recall-max-chunks 4096 ^
  --min-retrieval-score 0 ^
  --milvus-search-mode native_rrf ^
  --fielded-search ^
  --query-rewrite ^
  --hybrid-rrf-k 60 ^
  --top-k 3 ^
  --reranker llm ^
  --rerank-candidates 20 ^
  --rerank-strategy replace ^
  --reranker-cache-mode record ^
  --reranker-cache-path "%CACHE%" ^
  --llm-model gpt-5.6-sol ^
  --answer-generator extractive ^
  --category rag ^
  --gold-path "%PROJECT_ROOT%\data\processed\techqa_p3\golden_questions.curated.jsonl" ^
  --output "%OUTPUT%"
