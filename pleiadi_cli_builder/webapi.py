"""A read-only JSON client for web APIs (issue trackers, CI, wikis): it has only GET, so a tool built on it cannot
change anything there, whatever the token allows. Pages, retries with backoff (429/5xx, Retry-After), the token
in a header (never in the URL), an internal CA file or a pinned certificate fingerprint with its expiry date —
never verification turned off."""
import datetime, hashlib, http.client, json, socket, ssl, time, urllib.error, urllib.parse, urllib.request


class HTTPError(Exception):
    def __init__(self, status, url, body=""):
        super().__init__(f"HTTP {status} for {url}" + (f": {body[:200]}" if body else ""))
        self.status, self.url, self.body = status, url, body


def fingerprint(der):
    return hashlib.sha256(der).hexdigest()


def _pin_ok(der, pin, expires, today=None):
    """True when the certificate is the pinned one and the pin hasn't expired."""
    today = today or datetime.date.today()
    if expires and today > datetime.date.fromisoformat(expires):
        raise ssl.SSLError(f"pinned fingerprint expired on {expires}: check the new certificate and update the pin")
    return fingerprint(der) == pin.replace(":", "").lower()


class _PinnedHTTPS(urllib.request.HTTPSHandler):
    """Accepts exactly the certificate with the expected sha256 (an internal authority the system doesn't know):
    the chain check is replaced by the pin, never simply skipped."""
    def __init__(self, pin, expires):
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        super().__init__(context=ctx)
        self.pin, self.expires, self.ctx = pin, expires, ctx

    def https_open(self, req):
        pin, expires, ctx = self.pin, self.expires, self.ctx

        class Conn(http.client.HTTPSConnection):
            def connect(self):
                super().connect()
                der = self.sock.getpeercert(binary_form=True)
                if not _pin_ok(der, pin, expires):
                    self.sock.close()
                    raise ssl.SSLError(f"certificate of {self.host} is not the pinned one (sha256 {fingerprint(der)})")
        return self.do_open(lambda host, **kw: Conn(host, context=ctx, timeout=kw.get("timeout", 30)), req)


class ReadOnlyClient:
    """
        api = ReadOnlyClient("https://tracker.example", token=secret("tool.tracker", user, screen),
                             header="X-Api-Key", scheme="")
        for issue in api.pages("/issues.json", {"status_id": "open"}, items="issues"):
            ...
    """
    def __init__(self, base_url, token=None, header="Authorization", scheme="Bearer", timeout=30, retries=3,
                 ca_file=None, pin_sha256=None, pin_expires=None, agent="pleiadi-cli-builder"):
        if not base_url.startswith("https://") and not base_url.startswith("http://localhost") \
                and not base_url.startswith("http://127.0.0.1"):
            raise ValueError("https only (http just for localhost)")
        if pin_sha256 and not pin_expires:
            raise ValueError("a pinned fingerprint needs its expiry date (pin_expires='YYYY-MM-DD')")
        self.base, self.timeout, self.retries = base_url.rstrip("/"), timeout, retries
        self.headers = {"Accept": "application/json", "User-Agent": agent}
        if token:
            self.headers[header] = f"{scheme} {token}".strip()
        if pin_sha256:
            self.opener = urllib.request.build_opener(_PinnedHTTPS(pin_sha256, pin_expires))
        else:
            ctx = ssl.create_default_context(cafile=ca_file)
            self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))

    def url(self, path, params=None):
        q = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        return self.base + "/" + path.lstrip("/") + ("?" + q if q else "")

    def get(self, path, params=None):
        """GET → parsed JSON. Retries 429/5xx and network errors with backoff; other errors raise HTTPError."""
        url = self.url(path, params)
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(url, headers=self.headers, method="GET")
                with self.opener.open(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8") or "null")
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                e.close()
                if e.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise HTTPError(e.code, url.split("?")[0], body) from None
                wait = e.headers.get("Retry-After", "")
                time.sleep(min(30, float(wait)) if wait.isdigit() else 2 ** attempt)
            except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
                if isinstance(getattr(e, "reason", None), ssl.SSLError) or isinstance(e, ssl.SSLError) \
                        or attempt == self.retries:
                    raise  # a certificate problem doesn't get better by retrying
                time.sleep(2 ** attempt)

    def pages(self, path, params=None, items="items", limit=100, limit_param="limit", offset_param="offset",
              total="total_count", max_items=10000):
        """Every item of a paged list (offset/limit style, with the total in `total`), up to max_items."""
        offset, seen = 0, 0
        while seen < max_items:
            data = self.get(path, {**(params or {}), limit_param: limit, offset_param: offset})
            batch = (data or {}).get(items) or []
            for it in batch:
                yield it
                seen += 1
                if seen >= max_items:
                    return
            offset += len(batch)
            if not batch or (total in (data or {}) and offset >= data[total]):
                return
