import pprint
import re
import untangle
import json

from numpy import busday_offset, busday_count, floor, datetime64
# For testing purposes
from pprint import pprint


def email_validation(email):
    '''
    Function to validate an email address and gently inform user if smth not right, like:
    ' Hey, I could not send email to that address later'
    It's for future function to inform user via email
    '''
    # TODO: implement
    pass


def phone_validation():
    '''
    Function to validate phone number and gently inform PM if smth is not right, like
    'Hey, it seems we couldn't call such number later'
    It's for future function to inform user via phone
    '''
    # TODO: Implement
    pass


def tg_validation():
    ''' 
    Function to validate telegram username
    '''
# TODO: Implement
    pass

# TODO maybe don't need this
def main():
    '''
    Module recieve PosixPath of downloaded file.
    Returns dictionary of lists of dictionaries of project schedule and assignments
    If error occured should return at least string of error message, but maybe there is better way of error handling

    '''
    
    return

def load_gan(fp):
    '''
    This is a connector from GanttProject format (.gan) to inner format.
    Get file pointer on input
    Validates and converts data to inner dict-list-dict.. format
    Dictionary on output        
    '''
    
    # Using untangle on GAN - WORKING. This syntax cleaner and have some useful methods like 'children'
    # Declare dictionary to store data
    tasks = []
    
    # Parse the file
    obj = untangle.parse(str(fp))

    if 'task' in obj.project.tasks:
        # Loop through tasks
        for task in obj.project.tasks.task:
            # Add relevant data to list containing task information
            if 'allocation' in obj.project.allocations:
                allocations = obj.project.allocations.allocation
                # pprint(f' Tasks list before function call: {tasks}')
                # pprint(f"This task will be send to function: {task['name']}")
                tasks = compose_tasks_list(tasks, task, allocations)
                # pprint(f" .. and after function: {tasks}")
                # if task has subtask retreive data from it too
                if 'task' in task:
                    for subtask in task.task:
                        # pprint(f' Tasks list before function call: {tasks}')
                        tasks = compose_tasks_list(tasks, subtask, allocations)
                        # pprint(f' .. and after: {tasks}')

            else:
                raise ValueError('There are no assignments made. Whom are you gonna manage?')
    else:
        raise ValueError('There are no tasks in provided file. Nothing to do.')

    # TODO Resolving GanttProject bug of duplication of resource allocation. 
    # Better use standalone function in case they will fix this bug

    # Collect actioners
    staff = []
    property_id = ''
    
    # Check if special field for telegram id exist and choose correct 
    # custom property if there are several of them
    for custom_property in obj.project.resources.custom_property_definition:
        if custom_property['name'] == 'tg_username':
            property_id = custom_property['id']
            # no need to continue looking through custom properties
            break
        else:
            pass
    # Check if custom property for telegram was found
    if property_id:
        # If custom property found, then proceed through resources
        for actioner in obj.project.resources.resource:
            # Looking in custom properties of each resource for property assosiated with telegram
            tg_username = ''
            for property in actioner.custom_property:
                if property['definition-id'] == property_id:
                    # If such property not filled then abort and tell user to do his job and make a proper file
                    if not property['value']:
                        raise ValueError(f"'{actioner['name']}' have no tg_username value")
                    else:
                        tg_username = property['value']

            # Build list of actioners
            staff.append({
                'id' : int(actioner['id']),
                'name' : actioner['name'],
                'email' : actioner['contacts'],
                'phone' : actioner['phone'],
                'tg_username' : tg_username,
                'tg_id' : ""
            })
    # If no custom property for tg_username found then inform developer
    else:
        raise AttributeError(f"Project file has invalid structure: no 'tg_username' field")
    
    return tasks, staff


