from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
import string
import subprocess
import logging

import sys
sys.path.append('../global_config_files')
import env_config

################### Configuring Environment ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

@hosts('localhost')
def readKeyStoneDBConfigFile(fileName):
    # basically reads the entire file given 
    # and returns the content of the file
    # in a single string

    dbFile = open('config_files/' + fileName, 'r')
    lines = [line for line in dbFile.readlines()]
    fileContent = ""
    for oneLine in lines:
        fileContent = fileContent + oneLine + '\n'
    return fileContent

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


#keystone DB file 
keystoneConfigFileContents = readKeyStoneDBConfigFile('keystoneDBSetup.sql')
 
# config files for user Usr
admin_info = env_config.read_dict('config_files/keystone_admin_config') 
demo_user = env_config.read_dict('config_files/keystone_demo_config')

# create these files for easier access for other components when configuring with keystone

# create admin_openrc.sh file in ../global_config_files/admin_openrc.sh
adminFile = open('../global_config_files/admin-openrc.sh', 'w')
admin_openrc_contents = "export OS_TENANT_NAME=admin; export OS_USERNAME=admin; export OS_PASSWORD={}; export OS_AUTH_URL=http://controller:35357/v2.0".format(passwd['ADMIN_PASS'])
adminFile.write(admin_openrc_contents)
adminFile.close()

# create demo_openrc.sh file in ../global_config_files/demo_openrc.sh
demoFile = open('../global_config_files/demo-openrc.sh', 'w')
demo_openrc_contents = "export OS_TENANT_NAME=demo; export OS_USERNAME=demo; export OS_PASSWORD={}; export OS_AUTH_URL=http://controller:5000/v2.0".format(passwd['DEMO_PASS'])
demoFile.write(demo_openrc_contents)
demoFile.close()

# config file for keystone
keystone_conf = 'config_files/keystone.conf'

# logging setup

log_file = 'keystone_deployment.log'
logfilename = env_config.log_location + log_file

if log_file not in local('ls ' + env_config.log_location,capture=True):
    # file doesn't exist yet; create it
    local('touch ' + logfilename,capture=True)
    local('chmod 644 ' + logfilename,capture=True)

logging.basicConfig(filename=logfilename,level=logging.DEBUG,format=env_config.log_format)
# set paramiko logging to only output warnings
logging.getLogger("paramiko").setLevel(logging.WARNING)


################### Deployment ########################################

def set_keystone_config_file(admin_token,password):
    # edits the keystone config file without messing up
    # what's already there

    # This was mostly done before we knew about crudini

    conf_file = 'keystone.conf'
    conf_file_contents = read_config_file_with_sections(keystone_conf)

    with cd('/etc/keystone'):
        # make backup
        sudo("cp {} {}.back12".format(conf_file,conf_file))
        # for testing
        #conf_file += '.back12'

        for header in conf_file_contents.keys():
            lines_to_add = conf_file_contents[header]
            # replace password
            lines_to_add = [line.replace('KEYSTONE_DBPASS',password) for line in lines_to_add]
            # replace admin token
            lines_to_add = [line.replace('ADMIN_TOKEN',admin_token) for line in lines_to_add]

            for new_line in lines_to_add:
                section = header[1:-1]
                # new_line = new_line.split('=')
                new_line = [line.strip() for line in new_line.split('=')]
                parameter = '\'' + new_line[0] + '\''
                value = '\'' + new_line[1] + '\''
                if sudo('crudini --set {} {} {} {}'.format(conf_file,section,parameter,value)).return_code != 0:
                    logging.error('Crudini couldn\'t set up {} on section {} of conf file {}'\
                            .format(parameter,section,conf_file),extra=log_dict)



