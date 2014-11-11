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


class ShareAccessRulesCreateDeleteTest(stressaction.ShareStressAction):

    def setUp(self, **kwargs):
        super(ShareAccessRulesCreateDeleteTest, self).setUp(**kwargs)
        self.access_type = kwargs.get("access_type") or "ip"
        self.access_to = kwargs.get("access_to") or "1.1.1.1"

    def run(self):
        share_name = data_utils.rand_name("stress-tests-share-name")

        self.logger.info("creating %s" % share_name)

        __, share = self.shares_client.create_share(
            share_protocol=self.protocol,
            name=share_name,
            description=data_utils.rand_name("share-description"),
            size=self.share_size,
            share_network_id=self.share_network_id,
            volume_type_id=self.volume_type_id
        )
        self.shares_client.wait_for_share_status(share["id"], "available")
        self.logger.info("created %s" % share_name)

        self.logger.info("creating rule for %s" % share_name)

        # create rule
        resp, rule = self.shares_client.create_access_rule(share["id"],
                                                           self.access_type,
                                                           self.access_to)
        self.shares_client.wait_for_access_rule_status(share["id"],
                                                       rule["id"],
                                                       "active")
        self.logger.info("created rule for %s" % share_name)
        self.logger.info("deleting rule %s" % share_name)

        # delete rule
        resp, _ = self.shares_client.delete_access_rule(self.share["id"],
                                                        rule["id"])
        self.logger.info("deleted rule %s" % share_name)
        self.logger.info("deleting %s" % share_name)

        self.shares_client.delete_share(share["id"])
        self.shares_client.wait_for_resource_deletion(share_id=share["id"])

        self.logger.info("deleted %s" % share_name)
