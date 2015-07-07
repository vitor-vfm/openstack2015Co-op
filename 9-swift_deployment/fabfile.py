from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.contrib.files import append, put
import logging
import string

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, set_parameter, printMessage
from myLib import database_check, keystone_check, align_y, align_n

import glusterLib

############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

######################## Deployment ########################################

@roles('controller')
def setKeystoneController():
    """
    Create user, roles and tenants for Swift
    """

    with prefix(env_config.admin_openrc):

        if 'swift' not in sudo("keystone user-list"):
            msg = "Create user swift"
            runCheck(msg, "keystone user-create --name swift --pass {}".format(passwd['SWIFT_PASS']))

            msg = "Add the role of admin to user swift"
            runCheck(msg, "keystone user-role-add --user swift --tenant service --role admin")
        else:
            print blue('swift is already a user. Do nothing')

        if 'swift' not in sudo("keystone service-list"):
            msg = "Create service swift"
            runCheck(msg, 'keystone service-create --name swift --type object-store --description "OpenStack Object Storage"')
        else:
            print blue('swift is already a service. Do nothing')

        if 'http://controller:8080/' not in sudo("keystone endpoint-list"):
            msg = "Create endpoint for service swift"
            command = "keystone endpoint-create " +\
                    "--service-id $(keystone service-list | awk '/ object-store / {print $2}') " +\
                    "--publicurl 'http://controller:8080/v1/AUTH_%(tenant_id)s' " +\
                    "--internalurl 'http://controller:8080/v1/AUTH_%(tenant_id)s' " +\
                    "--adminurl http://controller:8080/ " +\
                    "--region regionOne"
            print 'command : ',command
            runCheck(msg, command)
        else:
            print blue('8080 is already an endpoint. Do nothing')

@roles('controller')
def installPackagesController():
    msg = "Install Packages on controller"
    # package python-keystone-auth-token was changed to python-keystoneclient
    runCheck(msg, "yum -y install openstack-swift-proxy python-swiftclient "
            "python-keystonemiddleware memcached")


@roles('controller')
def configureController():

    confFile = '/etc/swift/proxy-server.conf'
    localFile = 'proxy-server.conf'

    # proxyServerConf is a config file made based on this model: 
    # https://raw.githubusercontent.com/openstack/swift/stable/juno/etc/proxy-server.conf-sample

    msg = "Put base {} on controller".format(confFile)
    out = put(localFile,confFile)
    if out.succeeded:
        printMessage('good',msg)
    else:
        printMessage('oops',msg)

    # set parameters
    set_parameter(confFile,'DEFAULT','bind_port','8080')
    set_parameter(confFile,'DEFAULT','user','swift')
    set_parameter(confFile,'DEFAULT','swift_dir','/etc/swift')


    set_parameter(confFile,'pipeline:main','pipeline',"'authtoken cache healthcheck keystoneauth proxy-logging proxy-server'")
    set_parameter(confFile,'app:proxy-server','allow_account_management','true')
    set_parameter(confFile,'app:proxy-server','account_autocreate','true')

    set_parameter(confFile,'filter:keystoneauth','use','egg:swift#keystoneauth')
    set_parameter(confFile,'filter:keystoneauth','operator_roles','admin,_member_')

    set_parameter(confFile,'filter:authtoken','paste.filter_factory','keystonemiddleware.auth_token:filter_factory')
    set_parameter(confFile,'filter:authtoken','auth_uri','http://controller:5000/v2.0')
    set_parameter(confFile,'filter:authtoken','identity_uri','http://controller:35357')
    set_parameter(confFile,'filter:authtoken','admin_tenant_name','service')
    set_parameter(confFile,'filter:authtoken','admin_user','swift')
    set_parameter(confFile,'filter:authtoken','admin_password',passwd['SWIFT_PASS'])
    set_parameter(confFile,'filter:authtoken','delay_auth_decision','true')

    set_parameter(confFile,'filter:cache','memcache_servers','127.0.0.1:11211')

