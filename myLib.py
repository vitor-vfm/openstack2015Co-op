from fabric.colors import green, red


def printMessage(status, msg):
	if (status == "good"):
		 print(green("\t\t[GOOD] ") + " I can: "+ msg)
	else:
		 print(red("\t\t[OOP's] ") + " I CANNOT: "+ msg)

import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%b %d %H:%M',
                    filename='/opt/coop2015/coop2015/fabric.log',
                    filemode='a'
                    )
