from __future__ import with_statement
from fabric.api import *
from fabric.contrib.files import append, exists, sed, put
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.state import output
from fabric.colors import green, red, blue
import string
import logging
import datetime
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
nicDictionary = env_config.nicDictionary

mode = 'normal'
if output['debug']:
    mode = 'debug'
########################## Deployment ########################################

#@roles('storage')
@roles('controller','compute','network','storage')
#@roles('controller','compute','network')
def mustDoOnHost():
    selinuxStatus=run("grep -w ^SELINUX /etc/selinux/config")
    if( "enforcing"  in  selinuxStatus):
        sed('/etc/selinux/config','SELINUX=enforcing','SELINUX=disabled')
        print(red(" REBOOT ")+green(" REBOOT ")+blue(" REBOOT ")+" REBOOT ")
        abort("you must reboot")
    with settings(warn_only=True):
        fwdstatus=run("systemctl is-active firewalld")
        if ( fwdstatus != "unknown"): 
            msg = 'Stop & Disable firewalld on ' + env.host
            runCheck(msg, 'systemctl stop firewalld ; systemctl disable firewalld')
    msg='Renaming host to %s' % env['host']
    run('hostnamectl set-hostname %s' % env['host'])
    printMessage("good", msg)
    logging.info(msg)
    with settings(warn_only=True):
        hostsStatus=run('grep controller /etc/hosts')
        if(hostsStatus.return_code != 0):
            msg="updating /etc/hosts"
            for host in nicDictionary.keys():
                newline = '%s\t%s' % (nicDictionary[host]['mgtIPADDR'], host)
                runCheck(msg,"echo '%s' >> /etc/hosts" % newline)


#@roles('storage')
@roles('controller','compute','network','storage')
#@roles('controller','compute','network')
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
        sed("/etc/chrony.conf","#allow 192.168/16","allow 192.168/16")
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
#@roles('storage')
@roles('controller','compute','network','storage')
#@roles('controller','compute','network')
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
    runCheck(msg, 'yum -y localinstall https://repos.fedorapeople.org/repos/openstack/openstack-juno/rdo-release-juno-1.noarch.rpm')
    logging.info(msg)


    # Install Crudini and wget
    print('installing crudini wget openstack-utils')
    run("yum -y install crudini wget openstack-utils")
    for item in ['crudini','wget']:
        var1=run('rpm -qa |grep %s ' %item)
        print blue(item +" is version "+ var1)
        logging.info(item +" is version "+ var1)

#@roles('storage')
@roles('controller')
def installMariaDB():
    if (env.host != "controller"):
        return
    # Install MariaDB

    msg = 'Get packages for MariaDB'
    runCheck(msg, 'yum -y install mariadb mariadb-server MySQL-python')
    logging.info(msg)

    # set the config file

    with cd('/etc/'):
        confFile = 'my.cnf'
        fileContents = env_config.my_cnf

        # set bind-address
        fileContents = fileContents.replace(\
                'BIND_ADDRESS',nicDictionary[env.host]['mgtIPADDR'])

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
    msg = 'start mariadb service'
    runCheck(msg, 'systemctl start mariadb.service')
 
#@roles('storage')
@roles('controller')
def secureDB():
    if (env.host != "controller"):
        return
    run('echo "DELETE FROM mysql.user WHERE User=\'\';" | mysql ')
    run('echo "DELETE FROM mysql.db WHERE Db=\'test\' " | mysql ')
    run("""echo "update mysql.user set password=password('%s') where user='root'; " |mysql """ %  env_config.passwd['ROOT_SECRET'])
    run('systemctl restart mariadb.service')
    run("""echo 'select user,password from mysql.user where user="root"' | mysql -u root -p%s """ % env_config.passwd['ROOT_SECRET'])
    printMessage("good","********** MySQL is installed, configured and secured *************")
    logging.info("********** MySQL is installed, configured and secured *************")

@roles('controller')
def tdd_DB():
    if (env.host != "controller"):
        return
    msg=" talk to database engine"
    result = run('mysql -u root -p%s -e "SHOW DATABASES"'% env_config.passwd['ROOT_SECRET'])
    if result.failed :
        printMessage("oops",msg)
    else:
        printMessage("good",msg)
        print("Here is a list of the current databases:\n %s"% result)


