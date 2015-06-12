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
sys.path.append('..')
import env_config
from myLib import database_check, keystone_check, run_v, align_n, align_y

############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

glance_api_config_file = "/etc/glance/glance-api.conf"
glance_registry_config_file = "/etc/glance/glance-registry.conf"

################### General functions ########################################


def set_parameter(config_file, section, parameter, value):
    crudini_command = "crudini --set {} {} {} {}".format(config_file, section, parameter, value)
    run(crudini_command)


def setup_glance_database(GLANCE_DBPASS):
    mysql_commands = "CREATE DATABASE IF NOT EXISTS glance;"
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'controller' IDENTIFIED BY '{}';".format(GLANCE_DBPASS)
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'%' IDENTIFIED BY '{}';".format(GLANCE_DBPASS)

    
    print("mysql commands are: " + mysql_commands)
    run("echo '{}' | mysql -u root".format(mysql_commands))
    


def setup_glance_keystone(GLANCE_PASS):
    with prefix(admin_openrc):
        if 'glance' not in sudo("keystone user-list"):
            run("keystone user-create --name glance --pass {}".format(GLANCE_PASS))
            run("keystone user-role-add --user glance --tenant service --role admin")
        else:
            pass
            #new logging method REQUIRED
            #log_debug('User glance already in user list')

        if 'glance' not in sudo("keystone service-list"):
            run("keystone service-create --name glance --type image --description 'OpenStack Image Service'")
        else:
            pass
            #new logging method REQUIRED
            #log_debug('Service glance already in service list')

        if '9292' not in sudo("keystone endpoint-list"):
            run("keystone endpoint-create --service-id $(keystone service-list | awk '/ image / {print $2}') --publicurl http://controller:9292 --internalurl http://controller:9292  --adminurl http://controller:9292 --region regionOne")
        else:
            pass
            #new logging method REQUIRED
            #log_debug('Endpoint 9292 already in endpoint list')
    
def setup_glance_config_files(GLANCE_PASS, GLANCE_DBPASS):
    run("yum install -y openstack-glance python-glanceclient")
    
    set_parameter(glance_api_config_file, 'database', 'connection', 'mysql://glance:{}@controller/glance'.format(GLANCE_DBPASS))
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'auth_uri', 'http://controller:5000/v2.0')
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'identity_uri', 'http://controller:35357') 
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_user', 'glance')   
    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_password', GLANCE_PASS)   
    set_parameter(glance_api_config_file, 'paste_deploy', 'flavor', 'keystone')

    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #

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

    #CHECK IF WE NEED TO:
    # "Comment out any auth_host, auth_port, and auth_protocol options because the identity_uri option replaces them." -- manual
    #

    set_parameter(glance_registry_config_file, 'DEFAULT', 'notification_driver', 'noop')
    set_parameter(glance_registry_config_file, 'DEFAULT', 'verbose', 'True')
    



def populate_database():
    run("su -s /bin/sh -c 'glance-manage db_sync' glance")

def start_glance_services():
    run("systemctl enable openstack-glance-api.service openstack-glance-registry.service")
    run("systemctl start openstack-glance-api.service openstack-glance-registry.service")


@roles('controller')
def setup_GlusterFS_controller():
    # change the path that Glance uses for its file system
    gluster_volume = env_config.volumeNames['glance']
    run_log('crudini --set /etc/glance/glance-api.conf '' \
            filesystem_store_datadir {}/images'.format(gluster_volume))

    run_log('mkdir -p {}/images'.format(gluster_volume))
    run_log('chown -R glance:glance {}'.format(gluster_volume))

    # Are we creating an instance store? Is Nova also using Gluster?

    # create the directory for the instance store
    # run_log('mkdir /mnt/gluster/instance/')
    # run_log('chown -R nova:nova /mnt/gluster/instance/')
    # run_log('service openstack-glance-api restart')

# Are we creating an instance store? Is Nova also using Gluster?
# @roles('compute')
# def setup_GlusterFS_compute():
#     # change the path that nova uses for its file system
#     run_log('crudini --set /etc/nova/nova-api.conf '' \
#             instances_path /mnt/gluster/instance')

#     run_log('mkdir -p /mnt/gluster/instance/')
#     run_log('chown -R nova:nova /mnt/gluster/instance/')
#     run_log('service openstack-nova-compute restart')

    pass

def setup_GlusterFS():
    # configure Glance to use a gluster FS volume
    execute(setup_GlusterFS_controller)

   
@roles('controller')
def setup_glance():

    # setup glance database
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
