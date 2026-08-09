@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"
pushd "%PROJECT_ROOT%"

set "MAX_TOKENS=%~1"
set "OVERLAP_TOKENS=%~2"
set "SEGMENT_DOCUMENTS=%~3"
if "%SEGMENT_DOCUMENTS%"=="" set "SEGMENT_DOCUMENTS=800"
set "EMBEDDING_BATCH_SIZE=%~4"
if "%EMBEDDING_BATCH_SIZE%"=="" set "EMBEDDING_BATCH_SIZE=16"

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

set "REPORT=reports\p3-chunk-%MAX_TOKENS%-%OVERLAP_TOKENS%-index.json"

:index_segment
uv run python scripts\index_milvus.py ^
  --uri http://127.0.0.1:19530 ^
  --collection %COLLECTION% ^
  --corpus data\processed\techqa_p3\documents.jsonl ^
  --version %VERSION% ^
  --resume ^
  --max-documents %SEGMENT_DOCUMENTS% ^
  --backend nemotron ^
  --model models\nemotron-3-embed-1b ^
  --dimensions 1024 ^
  --device cuda ^
  --embedding-batch-size %EMBEDDING_BATCH_SIZE% ^
  --chunk-strategy structured_parent_child ^
  --chunk-max-tokens %MAX_TOKENS% ^
  --chunk-overlap-tokens %OVERLAP_TOKENS% ^
  --chunk-parent-max-tokens 1200 ^
  --chunking-version %CHUNKING_VERSION% ^
  --report %REPORT%
if errorlevel 1 exit /b %errorlevel%

findstr /C:true %REPORT% >nul
if not errorlevel 1 (
  popd
  exit /b 0
)
goto index_segment
