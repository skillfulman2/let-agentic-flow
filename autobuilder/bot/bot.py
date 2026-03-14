"""
Telegram bot for managing autobuilder agents.

Commands:
  /build <prompt>  — Spawn an agent to build an app
  /status          — List running agents
  /stop <name>     — Stop an agent
  /logs <name>     — Get recent logs from an agent
  /preview <name>  — Start a cloudflare tunnel to preview a built app
  /list            — List all workspaces (running + finished)
  /msg <name> <text> — Send feedback to a running agent

Also accepts plain text messages as build prompts.
"""

import asyncio
import logging
import os
import re
import subprocess
from datetime import datetime, timezone

import docker
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ALLOWED_USERS = {
    int(uid.strip())
    for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",")
    if uid.strip()
}
IMAGE = os.environ.get("AUTOBUILDER_IMAGE", "autobuilder")
MODEL = os.environ.get("MODEL", "")
MAX_BUDGET_USD = os.environ.get("MAX_BUDGET_USD", "")
CPU_LIMIT = os.environ.get("CPU_LIMIT", "2")
MEM_LIMIT = os.environ.get("MEM_LIMIT", "4g")
WORKSPACES_DIR = os.environ.get("WORKSPACES_DIR", "/workspaces")

docker_client = docker.from_env()

# Track active tunnels: container_name -> (tunnel_proc, server_proc)
active_tunnels: dict[str, tuple[subprocess.Popen, subprocess.Popen]] = {}


def auth(func):
    """Decorator to restrict commands to allowed users."""

    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
            await update.message.reply_text("Unauthorized.")
            return
        return await func(update, context)

    return wrapper


def slugify(prompt: str, max_len: int = 24) -> str:
    """Turn a prompt into a short container-safe slug."""
    # Lowercase, keep only alphanum and spaces
    clean = re.sub(r"[^a-z0-9 ]", "", prompt.lower())
    # Take first few meaningful words
    words = clean.split()
    # Skip filler words
    skip = {"a", "an", "the", "with", "and", "or", "for", "to", "that", "this", "build", "create", "make"}
    words = [w for w in words if w not in skip][:4]
    slug = "-".join(words) if words else "app"
    return slug[:max_len]


def agent_name(prompt: str) -> str:
    """Generate a descriptive, unique container name from the prompt."""
    slug = slugify(prompt)
    ts = datetime.now(timezone.utc).strftime("%H%M")
    return f"ab-{slug}-{ts}"


async def monitor_container(
    container_name: str, chat_id: int, app: Application
) -> None:
    """Background task: wait for container to finish, then notify."""
    try:
        container = docker_client.containers.get(container_name)
        # Poll instead of blocking wait so we don't block the event loop
        while True:
            container.reload()
            if container.status in ("exited", "dead"):
                break
            await asyncio.sleep(5)

        exit_code = container.attrs["State"]["ExitCode"]
        logs = container.logs(tail=30).decode("utf-8", errors="replace")

        if exit_code == 0:
            msg = (
                f"Agent `{container_name}` finished successfully.\n\n"
                f"Use /preview {container_name} to view it.\n\n"
                f"```\n{logs[-500:]}\n```"
            )
        else:
            msg = (
                f"Agent `{container_name}` failed (exit {exit_code}).\n\n"
                f"```\n{logs[-500:]}\n```"
            )

        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        await app.bot.send_message(
            chat_id=chat_id, text=f"Error monitoring `{container_name}`: {e}"
        )


def spawn_agent(name: str, prompt: str, chat_id: int) -> str:
    """Spawn a new agent container. Returns container name."""
    output_dir = os.path.join(WORKSPACES_DIR, name)
    os.makedirs(output_dir, exist_ok=True)

    env = {
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "PROMPT": prompt,
        "AGENT_NAME": name,
        # Pass Telegram creds so the agent can use /notify
        "TELEGRAM_BOT_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": str(chat_id),
    }
    if MODEL:
        env["MODEL"] = MODEL
    if MAX_BUDGET_USD:
        env["MAX_BUDGET_USD"] = MAX_BUDGET_USD

    container = docker_client.containers.run(
        IMAGE,
        detach=True,
        name=name,
        environment=env,
        cpuset_cpus=None,
        nano_cpus=int(float(CPU_LIMIT) * 1e9),
        mem_limit=MEM_LIMIT,
        volumes={output_dir: {"bind": "/output", "mode": "rw"}},
        remove=False,
    )
    return container.name


