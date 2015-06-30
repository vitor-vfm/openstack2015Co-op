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
sys.path.append('..')
import env_config
from myLib import runCheck, getRole


############################ Config ########################################

env.roledefs = env_config.roledefs

mode = 'normal'
if output['debug']:
    mode = 'debug'

################### General functions ########################################

def debug_str(command):
    # runs a command and returns its output in blue
    return blue(sudo(command,quiet=True))

def generate_ip(ip_address,nodes_in_role,node):
    # generate an IP address based on a base ip, a node, and a role list
    # will be used for setting up interfaces and for testing

    # split the IP into its four octets
    octets = ip_address.split('.')

    # increment last octet according to the node's index in the 
    # nodes_in_role list; 
    index = nodes_in_role.index(node)
    octets[-1] = str( int(octets[-1]) + index )

    # turn it back into a single string
    ip_address = ".".join(octets)
    return ip_address


########################## Deployment ########################################

def set_up_NIC_using_nmcli(specs_dict):
    """
    Set up a new interface by using NetworkManager's command line interface

    We don't use this currently, but we keep this function in case we need it
    """

    ifname = specs_dict['DEVICE']
    ip = specs_dict['IPADDR']
    # ifname = sudo("crudini --get {} '' DEVICE".format(conf_file))
    # ip = sudo("crudini --get {} '' IPADDR".format(conf_file))

    command = "nmcli connection add type ethernet"
    command += " con-name " + ifname # connection name == interface name
    command += " ifname " + ifname
    command += " ip4 " + ip

    msg = "Set up a new NIC with name {} and IP {}".format(ifname,ip)
    runCheck(msg, command)


# General function to restart network
def restart_network():
    # restarting network to implement changes 

    msg = "Restart network service"
    runCheck(msg, 'systemctl restart network')

# General function to set a virtual NIC
def set_up_network_interface(specs_dict,role):

    if 'IPADDR' in specs_dict:
        # change the IP in the dict for the correct one
        specs_dict['IPADDR'] = generate_ip(specs_dict['IPADDR'],
                env.roledefs[role], env.host_string)
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
        msg = 'Set up NIC with conf file {}'.format(config_file_name)
        runCheck(msg, 'echo -e "{}" >{}'.format(config_file,config_file_name))

        if mode == 'debug':
            print blue('This is the test config file: \n')
            print debug_str('cat ' + config_file_name +'\n')
            print blue('These are the ifcfg files in the directory: ')
            print debug_str('ls | grep ifcfg')
            print 'Deleting test file'
            print debug_str('rm ' + config_file_name)

def configChrony():

    # Install Chrony
    run('yum -y install chrony')


    chrony_conf = ''
    if getRole() == 'controller':
        # reference the ntp servers
        for server in env_config.ntpServers:
            chrony_conf += "server {} iburst\n".format(server)
    else:
        # reference the controller node
        chrony_conf += "server controller iburst\n"

    confFile = '/etc/chrony.conf'
    # make a backup
    sudo('cp {} {}.back12'.format(confFile,confFile))

    if mode == 'debug':
        confFile += '.back12'

    with settings(warn_only=True):
        msg = 'Add NTP server to ' + confFile
        runCheck(msg, "echo '{}' > {}".format(chrony_conf,confFile))

        if mode == 'debug':
            print blue('This is what the conf file will look like: ')
            print blue(sudo('cat ' + confFile,quiet=True))

        msg = 'Restart Chrony service'
        runCheck(msg, 'systemctl restart chronyd.service')

    # enable Chrony
    msg = 'Enable Chrony service'
    runCheck(msg, 'systemctl enable chronyd.service')
    msg = 'Start Chrony service'
    runCheck(msg, 'systemctl start chronyd.service')

def deployInterface(interface,specs):
    if mode == 'debug':
        print ''
        print blue('Deploying Interface {} now'.format(interface))
        print ''

    role = getRole()
    set_up_network_interface(specs,role)

def installChrony():
    """
    Install and Configure the Chrony NTP service
    """

    execute(configChrony,roles=['controller'])
    execute(configChrony,roles=['network'])
    execute(configChrony,roles=['compute'])
    execute(configChrony,roles=['storage'])

@roles('controller')
def controller_network_deploy():

    deployInterface('controller management',env_config.controllerManagement)

    deployInterface('controller tunnels',env_config.controllerTunnels)

    restart_network()
    logging.debug('Deployment done on host' + env.host_string)

@roles('network')
def network_node_network_deploy():

    deployInterface('network management',env_config.networkManagement)

    deployInterface('network tunnels',env_config.networkTunnels)

    deployInterface('network external',env_config.networkExternal)


    restart_network()
    logging.debug('Deployment done on host' + env.host)

@roles('compute')
def compute_network_deploy():

    deployInterface('compute management',env_config.computeManagement)

    deployInterface('compute tunnels',env_config.computeTunnels)

    restart_network()
    logging.debug('Deployment done on host' + env.host)

@roles('storage')
def storage_network_deploy():

    deployInterface('storage management',env_config.storageManagement)
    
    restart_network()
    logging.debug('Deployment done on host' + env.host)

def deploy():
   
    print blue('Ensure that you\'ve run packages installation fabfile first')

    with settings(warn_only=True):
        execute(controller_network_deploy)
        execute(network_node_network_deploy)
        execute(compute_network_deploy)
        execute(storage_network_deploy)

################################ TDD #########################################

@roles('controller')
def controller_tdd():

    pings = [
            ('google', 'google.ca'),
            ('8.8.8.8', '8.8.8.8'),
            ('management interface on network node', env_config.networkManagement['IPADDR']),
            ('management interface on compute node', env_config.computeManagement['IPADDR']),
            ]

    for name, address in pings:
        msg = 'Ping %s from %s' % (name, env.host)
        runCheck(msg, 'ping -c 1 %s' % address) 

@roles('network')
def network_tdd():

    pings = [
            ('google', 'google.ca'),
            ('8.8.8.8', '8.8.8.8'),
            ('management interface on controller node', env_config.controllerManagement['IPADDR']),
            ('instance tunnels interface on compute node', env_config.computeTunnels['IPADDR']),
            ]

    for name, address in pings:
        msg = 'Ping %s from %s' % (name, env.host)
        runCheck(msg, 'ping -c 1 %s' % address) 

@roles('compute')
def compute_tdd():

    pings = [
            ('google', 'google.ca'),
            ('8.8.8.8', '8.8.8.8'),
            ('management interface on controller node', env_config.controllerManagement['IPADDR']),
            ('instance tunnels interface on network node', env_config.networkTunnels['IPADDR']),
            ]

    for name, address in pings:
        msg = 'Ping %s from %s' % (name, env.host)
        runCheck(msg, 'ping -c 1 %s' % address) 

@roles('storage')
def storage_tdd():
    # see if the storage node can ping all the management interfaces
    hostsToPing = [
            "controller",
            "network",
            "compute1",
            "storage1",
            ]

    for host in hostsToPing:
        msg = 'Ping %s from %s' % (host, env.host)
        runCheck(msg, 'ping -c 1 %s' % host)  

def tdd():
    with settings(warn_only=True):
        execute(controller_tdd)
        execute(network_tdd)
        execute(compute_tdd)
        execute(storage_tdd)
