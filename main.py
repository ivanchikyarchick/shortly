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
import os

TELEGRAM_TOKEN = "8686260697:AAGdLkMTtu0Q47DtME2ZI6wvbfAHqVcx9ws"
RADIO_STATIONS = {
    "хіт фм": "https://online.hitfm.ua/HitFM",
    "люкс фм": "https://icecast.luxnet.ua/lux",
    "радіо рокс": "https://online.radioroks.ua/RadioROKS",
}

os.makedirs("static", exist_ok=True)

class KaterynaServer:
    def __init__(self):
        print("Ініціалізація серверної Катерини...")
        api_key = os.environ.get("GEMINI_API_KEY")
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
        
        self.tools = [{"function_declarations": [
            {"name": "play_music", "description": "Шукає та вмикає музику.", "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]}},
            {"name": "play_radio", "description": "Вмикає українське радіо.", "parameters": {"type": "OBJECT", "properties": {"station": {"type": "STRING"}}, "required": ["station"]}},
            {"name": "stop_audio", "description": "Повністю зупиняє музику/радіо."},
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
            {"name": "remember_name", "description": "Запам'ятати ім'я користувача.", "parameters": {"type": "OBJECT", "properties": {"name": {"type": "STRING"}}, "required": ["name"]}},
            {"name": "get_system_info", "description": "Стан процесора та пам'яті сервера."}
        ]}]

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
        return f"Тебе звати Катерина. Власник: {self.user_name}.\nТи — професійна смарт-колонка. Працюєш через WebSocket з ESP32.\n1. Спочатку викликай функцію, потім відповідай.\n2. Коли вмикаєш музику, КАЖИ яку.\n3. Будь лаконічною. Час: {self._get_ukrainian_date_time()}"

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
                        await self._play_effect("joke")
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
                                print(f"[Telegram] Підключено ID: {self.tg_chat_id}")
                except: pass
            await asyncio.sleep(10)

    async def speak_text(self, text):
        if not text or not self.send_to_client: return
        print(f"Катерина: {text}")
        temp_speech = "static/k_speech.mp3"
        try:
            cmd = ["python", "-m", "edge_tts", "--voice", "uk-UA-PolinaNeural", "--rate", "+15%", "--volume", "+50%", "--text", text, "--write-media", temp_speech]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.wait()
            if os.path.exists(temp_speech):
                url = f"{self.server_url}/static/k_speech.mp3?t={int(time.time())}"
                await self.send_to_client({"command": "play_tts_url", "url": url})
        except Exception as e: print(f"Speech error: {e}")

    async def play_music_task(self, query):
        try:
            if not query or query.strip().lower() in ["якусь пісню", "музику", "щось"]:
                query = "популярна українська музика 2024"
            results = await asyncio.to_thread(self.ytmusic.search, query, filter="songs")
            if not results: return "Пісню не знайдено."
            
            v_id = results[0]['videoId']
            self.current_song_info = {"title": results[0]['title'], "artist": results[0]['artists'][0]['name'], "id": v_id}
            url = f"https://www.youtube.com/watch?v={v_id}"
            
            def get_stream_url():
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl: return ydl.extract_info(url, download=False)['url']
            
            self.pending_url = await asyncio.to_thread(get_stream_url)
            return f"Знайшла: {results[0]['title']} від {results[0]['artists'][0]['name']}."
        except Exception as e: return "Помилка при пошуку музики."

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
                        res.append(f"{date}: від {mi} до {ma} градусів")
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
        audio_data = sr.AudioData(audio_bytes, 16000, 2)
        try:
            text = await asyncio.to_thread(self.recognizer.recognize_google, audio_data, language="uk-UA")
            await self.handle_user_text(text)
        except sr.UnknownValueError: pass

    async def handle_user_text(self, text):
        text_lower = text.lower().strip()
        
        if not self.is_active:
            if "катерина" in text_lower:
                self.is_active = True
                text = text_lower.replace("катерина", "").strip() or "Привіт"
                print(f"\n✅ Активація! Запит: {text}")
            else:
                print(f"🔇 [Ігнор фону]: {text}")
                return

        await self._play_effect("thinking")

        if not self.conversation_history:
            self.conversation_history = [{"role": "user", "parts": [{"text": "SYSTEM: " + self.get_system_instruction()}]}, {"role": "model", "parts": [{"text": "Привіт! Я готова допомагати."}]}]
        self.conversation_history.append({"role": "user", "parts": [{"text": text}]})

        try:
            response = await asyncio.to_thread(self.client.models.generate_content, model="gemini-2.5-flash", contents=self.conversation_history, config={"tools": self.tools})
            model_parts = response.candidates[0].content.parts or []
            full_text = ""
            tool_results = []

            for part in model_parts:
                if hasattr(part, "text") and part.text: full_text += part.text
                if hasattr(part, "function_call") and part.function_call:
                    res = await self.execute_tool(part.function_call.name, dict(part.function_call.args or {}))
                    tool_results.append({"function_response": {"name": part.function_call.name, "response": {"result": res}}})

            if tool_results:
                self.conversation_history.append({"role": "model", "parts": model_parts})
                self.conversation_history.append({"role": "user", "parts": tool_results})
                final_resp = await asyncio.to_thread(self.client.models.generate_content, model="gemini-2.5-flash", contents=self.conversation_history, config={"tools": self.tools})
                final_parts = final_resp.candidates[0].content.parts or []
                for p in final_parts:
                    if hasattr(p, "text") and p.text: full_text += p.text
                self.conversation_history.append({"role": "model", "parts": final_parts})
            else:
                self.conversation_history.append({"role": "model", "parts": model_parts})

            if full_text:
                await self.speak_text(full_text)
                
            if getattr(self, "pending_url", None):
                if self.send_to_client: await self.send_to_client({"command": "play_url", "url": self.pending_url})
                self.pending_url = None
                
        except Exception as e: print(f"Помилка Gemini: {e}")

    async def execute_tool(self, name, args):
        print(f"[Викликаю: {name}]")
        if name == "play_music": return await self.play_music_task(args.get("query", ""))
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
            lvl = args.get("level", 70)
            if lvl <= 10: lvl *= 10
            lvl = max(0, min(100, lvl))
            if self.send_to_client: await self.send_to_client({"command": "set_volume", "level": lvl})
            return f"Гучність встановлено на {lvl}%."
            
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
            await self._play_effect("coin")
            return "Випав Орел!" if time.time() % 2 > 1 else "Випала Решка!"
        if name == "roll_dice":
            await self._play_effect("dice")
            return f"Випало число {int(time.time() % 6) + 1}."
            
        if name == "save_note":
            note = args.get("note", "")
            with open("notes.txt", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now().strftime('%d.%m %H:%M')}] {note}\n")
            await self._play_effect("note")
            return "Нотатку збережено."
        if name == "read_notes":
            if not os.path.exists("notes.txt"): return "Нотаток немає."
            with open("notes.txt", "r", encoding="utf-8") as f:
                return "Ваші нотатки: " + ". ".join(f.readlines()[-5:])
                
        if name == "manage_shopping_list":
            action, item = args.get("action", ""), args.get("item", "")
            if action == "add":
                self.shopping_list.append(item)
                self.save_data("shopping_list.txt", self.shopping_list)
                return f"Додано {item} у список."
            elif action == "read":
                return "У списку покупок: " + ", ".join(self.shopping_list) if self.shopping_list else "Список порожній."
            elif action == "clear":
                self.shopping_list = []
                self.save_data("shopping_list.txt", [])
                return "Список очищено."
                
        if name == "send_telegram":
            msg = args.get("message", "")
            if not self.tg_chat_id: return "Помилка: Напишіть боту в Telegram спочатку."
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
            return f"Таймер сну на {m} хвилин встановлено."
            
        if name == "start_pomodoro":
            w = args.get("work_min", 25)
            async def pom():
                await asyncio.sleep(w * 60)
                await self._play_effect("joke")
                await self.speak_text("Час роботи вийшов! Пора відпочити.")
            asyncio.create_task(pom())
            return f"Помодоро на {w} хвилин запущено."
            
        if name == "daily_briefing":
            w = await self.get_weather_task("Бориспіль")
            n = await self.get_news_task()
            c = await self.get_currency_task()
            return f"Ваш звіт: {w}. {n}. {c}."
            
        if name == "get_system_info":
            return f"Завантаження процесора {psutil.cpu_percent()}%, пам'ять {psutil.virtual_memory().percent}%."
            
        if name == "add_to_favorites":
            if not self.current_song_info: return "Зараз нічого не грає."
            if any(f.get('id') == self.current_song_info['id'] for f in self.favorites): return "Вже в обраному."
            self.favorites.append(self.current_song_info)
            self.save_data("favorites.json", self.favorites)
            return f"Додала {self.current_song_info['title']} в обране."
            
        if name == "play_favorites":
            if not self.favorites: return "Список порожній."
            song = random.choice(self.favorites)
            return await self.play_music_task(f"{song['title']} {song['artist']}")
            
        if name == "remember_name":
            n = args.get("name", "")
            self.user_name = n
            self.save_data("user_name.txt", n)
            return f"Приємно познайомитись, {n}!"
            
        if name == "set_reminder":
            self.schedule.append({"time": args.get("time_str"), "message": args.get("message")})
            self.save_data("schedule.json", self.schedule)
            return "Нагадування збережено."
            
        if name == "set_timer":
            sec = args.get("seconds", 60)
            async def timer_task():
                await asyncio.sleep(sec)
                await self._play_effect("notify")
                await self.speak_text("Час таймера вийшов!")
            asyncio.create_task(timer_task())
            return f"Таймер на {sec} секунд запущено."
            
        return "Виконано."

assistant = KaterynaServer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(assistant.background_scheduler())
    asyncio.create_task(assistant.poll_telegram())
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("ESP32 підключено!")
    
    host = websocket.headers.get("host", "localhost:8000")
    scheme = "https" if "onrender" in host else "http"
    assistant.server_url = f"{scheme}://{host}"
    
    async def send_json(data):
        try:
            await websocket.send_json(data)
        except Exception as e: pass
            
    assistant.send_to_client = send_json
    await assistant._play_effect("startup")
    
    audio_buffer = bytearray()
    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message:
                audio_buffer.extend(message["bytes"])
            elif "text" in message:
                data = json.loads(message["text"])
                if data.get("action") == "process_audio":
                    if len(audio_buffer) > 0:
                        await assistant.process_user_audio(bytes(audio_buffer))
                        audio_buffer.clear()
    except (WebSocketDisconnect, RuntimeError):
        print("ESP32 відключено.")
        assistant.send_to_client = None

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
