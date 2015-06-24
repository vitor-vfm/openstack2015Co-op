from __future__ import with_statement
from fabric.api import *
from fabric.contrib.files import append, exists, sed
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.state import output
from fabric.colors import green, red, blue
import string
import logging

import sys, os
sys.path.append('..')
import env_config

from myLib import printMessage, runCheck

logging.info("################# "\
             + os.path.dirname(os.path.abspath(__file__)) + \
             " ########################")

############################ Config ########################################

env.roledefs = env_config.roledefs

mode = 'normal'
if output['debug']:
    mode = 'debug'

########################## Deployment ########################################

@roles('controller','compute','network','storage')
def renameHost():
	msg='Renaming host to %s' % env['host']
	run('hostnamectl set-hostname %s' % env['host'])
	printMessage("good", msg)
	logging.info(msg)

@roles(env_config.roles)
def disableFirewall():
    
    msg = 'Disable firewalld on ' + env.host
    runCheck(msg, 'systemctl disable firewalld')
    msg = 'Stop firewalld on ' + env.host
    runCheck(msg, 'systemctl stop firewalld')

@roles(env_config.roles)
def disableSELinux():

    set_parameter('/etc/selinux/config', '', 'SELINUX', 'disabled')


@roles('controller','compute','network','storage')
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
@roles('controller','compute','network','storage')
def install_packages():
	# Install EPEL (Extra Packages for Entreprise Linux
	print('installing yum-plugin-priorities and epel-release')
        msg = 'Install EPEL packages'
	runCheck(msg, 'yum -y install yum-plugin-priorities')
	runCheck(msg, 'yum -y install epel-release')
	for item in ['yum-plugin-priorities','epel-release']:
		var1=run('rpm -qa |grep %s ' %item)
		print blue(item +" is version "+ var1)
		logging.info(item +" is version "+ var1)


	# Install RDO repository for Juno
	print('installing yum-plugin-priorities and epel-release')
        msg = 'Install rdo-release-juno.rpm'
        runCheck(msg, 'yum -y install '
                'http://rdo.fedorapeople.org/openstack-juno/'
                'rdo-release-juno.rpm')

        # Install Crudini and wget
        print('installing crudini wget')
	sudo("yum -y install crudini wget")
	for item in ['crudini','wget']:
		var1=run('rpm -qa |grep %s ' %item)
		print blue(item +" is version "+ var1)
		logging.info(item +" is version "+ var1)

        # save credentials in the host
        # put('../admin_openrc.sh')
        # put('../demo_openrc.sh')

        msg = 'Upgrade to implement changes'
        runCheck(msg, 'yum -y upgrade')



@roles('controller')
def installMariaDB():
    # Install MariaDB
    
    msg = 'Get packages'
    runCheck(msg, 'yum -y install mariadb mariadb-server MySQL-python')

    # set the config file

    with cd('/etc/'):
        confFile = 'my.cnf'
        fileContents = env_config.my_cnf

        # set bind-address
        fileContents = fileContents.replace(\
                'BIND_ADDRESS',env_config.controllerManagement['IPADDR'])

        # make a backup
        run("cp {} {}.back12".format(confFile,confFile))

        if mode == 'debug':
            # change only backup file
            confFile += '.back12'

        # Add new my.cnf file, clobbering if necessary
        msg = 'Create my.cnf file'
        runCheck(msg, "echo '{}' >{}".format(fileContents,confFile))
        
        if mode == 'debug':
            print "Here is the final my.cnf file:"
            print blue(run("grep -vE '(^#|^$)' {}".format(confFile),\
                    quiet=True))

    msg = 'Enable mariadb service'
    runCheck(msg, 'systemctl enable mariadb.service')
    msg = 'Enable mariadb service'
    runCheck(msg, 'systemctl start mariadb.service')
        
    msg = 'Upgrade to implement changes'
    runCheck(msg, 'yum -y upgrade')

def ask_for_reboot():
    run('wall Everybody please reboot')


@roles('controller','compute','network','storage')
# @roles('controller','compute','network')
@with_settings(warn_only=True)
def test():
	result=run('systemctl status chronyd.service')
	if result.failed:
		run('systemctl start chronyd.service')
		run('systemctl enable chronyd.service')
	else:
		printMessage("good",result)
	var1=run('systemctl status chronyd.service |grep Active')



@roles('controller','compute','network','storage')
# @roles('controller','compute','network')
def deploy():
	execute(renameHost)
	execute(installConfigureChrony)
	execute(install_packages)
	execute(installMariaDB)
	execute(disableFirewall)
	execute(disableSELinux)

        # reboot the machine
        with settings(warn_only=True):
            run('reboot')


@roles('controller','compute','network','storage')
# @roles('controller','compute','network')
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

