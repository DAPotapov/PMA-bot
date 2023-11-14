import json
import logging
import re

from helpers import add_worker_info_to_staff, get_worker_oid_from_db_by_tg_username
from numpy import busday_offset, busday_count, floor, datetime64
from pathlib import Path
from pymongo.database import Database
from untangle import Element, parse

# Because GanttProject and MS Project have different values for dependency type here is the adaptor
# Will use MS Project values, because it's more popular program
# MS Project type of link (depend_type): Values are 0=FF, 1=FS, 2=SF and 3=SS
# (docs at https://learn.microsoft.com/en-us/office-project/xml-data-interchange/xml-schema-for-the-tasks-element?view=project-client-2016)  # noqa: E501
# GanttProject type values:
# 0 = none, 1 = start-start SS, 2 = finish-start FS,
# 3 - finish-finish FF, 4 - start-finish SF (usually not used)
# Map GanttProject dependency types to MS Project
GAN_DEPEND_TYPES = [3, 1, 0, 2]

# Configure logging
# logging.basicConfig(
#   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#   level=logging.INFO
# )
# logging.basicConfig(
#     filename=".data/log.log",
#     filemode="a",
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     level=logging.INFO,
# )
logger = logging.getLogger(__name__)


def load_gan(fp: Path, db: Database) -> list[dict]:
    """
    This is a connector from GanttProject format (.gan) to inner format.
    Gets file pointer on input. Reads data from file.
    Validates and converts data to inner dict-list-dict.. format.
    Saves actioners to staff collection in DB.
    Returns list of tasks.
    Raises AttributeError and ValueError errors
    if project structure in a file is not correct.
    """

    # Declare dictionary to store data
    tasks = []

    # Parse the file
    obj = parse(str(fp))

    # Store resources
    if (
        "project" in obj
        and "resources" in obj.project
        and "resource" in obj.project.resources
    ):
        resources = obj.project.resources
    else:
        raise AttributeError("Provided file does not contain information about staff")

    # Check if special field for telegram id exist and store id of this field
    property_id = ""
    if "custom_property_definition" in resources:
        for custom_property in resources.custom_property_definition:
            if (
                custom_property["id"]
                and custom_property["name"]
                and custom_property["name"] == "tg_username"
            ):
                property_id = custom_property["id"]
                # no need to continue looking through custom properties
                break

    # Store allocations
    if "allocations" in obj.project and "allocation" in obj.project.allocations:
        allocations = obj.project.allocations.allocation
    else:
        raise AttributeError(
            "There are no assignments made. Whom are you gonna manage?"
        )

    # Adding workers to DB - should be at first place, before proceeding allocations for tasks
    # Check if custom property for telegram was found
    if property_id:
        # If custom property found, then proceed through resources
        for actioner in resources.resource:
            # Looking in custom properties of each resource for property assosiated with telegram
            tg_username = ""
            if "custom_property" in actioner:
                for property in actioner.custom_property:
                    if property["definition-id"] == property_id:
                        tg_username = property["value"]

            # Check if username was collected
            if not tg_username:
                raise ValueError(f"'{actioner['name']}' have no tg_username value")

            # Make dict of actioner
            worker = {
                "name": actioner["name"],
                "email": actioner["contacts"],
                "phone": actioner["phone"],
                "tg_username": tg_username,
                "tg_id": "",
                "account_type": "free",
                "settings": {
                    "INFORM_OF_ALL_PROJECTS": False,
                },
            }

            # Add record to DB and see result
            try:
                if not add_worker_info_to_staff(worker, db):
                    logger.warning(
                        "Something went wrong while adding worker to staff collection"
                    )
            except ValueError as e:
                logger.error(f"{e}")

    # If no custom property for tg_username found then inform developer
    else:
        raise AttributeError(
            "Project file has invalid structure: no 'tg_username' field"
        )

    if "tasks" in obj.project and "task" in obj.project.tasks:
        # Loop through tasks
        for task in obj.project.tasks.task:
            # Build tasks list using recursion
            tasks.extend(compose_tasks_list(task, allocations, resources, property_id, db))
    else:
        raise AttributeError("There are no tasks in provided file. Nothing to do.")
    return tasks


