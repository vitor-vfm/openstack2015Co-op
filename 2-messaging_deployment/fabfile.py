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
import env_config
from env_config import log_debug, log_info, log_error, run_log, sudo_log

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


# Logging config
log_file = 'rabbit_deployment.log'
env_config.setupLoggingInFabfile(log_file)



################### General functions ########################################

def get_value(config_file, section, parameter):
    crudini_command = "crudini --get {} {} {}".format(config_file, section, parameter)
    return local(crudini_command, capture=True)

def set_value(config_file, section, parameter, value):
    sudo_log("crudini --set {} {} {} {}".format(config_file, section, parameter, value))
    log_debug('Setting parameter () on section {} of config file {}'.format(parameter,section,config_file))

############################# MESSAGING #####################################

@roles('controller')
def installRabbitMQ():

    sudo_log('yum -y install rabbitmq-server')
    #execute(if_error)
    if sudo_log('echo "NODENAME=rabbit@localhost" > /etc/rabbitmq/rabbitmq-env.conf').return_code != 0:
        log_error('Failed to create rabbitmq-env.conf on this host ')
    #execute(if_error)
    if sudo_log('systemctl enable rabbitmq-server.service').return_code != 0:
        log_error('Failed to enable rabbitmq-server.service')
    if sudo_log('systemctl start rabbitmq-server.service').return_code != 0:
        log_error('Failed to start rabbitmq-server.service')
    if sudo_log('systemctl restart rabbitmq-server.service').return_code != 0:
        log_error('Failed to restart rabbitmq-server.service')
    if sudo_log('firewall-cmd --permanent --add-port=5672/tcp').return_code != 0:
        log_error('Failed to add port 5672 to firewall')
    sudo_log('firewall-cmd --reload')

@roles('controller')
def change_password():
    sudo_log('rabbitmqctl change_password guest {}'.format(passwd['RABBIT_PASS']))
    if sudo_log('systemctl restart rabbitmq-server.service').return_code != 0:
        logging.error('Failed to restart rabbitmq-server.service',extra=log_dict)

    # Assuming we're using RabbitMQ version 3.3.0 or later, do the next 2 lines
#    sudo_log('if [ ! -f /etc/rabbitmq/rabbitmq.config ]; then' + '\n' 
 #           'echo "[{rabbit, [{loopback_users, []}]}]." >> /etc/rabbitmq/rabbitmq.config' + '\n'
  #          'else' + '\n'
   #         'if ! grep -qe "^[{rabbit, [{loopback_users, []}]}]. A$" "/etc/rabbitmq/rabbitmq.config"; then' + '\n'
    #        'echo "[{rabbit, [{loopback_users, []}]}]." >> /etc/rabbitmq/rabbitmq.config' + '\n'
     #       'fi' + '\n'
      #      'fi')
    #sudo_log('systemctl restart rabbitmq-server.service')
    log_debug('Installed RabbitMQ')


    
################### Deployment ########################################

def deploy():

    log_debug('Deploying')

    execute(installRabbitMQ)
    execute(change_password)


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

    time = [0]*8
    if sudo_log('yum install rabbitmq-server').return_code != 0:
        log_error('Failed to install rabbitmq-server')
    else:
        log_debug('Successfully installed rabbitmq-server')

    confFile = '/etc/rabbitmq/rabbitmq-env.conf'

    # make a backup
    sudo_log("cp {} {}.bak".format(confFile,confFile))

    if mode == 'debug':
        # make changes to back up file
        confFile += '.bak'

    time[0] = run_log('date +"%b %d %R"')
    sudo_log('echo "NODENAME=rabbit@localhost" > ' + confFile)
    if mode == 'debug':
        print blue("NODENAME will be set to rabbit@localhost")
        print "New file: "
        sudo_log("cat " + confFile)

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
    sudo_log('rabbitmqctl change_password guest {}'.format(passwd['RABBIT_PASS']))
    time[7] = run_log('date +"%b %d %R"')
    return time

@roles('compute', 'controller', 'network')
def check_log(time):

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
    log_debug('Running TDD function')
    with settings(warn_only=True):
        time = installRabbitMQtdd()
        execute(check_log,time)

