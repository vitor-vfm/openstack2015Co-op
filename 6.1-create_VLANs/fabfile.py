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

neutron_conf = '/etc/neutron/neutron.conf'
ml2_conf_file = '/etc/neutron/plugins/ml2/ml2_conf.ini'
l3_agent_file = '/etc/neutron/l3_agent.ini'
dhcp_agent_file = '/etc/neutron/dhcp_agent.ini'
ovs_conf_file = '/etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini'

confFiles = [neutron_conf, ml2_conf_file, l3_agent_file, dhcp_agent_file, ovs_conf_file]
backupSuffix = '.bak6.1'

vlans = env_config.vlans


# name for the test tenant that is used in this script
tenant = 'test-vlan'

# use the test tenant in the credentials
credentials = env_config.admin_openrc.replace('OS_TENANT_NAME=admin','OS_TENANT_NAME=%s' % tenant)
# credentials = env_config.admin_openrc

vniRanges = '65537:69999'
networkVlanRanges = 'external:6:2131' 

############################# General ####################################

def removePort(port):
    if ('Port ' + port) in run('ovs-vsctl show ', quiet=True):
        msg = 'Remove port ' + port
        runCheck(msg, 'ovs-vsctl del-port ' + port)
    else:
        print 'No port named ' + port

############################# VxLAN setup ################################

@roles('network', 'compute')
def VxLAN_basicSetup():
    "Create and set up two bridges for the VxLAN"
    # Reference: http://www.opencloudblog.com/?p=614 

    msg = 'Create br-uplink bridge'
    runCheck(msg, 'ovs-vsctl add-br br-uplink')

    msg = 'Create br-vlan bridge'
    runCheck(msg, 'ovs-vsctl add-br br-vlan')

    physicalInterface = env_config.nicDictionary[env.host]['tnlDEVICE']

    msg = 'Add the physical interface as the uplink'
    runCheck(msg, 'ip link set dev %s up' % physicalInterface)

    # Increase MTU so make room for the VXLAN headers
    # How to set up switch?
    msg = 'Increase MTU on the uplink'
    runCheck(msg, 'ip link set dev %s mtu 1600' % physicalInterface)

    msg = 'Add a port from br-uplink to the physical interface'
    trunk = ",".join([str(tag) for tag in vlans.keys()])
    runCheck(msg, 'ovs-vsctl add-port br-uplink %s ' % physicalInterface + \
            '-- set port %s vlan_mode=trunk trunk=%s' % (physicalInterface, trunk))

    # Remove patch ports created by the flat network setup

    if 'network' in env.host:
        removePort('int-br-ex')
        removePort('phy-br-ex')

    removePort('patch-tun')
    removePort('patch-int')

    msg = 'Create a patch port from br-uplink to br-vlan'
    runCheck(msg, 'ovs-vsctl add-port br-uplink patch-to-vlan '
            '-- set Interface patch-to-vlan type=patch options:peer=patch-to-uplink')

    msg = 'Create a patch port from br-vlan to br-uplink'
    runCheck(msg, 'ovs-vsctl add-port br-vlan patch-to-uplink '
            '-- set Interface patch-to-uplink type=patch options:peer=patch-to-vlan')

    # We also need a patch port between br-vlan and br-int
    # opencloudblog says that it's created by Openstack, but it isn't

    msg = 'Create a patch port from br-int to br-vlan'
    runCheck(msg, 'ovs-vsctl add-port br-int int-to-vlan '
            '-- set Interface int-to-vlan type=patch options:peer=vlan-to-int')

    msg = 'Create a patch port from br-vlan to br-uplink'
    runCheck(msg, 'ovs-vsctl add-port br-vlan vlan-to-int '
            '-- set Interface vlan-to-int type=patch options:peer=int-to-vlan')

    # connect br-ex and br-vlan

    if 'network' in env.host:

        msg = 'Create a patch port from br-ex to br-vlan'
        runCheck(msg, 'ovs-vsctl add-port br-ex ex-to-vlan '
                '-- set Interface ex-to-vlan type=patch options:peer=vlan-to-ex')

        msg = 'Create a patch port from br-vlan to br-ex'
        runCheck(msg, 'ovs-vsctl add-port br-vlan vlan-to-ex '
                '-- set Interface vlan-to-ex type=patch options:peer=ex-to-vlan')

    # Remove GRE ports from br-tun
    # Irreversible; don't do this unless you're certain

    # portsInBrTun = run('ovs-vsctl list-ports br-tun').splitlines()
    # grePorts = [p for p in portsInBrTun if 'gre' in p]
    # for port in grePorts:
    #     msg = 'Remove port ' + port
    #     runCheck(msg, 'ovs-vsctl del-port ' + port)

