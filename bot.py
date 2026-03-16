import os
import requests
import re
import subprocess
import logging
import threading
import traceback
from flask import Flask

from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# =========================
# LOGGING
# =========================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# =========================
# ENV VARIABLES
# =========================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

# =========================
# WORKSPACE
# =========================

WORKSPACE = "workspace"
os.makedirs(WORKSPACE, exist_ok=True)

# =========================
# GEMINI CLIENT
# =========================

client = genai.Client(api_key=GEMINI_API_KEY)

pending_push = {}

# =========================
# FLASK SERVER (Render free tier)
# =========================

web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Telegram AI Bot Running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

# =========================
# FILE WRITER
# =========================

def write_file(project, filename, content):

    project_path = os.path.join(WORKSPACE, project)
    os.makedirs(project_path, exist_ok=True)

    file_path = os.path.join(project_path, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path

# =========================
# FILE PARSER
# =========================

def extract_files(text):

    pattern = r"FILE:\s*(.*?)\nCODE:\n([\s\S]*?)(?=\nFILE:|$)"
    matches = re.findall(pattern, text)

    files = []

    for filename, code in matches:
        files.append((filename.strip(), code.strip()))

    return files

# =========================
# PUSH TO GITHUB
# =========================

def push_to_github(project):

    path = os.path.join(WORKSPACE, project)

    try:

        # ----------------------
        # CREATE GITHUB REPO
        # ----------------------

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }

        repo_data = {
            "name": project,
            "private": False
        }

        requests.post(
            "https://api.github.com/user/repos",
            headers=headers,
            json=repo_data
        )

        # ----------------------
        # INIT LOCAL REPO
        # ----------------------

        subprocess.run(["git", "init"], cwd=path, check=True)

        subprocess.run(
            ["git", "config", "user.email", "bot@telegram.ai"],
            cwd=path,
            check=True
        )

        subprocess.run(
            ["git", "config", "user.name", "Telegram AI Bot"],
            cwd=path,
            check=True
        )

        subprocess.run(["git", "add", "."], cwd=path, check=True)

        subprocess.run(
            ["git", "commit", "-m", "AI generated project"],
            cwd=path,
            check=True
        )

        # ----------------------
        # ADD REMOTE
        # ----------------------

        repo_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{project}.git"

        subprocess.run(
            ["git", "remote", "add", "origin", repo_url],
            cwd=path,
            check=True
        )

        subprocess.run(["git", "branch", "-M", "main"], cwd=path)

        subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=path,
            check=True
        )

        return True

    except Exception as e:

        logger.error(e)

        return False

# =========================
# TELEGRAM MESSAGE LIMIT
# =========================

async def send_long_message(update, text):

    max_length = 4000

    for i in range(0, len(text), max_length):
        await update.message.reply_text(text[i:i+max_length])

# =========================
# PROMPT BUILDER
# =========================

def build_prompt(user_text):

    return f"""
You are an AI coding assistant.

User message:
{user_text}

Determine intent.

Possible intents:

CHAT
CREATE_FILES

Respond ONLY in one of these formats.

For chat:

INTENT: CHAT
ANSWER: <response>

For code generation:

INTENT: CREATE_FILES

FILE: filename
CODE:
<code>

Example:

FILE: main.py
CODE:
print("hello world")
"""

# =========================
# MAIN HANDLER
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.message.from_user.id

    try:

        # PUSH CONFIRMATION

        if user_text.lower() == "yes" and user_id in pending_push:

            project = pending_push[user_id]

            success = push_to_github(project)

            if success:
                await update.message.reply_text("Project pushed to GitHub successfully")
            else:
                await update.message.reply_text("GitHub push failed")

            del pending_push[user_id]
            return

        prompt = build_prompt(user_text)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        text = response.text

        # CHAT RESPONSE

        if "INTENT: CHAT" in text:

            if "ANSWER:" in text:
                answer = text.split("ANSWER:",1)[1].strip()
            else:
                answer = text

            await send_long_message(update, answer)
            return

        # FILE GENERATION

        if "INTENT: CREATE_FILES" in text:

            files = extract_files(text)

            if not files:
                await send_long_message(update, text)
                return

            project = "ai_project"

            created = []

            for filename, code in files:

                path = write_file(project, filename, code)
                created.append(path)

            pending_push[user_id] = project

            await update.message.reply_text(
                "Files generated:\n\n"
                + "\n".join(created)
                + "\n\nReply YES to push to GitHub."
            )

            return

        await send_long_message(update, text)

    except Exception as e:

        traceback.print_exc()
        logger.error(str(e))

        await update.message.reply_text("Something went wrong.")

# =========================
# START BOT
# =========================

def main():

    logger.info("Starting Telegram AI Bot...")

    # Start Flask server for Render free tier
    threading.Thread(target=run_web).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    main()