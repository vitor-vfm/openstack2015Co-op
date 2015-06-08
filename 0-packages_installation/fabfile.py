from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.state import output
from fabric.colors import green, red, blue
import string


import sys
sys.path.append('../global_config_files')

import env_config


############################ Config ########################################

env.roledefs = env_config.roledefs

mode = 'normal'
if output['debug']:
    mode = 'debug'

################### Deployment ########################################

# General function to install packages that should be in all or several nodes
@with_settings(warn_only=True)
def install_packages():
    
    # Install Chrony
    sudo('yum -y install chrony')
    # enable Chrony
    sudo('systemctl enable chronyd.service')
    sudo('systemctl start chronyd.service')

    # Install EPEL (Extra Packages for Entreprise Linux
    sudo('yum -y install yum-plugin-priorities')
    sudo('yum -y install epel-release')

    # Install RDO repository for Juno
    sudo('yum -y install http://rdo.fedorapeople.org/openstack-juno/rdo-release-juno.rpm')

    # Install Crudini
    sudo("yum -y install crudini")

    # Install wget
    sudo("yum -y install wget")


    sudo("crudini --set /etc/selinux/config '' SELINUX disabled")


    # Install MariaDB
    # Only on controller node(s)
    
    if env.host_string in env.roledefs['controller']:
	    # get packages
        sudo('yum -y install mariadb mariadb-server MySQL-python')

        # set the config file
        # NB: crudini was not used because of unexpected parsing 1) without equal sign 2) ! include dir  

        section_header = '\[mysqld\]'

        with cd('/etc/'):
            confFile = 'my.cnf'

            # make a backup
            sudo("cp {} {}.back12".format(confFile,confFile))
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
                    sudo('sed -i "/{}/ d" {}'.format(pattern_to_find,confFile))
                    # append new line with the new value under the header
                    sudo("sed -i '/{}/ a\{}' {}".format(section_header,line,confFile))

            else:
                # simply add the section
                append(confFile,'\n' + section_header + '\n')
                for line in specs:
                    append(confFile,line)

            # set bind-address (controller's management interface)
            bind_address = env_config.controllerManagement['IPADDR']
            if sudo('grep bind-address {}'.format(confFile)).return_code != 0:
                # simply add the new line
                new_line = "bind-address = " + bind_address
                sudo('sed -i "/{}/a {}" my.cnf'.format(section_header,new_line))
            else:
                sudo("sed -i '/bind-address/ s/=.*/= {}/' my.cnf".format(bind_address))

            if mode == 'debug':
                print "Here is the final my.cnf file:"
                print blue(sudo("grep -vE '(^#|^$)' {}".format(confFile),quiet=True))

        # enable MariaDB
        sudo('systemctl enable mariadb.service')
        sudo('systemctl start mariadb.service')
        

    # Upgrade to implement changes
    sudo('yum -y upgrade')

def ask_for_reboot():
    sudo('wall Everybody please reboot')

@roles('controller','compute','network','storage')
def deploy():
    execute(install_packages)

