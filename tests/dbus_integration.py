"""Run using: dbus-run-session -- /usr/bin/python3 tests/dbus_integration.py."""
from pathlib import Path
import sys
import threading
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from gi.repository import Gio, GLib
import desktop

xml = '''<node><interface name="org.freedesktop.Notifications"><method name="Notify">
<arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="s" direction="in"/>
<arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="as" direction="in"/>
<arg type="a{sv}" direction="in"/><arg type="i" direction="in"/>
<arg type="u" direction="out"/></method></interface></node>'''
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','RequestName',
              GLib.Variant('(su)', ('org.freedesktop.Notifications', 0)), None, Gio.DBusCallFlags.NONE, 5000, None)
received = []
def on_call(_bus, _sender, _path, _interface, _method, params, invocation):
    received.append(params.unpack())
    invocation.return_value(GLib.Variant('(u)', (42,)))
registration = bus.register_object('/org/freedesktop/Notifications', Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0], on_call, None, None)
loop = GLib.MainLoop(); thread = threading.Thread(target=loop.run, daemon=True); thread.start()
try:
    with patch('subprocess.Popen', side_effect=AssertionError('Private notification must not spawn a process')):
        assert desktop.notify('Nuevo email en la cuenta (TR)', '<b>Alice</b>\nPRIVATE SUBJECT') == 42
    packet = received[0]
    assert packet[3] == 'Nuevo email en la cuenta (TR)'
    assert packet[4] == '<b>Alice</b>\nPRIVATE SUBJECT'
    assert packet[6]['transient'] is True
    assert b'PRIVATE SUBJECT' not in Path('/proc/self/cmdline').read_bytes()
    print('Real D-Bus delivery passed; no notification child process, private data absent from argv.')
finally:
    loop.quit(); thread.join(2); bus.unregister_object(registration)
