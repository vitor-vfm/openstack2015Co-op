#! /bin/bash





OPTIND=1
verbosity=0
dead=0
source dictionary.sh


while getopts "vs:e:a:dh" OPTION
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
	a)
	    action=$OPTARG
	    ;;
	d)
	    dead=$(($dead+1))
	    ;;
	h)
	    cat <<EOF

Performs specified action on the services for the openstack component specified by the user

USAGE:

REQUIRES:

(Mandatory)
-a = Action = the action to be performed on the services. (status|restart|disable|enable|stop|...) and anyother action that systemctl supports

Range - is specified using the start and end variables

(Mandatory)
-s = start = the number corresponding to the openstack component you wish to start with

(Optional)
-e = end = the number corresponding to the openstack component you wish to end with

(Optional)
-d = dead = show only services that are dead (inactive)

SYNTAX:

- to get the status for all services specified in components 1 through 3, the syntax is as follows:

./service.sh -s 1 -e 3 -a status

- to restart all services for components 5, the syntax is:

./service.sh -s 5 -a restart

- to get all services for component number 8 that are dead:

bash service.sh -s 8 -a status -d

EOF
	    exit
	    ;;
	esac
done

# shift argument so that verbose options don't conflict with arguments 
# for script 
shift $((OPTIND-1))


#action=$1
#start=$2
#end=$3

servicesComp=""
servicesCont=""
servicesNetw=""
servicesStor=""


function action_on_services {
    component=$1
    action=$2

    case "$1" in 
	0)
	    servicesComp="chronyd"
	    servicesCont="chronyd mariadb"
	    servicesNetw="chronyd"
	    servicesStor="chronyd"
	    ;;
	1)
#	    servicesComp="network chronyd "  
	    servicesCont="network chronyd "
