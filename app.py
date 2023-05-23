# Based on https://gitlab.com/Athamaxy/telegram-bot-tutorial/-/blob/main/TutorialBot.py

import logging
import os
import time
import json
import connectors
import tempfile
import asyncio


from dotenv import load_dotenv
# from io import BufferedIOBase
from telegram import Bot, Update, ForceReply, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, ExtBot, Updater, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, ContextTypes,  filters


# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Store bot screaming status
screaming = False

# Project constants, should be stored separately TODO
# TODO: change according to starter of the bot
PM = 'hagen10'
PROJECTTITLE = ''
PROJECTJSON = "temp.json"

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

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function handles /help command
    """

    bot_description = await context.bot.getMyDescription()
    bot_msg = bot_description.description
    await update.message.reply_text(bot_msg)

    bot_commands = await context.bot.getMyCommands()
    for command in bot_commands:
        bot_msg = f"/{command.command} \t- {command.description}"
        await update.message.reply_text(bot_msg)
    

async def status(update: Update, context: CallbackContext) -> None:
    """
    This function handles /status command
    """
    bot_msg = "Should print status to user"

    await update.message.reply_text(bot_msg)   


async def freshstart(update: Update, context: CallbackContext) -> None:
    """
    This function handles /freshstart command
    """

    bot_msg = "Here will be routine to start a new project"

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
    # Message to return to user
    bot_msg = ''

    # Check if user is PM
    uploader = update.message.from_user.username
    if uploader == PM:
        # Let's keep files got from user in temporary directory
        with tempfile.TemporaryDirectory() as tdp:
            gotfile = await context.bot.get_file(update.message.document)
            fp = await gotfile.download_to_drive(os.path.join(tdp, update.message.document.file_name))
            # if file is known format: call appropriate function with this file as argument
            project = {}
            try:
                match fp.suffix:
                    case '.gan':
                        # Send to connector to receive project in JSON format
                        project = connectors.load_gan(fp)

                    case '.json':
                        project = connectors.load_json(fp)

                # else inform user about supported file types
                    case _:                
                        bot_msg = 'Bot supports only these project file formats: .gan (GanttProject) and that is all for now.'
            except AttributeError as e:
                bot_msg = f'Seems like field for telegram id for team member is absent: {e}'
            except ValueError as e:
                bot_msg = f'Error occurred while processing file: {e}'
            except FileNotFoundError as e:
                bot_msg = f'Seems like the file {e} does not exist'
            except Exception as e:
                bot_msg = f'Unknow error occurred while processing file: {e}'
                logger.info(f'{time.asctime()}\t {type(e)} \t {e.with_traceback}')
            else:
                # Call function to save project in JSON format
                if project:
                    bot_msg = save_json(project)            
            
    else:
        bot_msg = 'Only Project Manager is allowed to upload new schedule'

    await update.message.reply_text(bot_msg)

def save_json(project):
    ''' 
    Saves project in JSON format and returns message about success of operation
    '''
    bot_msg = ''
    with open(PROJECTJSON, 'w') as json_fh:
        try:
            json.dump(project, json_fh)
        except:
            bot_msg = 'Error saving project to json file'    
        else:
            bot_msg = 'Successfully saved project to json file'
    return bot_msg

def main() -> None:

    load_dotenv()
    BOT_TOKEN = os.environ.get("BOT_TOKEN")

    # Create a builder via Application.builder() and then specifies all required arguments via that builder.
    #  Finally, the Application is created by calling builder.build()
    application = Application.builder().token(BOT_TOKEN).build()   

    # Then, we register each handler and the conditions the update must meet to trigger it
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

    # Start the Bot and run it until Ctrl+C pressed
    application.run_polling()


if __name__ == '__main__':
    main()