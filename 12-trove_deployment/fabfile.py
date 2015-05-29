from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
import string
import subprocess

import sys
sys.path.append('../global_config_files')
import env_config


############################ Config ########################################

#logging.basicConfig(filename='/var/log/juno2015', level=logging.DEBUG,format='%(asctime)s %(message)s')

env.roledefs = env_config.roledefs

# define local config file locations
admin_openrc = '../global_config_files/admin-openrc.sh'
global_config = '../global_config_files/global_config'
global_config_location = env_config.global_config_location

# get passwords 
passwd = env_config.passwd

############################ Config ########################################

def set_trove_config_files():

    config_files = ['trove.conf','trove-taskmanager.conf','trove-conductor.conf']

    for fil in config_files:
        # set parameters
        sudo('crudini --set {} DEFAULT log_dir /var/log/trove'.format(fil))
        sudo('crudini --set {} DEFAULT trove_auth_url http://controller:5000/v2.0'.format(fil))
        sudo('crudini --set {} DEFAULT nova_compute_url http://controller:8774/v2'.format(fil))
        sudo('crudini --set {} DEFAULT cinder_url http://controller:8776/v1'.format(fil))
        sudo('crudini --set {} DEFAULT swift_url http://controller:8080/v1/AUTH_'.format(fil))
        sudo('crudini --set {} DEFAULT sql_connection mysql://trove:{}@controller/trove'.format(fil,passwd['TROVE_DBPASS']))
        sudo('crudini --set {} DEFAULT notifier_queue_hostname controller'.format(fil))
        sudo('crudini --set {} DEFAULT rpc_backend rabbit'.format(fil))
        sudo('crudini --set {} DEFAULT rabbit_host controller'.format(fil))
        sudo('crudini --set {} DEFAULT rabbit_password {}'.format(fil,passwd['RABBIT_PASS']))


def get_api_and_config():
    api_filename = "api-paste.ini"
    
    api_file = open(global_config_location + api_filename,'r').read()
    sudo("echo '{}' >{}".format(api_file,api_filename))

    sudo('crudini --set {} filter:authtoken auth_uri http://controller:5000/v2.0'.format(api_filename))
    sudo('crudini --set {} filter:authtoken {} {}'.format(api_filename, 'identity_uri','http://controller:35357'))
    sudo('crudini --set {} filter:authtoken {} {}'.format(api_filename, 'admin_user', 'trove'))
    sudo('crudini --set {} filter:authtoken {} {}'.format(api_filename, 'admin_password', passwd['TROVE_DBPASS']))
    sudo('crudini --set {} filter:authtoken {} {}'.format(api_filename, 'admin_tenant_name', 'service'))
    sudo('crudini --set {} filter:authtoken {} {}'.format(api_filename, 'signing_dir', '/var/cache/trove'))


    config_files = ['trove.conf','trove-taskmanager.conf','trove-conductor.conf']

    
    sudo('crudini --set {} DEFAULT {} {}'.format(config_files[0], 'default_datastore', 'mysql'))
    sudo('crudini --set {} DEFAULT {} {}'.format(config_files[0], 'add_addresses', 'True'))
    sudo('crudini --set {} DEFAULT {} {}'.format(config_files[0], 'network_label_regex', '^NETWORK_LABEL$'))
    sudo('crudini --set {} DEFAULT {} {}'.format(config_files[0], 'api_paste_config', ''))


    sudo('crudini --set {} DEFAULT {} {}'.format(config_files[1], 'nova_proxy_admin_user', 'admin'))
    sudo('crudini --set {} DEFAULT {} {}'.format(config_files[1], 'nova_proxy_admin_pass', passwd['ADMIN_PASS']))
    sudo('crudini --set {} DEFAULT {} {}'.format(config_files[1], 'nova_proxy_admin_tenant_name', 'service'))
    sudo('crudini --set {} DEFAULT {} {}'.format(config_files[1], 'taskmanager_manager', 'trove.taskmanager.manager.Manager'))


