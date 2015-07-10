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
from myLib import database_check, keystone_check
from myLib import align_n, align_y, run_v, saveConfigFile


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

etc_nova_config_file = "/etc/nova/nova.conf"
    
######################## Deployment ########################################

@roles('controller')
def install_packages_controller():
    msg = 'Install Nova packages on controller node(s)'
    installation_command = "yum install -y openstack-nova-api openstack-nova-cert " + \
                           "openstack-nova-conductor openstack-nova-console openstack-nova-novncproxy " + \
                           "openstack-nova-scheduler python-novaclient"
    runCheck(msg, installation_command)

@roles('controller')
def setup_nova_database_on_controller():

    NOVA_DBPASS = passwd['NOVA_DBPASS']

    mysql_commands = createDatabaseScript('nova',NOVA_DBPASS)
    
    msg = "Create database for Nova"
    runCheck(msg, 'echo "' + mysql_commands + '" | mysql -u root -p' + env_config.passwd['ROOT_SECRET'])
    
@roles('controller')
def setup_nova_keystone_on_controller():
    """
    Set up Keystone credentials for Nova

    Create (a) a user and a service called 'nova', and 
    (b) an endpoint for the 'nova' service
    """

    NOVA_PASS = passwd['NOVA_PASS']

    # get admin credentials to run the CLI commands
    with prefix(env_config.admin_openrc):
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
            runCheck(msg, "keystone service-create --name nova --type compute " + \
                    "--description 'OpenStack Compute'")
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
    
@roles('controller')
def setup_nova_config_files_on_controller():

    NOVA_PASS = passwd['NOVA_PASS']
    NOVA_DBPASS = passwd['NOVA_DBPASS']
    RABBIT_PASS = passwd['RABBIT_PASS']
    CONTROLLER_MANAGEMENT_IP = env_config.nicDictionary['controller']['mgtIPADDR']

    set_parameter(etc_nova_config_file, 'database', 'connection', \
            'mysql://nova:{}@controller/nova'.format(NOVA_DBPASS))

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


@roles('controller')
def populate_database_on_controller():
    msg = "Populate database on controller node"
    runCheck(msg, "su -s /bin/sh -c 'nova-manage db sync' nova")

@roles('controller')
def start_nova_services_on_controller():
    nova_services = "openstack-nova-api.service openstack-nova-cert.service " + \
                    "openstack-nova-consoleauth.service openstack-nova-scheduler.service " + \
                    "openstack-nova-conductor.service openstack-nova-novncproxy.service"
    
    msg = "Enable nova services on controller"
    runCheck(msg, "systemctl enable " + nova_services)

    msg = "Start nova services on controller"
    runCheck(msg, "systemctl start " + nova_services)

    msg = "Restart nova services on controller"
    runCheck(msg, "systemctl restart " + nova_services)

@roles('compute')
def install_packages_compute():

    msg = 'Install Nova packages'
    installation_command = 'yum install -y openstack-nova-compute sysfsutils'
    runCheck(msg, installation_command)
    
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


@roles('compute')
def setup_nova_config_files_on_compute():
    """
    Set up variables on several config files on the compute node
    """

    NOVA_PASS = passwd['NOVA_PASS']
    NOVA_DBPASS = passwd['NOVA_DBPASS']
    RABBIT_PASS = passwd['RABBIT_PASS']
    NETWORK_MANAGEMENT_IP = env_config.nicDictionary['network']['mgtIPADDR']
    
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


@roles('compute')
def start_services_on_compute():
    msg = "Enable libvirt daemon"
    runCheck(msg, "systemctl enable libvirtd.service")
    msg = "Start libvirt daemon"
    runCheck(msg, "systemctl start libvirtd.service")
    msg = "Restart libvirt daemon"
    runCheck(msg, "systemctl restart libvirtd.service")

    msg = "Enable Nova service"
    runCheck(msg, "systemctl enable openstack-nova-compute.service")
    msg = "Start Nova service"
    runCheck(msg, "systemctl start openstack-nova-compute.service")
    msg = "Restart Nova service"
    runCheck(msg, "systemctl restart openstack-nova-compute.service")

@roles('controller') 
def setup_GlusterFS_Nova(): 
    """ 
    Configure the file path for the Nova Gluster volume 
    """ 
 
    # change the path that Glance uses for its file system 
    msg = 'Configure Nova to use Gluster' 
    glusterBrick = env_config.novaGlusterBrick 
 
    msg = 'Create local directory for the brick' 
    runCheck(msg, 'mkdir -p {}'.format(glusterBrick)) 
 
    msg = 'Set ownership of the brick' 
    runCheck(msg, 'chown -R nova:nova {}'.format(glusterBrick)) 
 
@roles('controller', 'compute') 
def setup_nova_conf_file(): 
    confFile = '/etc/nova/nova.conf'      
    #set_parameter(confFile, 'glance', 'libvirt_type', 'qemu') 
    set_parameter(confFile, 'DEFAULT', 'instances_path',  
            env_config.novaGlusterBrick)

################################## Deployment ########################################

def deploy():

    #nova installation on the controller
    execute(install_packages_controller)
    execute(setup_nova_database_on_controller)
    execute(setup_nova_keystone_on_controller)
    execute(setup_nova_config_files_on_controller)
    execute(populate_database_on_controller)
    execute(start_nova_services_on_controller)

    #nova installation on the compute
    execute(install_packages_compute)
    execute(setup_nova_config_files_on_compute)        
    execute(start_services_on_compute)

    execute(setup_nova_conf_file)
    execute(setup_GlusterFS_Nova)

######################################## TDD #########################################



@roles('controller')
def verify():

    result = 'OK'
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
                        result = 'FAIL'
                        logging.error("Expected service {}\'s status to be {}, got {}"\
                                .format(service,correct_value,current_value))
            else:
                print align_n("{} does NOT exist in nova service list".format(service)) 
                result = 'FAIL'
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
                    result = 'FAIL'
                    logging.error("Expected service {}\'s status to be {}, got {}"\
                            .format(service,correct_value,current_value))
        else:
            print align_n("{} does NOT exist in nova service list".format(service)) 
            result = 'FAIL'
            logging.error("{} does NOT exist in nova service list".format(service)) 

        # checks all statuses to make sure all images are ACTIVE
        statuses = run("cat image-list | awk '// {print $6}' ",quiet=True)
    
        statuses = statuses.split()
        for status in statuses[1:]:
            image_name = run("cat image-list | awk '/%s/ {print $4}'" % status,quiet=True)
            image_id = run("cat image-list | awk '/%s/ {print $2}'" % status,quiet=True)
            if status == 'ACTIVE':
                print align_y("Image: {}, ID: {} is {}".format(image_name, image_id, "ACTIVE"))
            else:
                print align_n("Image: {}, ID: {} is {}".format(image_name, image_id, "INACTIVE"))
                result = 'FAIL'
                logging.error("Image: {}, ID: {} is {}".format(image_name, image_id, "INACTIVE"))

        # run the lists and save them in local files
        run('rm service-list',quiet=True)
        run('rm image-list',quiet=True)

        return result
    

@roles('controller')
def tdd():
    with settings(warn_only=True):
        # save results of the tdds in a list
        results = list()

        res = database_check('nova')
        results.append(res)

        res = keystone_check('nova')
        results.append(res)

        res = verify()
        results.append(res)

        # check if any of the functions failed
        # and set status accordingly
        if any([r == 'FAIL' for r in results]):
            status = 'bad'
        else:
            status = 'good'

        # save config file
        saveConfigFile(etc_nova_config_file, status)
