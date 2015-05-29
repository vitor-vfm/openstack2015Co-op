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

# get passwords from their config file
passwd = dict()
passwd['TROVE_PASS'] = local('crudini --get {} trove TROVE_PASS'.format(global_config),capture=True)
passwd['TROVE_DBPASS'] = local('crudini --get {} trove TROVE_DBPASS'.format(global_config),capture=True)
passwd['RABBIT_PASS'] = local('crudini --get {} rabbitmq RABBIT_PASS'.format(global_config),capture=True)
print passwd

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


@roles('controller')
def database_deploy():

    # install packages
    sudo('yum -y install openstack-trove python-troveclient')

    # create trove user on keystone
    # get the admin-openrc script to obtain access to admin-only CLI commands
    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        # check if user neutron has been created and if not, create it
        if sudo('keystone user-list | grep trove',warn_only=True).return_code != 0:
            # create the trove user in keystone
            sudo('keystone user-create --name trove --pass {}'.format(passwd['TROVE_PASS']),quiet=True)
            # add the admin role to the trove user
            sudo('keystone user-role-add --user trove --tenant service --role admin')

    set_trove_config_files()


def deploy():
    execute(database_deploy)
