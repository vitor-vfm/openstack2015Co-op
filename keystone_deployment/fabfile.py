from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
import string
import subprocess
import sys
sys.path.append('../global_config_files')

import env_config

################### Configuring Environment ########################################

env.roledefs = env_config.roledefs
print env.roledefs

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
admin_openrc_contents = "export OS_TENANT_NAME=admin; export OS_USERNAME=admin; export OS_PASSWORD={}; export OS_AUTH_URL=http://controller:35357/v2.0".format(admin_info['PASSWD'])
adminFile.write(admin_openrc_contents)
adminFile.close()

# create demo_openrc.sh file in ../global_config_files/demo_openrc.sh
demoFile = open('../global_config_files/demo-openrc.sh', 'w')
demo_openrc_contents = "export OS_TENANT_NAME=demo; export OS_USERNAME=demo; export OS_PASSWORD={}; export OS_AUTH_URL=http://controller:5000/v2.0".format(demo_user['PASSWD'])
demoFile.write(demo_openrc_contents)
demoFile.close()





# config file for keystone
keystone_conf = 'config_files/keystone.conf'


################### Deployment ########################################

def set_keystone_config_file(admin_token,passwd):
    # edits the keystone config file without messing up
    # what's already there

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
            lines_to_add = [line.replace('KEYSTONE_DBPASS',passwd) for line in lines_to_add]
            # replace admin token
            lines_to_add = [line.replace('ADMIN_TOKEN',admin_token) for line in lines_to_add]

            for new_line in lines_to_add:
                section = header[1:-1]
                print new_line
                # new_line = new_line.split('=')
                new_line = [line.strip() for line in new_line.split('=')]
                parameter = '\'' + new_line[0] + '\''
                value = '\'' + new_line[1] + '\''
                print 'section:' + section
                print 'parameter:' + parameter
                print 'value:' + value
                sudo('crudini --set {} {} {} {}'.format(conf_file,section,parameter,value))

            # # see if there's a section with that header already in the file
            # if sudo("grep '{}' {}".format(header,conf_file)).return_code == 0:
            #     for new_line in lines_to_add:
            #         # remove old versions of the line from the conf file, ignoring comments
            #         pattern_to_find = new_line[:new_line.index('=')]
            #         sudo("sed -i '/^[!#]*%s*/d' %s" % (pattern_to_find,conf_file))
            #         # append new line under the header, ignoring comments
            #         sudo('''sed -i "/^[!#]*%s*/a %s" %s''' % (header,new_line,conf_file))
            #         # sudo("sed -i '/^#/!{/{}/a {}}' {}".format(header,new_line,conf_file))
            # else:
            #     # simply add the new section to the bottom of the file
            #     sudo("echo -e '{}' >>{}".format(header,conf_file))
            #     for new_line in lines_to_add:
            #         sudo("echo -e '{}' >>{}".format(new_line,conf_file))

