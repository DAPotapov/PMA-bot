# From https://gitlab.com/Athamaxy/telegram-bot-tutorial/-/blob/main/TutorialBot.py

import logging
import os
import time
# import asyncio


from dotenv import load_dotenv
from io import BufferedIOBase
from telegram import Update, ForceReply, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, Updater, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Store bot screaming status
screaming = False

# Project constants, should be stored separately TODO
# TODO: change according to starter of the bot
PM = 'hagen10'
PROJECTTITLE = ''

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


async def scream(update: Update, context: CallbackContext) -> None:
    """
    This function handles the /scream command
    """

    global screaming
    screaming = True


async def whisper(update: Update, context: CallbackContext) -> None:
    """
    This function handles /whisper command
    """

    global screaming
    screaming = False


async def menu(update: Update, context: CallbackContext) -> None:
    """
    This handler sends a menu with the inline buttons we pre-assigned above
    """
    # From v.13.  On this step of development not needed
    # context.bot.send_message(
    #     update.message.from_user.id,
    #     FIRST_MENU,
    #     parse_mode=ParseMode.HTML,
    #     reply_markup=FIRST_MENU_MARKUP
    # )


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

async def help(update: Update, context: CallbackContext) -> None:
    """
    This function handles /help command
    """
    bot_msg = "Should print description to user"
    # From v.13
    # context.bot.send_message(
    #         update.message.chat_id,
    #         bot_msg,
    #         # To preserve the markdown, we attach entities (bold, italic...)
    #         entities=update.message.entities
    #     )
    await update.message.reply_text(bot_msg)

async def status(update: Update, context: CallbackContext) -> None:
    """
    This function handles /status command
    """
    bot_msg = "Should print status to user"
    # context.bot.send_message(
    #         update.message.chat_id,
    #         bot_msg,
    #         # To preserve the markdown, we attach entities (bold, italic...)
    #         entities=update.message.entities
    #     ) 
    await update.message.reply_text(bot_msg)   

    # n = 10
    # for i in range(n):
    #     time.sleep(2)
    #     bot_msg = f'Current task is: {i}'
    #     context.bot.send_message(
    #         update.message.chat_id, 
    #         bot_msg,
    #         entities=update.message.entities
    #     )


async def freshstart(update: Update, context: CallbackContext) -> None:
    """
    This function handles /freshstart command
    """

    bot_msg = "Here will be routine to start a new project"
    # context.bot.send_message(
    #         update.message.chat_id,
    #         bot_msg,
    #         # To preserve the markdown, we attach entities (bold, italic...)
    #         entities=update.message.entities
    #     )   
    await update.message.reply_text(bot_msg)

async def settings(update: Update, context: CallbackContext) -> None:
    """
    This function handles /settings command
    """
    bot_msg = "Here PM should be able to change some of project settings. If no project started yet, then redirect to freshstart"

    # PPP: Check if asking user is PM: proceed only if it is. If not - inform user.
    # TODO: Add buttons to change project settings, such as:
    # 1. change of PM (see below)
    # PPP: 
    # Take new PM name, check if he's member of chat members, do nothing and inform user if otherwise
    # 
    # message = ''
    # global PM
    # if update.effective_user == PM:
    #     PM = update.effective_user.name
    #     message = 'Project manager now is: ' + newPM
    # else:
    #     message = 'Only project manager is allowed to assign new one'
    # await update.message.reply_text(message)

    # 2. change of project name
    # 3. interval of intermidiate reminders

    await update.message.reply_text(bot_msg)

async def upload(update: Update, context: CallbackContext) -> None:
    '''
    Function to upload new project file
    '''
    # Message to return
    message = ''

    # PPP:
    # Check if user is PM
    uploader = update.message.from_user.username
    if uploader == PM:
        # message = 'Project manager'
        # message = update.message.document.mime_type
        gotfile = await context.bot.get_file(update.message.document)
        # schedule_file = BufferedIOBase
        # await project_file.download_to_memory(schedule_file)
        fp = await gotfile.download_to_drive()
        # message = str(type(fp.suffix))
        match fp.suffix:
            case '.txt':
                message = 'It is a .txt file. Just for example of recognition.'
            case '.gan':
                message = 'It is a GanttProject file format'
            case _:                
                message = 'Bot supports only these project file formats: .gan (GanttProject) and that is all for now.'

    else:
        message = 'Only Project Manager is allowed to upload new schedule'
    # Get file
    # Check extension
    # Case for known file types
    # if known: call such function with this file as argument
    # else inform user about supported file types


    await update.message.reply_text(message)


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
    # application.add_handler(CommandHandler("menu", menu))
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
    # application.add_handler(CommandHandler("upload", upload))  
    # And if changes were made inside the bot, PM could download updated schedule (original format?)
    # dispatcher.add_handler(CommandHandler("download", download))

    # Register handler for inline buttons
    # application.add_handler(CallbackQueryHandler(button_tap))

    # Echo any message that is text and not a command
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Register handler for recieving new project file
    application.add_handler(MessageHandler(filters.Document.ALL, upload))

    # Start the Bot
    application.run_polling()

    # Run the bot until you press Ctrl-C
    # application.idle()


if __name__ == '__main__':
    main()