@auth
async def cmd_build(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prompt = " ".join(context.args) if context.args else ""
    if not prompt:
        await update.message.reply_text("Usage: /build <describe the app you want>")
        return

    name = agent_name(prompt)
    await update.message.reply_text(
        f"Spawning agent `{name}`...\n\nPrompt: {prompt[:200]}"
    )

    try:
        spawn_agent(name, prompt, update.effective_chat.id)
        await update.message.reply_text(
            f"Agent `{name}` is running. I'll notify you when it's done."
        )
        asyncio.create_task(
            monitor_container(name, update.effective_chat.id, context.application)
        )
    except Exception as e:
        await update.message.reply_text(f"Failed to spawn agent: {e}")


@auth
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    containers = docker_client.containers.list(filters={"name": "ab-"})
    if not containers:
        await update.message.reply_text("No running agents.")
        return

    lines = []
    for c in containers:
        status = c.status
        started = c.attrs.get("State", {}).get("StartedAt", "?")[:19]
        lines.append(f"• `{c.name}` — {status} (started {started})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@auth
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /stop <agent-name>")
        return

    name = context.args[0]
    try:
        container = docker_client.containers.get(name)
        container.stop(timeout=10)
        container.remove()
    except docker.errors.NotFound:
        await update.message.reply_text(f"Agent `{name}` not found.")
        return
    except Exception as e:
        await update.message.reply_text(f"Error stopping: {e}")
        return

    # Kill tunnel if active
    if name in active_tunnels:
        tunnel_proc, server_proc = active_tunnels.pop(name)
        tunnel_proc.terminate()
        server_proc.terminate()

    await update.message.reply_text(f"Stopped and removed `{name}`.")


@auth
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /logs <agent-name>")
        return

    name = context.args[0]
    try:
        container = docker_client.containers.get(name)
        logs = container.logs(tail=50).decode("utf-8", errors="replace")
        if len(logs) > 3500:
            logs = "...\n" + logs[-3500:]
        await update.message.reply_text(f"```\n{logs}\n```", parse_mode="Markdown")
    except docker.errors.NotFound:
        await update.message.reply_text(f"Agent `{name}` not found.")


@auth
async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /preview <agent-name>")
        return

    name = context.args[0]
    output_dir = os.path.join(WORKSPACES_DIR, name)

    if not os.path.isdir(output_dir):
        await update.message.reply_text(f"No output found for `{name}`.")
        return

    # Kill existing tunnel for this agent
    if name in active_tunnels:
        tunnel_proc, server_proc = active_tunnels.pop(name)
        tunnel_proc.terminate()
        server_proc.terminate()

    await update.message.reply_text(f"Starting preview tunnel for `{name}`...")

    try:
        port = 8080 + abs(hash(name)) % 1000
        server_proc = subprocess.Popen(
            ["python3", "-m", "http.server", str(port), "--directory", output_dir],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        tunnel_proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        active_tunnels[name] = (tunnel_proc, server_proc)

        url = None
        for line in tunnel_proc.stdout:
            match = re.search(r"(https://[a-z0-9-]+\.trycloudflare\.com)", line)
            if match:
                url = match.group(1)
                break

        if url:
            await update.message.reply_text(
                f"Preview ready:\n{url}\n\nUse /stop {name} to tear down."
            )
        else:
            await update.message.reply_text(
                "Tunnel started but couldn't find URL. Check logs."
            )

    except FileNotFoundError:
        await update.message.reply_text("cloudflared not found in bot container.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@auth
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not os.path.isdir(WORKSPACES_DIR):
        await update.message.reply_text("No workspaces yet.")
        return

    entries = sorted(os.listdir(WORKSPACES_DIR))
    if not entries:
        await update.message.reply_text("No workspaces yet.")
        return

    lines = []
    for name in entries:
        ws = os.path.join(WORKSPACES_DIR, name)
        if not os.path.isdir(ws):
            continue
        has_build = os.path.exists(os.path.join(ws, "index.html"))
        try:
            c = docker_client.containers.get(name)
            status = c.status
        except docker.errors.NotFound:
            status = "done" if has_build else "stopped"
        emoji = "✅" if has_build else "⏳" if status == "running" else "⬜"
        lines.append(f"{emoji} `{name}` — {status}")

    await update.message.reply_text("\n".join(lines) or "No workspaces.", parse_mode="Markdown")


@auth
async def cmd_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Write feedback to a running agent's feedback directory."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /msg <agent-name> <your feedback>")
        return

    name = context.args[0]
    feedback = " ".join(context.args[1:])
    output_dir = os.path.join(WORKSPACES_DIR, name)

    if not os.path.isdir(output_dir):
        await update.message.reply_text(f"No workspace found for `{name}`.")
        return

    # Write feedback to a file the agent can read
    feedback_dir = os.path.join(output_dir, "feedback")
    os.makedirs(feedback_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    feedback_file = os.path.join(feedback_dir, f"{ts}.txt")
    with open(feedback_file, "w") as f:
        f.write(feedback)

    await update.message.reply_text(f"Feedback sent to `{name}`.")


@auth
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text as a build prompt."""
    text = update.message.text.strip()
    if not text:
        return

    name = agent_name(text)
    await update.message.reply_text(
        f"Spawning agent `{name}`...\n\nPrompt: {text[:200]}"
    )

    try:
        spawn_agent(name, text, update.effective_chat.id)
        await update.message.reply_text(
            f"Agent `{name}` is running. I'll notify you when it's done."
        )
        asyncio.create_task(
            monitor_container(name, update.effective_chat.id, context.application)
        )
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")


def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("build", cmd_build))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("msg", cmd_msg))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
