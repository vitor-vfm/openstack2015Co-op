from __future__ import with_statement
from fabric.api import *
from fabric.decorators import with_settings
from fabric.colors import green, red
from fabric.contrib.files import append
import logging

import sys
sys.path.append('..')
import env_config
from myLib import runCheck, align_y, align_n, saveConfigFile


############################ Config ########################################

env.roledefs = env_config.roledefs
passwd = env_config.passwd

localsettings = "/etc/openstack-dashboard/local_settings"
cssFile = 'ece.css'
# staticDir = '/usr/share/openstack-dashboard/openstack_dashboard/static/'
staticDir = '/usr/share/openstack-dashboard/static/'

######################### General functions ################################

@roles('controller')
def setSettingsFile():
    "Set the local_setting.py file in the controller"

    newLines = "# Dashboard configuration\n"
    newLines += "SITE_BRANDING = 'Electrical and Computer Engineering Department'"

    out = append(localsettings, newLines)
    msg = "Set the local_setting.py file in the controller"
    if out:
        print align_n(msg)
    else:
        print align_y(msg)

@roles('controller')
def saveImagesAndCSS():
    "Save images and the CSS sheet in the controller"

    # save images
    imagesDir = staticDir + 'dashboard/img/'
    imageFiles = local('ls img',capture=True).split()
    for imageFile in imageFiles:
        put(local_path = 'img/%s' % imageFile, remote_path = imagesDir)

    # save CSS file
    cssDir = staticDir + 'dashboard/css/'
    put(local_path = cssFile, remote_path = cssDir)

@roles('controller')
def setStylesheetsFile():
    "Change the _stylesheets file to reference the new CSS sheet"

    stylesheetsFile = '/usr/share/openstack-dashboard/openstack_dashboard/' + \
    'templates/_stylesheets.html'

    newLine = "<link href='{{ STATIC_URL }}dashboard/css/%s'" % cssFile
    newLine += " media='screen' rel='stylesheet' />"

    stylesheetsContents = run('cat '+stylesheetsFile, quiet=True)
    if cssFile not in stylesheetsContents:
        msg = 'Add new line to _stylesheets referencing the custom css'
        runCheck(msg, 'echo "%s" >>%s' % (newLine, stylesheetsFile))
    else:
        print blue('New line already in _stylesheets. Nothing done')

@roles('controller')
def restartServices():

    msg = 'Restart Horizon services'
    runCheck(msg, "systemctl restart httpd.service memcached.service")

def deploy():
    execute(setSettingsFile)
    execute(saveImagesAndCSS)
    execute(setStylesheetsFile)
    execute(restartServices)

##################################### TDD ############################################


def tdd():
    msg = 'Connect to dashboard'
    output = runCheck(msg, "curl --connect-timeout 10 http://controller/dashboard | head -10")

    # check if it's the Dashboard frontpage
    if '<title>Login - OpenStack Dashboard</title>' in output:
        print align_y('Can access Dashboard frontpage')
    else:
        print align_n('Cannot access Dashboard frontpage')
        sys.exit(1)
