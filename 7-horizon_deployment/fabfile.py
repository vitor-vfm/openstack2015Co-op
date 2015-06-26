from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.context_managers import cd
from fabric.colors import green, red
from fabric.contrib.files import append
import string
import logging

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, align_y, align_n, saveConfigFile


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

etc_horizon_config_file = "/etc/openstack-dashboard/local_settings"

################### General functions ########################################

def setup_horizon_config_files():
    """
    Change variables on the dashboard conf files

    For this function, we can't use crudini because the config files
    have a non-standard format that is not compatible, so the setup
    is done with sed
    """
    msg = 'Install packages'
    runCheck(msg, "yum install -y openstack-dashboard httpd mod_wsgi memcached python-memcached")


    # uncomment below if you wish to delete config file and reinstall it 
    # run("rm " + etc_horizon_config_file)
    # run("yum reinstall -y openstack-dashboard")

    msg = 'set OPENSTACK_HOST = "controller"'
    runCheck(msg, """sed -i.bak 's/OPENSTACK_HOST = "127.0.0.1"/OPENSTACK_HOST = {} /g' {} """.format('"controller"',etc_horizon_config_file))


    imsg = "set 'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache'"
    runCheck(msg, """sed -i.bak1 "s/'django\.core\.cache\.backends\.locmem\.LocMemCache'/'django\.core\.cache\.backends\.memcached\.MemcachedCache',/g" /etc/openstack-dashboard/local_settings""")

    
    # remove commented #        'BACKEND': 'django\.core\.cache\.backends\.memcached\.MemcachedCache
    # in order to add 'LOCATION': '127.0.0.1:11211', with problem
    msg = "Remove comment on BACKEND line"
    runCheck(msg, """sed -i "s/#        'BACKEND': 'django\.core\.cache\.backends\.memcached\.MemcachedCache',/\ /g " /etc/openstack-dashboard/local_settings""") 

    msg = "set 'LOCATION': '127.0.0.1:11211'"
    runCheck(msg, """sed -i.bak2  "/'django\.core\.cache\.backends\.memcached\.MemcachedCache'/a\ \ \ \ \ \ \ \ 'LOCATION' : '127\.0\.0\.1:11211'," /etc/openstack-dashboard/local_settings """)


    msg = "set ALLOWED_HOSTS = ['*']"
    runCheck(msg, """sed -i.bak3 "s/ALLOWED_HOSTS = \['horizon\.example\.com', 'localhost'\]/ALLOWED_HOSTS = \['\*'\] /g" /etc/openstack-dashboard/local_settings """)

    msg = 'set TIME_ZONE'
    runCheck(msg, """sed -i.bak4  's/TIME_ZONE = "UTC"/TIME_ZONE = "America\/Edmonton" /g' /etc/openstack-dashboard/local_settings""")
    

def finalize_installation():
    # Configure SELinux
    # We don't use that
    # runCheck(msg, "setsebool -P httpd_can_network_connect on")

    # Due to a packaging bug, the dashboard CSS fails to load properly.
    # The following command fixes this issue:
    msg = "Set ownership on the openstack-dashboard/static file"
    runCheck(msg, "chown -R apache:apache /usr/share/openstack-dashboard/static")

def start_horizon_services():
    msg = 'Enable Horizon services'
    runCheck(msg, "systemctl enable httpd.service memcached.service")
    msg = 'Start Horizon services'
    runCheck(msg, "systemctl start httpd.service memcached.service")


def download_packages():
    # make sure we have crudini
    msg = 'Install Crudini'
    runCheck(msg, 'yum install -y crudini')
   
def setup_horizon():
    setup_horizon_config_files()
    finalize_installation()
    start_horizon_services()

################################## Deployment ########################################

@roles('controller')
def deploy():

    setup_horizon()

##################################### TDD ############################################


def reach_dashboard():
    msg = 'Connect to dashboard'
    output = runCheck(msg, "curl --connect-timeout 10 http://controller/dashboard | head -10")

    # check if it's the Dashboard frontpage
    if '<title>Login - OpenStack Dashboard</title>' in output:
        print align_y('Can access Dashboard frontpage')
    else:
        print align_n('Cannot access Dashboard frontpage')
        status = 'bad'

@roles('controller')
def tdd():

    # status is initialized as 'good'
    # if any of the tdd functions gets an error,
    # it changes the value to 'bad'
    status = 'good'

    with settings(warn_only=True):
        reach_dashboard()

        # save config file
        saveConfigFile(etc_horizon_config_file, status)
