# Based on https://gitlab.com/Athamaxy/telegram-bot-tutorial/-/blob/main/TutorialBot.py
# Structure:
# Imports
# Constants
# Sincronuous functions
# Async functions
# Settings part (functions for settings functionality)
# Post init
# Main function

import logging
import os
import json
import tempfile
import asyncio
import re
import connectors
import pymongo

from dotenv import load_dotenv
from datetime import datetime, date, time
# from io import BufferedIOBase
from telegram import (
                        Bot, 
                        BotCommand, 
                        Update, 
                        ForceReply, 
                        InlineKeyboardMarkup, 
                        InlineKeyboardButton, 
                        ReplyKeyboardMarkup, 
                        ReplyKeyboardRemove)
from telegram.constants import ParseMode
from telegram.ext import (
                            Application, 
                            ExtBot, 
                            Updater, 
                            CommandHandler, 
                            MessageHandler, 
                            CallbackContext, 
                            CallbackQueryHandler, 
                            ContextTypes,  
                            ConversationHandler,
                            filters)
from urllib.parse import quote_plus
from ptbcontrib.ptb_jobstores import PTBMongoDBJobStore
from helpers import (
    add_user_id, 
    get_assignees,
    get_db, 
    get_job_preset, 
    save_json)
# For testing purposes
from pprint import pprint

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# Project constants, should be stored in DB tied to project and PM TODO

# This setting control whether bot will send status report for PM in private chat 
# or in group chat if /status command executed in group chat
ALLOW_POST_STATUS_TO_GROUP = False 
# Inform actioners of milestones (by default only PM) 
INFORM_ACTIONERS_OF_MILESTONES = False
# Default values for daily reminders
MORNING = "10:00"
ONTHEEVE = "16:00"
FRIDAY = "15:00"

# TODO: change according to starter of the bot
PROJECTTITLE = 'TESTING PROJECT'
KNOWN_USERS = {}
load_dotenv()
PM = os.environ.get("PM")
PROJECTJSON = os.environ.get("PROJECTJSON")

# Link to DB for storing jobs
BOT_NAME = os.environ.get('BOT_NAME')
BOT_PASS = os.environ.get('BOT_PASS')
DB_URI = f"mongodb://{BOT_NAME}:{BOT_PASS}@localhost:27017/admin?retryWrites=true&w=majority"

# TODO DELETE? should work as standalone function
# # link to database
# DB_NAME = os.environ.get("DB_NAME", "database")
# host = '127.0.0.1:27017'
# uri = "mongodb://%s:%s@%s" % (quote_plus(BOT_NAME), quote_plus(BOT_PASS), host)
# try:
#     # client = pymongo.MongoClient(f"mongodb://{BOT_NAME}:{BOT_PASS}@localhost:27017/admin?retryWrites=true&w=majority")
#     client = pymongo.MongoClient(uri)    
#     DB = client[DB_NAME]
# except ConnectionError as e:
#     logger.error(f"There is problem with connecting to db '{DB_NAME}': {e}")   
# except Exception as e:
#     logger.error(f"Error occurred: {e}")
DB = get_db()

# Set list of commands
help_cmd = BotCommand("help","выводит данное описание")
status_cmd = BotCommand("status", "информация о текущем состоянии проекта")
settings_cmd = BotCommand("settings", "настройка параметров бота")
# freshstart_cmd = BotCommand("freshstart", "начало нового проекта")
feedback_cmd = BotCommand("feedback", "отправка сообщения разработчику")
start_cmd = BotCommand("start", "запуск бота")
stop_cmd = BotCommand("stop", "прекращение работы бота")

# Stages of settings menu:
FIRST_LVL, SECOND_LVL, THIRD_LVL, FOURTH_LVL, FIFTH_LVL = range(5)
# Callback data for settings menu
ONE, TWO, THREE, FOUR, FIVE = range(5)


def get_keybord_and_msg(level: int, info: str = None, user_id: int = None):
    '''
    Helper function to provide specific keyboard on different levels of settings menu
    '''

    keyboard = None
    msg = None
    match level:
        case 0:
            # First level menu keyboard
            msg = (f"Current settings for project: ")
            keyboard = [        
                [InlineKeyboardButton(f"Allow status update in group chat: {'On' if ALLOW_POST_STATUS_TO_GROUP == True else 'Off'}", callback_data=str(ONE))],
                [InlineKeyboardButton(f"Users get anounces about milestones {'On' if INFORM_ACTIONERS_OF_MILESTONES == True else 'Off'}", callback_data=str(TWO))],
                [InlineKeyboardButton("Reminders settings", callback_data=str(THREE))],
                [InlineKeyboardButton("Finish settings", callback_data=str(FOUR))],        
            ]
        case 1:
            # TODO: Here I could construct keyboard out of jobs registered for current user
            msg = (f"You can customize reminders here.")
            # Second level menu keyboard
            keyboard = [        
                [InlineKeyboardButton("Reminder on day before", callback_data=str(ONE))],
                [InlineKeyboardButton("Everyday morning reminder", callback_data=str(TWO))],
                [InlineKeyboardButton("Friday reminder of project files update", callback_data=str(THREE))],
                [InlineKeyboardButton("Back", callback_data=str(FOUR))],        
                [InlineKeyboardButton("Finish settings", callback_data=str(FIVE))],        
            ]
        case 2:
             # Message contents depend on a branch of menu, return None if nonsense given
            match info:
                case 'morning_update':                    
                    msg = (f"Daily morning reminder has to be set here.\n"
                            )
                case 'day_before_update':
                    msg = (f"The day before reminder has to be set here. \n"
                            )
                case 'file_update':
                    msg = (f"Reminder for file updates on friday has to be set here. \n"
                            )
                case _:
                    msg = None
            # Third level menu keyboard
            keyboard = [        
                [InlineKeyboardButton("Turn on/off", callback_data=str(ONE))],
                [InlineKeyboardButton("Set time", callback_data=str(TWO))],
                [InlineKeyboardButton("Set days of week", callback_data=str(THREE))],
                [InlineKeyboardButton("Back", callback_data=str(FOUR))],        
                [InlineKeyboardButton("Finish settings", callback_data=str(FIVE))],        
            ]
        case _:
            keyboard = None

    return keyboard, msg


async def day_before_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    This reminder must be send to all team members on the day before of the important dates:
    start of task, deadline
    '''

    if os.path.exists(PROJECTJSON):
        with open(PROJECTJSON, 'r') as fp:
            try:
                project = connectors.load_json(fp)
            except Exception as e:
                bot_msg = f"ERROR ({e}): Unable to load"
                logger.error(f'{e} \t {e.with_traceback}')                  
            else:

                # Loop through actioners to inform them about actual tasks
                for actioner in project['staff']:

                    # Bot can inform only ones with known id
                    # print(actioner)
                    if actioner['tg_id']:
                        for task in project['tasks']:

                            # Process only tasks in which current actioner participate
                            for doer in task['actioners']:
                                # print(doer)
                                if actioner['id'] == doer['actioner_id']:
                                    bot_msg = ""

                                    # Bot will inform user only of tasks with important dates
                                    # Check if task not completed
                                    if task['complete'] < 100:

                                        # If delta_start <0 task not started, otherwise already started
                                        delta_start = date.today() - date.fromisoformat(task['startdate'])

                                        # If delta_end >0 task overdue, if <0 task in progress
                                        delta_end = date.today() - date.fromisoformat(task['enddate'])

                                        # Deal with common task
                                        if task['include']:

                                            # For now focus only on subtasks, that can be actually done
                                            # I'll decide what to do with such tasks after gathering user experience
                                            pass
                                        else:

                                            # Don't inform about milestones, because noone assigned for them
                                            if task['milestone'] == True:    
                                                    pass
                                            else:

                                                # If task starts tomorrow
                                                if delta_start.days == -1:
                                                    bot_msg = f"task {task['id']} '{task['name']}' starts tomorrow."
                                                elif delta_end.days == -1:
                                                    bot_msg = f"Tomorrow is deadline for task {task['id']} '{task['name']}'!" 

                                        # Inform users if there are something to inform
                                        if bot_msg:
                                            await context.bot.send_message(
                                                actioner['tg_id'],
                                                text=bot_msg,
                                                parse_mode=ParseMode.HTML)


# TURNED OFF
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function would be added to the application as a handler for messages coming from the Bot API
    """

    # Print to console
    # user = update.effective_user
    user = update.message.from_user
    # username = update.message.from_user.username
    # firstname = update.message.from_user.first_name
    text = str(update.message.text)
    logger.info(f'{user.id} ({user.username}): {text}')

    # TODO I can use it to gather id from chat members and add them to project
    # global KNOWN_USERS
    # KNOWN_USERS.update({
    #     user.username: user.id
    # })
    # pprint(KNOWN_USERS)
    # print (update.message.chat_id)

    # reply only to personal messages
    if update.message.chat_id == user.id:
        await update.message.reply_text(text)


async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Initiation of feedback dialog with user    
    '''
    bot_msg = "What would you like inform developer about? Bugs, comments and suggestions highly appreciated."
    await update.message.reply_text(bot_msg)
    return FIRST_LVL


