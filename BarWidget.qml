import QtQuick
import QtQml.Models
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "eprom.gmail-notifier"

  property var accounts: []
  property int pollIntervalMinutes: 2
  property int fontSizeOffset: 0
  property int panelWidth: 376
  property string language: "en"
  property string selectedAccountId: ""
  property bool settingsMode: false
  property string lastError: ""
  property bool oauthReady: false
  property int flashDurationSeconds: 60
  property bool flashUntilClicked: false
  property var alerts: ({})
  property double flashClock: Date.now()
  property var pendingAcks: []
  property bool stateRefreshPending: false

  component EnvelopeIcon: Item {
    id: envelopeRoot
    property color iconColor: root.bar ? root.bar.foreground : Color.foreground
    implicitWidth: Style.bar.iconCanvas
    implicitHeight: Style.bar.iconCanvas

    Image {
      id: envelopeSource
      anchors.fill: parent
      source: Qt.resolvedUrl("assets/envelope.svg")
      fillMode: Image.PreserveAspectFit
      sourceSize.width: Math.round(width * 2)
      sourceSize.height: Math.round(height * 2)
      visible: false
      layer.enabled: true
    }

    MultiEffect {
      anchors.fill: envelopeSource
      source: envelopeSource
      colorization: 1.0
      colorizationColor: envelopeRoot.iconColor
    }
  }

  readonly property bool opened: panelLoader.item
    ? panelLoader.item.opened === true
    : false
  readonly property bool popoutSwitchClosing: panelLoader.item
    ? panelLoader.item.popoutSwitchClosing === true
    : false

  function injectPanel() {
    if (!panelLoader.item) return
    panelLoader.item.bar = root.bar
    panelLoader.item.anchorItem = settingsMode ? manageButton : selectedAnchor
    panelLoader.item.hostWidget = root
    panelLoader.item.accounts = root.accounts
    panelLoader.item.selectedAccountId = root.selectedAccountId
    panelLoader.item.settingsMode = root.settingsMode
    panelLoader.item.lastError = root.lastError
    panelLoader.item.oauthReady = root.oauthReady
    panelLoader.item.fontSizeOffset = root.fontSizeOffset
    panelLoader.item.panelWidth = root.panelWidth
    panelLoader.item.language = root.language
    panelLoader.item.flashDurationSeconds = root.flashDurationSeconds
    panelLoader.item.flashUntilClicked = root.flashUntilClicked
    panelLoader.item.isActionRunning = actionProcess.running
  }

  function open() {
    if (accounts.length === 0) {
      settingsMode = true
      selectedAnchor = manageButton
    } else if (!Model.visibleAccounts(accounts).length) {
      settingsMode = true
    }
    injectPanel()
    if (panelLoader.item) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item) panelLoader.item.close()
  }

  function toggle() {
    if (panelLoader.item) panelLoader.item.toggle()
  }

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  function showAccount(accountId, anchor) {
    var wasSame = selectedAccountId === accountId && !settingsMode && opened
    selectedAccountId = accountId
    settingsMode = false
    selectedAnchor = anchor
    injectPanel()
    if (wasSame) close()
    else {
      open()
      runAction(["details", accountId])
    }
  }

  function showSettings(anchor) {
    settingsMode = true
    selectedAnchor = anchor || (root.accounts.length === 0 ? manageButton : selectedAnchor)
    injectPanel()
    if (!opened) open()
  }

  function isAccountFlashing(accountId) {
    return Model.isAlertActive(alerts[accountId], flashClock)
  }

  function stopFlashing(accountId) {
    var alert = alerts[accountId]
    if (!alert || !alert.event_id) return
    pendingAcks = pendingAcks.concat([[accountId, alert.event_id]])
    sendNextAck()
  }

  function sendNextAck() {
    if (ackProcess.running || pendingAcks.length === 0) return
    var args = pendingAcks[0]
    pendingAcks = pendingAcks.slice(1)
    ackProcess.command = ["python3", helperPath, "ack-alert"].concat(args)
    ackProcess.running = true
  }

  function refreshState() {
    if (stateProcess.running) { stateRefreshPending = true; return }
    stateProcess.running = true
  }

  function receiveSnapshot(value) {
    try {
      var result = JSON.parse(value)
      if (result.ok !== true) {
        lastError = String(result.error || "Could not read Gmail status")
        injectPanel()
        return
      }
      if (Number.isFinite(Number(result.flash_duration_seconds)))
        flashDurationSeconds = Math.max(5, Math.min(600, Number(result.flash_duration_seconds)))
      flashUntilClicked = result.flash_until_clicked === true

      if (Array.isArray(result.accounts)) accounts = result.accounts
      alerts = result.alerts || ({})
      pollIntervalMinutes = Number(result.poll_interval_minutes || 2)
      if (Number.isFinite(Number(result.font_size_offset))) fontSizeOffset = Number(result.font_size_offset)
      if (Number.isFinite(Number(result.panel_width))) panelWidth = Number(result.panel_width)
      language = result.language === "en" ? "en" : "es"
      oauthReady = result.oauth_ready === true
      lastError = String(result.error || "")
      injectPanel()
      var selected = Model.accountById(accounts, selectedAccountId)
      if (!settingsMode && selected && Model.messageCount(selected) === 0)
        selectedAnchor = manageButton
      injectPanel()
      if (!settingsMode && opened && selected && selected.details_ready === false && !actionProcess.running)
        runAction(["details", selectedAccountId])
    } catch (error) {
      lastError = "Invalid response from Gmail Notifier helper"
    }
  }

  function actionFinished(value) {
    try {
      var result = JSON.parse(value)
      if (result.ok !== true) {
        lastError = String(result.error || "The requested action failed")
        injectPanel()
      } else refreshState()
    } catch (error) {
      lastError = "Invalid response from Gmail Notifier helper"
      injectPanel()
    }
  }

  function refresh() {
    if (!snapshotProcess.running) snapshotProcess.running = true
  }

  function runAction(arguments) {
    if (actionProcess.running) return
    actionProcess.command = ["python3", helperPath].concat(arguments)
    actionProcess.running = true
  }

  function applyAccountAction(action, accountId, value) {
    runAction([action, accountId, String(value)])
  }

  property var selectedAnchor: null
  readonly property string helperPath: decodeURIComponent(
    String(Qt.resolvedUrl("helper/main.py")).replace("file://", ""))

  implicitWidth: row.implicitWidth
  implicitHeight: row.implicitHeight
  onBarChanged: injectPanel()
  onAccountsChanged: injectPanel()
  onSettingsModeChanged: injectPanel()
  onSelectedAccountIdChanged: injectPanel()

  Timer {
    // Each bar instance refreshes the shared local snapshot frequently; the
    // helper itself contacts Gmail only once per configured poll interval.
    interval: 15000
    repeat: true
    running: true
    onTriggered: root.refresh()
  }

  // Local state is independent of Gmail polling and remains live while paused.
  Timer { interval: 250; running: true; repeat: true; onTriggered: root.flashClock = Date.now() }
  Timer { interval: 5000; running: true; repeat: true; onTriggered: root.refreshState() }

  Instantiator {
    model: ["snapshot.json", "alerts.json", "config.json"]
    delegate: FileView {
      required property string modelData
      path: Quickshell.env("HOME") + "/.config/omarchy/gmail-notifier/" + modelData
      watchChanges: true
      printErrors: false
      onFileChanged: { reload(); root.refreshState() }
    }
  }

  Process {
    id: stateProcess
    command: ["python3", root.helperPath, "state"]
    stdout: StdioCollector { onStreamFinished: { if (text.length > 0) root.receiveSnapshot(text) } }
    onExited: {
      if (root.stateRefreshPending) {
        root.stateRefreshPending = false
        Qt.callLater(root.refreshState)
      }
    }
  }

  Process {
    id: ackProcess
    stdout: StdioCollector { onStreamFinished: { if (text.length > 0) root.actionFinished(text) } }
    onExited: {
      root.refreshState()
      Qt.callLater(root.sendNextAck)
    }
  }

  Process {
    id: snapshotProcess
    command: ["python3", root.helperPath, "snapshot"]
    stdout: StdioCollector {
      id: snapshotOutput
      // A periodic/manual Gmail poll returns the fresh account snapshot.
      // Do not route it through actionFinished(), which only schedules a
      // local-state refresh and would leave the visible counts stale.
      onStreamFinished: { if (text.length > 0) root.receiveSnapshot(text) }
    }
    onExited: function(exitCode) {
      if (exitCode !== 0 && snapshotOutput.text.length === 0)
        root.lastError = "Gmail Notifier helper could not start"
    }
  }

  Process {
    id: actionProcess
    onRunningChanged: root.injectPanel()
    stdout: StdioCollector {
      id: actionOutput
      onStreamFinished: {
        if (text.length > 0) root.actionFinished(text)
      }
    }
    onExited: function(exitCode) {
      if (exitCode !== 0 && actionOutput.text.length === 0)
        root.lastError = "The requested action did not complete"
      root.refresh()
    }
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  Row {
    id: row
    spacing: Style.space(2)

    WidgetButton {
      id: manageButton
      bar: root.bar
      horizontalMargin: 2.5
      text: ""
      labelVisible: false
      hasVisualContent: true
      fixedWidth: manageEnvelope.implicitWidth + scaledHorizontalMargin * 2
      tooltipText: "Gmail settings and add accounts"
      onPressed: function(buttonCode) {
        if (buttonCode === Qt.LeftButton) root.showSettings(manageButton)
      }

      EnvelopeIcon {
        id: manageEnvelope
        anchors.centerIn: parent
        iconColor: manageButton.foreground
      }
    }

    Repeater {
      model: Model.visibleAccounts(root.accounts)

      delegate: WidgetButton {
        id: accountButton
        required property var modelData
        readonly property var account: modelData
        readonly property int unreadCount: account.enabled === false ? 0 : Model.messageCount(account)
        readonly property bool flashOn: Model.alertPhase(root.alerts[account.id], root.flashClock)
        readonly property bool isFlashing: root.isAccountFlashing(account.id)
        bar: root.bar
        horizontalMargin: 2.5
        text: ""
        labelVisible: false
        hasVisualContent: true
        fixedWidth: accountLabel.implicitWidth + scaledHorizontalMargin * 2
        tooltipText: account.enabled === false
          ? account.email + " — paused (click to manage)"
          : account.email + " — " + Model.messageCount(account) + " unread"
        onPressed: function(buttonCode) {
          root.stopFlashing(account.id)
          if (buttonCode === Qt.LeftButton) {
            if (account.enabled === false) root.showSettings(accountButton)
            else root.showAccount(account.id, accountButton)
          }
          else if (buttonCode === Qt.RightButton) root.showSettings(accountButton)
        }

        Row {
          id: accountLabel
          anchors.centerIn: parent
          spacing: Style.space(3)

          Text {
            text: Model.normalizedInitial(accountButton.account.initial, accountButton.account.email)
            textFormat: Text.PlainText
            color: accountButton.account.enabled === false
              ? Qt.rgba(accountButton.foreground.r, accountButton.foreground.g, accountButton.foreground.b, 0.45)
              : accountButton.foreground
            font.family: accountButton.fontFamily
            font.pixelSize: accountButton.fontSize
            verticalAlignment: Text.AlignVCenter
          }

          Rectangle {
            id: countBadge
            readonly property bool active: accountButton.unreadCount > 0 && accountButton.account.enabled !== false
            readonly property bool flashFill: accountButton.isFlashing && accountButton.flashOn
            width: Style.space(24)
            height: Style.space(15)
            radius: Style.space(3)
            color: flashFill ? accountButton.activeColor : "transparent"
            border.width: Style.space(1)
            border.color: active ? accountButton.activeColor
              : accountButton.account.enabled === false
                ? Qt.rgba(accountButton.foreground.r, accountButton.foreground.g, accountButton.foreground.b, 0.45)
                : Qt.darker(accountButton.foreground, 1.7)
            anchors.verticalCenter: parent.verticalCenter

            Text {
              id: countLabel
              anchors.centerIn: parent
              text: accountButton.unreadCount > 99 ? "99+" : String(accountButton.unreadCount)
              textFormat: Text.PlainText
              color: countBadge.flashFill ? Color.background
                : countBadge.active ? accountButton.activeColor
                : accountButton.account.enabled === false
                ? Qt.rgba(accountButton.foreground.r, accountButton.foreground.g, accountButton.foreground.b, 0.45)
                : accountButton.foreground
              font.family: accountButton.fontFamily
              font.pixelSize: Math.min(accountButton.fontSize, Style.font.caption)
              verticalAlignment: Text.AlignVCenter
              horizontalAlignment: Text.AlignHCenter
            }
          }
        }
      }
    }

  }

  Component.onCompleted: { refreshState(); refresh() }
}

