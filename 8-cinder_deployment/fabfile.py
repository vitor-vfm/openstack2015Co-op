from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.contrib.files import append
import logging
import string

import sys
sys.path.append('../')
import env_config
from myLib import runCheck, set_parameter, createDatabaseScript



"""
To use for other cases:

- make sure node has management ip/nic setup according to env_config

- change device_name to the device name that cinder is using to hold stuff

- change partition_name to the partition that has been formatted and 
is designated to be used for cinder volumes.


- make sure time difference between node hosting cinder and controller
node is less than 60 seconds

- when creating a volume, make sure you have enough space in partition


"""


############################ Config ########################################

env.roledefs = env_config.roledefs

#admin_openrc = "../global_config_files/admin-openrc.sh"
admin_openrc = env_config.admin_openrc

demo_openrc = env_config.demo_openrc

etc_cinder_config_file = "/etc/cinder/cinder.conf"

passwd = env_config.passwd


################### General functions ######################################

def setup_cinder_database_on_controller(CINDER_DBPASS):
    mysql_commands = "CREATE DATABASE IF NOT EXISTS cinder;"
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'localhost' IDENTIFIED BY '{}';".format(CINDER_DBPASS)
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'%' IDENTIFIED BY '{}';".format(CINDER_DBPASS)

    mysql_commands = createDatabaseScript("cinder",CINDER_DBPASS)    
    print("mysql commands are: " + mysql_commands)
    runCheck('Create the database', 'echo "{}" | mysql -u root'.format(mysql_commands))
    


def setup_cinder_keystone_on_controller(CINDER_PASS):
    #source_command = "source admin-openrc.sh"
    with prefix(admin_openrc):
        runCheck('Create a cinder user', "keystone user-create --name cinder --pass {}".format(CINDER_PASS))
        runCheck('Add the admin role to the cinder user', "keystone user-role-add --user cinder --tenant service --role admin")
        runCheck('Create the cinder service entities', "keystone service-create --name cinder --type volume --description 'OpenStack Block Storage'")
        runCheck('Create the cinder service entities', "keystone service-create --name cinderv2 --type volumev2 --description 'OpenStack Block Storage'")
        runCheck('Create the Block Storage service API endpoints',
        "keystone endpoint-create \
        --service-id $(keystone service-list | awk '/ volume / {print $2}') \
        --publicurl http://controller:8776/v1/%\(tenant_id\)s \
        --internalurl http://controller:8776/v1/%\(tenant_id\)s \
        --adminurl http://controller:8776/v1/%\(tenant_id\)s \
        --region regionOne")
        runCheck('Create the Block Storage service API endpoints',
        "keystone endpoint-create \
        --service-id $(keystone service-list | awk '/ volumev2 / {print $2}') \
        --publicurl http://controller:8776/v2/%\(tenant_id\)s \
        --internalurl http://controller:8776/v2/%\(tenant_id\)s \
        --adminurl http://controller:8776/v2/%\(tenant_id\)s \
        --region regionOne")

def setup_cinder_config_files_on_controller(CINDER_PASS, CINDER_DBPASS, RABBIT_PASS, CONTROLLER_MANAGEMENT_IP):
    installation_command = "yum install -y openstack-cinder python-cinderclient python-oslo-db"

    runCheck('Install the packages', installation_command)
    
    set_parameter(etc_cinder_config_file, 'database', 'connection', 'mysql://cinder:{}@controller/cinder'.format(CINDER_DBPASS))

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'auth_strategy', 'keystone')

    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_user', 'cinder')   
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_password', CINDER_PASS)   

    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'my_ip', CONTROLLER_MANAGEMENT_IP)

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'verbose', 'True')


def populate_database_on_controller():
    runCheck('Populate the Block Storage database', "su -s /bin/sh -c 'cinder-manage db sync' cinder")

def start_cinder_services_on_controller():
    enable_all = "systemctl enable openstack-cinder-api.service openstack-cinder-scheduler.service"

    start_all = "systemctl start openstack-cinder-api.service openstack-cinder-scheduler.service"
    
    runCheck('Enable Block Storage services to start when system boots', enable_all)
    runCheck('Start the Block Storage services', start_all)


