import logging
import os
import random

import pymongo
import pymongo.collection
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError

load_dotenv()

TOKEN = os.getenv("TG_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
PASSWORD = os.getenv("PASSWORD")
DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

client = pymongo.MongoClient(MONGODB_URI, connect=False)
db = client["db"]
users_collection = db.users
links_collection = db.links


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user["id"]
    if users_collection.find_one({"user_id": user_id}):
        await update.message.reply_text("You already joined LUCKY LINKS.")
        return

    users_collection.insert_one({"user_id": user_id, "status": "unverified"})
    logger.info(f"New user joined. (user id: {user_id})")
    await update.message.reply_text(
        "Welcome to LUCKY LINKS. Enter password to proceed."
    )


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user["id"]
    user = users_collection.find_one({"user_id": user_id})

    if not user:
        await update.message.reply_text("You need to start the bot first using /start.")
        return
    if user.get("status") == "verified":
        await update.message.reply_text("You are already verified!")
        return

    password = context.args[0] if context.args else None
    if password is None:
        await update.message.reply_text("Please enter a password.")
        return
    if password != PASSWORD:
        await update.message.reply_text("Invalid password. Please try again.")
        logger.info(f"Invalid verification occurred. (user id: {user_id})")
        return

    users_collection.update_one({"user_id": user_id}, {"$set": {"status": "verified"}})
    logger.info(f"New user verified. (user id: {user_id})")
    await update.message.reply_text("Verification successful!")


async def new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user["id"]
    user = users_collection.find_one({"user_id": user_id})

    if not user:
        await update.message.reply_text("You need to start the bot first using /start.")
        return

    if user.get("status") != "verified":
        await update.message.reply_text(
            "You need to be verified to add links. Please use /verify <password> first."
        )
        return

    link = link = context.args[0] if context.args else None
    if link is None:
        await update.message.reply_text("Please provide a link.")
        return

    links_collection.insert_one({"user_id": user_id, "link": link})
    logger.info(f"New link added. (user id: {user_id})")
    await update.message.reply_text("Link added successfully.")


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user["id"]
    user = users_collection.find_one({"user_id": user_id})

    if not user:
        await update.message.reply_text("You need to start the bot first using /start.")
        return

    if user.get("status") != "verified":
        await update.message.reply_text(
            "You need to be verified to delete links. Please use /verify <password> first."
        )
        return

    link = link = context.args[0] if context.args else None
    if link is None:
        await update.message.reply_text("Please provide a link.")
        return

    result = links_collection.delete_one({"user_id": user_id, "link": link})
    if result.deleted_count > 0:
        logger.info(f"Link deleted. (user id: {user_id})")
        await update.message.reply_text("Link deleted successfully.")
    else:
        await update.message.reply_text("Link not found.")


async def lucky(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user["id"]
    user = users_collection.find_one({"user_id": user_id})

    if not user:
        await update.message.reply_text("You need to start the bot first using /start.")
        return

    if user.get("status") != "verified":
        await update.message.reply_text(
            "You need to be verified to use this command. Please use /verify <password> first."
        )
        return

    count = links_collection.count_documents({"user_id": user_id})
    if count == 0:
        await update.message.reply_text("You have no links saved.")
        return

    random_index = random.randint(0, count - 1)
    link = (
        links_collection.find({"user_id": user_id}).skip(random_index).limit(1).next()
    )
    logger.info(f"Lucky link generated. (user id: {user_id})")
    await update.message.reply_text(link["link"])


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Here are the commands you can use:\n\n"
        "/start - Join LUCKY LINKS.\n"
        "/verify <password> - Verify yourself.\n"
        "/new <link> - Add a new link (available only to verified users).\n"
        "/delete <link> - Delete a specific link (available only to verified users).\n"
        "/lucky - Receive a LUCKY LINK (available only to verified users).\n"
        "/help - Show this help message."
    )
    await update.message.reply_text(help_text)


async def error_simulator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise Exception("This is a simulated exception.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    responses = ["You feeling LUCKY?", "Send me a LINK!"]
    await update.message.reply_text(random.choice(responses))


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Unknown command. Type /help for more info.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception occurred", exc_info=True)

    # Extract the message content that caused the error
    user_message = "No message content"
    user_id = "Unknown"
    first_name = "Unknown"

    if isinstance(update, Update) and update.effective_message:
        user_message = update.effective_message.text or "Non-text message"
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        first_name = (
            update.effective_user.first_name if update.effective_user else "Unknown"
        )

    # Prepare the error message to send to the developer
    error_message = (
        f"🚨 *Bot Error Alert* 🚨\n\n"
        f"*Exception:* `{context.error}`\n"
        f"*User:* [{first_name}](tg://user?id={user_id}) (ID: `{user_id}`)\n"
        f"*Chat ID:* `{update.effective_chat.id if update.effective_chat else 'Unknown'}`\n"
        f"*Message Sent:* `{user_message}`\n"
    )

    # Send the error message to the developer
    try:
        await context.bot.send_message(
            chat_id=DEVELOPER_CHAT_ID, text=error_message, parse_mode="Markdown"
        )
    except TelegramError as e:
        logger.error(f"Failed to send error report: {e}")


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("new", new))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("lucky", lucky))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("error", error_simulator))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
