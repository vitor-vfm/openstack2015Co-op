from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.contrib.files import append
import string
import sys
sys.path.append('../')#global_config_files')
import env_config
from myLib import runCheck
import time

############################ Config ########################################

env.roledefs = env_config.roledefs
PARTITION = 'strFile'
VOLUME = 'glance_volume'
STRIPE_NUMBER = 1
BRICK = 'glance_brick'

############################# GENERAL FUNCTIONS ############################

@roles('controller', 'compute', 'network', 'storage')
def setup_gluster():
    # Get name of directory partitions are in 
    # Following commented out line is for when /dev/centos isn't called /dev/centos. Put it instead of 
    # the /centos part of '/dev/centos' if there are troubles
    #home_dir = run("lvs | awk '/home/ {print $2}'")
    home_dir = run('ls /dev/ | grep centos')
    # Get and install gluster
    runCheck('Getting packages for gluster', 'wget -P /etc/yum.repos.d http://download.gluster.org/pub/gluster/glusterfs/LATEST/CentOS/glusterfs-epel.repo')
    runCheck('Installing gluster packages', 'yum -y install glusterfs glusterfs-fuse glusterfs-server')
    runCheck('Starting glusterd', 'systemctl start glusterd')
    # If not already made, make the file system (include in partition function)
    #out = run('df -T | grep {}'.format(PARTITION), warn_only=True)
    #out = run('file -sL /dev/{}/{} | grep -i xfs'.format(home_dir, PARTITION), warn_only = True)
    out = run('file -sL /dev/{}/{} | grep -i xfs'.format(home_dir, PARTITION), warn_only = True)
    if out == '':
        #runCheck('Making file system', 'mkfs.xfs -f /dev/{}/{}'.format(home_dir, PARTITION))
        runCheck('Making file system', 'mkfs.xfs -f /dev/{}/{}'.format(home_dir, PARTITION))
    # Mount the brick on the established partition
    run('mkdir -p /data/gluster/{}'.format(BRICK))
    out = run('mount | grep {} | grep /data/gluster/{}'.format(PARTITION, BRICK), warn_only=True)
    if out == '':
        #runCheck('Mounting brick on partition', 'mount /dev/{}/{} /data/gluster/{}'.format(home_dir, PARTITION, BRICK))
        runCheck('Mounting brick on partition', 'mount /dev/{}/{} /data/gluster/{}'.format(home_dir, PARTITION, BRICK))
    # Setup the ports
    #sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 111         -j ACCEPT')
    #sudo('iptables -A INPUT -m state --state NEW -m udp -p udp -s 192.168.254.0/24 --dport 111         -j ACCEPT')
    #sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 2049        -j ACCEPT')
    #sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 24007       -j ACCEPT')
    #sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 38465:38469 -j ACCEPT')
    #sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 49152       -j ACCEPT')
    # Ensure the nodes can probe each other
    runCheck('Restarting glusterd', 'service glusterd restart')
    #run('iptables -F')

@roles('controller', 'compute', 'network', 'storage')
def probe(some_hosts):
    with settings(warn_only=True):
        # peer probe the ip addresses of all the nodes
        for nodes in some_hosts:
            for node in nodes:
                if node !=  env.host_string:
                    node_id = node.split('@', 1)[-1]
                    if runCheck('Probe', 'gluster peer probe {}'.format(node_id)).return_code:
                        print(red('{} cannot probe {}'.format(env.host, node_id)))
                    else:
                        print(green('{} can probe {}'.format(env.host, node_id)))
    # Give time for the peers to actually attach to each other
    time.sleep(3)
    
@roles('controller', 'compute', 'network', 'storage')
def prevolume_start():
    runCheck('Setting conditions so a volume can be made', 'setfattr -x trusted.glusterfs.volume-id /data/gluster/{}'.format(BRICK))
    runCheck('Restarting glusterd', 'service glusterd restart')

