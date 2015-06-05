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


############################ Config ########################################

env.roledefs = env_config.roledefs

mode = 'normal'
if output['debug']:
    mode = 'debug'

# Get configuration dictionaries from the config files
# compute_tunnels = env_config.read_dict('config_files/compute_instance_tunnels_interface_config')
# compute_manage = env_config.read_dict('config_files/compute_management_interface_config')
# controller_manage = env_config.read_dict('config_files/controller_management_interface_config')
# network_ext = env_config.read_dict('config_files/network_node_external_interface_config')
# network_tunnels = env_config.read_dict('config_files/network_node_instance_tunnels_interface_config')
# network_manage = env_config.read_dict('config_files/network_node_management_interface_config')
# hosts_config = 'config_files/hosts_config'



# determine config file from local host

hostname = local("echo $HOSTNAME",capture=True)
if 'ipmi5' in hostname:
    main_config = 'config_files/production_config.cfg'
else:
    main_config = 'config_files/development_config.cfg'




# Logging config

log_file = 'basic-network.log'
env_config.setupLoggingInFabfile(log_file)
log_dict = {'host_string':'','role':''}

# Do a fabric run on the string 'command' and log results
run_log = lambda command : env_config.fabricLog(command,run,log_dict)
# Do a fabric sudo on the string 'command' and log results
sudo_log = lambda command : env_config.fabricLog(command,sudo,log_dict)

################### General functions ########################################

def read_dict_local(section):
    # parse main config file and return all the 
    # variables in the given section in a dictionary

    # save config file in a ConfigParser object
    parser = ConfigParser.ConfigParser()
    parser.read(main_config)

    # read variables and their values into a list of tuples
    name_value_pairs = parser.items(section)

    # return those pairs in a dictionary
    # ConfigParser puts all the letters in lowercase,
    # so we need to change them back to upper
    return {name.upper():value for name,value in name_value_pairs}

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
    # change to network-scripts directory
    with cd('/etc/sysconfig/network-scripts'):
        # create ifcfg file in the directory
        sudo_log('echo -e "{}" >ifcfg-{}'.format(config_file,device_name))

    logging.debug('Set up virtual NIC with name {}'.format(device_name),extra=log_dict)

def set_hosts():
    # configure the /etc/hosts file to put aliases
    aliases = read_dict_local('hosts')

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

    with settings(warn_only=True):
        run_log("echo '%s' > /etc/chrony.conf" % chrony_conf)

        run_log('systemctl restart chronyd.service')
        result=run_log('systemctl is-enabled chronyd.service')
        if result.failed :
            print "Chrony config failed"
        else:
            print "Chrony config OK"

def configureNTP():

    confFile = '/etc/ntp.conf'
    newLine = 'server controller iburst'

    # check if file has been configured already
    confFileStr = sudo("cat " + confFile,warn_only=True,quiet=True)
    # if int(sudo_log("grep -c '{}' {}".format(newLine,confFile))) == 0:
    if newLine not in confFileStr:

        # make a backup
        sudo_log('cp {} {}.back12'.format(confFile,confFile))

        # comment out all server keys
        sudo_log("sed -iE '/^server/ s/^/#/' " + confFile)

        # add one server key to reference the controller node
        sudo_log("echo '{}' >>{}".format(newLine,confFile))
    else:
        message = 'NTP conf file has already been set. Nothing done'
        print message
        logging.debug(message,extra=log_dict)

    # enable and start ntp service
    sudo_log("systemctl enable ntpd.service")
    sudo_log("systemctl start ntpd.service")

