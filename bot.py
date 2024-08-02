import logging
import os
import random

import pymongo
import pymongo.collection
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("TG_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
PASSWORD = os.getenv("PASSWORD")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.ERROR)

client = pymongo.MongoClient(MONGODB_URI, connect=False)
db = client["db"]
users_collection = db.users
links_collection = db.links


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user["id"]
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({"user_id": user_id, "status": "unverified"})
        logging.info(f"New user joined. (user id: {user_id})")
        await update.message.reply_text("Welcome to Lucky Links. Enter password to proceed.")
    else:
        await update.message.reply_text("The bot has already started.")


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        password = context.args[0] if context.args else None
        user_id = update.message.from_user["id"]
        user = users_collection.find_one({"user_id": user_id})

        if user:
            if password == PASSWORD:
                users_collection.update_one({"user_id": user_id}, {"$set": {"status": "verified"}})
                logging.info(f"New user verified. (user id: {user_id})")
                await update.message.reply_text("Verification successful!")
            else:
                await update.message.reply_text("Invalid password. Please try again.")
        else:
            await update.message.reply_text("You need to start the bot first using /start.")
    except IndexError:
        await update.message.reply_text("Please enter a password.")


async def new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        link = context.args[0] if context.args else None
        user_id = update.message.from_user["id"]
        user = users_collection.find_one({"user_id": user_id})

        if user:
            if user.get("status") == "verified":
                if link:
                    links_collection.insert_one({"user_id": user_id, "link": link})
                    logging.info(f"New link added. (user id: {user_id})")
                    await update.message.reply_text("Link added successfully.")
                else:
                    await update.message.reply_text("Please provide a link.")
            else:
                await update.message.reply_text(
                    "You need to be verified to add links. Please use /verify <password> first."
                )
        else:
            await update.message.reply_text("You need to start the bot first using /start.")
    except IndexError:
        await update.message.reply_text("Please provide a link.")


async def lucky(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user = users_collection.find_one({"user_id": user_id})

    if user:
        if user.get("status") == "verified":
            count = links_collection.count_documents({"user_id": user_id})
            if count == 0:
                await update.message.reply_text("You have no links saved.")
                return

            random_index = random.randint(0, count - 1)
            link = links_collection.find({"user_id": user_id}).skip(random_index).limit(1).next()
            logging.info(f"Lucky link generated. (user id: {user_id})")
            await update.message.reply_text(link["link"])
        else:
            await update.message.reply_text(
                "You need to be verified to use this command. Please use /verify <password> first."
            )
    else:
        await update.message.reply_text("You need to start the bot first using /start.")


def main():

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("new", new))
    app.add_handler(CommandHandler("lucky", lucky))

    app.run_polling()


if __name__ == "__main__":
    main()
