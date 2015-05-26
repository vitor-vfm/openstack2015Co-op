from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
import string

import sys
sys.path.append('../global_config_files')
import env_config


############################ Config ########################################

env.roledefs = env_config.roledefs

# get passwords from their config file
passwd = env_config.read_dict('config_files/passwd')

# define config file locations
database_script_file = 'config_files/database_creation.sql'

################### General functions ########################################


################### Deployment ########################################

@roles('controller')
def controller_deploy():
    
    # CREATE NEUTRON DATABASE

    database_script = open(database_script_file,'r').read() 
    # subtitute real password
    database_script = database_script.replace("NEUTRON_DBPASS",passwd["NEUTRON_DBPASS"])
    # send the commands to mysql client
    sudo("echo '{}' | mysql -u root".format(database_script))


    

@roles('network')
def network__deploy():
    pass

@roles('compute')
def compute__deploy():
    pass

def deploy():
    with settings(warn_only=True):
        execute(controller_deploy)

######################################## TDD #########################################

def tdd():
    with settings(warn_only=True):
        pass
