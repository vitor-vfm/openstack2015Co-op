from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
import string
import logging
import subprocess

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, createDatabaseScript, set_parameter
from myLib import align_y, align_n, keystone_check, database_check, saveConfigFile
from myLib import backupConfFile, restoreBackups


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

backupSuffix = '.bak6'

# define host config file locations
neutron_conf = '/etc/neutron/neutron.conf'
ml2_conf_file = '/etc/neutron/plugins/ml2/ml2_conf.ini'
nova_conf = '/etc/nova/nova.conf'
l3_agent_file = '/etc/neutron/l3_agent.ini'
dhcp_agent_file = '/etc/neutron/dhcp_agent.ini'
metadata_agent_file = '/etc/neutron/metadata_agent.ini'
#sysctl_conf = '/etc/sysctl.conf'
sysctl_conf = '/usr/lib/sysctl.d/50-default.conf' # for more info visit: https://www.digitalocean.com/community/questions/how-to-enable-ip-masquerading-forwarding-on-centos-7

confFiles = [
        neutron_conf,
        ml2_conf_file,
        nova_conf,
        l3_agent_file,
        dhcp_agent_file,
        metadata_agent_file,
        sysctl_conf,
        ]

dnsServer = ['129.128.208.13', '129.128.5.233']

######################### Deployment ########################################

# CONTROLLER

@roles('controller')
def create_neutron_database():
    database_script = createDatabaseScript('neutron',passwd['NEUTRON_DBPASS'])
    msg = "Create MySQL database for neutron"
    runCheck(msg, '''echo "{}" | mysql -u root -p{}'''.format(
        database_script, env_config.passwd['ROOT_SECRET']))

@roles('controller')
def setup_keystone_controller():
    """
    Set up Keystone credentials for Neutron

    Create (a) a user and a service called 'neutron', and
    (b) an endpoint for the 'neutron' service
    """

    # get credentials
    with prefix(env_config.admin_openrc):

        # check if user neutron has been created and if not, create it
        if 'neutron' not in run("keystone user-list"):
            # create the neutron user in keystone
            msg = "Create neutron user"
            runCheck(msg, 'keystone user-create --name neutron --pass {}'.format(passwd['NEUTRON_PASS']))
            msg = "Add the admin role to the neutron user"
            runCheck(msg, 'keystone user-role-add --user neutron --tenant service --role admin')
        else:
            print blue('\t\tneutron is already a user. Do nothing')

        # check if service neutron has been created and if not, create it
        if 'neutron' not in run("keystone service-list"):
            msg = "Create the neutron service entity"
            runCheck(msg, 'keystone service-create --name neutron --type network '
                    '--description "OpenStack Networking"')
        else:
            print blue('\t\tneutron is already a service. Do nothing')

        # check if a 9696 endpoint already exists and if not, create one
        if 'http://controller:9696' not in run("keystone endpoint-list"):
            msg =  "Create the networking service API endpoints"
            runCheck(msg, 'keystone endpoint-create ' + \
                    "--service-id $(keystone service-list | awk '/ network / {print $2}') " + \
                    "--publicurl http://controller:9696 " + \
                    "--adminurl http://controller:9696 " + \
                    "--internalurl http://controller:9696 " + \
                    "--region regionOne")
        else:
            print blue('\t\t9696 is already an endpoint. Do nothing')

