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
sys.path.append('..')
import env_config
from env_config import log_debug, log_info, log_error, run_log, sudo_log
from myLib import *


############################ Config ########################################

env.roledefs = env_config.roledefs

# define local config file locations
database_script_file = 'config_files/database_creation.sql'
admin_openrc = '../global_config_files/admin-openrc.sh'
global_config = '../global_config_files/global_config'

# define host config file locations
neutron_conf = '/etc/neutron/neutron.conf'

# get passwords from their config file
passwd = env_config.passwd

# get database script
database_script = env_config.databaseScript.replace("NEUTRON_DBPASS",passwd["NEUTRON_DBPASS"])

# Logging
log_file = 'neutron_deployment.log'
env_config.setupLoggingInFabfile(log_file)


################### Deployment ########################################

# CONTROLLER

def create_neutron_database():

    # read script, removing comments
    # database_script = "".join( [line for line in open(database_script_file,'r').readlines() \
    #         if line[0:2] != '--'] )
    # database_script = local("grep -v '^--' {}".format(database_script_file))
    
    # send the commands to mysql client
    sudo_log('''echo "{}" | mysql -u root'''.format(database_script))

    # get the admin-openrc script to obtain access to admin-only CLI commands
    exports = open(admin_openrc,'r').read()
    with prefix(exports):

        # check if user neutron has been created and if not, create it
        if 'neutron' not in sudo_log("keystone user-list"):
            # create the neutron user in keystone
            sudo('keystone user-create --name neutron --pass {}'.format(passwd['NEUTRON_PASS']),quiet=True)
            # add the admin role to the neutron user
            sudo_log('keystone user-role-add --user neutron --tenant service --role admin')
        else:
            log_debug('neutron is already a user. Do nothing')

        # check if service neutron has been created and if not, create it
        if 'neutron' not in sudo_log("keystone service-list"):
            # create the neutron service entity
            sudo_log('keystone service-create --name neutron --type network --description "OpenStack Networking"')
        else:
            log_debug('neutron is already a service. Do nothing')

        # check if a 9696 endpoint already exists and if not, create one
        if '9696' not in sudo_log("keystone endpoint-list"):
            # create the networking service API endpoints
            sudo_log('keystone endpoint-create ' + \
                    "--service-id $(keystone service-list | awk '/ network / {print $2}') " + \
                    "--publicurl http://controller:9696 " + \
                    "--adminurl http://controller:9696 " + \
                    "--internalurl http://controller:9696 " + \
                    "--region regionOne")
        else:
            log_debug('9696 is already an endpoint. Do nothing')

