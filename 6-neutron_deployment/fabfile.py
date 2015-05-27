from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
import string

import sys
sys.path.append('../global_config_files')
import env_config


############################ Config ########################################

env.roledefs = env_config.roledefs

# get passwords from their config file
passwd = env_config.read_dict('config_files/passwd')

# define local config file locations
database_script_file = 'config_files/database_creation.sql'
admin_openrc = '../global_config_files/admin-openrc.sh'

# define host config file locations
neutron_conf = '/etc/neutron/neutron.conf'

################### General functions ########################################


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

    neutron_conf = 
@roles('controller')
def controller_deploy():
    
    create_neutron_database()

    # install the networking components of openstack
    sudo('yum -y install openstack-neutron openstack-neutron-ml2 python-neutronclient which')

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
