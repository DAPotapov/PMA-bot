# Project manager assistant telegram bot

#### Description:

The purpose of this bot is assist Project Manager to control schedule (via reminders) and completion of tasks.  
It should make PM free from sitting behind dashboard and looking who delaying which task, and which tasks should be done by now.  
Overview of data structure used for schedule is [here](#data-structure)  

## Current state

Bot can inform user about purpose of each command.  
Bot can recieve file from user. And inform user of file formats supported.  
Bot currently accept .gan (GanttProject) format and MS Project XML and translate them to json format for inner use.  
Bot can inform PM about current status of schedule. Also it send notification to actioner assigned to that task.
Every day bot looks at schedule and sends notification to actioners about tasks that should start or have deadline tomorrow.  
Every day at the morning bot looks at schedule and sends notification to actioners about current status of schedule.  
Every friday bot reminds team members about necessity of updating shared project files (Customer requirement)  
PM can change settings of notifications: time to send reminders to actioners, turn them off and on, change days of week on which reminders should be sent.



## Data structure

First of all: the project file sent to bot should contain custom field 'tg_username' containing telegram username for members of a project team. Resources obviously should be present in file and assigned to tasks for bot to work :)


```json
"projects": [                           
    {
        "title": '',                    # Title of the project
        "active": True,                 # Flag that it's active project, can be only one for PM
        "pm_tg_id": '',                 # Telegram id of PM  
        "tg_chat_id": '',               # Group chat where project members discuss project will be stored here
        "reminders": {                  # Dict to store ids of apcheduler jobs for reminders
            "morning_update": id,                       
            "day_before_update": id,
            "friday_update": id,
        }
        "settings": {
            'ALLOW_POST_STATUS_TO_GROUP': False,        # This option controls 
                                                        # whether /status command from group chat 
                                                        # will send message to group chat or directly to user
            'INFORM_ACTIONERS_OF_MILESTONES': False,    # This option controls 
                                                        # whether participants will be informed 
                                                        # not only about tasks but about milestones too
        },
        "tasks": [
            {
                "id": 0,
                "WBS": "1",                             # Filled when project imported from MS Project,
                                                        # otherwise it's empty.
                "name": "Common task",
                "startdate": "2023-05-15",
                "enddate": "2023-05-18",
                "duration": 3,                          # Business days
                "predecessor": [],                      # Contains tasks prior to the current one 
                                                        # (filled when project imported from MS Project, 
                                                        # otherwise it's empty); 
                                                        # bot is not using it for now.
                "successors": [],                       # Tasks which follow after current
                "milestone": false,                     # True if task is a milestone
                "complete": 0,                          # Indicate percentage of completion (0-100)
                "basicplan_startdate": "2023-05-15",    # For future purpose: when postpone function
                "basicplan_enddate": "2023-05-18",      # will be developed
                "include": [                            # If task consist of subtasks, their ids go here
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
                "complete": 100,                        # 100 means completed
                "curator": "",
                "basicplan_startdate": "2023-05-08",
                "basicplan_enddate": "2023-05-15",
                "include": [],
                "actioners": [                          # List of actioners (doers) of this task:
                                                        # It is known that the best approach is 
                                                        # to decompose project to small tasks
                                                        # which can be assigned to only one person,
                                                        # but some tasks (e.g. to move furniture)
                                                        # need two or more people to be envolved
                    {
                        "actioner_id": "",              # This is id of person in staff collection below 
                                                        # (ObjectId stored as string)
                        "nofeedback": false             # For future purpose: this flag will store
                                                        # if person didn't respond on last reminder
                    },                                  # And will be used to inform PM that 
                                                        # this task may lack of attention 
                    {
                        "actioner_id": "",
                        "nofeedback": false
                }                                       
                ]
            },
            {
                "id": 4,
                "WBS": "",
                "name": "Some milestone",
                "startdate": "2023-05-15",
                "enddate": "2023-05-15",
                "duration": 0,                  # Milestones have zero duration
                "predecessor": [],
                "successors": [                 # Achiving this milestone means "successors" task started
                    {
                        "id": 2,                # id of such task
                        "depend_type": 1,       # Type of dependency (see below)
                        "depend_offset": 0      # Offset in days from current task (negative number 
                    },                          # means its earlier in time)
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
                        "actioner_id": "",
                        "nofeedback": false
                    }
                ]
            },        
        ],
    },
    "staff": [                      # Actioners are stored separately 
        {                           # If they were stored in tasks, 
                                    # then it will be a problem to write tg_id in each task
            "_id": ObjectId(),
            "name": "John",
            "email": "",
            "phone": "",
            "tg_username": "some_user42", 
            "tg_id": '000000',
            "account_type": 'free',                 # For future comercial use
            "settings": {
                'INFORM_OF_ALL_PROJECTS': False,    #  If set to True /status command will inform PM 
                                                    # about all his projects, otherwise   
            },                                      # only about active project  
        },
        {
            "_id": ObjectId(),
            "program_id": '',  
            "name": "Mark",
            "email": "",
            "phone": "",
            "tg_username": "some_user666",
            "tg_id": '000000',
            "account_type": 'free',
            "settings": {
                'INFORM_OF_ALL_PROJECTS': False,
            },
        },
    ]
]

```

Explanation of values for types of dependencies between tasks ([see docs](https://learn.microsoft.com/en-us/office-project/xml-data-interchange/xml-schema-for-the-tasks-element?view=project-client-2016)):  
0=FF=Finish-finish,  
1=FS=Finish-start (most common),  
2=SF=Start-finish (least common),  
3=SS=Start-start