#	    servicesNetw="network chronyd "
#	    servicesStor="network chronyd "
	    ;;
	2)
	    servicesComp=""
	    servicesCont="rabbitmq-server"
	    servicesNetw=""
	    servicesStor=""
	    ;;
	3)
	    servicesComp=""
	    servicesCont="openstack-keystone"
	    servicesNetw=""
	    servicesStor=""
	    ;;
	4)
	    servicesComp=""
	    servicesCont="openstack-glance-api"
	    servicesNetw=""
	    servicesStor=""
	    ;;
	5)
	    servicesComp="libvirtd openstack-nova-compute"
	    servicesCont="openstack-nova-api openstack-nova-cert openstack-nova-consoleauth openstack-nova-scheduler openstack-nova-conductor openstack-nova-novncproxy"
	    servicesNetw=""
	    servicesStor=""
	    ;;
	6)
	    servicesComp="openvswitch neutron-openvswitch-agent openstack-nova-compute"
	    servicesCont="openstack-nova-api openstack-nova-scheduler openstack-nova-conductor neutron-server"
	    servicesNetw="openvswitch neutron-openvswitch-agent neutron-l3-agent neutron-dhcp-agent neutron-metadata-agent neutron-ovs-cleanup"
	    servicesStor=""
	    ;;
	7)
	    servicesComp=""
	    servicesCont="httpd memcached"
	    servicesNetw=""
	    servicesStor=""
	    ;;
	8)
	    servicesComp=""
	    servicesCont="openstack-cinder-api openstack-cinder-scheduler.servic"
	    servicesNetw=""
	    servicesStor="openstack-cinder-volume target"
	    ;;
	9)
	    servicesComp=""
	    servicesCont="openstack-swift-proxy memcached"
	    servicesNetw=""
	    servicesStor="rsyncd openstack-swift-account openstack-swift-account-auditor openstack-swift-account-reaper openstack-swift-account-replicator systemctl start openstack-swift-container openstack-swift-container-auditor openstack-swift-container-replicator openstack-swift-container-updater openstack-swift-object openstack-swift-object-auditor openstack-swift-object-replicator openstack-swift-object-updater"
	    ;;
	10)
	    servicesComp=""
	    servicesCont="openstack-heat-api openstack-heat-api-cfn openstack-heat-engine"
	    servicesNetw=""
	    servicesStor=""
	    ;;
	11)
	    servicesComp="openstack-ceilometer-compute openstack-nova-compute"
	    servicesCont="openstack-ceilometer-api openstack-ceilometer-notification openstack-ceilometer-central openstack-ceilometer-collector openstack-ceilometer-alarm-evaluator openstack-ceilometer-alarm-notifier mongod"
	    servicesNetw=""
	    servicesStor=""
	    ;;
    esac


    function run_command {
	node=$3
	red=`tput setaf 1`
	green=`tput setaf 2`
	reset=`tput sgr0`

	for service in $1;
	do 
	    output=$(ssh root@$node "systemctl $2 $service")

	    if [ $verbosity -ge 1 ]
	    then
		echo "###############################################################################"

		echo -e "\n"
		echo "###############################################################################"
		echo "${green}running $action on $service ${reset}"
		echo "###############################################################################"

	    fi
	    
	    if  [ $verbosity == 2 ]
	    then

		echo "$output" # quoted to keep spacing and prettiness 

		echo "###############################################################################"

	    fi
	    
	    
	    state=$(ssh root@$node "systemctl status $service | awk '/Active:/ {\$1=\"\"; print \$0}' | xargs") 
	    # piped to xargs in order to get rid of spaces on either side
	    if [ "$dead" == 0 ]
	    then

		if [[ "$state" =~ ^active  ]] || [[ "$state" =~ running  ]] || [[ "$state" =~ exited ]]
		then
		    echo "As of $(date '+%H:%M:%S'), $service status on $node is: ${green} $state ${reset}"
		    
		elif [[ "$state" =~ ^inactive  ]] || [[ "$state" =~ dead  ]] || [[ "$state" =~ failed ]]
		then
		    echo "As of $(date '+%H:%M:%S'), $service status on $node is: ${red} $state ${reset}"

		else
		    echo "As of $(date '+%H:%M:%S'), $service status on $node is: $state (Unknown)"
		    
		fi
	    else
		if [[ "$state" =~ ^inactive  ]] || [[ "$state" =~ dead  ]] || [[ "$state" =~ failed ]]
		then
		    echo "As of $(date '+%H:%M:%S'), $service status on $node is: ${red} $state ${reset}"
		fi
		
	    fi

	done
	

    }


    if ! [ -z "$servicesCont" ] 
    then
	
	if [ $verbosity -ge 1 ]
	then
	    echo -e "\n"
	    echo "running $action on services for ${component_dictionary[$component]} that run on the Controller"
	fi

	run_command "$servicesCont" $action "controller"
	
    fi

    if ! [ -z "$servicesComp" ] 
    then
	if [ $verbosity -ge 1 ]
	then
	    echo -e "\n"
	    echo "running $action on services for ${component_dictionary[$component]} that run on the Compute"
	fi

	run_command "$servicesComp" $action "compute1"
    fi

    if ! [ -z "$servicesNetw" ] 
    then
	if [ $verbosity -ge 1 ]
	then
	    echo -e "\n"
	    echo "running $action on services for ${component_dictionary[$component]} that run on the Network"
	fi
	run_command "$servicesNetw" $action "network"

    fi

    if ! [ -z "$servicesStor" ] 
    then
	if [ $verbosity -ge 1 ]
	then
	    echo -e "\n"
	    echo "running $action on services for ${component_dictionary[$component]} that run on the Storage"
	fi
	run_command "$servicesStor" $action "storage1"

    fi
}
if [ -z "$start"  ]
then
    echo "--Argument for start missing"

elif [ -z "$action" ] 
then 
    echo "--Argument for action missing"

elif ! [ -z "$end"  ]
then
    for i in $(seq $start $end); 
    do
	action_on_services $i $action
	
    done
else
    # to handle the case when a single 
    # digit is specified in the range
    action_on_services $start $action

fi







# ref:

# colors:
# http://stackoverflow.com/questions/5947742/how-to-change-the-output-color-of-echo-in-linux
