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
from myLib import database_check, keystone_check, run_v, align_n, align_y



############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

ceilometer_config_file = "/etc/ceilometer/ceilometer.conf"


######################## Deployment ########################################

def setup_ceilometer_keystone(CEILOMETER_PASS):
    """
    Set up Keystone credentials for Ceilometer

    Create (a) a user and a service called 'ceilometer', and 
    (b) an endpoint for the 'ceilometer' service
    """

    # get admin credentials to run the CLI commands
    credentials = env_config.admin_openrc

    with prefix(credentials):
        # before each creation, we check a list to avoid duplicates

        if 'ceilometer' not in run("keystone user-list"):
            msg = "Create user ceilometer"
            runCheck(msg, "keystone user-create --name ceilometer --pass {}".format(CEILOMETER_PASS))

            msg = "Give the user 'ceilometer the role of admin"
            runCheck(msg, "keystone user-role-add --user ceilometer --tenant service --role admin")
        else:
            print blue("User ceilometer already created. Do nothing")

        if 'ceilometer' not in run("keystone service-list"):
            msg = "Create service ceilometer"
            runCheck(msg, "keystone service-create --name ceilometer --type image --description 'Telemetry'")
        else:
            print blue("Service ceilometer already created. Do nothing")

        if 'http://controller:9292' not in run("keystone endpoint-list"):
            msg = "Create endpoint for service ceilometer"
            runCheck(msg, "keystone endpoint-create " + \
                    "--service-id $(keystone service-list | awk '/ metering / {print $2}') " +\
                    "--publicurl http://controller:8777 " + \
                    "--internalurl http://controller:8777 " + \
                    "--adminurl http://controller:8777 " + \
                    "--region regionOne")
        else:
            print blue("Endpoint for service ceilometer already created. Do nothing")
    
def setup_ceilometer_config_files(CEILOMETER_PASS, CEILOMETER_DBPASS):

    install_command = "yum install openstack-ceilometer-api openstack-ceilometer-collector " + \
        "openstack-ceilometer-notification openstack-ceilometer-central openstack-ceilometer-alarm " + \
        "python-ceilometerclient"
    
    run(install_command)
    
    metering_secret = run("openssl rand -hex 10")
    
    set_parameter(ceilometer_config_file, 'database', 'connection', 'mongodb://ceilometer:{}@controller:27017/ceilometer'.format(CEILOMETER_DBPASS))

    set_parameter(ceilometer_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(ceilometer_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(ceilometer_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)

    set_parameter(ceilometer_config_file, 'DEFAULT', 'auth_strategy', 'keystone')


    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'admin_user', 'ceilometer')   
    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'admin_password', CEILOMETER_PASS)   


    set_parameter(ceilometer_config_file, 'service_credentials', 'os_auth_url', 'http://controller:5000/v2.0')
    set_parameter(ceilometer_config_file, 'service_credentials', 'os_username', 'ceilometer')
    set_parameter(ceilometer_config_file, 'service_credentials', 'os_tenant_name', 'service')
    set_parameter(ceilometer_config_file, 'service_credentials', 'os_password', CEILOMETER_PASS)   


    set_parameter(ceilometer_config_file, 'publisher', 'metering_secret', metering_secret)

    set_parameter(ceilometer_config_file, 'DEFAULT', 'verbose', 'True')





    return metering_secret
    

def setup_mongo(CONTROLLER_IP):
    run("yum install -y mongodb-server mongodb")
    confFile = "/etc/mongod.conf"


    sed_command = """sed -i 's/bind_ip = 127.0.0.1/bind_ip = {}/g' {}""".format(CONTROLLER_IP, confFile)

    runCheck('set bind_ip',sed_command)

