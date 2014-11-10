from tempest.common.utils.linux import remote_client
from tempest.openstack.common import log as logging
from tempest.scenario import manager
from tempest import config_share as config
from tempest import exceptions
from tempest.common.utils import data_utils


CONF = config.CONF

LOG = logging.getLogger(__name__)


class ManilaBasicScenarioWFACdote(manager.ManilaScenarioTest):
    protocol = "NFS"
    shares = []
    snapshots = []
    specs = \
        {u'netapp:vserverName': u'testvsm', u'netapp:clusName': u'manila',
         u'share_backend_name': u'NetApp_WFA',
         u'netapp:aggrName': u'aggr2', u'netapp:levelOfAccess': u'su'}

    def tearDown(self):
        super(ManilaBasicScenarioWFACdote, self).tearDown()
        for snapshot in self.snapshots:
            self.shares_client.delete_snapshot(snapshot["id"])
            self.shares_client.wait_for_resource_deletion(
                snapshot_id=snapshot["id"])

        for share in self.shares:
            self.shares_client.delete_share(share['id'])
            self.shares_client.wait_for_resource_deletion(share_id=share["id"])

        self.doCleanups()

    def setUp(self):
        super(ManilaBasicScenarioWFACdote, self).setUp()
        if not hasattr(self, 'image_ref'):
            self.image_ref = CONF.compute.image_ref
        if not hasattr(self, 'flavor_ref'):
            self.flavor_ref = CONF.compute.flavor_ref
        creds = CONF.scenario.creds_for_manila_mount
        self.user_name = creds[0] 
        self.password = creds[1] 
        self.address = creds[2] 

        name = data_utils.rand_name("wfa")
        self.volume_type = self.create_volume_type(name, self.specs)

    def get_remote_client(self):
        linux_client = remote_client.RemoteClient(self.address, self.user_name,
                                                  password=self.password)
        try:
            linux_client.validate_authentication()
        except exceptions.SSHTimeout:
            raise
        return linux_client

    def create_file(self, remote_client, path, file_name):
        command = "touch %s" % (path + '/' + file_name)
        resp = remote_client.exec_command(command)
        return resp

    def check_file(self, remote_client, path, file_name):
        try:
            command = "sudo ls %s" % path
            resp = remote_client.exec_command(command)
        except exceptions.SSHExecCommandFailed as e:
            resp = ""

        return file_name in resp

    def mount_share(self, share, remote_client, path):
        resp, share = self.shares_client.get_share(share['id'])
        share_path = share['export_location']
        try:
            command = "sudo mkdir %s" % path
            remote_client.exec_command(command)
        except exceptions.SSHExecCommandFailed as e:
            msg = "File exists"
            if msg not in str(e):
                raise e

        try:
            command = "sudo mount  %s %s" % (share_path, path)
            resp = remote_client.exec_command(command)
        except exceptions.SSHExecCommandFailed as e:
            msg_1 = "access denied"
            msg_2 = "timed out, giving up"
            if msg_1 in str(e) or msg_2 in str(e):
                resp = False
            else:
                raise e
        return resp

    def unmount_share(self, remote_client, path):
        command = "sudo umount  %s" % path
        resp = remote_client.exec_command(command)
        return resp

    def test_manila_basic(self):
        """
        1) create share1
        2) mount share (1) to VM
        3) create files
        4) create snapshot from share1 (1)
        5) create share from snapshot (4)
        6) mount share (5) to VM
        7) Assert files (3) exist
        8) create additional files in share (4)
        9) Assert files appeared only on share (4), but not on (1)
        10) Unmount share (4) from VM
        11) Assert files (3, 8) does not exist
        """
        # 1
        share = self.create_share(volume_type_id=self.volume_type['id'])
        self.shares.append(share)

        self.provide_access(share, self.address)
        # 2
        remote_client = self.get_remote_client()
        mount_path_1 = "/opt/test_1"
        self.mount_share(share, remote_client, mount_path_1)

        # 3
        filename_1 = "first"
        self.create_file(remote_client, mount_path_1, filename_1)

        # 4
        snapshot = self.create_snapshot(share)
        self.snapshots.append(snapshot)

        # 5
        share_from_sp = \
            self.create_share(snapshot=snapshot,
                              volume_type_id=self.volume_type['id'])
        self.shares.append(share_from_sp)

        self.provide_access(share_from_sp, self.address)

        # 6
        mount_path_2 = "/opt/test_2"
        self.mount_share(share_from_sp, remote_client, mount_path_2)

        # 7
        resp = self.mount_share(share_from_sp, remote_client, mount_path_2)
        self.assertTrue(resp)

        # 9
        resp = self.check_file(remote_client, mount_path_2, filename_1)
        self.assertTrue(resp)

        # 10
        filename_2 = "second"
        self.create_file(remote_client, mount_path_2, filename_2)

        # 11
        resp = self.check_file(remote_client, mount_path_2, filename_2)
        self.assertTrue(resp)
        # 12
        self.unmount_share(remote_client, mount_path_2)

        # 13
        resp = self.check_file(remote_client, mount_path_2, filename_2)
        self.assertFalse(resp)

class ManilaBasicScenarioWFA7mod(ManilaBasicScenarioWFACdote):
    specs = \
        {u'netapp:clusName': u'172.16.64.72',
         u'share_backend_name': u'NetApp_WFA2',
         u'netapp:aggrName': u'aggr1',
         u'netapp:levelOfAccess': u'rw'}