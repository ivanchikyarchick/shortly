from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import random

App = FastAPI()
db = {}

# Цей рядок містить найпростіший HTML код сторінки з формою
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Мій скорочувач посилань</title>
    <style>
        body { font-family: sans-serif; margin: 40px; text-align: center; }
        input[type="text"] { width: 300px; padding: 10px; margin-bottom: 10px; }
        input[type="submit"] { padding: 10px 20px; cursor: pointer; }
        .result { margin-top: 20px; font-size: 1.2em; font-weight: bold; color: green; }
    </style>
</head>
<body>
    <h2>Скорочувач посилань</h2>
    <form action="/shrt" method="post">
        <input type="text" name="link" placeholder="Вставте довге посилання сюди..." required>
        <br>
        <input type="submit" value="Скоротити">
    </form>
    {result_html}
</body>
</html>
"""

# Головна сторінка з формою
@App.get("/", response_class=HTMLResponse)
async def index():
    # Повертаємо HTML шаблон, де замість {result_html} нічого немає
    return HTML_TEMPLATE.format(result_html="")

# Обробка форми (ЗВЕРНИ УВАГУ: тепер ми отримуємо Form(...) замість Pydantic моделі)
@App.post("/shrt", response_class=HTMLResponse)
async def shortlink(request: Request, link: str = Form(...)):
    shrt = ""
    for i in range(5):
        shrt += random.choice("12345678890gnjvktikyhhjcnhtnfdjfedjvfDJKGVNGJNKVGDFGJKDFGHDJKBNVFCXNBILUSRFG")
    
    # Зберігаємо в нашу імпровізовану БД
    db[shrt] = link
    
    # Формуємо повне коротке посилання для відображення
    # request.base_url автоматично підставить http://127.0.0.1:8000 або адресу на Render
    full_short_url = f"{request.base_url}{shrt}"
    
    result_html = f'<div class="result">Твоє коротке посилання:<br><a href="{full_short_url}">{full_short_url}</a></div>'
    
    # Повертаємо ту саму сторінку, але вже зі згенерованим посиланням
    return HTML_TEMPLATE.format(result_html=result_html)

# Перехід за коротким посиланням (цей код майже не змінився)
@App.get("/{shortlnk}")
def go(shortlnk: str):
   url = db.get(shortlnk)
   if not url:
       return {"details": "Not Found"}
   
   # Маленький хак: якщо користувач ввів просто "google.com" без http://,
   # RedirectResponse може спрацювати некоректно. Додамо просту перевірку:
   if not url.startswith("http://") and not url.startswith("https://"):
       url = "http://" + url

   return RedirectResponse(url)
