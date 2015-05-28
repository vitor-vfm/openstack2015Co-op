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
    sudo('echo "NODENAME=rabbit@localhost" > /etc/rabbitmq/rabbitmq-env.conf')
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
