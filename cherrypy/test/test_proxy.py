import cherrypy
from cherrypy.test import helper

script_names = ['', '/path/to/myapp']


class ProxyTest(helper.CPWebCase):
    @staticmethod
    def setup_server():
        # Set up site
        cherrypy.config.update(
            {
                'tools.proxy.on': True,
                'tools.proxy.base': 'www.mydomain.test',
            },
        )

        # Set up application

        class Root:
            def __init__(self, sn):
                # Calculate a URL outside of any requests.
                self.thisnewpage = cherrypy.url(
                    '/this/new/page',
                    script_name=sn,
                )

            @cherrypy.expose
            def pageurl(self):
                return self.thisnewpage

            @cherrypy.expose
            def index(self):
                raise cherrypy.HTTPRedirect('dummy')

            @cherrypy.expose
            def remoteip(self):
                return cherrypy.request.remote.ip

            @cherrypy.expose
            @cherrypy.config(
                **{
                    'tools.proxy.local': 'X-Host',
                    'tools.trailing_slash.extra': True,
                },
            )
            def xhost(self):
                raise cherrypy.HTTPRedirect('blah')

            @cherrypy.expose
            def base(self):
                return cherrypy.request.base

            @cherrypy.expose
            @cherrypy.config(**{'tools.proxy.scheme': 'X-Forwarded-Ssl'})
            def ssl(self):
                return cherrypy.request.base

            @cherrypy.expose
            def newurl(self):
                return "Browse to <a href='%s'>this page</a>." % cherrypy.url(
                    '/this/new/page',
                )

            @cherrypy.expose
            @cherrypy.config(
                **{
                    'tools.proxy.base': None,
                },
            )
            def base_no_base(self):
                return cherrypy.request.base

        for sn in script_names:
            cherrypy.tree.mount(Root(sn), sn)

    def testProxy(self):
        self.getPage('/')
        self.assertHeader(
            'Location',
            '%s://www.mydomain.test%s/dummy' % (self.scheme, self.prefix()),
        )

        # Test X-Forwarded-Host (Apache 1.3.33+ and Apache 2)
        self.getPage(
            '/',
            headers=[('X-Forwarded-Host', 'http://www.example.test')],
        )
        self.assertHeader('Location', 'http://www.example.test/dummy')
        self.getPage('/', headers=[('X-Forwarded-Host', 'www.example.test')])
        self.assertHeader(
            'Location',
            '%s://www.example.test/dummy' % self.scheme,
        )
        # Test multiple X-Forwarded-Host headers
        self.getPage(
            '/',
            headers=[
                (
                    'X-Forwarded-Host',
                    'http://www.example.test, www.cherrypy.test',
                ),
            ],
        )
        self.assertHeader('Location', 'http://www.example.test/dummy')

        # Test X-Forwarded-For (Apache2)
        self.getPage(
            '/remoteip',
            headers=[('X-Forwarded-For', '192.168.0.20')],
        )
        self.assertBody('192.168.0.20')
        # Fix bug #1268
        self.getPage(
            '/remoteip',
            headers=[('X-Forwarded-For', '67.15.36.43, 192.168.0.20')],
        )
        self.assertBody('67.15.36.43')

        # Test X-Host (lighttpd; see https://trac.lighttpd.net/trac/ticket/418)
        self.getPage('/xhost', headers=[('X-Host', 'www.example.test')])
        self.assertHeader(
            'Location',
            '%s://www.example.test/blah' % self.scheme,
        )

        # Test X-Forwarded-Proto (lighttpd)
        self.getPage('/base', headers=[('X-Forwarded-Proto', 'https')])
        self.assertBody('https://www.mydomain.test')

        # Test X-Forwarded-Ssl (webfaction?)
        self.getPage('/ssl', headers=[('X-Forwarded-Ssl', 'on')])
        self.assertBody('https://www.mydomain.test')

        # Test cherrypy.url()
        for sn in script_names:
            # Test the value inside requests
            self.getPage(sn + '/newurl')
            self.assertBody(
                "Browse to <a href='%s://www.mydomain.test" % self.scheme
                + sn
                + "/this/new/page'>this page</a>.",
            )
            self.getPage(
                sn + '/newurl',
                headers=[('X-Forwarded-Host', 'http://www.example.test')],
            )
            self.assertBody(
                "Browse to <a href='http://www.example.test"
                + sn
                + "/this/new/page'>this page</a>.",
            )

            # Test the value outside requests
            port = ''
            if self.scheme == 'http' and self.PORT != 80:
                port = ':%s' % self.PORT
            elif self.scheme == 'https' and self.PORT != 443:
                port = ':%s' % self.PORT
            host = self.HOST
            if host in ('0.0.0.0', '::'):
                import socket

                host = socket.gethostname()
            expected = '%s://%s%s%s/this/new/page' % (
                self.scheme,
                host,
                port,
                sn,
            )
            self.getPage(sn + '/pageurl')
            self.assertBody(expected)

        # Test trailing slash (see
        # https://github.com/cherrypy/cherrypy/issues/562).
        self.getPage('/xhost/', headers=[('X-Host', 'www.example.test')])
        self.assertHeader(
            'Location',
            '%s://www.example.test/xhost' % self.scheme,
        )

    def test_no_base_port_in_host(self):
        """
        If no base is indicated, and the host header is used to resolve
        the base, it should rely on the host header for the port also.
        """
        headers = {'Host': 'localhost:8080'}.items()
        self.getPage('/base_no_base', headers=headers)
        self.assertBody('http://localhost:8080')
