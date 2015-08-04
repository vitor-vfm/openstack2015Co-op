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

    # TODO: fix the following paragraph
    # Connecting br-int and the management interface breaks all connectivity

    # # connect br-int and the management interface
    # mgtInterface = env_config.nicDictionary[env.host]['mgtDEVICE']
    # msg = 'Add a port from br-int to the management interface'
    # runCheck(msg, 'ovs-vsctl add-port br-int ' + mgtInterface)

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

@roles('network', 'compute')
def setNeutronConf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = configs['neutron']
    
    backupConfFile(confFile, backupSuffix)

    section = 'DEFAULT'
    set_parameter(confFile, section, 'max_l3_agents_per_router', '2')
    set_parameter(confFile, section, 'l3_ha', 'False')
    set_parameter(confFile, section, 'allow_automatic_l3agent_failover', 'True')
    set_parameter(confFile, section, 'allow_overlapping_ips', 'True')
    set_parameter(confFile, section, 'core_plugin', 'ml2')
    set_parameter(confFile, section, 'service_plugins', 'router')
    # set_parameter(confFile, section, 'service_plugins', 'router,firewall,lbaas,vpnaas,metering')
    set_parameter(confFile, section, 'force_gateway_on_subnet', 'True')
    set_parameter(confFile, section, 'dhcp_options_enabled', 'False')
    set_parameter(confFile, section, 'dhcp_agents_per_network', '1')
    set_parameter(confFile, section, 'router_distributed', 'False')
    set_parameter(confFile, section, 'router_delete_namespaces', 'True')
    set_parameter(confFile, section, 'check_child_processes', 'True')

    section = 'securitygroup'
    set_parameter(confFile, section, 'firewall_driver', 
            'neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver')
    set_parameter(confFile, section, 'enable_ipset', 'True')
    set_parameter(confFile, section, 'enable_security_group', 'True')

    section = 'agent'
    set_parameter(confFile, section, 'enable_distributed_routing', 'False')
    set_parameter(confFile, section, 'dont_fragment', 'True')
    set_parameter(confFile, section, 'arp_responder', 'False')

    # Crudini doesn't work when a variable name is setup more than once, as is service_provider,
    # so for this one we use sed
    newLine = ['service_provider = FIREWALL:Iptables:neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver:default']
    run("sed -i \"/\[service_providers\]/a %s\" %s" % (newLine, confFile))

@roles('network', 'compute')
def setMl2Conf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = configs['ml2']
    
    backupConfFile(confFile, backupSuffix)

    set_parameter(confFile, 'ml2', 'type_drivers', 'gre,local,vlan,flat')
    set_parameter(confFile, 'ml2',  'mechanism_drivers', 'openvswitch')
     
    # sort the vlan tags to get the smallest and the largest
    networkVlanRanges = 'external:%d:%d' % (sorted(vlans)[0], sorted(vlans)[-1])
    set_parameter(confFile, 'ml2_type_vlan', 'network_vlan_ranges', networkVlanRanges)
       
    # Crudini doesn't work with the * character
    run("sed -i 's/flat_networks = external/flat_networks = */' %s" % confFile)
        
    set_parameter(confFile, 'ovs', 'bridge_mappings', 'external:br-vlan')
    set_parameter(confFile, 'ovs', 'integration_bridge' , 'br-int')
    # TODO: determine whether this should be vlan, gre, or both:
    # tenant_network_type = type of network a tenant can create
    set_parameter(confFile, 'ovs', 'tenant_network_type' , 'gre,vlan')
    set_parameter(confFile, 'ovs', 'local_ip' , 
            env_config.nicDictionary[env.host]['tnlIPADDR'])
         
    set_parameter(confFile, 'agent', 'l2_population' , 'False')

