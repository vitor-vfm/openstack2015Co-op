import logging 
from subprocess import check_output, call
from fabric.api import run, sudo, env

##################### General functions ######################

# Read the values from a node file into a list
def read_nodes(node):
    node_info = open(node, 'r')
    node_string = node_info.read().splitlines()
    # remove comments (lines that have # in the beginning)
    # node_string_stripped = [node_element.strip() for node_element in node_string if node_element[0] != '#']
    node_info.close()
    #print node_string_stripped
    return node_string

# Make a dictionary from a config file with the format "KEY=value" on each 
# line
def read_dict(config_file):
    config_file_info = open(config_file, 'r')
    config_file_without_comments = [line for line in config_file_info.readlines() if line[0] != '#']
    config_file_string = "".join(config_file_without_comments)
    # config_file_string = config_file_info.read().replace('=','\n').splitlines()
    config_file_string = config_file_string.replace('=','\n').splitlines()
    config_file_string_stripped = [config_element.strip() for config_element in config_file_string]
    config_file_dict = dict()
    
    # Make a dictionary from the string from the file with the the first value
    # on a line being the key to the value after the '=' on the same line
    for config_file_key_index in range(0,len(config_file_string_stripped)-1,2):
        config_file_value_index = config_file_key_index + 1
        config_file_dict[config_file_string_stripped[config_file_key_index]] = config_file_string_stripped[config_file_value_index]
    
    config_file_info.close()

    #run("rm -rf %s" % config_file)
    return config_file_dict

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


######################### Global variables ######################

# Variables that can be imported into the env dictionary
hosts = list()
roledefs = dict()

# Get nodes and their roles from the config files
compute_nodes = read_nodes('../global_config_files/compute_nodes')
controller_nodes = read_nodes('../global_config_files/controller_nodes')
network_nodes = read_nodes('../global_config_files/network_nodes')
storage_nodes = read_nodes('../global_config_files/storage_nodes')

hosts = compute_nodes + controller_nodes + network_nodes
roledefs = { 'controller':controller_nodes, 'compute':compute_nodes, 'network':network_nodes, 'storage':storage_nodes }

global_config_file = '../global_config_files/global_config'
global_config_location =  '../global_config_files/'

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


# scripts to be sourced

admin_openrc = global_config_location + 'admin-openrc.sh'
demo_openrc = global_config_location + 'demo-openrc.sh'

# get passwords

global_config_file_lines = check_output("crudini --get --list --format=lines " + global_config_file,shell=True).splitlines()
# drop header
global_config_file_lines = [line.split(' ] ')[1] for line in global_config_file_lines]
# break between parameter and value
pairs = [line.split(' = ') for line in global_config_file_lines]
# make passwd dictionary
passwd = {pair[0].upper():pair[1] for pair in pairs}

####################### useful functions #################################


def db_exists(db):

    # 'OK' message
    okay = '[ ' + green('OK') + ' ]'
    
    command = "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{}';".format(db)
    if db in sudo("""echo "{}" | mysql -u root""".format(command)):
        return True
    else:
	return False
    
def table_count(db):
    command = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '{}';".format(db) 
    output = sudo("""echo "{}" | mysql -u root | grep -v "COUNT" """.format(command))
    return int(output)


