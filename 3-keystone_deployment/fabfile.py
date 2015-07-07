from __future__ import with_statement
from fabric.decorators import with_settings
from fabric.api import *
from fabric.context_managers import cd
from fabric.colors import green, red, blue
import string
import subprocess
import logging

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, createDatabaseScript
from myLib import keystone_check, database_check, align_y, align_n, saveConfigFile

########################## Configuring Environment #################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

################################ Deployment ########################################

@roles(env_config.roles)
def saveOpenrcFiles():
    "Save the admin-openrc and demo-openrc files in the hosts"

    contents = env_config.admin_openrc
    msg = 'Put admin-openrc.sh in '+env.host
    runCheck(msg, "echo '{}' >/root/admin-openrc.sh".format(contents))

    contents = env_config.demo_openrc
    msg = 'Put demo-openrc.sh in '+env.host
    runCheck(msg, "echo '{}' >/root/demo-openrc.sh".format(contents))

def setKeystoneConfigFile(admin_token,password):
    """
    Configure variables in keystone.conf
    """

    confFile= '/etc/keystone/keystone.conf'

    msg = 'Make a backup of keystone.conf'
    runCheck(msg, "cp {} {}.back12".format(confFile,confFile))

    crudiniCommands = "\n" + \
    "crudini --set {} DEFAULT admin_token {}\n""".format(confFile,admin_token) + \
    "crudini --set {} DEFAULT verbose True\n".format(confFile) + \
    "crudini --set {} database connection mysql://keystone:{}@controller/keystone\n".format(confFile,password) + \
    "crudini --set {} token provider keystone.token.providers.uuid.Provider\n".format(confFile) + \
    "crudini --set {} token driver keystone.token.persistence.backends.sql.Token\n".format(confFile) + \
    "crudini --set {} revoke driver keystone.contrib.revoke.backends.sql.Revoke\n".format(confFile)

    msg = 'Set up variables in {} using crudini'.format(confFile)
    runCheck(msg, crudiniCommands)

    # need to restart keystone so that it can read in the 
    # new admin_token from the configuration file
    msg = "Restart keystone service"
    runCheck(msg, "systemctl restart openstack-keystone.service")



def createGenericCertificatesAndKeys():
    """
    Set up Keystone's Public Key Infrastructure
    """
    msg = "Create a user and a group called 'keystone' for the PKI"
    runCheck(msg, "keystone-manage pki_setup --keystone-user keystone --keystone-group keystone")

    msg = "Change ownership for /var/log/keystone and /etc/keystone/ssl"
    runCheck(msg, "chown -R keystone:keystone /var/log/keystone")
    runCheck(msg, "chown -R keystone:keystone /etc/keystone/ssl")

    msg = "Remove rwx permissions to everyone on /etc/keystone/ssl"
    runCheck(msg, "chmod -R o-rwx /etc/keystone/ssl")

def configureCronToPurgeExpiredTokens():
    """
    Use cron to configure a periodic task that purges expired tokens hourly

    From the installation manual:
    "By default, the Identity service stores expired tokens in the database indefinitely.
    The accumulation of expired tokens considerably increases the database size and might 
    degrade service performance, particularly in environments with limited resources."

    """
    msg = " Use cron to configure a periodic task that purges expired tokens hourly"
    runCheck(msg, "(crontab -l -u keystone 2>&1 | grep -q token_flush) || " + \
            "echo '@hourly /usr/bin/keystone-manage token_flush >/var/log/keystone/ keystone-tokenflush.log 2>&1' " + \
            ">> /var/spool/cron/keystone")

def createUsersRolesAndTenants(admin_token):
    """
    Create (a) a user, a tenant, and role called 'admin', (b) a user and a 
    tenant called 'demo', (c) a tenant called 'service', and (d) a service 
    called 'keystone' and an endpoint fo this service, for Keystone's use
    """

    # get admin credentials
    credentials = "export OS_SERVICE_TOKEN={}; ".format(admin_token) + \
            "export OS_SERVICE_ENDPOINT=http://controller:35357/v2.0 "
    # credentials += env_config.admin_openrc
    with prefix(credentials):

        msg = "Create 'admin' tenant"
        runCheck(msg, "keystone tenant-create --name admin --description 'Admin Tenant'")

        msg = "Create 'admin' user"
        runCheck(msg, "keystone user-create --name admin --pass {} --email {}"\
                .format(passwd['ADMIN_PASS'], env_config.keystone_emails['ADMIN_EMAIL']))

        msg = "Create 'admin' role"
        runCheck(msg, "keystone role-create --name admin")

        msg = "Give role 'admin' to user 'admin'"
        runCheck(msg, "keystone user-role-add --user admin --tenant admin --role admin")


    
        msg = "Create 'demo' tenant"
        runCheck(msg, "keystone tenant-create --name demo --description 'Demo Tenant'")

        msg = "Create 'demo' user"
        runCheck(msg, "keystone user-create --name demo --tenant demo " +\
                "--pass {} --email {}".format('34demo43', env_config.keystone_emails['DEMO_EMAIL'])) 



        msg = "Create 'service' tenant"
        runCheck(msg, "keystone tenant-create --name service --description 'Service Tenant'")



        msg = "Create 'keystone' service"
        runCheck(msg, "keystone service-create --name keystone --type identity " + \
                "--description 'OpenStack Identity'")

        msg = "Create an endpoint for the 'keystone' service"
        runCheck(msg, "keystone endpoint-create " + \
                "--service-id $(keystone service-list | awk '/ identity / {print $2}') " + \
                "--publicurl http://controller:5000/v2.0 --internalurl http://controller:5000/v2.0 " + \
                "--adminurl http://controller:35357/v2.0 --region regionOne")


