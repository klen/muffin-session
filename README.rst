Muffin-Session
##############

.. _description:

**Muffin-Session** -- Signed Cookie-Based HTTP sessions for Muffin_ framework

.. _badges:

.. image:: https://github.com/klen/muffin-session/workflows/tests/badge.svg
    :target: https://github.com/klen/muffin-session/actions
    :alt: Tests Status

.. image:: https://img.shields.io/pypi/v/muffin-session
    :target: https://pypi.org/project/muffin-session/
    :alt: PYPI Version

.. _contents:

.. contents::

.. _requirements:

Requirements
=============

- python >= 3.8

.. _installation:

Installation
=============

**Muffin-Session** should be installed using pip: ::

    pip install muffin-session

.. _usage:

Usage
=====

1. Use it manually

.. code-block:: python

    from muffin import Application, ResponseHTML
    from muffin_session import Plugin as Session

    # Create Muffin Application
    app = Application('example')

    # Initialize the plugin
    # As alternative: session = Session(app, **options)
    session = Session()
    session.setup(app, secret_key='REALLY_SECRET_KEY_FOR_SIGN_YOUR_SESSIONS')

    # Use it inside your handlers
    @app.route('/update')
    async def update_session(request):
        ses = session.load_from_request(request)
        ses['var'] = 'value'
        response = ResponseHTML('Session has been updated')
        session.save_to_response(ses, response)
        return res

    @app.route('/load')
    async def load_session(request):
        ses = session.load_from_request(request)
        return ses.get('var')

1. Auto manage sessions (with middleware)

.. code-block:: python

    from muffin import Application, ResponseHTML
    from muffin_session import Plugin as Session

    # Create Muffin Application
    app = Application('example')

    # Initialize the plugin
    # As alternative: session = Session(app, **options)
    session = Session()
    session.setup(app, secret_key='REALLY_SECRET_KEY_FOR_SIGN_YOUR_SESSIONS', auto_manage=True)

    # Use it inside your handlers
    @app.route('/update')
    async def update_session(request):
        request.session['var'] = 'value'
        return 'Session has been updated'

    @app.route('/load')
    async def load_session(request):
        return request.session.get('var')


Options
-------

Format: ``Name`` -- Description (``default value``)

``secret_key`` -- A secret code to sign sessions (``InsecureSecret``)

``auto_manage`` -- Load/Save sessions automatically (``False``). Session will be loaded into ``request.session``

``cookie_name`` -- Sessions's cookie name (``session``)

``cookie_params`` -- Sessions's cookie params (``{'path': '/', 'max-age': None, 'samesite': 'lax', 'secure': False}``)

``default_user_checker`` -- A function to check a logged user (``lambda x: x``)

``login_url`` -- An URL to redirect anonymous users (it may be a function which accept ``Request`` and returns a string) (``/login``)


You are able to provide the options when you are initiliazing the plugin:

.. code-block:: python

    session.setup(app, secret_key='123455', cookie_name='info')


Or setup it inside ``Muffin.Application`` config using the ``SESSION_`` prefix:

.. code-block:: python

   SESSION_SECRET_KEY = '123455'

   SESSION_COOKIE_NAME = 'info'

``Muffin.Application`` configuration options are case insensetive


Examples
--------

.. code-block:: python

    from muffin import Application, ResponseHTML
    from muffin_session import Plugin as Session

    # Create Muffin Application
    app = Application('example')

    # Initialize the plugin
    # As alternative: session = Session(app, **options)
    session = Session()
    session.setup(app, secret_key='REALLY_SECRET_KEY_FOR_SIGN_YOUR_SESSIONS', auto_manage=True)

    @session.user_loader
    async def load_user(ident):
        """Define your own user loader. """
        return await my_database_load_user_by_id(ident)

    @app.register('/session')
    async def get_session(request):
        """ Load session and return it as JSON. """
        return dict(request.session)

    @app.register('/admin')
    @session.user_pass(lambda user: user.is_admin)
    async def admin(request):
        """Awailable for admins only. """
        return 'TOP SECRET'

    @app.register('/login')
    async def login(request):
        """Save user id into the current session. """
        # ...
        session.login(request, current_user.pk)
        return 'OK'

    @app.register('/logout')
    async def logout(request):
        """ Logout user. """
        # ...
        session.logout(request)
        return 'OK'

    @app.register('/somewhere')
    async def somewhere(request):
        """ Do something and leave a flash message """
        # ...
        request.session.clear()
        return 'OK'


.. _bugtracker:

Bug tracker
===========

If you have any suggestions, bug reports or
annoyances please report them to the issue tracker
at https://github.com/klen/muffin-session/issues

.. _contributing:

Contributing
============

Development of Muffin-Session happens at: https://github.com/klen/muffin-session


Contributors
=============

* klen_ (Kirill Klenov)

.. _license:

License
========

Licensed under a `MIT license`_.

.. _links:


.. _klen: https://github.com/klen
.. _Muffin: https://github.com/klen/muffin

.. _MIT license: http://opensource.org/licenses/MIT
