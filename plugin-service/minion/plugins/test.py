# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time

from minion.plugin_api import BlockingPlugin

class DelayedPlugin(BlockingPlugin):
    def do_run(self):
        for n in range(0,10):
            if self.stopped:
                return
            time.sleep(1)
        message = self.configuration.get('message', 'Hello, world')
        self.report_issues([{ "Summary":message, "Severity":"Info" }])

class FailingPlugin(BlockingPlugin):
    def do_run(self):
        raise Exception("Failing plugins gonna fail")
