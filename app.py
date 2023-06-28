# Based on https://gitlab.com/Athamaxy/telegram-bot-tutorial/-/blob/main/TutorialBot.py

import logging
import os
import time as tm
import json
import connectors
import tempfile
import asyncio
import re

from dotenv import load_dotenv
from datetime import datetime, date, time
# from io import BufferedIOBase
from telegram import Bot, BotCommand, Update, ForceReply, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
# Default values for daily reminders
MORNING = "10:00"
ONTHEEVE = "16:00"
FRIDAY = "15:00"

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
start_cmd = BotCommand("start", "запуск бота")
stop_cmd = BotCommand("stop", "прекращение работы бота")


# Configure buttons for menus
# for settings menu:
# allow_status_option = "Allow status update in group chat: "     
# milestones_anounce_option = "Users get anounces about milestones (by default only PM): "
# settings_done_option = "Done"

# New one:
# Stages:
FIRST_LVL, SECOND_LVL, THIRD_LVL, FOURTH_LVL, FIFTH_LVL = range(5)
# Callback data
ONE, TWO, THREE, FOUR, FIVE = range(5)


# Build keyboards
#   for /freshstart
# freshstart_kbd = [
#     [
#     InlineKeyboardButton("Yes", callback_data=1), # it is a string actually
#     InlineKeyboardButton("No", callback_data=2),
#     ],
# [InlineKeyboardButton("Info, please", callback_data=3)]
# ]
#   for /settings
# settings_kbd = []


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
                print(f"For testing purposes list jobs: {context.job_queue.jobs()}")
                for job in context.job_queue.jobs():
                    print(f"Job name: {job.name}, enabled: {job.enabled}")
                    pprint(f"has parameters: {job.job.trigger.fields}")
                # Main thread
                # bot_msg = f"Load successfull, wait for updates" # TODO delete
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
                    user_id = ''
                    bot_msg = ''
                    for actioner in project['actioners']:
                        if user.username == actioner['tg_username']:
                            user_id = actioner['id']
                    print(user_id)
                    # Proceed if user found in team members
                    if user_id:
                        for task in project['tasks']:
                            for doer in task['actioners']:
                                # Check time constraints if user assigned to this task
                                if user_id == doer['actioner_id']:
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
                                                    bot_msg = f"Milestone '{task['name']}' is near ({task['enddate']})!"
                                                else:
                                                    # if milestone in past do nothing
                                                    pass
                                            else:
                                                if delta_start.days == 0:
                                                    bot_msg = f"task {task['id']} '{task['name']}' started today."
                                                elif delta_start.days > 0  and delta_end.days < 0:
                                                    bot_msg = f"task {task['id']} '{task['name']}' is intermidiate. Due date is {task['enddate']}"
                                                elif delta_end.days == 0:
                                                    bot_msg = f"task {task['id']}  '{task['name']}' must be completed today!"
                                                elif delta_start.days > 0 and delta_end.days > 0:
                                                    bot_msg = f"task {task['id']} '{task['name']}' is overdue! (had to be completed on {task['enddate']})."
                                                else:
                                                    print(f"Future tasks as {task['id']} '{task['name']}' goes here")  

                        if not bot_msg:
                            bot_msg = f"Seems like there are no critical dates for you now, {user.first_name}."
                        # Send reply to user in group chat if allowed
                        if ALLOW_POST_STATUS_TO_GROUP == True:
                            await update.message.reply_text(bot_msg)
                        else:
                            # Or in private chat
                            await user.send_message(bot_msg)
                        
                    else:
                        bot_msg = f"{user.username} is not participate in schedule provided."
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


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    # username = update.message.from_user.username
    # if username == PM:
    #     option_suffix = ""
    #     option_suffix = "On" if ALLOW_POST_STATUS_TO_GROUP == True else "Off"
    #     allow_status_option = "Allow status update in group chat: " + option_suffix        
    #     option_suffix = "On" if INFORM_ACTIONERS_OF_MILESTONES == True else "Off"
    #     milestones_anounce_option = "Users get anounces about milestones (by default only PM): " + option_suffix

    #     settings_kbd = [
    #                     [InlineKeyboardButton(allow_status_option, callback_data="allow_status_option")],
    #                     [InlineKeyboardButton(milestones_anounce_option, callback_data="milestones_anounce_option")],
    #                     [InlineKeyboardButton(settings_done_option, callback_data="done_option")]
    #     ]
    #     settings_markup = InlineKeyboardMarkup(settings_kbd)     
    #     bot_msg = "You can alter this settings:"
    #     await update.message.reply_text(bot_msg, reply_markup=settings_markup)
    # else:
    #     bot_msg = "Only Project manager is allowed to change settings."
    #     await update.message.reply_text(bot_msg)

    # user = update.message.from_user
    # bot_msg = (f"Current settings for project: \n"
    #             f"Allow status update in group chat: {'On' if ALLOW_POST_STATUS_TO_GROUP == True else 'Off'} \n"
    #             f"Users get anounces about milestones (by default only PM): {'On' if INFORM_ACTIONERS_OF_MILESTONES == True else 'Off'}" 
    # )
    # keyboard = [        
    #         [InlineKeyboardButton("Allow status update in group chat", callback_data=str(ONE))],
    #         [InlineKeyboardButton("Users get anounces about milestones", callback_data=str(TWO))],
    #         [InlineKeyboardButton("Reminders settings", callback_data=str(THREE))],
    #         [InlineKeyboardButton("Finish settings", callback_data=str(FOUR))],        
    # ]
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
    print(f"Finish function, query.data = {query.data}")
    print(f"Current level is: {context.user_data['level']}")
    await query.answer()
    await query.edit_message_text(text="Settings done. You can do something else now.")
    return ConversationHandler.END