def configureNTP_on_controller():


    NTP_SERVERS = ["195.43.74.123", "206.108.0.131", "206.108.0.132"]
    NTP_SERVERS_HOSTNAME = ["ntp.amnic.net","ntp1.torix.ca","ntp2.torix.ca"]
    confFile = '/etc/ntp.conf'


    logging.debug("Making sure we have ntp",extra=log_dict)
    sudo_log('yum -y install ntp')

    # check if file has been configured already
    confFileStr = sudo("cat " + confFile,warn_only=True,quiet=True)
    ipToCheck = NTP_SERVERS[0]
    if ipToCheck in confFileStr:
        message = 'NTP conf file has already been set. Nothing done'
        print message
        logging.debug(message,extra=log_dict)
        return

    # make a backup
    sudo_log('cp {} {}.back12'.format(confFile,confFile))

    # comment out all server keys
    sudo_log("sed -iE '/^server/ s/^/#/' " + confFile)

    # add one server key to reference the controller node

    linesToAdd = ["restrict -4 default kod notrap nomodify","restrict -6 default kod notrap nomodify"]
    append(confFile,linesToAdd,use_sudo=True)

    for NTP_SERVER in NTP_SERVERS:
        sudo_log("echo '{}' >>{}".format("server {} iburst".format(NTP_SERVER),confFile))

    sudo("cat " + confFile)
    # enable and start ntp service
    sudo_log("systemctl enable ntpd.service")
    sudo_log("systemctl start ntpd.service")


@roles('controller')
def controller_network_deploy():
    # create log dictionary (to set up the log formatting)
    global log_dict
    log_dict = {'host_string':env.host_string,'role':env_config.getRole()}

    specs = read_dict_local('controller management')
    set_up_network_interface(specs,env_config.getRole())

    specs = read_dict_local('controller tunnels')
    set_up_network_interface(specs,env_config.getRole())

    restart_network()
    set_hosts()
    configChrony()
    logging.debug('Deployment done on host',extra=log_dict)

@roles('network')
def network_node_network_deploy():
    # create log dictionary (to set up the log formatting)
    global log_dict
    log_dict = {'host_string':env.host_string,'role':'network'}

    specs = read_dict_local('network management')
    set_up_network_interface(specs,env_config.getRole())

    specs = read_dict_local('network tunnels')
    set_up_network_interface(specs,env_config.getRole())

    specs = read_dict_local('network external')
    set_up_network_interface(specs,env_config.getRole())


    restart_network()
    set_hosts()
    configChrony()
    logging.debug('Deployment done on host',extra=log_dict)

@roles('compute')
def compute_network_deploy():
    # create log dictionary (to set up the log formatting)
    global log_dict
    log_dict = {'host_string':env.host_string,'role':'compute'}

    specs = read_dict_local('compute management')
    set_up_network_interface(specs,env_config.getRole())

    specs = read_dict_local('compute tunnels')
    set_up_network_interface(specs,env_config.getRole())

    restart_network()
    set_hosts()
    configChrony()
    logging.debug('Deployment done on host',extra=log_dict)

@roles('storage')
def storage_network_deploy():
    # create log dictionary (to set up the log formatting)
    global log_dict
    log_dict = {'host_string':env.host_string,'role':'compute'}

    configChrony()
    
    logging.debug('Deployment done on host',extra=log_dict)

def deploy():
    # create log dictionary (to set up the log formatting)
    log_dict = {'host_string':'','role':''}
    logging.debug('Starting deployment',extra=log_dict)
   
    print blue('Ensure that you\'ve run packages installation fabfile first')

    with settings(warn_only=True):
        execute(controller_network_deploy)
        execute(network_node_network_deploy)
        execute(compute_network_deploy)

######################################## TDD #########################################

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
        print red("controlles is not a source for chrony")




def chronyTDD():
    execute(chronyTDDController)
    execute(chronyTDDOtherNodes)

    

def controller_ntp_tdd_part1():

    # this repeats, we need to make it proper
    NTP_SERVERS = ["195.43.74.123", "206.108.0.131", "206.108.0.132"]
    NTP_SERVERS_HOSTNAME = ["ntp.amnic.net","ntp1.torix.ca","ntp2.torix.ca"]

    for NTP_SERVER in NTP_SERVERS:
        if NTP_SERVER in sudo_log("ntpq -c peers"):
            print(green("Found ntp server in column 'remote'"))
            return

    for NTP_SERVER_HOSTNAME in NTP_SERVERS_HOSTNAME:
        if NTP_SERVER_HOSTNAME in sudo_log("ntpq -c peers"):
            print(green("Found ntp server hostname in column 'remote'"))
            return

    
    print(red("Didnt find ntp server in column 'remote'"))
    print("Try waiting for sync")


