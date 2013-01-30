# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import json
import os
import re
import sys
import urlparse

import cyclone.web
from twisted.internet.defer import inlineCallbacks

from minion.task_engine.engine import TaskEngine, SCAN_DATABASE_CLASSES


TASK_ENGINE_SYSTEM_SETTINGS_PATH = "/etc/minion/task-engine.conf"
TASK_ENGINE_USER_SETTINGS_PATH = "~/.minion/task-engine.conf"


class PlansHandler(cyclone.web.RequestHandler):

    @inlineCallbacks
    def get(self):
        task_engine = self.application.task_engine
        plan_descriptions = yield task_engine.get_plan_descriptions()
        self.finish({'success': True, 'plans': plan_descriptions})


class PlanHandler(cyclone.web.RequestHandler):

    @inlineCallbacks
    def get(self, plan_name):
        task_engine = self.application.task_engine
        plan = yield task_engine.get_plan(plan_name)
        if plan is None:
            self.finish({'success': False, 'error': 'no-such-plan'})
        else:
            self.finish({'success': True, 'plan': plan})


class CreateScanHandler(cyclone.web.RequestHandler):    

    # This is pretty strict configuration validation where we just accept
    # configs of the form: { "target": "http://some.site.com" } .. the url
    # is not allowed to have embedded authentication, a query or a fragment
    # to avoid abuse of the service.

    ALLOWED_CONFIGURATION_FIELDS = ('target',)
    
    def _validate_target(self, url):
        """Only accept URLs that are basic. No query, fragment or embedded auth allowed"""
        if not isinstance(url, str) and not isinstance(url, unicode):
            return False
        p = urlparse.urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False
        if p.query or p.fragment or p.username or p.password:
            return False
        return True
        
    def _validate_configuration(self, body):
        try:
            cfg = json.loads(body)
            if not isinstance(cfg, dict):
                return False,None
            for key in cfg.keys():
                if key not in self.ALLOWED_CONFIGURATION_FIELDS:
                    return False,None
            if 'target' not in cfg or not self._validate_target(cfg['target']):
                return False,None
            return True, cfg
        except Exception as e:
            return False, None

    @inlineCallbacks
    def put(self, plan_name):

        task_engine = self.application.task_engine
        
        plan = yield task_engine.get_plan(plan_name)
        if plan is None:
            self.finish({'success': False, 'error': 'no-such-plan'})
            return

        valid, configuration = self._validate_configuration(self.request.body)
        if not valid:
            self.finish({'success': False, 'error': 'invalid-configuration'})
            return

        session = yield task_engine.create_session(plan, configuration)
        self.finish({ 'success': True, 'scan': session.summary() })


class ChangeScanStateHandler(cyclone.web.RequestHandler):
    
    @inlineCallbacks
    def post(self, scan_id):

        task_engine = self.application.task_engine

        state = self.request.body
        if state not in ('START', 'STOP'):
            self.finish({'success': False, 'error': 'unknown-state'})
            return

        session = yield task_engine.get_session(scan_id)
        if session is None:
            self.finish({'success': False, 'error': 'no-such-scan'})
            return
        
        if state == 'START':
            success = yield session.start()
            if not success:
                self.finish({'success': False, 'error': 'invalid-state-transition'})
                return
        elif state == 'STOP':
            success = yield session.stop()
            if not success:
                self.finish({'success': False, 'error': 'invalid-state-transition'})
                return

        self.finish({'success': True})
        
class ScanHandler(cyclone.web.RequestHandler):

    @inlineCallbacks
    def get(self, scan_id):

        task_engine = self.application.task_engine

        # Try to load this from the database. If it is not there then the scan
        # might be still in progress in which case the task engine has it.

        scan = yield self.application.scan_database.load(scan_id)
        if scan is not None:
            self.finish({ 'success': True, 'scan': scan })
            return

        session = yield task_engine.get_session(scan_id)
        if session is None:
            self.finish({'success': False, 'error': 'no-such-scan'})
            return

        self.finish({ 'success': True, 'scan': session.summary() })

    @inlineCallbacks
    def delete(self, scan_id):

        task_engine = self.application.task_engine

        # If this scan is still in progress then we need to stop it
        # first and then delete it.

        session = yield task_engine.get_session(scan_id)
        if session is not None:
            success = yield session.stop(delete=True)
            self.finish({'success': True})
            return        

        # The easy case is when the scan is finished and in the
        # database. We simply delete it and we are done.

        scan = yield self.application.scan_database.load(scan_id)
        if scan is not None:
            yield self.application.scan_database.delete(scan_id)
            self.finish({ 'success': True, 'scan': scan })
            return

        self.finish({'success': False, 'error': 'no-such-scan'})

