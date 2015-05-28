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

nova_config_file = 'nova_config'

admin_openrc = "../global_config_files/admin-openrc.sh"

demo_openrc = "../global_config_files/demo-openrc.sh"

controller_management_interface_file_location = '../network_deployment/config_files/controller_management_interface_config'
controller_management_interface_file_name = 'controller_management_interface_config'

compute_management_interface_file_location = '../network_deployment/config_files/compute_management_interface_config'
compute_management_interface_file_name = 'compute_management_interface_config'

global_config_file_location = '../global_config_files/global_config'
global_config_file_name = 'global_config'

etc_nova_config_file = "/etc/nova/nova.conf"
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
    return sudo_log(crudini_command)

def set_parameter(config_file, section, parameter, value):
    crudini_command = "crudini --set {} {} {} {}".format(config_file, section, parameter, value)
    sudo_log(crudini_command)


def setup_nova_database_on_controller(NOVA_DBPASS):
    print("NOVA_DBPASS is: {}".format(NOVA_DBPASS))
    mysql_commands = "CREATE DATABASE IF NOT EXISTS nova;"
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'localhost' IDENTIFIED BY '{}';".format(NOVA_DBPASS)
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'%' IDENTIFIED BY '{}';".format(NOVA_DBPASS)

    
    print("mysql commands are: " + mysql_commands)
    sudo_log('echo "{}" | mysql -u root'.format(mysql_commands))
    


def setup_nova_keystone_on_controller(NOVA_PASS):
    source_command = "source admin-openrc.sh"
    with prefix(source_command):
        sudo_log("keystone user-create --name nova --pass {}".format(NOVA_PASS))
        sudo_log("keystone user-role-add --user nova --tenant service --role admin")
        sudo_log("keystone service-create --name nova --type compute --description 'OpenStack Compute'")
        sudo_log("keystone endpoint-create --service-id $(keystone service-list | awk '/ compute / {print $2}') --publicurl http://controller:8774/v2/%\(tenant_id\)s  --internalurl http://controller:8774/v2/%\(tenant_id\)s --adminurl http://controller:8774/v2/%\(tenant_id\)s --region regionOne")
    
