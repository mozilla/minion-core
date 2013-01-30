Minion Plugin Service
=====================

This is the back-end component of Minion that runs security
plugins. Plugins are scanners or analyzers that look at a target and
return issues. The Plugin Service can run many scans at the same
time. It provides a small REST API that other components can call to
start and stop plugins and to collect found issues.

Also see the following two projects:

 * Minion NMAP Plugin at https://github.com/st3fan/minion-nmap-plugin
 * Minion Garmr Plugin at https://github.com/st3fan/minion-garmr-plugin

> Note that this is work in progress. The API and responses are likely to change a bit.

Setting up a development environment
------------------------------------

Development is best done in a Python Virtualenv. These instructions
assume you have Python 2.7.x and virtualenv installed.

If you are unfamiliar with virtualenv then please read
http://www.virtualenv.org/en/latest/#what-it-does first.

### Set up a virtualenv

    $ cd ~ # (or any directory where you do your development)
    $ virtualenv env
    $ source env/bin/activate

### Check out the project, install it's dependencies and set it up for development

    (env) $ git clone --recursive https://github.com/st3fan/minion-plugin-service.git
    (env) $ (cd minion-plugin-service/dependencies/klein; python setup.py install)
    (env) $ (cd minion-plugin-service; python setup.py develop)

Be sure to use the `--recursive` option as we will also need to clone the git submodules in `dependencies/`.

### Run the Minion Plugin Service

    (env) $ minion-plugin-service --debug
    12-10-28 12:31:11 I Starting plugin-service on 127.0.0.1:8181
    12-10-28 12:31:11 I Registered plugin minion.plugins.basic.AbortedPlugin
    12-10-28 12:31:11 I Registered plugin minion.plugins.basic.DummyPlugin
    12-10-28 12:31:11 I Registered plugin minion.plugins.basic.ExceptionPlugin
    12-10-28 12:31:11 I Registered plugin minion.plugins.basic.FailedPlugin
    12-10-28 12:31:11 I Registered plugin minion.plugins.basic.HSTSPlugin
    12-10-28 12:31:11 I Registered plugin minion.plugins.basic.LongRunningPlugin
    12-10-28 12:31:11 I Registered plugin minion.plugins.basic.XFrameOptionsPlugin
    12-10-28 12:31:11 I Registered plugin minion.plugins.garmr.GarmrPlugin
    12-10-28 12:31:11 I Registered plugin minion.plugins.nmap.NMAPPlugin
    2012-10-28 12:31:11-0400 [-] Log opened.
    2012-10-28 12:31:11-0400 [-] Site starting on 8181
    2012-10-28 12:31:11-0400 [-] Starting factory <twisted.web.server.Site instance at 0x108ea3170>

At this point you have a plugin service running. You can edit the code
and simply Control-C the server and start it again to see your changes
in effect.

Making calls to the Plugin Service
----------------------------------

All these examples assume that you are running the Plugin Service
locally and that you have `curl` installed.

### Get a list of available plugins

To find out what plugins the plugin service instance supports, request
the `/plugins` resource:

```
$ curl http://127.0.0.1:8181/plugins
{
    "plugins": [
        {
            "class": "minion.plugins.garmr.GarmrPlugin", 
            "name": "Garmr", 
            "version": "0.1"
        }, 
        {
            "class": "minion.plugins.zap_plugin.ZAPPlugin", 
            "name": "ZAP", 
            "version": "0.1"
        }, 
        {
            "class": "minion.plugins.nmap.NMAPPlugin", 
            "name": "NMAP", 
            "version": "0.1"
        }, 
    ], 
    "success": true
}
```

Note that not all plugins listed above may be installed. If you do not
see the Garmr and NMAP plugins then you can grab them from Github and
follow their instructions to get them installed. See the top of this
README for their links.

Some plugins like the `AbortedPlugin` and `FailedPlugin` are really
only there for testing and will likely go away when this project makes
an official release.

### Create a session

To run a specific plugin you first need to create a session. A session
is a context for a plugin and can be referenced by its unique id.

A session needs a configuration, which is a JSON structure that at
least describes what to run the plugin against (the target) but may
also list additional settings for the plugin.

Create a file called `configuration.json` and put the following in it:

    { "target": "http://some.site" }

Replace `www.yoursite.com` with the name of a web site that you want
to test against.

