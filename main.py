from fastapi import FastAPI
import random
from pydantic import BaseModel
from fastapi.responses import RedirectResponse

App = FastAPI()
db={}


class urlRequest(BaseModel):
    link:str


@App.get("/shrt")
def shortlink(link:urlRequest):
    shrt = ""
    for i in range(5):
        shrt = shrt + random.choice("12345678890gnjvktikyhhjcnhtnfdjfedjvfDJKGVNGJNKVGDFGJKDFGHDJKBNVFCXNBILUSRFG")
    db[shrt]=link.link
    return "http://127.0.0.1:8000/" + shrt

@App.get("/{shortlnk}")
def go(shortlnk):
   url = db.get(shortlnk)
   if not url:
       return {"details":"Not Found"}
   return RedirectResponse(url)




