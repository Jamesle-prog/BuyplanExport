# PO Automation GIII — Install Pack

This folder is everything needed to run PO Automation GIII on a new Windows
computer. No prior setup required — the installer takes care of Python,
dependencies, licensing, and your first login account.

## Install (one time)

1. Copy this whole folder to the new computer (anywhere is fine, e.g.
   `C:\Apps\PO_Automation_GIII` or your Desktop).
2. Double-click **`Install.bat`**.
3. It will:
   - Check for Python 3.13 and install it automatically if missing (no admin
     rights needed — installs just for your Windows account).
   - Set up the app's own isolated Python environment (`.venv\`) and install
     its dependencies. This step needs internet access and can take a few
     minutes.
   - Register a license for this specific computer.
   - Ask you to create a login username and password (you can add up to 3
     accounts here, and add more later — see below). **The first account you
     create becomes an admin automatically.**
4. When you see "Install complete!", you're done.

## Running the app (every time after install)

Double-click **`Start_PO_Extractor.bat`**. Wait for the console window to
print a line like:

```
You can now view your Streamlit app in your browser.
```

then open **http://localhost:8501** in your browser. Sign in with the
account you created during install.

Leave the console window open while you use the app — closing it stops the
app. To use it again later, just double-click `Start_PO_Extractor.bat` again.

## Adding or resetting accounts later

Open a terminal in this folder and run:

```
.venv\Scripts\python.exe setup_users.py
```

Follow the prompts. Re-running it is safe — entering an existing username
resets that account's password; it doesn't delete other accounts. (The
auto-admin rule only applies to the very first account ever created — every
account after that defaults to a regular user, same as before. Promote
someone to admin from the app's own User Management screen once you have at
least one admin account.)

## Updating to a new version

When you get a newer pack, you don't need to reinstall from scratch — updating
in place keeps your PO history, fabric database, and login accounts exactly
as they are.

1. Extract the new pack anywhere (e.g. your Downloads folder — it doesn't
   need to be near your existing install).
2. In the new pack, double-click **`Update.bat`**.
3. When it asks for the path to your existing install, paste the folder path
   of your **current** installation (e.g. `C:\Apps\PO_Automation_GIII`).
4. It copies in the new app code and refreshes dependencies. Never touched,
   no matter what the new pack contains: your `data\` folders (databases,
   buy-plan templates, size order, schema, custom fibers), `auth\users.json`,
   `auth\companies.json`, `auth\smtp_settings.json`, `auth\license.key`,
   and `.venv\`. (Because `data\` is preserved wholesale, template layout
   updates arrive via the app's Admin > Templates screen, not via update.)
5. Once it says "Update complete", launch the app as usual from your
   **existing** install's `Start_PO_Extractor.bat`.

## Uninstalling

Double-click **`Uninstall.bat`**. It always removes the Python environment
(`.venv\`) and this computer's license (`auth\license.key`) — both rebuild
automatically next time you run `Install.bat`.

Your PO history, fabric database, and login accounts are kept by default —
type `DELETE` when it asks if you want to erase those too. Do this only if
you're sure; that data doesn't come back.

Two things it won't do for you, on purpose:
- **Delete the folder itself** — close the window it opened, then delete the
  folder yourself in Explorer.
- **Uninstall Python 3.13** — it may be used by other things on this
  computer, so remove it manually via Windows Settings > Apps > Installed
  apps if you're sure you don't need it, rather than having an uninstaller
  silently remove a shared system component.

## Troubleshooting

- **"Python was installed but this script can't locate it yet"** — close the
  installer window, open a new one (double-click `Install.bat` again), and
  it will pick up the freshly-installed Python.
- **Install seems stuck on "Installing dependencies"** — this step downloads
  ~90 packages and can genuinely take a few minutes on a slow connection;
  it isn't actually stuck unless there's no output for 10+ minutes.
- **Browser shows "can't connect" right after starting** — the server takes
  a few seconds to start; wait for the "You can now view..." line in the
  console, then refresh the browser tab.
- Full architecture and conventions: see `IMPLEMENTATION_GUIDE.md` in this
  folder. Day-to-day start/stop details: `docs/HOW_TO_START.md`. Deploying
  this as an always-on server instead of a manual start: `docs/DEPLOYMENT.md`.
