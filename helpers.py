"""
Some helper functions to help main functions to manupulate with data
"""

import json

from telegram import User
from telegram.ext import ContextTypes


def add_user_id(user: User, project: dict):
    ''' 
    Helper function to add telegram id of username provided to project json
    '''

    # Remember telegram user id
    for actioner in project['actioners']:
        if actioner['tg_username'] == user.username:
            # This will overwrite existing id if present, but it should not be an issue
            actioner['tg_id'] = user.id
    return project


def get_assignees(task: dict, actioners: dict):
    '''
    Helper function for getting names and telegram usernames
    of person assigned to given task to insert in a bot message
    Returns string of the form: '@johntherevelator (John) and @judasofkerioth (Judas)'
    Also returns list of their telegram ids
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


def get_job_preset(reminder: str, user_id: int, projectname: str, context: ContextTypes.DEFAULT_TYPE):
    '''
    Helper function that returns current reminder preset for given user and project
    Return None if nothing is found or error occured
    '''
    
    preset = None

    # Look up a job associated with current PM and Project
    for job in context.job_queue.get_jobs_by_name(reminder):
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
                # pprint(preset)
                break
    return preset


def save_json(project: dict, PROJECTJSON: str) -> None:
    ''' 
    Saves project in JSON format and returns message about success of operation
    '''

    json_fh = open(PROJECTJSON, 'w', encoding='utf-8')
    bot_msg = json.dump(project, json_fh, ensure_ascii=False, indent=4)

    return bot_msg