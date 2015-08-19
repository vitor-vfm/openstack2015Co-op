# Using a virtual interface to implement each vlan
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
bridge = {tag:('br-vlan-%d' % tag) for tag in vlans}

virtualInterfaces = env_config.virtualInterfaces

############################# General ####################################

def removePort(port):
    "Given a port name, remove it using the OVS CLI"
    msg = 'Remove port ' + port
    runCheck(msg, 'ovs-vsctl del-port ' + port)

@roles('network')
def removeBridge(br):
    if br in run("ovs-vsctl list-br"):
        msg = 'Delete bridge ' + br
        runCheck(msg, "ovs-vsctl del-br " + br)
    else:
        print blue('No bridge called ' + br)

# File configuration ############################################################

@parallel
@roles('controller','network','compute')
def setML2Conf():
    confFile = configs['ml2']
    backupConfFile(confFile, backupSuffix)

    physnets = ','.join(['physnet%d' % tag for tag in vlans])
    set_parameter(confFile, 'ml2_type_flat', 'flat_networks', 'external,' + physnets)
    # set vlan ranges
    # network_vlan_ranges will be set to, e.g.,
    # physnet208,physnet209,physnet2131:208:2131
    # physnets = ','.join(['physnet%d' % tag for tag in vlans])
    # set_parameter(confFile, 'ml2_type_vlan', 'network_vlan_ranges', 
    #         '%s:%s:%s' % (physnets, min(vlans), max(vlans)))
    
    # set_parameter(confFile, 'ovs', 'tenant_network_type', 'gre')

@parallel
@roles('network','compute')
def setOVSConf():
    confFile = configs['ovs']
    backupConfFile(confFile, backupSuffix)

    # set bridge mappings
    mappings = ','.join(['physnet%d:%s' % (tag, bridge[tag]) 
        for tag in vlans])
    set_parameter(confFile, 'ovs', 'bridge_mappings', 'external:br-ex,' + mappings) 

    set_parameter(confFile, 'ovs', 'enable_tunneling', 'True') 
    set_parameter(confFile, 'ovs', 'integration_bridge', 'br-int') 
    set_parameter(confFile, 'ovs', 'tunnel_bridge', 'br-tun') 

@roles('network')
def setL3Conf():
    confFile = configs['l3']
    backupConfFile(confFile, backupSuffix)

    # When external_network_bridge is set, each L3 agent can be associated
    # with no more than one external network. This value should be set to the UUID
    # of that external network. To allow L3 agent support multiple external
    # networks, both the external_network_bridge and gateway_external_network_id
    # must be left empty.

    set_parameter(confFile, 'DEFAULT', 'external_network_bridge', "''")
    set_parameter(confFile, 'DEFAULT', 'gateway_external_network_id', "''")

@roles('network', 'compute')
def setConfs():
    # execute(setML2Conf)
    execute(setL3Conf)
    execute(setOVSConf)

# Bridge creation  ############################################################

@roles('network')
def makeBridge(tag):
    """
    Given a VLAN tag, create its corresponding bridge
    """
    br= bridge[tag]
    if br in run('ovs-vsctl list-br'):
        print blue('Bridge %s already created' % br)
        return
    msg = 'Create bridge %s ' % br
    runCheck(msg, "ovs-vsctl add-br %s" % br)

@roles('network')
def connectBridgeAndInterface(tag):
    """
    Given a VLAN tag, connect the corresponding bridge and virtual interface
    """
    br = bridge[tag]
    interface = virtualInterfaces[tag]
    msg = 'Connect %s and %s' % (br, interface)
    runCheck(msg, "ovs-vsctl add-port  %s %s" % (br, interface))

@roles('network')
def connectBridgeAndBrInt(tag):
    """
    Given a VLAN tag, connect the corresponding bridge to the integration bridge
    """
    br = bridge[tag]
    msg = 'Create a patch port from br-int to %s' % br
    runCheck(msg, 'ovs-vsctl add-port br-int int-to-%s ' % br + \
            '-- set Interface int-to-%s type=patch options:peer=%s-to-int' % (br,br))
    msg = 'Create a patch port from %s to br-int' % br
    runCheck(msg, 'ovs-vsctl add-port %s %s-to-int ' % (br,br) + \
            '-- set Interface %s-to-int type=patch options:peer=int-to-%s' % (br,br))

