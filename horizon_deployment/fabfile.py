from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import string
import logging

import sys
sys.path.append('../global_config_files')
import env_config


logging.basicConfig(filename='/tmp/juno2015.log',level=logging.DEBUG, format='%(asctime)s %(message)s')


############################ Config ########################################

env.roledefs = env_config.roledefs

etc_horizon_config_file = "/etc/openstack-dashboard/local_settings"


def sudo_log(command):
    output = sudo(command)
    logging.info(output)
    return output

def run_log(command):
    output = run(command)
    logging.info(output)
    return output


################### General functions ########################################

def get_parameter(config_file, section, parameter):
    crudini_command = "crudini --get {} {} {}".format(config_file, section, parameter)
    return sudo_log(crudini_command)

def set_parameter(config_file, section, parameter, value):
    crudini_command = "crudini --set {} {} {} {}".format(config_file, section, parameter, value)
    sudo_log(crudini_command)


def setup_horizon_config_files():
    sudo_log("yum install -y openstack-dashboard httpd mod_wsgi memcached python-memcached")


    # uncomment below if you wish to delete config file and reinstall it 
#    sudo_log("rm " + etc_horizon_config_file)
#    sudo_log("yum reinstall -y openstack-dashboard")


    # set OPENSTACK_HOST = "controller"
    sudo_log("""sed -i.bak 's/OPENSTACK_HOST = "127.0.0.1"/OPENSTACK_HOST = {} /g' {} """.format('"controller"',etc_horizon_config_file))


    # set 'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
    sudo_log("""sed -i.bak1 "s/'django\.core\.cache\.backends\.locmem\.LocMemCache'/'django\.core\.cache\.backends\.memcached\.MemcachedCache',/g" /etc/openstack-dashboard/local_settings""")

    
    # remove commented #        'BACKEND': 'django\.core\.cache\.backends\.memcached\.MemcachedCache
    # in order to add 'LOCATION': '127.0.0.1:11211', with problem
    sudo_log("""sed -i "s/#        'BACKEND': 'django\.core\.cache\.backends\.memcached\.MemcachedCache',/\ /g " /etc/openstack-dashboard/local_settings""") 

    # set 'LOCATION': '127.0.0.1:11211',
    sudo_log("""sed -i.bak2  "/'django\.core\.cache\.backends\.memcached\.MemcachedCache'/a\ \ \ \ \ \ \ \ 'LOCATION' : '127\.0\.0\.1:11211'," /etc/openstack-dashboard/local_settings """)


    # set ALLOWED_HOSTS = ['*']
    sudo_log("""sed -i.bak3 "s/ALLOWED_HOSTS = \['horizon\.example\.com', 'localhost'\]/ALLOWED_HOSTS = \['\*'\] /g" /etc/openstack-dashboard/local_settings """)

    # set TIME_ZONE = "TIME_ZONE"
    sudo_log("""sed -i.bak4  's/TIME_ZONE = "UTC"/TIME_ZONE = "America\/Edmonton" /g' /etc/openstack-dashboard/local_settings""")
    

def finalize_installation():
#    sudo_log("setsebool -P httpd_can_network_connect on")
    sudo_log("chown -R apache:apache /usr/share/openstack-dashboard/static")

def start_horizon_services():
    sudo_log("systemctl enable httpd.service memcached.service")
    sudo_log("systemctl start httpd.service memcached.service")


def download_packages():
    # make sure we have crudini
    sudo_log('yum install -y crudini')
   
def setup_horizon():
    setup_horizon_config_files()
    finalize_installation()
    start_horizon_services()

################### Deployment ########################################

#@roles('controller')
def deploy():
    setup_horizon()

######################################## TDD #########################################


def reach_dashboard():
    sudo_log("yum install -y wget")
    output = sudo_log("wget -Oo --tries=1 http://controller/dashboard")

    if 'connected' in output:
        print(green("Can connect to dashboard"))
    else:
        print(green("CANT connect to dashboard"))
        
#@roles('controller')
def tdd():
    with settings(warn_only=True):
        reach_dashboard()
        pass
