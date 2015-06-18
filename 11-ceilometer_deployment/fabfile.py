from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.contrib.files import append
import logging
import string

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, createDatabaseScript, set_parameter
from myLib import database_check, keystone_check, run_v, align_n, align_y

############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

ceilometer_config_file = "/etc/ceilometer/ceilometer.conf"


######################## Deployment ########################################
   
@roles('controller')
def setup_ceilometer_controller():
    pass

################################## Deployment ########################################

def deploy():
    execute(setup_ceilometer)

######################################## TDD #########################################

def tdd():
    with settings(warn_only=True):
        execute(database_check,'ceilometer',roles=['controller'])
        execute(keystone_check,'ceilometer',roles=['controller'])
