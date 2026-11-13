.pragma library

// Static help only. No credentials, filesystem changes or automatic sign-in.
function isSpanish(language) {
  return String(language || "en").toLowerCase().replace(/_/g, "-").split("-")[0] === "es"
}

function guide(language, existingAccounts) {
  var es = isSpanish(language)
  function t(en, spanish) { return es ? spanish : en }
  function link(label, spanish, url) {
    return {label: t(label, spanish), url: url + "?hl=" + (es ? "es" : "en")}
  }
  var result = {
    title: t("Set up Google sign-in", "Configura el acceso con Google"),
    intro: t("The plugin is installed. Google needs a small settings file called an OAuth client before you can connect Gmail. Follow one step at a time; you can return to this guide while you use your browser.",
             "El plugin está instalado. Google necesita un pequeño archivo de configuración llamado cliente OAuth antes de conectar Gmail. Sigue un paso cada vez; puedes volver a esta guía mientras usas el navegador."),
    existing: t("Already using the plugin? Updates keep your accounts and saved sign-in. If the file is missing, restore your ORIGINAL oauth-client.json from your own computer or private backup. Do not replace it with a new client or remove your accounts. A new client cannot reuse the old client's authorization.",
                "¿Ya usabas el plugin? Las actualizaciones conservan tus cuentas y tu autorización. Si falta el archivo, recupera tu oauth-client.json ORIGINAL desde tu propio ordenador o una copia privada. No lo sustituyas por un cliente nuevo ni borres tus cuentas. Un cliente nuevo no puede reutilizar la autorización del anterior."),
    privacy: t("Keep the JSON private. Never upload it to GitHub or paste it into a chat. The plugin asks for email labels and headers, not message bodies or permission to send/delete mail.",
               "Guarda el JSON en privado. Nunca lo subas a GitHub ni lo pegues en un chat. El plugin pide etiquetas y cabeceras del correo, no el contenido de los mensajes ni permiso para enviar o borrar correo."),
    stepLabel: t("Step %1 of %2", "Paso %1 de %2"),
    previous: t("Previous", "Anterior"),
    next: t("Next", "Siguiente"),
    back: t("Back to settings", "Volver a ajustes"),
    check: t("Check setup", "Comprobar configuración"),
    add: t("Add Gmail account", "Añadir cuenta de Gmail"),
    ready: t("Your client file is ready. You can now connect a Gmail account.",
             "El archivo de tu cliente está listo. Ya puedes conectar una cuenta de Gmail."),
    savedReady: t("Your client file is ready. Return to settings and update your saved accounts; you do not need to add them again.",
                  "El archivo del cliente está listo. Vuelve a ajustes y actualiza tus cuentas guardadas; no necesitas añadirlas otra vez."),
    missing: t("The client file is not here yet. Complete the file step, then choose Check setup.",
               "Aún falta el archivo del cliente. Completa el paso del archivo y pulsa Comprobar configuración."),
    invalid: t("The file is not a valid Desktop app JSON. Keep your saved accounts. Check that you downloaded the Desktop app client and copied the whole JSON, not an API key or a Web application client.",
               "El archivo no es un JSON válido de aplicación de escritorio. Conserva tus cuentas. Comprueba que descargaste el cliente de escritorio y copiaste todo el JSON, no una clave de API ni un cliente de aplicación web."),
    unreadable: t("The client file cannot be read. Check its location and owner-only permissions in the file step. Do not delete your accounts or credentials.",
                  "No se puede leer el archivo del cliente. Comprueba su ubicación y los permisos del paso del archivo. No borres tus cuentas ni tus credenciales."),
    troubleshooting: t("Need a hand?", "¿Necesitas una pista?"),
    problems: [
      t("Access blocked / access_denied: select the same Google project and add the Gmail address under Audience → Test users if the app is still in Testing. For a work/school account, ask the administrator if access is blocked.",
        "Acceso bloqueado / access_denied: selecciona el mismo proyecto y añade la dirección de Gmail en Público (Audience) → Usuarios de prueba si la app sigue en Pruebas. En una cuenta de trabajo o estudios, consulta al administrador si bloquea el acceso."),
      t("Google has not verified this app: check that it is your OWN project/client and that the access matches this guide. Read Google's explanation below. If you decide to proceed with your own client, Google may offer Advanced → Go to your app. Do not do this for an unknown app. An administrator block needs your administrator's help.",
        "Google no ha verificado esta aplicación: comprueba que es tu PROPIO proyecto/cliente y que los permisos coinciden con esta guía. Lee la explicación de Google abajo. Si decides continuar con tu propio cliente, Google puede mostrar Configuración avanzada → Ir a tu app. No lo hagas con una app desconocida. Un bloqueo del administrador requiere su ayuda."),
      t("Asked to sign in again after about seven days? Check the app's Testing status in the publishing step. Plugin updates do not reset sign-in, but Google can expire or revoke its grants. Keep the same client and saved accounts.",
        "¿Pide iniciar sesión otra vez tras unos siete días? Revisa el estado Pruebas del paso de publicación. Las actualizaciones del plugin no reinician la autorización, pero Google puede caducarla o revocarla. Conserva el mismo cliente y las cuentas guardadas."),
      t("Another computer: you may reuse your own client JSON. Connect accounts once on the new computer because their saved tokens are in each computer's private keyring. An update on the same computer reuses that keyring.",
        "Otro ordenador: puedes reutilizar tu propio JSON del cliente. Conecta las cuentas una vez en el ordenador nuevo porque sus tokens se guardan en el llavero privado de cada equipo. Una actualización en el mismo equipo reutiliza ese llavero.")
    ],
    supportLinks: [
      link("Google: sign-in warnings", "Google: avisos de acceso", "https://support.google.com/cloud/answer/7454865"),
      link("Google: authorization expiry", "Google: caducidad del acceso", "https://developers.google.com/identity/protocols/oauth2")
    ],
    steps: [
      {
        title: t("Create a Google project", "Crea un proyecto de Google"),
        paragraphs: [
          t("Open Google Cloud below and sign in with your Google account. At the top, open the project selector → New project. Name it, for example, My Mail Notifier, then choose Create.",
            "Abre Google Cloud con el botón de abajo e inicia sesión con tu cuenta de Google. Arriba, abre el selector de proyectos → Nuevo proyecto. Ponle, por ejemplo, Mi avisador de correo y pulsa Crear."),
          t("Select that project at the top of the page. A project is just a folder for these Google settings. Use this SAME project in every step. Already have your original client? Restore that file instead of creating another project.",
            "Selecciona ese proyecto arriba. Un proyecto es como una carpeta para estos ajustes de Google. Usa el MISMO proyecto en todos los pasos. ¿Ya tienes tu cliente original? Recupera ese archivo en lugar de crear otro proyecto.")
        ],
        links: [link("Open Google Cloud", "Abrir Google Cloud", "https://console.cloud.google.com/projectcreate")]
      },
      {
        title: t("Enable Gmail API", "Activa la API de Gmail"),
        paragraphs: [
          t("With your project selected, open Gmail API below. Choose Enable. If you see Manage, it is already enabled. This lets your project ask Gmail for the unread message list.",
            "Con tu proyecto seleccionado, abre la API de Gmail con el botón de abajo. Pulsa Habilitar. Si aparece Administrar, ya está activada. Así tu proyecto podrá consultar la lista de mensajes sin leer de Gmail.")
        ],
        links: [link("Open Gmail API", "Abrir API de Gmail", "https://console.cloud.google.com/apis/library/gmail.googleapis.com")]
      },
      {
        title: t("Tell Google who will use it", "Indica a Google quién la usará"),
        paragraphs: [
          t("Open Google Auth Platform → Branding. Choose Get started if asked. Enter your app name, your own support email and contact email. Choose External for personal Gmail accounts. Read Google's terms and finish creating the app.",
            "Abre Google Auth Platform → Desarrollo de la marca (Branding). Pulsa Comenzar si aparece. Escribe el nombre de tu app, tu correo de asistencia y tu correo de contacto. Elige Externo para cuentas personales de Gmail. Lee las condiciones de Google y termina de crearla."),
          t("Open Audience. While the app is in Testing, use Add users under Test users and add EVERY Gmail address you want to connect. An Internal app is only for its own Google Workspace organization. Menu names may differ slightly with Google's language.",
            "Abre Público (Audience). Mientras esté en Pruebas, pulsa Añadir usuarios en Usuarios de prueba y añade CADA dirección de Gmail que quieras conectar. Una app Interna solo sirve para su propia organización de Google Workspace. Los nombres pueden variar un poco según el idioma de Google.")
        ],
        links: [link("Open Branding", "Abrir Branding", "https://console.cloud.google.com/auth/branding"),
                link("Open Audience", "Abrir Público", "https://console.cloud.google.com/auth/audience")]
      },
      {
        title: t("Choose the small permission we need", "Elige solo el permiso necesario"),
        paragraphs: [
          t("Open Data Access → Add or remove scopes. Search for the exact scope below, select it, then Update and Save. Google calls it restricted, even though it only reads labels and headers. Do not add gmail.readonly, gmail.modify or full mail access.",
            "Abre Acceso a los datos (Data Access) → Añadir o quitar permisos. Busca el permiso exacto de abajo, selecciónalo y pulsa Actualizar y Guardar. Google lo llama restringido, aunque solo lee etiquetas y cabeceras. No añadas gmail.readonly, gmail.modify ni acceso completo al correo.")
        ],
        code: "https://www.googleapis.com/auth/gmail.metadata",
        links: [link("Open Data Access", "Abrir Acceso a los datos", "https://console.cloud.google.com/auth/scopes"),
                link("Google: Gmail permissions", "Google: permisos de Gmail", "https://developers.google.com/workspace/gmail/api/auth/scopes")]
      },
      {
        title: t("Create a Desktop app client", "Crea un cliente de escritorio"),
        paragraphs: [
          t("Open Clients → Create client. For Application type choose Desktop app, give it a name such as Omarchy computer, then Create. Download the JSON file when Google offers it and keep it private.",
            "Abre Clientes (Clients) → Crear cliente. En Tipo de aplicación elige Aplicación de escritorio, ponle un nombre como Ordenador Omarchy y pulsa Crear. Descarga el archivo JSON cuando Google lo ofrezca y guárdalo en privado."),
          t("Choose Desktop app, not Web application, API key or Service account. You do not need to type a redirect address: the plugin sets up the local callback. Keep this same client for future plugin updates.",
            "Elige Aplicación de escritorio, no Aplicación web, Clave de API ni Cuenta de servicio. No necesitas escribir una dirección de redirección: el plugin prepara la conexión local. Conserva este mismo cliente para las futuras actualizaciones.")
        ],
        links: [link("Open Clients", "Abrir Clientes", "https://console.cloud.google.com/auth/clients"),
                link("Google: create a client", "Google: crear un cliente", "https://developers.google.com/workspace/guides/create-credentials")]
      },
      {
        title: t("Put the file in its home", "Coloca el archivo en su sitio"),
        paragraphs: [
          t("In your file manager, open Downloads and find the JSON you just downloaded (its name often starts with client_secret). Rename it to exactly oauth-client.json, without adding .txt. This is the whole downloaded file; do not edit its contents.",
            "En el gestor de archivos, abre Descargas y busca el JSON que acabas de descargar (su nombre suele empezar por client_secret). Renómbralo exactamente oauth-client.json, sin añadir .txt. Es el archivo descargado completo: no edites su contenido."),
          t("Open your Home folder and press Ctrl+H to show hidden folders. Go into .config → omarchy → gmail-notifier, creating missing folders. Copy oauth-client.json there. If that file already exists, STOP and keep the original; never overwrite a working client just to update the plugin.",
            "Abre tu carpeta personal y pulsa Ctrl+H para ver las carpetas ocultas. Entra en .config → omarchy → gmail-notifier y crea las carpetas que falten. Copia ahí oauth-client.json. Si ese archivo ya existe, PARA y conserva el original; nunca sobrescribas un cliente que funciona para actualizar el plugin."),
          t("After copying it, open a terminal and paste the two lines below. They make the folder/file private to your user. The ~ symbol means your Home folder. Keep a private copy of the ORIGINAL client for recovery.",
            "Después de copiarlo, abre una terminal y pega las dos líneas de abajo. Dejan la carpeta y el archivo privados para tu usuario. El símbolo ~ significa tu carpeta personal. Conserva una copia privada del cliente ORIGINAL para poder recuperarlo.")
        ],
        location: "~/.config/omarchy/gmail-notifier/oauth-client.json",
        code: "chmod 700 ~/.config/omarchy/gmail-notifier\nchmod 600 ~/.config/omarchy/gmail-notifier/oauth-client.json",
        links: []
      },
      {
        title: t("Avoid the seven-day test limit", "Evita el límite de siete días de pruebas"),
        paragraphs: [
          t("Before your first sign-in, check Audience → Publishing status. An External app in Testing gives Gmail authorizations that expire after seven days. For regular use, review Google's requirements and choose Publish app / In production when allowed.",
            "Antes del primer inicio de sesión, revisa Público → Estado de publicación. Una app Externa en Pruebas concede autorizaciones de Gmail que caducan a los siete días. Para uso habitual, revisa los requisitos de Google y elige Publicar aplicación / En producción cuando se permita."),
          t("This changes the Google app's status; it does not upload your JSON or publish this plugin. Google may ask for verification or organization approval. Production removes this particular testing limit, but Google can still expire or revoke access for other reasons. Do not delete or replace the client.",
            "Esto cambia el estado de la app de Google; no sube tu JSON ni publica este plugin. Google puede pedir verificación o aprobación de tu organización. Producción elimina ese límite concreto de pruebas, pero Google aún puede caducar o revocar el acceso por otros motivos. No borres ni sustituyas el cliente.")
        ],
        links: [link("Open Audience", "Abrir Público", "https://console.cloud.google.com/auth/audience"),
                link("Google: testing and production", "Google: pruebas y producción", "https://support.google.com/cloud/answer/15549945")]
      },
      {
        title: t("Check the file, then connect Gmail", "Comprueba el archivo y conecta Gmail"),
        paragraphs: [
          t("Choose Check setup below. This only checks the local client file; it does not sign in or change saved accounts. When it says the file is ready, choose Add Gmail account. Your default browser opens Google's sign-in page. Check the account and requested access, then finish and return to Omarchy.",
            "Pulsa Comprobar configuración abajo. Solo comprueba el archivo local; no inicia sesión ni cambia cuentas guardadas. Cuando diga que el archivo está listo, pulsa Añadir cuenta de Gmail. Tu navegador abrirá el acceso de Google. Revisa la cuenta y los permisos, termina y vuelve a Omarchy."),
          t("Connect each account once on this computer. Saved accounts do not need to be added again after an update. If you restored an existing setup, return to settings and refresh instead. Keep your keyring unlocked; never delete its tokens to perform an update.",
            "Conecta cada cuenta una vez en este ordenador. Las cuentas guardadas no necesitan añadirse otra vez tras una actualización. Si has recuperado una instalación existente, vuelve a ajustes y actualiza el correo. Mantén desbloqueado el llavero; nunca borres sus tokens para actualizar.")
        ],
        links: []
      }
    ]
  }
  if (existingAccounts) {
    result.title = t("Keep your existing Google sign-in", "Conserva tu acceso con Google")
    result.steps = [
      {
        title: t("Find your ORIGINAL client file", "Busca tu archivo ORIGINAL del cliente"),
        paragraphs: [
          t("Your saved accounts are still here. A plugin update does not replace the OAuth client or remove saved tokens. Find your original oauth-client.json on your own computer or in a private backup; do not create a new Google project/client to repair an existing installation.",
            "Tus cuentas guardadas siguen aquí. Una actualización no sustituye el cliente OAuth ni borra los tokens. Busca tu oauth-client.json original en tu propio ordenador o en una copia privada; no crees otro proyecto o cliente de Google para reparar una instalación existente."),
          t("If you cannot find the original file, keep the saved accounts and ask for help before changing anything. A missing/changed client, a lost or locked keyring and a Google-expired grant need different fixes. Do not remove accounts or revoke access as a troubleshooting shortcut.",
            "Si no encuentras el original, conserva las cuentas y pide ayuda antes de cambiar nada. Un cliente perdido o cambiado, un llavero perdido o bloqueado y un permiso caducado por Google necesitan soluciones distintas. No borres cuentas ni revoques el acceso para intentar arreglarlo.")
        ], links: []
      },
      {
        title: t("Restore that same file", "Recupera ese mismo archivo"),
        paragraphs: [
          t("In your file manager, open Home and press Ctrl+H. Open .config → omarchy → gmail-notifier. If the client is missing, copy your ORIGINAL oauth-client.json here. If a file is already present but reported invalid, preserve a private copy before restoring the known original. Never substitute a new client.",
            "En el gestor de archivos, abre tu carpeta personal y pulsa Ctrl+H. Entra en .config → omarchy → gmail-notifier. Si falta el cliente, copia ahí tu oauth-client.json ORIGINAL. Si hay un archivo marcado como inválido, conserva una copia privada antes de recuperar el original conocido. Nunca lo sustituyas por un cliente nuevo."),
          t("Check the exact file name/location below. After restoring it, run these permission commands in a terminal. They do not delete accounts or tokens.",
            "Comprueba el nombre y la ubicación exactos de abajo. Después de recuperarlo, ejecuta estas órdenes de permisos en una terminal. No borran cuentas ni tokens.")
        ], location: result.steps[5].location, code: result.steps[5].code, links: []
      },
      {
        title: t("Check and return to saved accounts", "Comprueba y vuelve a tus cuentas"),
        paragraphs: [
          t("Choose Check setup below. When the file is ready, go Back to settings and choose Update. Existing saved authorizations are reused; do not add the same accounts again. Unlock your desktop keyring if asked.",
            "Pulsa Comprobar configuración abajo. Cuando el archivo esté listo, pulsa Volver a ajustes y Actualizar. Se reutilizan las autorizaciones guardadas; no vuelvas a añadir las mismas cuentas. Desbloquea el llavero del escritorio si lo pide."),
          t("Google can independently expire or revoke access, especially for a project left in Testing. See the hints below. Checking this file does not change your Google project or start authorization.",
            "Google puede caducar o revocar el acceso por su cuenta, especialmente si el proyecto sigue en Pruebas. Consulta las pistas de abajo. Comprobar este archivo no cambia tu proyecto de Google ni inicia una autorización.")
        ], links: []
      }
    ]
  }
  return result
}

function allowedLink(url) {
  // Only the fixed help destinations above, with an explicit supported locale.
  var values = guide("en").steps.concat([{links: guide("en").supportLinks}])
  for (var i = 0; i < values.length; i++) {
    for (var j = 0; j < values[i].links.length; j++) {
      var en = values[i].links[j].url
      if (url === en || url === en.replace(/\?hl=en$/, "?hl=es")) return true
    }
  }
  return false
}
