from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import string
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



################### General functions ########################################

def get_value(config_file, section, parameter):
    crudini_command = "crudini --get {} {} {}".format(config_file, section, parameter)
    return local(crudini_command, capture=True)

def set_value(config_file, section, parameter, value):
    sudo("crudini --set {} {} {} {}".format(config_file, section, parameter, value))

############################# MESSAGING #####################################

@roles('controller')
def installRabbitMQ():
    sudo('yum install rabbitmq-server')
    #execute(if_error)
    sudo('echo "NODENAME=rabbit@localhost" > /etc/rabbitmq/rabbitmq-env.conf')
    #execute(if_error)
    sudo('systemctl enable rabbitmq-server.service')
    sudo('systemctl start rabbitmq-server.service')
    sudo('systemctl restart rabbitmq-server.service')
    sudo('firewall-cmd --permanent --add-port=5672/tcp')
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


    
################### Deployment ########################################

def deploy():
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
    time = [0]*8
    sudo('yum install rabbitmq-server')
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
                print(red("Oh... Oh god no..."))
            else:
                print(green("Weeee are the Chaaampions..."))
            run('rm time')

@roles('controller')
def tdd():
    with settings(warn_only=True):
        time = installRabbitMQtdd()
        execute(check_log,time)

