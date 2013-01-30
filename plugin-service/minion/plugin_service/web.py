# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import logging
import os
import time
import uuid

import cyclone.web
from twisted.internet.defer import inlineCallbacks
from twisted.python import log

from minion.plugin_service.service import PluginService


PLUGIN_SERVICE_SYSTEM_SETTINGS_PATH = "/etc/minion/plugin-service.conf"
PLUGIN_SERVICE_USER_SETTINGS_PATH = "~/.minion/plugin-service.conf"


class PluginsHandler(cyclone.web.RequestHandler):
    def get(self):
        plugin_service = self.application.plugin_service
        self.finish({'success': True, 'plugins': plugin_service.plugin_descriptors()})

class PluginHandler(cyclone.web.RequestHandler):
    def get(self, plugin_name):
        plugin_service = self.application.plugin_service
        plugin = plugin_service.get_plugin_descriptor(plugin_name)
        if not plugin:
            self.finish({'success': False, 'error': 'no-such-plugin'})
            return
        self.finish({'success':True,'plugin':plugin})

class CreatePluginSessionHandler(cyclone.web.RequestHandler):
    def put(self, plugin_name):
        plugin_service = self.application.plugin_service
        plugin = plugin_service.get_plugin_descriptor(plugin_name)
        if not plugin:
            self.finish({'success': False, 'error': 'no-such-plugin'})
            return
        configuration = json.loads(self.request.body)
        session = plugin_service.create_session(plugin_name, configuration, self.settings.debug)
        if session:
            self.finish({'success': True, 'session': session.summary()})

class PutPluginSessionStateHandler(cyclone.web.RequestHandler):
    def put(self, session_id):
        state = self.request.body
        logging.debug("Putting state %s" % state)
        if state not in ('START', 'STOP'):
            self.finish({'success': False, 'error': 'unknown-state'})
            return
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        if state == 'START':
            if session.state != 'CREATED':
                self.finish({'success': False, 'error': 'unknown-state-transition'})
                return
            session.start()
        elif state == 'STOP':
            if session.state not in ('STARTED', 'CREATED'):
                self.finish({'success': False, 'error': 'unknown-state-transition'})
                return
            session.stop()
        self.finish({'success': True})

