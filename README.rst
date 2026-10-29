Muffin-Session
##############

**Muffin-Session** — Cookie-based HTTP sessions for the Muffin_ framework.

.. image:: https://github.com/klen/muffin-session/workflows/tests/badge.svg
    :target: https://github.com/klen/muffin-session/actions
    :alt: Test Status

.. image:: https://img.shields.io/pypi/v/muffin-session
    :target: https://pypi.org/project/muffin-session/
    :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/muffin-session
    :target: https://pypi.org/project/muffin-session/
    :alt: Supported Python Versions

.. contents::
   :local:

Overview
========

**Muffin-Session** provides a simple and flexible way to manage session data via cookies.
It integrates into Muffin applications with support for JWT-signed, Fernet-encrypted and
plain base64-encoded sessions.

Features
--------

- 🍪 Cookie-based session management
- 🔐 Three session backends:
  - **JWT**-signed sessions (default)
  - **Fernet**-encrypted sessions
  - Plain base64-encoded sessions (no signature, no encryption)
- 🧠 User loader & login utilities
- 🧩 Optional auto-managed middleware integration

Requirements
============

- Python ≥ 3.11
- Muffin 3
- Optional: `cryptography` for Fernet sessions

Installation
============

Install via pip:

.. code-block:: bash

    pip install muffin-session

Install with Fernet encryption support:

.. code-block:: bash

    pip install muffin-session[fernet]

Usage
=====

Manual integration
------------------

The session is loaded from the request explicitly and has to be saved to the response
explicitly. Calling ``login``/``logout`` alone does not send a cookie — pass ``response=``
(or call ``save_to_response`` yourself) to write it.

.. code-block:: python

    from muffin import Application, ResponseHTML
    from muffin_session import Plugin as Session

    app = Application('example')

    session = Session(app, secret_key='REALLY_SECRET_KEY')

    @app.route('/update')
    async def update(request):
        ses = session.load_from_request(request)
        ses['var'] = 'value'
        response = ResponseHTML('Session updated.')
        session.save_to_response(ses, response)
        return response

    @app.route('/load')
    async def load(request):
        ses = session.load_from_request(request)
        return {'var': ses.get('var')}

Auto-managed sessions
---------------------

With ``auto_manage=True`` the plugin installs a middleware: the session is available as
``request.session`` in every view, and is written back to the response cookie whenever it
was modified.

.. code-block:: python

    from muffin import Application
    from muffin_session import Plugin as Session

    app = Application('example')

    session = Session(app, secret_key='REALLY_SECRET_KEY', auto_manage=True)

    @app.route('/update')
    async def update(request):
        request.session['var'] = 'value'
        return 'Session updated.'

    @app.route('/load')
    async def load(request):
        return request.session.get('var')

Configuration
=============

You can pass options via ``session.setup(...)`` or set them in your application config using the
``SESSION_`` prefix:

.. code-block:: python

    SESSION_SECRET_KEY = 'REALLY_SECRET_KEY'
    SESSION_COOKIE_NAME = 'muffin_session'
    SESSION_COOKIE_PARAMS = {'path': '/', 'samesite': 'lax', 'secure': True}

Available Options
-----------------

=========================== ================================ ==========================================================
Option                      Default                          Description
=========================== ================================ ==========================================================
**session_type**            ``"jwt"``                        Backend type: ``"jwt"``, ``"fernet"``, or ``"base64"``
**secret_key**              ``"InsecureSecret"``             Secret used to sign or encrypt sessions
**auto_manage**             ``False``                        If enabled, session is auto-loaded into ``request.session``
**cookie_name**             ``"session"``                    Name of the session cookie
**cookie_params**           see `Cookie parameters`_         Cookie options: path, max-age, samesite, secure
**default_user_checker**    ``lambda x: x``                  Predicate applied to the user loaded for the session
**login_url**               ``"/login"``                     Redirect URL or callable for unauthenticated users
**redirect_type**           ``ResponseRedirect``             Response class raised to redirect unauthenticated users
=========================== ================================ ==========================================================

``redirect_type`` must be a response class accepting ``(location, **response_params)``. The default
``ResponseRedirect`` answers with ``307`` and an empty body. Use
``muffin_session.ResponseHTMLRedirect`` instead when the redirect has to keep cookies set by the
same response (e.g. behind clients that drop ``Set-Cookie`` on redirects): it renders an HTML page
with a meta refresh and a link, and stores the target in the ``location`` header.

Session backends
----------------

================= ===================================================== ==========================================
``session_type``  Payload                                               Requires
================= ===================================================== ==========================================
``"jwt"``         JSON, signed with ``secret_key`` (HS256)              ``pyjwt``, a required dependency
``"fernet"``      JSON, encrypted with a key derived from               ``cryptography``
                  ``secret_key``                                        (``muffin-session[fernet]``)
``"base64"``      JSON, base64url-encoded, neither signed nor           nothing
                  encrypted
================= ===================================================== ==========================================

- ``"jwt"`` is the default. The client can read the payload but cannot change it without
  invalidating the signature. With JWT, use a random secret of at least 32 bytes: PyJWT warns
  about shorter HMAC keys (RFC 7518).
- ``"fernet"`` hides the payload as well. The secret is truncated/padded to 32 characters by
  ``asgi-sessions``. Without ``cryptography``, creating a Fernet session raises
  ``RuntimeError: Install cryptography package to use fernet sessions.``
- ``"base64"`` offers no integrity protection: a client can read and modify its own session
  contents. Any value other than ``"jwt"``/``"fernet"`` falls back to this backend.

