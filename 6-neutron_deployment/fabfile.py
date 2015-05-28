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

################### General functions ########################################


################### Deployment ########################################

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
    

@roles('network')
def network_deploy():
    pass

@roles('compute')
def compute_deploy():
    pass

def deploy():
    # with settings(warn_only=True):
    execute(controller_deploy)

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


def tdd():
    with settings(warn_only=True):
        execute(controller_tdd)