@roles('network', 'compute')
def VxLAN_setNeutronConf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = neutron_conf
    
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

    # newLines = ['service_provider = VPN:openswan:neutron.services.vpn.service_drivers.ipsec.IPsecVPNDriver:default', 
    newLines = ['service_provider = FIREWALL:Iptables:neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver:default']

    for nl in newLines:
        run("sed -i \"/\[service_providers\]/a %s\" %s" % (nl, confFile))


@roles('network', 'compute')
def VxLAN_setMl2Conf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = ml2_conf_file
    
    backupConfFile(confFile, backupSuffix)

    set_parameter(confFile, 'ml2', 'type_drivers', 'vxlan,local,vlan,flat')
    # set_parameter(confFile, 'ml2', 'tenant_network_types', 'vxlan')
    set_parameter(confFile, 'ml2', 'tenant_network_types', 'vxlan,vlan')
    set_parameter(confFile, 'ml2',  'mechanism_drivers', 'openvswitch')
     
    set_parameter(confFile, 'ml2_type_vxlan', 'vni_ranges', vniRanges)
      
    set_parameter(confFile, 'ml2_type_vlan', 'network_vlan_ranges', networkVlanRanges)
       
    run("sed -i '/\[ml2_type_flat\]/a flat_networks\ =\ *' %s" % confFile)
        
    set_parameter(confFile, 'ovs', 'bridge_mappings', 'external:br-vlan')
    set_parameter(confFile, 'ovs', 'tunnel_type', 'vxlan')
    set_parameter(confFile, 'ovs', 'tunnel_bridge' , 'br-tun')
    set_parameter(confFile, 'ovs', 'integration_bridge' , 'br-int')
    set_parameter(confFile, 'ovs', 'tunnel_id_ranges' , vniRanges)
    set_parameter(confFile, 'ovs', 'enable_tunneling' , 'True')
    set_parameter(confFile, 'ovs', 'tenant_network_type' , 'vxlan')
    # set_parameter(confFile, 'ovs', 'tenant_network_type' , 'vlan')
    set_parameter(confFile, 'ovs', 'local_ip' , 
            env_config.nicDictionary[env.host]['tnlIPADDR'])
         
    set_parameter(confFile, 'agent', 'tunnel_types' , 'vxlan')
    set_parameter(confFile, 'agent', 'l2_population' , 'False')

    # msg = 'delete gre tunnel ranges'
    # runCheck(msg, 'crudini --del %s ml2_type_gre tunnel_id_ranges' % confFile)


@roles('network', 'compute')
def VxLAN_setL3Conf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = l3_agent_file
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
def VxLAN_setDHCPConf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = dhcp_agent_file
    backupConfFile(confFile, backupSuffix)

    set_parameter(confFile, 'DEFAULT', 'dhcp_delete_namespaces', 'True')
    set_parameter(confFile, 'DEFAULT', 'enable_metadata_network', 'False')
    set_parameter(confFile, 'DEFAULT', 'enable_isolated_metadata', 'True')
    set_parameter(confFile, 'DEFAULT', 'use_namespaces', 'True')
    set_parameter(confFile, 'DEFAULT', 'dhcp_driver', 'neutron.agent.linux.dhcp.Dnsmasq')
    set_parameter(confFile, 'DEFAULT', 'ovs_use_veth', 'False')
    set_parameter(confFile, 'DEFAULT', 'interface_driver', 
            'neutron.agent.linux.interface.OVSInterfaceDriver')
    set_parameter(confFile, 'DEFAULT', 'dhcp_agent_manager', 
            'neutron.agent.dhcp_agent.DhcpAgentWithStateReport')

