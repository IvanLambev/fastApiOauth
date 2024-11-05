from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import uvicorn
import platform
import asyncio
# from auth_router import router as auth_router  # Import the router
from chat_router import router as chat_router  # Import the router
from auth_router_cassandra import router as auth_router  # Import the router
from fastapi.middleware.cors import CORSMiddleware

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize FastAPI and add session middleware
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your_secret_key")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with specific origins if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)  # type: ignore

# Jinja2 Templates
templates = Jinja2Templates(directory="templates")

# Register the auth router
app.include_router(auth_router)
app.include_router(chat_router)


@app.middleware("http")
async def redirect_http_to_https(request: Request, call_next):
    try:
        if request.url.scheme != "https":
            url = request.url.replace(scheme="https", netloc=request.url.netloc)
            return RedirectResponse(url=url)
        response = await call_next(request)
        return response
    except Exception as e:
        print(f"Error: {e}")
        return RedirectResponse(url="https://localhost:8000")


# Home page
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    print(f"Session data: {request.session}")
    if "username" not in request.session:
        return RedirectResponse(url="/login")
    username = request.session.get("username")
    return templates.TemplateResponse("index.html", {"request": request, "username": username})


@app.get("/chat", response_class=HTMLResponse)
async def chat(request: Request):
    print(f"Session data: {request.session}")
    if "username" not in request.session:
        return RedirectResponse(url="/login")
    username = request.session.get("username")
    return templates.TemplateResponse("chatroom.html", {"request": request, "username": username})


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        ssl_ca_certs=r"./certs/myCA.pem",
        ssl_keyfile=r"./certs/newPrivateKey.key",
        ssl_certfile=r"./certs/newCert.crt",
        reload=True,
    )
