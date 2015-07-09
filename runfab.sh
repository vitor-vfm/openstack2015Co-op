#! /bin/bash

USAGE="""
./runfab [-options] f l\n
\n
   where\n
     f : first script, by number\n
     l : last script, by number\n
\n
   options:\n
     -h : show usage\n
     -t [task] : specify a fabric task to run. Default is 'deploy tdd'\n
     -R [role1,role2,etc] : specify which roles to run the task on. 
                            The list of roles is comma-separated\n
                            This doesn't override the @roles decorator\n
     -w : warn only. Script won't abort if there is an error in a task\n
     -f [path] : choose a file to log results in; default is 'deploy_log'\n
"""

green=`tput setaf 2`
reset=`tput sgr0`

# DEFAULTS
TASK='deploy tdd'
WARN_ONLY=false
LOGFILE='deploy_log'
ROLES=false

while getopts :t:wf:R:h flag; do
    case $flag in
        t) # set task 
            TASK=$OPTARG
            ;;
        w) # set warn only
            WARN_ONLY=true
            ;;
        f) # set log file
            LOGFILE=$OPTARG
            ;;
        R) # set roles
            ROLES=$OPTARG
            ;;
        h) # show usage
            echo -e $USAGE
            exit
            ;;
        \?) # unknown option
            echo -e "Unknown option\n\n"
            echo -e $USAGE
            exit
            ;;
    esac
done

shift $((OPTIND-1))

case "$#" in
    1)  FIRST=$1
        DIRECTORIES=$(ls | egrep ^$FIRST-)
        ;;
    2)  FIRST=$1 
        LAST=$2
        DIRECTORIES=$(ls | egrep ^[0-9] | sort -g | awk "/^$FIRST-/,/^$LAST-/")
        ;;
    *) echo "Invalid number of parameters"
        echo -e $USAGE
        exit
        ;;
esac

# log results
touch $LOGFILE

# Process options
COMMAND="fab"

if [ $ROLES != false ]; then
    COMMAND="$COMMAND -R $ROLES";
fi

if [ $WARN_ONLY = true ]; then
    COMMAND="$COMMAND -w";
fi


# Run the command in each directory
for d in $DIRECTORIES; do
    echo -e "\n${green} Now on $d ${reset}\n"

    if [ -e $d ]; then
        cd $d;
    else
        cd ../$d;
    fi


    $COMMAND $TASK | tee -a ../$LOGFILE
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        echo -e "NON-ZERO EXIT CODE ON FAB; RUNFAB ABORTING\n"
        exit
    fi

done
