from fabric.colors import green, red
from fabric.api import run
from env_config import *

def printMessage(status, msg):
	if (status == "good"):
		 #print(green("\t\t[GOOD] ") + " I can: "+ msg)
                print align_y('I can: ' + msg)
	else:
		 #print(red("\t\t[OOPS] ") + " I CANNOT: "+ msg)
                print align_n('I CANNOT: ' + msg)

import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%b %d %H:%M',
                    #filename='/opt/coop2015/coop2015/fabric.log',
                    filename=logfilename,
                    filemode='a'
                    )

def grep(pattern,stream):
    """
    takes a string and a pattern
    and returns all the lines in the string
    that contain the pattern
    """
    return [l for l in stream.splitlines() if pattern in l]

def checkLog(time):
    """
    given a timestamp, outputs all error in the logs 
    that happened after the timestamp
    """

    result = ""
    maxLines = 20

    # remove last digit to avoid too
    # much precision
    time = time[:-1]

    for log in lslogs:
        # Filter out all lines before the timestamp and grep for errors
        error = run("if [ -e {} ]; then ".format(log) +\
                "sed '0,/{}/d' {}; fi".format(time,log)\
                # "sed -n '/{}/,/{}/p' {}; fi".format(before,after,log)\
                ,quiet=True)

        if error:

            # avoid too many lines
            error = run("echo '{}' | tail -{}".format(error,maxLines),quiet=True)
                
            result += red("Found error on log " + log + "\n")
            result += error
            result += "\n"

    return result
        



def runCheck(msg,command,quiet=False):
    """
    Runs a fabric command and reports
    results, logging them in necessary
    """
    # time = run('date +"%Y-%m-%d %H:%M"')
    time = run('date +"%Y-%m-%d %H:%M:%S"',quiet=True)
    out = run(command,quiet=quiet,warn_only=True)

    if out.return_code == 0:
        result = 'good'
        logging.debug('Success on: ' + msg)
    else:
        result = 'oops'
        errormsg = 'Failure on: ' + msg
        logging.error(errormsg)
        logging.error(out)
        print checkLog(time)

    printMessage(result,msg)
    return out


def set_parameter(config_file, section, parameter, value):
    """
    Change a parameter in a config file

    Wrapper for crudini
    """
    crudini_command = "crudini --set {} {} {} {}".format(config_file, section, parameter, value)
    result = run(crudini_command,warn_only=True,quiet=True)
    if result.return_code != 0:
        print align_n("Couldn't set parameter {} on {}".format(parameter,config_file))
        print red("SHELL OUTPUT: " + result)
    else:
        print align_y(crudini_command)
    return result

def get_parameter(config_file, section, parameter, value):
    """
    Get a parameter in a config file

    Wrapper for crudini
    """
    crudini_command = "crudini --get {} {} {} {}".format(config_file, section, parameter, value)
    result = run(crudini_command,warn_only=True,quiet=True)
    if result.return_code != 0:
        print align_n("\t\t[OOPS] Couldn't get parameter {} on {}".format(parameter,config_file))
        print red("SHELL OUTPUT: " + result)
    return result


def createDatabaseScript(databaseName,password):
    """
    Returns a database script based on
    a general template.

    Inputs: a database name and a password
    Outputs: a string containing a MySQL script
    """

    return \
            "DROP DATABASE IF EXISTS {}; ".format(databaseName) + \
            "CREATE DATABASE {}; ".format(databaseName) + \
            "GRANT ALL PRIVILEGES ON {}.* TO '{}'@'controller' ".format(databaseName,databaseName) + \
            "IDENTIFIED BY '{}'; ".format(password) +\
            "GRANT ALL PRIVILEGES ON {}.* TO '{}'@'localhost' ".format(databaseName,databaseName) + \
            "IDENTIFIED BY '{}'; ".format(password) +\
            "GRANT ALL PRIVILEGES ON {}.* TO '{}'@'%' ".format(databaseName,databaseName) + \
            "IDENTIFIED BY '{}';".format(password)

def getRole():
    """
    Find the role of the current host
    """
    for role in env.roledefs.keys():
        if env.host_string in env.roledefs[role]:
            return role

    # if none was found
    raise ValueError("Host " + env.hoststring + " not in roledefs")

def parseConfig(cfg,section):
    """
    Parse a config file and return all the 
    variables in the given section in a dictionary
    """

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

def fix_length(message, max_len):
    """
    appends spaces until message is max_len characters long


    requires:
    - message to elongated, if less than max_len characters long
    - maximum length to elongate message to 

    returns:
    - message increased to max len characters long in string format

    """
    
    new_message = [message]
    if len(message) < max_len and not len(message) > max_len:
        count = max_len - len(message)
        index = 1;
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

    max_len = 80

   
    new_message = [fix_length(message, max_len)]


    new_message.append('[  ' + green('OK') + '  ]')
    new_message.append('\n')
    return "".join(new_message)