async def allow_status_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    print(f"Allow status to group function, query.data = {query.data}")
    print(f"Current level is: {context.user_data['level']}")
    await query.answer()
    # Switch parameter
    global ALLOW_POST_STATUS_TO_GROUP
    ALLOW_POST_STATUS_TO_GROUP = False if ALLOW_POST_STATUS_TO_GROUP else True
    # bot_msg = (f"Current settings for project: \n"
    #             f"Allow status update in group chat: {'On' if ALLOW_POST_STATUS_TO_GROUP == True else 'Off'} \n"
    #             f"Users get anounces about milestones (by default only PM): {'On' if INFORM_ACTIONERS_OF_MILESTONES == True else 'Off'}" 
    # )
#     keyboard = [        
#         [InlineKeyboardButton("Allow status update in group chat", callback_data=str(ONE))],
#         [InlineKeyboardButton("Users get anounces about milestones", callback_data=str(TWO))],
#         [InlineKeyboardButton("Reminders settings", callback_data=str(THREE))],
#         [InlineKeyboardButton("Finish settings", callback_data=str(FOUR))],        
# ]
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
    query = update.callback_query
    print(f"Milestones function, query.data = {query.data}")
    print(f"Current level is: {context.user_data['level']}")
    await query.answer()
    # Switch parameter
    global INFORM_ACTIONERS_OF_MILESTONES
    INFORM_ACTIONERS_OF_MILESTONES = False if INFORM_ACTIONERS_OF_MILESTONES else True
    # bot_msg = (f"Current settings for project: \n"
    #             f"Allow status update in group chat: {'On' if ALLOW_POST_STATUS_TO_GROUP == True else 'Off'} \n"
    #             f"Users get anounces about milestones (by default only PM): {'On' if INFORM_ACTIONERS_OF_MILESTONES == True else 'Off'}" 
    # )
#     keyboard = [        
#         [InlineKeyboardButton("Allow status update in group chat", callback_data=str(ONE))],
#         [InlineKeyboardButton("Users get anounces about milestones", callback_data=str(TWO))],
#         [InlineKeyboardButton("Reminders settings", callback_data=str(THREE))],
#         [InlineKeyboardButton("Finish settings", callback_data=str(FOUR))],        
# ]

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
    # TODO: using future unified function for reminders, 
    # this menu level could provide as many menu items as jobs for current user
    
    query = update.callback_query
    print(f"reminders function, query.data = {query.data}")
    await query.answer()
    context.user_data['level'] = SECOND_LVL
    # TODO add information about reminder settings
    # bot_msg = (f"You can customize reminders here. Current settings are: \n"
    #             f"<under construction>"
    # )