> *Please do not run security tools against sites that you do not own.*

Now we `PUT` the configuration to the API to create a new session for
the built-in XFrameOptionsPlugin, which checks the presence of the
X-Frame-Options header.

```
$ curl -XPUT -d @configuration.json http://127.0.0.1:8181/session/create/minion.plugins.basic.XFrameOptionsPlugin
{
    "session": {
        "configuration": {
            "target": "http://some.site"
        }, 
        "duration": 0, 
        "files": [], 
        "id": "b4ca7f40-18b9-4cf8-8445-cd815150a9b6", 
        "issues": [], 
        "plugin": {
            "class": "minion.plugins.basic.XFrameOptionsPlugin", 
            "name": "XFrameOptionsPlugin", 
            "version": "0.0"
        }, 
        "progress": null, 
        "started": 1353090532, 
        "state": "CREATED"
    }, 
    "success": true
}
```

All calls to the Plugin Service return JSON dictionaries. The
`success` field is always present to indicate whether the call was
succesful.

### Start the session

To start the session we need to change it's state to `STARTED`. We do
this with a `PUT` request:

```
$ curl -XPUT -d 'START' http://127.0.0.1:8181/session/b4ca7f40-18b9-4cf8-8445-cd815150a9b6/state
{
    "success": true
}
```

The result of this will be that the Plugin Service spawns a new
process, a plugin-runner, in which the specific plugin will
execute. The plugin is now in it's `STARTED` state.

The X-Frame-Options plugin will start and finish really quickly but if
you look at the process list while more complicated plugins are
running, you could see a hierarchy similar to this:

    O-+= 67248 minion-plugin-service
      \-+- 81897 minion-plugin-runner -p minion.plugins.nmap.NMAPPlugin
        \--- 81898 nmap --open www.mysite.com
      \-+- 81899 minion-plugin-runner -p minion.plugins.garmr.GarmrPlugin
        \--- 81901 garmr -o /dev/stdout -u http://www.mysite.com
      \-+- 81903 minion-plugin-runner -p minion.plugins.basic.HSTSPlugin
      \-+- 81904 minion-plugin-runner -p minion.plugins.basic.XFrameOptionsPlugin

The `minion-plugin-service` is the controlling process that spawns
`minion-plugin-runner` processes. Those runners either spawn an
external tool, like nmap or garmr, or, if they are implemented in
Python, they execute in the runner process.

### Poll the session to find out it's status

When a plugin is running you can `GET` it's info to see the status and
find out if and how it finished:

```
$ curl http://127.0.0.1:8181/session/b4ca7f40-18b9-4cf8-8445-cd815150a9b6
{
    "session": {
        "configuration": {
            "target": "http://some.site"
        }, 
        "duration": 41, 
        "files": [], 
        "id": "b4ca7f40-18b9-4cf8-8445-cd815150a9b6", 
        "plugin": {
            "class": "minion.plugins.basic.XFrameOptionsPlugin", 
            "name": "XFrameOptionsPlugin", 
            "version": "0.0"
        }, 
        "progress": null, 
        "started": 1353090532, 
        "state": "FINISHED"
    }, 
    "success": true
}
```

When the plugin has finished correctly without operational errors,
it's state will be `FINISHED`. If it failed because of errors it will
be set to `FAILED` or `ABORTED`.

Note that there may still be reported issues when the plugin has
finished with an error state.

### Fetch the results

To collect all results, `GET` the /results resource of the session:

```
$ curl http://127.0.0.1:8181/session/b4ca7f40-18b9-4cf8-8445-cd815150a9b6/results
{
    "success": true,
    "session": {
        "configuration": {
            "target": "http://some.site"
        }, 
        "duration": 41, 
        "files": [], 
        "id": "b4ca7f40-18b9-4cf8-8445-cd815150a9b6", 
        "plugin": {
            "class": "minion.plugins.basic.XFrameOptionsPlugin", 
            "name": "XFrameOptionsPlugin", 
            "version": "0.0"
        }, 
        "progress": null, 
        "started": 1353090532, 
        "state": "FINISHED"
    }, 
    "issues": [
        {
            "Severity": "High", 
            "Summary": "Site has no X-Frame-Options header set"
        }
    ] 
}
```

### Terminating a session

TODO

### Deleting a session

TODO

