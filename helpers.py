"""
Some helper functions to help main functions to manupulate with data
"""

import json
import logging
import pymongo
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson import ObjectId
from datetime import date
from dotenv import load_dotenv
from pprint import pprint
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from pymongo.database import Database
from re import sub
from telegram import User, InlineKeyboardButton
from telegram.ext import ContextTypes
from typing import Tuple
from urllib.parse import quote_plus

# Callback data for settings menu
ONE, TWO, THREE, FOUR, FIVE, SIX = range(6)

# Configure logging
# logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.basicConfig(filename=".data/log.log", 
                    filemode='a', 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
                    level=logging.INFO)
logger = logging.getLogger(__name__)


def add_user_id_to_db(user: User, db: Database) -> str:
    ''' 
    Helper function to add telegram id of username provided to DB. 
    Returns empty string if telegram username not found in staff collection, did't updated or something went wrong.
    Returns ObjectId if record updated
    '''
    output = ''

    # Fill record with absent id with current one
    # For now I assume that users don't switch their usernames and such situation is force-major
    record = db.staff.find_one({"tg_username": user.username}, {"tg_id": 1})

    if (record and type(record) == dict and 
        'tg_id' in record.keys() and not record['tg_id']):            

            # Remember: for update_one matched_count will not be more than one
            result = db.staff.update_one({"tg_username": user.username}, {"$set": {"tg_id": str(user.id)}})
            if result.modified_count > 0:            
                output = record["_id"]

    return output


def add_user_info_to_db(user: User, db: Database):
    """
    Adds missing user info (telegram id and name) to DB
    Returns None if telegram username not found in staff collection, did't updated or something went wrong.
    Returns ObjectId if record updated
    """
    output = ''

    # Get user from DB

    db_user = db.staff.find_one({"tg_username": user.username})

    # Check if field is empty and fill it with corresponding field from User
    if (db_user and type(db_user) == dict and 
        'tg_id' in db_user.keys() and 'name' in db_user.keys()) :
        dict2update = {}
        if not db_user['tg_id']:
            dict2update['tg_id'] = str(user.id)
        if not db_user['name']:
            if user.first_name:
                dict2update['name'] = user.first_name
            elif user.name:
                dict2update['name'] = user.name

        # Make update in DB using list of collected list of should be modified fields converted to tuple
        if dict2update:
            result = db.staff.update_one({"tg_username": user.username}, {"$set": dict2update})
            
            if result.modified_count > 0:    
                output = db_user['_id']

    return output


def add_worker_info_to_staff(worker: dict, db: Database):
    ''' 
    Calls functions to check whether such worker exist in staff collection. 
    Adds given worker to staff collection if not exist already.
    Fill empty fields in case worker already present in staff (for ex. PM is actioner in other project)
    '''
    
    worker_id = None

    # Check DB if worker already present via telegram id
    if worker['tg_id']:
        worker_id = get_worker_oid_from_db_by_tg_id(worker['tg_id'], db)

    # Otherwise via telegram username
    elif worker['tg_username']:
        worker_id = get_worker_oid_from_db_by_tg_username(worker['tg_username'], db)
    else:
        raise ValueError(f"Not enough information about worker provided: neither tg_id nor tg_username. Provided dict:\n{worker}")
    
    # If worker not found in staff collection add him, if exist then fill empty fields
    if not worker_id:
        worker_id = db.staff.insert_one(worker).inserted_id
    else:
        db_worker = db.staff.find_one({"_id": worker_id})
        if db_worker and type(db_worker) == dict:
            for key in worker.keys():
                if not db_worker[key]:
                    db_worker[key] = worker[key]
            result = db.staff.replace_one({"_id": worker_id}, replacement=db_worker)
            # TODO consider make it info rather than warning after development finished
            logger.warning(f"Results of worker {db_worker['tg_username']} update: '{result.matched_count}' found, '{result.modified_count}' modified.")

    return worker_id


def clean_project_title(user_input: str) -> str:
    """
    Clean title typed by user from unnesesary spaces and so on.
    Imagine someone copy-pasted project title here, what can be improved?
    Should return string.
    If something went wrong raise value error to be managed on calling side.
    """

    # To prevent user from using War and Peace as a title let's limit its length to this number of symbols
    max_title_len = 128

    # Replace whitespaces and their doubles with spaces, cut leading and ending spaces
    title = sub("\s+", " ", user_input).strip()
    if not title:
        raise ValueError("Text absent")
    
    return title[:max_title_len]


