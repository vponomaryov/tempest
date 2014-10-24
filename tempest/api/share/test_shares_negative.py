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

import testtools  # noqa

from tempest.api.share import base
from tempest import config_share as config
from tempest import exceptions
from tempest import share_exceptions
from tempest import test

CONF = config.CONF


class SharesNegativeTest(base.BaseSharesTest):

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_create_share_with_invalid_protocol(self):
        self.assertRaises(exceptions.BadRequest,
                          self.shares_client.create_share,
                          share_protocol="nonexistent_protocol")

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_get_share_with_wrong_id(self):
        self.assertRaises(exceptions.NotFound, self.shares_client.get_share,
                          "wrong_share_id")

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_get_share_without_passing_share_id(self):
        # Should not be able to get share when empty ID is passed
        self.assertRaises(exceptions.NotFound,
                          self.shares_client.get_share, '')

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_list_shares_nonadmin_with_nonexistent_share_server_filter(self):
        # filtering by share server allowed only for admins by default
        self.assertRaises(exceptions.Unauthorized,
                          self.shares_client.list_shares_with_detail,
                          {'share_server_id': 'fake_share_server_id'})

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_delete_share_with_wrong_id(self):
        self.assertRaises(exceptions.NotFound, self.shares_client.delete_share,
                          "wrong_share_id")

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_delete_share_without_passing_share_id(self):
        # Should not be able to delete share when empty ID is passed
        self.assertRaises(exceptions.NotFound,
                          self.shares_client.delete_share, '')

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_create_snapshot_with_wrong_id(self):
        self.assertRaises(exceptions.NotFound,
                          self.shares_client.create_snapshot,
                          "wrong_share_id")

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_delete_snapshot_with_wrong_id(self):
        self.assertRaises(exceptions.NotFound,
                          self.shares_client.delete_snapshot,
                          "wrong_share_id")

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_create_share_with_invalid_size(self):
        self.assertRaises(exceptions.BadRequest,
                          self.shares_client.create_share, size="#$%")

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_create_share_with_out_passing_size(self):
        self.assertRaises(exceptions.BadRequest,
                          self.shares_client.create_share, size="")

    @test.attr(type=["negative", "smoke", "gate", ])
    def test_create_share_with_zero_size(self):
        self.assertRaises(exceptions.BadRequest,
                          self.shares_client.create_share, size=0)

    @test.attr(type=["negative", "gate", ])
    def test_try_delete_share_with_existing_snapshot(self):
        # share can not be deleted while snapshot exists

        # create share
        __, share = self.create_share()

        # create snapshot
        self.create_snapshot_wait_for_active(share["id"])

        # try delete share
        self.assertRaises(exceptions.Unauthorized,
                          self.shares_client.delete_share, share["id"])

    @test.attr(type=["negative", "gate", ])
    def test_create_share_from_snap_with_less_size(self):
        # requires minimum 5Gb available space

        skip_msg = "Check disc space for this test"

        try:  # create share
            __, share = self.create_share(
                size=2, cleanup_in_class=False)
        except share_exceptions.ShareBuildErrorException:
            self.skip(skip_msg)

        try:  # create snapshot
            __, snap = self.create_snapshot_wait_for_active(
                share["id"], cleanup_in_class=False)
        except share_exceptions.SnapshotBuildErrorException:
            self.skip(skip_msg)

        # try create share from snapshot with less size
        self.assertRaises(exceptions.BadRequest,
                          self.create_share,
                          size=1, snapshot_id=snap["id"],
                          cleanup_in_class=False)

    @test.attr(type=["negative", "smoke", "gate", ])
    @testtools.skipIf(not CONF.share.multitenancy_enabled,
                      "Only for multitenancy.")
    def test_create_share_with_nonexistant_share_network(self):
        self.assertRaises(exceptions.NotFound,
                          self.shares_client.create_share,
                          share_network_id="wrong_sn_id")

    @test.attr(type=["negative", "smoke", "gate", ])
    @testtools.skipIf(not CONF.share.multitenancy_enabled,
                      "Only for multitenancy.")
    def test_create_share_from_snap_with_different_share_network(self):
        # create share
        __, share = self.create_share(cleanup_in_class=False)

        # get parent's share network
        __, parent_share = self.shares_client.get_share(share["id"])
        __, parent_sn = self.shares_client.get_share_network(
            parent_share["share_network_id"])

        # create new share-network - net duplicate of parent's share
        __, new_duplicated_sn = self.create_share_network(
            cleanup_in_class=False,
            neutron_net_id=parent_sn["neutron_net_id"],
            neutron_subnet_id=parent_sn["neutron_subnet_id"],
        )

        # create snapshot of parent share
        __, snap = self.create_snapshot_wait_for_active(
            share["id"], cleanup_in_class=False)

        # try create share with snapshot using another share-network
        # 400 bad request is expected
        self.assertRaises(
            exceptions.BadRequest,
            self.create_share,
            cleanup_in_class=False,
            share_network_id=new_duplicated_sn["id"],
            snapshot_id=snap["id"],
        )
