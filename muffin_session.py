"""
    muffin-session description.

"""

# Package information
# ===================


import asyncio
import base64
import functools
import time

import ujson as json

from muffin import HTTPFound, HTTPException, Response
from muffin.plugins import BasePlugin
from muffin.utils import create_signature, check_signature, to_coroutine


__version__ = "0.0.5"
__project__ = "muffin-session"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


FUNC = lambda x: x # noqa

SESSION_KEY = 'session'


class Plugin(BasePlugin):

    """ Support sessions. """

    name = 'session'
    defaults = {
        'default_user_checker': lambda x: x,
        'login_url': '/login',
        'secret': 'InsecureSecret',
        'auto_load': False,
    }

    def setup(self, app):
        """ Initialize the application. """
        super().setup(app)

        if self.options['secret'] == 'InsecureSecret':
            app.logger.warn(
                'Use insecure secret key. Change SESSION_SECRET option in configuration.')

        self._user_loader = asyncio.coroutine(lambda id_: id_)

    @asyncio.coroutine
    def middleware_factory(self, app, handler):
        """ Provide session middleware. """
        @asyncio.coroutine
        def middleware(request):
            """ Load a session from users cookies. """
            if self.options.auto_load:
                yield from self.load(request)

            try:
                response = yield from handler(request)
                self.save(request, response)
                return response

            except HTTPException as response:
                self.save(request, response)
                raise

        return middleware

    def user_loader(self, func):
        """ Register a function as user loader. """
        self._user_loader = to_coroutine(func)
        return self._user_loader

    @asyncio.coroutine
    def load(self, request):
        """ Load session from cookies. """
        if SESSION_KEY not in request:
            session = Session(self.options['secret'])
            session.load(request.cookies)
            self.app.logger.debug('Session loaded: %s', session)
            request[SESSION_KEY] = request.session = session
        return request[SESSION_KEY]

    __call__ = load

    def save(self, request, response):
        if isinstance(response, Response) and SESSION_KEY in request and not response.started:
            session = request[SESSION_KEY]
            self.app.logger.debug('Session saved: %s', session)
            session.save(response.set_cookie)

    @asyncio.coroutine
    def load_user(self, request):
        """ Load user from request. """
        session = yield from self.load(request)
        if 'id' not in session:
            return None
        request.user = yield from self._user_loader(session['id'])
        return request.user

    @asyncio.coroutine
    def check_user(self, request, func=FUNC, location=None, **kwargs):
        """ Check for user is logged and pass func. """
        user = yield from self.load_user(request)
        func = func or self.options.default_user_checker
        if not func(user):
            raise HTTPFound(location or self.options.login_url, **kwargs)
        return user

    def user_pass(self, func=None, location=None, **rkwargs):
        def wrapper(view):
            view = to_coroutine(view)

            @asyncio.coroutine
            @functools.wraps(view)
            def handler(request, *args, **kwargs):
                yield from self.check_user(request, func, location, **rkwargs)
                return (yield from view(request, *args, **kwargs))
            return handler

        return wrapper

    @asyncio.coroutine
    def login(self, request, id):
        """ Login an user by ID. """
        session = yield from self.load(request)
        session['id'] = id

    @asyncio.coroutine
    def logout(self, request):
        """ Logout an user. """
        session = yield from self.load(request)
        del session['id']


class Session(dict):

    encoding = 'utf-8'

    def __init__(self, secret, key='session.id', **params):
        self.secret = secret.encode(self.encoding)
        self.key = key
        self.params = params
        self.store = {}

    def save(self, set_cookie):
        if set(self.store.items()) ^ set(self.items()):
            value = dict(self.items())
            value = json.dumps(value)
            value = self.encrypt(value)
            if not isinstance(value, str):
                value = value.encode(self.encoding)
            set_cookie(self.key, value, **self.params)

    def __setitem__(self, name, value):
        if isinstance(value, (dict, list, tuple, set)):
            value = json.dumps(value)
        super().__setitem__(name, value)

    def load(self, cookies, **kwargs):
        value = cookies.get(self.key, None)
        if value is None:
            return False

        value = self.decrypt(value)
        if not value:
            return False

        data = json.loads(value)
        if not isinstance(data, dict):
            return False

        self.store = data
        self.update(self.store)

    def encrypt(self, value):
        timestamp = str(int(time.time()))
        value = base64.b64encode(value.encode(self.encoding))
        signature = create_signature(self.secret, value + timestamp.encode(),
                                     encoding=self.encoding)
        return "|".join([value.decode(self.encoding), timestamp, signature])

    def decrypt(self, value):
        value, timestamp, signature = value.split("|")
        if check_signature(signature, self.secret, value + timestamp, encoding=self.encoding):
            return base64.b64decode(value).decode(self.encoding)
        return 'null'