class ScanResultsHandler(cyclone.web.RequestHandler):

    def _validate_token(self, token):
        try:
            decoded = base64.b64decode(token)
            if decoded is None or not re.match(r"^\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d\.\d\d\d\d\d\dZ+$", decoded):
                return False
            return True
        except Exception as e:
            return False

    def _parse_token(self, token):
        return base64.b64decode(token)
    
    def _all_sessions_done(self, sessions):
        for session in sessions:
            if session['state'] in ('CREATED', 'STARTED'):
                return False
        return True

    def _generate_token(self, since, sessions):
        if len(sessions) == 0:
            return base64.b64encode("1975-09-23Z00:00:00.000000Z")
        if not self._all_sessions_done(sessions):
            max_time = since
            for session in sessions:
                issues = []
                for i in session['issues']:
                    if i['Date'] > max_time:
                        max_time = i['Date']
            return base64.b64encode(str(max_time))

    @inlineCallbacks
    def get(self, scan_id):

        task_engine = self.application.task_engine

        session = yield task_engine.get_session(scan_id)
        if session is None:
            self.finish({'success': False, 'error': 'no-such-scan'})
            return

        since = "1975-09-23T00:00:00.000000Z"
        token = self.get_argument('token', None)
        if token:
            if not self._validate_token(token):
                self.finish({ 'success': False, 'error': 'malformed-token' })
                return
            since = self._parse_token(token)
            
        scan_results = session.results(since=since)
        token = self._generate_token(since, scan_results['sessions'])
        self.finish({ 'success': True, 'scan': scan_results, 'token': token })

class ScanArtifactsHandler(cyclone.web.RequestHandler):

    @inlineCallbacks
    def get(self, scan_id, session_id):

        # Try to load this from the database. If it is not there then the scan
        # might be still in progress in which case the task engine has it.

        scan = yield self.application.scan_database.load(scan_id)
        if scan is None:
            session = yield task_engine.get_session(scan_id)
            if session is not None:
                scan = session.summary()

        if scan is None:
            raise cyclone.web.HTTPError(404)
        
        artifacts_path = os.path.expanduser(self.settings['task_engine']['artifacts_path']) + "/" + session_id + ".zip"
        print "LOOKING AT", artifacts_path
        if not os.path.exists(artifacts_path):
            raise cyclone.web.HTTPError(404)            

        with open(artifacts_path) as f:
            data = f.read()
            self.set_header("Content-Type", "application/zip")
            self.set_header("Content-Length", str(len(data)))
            self.finish(data)        
        

class TaskEngineApplication(cyclone.web.Application):

    def __init__(self):

        # Configure our settings. We have basic default settings that just work for development
        # and then override those with what is defined in either ~/.minion/ or /etc/minion/

        task_engine_settings = dict(plugin_service_api="http://127.0.0.1:8181",
                                    scan_database_type="memory",
                                    scan_database_location=None,
                                    artifacts_path="/tmp")

        for settings_path in (TASK_ENGINE_USER_SETTINGS_PATH, TASK_ENGINE_SYSTEM_SETTINGS_PATH):
            settings_path = os.path.expanduser(settings_path)
            if os.path.exists(settings_path):
                with open(settings_path) as file:
                    try:
                        task_engine_settings = json.load(file)
                        break
                    except Exception as e:
                        logging.error("Failed to parse configuration file %s: %s" % (settings_path, str(e)))
                        sys.exit(1)

        # Setup the database

        scan_database_type = task_engine_settings['scan_database_type']
        scan_database_class = SCAN_DATABASE_CLASSES.get(scan_database_type)
        if scan_database_class is None:
            logging.error("Unable to configure scan_database_type '%s'. No such type." % scan_database_type)
            sys.exit(1)

        try:
            self.scan_database = scan_database_class(task_engine_settings['scan_database_location'])
        except Exception as e:
            logging.error("Failed to setup the scan database: %s" % str(e))
            sys.exit(1)
        
        # Create the Task Engine

        self.task_engine = TaskEngine(self.scan_database, task_engine_settings['plugin_service_api'],
                                      task_engine_settings['artifacts_path'])

        # Setup our routes and initialize the Cyclone application

        handlers = [
            (r"/plans", PlansHandler),
            (r"/plan/([a-z0-9_-]+)", PlanHandler),
            (r"/scan/create/([a-z0-9_-]+)", CreateScanHandler),
            (r"/scan/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/state", ChangeScanStateHandler),
            (r"/scan/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/results", ScanResultsHandler),
            (r"/scan/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/artifacts/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", ScanArtifactsHandler),
            (r"/scan/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", ScanHandler),
        ]

        settings = dict(
            debug=True,
            task_engine=task_engine_settings,
        )

        cyclone.web.Application.__init__(self, handlers, **settings)


Application = lambda: TaskEngineApplication()