@roles('controller')
def configure_networking_server_component():
    # configure neutron.conf with crudini

    # make a backup
    backupConfFile(neutron_conf, backupSuffix)

    # configure database access
    parameter = 'mysql://neutron:{}@controller/neutron'.format(passwd['NEUTRON_DBPASS'])
    set_parameter(neutron_conf,'database','connection',parameter)

    # configure RabbitMQ access
    set_parameter(neutron_conf,'DEFAULT','rpc_backend','rabbit')
    set_parameter(neutron_conf,'DEFAULT','rabbit_host','controller')
    set_parameter(neutron_conf,'DEFAULT','rabbit_password',passwd['RABBIT_PASS'])

    # configure Identity service access

    set_parameter(neutron_conf,'DEFAULT','auth_strategy','keystone')
    set_parameter(neutron_conf,'keystone_authtoken','auth_uri','http://controller:5000/v2.0')
    set_parameter(neutron_conf,'keystone_authtoken','identity_uri','http://controller:35357')
    set_parameter(neutron_conf,'keystone_authtoken','admin_tenant_name','service')
    set_parameter(neutron_conf,'keystone_authtoken','admin_user','neutron')
    set_parameter(neutron_conf,'keystone_authtoken','admin_password',passwd['NEUTRON_PASS'])

    # enable ML2 plugin

    set_parameter(neutron_conf,'DEFAULT','core_plugin','ml2')
    set_parameter(neutron_conf,'DEFAULT','service_plugins','router')
    set_parameter(neutron_conf,'DEFAULT','allow_overlapping_ips','True')

    # set Neutron to notify Nova of of topology changes
    # get service tenant id
    with prefix(env_config.admin_openrc):
        nova_admin_tenant_id = run('keystone tenant-list | grep service | cut -d\| -f2')

    if nova_admin_tenant_id:
        # if tenant service doesn't exist, this variable will be empty
        set_parameter(neutron_conf,'DEFAULT','nova_admin_tenant_id',nova_admin_tenant_id)


    set_parameter(neutron_conf,'DEFAULT','notify_nova_on_port_status_changes','True')
    set_parameter(neutron_conf,'DEFAULT','notify_nova_on_port_data_changes','True')
    set_parameter(neutron_conf,'DEFAULT','nova_url','http://controller:8774/v2')
    set_parameter(neutron_conf,'DEFAULT','nova_admin_auth_url','http://controller:35357/v2.0')
    set_parameter(neutron_conf,'DEFAULT','nova_region_name','regionOne')
    set_parameter(neutron_conf,'DEFAULT','nova_admin_username','nova')
    set_parameter(neutron_conf,'DEFAULT','nova_admin_password',passwd['NOVA_PASS'])

    # turn on verbose logging
    set_parameter(neutron_conf,'DEFAULT','verbose','True')
    set_parameter(neutron_conf,'DEFAULT','debug','True')

def configure_ML2_plugin_general():
    # The ML2 plug-in uses the Open vSwitch (OVS) mechanism (agent) to build the virtual
    # networking framework for instances. However, the controller node does not need the OVS
    # components because it does not handle instance network traffic.

    # make a backup
    backupConfFile(ml2_conf_file, backupSuffix)


    # set_parameter(ml2_conf_file,'ml2','type_drivers','flat,gre')
    set_parameter(ml2_conf_file,'ml2','type_drivers','flat,gre,vlan')
    set_parameter(ml2_conf_file,'ml2','tenant_network_types','gre')
    set_parameter(ml2_conf_file,'ml2','mechanism_drivers','openvswitch')

    set_parameter(ml2_conf_file,'ml2_type_gre','tunnel_id_ranges','1:1000')

    set_parameter(ml2_conf_file,'securitygroup','enable_security_group','True')
    set_parameter(ml2_conf_file,'securitygroup','enable_ipset','True')
    set_parameter(ml2_conf_file,'securitygroup','firewall_driver',\
            'neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver')

@roles('controller')
def restart_nova_controller():
    # Restart nova
    msg = "Restart Nova services"
    runCheck(msg, 'systemctl restart openstack-nova-api.service openstack-nova-scheduler.service' + \
              ' openstack-nova-conductor.service')