@roles('controller')
def startServicesController():
    msg = 'Start the Object Storage proxy service on the controller node'
    runCheck(msg, "systemctl enable openstack-swift-proxy.service memcached.service")
    msg = 'Enable the Object Storage proxy service on the controller node'
    runCheck(msg, "systemctl start openstack-swift-proxy.service memcached.service")

@roles('controller')
def controllerDeploy():

    execute(installPackagesController)
    execute(setKeystoneController)
    execute(configureController)
    execute(startServicesController)

# STORAGE NODE

############################### GLUSTER ##################################

@roles('storage')
def setGluster():
    """
    Set the storage nodes to use the Gluster brick

    Based on the gluster-swift quick start guide:
    https://github.com/gluster/gluster-swift/blob/master/doc/markdown/quick_start_guide.md

    Assumes GlusterFS packages are installed
    """
    execute(glusterLib.setup_gluster, env_config.swiftPartition, env_config.swiftBrick)
    execute(glusterLib.probe, env_config.hosts)
    execute(glusterLib.create_volume, env_config.swiftBrick, env_config.swiftVolume, env_config.hosts)
    execute(glusterLib.mount, env_config.swiftVolume)


##########################################################################

@roles('storage')
def glusterswiftSetup():
    """
    Configures gluster-swift

    Based on the gluster-swift quick start guide:
    https://github.com/gluster/gluster-swift/blob/master/doc/markdown/quick_start_guide.md

    Assumes GlusterFS packages are installed
    """

    msg = 'Install gluster-swift'
    runCheck(msg,
            'yum install -y http://ftp.redhat.com/pub/redhat/linux/enterprise/6Server/en/RHS/SRPMS/gluster-swift-1.4.8-4.el6.src.rpm')
            #'yum install -y https://repos.fedorapeople.org/repos/openstack/openstack-juno/epel-7/openstack-swift-2.2.0-1.el7.centos.noarch.rpm')
            #'yum install -y https://launchpad.net/swift/juno/2.2.0/+download/swift-2.2.0.tar.gz')
            #'yum install -y https://launchpad.net/swiftonfile/havana/1.10.0-2/+download/glusterfs-openstack-swift-1.10.0-2.5.el6.noarch.rpm')

    msg = 'Make sure that gluster-swift is enabled at system startup'
    runCheck(msg, 
            "chkconfig openstack-swift-proxy on\n"
            "chkconfig openstack-swift-account on\n"
            "chkconfig openstack-swift-container on\n"
            "chkconfig openstack-swift-object on")

    # Fedora 19 Adjustment - might or might not be necessary for CentOS 7

    # Currently gluster-swift requires its processes to be run as root. 
    # We need to edit the openstack-swift-*.service files in 
    # /etc/systemd/system/multi-user.target.wants and change the User entry value to root.

    services = ['proxy','account','container','object']
    for service in services:
        confFile = '/etc/systemd/system/multi-user.target.wants/openstack-swift-%s.service' % (service)
        set_parameter(confFile, '', 'User', 'root')

    msg = 'Restart services'
    runCheck(msg, 'systemctl --system daemon-reload')

    # copy the *.conf-gluster files to *.conf files
    with cd('/etc/swift/'):
        msg = 'copy the *.conf-gluster files to *.conf files'
        runCheck(msg, 
                'for tmpl in *.conf-gluster ; do cp ${tmpl} ${tmpl%.*}.conf; done')

    msg = 'Generate the ring files'
    runCheck(msg,
            'gluster-swift-gen-builders '+env_config.swiftVolume)

    msg = 'Expose the gluster volume'
    runCheck(msg,
            'cd /etc/swift; /usr/bin/gluster-swift-gen-builders myvolume')

    for service in services:
        msg = 'Start service ' + service
        runCheck(msg, 'service %s start' % service)

@roles('storage')
def configurersyncd():

    fileContents = env_config.rsyncd_conf

    # replace variables
    fileContents = fileContents.replace('MANAGEMENT_INTERFACE_IP_ADDRESS', 
            env_config.storageManagement['IPADDR'])

    devicepath = env_config.glusterPath + env_config.swiftVolume
    fileContents = fileContents.replace('PATH', devicepath)

    out = append('/etc/rsynd.conf', fileContents)
    if out:
        print align_n("Error appending to rsyncd.conf")
        logging.error(out)
    else:
        print align_y("Success appending to rsyncd.conf")
        logging.info(out)

    msg= 'Enable rsyncd service'
    runCheck(msg, 'systemctl enable rsyncd.service')
    msg= 'Start rsyncd service'
    runCheck(msg, 'systemctl start rsyncd.service')

