#! /bin/bash

first=$1
last=$2

dir=$(ls | egrep ^[$first-$last]- | sort -g)

for d in $dir; do
    if [ -e $d ]; then
        cd $d;
    else
        cd ../$d;
    fi
    fab deploy tdd
done
