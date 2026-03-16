import os
import re
import subprocess
import logging

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
# TELEGRAM MESSAGE LIMIT
# =========================

async def send_long_message(update, text):

    max_length = 4000

    for i in range(0, len(text), max_length):
        await update.message.reply_text(text[i:i+max_length])


# =========================
# INTENT PROMPT
# =========================

def build_prompt(user_text):

    return f"""
You are an AI developer assistant.

User message:
{user_text}

Determine intent.

Possible intents:

CHAT → normal conversation  
CREATE_FILES → user wants code/project files

Rules:

If chatting:

INTENT: CHAT
ANSWER:
<response>

If user asks for code or project generation:

INTENT: CREATE_FILES

Return files in this format:

FILE: filename
CODE:
<code>

Example:

FILE: main.py
CODE:
print("hello")
"""


# =========================
# MAIN HANDLER
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.message.from_user.id

    try:

        # =====================
        # PUSH CONFIRMATION
        # =====================

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

        # =====================
        # AI RESPONSE
        # =====================

        prompt = build_prompt(user_text)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        text = response.text

        # =====================
        # CHAT RESPONSE
        # =====================

        if "INTENT: CHAT" in text:

            answer = text.split("ANSWER:")[1].strip()

            await send_long_message(update, answer)

            return

        # =====================
        # FILE GENERATION
        # =====================

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

        # fallback
        await send_long_message(update, text)

    except Exception as e:

        logger.error(e)

        await update.message.reply_text("Something went wrong.")


# =========================
# START BOT
# =========================

def main():

    logger.info("Starting Telegram AI Bot...")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()