import ConfigParser
import logging 
from subprocess import check_output, call
from fabric.api import run, sudo, env
from fabric.colors import red, green



##################### General functions ######################


"""

keystone check function


requires: 
- as argument: name of component being tdd'd
- requires the admin-openrc.sh file to be sourced
as it will be doing lots of keystone stuff... understandably


checks for:
- existence of user
- enable status of user
- existence of service
- existence of endpoint
- checks to make sure admin url, internal url and public url
of the endpoint match the ones given in the manual


Tested on:
- glance
- keystone
- nova
- neutron

TODO:
- quiet and verbose modes


"""

def keystone_check(name):

    # 'OK' message
    okay = '[ ' + green('OK') + ' ]'

    def quiet_sudo(command):
        return sudo(command, quiet=True)
#        return sudo(command)


    def tenant_check():
        tenants = ['admin', 'demo', 'service']

        for tenant in tenants:
            if tenant in quiet_sudo("keystone tenant-list | awk '// {print $4}'"):
                print(green(tenant +" tenant exists"))
                print okay

                if "True" == quiet_sudo("keystone tenant-list | awk '/" + tenant + "/ {print $6}'"):
                    print(green(tenant + " tenant enabled"))
                    print okay
                else:
                    print(red(tenant +" tenant NOT enabled"))

            else:
                print(red(name +" tenant does NOT exists"))

    def user_check():
        users = ['admin', 'demo']

        for user in users:
            if user in quiet_sudo("keystone user-list | awk '// {print $4}'"):
                print(green(user +" user exists"))
                print okay

                if "True" == quiet_sudo("keystone user-list | awk '/" + user + "/ {print $6}'"):
                    print(green(user + " user enabled"))
                    print okay
                else:
                    print(red(user +" user NOT enabled"))

            else:
                print(red(name +" user does NOT exists"))


        

    def user_exists(name):
        if name in quiet_sudo("keystone user-list | awk '// {print $4}'"):
            print(green(name +" user exists"))
            print okay
        else:
            print(red(name +" user does NOT exists"))

    def user_enabled(name):
        if "True" == quiet_sudo("keystone user-list | awk '/" + name + "/ {print $6}'"):
            print(green(name +" user enabled"))
            print okay
        else:
            print(red(name +" user NOT enabled"))

    def service_exists(name):
        if name in quiet_sudo("keystone service-list | awk '// {print$4}'"):
            output = quiet_sudo("keystone service-list | awk '/" + name + "/ {print$4}'")
            print(green(name +" service exists. Type: " + output))
            print okay
        else:
            print(name +" service does NOT exist")
    
    def endpoint_check(name):
        ref_d = {
            # urls taken from manual
            # FORMAT = component_name : [admin url, internal url, public url]
            'keystone': ['http://controller:35357/v2.0','http://controller:5000/v2.0','http://controller:5000/v2.0'],
            'glance': ['http://controller:9292','http://controller:9292','http://controller:9292'],
            'nova': ['http://controller:8774/v2/%(tenant_id)s','http://controller:8774/v2/%(tenant_id)s','http://controller:8774/v2/%(tenant_id)s'],
            'neutron': ['http://controller:9696','http://controller:9696','http://controller:9696'],
            'cinder': ['http://controller:8776/v1/%(tenant_id)s','http://controller:8776/v1/%(tenant_id)s','http://controller:8776/v1/%(tenant_id)s'],
            'cinderv2': ['http://controller:8776/v2/%(tenant_id)s','http://controller:8776/v2/%(tenant_id)s','http://controller:8776/v2/%(tenant_id)s'],
            'swift': ['http://controller:8080/','http://controller:8080/v1/AUTH_%(tenant_id)s','http://controller:8080/v1/AUTH_%(tenant_id)s'],
            'horizon': ['','',''],
            'heat': ['http://controller:8004/v1/%(tenant_id)s','http://controller:8004/v1/%(tenant_id)s','http://controller:8004/v1/%(tenant_id)s'],
            'trove': ['http://controller:8779/v1.0/%\(tenant_id\)s','http://controller:8779/v1.0/%\(tenant_id\)s','http://controller:8779/v1.0/%\(tenant_id\)s'],
            'sahara': ['http://controller:8386/v1.1/%\(tenant_id\)s','http://controller:8386/v1.1/%\(tenant_id\)s','http://controller:8386/v1.1/%\(tenant_id\)s'],
            'ceilometer': ['http://controller:8777','http://controller:8777','http://controller:8777']
        }

        #service_type = quiet_sudo("keystone service-list | awk '/ " + name + "/ {print $6}'")
        if name not in quiet_sudo("keystone service-list"):
            print("Service not found in service list. Service does not exist, so endpoint can't exist. Exiting function")
            return
            

        service_id = quiet_sudo("keystone service-list | awk '/ "+ name + " / {print $2}'")

        if service_id not in quiet_sudo("keystone endpoint-list"):
            print("Service id not found in endpoint list. Endpoint does not exist. Exiting function")
            return

        urls = ref_d[name]

        admin_url_found = quiet_sudo("keystone endpoint-list | awk '/" + service_id + "/ {print$10}'")
        internal_url_found = quiet_sudo("keystone endpoint-list | awk '/" + service_id + "/ {print$8}'")
        public_url_found = quiet_sudo("keystone endpoint-list | awk '/" + service_id + "/ {print$6}'")

        proper_admin_url = urls[0]
        proper_internal_url = urls[1]
        proper_public_url = urls[2]
            
        if ( admin_url_found == proper_admin_url and 
             internal_url_found == proper_internal_url and
             public_url_found == proper_public_url):
            print(green("All urls are found to be matching"))
            print okay
        else:
            print(name +" endpoint urls do not match our records")
        

    # call all functions 

    user_check()
    tenant_check()
    service_exists(name)
    endpoint_check(name)
    
    if name != 'keystone':
        user_exists(name)
        user_enabled(name)

            



