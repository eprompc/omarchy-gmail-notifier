# Configura el acceso con Google

El plugin está instalado. Google necesita un pequeño archivo de configuración llamado cliente OAuth antes de conectar Gmail. Sigue un paso cada vez; puedes volver a esta guía mientras usas el navegador.

¿Ya usabas el plugin? Las actualizaciones conservan tus cuentas y tu autorización. Si falta el archivo, recupera tu oauth-client.json ORIGINAL desde tu propio ordenador o una copia privada. No lo sustituyas por un cliente nuevo ni borres tus cuentas. Un cliente nuevo no puede reutilizar la autorización del anterior.

Guarda el JSON en privado. Nunca lo subas a GitHub ni lo pegues en un chat. El plugin pide etiquetas y cabeceras del correo, no el contenido de los mensajes ni permiso para enviar o borrar correo.

## 1. Crea un proyecto de Google

Abre Google Cloud con el botón de abajo e inicia sesión con tu cuenta de Google. Arriba, abre el selector de proyectos → Nuevo proyecto. Ponle, por ejemplo, Mi avisador de correo y pulsa Crear.

Selecciona ese proyecto arriba. Un proyecto es como una carpeta para estos ajustes de Google. Usa el MISMO proyecto en todos los pasos. ¿Ya tienes tu cliente original? Recupera ese archivo en lugar de crear otro proyecto.

