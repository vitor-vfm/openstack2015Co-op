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


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

admin_openrc = "../global_config_files/admin-openrc.sh"
demo_openrc = "../global_config_files/demo-openrc.sh"


glance_api_config_file = "/etc/glance/glance-api.conf"

glance_registry_config_file = "/etc/glance/glance-registry.conf"


def sudo_log(command):
    output = sudo(command)
    if output.return_code != 0:
        logging.error("Problem on command '{}'".format(command),extra=log_dict)
    else:
        for line in output.splitlines():
            # don't log lines that have passwords
            if 'pass' not in line.lower():
                # skip empty lines
                if line != '' or line !='\n':
                    logging.debug(line,extra=log_dict)
    return output

def run_log(command):
    output = run(command)
    if output.return_code != 0:
        logging.error("Problem on command '{}'".format(command),extra=log_dict)
    else:
        for line in output.splitlines():
            # don't log lines that have passwords
            if 'pass' not in line.lower():
                # skip empty lines
                if line != '' or line !='\n':
                    logging.debug(line,extra=log_dict)
    return output

# logging setup

log_file = 'glance_deployment.log'
env_config.setupLoggingInFabfile(log_file)

################### General functions ########################################

def get_parameter(config_file, section, parameter):
    crudini_command = "crudini --get {} {} {}".format(config_file, section, parameter)
    return local(crudini_command, capture=True)
#    return sudo_log(crudini_command)

def set_parameter(config_file, section, parameter, value):
    crudini_command = "crudini --set {} {} {} {}".format(config_file, section, parameter, value)
    sudo_log(crudini_command)


def setup_glance_database(GLANCE_DBPASS):
    mysql_commands = "CREATE DATABASE IF NOT EXISTS glance;"
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'localhost' IDENTIFIED BY '{}';".format(GLANCE_DBPASS)
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'%' IDENTIFIED BY '{}';".format(GLANCE_DBPASS)

    
    print("mysql commands are: " + mysql_commands)
    sudo_log('echo "{}" | mysql -u root'.format(mysql_commands))
    


def setup_glance_keystone(GLANCE_PASS):
    source_command = "source admin-openrc.sh"
    with prefix(source_command):
        if 'glance' not in sudo("keystone user-list"):
            sudo_log("keystone user-create --name glance --pass {}".format(GLANCE_PASS))
            sudo_log("keystone user-role-add --user glance --tenant service --role admin")
        else:
            logging.debug('User glance already in user list',extra=log_dict)

        if 'glance' not in sudo("keystone service-list"):
            sudo_log("keystone service-create --name glance --type image --description 'OpenStack Image Service'")
        else:
            logging.debug('Service glance already in service list',extra=log_dict)

        if '9292' not in sudo("keystone endpoint-list"):
            sudo_log("keystone endpoint-create --service-id $(keystone service-list | awk '/ image / {print $2}') --publicurl http://controller:9292 --internalurl http://controller:9292  --adminurl http://controller:9292 --region regionOne")
        else:
            logging.debug('Endpoint 9292 already in endpoint list',extra=log_dict)
    
def setup_glance_config_files(GLANCE_PASS, GLANCE_DBPASS):
    sudo_log("yum install -y openstack-glance python-glanceclient")
    
    set_parameter(glance_api_config_file, 'database', 'connection', 'mysql://glance:{}@controller/glance'.format(GLANCE_DBPASS))
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_user', 'glance')   
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_password', GLANCE_PASS)   
    set_parameter(glance_api_config_file, 'paste_deploy', 'flavor', 'keystone')

    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #

    set_parameter(glance_api_config_file, 'glance_store', 'default_store', 'file')
    set_parameter(glance_api_config_file, 'glance_store', 'filesystem_store_datadir', '/var/lib/glance/images/')
    set_parameter(glance_api_config_file, 'DEFAULT', 'notification_driver', 'noop')
    set_parameter(glance_api_config_file, 'DEFAULT', 'verbose', 'True')



    set_parameter(glance_registry_config_file, 'database', 'connection', 'mysql://glance:{}@controller/glance'.format(GLANCE_DBPASS))


    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'admin_user', 'glance')   
    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'admin_password', GLANCE_PASS)   
    set_parameter(glance_registry_config_file, 'paste_deploy', 'flavor', 'keystone')

    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #

    set_parameter(glance_registry_config_file, 'DEFAULT', 'notification_driver', 'noop')
    set_parameter(glance_registry_config_file, 'DEFAULT', 'verbose', 'True')
    



def populate_database():
    sudo_log("su -s /bin/sh -c 'glance-manage db_sync' glance")

def start_glance_services():
    sudo_log("systemctl enable openstack-glance-api.service openstack-glance-registry.service")
    sudo_log("systemctl start openstack-glance-api.service openstack-glance-registry.service")

def download_packages():
    # make sure we have crudini
    sudo_log('yum install -y crudini')
   
@roles('controller')
def setup_glance():

    # info for logging
    global log_dict
    log_dict = {'host_string':env.host_string, 'role':'controller'}

    download_packages()
    
    # upload admin-openrc.sh to set variables in host machine
    put(admin_openrc)
    
    # variable setup
    # GLANCE_DBPASS = get_parameter(env_config.global_config_file, 'mysql', 'GLANCE_DBPASS')
    # GLANCE_PASS = get_parameter(env_config.global_config_file, 'keystone', 'GLANCE_PASS')    

    # setup glance database
    setup_glance_database(passwd['GLANCE_DBPASS'])
    setup_glance_keystone(passwd['GLANCE_PASS'])

    setup_glance_config_files(passwd['GLANCE_PASS'], passwd['GLANCE_DBPASS'])
    populate_database()
    start_glance_services()
        
################### Deployment ########################################

def deploy():
    execute(setup_glance)

######################################## TDD #########################################



@roles('controller')
def get_image_tdd():

    # dictionary for logging format
    global log_dict
    log_dict = {'host_string':env.host_string, 'role':'controller'}


    sudo_log("mkdir /tmp/images")
    url = "http://download.cirros-cloud.net/0.3.3/cirros-0.3.3-x86_64-disk.img"
#    sudo_log("wget -P /tmp/images http://cdn.download.cirros-cloud.net/0.3.3/cirros-0.3.3-x86_64-disk.img")
    sudo_log("wget -P /tmp/images " + url)
    source_command = "source admin-openrc.sh"
    with prefix(source_command):
        sudo_log("glance image-create --name 'cirros-0.3.3-x86_64' --file /tmp/images/cirros-0.3.3-x86_64-disk.img --disk-format qcow2 --container-format bare --is-public True --progress")
        output = sudo_log("glance image-list")

    if 'cirros-0.3.3-x86_64' in output:
        print(green("Successfully installed cirros image"))
    else:
        print(red("Couldn't install cirros image"))
        
    sudo_log("rm -r /tmp/images")



def tdd():
    with settings(warn_only=True):
        execute(get_image_tdd)
