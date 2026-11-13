"""Render the real guide with small host-theme/button shims, without Google or a compositor.

This checks QML bindings, navigation, localization and layout; it is not acceptance
inside Omarchy. All shims match the guide's used public Ui.Button properties.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
import json
from pathlib import Path
import sys
import tempfile
from PySide6.QtCore import QObject, QUrl, QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
app = QGuiApplication([])
with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    commons = folder/'qs/Commons'
    ui = folder/'qs/Ui'
    commons.mkdir(parents=True)
    ui.mkdir(parents=True)
    (commons/'qmldir').write_text('module qs.Commons\nsingleton Style 1.0 Style.qml\nsingleton Color 1.0 Color.qml\nsingleton I18n 1.0 I18n.qml\n')
    (commons/'Style.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
  property var font: ({body:14,bodySmall:13})
  function space(value) { return value }
}''')
    (commons/'Color.qml').write_text('''pragma Singleton
import QtQuick
QtObject { property color foreground: "#e5e7eb"; property color accent: "#8fbcbb" }''')
    (commons/'I18n.qml').write_text('''pragma Singleton
import QtQuick
QtObject { property string language: "es-ES" }''')
    (ui/'qmldir').write_text('module qs.Ui\nButton 1.0 Button.qml\n')
    (ui/'Button.qml').write_text('''import QtQuick
Rectangle {
  id:button
  property string text: ""
  property bool bordered: false
  property bool focusable: false
  property color accent: "#8fbcbb"
  signal clicked()
  implicitWidth: Math.max(70,label.implicitWidth+24)
  implicitHeight: 34
  color: "#20252d"; border.color: accent; border.width: bordered?1:0; radius:4
  opacity: enabled?1:0.4
  Text { id:label; anchors.centerIn:parent; width:Math.max(0,parent.width-24)
    text:button.text; color:"#e5e7eb"; font.pixelSize:14; horizontalAlignment:Text.AlignHCenter
    textFormat:Text.PlainText; fontSizeMode:Text.HorizontalFit; minimumPixelSize:10; elide:Text.ElideRight }
  MouseArea { anchors.fill:parent; onClicked:button.clicked() }
}''')
    wrapper = folder/'Preview.qml'
    wrapper.write_text('''import QtQuick
import %s as Plugin
Rectangle {
  width:408; height:720; color:"#10141c"
  Flickable { id:scroll; objectName:"scroll"; anchors.fill:parent; clip:true
    contentHeight:help.implicitHeight+32
    Plugin.OAuthSetupHelp { id:help; objectName:"guide"; x:16; y:16; width:parent.width-32
      onNavigated: scroll.contentY=0 }
  }
}''' % json.dumps(ROOT.as_uri()))
    view = QQuickView()
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    warnings = []
    view.engine().warnings.connect(lambda errors: warnings.extend(str(e.toString()) for e in errors))
    view.engine().addImportPath(str(folder))
    view.setSource(QUrl.fromLocalFile(str(wrapper)))
    assert view.status() == QQuickView.Ready, [e.toString() for e in view.errors()]
    view.show()
    QTest.qWait(100)
    guide = view.rootObject().findChild(QObject, 'guide')
    scroll = view.rootObject().findChild(QObject, 'scroll')
    check_signals = []
    connect_signals = []
    guide.checkRequested.connect(lambda: check_signals.append(True))
    guide.connectRequested.connect(lambda: connect_signals.append(True))

    def click(name):
        button = guide.findChild(QObject, name)
        assert button and button.isVisible() and button.isEnabled(), name
        point = button.mapToItem(view.rootObject(), button.boundingRect().center())
        scroll.setProperty('contentY', max(0,point.y()-view.height()/2))
        QTest.qWait(5)
        point = button.mapToItem(view.rootObject(), button.boundingRect().center())
        QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()),round(point.y())))
        QTest.qWait(10)

    # Auto locale must follow the host's es-ES without changing plugin settings.
    assert guide.property('help').toVariant()['title'] == 'Configura el acceso con Google'
    for language in ('en','es'):
        for width in (360,448,720):
            view.setWidth(width+32)
            guide.setProperty('language',language)
            guide.setProperty('hasAccounts',False)
            guide.setProperty('stepIndex',0)
            for index in range(8):
                QTest.qWait(5)
                assert guide.property('stepIndex') == index
                assert guide.width() == width
                assert guide.implicitHeight() > 0
                assert guide.property('step').toVariant()['title']
                if index < 7:
                    click('helpNext')
            # Inspect readiness transitions without calling OAuth or a network API.
            for status in ('missing','invalid','unreadable','ready'):
                guide.setProperty('oauthStatus',status)
                guide.setProperty('oauthReady',status=='ready')
                QTest.qWait(5)
            click('helpCheck')
            assert len(connect_signals) == 0
            assert guide.findChild(QObject,'helpConnect').isVisible()
            guide.setProperty('networkBusy',True)
            QTest.qWait(5)
            assert not guide.findChild(QObject,'helpConnect').isEnabled()
            assert guide.findChild(QObject,'helpCheck').isEnabled()
            guide.setProperty('networkBusy',False)
            click('helpPrevious')
            assert guide.property('stepIndex') == 6
            if '--screenshots' in sys.argv and width == 360:
                target=ROOT/'artifacts'
                target.mkdir(exist_ok=True)
                scroll.setProperty('contentY',0)
                QTest.qWait(30)
                assert view.grabWindow().save(str(target/('oauth-help-'+language+'.png')))
            guide.setProperty('stepIndex',7)
            guide.setProperty('hasAccounts',True)
            QTest.qWait(5)
            assert guide.property('stepIndex') == 0
            assert len(guide.property('help').toVariant()['steps']) == 3
            click('helpNext'); click('helpNext')
            assert not guide.findChild(QObject,'helpConnect').isVisible()
    assert len(check_signals) == 6
    assert not connect_signals, 'navigation/check must not silently connect Gmail'
    assert not warnings, '\n'.join(warnings)
    view.close()
    print('Qt guide rendering/navigation passed: EN/ES, auto locale, 360/448/720 widths, setup states and recovery. Host shims used; Omarchy desktop acceptance remains separate.')
