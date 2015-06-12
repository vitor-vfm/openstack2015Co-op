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
from myLib import align_n, align_y, database_check, keystone_check, run_v


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

etc_nova_config_file = "/etc/nova/nova.conf"
    
################### General functions ########################################

def set_parameter(config_file, section, parameter, value):
    crudini_command = "crudini --set {} {} {} {}".format(config_file, section, parameter, value)
    run(crudini_command)


def setup_nova_database_on_controller(NOVA_DBPASS):
    mysql_commands = "CREATE DATABASE IF NOT EXISTS nova;"
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'controller' IDENTIFIED BY '{}';".format(NOVA_DBPASS)
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'%' IDENTIFIED BY '{}';".format(NOVA_DBPASS)

    
    print("mysql commands are: " + mysql_commands)
    run('echo "{}" | mysql -u root'.format(mysql_commands))
    


def setup_nova_keystone_on_controller(NOVA_PASS):
    source_command = "source admin-openrc.sh"
    with prefix(source_command):

        if 'nova' not in sudo("keystone user-list"):
            run("keystone user-create --name nova --pass {}".format(NOVA_PASS))
            run("keystone user-role-add --user nova --tenant service --role admin")
        else:
            log_debug('User nova already in user list')

        if 'nova' not in sudo("keystone service-list"):
            run("keystone service-create --name nova --type compute --description 'OpenStack Compute'")
        else:
            log_debug('Service nova already in service list')

        if '8774' not in sudo("keystone endpoint-list"):
            run("keystone endpoint-create --service-id $(keystone service-list | awk '/ compute / {print $2}') --publicurl http://controller:8774/v2/%\(tenant_id\)s  --internalurl http://controller:8774/v2/%\(tenant_id\)s --adminurl http://controller:8774/v2/%\(tenant_id\)s --region regionOne")
        else:
            log_debug('Endpoint 8774 already in endpoint list')
    
def setup_nova_config_files_on_controller(NOVA_PASS, NOVA_DBPASS, RABBIT_PASS, CONTROLLER_MANAGEMENT_IP):
    installation_command = "yum install -y openstack-nova-api openstack-nova-cert openstack-nova-conductor openstack-nova-console openstack-nova-novncproxy openstack-nova-scheduler python-novaclient"
    run(installation_command)
    
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
    run("su -s /bin/sh -c 'nova-manage db sync' nova")

def start_nova_services_on_controller():
    enable_all = "systemctl enable openstack-nova-api.service openstack-nova-cert.service openstack-nova-consoleauth.service openstack-nova-scheduler.service openstack-nova-conductor.service openstack-nova-novncproxy.service"

    start_all = "systemctl start openstack-nova-api.service openstack-nova-cert.service openstack-nova-consoleauth.service openstack-nova-scheduler.service openstack-nova-conductor.service openstack-nova-novncproxy.service"
    
    run(enable_all)
    run(start_all)



def setup_nova_config_files_on_compute(NOVA_PASS, NOVA_DBPASS, RABBIT_PASS, NETWORK_MANAGEMENT_IP):



    run('yum install -y openstack-nova-compute sysfsutils')
    
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
        output = run("egrep -c '(vmx|svm)' /proc/cpuinfo")    

    if int(output) < 1:
        # we need to do more configuration
        set_parameter(etc_nova_config_file, 'libvirt', 'virt_type', 'qemu')

def start_services_on_compute():
    run("systemctl enable libvirtd.service openstack-nova-compute.service")
    run("systemctl start libvirtd.service openstack-nova-compute.service")


@roles('compute')
def setup_nova_on_compute():

    NETWORK_MANAGEMENT_IP = env_config.networkManagement['IPADDR']

    setup_nova_config_files_on_compute(passwd['NOVA_PASS'], passwd['NOVA_DBPASS'], passwd['RABBIT_PASS'], NETWORK_MANAGEMENT_IP)        
    start_services_on_compute()
    

@roles('controller')   
def setup_nova_on_controller():

    CONTROLLER_MANAGEMENT_IP = env_config.controllerManagement['IPADDR']

    # setup nova database
    setup_nova_database_on_controller(passwd['NOVA_DBPASS'])
    setup_nova_keystone_on_controller(passwd['NOVA_PASS'])

    setup_nova_config_files_on_controller(passwd['NOVA_PASS'], passwd['NOVA_DBPASS'], passwd['RABBIT_PASS'], CONTROLLER_MANAGEMENT_IP)
    populate_database_on_controller()
    start_nova_services_on_controller()

################### Deployment ########################################

def deploy():
    execute(setup_nova_on_controller)
    execute(setup_nova_on_compute)

######################################## TDD #########################################



@roles('controller')
def verify():

    database_check('nova')
    keystone_check('nova')
    
    nova_services = ['nova-conductor','nova-consoleauth','nova-scheduler', 'nova-cert']
    
    with prefix(env_config.admin_openrc):
        for service in nova_services:
            if service in run("nova service-list"):
                print align_y("{} exists in nova service list".format(service)) 
                check_for = {'6':'controller','8':'internal','10':'enabled','12':'up'}

                for location, correct_value in check_for.iteritems():
                    if (run("nova service-list | awk '/{}/ {print $"+ location +"}'".format(service)) == correct_value):
                        print align_y("{} host is {}".format(service, correct_value)) 
                    else:
                        print align_n("{} host is NOT {}".format(service, correct_value))  
            else:
                print align_n("{} does NOT exist in nova service list".format(service)) 

        # separate check for nova-compuet as it has different values
        service = 'nova-compute'
        if service in run("nova service-list"):
            print align_y("{} exists in nova service list".format(service)) 
            check_for = {'6':'compute1','8':'nova','10':'enabled','12':'up'}
            
            for location, correct_value in check_for.iteritems():
                if (run("nova service-list | awk '/{}/ {print $"+ location +"}'".format(service)) == correct_value):
                print align_y("{} host is {}".format(service, correct_value)) 
            else:
                print align_n("{} host is NOT {}".format(service, correct_value))  
        else:
            print align_n("{} does NOT exist in nova service list".format(service)) 

                
                '''        
                if (run("nova service-list | awk '/{}/ {print $6}'".format(service)) == 'controller'):
                    print align_y("{} host is controller".format(service)) 
                else:
                    print align_n("{} host is NOT controller".format(service)) 

                if (run("nova service-list | awk '/{}/ {print $8}'".format(service)) == 'internal'):
                    print align_y("{} host is internal".format(service)) 
                else:
                    print align_n("{} host is NOT internal".format(service)) 

                if (run("nova service-list | awk '/{}/ {print $10}'".format(service)) == 'enabled'):
                    print align_y("{} host is enabled".format(service)) 
                else:
                    print align_n("{} host is NOT enabled".format(service)) 

                if (run("nova service-list | awk '/{}/ {print $12}'".format(service)) == 'up'):
                    print align_y("{} host is controller".format(service)) 
                else:
                    print align_n("{} host is NOT controller".format(service)) 
                '''


        # NEED TO DO TDD FOR THE ARGUMENT BELOW
        run("nova image-list")
    

def tdd():
    with settings(warn_only=True):
        # to be done on the controller node
        execute(verify)