@roles('controller')
def setupKeystone():
    # remember to set the decorator
    # to ensure that it only runs on the controller

    # we are seting controller to point to the 
    # ip that we sshed into through the hosts file

    # this shouldn't be a problem b/c when we implement,
    # the actual hosts will be the controller node and whatnot

    # host_command = 'sudo -- sh -c "{}"'.format("echo '{}' >> /etc/hosts".format("{}        controller".format(env.host))) 
    # sudo(host_command)


    # fixing bind-address on /etc/my.cnf

    # bindCommand = "sed -i.bak 's/^\(bind-address=\).*/\1 {} /' /etc/my.cnf".format(env.host)
    # bindCommand = "sed -i '/bind-address/s/=.*/={}/' /etc/my.cnf".format(env.host)
    # sudo(bindCommand)
    
    sudo("systemctl restart mariadb")

    fileContents = keystoneConfigFileContents
    fileContents = fileContents.replace('NEW_PASS',admin_info['PASSWD'])
    print red(fileContents)
    
    # we assume that mariadb is up and running!
    sudo('echo "' + fileContents + '" | mysql -u root')
    admin_token = run('openssl rand -hex 10')
    sudo("yum -y install openstack-keystone python-keystoneclient")
    
    # set config files
    set_keystone_config_file(admin_token,admin_info['PASSWD'])
    
    # create generic certificates and keys and restrict access to the associated files
    sudo("keystone-manage pki_setup --keystone-user keystone --keystone-group keystone")
    sudo("chown -R keystone:keystone /var/log/keystone")
    sudo("chown -R keystone:keystone /etc/keystone/ssl")
    sudo("chmod -R o-rwx /etc/keystone/ssl")

    # populate the Identity service database
    sudo("su -s /bin/sh -c 'keystone-manage db_sync' keystone")

    # start the Identity service and configure it to start when the system boots
    sudo("systemctl enable openstack-keystone.service")
    sudo("systemctl start openstack-keystone.service")

    # configure a periodic task that purges expired tokens hourly
    sudo("(crontab -l -u keystone 2>&1 | grep -q token_flush) || " + \
            "echo '@hourly /usr/bin/keystone-manage token_flush >/var/log/keystone/" + \
            "keystone-tokenflush.log 2>&1' >> /var/spool/cron/keystone")

    # need to restart keystone so that it can read in the 
    # new admin_token from the configuration file
    sudo("systemctl restart openstack-keystone.service")

    # configure a periodic task that purges expired tokens hourly
    sudo("(crontab -l -u keystone 2>&1 | grep -q token_flush) || " + \
            "echo '@hourly /usr/bin/keystone-manage token_flush >/var/log/keystone/" + \
            "keystone-tokenflush.log 2>&1' >> /var/spool/cron/keystone")

    # configure prereqs for creating tenants, users, and roles
    exports = "export OS_SERVICE_TOKEN={}; ".format(admin_token)
    exports += "export OS_SERVICE_ENDPOINT=http://controller:35357/v2.0"

    with prefix(exports):

        sudo("keystone tenant-list")
        sudo("keystone user-list")
        sudo("keystone role-list")
        sudo("keystone service-list")
        sudo("keystone endpoint-list")
        # create tenants, users, and roles
        sudo("keystone tenant-create --name admin --description 'Admin Tenant'")
        sudo("keystone user-create --name admin --pass {} --email {}".format(admin_info['PASSWD'], admin_info['EMAIL']))
        sudo("keystone role-create --name admin")
        sudo("keystone user-role-add --user admin --tenant admin --role admin")
        
        # note, the following can be repeated to make more tenants and 
        # create a demo tenant for typical operations in environment
        sudo("keystone tenant-create --name demo --description 'Demo Tenant'") 
        # sudo("keystone user-create --name demo --tenant demo --pass {} --email {}".format(demo_user['PASSWD'], demo_user['EMAIL'])) 
        sudo("keystone user-create --name demo --tenant demo --pass {} --email {}".format('34demo43', 'demo@gmail.com')) 

        # create one or more unique users with the admin role under the service tenant
        sudo("keystone tenant-create --name service --description 'Service Tenant'")

        # create the service entity for the Identity service
        sudo("keystone service-create --name keystone --type identity " + \
                "--description 'OpenStack Identity'")
        sudo("keystone endpoint-create " + \
                "--service-id $(keystone service-list | awk '/ identity / {print $2}') " + \
                "--publicurl http://controller:5000/v2.0 --internalurl http://controller:5000/v2.0 " + \
                "--adminurl http://controller:35357/v2.0 --region regionOne")

    # verify operation of the Identity service

    sudo("unset OS_SERVICE_TOKEN OS_SERVICE_ENDPOINT")
    sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 token-get".format(admin_info['PASSWD'])) 
    sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 tenant-list".format(admin_info['PASSWD']))
    sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 user-list".format(admin_info['PASSWD']))
    sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 role-list".format(admin_info['PASSWD']))

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

        # Check if non-admin user is forbidden to perform admin tasks
        user_list_output = sudo("keystone --os-tenant-name demo --os-username demo --os-password {} --os-auth-url http://controller:35357/v2.0 user-list".format(demo_user['PASSWD']))
        if 'You are not authorized to perform the requested action' in user_list_output:
            print okay
        else:
            print red('demo was allowed to run user-list')

        # Check if 'admin' and 'demo' are users
        user_list_output = sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 user-list".format(admin_info['PASSWD']))
        if 'admin' in user_list_output:
            print okay
        else:
            print red('admin not a user')

        if 'demo' in user_list_output:
            print okay
        else:
            print red('demo not a user')

        # Check if 'admin', 'service' and 'admin' are tenants
        tenant_list_output = sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 tenant-list".format(admin_info['PASSWD']))
        if 'admin' in tenant_list_output:
            print okay
        else:
            print red('admin not a tenant')

        if 'demo' in tenant_list_output:
            print okay
        else:
            print red('demo not a tenant')

        if 'service' in tenant_list_output:
            print okay
        else:
            print red('service not a tenant')

        # Check if '_member_' and 'admin' are roles
        role_list_output = sudo("keystone --os-tenant-name admin --os-username admin --os-password {} --os-auth-url http://controller:35357/v2.0 role-list".format(admin_info['PASSWD']))
        if '_member_' in role_list_output:
            print okay
        else:
            print red('_member_ not a role')

        if 'admin' in role_list_output:
            print okay
        else:
            print red('admin not a role')


def tdd():
    execute(keystone_tdd)