@roles('storage')
def configureStorage():
    """
    Set the account-, container-, and object-server conf files
    """

    serverConfFiles = ['account-server.conf','container-server.conf','object-server.conf']
    ip = env_config.storageManagement['IPADDR']
    devicepath = env_config.glusterPath + env_config.swiftVolume
    # devicepath = '/srv/node'

    # save base files into the host
    for fil in serverConfFiles:
        remotefile = '/etc/swift/' + fil
        out = put(fil,remotefile)
        msg = "Save file {} on host {}".format(fil,env.host)
        if out.succeeded:
            printMessage('good', msg)
        else:
            printMessage('oops', msg)

    # set variables that are the same in all conf files
    for confFile in serverConfFiles:
        set_parameter('/etc/swift/' + confFile,'DEFAULT','bind_ip',ip)
        set_parameter('/etc/swift/' + confFile,'DEFAULT','user','swift')
        set_parameter('/etc/swift/' + confFile,'DEFAULT','swift_dir','/etc/swift')
        set_parameter('/etc/swift/' + confFile,'DEFAULT','devices',devicepath)

        set_parameter('/etc/swift/' + confFile,'filter:recon','recon_cache_path','/var/cache/swift')

        # when the device isn't an actual disk, 
        # we need to set mount_check to false
        set_parameter('/etc/swift/' + confFile,'DEFAULT','mount_check','false')


    # Edit the account-server.conf file
    confFile = '/etc/swift/' + serverConfFiles[0]

    set_parameter(confFile,'DEFAULT','bind_port','6002')
    set_parameter(confFile,'pipeline:main','pipeline',"'healthcheck recon account-server'")

    # Edit the /etc/swift/container-server.conf file
    confFile = '/etc/swift/' + serverConfFiles[1]

    set_parameter(confFile,'DEFAULT','bind_port','6001')
    set_parameter(confFile,'pipeline:main','pipeline',"'healthcheck recon container-server'")

    # Edit the /etc/swift/object-server.conf
    confFile = '/etc/swift/' + serverConfFiles[2]

    set_parameter(confFile,'DEFAULT','bind_port','6000')
    set_parameter(confFile,'pipeline:main','pipeline',"'healthcheck recon object-server'")



    msg = 'Ensure proper ownership of the mount point directory structure'
    runCheck(msg, "chown -R swift:swift {}".format(devicepath))

    msg = 'Create the recon directory'
    runCheck(msg, "mkdir -p /var/cache/swift")
    msg = 'Ensure proper ownership of recon directory'
    runCheck(msg, " chown -R swift:swift /var/cache/swift")

def deleteRings():
    pass

def createRing(typeRing,port,IP,deviceName,deviceWeight):
    # ASSUMES A SINGLE DEVICE ON STORAGE NODE

    port = str(port)

    with cd('/etc/swift/'):
        # verify if ring is already there
        out = run("swift-ring-builder %s.builder" % (typeRing),quiet=True)
        if 'does not exist' in out:
            # ring is not created yet

            # Create the base *.builder file
            run("swift-ring-builder %s.builder create 10 3 1" % (typeRing))

            # Add node to the ring
            run("swift-ring-builder %s.builder add r1z1-%s:%s/%s %s" % 
                    (typeRing,IP,port,deviceName,deviceWeight))

            # rebalance ring
            run("swift-ring-builder %s.builder rebalance" % (typeRing))
        else:
            print blue("Ring {} already exists. Nothing done".format(typeRing))

        run("ls")

    msg = 'Restart proxy server service'
    runCheck(msg, 'systemctl restart openstack-swift-proxy.service')

