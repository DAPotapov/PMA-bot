# PMA-bot

Project manager assistant telegram bot

## Description

The purpose of this bot is assist Project Manager to control schedule (via reminders) and completion of tasks.  
It should make free PM from sitting behind dashboard and looking who delaying which task, and which tasks should be done by now.  
Overview of data structure used for schedule is here:  

## Current state

Bot can inform user about purpose of each command.
Bot can recieve file from user. And inform user of file formats supported.  
Bot currently accept .gan (GanttProject) format and translate it to json format for inner use.
Bot can inform user about current status of schedule

## TODO

[ ] fixbug: last of children tasks rewrites its parent task (in load_gan)  
[ ] fully implement connector to json format  
[ ] make status command working for team members too  
[ ] ask if PM wants to rewrite project file if new uploaded
[ ] make bot persistent https://github.com/python-telegram-bot/python-telegram-bot/wiki/Making-your-bot-persistent  
[ ] Error handling: https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.error_handlers
[x] add example of json structure for project files and requirments for project files to README.  
[x] make export to json format with readable formatting  
[x] implement /help command  
[x] implement /status command  
[x] Make "hello world" type bot - learn how to connect app to telegram  

## Data structure

First of all: the project file sent to bot should contain field 'tg_username' containing telegram username for members of a project team. Resources obviously should be present in file and assigned to tasks for bot to work :)

```json
{
    "tasks": [
        {
            "id": 0,
            "name": "Common task",
            "startdate": "2023-05-15",
            "enddate": "2023-05-18",
            "duration": 3, # Business days
            "successors": [], 
            "milestone": false,
            "complete": 0, # should 0-100 indicate percentage of completion
            "curator": "", # for future purposes: if overseer role will be needed
            "basicplan_startdate": "2023-05-15",
            "basicplan_enddate": "2023-05-18",
            "include": [  # For common task in this list goes ids of included subtasks. 
                1,
                4,
                2
            ],
            "actioners": []
        },
        {
            "id": 1,
            "name": "First task",
            "startdate": "2023-05-08",
            "enddate": "2023-05-15",
            "duration": 5,
            "successors": [],
            "milestone": false,
            "complete": 100, # 100 means completed
            "curator": "",
            "basicplan_startdate": "2023-05-08",
            "basicplan_enddate": "2023-05-15",
            "include": [],
            "actioners": [  # Actioner (doer) of this task
                {
                    "actioner_id": 1,   # This is id of person in actioners list below
                    "nofeedback": false # This flag will store if person didn't respond on last reminder
                },                      # And will be used to inform PM that this task may lack of attention 
                {
                    "actioner_id": 2,   # It is better to decompose project to small task  
                    "nofeedback": false # which can be assigned to one doer, but some tasks (like moving furniture)
                }                       # need two or more people envolved
            ]
        },
        {
            "id": 4,
            "name": "Some milestone",
            "startdate": "2023-05-15",
            "enddate": "2023-05-15",
            "duration": 0, # Milestones have zero duration
            "successors": [ # Achiving this milestone means "successors" task started
                {
                    "id": 2, # id of such task
                    "depend_type": "2", # Type of dependency (see below)
                    "depend_offset": 0  # Offset in days from current task (negative number means its earlier in time)
                },
                {
                    "id": 5,
                    "depend_type": "2",
                    "depend_offset": 0
                }
            ],
            "milestone": true,
            "complete": 0,
            "curator": "",
            "basicplan_startdate": "2023-05-15",
            "basicplan_enddate": "2023-05-15",
            "include": [],
            "actioners": []
        },
        {
            "id": 2,
            "name": "Another task",
            "startdate": "2023-05-15",
            "enddate": "2023-05-18",
            "duration": 3,
            "successors": [
                {
                    "id": 5,
                    "depend_type": "3",
                    "depend_offset": 0
                }
            ],
            "milestone": false,
            "complete": 0,
            "curator": "",
            "basicplan_startdate": "2023-05-15",
            "basicplan_enddate": "2023-05-18",
            "include": [],
            "actioners": [
                {
                    "actioner_id": 0,
                    "nofeedback": false
                }
            ]
        },        
    ],
    "actioners": [
        {
            "id": "0",
            "name": "John",
            "email": "",
            "phone": "",
            "telegram_id": "some_user42" # Actually its telegram username
        },
        {
            "id": "1",
            "name": "Mark",
            "email": "",
            "phone": "",
            "telegram_id": "some_user666"
        }
    ]
}

```

Explanation of types of dependencies between tasks:  
1 - start-start (SS)  
2 - finish-start (FS)  
3 - finish-finish (FF)  
4 - start-finish (SF) - usually not used  
This types was inherited from GanttProject because of "duckling law" (it's format I started with)
