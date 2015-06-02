from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import string
import logging

import sys
sys.path.append('../global_config_files')
import env_config


############################ Config ########################################

env.roledefs = env_config.roledefs

# Get configuration dictionaries from the config files
compute_tunnels = env_config.read_dict('config_files/compute_instance_tunnels_interface_config')
compute_manage = env_config.read_dict('config_files/compute_management_interface_config')
controller_manage = env_config.read_dict('config_files/controller_management_interface_config')
network_ext = env_config.read_dict('config_files/network_node_external_interface_config')
network_tunnels = env_config.read_dict('config_files/network_node_instance_tunnels_interface_config')
network_manage = env_config.read_dict('config_files/network_node_management_interface_config')
hosts_config = 'config_files/hosts_config'

# Logging config

log_file = 'basic-network.log'
env_config.setupLoggingInFabfile(log_file)

################### General functions ########################################

def generate_ip(ip_address,nodes_in_role,node):
	# generate an IP address based on a base ip, a node, and a role list
	# will be used for setting up interfaces and for testing

	last_octet = int(ip_address.split('.')[3])
	# first node will have last_octet + 0 as last octet; second node 
	# will have last_octet + 1, etc   
	last_octet += nodes_in_role.index(node)
	# turn it into a list of octets, with the old last octet removed
	octets = ip_address.split('.')[0:3]
	# add the dots to the octets
	octets = [octet + '.' for octet in octets]
	# append the last octet
        octets.append(str(last_octet))
	# turn it back into a single string
	ip_address = "".join(octets)
	return ip_address

################### Deployment ########################################

# General function to restart network
def restart_network(log_dict):
    # restarting network to implement changes 
    # turn off NetworkManager and use regular network application to restart

    sudo('chkconfig NetworkManager off')
    sudo('service NetworkManager stop')
    if sudo('service network restart').return_code != 0:
        logging.error('service network failed to restart',extra=log_dict)
    if sudo('service NetworkManager start').return_code != 0:
        logging.error('NetworkManager faile to restart',extra=log_dict)

# General function to set a virtual NIC
def set_up_network_interface(specs_dict,role,log_dict):

    if 'IPADDR' in specs_dict:
	# change the IP in the dict for the correct one
	specs_dict['IPADDR'] = generate_ip(specs_dict['IPADDR'], env.roledefs[role], env.host_string)
	#IPs_in_network.append((ip_address, env.host_string))


    # create config file
    config_file = ''
    for shell_variable in specs_dict.keys():
        config_file += shell_variable + '=' + specs_dict[shell_variable] + '\n' 

    # save file into directory

    device_name = specs_dict['DEVICE']
    # change to network-scripts directory
    with cd('/etc/sysconfig/network-scripts'):
        # create ifcfg file in the directory
        sudo('echo -e "{}" >ifcfg-{}'.format(config_file,device_name))

    logging.debug('Set up virtual NIC with name {}'.format(device_name),extra=log_dict)

def set_hosts(log_dict):
    # configure the /etc/hosts file to put aliases
    config_file = open(hosts_config, 'r').read()
    sudo("cp /etc/hosts /etc/hosts.back12")
    sudo("sed -i '/controller/d' /etc/hosts")
    sudo("sed -i '/network/d' /etc/hosts")
    sudo("sed -i '/compute/d' /etc/hosts")
    append('/etc/hosts',config_file,use_sudo=True)
    logging.debug('Configured /etc/hosts file',extra=log_dict)

def configureNTP(log_dict):

    confFile = '/etc/ntp.conf'
    newLine = 'server controller iburst'

    # check if file has been configured already
    if sudo("grep '{}' {}".format(newLine,confFile)).return_code == 0:
        message = 'NTP conf file has already been set. Nothing done'
        print message
        logging.debug(message,extra=log_dict)
        return

    # make a backup
    sudo('cp {} {}.back12'.format(confFile,confFile))

    # comment out all server keys
    sudo("sed -i '/server/ s/^/#/' " + confFile)

    # add one server key to reference the controller node
    sudo("echo '{}' >>{}".format(newLine,confFile))
    sudo("cat {} | grep -v '#'".format(confFile))

    # enable and start ntp service
    sudo("systemctl enable ntpd.service")
    sudo("systemctl start ntpd.service")

@roles('controller')
def controller_network_deploy():
    # create log dictionary (to set up the log formatting)
    log_dict = {'host_string':env.host_string,'role':'controller'}

    # set up management interface
    management_specs = controller_manage
    set_up_network_interface(management_specs,'controller',log_dict)

    restart_network(log_dict)
    set_hosts(log_dict)
    logging.debug('Deployment done on host',extra=log_dict)

@roles('network')
def network_node_network_deploy():
    # create log dictionary (to set up the log formatting)
    log_dict = {'host_string':env.host_string,'role':'controller'}

    # set up management interface
    management_specs = network_manage
    set_up_network_interface(management_specs,'network',log_dict)

    # set up instance tunnels interface
    instance_tunnels_specs = network_tunnels
    set_up_network_interface(instance_tunnels_specs,'network',log_dict)

    # set up external interface
    external_specs = network_ext
    set_up_network_interface(external_specs,'network',log_dict)

    restart_network(log_dict)
    set_hosts(log_dict)
    configureNTP(log_dict)
    logging.debug('Deployment done on host',extra=log_dict)

