# 🎵 Discord-Slave-Bot (`v2.2.2`)

![Version](https://img.shields.io/badge/version-v2.2.2-5865F2?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Discord.py](https://img.shields.io/badge/discord.py-voice-5865F2?style=for-the-badge&logo=discord&logoColor=white)
![Vibe Coded](https://img.shields.io/badge/%E2%9C%A8_100%25-Vibe_Coded-FF69B4?style=for-the-badge)

> **✨ Note: This bot is 100% Vibe Coded!**  
> Every feature, bug fix, anti-stutter RAM buffer, anti-403 stream workaround, and UI button in **Discord-Slave-Bot** was built iteratively through pure vibes, live testing, and conversational prompting—designed to run 24/7 on an old Zorin OS Linux laptop.

**Discord-Slave-Bot** (`slave`) is a self-hosted, single-file Python Discord music bot engineered for high-bitrate studio audio, zero-gap transitions, and zero chat clutter. It searches **1. YouTube Music → 2. Spotify → 3. YouTube** automatically and formats every track cleanly as **`Composer - Song Title`**.

---

## ✨ Features (`v2.2.2`)

* **🎧 3-Stage Priority Search (`1. YouTube Music → 2. Spotify → 3. YouTube`):**
  * Prioritizes **YouTube Music's** native InnerTube API for clean studio audio streams, falls back to **Spotify / Music Catalog** metadata, and finally regular **YouTube**.
  * Strips channel clutter (`- Topic`, `VEVO`, `(Official Video)`) so every track displays as **`Composer - Song Title`** (e.g., `Daft Punk - Revolution 909`).
  * Includes an interactive **"🔎 Did you mean?"** button picker if a search query is misspelled or ambiguous.
* **🟢 Zero-Config Spotify Integration:**
  * Paste any Spotify **Track, Playlist, Album, or Artist** link (`open.spotify.com/...` or `spotify.link/...`)—extracts up to 100 tracks in under 0.5 seconds with **no Spotify API keys required**.
* **🔍 Live Slash-Command Autocomplete:**
  * Typing a song query into `/play`, `/slave play`, or `/slave playnext` pops up a live dropdown of the top 5 matching tracks from YouTube Music in real time (or suggests your liked/recent tracks before you type).
* **⚡ Zero-Gap Next-Track Pre-Caching:**
  * Quietly pre-downloads and caches the audio stream for track `#1 (Up Next)` in the background while the current track is playing (`⚡`), making song transitions and skips instantaneous.
* **🛡️ Anti-Stutter 5-Second RAM Ring-Buffer & Local-First Caching (`v2.2.2`):**
  * **Local-First Chunked Download:** Downloads songs in 10 MB chunks to `/tmp/slave_audio_cache` before playing so FFmpeg reads from local disk/RAM with **zero network jitter, zero CDN throttling, and zero mid-song HTTP 403 drops**.
  * **`BufferedOpusSource` (5s RAM Queue):** A dedicated background producer thread buffers 250 Opus frames (5 full seconds of audio) in RAM ahead of Discord's 20ms real-time UDP voice thread, paired with a 25ms clock-drift guard so packets never stutter or burst.
* **🎚️ Toggleable Loudness Normalization (`dynaudnorm`):**
  * Optional low-latency dynamic audio normalizer toggleable anytime via the `🎚️ Norm` button on the player card.
* **🎛️ Single Active Player Card (Zero Chat Clutter):**
  * Automatically deletes the previous `"🎶 Now Playing"` message whenever a new song starts, keeping only one clean card with album art, a live progress bar (`01:24 ━━●──── 05:26`), and 10 interactive buttons at the bottom of your channel.
* **🔄 Crashed-Queue Recovery & Persistent Storage:**
  * Saves custom server playlists, personal liked songs (`❤️`), and active queue snapshots in `slave_data.json`. If the bot or laptop restarts mid-session, a **1-click "🔄 Restore Previous Session"** button appears automatically.
* **🔒 Voice-Chat-Only Control Rule & Smart Auto-Pause:**
  * Only users currently inside the active voice channel can add, skip, move, or control music. Users outside voice chat can still view `/playlist`, `/np`, `/slave lyrics`, and `/slave help`.
  * Automatically pauses when everyone leaves the voice channel and resumes if someone returns within 3 minutes.

---

## 📋 Command Reference (Hybrid Style 1)

### ⚡ Fast Top-Level Shortcuts
| Shortcut | Description | Access |
| :--- | :--- | :--- |
| `/play [song or link]` | Play a song or playlist with **live YouTube Music autocomplete** | 🔒 Voice Only |
| `/skip [position]` | Skip the current song, or jump straight to track `#` in the playlist | 🔒 Voice Only |
| `/playlist [page]` | View the interactive paginated queue + **📄 Full List (Scrollable)** button | 🌍 Everyone |
| `/np` | Show the single active **Now Playing** card with progress bar & 10 buttons | 🌍 Everyone |

### 🛠️ Full `/slave` Command Suite (22 Subcommands)
| Command | Description | Access |
| :--- | :--- | :--- |
| `/slave play [song or link]` | Play a song (`Composer - Title`) or URL/playlist with live autocomplete | 🔒 Voice Only |
| `/slave playnext [song or link]` | Insert a song or playlist right at `#1 (Up Next)` with live autocomplete | 🔒 Voice Only |
| `/slave move [from] [to]` | Move a song from one position in the playlist to another (e.g. `/slave move 8 1`) | 🔒 Voice Only |
| `/slave playlist [page]` | Open the interactive playlist viewer + private scrollable `.txt` full list | 🌍 Everyone |
| `/slave nowplaying` | Display the rich Now Playing card with album art, progress bar & 10 buttons | 🌍 Everyone |
| `/slave seek [timestamp]` | Jump to a timestamp in the current track (`1:30`, or `0:00` to restart) | 🔒 Voice Only |
| `/slave previous` | Jump back to the previously played track from history | 🔒 Voice Only |
| `/slave skip [position]` | Skip the current track, or jump directly to track `#` in the playlist | 🔒 Voice Only |
| `/slave remove [position]` | Remove track `#` from the upcoming playlist | 🔒 Voice Only |
| `/slave removedupes` | Remove duplicate songs from the upcoming playlist | 🔒 Voice Only |
| `/slave autoplay` | Toggle endless **Autoplay Radio** mode when the queue finishes | 🔒 Voice Only |
| `/slave restore` | Restore and resume the previous interrupted queue after a restart | 🔒 Voice Only |
| `/slave save [name]` | Save the current song + queue as a server playlist (or `list` to view all) | 🔒 Voice Only |
| `/slave load [name]` | Load a saved server playlist (with live name autocomplete, or `list` to view all) | 🔒 Voice Only |
| `/slave deletesaved [name]` | Delete a saved server playlist (with live name autocomplete) | 🔒 Voice Only |
| `/slave like` | Save the currently playing song to your personal favorites list | 🌍 Everyone |
| `/slave playlikes` | Queue all songs from your personal liked tracks list | 🔒 Voice Only |
| `/slave lyrics [song]` | Fetch full song lyrics via LRCLIB for the current track or any search query | 🌍 Everyone |
| `/slave clear` | Clear all upcoming tracks from the playlist while keeping the current song playing | 🔒 Voice Only |
| `/slave shuffle` | Randomly shuffle all upcoming tracks in the playlist | 🔒 Voice Only |
| `/slave pause` | Toggle pause/resume on the current track | 🔒 Voice Only |
| `/slave loop [off \| track \| queue]` | Loop the current song (`track`), the whole playlist (`queue`), or turn loop `off` | 🔒 Voice Only |
| `/slave volume [1-200]` | Set playback volume from `1%` to `200%` | 🔒 Voice Only |
| `/slave stop` | Stop playback, clear the playlist, and disconnect from voice | 🔒 Voice Only |
| `/slave help` | Show the complete command list and current version inside Discord | 🌍 Everyone |

---

## 🚀 Quick Start (Zorin OS / Ubuntu / Debian Linux)

### 1. Install System Dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg nodejs libffi-dev libnacl-dev git
```

### 2. Clone the Repository & Create the Virtual Environment
```bash
git clone https://github.com/terroreinhorn/Discord-Slave-Bot.git
cd Discord-Slave-Bot
python3 -m venv venv
source venv/bin/activate
pip install -U -r requirements.txt
```

### 3. Configure Your Discord Bot Token (`token.txt`)
1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications) and enable **Message Content Intent** and **Server Members Intent** under the **Bot** tab.
2. Save your token in a local `token.txt` file inside the project folder (which `.gitignore` automatically protects so it is never pushed to GitHub or overwritten by `git pull`):
   ```bash
   echo "YOUR_DISCORD_BOT_TOKEN_HERE" > token.txt
   ```

### 4. Run the Bot
```bash
./venv/bin/python slave_bot.py
```

For full 24/7 background `systemd` service setup, Wi-Fi power-save fixes, and laptop lid-close configuration on Zorin OS, see [`hosting_guide.md`](hosting_guide.md).
