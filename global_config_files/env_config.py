import ConfigParser
import logging 
from subprocess import check_output, call
from fabric.api import run, sudo, env
from fabric.colors import red, green
from fabric.api import *
##################### General functions ######################


def keystone_check(name):

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


    # 'OK' message
    okay = '[ ' + green('OK') + ' ]'

    def quiet_sudo(command):
        return sudo(command, quiet=True)
       # return sudo(command)


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

    admin_openrc = global_config_location + 'admin-openrc.sh'
    exports = open(admin_openrc,'r').read()
    with prefix(exports): 
        user_check()
        tenant_check()
        service_exists(name)
        endpoint_check(name)
        
        if name != 'keystone':
            user_exists(name)
            user_enabled(name)


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


def getRole():
    for role in env.roledefs.keys():
        if env.host_string in env.roledefs[role]:
            return role
    # if none was found
    raise ValueError("Host " + env.hoststring + " not in roledefs")

# parse a config file and return all the 
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

############################## Logging #########################

def log_general(func,msg):
    d = {'host_string':env.host}
    return func(msg,extra = d)

log_debug = lambda msg : log_general(logging.debug,msg)
log_error = lambda msg : log_general(logging.error,msg)
log_info = lambda msg : log_general(logging.info,msg)

# Do a fabric command on the string 'command' and log results
def fabricLog(command,func):
    output = func(command)
    if output.return_code != 0:
        log_error("Problem on command '{}'")
    else:
        for line in output.splitlines():
            # don't log lines that have passwords
            if 'pass' not in line.lower():
                # skip empty lines
                if line != '' or line !='\n':
                    log_debug(line)
    return output


def run_log(command):
    return fabricLog(command,run)

def sudo_log(command):
    return fabricLog(command,sudo)

def setupLoggingInFabfile(log_file):
    logfilename = log_location + log_file

    if log_file not in check_output('ls ' + log_location,shell=True):
        # file doesn't exist yet; create it
        call('touch ' + logfilename,shell=True)
        call('chmod 644 ' + logfilename,shell=True)

    logging.basicConfig(filename=logfilename,level=logging.DEBUG,format=log_format,\
            host_string=env.host)
    # set paramiko logging to only output warnings
    logging.getLogger("paramiko").setLevel(logging.WARNING)


log_format = '%(asctime)-15s:%(levelname)s:%(host_string)s:\t%(message)s'
log_location = '../var/log/juno/'
if not check_output('if [ -e {} ]; then echo found; fi'.format(log_location),shell=True):
    # location not created yet
    call('mkdir -p ' + log_location,shell=True)
    call('chmod 744 ' + log_location,shell=True)
log_dict = {'host_string':'','role':''} # default value for log_dict

######################### Global variables ######################

if 'ipmi5' in check_output('echo $HOSTNAME',shell=True):
    # PRODUCTION
    pass
else:
    # DEVELOPMENT

    global_config_location =  '../global_config_files/'

    # mariadb
    mariaDBmysqldSpecs = ['default-storage-engine=innodb',
                          'innodb_file_per_table',
                          'collation-server=utf8_general_ci',
                          'init-connect=SET NAMES utf8',
                          'character-set-server=utf8']

    # scripts to be sourced
    admin_openrc = global_config_location + 'admin-openrc.sh'
    demo_openrc = global_config_location + 'demo-openrc.sh'

    # for the env dictionary
    roledefs = { 'compute' : ['root@computeVM'],
                 'network' : ['root@networkVM'],
                 'storage' : ['root@storageVM'],
                 'controller' : ['root@controllerVM']}
    hosts = roledefs.values()

    # keystone data
    keystone = { 'ADMIN_EMAIL' : 'admin@example.com',
                 'DEMO_EMAIL' : 'demo@example.com'}

    # ntp
    ntpServers = ['time1.srv.ualberta.ca','time2.srv.ualberta.ca','time3.srv.ualberta.ca']

    # passwords
    passwd = { 'METADATA_SECRET' : '34m3t$3c43',
               'RABBIT_PASS' : '34RabbGuest43',
               'NOVA_DBPASS' : '34nova_db43',
               'NEUTRON_DBPASS' : '34neu43',
               'HEAT_DBPASS' : '34heat_db43',
               'GLANCE_DBPASS' : '34glance_db43',
               'SAHARA_DBPASS' : '34sahara_db43',
               'CINDER_DBPASS' : '34cinder_db43',
               'ADMIN_PASS' : '34adm43',
               'DEMO_PASS' : '34demo43',
               'NOVA_PASS' : '34nova_ks43',
               'NEUTRON_PASS' : '34neu43',
               'HEAT_PASS' : '34heat_ks43',
               'GLANCE_PASS' : '34glance_ks43',
               'SAHARA_PASS' : '34sahara_ks43',
               'CINDER_PASS' : '34cinder_ks43',
               'SWIFT_PASS' : '34$w1f43',
               'TROVE_PASS' : '34Tr0v343',
               'TROVE_DBPASS' : '34Tr0v3db4s343'}

    # basic networking

    controllerManagement = { 'DEVICE' : 'eth1',
                             'IPADDR' : '192.168.1.11',
                             'NETMASK' : '255.255.255.0'}

    controllerTunnels = { 'DEVICE' : 'eth2',
                          'IPADDR' : '192.168.2.11',
                          'NETMASK' : '255.255.255.0'}

    networkManagement = { 'DEVICE' : 'eth1',
                          'IPADDR' : '192.168.1.21',
                          'NETMASK' : '255.255.255.0'}

    networkTunnels = { 'DEVICE' : 'eth2',
                       'IPADDR' : '192.168.2.21',
                       'NETMASK' : '255.255.255.0'}

    networkExternal = { 'DEVICE' : 'eth3',
                        'TYPE' : 'Ethernet',
                        'ONBOOT' : '"yes"',
                        'BOOTPROTO' : '"none"',
                        'IPADDR' : '192.168.3.21'}

    computeManagement = { 'DEVICE' : 'eth1',
                          'IPADDR' : '192.168.1.41',
                          'NETMASK' : '255.255.255.0'}

    computeTunnels = { 'DEVICE' : 'eth2',
                       'IPADDR' : '192.168.2.41',
                       'NETMASK' : '255.255.255.0'}

    hosts = { controllerManagement['IPADDR'] : 'controller',
              networkManagement['IPADDR'] : 'network'}

    # add the compute nodes to hosts config
    baseIP = computeManagement['IPADDR']
    for i, computeNode in enumerate(roledefs['compute']):
        # increment base ip
        baseIPListOfInts = [int(octet) for octet in baseIP.split('.')]
        baseIPListOfInts[-1] += i
        IP = "".join([str(octet)+'.' for octet in baseIPListOfInts])
        IP = IP[:-1] # remove last dot

        hosts[IP] = 'compute' + str(i+1)

    # neutron

    # this script creates a database to be used by Neutron
    # 'NEUTRON_DBPASS' should be replaced by a suitable password
    databaseScript = "CREATE DATABASE IF NOT EXISTS neutron; " + \
            "GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'localhost' " + \
            "IDENTIFIED BY 'NEUTRON_DBPASS'; " +\
            "GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'%' " +\
            "IDENTIFIED BY 'NEUTRON_DBPASS';"