@roles('compute')
def compute_network_deploy():
    # create log dictionary (to set up the log formatting)
    log_dict = {'host_string':env.host_string,'role':'controller'}

    # set up management interface
    management_specs = compute_manage
    set_up_network_interface(management_specs,'compute',log_dict)

    # set up instance tunnels interface
    instance_tunnels_specs = compute_tunnels
    set_up_network_interface(instance_tunnels_specs,'compute',log_dict)

    restart_network(log_dict)
    set_hosts(log_dict)
    configureNTP(log_dict)
    logging.debug('Deployment done on host',extra=log_dict)

def deploy():
    # create log dictionary (to set up the log formatting)
    log_dict = {'host_string':'','role':''}
    logging.debug('Starting deployment',extra=log_dict)

    with settings(warn_only=True):
        execute(controller_network_deploy)
        execute(network_node_network_deploy)
        execute(compute_network_deploy)

#################### Fix me ########################

@roles('network','compute')
def fixme(log_dict={}):

    confFile = '/etc/ntp.conf'

    # make a backup
    print('cp {} {}.back12'.format(confFile,confFile))
    sudo('cp {} {}.back12'.format(confFile,confFile))

    # comment out all server keys
    sudo("sed -i '/server/ s/^/#/' " + confFile)

    # add one server key to reference the controller node
    newLine = 'server controller iburst'
    sudo("echo '{}' >>{}".format(newLine,confFile))
    sudo("cat {} | grep -v '#'".format(confFile))

    # enable and start ntp service
    sudo("systemctl enable ntpd.service")
    sudo("systemctl start ntpd.service")
######################################## TDD #########################################

# pings an ip address and see if it works
def ping_ip(ip_address, host, role='', type_interface=''):
    ping_command = 'ping -q -c 1 ' + ip_address
    result = run(ping_command)
    if result.return_code != 0:
        print(red('Problem from {} to {}({})\'s {} interface'.format(env.host_string, host, role, type_interface)))
    else:
        print(green('Okay from {} to {}({})\'s {} interface'.format(env.host_string, host, role, type_interface)))

@roles('controller')
def network_tdd_controller():
    # ping a website
    ping_ip('www.google.ca','google.ca')

    # ping management interface on network nodes
    nodes_in_role = env.roledefs['network']
    base_ip = network_manage['IPADDR']
    # generate a list of tuples (IP,node) for each network node
    management_network_interfaces = [( generate_ip(base_ip,nodes_in_role,node) ,node) for node in nodes_in_role]
    # ping the management interfaces
    for interface_ip, network_node in management_network_interfaces:
        ping_ip(interface_ip, network_node, 'network', 'management')

@roles('network')
def network_tdd_network():
    # needs to ping management interface(s) on controller node(s)
    # and instance tunnels interface(s) on compute node(s)

    # check for connection to internet
    ping_ip('google.ca', 'google.ca')

    # management interfaces on controller
    specs_dict = controller_manage
    ip_list = [(generate_ip(specs_dict['IPADDR'], env.roledefs['controller'], node), node) for node in env.roledefs['controller']]
    for ip, host in ip_list:
        ping_ip(ip, host, 'controller', 'management')

    # instance tunnel interfaces on compute
    specs_dict = compute_tunnels
    ip_list = [(generate_ip(specs_dict['IPADDR'], env.roledefs['compute'], node), node) for node in env.roledefs['compute']]
    for ip, host in ip_list:
        ping_ip(ip, host, 'compute', 'instance tunnel')

@roles('compute')
def network_tdd_compute():
    # check for connection to internet
    ping_ip('google.ca', 'google.ca')

    # ping management interface on controller nodes
    nodes_in_role = env.roledefs['controller']
    base_ip = controller_manage['IPADDR']
    # generage a list of tuples (IP,node) for each controller node
    management_controller_interfaces = [(generate_ip(base_ip, nodes_in_role, node), node) for node in nodes_in_role]
    # ping the management interfaces
    for interface_ip, controller_node in management_controller_interfaces:
        ping_ip(interface_ip, controller_node, 'controller', 'management')

    # ping instance tunnel interface on network nodes
    nodes_in_role = env.roledefs['network']
    base_ip = network_tunnels['IPADDR']
    # generage a list of tuples (IP,node) for each controller node
    network_tunnels_interfaces = [(generate_ip(base_ip, nodes_in_role, node), node) for node in nodes_in_role]
    # ping the management interfaces
    for interface_ip, network_node in network_tunnels_interfaces:
        ping_ip(interface_ip, network_node, 'network', 'instance tunnel')

            
def tdd():
    with settings(warn_only=True):
	execute(network_tdd_controller)
	execute(network_tdd_network)
	execute(network_tdd_compute)
