from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.contrib.files import append
import logging
import string

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, createDatabaseScript, set_parameter
from myLib import database_check, keystone_check, run_v, align_n, align_y

############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

glance_api_config_file = "/etc/glance/glance-api.conf"
glance_registry_config_file = "/etc/glance/glance-registry.conf"

######################## Deployment ########################################


def generate_key():
    # http://unix.stackexchange.com/questions/69314/automated-ssh-keygen-without-passphrase-how
#    run("ssh-keygen -b 2048 -t rsa -f ~/.ssh/id_rsa.pub -q -N '' ")
    run("ssh-keygen")
    
    run("nova keypair-add --pub-key ~/.ssh/id_rsa.pub demo-key")

    run("echo $(neutron net-list | awk '/demo-net/ {print $2}')")

    run("echo $(neutron floatingip-create ext-net | awk '/floating_ip_address/ {print $4}')")

def boot_vm():
    run("nova boot --flavor m1.tiny --image cirros-0.3.3-x86_64 "\
    "--nic net-id=$(neutron net-list | awk '/demo-net/ {print $2}') "\
    "--security-group default --key-name demo-key demo-instance1")


def remote_access():
    run("nova secgroup-add-rule default icmp -1 -1 0.0.0.0/0")
    run("nova secgroup-add-rule default tcp 22 22 0.0.0.0/0")

    #run("neutron floatingip-create ext-net")

    run("nova floating-ip-associate demo-instance1 $(neutron floatingip-create ext-net |" \
    "awk '/floating_ip_address/ {print $4}')")


def list_vms():
    run("nova list")
    

   
@roles('controller')
def launch_vm():
    credentials = env_config.demo_openrc
    with prefix(credentials):
        generate_key()
#        boot_vm()
#        remote_access()
#        list_vms()
        
        
################### Deployment ########################################

def deploy():
    execute(launch_vm)

######################################## TDD #########################################

def tdd():
    with settings(warn_only=True):
        pass
