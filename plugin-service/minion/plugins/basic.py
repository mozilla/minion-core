# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import os
import time
import sys

from twisted.internet.task import LoopingCall

import requests
from minion.plugin_api import AbstractPlugin,BlockingPlugin,ExternalProcessPlugin


class XFrameOptionsPlugin(BlockingPlugin):
    
    """
    This is a minimal plugin that does one http request to find out if
    the X-Frame-Options header has been set. It does not override anything
    except start() since that one check is quick and there is no point
    in suspending/resuming/terminating.

    All plugins run in a separate process so we can safely do a blocking
    HTTP request. The PluginRunner catches exceptions thrown by start() and
    will report that back as an error state of the plugin.
    """
    
    def do_run(self):        
        r = requests.get(self.configuration['target'])
        if r.status_code != 200:
            self.report_error([{"Info":"Received a non-200 response: %d" % r.status_code}])
        else:
            if 'x-frame-origin' in r.headers:
                if r.headers['x-frame-options'] not in ('DENY', 'SAMEORIGIN'):
                    self.report_issues([{ "Summary":"Site has X-Frame-Options header but it has an unknown or invalid value: %s" % r.headers['x-frame-options'],"Severity":"High" }])
                else:
                    self.report_issues([{ "Summary":"Site has a correct X-Frame-Options header", "Severity":"Info" }])
            else:
                self.report_issues([{"Summary":"Site has no X-Frame-Options header set", "Severity":"High"}])


class HSTSPlugin(BlockingPlugin):

    """
    This plugin checks if the site sends out an HSTS header if it is HTTPS enabled.
    """

    def do_run(self):
        r = requests.get(self.configuration['target'])
        if r.status_code != 200:
            self.report_issues([{ "Summary":"Received a non-200 response: %d" % r.status_code, "Severity":"Info" }])
        else:            
            if r.url.startswith("https://") and 'hsts' not in r.headers:
                self.report_issues([{ "Summary":"Site does not set HSTS header", "Severity":"High" }])
            else:
                self.report_issues([{ "Summary":"Site sets HSTS header", "Severity":"Info" }])