@roles('network')
def setBridges():
    """
    Create and connect the OVS bridges for each VLAN
    """
    with prefix(env_config.admin_openrc):
        for tag in vlans:
            execute(makeBridge,tag)
            execute(connectBridgeAndInterface,tag)
            execute(connectBridgeAndBrInt,tag)

# Restart services ############################################################

@parallel
@roles('controller','network', 'compute')
def restartServices():
    msg = 'Restart services'
    runCheck(msg, 'openstack-service restart neutron')

# @roles('network', 'compute')
# def restartOVS():
#     msg = 'Restart OpenvSwitch agent'
#     runCheck(msg, 'systemctl restart openvswitch.service')

# @roles('controller')
# def restartNeutronServer():
#     msg = 'Restart neutron server'
#     runCheck(msg, 'systemctl restart neutron-server.service')

# Create router and networks ##################################################

@roles('controller')
def createNeutronNetwork(netName, subnetName, tag, cidr):

    if netName in run('neutron net-list'):
        print blue('Network %s already created' % netName)
        return

    msg = 'Create net ' + netName
    runCheck(msg, 'neutron net-create %s ' % netName + \
            '--router:external True '
            '--provider:network_type flat '
            '--provider:physical_network physnet%d ' % tag)

    msg = 'Create a subnet on net ' + netName
    runCheck(msg, 
            'neutron subnet-create --name %s %s %s --disable-dhcp '  % 
            (subnetName, netName, cidr))

# @roles('controller')
# def createRouter(routerName, subnetName):

#     if routerName in run('neutron router-list'):
#         print blue('Router %s already created' % routerName)
#         return

#     msg = 'Create virtual router for subnet ' + subnetName
#     runCheck(msg, 'neutron router-create ' + routerName)

#     msg = 'Connect vlan and router'
#     # vlanID = run("neutron subnet-list | awk '/%d/ {print $2}'" % tag)
#     runCheck(msg, "neutron router-interface-add %s %s" % (routerName, subnetName))

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
            execute(createNeutronNetwork, netName, subnetName, tag, cidr)
            # routerName = 'vlan-router-' + str(tag)
            # execute(createRouter, routerName, subnetName)

#################################### Deployment ######################################

def deploy():
    execute(setConfs)
    execute(setBridges)
    execute(restartServices)
    execute(createNetworks)

#################################### Undeployment ######################################

@roles('network','compute')
def restoreOriginalConfFiles():
    restoreBackups(configs['ml2'], backupSuffix)
    restoreBackups(configs['l3'], backupSuffix)

@roles('network')
def undeploy():
    execute(restoreOriginalConfFiles)
    for br in bridge.values():
        execute(removeBridge, br)

    # remove ports that were added
    listPorts = run('ovs-vsctl list-ports br-int').splitlines()
    for port in [p for p in listPorts if 'vlan' in p]: 
        execute(removePort, port)

    # restart all services
    execute(restartServices)

####################################### TDD ##########################################

@roles('network')
def test():
    pass

@roles('network')
def tdd():
    """
    Create some test instances
    """
    with prefix(env_config.admin_openrc): 
        for tag in vlans:
            netid = run("neutron net-list | grep vlan | awk '/%d/ {print $2}'" % tag)
            if not netid:
                print align_n("No vlan network found for tag %d" % tag)
                sys.exit(1)

            instanceName = 'test-vlan-%d' % tag
            msg = 'Launch instance for vlan %d' % tag
            runCheck(msg, 
                    "nova boot "
                    "--flavor m1.tiny "
                    "--image cirros-test "
                    "--nic net-id=%s "
                    "--security-group default "
                    " %s"
                    % (netid, instanceName))

        # restart all services
        # execute(restartServices)
        time.sleep(20)
        run('nova list')