@roles('network', 'compute')
def setL3Conf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = configs['l3']
    backupConfFile(confFile, backupSuffix)

    # very important - set the two following entries to an empty string
    # do not leave the default values
    set_parameter(confFile, 'DEFAULT', 'gateway_external_network_id', '')
    set_parameter(confFile, 'DEFAULT', 'external_network_bridge', '')

    # we use the legacy mode - HA and DVR are broken in Juno and should 
    # not used in production environments
    set_parameter(confFile, 'DEFAULT', 'agent_mode', 'legacy')
    
    # nova metadata is deployed only on the network node(s) and listens on 127.0.0.1 node
    set_parameter(confFile, 'DEFAULT', 'metadata_port', '8775')
    set_parameter(confFile, 'DEFAULT', 'metadata_ip', '127.0.0.1')
    set_parameter(confFile, 'DEFAULT', 'enable_metadata_proxy', 'True')
    
    set_parameter(confFile, 'DEFAULT', 'handle_internal_only_routers', 'True')
    set_parameter(confFile, 'DEFAULT', 'router_delete_namespaces', 'True')
    
    # veths should be avoided
    set_parameter(confFile, 'DEFAULT', 'ovs_use_veth', 'False')
    
    set_parameter(confFile, 'DEFAULT', 'interface_driver', 
            'neutron.agent.linux.interface.OVSInterfaceDriver')
    set_parameter(confFile, 'DEFAULT', 'use_namespaces', 'True')

    # for testing
    set_parameter(confFile, 'DEFAULT', 'debug', 'True')

@roles('network', 'compute')
def setDHCPConf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = configs['dhcp']
    backupConfFile(confFile, backupSuffix)

    set_parameter(confFile, 'DEFAULT', 'dhcp_delete_namespaces', 'True')
    set_parameter(confFile, 'DEFAULT', 'enable_metadata_network', 'False')
    set_parameter(confFile, 'DEFAULT', 'enable_isolated_metadata', 'True')
    set_parameter(confFile, 'DEFAULT', 'use_namespaces', 'True')
    set_parameter(confFile, 'DEFAULT', 'ovs_use_veth', 'False')
    set_parameter(confFile, 'DEFAULT', 'dhcp_agent_manager', 
            'neutron.agent.dhcp_agent.DhcpAgentWithStateReport')

@roles('network', 'compute')
def setOVSConf():
    "Set ovs_neutron_plugin.ini"

    # This isn't specified in the source (opencloudblog), but the file exists
    # and it seems like it should also be setup

    confFile = configs['ovs']
    backupConfFile(confFile, backupSuffix)

    set_parameter(confFile, 'ovs', 'bridge_mappings', 'external:br-vlan')
    set_parameter(confFile, 'ovs', 'tenant_network_type', 'vlan')
    networkVlanRanges = 'external:%d:%d' % (sorted(vlans)[0], sorted(vlans)[-1])
    set_parameter(confFile, 'ovs', 'network_vlan_ranges', networkVlanRanges)
        
@roles('network', 'compute')
def setConfs():
    execute(setNeutronConf)
    execute(setMl2Conf)
    execute(setL3Conf)
    execute(setDHCPConf)
    execute(setOVSConf)

@roles('network', 'compute')
def restartOVS():
    msg = 'Restart OpenvSwitch agent'
    runCheck(msg, 'systemctl restart openvswitch.service')

@roles('controller')
def restartNeutronServer():
    msg = 'Restart neutron server'
    runCheck(msg, 'systemctl restart neutron-server.service')


################################### Vlans ####################################

@roles('controller')
def createTenant():
    "Create a tenant to test VLANs"

    with prefix(env_config.admin_openrc): 

        tenantList = run('keystone tenant-list')
        if tenant in tenantList:
            print blue("Tenant already created. Nothing done")
        else:
            msg = 'Create tenant ' + tenant
            runCheck(msg, 'keystone tenant-create --name %s --description "VLAN testing"' %
                    tenant)

            msg = 'Give the admin user the role of admin in the test tenant'
            runCheck(msg, 'keystone user-role-add --user admin --tenant %s --role admin' %
                    tenant)
    
