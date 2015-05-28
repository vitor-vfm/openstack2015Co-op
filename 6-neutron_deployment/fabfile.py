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
database_script_file = 'config_files/database_creation.sql'
admin_openrc = '../global_config_files/admin-openrc.sh'
global_config = '../global_config_files/global_config'

# define host config file locations
neutron_conf = '/etc/neutron/neutron.conf'

# get passwords from their config file
passwd = dict()
passwd['RABBIT_PASS'] = local('crudini --get {} rabbitmq RABBIT_PASS'.format(global_config),capture=True)
passwd['NOVA_PASS'] = local('crudini --get {} keystone NOVA_PASS'.format(global_config),capture=True)
passwd['NEUTRON_PASS'] = local('crudini --get {} keystone NEUTRON_PASS'.format(global_config),capture=True)
passwd['NEUTRON_DBPASS'] = local('crudini --get {} mysql NEUTRON_DBPASS'.format(global_config),capture=True)
passwd['METADATA_SECRET'] = local('crudini --get {} metadata METADATA_SECRET'.format(global_config),capture=True)

################### General functions ########################################


################### Deployment ########################################

# CONTROLLER

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
            sudo('keystone user-create --name neutron --pass {}'.format(passwd['NEUTRON_PASS']),quiet=True)
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
    # crudini --set config_file section parameter value

    neutron_conf = '/etc/neutron/neutron.conf'
    
    # make a backup
    sudo('cp {} {}.back12'.format(neutron_conf,neutron_conf))

    # configure database access
    parameter = 'mysql://neutron:{}@controller/neutron'.format(passwd['NEUTRON_DBPASS'])
    sudo('crudini --set {} database connection {}'.format(neutron_conf,parameter))

    # configure RabbitMQ access
    sudo('crudini --set {} DEFAULT rpc_backend rabbit'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT rabbit_host controller'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT rabbit_password {}'.format(neutron_conf,passwd['RABBIT_PASS']),quiet=True)

    # configure Identity service access

    sudo('crudini --set {} DEFAULT auth_strategy keystone'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken auth_uri http://controller:5000/v2.0'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken identity_uri http://controller:35357'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_tenant_name service'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_user neutron'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_password {}'.format(neutron_conf,passwd['NEUTRON_PASS']),quiet=True)

    # enable ML2 plugin

    sudo('crudini --set {} DEFAULT core_plugin ml2'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT service_plugins router'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT allow_overlapping_ips True'.format(neutron_conf))

    # set Neutron to notify Nova of of topology changes
    # get service tenant id
    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        nova_admin_tenant_id = sudo('keystone tenant-list | grep service | cut -d\| -f2')

    if nova_admin_tenant_id:
        # if tenant service doesn't exist, this variable will be empty
        sudo('crudini --set {} DEFAULT nova_admin_tenant_id {}'.format(neutron_conf, nova_admin_tenant_id))


    sudo('crudini --set {} DEFAULT notify_nova_on_port_status_changes True'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT notify_nova_on_port_data_changes True'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_url http://controller:8774/v2'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_admin_auth_url http://controller:35357/v2.0'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_region_name regionOne'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_admin_username nova'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT nova_admin_password {}'.format(neutron_conf,passwd['NOVA_PASS']),quiet=True)

    # turn on verbose logging
    sudo('crudini --set {} DEFAULT verbose True'.format(neutron_conf))

def configure_ML2_plugin():
    # The ML2 plug-in uses the Open vSwitch (OVS) mechanism (agent) to build the virtual 
    # networking framework for instances. However, the controller node does not need the OVS 
    # components because it does not handle instance network traffic.

    ml2_conf_file = '/etc/neutron/plugins/ml2/ml2_conf.ini'

    sudo('crudini --set ' + ml2_conf_file + ' ml2 type_drivers flat,gre')
    sudo('crudini --set ' + ml2_conf_file + ' ml2 tenant_network_types gre')
    sudo('crudini --set ' + ml2_conf_file + ' ml2 mechanism_drivers openvswitch')

    sudo('crudini --set ' + ml2_conf_file + ' ml2_type_gre tunnel_id_ranges 1:1000')

    sudo('crudini --set ' + ml2_conf_file + ' securitygroup enable_security_group True')
    sudo('crudini --set ' + ml2_conf_file + ' securitygroup enable_ipset True')
    sudo('crudini --set ' + ml2_conf_file + ' securitygroup firewall_driver' + \
            ' neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver')


def configure_nova_to_use_neutron():

    nova_conf = '/etc/nova/nova.conf'

    sudo('crudini --set ' + nova_conf + ' DEFAULT network_api_class nova.network.neutronv2.api.API')
    sudo('crudini --set ' + nova_conf + ' DEFAULT security_group_api neutron')
    sudo('crudini --set ' + nova_conf + ' DEFAULT linuxnet_interface_driver nova.network.linux_net.LinuxOVSInterfaceDriver')
    sudo('crudini --set ' + nova_conf + ' DEFAULT firewall_driver nova.virt.firewall.NoopFirewallDriver')

    sudo('crudini --set ' + nova_conf + ' neutron url http://controller:9696')
    sudo('crudini --set ' + nova_conf + ' neutron auth_strategy keystone')
    sudo('crudini --set ' + nova_conf + ' neutron admin_auth_url http://controller:35357/v2.0')
    sudo('crudini --set ' + nova_conf + ' neutron admin_tenant_name service')
    sudo('crudini --set ' + nova_conf + ' neutron admin_username neutron')
    sudo('crudini --set ' + nova_conf + ' neutron admin_password ' + passwd['NEUTRON_PASS'],quiet=True)

@roles('controller')
def controller_deploy():
    
    create_neutron_database()

    # install the networking components of openstack
    sudo('yum -y install openstack-neutron openstack-neutron-ml2 python-neutronclient which')

    configure_networking_server_component()

    configure_ML2_plugin()

    configure_nova_to_use_neutron()

    # The Networking service initialization scripts expect a symbolic link /etc/neutron/plugin.ini 
    # pointing to the ML2 plug-in configuration file, /etc/neutron/plugins/ml2/ml2_conf.ini. 
    # If this symbolic link does not exist, create it
    if 'plugin.ini' not in sudo('ls /etc/neutron'):
        sudo('ln -s /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini')

    # Populate the database
    sudo('su -s /bin/sh -c "neutron-db-manage --config-file /etc/neutron/neutron.conf ' + \
              '--config-file /etc/neutron/plugins/ml2/ml2_conf.ini upgrade juno" neutron')

    # Restart nova
    sudo('systemctl restart openstack-nova-api.service openstack-nova-scheduler.service' + \
              ' openstack-nova-conductor.service')

    # Start neutron
    sudo('systemctl enable neutron-server.service')
    sudo('systemctl start neutron-server.service')
    

# NETWORK

def configure_the_Networking_common_components():

    # make a backup
    sudo('cp {} {}.back12'.format(neutron_conf,neutron_conf))

    # configure RabbitMQ access
    sudo('crudini --set {} DEFAULT rpc_backend rabbit'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT rabbit_host controller'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT rabbit_password {}'.format(neutron_conf,passwd['RABBIT_PASS']),quiet=True)

    # configure Identity service access

    sudo('crudini --set {} DEFAULT auth_strategy keystone'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken auth_uri http://controller:5000/v2.0'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken identity_uri http://controller:35357'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_tenant_name service'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_user neutron'.format(neutron_conf))
    sudo('crudini --set {} keystone_authtoken admin_password {}'.format(neutron_conf,passwd['NEUTRON_PASS']),quiet=True)

    # enable ML2 plugin

    sudo('crudini --set {} DEFAULT core_plugin ml2'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT service_plugins router'.format(neutron_conf))
    sudo('crudini --set {} DEFAULT allow_overlapping_ips True'.format(neutron_conf))

def configure_the_ML2_plug_in():
    
    ml2_conf_file = '/etc/neutron/plugins/ml2/ml2_conf.ini'

    # most of the configuration is the same as the controller
    configure_ML2_plugin()

    # configure the external flat provider network 
    sudo('crudini --set ' + ml2_conf_file + ' ml2_type_flat flat_networks external')

    # configure the external flat provider network 
    sudo('crudini --set ' + ml2_conf_file + ' ovs enable_tunneling True')
    sudo('crudini --set ' + ml2_conf_file + ' ovs bridge_mappings external:br-ex')
    local_ip_file_location = '../network_deployment/config_files/network_node_instance_tunnels_interface_config'
    local_ip = local("crudini --get {} '' IPADDR".format(local_ip_file_location),capture=True)
    sudo('crudini --set ' + ml2_conf_file + ' ovs local_ip ' + local_ip)

    # enable GRE tunnels 
    sudo('crudini --set ' + ml2_conf_file + ' agent tunnel_types gre')

def configure_Layer3_agent():

    l3_agent_file = '/etc/neutron/l3_agent.ini'

    sudo("crudini --set {} DEFAULT interface_driver neutron.agent.linux.interface.OVSInterfaceDriver".format(l3_agent_file))
    sudo("crudini --set {} DEFAULT use_namespaces True".format(l3_agent_file))
    sudo("crudini --set {} DEFAULT external_network_bridge br-ex".format(l3_agent_file))
    sudo("crudini --set {} DEFAULT router_delete_namespaces True".format(l3_agent_file))
    sudo("crudini --set {} DEFAULT verbose True".format(l3_agent_file))

def configure_DHCP_agent():

    dhcp_agent_file = '/etc/neutron/dhcp_agent.ini' 

    sudo("crudini --set {} DEFAULT interface_driver neutron.agent.linux.interface.OVSInterfaceDriver".format(dhcp_agent_file))
    sudo("crudini --set {} DEFAULT dhcp_driver neutron.agent.linux.dhcp.Dnsmasq".format(dhcp_agent_file))
    sudo("crudini --set {} DEFAULT use_namespaces True".format(dhcp_agent_file))
    sudo("crudini --set {} DEFAULT dhcp_delete_namespaces True".format(dhcp_agent_file))
    sudo("crudini --set {} DEFAULT verbose True".format(dhcp_agent_file))

@roles('controller')
def configure_metadata_proxy_on_controller():
    # to configure the metadata agent, some changes need to be made
    # on the controller node

    conf = '/etc/nova/nova.conf'

    sudo("crudini --set {} service_metadata_proxy True".format(conf))
    sudo("crudini --set {} metadata_proxy_shared_secret {}".format(conf,passwd['METADATA_SECRET']))

    sudo("systemctl restart openstack-nova-api.service")


def configure_metadata_agent():

    metadata_agent_file = '/etc/neutron/metadata_agent.ini'

    sudo("crudini --set {} DEFAULT auth_url http://controller:5000/v2.0".format(metadata_agent_file))
    sudo("crudini --set {} DEFAULT auth_region regionOne".format(metadata_agent_file))
    sudo("crudini --set {} DEFAULT admin_tenant_name service".format(metadata_agent_file))
    sudo("crudini --set {} DEFAULT admin_user neutron".format(metadata_agent_file))
    sudo("crudini --set {} DEFAULT nova_metadata_ip controller".format(metadata_agent_file))
    sudo("crudini --set {} DEFAULT admin_password {}".format(metadata_agent_file,passwd['NEUTRON_PASS']))
    sudo("crudini --set {} DEFAULT metadata_proxy_shared_secret {}".format(metadata_agent_file,passwd['METADATA_SECRET']))
    sudo("crudini --set {} DEFAULT verbose True".format(metadata_agent_file))

    execute(configure_metadata_proxy_on_controller)

def configure_Open_vSwitch_service():

    sudo("systemctl enable openvswitch.service")
    sudo("systemctl start openvswitch.service")

    # for testing
    sudo("ovs-vsctl del-br br-ex")

    # add br-ex bridge
    if 'br-ex' not in sudo("ovs-vsctl list-br"):
        sudo("ovs-vsctl add-br br-ex")

        interface_config_file = "../network_deployment/config_files/network_node_external_interface_config"
        interface_name = local("crudini --get {} '' DEVICE".format(interface_config_file),capture=True)
        sudo("ovs-vsctl --log-file=/home/uadm/ovslog add-port br-ex '{}'".format(interface_name))

    


@roles('network')
def network_deploy():
    # edit sysctl.conf
    sysctl_conf = '/etc/sysctl.conf'

    sudo("crudini --set  {} '' net.ipv4.ip_forward 1".format(sysctl_conf))
    sudo("crudini --set  {} '' net.ipv4.conf.all.rp_filter 0".format(sysctl_conf))
    sudo("crudini --set  {} '' net.ipv4.conf.default.rp_filter 0".format(sysctl_conf))

    sudo("sysctl -p")

    # install networking components
    sudo("yum -y install openstack-neutron openstack-neutron-ml2 openstack-neutron-openvswitch")

    # configuration 

    configure_the_Networking_common_components()

    configure_the_ML2_plug_in()

    configure_Layer3_agent()

    configure_DHCP_agent()

    configure_metadata_agent()

    # configure_Open_vSwitch_service()

    # finalize installation

    # The Networking service initialization scripts expect a symbolic link /etc/neutron/plugin.ini 
    # pointing to the ML2 plug-in configuration file, /etc/neutron/plugins/ml2/ml2_conf.ini. 
    # If this symbolic link does not exist, create it
    if 'plugin.ini' not in sudo('ls /etc/neutron'):
        sudo('ln -s /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini')

    # Due to a packaging bug, the Open vSwitch agent initialization script explicitly looks for 
    # the Open vSwitch plug-in configuration file rather than a symbolic link /etc/neutron/plugin.ini pointing to the ML2 
    # plug-in configuration file. Run the following commands to resolve this issue:
    sudo("cp /usr/lib/systemd/system/neutron-openvswitch-agent.service " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service.orig")
    sudo("sed -i 's,plugins/openvswitch/ovs_neutron_plugin.ini,plugin.ini,g' " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service")

    # initialize services
    sudo("systemctl enable neutron-openvswitch-agent.service neutron-l3-agent.service " +  \
              "neutron-dhcp-agent.service neutron-metadata-agent.service " + \
                "neutron-ovs-cleanup.service")
    sudo("systemctl start neutron-openvswitch-agent.service neutron-l3-agent.service " + \
              "neutron-dhcp-agent.service neutron-metadata-agent.service")





@roles('compute')
def compute_deploy():
    pass

def deploy():
    # with settings(warn_only=True):
    execute(controller_deploy)
    execute(network_deploy)

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
            name = sudo('neutron ext-list | grep {} | cut -d\| -f3'.format(alias))
            if pair[1] not in name:
                print red("Problem with alias {}: should be {}, is {}".format(alias,pair[1],name.strip()))
            else:
                print green("alias {} is {}, as expected".format(alias,name.strip()))

@roles('controller')
def verify_neutron_agents():
    # this test should be done after the network deployment,
    # even though it's done on the controller node

    # verify successful launch of the neutron agents

    neutron_agents = ['Metadata agent','Open vSwitch agent','L3 agent','DHCP agent']

    exports = open(admin_openrc,'r').read()
    with prefix(exports):
        # grab the agent list as a list of lines, skipping header
        agent_list = sudo("neutron agent-list").splitlines()[3:]

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
                    print red(sudo(get_line))
                else:
                    print green("Neutron agent {} OK!".format(agent))


@roles('network')
def network_tdd():
    execute(verify_neutron_agents)


def tdd():
    with settings(warn_only=True):
        execute(controller_tdd)


