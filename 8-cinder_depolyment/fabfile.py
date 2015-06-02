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

controller_management_interface_file_location = '../1-network_deployment/config_files/controller_management_interface_config'
controller_management_interface_file_name = 'controller_management_interface_config'

compute_management_interface_file_location = '../1-network_deployment/config_files/compute_management_interface_config'
compute_management_interface_file_name = 'compute_management_interface_config'

etc_cinder_config_file = "/etc/cinder/cinder.conf"

passwd = env_config.passwd

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


def setup_cinder_database_on_controller(CINDER_DBPASS):
    mysql_commands = "CREATE DATABASE IF NOT EXISTS cinder;"
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'localhost' IDENTIFIED BY '{}';".format(CINDER_DBPASS)
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'%' IDENTIFIED BY '{}';".format(CINDER_DBPASS)

    
    print("mysql commands are: " + mysql_commands)
    sudo_log('echo "{}" | mysql -u root'.format(mysql_commands))
    


def setup_cinder_keystone_on_controller(CINDER_PASS):
    source_command = "source admin-openrc.sh"
    with prefix(source_command):
        sudo_log("keystone user-create --name cinder --pass {}".format(CINDER_PASS))
        sudo_log("keystone user-role-add --user cinder --tenant service --role admin")
        sudo_log("keystone service-create --name cinder --type volume --description 'OpenStack Block Storage'")
        sudo_log("keystone service-create --name cinderv2 --type volumev2 --description 'OpenStack Block Storage'")
        sudo_log("keystone endpoint-create \
        --service-id $(keystone service-list | awk '/ volume / {print $2}') \
        --publicurl http://controller:8776/v1/%\(tenant_id\)s \
        --internalurl http://controller:8776/v1/%\(tenant_id\)s \
        --adminurl http://controller:8776/v1/%\(tenant_id\)s \
        --region regionOne")
        sudo_log("keystone endpoint-create \
        --service-id $(keystone service-list | awk '/ volumev2 / {print $2}') \
        --publicurl http://controller:8776/v2/%\(tenant_id\)s \
        --internalurl http://controller:8776/v2/%\(tenant_id\)s \
        --adminurl http://controller:8776/v2/%\(tenant_id\)s \
        --region regionOne")

def setup_cinder_config_files_on_controller(CINDER_PASS, CINDER_DBPASS, RABBIT_PASS, CONTROLLER_MANAGEMENT_IP):
    installation_command = "yum install -y openstack-cinder python-cinderclient python-oslo-db"

    sudo_log(installation_command)
    
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
    sudo_log("su -s /bin/sh -c 'cinder-manage db sync' cinder")

def start_cinder_services_on_controller():
    enable_all = "systemctl enable openstack-cinder-api.service openstack-cinder-scheduler.service"


    start_all = "systemctl start openstack-cinder-api.service openstack-cinder-scheduler.service"

    
    sudo_log(enable_all)
    sudo_log(start_all)


@roles('controller')   
def setup_cinder_on_controller():
    
    put(admin_openrc)
    
    # setup cinder database
    setup_cinder_database_on_controller(passwd['CINDER_DBPASS'])
    #setup_cinder_keystone_on_controller(passwd['CINDER_PASS'])


    CONTROLLER_MANAGEMENT_IP = get_parameter(controller_management_interface_file_location, "''", 'IPADDR')

    setup_cinder_config_files_on_controller(passwd['CINDER_PASS'], passwd['CINDER_DBPASS'], passwd['RABBIT_PASS'], CONTROLLER_MANAGEMENT_IP)
    populate_database_on_controller()
    start_cinder_services_on_controller()




def setup_cinder_config_files_on_storage(CINDER_PASS, CINDER_DBPASS, RABBIT_PASS, NETWORK_MANAGEMENT_IP):
    
    install_command = "yum install -y openstack-cinder targetcli python-oslo-db MySQL-python"

    sudo_log(install_command)

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
    sudo_log(enable_services)
    sudo_log(start_services)
    sudo_log(restart_services)

#@roles('storage')
def setup_cinder_on_storage():
    put(admin_openrc)


    # create management interface
    DEVICE = "eth0:0"
    NETMASK = "255.255.255.0"
    IPADDR = "192.168.0.41"
    file_content = "DEVICE={} \n NETMASK={} \n IPADDR={} \n".format(DEVICE, NETMASK, IPADDR)
    with cd('/etc/sysconfig/network-scripts'):
        # create ifcfg file in the directory
        sudo('echo -e "{}" >ifcfg-{}'.format(file_content, DEVICE))

    sudo("ifdown {}; ifup {}".format(DEVICE,DEVICE))

    # set hostname
    sudo("hostnamectl set-hostname block1")


    # install package and start
    sudo("yum install -y lvm2")
    sudo("systemctl enable lvm2-lvmetad.service")
    sudo("systemctl start lvm2-lvmetad.service")

    # creat volume
    
#    device_name = "vdb"

#    sudo("pvcreate /dev/"+device_name)

#    sudo("vgcreate cinder-volumes /dev/"+device_name)


    config_file = "/etc/lvm/lvm.conf"
    


    # variable setup

    CINDER_DBPASS = get_parameter(env_config.global_config_file,'mysql','CINDER_DBPASS')
    CINDER_PASS = get_parameter(env_config.global_config_file,'keystone','CINDER_PASS')
    RABBIT_PASS = get_parameter(env_config.global_config_file,'rabbitmq', 'RABBIT_PASS')
    NETWORK_MANAGEMENT_IP = get_parameter(compute_management_interface_file_location, "''", 'IPADDR')

    setup_cinder_config_files_on_storage(CINDER_PASS, CINDER_DBPASS, RABBIT_PASS, NETWORK_MANAGEMENT_IP)        
    start_services_on_storage()
    


################### Deployment ########################################

def deploy():
    execute(setup_cinder_on_controller)
    execute(setup_cinder_on_storage)

######################################## TDD #########################################


def tdd():
    with settings(warn_only=True):
        # to be done on the controller node
        execute(verify)


