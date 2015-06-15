from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.state import output
from fabric.contrib.files import append
import string
import paramiko
import logging
import sys
sys.path.append('../global_config_files')
sys.path.append('..')
from myLib import runCheck
import env_config

@roles('compute')
def if_error():
        sudo('if [[ $? -ne 0 ]]; then # check return code passed to function' + '\n'
        'print "$1 TIME:$TIME" | tee -a /var/log # if rc > 0 then print error msg and quit' + '\n'
        'exit $?' + '\n'
        'fi')

############################ Config ########################################

# set mode
mode = 'normal'
if output['debug']:
    mode = 'debug'

env.roledefs = env_config.roledefs
passwd = env_config.passwd

######################### General functions ################################

def get_value(config_file, section, parameter):
    crudini_command = "crudini --get {} {} {}".format(config_file, section, parameter)
    return local(crudini_command, capture=True)

def set_value(config_file, section, parameter, value):
    run("crudini --set {} {} {} {}".format(config_file, section, parameter, value))

########################### Deployment #####################################

@roles('controller')
def installRabbitMQ():

    msg = "Install rabbitmq-server"
    runCheck(msg, 'yum -y install rabbitmq-server')

    msg = "Set NODENAME on rabbit-env.conf"
    runCheck(msg, 'echo "NODENAME=rabbit@localhost" > /etc/rabbitmq/rabbitmq-env.conf')

    msg = "Enable rabbitmq service"
    runCheck(msg, 'systemctl enable rabbitmq-server.service')

    msg = "Start rabbitmq service"
    runCheck(msg, 'systemctl start rabbitmq-server.service')

    # Unnecessary since we don't have a firewall between the nodes
    # if run('firewall-cmd --permanent --add-port=5672/tcp').return_code != 0:
    # run('firewall-cmd --reload')

@roles('controller')
def setGuestPassword():
    """
    Set password for user 'guest' according to passwd dictionary
    """

    msg = "Set password for user guest"
    runCheck(msg, 'rabbitmqctl change_password guest ' + passwd['RABBIT_PASS'])

    msg = "Restart rabbitmq service"
    runCheck(msg, 'systemctl restart rabbitmq-server.service')

def deploy():
    execute(installRabbitMQ)
    execute(setGuestPassword)

######################################## TDD #########################################

def runAndRecordTime(command,timestamps):
    """
    Run the command, record the current system time on the host,
    and append the result, as a tuple, to the list 'timestamps'.

    Worker for installRabbitMQtdd
    """
    run(command)
    time = run('date +"%b %d %R"')
    timestamps.append( (command,time) )
        
@roles('controller')
def installRabbitMQtdd():
    """
    Perform several operations using rabbit, record the time
    in which they were made and use them to later check
    /var/log/messages for errors

    Inputs: none

    Outputs: A list of tuples (command,time)
    """

    timestamps = list()

    confFile = '/etc/rabbitmq/rabbitmq-env.conf'

    command = 'echo "NODENAME=rabbit@localhost" > ' + confFile
    runAndRecordTime(command,timestamps)

    command = 'systemctl enable rabbitmq-server.service'
    runAndRecordTime(command,timestamps)

    command = 'systemctl start rabbitmq-server.service'
    runAndRecordTime(command,timestamps)

    command = 'systemctl restart rabbitmq-server.service'
    runAndRecordTime(command,timestamps)

    command = 'rabbitmqctl change_password guest {}'.format(passwd['RABBIT_PASS'])
    runAndRecordTime(command,timestamps)

    return timestamps

@roles('controller')
def check_log(timestamps):
    """
    Look for errors in /var/log/messages
    at the times specified by timestamps

    Print results
    """

    with settings(quiet=True):
        for command, time in timestamps:
            # Grep for message levels "ERROR", "WARNING", and "CRITICAL" and for the timestamp
            error = run("cat /var/log/messages | egrep -i '(error|warning|critical)' | grep '{}'".format(time))

            if error:
                print red("/var/log/messages shows an error when the following command was run")
                print red("Command: " + command)
                print red("Log error message: ")
                print red(error)
            else:
                print(green("No error when the command '{}' was run".format(command)))

@roles('controller')
def tdd():
    with settings(warn_only=True):
        time = installRabbitMQtdd()
        execute(check_log,time)

