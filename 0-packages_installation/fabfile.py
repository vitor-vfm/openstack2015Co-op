from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.state import output
from fabric.colors import green, red, blue
import string

import sys
sys.path.append('../global_config_files')
sys.path.append('..')
import myLib

import env_config
from env_config import log_debug, log_info, log_error, run_log, sudo_log


############################ Config ########################################

env.roledefs = env_config.roledefs

mode = 'normal'
if output['debug']:
    mode = 'debug'

# Logging config

log_file = 'basic-network.log'
env_config.setupLoggingInFabfile(log_file)

################### Deployment ########################################
@roles('controller','compute','network')
def renameHost():
	msg='Renaming host to %s' % env['host']
	run('hostnamectl set-hostname %s' % env['host'])
	printMessage("good", msg)
	logging.debug(msg)

# General function to install packages that should be in all or several nodes
@with_settings(warn_only=True)
def install_packages():
    
    # Install Chrony
    sudo_log('yum -y install chrony')
    # enable Chrony
    sudo_log('systemctl enable chronyd.service')
    sudo_log('systemctl start chronyd.service')

    # Install EPEL (Extra Packages for Entreprise Linux
    sudo_log('yum -y install yum-plugin-priorities')
    sudo_log('yum -y install epel-release')

    # Install RDO repository for Juno
    sudo_log('yum -y install http://rdo.fedorapeople.org/openstack-juno/rdo-release-juno.rpm')

    # Install Crudini
    sudo_log("yum -y install crudini")

    # Install wget
    sudo_log("yum -y install wget")



def instalMariaDB():
    # Install MariaDB
    # Only on controller node(s)
    
    if env.host_string in env.roledefs['controller']:
	    # get packages
        sudo_log('yum -y install mariadb mariadb-server MySQL-python')

        # set the config file
        # NB: crudini was not used because of unexpected parsing 1) without equal sign 2) ! include dir  

        section_header = '\[mysqld\]'

        with cd('/etc/'):
            confFile = 'my.cnf'

            # make a backup
            sudo_log("cp {} {}.back12".format(confFile,confFile))
            if mode == 'debug':
                # change only backup file
                confFile += '.back12'

            # check if the section is already in the file
            if run("grep '{}' {}".format(section_header,confFile)).return_code == 0:
                # do a search and replace for all the variables
                specs = env_config.mariaDBmysqldSpecs
                for line in specs:
                    # delete old line in the file
                    if ('=' in line):
                        pattern_to_find = line[:line.index('=')]
                    else:
                        pattern_to_find = line
                    sudo_log('sed -i "/{}/ d" {}'.format(pattern_to_find,confFile))
                    # append new line with the new value under the header
                    sudo("sed -i '/{}/ a\{}' {}".format(section_header,line,confFile))

            else:
                # simply add the section
                append(confFile,'\n' + section_header + '\n')
                for line in specs:
                    append(confFile,line)

            # set bind-address (controller's management interface)
            bind_address = env_config.controllerManagement['IPADDR']
            if sudo_log('grep bind-address {}'.format(confFile)).return_code != 0:
                # simply add the new line
                new_line = "bind-address = " + bind_address
                sudo('sed -i "/{}/a {}" my.cnf'.format(section_header,new_line))
            else:
                sudo_log("sed -i '/bind-address/ s/=.*/= {}/' my.cnf".format(bind_address))

            if mode == 'debug':
                print "Here is the final my.cnf file:"
                print blue(sudo_log("grep -vE '(^#|^$)' {}".format(confFile),quiet=True))

        # enable MariaDB
        sudo_log('systemctl enable mariadb.service')
        sudo_log('systemctl start mariadb.service')
        

    # Upgrade to implement changes
    sudo_log('yum -y upgrade')

def ask_for_reboot():
    sudo_log('wall Everybody please reboot')


#@roles('controller','compute','network','storage')
@roles('controller','compute','network')
def test():
    run("echo Hello $(hostname)")


#@roles('controller','compute','network','storage')
@roles('controller','compute','network')
def deploy():
    execute(install_packages)

@roles('controller','compute','network')
def tdd():
	run('hostname')