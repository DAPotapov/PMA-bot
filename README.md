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

[ ] make status command working for team members too  
[ ] fully implement connector to json format  
[ ] ask if PM wants to rewrite project file if new uploaded
[ ] make bot persistent https://github.com/python-telegram-bot/python-telegram-bot/wiki/Making-your-bot-persistent  
[ ] Error handling: https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.error_handlers
[x] fixbug: last of children tasks rewrites its parent task (in load_gan)  
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
            "WBS": "1", # Filled when project imported from MS Project, otherwise it's empty; bot not using it for now.
            "name": "Common task",
            "startdate": "2023-05-15",
            "enddate": "2023-05-18",
            "duration": 3, # Business days
            "predecessor": [], # Filled when project imported from MS Project, otherwise it's empty; bot not using it for now.
            "successors": [], 
            "milestone": false, # True if task is a milestone
            "complete": 0, # should 0-100 indicate percentage of completion
            "curator": "", # for future purposes - if overseer role will be needed
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
            "WBS": "",
            "name": "First task",
            "startdate": "2023-05-08",
            "enddate": "2023-05-15",
            "duration": 5,
            "predecessor": [],
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
            "WBS": "",
            "name": "Some milestone",
            "startdate": "2023-05-15",
            "enddate": "2023-05-15",
            "duration": 0, # Milestones have zero duration
            "predecessor": [],
            "successors": [ # Achiving this milestone means "successors" task started
                {
                    "id": 2, # id of such task
                    "depend_type": 1, # Type of dependency (see below)
                    "depend_offset": 0  # Offset in days from current task (negative number means its earlier in time)
                },
                {
                    "id": 5,
                    "depend_type": 1,
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
            "WBS": "",
            "name": "Another task",
            "startdate": "2023-05-15",
            "enddate": "2023-05-18",
            "duration": 3,
            "predecessor": [
                {
                    "id": 4,
                    "depend_type": 1,
                    "depend_offset": 0
                }
            ],
            "successors": [
                {
                    "id": 5,
                    "depend_type": 0,
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
            "tg_username": "some_user42", 
            "tg_id": 000000
        },
        {
            "id": "1",
            "name": "Mark",
            "email": "",
            "phone": "",
            "tg_username": "some_user666",
            "tg_id": 000000
        }
    ]
}

```

Explanation of values for types of dependencies between tasks ([see docs](https://learn.microsoft.com/en-us/office-project/xml-data-interchange/xml-schema-for-the-tasks-element?view=project-client-2016)):  
0=FF=Finish-finish,  
1=FS=Finish-start (most common),  
2=SF=Start-finish (least common),  
3=SS=Start-start
