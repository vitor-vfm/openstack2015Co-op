from fabric.colors import green, red
from fabric.api import run


def printMessage(status, msg):
	if (status == "good"):
		 print(green("\t\t[GOOD] ") + " I can: "+ msg)
	else:
		 print(red("\t\t[OOP's] ") + " I CANNOT: "+ msg)

import logging

logging.basicConfig(filename='/tmp/test.log',level=logging.DEBUG)
#logging.debug('This message should go to the log file')
#logging.info('So should this')
#logging.warning('And this, too')


def runCheck(msg,command):

    out = run(command,warn_only=True)
    if out.return_code == 0:
        result = 'good'
        logging.debug('Success on: ' + msg)
    else:
        result = 'oops'
        errormsg = 'Failure on: ' + msg
        logging.error(errormsg)
    printMessage(result,msg)
    return out



def fix_length(message, max_len):
    """
    appends spaces until message is max_len characters long


    requires:
    - message to elongated, if less than max_len characters long
    - maximum length to elongate message to 

    returns:
    - message increased to max len characters long in string format

    """

    if len(message) < max_len and not len(message) > max_len:
        count = max_len - len(message)
        index = 1;
        new_message = [message]
        while (index < count):
            new_message.append('-');
            index = index + 1

    return "".join(new_message)

def align_y(message):
    """
    returns a nicely formatted positive message in string format for you to print

    >>> align_y("Print OK if is this function is wonderful") == 'Print OK if is this function is wonderful------------------[  ' + green('OK') + '  ]'
    True
    >>> align_y("but seriously its good") == 'but seriously its good-------------------------------------[  ' + green('OK') + '  ]'
    True

    """

    max_len = 60

   
    new_message = [fix_length(message, max_len)]

    new_message.append('[  ' + green('OK') + '  ]')
    return "".join(new_message)


def align_n(message):
    """
    returns a still nicely formatted message but for a negative occasion

    >>> align_n("wow what a") == 'wow what a-------------------------------------------------[ ' + red('FAIL') + ' ]'
    True
    >>> align_n("but yeah, see how it works with different lengths?") == 'but yeah, see how it works with different lengths?---------[ ' + red('FAIL') + ' ]'
    True

    """

    max_len = 60
    
    new_message = [fix_length(message, max_len)]

    new_message.append('[ ' + red('FAIL') + ' ]')        
    return "".join(new_message)

def _test():
    # function that initiates doctests
    import doctest
    doctest.testmod(verbose=True)
    
if __name__ == '__main__': 
    # if statement so we only do the tests
    # when someone does python (this filename).py 
    # not when someone imports or something

    print "TESTING"

    print '\n'
    print "Aligned results example:"
    print align_n("nova user disabled")
    print align_y("nova user enabled")
    _test()


    print 'Finished Testing ' + '[ ' + green('OK') + ' ]'        

def keystone_check(name, verbose=False):
    
    """
    keystone check function


    requires: 
    - as argument: name of component being tdd'd
    - requires the admin-openrc.sh file to be sourced
    as it will be doing lots of keystone stuff... understandably


    checks for:
    - existence of user
    - the enable status of user (does not enable user)
    - existence of service
    - existence of endpoint
    
    Also checks to make sure admin url, internal url and public url
    of the endpoint match the ones given in the manual


    Tested on:
    - glance
    - keystone
    - nova
    - neutron

    TODO:
    - quiet and verbose modes (DONE)

    """


    def sudo_v(command):
        # ref: http://www.pythoncentral.io/one-line-if-statement-in-python-ternary-conditional-operator/
        # <expression1> if <condition> else <expression2>        
        return sudo(command) if verbose else sudo(command, quiet=True)


    def tenant_check():
        tenants = ['admin', 'demo', 'service']

        for tenant in tenants:
            if tenant in sudo_v("keystone tenant-list | awk '// {print $4}'"):
                print align_y(tenant + 'tenant enabled')

                if "True" == sudo_v("keystone tenant-list | awk '/" + tenant + "/ {print $6}'"):
                    print align_y(tenant + "tenant enabled")
                else:
                    print align_n(tenant + "tenant disabled")

            else:
                print align_n(tenant + "tenant absent")

    def user_check():
        users = ['admin', 'demo']

        for user in users:
            if user in sudo_v("keystone user-list | awk '// {print $4}'"):
                print align_y(user + 'user enabled')

                if "True" == sudo_v("keystone user-list | awk '/" + user + "/ {print $6}'"):
                    print align_y(user + "user enabled")
                else:
                    print align_n(user + "user disabled")

            else:
                print align_n(user + "user absent")


        

    def user_exists(name):
        if name in sudo_v("keystone user-list | awk '// {print $4}'"):
            print align_y(user + 'user exists')
        else:
            print align_n(user + "user absent")
            
    def user_enabled(name):
        if "True" == sudo_v("keystone user-list | awk '/" + name + "/ {print $6}'"):
            print align_y(user + "user enabled")
        else:
            print align_n(user + "user disabled")

    def service_exists(name):
        if name in sudo_v("keystone service-list | awk '// {print$4}'"):
            print align_y(name + 'service exists')
        else:
            print align_n(name + 'service absent')
    
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

        #service_type = sudo_v("keystone service-list | awk '/ " + name + "/ {print $6}'")
        if name not in sudo_v("keystone service-list"):
            print(red("Service not found in service list. Service does not exist, so endpoint can't exist. Exiting function"))
            return
            

        service_id = sudo_v("keystone service-list | awk '/ "+ name + " / {print $2}'")

        if service_id not in sudo_v("keystone endpoint-list"):
            print(red("Service id not found in endpoint list. Endpoint does not exist. Exiting function"))
            return

        urls = ref_d[name]

        admin_url_found = sudo_v("keystone endpoint-list | awk '/" + service_id + "/ {print$10}'")
        internal_url_found = sudo_v("keystone endpoint-list | awk '/" + service_id + "/ {print$8}'")
        public_url_found = sudo_v("keystone endpoint-list | awk '/" + service_id + "/ {print$6}'")

        proper_admin_url = urls[0]
        proper_internal_url = urls[1]
        proper_public_url = urls[2]
            
        if (admin_url_found == proper_admin_url):
            print align_y("Admin url correct")
        else:
            print align_n("Admin url incorrect")

        if (internal_url_found == proper_proper_url):
            print align_y("Internal url correct")
        else:
            print align_n("Internal url incorrect")

        if (public_url_found == proper_public_url):
            print align_y("Public url correct")
        else:
            print align_n("Public url incorrect")
    # call all functions 

    admin_openrc = global_config_location + 'admin-openrc.sh'
    admin_openrc_file = open(admin_openrc,'r')
    exports = admin_openrc_file.read()
    with prefix(exports): 
        user_check()
        tenant_check()
        service_exists(name)
        endpoint_check(name)
        
        if name != 'keystone':
            user_exists(name)
            user_enabled(name)

    admin_openrc_file.close()

#keystone_check('glance', True)


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
        print align_y(message)
        print okay
        logging.debug(message,extra=log_dict)
    else:
        message = "DB " + db + " does not exist"
        print align_n(message)
        print red(message)
        logging.debug(message,extra=log_dict)

    nbr = table_count(db)
    if nbr > 0:
        message = "table for " + db + " has " + str(nbr) + " entries"
        print align_y(message)
        print green(message)
        print okay
        logging.debug(message,extra=log_dict)
    else:
        message = "table for " + db + " is empty. Nbr of entries : " + str(nbr)
        print align_n(message)
        print red(message)
        logging.debug(message,extra=log_dict)
