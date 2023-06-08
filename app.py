# Based on https://gitlab.com/Athamaxy/telegram-bot-tutorial/-/blob/main/TutorialBot.py

import logging
import os
import time as tm
import json
import connectors
import tempfile
import asyncio

from dotenv import load_dotenv
from datetime import datetime, date, time
# from io import BufferedIOBase
from telegram import Bot, BotCommand, Update, ForceReply, InlineKeyboardMarkup, InlineKeyboardButton
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
                            filters)
# For testing purposes
from pprint import pprint


# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# Project constants, should be stored separately TODO

# This setting control whether bot will send status report for PM in private chat 
# or in group chat if /status command executed in group chat
ALLOW_POST_STATUS_TO_GROUP = False 
# Inform actioners of milestones (by default only PM) TODO
INFORM_ACTIONERS_OF_MILESTONES = False
# Time for daily reminders
MORNING = "10:00"
ONTHEEVE = "16:00"

# TODO: change according to starter of the bot
PM = 'hagen10'
# PM = 'Sokolovaspace'
PROJECTTITLE = 'TESTING PROJECT'
PROJECTJSON = "data/temp.json"
KNOWN_USERS = {}

# Set list of commands
help_cmd = BotCommand("help","выводит данное описание")
status_cmd = BotCommand("status", "информация о текущем состоянии проекта")
settings_cmd = BotCommand("settings", "настройка параметров бота")
freshstart_cmd = BotCommand("freshstart", "начало нового проекта")
feedback_cmd = BotCommand("feedback", "+<сообщение> отправит такое сообщение разработчику")


# Configure buttons for menus
# for settings menu:
allow_status_option = "Allow status update in group chat: "     
milestones_anounce_option = "Users get anounces about milestones (by default only PM): "
settings_done_option = "Done"

# Build keyboards
#   for /freshstart
freshstart_kbd = [
    [
    InlineKeyboardButton("Yes", callback_data=1), # it is a string actually
    InlineKeyboardButton("No", callback_data=2),
    ],
[InlineKeyboardButton("Info, please", callback_data=3)]
]
#   for /settings
settings_kbd = []


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
# (update: Update, context: CallbackContext) -> None:
    """
    This function would be added to the application as a handler for messages coming from the Bot API
    """

    # Print to console
    # user = update.effective_user
    user = update.message.from_user
    # username = update.message.from_user.username
    # firstname = update.message.from_user.first_name
    text = str(update.message.text)
    print(f'{user.first_name} wrote {text}')
    logger.info(f'{tm.asctime()}\t{user.id} ({user.username}): {text}')

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