def compose_tasks_list(list, task, allocations):
    ''' Function to append to list of tasks information of one task or subtask'''

    # Dictionary of id of actioners and their last reaction
    # Completeness of task assignments will be controlled in /status function
    # pprint(f"Function got these parameters:\n {list}\n{task['name']}\n{allocations}")
    actioners = [] 
    for allocation in allocations:
        if task['id'] == allocation['task-id']:
            actioners.append({
                # Memo: GanntProject starts numeration of resources from 0, MS Project - from 1
                'actioner_id': int(allocation['resource-id']), 
                'nofeedback': False # Default. Will be changed to True if person didn't answer to bot
                })
                             
    # Dictionary of tasks which succeed from this one
    successors = []
    if 'depend' in dir(task):
        for follower in task.depend:
            # Because GanttProject and MS Project have different values for dependency type here is the adaptor
            # Will use MS Project values, because it's more popular program
            # Type of link (depend_type): Values are 0=FF, 1=FS, 2=SF and 3=SS (docs at https://learn.microsoft.com/en-us/office-project/xml-data-interchange/xml-schema-for-the-tasks-element?view=project-client-2016)
            # GanttProject type values: 0 = none, 1 = start-start SS, 2 = finish-start FS, 3 - finish-finish FF, 4 - start-finish SF (usually not used)
            depend_type = 1 # FS - most common
            match follower['type']:
                case '1':
                    depend_type = 3
                case '2':
                    depend_type = 1
                case '3':
                    depend_type = 0
                case '4':
                    depend_type = 2
                case _:
                    raise ValueError(f"Unknown dependency type ('{follower['type']}')of successor task: {int(follower['id'])}")
            successors.append({
                'id': int(follower['id']),
                'depend_type': depend_type,
                'depend_offset': int(follower['difference'])
                })

    # Dictionary of subtasks' id of this one. This way helpful to almost infinitely decompose tasks. 
    include = []
    if 'task' in task:
        for subtask in task.task:
            include.append(int(subtask['id']))
    
    # Construct dictionary of task and append to list of tasks   
    if task['meeting'].lower() == "false":
        milestone = False
    elif task['meeting'].lower() == "true":
        milestone = True
    else:
        raise ValueError('File may be damaged: milestone field contains invalid value ' + str(task['meeting']))
    
    # TODO in v.2: project apps supports alternative calendars, bot should support them as well.
    # Construct end date from start date, duration and numpy function.
    # Numpy function returns sees duration as days _between_ dates, 
    # but in project management enddate must be a date of deadline, 
    # so correct expected return value by decreasing duration by one day.
    if int(task['duration']) == 0:
        enddate = task['start']
    else:
        enddate = str(busday_offset(datetime64(task['start']), int(task['duration']) - 1, roll='forward'))

    list.append({
                'id': int(task['id']),
                'WBS': None, # For compatibility with MS Project
                'name': task['name'],
                'startdate': task['start'],
                'enddate': enddate, 
                'duration': int(task['duration']),
                'predecessors': [], # For compatibility with MS Project
                'successors': successors,
                'milestone': milestone,
                'complete': int(task['complete']),
                'curator': '', # not using for now, but it may become usefull later
                'basicplan_startdate': task['start'], # equal to start date on a start of the project
                'basicplan_enddate': enddate, # equal to end date on a start of the project
                'include': include,
                'actioners': actioners
            })
    return list


def load_json(fp):
    '''
    Loads JSON data from file into dictionary.
    This connector useful in case we downloaded JSON, manually made some changes, 
    and upload it again to bot 
    '''
    # TODO: Do this connector when i'm sure scheme doesn't changes
    # 1. Limit size of data to load to prevent attacks
    # 2. 
    
    project = json.load(fp)
    tasks = []
    staff = []
    # TODO check if it seems like project. Look for inner format structure
    # TODO parse project to corresponding lists
    return tasks, staff


