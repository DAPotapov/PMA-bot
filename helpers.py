"""
Some helper functions to help main functions to manupulate with data
"""

import json
import logging
import pymongo
import os

from dotenv import load_dotenv
from telegram import User
from telegram.ext import ContextTypes
from urllib.parse import quote_plus

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def add_user_id_to_db(user: User):
    ''' 
    Helper function to add telegram id of username provided to DB. Returns ObjectId on success
    '''
    result = None
    DB = get_db()

    # Fill record with absent id with current one
    # For now I assume that users don't switch their usernames and such situation is force-major
    try:
        record = DB.staff.find_one({"tg_username": user.username}, {"tg_id": 1, "_id": 0})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if not record:
            result = DB.staff.update_one({"tg_username": user.username}, {"$set": {"tg_id": user.id}}).upserted_id
            if not result:
                logger.warning(f"Something went wrong while adding telegram id for telegram username {user.username}")

    return result


def add_worker_to_staff(worker):
    ''' 
    Calls functions to check whether such worker exist in staff collection. 
    Adds given worker to staff collection if not exist already.
    '''

    worker_id = None
    DB = get_db()

    if DB == None:
        logger.error(f"There was error getting DB.")
    else:

        # Check DB if worker already present via telegram id
        if worker['tg_id']:
            worker_id = get_worker_id_from_db_by_tg_id(worker['tg_id'])
        # Othervise via telegram username
        elif worker['tg_username']:
            worker_id = get_worker_id_from_db_by_tg_username(worker['tg_username'])
        else:
            raise ValueError(f"Not enough information about worker provided: neither tg_id nor tg_username. Provided dict:\n{worker}")
        
        if not worker_id:
            worker_id = DB.staff.insert_one(worker).inserted_id

    return worker_id


def get_worker_id_from_db_by_tg_username(tg_username: str):
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


def get_worker_id_from_db_by_tg_id(tg_id):
    '''
    Search staff collection in DB for given telegram id and return DB-id.
    If something went wrong return None (should be checked on calling side)
    '''

    worker_id = None
    DB = get_db()
  
    try:
        result = DB.staff.find_one({'tg_id': tg_id})
    except Exception as e:
        logger.error(f"There was error getting DB: {e}")
    else:
        if result:
            # print(f"result of searching db for username: {result['_id']}")
            worker_id = result['_id']
            # print(type(worker_id))

    return worker_id


def get_assignees(task: dict, actioners: dict):
    '''
    Helper function for getting names and telegram usernames
    of person assigned to given task to insert in a bot message
    Returns string of the form: '@johntherevelator (John) and @judasofkerioth (Judas)'
    Also returns list of their telegram ids
    # TODO refactor this to use DB
    '''

    people = ""
    user_ids = []
    for doer in task['actioners']:
        for member in actioners:
            # print(f"Doer: {type(doer['actioner_id'])} \t {type(member['id'])}")
            if doer['actioner_id'] == member['id']:                                                    
                if member['tg_id']:
                    user_ids.append(member['tg_id'])              
                if len(people) > 0:
                    people = people + "and @" + member['tg_username'] + " (" + member['name'] + ")"
                else:
                    people = f"{people}@{member['tg_username']} ({member['name']})"
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


def save_json(project: dict, PROJECTJSON: str) -> None:
    ''' 
    Saves project in JSON format and returns 
    '''

    json_fh = open(PROJECTJSON, 'w', encoding='utf-8')
    bot_msg = json.dump(project, json_fh, ensure_ascii=False, indent=4)
    json_fh.close()

    return bot_msg