from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.contrib.files import append, sed
from fabric.state import output
import string
import logging
import ConfigParser

import sys
sys.path.append('../global_config_files')
import env_config
from env_config import log_debug, log_info, log_error


############################ Config ########################################

env.roledefs = env_config.roledefs

mode = 'normal'
if output['debug']:
    mode = 'debug'

# Logging config

log_file = 'basic-network.log'
env_config.setupLoggingInFabfile(log_file)

run_log = env_config.run_log
sudo_log = env_config.sudo_log

################### General functions ########################################

def debug_str(command):
    # runs a command and returns its output in blue
    return blue(sudo(command,quiet=True))

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

def set_up_NIC_using_nmcli(specs_dict):
    # Set up a new interface by using NetworkManager's 
    # command line interface

    ifname = specs_dict['DEVICE']
    ip = specs_dict['IPADDR']
    # ifname = sudo_log("crudini --get {} '' DEVICE".format(conf_file))
    # ip = sudo_log("crudini --get {} '' IPADDR".format(conf_file))

    command = "nmcli connection add type ethernet"
    command += " con-name " + ifname # connection name is the same as interface name
    command += " ifname " + ifname
    command += " ip4 " + ip

    sudo_log(command)


# General function to restart network
def restart_network():
    # restarting network to implement changes 
    # turn off NetworkManager and use regular network application to restart

    # sudo_log('chkconfig NetworkManager off')
    # sudo_log('service NetworkManager stop')
    sudo_log('service network restart')
    # sudo_log('service NetworkManager start')

    # sudo_log("systemctl restart NetworkManager")

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
    config_file_name = 'ifcfg-' + device_name

    if mode == 'debug':
        config_file_name += '.test'
        print blue('Setting up debug file (.test)')

    # change to network-scripts directory
    with cd('/etc/sysconfig/network-scripts'):
        # create ifcfg file in the directory
        sudo_log('echo -e "{}" >{}'.format(config_file,config_file_name))

        if mode == 'debug':
            print blue('This is the test config file: ')
            print ''
            print debug_str('cat ' + config_file_name)
            print ''
            print blue('These are the ifcfg files in the directory: ')
            print debug_str('ls | grep ifcfg')
            print 'Deleting test file'
            print debug_str('rm ' + config_file_name)


    log_debug('Set up virtual NIC with conf file {}'.format(config_file_name))

def set_hosts():
    # configure the /etc/hosts file to put aliases
    aliases = env_config.hosts

    # make backup
    run_log("cp /etc/hosts /etc/hosts.back12")


    if mode == 'normal':
        confFile = '/etc/hosts'
    elif mode == 'debug':
        confFile = '~/hosts.debug'
        sudo("cp /etc/hosts " + confFile)
        print blue("Debugging set_hosts")

    # delete previous aliases
    run_log("sed -i '/controller/d' {}".format(confFile))
    run_log("sed -i '/network/d' {}".format(confFile))
    run_log("sed -i '/compute/d' {}".format(confFile))

    # add new aliases
    lines_to_add = [ip + "\t" + aliases[ip] for ip in aliases.keys()]
    for line in lines_to_add:
        run_log("echo '{}' >>{}".format(line,confFile))
    # delete empty lines
    run_log("sed -i '/^$/ d' {}".format(confFile))

    if mode == 'debug':
        # show file to check
        print blue("Final result for {} : ".format(confFile))
        sudo("cat " + confFile)
        # delete test file
        sudo("rm " + confFile)

def configChrony():

    chrony_conf = ''
    if env_config.getRole() == 'controller':
        # reference the ntp servers
        for server in env_config.ntpServers:
            chrony_conf += "server {} iburst\n".format(server)
    else:
        # reference the controller node
        chrony_conf += "server controller iburst\n"

    confFile = '/etc/chrony.conf'
    # make a backup
    sudo_log('cp {} {}.back12'.format(confFile,confFile))

    if mode == 'debug':
        confFile += '.back12'

    with settings(warn_only=True):
        run_log("echo '{}' > {}".format(chrony_conf,confFile))

        if mode == 'debug':
            print blue('This is what the conf file will look like: ')
            print blue(sudo('cat ' + confFile,quiet=True))

        run_log('systemctl restart chronyd.service')
        result=run_log('systemctl is-enabled chronyd.service')
        if result.failed :
            print "Chrony config failed"
        else:
            print "Chrony config OK"

