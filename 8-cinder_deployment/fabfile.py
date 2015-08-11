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
from myLib import align_n, align_y, checkLog


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

etc_cinder_config_file = "/etc/cinder/cinder.conf"

passwd = env_config.passwd

cinderGlusterDir = "/mnt/gluster/cinder"

nfs_share = env_config.nfs_share

################### General functions ######################################

@roles('controller')
def setup_cinder_database_on_controller():

    mysql_commands = createDatabaseScript("cinder",passwd['CINDER_DBPASS'])    
    msg = 'Create the database'
    runCheck(msg, 'echo "%s" | mysql -u root -p%s' % (mysql_commands, 
        env_config.passwd['ROOT_SECRET']))

@roles('controller')
def setup_cinder_keystone_on_controller():

    with prefix(env_config.admin_openrc):

        if 'cinder' not in run("keystone user-list"):
            runCheck('Create a cinder user',
                    "keystone user-create --name cinder --pass %s" % passwd['CINDER_PASS'])
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

        if 'http://controller:8776' not in run("keystone endpoint-list"):
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

    installation_command = "yum install -y openstack-cinder python-oslo-db MySQL-python"
    # installation_command = "yum install -y openstack-cinder python-cinderclient python-oslo-db"

    runCheck('Install the packages', installation_command)
    
    set_parameter(etc_cinder_config_file, 'database', 'connection', 
            'mysql://cinder:%s@controller/cinder' % passwd['CINDER_DBPASS'])

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rpc_backend', 'rabbit')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_host', 'controller')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'rabbit_password', passwd['RABBIT_PASS'])

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'auth_strategy', 'keystone')

    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'auth_uri', 
            'http://controller:5000/v2.0')
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'identity_uri', 
            'http://controller:35357') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_user', 'cinder')   
    set_parameter(etc_cinder_config_file, 'keystone_authtoken', 'admin_password', 
            passwd['CINDER_PASS'])   

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'my_ip', 
           env_config.nicDictionary['controller']['mgtIPADDR'])

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'glance_host', 'controller') # new line

    set_parameter(etc_cinder_config_file, 'DEFAULT', 'verbose', 'True')


@roles('controller')
def populate_database_on_controller():
    msg = 'Populate the Block Storage database'
    runCheck(msg, "su -s /bin/sh -c 'cinder-manage db sync' cinder")

@roles('controller')
def start_cinder_services_on_controller():
    services = ['openstack-cinder-api','openstack-cinder-scheduler',
            'openstack-cinder-volume','target']

    for service in services:
        msg = 'Enable %s service' % service
        runCheck(msg, 'systemctl enable %s.service' % service)
        msg = 'Start %s service' % service
        runCheck(msg, 'systemctl start %s.service' % service)

@roles('storage')
def setup_cinder_config_files_on_storage():
    
    CINDER_DBPASS = passwd['CINDER_DBPASS']
    CINDER_PASS = passwd['CINDER_PASS']
    RABBIT_PASS = passwd['RABBIT_PASS']
    STORAGE_MANAGEMENT_IP = env_config.nicDictionary['storage1']['mgtIPADDR']

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

########################### Gluster ###########################################

@roles('controller')
def change_cinder_file_for_gluster():
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'volume_driver', 'cinder.volume.drivers.glusterfs.GlusterfsDriver')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'glusterfs_shares_config', '/etc/cinder/shares.conf')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'state_path', cinderGlusterDir)
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'glusterfs_mount_point_base', "'$state_path'")

@roles('controller')
def change_shares_file_for_gluster():
    runCheck('Make shares.conf file', 'touch /etc/cinder/shares.conf')
    runCheck('Make export path for cinder', 'mkdir -p %s' % cinderGlusterDir)
    runCheck('Change permissions for export path for cinder', 'chown -R cinder:cinder %s' % cinderGlusterDir)
    # runCheck('Fill shares.conf file', 'echo "192.168.1.11:/cinder_volume -o backupvolfile-server=192.168.1.31" > /etc/cinder/shares.conf')
    #runCheck('Fill shares.conf file', 'echo "%s:/%s" > /etc/cinder/shares.conf' % (env_config.nicDictionary['controller']['mgtIPADDR'], env_config.gluster_volume))
    runCheck('Fill shares.conf file', 'echo "localhost:/%s" > /etc/cinder/shares.conf' % env_config.gluster_volume)

@roles('controller')
def restart_cinder():
    services = ['api', 'scheduler', 'volume']
    for service in services:
        msg = 'Restart cinder-%s' % service
        runCheck(msg, 'systemctl restart openstack-cinder-%s' % service)

############################## NFS ############################################