async def feedback_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ Gather information user provided and answer user"""
    # TODO Maybe add handling of file or screenshot (PHOTO) recieving from user?
    logger.warning(f'FEEDBACK from {update.message.from_user.username} ({update.message.from_user.id}): {update.message.text}')
    bot_msg = "Feedback sent to developer."
    await update.message.reply_text(bot_msg)
    # TODO definitely should send message to me (hide tg_id in .env)
    return ConversationHandler.END


async def file_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    This function is a reminder for team members that common files should be updated in the end of the week
    '''

    if os.path.exists(PROJECTJSON):
        with open(PROJECTJSON, 'r') as fp:
            try:
                project = connectors.load_json(fp)
            except Exception as e:
                logger.error(f'{e} \t {e.with_traceback}')                  
            else:

                # Loop through actioners to inform them about actual tasks
                bot_msg = "Напоминаю, что сегодня надо освежить файлы по проекту! Чтобы другие участники команды имели актуальную информацию. Спасибо!"
                for actioner in project['staff']:

                    # Bot can inform only ones with known id
                    # print(actioner)
                    if actioner['tg_id']:
                        await context.bot.send_message(
                            actioner['tg_id'],
                            text=bot_msg,
                            parse_mode=ParseMode.HTML)


# async def freshstart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """
#     TODO: This function handles /freshstart command
#     """
#     freshstart_markup = InlineKeyboardMarkup(freshstart_kbd)
#     bot_msg = "Are you really want to start a new project?"
#     await update.message.reply_text(bot_msg, reply_markup=freshstart_markup)


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function handles /help command
    """
    # Get description and send to user
    bot_description = await context.bot.getMyDescription()
    bot_msg = bot_description.description
    await update.message.reply_text(bot_msg)

    bot_commands = await context.bot.getMyCommands()
    # Build message about commands not repeating /help command
    bot_msg = ''
    for command in bot_commands:
        if command.command != 'help':
            bot_msg = f"/{command.command} - {command.description}\n" + bot_msg

    await update.message.reply_text(bot_msg)
 

async def morning_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    This routine will be executed on daily basis to control project(s) schedule
    '''

    # TODO use data to associate project name with job
    # TODO how to make observation of project a standalone function to be called elsewhere?
    # because every reminder function load project from file and looks through it

    if os.path.exists(PROJECTJSON):
        with open(PROJECTJSON, 'r') as fp:
            try:
                project = connectors.load_json(fp)
            except Exception as e:
                bot_msg = f"ERROR ({e}): Unable to load"
                logger.error(f'{e} \t {e.with_traceback}')                  
            else:

                # Loop through actioners to inform them about actual tasks
                for actioner in project['staff']:

                    # Bot can inform only ones with known id
                    # print(actioner)
                    if actioner['tg_id']:
                        for task in project['tasks']:

                            # Process only tasks in which current actioner participate
                            for doer in task['actioners']:
                                # print(doer)
                                if actioner['id'] == doer['actioner_id']:
                                    bot_msg = ""

                                    # Bot will inform user only of tasks with important dates
                                    # Check if task not completed
                                    if task['complete'] < 100:

                                        # If delta_start <0 task not started, otherwise already started
                                        delta_start = date.today() - date.fromisoformat(task['startdate'])

                                        # If delta_end >0 task overdue, if <0 task in progress
                                        delta_end = date.today() - date.fromisoformat(task['enddate'])

                                        # Deal with common task
                                        if task['include']:

                                            # For now focus only on subtasks, that can be actually done
                                            # I'll decide what to do with such tasks after gathering user experience
                                            pass
                                        else:

                                            # Don't inform about milestones, because noone assigned for them
                                            if task['milestone'] == True:    
                                                    pass
                                            else:
                                                if delta_start.days == 0:
                                                    bot_msg = f"task {task['id']} '{task['name']}' started today."
                                                elif delta_start.days > 0  and delta_end.days < 0:
                                                    bot_msg = f"task {task['id']} '{task['name']}' is intermidiate. Due date is {task['enddate']}."
                                                elif delta_end.days == 0:
                                                    bot_msg = f"task {task['id']}  '{task['name']}' must be completed today!"
                                                elif delta_start.days > 0 and delta_end.days > 0:                                       
                                                    bot_msg = f"task {task['id']} '{task['name']}' is overdue! (had to be completed on {task['enddate']})"
                                                else:
                                                    print(f"Future tasks as {task['id']} '{task['name']}' goes here")                            

                                        # Check if there is something to report to user
                                        if bot_msg:
                                            await context.bot.send_message(
                                                actioner['tg_id'],
                                                text=bot_msg,
                                                parse_mode=ParseMode.HTML)

######### START section ########################
async def start(update: Update, context: CallbackContext) -> int:
    '''
    Function to handle start of the bot
    '''

    # TODO PPP: 
    # check connection to DB?
    # inform user what to do with this bot
    # Call function to upload project file
    # Call function to make jobs
    PM = {
        'pm_id': update.effective_user.id,
        'pm_username': update.effective_user.username,
        'pm_firstname': update.effective_user.first_name,
        'account_type': 'free',
        'settings': {
            'INFORM_OF_ALL_PROJECTS': False,         
        },
        'projects': [],
    }
    # Store information about PM in context
    context.user_data['PM'] = PM

    bot_msg = (f"Hello, {update.effective_user.first_name}!\n"
               f"You are starting a new project.\n"
               f"Provide a name for it.\n"
               f"(type 'cancel' if you changed you mind during this process)"
    )
    await update.message.reply_text(bot_msg)
    return FIRST_LVL


async def naming_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ''' Function for recognizing name of the project '''
    
    #TODO: Clean input and add check for malicous input    
    global PROJECTTITLE
    PROJECTTITLE = update.message.text
    project = {
        'title': PROJECTTITLE,
        'active': True,
        'tg_chat_id': '', # TODO store here group chat where project members discuss project
        'settings': {
            # TODO decide after user testing whether these settings should be stored in here or in PM's settings
            'ALLOW_POST_STATUS_TO_GROUP': False,
            'INFORM_ACTIONERS_OF_MILESTONES': False,
            },
        'tasks': [],
        'staff': []
    }
    # Add project data to dictionary in user_data. 
    # One start = one project. But better keep PM and project separated, 
    # because they could be written to DB separately
    context.user_data['project'] = project

    # Check DB for such name for this user, (TODO standalone?)
    print(context.user_data['PM']['pm_id'])
    # if check_db_for_user(context.user_data['PM']['pm_id']):
    db_pm_id = DB.PMs.find_one({"pm_id": context.user_data['PM']['pm_id']})
    print(db_pm_id)
    if db_pm_id:
        prj_id = DB.PMs.find_one({"pm_id": context.user_data['PM']['pm_id'], "projects.title": project['title']})
        pprint(f"Results for looking this project name in DB: {prj_id}")
        if prj_id:
            bot_msg = f"You already started project with name {project['title']}. Try another one."
            await update.message.reply_text(bot_msg)
            return FIRST_LVL
        else:
            # projects_list = DB.PMs.find_one({"pm_id": context.user_data['PM']['pm_id']}, {"projects": 1, "_id": 0})
            # new_projects_list = projects_list.append(project)
            # DB.PMs.update_one({"pm_id": context.user_data['PM']['pm_id']}, {"$set": {"projects": new_projects_list}})
            # TODO above lines will be done on next step
            bot_msg = f"Got it. Now you can upload your project file. Supported formats are: .gan (GanttProject), .json, .xml (MS Project)"
            await update.message.reply_text(bot_msg)
            return SECOND_LVL
    else:
        DB.PMs.insert_one(context.user_data['PM'])
        # bot_msg = f"Record {} added to DB"
        bot_msg = f"Got it. Now you can upload your project file. Supported formats are:\n.gan (GanttProject), .json, .xml (MS Project)"
        await update.message.reply_text(bot_msg)
        return SECOND_LVL

# TODO DELETE
    # try:
    #     # If PM does not present in DB then add him with a project
    #     # Otherwise add this project to list of projects of this PM
    #     # If PM already has such project ask user to provide new name
    #     # TODO: there is no need here to write to DB
    #     #       Just collect data
    #     #       Check if project exist to suggest a new name
    #     #       Но тогда на следующем шаге опять потребуется делать все эти проверки
    #     #       Если РП нет в БД, то можно на следующем шаге всё сразу записать
    #     #       Если есть, и имя проекта новое, то обновленный список проектов можно записать на следующем шаге
        
    # except Exception as e:
    #     logger.error(f"Problems with database: {e}")
    # else:
    #     await update.message.reply_text(bot_msg)
    #     return SECOND_LVL

### DELETE? seems that this standalone function doesn't give any advantages
# def check_db_for_user(pm_id) -> bool:
#     ''' Function to check whether DB has a PM with provided telegram_id '''
#     if DB.PMs.find_one({"pm_id": pm_id}):
#         return True
#     else:
#         return False


async def file_recieved(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ''' Function to proceed uploaded file and saving to DB'''
    # TODO reconsider to make this part as standalone function because it's same as in /upload
    # Call function to recieve file and call converters
    with tempfile.TemporaryDirectory() as tdp:
        gotfile = await context.bot.get_file(update.message.document)
        fp = await gotfile.download_to_drive(os.path.join(tdp, update.message.document.file_name))
        
        # Call function which converts given file to dictionaries
        tasks, staff = file_to_dict(fp)
        if tasks and staff:
            # Remember telegram user id
            staff = add_user_id(update.message.from_user, staff)
            bot_msg = "File parsed successfully"

            # Add tasks and staff to user data dictionary in context
            context.user_data['project']['tasks'] = tasks
            context.user_data['project']['staff'] = staff

            # Save project to DB
            # At this point PM should be present in DB, so try to append project to it's project list
            try:
                projects_list = DB.PMs.find_one({"pm_id": context.user_data['PM']['pm_id']}, {"projects": 1, "_id": 0})
                # print(f"Projects dict returned: {projects_list['projects']}, it has type: {type(projects_list['projects'])}")
                # Check if there are projects
                if projects_list['projects']:
                    # Make other projects not active
                    for item in projects_list['projects']:
                        item['active'] = False
                    new_projects_list = projects_list['projects'].copy()
                else:
                    new_projects_list = []
                new_projects_list.append(context.user_data['project'])
                # pprint(f"What is in context? {context.user_data['project']}")
                # pprint(f"NEW Project list returned: {new_projects_list}, it has type: {type(new_projects_list)}")
                DB.PMs.update_one({"pm_id": context.user_data['PM']['pm_id']}, {"$set": {"projects": new_projects_list}})
            except Exception as e:
                # TODO separate AttributeError(?) (when PM is not present somehow)
                bot_msg = (bot_msg + f"\nSomething went wrong when writing project to DB:\n{e}")
            else:
                # If succeed call function to create Jobs
                project_title = context.user_data['project']['title']
                pprint(f"Project title: {project_title}")
                if schedule_jobs(str(update.effective_user.id), project_title, context):
                    bot_msg = (bot_msg + "\nReminders were created: on the day before event, in the morning of event and reminder for friday file update. "
                                "You can change them or turn off in /settings."
                                "\nProject initialization complete."
                    )
                    # Since new project added successfully and it's active, lets make other projects inactive
                else:
                    bot_msg = (bot_msg + "\nSomething went wrong while scheduling reminders."
                                "\nPlease, contact bot developer to check the logs.")
            finally:
                await update.message.reply_text(bot_msg)
                return ConversationHandler.END                                  
        else:
            bot_msg = (f"Couldn't process given file.\n"
                        f"Supported formats are: .gan (GanttProject), .json, .xml (MS Project)\n"
                        f"Make sure these files contain custom field named 'tg_username', which store usernames of project team members.\n"
                        f"If you would like to see other formats supported feel free to message bot developer via /feedback command.\n"
                        f"Try upload another one."
            )
        await update.message.reply_text(bot_msg)
        return SECOND_LVL


async def start_ended(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ''' Finish function of start routine'''
    bot_msg = "This is fallback function. How we get here? When something unexpected happens in conversation. Text message instead of file upload, for example"
    logger.warning(f"User: {update.message.from_user.username} ({update.message.from_user.id}) wrote: {update.message.text}")
    await update.message.reply_text(bot_msg)
    return ConversationHandler.END

### HELPERS:
def file_to_dict(fp):
    ''' Get file, return dictionaries '''
    tasks = []
    staff = []

    # If file is known format: call appropriate function with this file as argument and expect project dictionary on return
    try:
        match fp.suffix:
            case '.gan':
                tasks, staff = connectors.load_gan(fp)

            case '.json':
                tasks, staff = connectors.load_json(fp)

            case '.xml':
                tasks, staff = connectors.load_xml(fp)

        # else log what was tried to be loaded
            case _:
                logger.warning(f"Someone tried to load '{fp.suffix}' file.")                
    except Exception as e:
        logger.error(f'{e} \t {e.with_traceback}')
        return None, None    
    else:
        return tasks, staff


def schedule_jobs(user_id: str, project_title: str, context: ContextTypes.DEFAULT_TYPE):
    ''' 
    Schedule jobs for main reminders. Return false if not succeded
    TODO v2: When custom reminders functionality will be added this function must be revised
    '''    
    
    morning_update_job, day_before_update_job, file_update_job = None, None, None

    # TODO create jobs in mongo in apsheduler collection

    job_id = str(user_id) + '_' + project_title + '_' + 'morning_update'
    print(job_id)
    preset = get_job_preset(job_id, context)
    print(preset)
    if not preset:

        # Use default values from constants
        try:
            hour, minute = map(int, MORNING.split(":"))                    
            time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
        except ValueError as e:
            logger.error(f'Error while parsing time: {e} \t {e.with_traceback}')

        # Set job schedule 
        else:
            
            ''' To persistence to work job must have explicit ID and 'replace_existing' must be True
            or a new copy of the job will be created every time application restarts! '''
            job_kwargs = {'id': job_id, 'replace_existing': True}
            morning_update_job = context.job_queue.run_daily(morning_update, user_id=user_id, time=time2check, data=project_title, job_kwargs=job_kwargs)
            
            # and enable it.
            morning_update_job.enabled = True 
            print(f"Next time: {morning_update_job.next_t}, is it on? {morning_update_job.enabled}")      
            
    # 2nd - daily on the eve of task reminder
    job_id = str(user_id) + '_' + project_title + '_' + 'day_before_update'
    print(job_id)
    preset = get_job_preset(job_id, context)
    if not preset:                    
        try:
            hour, minute = map(int, ONTHEEVE.split(":"))                    
            time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
        except ValueError as e:
            logger.error(f'Error while parsing time: {e} \t {e.with_traceback}')
        
        # Add job to queue and enable it
        else:                            
            job_kwargs = {'id': job_id, 'replace_existing': True}
            day_before_update_job = context.job_queue.run_daily(day_before_update, user_id=user_id, time=time2check, data=project_title, job_kwargs=job_kwargs)
            day_before_update_job.enabled = True
            # print(f"Next time: {day_before_update_job.next_t}, is it on? {day_before_update_job.enabled}")   

    # Register friday reminder
    job_id = str(user_id) + '_' + project_title + '_' + 'file_update'
    preset = get_job_preset(job_id, context)
    if not preset:   
        try:
            hour, minute = map(int, FRIDAY.split(":"))                    
            time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
        except ValueError as e:
            logger.error(f'Error while parsing time: {e} \t {e.with_traceback}')
        
        # Add job to queue and enable it
        else:
            job_kwargs = {'id': job_id, 'replace_existing': True}
            file_update_job = context.job_queue.run_daily(file_update, user_id=user_id, time=time2check, days=(5,), data=project_title, job_kwargs=job_kwargs)
            file_update_job.enabled = True
            # print(f"Next time: {file_update_job.next_t}, is it on? {file_update_job.enabled}") 

    print("On the exit of job creation function we have:")        
    pprint(morning_update_job)
    pprint(day_before_update_job)
    pprint(file_update_job)

    if morning_update_job and day_before_update_job and file_update_job:
        return True
    else:
        return False
######### END OF START SECTION ###########


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function handles /status command
    """
    # Dummy message 
    bot_msg = "Should print status to user"

    # PPP
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    # First look up DB for PM via id
    result = DB.PMs.find_one({"pm_id": user_id})
    if not result:
        # Then by his username
        result = DB.PMs.find_one({"pm_username": user_name})
    if result:
        # Go on and update PM telegram id
        # TODO - old function isn't useful here
        # TODO also update username if changed 
        # Then read settings 
        INFORM_OF_ALL_PROJECTS = result['settings']['INFORM_OF_ALL_PROJECTS']
        for project in result['projects']:
            text_accumulator = ''
            user_ids = []
            print(f"We are in this project: {project}") # What if None?
            ALLOW_POST_STATUS_TO_GROUP = project['settings']['ALLOW_POST_STATUS_TO_GROUP']
            INFORM_ACTIONERS_OF_MILESTONES = project['settings']['INFORM_ACTIONERS_OF_MILESTONES']
            # Proceed only if this project is active or PM want to be informed about all projects
            if INFORM_OF_ALL_PROJECTS or project['active']:
                bot_msg = f"Status of events for project {project['title']}:"
                for task in project['tasks']:
                    # Bot will inform user only of tasks with important dates

                    # Check if task not completed
                    if task['complete'] < 100:

                        # If delta_start <0 task not started, otherwise already started
                        delta_start = date.today() - date.fromisoformat(task['startdate'])

                        # If delta_end >0 task overdue, if <0 task in progress
                        delta_end = date.today() - date.fromisoformat(task['enddate'])
                        
                        # Deal with common task
                        if task['include']:

                            # For now focus only on subtasks, that can be actually done
                            # I'll decide what to do with such tasks after gathering user experience
                            pass
                        else:

                            # Inform about milestone
                            if task['milestone'] == True:
                                if delta_end.days < 0:

                                    # If milestone in future inform user
                                    text_accumulator = text_accumulator + f"\nMilestone '{task['name']}' is near ({task['enddate']})!"
                                else:
                                    # if milestone in past do nothing
                                    pass
                            else:
                                # TODO should refactor this
                                actioners = project['staff']
                                if delta_start.days == 0:
                                    try:
                                        people, user_ids = get_assignees(task, actioners)
                                    except Exception as e:
                                        text_accumulator = text_accumulator + f"\nError occured while processing assigned actioners to task {task['id']} '{task['name']}' starting today"
                                        logger.error(f'{e} \t {e.with_traceback}')
                                    else:
                                        text_accumulator = text_accumulator + f"\nTask {task['id']} '{task['name']}' starts today. Assigned to: {people}"
                                elif delta_start.days > 0  and delta_end.days < 0:
                                    try:
                                        people, user_ids = get_assignees(task, actioners)
                                    except Exception as e:
                                        text_accumulator = text_accumulator + f"\nError occured while processing assigned actioners to task {task['id']} {task['name']}"
                                        logger.error(f'{e} \t {e.with_traceback}')
                                    else:
                                        text_accumulator = text_accumulator + f"\nTask {task['id']} '{task['name']}' is intermidiate. Due date is {task['enddate']}. Assigned to: {people}"
                                elif delta_end.days == 0:
                                    try:
                                        people, user_ids = get_assignees(task, actioners)
                                    except Exception as e:
                                        text_accumulator = text_accumulator + f"\nError occured while processing assigned actioners to task {task['id']} {task['name']}"
                                        logger.error(f'{e} \t {e.with_traceback}')
                                    else:                                        
                                        text_accumulator = text_accumulator + f"\nTask {task['id']}  '{task['name']}' must be completed today! Assigned to: {people}"
                                elif delta_start.days > 0 and delta_end.days > 0:
                                    try:
                                        people, user_ids = get_assignees(task, actioners)
                                    except Exception as e:
                                        text_accumulator = text_accumulator + f"\nError occured while processing assigned actioners to task {task['id']} {task['name']}"
                                        logger.error(f'{e} \t {e.with_traceback}')
                                    else:                                         
                                        text_accumulator = text_accumulator + f"\nTask {task['id']} '{task['name']}' is overdue! (had to be completed on {task['enddate']}). Assigned to: {people}"
                                else:
                                    logger.info(f"Loop through future task '{task['id']}' '{task['name']}'")

            # Check if there is something to report to user
            if not text_accumulator:
                bot_msg = f"{bot_msg}\nSeems like there are no events worth mention"
            
            bot_msg = f"{bot_msg}\n{text_accumulator}"

            # Send reply to PM in group chat if allowed
            if ALLOW_POST_STATUS_TO_GROUP == True:
                await update.message.reply_text(bot_msg)
            else:

                # Or in private chat
                await context.bot.send_message(user_id, bot_msg)

            # And send msg to actioner (if it is not a PM)
            # user_ids should be empty if no events worth mention
            for id in user_ids:
                # print(id)
                if id != user_id: 
                    await context.bot.send_message(
                        id,
                        text=bot_msg,
                        parse_mode=ParseMode.HTML)

    else:
        # If current user not found in project managers 
        # then just search him in all records and inform about events
        # if nothing found - Suggest him to start a project
        pass
    # Пишем название проекта и далее ключевые события
    # TODO(тут можно добавить настройку: уведомлять о всех проектах или только об активном)
    # если юзера нет среди РП, то:
        # отбираем записи, где юзер - исполнитель 
            # TODO(возможно потребуется пересмотреть схему: записи из staff перенести непосредственно в исполнителей таска
            # !!! Предварительно надо выяснить как будет вести себя updateMany при обновлении tg_id для заданного юзернейма
                # если возможно обновить все таски с её помощью, то ок
                # если нет, то справочник staff придется оставить (или сделать его отдельной коллекцией?)
        # для таких записей: выводим название проекта, имя РП и далее события, относящиеся к юзеру


    # Because /status command could be called anytime, we can't pass project stored in memory to it
    # so it will be loaded from disk
    # if os.path.exists(PROJECTJSON):
    #     with open(PROJECTJSON, 'r') as fp:
    #         try:
    #             project = connectors.load_json(fp)
    #         except Exception as e:
    #             bot_msg = f"ERROR ({e}): Unable to load"
    #             logger.info(f'{e} \t {e.with_traceback}')                  
    #         else:
    #             # print(f"For testing purposes list jobs: {context.job_queue.jobs()}")
    #             # for job in context.job_queue.jobs():
    #                 # print(f"Job name: {job.name}, enabled: {job.enabled}")
    #                 # pprint(f"has parameters: {job.job.trigger.fields}")

    #             # Main thread
    #             user = update.message.from_user
    #             username = user.username

    #             # Check if user in project team, update id if not present
    #             project = add_user_id(user, project)

    #             # Update project file
    #             try:
    #                 save_json(project, PROJECTJSON)
    #             except FileNotFoundError as e:
    #                 logger.error(f'{e} \t {e.with_traceback}')
    #                 # TODO better inform PM that there are problems with writing project
    #             except Exception as e:
    #                 logger.error(f'{e} \t {e.with_traceback}')

    #             # Check Who calls? If PM then proceed all tasks
    #             if username == PM:
    #                 for task in project['tasks']:
    #                     # Bot will inform user only of tasks with important dates
    #                     bot_msg = ""

    #                     # Check if task not completed
    #                     if task['complete'] < 100:

    #                         # If delta_start <0 task not started, otherwise already started
    #                         delta_start = date.today() - date.fromisoformat(task['startdate'])

    #                         # If delta_end >0 task overdue, if <0 task in progress
    #                         delta_end = date.today() - date.fromisoformat(task['enddate'])
    #                         user_ids = []

    #                         # Deal with common task
    #                         if task['include']:

    #                             # For now focus only on subtasks, that can be actually done
    #                             # I'll decide what to do with such tasks after gathering user experience
    #                             pass
    #                         else:

    #                             # Inform about milestone
    #                             if task['milestone'] == True:
    #                                 if delta_end.days < 0:

    #                                     # If milestone in future inform user
    #                                     bot_msg = f"Milestone '{task['name']}' is near ({task['enddate']})!"
    #                                 else:
    #                                     # if milestone in past do nothing
    #                                     pass
    #                             else:
    #                                 actioners = project['staff']
    #                                 if delta_start.days == 0:
    #                                     try:
    #                                         people, user_ids = get_assignees(task, actioners)
    #                                     except Exception as e:
    #                                         bot_msg = "Error occured while processing assigned actioners to task task['id']} '{task['name']}' starting today"
    #                                         logger.error(f'{e} \t {e.with_traceback}')
    #                                     else:
    #                                         bot_msg = f"task {task['id']} '{task['name']}' starts today. Assigned to: {people}"
    #                                 elif delta_start.days > 0  and delta_end.days < 0:
    #                                     try:
    #                                         people, user_ids = get_assignees(task, actioners)
    #                                     except Exception as e:
    #                                         bot_msg = f"Error occured while processing assigned actioners to task {task['id']} {task['name']}"
    #                                         logger.error(f'{e} \t {e.with_traceback}')
    #                                     else:
    #                                         bot_msg = f"task {task['id']} '{task['name']}' is intermidiate. Due date is {task['enddate']}. Assigned to: {people}"
    #                                 elif delta_end.days == 0:
    #                                     try:
    #                                         people, user_ids = get_assignees(task, actioners)
    #                                     except Exception as e:
    #                                         bot_msg = f"Error occured while processing assigned actioners to task {task['id']} {task['name']}"
    #                                         logger.error(f'{e} \t {e.with_traceback}')
    #                                     else:                                        
    #                                         bot_msg = f"task {task['id']}  '{task['name']}' must be completed today! Assigned to: {people}"
    #                                 elif delta_start.days > 0 and delta_end.days > 0:
    #                                     try:
    #                                         people, user_ids = get_assignees(task, actioners)
    #                                     except Exception as e:
    #                                         bot_msg = f"Error occured while processing assigned actioners to task {task['id']} {task['name']}"
    #                                         logger.error(f'{e} \t {e.with_traceback}')
    #                                     else:                                         
    #                                         bot_msg = f"task {task['id']} '{task['name']}' is overdue! (had to be completed on {task['enddate']}). Assigned to: {people}"
    #                                 else:
    #                                     logger.info(f"Loop through future task '{task['id']}' '{task['name']}'")

    #                         # Check if there is something to report to user
    #                         if bot_msg:

    #                             # Send reply to PM in group chat if allowed
    #                             if ALLOW_POST_STATUS_TO_GROUP == True:
    #                                 await update.message.reply_text(bot_msg)
    #                             else:

    #                                 # Or in private chat
    #                                 await user.send_message(bot_msg)

    #                             # And send msg to actioner (if it is not a PM)
    #                             for id in user_ids:
    #                                 # print(id)
    #                                 if id != user.id: 
    #                                     await context.bot.send_message(
    #                                         id,
    #                                         text=bot_msg,
    #                                         parse_mode=ParseMode.HTML)

    #             # if not - then only tasks for this member
    #             else:
    #                 user_id = ''
    #                 bot_msg = ''
    #                 for actioner in project['staff']:
    #                     if user.username == actioner['tg_username']:
    #                         user_id = actioner['id']
    #                 # print(user_id)

    #                 # Proceed if user found in team members
    #                 if user_id:
    #                     for task in project['tasks']:
    #                         for doer in task['actioners']:

    #                             # Check time constraints if user assigned to this task
    #                             if user_id == doer['actioner_id']:

    #                                 # Check if task not completed
    #                                 if task['complete'] < 100:

    #                                     # If delta_start <0 task not started, otherwise already started
    #                                     delta_start = date.today() - date.fromisoformat(task['startdate'])

    #                                     # If delta_end >0 task overdue, if <0 task in progress
    #                                     delta_end = date.today() - date.fromisoformat(task['enddate'])

    #                                     # Deal with common task
    #                                     if task['include']:

    #                                         # For now focus only on subtasks, that can be actually done
    #                                         # I'll decide what to do with such tasks after gathering user experience
    #                                         pass
    #                                     else:

    #                                         # Inform about milestone
    #                                         if task['milestone'] == True:
    #                                             if delta_end.days < 0:

    #                                                 # If milestone in future inform user
    #                                                 bot_msg = f"Milestone '{task['name']}' is near ({task['enddate']})!"
    #                                             else:

    #                                                 # if milestone in past do nothing
    #                                                 pass
    #                                         else:
    #                                             if delta_start.days == 0:
    #                                                 bot_msg = f"task {task['id']} '{task['name']}' started today."
    #                                             elif delta_start.days > 0  and delta_end.days < 0:
    #                                                 bot_msg = f"task {task['id']} '{task['name']}' is intermidiate. Due date is {task['enddate']}"
    #                                             elif delta_end.days == 0:
    #                                                 bot_msg = f"task {task['id']}  '{task['name']}' must be completed today!"
    #                                             elif delta_start.days > 0 and delta_end.days > 0:
    #                                                 bot_msg = f"task {task['id']} '{task['name']}' is overdue! (had to be completed on {task['enddate']})."
    #                                             else:
    #                                                 logger.info(f"loop through future task '{task['id']}' '{task['name']}'")
    #                     if not bot_msg:
    #                         bot_msg = f"Seems like there are no critical dates for you now, {user.first_name}."

    #                     # Send reply to user in group chat if allowed
    #                     if ALLOW_POST_STATUS_TO_GROUP == True:
    #                         await update.message.reply_text(bot_msg)
    #                     else:

    #                         # Or in private chat
    #                         await user.send_message(bot_msg)
                        
    #                 else:
    #                     bot_msg = f"{user.username} is not participate in schedule provided."
    #                     # TODO This case should be certanly send to PM. For time being just keep it this way
    #                     await update.message.reply_text(bot_msg)
    #                 # print(f"username: {user.username}, id: {user.id}")                
                  
    # else:
    #     bot_msg = f"Project file does not exist, try to load first"
    #     # TODO consider send directly to user asked
    #     await update.message.reply_text(bot_msg)  


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Function to stop the bot.
    Should make bot forget about the user, 
    and stop all jobs associated with the user
    '''

    # Find all jobs for current user associated with current project and remove them
    job_id_mask = str(update.effective_user.id) + '_' + PROJECTTITLE
    current_jobs = context.job_queue.scheduler.get_jobs()   
    if not current_jobs:
        pass
    else:
        for job in current_jobs:
            if job_id_mask in job.id:
                job.remove()


async def upload(update: Update, context: CallbackContext) -> None:
    '''
    Function to upload new project file
    '''

    # Message to return to user
    bot_msg = ''

    # Check if user is PM
    uploader = update.message.from_user.username
    if uploader == PM:
        # Let's keep files got from user in temporary directory TODO what's happenning with them there?
        with tempfile.TemporaryDirectory() as tdp:
            gotfile = await context.bot.get_file(update.message.document)
            fp = await gotfile.download_to_drive(os.path.join(tdp, update.message.document.file_name))
            
            # Call function which converts given file to dictionaries
            tasks, staff = file_to_dict(fp)
            if tasks and staff:
                # Remember telegram user id
                staff = add_user_id(update.message.from_user, staff)

                # Call function to save project in JSON format and log exception
                # TODO delete. this is temporariry until I make DB work
                project = {
                    'tasks': tasks,
                    'staff': staff
                }
                try:
                    save_json(project, PROJECTJSON)
                except FileNotFoundError as e:
                    logger.error(f'{e} \t {e.with_traceback}')
                    # TODO better inform PM that there are problems with writing project
                    bot_msg = "Seems like path to save project does not exist"
                except Exception as e:
                    logger.error(f'{e} \t {e.with_traceback}')
                    bot_msg = "Error saving project"
                else:
                    bot_msg = "Project file saved successfully"
                    
                    # Call function to create jobs:
                    project_title = context.user_data['project']['title']
                    if schedule_jobs(str(update.effective_user.id), project_title, context):
                        bot_msg = (bot_msg + "\nReminders were created: on the day before event, in the morning of event and reminder for friday file update."
                                    "You can change them or turn off in /setttings"
                        )
                    else:
                        bot_msg = (bot_msg + "\nSomething went wrong while scheduling reminders."
                                    "\nPlease, contact bot developer to check the logs.")
            else:
                bot_msg = (f"Couldn't process given file.\n"
                           f"Supported formats are: .gan (GanttProject), .json, .xml (MS Project)"
                           f"Make sure these files contain custom field named 'tg_username', which store usernames of project team members."
                           f"If you would like to see other formats supported feel free to message bot developer via /feedback command."
                )
        
    else:
        bot_msg = 'Only Project Manager is allowed to upload new schedule'
    await update.message.reply_text(bot_msg)


### This part contains functions which make settings menu functionality #########################################################################

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    This function handles /settings command
    """

    # Every user could be PM, but project-PM pair is unique
    # TODO: Add buttons to change project settings, such as:
    # 1. change of PM (see below) (Need to remake Jobs (because of ID))
    # PPP: 
    # Take new PM name, check if he's member of chat members, otherwise do nothing and inform user 
    # 
    # message = ''
    # global PM
    # if update.effective_user == PM:
    #     PM = update.effective_user.name
    #     message = 'Project manager now is: ' + newPM
    # else:
    #     message = 'Only project manager is allowed to assign new one'
    # await update.message.reply_text(message)

    # 2. change of project name (Needs jobs remake because of job ID)
    # + Allow status update in group chat
    # 4. interval of intermidiate reminders
    # For this purpose I will need ConversationHandler
    # + Time of daily update of starting and deadline tasks, and days too

    keyboard, bot_msg = get_keybord_and_msg(FIRST_LVL)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
    else:
        # Let's control which level of settings we are at any given moment
        context.user_data['level'] = FIRST_LVL
        reply_markup = InlineKeyboardMarkup(keyboard)
        # print(update.message)
        await update.message.reply_text(bot_msg, reply_markup=reply_markup)
    return FIRST_LVL


async def finish_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Endpoint of settings conversation
    '''
    query = update.callback_query
    # print(f"Finish function, query.data = {query.data}")
    # print(f"Current level is: {context.user_data['level']}")
    await query.answer()
    await query.edit_message_text(text="Settings done. You can do something else now.")
    return ConversationHandler.END


