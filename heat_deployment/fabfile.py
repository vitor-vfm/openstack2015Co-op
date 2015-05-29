from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import logging
import string

import sys
sys.path.append('../global_config_files')
import env_config


logging.basicConfig(filename='/tmp/juno2015.log',level=logging.DEBUG, format='%(asctime)s %(message)s')


############################ Config ########################################

env.roledefs = env_config.roledefs

admin_openrc = "../global_config_files/admin-openrc.sh"
demo_openrc = "../global_config_files/demo-openrc.sh"

etc_heat_config_file = "/etc/heat/heat.conf"
heat_test_file = "test_file/test-stack.yml"
def sudo_log(command):
    output = sudo(command)
    logging.info(output)
    return output

def run_log(command):
    output = run(command)
    logging.info(output)
    return output


################### General functions ########################################

def get_parameter(config_file, section, parameter):
    crudini_command = "crudini --get {} {} {}".format(config_file, section, parameter)
    return local(crudini_command, capture=True)
#    return sudo_log(crudini_command)

def set_parameter(config_file, section, parameter, value):
    crudini_command = "crudini --set {} {} {} {}".format(config_file, section, parameter, value)
    sudo_log(crudini_command)


def setup_heat_database(HEAT_DBPASS):
    print("HEAT_DBPASS is: {}".format(HEAT_DBPASS))
    mysql_commands = "CREATE DATABASE IF NOT EXISTS heat;"
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON heat.* TO 'heat'@'localhost' IDENTIFIED BY '{}';".format(HEAT_DBPASS)
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON heat.* TO 'heat'@'%' IDENTIFIED BY '{}';".format(HEAT_DBPASS)

    
    print("mysql commands are: " + mysql_commands)
    sudo_log('echo "{}" | mysql -u root'.format(mysql_commands))
    


def setup_heat_keystone(HEAT_PASS):
    source_command = "source admin-openrc.sh"
    with prefix(source_command):
        sudo_log("keystone user-create --name heat --pass {}".format(HEAT_PASS))
        sudo_log("keystone user-role-add --user heat --tenant service --role admin")
        sudo_log("keystone role-create --name heat_stack_owner")
        sudo_log("keystone user-role-add --user demo --tenant demo --role heat_stack_owner")
        sudo_log("keystone role-create --name heat_stack_user")
        sudo_log('keystone service-create --name heat --type orchestration --description "Orchestration"')
        sudo_log('keystone service-create --name heat-cfn --type cloudformation --description "Orchestration"')
        
        sudo_log("""keystone endpoint-create \
        --service-id $(keystone service-list | awk '/ orchestration / {print $2}') \
        --publicurl http://controller:8004/v1/%\(tenant_id\)s \
        --internalurl http://controller:8004/v1/%\(tenant_id\)s \
        --adminurl http://controller:8004/v1/%\(tenant_id\)s \
        --region regionOne""")

        sudo_log("""keystone endpoint-create \
        --service-id $(keystone service-list | awk '/ cloudformation / {print $2}') \
        --publicurl http://controller:8000/v1 \
        --internalurl http://controller:8000/v1 \
        --adminurl http://controller:8000/v1 \
        --region regionOne""")
        
def setup_heat_config_files(HEAT_PASS, HEAT_DBPASS, RABBIT_PASS):
    sudo_log("yum install -y openstack-heat-api openstack-heat-api-cfn openstack-heat-engine python-heatclient")
    
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


    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #




    set_parameter(etc_heat_config_file, 'DEFAULT', 'heat_metadata_server_url', 'http://controller:8000')
    set_parameter(etc_heat_config_file, 'DEFAULT', 'heat_waitcondition_server_url', 'http://controller:8000/v1/waitcondition')
    set_parameter(etc_heat_config_file, 'DEFAULT', 'verbose', 'True')
    



def populate_database():
    sudo_log("su -s /bin/sh -c 'heat-manage db_sync' heat")

def start_heat_services():
    sudo_log("systemctl enable openstack-heat-api.service openstack-heat-api-cfn.service openstack-heat-engine.service")
    sudo_log("systemctl start openstack-heat-api.service openstack-heat-api-cfn.service openstack-heat-engine.service")


def download_packages():
    # make sure we have crudini
    sudo_log('yum install -y crudini')
   
@roles('controller')
def setup_heat():

    # upload admin-openrc.sh to set variables in host machine
    put(admin_openrc)
    
    # variable setup
    HEAT_DBPASS = get_parameter(env_config.global_config_file, 'mysql', 'HEAT_DBPASS')
    HEAT_PASS = get_parameter(env_config.global_config_file, 'keystone', 'HEAT_PASS')    
    RABBIT_PASS = get_parameter(env_config.global_config_file, 'rabbitmq', 'RABBIT_PASS')

    print(HEAT_DBPASS)
    setup_heat_database(HEAT_DBPASS)
    setup_heat_keystone(HEAT_PASS)

    setup_heat_config_files(HEAT_PASS, HEAT_DBPASS, RABBIT_PASS)
    populate_database()
    start_heat_services()




################### Deployment ########################################

def deploy():
    execute(setup_heat)

######################################## TDD #########################################


@roles('controller')
def create_stack():
    # upload admin-openrc.sh to set variables in host machine
    put(admin_openrc)
    put(heat_test_file)
    source_command = "source admin-openrc.sh"
    with prefix(source_command):
        sudo("NET_ID=$(nova net-list | awk '/ demo-net / { print $2 }')")
        sudo("""heat stack-create -f test-stack.yml -P "ImageID=cirros-0.3.3-x86_64;NetID=$NET_ID" testStack""")
        output = sudo("heat stack-list")

    if "testStack" in output:
        print(green("Stack created succesfully"))
    else:
        print(green("Stack NOT created"))
        
        
def tdd():
    with settings(warn_only=True):
        execute(create_stack)
