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

def key_exists():
    # checks for existence of /root/.ssh/id_rsa
    ls_utput = run("ls /root/.ssh")
    if "id_rsa" in ls_utput:
        return True
    else:
        return False

def generate_key(keyName):
    if key_exists() == False:
        runCheck("generate keygen", "ssh-keygen")

    if runCheck("check for nova keypair","nova keypair-list | awk '/%s/'" % keyName) == "":
        runCheck("Add keypair", "nova keypair-add --pub-key ~/.ssh/id_rsa.pub %s" % keyName)
        
    
def image_active(image):
    with prefix(env_config.admin_openrc):
        imageStatus = runCheck("check if %s exists" % image, "glance image-list | awk '/" + image + "/ {print $12}'")
        
        if imageStatus == "active":
            return True
        else:
            return False
            
def delete_image(image_to_delete):
    # delete image given image name
    # assumes only one image with name
    # image_to_delete exists
    # otherwise, functions needs image id
    with prefix(env_config.admin_openrc):
        runCheck("delete %s" % image,"glance delete %s" % image_to_delete)

def create_image(url, imageName, imageFile, diskFormat):
    if image_active(imageName):
        return
    
    msg = 'Retrieve instance image'
    run("mkdir -p /tmp/images")
    with settings(warn_only=True):
        if run("ls /tmp/images | grep %s" % imageFile, quiet=True) == '':
            runCheck(msg, "wget -P /tmp/images " + url)

            print(blue("Waiting for image file to finish downloading"))
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

def create_volume(volumeSize, volumeName):
    runCheck('Create a %s GB volume' % volumeSize,
            'cinder create --display-name %s %s' % (volumeName, volumeSize))
 
def create_bootable_volume(imageName, volumeSize, volumeName):
    imageID = run("glance image-list | grep '%s' | awk '{print $2}'" % imageName)
    runCheck('Create a %s GB volume' % volumeSize,
            'cinder create --display-name %s --image_id %s %s' % (
                volumeName, imageID, volumeSize))
   
#def boot_vm(flavorSize, imageName, keyName, instanceName):
def boot_from_volume(flavorSize, volumeName, keyName, instanceName):
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
                sys.exit("Major problem: instance can't be made")
    print(green("Instance built!"))
        
#def boot_vm(flavorSize, imageName, keyName, instanceName):
def boot_from_image(volumeName, flavorSize, imageName, keyName, instanceName):
    volumeID = run("nova volume-list | grep '%s' | awk '{print $2}'" % volumeName)
    
    if volumeID != '':
        with settings(warn_only=True):
            print(blue("Waiting for volume to finish building"))
            while run("cinder list | grep %s | grep available" % volumeName, quiet=True) == '':
                pass
 
    netid = run("neutron net-list | awk '/demo-net/ {print $2}'")
    run("nova boot --flavor m1.%s --image %s " % (flavorSize, imageName) + \
    "--nic net-id=%s " % netid + \
    "--block-device source=volume,id=%s,dest=volume,bus=virtio " % volumeID + \
    "--security-group default --key-name %s %s" % (keyName, instanceName))
    print(blue("Waiting for instance to finish building"))
    with settings(warn_only=True):
        while run("nova list | grep %s | grep ACTIVE" % instanceName, quiet=True) == '':
            if run("nova list | grep %s | grep ERROR" % instanceName, quiet=True) != '':
                sys.exit("Major problem: instance can't be made")
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
    #with prefix(env_config.admin_openrc):
        #create_image(
        #    'http://download.cirros-cloud.net/0.3.3/cirros-0.3.3-x86_64-disk.img',
        #    'cirros-test0',
        #    'cirros-0.3.3-x86_64-disk.img',
        #    'qcow2')
    with prefix(env_config.demo_openrc):
        generate_key('demo-key')
        #create_bootable_volume('cirros-test0', '10', 'cirros-volume0')
        boot_from_volume('small', 'cirros-volume0', 'demo-key', 'demo-instance0')
        give_floating_ip('demo-instance0')
        #attach_volume('cirros-volume0', 'demo-instance0')
        #check_if_volume_attached('demo-instance0', 'cirros-volume0')
        #run("nova list")

