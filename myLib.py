from fabric.colors import green, red
from fabric.api import run
from global_config_files.env_config import *

def printMessage(status, msg):
	if (status == "good"):
		 print(green("\t\t[GOOD] ") + " I can: "+ msg)
	else:
		 print(red("\t\t[OOP's] ") + " I CANNOT: "+ msg)

import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%b %d %H:%M',
                    #filename='/opt/coop2015/coop2015/fabric.log',
                    filename=logfilename,
                    filemode='a'
                    )


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


def createDatabaseScript(databaseName,password):
    """
    Returns a database script based on
    a general template.

    Inputs: a database name and a password
    Outputs: a string containing a MySQL script
    """

    return  "CREATE DATABASE IF NOT EXISTS {}; ".format(databaseName) + \
            "GRANT ALL PRIVILEGES ON {}.* TO '{}'@'controller' ".format(databaseName,databaseName) + \
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
