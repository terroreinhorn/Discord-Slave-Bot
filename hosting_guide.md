# 🖥️ Zorin OS 24/7 Hosting & Maintenance Guide (`v2.2.1`)

This guide walks you through setting up **Discord-Slave-Bot** (`slave`) on an old **Zorin OS** (or Ubuntu/Debian) laptop so it runs 24/7 in the background with the laptop lid closed, automatically restarts if the Wi-Fi drops or the laptop reboots, and updates cleanly from GitHub with a single command.

---

## 📋 Table of Contents
1. [Step 1: Keep the Laptop Running with the Lid Closed](#step-1-keep-the-laptop-running-with-the-lid-closed)
2. [Step 2: Install System Dependencies (FFmpeg, Node.js, Python)](#step-2-install-system-dependencies-ffmpeg-nodejs-python)
3. [Step 3: Clone the Repository & Install Python Packages](#step-3-clone-the-repository--install-python-packages)
4. [Step 4: Store Your Discord Token Safely in `token.txt`](#step-4-store-your-discord-token-safely-in-tokentxt)
5. [Step 5: Create the 24/7 `systemd` Background Service](#step-5-create-the-247-systemd-background-service)
6. [Step 6: Updating from GitHub (`git pull`) & Pushing Changes (`git push`)](#step-6-updating-from-github-git-pull--pushing-changes-git-push)
7. [Step 7: Automatic Weekly `yt-dlp` Updates (Recommended)](#step-7-automatic-weekly-yt-dlp-updates-recommended)
8. [Step 8: Useful Commands & Troubleshooting](#step-8-useful-commands--troubleshooting)

---

## Step 1: Keep the Laptop Running with the Lid Closed

By default, closing a laptop lid suspends Linux and disconnects your bot. To make your Zorin OS laptop stay awake 24/7 with the screen off when the lid is closed:

1. Open your terminal (`Ctrl + Alt + T`) and edit the `logind.conf` file:
   ```bash
   sudo nano /etc/systemd/logind.conf
   ```
2. Find the lines below, remove the `#` at the start of each line if present, and set them to `ignore`:
   ```ini
   HandleLidSwitch=ignore
   HandleLidSwitchExternalPower=ignore
   HandleLidSwitchDocked=ignore
   ```
3. Press **`Ctrl + O`**, then **`Enter`** to save, and **`Ctrl + X`** to exit.
4. Apply the change immediately:
   ```bash
   sudo systemctl restart systemd-logind
   ```

---

## Step 2: Install System Dependencies (FFmpeg, Node.js, Python)

`slave` uses **FFmpeg** for Opus audio normalization (`dynaudnorm`), **PyNaCl** for Discord voice encryption, and **Node.js** so `yt-dlp` can solve YouTube's 2026 stream challenges without getting `HTTP 403 Forbidden` errors.

Run this in your terminal:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg nodejs libffi-dev libnacl-dev git gh
```

---

## Step 3: Clone the Repository & Install Python Packages

If you are setting up the folder for the first time, clone your repository into `~/slave-bot` and create a Python virtual environment:

```bash
git clone https://github.com/terroreinhorn/Discord-Slave-Bot.git ~/slave-bot
cd ~/slave-bot

# Create virtual environment
python3 -m venv venv

# Upgrade pip and install dependencies (including pre-release yt-dlp + curl-cffi)
~/slave-bot/venv/bin/pip install -U pip
~/slave-bot/venv/bin/pip install -U -r requirements.txt
~/slave-bot/venv/bin/pip install -U --pre "yt-dlp[default,curl-cffi]"
```

---

## Step 4: Store Your Discord Token Safely in `token.txt`

In **`v2.2.1`**, `slave_bot.py` automatically loads your Discord token in this priority order:
1. The `DISCORD_TOKEN` environment variable (if set).
2. A local **`~/slave-bot/token.txt`** file in the same folder.
3. The fallback `DISCORD_TOKEN` string on **Line 33** of `slave_bot.py`.

By keeping your token in `~/slave-bot/token.txt` (which is ignored by `.gitignore`), you can run `git pull` and `git push` anytime without ever overwriting your token or leaking it to GitHub!

```bash
echo "PASTE_YOUR_REAL_DISCORD_TOKEN_HERE" > ~/slave-bot/token.txt
chmod 600 ~/slave-bot/token.txt
```

### Discord Developer Portal Checklist:
Make sure your bot application at [discord.com/developers/applications](https://discord.com/developers/applications) has:
* **Bot Tab → Privileged Gateway Intents:** Enable **Message Content Intent** and **Server Members Intent**.
* **OAuth2 → URL Generator:** Select scopes **`bot`** and **`applications.commands`**, and permissions **View Channels**, **Send Messages**, **Embed Links**, **Attach Files**, **Manage Messages** *(for auto-cleaning old Now Playing cards)*, **Connect**, and **Speak**.

---

## Step 5: Create the 24/7 `systemd` Background Service

Setting up a `systemd` service ensures **slave** starts automatically whenever the laptop boots up and restarts within 5 seconds if the internet drops.

1. Create the service file (replace `patrick` with your Linux username if different—you can check by running `whoami`):
   ```bash
   sudo nano /etc/systemd/system/slave-bot.service
   ```
2. Paste the following configuration:
   ```ini
   [Unit]
   Description=Slave Discord Music Bot (v2.2.1)
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=patrick
   WorkingDirectory=/home/patrick/slave-bot
   ExecStart=/home/patrick/slave-bot/venv/bin/python /home/patrick/slave-bot/slave_bot.py
   Restart=always
   RestartSec=5
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```
3. Save (`Ctrl + O`, `Enter`) and exit (`Ctrl + X`).
4. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable slave-bot
   sudo systemctl start slave-bot
   ```
5. Verify that it is running cleanly:
   ```bash
   sudo systemctl status slave-bot
   ```

---

## Step 6: Updating from GitHub (`git pull`) & Pushing Changes (`git push`)

### ⬇️ Downloading the Newest Version from GitHub (`git pull`)
Whenever you update the repository on GitHub and want your Zorin OS laptop to download and run the newest version:

```bash
cd ~/slave-bot
git pull
~/slave-bot/venv/bin/pip install -U -r requirements.txt
sudo systemctl restart slave-bot
```
*(Because `token.txt` and `slave_data.json` are in `.gitignore`, your bot token, saved server playlists, and liked songs are 100% untouched during `git pull`!)*

**💡 Pro-Tip — Create a 1-Word `update-slave` Shortcut:**
Run this once in your terminal:
```bash
echo "alias update-slave='cd ~/slave-bot && git pull && ~/slave-bot/venv/bin/pip install -U -r requirements.txt && ~/slave-bot/venv/bin/pip install -U --pre \"yt-dlp[default,curl-cffi]\" && sudo systemctl restart slave-bot'" >> ~/.bashrc
source ~/.bashrc
```
Now you can simply type **`update-slave`** from anywhere in your terminal to pull the latest GitHub changes, update `yt-dlp`, and restart the bot!

---

### ⬆️ Pushing Local Changes from Your Laptop to GitHub (`git push`)
If you edit files inside `~/slave-bot` on your laptop and want to upload them to your **`terroreinhorn/Discord-Slave-Bot`** repo on GitHub:

1. **Make sure you are logged into GitHub CLI once:**
   ```bash
   gh auth login
   ```
   *(Select `GitHub.com` → `HTTPS` → `Yes` → `Login with a web browser`.)*

2. **Stage, commit, and push your changes:**
   ```bash
   cd ~/slave-bot
   git add .gitignore README.md hosting_guide.md requirements.txt slave_bot.py
   git commit -m "Update Discord-Slave-Bot to v2.2.1"
   git push origin main
   ```

---

## Step 7: Automatic Weekly `yt-dlp` Updates (Recommended)

YouTube frequently updates its audio player signatures. Adding a weekly cron job ensures your Zorin laptop automatically updates `yt-dlp` every Sunday at 4:00 AM and restarts the bot:

1. Open your crontab editor:
   ```bash
   crontab -e
   ```
2. Add this line at the very bottom (adjust `/home/patrick` if your username differs):
   ```cron
   0 4 * * 0 /home/patrick/slave-bot/venv/bin/pip install -U --pre "yt-dlp[default,curl-cffi]" && sudo systemctl restart slave-bot
   ```

---

## Step 8: Useful Commands & Troubleshooting

### Common Service Commands
* **Watch live bot logs in real time:**
  ```bash
  journalctl -u slave-bot -f
  ```
* **Restart the bot:**
  ```bash
  sudo systemctl restart slave-bot
  ```
* **Stop the bot:**
  ```bash
  sudo systemctl stop slave-bot
  ```

### Troubleshooting
* **Slash commands (`/play`, `/skip`, `/slave ...`) don't show up right away:**
  * Restart the bot (`sudo systemctl restart slave-bot`) and press **`Ctrl + R`** inside your Discord desktop app to refresh the Discord client cache.
* **YouTube streams return `HTTP 403 Forbidden`:**
  * Run `update-slave` (or `~/slave-bot/venv/bin/pip install -U --pre "yt-dlp[default,curl-cffi]"` and `sudo apt install -y nodejs`) and restart the bot. `slave` (`v2.2.1`) also includes a 3-layer fallback that automatically caches audio locally if direct streaming is blocked.
* **Bot crashes with `ERROR: No Discord token found!`:**
  * Make sure `~/slave-bot/token.txt` exists and contains your bot token (`cat ~/slave-bot/token.txt`).
