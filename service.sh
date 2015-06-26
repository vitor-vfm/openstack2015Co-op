#! /bin/bash

action=$1
start=$2
end=$3

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
	    servicesComp="network chronyd "  
	    servicesCont="network chronyd "
	    servicesNetw="network chronyd "
	    servicesStor="network chronyd "
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
	    echo -e "\n\n"

	    
	    # run specified command
	    echo "###############################################################################"
	    echo "${green}running $action on $service ${reset}"
	    echo "###############################################################################"


	    ssh root@controller "systemctl $2 $service"

	    # echo out status after specified command is run

	    echo "###############################################################################"
	    
	    state=$(ssh root@controller "systemctl status $service | awk '/Active/ {print \$2,\$3}'")
	    if [[ "$state" =~ "active"  ]] || [[ "$state" =~ "running"  ]]
	    then
		echo "$service status on $node is now: ${green} $state ${reset}"
		
	    elif [[ "$state" =~ "inactive"  ]] || [[ "$state" =~ "dead"  ]]
	    then
		echo "$service status on $node is now: ${red} $state ${reset}"

	    else
		echo "$service status on $node is now: $state (neither active nor inactive)"
		
	    fi

	    echo "###############################################################################"

	done
	

    }


    if ! [ -z "$servicesCont" ] 
    then
	echo -e "\n\n"
	echo "running $action on services for $component that run on the Controller"
	echo "###############################################################################"
	#    ssh root@controller "systemctl $action $servicesCont"

	run_command "$servicesCont" $action "controller"
	
    fi

    if ! [ -z "$servicesComp" ] 
    then
	echo -e "\n\n"
	echo "running $action on services for $component that run on the Compute"
	echo "###############################################################################"
	#    ssh root@compute1 "systemctl $action $servicesComp"

	run_command "$servicesComp" $action "compute"
    fi

    if ! [ -z "$servicesNetw" ] 
    then
	echo -e "\n\n"
	echo "running $action on services for $component that run on the Network"
	echo "###############################################################################"
	#    ssh root@network "systemctl $action $servicesNetw"
	run_command "$servicesNetw" $action "network"

    fi

    if ! [ -z "$servicesStor" ] 
    then
	echo -e "\n\n"
	echo "running $action on services for $component that run on the Storage"
	echo "###############################################################################"
	#    ssh root@storage1 "systemctl $action $servicesStor"
	run_command "$servicesStor" $action "storage"

    fi





}


for i in $(seq $start $end); 
do
    action_on_services $i $action
    
done



