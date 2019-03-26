#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Library for working with internet connections"""

# Part of the PsychoPy library
# Copyright (C) 2018 Jonathan Peirce
# Distributed under the terms of the GNU General Public License (GPL).

from __future__ import absolute_import, print_function

# from future import standard_library
# standard_library.install_aliases()

from builtins import object
import sys
import socket
import re
from psychopy import logging, constants
from psychopy import prefs

import requests

# default 20s from prefs, min 2s
TIMEOUT = max(prefs.connections['timeout'], 2.0)
socket.setdefaulttimeout(TIMEOUT)

# global proxies
proxies = None  # if this is populated then it has been set up already
headers = {
    'user-agent': constants.PSYCHOPY_USERAGENT
}
session = requests.session()


class NoInternetAccessError(Exception):
    """An internet connection is required but not available
    """
# global haveInternet
haveInternet = None  # gets set True or False when you check


def setSessionProxy(proxiesDict):
    """

    Parameters
    ----------
    proxiesDict : dictionary of proxies (e.g. {'https':'https://proxyplace.com'})

    """
    global session
    session.proxies = proxiesDict


def haveInternetAccess(forceCheck=False):
    """Detect active internet connection or fail quickly.

    If forceCheck is False, will rely on a cached value if possible.
    """
    global haveInternet
    if forceCheck or haveInternet is None:
        # try to connect to a high-availability site
        sites = ["https://www.google.com/", "https://www.google.co.uk/"]
        for wait in [0.3, 0.7]:  # try to be quick first
            for site in sites:
                try:
                    r = requests.get(site, timeout=wait)
                    if r.status_code == 200:
                        haveInternet = True  # cache
                        return True  # one success is good enough
                except (requests.ConnectionError, requests.ConnectTimeout):
                    #  socket.timeout() can also happen
                    pass
        else:
            haveInternet = False
    return haveInternet


def requireInternetAccess(forceCheck=False):
    """Checks for access to the internet, raise error if no access.
    """
    if not haveInternetAccess(forceCheck=forceCheck):
        msg = 'Internet access required but not detected.'
        logging.error(msg)
        raise NoInternetAccessError(msg)
    return True


def tryProxy(handler, URL=None):
    """
    Test whether we can connect to a URL with the current proxy settings.

    `handler` can be typically `web.proxies`, if `web.setupProxy()` has been
    run.

    :Returns:

        - True (success)
        - a `requests.ConnectionError`

    """
    if URL is None:
        URL = 'http://www.google.com'  # hopefully google isn't down!
    try:
        r = requests.get(URL, proxies=handler, timeout=2)
        if r.status_code == 200:
            global haveInternet
            haveInternet = True
            return True
    except (requests.ConnectionError, requests.ConnectTimeout) as err:
        return err


def getPacFiles():
    """Return a list of possible auto proxy .pac files being used,
    based on the system registry (win32) or system preferences (OSX).
    """
    pacFiles = []
    if sys.platform == 'win32':
        try:
            import _winreg as winreg  # used from python 2.0-2.6
        except ImportError:
            import winreg  # used from python 2.7 onwards
        net = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings")
        nSubs, nVals, lastMod = winreg.QueryInfoKey(net)
        subkeys = {}
        for i in range(nVals):
            thisName, thisVal, thisType = winreg.EnumValue(net, i)
            subkeys[thisName] = thisVal
        if ('AutoConfigURL' in list(subkeys.keys()) and
                len(subkeys['AutoConfigURL']) > 0):
            pacFiles.append(subkeys['AutoConfigURL'])
    elif sys.platform == 'darwin':
        import plistlib
        sysPrefs = plistlib.readPlist('/Library/Preferences/System'
                                      'Configuration/preferences.plist')
        networks = sysPrefs['NetworkServices']
        # loop through each possible network (e.g. Ethernet, Airport...)
        for network in list(networks.items()):
            netKey, network = network  # the first part is a long identifier
            if 'ProxyAutoConfigURLString' in network['Proxies']:
                pacFiles.append(network['Proxies']['ProxyAutoConfigURLString'])
    return list(set(pacFiles))  # remove redundant ones


