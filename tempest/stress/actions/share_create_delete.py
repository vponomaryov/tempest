# Copyright 2014 Mirantis Inc.
# All Rights Reserved.
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

from tempest.common.utils import data_utils
import tempest.stress.stressaction as stressaction


class ShareCreateDeleteTest(stressaction.ShareStressAction):

    def setUp(self, **kwargs):
        manila_driver = kwargs.get('driver')

        if manila_driver == 'cdot':
            extra_specs = \
                {u'netapp:vserverName': u'testvsm',
                 u'netapp:clusName': u'manila',
                 u'share_backend_name': u'NetApp_WFA',
                 u'netapp:aggrName': u'aggr2',
                 u'netapp:levelOfAccess': u'su'}
        elif manila_driver == "7mod":
            extra_specs = \
                {u'netapp:clusName': u'172.16.64.72',
                 u'share_backend_name': u'NetApp_WFA2',
                 u'netapp:aggrName': u'aggr1',
                 u'netapp:levelOfAccess': u'rw'}
        else:
            extra_specs = None

        self.volume_type_id = None
        if extra_specs:
            volume_type_name = data_utils.rand_name("stress-tests-volume-type")
            __, volume_type = \
                self.shares_client.create_volume_type(
                    name=volume_type_name, extra_specs=extra_specs)

            self.volume_type_id = volume_type['id']

    def run(self):
        share_name = data_utils.rand_name("stress-tests-share-name")

        self.logger.info("creating %s" % share_name)

        __, share = self.shares_client.create_share(
            share_protocol=self.protocol,
            name=share_name,
            description=data_utils.rand_name("share-description"),
            size=self.share_size,
            share_network_id=self.share_network,
            volume_type_id=self.volume_type_id
        )
        self.shares_client.wait_for_share_status(share["id"], "available")
        self.logger.info("created %s" % share_name)

        self.logger.info("deleting %s" % share_name)

        self.shares_client.delete_share(share["id"])
        self.shares_client.wait_for_resource_deletion(share_id=share["id"])

        self.logger.info("deleted %s" % share_name)