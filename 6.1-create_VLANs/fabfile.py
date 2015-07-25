from __future__ import with_statement
from fabric.api import *
from fabric.colors import green, red, blue
import string
import logging
import time

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, set_parameter, checkLog
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

# dict mapping VLAN tags to CIDRs
vlans = {
        208: '129.128.208.0/24',
        209: '129.128.209.0/24',
        6: '142.244.63.0/24',
        2131: '129.128.213.0/24',
        }

# name for the test tenant that is used in this script
tenant = 'test-vlan'

# use the test tenant in the credentials
credentials = env_config.admin_openrc.replace('OS_TENANT_NAME=admin','OS_TENANT_NAME=%s' % tenant)

vniRanges = '65537:69999'
networkVlanRanges = 'external:6:2131' 

############################# General ####################################

@roles('controller')
def backupConfFile(confFile):

    backupFile = confFile + '.bak'

    exists = run('[ -e %s ]' % backupFile, warn_only=True).return_code == 0

    if exists:
        print blue('Backup file already exists and will not be rewritten')
    else:
        msg = 'Make backup file'
        runCheck(msg, 'cp %s %s' % (confFile, backupFile))

############################# VxLAN setup ################################

@roles('network', 'compute')
def VxLANBasicSetup():
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

    # Remove GRE ports from br-tun
    # Irreversible; don't do this unless you're certain

    # portsInBrTun = run('ovs-vsctl list-ports br-tun').splitlines()
    # grePorts = [p for p in portsInBrTun if 'gre' in p]
    # for port in grePorts:
    #     msg = 'Remove port ' + port
    #     runCheck(msg, 'ovs-vsctl del-port ' + port)

@roles('network', 'compute')
def VxLANSetNeutronConf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = neutron_conf
    
    backupConfFile(confFile)

    section = 'DEFAULT'
    set_parameter(confFile, section, 'max_l3_agents_per_router', '2')
    set_parameter(confFile, section, 'l3_ha', 'False')
    set_parameter(confFile, section, 'allow_automatic_l3agent_failover', 'True')
    set_parameter(confFile, section, 'allow_overlapping_ips', 'true')
    set_parameter(confFile, section, 'core_plugin', 'ml2')
    set_parameter(confFile, section, 'service_plugins', 'router,firewall,lbaas,vpnaas,metering')
    set_parameter(confFile, section, 'force_gateway_on_subnet', 'true')
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

    section = 'service_providers'
    set_parameter(confFile, section, 'service_provider', 
            'LOADBALANCER:Haproxy:neutron.services.loadbalancer.drivers.'
            'haproxy.plugin_driver.HaproxyOnHostPluginDriver:default')
    set_parameter(confFile, section, 'service_provider', 
            'VPN:openswan:neutron.services.vpn.service_drivers.ipsec.IPsecVPNDriver:default')
    set_parameter(confFile, section, 'service_provider', 
            'FIREWALL:Iptables:neutron.agent.linux.iptables_firewall.'
            'OVSHybridIptablesFirewallDriver:default')


@roles('network', 'compute')
def VxLANSetMl2Conf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = ml2_conf_file
    
    backupConfFile(confFile)

    set_parameter(confFile, 'ml2', 'type_drivers', 'vxlan,local,vlan,flat')
    set_parameter(confFile, 'ml2', 'tenant_network_types', 'vxlan')
    set_parameter(confFile, 'ml2',  'mechanism_drivers', 'openvswitch')
     
    set_parameter(confFile, 'ml2_type_vxlan', 'vni_ranges', vniRanges)
      
    set_parameter(confFile, 'ml2_type_vlan', 'network_vlan_ranges', networkVlanRanges)
       
    set_parameter(confFile, 'ml2_type_flat', 'flat_networks', '*')
        
    set_parameter(confFile, 'ovs', 'bridge_mappings', 'external:br-vlan')
    set_parameter(confFile, 'ovs', 'tunnel_type', 'vxlan')
    set_parameter(confFile, 'ovs', 'tunnel_bridge' , 'br-tun')
    set_parameter(confFile, 'ovs', 'integration_bridge' , 'br-int')
    set_parameter(confFile, 'ovs', 'tunnel_id_ranges' , vniRanges)
    set_parameter(confFile, 'ovs', 'enable_tunneling' , 'True')
    set_parameter(confFile, 'ovs', 'tenant_network_type' , 'vxlan')
    set_parameter(confFile, 'ovs', 'local_ip' , 
            env_config.nicDictionary[env.host]['tnlIPADDR'])
         
    set_parameter(confFile, 'agent', 'tunnel_types' , 'vxlan')
    set_parameter(confFile, 'agent', 'l2_population' , 'False')

