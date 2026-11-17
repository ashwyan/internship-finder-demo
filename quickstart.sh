#!/bin/bash
# One command to try the finder:   bash quickstart.sh          (keyword mode, takes seconds, no AI needed)
#                                  bash quickstart.sh --ai     (also uses local Ollama if it is installed)
set -e
cd "$(dirname "$0")"
PY="$(command -v python3 || true)"
[ -n "$PY" ] || { echo "Python 3 is missing. Install Python 3.8+ from python.org, then run this again."; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || { echo "Python 3.8+ is needed. You have: $($PY --version)"; exit 1; }
echo "Python OK: $($PY --version)"

if [ ! -f master_resume.json ]; then
  cp master_resume.example.json master_resume.json
  echo "Created master_resume.json from the FAKE example. Edit it with your own details for real results."
fi

ARGS="--no-ai"
if [ "$1" = "--ai" ]; then
  if command -v ollama >/dev/null && curl -s -m 3 http://localhost:11434/api/version >/dev/null; then
    for m in qwen3:4b nomic-embed-text; do ollama list | grep -q "^$m" || { echo "Pulling $m (one time, about 2.5 GB for qwen3:4b)..."; ollama pull "$m"; }; done
    ARGS=""
  else
    echo "Ollama is not installed or not running, so using keyword mode. Install it from https://ollama.com and run: ollama serve"
  fi
fi

echo "Running (needs internet to read the public job lists)..."
"$PY" src/internship_finder.py $ARGS
REPORT="$(ls -1d output/*/report.txt | tail -1)"
echo; echo "===== top of $REPORT ====="; head -25 "$REPORT"
echo; echo "Full report: $REPORT"
echo "Next: edit master_resume.json, then see README.md to run it every day."