#     keyboard = [        
#         [InlineKeyboardButton("Reminder on day before", callback_data=str(ONE))],
#         [InlineKeyboardButton("Everyday morning reminder", callback_data=str(TWO))],
#         [InlineKeyboardButton("Friday reminder of project files update", callback_data=str(THREE))],
#         [InlineKeyboardButton("Back", callback_data=str(FOUR))],        
#         [InlineKeyboardButton("Finish settings", callback_data=str(FIVE))],        
# ]
    keyboard, bot_msg = get_keybord_and_msg(SECOND_LVL)
    # If somehow app couldn't build a keyboard it is safier to return first level state
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return SECOND_LVL

async def settings_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
#     '''
#     Determin
#     '''
    # I can (can i?) store and access state via     
    # user_data = context.user_data 
    # see:  https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.user_data

# WHAT if i don't change response here?
    print(f"Current level is: {context.user_data['level']}")
    query = update.callback_query
    print(f"Back function, query.data = {query.data}")
    await query.answer()
    bot_msg = "Back from back function. Should add 'bot_msg' to helper function too. "
    # We can return back only if we are not on 1st level
    if context.user_data['level'] > 0:
        context.user_data['level'] = context.user_data['level'] - 1  
    # Make keyboard appropriate to a level we are returning to
    keyboard, bot_msg = get_keybord_and_msg(context.user_data['level'])
    # If somehow app couldn't build a keyboard it is safier to return first level state
    if keyboard == None or bot_msg == None:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:    
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        print(f"Hit 'back' and now level is: {context.user_data['level']}")
        return context.user_data['level']
# Or should I call some of other functions depending on lvl? - I don't quite understand how make it work...
# Or should I provide different keybords here depending on level? - 
# But I can make standalone function to make same keybords instead of making them every time again and again


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
            # TODO: make helper function on a stage when I store job ids (in mongoDB)
            # def get_job_info(info)
            # which should return text to append to message
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


async def day_before_update_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # !!!TODO I can make unified function from this!!!
    # just to know what menu item pressed  - what query data sent
    # This way I could use such function as constructor for any future reminders
    # User could create a reminder and provide text of it himself, 
    # which could be stored in user_data
    
    query = update.callback_query
    print(f"day before reminder function, query.data = {query.data}")
    await query.answer()
    context.user_data['level'] = THIRD_LVL
    # Remember name of JOB this menu item coresponds to.
    context.user_data['last_position'] = 'day_before_update'
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, context.user_data['last_position'])
    preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
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
    query = update.callback_query
    print(f"morning reminder function, query.data = {query.data}")
    await query.answer()
    context.user_data['level'] = THIRD_LVL
    # Remember name of JOB this menu item coresponds to.
    context.user_data['last_position'] = 'morning_update'

    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, context.user_data['last_position'])
    preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
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
    query = update.callback_query
    print(f"friday reminder function, query.data = {query.data}")
    await query.answer()
    context.user_data['level'] = THIRD_LVL
    # Remember what job we are modifying right now
    context.user_data['last_position'] = 'file_update'

    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, context.user_data['last_position'])
    preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
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
    print(f"Reminder switcher function, query.data = {query.data}")
    await query.answer()
    # Recall reminder we are working with
    reminder = context.user_data['last_position']
    print(f"Reminder in reminder switcher: {reminder}")
    # Find a job with given name for current user
    for job in context.job_queue.get_jobs_by_name(reminder):
        print(context.job_queue.get_jobs_by_name(reminder))
        # There should be only one job with given name for a project and for PM
        if job.user_id == update.effective_user.id and job.data == PROJECTTITLE:
            # Switch state for reminder found
            job.enabled = False if job.enabled else True
    
    # Return previous menu
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, reminder)
    preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
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
    # TODO: Should refactor these functions to one universal function
    query = update.callback_query
    print(f"Change time pressed, query.data = {query.data}")
    await query.answer()
    # Recall reminder we are working with
    reminder = context.user_data['last_position']
    preset = get_job_preset(reminder, update.effective_user.id, PROJECTTITLE, context)

    # Check if job found and inform user accordingly
    if not preset:
        text = (f"Seems that reminder doesn't set")
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
    else:
        bot_msg = (f"Current preset for reminder:\n"
                    f"{preset} \n"
                    f"Enter new time in format: 12:30"
                    )
        await query.edit_message_text(bot_msg)
        # Tell conversationHandler to treat answer in a State4 function
        return FOURTH_LVL


