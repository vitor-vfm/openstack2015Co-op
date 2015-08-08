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
    ls_output = run("ls /root/.ssh")
    if "id_rsa" in ls_output:
        print(blue("keygen already exists"))
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
            print(blue(image + " already active"))
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

def get_iso(url, imageFile):
    msg = 'Retrieve instance image'
    run("mkdir -p /tmp/images")
    with settings(warn_only=True):
        if run("ls /tmp/images | grep %s" % imageFile, quiet=True) == '':
            runCheck(msg, "wget -P /tmp/images " + url)

            print(blue("Waiting for image file to finish downloading"))
            while run("ls /tmp/images | grep %s" % imageFile, quiet=True) == '':
                if run("nova image-list | grep %s | grep -i ERROR" % imageName, quiet=True) != '':
                    sys.exit("Major problem: image can't be downloaded")


def create_image(imageName, imageFile, diskFormat):
    # requires image to be in /tmp/images

    if image_active(imageName):
        return
    
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

def volume_exists(volume_name):
    if runCheck("checking volume", "cinder list | awk '/%s/'" % volume_name) == "":
        return False
    else:
        print(blue(volume_name + " already exists"))
        return True
        

def create_volume(volumeSize, volumeName):
    if volume_exists(volumeName):
        return
    runCheck('Create a %s GB volume' % volumeSize,
            'cinder create --display-name %s %s' % (volumeName, volumeSize))
 
def create_bootable_volume(imageName, volumeSize, volumeName):
    if volume_exists(volumeName):
        return
    imageID = run("glance image-list | grep '%s' | awk '{print $2}'" % imageName)
    runCheck('Create a %s GB volume' % volumeSize,
            'cinder create --display-name %s --image_id %s %s' % (
                volumeName, imageID, volumeSize))

def already_booted(instanceName):
    if runCheck("check if already booted"," nova list | awk '/%s/'" % instanceName) == "":
        return False
    else:
        print(blue("already booted"))
        return True
   
#def boot_vm(flavorSize, imageName, keyName, instanceName):
def boot_from_volume(flavorSize, volumeName, keyName, instanceName):
    if already_booted(instanceName):
        return

    volumeID = run("nova volume-list | grep '%s' | awk '{print $2}'" % volumeName)
    
    if volumeID != '':
        with settings(warn_only=True):
            print(blue("Waiting for volume to finish building"))
            while run("cinder list | grep %s | grep available" % volumeName, quiet=True) == '':
                if run("cinder list | grep %s | grep error" % volumeName, quiet=True) != '':
                    sys.exit("Major problem: volume can't be made")
 
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
    if already_booted(instanceName):
        return

    volumeID = run("nova volume-list | grep '%s' | awk '{print $2}'" % volumeName)
    
    if volumeID != '':
        with settings(warn_only=True):
            print(blue("Waiting for volume to finish building"))
            while run("cinder list | grep %s | grep available" % volumeName, quiet=True) == '':
                if run("cinder list | grep %s | grep error" % volumeName, quiet=True) != '':
                    sys.exit("Major problem: volume can't be made")
 

 
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
def security_rules_set_on_demo():
    with prefix(env_config.demo_openrc):
        output = runCheck("check for icmp and tcp rule","nova secgroup-list-rules default")
        if all(rule in output for rule in ['tcp', 'icmp']):
            print(blue("rules for icmp and tcp already set"))
            return True
        else:
            return False

@roles('controller')
def adjust_security():
    with prefix(env_config.demo_openrc):
        if security_rules_set_on_demo:
            return
        else:
            runCheck("Edit ICMP security rules", "nova secgroup-add-rule default icmp -1 -1 0.0.0.0/0")
            runCheck("Edit TCP security rules", "nova secgroup-add-rule default tcp 22 22 0.0.0.0/0")

