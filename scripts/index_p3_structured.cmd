@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"
pushd "%PROJECT_ROOT%"

set "SEGMENT_DOCUMENTS=%~1"
if "%SEGMENT_DOCUMENTS%"=="" set "SEGMENT_DOCUMENTS=800"

set "COLLECTION=enterprise_chunks_structured"
set "VERSION=p3-techqa-28481-nemotron-1024-structured-v1"
set "REPORT=reports\p3-structured-index-progress.json"

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
  --embedding-batch-size 8 ^
  --chunk-strategy structured_parent_child ^
  --chunk-max-tokens 384 ^
  --chunk-overlap-tokens 64 ^
  --chunk-parent-max-tokens 1200 ^
  --chunking-version structured-parent-child-v1 ^
  --report %REPORT%
if errorlevel 1 exit /b %errorlevel%

findstr /C:true %REPORT% >nul
if not errorlevel 1 (
  popd
  exit /b 0
)
goto index_segment