async def allow_status_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Switch for menu option 'Allow status update in group chat'"""
    query = update.callback_query
    # print(f"Allow status to group function, query.data = {query.data}")
    # print(f"Current level is: {context.user_data['level']}")
    await query.answer()

    # Switch parameter
    global ALLOW_POST_STATUS_TO_GROUP
    ALLOW_POST_STATUS_TO_GROUP = False if ALLOW_POST_STATUS_TO_GROUP else True

    # Call function which create keyboard and generate message to send to user. End conversation if that was unsuccessful.
    keyboard, bot_msg = get_keybord_and_msg(FIRST_LVL)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
    return FIRST_LVL


async def milestones_anounce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Switch for menu option 'Users get anounces about milestones'"""
    query = update.callback_query
    # print(f"Milestones function, query.data = {query.data}")
    # print(f"Current level is: {context.user_data['level']}")
    await query.answer()

    # Switch parameter
    global INFORM_ACTIONERS_OF_MILESTONES
    INFORM_ACTIONERS_OF_MILESTONES = False if INFORM_ACTIONERS_OF_MILESTONES else True

    # Call function which create keyboard and generate message to send to user. End conversation if that was unsuccessful.
    keyboard, bot_msg = get_keybord_and_msg(FIRST_LVL)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
    return FIRST_LVL