#    bind_ip_in_conf = run("cat {} | grep bind_ip | awk '// {print $3}'".format(confFile), quiet=True)
#    if CONTROLLER_IP == bind_ip_in_conf:
    bind_ip_in_conf = run("cat {} | grep bind_ip".format(confFile), quiet=True)
    if CONTROLLER_IP in bind_ip_in_conf:
        print(blue("bind_ip setup to " + CONTROLLER_IP))
    else:
        print(red("weird cuz bind_ip is " + bind_ip_in_conf))

    sed_command = """sed -i 's/#smallfiles = true/smallfiles = true/g' {}""".format(confFile)

    runCheck('set smallfiles = true',sed_command)

    smallfiles_in_conf = run("cat {} | grep smallfiles".format(confFile), quiet=True)
    if "smallfiles = true" in smallfiles_in_conf:
        print(blue("smallfiles setup to " + smallfiles_in_conf))
    else:
        print(red("weird cuz smallfiles is " + smallfiles_in_conf))
        

    runCheck('Enable mongo','systemctl enable mongod.service')
    runCheck('Start mongo','systemctl start mongod.service')
    runCheck('Restart mongo','systemctl restart mongod.service')
    

def create_mongo_ceilometer_db(CEILOMETER_PASS):
    command = """ mongo --host controller --eval ' """ + \
              """ db = db.getSiblingDB("ceilometer");  """ + \
              """  db.addUser({  """ + \
              """  user: "ceilometer",  """ + \
              """  pwd: "%s",  """ % CEILOMETER_PASS + \
              """  roles: [ "readWrite", "dbAdmin" ]  """ + \
              """  })'  """ 
    runCheck('setup ceilometer db in mongo', command) 

def start_ceilometer_services():
    ceilometer_services = "openstack-ceilometer-api.service openstack-ceilometer-notification.service " + \
                          "openstack-ceilometer-central.service openstack-ceilometer-collector.service " + \
                          "openstack-ceilometer-alarm-evaluator.service openstack-ceilometer-alarm-notifier.service " 

    msg = "Enable ceilometer services"
    runCheck(msg, "systemctl enable " + ceilometer_services)
    msg = "Start ceilometer services"
    runCheck(msg, "systemctl start " + ceilometer_services)
    msg = "Restart ceilometer services"
    runCheck(msg, "systemctl restart " + ceilometer_services) 

def install_packages():
    # Install packages
    msg = "Install OpenStack Ceilometer packages"
    runCheck(msg, "yum install -y openstack-ceilometer python-ceilometerclient",quiet=True)


