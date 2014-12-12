##
# This file is part of agithub
# Originally created by Jonathan Paugh
#
# https://github.com/jpaugh/agithub
#
# Copyright 2012 Jonathan Paugh
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
##
"""
This module contains Rest api utilities,
Mainly the RestClient, which you can use to easily pythonify a rest api.

based on https://github.com/jpaugh/agithub/commit/1e2575825b165c1cb7cbd85c22e2561fc4d434d3

@author: Jonathan Paugh
@author: Jens Timmerman
"""
import base64
import urllib
import urllib2
try:
    import json
except ImportError:
    import simplejson as json

from vsc.utils import fancylogger

try:
    from functools import partial
except ImportError:
    from vsc.utils.missing import partial


class Client(object):
    """An implementation of a REST client"""
    DELETE = 'DELETE'
    GET = 'GET'
    HEAD = 'HEAD'
    PATCH = 'PATCH'
    POST = 'POST'
    PUT = 'PUT'

    HTTP_METHODS = (
        DELETE,
        GET,
        HEAD,
        PATCH,
        POST,
        PUT,
    )

    USER_AGENT = 'vsc-rest-client'

    def __init__(self, url, username=None, password=None, token=None, token_type='Token', user_agent=None, append_slash=False):
        """
        Create a Client object,
        this client can consume a REST api hosted at host/endpoint

        If a username is given a password or a token is required.
        You can not use a password and a token.
        token_type is the typoe fo th the authorization token text in the http authentication header, defaults to Token
        This should be set to 'Bearer' for certain OAuth implementations.
        """
        self.auth_header = None
        self.username = username
        self.url = url
        self.append_slash = append_slash

        if not user_agent:
            self.user_agent = self.USER_AGENT
        else:
            self.user_agent = user_agent

        handler = urllib2.HTTPSHandler()
        self.opener = urllib2.build_opener(handler)

        if username is not None:
            if password is None and token is None:
                raise TypeError("You need a password or an OAuth token to authenticate as " + username)
            if password is not None and token is not None:
                raise TypeError("You cannot use both password and OAuth token authenication")

        if password is not None:
            self.auth_header = self.hash_pass(password, username)
        elif token is not None:
            self.auth_header = '%s %s' % (token_type, token)

    def get(self, url, headers={}, **params):
        """
        Do a http get request on the given url with given headers and parameters
        Parameters is a dictionary that will will be urlencoded
        """
        if self.append_slash:
            url += '/'
        url += self.urlencode(params)
        return self.request(self.GET, url, None, headers)

    def head(self, url, headers={}, **params):
        """
        Do a http head request on the given url with given headers and parameters
        Parameters is a dictionary that will will be urlencoded
        """
        if self.append_slash:
            url += '/'
        url += self.urlencode(params)
        return self.request(self.HEAD, url, None, headers)

    def delete(self, url, headers={}, **params):
        """
        Do a http delete request on the given url with given headers and parameters
        Parameters is a dictionary that will will be urlencoded
        """
        if self.append_slash:
            url += '/'
        url += self.urlencode(params)
        return self.request(self.DELETE, url, None, headers)

    def post(self, url, body=None, headers={}, **params):
        """
        Do a http post request on the given url with given body, headers and parameters
        Parameters is a dictionary that will will be urlencoded
        """
        if self.append_slash:
            url += '/'
        url += self.urlencode(params)
        headers['Content-Type'] = 'application/json'
        return self.request(self.POST, url, json.dumps(body), headers)

    def put(self, url, body=None, headers={}, **params):
        """
        Do a http put request on the given url with given body, headers and parameters
        Parameters is a dictionary that will will be urlencoded
        """
        if self.append_slash:
            url += '/'
        url += self.urlencode(params)
        headers['Content-Type'] = 'application/json'
        return self.request(self.PUT, url, json.dumps(body), headers)

    def patch(self, url, body=None, headers={}, **params):
        """
        Do a http patch request on the given url with given body, headers and parameters
        Parameters is a dictionary that will will be urlencoded
        """
        if self.append_slash:
            url += '/'
        url += self.urlencode(params)
        headers['Content-Type'] = 'application/json'
        return self.request(self.PATCH, url, json.dumps(body), headers)

    def request(self, method, url, body, headers):
        if self.auth_header is not None:
            headers['Authorization'] = self.auth_header
        headers['User-Agent'] = self.user_agent
        fancylogger.getLogger().debug('cli request: %s, %s, %s, %s', method, url, body, headers)
        #TODO: in recent python: Context manager
        conn = self.get_connection(method, url, body, headers)
        status = conn.code
        body = conn.read()
        try:
            pybody = json.loads(body)
        except ValueError:
            pybody = body
        fancylogger.getLogger().debug('reponse len: %s ', len(pybody))
        conn.close()
        return status, pybody

    def urlencode(self, params):
        if not params:
            return ''
        return '?' + urllib.urlencode(params)

    def hash_pass(self, password, username=None):
        if not username:
            username = self.username
        return 'Basic ' + base64.b64encode('%s:%s' % (username, password)).strip()

    def get_connection(self, method, url, body, headers):
        if not self.url.endswith('/') and not url.startswith('/'):
            sep = '/'
        else:
            sep = ''
        request = urllib2.Request(self.url + sep + url, data=body)
        for header, value in headers.iteritems():
            request.add_header(header, value)
        request.get_method = lambda: method
        fancylogger.getLogger().debug('opening request:  %s%s%s', self.url, sep, url)
        connection = self.opener.open(request)
        return connection


