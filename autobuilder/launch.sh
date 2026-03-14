#!/usr/bin/env bash
set -euo pipefail

#
# Launch one or more autobuilder agents, each in its own container.
#
# Usage:
#   # Single agent
#   ./launch.sh "Build a todo app with drag-and-drop"
#
#   # Multiple agents
#   ./launch.sh "Build a todo app" "Build a weather dashboard" "Build a markdown editor"
#
#   # From prompt files
#   ./launch.sh prompts/*.txt
#
# Environment:
#   ANTHROPIC_API_KEY   Required.
#   MODEL               Optional. (default: claude's default)
#   MAX_BUDGET_USD      Optional. Per-agent budget cap.
#   MAX_TURNS           Optional. Per-agent turn limit.
#   CPU_LIMIT           Optional. CPU limit per container (default: 2)
#   MEM_LIMIT           Optional. Memory limit per container (default: 4g)
#

IMAGE="autobuilder"
CPU_LIMIT="${CPU_LIMIT:-2}"
MEM_LIMIT="${MEM_LIMIT:-4g}"
OUTPUT_BASE="$(pwd)/output"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set"
  exit 1
fi

if [ $# -eq 0 ]; then
  echo "Usage: $0 <prompt|file.txt> [<prompt|file.txt> ...]"
  exit 1
fi

# Collect prompts — if arg is a .txt file, read its contents
prompts=()
for arg in "$@"; do
  if [[ "$arg" == *.txt ]] && [ -f "$arg" ]; then
    prompts+=("$(cat "$arg")")
  else
    prompts+=("$arg")
  fi
done

echo "Launching ${#prompts[@]} agent(s)..."
echo ""

mkdir -p "$OUTPUT_BASE"

for i in "${!prompts[@]}"; do
  name="autobuilder-$(printf '%02d' "$i")"
  prompt="${prompts[$i]}"
  output_dir="$OUTPUT_BASE/$name"
  mkdir -p "$output_dir"

  echo "[$name] ${prompt:0:80}..."

  docker run -d \
    --name "$name" \
    --cpus="$CPU_LIMIT" \
    --memory="$MEM_LIMIT" \
    -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    -e PROMPT="$prompt" \
    ${MODEL:+-e MODEL="$MODEL"} \
    ${MAX_BUDGET_USD:+-e MAX_BUDGET_USD="$MAX_BUDGET_USD"} \
    ${MAX_TURNS:+-e MAX_TURNS="$MAX_TURNS"} \
    -v "$output_dir:/output" \
    "$IMAGE" \
    > /dev/null

  echo "[$name] Container started"
done

echo ""
echo "All agents launched. Monitor with:"
echo "  docker ps --filter name=autobuilder"
echo "  docker logs -f autobuilder-00"
echo ""
echo "Built apps will appear in: $OUTPUT_BASE/"