async def reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menu option 'Reminders settings'"""
    
    # TODO: using future unified function for reminders, 
    # this menu level could provide as many menu items as jobs for current user
    
    query = update.callback_query
    # print(f"reminders function, query.data = {query.data}")
    await query.answer()
    context.user_data['level'] = SECOND_LVL

    # Call function which create keyboard and generate message to send to user. End conversation if that was unsuccessful.
    keyboard, bot_msg = get_keybord_and_msg(SECOND_LVL)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return SECOND_LVL


async def settings_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menu option 'Back'. Handles returning to previous menu level"""

    # print(f"Current level is: {context.user_data['level']}")
    query = update.callback_query
    # print(f"Back function, query.data = {query.data}")
    await query.answer()
    bot_msg = "Back from back function. Should add 'bot_msg' to helper function too. "

    # We can return back only if we are not on 1st level
    if context.user_data['level'] > 0:
        context.user_data['level'] = context.user_data['level'] - 1  

    # Make keyboard appropriate to a level we are returning to
    keyboard, bot_msg = get_keybord_and_msg(context.user_data['level'])

    # Call function which create keyboard and generate message to send to user. End conversation if that was unsuccessful.
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:    
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        # print(f"Hit 'back' and now level is: {context.user_data['level']}")
        return context.user_data['level']


