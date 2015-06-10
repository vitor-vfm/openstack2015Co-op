/*
default password is NEW_PASS
*/
CREATE DATABASE IF NOT EXISTS keystone;
GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'controller' IDENTIFIED BY 'NEW_PASS';
GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'%' IDENTIFIED BY 'NEW_PASS';