@roles('controller')
def configure_image_service():
    image_config_file_names = ['/etc/glance/glance-api.conf','/etc/glance/glance-registry.conf']

    for image_config_file in image_config_file_names:
        set_parameter(image_config_file, 'DEFAULT', 'notification_driver', 'rabbit')
        set_parameter(image_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
        set_parameter(image_config_file, 'DEFAULT', 'rabbit_host', 'controller')
        set_parameter(image_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)
        
    run("systemctl restart openstack-glance-api.service openstack-glance-registry.service")

@roles('controller', 'storage')
def configure_block_storage():
    block_config_file = '/etc/cinder/cinder.conf'
    set_parameter(block_config_file, 'DEFAULT', 'control_exchange', 'cinder')
    set_parameter(block_config_file, 'DEFAULT', 'notification_driver', 'messagingv2')
        
    run("systemctl restart openstack-cinder-api.service openstack-cinder-scheduler.service")

    run("systemctl restart openstack-cinder-volume.service")

@roles('controller')
def configure_object_storage():
    object_config_file = '/etc/swift/proxy-server.conf'

    # get admin credentials to run the CLI commands
    credentials = env_config.admin_openrc

    with prefix(credentials):
        # before each creation, we check a list to avoid duplicates

        if 'Reseller' in run("keystone role-list"):
            print(blue("ResellerAdmin already set"))
        else:
            runCheck('','keystone role-create --name ResellerAdmin')
            runCheck('Create and add ResellerAdmin to ',"keystone user-role-add --tenant service --user ceilometer " + \
                     "--role $(keystone role-list | awk '/ResellerAdmin/ {print $2}')")


    set_parameter(object_config_file, 'filter:keystoneauth', 'operator_roles', 'admin,_member_,ResellerAdmin')
    set_parameter(object_config_file, 'pipeline:main', 'pipeline', 'authtoken cache healthcheck keystoneauth proxy-logging ceilometer proxy-server')
    set_parameter(object_config_file, 'filter:ceilometer', 'use', 'egg:ceilometer#swift')
    set_parameter(object_config_file, 'filter:ceilometer', 'log_level', 'WARN')
        
    runCheck('add swift to allow access to telemetry config files',"usermod -a -G ceilometer swift")

    runCheckm('restart swift',"systemctl restart openstack-swift-proxy.service")
    


   
@roles('controller')
def setup_ceilometer_controller():
    setup_mongo(env_config.controllerManagement['IPADDR'])
    create_mongo_ceilometer_db(env_config.passwd['CEILOMETER_PASS'])
    
    metering_secret = setup_ceilometer_keystone(passwd['CEILOMETER_PASS'])
    setup_ceilometer_config_files(passwd['CEILOMETER_PASS'], passwd['CEILOMETER_DBPASS'])
    start_ceilometer_services()

def install_and_configure_ceilometer(metering_secret, RABBIT_PASS, CEILOMETER_PASS):

    set_parameter(ceilometer_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(ceilometer_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(ceilometer_config_file, 'DEFAULT', 'rabbit_password', RABBIT_PASS)

    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'admin_user', 'ceilometer')   
    set_parameter(ceilometer_config_file, 'keystone_authtoken', 'admin_password', CEILOMETER_PASS)   


    set_parameter(ceilometer_config_file, 'service_credentials', 'os_auth_url', 'http://controller:5000/v2.0')
    set_parameter(ceilometer_config_file, 'service_credentials', 'os_username', 'ceilometer')
    set_parameter(ceilometer_config_file, 'service_credentials', 'os_tenant_name', 'service')
    set_parameter(ceilometer_config_file, 'service_credentials', 'os_password', CEILOMETER_PASS)   
    set_parameter(ceilometer_config_file, 'service_credentials', 'os_endpoint_type', 'internalURL')
    set_parameter(ceilometer_config_file, 'service_credentials', 'os_region_name', 'regionOne')


    set_parameter(ceilometer_config_file, 'publisher', 'metering_secret', metering_secret)

    set_parameter(ceilometer_config_file, 'DEFAULT', 'verbose', 'True')



def configure_notifications():
    conf_file = "/etc/nova/nova.conf" 
    
    set_parameter(conf_file, 'DEFAULT','instance_usage_audit', 'True')
    set_parameter(conf_file, 'DEFAULT','instance_usage_audit_period', 'hour')
    set_parameter(conf_file, 'DEFAULT','notify_on_state_change', 'vm_and_task_state')
    set_parameter(conf_file, 'DEFAULT','notification_driver', 'messagingv2')

def start_telemetry():
    run("enable telemetry","systemctl enable openstack-ceilometer-compute.service")
    run("start telemetry","systemctl start openstack-ceilometer-compute.service")
    run("restart telemetry","systemctl restart openstack-ceilometer-compute.service")

def restart_nova():
    run("systemctl restart openstack-nova-compute.service")

@roles('compute')
def setup_ceilometer_on_compute():
    install_and_configure_ceilometer(metering_secret, passwd['RABBIT_PASS'], passwd['CEILOMETER_PASS'])
    
    configure_notifications()

    start_telemetry()
    
    restart_nova()

        
################################## Deployment ########################################

def deploy():
    execute(setup_ceilometer)

######################################## TDD #########################################

def tdd():
    with settings(warn_only=True):
        execute(database_check,'ceilometer',roles=['controller'])
        execute(keystone_check,'ceilometer',roles=['controller'])
