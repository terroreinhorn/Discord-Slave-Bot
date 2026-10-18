# Hosting Guide: Running **slave** 24/7 on Your Old Zorin OS Laptop (`v2.2.0`)

An old laptop running **Zorin OS** (which is built on Ubuntu Linux) is the **best possible setup** for a Discord music bot:
* **100% Free** (and uses less than 10W–15W of power with the screen off).
* **Uses Your Home IP Address**, so YouTube and YouTube Music won't block it like they block cloud data centers.
* **Built-in Battery Backup (UPS)**—if your power flickers, the laptop stays online.

---

## Step 1: Stop the Laptop from Sleeping When You Close the Lid

By default, closing the laptop lid puts Zorin OS to sleep and disconnects your bot. Let's make it stay awake with the screen turned off when the lid is closed:

1. Open the **Terminal** app on your Zorin OS laptop (`Ctrl + Alt + T`).
2. Open the system power configuration file:
   ```bash
   sudo nano /etc/systemd/logind.conf
   ```
3. Scroll down using the arrow keys and find the line `#HandleLidSwitch=suspend`.
4. Remove the `#` at the start and change it to:
   ```ini
   HandleLidSwitch=ignore
   HandleLidSwitchExternalPower=ignore
   ```
5. Press **`Ctrl + O`**, then **`Enter`** to save, and **`Ctrl + X`** to exit.
6. Apply the change immediately:
   ```bash
   sudo systemctl restart systemd-logind
   ```
*(Now you can close the laptop lid anytime and it will keep running silently!)*

---

## Step 2: Install Python, FFmpeg, Node.js, and Voice Libraries