@roles('controller')
def grabGZfiles():
    """
    Grabs the three .gz files from the controller node and
    returns their contents as a dictionary
    """

    filenames = ['account.ring.gz','container.ring.gz','object.ring.gz']

    with cd('/etc/swift'):
        for filename in filenames:
            get(filename)

@roles('storage')
def saveGZfiles():
    """
    Saves the three .gz files in the storage node
    """
    filenames = ['account.ring.gz','container.ring.gz','object.ring.gz']

    with cd('/etc/swift'):
        for filename in filenames:
            put(local_path='root@controller/'+filename,
                    remote_path='/etc/swift/'+filename)

@roles('controller')
def createInitialRings():
    """
    Create 3 initial rings as a test
    """

    managementIP = env_config.storageManagement['IPADDR']
    deviceLocation = env_config.glusterPath + env_config.swiftVolume
    deviceName = "rings"
    deviceWeight = '100'
    # deviceName = "/dev/sdd"

    msg = 'create new directory for the rings'
    runCheck(msg, 'mkdir -p %s/%s' % (deviceLocation, deviceName))

    # create account ring
    createRing('account',6002,managementIP,deviceName,deviceWeight)

    # create container ring
    createRing('container',6001,managementIP,deviceName,deviceWeight)

    # create object ring
    createRing('object',6000,managementIP,deviceName,deviceWeight)

    execute(grabGZfiles)
    execute(saveGZfiles)

@roles('storage')
def startServicesStorage():
    """
    Start the Object Storage services and configure them to start when the system boots

    Enabling the services currently doesn't work; returns "Invalid argument"
    """

    msg = 'Enable account services'
    # runCheck(msg, "systemctl enable openstack-swift-account.service openstack-swift-account-auditor.service openstack-swift-account-reaper.service openstack-swift-account-replicator.service")
    msg = 'Start account services'
    runCheck(msg, "systemctl start openstack-swift-account.service openstack-swift-account-auditor.service openstack-swift-account-reaper.service openstack-swift-account-replicator.service")

    msg = 'Enable container services'
    # runCheck(msg, "systemctl enable openstack-swift-container.service openstack-swift-container-auditor.service openstack-swift-container-replicator.service openstack-swift-container-updater.service")
    msg = 'Start container services'
    runCheck(msg, "systemctl start openstack-swift-container.service openstack-swift-container-auditor.service openstack-swift-container-replicator.service openstack-swift-container-updater.service")

    msg = 'Enable object services'
    # runCheck(msg, "systemctl enable openstack-swift-object.service openstack-swift-object-auditor.service openstack-swift-object-replicator.service openstack-swift-object-updater.service")
    msg = 'Start object services'
    runCheck(msg, "systemctl start openstack-swift-object.service openstack-swift-object-auditor.service openstack-swift-object-replicator.service openstack-swift-object-updater.service")



@roles('storage', 'controller')
def finalizeInstallation():
    """
    Final steps of the installation, such as setting swift.conf and restarting services
    """

    confFile = '/etc/swift/swift.conf'
    localFile = 'swift.conf'

    msg = 'Put base config file on node'
    out = put(localFile,confFile)
    if out.succeeded:
        printMessage('good',msg)
    else:
        printMessage('oops',msg)


    # In the [swift-hash] section, configure the hash path prefix and suffix for your environment
    set_parameter(confFile,'swift-hash','swift_hash_path_prefix',env_config.hashPathPrefix)
    set_parameter(confFile,'swift-hash','swift_hash_path_suffix',env_config.hashPathSuffix)

    # In the [storage-policy:0] section, configure the default storage policy
    set_parameter(confFile,'storage-policy:0','name','Policy-0')
    set_parameter(confFile,'storage-policy:0','default','yes')

    msg = 'Change ownership of the configuration directory to swift'
    run("chown -R swift:swift /etc/swift")

    execute(startServicesController)
    execute(startServicesStorage)

    

@roles('storage')
def installPackagesStorage():
    msg = 'Install packages on host ' + env.host
    runCheck(msg, "yum -y install openstack-swift-account openstack-swift-container openstack-swift-object")



@roles('storage')
def storageDeploy():

    execute(installPackagesStorage)

    execute(setGluster)

    execute(createInitialRings)

    execute(configurersyncd)    
    execute(configureStorage)    

    execute(finalizeInstallation)

