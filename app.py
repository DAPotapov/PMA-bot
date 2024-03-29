# Based on
# https://gitlab.com/Athamaxy/telegram-bot-tutorial/-/blob/main/TutorialBot.py
# Structure:
# Imports
# Constants
# Sincronuous functions
# Async functions
# Settings part (functions for settings menu functionality)
# Post init
# Main function

import json
import logging
import os
import pymongo
import re
import sys
import tempfile

from bson import ObjectId
from connectors import load_gan, load_json, load_xml
from dotenv import load_dotenv
from datetime import datetime, date, time
from helpers import (
    add_user_id_to_db,
    add_user_info_to_db,
    add_worker_info_to_staff,
    clean_project_title,
    get_active_project,
    get_db,
    get_job_preset,
    get_keyboard_and_msg,
    get_message_and_button_for_task,
    get_project_by_title,
    get_project_team,
    get_projects_and_pms_for_user,
    get_status_on_project,
    get_worker_oid_from_db_by_tg_id,
    get_worker_oid_from_db_by_tg_username,
    is_db,
)
from pathlib import Path
from ptbcontrib.ptb_jobstores import PTBMongoDBJobStore
from pymongo.database import Database
from telegram import BotCommand, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)


# Configure logging
# logging.basicConfig(
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
# )
# Log to file in production stage
logging.basicConfig(filename=".data/log.log",
                    filemode='a',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Default values for daily reminders
MORNING = "10:00"
ONTHEEVE = "16:00"
FRIDAY = "15:00"

load_dotenv()
DEV_TG_ID = os.environ.get("DEV_TG_ID")
# Link to DB for storing jobs
BOT_NAME = os.environ.get("BOT_NAME")
BOT_PASS = os.environ.get("BOT_PASS")
DB_URI = (
    f"mongodb://{BOT_NAME}:{BOT_PASS}@localhost:27017/admin?retryWrites=true&w=majority"
)

# Make connection to database #
try:
    DB = get_db()
except ConnectionError as e:
    sys.exit(f"Couldn't connect to DB.\n {e}\nCan't work without it.")
except AttributeError as e:
    sys.exit(f"{e}")

# Set list of commands
help_cmd = BotCommand("help", "show commands with their description")
status_cmd = BotCommand("status", "information about current state of the project")
settings_cmd = BotCommand(
    "settings", "change bot parameters (works only in private chats)"
)
feedback_cmd = BotCommand("feedback", "send feedback to developer")
start_cmd = BotCommand("start", "starts this bot or new project")
stop_cmd = BotCommand("stop", "stops bot")
upload_cmd = BotCommand(
    "upload",
    "upload new schedule for active project "
    + "(e.g., if some tasks were rescheduled or actioner was replaced) "
    + "(works only in private chats)",
)
download_cmd = BotCommand("download", "download actual project file (in .json format for now)")

# States of settings menu:
FIRST_LVL, SECOND_LVL, THIRD_LVL, FOURTH_LVL, FIFTH_LVL, SIXTH_LVL, SEVENTH_LVL = range(
    7
)
# Callback data for settings menu
ONE, TWO, THREE = range(3)


def extract_tasks_from_file(fp: Path, db: Database) -> list[dict]:
    """
    Get file with project,
    determine supported type,
    call dedicated function to get list of tasks,
    return it to caller.
    Return empty list on error.
    """

    tasks = []

    # If file is known format:
    # call appropriate function with this file as argument
    # and expect project dictionary on return
    try:
        match fp.suffix:
            case ".gan":
                tasks = load_gan(fp, db)

            case ".json":
                tasks = load_json(fp, db)

            case ".xml":
                tasks = load_xml(fp, db)

            # else log what was tried to be loaded
            case _:
                logger.warning(f"Someone tried to load '{fp.suffix}' file.")
    except (AttributeError, IndexError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"{e}")
    finally:
        return tasks


async def day_before_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This reminder must be sent to all team members on
    the day before of the important dates:
    start of task, deadline, optionally milestones (according to setting).
    It executes form a job from a job_queue.
    """
    if (
        DB is not None
        and is_db(DB)
        and context.job
        and context.job.data
        and type(context.job.data) is dict
    ):
        project = get_project_by_title(
            DB, str(context.job.data["pm_tg_id"]), context.job.data["project_title"]
        )
        if project:
            # Find task to inform about and send message to users
            for task in project["tasks"]:
                bot_msg = (  # Also acts as flag that there is something to inform user of
                    ""
                )

                # If delta_start <0 task not started, otherwise already started
                delta_start = date.today() - date.fromisoformat(task["startdate"])

                # If delta_end >0 task overdue, if <0 task in progress
                delta_end = date.today() - date.fromisoformat(task["enddate"])

                # Inform about task if it starts or has a deadline tomorrow
                if (
                    task["complete"] < 100
                    and not task["include"]
                    and not task["milestone"]
                ):
                    if delta_start.days == -1:
                        bot_msg = (
                            f"🚥🛣Task №{task['id']} '<i>{task['name']}</i>' of"
                            f" '<b>{project['title']}</b>' (PM:"
                            f" @{project['tg_username']}) starts <u>tomorrow</u>."
                        )
                    elif delta_end.days == -1:
                        bot_msg = (
                            f"⏰⌛<u>Tomorrow</u> is deadline for task {task['id']} "
                            f"'<i>{task['name']}</i>' of '<b>{project['title']}</b>' "
                            f"(PM: @{project['tg_username']})!"
                        )

                # Inform about tomorrow milestone according to project's setting
                if (
                    project["settings"]["INFORM_ACTIONERS_OF_MILESTONES"]
                    and task["milestone"]
                    and delta_end.days == -1
                ):
                    bot_msg = (
                        f"🎌<u>Tomorrow</u> is the date of milestone {task['id']} "
                        f"'<i>{task['name']}</i>' of '<b>{project['title']}</b>' "
                        f"(PM: @{project['tg_username']})!"
                    )

                # If task worth talking, and tg_id could be found in staff and actioner not PM
                # (will be informed separately) then send message to actioner
                if bot_msg:
                    for actioner in task["actioners"]:
                        worker = DB.staff.find_one(
                            {"_id": actioner["actioner_id"]}, {"tg_id": 1, "_id": 0}
                        )
                        if (
                            worker
                            and type(worker) is dict
                            and "tg_id" in worker.keys()
                            and worker["tg_id"]
                            and worker["tg_id"] != project["pm_tg_id"]
                        ):
                            await context.bot.send_message(
                                worker["tg_id"], bot_msg, parse_mode="HTML"
                            )

                    # And inform PM
                    await context.bot.send_message(
                        project["pm_tg_id"], bot_msg, parse_mode="HTML"
                    )
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        logger.error("Error occured while accessing database.")
        await context.bot.send_message(context.job.data["pm_tg_id"], bot_msg)  # type: ignore


async def download(update: Update, context: CallbackContext):
    """
    Let user download (updated) active project.
    First of all: in json format.
    """

    # Check if user is PM and remember what project to update
    if DB is not None and is_db(DB):
        # Get whole active project for user as PM
        project = get_active_project(
            str(update.effective_user.id), DB, include_tasks=True
        )
        if project:
            # Get project team for this project
            staff = get_project_team(project["_id"], DB)

            # This approach will be useful in future development
            # when this function become conversation with multiple choice
            # Store project with staff in it in user_data in context
            context.user_data["project"] = project
            if staff:
                context.user_data["project"]["staff"] = staff

            # Save to json using temporary file to save space and provide it to user
            with tempfile.NamedTemporaryFile(
                mode="w+t", encoding="utf-8", prefix="project_", suffix=".json"
            ) as fp:
                json.dump(
                    context.user_data["project"], fp, ensure_ascii=False, indent=4
                )
                fp.seek(0)
                await update.message.reply_document(
                    document=fp.name, caption="Here is your project file:"
                )

        # If user is not PM at least add his id in DB
        # (if his telegram username is there)
        else:
            if update.effective_user:  # silence pylance
                add_user_info_to_db(update.effective_user, DB)
            bot_msg = "To download a project file you should /start a project first."
            await update.message.reply_text(bot_msg)
            return ConversationHandler.END
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        logger.error("Error occured while accessing database.")
        await context.bot.send_message(update.effective_user.id, bot_msg)
        return ConversationHandler.END


async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    First step of feedback dialog with user
    """
    bot_msg = (
        "What would you like inform developer about? "
        "Bugs, comments and suggestions highly appreciated."
    )
    await update.message.reply_text(bot_msg)
    return FIRST_LVL


async def feedback_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Get feedback provided by user, log it,
    send to depeloper and answer to user
    """

    msg = (
        "FEEDBACK from"
        f" {update.message.from_user.username} ({update.message.from_user.id}):"
        f" {update.message.text}"
    )
    logger.warning(msg)
    bot_msg = "Feedback sent to developer."
    await update.message.reply_text(bot_msg)

    # Send message to developer
    if DEV_TG_ID:
        await context.bot.send_message(DEV_TG_ID, msg)
    return ConversationHandler.END


async def feedback_aborted(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fallback function for feedback command"""

    bot_msg = "Feedback aborted."
    await update.message.reply_text(bot_msg)
    return ConversationHandler.END


async def file_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function is a reminder for team members
    that common files should be updated in the end of the week.
    It executes form a job from a job_queue.
    """

    if DB is not None and is_db(DB):
        project = get_project_by_title(
            DB,
            str(context.job.data["pm_tg_id"]),  # type: ignore
            context.job.data["project_title"],  # type: ignore
        )
        if project:
            team = get_project_team(project["_id"], DB)
            if team:
                for member in team:
                    if member["tg_id"]:
                        bot_msg = (
                            f"💾💻{member['name']}, remember to update common files "
                            f"for project '<b>{project['title']}</b>'!\n"
                            "Other team members should have actual information!"
                        )
                        await context.bot.send_message(
                            member["tg_id"], bot_msg, parse_mode="HTML"
                        )
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        logger.error("Error occured while accessing database.")
        await context.bot.send_message(context.job.data["pm_tg_id"], bot_msg)  # type: ignore


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function handles /help command.
    Shows description and available commands to user.
    """
    # Get description and send to user
    bot_description = await context.bot.getMyDescription()
    bot_msg = bot_description.description
    await update.message.reply_text(bot_msg)

    bot_commands = await context.bot.getMyCommands()

    # Build message about commands not repeating /help command
    bot_msg = ""
    for command in bot_commands:
        bot_msg = f"/{command.command} - {command.description}\n" + bot_msg

    await update.message.reply_text(bot_msg)


async def morning_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This reminder will be executed on daily basis to control project(s) schedule.
    It executes form a job from a job_queue.
    """

    if DB is not None and is_db(DB):
        project = get_project_by_title(
            DB,
            str(context.job.data["pm_tg_id"]),  # type: ignore
            context.job.data["project_title"],  # type: ignore
        )
        if project:
            # Get project team to inform
            team = get_project_team(project["_id"], DB)
            if team:
                # For each member (except PM) compose status update on project and send
                for member in team:
                    if (
                        member["tg_id"] and
                        member["tg_id"] != str(context.job.data["pm_tg_id"])  # type: ignore
                    ):
                        bot_msg = get_status_on_project(project, member["_id"], DB)
                        await context.bot.send_message(
                            member["tg_id"], bot_msg, parse_mode="HTML"
                        )

            # If no team inform only PM about such situation
            else:
                bot_msg = (
                    "Project has no team or something is wrong with database - "
                    "contact developer."
                )
                await context.bot.send_message(
                    str(context.job.data["pm_tg_id"]), bot_msg  # type: ignore
                )

            # Make status update with buttons for PM
            bot_msg = (
                f"Morning status update for project "
                f"'<b>{context.job.data['project_title']}</b>':"  # type: ignore
            )
            await context.bot.send_message(
                str(context.job.data["pm_tg_id"]),  # type: ignore
                bot_msg,
                parse_mode="HTML",
            )
            task_counter = 0
            for task in project["tasks"]:
                task_counter += 1
                bot_msg, reply_markup = get_message_and_button_for_task(
                    task, project["_id"], DB
                )
                if bot_msg and reply_markup:
                    await context.bot.send_message(
                        str(context.job.data["pm_tg_id"]),  # type: ignore
                        bot_msg,
                        reply_markup=reply_markup,  # type: ignore
                        parse_mode="HTML",
                    )
            if task_counter == 0:
                bot_msg = "Seems like there are no events to inform about at this time."
                await context.bot.send_message(
                    str(context.job.data["pm_tg_id"]), bot_msg  # type: ignore
                )

    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        logger.error("Error occured while accessing database.")
        await context.bot.send_message(context.job.data["pm_tg_id"], bot_msg)  # type: ignore


async def set_task_accomplished(update: Update, context: CallbackContext):
    """
    Function to mark task accomplished when corresponding
    button pressed during output of /status command
    """
    bot_msg = "Unsuccessful"
    query = update.callback_query
    await query.answer()

    # Prepare data to find
    if query and query.data:
        data = query.data.split("_", 2)
        project_to_find = ObjectId(data[1])
        task_to_find = int(data[2])

        # Update the database: set completeness of task to 100%
        if is_db(DB):
            project = DB.projects.find_one_and_update(
                {"_id": project_to_find},  # search for project is here
                {"$set": {"tasks.$[elem].complete": 100}},
                # Below we choose which element of array to update
                array_filters=[{"elem.id": task_to_find}],
                return_document=pymongo.ReturnDocument.AFTER,
                # Below we set which fields of document to show
                projection={
                    "title": 1,
                    "tasks": {
                        # and select first and only element of array which satisfy condition
                        "$elemMatch": {"id": task_to_find}
                    },
                },
            )
            if (
                project
                and "tasks" in project.keys()
                and project["tasks"]
                and "name" in project["tasks"][0].keys()
                and "complete" in project["tasks"][0].keys()
                and project["tasks"][0]["complete"] == 100
            ):
                bot_msg = (
                    f"Task №{project['tasks'][0]['id']} "
                    f"'<i>{project['tasks'][0]['name']}</i>' marked completed🏁. "
                    "Congratulations! 🎉🍾"
                )

        # Send message
        await query.edit_message_text(bot_msg, parse_mode="HTML")


"""
################# START section
"""


async def start(update: Update, context: CallbackContext) -> int:
    """
    Function to handle /start command - first step
    """

    # Collect information about PM
    pm = {
        "name": update.effective_user.first_name,
        "email": "",
        "phone": "",
        "tg_username": update.effective_user.username,
        "tg_id": str(update.effective_user.id),
        "account_type": "free",
        "settings": {
            "INFORM_OF_ALL_PROJECTS": False,
        },
    }

    # Store information about PM in context
    context.user_data["PM"] = pm

    disclaimer = (
        "❕<i>Disclaimer: All data provided by the user, "
        "which may be considered personal data within the scope of applicable law, "
        "is used exclusively for the purposes for which this software is intended "
        "and is not passed on to third parties.</i>"
    )
    await update.message.reply_text(disclaimer, parse_mode="HTML")

    bot_msg = (
        f"Hello, <b>{update.effective_user.first_name}</b>!\n"
        "You are starting a new project.\n"
        "Provide a name for it (less than 128 characters).\n"
        "(type '<u>cancel</u>' if you changed you mind during this process)"
    )
    await update.message.reply_text(bot_msg, parse_mode="HTML")
    return FIRST_LVL


async def naming_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Function for recognizing name of the project
    Second step of /start command
    """

    # Try to clean project title from unnecessary symbols and if not succeed give him another try.
    try:
        title = clean_project_title(str(update.message.text))  # to silence type error
    except ValueError as e:
        bot_msg = f"Title is not very suitable for human reading. {e}"
        await update.message.reply_text(bot_msg)
        return FIRST_LVL
    else:
        project = {
            "title": title,
            "active": True,
            "pm_tg_id": str(context.user_data["PM"]["tg_id"]),
            # group chat where project members discuss project will be stored here
            "tg_chat_id": "",
            "settings": {
                "ALLOW_POST_STATUS_TO_GROUP": False,
                "INFORM_ACTIONERS_OF_MILESTONES": False,
            },
            "reminders": {},
            "tasks": [],
        }

        # Add project data to dictionary in user_data.
        # One start = one project. But better keep PM and project separated,
        # because they could be written to DB separately
        context.user_data["project"] = project

        # Check and add PM to staff
        if DB is not None and is_db(DB):
            pm_oid = ""
            try:
                pm_oid = add_worker_info_to_staff(context.user_data["PM"], DB)
            except ValueError as e:
                bot_msg = f"{e}"
                await update.message.reply_text(bot_msg)
                return ConversationHandler.END
            if not pm_oid:
                bot_msg = (
                    "There is a problem with database connection. "
                    "Contact developer or try later."
                )
                await update.message.reply_text(bot_msg)
                return ConversationHandler.END
            else:
                prj_id = DB.projects.find_one(
                    {
                        "title": project["title"],
                        "pm_tg_id": str(context.user_data["PM"]["tg_id"]),
                    },
                    {"_id": 1},
                )
                if (
                    prj_id
                    and type(prj_id) is dict
                    and "_id" in prj_id.keys()
                    and prj_id["_id"]
                ):
                    bot_msg = (
                        "You've already started project with name"
                        f" <b>{project['title']}</b>. Try another one."
                    )
                    await update.message.reply_text(bot_msg, parse_mode="HTML")
                    return FIRST_LVL
                else:
                    bot_msg = (
                        f"Title was refurbushed to: '<b>{title}</b>'.\nYou can change"
                        " it later in /settings.\nNow you can upload your project"
                        " file. Supported formats are: <u>.gan</u> (GanttProject),"
                        " <u>.json</u>, <u>.xml</u> (MS Project)"
                    )
                    await update.message.reply_text(bot_msg, parse_mode="HTML")
                    return SECOND_LVL
        else:
            logger.error("Error occured while accessing database.")
            bot_msg = (
                "Error occured while accessing database. "
                "Try again later or contact developer."
            )
            await context.bot.send_message(context.job.data["pm_tg_id"], bot_msg)  # type: ignore
            return ConversationHandler.END


async def file_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Function to proceed uploaded file and saving to DB
    Third step of /start command
    """

    # Get file and save it as temp
    with tempfile.TemporaryDirectory() as tdp:
        gotfile = await context.bot.get_file(update.message.document)  # type: ignore
        fp = await gotfile.download_to_drive(
            os.path.join(tdp, update.message.document.file_name)  # type: ignore
        )

        # Call function which converts given file to dictionary
        # and add actioners to staff collection
        tasks = extract_tasks_from_file(fp, DB)
        if tasks:
            bot_msg = "File parsed successfully."

            # Add tasks to user data dictionary in context
            context.user_data["project"]["tasks"] = tasks

            # Schedule jobs and store corresponding ids in project dict
            context.user_data["project"]["reminders"] = schedule_jobs(context)
            if not context.user_data["project"]["reminders"]:
                bot_msg = bot_msg + "\nCouldn't create reminders. Contact developer."
                logger.error(
                    "Couldn't create reminders for project"
                    f" '{context.user_data['project']}'"
                )
            else:
                bot_msg = (
                    bot_msg
                    + "\nReminders were created: on the day before event"
                    f" (<i>{ONTHEEVE}</i>), in the morning of event"
                    f" (<i>{MORNING}</i>) and reminder for friday file update"
                    f" (<i>{FRIDAY}</i>). You can change them or turn off in"
                    " /settings.\nAlso you can update the schedule by uploading new"
                    " file via /upload command.\nRemember that you can /start a new"
                    " project anytime."
                )

            # Save project to DB
            if is_db(DB):
                prj_oid = DB.projects.insert_one(context.user_data["project"])

                # If succeed make other projects inactive
                if prj_oid and prj_oid.inserted_id:
                    bot_msg = (
                        bot_msg
                        + "\nProject added to database.\nProject initialization"
                        " complete."
                    )

                    # Since new project added successfully and it's active,
                    # lets make other projects inactive (actually there should be just one,
                    # but just in case)
                    prj_count = DB.projects.count_documents(
                        {
                            "pm_tg_id": str(context.user_data["PM"]["tg_id"]),
                            "title": {"$ne": context.user_data["project"]["title"]},
                        }
                    )
                    if prj_count > 0:
                        result = DB.projects.update_many(
                            {
                                "pm_tg_id": str(context.user_data["PM"]["tg_id"]),
                                "title": {"$ne": context.user_data["project"]["title"]},
                            },
                            {"$set": {"active": False}},
                        )

                        # If other project didn't switched to inactive state end conversation
                        # and log error,
                        # because later bot wouldn't comprehend which project to use
                        if result.acknowledged and result.modified_count == 0:
                            logger.error(
                                "Error making project inactive when user"
                                f" '{update.effective_user.id}' project"
                                f" '{context.user_data['project']['title']}'"
                            )
                            bot_msg = (
                                bot_msg
                                + "Attempt to update database was unsuccessful. Records"
                                " maybe corrupted. Contact developer or try later."
                            )

            else:
                bot_msg = (
                    bot_msg
                    + "There is a problem with database connection. Contact developer"
                    " or try later."
                )
                logger.error("Error occured while accessing database.")

        # If provided file couldn't be processed let user try again
        else:
            logger.warning(
                f"User '{update.effective_user.id}' tried to upload unsupported file:"
                f" '{update.message.document.file_name}'"
            )
            bot_msg = (
                "Couldn't process given file.\nSupported formats are: <u>.gan</u>"
                " (GanttProject), <u>.json</u>, <u>.xml</u> (MS Project)\nMake sure"
                " these files contain custom field named '<i>tg_username</i>', which"
                " store usernames of project team members.\nIf you would like to see"
                " other formats supported feel free to message bot developer via"
                " /feedback command.\nTry upload another one."
            )
            await update.message.reply_text(bot_msg, parse_mode="HTML")
            return SECOND_LVL

        await update.message.reply_text(bot_msg, parse_mode="HTML")
        return ConversationHandler.END


async def start_ended(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fallback function of /start command"""

    bot_msg = "Procedure of starting new project aborted."
    logger.warning(
        f"User: {update.message.from_user.username} ({update.message.from_user.id})"
        f" wrote: {update.message.text}"
    )
    await update.message.reply_text(bot_msg)
    return ConversationHandler.END


def schedule_jobs(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """
    Schedule jobs for main reminders.
    Return empty dictionary if not succeded.
    """

    morning_update_job = None
    day_before_update_job = None
    file_update_job = None

    # Construct additinal information to store in job.data
    # to be available when job runs
    data = {
        "project_title": context.user_data["project"]["title"],
        "pm_tg_id": str(context.user_data["PM"]["tg_id"]),
    }

    """ From docs: To persistence to work job must have explicit ID
        and 'replace_existing' must be True
        or a new copy of the job will be created
        every time application restarts! """
    job_kwargs = {"replace_existing": True}

    # Use default values from constants for time
    try:
        hour, minute = map(int, MORNING.split(":"))
        time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError as e:
        logger.error(f"Error while parsing time: {e}")

    # Set job schedule
    else:
        # Create job with configured parameters
        morning_update_job = context.job_queue.run_daily(
            morning_update,
            user_id=int(context.user_data["PM"]["tg_id"]),
            time=time2check,
            data=data,
            job_kwargs=job_kwargs,
        )

        # and enable it.
        morning_update_job.enabled = True

    # 2nd - daily on the eve of task reminder
    try:
        hour, minute = map(int, ONTHEEVE.split(":"))
        time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError as e:
        logger.error(f"Error while parsing time: {e}")

    # Add job to queue and enable it
    else:
        day_before_update_job = context.job_queue.run_daily(
            day_before_update,
            user_id=int(context.user_data["PM"]["tg_id"]),
            time=time2check,
            data=data,
            job_kwargs=job_kwargs,
        )
        day_before_update_job.enabled = True

    # Register friday reminder
    try:
        hour, minute = map(int, FRIDAY.split(":"))
        time2check = time(hour, minute, tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError as e:
        logger.error(f"Error while parsing time: {e}")

    # Add job to queue and enable it
    else:
        file_update_job = context.job_queue.run_daily(
            file_update,
            user_id=int(context.user_data["PM"]["tg_id"]),
            time=time2check,
            days=(5,),
            data=data,
            job_kwargs=job_kwargs,
        )
        file_update_job.enabled = True

    # Check if jobs created and make output dictionary
    if morning_update_job and day_before_update_job and file_update_job:
        return {
            "morning_update": morning_update_job.id,
            "day_before_update": day_before_update_job.id,
            "friday_update": file_update_job.id,
        }
    else:
        return {}


""" ######### END OF START SECTION ########### """


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function handles /status command.
    And informs user about important dates.
    """
    # Dummy message
    bot_msg = "Should print status to user"

    user_id = str(update.effective_user.id)
    user_name = update.effective_user.username

    # Read setting for effective user if there is connection to database
    if DB is not None and is_db(DB):
        pm = DB.staff.find_one(
            {"tg_username": user_name}, {"settings.INFORM_OF_ALL_PROJECTS": 1, "_id": 0}
        )
        if pm and type(pm) is dict and "settings" in pm.keys() and pm["settings"]:
            # Get 'list' of projects, which depending on preset consists of one project or many
            # Cursor object never None, so cast it to list first
            if pm["settings"]["INFORM_OF_ALL_PROJECTS"]:
                projects = list(DB.projects.find({"pm_tg_id": user_id}))
            else:
                projects = list(DB.projects.find({"pm_tg_id": user_id, "active": True}))

            if projects:
                # Iterate through list
                for project in projects:
                    bot_msg = (
                        f"Status of events for project '<b>{project['title']}</b>':"
                    )
                    if (
                        project["settings"]["ALLOW_POST_STATUS_TO_GROUP"]
                        and update.message.chat_id != update.effective_user.id
                    ):
                        await update.message.reply_text(bot_msg, parse_mode="HTML")
                    else:
                        await context.bot.send_message(
                            user_id, bot_msg, parse_mode="HTML"
                        )

                    # Lets keep track of messages sent to user about tasks
                    task_counter = 0

                    # Find task to inform about
                    for task in project["tasks"]:
                        # Get information from dedicated function
                        bot_msg, reply_markup = get_message_and_button_for_task(
                            task, project["_id"], DB
                        )
                        if bot_msg and reply_markup:
                            task_counter += 1

                            # Check current setting and chat where update came from to decide
                            # where to send answer
                            if (
                                project["settings"]["ALLOW_POST_STATUS_TO_GROUP"]
                                and update.message.chat_id != update.effective_user.id
                            ):
                                await update.message.reply_text(
                                    bot_msg, parse_mode="HTML"
                                )
                            else:
                                # Buttons should be send only in direct message to PM
                                await context.bot.send_message(
                                    user_id,
                                    bot_msg,
                                    reply_markup=reply_markup,
                                    parse_mode="HTML",
                                )
                    if task_counter == 0:
                        bot_msg = (
                            "Seems like there are no events to inform about at this"
                            " time."
                        )
                        # Check current setting and chat where update came from to decide
                        # where to send answer
                        if (
                            project["settings"]["ALLOW_POST_STATUS_TO_GROUP"]
                            and update.message.chat_id != update.effective_user.id
                        ):
                            await update.message.reply_text(bot_msg, parse_mode="HTML")
                        else:
                            await context.bot.send_message(
                                user_id, bot_msg, parse_mode="HTML"
                            )

            else:
                # If current user not found in project managers
                # then just search him by his ObjectId in all records and inform about events
                # if nothing found - Suggest him to start a project
                user_oid = get_worker_oid_from_db_by_tg_id(user_id, DB)
                if not user_oid and user_name:
                    user_oid = get_worker_oid_from_db_by_tg_username(user_name, DB)
                if not user_oid:
                    bot_msg = (
                        "No information found about you in database.\n"
                        "If you think it's a mistake contact your project manager.\n"
                        "Or consider to /start a new project by yourself."
                    )
                    await context.bot.send_message(user_id, bot_msg)
                else:
                    # Add his id to DB since there is none
                    if update.effective_user:  # silence pylance
                        add_user_id_to_db(update.effective_user, DB)

                    # Get all documents where user mentioned,
                    # cast cursor object to list to check if smth returned
                    projects = list(
                        DB.projects.find(
                            {
                                "tasks.actioners": {
                                    "$elemMatch": {"actioner_id": user_oid}
                                }
                            }
                        )
                    )

                    # If documents was found where user mentioned then loop them
                    # and collect status update for user
                    if projects:
                        for project in projects:
                            # Compose message from tasks of the project and send to user
                            bot_msg = get_status_on_project(project, user_oid, DB)
                            await context.bot.send_message(
                                user_id, bot_msg, parse_mode="HTML"
                            )

                    # Inform user if he is in staff, but not in any project participants
                    else:
                        bot_msg = (
                            "Seems like you don't participate in any project.\nIf you"
                            " think it's a mistake contact your project manager.\nOr"
                            " consider to /start a new project by yourself."
                        )
                        await context.bot.send_message(user_id, bot_msg)
        else:
            bot_msg = (
                "Seems like you don't participate in any project.\n"
                "If you think it's a mistake contact your project manager.\n"
                "Or consider to /start a new project by yourself."
            )
            await context.bot.send_message(user_id, bot_msg)
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        logger.error("Error occured while accessing database.")
        await context.bot.send_message(user_id, bot_msg)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry function to stop the bot.
    Checks if bot can be stopped for user.
    Asks confirmation if it is.
    """

    bot_msg = ""

    # Check if user is PM, if not it is not for him to decide about reminders of project events
    if DB is not None and is_db(DB):
        docs_count = DB.projects.count_documents(
            {"pm_tg_id": str(update.effective_user.id)}
        )
        if docs_count > 0:
            bot_msg = (
                "🛑 Are you sure? This will <b>delete all of your projects</b> from"
                " bot.🛑\nYou can disable reminders in /settings if they are bothering"
                " you (but this will made bot pointless)"
            )
            keyboard = [
                [
                    InlineKeyboardButton(
                        "Yes, delete all, I could start again any moment",
                        callback_data=str(ONE),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "No, I want to keep data and bot running",
                        callback_data=str(TWO),
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                update.effective_user.id,
                bot_msg,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return FIRST_LVL
        else:
            # If he is an actioner
            user_oid = get_worker_oid_from_db_by_tg_id(
                str(update.effective_user.id), DB
            )
            projects_count = 0
            if user_oid:
                projects_count = DB.projects.count_documents(
                    {"tasks.actioners": {"$elemMatch": {"actioner_id": user_oid}}}
                )
                if projects_count > 0:
                    # Collect names of projects with their PMs tg_username to contact
                    projects_with_PMs = get_projects_and_pms_for_user(user_oid, DB)
                    if projects_with_PMs:
                        bot_msg = (
                            "I'm afraid I can't stop informing you of events of other"
                            f" people's projects: {projects_with_PMs}"
                        )
                    else:
                        bot_msg = (
                            "I'm afraid I can't stop informing you of events of other"
                            " people's projects."
                        )
                        logger.warning(
                            "Couldn't gather information about projects and PMs where"
                            f" user {update.effective_user.id} participate"
                        )

            # If he don't participate in any project - be quiet
            if not user_oid or projects_count == 0:
                bot_msg = "Bot stopped"
            await context.bot.send_message(
                update.effective_user.id, bot_msg, parse_mode="HTML"
            )
            return ConversationHandler.END
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        logger.error("Error occured while accessing database.")
        await context.bot.send_message(
            update.effective_user.id, bot_msg, parse_mode="HTML"
        )
        return ConversationHandler.END


async def stopping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Second step of stopping bot.
    Delete all user's projects and jobs
    """

    # Find all jobs for current user and remove them
    if DB is not None and is_db(DB):
        for project in DB.projects.find({"pm_tg_id": str(update.effective_user.id)}):
            for id in project["reminders"].values():
                context.job_queue.scheduler.get_job(id).remove()

        # Delete all projects for current user.
        # I don't see necessity for checking result of operation for now.
        result = DB.projects.delete_many(  # noqa: F841
            {"pm_tg_id": str(update.effective_user.id)}
        )

        bot_msg = "Projects deleted. Reminders too. Bot stopped."
        await context.bot.send_message(update.effective_user.id, bot_msg)
        return ConversationHandler.END
    else:
        logger.error("Error occured while accessing database.")
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        await context.bot.send_message(context.job.data["pm_tg_id"], bot_msg)  # type: ignore
        return ConversationHandler.END


async def stop_aborted(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fallback function for bot stopping"""
    bot_msg = "Stopping bot aborted."
    await context.bot.send_message(update.effective_user.id, bot_msg)
    return ConversationHandler.END


async def update_staff_on_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Function to update staff collection with ids to be able contact users later.
    """

    # Check if update caused by user and his info was not updated in database yet
    if update.effective_user:
        if "known" not in context.user_data.keys():
            context.user_data["known"] = False
        if context.user_data["known"] is False:
            result = add_user_info_to_db(update.effective_user, DB)
            if not result:
                logger.debug(
                    f"User id ({update.effective_user.id}) of"
                    f" {update.effective_user.username} was not added to DB (maybe"
                    " already present)."
                )
            context.user_data["known"] = True


async def upload(update: Update, context: CallbackContext) -> int:
    """
    Entry point of conversation of uploading new project file
    """

    # Check if user is PM and remember what project to update
    if DB is not None and is_db(DB):
        project = get_active_project(str(update.effective_user.id), DB)
        if project:
            context.user_data["project"] = project

            # Message to return to user
            bot_msg = (
                f"This function will replace existing schedule for '{project['title']}'"
                " project. Reminders will not change.\nIf you are sure just upload"
                " file with new schedule.\nIf you changed your mind press a button"
            )
            cancel_btn = InlineKeyboardButton("Cancel", callback_data=str(ONE))
            kbd = InlineKeyboardMarkup([[cancel_btn]])
            await update.message.reply_text(bot_msg, reply_markup=kbd)
            return FIRST_LVL

        # If user is not PM at least add his id in DB (if his telegram username is there)
        else:
            if update.effective_user:  # silence pylance
                add_user_info_to_db(update.effective_user, DB)
            bot_msg = (
                "Change in project can be made only after starting one: use /start"
                " command to start a project."
            )
            await update.message.reply_text(bot_msg)
            return ConversationHandler.END
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        logger.error("Error occured while accessing database.")
        await context.bot.send_message(update.effective_user.id, bot_msg)
        return ConversationHandler.END


async def upload_file_recieved(update: Update, context: CallbackContext) -> int:
    """
    Function to proceed uploaded new project file
    and update corresponding record in DB.
    Second and final step of /upload command.
    """

    with tempfile.TemporaryDirectory() as tdp:
        gotfile = await context.bot.get_file(update.message.document)
        fp = await gotfile.download_to_drive(
            os.path.join(tdp, update.message.document.file_name)  # type: ignore
            )

        # Call function which converts given file to dictionary
        # and add actioners to staff collection
        tasks = extract_tasks_from_file(fp, DB)
        if tasks:
            bot_msg = "File parsed successfully."

            # Update tasks in active project
            if is_db(DB):
                result = DB.projects.update_one(
                    {
                        "pm_tg_id": str(update.effective_user.id),
                        "title": context.user_data["project"]["title"],
                    },
                    {"$set": {"tasks": tasks}},
                )
                if result.matched_count > 0:
                    if result.modified_count > 0:
                        bot_msg = bot_msg + "\nProject schedule updated successfully."
                    else:
                        bot_msg = (
                            bot_msg
                            + "\nProject schedule is same as existing, didn't updated."
                        )
                else:
                    bot_msg = (
                        bot_msg
                        + "\nSomething went wrong while updating project schedule."
                    )
                    logger.warning(
                        f"Project {context.user_data['project']['title']} was not found"
                        "                                 for user"
                        f" {str(update.effective_user.id)} during update, but was found"
                        " on previous step."
                    )

                # End on success
                await update.message.reply_text(bot_msg)
                return ConversationHandler.END
            else:
                logger.error("Error occured while accessing database.")
                bot_msg = (
                    "Error occured while accessing database. Try again later or contact"
                    " developer."
                )
                await context.bot.send_message(
                    context.job.data["pm_tg_id"],  # type: ignore
                    bot_msg
                    )
                return ConversationHandler.END

        else:
            bot_msg = (
                "Couldn't process given file.\nSupported formats are: <u>.gan</u>"
                " (GanttProject), <u>.json</u>, <u>.xml</u> (MS Project)\nMake sure these files"
                " contain custom field named '<i>tg_username</i>', which store usernames of"
                " project team members.\nIf you would like to see other formats"
                " supported feel free to message bot developer via /feedback"
                " command.\nTry upload another one."
            )
            await update.message.reply_text(bot_msg, parse_mode="HTML")
            return FIRST_LVL


async def upload_ended(update: Update, context: CallbackContext) -> int:
    """Fallback function for /upload command conversation"""
    bot_msg = "Upload aborted"
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(bot_msg)
    elif update.message:
        await update.message.reply_text(bot_msg)
    return ConversationHandler.END


""" ### This part contains functions which make SETTINGS menu functionality ### """


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    This function handles /settings command, entry point for menu
    """

    # Check if current user is acknowledged PM
    # then proceed otherwise suggest to start a new project
    if DB is not None and is_db(DB):
        # Let's control which level of settings we are at any given moment
        context.user_data["level"] = FIRST_LVL
        project = get_active_project(str(update.message.from_user.id), DB)
        if not project:
            # If user is not PM at least add his id in DB (if his telegram username is there)
            if update.effective_user:
                add_user_info_to_db(update.effective_user, DB)
            bot_msg = (
                "Settings available after starting a project: "
                "use /start command for a new one."
            )
            await update.message.reply_text(bot_msg)
            return ConversationHandler.END
        else:
            context.user_data["project"] = project
            keyboard, bot_msg = get_keyboard_and_msg(
                DB,
                context.user_data["level"],
                str(update.message.from_user.id),
                context.user_data["project"],
            )
            if not keyboard and not bot_msg:
                bot_msg = "Some error happened. Unable to show a menu."
                await update.message.reply_text(bot_msg)
            else:
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(bot_msg, reply_markup=reply_markup)
            return context.user_data["level"]
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        logger.error("Error occured while accessing database.")
        await context.bot.send_message(update.effective_user.id, bot_msg)
        return ConversationHandler.END


async def settings_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menu option 'Back'. Handles return to previous menu level"""

    query = update.callback_query
    await query.answer()
    bot_msg = ""

    # We can return back only if we are not on 1st level
    if context.user_data["level"] > 0:
        context.user_data["level"] = context.user_data["level"] - 1
        context.user_data["branch"].pop()

    # Make keyboard appropriate to a level we are returning to
    if "branch" in context.user_data.keys() and context.user_data["branch"]:
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
            context.user_data["branch"][-1],
        )
    else:
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
        )

    # Call function which create keyboard and generate message to send to user.
    # End conversation if that was unsuccessful.
    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return context.user_data["level"]


async def finish_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Function to handle 'finish' button.
    Endpoint of /settings conversation.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Settings done. You can do something else now.")
    return ConversationHandler.END


async def settings_aborted(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Fallback function of /settings conversation
    """

    bot_msg = "Settings function aborted."
    logger.warning(
        f"User: {update.message.from_user.username} ({update.message.from_user.id})"
        f" wrote: {update.message.text} in settings function."
    )
    await update.message.reply_text(bot_msg)
    return ConversationHandler.END


async def second_lvl_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Function to control second level menu.
    Shows second level menu according to button pressed on 1st level.
    """

    query = update.callback_query
    await query.answer()

    # Call function which create keyboard and generate message to send to user.
    # End conversation if that was unsuccessful.
    if query.data:
        context.user_data["level"] += 1
        if "branch" not in context.user_data:  # type: ignore
            context.user_data["branch"] = []
        context.user_data["branch"].append(query.data)
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
            context.user_data["branch"][-1],
        )
    else:
        # Stay on same level
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
        )

    # Check if we have message and keyboard and show them to user
    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await query.edit_message_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return context.user_data["level"]


""" REMINDERS BRANCH """


async def allow_status_to_group(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Switch for menu option 'Allow status update in group chat'"""

    query = update.callback_query
    await query.answer()

    # Switch parameter in context
    context.user_data["project"]["settings"]["ALLOW_POST_STATUS_TO_GROUP"] = (
        False
        if context.user_data["project"]["settings"]["ALLOW_POST_STATUS_TO_GROUP"]
        else True
    )

    # Update DB. No need to check for success, let app proceed
    if is_db(DB):
        DB.projects.update_one(
            {
                "pm_tg_id": str(update.effective_user.id),
                "title": context.user_data["project"]["title"],
            },
            {
                "$set": {
                    "settings.ALLOW_POST_STATUS_TO_GROUP": context.user_data["project"][
                        "settings"
                    ]["ALLOW_POST_STATUS_TO_GROUP"]
                }
            },
        )
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        await context.bot.send_message(update.effective_user.id, bot_msg)
        return ConversationHandler.END

    # Call function which create keyboard and generate message to send to user.
    # End conversation if that was unsuccessful.
    keyboard, bot_msg = get_keyboard_and_msg(
        DB,
        context.user_data["level"],
        str(update.effective_user.id),
        context.user_data["project"],
        context.user_data["branch"][-1],
    )
    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
    return context.user_data["level"]


async def milestones_anounce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Switch for menu option 'Users get anounces about milestones'"""
    query = update.callback_query
    await query.answer()

    # Switch parameter in context
    context.user_data["project"]["settings"]["INFORM_ACTIONERS_OF_MILESTONES"] = (
        False
        if context.user_data["project"]["settings"]["INFORM_ACTIONERS_OF_MILESTONES"]
        else True
    )

    # No need to check for success, let app proceed
    if is_db(DB):
        DB.projects.update_one(
            {
                "pm_tg_id": str(update.effective_user.id),
                "title": context.user_data["project"]["title"],
            },
            {
                "$set": {
                    "settings.INFORM_ACTIONERS_OF_MILESTONES": context.user_data[
                        "project"
                    ]["settings"]["INFORM_ACTIONERS_OF_MILESTONES"]
                }
            },
        )
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        await context.bot.send_message(update.effective_user.id, bot_msg)
        return ConversationHandler.END

    # Call function which create keyboard and generate message to send to user.
    # End conversation if that was unsuccessful.
    keyboard, bot_msg = get_keyboard_and_msg(
        DB,
        context.user_data["level"],
        str(update.effective_user.id),
        context.user_data["project"],
        context.user_data["branch"][-1],
    )
    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
    return context.user_data["level"]


async def notify_of_all_projects(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Switch for menu option '/status command notify PM of all projects (not only active)'"""
    query = update.callback_query
    await query.answer()

    # Read parameter and switch it
    if is_db(DB):
        result = DB.staff.find_one(
            {"tg_id": str(update.effective_user.id)},
            {"settings.INFORM_OF_ALL_PROJECTS": 1, "_id": 0},
        )
        if (
            result
            and type(result) is dict
            and "settings" in result.keys()
            and result["settings"]
        ):
            INFORM_OF_ALL_PROJECTS = result["settings"]["INFORM_OF_ALL_PROJECTS"]
            INFORM_OF_ALL_PROJECTS = False if INFORM_OF_ALL_PROJECTS else True

            # No need to check for success, let app proceed
            DB.staff.update_one(
                {"tg_id": str(update.effective_user.id)},
                {"$set": {"settings.INFORM_OF_ALL_PROJECTS": INFORM_OF_ALL_PROJECTS}},
            )
    else:
        bot_msg = (
            "Error occured while accessing database. Try again later or contact"
            " developer."
        )
        await context.bot.send_message(update.effective_user.id, bot_msg)
        return ConversationHandler.END

    # Call function which create keyboard and generate message to send to user.
    # End conversation if that was unsuccessful.
    keyboard, bot_msg = get_keyboard_and_msg(
        DB,
        context.user_data["level"],
        str(update.effective_user.id),
        context.user_data["project"],
        context.user_data["branch"][-1],
    )
    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return context.user_data["level"]


""" TRANSFER CONTROL BRANCH """


async def transfer_control(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Change ownership of current project to given telegram user (id)"""

    query = update.callback_query
    await query.answer()

    # Write to DB new owner of project and update corresponding jobs
    # Send message to user and
    # End conversation because only PM should change settings but current user isn't a PM already
    if query and "data" in dir(query) and query.data:
        if DB is not None and is_db(DB):
            # Check if reciever has other projects, and deactivate given project if so
            new_pm_projects_count = DB.projects.count_documents(
                {"pm_tg_id": query.data}
            )
            if new_pm_projects_count == 0:
                result = DB.projects.update_one(
                    {
                        "pm_tg_id": str(update.effective_user.id),
                        "title": context.user_data["project"]["title"],
                    },
                    {"$set": {"pm_tg_id": query.data}},
                )
            else:
                result = DB.projects.update_one(
                    {
                        "pm_tg_id": str(update.effective_user.id),
                        "title": context.user_data["project"]["title"],
                    },
                    {"$set": {"pm_tg_id": query.data, "active": False}},
                )

            if result.matched_count > 0 and result.modified_count > 0:
                # On success update corresponding jobs
                reminders = DB.projects.find_one(
                    {
                        "title": context.user_data["project"]["title"],
                        "pm_tg_id": query.data,
                    },
                    {"reminders": 1, "_id": 0},
                )
                if (
                    reminders
                    and type(reminders) is dict
                    and "reminders" in reminders.keys()
                    and reminders["reminders"]
                ):
                    for id in reminders["reminders"].values():
                        job = context.job_queue.scheduler.get_job(id)
                        if job:
                            args = job.args
                            args[0].data["pm_tg_id"] = query.data
                            job = job.modify(args=args)

                # Make other project active for former PM,
                # First check if he has other projects
                # Then make sure he has no other active projects (just in case)
                # Replace project stored in context with one from database
                former_pm_projects_count = DB.projects.count_documents(
                    {"pm_tg_id": context.user_data["project"]["pm_tg_id"]}
                )
                activated = {}
                if former_pm_projects_count > 0:
                    count_active = DB.projects.count_documents(
                        {
                            "pm_tg_id": context.user_data["project"]["pm_tg_id"],
                            "active": True,
                        }
                    )
                    if count_active == 0:
                        activated = DB.projects.find_one_and_update(
                            {"pm_tg_id": context.user_data["project"]["pm_tg_id"]},
                            {"$set": {"active": True}},
                            {"tasks": 0},
                        )
                    else:
                        activated = DB.projects.find_one(
                            {
                                "pm_tg_id": context.user_data["project"]["pm_tg_id"],
                                "active": True,
                            },
                            {"tasks": 0},
                        )
                context.user_data["old_title"] = context.user_data["project"]["title"]
                context.user_data["project"] = activated
                bot_msg = (
                    "You successfuly transfered control over project"
                    f" '{context.user_data['old_title']}'."
                )
                if activated and "title" in activated.keys() and activated["title"]:
                    bot_msg = (
                        bot_msg
                        + f"\nProject '{activated['title']}' activated. You can change"
                        " it in /settings."
                    )
                else:
                    bot_msg = bot_msg + "\nYou can /start a new project now."

                # Inform reciever that he is in control now
                msg = (
                    f"@{update.effective_user.username} delegated management "
                    f"of the project '{context.user_data['old_title']}' to you.\n"
                )
                msg = (
                    msg + "You can activate it in /settings."
                    if new_pm_projects_count > 0
                    else msg + "You can check its /status."
                )
                msg = msg + "\nTo learn other functions use /help."

                await context.bot.send_message(query.data, msg)

            else:
                bot_msg = (
                    "Something went wrong while transfering control to choosen project"
                    " team member. Contact developer to check the logs."
                )
                logger.error(
                    "Couldn't change PM in project"
                    f" '{context.user_data['project']['title']}' from"
                    f" '{context.user_data['project']['pm_tg_id']}' to '{query.data}'"
                )
        else:
            bot_msg = (
                "Error occured while accessing database. Try again later or contact"
                " developer."
            )
            logger.error("Error occured while accessing database.")
        await query.edit_message_text(bot_msg)
        return ConversationHandler.END
    else:
        # If callback data absent somehow - return to same level
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
            context.user_data["branch"][-1],
        )

        # Check if we have message and keyboard and show them to user
        if not keyboard and not bot_msg:
            bot_msg = "Some error happened. Unable to show a menu."
            await query.edit_message_text(bot_msg)
            return ConversationHandler.END
        else:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(bot_msg, reply_markup=reply_markup)
            return context.user_data["level"]


""" PROJECTS CONTROL BRANCH """


async def project_activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Menu option to activate choosen project and deactivate current project.
    Replaces current project in context.
    Work as switch and return keyboard with projects.
    """
    query = update.callback_query
    await query.answer()
    msg = ""

    # Таке oid of the project from query
    if query.data:
        if is_db(DB):
            new_active_oid = ObjectId(query.data.split("_", 1)[1])

            # Make current project inactive
            make_inactive = DB.projects.update_one(
                {
                    "title": context.user_data["project"]["title"],
                    "pm_tg_id": str(update.effective_user.id),
                },
                {"$set": {"active": False}},
            )
            if make_inactive.modified_count > 0:
                # Make project with received oid active
                # and store updated record in context (w\o tasks)
                new_active = DB.projects.find_one_and_update(
                    {"_id": new_active_oid},
                    {"$set": {"active": True}},
                    projection={"tasks": 0},
                    return_document=pymongo.ReturnDocument.AFTER,
                )
                if new_active:
                    context.user_data["project"] = new_active
                    msg = f"Project '{new_active['title']}' is active project now."
                else:
                    msg = "Couldn't activate choosen project"
                    logger.error(msg)
            else:
                msg = (
                    f"Couldn't set project '{context.user_data['project']['title']}'"
                    " inactive"
                )
                logger.error(msg)
        else:
            bot_msg = (
                "Error occured while accessing database. Try again later or contact"
                " developer."
            )
            logger.error("Error occured while accessing database.")
    else:
        msg = "Query data is empty when get to activate project function"
        logger.error(msg)

    # Return to same level
    keyboard, bot_msg = get_keyboard_and_msg(
        DB,
        context.user_data["level"],
        str(update.effective_user.id),
        context.user_data["project"],
        context.user_data["branch"][-1],
    )

    # Check if we have message and keyboard and show them to user
    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await query.edit_message_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        if msg:
            bot_msg = msg + "\n" + bot_msg
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return context.user_data["level"]


async def project_delete_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Function handles press of button 'Delete {project title}'.
    Asks for confirmation.
    """
    query = update.callback_query
    await query.answer()

    if query.data:
        context.user_data["oid_to_delete"] = ObjectId(query.data.split("_", 1)[1])
        context.user_data["title_to_delete"] = ""
        context.user_data["level"] += 1
        context.user_data["branch"].append(query.data.split("_", 1)[0])
        # Get title of the project to delete to show to the user
        if is_db(DB):
            title = DB.projects.find_one(
                {"_id": context.user_data["oid_to_delete"]}, {"title": 1, "_id": 0}
            )
            if (
                title
                and type(title) is dict
                and "title" in title.keys()
                and title["title"]
            ):
                context.user_data["title_to_delete"] = title["title"]

        # Show confirmation keyboard
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
            context.user_data["branch"][-1],
        )

        # Check if we have message and keyboard and show them to user
        if not keyboard and not bot_msg:
            bot_msg = "Some error happened. Unable to show a menu."
            await query.edit_message_text(bot_msg)
            return ConversationHandler.END
        else:
            reply_markup = InlineKeyboardMarkup(keyboard)
            bot_msg = (
                "You are going to delete project"
                f" '{context.user_data['title_to_delete']}' with all reminders.\n"
                + bot_msg
            )
            await query.edit_message_text(bot_msg, reply_markup=reply_markup)
            return context.user_data["level"]

    else:
        logger.error(
            "Something strange happened while trying to rename delete project."
            f" Context: {context.user_data}"
        )
        bot_msg = "Error occured. Contact developer."
        await query.edit_message_text(bot_msg)
        return ConversationHandler.END


async def project_delete_finish(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Deletes selected project with reminders
    from database and returns to projects menu.
    """
    query = update.callback_query
    await query.answer()
    msg = ""

    # Delete project and associated jobs from DB
    if is_db(DB):
        reminders = DB.projects.find_one_and_delete(
            {"_id": context.user_data["oid_to_delete"]}, {"reminders": 1, "_id": 0}
        )
        if (
            reminders
            and type(reminders) is dict
            and "reminders" in reminders.keys()
            and reminders["reminders"]
        ):
            for id in reminders["reminders"].values():
                context.job_queue.scheduler.get_job(id).remove()
            msg = (
                f"Project '{context.user_data['title_to_delete']}' successfully deleted"
            )
        else:
            msg = "Error getting data from database."

    # Return to projects menu level
    context.user_data["level"] -= 1
    context.user_data["branch"].pop()
    keyboard, bot_msg = get_keyboard_and_msg(
        DB,
        context.user_data["level"],
        str(update.effective_user.id),
        context.user_data["project"],
        context.user_data["branch"][-1],
    )

    # Check if we have message and keyboard and show them to user
    if not keyboard and not bot_msg:
        bot_msg = msg + "\n" + "Some error happened. Unable to show a menu."
        await query.edit_message_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = msg + "\n" + bot_msg
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return context.user_data["level"]


async def project_rename_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Start point of conversation for project rename:
    asks user for new name
    """

    query = update.callback_query
    await query.answer()

    # Pass oid of project to rename
    if query.data:
        context.user_data["oid_to_rename"] = ObjectId(query.data.split("_", 1)[1])

        #  Get title from DB by oid
        if is_db(DB):
            context.user_data["title_to_rename"] = DB.projects.find_one(
                {"_id": context.user_data["oid_to_rename"]}, {"title": 1, "_id": 0}
            )
        bot_msg = (
            "Type a new title for the project"
            f" '{context.user_data['title_to_rename']['title']}': "
        )
        await query.edit_message_text(bot_msg)
        return SIXTH_LVL
    else:
        logger.error(
            "Something strange happened while trying to rename chosen project."
            f" Context: {context.user_data}"
        )
        bot_msg = "Error occured. Contact developer."
        await query.edit_message_text(bot_msg)
        return ConversationHandler.END


async def project_rename_finish(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    End point of conversation of project rename.
    Receive and check new project title.
    Return user to project control menu at the end.
    """

    try:
        new_title = clean_project_title(str(update.message.text))  # to silence pylance
    except ValueError as e:
        bot_msg = (
            f"Try another name for project. Maybe more human readable this time. {e}"
        )

        # Let user have another try
        await update.message.reply_text(bot_msg)
        return SIXTH_LVL
    else:
        if is_db(DB):
            # Check if not existing one then change project title in context and in DB
            prj_id = DB.projects.find_one(
                {"title": new_title, "pm_tg_id": str(update.effective_user.id)},
                {"_id": 1},
            )
            if (
                prj_id
                and type(prj_id) is dict
                and "_id" in prj_id.keys()
                and prj_id["_id"]
            ):
                bot_msg = (
                    f"You already have project with name '{new_title}'. Try another"
                    " one."
                )
                await update.message.reply_text(bot_msg)
                return SIXTH_LVL

            else:
                # Change title in DB
                title_update = DB.projects.update_one(
                    {"_id": context.user_data["oid_to_rename"]},
                    {"$set": {"title": new_title}},
                )
                if title_update.modified_count > 0:
                    bot_msg = (
                        f"Got it. '{context.user_data['title_to_rename']['title']}'"
                        f" changed to '{new_title}'"
                    )

                    # Change title in context if needed
                    if (
                        context.user_data["project"]["title"]
                        == context.user_data["title_to_rename"]["title"]
                    ):
                        context.user_data["project"]["title"] = new_title

                    # Get jobs id from reminders dict, get each job by id
                    # and change title in job_data in apscheduler DB
                    reminders = DB.projects.find_one(
                        {"_id": context.user_data["oid_to_rename"]},
                        {"reminders": 1, "_id": 0},
                    )
                    if (
                        reminders
                        and type(reminders) is dict
                        and "reminders" in reminders.keys()
                        and reminders["reminders"]
                    ):
                        for id in reminders["reminders"].values():
                            job = context.job_queue.scheduler.get_job(id)
                            if job:
                                args = job.args
                                args[0].data["project_title"] = new_title
                                job = job.modify(args=args)
                    await update.message.reply_text(bot_msg)
                else:
                    bot_msg = (
                        "Something went wrong, couldn't change"
                        f" '{context.user_data['title_to_rename']['title']}' to"
                        f" '{new_title}'.\nMaybe try again later"
                    )
                    logger.error(
                        "Something went wrong, couldn't change"
                        f" '{context.user_data['title_to_rename']['title']} to"
                        f" '{new_title}' for user: '{update.effective_user.id}'"
                    )
                    await update.message.reply_text(bot_msg)

        # Return to level with projects
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
            context.user_data["branch"][-1],
        )

        # Check if we have message and keyboard and show them to user
        if not keyboard and not bot_msg:
            bot_msg = "Some error happened. Unable to show a menu."
            await update.message.reply_text(bot_msg)
            return ConversationHandler.END
        else:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(bot_msg, reply_markup=reply_markup)
            return context.user_data["level"]


""" REMINDERS SETTINGS BRANCH """


async def reminders_settings_item(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Function to show reminders control menu branch"""
    query = update.callback_query
    await query.answer()

    # Check if data contains reminder name then prepare going to next level
    # make a keyboard for it, get reminder's preset to show to user
    preset = ""
    if query.data:
        context.user_data["level"] += 1
        context.user_data["branch"].append(query.data)
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
            context.user_data["branch"][-1],
        )
        job_id = context.user_data["project"]["reminders"][
            str(context.user_data["branch"][-1])
        ]
        preset = get_job_preset(job_id, context)

    # Stay on same level if not
    else:
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
        )

    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await query.edit_message_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return context.user_data["level"]


async def reminder_switcher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles menu item for turning on/off choosen reminder
    """

    query = update.callback_query
    await query.answer()

    # Find a job by id and pause it if it's enabled or resume if it's paused
    job_id = context.user_data["project"]["reminders"][
        str(context.user_data["branch"][-1])
    ]

    job = context.job_queue.scheduler.get_job(job_id)
    if job:
        if job.next_run_time:
            job = job.pause()
        else:
            job = job.resume()

    # Return previous menu:
    # Call function which create keyboard and generate message to send to user.
    # Call function which get current preset of reminder, to inform user.
    # End conversation if that was unsuccessful.
    keyboard, bot_msg = get_keyboard_and_msg(
        DB,
        context.user_data["level"],
        str(update.effective_user.id),
        context.user_data["project"],
        context.user_data["branch"][-1],
    )
    preset = get_job_preset(job_id, context)
    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await query.edit_message_text(bot_msg, reply_markup=reply_markup)
    return context.user_data["level"]


async def reminder_time_pressed(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Menu option 'Set time' (for for choosen reminder)"""

    query = update.callback_query
    await query.answer()

    # Call function to get current preset for reminder
    job_id = context.user_data["project"]["reminders"][
        str(context.user_data["branch"][-1])
    ]
    preset = get_job_preset(job_id, context)

    # If reminder not set return menu with reminder settings
    if not preset:
        text = "Seems that reminder doesn't set"

        # Call function which create keyboard and generate message to send to user.
        # End conversation if that was unsuccessful.
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
            context.user_data["branch"][-1],
        )
        if not keyboard and not bot_msg:
            bot_msg = f"{text}\nSome error happened. Unable to show a menu."
            await query.edit_message_text(bot_msg)
            return ConversationHandler.END
        else:
            reply_markup = InlineKeyboardMarkup(keyboard)
            bot_msg = f"{text}\n{bot_msg}"
            await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return context.user_data["level"]

    # If reminder set send message to user with current preset
    # and example of input expected from him
    else:
        bot_msg = (
            f"Current preset for reminder:\n{preset} \nEnter new time in format: 12:30"
        )
        await query.edit_message_text(bot_msg)

        # Tell conversationHandler to treat answer in a State 4 function
        return FOURTH_LVL


async def reminder_days_pressed(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Menu option 'Set days of week' for choosen reminder"""

    query = update.callback_query
    await query.answer()

    # Call function to get current preset for reminder
    job_id = context.user_data["project"]["reminders"][
        str(context.user_data["branch"][-1])
    ]
    preset = get_job_preset(job_id, context)

    # If reminder not set return menu with reminder settings
    if not preset:
        text = "Seems that reminder doesn't set"

        # Call function which create keyboard and generate message to send to user.
        # End conversation if that was unsuccessful.
        keyboard, bot_msg = get_keyboard_and_msg(
            DB,
            context.user_data["level"],
            str(update.effective_user.id),
            context.user_data["project"],
            context.user_data["branch"][-1],
        )
        if not keyboard and not bot_msg:
            bot_msg = f"{text}\nSome error happened. Unable to show a menu."
            await query.edit_message_text(bot_msg)
            return ConversationHandler.END
        else:
            reply_markup = InlineKeyboardMarkup(keyboard)
            bot_msg = f"{text}\n{bot_msg}"
            await query.edit_message_text(bot_msg, reply_markup=reply_markup)
        return context.user_data["level"]

    # If reminder set send message to user with current preset
    # and example of input expected from him
    else:
        bot_msg = (
            "Current preset for reminder:\n"
            f"{preset} \n"
            "Type days of week when reminder should work in this format: \n"
            "monday, wednesday, friday \n"
            "or\n"
            "mon, wed, fri"
        )
        await query.edit_message_text(bot_msg)

        # Tell conversationHandler to treat answer in a State 5
        return FIFTH_LVL


async def reminder_time_setter(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Handles new time provided by user.
    Reschedules corresponding job.
    """

    bot_msg = "Unable to reschedule the reminder"

    # Try to convert user provided input (time) to hours and minutes
    try:
        hour, minute = map(
            int, re.split("[\s:;_-]", str(update.message.text))  # noqa: W605
        )  # convert to string to silence pylance

    except ValueError:
        # Prepare message if not succeded
        bot_msg = "Did not recognize time. Please use 24h format: 15:05"
    else:
        # Find a job by id for further rescheduling
        job_id = context.user_data["project"]["reminders"][
            str(context.user_data["branch"][-1])
        ]
        job = context.job_queue.scheduler.get_job(job_id)
        if job:
            # Get timezone attribute from current job
            tz = job.trigger.timezone

            # Get list of days of week by index of this attribute in list of fields
            day_of_week = job.trigger.fields[
                job.trigger.FIELD_NAMES.index("day_of_week")
            ]

            # Reschedule the job
            try:
                job = job.reschedule(
                    trigger="cron",
                    hour=hour,
                    minute=minute,
                    day_of_week=day_of_week,
                    timezone=tz,
                )
            except (AttributeError, ValueError) as e:
                bot_msg = "Unable to reschedule the reminder"
                logger.info(f"{e}")
            else:
                # Get job by id again because next_run_time didn't updated after reschedule
                # (no matter what docs says)
                job = context.job_queue.scheduler.get_job(job_id)
                bot_msg = f"Time updated. Next time: {job.next_run_time}"
        else:
            logger.error(
                f"Suddenly can't find job (id='{job_id}') while setting a time for it."
            )
            bot_msg = "Something went wrong. Try again later."

    # Inform the user how reschedule went
    await update.message.reply_text(bot_msg)

    # Provide keyboard of level 3 menu
    keyboard, bot_msg = get_keyboard_and_msg(
        DB,
        context.user_data["level"],
        str(update.effective_user.id),
        context.user_data["project"],
        context.user_data["branch"][-1],
    )

    # And get current (updated) preset
    job_id = context.user_data["project"]["reminders"][
        str(context.user_data["branch"][-1])
    ]
    preset = get_job_preset(job_id, context)
    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await update.message.reply_text(bot_msg, reply_markup=reply_markup)

    # Tell conversation handler to process query from this keyboard as STATE3
    return context.user_data["level"]


async def reminder_days_setter(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Handles new days of week provided by user for reminder.
    Reschedules corresponding job.
    """

    bot_msg = "Unable to reschedule the reminder"
    new_days = []

    # Better use variables for names of days for later translation
    days_of_week = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]

    # Store user input to list, clean from whitespaces, convert to lower case
    if update.message.text:
        user_input = update.message.text.split(",")
        for day in user_input:
            day = day.strip().lower()
            if (
                day == "monday"
                or day == "mon"
                or day == "понедельник"
                or day == "пн"
                or day == "пон"
            ):
                # Do not add doubles
                if not days_of_week[1] in new_days:
                    new_days.append(days_of_week[1])
            if (
                day == "tuesday"
                or day == "tue"
                or day == "вторник"
                or day == "вт"
                or day == "вто"
            ):
                if not days_of_week[2] in new_days:
                    new_days.append(days_of_week[2])
            if (
                day == "wednesday"
                or day == "wed"
                or day == "среда"
                or day == "ср"
                or day == "сре"
            ):
                if not days_of_week[3] in new_days:
                    new_days.append(days_of_week[3])
            if (
                day == "thursday"
                or day == "thu"
                or day == "четверг"
                or day == "чт"
                or day == "чет"
            ):
                if not days_of_week[4] in new_days:
                    new_days.append(days_of_week[4])
            if (
                day == "friday"
                or day == "fri"
                or day == "пятница"
                or day == "пт"
                or day == "пят"
            ):
                if not days_of_week[5] in new_days:
                    new_days.append(days_of_week[5])
            if (
                day == "saturday"
                or day == "sat"
                or day == "суббота"
                or day == "сб"
                or day == "суб"
            ):
                if not days_of_week[6] in new_days:
                    new_days.append(days_of_week[6])
            if (
                day == "sunday"
                or day == "sun"
                or day == "воскресенье"
                or day == "вс"
                or day == "вос"
            ):
                if not days_of_week[0] in new_days:
                    new_days.append(days_of_week[0])
        if new_days:
            # Find job by id to reschedule
            job_id = context.user_data["project"]["reminders"][
                context.user_data["branch"][-1]
            ]
            job = context.job_queue.scheduler.get_job(job_id)

            if job:
                # Get current parameters of job
                tz = job.trigger.timezone
                hour = job.trigger.fields[job.trigger.FIELD_NAMES.index("hour")]
                minute = job.trigger.fields[job.trigger.FIELD_NAMES.index("minute")]

                # Reschedule the job
                try:
                    job.reschedule(
                        trigger="cron",
                        hour=hour,
                        minute=minute,
                        day_of_week=",".join(new_days),
                        timezone=tz,
                    )
                except (ValueError, AttributeError) as e:
                    bot_msg = "Unable to reschedule the reminder"
                    logger.error(f"{e}")
                bot_msg = f"Time updated. Next time: \n{job.next_run_time}"
            else:
                bot_msg = "Sorry, couldn't reschedule. Contact developer."
                logger.error(f"Couldn't find job with id '{job_id}'.")
        else:
            bot_msg = "No correct names for days of week found in you message.\n"
    else:
        bot_msg = "Sorry, can't hear you: got empty message"

    # Inform the user how reschedule went
    await update.message.reply_text(bot_msg)

    # Provide keyboard of level 3 menu
    keyboard, bot_msg = get_keyboard_and_msg(
        DB,
        context.user_data["level"],
        str(update.effective_user.id),
        context.user_data["project"],
        context.user_data["branch"][-1],
    )
    # And get current preset (updated) of the reminder to show to user
    job_id = context.user_data["project"]["reminders"][
        str(context.user_data["branch"][-1])
    ]
    preset = get_job_preset(job_id, context)
    if not keyboard and not bot_msg:
        bot_msg = "Some error happened. Unable to show a menu."
        await update.message.reply_text(bot_msg)
        return ConversationHandler.END
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot_msg = f"{bot_msg}Current preset: {preset}"
        await update.message.reply_text(bot_msg, reply_markup=reply_markup)

    # Tell conversation handler to process query from this keyboard as STATE3
    return context.user_data["level"]


""" ### END OF SETTINGS PART ### """


async def post_init(application: Application) -> None:
    """
    Function to control list of commands and description in bot itself.
    Commands itself are global because they used in main() too.
    """
    commands = await application.bot.get_my_commands()
    new_commands = (
        download_cmd,
        feedback_cmd,
        help_cmd,
        settings_cmd,
        start_cmd,
        status_cmd,
        stop_cmd,
        upload_cmd,
    )
    if commands != new_commands:
        await application.bot.set_my_commands(new_commands)

    description = await application.bot.get_my_description()
    new_description = (
        "The purpose of this bot to assist you as a Project Manager (PM) "
        "to keep control over project. "
        "It informs about current state of the provided project: which tasks started, "
        "which are at deadline, about milestones, and tasks in overdue state. "
        "It also informs assignees about their tasks. "
        "You can change time and days when bot should send its reminders."
    )
    if description.description != new_description:
        await application.bot.set_my_description(new_description)

    short_description = await application.bot.get_my_short_description()
    new_short_description = (
        "This Assisstant created to help Project Manager (PM) "
        "and project team keep informed about project status.")
    if short_description.short_description != new_short_description:
        await application.bot.set_my_short_description(new_short_description)

    bot_name = await application.bot.get_my_name()
    new_bot_name = "Project Manager Assistant bot"
    if bot_name.name != new_bot_name:
        await application.bot.set_my_name(bot_name)


def main() -> None:
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    if not BOT_TOKEN:
        sys.exit("Bot token not found")

    # Create a builder via Application.builder()
    # and then specifies all required arguments via that builder.
    # Finally, the Application is created by calling builder.build()
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Add job store MongoDB
    application.job_queue.scheduler.add_jobstore(
        PTBMongoDBJobStore(
            application=application,
            host=DB_URI,
        )
    )

    # Register handler for /help command
    application.add_handler(CommandHandler(help_cmd.command, help))

    # Command to trigger project status check.
    application.add_handler(CommandHandler(status_cmd.command, status))

    # Command to allow user to save project file to local computer
    application.add_handler(
        CommandHandler(download_cmd.command, download, ~filters.ChatType.GROUPS)
    )

    # Run on any message in a group that is a text and not a command
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
            update_staff_on_message,
        )
    )

    # Catch when PM pressed a button to mark task accomplished
    application.add_handler(
        CallbackQueryHandler(set_task_accomplished, pattern="^task")
    )

    # Conversation handler for /start
    start_conv = ConversationHandler(
        entry_points=[
            CommandHandler(start_cmd.command, start, ~filters.ChatType.GROUPS)
        ],
        states={
            FIRST_LVL: [
                MessageHandler(
                    filters.TEXT
                    & ~(
                        filters.COMMAND
                        | filters.Regex(re.compile("^cancel$", re.IGNORECASE))
                    ),
                    naming_project,
                ),
            ],
            SECOND_LVL: [MessageHandler(filters.Document.ALL, file_received)],
        },
        fallbacks=[
            MessageHandler(filters.TEXT | filters.COMMAND, start_ended),
            MessageHandler(
                filters.Regex(re.compile("^cancel$", re.IGNORECASE)), start_ended
            ),
        ],
    )
    application.add_handler(start_conv, group=1)

    # Conversation handler for /feedback command
    feedback_conv = ConversationHandler(
        entry_points=[
            CommandHandler(feedback_cmd.command, feedback, ~filters.ChatType.GROUPS)
        ],
        states={
            FIRST_LVL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_answer)
            ]
        },
        fallbacks=[MessageHandler(filters.COMMAND, feedback_aborted)],
    )
    application.add_handler(feedback_conv, group=3)

    # PM should have the abibility to change bot behaviour, such as reminder interval and so on
    # Configure /settings conversation and add a handler
    settings_conv = ConversationHandler(
        entry_points=[
            CommandHandler(settings_cmd.command, settings, ~filters.ChatType.GROUPS)
        ],
        states={
            FIRST_LVL: [
                CallbackQueryHandler(
                    second_lvl_menu,
                    pattern="^notifications$|^reminders$|^projects$|^control$",
                ),
                CallbackQueryHandler(finish_settings, pattern="^finish$"),
            ],
            SECOND_LVL: [
                CallbackQueryHandler(
                    allow_status_to_group, pattern="^" + str(ONE) + "$"
                ),
                CallbackQueryHandler(milestones_anounce, pattern="^" + str(TWO) + "$"),
                CallbackQueryHandler(
                    notify_of_all_projects, pattern="^" + str(THREE) + "$"
                ),
                CallbackQueryHandler(
                    reminders_settings_item,
                    pattern="^day_before_update$|^morning_update$|^friday_update$",
                ),
                # According to docs (https://core.telegram.org/bots/api#user)
                # id should be less than 52 bits:
                CallbackQueryHandler(
                    transfer_control, pattern="^\d{6,15}$"  # noqa: W605
                ),
                CallbackQueryHandler(project_activate, pattern="^activate"),
                CallbackQueryHandler(project_delete_start, pattern="^delete"),
                CallbackQueryHandler(project_rename_start, pattern="^rename"),
                CallbackQueryHandler(settings_back, pattern="^back$"),
                CallbackQueryHandler(finish_settings, pattern="^finish$"),
            ],
            THIRD_LVL: [
                CallbackQueryHandler(reminder_switcher, pattern="^" + str(ONE) + "$"),
                CallbackQueryHandler(
                    reminder_time_pressed, pattern="^" + str(TWO) + "$"
                ),
                CallbackQueryHandler(
                    reminder_days_pressed, pattern="^" + str(THREE) + "$"
                ),
                CallbackQueryHandler(project_delete_finish, pattern="^yes$"),
                CallbackQueryHandler(settings_back, pattern="^back$"),
                CallbackQueryHandler(finish_settings, pattern="^finish$"),
            ],
            # Don't need 'cancel' in two states below: they process all input and
            # exit from settings can be done via 'finish' button when menu appears
            FOURTH_LVL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time_setter),
            ],
            FIFTH_LVL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_days_setter),
            ],
            SIXTH_LVL: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND
                    & ~filters.Regex(re.compile("^cancel$", re.IGNORECASE)),
                    project_rename_finish,
                ),
            ],
        },
        fallbacks=[
            MessageHandler(filters.COMMAND, settings_aborted),
            MessageHandler(
                filters.Regex(re.compile("^cancel$", re.IGNORECASE)), settings_aborted
            ),
        ],
    )
    application.add_handler(settings_conv, group=2)

    # Configure /stop conversation and add a handler
    stop_conv = ConversationHandler(
        entry_points=[CommandHandler(stop_cmd.command, stop)],
        states={
            FIRST_LVL: [
                CallbackQueryHandler(stopping, pattern="^" + str(ONE) + "$"),
                CallbackQueryHandler(stop_aborted, pattern="^" + str(TWO) + "$"),
            ]
        },
        fallbacks=[MessageHandler(filters.TEXT | filters.COMMAND, stop_aborted)],
    )
    application.add_handler(stop_conv, group=5)

    # Configure /upload conversation and add a handler
    upload_conv = ConversationHandler(
        entry_points=[
            CommandHandler(upload_cmd.command, upload, ~filters.ChatType.GROUPS)
        ],
        states={
            FIRST_LVL: [
                MessageHandler(filters.Document.ALL, upload_file_recieved),
                CallbackQueryHandler(upload_ended, pattern="^" + str(ONE) + "$"),
            ],
        },
        fallbacks=[MessageHandler(filters.COMMAND, upload_ended)],
    )
    application.add_handler(upload_conv, group=4)

    # Start the Bot and run it until Ctrl+C pressed
    application.run_polling()


if __name__ == "__main__":
    main()
