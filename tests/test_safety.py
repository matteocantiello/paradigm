"""Tests for sandbox safety scanner — network module detection."""

from paradigm.sandbox.safety import SafetyScanner


class TestNetworkModuleDetection:
    """Tests for network module import detection in safety scanner."""

    def test_network_module_requests_rejected(self):
        """import requests is rejected with a clear message."""
        scanner = SafetyScanner()
        verdict = scanner.scan("import requests\nresponse = requests.get('http://example.com')")
        assert not verdict.safe
        assert any("requests" in v and "no network" in v.lower() for v in verdict.violations)

    def test_network_module_httpx_rejected(self):
        """import httpx is rejected."""
        scanner = SafetyScanner()
        verdict = scanner.scan("import httpx\nclient = httpx.Client()")
        assert not verdict.safe
        assert any("httpx" in v and "no network" in v.lower() for v in verdict.violations)

    def test_network_module_aiohttp_rejected(self):
        """from aiohttp import ClientSession is rejected."""
        scanner = SafetyScanner()
        verdict = scanner.scan("from aiohttp import ClientSession")
        assert not verdict.safe
        assert any("aiohttp" in v for v in verdict.violations)

    def test_urllib_parse_allowed(self):
        """from urllib.parse import urlparse is NOT rejected."""
        scanner = SafetyScanner()
        verdict = scanner.scan("from urllib.parse import urlparse\nresult = urlparse('http://x')")
        assert verdict.safe

    def test_urllib_request_rejected(self):
        """from urllib.request import urlopen is rejected via regex."""
        scanner = SafetyScanner()
        verdict = scanner.scan(
            "from urllib.request import urlopen\ndata = urlopen('http://example.com')"
        )
        assert not verdict.safe
        assert any("urllib.request" in v for v in verdict.violations)

    def test_http_client_rejected(self):
        """import http.client is detected via regex."""
        scanner = SafetyScanner()
        verdict = scanner.scan("import http.client\nconn = http.client.HTTPConnection('x')")
        assert not verdict.safe
        assert any("http.client" in v for v in verdict.violations)

    def test_socket_connection_rejected(self):
        """socket.socket() is detected via regex."""
        scanner = SafetyScanner()
        verdict = scanner.scan(
            "import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)"
        )
        assert not verdict.safe
        assert any("socket" in v for v in verdict.violations)

    def test_safe_code_passes(self):
        """Normal scientific code passes all checks including network checks."""
        scanner = SafetyScanner()
        verdict = scanner.scan(
            "import numpy as np\n"
            "import matplotlib.pyplot as plt\n"
            "x = np.linspace(0, 10, 100)\n"
            "plt.plot(x, np.sin(x))\n"
            "plt.savefig('plot.png')\n"
        )
        assert verdict.safe
        assert len(verdict.violations) == 0

    def test_requests_from_import_rejected(self):
        """from requests import Session is rejected."""
        scanner = SafetyScanner()
        verdict = scanner.scan("from requests import Session\ns = Session()")
        assert not verdict.safe
        assert any("requests" in v for v in verdict.violations)