def get_tg_un_from_gan_resources(
    resource_id: str, resources: Element, property_id: str
) -> str:
    """
    Find telegram username in dictionary of resources (from .gan file)
    which corresponds provided id.
    Return None if nothing found. Should be controlled on calling side.
    """

    tg_username = ""

    for actioner in resources.resource:
        if "custom_property" in actioner and resource_id == actioner["id"]:
            for property in actioner.custom_property:
                if property["definition-id"] == property_id:
                    # If such property not filled then abort
                    # and tell user to do his job and make a proper file
                    if property["value"]:
                        tg_username = str(property["value"])
                    else:
                        raise ValueError(
                            f"'{actioner['name']}' have no tg_username value"
                        )

    return tg_username


def get_tg_un_from_xml_resources(
    resource_id: str, resources: Element, property_id: str
) -> str:
    """
    Find telegram username in dictionary of resources (from .xml file)
    which corresponds provided id.
    Return None if nothing found. Should be controlled on calling side.
    """

    tg_username = ""
    for actioner in resources.Resource:
        if resource_id == actioner.UID.cdata:
            for property in actioner.ExtendedAttribute:
                if property.FieldID.cdata == property_id:
                    # If such property not filled then abort and tell user to do his job
                    # and make a proper file
                    if not property.Value.cdata:
                        raise ValueError(
                            f"'{actioner.Name.cdata}' have no tg_username value"
                        )
                    else:
                        tg_username = property.Value.cdata
    return tg_username


def compose_tasks_list(
    task: Element,
    allocations: Element,
    resources: Element,
    property_id: str,
    db: Database,
) -> list:
    """
    Creates tasks list from a task element of .gan file
    and its nested subtasks (if any),
    resources and allocations collections (elements of .gan file too).
    Raises AttributeError or ValueError errors if structure is not correct.
    """

    output_tasks = []

    # Dictionary of id of actioners and their last reaction
    # Completeness of task assignments will be controlled in /status function
    actioners = []
    for allocation in allocations:
        if task["id"] and allocation["task-id"] and task["id"] == allocation["task-id"]:
            # Memo: GanntProject starts numeration of resources from 0, MS Project - from 1
            tg_username = ""
            if allocation["resource-id"]:
                tg_username = get_tg_un_from_gan_resources(
                    str(allocation["resource-id"]), resources, property_id
                )
            if tg_username:
                actioner_id = get_worker_oid_from_db_by_tg_username(tg_username, db)
                if actioner_id:
                    actioners.append(
                        {
                            "actioner_id": (
                                actioner_id
                            ),  # Now this field stores id of document in staff collection
                            "nofeedback": (
                                False
                            ),  # Default. Will be changed to True if person didn't answer to bot
                        }
                    )
                else:
                    raise AttributeError(
                        f"Couldn't get ObjectId from DB for '{tg_username} while"
                        f" processing task-id='{task['id']}'and"
                        f" resource-id='{allocation['resource-id']}' in resources"
                        " section of provided file"
                    )
            else:
                raise AttributeError(
                    f"Telegram username not found for task-id='{task['id']}'and"
                    f" resource-id='{allocation['resource-id']}' in resources section"
                    " of provided file"
                )

    # List of tasks which succeed from this one
    successors = []
    if "depend" in dir(task):
        for follower in task.depend:
            # If dependency translation not possible better aware user than import with somehow
            if int(str(follower["type"])) == 0:
                raise ValueError(
                    f"Unknown dependency type ('{follower['type']}')of successor task:"
                    f" {follower['id']}"
                )
            try:
                depend_type = GAN_DEPEND_TYPES[int(str(follower["type"])) - 1]
            except IndexError:
                raise ValueError(
                    f"Unknown dependency type ('{follower['type']}')of successor task:"
                    f" {follower['id']}"
                )
            else:
                successors.append(
                    {
                        "id": int(str(follower["id"])),
                        "depend_type": depend_type,
                        "depend_offset": int(str(follower["difference"])),
                    }
                )

    # Dictionary of subtasks' ids of this one.
    include = []
    if "task" in task:
        for subtask in task.task:
            include.append(int(str(subtask["id"])))

    # Construct dictionary of task and append to list of tasks
    if str(task["meeting"]).lower() == "false":
        milestone = False
    elif str(task["meeting"]).lower() == "true":
        milestone = True
    else:
        milestone = False

    # Construct end date from start date, duration and numpy function.
    # Numpy function returns sees duration as days _between_ dates,
    # but in project management enddate must be a date of deadline,
    # so correct expected return value by decreasing duration by one day.
    if int(str(task["duration"])) == 0:
        enddate = task["start"]
    else:
        enddate = str(
            busday_offset(
                datetime64(task["start"]),
                int(str(task["duration"])) - 1,
                roll="forward",
            )
        )

    output_tasks.append(
        {
            "id": int(str(task["id"])),
            "WBS": "",  # For compatibility with MS Project
            "name": task["name"],
            "startdate": task["start"],
            "enddate": enddate,
            "duration": int(str(task["duration"])),
            "predecessors": [],  # For compatibility with MS Project
            "successors": successors,
            "milestone": milestone,
            "complete": int(str(task["complete"])),
            "basicplan_startdate": task[
                "start"
            ],  # equal to start date on a start of the project
            "basicplan_enddate": enddate,  # equal to end date on a start of the project
            "include": include,
            "actioners": actioners,
        }
    )

    # Go deeper in subtasks to build tasks list
    if "task" in task:
        for subtask in task.task:
            subtasks = compose_tasks_list(subtask, allocations, resources, property_id, db)
            output_tasks.extend(subtasks)

    return output_tasks


