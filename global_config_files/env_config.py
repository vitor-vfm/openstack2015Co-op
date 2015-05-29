from subprocess import check_output

# Variables that can be imported into the env dictionary
hosts = list()
roledefs = dict()

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


# Get nodes and their roles from the config files
compute_nodes = read_nodes('../global_config_files/compute_nodes')
controller_nodes = read_nodes('../global_config_files/controller_nodes')
network_nodes = read_nodes('../global_config_files/network_nodes')

hosts = compute_nodes + controller_nodes + network_nodes
roledefs = { 'controller':controller_nodes, 'compute':compute_nodes, 'network':network_nodes }
global_config_file = '../global_config_files/global_config'
global_config_location =  '../global_config_files/'

# scripts to be sourced

admin_openrc = global_config_location + 'admin-openrc.sh'
demo_openrc = global_config_location + 'demo-openrc.sh'

# get passwords

global_config_file_lines = check_output("crudini --get --list --format=lines " + global_config_file,shell=True).splitlines()
# drop header
global_config_file_lines = [line.split(' ] ')[1] for line in global_config_file_lines]
# break between parameter and value
pairs = [line.split(' = ') for line in global_config_file_lines]
# remove parameters that aren't passwords
pairs = [pair for pair in pairs if 'PASS' in pair[0] or 'pass' in pair[0]]
# make passwd dictionary
passwd = {pair[0].upper():pair[1] for pair in pairs}

