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


def lookup(email):
    with secret_api() as (Secret, schema, cancel):
        attrs = {"application": "gmail-notifier", "account": key(email)}
        value = Secret.password_lookup_sync(schema, attrs, cancel)
        if not value:
            # Read the legacy secret-tool entry in process, then migrate it.
            attrs["account"] = email
            value = Secret.password_lookup_sync(schema, attrs, cancel)
            if value:
                token = json.loads(value)
                store(email, token)
                Secret.password_clear_sync(schema, attrs, cancel)
        return json.loads(value) if value else None


def store(email, token):
    with secret_api() as (Secret, schema, cancel):
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
