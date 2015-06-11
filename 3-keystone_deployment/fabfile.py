from __future__ import with_statement
from fabric.decorators import with_settings
from fabric.api import *
from fabric.context_managers import cd
from fabric.colors import green, red
import string
import subprocess
import logging

import sys
sys.path.append('../global_config_files')
sys.path.append('..')
import env_config
from myLib import *

########################## Configuring Environment ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

@hosts('localhost')
def read_config_file_with_sections(file_location):
    # reads a config file and returns a dictionary mapping
    # headers (section names) to a list of the lines that follow the header

    file_dict = dict()
    config_file_lines = open(file_location, 'r').readlines()
    # ignore comments
    # remove \n from the end
    config_file_lines = [line[:-1] for line in config_file_lines if '#' not in line]

    # find on config_file_lines where the headers are
    headers = [line for line in config_file_lines if '[' in  line and ']' in line]

    for i, header in enumerate(headers[:-1]):
        header_index = config_file_lines.index(header)
        next_header = headers[i+1]
        next_header_index = config_file_lines.index(next_header)
        file_dict[header] = config_file_lines[ (header_index+1):(next_header_index)] 

    # put last header
    last_index = config_file_lines.index(headers[-1])
    file_dict[ headers[-1] ] = config_file_lines[last_index+1:]

    return file_dict


# config files for user Usr
admin_email = env_config.keystone['ADMIN_EMAIL']
demo_email = env_config.keystone['DEMO_EMAIL']

################### Deployment ########################################

def setKeystoneConfigFile(admin_token,password):
    """
    Configure variables in keystone.conf
    """

    confFile= '/etc/keystone/keystone.conf'

    msg = 'Make a backup of keystone.conf'
    runCheck(msg, "cp {} {}.back12".format(confFile,confFile))

    # for testing
    confFile += '.back12'

    crudiniCommands = "\n" + \
    "crudini --set {} DEFAULT admin_token {}\n""".format(confFile,admin_token) + \
    "crudini --set {} DEFAULT verbose True\n".format(confFile) + \
    "crudini --set {} database connection mysql://keystone:{}@controller/keystone\n".format(confFile,password) + \
    "crudini --set {} token provider keystone.token.providers.uuid.Provider\n".format(confFile) + \
    "crudini --set {} token driver keystone.token.persistence.backends.sql.Token\n".format(confFile) + \
    "crudini --set {} revoke driver keystone.contrib.revoke.backends.sql.Revoke\n".format(confFile)

    msg = 'Set up variables in {} using crudini'.format(confFile)
    runCheck(msg, crudiniCommands)

    print 'New file: '
    run('cat ' + confFile + " | egrep -v '^#' | egrep -v '^$'")

