# -*- coding: utf-8; -*-
#
# This file is part of Superdesk.
#
# Copyright 2013, 2014 Sourcefabric z.u. and contributors.
#
# For the full copyright and license information, please see the
# AUTHORS and LICENSE files distributed with this source code, or
# at https://www.sourcefabric.org/superdesk/license


import os
import json
import unittest
import requests

from superdesk.publish import SUBSCRIBER_TYPES
from superdesk.publish.transmitters.http_push import HTTPPushService

from unittest import mock
from unittest.mock import Mock
from superdesk.errors import PublishHTTPPushServerError, PublishHTTPPushClientError


def get_fixture(fixture):
    filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), '%s.json' % fixture)
    with open(filename, 'r') as file:
        return json.load(file)


class ItemNotFound(Exception):
    pass


class NotFoundResponse():
    status_code = 404


class CreatedResponse():
    status_code = 201


class HTTPPushPublishTestCase(unittest.TestCase):

    def setUp(self):
        if 'HTTP_PUSH_RESOURCE_URL' not in os.environ:
            self.resource_url = ''
        else:
            self.resource_url = os.environ['HTTP_PUSH_RESOURCE_URL']

        self.subscribers = [{"_id": "1", "name": "Test", "media_type": "media",
                             "subscriber_type": SUBSCRIBER_TYPES.DIGITAL, "is_active": True,
                             "sequence_num_settings": {"max": 10, "min": 1},
                             "destinations": [{"name": "test", "delivery_type": "http_push", "format": "ninjs",
                                               "config": {"resource_url": self.resource_url}
                                               }]}]
        self.formatted_item1 = {"_id": "item1",
                                "headline": "headline",
                                "versioncreated": "2015-03-09T16:32:23",
                                "version": 1
                                }
        self.formatted_item2 = {"_id": "item1",
                                "headline": "headline2",
                                "versioncreated": "2015-03-21T13:43:51",
                                "version": 2
                                }
        self.item = {'item_id': 'item1',
                     'format': 'ninjs',
                     'item_version': 1,
                     'published_seq_num': 1,
                     'formatted_item': json.dumps(self.formatted_item1),
                     'destination': {"name": "test", "delivery_type": "http_push", "format": "ninjs",
                                     "config": {"resource_url": self.resource_url}
                                     }}

        self.destination = self.item.get('destination', {})

    def is_item_published(self, item_id):
        """Return True if the item was published, False otherwise.

        Raises Exception in case of server/communication error.
        """
        if not getattr(self, 'resource_url', None):
            return

        response = requests.get(self.getItemURL(item_id))
        if response.status_code == requests.codes.not_found:  # @UndefinedVariable
            return False
        self.assertEqual(response.status_code, requests.codes.ok,  # @UndefinedVariable
                         'Error retrieving item from the content API')
        return True

    def getItemURL(self, item_id):
        """Returns the URL for item read

        @param item_id: the item identifier
        @return: string
        """
        return '%s/%s' % (self.resource_url, item_id)

    def test_get_assets_url(self):
        service = HTTPPushService()
        self.assertEqual(service._get_assets_url(self.destination), None)

    def test_get_resource_url(self):
        service = HTTPPushService()
        self.assertEqual(service._get_resource_url(self.destination), self.resource_url)

    def test_publish_an_item(self):
        if not getattr(self, 'resource_url', None):
            return

        service = HTTPPushService()

        service._transmit(self.item, self.subscribers)
        self.assertTrue(self.is_item_published(self.item['item_id']))

        self.item['formatted_item'] = json.dumps(self.formatted_item2)
        service._transmit(self.item, self.subscribers)
        item = requests.get(self.getItemURL(self.item['item_id'])).json()
        self.assertEqual(item['headline'], 'headline2')
        self.assertEqual(item['version'], 2)

    @mock.patch('superdesk.errors.notifiers')
    @mock.patch('requests.post')
    def test_client_publish_error_thrown(self, fake_post, fake_notifiers):
        raise_http_exception = Mock(side_effect=PublishHTTPPushClientError.httpPushError(Exception('client 4xx')))

        fake_post.return_value = Mock(status_code=401, text='client 4xx', raise_for_status=raise_http_exception)

        # needed for bad exception handling classes
        fake_notifiers.return_value = []

        service = HTTPPushService()

        with self.assertRaises(PublishHTTPPushClientError):
            service._push_item(self.destination, json.dumps(self.item))

    @mock.patch('superdesk.errors.notifiers')
    @mock.patch('requests.post')
    def test_server_publish_error_thrown(self, fake_post, fake_notifiers):
        raise_http_exception = Mock(side_effect=PublishHTTPPushServerError.httpPushError(Exception('server 5xx')))

        fake_post.return_value = Mock(status_code=503, text='server 5xx', raise_for_status=raise_http_exception)

        # needed for bad exception handling classes
        fake_notifiers.return_value = []

        service = HTTPPushService()

        with self.assertRaises(PublishHTTPPushServerError):
            service._push_item(self.destination, json.dumps(self.item))

    @mock.patch('superdesk.publish.transmitters.http_push.app')
    @mock.patch('requests.post', return_value=CreatedResponse)
    @mock.patch('requests.get', return_value=NotFoundResponse)
    def test_push_associated_assets(self, get_mock, post_mock, app_mock):
        app_mock.media.get.return_value = 'bin'

        dest = {'config': {'assets_url': 'http://example.com'}}
        item = get_fixture('package')

        service = HTTPPushService()
        service._copy_published_media_files({}, dest)

        get_mock.assert_not_called()
        post_mock.assert_not_called()

        service._copy_published_media_files(item, dest)

        images = [
            # embedded original
            '2017020111028/9a836848c3c3387a151dbed96e83b7d50e6b0e71ca397e0b1dc0f4b2f4127acd.jpg',
            # main-0 original
            '20170201110216/d3ad29bafe0710c42b7cfc201939f266c6ca5c11a713625388decff4da87ba5b.jpg',
            # embedded thumbnail
            '2017020111028/a0502320d6d07dd921253171e971943adf791eb2b34dfe82da73c053a343a7c2.jpg',
        ]

        for media in images:
            get_mock.assert_any_call('http://example.com/%s' % media)
            post_mock.assert_any_call('http://example.com',
                                      files={'media': (media, app_mock.media.get.return_value, 'image/jpeg')},
                                      data={'media_id': media})

    @mock.patch('superdesk.publish.transmitters.http_push.app')
    @mock.patch('requests.post', return_value=CreatedResponse)
    @mock.patch('requests.get', return_value=NotFoundResponse)
    def test_push_attachments(self, get_mock, post_mock, app_mock):
        app_mock.media.get.return_value = 'bin'

        dest = {'config': {'assets_url': 'http://example.com'}}
        item = {
            'type': 'text',
            'attachments': [
                {'id': 'foo', 'media': 'media-id', 'mimetype': 'text/plain'},
            ]
        }

        service = HTTPPushService()
        service._copy_published_media_files(item, dest)

        app_mock.media.get.assert_called_with('media-id', resource='attachments')
        get_mock.assert_called_with('http://example.com/media-id')
        post_mock.assert_called_with(
            'http://example.com',
            files={'media': ('media-id', app_mock.media.get.return_value, 'text/plain')},
            data={'media_id': 'media-id'})
