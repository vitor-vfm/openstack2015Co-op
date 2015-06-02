#! /usr/bin/python

usage = \
'\n  A script to parse and display logs\n' + \
'\n' + \
'   Usage:\n' + \
'       checkLog.py [log] [options]\n' + \
'\n' + \
'       log = the program whose log you want to see;\n' + \
'             can be "all" to display all the logs \n' + \
'\n' + \
'       options:\n' + \
'\n' + \
'           -t [n] = take only the last n lines\n' + \
'           -d [date] = take only lines from the specified date;\n' + \
'                       can be "today"                         \n' + \
'           -h = display this message\n'


import sys
from subprocess import check_output


############### Config #####################

# logs directories
deploymentLogsDirectory = 'var/log/juno/'
openstackComponentsLogsDirectory = '/var/log/'

# dictionaries that map parameters to files
# fill them up later
componentsLogs = { 'nova' : 'nova/nova.config',
                   'rabbit' : 'rabbitmq/rabbitmq.config',
                   # for testing:
                   'kern' : 'kern.log'}

deploymentLogs = {'basic_networking' : 'basic-network.log',
                  'rabbit' : 'rabbit_deployment.log'}

# add directories to the front of the values
componentsLogs = { k : openstackComponentsLogsDirectory + componentsLogs[k] \
        for k in componentsLogs.keys() }

deploymentLogs = { k : deploymentLogsDirectory + deploymentLogs[k] \
        for k in deploymentLogs.keys() }

############# Log display #####################

def showLog(log,date="",past="",tail=""):
    # prints a log to the screen, according to specifications
    log_lines = open(log,'r').readlines()

    if date:
        # filter according to the date
        if date.lower() == 'today':
            date = check_output('date -Idate',shell=True)
        log_lines = [line for line in log_lines if date in line]

    if tail:
        # grab only the last X lines
        try:
            nLines = int(tail)
        except:
            raise ValueError("Invalid parameter for tail (-t)")

        log_lines = log_lines[-nLines:]

    # if past:
        # filter to only the past X hours or minutes
        # currentTime = check_output("date +'%H %M %S'",shell=True).split()
        # if past.lower()[-1] == 'm':
        #     # user wants logs from the past X minutes
        #     minutesAgo = int(past[:-1])
            
        #     initalTime[3] = '00'
        #     initalTime[2] = currentTime[2]
        #     currentTime[0] -= minutes // 60
        # log_lines = [line for line in log_lines if date in line]

    # concatenate lines and return them
    return "".join(log_lines)

def main(args):

    if '-h' in args:
        print usage
        return

    log = args[0].lower()
    if log in deploymentLogs:
        log_file = deploymentLogs[log]
    elif log in componentsLogs:
        log_file = componentsLogs[log]
    elif log != 'all':
        raise ValueError('Not a valid log parameter : ' + log)

    date = past = tail = ""
    if '-d' in args:
        date = args[ args.index('-d') + 1 ]
    if '-p' in args:
        past = args[ args.index('-p') + 1 ]
    if '-t' in args:
        tail = args[ args.index('-t') + 1 ]

    if log == 'all':
        allLogs = [l for l in deploymentLogs.values() ] + \
                [l for l in componentsLogs.values() ]
        for l in allLogs:
            print showLog(l,date,past,tail)
    else:
        print showLog(log_file,date,past,tail)





if __name__=="__main__":
    main(sys.argv[1:])

