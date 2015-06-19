from __future__ import with_statement
from fabric.api import *
from fabric.contrib.files import append, exists, sed
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.state import output
from fabric.colors import green, red, blue
import string

import sys, os
sys.path.append('..')
import env_config

from myLib import *
logging.info("################# "\
             + os.path.dirname(os.path.abspath(__file__)) + \
             " ########################")

############################ Config ########################################

env.roledefs = env_config.roledefs

mode = 'normal'
if output['debug']:
    mode = 'debug'

# Logging config

log_file = 'basic-network.log'

########################## Deployment ########################################
@roles('controller','compute','network')
def renameHost():
	msg='Renaming host to %s' % env['host']
	run('hostnamectl set-hostname %s' % env['host'])
	printMessage("good", msg)
	logging.info(msg)


@roles('controller','compute','network')
def installConfigureChrony():
	msg='installing chrony on %s'% env.host
	sudo('yum -y install chrony')
	var1=run('rpm -qa |grep chrony ')
	printMessage("good", msg)
	logging.info(msg +" version "+ var1)
	if env.host == 'controller':
		sed ('/etc/chrony.conf',
                     'server 0.centos.pool.ntp.org iburst',
                     'server time1.srv.ualberta.ca iburst')
		sed ('/etc/chrony.conf',
                     'server 1.centos.pool.ntp.org iburst',
                     'server time2.srv.ualberta.ca iburst')
		sed ('/etc/chrony.conf',
                     'server 2.centos.pool.ntp.org iburst',
                     'server time3.srv.ualberta.ca iburst')
		sed ('/etc/chrony.conf',
                     'server 3.centos.pool.ntp.org iburst',
                     '')
	else:
		run('echo "server controller iburst" > /etc/chrony.conf')

	run('systemctl restart chronyd.service')
	result=run('systemctl status chronyd.service')
	if result.failed:
		logging.info(" starting Chrony on " +env.host)
		run('systemctl start chronyd.service')
		run('systemctl enable chronyd.service')
	else:
		logging.info(" restarting Chrony on " +env.host)
		run('systemctl restart chronyd.service')
	printMessage("good",msg)
	var1=run('systemctl status chronyd.service |grep Active')
	logging.info(env.host +" Chrony is "+ var1)


# General function to install packages that should be in all or several nodes
@roles('controller','compute','network')
def install_packages():
	# Install EPEL (Extra Packages for Entreprise Linux
	print('installing yum-plugin-priorities and epel-release')
	sudo('yum -y install yum-plugin-priorities')
	sudo('yum -y install epel-release')
	for item in ['yum-plugin-priorities','epel-release']:
		var1=run('rpm -qa |grep %s ' %item)
		printMessage("good", item +" is version "+ var1)
		logging.info(item +" is version "+ var1)


	# Install RDO repository for Juno
	print('installing yum-plugin-priorities and epel-release')
	with settings(warn_only=True):
		sudo('yum -y install '
                     'http://rdo.fedorapeople.org/openstack-juno/'
                     'rdo-release-jun.rpm')
	printMessage("good", 'rdo-release-juno.rpm is installed')
	logging.info( 'rdo-release-juno.rpm is installed')

    # Install GlusterFS
    #sudo_log('yum -y install glusterfs-fuse glusterfs')

    # Install Crudini
	print('installing crudini wget')
	sudo("yum -y install crudini wget")
	for item in ['crudini','wget']:
		var1=run('rpm -qa |grep %s ' %item)
		printMessage("good", item +" is version "+ var1)
		logging.info(item +" is version "+ var1)


def installMariaDB():
    # Install MariaDB
    # Only on controller node(s)
    
    if env.host_string in env.roledefs['controller']:
	    # get packages
        sudo_log('yum -y install mariadb mariadb-server MySQL-python')

        # set the config file
        # NB: crudini was not used because of 
        # unexpected parsing 1) without equal sign 2) ! include dir  

        section_header = '\[mysqld\]'

        with cd('/etc/'):
            confFile = 'my.cnf'

            # make a backup
            sudo_log("cp {} {}.back12".format(confFile,confFile))
            if mode == 'debug':
                # change only backup file
                confFile += '.back12'

            # check if the section is already in the file
            out = run("grep '{}' {}".format(section_header,confFile))
            if out.return_code == 0:
                # do a search and replace for all the variables
                specs = env_config.mariaDBmysqldSpecs
                for line in specs:
                    # delete old line in the file
                    if ('=' in line):
                        pattern_to_find = line[:line.index('=')]
                    else:
                        pattern_to_find = line
                    sudo_log('sed -i "/{}/ d" {}'.format\
                            (pattern_to_find,confFile))
                    # append new line with the new value under the header
                    sudo("sed -i '/{}/ a\{}' {}".format\
                            (section_header,line,confFile))

            else:
                # simply add the section
                append(confFile,'\n' + section_header + '\n')
                for line in specs:
                    append(confFile,line)

            # set bind-address (controller's management interface)
            bind_address = env_config.controllerManagement['IPADDR']
            out = sudo('grep bind-address {}'.format(confFile),warn_only=True)
            if out.return_code != 0:
                # simply add the new line
                new_line = "bind-address = " + bind_address
                sudo('sed -i "/{}/a {}" my.cnf'.format\
                        (section_header,new_line))
            else:
                sudo_log("sed -i '/bind-address/ s/=.*/= {}/' my.cnf".format\
                        (bind_address))

            if mode == 'debug':
                print "Here is the final my.cnf file:"
                print blue(sudo_log("grep -vE '(^#|^$)' {}".format(confFile),\
                        quiet=True))

        # enable MariaDB
        sudo_log('systemctl enable mariadb.service')
        sudo_log('systemctl start mariadb.service')
        
    # Upgrade to implement changes
    sudo_log('yum -y upgrade')

def ask_for_reboot():
    sudo_log('wall Everybody please reboot')


#@roles('controller','compute','network','storage')
@roles('controller','compute','network')
@with_settings(warn_only=True)
def test():
	result=run('systemctl status chronyd.service')
	if result.failed:
		run('systemctl start chronyd.service')
		run('systemctl enable chronyd.service')
	else:
		printMessage("good",result)
	var1=run('systemctl status chronyd.service |grep Active')



#@roles('controller','compute','network','storage')
@roles('controller','compute','network')
def deploy():
	execute(renameHost)
	execute(installConfigureChrony)
	execute(install_packages)

@roles('controller','compute','network')
def tdd():
	with settings(warn_only=True):
		print('checking var/log/messages for chronyd output')
		run('grep "$(date +"%b %d %H")" /var/log/messages | '
                    'grep -Ei "(chronyd)"')

	logging.info( " TDD on " +env.host)
	with settings(hide('warnings', 'running', 'stdout', 'stderr'),
                warn_only=True):

		var1=run('systemctl status chronyd.service |grep Active')
		var2=run('date')
	logging.info(env.host +" Chrony is "+ var1)
	logging.info(env.host +" the date is "+ var2)

