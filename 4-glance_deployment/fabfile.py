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

glance_api_config_file = "/etc/glance/glance-api.conf"
glance_registry_config_file = "/etc/glance/glance-registry.conf"

######################## Deployment ########################################


def setup_glance_database(GLANCE_DBPASS):

    mysql_commands = createDatabaseScript('glance',GLANCE_DBPASS)
    
    msg = "Create database for keystone"
    runCheck(msg, 'echo "' + mysql_commands + '" | mysql -u root')
    


def setup_glance_keystone(GLANCE_PASS):
    """
    Set up Keystone credentials for Glance

    Create (a) a user and a service called 'glance', and 
    (b) an endpoint for the 'glance' service
    """

    # get admin credentials to run the CLI commands
    credentials = env_config.admin_openrc

    with prefix(credentials):
        # before each creation, we check a list to avoid duplicates

        if 'glance' not in run("keystone user-list"):
            msg = "Create user glance"
            runCheck(msg, "keystone user-create --name glance --pass {}".format(GLANCE_PASS))

            msg = "Give the user 'glance the role of admin"
            runCheck(msg, "keystone user-role-add --user glance --tenant service --role admin")
        else:
            print blue("User glance already created. Do nothing")

        if 'glance' not in run("keystone service-list"):
            msg = "Create service glance"
            runCheck(msg, "keystone service-create --name glance --type image --description 'OpenStack Image Service'")
        else:
            print blue("Service glance already created. Do nothing")

        if 'http://controller:9292' not in run("keystone endpoint-list"):
            msg = "Create endpoint for service glance"
            runCheck(msg, "keystone endpoint-create " + \
                    "--service-id $(keystone service-list | awk '/ image / {print $2}') " +\
                    "--publicurl http://controller:9292 " + \
                    "--internalurl http://controller:9292 " + \
                    "--adminurl http://controller:9292 " + \
                    "--region regionOne")
        else:
            print blue("Enpoint for service glance already created. Do nothing")
    
def setup_glance_config_files(GLANCE_PASS, GLANCE_DBPASS):
    
    set_parameter(glance_api_config_file, 'database', 'connection', 'mysql://glance:{}@controller/glance'.format(GLANCE_DBPASS))
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_user', 'glance')   
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_password', GLANCE_PASS)   
    set_parameter(glance_api_config_file, 'paste_deploy', 'flavor', 'keystone')

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

    set_parameter(glance_registry_config_file, 'DEFAULT', 'notification_driver', 'noop')
    set_parameter(glance_registry_config_file, 'DEFAULT', 'verbose', 'True')
    



def populate_database():
    msg = "Populate database"
    runCheck(msg, "su -s /bin/sh -c 'glance-manage db_sync' glance")

def start_glance_services():
    msg = "Enable glance services"
    runCheck(msg, "systemctl enable openstack-glance-api.service openstack-glance-registry.service")
    msg = "Start glance services"
    runCheck(msg, "systemctl start openstack-glance-api.service openstack-glance-registry.service")


@roles('controller')
def setup_GlusterFS_controller():
    # change the path that Glance uses for its file system
    gluster_volume = env_config.volumeNames['glance']
    runCheck(msg, 'crudini --set /etc/glance/glance-api.conf '' \
            filesystem_store_datadir {}/images'.format(gluster_volume))

    runCheck(msg, 'mkdir -p {}/images'.format(gluster_volume))
    runCheck(msg, 'chown -R glance:glance {}'.format(gluster_volume))

    # Are we creating an instance store? Is Nova also using Gluster?

    # create the directory for the instance store
    # runCheck(msg, 'mkdir /mnt/gluster/instance/')
    # runCheck(msg, 'chown -R nova:nova /mnt/gluster/instance/')
    # runCheck(msg, 'service openstack-glance-api restart')

# Are we creating an instance store? Is Nova also using Gluster?
# @roles('compute')
# def setup_GlusterFS_compute():
#     # change the path that nova uses for its file system
# runCheck(msg, 'crudini --set /etc/nova/nova-api.conf '' \
#             instances_path /mnt/gluster/instance')

# runCheck(msg, 'mkdir -p /mnt/gluster/instance/')
# runCheck(msg, 'chown -R nova:nova /mnt/gluster/instance/')
# runCheck(msg, 'service openstack-nova-compute restart')


def setup_GlusterFS():
    # configure Glance to use a gluster FS volume
    execute(setup_GlusterFS_controller)

   
@roles('controller')
def setup_glance():

    # Install packages
    msg = "Install OpenStack Glance packages"
    runCheck(msg, "yum install -y openstack-glance python-glanceclient")

    setup_glance_database(passwd['GLANCE_DBPASS'])
    
    setup_glance_keystone(passwd['GLANCE_PASS'])

    setup_glance_config_files(passwd['GLANCE_PASS'], passwd['GLANCE_DBPASS'])

    populate_database()

    start_glance_services()
        
################### Deployment ########################################

def deploy():
    execute(setup_glance)
    # setup_GlusterFS()

######################################## TDD #########################################



@roles('controller')
def glance_tdd():

    run_v("mkdir /tmp/images")
    url = "http://download.cirros-cloud.net/0.3.3/cirros-0.3.3-x86_64-disk.img"
    run("wget -P /tmp/images " + url)
    with prefix(admin_openrc):
        run("glance image-create --name 'cirros-0.3.3-x86_64' --file /tmp/images/cirros-0.3.3-x86_64-disk.img --disk-format qcow2 --container-format bare --is-public True --progress")
        output = run("glance image-list")

    if 'cirros-0.3.3-x86_64' in output:
        print(align_y("Successfully installed cirros image"))
    else:
        print(align_n("Couldn't install cirros image"))
        
    run("rm -r /tmp/images")

    
    database_check('glance')
    keystone_check('glance')

def tdd():
    with settings(warn_only=True):
        execute(glance_tdd)