@roles('storage')
def install_nfs_on_storage():
    runCheck("Install NFS", "yum install nfs-utils rpcbind -y")

@roles('storage')
def make_nfs_directories():
    runCheck("Make nfs cinder directory", "mkdir %s" % nfs_share)
    runCheck("Make nfs swift directory", "mkdir /home/swift")

    runCheck("Setup exports file", "echo '%s 192.168.1.0/24(rw,sync)'>/etc/exports" % nfs_share)
    runCheck("Continue setting up exports file", "echo '/home/swift 192.168.1.0/24(rw,sync)'>>/etc/exports")
    
    runCheck("Change cinder NFS file permissions", "chown -R 65534:65534 %s/" nfs_share)
    
@roles('storage')
def export_and_start_nfs():
    runCheck("Export the file system", "exportfs -a")
    
    runCheck("Start rpcbind", "service rpcbind start && chkconfig rpcbind on")
    runCheck("Start NFS", "service rpcbind start; service nfs start")

@roles('controller')
def change_shares_file_for_nfs():
    runCheck('Make shares.conf file', "echo 'storage1:/%s' > /etc/cinder/shares.conf" % nfs_share)
    runCheck('Change permissions for shares.conf file', 'chown root:cinder /etc/cinder/shares.conf')
    runCheck('Make shares.conf file readable to members of the cinder group',
                'chmod 0640 /etc/cinder/shares.conf')
    
@roles('controller')
def change_cinder_file_for_nfs():
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'nfs_shares_config', '/etc/cinder/shares.conf')
    set_parameter(etc_cinder_config_file, 'DEFAULT', 'volume_driver', 'cinder.volume.drivers.nfs.NfsDriver')

@roles('controller')
def install_nfs_on_controller():
    # ref: http://www.unixmen.com/setting-nfs-server-client-centos-7/
    # may need to do this on both controller & storage
    runCheck("Install NFS", "yum install nfs-utils nfs-utils-lib -y")

@roles('controller')
def enable_and_start_nfs_services_on_controller():
    # ref: http://www.unixmen.com/setting-nfs-server-client-centos-7/
    # may need to do this on both controller & storage
    services_for_nfs = ["rpcbind", "nfs-server", "nfs-lock", "nfs-idmap"]

    # order maybe important... dont refactor into one loop
    # unless you know what your doing
    
    # enable them all
    for nfs_service in services_for_nfs:
        run("systemctl enable " + nfs_service, warn_only=True)
    
    # start them all
    for nfs_service in services_for_nfs:
        run("systemctl start " + nfs_service, warn_only=True)

########################### Deployment ########################################

def deploy():
    # setup cinder database
    execute(setup_cinder_database_on_controller)
    execute(setup_cinder_keystone_on_controller)
    execute(setup_cinder_config_files_on_controller)
    execute(populate_database_on_controller)
    execute(start_cinder_services_on_controller)

    # customize gluster to cinder
    #execute(change_cinder_file_for_gluster)
    #execute(change_shares_file_for_gluster)
    #execute(restart_cinder)

    # customize storage node for nfs
    execute(install_nfs_on_storage)
    execute(make_nfs_directories)
    execute(export_and_start_nfs)
    
    # customize cinder for nfs
    execute(install_nfs_on_controller)
    execute(enable_and_start_nfs_services_on_controller)
    execute(change_shares_file_for_nfs)
    execute(change_cinder_file_for_nfs)
    execute(restart_cinder)

################################# TDD #########################################

@roles(env_config.roles)
def showStatus():
    run('openstack-status')

@roles('controller')
def tdd():
    execute(showStatus)

    with prefix(env_config.admin_openrc):
        runCheck('List service components', 'cinder service-list')

    with prefix(env_config.demo_openrc):    
        timestamp = run('date +"%Y-%m-%d %H:%M:%S"',quiet=True)
        runCheck('Create a 1 GB volume', 
                'cinder create --display-name demo-volume1 1')

        msg = 'Verify creation and availability of volume'
        run('cinder list')
        status = run("cinder list | awk '/demo-volume1/ {print $4}'",quiet=True)
        if not status:
            print align_n('There is no volume called demo-volume1')
            sys.exit(1)
        else:
            # volume takes a while to build, so we loop until it's done
            while status != 'error' and status != 'available':
                status = run("cinder list | awk '/demo-volume1/ {print $4}'",quiet=True)

            if status == 'available':
                print align_y('demo-volume1 is available')
                runCheck('Delete test volume', 'cinder delete demo-volume1')
            else:
                print align_n('Problem with demo-volume1:')
                checkLog(timestamp)
                runCheck('Delete test volume', 'cinder delete demo-volume1')
                sys.exit(1)