def load_json(fp: Path, db: Database) -> list[dict]:
    """
    Loads JSON data from file into dictionary.
    This connector useful in case we downloaded JSON,
    manually made some changes, and upload it again to bot.
    Returns list of tasks of the project.
    Raises AttributeError and ValueError errors
    if project structure in a file is not correct.
    """

    tasks = []

    # Open file
    with open(fp, "r") as json_file:
        project = json.load(json_file)

        # Check and get two lists: tasks and staff
        if (
            project
            and type(project) is dict
            and "tasks" in project.keys()
            and "staff" in project.keys()
            and type(project["tasks"]) is list
            and type(project["staff"]) is list
            and project["tasks"]
            and project["staff"]
        ):
            # Check staff members for consistency and add to database
            # (if tg_id or tg_username not present already)
            # And store new oid to same dictionary for later use in actioners of tasks
            staff_keys = [
                "_id",
                "program_id",
                "name",
                "email",
                "phone",
                "tg_username",
                "tg_id",
                "account_type",
                "settings",
            ]
            for worker in project["staff"]:
                # Check that provided staff list contains all necessary keys
                if all(x in staff_keys for x in worker.keys()):
                    oid = add_worker_info_to_staff(worker, db)
                    if oid:
                        worker["new_oid"] = oid
                    else:
                        raise ValueError(
                            "Unable to add following staff member to database:"
                            f" '{worker}'"
                        )
                else:
                    raise AttributeError(
                        f"Member of staff doesn't have all necessary keys ({worker})"
                    )

            # Check each task for presence of keys and values
            # Order of this list matter! See remarks and check below.
            task_keys = [
                "name",
                "startdate",
                "enddate",
                "complete",
                # Can be False that will spoil check below
                "milestone",
                # Duration will be recalculated
                "duration",
                # id=0 becomes False in check below
                "id",
                # These could be empty and will fail check below as well
                "predecessors",
                "successors",
                "actioners",
                "WBS",
                "include",
            ]
            for task in project["tasks"]:
                # Check for keys
                if not all(x in task.keys() for x in task_keys):
                    raise AttributeError(
                        f"Task #{task['id']} doesn't have all necessary keys"
                        f" \n({task_keys})"
                    )

                # Check that necessary parameters are filled
                if not all(str(task[x]) for x in task_keys[:5]):
                    raise AttributeError(
                        f"Not all necessary parameters ({task_keys[:5]}) of task"
                        f" {task['id']} are filled."
                    )

                # Complete have type integer
                if (
                    type(task["complete"]) is not int
                    and task["complete"] >= 0
                    and task["complete"] < 101
                ):
                    raise ValueError(
                        "Completeness of task should be an integer from 0 to 100"
                        " percent."
                    )

                # Dates have right order
                if datetime64(task["startdate"]) > datetime64(task["enddate"]):
                    raise ValueError(
                        f"Taks #{task['id']} '{task['name']}' starts later than"
                        " finishes."
                    )

                # Regular task should have actioners and enddate later than startdate
                if task["milestone"] is False and not task["include"]:
                    if not task["actioners"]:
                        raise ValueError(
                            f"Taks #{task['id']} '{task['name']}' has no actioners."
                        )

                # Recalculate duration with dates provided
                task["duration"] = int(
                    busday_count(
                        datetime64(task["startdate"]), datetime64(task["enddate"])
                    )
                )

                # Update actioners with ids from database if its not actual
                if task["actioners"]:
                    for actioner in task["actioners"]:
                        for worker in project["staff"]:
                            if (
                                actioner["actioner_id"] == worker["_id"]
                                and worker["_id"] != worker["new_oid"]
                            ):
                                actioner["actioner_id"] = worker["new_oid"]

                # That's enough checks for sake of example,
                # but serious schedule management will need more checks:
                # taking in account dependent tasks and their dates and other

            tasks = project["tasks"]

        else:
            raise AttributeError(
                "File malformed: project dictionary must contain 'tasks' and 'staff'"
                " lists, each contains corresponding dictionaries. See example."
            )

    return tasks


