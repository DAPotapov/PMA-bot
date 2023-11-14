# Project manager assistant telegram bot ([@PMA_sp_bot](https://t.me/PMA_sp_bot))

- [Project manager assistant telegram bot (@PMA\_sp\_bot)](#project-manager-assistant-telegram-bot-pma_sp_bot)
  - [Description](#description)
    - [What problem is the bot trying to solve?](#what-problem-is-the-bot-trying-to-solve)
    - [Constraints](#constraints)
    - [Functionality Description](#functionality-description)
      - [/help](#help)
      - [/start](#start)
      - [/feedback](#feedback)
      - [/download](#download)
      - [/upload](#upload)
      - [/stop](#stop)
      - [/status](#status)
      - [/settings](#settings)
    - [What's Under the Hood?](#whats-under-the-hood)
      - [app.py](#apppy)
      - [connectors.py](#connectorspy)
        - [compose\_tasks\_list](#compose_tasks_list)
        - [get\_tg\_un\_from\_gan\_resources](#get_tg_un_from_gan_resources)
        - [get\_tg\_un\_from\_xml\_resources](#get_tg_un_from_xml_resources)
        - [load\_gan](#load_gan)
        - [load\_json](#load_json)
        - [load\_xml](#load_xml)
        - [xml\_date\_conversion](#xml_date_conversion)
      - [helpers.py](#helperspy)
        - [add\_user\_id\_to\_db](#add_user_id_to_db)
        - [add\_user\_info\_to\_db](#add_user_info_to_db)
        - [add\_worker\_info\_to\_staff](#add_worker_info_to_staff)
        - [clean\_project\_title](#clean_project_title)
        - [get\_active\_project](#get_active_project)
        - [get\_assignees](#get_assignees)
        - [get\_db](#get_db)
        - [get\_job\_preset](#get_job_preset)
        - [get\_job\_preset\_dict](#get_job_preset_dict)
        - [get\_keyboard\_and\_msg](#get_keyboard_and_msg)
        - [get\_message\_and\_button\_for\_task](#get_message_and_button_for_task)
        - [get\_project\_by\_title](#get_project_by_title)
        - [get\_project\_team](#get_project_team)
        - [get\_projects\_and\_pms\_for\_user](#get_projects_and_pms_for_user)
        - [get\_status\_on\_project](#get_status_on_project)
        - [get\_worker\_oid\_from\_db\_by\_tg\_id](#get_worker_oid_from_db_by_tg_id)
        - [get\_worker\_oid\_from\_db\_by\_tg\_username](#get_worker_oid_from_db_by_tg_username)
        - [get\_worker\_tg\_id\_from\_db\_by\_tg\_username](#get_worker_tg_id_from_db_by_tg_username)
        - [get\_worker\_tg\_username\_by\_oid](#get_worker_tg_username_by_oid)
        - [get\_worker\_tg\_username\_by\_tg\_id](#get_worker_tg_username_by_tg_id)
        - [is\_db](#is_db)
    - [Data structure](#data-structure)
  - [Installation and usage](#installation-and-usage)

## Description

The purpose of this bot is to assist you, as a Project Manager (PM), in maintaining control over your project. It informs the PM about the current state of the provided project—detailing which tasks have started, which are approaching deadlines, approaching milestones, and tasks in an overdue state. Additionally, it keeps assignees informed about their tasks. An overview of the data structure can be found [here](#data-structure).  

### What problem is the bot trying to solve?  

The idea for this bot came to me as I reflected on my experience in project management and observed how different teams handled various projects. One of the most common issues was that a project team member, deeply engrossed in their current task, often forgot to keep track of the project schedule — especially when managing multiple projects simultaneously. While the Project Manager (PM) could bring attention to certain timelines, in practice, the PM's focus was typically consumed by "firefighting", addressing problems that arose constantly. As a result, the task of schedule monitoring was delegated to one of the project team members, diverting their attention from their primary responsibilities. Alternatively, creating a separate position and hiring someone for schedule monitoring would incur additional costs, contributing to an overall increase in project expenses.  
There are numerous software and services designed to address this problem, offering features to monitor project status and send task reminders. However, introducing a new software solution to a team accustomed to various applications and services can be challenging. Project Managers (PMs) would need to compel team members to install a specific app or register with a particular service, incurring both financial and time resources. This bot is designed to address such challenges. It is well-suited for teams that are:

- Organized for a specific project with a duration limited to its completion (e.g., teams consisting of freelancers, as organizations typically stick to a chosen software for the majority of their projects).
- Already using the Telegram messenger.

Additionally, this bot is suitable for anyone managing their own project, possessing project management skills, and disliking the idea of keeping MS Project (or any other tool) open continuously to monitor the schedule. Instead, it caters to those who prefer occasional notifications of deadlines and other crucial milestones in their project schedule.  

### Constraints

- The bot only functions when the MongoDB server is running.
- The bot must be aware of the user's Telegram ID to send messages, as per the limitation imposed by the Telegram API.
- The project file (GAN or XML) should include a custom field called 'tg_username,' containing actual Telegram usernames. Without this information, the bot cannot correlate task performers with Telegram users. It is crucial to note that users should not change or switch their usernames while using this bot, as it would render the bot's operation unpredictable. While it is possible for the Project Manager (PM) to collect Telegram IDs of project team members and store them in the project file instead of usernames, this approach is more challenging to implement and goes against the intended purpose of this bot, which is to simplify the PM's work.

### Functionality Description  

The bot has the following commands:

#### /help

Displays the bot's description and a list of available commands.  

#### /start

[Executes](#start_function) when a user adds the bot for the first time. It initiates the creation of a new project within the bot. The user is prompted for the project title and then asked to upload the project file. Currently, the bot supports the following project file formats: .gan ([GanttProject](https://www.ganttproject.biz])), .xml (MS Project), and .json (which can be downloaded using the [/download](#download) command within the bot).  
Things to Consider:  
There is no schedule verification when a file is uploaded. Primarily, this is because project management software (in which the file was created) typically performs this verification. Additionally, when a user uploads a file, they, as the Project Manager (PM), are the most interested party in ensuring the correctness of the schedule. It is not in their interest to make manual mistakes in the file.  
At the start, the bot generates three reminders:  
[**Day Before Reminder**](#day_before_update): This runs every day at a specified time (default is 16:00). It notifies the project team of tasks scheduled to start or end the following day and highlights upcoming milestones if the corresponding setting is enabled.  
[**Daily Morning Reminder**](#morning_update): This reminder is scheduled to run every day at a specified time (default is 10:00). It notifies the project team of tasks that are scheduled to start or end on the same day, tasks in progress, overdue tasks, and milestones (if the corresponding setting is enabled).  
[**Friday Update Reminder**](#file_update): This reminder was created in response to the first client's request. She emphasizes the importance of project team members updating project files in the cloud storage to ensure that colleagues are working with the latest information. By default, it runs at 15:00 on Fridays—late enough for the weekend to have started but early enough for project changes to accumulate until the end of the workday.  
The /start command can be called at any time during the bot's use.

#### /feedback

The **/feedback** command allows users to send messages to the developer (me) to report bugs, request features, or share positive feedback.  

#### /download

Allows users to download the active project as a .json file, enabling them to make corrections using a text editor.  

#### /upload

Enables users to upload a new schedule to the active project. The key distinction from the /start command is that the project's title, settings, and reminders remain unchanged, while only the schedule is replaced with the uploaded one.

#### /stop

This command stops the bot's work for the user and deletes all projects managed by the user as a Project Manager (PM). The bot requests confirmation before proceeding.

#### /status

For Project Managers (PMs), this command displays tasks that reach important dates, such as starting or ending on the current day, being overdue, or in an ongoing state. It also shows milestones. Each task or milestone is accompanied by a button to mark the event as completed, preventing further reminders.  
If the user is a project team member (not a PM), the command notifies them of tasks for which they are responsible and have reached important dates as described above.  

#### /settings

[Displays](#settings_function) the PM settings menu and allows the management of projects under the PM's control. The menu items include:

- "Change notification settings": Manages which notifications will be sent to the user. This includes the following options:  
  - "Allow status update in group chat": If turned on, the /status command will send information to the group chat if it's called within one. Otherwise, it sends information in a private chat. This setting is off by default.  
  - "Users get anounces about milestones": If turned on, regular team members will receive notifications not only for tasks but also for milestones. It is up to the PM to decide whether to divert the team's attention from specific tasks. This setting is off by default.  
  - "/status notify PM of all projects": If turned on, the PM will receive status updates on all their projects. Otherwise, they will only receive updates on the active project. This setting is off by default.

- "Manage projects": Lists all user projects with buttons for management. The active project can only be renamed. Inactive projects can be deleted or activated after confirmation.

- "Reminders settings": PMs can change the time and day of the week when each of the reminders created at the start should run. They can also toggle reminders on and off.

- "Transfer control over the active project to another user": Allows the PM to resign and delegate the management of the active project to other team members.

### What's Under the Hood?

The bot application consists of three modules:

[app.py](#apppy): The main part, which includes functions that implement bot commands and the core functionality.  
[connectors.py](#connectorspy): Functions to parse project files.  
[helpers.py](#helperspy): Other functions called from the main module.  

#### app.py  

This bot is created using the popular Python library: python-telegram-bot (PTB), which includes the telegram and telegram.ext modules.  
To store data about projects and participants, a NoSQL database, MongoDB 4.4, is utilized. The choice of version is influenced by hardware restrictions. The module pymongo is employed to access the database. Although I initially considered using SQLite, a familiar database, I opted to acquire new knowledge and develop skills in using a NoSQL database. The description of the data structure is provided [here](#data-structure).

Some other important modules for the bot's operation include:  

*json*: Used to save projects to a file.

*dotenv*: Enables access to environment variables, where sensitive information such as the bot token is stored.

*tempfile*: Aids in managing storage space using temporary files and folders during the execution of upload and download commands. This becomes particularly crucial when the bot is run on a paid server.

*logging*: Utilized for displaying and saving (for further investigation) errors that occur during the bot's operation.

*untangle*: Used for parsing project files. While .gan files are XML files, their structure differs from that used by MS Project. This module is user-friendly, and its objects have a clear structure.

Reminders are implemented using the Job class from the python-telegram-bot (PTB) module, which is an instance of the apscheduler module's job.Job class. While they are created using PTB methods, editing is done using apscheduler methods. The serialization, saving to the database, and loading after a bot restart (if it occurs) are handled by the PTB extension called ptbcontrib.ptb_jobstores.

On application start:

- It attempts to connect to the database using the [*get_db()*](#get_db) function from [helpers.py](#helperspy). If the connection fails, the application exits with an error message. This is a crucial point, as the bot cannot function without the ability to save and retrieve project data.

- On bot creation, the *post_init()* function is called, which manages the bot's command list, description, and name.  

The *main()* function creates handlers to bind commands with corresponding functions. A special type of handler, ConversationHandler from the PTB module, is used for commands that engage in a dialog with the user. This class is effective for implementing branching dialogues and menus.

Let's explore how it's implemented using the [/start](#start) command as an example. The entry point is the [/start](#start) command, intercepted by the CommandHandler, which calls the <a id="start_function">'start' function</a>. This function retrieves information about the user (project manager) for further storage in the database. The bot then sends a message to the user, asking them to name the project.

Functions within ConversationHandler should always return an integer value interpreted by the handler to determine the state in which the user's message should be channeled. In this case, the user sends a text message (project title), handled by handlers listed in a state equal to 0 (first level). There is only one handler, MessageHandler, which calls the next function in the start conversation if the user's message meets certain conditions: it is text, not a command, and not the word 'cancel'.

This handler invokes the function *'naming_project'*, which cleans the sent message from unnecessary elements (white spaces and new line characters) using the ['*clean_project_title*'](#clean_project_title) function from [helpers.py](#helperspy). It also limits the input to 128 characters to fit most titles comfortably. The function saves information about the project manager to the 'staff' collection of the database using ['*add_worker_info_to_staff*'](#add_worker_info_to_staff) function from [helpers.py](#helperspy). It then checks if a project with the same title is already present in the database for this user. If so, it asks the user to invent another title (returning the same state). Otherwise, it asks the user to send a project file and returns the next state value.

On the second level (state == 1), the user's message is again handled by MessageHandler, but this time it is expected to be a file. If not, the bot will ask again for a file. The function '*file_received*' is called on a file. This function sends the file pointer to *'extract_tasks_from_file'*, which identifies the file type by extension and sends its pointer to the corresponding function for tasks and project team extraction. Project team members are saved to the database on the spot, but the list of extracted tasks is returned. If it's empty (indicating the file wasn't processed), the bot will ask the user to send the correct file (returning the same state value). Only on success will the bot create 'jobs' for reminders using ['*schedule_jobs*'](#schedule_jobs). This function returns a dictionary with reminders' names as keys and their identifiers in the jobs collection in the database as values. These identifiers will be needed later to change the run time and days of the week.

After creating a project with added tasks and reminders, it is saved to the database. Other projects managed by the user (if any) are set as inactive. To facilitate the operational storage of data about the project manager (PM), project, and related variables and flags, the 'user_data' property of the 'context' class (from the PTB module) is used. This allows information to be built up incrementally and used in different functions without the need to transfer such information directly between them. This is especially important when using ConversationHandler because functions within it do not call each other directly.

After finishing, the function returns the constant 'END' (with a value of -1), built into ConversationHandler. Its purpose is to indicate that the next messages from the user should not be intercepted by ConversationHandler handlers of any state (except the entry point, of course).

In situations where a user sends a message that none of the handlers within ConversationHandler can intercept, the bot needs to inform the user that something unexpected was received, especially if the user attempts to run another command. Handling this issue at the function level would overly complicate all functions and the application itself. This is where fallbacks in ConversationHandler come into play.

Primaraly fallbacks in ConversationHandler handle commands that are intercepted here. Additionaly, text messages recieved on the second step of the dialogue (the first step is handled within state == 0) or the word 'cancel' is sent on the first step of the dialogue, then the '*start_ended*' function will be called. This function sends a message informing the user that the procedure was aborted and returns '-1' (the END constant) to ConversationHandler.

Commands [**'/feedback'**](#feedback), [**'/upload'**](#upload), and [**'/stop'**](#stop) are treated similarly (except that the latter uses CallbackqueryHandler, which will be described below), so there's no need to detail them here.

The ['/settings'](#settings) command leads to a multilevel menu consisting of buttons sent to the user. This is also implemented using ConversationHandler. The entry point for it is called the <a id="settings_function">*'settings_started'*</a> function. The menu should be shown only for project managers (PMs), so initially, there is a check to ensure the user is in control of one of the projects in the database. If not, the bot sends a relevant message, and the function [*'add_user_info_to_db'*](#add_user_info_to_db) is called. Its job is to add information about a user missing in the database. It searches for the user's Telegram username in the 'staff' collection in the database and, if found, fills empty fields for name and [Telegram ID](#constraints).

If the user is a PM, the function shows the first level of the menu using a special function [*'get_keyboard_and_msg'*](#get_keyboard_and_msg) from ['helpers.py'](#helperspy). The current menu level is stored in the value of a key 'level' in 'user_data' of the context class. To control which branch of the menu the user is in at any given moment, a 'branch' list is used. It stores the path to the current menu level. The function [*'get_keyboard_and_msg'*](#get_keyboard_and_msg) creates a 'keyboard,' meaning a list (of lists) of buttons of the InlineKeyboardButton class from the PTB module, for all menu levels. The menu structure is described [above](#settings), so in this section, I'll go into details of some menu items' realization. Menu branching is achieved using the match: case: construction (for levels) and nested match: case: constructions for branch choices.

Each case element prepares a common message text for the corresponding menu level (and branch) and a 'keyboard' with buttons for every menu item. These message and keyboard elements are then returned to the calling function and sent to the user. Some menus are predefined, such as the initial menu, while others, like the menu items 'projects management' and 'transfer control over project', are created using a loop on a list of projects obtained from the database (for the former). For the latter, buttons are created from a list of project team members obtained from the function [*'get_project_team'*](#get_project_team) in ['helpers.py'](#helperspy).

Each InlineKeyboardButton instance contains text, which is the text displayed on the button, and callback_data, a string value passed when a user presses the button. This value is intercepted by CallbackqueryHandler within ConversationHandler in a 'state' that is returned from the function that created this menu.

For example, in a menu like 'projects management', callback_data contains composite information: the action to perform on a project the user chose and the identifier of the project on which this action should be performed. In other places, simpler data is passed. In the ConversationHandler, CallbackqueryHandler recognizes the chosen action using built-in regex capabilities and calls the appropriate function. In that function, the project identifier is extracted from a string passed with callback_data. Using this identifier, the project is found in the database, and the chosen action is performed, such as updating the 'title' or 'active' fields or deleting the document of such a project from the 'projects' collection of the database.

Some menu items do not lead to another menu but expect a text message from the user. These include items for setting a new time for a reminder and a new set of weekdays for a reminder. While they are logically located on the same menu level, if they return the same 'state,' user messages from each of them will be collected by the same MessageHandler and sent to the same function. This would require implementing a complicated algorithm to distinguish whether user input is time or days of the week and then return to the corresponding menu branch. It is simpler to separate them initially by using separate 'states'. These 'states' have their own MessageHandlers that pass user input to the appropriate function for setting the new time or days of the week of the reminder.

The first function, '*reminder_time_setter*', processes the text sent by the user and attempts to separate it into hours and minutes using delimiters such as ":", ";", " ", "_", and "-". This approach aims to anticipate user mistakes and typos. At this point, the 'branch' list in 'user_data' stores the reminder name the user chose to modify as the last item. The function finds the corresponding identifier of the reminder in the 'reminders' dictionary of the 'project' dictionary stored in 'user_data' of the context. After that, the function retrieves the reminder job by this identifier from the 'scheduler' and calls the *reschedule* method on this job to set a new time. Other parameters of the job have to remain the same (like days of the week, timezone, and trigger type), so they are copied to variables before rescheduling.

The second function, 'reminder_days_setter', is similar. However, instead of time, names of days of the week are searched in the user's message.

At the end of each function, the user receives information about the results, and the appropriate menu is sent to them.

To go back one level in the menu, a universal function '*settings_back*' is utilized. It is called by pressing the 'Back' menu button via the appropriate CallbackQueryHandler. This function decreases the value of 'level' by 1 and removes the last item from the 'branch' list stored in 'user_data'. To exit the menu, the 'Finish' menu button is used, which calls a 'finish_settings' function. This function sends a goodbye message to the user and returns the END constant for the ConversationHandler to stop capturing user messages.

The command ['/status'](#status) calls the <a id="status_function">'status'</a> function. First, it retrieves the value of the 'inform_of_all_projects' parameter for the user. Then, it fetches all or just the active project in the user's control from the database. For each project it sends user a message with the project title for which information will be presented, then a loop is initiated to examine each task and call the ['*get_message_and_button_for_task*'](#get_message_and_button_for_task) function from [helpers.py](#helperspy) on it. If the task is worth mentioning, the function returns the corresponding message and a button labeled 'Mark as complete'. The callback_data of such a button represents a composite string, consisting of the word 'task,' the project identifier, and the task id delimited with an underscore. Pressing such a button is intercepted by CallbackQueryHandler with the keyword 'task' at the start. Then, the ['*set_task_accomplished*'](#set_task_accomplished) function is called.

The counter is incremented during the task-checking loop if a non-empty result is returned from the ['*get_message_and_button_for_task*'](#get_message_and_button_for_task) function. If the counter is equal to zero at the end of the loop, the user is informed that there is nothing to be aware of.

If there are no projects under the user's control, the database is searched for projects where the user participates as a performer. The search is done using the user's ObjectId obtained from the 'staff' collection of the database. For each found project, the ['*get_status_on_project*'](#get_status_on_project) function is called, which returns a message containing information about the project status for this user. This message is then sent to the user. If the user doesn't participate in any projects, the bot sends a message suggesting the user start one.

The <a id="set_task_accomplished">'set_task_accomplished'</a> function decomposes the string obtained from 'callback_data' into a project identifier and task id. Using these identifiers, the database record is updated by setting the value of the 'complete' key to 100. To ensure that the value has been updated, the function performs a check. Then, the bot sends a corresponding message to the user.

The <a id="schedule_jobs">'*schedule_jobs*'</a> function creates instances of the job class needed to run reminder [functions](#day_before_update) at predetermined moments in time using the 'run_daily' method. The times for reminders are obtained from global constants. The method's parameters allow associating the job with a certain user by their Telegram ID (PM in this case) and also storing additional information in the 'data' parameter. The bot stores a dictionary in 'data' containing the project title and, for clarity, the Telegram ID of the PM.

The <a id="day_before_update">'*day_before_update*'</a> reminder function works as follows:

It retrieves the project dictionary from the database using data stored in job.data. Then, in a loop, the project tasks are checked to satisfy the following conditions: the task is not completed, it doesn't include subtasks, and it isn't a milestone. For such tasks, the date is checked: if today's date is one day less than the start date of the task, the bot sends a message to the actioner(s) so they can get prepared. If today's date is one day less than the end date of the task, the bot sends a message to the actioner(s) to remind them to complete the task in time. Additionally, actioners get informed about milestones if the PM has configured the corresponding setting. These messages are also sent to the PM.

The <a id="morning_update">'*morning_update*'</a> reminder function works as follows:

It retrieves the project dictionary from the database using data stored in job.data. Then, it calls the function ['*get_project_team*'](#get_project_team) to obtain a list of project team members. For each of the members, the function ['*get_status_on_project*'](#get_status_on_project) is called, which is also used in the ['status'](#status_function) function. This function returns a message that the bot then sends to the current member of the project team.

The <a id="file_update">'*file_update*'</a> reminder function works as follows:

It retrieves the project dictionary from the database using data stored in job.data. Then, it calls the function ['*get_project_team*'](#get_project_team) to obtain a list of project team members. Afterward, it sends a message to every team member about the necessity of updating common project files.

The '*update_staff_on_message*' function is used to obtain missing information (such as name and Telegram ID) about project team members. It is triggered by a handler that intercepts text messages in a group chat. This restriction is made to minimize CPU time spent when using this bot on a paid server and to prevent conflicts with command handling. Additionally, functions that handle commands also gather missing information.

There is a flag called 'known' created in 'user_data' in the context for resource economy purposes. It is created (if it does not exist) at the start of this function with the default value 'False'. This flag indicates whether the function has attempted to add this user to the database yet. For this purpose, the function ['*add_user_info_to_db*'](#add_user_info_to_db) is called (from [helpers.py](#helperspy)). Even if the user was not added to the database (for example, if they are in a group chat but aren't present in project team members, such as a project curator or client), the flag will be set to True to avoid further attempts.

#### connectors.py

Both of the outer file formats (.gan and .xml) represent the [XML format](https://en.wikipedia.org/wiki/XML). MS Project .xml files contain a hierarchical structure of the project, including subsets of tasks, resources, assignments, and others not used by the bot currently. Tasks have a subset of properties, such as id, name, duration, and so on. This hierarchy is represented by nested tags, with values of properties stored between tags in a 'content' part. The nesting of subtasks is represented using properties like WBS, outline level, and outline number.

The .gan file of GanttProject also uses a hierarchy, where the project contains tasks, resources, allocations, and others, represented by tags. However, these are empty-element tags, and values are stored in attributes of tasks in the form of name–value pairs (e.g., id=”1”, duration=”0”, etc.). Nesting of subtasks is represented by nested tags.

Parsing these files slightly differs, and it needs to be separated into two functions: [load_xml](#load_xml) and [load_gan](#load_gan). Generally, they store project resources into a variable of the Element class (from the Untangle module). Then, the id of a 'tg_username' field of the file is remembered, which should contain the Telegram username of the project participant. Assignments (or allocations) are then stored in an Element-class variable.

After that, the function loops through resources and creates a dictionary that represents one of the project team members (actioners). This dictionary is then passed to the function [*‘add_worker_info_to_staff’*](#add_worker_info_to_staff), which saves it into the 'staff' collection of the database.

Then, tasks are looped through, with each transformed into a dictionary (see structure description [below](#data-structure)) with conversions if needed. For example, MS Project stores task duration in hours, which is excessive for the purpose of this bot. Additionally, codes of dependency types between tasks (predecessors and successors) differ in GanttProject. Due to nested tasks of the .gan project format, the function ['*compose_tasks_list*'](#compose_tasks_list) is used to handle them. It creates a task dictionary with the use of allocations and resources elements and adds this dictionary to a list. This function is recursive, so if a task contains a subtask, it calls itself on it. It returns a list of tasks.

Need to mention, if the function encounters something unexpected in the file structure at every step, it raises an exception (ValueError or AttributeError, depending on the case).  

##### compose_tasks_list

Creates tasks list from a task element of .gan file and its nested subtasks (if any), resources and allocations collections (elements of .gan file too). Raises AttributeError or ValueError errors if structure is not correct.

##### get_tg_un_from_gan_resources

Find telegram username in dictionary of resources (from .gan file) which corresponds provided id. Return None if nothing found. Should be controlled on calling side.  

##### get_tg_un_from_xml_resources

Find telegram username in dictionary of resources (from .xml file) which corresponds provided id. Return None if nothing found. Should be controlled on calling side.  

##### load_gan

This is a connector from GanttProject format (.gan) to inner format. Gets file pointer on input. Reads data from file. Validates and converts data to inner dict-list-dict.. format. Saves actioners to staff collection in DB. Returns list of tasks. Raises AttributeError and ValueError errors if project structure in a file is not correct.  

##### load_json

Loads JSON data from file into dictionary. This connector useful in case we downloaded JSON, manually made some changes, and upload it again to bot. Returns list of tasks of the project. Raises AttributeError and ValueError errors if project structure in a file is not correct.  

##### load_xml

Function to import from MS Project XML file Get file pointer and database instance on input. Validates and converts data to inner dict-list-dict.. format Saves actioners to staff collection in DB. Returns list of tasks. Raises AttributeError and ValueError errors if project structure in a file is not correct.  

##### xml_date_conversion

Convert Project dateTime format (2023-05-15T08:00:00) to inner date format (2023-05-15)  

#### helpers.py

##### add_user_id_to_db

Helper function to add telegram id of username provided to DB. Returns None if telegram username not found in staff collection, did't updated or something went wrong. Returns ObjectId if record updated  

##### add_user_info_to_db

Adds missing user info (telegram id and name) to DB Returns None if telegram username not found in staff collection, did't updated or something went wrong. Returns ObjectId if record updated  

##### add_worker_info_to_staff

Calls functions to check whether such worker exist in staff collection. Adds given worker to staff collection if not exist already. Fill empty fields in case worker already present in staff (for ex. PM is actioner in other project) Returns empty string if worker telegram id not found in staff collection. Return ObjectId as a string otherwise.  

##### clean_project_title

Clean title typed by user from unnecessary spaces and so on. Return string of refurbished title. If something went wrong raise value error to be managed on calling side.  

##### get_active_project

Gets active project (without tasks by default to save some memory) by given PM telegram id. And fixes if something not right: - makes one project active if there were not, - if more than one active: leave only one active. Returns empty dictionary if no projects found for user.  

##### get_assignees

Helper function for getting names and telegram usernames of person assigned to given task to insert in a bot message Returns string of the form: '@johntherevelator (John) and @judasofkerioth (Judas)' Also returns list of their telegram ids for bot to be able to send direct messages.  

##### get_db

Creates connection to mongo server and returns database instance. Raises exception if not succeed.  

##### get_job_preset

Returns current preset of job in text format to add to messages, based on preset dictionary. Returns empty string if subroutine returned empty dictionary.  

##### get_job_preset_dict

Helper function that returns dictionary of current reminder preset for given job id. Returns empty dict if nothing is found or error occured.  

##### get_keyboard_and_msg

Helper function to provide specific keyboard on different levels and branches of settings menu.  

##### get_message_and_button_for_task

Helper function to provide status update on task with a button (InlineKeyboardReplyMarkup to be sent) to mark such task as complete. Returns tuple of empty string and Nonetype object if task not worth mention.  

##### get_project_by_title

Get project from database by title for given telegram id of PM. Returns empty dict if nothing was found.  

##### get_project_team

Construct list of project team members by given id of project. Returns empty list if it is not possible to achieve or something went wrong.  

##### get_projects_and_pms_for_user

Function to get string of projects (and their PMs) where user participate as an actioner. Return empty string if nothing was found.  

##### get_status_on_project

Function composes message which contains status update on given project for given ObjectId of actioner. Returns composed message to be sent.  

##### get_worker_oid_from_db_by_tg_id

Search staff collection in DB for given telegram id and return ObjectId of found worker as a string. If something went wrong return empty string (should be checked on calling side).  

##### get_worker_oid_from_db_by_tg_username

Search staff collection in DB for given telegram username and returns ObjectId of found worker (as string). If something went wrong return empty string (should be checked on calling side).  

##### get_worker_tg_id_from_db_by_tg_username

Search staff collection in DB for given telegram username and return telegram-id of found worker. If something went wrong return empty string (should be checked on calling side).  

##### get_worker_tg_username_by_oid

Search staff collection in DB for given ObjectId and return telegram username. If something went wrong return empty string (should be checked on calling side)  

##### get_worker_tg_username_by_tg_id

Searches staff collection in DB for given telegram id and returns telegram username. If something went wrong return empty string (should be checked on calling side)  

##### is_db

Function to check is there a connection to DB. Return True if database reached, and False otherwise.  

### Data structure

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

## Installation and usage

1. Clone the repository.
2. Install the requirements.
3. Install MongoDB 4.4 if you don't have it yet: [MongoDB Installation Guide](https://www.mongodb.com/docs/v4.4/installation/)
4. Create a project with GanttProject or MS Project (or use your already created project). For MS Project: save the project in an XML format. You can also use the example project provided (`example.json`). It has JSON format and can be edited in a text editor. *Note: to use it, you should write actual Telegram usernames in the 'staff' dictionary.*
5. Run `app.py` in the way most suitable for you.

Feel free to contact me if you have any questions.
