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
#demo_openrc = "../global_config_files/demo-openrc.sh"

etc_config_file = "/etc/my.conf"
etc_sahara_config_file = "/etc/sahara/sahara.conf"
#sahara_test_file = "test_file/test-stack.yml"

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

def set_parameter(config_file, section, parameter, value):
    crudini_command = "crudini --set {} {} {} {}".format(config_file, section, parameter, value)
    sudo_log(crudini_command)


def setup_sahara_database(SAHARA_DBPASS):
    #print("SAHARA_DBPASS is: {}".format(SAHARA_DBPASS))
    #mysql_commands = "CREATE DATABASE IF NOT EXISTS sahara;"
    #mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON sahara.* TO 'sahara'@'localhost' IDENTIFIED BY '{}';".format(SAHARA_DBPASS)
    #mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON sahara.* TO 'sahara'@'%' IDENTIFIED BY '{}';".format(SAHARA_DBPASS)

    
    #print("mysql commands are: " + mysql_commands)
    #sudo_log('echo "{}" | mysql -u root'.format(mysql_commands))
    
    sudo_log("sahara-db-manage --config-file /etc/sahara/sahara.conf upgrade head")


def setup_sahara_keystone(SAHARA_PASS):
#    source_command = "source admin-openrc.sh"
#    with prefix(source_command):
        #sudo_log("keystone user-create --name sahara --pass {}".format(SAHARA_PASS))
        #sudo_log("keystone user-role-add --user sahara --tenant service --role admin")
        #sudo_log("keystone role-create --name sahara_stack_owner")
        #sudo_log("keystone user-role-add --user demo --tenant demo --role sahara_stack_owner")
        #sudo_log("keystone role-create --name sahara_stack_user")
    sudo_log('keystone service-create --name sahara --type data_processing --description "Data processing service"')
        #sudo_log('keystone service-create --name sahara-cfn --type cloudformation --description "Orchestration"')
        
    sudo_log("""keystone endpoint-create \
        --service-id $(keystone service-list | awk '/ sahara / {print $2}') \
        #--publicurl http://controller:8386/v1.1/%\(tenant_id\)s \
        #--internalurl http://controller:8386/v1.1/%\(tenant_id\)s \
        #--adminurl http://controller:8386/v1.1/%\(tenant_id\)s \
        #--region regionOne""")

        #sudo_log("""keystone endpoint-create \
        #--service-id $(keystone service-list | awk '/ cloudformation / {print $2}') \
        #--publicurl http://controller:8000/v1 \
        #--internalurl http://controller:8000/v1 \
        #--adminurl http://controller:8000/v1 \
        #--region regionOne""")
        
def setup_sahara_config_files(SAHARA_PASS, SAHARA_DBPASS, RABBIT_PASS):
    sudo_log("yum install -y openstack-sahara python-saharaclient")
    
    set_parameter(etc_sahara_config_file, 'database', 'connection', 'mysql://sahara:{}@controller/sahara'.format(SAHARA_DBPASS))

    #set_parameter(etc_sahara_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    #set_parameter(etc_sahara_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    #set_parameter(etc_sahara_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)
    
    set_parameter(etc_sahara_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(etc_sahara_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(etc_sahara_config_file, 'keystone_authtoken', 'admin_user', 'sahara')   
    set_parameter(etc_sahara_config_file, 'keystone_authtoken', 'admin_password', SAHARA_PASS)   
    set_parameter(etc_sahara_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service')
    
    #set_parameter(etc_sahara_config_file, 'ec2authtoken', 'auth_uri', 'http://controller:5000/v2.0')   


    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #




    #set_parameter(etc_sahara_config_file, 'DEFAULT', 'sahara_metadata_server_url', 'http://controller:8000')
    #set_parameter(etc_sahara_config_file, 'DEFAULT', 'sahara_waitcondition_server_url', 'http://controller:8000/v1/waitcondition')
    #set_parameter(etc_sahara_config_file, 'DEFAULT', 'verbose', 'True')
    
    set_parameter(etc_sahara_config_file, 'DEFAULT', 'use_neutron', 'true')

    # If the following is true, sahara will start to write logs of INFO level
    # and above
    #set_parameter(etc_sahara_config_file, 'DEFAULT', 'verbose', 'true')

    # If the following is true, sahara will write all the logs, including
    # the DEBUG ones
    #set_parameter(etc_sahara_config_file, 'DEFAULT', 'debug', 'true')

    set_parameter(etc_config_file, 'mysqld', 'max_allowed_packet', '256M')



#def populate_database():
#    sudo_log("su -s /bin/sh -c 'sahara-manage db_sync' sahara")

def start_sahara_services():
    sudo_log("systemctl restart mariadb.service")
    sudo_log("systemctl start openstack-sahara-all")
    sudo_log("systemctl enable openstack-sahara-all")
    

def download_packages():
    # make sure we have crudini
    sudo_log('yum install -y crudini')
   
@roles('controller')
def setup_sahara():

    # upload admin-openrc.sh to set variables in host machine
    put(admin_openrc)
    
    # variable setup
    SAHARA_DBPASS = get_parameter(env_config.global_config_file, 'mysql', 'SAHARA_DBPASS')
    SAHARA_PASS = get_parameter(env_config.global_config_file, 'keystone', 'SAHARA_PASS')    
    RABBIT_PASS = get_parameter(env_config.global_config_file, 'rabbitmq', 'RABBIT_PASS')

    #print(SAHARA_DBPASS)
    #setup_sahara_database(SAHARA_DBPASS)
    #setup_sahara_keystone(SAHARA_PASS)

    setup_sahara_config_files(SAHARA_PASS, SAHARA_DBPASS, RABBIT_PASS)
    #populate_database()
    start_sahara_services()

    setup_sahara_database(SAHARA_DBPASS)
    setup_sahara_keystone(SAHARA_PASS)



################### Deployment ########################################

def deploy():
    execute(setup_sahara)

######################################## TDD #########################################


@roles('controller')       
def tdd():
    with settings(warn_only=True):
        run_log("source demo-openrc.sh")
        run_log("sahara cluster-list")
