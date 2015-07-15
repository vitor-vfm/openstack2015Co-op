from __future__ import with_statement
from fabric.decorators import with_settings
from fabric.api import *
from fabric.context_managers import cd
from fabric.colors import green, red, blue
from fabric.contrib.files import append
import string
import subprocess
import logging

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, set_parameter

 
######################### Configuring Environment ###########################

confFile = '/etc/keystone/keystone.conf'


######################### Integrate Identity with LDAP ######################

def defineDestination():
    msg = 'Make a backup of keystone.conf'
    runCheck(msg, "cp %s %s.backup" % (confFile, confFile))

    set_parameter(confFile, 'ldap', 'url', 'ldap://localhost')
    set_parameter(confFile, 'ldap', 'user', 'dc=Manager,dc=example,dc=org')
    set_parameter(confFile, 'ldap', 'password', '34ldappass43')
    set_parameter(confFile, 'ldap', 'suffix', 'dc=example,dc=org')
    set_parameter(confFile, 'ldap', 'use_dumb_member', 'False')
    set_parameter(confFile, 'ldap', 'allow_subtree_delete', 'False')
    
def setQueryOption():
    set_parameter(confFile, 'ldap', 'query_scope', 'sub')
    set_parameter(confFile, 'ldap', 'page_size', '0')
    set_parameter(confFile, 'ldap', 'alias_dereferencing', 'default')
    set_parameter(confFile, 'ldap', 'chase_referrals', '')
    
def setDebug():
    set_parameter(confFile, 'ldap', 'debug_level', '-1')
    
def setConnectionPooling():
    set_parameter(confFile, 'ldap', 'use_pool', 'true')
    set_parameter(confFile, 'ldap', 'pool_size', '10')
    set_parameter(confFile, 'ldap', 'pool_retry_max', '3')
    set_parameter(confFile, 'ldap', 'pool_retry_delay', '0.1')
    set_parameter(confFile, 'ldap', 'pool_connection_timeout', '-1')
    set_parameter(confFile, 'ldap', 'pool_connection_lifetime', '600')

def setConnectionPoolingForEndUserAuthentication():
    set_parameter(confFile, 'ldap', 'use_auth_pool', 'false')
    set_parameter(confFile, 'ldap', 'auth_pool_size', '100')
    set_parameter(confFile, 'ldap', 'auth_pool_connection_lifetime', '60')

def restartKeystone():
    runCheck('Restart Openstack Identity service', 'service keystone restart')
    
############ Integrate Identity Back End with LDAP ##########################

def enableLDAPIdentityDriver():
    set_parameter(confFile, 'identity', 'driver', 'keystone.identity.backends.ldap.IDENTITY')

def createOrganizationalUnitsAndDefineLocation():
    set_parameter(confFile, 'ldap', 'user_tree_dn', 'ou=Users,dc=example,dc=org')
    set_parameter(confFile, 'ldap', 'user_objectclass', 'inetOrgPerson')
    set_parameter(confFile, 'ldap', 'group_tree_dn', 'ou=Groups,dc=example,dc=org')
    set_parameter(confFile, 'ldap', 'group_objectclass', 'groupOfNames')



    

######################### Deployment ########################################