@roles('network', 'compute')
def VxLANSetL3Conf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = l3_agent_file
    backupConfFile(confFile)


    # very important - set the two following entries to an empty string
    # do not leave the default values
    set_parameter(confFile, 'DEFAULT', 'gateway_external_network_id', '')
    set_parameter(confFile, 'DEFAULT', 'external_network_bridge', '')

    # we use the legacy mode - HA and DVR are broken in Juno and should 
    # not used in production environments
    set_parameter(confFile, 'DEFAULT', 'agent_mode', 'legacy')
    
    # nova metadata is deployed only on the network node(s) and listens on controller node
    set_parameter(confFile, 'DEFAULT', 'metadata_port', '8775')
    set_parameter(confFile, 'DEFAULT', 'metadata_ip', 'controller')
    set_parameter(confFile, 'DEFAULT', 'enable_metadata_proxy', 'True')
    
    set_parameter(confFile, 'DEFAULT', 'handle_internal_only_routers', 'true')
    set_parameter(confFile, 'DEFAULT', 'router_delete_namespaces', 'True')
    
    # veths should be avoided
    set_parameter(confFile, 'DEFAULT', 'ovs_use_veth', 'false')
    
    set_parameter(confFile, 'DEFAULT', 'interface_driver', 
            'neutron.agent.linux.interface.OVSInterfaceDriver')
    set_parameter(confFile, 'DEFAULT', 'use_namespaces', 'true')

@roles('network', 'compute')
def VxLANSetDHCPConf():
    # Reference: http://www.opencloudblog.com/?p=630

    confFile = dhcp_agent_file
    backupConfFile(confFile)

    set_parameter(confFile, 'DEFAULT', 'dhcp_delete_namespaces', 'True')
    set_parameter(confFile, 'DEFAULT', 'enable_metadata_network', 'false')
    set_parameter(confFile, 'DEFAULT', 'enable_isolated_metadata', 'true')
    set_parameter(confFile, 'DEFAULT', 'use_namespaces', 'true')
    set_parameter(confFile, 'DEFAULT', 'dhcp_driver', 'neutron.agent.linux.dhcp.Dnsmasq')
    set_parameter(confFile, 'DEFAULT', 'ovs_use_veth', 'false')
    set_parameter(confFile, 'DEFAULT', 'interface_driver', 
            'neutron.agent.linux.interface.OVSInterfaceDriver')
    set_parameter(confFile, 'DEFAULT', 'dhcp_agent_manager', 
            'neutron.agent.dhcp_agent.DhcpAgentWithStateReport')

