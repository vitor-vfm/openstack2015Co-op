from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import string
import sys
sys.path.append('../')#global_config_files')
import env_config
import myLib

############################ Config ########################################

env.roledefs = env_config.roledefs
PARTITION = '/dev/sda1'
EX_VOLUME = 'vol0'
GLANCE_VOLUME = 'exp1'

############################# GENERAL FUNCTIONS ############################

def get_parameter(config_file, section, parameter):
    crudini_command = "crudini --get {} {} {}".format(config_file, section, parameter)
    return local(crudini_command, capture=True)

@roles('controller', 'compute', 'network', 'storage')
def shrinkHome():
    run('umount /rootfs')
    run('lvresize -L -{} /dev/mapper/centos-root'.format(env_config.partition['size_reduction_of_home']))
    run('mkfs -t xfs -f /dev/centos/root')
    run('mount /rootfs')

@roles('controller', 'network', 'compute', 'storage')
def prepGlusterFS():
    run('lvs')
    run('lvcreate -i 1 -I 8 -L {} centos'.format(env_config.partition['partition_size']))
    run('lvrename /dev/centos/lvol0 strFile')
    run('lvcreate -i 1 -I 8 -L {} centos'.format(env_config.partition['partition_size']))
    run('lvrename /dev/centos/lvol0 strObj')
    run('lvcreate -i 1 -I 8 -L {} centos'.format(env_config.partition['partition_size']))
    run('lvrename /dev/centos/lvol0 strBlk')
    run('lvs')

@roles('controller', 'compute', 'network', 'storage')
def setup_gluster():
    # Get and install gluster
    runCheck('Getting packages for gluster', 'wget -P /etc/yum.repos.d http://download.gluster.org/pub/gluster/glusterfs/LATEST/CentOS/glusterfs-epel.repo')
    runCheck('Installing gluster packages', 'yum -y install glusterfs glusterfs-fuse glusterfs-server')
    runCheck('Starting glusterd', 'systemctl start glusterd')
    # Make the file system (probably include this in partition function)
    #sudo('mkfs.xfs {}'.format(PARTITION))
    # Mount the brick on the established partition
    sudo('mkdir -p /data/gluster/brick')
    runCheck('Mounting brick on partition', 'mount {} /data/gluster'.format(PARTITION))
    # Setup the ports
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 111         -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m udp -p udp -s 192.168.254.0/24 --dport 111         -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 2049        -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 24007       -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 38465:38469 -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 49152       -j ACCEPT')
    # Ensure the nodes can probe each other
    runCheck('Restarting glusterd', 'service glusterd restart')
    sudo('iptables -F')

@roles('controller', 'compute', 'network', 'storage')
def probe():
    with settings(warn_only=True):
        # peer probe the ip addresses of all the nodes
        for node in env_config.hosts:
            if node != env.host_string:
                node_ip = node.split('@', 1)[-1]
                if sudo('gluster peer probe {}'.format(node_ip)).return_code:
                    print(red('{} cannot probe {}'.format(env.host, node.split('@', 1)[0])))
                else:
                    print(green('{} can probe {}'.format(env.host, node.split('@', 1)[0])))
    
@roles('controller', 'compute', 'network', 'storage')
def prevolume_start():
    runCheck('Setting conditions so a volume can be made', 'setfattr -x trusted.glusterfs.volume-id /data/gluster/brick')
    runCheck('Restarting glusterd', 'service glusterd restart')

@roles('compute')
def create_volume():
    num_nodes = len(env_config.hosts)
    # Make a string of the ip addresses followed by required string to feed 
    # into following command
    node_ips = string.join([node.split('@', 1)[-1]+':/data/gluster/brick' for node in env_config.hosts])
    runCheck('Creating volume', 'gluster volume create {} rep {} transport tcp {} force'.format(GLANCE_VOLUME, num_nodes, node_ips))
    #prevolume_start()
    runCheck('Starting volume', 'gluster volume start {} force'.format(GLANCE_VOLUME))
    runCheck('Restarting glusterd', '/bin/systemctl restart glusterd.service')

@roles('controller', 'compute', 'network', 'storage')
def mounter():
    runCheck('Making mount point', 'mkdir -p /mnt/gluster')
    runCheck('Mounting mount point', 'mount -t glusterfs {}:/{} /mnt/gluster/'.format(env.host, GLANCE_VOLUME))

@roles('controller', 'compute')
def put_in_nova_line():
    runCheck('Putting line into nova.conf file', "crudini --set '/etc/nova/nova.conf' 'glance' 'libvirt_type' 'qemu'")

@roles('controller')
def put_in_glance_line():
    runCheck('Putting line into glance-api.conf', "crudini --set '/etc/glance/glance-api.conf' 'glance_store' 'filesystem_store_datadir' '/mnt/gluster/glance/images'")

