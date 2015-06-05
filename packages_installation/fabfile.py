from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
import string


import sys
sys.path.append('../global_config_files')

import env_config


############################ Config ########################################

env.roledefs = env_config.roledefs

# config files for MariaDB
mariadb_repo = 'config_files/mariadb_repo'
mariadb_mysqld_specs = 'config_files/mariadb_mysqld_specs'

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
        section_header = '\[mysqld\]'

        with cd('/etc/'):
            # check if the section is already in the file
            if run("grep '{}' my.cnf".format(section_header)).return_code == 0:
                # do a search and replace for all the variables
                config_file = open(mariadb_mysqld_specs, 'r').readlines(True)
                # make a backup
                sudo("cp my.cnf my.cnf.back12")

                for line in config_file:
                    # delete old line in the file
                    # remove \n
                    line = line[:-1]
                    if ('=' in line):
                        pattern_to_find = line[:line.index('=')]
                    else:
                        pattern_to_find = line
                    sudo('sed -i "/{}/ d" my.cnf'.format(pattern_to_find))
                    # append new line with the new value under the header
                    sudo('''sed -i '/{}/ a\{}' my.cnf'''.format(section_header,line))

            else:
                # simply add the section
                config_file = '\n' + section_header + '\n'
                config_file += open(mariadb_mysqld_specs, 'r').read()
                sudo('echo -e "{}" >>my.cnf'.format(config_file))
            
            # set bind-address (controller's management interface)
            controller_NIC = '../1-network_deployment/config_files/controller_management_interface_config'
            bind_address = local("crudini --get {} '' IPADDR".format(controller_NIC),capture=True)
            if sudo('grep bind-address my.cnf').return_code != 0:
                # simply add the new line
                new_line = "bind-address = " + bind_address
                sudo("""sed -i "/{}/a {}" my.cnf""".format(section_header,new_line))
            else:
                sudo("sed -i '/bind-address/ s/=.*/={}/' my.cnf".format(bind_address))
            # sudo('crudini --set my.cnf mysqld bind-address {}'.format(bind_address))
            sudo('grep bind-address my.cnf')

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

