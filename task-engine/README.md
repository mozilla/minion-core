Minion Task Engine
==================

This is a back-end component of Minion that is responsible for running many plugins as part of a test plan.

Also see the following two projects:

 * Minion Plugin Service at https://github.com/st3fan/minion-plugin-service
 * Minion NMAP Plugin at https://github.com/st3fan/minion-nmap-plugin
 * Minion Garmr Plugin at https://github.com/st3fan/minion-garmr-plugin

> Note that this is work in progress. The API and responses are likely to change a bit.

Setting up a development environment
-----------------------------------

Development is best done in a Python Virtualenv. These instructions
assume you have Python 2.7.x and virtualenv installed.

If you are unfamiliar with virtualenv then please read
http://www.virtualenv.org/en/latest/#what-it-does first.

### Set up a virtualenv

    $ cd ~ # (or any directory where you do your development)
    $ virtualenv env
    $ source env/bin/activate

### Check out the project, install it's dependencies and set it up for development

    (env) $ git clone --recursive https://github.com/st3fan/minion-task-engine.git
    (env) $ (cd minion-task-engine/dependencies/klein; python setup.py install)
    (env) $ (cd minion-task-engine; python setup.py develop)

Be sure to use the `--recursive` option as we will also need to clone the git submodules in `dependencies/`.

### Run the Minion Task Engine

Note that you also need to have the Plugin Service running. The Task Engine currently expects the Plugin service to be running on it's default port (8181) on localhost.

    (env) $ minion-task-engine --debug
    12-10-31 13:06:51 I Starting task-engine on 127.0.0.1:8282
    2012-10-31 13:06:51+0000 [-] Log opened.
    2012-10-31 13:06:51+0000 [-] Site starting on 8282
    2012-10-31 13:06:51+0000 [-] Starting factory <twisted.web.server.Site instance at 0x245bdd0>

At this point you have a plugin service running. You can edit the code
and simply Control-C the server and start it again to see your changes
in effect.

Run a scan with the Task Engine
-------------------------------

There are currently two plans defined in the Task Engine. They are called `tickle` and `scratch`. The first does a very minimal scan and the second a more complete one with Garmr and NMAP.

(The plans are currently defined in the minion-task-engine script but will move to some external place.)

To execute a plan, start by sourcing in the virtualenv:

    $ cd ~ # (or any directory where you do your development)
    $ source env/bin/activate

Assuming the task-engine is running in a separate window, you can now execute the client:

    (env) $ minion-task-client http://127.0.0.1:8282 tickle '{"target":"http://www.soze.com"}'
    
This will print out the raw JSON responses of all the calls made to the Task Engine and finally the results of the scan.

Talking to the REST API
=======================

You can ask the plans that are available

    $ curl -XGET http://127.0.0.1:8282/plans
    {
        "plans": [
            {
                "description": "Run basic tests and do a very basic port scan using NMAP.", 
                "name": "tickle"
            }, 
            {
                "description": "Run Garmr and do a full port scan using NMAP.", 
                "name": "scratch"
            }
        ], 
        "success": true
    }
    
You can see detailed information about a specific plan:

    $ curl -XGET http://127.0.0.1:8282/plans/tickle
    {
        "plan": {
            "description": "Run basic tests and do a very basic port scan using NMAP.", 
            "name": "tickle", 
            "workflow": [
                {
                    "configuration": {
                    }, 
                    "plugin_name": "minion.plugins.basic.HSTSPlugin"
                }, 
                {
                    "configuration": {
                    }, 
                    "plugin_name": "minion.plugins.basic.XFrameOptionsPlugin"
                }, 
                {
                    "configuration": {
                        "ports": "U:53,111,137,T:21-25,139,8080,8443", 
                    }, 
                    "plugin_name": "minion.plugins.nmap.NMAPPlugin"
                }
            ]
        }, 
        "success": true
    }

You can start a scan against a specific host by PUTting a configuration:

    $ curl -XPUT -d '{"target":"http://moo.mx"}' http://127.0.0.1:8282/scan/create/tickle
    {
        "scan": {
            "configuration": {
                "target": "http://moo.mx"
            }, 
            "id": "3c0883e2-c22f-47a8-932a-958a7846c2ad", 
            "plan_name": "tickle", 
            "sessions": [], 
            "state": "CREATED"
        }, 
        "success": true
    }

