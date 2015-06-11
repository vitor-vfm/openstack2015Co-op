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
