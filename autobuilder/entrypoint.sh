#!/usr/bin/env bash
set -euo pipefail

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set"
  exit 1
fi

if [ -z "${PROMPT:-}" ]; then
  exec /bin/bash
fi

# Create the /notify script so Claude can alert the user via Telegram
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  cat > /usr/local/bin/notify << 'SCRIPT'
#!/usr/bin/env bash
# Send a Telegram notification to the user.
# Usage: notify "Your message here"
MESSAGE="${1:-Agent needs attention}"
AGENT_NAME="${AGENT_NAME:-unknown}"
FULL_MESSAGE="🔔 *Agent \`${AGENT_NAME}\`*:
${MESSAGE}"
curl -s -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_CHAT_ID}" \
  -d text="${FULL_MESSAGE}" \
  -d parse_mode="Markdown" \
  > /dev/null 2>&1
SCRIPT
  chmod +x /usr/local/bin/notify
else
  # Stub that just logs if no Telegram config
  cat > /usr/local/bin/notify << 'SCRIPT'
#!/usr/bin/env bash
echo "[NOTIFY] $*"
SCRIPT
  chmod +x /usr/local/bin/notify
fi

echo "Agent ${AGENT_NAME:-?} starting..."
echo "Prompt: ${PROMPT:0:120}..."

# Build system prompt that tells Claude about /notify
NOTIFY_INSTRUCTIONS="You have a command available: notify \"message\"
Run it via Bash whenever you:
- Need the user to manually test or review something
- Hit a blocker that requires human input or a decision
- Finish building the app and it's ready for preview
- Encounter an error you can't resolve on your own
Keep the message short and actionable. Example: notify \"App is ready for preview\" or notify \"Need your input: should I use tabs or a sidebar for navigation?\""

COMBINED_SYSTEM_PROMPT="${NOTIFY_INSTRUCTIONS}"
if [ -n "${SYSTEM_PROMPT:-}" ]; then
  COMBINED_SYSTEM_PROMPT="${COMBINED_SYSTEM_PROMPT}

${SYSTEM_PROMPT}"
fi

args=(
  -p "$PROMPT"
  --dangerously-skip-permissions
  --no-session-persistence
  --append-system-prompt "$COMBINED_SYSTEM_PROMPT"
)

[ -n "${MODEL:-}" ] && args+=(--model "$MODEL")
[ -n "${MAX_BUDGET_USD:-}" ] && args+=(--max-budget-usd "$MAX_BUDGET_USD")
[ -n "${MAX_TURNS:-}" ] && args+=(--max-turns "$MAX_TURNS")

cd /autobuilder
claude "${args[@]}"
exit_code=$?

# Copy built app to output volume if it exists
if [ -d /autobuilder/app/build ] && [ -d /output ]; then
  cp -a /autobuilder/app/build/* /output/ 2>/dev/null || true
  echo "Build artifacts copied to /output"
fi

# Notify on completion
if [ $exit_code -eq 0 ]; then
  notify "Finished successfully. Use /preview ${AGENT_NAME:-?} to view."
else
  notify "Exited with error (code $exit_code). Use /logs ${AGENT_NAME:-?} to check."
fi

exit $exit_code