class RequestBuilder(object):
    '''RequestBuilder(client).path.to.resource.method(...)
        stands for
    RequestBuilder(client).client.method('path/to/resource, ...)

    Also, if you use an invalid path, too bad. Just be ready to catch a
    You can use item access instead of attribute access. This is
    convenient for using variables' values and required for numbers.
    bad status from github.com. (Or maybe an httplib.error...)

    To understand the method(...) calls, check out github.client.Client.
    '''
    def __init__(self, client):
        """Constructor"""
        self.client = client
        self.url = ''

    def __getattr__(self, key):
        """
        Overwrite __getattr__ to build up the equest url
        this enables us to do bla.some.path['something']
        and get the url bla/some/path/something
        """
        # make sure key is a string
        key = str(key)
        # our methods are lowercase, but our HTTP_METHOD constants are upercase, so check if it is in there, but only
        # if it was a lowercase key
        # this is here so bla.something.get() should work, and not result in bla/something/get being returned
        if key.upper() in self.client.HTTP_METHODS and [x for x in key if x.islower()]:
            mfun = getattr(self.client, key)
            fun = partial(mfun, url=self.url)
            return fun
        self.url += '/' + key
        return self

    __getitem__ = __getattr__

    def __str__(self):
        '''If you ever stringify this, you've (probably) messed up
        somewhere. So let's give a semi-helpful message.
        '''
        return "I don't know about %s, You probably want to do a get or other http request, use .get()" % self.url

    def __repr__(self):
        return '%s: %s' % (self.__class__, self.url)


class RestClient(object):
    """
    A client with a request builder, so you can easily create rest requests
    e.g. to create a github Rest API client just do
    >>> g = RestClient('https://api.github.com', username='user', password='pass')
    >>> g = RestClient('https://api.github.com', token='oauth token')
    >>> status, data = g.issues.get(filter='subscribed')
    >>> data
    ... [ list_, of, stuff ]
    >>> status, data = g.repos.jpaugh64.repla.issues[1].get()
    >>> data
    ... { 'dict': 'my issue data', }
    >>> name, repo = 'jpaugh64', 'repla'
    >>> status, data = g.repos[name][repo].issues[1].get()
    ... same thing
    >>> status, data = g.funny.I.donna.remember.that.one.get()
    >>> status
    ... 404

    That's all there is to it. (blah.post() should work, too.)

    NOTE: It is up to you to spell things correctly. Github doesn't even
    try to validate the url you feed it. On the other hand, it
    automatically supports the full API--so why should you care?
    """
    def __init__(self, *args, **kwargs):
        """We create a client with the given arguments"""
        self.client = Client(*args, **kwargs)

    def __getattr__(self, key):
        """Get an attribute, we will build a request with it"""
        return RequestBuilder(self.client).__getattr__(key)
