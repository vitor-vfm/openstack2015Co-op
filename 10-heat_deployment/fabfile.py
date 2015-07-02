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
from myLib import database_check, keystone_check, saveConfigFile


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

etc_heat_config_file = "/etc/heat/heat.conf"
heat_test_file = "test_file/test-stack.yml"

# global variable to be used in the TDD functions
status = str()

################### General functions ########################################

def setup_heat_database(HEAT_DBPASS):

    mysql_commands = createDatabaseScript('heat',HEAT_DBPASS)
    
    msg = 'Create database for heat'
    runCheck(msg, 'echo "{}" | mysql -u root -p{}'.format(mysql_commands, env_config.passwd['ROOT_SECRET']))
    


def setup_heat_keystone(HEAT_PASS):
    """
    Create a user, a tenant, etc. in Keystone for Heat
    """

    # get credentials
    with prefix(env_config.admin_openrc):

        if 'heat' not in run("keystone user-list"):
            msg = 'Create user heat'
            runCheck(msg, "keystone user-create --name heat --pass {}".format(HEAT_PASS))
            msg = 'Add role of admin to user heat'
            runCheck(msg, "keystone user-role-add --user heat --tenant service --role admin")
        else:
            print blue('heat is already a user. Do nothing')

        if 'heat_stack_owner' not in run("keystone role-list"):
            msg = "Create role heat_stack_owner"
            runCheck(msg, "keystone role-create --name heat_stack_owner")
            msg = "Add the role of heat_stack_owner to user demo"
            runCheck(msg, "keystone user-role-add --user demo --tenant demo --role heat_stack_owner")
        else:
            print blue('heat_stack_owner is already a role. Do nothing')

        if 'heat_stack_user' not in sudo("keystone role-list"):
            msg = "Create role heat_stack_user"
            runCheck(msg, "keystone role-create --name heat_stack_user")
        else:
            print blue('heat_stack_user is already a role. Do nothing')

        if 'heat' not in sudo("keystone service-list"):
            msg = 'Create service heat'
            runCheck(msg, 'keystone service-create --name heat --type orchestration --description "Orchestration"')
        else:
            print blue('heat is already a service. Do nothing')

        if 'heat-cfn' not in sudo("keystone service-list"):
            msg = 'Create service heat-cfn'
            runCheck(msg, 'keystone service-create --name heat-cfn --type cloudformation --description "Orchestration"')
        else:
            print blue('heat-cfn is already a service. Do nothing')
        
        if 'http://controller:8004' not in sudo("keystone endpoint-list"):
            runCheck(msg, """keystone endpoint-create \
            --service-id $(keystone service-list | awk '/ orchestration / {print $2}') \
            --publicurl http://controller:8004/v1/%\(tenant_id\)s \
            --internalurl http://controller:8004/v1/%\(tenant_id\)s \
            --adminurl http://controller:8004/v1/%\(tenant_id\)s \
            --region regionOne""")
        else:
            print blue('8004 is already an endpoint. Do nothing')

        if 'http://controller:8000' not in sudo("keystone endpoint-list"):
            runCheck(msg, """keystone endpoint-create \
            --service-id $(keystone service-list | awk '/ cloudformation / {print $2}') \
            --publicurl http://controller:8000/v1 \
            --internalurl http://controller:8000/v1 \
            --adminurl http://controller:8000/v1 \
            --region regionOne""")
        else:
            print blue('8000 is already an endpoint. Do nothing')
        
def setup_heat_config_files(HEAT_PASS, HEAT_DBPASS, RABBIT_PASS):
    msg = 'Install packages'
    runCheck(msg, "yum install -y openstack-heat-api openstack-heat-api-cfn openstack-heat-engine python-heatclient")
    
    set_parameter(etc_heat_config_file, 'database', 'connection', 'mysql://heat:{}@controller/heat'.format(HEAT_DBPASS))

    set_parameter(etc_heat_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_heat_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_heat_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)


    set_parameter(etc_heat_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(etc_heat_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(etc_heat_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_heat_config_file, 'keystone_authtoken', 'admin_user', 'heat')   
    set_parameter(etc_heat_config_file, 'keystone_authtoken', 'admin_password', HEAT_PASS)   

    set_parameter(etc_heat_config_file, 'ec2authtoken', 'auth_uri', 'http://controller:5000/v2.0')   

    set_parameter(etc_heat_config_file, 'DEFAULT', 'heat_metadata_server_url', 'http://controller:8000')
    set_parameter(etc_heat_config_file, 'DEFAULT', 'heat_waitcondition_server_url', 'http://controller:8000/v1/waitcondition')
    set_parameter(etc_heat_config_file, 'DEFAULT', 'verbose', 'True')
    
def populate_database():
    msg = 'Populate database'
    runCheck(msg, "su -s /bin/sh -c 'heat-manage db_sync' heat")

def start_heat_services():
    msg = 'Enable heat services'
    runCheck(msg, "systemctl enable openstack-heat-api.service openstack-heat-api-cfn.service openstack-heat-engine.service")
    msg = 'Start heat services'
    runCheck(msg, "systemctl start openstack-heat-api.service openstack-heat-api-cfn.service openstack-heat-engine.service")
   
@roles('controller')
def setup_heat():

    setup_heat_database(passwd['HEAT_DBPASS'])
    setup_heat_keystone(passwd['HEAT_PASS'])

    setup_heat_config_files(passwd['HEAT_PASS'], passwd['HEAT_DBPASS'], passwd['RABBIT_PASS'])
    populate_database()
    start_heat_services()




################### Deployment ########################################

def deploy():
    execute(setup_heat)

######################################## TDD #########################################


@roles('controller')
def create_stack():
    """
    Create a stack on the demo-net (assuming it exists)
    """

    with prefix(env_config.demo_openrc):

        # Upload the test file to the host
        put(heat_test_file)

        msg = "Grab the net id for demo-net"
        netid = runCheck(msg, "nova net-list | awk '/ demo-net / { print $2 }'")

        # Create a test stack based on the test file
        msg = "Create a test stack"
        runCheck(msg, "heat stack-create -f test-stack.yml "
                '-P "ImageID=cirros-0.3.3-x86_64;NetID={}" testStack'.format(netid))
        output = run("heat stack-list")

    if "testStack" in output:
        print(green("Stack created succesfully"))
    else:
        print(red("Stack NOT created"))
        status = 'bad'
        
        
@roles('controller')
def tdd():

    # status is initialized as 'good'
    # if any of the tdd functions gets an error,
    # it changes the value to 'bad'
    status = 'good'

    with settings(warn_only=True):
        
        res = keystone_check('heat')
        if res != 'OK':
            status = 'bad'

        res = database_check('heat')
        if res != 'OK':
            status = 'bad'

        create_stack()

        # save config file
        saveConfigFile(etc_heat_config_file, status)

