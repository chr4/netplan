#
# Tests for tunnel devices config generated via netplan
#
# Copyright (C) 2018-2022 Canonical, Ltd.
# Copyright (C) 2022 Datto, Inc.
# Author: Mathieu Trudel-Lapierre <mathieu.trudel.lapierre@canonical.com>
# Author: Anthony Timmins <atimmins@datto.com>
# Author: Lukas Märdian <slyon@ubuntu.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import re

from .base import TestBase, ND_WITHIPGW, ND_EMPTY, NM_WG, ND_WG, ND_VXLAN


def prepare_config_for_mode(renderer, mode, key=None, ttl=None):
    config = """network:
  version: 2
  renderer: {}
""".format(renderer)

    if mode == "ip6gre" \
            or mode == "ip6ip6" \
            or mode == "vti6" \
            or mode == "ipip6" \
            or mode == "ip6gretap":
        local_ip = "fe80::dead:beef"
        remote_ip = "2001:fe:ad:de:ad:be:ef:1"
    else:
        local_ip = "10.10.10.10"
        remote_ip = "20.20.20.20"

    append_ttl = '\n      ttl: {}'.format(ttl) if ttl else ''
    config += """
  tunnels:
    tun0:
      mode: {}
      local: {}
      remote: {}{}
      addresses: [ 15.15.15.15/24 ]
      gateway4: 20.20.20.21
""".format(mode, local_ip, remote_ip, append_ttl)

    # Handle key/keys as str or dict as required by the test
    if type(key) is str:
        config += """
      key: {}
""".format(key)
    elif type(key) is dict:
        config += """
      keys:
        input: {}
        output: {}
""".format(key['input'], key['output'])

    return config


def prepare_wg_config(listen=None, privkey=None, fwmark=None, peers=[], renderer="networkd"):
    config = '''network:
  version: 2
  renderer: %s
  tunnels:
    wg0:
      mode: wireguard
      addresses: [15.15.15.15/24, 2001:de:ad:be:ef:ca:fe:1/128]
      gateway4: 20.20.20.21
''' % renderer
    if privkey is not None:
        config += '      key: {}\n'.format(privkey)
    if fwmark is not None:
        config += '      mark: {}\n'.format(fwmark)
    if listen is not None:
        config += '      port: {}\n'.format(listen)
    if len(peers) > 0:
        config += '      peers:\n'
    for peer in peers:
        public_key = peer.get('public-key')
        peer.pop('public-key', None)
        shared_key = peer.get('shared-key')
        peer.pop('shared-key', None)
        pfx = '        - '
        for k, v in peer.items():
            config += '{}{}: {}\n'.format(pfx, k, v)
            pfx = '          '
        if public_key or shared_key:
            config += '{}keys:\n'.format(pfx)
            if public_key:
                config += '            public: {}\n'.format(public_key)
            if shared_key:
                config += '            shared: {}\n'.format(shared_key)
    return config