async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    This function purpose is to inform developer of user feedback    
    '''
    # Log when and what user sent using feedback command
    logger.warning(f'{tm.asctime()}\tFEEDBACK from {update.message.from_user.username}: {update.message.text}')
    # List of args can be parsed to retrieve some information, I'm not sure yet what exactly
    # user_feedback = context.args
    bot_msg = "Feedback sent to developer."
    await update.message.reply_text(bot_msg)

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function handles /help command
    """
    # Get description and send to user
    bot_description = await context.bot.getMyDescription()
    bot_msg = bot_description.description
    await update.message.reply_text(bot_msg)

    bot_commands = await context.bot.getMyCommands()
    # Build message about commands
    bot_msg = ''
    for command in bot_commands:
        if command.command != 'help':
            bot_msg = f"/{command.command} - {command.description}\n" + bot_msg

    await update.message.reply_text(bot_msg)
    
def get_assignees(task, actioners):
    '''
    Helper function for getting name and telegram username 
    of person assigned to given task to insert in a bot message
    '''
    people = ""
    user_ids = []
    for doer in task['actioners']:
        for member in actioners:
            # print(f"Doer: {type(doer['actioner_id'])} \t {type(member['id'])}")
            if doer['actioner_id'] == member['id']:                                                    
                # people.append((member['name'], member['tg_username']))  
                if member['tg_id']:
                    user_ids.append(member['tg_id'])              
                if len(people) > 0:
                    people = people + "and @" + member['tg_username'] + " (" + member['name'] + ")"
                else:
                    people = f"{people}@{member['tg_username']} ({member['name']})"
    return people, user_ids


def add_user_id(user, project):
    ''' 
    Helper function to add telegram id of user to project json
    '''
    # Remember telegram user id
    for actioner in project['actioners']:
        if actioner['tg_username'] == user.username:
            # This will overwrite existing id if present, but it should not be an issue
            actioner['tg_id'] = user.id
    return project


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function handles /status command
    """
    bot_msg = "Should print status to user"
    # Because /status command could be called anytime, we can't pass project stored in memory to it
    # so it will be loaded from disk

    if os.path.exists(PROJECTJSON):
        with open(PROJECTJSON, 'r') as fp:
            try:
                project = connectors.load_json(fp)
            except Exception as e:
                bot_msg = f"ERROR ({e}): Unable to load"
                logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')                  
            else:
                # Main thread
                bot_msg = f"Load successfull, wait for updates"
                user = update.message.from_user
                username = user.username
                # Check if user in project team, update id if not present
                project = add_user_id(user, project)
                # Update project file
                bot_msg = save_json(project)
                # check Who calls?
                # if PM then proceed all tasks
                if username == PM:
                    for task in project['tasks']:
                        # Bot will inform user only of tasks with important dates
                        bot_msg = ""
                        # Check if task not completed
                        if task['complete'] < 100:
                            # If delta_start <0 task not started, otherwise already started
                            delta_start = date.today() - date.fromisoformat(task['startdate'])
                            # If delta_end >0 task overdue, if <0 task in progress
                            delta_end = date.today() - date.fromisoformat(task['enddate'])
                            user_ids = []
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
                                        bot_msg = f"Milestone '{task['name']}' is near ({task['enddate']})!"
                                    else:
                                        # if milestone in past do nothing
                                        pass
                                else:
                                    actioners = project['actioners']
                                    if delta_start.days == 0:
                                        try:
                                            people, user_ids = get_assignees(task, actioners)
                                        except Exception as e:
                                            bot_msg = "Error occured while processing assigned actioners to task task['id']} '{task['name']}' starting today"
                                            logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')
                                        else:
                                            bot_msg = f"task {task['id']} '{task['name']}' starts today. Assigned to: {people}"
                                    elif delta_start.days > 0  and delta_end.days < 0:
                                        try:
                                            people, user_ids = get_assignees(task, actioners)
                                        except Exception as e:
                                            bot_msg = f"Error occured while processing assigned actioners to task {task['id']} {task['name']}"
                                            logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')
                                        else:
                                            bot_msg = f"task {task['id']} '{task['name']}' is intermidiate. Due date is {task['enddate']}. Assigned to: {people}"
                                    elif delta_end.days == 0:
                                        try:
                                            people, user_ids = get_assignees(task, actioners)
                                        except Exception as e:
                                            bot_msg = f"Error occured while processing assigned actioners to task {task['id']} {task['name']}"
                                            logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')
                                        else:                                        
                                            bot_msg = f"task {task['id']}  '{task['name']}' must be completed today! Assigned to: {people}"
                                    elif delta_start.days > 0 and delta_end.days > 0:
                                        try:
                                            people, user_ids = get_assignees(task, actioners)
                                        except Exception as e:
                                            bot_msg = f"Error occured while processing assigned actioners to task {task['id']} {task['name']}"
                                            logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')
                                        else:                                         
                                            bot_msg = f"task {task['id']} '{task['name']}' is overdue! (had to be completed on {task['enddate']}). Assigned to: {people}"
                                    else:
                                        print(f"Future tasks as {task['id']} '{task['name']}' goes here")                            

                            # Check if there is something to report to user
                            if bot_msg:
                                # Send reply to PM in group chat if allowed
                                if ALLOW_POST_STATUS_TO_GROUP == True:
                                    await update.message.reply_text(bot_msg)
                                else:
                                    # Or in private chat
                                    await user.send_message(bot_msg)
                                # And send msg to actioner (if it is not a PM)
                                for id in user_ids:
                                    # print(id)
                                    if id != user.id: 
                                        await context.bot.send_message(
                                            id,
                                            text=bot_msg,
                                            parse_mode=ParseMode.HTML)

                # if not - then only tasks for this member
                else:
                    # Check if user is part of the project team
                    if [True for x in project['actioners'] if x['tg_username'] == username]:
                        bot_msg = f"Project status for {username} (will be here)"




                        # Send reply to user in group chat if allowed
                        if ALLOW_POST_STATUS_TO_GROUP == True:
                            await update.message.reply_text(bot_msg)
                        else:
                            # Or in private chat
                            await user.send_message(bot_msg)
                    else:
                        bot_msg = f"{username} is not participate in schedule provided."
                        # TODO This case should be certanly send to PM. For time being just keep it this way
                        await update.message.reply_text(bot_msg)

                    print(f"username: {user.username}, id: {user.id}")
                    
                  
    else:
        bot_msg = f"Project file does not exist, try to load first"
        # TODO consider send directly to user asked
        await update.message.reply_text(bot_msg)  

async def freshstart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function handles /freshstart command
    """
    freshstart_markup = InlineKeyboardMarkup(freshstart_kbd)
    bot_msg = "Are you really want to start a new project?"
    await update.message.reply_text(bot_msg, reply_markup=freshstart_markup)


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
    # + Allow status update in group chat
    # 4. interval of intermidiate reminders
    # For this purpose I will need ConversationHandler
    # 5. Time of daily update of starting and deadline tasks, and days too

    # Check if it is PM who wish to change settings
    username = update.message.from_user.username
    if username == PM:
        option_suffix = ""
        option_suffix = "On" if ALLOW_POST_STATUS_TO_GROUP == True else "Off"
        allow_status_option = "Allow status update in group chat: " + option_suffix        
        option_suffix = "On" if INFORM_ACTIONERS_OF_MILESTONES == True else "Off"
        milestones_anounce_option = "Users get anounces about milestones (by default only PM): " + option_suffix

        settings_kbd = [
                        [InlineKeyboardButton(allow_status_option, callback_data="allow_status_option")],
                        [InlineKeyboardButton(milestones_anounce_option, callback_data="milestones_anounce_option")],
                        [InlineKeyboardButton(settings_done_option, callback_data="done_option")]
        ]
        settings_markup = InlineKeyboardMarkup(settings_kbd)     
        bot_msg = "You can alter this settings:"
        await update.message.reply_text(bot_msg, reply_markup=settings_markup)
    else:
        bot_msg = "Only Project manager is allowed to change settings."
        await update.message.reply_text(bot_msg)

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ Function to control buttons in settings """
    bot_msg = "Bot answer"
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    """ As said in documentation CallbackQueries need to be answered """
    await query.answer()
    # Should use global variables
    global ALLOW_POST_STATUS_TO_GROUP
    global INFORM_ACTIONERS_OF_MILESTONES
    match query.data:
        # Handling buttons
        case "allow_status_option":
            # Switch this setting and reconfigure keyboard and markup
            ALLOW_POST_STATUS_TO_GROUP = True if ALLOW_POST_STATUS_TO_GROUP == False else False
            option_suffix = "On" if ALLOW_POST_STATUS_TO_GROUP == True else "Off"
            allow_status_option = "Allow status update in group chat: " + option_suffix   
            option_suffix = "On" if INFORM_ACTIONERS_OF_MILESTONES == True else "Off"
            milestones_anounce_option = "Users get anounces about milestones (by default only PM): " + option_suffix                 
            settings_kbd = [
                            [InlineKeyboardButton(allow_status_option, callback_data="allow_status_option")],
                            [InlineKeyboardButton(milestones_anounce_option, callback_data="milestones_anounce_option")],
                            [InlineKeyboardButton(settings_done_option, callback_data="done_option")]
            ]
            settings_markup = InlineKeyboardMarkup(settings_kbd) 
            bot_msg = "Setting updated. Something else?"
            await query.edit_message_text(bot_msg, reply_markup=settings_markup)
        case "milestones_anounce_option":
            INFORM_ACTIONERS_OF_MILESTONES = True if INFORM_ACTIONERS_OF_MILESTONES == False else False
            option_suffix = "On" if ALLOW_POST_STATUS_TO_GROUP == True else "Off"
            allow_status_option = "Allow status update in group chat: " + option_suffix   
            option_suffix = "On" if INFORM_ACTIONERS_OF_MILESTONES == True else "Off"
            milestones_anounce_option = "Users get anounces about milestones (by default only PM): " + option_suffix                 
            settings_kbd = [
                            [InlineKeyboardButton(allow_status_option, callback_data="allow_status_option")],
                            [InlineKeyboardButton(milestones_anounce_option, callback_data="milestones_anounce_option")],
                            [InlineKeyboardButton(settings_done_option, callback_data="done_option")]
            ]
            settings_markup = InlineKeyboardMarkup(settings_kbd)             
            bot_msg = "Setting updated. Something else?"
            await query.edit_message_text(bot_msg, reply_markup=settings_markup)
        case "done_option":
            bot_msg = "Ok. You may call some other commands"
            await query.edit_message_text(bot_msg)
        # Handling freshstart buttons here
        case "1":
            bot_msg = "As you wish. Upload new project file"
            await query.edit_message_text(bot_msg)
        case "2":
            bot_msg = "Let's continue with current project"
            await query.edit_message_text(bot_msg)
        case "3":
            bot_msg = "Starting new project will replace your current reminders with new schedule"
            await query.edit_message_text(bot_msg)
            # Telegram API can't edit markup at this time, so this is workaround: send new message with buttons
            freshstart_markup = InlineKeyboardMarkup(freshstart_kbd)
            bot_msg = "So what did you decide?"
            await context.bot.send_message(
                update.effective_message.chat_id,
                parse_mode=ParseMode.MARKDOWN_V2,
                text=bot_msg,
                reply_markup=freshstart_markup)
        # Here we could add new buttons behaviour if we decide to create new menus
        case _:
            bot_msg = "Unknown answer"
            await query.edit_message_text(bot_msg)                        


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

                    case '.xml':
                        project = connectors.load_xml(fp)

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
                logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')
            else:
                if project:
                    # Remember telegram user id
                    project = add_user_id(update.message.from_user, project)
                    # Call function to save project in JSON format
                    bot_msg = save_json(project)

                    # Create daily reminders: 1st - daily morining reminder
                    # Prepare time provide timezone info of user location 
                    # TODO this should be done in settings set by PM, along with check for correct values. And stored in project settings
                    try:
                        hour, minute = map(int, MORNING.split(":"))                    
                        time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
                    except ValueError as e:
                        print(f"Error while parsing time: {e}")
                    else:
                        # Set job schedule and enable it
                        context.job_queue.run_daily(morning_update, time=time2check, data=PROJECTTITLE).enabled = True 
                        for job in context.job_queue.get_jobs_by_name('morning_update'):
                            print(f"Next time: {job.next_t}, is it on? {job.enabled}")      
                            
                    # 2nd - daily on the eve of task reminder
                    try:
                        hour, minute = map(int, ONTHEEVE.split(":"))                    
                        time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
                    except ValueError as e:
                        print(f"Error while parsing time: {e}")
                    else:
                        # Add job to queue and enable it
                        context.job_queue.run_daily(on_the_eve_update, time=time2check, data=PROJECTTITLE).enabled = True 
                        for job in context.job_queue.get_jobs_by_name('on_the_eve_update'):
                            print(f"Next time: {job.next_t}, is it on? {job.enabled}")     
            
    else:
        bot_msg = 'Only Project Manager is allowed to upload new schedule'

    await update.message.reply_text(bot_msg)

async def file_update_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    This function to remind team members that common files should be updated in the end of the week
    '''
    if os.path.exists(PROJECTJSON):
        with open(PROJECTJSON, 'r') as fp:
            try:
                project = connectors.load_json(fp)
            except Exception as e:
                logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')                  
            else:
                # Loop through actioners to inform them about actual tasks
                bot_msg = "Напоминаю, что сегодня надо освежить файлы по проекту! Чтобы другие участники команды имели актуальную информацию. Спасибо!"
                for actioner in project['actioners']:
                    # Bot can inform only ones with known id
                    # print(actioner)
                    if actioner['tg_id']:
                        await context.bot.send_message(
                            actioner['tg_id'],
                            text=bot_msg,
                            parse_mode=ParseMode.HTML)
    # TODO delete
    print("friday update")