async def day_before_update_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menu option 'Reminder on day before'"""
    
    # !!!TODO I can make unified function from this!!!
    # just to know what menu item pressed  - what query data sent
    # This way I could use such function as constructor for any future reminders
    # User could create a reminder and provide text of it himself, 
    # which could be stored in user_data
    
    query = update.callback_query
    # print(f"day before reminder function, query.data = {query.data}")
    await query.answer()
    context.user_data['level'] = THIRD_LVL

    # Remember name of JOB this menu item coresponds to.
    context.user_data['last_position'] = 'day_before_update'
    
    # Call function which create keyboard and generate message to send to user. 
    # Call function which get current preset of reminder, to inform user.
    # End conversation if that was unsuccessful. 
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, context.user_data['last_position'])
    job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + str(context.user_data['last_position'])
    preset = get_job_preset(job_id, context)
    
    # preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await  query.edit_message_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return THIRD_LVL
    

async def morning_update_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menu option 'Everyday morning reminder'"""

    # !!!TODO I can make unified function from this!!! see day_before_update_item
    
    query = update.callback_query
    # print(f"morning reminder function, query.data = {query.data}")
    await query.answer()
    context.user_data['level'] = THIRD_LVL

    # Remember name of JOB this menu item coresponds to.
    context.user_data['last_position'] = 'morning_update'

    # Call function which create keyboard and generate message to send to user. 
    # Call function which get current preset of reminder, to inform user.
    # End conversation if that was unsuccessful. 
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, context.user_data['last_position'])
    job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + str(context.user_data['last_position'])
    preset = get_job_preset(job_id, context)
    # preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return THIRD_LVL