@roles('compute')
def create_volume(some_hosts):
    num_nodes = len(some_hosts)
    # Make a string of the ip addresses followed by required string to feed 
    # into following command
    node_ips = string.join([node.split('@', 1)[-1]+':/data/gluster/{} '.format(BRICK) for nodes in some_hosts for node in nodes])
    check_volume = run('gluster volume list', warn_only=True)
    if check_volume != VOLUME:
        runCheck('Creating volume', 'gluster volume create {} rep {} transport tcp {} force'.format(VOLUME, num_nodes, node_ips))
    #prevolume_start()
        runCheck('Starting volume', 'gluster volume start {} force'.format(VOLUME))
    runCheck('Restarting glusterd', '/bin/systemctl restart glusterd.service')

@roles('controller', 'compute', 'network', 'storage')
def mounter():
    runCheck('Making mount point', 'mkdir -p /mnt/gluster/{}'.format(VOLUME))
    if run('mount | grep {} | grep /mnt/gluster/{}'.format(VOLUME, VOLUME), warn_only=True).return_code:
        runCheck('Mounting mount point', 'mount -t glusterfs {}:/{} /mnt/gluster/{}/'.format(env.host, VOLUME, VOLUME))

# This function exists for testing. Should be able to use this then deploy to
# set up gluster on a prepartitioned section of the hard drive
@roles('controller', 'compute', 'network', 'storage')
def destroy_gluster():
    runCheck('Unmounting gluster from /data/', 'umount -l /data/gluster/{}'.format(BRICK))
    runCheck('Removing glusterd from /var/lib/', 'rm -rf /var/lib/glusterd')
    runCheck('Removing gluster from /data/', 'rm -rf /data/gluster/{}'.format(BRICK))

@roles('compute')
def destroy_vol():
    runCheck('Stopping gluster volume', 'yes | gluster volume stop {}'.format(VOLUME)) 
    runCheck('Deleting gluster volume', 'yes | gluster volume delete {}'.format(VOLUME))

@roles('controller', 'compute', 'network', 'storage')
def destroy_mount():
    runCheck('Unmounting gluster from /mnt/', 'umount -l /mnt/gluster/{}'.format(VOLUME)) 
    runCheck('Removing gluster from /mnt/', 'rm -rf /mnt/gluster/{}'.format(VOLUME))
    #runCheck('Unmounting gluster from /mnt/', 'umount -l /mnt/gluster') 
    #runCheck('Removing gluster from /mnt/', 'rm -rf /mnt/gluster')


@roles('controller', 'compute', 'network', 'storage')
def nuke_probes():
    with settings(warn_only=True):
        run('rm -f /var/lib/glusterd/glusterd.info')
        run('rm -f /var/lib/glusterd/peers/*')
        run('service glusterd stop')
        run('systemctl restart glusterd')

##################### Glance ###############################################


@roles('controller', 'compute')
def put_in_nova_line():
    runCheck('Putting line into nova.conf file', "crudini --set '/etc/nova/nova.conf' 'glance' 'libvirt_type' 'qemu'")

@roles('controller')
def put_in_glance_line():
    runCheck('Putting line into glance-api.conf', "crudini --set '/etc/glance/glance-api.conf' 'glance_store' 'filesystem_store_datadir' '/mnt/gluster/glance_volume/glance/images'")

@roles('controller')
def backup_glance_with_gluster():
    runCheck('Making the place where stuff from Glance will be stored', 'mkdir -p /mnt/gluster/glance_volume/glance/images')
    runCheck('Changing the owner to Glance', 'chown -R glance:glance /mnt/gluster/glance_volume/glance/')
    #runCheck('Making the place where stuff from Nova will be stored', 'mkdir /mnt/gluster/instance/')
    #runCheck('Changing the owner to Nova', 'chown -R nova:nova /mnt/gluster/instance/')
    runCheck('Restarting Glance', 'service openstack-glance-api restart') 

@roles('controller', 'compute')
def put_in_other_nova_line():
    runCheck('Adding another line to nova.conf', "crudini --set '/etc/nova/nova.conf' 'DEFAULT' 'instances_path' '/mnt/gluster/glance_volume/instance'")