async def on_the_eve_update(context: ContextTypes.DEFAULT_TYPE) -> None:
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
                logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')                  
            else:
                # Loop through actioners to inform them about actual tasks
                for actioner in project['actioners']:
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


async def morning_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    This routine will be executed on daily basis to control project(s) schedule
    '''
    # TODO use data to associate project name with job
    # TODO how to make observation of project a standalone function to be called elsewhere?

    if os.path.exists(PROJECTJSON):
        with open(PROJECTJSON, 'r') as fp:
            try:
                project = connectors.load_json(fp)
            except Exception as e:
                bot_msg = f"ERROR ({e}): Unable to load"
                logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')                  
            else:
                # Loop through actioners to inform them about actual tasks
                for actioner in project['actioners']:
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

    # for job in context.job_queue.get_jobs_by_name('daily_update'):         
    #     logger.info(f'{tm.asctime()}\t Job data: {job.data}, Name: {job.name}, next time: {job.next_t}')

def save_json(project):
    ''' 
    Saves project in JSON format and returns message about success of operation
    '''
    bot_msg = ''
    with open(PROJECTJSON, 'w', encoding='utf-8') as json_fh:
        try:
            json.dump(project, json_fh, ensure_ascii=False, indent=4)
        except:
            bot_msg = 'Error saving project to json file'    
        else:
            bot_msg = 'Successfully saved project to json file'

    # TODO reconsider returning None if succeed because there is no need always inform user about every file update
    return bot_msg

async def start(update: Update, context: CallbackContext) -> None:
    '''
    Function to handle start of the bot
    '''
    # Update PM to current user
    # global PM
    # PM = update.effective_user.username
    bot_msg = f"Hello, {update.effective_user.first_name}!"
    await update.message.reply_text(bot_msg)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Function to stop the bot.
    Should make bot forget about the user, 
    and stop all jobs associated with the user
    '''

    # Remove daily reminder associated with PROJECTTITLE
    # TODO revise
    current_jobs = context.job_queue.jobs    
    if not current_jobs:
        pass
    else:
        for job in current_jobs:
            if job.data == PROJECTTITLE:
                job.schedule_removal()