async def reminder_days_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    print(f"Change days pressed, query.data = {query.data}")
    await query.answer()
    # Recall reminder we are working with
    reminder = context.user_data['last_position']
    preset = get_job_preset(reminder, update.effective_user.id, PROJECTTITLE, context)
    # Check if job found and inform user accordingly
    if not preset:
        text = (f"Seems that reminder doesn't set")
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
    else:
        bot_msg = (f"Current preset for reminder:\n"
                    f"{preset} \n"
                    f"Write days of week when reminder should work in this format: \n"
                    f"monday, wednesday, friday \n"
                    f"or\n"
                    f"mon,wed,fri"
                    )
        await query.edit_message_text(bot_msg)
        # Tell conversationHandler to treat answer in a State4 function
        return FIFTH_LVL


async def reminder_time_setter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # query = update.callback_query  # query in None here
    reminder = context.user_data['last_position']
    # print(f"User answer got, query.data = {query.data}")
    # await query.answer() # Because query in None here, i think this line needless
    bot_msg = (f"Unable to reschedule the reminder")
    # Try to convert user provided input (time) to hours and minutes
    try:
        hour, minute = map(int, update.message.text.split(":"))                    
        # time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError as e:
        # Prepare message if not succeded
        bot_msg = "Did not recognize time. Please use 24h format: 15:05"
    else:
        for job in context.job_queue.get_jobs_by_name(reminder):
            # There should be only one job with given name for a project and for PM
            if job.user_id == update.message.from_user.id and job.data == PROJECTTITLE:
                # Get timezone attribute from current job
                tz = job.job.trigger.timezone
                # Get list of days of week by index of this attribute in list of fields
                day_of_week = job.trigger.fields[job.trigger.FIELD_NAMES.index('day_of_week')]
                # Reschedule the job
                try:
                    job.job.reschedule(trigger='cron', hour=hour, minute=minute, day_of_week=day_of_week, timezone=tz)
                except Exception as e:
                    bot_msg = (f"Unable to reschedule the reminder")
                    logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')
                bot_msg = (f"Time updated. Next time: "
                            f"{job.next_t}, is it on? {job.enabled}"
                            )                  
                break

    # Inform the user how reschedule went
    await update.message.reply_text(bot_msg)

    # Provide keyboard of level 3 menu 
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, reminder)
    preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
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
    # query = update.callback_query
    reminder = context.user_data['last_position']
    # print(f"User answer got, query.data = {query.data}")
    # await query.answer()
    bot_msg = (f"Unable to reschedule the reminder")
    new_days = []
    # days_of_week = ['mon','tue','wed','thu','fri','sat','sun']
    # Separate user input to list, clean from whitespaces, convert to lower case
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

            # Find a job to reschedule
            for job in context.job_queue.get_jobs_by_name(reminder):
                # There should be only one job with given name for a project and for PM
                if job.user_id == update.message.from_user.id and job.data == PROJECTTITLE:
                    # Get current parameters of job
                    tz = job.trigger.timezone
                    hour = job.trigger.fields[job.trigger.FIELD_NAMES.index('hour')]
                    minute = job.trigger.fields[job.trigger.FIELD_NAMES.index('minute')]                                  
                    # Reschedule the job
                    try:
                        job.job.reschedule(trigger='cron', hour=hour, minute=minute, day_of_week=','.join(new_days), timezone=tz)
                    except Exception as e:
                        bot_msg = (f"Unable to reschedule the reminder")
                        logger.info(f'{tm.asctime()}\t {type(e)} \t {e.with_traceback}')
                    bot_msg = (f"Time updated. Next time: \n"
                                f"{job.next_t}, is it on? {job.enabled}"
                                )
        else:
            bot_msg = (f"No correct names for days of week found in you message.\n")                       
    else:
        bot_msg = (f"Sorry, can't hear you: got empty message")

    # Inform the user how reschedule went
    await update.message.reply_text(bot_msg)

    # Provide keyboard of level 3 menu 
    keyboard, bot_msg = get_keybord_and_msg(THIRD_LVL, reminder)
    preset = get_job_preset(context.user_data['last_position'], update.effective_user.id, PROJECTTITLE, context)
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