@roles('network', 'compute')
def VxLANSetOVSConf():
    "Set ovs_neutron_plugin.ini"

    # This isn't specified in the source (opencloudblog), but the file exists
    # and it seems like it should also be setup

    confFile = ovs_conf_file
    backupConfFile(confFile)

    # set_parameter(confFile, 'ovs', 'bridge_mappings', 'external:br-vlan')
    # set_parameter(confFile, 'ovs', 'tenant_network_type', 'vlan')
    # set_parameter(confFile, 'ovs', 'network_vlan_ranges', networkVlanRanges)
        

    set_parameter(confFile, 'ovs', 'tenant_network_types', 'vlan,gre,vxlan')
    set_parameter(confFile, 'ovs', 'network_vlan_ranges', networkVlanRanges)
    set_parameter(confFile, 'ovs', 'tenant_network_type', 'vxlan')
    set_parameter(confFile, 'ovs', 'enable_tunneling' , 'True')
    set_parameter(confFile, 'ovs', 'tunnel_type', 'vxlan')
    set_parameter(confFile, 'ovs', 'tunnel_id_ranges' , vniRanges)
    set_parameter(confFile, 'agent', 'tunnel_types' , 'vxlan')

@roles('controller')
def setUpVxLAN():

    execute(VxLANBasicSetup)
    execute(VxLANSetNeutronConf)
    execute(VxLANSetMl2Conf)
    execute(VxLANSetL3Conf)
    # metadata agent is already set up correctly
    execute(VxLANSetDHCPConf)
    execute(VxLANSetOVSConf)

    # The reference (opencloudblog) mentions a certain 'nova-metadata.conf', but this file 
    # doesn't seem to exist in our installation. Maybe a legacy networking thing?

    msg = 'Restart neutron server'
    runCheck(msg, 'systemctl restart neutron-server.service')

######################## InitialVlans : Cloud Administrator Guide ###################

# This set up is based on the OpenvSwitch setup in the official Cloud Administrator
# Guide

# Reference: http://docs.openstack.org/admin-guide-cloud/content/under_the_hood_openvswitch.html

@roles('network', 'compute')
def cloud_setConfFile():

    confFile = ovs_conf_file

    set_parameter(confFile, 'ovs', 'tenant_network_type', 'vlan')
    set_parameter(confFile, 'ovs', 'network_vlan_ranges', 'physnet1,physnet2:6:2131')
    set_parameter(confFile, 'ovs', 'integration_bridge', 'br-int')
    set_parameter(confFile, 'ovs', 'bridge_mappings', 'physnet2:br-ex')
    # this is a shot in the dark:
    set_parameter(confFile, 'ovs', 'bridge_mappings', 'physnet1:br-tun')

@roles('controller')
def cloud_createNets():

    with prefix(credentials):

        msg = 'Create router01'
        runCheck(msg, 'neutron router-create router01')

        msg = 'Create public network'
        runCheck(msg, 'neutron net-create public01 '
                '--provider:network_type flat '
                '--provider:physical_network physnet1 '
                '--router:external True ')

        msg = 'Create subnet on the public network'
        runCheck(msg, 'neutron subnet-create --name public01_subnet01 '
                '--disable-dhcp '
                # what's up with this CIDR?
                'public01 10.64.201.0/24 ')

        msg = 'Set router as gateway of public network'
        runCheck(msg, 'neutron router-gateway-set router01 public01')

        for tag in vlans.keys():
            netName = 'net' + str(tag)

            msg = 'Create VLAN ' + netName
            runCheck(msg, 'neutron net-create %s '
                    '--provider:network_type vlan '
                    '--provider:physical_network physnet2 '
                    '--provider:segmentation_id %d '
                    % (netName, tag))

            msg = 'Create subnet for ' + netName
            runCheck(msg, 'neutron subnet-create --name %s_subnet01 %s %s' 
                    % (netName, netName, vlan[tag]))

            msg = 'Add VLAN to router'
            runCheck(msg, 'neutron router-interface-add router01 %s_subnet01' % netName)

def cloud_deploy():
    execute(cloud_setConfFile)
    execute(cloud_createNets)


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

# @roles('controller')
# def VLAN_createExtNet():
#     "Make an external network where the VLAN subnets will reside"

#     with prefix(credentials):

#         netName = 'vlan-ext'
#         msg = 'Create net ' + netName
#         runCheck(msg, 'neutron net-create %s ' % netName + \
#                 '--router:external True '
#                 '--provider:physical_network external '
#                 '--provider:network_type flat'
#                 )
    