Run these commands in your Zorin OS terminal to install FFmpeg, Node.js (used by `yt-dlp` to solve YouTube's 2026 stream challenges), and Python's voice dependencies:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg nodejs libffi-dev libnacl-dev
```

---

## Step 3: Create the Bot Folder & Virtual Environment

Zorin OS uses modern Ubuntu packages that require a virtual environment (`venv`) for `pip` packages:

```bash
mkdir -p ~/slave-bot
cd ~/slave-bot
python3 -m venv venv
source venv/bin/activate
pip install -U "discord.py[voice]" PyNaCl
pip install -U --pre "yt-dlp[default,curl-cffi]"
```

---

## Step 4: Create `slave_bot.py` (`v2.2.0`) and Test It

1. Open `slave_bot.py` (or clear it first if updating from an older version):
   ```bash
   > ~/slave-bot/slave_bot.py
   nano ~/slave-bot/slave_bot.py
   ```
2. Copy the entire code from **`slave_bot.py` (`v2.2.0`)** and paste it into the terminal (`Ctrl + Shift + V`).
3. Replace `"YOUR_DISCORD_BOT_TOKEN_HERE"` on **Line 33** with your real token from the [Discord Developer Portal](https://discord.com/developers/applications).
   * **Important:** In the Discord Developer Portal -> **Bot** tab, make sure **Message Content Intent** and **Server Members Intent** are toggled **ON** and click **Save Changes**!
4. Save and exit (`Ctrl + O`, `Enter`, `Ctrl + X`).
5. **Test it directly in the terminal:**
   ```bash
   ~/slave-bot/venv/bin/python ~/slave-bot/slave_bot.py
   ```

### What You Should See in the Terminal:
```text
================================================================
slave Music Bot — Version: v2.2.0
Logged in as: slave#1234 (ID: ...)
FFmpeg installed: YES (/usr/bin/ffmpeg)
JS Runtime (node/deno): YES (/usr/bin/node)
PyNaCl (voice library) installed: YES
Connected to 1 server(s):
 - Your Server Name (ID: ...) -> Syncing Hybrid /slave + shortcut commands...
slave v2.2.0 is online and ready!
================================================================
```

---

## ✨ What's New in `v2.2.0`

1. **🔀 Hybrid Style 1 Command Layout:**
   * All 25 `/slave ...` subcommands remain neatly organized under `/slave`, **plus** you now have 4 fast top-level shortcuts for your most common actions:
     * **`/play [song or link]`** — Fast shortcut for `/slave play` (with live song autocomplete!).
     * **`/skip [position]`** — Fast shortcut for `/slave skip`.
     * **`/playlist [page]`** — Fast shortcut for `/slave playlist`.
     * **`/np`** — Fast shortcut for `/slave nowplaying`.
2. **🔍 Live Slash-Command Autocomplete Dropdown:**
   * As you type a song name into `/play`, `/slave play`, or `/slave playnext`, Discord automatically pops up a live dropdown of the top 5 matching **`Composer - Song Title`** tracks from YouTube Music! (If you haven't typed anything yet, it suggests your liked/recent tracks; if you paste a `http://` or `https://` link, it stays out of your way.)
   * `/slave load` and `/slave deletesaved` also autocomplete your saved server playlist names!
3. **⚡ Next-Track Pre-Resolving (Zero-Gap Transitions):**
   * While your current song is playing, **slave** quietly pre-resolves the audio stream for track `#1 (Up Next)` in the background. When the current song ends or you click `⏭️ Skip`, the next song starts immediately with zero loading delay.
4. **🎚️ Automatic Studio Loudness Normalization (`dynaudnorm`):**
   * Enabled by default using FFmpeg's dynamic audio normalizer so quiet tracks and loud tracks play at the same balanced volume automatically. You can toggle it anytime using the **`🎚️ Norm`** button on the `"Now Playing"` card (or `!slave normalize` in chat).
5. **🧹 Single Active Player Card (Zero Chat Clutter):**
   * Whenever a new song starts or you run `/np`, **slave** automatically deletes its previous `"🎶 Now Playing"` card so there is only ever **one** clean player box at the bottom of your channel.
6. **🔄 Crashed-Queue Recovery (`/slave restore` & 1-Click Button):**
   * **slave** automatically snapshots your active queue and settings to `slave_data.json`. If your laptop or bot restarts mid-session, **slave** posts a **"🔄 Restore Previous Session"** button on startup (or you can run `/slave restore` anytime).

---

## 📋 Complete Command Reference (`v2.2.0`)

### ⚡ Fast Top-Level Shortcuts (Hybrid Style 1)
| Shortcut | What It Does |
| :--- | :--- |
| `/play [song or link]` | Plays a song or playlist with **live YouTube Music autocomplete** *(Requires Voice)* |
| `/skip [position]` | Skips the current track, or jumps straight to track `#` in the playlist *(Requires Voice)* |
| `/playlist [page]` | Opens the interactive playlist card + **📄 Full List (Scrollable)** button *(Open to Everyone)* |
| `/np` | Shows the rich **Now Playing** card with progress bar and 10 interactive buttons *(Open to Everyone)* |

### 🎵 Full `/slave` Command Suite (25 Subcommands)
| Command | What It Does |
| :--- | :--- |
| `/slave play [song or link]` | Searches **1. YouTube Music → 2. Spotify → 3. YouTube** (with live autocomplete & *"Did you mean?"* buttons) *(Requires Voice)* |
| `/slave playnext [song or link]` | Inserts a song or playlist right at `#1` with live autocomplete *(Requires Voice)* |
| `/slave move [from] [to]` | Moves a track from one position in the playlist to another, e.g. `/slave move 8 1` *(Requires Voice)* |
| `/slave playlist [page]` | Displays the interactive playlist card with page buttons and **📄 Full List (Scrollable)** *(Open to Everyone)* |
| `/slave nowplaying` | Rich card with album artwork, visual progress bar (`01:24 ━━●──── 05:26`), and 10 player buttons *(Open to Everyone)* |
| `/slave seek [timestamp]` | Jumps to a timestamp in the current track (`0:00` restarts from the beginning) *(Requires Voice)* |
| `/slave previous` | Jumps back to the previously played track from history *(Requires Voice)* |
| `/slave skip [position]` | Skips the current song (or jumps directly to track `#` if `position` is given) *(Requires Voice)* |
| `/slave remove [number]` | Deletes track `#` from `/slave playlist` *(Requires Voice)* |
| `/slave removedupes` | Scans the upcoming playlist and removes duplicate tracks *(Requires Voice)* |
| `/slave autoplay` | Toggles endless **Autoplay Radio** mode when the playlist runs out *(Requires Voice)* |
| `/slave restore` | Restores and queues the previous interrupted session after a bot or laptop restart *(Requires Voice)* |
| `/slave save [name]` | Saves the current song + queue onto your laptop (`slave_data.json`), or type `/slave save list` to view all |
| `/slave load [name]` | Loads and queues a saved server playlist (with live name autocomplete, or `list` to view all) *(Requires Voice)* |
| `/slave deletesaved [name]` | Deletes a saved server playlist (with live name autocomplete) *(Requires Voice)* |
| `/slave like` | Hearts/saves the currently playing track to your personal favorites list |
| `/slave playlikes` | Queues all tracks from your personal liked songs list *(Requires Voice)* |
| `/slave lyrics [song]` | Fetches and displays full lyrics for the current song or any search query *(Open to Everyone)* |
| `/slave clear` | Removes all upcoming tracks from the playlist while keeping the current song playing *(Requires Voice)* |
| `/slave shuffle` | Randomly shuffles all tracks in the playlist *(Requires Voice)* |
| `/slave pause` | Toggles pause/resume on the current song (`!slave resume` also works in chat) *(Requires Voice)* |
| `/slave loop [off \| track \| queue]` | Loops the current track (`track`), the entire playlist (`queue`), or turns looping off (`off`) *(Requires Voice)* |
| `/slave volume [1-200]` | Changes the music volume from `1%` to `200%` *(Requires Voice)* |
| `/slave stop` | Stops playback, clears the playlist, and disconnects from voice *(Requires Voice)* |
| `/slave help` | Displays the full command list and current bot version (`v2.2.0`) inside Discord *(Open to Everyone)* |

---

## Step 5: Make **slave** Run 24/7 Automatically in the Background

Once you've confirmed the bot works in Step 4, press **`Ctrl + C`** to stop the manual test and set up a background `systemd` service:

1. Create the service file:
   ```bash
   sudo nano /etc/systemd/system/slave-bot.service
   ```
2. Paste the following configuration (replace `patrick` with your Linux username if different):
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

   [Install]
   WantedBy=multi-user.target
   ```
3. Save and exit (`Ctrl + O`, `Enter`, `Ctrl + X`).
4. Enable and start the background service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable slave-bot
   sudo systemctl start slave-bot
   ```

### Useful Maintenance Commands on Zorin OS:
* **Check bot status & logs:** `sudo systemctl status slave-bot`
* **Watch live logs:** `journalctl -u slave-bot -f`
* **Restart the bot:** `sudo systemctl restart slave-bot`
* **Automatic Weekly `yt-dlp` Auto-Updater (Cron Job):**
  ```bash
  (crontab -l 2>/dev/null; echo "0 4 * * 0 /home/$USER/slave-bot/venv/bin/pip install -U --pre 'yt-dlp[default,curl-cffi]' && sudo systemctl restart slave-bot") | crontab -
  ```
* **Disable Wi-Fi Power-Saving Drops (Run Once if Using Wi-Fi):**
  ```bash
  sudo sed -i 's/wifi.powersave = 3/wifi.powersave = 2/' /etc/NetworkManager/conf.d/default-wifi-powersave-on.conf && sudo systemctl restart NetworkManager
  ```