@roles('controller')
def deploy_windows7():
    with prefix(env_config.admin_openrc):
        #generate_key('demo-key')
        create_image(
            'http://129.128.208.21/public/Microsoft%20Windows/en_windows_7_enterprise_sp1_x86.ISO',
            'windows7-test0',
            'win7.qcow2',
            'qcow2')
    with prefix(env_config.demo_openrc):
        create_bootable_volume('windows7-test0', '75', 'windows7-volume0')
        boot_from_volume('large', 'windows7-volume0', 'demo-key', 'windows7-instance0')
        give_floating_ip('windows7-instance0')
        #attach_volume('windows7-volume0', 'windows7-instance0')
        #check_if_volume_attached('windows7-instance0', 'windows7-volume0')
        
@roles('controller')
def deploy_ubuntu():
    with prefix(env_config.admin_openrc):
        #generate_key('demo-key')
        create_image(
            'http://releases.ubuntu.com/14.04.2/ubuntu-14.04.2-desktop-amd64.iso',
            'ubuntu-test0',
            'ubuntu-14.04.2-desktop-amd64.iso',
            'qcow2')
    with prefix(env_config.demo_openrc):
        create_bootable_volume('ubuntu-test0', '50', 'ubuntu-volume0')
        boot_from_volume('large', 'ubuntu-volume0', 'demo-key', 'ubuntu-instance0')
        give_floating_ip('ubuntu-instance0')
        #attach_volume('ubuntu-volume0', 'ubuntu-instance0')
        #check_if_volume_attached('ubuntu-instance0', 'ubuntu-volume0')

@roles('controller')
def deploy_centos_start():
    #with prefix(env_config.admin_openrc):
        #create_image(
        #    'http://centos.mirror.netelligent.ca/centos/7/isos/x86_64/CentOS-7-x86_64-Minimal-1503-01.iso',
        #    'centos-7-x86_64_minimal_iso',
        #    'CentOS-7-x86_64-Minimal-1503-01.iso',
        #    'iso')
    with prefix(env_config.demo_openrc):
        generate_key('demo-key')
        #create_volume('10', 'centos-7-minimal')
        boot_from_image('centos-7-minimal', 
                        'small', 
                        'centos-7-x86_64_minimal_iso', 
                        'demo-key', 
                        'centos-instance0')
        give_floating_ip('centos-instance0')
    
@roles('controller')
def deploy_centos_end():
    with prefix(env_config.demo_openrc):
        runCheck('Get rid of old instance', 'nova delete centos-instance0')
        runCheck('Make volume bootable', 'cinder set-bootable centos-7-minimal true')
        boot_from_volume('small', 'centos-7-minimal', 'demo-key', 'centos-volume-instance')

def deploy():
    execute(adjust_security)
    execute(deploy_cirros)


def destroy_stuff(imageName, volumeName, instanceName):
    with prefix(env_config.admin_openrc):
        runCheck("Delete image", "nova image-delete %s" % imageName)
    with prefix(env_config.demo_openrc):
        runCheck("Delete instance", "nova delete %s" % instanceName)
        volumeID = run("nova volume-list | grep '%s' | awk '{print $2}'" % volumeName)
        runCheck("Delete volume", "cinder delete %s" % volumeID)
        #runCheck("Delete image files", "rm -rf /tmp/images")
    
@roles('controller')
def undeploy_cirros():
    destroy_stuff('cirros-test0', 'cirros-volume0', 'demo-instance0')

@roles('controller')
def undeploy_windows7():
    destroy_stuff('windows7-test0', 'windows7-volume0', 'windows7-instance0')

@roles('controller')
def undeploy_ubuntu():
    destroy_stuff('ubuntu-test0', 'ubuntu-volume0', 'ubuntu-instance0')

