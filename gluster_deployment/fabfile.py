from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import string
import sys
sys.path.append('../global_config_files')
import env_config


############################ Config ########################################

env.roledefs = env_config.roledefs
PARTITION = '/dev/sda3'
VOLUME = 'vol0'

############################# GENERAL FUNCTIONS ############################

@roles('controller', 'compute', 'network')
def setup_gluster():
    sudo('wget -P /etc/yum.repos.d http://download.gluster.org/pub/gluster/glusterfs/LATEST/CentOS/glusterfs-epel.repo')
    sudo('yum -y install glusterfs glusterfs-fuse glusterfs-server')
    sudo('systemctl start glusterd')
    #sudo('mkfs.ext4 {}'.format(PARTITION))
    sudo('mkdir -p /data/gluster/brick')
    sudo('mount {} /data/gluster'.format(PARTITION))
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 111         -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m udp -p udp -s 192.168.254.0/24 --dport 111         -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 2049        -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 24007       -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 38465:38469 -j ACCEPT')
    sudo('iptables -A INPUT -m state --state NEW -m tcp -p tcp -s 192.168.254.0/24 --dport 49152       -j ACCEPT')
    sudo('service glusterd restart')
    sudo('iptables -F')

@roles('controller', 'compute', 'network')
def probe():
    with settings(warn_only=True):
        # peer probe the ip addresses of all the nodes
        for node in env_config.hosts:
            if node != env.host_string:
                node_ip = node.split('@', 1)[-1]
                if sudo('gluster peer probe {}'.format(node_ip)).return_code:
                    print(red('{} cannot probe {}'.format(env.user, node.split('@', 1)[0])))
                else:
                    print(green('{} can probe {}'.format(env.user, node.split('@', 1)[0])))
    
@roles('controller', 'compue', 'network')
def prevolume():
    sudo('setfattr -x trusted.glusterfs.volume-id /data/gluster/brick')
    sudo('service glusterd restart')

@roles('compute')
def create_volume():
    num_nodes = len(env_config.hosts)
    # Make a string of the ip addresses followed by required string to feed 
    # into following command
    node_ips = string.join([node.split('@', 1)[-1]+':/data/gluster/brick' for node in env_config.hosts])
    sudo('gluster volume create {} rep {} transport tcp {} force'.format(VOLUME, num_nodes, node_ips))
    #sudo('gluster volume start {}'.format(VOLUME))

@roles('compute')
def destroy_vol():
    sudo('gluster volume delete {}'.format(VOLUME))

# This function exists for testing. Should be able to use this then deploy to
# set up gluster on a prepartitioned section of the hard drive
@roles('controller', 'compute', 'network')
def destroy_gluster():
    sudo('umount /data/gluster')
    sudo('rm -rf /var/lib/glusterd')
    sudo('rm -rf /data/gluster')


    
################### Deployment #############################################

def deploy():
    execute(setup_gluster)
    execute(probe)

def undeploy():
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

@roles('controller')
def tdd():
    with settings(warn_only=True):
        time = installRabbitMQtdd()
        execute(check_log,time)

