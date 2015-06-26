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

start=$1
end=$2

function check_port {
    nodes="controller compute1 network storage1"
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


    red=`tput setaf 1`
    green=`tput setaf 2`
    reset=`tput sgr0`
    
    for port in $ports;
    do

	echo -e '\n\n'
	echo '##################'
	echo 'Checking port ' $port ' in component ' $1
	echo '##################'
	for node in $nodes;
	do
	    output=$(ssh root@$node "ss -nltp | grep $port")
	    if [[ "$output" =~ ^LISTEN ]]
	    then
		echo "${green}LISTENER on $node ${reset}"	    
		
	    else
		echo "${red}No LISTENER on $node ${reset}"	    
		
	    fi
	done

    done
}    


if ! [ -z "$end"  ]
then
    for i in $(seq $start $end); 
    do
	check_port $i
	
    done
else
    # to handle the case when a single 
    # digit is specified in the range
    check_port $start
    
fi
