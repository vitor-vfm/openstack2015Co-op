#!/bin/bash

NODE=$1

declare -A nodes=(
    [controller]=10.70.4.10
    [network]=10.70.4.11
    [compute1]=10.70.4.12
    [compute2]=10.70.4.13
    [compute3]=10.70.4.14
    [compute4]=10.70.4.15
)


if [ !  -z  $NODE  ];then
	echo "Status of ${nodes[$NODE]}"
	ipmitool -I lanplus -H ${nodes[$NODE]} -U ADMIN -P ADMIN  sdr list

else
	for i in controller network compute1 compute2 compute3 compute4;
	do
		echo "Status of ${nodes[$i]}"
		ipmitool -I lanplus -H ${nodes[$i]} -U ADMIN -P ADMIN  sdr list
	done
fi

exit
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