@roles('controller','compute','network','storage')
@with_settings(warn_only=True)
def test():
    pass


#@roles('storage')
@roles('controller','compute','network','storage')
#@roles('controller', 'compute', 'network')
def shrinkHome():
    # check if partitions already exist
    if 'str' in run("lvs"):
        print blue('Partitions already created. Nothing done on '+env.host)
    else:
        home_dir = run("mount | grep home|cut -d' ' -f1")
        runCheck('Unmount home', 'umount /home')
        runCheck('Resize home', 'lvresize -f -L -{} {}'.format(env_config.partition['size_reduction_of_home'], home_dir))
        runCheck('Put a filesystem back on home', 'mkfs -t xfs -f {}'.format(home_dir))
        runCheck('Remount home', 'mount /home')

#@roles('storage')
@roles('controller','compute','network','storage')
#@roles('controller','compute','network')
def tdd_lvs():
    msg = "TDD LVS Free space"
    lvsFree=run("vgs | awk '/centos/ {print $7}'")
    printMessage("good", msg +' '+ lvsFree)


#@roles('storage')
@roles('controller','compute','network','storage')
#@roles('controller', 'network', 'compute')
def prepGlusterFS():
# check if partitions already exist
    if 'str' in run("lvs"):
        print blue('Partitions already created. Nothing done on '+env.host)
    else:
        STRIPE_NUMBER = env_config.partition['stripe_number']
        home_dir = run("lvs | awk '/home/ {print $2}'")
        runCheck('Create glance partition', 'lvcreate -i {} -I 8 -L {} {}'.format(
            STRIPE_NUMBER, env_config.partition['glance_partition_size'], home_dir))
        runCheck('Rename glance partition', 'lvrename /dev/{}/lvol0 strFile'.format(home_dir))
        runCheck('Create swift partition', 'lvcreate -i {} -I 8 -L {} {}'.format(
            STRIPE_NUMBER, env_config.partition['swift_partition_size'], home_dir))
        runCheck('Rename swift partition', 'lvrename /dev/{}/lvol0 strObj'.format(home_dir))
        runCheck('Create cinder partition', 'lvcreate -i {} -I 8 -L {} {}'.format(
            STRIPE_NUMBER, env_config.partition['cinder_partition_size'], home_dir))
        runCheck('Rename cinder partition', 'lvrename /dev/{}/lvol0 strBlk'.format(home_dir))
        runCheck('List new partitions', 'fdisk -l|grep str')


def deploy():
    logging.info("Deploy begin at: {:%Y-%b-%d %H:%M:%S}".format(datetime.datetime.now()))
    execute(mustDoOnHost)
    execute(installConfigureChrony)
    execute(install_packages)
    execute(installMariaDB)
    execute(secureDB)
    execute(shrinkHome)
    execute(prepGlusterFS)
    logging.info("Deploy ended at: {:%Y-%b-%d %H:%M:%S}".format(datetime.datetime.now()))
    print align_y('Yeah we are done')


#@roles('storage')
@roles('controller','compute','network','storage')
#@roles('controller','compute','network')
def check_firewall():
    with settings(warn_only=True):
        fwdstatus=run("systemctl is-active firewalld")
        if ( fwdstatus == "unknown"): 
            msg="Verify firewall is down "
            printMessage("good",msg)
        
#@roles('storage')
@roles('controller','compute','network','storage')
#@roles('controller','compute','network')
def check_selinux():
    output = run("getenforce")
    if "Disabled" in output:
        print align_y("SELINUX is " + output)
    else:            
        print align_n("Oh no! SELINUX is " + output)

#@roles('storage')
@roles('controller','compute','network','storage')
#@roles('controller','compute','network')
def chronytdd():
    msg="verify chronyd"
    runCheck(msg,'chronyc sources -v ')

#@roles('storage')
@roles('controller','compute','network','storage')
# @roles('controller','compute','network')
def tdd():
    chronytdd()
    tdd_DB()
    tdd_lvs()
    run('fdisk -l|grep str')
    run('openstack-status')

