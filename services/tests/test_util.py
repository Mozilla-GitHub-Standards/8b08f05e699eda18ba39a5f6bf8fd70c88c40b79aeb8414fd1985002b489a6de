# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Sync Server
#
# The Initial Developer of the Original Code is the Mozilla Foundation.
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Tarek Ziade (tarek@mozilla.com)
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****
import unittest
import time
import tempfile
import os
import urllib2
import socket

from webob.exc import HTTPServiceUnavailable

from services.util import (convert_config, bigint2time,
                           time2bigint, valid_email, batch,
                           validate_password, ssha, ssha256,
                           valid_password, json_response,
                           newlines_response, whoisi_response, text_response,
                           extract_username, get_url, proxy)


_EXTRA = """\
[some]
stuff = True

[other]
thing = ok
"""


class TestUtil(unittest.TestCase):

    def setUp(self):
        self.oldopen = urllib2.urlopen
        urllib2.urlopen = self._urlopen

    def tearDown(self):
        urllib2.urlopen = self.oldopen

    def _urlopen(self, req, timeout=None):
        # mimics urlopen
        class FakeResult(object):
            headers = {}
            body = '{}'

            def getcode(self):
                return 200

            def read(self):
                return self.body

        url = req.get_full_url()
        if url == 'impossible url':
            raise ValueError()
        if url == 'http://dwqkndwqpihqdw.com':
            msg = 'Name or service not known'
            raise urllib2.URLError(socket.gaierror(-2, msg))
        if url == 'http://google.com':
            return FakeResult()
        if url == 'http://badauth':
            raise urllib2.HTTPError(url, 401, '', {}, None)
        if url == 'http://goodauth':
            return FakeResult()
        if url == 'http://timeout':
            raise urllib2.URLError(socket.timeout())
        if url == 'http://error':
            raise urllib2.HTTPError(url, 500, 'Error', {}, None)
        if url == 'http://newplace':
            res = FakeResult()
            res.body = url + ' ' + req.headers['Authorization']
            return res

        raise ValueError(url)

    def test_convert_config(self):
        config = {'one': '1', 'two': 'bla', 'three': 'false'}
        config = convert_config(config)

        self.assertTrue(config['one'])
        self.assertEqual(config['two'], 'bla')
        self.assertFalse(config['three'])

        # config also reads extra config files.
        __, filename = tempfile.mkstemp()
        try:
            with open(filename, 'w') as f:
                f.write(_EXTRA)

            config = {'one': '1', 'two': 'file:%s' % filename}
            config = convert_config(config)
            self.assertTrue(config['some.stuff'])
            self.assertEquals(config['other.thing'], 'ok')
        finally:
            os.remove(filename)

    def test_bigint2time(self):
        self.assertEquals(bigint2time(None), None)

    def test_time2bigint(self):
        now = time.time()
        self.assertAlmostEqual(bigint2time(time2bigint(now)), now, places=1)

    def test_valid_email(self):
        self.assertFalse(valid_email('tarek'))
        self.assertFalse(valid_email('tarek@moz'))
        self.assertFalse(valid_email('tarek@192.12.32334.3'))

        self.assertTrue(valid_email('tarek@mozilla.com'))
        self.assertTrue(valid_email('tarek+sync@mozilla.com'))
        self.assertTrue(valid_email('tarek@127.0.0.1'))

    def test_batch(self):
        self.assertEquals(len(list(batch(range(250)))), 3)
        self.assertEquals(len(list(batch(range(190)))), 2)
        self.assertEquals(len(list(batch(range(24, 25)))), 1)

    def test_validate_password(self):
        one = ssha('one')
        two = ssha256('two')
        self.assertTrue(validate_password('one', one))
        self.assertTrue(validate_password('two', two))

    def test_valid_password(self):
        self.assertFalse(valid_password('tarek', 'xx'))
        self.assertFalse(valid_password('t' * 8, 't' * 8))
        self.assertTrue(valid_password('tarek', 't' * 8))

    def test_response_conversions(self):
        data = {'some': 'data'}
        resp = text_response(data)
        self.assertEquals(resp.body, "{'some': 'data'}")
        self.assertEquals(resp.content_type, 'text/plain')

        data = "abc"
        resp = whoisi_response(data)
        self.assertEquals(resp.body,
                '\x00\x00\x00\x03"a"\x00\x00\x00\x03"b"\x00\x00\x00\x03"c"')
        self.assertEquals(resp.content_type, 'application/whoisi')

        resp = newlines_response(data)
        self.assertEquals(resp.body, '"a"\n"b"\n"c"\n')
        self.assertEquals(resp.content_type, 'application/newlines')

        data = {'some': 'data'}
        resp = json_response(data)
        self.assertEquals(resp.body, '{"some": "data"}')
        self.assertEquals(resp.content_type, 'application/json')

    def test_extract_username(self):
        self.assertEquals(extract_username('username'), 'username')
        self.assertEquals(extract_username('test@test.com'),
                          'u2wqblarhim5su7pxemcbwdyryrghmuk')

    def test_get_url(self):

        # malformed url
        self.assertRaises(ValueError, get_url, 'impossible url')

        # unknown location
        code, headers, body = get_url('http://dwqkndwqpihqdw.com',
                                      get_body=False)
        self.assertEquals(code, 502)
        self.assertTrue('Name or service not known' in body)

        # any page
        code, headers, body = get_url('http://google.com', get_body=False)
        self.assertEquals(code, 200)
        self.assertEquals(body, '')

        # page with auth failure
        code, headers, body = get_url('http://badauth',
                                      user='tarek',
                                      password='xxxx')
        self.assertEquals(code, 401)

        # page with right auth
        code, headers, body = get_url('http://goodauth',
                                      user='tarek',
                                      password='passat76')
        self.assertEquals(code, 200)
        self.assertEquals(body, '{}')

        # page that times out
        code, headers, body = get_url('http://timeout', timeout=0.1)
        self.assertEquals(code, 504)

        # page that fails
        code, headers, body = get_url('http://error', get_body=False)
        self.assertEquals(code, 500)
        self.assertTrue('Error' in body)

    def test_proxy(self):
        class FakeRequest(object):
            url = 'http://locahost'
            method = 'GET'
            body = 'xxx'
            headers = {'Content-Length': 3}
            remote_addr = '192.168.1.1'
            _authorization = 'Basic SomeToken'

        request = FakeRequest()
        response = proxy(request, 'http', 'newplace')
        self.assertEqual(response.content_length, 31)
        self.assertEqual(response.body, 'http://newplace Basic SomeToken')
