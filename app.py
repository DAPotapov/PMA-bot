# From https://gitlab.com/Athamaxy/telegram-bot-tutorial/-/blob/main/TutorialBot.py

import logging
import os
import time

from dotenv import load_dotenv
from telegram import Update, ForceReply, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, Updater, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters



logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Store bot screaming status
screaming = False

# Pre-assign menu text
FIRST_MENU = "<b>Menu 1</b>\n\nA beautiful menu with a shiny inline button."
SECOND_MENU = "<b>Menu 2</b>\n\nA better menu with even more shiny inline buttons."

# Pre-assign button text
NEXT_BUTTON = "Next"
BACK_BUTTON = "Back"
TUTORIAL_BUTTON = "Tutorial"

# Build keyboards
FIRST_MENU_MARKUP = InlineKeyboardMarkup([[
    InlineKeyboardButton(NEXT_BUTTON, callback_data=NEXT_BUTTON)
]])
SECOND_MENU_MARKUP = InlineKeyboardMarkup([
    [InlineKeyboardButton(BACK_BUTTON, callback_data=BACK_BUTTON)],
    [InlineKeyboardButton(TUTORIAL_BUTTON, url="https://core.telegram.org/bots/api")]
])


async def echo(update: Update, context: CallbackContext) -> None:
    """
    This function would be added to the application as a handler for messages coming from the Bot API
    """

    # Print to console
    # user = update.effective_user
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    firstname = update.message.from_user.first_name
    text = str(update.message.text) + ', ' + str(username)
    print(f'{firstname} wrote {text}')
    logger.info(f'{time.asctime()}\t{user_id} ({username}): {text}')

    if screaming and update.message.text:
        await update.message.reply_text(text.upper())
        # From v.13
        # context.bot.send_message(
        #     update.message.chat_id,
        #     text.upper(),
        #     # To preserve the markdown, we attach entities (bold, italic...)
        #     entities=update.message.entities
        # )
    else:
        # print("This is else")
        # This is equivalent to forwarding, without the sender's name
        await update.message.reply_text(text)


def scream(update: Update, context: CallbackContext) -> None:
    """
    This function handles the /scream command
    """

    global screaming
    screaming = True


def whisper(update: Update, context: CallbackContext) -> None:
    """
    This function handles /whisper command
    """

    global screaming
    screaming = False


def menu(update: Update, context: CallbackContext) -> None:
    """
    This handler sends a menu with the inline buttons we pre-assigned above
    """

    context.bot.send_message(
        update.message.from_user.id,
        FIRST_MENU,
        parse_mode=ParseMode.HTML,
        reply_markup=FIRST_MENU_MARKUP
    )


def button_tap(update: Update, context: CallbackContext) -> None:
    """
    This handler processes the inline buttons on the menu
    """

    data = update.callback_query.data
    text = ''
    markup = None

    if data == NEXT_BUTTON:
        text = SECOND_MENU
        markup = SECOND_MENU_MARKUP
    elif data == BACK_BUTTON:
        text = FIRST_MENU
        markup = FIRST_MENU_MARKUP

    # Close the query to end the client-side loading animation
    update.callback_query.answer()

    # Update message content with corresponding menu section
    update.callback_query.message.edit_text(
        text,
        ParseMode.HTML,
        reply_markup=markup
    )

def help(update: Update, context: CallbackContext) -> None:
    """
    This function handles /help command
    """
    bot_msg = "Should print description to user"
    context.bot.send_message(
            update.message.chat_id,
            bot_msg,
            # To preserve the markdown, we attach entities (bold, italic...)
            entities=update.message.entities
        )

def status(update: Update, context: CallbackContext) -> None:
    """
    This function handles /status command
    """
    bot_msg = "Should print status to user"
    context.bot.send_message(
            update.message.chat_id,
            bot_msg,
            # To preserve the markdown, we attach entities (bold, italic...)
            entities=update.message.entities
        ) 

    n = 10
    for i in range(n):
        time.sleep(2)
        bot_msg = f'Current task is: {i}'
        context.bot.send_message(
            update.message.chat_id, 
            bot_msg,
            entities=update.message.entities
        )


def freshstart(update: Update, context: CallbackContext) -> None:
    """
    This function handles /freshstart command
    """

    bot_msg = "Here will be routine to start a new project"
    context.bot.send_message(
            update.message.chat_id,
            bot_msg,
            # To preserve the markdown, we attach entities (bold, italic...)
            entities=update.message.entities
        )   

def settings(update: Update, context: CallbackContext) -> None:
    """
    This function handles /settings command
    """
    bot_msg = "Here PM should be able to change some of project settings. If no project started yet, then redirect to freshstart"
    context.bot.send_message(
            update.message.chat_id,
            bot_msg,
            # To preserve the markdown, we attach entities (bold, italic...)
            entities=update.message.entities
        ) 

def upload(update: Update, context: CallbackContext) -> None:
    '''
    Function to upload new project file
    '''

    pass

def main() -> None:
    # updater = Updater("<YOUR_BOT_TOKEN_HERE>")
    load_dotenv()
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    # updater = Updater(BOT_TOKEN) # deprecated
    # Create a builder via Application.builder() and then specifies all required arguments via that builder.
    #  Finally, the Application is created by calling builder.build()
    application = Application.builder().token(BOT_TOKEN).build()


    # Get the dispatcher to register handlers
    # Then, we register each handler and the conditions the update must meet to trigger it
    # dispatcher = updater.dispatcher # depricated

    # Register commands
    application.add_handler(CommandHandler("scream", scream))
    application.add_handler(CommandHandler("whisper", whisper))
    application.add_handler(CommandHandler("menu", menu))
    #TODO: Add more commands
    # dispatcher.add_handler(CommandHandler("start", start)) 
    # dispatcher.add_handler(CommandHandler("stop", stop)) # in case smth went wrong 
    application.add_handler(CommandHandler("help", help)) # make it show description
    # PM should have the abibility to change bot behaviour, such as reminder interval and so on
    application.add_handler(CommandHandler("settings", settings))
    # Command to trigger project status check.
    application.add_handler(CommandHandler("status", status))
    # Initialize start of the project: project name, db initialization and so on, previous project should be archived
    application.add_handler(CommandHandler("freshstart", freshstart))  
    # It will be useful if schedule changed outside the bot
    application.add_handler(CommandHandler("upload", upload))  
    # And if changes were made inside the bot, PM could download updated schedule
    # dispatcher.add_handler(CommandHandler("download", download))

    # Register handler for inline buttons
    application.add_handler(CallbackQueryHandler(button_tap))

    # Echo any message that is text and not a command
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Start the Bot
    application.run_polling()

    # Run the bot until you press Ctrl-C
    # application.idle()


if __name__ == '__main__':
    main()