@roles('network', 'compute')
def VxLAN_setOVSConf():
    "Set ovs_neutron_plugin.ini"

    # This isn't specified in the source (opencloudblog), but the file exists
    # and it seems like it should also be setup

    confFile = ovs_conf_file
    backupConfFile(confFile, backupSuffix)

    # set_parameter(confFile, 'ovs', 'bridge_mappings', 'external:br-vlan')
    # set_parameter(confFile, 'ovs', 'tenant_network_type', 'vlan')
    # set_parameter(confFile, 'ovs', 'network_vlan_ranges', networkVlanRanges)
        

    set_parameter(confFile, 'ovs', 'tenant_network_types', 'vlan,vxlan')
    set_parameter(confFile, 'ovs', 'network_vlan_ranges', networkVlanRanges)
    set_parameter(confFile, 'ovs', 'tenant_network_type', 'vxlan')
    # set_parameter(confFile, 'ovs', 'tenant_network_type', 'vlan')
    set_parameter(confFile, 'ovs', 'enable_tunneling' , 'True')
    set_parameter(confFile, 'ovs', 'tunnel_type', 'vxlan')
    set_parameter(confFile, 'ovs', 'tunnel_id_ranges' , vniRanges)
    set_parameter(confFile, 'agent', 'tunnel_types' , 'vxlan')

@roles('network', 'compute')
def restartOVS():
    msg = 'Restart OpenvSwitch agent'
    runCheck(msg, 'systemctl restart openvswitch.service')

@roles('controller')
def VxLAN_deploy():

    execute(VxLAN_basicSetup)
    execute(VxLAN_setNeutronConf)
    execute(VxLAN_setMl2Conf)
    execute(VxLAN_setL3Conf)
    # metadata agent is already set up correctly
    execute(VxLAN_setDHCPConf)
    execute(VxLAN_setOVSConf)

    # The reference (opencloudblog) mentions a certain 'nova-metadata.conf', but this file 
    # doesn't seem to exist in our installation. Maybe a legacy networking thing?

    msg = 'Restart neutron server'
    runCheck(msg, 'systemctl restart neutron-server.service')

    execute(restartOVS)

################################### InitialVlans ####################################

@roles('controller')
def VLAN_createTenant():
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
def VLAN_createNets():
    "Create Neutron networks for each VLAN"

    with prefix(credentials):

        for tag in vlans.keys():
            netName = 'vlan' + str(tag)
            msg = 'Create net ' + netName
            runCheck(msg, 'neutron net-create %s ' % netName + \
                    # '--router:external True '
                    '--provider:physical_network external '
                    '--provider:network_type vlan '
                    # '--provider:network_type flat '
                    '--provider:segmentation_id %s ' % tag
                    )

@roles('controller')
def VLAN_createSubnets():
    "Create Neutron subnets for each VLAN"

    with prefix(credentials):
        netName = 'ext-net'

        for tag in vlans.keys():
            # netName = 'vlan' + str(tag)
            subnetName = 'vlansub' + str(tag)
            cidr = vlans[tag]
            msg = 'Create subnet ' + subnetName
            runCheck(msg, 'neutron subnet-create %s --name %s --dns-nameserver 129.128.208.13 %s' % 
                    (netName, subnetName, cidr))

@roles('controller')
def VLAN_createTestInstances():
    # Assumes cirros-test has been created

    instancesPerVLAN = 1

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
        for tag in vlans.keys():
            for number in range(instancesPerVLAN):
                netName = 'vlan' + str(tag)
                instName = 'testvlan-%d-%d' % (tag, number)
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
def VLAN_deploy():

    execute(VLAN_createTenant)
    execute(VLAN_createNets)
    execute(VLAN_createSubnets)
    execute(VLAN_createTestInstances)

#################################### Deployment ######################################

def deploy():
    # execute(VxLAN_deploy)
    # execute(VLAN_deploy)
    pass

#################################### Undeployment ######################################

@roles('network', 'compute')
def deleteBridges():
    print 'Deleting ports'
    for port in ['int-to-vlan','ex-to-vlan','vlan-to-ex']:
        removePort(port)

    for br in ['br-uplink','br-vlan']:
        if ('Bridge ' + br) in run('ovs-vsctl show', quiet=True):
            msg = 'Delete bridge ' + br
            runCheck(msg, 'ovs-vsctl del-br ' + br)

@roles('controller')
def removeAllInstances():

    with prefix(credentials):

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
    restoreBackups(confFiles, backupSuffix)

@roles('controller')
def undeploy():
    execute(deleteBridges)
    execute(removeAllInstances)
    execute(restoreOriginalConfFiles)

####################################### TDD ##########################################

@roles('controller')
def test():
    execute(VxLAN_deploy)
    execute(VLAN_deploy)
    pass

def tdd():
    pass
