import QtQuick
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
  property string language: "auto"
  property string selectedAccountId: ""
  property bool settingsMode: false
  property string lastError: ""
  property bool oauthReady: false
  property int flashDurationSeconds: 60
  property bool flashUntilClicked: false
  property var alerts: ({})
  property double flashClock: Date.now()
  property string stateEpoch: ""
  property double stateRevision: -1
  property bool connected: false
  property var actionQueue: []
  property var currentAction: []
  property int requestSequence: 0
  property bool isActionRunning: false
  property bool networkBusy: false
  property string pendingDetailsId: ""
  property string actionError: ""
  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
  Connections {
    target: Commons.I18n
    function onLanguageChanged() { root.sendPacket(["language", Commons.I18n.language], 0) }
  }
  function tr(es, en) {
    if (language === "es") return es
    if (language === "en") return en
    return strings.t(en, en)
  }

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
    panelLoader.item.lastError = root.actionError || root.lastError
    panelLoader.item.oauthReady = root.oauthReady
    panelLoader.item.fontSizeOffset = root.fontSizeOffset
    panelLoader.item.panelWidth = root.panelWidth
    panelLoader.item.language = root.language
    panelLoader.item.flashDurationSeconds = root.flashDurationSeconds
    panelLoader.item.flashUntilClicked = root.flashUntilClicked
    panelLoader.item.isActionRunning = root.isActionRunning
    panelLoader.item.networkBusy = root.networkBusy
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
    pendingDetailsId = ""
    var wasSame = selectedAccountId === accountId && !settingsMode && opened
    selectedAccountId = accountId
    settingsMode = false
    selectedAnchor = anchor
    injectPanel()
    if (wasSame) close()
    else {
      open()
      if (networkBusy || isActionRunning) pendingDetailsId = accountId
      else runAction(["details", accountId])
    }
  }

  function showSettings(anchor) {
    pendingDetailsId = ""
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
    if (alert && alert.event_id) sendPacket(["ack-alert", accountId, alert.event_id], 0)
  }

  function sendPacket(args, id) {
    if (!connected) return false
    clientProcess.write(JSON.stringify({args: args, request_id: id}) + "\n")
    return true
  }

  function cancelAuthorization() { sendPacket(["cancel-auth"], 0) }

  function receivePacket(value) {
    try {
      var packet = JSON.parse(value)
      if (packet.type === "state") {
        if (!connected) {
          connected = true
          actionError = ""
          stateEpoch = packet.epoch
          stateRevision = -1
          sendPacket(["language", Commons.I18n.language], 0)
        }
        if (packet.epoch !== stateEpoch || Number(packet.revision) <= stateRevision) return
        stateRevision = Number(packet.revision)
        receiveSnapshot(value)
      } else if (packet.type === "result" && packet.request_id === requestSequence) {
        var completed = currentAction
        currentAction = []
        isActionRunning = false
        if (packet.code === "busy") {
          networkBusy = true
          if (completed[0] === "details" && opened && !settingsMode)
            pendingDetailsId = selectedAccountId
        } else if (packet.ok !== true) {
          actionError = String(packet.error || "The requested action failed")
        }
        if (packet.code !== "busy" && completed[0] === "update" && opened && !settingsMode)
          pendingDetailsId = selectedAccountId
        injectPanel()
        Qt.callLater(startNextAction)
      }
    } catch (error) {
      actionError = "Invalid response from Gmail Notifier service"
      injectPanel()
    }
  }

  function receiveSnapshot(value) {
    try {
      var result = JSON.parse(value)
      networkBusy = result.network_busy === true
      if (result.ok !== true) {
        lastError = String(result.error || "Could not read Gmail status")
        injectPanel()
        return
      }
      if (Number.isFinite(Number(result.flash_duration_seconds)))
        flashDurationSeconds = Math.max(5, Math.min(600, Number(result.flash_duration_seconds)))
      flashUntilClicked = result.flash_until_clicked === true

      if (Array.isArray(result.accounts) && JSON.stringify(accounts) !== JSON.stringify(result.accounts))
        accounts = result.accounts
      alerts = result.alerts || ({})
      pollIntervalMinutes = Number(result.poll_interval_minutes || 2)
      if (Number.isFinite(Number(result.font_size_offset))) fontSizeOffset = Number(result.font_size_offset)
      if (Number.isFinite(Number(result.panel_width))) panelWidth = Number(result.panel_width)
      language = ["en", "es"].indexOf(result.language) >= 0 ? result.language : "auto"
      oauthReady = result.oauth_ready === true
      lastError = String(result.error || result.network_error || "")
      injectPanel()
      var selected = Model.accountById(accounts, selectedAccountId)
      if (!settingsMode && selected && Model.messageCount(selected) === 0)
        selectedAnchor = manageButton
      injectPanel()
      Qt.callLater(startNextAction)
    } catch (error) {
      lastError = "Invalid response from Gmail Notifier helper"
    }
  }

  function runAction(args) {
    if (!connected) { actionError = "Gmail service is disconnected"; injectPanel(); return }
    if (["update", "details", "more-details", "add-account"].indexOf(args[0]) >= 0 &&
        (networkBusy || (isActionRunning && ["update", "details", "more-details", "add-account"].indexOf(currentAction[0]) >= 0))) {
      if (args[0] === "details") pendingDetailsId = args[1]
      return
    }
    if (args[0] === "update" && actionQueue.some(function(item) { return item[0] === "update" })) return
    if (actionQueue.length >= 32) { actionError = "Too many queued actions"; injectPanel(); return }
    actionQueue = actionQueue.concat([args])
    startNextAction()
  }

  function startNextAction() {
    if (isActionRunning || !connected) return
    if (actionQueue.length === 0) {
      if (!networkBusy && pendingDetailsId && opened && !settingsMode && pendingDetailsId === selectedAccountId) {
        var accountId = pendingDetailsId
        pendingDetailsId = ""
        runAction(["details", accountId])
      }
      return
    }
    if (networkBusy && ["update", "details", "more-details", "add-account"].indexOf(actionQueue[0][0]) >= 0) return
    currentAction = actionQueue[0]
    actionQueue = actionQueue.slice(1)
    requestSequence += 1
    actionError = ""
    isActionRunning = true
    sendPacket(currentAction, requestSequence)
    injectPanel()
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
    interval: 250
    running: Object.keys(root.alerts).some(function(id) { return root.isAccountFlashing(id) })
    repeat: true
    onTriggered: root.flashClock = Date.now()
  }

  Timer {
    id: reconnectTimer
    interval: 2000
    onTriggered: clientProcess.running = true
  }

  Process {
    id: clientProcess
    command: ["python3", root.helperPath, "watch"]
    stdinEnabled: true
    running: true
    stdout: SplitParser { onRead: function(data) { root.receivePacket(data) } }
    onExited: {
      root.connected = false
      root.isActionRunning = false
      root.networkBusy = false
      root.pendingDetailsId = ""
      root.actionQueue = []
      root.currentAction = []
      root.actionError = "Gmail service disconnected; pending actions were cancelled."
      root.injectPanel()
      reconnectTimer.restart()
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
      tooltipText: root.tr("Configuración de Gmail y añadir cuentas", "Gmail settings and add accounts")
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
        readonly property bool flashOn: Style.duration(1) === 0 || Model.alertPhase(root.alerts[account.id], root.flashClock)
        readonly property bool isFlashing: root.isAccountFlashing(account.id)
        bar: root.bar
        horizontalMargin: 2.5
        text: ""
        labelVisible: false
        hasVisualContent: true
        fixedWidth: accountLabel.implicitWidth + scaledHorizontalMargin * 2
        tooltipText: Model.escapeMarkup(account.enabled === false
          ? root.tr("%1 — pausada", "%1 — paused").arg(account.email)
          : (root.language === "auto"
            ? strings.tn("account.unread", Model.messageCount(account))
            : root.tr("%1 — %2 sin leer", "%1 — %2 unread"))
              .arg(account.email).arg(Commons.I18n.formatNumber(Model.messageCount(account))))
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
              text: accountButton.unreadCount > 99 ? "99+" : Commons.I18n.formatNumber(accountButton.unreadCount)
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


}


