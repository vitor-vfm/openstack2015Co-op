from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.colors import green, red
import logging

import sys
sys.path.append('..')
import env_config
from myLib import runCheck

###################################### Config ########################################

env.roledefs = env_config.roledefs

################################## Deployment ########################################


def generate_key(keyName):
    # http://unix.stackexchange.com/questions/69314/automated-ssh-keygen-without-passphrase-how
    
#    run("ssh-keygen -b 2048 -t rsa -f ~/.ssh/id_rsa.pub -q -N '' ")
    runCheck("Generate keys", "ssh-keygen")
    
    runCheck("Add keypair", "nova keypair-add --pub-key ~/.ssh/id_rsa.pub %s" % keyName)

def create_image(url, imageName, imageFile):
    msg = 'Retrieve instance image'
    run("mkdir -p /tmp/images")
    runCheck(msg, "wget -qP /tmp/images " + url)

    with prefix(env_config.admin_openrc):

        msg = 'Create glance image'
        runCheck(msg, "glance image-create --name '%s' " % imageName + \
                "--file /tmp/images/'%s' " % imageFile + \
                "--disk-format qcow2 " + \
                "--container-format bare " + \
                "--is-public True "
                )

        msg = 'List images'
        output = runCheck(msg, "glance image-list | grep '%s'" % imageName)
        # imageIDs = [l.split()[1] for l in output.splitlines() if 'cirros-test' in l]
        imageID = run("glance image-list | grep '%s' | awk '{print $2}'" % imageName)

        if len(output.splitlines()) > 1:
            print(red("There seems to be more than one '%s'!" % imageName))
            return 'FAIL'

        if output:
            print(green("Successfully installed image"))
        else:
            print(red("Couldn't install image"))
            return 'FAIL'
    
def boot_vm(flavorSize, imageName, keyName, instanceName):
    # Assumes cirros-test has been created

    netid = run("neutron net-list | awk '/demo-net/ {print $2}'")
    run("nova boot --flavor m1.%s --image %s " % (flavorSize, imageName) + \
    "--nic net-id=%s " % netid + \
    "--security-group default --key-name %s %s" % (keyName, instanceName))

@roles('controller')
def adjust_security():
    credentials = env_config.admin_openrc
    with settings(warn_only=True):
        with prefix(credentials):
            runCheck("Edit ICMP security rules", "nova secgroup-add-rule default icmp -1 -1 0.0.0.0/0")
            runCheck("Edit TCP security rules", "nova secgroup-add-rule default tcp 22 22 0.0.0.0/0")

def give_floating_ip(instanceName):

    runCheck("Assign floating ip", "nova floating-ip-associate %s " % instanceName + \
            "$(neutron floatingip-create ext-net | awk '/floating_ip_address/ {print $4}')")

def create_volume(imageName, volumeSize, volumeName):
    imageID = run("glance image-list | grep '%s' | awk '{print $2}'" % imageName)
    with prefix(env_config.demo_openrc):
        runCheck('Create a %s GB volume' % volumeSize,
                'cinder create --display-name %s --image_id %s %s' % (
                    volumeName, imageID, volumeSize))

def attach_volume(volumeName, instanceName):
    with prefix(env_config.demo_openrc):
        volumeID = run("nova volume-list | grep '%s' | awk '{print $2}'" % volumeName)
        runCheck("Attach volume to instance", "nova volume-attach %s %s" % (
                    instanceName, volumeID))

def check_if_volume_attached(instanceName, volumeName):
    with prefix(env_config.demo_openrc):
        if run('nova volume-list | grep %s | grep in-use' % instanceName, warn_only=True) == '':
            print(red("Looks like %s didn't get attached to %s" % (volumeName, instanceName)))
        else:
            print(green('%s successfully attached to %s' % (volumeName, instanceName)))


@roles('controller')
def deploy_cirros():
    credentials = env_config.admin_openrc
    with prefix(credentials):
        #generate_key('demo_key')
        create_image(
            'http://download.cirros-cloud.net/0.3.3/cirros-0.3.3-x86_64-disk.img',
            'cirros-test3',
            'cirros-0.3.3-x86_64-disk.img')
        boot_vm('tiny', 'cirros-test3', 'demo_key', 'demo-instance2')
        give_floating_ip('demo-instance2')
        create_volume('cirros-test3', '1', 'cirros-volume2')
        attach_volume('cirros-volume2', 'demo-instance2')
        check_if_volume_attached('demo-instance2', 'cirros-volume2')
        #run("nova list")

def deploy():
    execute(adjust_security)
    execute(deploy_cirros)
