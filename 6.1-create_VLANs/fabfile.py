
### Following server-world's instructions 
# http://www.server-world.info/en/note?os=CentOS_7&p=openstack_juno&f=15

from __future__ import with_statement
from fabric.api import *
from fabric.colors import green, red, blue
import string
import logging
import time

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, set_parameter, checkLog, restoreBackups, backupConfFile
from myLib import align_y, align_n, keystone_check, database_check, saveConfigFile


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

# DNS server for the subnets that will be created
dns = '129.128.208.13'

# filepaths of the various configuration files that will be edited
configs = {
'neutron' : '/etc/neutron/neutron.conf',
'ml2' : '/etc/neutron/plugins/ml2/ml2_conf.ini',
'l3' : '/etc/neutron/l3_agent.ini',
'dhcp' : '/etc/neutron/dhcp_agent.ini',
'ovs' : '/etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini',
}

# suffix for the backup files
backupSuffix = '.bak6.1'

# vlan specifications {tag:cidr}
vlans = env_config.vlans

# name for the test tenant that is used in this script
tenant = 'test-vlan'

# use the test tenant in the credentials
credentials = env_config.admin_openrc.replace('OS_TENANT_NAME=admin','OS_TENANT_NAME=' + tenant)

# networkVlanRanges = 'external:6:2131' 

############################# General ####################################

def removePort(port):
    "Given a port name, remove it using the OVS CLI"

    # Check if the port exists
    if ('Port ' + port) in run('ovs-vsctl show ', quiet=True):
        msg = 'Remove port ' + port
        runCheck(msg, 'ovs-vsctl del-port ' + port)
    else:
        print 'No port named ' + port

############################# Setup ################################

@roles('network')
def makeBridges():
    "Create virtual bridges and ports to enable VLAN tagging between the VMs"
    # Reference: http://www.opencloudblog.com/?p=614 

    # This script reverts the effects of the function
    # Run it in the host if stuff breaks
    script = 'revert_vlan'
    local('scp %s root@network:/root/%s' % (script, script))
    run('chmod +x %s' % script)
    run('source %s' % script)

    # Connecting br-int and the management interface breaks all connectivity
    # so we don't do it

    # create a bridge for vlan traffic
    msg = 'Create br-vlan bridge'
    runCheck(msg, 'ovs-vsctl add-br br-vlan')

    # Remove the connection between br-int and br-ex
    for port in ['phy-br-ex', 'int-br-ex']:
        removePort(port)

    # connect br-ex and br-vlan
    msg = 'Create a patch port from br-ex to br-vlan'
    runCheck(msg, 'ovs-vsctl add-port br-ex ex-to-vlan '
            '-- set Interface ex-to-vlan type=patch options:peer=vlan-to-ex')
    msg = 'Create a patch port from br-vlan to br-ex'
    runCheck(msg, 'ovs-vsctl add-port br-vlan vlan-to-ex '
            '-- set Interface vlan-to-ex type=patch options:peer=ex-to-vlan')

    # connect br-int and br-vlan
    msg = 'Create a patch port from br-int to br-vlan'
    runCheck(msg, 'ovs-vsctl add-port br-int int-to-vlan '
            '-- set Interface int-to-vlan type=patch options:peer=vlan-to-int')
    msg = 'Create a patch port from br-vlan to br-int'
    runCheck(msg, 'ovs-vsctl add-port br-vlan vlan-to-int '
            '-- set Interface vlan-to-int type=patch options:peer=int-to-vlan')

# File configuration ############################################################

@roles('controller','network','compute')
def setML2Conf():
    confFile = configs['ml2']
    backupConfFile(confFile, backupSuffix)
    set_parameter(confFile, 'ml2_type_vlan', 'network_vlan_ranges', 'physnet1:1000:2999')
    set_parameter(confFile, 'ovs', 'tenant_network_type', 'vlan')
    set_parameter(confFile, 'ovs', 'bridge_mappings', 'physnet1:br-ex')

@roles('network')
def setL3Conf():
    confFile = configs['l3']
    backupConfFile(confFile, backupSuffix)
    set_parameter(confFile, 'DEFAULT', 'external_network_bridge', 'br-ex')
       
@roles('network', 'compute')
def setConfs():
    execute(setML2Conf)
    execute(setL3Conf)

# Restart services ############################################################

@roles('network', 'compute')
def restartOVS():
    msg = 'Restart OpenvSwitch agent'
    runCheck(msg, 'systemctl restart openvswitch.service')

@roles('controller')
def restartNeutronServer():
    msg = 'Restart neutron server'
    runCheck(msg, 'systemctl restart neutron-server.service')

# Create router and networks ##################################################

# @roles('controller')
# def createRouter(router):
#     """
#     Create a virtual router for the VLANs
#     """

#     if router in run('neutron router-list'):
#         print blue('Router %s already created' % router)
#     else:
#         msg = 'Create virtual router'
#         runCheck(msg, 'neutron router-create ' + router)

# @roles('controller')
# def createIntNets(netNameBase, subnetNameBase, router):
#     """
#     Create internal networks, one for each VLAN, and associate them with the router
#     """
#     routerID = run("neutron router-list | awk '/%s/ {print $2}'" % router)

#     # save net-list locally to avoid querying the server multiple times
#     run('neutron net-list >net-list')

#     for tag, cidr in vlans.items():

