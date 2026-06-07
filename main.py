#!/usr/bin/python3
# -*- coding:utf-8 -*-
import sys
import os
import time
import logging
import threading
import requests
import io
import gc
import socket
import resource
import signal
import json
import asyncio
import pickle
import subprocess
import math
import random
import calendar
import urllib.parse
from collections import deque
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance
from logging.handlers import RotatingFileHandler

# --- GMAIL IMPORTS ---
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# --- SYSTEM LIMITS ---
try:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
except Exception as e:
    print(f"Failed to set rlimit: {e}")

# --- PATHS ---
BASE_DIR = os.path.dirname(os.path.realpath(__file__))
LIB_DIR = os.path.join(BASE_DIR, 'lib')
FONT_DIR = os.path.join(BASE_DIR, 'fnt')
ICON_DIR = os.path.join(BASE_DIR, 'icons')
LOG_FILE = os.path.join(BASE_DIR, 'dashboard.log')

# ######################
# --- WIDGET TOGGLES ---
# ######################
ENABLE_STRAVA = False
ENABLE_BAMBU = False
ENABLE_ROBOROCK = False
ENABLE_ANTIGRAVITY = False
ENABLE_CLAUDE = True
# CLAUDE_MOCK: True = built-in simulated demo usage (no Claude account/OAuth needed);
#             False = real Claude Code usage via OAuth (see claude.py and README).
CLAUDE_MOCK = True
ENABLE_SPOTIFY = False

# --- Cryptocurrency price source ---
# 'binance'   = Binance public market data (reachable from mainland China)
# 'coingecko' = CoinGecko (global, original author's source)
CRYPTO_SOURCE = 'binance'

_CRYPTO_SOURCES = {
    'binance': {
        'btc': 'https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=2h&limit=84',
        'eth': 'https://data-api.binance.vision/api/v3/klines?symbol=ETHUSDT&interval=2h&limit=84',
    },
    'coingecko': {
        'btc': 'https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=7',
        'eth': 'https://api.coingecko.com/api/v3/coins/ethereum/market_chart?vs_currency=usd&days=7',
    },
}

# --- API ENDPOINTS ---
API_ENDPOINTS = {
    'weather': 'https://api.open-meteo.com/v1/forecast',
    'aqi': 'https://air-quality-api.open-meteo.com/v1/air-quality',
    'strava_token': 'https://www.strava.com/oauth/token',
    'strava_auth': 'https://www.strava.com/oauth/authorize',
    'strava_activities': 'https://www.strava.com/api/v3/athlete/activities',
    'btc': _CRYPTO_SOURCES[CRYPTO_SOURCE]['btc'],
    'eth': _CRYPTO_SOURCES[CRYPTO_SOURCE]['eth'],
    'lastfm': 'http://ws.audioscrobbler.com/2.0/'
}

# ===================== LOCALIZATION =====================
# Region preset (one-line switch). Fine-grained overrides below win when set.
REGION = 'China'                 # 'China' | 'Global'

CITIES = {
    # China
    'Shanghai': (31.2304, 121.4737), 'Beijing': (39.9042, 116.4074),
    'Shenzhen': (22.5431, 114.0579), 'Hangzhou': (30.2741, 120.1551),
    'Guangzhou': (23.1291, 113.2644),
    # International
    'Belgrade': (44.8240, 20.4934), 'London': (51.5074, -0.1278),
    'New York': (40.7128, -74.0060), 'Tokyo': (35.6762, 139.6503),
}

# AQI standard: 'china' = HJ633-2012 (computed locally), 'european' = EAQI, 'us' = USAQI
_REGION_PRESETS = {
    'China':  {'aqi_standard': 'china',    'city': 'Shanghai'},
    'Global': {'aqi_standard': 'european', 'city': 'Belgrade'},
}

# Overrides: set a value to override the region preset, or leave None to follow it.
CITY = None                      # e.g. 'Beijing'
AQI_STANDARD = None              # 'china' | 'european' | 'us'

# AQI value at which the on-screen number inverts (white-on-black = air getting worse).
# EAQI is ~0-100; China/US AQI are 0-500, so thresholds differ per scale.
_AQI_INVERT = {'china': 150, 'us': 150, 'european': 50}

_preset = _REGION_PRESETS[REGION]
CITY = CITY or _preset['city']
AQI_STANDARD = AQI_STANDARD or _preset['aqi_standard']
LOCATION_LAT, LOCATION_LON = CITIES[CITY]
# =======================================================

PRINTER_CONF = {
    'IP': '192.168....',
    'SERIAL': '',
    'ACCESS_CODE': ''
}

ROBOROCK_CONF = {
    'EMAIL': 'email...'
}

LASTFM_CONF = {
    'API_KEY': '',
    'USERNAME': ''
}

STRAVA_CONF = {
    'TOKEN_FILE': os.path.join(BASE_DIR, 'strava_token.json')
}

# --- FILES & SCOPES ---
GMAIL_TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')
ROBOROCK_TOKEN_FILE = os.path.join(BASE_DIR, 'roborock_session.pkl')
ROBOROCK_STATS_FILE = os.path.join(BASE_DIR, 'roborock_stats.json')
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

if os.path.exists(LIB_DIR):
    sys.path.append(LIB_DIR)

# core display driver: must succeed (no longer silently swallowed)
from waveshare_epd import epd10in85

# optional SDKs: missing is fine, widgets stay disabled
try:
    import bambulabs_api as bl
    from roborock.web_api import RoborockApiClient
    from roborock.devices.device_manager import create_device_manager, UserParams
except ImportError:
    pass

# --- LOGGING ---
logging.getLogger("bambulabs_api").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("roborock").setLevel(logging.CRITICAL)
logging.getLogger("aiomqtt").setLevel(logging.CRITICAL)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=1)
file_handler.setFormatter(formatter)

logger.handlers.clear()
logger.addHandler(console_handler)
logger.addHandler(file_handler)

icon_cache = {}
global_printer = None


class HardwareTimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise HardwareTimeoutError("Hardware Busy-Wait Timeout")


# --- ROBUST NETWORK MANAGER ---
class NetworkManager:
    def __init__(self):
        self.session = None
        self.create_session()

    def create_session(self):
        if self.session:
            try:
                self.session.close()
            except:
                pass
        gc.collect()
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5, pool_maxsize=10,
            max_retries=requests.adapters.Retry(total=1, backoff_factor=0.5)
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def get_json(self, url, headers=None, data=None, method='GET', timeout=10):
        try:
            if self.session is None: self.create_session()
            if method == 'POST':
                resp = self.session.post(url, headers=headers, data=data, timeout=timeout)
            else:
                resp = self.session.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.create_session()
            return None

    def get_image(self, url, timeout=15):
        try:
            if self.session is None: self.create_session()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            self.create_session()
            return None


net = NetworkManager()


