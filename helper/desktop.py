"""Desktop IPC in process: no private text in argv, env, temporary payloads or logs."""
import hashlib
import json
import threading
from contextlib import contextmanager


def gio():
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        return Gio, GLib
    except (ImportError, ValueError) as error:
        raise RuntimeError("Install python-gobject for desktop D-Bus access.") from error


def notify(headline, body):
    Gio, GLib = gio()
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return bus.call_sync(
        "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
        "org.freedesktop.Notifications", "Notify",
        GLib.Variant("(susssasa{sv}i)", (
            "Gmail Notifier", 0, "mail-unread", headline, body, [],
            {"urgency": GLib.Variant("y", 1), "transient": GLib.Variant("b", True)}, -1,
        )), GLib.VariantType.new("(u)"), Gio.DBusCallFlags.NONE, 5000, None,
    ).unpack()[0]


@contextmanager
def secret_api():
    Gio, _ = gio()
    import gi
    try:
        gi.require_version("Secret", "1")
        from gi.repository import Secret
    except (ImportError, ValueError) as error:
        raise RuntimeError("Install libsecret (including its introspection typelib).") from error
    schema = Secret.Schema.new("org.omarchy.GmailNotifier", Secret.SchemaFlags.DONT_MATCH_NAME,
                               {"application": Secret.SchemaAttributeType.STRING,
                                "account": Secret.SchemaAttributeType.STRING})
    cancel = Gio.Cancellable()
    timer = threading.Timer(15, cancel.cancel)
    timer.daemon = True
    timer.start()
    try:
        yield Secret, schema, cancel
    finally:
        timer.cancel()


def key(email):
    return hashlib.sha256(email.lower().encode("utf-8")).hexdigest()


def decoded_token(value):
    if not isinstance(value, str) or len(value.encode('utf-8')) > 65536:
        return None
    try:
        token = json.loads(value)
        return token if isinstance(token, dict) and isinstance(token.get('refresh_token'), str) and token['refresh_token'] else None
    except (ValueError, UnicodeError):
        return None


def legacy_schema(Secret):
    return Secret.Schema.new('org.freedesktop.Secret.Generic', Secret.SchemaFlags.DONT_MATCH_NAME,
                             {'application': Secret.SchemaAttributeType.STRING,
                              'account': Secret.SchemaAttributeType.STRING})


def lookup(email, preserve_legacy=True):
    with secret_api() as (Secret, schema, cancel):
        hashed = decoded_token(Secret.password_lookup_sync(schema,
            {'application': 'gmail-notifier', 'account': key(email)}, cancel))
        legacy = decoded_token(Secret.password_lookup_sync(schema,
            {'application': 'gmail-notifier', 'account': email}, cancel))
        # Existing accounts keep their original entry as the authoritative copy.
        # A crash between the two writes can therefore never prefer a stale hash.
        token = legacy or hashed
        if token is not None and (hashed != token or (preserve_legacy and legacy != token)):
            try:
                store(email, token, preserve_legacy=preserve_legacy or legacy is not None)
            except Exception:
                # Compatibility copies are best effort on a read-only/locked store.
                # The valid original remains usable; a failed copy must never
                # turn an existing authorization into a new OAuth requirement.
                return token
        return token


def store(email, token, preserve_legacy=True):
    with secret_api() as (Secret, schema, cancel):
        attrs = {'application': 'gmail-notifier', 'account': email}
        existing = Secret.password_lookup_sync(schema, attrs, cancel)
        if preserve_legacy or existing:
            # Keep old releases usable. Never delete credentials during an upgrade.
            # Write the authoritative legacy copy first for crash recovery.
            if not Secret.password_store_sync(legacy_schema(Secret), attrs,
                    Secret.COLLECTION_DEFAULT, 'Gmail Notifier authorization',
                    json.dumps(token), cancel):
                raise RuntimeError('Secret Service could not preserve compatible authorization.')
        if not Secret.password_store_sync(schema,
                {"application": "gmail-notifier", "account": key(email)},
                Secret.COLLECTION_DEFAULT, "Gmail Notifier authorization",
                json.dumps(token), cancel):
            raise RuntimeError("Secret Service could not save authorization.")


def clear(email):
    with secret_api() as (Secret, schema, cancel):
        for account in (key(email), email):
            Secret.password_clear_sync(schema,
                {"application": "gmail-notifier", "account": account}, cancel)