# GENERAL DEPLOYMENT

def deploy():
    execute(controllerDeploy)
    execute(storageDeploy)       

######################################## TDD #########################################

@roles('controller')
def testFile():
    """
    TDD: Upload and download back a test file using the CLI
    """
    testcontainer = 'demo-container1'
    testfile = 'FILE'

    # get creadentials for demo user
    with prefix(env_config.demo_openrc):

        msg = "Create local test file"
        out = runCheck(msg, "echo 'Test file for Swift TDD\nline1\nline2\nline3' >" + testfile)

        msg = 'Upload test file'
        runCheck(msg, "swift upload %s %s" % (testcontainer,testfile))

        msg = 'See new container'
        runCheck(msg, "swift list | grep " + testcontainer)

        msg = 'Download test file'
        runCheck(msg, "swift download %s %s" % (testcontainer,testfile))

        msg = 'Show test file'
        runCheck(msg, "cat "+testfile)

        msg = 'Remove test file'
        runCheck(msg, 'rm ' + testfile)

@roles(env_config.roles)
def peerStatus():
    """
    TDD: Check gluster peer status
    """
    expectedNumPeers = sum([len(rolelist) for rolelist in env.roledefs.values()]) - 1
    numPeersConnected = int(run('gluster peer status | '
                   'grep -c "Peer in Cluster (Connected)"'))
    if numPeersConnected != expectedNumPeers:
        print align_n('Problem on host '+env.host)
        run('gluster peer status')
    else:
        print align_y('Peer status on host %s OK')



@roles('storage')
def glusterTDD():
    """
    TDD: check if the contents of the Gluster brick are the same on all nodes
    """

    @roles('controller','network','storage','compute')
    def _glusterTDD():
        "Grab the contents of the gluster brick for each host"
        directory = env_config.glusterPath + env_config.swiftVolume 
        with cd(directory):
            msg = 'Get contents of brick on '+env.host
            contents = runCheck(msg, "ls -a")
        return contents

    results = execute(_glusterTDD)
    hosts = results.keys()

    for i, host in enumerate(hosts):
        for otherHost in hosts[i+1:]:
            if results[host] != results[otherHost]:
                print align_n('Hosts %s and %s have different contents' % (host,otherHost))
            else:
                print align_y('Hosts %s and %s OK' % (host,otherHost))
            


@roles('storage')
def curlTDD():
    """
    TDD: make some curl operations and check their results
    """

    with prefix(env_config.admin_openrc):
        msg = 'Get storage URL and token'
        url, token = runCheck(msg, "swift stat -v | awk '/StorageURL/ {print $2} /Auth Token/ {print $3}'").splitlines()

    msg = 'Show containers'
    runCheck(msg, 'curl -v -X GET -H "X-Auth-Token: %s" %s' % (token,url))

    msg = 'Make a container creation request'
    out = runCheck(msg, 'curl -v -X PUT -H "X-Auth-Token: %s" %s/mycontainer' % (token,url))
    if 'HTTP/1.1 201 Created' in out:
        print align_y('Container creation succeeded')
    else:
        print align_n('Problem in the container creation')

    run('echo "Now testing object creation" >mytestfile')
    msg = 'Request object creation'
    runCheck(msg, 'curl -v -X PUT -T mytestfile -H "X-Auth-Token: %s" %s/mycontainer/mytestfile' % (token, url))

    msg = 'Request the new object'
    runCheck(msg, 'curl -v -X GET -o newfile -H "X-Auth-Token: %s" %s/mycontainer/mytestfile' % (token, url))

    diff = run('diff newfile mytestfile', quiet=True)
    if diff:
        print align_n('File downloaded and local file are not the same')
        run('cat newfile')
        run('cat mytestfile')
    else:
        print align_y('File downloaded and local file are the same')

    run('rm newfile mytestfile')

def tdd():
    with settings(warn_only=True):
        execute(keystone_check,'swift',roles=['controller'])
        execute(testFile)
        execute(curlTDD)
        execute(peerStatus)
        execute(glusterTDD)