# --- GLOBAL DATA STORE ---
class DataStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.weather = {}
        self.aqi = 0
        self.strava = {
            'rides': 0, 'total_distance': 0,
            'rides_curr': 0, 'distance_curr': 0,
            'rides_prev': 0, 'distance_prev': 0,
            'bike_total': 0, 'hike_total': 0
        }
        self.printer = {'status': 'OFFLINE'}
        self.gmail_unread = 0
        self.spotify = {'status': 'PAUSED', 'text': '', 'cover': None}
        self.claude = {'error': False, 'five_hour': {}, 'seven_day': {}}
        self.antigravity = {'error': False, 'models': []}
        self.roborock = {
            'status': 'OFFLINE', 'battery': 0, 'is_cleaning': False,
            'current_area': 0.0, 'ref_area': 0.0, 'pct': 0.0, 'last_date': '-'
        }
        self.sysload = {'cpu': 0, 'ram_free': 0, 'history': deque(maxlen=30)}
        self.crypto = {'btc': 0, 'eth': 0, 'btc_hist': [], 'eth_hist': []}
        self.ping = {'current': 0, 'history': deque(maxlen=50)}

        self.last_update = {
            'weather': 0, 'strava': 0, 'printer': 0, 'gmail': 0,
            'spotify': 0, 'crypto': 0, 'sysload': 0, 'ping': 0,
            'claude': 0, 'antigravity': 0
        }


data_store = DataStore()


# --- HELPERS ---
def ping_printer(ip):
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '1', ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0
    except:
        return False


def get_cached_icon(name, size, is_white=False):
    key = f"{name}_{size[0]}x{size[1]}_{'white' if is_white else 'black'}"
    if key not in icon_cache:
        path = os.path.join(ICON_DIR, f"{name}.bmp")
        if os.path.exists(path):
            try:
                with Image.open(path) as f_img:
                    img = f_img.convert("L").resize(size)
                    img = ImageOps.invert(img)
                    icon_cache[key] = img.convert("1")
            except:
                return None
        else:
            icon_cache[key] = None
    return icon_cache.get(key)


def compute_china_aqi(cur):
    """China AQI (HJ 633-2012) from open-meteo pollutant concentrations.
    Returns (aqi:int, dominant:str). Real-time hourly values as approximation
    (PM uses 24h breakpoints; SO2/NO2/O3/CO use 1h breakpoints)."""
    IAQI = [0, 50, 100, 150, 200, 300, 400, 500]
    BP = {
        'pm2_5': [0, 35, 75, 115, 150, 250, 350, 500],
        'pm10':  [0, 50, 150, 250, 350, 420, 500, 600],
        'sulphur_dioxide':  [0, 150, 500, 650, 800, 1600, 2100, 2620],
        'nitrogen_dioxide': [0, 100, 200, 700, 1200, 2340, 3090, 3840],
        'ozone':            [0, 160, 200, 300, 400, 800, 1000, 1200],
        'carbon_monoxide':  [0, 5, 10, 35, 60, 90, 120, 150],
    }
    def _iaqi(c, bp):
        if c is None:
            return None
        if c > bp[-1]:
            return 500
        for i in range(len(bp) - 1):
            if bp[i] <= c <= bp[i + 1]:
                return (IAQI[i+1]-IAQI[i])/(bp[i+1]-bp[i])*(c-bp[i])+IAQI[i]
        return None
    scores = {}
    for k, bp in BP.items():
        c = cur.get(k)
        if k == 'carbon_monoxide' and c is not None:
            c = c / 1000.0
        v = _iaqi(c, bp)
        if v is not None:
            scores[k] = v
    if not scores:
        return 0, ''
    dominant = max(scores, key=lambda k: scores[k])
    return int(round(scores[dominant])), dominant


def time_until(iso_str):
    if not iso_str: return "N/A"
    try:
        # Handling the explicit +00:00 timezone format
        target = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        diff = target - now
        if diff.total_seconds() < 0: return "Resetting..."
        hours, rem = divmod(diff.total_seconds(), 3600)
        days, hours = divmod(hours, 24)
        if days > 0:
            return f"{int(days)}d {int(hours)}h"
        else:
            minutes = rem // 60
            return f"{int(hours)}h {int(minutes)}m"
    except Exception:
        return "N/A"


# --- AUTH & FETCH THREADS ---

def auth_claude():
    global ENABLE_CLAUDE
    if not ENABLE_CLAUDE: return
    if CLAUDE_MOCK:
        # mock mode: built-in simulated usage, no OAuth/network needed
        return
    try:
        import claude
        success = claude.interactive_auth()
        if not success:
            ENABLE_CLAUDE = False
            print("Claude widget is disabled.")
    except ImportError:
        print("claude.py not found. Claude widget disabled.")
        ENABLE_CLAUDE = False


