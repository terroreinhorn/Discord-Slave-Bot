# 🖥️ Zorin OS 24/7 Hosting & GitHub Guide (`Discord-Slave-Bot v2.2.2`)

This guide walks you through setting up **Discord-Slave-Bot (`slave`)** to run 24/7 on an old Zorin OS (Ubuntu/Debian) laptop with the lid closed, keeping it updated via GitHub (`git pull` & `git push`), and eliminating Wi-Fi/CPU audio stuttering.

---

## 📑 Table of Contents
1. [Step 1: Stop the Laptop from Sleeping When You Close the Lid](#step-1-stop-the-laptop-from-sleeping-when-you-close-the-lid)
2. [Step 2: Disable Linux Wi-Fi Power Saving (Critical for Stutter-Free Voice!)](#step-2-disable-linux-wi-fi-power-saving-critical-for-stutter-free-voice)
3. [Step 3: Install Required System Packages](#step-3-install-required-system-packages)
4. [Step 4: Set Up the Project Folder & Virtual Environment](#step-4-set-up-the-project-folder--virtual-environment)
5. [Step 5: Save Your Discord Bot Token Safely in `token.txt`](#step-5-save-your-discord-bot-token-safely-in-tokentxt)
6. [Step 6: Create the 24/7 `systemd` Background Service](#step-6-create-the-247-systemd-background-service)
7. [Step 7: How to Pull Updates from GitHub (`git pull`)](#step-7-how-to-pull-updates-from-github-git-pull)
8. [Step 8: How to Push Changes to GitHub (`git push`)](#step-8-how-to-push-changes-to-github-git-push)
9. [Step 9: Automatic Weekly `yt-dlp` Updates (`crontab`)](#step-9-automatic-weekly-yt-dlp-updates-crontab)
10. [Troubleshooting & Useful Commands](#troubleshooting--useful-commands)

---

## Step 1: Stop the Laptop from Sleeping When You Close the Lid

1. Open the terminal on your Zorin OS laptop and edit the `logind.conf` file:
   ```bash
   sudo nano /etc/systemd/logind.conf
   ```
2. Find the lines below, remove the `#` at the front of each line if present, and set them to `ignore`:
   ```ini
   HandleLidSwitch=ignore
   HandleLidSwitchExternalPower=ignore
   HandleLidSwitchDocked=ignore
   ```
3. Press **`Ctrl + O`**, **`Enter`** to save, and **`Ctrl + X`** to exit.
4. Apply the change immediately:
   ```bash
   sudo systemctl restart systemd-logind
   ```

---

## Step 2: Disable Linux Wi-Fi Power Saving (Critical for Stutter-Free Voice!)

By default, Zorin OS / Ubuntu enables aggressive **Wi-Fi Power Management (`wifi.powersave = 3`)** on laptops, which puts the Wi-Fi chip into micro-sleep every few hundred milliseconds. Because Discord voice sends a UDP audio packet every **20 milliseconds**, Wi-Fi micro-sleep causes noticeable audio stuttering!

Run this one-liner to keep your laptop's Wi-Fi card awake at full performance:
```bash
sudo sed -i 's/wifi.powersave = 3/wifi.powersave = 2/' /etc/NetworkManager/conf.d/default-wifi-powersave-on.conf 2>/dev/null || true
sudo systemctl restart NetworkManager
```

---

## Step 3: Install Required System Packages

Install Python, `ffmpeg` (for Opus audio encoding), `nodejs` (for 2026 YouTube stream challenge solving), `git`, and the GitHub CLI (`gh`):
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg nodejs libffi-dev libnacl-dev git gh
```

---

## Step 4: Set Up the Project Folder & Virtual Environment

```bash
mkdir -p ~/slave-bot
cd ~/slave-bot
python3 -m venv venv
~/slave-bot/venv/bin/pip install --upgrade pip
~/slave-bot/venv/bin/pip install -U -r requirements.txt
~/slave-bot/venv/bin/pip install -U --pre "yt-dlp[default,curl-cffi]"
```

---

## Step 5: Save Your Discord Bot Token Safely in `token.txt`

Instead of pasting your live Discord token directly into `slave_bot.py` (where it could accidentally get pushed to GitHub or overwritten during a `git pull`), save it into `~/slave-bot/token.txt`:

```bash
echo "PASTE_YOUR_REAL_DISCORD_BOT_TOKEN_HERE" > ~/slave-bot/token.txt
chmod 600 ~/slave-bot/token.txt
```
*(Because `token.txt` is listed in `.gitignore`, Git will never upload or overwrite it!)*

---

## Step 6: Create the 24/7 `systemd` Background Service

1. Create the service file (with `Nice=-10` high CPU priority so audio encoding never starves):
   ```bash
   sudo nano /etc/systemd/system/slave-bot.service
   ```
2. Paste the following configuration (replace `patrick` if your Linux username is different):
   ```ini
   [Unit]
   Description=Slave Discord Music Bot
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=patrick
   WorkingDirectory=/home/patrick/slave-bot
   ExecStart=/home/patrick/slave-bot/venv/bin/python /home/patrick/slave-bot/slave_bot.py
   Restart=always
   RestartSec=5
   Nice=-10
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```
3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable slave-bot
   sudo systemctl start slave-bot
   ```

---

## Step 7: How to Pull Updates from GitHub (`git pull`)

Whenever a new version is available on your GitHub repository (`https://github.com/terroreinhorn/Discord-Slave-Bot.git`), run:
```bash
cd ~/slave-bot && git pull && ~/slave-bot/venv/bin/pip install -U -r requirements.txt && sudo systemctl restart slave-bot
```

*(Optional Pro-Tip: Create a 1-word shortcut command called `update-slave`)*:
```bash
echo "alias update-slave='cd ~/slave-bot && git pull && ~/slave-bot/venv/bin/pip install -U -r requirements.txt && sudo systemctl restart slave-bot'" >> ~/.bashrc
source ~/.bashrc
```

---

## Step 8: How to Push Changes to GitHub (`git push`)

1. **Make sure your real token is in `token.txt`** and Line 35 of `slave_bot.py` still says:
   ```python
   DISCORD_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"
   ```
2. **Log in to GitHub CLI once (if you haven't already):**
   ```bash
   gh auth login
   ```
3. **Stage, commit, and push your updated files:**
   ```bash
   cd ~/slave-bot
   git add .gitignore README.md hosting_guide.md requirements.txt slave_bot.py
   git commit -m "Update Discord-Slave-Bot to v2.2.2 (anti-stutter engine)"
   git push origin main
   ```

---

## Step 9: Automatic Weekly `yt-dlp` Updates (`crontab`)

YouTube updates its streaming signatures regularly. To have your Zorin OS laptop automatically update `yt-dlp` and restart `slave-bot` every Sunday at 4:00 AM:
```bash
(crontab -l 2>/dev/null; echo "0 4 * * 0 /home/patrick/slave-bot/venv/bin/pip install -U --pre 'yt-dlp[default,curl-cffi]' && sudo systemctl restart slave-bot") | crontab -
```

---

## 🛠️ Troubleshooting & Useful Commands

* **View live bot logs in real time:**
  ```bash
  journalctl -u slave-bot -f
  ```
* **Check service status:**
  ```bash
  sudo systemctl status slave-bot
  ```
* **Restart the bot after editing files:**
  ```bash
  sudo systemctl restart slave-bot
  ```
