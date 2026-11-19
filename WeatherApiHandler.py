import requests
import datetime
import os
import json
import sqlite3
import math
import sys
##import numpy as np
from dotenv import load_dotenv
load_dotenv()

##Define as configurações da API
##A chave vem do ambiente: secret do GitHub Actions no CI, ou um arquivo .env local (fora do git).
API_KEY = os.getenv("WEATHER_API_KEY") or os.getenv("API_KEY")
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
CALLS_LOG = "api_calls.json"
DAILY_LIMIT = 950
DB_PATH = 'weather_data.db'


def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=20)  # Added timeout parameter
        conn.execute('PRAGMA foreign_keys = ON')  # Enable foreign key support
        return conn
    except sqlite3.Error as e:
        print(f"Couldn't connect to the database: {e}")
        return None

# Initialize database (create table if not exists)
def init_database():
    try:
        conn = get_db_connection()
        if conn is None:
            return False
        
        cursor = conn.cursor()
            
        # Check if table exists before creating it
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='weather'")
        if not cursor.fetchone():
            cursor.execute('''
            CREATE TABLE weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT,
                temperature REAL,
                feels_like REAL,
                humidity INTEGER,
                rain REAL,
                description TEXT,
                rain_mood TEXT,
                timestamp TEXT
            )
            ''')
            conn.commit()
            print("The database has been created and the tables are now set.")
        
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Couldn't initialize database: {e}")
        return False


#Toda arquitetura do arquivo JSON é para garantir que não ocorram chamadas demais na API, visando evitar o pagamento de taxas extras.
def load_api_log():
    if not os.path.exists(CALLS_LOG):
        return {}
    with open(CALLS_LOG, 'r') as f:
        return json.load(f)

def save_api_log(log):
    with open(CALLS_LOG, 'w') as f:
        json.dump(log, f)

def can_make_api_call():
    log = load_api_log()
    today = datetime.date.today().isoformat()

    if today not in log:
        log[today] = 0

    if log[today] >= DAILY_LIMIT:
        return False, log
    else:
        log[today] += 1
        save_api_log(log)
        return True, log

# Salvar no banco
def save_weather_to_db(weather_data):
    try:
        conn = get_db_connection()
        if conn is None:
            print( "Couldn't create database.")
            return False
        
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        
        cursor.execute('''
        INSERT INTO weather (city, temperature, feels_like, humidity, rain, description, rain_mood, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            weather_data['city'],
            weather_data['temp'],
            weather_data['feels_like'],
            weather_data['humidity'],
            weather_data['rain'],
            weather_data['description'],
            weather_data['rain_mood'],
            now
        ))
        conn.commit()
        print(f"Weather data for {weather_data['city']} has been etched onto the database.")
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"{e} prevented you from saving data to the database.")
        return False

# Pega o clima
def get_weather(city_name):
    allowed, log = can_make_api_call()
    if not allowed:
        print("⚠️ Resquest threshold reached. Why are you abusing my little infrastructure?")
        return False

    params = {
        'q': city_name,
        'appid': API_KEY,
        'units': 'metric',
        'lang': 'en'
    }

    try:
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()

        data = response.json()
        city = data['name']
        temp = data['main']['temp']
        feels = data['main']['feels_like']
        humidity = data['main']['humidity']
        desc = data['weather'][0]['description']
        rain = data.get('rain', {}).get('1h', 0)
        ## rain  = data['main']['rain'] // entrada obsoleta. O erro consiste na busca pela variável rain dentro de main, quando na verdade ela está dentro de outra variável no JSON.
        ##Preciso dimensionar o ponto de orvalho
        ##preciso traduzir a desc = data
        if rain >= 50:
            rain_mood = "Strong rain, I'm probably happy"
        elif rain >= 20:
            rain_mood = "moderate rain, I could be doing better."
        elif rain == 0:
            rain_mood = "No rain, I'm probably sad."
        else:
            rain_mood = "Light rain, it's better than nothing "

        print(f"\n🌤️  The weather in {city} is:\n")
        print(f"Temperature: {temp}°C (Around {feels}°C on flesh)")
        print(f"Relative air humidity: {humidity}%")
        ## print(f"Ponto de orvalho: {dew:.2f}°C")
        print(f"Description: {desc.capitalize()}")
        print(f"is_rain == true?: {rain}mm. {rain_mood}")
        print(f"API requests today: {log[datetime.date.today().isoformat()]}/{DAILY_LIMIT}")

        # Salvar no banco
        weather_data = {
            'city': city,
            'temp': temp,
            'feels_like': feels,
            'humidity': humidity,
            'rain': rain,
            'description': desc,
            'rain_mood' : rain_mood
        }
        return save_weather_to_db(weather_data)

    except requests.exceptions.RequestException as e:
        print("❌ Network error:", e)
    except KeyError:
        print("❌ Couldn't locate this city or JSON format error.")
    except Exception as e:
        print("❌ 404", e)
    return False

def update_readme():
    conn = get_db_connection()
    if conn is None:
        print("Couldn't connect to the database.")
        return False
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM weather ORDER BY id DESC LIMIT 1')
    row = cursor.fetchone()
    conn.close()

    if not row:
        print("❌ No weather data in the database, README not updated.")
        return False

    city, temp, feels_like, humidity, rain, description, rain_mood, timestamp = row[1:]

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(f"""\
### ☁️ 🌤️  The weather in {city} is: {description.capitalize()}

- Temperature: {temp}°C (Around {feels_like}°C on flesh)
- Relative air humidity: {humidity}%
- is_rain == true?: {rain}mm. {rain_mood}
- last updated: {timestamp}
""")
    return True

# bota pa fude
def main():
    if not API_KEY:
        print("❌ WEATHER_API_KEY is not set (GitHub secret or local .env).")
        return False

    if not init_database():
        print("Couldn't initialize databank.")
        return False

    try:
        ##city = input("What city are we scanning today?: ")
        city = str("florianopolis")
        return get_weather(city)
    except Exception as e:
        print(f"Error executing program: {e}")
        import traceback
        traceback.print_exc()
        return False

# entrada do programa
# Sai com código 1 se algo falhar, pra o GitHub Actions marcar o run em vermelho.
if __name__ == "__main__":
    ok = main() and update_readme()
    sys.exit(0 if ok else 1)