@roles('controller')
def setupKeystone():

    msg = "Restart MariaDB service"
    out = runCheck(msg, "systemctl restart mariadb")

    if out.return_code != 0:
        # we need mariadb working in order to proceed
        sys.exit("Failed to restart mariadb")

    # get Keystone database creation scripts
    databaseCreation = createDatabaseScript('keystone',passwd['KEYSTONE_DBPASS'])
    
    msg = "Create database for keystone"
    runCheck(msg, 'echo "' + databaseCreation + '" | mysql -u root')
  
    msg = "Generate an admin token"
    admin_token = runCheck(msg, 'openssl rand -hex 10')

    msg = "Install keystone packages"
    runCheck(msg, "yum -y install openstack-keystone python-keystoneclient")
    
    # set config files
    setKeystoneConfigFile(admin_token,passwd['KEYSTONE_DBPASS'])
    # from this point on script is not fixed yet
    return
    
    # create generic certificates and keys and restrict access to the associated files
    run("keystone-manage pki_setup --keystone-user keystone --keystone-group keystone")
    run("chown -R keystone:keystone /var/log/keystone")
    run("chown -R keystone:keystone /etc/keystone/ssl")
    run("chmod -R o-rwx /etc/keystone/ssl")

    msg = 'Populate the Identity service database'
    runCheck("su -s /bin/sh -c 'keystone-manage db_sync' keystone")


    # start the Identity service and configure it to start when the system boots
    if run("systemctl enable openstack-keystone.service").return_code != 0:
        log_error('Failed to enable openstack-keystone.service')
    if run("systemctl start openstack-keystone.service").return_code != 0:
        log_error('Failed to start openstack-keystone.service')
    else:
        log_debug('Started openstack-keystone.service')


    # configure a periodic task that purges expired tokens hourly
    run("(crontab -l -u keystone 2>&1 | grep -q token_flush) || " + \
            "echo '@hourly /usr/bin/keystone-manage token_flush >/var/log/keystone/" + \
            "keystone-tokenflush.log 2>&1' >> /var/spool/cron/keystone")

    # need to restart keystone so that it can read in the 
    # new admin_token from the configuration file
    if run("systemctl restart openstack-keystone.service").return_code != 0:
        log_error('Failed to restart openstack-keystone.service')

    # configure prereqs for creating tenants, users, and roles
    exports = 'export OS_SERVICE_TOKEN={}; export OS_SERVICE_ENDPOINT=http://controller:35357/v2.0'\
            .format(admin_token)

    with prefix(exports):

        # create tenants, users, and roles
        if 'admin' not in run("keystone tenant-list"):
            run("keystone tenant-create --name admin --description 'Admin Tenant'")
        if 'admin' not in run("keystone user-list"):
            run("keystone user-create --name admin --pass {} --email {}"\
                    .format(passwd['ADMIN_PASS'], admin_email))
        if 'admin' not in run("keystone role-list"):
            run("keystone role-create --name admin")
            run("keystone user-role-add --user admin --tenant admin --role admin")
        
        # note, the following can be repeated to make more tenants and 
        # create a demo tenant for typical operations in environment
        if 'demo' not in run("keystone tenant-list"):
            run("keystone tenant-create --name demo --description 'Demo Tenant'")
        # run("keystone user-create --name demo --tenant demo --pass {} --email {}".format(demo_user['PASSWD'], demo_user['EMAIL'])) 
        if 'demo' not in run("keystone user-list"):
            run("keystone user-create --name demo --tenant demo --pass {} --email {}".format('34demo43', 'demo@gmail.com')) 

        # create one or more unique users with the admin role under the service tenant
        if 'service' not in run("keystone tenant-list"):
            run("keystone tenant-create --name service --description 'Service Tenant'")

        # create the service entity for the Identity service
        if 'keystone' not in run("keystone service-list"):
            run("keystone service-create --name keystone --type identity " + \
                    "--description 'OpenStack Identity'")
        if 'adminurl http://controller:35357' not in run("keystone endpoint-list"):
            run("keystone endpoint-create " + \
                    "--service-id $(keystone service-list | awk '/ identity / {print $2}') " + \
                    "--publicurl http://controller:5000/v2.0 --internalurl http://controller:5000/v2.0 " + \
                    "--adminurl http://controller:35357/v2.0 --region regionOne")


def deploy():
    execute(setupKeystone)

######################################## TDD #########################################


@roles('controller')
def keystone_tdd():

    # 'OK' message
    okay = '[ ' + green('OK') + ' ]'
    
    # warn_only=True because the last command is supposed to fail
    # if we don't set warn_only, the script will stop after these commands
    with settings(warn_only=True):

        env_config.keystone_check('keystone')

        # Check if 'admin' and 'demo' are users
        user_list_output = run("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 user-list".format(passwd['ADMIN_PASS']))
        if 'admin' in user_list_output:
            print okay
        else:
            print red('admin not a user')

        if 'demo' in user_list_output:
            print okay
        else:
            print red('demo not a user')

        # Check if 'admin', 'service' and 'demo' are tenants
        tenant_list_output = run("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 tenant-list".format(passwd['ADMIN_PASS']))
        for name in ['admin','demo','service']:
            if name in tenant_list_output:
                print okay
            else:
                print red('{} not a tenant'.format(name))

        # Check if '_member_' and 'admin' are roles
        role_list_output = run("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 role-list".format(passwd['ADMIN_PASS']))
        if '_member_' in role_list_output:
            print okay
        else:
            print red('_member_ not a role')

        if 'admin' in role_list_output:
            print okay
        else:
            print red('admin not a role')

        # Check if non-admin user is forbidden to perform admin tasks
        user_list_output = run("keystone --os-tenant-name demo --os-username demo --os-password {} --os-auth-url http://controller:35357/v2.0 user-list".format(passwd['DEMO_PASS']))
        if 'You are not authorized to perform the requested action' in user_list_output:
            print okay
        else:
            print red('demo was allowed to run user-list')

def tdd():
    log_debug('Starting TDD function')
    log_debug('Done')
    execute(keystone_tdd)
    #execute(env_config.keystone_check, 'keystone', roles='controller')
