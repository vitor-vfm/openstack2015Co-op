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
from myLib import runCheck, set_parameter, createDatabaseScript, printMessage



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

@roles('controller')
def setup_cinder_database_on_controller():

    CINDER_DBPASS = passwd['CINDER_DBPASS']

    mysql_commands = createDatabaseScript("cinder",CINDER_DBPASS)    
    msg = 'Create the database'
    runCheck(msg, 'echo "{}" | mysql -u root -p{}'.format(mysql_commands, env_config.passwd['ROOT_SECRET']))
    

@roles('controller')
def setup_cinder_keystone_on_controller():

    CINDER_PASS = passwd['CINDER_PASS']

    with prefix(admin_openrc):

        if 'cinder' not in run("keystone user-list"):
            runCheck('Create a cinder user',
                    "keystone user-create --name cinder --pass {}".format(CINDER_PASS))
            runCheck('Add the admin role to the cinder user',
                    "keystone user-role-add "
                    "--user cinder --tenant service --role admin")
        else:
            print blue('User cinder already created')

        if 'cinder' not in run("keystone service-list"):
            runCheck('Create the cinder service entities', 
                    "keystone service-create "
                    "--name cinder "
                    "--type volume "
                    "--description 'OpenStack Block Storage'")
        else:
            print blue('Service cinder already created')


        if 'cinderv2' not in run("keystone service-list"):
            runCheck('Create the cinder service entities', 
                    "keystone service-create "
                    "--name cinderv2 "
                    "--type volumev2 "
                    "--description 'OpenStack Block Storage'")
        else:
            print blue('Service cinderv2 already created')

        if '8776' not in run("keystone endpoint-list"):
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
        else:
            print blue('Endpoints for port 8776 already created')

@roles('controller')
def setup_cinder_config_files_on_controller():

    CINDER_DBPASS = passwd['CINDER_DBPASS']
    CINDER_PASS = passwd['CINDER_PASS']
    RABBIT_PASS = passwd['RABBIT_PASS']
    CONTROLLER_MANAGEMENT_IP = env_config.controllerManagement['IPADDR']

    installation_command = "yum install -y openstack-cinder python-cinderclient python-oslo-db"

    runCheck('Install the packages', installation_command)
    
    set_parameter(etc_cinder_config_file, 'database', 'connection', 
            'mysql://cinder:{}@controller/cinder'.format(CINDER_DBPASS))

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'auth_strategy', 'keystone')

    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'auth_uri', 
            'http://controller:5000/v2.0')
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'identity_uri', 
            'http://controller:35357') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_user', 'cinder')   
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_password', CINDER_PASS)   

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'my_ip', CONTROLLER_MANAGEMENT_IP)

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'verbose', 'True')


@roles('controller')
def populate_database_on_controller():
    msg = 'Populate the Block Storage database'
    runCheck(msg, "su -s /bin/sh -c 'cinder-manage db sync' cinder")

@roles('controller')
def start_cinder_services_on_controller():

    enable_all = "systemctl enable openstack-cinder-api.service openstack-cinder-scheduler.service"

    start_all = "systemctl start openstack-cinder-api.service openstack-cinder-scheduler.service"
    
    runCheck('Enable Block Storage services to start when system boots', enable_all)
    runCheck('Start the Block Storage services', start_all)


@roles('controller')   
def setup_cinder_on_controller():
    
    # setup cinder database
    execute(setup_cinder_database_on_controller)

    execute(setup_cinder_keystone_on_controller)

    execute(setup_cinder_config_files_on_controller)

    execute(populate_database_on_controller)

    execute(start_cinder_services_on_controller)


@roles('storage')
def setup_cinder_config_files_on_storage():
    
    CINDER_DBPASS = passwd['CINDER_DBPASS']
    CINDER_PASS = passwd['CINDER_PASS']
    RABBIT_PASS = passwd['RABBIT_PASS']
    STORAGE_MANAGEMENT_IP = env_config.storageManagement['IPADDR']

    install_command = "yum install -y openstack-cinder targetcli python-oslo-db MySQL-python"
    runCheck('Install packages on storage node', install_command)

    set_parameter(etc_cinder_config_file, 'database', 'connection', 
            'mysql://cinder:{}@controller/cinder'.format(CINDER_DBPASS))    

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'auth_strategy', 'keystone')

    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'auth_uri', 
            'http://controller:5000/v2.0')
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'identity_uri',
            'http://controller:35357') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_user', 'cinder')   
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_password', CINDER_PASS)   

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'my_ip', STORAGE_MANAGEMENT_IP)
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'iscsi_helper', 'lioadm')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'glance_host', 'controller')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'verbose', 'True')


@roles('storage')
def start_services_on_storage():
    enable_services = "systemctl enable openstack-cinder-volume.service target.service"
    start_services = "systemctl start openstack-cinder-volume.service target.service"
    restart_services = "systemctl restart openstack-cinder-volume.service target.service"
    runCheck('Enable services on storage', enable_services)
    runCheck('Start services on storage', start_services)
    runCheck('Restart services on storage', restart_services)

@roles('storage')
def setup_volume_using_cinder(partition_name):
    if partition_name in run("ls /dev/"):
        sudo("pvcreate /dev/" + partition_name)
        sudo("vgcreate cinder-volumes /dev/" + partition_name)
        
@roles('storage')
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

@roles('storage')
def install_and_start_lvm():
    # install package and start
    runCheck('Install lvm2', "yum install -y lvm2")
    runCheck('Enable lvm2', "systemctl enable lvm2-lvmetad.service")
    runCheck('Start lvm2', "systemctl start lvm2-lvmetad.service")


@roles('storage')
def setup_cinder_on_storage():

    cinder_device_name = ""
    cinder_partition_name = "/dev/centos/strBlk"

    #execute(install_and_start_lvm)

    #execute(setup_volume_using_cinder,cinder_partition_name)

    #execute(setup_lvm_config_file,cinder_device_name)

    execute(setup_cinder_config_files_on_storage)     

    execute(start_services_on_storage)
    


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
        run('cinder list')
        status = run("cinder list | awk '/demo-volume1/ {print $4}'",quiet=True)
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


