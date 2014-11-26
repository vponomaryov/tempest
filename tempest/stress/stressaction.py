# (c) Copyright 2013 Hewlett-Packard Development Company, L.P.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import abc
import signal
import sys

import six

from random import randint
from tempest.openstack.common import log as logging
from tempest import clients_share as share_clients

from tempest import config_share as config

CONF = config.CONF


@six.add_metaclass(abc.ABCMeta)
class StressAction(object):

    def __init__(self, manager, max_runs=None, stop_on_error=False):
        full_cname = self.__module__ + "." + self.__class__.__name__
        self.logger = logging.getLogger(full_cname)
        self.manager = manager
        self.max_runs = max_runs
        self.stop_on_error = stop_on_error

    def _shutdown_handler(self, signal, frame):
        try:
            self.tearDown()
        except Exception:
            self.logger.exception("Error while tearDown")
        sys.exit(0)

    @property
    def action(self):
        """This methods returns the action. Overload this if you
        create a stress test wrapper.
        """
        return self.__class__.__name__

    def setUp(self, **kwargs):
        """This method is called before the run method
        to help the test initialize any structures.
        kwargs contains arguments passed in from the
        configuration json file.

        setUp doesn't count against the time duration.
        """
        self.logger.debug("setUp")

    def tearDown(self):
        """This method is called to do any cleanup
        after the test is complete.
        """
        self.logger.debug("tearDown")

    def execute(self, shared_statistic):
        """This is the main execution entry point called
        by the driver.   We register a signal handler to
        allow us to tearDown gracefully, and then exit.
        We also keep track of how many runs we do.
        """
        signal.signal(signal.SIGHUP, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

        while self.max_runs is None or (shared_statistic['runs'] <
                                        self.max_runs):
            self.logger.debug("Trigger new run (run %d)" %
                              shared_statistic['runs'])
            try:
                self.run()
            except Exception:
                shared_statistic['fails'] += 1
                self.logger.exception("Failure in run")
            finally:
                shared_statistic['runs'] += 1
                if self.stop_on_error and (shared_statistic['fails'] > 1):
                    self.logger.warn("Stop process due to"
                                     "\"stop-on-error\" argument")
                    self.tearDown()
                    sys.exit(1)

    @abc.abstractmethod
    def run(self):
        """This method is where the stress test code runs."""
        return


class ShareStressAction(StressAction):
    def __init__(self, manager, max_runs=None, stop_on_error=False):
        super(ShareStressAction, self).__init__(manager, max_runs=None,
                                                stop_on_error=False)
        self.max_runs = CONF.share_stress.count_recreations
        share_os = share_clients.AdminManager(interface="json")
        self.shares_client = share_os.shares_client

        min_size = int(CONF.share_stress.sizes_range[0])
        max_size = int(CONF.share_stress.sizes_range[1])
        self.share_size = randint(min_size, max_size)
        self.protocol = CONF.share.enable_protocols[0]

    def setUp(self, **kwargs):
        self.volume_type_id = kwargs.get('volume_type_id')
        self.share_network_id = kwargs.get('shared_network_id')
