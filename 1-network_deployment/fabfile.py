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
nicDictionary = env_config.nicDictionary

mode = 'normal'
if output['debug']:
    mode = 'debug'

################### General functions ########################################

def debug_str(command):
    # runs a command and returns its output in blue
    return blue(sudo(command,quiet=True))

########################## Deployment ########################################
@roles('controller','compute','network', 'storage')
def deployNIC():
    config_file = ''
    if (nicDictionary[env.host]['tnlDEVICE']!=''):
        config_file += "DEVICE=" +nicDictionary[env.host]['tnlDEVICE'] + '\n'
        config_file += "IPADDR=" +nicDictionary[env.host]['tnlIPADDR'] + '\n'
        config_file += "NETMASK=" +nicDictionary[env.host]['tnlNETMASK'] + '\n'
        config_file_name = '/etc/sysconfig/network-scripts/ifcfg-' + nicDictionary[env.host]['tnlDEVICE']
        msg = 'Set up NIC with conf file %s' % nicDictionary[env.host]['tnlDEVICE']
        runCheck(msg, 'echo -e "%s" > %s' % (config_file,config_file_name))
        msg = "Restart network service"
        runCheck(msg, 'systemctl restart network')

def deploy():
    execute(deployNIC)

################################ TDD #########################################

@roles('controller','compute','network', 'storage')
def tdd():

    pings = [
            ('google', 'google.ca'),
            ('8.8.8.8', '8.8.8.8'),
            ('tunnel interface on network node', nicDictionary['network']['tnlIPADDR']),
            ('management interface on controller node', nicDictionary['controller']['mgtIPADDR']),
            ]

    for name, address in pings:
        msg = 'Ping %s from %s' % (name, env.host)
        runCheck(msg, 'ping -c 1 %s' % address) 


