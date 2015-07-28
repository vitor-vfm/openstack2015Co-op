#! /bin/bash

if [ -z "$1" ]
then
    resultsMessage=""
else
    resultsMessage=$1
fi

cpuReps=50000
ramReps=50000



TIMEFORMAT=%R
decimals=3
reps=3
#yum install -y bc

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


##########################################################################################################################


function ramTest {

    ramTime=0
    for ((i=0; i<$reps;i++))
    do 
	newRamTime=0 
	var=0
	newRamTime=$( { time for ((j=0; j<=$ramReps;j++)); do var=$((var+j));  done; } 2>&1)
	ramTime=$(echo "scale=$decimals;$ramTime+$newRamTime" | bc -l | sed -r 's/0+$//g')    
    done
    ramTimeAvg=$(echo "scale=$decimals;$ramTime / $reps" | bc -l | sed -r 's/0+$//g')

    
}

##########################################################################################################################


function cpuTest {
    cpuTime=0
    for ((i=0; i<$reps;i++))
    do 
	newCpuTime=0

	newCpuTime=$({ time for ((j=0; j<=$cpuReps;j++)); do echo $((13**99)) > /dev/null; done; } 2>&1)
	cpuTime=$(echo "scale=$decimals;$newCpuTime+$cpuTime" | bc -l | sed -r 's/0+$//g')    
	
	
    done

    cpuTimeAvg=$(echo "scale=$decimals;$cpuTime / $reps" | bc -l | sed -r 's/0+$//g')
}

##########################################################################################################################

function bandwidthTest {


    netTime=0

    for ((i=0; i<$reps;i++))
    do 
	newNetTime=0

	newNetTime=$({ time curl -s http://129.128.208.164/sample.txt >/dev/null ; } 2>&1)
	netTime=$(echo "scale=$decimals;$newNetTime+$netTime" | bc -l | sed -r 's/0+$//g')    


    done

    netTimeAvg=$(echo "scale=$decimals;$netTime / $reps" | bc -l | sed -r 's/0+$//g')

}

##########################################################################################################################

function hardDriveTest {


    storTime=0
    storSpeed=0
    rate=""
    for ((i=0; i<$reps;i++))
    do 
	newStorTime=0
	newStorSpeed=0

	newStorTime=$({ time dd if=/dev/urandom of=/var/lib/cinder/mnt/672f9ab3b59295047f954bf6b29c138b/testFile.txt bs=25MB count=1 2> ddResults.txt; } 2>&1 )
	newStorSpeed=$(cat ddResults.txt | awk '{print $8}')
	rate=$(cat ddResults.txt | awk '{print $9}' | xargs)
	storSpeed=$(echo "scale=$decimals;$newStorSpeed+$storSpeed" | bc -l | sed -r 's/0+$//g')
	storTime=$(echo "scale=$decimals;$newStorTime+$storTime" | bc -l | sed -r 's/0+$//g')

    done

    storTimeAvg=$(echo "scale=$decimals;$storTime / $reps" | bc -l | sed -r 's/0+$//g')
    storSpeedAvg=$(echo "scale=$decimals;$storSpeed / $reps" | bc -l | sed -r 's/0+$//g')
    # clean up after hard drive test
    rm -f /mnt/gluster/testFile.txt


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

resultsRecord=resultsRecord

#block size for each of the results and their respective titles
block_size=30

date | tee -a $resultsRecord
echo "Host: $(hostname)" | tee -a $resultsRecord
echo | tee -a $resultsRecord

echo "Result (Average taken from performing the the tests $reps time(s))" | tee -a $resultsRecord

printf "%${block_size}s" "RAM Test (sec)" | tee -a $resultsRecord && printf "%${block_size}s" "CPU Test (sec)" | tee -a $resultsRecord && printf "%${block_size}s" 'Bandwidth Test (sec)' | tee -a $resultsRecord && printf "%${block_size}s" 'Hard Drive Test (sec)' | tee -a $resultsRecord
echo | tee -a $resultsRecord
printf "%${block_size}s" "($ramReps reps)" | tee -a $resultsRecord && printf "%${block_size}s" "($cpuReps reps)" | tee -a $resultsRecord && printf "%${block_size}s" ' ' | tee -a $resultsRecord && printf "%${block_size}s" ' ' | tee -a $resultsRecord
echo | tee -a $resultsRecord
printf "%${block_size}s" "$ramTimeAvg" | tee -a $resultsRecord && printf "%${block_size}s" "$cpuTimeAvg"  | tee -a $resultsRecord && printf "%${block_size}s" "$netTimeAvg"  | tee -a $resultsRecord && printf "%${block_size}s" "$storTimeAvg, $storSpeedAvg $rate" | tee -a $resultsRecord
echo -e "\n"| tee -a $resultsRecord


if [ -z "$resultsMessage" ]
then
    echo "Include a message:" 
    read resultsMessage
fi

echo $resultsMessage >> $resultsRecord
echo "################################################################################################################################"  >> $resultsRecord 

fileToSaveResults=/tmp/performanceTestResults
echo -e "$(date) \t $(hostname) \t $reps \t $ramTimeAvg \t $cpuTimeAvg \t $netTimeAvg \t $storTimeAvg \t $storSpeedAvg $rate \t $resultsMessage" > $fileToSaveResults 

echo "Writing to Google Docs"
./writeToGoogleDoc.sh $fileToSaveResults
echo "Done writing"

# date \t hostname \t reps \t ramTimeAvg \t cpuTimeAvg \t netTimeAvg \t storTimeAvg \t storSpeedAvg \t Message 
