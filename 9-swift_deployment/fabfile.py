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
import env_config


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

admin_openrc = "../global_config_files/admin-openrc.sh"
demo_openrc = "../global_config_files/demo-openrc.sh"

# Logging
log_file = 'swift_deployment.log'
env_config.setupLoggingInFabfile(log_file)

# Do a fabric run on the string 'command' and log results
run_log = lambda command : env_config.fabricLog(command,run,log_dict)
# Do a fabric run on the string 'command' and log results
sudo_log = lambda command : env_config.fabricLog(command,sudo,log_dict)

################### General functions ########################################

################### Deployment ########################################

def setUpKeystoneCredentialsController():
    exports = open(admin_openrc,'r').read()
    with prefix(exports):

        if 'swift' not in sudo("keystone user-list"):
            sudo_log("keystone user-create --name swift --pass {}".format(passwd['SWIFT_PASS']))
            sudo_log("keystone user-role-add --user swift --tenant service --role admin")
        else:
            logging.debug('swift is already a user. Do nothing',extra=log_dict)

        if 'swift' not in sudo("keystone service-list"):
            sudo_log('keystone service-create --name swift --type object-store --description "OpenStack Object Storage"')
        else:
            logging.debug('swift is already a service. Do nothing',extra=log_dict)

        if '8080' not in sudo("keystone endpoint-list"):
            command = "keystone endpoint-create \
                      --service-id $(keystone service-list | awk '/ object-store / {print $2}') \
                        --publicurl 'http://controller:8080/v1/AUTH_%(tenant_id)s' \
                          --internalurl 'http://controller:8080/v1/AUTH_%(tenant_id)s' \
                            --adminurl http://controller:8080 \
                              --region regionOne"
            sudo_log(command)
        else:
            logging.debug('8004 is already an endpoint. Do nothing',extra=log_dict)

def installPackagesController():
    sudo_log("yum -y install openstack-swift-proxy python-swiftclient python-keystone-auth-token \
              python-keystonemiddleware memcached")

def configureControllerNode():

    confFile = '/etc/swift/proxy-server.conf'
    baseConfFile = open(env_config.global_config_location + 'swift.proxy-server.conf').read()

    # create base conf file
    sudo_log("echo '{}' >>{}".format(baseConfFile,confFile))

    # set parameters
    sudo_log("crudini --set {} DEFAULT bind_port 8080".format(confFile))
    sudo_log("crudini --set {} DEFAULT user swift".format(confFile))
    sudo_log("crudini --set {} DEFAULT swift_dir /etc/swift".format(confFile))


    sudo_log("crudini --set {} pipeline:main pipeline 'authtoken cache healthcheck keystoneauth proxy-logging proxy-server'".format(confFile))
    sudo_log("crudini --set {} app:proxy-server allow_account_management true".format(confFile))
    sudo_log("crudini --set {} app:proxy-server account_autocreate true".format(confFile))

    sudo_log("crudini --set {} filter:keystoneauth use egg:swift#keystoneauth".format(confFile))
    sudo_log("crudini --set {} filter:keystoneauth operator_roles admin,_member_".format(confFile))

    sudo_log("crudini --set {} filter:authtoken paste.filter_factory keystonemiddleware.auth_token:filter_factory".format(confFile))
    sudo_log("crudini --set {} filter:authtoken auth_uri http://controller:5000/v2.0".format(confFile))
    sudo_log("crudini --set {} filter:authtoken identity_uri http://controller:35357".format(confFile))
    sudo_log("crudini --set {} filter:authtoken admin_tenant_name service".format(confFile))
    sudo_log("crudini --set {} filter:authtoken admin_user swift".format(confFile))
    sudo_log("crudini --set {} filter:authtoken admin_password {}".format(confFile,passwd['SWIFT_PASS']))
    sudo_log("crudini --set {} filter:authtoken delay_auth_decision true".format(confFile))

    sudo_log("crudini --set {} filter:cache memcache_servers 127.0.0.1:11211".format(confFile))

@roles('controller')
def controllerDeploy():

    # set up logging format dictionary
    global log_dict
    log_dict = {'host_string':env.host_string, 'role':'controller'}

    setUpKeystoneCredentialsController()
    configureControllerNode()


def deploy():
    execute(controllerDeploy)

######################################## TDD #########################################


@roles('controller')
def create_stack():

    # set up logging format dictionary
    global log_dict
    log_dict = {'host_string':env.host_string, 'role':'controller'}

    # upload admin-openrc.sh to set variables in host machine
    put(admin_openrc)
    put(heat_test_file)
    source_command = "source admin-openrc.sh"
    with prefix(source_command):
        sudo("NET_ID=$(nova net-list | awk '/ demo-net / { print $2 }')")
        sudo("""heat stack-create -f test-stack.yml -P "ImageID=cirros-0.3.3-x86_64;NetID=$NET_ID" testStack""")
        output = sudo("heat stack-list")

    if "testStack" in output:
        print(green("Stack created succesfully"))
    else:
        print(green("Stack NOT created"))
        
        
def tdd():
    with settings(warn_only=True):
        execute(create_stack)