@roles('controller')   
def setup_cinder_on_controller():
    CONTROLLER_MANAGEMENT_IP =  env_config.controllerManagement['IPADDR']
    
    # setup cinder database
    setup_cinder_database_on_controller(passwd['CINDER_DBPASS'])

    #setup_cinder_keystone_on_controller(passwd['CINDER_PASS'])

    setup_cinder_config_files_on_controller(passwd['CINDER_PASS'], passwd['CINDER_DBPASS'], passwd['RABBIT_PASS'], CONTROLLER_MANAGEMENT_IP)

    populate_database_on_controller()

    start_cinder_services_on_controller()


def setup_cinder_config_files_on_storage(CINDER_PASS, CINDER_DBPASS, RABBIT_PASS, NETWORK_MANAGEMENT_IP):
    
    install_command = "yum install -y openstack-cinder targetcli python-oslo-db MySQL-python"

    runCheck('Install packages on storage node', install_command)

    set_parameter(etc_cinder_config_file, 'database', 'connection', 'mysql://cinder:{}@controller/cinder'.format(CINDER_DBPASS))    

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'auth_strategy', 'keystone')

    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_user', 'cinder')   
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_password', CINDER_PASS)   

    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'my_ip', "192.168.0.41")
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'iscsi_helper', 'lioadm')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'glance_host', 'controller')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'verbose', 'True')


def start_services_on_storage():
    enable_services = "systemctl enable openstack-cinder-volume.service target.service"
    start_services = "systemctl start openstack-cinder-volume.service target.service"
    restart_services = "systemctl restart openstack-cinder-volume.service target.service"
    runCheck('Enable services on storage', enable_services)
    runCheck('Start services on storage', start_services)
    runCheck('Restart services on storage', restart_services)

def setup_volume_using_cinder(partition_name):
    if partition_name in run("ls /dev/"):
        sudo("pvcreate /dev/" + partition_name)
        sudo("vgcreate cinder-volumes /dev/" + partition_name)
        
def setup_lvm_config_file(device_name):
    config_file = "/etc/lvm/lvm.conf"
    # replace line 107 with the filter line
    filter_command = '\ \ \ \ filter = [ "a/'+device_name+'/","r/.*/" ]'
    filter_line = 'filter = [ "a/'+device_name+'/","r/.*/" ]'
    if filter_line not in run("cat " + config_file, quiet=True):
        runCheck('Append filter command to lvm.conf',"""sed -i '107i""" + filter_command +  """' """ + config_file)
    else:
        print(blue("lvm.conf already configured, i.e"))
        print(blue(filter_line + " already present in lvm.conf file"))

def install_and_start_lvm():
    # install package and start
    runCheck('Install lvm2', "yum install -y lvm2")
    runCheck('Enable lvm2', "systemctl enable lvm2-lvmetad.service")
    runCheck('Start lvm2', "systemctl start lvm2-lvmetad.service")


@roles('storage')
def setup_cinder_on_storage():

    CINDER_DBPASS = passwd['CINDER_DBPASS']
    CINDER_PASS = passwd['CINDER_PASS']
    RABBIT_PASS = passwd['RABBIT_PASS']
    NETWORK_MANAGEMENT_IP = env_config.storageManagement['IPADDR']
    cinder_device_name = ""
    cinder_partition_name = "/dev/centos/strBlk"

    #install_and_start_lvm()

    #setup_volume_using_cinder(cinder_partition_name)

    #setup_lvm_config_file(cinder_device_name)

    setup_cinder_config_files_on_storage(CINDER_PASS, CINDER_DBPASS, RABBIT_PASS, NETWORK_MANAGEMENT_IP)     

    start_services_on_storage()
    


########################### Deployment ########################################

def deploy():
    execute(setup_cinder_on_controller)
    execute(setup_cinder_on_storage)

################################# TDD #########################################

@roles('controller')
def verify():
    with prefix(admin_openrc):
        runCheck('List service components', 'cinder service-list')
    #runCheck('Restarting cinder', 'systemctl status openstack-cinder-volume.service')
    with prefix(demo_openrc):    
        runCheck('Create a 1 GB volume', 
                'cinder create --display-name demo-volume1 1')

        msg = 'Verify creation and availability of volume'
        status = run("cinder list | awk '/demo-volume1/ {print $4}'")
        if (status != '') and (status != 'error'):
            printMessage('good', msg)
        else:
            printMessage('oops', msg)

        runCheck('Delete test volume', 'cinder delete demo-volume1')
        #runCheck('Check if cinder is running', 'cinder service-list')

def tdd():
    with settings(warn_only=True):
        # to be done on the controller node
        execute(verify)