@roles('controller')
def setupKeystone():
    # remember to set the decorator
    # to ensure that it only runs on the controller

    # we are seting controller to point to the 
    # ip that we sshed into through the hosts file

    # this shouldn't be a problem b/c when we implement,
    # the actual hosts will be the controller node and whatnot

    # info for logging
    log_dict = {'host_string':env.host_string, 'role':'controller'}


    logging.debug('Setting up keystone on host',extra=log_dict)

    if sudo("systemctl restart mariadb").return_code != 0:
        logging.error('Failed to restart maridb',extra=log_dict)

    fileContents = keystoneConfigFileContents
    fileContents = fileContents.replace('NEW_PASS',passwd['ADMIN_PASS'])
    
    # we assume that mariadb is up and running!
    sudo('echo "' + fileContents + '" | mysql -u root')
    admin_token = run('openssl rand -hex 10')
    sudo("yum -y install openstack-keystone python-keystoneclient")
    
    # set config files
    set_keystone_config_file(admin_token,passwd['ADMIN_PASS'])
    
    # create generic certificates and keys and restrict access to the associated files
    sudo("keystone-manage pki_setup --keystone-user keystone --keystone-group keystone")
    sudo("chown -R keystone:keystone /var/log/keystone")
    sudo("chown -R keystone:keystone /etc/keystone/ssl")
    sudo("chmod -R o-rwx /etc/keystone/ssl")

    # populate the Identity service database
    if sudo("su -s /bin/sh -c 'keystone-manage db_sync' keystone").return_code != 0:
        logging.error('Failed to populate database',extra=log_dict)
    else:
        logging.debug('Populated database',extra=log_dict)


    # start the Identity service and configure it to start when the system boots
    if sudo("systemctl enable openstack-keystone.service").return_code != 0:
        logging.error('Failed to enable openstack-keystone.service',extra=log_dict)
    if sudo("systemctl start openstack-keystone.service").return_code != 0:
        logging.error('Failed to start openstack-keystone.service',extra=log_dict)
    else:
        logging.debug('Started openstack-keystone.service',extra=log_dict)


    # configure a periodic task that purges expired tokens hourly
    sudo("(crontab -l -u keystone 2>&1 | grep -q token_flush) || " + \
            "echo '@hourly /usr/bin/keystone-manage token_flush >/var/log/keystone/" + \
            "keystone-tokenflush.log 2>&1' >> /var/spool/cron/keystone")

    # need to restart keystone so that it can read in the 
    # new admin_token from the configuration file
    if sudo("systemctl restart openstack-keystone.service").return_code != 0:
        logging.error('Failed to restart openstack-keystone.service',extra=log_dict)

    # configure a periodic task that purges expired tokens hourly
    sudo("(crontab -l -u keystone 2>&1 | grep -q token_flush) || " + \
            "echo '@hourly /usr/bin/keystone-manage token_flush >/var/log/keystone/" + \
            "keystone-tokenflush.log 2>&1' >> /var/spool/cron/keystone")

    # configure prereqs for creating tenants, users, and roles
    exports = 'export OS_SERVICE_TOKEN={}; export OS_SERVICE_ENDPOINT=http://controller:35357/v2.0'\
            .format(admin_token)

    with prefix(exports):

        # create tenants, users, and roles
        if 'admin' not in sudo("keystone tenant-list"):
            logging.debug(sudo("keystone tenant-create --name admin --description 'Admin Tenant'"),extra=log_dict)
        if 'admin' not in sudo("keystone user-list"):
            logging.debug(sudo("keystone user-create --name admin --pass {} --email {}"\
                    .format(passwd['ADMIN_PASS'], admin_info['EMAIL'])),extra=log_dict)
        if 'admin' not in sudo("keystone role-list"):
            logging.debug(sudo("keystone role-create --name admin"),extra=log_dict)
            logging.debug(sudo("keystone user-role-add --user admin --tenant admin --role admin"),extra=log_dict)
        
        # note, the following can be repeated to make more tenants and 
        # create a demo tenant for typical operations in environment
        if 'demo' not in sudo("keystone tenant-list"):
            logging.debug(sudo("keystone tenant-create --name demo --description 'Demo Tenant'") ,extra=log_dict)
        # sudo("keystone user-create --name demo --tenant demo --pass {} --email {}".format(demo_user['PASSWD'], demo_user['EMAIL'])) 
        if 'demo' not in sudo("keystone user-list"):
            sudo("keystone user-create --name demo --tenant demo --pass {} --email {}".format('34demo43', 'demo@gmail.com')) 

        # create one or more unique users with the admin role under the service tenant
        if 'service' not in sudo("keystone tenant-list"):
            logging.debug(sudo("keystone tenant-create --name service --description 'Service Tenant'"),extra=log_dict)

        # create the service entity for the Identity service
        if 'keystone' not in sudo("keystone service-list"):
            logging.debug(sudo("keystone service-create --name keystone --type identity " + \
                    "--description 'OpenStack Identity'"),extra=log_dict)
        if '5000' not in sudo("keystone endpoint-list"):
            logging.debug(sudo("keystone endpoint-create " + \
                    "--service-id $(keystone service-list | awk '/ identity / {print $2}') " + \
                    "--publicurl http://controller:5000/v2.0 --internalurl http://controller:5000/v2.0 " + \
                    "--adminurl http://controller:35357/v2.0 --region regionOne"),extra=log_dict)


def deploy():
    log_dict = {'host_string':'','role':''} 
    logging.debug('Deploying',extra=log_dict)
    execute(setupKeystone)
    logging.debug('Done',extra=log_dict)

######################################## TDD #########################################

@roles('controller')
def keystone_tdd():

    # 'OK' message
    okay = '[ ' + green('OK') + ' ]'
    
    # warn_only=True because the last command is supposed to fail
    # if we don't set warn_only, the script will stop after these commands
    with settings(warn_only=True):

        # Check if non-admin user is forbidden to perform admin tasks
        user_list_output = sudo("keystone --os-tenant-name demo --os-username demo --os-password {} --os-auth-url http://controller:35357/v2.0 user-list".format(passwd['DEMO_PASS']))
        if 'You are not authorized to perform the requested action' in user_list_output:
            print okay
        else:
            print red('demo was allowed to run user-list')

        # Check if 'admin' and 'demo' are users
        user_list_output = sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 user-list".format(passwd['ADMIN_PASS']))
        if 'admin' in user_list_output:
            print okay
        else:
            print red('admin not a user')

        if 'demo' in user_list_output:
            print okay
        else:
            print red('demo not a user')

        # Check if 'admin', 'service' and 'demo' are tenants
        tenant_list_output = sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 tenant-list".format(passwd['ADMIN_PASS']))
        for name in ['admin','demo','service']:
            if name in tenant_list_output:
                print okay
            else:
                print red('{} not a tenant'.format(name))

        # Check if '_member_' and 'admin' are roles
        role_list_output = sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 role-list".format(passwd['ADMIN_PASS']))
        if '_member_' in role_list_output:
            print okay
        else:
            print red('_member_ not a role')

        if 'admin' in role_list_output:
            print okay
        else:
            print red('admin not a role')


def tdd():
    log_dict = {'host_string':'','role':''} 
    logging.debug('Starting TDD function',extra=log_dict)
    execute(keystone_tdd)
    logging.debug('Done',extra=log_dict)
