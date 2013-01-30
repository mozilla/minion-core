# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from setuptools import setup

install_requires = [
    'requests==1.0.4',
    'cyclone==1.0'
]

setup(name="minion.plugin_service",
      version="0.1",
      description="Minion Plugin Service",
      url="https://github.com/ygjb/minion",
      author="Mozilla",
      author_email="minion@mozilla.com",
      packages=['minion', 'minion.plugins'],
      namespace_packages=['minion','minion.plugins'],
      include_package_data=True,
      install_requires = install_requires,
      test_suite = 'minion.plugin_service.tests',
      scripts=['scripts/minion-plugin-service',
               'scripts/minion-plugin-runner',
               'scripts/minion-plugin-client'])