async def file_update_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ Menu option 'Friday reminder of project files update'"""
    
    # !!!TODO I can make unified function from this!!! see day_before_update_item

    query = update.callback_query
    # print(f"friday reminder function, query.data = {query.data}")
    await query.answer()
    context.user_data['level'] = THIRD_LVL

    # Remember what job we are modifying right now
    context.user_data['last_position'] = 'file_update'

    # Call function which create keyboard and generate message to send to user. 
    # Call function which get current preset of reminder, to inform user.
    # End conversation if that was unsuccessful. 
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, context.user_data['last_position'])
    job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + str(context.user_data['last_position'])
    preset = get_job_preset(job_id, context)
    # preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return THIRD_LVL


async def reminder_switcher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Handles menu item for turning on/off choosen reminder
    '''

    query = update.callback_query
    # print(f"Reminder switcher function, query.data = {query.data}")
    await query.answer()

    # Recall reminder we are working with
    reminder = context.user_data['last_position']
    # print(f"Reminder in reminder switcher: {reminder}")

    # Find a job by id and pause it if it's enabled or resume if it's paused
    job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + str(context.user_data['last_position'])
    job = context.job_queue.scheduler.get_job(job_id)
    if job.next_run_time:
        job = job.pause()
    else:
        job = job.resume()
    
    # Return previous menu:
    # Call function which create keyboard and generate message to send to user. 
    # Call function which get current preset of reminder, to inform user.
    # End conversation if that was unsuccessful. 
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, reminder)
    preset = get_job_preset(job_id, context)
    # preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
    return THIRD_LVL


async def reminder_time_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menu option 'Set time' (for reminders) """

    query = update.callback_query
    # print(f"Change time pressed, query.data = {query.data}")
    await query.answer()

    # Recall reminder we are working with
    reminder = context.user_data['last_position']

    # Call function to get current preset for reminder
    job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + str(context.user_data['last_position'])
    preset = get_job_preset(job_id, context)
    # preset = get_job_preset(reminder, update.effective_user.id, PROJECTTITLE, context)

    # If reminder not set return menu with reminder settings
    if not preset:
        text = (f"Seems that reminder doesn't set")

        # Call function which create keyboard and generate message to send to user. End conversation if that was unsuccessful.
        keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, reminder)
        if keyboard == None or bot_msg == None:
            bot_msg = f"{text}\nSome error happened. Unable to show a menu."
            await query.edit_message_text(bot_msg)
            return ConversationHandler.END
        else:
            reply_markup = InlineKeyboardMarkup(keyboard)  
            bot_msg = f"{text}\n{bot_msg}"  
            await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return THIRD_LVL
    
    # If reminder set send message to user with current preset and example of input expected from him
    else:
        bot_msg = (f"Current preset for reminder:\n"
                    f"{preset} \n"
                    f"Enter new time in format: 12:30"
                    )
        await query.edit_message_text(bot_msg)

        # Tell conversationHandler to treat answer in a State 4 function
        return FOURTH_LVL