# Function to control list of commands in bot itself. Commands itself are global
async def post_init(application: Application):
    await application.bot.set_my_commands([
                                        help_cmd,
                                        status_cmd,
                                        settings_cmd,
                                        freshstart_cmd,
                                        feedback_cmd
    ])


def main() -> None:

    load_dotenv()
    BOT_TOKEN = os.environ.get("BOT_TOKEN")

    # Create a builder via Application.builder() and then specifies all required arguments via that builder.
    #  Finally, the Application is created by calling builder.build()
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()   


    # Then, we register each handler and the conditions the update must meet to trigger it
    # Register commands
    # Start communicating with user from the new begining
    application.add_handler(CommandHandler("start", start)) 
    # /stop should make bot 'forget' about this user and stop jobs
    application.add_handler(CommandHandler("stop", stop)) # in case smth went wrong 
    application.add_handler(CommandHandler(help_cmd.command, help)) # make it show description
    # PM should have the abibility to change bot behaviour, such as reminder interval and so on
    application.add_handler(CommandHandler(settings_cmd.command, settings))
    # Command to trigger project status check.
    application.add_handler(CommandHandler(status_cmd.command, status))
    # Initialize start of the project: project name, db initialization and so on, previous project should be archived
    application.add_handler(CommandHandler(freshstart_cmd.command, freshstart))  
    # Bot should have the ability for user to inform developer of something: bugs, features and so on
    application.add_handler(CommandHandler(feedback_cmd.command, feedback))  
    # It will be useful if schedule changed outside the bot
    # application.add_handler(CommandHandler("upload", upload))  
    # And if changes were made inside the bot, PM could download updated schedule (original format?)
    # dispatcher.add_handler(CommandHandler("download", download))

    # Handler to control buttons 
    application.add_handler(CallbackQueryHandler(buttons))    

    # Echo any message that is text and not a command
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Register handler for recieving new project file
    application.add_handler(MessageHandler(filters.Document.ALL, upload))

    # Register friday reminder
    friday_time = "15:00"
    try:
        hour, minute = map(int, friday_time.split(":"))                    
        time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError as e:
        print(f"Error while parsing time: {e}")
    else:
        # Add job to queue and enable it
        application.job_queue.run_daily(file_update_reminder, time=time2check, days=(5,), data=PROJECTTITLE).enabled = True 
        for job in application.job_queue.get_jobs_by_name('file_update_reminder'):
            print(f"Next time: {job.next_t}, is it on? {job.enabled}")     

    # Start the Bot and run it until Ctrl+C pressed
    application.run_polling()


if __name__ == '__main__':
    main()