# async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """ Function to control buttons in settings """
#     bot_msg = "Bot answer"
#     """Parses the CallbackQuery and updates the message text."""
#     query = update.callback_query
#     """ As said in documentation CallbackQueries need to be answered """
#     await query.answer()
#     # Should use global variables
#     global ALLOW_POST_STATUS_TO_GROUP
#     global INFORM_ACTIONERS_OF_MILESTONES
#     match query.data:
#         # Handling buttons
#         case "allow_status_option":
#             # Switch this setting and reconfigure keyboard and markup
#             ALLOW_POST_STATUS_TO_GROUP = True if ALLOW_POST_STATUS_TO_GROUP == False else False
#             option_suffix = "On" if ALLOW_POST_STATUS_TO_GROUP == True else "Off"
#             allow_status_option = "Allow status update in group chat: " + option_suffix   
#             option_suffix = "On" if INFORM_ACTIONERS_OF_MILESTONES == True else "Off"
#             milestones_anounce_option = "Users get anounces about milestones (by default only PM): " + option_suffix                 
#             settings_kbd = [
#                             [InlineKeyboardButton(allow_status_option, callback_data="allow_status_option")],
#                             [InlineKeyboardButton(milestones_anounce_option, callback_data="milestones_anounce_option")],
#                             [InlineKeyboardButton(settings_done_option, callback_data="done_option")]
#             ]
#             settings_markup = InlineKeyboardMarkup(settings_kbd) 
#             bot_msg = "Setting updated. Something else?"
#             await query.edit_message_text(bot_msg, reply_markup=settings_markup)
#         case "milestones_anounce_option":
#             INFORM_ACTIONERS_OF_MILESTONES = True if INFORM_ACTIONERS_OF_MILESTONES == False else False
#             option_suffix = "On" if ALLOW_POST_STATUS_TO_GROUP == True else "Off"
#             allow_status_option = "Allow status update in group chat: " + option_suffix   
#             option_suffix = "On" if INFORM_ACTIONERS_OF_MILESTONES == True else "Off"
#             milestones_anounce_option = "Users get anounces about milestones (by default only PM): " + option_suffix                 
#             settings_kbd = [
#                             [InlineKeyboardButton(allow_status_option, callback_data="allow_status_option")],
#                             [InlineKeyboardButton(milestones_anounce_option, callback_data="milestones_anounce_option")],
#                             [InlineKeyboardButton(settings_done_option, callback_data="done_option")]
#             ]
#             settings_markup = InlineKeyboardMarkup(settings_kbd)             
#             bot_msg = "Setting updated. Something else?"
#             await query.edit_message_text(bot_msg, reply_markup=settings_markup)
#         case "done_option":
#             bot_msg = "Ok. You may call some other commands"
#             await query.edit_message_text(bot_msg)
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

                    # TODO Reminders should be set after successful upload during start/freshstart routine - Separate function!
                    # Create daily reminders: 1st - daily morining reminder
                    # Prepare time provide timezone info of user location 
                    # Check if jobs already present and add if not
                    preset = get_job_preset('morning_update', update.effective_user.id, PROJECTTITLE, context)
                    if not preset:
                        try:
                    # TODO this should be done in settings set by PM, along with check for correct values. And stored in project settings
                            hour, minute = map(int, MORNING.split(":"))                    
                            time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
                        except ValueError as e:
                            print(f"Error while parsing time: {e}")
                        else:
                            # Set job schedule 
                            morning_update_job = context.job_queue.run_daily(morning_update, user_id=update.effective_user.id, time=time2check, data=PROJECTTITLE)
                            # and enable it. TODO store job id for further use
                            morning_update_job.enabled = True 
                            print(f"Next time: {morning_update_job.next_t}, is it on? {morning_update_job.enabled}")      
                            
                    # 2nd - daily on the eve of task reminder
                    preset = get_job_preset('day_before_update', update.effective_user.id, PROJECTTITLE, context)
                    if not preset:                    
                        try:
                            hour, minute = map(int, ONTHEEVE.split(":"))                    
                            time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
                        except ValueError as e:
                            print(f"Error while parsing time: {e}")
                        else:
                            # Add job to queue and enable it
                            day_before_update_job = context.job_queue.run_daily(day_before_update, user_id=update.effective_user.id, time=time2check, data=PROJECTTITLE)
                            day_before_update_job.enabled = True
                            print(f"Next time: {day_before_update_job.next_t}, is it on? {day_before_update_job.enabled}")   

                    # Register friday reminder
                    preset = get_job_preset('file_update', update.effective_user.id, PROJECTTITLE, context)
                    if not preset:   
                        try:
                            hour, minute = map(int, FRIDAY.split(":"))                    
                            time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
                        except ValueError as e:
                            print(f"Error while parsing time: {e}")
                        else:
                            # Add job to queue and enable it
                            file_update_job = context.job_queue.run_daily(file_update, user_id=update.effective_user.id, time=time2check, days=(5,), data=PROJECTTITLE)
                            file_update_job.enabled = True
                            print(f"Next time: {file_update_job.next_t}, is it on? {file_update_job.enabled}") 
            
    else:
        bot_msg = 'Only Project Manager is allowed to upload new schedule'

    await update.message.reply_text(bot_msg)