@roles('compute')
def setup_nova_paths():
    runCheck('Making the place where stuff from Nova will be stored', 'mkdir -p /mnt/gluster/glance_volume/instance/')
    runCheck('Changing the owner to Nova', 'chown -R nova:nova /mnt/gluster/glance_volume/instance/')
    runCheck('Restarting Nova', 'service openstack-nova-compute restart')

@roles('controller')
def destroy_backup():
    runCheck('Removing glance from gluster', 'rm -rf /mnt/gluster/glance_volume/glance')
    #runCheck('Removing instance from gluster', 'rm -rf /mnt/gluster/instance')
    runCheck('Restarting glance', 'service openstack-glance-api restart')

@roles('compute')
def destroy_nova_paths():
    runCheck('Removing instance from gluster', 'rm -rf /mnt/gluster/glance_volume/instance/')
    runCheck('Restarting nova', 'service openstack-nova-compute restart')

def deploy_glance():
    global PARTITION
    PARTITION = 'strFile'
    global VOLUME
    VOLUME = 'glance_volume'
    global BRICK
    BRICK = 'glance_brick'
    execute(setup_gluster)
    execute(probe, env_config.hosts)
    execute(create_volume, env_config.hosts)
    execute(put_in_nova_line)
    execute(mounter)
    execute(put_in_glance_line)
    execute(backup_glance_with_gluster)
    execute(put_in_other_nova_line)
    execute(setup_nova_paths)

def undeploy_glance():
    global PARTITION
    PARTITION = 'strFile'
    global VOLUME
    VOLUME = 'glance_volume'
    global BRICK
    BRICK = 'glance_brick'
    execute(destroy_nova_paths)
    execute(destroy_backup)
    execute(destroy_mount)
    execute(destroy_vol)
    execute(destroy_gluster) 


################################ Cinder ######################################

@roles('controller', 'storage')
def oldinstallGluster():
    runCheck('Install Gluster', 'yum -y install glusterfs-fuse')

@roles('controller', 'storage')
def oldconfigureCinder():
    runCheck('Setup drivers', 'openstack-config --set /etc/cinder/cinder.conf DEFAULT volume_driver cinder.volume.drivers.glusterfs.GlusterfsDriver')
    runCheck('Setup shares', 'openstack-config --set /etc/cinder/cinder.conf DEFAULT glusterfs_shares_config /etc/cinder/shares.conf')
    runCheck('Setup mount points', 'openstack-config --set /etc/cinder/cinder.conf DEFAULT glusterfs_mount_point_base /var/lib/cinder/volumes')

@roles('controller', 'storage')
def oldcreateGlusterVolumeList():
    runCheck('Create cinder file', 'touch /etc/cinder/shares.conf')
    runCheck('Entering info', 'echo -e "192.168.1.11:/mnt/gluster/cinder\n192.168.1.31:/mnt/gluster/cinder" > /etc/cinder/shares.conf')

@roles('controller')
def oldrestartCinder():
    runCheck('Restart Cinder services', 'for i in api scheduler volume; do sudo service openstack-cinder-${i} start; done')
    runCheck('Check logs', "tail -50 /var/log/cinder/volume.log | egrep -i '(ERROR|WARNING|CRITICAL)'")

@roles('controller')
def oldcinderVolumeCreate():
    with prefix(env_config.admin_openrc):
        runCheck('Create a Cinder volume', 'cinder create --display_name myvol 10')
        #with settings(warn_only=True):
        if runCheck('Check to see if volume is created', 'cinder list | grep -i available'):
            print(green('Volume created'))

def olddeploy_cinder():
    PARTITION = 'strBlk'
    VOLUME = 'cinder_volume'
    BRICK = 'cinder_brick'
    execute(installGluster)
    execute(configureCinder)
    execute(createGlusterVolumeList)
    execute(restartCinder)
    execute(cinderVolumeCreate)

@roles('controller')
def olddestroy_cinder_volume():
    with prefix(env_config.admin_openrc):
        runCheck('Delete volume', 'cinder delete myvol')
    runCheck('Stop cinder', 'for i in api scheduler volume; do sudo service openstack-cinder-${i} stop; done')

