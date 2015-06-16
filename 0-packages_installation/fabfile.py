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
# from myLib import *
import env_config
# logging.info("################# " + os.path.dirname(os.path.abspath(__file__)) + " ########################")

############################ Config ########################################

env.roledefs = env_config.roledefs

mode = 'normal'
if output['debug']:
    mode = 'debug'

########################## Deployment ########################################
@roles('controller','compute','network')
def renameHost():
	msg='Renaming host to %s' % env['host']
	run('hostnamectl set-hostname %s' % env['host'])
	printMessage("good", msg)
	logging.info(msg)


@roles('controller','compute','network')
def installConfigureChrony():
	msg='installing chrony'
	sudo('yum -y install chrony')
	var1=run('rpm -qa |grep chrony ')
	printMessage("good", msg)
	logging.info(msg +" version "+ var1)
	if env.host == 'controller':
		sed ('/etc/chrony.conf','server 0.centos.pool.ntp.org iburst','server time1.srv.ualberta.ca iburst')
		sed ('/etc/chrony.conf','server 1.centos.pool.ntp.org iburst','server time2.srv.ualberta.ca iburst')
		sed ('/etc/chrony.conf','server 2.centos.pool.ntp.org iburst','server time3.srv.ualberta.ca iburst')
		sed ('/etc/chrony.conf','server 3.centos.pool.ntp.org iburst','')
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
@with_settings(warn_only=True)
def install_packages():
    
    # Install EPEL (Extra Packages for Entreprise Linux
    run('yum -y install yum-plugin-priorities')
    run('yum -y install epel-release')

    # Install RDO repository for Juno
    run('yum -y install http://rdo.fedorapeople.org/openstack-juno/rdo-release-juno.rpm')

    # Install GlusterFS
    run('yum -y install glusterfs-fuse glusterfs')

    # Install Crudini
    run("yum -y install crudini")

    # Install wget
    run("yum -y install wget")



@roles('controller')
def installMariaDB():
    """
    Install MariaDB and set its conf files
    """
    
    if env.host_string in env.roledefs['controller']:
	    # get packages
        run('yum -y install mariadb mariadb-server MySQL-python')

        # set the config file
        # NB: crudini was not used because of unexpected parsing 1) without equal sign 2) ! include dir  

        section_header = '\[mysqld\]'

        with cd('/etc/'):
            confFile = 'my.cnf'

            # make a backup
            run("cp {} {}.back12".format(confFile,confFile))
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
                    run('sed -i "/{}/ d" {}'.format(pattern_to_find,confFile))
                    # append new line with the new value under the header
                    sudo("sed -i '/{}/ a\{}' {}".format(section_header,line,confFile))

            else:
                # simply add the section
                append(confFile,'\n' + section_header + '\n')
                for line in specs:
                    append(confFile,line)

            # set bind-address (controller's management interface)
            bind_address = env_config.controllerManagement['IPADDR']
            if sudo('grep bind-address {}'.format(confFile),warn_only=True).return_code != 0:
                # simply add the new line
                new_line = "bind-address = " + bind_address
                sudo('sed -i "/{}/a {}" my.cnf'.format(section_header,new_line))
            else:
                run("sed -i '/bind-address/ s/=.*/= {}/' my.cnf".format(bind_address))

            if mode == 'debug':
                print "Here is the final my.cnf file:"
                print blue(run("grep -vE '(^#|^$)' {}".format(confFile),quiet=True))

        # enable MariaDB
        run('systemctl enable mariadb.service')
        run('systemctl start mariadb.service')
        

    # Upgrade to implement changes
    run('yum -y upgrade')

def ask_for_reboot():
    run('wall Everybody please reboot')


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
    execute(install_packages)

@roles('controller','compute','network')
def tdd():
	with settings(warn_only=True):
		print('checking var/log/messages for chronyd output')
		run('grep "$(date +"%b %d %H")" /var/log/messages| grep -Ei "(chronyd)"')
	logging.info( " TDD on " +env.host)
	with settings(hide('warnings', 'running', 'stdout', 'stderr'),warn_only=True):
		var1=run('systemctl status chronyd.service |grep Active')
		var2=run('date')
	logging.info(env.host +" Chrony is "+ var1)
	logging.info(env.host +" the date is "+ var2)