# # Read the values from a node file into a list
# def read_nodes(node):
#     node_info = open(node, 'r')
#     node_string = node_info.read().splitlines()
#     # remove comments (lines that have # in the beginning)
#     # node_string_stripped = [node_element.strip() for node_element in node_string if node_element[0] != '#']
#     node_info.close()
#     #print node_string_stripped
#     return node_string

# # Make a dictionary from a config file with the format "KEY=value" on each 
# # line
# def read_dict(config_file):
#     config_file_info = open(config_file, 'r')
#     config_file_without_comments = [line for line in config_file_info.readlines() if line[0] != '#']
#     config_file_string = "".join(config_file_without_comments)
#     # config_file_string = config_file_info.read().replace('=','\n').splitlines()
#     config_file_string = config_file_string.replace('=','\n').splitlines()
#     config_file_string_stripped = [config_element.strip() for config_element in config_file_string]
#     config_file_dict = dict()
    
#     # Make a dictionary from the string from the file with the the first value
#     # on a line being the key to the value after the '=' on the same line
#     for config_file_key_index in range(0,len(config_file_string_stripped)-1,2):
#         config_file_value_index = config_file_key_index + 1
#         config_file_dict[config_file_string_stripped[config_file_key_index]] = config_file_string_stripped[config_file_value_index]
    
#     config_file_info.close()

#     #run("rm -rf %s" % config_file)
#     return config_file_dict

# General database check that will be used in several TDDs
def database_check(db):

    # 'OK' message
    okay = '[ ' + green('OK') + ' ]'
        
    def db_exists(db):
        command = "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{}';".format(db)
        if db in sudo("""echo "{}" | mysql -u root""".format(command)):
            return True
        else:
            return False
        
    def table_count(db):
        command = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '{}';".format(db) 
        output = sudo("""echo "{}" | mysql -u root | grep -v "COUNT" """.format(command))
        return int(output)

    if db_exists(db):
        message = "DB " + db + " exists"
        print green(message)
        print okay
        logging.debug(message,extra=log_dict)
    else:
        message = "DB " + db + " does not exist"
        print red(message)
        logging.debug(message,extra=log_dict)

    nbr = table_count(db)
    if nbr > 0:
        message = "table for " + db + " has " + str(nbr) + " entries"
        print green(message)
        print okay
        logging.debug(message,extra=log_dict)
    else:
        message = "table for " + db + " is empty. Nbr of entries : " + str(nbr)
        print red(message)
        logging.debug(message,extra=log_dict)


