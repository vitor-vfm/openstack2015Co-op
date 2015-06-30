from __future__ import with_statement
from fabric.api import *
from fabric.contrib.files import append, exists, sed, put
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.state import output
from fabric.colors import green, red, blue
import string
import logging

import sys, os
sys.path.append('..')
import env_config

from myLib import printMessage, runCheck, set_parameter
from myLib import align_n, align_y, saveConfigFile

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

#@roles(env_config.roles)
@roles('controller','compute','network','storage')
def disableFirewall():
    
    msg = 'Disable firewalld on ' + env.host
    runCheck(msg, 'systemctl disable firewalld')
    msg = 'Stop firewalld on ' + env.host
    runCheck(msg, 'systemctl stop firewalld')

#@roles(env_config.roles)
@roles('controller','compute','network','storage')
def disableSELinux():
    set_parameter('/etc/selinux/config', '""', 'SELINUX', 'disabled')


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
        with settings(warn_only=True):
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
        contents = env_config.admin_openrc
        msg = 'Put admin_openrc.sh in '+env.host
        runCheck(msg, "echo '{}' >/root/admin_openrc.sh".format(contents))

        contents = env_config.demo_openrc
        msg = 'Put demo_openrc.sh in '+env.host
        runCheck(msg, "echo '{}' >/root/demo_openrc.sh".format(contents))



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

@roles('controller', 'compute', 'network', 'storage')
def shrinkHome():
    # check if partitions already exist
    if 'str' in run("lvs"):
        print blue('Partitions already created. Nothing done on '+env.host)
    else:
        home_dir = run("lvs | awk '/home/ {print $2}'")
        run('umount /home')
        run('lvresize -L -{} /dev/mapper/{}-home'.format(
            env_config.partition['size_reduction_of_home'], home_dir))
        run('mkfs -t xfs -f /dev/{}/home'.format(home_dir))
        run('mount /home')

@roles('controller', 'network', 'compute', 'storage')
def prepGlusterFS():

    # check if partitions already exist
    if 'str' in run("lvs"):
        print blue('Partitions already created. Nothing done on '+env.host)
    else:
        STRIPE_NUMBER = env_config.partition['stripe_number']

        home_dir = run("lvs | awk '/home/ {print $2}'")

        run('lvcreate -i {} -I 8 -L {} {}'.format(
            STRIPE_NUMBER, env_config.partition['partition_size'], home_dir))

        run('lvrename /dev/{}/lvol0 strFile'.format(home_dir))

        run('lvcreate -i {} -I 8 -L {} {}'.format(
            STRIPE_NUMBER, env_config.partition['partition_size'], home_dir))

        run('lvrename /dev/{}/lvol0 strObj'.format(home_dir))

        run('lvcreate -i {} -I 8 -L {} {}'.format(
            STRIPE_NUMBER, env_config.partition['partition_size'], home_dir))

        run('lvrename /dev/{}/lvol0 strBlk'.format(home_dir))

        run('lvs')

@roles('controller','compute','network','storage')
# @roles('controller','compute','network')
def deploy():
	execute(renameHost)
	execute(installConfigureChrony)
	execute(install_packages)
	execute(installMariaDB)
	execute(disableFirewall)
	execute(disableSELinux)

        execute(shrinkHome)
        execute(prepGlusterFS)

        # reboot the machine
        with settings(warn_only=True):
            run('reboot')

@roles('controller','compute','network','storage')
def check_firewall():
    output = run("systemctl status firewalld | awk '/Active/ {print $2,$3}'", quiet=True)
    if any(status in output for status in ["inactive", "(dead)"]):
        print align_y("Firewall is: " + output)
    else:
        print align_n("Firewall is not dead. Show status:")
        run("systemctl status firewalld")
        
@roles('controller','compute','network','storage')
def check_selinux():
    output = run("getenforce")
    if "Disabled" in output:
        print align_y("SELINUX is " + output)
    else:            
        print align_n("Oh no! SELINUX is " + output)

def chronytdd():

	with settings(warn_only=True):
		print('checking var/log/messages for chronyd output')
		run('grep "$(date +"%b %d %H")" /var/log/messages | '
                    'grep -Ei "(chronyd)"')

	logging.info( " TDD on " +env.host)
	with settings(hide('warnings', 'running', 'stdout', 'stderr'),
                warn_only=True):

		servstatus = run('systemctl status chronyd.service |grep Active')
		date = run('date')
	logging.info(env.host +" Chrony is "+ servstatus)
	logging.info(env.host +" the date is "+ date)

        confFile = '/etc/chrony.conf'
        if servstatus.return_code == 0:
            saveConfigFile(confFile,'good')
        else:
            saveConfigFile(confFile,'bad')

@roles('controller','compute','network','storage')
# @roles('controller','compute','network')
def tdd():
        check_firewall()
        check_selinux()
        chronytdd()

