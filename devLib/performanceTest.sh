#! /bin/bash


reps=1
#cpuReps=1000000
#ramReps=1000000
cpuReps=10000
ramReps=10000

TIMEFORMAT=%R

function display_progress {
    task=$1
    progress=$2
    max_progress=100
    bar="$task: "
    for (( i=0; i<=$max_progress; i++)) 
    do
    	if [ "$i" -le "$progress" ] 
    	then
    	    bar="$bar#"
    	else
    	    bar="$bar "	    
    	fi

    done
    
    bar="$bar ($progress%)\r"
    echo -ne $bar

    if [ "$progress" -ge "$max_progress" ]
    then
    	echo -ne "\n"
    fi
}
echo "Starting Tests"


##########################################################################################################################


function ramTest {

    ramTime=0
    for ((i=0; i<$reps;i++))
    do 
	newRamTime=0 
	var=0
	newRamTime=$( { time for ((j=0; j<=$ramReps;j++)); do var=$((var+j));  done; } 2>&1)
	ramTime=$(echo "$ramTime+$newRamTime" | bc -l | sed -r 's/0+$//g')    
    done
    
    ramTimeAvg=$(echo "$ramTime / $reps" | bc -l | sed -r 's/0+$//g')

    
}

##########################################################################################################################


function cpuTest {
    cpuTime=0
    for ((i=0; i<$reps;i++))
    do 
	newCpuTime=0

	newCpuTime=$({ time for ((j=0; j<=$cpuReps;j++)); do echo "hello" > /dev/null; done; } 2>&1)
	cpuTime=$(echo "$newCpuTime+$cpuTime" | bc -l | sed -r 's/0+$//g')    
	
	
    done

    cpuTimeAvg=$(echo "$cpuTime / $reps" | bc -l | sed -r 's/0+$//g')
}

##########################################################################################################################

function bandwidthTest {


    netTime=0

    for ((i=0; i<$reps;i++))
    do 
	newNetTime=0

	newNetTime=$({ time curl -s http://129.128.208.164/sample.txt >/dev/null ; } 2>&1)
	netTime=$(echo "$newNetTime+$netTime" | bc -l | sed -r 's/0+$//g')    


    done

    netTimeAvg=$(echo "$netTime / $reps" | bc -l | sed -r 's/0+$//g')

}

##########################################################################################################################

function hardDriveTest {


    storTime=0
    for ((i=0; i<$reps;i++))
    do 
	newStorTime=0

	newStorTime=$({ time dd if=/dev/urandom of=sample.txt bs=50MB count=1 2> /dev/null; } 2>&1 )
	storTime=$(echo "$newStorTime+$storTime" | bc -l | sed -r 's/0+$//g')    

    done

    storTimeAvg=$(echo "$storTime / $reps" | bc -l | sed -r 's/0+$//g')

    # clean up after hard drive test
    rm -f sample.txt


}

##########################################################################################################################


# run all tests

echo

display_progress "Testing Ram" 0

ramTest

display_progress "Testing CPU" 20

cpuTest

display_progress "Testing Bandwidth" 40

bandwidthTest

display_progress "Testing Hard Drive" 70

hardDriveTest

display_progress "Done testing" 100


echo "Result (Average taken from performing the the tests $reps time(s))"


echo "Results"

echo -e '$ramTimeAvg \t $cpuTimeAvg \t $netTimeAvg \t $storTimeAvg'
