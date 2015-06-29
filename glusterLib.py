# This module contains general GLusterFS
# functions which are used by several fabfiles

from fabric.api import *
from fabric.decorators import roles
from fabric.context_managers import settings
from fabric.colors import green, red, blue
import env_config
from myLib import runCheck, set_parameter


@roles('controller', 'compute', 'network', 'storage')
def setup_gluster(partition,brick):
    # Get name of directory partitions are in 
    home_dir = run("lvs | awk '/home/ {print $2}'")

    # Get and install gluster

    runCheck('Get packages for gluster', 
            'wget -P /etc/yum.repos.d '
            'http://download.gluster.org/pub/'
            'gluster/glusterfs/LATEST/CentOS/glusterfs-epel.repo')

    runCheck('Install gluster packages', 
            'yum -y install glusterfs glusterfs-fuse glusterfs-server')

    runCheck('Start glusterd', 'systemctl start glusterd')

    # If not already made, make the file system (include in partition function)
    out = run('file -sL /dev/centos/{} | grep -i xfs'.format(partition))
    if out == '':
        runCheck('Make file system', 'mkfs.xfs -f /dev/{}/{}'.format(
            home_dir, partition))

    # Mount the brick on the established partition
    run('mkdir -p /data/gluster/{}'.format(brick))
    out = run("mount | grep '{}' | grep '/data/gluster/{}'".format(
        partition, brick), warn_only=True)
    if out == '':
        runCheck('Mount brick on partition', 
                'mount /dev/{}/{} /data/gluster/{}'.format(
                    home_dir, partition, brick))
    
    # Ensure the nodes can probe each other
    runCheck('Restart glusterd', 'service glusterd restart')


@roles('controller', 'compute', 'network', 'storage')
def probe():
    with settings(warn_only=True):
        # peer probe the ip addresses of all the nodes
        for node in env_config.hosts:
            if node != env.host_string:
                node_ip = node.split('@', 1)[-1]
                if sudo('gluster peer probe {}'.format(node_ip)).return_code:
                    print(red('{} cannot probe {}'.format(
                        env.host, node.split('@', 1)[0])))
                else:
                    print(green('{} can probe {}'.format(
                        env.host, node.split('@', 1)[0])))

@roles('compute')
def create_volume(brick, volume):
    num_nodes = len(env_config.hosts)

    # Make a string of the ip addresses followed by required string to feed 
    # into following command
    node_ips = string.join([
        node.split('@', 1)[-1]+':/data/gluster/{}'.format(brick)
        for node in env_config.hosts
        ])

    check_volume = run('gluster volume list', warn_only=True)
    if check_volume != volume:
        runCheck('Create volume', 
                'gluster volume create {} rep {} transport tcp {} force'.format(
                    volume, num_nodes, node_ips))

        runCheck('Start volume', 'gluster volume start {} force'.format(
            volume))

    runCheck('Restart glusterd', '/bin/systemctl restart glusterd.service')


@roles('controller', 'compute', 'network', 'storage')
def mount(volume):
    runCheck('Make mount point', 'mkdir -p /mnt/gluster')
    if run("mount | grep '{}' | grep /mnt/gluster".format(volume), 
            warn_only=True).return_code:
        runCheck('Mount mount point', 
                'mount -t glusterfs {}:/{} /mnt/gluster/'.format(
                    env.host, volume))
