declare -A component_dictionary

# it is crucial that this script not be moved much
# and that the parent directory be the directory
# that contains all deployment folders
# with their numbers and names

cd ..
for dir_name in $(ls | egrep ^[0-9] | sort -g)
do 
    number_portion=${dir_name%-*}
    name_portion=${dir_name#*-}
    component_dictionary[$number_portion]=$name_portion
    
done
