import os
import re
import subprocess
import logging

from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# =========================
# LOGGING (important for Render logs)
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
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
# WORKSPACE SETUP
# =========================

WORKSPACE = "workspace"
os.makedirs(WORKSPACE, exist_ok=True)

# =========================
# GEMINI CLIENT
# =========================

client = genai.Client(api_key=GEMINI_API_KEY)

pending_push = {}

# =========================
# UTIL: WRITE FILE
# =========================

def write_file(project, filename, content):

    project_path = os.path.join(WORKSPACE, project)
    os.makedirs(project_path, exist_ok=True)

    file_path = os.path.join(project_path, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


# =========================
# UTIL: EXTRACT FILES
# =========================

def extract_files(text):

    pattern = r"FILE:\s*(.*?)\nCODE:\n([\s\S]*?)(?=\nFILE:|$)"
    matches = re.findall(pattern, text)

    files = []

    for filename, code in matches:
        files.append((filename.strip(), code.strip()))

    return files


# =========================
# UTIL: PUSH TO GITHUB
# =========================

def push_to_github(project):

    path = os.path.join(WORKSPACE, project)

    try:

        subprocess.run(["git", "init"], cwd=path, check=True)
        subprocess.run(["git", "add", "."], cwd=path, check=True)
        subprocess.run(["git", "commit", "-m", "AI generated project"], cwd=path, check=True)

        repo_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{project}.git"

        subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=path)
        subprocess.run(["git", "branch", "-M", "main"], cwd=path)

        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=path, check=True)

        return True

    except Exception as e:

        logger.error(e)
        return False


# =========================
# UTIL: TELEGRAM MESSAGE LIMIT
# =========================

async def send_long_message(update, text):

    max_length = 4000

    for i in range(0, len(text), max_length):
        await update.message.reply_text(text[i:i + max_length])


# =========================
# MAIN BOT HANDLER
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.message.from_user.id

    try:

        # -------- PUSH CONFIRMATION --------

        if user_text.lower() == "yes" and user_id in pending_push:

            project = pending_push[user_id]

            success = push_to_github(project)

            if success:
                await update.message.reply_text(
                    f"Project pushed to GitHub successfully: {project}"
                )
            else:
                await update.message.reply_text("GitHub push failed.")

            del pending_push[user_id]
            return

        # -------- GEMINI PROMPT --------

        prompt = f"""
You are an AI coding assistant.

User request:
{user_text}

Generate project files.

Return ONLY in this format:

FILE: filename
CODE:
<code>

Example:

FILE: main.py
CODE:
print("hello")
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        text = response.text

        files = extract_files(text)

        if not files:

            await send_long_message(update, text)
            return

        project = "ai_project"

        created_files = []

        for filename, code in files:

            path = write_file(project, filename, code)
            created_files.append(path)

        pending_push[user_id] = project

        file_list = "\n".join(created_files)

        await update.message.reply_text(
            f"Files generated:\n\n{file_list}\n\nReply YES to push to GitHub."
        )

    except Exception as e:

        logger.error(e)
        await update.message.reply_text("An error occurred.")


# =========================
# START BOT
# =========================

def main():

    logger.info("Starting Telegram AI Bot...")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()