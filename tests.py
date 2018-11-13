import pytest
import asyncio
import muffin


@pytest.fixture(scope='session')
def app():
    app = muffin.Application('session', SESSION_LOGIN_URL='/', PLUGINS=['muffin_session'])

    @app.register('/')
    async def index(request):
        return 'OK'

    @app.register('/auth')
    @app.ps.session.user_pass()
    def auth(request):
        return request.user

    def determine_redir(request):
        return request.query.get('target')

    @app.register('/auth_dyn')
    @app.ps.session.user_pass(location=determine_redir)
    def auth_dyn(request):
        return request.user

    @asyncio.coroutine
    def determine_redir_async(request):
        return request.query.get('target')

    @app.register('/auth_dyn_async')
    @app.ps.session.user_pass(location=determine_redir)
    def auth_dyn_async(request):
        return request.user

    @app.register('/login')
    async def login(request):
        await app.ps.session.login(request, request.query.get('name'))
        return muffin.HTTPFound('/auth')

    @app.register('/logout')
    async def logout(request):
        await app.ps.session.logout(request)
        return muffin.HTTPFound('/')

    @app.register('/session')
    async def session(request):
        session = await app.ps.session(request)
        return dict(session)

    @app.register('/error')
    async def error(request):
        session = await app.ps.session(request)
        session = await app.ps.session(request)
        session['name'] = 'value'
        raise muffin.HTTPForbidden()

    return app


async def test_muffin_session(app, client):
    assert app.ps.session

    async with client.get('/auth', allow_redirects=False) as resp:
        assert resp.status == 302
        assert resp.headers['location'] == '/'

    async with client.get(
            '/auth_dyn', params={'target': '/another_page'}, allow_redirects=False) as resp:
        assert resp.status == 302
        assert resp.headers['location'] == '/another_page'

    async with client.get(
            '/auth_dyn_async', params={'target': '/another_page'}, allow_redirects=False) as resp:
        assert resp.status == 302
        assert resp.headers['location'] == '/another_page'

    async with client.get('/login', params={'name': 'mike'}) as resp:
        assert resp.status == 200
        text = await resp.text()
        assert 'mike' in text

    async with client.get('/session') as resp:
        assert resp.status == 200
        json = await resp.json()
        assert json == {'id': 'mike'}

    async with client.get('/error') as resp:
        assert resp.status == 403

    async with client.get('/session') as resp:
        assert resp.status == 200
        json = await resp.json()
        assert 'name' in json

    async with client.get('/logout'):
        async with client.get('/session') as resp:
            json = await resp.json()
            assert 'id' not in json

    async with client.get('/auth', allow_redirects=False) as resp:
        assert resp.status == 302
        assert resp.headers['location'] == '/'

    async with client.get('/logout', allow_redirects=False) as resp:
        assert resp.status == 302
        assert resp.headers['location'] == '/'


def test_session():
    from muffin_session import Session

    session = Session('secret')
    session.load({session.key: 'invalid'})
    assert not session.store

    session.load({session.key: session.encrypt('{"test":true}')})
    assert session.store == {'test': True}
