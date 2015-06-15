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
from myLib import align_n, align_y, database_check, keystone_check, run_v


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

etc_nova_config_file = "/etc/nova/nova.conf"
    
######################## Deployment ########################################

def setup_nova_database_on_controller(NOVA_DBPASS):

    mysql_commands = createDatabaseScript('nova',NOVA_DBPASS)
    
    msg = "Create database for Nova"
    runCheck(msg, 'echo "' + mysql_commands + '" | mysql -u root')
    


def setup_nova_keystone_on_controller(NOVA_PASS):
    """
    Set up Keystone credentials for Nova

    Create (a) a user and a service called 'nova', and 
    (b) an endpoint for the 'nova' service
    """

    # get admin credentials to run the CLI commands
    credentials = env_config.admin_openrc

    with prefix(credentials):
        # before each creation, we check a list to avoid duplicates

        if 'nova' not in run("keystone user-list"):
            msg = "Create user nova"
            runCheck(msg, "keystone user-create --name nova --pass {}".format(NOVA_PASS))

            msg = "Give the user nova the role of admin"
            runCheck(msg, "keystone user-role-add --user nova --tenant service --role admin")
        else:
            print blue("User nova already created. Do nothing")

        if 'nova' not in run("keystone service-list"):
            msg = "Create service nova"
            runCheck(msg, "keystone service-create --name nova --type compute --description 'OpenStack Compute'")
        else:
            print blue("Service nova already created. Do nothing")

        if 'http://controller:8774' not in run("keystone endpoint-list"):
            msg = "Create endpoint for service nova"
            runCheck(msg, "keystone endpoint-create " + \
                    "--service-id $(keystone service-list | awk '/ compute / {print $2}') " + \
                    "--publicurl http://controller:8774/v2/%\(tenant_id\)s  " + \
                    "--internalurl http://controller:8774/v2/%\(tenant_id\)s " + \
                    "--adminurl http://controller:8774/v2/%\(tenant_id\)s " + \
                    "--region regionOne")
        else:
            print blue("Enpoint for service nova already created. Do nothing")
    
