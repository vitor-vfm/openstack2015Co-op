from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
import logging

import sys
sys.path.append('..')
import env_config
from myLib import runCheck

###################################### Config ########################################

env.roledefs = env_config.roledefs

################################## Deployment ########################################


def generate_key():
    # http://unix.stackexchange.com/questions/69314/automated-ssh-keygen-without-passphrase-how
    
#    run("ssh-keygen -b 2048 -t rsa -f ~/.ssh/id_rsa.pub -q -N '' ")
    run("ssh-keygen")
    
    run("nova keypair-add --pub-key ~/.ssh/id_rsa.pub demo-key")

def boot_vm():
    # Assumes cirros-test has been created

    netid = run("neutron net-list | awk '/demo-net/ {print $2}'")
    run("nova boot --flavor m1.tiny --image cirros-test "\
    "--nic net-id=%s " % netid + \
    "--security-group default --key-name demo-key demo-instance1")


def remote_access():

    with settings(warn_only=True):
        run("nova secgroup-add-rule default icmp -1 -1 0.0.0.0/0")
        run("nova secgroup-add-rule default tcp 22 22 0.0.0.0/0")

    run("nova floating-ip-associate demo-instance1 $(neutron floatingip-create ext-net |"
            "awk '/floating_ip_address/ {print $4}')")


@roles('controller')
def deploy():
    credentials = env_config.admin_openrc
    with prefix(credentials):
        generate_key()
        boot_vm()
        remote_access()
        run("nova list")

######################################## TDD #########################################

def tdd():
    with settings(warn_only=True):
        pass
