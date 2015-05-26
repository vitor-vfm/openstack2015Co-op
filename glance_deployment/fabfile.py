from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import string


############################ Config ########################################

# Read the values from a node file into a list
@hosts('localhost')
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
@hosts('localhost')
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
compute_nodes = read_nodes('config_files/compute_nodes')
controller_nodes = read_nodes('config_files/controller_nodes')
network_nodes = read_nodes('config_files/network_nodes')
#env.hosts = compute_nodes + controller_nodes + network_nodes
env.roledefs = { 'controller':controller_nodes, 'compute':compute_nodes, 'network':network_nodes }

# Get configuration dictionaries from the config files
compute_tunnels = read_dict('config_files/compute_instance_tunnels_interface_config')
compute_manage = read_dict('config_files/compute_management_interface_config')
controller_manage = read_dict('config_files/controller_management_interface_config')
network_ext = read_dict('config_files/network_node_external_interface_config')
network_tunnels = read_dict('config_files/network_node_instance_tunnels_interface_config')
network_manage = read_dict('config_files/network_node_management_interface_config')

glance_config_file = 'glance_config'
admin_openrc = "../keystone_deployment/config_files/keystone_admin_files"
demo_openrc = "../keystone_deployment/config_files/keystone_demo_files"

################### General functions ########################################

def get_parameter(section, parameter):
    crudini_command = "crudini --get {} {} {}".format(glance_config_file, section, parameter)
    return sudo(crudini_command)


def setup_glance_database(GLANCE_DBPASS):

    mysql_commands = "CREATE DATABASE glance;"
    mysql_commands = mysql_commands + "GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'localhost' IDENTIFIED BY '{}';".format(GLANCE_DBPASS)
    mysql_commands = mysql_commands + "GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'%' IDENTIFIED BY '{}';".format(GLANCE_DBPASS)

    



def setup_glance():
    
    # make sure we have crudini
    sudo('yum install -y crudini')

    # upload config file for reading via crudini
    put(glance_config_file)

    # setup glance database
    GLANCE_DBPASS = get_parameter('mysql', 'GLANCE_DBPASS')
    setup_glance_database(GLANCE_DBPASS)

    

################### Deployment ########################################

def deploy():
    
    pass

######################################## TDD #########################################


            
def tdd():
    with settings(warn_only=True):
        pass