def load_xml(fp):
    """ 
    Function to import from MS Project XML file 
    Get file pointer on input
    Validates and converts data to inner dict-list-dict.. format
    Dictionary on output    
    """

    # List for staff
    tasks = []
    staff = []
    # Store XML inner ID for field where telegram username located
    property_id = ''

    obj = untangle.parse(str(fp))

    #TODO consider adding version check if difficulties ocurr

    # Check for telegram username field in XML provided
    if 'ExtendedAttribute' in obj.Project.ExtendedAttributes:
        for attr in obj.Project.ExtendedAttributes.ExtendedAttribute:
            if attr.Alias.cdata == 'tg_username':
                property_id = attr.FieldID.cdata
        # If telegram username field is not found then inform user
        if not property_id:
            raise AttributeError("Project file has invalid structure: no 'tg_username' field")
    else:
        raise AttributeError("Project file has invalid structure: no 'tg_username' field")

    # Add resources from XML to list of actioners
    if 'Resource' in obj.Project.Resources:
        for actioner in obj.Project.Resources.Resource:
            # Because collection of resources must contain at least one resource (from docs) seems like MS Project adds one with id=0
            # But it lacks some of the fields like ExtendedAttribute, so it's better to check if current resource has one
            if 'ExtendedAttribute' in actioner:
                # Get telegram username from XML for this actioner
                tg_username = ''
                for attr in actioner.ExtendedAttribute:
                    if attr.FieldID.cdata == property_id:
                        tg_username = attr.Value.cdata
                if not tg_username:
                    raise ValueError(f"'{actioner.Name.cdata}' have no tg_username value") 
                staff.append({
                    'id' : int(actioner.UID.cdata),
                    'name' : actioner.Name.cdata,
                    # Seems like XML not necessary contain email address field for resource
                    'email' : actioner.EmailAddress.cdata if 'EmailAddress' in actioner else '',
                    # Seems like MS Project does not know about phones :) 
                    # Maybe I'll use ExtendedAttribute for this purpose later
                    'phone' : '',
                    'tg_username' : tg_username,
                    'tg_id' : ""
                })
    else:
        raise ValueError(f'There are no actioners (resources) in provided file. Who gonna work?')

    # Gathering tasks from XML
    if 'Task' in obj.Project.Tasks:
        # Because 1st element in MS Project XML format represents project itself so skip it
        for i, task in enumerate(obj.Project.Tasks.Task):
            if i == 0:
                continue            
            
            # Calculate duration from start and end dates using only business days 
            # and considering that end date (aka deadline) should be included
            # Calculating duration from presented duration in XML (in hours) may provide not right results: 
            # actually its effort - assume work only need 1 hour but sometime during the week
            # And milestones have zero duration
            if task.Milestone.cdata == '1':
                duration = 0
            else:
                duration = int(busday_count(xml_date_conversion(task.Start.cdata), xml_date_conversion(task.Finish.cdata)) + 1)
                # print(f"Duration type is: {type(duration)}")
            # print(f"Start: {task.Start.cdata}, End: {task.Finish.cdata}, duration: {duration}")

            # make actioners list for this task, skipping milestones
            # Completeness of task assignments will be controlled in /status function
            actioners = []
            for assignment in obj.Project.Assignments.Assignment:
                if task.UID.cdata == assignment.TaskUID.cdata and task.Milestone.cdata == '0':
                    # MS Project store value '-65535' in case no resource assigned. I'll leave this list empty
                    if int(assignment.ResourceUID.cdata) > 0:
                        actioners.append({
                            # Memo: GanntProject starts numeration of resources from 0, MS Project - from 1
                            'actioner_id': int(assignment.ResourceUID.cdata),
                            'nofeedback': False # Default. Will be changed to True if person didn't answer to bot
                        })

            # Besides successors will store predecessors for backward compatibility with MS Project
            predecessors = []
            if 'PredecessorLink' in task:
                for predecessor in task.PredecessorLink:
                    predecessors.append({
                        'id': int(predecessor.PredecessorUID.cdata),
                        'depend_type': int(predecessor.Type.cdata),
                        'depend_offset': 0 if predecessor.LinkLag.cdata == '0' else int(floor(int(predecessor.LinkLag.cdata) / 4800)),
                        })

            tasks.append({
                'id': int(task.UID.cdata),
                'WBS': task.WBS.cdata, # this field is useful for determining inclusion of tasks
                'name': task.Name.cdata,
                'startdate': xml_date_conversion(task.Start.cdata), 
                'enddate': xml_date_conversion(task.Finish.cdata),
                'duration': duration,
                'predecessors': predecessors,
                'successors': [], # # need to be calculated from PredecessorLink
                'milestone': True if task.Milestone.cdata == '1' else False, 
                'complete': int(task.PercentComplete.cdata),
                'curator': '', # not using for now, but it may become usefull later
                'basicplan_startdate': xml_date_conversion(task.Start.cdata), # equal to start date on a start of the project
                'basicplan_enddate': xml_date_conversion(task.Finish.cdata), # date need to be converted # equal to end date on a start of the project
                'include': [],  # need to be calculated from WBS and OutlineLevel
                'actioners': actioners # will be calculated separately
            })
            # pprint(tasks[i-1])

        # Go through collection of tasks and find it is a someone predecessor
        for record in tasks:
            successors = []
            for task in obj.Project.Tasks.Task:
                if 'PredecessorLink' in task:
                    for predecessor in task.PredecessorLink:            
                        # pprint(predecessor)
                        if record['id'] == int(predecessor.PredecessorUID.cdata):
                            # Recalculate offset from LinkLag, which expressed in tenth of minutes (sic!), so 4800 is 8 hours
                            if int(predecessor.LinkLag.cdata) == 0:
                                offset = 0
                            else:
                                # For project management purposes it's better to be aware of smth earlier than later
                                offset = int(floor(int(predecessor.LinkLag.cdata) / 4800))
                            # print(f"Type of offset: {type(offset)}")
                            successors.append({
                                'id': int(task.UID.cdata),
                                # Type of link (depend_type): Values are 0=FF, 1=FS, 2=SF and 3=SS 
                                # (docs at https://learn.microsoft.com/en-us/office-project/xml-data-interchange/xml-schema-for-the-tasks-element?view=project-client-2016)
                                'depend_type': int(predecessor.Type.cdata),
                                'depend_offset': offset
                            })

                # Also find included tasks
                # Look at outline level to comprehend level of WBS to look for - more than one
                if int(task.OutlineLevel.cdata) > 1:
                # Take part of WBS of task before last dot - this is WBS of Parent task
                    parentWBS = task.WBS.cdata[:task.WBS.cdata.rindex('.')]
                    # Find in gathered tasks list task with such WBS and add UID of task to 'include' sublist
                    if record['WBS'] == parentWBS:
                        record['include'].append(int(task.UID.cdata))

            record['successors'] = successors
     
    else:        
        raise ValueError(f'There are no tasks in provided file. Nothing to do.')

    return tasks, staff


def xml_date_conversion(datestring):
    """
    Convert Project dateTime format (2023-05-15T08:00:00) to inner date format (2023-05-15)
    """

    # Given date from XML, expect dateTime Project format
    datestring = re.search('^\d{4}-\d{2}-\d{2}', datestring)
    if not datestring:
        raise ValueError (f"Error in start date found ({datestring})")
    else:
        datestring = datestring.group()

    return datestring


if __name__ == '__main__':
    main()