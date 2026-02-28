# Waveshare-ePaper-10.85 Dashboard

A fully functional E-ink dashboard running on a Raspberry Pi Zero 2W. Designed for large Waveshare e-Paper displays (e.g., 10.85"), this project aggregates essential daily information and smart home status into a clean, minimalist interface.

## Key Features

* **Weather & Air Quality:** Real-time temperature, humidity, wind direction/speed, UV index, 4-hour forecast, and AQI (with visual inversion for high pollution levels) using the Open-Meteo API.
* **Strava Integration:** Displays total and yearly activity statistics (distance and ride counts), including specific breakdowns for biking and hiking.
* **Bambu Lab 3D Printer:** Live monitoring of print status, completion percentage, remaining time, and current layer progress.
* **Roborock Vacuum:** Live battery level, current status, and tracking for cleaned area during active cleaning.
* **Spotify:** Displays the currently playing track and artist.
* **Gmail:** Tracks the number of unread emails in your primary inbox.
* **System Fallbacks:** Automatically switches to displaying System Load (CPU/RAM usage) or Cryptocurrency prices (BTC/ETH) if certain hardware integrations are disabled or offline for demonstration of dashboard capabilities. The fallback wedgets are not required tokens and ready to go.
* **Optimized Rendering:** Uses partial screen refreshes to prevent flickering, with scheduled full refreshes to clear e-ink ghosting.

<img width="2400" height="1792" alt="dashboard_primary" src="https://github.com/user-attachments/assets/20be2eae-4a06-48e2-9ad4-efcba00dcb7f" />
<img width="2400" height="1792" alt="dashboard_fallback" src="https://github.com/user-attachments/assets/158d65ee-9a12-4f09-a9d3-ea66ca3055bc" />

---

## Prerequisites & Installation

### Hardware
* [Raspberry Pi Zero 2W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
* [Waveshare E-Ink Display 10.85"](https://www.waveshare.com/10.85inch-e-paper-hat-plus.htm?sku=29790)

### 1. System Setup
Enable the SPI interface on your Raspberry Pi, which is required for communicating with the e-ink display:
`sudo raspi-config`
Go to Interfacing Options -> SPI -> Enable.

Update your system and install necessary system-level dependencies, including `tmux` for keeping the script running in the background:
`sudo apt update`
`sudo apt install python3-pip python3-pil python3-numpy git tmux -y`

### 2. Python Dependencies
Install the required standard Python packages:
`pip3 install requests Pillow google-api-python-client google-auth-httplib2 google-auth-oauthlib aiomqtt roborock`

*Note: `bambulabs_api` library already included in this package.*

### 3. Display Library
The **patched** version of the epd10in85 library with fixed partial refresh issue already included in this package.

---

## Configuration & Widget Setup

All widget toggles and API configurations are located at the top of the `main.py` script. You can enable or disable specific widgets using the `ENABLE_*` boolean variables.

### Strava
1. Go to your Strava API Settings and create an API Application.
2. Note down your **Client ID** and **Client Secret**.
3. Run the `main.py` script from the terminal for the first time.
4. The script will pause, ask for your ID/Secret, and print an authorization URL in the console. 
5. Open that URL in your browser, click "Authorize", and you will be redirected to a dead `localhost` page.
6. Copy the `code=...` portion from your browser's address bar and paste it back into the terminal. The script will automatically fetch and save the required `activity:read_all` tokens to `strava_token.json`.

### Roborock
1. Open `main.py` and input your Roborock account email address in the `ROBOROCK_CONF` dictionary.
2. Run the script from the terminal.
3. The script will request an OTP (One-Time Password) which will be sent to your email.
4. Enter the 6-digit code in the terminal. The script will securely save your session data locally.

### Bambu Lab 3D Printer
**You DON'T need to enable "LAN Mode" on your Bambu Lab printer to access local data.**
1. On your printer's screen, go to **Settings -> Network**.
2. Note your printer's **IP Address**, **Serial Number**, and **Access Code**. (Force on your router to map exact IP address)
3. Update the `PRINTER_CONF` dictionary in the script with these local credentials.

### Spotify (via Last.fm)
Since the official Spotify API requires running a local web server for complex token renewals, this dashboard uses Last.fm to fetch the current playing track reliably form Spotify. It's is transparent and working method.
1. Connect your Spotify account to Last.fm.
2. Create a Last.fm API account to generate an **API Key**.
3. Update `LASTFM_CONF` in the script with your API Key and Last.fm Username.
** After configuration, you don't need to use last.fm service, Payed last.fm account is not required. You can coutinue use only spotify service **

### Gmail
1. Go to the Google Cloud Console.
2. Create a new project and enable the **Gmail API**.
3. Create OAuth 2.0 Client ID credentials (choose "Desktop Application" as the application type).
4. Download the generated JSON file, rename it exactly to `credentials.json` (if your setup requires it, or just use `token.json` generation), and place it in the same directory as the script.
5. On the first run, the script will open a browser window (or provide a link) for you to log in and grant read-only access. It will generate a `token.json` file for all future headless authentications.

---

## Running the Dashboard

To ensure the dashboard continues running even after you close your SSH connection, use `tmux`.

1. Start a new tmux session:
`tmux new -s dashboard`

2. Run the script inside the tmux session:
`python3 main.py`

3. Detach from the session (leave it running in the background) by pressing:
`Ctrl+B`, then release and press `D`.

To reattach to the session later and view the logs or stop the script:
`tmux attach -t dashboard`

## How It Works

The dashboard is built on a robust, multi-threaded architecture designed to keep the UI responsive and prevent hardware lockups.

* **Asynchronous Data Fetching:** Instead of fetching all data sequentially, the script spawns dedicated background threads. Each service (Weather, Strava, Roborock, Bambu Lab, etc.) pulls data asynchronously at its own specific interval. This ensures that a slow API response or a temporary network drop from one service will never block the others or freeze the system.
* **Scheduled Rendering:** The main application loop acts purely as a renderer. It collects the latest available information from a thread-safe global data store and pushes a new frame to the e-ink display exactly once per minute using a partial screen refresh. 

**Important Notes:**

* **Initial Data Population Delay:** When you first launch the script, you will notice that the widgets may show placeholders or zeros, and the full array of data takes a few minutes to completely appear on the screen. This is an intentional design choice to stagger initial network requests. It prevents sudden spikes in CPU usage, avoids overwhelming the Raspberry Pi's network stack, and respects the rate limits of the external APIs.
* **Hardware Refresh Limits:** The 60-second rendering interval is strictly enforced. Refreshing the screen more frequently than once a minute is strongly discouraged by the display manufacturer (Waveshare). Aggressive refresh rates on large e-paper panels can lead to severe ghosting and may cause permanent hardware damage to the display.
