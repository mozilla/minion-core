#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/

import datetime
import json
import logging
import optparse
import os
import time
import uuid
import zipfile

import zope.interface
from twisted.internet import protocol
from twisted.internet import reactor
from twisted.internet.error import ProcessDone, ProcessTerminated

from minion.plugin_api import AbstractPlugin

class PluginRunnerProcessProtocol(protocol.ProcessProtocol):

    def __init__(self, plugin_session):
        self.plugin_session = plugin_session

    def connectionMade(self):
        logging.debug("PluginRunnerProcessProtocol.connectionMade")
        pass

    # TODO We should redirect plugin output to separate log files like date-session.{stdout,stderr}

    def outReceived(self, data):
        logging.debug("PluginRunnerProcessProtocol.outReceived: " + data)

    def errReceived(self, data):
        logging.debug("PluginRunnerProcessProtocol.errReceived: " + data)

    def processEnded(self, reason):
        #logging.debug("PluginRunnerProcessProtocol.processEnded %s" % str(reason))
        self.plugin_session.duration = int(time.time()) - self.plugin_session.started
        if isinstance(reason.value, ProcessDone):
            # TODO This should happen async to not block. Probably better in the success callback of spawnProcess() ?
            if self.plugin_session.artifacts:
                try:
                    logging.debug("Opening zip file %s" % self.plugin_session.artifacts_path())
                    os.chdir(self.plugin_session.work_directory) # This is cheating a little but it makes path handling easier
                    with zipfile.ZipFile(self.plugin_session.artifacts_path(), "w") as zip:
                        for name,paths in self.plugin_session.artifacts.items():
                            for path in paths:
                                if os.path.isfile(path):
                                    logging.debug("Zipping %s to %s" % (path, path))
                                    zip.write(path, path, zipfile.ZIP_DEFLATED)
                                elif os.path.isdir(path):
                                    for base, dirs, files in os.walk(path):
                                        for file in files:
                                            fn = os.path.join(base, file)
                                            logging.debug("Zipping %s to %s" % (fn, fn))
                                            zip.write(fn, fn, zipfile.ZIP_DEFLATED)
                except Exception as e:
                    logging.exception("Failed to create artifacts zip file: " + str(e))
            # TODO Is this the right thing to do now that we set the state from /session/id/report/finish ?
            self.plugin_session.state = 'FINISHED'
        elif isinstance(reason.value, ProcessTerminated):
            # TODO Is this the right thing to do now that we set the state from /session/id/report/finish ?
            self.plugin_session.state = 'FAILED'