def setup_nova_config_files_on_controller(NOVA_PASS, NOVA_DBPASS, RABBIT_PASS, CONTROLLER_MANAGEMENT_IP):

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

    set_parameter(etc_nova_config_file, 'DEFAULT', 'my_ip', CONTROLLER_MANAGEMENT_IP)
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_listen', CONTROLLER_MANAGEMENT_IP)
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_proxyclient_address', CONTROLLER_MANAGEMENT_IP)

    set_parameter(etc_nova_config_file, 'glance', 'host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'verbose', 'True')


def populate_database_on_controller():
    msg = "Populate database on controller node"
    runCheck(msg, "su -s /bin/sh -c 'nova-manage db sync' nova")

def start_nova_services_on_controller():
    nova_services = "openstack-nova-api.service openstack-nova-cert.service \
            openstack-nova-consoleauth.service openstack-nova-scheduler.service \
            openstack-nova-conductor.service openstack-nova-novncproxy.service"
    
    msg = "Enable nova services on controller"
    runCheck(msg, "systemctl enable " + nova_services)

    msg = "Start nova services on controller"
    runCheck(msg, "systemctl start " + nova_services)

def hardware_accel_check():
    """
    Determine whether compute node supports hardware acceleration for VMs
    """
    with settings(warn_only=True):
        output = run("egrep -c '(vmx|svm)' /proc/cpuinfo")    

    if int(output) < 1:
        print blue("Compute node does not support Hardware acceleration for virtual machines")
        print blue("Configure libvirt to use QEMU instead of KVM")
        set_parameter(etc_nova_config_file, 'libvirt', 'virt_type', 'qemu')


def setup_nova_config_files_on_compute(NOVA_PASS, NOVA_DBPASS, RABBIT_PASS, NETWORK_MANAGEMENT_IP):
    """
    Set up variables on several config files on the compute node
    """

    
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)

    set_parameter(etc_nova_config_file, 'DEFAULT', 'auth_strategy', 'keystone')

    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_user', 'nova')   
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_password', NOVA_PASS)   

    set_parameter(etc_nova_config_file, 'DEFAULT', 'my_ip', NETWORK_MANAGEMENT_IP)

    set_parameter(etc_nova_config_file, 'DEFAULT', 'vnc_enabled', 'True')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_listen', '0.0.0.0')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_proxyclient_address', NETWORK_MANAGEMENT_IP)
    set_parameter(etc_nova_config_file, 'DEFAULT', 'novncproxy_base_url', 'http://controller:6080/vnc_auto.html')


    set_parameter(etc_nova_config_file, 'glance', 'host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'verbose', 'True')

    hardware_accel_check()


def start_services_on_compute():
    msg = "Enable libvirt daemon"
    runCheck(msg, "systemctl enable libvirtd.service")
    msg = "Start libvirt daemon"
    runCheck(msg, "systemctl start libvirtd.service")

    msg = "Enable Nova service"
    runCheck(msg, "systemctl enable openstack-nova-compute.service")
    msg = "Start Nova service"
    runCheck(msg, "systemctl start openstack-nova-compute.service")

@roles('compute')
def setup_nova_on_compute():
    msg = 'Install Nova packages'
    installation_command = 'yum install -y openstack-nova-compute sysfsutils'
    runCheck(msg, installation_command)
    

    NETWORK_MANAGEMENT_IP = env_config.networkManagement['IPADDR']
    setup_nova_config_files_on_compute(passwd['NOVA_PASS'], passwd['NOVA_DBPASS'], passwd['RABBIT_PASS'], NETWORK_MANAGEMENT_IP)        

    start_services_on_compute()
    

@roles('controller')   
def setup_nova_on_controller():
    msg = 'Install Nova packages'
    installation_command = "yum install -y openstack-nova-api openstack-nova-cert " +\
            "openstack-nova-conductor openstack-nova-console openstack-nova-novncproxy " + \
            "openstack-nova-scheduler python-novaclient"
    runCheck(msg, installation_command)

    CONTROLLER_MANAGEMENT_IP = env_config.controllerManagement['IPADDR']

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
        # run the lists and save them in local files
        run('nova service-list >service-list',quiet=True)
        run('nova image-list >image-list',quiet=True)

        for service in nova_services:
            if service in run("cat service-list",quiet=True):
                print align_y("{} exists in nova service list".format(service)) 
                check_for = {'6':'controller','8':'internal','10':'enabled','12':'up'}

                for location, correct_value in check_for.iteritems():
                    current_value = run("cat service-list | awk '/%s/ {print $%s}'" % (service,location),quiet=True)
                    if (current_value.strip() == correct_value.strip()):
                        print align_y("{} host is {}".format(service, correct_value)) 
                    else:
                        print align_n("{} host is NOT {}".format(service, correct_value))  
                        logging.error("Expected service {}\'s status to be {}, got {}"\
                                .format(service,correct_value,current_value))
            else:
                print align_n("{} does NOT exist in nova service list".format(service)) 
                logging.error("{} does NOT exist in nova service list".format(service)) 

        # separate check for nova-compute as it has different values
        service = 'nova-compute'
        if service in run("cat service-list",quiet=True):
            print align_y("{} exists in nova service list".format(service)) 
            check_for = {'6':'compute1','8':'nova','10':'enabled','12':'up'}
            
            for location, correct_value in check_for.iteritems():
                current_value = run("cat service-list | awk '/%s/ {print $%s}'" % (service,location),quiet=True)
                if (current_value.strip() == correct_value):
                    print align_y("{} host is {}".format(service, correct_value)) 
                else:
                    print align_n("{} host is NOT {}".format(service, correct_value))  
                    logging.error("Expected service {}\'s status to be {}, got {}"\
                            .format(service,correct_value,current_value))
        else:
            print align_n("{} does NOT exist in nova service list".format(service)) 
            logging.error("{} does NOT exist in nova service list".format(service)) 

                
                # if (run("cat service-list | awk '/{}/ {print $6}'".format(service)) == 'controller'):
                #     print align_y("{} host is controller".format(service)) 
                # else:
                #     print align_n("{} host is NOT controller".format(service)) 

                # if (run("cat service-list | awk '/{}/ {print $8}'".format(service)) == 'internal'):
                #     print align_y("{} host is internal".format(service)) 
                # else:
                #     print align_n("{} host is NOT internal".format(service)) 

                # if (run("cat service-list | awk '/{}/ {print $10}'".format(service)) == 'enabled'):
                #     print align_y("{} host is enabled".format(service)) 
                # else:
                #     print align_n("{} host is NOT enabled".format(service)) 

                # if (run("cat service-list | awk '/{}/ {print $12}'".format(service)) == 'up'):
                #     print align_y("{} host is controller".format(service)) 
                # else:
                #     print align_n("{} host is NOT controller".format(service)) 


        # NEED TO DO TDD FOR THE ARGUMENT BELOW
        # Cehck if there is at least one image active
        if 'ACTIVE' in run("cat image-list",quiet=True):
            print align_y("images active".format(service)) 
        else:
            print align_n("no images active".format(service)) 
            logging.error("No images active on nova image-list")

        # run the lists and save them in local files
        run('rm service-list',quiet=True)
        run('rm image-list',quiet=True)

    

def tdd():
    with settings(warn_only=True):
        # to be done on the controller node
        execute(verify)


