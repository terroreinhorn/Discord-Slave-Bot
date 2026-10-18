(Optional Pro-Tip: You can even create a shortcut command called update-slave by running echo "alias update-slave='cd ~/slave-bot && git pull && ~/slave-bot/venv/bin/pip install -U -r requirements.txt && sudo systemctl restart slave-bot'" >> ~/.bashrc && source ~/.bashrc — then you only ever have to type update-slave in your terminal!)

⬆️ How to Push Your Local ~/slave-bot Folder to GitHub (git push)

If you want to upload the files from your Zorin OS laptop directly into your Discord-Slave-Bot repository on GitHub, follow these steps in your terminal:

1. Double-Check Your Token Is NOT Inside slave_bot.py

Before pushing to GitHub, make sure your real Discord token is saved in ~/slave-bot/token.txt and that Line 33 of slave_bot.py says:

DISCORD_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"


(Because .gitignore blocks token.txt, venv/, and slave_data.json, Git will automatically skip your private token and virtual environment when you push!)

2. Log In to GitHub Once (gh auth login)

GitHub no longer accepts regular account passwords in the terminal, so the easiest way to log in once is with the official GitHub CLI (gh):

sudo apt update && sudo apt install -y git gh
gh auth login


Select GitHub.com -> HTTPS -> Yes (authenticate Git with your GitHub credentials) -> Login with a web browser.

Copy the 8-character one-time code shown in the terminal, press Enter to open the browser, and authorize it.

3. Initialize, Commit, and Push Your Folder

Run these commands inside ~/slave-bot (replace YOUR_GITHUB_USERNAME with your actual GitHub username):

cd ~/slave-bot

# Set your Git name and email (required once for commits)
git config --global user.name "YOUR_GITHUB_USERNAME"
git config --global user.email "your_email@example.com"

# Initialize Git and stage your clean files
git init
git branch -M main
git add .gitignore README.md hosting_guide.md requirements.txt slave_bot.py
git commit -m "Update Discord-Slave-Bot v2.2.1 (100% vibe coded)"

# Link to your GitHub repo (skip the 'remote add' line if you already added origin earlier)
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/Discord-Slave-Bot.git

# Push the files up to GitHub!
git push -u origin main --force


4. Pushing Future Edits Anytime Thereafter

Once you've done the setup above, anytime you edit a file on your laptop and want to upload the changes to GitHub, you only need these 3 lines:

cd ~/slave-bot
git add .
git commit -m "Updated bot"
git push


Step 1: Stop the Laptop from Sleeping When You Close the Lid