@roles('controller')
def configure_nova_to_use_neutron():

    # make a backup
    backupConfFile(nova_conf, backupSuffix)

    set_parameter(nova_conf,'DEFAULT','network_api_class','nova.network.neutronv2.api.API')
    set_parameter(nova_conf,'DEFAULT','security_group_api','neutron')
    set_parameter(nova_conf,'DEFAULT','linuxnet_interface_driver','nova.network.linux_net.LinuxOVSInterfaceDriver')
    set_parameter(nova_conf,'DEFAULT','firewall_driver','nova.virt.firewall.NoopFirewallDriver')

    set_parameter(nova_conf,'neutron','url','http://controller:9696')
    set_parameter(nova_conf,'neutron','auth_strategy','keystone')
    set_parameter(nova_conf,'neutron','admin_auth_url','http://controller:35357/v2.0')
    set_parameter(nova_conf,'neutron','admin_tenant_name','service')
    set_parameter(nova_conf,'neutron','admin_username','neutron')
    set_parameter(nova_conf,'neutron','admin_password',passwd['NEUTRON_PASS'])

@roles('controller')
def installPackagesController():
    msg = "Install Neutron packages on controller"
    runCheck(msg,
            'yum -y install '
            'openstack-neutron '
            'openstack-neutron-ml2 '
            'python-neutronclient '
            'which')

@roles('controller')
def controller_deploy():

    execute(create_neutron_database)
    execute(setup_keystone_controller)
    execute(installPackagesController)
    execute(configure_networking_server_component)

    configure_ML2_plugin_general()

    execute(configure_nova_to_use_neutron)

    # The Networking service initialization scripts expect a symbolic link /etc/neutron/plugin.ini
    # pointing to the ML2 plug-in configuration file, /etc/neutron/plugins/ml2/ml2_conf.ini.
    # If this symbolic link does not exist, create it
    if 'plugin.ini' not in run('ls /etc/neutron'):
        msg = "Create symbolic link to ml2 conf file"
        runCheck(msg, 'ln -s /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini')

    msg = "Populate the database for neutron"
    runCheck(msg, 'su -s /bin/sh -c "neutron-db-manage --config-file /etc/neutron/neutron.conf ' + \
              '--config-file /etc/neutron/plugins/ml2/ml2_conf.ini upgrade juno" neutron')

    # Restart nova
    msg = "Restart Nova services"
    runCheck(msg, 'systemctl restart openstack-nova-api.service openstack-nova-scheduler.service' + \
              ' openstack-nova-conductor.service')

    msg = "Enable Neutron service"
    runCheck(msg, 'systemctl enable neutron-server.service')
    msg = "Enable Neutron service"
    runCheck(msg, 'systemctl start neutron-server.service')
  
    execute(restart_nova_controller)

# NETWORK

def configure_the_Networking_common_components():

    # make a backup
    backupConfFile(neutron_conf, backupSuffix)

    # configure RabbitMQ access
    set_parameter(neutron_conf,'DEFAULT','rpc_backend','rabbit')
    set_parameter(neutron_conf,'DEFAULT','rabbit_host','controller')
    set_parameter(neutron_conf,'DEFAULT','rabbit_password',passwd['RABBIT_PASS'])

    # configure Identity service access

    set_parameter(neutron_conf,'DEFAULT','auth_strategy','keystone')
    set_parameter(neutron_conf,'keystone_authtoken','auth_uri','http://controller:5000/v2.0')
    set_parameter(neutron_conf,'keystone_authtoken','identity_uri','http://controller:35357')
    set_parameter(neutron_conf,'keystone_authtoken','admin_tenant_name','service')
    set_parameter(neutron_conf,'keystone_authtoken','admin_user','neutron')
    set_parameter(neutron_conf,'keystone_authtoken','admin_password',passwd['NEUTRON_PASS'])

    # enable ML2 plugin

    set_parameter(neutron_conf,'DEFAULT','core_plugin','ml2')
    set_parameter(neutron_conf,'DEFAULT','service_plugins','router')
    set_parameter(neutron_conf,'DEFAULT','allow_overlapping_ips','True')
    set_parameter(neutron_conf,'DEFAULT','verbose','True')
    set_parameter(neutron_conf,'DEFAULT','debug','True')