def setup_database():
    mysql_commands = "CREATE DATABASE IF NOT EXISTS trove;"
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON trove.* TO 'trove'@'localhost' IDENTIFIED BY '{}';".format(passwd['TROVE_DBPASS'])
    mysql_commands = mysql_commands + " GRANT ALL PRIVILEGES ON trove.* TO 'trove'@'%' IDENTIFIED BY '{}';".format(passwd['TROVE_DBPASS'])

    
    print("mysql commands are: " + mysql_commands)
    sudo('echo "{}" | mysql -u root'.format(mysql_commands))

def populate_database():
    sudo("""su -s /bin/sh -c "trove-manage db_sync" trove""")

    # not sure about following command 

#    sudo("""su -s /bin/sh -c "trove-manage datastore_update mysql ''" trove """)

def edit_trove_guestagent():

    fil = "trove-guestagent.conf"
    sudo('crudini --set {} "" rabbit_host controller'.format(fil))
    sudo('crudini --set {} "" rabbit_password {}'.format(fil,passwd['RABBIT_PASS']))

    sudo('crudini --set {} "" {} {}'.format(fil, 'nova_proxy_admin_user', 'admin'))
    sudo('crudini --set {} "" {} {}'.format(fil, 'nova_proxy_admin_pass', passwd['ADMIN_PASS']))
    sudo('crudini --set {} "" {} {}'.format(fil, 'nova_proxy_admin_tenant_name', 'service'))
    sudo('crudini --set {} "" {} {}'.format(fil, 'nova_proxy_admin_tenant_name', 'service'))
    sudo('crudini --set {} "" {} {}'.format(fil, 'trove_auth_url', 'http://controller:35357/v2.0'))   
    
    
def update_datastore():
    sudo(""" trove-manage --config-file /etc/trove/trove.conf datastore_version_update mysql mysql-5.5 mysql glance_image_ID mysql-server-5.5 1""")

def keystone_register():   
    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        if 'trove' not in sudo('keystone service-list'):
            sudo("""keystone service-create --name trove --type database  --description "OpenStack Database Service" """)
        if '8779' not in sudo('keystone endpoint-list'):
            sudo("""keystone endpoint-create \
                    --service-id $(keystone service-list | awk '/ trove / {print $2}') \
                    --publicurl http://controller:8779/v1.0/%\(tenant_id\)s \
                    --internalurl http://controller:8779/v1.0/%\(tenant_id\)s \
                    --adminurl http://controller:8779/v1.0/%\(tenant_id\)s \
                    --region regionOne """)

def start_services():
    sudo("systemctl enable openstack-trove-api.service openstack-trove-taskmanager.service openstack-trove-conductor.service")
    sudo("systemctl start openstack-trove-api.service openstack-trove-taskmanager.service  openstack-trove-conductor.service")

@roles('controller')
def database_deploy():

    # install packages
    sudo('yum -y install openstack-trove python-troveclient')

    # create trove user on keystone
    # get the admin-openrc script to obtain access to admin-only CLI commands
    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        # check if user neutron has been created and if not, create it
        if 'trove' not in sudo('keystone user-list'):
            # create the trove user in keystone
            sudo('keystone user-create --name trove --pass {}'.format(passwd['TROVE_PASS']),quiet=True)
            # add the admin role to the trove user
            sudo('keystone user-role-add --user trove --tenant service --role admin')

    with cd("/etc/trove/"):
        set_trove_config_files()
        get_api_and_config()
        setup_database()
        populate_database()
        edit_trove_guestagent()
        update_datastore()
        keystone_register()
        start_services()

def deploy():
    execute(database_deploy)

############################# TDD #####################################

@roles('controller')
def verify_database():
    exports = open(env_config.demo_openrc,'r').read()
    with prefix(exports):
        sudo("trove list")
        # output_old = sudo("trove list")
        # sudo("""trove create name 2 --size=2 --databases DBNAME \
        # --users USER:PASSWORD --datastore_version mysql-5.5 \
        # --datastore mysql """)
        # output_new = sudo("trove list")

def tdd():
    execute(verify_database)

