from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.contrib.files import append
import logging
import string

import sys
sys.path.append('..')
import env_config
import myLib
from myLib import runCheck, createDatabaseScript, set_parameter
from myLib import run_v, align_n, align_y, saveConfigFile

import glusterLib

############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

glance_api_config_file = "/etc/glance/glance-api.conf"
glance_registry_config_file = "/etc/glance/glance-registry.conf"
glanceGlusterDir = "mnt/gluster/glance/images"

######################## Deployment ########################################


@roles('controller')
def setup_glance_database():

    GLANCE_DBPASS=passwd['GLANCE_DBPASS']

    mysql_commands = createDatabaseScript('glance',GLANCE_DBPASS)
    
    msg = "Create database for keystone"
    runCheck(msg, 'echo "' + mysql_commands + '" | mysql -u root -p"%s" ' % env_config.passwd['ROOT_SECRET'])
    run(' mysql -u root -p"%s" -e  "select host, user, password from user where user=\'glance\'" mysql' % env_config.passwd['ROOT_SECRET'])


@roles('controller')
def setup_glance_keystone():
    """
    Set up Keystone credentials for Glance

    Create (a) a user and a service called 'glance', and 
    (b) an endpoint for the 'glance' service
    """

    GLANCE_PASS = passwd['GLANCE_PASS']
    # get admin credentials to run the CLI commands
    credentials = env_config.admin_openrc

    with prefix(credentials):
        # before each creation, we check a list to avoid duplicates
        if 'glance' not in run("keystone user-list"):
            msg = "Create user glance"
            runCheck(msg, "keystone user-create --name glance --pass {}"\
                    .format(GLANCE_PASS))

            msg = "Give the user glance the role of admin"
            runCheck(msg, "keystone user-role-add --user glance "
                    "--tenant service --role admin")
        else:
            print blue("User glance already created. Do nothing")

        if 'glance' not in run("keystone service-list"):
            msg = "Create service glance"
            runCheck(msg, "keystone service-create --name glance --type image "
                    "--description 'OpenStack Image Service'")
        else:
            print blue("Service glance already created. Do nothing")

        if 'http://controller:9292' not in run("keystone endpoint-list"):
            msg = "Create endpoint for service glance"
            runCheck(msg, "keystone endpoint-create "
                    "--service-id $(keystone service-list "
                    "| awk '/ image / {print $2}') "
                    "--publicurl http://controller:9292 "
                    "--internalurl http://controller:9292 "
                    "--adminurl http://controller:9292 "
                    "--region regionOne")
        else:
            print blue("Enpoint for service glance already created. "
                    "Nothing done")

@roles('controller')
def setup_glance_config_files():

    GLANCE_DBPASS = passwd['GLANCE_DBPASS']
    GLANCE_PASS = passwd['GLANCE_PASS']
    
    set_parameter(glance_api_config_file, 'database', 'connection', \
            'mysql://glance:{}@controller/glance'.format(GLANCE_DBPASS))

    set_parameter(glance_api_config_file, 'keystone_authtoken', 'auth_uri', \
            'http://controller:5000/v2.0')

    set_parameter(glance_api_config_file, 'keystone_authtoken', 'identity_uri', \
            'http://controller:35357') 

    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_tenant_name', 'service') 

    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_user', 'glance') 

    set_parameter(glance_api_config_file, 'keystone_authtoken', 'admin_password', GLANCE_PASS) 

    set_parameter(glance_api_config_file, 'paste_deploy', 'flavor', 'keystone')

    set_parameter(glance_api_config_file, 'glance_store', 'default_store', 'file')

    # this line sets up the default filesystem. This will be overwritten by the Gluster setup
    set_parameter(glance_api_config_file, 'glance_store', 'filesystem_store_datadir', \
            '/var/lib/glance/images/')

    set_parameter(glance_api_config_file, 'DEFAULT', 'notification_driver', 'noop')

    set_parameter(glance_api_config_file, 'DEFAULT', 'verbose', 'True')

    set_parameter(glance_registry_config_file, 'database', 'connection', \
            'mysql://glance:{}@controller/glance'.format(GLANCE_DBPASS))

    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'auth_uri', \
            'http://controller:5000/v2.0')

    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'identity_uri', \
            'http://controller:35357') 

    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'admin_tenant_name', \
            'service') 

    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'admin_user', \
            'glance')   

    set_parameter(glance_registry_config_file, 'keystone_authtoken', 'admin_password', \
            GLANCE_PASS)   

    set_parameter(glance_registry_config_file, 'paste_deploy', 'flavor', 'keystone')

    set_parameter(glance_registry_config_file, 'DEFAULT', 'notification_driver', 'noop')

    set_parameter(glance_registry_config_file, 'DEFAULT', 'verbose', 'True')



@roles('controller')
def populate_database():
    msg = "Populate database"
    runCheck(msg, "su -s /bin/sh -c 'glance-manage db_sync' glance")
    run('mysql -u root -p%s -e "SHOW DATABASES"'% env_config.passwd['ROOT_SECRET'])    

@roles('controller')
def start_glance_services():
    msg = "Enable glance services"
    runCheck(msg, "systemctl enable openstack-glance-api.service "
            "openstack-glance-registry.service")
    msg = "Start glance services"
    runCheck(msg, "systemctl start openstack-glance-api.service "
            "openstack-glance-registry.service")


