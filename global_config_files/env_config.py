import ConfigParser
import logging 
from subprocess import check_output, call
from fabric.api import run, sudo, env
from fabric.colors import red, green
from fabric.api import *

######################### Global variables ######################

if 'ipmi5' in check_output('echo $HOSTNAME',shell=True):
	# PRODUCTION
	roledefs = { 'compute' : ['root@compute1','root@compute2','root@compute3','root@compute4' ],
                 'network' : ['root@network'],
                 'storage' : ['root@storage'],
                 'controller' : ['root@controller']}
	logfilename='/opt/coop2015/coop2015/fabric.log'

else:
    # DEVELOPMENT

    # logging
    logfilename = '/tmp/test.log'


    global_config_location =  '../global_config_files/'

    # mariadb
    mariaDBmysqldSpecs = ['default-storage-engine=innodb',
                          'innodb_file_per_table',
                          'collation-server=utf8_general_ci',
                          'init-connect=SET NAMES utf8',
                          'character-set-server=utf8']
    # for the env dictionary
    roledefs = { 'compute' : ['root@computeVM'],
                 'network' : ['root@networkVM'],
                 'storage' : ['root@storageVM'],
                 'controller' : ['root@controllerVM']}

    roles = roledefs.keys()
    hosts = roledefs.values()

    # keystone data
    keystone = { 'ADMIN_EMAIL' : 'admin@example.com',
                 'DEMO_EMAIL' : 'demo@example.com'}

    # ntp
    ntpServers = ['time1.srv.ualberta.ca','time2.srv.ualberta.ca','time3.srv.ualberta.ca']

    # passwords
    passwd = { 'METADATA_SECRET' : '34m3t$3c43',
               'RABBIT_PASS' : '34RabbGuest43',
               'NOVA_DBPASS' : '34nova_db43',
               'NEUTRON_DBPASS' : '34neu43',
               'HEAT_DBPASS' : '34heat_db43',
               'GLANCE_DBPASS' : '34glance_db43',
               'SAHARA_DBPASS' : '34sahara_db43',
               'CINDER_DBPASS' : '34cinder_db43',
               'ADMIN_PASS' : '34adm43',
               'DEMO_PASS' : '34demo43',
               'KEYSTONE_DBPASS' : '34keydb43',
               'NOVA_PASS' : '34nova_ks43',
               'NEUTRON_PASS' : '34neu43',
               'HEAT_PASS' : '34heat_ks43',
               'GLANCE_PASS' : '34glance_ks43',
               'SAHARA_PASS' : '34sahara_ks43',
               'CINDER_PASS' : '34cinder_ks43',
               'SWIFT_PASS' : '34$w1f43',
               'TROVE_PASS' : '34Tr0v343',
               'TROVE_DBPASS' : '34Tr0v3db4s343'}

    """
    BASIC NETWORKING
    """

    controllerManagement = { 'DEVICE' : 'eth1',
                             'IPADDR' : '192.168.1.11',
                             'NETMASK' : '255.255.255.0'}

    controllerTunnels = { 'DEVICE' : 'eth2',
                          'IPADDR' : '192.168.2.11',
                          'NETMASK' : '255.255.255.0'}

    networkManagement = { 'DEVICE' : 'eth1',
                          'IPADDR' : '192.168.1.21',
                          'NETMASK' : '255.255.255.0'}

    networkTunnels = { 'DEVICE' : 'eth2',
                       'IPADDR' : '192.168.2.21',
                       'NETMASK' : '255.255.255.0'}

    networkExternal = { 'DEVICE' : 'eth3',
                        'TYPE' : 'Ethernet',
                        'ONBOOT' : '"yes"',
                        # 'BOOTPROTO' : '"dhcp"'}
                        'BOOTPROTO' : '"none"',
                        'IPADDR' : '192.168.3.21'}

    computeManagement = { 'DEVICE' : 'eth1',
                          'IPADDR' : '192.168.1.41',
                          'NETMASK' : '255.255.255.0'}

    computeTunnels = { 'DEVICE' : 'eth2',
                       'IPADDR' : '192.168.2.41',
                       'NETMASK' : '255.255.255.0'}

    storageManagement = {   'DEVICE' : 'eth1',
                            'IPADDR' : '192.168.1.51',
                            'NETMASK' : '255.255.255.0'}

    hosts = { controllerManagement['IPADDR'] : 'controller',
              networkManagement['IPADDR'] : 'network',
              storageManagement['IPADDR'] : 'storage'}

    # add the compute nodes to hosts config
    baseIP = computeManagement['IPADDR']
    for i, computeNode in enumerate(roledefs['compute']):
        # increment base ip
        baseIPListOfInts = [int(octet) for octet in baseIP.split('.')]
        baseIPListOfInts[-1] += i
        IP = "".join([str(octet)+'.' for octet in baseIPListOfInts])
        IP = IP[:-1] # remove last dot

        hosts[IP] = 'compute' + str(i+1)

    """
    KEYSTONE
    """

    # these are the variables whose values will be set in keystone.conf



    """
    NEUTRON
    """

    """
    Partitioning data
    """
    partition = {   'size_reduction_of_home' : '3.5G',
                    'partition_size' : '500M' }




    """
    admin-openrc and demo-openrc
    
    These scripts set up credentials for the keystone users
    admin and demo respectively. They export system variables that 
    allow the user to execute certain keystone CLI commands. They 
    are necessary every time the deployment scripts use keystone.


    We also save them as local text files, because it\'s sometimes useful
    to send them via scp to the hosts and source them from there.
    """

    admin_openrc = "export OS_TENANT_NAME=admin; " +\
            "export OS_USERNAME=admin; " + \
            "export OS_PASSWORD={}; ".format(passwd['ADMIN_PASS']) + \
            "export OS_AUTH_URL=http://controller:35357/v2.0"

    demo_openrc = "export OS_TENANT_NAME=demo; " +\
            "export OS_USERNAME=demo; " + \
            "export OS_PASSWORD={}; ".format(passwd['DEMO_PASS']) + \
            "export OS_AUTH_URL=http://controller:5000/v2.0"

    # save them as local files; clobber if necessary
    admin_openrc_local = '../global_config_files/admin-openrc.sh' 
    demo_openrc_local = '../global_config_files/demo-openrc.sh' 

    call("echo '{}' >{}".format(admin_openrc,admin_openrc_local),shell=True)
    call("echo '{}' >{}".format(demo_openrc,demo_openrc_local),shell=True)
