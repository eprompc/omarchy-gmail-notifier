# Set up Google sign-in

The plugin is installed. Google needs a small settings file called an OAuth client before you can connect Gmail. Follow one step at a time; you can return to this guide while you use your browser.

Already using the plugin? Updates keep your accounts and saved sign-in. If the file is missing, restore your ORIGINAL oauth-client.json from your own computer or private backup. Do not replace it with a new client or remove your accounts. A new client cannot reuse the old client's authorization.

Keep the JSON private. Never upload it to GitHub or paste it into a chat. The plugin asks for email labels and headers, not message bodies or permission to send/delete mail.

## 1. Create a Google project

Open Google Cloud below and sign in with your Google account. At the top, open the project selector → New project. Name it, for example, My Mail Notifier, then choose Create.

Select that project at the top of the page. A project is just a folder for these Google settings. Use this SAME project in every step. Already have your original client? Restore that file instead of creating another project.

[Open Google Cloud](https://console.cloud.google.com/projectcreate?hl=en)

## 2. Enable Gmail API

With your project selected, open Gmail API below. Choose Enable. If you see Manage, it is already enabled. This lets your project ask Gmail for the unread message list.

[Open Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com?hl=en)

## 3. Tell Google who will use it

Open Google Auth Platform → Branding. Choose Get started if asked. Enter your app name, your own support email and contact email. Choose External for personal Gmail accounts. Read Google's terms and finish creating the app.

Open Audience. While the app is in Testing, use Add users under Test users and add EVERY Gmail address you want to connect. An Internal app is only for its own Google Workspace organization. Menu names may differ slightly with Google's language.

[Open Branding](https://console.cloud.google.com/auth/branding?hl=en)

[Open Audience](https://console.cloud.google.com/auth/audience?hl=en)

## 4. Choose the small permission we need

Open Data Access → Add or remove scopes. Search for the exact scope below, select it, then Update and Save. Google calls it restricted, even though it only reads labels and headers. Do not add gmail.readonly, gmail.modify or full mail access.

```text
https://www.googleapis.com/auth/gmail.metadata
```

[Open Data Access](https://console.cloud.google.com/auth/scopes?hl=en)

[Google: Gmail permissions](https://developers.google.com/workspace/gmail/api/auth/scopes?hl=en)

## 5. Create a Desktop app client

Open Clients → Create client. For Application type choose Desktop app, give it a name such as Omarchy computer, then Create. Download the JSON file when Google offers it and keep it private.

Choose Desktop app, not Web application, API key or Service account. You do not need to type a redirect address: the plugin sets up the local callback. Keep this same client for future plugin updates.

[Open Clients](https://console.cloud.google.com/auth/clients?hl=en)

[Google: create a client](https://developers.google.com/workspace/guides/create-credentials?hl=en)

## 6. Put the file in its home

In your file manager, open Downloads and find the JSON you just downloaded (its name often starts with client_secret). Rename it to exactly oauth-client.json, without adding .txt. This is the whole downloaded file; do not edit its contents.

Open your Home folder and press Ctrl+H to show hidden folders. Go into .config → omarchy → gmail-notifier, creating missing folders. Copy oauth-client.json there. If that file already exists, STOP and keep the original; never overwrite a working client just to update the plugin.

After copying it, open a terminal and paste the two lines below. They make the folder/file private to your user. The ~ symbol means your Home folder. Keep a private copy of the ORIGINAL client for recovery.

`~/.config/omarchy/gmail-notifier/oauth-client.json`

```bash
chmod 700 ~/.config/omarchy/gmail-notifier
chmod 600 ~/.config/omarchy/gmail-notifier/oauth-client.json
```

## 7. Avoid the seven-day test limit

Before your first sign-in, check Audience → Publishing status. An External app in Testing gives Gmail authorizations that expire after seven days. For regular use, review Google's requirements and choose Publish app / In production when allowed.

This changes the Google app's status; it does not upload your JSON or publish this plugin. Google may ask for verification or organization approval. Production removes this particular testing limit, but Google can still expire or revoke access for other reasons. Do not delete or replace the client.

[Open Audience](https://console.cloud.google.com/auth/audience?hl=en)

[Google: testing and production](https://support.google.com/cloud/answer/15549945?hl=en)

## 8. Check the file, then connect Gmail

Choose Check setup below. This only checks the local client file; it does not sign in or change saved accounts. When it says the file is ready, choose Add Gmail account. Your default browser opens Google's sign-in page. Check the account and requested access, then finish and return to Omarchy.

Connect each account once on this computer. Saved accounts do not need to be added again after an update. If you restored an existing setup, return to settings and refresh instead. Keep your keyring unlocked; never delete its tokens to perform an update.

## Need a hand?

- Access blocked / access_denied: select the same Google project and add the Gmail address under Audience → Test users if the app is still in Testing. For a work/school account, ask the administrator if access is blocked.

- Google has not verified this app: check that it is your OWN project/client and that the access matches this guide. Read Google's explanation below. If you decide to proceed with your own client, Google may offer Advanced → Go to your app. Do not do this for an unknown app. An administrator block needs your administrator's help.

- Asked to sign in again after about seven days? Check the app's Testing status in the publishing step. Plugin updates do not reset sign-in, but Google can expire or revoke its grants. Keep the same client and saved accounts.

- Another computer: you may reuse your own client JSON. Connect accounts once on the new computer because their saved tokens are in each computer's private keyring. An update on the same computer reuses that keyring.

[Google: sign-in warnings](https://support.google.com/cloud/answer/7454865?hl=en)

[Google: authorization expiry](https://developers.google.com/identity/protocols/oauth2?hl=en)

## Keep your existing Google sign-in

### 1. Find your ORIGINAL client file

Your saved accounts are still here. A plugin update does not replace the OAuth client or remove saved tokens. Find your original oauth-client.json on your own computer or in a private backup; do not create a new Google project/client to repair an existing installation.

If you cannot find the original file, keep the saved accounts and ask for help before changing anything. A missing/changed client, a lost or locked keyring and a Google-expired grant need different fixes. Do not remove accounts or revoke access as a troubleshooting shortcut.

### 2. Restore that same file

In your file manager, open Home and press Ctrl+H. Open .config → omarchy → gmail-notifier. If the client is missing, copy your ORIGINAL oauth-client.json here. If a file is already present but reported invalid, preserve a private copy before restoring the known original. Never substitute a new client.

Check the exact file name/location below. After restoring it, run these permission commands in a terminal. They do not delete accounts or tokens.

`~/.config/omarchy/gmail-notifier/oauth-client.json`

```bash
chmod 700 ~/.config/omarchy/gmail-notifier
chmod 600 ~/.config/omarchy/gmail-notifier/oauth-client.json
```

### 3. Check and return to saved accounts

Choose Check setup below. When the file is ready, go Back to settings and choose Update. Existing saved authorizations are reused; do not add the same accounts again. Unlock your desktop keyring if asked.

Google can independently expire or revoke access, especially for a project left in Testing. See the hints below. Checking this file does not change your Google project or start authorization.