@roles('controller')
def backup_glance_with_gluster():
    runCheck('Making the place where stuff from Glance will be stored', 'mkdir -p /mnt/gluster/glance/images')
    runCheck('Changing the owner to Glance', 'chown -R glance:glance /mnt/gluster/glance/')
    #runCheck('Making the place where stuff from Nova will be stored', 'mkdir /mnt/gluster/instance/')
    #runCheck('Changing the owner to Nova', 'chown -R nova:nova /mnt/gluster/instance/')
    runCheck('Restarting Glance', 'service openstack-glance-api restart') 

@roles('controller', 'compute')
def put_in_other_nova_line():
    runCheck('Adding another line to nova.conf', "crudini --set '/etc/nova/nova.conf' 'DEFAULT' 'instances_path' '/mnt/gluster/instance'")

@roles('compute')
def setup_nova_paths():
    runCheck('Making the place where stuff from Nova will be stored', 'mkdir -p /mnt/gluster/instance/')
    runCheck('Changing the owner to Nova', 'chown -R nova:nova /mnt/gluster/instance/')
    runCheck('Restarting Nova', 'service openstack-nova-compute restart')

# This function exists for testing. Should be able to use this then deploy to
# set up gluster on a prepartitioned section of the hard drive
@roles('controller', 'compute', 'network', 'storage')
def destroy_gluster():
    runCheck('Unmounting gluster from /data/', 'umount /data/gluster')
    runCheck('Removing glusterd from /var/lib/', 'rm -rf /var/lib/glusterd')
    runCheck('Removing gluster from /data/', 'rm -rf /data/gluster')

@roles('compute')
def destroy_vol():
    runCheck('Stopping gluster volume', 'yes | gluster volume stop {}'.format(GLANCE_VOLUME)) 
    runCheck('Deleting gluster volume', 'yes | gluster volume delete {}'.format(GLANCE_VOLUME))

@roles('controller', 'compute', 'network', 'storage')
def destroy_mount():
    runCheck('Unmounting gluster from /mnt/', 'umount /mnt/gluster') 
    runCheck('Removing gluster from /mnt/', 'rm -rf /mnt/gluster')

@roles('controller')
def destroy_backup():
    runCheck('Removing glance from gluster', 'rm -rf /mnt/gluster/glance')
    #runCheck('Removing instance from gluster', 'rm -rf /mnt/gluster/instance')
    runCheck('Restarting glance', 'service openstack-glance-api restart')

@roles('compute')
def destroy_nova_paths():
    runCheck('Removing instance from gluster', 'rm -rf /mnt/gluster/instance/')
    runCheck('Restarting nova', 'service openstack-nova-compute restart')

##################### Glance ###############################################

def deploy_glance():
    execute(setup_gluster)
    execute(probe)
    execute(create_volume)
    execute(put_in_nova_line)
    execute(mounter)
    execute(put_in_glance_line)
    execute(backup_glance_with_gluster)
    execute(put_in_other_nova_line)
    execute(setup_nova_paths)

def undeploy_glance():
    execute(destroy_nova_paths)
    execute(destroy_backup)
    execute(destroy_mount)
    execute(destroy_vol)
    execute(destroy_gluster) 


################### Deployment #############################################

def deploy():
    execute(setup_gluster)
    execute(probe)
    execute(create_volume)
    execute(mounter)

def undeploy():
    execute(destroy_mount)
    execute(destroy_vol)
    execute(destroy_gluster)

######################################## TDD ###############################



#        print(green("GOOD"))
 #   else:
  #      print(red("BAD")) 
   #sudo("rm -r /tmp/images")



#def tdd():
#    with settings(warn_only=True):
        # Following command lists errors. Find out how to get it to find 
        # specific errors or a certain number of them based on time.
        #sudo cat messages | egrep '(error|warning)'
 #       time = installRabbitMQtdd()
  #      check_log(time)
        

@roles('compute', 'controller', 'network')
def check_log(time):
    with settings(quiet=True):
        for error_num in range(8):
            print(time[error_num]) 
            run('echo {} > time'.format(time[error_num]))
            if run("sudo cat /var/log/messages | egrep '(debug|warning|critical)' | grep -f time"):
                # Make it specify which one doesn't work
                print(red("Error in so far unspecified function"))
            else:
                print(green("Success, whatever this is"))
            run('rm time')

@roles('controller', 'compute', 'network')
def check_for_file():
    if sudo('ls /mnt/gluster/'):
        print(green('Gluster is set up on {}'.format(env.user)))
    else:
        print(red('No matter what was said before, Gluster isn\'t correctly set up on any'))

@roles('compute')
def tdd():
    with settings(warn_only=True):
        sudo('touch /mnt/gluster/testfile')
        execute(check_for_file)
        sudo('rm /mnt/gluster/testfile')
