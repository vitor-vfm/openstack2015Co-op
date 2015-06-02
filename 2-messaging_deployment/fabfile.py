from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import string
import paramiko
import logging
import sys
sys.path.append('../global_config_files')
import env_config

@roles('compute')
def if_error():
        sudo('if [[ $? -ne 0 ]]; then # check return code passed to function' + '\n'
        'print "$1 TIME:$TIME" | tee -a /var/log # if rc > 0 then print error msg and quit' + '\n'
        'exit $?' + '\n'
        'fi')

############################ Config ########################################

env.roledefs = env_config.roledefs

messaging_config_file = 'messaging_config'


# Logging config

log_file = 'rabbit_deployment.log'
logfilename = env_config.log_location + log_file

if log_file not in local('ls ' + env_config.log_location,capture=True):
    # file doesn't exist yet; create it
    local('touch ' + logfilename,capture=True)
    local('chmod 644 ' + logfilename,capture=True)

logging.basicConfig(filename=logfilename,level=logging.DEBUG,format=env_config.log_format)
# set paramiko logging to only output warnings
logging.getLogger("paramiko").setLevel(logging.WARNING)

################### General functions ########################################

def get_value(config_file, section, parameter):
    crudini_command = "crudini --get {} {} {}".format(config_file, section, parameter)
    return local(crudini_command, capture=True)

def set_value(config_file, section, parameter, value):
    sudo("crudini --set {} {} {} {}".format(config_file, section, parameter, value))
    logging.debug('Setting parameter () on section {} of config file {}'.format(parameter,section,config_file))

############################# MESSAGING #####################################

@roles('controller')
def installRabbitMQ():

    log_dict = {'host_string':env.host_string, 'role':'controller'}
    logging.debug(sudo('yum install rabbitmq-server'),extra=log_dict)
    #execute(if_error)
    if sudo('echo "NODENAME=rabbit@localhost" > /etc/rabbitmq/rabbitmq-env.conf').return_code != 0:
        logging.error('Failed to create rabbitmq-env.conf on host ' + env.host_string)
    #execute(if_error)
    if sudo('systemctl enable rabbitmq-server.service').return_code != 0:
        logging.error('Failed to enable rabbitmq-server.service',extra=log_dict)
    if sudo('systemctl start rabbitmq-server.service').return_code != 0:
        logging.error('Failed to start rabbitmq-server.service',extra=log_dict)
    if sudo('systemctl restart rabbitmq-server.service').return_code != 0:
        logging.error('Failed to restart rabbitmq-server.service',extra=log_dict)
    if sudo('firewall-cmd --permanent --add-port=5672/tcp').return_code != 0:
        logging.error('Failed to add port 5672 to firewall',extra=log_dict)
    sudo('firewall-cmd --reload')
    sudo('rabbitmqctl change_password guest {}'.format(
        get_value('messaging_config', '""', 'PASSWORD')), quiet=True)
    # Assuming we're using RabbitMQ version 3.3.0 or later, do the next 2 lines
#    sudo('if [ ! -f /etc/rabbitmq/rabbitmq.config ]; then' + '\n' 
 #           'echo "[{rabbit, [{loopback_users, []}]}]." >> /etc/rabbitmq/rabbitmq.config' + '\n'
  #          'else' + '\n'
   #         'if ! grep -qe "^[{rabbit, [{loopback_users, []}]}]. A$" "/etc/rabbitmq/rabbitmq.config"; then' + '\n'
    #        'echo "[{rabbit, [{loopback_users, []}]}]." >> /etc/rabbitmq/rabbitmq.config' + '\n'
     #       'fi' + '\n'
      #      'fi')
    #sudo('systemctl restart rabbitmq-server.service')
    logging.debug('Installed RabbitMQ',extra=log_dict)


    
################### Deployment ########################################

def deploy():
    log_dict = {'host_string':'', 'role':''}
    logging.debug('Deploying',extra=log_dict)
    execute(installRabbitMQ)



######################################## TDD #########################################



#        print(green("GOOD"))
 #   else:
  #      print(red("BAD")) 
   #sudo("rm -r /tmp/images")



#def tdd():
#    with settings(warn_only=True):
        # Following command lists errors. Find out how to get it to find 
        # specific errors or a certain number of them based on time.
        #sudo cat messages | egrep '(error|warning)'
 #       time = installRabbitMQtdd()
  #      check_log(time)
        
@roles('controller')
def installRabbitMQtdd():

    log_dict = {'host_string':env.host_string, 'role':'controller'}
    time = [0]*8
    if sudo('yum install rabbitmq-server').return_code != 0:
        logging.error('Failed to install rabbitmq-server')
    else:
        logging.debug('Successfully installed rabbitmq-server')

    time[0] = run('date +"%b %d %R"')
    sudo('echo "NODENAME=rabbit@localhost" > /etc/rabbitmq/rabbitmq-env.conf')
    time[1] = run('date +"%b %d %R"')

    sudo('systemctl enable rabbitmq-server.service')
    time[2] = run('date +"%b %d %R"')
    sudo('systemctl start rabbitmq-server.service')
    time[3] = run('date +"%b %d %R"')
    sudo('systemctl restart rabbitmq-server.service')
    time[4] = run('date +"%b %d %R"')
    sudo('firewall-cmd --permanent --add-port=5672/tcp')
    time[5] = run('date +"%b %d %R"')
    sudo('firewall-cmd --reload')
    time[6] = run('date +"%b %d %R"')
    sudo('rabbitmqctl change_password guest {}'.format(
        get_value('messaging_config', '""', 'PASSWORD')), quiet=True)
    time[7] = run('date +"%b %d %R"')
    return time

@roles('compute', 'controller', 'network')
def check_log(time):
    with settings(quiet=True):
        for error_num in range(8):
            run('echo {} > time'.format(time[error_num]))
            if run("sudo cat /var/log/messages | egrep '(debug|warning|critical)' | grep -f time"):
                # Make it specify which one doesn't work
                print(red("Error in so far unspecified function"))
            else:
                print(green("Success, whatever this is"))
            run('rm time')

@roles('controller')
def tdd():
    log_dict = {'host_string':'', 'role':''}
    logging.debug('Running TDD function',extra=log_dict)
    with settings(warn_only=True):
        time = installRabbitMQtdd()
        execute(check_log,time)

