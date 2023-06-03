import pprint
import re
import untangle
import json

from numpy import busday_offset, busday_count, datetime64
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
    project = {}

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

    # Append tasks list to project dictionary
    project['tasks'] = tasks
    actioners = []
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
            actioners.append({
                'id' : int(actioner['id']),
                'name' : actioner['name'],
                'email' : actioner['contacts'],
                'phone' : actioner['phone'],
                'tg_username' : tg_username,
            })
    # If no custom property for tg_username found then inform the user
    else:
        raise AttributeError("Project file has invalid structure: no 'tg_username' field")
    
    # Append actioners list to project dictionary
    project['actioners'] = actioners

    return project


def compose_tasks_list(list, task, allocations):
    ''' Function to append to list of tasks information of one task or subtask'''

    # Dictionary of id of actioners and their last reaction
    # pprint(f"Function got these parameters:\n {list}\n{task['name']}\n{allocations}")
    actioners = [] 
    for allocation in allocations:
        if task['id'] == allocation['task-id']:
            actioners.append({
                'actioner_id': int(allocation['resource-id']),
                'nofeedback': False # Default. Will be changed to True if person didn't answer to bot
                })
                             
    # Dictionary of tasks which succeed from this one
    successors = []
    if 'depend' in dir(task):
        for follower in task.depend:
            successors.append({
                'id': int(follower['id']),
                'depend_type': follower['type'],
                'depend_offset': int(follower['difference'])
                })
                # depend types:
                # 0 - none
                # 1 - start-start SS
                # 2 - finish-start FS
                # 3 - finish-finish FF
                # 4 - start-finish SF - usually not used

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
    # Construct end date from start date, duration and numpy function:
    # TODO it calculates in between: on a begining of end date task already must be done, end date not exactly the day of deadline
    # Should be reconsidered: GanttProject itself calculates right
    enddate = str(busday_offset(datetime64(task['start']), int(task['duration']), roll='forward'))

    list.append({
                'id': int(task['id']),
                'name': task['name'],
                'startdate': task['start'],
                'enddate': enddate, 
                'duration': int(task['duration']),
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
    # TODO:
    # 1. Limit size of data to load to prevent attacks
    # 2. 
    
    project = json.load(fp)
    # TODO check if it seems like project. Look for inner format structure
    return project


def load_xml(fp):
    """ 
    Function to import from MS Project XML file 
    Get file pointer on input
    Validates and converts data to inner dict-list-dict.. format
    Dictionary on output    
    """

    project = {}
    actioners = []
    tasks = []
    # Store XML inner ID for field where telegram username located
    property_id = ''

    obj = untangle.parse(str(fp))

    #TODO consider adding version check if difficulties ocurred 

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
            # Get telegram username from XML for this actioner
            tg_username = ''
            for attr in actioner.ExtendedAttribute:
                if attr.FieldID.cdata == property_id:
                    tg_username = attr.Value.cdata
            if not tg_username:
                raise ValueError(f"'{actioner.Name.cdata}' have no tg_username value") 
            actioners.append({
                'id' : int(actioner.UID.cdata),
                'name' : actioner.Name.cdata,
                'email' : actioner.EmailAddress.cdata,
                # Seems like MS Project does not know about phones :) 
                # Maybe I'll use ExtendedAttribute for this purpose later
                'phone' : '',
                'tg_username' : tg_username               
            })
    else:
        raise ValueError('There are no actioners (resources) in provided file. Who gonna work?')

    # Add collected actioners to project dictionary
    project['actioners'] = actioners

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
                duration = busday_count(xml_date_conversion(task.Start.cdata), xml_date_conversion(task.Finish.cdata)) + 1
            # print(f"Start: {task.Start.cdata}, End: {task.Finish.cdata}, duration: {duration}")

            # Offset should be recalculated from LinkLag, which expressed in tenth of minutes (sic!), so 4800 is 8 hours
            # Type of link: Values are 0=FF, 1=FS, 2=SF and 3=SS (docs at https://learn.microsoft.com/en-us/office-project/xml-data-interchange/xml-schema-for-the-tasks-element?view=project-client-2016)
            # Consider using this one instead of Gantt (and change in that function)
            include = []

            tasks.append({
                'id': int(task.UID.cdata),
                'WBS': task.WBS.cdata, # this field is useful for determining inclusion of tasks
                'name': task.Name.cdata,
                'startdate': xml_date_conversion(task.Start.cdata), 
                'enddate': xml_date_conversion(task.Finish.cdata),
                'duration': duration,
                'successors': [], # # need to be calculated from PredecessorLink
                'milestone': True if task.Milestone.cdata == '1' else False, 
                'complete': int(task.PercentComplete.cdata),
                'curator': '', # not using for now, but it may become usefull later
                'basicplan_startdate': xml_date_conversion(task.Start.cdata), # equal to start date on a start of the project
                'basicplan_enddate': xml_date_conversion(task.Finish.cdata), # date need to be converted # equal to end date on a start of the project
                'include': [],  # need to be calculated from WBS and OutlineLevel
                'actioners': [] # will be calculated separately
            })
            # pprint(tasks[i-1])

        # Start loop again to 
        for task in obj.Project.Tasks.Task:
            # find predecessors and fill them
            if 'PredecessorLink' in task:
                for record in tasks:
                    for predecessor in task.PredecessorLink:
                        # pprint(predecessor)
                        if record['id'] == int(predecessor.PredecessorUID.cdata):
                            record['successors'].append(int(task.UID.cdata))
            
            # And to find included tasks
            if task.Type.cdata == '0':
                # Look at outline level to comprehend level of WBS to look for - more than one
                if int(task.OutlineLevel.cdata) > 1:
                # Take part of WBS of task before last dot - this is WBS of Parent task
                    parentWBS = task.WBS.cdata[:task.WBS.cdata.rindex('.')]
                    # Find in gathered tasks list task with such WBS and add UID of task to 'include' sublist
                    for record in tasks:
                        if record['WBS'] == parentWBS:
                            record['include'].append(int(task.UID.cdata))

    else:        
        raise ValueError('There are no tasks in provided file. Nothing to do.')

    # Add collected tasks to project dictionary
    project['tasks'] = tasks

    return project

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