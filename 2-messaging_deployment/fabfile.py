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
env_config.setupLoggingInFabfile(log_file)

# Do a fabric run on the string 'command' and log results
run_log = lambda command : env_config.fabricLog(command,run,log_dict)
# Do a fabric run on the string 'command' and log results
sudo_log = lambda command : env_config.fabricLog(command,sudo,log_dict)

################### General functions ########################################

def get_value(config_file, section, parameter):
    crudini_command = "crudini --get {} {} {}".format(config_file, section, parameter)
    return local(crudini_command, capture=True)

def set_value(config_file, section, parameter, value):
    sudo_log("crudini --set {} {} {} {}".format(config_file, section, parameter, value))
    logging.debug('Setting parameter () on section {} of config file {}'.format(parameter,section,config_file))

############################# MESSAGING #####################################

@roles('controller')
def installRabbitMQ():

    # logging info
    global log_dict
    log_dict = {'host_string':env.host_string, 'role':'controller'}

    sudo_log('yum -y install rabbitmq-server')
    #execute(if_error)
    if sudo_log('echo "NODENAME=rabbit@localhost" > /etc/rabbitmq/rabbitmq-env.conf').return_code != 0:
        logging.error('Failed to create rabbitmq-env.conf on host ' + env.host_string)
    #execute(if_error)
    if sudo_log('systemctl enable rabbitmq-server.service').return_code != 0:
        logging.error('Failed to enable rabbitmq-server.service',extra=log_dict)
    if sudo_log('systemctl start rabbitmq-server.service').return_code != 0:
        logging.error('Failed to start rabbitmq-server.service',extra=log_dict)
    if sudo_log('systemctl restart rabbitmq-server.service').return_code != 0:
        logging.error('Failed to restart rabbitmq-server.service',extra=log_dict)
    if sudo_log('firewall-cmd --permanent --add-port=5672/tcp').return_code != 0:
        logging.error('Failed to add port 5672 to firewall',extra=log_dict)
    sudo_log('firewall-cmd --reload')
    sudo_log('rabbitmqctl change_password guest {}'.format(\
        get_value('messaging_config', '""', 'PASSWORD')))
    # Assuming we're using RabbitMQ version 3.3.0 or later, do the next 2 lines
#    sudo_log('if [ ! -f /etc/rabbitmq/rabbitmq.config ]; then' + '\n' 
 #           'echo "[{rabbit, [{loopback_users, []}]}]." >> /etc/rabbitmq/rabbitmq.config' + '\n'
  #          'else' + '\n'
   #         'if ! grep -qe "^[{rabbit, [{loopback_users, []}]}]. A$" "/etc/rabbitmq/rabbitmq.config"; then' + '\n'
    #        'echo "[{rabbit, [{loopback_users, []}]}]." >> /etc/rabbitmq/rabbitmq.config' + '\n'
     #       'fi' + '\n'
      #      'fi')
    #sudo_log('systemctl restart rabbitmq-server.service')
    logging.debug('Installed RabbitMQ',extra=log_dict)


    
################### Deployment ########################################

def deploy():

    # logging info
    global log_dict
    log_dict = {'host_string':'', 'role':''}
    logging.debug('Deploying',extra=log_dict)

    execute(installRabbitMQ)



######################################## TDD #########################################



#        print(green("GOOD"))
 #   else:
  #      print(red("BAD")) 
   #sudo_log("rm -r /tmp/images")



#def tdd():
#    with settings(warn_only=True):
        # Following command lists errors. Find out how to get it to find 
        # specific errors or a certain number of them based on time.
        #sudo_log cat messages | egrep '(error|warning)'
 #       time = installRabbitMQtdd()
  #      check_log(time)
        
@roles('controller')
def installRabbitMQtdd():

    # info for logging
    global log_dict
    log_dict = {'host_string':env.host_string, 'role':env_config.getRole()}

    time = [0]*8
    if sudo_log('yum install rabbitmq-server').return_code != 0:
        logging.error('Failed to install rabbitmq-server',extra=log_dict)
    else:
        logging.debug('Successfully installed rabbitmq-server',extra=log_dict)

    time[0] = run_log('date +"%b %d %R"')
    sudo_log('echo "NODENAME=rabbit@localhost" > /etc/rabbitmq/rabbitmq-env.conf')
    time[1] = run_log('date +"%b %d %R"')

    sudo_log('systemctl enable rabbitmq-server.service')
    time[2] = run_log('date +"%b %d %R"')
    sudo_log('systemctl start rabbitmq-server.service')
    time[3] = run_log('date +"%b %d %R"')
    sudo_log('systemctl restart rabbitmq-server.service')
    time[4] = run_log('date +"%b %d %R"')
    sudo_log('firewall-cmd --permanent --add-port=5672/tcp')
    time[5] = run_log('date +"%b %d %R"')
    sudo_log('firewall-cmd --reload')
    time[6] = run_log('date +"%b %d %R"')
    sudo_log('rabbitmqctl change_password guest {}'.format(
        get_value('messaging_config', '""', 'PASSWORD')))
    time[7] = run_log('date +"%b %d %R"')
    return time

@roles('compute', 'controller', 'network')
def check_log(time):

    # info for logging
    global log_dict
    log_dict = {'host_string':env.host_string, 'role':env_config.getRole()}

    with settings(quiet=True):
        for error_num in range(8):
            run_log('echo {} > time'.format(time[error_num]))
            if run_log("sudo cat /var/log/messages | egrep '(debug|warning|critical)' | grep -f time"):
                # Make it specify which one doesn't work
                print(red("Error in so far unspecified function"))
            else:
                print(green("Success, whatever this is"))
            run_log('rm time')

@roles('controller')
def tdd():
    log_dict = {'host_string':'', 'role':''}
    logging.debug('Running TDD function',extra=log_dict)
    with settings(warn_only=True):
        time = installRabbitMQtdd()
        execute(check_log,time)

