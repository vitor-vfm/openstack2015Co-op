from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import string


############################ Config ########################################

# Read the values from a node file into a list
@hosts('localhost')
def read_nodes(node):
    node_info = open(node, 'r')
    node_string = node_info.read().splitlines()
    # remove comments (lines that have # in the beginning)
    # node_string_stripped = [node_element.strip() for node_element in node_string if node_element[0] != '#']
    node_info.close()
    #print node_string_stripped
    return node_string

# Make a dictionary from a config file with the format "KEY=value" on each 
# line
@hosts('localhost')
def read_dict(config_file):
    config_file_info = open(config_file, 'r')
    config_file_without_comments = [line for line in config_file_info.readlines() if line[0] != '#']
    config_file_string = "".join(config_file_without_comments)
    # config_file_string = config_file_info.read().replace('=','\n').splitlines()
    config_file_string = config_file_string.replace('=','\n').splitlines()
    config_file_string_stripped = [config_element.strip() for config_element in config_file_string]
    config_file_dict = dict()
    
    # Make a dictionary from the string from the file with the the first value
    # on a line being the key to the value after the '=' on the same line
    for config_file_key_index in range(0,len(config_file_string_stripped)-1,2):
        config_file_value_index = config_file_key_index + 1
        config_file_dict[config_file_string_stripped[config_file_key_index]] = config_file_string_stripped[config_file_value_index]
    
    config_file_info.close()

    #run("rm -rf %s" % config_file)
    return config_file_dict


# Get nodes and their roles from the config files
compute_nodes = read_nodes('config_files/compute_nodes')
controller_nodes = read_nodes('config_files/controller_nodes')
network_nodes = read_nodes('config_files/network_nodes')
#env.hosts = compute_nodes + controller_nodes + network_nodes
env.roledefs = { 'controller':controller_nodes, 'compute':compute_nodes, 'network':network_nodes }

# Get configuration dictionaries from the config files
compute_tunnels = read_dict('config_files/compute_instance_tunnels_interface_config')
compute_manage = read_dict('config_files/compute_management_interface_config')
controller_manage = read_dict('config_files/controller_management_interface_config')
network_ext = read_dict('config_files/network_node_external_interface_config')
network_tunnels = read_dict('config_files/network_node_instance_tunnels_interface_config')
network_manage = read_dict('config_files/network_node_management_interface_config')
hosts_config = 'config_files/hosts_config'

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
def restart_network():
    # restarting network to implement changes 
    # turn off NetworkManager and use regular network application to restart

    sudo('chkconfig NetworkManager off')
    sudo('service NetworkManager stop')
    sudo('service network restart')
    sudo('service NetworkManager start')
    # sudo('service NetworkManager restart')
    # sudo('nmcli connection reload')
    # device_name = compute_manage['DEVICE'][:-2]
    # sudo('nmcli device disconnect {}'.format(device_name))
    # sudo('nmcli device connect {}'.format(device_name))

# General function to set a virtual NIC
def set_up_network_interface(specs_dict,role):

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
    # restart network interface to initiate
    #sudo('service network restart')
    #sudo('ifdown {} && ifup {}'.format(device_name,device_name))

def set_hosts():
    # configure the /etc/hosts file to put aliases
    config_file = open(hosts_config, 'r').read()
    sudo("cp /etc/hosts /etc/hosts.back12")
    append('/etc/hosts',config_file,use_sudo=True)

@roles('controller')
def controller_network_deploy():
    # set up management interface
    management_specs = controller_manage
    set_up_network_interface(management_specs,'controller')

    restart_network()
    set_hosts()

@roles('network')
def network_node_network_deploy():
    # set up management interface
    management_specs = network_manage
    set_up_network_interface(management_specs,'network')

    # set up instance tunnels interface
    instance_tunnels_specs = network_tunnels
    set_up_network_interface(instance_tunnels_specs,'network')

    # set up external interface
    external_specs = network_ext
    set_up_network_interface(external_specs,'network')

    restart_network()
    set_hosts()

@roles('compute')
def compute_network_deploy():
    # set up management interface
    management_specs = compute_manage
    set_up_network_interface(management_specs,'compute')

    # set up instance tunnels interface
    instance_tunnels_specs = compute_tunnels
    set_up_network_interface(instance_tunnels_specs,'compute')

    restart_network()
    set_hosts()

def network_deploy():
    execute(controller_network_deploy)
    execute(network_node_network_deploy)
    execute(compute_network_deploy)

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

            
def network_tdd():
    with settings(warn_only=True):
	execute(network_tdd_controller)
	execute(network_tdd_network)
	execute(network_tdd_compute)
