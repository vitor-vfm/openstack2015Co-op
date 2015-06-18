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

def setup_ceilometer_keystone(CEILOMETER_PASS):
    """
    Set up Keystone credentials for Ceilometer

    Create (a) a user and a service called 'ceilometer', and 
    (b) an endpoint for the 'ceilometer' service
    """

    # get admin credentials to run the CLI commands
    credentials = env_config.admin_openrc

    with prefix(credentials):
        # before each creation, we check a list to avoid duplicates

        if 'ceilometer' not in run("keystone user-list"):
            msg = "Create user ceilometer"
            runCheck(msg, "keystone user-create --name ceilometer --pass {}".format(CEILOMETER_PASS))

            msg = "Give the user 'ceilometer the role of admin"
            runCheck(msg, "keystone user-role-add --user ceilometer --tenant service --role admin")
        else:
            print blue("User ceilometer already created. Do nothing")

        if 'ceilometer' not in run("keystone service-list"):
            msg = "Create service ceilometer"
            runCheck(msg, "keystone service-create --name ceilometer --type image --description 'Telemetry'")
        else:
            print blue("Service ceilometer already created. Do nothing")

        if 'http://controller:9292' not in run("keystone endpoint-list"):
            msg = "Create endpoint for service ceilometer"
            runCheck(msg, "keystone endpoint-create " + \
                    "--service-id $(keystone service-list | awk '/ metering / {print $2}') " +\
                    "--publicurl http://controller:8777 " + \
                    "--internalurl http://controller:8777 " + \
                    "--adminurl http://controller:8777 " + \
                    "--region regionOne")
        else:
            print blue("Endpoint for service ceilometer already created. Do nothing")
   
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
