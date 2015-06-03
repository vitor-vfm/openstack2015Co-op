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

local_config = "config_files/"
management_interface = local_config + "management_interface"
hosts_file = local_config + "hosts_file"

# Logging
log_file = 'swift_deployment.log'
env_config.setupLoggingInFabfile(log_file)

# Do a fabric run on the string 'command' and log results
run_log = lambda command : env_config.fabricLog(command,run,log_dict)
# Do a fabric run on the string 'command' and log results
sudo_log = lambda command : env_config.fabricLog(command,sudo,log_dict)

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
    baseConfFile = open(local_config + 'proxy-server.conf').read()

    # create base conf file
    sudo_log("echo '{}' >{}".format(baseConfFile,confFile))

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

# STORAGE NODE

def setUpNIC(managementInterfaceNetworkScript,hostsFile):

    # put management interface script on host
    script = open(managementInterfaceNetworkScript,'r').read()

    deviceName = local("crudini --get {} '' DEVICE".format(managementInterfaceNetworkScript),capture=True)
    logging.debug("Grabbing device name for NIC : " + deviceName,extra=log_dict)

    remoteScript = '/etc/sysconfig/network-scripts/ifcfg-' + deviceName

    sudo_log("echo '{}' >{}".format(script,remoteScript))

    # put an alias on hosts file
    aliases = open(hostsFile,'r'),readlines()
    remoteFile = '/etc/hosts'
    # make backup
    sudo_log("cp {} {}.back12".format(remoteFile))

    for alias in aliases:
        # check if alias is already on file
        # if not, add it
        if alias in sudo_log("cat " + remoteFile):
            sudo_log("echo '{}' >>{}".format(alias, remoteFile))

    # restart networks
    sudo_log("service network stop")
    sudo_log("systemctl NetworkManager restart")
    sudo_log("service network start")

def installPackagesOnStorageNode():
    sudo_log("yum -y install openstack-swift-account openstack-swift-container openstack-swift-object")

def configureStorageNode():

    serverConfFiles = ['account-server.conf','container-server.conf','object-server.conf']

    managementInterfaceCfg = management_interface
    managementInterfaceIPAddress = local("crudini --get {} '' IPADDRESS".format(managementInterfaceCfg),capture=True)

    # save base files into the host
    for fil in serverConfFiles:
        localFile = local_config + fil
        remoteFile = '/etc/swift/' + fil
        sudo_log("echo '{}' >{}".format(localFile,remoteFile))

    # configure account-server.conf
    confFile = '/etc/swift/' + serverConfFiles[0]

    sudo_log("crudini --set {} DEFAULT bind_ip {}".format(confFile,managementInterfaceIPAddress))
    sudo_log("crudini --set {} DEFAULT bind_port 6002".format(confFile))
    sudo_log("crudini --set {} DEFAULT user swift".format(confFile))
    sudo_log("crudini --set {} DEFAULT swift_dir /etc/swift".format(confFile))
    sudo_log("crudini --set {} DEFAULT devices /srv/node".format(confFile))

    sudo_log("crudini --set {} pipeline:main pipeline healthcheck recon account-server".format(confFile))

    sudo_log("crudini --set {} filter:recon recon_cache_path = /var/cache/swift".format(confFile))

    # Edit the /etc/swift/container-server.conf file
    confFile = '/etc/swift/' + serverConfFiles[1]

    sudo_log("crudini --set {} DEFAULT bind_ip {}".format(confFile,managementInterfaceIPAddress))
    sudo_log("crudini --set {} DEFAULT bind_port 6001".format(confFile))
    sudo_log("crudini --set {} DEFAULT user swift".format(confFile))
    sudo_log("crudini --set {} DEFAULT swift_dir /etc/swift".format(confFile))
    sudo_log("crudini --set {} DEFAULT devices /srv/node".format(confFile))

    sudo_log("crudini --set {} pipeline:main pipeline healthcheck recon container-server".format(confFile))

    sudo_log("crudini --set {} filter:recon recon_cache_path /var/cache/swift".format(confFile))

    # Edit the /etc/swift/object-server.conf
    confFile = '/etc/swift/' + serverConfFiles[2]

    sudo_log("crudini --set {} DEFAULT bind_ip {}".format(confFile,managementInterfaceIPAddress))
    sudo_log("crudini --set {} DEFAULT bind_port 6000".format(confFile))
    sudo_log("crudini --set {} DEFAULT user swift".format(confFile))
    sudo_log("crudini --set {} DEFAULT swift_dir /etc/swift".format(confFile))
    sudo_log("crudini --set {} DEFAULT devices /srv/node".format(confFile))

    sudo_log("crudini --set {} pipeline:main pipeline healthcheck recon object-server".format(confFile))

    sudo_log("crudini --set {} filter:recon recon_cache_path = /var/cache/swift".format(confFile))


    # Ensure proper ownership of the mount point directory structure
    sudo_log("chown -R swift:swift /srv/node")

    # Create the recon directory and ensure proper ownership of it
    sudo_log("mkdir -p /var/cache/swift")
    sudo_log(" chown -R swift:swift /var/cache/swift")