def align_n(message):
    """
    returns a still nicely formatted message but for a negative occasion

    >>> align_n("wow what a") == 'wow what a-------------------------------------------------[ ' + red('FAIL') + ' ]'
    True
    >>> align_n("but yeah, see how it works with different lengths?") == 'but yeah, see how it works with different lengths?---------[ ' + red('FAIL') + ' ]'
    True

    """

    max_len = 80
    
    new_message = [fix_length(message, max_len)]

    new_message.append('[ ' + red('FAIL') + ' ]\n')        
    new_message.append('\n')
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

def run_v(command, verbose=False):
    # ref: http://www.pythoncentral.io/one-line-if-statement-in-python-ternary-conditional-operator/
    # <expression1> if <condition> else <expression2>        
    return run(command) if verbose else run(command, quiet=True)





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
    def tenant_check():
        tenants = ['admin', 'demo', 'service']

        for tenant in tenants:
            if tenant in run_v("cat tenant-list | awk '// {print $4}'"):
                print align_y(tenant + ' tenant enabled')

                if "True" == run_v("cat tenant-list | awk '/" + tenant + "/ {print $6}'"):
                    print align_y(tenant + " tenant enabled")
                else:
                    print align_n(tenant + "  tenant disabled")

            else:
                print align_n(tenant + " tenant absent")

    def user_check():
        users = ['admin', 'demo']

        for user in users:
            if user in run_v("cat user-list | awk '// {print $4}'"):
                print align_y(user + ' user enabled')

                if "True" == run_v("cat user-list | awk '/" + user + "/ {print $6}'"):
                    print align_y(user + " user enabled")
                else:
                    print align_n(user + " user disabled")

            else:
                print align_n(user + " user absent")


        

    def user_exists(name):
        if name in run_v("cat user-list | awk '// {print $4}'"):
            print align_y(name + ' user exists')
        else:
            print align_n(name + " user absent")
            
    def user_enabled(name):
        if "True" == run_v("cat user-list | awk '/" + name + "/ {print $6}'"):
            print align_y(name + " user enabled")
        else:
            print align_n(name + " user disabled")

    def service_exists(name):
        if name in run_v("cat service-list | awk '// {print$4}'"):
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

        #service_type = run_v("cat service-list | awk '/ " + name + "/ {print $6}'")
        if name not in run_v("cat service-list"):
            print(red("Service not found in service list. Service does not exist, so endpoint can't exist. Exiting function"))
            return
            

        service_id = run_v("cat service-list | awk '/ "+ name + " / {print $2}'")

        if service_id not in run_v("cat endpoint-list"):
            print(red("Service id not found in endpoint list. Endpoint does not exist. Exiting function"))
            return

        urls = ref_d[name]

        admin_url_found = run_v("cat endpoint-list | awk '/" + service_id + "/ {print$10}'")
        internal_url_found = run_v("cat endpoint-list | awk '/" + service_id + "/ {print$8}'")
        public_url_found = run_v("cat endpoint-list | awk '/" + service_id + "/ {print$6}'")

        proper_admin_url = urls[0]
        proper_internal_url = urls[1]
        proper_public_url = urls[2]
            
        if (admin_url_found == proper_admin_url):
            print align_y("Admin url correct")
        else:
            print align_n("Admin url incorrect")

        if (internal_url_found == proper_internal_url):
            print align_y("Internal url correct")
        else:
            print align_n("Internal url incorrect")

        if (public_url_found == proper_public_url):
            print align_y("Public url correct")
        else:
            print align_n("Public url incorrect")
    # call all functions 

    with prefix(admin_openrc):
        # Get lists and save them into local files
        run("keystone service-list >service-list",quiet=True)
        run("keystone tenant-list >tenant-list",quiet=True)
        run("keystone user-list >user-list",quiet=True)
        run("keystone endpoint-list >endpoint-list",quiet=True)

        user_check()
        tenant_check()
        service_exists(name)
        endpoint_check(name)
        
        if name != 'keystone':
            user_exists(name)
            user_enabled(name)

        # remove local files
        run("rm service-list",quiet=True)
        run("rm tenant-list",quiet=True)
        run("rm user-list",quiet=True)
        run("rm endpoint-list",quiet=True)


# General database check that will be used in several TDDs
def database_check(db,verbose=False):




    def db_exists(db):
        command = "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{}';".format(db)
        if db in run_v("""echo "{}" | mysql -u root""".format(command)):
            return True
        else:
            return False
        
    def table_count(db):
        command = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '{}';".format(db) 
        output = run_v("""echo "{}" | mysql -u root | grep -v "COUNT" """.format(command))
        return int(output)

    if db_exists(db):
        message = "DB " + db + " exists"
        print align_y(message)
        logging.debug(message)
    else:
        message = "DB " + db + " does not exist"
        print align_n(message)
        logging.debug(message)

    nbr = table_count(db)
    if nbr > 0:
        message = "table for " + db + " has " + str(nbr) + " entries"
        print align_y(message)
        logging.debug(message)
    else:
        message = "table for " + db + " is empty. Nbr of entries : " + str(nbr)
        print align_n(message)
        logging.debug(message)
