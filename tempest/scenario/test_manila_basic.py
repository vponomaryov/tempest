from tempest.common.utils.linux import remote_client
from tempest.openstack.common import log as logging
from tempest.scenario import manager
from tempest import config_share as config
from tempest import exceptions
from tempest.common.utils import data_utils


CONF = config.CONF

LOG = logging.getLogger(__name__)


class ManilaBasicScenario(manager.ManilaScenarioTest):
    protocol = "NFS"
    shares = []
    snapshots = []
    share_network = {'id': None}

    def tearDown(self):
        super(ManilaBasicScenario, self).tearDown()
        for snapshot in self.snapshots:
            self.shares_client.delete_snapshot(snapshot["id"])
            self.shares_client.wait_for_resource_deletion(
                snapshot_id=snapshot["id"])

        for share in self.shares:
            self.shares_client.delete_share(share['id'])
            self.shares_client.wait_for_resource_deletion(share_id=share["id"])

        __, shares_servers = self.shares_client.list_share_servers()
        for i in shares_servers:
            if i['share_network_id'] == self.share_network['id']:
                self.shares_client.delete_share_server(i['id'])

        self.shares_client.delete_share_network(self.share_network)

        self.doCleanups()

    def setUp(self):
        super(ManilaBasicScenario, self).setUp()
        if not hasattr(self, 'image_ref'):
            self.image_ref = CONF.compute.image_ref
        if not hasattr(self, 'flavor_ref'):
            self.flavor_ref = CONF.compute.flavor_ref
        self.user_name = CONF.scenario.ssh_user
        self.share_network = self.create_share_network()
        self.keypair = self.create_keypair()
        # NOTE(MS) for some images need use password
        # authentication instead of keypair
        self.password = CONF.compute.image_ssh_password

    def get_remote_client(self, ip):
        private_key = self.keypair['private_key']
        linux_client = remote_client.RemoteClient(ip, self.user_name,
                                                  password=self.password,
                                                  pkey=private_key)
        try:
            linux_client.validate_authentication()
        except exceptions.SSHTimeout:
            raise
        return linux_client

    def boot_instance(self):
        security_group = self._create_security_group()
        security_groups = [security_group]
        create_kwargs = {
            'key_name': self.keypair['name'],
            'security_groups': security_groups,
        }
        name = data_utils.rand_name(self.__class__.__name__)

        _, server = self.servers_client.create_server(name,
                                                      self.image_ref,
                                                      self.flavor_ref,
                                                      **create_kwargs)

        self.addCleanup(self.servers_client.wait_for_server_termination,
                        server['id'])

        self.addCleanup_with_wait(
            waiter_callable=self.servers_client.wait_for_server_termination,
            thing_id=server['id'], thing_id_param='server_id',
            cleanup_callable=self.delete_wrapper,
            cleanup_args=[self.servers_client.delete_server, server['id']])

        self.servers_client.wait_for_server_status(server_id=server['id'],
                                                   status='ACTIVE')
        _, instance = self.servers_client.get_server(server['id'])
        return instance

    def get_ssh_client(self, instance):
        # Obtain a floating IP
        _, floating_ip = self.floating_ips_client.create_floating_ip()
        self.addCleanup(self.delete_wrapper,
                        self.floating_ips_client.delete_floating_ip,
                        floating_ip['id'])
        # Attach a floating IP
        self.floating_ips_client.associate_floating_ip_to_server(
            floating_ip['ip'], instance['id'])

        remote_client = self.get_remote_client(
            ip=floating_ip['ip'])
        return remote_client

    def nova_floating_ip_create(self):
        _, self.floating_ip = self.floating_ips_client.create_floating_ip()
        self.addCleanup(self.delete_wrapper,
                        self.floating_ips_client.delete_floating_ip,
                        self.floating_ip['id'])

    def nova_floating_ip_add(self):
        self.floating_ips_client.associate_floating_ip_to_server(
            self.floating_ip['ip'], self.server['id'])

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
        2) create VM1
        3) provide access for VM1 (2)
        4) mount share (1) to VM1 (2)
        5) create files
        6) create snapshot from share1 (1)
        7) create share from snapshot (6)
        8) create second VM2
        9) try mount (7) to (8) - permission denied
        10) add access for VM2 (8) using share (7)
        11) try mount share (7) to VM1 (2) - permission denied
        12) mount share (7) to VM (8)
        13) Assert files (5) exist
        14) create additional files in share (7)
        15) Assert files appeared only on share (7), but not on (1)
        16) Unmount share (7) from VM2 (8)
        17) Assert files (5, 14) does not exist
        18) deny access to VM2 (8) for share (7)
        19) try mount share(7) to VM2 (8) - permission denied
        """
        # 1
        share = self.create_share()
        self.shares.append(share)
        # 2
        instance_1 = self.boot_instance()

        # 3
        rule_1 = self.provide_access(share, instance_1)

        # 4
        remote_client_1 = self.get_ssh_client(instance_1)
        mount_path_1 = "/opt/test_1"
        self.mount_share(share, remote_client_1, mount_path_1)

        # 5
        filename_1 = "first"
        self.create_file(remote_client_1, mount_path_1, filename_1)

        # 6
        snapshot = self.create_snapshot(share)
        self.snapshots.append(snapshot)

        # 7
        share_from_sp = self.create_share(snapshot)
        self.shares.append(share_from_sp)

        # 8
        instance_2 = self.boot_instance()

        # 9
        remote_client_2 = self.get_ssh_client(instance_2)
        mount_path_2 = "/opt/test_2"
        self.mount_share(share_from_sp, remote_client_2, mount_path_2)

        # 10
        rule_2 = self.provide_access(share_from_sp, instance_2)

        # 11
        resp = self.mount_share(share_from_sp, remote_client_1, mount_path_2)
        self.assertFalse(resp)

        # 12
        self.mount_share(share_from_sp, remote_client_2, mount_path_2)

        # 13
        resp = self.check_file(remote_client_2, mount_path_2, filename_1)
        self.assertTrue(resp)

        # 14
        filename_2 = "second"
        self.create_file(remote_client_2, mount_path_2, filename_2)

        # 15
        resp = self.check_file(remote_client_2, mount_path_2, filename_2)
        self.assertTrue(resp)
        resp = self.check_file(remote_client_1, mount_path_2, filename_2)
        self.assertFalse(resp)

        # 16
        self.unmount_share(remote_client_2, mount_path_2)

        # 17
        resp = self.check_file(remote_client_2, mount_path_2, filename_2)
        self.assertFalse(resp)

        # 18
        self.deny_access(share_from_sp, rule_2)
        self.deny_access(share, rule_1)

        # 19
        resp = self.mount_share(share_from_sp, remote_client_2, mount_path_2)
        self.assertFalse(resp)