def load_xml(fp: Path, db: Database) -> list[dict]:
    """
    Function to import from MS Project XML file
    Get file pointer and database instance on input.
    Validates and converts data to inner dict-list-dict.. format
    Saves actioners to staff collection in DB.
    Returns list of tasks.
    Raises AttributeError and ValueError errors
    if project structure in a file is not correct.
    """

    tasks = []
    obj = parse(str(fp))

    # Store resources
    if "Project" in obj and "Resource" in obj.Project.Resources:
        resources = obj.Project.Resources
    else:
        raise AttributeError("Provided file does not contain information about staff")

    # Check for telegram username field in XML provided
    property_id = ""
    if (
        "ExtendedAttributes" in obj.Project
        and "ExtendedAttribute" in obj.Project.ExtendedAttributes
    ):
        for attr in obj.Project.ExtendedAttributes.ExtendedAttribute:
            if (
                "Alias" in attr
                and "FieldID" in attr
                and attr.Alias.cdata == "tg_username"
            ):
                property_id = attr.FieldID.cdata

    # If telegram username field is not found then inform user
    if not property_id:
        raise AttributeError(
            "Project file has invalid structure: no 'tg_username' field"
        )

    # Store allocations
    if "Assignments" in obj.Project and "Assignment" in obj.Project.Assignments:
        allocations = obj.Project.Assignments.Assignment
    else:
        raise AttributeError(
            "There are no assignments made. Whom are you gonna manage?"
        )

    # Adding workers to DB - should be at first place, before proceeding allocations for tasks
    for actioner in resources.Resource:
        # Because collection of resources must contain at least one resource (from docs)
        # seems like MS Project adds one with id=0
        # But it lacks some of the fields like ExtendedAttribute,
        # so it's better to check if current resource has one
        if (
            "ExtendedAttribute" in actioner
            and "Name" in actioner
            and "EmailAddress" in actioner
        ):
            # Get telegram username from XML for this actioner
            tg_username = ""
            for property in actioner.ExtendedAttribute:
                if (
                    "FieldID" in property
                    and "Value" in property
                    and property.FieldID.cdata == property_id
                ):
                    tg_username = property.Value.cdata

            # Check if username was collected
            if not tg_username:
                raise ValueError(f"'{actioner.Name.cdata}' have no tg_username value")

            # Make dict of actioner
            worker = {
                "name": actioner.Name.cdata,
                # Seems like XML not necessary contain email address field for resource
                "email": (
                    actioner.EmailAddress.cdata if "EmailAddress" in actioner else ""
                ),
                # Seems like MS Project does not know about phones :)
                # Maybe I'll use ExtendedAttribute for this purpose later
                "phone": "",
                "tg_username": tg_username,
                "tg_id": "",
                "account_type": "free",
                "settings": {
                    "INFORM_OF_ALL_PROJECTS": False,
                },
            }

            # Add record to DB and see result
            try:
                if not add_worker_info_to_staff(worker, db):
                    logger.warning(
                        f"Something went wrong while adding worker {worker} to staff"
                        " collection"
                    )
            except ValueError as e:
                logger.error(f"{e}")

    # Gathering tasks from XML
    if "Tasks" in obj.Project and "Task" in obj.Project.Tasks:
        # Because 1st element in MS Project XML format represents project itself so skip it
        tasks_from_xml = iter(obj.Project.Tasks.Task)
        next(tasks_from_xml)
        for task in tasks_from_xml:
            duration = 0
            actioners = []
            # First check all needed fields
            if (
                "Milestone" in task
                and "UID" in task
                and "WBS" in task
                and "Name" in task
                and "PercentComplete" in task
                and "Start" in task
                and "Finish" in task
            ):
                # Calculate duration from start and end dates using only business days
                # and considering that end date (aka deadline) should be included
                # Calculating duration from presented duration in XML (in hours)
                # may provide not right results:
                # actually its effort - assume work only need 1 hour but sometime during the week
                # And milestones have zero duration
                if task.Milestone.cdata == "0":
                    duration = int(
                        busday_count(
                            xml_date_conversion(task.Start.cdata),
                            xml_date_conversion(task.Finish.cdata),
                        )
                        + 1
                    )

                    # Make actioners list for this task, skipping milestones
                    # Completeness of task assignments will be controlled in /status function
                    for allocation in allocations:
                        if (
                            "TaskUID" in allocation
                            and "ResourceUID" in allocation
                            and task.UID.cdata == allocation.TaskUID.cdata
                        ):
                            # MS Project store value '-65535' in case no resource assigned.
                            # I'll leave this list empty
                            if int(allocation.ResourceUID.cdata) > 0:
                                tg_username = get_tg_un_from_xml_resources(
                                    allocation.ResourceUID.cdata, resources, property_id
                                )
                                if tg_username:
                                    actioner_id = get_worker_oid_from_db_by_tg_username(
                                        tg_username, db
                                    )
                                    if actioner_id:
                                        actioners.append(
                                            {
                                                # Memo: GanntProject starts numeration
                                                # of resources from 0,
                                                # MS Project - from 1
                                                "actioner_id": actioner_id,
                                                # For future development.
                                                # This setting will be changed to True
                                                # if person didn't answer to bot
                                                "nofeedback": (
                                                    False
                                                ),
                                            }
                                        )
                                    else:
                                        raise AttributeError(
                                            "Couldn't get ObjectId from DB for"
                                            f" '{tg_username} while processing"
                                            f" task-id='{task.UID.cdata}'and"
                                            f" resource-id='{allocation.ResourceUID.cdata}'"
                                            " in resources section of provided file"
                                        )
                                else:
                                    raise AttributeError(
                                        "Telegram username not found for"
                                        f" task-id='{task.UID.cdata}'and"
                                        f" resource-id='{allocation.ResourceUID.cdata}'"
                                        " in resources section of provided file"
                                    )

                # Besides successors will store predecessors
                # for backward compatibility with MS Project
                predecessors = []
                if "PredecessorLink" in task:
                    for predecessor in task.PredecessorLink:
                        depend_offset = 0
                        if (
                            "LinkLag" in predecessor
                            and predecessor.LinkLag.cdata != "0"
                        ):
                            depend_offset = int(
                                floor(int(predecessor.LinkLag.cdata) / 4800)
                            )
                        predecessors.append(
                            {
                                "id": (
                                    int(predecessor.PredecessorUID.cdata)
                                    if "PredecessorUID" in predecessor
                                    else None
                                ),
                                "depend_type": (
                                    int(predecessor.Type.cdata)
                                    if "Type" in predecessor
                                    else None
                                ),
                                "depend_offset": depend_offset,
                            }
                        )

                tasks.append(
                    {
                        "id": int(task.UID.cdata),
                        "WBS": (
                            task.WBS.cdata
                        ),  # this field is useful for determining inclusion of tasks
                        "name": task.Name.cdata,
                        "startdate": xml_date_conversion(task.Start.cdata),
                        "enddate": xml_date_conversion(task.Finish.cdata),
                        "duration": duration,
                        "predecessors": predecessors,
                        "successors": (
                            []
                        ),  # will be calculated below from PredecessorLink
                        "milestone": True if task.Milestone.cdata == "1" else False,
                        "complete": int(task.PercentComplete.cdata),
                        "basicplan_startdate": xml_date_conversion(
                            task.Start.cdata
                        ),  # equal to start date on a start of the project
                        "basicplan_enddate": xml_date_conversion(
                            task.Finish.cdata
                        ),  # equal to end date on a start of the project
                        "include": (
                            []
                        ),  # will be calculated later from WBS and OutlineLevel
                        "actioners": actioners,
                    }
                )

        # Go through collection of tasks and find it is a someone predecessor
        for record in tasks:
            successors = []
            for task in obj.Project.Tasks.Task:
                if "PredecessorLink" in task:
                    for predecessor in task.PredecessorLink:
                        if (
                            "PredecessorUID" in predecessor
                            and "LinkLag" in predecessor
                            and "Type" in predecessor
                            and record["id"] == int(predecessor.PredecessorUID.cdata)
                        ):
                            # Recalculate offset from LinkLag,
                            # which expressed in tenth of minutes (sic!), so 4800 is 8 hours
                            if int(predecessor.LinkLag.cdata) == 0:
                                offset = 0
                            else:
                                # For project management purposes it's better
                                # to be aware of smth earlier than later
                                offset = int(
                                    floor(int(predecessor.LinkLag.cdata) / 4800)
                                )
                            successors.append(
                                {
                                    "id": int(task.UID.cdata),
                                    # Type of link (depend_type):
                                    # Values are 0=FF, 1=FS, 2=SF and 3=SS
                                    # (docs at https://learn.microsoft.com/en-us/office-project/xml-data-interchange/xml-schema-for-the-tasks-element?view=project-client-2016)   # noqa: E501
                                    "depend_type": int(predecessor.Type.cdata),
                                    "depend_offset": offset,
                                }
                            )

                # Also find included tasks
                # Look at outline level to comprehend level of WBS to look for - more than one
                if (
                    "OutlineLevel" in task
                    and "WBS" in task
                    and "UID" in task
                    and int(task.OutlineLevel.cdata) > 1
                ):
                    # Take part of WBS of task before last dot - this is WBS of Parent task
                    parentWBS = task.WBS.cdata[: task.WBS.cdata.rindex(".")]

                    # Find in gathered tasks list task with such WBS
                    # and add UID of task to 'include' sublist
                    if record["WBS"] == parentWBS:
                        record["include"].append(int(task.UID.cdata))
            record["successors"] = successors
    else:
        raise AttributeError("There are no tasks in provided file. Nothing to do.")
    return tasks


def xml_date_conversion(input_date: str) -> str:
    """
    Convert Project dateTime format (2023-05-15T08:00:00)
    to inner date format (2023-05-15)
    """

    # Given date from XML, expect dateTime Project format
    datestring = re.search("^\d{4}-\d{2}-\d{2}", input_date)  # noqa: W605
    if not datestring:
        raise ValueError(f"Error in start date found ({datestring})")
    else:
        datestring = datestring.group()

    return datestring
