@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=none"
if /I not "%MODE%"=="none" if /I not "%MODE%"=="deepseek_replace" if /I not "%MODE%"=="gpt_replace" (
  echo Mode must be none, deepseek_replace, or gpt_replace.
  exit /b 2
)

set "RAG_CHUNKING_STRATEGY=legacy"
set "RERANK_ARGS=--reranker none --candidate-diagnostics --candidate-limit 20"
set "OUTPUT=%PROJECT_ROOT%\reports\p3-chunk-legacy-900-100-adaptive20-native.json"

if /I "%MODE%"=="deepseek_replace" (
  set "RERANK_ARGS=--reranker llm --rerank-candidates 20 --rerank-strategy replace --reranker-cache-mode record --reranker-cache-path %PROJECT_ROOT%\artifacts\p3-chunk-legacy-900-100-adaptive20-fair-deepseek-replace.jsonl"
  set "OUTPUT=%PROJECT_ROOT%\reports\p3-chunk-legacy-900-100-adaptive20-deepseek-replace.json"
)

if /I "%MODE%"=="gpt_replace" (
  rem Do not inherit DeepSeek's higher-priority RAG_LLM_* values in GPT mode.
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
  set "RERANK_ARGS=--reranker llm --rerank-candidates 20 --rerank-strategy replace --reranker-cache-mode record --reranker-cache-path %PROJECT_ROOT%\artifacts\p3-chunk-legacy-900-100-adaptive20-fair-nowcoding-gpt-5.6-luna-replace.jsonl --llm-model gpt-5.6-luna"
  set "OUTPUT=%PROJECT_ROOT%\reports\p3-chunk-legacy-900-100-adaptive20-nowcoding-gpt-5.6-luna-replace.json"
)

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
  --chunking-version legacy-characters-v1 ^
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
