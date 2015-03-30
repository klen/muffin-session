import pytest
import muffin


@pytest.fixture(scope='session')
def app(loop):
    app = muffin.Application(
        'session', loop=loop,

        PLUGINS=['muffin_session'])

    @app.register('/auth')
    @app.ps.session.user_pass()
    def auth(request):
        return request.user

    @app.register('/login')
    def login(request):
        yield from app.ps.session.login(request, request.GET.get('name'))
        return muffin.HTTPFound('/auth')

    @app.register('/logout')
    def logout(request):
        yield from app.ps.session.logout(request)
        return muffin.HTTPFound('/')

    return app


def test_muffin_session(app, client):
    assert app.ps.session

    response = client.get('/auth')
    assert response.status_code == 302

    client.get('/login', {'name': 'mike'})
    response = client.get('/auth')
    assert 'mike' in response.text

    client.get('/logout')
    response = client.get('/auth')
    assert response.status_code == 302