#         netName = netNameBase + '.' + str(tag)
#         if netName in run('cat net-list'):
#             print blue('Net %s already created' % netName)
#         else:
#             msg = 'Create internal net ' + netName
#             runCheck(msg, 'neutron net-create ' + netName)

#         subnetName = subnetNameBase + '.' + str(tag)
#         if subnetName in run('neutron subnet-list'):
#             print blue('Subnet %s already created' % subnetName)
#         else:
#             msg = 'Create a subnet on the internal net ' + netName
#             runCheck(msg, 
#                     'neutron subnet-create '
#                     '--name %s ' % subnetName + \
#                     '--dns-nameserver 129.128.208.13 '
#                     '%s ' % netName + \
#                     '%s ' % cidr)

#         msg = 'Add interface on router to subnet ' + subnetName
#         subnetID = run("neutron subnet-list | awk '/%s/ {print $2}'" % subnetName)
#         runCheck(msg, "neutron router-interface-add %s %s" % (routerID, subnetID))

#     run('rm net-list')
#     run('neutron net-list')

# @roles('controller')
# def createExternalNet(netName, subnetCIDR, router):
#     """
#     Create an external network and associate it with the router
#     """
 
#     if netName in run('neutron net-list'):
#         print blue('Net %s already created' % netName)
#         return
#     else:
#         msg = 'Create external net'
#         runCheck(msg, 
#                 'neutron net-create %s ' % netName + \
#                 '--router:external=True '
#                 '--provider:network_type vlan')

#         msg = 'Create a subnet on the external net'
#         runCheck(msg, 
#                 'neutron subnet-create '
#                 '--name vlan-ext-subnet '
#                 # TODO(Vitor): The guide uses the default gateway as DNS. Is that right?
#                 # '--dns-nameserver 10.0.0.1 '
#                 # '--dns-nameserver 129.128.208.13 '
#                 '%s ' % netName + \
#                 '%s ' % subnetCIDR)

#     msg = 'Set gateway for the router as the external network'
#     routerID = run("neutron router-list | awk '/%s/ {print $2}'" % router)
#     extnetID = run("neutron net-list | awk '/%s/ {print $2}'" % netName)
#     runCheck(msg, "neutron router-gateway-set %s %s" % (routerID, extnetID))

#     # TEST (Vitor)
#     # msg = 'Connect external network and demo-router'
#     # runCheck(msg, "neutron router-interface-add demo-router vlan-ext-subnet")

# @roles('controller')
# def createRouterAndNetworks():
#     with prefix(env_config.admin_openrc): 
#         router = 'vlan-router'
#         execute(createRouter, router)
#         execute(createIntNets, 'vlan-net', 'vlan-subnet', router)
#         # execute(createExternalNet, 'vlan-ext-net', '10.0.0.0/24', router)

#         # TEST (Vitor)
#         msg = 'Connect external network and vlan-router'
#         runCheck(msg, "neutron router-interface-add vlan-router ext-net")

@roles('controller')
def createNeutronNetwork(netName, subnetName, tag, cidr):

    if netName in run('neutron net-list'):
        print blue('Network %s already created' % netName)
        return

    msg = 'Create net ' + netName
    runCheck(msg, 'neutron net-create %s --provider:segmentation_id %d' % 
            (netName, tag))

    msg = 'Create a subnet on net ' + netName
    runCheck(msg, 
            'neutron subnet-create --name %s %s %s'  % 
            (subnetName, netName, cidr))


@roles('controller')
def createRouter(routerName, subnetName):

    if routerName in run('neutron router-list'):
        print blue('Router %s already created' % routerName)
        return

    msg = 'Create virtual router for subnet ' + subnetName
    runCheck(msg, 'neutron router-create ' + routerName)

    msg = 'Connect vlan and router'
    # vlanID = run("neutron subnet-list | awk '/%d/ {print $2}'" % tag)
    runCheck(msg, "neutron router-interface-add %s %s" % (routerName, subnetName))

@roles('controller')
def createNetworks():
    """
    Create one network and one router for each VLAN in the vlans dict

    The router will connect the VLAN to the outside world
    """
    with prefix(env_config.admin_openrc): 

        # # save lists locally to avoid querying the database multiple times
        # run('neutron net-list >net-list')
        # run('neutron router-list >router-list')
        # run('neutron subnet-list >subnet-list')

        for tag, cidr in vlans.items():
            netName = 'vlan-net-' + str(tag)
            subnetName = 'vlan-subnet-' + str(tag)
            routerName = 'vlan-router-' + str(tag)
            execute(createNeutronNetwork, netName, subnetName, tag, cidr)
            execute(createRouter, routerName, subnetName)

#################################### Deployment ######################################

def deploy():
    pass

@roles('controller')
def test():
    execute(setConfs)
    execute(restartNeutronServer)
    execute(restartOVS)
    # execute(createRouterAndNetworks)
    execute(createNetworks)

#################################### Undeployment ######################################

@roles('network','compute')
def restoreOriginalConfFiles():
    # restoreBackups(configs.values(), backupSuffix)
    restoreBackups(configs['ml2'], backupSuffix)
    restoreBackups(configs['l3'], backupSuffix)

@roles('controller')
def undeploy():
    execute(restoreOriginalConfFiles)
    # execute(restartNeutronServer)
    # execute(restartOVS)
    local('cd ../devLib && ./service.sh -s 6 -a restart')

####################################### TDD ##########################################

def tdd():
    pass
