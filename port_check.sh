#! /bin/bash

<<<<<<< HEAD:port_check.sh
<<EOF

Checks whether or not a port listener is setup for a given 
openstack component using ss -nltp | grep port 

Requires:

component

usage:

To check for listeners for component number 2
./port_check 2

EOF
=======

# Checks whether or not a port listener is setup for a given 
# openstack component using ss -nltp | grep port 
#
# Requires:
#
# component - can be specified in a range
#
# usage:
#
# To check for listeners for component number 2 use -s(tart)
# bash port_check -s 2
#
# To check for listeners for components from 2 to 7 -s(tart) and -e(nd)
# bash port_check -s 2 -e 7
#
#
#
# Verbose options:
# -v ---> shows which component name is found on what node(s) 
#         and the port associated with it
#
# -vv ---> shows which component name is found on what node(s) 
#          and the port associated as well as the output of the 
# 	 ss -ntlp | grep port command



# get component dictionary variable in order 
# to be able to replace component numbers with
# component names
source dictionary.sh

OPTIND=1
verbosity=0

while getopts "vs:e:" OPTION
do

    case $OPTION in 
	v)
	    verbosity=$(($verbosity+1))
	    ;;
	s)
	    start=$OPTARG
	    ;;

	e)
	    end=$OPTARG
	    ;;
	esac
done

# shift argument so that verbose options don't conflict with arguments 
# for script 
shift $((OPTIND-1))

#start=$1
#end=$2


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

	
	if [ $verbosity -gt 1 ]
	then
	    echo -e '\n'
	    echo '##############################################################################'
	    echo 'Checking port ' $port ' in component ' ${component_dictionary[$1]}
	    echo '##############################################################################'
	fi

	for node in $nodes;
	do
	    output=$(ssh root@$node "ss -nltp | grep $port")
	    if [[ "$output" =~ ^LISTEN ]]
	    then
		if [ $verbosity == 0 ]
		then
		    echo "${green}${component_dictionary[$1]} listener found on $node ${reset}"		    
		elif [ $verbosity == 1 ]
		then
		    echo "${green}${component_dictionary[$1]} listener port $port found on $node ${reset}"
		else
		    echo "${green}${component_dictionary[$1]} listener on port $port found on $node ${reset}: "$output		    
		fi
	    else
	        echo "${red}${component_dictionary[$1]} listener NOT found on $node ${reset}"	    
		
	    fi
	done

    done
}    

if ! [ -z "$end"  ] && ! [ -z "$start" ]
then
    for i in $(seq $start $end); 
    do
	check_port $i
	
    done
elif ! [ -z "$start" ]
then
    # to handle the case when a single 
    # digit is specified in the range
    check_port $start

else 
    echo "--Arguments for start and end missing"
    
fi
