from fabric.colors import green, red


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