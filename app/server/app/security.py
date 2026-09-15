import base64
import hashlib
import hmac
import secrets
import time


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 20000).hex()
    return salt + "$" + digest


def verify_password(password, stored):
    try:
        salt, digest = stored.split("$")
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 20000).hex()
    return hmac.compare_digest(calc, digest)


def make_token(uid, secret, ttl=86400 * 7):
    exp = int(time.time()) + ttl
    payload = base64.urlsafe_b64encode(("%d:%d" % (uid, exp)).encode()).decode()
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + sig


def parse_token(token, secret):
    try:
        payload, sig = token.split(".")
        expect = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        uid, exp = base64.urlsafe_b64decode(payload.encode()).decode().split(":")
        if int(exp) < int(time.time()):
            return None
        return int(uid)
    except Exception:
        return None