# Do a fabric command on the string 'command' and log results
def fabricLog(command,func,log_dict):
    output = func(command)
    if output.return_code != 0:
        logging.error("Problem on command '{}'".format(command),extra=log_dict)
    else:
        for line in output.splitlines():
            # don't log lines that have passwords
            if 'pass' not in line.lower():
                # skip empty lines
                if line != '' or line !='\n':
                    logging.debug(line,extra=log_dict)
    return output


def setupLoggingInFabfile(log_file):
    logfilename = log_location + log_file

    if log_file not in check_output('ls ' + log_location,shell=True):
        # file doesn't exist yet; create it
        call('touch ' + logfilename,shell=True)
        call('chmod 644 ' + logfilename,shell=True)

    logging.basicConfig(filename=logfilename,level=logging.DEBUG,format=log_format)
    # set paramiko logging to only output warnings
    logging.getLogger("paramiko").setLevel(logging.WARNING)

def getRole():
    for role in env.roledefs.keys():
        if env.host_string in env.roledefs[role]:
            return role
    # if none was found
    raise ValueError("Host " + env.hoststring + " not in roledefs")

# parse main config file and return all the 
# variables in the given section in a dictionary
def parseConfig(cfg,section):
    print cfg

    # save config file in a ConfigParser object
    parser = ConfigParser.ConfigParser()

    # preserve case
    parser.optionxform = str

    # load cfg file
    parser.read(cfg)

    # read variables and their values into a list of tuples
    nameValuePairs = parser.items(section)

    # return those pairs in a dictionary
    return {name:value for name,value in nameValuePairs}

# parse main config file and get
# roledefs dictionary
def getRoledefsDict(cfg):

    # get a dictionary mapping a role to a 
    # CSV string with all the nodes in that role
    nodesInRole = parseConfig(cfg,'roledefs')

    # split CSV strings into lists and return the dict
    return {role: (nodesInRole[role].split(',')) for role in nodesInRole}

######################### Global variables ######################

global_config_location =  '../global_config_files/'

# determine config file from local host

hostname = check_output("echo $HOSTNAME",shell=True)
if 'ipmi5' in hostname:
    mainCfg = global_config_location + 'production_global_config.cfg'
else:
    mainCfg = global_config_location + 'development_global_config.cfg'

# Variables that can be imported into the env dictionary

roledefs = getRoledefsDict(mainCfg)
hosts = roledefs.values()

# Get nodes and their roles from the config files
# compute_nodes = read_nodes('../global_config_files/compute_nodes')
# controller_nodes = read_nodes('../global_config_files/controller_nodes')
# network_nodes = read_nodes('../global_config_files/network_nodes')
# storage_nodes = read_nodes('../global_config_files/storage_nodes')

# hosts = compute_nodes + controller_nodes + network_nodes
# roledefs = { 'controller':controller_nodes, 'compute':compute_nodes, 'network':network_nodes, 'storage':storage_nodes }

# LOGGING

#log_location = '/var/log/juno/'
#if not check_output('sudo if [ -e {} ]; then echo found; fi'.format(log_location),shell=True):
#    # location not created; make it
#    call('sudo mkdir -p ' + log_location,shell=True)
#    call('sudo chmod 777 ' + log_location,shell=True)


log_format = '%(asctime)-15s:%(levelname)s:%(host_string)s:%(role)s:\t%(message)s'
log_location = '../var/log/juno/'
if not check_output('if [ -e {} ]; then echo found; fi'.format(log_location),shell=True):
    # location not created yet
    call('mkdir -p ' + log_location,shell=True)
    call('chmod 744 ' + log_location,shell=True)
log_dict = {'host_string':'','role':''} # default value for log_dict


# scripts to be sourced

admin_openrc = global_config_location + 'admin-openrc.sh'
demo_openrc = global_config_location + 'demo-openrc.sh'

# get passwords from config file
passwdFile = global_config_location + 'passwd.cfg'
passwd = parseConfig(passwdFile,'passwords')

# ntp
# get a list of ntp servers, from config file
ntpServers = parseConfig(mainCfg,'ntp')['servers'].split(',')
