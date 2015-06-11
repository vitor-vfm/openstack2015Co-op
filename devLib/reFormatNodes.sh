#!/bin/bash
NODELIST="10.70.4.10 10.70.4.11 10.70.4.12 10.70.4.13 10.70.4.14 10.70.4.15"

for item in $NODELIST
do
	echo "reformating  $item"
	ipmitool -I lanplus -H $item -U ADMIN -P ADMIN  chassis bootdev pxe
	ipmitool -I lanplus -H $item -U ADMIN -P ADMIN  power reset
done




#Get a serial-over-lan console on rcXX: 
#	ipmitool -I lanplus -H xx.xx.xx.xx -U ADMIN -P ADMIN -a sol activate
#Get the power status: 
#	ipmitool -I lanplus -H xx.xx.xx.xx -U ADMIN -P ADMIN  chassis status
#Reboot a machine: 
#	ipmitool -I lanplus -H xx.xx.xx.xx -U ADMIN -P ADMIN  power reset
#Force PXE boot on the next boot only:
#	 ipmitool -I lanplus -H xx.xx.xx.xx -U ADMIN -P ADMIN  chassis bootdev pxe
#(This will cause the machine to reinstall all its software on the next boot)
#Reboot the IPMI card:
#	 ipmitool -I lanplus xx.xx.xx.xx -U ADMIN -P ADMIN  mc reset cold
#Get sensor output:
#	 ipmitool -I lanplus xx.xx.xx.xx -U ADMIN -P ADMIN  sdr list
#Get the error log:
#	 ipmitool -I lanplus -H xx.xx.xx.xx -U ADMIN -P ADMIN  sel elist