def createRing(typeRing,port,IP,deviceName,deviceWeight):
    # ASSUMES A SINGLE DEVICE ON STORAGE NODE

    port = str(port)

    with cd('/etc/swift/'):
        # verify if ring is already there
        ringContents = sudo_log("swift-ring-builder {}.builder".format(typeRing)).splitlines()
        linesWithTheSpecs =  [l for l in ringContents if (IP in l and deviceName in l)]

        if not linesWithTheSpecs:
            # ring is not created yet

            # Create the base *.builder file
            sudo_log("swift-ring-builder {}.builder create 10 3 1".format(typeRing))

            # Add node to the ring
            sudo_log("swift-ring-builder {}.builder add r1z1-{}:{}/{} {}".format(typeRing,IP,port,deviceName,deviceWeight))

            # rebalance ring
            sudo_log("swift-ring-builder {}.builder rebalance")

def createInitialRings():

    managementIP = local("crudini --get {} '' IPADDR".format(management_interface),capture=True)
    deviceName = local("crudini --get {} '' DEVICE".format(management_interface),capture=True)
    deviceWeight = '100'

    # create account ring
    createRing('account',6002,managementIP,deviceName,deviceWeight)

    # create container ring
    createRing('container',6001,managementIP,deviceName,deviceWeight)

    # create object ring
    createRing('object',6000,managementIP,deviceName,deviceWeight)


def finalizeInstallation():

    baseFile = local_config + 'swift.conf'
    confFile = '/etc/swift/swift.conf'

    # put base config file on node
    putResult = put(baseFile,confFile)
    logging.debug(putResult,extra=log_dict)

    # In the [swift-hash] section, configure the hash path prefix and suffix for your environment
    hashPathPrefix = local("crudini --get {} '' HASH_PATH_PREFIX".format(swift_hash_values))
    hashPathSuffix = local("crudini --get {} '' HASH_PATH_SUFFIX".format(swift_hash_values))
    sudo_log("crudini --set {} swift-hash swift_hash_path_prefix {}".format(confFile,hashPathPrefix))
    sudo_log("crudini --set {} swift-hash swift_hash_path_suffix {}".format(confFile,hashPathSuffix))

    # In the [storage-policy:0] section, configure the default storage policy
    sudo_log("crudini --set {} storage-policy:0 name Policy-0".format(confFile))
    sudo_log("crudini --set {} storage-policy:0 default yes".format(confFile))

    # ensure proper ownership of the configuration directory 
    sudo_log("chown -R swift:swift /etc/swift")

    startOnController()

    # start the Object Storage services and configure them to start when the system boots
    sudo_log("systemctl enable openstack-swift-account.service openstack-swift-account-auditor.service \
              openstack-swift-account-reaper.service openstack-swift-account-replicator.service")
    sudo_log("systemctl start openstack-swift-account.service openstack-swift-account-auditor.service \
            openstack-swift-account-reaper.service openstack-swift-account-replicator.service")
    sudo_log("systemctl enable openstack-swift-container.service openstack-swift-container-auditor.service \
            openstack-swift-container-replicator.service openstack-swift-container-updater.service")
    sudo_log("systemctl start openstack-swift-container.service openstack-swift-container-auditor.service \
            openstack-swift-container-replicator.service openstack-swift-container-updater.service")
    sudo_log("systemctl enable openstack-swift-object.service openstack-swift-object-auditor.service \
            openstack-swift-object-replicator.service openstack-swift-object-updater.service")
    sudo_log("systemctl start openstack-swift-object.service openstack-swift-object-auditor.service \
            openstack-swift-object-replicator.service openstack-swift-object-updater.service")

@roles('controller')
def startOnController():
    # start the Object Storage proxy service on the controller node
    sudo_log("systemctl enable openstack-swift-proxy.service memcached.service")
    sudo_log("systemctl start openstack-swift-proxy.service memcached.service")


@roles('storage')
def storageDeploy():

    # set up logging format dictionary
    global log_dict
    log_dict = {'host_string':env.host_string, 'role':'controller'}

    installPackagesOnStorageNode()

    configureStorageNode()

    createInitialRings()

    finalizeInstallation()

# GENERAL DEPLOYMENT

def deploy():
    execute(controllerDeploy)
    execute(storageDeploy)

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
