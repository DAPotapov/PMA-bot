import pprint
import untangle
import json

from numpy import busday_offset, datetime64


def main():
    '''
    Module recieve PosixPath of downloaded file.
    Returns JSON of project schedule and assignments
    If error occured should return at least string of error message, but maybe there is better way of error handling

    '''
    
    return

def load_gan(fp):
    '''
        This is a connector from GanttProject format (.gan) to inner JSON format.
        На входе получаем имя файла (.gan )
        Выполняем парсинг
        Затем преобразовываем к внутреннему формату: берем только нужные элементы
        Имеем json на выходе
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
                tasks = compose_tasks_list(tasks, task, allocations)
                # if task has subtask retreive data from it too
                if 'task' in task:
                    for task in task.task:
                        tasks = compose_tasks_list(tasks, task, allocations)

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
        if custom_property['name'] == 'telegram_id':
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
            telegram_id = ''
            for property in actioner.custom_property:
                if property['definition-id'] == property_id:
                    # If such property not filled then abort and tell user to do his job and make a proper file
                    if not property['value']:
                        raise ValueError(f"'{actioner['name']}' have no telegram_id value")
                    else:
                        telegram_id = property['value']

            # Build list of actioners
            actioners.append({
                'id' : actioner['id'],
                'name' : actioner['name'],
                'email' : actioner['contacts'],
                'phone' : actioner['phone'],
                'telegram_id' : telegram_id,
            })
    # If no custom property for telegram_id found then inform the user
    else:
        raise AttributeError("Project file has invalid structure: no 'telegram_id' field")
    
    # Append actioners list to project dictionary
    project['actioners'] = actioners

    return project


def compose_tasks_list(list, task, allocations):
    ''' Function to append to list of tasks information of one task or subtask'''

    # Dictionary of id of actioners and their last reaction
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
        for task in task.task:
            include.append(int(task['id']))
    
    # Construct dictionary of task and append to list of tasks   
    if task['meeting'].lower() == "false":
        milestone = False
    elif task['meeting'].lower() == "true":
        milestone = True
    else:
        raise ValueError('File may be damaged: milestone field contains invalid value ' + str(task['meeting']))
    
    # Construct end date from start date, duration and numpy function:
    # TODO in v.2: project apps supports alternative calendars, bot should support them as well.
    enddate = str(busday_offset(datetime64(task['start']), int(task['duration']), roll='forward'))

    list.append({
                'id': int(task['id']),
                'name': task['name'],
                'startdate': task['start'],
                'end_date': enddate, 
                'duration': int(task['duration']),
                'successors': successors,
                'milestone': milestone,
                'complete': int(task['complete']),
                'curator': '', # not using for now, but it may become usefull later
                'basicplan_startdate': task['start'], # equal to start date on a start of the project
                'basicplan_enddate': enddate, # equal to end date on a start of the project
                'include': include,
                'successors': successors,
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

if __name__ == '__main__':
    main()