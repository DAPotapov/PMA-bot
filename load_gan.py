import pprint
import untangle
import json

from numpy import busday_offset, datetime64


def main():
    '''
    This is a connector from GanttProject format (.gan) to inner JSON format.
    На входе получаем имя файла (.gan )
    Выполняем парсинг
    Затем преобразовываем к внутреннему формату: берем только нужные элементы
    Имеем json на выходе
    '''

    # Using untangle on GAN - WORKING. This syntax cleaner and have some useful methods like 'children'
    # Declare dictionary to store data
    project = {
        'tasks' : [],
        'actioners': []
        }
    tasks = []
    filename = "data/test1.gan"
    try:
        obj = untangle.parse(filename)
    except:
        print('Oh no! Error occured!')
    else:
        # Loop through tasks
        for task in obj.project.tasks.task:
            # Add relevant data to list containing task information
            allocations = obj.project.allocations.allocation
            try:
                tasks = compose_tasks_list(tasks, task, allocations)
            except Exception as e:
                print("Error occured: " + str(e))
            else:
                # if task has subtask retreive data from it too
                if 'task' in task:
                    for task in task.task:
                        try:
                            tasks = compose_tasks_list(tasks, task, allocations)
                        except Exception as e:
                            print("Error occured: " + str(e))

        # TODO Resolving GanttProject bug of duplication of resource allocation. 
        # Better use standalone function in case they will fix this bug

        # Append tasks list to project dictionary
        project['tasks'] = tasks

        actioners = []
        for actioner in obj.project.resources.resource:
            # TODO Add check if special field for telegram id exist and to choose correct 
            # custom property if there are several of them
            telegram_id = actioner.custom_property['value']
            # Build list of actioners
            actioners.append({
                'id' : actioner['id'],
                'name' : actioner['name'],
                'email' : actioner['contacts'],
                'phone' : actioner['phone'],
                'telegram_id' : telegram_id,
            })
        # Append actioners list to project dictionary
        project['actioners'] = actioners

    # Save project to file TEMPORARY TODO Remove. It should be on other side
    json_file = "data/temp.json"
    # TODO add error handling
    with open(json_file, 'w') as json_fh:
        json.dump(project, json_fh)


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
    # TODO: construct end date from start date, duration and numpy function:
    #  https://numpy.org/doc/stable/reference/routines.datetime.html
    # TODO in v.2: project apps supports alternative calendars, bot should support them as well.
    if task['meeting'].lower() == "false":
        milestone = False
    elif task['meeting'].lower() == "true":
        milestone = True
    else:
        raise ValueError('File may be damaged: milestone field contains invalid value ' + str(task['meeting']))

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


if __name__ == '__main__':
    main()