def get_assignees(task: dict, db: Database):
    '''
    Helper function for getting names and telegram usernames
    of person assigned to given task to insert in a bot message
    Returns string of the form: '@johntherevelator (John) and @judasofkerioth (Judas)'
    Also returns list of their telegram ids for bot to be able to send direct messages
    '''

    people = ""
    user_ids = []

    for doer in task['actioners']:
        try:
            team_member = db.staff.find_one({"_id": doer['actioner_id']})
        except Exception as e:
            logger.error(f"There was error getting DB: {e}")
        else:
            if team_member and type(team_member) == dict:
                if 'tg_id' in team_member.keys() and team_member['tg_id']:
                    user_ids.append(team_member['tg_id'])
                if len(people) > 0:
                    people = people + "and @" + team_member['tg_username'] + " (" + team_member['name'] + ")"
                else:
                    people = f"{people}@{team_member['tg_username']} ({team_member['name']})"

    return people, user_ids # ids will be needed for buttons to ping users


def get_db():
    """
    Creates connection to mongo server and returns database instance. Raises exception if not succeed.
    """
    load_dotenv()
    BOT_NAME = os.environ.get('BOT_NAME')
    BOT_PASS = os.environ.get('BOT_PASS')

    # link to database
    # DB_URI = f"mongodb://{BOT_NAME}:{BOT_PASS}@localhost:27017/admin?retryWrites=true&w=majority"
    DB_NAME = os.environ.get("DB_NAME", "database")
    host = '127.0.0.1:27017'
    if not BOT_NAME or not BOT_PASS:
        raise AttributeError("Can't get bot credentials from environment.")
    uri = "mongodb://%s:%s@%s" % (quote_plus(BOT_NAME), quote_plus(BOT_PASS), host)
    # DB = None
    try:
        # client = pymongo.MongoClient(f"mongodb://{BOT_NAME}:{BOT_PASS}@localhost:27017/admin?retryWrites=true&w=majority")
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=1000) 
    except ConnectionError as e:
        logger.error(f"There is problem with connecting to db '{DB_NAME}': {e}")   
    else:

        # Check for connection
        try:
            # client.admin.command('ping')
            # client.admin.command('ismaster')
            client.server_info()
        except (ServerSelectionTimeoutError, ConnectionFailure) as e:
            raise ConnectionError(e)
        else:
            DB = client[DB_NAME]
            return DB        


