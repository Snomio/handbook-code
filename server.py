#!/usr/local/bin/python
"""HTTP Server based on SimpleHTTPServer with basic templating functions

Handles GET and POST requests.

A simple templating system is provided, using the Python string substitution
(see: https://docs.python.org/2/library/string.html#template-strings)
only files with .xml extension are handed as a template, templates variables
are initiated from command line using the -v switch, into the template you can
use also variables coming form the GET request URI or the POST body.

This server is based on the code provided by Pierre Quentel:
    http://code.activestate.com/recipes/392879-my-first-application-server/
"""

import sys
import os
import string
import cStringIO
import select
import SimpleHTTPServer
import BaseHTTPServer
import logging
import cgi


class MyHTTPServer(BaseHTTPServer.HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, variables):
        self.variables = variables
        BaseHTTPServer.HTTPServer.__init__(self, server_address, RequestHandlerClass)


class ScriptRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    """One instance of this class is created for each HTTP request"""

    def do_GET(self):
        """Begin serving a GET request"""
        # build self.req_params from the query string
        self.req_params = {}
        if self.path.find('?') > -1:
            qs = self.path.split('?', 1)[1]
            self.req_params = cgi.parse_qs(qs, keep_blank_values=1)
        self.handle_data()

    def do_POST(self):
        """Begin serving a POST request. The request data is readable
        on a file-like object called self.rfile"""
        ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
        length = int(self.headers.getheader('content-length'))
        if ctype == 'multipart/form-data':
            self.req_params = cgi.parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            qs = self.rfile.read(length)
            self.req_params = cgi.parse_qs(qs, keep_blank_values=1)
        else:
            self.req_params = {}                   # Unknown content-type
        # some browsers send 2 more bytes...
        [ready_to_read, x, y] = select.select([self.connection], [], [], 0)
        if ready_to_read:
            self.rfile.read(2)
        self.handle_data()

    def handle_data(self):
        """Process the data received"""
        self.resp_headers = {"Content-type": 'text/html'}  # default
        path = self.get_file()  # return a file name or None
        if os.path.isdir(path):
            # list directory
            dir_list = self.list_directory(path)
            self.copyfile(dir_list, self.wfile)
            return
        ext = os.path.splitext(path)[1].lower()

        ctype = self.guess_type(path)
        self.resp_headers['Content-type'] = ctype

        if len(ext) > 1 and ext == ".xml" and os.path.isfile(path):  # Pre parse only .xml files
            logging.info("Found XML file to parse")
            self.run_xml(path)
        else:
            # other files
            if ctype.startswith('text/'):
                mode = 'r'
            else:
                mode = 'rb'
            try:
                f = open(path, mode)
                self.resp_headers['Content-length'] = str(os.fstat(f.fileno())[6])
                self.done(200, f)
            except IOError:
                self.send_error(404, "File not found")

    def done(self, code, infile):
        """Send response, cookies, response headers 
        and the data read from infile"""
        self.send_response(code)
        for (k, v) in self.resp_headers.items():
            self.send_header(k, v)
        self.end_headers()
        infile.seek(0)
        self.copyfile(infile, self.wfile)

    def get_file(self):
        """Set the Content-type header and return the file open
        for reading, or None"""
        path = self.path
        if path.find('?') > 1:
            # remove query string, otherwise the file will not be found
            path = path.split('?', 1)[0]
        path = self.translate_path(path)
        if os.path.isdir(path):

            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
        return path

    def run_xml(self, script):
        """Templating system with the string substitution syntax
        introduced in Python 2.4"""

        try:
            # values must be strings, not lists
            dic = dict([(k, v[0]) for k, v in self.req_params.items()])
            # Merge req_params and command line defined vars
            dic.update(self.server.variables)
            data = string.Template(open(script).read()).safe_substitute(dic)
        except Exception, e:
            data = '<h1>Internal server error</h1> Excpetion: in file %s : %s' \
                % (os.path.basename(script), e)
            self.resp_headers['Content-length'] = len(data)
            # Something went wrong, return an error 500
            self.done(500, cStringIO.StringIO(data))
            return

        self.resp_headers['Content-length'] = len(data)
        self.done(200, cStringIO.StringIO(data))

if __name__ == "__main__":
    # launch the server on the specified port
    import SocketServer
    import optparse

    usage = """%prog [OPTIONS]"""
    opt = optparse.OptionParser(usage=usage)
    opt.add_option('-i', dest='ip_address', type='string', default="0.0.0.0",
                        help='Specify ip address to bind on (default: 0.0.0.0)')

    opt.add_option('-p', dest='port', type='int', default=8000,
                        help='Specify the TCP port to bind on (default: 8000')
    opt.add_option('-v', dest='variables', type='string', action='append', default=[],
                        help="Add a variable to parse into a .xml file")

    options, args = opt.parse_args(sys.argv[1:])

    template_vars = {}

    for v in options.variables:
        try:
            key = v.split(":")[0]
            val = ":".join(v.split(":")[1:])
            template_vars.update({key: val})
        except IndexError:
            print "ERROR: variables must be in format name:value. %s" % v
            opt.print_help()
            sys.exit()

    s = MyHTTPServer((options.ip_address, options.port), ScriptRequestHandler, variables=template_vars)

    print "=========================="
    print "Server running on port %s:%d" % (options.ip_address, options.port)
    print "Press CTRL-C to quit."
    print "=========================="
    print "Defined variables:"

    for k in template_vars:
        print "* %s: '%s'" % (k, template_vars[k])
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        print ("Bye bye !")
