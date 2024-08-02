import html
import json
import logging
import os
import random
import traceback

import pymongo
import pymongo.collection
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

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
        await update.message.reply_text("You already joined Lucky Links.")
        return

    users_collection.insert_one({"user_id": user_id, "status": "unverified"})
    logger.info(f"New user joined. (user id: {user_id})")
    await update.message.reply_text("Welcome to Lucky Links. Enter password to proceed.")


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        password = context.args[0] if context.args else None
    except IndexError:
        await update.message.reply_text("Please enter a password.")
        return

    user_id = update.message.from_user["id"]
    user = users_collection.find_one({"user_id": user_id})

    if not user:
        await update.message.reply_text("You need to start the bot first using /start.")
        return

    if password != PASSWORD:
        await update.message.reply_text("Invalid password. Please try again.")
        return

    users_collection.update_one({"user_id": user_id}, {"$set": {"status": "verified"}})
    logger.info(f"New user verified. (user id: {user_id})")
    await update.message.reply_text("Verification successful!")


async def new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        link = context.args[0] if context.args else None
    except IndexError:
        await update.message.reply_text("Please provide a link.")
        return

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

    links_collection.insert_one({"user_id": user_id, "link": link})
    logger.info(f"New link added. (user id: {user_id})")
    await update.message.reply_text("Link added successfully.")


async def del_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        link = context.args[0] if context.args else None
    except IndexError:
        await update.message.reply_text("Please provide a link to delete.")
        return

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

    result = links_collection.delete_one({"user_id": user_id, "link": link})
    if result.deleted_count > 0:
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
    link = links_collection.find({"user_id": user_id}).skip(random_index).limit(1).next()
    logger.info(f"Lucky link generated. (user id: {user_id})")
    await update.message.reply_text(link["link"])


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user["id"]
    help_text = (
        "Here are the commands you can use:\n\n"
        "/start - Join Lucky Links.\n"
        "/verify <password> - Verify yourself.\n"
        "/new <link> - Add a new link (available only to verified users).\n"
        "/del <link> - Delete a specific link (available only to verified users).\n"
        "/lucky - Receive a LUCKY link (available only to verified users).\n"
        "/help - Show this help message."
    )
    logger.info(f"Help sent. (user id: {user_id})")
    await update.message.reply_text(help_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    user_id = update.message.from_user["id"]
    logger.info(f"Msg: {text}. (user id: {user_id})")
    responses = ["You feeling LUCKY?", "Send me a LINK!"]
    await update.message.reply_text(random.choice(responses))


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    user_id = update.message.from_user["id"]
    logger.info(f"Unknown command: {text}. (user id: {user_id})")
    await update.message.reply_text("Unknown command. Type /help for more info.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    await context.bot.send_message(
        chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML
    )


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("new", new))
    app.add_handler(CommandHandler("del", del_link))
    app.add_handler(CommandHandler("lucky", lucky))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
