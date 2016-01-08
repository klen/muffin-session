import pytest
import asyncio
import muffin


@pytest.fixture(scope='session')
def app(loop):
    app = muffin.Application(
        'session', loop=loop,

        PLUGINS=['muffin_session'],
    )

    @app.register('/auth')
    @app.ps.session.user_pass()
    def auth(request):
        return request.user

    def determine_redir(request):
        return request.GET.get('target')

    @app.register('/auth_dyn')
    @app.ps.session.user_pass(location=determine_redir)
    def auth_dyn(request):
        return request.user

    @asyncio.coroutine
    def determine_redir_async(request):
        return request.GET.get('target')

    @app.register('/auth_dyn_async')
    @app.ps.session.user_pass(location=determine_redir)
    def auth_dyn_async(request):
        return request.user

    @app.register('/login')
    def login(request):
        yield from app.ps.session.login(request, request.GET.get('name'))
        return muffin.HTTPFound('/auth')

    @app.register('/logout')
    def logout(request):
        yield from app.ps.session.logout(request)
        return muffin.HTTPFound('/')

    @app.register('/session')
    def session(request):
        session = yield from app.ps.session(request)
        return dict(session)

    @app.register('/error')
    def error(request):
        session = yield from app.ps.session(request)
        session = yield from app.ps.session(request)
        session['name'] = 'value'
        raise muffin.HTTPForbidden()

    @app.register('/flash')
    def flash(request):
        yield from app.ps.session.flash(request, request.GET.get('message'))
        return 'ok'

    @app.register('/flash_get')
    def flash_get(request):
        msgs = (yield from app.ps.session.get_flashed_messages_async(request))
        return msgs

    return app

def test_muffin_session(app, client):
    assert app.ps.session

    response = client.get('/auth')
    assert response.status_code == 302
    assert response.headers['location'] == '/login'

    response = client.get('/auth_dyn', {'target': '/another_page'})
    assert response.status_code == 302
    assert response.headers['location'] == '/another_page'

    response = client.get('/auth_dyn_async', {'target': '/another_page'})
    assert response.status_code == 302
    assert response.headers['location'] == '/another_page'

    client.get('/login', {'name': 'mike'})
    response = client.get('/auth')
    assert 'mike' in response.text

    response = client.get('/session')
    assert response.json == {'id': 'mike'}

    client.get('/error', status=403)
    response = client.get('/session')
    assert 'name' in response.json

    client.get('/logout')
    response = client.get('/auth')
    assert response.status_code == 302
    assert response.headers['location'] == '/login'

    response = client.get('/logout')
    assert response.status_code == 302
    assert response.headers['location'] == '/'

    response = client.get('/session')
    assert 'id' not in response.json

def test_muffin_session_redirect_url(app, client):
    # FIXME it is a hack, but having two fixtures doesn't work
    object.__setattr__(app.ps.session.cfg, '_lock', False)
    app.ps.session.cfg.login_url = lambda request: '/login?redir='+request.path

    response = client.get('/auth')
    assert response.status_code == 302
    assert response.headers['location'] == '/login?redir=/auth'

def test_muffin_session_flash(app, client):
    # add one message
    response = client.get('/flash?message=Hello')
    assert response.status_code == 200
    assert response.text == 'ok'

    # add another message
    response = client.get('/flash?message=abc')

    # check that both messages are present
    response = client.get('/flash_get')
    assert response.status_code == 200
    assert 'Hello' in response.json
    assert 'abc' in response.json

    # check that both messages were removed in previous request
    response = client.get('/flash_get')
    assert response.status_code == 200
    assert response == []

