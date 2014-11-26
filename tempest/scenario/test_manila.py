from tempest.common.utils.linux import remote_client
from tempest.openstack.common import log as logging
from tempest.scenario import manager
from tempest import config_share as config
from tempest import exceptions
from tempest.common.utils import data_utils


CONF = config.CONF

LOG = logging.getLogger(__name__)


class ManilaBasicScenario(manager.ManilaScenarioTest):
    protocol = CONF.share.enable_protocols[0]
    shares = []
    snapshots = []

    def tearDown(self):
        super(ManilaBasicScenario, self).tearDown()
        share = self.shares[1]
        self.shares_client.delete_share(share['id'])
        self.shares_client.wait_for_resource_deletion(share_id=share["id"])

        for snapshot in self.snapshots:
            self.shares_client.delete_snapshot(snapshot["id"])
            self.shares_client.wait_for_resource_deletion(
                snapshot_id=snapshot["id"])

        share = self.shares[0]
        self.shares_client.delete_share(share['id'])
        self.shares_client.wait_for_resource_deletion(share_id=share["id"])

        __, shares_servers = self.shares_client.list_share_servers()

        if self.share_network_id:
            network_name = self.share_network['name']
            for share_server in shares_servers:
                if share_server['share_network_name'] == network_name:
                    self.shares_client.delete_share_server(share_server['id'])
                    self.shares_client.wait_for_resource_deletion(
                        server_id=share_server["id"])
            self.shares_client.delete_share_network(self.share_network_id)

    def setUp(self):
        super(ManilaBasicScenario, self).setUp()
        if not hasattr(self, 'image_ref'):
            self.image_ref = CONF.compute.image_ref
        if not hasattr(self, 'flavor_ref'):
            self.flavor_ref = CONF.compute.flavor_ref

        self.share_network_id = CONF.scenario.share_network_id
        self.volume_type_id = CONF.scenario.volume_type_id
        if not self.volume_type_id:
            self.share_network = self.create_share_network()
            self.share_network_id = self.share_network['id']

        # NOTE(MS) for some images need use password
        # authentication instead of keypair
        self.keypair = self.create_keypair()

        instances = CONF.scenario.creds_for_manila_mount
        if not instances:
            self.instance_1 = self.boot_instance()
            self.instance_2 = self.boot_instance()
        else:
            self.instance_1 = instances[0:3]
            self.instance_2 = instances[3:6]

    def get_remote_client(self, creds_or_ip):
        if isinstance(creds_or_ip, list):
            ip = creds_or_ip[2]
            username = creds_or_ip[0]
            password = creds_or_ip[1]
            private_key = None
        else:
            ip = creds_or_ip
            username = CONF.compute.ssh_user
            password = CONF.compute.image_ssh_password
            private_key = self.keypair['private_key']
        linux_client = remote_client.RemoteClient(ip, username,
                                                  password=password,
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

    def get_ssh_client(self, instance_or_creds):
        if isinstance(instance_or_creds, dict):
            # Obtain a floating IP
            _, floating_ip = self.floating_ips_client.create_floating_ip()
            self.addCleanup(self.delete_wrapper,
                            self.floating_ips_client.delete_floating_ip,
                            floating_ip['id'])
            # Attach a floating IP
            self.floating_ips_client.associate_floating_ip_to_server(
                floating_ip['ip'], instance_or_creds['id'])

            remote_client = self.get_remote_client(floating_ip['ip'])
        else:
            remote_client = self.get_remote_client(instance_or_creds)

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
        1) create share 1
        2) provide access for VM1
        3) mount share (1) to VM1
        4) create files
        5) create snapshot from share1 (1)
        6) create share from snapshot (6)
        7) try mount (7) to (8) - permission denied
        8) add access for VM2 using share (7)
        9) try mount share (7) to VM1  - permission denied
        10) mount share (7) to VM2
        11) Assert files (5) exist
        12) create additional files in share (7)
        13) Assert files appeared only on share (7), but not on (1)
        14) Unmount share (7) from VM2
        15) Assert files (5, 14) does not exist
        16) deny access to VM2 for share (7)
        17) try mount share(7) to VM2 - permission denied
        """
        # 1
        share = self.create_share()
        self.shares.append(share)
        # 2
        rule_1 = self.provide_access(share, self.instance_1)
        # 3
        remote_client_1 = self.get_ssh_client(self.instance_1)
        mount_path_1 = "/opt/test_1"
        self.mount_share(share, remote_client_1, mount_path_1)
        # 4
        filename_1 = "first"
        self.create_file(remote_client_1, mount_path_1, filename_1)
        # 5
        snapshot = self.create_snapshot(share)
        self.snapshots.append(snapshot)
        # 6
        share_from_sp = self.create_share(snapshot)
        self.shares.append(share_from_sp)
        # 7
        remote_client_2 = self.get_ssh_client(self.instance_2)
        mount_path_2 = "/opt/test_2"
        self.mount_share(share_from_sp, remote_client_2, mount_path_2)
        # 8
        rule_2 = self.provide_access(share_from_sp, self.instance_2)
        # 9
        resp = self.mount_share(share_from_sp, remote_client_1, mount_path_2)
        self.assertFalse(resp)
        # 10
        self.mount_share(share_from_sp, remote_client_2, mount_path_2)
        # 11
        resp = self.check_file(remote_client_2, mount_path_2, filename_1)
        self.assertTrue(resp)
        # 12
        filename_2 = "second"
        self.create_file(remote_client_2, mount_path_2, filename_2)
        # 13
        resp = self.check_file(remote_client_2, mount_path_2, filename_2)
        self.assertTrue(resp)
        resp = self.check_file(remote_client_1, mount_path_2, filename_2)
        self.assertFalse(resp)
        # 14
        self.unmount_share(remote_client_2, mount_path_2)
        # 15
        resp = self.check_file(remote_client_2, mount_path_2, filename_2)
        self.assertFalse(resp)
        # 16
        self.deny_access(share_from_sp, rule_2)
        self.deny_access(share, rule_1)
        # 17
        resp = self.mount_share(share_from_sp, remote_client_2, mount_path_2)
        self.assertFalse(resp)