def give_floating_ip(instanceName):
    if "," in runCheck("check if instance has floating ip", " nova list | awk '/%s/ {print $12}' " % instanceName):
        print(blue("floating ip for %s already exists" % instanceName))
        return

    runCheck("Assign floating ip", "nova floating-ip-associate %s " % instanceName + \
            "$(neutron floatingip-create ext-net | awk '/floating_ip_address/ {print $4}')")

def attach_volume(volumeName, instanceName):
    volumeID = run("nova volume-list | grep '%s' | awk '{print $2}'" % volumeName)
    print(blue('Waiting for instance to finish building'))
    if volumeID != '':
        with settings(warn_only=True):
            while run("nova list | grep %s | grep ACTIVE" % instanceName, quiet=True) == '':
                if run("nova list | grep %s | grep ERROR" % instanceName, quiet=True) != '':
                    sys.exit("Major problem: instance can't be made")
 
            print(blue("Waiting for volume to finish building"))
            while run("cinder list | grep %s | grep available" % volumeName, quiet=True) == '':
                if run("cinder list | grep %s | grep error" % volumeName, quiet=True) != '':
                    sys.exit("Major problem: volume can't be made")

    runCheck("Attach volume to instance", "nova volume-attach %s %s auto" % (
                instanceName, volumeID))
    time.sleep(5)

def check_if_volume_attached(instanceName, volumeName):
    if run('nova volume-list | grep %s | grep in-use' % volumeName, warn_only=True) == '':
        print(red("Looks like %s didn't get attached to %s" % (volumeName, instanceName)))
    else:
        print(green('%s successfully attached to %s' % (volumeName, instanceName)))

def create_image_from_volume(volumeName, volumeImageName):
    runCheck('Make an image from the volume', 'cinder upload-to-image %s %s' % (
            volumeName, volumeImageName))

@roles('controller')
def deploy_cirros():
    with prefix(env_config.admin_openrc):
        get_iso('http://129.128.208.164/images/cirros-0.3.3-x86_64-disk.img',
                'cirros-0.3.3-x86_64-disk.img')
        create_image(
           'cirros-image0',
           'cirros-0.3.3-x86_64-disk.img',
           'qcow2')
    with prefix(env_config.demo_openrc):
        generate_key('demo-key')
        create_bootable_volume('cirros-image0', '10', 'cirros-volume0')
        boot_from_volume('small', 'cirros-volume0', 'demo-key', 'demo-instance0')
        give_floating_ip('demo-instance0')
        #attach_volume('cirros-volume0', 'demo-instance0')
        #check_if_volume_attached('demo-instance0', 'cirros-volume0')
        #run("nova list")

@roles('controller')
def deploy_windows7():
    # preconfigured .qcow2 must be present in /tmp/images
    # with name matching the one used below
    with prefix(env_config.admin_openrc):
        get_iso('http://129.128.208.164/images/windows7.qcow2',
                'windows7.qcow2')
        create_image(
            'windows7-image0',
            'windows7.qcow2',
            'qcow2')
    with prefix(env_config.demo_openrc):
        generate_key('demo-key')
        create_bootable_volume('windows7-image0', '50', 'windows7-volume0')
        boot_from_volume('large', 'windows7-volume0', 'demo-key', 'windows7-instance0')
        give_floating_ip('windows7-instance0')
      
@roles('controller')
def deploy_ubuntu_start():
    with prefix(env_config.admin_openrc):
#        get_iso('http://129.128.208.164/images/ubuntu-14.04.3-desktop-amd64.iso',
        get_iso('http://releases.ubuntu.com/14.04.2/ubuntu-14.04.2-desktop-amd64.iso',
                'ubuntu-14.04.2-desktop-amd64.iso')
        create_image(
            'ubuntu-test0',
            'ubuntu-14.04.2-desktop-amd64.iso',
            'qcow2')
    with prefix(env_config.demo_openrc):
        generate_key('demo-key')
        create_volume('10', 'ubuntu-volume0')
        boot_from_image('ubuntu-volume0', 
                        'medium', 
                        'ubuntu-image0', 
                        'demo-key', 
                        'ubuntu-instance0')
        give_floating_ip('ubuntu-instance0')
        #attach_volume('ubuntu-volume0', 'ubuntu-instance0')
        #check_if_volume_attached('ubuntu-instance0', 'ubuntu-volume0')