You start the scan by POSTing `START` to it's status:

    $ curl -XPOST -d START http://127.0.0.1:8282/scan/3c0883e2-c22f-47a8-932a-958a7846c2ad/state
    {
        "success": true
    }

You can find the status of the scan by GETting it:

    $ curl -XGET http://127.0.0.1:8282/scan/3c0883e2-c22f-47a8-932a-958a7846c2ad
    {
        "scan": {
            "configuration": {
                "target": "http://moo.mx"
            }, 
            "id": "3c0883e2-c22f-47a8-932a-958a7846c2ad", 
            "plan_name": "tickle", 
            "sessions": [
                {
                    "configuration": {
                        "target": "http://moo.mx"
                    }, 
                    "duration": 3, 
                    "id": "8e10cc65-3a7c-4466-b859-c5c56de6a0a2", 
                    "plugin_name": "minion.plugins.basic.HSTSPlugin", 
                    "started": 1351782043, 
                    "state": "FINISHED"
                }, 
                {
                    "configuration": {
                        "target": "http://moo.mx"
                    }, 
                    "duration": 3, 
                    "id": "46db06c7-10f6-4f85-b715-c84eb503cb18", 
                    "plugin_name": "minion.plugins.basic.XFrameOptionsPlugin", 
                    "started": 1351782043, 
                    "state": "FINISHED"
                }, 
                {
                    "configuration": {
                        "ports": "U:53,111,137,T:21-25,139,8080,8443", 
                        "target": "http://moo.mx"
                    }, 
                    "duration": 4, 
                    "id": "4344a898-9f30-43d5-aa9f-8761c94c8d49", 
                    "plugin_name": "minion.plugins.nmap.NMAPPlugin", 
                    "started": 1351782043, 
                    "state": "FINISHED"
                }
            ], 
            "state": "FINISHED"
        }, 
        "success": true
    }

As you can see all the individual plugins are all `FINISHED` and the scan itself has therefore also set to `FINISHED`

You can grab the results by GETing them. You don't have to wait until the scan is completely FINISHED. Plugins can add incremental updates to their results and they will appear as they go.

    $ curl -XGET http://127.0.0.1:8282/scan/3c0883e2-c22f-47a8-932a-958a7846c2ad/results
    {
        "results": [
            {
                "issues": [
                    {
                        "severity": "high", 
                        "summary": "Site does not set HSTS header"
                    }
                ], 
                "session": {
                    "configuration": {
                        "target": "http://moo.mx"
                    }, 
                    "duration": 3, 
                    "id": "8e10cc65-3a7c-4466-b859-c5c56de6a0a2", 
                    "plugin_name": "minion.plugins.basic.HSTSPlugin", 
                    "started": 1351782043, 
                    "state": "FINISHED"
                }
            }, 
            {
                "issues": [
                    {
                        "severity": "high", 
                        "summary": "Site has no X-Frame-Options header set"
                    }
                ], 
                "session": {
                    "configuration": {
                        "target": "http://moo.mx"
                    }, 
                    "duration": 3, 
                    "id": "46db06c7-10f6-4f85-b715-c84eb503cb18", 
                    "plugin_name": "minion.plugins.basic.XFrameOptionsPlugin", 
                    "started": 1351782043, 
                    "state": "FINISHED"
                }
            }, 
            {
                "issues": [
                    {
                        "severity": "high", 
                        "summary": "Port 22 is open"
                    }, 
                    {
                        "severity": "high", 
                        "summary": "Port 25 is open"
                    }
                ], 
                "session": {
                    "configuration": {
                        "ports": "U:53,111,137,T:21-25,139,8080,8443", 
                        "target": "http://moo.mx"
                    }, 
                    "duration": 4, 
                    "id": "4344a898-9f30-43d5-aa9f-8761c94c8d49", 
                    "plugin_name": "minion.plugins.nmap.NMAPPlugin", 
                    "started": 1351782043, 
                    "state": "FINISHED"
                }
            }
        ], 
        "success": true
    }