@roles('controller')
def VLAN_createNets():
    "Create Neutron networks for each VLAN"

    with prefix(credentials):

        for tag in vlans.keys():
            netName = 'vlan' + str(tag)
            msg = 'Create net ' + netName
            runCheck(msg, 'neutron net-create %s ' % netName + \
                    '--router:external True '
                    '--provider:physical_network external '
                    '--provider:network_type vlan '
                    '--provider:segmentation_id %s ' % tag
                    # '--provider:network_type gre'
                    )

@roles('controller')
def VLAN_createSubnets():
    "Create Neutron subnets for each VLAN"

    with prefix(credentials):

        for tag in vlans.keys():
            netName = 'vlan' + str(tag)
            # netName = 'vlan-ext'
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

    # netName = 'vlan-ext'
    # with prefix(credentials):
    #     netid = run("neutron net-list | awk '/%s/ {print $2}'" % netName)
        # for tag in vlans.keys():
        #     for number in range(instancesPerVLAN):
        #         instName = 'testvlan-%d-%d' % (tag, number)
        #         msg = 'Create instance ' + instName
        #         runCheck(msg, 'nova boot --flavor m1.tiny --image cirros-test '
        #                 '--security-group default --nic net-id=%s %s' % (netid, instName))


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
                runCheck(msg, 'nova boot --flavor m1.tiny --image cirros-test '
                        '--security-group default --nic net-id=%s %s' % (netid, instName))

@roles('controller')
def createVLANs():

    execute(VLAN_createTenant)
    execute(VLAN_createNets)
    # execute(VLAN_createExtNet)
    execute(VLAN_createSubnets)
    execute(VLAN_createTestInstances)

#################################### Deployment ######################################


def testDeploy():
    execute(setUpVxLAN)
    execute(createVLANs)

def deploy():
    pass

#################################### Undeployment ######################################

@roles('network', 'compute')
def deleteBridges():
    msg = 'Delete port from br-int to br-vlan'
    runCheck(msg, 'ovs-vsctl del-port int-to-vlan')

    for br in ['br-uplink','br-vlan']:
        msg = 'Delete bridge ' + br
        runCheck(msg, 'ovs-vsctl del-br ' + br)

@roles('network', 'compute')
def restoreBackups(confs = confFiles):

    # The function accepts a string or a list of strings
    if type(confs) == str:
        confs = [confs]

    for conf in confs:

        backup = conf + '.bak'

        command = "if [ -e %s ]; then " % backup
        command += "rm %s; " % conf
        command += "mv %s %s; " % (backup, conf)
        command += "else echo No backup file; "
        command += "fi"

        msg = 'Restore backup for ' + conf
        runCheck(msg, command)

@roles('controller')
def removeAllInstances():

    with prefix(credentials):

        deletionCommand = "for id in $(%s | tail -n +4 | head -n -1 | awk '{print $2}'); do " + \
                "%s $id; " + \
                "done"

        msg = 'Remove all instances'
        runCheck(msg, deletionCommand % ('nova list', 'nova delete'))
        # time.sleep(3)

        msg = 'Remove all subnets'
        runCheck(msg, deletionCommand % ('neutron subnet-list', 'neutron subnet-delete'))
        # time.sleep(3)

        msg = 'Remove all nets'
        runCheck(msg, deletionCommand % ('neutron net-list', 'neutron net-delete'))
        # time.sleep(3)

        msg = 'Remove all routers'
        runCheck(msg, deletionCommand % ('neutron router-list', 'neutron router-delete'))
        # time.sleep(3)

@roles('controller')
def undeploy():
    execute(deleteBridges)
    execute(restoreBackups)
    execute(removeAllInstances)

####################################### TDD ##########################################

@roles('controller')
def test():
    pass

def tdd():
    pass
