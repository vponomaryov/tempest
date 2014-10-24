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

from tempest.api.share import base
from tempest import test


class SecurityServicesMappingTest(base.BaseSharesTest):

    @classmethod
    def setUpClass(cls):
        super(SecurityServicesMappingTest, cls).setUpClass()
        cls.cl = cls.shares_client

    def setUp(self):
        super(SecurityServicesMappingTest, self).setUp()

        # create share network
        data = self.generate_share_network_data()

        resp, self.sn = self.create_share_network(client=self.cl, **data)
        self.assertIn(int(resp["status"]), test.HTTP_SUCCESS)
        self.assertDictContainsSubset(data, self.sn)

        # create security service
        data = self.generate_security_service_data()

        resp, self.ss = self.create_security_service(client=self.cl, **data)
        self.assertIn(int(resp["status"]), test.HTTP_SUCCESS)
        self.assertDictContainsSubset(data, self.ss)

        # Add security service to share network
        resp, __ = self.cl.add_sec_service_to_share_network(self.sn["id"],
                                                            self.ss["id"])
        self.assertIn(int(resp["status"]), test.HTTP_SUCCESS)

    @test.attr(type=["gate", "smoke"])
    def test_map_ss_to_sn_and_list(self):

        # List security services for share network
        resp, ls = self.cl.list_sec_services_for_share_network(self.sn["id"])
        self.assertIn(int(resp["status"]), test.HTTP_SUCCESS)
        self.assertEqual(1, len(ls))
        for key in ["status", "id", "name"]:
            self.assertIn(self.ss[key], ls[0][key])

    @test.attr(type=["gate", "smoke"])
    def test_map_ss_to_sn_and_delete(self):

        # Remove security service from share network
        resp, __ = self.cl.remove_sec_service_from_share_network(self.sn["id"],
                                                                 self.ss["id"])
        self.assertIn(int(resp["status"]), test.HTTP_SUCCESS)

    @test.attr(type=["gate", "smoke"])
    def test_remap_ss_to_sn(self):

        # Remove security service from share network
        resp, __ = self.cl.remove_sec_service_from_share_network(self.sn["id"],
                                                                 self.ss["id"])
        self.assertIn(int(resp["status"]), test.HTTP_SUCCESS)

        # Add security service to share network again
        resp, __ = self.cl.add_sec_service_to_share_network(self.sn["id"],
                                                            self.ss["id"])
        self.assertIn(int(resp["status"]), test.HTTP_SUCCESS)