@roles('controller')
def setup_GlusterFS_Glance():
    """
    Configure the file path for the Glance Gluster volume
    """
    run("mount |grep '^/'")
    # change the path that Glance uses for its file system
    msg = 'Configure Glance to use Gluster'
    glusterDir = glanceGlusterDir
    runCheck(msg, "crudini --set /etc/glance/glance-api.conf glance_store " + \
            "filesystem_store_datadir {}".format(glusterDir))

    msg = 'Create local directory on the brick'
    runCheck(msg, 'mkdir -p {}'.format(glusterDir))

    msg = 'Set ownership of the directory'
    runCheck(msg, 'chown -R glance:glance {}'.format(glusterDir))

    msg = 'Restart Glance'
    runCheck(msg, 'systemctl restart openstack-glance-api') 
    run("mount |grep '^/'")


@roles('controller')
def setup_glance_api_conf_file():
    set_parameter(glance_api_config_file, 'glance_store', 'filesystem_store_datadir', 
            glanceGlusterDir)

@roles('controller')
def install_packages():
    # Install packages
    msg = "Install OpenStack Glance packages"
    runCheck(msg, "yum install -y openstack-glance python-glanceclient")
   
############################## Deployment #####################################

def deploy():
    # Setup gluster
    #partition = 'strFile'
    #volume = 'glance_volume'
    #brick = 'glance_brick'

    #execute(glusterLib.setup_gluster, partition, brick)
    #execute(glusterLib.probe, env_config.hosts)
    #execute(glusterLib.create_volume, brick, volume, env_config.hosts)
    #execute(glusterLib.mount, volume)

    # Setup glance
    execute(install_packages)
    execute(setup_glance_database)
    execute(setup_glance_keystone)
    execute(setup_glance_config_files)
    execute(populate_database)
    execute(start_glance_services)

    # Customize gluster to glance
    execute(setup_glance_api_conf_file)
    execute(setup_GlusterFS_Glance)
    execute(start_glance_services)

################################# TDD #########################################



@roles('controller')
def imageCreationTDD():
    """
    TDD: Try to create an image and see if it shows up in all hosts
    """

    result = 'OK'
    
    msg = 'Retrieve instance image from the cirros website'
    run_v("mkdir /tmp/images")
    url = "http://download.cirros-cloud.net/0.3.3/cirros-0.3.3-x86_64-disk.img"
    runCheck(msg, "wget -qP /tmp/images " + url)

    with prefix(env_config.admin_openrc):

        msg = 'Create glance image'
        runCheck(msg, "glance image-create --name 'cirros-test' "
                "--file /tmp/images/cirros-0.3.3-x86_64-disk.img "
                "--disk-format qcow2 "
                "--container-format bare "
                "--is-public True "
                )

        msg = 'List images'
        output = runCheck(msg, "glance image-list | grep 'cirros-test'")
        # imageIDs = [l.split()[1] for l in output.splitlines() if 'cirros-test' in l]
        imageID = run("glance image-list | grep 'cirros-test' | awk '{print $2}'") 
        
        if len(output.splitlines()) > 1:
            align_n("There seems to be more than one 'cirros-test'!")
            return 'FAIL'

        if output:
            print(align_y("Successfully installed cirros image"))
        else:
            print(align_n("Couldn't install cirros image"))
            return 'FAIL'

    # check the hosts and see if the image file
    # was distributed among all of them

    results = execute(glusterTDD,imageID).values()
    for r in results:
        if r == 'FAIL':
            result = 'FAIL'

    msg = 'Clear local files'
    runCheck(msg, "rm -r /tmp/images")

    return result

@roles(env_config.roles)
def glusterTDD(imageID):
    """
    TDD: Check the bricks and see if the image is there
    """
    result = 'OK'

    imageDir = glanceGlusterDir

    if run("[ -e {} ]".format(imageDir)).return_code != 0:
        print red("Directory {} does not exist in host {}!".format(
            imageDir, env.host))
        return 'FAIL'


    imagesInDir = runCheck("See inside directory", "ls " + imageDir)

    if not imagesInDir:
        print align_n('Directory seems to be empty in host' + env.host)
        result = 'FAIL'
    elif imageID not in imagesInDir:
        print align_n('The image requested '
                'is not in the glance brick in host ' + env.host)
        print 'Image requested: ', blue(imageID)
        print 'Contents of directory: ', red(imagesInDir)
        result = 'FAIL'
    else:
        print align_y('Can see the image in host ' + env.host)

    return result

@roles('controller')
def tdd1():
    run('mysql -u root -p%s -D mysql -e  "show databases" mysql' % passwd['ROOT_SECRET'])
    run('mysql -u root -p%s -D mysql -e  "select User, Host, Password  from user" mysql' % passwd['ROOT_SECRET'])
    run('mysql -u root -p%s -D mysql -e  "show tables" glance' % passwd['ROOT_SECRET'])
    run('source admin-openrc.sh; keystone user-list')
    run('source admin-openrc.sh; keystone tenant-list')
    run('rpm -qa |grep "openstack-glance\|python-glanceclient"')
    run('. admin-openrc.sh;  glance image-list')
    print(green('[GOOD]')+ ' glance service is fully functional')

@roles('controller')
def tdd():
    # save results of the tdds in a list
    results = list()

    res = myLib.database_check('glance')
    results.append(res)

    res = myLib.keystone_check('glance')
    results.append(res)

    res = imageCreationTDD()
    results.append(res)

    # check if any of the functions failed
    # and set status accordingly
    if any([r == 'FAIL' for r in results]):
        status = 'bad'
    else:
        status = 'good'

    # save config files
    confFile = "/etc/glance/glance-api.conf"
    saveConfigFile(confFile, status)
    confFile = "/etc/glance/glance-registry.conf"
    saveConfigFile(confFile, status)