[Abrir Google Cloud](https://console.cloud.google.com/projectcreate?hl=es)

## 2. Activa la API de Gmail

Con tu proyecto seleccionado, abre la API de Gmail con el botón de abajo. Pulsa Habilitar. Si aparece Administrar, ya está activada. Así tu proyecto podrá consultar la lista de mensajes sin leer de Gmail.

[Abrir API de Gmail](https://console.cloud.google.com/apis/library/gmail.googleapis.com?hl=es)

## 3. Indica a Google quién la usará

Abre Google Auth Platform → Desarrollo de la marca (Branding). Pulsa Comenzar si aparece. Escribe el nombre de tu app, tu correo de asistencia y tu correo de contacto. Elige Externo para cuentas personales de Gmail. Lee las condiciones de Google y termina de crearla.

Abre Público (Audience). Mientras esté en Pruebas, pulsa Añadir usuarios en Usuarios de prueba y añade CADA dirección de Gmail que quieras conectar. Una app Interna solo sirve para su propia organización de Google Workspace. Los nombres pueden variar un poco según el idioma de Google.

[Abrir Branding](https://console.cloud.google.com/auth/branding?hl=es)

[Abrir Público](https://console.cloud.google.com/auth/audience?hl=es)

## 4. Elige solo el permiso necesario

Abre Acceso a los datos (Data Access) → Añadir o quitar permisos. Busca el permiso exacto de abajo, selecciónalo y pulsa Actualizar y Guardar. Google lo llama restringido, aunque solo lee etiquetas y cabeceras. No añadas gmail.readonly, gmail.modify ni acceso completo al correo.

```text
https://www.googleapis.com/auth/gmail.metadata
```

[Abrir Acceso a los datos](https://console.cloud.google.com/auth/scopes?hl=es)

[Google: permisos de Gmail](https://developers.google.com/workspace/gmail/api/auth/scopes?hl=es)

## 5. Crea un cliente de escritorio

Abre Clientes (Clients) → Crear cliente. En Tipo de aplicación elige Aplicación de escritorio, ponle un nombre como Ordenador Omarchy y pulsa Crear. Descarga el archivo JSON cuando Google lo ofrezca y guárdalo en privado.

Elige Aplicación de escritorio, no Aplicación web, Clave de API ni Cuenta de servicio. No necesitas escribir una dirección de redirección: el plugin prepara la conexión local. Conserva este mismo cliente para las futuras actualizaciones.

[Abrir Clientes](https://console.cloud.google.com/auth/clients?hl=es)

[Google: crear un cliente](https://developers.google.com/workspace/guides/create-credentials?hl=es)

## 6. Coloca el archivo en su sitio

En el gestor de archivos, abre Descargas y busca el JSON que acabas de descargar (su nombre suele empezar por client_secret). Renómbralo exactamente oauth-client.json, sin añadir .txt. Es el archivo descargado completo: no edites su contenido.

Abre tu carpeta personal y pulsa Ctrl+H para ver las carpetas ocultas. Entra en .config → omarchy → gmail-notifier y crea las carpetas que falten. Copia ahí oauth-client.json. Si ese archivo ya existe, PARA y conserva el original; nunca sobrescribas un cliente que funciona para actualizar el plugin.

Después de copiarlo, abre una terminal y pega las dos líneas de abajo. Dejan la carpeta y el archivo privados para tu usuario. El símbolo ~ significa tu carpeta personal. Conserva una copia privada del cliente ORIGINAL para poder recuperarlo.

`~/.config/omarchy/gmail-notifier/oauth-client.json`

```bash
chmod 700 ~/.config/omarchy/gmail-notifier
chmod 600 ~/.config/omarchy/gmail-notifier/oauth-client.json
```

## 7. Evita el límite de siete días de pruebas

Antes del primer inicio de sesión, revisa Público → Estado de publicación. Una app Externa en Pruebas concede autorizaciones de Gmail que caducan a los siete días. Para uso habitual, revisa los requisitos de Google y elige Publicar aplicación / En producción cuando se permita.

Esto cambia el estado de la app de Google; no sube tu JSON ni publica este plugin. Google puede pedir verificación o aprobación de tu organización. Producción elimina ese límite concreto de pruebas, pero Google aún puede caducar o revocar el acceso por otros motivos. No borres ni sustituyas el cliente.

[Abrir Público](https://console.cloud.google.com/auth/audience?hl=es)

[Google: pruebas y producción](https://support.google.com/cloud/answer/15549945?hl=es)

## 8. Comprueba el archivo y conecta Gmail

Pulsa Comprobar configuración abajo. Solo comprueba el archivo local; no inicia sesión ni cambia cuentas guardadas. Cuando diga que el archivo está listo, pulsa Añadir cuenta de Gmail. Tu navegador abrirá el acceso de Google. Revisa la cuenta y los permisos, termina y vuelve a Omarchy.

Conecta cada cuenta una vez en este ordenador. Las cuentas guardadas no necesitan añadirse otra vez tras una actualización. Si has recuperado una instalación existente, vuelve a ajustes y actualiza el correo. Mantén desbloqueado el llavero; nunca borres sus tokens para actualizar.

## ¿Necesitas una pista?

- Acceso bloqueado / access_denied: selecciona el mismo proyecto y añade la dirección de Gmail en Público (Audience) → Usuarios de prueba si la app sigue en Pruebas. En una cuenta de trabajo o estudios, consulta al administrador si bloquea el acceso.

- Google no ha verificado esta aplicación: comprueba que es tu PROPIO proyecto/cliente y que los permisos coinciden con esta guía. Lee la explicación de Google abajo. Si decides continuar con tu propio cliente, Google puede mostrar Configuración avanzada → Ir a tu app. No lo hagas con una app desconocida. Un bloqueo del administrador requiere su ayuda.

- ¿Pide iniciar sesión otra vez tras unos siete días? Revisa el estado Pruebas del paso de publicación. Las actualizaciones del plugin no reinician la autorización, pero Google puede caducarla o revocarla. Conserva el mismo cliente y las cuentas guardadas.

- Otro ordenador: puedes reutilizar tu propio JSON del cliente. Conecta las cuentas una vez en el ordenador nuevo porque sus tokens se guardan en el llavero privado de cada equipo. Una actualización en el mismo equipo reutiliza ese llavero.

[Google: avisos de acceso](https://support.google.com/cloud/answer/7454865?hl=es)

[Google: caducidad del acceso](https://developers.google.com/identity/protocols/oauth2?hl=es)

## Conserva tu acceso con Google

### 1. Busca tu archivo ORIGINAL del cliente

Tus cuentas guardadas siguen aquí. Una actualización no sustituye el cliente OAuth ni borra los tokens. Busca tu oauth-client.json original en tu propio ordenador o en una copia privada; no crees otro proyecto o cliente de Google para reparar una instalación existente.

Si no encuentras el original, conserva las cuentas y pide ayuda antes de cambiar nada. Un cliente perdido o cambiado, un llavero perdido o bloqueado y un permiso caducado por Google necesitan soluciones distintas. No borres cuentas ni revoques el acceso para intentar arreglarlo.

### 2. Recupera ese mismo archivo

En el gestor de archivos, abre tu carpeta personal y pulsa Ctrl+H. Entra en .config → omarchy → gmail-notifier. Si falta el cliente, copia ahí tu oauth-client.json ORIGINAL. Si hay un archivo marcado como inválido, conserva una copia privada antes de recuperar el original conocido. Nunca lo sustituyas por un cliente nuevo.

Comprueba el nombre y la ubicación exactos de abajo. Después de recuperarlo, ejecuta estas órdenes de permisos en una terminal. No borran cuentas ni tokens.

`~/.config/omarchy/gmail-notifier/oauth-client.json`

```bash
chmod 700 ~/.config/omarchy/gmail-notifier
chmod 600 ~/.config/omarchy/gmail-notifier/oauth-client.json
```

### 3. Comprueba y vuelve a tus cuentas

Pulsa Comprobar configuración abajo. Cuando el archivo esté listo, pulsa Volver a ajustes y Actualizar. Se reutilizan las autorizaciones guardadas; no vuelvas a añadir las mismas cuentas. Desbloquea el llavero del escritorio si lo pide.

Google puede caducar o revocar el acceso por su cuenta, especialmente si el proyecto sigue en Pruebas. Consulta las pistas de abajo. Comprobar este archivo no cambia tu proyecto de Google ni inicia una autorización.
