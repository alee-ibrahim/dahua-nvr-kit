"""Minimal Dahua RPC2 client with session-cookie authentication.

Dahua NVRs/DVRs/cameras expose a JSON-RPC endpoint at /RPC2 (and a login endpoint
at /RPC2_Login). Authentication is a two-step MD5 challenge-response:

    1. POST global.login with an empty password -> server returns {realm, random}.
    2. POST global.login again with
           hash = MD5( user : random : MD5( user : realm : password ) ).upper()

After login the session id is set as the ``DhWebClientSessionID`` cookie. On several
firmware builds HTTP Digest auth against the CGI layer fails while this cookie-based
session works, so we authenticate once and reuse the session for every call.

Safety: this client performs a SINGLE login attempt. It never loops on a failed
password, because Dahua devices lock the admin account after a few bad tries.
No password is ever printed.
"""
import hashlib
import requests


def _md5(s):
    return hashlib.md5(s.encode()).hexdigest().upper()


class DahuaRPC:
    def __init__(self, host, username="admin", password="", timeout=20, port=80):
        self.base = f"http://{host}:{port}" if port != 80 else f"http://{host}"
        self.host = host
        self.username = username
        self._password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.sid = None
        self._id = 0

    # -- login ---------------------------------------------------------------
    def login(self):
        """Perform the two-step challenge-response login. Returns True on success.
        Raises RuntimeError on an explicit login failure. No retry loop."""
        r = self.session.post(
            self.base + "/RPC2_Login",
            json={
                "method": "global.login",
                "params": {"userName": self.username, "password": "",
                           "clientType": "Web3.0", "loginType": "Direct"},
                "id": 1,
            },
            timeout=self.timeout,
        ).json()
        params = r.get("params") or {}
        sid = r.get("session")
        realm, random = params.get("realm"), params.get("random")
        if not realm or not random:
            raise RuntimeError(f"{self.host}: unexpected login challenge")
        if params.get("encryption") not in (None, "Default"):
            raise RuntimeError(f"{self.host}: unsupported encryption {params.get('encryption')!r}")

        inner = _md5(f"{self.username}:{realm}:{self._password}")
        h = _md5(f"{self.username}:{random}:{inner}")
        r = self.session.post(
            self.base + "/RPC2_Login",
            json={
                "method": "global.login",
                "params": {"userName": self.username, "password": h,
                           "clientType": "Web3.0", "loginType": "Direct",
                           "authorityType": "Default"},
                "session": sid, "id": 2,
            },
            timeout=self.timeout,
        ).json()
        if not r.get("result"):
            raise RuntimeError(f"{self.host}: login failed ({r.get('error')})")
        self.sid = r.get("session") or sid
        self.session.cookies.set("DhWebClientSessionID", str(self.sid))
        self._id = 10
        return True

    # -- generic call --------------------------------------------------------
    def call(self, method, params=None, timeout=None):
        self._id += 1
        r = self.session.post(
            self.base + "/RPC2",
            json={"method": method, "params": params, "session": self.sid, "id": self._id},
            timeout=timeout or self.timeout,
        )
        return r.json()

    def logout(self):
        try:
            self.call("global.logout", None)
        except Exception:
            pass

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, *exc):
        self.logout()

    # -- convenience wrappers ------------------------------------------------
    def get_config(self, name):
        r = self.call("configManager.getConfig", {"name": name})
        return (r.get("params") or {})

    def get_table(self, name):
        return self.get_config(name).get("table")

    def set_config(self, name, table):
        return self.call("configManager.setConfig", {"name": name, "table": table})

    def camera_states(self):
        """Return {zero_based_channel: connectionState} for every channel."""
        out = {}
        r = self.call("LogicDeviceManager.getCameraState", {"uniqueChannels": [-1]})
        for it in ((r.get("params") or {}).get("states") or []):
            out[it.get("channel")] = it.get("connectionState")
        return out

    def snapshot(self, channel):
        """Fetch a JPEG snapshot for a 1-based channel using the live session.
        Returns bytes or None."""
        r = self.session.get(
            f"{self.base}/cgi-bin/snapshot.cgi?channel={channel}", timeout=max(self.timeout, 25)
        )
        if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
            return r.content
        return None

    def export_config_backup(self, extension=0):
        """GET the encrypted config backup (magic 'MWPZWJGS'). Returns bytes or None."""
        import time
        url = (f"{self.base}/cgi-bin/configFileExport.backup"
               f"?action=All&ExtensionName={extension}&{int(time.time() * 1000)}")
        r = self.session.get(url, timeout=max(self.timeout, 60))
        if r.status_code == 200 and len(r.content) > 1000:
            return r.content
        return None
