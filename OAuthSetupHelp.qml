import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui
import "SetupHelp.js" as SetupHelp

Column {
  id: root
  property string language: "auto"
  property bool oauthReady: false
  property string oauthStatus: "missing"
  property bool hasAccounts: false
  property bool actionRunning: false
  property bool networkBusy: false
  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property int fontSize: Style.font.body
  property int stepIndex: 0
  readonly property string effectiveLanguage: language === "auto" ? Commons.I18n.language : language
  readonly property var help: SetupHelp.guide(effectiveLanguage, hasAccounts)
  readonly property var step: help.steps[Math.min(stepIndex, help.steps.length - 1)]
  onHasAccountsChanged: stepIndex = 0
  signal backRequested()
  signal checkRequested()
  signal connectRequested()
  signal navigated()
  spacing: Style.space(10)

  function openLink(url) {
    if (SetupHelp.allowedLink(url)) Qt.openUrlExternally(url)
  }
  function moveStep(delta) {
    stepIndex = Math.max(0, Math.min(help.steps.length - 1, stepIndex + delta))
    navigated()
  }

  Ui.Button {
    objectName: "helpBack"
    text: root.help.back
    bordered: true
    focusable: true
    onClicked: root.backRequested()
  }
  Text {
    width: parent.width
    text: root.help.title
    textFormat: Text.PlainText
    color: root.accent
    font.pixelSize: root.fontSize + 2
    font.bold: true
    wrapMode: Text.WordWrap
  }
  Text {
    visible: root.stepIndex === 0
    width: parent.width
    text: root.help.intro
    textFormat: Text.PlainText
    color: root.foreground
    font.pixelSize: root.fontSize
    wrapMode: Text.WordWrap
  }
  Text {
    visible: root.hasAccounts
    width: parent.width
    text: root.help.existing
    textFormat: Text.PlainText
    color: root.accent
    font.pixelSize: root.fontSize
    wrapMode: Text.WordWrap
  }
  Text {
    width: parent.width
    text: root.help.stepLabel.replace("%1", String(root.stepIndex + 1)).replace("%2", String(root.help.steps.length)) + " · " + root.step.title
    textFormat: Text.PlainText
    color: root.accent
    font.pixelSize: root.fontSize
    font.bold: true
    wrapMode: Text.WordWrap
  }
  Repeater {
    model: root.step.paragraphs
    delegate: Text {
      required property string modelData
      width: root.width
      text: modelData
      textFormat: Text.PlainText
      color: root.foreground
      font.pixelSize: root.fontSize
      wrapMode: Text.WordWrap
    }
  }
  TextEdit {
    visible: !!root.step.location
    width: parent.width
    text: root.step.location || ""
    textFormat: TextEdit.PlainText
    readOnly: true
    selectByMouse: true
    persistentSelection: true
    wrapMode: TextEdit.WrapAnywhere
    color: root.accent
    font.pixelSize: root.fontSize
    Accessible.name: text
  }
  Rectangle {
    visible: !!root.step.code
    width: parent.width
    height: commandText.implicitHeight + Style.space(16)
    color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.08)
    border.color: root.accent
    border.width: 1
    radius: Style.space(4)
    TextEdit {
      id: commandText
      x: Style.space(8)
      y: Style.space(8)
      width: parent.width - Style.space(16)
      text: root.step.code || ""
      textFormat: TextEdit.PlainText
      readOnly: true
      selectByMouse: true
      persistentSelection: true
      wrapMode: TextEdit.WrapAnywhere
      color: root.foreground
      font.family: "monospace"
      font.pixelSize: root.fontSize
      Accessible.name: text
    }
  }
  Repeater {
    model: root.step.links
    delegate: Ui.Button {
      required property var modelData
      width: root.width
      text: modelData.label + " ↗"
      bordered: true
      focusable: true
      onClicked: root.openLink(modelData.url)
    }
  }
  Text {
    visible: root.stepIndex === root.help.steps.length - 1
    width: parent.width
    text: root.oauthReady ? (root.hasAccounts ? root.help.savedReady : root.help.ready)
      : root.oauthStatus === "invalid" ? root.help.invalid
      : root.oauthStatus === "unreadable" ? root.help.unreadable : root.help.missing
    textFormat: Text.PlainText
    color: root.oauthReady ? root.foreground : root.accent
    font.pixelSize: root.fontSize
    wrapMode: Text.WordWrap
  }
  Ui.Button {
    objectName: "helpCheck"
    visible: root.stepIndex === root.help.steps.length - 1
    width: parent.width
    text: root.help.check
    bordered: true
    focusable: true
    enabled: !root.actionRunning
    onClicked: root.checkRequested()
  }
  Ui.Button {
    objectName: "helpConnect"
    visible: root.stepIndex === root.help.steps.length - 1 && root.oauthReady && !root.hasAccounts
    width: parent.width
    text: root.help.add
    bordered: true
    focusable: true
    enabled: !root.actionRunning && !root.networkBusy
    accent: root.accent
    onClicked: root.connectRequested()
  }
  Row {
    width: parent.width
    spacing: Style.space(8)
    Ui.Button {
      objectName: "helpPrevious"
      width: (parent.width - Style.space(8)) / 2
      text: "← " + root.help.previous
      bordered: true
      focusable: true
      enabled: root.stepIndex > 0
      onClicked: root.moveStep(-1)
    }
    Ui.Button {
      objectName: "helpNext"
      width: (parent.width - Style.space(8)) / 2
      text: root.help.next + " →"
      bordered: true
      focusable: true
      enabled: root.stepIndex < root.help.steps.length - 1
      onClicked: root.moveStep(1)
    }
  }
  Text {
    visible: root.stepIndex === 0 || root.stepIndex === root.help.steps.length - 1
    width: parent.width
    text: root.help.privacy
    textFormat: Text.PlainText
    color: root.foreground
    font.pixelSize: root.fontSize
    wrapMode: Text.WordWrap
  }
  Text {
    visible: root.stepIndex === root.help.steps.length - 1
    width: parent.width
    text: root.help.troubleshooting
    color: root.accent
    font.pixelSize: root.fontSize
    font.bold: true
  }
  Repeater {
    model: root.stepIndex === root.help.steps.length - 1 ? root.help.problems : []
    delegate: Text {
      required property string modelData
      width: root.width
      text: modelData
      textFormat: Text.PlainText
      color: root.foreground
      font.pixelSize: root.fontSize
      wrapMode: Text.WordWrap
    }
  }
  Repeater {
    model: root.stepIndex === root.help.steps.length - 1 ? root.help.supportLinks : []
    delegate: Ui.Button {
      required property var modelData
      width: root.width
      text: modelData.label + " ↗"
      bordered: true
      focusable: true
      onClicked: root.openLink(modelData.url)
    }
  }
}