def get_job_preset(reminder: str, user_id: int, projectname: str, context: ContextTypes.DEFAULT_TYPE):
    '''
    Helper function that returns current reminder preset for given user and project
    Return None if nothing is found or error occured
    '''
    preset = None
    for job in context.job_queue.get_jobs_by_name(reminder):
        # Search for one associated with current PM and Project
        if job.user_id == user_id and job.data == projectname:
            try:
                hour = job.trigger.fields[job.trigger.FIELD_NAMES.index('hour')]
                minute = f"{job.trigger.fields[job.trigger.FIELD_NAMES.index('minute')]}"
            except:
                preset = None
                break
            else:
                if int(minute) < 10:
                    time_preset = f"{hour}:0{minute}"
                else:
                    time_preset = f"{hour}:{minute}"
                state = 'ON' if job.enabled else 'OFF'
                days_preset = job.trigger.fields[job.trigger.FIELD_NAMES.index('day_of_week')]
                preset = f"{state} {time_preset}, {days_preset}"
                pprint(preset)
                break
    return preset


async def file_update(context: ContextTypes.DEFAULT_TYPE) -> None:
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
    application.add_handler(CommandHandler(start_cmd.command, start)) 
    # /stop should make bot 'forget' about this user and stop jobs
    application.add_handler(CommandHandler(stop_cmd.command, stop)) # in case smth went wrong 
    application.add_handler(CommandHandler(help_cmd.command, help)) # make it show description

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

    # TODO: version 2 - ability to add custom user reminders (jobs)
    # in this case reminders edit ability should be separated from settings
    # application.add_handler(CommandHandler("remind", add_reminder))
    
    # Handler to control buttons 
    # application.add_handler(CallbackQueryHandler(buttons))    

    # Echo any message that is text and not a command
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Register handler for recieving new project file
    application.add_handler(MessageHandler(filters.Document.ALL, upload))

    # PM should have the abibility to change bot behaviour, such as reminder interval and so on
    # application.add_handler(CommandHandler(settings_cmd.command, settings))
    # Settings conversation handler added here 
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
            FOURTH_LVL:[ # TODO
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time_setter),
            ],
            FIFTH_LVL:[ # TODO
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