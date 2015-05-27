from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
import string
import logging
import subprocess

import sys
sys.path.append('../global_config_files')
import env_config





############################ Config ########################################

logging.basicConfig(filename='/var/log/juno2015', level=logging.DEBUG,format='%(asctime)s %(message)s')

env.roledefs = env_config.roledefs


# define local config file locations
database_script_file = 'config_files/database_creation.sql'
admin_openrc = '../global_config_files/admin-openrc.sh'
global_config = '../global_config_files/global_config'

# define host config file locations
neutron_conf = '/etc/neutron/neutron.conf'

# get passwords from their config file
passwd = env_config.read_dict('config_files/passwd')
passwd['RABBIT_PASS'] = local('crudini --get {} rabbitmq RABBIT_PASS'.format(global_config),capture=True)
nova_password_file = '../nova_development/nova_config'
# FIX THIS ONCE CENTOS IS REINSTALLED
# passwd['NOVA_PASS'] = local('crudini --get {} keystone NOVA_PASS'.format(nova_password_file),capture=True)
passwd['NOVA_PASS'] = '34nova_ks43'

################### General functions ########################################

# does sudo and logs the result
def sudo_log(command):
    output = sudo(command)
    logging.info(output)


################### Deployment ########################################

def create_neutron_database():

    # read script, removing comments
    database_script = "".join( [line for line in open(database_script_file,'r').readlines() \
            if line[0:2] != '--'] )
    # database_script = local("grep -v '^--' {}".format(database_script_file))

    # subtitute real password
    database_script = database_script.replace("NEUTRON_DBPASS",passwd["NEUTRON_DBPASS"])
    
    # send the commands to mysql client
    sudo('''echo "{}" | mysql -u root'''.format(database_script))

    # get the admin-openrc script to obtain access to admin-only CLI commands
    exports = open(admin_openrc,'r').read()
    with prefix(exports):

        # check if user neutron has been created and if not, create it
        if sudo('keystone user-list | grep neutron',warn_only=True).return_code != 0:
            # create the neutron user in keystone
            sudo('keystone user-create --name neutron --pass {}'.format(passwd['NEUTRON_PASS']))

            # add the admin role to the neutron user
            sudo('keystone user-role-add --user neutron --tenant service --role admin')

        # check if service neutron has been created and if not, create it
        if sudo('keystone service-list | grep neutron',warn_only=True).return_code != 0:
            # create the neutron service entity
            sudo('keystone service-create --name neutron --type network --description "OpenStack Networking"')

        # check if a 9696 endpoint already exists and if not, create one
        if sudo('keystone endpoint-list | grep 9696',warn_only=True).return_code != 0:
            # create the networking service API endpoints
            sudo('keystone endpoint-create ' + \
                    "--service-id $(keystone service-list | awk '/ network / {print $2}') " + \
                    "--publicurl http://controller:9696 " + \
                    "--adminurl http://controller:9696 " + \
                    "--internalurl http://controller:9696 " + \
                    "--region regionOne")

def configure_networking_server_component():
    # configure neutron.conf with crudini
    # crudini --set config_file section parameter value

    neutron_conf = '/etc/neutron/neutron.conf'
    
    # make a backup
    sudo('cp {} {}.back12'.format(neutron_conf,neutron_conf))

    # for testing
    neutron_conf_old = neutron_conf
    neutron_conf += '.back12'
    
    # configure database access
    parameter = 'mysql://neutron:{}@controller/neutron'.format(passwd['NEUTRON_DBPASS'])
    sudo('crudini --set {} database connection {}'.format(neutron_conf,parameter))

    # configure RabbitMQ access
    sudo('crudini --set {} DEFAULT rpc_backend rabbit'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT rabbit_host controller'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT rabbit_password {}'.format(neutron_conf,passwd['RABBIT_PASS']))

    # configure Identity service access

    sudo('crudini --set {} DEFAULT auth_strategy keystone'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken auth_uri http://controller:5000/v2.0'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken identity_uri http://controller:35357'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_tenant_name service'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_user neutron'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_password {}'.format(neutron_conf,passwd['NEUTRON_PASS']))

    # enable Modular Layer 2 plugin

    # get service tenant id
    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        nova_admin_tenant_id = sudo('keystone tenant-list | grep service | cut -d\| -f2')

    if nova_admin_tenant_id:
        # if tenant service doesn't exist, this variable will be empty
        sudo('crudini --set {} DEFAULT nova_admin_tenant_id {}'.format(neutron_conf, nova_admin_tenant_id))


    sudo('crudini --set {} DEFAULT notify_nova_on_port_status_changes True'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT notify_nova_on_port_data_changes True'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_url http://controller:8774/v2'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_admin_auth_url http://controller:35357/v2.0'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_region_name regionOne'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_admin_username nova'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_admin_password {}'.format(neutron_conf,passwd['NOVA_PASS']))

    # turn on verbose logging
    sudo('crudini --set {} DEFAULT verbose True'.format(neutron_conf))

    neutron_conf = neutron_conf_old


@roles('controller')
def controller_deploy():
    
    # create_neutron_database()

    # install the networking components of openstack
    # sudo('yum -y install openstack-neutron openstack-neutron-ml2 python-neutronclient which')

    configure_networking_server_component()


    

@roles('network')
def network_deploy():
    pass

@roles('compute')
def compute_deploy():
    pass

def deploy():
    # with settings(warn_only=True):
    execute(controller_deploy)

######################################## TDD #########################################

def tdd():
    with settings(warn_only=True):
        pass