def getWpadFiles():
    """Return possible pac file locations from the standard set of .wpad
    locations

    NB this method only uses the DNS method to search, not DHCP queries, and
    so may not find all possible .pac locations.

    See http://en.wikipedia.org/wiki/Web_Proxy_Autodiscovery_Protocol
    """
    # pacURLs.append("http://webproxy."+domain+"/wpad.dat")
    # for me finds a file that starts: function FindProxyForURL(url,host)
    # dynamcially chooses a proxy based on the requested url and host; how to
    # parse?

    domainParts = socket.gethostname().split('.')
    pacURLs = []
    for ii in range(len(domainParts)):
        domain = '.'.join(domainParts[ii:])
        pacURLs.append("http://wpad." + domain + "/wpad.dat")
    return list(set(pacURLs))  # remove redundant ones


def proxyFromPacFiles(pacURLs=None, URL=None, log=True):
    """Attempts to locate and setup a valid proxy server from pac file URLs

    :Parameters:

        - pacURLs : list

            List of locations (URLs) to look for a pac file. This might
            come from :func:`~psychopy.web.getPacFiles` or
            :func:`~psychopy.web.getWpadFiles`.

        - URL : string

            The URL to use when testing the potential proxies within the files

    :Returns:

        - A proxy dict if successful (and this will have
          been added as an opener to the web.session)
        - False if no proxy was found in the files that allowed successful
          connection
    """

    if pacURLs == None:  # if given none try to find some
        pacURLs = getPacFiles()
    if pacURLs == []:  # if still empty search for wpad files
        pacURLs = getWpadFiles()
        # for each file search for valid urls and test them as proxies
    for thisPacURL in pacURLs:
        if log:
            msg = 'proxyFromPacFiles is searching file:\n  %s'
            logging.debug(msg % thisPacURL)
        try:
            r = requests.get(thisPacURL, timeout=2)
        except (requests.ConnectTimeout, requests.ConnectionError):
            if log:
                logging.debug("Failed to find PAC URL '%s' " % thisPacURL)
            continue
        pacStr = r.text
        # find the candidate PROXY strings (valid URLS), numeric and
        # non-numeric:
        pattern = r"PROXY\s([^\s;,:]+:[0-9]{1,5})[^0-9]"
        possProxies = re.findall(pattern, pacStr + '\n')
        for thisPoss in possProxies:
            proxUrl = 'https://' + thisPoss
            handler = {'https': proxUrl}
            if tryProxy(handler) == True:
                if log:
                    logging.debug('successfully loaded: %s' % proxUrl)
                setSessionProxy(handler)
                return handler
    return False


def setupProxy(log=True):
    """Set up the requests proxy if possible.

     The function will use the following methods in order to try and
     determine proxies:
        #. standard requests.get (which will use any
           statically-defined http-proxy settings)
        #. previous stored proxy address (in prefs)
        #. proxy.pac files if these have been added to system settings
        #. auto-detect proxy settings (WPAD technology)

     .. note:
        This can take time, as each failed attempt to set up a proxy
        involves trying to load a URL and timing out. Best
        to do in a separate thread.

    :Returns:

        True (success) or False (failure)
    """
    global proxies
    # try doing nothing
    proxies = None
    if tryProxy(proxies) is True:
        if log:
            logging.debug("Using standard requests (static proxy or "
                          "no proxy required)")
        return 1

    # try doing what we did on previous app instance (stored in prefs)
    if len(prefs.connections['proxy']) > 0:
        proxies = {'https': prefs.connections['proxy']}
        if tryProxy(proxies) is True:
            if log:
                msg = 'Using %s (from prefs)'
                logging.debug(msg % prefs.connections['proxy'])
            setSessionProxy(proxies)
            return 1
        else:
            if log:
                logging.debug("Found a previous proxy but it didn't work")

    # try finding/using a proxy.pac file
    for pacURLs in getPacFiles()+getWpadFiles():
        if log:
            logging.debug("Found proxy PAC files: %s" % pacURLs)
        proxies = proxyFromPacFiles(pacURLs)  # installs opener, if successful
        if (proxies and
                hasattr(proxies, 'proxies') and
                len(proxies.proxies['https']) > 0):
            # save that proxy for future
            prefs.connections['proxy'] = proxies.proxies['https']
            prefs.saveUserPrefs()
            if log:
                msg = 'Using %s (from proxy PAC file and auto-detect)'
                logging.debug(msg % prefs.connections['proxy'])
            return 1

    proxies = 0
    return 0
