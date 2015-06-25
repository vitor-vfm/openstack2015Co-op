#! /bin/bash

first=$1
last=$2

dir=$(ls | egrep ^[$first-$last]- | sort -g)

for d in $dir; do
    echo -e "\nNow on $d\n"

    if [ -e $d ]; then
        cd $d;
    else
        cd ../$d;
    fi

    fab tdd
done
