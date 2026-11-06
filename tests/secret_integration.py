"""An isolated empty keyring: only synthetic secrets, never a user's collection."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from gi.repository import Gio, GLib
import desktop

with tempfile.TemporaryDirectory() as temporary:
    runtime=Path(temporary)/'runtime';runtime.mkdir(mode=0o700)
    data=Path(temporary)/'data';data.mkdir(mode=0o700)
    environment=dict(os.environ, XDG_RUNTIME_DIR=str(runtime), XDG_DATA_HOME=str(data))
    process=subprocess.Popen(['gnome-keyring-daemon','--foreground','--unlock','--components=secrets'],
                             stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                             env=environment)
    process.stdin.write(b'\n');process.stdin.close()
    try:
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        deadline=time.monotonic()+10
        while True:
            owned=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
                    'NameHasOwner',GLib.Variant('(s)',('org.freedesktop.secrets',)),None,
                    Gio.DBusCallFlags.NONE,2000,None).unpack()[0]
            if owned: break
            if process.poll() is not None or time.monotonic()>deadline:
                raise AssertionError('Isolated Secret Service did not start')
            time.sleep(0.1)
        address='synthetic@example.invalid'
        token={'refresh_token':'synthetic-refresh','access_token':'synthetic-access'}
        desktop.store(address,token)
        assert desktop.lookup(address)==token
        desktop.clear(address)
        assert desktop.lookup(address) is None
        # Reproduce the old secret-tool attributes with its generic schema name.
        import gi,json
        gi.require_version('Secret','1')
        from gi.repository import Secret
        schema=Secret.Schema.new('org.freedesktop.Secret.Generic',Secret.SchemaFlags.NONE,
              {'application':Secret.SchemaAttributeType.STRING,'account':Secret.SchemaAttributeType.STRING})
        attrs={'application':'gmail-notifier','account':address}
        assert Secret.password_store_sync(schema,attrs,Secret.COLLECTION_DEFAULT,'synthetic legacy',json.dumps(token),None)
        assert desktop.lookup(address)==token
        assert Secret.password_lookup_sync(schema,attrs,None) is None
        assert desktop.lookup(address)==token
        desktop.clear(address)
        assert desktop.lookup(address) is None
        print('Real libsecret store/lookup/clear and legacy migration passed on an isolated empty keyring.')
    finally:
        process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill();process.wait(timeout=3)
