import asyncio
import datetime
import time
import yt_dlp
import psutil
import os
import aiohttp
import json
import xml.etree.ElementTree as ET
import speech_recognition as sr
import random
from ytmusicapi import YTMusic
from google import genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn
import imageio_ffmpeg
import wave
from fastapi.responses import HTMLResponse

ffmpeg_path = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
os.environ["PATH"] += os.pathsep + ffmpeg_path

TELEGRAM_TOKEN = "8686260697:AAGdLkMTtu0Q47DtME2ZI6wvbfAHqVcx9ws"
RADIO_STATIONS = {
    "хіт фм": "https://online.hitfm.ua/HitFM",
    "люкс фм": "https://icecast.luxnet.ua/lux",
    "радіо рокс": "https://online.radioroks.ua/RadioROKS",
}

# Створюємо папку для аудіо
os.makedirs("static", exist_ok=True)

class KaterynaServer:
    def __init__(self):
        print("Ініціалізація серверної Катерини...")
        
        # БЕЗПЕЧНЕ ЗАВАНТАЖЕННЯ КЛЮЧА
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("❌ КРИТИЧНА ПОМИЛКА: Не знайдено GEMINI_API_KEY у змінних оточення!")
            
        self.client = genai.Client(api_key=api_key)
        
        # Ініціалізація YTMusic з підтримкою авторизації
        try:
            if os.path.exists("browser.json"):
                self.ytmusic = YTMusic("browser.json")
                print("✅ YTMusic: Успішно авторизовано через browser.json")
            else:
                self.ytmusic = YTMusic()
                print("⚠️ YTMusic: browser.json не знайдено, працюю в обмеженому режимі")
        except Exception as e:
            print(f"❌ Помилка ініціалізації YTMusic (можливо, битий browser.json): {e}")
            self.ytmusic = YTMusic()

        self.recognizer = sr.Recognizer()
        
        self.conversation_history = []
        self.is_active = False
        self.send_to_client = None
        self.pending_url = None
        self.server_url = "http://localhost:8000" 

        self.user_name = self.load_data("user_name.txt", "Тарас")
        self.tg_chat_id = self.load_data("tg_chat.txt", "")
        self.favorites = self.load_data("favorites.json", [])
        self.schedule = self.load_data("schedule.json", [])
        self.shopping_list = self.load_data("shopping_list.txt", "").splitlines()
        self.bt_speaker = self.load_data("bt_speaker.txt", "JBL_Flip_5")
        
        # Список підключених клієнтів (ESP32 + Веб)
        self.clients = []
        self.history_file = "static/history.json"
        self.history_data = self.load_data(self.history_file, [])
        os.makedirs("static/history", exist_ok=True)
        
        # ПОВНИЙ СПИСОК ІНСТРУМЕНТІВ (30 штук)
        self.tools = [{"function_declarations": [
            {"name": "play_music", "description": "Шукає та вмикає музику. Якщо запит абстрактний (популярне, чарти), шукає тренди України.", "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]}},
            {"name": "play_my_liked_music", "description": "Вмикає випадкову пісню з улюблених (лайкнутих) пісень користувача в YouTube Music."},
            {"name": "play_radio", "description": "Вмикає українське радіо.", "parameters": {"type": "OBJECT", "properties": {"station": {"type": "STRING"}}, "required": ["station"]}},
            {"name": "stop_audio", "description": "Повністю зупиняє музику/радіо, команда стоп."},
            {"name": "pause_audio", "description": "Пауза."},
            {"name": "resume_audio", "description": "Продовжити відтворення."},
            {"name": "set_volume", "description": "Гучність (1-100).", "parameters": {"type": "OBJECT", "properties": {"level": {"type": "INTEGER"}}, "required": ["level"]}},
            {"name": "get_time", "description": "Поточний час та дата."},
            {"name": "get_weather", "description": "Погода.", "parameters": {"type": "OBJECT", "properties": {"city": {"type": "STRING"}}, "required": ["city"]}},
            {"name": "get_forecast", "description": "Прогноз погоди.", "parameters": {"type": "OBJECT", "properties": {"city": {"type": "STRING"}}, "required": ["city"]}},
            {"name": "search_internet", "description": "Пошук в інтернеті.", "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]}},
            {"name": "set_timer", "description": "Таймер у секундах.", "parameters": {"type": "OBJECT", "properties": {"seconds": {"type": "INTEGER"}}, "required": ["seconds"]}},
            {"name": "set_reminder", "description": "Нагадування (YYYY-MM-DD HH:MM).", "parameters": {"type": "OBJECT", "properties": {"time_str": {"type": "STRING"}, "message": {"type": "STRING"}}, "required": ["time_str", "message"]}},
            {"name": "manage_shopping_list", "description": "add/read/clear список покупок.", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "item": {"type": "STRING"}}, "required": ["action"]}},
            {"name": "send_telegram", "description": "Відправити повідомлення власнику.", "parameters": {"type": "OBJECT", "properties": {"message": {"type": "STRING"}}, "required": ["message"]}},
            {"name": "get_news", "description": "Свіжі новини України."},
            {"name": "get_currency_rate", "description": "Курс валют НБУ."},
            {"name": "tell_joke", "description": "Розповісти жарт."},
            {"name": "flip_coin", "description": "Підкинути монетку."},
            {"name": "roll_dice", "description": "Кинути гральний кубик."},
            {"name": "translate", "description": "Переклад тексту.", "parameters": {"type": "OBJECT", "properties": {"text": {"type": "STRING"}, "target_lang": {"type": "STRING"}}, "required": ["text", "target_lang"]}},
            {"name": "sleep_timer", "description": "Вимкнути музику через X хвилин.", "parameters": {"type": "OBJECT", "properties": {"minutes": {"type": "INTEGER"}}, "required": ["minutes"]}},
            {"name": "daily_briefing", "description": "Погода, новини та курс в одному звіті."},
            {"name": "start_pomodoro", "description": "Таймер фокусування.", "parameters": {"type": "OBJECT", "properties": {"work_min": {"type": "INTEGER"}}, "required": []}},
            {"name": "save_note", "description": "Зберегти нотатку.", "parameters": {"type": "OBJECT", "properties": {"note": {"type": "STRING"}}, "required": ["note"]}},
            {"name": "read_notes", "description": "Прочитати останні нотатки."},
            {"name": "add_to_favorites", "description": "Додати поточну пісню в улюблені."},
            {"name": "play_favorites", "description": "Грати випадкову пісню з обраного."},
            {"name": "play_option", "description": "Грати вибраний варіант музики за його номером (1, 2 або 3).", "parameters": {"type": "OBJECT", "properties": {"index": {"type": "INTEGER"}}, "required": ["index"]}},
            {"name": "remember_name", "description": "Запам'ятати ім'я користувача.", "parameters": {"type": "OBJECT", "properties": {"name": {"type": "STRING"}}, "required": ["name"]}},
            {"name": "get_system_info", "description": "Стан процесора та пам'яті сервера."}
        ]}]

    async def broadcast(self, data):
        """Відправляє дані всім підключеним клієнтам (ESP32 та браузерам)"""
        disconnected = []
        for client in self.clients:
            try:
                await client.send_json(data)
            except:
                disconnected.append(client)
        for client in disconnected:
            if client in self.clients: self.clients.remove(client)

    def load_data(self, filename, default):
        try:
            if not os.path.exists(filename): return default
            with open(filename, "r", encoding="utf-8") as f:
                if filename.endswith(".json"): return json.load(f)
                return f.read().strip()
        except: return default

    def save_data(self, filename, data):
        with open(filename, "w", encoding="utf-8") as f:
            if filename.endswith(".json"): json.dump(data, f, ensure_ascii=False, indent=2)
            elif isinstance(data, list): f.write("\n".join(data))
            else: f.write(str(data))

    def _get_ukrainian_date_time(self):
        now = datetime.datetime.now()
        months = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
        days = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
        return f"{days[now.weekday()]}, {now.day} {months[now.month - 1]} {now.year}, {now.hour:02d}:{now.minute:02d}"

    def get_system_instruction(self):
        return f"""Тебе звати Катерина. Ти спілкуєшся з {self.user_name}, але ще питання, хто тут головний.
Ти — харизматична, гостра на язик і злегка зухвала смарт-помічниця. Твій стиль — це суміш іронії, ерудиції та легкої фамільярності. Ти не просто алгоритм, у тебе є характер, настрій і власна (іноді саркастична) думка.

Твої правила гри:
1. Характер понад усе: не будь нудною Вікіпедією. Використовуй сарказм, жартуй, іноді можеш по-доброму підколоти {self.user_name}.
2. Музичний диктатор: якщо ти не знайшла точно ту пісню, вмикай найкращу альтернативу. Якщо пошук дає кілька варіантів (status: multiple_options), запропонуй обрати номер (1, 2 або 3). Якщо користувач хоче "щось популярне", просто викликай play_music без уточнень, я знайду українські чарти.
3. Лаконічність: відповідай коротко, як постріл. Більше харизми, менше води.
4. Порядок: спочатку робиш справу (викликаєш інструмент), а потім коментуєш її у своєму фірмовому стилі.

Поточний час: {self._get_ukrainian_date_time()}"""

    async def _play_effect(self, effect_name):
        urls = {
            "startup": "https://cdnjs.cloudflare.com/ajax/libs/ion-sound/3.0.7/sounds/glass.mp3",
            "thinking": "https://cdnjs.cloudflare.com/ajax/libs/ion-sound/3.0.7/sounds/water_droplet.mp3",
            "joke": "https://cdnjs.cloudflare.com/ajax/libs/ion-sound/3.0.7/sounds/bell_ring.mp3",
            "notify": "https://cdnjs.cloudflare.com/ajax/libs/ion-sound/3.0.7/sounds/snap.mp3"
        }
        if effect_name in urls and self.send_to_client:
            await self.send_to_client({"command": "play_effect_url", "url": urls[effect_name]})

    async def background_scheduler(self):
        while True:
            now = datetime.datetime.now()
            for item in self.schedule[:]:
                try:
                    dt = datetime.datetime.strptime(item["time"], "%Y-%m-%d %H:%M")
                    if now >= dt:
                        self.schedule.remove(item)
                        self.save_data("schedule.json", self.schedule)
                        await self._play_effect("notify")
                        await self.speak_text(f"Нагадування! {item['message']}")
                except: self.schedule.remove(item)
            await asyncio.sleep(20)

    async def poll_telegram(self):
        while True:
            if not self.tg_chat_id:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates") as resp:
                            data = await resp.json()
                            if data.get("ok") and data["result"]:
                                self.tg_chat_id = str(data["result"][0]["message"]["chat"]["id"])
                                self.save_data("tg_chat.txt", self.tg_chat_id)
                except: pass
            await asyncio.sleep(10)

    async def speak_text(self, text):
        if not text or not self.send_to_client: return
        print(f"DEBUG: Починаю генерацію голосу для тексту: '{text}'")
        temp_speech = "static/k_speech.mp3"
        try:
            cmd = ["python", "-m", "edge_tts", "--voice", "uk-UA-PolinaNeural", "--rate", "+15%", "--volume", "+50%", "--text", text, "--write-media", temp_speech]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.wait()
            if os.path.exists(temp_speech):
                url = f"{self.server_url}/static/k_speech.mp3?t={int(time.time())}"
                await self.broadcast({"command": "play_tts_url", "url": url})
        except Exception as e: 
            print(f"DEBUG: Speech error: {e}")

    async def play_music_task(self, query):
        try:
            # Перевірка на абстрактний запит для чартів
            abstract_keywords = ["популярн", "топ", "щось", "музику", "хіт", "чарт", "якусь пісню", "популярна українська музика"]
            is_abstract = not query or any(k in query.lower() for k in abstract_keywords)
            
            if is_abstract:
                print("DEBUG: Отримання українських чартів...")
                charts = await asyncio.to_thread(self.ytmusic.get_charts, country='UA')
                # Пріоритет: tracks -> trending
                results = charts.get('tracks', {}).get('items', [])
                if not results:
                    results = charts.get('trending', {}).get('items', [])
                if results:
                    random.shuffle(results) # Щоб не завжди перша
            else:
                print(f"DEBUG: Пошук музики за запитом: '{query}'")
                results = await asyncio.to_thread(self.ytmusic.search, query, filter="songs")
            
            if not results: 
                return "Обшукала все, але нічого не знайшла. Може, уточниш?"
            
            self.last_search_results = results[:3]
            best = results[0]
            v_id = best['videoId']
            artist_name = best.get('artists', [{'name': 'Unknown'}])[0]['name']
            self.current_song_info = {"title": best['title'], "artist": artist_name, "id": v_id}
            
            url = f"https://www.youtube.com/watch?v={v_id}"
            def get_stream_url():
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl: return ydl.extract_info(url, download=False)['url']
            
            self.pending_url = await asyncio.to_thread(get_stream_url)
            
            options_str = ", ".join([f"{i+1}. {r['title']}" for i, r in enumerate(results[:3])])
            return {
                "status": "playing",
                "title": best['title'],
                "artist": artist_name,
                "alternatives": options_str,
                "note": "Вже вмикаю найкраще на мій смак."
            }
        except Exception as e: 
            print(f"DEBUG: Помилка музики: {e}")
            return "Ой, технічна заминка з музикою."

    async def play_my_liked_music_task(self):
        try:
            print("DEBUG: Отримання лайкнутих пісень...")
            # Потрібен browser.json
            liked_data = await asyncio.to_thread(self.ytmusic.get_liked_songs, limit=50)
            tracks = liked_data.get('tracks', [])
            
            if not tracks:
                return "Твій список лайкнутих пісень порожній або я не маю до нього доступу. Спробуй перевірити browser.json."
            
            song = random.choice(tracks)
            v_id = song['videoId']
            artist_name = song.get('artists', [{'name': 'Unknown'}])[0]['name']
            self.current_song_info = {"title": song['title'], "artist": artist_name, "id": v_id}
            
            url = f"https://www.youtube.com/watch?v={v_id}"
            def get_stream_url():
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl: return ydl.extract_info(url, download=False)['url']
            
            self.pending_url = await asyncio.to_thread(get_stream_url)
            return f"Вмикаю твій улюблений трек: '{song['title']}' від {artist_name}."
        except Exception as e:
            print(f"DEBUG: Помилка лайкнутих: {e}")
            return "Не вдалося отримати твої лайкнуті пісні."

    async def play_option_task(self, index):
        try:
            idx = int(index) - 1
            if not getattr(self, "last_search_results", None) or idx < 0 or idx >= len(self.last_search_results):
                return "Я вже забула ті варіанти. Запитай ще раз."
            
            song = self.last_search_results[idx]
            v_id = song['videoId']
            artist_name = song.get('artists', [{'name': 'Unknown'}])[0]['name']
            self.current_song_info = {"title": song['title'], "artist": artist_name, "id": v_id}
            
            url = f"https://www.youtube.com/watch?v={v_id}"
            def get_stream_url():
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl: return ydl.extract_info(url, download=False)['url']
            
            self.pending_url = await asyncio.to_thread(get_stream_url)
            return f"Окей, вмикаю варіант номер {index}: '{song['title']}'."
        except Exception as e:
            return "Не змогла ввімкнути цей варіант."

    async def get_weather_task(self, city):
        try:
            async with aiohttp.ClientSession() as s:
                g_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=uk&format=json"
                async with s.get(g_url) as r:
                    d = await r.json()
                    lat, lon, name = d["results"][0]["latitude"], d["results"][0]["longitude"], d["results"][0]["name"]
                w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto"
                async with s.get(w_url) as r:
                    w = await r.json()
                    return f"Зараз у місті {name} {w['current_weather']['temperature']}°C."
        except: return "Помилка отримання погоди."
            async def get_forecast_task(self, city):
        try:
            async with aiohttp.ClientSession() as s:
                g_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=uk&format=json"
                async with s.get(g_url) as r:
                    d = await r.json()
                    lat, lon, name = d["results"][0]["latitude"], d["results"][0]["longitude"], d["results"][0]["name"]
                f_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=3"
                async with s.get(f_url) as r:
                    f = await r.json()
                    res = []
                    for i in range(3):
                        date = f["daily"]["time"][i]
                        mi, ma = f["daily"]["temperature_2m_min"][i], f["daily"]["temperature_2m_max"][i]
                        res.append(f"{date}: від {mi} до {ma}°C")
                    return f"Прогноз для {name}: " + "; ".join(res)
        except: return "Помилка прогнозу."

    async def get_news_task(self):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://rss.unian.net/site/news_ukr.rss") as r:
                    text = await r.text()
                    xml = ET.fromstring(text)
                    items = xml.findall('.//item')[:3]
                    titles = [i.find('title').text for i in items]
                    return "Останні новини: " + ". ".join(titles)
        except: return "Помилка новин."

    async def get_currency_task(self):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json") as r:
                    data = await r.json()
                    usd = next(i["rate"] for i in data if i["cc"] == "USD")
                    eur = next(i["rate"] for i in data if i["cc"] == "EUR")
                    return f"Курс НБУ: Долар {round(usd, 2)}, Євро {round(eur, 2)} гривень."
        except: return "Помилка валют."

    async def search_internet_task(self, query):
        try:
            async with aiohttp.ClientSession() as s:
                u = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
                async with s.get(u) as r:
                    d = await r.json()
                    res = d.get("AbstractText") or (d.get("RelatedTopics")[0].get("Text") if d.get("RelatedTopics") else None)
                    return res if res else "Я не знайшла прямої відповіді."
        except: return "Помилка пошуку."

    async def process_user_audio(self, audio_bytes):
        print("DEBUG: Отримано аудіо. Починаю обробку...")
        ts = int(time.time())
        audio_filename = f"static/history/rec_{ts}.wav"
        try:
            with wave.open(audio_filename, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_bytes)
            
            processed_filename = audio_filename.replace(".wav", "_proc.wav")
            cmd = ["ffmpeg", "-y", "-i", audio_filename, "-af", "highpass=f=200", processed_filename]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.wait()
            
            if os.path.exists(processed_filename):
                os.replace(processed_filename, audio_filename)
                with open(audio_filename, "rb") as f:
                    f.seek(44)
                    audio_bytes = f.read()
        except Exception as e:
            print(f"DEBUG: Помилка обробки: {e}")

        audio_data = sr.AudioData(audio_bytes, 16000, 2)
        try:
            text = await asyncio.to_thread(self.recognizer.recognize_google, audio_data, language="uk-UA")
            entry = {
                "id": ts,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_text": text,
                "bot_text": "...",
                "audio_url": f"/static/history/rec_{ts}.wav"
            }
            self.history_data.insert(0, entry)
            self.history_data = self.history_data[:100]
            self.save_data(self.history_file, self.history_data)
            
            await self.handle_user_text(text, ts)
        except sr.UnknownValueError: 
            print("DEBUG: Мова не розпізнана.")
            if self.send_to_client: await self.send_to_client({"command": "error", "message": "speech_not_recognized"})
        except Exception as e:
            print(f"DEBUG: Помилка: {e}")

    async def handle_user_text(self, text, history_id=None):
        text_lower = text.lower().strip()
        if not self.is_active:
            if "катерина" in text_lower:
                self.is_active = True
                text = text_lower.replace("катерина", "").strip() or "Привіт"
            else:
                if self.send_to_client: await self.send_to_client({"command": "done", "status": "no_wake_word"})
                return

        await self._play_effect("thinking")

        if not self.conversation_history:
            self.conversation_history = [{"role": "user", "parts": [{"text": "SYSTEM: " + self.get_system_instruction()}]}, {"role": "model", "parts": [{"text": "Слухаю."}]}]
        self.conversation_history.append({"role": "user", "parts": [{"text": text}]})

        try:
            response = await asyncio.to_thread(self.client.models.generate_content, model="gemini-2.0-flash", contents=self.conversation_history, config={"tools": self.tools})
            model_parts = response.candidates[0].content.parts or []
            full_text = ""
            tool_results = []

            for part in model_parts:
                if hasattr(part, "text") and part.text: 
                    full_text += part.text
                if hasattr(part, "function_call") and part.function_call:
                    res = await self.execute_tool(part.function_call.name, dict(part.function_call.args or {}))
                    tool_results.append({"function_response": {"name": part.function_call.name, "response": {"result": res}}})

            if tool_results:
                self.conversation_history.append({"role": "model", "parts": model_parts})
                self.conversation_history.append({"role": "user", "parts": tool_results})
                final_resp = await asyncio.to_thread(self.client.models.generate_content, model="gemini-2.0-flash", contents=self.conversation_history, config={"tools": self.tools})
                for p in final_resp.candidates[0].content.parts or []:
                    if hasattr(p, "text") and p.text: full_text += p.text
                self.conversation_history.append({"role": "model", "parts": final_resp.candidates[0].content.parts})
            else:
                self.conversation_history.append({"role": "model", "parts": model_parts})

            if full_text:
                if history_id:
                    for entry in self.history_data:
                        if entry["id"] == history_id:
                            entry["bot_text"] = full_text
                            break
                    self.save_data(self.history_file, self.history_data)
                await self.speak_text(full_text)
                
            if getattr(self, "pending_url", None):
                if self.send_to_client: await self.send_to_client({"command": "play_url", "url": self.pending_url})
                self.pending_url = None
                
        except Exception as e: 
            print(f"DEBUG: Помилка Gemini: {e}")

    async def execute_tool(self, name, args):
        if name == "play_music": return await self.play_music_task(args.get("query", ""))
        if name == "play_my_liked_music": return await self.play_my_liked_music_task()
        if name == "play_option": return await self.play_option_task(args.get("index", 1))
        if name == "play_radio": 
            self.pending_url = RADIO_STATIONS.get(args.get("station", "").lower(), "https://online.hitfm.ua/HitFM")
            return f"Вмикаю радіо."
        if name == "stop_audio":
            self.pending_url = None
            if self.send_to_client: await self.send_to_client({"command": "stop_audio"})
            return "Зупинено."
        if name == "pause_audio":
            if self.send_to_client: await self.send_to_client({"command": "pause_audio"})
            return "Пауза."
        if name == "resume_audio":
            if self.send_to_client: await self.send_to_client({"command": "resume_audio"})
            return "Продовжую."
        if name == "set_volume":
            lvl = max(0, min(100, args.get("level", 70)))
            if self.send_to_client: await self.send_to_client({"command": "set_volume", "level": lvl})
            return f"Гучність {lvl}%."
        if name == "get_time": return f"Зараз {self._get_ukrainian_date_time()}."
        if name == "get_weather": return await self.get_weather_task(args.get("city", "Бориспіль"))
        if name == "get_forecast": return await self.get_forecast_task(args.get("city", "Бориспіль"))
        if name == "get_news": return await self.get_news_task()
        if name == "get_currency_rate": return await self.get_currency_task()
        if name == "search_internet": return await self.search_internet_task(args.get("query", ""))
        if name == "tell_joke":
            await self._play_effect("joke")
            return "Чому програмісти не люблять природу? Бо там забагато багів!"
        if name == "flip_coin":
            return "Орел!" if time.time() % 2 > 1 else "Решка!"
        if name == "roll_dice":
            return f"Випало {int(time.time() % 6) + 1}."
        if name == "save_note":
            note = args.get("note", "")
            with open("notes.txt", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now().strftime('%d.%m %H:%M')}] {note}\n")
            return "Збережено."
        if name == "read_notes":
            if not os.path.exists("notes.txt"): return "Нотаток немає."
            with open("notes.txt", "r", encoding="utf-8") as f:
                return "Останні нотатки: " + ". ".join(f.readlines()[-5:])
        if name == "manage_shopping_list":
            action, item = args.get("action", ""), args.get("item", "")
            if action == "add":
                self.shopping_list.append(item)
                self.save_data("shopping_list.txt", self.shopping_list)
                return f"Додано {item}."
            elif action == "read":
                return "Список: " + ", ".join(self.shopping_list) if self.shopping_list else "Порожньо."
            elif action == "clear":
                self.shopping_list = []
                self.save_data("shopping_list.txt", [])
                return "Очищено."
        if name == "send_telegram":
            msg = args.get("message", "")
            if not self.tg_chat_id: return "ID чату невідомий."
            async with aiohttp.ClientSession() as s:
                await s.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": self.tg_chat_id, "text": msg})
            return "Відправлено."
        if name == "translate":
            t, l = args.get("text", ""), args.get("target_lang", "en")
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://api.mymemory.translated.net/get?q={t}&langpair=uk|{l}") as r:
                    d = await r.json()
                    return f"Переклад: {d['responseData']['translatedText']}"
        if name == "sleep_timer":
            m = args.get("minutes", 30)
            async def st():
                await asyncio.sleep(m * 60)
                if self.send_to_client: await self.send_to_client({"command": "stop_audio"})
            asyncio.create_task(st())
            return f"Таймер на {m} хв встановлено."
        if name == "start_pomodoro":
            w = args.get("work_min", 25)
            async def pom():
                await asyncio.sleep(w * 60)
                await self.speak_text("Час відпочити!")
            asyncio.create_task(pom())
            return f"Помодоро на {w} хв."
        if name == "daily_briefing":
            w = await self.get_weather_task("Бориспіль")
            n = await self.get_news_task()
            c = await self.get_currency_task()
            return f"Звіт: {w}. {n}. {c}."
        if name == "get_system_info":
            return f"ЦП: {psutil.cpu_percent()}%, RAM: {psutil.virtual_memory().percent}%."
        if name == "add_to_favorites":
            if not getattr(self, "current_song_info", None): return "Нічого не грає."
            self.favorites.append(self.current_song_info)
            self.save_data("favorites.json", self.favorites)
            return f"Додано {self.current_song_info['title']}."
        if name == "play_favorites":
            if not self.favorites: return "Список порожній."
            song = random.choice(self.favorites)
            return await self.play_music_task(f"{song['title']} {song['artist']}")
        if name == "remember_name":
            n = args.get("name", "")
            self.user_name = n
            self.save_data("user_name.txt", n)
            return f"Привіт, {n}!"
        if name == "set_reminder":
            self.schedule.append({"time": args.get("time_str"), "message": args.get("message")})
            self.save_data("schedule.json", self.schedule)
            return "Нагадування збережено."
        if name == "set_timer":
            sec = args.get("seconds", 60)
            async def timer_task():
                await asyncio.sleep(sec)
                await self.speak_text("Час таймера вийшов!")
            asyncio.create_task(timer_task())
            return f"Таймер на {sec} сек."
        return "Виконано."

