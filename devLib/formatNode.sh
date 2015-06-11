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
	echo "reformating  $NODE"
	ipmitool -I lanplus -H $NODE -U ADMIN -P ADMIN  chassis bootdev pxe
	ipmitool -I lanplus -H $NODE -U ADMIN -P ADMIN  power reset

else
	for i in controller network compute1 compute2 compute3 compute4;
	do
		echo "reformating  ${nodes[$i]}"
		ipmitool -I lanplus -H ${nodes[$i]} -U ADMIN -P ADMIN  chassis bootdev pxe
		ipmitool -I lanplus -H ${nodes[$i]} -U ADMIN -P ADMIN  power reset
	done
fi