def deployInterface(interface,specs):
    if mode == 'debug':
        print ''
        print blue('Deploying Interface {} now'.format(interface))
        print ''
    role = env_config.getRole()
    set_up_network_interface(specs,role)

@roles('controller')
def controller_network_deploy():

    deployInterface('controller management',env_config.controllerManagement)

    deployInterface('controller tunnels',env_config.controllerTunnels)

    restart_network()
    set_hosts()
    configChrony()
    log_debug('Deployment done on host')

@roles('network')
def network_node_network_deploy():

    deployInterface('network management',env_config.networkManagement)

    deployInterface('network tunnels',env_config.networkTunnels)

    deployInterface('network external',env_config.networkExternal)


    restart_network()
    set_hosts()
    configChrony()
    log_debug('Deployment done on host')

@roles('compute')
def compute_network_deploy():

    deployInterface('compute management',env_config.computeManagement)

    deployInterface('compute tunnels',env_config.computeTunnels)

    restart_network()
    set_hosts()
    configChrony()
    log_debug('Deployment done on host')

@roles('storage')
def storage_network_deploy():

    configChrony()
    
    log_debug('Deployment done on host')

def deploy():
   
    print blue('Ensure that you\'ve run packages installation fabfile first')

    with settings(warn_only=True):
        execute(controller_network_deploy)
        execute(network_node_network_deploy)
        execute(compute_network_deploy)

######################################## TDD #########################################

# pings an ip address and see if it works
def ping_ip(ip_address, host, role='', type_interface=''):
    ping_command = 'ping -q -c 1 ' + ip_address
    result = run_log(ping_command)
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
    base_ip = env_config.networkManagement['IPADDR']
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
    specs_dict = env_config.controllerManagement
    ip_list = [(generate_ip(specs_dict['IPADDR'], env.roledefs['controller'], node), node) for node in env.roledefs['controller']]
    for ip, host in ip_list:
        ping_ip(ip, host, 'controller', 'management')

    # instance tunnel interfaces on compute
    specs_dict = env_config.computeTunnels
    ip_list = [(generate_ip(specs_dict['IPADDR'], env.roledefs['compute'], node), node) for node in env.roledefs['compute']]
    for ip, host in ip_list:
        ping_ip(ip, host, 'compute', 'instance tunnel')

@roles('compute')
def network_tdd_compute():

    # check for connection to internet
    ping_ip('google.ca', 'google.ca')

    # ping management interface on controller nodes
    nodes_in_role = env.roledefs['controller']
    base_ip = env_config.controllerManagement['IPADDR']
    # generage a list of tuples (IP,node) for each controller node
    management_controller_interfaces = [(generate_ip(base_ip, nodes_in_role, node), node) for node in nodes_in_role]
    # ping the management interfaces
    for interface_ip, controller_node in management_controller_interfaces:
        ping_ip(interface_ip, controller_node, 'controller', 'management')

    # ping instance tunnel interface on network nodes
    nodes_in_role = env.roledefs['network']
    base_ip = env_config.networkTunnels['IPADDR']
    # generage a list of tuples (IP,node) for each controller node
    network_tunnels_interfaces = [(generate_ip(base_ip, nodes_in_role, node), node) for node in nodes_in_role]
    # ping the management interfaces
    for interface_ip, network_node in network_tunnels_interfaces:
        ping_ip(interface_ip, network_node, 'network', 'instance tunnel')


@roles('controller')
def chronyTDDController():
    # check if ntp servers are in the sources
    sourcesTable = sudo_log('chronyc sources')
    for server in env_config.ntpServers:
        if server in sourcesTable:
            print green("server {} is a source for chrony".format(server))
        else:
            print red("server {} is not a source for chrony".format(server))

@roles([r for r in env.roledefs.keys() if r != 'controller'])
def chronyTDDOtherNodes():
    # check if controller is in the sources
    sourcesTable = sudo_log('chronyc sources')
    if 'controller' in sourcesTable:
        print green("controller is a source for chrony")
    else:
        print red("controller is not a source for chrony")

def chronyTDD():
    execute(chronyTDDController)
    execute(chronyTDDOtherNodes)

            
def tdd():
    with settings(warn_only=True):
	execute(network_tdd_controller)
	execute(network_tdd_network)
	execute(network_tdd_compute)
	execute(chronyTDD)
