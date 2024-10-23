from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from httpx import AsyncClient
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from passlib.context import CryptContext  # Import passlib for password hashing

from sqlalchemy import create_engine, Column, String, Boolean
# from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base

import uvicorn
import configparser

import asyncio
import platform

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize FastAPI and add session middleware
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your_secret_key")  # type: ignore

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

templates = Jinja2Templates(directory="templates")


# GitHub OAuth credentials


# CLIENT_ID = "Iv23liAxUCpqD2GzvkYQ"
# CLIENT_SECRET = "e7a3c18a5ebd130c5f71eb3b779ee66887ddb8b0"

def get_github_credentials():
    config = configparser.ConfigParser()  # Correctly instantiate ConfigParser
    config.read('config.ini')

    client_id = config['github']['CLIENT_ID']
    client_secret = config['github']['CLIENT_SECRET']

    return client_id, client_secret


# Use the function
CLIENT_ID, CLIENT_SECRET = get_github_credentials()

# Password hashing setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@app.middleware("http")
async def redirect_http_to_https(request: Request, call_next):
    if request.url.scheme != "https":
        url = request.url.replace(scheme="https", netloc=request.url.netloc)
        return RedirectResponse(url=url)
    response = await call_next(request)
    return response


# SQLAlchemy model for user
class UserModel(Base):
    __tablename__ = "users"
    username = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    disabled = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Helper functions
def get_user(db: Session, username: str):
    return db.query(UserModel).filter(UserModel.username == username).first()


def save_user(db, username: str, email: str, full_name: str, password: str, disabled: bool):
    hashed_password = pwd_context.hash(password)  # Hash the password before saving
    db_user = UserModel(username=username, email=email, full_name=full_name, hashed_password=hashed_password,
                        disabled=disabled)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# GitHub OAuth callback
@app.get("/auth/callback")
async def auth_callback(request: Request, code: str, db: Session = Depends(get_db)):
    async with AsyncClient() as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        response_data = response.json()
        if "access_token" not in response_data:
            raise HTTPException(status_code=400, detail="Invalid code")

        access_token = response_data["access_token"]
        user_info_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {access_token}"},
        )
        user_info = user_info_response.json()
        print(f"User info: {user_info}")
        username = user_info["login"]
        email = user_info.get("email", None)
        full_name = user_info.get("name", "")

        # Check if user exists in the database
        user = get_user(db, username=username)
        if not user:
            # If user doesn't exist, create a new one
            save_user(db, username, email, full_name, password="", disabled=False)

        # Store the user info in the session
        print(f"Storing user info in session: {username}, {full_name}")
        try:
            request.session['username'] = username
            request.session['full_name'] = full_name
            print(f"Session data after saving: {request.session}")
        except Exception as e:
            print(f"Error: {e}")

        return RedirectResponse(url="/", status_code=303)


@app.get("/login/github")
async def login_github():
    redirect_uri = "https://localhost:8000/auth/callback"
    return RedirectResponse(
        url=f"https://github.com/login/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={redirect_uri}&scope=user:email"
    )


# Sign up user
@app.post("/signup")
async def signup(request: Request, username: str = Form(...), email: str = Form(...), full_name: str = Form(...),
                 password: str = Form(...), db: Session = Depends(get_db)):
    existing_user = get_user(db, username)
    if existing_user:
        return templates.TemplateResponse("signup.html", {"request": request, "message": "User already exists"})
    save_user(db, username, email, full_name, password, False)
    return RedirectResponse(url="/login")


# Login page (GET method)
@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# Login endpoint (POST method)
@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = get_user(db, username)
    if not user or not pwd_context.verify(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "message": "Invalid credentials"})

    # Store user session
    request.session['username'] = user.username
    request.session['full_name'] = user.full_name

    return RedirectResponse(url="/", status_code=303)


# Logout endpoint
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")


# Retrieve current user from session
@app.get("/me", response_class=HTMLResponse)
async def get_current_user(request: Request):
    print(f"Session data in /me: {request.session}")
    if "username" not in request.session:
        print("Redirecting to login")
        # return RedirectResponse(url="/login")

    username = request.session.get("username")
    full_name = request.session.get("full_name")

    return templates.TemplateResponse("me.html", {"request": request, "username": username, "full_name": full_name})


# Home page
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    print(f"Session data: {request.session}")
    if "username" not in request.session:
        return RedirectResponse(url="/login")

    username = request.session.get("username")
    return templates.TemplateResponse("index.html", {"request": request, "username": username})

import os

if __name__ == "__main__":
    # # Check if the files exist before starting uvicorn
    # print(os.path.exists(r"./certs/myCA.pem"))
    # print(os.path.exists(r"./certs/myCA.key"))
    # print(os.path.exists(r"./certs/hellfish.test.crt"))

    uvicorn.run(
        "sessionBasedLogic:app",
        host="127.0.0.1",
        port=8000,
        ssl_ca_certs=r"./certs/myCA.pem",
        ssl_keyfile=r"./certs/newPrivateKey.key",
        ssl_certfile=r"./certs/newCert.crt",
        reload=True,

    )

# uvicorn sessionBasedLogic:app --host 127.0.0.1 --port 8000 --ssl-ca-certs ./certs/myCA.pem --ssl-keyfile ./certs/newPrivateKey.key --ssl-certfile ./certs/newCert.crt

