#! /bin/bash

<<EOF

Checks whether or not a port listener is setup for a given 
openstack component using ss -nltp | grep port 

Requires:

component

usage:

To check for listeners for component number 2
./port_check 2

EOF

component=$1

case "$1" in 
    0)
	ports=""
	;;
    1)
	ports=""
	;;
    2)
	ports="5672"
	;;
    3)
	ports="35357 5000"
	;;
    4)
	ports="9292"
	;;
    5)
	ports="8774"
	;;
    6)
	ports="9696"
	;;
    7)
	ports=""
	;;
    8)
	ports="8776"
	;;
    9)
	ports="8080"
	;;
    10)
	ports="8004"
	;;
    11)
	ports="8777"

	;;
esac

nodes="controller compute1 network storage1"
for port in $ports;
do
    for node in $nodes;
    do
	ssh root@$node "ss -nltp | grep $port"
    done

done
    
