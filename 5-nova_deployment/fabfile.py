from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.contrib.files import append
import logging
from subprocess import check_output
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
novaGlusterDir = "/mnt/gluster/instance"

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

    set_parameter(etc_nova_config_file, 'glance', 'host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'verbose', 'True')

    set_parameter(etc_nova_config_file, 'libvirt', 'cpu_mode', 'host-passthrough')    

    if 'ipmi5' in check_output('echo $HOSTNAME',shell=True):
        # set this parameter if we are not in production mode
        set_parameter(etc_nova_config_file, 'DEFAULT', 'novncproxy_host', '0.0.0.0')    
        set_parameter(etc_nova_config_file, 'DEFAULT', 'novncproxy_port', '6080')    
        set_parameter(etc_nova_config_file, 'DEFAULT', 'novncproxy_base_url', 'http://129.128.208.164:6080/vnc_auto.html')    
    else:
        set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_listen', CONTROLLER_MANAGEMENT_IP)
        set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_proxyclient_address', CONTROLLER_MANAGEMENT_IP)
        

        
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

@parallel
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


@parallel
@roles('compute')
def setup_nova_config_files_on_compute():
    """
    Set up variables on several config files on the compute node
    """

    NOVA_PASS = passwd['NOVA_PASS']
    NOVA_DBPASS = passwd['NOVA_DBPASS']
    RABBIT_PASS = passwd['RABBIT_PASS']
    MANAGEMENT_IP = env_config.nicDictionary[env.host]['mgtIPADDR']
    
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)

    set_parameter(etc_nova_config_file, 'DEFAULT', 'auth_strategy', 'keystone')

    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_user', 'nova')   
    set_parameter(etc_nova_config_file, 'keystone_authtoken', 'admin_password', NOVA_PASS)   

    set_parameter(etc_nova_config_file, 'DEFAULT', 'my_ip', MANAGEMENT_IP)

    set_parameter(etc_nova_config_file, 'DEFAULT', 'vnc_enabled', 'True')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_listen', '0.0.0.0')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_proxyclient_address', MANAGEMENT_IP)
    set_parameter(etc_nova_config_file, 'DEFAULT', 'novncproxy_base_url', 'http://controller:6080/vnc_auto.html')


    set_parameter(etc_nova_config_file, 'glance', 'host', 'controller')
    set_parameter(etc_nova_config_file, 'DEFAULT', 'verbose', 'True')

    set_parameter(etc_nova_config_file, 'libvirt', 'cpu_mode', 'host-passthrough')    

    if 'ipmi5' in check_output('echo $HOSTNAME',shell=True):
        # set this parameter if we are not in production mode
        set_parameter(etc_nova_config_file, 'DEFAULT', 'novncproxy_host', '0.0.0.0')    
        set_parameter(etc_nova_config_file, 'DEFAULT', 'novncproxy_port', '6080')    
        set_parameter(etc_nova_config_file, 'DEFAULT', 'novncproxy_base_url', 'http://129.128.208.164:6080/vnc_auto.html')    
    else:
        set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_listen', CONTROLLER_MANAGEMENT_IP)
        set_parameter(etc_nova_config_file, 'DEFAULT', 'vncserver_proxyclient_address', CONTROLLER_MANAGEMENT_IP)
        

    hardware_accel_check()


@parallel
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
    glusterDir = novaGlusterDir
 
    msg = 'Create local directory on the brick' 
    runCheck(msg, 'mkdir -p {}'.format(glusterDir)) 
 
    msg = 'Set ownership of the directory' 
    runCheck(msg, 'chown -R nova:nova {}'.format(glusterDir)) 
 
@roles('controller', 'compute') 
def setup_nova_conf_file(): 
    set_parameter(etc_nova_config_file, 'glance', 'libvirt_type', 'qemu') 
    set_parameter(etc_nova_config_file, 'DEFAULT', 'instances_path',  
            novaGlusterDir)

#@roles('controller', 'compute') 
#def fixme():


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

    #execute(setup_nova_conf_file)
    #execute(setup_GlusterFS_Nova)

######################################## TDD #########################################

@roles('controller')
def servicesTDD():
    "Check service-list to see if the nova services are up and running"

    with prefix(env_config.admin_openrc):
        msg = 'Get service list'
        serviceList = runCheck(msg, 'nova service-list >service-list')

    run('cat service-list')

    servlist = run('cat service-list | grep nova', quiet=True)

    # check if all services are running
    allRunning = True
    for line in servlist.splitlines():
        if 'enabled' not in line:
            print align_n('One of the services is not enabled')
            print line
            allRunning = False
        elif 'up' not in line: 
            print align_n('One of the services is not up')
            print line
            allRunning = False
    if allRunning:
        print align_y('All services OK')

    # check if all compute nodes are mentioned in the list
    computeNodes = [host.replace('root@','') for host in env.roledefs['compute']]
    allComputes = True
    for node in computeNodes:
        if node not in servlist:
            print align_n('%s is not mentioned in the service list' % node)
            allComputes = False
    if allComputes:
        print align_y('All compute nodes have a service')


    if not allRunning or not allComputes:
        saveConfigFile(etc_nova_config_file, 'bad')
        sys.exit(1)

@roles('controller')
def imageTDD():
    "Run image-list to verify connectivity with Keystone and Glance"

    with prefix(env_config.admin_openrc):
        msg = 'Run nova image-list'
        out = runCheck(msg, 'nova image-list')
        if 'ACTIVE' not in out:
            print align_n('No active images')
            saveConfigFile(etc_nova_config_file, 'bad')
            sys.exit(1)


@roles('controller')
def tdd():

    res = database_check('nova')
    if res == 'FAIL':
        saveConfigFile(etc_nova_config_file, 'bad')
        sys.exit(1)

    res = keystone_check('nova')
    if res == 'FAIL':
        saveConfigFile(etc_nova_config_file, 'bad')
        sys.exit(1)

    execute(servicesTDD)
    execute(imageTDD)

    # if all TDDs passed, save config files as 'good'
    saveConfigFile(etc_nova_config_file, 'good')
