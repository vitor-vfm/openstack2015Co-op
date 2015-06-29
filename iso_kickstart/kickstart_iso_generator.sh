#!/bin/bash


# Usage:
#
# Requires:
#
# 1) Directory Tree:
#
# Before Execution of Script (Note placements and directory names, as they are crucial):
#
# .
# |-- Build-Assets
# |   |-- CentOS-7.0-x86_64-storage1_ks.iso
# |   `-- CentOS-7-x86_64-DVD-1503-01.iso ----> original iso file from which new one will be derived
# |-- iso
# |-- kickstart_iso_generator_backup.sh
# |-- kickstart_iso_generator.sh
# `-- storage1_ks.cfg ---> kickstart file to be integrated 
#
#
#
# 2) Parameters
# kickstart_file = the kickstart_file that will be integrated into the new iso 
#
# iso_file = the name of the iso file from which the new iso will be derived
#
# new_iso_file_name = name of new iso file. Script combines kickstart_file name with iso_file name to generate new_iso_file_name 
#
#
# Syntax:
#
# # sudo bash kickstart_iso.generator.sh
#

kickstart_file="storage1_ks.cfg"

iso_file="CentOS-7-x86_64-DVD-1503-01.iso"

new_iso_file_name="CentOS-7.0-x86_64-${kickstart_file%.*}.iso"





if [ -f Build-Assets/$iso_file ];
then
    echo "File exists, no need to download"
else
    echo "File does not exist, downloading..."
    if [ ! -d "Build-Assets" ];
    then
        echo "Creating Build-Assets directory"
        mkdir "Build-Assets"
    fi
    curl -Lo Build-Assets/CentOS-7.0-1406-x86_64-Minimal.iso http://mirror.csclub.uwaterloo.ca/centos/7.0.1406/isos/x86_64/CentOS-7.0-1406-x86_64-Minimal.iso
    #curl -OL http://mirror.rackcentral.com.au/centos/6.5/isos/x86_64/CentOS-6.5-x86_64-netinstall.iso
fi
#/* far a mac */hdiutil mount Build-Assets/CentOS-7.0-1406-x86_64-Minimal.iso

mkdir /mnt/myIso
mount -t iso9660 Build-Assets/$iso_file /mnt/myIso
mkdir Build-Assets/tmp/
chmod 777 Build-Assets/tmp/
### step 1 #### mod ks

cp -a $kickstart_file Build-Assets/tmp/ks.cfg

cp -a /mnt/myIso/ Build-Assets/tmp/
chmod 777 Build-Assets/tmp/isolinux/
chmod 777 Build-Assets/tmp/isolinux/isolinux.cfg
chmod 777 Build-Assets/tmp/isolinux/isolinux.bin

#cp -a isolinux.cfg Build-Assets/tmp/isolinux/

umount /mnt/myIso
rm /mnt/myIso
cd Build-Assets/tmp/
###step 2 ####### rename output file after "-o"
mkisofs -o ../$new_iso_file_name -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -R -J -v -T .
cd -
exit
