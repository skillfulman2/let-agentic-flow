# let-agentic-flow

Build web apps with your voice. Send a Telegram message describing what you want, and autonomous Claude Code agents build it for you in isolated Docker containers on a remote server.

Inspired by [@karpathy's autoresearch](https://github.com/karpathy/autoresearch) — which applies the same core loop to ML training: an agent modifies code, evaluates the result, keeps improvements, discards regressions, and repeats indefinitely. let-agentic-flow adapts this pattern from `train.py` optimization to full web app construction.

## How it works

```
┌─────────────┐       ┌──────────────────┐
│  Telegram    │──────▶│  Bot container   │
│  (you)       │◀──────│  (orchestrator)  │
└─────────────┘       └────────┬─────────┘
                               │ spawns via Docker socket
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        ┌────────────┐  ┌────────────┐  ┌────────────┐
        │ Agent      │  │ Agent      │  │ Agent      │
        │ ab-todo-.. │  │ ab-weather │  │ ab-editor  │
        └────────────┘  └────────────┘  └────────────┘
```

1. You send a message to the Telegram bot (text or voice)
2. The bot spawns a Docker container with Claude Code running autonomously
3. The agent builds a SvelteKit app, iterating in a loop — modify code, run Playwright tests, keep or discard
4. When the agent needs input or finishes, it pings you on Telegram via `notify`
5. You preview the app through a Cloudflare tunnel, send feedback, and the agent keeps iterating

Each agent runs in its own container with CPU/memory limits, so multiple apps can be built in parallel without interfering with each other or other services on the server.

## The autoresearch loop

The core idea comes from [autoresearch](https://github.com/karpathy/autoresearch): instead of a human manually editing code, you write a `program.md` that instructs an AI agent how to experiment autonomously. The agent runs in a loop:

1. Make a change
2. Evaluate (run tests / train a model)
3. If the result improved, keep the commit
4. If not, discard and try something else
5. Repeat forever

In the original autoresearch, the agent optimizes `train.py` against a val_bpb metric. In the autobuilder, the agent optimizes a SvelteKit app against Playwright tests covering functionality, PWA compliance, and accessibility. Same loop, different domain.

## Setup

**Requirements:** Docker, a Telegram bot token ([@BotFather](https://t.me/BotFather)), an Anthropic API key.

```bash
# 1. Build the agent image
cd autobuilder && docker build -t autobuilder .

# 2. Configure environment
cp .env.example .env
# Fill in: TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_USER_IDS

# 3. Start the Telegram bot
docker compose up -d
```

To get your Telegram user ID, message [@userinfobot](https://t.me/userinfobot).

## Telegram commands

| Command | Description |
|---------|-------------|
| *any text message* | Spawn an agent with that prompt |
| `/build <prompt>` | Explicit build command |
| `/status` | List running agents |
| `/logs <name>` | Tail logs from an agent |
| `/preview <name>` | Open a Cloudflare tunnel to preview the app |
| `/msg <name> <text>` | Send feedback to a running agent |
| `/stop <name>` | Stop an agent and tear down its tunnel |
| `/list` | List all workspaces (running + finished) |

Agents are named from the prompt — e.g. "Build a todo app with drag-and-drop" becomes `ab-todo-drag-drop-1423`.

## Project structure

```
autobuilder/
├── Dockerfile           — agent container (Node, Python, Playwright, Claude Code)
├── entrypoint.sh        — agent entrypoint with notify script injection
├── docker-compose.yml   — bot orchestrator
├── .env.example         — required environment variables
├── launch.sh            — standalone launcher (no Telegram)
├── bot/
│   ├── Dockerfile       — bot container (Python + cloudflared)
│   ├── bot.py           — Telegram bot
│   └── requirements.txt
├── app/                 — SvelteKit app template (scaffold)
├── evaluate.py          — Playwright test evaluation harness
├── tests/               — fixed Playwright tests (functional, PWA, a11y)
├── scaffold.sh          — local setup script (no Docker)
├── program.md           — agent loop instructions
└── feedback/            — user feedback transcripts
```

## Configuration

Environment variables (set in `.env`):

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | From @BotFather |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `ALLOWED_USER_IDS` | Yes | Comma-separated Telegram user IDs |
| `MODEL` | No | Claude model to use |
| `MAX_BUDGET_USD` | No | Per-agent cost cap |
| `CPU_LIMIT` | No | CPU cores per agent (default: 2) |
| `MEM_LIMIT` | No | Memory per agent (default: 4g) |

## Credits

Built on the autonomous experimentation pattern from [@karpathy/autoresearch](https://github.com/karpathy/autoresearch).

## License

MIT
