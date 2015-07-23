#! /bin/bash


reps=1
#cpuReps=1000000
#ramReps=1000000
cpuReps=10000
ramReps=10000

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


echo "Starting CPU test"

for i in {1..$repetitions};
do 
    newCpuTime=0
    cpuTime=0

    newCpuTime=$({ time for i in {1..$cpuReps}; do echo "hello" > /dev/null; done ;} 2>&1 |  awk '/real/ {print $2}' )
    cpuTime=$((newCpuTime+cpuTime))
    
    
done

cpuTimeAvg=(echo "$cpuTime / $reps" | bc)

echo "Done CPU Test"


##########################################################################################################################


echo "Starting Network Test"


for i in {1..$repetitions};
do 
    newNetTime=0
    netTime=0

    networkTime=$({ time curl http://129.128.208.164/sample.txt >/dev/null ; }  2>&1 |  awk '/real/ {print $2}' )
    netTime=$((newNetTime+netTime))


done

netTimeAvg=(echo "$netTime / $reps" | bc)

echo "Done Network Test"

##########################################################################################################################


echo "Starting Storage Test"

for i in {1..$repetitions};
do 
    newStorTime=0
    storTime=0

    newStorTime=$({ time dd if=/dev/urandom of=sample.txt bs=50MB count=1 ; }  2>&1 |  awk '/real/ {print $2}' )
    storTime=$((netStorTime+storTime))

done

storTimeAvg=(echo "$storTime / $reps" | bc)

echo "Done Storage Test"


##########################################################################################################################



echo "Done testing"

echo "Results"

echo -e '$ramTimeAvg \t $cpuTimeAvg \t $netTimeAvg \t $storTimeAvg'