class _CommonParserErrors():

    def test_fail_invalid_private_key(self):
        """[wireguard] Show an error for an invalid private key"""
        config = prepare_wg_config(listen=12345, privkey='invalid.key',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:1005'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: wg0: invalid wireguard private key", out)

    def test_fail_invalid_public_key(self):
        """[wireguard] Show an error for an invalid private key"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': '/invalid.key',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:1005'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: wg0: invalid wireguard public key", out)

    def test_fail_invalid_shared_key(self):
        """[wireguard] Show an error for an invalid pre shared key"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'shared-key': 'invalid.key',
                                           'endpoint': '1.2.3.4:1005'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: wg0: invalid wireguard shared key", out)

    def test_fail_keepalive_2big(self):
        """[wireguard] Show an error if keepalive is too big"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 100500,
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: wg0: keepalive must be 0-65535 inclusive.", out)

    def test_fail_keepalive_bogus(self):
        """[wireguard] Show an error if keepalive is not an int"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 'bogus',
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: invalid unsigned int value 'bogus'", out)

    def test_fail_allowed_ips_prefix4(self):
        """[wireguard] Show an error if ipv4 prefix is too big"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/200, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: invalid prefix length in address", out)

    def test_fail_allowed_ips_prefix6(self):
        """[wireguard] Show an error if ipv6 prefix too big"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/224"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: invalid prefix length in address", out)

    def test_fail_allowed_ips_noprefix4(self):
        """[wireguard] Show an error if ipv4 prefix is missing"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: address \'0.0.0.0\' is missing /prefixlength", out)

    def test_fail_allowed_ips_noprefix6(self):
        """[wireguard] Show an error if ipv6 prefix is missing"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: address '2001:fe:ad:de:ad:be:ef:1' is missing /prefixlength", out)

    def test_fail_allowed_ips_bogus(self):
        """[wireguard] Show an error if the address is completely bogus"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[302.302.302.302/24, "2001:fe:ad:de:ad:be:ef:1"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: malformed address \'302.302.302.302/24\', \
must be X.X.X.X/NN or X:X:X:X:X:X:X:X/NN", out)

    def test_fail_remote_no_port4(self):
        """[wireguard] Show an error if ipv4 remote endpoint lacks a port"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: endpoint '1.2.3.4' is missing :port", out)

    def test_fail_remote_no_port6(self):
        """[wireguard] Show an error if ipv6 remote endpoint lacks a port"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': "2001:fe:ad:de:ad:be:ef:1"}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: invalid endpoint address or hostname", out)

    def test_fail_remote_no_port_hn(self):
        """[wireguard] Show an error if fqdn remote endpoint lacks a port"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': 'fq.dn'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: endpoint 'fq.dn' is missing :port", out)

    def test_fail_remote_big_port4(self):
        """[wireguard] Show an error if ipv4 remote endpoint port is too big"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:100500'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: invalid port in endpoint '1.2.3.4:100500", out)

    def test_fail_ipv6_remote_noport(self):
        """[wireguard] Show an error for v6 remote endpoint without port"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'endpoint': '"[2001:fe:ad:de:ad:be:ef:11]"'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("endpoint \'[2001:fe:ad:de:ad:be:ef:11]\' is missing :port", out)

    def test_fail_ipv6_remote_nobrace(self):
        """[wireguard] Show an error for v6 remote endpoint without closing brace"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'endpoint': '"[2001:fe:ad:de:ad:be:ef:11"'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("invalid address in endpoint '[2001:fe:ad:de:ad:be:ef:11'", out)

    def test_fail_ipv6_remote_malformed(self):
        """[wireguard] Show an error for malformed-v6 remote endpoint"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'endpoint': '"[2001:fe:badfilinad:be:ef]:11"'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("invalid endpoint address or hostname '[2001:fe:badfilinad:be:ef]:11", out)

    def test_fail_short_remote(self):
        """[wireguard] Show an error for too-short remote endpoint"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'endpoint': 'ab'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: invalid endpoint address or hostname 'ab'", out)

    def test_fail_bogus_peer_key(self):
        """[wireguard] Show an error for a bogus key in a peer"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'bogus': 'true',
                                           'endpoint': '1.2.3.4:1005'}], renderer=self.backend)

        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: unknown key 'bogus'", out)

    def test_fail_no_public_key(self):
        """[wireguard] Show an error for missing public_key"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:1005'}], renderer=self.backend)
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: wg0: a public key is required.", out)

    def test_vxlan_port_range_fail(self):
        out = self.generate('''network:
  tunnels:
    vx0:
      mode: vxlan
      port-range: [1,2,3]''', expect_fail=True)
        self.assertIn("Expected exactly two values for port-range", out)

    def test_vxlan_port_min_wrong_type(self):
        out = self.generate('''network:
  tunnels:
    vx0:
      mode: vxlan
      port-range: [a,10]''', expect_fail=True)
        self.assertIn("invalid unsigned int value 'a'", out)

    def test_vxlan_port_max_wrong_type(self):
        out = self.generate('''network:
  tunnels:
    vx0:
      mode: vxlan
      port-range: [10,b]''', expect_fail=True)
        self.assertIn("invalid unsigned int value 'b'", out)

    def test_vxlan_flags_fail(self):
        out = self.generate('''network:
  tunnels:
    vx0:
      mode: vxlan
      notifications: [INVALID]''', expect_fail=True)
        self.assertIn("invalid value for notifications: 'INVALID'", out)

    def test_vxlan_missing_vni(self):
        out = self.generate('''network:
  version: 2
  tunnels:
    vxlan1005:
      mode: vxlan''', expect_fail=True)
        self.assertIn('missing \'id\' property (VXLAN VNI)', out)

    def test_vxlan_oob_vni(self):
        out = self.generate('''network:
  version: 2
  tunnels:
    vxlan1005:
      mode: vxlan
      id: 17000000''', expect_fail=True)
        self.assertIn('VXLAN \'id\' (VNI) must be in range [1..16777215]', out)

    def test_vxlan_oob_flow_label(self):
        out = self.generate('''network:
  version: 2
  tunnels:
    vxlan1005:
      mode: vxlan
      id: 1005
      flow-label: 1111111''', expect_fail=True)
        self.assertIn('VXLAN \'flow-label\' must be in range [0..1048575]', out)

    def test_vxlan_local_remote_ip_family_mismatch(self):
        out = self.generate('''network:
  version: 2
  tunnels:
    vxlan1005:
      mode: vxlan
      id: 1005
      local: 10.10.10.1
      remote: fe80::3''', expect_fail=True)
        self.assertIn('\'local\' and \'remote\' must be of same IP family type', out)


class _CommonTests():

    def test_simple(self):
        """[wireguard] Validate generation of simple wireguard config"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   fwmark=42,
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'shared-key': '7voRZ/ojfXgfPOlswo3Lpma1RJq7qijIEEUEMShQFV8=',
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        self.generate(config)
        if self.backend == 'networkd':
            self.assert_networkd({'wg0.netdev': ND_WG % ('=4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=', '12345', '''FwMark=42

[WireGuardPeer]
PublicKey=M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=
AllowedIPs=0.0.0.0/0,2001:fe:ad:de:ad:be:ef:1/24
PersistentKeepalive=23
Endpoint=1.2.3.4:5
PresharedKey=7voRZ/ojfXgfPOlswo3Lpma1RJq7qijIEEUEMShQFV8='''),
                                  'wg0.network': ND_WITHIPGW % ('wg0', '15.15.15.15/24', '2001:de:ad:be:ef:ca:fe:1/128',
                                                                '20.20.20.21')})
        elif self.backend == 'NetworkManager':
            self.assert_nm({'wg0.nmconnection': NM_WG % ('4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=', '12345', '''fwmark=42

[wireguard-peer.M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=]
persistent-keepalive=23
endpoint=1.2.3.4:5
preshared-key=7voRZ/ojfXgfPOlswo3Lpma1RJq7qijIEEUEMShQFV8=
preshared-key-flags=0
allowed-ips=0.0.0.0/0;2001:fe:ad:de:ad:be:ef:1/24;''')})

    def test_simple_multi_pass(self):
        """[wireguard] Validate generation of a wireguard config, which is parsed multiple times"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        config = config.replace('tunnels:', 'bridges: {br0: {interfaces: [wg0]}}\n  tunnels:')
        self.generate(config)
        if self.backend == 'networkd':
            self.assert_networkd({'wg0.netdev': ND_WG % ('=4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=', '12345', '''
[WireGuardPeer]
PublicKey=M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=
AllowedIPs=0.0.0.0/0,2001:fe:ad:de:ad:be:ef:1/24
PersistentKeepalive=23
Endpoint=1.2.3.4:5'''),
                                  'wg0.network': (ND_WITHIPGW % ('wg0', '15.15.15.15/24', '2001:de:ad:be:ef:ca:fe:1/128',
                                                                 '20.20.20.21') + 'Bridge=br0\n')
                                  .replace('LinkLocalAddressing=ipv6', 'LinkLocalAddressing=no'),
                                  'br0.network': ND_EMPTY % ('br0', 'ipv6'),
                                  'br0.netdev': '''[NetDev]\nName=br0\nKind=bridge\n'''})
        elif self.backend == 'NetworkManager':
            self.assert_nm({'wg0.nmconnection': '''[connection]
id=netplan-wg0
type=wireguard
interface-name=wg0
slave-type=bridge # wokeignore:rule=slave
master=br0 # wokeignore:rule=master

[wireguard]
private-key=4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=
listen-port=12345

[wireguard-peer.M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=]
persistent-keepalive=23
endpoint=1.2.3.4:5
allowed-ips=0.0.0.0/0;2001:fe:ad:de:ad:be:ef:1/24;

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=manual
address1=2001:de:ad:be:ef:ca:fe:1/128
ip6-privacy=0
''',
                            'br0.nmconnection': '''[connection]
id=netplan-br0
type=bridge
interface-name=br0

[ipv4]
method=link-local

[ipv6]
method=ignore
'''})

    def test_2peers(self):
        """[wireguard] Validate generation of wireguard config with two peers"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'endpoint': '1.2.3.4:5'}, {
                                           'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG5=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        self.generate(config)
        if self.backend == 'networkd':
            self.assert_networkd({'wg0.netdev': ND_WG % ('=4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=', '12345', '''
[WireGuardPeer]
PublicKey=M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=
AllowedIPs=0.0.0.0/0,2001:fe:ad:de:ad:be:ef:1/24
PersistentKeepalive=23
Endpoint=1.2.3.4:5

[WireGuardPeer]
PublicKey=M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG5=
AllowedIPs=0.0.0.0/0,2001:fe:ad:de:ad:be:ef:1/24
PersistentKeepalive=23
Endpoint=1.2.3.4:5'''),
                                  'wg0.network': ND_WITHIPGW % ('wg0', '15.15.15.15/24', '2001:de:ad:be:ef:ca:fe:1/128',
                                                                '20.20.20.21')})
        elif self.backend == 'NetworkManager':
            self.assert_nm({'wg0.nmconnection': NM_WG % ('4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=', '12345', '''
[wireguard-peer.M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=]
persistent-keepalive=23
endpoint=1.2.3.4:5
allowed-ips=0.0.0.0/0;2001:fe:ad:de:ad:be:ef:1/24;

[wireguard-peer.M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG5=]
persistent-keepalive=23
endpoint=1.2.3.4:5
allowed-ips=0.0.0.0/0;2001:fe:ad:de:ad:be:ef:1/24;''')})

    def test_privatekeyfile(self):
        """[wireguard] Validate generation of another simple wireguard config"""
        config = prepare_wg_config(listen=12345, privkey='/tmp/test_private_key',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'shared-key': '/tmp/test_preshared_key',
                                           'endpoint': '1.2.3.4:5'}], renderer=self.backend)
        if self.backend == 'networkd':
            self.generate(config)
            self.assert_networkd({'wg0.netdev': ND_WG % ('File=/tmp/test_private_key', '12345', '''
[WireGuardPeer]
PublicKey=M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=
AllowedIPs=0.0.0.0/0,2001:fe:ad:de:ad:be:ef:1/24
PersistentKeepalive=23
Endpoint=1.2.3.4:5
PresharedKeyFile=/tmp/test_preshared_key'''),
                                  'wg0.network': ND_WITHIPGW % ('wg0', '15.15.15.15/24', '2001:de:ad:be:ef:ca:fe:1/128',
                                                                '20.20.20.21')})
        elif self.backend == 'NetworkManager':
            err = self.generate(config, expect_fail=True)
            self.assertIn('wg0: private key needs to be base64 encoded when using the NM backend', err)

    def test_ipv6_remote(self):
        """[wireguard] Validate generation of wireguard config with v6 remote endpoint"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 23,
                                           'endpoint': '"[2001:fe:ad:de:ad:be:ef:11]:5"'}], renderer=self.backend)
        self.generate(config)
        if self.backend == 'networkd':
            self.assert_networkd({'wg0.netdev': ND_WG % ('=4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=', '12345', '''
[WireGuardPeer]
PublicKey=M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=
AllowedIPs=0.0.0.0/0,2001:fe:ad:de:ad:be:ef:1/24
PersistentKeepalive=23
Endpoint=[2001:fe:ad:de:ad:be:ef:11]:5'''),
                                  'wg0.network': ND_WITHIPGW % ('wg0', '15.15.15.15/24', '2001:de:ad:be:ef:ca:fe:1/128',
                                                                '20.20.20.21')})
        elif self.backend == 'NetworkManager':
            self.assert_nm({'wg0.nmconnection': NM_WG % ('4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=', '12345', '''
[wireguard-peer.M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=]
persistent-keepalive=23
endpoint=[2001:fe:ad:de:ad:be:ef:11]:5
allowed-ips=0.0.0.0/0;2001:fe:ad:de:ad:be:ef:1/24;''')})

    def test_vxlan(self):
        out = self.generate('''network:
  renderer: %(r)s
  version: 2
  tunnels:
    vxlan1005:
      link: br0
      mode: vxlan
      local: 10.10.10.1
      remote: 224.0.0.5
      id: 1005
      port: 4789
      ageing: 42
      mac-learning: true
      limit: 37
      arp-proxy: true
      short-circuit: true
      type-of-service: 292
      ttl: 128
      flow-label: 0
      do-not-fragment: true
      notifications: [l2-miss, l3-miss]
      checksums: [udp, zero-udp6-tx, zero-udp6-rx, remote-tx, remote-rx]
      extensions: [group-policy, generic-protocol]
      port-range: [42, 442]
      neigh-suppress: false
  bridges:
    br0:
      interfaces: [vxlan1005]''' % {'r': self.backend})

        if self.backend == 'networkd':
            self.assert_networkd({'vxlan1005.netdev': ND_VXLAN % ('vxlan1005', 1005) +
                                  '''Group=224.0.0.5
Local=10.10.10.1
TOS=292
TTL=128
MacLearning=true
FDBAgeingSec=42
MaximumFDBEntries=37
ReduceARPProxy=true
L2MissNotification=true
L3MissNotification=true
RouteShortCircuit=true
UDPChecksum=true
UDP6ZeroChecksumTx=true
UDP6ZeroChecksumRx=true
RemoteChecksumTx=true
RemoteChecksumRx=true
GroupPolicyExtension=true
GenericProtocolExtension=true
DestinationPort=4789
PortRange=42-442
FlowLabel=0
IPDoNotFragment=true\n''',
                                  'vxlan1005.network': '''[Match]
Name=vxlan1005

[Network]
LinkLocalAddressing=no
ConfigureWithoutCarrier=yes
Bridge=br0

[Bridge]
NeighborSuppression=false\n''',
                                  'br0.network': '''[Match]
Name=br0

[Network]
LinkLocalAddressing=ipv6
ConfigureWithoutCarrier=yes
VXLAN=vxlan1005\n''',
                                  'br0.netdev': '''[NetDev]
Name=br0
Kind=bridge\n'''})
        elif self.backend == 'NetworkManager':
            self.assertIn('checksums/extensions/flow-lable/do-not-fragment are '
                          'not supported by NetworkManager', out)
            self.assert_nm({'vxlan1005': '''[connection]
id=netplan-vxlan1005
type=vxlan
interface-name=vxlan1005
slave-type=bridge # wokeignore:rule=slave
master=br0 # wokeignore:rule=master

[vxlan]
ageing=42
destination-port=4789
id=1005
learning=true
limit=37
local=10.10.10.1
remote=224.0.0.5
proxy=true
l2-miss=true
l3-miss=true
source-port-min=42
source-port-max=442
tos=292
ttl=128
rsc=true
parent=br0

[ipv4]
method=disabled

[ipv6]
method=ignore\n''',
                            'br0': '''[connection]
id=netplan-br0
type=bridge
interface-name=br0

[ipv4]
method=link-local

[ipv6]
method=ignore\n'''})

    def test_vxlan_maclearning_arpproxy_shortcircuit_true(self):
        self.generate('''network:
  renderer: %(r)s
  version: 2
  ethernets:
    eth0:
      ignore-carrier: true
  tunnels:
    vxlan1005:
      link: eth0
      mode: vxlan
      id: 1005
      mac-learning: true
      arp-proxy: true
      short-circuit: true''' % {'r': self.backend})

        if self.backend == 'networkd':
            self.assert_networkd({'vxlan1005.netdev': ND_VXLAN % ('vxlan1005', 1005) +
                                  '''MacLearning=true
ReduceARPProxy=true
RouteShortCircuit=true\n''',
                                 'vxlan1005.network': ND_EMPTY % ('vxlan1005', 'ipv6'),
                                  'eth0.network': ND_EMPTY % ('eth0', 'ipv6') +
                                  '''VXLAN=vxlan1005\n'''})

        elif self.backend == 'NetworkManager':
            self.assert_nm({'vxlan1005': '''[connection]
id=netplan-vxlan1005
type=vxlan
interface-name=vxlan1005

[vxlan]
id=1005
learning=true
proxy=true
rsc=true
parent=eth0

[ipv4]
method=disabled

[ipv6]
method=ignore\n''',
                            'eth0': '''[connection]
id=netplan-eth0
type=ethernet
interface-name=eth0

[ethernet]
wake-on-lan=0

[ipv4]
method=link-local

[ipv6]
method=ignore\n'''})

    def test_vxlan_maclearning_arpproxy_shortcircuit_false(self):
        self.generate('''network:
  renderer: %(r)s
  version: 2
  ethernets:
    eth0:
      ignore-carrier: true
  tunnels:
    vxlan1005:
      link: eth0
      mode: vxlan
      id: 1005
      mac-learning: false
      arp-proxy: false
      short-circuit: false''' % {'r': self.backend})

        if self.backend == 'networkd':
            self.assert_networkd({'vxlan1005.netdev': ND_VXLAN % ('vxlan1005', 1005) +
                                  '''MacLearning=false
ReduceARPProxy=false
RouteShortCircuit=false\n''',
                                 'vxlan1005.network': ND_EMPTY % ('vxlan1005', 'ipv6'),
                                  'eth0.network': ND_EMPTY % ('eth0', 'ipv6') +
                                  '''VXLAN=vxlan1005\n'''})

        elif self.backend == 'NetworkManager':
            self.assert_nm({'vxlan1005': '''[connection]
id=netplan-vxlan1005
type=vxlan
interface-name=vxlan1005

[vxlan]
id=1005
learning=false
proxy=false
rsc=false
parent=eth0

[ipv4]
method=disabled

[ipv6]
method=ignore\n''',
                            'eth0': '''[connection]
id=netplan-eth0
type=ethernet
interface-name=eth0

[ethernet]
wake-on-lan=0

[ipv4]
method=link-local

[ipv6]
method=ignore\n'''})


# Execute the _CommonParserErrors only for one backend, to spare some test cycles
class TestNetworkd(TestBase, _CommonTests, _CommonParserErrors):
    backend = 'networkd'

    def test_sit(self):
        """[networkd] Validate generation of SIT tunnels"""
        config = prepare_config_for_mode('networkd', 'sit')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=sit

[Tunnel]
Independent=true
Local=10.10.10.10
Remote=20.20.20.20
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_sit_he(self):
        """[networkd] Validate generation of SIT tunnels (HE example)"""
        # Test specifically a config like one that would enable Hurricane
        # Electric IPv6 tunnels.
        config = '''network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      addresses:
        - 1.1.1.1/24
        - "2001:cafe:face::1/64"  # provided by HE as routed /64
      gateway4: 1.1.1.254
  tunnels:
    he-ipv6:
      mode: sit
      remote: 2.2.2.2
      local: 1.1.1.1
      addresses:
        - "2001:dead:beef::2/64"
      gateway6: "2001:dead:beef::1"
'''
        self.generate(config)
        self.assert_networkd({'eth0.network': '''[Match]
Name=eth0

[Network]
LinkLocalAddressing=ipv6
Address=1.1.1.1/24
Address=2001:cafe:face::1/64
Gateway=1.1.1.254
''',
                              'he-ipv6.netdev': '''[NetDev]
Name=he-ipv6
Kind=sit

[Tunnel]
Independent=true
Local=1.1.1.1
Remote=2.2.2.2
''',
                              'he-ipv6.network': '''[Match]
Name=he-ipv6

[Network]
LinkLocalAddressing=ipv6
Address=2001:dead:beef::2/64
Gateway=2001:dead:beef::1
ConfigureWithoutCarrier=yes
'''})

    def test_vti(self):
        """[networkd] Validate generation of VTI tunnels"""
        config = prepare_config_for_mode('networkd', 'vti')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=vti

[Tunnel]
Independent=true
Local=10.10.10.10
Remote=20.20.20.20
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_vti_with_key_str(self):
        """[networkd] Validate generation of VTI tunnels with input/output keys"""
        config = prepare_config_for_mode('networkd', 'vti', key='1.1.1.1')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=vti

[Tunnel]
Independent=true
Local=10.10.10.10
Remote=20.20.20.20
InputKey=1.1.1.1
OutputKey=1.1.1.1
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_vti_with_key_dict(self):
        """[networkd] Validate generation of VTI tunnels with key dict"""
        config = prepare_config_for_mode('networkd', 'vti', key={'input': 1234, 'output': 5678})
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=vti

[Tunnel]
Independent=true
Local=10.10.10.10
Remote=20.20.20.20
InputKey=1234
OutputKey=5678
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_vti_invalid_key(self):
        """[networkd] Validate VTI tunnel generation key handling"""
        config = prepare_config_for_mode('networkd', 'vti', key={'input': 42, 'output': 'invalid'})
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: invalid tunnel key 'invalid'", out)

    def test_vti6(self):
        """[networkd] Validate generation of VTI6 tunnels"""
        config = prepare_config_for_mode('networkd', 'vti6')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=vti6

[Tunnel]
Independent=true
Local=fe80::dead:beef
Remote=2001:fe:ad:de:ad:be:ef:1
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_vti6_with_key(self):
        """[networkd] Validate generation of VTI6 tunnels with input/output keys"""
        config = prepare_config_for_mode('networkd', 'vti6', key='1.1.1.1')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=vti6

[Tunnel]
Independent=true
Local=fe80::dead:beef
Remote=2001:fe:ad:de:ad:be:ef:1
InputKey=1.1.1.1
OutputKey=1.1.1.1
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_vti6_invalid_key(self):
        """[networkd] Validate VTI6 tunnel generation key handling"""
        config = prepare_config_for_mode('networkd', 'vti6', key='invalid')
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: invalid tunnel key 'invalid'", out)

    def test_ipip6(self):
        """[networkd] Validate generation of IPIP6 tunnels"""
        config = prepare_config_for_mode('networkd', 'ipip6')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=ip6tnl

[Tunnel]
Independent=true
Mode=ipip6
Local=fe80::dead:beef
Remote=2001:fe:ad:de:ad:be:ef:1
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_ipip(self):
        """[networkd] Validate generation of IPIP tunnels"""
        config = prepare_config_for_mode('networkd', 'ipip', ttl=64)
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=ipip

[Tunnel]
Independent=true
Local=10.10.10.10
Remote=20.20.20.20
TTL=64
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_isatap(self):
        """[networkd] Warning for ISATAP tunnel generation not supported"""
        config = prepare_config_for_mode('networkd', 'isatap')
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: ISATAP tunnel mode is not supported", out)

    def test_gre(self):
        """[networkd] Validate generation of GRE tunnels"""
        config = prepare_config_for_mode('networkd', 'gre')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=gre

[Tunnel]
Independent=true
Local=10.10.10.10
Remote=20.20.20.20
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_ip6gre(self):
        """[networkd] Validate generation of IP6GRE tunnels"""
        config = prepare_config_for_mode('networkd', 'ip6gre', '33490175')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=ip6gre

[Tunnel]
Independent=true
Local=fe80::dead:beef
Remote=2001:fe:ad:de:ad:be:ef:1
InputKey=33490175
OutputKey=33490175
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_gretap(self):
        """[networkd] Validate generation of GRETAP tunnels"""
        config = prepare_config_for_mode('networkd', 'gretap')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=gretap

[Tunnel]
Independent=true
Local=10.10.10.10
Remote=20.20.20.20
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_ip6gretap(self):
        """[networkd] Validate generation of IP6GRETAP tunnels"""
        config = prepare_config_for_mode('networkd', 'ip6gretap')
        self.generate(config)
        self.assert_networkd({'tun0.netdev': '''[NetDev]
Name=tun0
Kind=ip6gretap

[Tunnel]
Independent=true
Local=fe80::dead:beef
Remote=2001:fe:ad:de:ad:be:ef:1
''',
                              'tun0.network': '''[Match]
Name=tun0

[Network]
LinkLocalAddressing=ipv6
Address=15.15.15.15/24
Gateway=20.20.20.21
ConfigureWithoutCarrier=yes
'''})

    def test_vxlan_port_range_swap(self):
        out = self.generate('''network:
  version: 2
  tunnels:
    vx0:
      mode: vxlan
      id: 1005
      remote: 10.0.0.5
      port-range: [100, 10]''')
        self.assertIn("swapped invalid port-range order [MIN, MAX]", out)

        self.assert_networkd({'vx0.netdev': ND_VXLAN % ('vx0', 1005) +
                              'Remote=10.0.0.5\nPortRange=10-100\nIndependent=true\n',
                              'vx0.network': ND_EMPTY % ('vx0', 'ipv6')})

    def test_vxlan_ip6_multicast(self):
        self.generate('''network:
  version: 2
  tunnels:
    vx0:
      mode: vxlan
      id: 1005
      remote: "ff42::dead:beef"''')

        self.assert_networkd({'vx0.netdev': ND_VXLAN % ('vx0', 1005) +
                              'Group=ff42::dead:beef\nIndependent=true\n',
                              'vx0.network': ND_EMPTY % ('vx0', 'ipv6')})


class TestNetworkManager(TestBase, _CommonTests):
    backend = 'NetworkManager'

    def test_fail_invalid_private_key_file(self):
        """[wireguard] Show an error for an invalid private key-file"""
        config = prepare_wg_config(listen=12345, privkey='/invalid.key',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'endpoint': '1.2.3.4:1005'}], renderer=self.backend)

        out = self.generate(config, expect_fail=True)
        self.assertIn("wg0: private key needs to be base64 encoded when using the NM backend", out)

    def test_fail_invalid_shared_key_file(self):
        """[wireguard] Show an error for an invalid pre shared key-file"""
        config = prepare_wg_config(listen=12345, privkey='4GgaQCy68nzNsUE5aJ9fuLzHhB65tAlwbmA72MWnOm8=',
                                   peers=[{'public-key': 'M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=',
                                           'allowed-ips': '[0.0.0.0/0, "2001:fe:ad:de:ad:be:ef:1/24"]',
                                           'keepalive': 14,
                                           'shared-key': '/invalid.key',
                                           'endpoint': '1.2.3.4:1005'}], renderer=self.backend)

        out = self.generate(config, expect_fail=True)
        self.assertIn("wg0: shared key needs to be base64 encoded when using the NM backend", out)

    def test_isatap(self):
        """[NetworkManager] Validate ISATAP tunnel generation"""
        config = prepare_config_for_mode('NetworkManager', 'isatap')
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=4
local=10.10.10.10
remote=20.20.20.20

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_sit(self):
        """[NetworkManager] Validate generation of SIT tunnels"""
        config = prepare_config_for_mode('NetworkManager', 'sit')
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=3
local=10.10.10.10
remote=20.20.20.20

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_sit_he(self):
        """[NetworkManager] Validate generation of SIT tunnels (HE example)"""
        # Test specifically a config like one that would enable Hurricane
        # Electric IPv6 tunnels.
        config = '''network:
  version: 2
  renderer: NetworkManager
  ethernets:
    eth0:
      addresses:
        - 1.1.1.1/24
        - "2001:cafe:face::1/64"  # provided by HE as routed /64
      gateway4: 1.1.1.254
  tunnels:
    he-ipv6:
      mode: sit
      remote: 2.2.2.2
      local: 1.1.1.1
      addresses:
        - "2001:dead:beef::2/64"
      gateway6: "2001:dead:beef::1"
'''
        self.generate(config)
        self.assert_nm({'eth0': '''[connection]
id=netplan-eth0
type=ethernet
interface-name=eth0

[ethernet]
wake-on-lan=0

[ipv4]
method=manual
address1=1.1.1.1/24
gateway=1.1.1.254

[ipv6]
method=manual
address1=2001:cafe:face::1/64
ip6-privacy=0
''',
                        'he-ipv6': '''[connection]
id=netplan-he-ipv6
type=ip-tunnel
interface-name=he-ipv6

[ip-tunnel]
mode=3
local=1.1.1.1
remote=2.2.2.2

[ipv4]
method=disabled

[ipv6]
method=manual
address1=2001:dead:beef::2/64
ip6-privacy=0
gateway=2001:dead:beef::1
'''})

    def test_vti(self):
        """[NetworkManager] Validate generation of VTI tunnels"""
        config = prepare_config_for_mode('NetworkManager', 'vti')
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=5
local=10.10.10.10
remote=20.20.20.20

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_vti6(self):
        """[NetworkManager] Validate generation of VTI6 tunnels"""
        config = prepare_config_for_mode('NetworkManager', 'vti6')
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=9
local=fe80::dead:beef
remote=2001:fe:ad:de:ad:be:ef:1

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_ip6ip6(self):
        """[NetworkManager] Validate generation of IP6IP6 tunnels"""
        config = prepare_config_for_mode('NetworkManager', 'ip6ip6')
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=6
local=fe80::dead:beef
remote=2001:fe:ad:de:ad:be:ef:1

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_ipip(self):
        """[NetworkManager] Validate generation of IPIP tunnels"""
        config = prepare_config_for_mode('NetworkManager', 'ipip', ttl=64)
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=1
local=10.10.10.10
remote=20.20.20.20
ttl=64

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_gre(self):
        """[NetworkManager] Validate generation of GRE tunnels"""
        config = prepare_config_for_mode('NetworkManager', 'gre')
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=2
local=10.10.10.10
remote=20.20.20.20

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_gre_with_keys(self):
        """[NetworkManager] Validate generation of GRE tunnels with keys"""
        config = prepare_config_for_mode('NetworkManager', 'gre', key={'input': 1111, 'output': 5555})
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=2
local=10.10.10.10
remote=20.20.20.20
input-key=1111
output-key=5555

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_ip6gre(self):
        """[NetworkManager] Validate generation of IP6GRE tunnels"""
        config = prepare_config_for_mode('NetworkManager', 'ip6gre')
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=8
local=fe80::dead:beef
remote=2001:fe:ad:de:ad:be:ef:1

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_ip6gre_with_key(self):
        """[NetworkManager] Validate generation of IP6GRE tunnels with key"""
        config = prepare_config_for_mode('NetworkManager', 'ip6gre', key='9999')
        self.generate(config)
        self.assert_nm({'tun0': '''[connection]
id=netplan-tun0
type=ip-tunnel
interface-name=tun0

[ip-tunnel]
mode=8
local=fe80::dead:beef
remote=2001:fe:ad:de:ad:be:ef:1
input-key=9999
output-key=9999

[ipv4]
method=manual
address1=15.15.15.15/24
gateway=20.20.20.21

[ipv6]
method=ignore
'''})

    def test_vxlan_uuid(self):
        self.generate('''network:
  renderer: NetworkManager
  tunnels:
    vx0:
      mode: vxlan
      id: 42
      link: id0
  ethernets:
    id0:
      match: {name: 'someIface'}''')

        self.assert_networkd({})

        # get assigned UUID  from id0 connection
        with open(os.path.join(self.workdir.name, 'run/NetworkManager/system-connections/netplan-id0.nmconnection')) as f:
            m = re.search('uuid=([0-9a-fA-F-]{36})\n', f.read())
            self.assertTrue(m)
            uuid = m.group(1)
            self.assertNotEqual(uuid, "00000000-0000-0000-0000-000000000000")

        self.assert_nm({'vx0': '''[connection]
id=netplan-vx0
type=vxlan
interface-name=vx0

[vxlan]
id=42
parent=%s

[ipv4]
method=disabled

[ipv6]
method=ignore\n''' % uuid,
                       'id0': '''[connection]
id=netplan-id0
type=ethernet
uuid=%s
interface-name=someIface

[ethernet]
wake-on-lan=0

[ipv4]
method=link-local

[ipv6]
method=ignore\n''' % uuid})

    def test_wireguard_with_private_key_flags(self):
        self.generate('''network:
  version: 2
  tunnels:
    wg-tunnel:
      renderer: NetworkManager
      addresses:
      - "10.20.30.1/24"
      ipv6-address-generation: "stable-privacy"
      mode: "wireguard"
      peers:
      - endpoint: "10.20.30.40:51820"
        keys:
          public: "M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4="
        allowed-ips:
        - "0.0.0.0/0"
      keys:
        private-key-flags:
        - agent-owned
        - not-saved
        - not-required''')

        self.assert_nm({'wg-tunnel': '''[connection]
id=netplan-wg-tunnel
type=wireguard
interface-name=wg-tunnel

[wireguard]
private-key-flags=7

[wireguard-peer.M9nt4YujIOmNrRmpIRTmYSfMdrpvE7u6WkG8FY8WjG4=]
endpoint=10.20.30.40:51820
allowed-ips=0.0.0.0/0;

[ipv4]
method=manual
address1=10.20.30.1/24

[ipv6]
method=manual
addr-gen-mode=1
ip6-privacy=0
'''})


class TestConfigErrors(TestBase):

    def test_missing_mode(self):
        """Fail if tunnel mode is missing"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      remote: 20.20.20.20
      local: 10.10.10.10
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: missing or invalid 'mode' property for tunnel", out)

    def test_invalid_mode(self):
        """Ensure an invalid tunnel mode shows an error message"""
        config = prepare_config_for_mode('networkd', 'invalid')
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: tunnel mode 'invalid' is not supported", out)

    def test_malformed_tunnel_ip(self):
        """Fail if local/remote IP for tunnel are malformed"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      mode: gre
      remote: 20.20.20.20
      local: 10.10.1invalid
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: malformed address '10.10.1invalid', must be X.X.X.X or X:X:X:X:X:X:X:X", out)

    def test_cidr_tunnel_ip(self):
        """Fail if local/remote IP for tunnel include /prefix"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      mode: gre
      remote: 20.20.20.20
      local: 10.10.10.10/21
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: address '10.10.10.10/21' should not include /prefixlength", out)

    def test_missing_remote_ip(self):
        """Fail if remote IP is missing"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      mode: gre
      local: 20.20.20.20
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: missing 'remote' property for tunnel", out)

    def test_invalid_ttl(self):
        """Fail if TTL not in range [1...255]"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      mode: ipip
      local: 20.20.20.20
      remote: 10.10.10.10
      ttl: 300
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: 'ttl' property for tunnel must be in range [1...255]", out)

    def test_wrong_local_ip_for_mode_v4(self):
        """Show an error when an IPv6 local addr is used for an IPv4 tunnel mode"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      mode: gre
      local: fe80::2
      remote: 20.20.20.20
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: 'local' must be a valid IPv4 address for this tunnel type", out)

    def test_wrong_remote_ip_for_mode_v4(self):
        """Show an error when an IPv6 remote addr is used for an IPv4 tunnel mode"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      mode: gre
      local: 10.10.10.10
      remote: 2006::1
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: 'remote' must be a valid IPv4 address for this tunnel type", out)

    def test_wrong_local_ip_for_mode_v6(self):
        """Show an error when an IPv4 local addr is used for an IPv6 tunnel mode"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      mode: ip6gre
      local: 10.10.10.10
      remote: 2001::3
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: 'local' must be a valid IPv6 address for this tunnel type", out)

    def test_wrong_remote_ip_for_mode_v6(self):
        """Show an error when an IPv4 remote addr is used for an IPv6 tunnel mode"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      mode: ip6gre
      local: 2001::face
      remote: 20.20.20.20
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: 'remote' must be a valid IPv6 address for this tunnel type", out)

    def test_malformed_keys(self):
        """Show an error if tunnel keys stanza is malformed"""
        config = '''network:
  version: 2
  tunnels:
    tun0:
      mode: ipip
      local: 10.10.10.10
      remote: 20.20.20.20
      keys:
        - input: 1234
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: invalid type for 'key[s]': must be a scalar or mapping", out)

    def test_networkd_invalid_input_key_use(self):
        """[networkd] Show an error if input-key is used for a mode that does not support it"""
        config = '''network:
  version: 2
  renderer: networkd
  tunnels:
    tun0:
      mode: ipip
      local: 10.10.10.10
      remote: 20.20.20.20
      keys:
        input: 1234
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: 'input-key' is not required for this tunnel type", out)

    def test_networkd_invalid_output_key_use(self):
        """[networkd] Show an error if output-key is used for a mode that does not support it"""
        config = '''network:
  version: 2
  renderer: networkd
  tunnels:
    tun0:
      mode: ipip
      local: 10.10.10.10
      remote: 20.20.20.20
      keys:
        output: 1234
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: 'output-key' is not required for this tunnel type", out)

    def test_nm_invalid_input_key_use(self):
        """[NetworkManager] Show an error if input-key is used for a mode that does not support it"""
        config = '''network:
  version: 2
  renderer: NetworkManager
  tunnels:
    tun0:
      mode: ipip
      local: 10.10.10.10
      remote: 20.20.20.20
      keys:
        input: 1234
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: 'input-key' is not required for this tunnel type", out)

    def test_nm_invalid_output_key_use(self):
        """[NetworkManager] Show an error if output-key is used for a mode that does not support it"""
        config = '''network:
  version: 2
  renderer: NetworkManager
  tunnels:
    tun0:
      mode: ipip
      local: 10.10.10.10
      remote: 20.20.20.20
      keys:
        output: 1234
'''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: tun0: 'output-key' is not required for this tunnel type", out)

    def test_vxlan_eth_with_route(self):
        """[networkd] Validate that VXLAN= is in the right section (LP#2000713)"""
        config = '''network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      routes:
        - to: 10.20.30.40/32
          via: 10.20.30.1
  tunnels:
    vxlan1:
      mode: vxlan
      id: 1
      link: eth0
'''
        self.generate(config)
        self.assert_networkd({'eth0.network': '''[Match]
Name=eth0

[Network]
LinkLocalAddressing=ipv6
VXLAN=vxlan1

[Route]
Destination=10.20.30.40/32
Gateway=10.20.30.1
''',
                              'vxlan1.netdev': (ND_VXLAN % ('vxlan1', 1)).strip(),
                              'vxlan1.network': ND_EMPTY % ('vxlan1', 'ipv6')})

    def test_wireguard_wrong_private_key_flag(self):
        config = '''network:
  version: 2
  tunnels:
    wg-tunnel:
      renderer: NetworkManager
      mode: "wireguard"
      keys:
        private-key-flags:
        - agent-owned
        - not-required
        - it-doesnt-exist
        '''
        out = self.generate(config, expect_fail=True)
        self.assertIn("Error in network definition: Key flag 'it-doesnt-exist' is not supported.", out)