def configure_networking_server_component():
    # configure neutron.conf with crudini
    # crudini --set config_file section parameter value

    neutron_conf = '/etc/neutron/neutron.conf'
    
    # make a backup
    sudo_log('cp {} {}.back12'.format(neutron_conf,neutron_conf))

    # configure database access
    parameter = 'mysql://neutron:{}@controller/neutron'.format(passwd['NEUTRON_DBPASS'])
    sudo_log('crudini --set {} database connection {}'.format(neutron_conf,parameter))

    # configure RabbitMQ access
    sudo_log('crudini --set {} DEFAULT rpc_backend rabbit'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT rabbit_host controller'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT rabbit_password {}'.format(neutron_conf,passwd['RABBIT_PASS']),quiet=True)

    # configure Identity service access

    sudo_log('crudini --set {} DEFAULT auth_strategy keystone'.format(neutron_conf))
    sudo_log('crudini --set {} keystone_authtoken auth_uri http://controller:5000/v2.0'.format(neutron_conf))
    sudo_log('crudini --set {} keystone_authtoken identity_uri http://controller:35357'.format(neutron_conf))
    sudo_log('crudini --set {} keystone_authtoken admin_tenant_name service'.format(neutron_conf))
    sudo_log('crudini --set {} keystone_authtoken admin_user neutron'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_password {}'.format(neutron_conf,passwd['NEUTRON_PASS']),quiet=True)

    # enable ML2 plugin

    sudo_log('crudini --set {} DEFAULT core_plugin ml2'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT service_plugins router'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT allow_overlapping_ips True'.format(neutron_conf))

    # set Neutron to notify Nova of of topology changes
    # get service tenant id
    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        nova_admin_tenant_id = sudo_log('keystone tenant-list | grep service | cut -d\| -f2')

    if nova_admin_tenant_id:
        # if tenant service doesn't exist, this variable will be empty
        sudo_log('crudini --set {} DEFAULT nova_admin_tenant_id {}'.format(neutron_conf, nova_admin_tenant_id))


    sudo_log('crudini --set {} DEFAULT notify_nova_on_port_status_changes True'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT notify_nova_on_port_data_changes True'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT nova_url http://controller:8774/v2'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT nova_admin_auth_url http://controller:35357/v2.0'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT nova_region_name regionOne'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT nova_admin_username nova'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_admin_password {}'.format(neutron_conf,passwd['NOVA_PASS']),quiet=True)

    # turn on verbose logging
    sudo_log('crudini --set {} DEFAULT verbose True'.format(neutron_conf))

def configure_ML2_plugin_general():
    # The ML2 plug-in uses the Open vSwitch (OVS) mechanism (agent) to build the virtual 
    # networking framework for instances. However, the controller node does not need the OVS 
    # components because it does not handle instance network traffic.

    ml2_conf_file = '/etc/neutron/plugins/ml2/ml2_conf.ini'

    sudo_log('crudini --set ' + ml2_conf_file + ' ml2 type_drivers flat,gre')
    sudo_log('crudini --set ' + ml2_conf_file + ' ml2 tenant_network_types gre')
    sudo_log('crudini --set ' + ml2_conf_file + ' ml2 mechanism_drivers openvswitch')

    sudo_log('crudini --set ' + ml2_conf_file + ' ml2_type_gre tunnel_id_ranges 1:1000')

    sudo_log('crudini --set ' + ml2_conf_file + ' securitygroup enable_security_group True')
    sudo_log('crudini --set ' + ml2_conf_file + ' securitygroup enable_ipset True')
    sudo_log('crudini --set ' + ml2_conf_file + ' securitygroup firewall_driver' + \
            ' neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver')


def configure_nova_to_use_neutron():

    nova_conf = '/etc/nova/nova.conf'

    sudo_log('crudini --set ' + nova_conf + ' DEFAULT network_api_class nova.network.neutronv2.api.API')
    sudo_log('crudini --set ' + nova_conf + ' DEFAULT security_group_api neutron')
    sudo_log('crudini --set ' + nova_conf + ' DEFAULT linuxnet_interface_driver nova.network.linux_net.LinuxOVSInterfaceDriver')
    sudo_log('crudini --set ' + nova_conf + ' DEFAULT firewall_driver nova.virt.firewall.NoopFirewallDriver')

    sudo_log('crudini --set ' + nova_conf + ' neutron url http://controller:9696')
    sudo_log('crudini --set ' + nova_conf + ' neutron auth_strategy keystone')
    sudo_log('crudini --set ' + nova_conf + ' neutron admin_auth_url http://controller:35357/v2.0')
    sudo_log('crudini --set ' + nova_conf + ' neutron admin_tenant_name service')
    sudo_log('crudini --set ' + nova_conf + ' neutron admin_username neutron')
    sudo('crudini --set ' + nova_conf + ' neutron admin_password ' + passwd['NEUTRON_PASS'],quiet=True)

@roles('controller')
def controller_deploy():
    
    create_neutron_database()

    # install the networking components of openstack
    sudo_log('yum -y install openstack-neutron openstack-neutron-ml2 python-neutronclient which')

    configure_networking_server_component()

    configure_ML2_plugin_general()

    configure_nova_to_use_neutron()

    # The Networking service initialization scripts expect a symbolic link /etc/neutron/plugin.ini 
    # pointing to the ML2 plug-in configuration file, /etc/neutron/plugins/ml2/ml2_conf.ini. 
    # If this symbolic link does not exist, create it
    if 'plugin.ini' not in sudo_log('ls /etc/neutron'):
        sudo_log('ln -s /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini')

    # Populate the database
    sudo_log('su -s /bin/sh -c "neutron-db-manage --config-file /etc/neutron/neutron.conf ' + \
              '--config-file /etc/neutron/plugins/ml2/ml2_conf.ini upgrade juno" neutron')

    # Restart nova
    sudo_log('systemctl restart openstack-nova-api.service openstack-nova-scheduler.service' + \
              ' openstack-nova-conductor.service')

    # Start neutron
    sudo_log('systemctl enable neutron-server.service')
    sudo_log('systemctl start neutron-server.service')
    

# NETWORK

def configure_the_Networking_common_components():

    # make a backup
    sudo_log('cp {} {}.back12'.format(neutron_conf,neutron_conf))

    # configure RabbitMQ access
    sudo_log('crudini --set {} DEFAULT rpc_backend rabbit'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT rabbit_host controller'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT rabbit_password {}'.format(neutron_conf,passwd['RABBIT_PASS']),quiet=True)

    # configure Identity service access

    sudo_log('crudini --set {} DEFAULT auth_strategy keystone'.format(neutron_conf))
    sudo_log('crudini --set {} keystone_authtoken auth_uri http://controller:5000/v2.0'.format(neutron_conf))
    sudo_log('crudini --set {} keystone_authtoken identity_uri http://controller:35357'.format(neutron_conf))
    sudo_log('crudini --set {} keystone_authtoken admin_tenant_name service'.format(neutron_conf))
    sudo_log('crudini --set {} keystone_authtoken admin_user neutron'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_password {}'.format(neutron_conf,passwd['NEUTRON_PASS']),quiet=True)

    # enable ML2 plugin

    sudo_log('crudini --set {} DEFAULT core_plugin ml2'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT service_plugins router'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT allow_overlapping_ips True'.format(neutron_conf))
    sudo_log('crudini --set {} DEFAULT verbose True'.format(neutron_conf))

def configure_ML2_plug_in_network():
    
    ml2_conf_file = '/etc/neutron/plugins/ml2/ml2_conf.ini'

    # most of the configuration is the same as the controller
    configure_ML2_plugin_general()

    # configure the external flat provider network 
    sudo_log('crudini --set ' + ml2_conf_file + ' ml2_type_flat flat_networks external')

    # configure the external flat provider network 
    sudo_log('crudini --set ' + ml2_conf_file + ' ovs enable_tunneling True')
    sudo_log('crudini --set ' + ml2_conf_file + ' ovs bridge_mappings external:br-ex')
    local_ip = env_config.networkTunnels['IPADDR']
    sudo_log('crudini --set ' + ml2_conf_file + ' ovs local_ip ' + local_ip)

    # enable GRE tunnels 
    sudo_log('crudini --set ' + ml2_conf_file + ' agent tunnel_types gre')

def configure_Layer3_agent():

    l3_agent_file = '/etc/neutron/l3_agent.ini'

    sudo_log("crudini --set {} DEFAULT interface_driver neutron.agent.linux.interface.OVSInterfaceDriver".format(l3_agent_file))
    sudo_log("crudini --set {} DEFAULT use_namespaces True".format(l3_agent_file))
    sudo_log("crudini --set {} DEFAULT external_network_bridge br-ex".format(l3_agent_file))
    sudo_log("crudini --set {} DEFAULT router_delete_namespaces True".format(l3_agent_file))
    sudo_log("crudini --set {} DEFAULT verbose True".format(l3_agent_file))

def configure_DHCP_agent():

    dhcp_agent_file = '/etc/neutron/dhcp_agent.ini' 

    sudo_log("crudini --set {} DEFAULT interface_driver neutron.agent.linux.interface.OVSInterfaceDriver".format(dhcp_agent_file))
    sudo_log("crudini --set {} DEFAULT dhcp_driver neutron.agent.linux.dhcp.Dnsmasq".format(dhcp_agent_file))
    sudo_log("crudini --set {} DEFAULT use_namespaces True".format(dhcp_agent_file))
    sudo_log("crudini --set {} DEFAULT dhcp_delete_namespaces True".format(dhcp_agent_file))
    sudo_log("crudini --set {} DEFAULT verbose True".format(dhcp_agent_file))

@roles('controller')
def configure_metadata_proxy_on_controller():
    # to configure the metadata agent, some changes need to be made
    # on the controller node

    conf = '/etc/nova/nova.conf'

    sudo_log("crudini --set {} service_metadata_proxy True".format(conf))
    sudo_log("crudini --set {} metadata_proxy_shared_secret {}".format(conf,passwd['METADATA_SECRET']))

    sudo_log("systemctl restart openstack-nova-api.service")


def configure_metadata_agent():

    metadata_agent_file = '/etc/neutron/metadata_agent.ini'

    sudo_log("crudini --set {} DEFAULT auth_url http://controller:5000/v2.0".format(metadata_agent_file))
    sudo_log("crudini --set {} DEFAULT auth_region regionOne".format(metadata_agent_file))
    sudo_log("crudini --set {} DEFAULT admin_tenant_name service".format(metadata_agent_file))
    sudo_log("crudini --set {} DEFAULT admin_user neutron".format(metadata_agent_file))
    sudo_log("crudini --set {} DEFAULT nova_metadata_ip controller".format(metadata_agent_file))
    sudo_log("crudini --set {} DEFAULT admin_password {}".format(metadata_agent_file,passwd['NEUTRON_PASS']))
    sudo_log("crudini --set {} DEFAULT metadata_proxy_shared_secret {}".format(metadata_agent_file,passwd['METADATA_SECRET']))
    sudo_log("crudini --set {} DEFAULT verbose True".format(metadata_agent_file))

    execute(configure_metadata_proxy_on_controller)

def configure_Open_vSwitch_service():

    sudo_log("systemctl enable openvswitch.service")
    sudo_log("systemctl start openvswitch.service")

    # for testing
    # sudo_log("ovs-vsctl del-br br-ex")

    # add br-ex bridge
    if 'br-ex' not in sudo_log("ovs-vsctl list-br"):
        sudo_log("ovs-vsctl add-br br-ex")

        interface_name = env_config.networkExternal['DEVICE']
        sudo_log("ovs-vsctl --log-file=/home/uadm/ovslog add-port br-ex '{}'".format(interface_name))

    


@roles('network')
def network_deploy():
    
    # edit sysctl.conf
    sysctl_conf = '/etc/sysctl.conf'

    sudo_log("crudini --set  {} '' net.ipv4.ip_forward 1".format(sysctl_conf))
    sudo_log("crudini --set  {} '' net.ipv4.conf.all.rp_filter 0".format(sysctl_conf))
    sudo_log("crudini --set  {} '' net.ipv4.conf.default.rp_filter 0".format(sysctl_conf))

    sudo_log("sysctl -p")

    # install networking components
    sudo_log("yum -y install openstack-neutron openstack-neutron-ml2 openstack-neutron-openvswitch")

    # configuration 

    configure_the_Networking_common_components()

    configure_ML2_plug_in_network()

    configure_Layer3_agent()

    configure_DHCP_agent()

    configure_metadata_agent()

    configure_Open_vSwitch_service()

    # finalize installation

    # The Networking service initialization scripts expect a symbolic link /etc/neutron/plugin.ini 
    # pointing to the ML2 plug-in configuration file, /etc/neutron/plugins/ml2/ml2_conf.ini. 
    # If this symbolic link does not exist, create it
    if 'plugin.ini' not in sudo_log('ls /etc/neutron'):
        sudo_log('ln -s /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini')

    # Due to a packaging bug, the Open vSwitch agent initialization script explicitly looks for 
    # the Open vSwitch plug-in configuration file rather than a symbolic link /etc/neutron/plugin.ini pointing to the ML2 
    # plug-in configuration file. Run the following commands to resolve this issue:
    sudo_log("cp /usr/lib/systemd/system/neutron-openvswitch-agent.service " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service.orig")
    sudo_log("sed -i 's,plugins/openvswitch/ovs_neutron_plugin.ini,plugin.ini,g' " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service")

    # initialize services
    sudo_log("systemctl enable neutron-openvswitch-agent.service neutron-l3-agent.service " +  \
              "neutron-dhcp-agent.service neutron-metadata-agent.service " + \
                "neutron-ovs-cleanup.service")
    sudo_log("systemctl start neutron-openvswitch-agent.service neutron-l3-agent.service " + \
              "neutron-dhcp-agent.service neutron-metadata-agent.service")


# COMPUTE

def configure_ML2_plug_in_compute():
    
    ml2_conf_file = '/etc/neutron/plugins/ml2/ml2_conf.ini'

    # most of the configuration is the same as the controller
    configure_ML2_plugin_general()

    # configure the external flat provider network 
    sudo_log('crudini --set ' + ml2_conf_file + ' ovs enable_tunneling True')
    local_ip = env_config.computeTunnels['IPADDR']
    sudo_log('crudini --set ' + ml2_conf_file + ' ovs local_ip ' + local_ip)

    # enable GRE tunnels 
    sudo_log('crudini --set ' + ml2_conf_file + ' agent tunnel_types gre')

@roles('compute')
def compute_deploy():
    
    # edit sysctl.conf
    sysctl_conf = '/etc/sysctl.conf'

    sudo_log("crudini --set  {} '' net.ipv4.conf.all.rp_filter 0".format(sysctl_conf))
    sudo_log("crudini --set  {} '' net.ipv4.conf.default.rp_filter 0".format(sysctl_conf))

    sudo_log("sysctl -p")

    # install networking components
    sudo_log("yum -y install openstack-neutron-ml2 openstack-neutron-openvswitch")

    # configuration

    configure_the_Networking_common_components() # same as networking

    configure_ML2_plug_in_compute()

    configure_nova_to_use_neutron()

    # enable Open vSwitch
    sudo_log('systemctl enable openvswitch.service')
    sudo_log('systemctl start openvswitch.service')

    # finalize installation

    # The Networking service initialization scripts expect a symbolic link /etc/neutron/plugin.ini 
    # pointing to the ML2 plug-in configuration file, /etc/neutron/plugins/ml2/ml2_conf.ini. 
    # If this symbolic link does not exist, create it
    if 'plugin.ini' not in sudo_log('ls /etc/neutron'):
        sudo_log('ln -s /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini')

    # Due to a packaging bug, the Open vSwitch agent initialization script explicitly looks for 
    # the Open vSwitch plug-in configuration file rather than a symbolic link /etc/neutron/plugin.ini pointing to the ML2 
    # plug-in configuration file. Run the following commands to resolve this issue:
    sudo_log("cp /usr/lib/systemd/system/neutron-openvswitch-agent.service " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service.orig")
    sudo_log("sed -i 's,plugins/openvswitch/ovs_neutron_plugin.ini,plugin.ini,g' " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service")

    # restart Nova service
    # sudo_log("systemctl restart openstack-nova-compute.service")

    # start Open vSwitch
    sudo_log("systemctl enable neutron-openvswitch-agent.service")
    sudo_log("systemctl start neutron-openvswitch-agent.service")

# INITIAL NETWORK

def createExternalNetwork():
    if 'ext-net' in run('neutron --debug net-list'):
        msg = 'Ext-net already created'
        printMessage('good',msg)
    else:
        msg = 'create external network on network node'
        runCheck(msg,'neutron net-create ext-net --router:external True '+\
                '--provider:physical_network external --provider:network_type flat')

def createInitialSubnet():

    # fix this IP scheme
    floatingIPStart = '192.168.122.50'
    floatingIPEnd = '192.168.122.100'
    ExternalNetworkGateway = '192.168.122.1'
    ExternalNetworkCIDR = '192.168.122.0/24'

    if 'ext-subnet' in run('neutron subnet-list'):
        msg = 'ext-net already created'
        printMessage('good',msg)
    else:
        msg = 'create initial subnet on external net on network node'
        runCheck(msg,'neutron subnet-create ext-net --name ext-subnet --allocation-pool start={},end={} --disable-dhcp --gateway {} {}'\
                  .format(floatingIPStart,floatingIPEnd,ExternalNetworkGateway,ExternalNetworkCIDR))

def createDemoTenantNetwork():
    gateway = '10.0.0.1'
    cidr = '10.0.0.0/8'


    if 'demo-net' in run('neutron net-list'):
        msg = 'Demo-net already created'
        printMessage('good',msg)
    else:
        msg = 'create initial demo tenant network on network node'
        runCheck(msg, 'neutron net-create demo-net')

    if 'demo-subnet' in run('neutron subnet-list'):
        msg = 'Demo-subnet already created'
        printMessage('good',msg)
    else:
        msg = 'create subnet on demo-net'
        runCheck(msg,'neutron subnet-create demo-net --name demo-subnet --gateway {} {}'.format(gateway,cidr))

def createSetupRouter():
    if 'demo-router' in run('neutron router-list'):
        msg = 'Demo-router already created'
        printMessage('good',msg)
    else:
        msg = 'create the demo router'
        runCheck(msg,'neutron router-create demo-router')

        msg = 'attach the demo router to the demo subnet'
        runCheck(msg,'neutron router-interface-add demo-router demo-subnet')

        msg = 'attach the router to the external network by setting it as the gateway'
        runCheck(msg,'neutron router-gateway-set demo-router ext-net')


@roles('network')
def createInitialNetwork():
    # Creates a sample network for testing 

    # get admin credentials
    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        createExternalNetwork()
        createInitialSubnet()
        createDemoTenantNetwork()
        createSetupRouter()





def deploy():

    log_debug('Beginning deployment')
    
    # with settings(warn_only=True):
    execute(controller_deploy)
    execute(network_deploy)
    execute(compute_deploy)

######################################## TDD #########################################

@roles('controller')
def controller_tdd():

    # Check loaded extensions to verify launch of neutron
    alias_name_pairs = list()
    alias_name_pairs.append(('security-group','security-group'))
    alias_name_pairs.append(('l3_agent_scheduler','L3 Agent Scheduler'))
    alias_name_pairs.append(('ext-gw-mode','Neutron L3 Configurable external gateway mode'))
    alias_name_pairs.append(('binding','Port Binding'))
    alias_name_pairs.append(('provider','Provider Network'))
    alias_name_pairs.append(('agent','agent'))
    alias_name_pairs.append(('quotas','Quota management support'))
    alias_name_pairs.append(('dhcp_agent_scheduler','DHCP Agent Scheduler'))
    alias_name_pairs.append(('l3-ha','HA Router extension'))
    alias_name_pairs.append(('multi-provider','Multi Provider Network'))
    alias_name_pairs.append(('external-net','Neutron external network'))
    alias_name_pairs.append(('router','Neutron L3 Router'))
    alias_name_pairs.append(('allowed-address-pairs','Allowed Address Pairs'))
    alias_name_pairs.append(('extraroute','Neutron Extra Route'))
    alias_name_pairs.append(('extra_dhcp_opt','Neutron Extra DHCP opts'))
    alias_name_pairs.append(('dvr','Distributed Virtual Router'))

    print 'Checking loaded extensions'
    
    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        for pair in alias_name_pairs:
            alias = pair[0]
            name = sudo_log('neutron ext-list | grep {} | cut -d\| -f3'.format(alias))
            if pair[1] not in name:
                print red("Problem with alias {}: should be {}, is {}".format(alias,pair[1],name.strip()))
            else:
                print green("alias {} is {}, as expected".format(alias,name.strip()))

@roles('controller')
def verify_neutron_agents_network():

    # this test should be done after the network deployment,
    # even though it's done on the controller node

    # verify successful launch of the neutron agents

    neutron_agents = ['Metadata agent','Open vSwitch agent','L3 agent','DHCP agent']

    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        # grab the agent list as a list of lines, skipping header
        agent_list = sudo_log("neutron agent-list").splitlines()[3:]

        for agent in neutron_agents:
            agent_line = [line for line in agent_list if agent in line]
            if not agent_line:
                print red("Neutron agent {} not found in agent-list".format(agent))
            else:
                agent_line = agent_line[0]
                # change the hostname to 'network' when doing it for real
                hostname = '524564.ece.ualberta.ca'
                if hostname not in agent_line or ':-)' not in agent_line:
                    print red("Problem with agent {}".format(agent))
                    get_line = "neutron agent-list | grep '{}' ".format(agent)
                    print red(sudo_log(get_line))
                else:
                    print green("Neutron agent {} OK!".format(agent))


@roles('network')
def network_tdd():
    execute(verify_neutron_agents_network)

@roles('controller')
def verify_neutron_agents_compute():

    # this test should be done after the compute deployment,
    # even though it's done on the controller node

    # verify successful launch of the compute agents

    # get list of compute nodes from the hosts config
    list_of_compute_hostnames = [hostname for hostname in env_config.hosts.values()\
            if 'compute' in hostname]

    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        # grab the agent list as a list of lines, skipping header
        agent_list = sudo_log("neutron agent-list").splitlines()[3:]

        for agent in list_of_compute_hostnames:
            agent = '529569.ece.ualberta.ca' # remove this when it's a real deployment
            agent_line = [line for line in agent_list if agent in line]
            if not agent_line:
                print red("Neutron agent {} not found in agent-list".format(agent))
            else:
                agent_line = agent_line[0]
                if ':-)' not in agent_line:
                    print red("Problem with agent {}".format(agent))
                    get_line = "neutron agent-list | grep '{}' ".format(agent)
                    print red(sudo_log(get_line))
                else:
                    print green("Neutron agent {} OK!".format(agent))

@roles('compute')
def compute_tdd():
    execute(verify_neutron_agents_compute)

def tdd():
    with settings(warn_only=True):
        execute(controller_tdd)


