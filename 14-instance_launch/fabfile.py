from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.colors import green, red, blue
import logging
import time

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

def create_image(url, imageName, imageFile, diskFormat):
    msg = 'Retrieve instance image'
    run("mkdir -p /tmp/images")
    runCheck(msg, "wget -P /tmp/images " + url)

    print(blue("Waiting for image file to finish downloading"))
    with settings(warn_only=True):
        while run("ls /tmp/images | grep %s" % imageFile, quiet=True) == '':
            pass    
        msg = 'Create glance image'
        runCheck(msg, "glance image-create --progress " + \
                "--name %s " % imageName + \
                "--file /tmp/images/%s " % imageFile + \
                "--container-format bare " + \
                "--is-public True " + \
                #"--disk-format %s < /tmp/images/%s " % (diskFormat, imageFile)
                "--disk-format %s " % diskFormat
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

def create_volume(imageName, volumeSize, volumeName):
    imageID = run("glance image-list | grep '%s' | awk '{print $2}'" % imageName)
    runCheck('Create a %s GB volume' % volumeSize,
            'cinder create --display-name %s --image_id %s %s' % (
                volumeName, imageID, volumeSize))
   
#def boot_vm(flavorSize, imageName, keyName, instanceName):
def boot_vm(flavorSize, volumeName, keyName, instanceName):
    volumeID = run("nova volume-list | grep '%s' | awk '{print $2}'" % volumeName)
    
    if volumeID != '':
        with settings(warn_only=True):
            print(blue("Waiting for volume to finish building"))
            while run("cinder list | grep %s | grep available" % volumeName, quiet=True) == '':
                pass
 
    netid = run("neutron net-list | awk '/demo-net/ {print $2}'")
    #run("nova boot --flavor m1.%s --image %s " % (flavorSize, imageName) + \
    run("nova boot --flavor m1.%s --boot-volume %s " % (flavorSize, volumeID) + \
    "--nic net-id=%s " % netid + \
    "--security-group default --key-name %s %s" % (keyName, instanceName))
    print(blue("Waiting for instance to finish building"))
    with settings(warn_only=True):
        while run("nova list | grep %s | grep ACTIVE" % instanceName, quiet=True) == '':
            if run("nova list | grep %s | grep ERROR" % instanceName, quiet=True) != '':
                print(red("Major problem: instance can't be made"))
                # Is there a way to stop it here?
                return
    print(green("Instance built!"))
        
@roles('controller')
def adjust_security():
    with settings(warn_only=True):
        runCheck("Edit ICMP security rules", "nova secgroup-add-rule default icmp -1 -1 0.0.0.0/0")
        runCheck("Edit TCP security rules", "nova secgroup-add-rule default tcp 22 22 0.0.0.0/0")

def give_floating_ip(instanceName):

    runCheck("Assign floating ip", "nova floating-ip-associate %s " % instanceName + \
            "$(neutron floatingip-create ext-net | awk '/floating_ip_address/ {print $4}')")

def attach_volume(volumeName, instanceName):
    volumeID = run("nova volume-list | grep '%s' | awk '{print $2}'" % volumeName)
    print(blue('Waiting for instance to finish building'))
    if volumeID != '':
        with settings(warn_only=True):
            while run("nova list | grep %s | grep ACTIVE" % instanceName, quiet=True) == '':
                pass
            print(blue("Waiting for volume to finish building"))
            while run("cinder list | grep %s | grep available" % volumeName, quiet=True) == '':
                pass
    runCheck("Attach volume to instance", "nova volume-attach %s %s auto" % (
                instanceName, volumeID))
    time.sleep(5)

def check_if_volume_attached(instanceName, volumeName):
    if run('nova volume-list | grep %s | grep in-use' % volumeName, warn_only=True) == '':
        print(red("Looks like %s didn't get attached to %s" % (volumeName, instanceName)))
    else:
        print(green('%s successfully attached to %s' % (volumeName, instanceName)))


@roles('controller')
def deploy_cirros():
    credentials = env_config.admin_openrc
    with prefix(credentials):
        generate_key('demo_key')
        create_image(
            'http://download.cirros-cloud.net/0.3.3/cirros-0.3.3-x86_64-disk.img',
            'cirros-test0',
            'cirros-0.3.3-x86_64-disk.img',
            'qcow2')
        create_volume('cirros-test0', '1', 'cirros-volume0')
        boot_vm('tiny', 'cirros-volume0', 'demo_key', 'demo-instance0')
        give_floating_ip('demo-instance0')
        #attach_volume('cirros-volume0', 'demo-instance0')
        #check_if_volume_attached('demo-instance0', 'cirros-volume0')
        #run("nova list")

@roles('controller')
def deploy_windows7():
    with prefix(env_config.admin_openrc):
        #generate_key('demo_key')
        create_image(
            'http://129.128.208.21/public/Microsoft%20Windows/en_windows_7_enterprise_sp1_x86.ISO',
            'windows7-test0',
            'en_windows_7_enterprise_sp1_x86.ISO',
            'iso')
        create_volume('windows7-test0', '75', 'windows7-volume0')
        boot_vm('large', 'windows7-volume0', 'demo_key', 'windows7-instance0')
        give_floating_ip('windows7-instance0')
        #attach_volume('windows7-volume0', 'windows7-instance0')
        #check_if_volume_attached('windows7-instance0', 'windows7-volume0')
        
@roles('controller')
def deploy_ubuntu():
    with prefix(env_config.admin_openrc):
        #generate_key('demo_key')
        create_image(
            'http://releases.ubuntu.com/14.04.2/ubuntu-14.04.2-desktop-amd64.iso',
            'ubuntu-test0',
            'ubuntu-14.04.2-desktop-amd64.iso',
            'qcow2')
        create_volume('ubuntu-test0', '50', 'ubuntu-volume0')
        boot_vm('large', 'ubuntu-volume0', 'demo_key', 'ubuntu-instance0')
        give_floating_ip('ubuntu-instance0')
        #attach_volume('ubuntu-volume0', 'ubuntu-instance0')
        #check_if_volume_attached('ubuntu-instance0', 'ubuntu-volume0')


def deploy():
    execute(adjust_security)
    execute(deploy_cirros)


def destroy_stuff(imageName, volumeName, instanceName):
    runCheck("Delete image", "nova image-delete %s" % imageName)
    runCheck("Delete instance", "nova delete %s" % instanceName)
    #volumeID = run("nova volume-list | grep '%s' | awk '{print $2}'" % volumeName)
    #runCheck("Delete volume", "cinder delete %s" % volumeID)
    #runCheck("Delete image files", "rm -rf /tmp/images")
    
@roles('controller')
def undeploy_cirros():
    credentials = env_config.admin_openrc
    with prefix(credentials):
        destroy_stuff('cirros-test0', 'cirros-volume0', 'demo-instance0')

@roles('controller')
def undeploy_windows7():
    credentials = env_config.admin_openrc
    with prefix(credentials):
        destroy_stuff('windows7-test0', 'windows7-volume0', 'windows7-instance0')

@roles('controller')
def undeploy_ubuntu():
    credentials = env_config.admin_openrc
    with prefix(credentials):
        destroy_stuff('ubuntu-test0', 'ubuntu-volume0', 'ubuntu-instance0')