def setup_nova_config_files_on_controller(NOVA_PASS, NOVA_DBPASS, RABBIT_PASS, CONTROLLER_MANAGEMENT_IP):
    installation_command = "yum install -y openstack-nova-api openstack-nova-cert openstack-nova-conductor openstack-nova-console openstack-nova-novncproxy openstack-nova-scheduler python-novaclient"
    sudo_log(installation_command)
    
    set_parameter(etc_nova_config_file, 'database', 'connection', 'mysql://nova:{}@controller/nova'.format(NOVA_DBPASS))

    set_parameter(etc_nova_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)

    set_parameter(etc_nova_config_file, 'DEFAULT', 'auth_strategy', 'keystone')

    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_user', 'nova')   
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_password', NOVA_PASS)   

    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #

    set_parameter(etc_nova_config_file, 'DEFAULT', 'my_ip', CONTROLLER_MANAGEMENT_IP)
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_listen', CONTROLLER_MANAGEMENT_IP)
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_proxyclient_address', CONTROLLER_MANAGEMENT_IP)


    set_parameter(etc_nova_config_file, 'glance', 'host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'verbose', 'True')





def populate_database_on_controller():
    sudo_log("su -s /bin/sh -c 'nova-manage db sync' nova")

def start_nova_services_on_controller():
    enable_all = "systemctl enable openstack-nova-api.service openstack-nova-cert.service openstack-nova-consoleauth.service openstack-nova-scheduler.service openstack-nova-conductor.service openstack-nova-novncproxy.service"

    start_all = "systemctl start openstack-nova-api.service openstack-nova-cert.service openstack-nova-consoleauth.service openstack-nova-scheduler.service openstack-nova-conductor.service openstack-nova-novncproxy.service"
    
    sudo_log(enable_all)
    sudo_log(start_all)


def upload_files_on_controller():
    # upload config file for reading via crudini
    put(nova_config_file)

    # upload admin-openrc.sh to set variables in host machine
    put(admin_openrc)

    # for getting the management interface ip address of the controller
    put(controller_management_interface_file_location)

    # for getting rabbitmq credentials
    put(global_config_file_location)

def download_packages():
    # make sure we have crudini
    sudo_log('yum install -y crudini')



def setup_nova_config_files_on_compute(NOVA_PASS, NOVA_DBPASS, RABBIT_PASS, NETWORK_MANAGEMENT_IP):



    sudo_log('yum install -y openstack-nova-compute sysfsutils')
    
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)

    set_parameter(etc_nova_config_file, 'DEFAULT', 'auth_strategy', 'keystone')

    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_user', 'nova')   
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_password', NOVA_PASS)   

    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #

    set_parameter(etc_nova_config_file, 'DEFAULT', 'my_ip', NETWORK_MANAGEMENT_IP)

    set_parameter(etc_nova_config_file, 'DEFAULT', 'vnc_enabled', 'True')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_listen', '0.0.0.0')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_proxyclient_address', NETWORK_MANAGEMENT_IP)
    set_parameter(etc_nova_config_file, 'DEFAULT', 'novncproxy_base_url', 'http://controller:6080/vnc_auto.html')


    set_parameter(etc_nova_config_file, 'glance', 'host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'verbose', 'True')

    hardware_accel_check()

def hardware_accel_check():
    with settings(warn_only=True):
        output = sudo_log("egrep -c '(vmx|svm)' /proc/cpuinfo")    

    if int(output) < 1:
        # we need to do more configuration
        set_parameter(etc_nova_config_file, 'libvirt', 'virt_type', 'qemu')

def start_services_on_compute():
    sudo_log("systemctl enable libvirtd.service openstack-nova-compute.service")
    sudo_log("systemctl start libvirtd.service openstack-nova-compute.service")



def upload_files_on_compute():
    # upload config file for reading via crudini
    put(nova_config_file)

    # for getting the management interface ip address of the controller
    put(compute_management_interface_file_location)

    # for getting rabbitmq credentials
    put(global_config_file_location)
    

@roles('compute')
def setup_nova_on_compute():
    download_packages()


    upload_files_on_compute()
    
    # variable setup
    NOVA_DBPASS = get_parameter(nova_config_file, 'mysql', 'NOVA_DBPASS')
    NOVA_PASS = get_parameter(nova_config_file, 'keystone', 'NOVA_PASS')    
    RABBIT_PASS = get_parameter(global_config_file_name, 'rabbitmq', 'RABBIT_PASS')
    NETWORK_MANAGEMENT_IP = get_parameter(compute_management_interface_file_name, "''", 'IPADDR')

    setup_nova_config_files_on_compute(NOVA_PASS, NOVA_DBPASS, RABBIT_PASS, NETWORK_MANAGEMENT_IP)        
    start_services_on_compute()
    

@roles('controller')   
def setup_nova_on_controller():
    
    host_command = 'sudo_log -- sh -c "{}"'.format("echo '{}' >> /etc/hosts".format("{}        controller".format(env.host))) 
    #    sudo_log(host_command)
    
    
    # fixing bind-address on /etc/my.cnf
    
    # bindCommand = "sed -i.bak 's/^\(bind-address=\).*/\1 {} /' /etc/my.cnf".format(env.host)
    bindCommand = "sed -i '/bind-address/s/=.*/={}/' /etc/my.cnf".format(env.host)
    #    sudo_log(bindCommand)
    
    #    sudo_log("systemctl restart mariadb")
    
    download_packages()

    upload_files_on_controller()
    
    # variable setup
    NOVA_DBPASS = get_parameter(nova_config_file, 'mysql', 'NOVA_DBPASS')
    NOVA_PASS = get_parameter(nova_config_file, 'keystone', 'NOVA_PASS')    
    RABBIT_PASS = get_parameter(global_config_file_name, 'rabbitmq', 'RABBIT_PASS')
    CONTROLLER_MANAGEMENT_IP = get_parameter(controller_management_interface_file_name, "''", 'IPADDR')

    # setup nova database
    setup_nova_database_on_controller(NOVA_DBPASS)
    setup_nova_keystone_on_controller(NOVA_PASS)

    setup_nova_config_files_on_controller(NOVA_PASS, NOVA_DBPASS, RABBIT_PASS, CONTROLLER_MANAGEMENT_IP)
    populate_database_on_controller()
    start_nova_services_on_controller()
        

################### Deployment ########################################

def deploy():
    execute(setup_nova_on_controller)
    execute(setup_nova_on_compute)

######################################## TDD #########################################



@roles('controller')
def verify():
    source_command = "source admin-openrc.sh"
    with prefix(source_command):
        sudo_log("nova service-list")
        sudo_log("nova image-list")


def tdd():
    with settings(warn_only=True):
        # to be done on the controller node
        execute(verify)


