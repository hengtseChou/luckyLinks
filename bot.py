import logging
import os
import random
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

### Config ###
load_dotenv()

TG_TOKEN = os.getenv("TG_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
PASSWORD = os.getenv("PASSWORD")
DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")


### Mongo Setup ###
@contextmanager
def mongo_connection():
    """Context manager for handling MongoDB connections."""
    client = MongoClient(MONGO_URL, maxPoolSize=10, minPoolSize=1)
    try:
        database = client["data"]
        yield database
    finally:
        client.close()


### Logging Setup ###
class MyLogger(logging.Logger):
    def __init__(self, name: str) -> None:
        super().__init__(name)

    def info(self, msg, db, *args, **kwargs):
        super().info(msg, *args, **kwargs)
        db.logs.insert_one({"level": "INFO", "message": msg, "timestamp": datetime.now(timezone.utc)})

    def error(self, msg, db, *args, **kwargs):
        super().error(msg, *args, **kwargs)
        db.logs.insert_one({"level": "ERROR", "message": msg, "timestamp": datetime.now(timezone.utc)})


logger = MyLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(levelname)s - %(message)s")
stream_handler = logging.StreamHandler(stream=sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

logging.getLogger("httpx").setLevel(logging.WARNING)


### Bot Handlers ###
async def handle_invalid_attempt(update: Update, attempt_type: str, context: ContextTypes.DEFAULT_TYPE = None) -> None:
    if attempt_type == "not_started":
        await update.effective_message.reply_text("You need to start the bot first using /start.")
    elif attempt_type == "not_verified":
        await update.effective_message.reply_text(
            "You need to be verified to use this command. Please use /verify <password> first."
        )
        message = (
            f"*Someone is UNLUCKY...*\n\n"
            f"*Type*: Failed attempt to use advanced commands.\n"
            f"*User*: [{update.effective_user.first_name}](tg://user?id={update.effective_user.id})\n"
            f"*Message Sent*: {update.effective_message.text or 'Non-text message'}\n"
        )
        await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)
    elif attempt_type == "failed_verification":
        await update.effective_message.reply_text("Invalid password. Please try again.")
        message = (
            f"*Someone is UNLUCKY...*\n\n"
            f"*Type*: Invalid Verification\n"
            f"*User*: [{update.effective_user.first_name}](tg://user?id={update.effective_user.id})\n"
            f"*Message Sent*: {update.effective_message.text or 'Non-text message'}\n"
        )
        await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    with mongo_connection() as db:
        users = db.users
        if users.find_one({"user_id": user_id}):
            await update.effective_message.reply_text("You already joined LUCKY LINKS.")
            return
        users.insert_one({"user_id": user_id, "status": "unverified"})
        logger.info(f"New user joined (user id: {user_id})", db)

    await update.effective_message.reply_text("Welcome to LUCKY LINKS. Please use /verify <password> to proceed.")
    await context.bot.send_message(
        chat_id=DEVELOPER_CHAT_ID,
        text=f"[{update.effective_user.full_name}](tg://user?id={user_id}) joined LUCKY LINKS.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    with mongo_connection() as db:
        users = db.users
        user = users.find_one({"user_id": user_id})
        if not user:
            await handle_invalid_attempt(update, "not_started")
            return
        if user.get("status") == "verified":
            await update.effective_message.reply_text("You are already verified!")
            return

        password = context.args[0] if context.args else None
        if password is None:
            await update.effective_message.reply_text("Please enter a password.")
            return
        if password != PASSWORD:
            await handle_invalid_attempt(update, "failed_verification", context)
            logger.info(f"Invalid verification occurred (user id: {user_id})")
            return

        users.update_one({"user_id": user_id}, {"$set": {"status": "verified"}})
        logger.info(f"User verified (user id: {user_id})", db)

    await update.effective_message.reply_text("Verification successful!")


async def new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    with mongo_connection() as db:
        users = db.users
        user = users.find_one({"user_id": user_id})
        if not user:
            await handle_invalid_attempt(update, "not_started")
            return
        if user.get("status") != "verified":
            await handle_invalid_attempt(update, "not_verified", context)
            return

        link = context.args[0] if context.args else None
        if link is None:
            await update.effective_message.reply_text("Please provide a link.")
            return
        links = db.links
        links.insert_one({"user_id": user_id, "link": link})
        logger.info(f"Link added: {link} (user id: {user_id})", db)

    await update.effective_message.reply_text("Link added successfully.")


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    with mongo_connection() as db:
        users = db.users
        user = users.find_one({"user_id": user_id})
        if not user:
            await handle_invalid_attempt(update, "not_started")
            return
        if user.get("status") != "verified":
            await handle_invalid_attempt(update, "not_verified", context)
            return

        link = context.args[0] if context.args else None
        if link is None:
            await update.effective_message.reply_text("Please provide a link.")
            return
        entries = db.links
        result = entries.delete_one({"user_id": user_id, "link": link})

        if result.deleted_count > 0:
            logger.info(f"Link deleted: {link} (user id: {user_id})", db)
            await update.effective_message.reply_text("Link deleted successfully.")
        else:
            await update.effective_message.reply_text("Link not found.")


async def lucky(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    with mongo_connection() as db:
        users = db.users
        user = users.find_one({"user_id": user_id})
        if not user:
            await handle_invalid_attempt(update, "not_started")
            return
        if user.get("status") != "verified":
            await handle_invalid_attempt(update, "not_verified", context)
            return

        entries = db.links
        count = entries.count_documents({"user_id": user_id})
        if count == 0:
            await update.effective_message.reply_text("You have no links saved.")
            return

        random_index = random.randint(0, count - 1)
        link = entries.find({"user_id": user_id}).skip(random_index).limit(1).next()["link"]
        logger.info(f"Lucky link: {link} (user id: {user_id})", db)

    await update.effective_message.reply_text(link)


async def dedup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    with mongo_connection() as db:
        users = db.users
        user = users.find_one({"user_id": user_id})
        if not user:
            await handle_invalid_attempt(update, "not_started")
            return
        if user.get("status") != "verified":
            await handle_invalid_attempt(update, "not_verified", context)
            return

        entries = db.links
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$group": {
                    "_id": "$link",
                    "count": {"$sum": 1},
                    "doc_ids": {"$push": "$_id"},
                }
            },
            {"$match": {"count": {"$gt": 1}}},
        ]
        duplicates = entries.aggregate(pipeline)
        deleted = 0
        for dup in duplicates:
            doc_ids = dup["doc_ids"]
            ids_to_remove = doc_ids[1:]
            if ids_to_remove:
                result = entries.delete_many({"_id": {"$in": ids_to_remove}})
                deleted += result.deleted_count
        remaining = entries.count_documents({"user_id": user_id})
        logger.info(f"Dedup: {deleted} entries deleted, current count={remaining} (user id: {user_id})", db)

    await update.effective_message.reply_text(f"Deleted duplicates: {deleted}. Remaining links: {remaining}.")


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    with mongo_connection() as db:
        users = db.users
        user = users.find_one({"user_id": user_id})
        if not user:
            await handle_invalid_attempt(update, "not_started")
            return
        if user.get("status") != "verified":
            await handle_invalid_attempt(update, "not_verified", context)
            return

        search_term = context.args[0] if context.args else None
        if search_term is None:
            await update.effective_message.reply_text("Please provide a keyword to search.")
            return

        entries = db.links
        regex_pattern = re.compile(search_term, re.IGNORECASE)
        count = entries.count_documents({"user_id": user_id, "link": {"$regex": regex_pattern}})
        if count == 0:
            await update.effective_message.reply_text("No matching links found.")
            return
        else:
            message = "*These links are FEELING LUCKY:* \n\n"
            results = entries.find({"user_id": user_id, "link": {"$regex": regex_pattern}})
            for doc in results:
                message += f"• {doc['link']}\n"
            await update.effective_message.reply_text(text=message, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Here are the commands you can use:\n\n"
        "/start - Join LUCKY LINKS.\n"
        "/verify <password> - Verify yourself.\n"
        "/new <link> - Add a new link (available only to verified users).\n"
        "/delete <link> - Delete a specific link (available only to verified users).\n"
        "/lucky - Receive a LUCKY LINK (available only to verified users).\n"
        "/dedup - Delete duplicate links (available only to verified users).\n"
        "/search <keyword> - Search for links containing a keyword (available only to verified users).\n"
        "/help - Show this help message."
    )
    await update.effective_message.reply_text(help_text)


async def error_simulator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise Exception("This is a simulated exception.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    responses = ["You feeling LUCKY?", "Send me a LINK!"]
    await update.effective_message.reply_text(random.choice(responses))


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Unknown command. Type /help for more info.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update and update.effective_message:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        chat_id = update.effective_chat.id
        message = update.effective_message.text or "Non-text message"
        error_message = (
            f"🚨 *Bot Error Alert* 🚨\n\n"
            f"*Exception: * `{context.error}`\n"
            f"*User: * [{first_name}](tg://user?id={user_id})\n"
            f"*Chat ID: * `{chat_id}`\n"
            f"*Message Sent: * `{message}`\n"
        )
    else:
        error_message = f"🚨 *Bot Error Alert* 🚨\n\n*Exception :* `{context.error}`\n"

    await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=error_message, parse_mode=ParseMode.MARKDOWN)
    with mongo_connection() as db:
        logger.error(f"{context.error}", db)


def main():
    app = ApplicationBuilder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("new", new))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("lucky", lucky))
    app.add_handler(CommandHandler("dedup", dedup))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("error", error_simulator))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    app.add_error_handler(error_handler)
    app.run_polling()


if __name__ == "__main__":
    main()