class PluginSession:

    """
    This class represents one running plugin or its session. It handles the plugin state,
    collecting from the plugin, etc.
    """

    def __init__(self, plugin_name, plugin_class, configuration, work_directory_root, debug = False):
        self.plugin_name = plugin_name
        self.plugin_class = plugin_class
        self.configuration = configuration
        self.work_directory_root = work_directory_root
        self.debug = debug
        
        self.id = str(uuid.uuid4())
        self.state = 'CREATED'
        self.started = int(time.time())
        self.duration = None
        self.results = []
        self.errors = []
        self.progress = None
        self.artifacts = {}
        self.work_directory = os.path.join(self.work_directory_root, self.id)
        
    def start(self):
        logging.debug("PluginSession %s %s start()" % (self.id, self.plugin_name))
        if not os.path.exists(self.work_directory):
            os.mkdir(self.work_directory)
        protocol = PluginRunnerProcessProtocol(self)
        arguments = ["minion-plugin-runner"]
        if self.debug:
            arguments += ["--debug"]
        arguments += ["--plugin", self.plugin_name]
        arguments += ["--work-root", self.work_directory_root]
        arguments += ["--session-id", self.id]
        arguments += ["--mode", "plugin-service"]
        arguments += ["--plugin-service-api", "http://127.0.0.1:8181"]
        environment = { 'PATH': os.getenv('PATH') }
        self.process = reactor.spawnProcess(protocol, "minion-plugin-runner", arguments, environment, path=self.work_directory)
        self.state = 'STARTED'

    #
    # This is called by the user of the plugin-service by setting the state of
    # a session to STOPPED. If we are only CREATED then we move immediately to
    # STOPPED. If we are STARTED then we send a USR1 signal to the plugin-runner
    # and let it stop.
    #
    # TODO This could be improved by starting a timer to forcibly kill
    #      the plugin-runner if it does not stop in time.
    #

    def stop(self):
        if self.state == 'CREATED':
            self.state = 'STOPPED'
        elif self.state == 'STARTED':
            self.process.signalProcess(30) # USR1
            self.state = 'STOPPING'

    #
    # This is called by the plugin-runner through the /session/ID/report/results api. It
    # simply collects the reported issues.
    #
    # TODO I just realized that the ID generation should actually
    #      happen in the plugin-runner and not here. Otherwise it
    #      is not possible to submit updated issues later on.
    #

    def add_results(self, results):
        # Add a timestamp to the results. This is not super accurate but that is ok, it is
        # just to get them incrementally later from the task engine api.
        for result in results:
            date = datetime.datetime.utcnow()
            result['Date'] = date.isoformat() + 'Z'
        for result in results:
            result['Id'] = str(uuid.uuid4())
        self.results += results

    #
    # This is called by the plugin-runner through the /session/ID/finish api. It
    # is used to tell the plugin-service that a session has finished with a
    # specific status. After this is received, the session is done and even if
    # the plugin makes calls, we reject them. TODO That last bit is not yet
    # implemented.
    #

    def finish(self, result):
        state = result['state']
        if state in ('FINISHED', 'STOPPED', 'FAILED'):
            self.state = state            

    #
    # Add artifacts to this session. The format is an array that
    # looks like this:
    #
    #  [
    #    { name: "Reports", paths: ["report1.txt", "report2.txt"] },
    #    { name: "Unspecified", paths: ["output.log", "errors.log"] }
    #  ]
    #
    # The files should be relative to the plugin work directory and
    # are all at the root of the artifacts zip file.
    #

    def add_artifacts(self, artifacts):
        for artifact in artifacts:
            self.artifacts.setdefault(artifact["name"], set()).update(artifact["paths"])

    def flatten_artifacts(self):
        artifacts = {}
        for name,paths in self.artifacts.items():
            artifacts[name] = sorted(list(paths))
        return artifacts

    def artifacts_path(self):
        return os.path.join(self.work_directory_root, self.id + ".zip")

    def summary(self):
        return { 'id': self.id,
                 'state': self.state,
                 'configuration': self.configuration,
                 'plugin': { 'name': self.plugin_class.name(),
                             'version': self.plugin_class.version(),
                             'class': self.plugin_class.__module__ + "." + self.plugin_class.__name__ },
                 'progress': self.progress,
                 'started': self.started,
                 'issues': [],
                 'artifacts' : self.flatten_artifacts(),
                 'duration': self.duration if self.duration else int(time.time()) - self.started }


# TODO Move to Plugin class
def _plugin_descriptor(plugin):
    return {'class': plugin.__module__ + "." + plugin.__name__,
            'name': plugin.name(),
            'version': plugin.version()}

class PluginService:
    
    def __init__(self, work_directory_root):
        self.work_directory_root = work_directory_root
        self.sessions = {}
        self.plugins = {}

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def create_session(self, plugin_name, configuration, debug):
        plugin_class = self.plugins.get(plugin_name)
        if plugin_class:
            session = PluginSession(plugin_name, plugin_class, configuration, self.work_directory_root, debug)
            self.sessions[session.id] = session
            return session

    def delete_session(self, session):
        if session.id in self.sessions:
            del self.sessions[session.id]

    def register_plugin(self, plugin_class):
        self.plugins[str(plugin_class)] = plugin_class

    def get_plugin_descriptor(self, plugin_name):
        if plugin_name in self.plugins:
            return _plugin_descriptor(self.plugins[plugin_name])

    def plugin_descriptors(self):
        return map(_plugin_descriptor, self.plugins.values())

