import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import qs.Ui as Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "eprom.gmail-notifier"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property var accounts: []
  property string selectedAccountId: ""
  property bool settingsMode: false
  property string lastError: ""
  property bool oauthReady: false
  property int fontSizeOffset: 0
  property int panelWidth: 376
  property string language: "auto"
  property string pendingRemoveId: ""
  property int flashDurationSeconds: 60
  property bool flashUntilClicked: false
  property bool isActionRunning: false

  property color themeGreen: Color.accent
  property color themeRed: (root.bar && root.bar.urgent) ? root.bar.urgent : Color.urgent

  FileView {
    id: themeColorsView
    path: Color.currentThemePath + "/colors.toml"
    printErrors: false
    watchChanges: true
    onFileChanged: reload()
    onLoaded: {
      root.themeGreen = Color.accent
      root.themeRed = Color.urgent
      var lines = text().split("\n")
      for (var i = 0; i < lines.length; i++) {
        var matchG = lines[i].match(/^\s*green\s*=\s*["']?(#[0-9A-Fa-f]{6})/)
        if (matchG) root.themeGreen = matchG[1]
        var matchR = lines[i].match(/^\s*red\s*=\s*["']?(#[0-9A-Fa-f]{6})/)
        if (matchR) root.themeRed = matchR[1]
      }
    }
  }

  readonly property int configuredFontSize: Math.max(Style.font.caption, Style.font.body + fontSizeOffset)
  // Match the actual popup frame and Omarchy's normal foreground.
  readonly property color panelAccent: Border.color(panel.borderSpec)
  readonly property color panelText: root.foreground

  readonly property bool popoutSwitchClosing: false
  readonly property color foreground: bar ? bar.foreground : Color.foreground

  function open() { root.controller.show() }
  function close() { root.controller.hide() }
  function toggle() {
    if (root.opened) close()
    else open()
  }
  function closeForPopoutSwitch() { close() }
  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.hostWidget || root, direction)
    return false
  }
  function account(id) { return Model.accountById(accounts, id) }
  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
  function tr(es, en) {
    if (language === "en") return en
    if (language === "es") return es
    return strings.t(en, en)
  }
  function runAction(args) {
    if (!hostWidget || typeof hostWidget.runAction !== "function") return
    hostWidget.runAction(args)
  }
  function setEnabled(item) {
    runAction(["set-enabled", item.id, item.enabled === false ? "true" : "false"])
  }
  function cycleInterval(delta) {
    var value = Math.max(1, Math.min(60, Number(hostWidget.pollIntervalMinutes || 2) + delta))
    runAction(["set-interval", String(value)])
  }
  function senderDisplayName(value) {
    var sender = String(value || "Unknown sender").trim()
    var withAddress = sender.match(/^\s*(.*?)\s*<([^>]+)>\s*$/)
    if (withAddress) {
      var name = withAddress[1].trim().replace(/^"|"$/g, "")
      if (name.length > 0) return name
      sender = withAddress[2].trim()
    }
    var address = sender.match(/^([^@\s]+)@[^@\s]+$/)
    return address ? address[1] : sender
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(root.panelWidth))
    contentHeight: panel.fittedContentHeight(content.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        id: contentScroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height

        Column {
          id: content
          width: parent.width
          spacing: Style.space(10)

          Text {
            visible: root.settingsMode
            width: parent.width
            text: "GMail Notifier by Eprom"
            color: root.panelAccent
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.body
            font.bold: true
          }

          Rectangle {
            visible: root.settingsMode
            width: parent.width
            height: Math.max(2, Style.space(2))
            color: root.panelAccent
            opacity: 1.0
          }

          Text {
            visible: root.lastError.length > 0
            width: parent.width
            text: root.lastError
            textFormat: Text.PlainText
            color: root.themeRed
            wrapMode: Text.WordWrap
          }

          Loader {
            width: parent.width
            height: item ? item.implicitHeight : 0
            sourceComponent: root.settingsMode ? settingsView : accountView
          }
        }
      }
    }
  }

  Component {
    id: settingsView
    Column {
      width: parent.width
      spacing: Style.space(8)

      Row {
        width: parent.width
        height: Style.space(28)
        spacing: Style.space(8)

        Text {
          width: parent.width - (updateSettingsBtn.visible ? updateSettingsBtn.width + Style.space(8) : 0)
          text: root.tr("Cuentas configuradas", "Configured accounts")
          color: root.foreground
          font.bold: true
          font.pixelSize: Style.font.body
          anchors.verticalCenter: parent.verticalCenter
        }

        Ui.Button {
          id: updateSettingsBtn
          visible: root.accounts.length > 0
          text: root.tr("Actualizar", "Update")
          iconText: "\uf021"
          iconSpinning: root.isActionRunning
          bordered: true
          enabled: !root.isActionRunning
          fontSize: Style.font.bodySmall
          horizontalPadding: Style.space(8)
          verticalPadding: Style.space(3)
          anchors.verticalCenter: parent.verticalCenter
          onClicked: root.runAction(["update"])
        }
      }

      Text {
        visible: root.accounts.length === 0
        width: parent.width
        text: root.oauthReady
          ? root.tr("Aún no hay cuentas. Pulsa «Añadir cuenta de Gmail» para iniciar sesión con Google.", "No accounts linked yet. Choose “Add Gmail account” to sign in with Google.")
          : root.tr("Google necesita un archivo OAuth de escritorio en ~/.config/omarchy/gmail-notifier/oauth-client.json. Configúralo antes de añadir una cuenta.", "Google sign-in needs a Desktop OAuth client JSON at ~/.config/omarchy/gmail-notifier/oauth-client.json. Set it up before adding an account.")
        color: root.foreground
        wrapMode: Text.WordWrap
        font.pixelSize: Style.font.bodySmall
      }

      Ui.Button {
        visible: root.isActionRunning && root.hostWidget && root.hostWidget.currentAction[0] === "add-account"
        text: root.tr("Cancelar autorización", "Cancel authorization")
        onClicked: root.hostWidget.cancelAuthorization()
      }

      Repeater {
        model: root.accounts
        delegate: Column {
          id: accountItem
          required property var modelData
          required property int index
          width: parent.width
          spacing: Style.space(6)

          // Line 1: Reorder buttons, Status dot, Email, Initial badge
          Row {
            width: parent.width
            height: Style.space(28)
            spacing: Style.space(4)

            Ui.Button {
              text: "↑"
              bordered: true
              enabled: index > 0
              width: Style.space(24)
              height: Style.space(24)
              anchors.verticalCenter: parent.verticalCenter
              fontSize: Style.font.caption
              horizontalPadding: 0
              verticalPadding: 0
              onClicked: root.runAction(["move-account", modelData.id, "up"])
            }

            Ui.Button {
              text: "↓"
              bordered: true
              enabled: index < root.accounts.length - 1
              width: Style.space(24)
              height: Style.space(24)
              anchors.verticalCenter: parent.verticalCenter
              fontSize: Style.font.caption
              horizontalPadding: 0
              verticalPadding: 0
              onClicked: root.runAction(["move-account", modelData.id, "down"])
            }

            Text {
              width: parent.width - (Style.space(24) * 2 + Style.space(4) * 3 + initialField.width)
              text: (modelData.enabled === false ? "○ " : "● ") + modelData.email
              textFormat: Text.PlainText
              color: modelData.enabled === false ? Color.muted : root.foreground
              elide: Text.ElideRight
              font.pixelSize: Style.font.body
              anchors.verticalCenter: parent.verticalCenter
            }

            Rectangle {
              id: initialField
              width: Style.space(64)
              height: Style.space(24)
              color: "transparent"
              radius: Style.cornerRadius
              border.color: root.panelAccent
              border.width: Math.max(1, Style.normalBorderWidth)
              anchors.verticalCenter: parent.verticalCenter

              TextInput {
                id: initialInput
                anchors.fill: parent
                anchors.leftMargin: Style.space(4)
                anchors.rightMargin: Style.space(4)
                text: String(modelData.initial || "?")
                color: root.foreground
                font.pixelSize: Style.font.bodySmall
                maximumLength: 7
                horizontalAlignment: TextInput.AlignHCenter
                verticalAlignment: TextInput.AlignVCenter
                selectByMouse: true
                onEditingFinished: {
                  if (text !== String(modelData.initial || "?")) root.runAction(["set-initial", modelData.id, text])
                }
              }
            }
          }

          // Line 2: Avisos switch, Pausar/Reanudar, Borrar (Urgent Red)
          Row {
            width: parent.width
            spacing: Style.space(8)
            height: Style.space(28)

            Row {
              spacing: Style.space(5)
              anchors.verticalCenter: parent.verticalCenter

              Text {
                text: root.tr("Avisos", "Alerts")
                color: root.foreground
                font.pixelSize: Style.font.bodySmall
                anchors.verticalCenter: parent.verticalCenter
              }

              Ui.ToggleSwitch {
                checked: modelData.notifications !== false
                anchors.verticalCenter: parent.verticalCenter
                onToggled: root.runAction(["set-notifications", modelData.id,
                  modelData.notifications === false ? "true" : "false"])
              }
            }

            Item {
              width: Style.space(4)
              height: 1
            }

            Ui.Button {
              text: modelData.enabled === false ? root.tr("Reanudar", "Resume") : root.tr("Pausar", "Pause")
              bordered: true
              horizontalPadding: Style.space(8)
              verticalPadding: Style.space(3)
              fontSize: Style.font.bodySmall
              anchors.verticalCenter: parent.verticalCenter
              onClicked: root.setEnabled(modelData)
            }

            Ui.Button {
              text: root.tr("Borrar", "Remove")
              bordered: true
              foreground: root.themeRed
              accent: root.themeRed
              borderSpec: Border.flat(root.themeRed, Math.max(1, Style.normalBorderWidth))
              horizontalPadding: Style.space(8)
              verticalPadding: Style.space(3)
              fontSize: Style.font.bodySmall
              anchors.verticalCenter: parent.verticalCenter
              onClicked: root.pendingRemoveId = modelData.id
            }
          }

          // Line 3: Deletion confirmation
          Row {
            visible: root.pendingRemoveId === modelData.id
            spacing: Style.space(6)
            height: Style.space(28)

            Text {
              text: root.tr("¿Borrar esta cuenta?", "Remove this account?")
              color: root.themeRed
              font.pixelSize: Style.font.bodySmall
              anchors.verticalCenter: parent.verticalCenter
            }

            Ui.Button {
              text: root.tr("Cancelar", "Cancel")
              bordered: true
              horizontalPadding: Style.space(7)
              verticalPadding: Style.space(3)
              fontSize: Style.font.bodySmall
              anchors.verticalCenter: parent.verticalCenter
              onClicked: root.pendingRemoveId = ""
            }

            Ui.Button {
              text: root.tr("Confirmar borrado", "Confirm remove")
              bordered: true
              foreground: root.themeRed
              accent: root.themeRed
              borderSpec: Border.flat(root.themeRed, Math.max(1, Style.normalBorderWidth))
              horizontalPadding: Style.space(7)
              verticalPadding: Style.space(3)
              fontSize: Style.font.bodySmall
              anchors.verticalCenter: parent.verticalCenter
              onClicked: {
                root.pendingRemoveId = ""
                root.runAction(["remove-account", modelData.id])
              }
            }
          }

          Rectangle {
            visible: index < root.accounts.length - 1
            width: parent.width
            height: Style.space(1)
            color: root.panelAccent
            opacity: 0.5
          }
        }
      }

      Rectangle { width: parent.width; height: Style.space(1); color: root.panelAccent; opacity: 0.8 }

      // Settings rows
      Row {
        spacing: Style.space(6)
        Text { text: root.tr("Idioma", "Language"); color: root.foreground; font.pixelSize: Style.font.bodySmall; anchors.verticalCenter: parent.verticalCenter }
        Ui.Button {
          text: root.tr("Sistema", "System"); bordered: true
          enabled: root.language !== "auto"
          onClicked: root.runAction(["set-display", "language", "auto"])
        }
        Ui.Button {
          text: "English"; bordered: true; horizontalPadding: Style.space(7); verticalPadding: Style.space(2)
          enabled: root.language !== "en"
          onClicked: root.runAction(["set-display", "language", "en"])
        }
        Ui.Button {
          text: "Español"; bordered: true; horizontalPadding: Style.space(7); verticalPadding: Style.space(2)
          enabled: root.language !== "es"
          onClicked: root.runAction(["set-display", "language", "es"])
        }
      }

      Row {
        spacing: Style.space(8)
        height: Style.space(28)
        Text { text: root.tr("Comprobar cada", "Check every"); color: root.foreground; font.pixelSize: Style.font.bodySmall; anchors.verticalCenter: parent.verticalCenter }
        Ui.Button {
          text: "−"
          bordered: true
          width: Style.space(24)
          height: Style.space(24)
          anchors.verticalCenter: parent.verticalCenter
          fontSize: Style.font.bodySmall
          horizontalPadding: 0
          verticalPadding: 0
          onClicked: root.cycleInterval(-1)
        }
        Text {
          text: Commons.I18n.formatNumber(root.hostWidget ? root.hostWidget.pollIntervalMinutes : 2) + " min"
          color: root.foreground
          font.pixelSize: Style.font.bodySmall
          anchors.verticalCenter: parent.verticalCenter
        }
        Ui.Button {
          text: "+"
          bordered: true
          width: Style.space(24)
          height: Style.space(24)
          anchors.verticalCenter: parent.verticalCenter
          fontSize: Style.font.bodySmall
          horizontalPadding: 0
          verticalPadding: 0
          onClicked: root.cycleInterval(1)
        }
      }

      // Flash alert settings
      Row {
        spacing: Style.space(8)
        height: Style.space(28)
        Text {
          text: root.tr("Parpadear hasta hacer clic", "Flash until clicked")
          color: root.foreground
          font.pixelSize: Style.font.bodySmall
          anchors.verticalCenter: parent.verticalCenter
        }
        Ui.ToggleSwitch {
          checked: root.flashUntilClicked
          anchors.verticalCenter: parent.verticalCenter
          onToggled: root.runAction(["set-display", "flash-until-clicked", root.flashUntilClicked ? "false" : "true"])
        }
      }

      Row {
        visible: !root.flashUntilClicked
        spacing: Style.space(8)
        height: Style.space(28)
        Text {
          text: root.tr("Duración del aviso", "Alert duration")
          color: root.foreground
          font.pixelSize: Style.font.bodySmall
          anchors.verticalCenter: parent.verticalCenter
        }
        Ui.Button {
          text: "−"
          bordered: true
          width: Style.space(24)
          height: Style.space(24)
          anchors.verticalCenter: parent.verticalCenter
          fontSize: Style.font.bodySmall
          horizontalPadding: 0
          verticalPadding: 0
          onClicked: {
            var next = Math.max(5, root.flashDurationSeconds - 10)
            root.runAction(["set-display", "flash-duration-seconds", String(next)])
          }
        }
        Text {
          text: Commons.I18n.formatNumber(root.flashDurationSeconds) + " s"
          color: root.foreground
          font.pixelSize: Style.font.bodySmall
          anchors.verticalCenter: parent.verticalCenter
        }
        Ui.Button {
          text: "+"
          bordered: true
          width: Style.space(24)
          height: Style.space(24)
          anchors.verticalCenter: parent.verticalCenter
          fontSize: Style.font.bodySmall
          horizontalPadding: 0
          verticalPadding: 0
          onClicked: {
            var next = Math.min(600, root.flashDurationSeconds + 10)
            root.runAction(["set-display", "flash-duration-seconds", String(next)])
          }
        }
      }

      Row {
        spacing: Style.space(8)
        height: Style.space(28)
        Text { text: root.tr("Tamaño del texto", "Text size"); color: root.foreground; font.pixelSize: Style.font.bodySmall; anchors.verticalCenter: parent.verticalCenter }
        Ui.Button {
          text: "−"; bordered: true; width: Style.space(24); height: Style.space(24)
          anchors.verticalCenter: parent.verticalCenter
          fontSize: Style.font.bodySmall; horizontalPadding: 0; verticalPadding: 0
          onClicked: root.runAction(["set-display", "font-size-offset", String(root.fontSizeOffset - 1)])
        }
        Text { text: Commons.I18n.formatNumber(root.configuredFontSize) + " px"; color: root.foreground; font.pixelSize: Style.font.bodySmall; anchors.verticalCenter: parent.verticalCenter }
        Ui.Button {
          text: "+"; bordered: true; width: Style.space(24); height: Style.space(24); anchors.verticalCenter: parent.verticalCenter
          fontSize: Style.font.bodySmall; horizontalPadding: 0; verticalPadding: 0
          onClicked: root.runAction(["set-display", "font-size-offset", String(root.fontSizeOffset + 1)])
        }
      }

      Row {
        spacing: Style.space(8)
        height: Style.space(28)
        Text { text: root.tr("Ancho del panel", "Panel width"); color: root.foreground; font.pixelSize: Style.font.bodySmall; anchors.verticalCenter: parent.verticalCenter }
        Ui.Button {
          text: "−"; bordered: true; width: Style.space(24); height: Style.space(24); anchors.verticalCenter: parent.verticalCenter
          fontSize: Style.font.bodySmall; horizontalPadding: 0; verticalPadding: 0
          onClicked: root.runAction(["set-display", "panel-width", String(root.panelWidth - 24)])
        }
        Text { text: Commons.I18n.formatNumber(root.panelWidth) + " px"; color: root.foreground; font.pixelSize: Style.font.bodySmall; anchors.verticalCenter: parent.verticalCenter }
        Ui.Button {
          text: "+"; bordered: true; width: Style.space(24); height: Style.space(24); anchors.verticalCenter: parent.verticalCenter
          fontSize: Style.font.bodySmall; horizontalPadding: 0; verticalPadding: 0
          onClicked: root.runAction(["set-display", "panel-width", String(root.panelWidth + 24)])
        }
      }

      // Add Gmail Account Button (Themed Success Green with thick border)
      Ui.Button {
        width: parent.width
        text: root.tr("Añadir cuenta de Gmail", "Add Gmail account")
        iconText: "\uf0e0"
        leftAlign: true
        bordered: true
        focusable: true
        foreground: root.themeGreen
        accent: root.themeGreen
        borderSpec: Border.flat(root.themeGreen, Math.max(2, Style.space(2)))
        horizontalPadding: Style.space(12)
        verticalPadding: Style.space(8)
        onClicked: {
          root.lastError = ""
          root.runAction(["add-account"])
        }
      }

      Text {
        width: parent.width
        text: root.tr("Solo se cuentan los mensajes sin leer de Recibidos. Los pospuestos salen de Recibidos. El plugin lee solo las cabeceras, nunca el contenido.", "Only unread Inbox messages are counted. Snoozed mail leaves Inbox. The plugin reads headers only; it never reads message bodies.")
        color: root.foreground
        wrapMode: Text.WordWrap
        font.pixelSize: Style.font.bodySmall
      }
    }
  }

  Component {
    id: accountView
    Column {
      width: parent.width
      spacing: Style.space(8)
      readonly property var selected: root.account(root.selectedAccountId)

      Row {
        width: parent.width
        height: Style.space(28)
        spacing: Style.space(8)

        Text {
          width: parent.width - updateAccountBtn.width - Style.space(8)
          text: parent.parent.selected ? parent.parent.selected.email : "No account selected"
          textFormat: Text.PlainText
          color: root.panelAccent
          font.bold: true
          font.pixelSize: root.configuredFontSize
          elide: Text.ElideRight
          anchors.verticalCenter: parent.verticalCenter
        }

        Ui.Button {
          id: updateAccountBtn
          text: root.tr("Actualizar", "Update")
          iconText: "\uf021"
          iconSpinning: root.isActionRunning
          bordered: true
          enabled: !root.isActionRunning
          fontSize: Style.font.bodySmall
          horizontalPadding: Style.space(8)
          verticalPadding: Style.space(3)
          anchors.verticalCenter: parent.verticalCenter
          onClicked: root.runAction(["update"])
        }
      }

      Rectangle {
        visible: parent.selected && parent.selected.messages.length > 0
        width: parent.width
        height: Style.space(1)
        color: root.panelAccent
        opacity: 0.8
      }

      Text {
        visible: parent.selected && parent.selected.messages.length === 0
        width: parent.width
        text: parent.selected && parent.selected.unread_count > 0 && parent.selected.details_ready !== true
          ? root.isActionRunning ? root.tr("Cargando remitente y asunto…", "Loading sender and subject…") : root.tr("Pulsa Cargar mensajes para reintentar", "Choose Load messages to retry")
          : root.tr("No hay mensajes sin leer en Recibidos", "No unread messages in Inbox")
        color: root.panelText
        font.pixelSize: root.configuredFontSize
      }

      Row {
        spacing: Style.space(8)
        visible: parent.selected && (parent.selected.details_ready !== true || parent.selected.details_more === true)
        Ui.Button {
          text: root.tr("Cargar mensajes", "Load messages")
          enabled: !root.isActionRunning
          onClicked: root.runAction(["more-details", root.selectedAccountId])
        }
      }

      Repeater {
        model: parent.selected ? parent.selected.messages : []
        delegate: Column {
          required property var modelData
          width: parent.width
          spacing: Style.space(5)

          Text {
            width: parent.width
            text: root.senderDisplayName(modelData.from)
            textFormat: Text.PlainText
            color: root.panelAccent
            font.bold: false
            font.pixelSize: root.configuredFontSize
            elide: Text.ElideRight
          }
          Text {
            width: parent.width
            text: modelData.subject || root.tr("(sin asunto)", "(no subject)")
            textFormat: Text.PlainText
            color: root.panelText
            font.pixelSize: root.configuredFontSize
            elide: Text.ElideRight
            maximumLineCount: 1
          }
          Rectangle {
            width: parent.width
            height: Style.space(1)
            color: root.panelAccent
            opacity: 0.8
          }
        }
      }
    }
  }

}