@roles('controller')
def deploy_ubuntu_end():
     with prefix(env_config.demo_openrc):
        runCheck('Get rid of old instance', 'nova delete ubuntu-instance0')
        runCheck('Make volume bootable', 'cinder set-bootable ubuntu-volume0 true')
        create_image_from_volume('ubuntu-volume0', 'ubuntu-final-image') 
        create_bootable_volume('ubuntuQcowImage', '10', 'ubuntu-bootable-volume1')
        boot_from_volume('small', 'ubuntu-bootable-volume1', 'demo-key', 'ubuntu-volume-instance1')

   
@roles('controller')
def boot_instance(url):
    # function purpose:
    # 1.) gets preconfigured qcow2 file from url location
    #
    # 2.) creates an image from that downloaded file
    #
    # 3.) creates a bootable volume from image 
    #
    # 4.) generates key, boots from bootable volume 
    # and attaches floating ip
    
    instance_suffix = runCheck('get instance name suffix','echo "$(date +%H%M%S)"')
    image_location = url
    image_filename = image_location.split('/')[-1]
    image_name = image_filename.split('.')[0] 
    image_format = image_filename.split('.')[-1]
    instance_name = image_name + 'Instance'
    volume_name =  image_name + 'Volume'
    key_name = 'demo-key'


    # add unique suffixes
    # image_name += instance_suffix
    instance_name += instance_suffix
    # volume_name += instance_suffix

    if "w" in image_name: # to allocate larger size for windows instances
        disk_size = '50'
        flavor = 'large'
    else:
        disk_size = '10'
        flavor = 'medium'
        

    with prefix(env_config.admin_openrc):        
        get_iso(image_location, image_filename)
        create_image(
            image_name,
            image_filename,
            image_format)
    with prefix(env_config.demo_openrc):
        generate_key(key_name)
        create_bootable_volume(image_name, disk_size, volume_name)
        boot_from_volume(flavor, volume_name, key_name, instance_name)
        give_floating_ip(instance_name)

@roles('controller')
def deploy_centos_start():
    with prefix(env_config.admin_openrc):
        get_iso('http://129.128.208.164/images/CentOS-7-x86_64-Minimal-1503-01.iso',
                'CentOS-7-x86_64-Minimal-1503-01.iso') 
        create_image(
            'centos-7-image',
            'CentOS-7-x86_64-Minimal-1503-01.iso',
            'iso')
    with prefix(env_config.demo_openrc):
        generate_key('demo-key')
        create_volume('10', 'centos-7-volume')
        boot_from_image('centos-7-volume', 
                        'small', 
                        'centos-7-image', 
                        'demo-key', 
                        'centos-instance0')
        give_floating_ip('centos-instance0')
    
@roles('controller')
def deploy_centos_end():
    with prefix(env_config.demo_openrc):
        runCheck('Get rid of old instance', 'nova delete centos-instance0')
        runCheck('Make volume bootable', 'cinder set-bootable centos-7-volume true')
        boot_from_volume('small', 'centos-7-volume', 'demo-key', 'centos-volume-instance')

def deploy():
    centos7Minimal_location = 'http://129.128.208.164/images/centos7Minimal.qcow2'
    windows8_location = 'http://129.128.208.164/images/w8.qcow2'
    windows7_location = 'http://129.128.208.164/images/windows7.qcow2'

    execute(adjust_security)

    execute(boot_instance, centos7Minimal_location)
    execute(boot_instance, windows8_location)
    execute(boot_instance, windows7_location)

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

