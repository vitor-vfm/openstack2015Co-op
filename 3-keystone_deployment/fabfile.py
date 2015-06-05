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
env_config.setupLoggingInFabfile(log_file)

# Do a fabric run on the string 'command' and log results
run_log = lambda command : env_config.fabricLog(command,run,log_dict)
# Do a fabric run on the string 'command' and log results
sudo_log = lambda command : env_config.fabricLog(command,sudo,log_dict)

################### Deployment ########################################

def set_keystone_config_file(admin_token,password):
    # edits the keystone config file without messing up
    # what's already there

    # This was mostly done before we knew about crudini

    conf_file = 'keystone.conf'
    conf_file_contents = read_config_file_with_sections(keystone_conf)

    with cd('/etc/keystone'):
        # make backup
        sudo_log("cp {} {}.back12".format(conf_file,conf_file))
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
                if sudo_log('crudini --set {} {} {} {}'.format(conf_file,section,parameter,value)).return_code != 0:
                    logging.error('Crudini couldn\'t set up {} on section {} of conf file {}'\
                            .format(parameter,section,conf_file),extra=log_dict)



@roles('controller')
def setupKeystone():
    # info for logging
    global log_dict
    log_dict = {'host_string':env.host_string, 'role':'controller'}


    logging.debug('Setting up keystone on host',extra=log_dict)

    if sudo_log("systemctl restart mariadb").return_code != 0:
        logging.error('Failed to restart mariadb',extra=log_dict)
        # we need mariadb working in order to proceed
        sys.exit("Failed to restart mariadb")
    else:
	logging.debug("Succesfully restarted mariadb", extra=log_dict)

    fileContents = keystoneConfigFileContents
    fileContents = fileContents.replace('NEW_PASS',passwd['ADMIN_PASS'])
    
    if sudo_log('echo "' + fileContents + '" | mysql -u root').return_code != 0:
	logging.error("Failed to setup to mariadb")
    else:
	logging.debug("Setup mariadb", extra=log_dict)  
  
    admin_token = run('openssl rand -hex 10')
    sudo_log("yum -y install openstack-keystone python-keystoneclient")
    
    # set config files
    set_keystone_config_file(admin_token,passwd['ADMIN_PASS'])
    
    # create generic certificates and keys and restrict access to the associated files
    sudo_log("keystone-manage pki_setup --keystone-user keystone --keystone-group keystone")
    sudo_log("chown -R keystone:keystone /var/log/keystone")
    sudo_log("chown -R keystone:keystone /etc/keystone/ssl")
    sudo_log("chmod -R o-rwx /etc/keystone/ssl")

    # populate the Identity service database
    if sudo_log("su -s /bin/sh -c 'keystone-manage db_sync' keystone").return_code != 0:
        logging.error('Failed to populate database',extra=log_dict)
    else:
        logging.debug('Populated database',extra=log_dict)


    # start the Identity service and configure it to start when the system boots
    if sudo_log("systemctl enable openstack-keystone.service").return_code != 0:
        logging.error('Failed to enable openstack-keystone.service',extra=log_dict)
    if sudo_log("systemctl start openstack-keystone.service").return_code != 0:
        logging.error('Failed to start openstack-keystone.service',extra=log_dict)
    else:
        logging.debug('Started openstack-keystone.service',extra=log_dict)


    # configure a periodic task that purges expired tokens hourly
    sudo_log("(crontab -l -u keystone 2>&1 | grep -q token_flush) || " + \
            "echo '@hourly /usr/bin/keystone-manage token_flush >/var/log/keystone/" + \
            "keystone-tokenflush.log 2>&1' >> /var/spool/cron/keystone")

    # need to restart keystone so that it can read in the 
    # new admin_token from the configuration file
    if sudo_log("systemctl restart openstack-keystone.service").return_code != 0:
        logging.error('Failed to restart openstack-keystone.service',extra=log_dict)

    # configure prereqs for creating tenants, users, and roles
    exports = 'export OS_SERVICE_TOKEN={}; export OS_SERVICE_ENDPOINT=http://controller:35357/v2.0'\
            .format(admin_token)

    with prefix(exports):

        # create tenants, users, and roles
        if 'admin' not in sudo_log("keystone tenant-list"):
            sudo_log("keystone tenant-create --name admin --description 'Admin Tenant'")
        if 'admin' not in sudo_log("keystone user-list"):
            sudo_log("keystone user-create --name admin --pass {} --email {}"\
                    .format(passwd['ADMIN_PASS'], admin_info['EMAIL']))
        if 'admin' not in sudo_log("keystone role-list"):
            sudo_log("keystone role-create --name admin")
            sudo_log("keystone user-role-add --user admin --tenant admin --role admin")
        
        # note, the following can be repeated to make more tenants and 
        # create a demo tenant for typical operations in environment
        if 'demo' not in sudo_log("keystone tenant-list"):
            sudo_log("keystone tenant-create --name demo --description 'Demo Tenant'")
        # sudo_log("keystone user-create --name demo --tenant demo --pass {} --email {}".format(demo_user['PASSWD'], demo_user['EMAIL'])) 
        if 'demo' not in sudo_log("keystone user-list"):
            sudo_log("keystone user-create --name demo --tenant demo --pass {} --email {}".format('34demo43', 'demo@gmail.com')) 

        # create one or more unique users with the admin role under the service tenant
        if 'service' not in sudo_log("keystone tenant-list"):
            sudo_log("keystone tenant-create --name service --description 'Service Tenant'")

        # create the service entity for the Identity service
        if 'keystone' not in sudo_log("keystone service-list"):
            sudo_log("keystone service-create --name keystone --type identity " + \
                    "--description 'OpenStack Identity'")
        if '5000' not in sudo_log("keystone endpoint-list"):
            sudo_log("keystone endpoint-create " + \
                    "--service-id $(keystone service-list | awk '/ identity / {print $2}') " + \
                    "--publicurl http://controller:5000/v2.0 --internalurl http://controller:5000/v2.0 " + \
                    "--adminurl http://controller:35357/v2.0 --region regionOne")


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


        # Check if 'admin' and 'demo' are users
        user_list_output = sudo_log("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 user-list".format(passwd['ADMIN_PASS']))
        if 'admin' in user_list_output:
            print okay
        else:
            print red('admin not a user')

        if 'demo' in user_list_output:
            print okay
        else:
            print red('demo not a user')

        # Check if 'admin', 'service' and 'demo' are tenants
        tenant_list_output = sudo_log("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 tenant-list".format(passwd['ADMIN_PASS']))
        for name in ['admin','demo','service']:
            if name in tenant_list_output:
                print okay
            else:
                print red('{} not a tenant'.format(name))

        # Check if '_member_' and 'admin' are roles
        role_list_output = sudo_log("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 role-list".format(passwd['ADMIN_PASS']))
        if '_member_' in role_list_output:
            print okay
        else:
            print red('_member_ not a role')

        if 'admin' in role_list_output:
            print okay
        else:
            print red('admin not a role')

        # Check if non-admin user is forbidden to perform admin tasks
        user_list_output = sudo_log("keystone --os-tenant-name demo --os-username demo --os-password {} --os-auth-url http://controller:35357/v2.0 user-list".format(passwd['DEMO_PASS']))
        if 'You are not authorized to perform the requested action' in user_list_output:
            print okay
        else:
            print red('demo was allowed to run user-list')

def tdd():
    global log_dict
    log_dict = {'host_string':'','role':''} 
    logging.debug('Starting TDD function',extra=log_dict)
    logging.debug('Done',extra=log_dict)
