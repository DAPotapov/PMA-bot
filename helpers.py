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
from telegram import User
from telegram.ext import ContextTypes
from urllib.parse import quote_plus

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def add_user_id_to_db(user: User, db: Database):
    ''' 
    Helper function to add telegram id of username provided to DB. 
    Returns None if telegram username not found in staff collection, did't updated or something went wrong.
    Returns ObjectId if record updated
    '''
    output = None
    # DB = get_db()
    # print(f"user is {user}")

    # Fill record with absent id with current one
    # For now I assume that users don't switch their usernames and such situation is force-major
    try:
        record = db.staff.find_one({"tg_username": user.username}, {"tg_id": 1})
        # print(f"record is {record}")
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:

        # TODO refactor such part in any other places where key error may occur, check in temp.py what is better
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
    try:
        db_user = db.staff.find_one({"tg_username": user.username})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:

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
    # DB = get_db()

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


def get_assignees(task: dict, db: Database):
    '''
    Helper function for getting names and telegram usernames
    of person assigned to given task to insert in a bot message
    Returns string of the form: '@johntherevelator (John) and @judasofkerioth (Judas)'
    Also returns list of their telegram ids for bot to be able to send direct messages
    '''

    people = ""
    user_ids = []
    # DB = get_db()

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


def get_projects_and_pms_for_user(user_oid: ObjectId, db: Database) -> str:
    ''' Function to get string of projects (and their PMs) where user participate as actioner '''
    
    projects_and_pms = ''
    # DB = get_db()
    try:
        projects = list(db.projects.find({"tasks.actioners": {"$elemMatch":{"actioner_id": user_oid}}}, {"title":1, "pm_tg_id":1, "_id":0}))
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
    # DB = get_db()
  
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
    # DB = get_db()

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
    # DB = get_db()
  
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
    # DB = get_db()
  
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