async def reminder_days_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ Menu option 'Set days of week'"""    

    query = update.callback_query
    # print(f"Change days pressed, query.data = {query.data}")
    await query.answer()

    # Recall reminder we are working with
    reminder = context.user_data['last_position']

    # Call function to get current preset for reminder
    # preset = get_job_preset(reminder, update.effective_user.id, PROJECTTITLE, context)
    job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + reminder
    preset = get_job_preset(job_id, context)

    # If reminder not set return menu with reminder settings
    if not preset:
        text = (f"Seems that reminder doesn't set")

        # Call function which create keyboard and generate message to send to user. End conversation if that was unsuccessful.
        keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, reminder)
        if keyboard == None or bot_msg == None:
            bot_msg = f"{text}\nSome error happened. Unable to show a menu."
            await query.edit_message_text(bot_msg)
            return ConversationHandler.END
        else:
            reply_markup = InlineKeyboardMarkup(keyboard)  
            bot_msg = f"{text}\n{bot_msg}"  
            await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return THIRD_LVL
    
    # If reminder set send message to user with current preset and example of input expected from him
    else:
        bot_msg = (f"Current preset for reminder:\n"
                    f"{preset} \n"
                    f"Write days of week when reminder should work in this format: \n"
                    f"monday, wednesday, friday \n"
                    f"or\n"
                    f"mon,wed,fri"
                    )
        await query.edit_message_text(bot_msg)

        # Tell conversationHandler to treat answer in a State 5 function
        return FIFTH_LVL


async def reminder_time_setter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ Handles new time provided by user"""

    reminder = context.user_data['last_position']
    # print(f"User answer got, query.data = {query.data}")
    bot_msg = (f"Unable to reschedule the reminder")

    # Try to convert user provided input (time) to hours and minutes
    try:
        hour, minute = map(int, update.message.text.split(":"))                    
    except ValueError as e:

        # Prepare message if not succeded
        bot_msg = "Did not recognize time. Please use 24h format: 15:05"
    else:
        # Find a job by id for further rescheduling
        job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + reminder
        job = context.job_queue.scheduler.get_job(job_id)
        # Get timezone attribute from current job
        tz = job.trigger.timezone

        # Get list of days of week by index of this attribute in list of fields
        day_of_week = job.trigger.fields[job.trigger.FIELD_NAMES.index('day_of_week')]

        # Reschedule the job
        try:
            job.reschedule(trigger='cron', hour=hour, minute=minute, day_of_week=day_of_week, timezone=tz)
        except Exception as e:
            bot_msg = (f"Unable to reschedule the reminder")
            logger.info(f'{e} \t {e.with_traceback}')
        bot_msg = (f"Time updated. Next time: "
                    f"{job.next_run_time}"
                    )       

    # Inform the user how reschedule went
    await update.message.reply_text(bot_msg)

    # Provide keyboard of level 3 menu 
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, reminder)

    # And get current (updated) preset
    job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + reminder
    preset = get_job_preset(job_id, context)
    # preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await update.message.reply_text(bot_msg, reply_markup=reply_markup)

    # Tell conversation handler to process query from this keyboard as STATE3
    return THIRD_LVL    