def simulate_claude_usage():
    # 1-hour window; value ramps from a random start (10-20%) to a random end
    # (50-90%). start/end are deterministic per window (seeded by window index),
    # so the value only moves smoothly upward within the hour, then resets.
    now = time.time()
    WIN = 3600
    win_idx = int(now // WIN)
    progress = (now % WIN) / WIN
    def gen(seed_off):
        rng = random.Random(win_idx * 1000 + seed_off)
        start = rng.uniform(10, 20)
        end = rng.uniform(50, 90)
        return int(round(start + (end - start) * progress))
    # 5h window resets on a 5-hour boundary, 7d window on a 7-day boundary (distinct)
    FIVE_H = 5 * 3600
    SEVEN_D = 7 * 86400
    resets_5h = datetime.fromtimestamp((int(now // FIVE_H) + 1) * FIVE_H, tz=timezone.utc).isoformat()
    resets_7d = datetime.fromtimestamp((int(now // SEVEN_D) + 1) * SEVEN_D, tz=timezone.utc).isoformat()
    return {
        'error': False,
        'five_hour': {'utilization': gen(1), 'resets_at': resets_5h},
        'seven_day': {'utilization': gen(2), 'resets_at': resets_7d},
    }


def auth_antigravity():
    global ENABLE_ANTIGRAVITY
    if not ENABLE_ANTIGRAVITY: return
    try:
        import antigravity
        success = antigravity.interactive_auth()
        if not success:
            ENABLE_ANTIGRAVITY = False
            print("Antigravity widget is disabled.")
    except ImportError:
        print("antigravity.py not found. Antigravity widget disabled.")
        ENABLE_ANTIGRAVITY = False


def auth_strava():
    global ENABLE_STRAVA
    if not ENABLE_STRAVA: return

    if os.path.exists(STRAVA_CONF['TOKEN_FILE']):
        return

    print("\n--- STRAVA CONFIGURATION REQUIRED ---")
    c_id = input("Enter Strava Client ID (or press Enter to disable): ").strip()
    if not c_id:
        print("Strava is disabled. Fallback widget (System Load) will be used.\n")
        ENABLE_STRAVA = False
        return

    c_secret = input("Enter Strava Client Secret: ").strip()

    auth_url = (
        f"{API_ENDPOINTS['strava_auth']}?"
        f"client_id={c_id}&"
        f"response_type=code&"
        f"redirect_uri=http://localhost&"
        f"approval_prompt=force&"
        f"scope=activity:read_all"
    )

    print("\n[!] To get a token with the correct permissions, open this link in your browser:\n")
    print(f"--> {auth_url} <--\n")
    print("Click 'Authorize'. You will be redirected to an empty/error page (localhost).")
    print("Look at the address bar. Copy the 'code' parameter.")

    code_input = input("Enter the 'code' from the URL (or paste the full URL): ").strip()

    if not code_input:
        print("Authorization cancelled. Strava is disabled.\n")
        ENABLE_STRAVA = False
        return

    if 'code=' in code_input:
        try:
            parsed = urllib.parse.urlparse(code_input)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get('code', [code_input])[0]
        except:
            code = code_input.split('code=')[1].split('&')[0]
    else:
        code = code_input

    print("Fetching Access Token...")
    data = {'client_id': c_id, 'client_secret': c_secret, 'code': code, 'grant_type': 'authorization_code'}

    try:
        resp = requests.post(API_ENDPOINTS['strava_token'], data=data)
        resp.raise_for_status()
        token_data = resp.json()
        token_data['client_id'] = c_id
        token_data['client_secret'] = c_secret

        with open(STRAVA_CONF['TOKEN_FILE'], 'w') as f:
            json.dump(token_data, f, indent=4)
        print("Strava Authorization Successful!\n")
    except Exception as e:
        print(f"Failed to fetch Strava tokens: {e}")
        ENABLE_STRAVA = False


def fetch_strava_data():
    if not os.path.exists(STRAVA_CONF['TOKEN_FILE']): return None
    with open(STRAVA_CONF['TOKEN_FILE'], 'r') as f:
        token_data = json.load(f)

    c_id = token_data.get('client_id')
    c_secret = token_data.get('client_secret')

    if time.time() > token_data.get('expires_at', 0):
        data = {'client_id': c_id, 'client_secret': c_secret, 'grant_type': 'refresh_token',
                'refresh_token': token_data.get('refresh_token')}
        new_token = net.get_json(API_ENDPOINTS['strava_token'], data=data, method='POST')
        if new_token and 'access_token' in new_token:
            new_token['client_id'] = c_id
            new_token['client_secret'] = c_secret
            token_data = new_token
            with open(STRAVA_CONF['TOKEN_FILE'], 'w') as f:
                json.dump(token_data, f, indent=4)
        else:
            return None

    access_token = token_data['access_token']

    now_year = datetime.now().year
    start_curr_ts = datetime(now_year, 1, 1).timestamp()
    start_prev_ts = datetime(now_year - 1, 1, 1).timestamp()
    end_prev_ts = datetime(now_year - 1, 12, 31, 23, 59, 59).timestamp()

    page = 1
    total_rides, total_dist = 0, 0
    rides_curr, dist_curr = 0, 0
    rides_prev, dist_prev = 0, 0
    bike_total, hike_total = 0, 0

    headers = {"Authorization": f"Bearer {access_token}"}

    while True:
        url = f"{API_ENDPOINTS['strava_activities']}?page={page}&per_page=100"
        activities = net.get_json(url, headers=headers)
        if not activities: break

        for act in activities:
            t = act.get('type')
            d = act.get('distance', 0)
            act_time = datetime.strptime(act['start_date'], "%Y-%m-%dT%H:%M:%SZ").timestamp()

            if t in ['Ride', 'VirtualRide', 'EBikeRide', 'GravelRide', 'MountainBikeRide']:
                total_rides += 1
                total_dist += d
                bike_total += d
                if act_time >= start_curr_ts:
                    rides_curr += 1
                    dist_curr += d
                elif start_prev_ts <= act_time <= end_prev_ts:
                    rides_prev += 1
                    dist_prev += d
            elif t in ['Hike', 'Walk']:
                hike_total += d

        if len(activities) < 100: break
        page += 1

    return {
        "rides": total_rides,
        "total_distance": round(total_dist / 1000, 1),
        "rides_curr": rides_curr,
        "distance_curr": round(dist_curr / 1000, 1),
        "rides_prev": rides_prev,
        "distance_prev": round(dist_prev / 1000, 1),
        "bike_total": round(bike_total / 1000, 1),
        "hike_total": round(hike_total / 1000, 1)
    }


def auth_roborock(email):
    global ENABLE_ROBOROCK
    if not ENABLE_ROBOROCK: return None

    if os.path.exists(ROBOROCK_TOKEN_FILE):
        try:
            with open(ROBOROCK_TOKEN_FILE, "rb") as f:
                return pickle.load(f)
        except:
            pass

    print("\n--- ROBOROCK AUTHORIZATION REQUIRED ---")

    async def _do_auth():
        web_api = RoborockApiClient(username=email)
        await web_api.request_code()
        code = input(f"Enter 6-digit Roborock auth code sent to {email} (or press Enter to disable): ").strip()
        if not code: return None
        user_data = await web_api.code_login(code)
        with open(ROBOROCK_TOKEN_FILE, "wb") as f: pickle.dump(user_data, f)
        print("Roborock Authorization Successful!\n")
        return user_data

    if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        user_data = asyncio.run(_do_auth())
        if not user_data:
            print("Roborock is disabled. Fallback widget (Ping) will be used.\n")
            ENABLE_ROBOROCK = False
        return user_data
    except Exception as e:
        print(f"Failed to auth Roborock: {e}")
        ENABLE_ROBOROCK = False
        return None


def roborock_update_thread(user_data, email):
    if not ENABLE_ROBOROCK or not user_data: return

    async def _loop():
        ref_area, last_date = 0.0, "-"
        if os.path.exists(ROBOROCK_STATS_FILE):
            try:
                with open(ROBOROCK_STATS_FILE, "r") as f:
                    stats = json.load(f)
                    ref_area, last_date = stats.get("ref_area", 0.0), stats.get("last_date", "-")
            except:
                pass

        user_params = UserParams(username=email, user_data=user_data)
        device_manager = await create_device_manager(user_params)

        short_states = {
            5: "Clean", 6: "Return", 8: "Charge", 10: "Pause",
            17: "Spot", 18: "Room", 22: "Empty", 23: "Wash",
            26: "ToWash", 29: "Map"
        }

        while True:
            try:
                devices = await device_manager.get_devices()
                if devices and devices[0].v1_properties:
                    device = devices[0]
                    status_trait = device.v1_properties.status
                    await status_trait.refresh()
                    current_area = (status_trait.clean_area / 1000000) if status_trait.clean_area else 0

                    is_cleaning = status_trait.state in [5, 6, 10, 17, 18, 22, 23, 26, 29]
                    status_str = short_states.get(status_trait.state, f"S:{status_trait.state}")

                    if not is_cleaning and current_area > 0 and current_area != ref_area:
                        ref_area = current_area
                        last_date = datetime.now().strftime("%d %b %H:%M")
                        with open(ROBOROCK_STATS_FILE, "w") as f: json.dump(
                            {"ref_area": ref_area, "last_date": last_date}, f)

                    pct = (current_area / ref_area) * 100 if is_cleaning and ref_area > 0 else 0.0

                    with data_store.lock:
                        data_store.roborock = {
                            'status': status_str, 'battery': status_trait.battery,
                            'is_cleaning': is_cleaning, 'current_area': current_area,
                            'ref_area': ref_area, 'pct': pct, 'last_date': last_date
                        }
            except Exception as e:
                logging.error(f"Roborock error: {e}")
            await asyncio.sleep(60)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_loop())


def update_data_thread():
    global global_printer

    if ENABLE_BAMBU:
        try:
            global_printer = bl.Printer(PRINTER_CONF['IP'], PRINTER_CONF['ACCESS_CODE'], PRINTER_CONF['SERIAL'])
        except Exception as e:
            logging.error(f"Bambu init error: {e}")
            global_printer = None

    is_connected = False

    while True:
        now = time.time()

        if now - data_store.last_update['weather'] > 600:
            weather_url = f"{API_ENDPOINTS['weather']}?latitude={LOCATION_LAT}&longitude={LOCATION_LON}&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m,weather_code,is_day,uv_index&hourly=temperature_2m,precipitation_probability,weather_code,cloud_cover&timezone=auto&forecast_days=2"
            if AQI_STANDARD == 'china':
                _aqi_fields = 'pm2_5,pm10,sulphur_dioxide,nitrogen_dioxide,ozone,carbon_monoxide'
            elif AQI_STANDARD == 'us':
                _aqi_fields = 'us_aqi'
            else:
                _aqi_fields = 'european_aqi'
            aqi_url = f"{API_ENDPOINTS['aqi']}?latitude={LOCATION_LAT}&longitude={LOCATION_LON}&current={_aqi_fields}&timezone=auto"
            w_data = net.get_json(weather_url)
            a_data = net.get_json(aqi_url)
            with data_store.lock:
                if w_data: data_store.weather = w_data
                if a_data and 'current' in a_data:
                    _cur = a_data['current']
                    if AQI_STANDARD == 'china':
                        data_store.aqi = compute_china_aqi(_cur)[0]
                    elif AQI_STANDARD == 'us':
                        data_store.aqi = _cur.get('us_aqi', 0)
                    else:
                        data_store.aqi = _cur.get('european_aqi', 0)
            data_store.last_update['weather'] = now

        if ENABLE_STRAVA:
            if now - data_store.last_update['strava'] > 900:
                s_data = fetch_strava_data()
                if s_data:
                    with data_store.lock: data_store.strava = s_data
                data_store.last_update['strava'] = now
        else:
            if now - data_store.last_update['sysload'] > 30:
                try:
                    with open('/proc/loadavg', 'r') as f:
                        cpu = float(f.read().split()[0]) * 10
                    with open('/proc/meminfo', 'r') as f:
                        lines = f.readlines()
                        free = int(lines[1].split()[1]) // 1024
                    with data_store.lock:
                        data_store.sysload['cpu'] = min(int(cpu), 100)
                        data_store.sysload['ram_free'] = free
                        data_store.sysload['history'].append(min(int(cpu), 100))
                except:
                    pass
                data_store.last_update['sysload'] = now

        if ENABLE_BAMBU:
            update_interval = 5 if is_connected else 15
            if now - data_store.last_update['printer'] > update_interval:
                is_alive = ping_printer(PRINTER_CONF['IP'])
                if is_alive:
                    try:
                        if not is_connected and global_printer:
                            global_printer.connect()
                            time.sleep(1)
                            is_connected = True
                        if global_printer:
                            status = global_printer.get_state()
                            if status and status != "UNKNOWN":
                                with data_store.lock:
                                    data_store.printer = {
                                        'status': status,
                                        'percentage': global_printer.get_percentage(),
                                        'remaining_time': global_printer.get_time(),
                                        'layers': f"{global_printer.current_layer_num()}/{global_printer.total_layer_num()}"
                                    }
                    except Exception as e:
                        is_connected = False
                        with data_store.lock:
                            data_store.printer['status'] = 'OFFLINE'
                        try:
                            if global_printer: global_printer.disconnect()
                        except:
                            pass
                else:
                    if is_connected:
                        is_connected = False
                        try:
                            global_printer.disconnect()
                        except:
                            pass
                    with data_store.lock:
                        data_store.printer['status'] = 'OFFLINE'
                data_store.last_update['printer'] = now
        else:
            if now - data_store.last_update['crypto'] > 600:
                btc_data = net.get_json(API_ENDPOINTS['btc'])
                eth_data = net.get_json(API_ENDPOINTS['eth'])
                def _crypto_prices(d):
                    if not d:
                        return []
                    if CRYPTO_SOURCE == 'coingecko':
                        return [pt[1] for pt in d.get('prices', [])]
                    return [float(k[4]) for k in d]   # binance klines: close price
                with data_store.lock:
                    btc_p = _crypto_prices(btc_data)
                    if btc_p:
                        data_store.crypto['btc'] = int(btc_p[-1])
                        data_store.crypto['btc_hist'] = btc_p[::max(1, len(btc_p) // 50)][:50]
                    eth_p = _crypto_prices(eth_data)
                    if eth_p:
                        data_store.crypto['eth'] = int(eth_p[-1])
                        data_store.crypto['eth_hist'] = eth_p[::max(1, len(eth_p) // 50)][:50]
                data_store.last_update['crypto'] = now

        if not ENABLE_ROBOROCK and not ENABLE_ANTIGRAVITY:
            if now - data_store.last_update['ping'] > 20:
                try:
                    out = subprocess.check_output(['ping', '-c', '1', '-W', '1', '8.8.8.8']).decode('utf-8')
                    ms = float(out.split('time=')[1].split(' ms')[0])
                except:
                    ms = 0
                with data_store.lock:
                    data_store.ping['current'] = int(ms)
                    data_store.ping['history'].append(int(ms))
                data_store.last_update['ping'] = now

        if now - data_store.last_update['gmail'] > 300:
            try:
                creds = None
                if os.path.exists(GMAIL_TOKEN_PATH):
                    creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, GMAIL_SCOPES)
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                        with open(GMAIL_TOKEN_PATH, 'w') as t: t.write(creds.to_json())
                if creds and creds.valid:
                    service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
                    label_info = service.users().labels().get(userId='me', id='INBOX').execute()
                    with data_store.lock: data_store.gmail_unread = label_info.get('messagesUnread', 0)
            except:
                pass
            data_store.last_update['gmail'] = now

        # Claude usage: mock = built-in simulation; real = external claude.py every 10 min
        if ENABLE_CLAUDE and CLAUDE_MOCK:
            with data_store.lock:
                data_store.claude = simulate_claude_usage()
            data_store.last_update['claude'] = now
        elif ENABLE_CLAUDE and now - data_store.last_update['claude'] > 600:
            try:
                subprocess.run([sys.executable, os.path.join(BASE_DIR, 'claude.py')], capture_output=True, timeout=30)
                usage_path = os.path.join(BASE_DIR, 'usage.json')
                if os.path.exists(usage_path):
                    with open(usage_path, 'r') as f:
                        usage_data = json.load(f)
                    with data_store.lock:
                        data_store.claude = usage_data
                        if "error" in usage_data and "five_hour" not in usage_data:
                            data_store.claude['error'] = True
                        else:
                            data_store.claude['error'] = False
                else:
                    with data_store.lock:
                        data_store.claude['error'] = True
            except Exception as e:
                logging.error(f"Claude update error: {e}")
                with data_store.lock:
                    data_store.claude['error'] = True
            data_store.last_update['claude'] = now

        if ENABLE_ANTIGRAVITY and now - data_store.last_update['antigravity'] > 60:
            try:
                subprocess.run([sys.executable, os.path.join(BASE_DIR, 'antigravity.py')], capture_output=True, timeout=30)
                limits_path = os.path.join(BASE_DIR, 'limits.json')
                if os.path.exists(limits_path):
                    with open(limits_path, 'r', encoding='utf-8') as f:
                        limits_data = json.load(f)
                    with data_store.lock:
                        data_store.antigravity = limits_data
                        if "error" in limits_data:
                            data_store.antigravity['error'] = True
                        else:
                            data_store.antigravity['error'] = False
                else:
                    with data_store.lock:
                        data_store.antigravity['error'] = True
            except Exception as e:
                logging.error(f"Antigravity update error: {e}")
                with data_store.lock:
                    data_store.antigravity['error'] = True
            data_store.last_update['antigravity'] = now

        if ENABLE_SPOTIFY and now - data_store.last_update['spotify'] > 20:
            url = f"{API_ENDPOINTS['lastfm']}?method=user.getrecenttracks&user={LASTFM_CONF['USERNAME']}&api_key={LASTFM_CONF['API_KEY']}&format=json&limit=2&rnd={int(now)}"
            s_data = net.get_json(url, timeout=5)
            if s_data:
                try:
                    tracks = s_data.get('recenttracks', {}).get('track', [])
                    if isinstance(tracks, dict): tracks = [tracks]
                    if tracks:
                        current_track = tracks[0]
                        is_playing = current_track.get('@attr', {}).get('nowplaying') == 'true'
                        if is_playing:
                            track_name = current_track.get('name', 'Unknown')
                            artist = current_track.get('artist', {}).get('#text', 'Unknown')
                            img_url = ""
                            for img in current_track.get('image', []):
                                if img.get('size') == 'extralarge': img_url = img.get('#text', '')
                            cover_dithered = None
                            if img_url:
                                img_bytes = net.get_image(img_url)
                                if img_bytes:
                                    img_pil = Image.open(io.BytesIO(img_bytes)).convert("L").resize((120, 120))
                                    enhancer = ImageEnhance.Contrast(img_pil)
                                    img_pil = enhancer.enhance(3.0)
                                    cover_dithered = img_pil.convert("1", dither=Image.NONE)
                            with data_store.lock:
                                data_store.spotify = {'status': 'PLAYING', 'text': f"{artist} - {track_name}",
                                                      'cover': cover_dithered}
                        else:
                            with data_store.lock:
                                data_store.spotify = {'status': 'PAUSED', 'text': '', 'cover': None}
                except:
                    pass
            data_store.last_update['spotify'] = now

        gc.collect()
        time.sleep(1)


# --- GRAPHICS FUNCTIONS ---
def draw_icon(draw, x, y, name, size=(40, 40), is_white=False):
    icon = get_cached_icon(name, size, is_white)
    if icon:
        draw.bitmap((x, y), icon, fill=255 if is_white else 0)
    else:
        draw.rectangle((x, y, x + size[0], y + size[1]), outline=255 if is_white else 0)


def draw_sparkline(draw, x, y, data, max_items=50, width=400, height=60, color=0, style="bar"):
    if not data: return
    max_val = max(data) if max(data) > 0 else 1
    step = width / max(max_items - 1, 1)

    if style == "line":
        points = []
        for i, val in enumerate(data):
            px = x + i * step
            py = y + height - (val / max_val) * height
            points.append((px, py))
        if len(points) > 1: draw.line(points, fill=color, width=2)
    elif style == "bar":
        bar_w = max(int(step) - 1, 1)
        for i, val in enumerate(data):
            bh = int((val / max_val) * height)
            bx = x + i * step
            by = y + height - bh
            draw.rectangle((bx, by, bx + bar_w, y + height), fill=color)


def get_weather_icon(code, is_day=1):
    if code == 0:
        return "icon_sun" if is_day else "icon_moon"
    elif code in [1, 2]:
        return "icon_partly-cloudy-day"
    elif code == 3:
        return "icon_clouds"
    elif code in [45, 48]:
        return "icon_wind"
    elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return "icon_rain"
    elif code in [71, 73, 75, 85, 86]:
        return "icon_snow"
    elif code in [95, 96, 99]:
        return "icon_lightning"
    return "icon_sun"


def render_screen(epd, fonts):
    Himage = Image.new('1', (epd.width, epd.height), 255)
    draw = ImageDraw.Draw(Himage)

    if not data_store.lock.acquire(timeout=2.0): return Himage
    try:
        weather = data_store.weather.copy()
        aqi = data_store.aqi
        strava = data_store.strava.copy()
        printer = data_store.printer.copy()
        rob = data_store.roborock.copy()
        gmail_unread = data_store.gmail_unread
        spotify = data_store.spotify.copy()
        claude = data_store.claude.copy()
        antigravity = data_store.antigravity.copy()
        sysload = data_store.sysload.copy()
        crypto = data_store.crypto.copy()
        ping = data_store.ping.copy()
    finally:
        data_store.lock.release()

    col_w = epd.width // 3

    # --- COLUMN 1 (Widgets) ---
    col1_x = 20

    # Widget 1: Strava or SysLoad
    y1 = 20
    if ENABLE_STRAVA:
        draw_icon(draw, col1_x, y1, "icon_strava", (60, 60))
        draw.text((col1_x + 70, y1), "STRAVA STATS", font=fonts['28'], fill=0)

        now_y = datetime.now().year
        draw.text((col1_x + 70, y1 + 35),
                  f"{now_y}: {strava.get('distance_curr', 0)} km | {now_y - 1}: {strava.get('distance_prev', 0)} km",
                  font=fonts['20'], fill=0)
        draw.text((col1_x + 70, y1 + 60),
                  f"Total: {strava.get('total_distance', 0)} km | {strava.get('rides', 0)} acts", font=fonts['20'],
                  fill=0)

        draw_icon(draw, col1_x + 70, y1 + 85, "icon_bike", (30, 30))
        draw.text((col1_x + 105, y1 + 90), f"{strava.get('bike_total', 0)} km", font=fonts['20'], fill=0)

        draw_icon(draw, col1_x + 220, y1 + 85, "icon_hike", (30, 30))
        draw.text((col1_x + 255, y1 + 90), f"{strava.get('hike_total', 0)} km", font=fonts['20'], fill=0)

    else:
        draw_icon(draw, col1_x, y1, "icon_cpu", (50, 50))
        draw.text((col1_x + 60, y1), f"SYSTEM LOAD: {sysload['cpu']}%", font=fonts['28'], fill=0)
        draw.text((col1_x + 60, y1 + 35), f"RAM Free: {sysload['ram_free']} MB", font=fonts['20'], fill=0)
        draw_sparkline(draw, col1_x + 60, y1 + 60, list(sysload['history']), max_items=30, width=350, height=40,
                       style="bar")

    draw.line((col1_x, 150, col_w - 20, 150), fill=0, width=2)

    # Widget 2: Bambu or Crypto
    y2 = 170
    if ENABLE_BAMBU:
        p_status = str(printer.get('status', 'OFFLINE')).upper()
        draw_icon(draw, col1_x, y2, "icon_3d", (60, 60))
        draw.text((col1_x + 70, y2), f"PRINTER: {p_status}", font=fonts['28'], fill=0)
        if p_status not in ["OFFLINE", "UNKNOWN", "FINISH"]:
            percent = printer.get('percentage', 0)
            draw.rectangle((col1_x + 70, y2 + 40, col1_x + 400, y2 + 60), outline=0)
            draw.rectangle((col1_x + 70, y2 + 40, col1_x + 70 + int(330 * (percent / 100)), y2 + 60), fill=0)
            draw.text((col1_x + 70, y2 + 70),
                      f"{percent}% | Rem: {printer.get('remaining_time', '0')}m | {printer.get('layers', '0/0')} L",
                      font=fonts['20'], fill=0)
    else:
        draw_icon(draw, col1_x, y2, "icon_btc", (50, 50))
        draw.text((col1_x + 60, y2), f"BTC: ${crypto['btc']}", font=fonts['28'], fill=0)
        draw_sparkline(draw, col1_x + 60, y2 + 35, crypto['btc_hist'], max_items=50, width=350, height=35, style="bar")

        draw_icon(draw, col1_x, y2 + 80, "icon_eth", (50, 50))
        draw.text((col1_x + 60, y2 + 80), f"ETH: ${crypto['eth']}", font=fonts['28'], fill=0)
        draw_sparkline(draw, col1_x + 60, y2 + 115, crypto['eth_hist'], max_items=50, width=350, height=35, style="bar")

    draw.line((col1_x, 320, col_w - 20, 320), fill=0, width=2)

    # Widget 3: Roborock or Ping
    y3 = 340
    if ENABLE_ROBOROCK:
        draw_icon(draw, col1_x, y3, "icon_roborock", (50, 50))
        draw.text((col1_x + 60, y3), f"Bat: {rob['battery']}% | {rob['status']}", font=fonts['28'], fill=0)
        if rob['is_cleaning']:
            draw.text((col1_x + 60, y3 + 35), f"Clean: {rob['current_area']:.1f} m2 ({rob['pct']:.0f}%)",
                      font=fonts['24'], fill=0)
            clamped_pct = min(rob['pct'], 100)
            draw.rectangle((col1_x + 60, y3 + 70, col1_x + 390, y3 + 90), outline=0)
            draw.rectangle((col1_x + 60, y3 + 70, col1_x + 60 + int(330 * (clamped_pct / 100)), y3 + 90), fill=0)
        else:
            draw.text((col1_x + 60, y3 + 35), f"Last: {rob['last_date']} | {rob['ref_area']:.1f} m2", font=fonts['24'],
                      fill=0)
    elif ENABLE_ANTIGRAVITY:
        draw_icon(draw, col1_x, y3, "icon_cpu", (50, 50))
        draw.text((col1_x + 60, y3), "ANTIGRAVITY USAGE", font=fonts['28'], fill=0)
        
        if antigravity.get('error'):
            draw.text((col1_x + 60, y3 + 35), "Error loading data", font=fonts['20'], fill=0)
        else:
            models = antigravity.get('models', [])
            opus = next((m for m in models if m.get('modelId') == 'claude-opus-4-6-thinking'), None)
            gemini = next((m for m in models if m.get('modelId') == 'gemini-3-pro-high'), None)
            
            y_off = y3 + 35
            for m_data in (opus, gemini):
                if m_data:
                    label = "Opus 4.6" if m_data.get('modelId') == 'claude-opus-4-6-thinking' else "Gemini 3Pro"
                    pct = m_data.get('usedPercentage', 0)
                    rem_time = time_until(m_data.get('resetDate'))
                    
                    draw.text((col1_x + 60, y_off), f"{label} {pct}% | In {rem_time}", font=fonts['20'], fill=0)
                    
                    bx, bw, bh = col1_x + 60, 330, 15
                    draw.rectangle((bx, y_off + 25, bx + bw, y_off + 25 + bh), outline=0, width=2)
                    fill_w = int((bw - 4) * min(pct / 100.0, 1.0))
                    if fill_w > 0: draw.rectangle((bx + 2, y_off + 27, bx + 2 + fill_w, y_off + 25 + bh - 2), fill=0)
                    
                    y_off += 50
    else:
        draw_icon(draw, col1_x, y3, "icon_wifi", (50, 50))
        draw.text((col1_x + 60, y3), f"Internet Quality: {ping['current']} ms", font=fonts['28'], fill=0)
        draw_sparkline(draw, col1_x, y3 + 60, list(ping['history']), max_items=50, width=400, height=40, style="bar")

    draw.line((col_w, 10, col_w, 470), fill=0, width=2)

    # --- COLUMN 2 (Weather) ---
    col2_x = col_w + 20

    if 'current' in weather:
        cur = weather['current']
        temp = cur.get('temperature_2m', 0)
        hum = cur.get('relative_humidity_2m', 0)
        pres = cur.get('surface_pressure', 0)
        w_code = cur.get('weather_code', 0)
        wind_dir = cur.get('wind_direction_10m', 0)
        wind_spd = cur.get('wind_speed_10m', 0)
        is_day = cur.get('is_day', 1)
        uv_index = cur.get('uv_index', 0.0)

        temp_rounded = math.floor(temp + 0.5)

        draw_icon(draw, col2_x, 20, get_weather_icon(w_code, is_day), (90, 90))
        # City label centered under the weather icon — at-a-glance location for multi-region
        _city_label = CITY.upper()
        try:
            _bb = draw.textbbox((0, 0), _city_label, font=fonts['20'])
            _cw = _bb[2] - _bb[0]
        except AttributeError:
            _cw = draw.textsize(_city_label, font=fonts['20'])[0]
        draw.text((col2_x + 45 - _cw // 2, 114), _city_label, font=fonts['20'], fill=0)
        draw.text((col2_x + 100, 10), f"{temp_rounded}°C", font=fonts['80'], fill=0)

        uv_x, uv_y = col2_x + 320, 25
        uv_rounded = math.floor(uv_index + 0.5)
        draw.text((uv_x, uv_y), "UV", font=fonts['28'], fill=0)
        uv_val_str = str(uv_rounded)
        try:
            bbox = draw.textbbox((0, 0), uv_val_str, font=fonts['60'])
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            tw, th = draw.textsize(uv_val_str, font=fonts['60'])

        uv_val_x, uv_val_y = uv_x + 45, 5
        if uv_rounded >= 6:
            pad = 5
            draw.rectangle((uv_val_x - pad, uv_val_y - pad + 10, uv_val_x + tw + pad, uv_val_y + th + pad), fill=0)
            draw.text((uv_val_x, uv_val_y), uv_val_str, font=fonts['60'], fill=255)
        else:
            draw.text((uv_val_x, uv_val_y), uv_val_str, font=fonts['60'], fill=0)

        draw.text((col2_x + 135, 95), f"Humidity: {hum}%", font=fonts['20'], fill=0)
        draw.text((col2_x + 135, 120), f"Press: {pres} hPa", font=fonts['20'], fill=0)

        draw.line((col2_x, 140, col2_x + col_w - 40, 140), fill=0, width=2)

        y_c2 = 160
        draw_icon(draw, col2_x + 5, y_c2, "icon_wind", (30, 30))

        cx, cy, r = col2_x + 80, y_c2 + 80, 60
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=0, width=2)

        for angle in range(0, 360, 45):
            rad_tick = math.radians(angle)
            inner_r = r - 8 if angle % 90 == 0 else r - 4
            tx1, ty1 = cx + inner_r * math.cos(rad_tick), cy + inner_r * math.sin(rad_tick)
            tx2, ty2 = cx + r * math.cos(rad_tick), cy + r * math.sin(rad_tick)
            draw.line((tx1, ty1, tx2, ty2), fill=0, width=2)

        draw.text((cx - 8, cy - r - 22), "N", font=fonts['20'], fill=0)
        draw.text((cx - 8, cy + r + 4), "S", font=fonts['20'], fill=0)
        draw.text((cx + r + 6, cy - 10), "E", font=fonts['20'], fill=0)
        draw.text((cx - r - 24, cy - 10), "W", font=fonts['20'], fill=0)

        rad_arrow = math.radians(wind_dir - 90)
        tip_x = cx + (r - 12) * math.cos(rad_arrow)
        tip_y = cy + (r - 12) * math.sin(rad_arrow)
        base_angle = math.radians(150)
        left_x = cx + 20 * math.cos(rad_arrow + base_angle)
        left_y = cy + 20 * math.sin(rad_arrow + base_angle)
        right_x = cx + 20 * math.cos(rad_arrow - base_angle)
        right_y = cy + 20 * math.sin(rad_arrow - base_angle)
        draw.polygon([(tip_x, tip_y), (left_x, left_y), (right_x, right_y)], fill=0)
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=0)

        spd_text = f"{wind_spd} km/h"
        try:
            bbox = draw.textbbox((0, 0), spd_text, font=fonts['20'])
            tw = bbox[2] - bbox[0]
        except AttributeError:
            tw = draw.textsize(spd_text, font=fonts['20'])[0]

        draw.text((cx - tw / 2, cy + 25), spd_text, font=fonts['20'], fill=0)

        aqi_x = col2_x + 180
        draw.text((aqi_x, y_c2 + 10), "AIR QUALITY", font=fonts['20'], fill=0)
        draw.text((aqi_x, y_c2 + 55), "AQI:", font=fonts['28'], fill=0)

        aqi_str = str(aqi)
        try:
            bbox = draw.textbbox((0, 0), aqi_str, font=fonts['80'])
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            tw, th = draw.textsize(aqi_str, font=fonts['80'])

        val_x, val_y = aqi_x + 80, y_c2 + 66

        if aqi >= _AQI_INVERT.get(AQI_STANDARD, 50):
            pad = 20
            draw.rectangle((val_x - pad, val_y - pad + 15, val_x + tw + pad, val_y + th + pad - 5), fill=0)
            draw.text((val_x, val_y), aqi_str, font=fonts['80'], fill=255)
        else:
            draw.text((val_x, val_y), aqi_str, font=fonts['80'], fill=0)

        draw.line((col2_x, 320, col2_x + col_w - 40, 320), fill=0, width=2)

        hourly = weather.get('hourly', {})
        times = hourly.get('time', [])
        temps = hourly.get('temperature_2m', [])
        codes = hourly.get('weather_code', [])

        cur_iso = datetime.now().strftime("%Y-%m-%dT%H:00")
        try:
            start_idx = times.index(cur_iso) + 1
        except:
            start_idx = 0

        for i in range(4):
            idx = start_idx + i
            if idx < len(times):
                off_x = col2_x + (i * 105)
                draw.text((off_x + 10, 340), f"{times[idx].split('T')[1][:5]}", font=fonts['24'], fill=0)
                draw_icon(draw, off_x + 15, 375, get_weather_icon(codes[idx], 1), (60, 60))
                f_temp = math.floor(temps[idx] + 0.5)
                draw.text((off_x + 15, 440), f"{f_temp}°C", font=fonts['24'], fill=0)

    draw.line((col_w * 2, 10, col_w * 2, 470), fill=0, width=2)

    # --- COLUMN 3 (Time, Claude/Spotify/Progress, Gmail) ---
    col3_x = col_w * 2 + 30
    dt = datetime.now()

    # 1. Time & Date
    draw.text((col3_x, 10), dt.strftime("%H:%M"), font=fonts['clock'], fill=0)

    date_str = dt.strftime("%d %B %Y")
    day_str = dt.strftime("%a").upper()

    draw.text((col3_x, 170), date_str, font=fonts['32'], fill=0)
    draw.text((col3_x + 340, 170), day_str, font=fonts['32'], fill=0)

    draw.line((col3_x, 220, epd.width - 20, 220), fill=0, width=2)

    # 2. Claude AI OR Spotify OR Time Progress
    sp_y = 240
    # Clear background for widget
    draw.rectangle((col3_x, sp_y, col3_x + 420, sp_y + 130), fill=255)

    if ENABLE_CLAUDE:
        draw.text((col3_x, sp_y), "CLAUDE AI USAGE", font=fonts['28'], fill=0)

        if claude.get('error'):
            draw.text((col3_x, sp_y + 50), "Claude Usage Error", font=fonts['24'], fill=0)
        else:
            # 5-Hour Limit
            pct_5h = claude.get('five_hour', {}).get('utilization', 0)
            resets_5h = claude.get('five_hour', {}).get('resets_at')
            rem_5h = time_until(resets_5h)

            draw.text((col3_x, sp_y + 40), f"5-Hour Limit: {pct_5h}% (Resets in {rem_5h})", font=fonts['20'], fill=0)
            bx, bw, bh = col3_x, 400, 15
            draw.rectangle((bx, sp_y + 65, bx + bw, sp_y + 65 + bh), outline=0, width=2)
            fill_w = int((bw - 4) * min(pct_5h / 100.0, 1.0))
            if fill_w > 0: draw.rectangle((bx + 2, sp_y + 67, bx + 2 + fill_w, sp_y + 65 + bh - 2), fill=0)

            # 7-Day Limit
            pct_7d = claude.get('seven_day', {}).get('utilization', 0)
            resets_7d = claude.get('seven_day', {}).get('resets_at')
            rem_7d = time_until(resets_7d)

            draw.text((col3_x, sp_y + 90), f"7-Day Limit: {pct_7d}% (Resets in {rem_7d})", font=fonts['20'], fill=0)
            draw.rectangle((bx, sp_y + 115, bx + bw, sp_y + 115 + bh), outline=0, width=2)
            fill_w = int((bw - 4) * min(pct_7d / 100.0, 1.0))
            if fill_w > 0: draw.rectangle((bx + 2, sp_y + 117, bx + 2 + fill_w, sp_y + 115 + bh - 2), fill=0)

    elif ENABLE_SPOTIFY:
        if spotify['cover']:
            Himage.paste(spotify['cover'], (col3_x, sp_y))
        else:
            draw_icon(draw, col3_x, sp_y, "icon_spotify", (120, 120))

        status_ico = "icon_play" if spotify['status'] == 'PLAYING' else "icon_pause"
        draw_icon(draw, col3_x + 140, sp_y + 10, status_ico, (30, 30))

        if spotify['status'] == 'PLAYING':
            words = spotify['text'].split(' - ')
            artist = words[0] if len(words) > 0 else "Unknown"
            track = words[1] if len(words) > 1 else ""
            draw.text((col3_x + 180, sp_y + 10), artist[:20], font=fonts['28'], fill=0)
            draw.text((col3_x + 140, sp_y + 50), track[:25], font=fonts['24'], fill=0)

    else:
        # Fallback: Time Progress
        tp_y = sp_y
        draw.text((col3_x, tp_y), "TIME PROGRESS", font=fonts['28'], fill=0)

        day_pct = (dt.hour * 3600 + dt.minute * 60 + dt.second) / 86400.0
        days_in_m = calendar.monthrange(dt.year, dt.month)[1]
        month_pct = (dt.day - 1 + (dt.hour / 24.0)) / days_in_m
        days_in_y = 366 if calendar.isleap(dt.year) else 365
        year_pct = (dt.timetuple().tm_yday - 1 + (dt.hour / 24.0)) / days_in_y

        def draw_prog(y_offset, label, pct):
            draw.text((col3_x, tp_y + y_offset), label, font=fonts['24'], fill=0)
            bx = col3_x + 110
            bw = 200
            bh = 20
            draw.rectangle((bx, tp_y + y_offset + 2, bx + bw, tp_y + y_offset + bh + 2), outline=0, width=2)
            if pct > 0:
                fill_w = int((bw - 4) * min(pct, 1.0))
                if fill_w > 0:
                    draw.rectangle((bx + 2, tp_y + y_offset + 4, bx + 2 + fill_w, tp_y + y_offset + bh), fill=0)
            draw.text((bx + bw + 15, tp_y + y_offset), f"{int(pct * 100)}%", font=fonts['24'], fill=0)

        draw_prog(40, "DAY", day_pct)
        draw_prog(75, "MONTH", month_pct)
        draw_prog(110, "YEAR", year_pct)

    draw.line((col3_x, 380, epd.width - 20, 380), fill=0, width=2)

    # 3. Gmail
    gm_y = 400
    draw_icon(draw, col3_x, gm_y, "icon_mail", (60, 60))
    draw.text((col3_x + 80, gm_y + 10), f"Unread Inbox: {gmail_unread}", font=fonts['35'], fill=0)

    return Himage


# --- MAIN LOOP ---
def main():
    auth_strava()
    auth_claude()
    auth_antigravity()
    roborock_user_data = auth_roborock(ROBOROCK_CONF['EMAIL'])

    signal.signal(signal.SIGALRM, timeout_handler)
    epd = None

    try:
        epd = epd10in85.EPD()
        epd.init()
        epd.Clear()
        time.sleep(1)
        epd.init_Part()

        def load_font(name, size):
            return ImageFont.truetype(os.path.join(FONT_DIR, name), size)

        fonts = {
            '20': load_font('Aldrich-Regular.ttc', 20),
            '24': load_font('Aldrich-Regular.ttc', 24),
            '28': load_font('Aldrich-Regular.ttc', 28),
            '32': load_font('Aldrich-Regular.ttc', 32),
            '35': load_font('Aldrich-Regular.ttc', 35),
            '40': load_font('Aldrich-Regular.ttc', 40),
            '60': load_font('Aldrich-Regular.ttc', 60),
            '80': load_font('Aldrich-Regular.ttc', 80),
            'clock': load_font('advanced_led_board-7.ttc', 180),
        }

        t_data = threading.Thread(target=update_data_thread)
        t_data.daemon = True
        t_data.start()

        if ENABLE_ROBOROCK:
            t_robo = threading.Thread(target=roborock_update_thread, args=(roborock_user_data, ROBOROCK_CONF['EMAIL']))
            t_robo.daemon = True
            t_robo.start()

        refresh_counter = 0

        while True:
            start_time = time.time()
            try:
                signal.alarm(20)
                image = render_screen(epd, fonts)
                buf = epd.getbuffer(image)

                if refresh_counter >= 600:
                    logging.info("Full Refresh cycle")
                    epd.init()
                    epd.display(buf)
                    time.sleep(2)
                    epd.init_Part()
                    refresh_counter = 0
                else:
                    logging.info("Partial Refresh")
                    epd.display_Partial(buf, 0, 0, epd.width, epd.height)
                    refresh_counter += 1

                signal.alarm(0)
                del image
                del buf
                if refresh_counter % 10 == 0: gc.collect()

            except HardwareTimeoutError:
                logging.critical("HARDWARE HANG DETECTED!")
                signal.alarm(0)
                logging.shutdown()
                os.execv(sys.executable, ['python'] + sys.argv)
            except OSError as e:
                signal.alarm(0)
                if e.errno == 24:
                    os.execv(sys.executable, ['python'] + sys.argv)
            except Exception as e:
                signal.alarm(0)
                logging.error(f"Unexpected error in main: {e}")

            elapsed = time.time() - start_time
            sleep_time = max(5, 60 - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        try:
            signal.alarm(0)
            epd10in85.epdconfig.module_exit(cleanup=True)
        except:
            pass
        exit()


if __name__ == '__main__':
    main()
