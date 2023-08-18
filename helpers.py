"""
Some helper functions to help main functions to manupulate with data
"""

import json
import logging
import pymongo
import os

from bson import ObjectId
from datetime import date
from dotenv import load_dotenv
from pprint import pprint
from telegram import User
from telegram.ext import ContextTypes
from urllib.parse import quote_plus

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def add_user_id_to_db(user: User):
    ''' 
    Helper function to add telegram id of username provided to DB. 
    Returns None if telegram username not found in staff collection, did't updated or something went wrong.
    Returns ObjectId if record updated
    TODO try to fill other fields as well - use standalone function
    '''
    output = None
    DB = get_db()
    print(f"user is {user}")

    # Fill record with absent id with current one
    # For now I assume that users don't switch their usernames and such situation is force-major
    try:
        record = DB.staff.find_one({"tg_username": user.username}, {"tg_id": 1})
        # print(f"record is {record}")
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:

        # TODO refactor such part in any other places where key error may occur
        if record and ('tg_id' in record.keys()) and not record['tg_id']:            

            # Remember: for update_one matched_count will not be more than one
            result = DB.staff.update_one({"tg_username": user.username}, {"$set": {"tg_id": str(user.id)}})
            if result.modified_count > 0:            
                output = record["_id"]

    return output


def add_worker_to_staff(worker: dict):
    ''' 
    Calls functions to check whether such worker exist in staff collection. 
    Adds given worker to staff collection if not exist already.
    # TODO because PM already added to DB before we get to know his contacts from 'resources' 
    (if he is in there) we should call here a function to update missing fields (and only them! 
    - so it will be universal function which can be called anywhere)
    Otherwise if  PM is actioner in other project such record will lack contact information
    '''

    worker_id = None
    DB = get_db()

    if DB == None:
        logger.error(f"There was error getting DB.")
    else:

        # Check DB if worker already present via telegram id
        if worker['tg_id']:
            worker_id = get_worker_oid_from_db_by_tg_id(worker['tg_id'])
        # Othervise via telegram username
        elif worker['tg_username']:
            worker_id = get_worker_oid_from_db_by_tg_username(worker['tg_username'])
        else:
            raise ValueError(f"Not enough information about worker provided: neither tg_id nor tg_username. Provided dict:\n{worker}")
        
        if not worker_id:
            worker_id = DB.staff.insert_one(worker).inserted_id

    return worker_id


def get_assignees(task: dict):
    '''
    Helper function for getting names and telegram usernames
    of person assigned to given task to insert in a bot message
    Returns string of the form: '@johntherevelator (John) and @judasofkerioth (Judas)'
    Also returns list of their telegram ids for bot to be able to send direct messages
    '''

    people = ""
    user_ids = []
    DB = get_db()

    try:
        staff = DB.staff.find()
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        # pprint(f"Staff dict: {staff}")
        if staff:
            for doer in task['actioners']:
                for member in staff:
                    # print(f"Doer: {type(doer['actioner_id'])} \t {type(member['_id'])}")
                    if doer['actioner_id'] == member['_id']:                                                    
                        if member['tg_id']:
                            user_ids.append(member['tg_id'])              
                        if len(people) > 0:
                            people = people + "and @" + member['tg_username'] + " (" + member['name'] + ")"
                        else:
                            people = f"{people}@{member['tg_username']} ({member['name']})"
        else:
            # Return nothing if something not right
            # raise ValueError(f"While proceding task {task} has found out that staff collection is empty.")
            logger.error(f"While proceding task {task} had found out that staff collection is empty.")

    return people, user_ids


def get_db():
    load_dotenv()
    BOT_NAME = os.environ.get('BOT_NAME')
    BOT_PASS = os.environ.get('BOT_PASS')

    # link to database
    # DB_URI = f"mongodb://{BOT_NAME}:{BOT_PASS}@localhost:27017/admin?retryWrites=true&w=majority"
    DB_NAME = os.environ.get("DB_NAME", "database")
    host = '127.0.0.1:27017'
    DB = None
    try:
        uri = "mongodb://%s:%s@%s" % (quote_plus(BOT_NAME), quote_plus(BOT_PASS), host)
        # client = pymongo.MongoClient(f"mongodb://{BOT_NAME}:{BOT_PASS}@localhost:27017/admin?retryWrites=true&w=majority")
        client = pymongo.MongoClient(uri)    
        DB = client[DB_NAME]
    except ConnectionError as e:
        logger.error(f"There is problem with connecting to db '{DB_NAME}': {e}")   
    except Exception as e:
        logger.error(f"Error occurred: {e}")
    return DB


