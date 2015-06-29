declare -A component_dictionary

for dir_name in $(ls | egrep ^[0-9] | sort -g)
do 
    number_portion=${dir_name%-*}
    name_portion=${dir_name#*-}
    component_dictionary[$number_portion]=$name_portion
    
done