async def reminder_days_setter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles new days of week provided by user for reminder"""

    reminder = context.user_data['last_position']
    bot_msg = (f"Unable to reschedule the reminder")
    new_days = []
    # days_of_week = ['mon','tue','wed','thu','fri','sat','sun']

    # Store user input to list, clean from whitespaces, convert to lower case
    if update.message.text:
        user_input = update.message.text.split(',')
        # TODO: better use variables for names of days for later translation
        for day in user_input:
            day = day.strip().lower()
            if day == 'monday' or day == 'mon' or day == 'понедельник' or day == 'пн':

                # Do not add dubles
                if not 'mon' in new_days:
                    new_days.append('mon')
            if day == 'tuesday' or day == 'tue' or day == 'вторник' or day == 'вт':
                if not 'tue' in new_days:               
                    new_days.append('tue')
            if day == 'wednesday' or day == 'wed' or day == 'среда' or day == 'ср':
                if not 'wed' in new_days:
                    new_days.append('wed')  
            if day == 'thursday' or day == 'thu' or day == 'четверг' or day == 'чт':
                if not 'thu' in new_days:
                    new_days.append('thu')
            if day == 'friday' or day == 'fri' or day == 'пятница' or day == 'пт':
                if not 'fri' in new_days:
                    new_days.append('fri')
            if day == 'saturday' or day == 'sat' or day == 'суббота' or day == 'сб':
                if not 'sat' in new_days:
                    new_days.append('sat')
            if day == 'sunday' or day == 'sun' or day == 'воскресенье' or day == 'вс':
                if not 'sun' in new_days:
                    new_days.append('sun') 
        if new_days:

            # Find job by id to reschedule
            job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + reminder
            job = context.job_queue.scheduler.get_job(job_id)
            # Get current parameters of job
            tz = job.trigger.timezone
            hour = job.trigger.fields[job.trigger.FIELD_NAMES.index('hour')]
            minute = job.trigger.fields[job.trigger.FIELD_NAMES.index('minute')]  

            # Reschedule the job
            try:
                job.reschedule(trigger='cron', hour=hour, minute=minute, day_of_week=','.join(new_days), timezone=tz)
            except Exception as e:
                bot_msg = (f"Unable to reschedule the reminder")
                logger.error(f'{e} \t {e.with_traceback}')
            bot_msg = (f"Time updated. Next time: \n"
                        f"{job.next_run_time}"
                        ) 
        else:
            bot_msg = (f"No correct names for days of week found in you message.\n")                       
    else:
        bot_msg = (f"Sorry, can't hear you: got empty message")

    # Inform the user how reschedule went
    await update.message.reply_text(bot_msg)

    # Provide keyboard of level 3 menu 
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, reminder)
    # And get current preset (updated) of the reminder to show to user
    job_id = str(update.effective_user.id) + '_' + PROJECTTITLE + '_' + reminder
    preset = get_job_preset(job_id, context)
    # preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await update.message.reply_text(bot_msg, reply_markup=reply_markup)

    # Tell conversation handler to process query from this keyboard as STATE3
    return THIRD_LVL  

### END OF SETTINGS PART #################################


# async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """ Function to control buttons (for 'fresh start' - early version)"""
#     bot_msg = "Bot answer"
#     """Parses the CallbackQuery and updates the message text."""
#     query = update.callback_query
#     """ As said in documentation CallbackQueries need to be answered """
#     await query.answer()
#     # Should use global variables
#     global ALLOW_POST_STATUS_TO_GROUP
#     global INFORM_ACTIONERS_OF_MILESTONES
#     match query.data:
#        
#         # Handling freshstart buttons here
#         case "1":
#             bot_msg = "As you wish. Upload new project file"
#             await query.edit_message_text(bot_msg)
#         case "2":
#             bot_msg = "Let's continue with current project"
#             await query.edit_message_text(bot_msg)
#         case "3":
#             bot_msg = "Starting new project will replace your current reminders with new schedule"
#             await query.edit_message_text(bot_msg)
#             # Telegram API can't edit markup at this time, so this is workaround: send new message with buttons
#             freshstart_markup = InlineKeyboardMarkup(freshstart_kbd)
#             bot_msg = "So what did you decide?"
#             await context.bot.send_message(
#                 update.effective_message.chat_id,
#                 parse_mode=ParseMode.MARKDOWN_V2,
#                 text=bot_msg,
#                 reply_markup=freshstart_markup)
#         # Here we could add new buttons behaviour if we decide to create new menus
#         case _:
#             bot_msg = "Unknown answer"
#             await query.edit_message_text(bot_msg)                        


async def post_init(application: Application):
    """Function to control list of commands in bot itself. Commands itself are global """
    await application.bot.set_my_commands([
                                        help_cmd,
                                        start_cmd,
                                        status_cmd,
                                        settings_cmd,
                                        # freshstart_cmd,
                                        feedback_cmd,
                                        stop_cmd
    ])


def main() -> None:

    BOT_TOKEN = os.environ.get("BOT_TOKEN")

    # Create a builder via Application.builder() and then specifies all required arguments via that builder.
    #  Finally, the Application is created by calling builder.build()
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()   

    # Add job store MongoDB
    application.job_queue.scheduler.add_jobstore(
    PTBMongoDBJobStore(
        application=application,
        host=DB_URI,
        )
    )

    # Then, we register each handler and the conditions the update must meet to trigger it
    # Register commands
    # Start communicating with user from the new begining
    # application.add_handler(CommandHandler(start_cmd.command, start)) 
    # /stop should make bot 'forget' about this user and stop jobs
    application.add_handler(CommandHandler(stop_cmd.command, stop)) # in case smth went wrong 
    application.add_handler(CommandHandler(help_cmd.command, help)) # make it show description

    # Command to trigger project status check.
    application.add_handler(CommandHandler(status_cmd.command, status))
    # Initialize start of the project: project name, db initialization and so on, previous project should be archived
    # application.add_handler(CommandHandler(freshstart_cmd.command, freshstart))  
    # Bot should have the ability for user to inform developer of something: bugs, features and so on
    # application.add_handler(CommandHandler(feedback_cmd.command, feedback))  # see below
    # It will be useful if schedule changed outside the bot
    # application.add_handler(CommandHandler("upload", upload))  
    # And if changes were made inside the bot, PM could download updated schedule (original format?)
    # dispatcher.add_handler(CommandHandler("download", download))

    # TODO: version 2 - ability to add custom user reminders (jobs)
    # in this case reminders edit ability should be separated from settings
    # application.add_handler(CommandHandler("remind", add_reminder))
    
    # Handler to control buttons 
    # application.add_handler(CallbackQueryHandler(buttons))    

    # Echo any message that is text and not a command
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Register handler for recieving new project file
    # It's conflicting with /start conversation, better place it in conversation as well
    # application.add_handler(MessageHandler(filters.Document.ALL, upload))

    # Conversation handler for /start
    start_conv = ConversationHandler(
        entry_points=[CommandHandler(start_cmd.command, start)],
        states={
            FIRST_LVL: [MessageHandler(filters.TEXT & ~(filters.COMMAND | filters.Regex(re.compile(r'cancel', re.IGNORECASE))), naming_project),
                        MessageHandler(filters.Regex(re.compile(r'cancel', re.IGNORECASE)), start_ended)
                        ],
            SECOND_LVL: [MessageHandler(filters.Document.ALL, file_recieved)]
        },
        fallbacks=[MessageHandler(filters.TEXT & ~filters.COMMAND, start_ended)]
    )
    application.add_handler(start_conv)

    # Conversation handler for /feedback command
    feedback_conv = ConversationHandler(
        entry_points=[CommandHandler(feedback_cmd.command, feedback)],
        states={
            FIRST_LVL: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_answer)]
        },
        fallbacks=[MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_answer)]
    )
    application.add_handler(feedback_conv)

    # PM should have the abibility to change bot behaviour, such as reminder interval and so on
    settings_conv = ConversationHandler(
        entry_points=[CommandHandler(settings_cmd.command, settings)],
        states={
            FIRST_LVL: [
                CallbackQueryHandler(allow_status_to_group, pattern="^" + str(ONE) + "$"),
                CallbackQueryHandler(milestones_anounce, pattern="^" + str(TWO) + "$"),
                CallbackQueryHandler(reminders, pattern="^" + str(THREE) + "$"),
                CallbackQueryHandler(finish_settings, pattern="^" + str(FOUR) + "$"),
            ],
            SECOND_LVL: [
                CallbackQueryHandler(day_before_update_item, pattern="^" + str(ONE) + "$"),
                CallbackQueryHandler(morning_update_item, pattern="^" + str(TWO) + "$"),
                CallbackQueryHandler(file_update_item, pattern="^" + str(THREE) + "$"),
                CallbackQueryHandler(settings_back, pattern="^" + str(FOUR) + "$"),
                CallbackQueryHandler(finish_settings, pattern="^" + str(FIVE) + "$"),
            ],
            THIRD_LVL: [
                CallbackQueryHandler(reminder_switcher, pattern="^" + str(ONE) + "$"),
                CallbackQueryHandler(reminder_time_pressed, pattern="^" + str(TWO) + "$"),
                CallbackQueryHandler(reminder_days_pressed, pattern="^" + str(THREE) + "$"),
                CallbackQueryHandler(settings_back, pattern="^" + str(FOUR) + "$"),
                CallbackQueryHandler(finish_settings, pattern="^" + str(FIVE) + "$"),
            ],
            FOURTH_LVL:[
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time_setter),
            ],
            FIFTH_LVL:[
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_days_setter),
            ]
        },
        fallbacks=[CallbackQueryHandler(finish_settings)]
    )
    application.add_handler(settings_conv)


    # Start the Bot and run it until Ctrl+C pressed
    application.run_polling()


if __name__ == '__main__':
    main()
