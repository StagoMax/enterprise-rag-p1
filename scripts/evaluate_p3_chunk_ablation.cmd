@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

set "MAX_TOKENS=%~1"
set "OVERLAP_TOKENS=%~2"
set "MODE=%~3"
if "%MODE%"=="" set "MODE=none"

if "%MAX_TOKENS%"=="384" if "%OVERLAP_TOKENS%"=="64" (
  set "COLLECTION=enterprise_chunks_structured"
  set "VERSION=p3-techqa-28481-nemotron-1024-structured-v1"
  set "CHUNKING_VERSION=structured-parent-child-v1"
)
if "%MAX_TOKENS%"=="320" if "%OVERLAP_TOKENS%"=="48" (
  set "COLLECTION=enterprise_chunks_structured_320_48"
  set "VERSION=p3-techqa-28481-nemotron-1024-structured-320-48-v1"
  set "CHUNKING_VERSION=structured-parent-child-320-48-v1"
)
if "%MAX_TOKENS%"=="256" if "%OVERLAP_TOKENS%"=="48" (
  set "COLLECTION=enterprise_chunks_structured_256_48"
  set "VERSION=p3-techqa-28481-nemotron-1024-structured-256-48-v1"
  set "CHUNKING_VERSION=structured-parent-child-256-48-v1"
)
if not defined COLLECTION (
  echo Supported parameter sets: 384 64, 320 48, 256 48.
  exit /b 2
)
if /I not "%MODE%"=="none" if /I not "%MODE%"=="replace" if /I not "%MODE%"=="gpt_replace" (
  echo Mode must be none, replace, or gpt_replace.
  exit /b 2
)

set "RERANK_ARGS=--reranker none --candidate-diagnostics --candidate-limit 20"
set "OUTPUT=%PROJECT_ROOT%\reports\p3-chunk-%MAX_TOKENS%-%OVERLAP_TOKENS%-adaptive20-native.json"
set "CACHE=%PROJECT_ROOT%\artifacts\p3-chunk-%MAX_TOKENS%-%OVERLAP_TOKENS%-adaptive20-fair-deepseek-replace.jsonl"
if /I "%MODE%"=="replace" (
  set "RERANK_ARGS=--reranker llm --rerank-candidates 20 --rerank-strategy replace --reranker-cache-mode record --reranker-cache-path %CACHE%"
  set "OUTPUT=%PROJECT_ROOT%\reports\p3-chunk-%MAX_TOKENS%-%OVERLAP_TOKENS%-adaptive20-deepseek-replace.json"
)
if /I "%MODE%"=="gpt_replace" (
  set "RERANK_ARGS=--reranker llm --rerank-candidates 20 --rerank-strategy replace --reranker-cache-mode record --reranker-cache-path %PROJECT_ROOT%\artifacts\p3-chunk-%MAX_TOKENS%-%OVERLAP_TOKENS%-adaptive20-fair-nowcoding-gpt-5.6-luna-replace.jsonl --llm-model gpt-5.6-luna"
  set "OUTPUT=%PROJECT_ROOT%\reports\p3-chunk-%MAX_TOKENS%-%OVERLAP_TOKENS%-adaptive20-nowcoding-gpt-5.6-luna-replace.json"
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
  --chunk-max-tokens %MAX_TOKENS% ^
  --chunk-overlap-tokens %OVERLAP_TOKENS% ^
  --chunk-parent-max-tokens 1200 ^
  --chunking-version %CHUNKING_VERSION% ^
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
  %RERANK_ARGS% ^
  --answer-generator extractive ^
  --category rag ^
  --gold-path "%PROJECT_ROOT%\data\processed\techqa_p3\golden_questions.curated.jsonl" ^
  --output "%OUTPUT%"