def get_job_preset(job_id: str, context: ContextTypes.DEFAULT_TYPE):
    '''
    Helper function that returns current reminder preset for given job id
    Return None if nothing is found or error occured
    '''  
    preset = None

    job = context.job_queue.scheduler.get_job(job_id)
    # print(f"Got the job: {job}")
    try:
        hour = job.trigger.fields[job.trigger.FIELD_NAMES.index('hour')]
        minute = f"{job.trigger.fields[job.trigger.FIELD_NAMES.index('minute')]}"
    except:
        preset = None        
    else:
        if int(minute) < 10:
            time_preset = f"{hour}:0{minute}"
        else:
            time_preset = f"{hour}:{minute}"

        # Determine if job is on or off
        if job.next_run_time:
            state = 'ON'
        else:
            state = 'OFF'
        
        days_preset = job.trigger.fields[job.trigger.FIELD_NAMES.index('day_of_week')]
        preset = f"{state} {time_preset}, {days_preset}"
        # pprint(preset)        
    return preset


def get_project_team(project: dict):
    """
    Construct list of project team members.
    Returns None if it is not possible to achieve or something went wrong.
    """
    team = []
    
    DB = get_db()
  
    # Loop through project tasks and gather information about project team
    for task in project['tasks']:

        # Process only tasks with actioners
        if task['actioners']:
            for actioner in task['actioners']:

                # Proceed if such actioner not in team already
                if not any(str(actioner['actioner_id']) in str(member['_id']) for member in team):
                    try:
                        result = DB.staff.find_one({'_id': actioner['actioner_id']})
                    except Exception as e:
                        logger.error(f"There was error getting DB: {e}")
                    else:
                        if result:
                            team.append(result)
    
    if not team:
        logger.error(f"Maybe DB is corrupted: project '{project['title']}' (id: {project['_id']}) has no project team!")

    return team


def get_status_on_project(project: dict, user_oid: ObjectId) -> str:
    """
    Function compose message contains status update on given project for given tg_id
    """
    DB = get_db()

    bot_msg = f"Status of events for project '{project['title']}'"

    # Add PM username
    try:
        record = DB.staff.find_one({"tg_id": project['pm_tg_id']})
    except Exception as e:
        logger.error(f"Error happens while accessing DB for PM tg_id={project['pm_tg_id']} in staff collection: {e}")
        bot_msg = f"Error occured while processing your query"
    else:
        if record and record['tg_username']:
            project['tg_username'] = record['tg_username']
            bot_msg = bot_msg + f" (PM: @{project['tg_username']}):"
        else:
            logger.error(f"PM (with tg_id: {project['pm_tg_id']}) was not found in db.staff!")

        # Get user telegram username to add to message
        user = DB.staff.find_one({"_id": user_oid},{"tg_username":1, "_id": 0})
        if user and user['tg_username']:

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
                bot_msg = bot_msg + f"\nTasks assigned to @{user['tg_username']}:\n" + msg
            else:
                bot_msg = bot_msg + f"\nNo events for @{user['tg_username']} to inform for now."
        else:
            logger.error(f"Something wrong: user has id: {user_oid} but no tg_username in DB")
            bot_msg = f"Error occured while processing your query"
    return bot_msg


def get_worker_oid_from_db_by_tg_username(tg_username: str):
    '''
    Search staff collection in DB for given telegram username and return DB-id.
    If something went wrong return None (should be checked on calling side)
    '''

    worker_id = None
    DB = get_db()
  
    try:
        result = DB.staff.find_one({'tg_username': tg_username})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if result:
            # print(f"result of searching db for username: {result['_id']}")
            worker_id = result['_id']
            # print(type(worker_id))

    return worker_id


def get_worker_oid_from_db_by_tg_id(tg_id):
    '''
    Search staff collection in DB for given telegram id and return DB-id.
    If something went wrong return None (should be checked on calling side)
    '''

    worker_id = None
    DB = get_db()
  
    try:
        result = DB.staff.find_one({'tg_id': str(tg_id)})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if result:
            # print(f"result of searching db for username: {result['_id']}")
            worker_id = result['_id']
            # print(type(worker_id))

    return worker_id


def get_worker_tg_id_from_db_by_tg_username(tg_username: str):
    '''
    Search staff collection in DB for given telegram username and return DB-id.
    If something went wrong return None (should be checked on calling side)
    '''

    tg_id = None
    DB = get_db()
  
    try:
        result = DB.staff.find_one({'tg_username': tg_username})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if result:
            # print(f"result of searching db for username: {result['_id']}")
            tg_id = result['tg_id']
            # print(type(worker_id))

    return tg_id


def save_json(project: dict, PROJECTJSON: str) -> None:
    ''' 
    Saves project in JSON format and returns 
    '''

    json_fh = open(PROJECTJSON, 'w', encoding='utf-8')
    bot_msg = json.dump(project, json_fh, ensure_ascii=False, indent=4)
    json_fh.close()

    return bot_msg