def configure_ML2_plug_in_network():
  
    # most of the configuration is the same as the controller
    configure_ML2_plugin_general()

    # configure the external flat provider network
    set_parameter(ml2_conf_file,'ml2_type_flat','flat_networks','external')

    # configure the external flat provider network
    set_parameter(ml2_conf_file,'ovs','enable_tunneling','True')
    set_parameter(ml2_conf_file,'ovs','bridge_mappings','external:br-ex')
    local_ip = env_config.nicDictionary[env.host]['tnlIPADDR']
    set_parameter(ml2_conf_file,'ovs','local_ip',local_ip)

    # enable GRE tunnels
    set_parameter(ml2_conf_file,'agent','tunnel_types','gre')

def configure_Layer3_agent():

    # make a backup
    backupConfFile(l3_agent_file, backupSuffix)

    set_parameter(l3_agent_file,"DEFAULT","interface_driver","neutron.agent.linux.interface.OVSInterfaceDriver")
    set_parameter(l3_agent_file,"DEFAULT","use_namespaces","True")
    set_parameter(l3_agent_file,"DEFAULT","external_network_bridge","br-ex")
    set_parameter(l3_agent_file,"DEFAULT","router_delete_namespaces","True")
    set_parameter(l3_agent_file,"DEFAULT","verbose","True")
    set_parameter(l3_agent_file,"DEFAULT","debug","True")

def configure_DHCP_agent():

    # make a backup
    backupConfFile(dhcp_agent_file, backupSuffix)

    set_parameter(dhcp_agent_file,"DEFAULT","interface_driver",
            "neutron.agent.linux.interface.OVSInterfaceDriver")
    set_parameter(dhcp_agent_file,"DEFAULT","dhcp_driver",
            "neutron.agent.linux.dhcp.Dnsmasq")
    set_parameter(dhcp_agent_file,"DEFAULT","use_namespaces","True")
    set_parameter(dhcp_agent_file,"DEFAULT","dhcp_delete_namespaces","True")
    set_parameter(dhcp_agent_file,"DEFAULT","verbose","True")
    set_parameter(dhcp_agent_file,"DEFAULT","debug","True")

@roles('controller')
def configure_metadata_proxy_on_controller():
    # to configure the metadata agent, some changes need to be made
    # on the controller node

    # make a backup
    backupConfFile(nova_conf, backupSuffix)

    set_parameter(nova_conf,'neutron','service_metadata_proxy','True')
    set_parameter(nova_conf,'neutron','metadata_proxy_shared_secret',
            passwd['METADATA_SECRET'])

    msg = "Restart Nova service"
    runCheck(msg, "systemctl restart openstack-nova-api.service")


def configure_metadata_agent():

    # make a backup
    backupConfFile(metadata_agent_file, backupSuffix)

    set_parameter(metadata_agent_file,'DEFAULT','auth_url','http://controller:5000/v2.0')
    set_parameter(metadata_agent_file,'DEFAULT','auth_region','regionOne')
    set_parameter(metadata_agent_file,'DEFAULT','admin_tenant_name','service')
    set_parameter(metadata_agent_file,'DEFAULT','admin_user','neutron')
    set_parameter(metadata_agent_file,'DEFAULT','nova_metadata_ip','controller')
    set_parameter(metadata_agent_file,'DEFAULT','admin_password',passwd['NEUTRON_PASS'])
    set_parameter(metadata_agent_file,'DEFAULT','metadata_proxy_shared_secret',
            passwd['METADATA_SECRET'])
    set_parameter(metadata_agent_file,'DEFAULT','verbose','True')
    set_parameter(metadata_agent_file,'DEFAULT','debug','True')

    execute(configure_metadata_proxy_on_controller)

