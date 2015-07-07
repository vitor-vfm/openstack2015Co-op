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
sys.path.append('..')
from myLib import runCheck, saveConfigFile, printMessage
import env_config

############################### Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

############################## Deployment #####################################
@roles('controller')
def installRabbitMQ():
    msg= "install rabbitmq-server erlang-sd_notify"
    runCheck(msg, 'yum -y install rabbitmq-server erlang-sd_notify')
    run('systemctl enable rabbitmq-server.service')
    run('systemctl start rabbitmq-server.service')
    run('systemctl restart rabbitmq-server.service')
    msg="Changing rabbit guest password "
    runCheck(msg, 'rabbitmqctl change_password guest %s' % passwd['RABBIT_PASS'])

def deploy():
    execute(installRabbitMQ)

@roles('controller')
def tdd():
    with settings(hide('everything'),warn_only=True):
        msg=" testing RabbitMQ status"
        runCheck(msg, 'rabbitmqctl status')

