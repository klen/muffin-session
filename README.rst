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

**Muffin-Session** provides a simple and flexible way to manage secure session data via cookies.
It integrates seamlessly into Muffin apps with support for JWT, Fernet, and plain base64-encoded sessions.

Features
--------

- 🍪 Cookie-based session management
- 🔐 Supports multiple session backends:
  - Base64 (default)
  - **JWT**-signed sessions
  - **Fernet**-encrypted sessions
- 🧠 User loader & login utilities
- 🧩 Optional auto-managed middleware integration

Requirements
============

- Python ≥ 3.10
- Muffin ≥ 1.0
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
        return ses.get('var')


Auto-managed sessions
---------------------

.. code-block:: python

    from muffin import Application
    from muffin_session import Plugin as Session

    app = Application('example')

    session = Session()
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

You can pass options via `session.setup(...)` or set them in your application config using the `SESSION_` prefix:

.. code-block:: python

    SESSION_SECRET_KEY = 'REALLY_SECRET_KEY'
    SESSION_COOKIE_NAME = 'muffin_session'

Available Options
-----------------

=========================== =========================== ========================================================
Option                      Default                     Description
--------------------------- --------------------------- --------------------------------------------------------
**session_type**            ``"jwt"``                   Backend type: ``"base64"``, ``"jwt"``, or ``"fernet"``
**secret_key**              ``"InsecureSecret"``        Secret used to sign or encrypt sessions
**auto_manage**             ``False``                   If enabled, session is auto-loaded into ``request.session``
**cookie_name**             ``"session"``               Name of the session cookie
**cookie_params**           see below                   Cookie options: path, max-age, samesite, secure
**default_user_checker**    ``lambda x: True``          Function used to verify authenticated user
**login_url**               ``"/login"``                Redirect URL or callable for unauthenticated users
=========================== =========================== ========================================================

Example
=======

.. code-block:: python

    from muffin import Application
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
    @session.user_pass(lambda user: user.is_admin)
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