def get_job_preset(job_id: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    """ Returns current preset of job in text format to add to messages """
    #TODO Better make this a method of a job-class (maybe reminder class) evolved from base job-class

    presets_dict = get_job_preset_dict(job_id, context)
    if presets_dict:
        if presets_dict['minute'] < 10:
            time_preset = f"{presets_dict['hour']}:0{presets_dict['minute']}"
        else:
            time_preset = f"{presets_dict['hour']}:{presets_dict['minute']}"
        preset = f"{presets_dict['state']} {time_preset}, {presets_dict['day_of_week']}"
    else:
        preset = ''

    return preset


def get_job_preset_dict(job_id: str, context: ContextTypes.DEFAULT_TYPE) -> dict:
    '''
    Helper function that returns current reminder preset for given job id
    Returns empty dict if nothing is found or error occured
    '''  
    #TODO Better make this a method of a job-class (maybe reminder class) evolved from base job-class
    
    preset = {}

    job = context.job_queue.scheduler.get_job(job_id)
    try:
        hour = job.trigger.fields[job.trigger.FIELD_NAMES.index('hour')]
        # TODO WHY string?
        minute = job.trigger.fields[job.trigger.FIELD_NAMES.index('minute')]
        days_preset = str(job.trigger.fields[job.trigger.FIELD_NAMES.index('day_of_week')])
        # days_list = list(job.trigger.fields[job.trigger.FIELD_NAMES.index('day_of_week')])
    except:
        preset = {}       
    else:

        # Determine if job is on or off
        if job.next_run_time:
            state = 'ON'
        else:
            state = 'OFF'
        
        preset = {
            'hour': int(str(hour)),
            'minute': int(str(minute)),
            'day_of_week': days_preset,
            'state': state
        }
   
    return preset


def get_keyboard_and_msg(db, level: int, user_id: str, project: dict, branch: str = None) -> Tuple[list, str]:
    '''
    Helper function to provide specific keyboard on different levels of settings menu
    '''

    keyboard = []
    msg = ''

    if ('title' in project.keys() and 'settings' in project.keys() and 
        'reminders' in project.keys() and
        project['title'] and project['settings']):
        
        # Configure keyboard and construct message depending of menu level
        match level:

            # First level of menu 
            case 0:
                msg = (f"Manage settings. Active project: '{project['title']}'")
                keyboard = [        
                    [InlineKeyboardButton(f"Change notifications settings", callback_data="notifications")],
                    [InlineKeyboardButton(f"Manage projects", callback_data="projects")],
                    [InlineKeyboardButton(f"Reminders settings", callback_data="reminders")],
                    [InlineKeyboardButton(f"Transfer control over active project to other user", callback_data="control")],
                    [InlineKeyboardButton(f"Finish settings", callback_data='finish')],        
                ]

            # Second level of menu
            case 1:
                match branch:
                    case "notifications":
                        if is_db(db):
                            try: #TODO consider get this setting outside keyboard function
                                pm_settings = db.staff.find_one({"tg_id": str(user_id)}, {"settings":1, "_id":0})
                            except Exception as e:
                                logger.error(f"There was error getting DB: {e}")
                            else:
                                if (pm_settings and 
                                    type(pm_settings) == dict and
                                    'settings' in pm_settings.keys() and
                                    'INFORM_OF_ALL_PROJECTS' in pm_settings['settings'].keys()):

                                    msg = f"Manage notification settings:"
                                    keyboard = [        
                                        [InlineKeyboardButton(f"Allow status update in group chat: {'On' if project['settings']['ALLOW_POST_STATUS_TO_GROUP'] == True else 'Off'}", callback_data=str(ONE))],
                                        [InlineKeyboardButton(f"Users get anounces about milestones: {'On' if project['settings']['INFORM_ACTIONERS_OF_MILESTONES'] == True else 'Off'}", callback_data=str(TWO))],
                                        [InlineKeyboardButton(f"/status command notify PM of all projects (not only active): {'On' if pm_settings['settings']['INFORM_OF_ALL_PROJECTS'] == True else 'Off'}", callback_data=str(THREE))],
                                        [InlineKeyboardButton("Back", callback_data='back')], 
                                        [InlineKeyboardButton("Finish settings", callback_data='finish')],        
                                    ]

                    case "projects":
                        if is_db(db):
                            msg = f"You can manage these projects (active project could only be renamed): "
                            # Get list of projects for user
                            projects = list(db.projects.find({"pm_tg_id": str(user_id)}))
                            
                            # For each project make buttons: active(if not active), rename, delete with oid as a string
                            keyboard = []
                            for project in projects:                                    
                                keyboard.append([InlineKeyboardButton(f"Rename: '{project['title']}'", callback_data=f"rename_{project['_id']}")])
                                
                                if project['active'] == False: 
                                    row = [
                                        InlineKeyboardButton(f"Activate '{project['title']}'", callback_data=f"activate_{project['_id']}"),
                                        InlineKeyboardButton(f"Delete '{project['title']}'", callback_data=f"delete_{project['_id']}"),
                                    ]   
                                    keyboard.append(row)
                            keyboard.extend([
                                    [InlineKeyboardButton("Back", callback_data='back')],        
                                    [InlineKeyboardButton("Finish settings", callback_data='finish')]
                            ])                         

                    case "reminders":
                        # TODO: Here I could construct keyboard out of jobs registered for current user and active project,
                        # similar to project list above.
                        # but this will need of passing composite callback_data,
                        # first part of which will be checked by pattern parameter of CallbackQueryHandler
                        # and second used inside universal reminder function
                        msg = (f"You can customize reminders here.")
                        keyboard = [        
                            [InlineKeyboardButton("Reminder on day before", callback_data='day_before_update')],
                            [InlineKeyboardButton("Everyday morning reminder", callback_data='morning_update')],
                            [InlineKeyboardButton("Friday reminder of project files update", callback_data='friday_update')],
                            [InlineKeyboardButton("Back", callback_data='back')],        
                            [InlineKeyboardButton("Finish settings", callback_data='finish')],        
                        ]

                    case "control":
                        if is_db(db):
                            msg = (f"Choose a project team member to transfer control to.")

                            # Get team members names with telegram ids, except PM
                            # Construct keyboard from that list
                            # TODO TEST WHat if it's a sole project? Only PM is working?
                            team = get_project_team(project, db)
                            if team:
                                keyboard = []
                                for member in team:
                                    if user_id != member['tg_id']:
                                        keyboard.append([InlineKeyboardButton(f"{member['name']} (@{member['tg_username']})", callback_data=member['tg_id'])])       
                                keyboard.extend([
                                    [InlineKeyboardButton("Back", callback_data='back')],        
                                    [InlineKeyboardButton("Finish settings", callback_data='finish')]
                                ])                                

            # Third menu level
            case 2:
                reminders_kbd = [        
                    [InlineKeyboardButton("Turn on/off", callback_data=str(ONE))],
                    [InlineKeyboardButton("Set time", callback_data=str(TWO))],
                    [InlineKeyboardButton("Set days of week", callback_data=str(THREE))],
                    [InlineKeyboardButton("Back", callback_data='back')],        
                    [InlineKeyboardButton("Finish settings", callback_data='finish')],        
                ]
                project_delete_kbd = [
                    [InlineKeyboardButton("Yes", callback_data='yes')],
                    [InlineKeyboardButton("No", callback_data='back')],
                ]
                # Message contents depend on a branch of menu, return None if nonsense given
                match branch:
                    case 'morning_update':                    
                        msg = (f"Daily morning reminder has to be set here.\n"
                                )
                        keyboard = reminders_kbd
                    case 'day_before_update':
                        msg = (f"The day before reminder has to be set here. \n"
                                )
                        keyboard = reminders_kbd
                    case 'friday_update':
                        msg = (f"Reminder for file updates on friday has to be set here. \n"
                                )
                        keyboard = reminders_kbd
                    case 'delete':
                        msg = f"Are you sure?"
                        keyboard = project_delete_kbd

    return keyboard, msg


def get_projects_and_pms_for_user(user_oid: ObjectId, db: Database) -> str:
    ''' Function to get string of projects (and their PMs) where user participate as actioner '''
    
    projects_and_pms = ''
    try:
        projects = list(db.projects.find(
            {"tasks.actioners": 
                {"$elemMatch":
                    {"actioner_id": user_oid}}}, 
            {"title":1, "pm_tg_id":1, "_id":0})
            )
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if projects:
            for project in projects:
                if projects_and_pms:
                    projects_and_pms += ', '
                pm_un = get_worker_tg_username_by_tg_id(project['pm_tg_id'], db)
                if pm_un:
                    projects_and_pms = projects_and_pms + f"'{project['title']}' (@{pm_un})"
                else:
                    projects_and_pms = projects_and_pms + f"'{project['title']}'"        

    return projects_and_pms


def get_project_team(project: dict, db: Database) -> list:
    """
    Construct list of project team members.
    Returns None if it is not possible to achieve or something went wrong.
    """
    team = []    
  
    # Loop through project tasks and gather information about project team
    for task in project['tasks']:

        # Process only tasks with actioners
        if task['actioners']:
            for actioner in task['actioners']:

                # Proceed if such actioner not in team already
                if not any(str(actioner['actioner_id']) in str(member['_id']) for member in team):
                    try:
                        result = db.staff.find_one({'_id': actioner['actioner_id']})
                    except Exception as e:
                        logger.error(f"There was error getting DB: {e}")
                    else:
                        if result and type(result) == dict:
                            team.append(result)
    
    if not team:
        logger.error(f"Maybe DB is corrupted: project '{project['title']}' (id: {project['_id']}) has no project team!")

    return team


def get_status_on_project(project: dict, user_oid: ObjectId, db: Database) -> str:
    """
    Function compose message contains status update on given project for given ObjectId (actioner)
    """

    bot_msg = f"Status of events for project '{project['title']}'"

    # Add PM username
    pm_username = get_worker_tg_username_by_tg_id(project['pm_tg_id'], db)

    if pm_username:
        project['tg_username'] = pm_username
        bot_msg = bot_msg + f" (PM: @{project['tg_username']}):"
    else:
        logger.error(f"PM (with tg_id: {project['pm_tg_id']}) was not found in db.staff!")

    # Get user telegram username to add to message
    actioner_username = get_worker_tg_username_by_oid(user_oid, db)
    if actioner_username:

        # Find task to inform about: not completed yet, not a milestone, not common task (doesn't consist of subtasks), and this user assigned to it
        msg = ''
        for task in project['tasks']:
            if (task['complete'] < 100 and 
                not task['include'] and 
                not task['milestone'] and 
                # User object_id is not iterable so convert it to string previously
                any(str(user_oid) in str(doer['actioner_id']) for doer in task['actioners'])):

                # If delta_start <0 task not started, otherwise already started
                delta_start = date.today() - date.fromisoformat(task['startdate'])

                # If delta_end >0 task overdue, if <0 task in progress
                delta_end = date.today() - date.fromisoformat(task['enddate'])

                if delta_start.days == 0:
                    msg = msg + f"\nTask {task['id']} '{task['name']}' started today."
                elif delta_start.days > 0  and delta_end.days < 0:
                    msg = msg + f"\nTask {task['id']} '{task['name']}' is intermidiate. Due date is {task['enddate']}."
                elif delta_end.days == 0:
                    msg = msg + f"\nTask {task['id']}  '{task['name']}' must be completed today!"
                elif delta_start.days > 0 and delta_end.days > 0:                                       
                    msg = msg + f"\nTask {task['id']} '{task['name']}' is overdue! (had to be completed on {task['enddate']})"
                else:
                    # print(f"Future tasks as {task['id']} '{task['name']}' goes here")   
                    pass
        if msg:
            bot_msg = bot_msg + f"\nTasks assigned to @{actioner_username}:\n" + msg
        else:
            bot_msg = bot_msg + f"\nNo events for @{actioner_username} to inform for now."
    else:
        logger.error(f"Something wrong: user has id: {user_oid} but no tg_username in DB")
        bot_msg = f"Error occured while processing your query"
    return bot_msg


def get_worker_oid_from_db_by_tg_username(tg_username: str, db: Database):
    '''
    Search staff collection in DB for given telegram username and return DB-id.
    If something went wrong return None (should be checked on calling side)
    '''

    worker_id = None
  
    try:
        result = db.staff.find_one({'tg_username': tg_username})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if (result and type(result) == dict and 
            '_id' in result.keys() and result['_id']):
            worker_id = result['_id']

    return worker_id


def get_worker_oid_from_db_by_tg_id(tg_id, db: Database):
    '''
    Search staff collection in DB for given telegram id and return DB-id.
    If something went wrong return None (should be checked on calling side)
    '''

    worker_id = None
  
    try:
        result = db.staff.find_one({'tg_id': str(tg_id)})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if (result and type(result) == dict and 
            '_id' in result.keys() and result['_id']):
            worker_id = result['_id']

    return worker_id


def get_worker_tg_id_from_db_by_tg_username(tg_username: str, db: Database):
    '''
    Search staff collection in DB for given telegram username and return telegram-id.
    If something went wrong return None (should be checked on calling side)
    '''

    tg_id = None
    # DB = get_db()
  
    try:
        result = db.staff.find_one({'tg_username': tg_username})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if (result and type(result) == dict and 
            'tg_id' in result.keys() and result['tg_id']):
            tg_id = result['tg_id']
    return tg_id


def get_worker_tg_username_by_oid(user_oid: ObjectId, db: Database) -> str:
    """Search staff collection in DB for given ObjectId and return telegram username.
    If something went wrong return empty string (should be checked on calling side)"""

    tg_un = ''
    # DB = get_db()
  
    try:
        result = db.staff.find_one({'_id': user_oid})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if (result and type(result) == dict and 
            'tg_username' in result.keys()):
            tg_un = result['tg_username']
    return tg_un


def get_worker_tg_username_by_tg_id(tg_id: str, db: Database) -> str:
    '''
    Search staff collection in DB for given telegram id and return telegram username.
    If something went wrong return empty string (should be checked on calling side)
    '''
    tg_un = ''
    # DB = get_db()
  
    try:
        result = db.staff.find_one({'tg_id': tg_id})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if (result and type(result) == dict and
            'tg_username' in result.keys()):
            tg_un = result['tg_username']

    return tg_un


def is_db(db):
    try:
        db.command('ping')
    except (AttributeError, ServerSelectionTimeoutError) as e:
        logger.error(f"There was error getting DB: {e}")
        return False
    else:
        return True
    

def save_json(project: dict, PROJECTJSON: str) -> None:
    '''
    Saves project in JSON format and returns
    '''

    json_fh = open(PROJECTJSON, 'w', encoding='utf-8')
    bot_msg = json.dump(project, json_fh, ensure_ascii=False, indent=4)
    json_fh.close()

    return bot_msg