class PluginSessionHandler(cyclone.web.RequestHandler):
    def get(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        self.finish({'success': True, 'session': session.summary()})
    def delete(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        if session.state not in ('CREATED', 'STOPPED', 'FINISHED', 'FAILED'):
            self.finish({'success': False, 'error': 'invalid-state'})
            return
        plugin_service.delete_session(session)
        self.finish({'success': True})

class GetPluginSessionResultsHandler(cyclone.web.RequestHandler):
    def get(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        self.finish({'success': True, 'session': session.summary(), 'issues': session.results})

class GetPluginSessionArtifactsHandler(cyclone.web.RequestHandler):
    def get(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        # TODO This blocks the server. What is the right way to serve files?
        artifacts_path = session.artifacts_path()
        if not os.path.exists(artifacts_path):
            raise cyclone.web.HTTPError(404)
        with open(artifacts_path) as f:
            data = f.read()
            self.set_header("Content-Type", "application/zip")
            filename = session_id + ".zip"
            self.set_header("Content-Disposition", "inline; filename=\"%s\"" % filename)
            self.finish(data)

#

class PluginRunnerGetConfigurationHandler(cyclone.web.RequestHandler):

    def get(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        self.finish(session.configuration)

class PluginRunnerReportProgressHandler(cyclone.web.RequestHandler):

    def post(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        progress = json.loads(self.request.body)
        logging.debug("Received progress from plugin session %s: " + str(progress))
        session.progress = progress
        self.finish({'success':True})

class PluginRunnerReportIssuesHandler(cyclone.web.RequestHandler):

    def post(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        results = json.loads(self.request.body)
        logging.debug("Received results from plugin session %s: %s" % (session,str(results)))
        session.add_results(results)
        self.finish({'success':True})

class PluginRunnerReportArtifactsHandler(cyclone.web.RequestHandler):

    def post(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        artifacts = json.loads(self.request.body)
        logging.debug("Received artifacts from plugin session %s: %s" % (session,str(artifacts)))
        session.add_artifacts(artifacts)
        self.finish({'success':True})

# TODO Is this actually used?
class PluginRunnerReportErrorsHandler(cyclone.web.RequestHandler):

    def post(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        body = self.request.body
        logging.debug("Received errors from plugin session %s: %s" % (session,body))
        self.finish({'success':True})

class PluginRunnerReportFinishHandler(cyclone.web.RequestHandler):

    def post(self, session_id):
        plugin_service = self.application.plugin_service
        session = plugin_service.get_session(session_id)
        if not session:
            self.finish({'success': False, 'error': 'no-such-session'})
            return
        result = json.loads(self.request.body)
        session.finish(result)
        logging.debug("Received finish from plugin session %s: %s" % (session,str(result)))
        self.finish({'success':True})
        

class PluginServiceApplication(cyclone.web.Application):

    def __init__(self):

        # I don't think this should be in here? Where does it go?
        
        observer = log.PythonLoggingObserver()
        observer.start()

        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname).1s %(message)s', datefmt='%y-%m-%d %H:%M:%S')

        # Configure our settings. We have basic default settings that just work for development
        # and then override those with what is defined in either ~/.minion/ or /etc/minion/

        plugin_service_settings = {"work_directory_root": "/tmp"}

        for settings_path in (PLUGIN_SERVICE_USER_SETTINGS_PATH, PLUGIN_SERVICE_SYSTEM_SETTINGS_PATH):
            settings_path = os.path.expanduser(settings_path)
            if os.path.exists(settings_path):
                with open(settings_path) as file:
                    try:
                        plugin_service_settings = json.load(file)
                        break
                    except Exception as e:
                        logging.error("Failed to parse configuration file %s: %s" % (settings_path, str(e)))
                        sys.exit(1)
        
        # Create the Plugin Service and register plugins

        self.plugin_service = PluginService(plugin_service_settings['work_directory_root'])

        from minion.plugins.basic import ExceptionPlugin
        from minion.plugins.basic import FailedPlugin
        from minion.plugins.basic import HSTSPlugin
        from minion.plugins.basic import IncrementalAsyncPlugin
        from minion.plugins.basic import IncrementalBlockingPlugin
        from minion.plugins.basic import IssueGeneratingPlugin
        from minion.plugins.basic import LongRunningPlugin
        from minion.plugins.basic import XFrameOptionsPlugin
        from minion.plugins.basic import ReportGeneratingPlugin
        from minion.plugins.basic import SimpleExternalPlugin

        self.plugin_service.register_plugin(ExceptionPlugin)
        self.plugin_service.register_plugin(FailedPlugin)
        self.plugin_service.register_plugin(HSTSPlugin)
        self.plugin_service.register_plugin(IncrementalAsyncPlugin)
        self.plugin_service.register_plugin(IncrementalBlockingPlugin)
        self.plugin_service.register_plugin(IssueGeneratingPlugin)
        self.plugin_service.register_plugin(LongRunningPlugin)
        self.plugin_service.register_plugin(XFrameOptionsPlugin)
        self.plugin_service.register_plugin(ReportGeneratingPlugin)
        self.plugin_service.register_plugin(SimpleExternalPlugin)

        try:
            from minion.plugins.nmap import NMAPPlugin
            self.plugin_service.register_plugin(NMAPPlugin)
        except ImportError as e:
            pass

        try:
            from minion.plugins.garmr import GarmrPlugin
            self.plugin_service.register_plugin(GarmrPlugin)
        except ImportError as e:
            pass

        try:
            from minion.plugins.zap_plugin import ZAPPlugin
            self.plugin_service.register_plugin(ZAPPlugin)
        except ImportError as e:
            pass        

        try:
            from minion.plugins.skipfish import SkipfishPlugin
            self.plugin_service.register_plugin(SkipfishPlugin)
        except ImportError as e:
            pass

        for plugin in self.plugin_service.plugin_descriptors():
            logging.info("Registered plugin {} v{}".format(plugin['class'], plugin['version']))

        # Setup our routes and initialize the Cyclone application

        handlers = [
            # Public API
            (r"/plugins", PluginsHandler),
            (r"/plugin/(.+)", PluginHandler),
            (r"/session/create/(.+)", CreatePluginSessionHandler),
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/state", PutPluginSessionStateHandler),
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", PluginSessionHandler),
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/results", GetPluginSessionResultsHandler),
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/artifacts", GetPluginSessionArtifactsHandler),
            # Plugin Runner API
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/configuration", PluginRunnerGetConfigurationHandler),
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/report/progress", PluginRunnerReportProgressHandler),
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/report/issues", PluginRunnerReportIssuesHandler),
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/report/artifacts", PluginRunnerReportArtifactsHandler),
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/report/errors", PluginRunnerReportErrorsHandler),
            (r"/session/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/report/finish", PluginRunnerReportFinishHandler),
        ]

        settings = dict(
            debug=True,
            plugin_service=plugin_service_settings,
        )

        cyclone.web.Application.__init__(self, handlers, **settings)


Application = lambda: PluginServiceApplication()
