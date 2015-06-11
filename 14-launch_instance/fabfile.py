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
sys.path.append('..')
import env_config
from myLib import *


############################ Config ########################################

env.roledefs = env_config.roledefs

mode = 'normal'
if output['debug']:
    mode = 'debug'

# demo user credentials 
demoCred = env_config.demo_openrc

################### Deployment ########################################

@roles('controller')
def launchDemoInstance():
    # Launches an instance called demo-instance1 for testing purposes

    # get user credentials
    with prefix(demoCred):
        run('ssh-keygen') # how to do this with fabric?

        msg = 'Add host\'s public key to the OpenStack environment'
        runCheck(msg, 'nova keypair-add --pub-key ~/.ssh/id_rsa.pub demo-key')

        msg = 'Get the net ID for demo-net'
        demoNetID = runCheck(msg, "neutron net-list | awk '/demo-net/ {print $2}'")

        msg = 'Launch demo-instance1 instance'
        runCheck(msg, 'nova boot --flavor m1.tiny --image cirros-0.3.3-x86_64 --nic net-id=' + demoNetID \
                + ' --security-group default --key-name demo-key demo-instance1')

@roles('controller')
def enableRemoteAccess():
    # sets up remote access to the demo instance so that you can ssh into it
    demoInstanceName = 'demo-instance1'

    # get user credentials
    with prefix(demoCred):
        msg = 'Permit ICMP (ping)'
        runCheck(msg, "nova secgroup-add-rule default icmp -1 -1 0.0.0.0/0")

        msg = 'Permit secure shell (SSH) access'
        runCheck(msg, "nova secgroup-add-rule default tcp 22 22 0.0.0.0/0")

        # This assumes that the ext-net network exists
        # That's the external network created by the createInitialNetwork function
        # on the neutron deployment fabfile
        msg = 'Create a floating IP address on the ext-net external network'
        runCheck = (msg, "neutron floatingip-create ext-net")

        msg = 'Grab floating IP'
        floatingIP = runCheck(msg, "nova list | awk '/%s/ {print $13}'" % demoInstanceName)

        print 'The instance\'s floating IP is ' + floatingIP

def deploy():
    execute(launchDemoInstance)
    execute(enableRemoteAccess)

######################################## TDD #########################################

# pings an ip address and see if it works

@roles('controller')
def checkInstanceStatus():
    # verify if the the demo instance exists and is active
    demoInstanceName = 'demo-instance1' 

    # get user credentials
    with prefix(demoCred):
        msg = 'verify demo instance\'s existence'
        out = runCheck(msg, "nova list | grep " + demoInstanceName)

        if out.return_code != 0:
            print red('Demo instance is not there!')
            return
        else:
            msg = 'verify demo instance\'s status'
            instanceStatus = runCheck(msg, "nova list | awk '/%s/ {print $6}'" % demoInstanceName)

            print blue('The instance\'s status is ' + instanceStatus)

@roles('controller')
def pingfloatingIP():
    # ping the new instance's floating IP
    # and check if it's responsive
    demoInstanceName = 'demo-instance1' 

    # get user credentials
    with prefix(demoCred):
        msg = 'Grab floating IP'
        floatingIP = runCheck(msg, "nova list | awk '/%s/ {print $13}'" % demoInstanceName)

        msg = 'Ping floating IP'
        runCheck(msg, "ping -c 1 " + floatingIP)

def tdd():
    with settings(warn_only=True):
	execute(checkInstanceStatus)
	execute(pingfloatingIP)