def controller_ntp_tdd_part2():


    if "sys_peer" in sudo_log("ntpq -c assoc"):
        print(green("Found sys_peer"))
        return
    
    print(red("Didnt find sys_peer"))
    print("Try waiting for sync")

@roles('controller')
def controller_ntp_tdd():
    controller_ntp_tdd_part1()
    controller_ntp_tdd_part2()


def other_nodes_ntp_tdd_part1():
    if "controller" in sudo_log("ntpq -c peers"):
        print(green("Found controller in column 'remote'"))
        return
    
    print(red("Didnt find controller in column 'remote'"))
    print("Try waiting for sync")


def other_nodes_ntp_tdd_part2():
    if "sys_peer" in sudo_log("ntpq -c assoc"):
        print(green("Found sys_peer"))
        return
    
    print(red("Didnt find sys_peer"))
    print("Try waiting for sync")

@roles('network','compute')
def other_nodes_ntp_tdd():
    other_nodes_ntp_tdd_part1()
    other_nodes_ntp_tdd_part2()
        
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
    # create log dictionary (to set up the log formatting)
    global log_dict
    log_dict = {'host_string':env.host_string,'role':'controller'}

    # ping a website
    ping_ip('www.google.ca','google.ca')

    # ping management interface on network nodes
    nodes_in_role = env.roledefs['network']
    base_ip = read_dict_local('network management')['IPADDR']
    # generate a list of tuples (IP,node) for each network node
    management_network_interfaces = [( generate_ip(base_ip,nodes_in_role,node) ,node) for node in nodes_in_role]
    # ping the management interfaces
    for interface_ip, network_node in management_network_interfaces:
        ping_ip(interface_ip, network_node, 'network', 'management')

@roles('network')
def network_tdd_network():
    # create log dictionary (to set up the log formatting)
    global log_dict
    log_dict = {'host_string':env.host_string,'role':'network'}

    # needs to ping management interface(s) on controller node(s)
    # and instance tunnels interface(s) on compute node(s)

    # check for connection to internet
    ping_ip('google.ca', 'google.ca')

    # management interfaces on controller
    specs_dict = read_dict_local('controller management')
    ip_list = [(generate_ip(specs_dict['IPADDR'], env.roledefs['controller'], node), node) for node in env.roledefs['controller']]
    for ip, host in ip_list:
        ping_ip(ip, host, 'controller', 'management')

    # instance tunnel interfaces on compute
    specs_dict = read_dict_local('compute tunnels')
    ip_list = [(generate_ip(specs_dict['IPADDR'], env.roledefs['compute'], node), node) for node in env.roledefs['compute']]
    for ip, host in ip_list:
        ping_ip(ip, host, 'compute', 'instance tunnel')

@roles('compute')
def network_tdd_compute():
    # create log dictionary (to set up the log formatting)
    global log_dict
    log_dict = {'host_string':env.host_string,'role':'compute'}

    # check for connection to internet
    ping_ip('google.ca', 'google.ca')

    # ping management interface on controller nodes
    nodes_in_role = env.roledefs['controller']
    base_ip = read_dict_local('controller management')['IPADDR']
    # generage a list of tuples (IP,node) for each controller node
    management_controller_interfaces = [(generate_ip(base_ip, nodes_in_role, node), node) for node in nodes_in_role]
    # ping the management interfaces
    for interface_ip, controller_node in management_controller_interfaces:
        ping_ip(interface_ip, controller_node, 'controller', 'management')

    # ping instance tunnel interface on network nodes
    nodes_in_role = env.roledefs['network']
    base_ip = read_dict_local('network tunnels')['IPADDR']
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
	execute(chronyTDD)
