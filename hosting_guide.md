🖥️ Zorin OS 24/7 Hosting & GitHub Guide (Discord-Slave-Bot v2.2.2)

This guide walks you through setting up Discord-Slave-Bot (slave) to run 24/7 on an old Zorin OS (Ubuntu/Debian) laptop with the lid closed, keeping it updated via GitHub (git pull & git push), and eliminating Wi-Fi/CPU audio stuttering.

📑 Table of Contents

Step 1: Stop the Laptop from Sleeping When You Close the Lid

Step 2: Disable Linux Wi-Fi Power Saving (Critical for Stutter-Free Voice!)

Step 3: Install Required System Packages

Step 4: Set Up the Project Folder & Virtual Environment

Step 5: Save Your Discord Bot Token Safely in token.txt

Step 6: Create the 24/7 systemd Background Service

Step 7: How to Pull Updates from GitHub (git pull)

Step 8: How to Push Changes to GitHub (git push)

Step 9: Automatic Weekly yt-dlp Updates (crontab)

Troubleshooting & Useful Commands

Step 1: Stop the Laptop from Sleeping When You Close the Lid

Open the terminal on your Zorin OS laptop and edit the logind.conf file:

sudo nano /etc/systemd/logind.conf


Find the lines below, remove the # at the front of each line if present, and set them to ignore:

HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore


Press Ctrl + O, Enter to save, and Ctrl + X to exit.

Apply the change immediately:

sudo systemctl restart systemd-logind


Step 2: Disable Linux Wi-Fi Power Saving (Critical for Stutter-Free Voice!)

By default, Zorin OS / Ubuntu enables aggressive Wi-Fi Power Management (wifi.powersave = 3) on laptops, which puts the Wi-Fi chip into micro-sleep every few hundred milliseconds. Because Discord voice sends a UDP audio packet every 20 milliseconds, Wi-Fi micro-sleep causes noticeable audio stuttering!

Run this one-liner to keep your laptop's Wi-Fi card awake at full performance:

sudo sed -i 's/wifi.powersave = 3/wifi.powersave = 2/' /etc/NetworkManager/conf.d/default-wifi-powersave-on.conf 2>/dev/null || true
sudo systemctl restart NetworkManager


Step 3: Install Required System Packages

Install Python, ffmpeg (for Opus audio encoding), nodejs (for 2026 YouTube stream challenge solving), git, and the GitHub CLI (gh):

sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg nodejs libffi-dev libnacl-dev git gh


Step 4: Set Up the Project Folder & Virtual Environment

mkdir -p ~/slave-bot
cd ~/slave-bot
python3 -m venv venv
~/slave-bot/venv/bin/pip install --upgrade pip
~/slave-bot/venv/bin/pip install -U -r requirements.txt
~/slave-bot/venv/bin/pip install -U --pre "yt-dlp[default,curl-cffi]"


Step 5: Save Your Discord Bot Token Safely in token.txt

Instead of pasting your live Discord token directly into slave_bot.py (where it could accidentally get pushed to GitHub or overwritten during a git pull), save it into ~/slave-bot/token.txt:

echo "PASTE_YOUR_REAL_DISCORD_BOT_TOKEN_HERE" > ~/slave-bot/token.txt
chmod 600 ~/slave-bot/token.txt


(Because token.txt is listed in .gitignore, Git will never upload or overwrite it!)

Step 6: Create the 24/7 systemd Background Service

Create the service file (with Nice=-10 high CPU priority so audio encoding never starves):

sudo nano /etc/systemd/system/slave-bot.service


Paste the following configuration (replace patrick if your Linux username is different):

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


Enable and start the service:

sudo systemctl daemon-reload
sudo systemctl enable slave-bot
sudo systemctl start slave-bot


Step 7: How to Pull Updates from GitHub (git pull)

Whenever a new version is available on your GitHub repository (https://github.com/terroreinhorn/Discord-Slave-Bot.git), run:

cd ~/slave-bot && git pull && ~/slave-bot/venv/bin/pip install -U -r requirements.txt && sudo systemctl restart slave-bot


(Optional Pro-Tip: Create a 1-word shortcut command called update-slave):

echo "alias update-slave='cd ~/slave-bot && git pull && ~/slave-bot/venv/bin/pip install -U -r requirements.txt && sudo systemctl restart slave-bot'" >> ~/.bashrc
source ~/.bashrc


Step 8: How to Push Changes to GitHub (git push)

Make sure your real token is in token.txt and Line 35 of slave_bot.py still says:

DISCORD_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"


Log in to GitHub CLI once (if you haven't already):

gh auth login


Stage, commit, and push your updated files:

cd ~/slave-bot
git add .gitignore README.md hosting_guide.md requirements.txt slave_bot.py
git commit -m "Update Discord-Slave-Bot to v2.2.2 (anti-stutter engine)"
git push origin main


Step 9: Automatic Weekly yt-dlp Updates (crontab)

YouTube updates its streaming signatures regularly. To have your Zorin OS laptop automatically update yt-dlp and restart slave-bot every Sunday at 4:00 AM:

(crontab -l 2>/dev/null; echo "0 4 * * 0 /home/patrick/slave-bot/venv/bin/pip install -U --pre 'yt-dlp[default,curl-cffi]' && sudo systemctl restart slave-bot") | crontab -


🛠️ Troubleshooting & Useful Commands

View live bot logs in real time:

journalctl -u slave-bot -f


Check service status:

sudo systemctl status slave-bot


Restart the bot after editing files:

sudo systemctl restart slave-bot