def configure_Open_vSwitch_service():

    msg = 'Enable OpenvSwitch service'
    runCheck(msg, "systemctl enable openvswitch.service")
    msg = 'Start OpenvSwitch service'
    runCheck(msg, "systemctl start openvswitch.service")

    # add br-ex bridge
    if 'br-ex' not in run("ovs-vsctl list-br"):
        msg = 'Create bridge br-ex'
        runCheck(msg, "ovs-vsctl add-br br-ex")

        msg = 'Add port to br-ex'
        runCheck(msg, "ovs-vsctl add-port br-ex " + \
                env_config.nicDictionary[env.host]['extDEVICE'])
    else:
        print blue('br-ex already created. Do nothing')

@roles('network')
def installPackagesNetwork():
    msg = "Install Neutron packages on network"
    runCheck(msg,
            "yum -y install "
            "openstack-neutron "
            "openstack-neutron-ml2 "
            "openstack-neutron-openvswitch",
            )

@roles('network')
def network_deploy():

    # edit sysctl.conf

    # make a backup
    backupConfFile(sysctl_conf, backupSuffix)

    set_parameter(sysctl_conf,"''",'net.ipv4.ip_forward','1')
    set_parameter(sysctl_conf,"''",'net.ipv4.conf.all.rp_filter','0')
    set_parameter(sysctl_conf,"''",'net.ipv4.conf.default.rp_filter','0')

    msg = "Implement changes on sysctl"
    runCheck(msg, "sysctl --system")  # for more info visit: http://www.commandlinefu.com/commands/view/11891/reload-all-sysctl-variables-without-reboot

    installPackagesNetwork()
  
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
    if 'plugin.ini' not in run('ls /etc/neutron'):
        msg = "Create symbolic link to ml2 conf file"
        runCheck(msg, 'ln -s /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini')

    # Due to a packaging bug, the Open vSwitch agent initialization script explicitly looks for
    # the Open vSwitch plug-in configuration file rather than a symbolic link /etc/neutron/plugin.ini pointing to the ML2
    # plug-in configuration file. Run the following commands to resolve this issue:
    run("cp /usr/lib/systemd/system/neutron-openvswitch-agent.service " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service.orig")
    run("sed -i 's,plugins/openvswitch/ovs_neutron_plugin.ini,plugin.ini,g' " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service")

    # initialize services
    msg = "Enable neutron services"
    run("systemctl enable neutron-openvswitch-agent.service neutron-l3-agent.service " +  \
              "neutron-dhcp-agent.service neutron-metadata-agent.service " + \
                "neutron-ovs-cleanup.service")
    msg = "Start neutron services"
    run("systemctl start neutron-openvswitch-agent.service neutron-l3-agent.service " + \
              "neutron-dhcp-agent.service neutron-metadata-agent.service")


# COMPUTE

def configure_ML2_plug_in_compute():
    
    # most of the configuration is the same as the controller
    configure_ML2_plugin_general()

    # configure the external flat provider network 
    set_parameter(ml2_conf_file,'ovs','enable_tunneling','True')
    local_ip = env_config.nicDictionary[env.host]['tnlIPADDR']
    set_parameter(ml2_conf_file,'ovs','local_ip',local_ip)

    # enable GRE tunnels
    set_parameter(ml2_conf_file,'agent','tunnel_types','gre')

@parallel
@roles('compute')
def installPackagesCompute():

    msg = "Install Neutron packages on " + env.host
    runCheck(msg, "yum -y install "
            "openstack-neutron-ml2 "
            "openstack-neutron-openvswitch",
            )

@parallel
@roles('compute')
def compute_deploy():
  
    # edit sysctl.conf

    # make a backup
    backupConfFile(sysctl_conf, backupSuffix)

    set_parameter(sysctl_conf,"''",'net.ipv4.conf.all.rp_filter','0')
    set_parameter(sysctl_conf,"''",'net.ipv4.conf.default.rp_filter','0')

    msg = "Implement changes on sysctl on compute node " + env.host
    runCheck(msg, "sysctl -p")

    installPackagesCompute()

    # configuration

    configure_the_Networking_common_components() # same as networking

    configure_ML2_plug_in_compute()

    configure_nova_to_use_neutron()

    msg = 'Enable Open vSwitch'
    runCheck(msg, 'systemctl enable openvswitch.service')
    msg = 'Start Open vSwitch'
    runCheck(msg, 'systemctl start openvswitch.service')

    # finalize installation

    # The Networking service initialization scripts expect a symbolic link /etc/neutron/plugin.ini
    # pointing to the ML2 plug-in configuration file, /etc/neutron/plugins/ml2/ml2_conf.ini.
    # If this symbolic link does not exist, create it
    if 'plugin.ini' not in run('ls /etc/neutron'):
        msg = 'Create a symbolic link to Open vSwitch\'s conf file'
        runCheck(msg, 'ln -s /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini')

    # Due to a packaging bug, the Open vSwitch agent initialization script explicitly looks for
    # the Open vSwitch plug-in configuration file rather than a symbolic link /etc/neutron/plugin.ini pointing to the ML2
    # plug-in configuration file. Run the following commands to resolve this issue:
    msg = 'Chenge Open vSwitch to look for a symbolic link to to the ML2 conf file'
    run("cp /usr/lib/systemd/system/neutron-openvswitch-agent.service " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service.orig")
    run("sed -i 's,plugins/openvswitch/ovs_neutron_plugin.ini,plugin.ini,g' " + \
            "/usr/lib/systemd/system/neutron-openvswitch-agent.service")

    msg = 'Restart Nova service'
    runCheck(msg, "systemctl restart openstack-nova-compute.service")

    msg = 'Enable Open vSwitch'
    runCheck(msg, 'systemctl enable neutron-openvswitch-agent.service')
    msg = 'Start Open vSwitch'
    runCheck(msg, 'systemctl start neutron-openvswitch-agent.service')
    msg = 'Restart Open vSwitch'
    runCheck(msg, 'systemctl restart neutron-openvswitch-agent.service')

# INITIAL NETWORK

@roles('controller')
def createExtNet():
  
    with prefix(env_config.admin_openrc):
        if 'ext-net' in run('neutron net-list'):
            msg = 'Ext-net already created'
            print msg
        else:
            msg = 'create external network on network node'
            runCheck(msg,
                    'neutron net-create ext-net '
                    '--router:external True '
                    '--provider:physical_network external '
                    '--provider:network_type flat')
                    # '--provider:network_type vlan')

        msg = 'Restart Neutron service'
        runCheck(msg, 'systemctl restart neutron-server.service')

@roles('controller')
def createExtSubnet():

    with prefix(env_config.admin_openrc):
        if 'ext-subnet' in run('neutron subnet-list'):
            msg = 'ext-subnet already created'
            print msg
        else:
            msg = 'create initial subnet on external net on network node'
            runCheck(msg,
                    'neutron subnet-create ext-net '
                    '--name ext-subnet '
                    '--allocation-pool start=%s,end=%s ' % 
                    (env_config.ext_subnet['start'], env_config.ext_subnet['end']) + \
                    '--disable-dhcp '
                    '--gateway %s ' % env_config.ext_subnet['gateway'] + \
                    '%s ' % env_config.ext_subnet['cidr'])

        msg = 'Restart Neutron service'
        runCheck(msg, 'systemctl restart neutron-server.service')

@roles('controller')
def createDemoNet():
    with prefix(env_config.demo_openrc):
        if 'demo-net' in run('neutron net-list'):
            print blue('Demo-net already created')
        else:
            msg = 'Create initial demo tenant network on network node'
            runCheck(msg, 'neutron net-create demo-net')

        msg = 'Restart Neutron service'
        runCheck(msg, 'systemctl restart neutron-server.service')

@roles('controller')
def createDemoSubnet():
    with prefix(env_config.demo_openrc):
        if 'demo-subnet' in run('neutron subnet-list'):
            msg = 'Demo-subnet already created'
            print msg
        else:
            msg = 'create subnet on demo-net'
            runCheck(msg,
                    'neutron subnet-create demo-net '
                    '--name demo-subnet '
                    + ''.join(['--dns-nameserver %s ' % ip for ip in dnsServer]) +
                    '--gateway %s ' % env_config.demo_subnet['gateway'] + \
                    '%s ' % env_config.demo_subnet['cidr'])

        msg = 'Restart Neutron service'
        runCheck(msg, 'systemctl restart neutron-server.service')

@roles('controller')
def createDemoRouter():
    with prefix(env_config.demo_openrc):
        if 'demo-router' in run('neutron router-list'):
            print blue('Demo-router already created')
        else:
            msg = 'create the demo router'
            runCheck(msg,'neutron router-create demo-router')

            msg = 'attach the demo router to the demo subnet'
            runCheck(msg, 'neutron router-interface-add demo-router demo-subnet')

            # attach the router to the external network by setting it as the gateway
            msg = 'Set router as gateway'
            runCheck(msg,'neutron router-gateway-set demo-router ext-net')

        msg = 'Restart Neutron service'
        runCheck(msg, 'systemctl restart neutron-server.service')


@roles('controller')
def createInitialNetwork():
    # Creates a sample network for testing
    execute(createExtNet)
    execute(createExtSubnet)
    execute(createDemoNet)
    execute(createDemoSubnet)
    execute(createDemoRouter)

def deploy():
    execute(controller_deploy)
    execute(network_deploy)
    execute(compute_deploy)
    execute(createInitialNetwork)

##################################### Undeploy #######################################

@roles('network')
def removeBridges():
    delete = ['br-ex']
    for br in delete:
        if br in run("ovs-vsctl list-br"):
            msg = 'Delete bridge ' + br
            runCheck(msg, "ovs-vsctl del-br " + br)
        else:
            print blue('No bridge called ' + br)

@parallel
@roles('controller','network','compute')
def restoreConfs():
    restoreBackups(confFiles, backupSuffix)

@roles('controller')
def restoreDB():
    """
    Delete the database and repopulate it
    """

    database_script = createDatabaseScript('neutron',passwd['NEUTRON_DBPASS'])
    msg = "Recreate MySQL database for neutron"
    runCheck(msg, '''echo "{}" | mysql -u root -p{}'''.format(
        database_script, env_config.passwd['ROOT_SECRET']))

    msg = "Populate the database for neutron"
    runCheck(msg, 'su -s /bin/sh -c "neutron-db-manage --config-file /etc/neutron/neutron.conf ' + \
              '--config-file /etc/neutron/plugins/ml2/ml2_conf.ini upgrade juno" neutron')

@parallel
@roles('controller','network', 'compute')
def restartServices():
    msg = 'Restart services in ' + env.host
    runCheck(msg, 'openstack-service restart neutron')

@parallel
@roles('controller','network', 'compute')
def stopServices():
    msg = 'Stop services in ' + env.host
    runCheck(msg, 'openstack-service stop neutron')

@roles('controller')
def undeploy():
    execute(restoreConfs)
    execute(removeBridges)

    # stop all services
    execute(stopServices)

    execute(restoreDB)

    # restart all services
    execute(restartServices)

######################################## TDD #########################################

@roles('controller')
def saveConfigController(status):
    "Save locally the config files that exist in the controller node"
    saveConfigFile(neutron_conf,status)
    saveConfigFile(ml2_conf_file,status)
    saveConfigFile(nova_conf,status)

@roles('network')
def saveConfigNetwork(status):
    "Save locally the config files that exist in the network node"
    saveConfigFile(sysctl_conf,status)
    saveConfigFile(neutron_conf,status)
    saveConfigFile(ml2_conf_file,status)
    saveConfigFile(l3_agent_file,status)
    saveConfigFile(dhcp_agent_file,status)
    saveConfigFile(metadata_agent_file,status)

@parallel
@roles('compute')
def saveConfigCompute(status):
    "Save locally the config files that exist in the compute nodes"
    saveConfigFile(sysctl_conf,status)
    saveConfigFile(neutron_conf,status)
    saveConfigFile(nova_conf,status)

@roles('controller')
def controllerTDD():
    "Check if all extensions are functioning"

    with prefix(env_config.admin_openrc):
        msg = 'Run ext-list'
        extList = runCheck(msg, 'neutron ext-list')

    extensions = [
            'security-group',
            'l3_agent_scheduler',
            'ext-gw-mode',
            'binding',
            'provider',
            'agent',
            'quotas',
            'dhcp_agent_scheduler',
            'l3-ha',
            'multi-provider',
            'external-net',
            'router',
            'allowed-address-pairs',
            'extraroute',
            'extra_dhcp_opt',
            'dvr',
            ]

    allInList = True
    for extension in extensions:
        if extension not in extList:
            print align_n('Extension %s is not in the list' % extension)
            allInList = False

    if allInList:
        print align_y('All extensions in list')
    else:
        execute(saveConfigController,'bad')
        sys.exit(1)

@roles('network')
def networkTDD():
    "Check if all agents are functioning"

    with prefix(env_config.admin_openrc):
        msg = 'Run agent-list'
        agentList = runCheck(msg, 'neutron agent-list')

    # check if all agents are in the list
    allInList = True
    for agent in ['Metadata', 'Open vSwitch', 'L3', 'DHCP']:
        if agent not in agentList:
            print align_n('Agent %s is not in agent list' % agent)
            allInList = False
    if allInList:
        print align_y('All agents in list')

    # check if agents are active
    agentLines = agentList.splitlines()[3:-1] # remove header and footer
    allActive = True
    for line in agentLines:
        if ':-)' not in line:
            print align_n('One of the agents is not active')
            print line
            allActive = False
    if allActive:
        print align_y('All agents active')

    if not allActive or not allInList:
        execute(saveConfigNetwork,'bad')
        sys.exit(1)

@roles('controller')
def computeTDD():
    "Check if all compute nodes have an OVS agent active"

    with prefix(env_config.admin_openrc):
        msg = 'Run agent-list'
        agentList = runCheck(msg, 'neutron agent-list')

    # check if all compute nodes are mentioned in the list
    computeNodes = [host.replace('root@','') for host in env.roledefs['compute']]
    allInList = True
    for node in computeNodes:
        if node not in agentList:
            print align_n('%s is not mentioned in the agent list' % node)
            allInList = False
    if allInList:
        print align_y('All compute nodes are mentioned in agent list')

    # check if agents are active
    agentLines = agentList.splitlines()[3:-1] # remove header and footer
    allActive = True
    for line in agentLines:
        if ':-)' not in line:
            print align_n('One of the agents is not active')
            print line
            allActive = False
    if allActive:
        print align_y('All agents active')

    if not allActive or not allInList:
        execute(saveConfigCompute,'bad')
        sys.exit(1)

@roles('network')
def createInitialNetworkTDD():

    msg = 'Get namespaces'
    netspaces = runCheck(msg, 'ip netns list').splitlines()

    if len(netspaces) > 1:
        print align_n('There should be only one namespace (qrouter). Namespaces:')
        print netspaces
        # exit with error
        execute(saveConfigCompute,'bad')
        sys.exit(1)

    msg = "Ping the tenant router gateway from " + env.host
    runCheck(msg, "ip netns exec %s ping -c 1 %s" % 
            (netspaces[0], env_config.ext_subnet['start']))

@roles('controller')
def tdd():

    if database_check('neutron') == 'FAIL' or keystone_check('neutron') == 'FAIL':
        execute(saveConfigController,'bad')
        sys.exit(1)

    execute(controllerTDD)
    execute(networkTDD)
    execute(computeTDD)
    execute(createInitialNetworkTDD)

    # if all TDDs passed, save config files as 'good'
    execute(saveConfigController,'good')
    execute(saveConfigNetwork,'good')
    execute(saveConfigCompute,'good')