@roles('controller', 'storage')
def olddestroy_cinder():
    runCheck('Delete cinder file', 'rm /etc/cinder/shares.conf')
    runCheck('Getting rid of Gluster', 'yum remove -y glusterfs-fuse')

def oldundeploy_cinder():
    #PARTITION = 'strBlk'
    #VOLUME = 'cinder_volume'
    #BRICK = 'cinder_brick'
    execute(olddestroy_cinder_volume)
    execute(olddestroy_cinder)

################################ New Cinder ##################################

@roles('controller', 'storage')
def change_cinder_files():
    runCheck('Change cinder.conf file', "crudini --set '/etc/cinder/cinder.conf' 'DEFAULT' 'volume_driver' 'cinder.volume.drivers.glusterfs.GlusterfsDriver'")
    runCheck('Change cinder.conf file', "crudini --set '/etc/cinder/cinder.conf' 'DEFAULT' 'glusterfs_shares_config' '/etc/cinder/shares.conf'")

@roles('controller', 'storage')
def change_shares_file():
    runCheck('Make shares.conf file', 'touch /etc/cinder/shares.conf')
    runCheck('Fill shares.conf file', 'echo "192.168.1.11:/cinder_volume -o backupvolfile-server=192.168.1.31" > /etc/cinder/shares.conf')

@roles('controller', 'storage')
def restart_cinder():
    runCheck('Restart cinder services', 'for i in api scheduler volume; do service openstack-cinder-${i} restart; done')

def deploy_cinder():
    #with settings(host_string = {'controller':['root@controller'], 'storage':['root@storage1']}):
    global PARTITION
    PARTITION = 'strBlk'
    global VOLUME
    VOLUME = 'cinder_volume'
    global BRICK
    BRICK = 'cinder_brick'
    #global [env_config.hosts] 
    #env_config.hosts = {'192.168.1.11': 'controller', '192.168.1.31': 'storage1'}
    execute(setup_gluster)#, roles=['controller','storage'])#, hosts=['root@controller', 'root@storage1'])
    execute(probe, env_config.hosts)#, [['root@controller'], ['root@storage1']], roles=['controller','storage'])#, hosts=['root@controller', 'root@storage1'])
    execute(create_volume, env_config.hosts)#, [['root@controller'], ['root@storage1']], roles=['controller'])
    execute(mounter)#, roles=['controller', 'storage'])#, hosts=['root@controller', 'root@storage1'])
    execute(change_cinder_files)
    execute(change_shares_file)
    execute(restart_cinder) 

				
def undeploy_cinder():
    global PARTITION
    PARTITION = 'strBlk'
    global VOLUME
    VOLUME = 'cinder_volume99'
    global BRICK
    BRICK = 'cinder_brick'
    execute(destroy_mount, roles=['controller', 'storage'])
    execute(destroy_vol, roles=['controller'])
    execute(destroy_gluster, roles=['controller', 'storage'])
 
################################ Deployment ##################################

def deploy():
    execute(setup_gluster)
    execute(probe, env_config.hosts)
    execute(create_volume, env_config.hosts)
    execute(mounter)

def undeploy():
    with settings(warn_only=True):
        execute(destroy_mount)
        execute(destroy_vol)
        execute(destroy_gluster)

################################# TDD ########################################



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

@roles('controller', 'compute', 'network', 'storage')
def check_for_file():
    if run('ls /mnt/gluster/{}'.format(VOLUME)):
        print(green('Gluster is set up on {}'.format(env.user)))
    else:
        print(red('No matter what was said before, Gluster isn\'t correctly set up on any'))

@roles('compute')
def tdd():
    with settings(warn_only=True):
        run('touch /mnt/gluster/{}/testfile'.format(VOLUME))
        execute(check_for_file)
        run('rm /mnt/gluster/{}/testfile'.format(VOLUME))

# Edit this. Check for permissions and who owns the brick.
def glance_tdd():
    with settings(hide('warnings', 'running', 'stdout', 'stderr')):
        execute(deploy_glance)
        execute(tdd)    