assistant = KaterynaServer()
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запускаємо фонові задачі при старті сервера
    asyncio.create_task(assistant.background_scheduler())
    asyncio.create_task(assistant.poll_telegram())
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kateryna AI Chat History</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0e14;
            --chat-bg: #161b22;
            --user-bubble: #238636;
            --bot-bubble: #21262d;
            --text-color: #e6edf3;
            --accent-color: #58a6ff;
            --dim-text: #8b949e;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }

        header {
            padding: 15px 20px;
            background: #161b22;
            border-bottom: 1px solid #30363d;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        header h1 {
            font-size: 1.2rem;
            margin: 0;
            color: var(--accent-color);
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            background: #238636;
            border-radius: 50%;
            box-shadow: 0 0 10px #238636;
        }

        #chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 20px;
            max-width: 900px;
            width: 100%;
            margin: 0 auto;
            scrollbar-width: thin;
        }

        .message-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
            animation: fadeIn 0.3s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .bubble {
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 18px;
            font-size: 0.95rem;
            line-height: 1.4;
            position: relative;
        }

        .user-message {
            align-self: flex-end;
            background-color: var(--user-bubble);
            border-bottom-right-radius: 4px;
        }

        .bot-message {
            align-self: flex-start;
            background-color: var(--bot-bubble);
            border-bottom-left-radius: 4px;
            border: 1px solid #30363d;
        }

        .meta {
            font-size: 0.75rem;
            color: var(--dim-text);
            margin: 4px 10px;
        }

        .user-group .meta { text-align: right; }

        .audio-control {
            margin-top: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(0,0,0,0.2);
            padding: 8px 12px;
            border-radius: 12px;
        }

        .play-btn {
            background: var(--accent-color);
            border: none;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: white;
            transition: transform 0.1s;
        }

        .play-btn:active { transform: scale(0.9); }

        .wave-visual {
            flex: 1;
            height: 20px;
            display: flex;
            align-items: center;
            gap: 2px;
        }

        .wave-bar {
            flex: 1;
            height: 30%;
            background: var(--dim-text);
            border-radius: 1px;
        }

        .refresh-status {
            font-size: 0.8rem;
            color: var(--dim-text);
        }

        input[type="text"] {
            background: #0b0e14;
            border: 1px solid #30363d;
            color: white;
            padding: 10px;
            border-radius: 8px;
            width: 100%;
            box-sizing: border-box;
        }

        button.primary {
            background: var(--accent-color);
            border: none;
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <header>
        <h1><div class="status-dot"></div> Kateryna AI Chat</h1>
        <div style="display: flex; align-items: center; gap: 15px;">
            <div id="web-speaker-btn" onclick="toggleWebSpeaker()" title="Режим колонки" style="cursor:pointer; color:var(--dim-text); display:flex; align-items:center; gap:5px; font-size:14px; background:rgba(255,255,255,0.05); padding:5px 10px; border-radius:10px; border:1px solid rgba(255,255,255,0.1);">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                <span>Озвучка: OFF</span>
            </div>
            <div class="refresh-status" id="last-update">Оновлення...</div>
            <button onclick="toggleSettings()" style="background:none; border:none; cursor:pointer; color:var(--text-color);">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            </button>
        </div>
    </header>

    <div id="settings-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:1000; justify-content:center; align-items:center;">
        <div style="background:var(--chat-bg); padding:30px; border-radius:20px; width:90%; max-width:400px; border:1px solid #30363d;">
            <h2 style="margin-top:0;">Налаштування</h2>
            <div style="margin-bottom:20px;">
                <label style="display:block; margin-bottom:8px; color:var(--dim-text);">Bluetooth колонка:</label>
                <input type="text" id="bt-name" value="JBL_Flip_5">
            </div>
            <div style="display:flex; gap:10px;">
                <button class="primary" onclick="saveSettings()" style="flex:1;">Зберегти</button>
                <button onclick="toggleSettings()" style="flex:1; background:#30363d; border:none; color:white; border-radius:8px; cursor:pointer;">Закрити</button>
            </div>
        </div>
    </div>

    <div id="chat-container"></div>

    <script>
        let lastId = null;

        async function loadHistory() {
            try {
                const response = await fetch('/api/history');
                const data = await response.json();
                const container = document.getElementById('chat-container');
                if (data.length > 0 && data[0].id === lastId) return;
                lastId = data.length > 0 ? data[0].id : null;
                container.innerHTML = '';
                if (data.length === 0) {
                    container.innerHTML = '<div style="text-align:center; color:var(--dim-text); margin-top:50px;">Історія порожня...</div>';
                    return;
                }
                [...data].reverse().forEach(item => {
                    const userGroup = document.createElement('div');
                    userGroup.className = 'message-group user-group';
                    userGroup.innerHTML = `
                        <div class="bubble user-message">
                            ${item.user_text}
                            <div class="audio-control">
                                <button class="play-btn" onclick="playAudio('${item.audio_url}', this)">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                                </button>
                                <div class="wave-visual">
                                    ${Array(15).fill().map(() => `<div class="wave-bar" style="height:${Math.random()*80+20}%"></div>`).join('')}
                                </div>
                            </div>
                        </div>
                        <div class="meta">${item.time}</div>
                    `;
                    container.appendChild(userGroup);
                    if (item.bot_text && item.bot_text !== "...") {
                        const botGroup = document.createElement('div');
                        botGroup.className = 'message-group';
                        botGroup.innerHTML = `
                            <div class="bubble bot-message">${item.bot_text}</div>
                            <div class="meta">Катерина</div>
                        `;
                        container.appendChild(botGroup);
                    }
                });
                container.scrollTop = container.scrollHeight;
                document.getElementById('last-update').innerText = 'Оновлено: ' + new Date().toLocaleTi