@roles('controller')
def createNets():
    "Create Neutron networks for each VLAN"

    # TODO: still getting that same error in neutron-server.log:
    # "2015-07-31 15:45:07.964 27497 INFO neutron.api.v2.resource 
    #    [req-0088af38-0172-4f1d-baee-66f16b9b1484 None] 
    #    create failed (client error): Invalid input for operation: 
    #    network_type value vlan not supported."

    with prefix(credentials):
        for tag in vlans:
            netName = 'vlan' + str(tag)
            msg = 'Create net ' + netName
            runCheck(msg, 'neutron net-create %s ' % netName + \
                    '--router:external True '
                    '--provider:physical_network external '
                    '--provider:network_type vlan '
                    '--provider:segmentation_id %d ' % tag
                    )

@roles('controller')
def createSubnets():
    "Create Neutron subnets for each VLAN"

    with prefix(credentials):
        for tag, cidr in vlans.items():
            netName = 'vlan' + str(tag)
            subnetName = 'vlansub' + str(tag)
            msg = 'Create subnet ' + subnetName
            runCheck(msg, 'neutron subnet-create %s --name %s --dns-nameserver %s %s' % 
                    (netName, subnetName, dns, cidr))

@roles('controller')
def createTestInstances():
    # Assumes cirros-test has been created

    instancesPerVLAN = 2

    # Version with only one external network

    # netName = 'ext-net'
    # with prefix(credentials):
    #     netid = run("neutron net-list | awk '/%s/ {print $2}'" % netName)
    #     for tag in vlans.keys():
    #         for number in range(instancesPerVLAN):
    #             instName = 'testvlan-%d-%d' % (tag, number)
    #             msg = 'Create instance ' + instName 
    #             runCheck(msg, 'nova boot --flavor m1.tiny --image cirros-test '
    #                     '--security-group default --nic net-id=%s %s' % (netid, instName))


    # Version with one external network per VLAN

    with prefix(credentials):
        # save net-list locally
        run('neutron net-list >net-list')
        for tag in vlans:
            for instNbr in range(instancesPerVLAN):
                netName = 'vlan' + str(tag)
                instName = 'testvlan-%d-%d' % (tag, instNbr)
                netid = run("cat net-list | awk '/%s/ {print $2}'" % netName)
                msg = 'Create instance ' + instName
                runCheck(msg, 
                        'nova boot '
                        '--flavor m1.tiny '
                        '--image cirros-test '
                        '--security-group default '
                        '--nic net-id=' + netid + ' '
                        + instName
                        )

@roles('controller')
def createVLANs():
    execute(createTenant)
    execute(createNets)
    execute(createSubnets)
    execute(createTestInstances)

#################################### Deployment ######################################

def deploy():
    pass

#################################### Undeployment ######################################

# These functions restore the network to its original state (before this script was deployed)

@roles('controller')
def removeResources():

    with prefix(credentials):

        # This bash command grabs all IDs from an openstack table and deletes each one
        deletionCommand = "for id in $(%s | tail -n +4 | head -n -1 | awk '{print $2}'); do " + \
                "%s $id; " + \
                "done"

        msg = 'Remove all instances'
        runCheck(msg, deletionCommand % ('nova list', 'nova delete'))

        msg = 'Remove all subnets'
        runCheck(msg, deletionCommand % ('neutron subnet-list ', 'neutron subnet-delete'))

        msg = 'Remove all nets'
        runCheck(msg, deletionCommand % ('neutron net-list ', 'neutron net-delete'))

        msg = 'Remove all routers'
        runCheck(msg, deletionCommand % ('neutron router-list ', 'neutron router-delete'))

@roles('network','compute')
def restoreOriginalConfFiles():
    restoreBackups(configs.values(), backupSuffix)

@roles('controller')
def undeploy():
    execute(removeResources)
    execute(restoreOriginalConfFiles)

####################################### TDD ##########################################

@roles('controller')
def test():
    execute(makeBridges)
    execute(setConfs)
    execute(restartNeutronServer)
    execute(restartOVS)
    execute(createVLANs)
    pass

def tdd():
    pass