@roles('controller')
def installPackages():
    msg = 'Install packages'
    runCheck(msg, 'yum -y install openstack-keystone python-keystoneclient',quiet=True)

    msg = "Start keystone service"
    runCheck(msg, "systemctl start openstack-keystone.service",quiet=True)
    msg = "Start enable service"
    runCheck(msg, "systemctl enable openstack-keystone.service",quiet=True)

 
@roles('controller')
def setupKeystone():

    msg = "Checking MariaDB service"
    out = runCheck(msg, "systemctl is-enabled mariadb")
    if out.return_code != 0:
        # we need mariadb working in order to proceed
        sys.exit("mariadb is not enabled")

    # get Keystone database creation scripts
    databaseCreation = createDatabaseScript('keystone',passwd['KEYSTONE_DBPASS'])

    msg = "Create database for keystone"
    runCheck(msg, 'echo "' + databaseCreation + '" | mysql -u root -p"%s" ' % env_config.passwd['ROOT_SECRET'])
    run(' mysql -u root -p"%s" -e "Select * from users where user=`keystone`"' % env_config.passwd['ROOT_SECRET'])
    execute(installPackages)
  
    msg = "Generate an admin token"
    admin_token = runCheck(msg, 'openssl rand -hex 10')

    setKeystoneConfigFile(admin_token,passwd['KEYSTONE_DBPASS'])
    
    createGenericCertificatesAndKeys()

    msg = 'Populate the Identity service database'
    runCheck(msg, "su -s /bin/sh -c 'keystone-manage db_sync' keystone")

    # start the Identity service and configure it to start when the system boots
    msg = "Enable keystone service"
    runCheck(msg, "systemctl enable openstack-keystone.service")
    msg = "Start keystone service"
    runCheck(msg, "systemctl start openstack-keystone.service")

    configureCronToPurgeExpiredTokens()

    createUsersRolesAndTenants(admin_token)


def deploy():
    execute(setupKeystone)
    execute(saveOpenrcFiles)

######################################## TDD #########################################

@roles('controller')
def keystone_tdd():

    with settings(warn_only=True):

        status = 'good'

        resk = keystone_check('keystone')
        resd = database_check('keystone')

        if (resk == 'FAIL') or (resd == 'FAIL'):
            status = 'bad'

        # Check if 'admin' and 'demo' are users
        user_list_output = run("keystone --os-tenant-name admin --os-username admin " + \
                "--os-password {} --os-auth-url http://controller:35357/v2.0 user-list"\
                                 .format(passwd['ADMIN_PASS']), quiet=True)
        if 'admin' in user_list_output:
            print align_y('Admin was found in user list')
        else:
            print align_n('admin not a user')
            status = 'bad'

        if 'demo' in user_list_output:
            print align_y('Demo was found in user list')
        else:
            print align_n('demo not a user')
            status = 'bad'

        # Check if 'admin', 'service' and 'demo' are tenants
        tenant_list_output = run("keystone --os-tenant-name admin --os-username admin " + \
                "--os-password {} --os-auth-url http://controller:35357/v2.0 tenant-list"\
                .format(passwd['ADMIN_PASS']), quiet=True)
        for name in ['admin','demo','service']:
            if name in tenant_list_output:
                print align_y('{} was found in tenant list'.format(name))
            else:
                print align_n('{} not a tenant'.format(name))
                status = 'bad'

        # Check if '_member_' and 'admin' are roles
        role_list_output = run("keystone --os-tenant-name admin --os-username admin " + \
                "--os-password {} --os-auth-url http://controller:35357/v2.0 role-list"\
                .format(passwd['ADMIN_PASS']), quiet=True)
        if '_member_' in role_list_output:
            print align_y('_member_ is a role')
        else:
            print align_n('_member_ not a role')
            status = 'bad'

        if 'admin' in role_list_output:
            print align_y('admin is a role')
        else:
            print align_n('admin not a role')
            status = 'bad'

        # Check if non-admin user is forbidden to perform admin tasks
        user_list_output = run("keystone --os-tenant-name demo --os-username demo " + \
                "--os-password {} --os-auth-url http://controller:35357/v2.0 user-list"\
                .format(passwd['DEMO_PASS']), quiet=True)
        if 'You are not authorized to perform the requested action' in user_list_output:
            print align_y('demo was not allowed to run user-list')
        else:
            print align_n('demo was allowed to run user-list')
            status = 'bad'

        confFile= '/etc/keystone/keystone.conf'
        saveConfigFile(confFile,status)

def tdd():
    print blue('Starting TDD function')
    execute(keystone_tdd)
    print blue('Done')

