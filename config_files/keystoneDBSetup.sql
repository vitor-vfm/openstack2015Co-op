/*
default password is NEW_PASS

You can change via the bash and using the sed command.
I have given a quick example below:


# echo 'buncha of random blah asdasd blahasdasb asdasblah asdasd' | sed -e 's:blah:YEAH:g'
buncha of random YEAH asdasd YEAHasdasb asdasYEAH asdasd

so for the file it will be:

# cat script.sql | sed -e 's:NEW_PASS:NEW_PASS:g'
...file contents will be displayed...

The above command is tested and it works

In order to get it into a file, you need to ' > ' to a different file
For example:

# cat script.sql | sed -e 's:NEW_PASS:NEW_PASS:g' > script2.sql

And then script2.sql will contain the script with the updated password.

The above commands are tested and they work


*/
CREATE DATABASE IF NOT EXISTS keystone;
GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'localhost' IDENTIFIED BY 'NEW_PASS';
GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'%' IDENTIFIED BY 'NEW_PASS';