.. warning::

    ``secret_key`` defaults to ``"InsecureSecret"`` and is only meant to make a development setup
    start. The plugin logs a warning on startup when it is left unchanged. Always set
    ``SESSION_SECRET_KEY`` to a long random value in production — anyone knowing it can forge
    (JWT) or decrypt/decode (Fernet, base64) session cookies.

Cookie parameters
-----------------

``cookie_params`` is a dict passed to the ``Set-Cookie`` header. Its defaults:

============= =========== ==========================================================================
Key           Default     Description
============= =========== ==========================================================================
``path``      ``"/"``     Cookie path scope.
``max-age``   ``None``    Lifetime in seconds. ``None`` means no ``Max-Age`` attribute, so the cookie
                          lives until the browser session ends. Set e.g. ``14 * 24 * 3600`` to keep
                          users logged in across browser restarts.
``samesite``  ``"lax"``   CSRF protection. ``"lax"`` blocks cross-site POSTs while keeping top-level
                          navigation working. Use ``"strict"`` when no cross-site flows exist.
                          ``"none"`` requires ``secure=True``.
``secure``    ``False``   Send the cookie over HTTPS only.
============= =========== ==========================================================================

.. warning::

    The defaults are not production-safe. Enable ``secure`` and keep ``samesite`` at ``"lax"`` or
    ``"strict"`` in production:

    .. code-block:: python

        SESSION_COOKIE_PARAMS = {'path': '/', 'samesite': 'lax', 'secure': True}

    The whole dict is replaced by this option, so list every key you want to keep.

API
===

``user_loader(func)``
    Decorator registering the function used to load a user by the ID stored in the session.
    It receives ``session["id"]`` and may be a coroutine. Returns the user object (or ``None``).

``load_from_request(request)``
    Return the session for the request, creating it from the session cookie (or empty). The
    result is cached in ``request["session"]``, so repeated calls return the same object.

``create_from_token(token=None)``
    Build a session object from a raw cookie value using the configured ``session_type``.

``save_to_response(obj, response, **changes)``
    Store ``**changes`` into the session and write its ``Set-Cookie`` header to ``response``.
    ``obj`` may be a ``Session`` or a ``Request`` (the session is loaded from it). A non-Response
    value is converted with ``asgi_tools.response.parse_response``. Returns the response.

``async load_user(request)``
    Return the user for the current session by calling the registered user loader with
    ``session["id"]``, or ``None`` when the session has no ``id``. The result is cached in
    ``request["user"]``; in views covered by ``user_pass`` it is available as ``request.user``.

``async check_user(request, checker=None, location=None, **response_params)``
    Raise a redirect (or an error) unless the loaded user passes ``checker``. ``checker``
    defaults to ``default_user_checker`` and must be a synchronous predicate returning a truthy
    value for allowed users. It is called with the user loaded for the session, or with ``None``
    for anonymous requests, so custom checkers have to accept ``None``:
    ``lambda user: bool(user and user.is_admin)``. ``default_user_checker`` is ``lambda x: x``,
    i.e. "any loaded user".
    ``location`` may be a URL string, a callable returning a URL (sync or async), or a
    ``ResponseError`` instance to raise as is. Other keyword arguments are forwarded to
    ``redirect_type``. Returns the user when the check passes.

``user_pass(checker=None, location=None, **rkwargs)``
    Route decorator wrapping ``check_user``. Example:
    ``@session.user_pass(lambda user: user.is_admin)``. Without a checker it only requires a
    logged-in user.

``login(request, ident, *, response=None)``
    Put ``ident`` into the session as ``id``. The cookie is written only when ``response`` is
    given, in which case the response is returned.

``logout(request, *, response=None)``
    Remove ``id`` from the session. As with ``login``, pass ``response=`` to write the cookie.

``request.session`` (``auto_manage=True``)
    The session dict loaded by the middleware. Mutations are saved automatically when the view
    returns a ``Response``.

``ResponseHTMLRedirect``
    Alternative ``redirect_type`` rendering an HTML redirect (see `Available Options`_).

Example
=======

.. code-block:: python

    from muffin import Application, ResponseHTML
    from muffin_session import Plugin as Session

    app = Application('example')
    session = Session(app, secret_key='REALLY_SECRET_KEY', auto_manage=True)

    @session.user_loader
    async def load_user(user_id):
        return await db.get_user_by_id(user_id)

    @app.route('/session')
    async def get_session(request):
        return dict(request.session)

    @app.route('/admin')
    @session.user_pass(lambda user: bool(user and user.is_admin))
    async def admin(request):
        return 'Top secret admin page.'

    @app.route('/login')
    async def login(request):
        user = await authenticate(request)
        session.login(request, user.id)
        return 'Logged in.'

    @app.route('/logout')
    async def logout(request):
        session.logout(request)
        return 'Logged out.'

    @app.route('/clear')
    async def clear(request):
        request.session.clear()
        return 'Session cleared.'

Bug Tracker
===========

Found a bug or want to propose a feature?
Please use the issue tracker at: https://github.com/klen/muffin-session/issues

Contributing
============

Want to contribute? PRs are welcome!
Development happens at: https://github.com/klen/muffin-session

License
=======

This project is licensed under the MIT license. See `MIT license`_ for details.

Author
======

- Kirill Klenov (`klen`_) — https://github.com/klen

.. _klen: https://github.com/klen
.. _Muffin: https://github.com/klen/muffin
.. _MIT license: http://opensource.org/licenses/MIT
