from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from passlib.context import CryptContext
from httpx import AsyncClient
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
import configparser
from starlette.templating import Jinja2Templates
from cassandra.util import uuid_from_time
from datetime import datetime
# Set up router
router = APIRouter()

# Cassandra setup
cluster = Cluster(['127.0.0.1'], port=9042)
session = cluster.connect('chat_app')  # Connect to the keyspace

# Jinja2 Templates
templates = Jinja2Templates(directory="templates")

# Password hashing setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# GitHub OAuth credentials
def get_github_credentials():
    config = configparser.ConfigParser()
    config.read('config.ini')
    client_id = config['github']['CLIENT_ID']
    client_secret = config['github']['CLIENT_SECRET']
    return client_id, client_secret


CLIENT_ID, CLIENT_SECRET = get_github_credentials()


# Helper function to get user from Cassandra
def get_user(username: str):
    query = "SELECT * FROM users WHERE username = %s ALLOW FILTERING"
    user_row = session.execute(query, (username,)).one()
    return user_row


# Helper function to save user to Cassandra
def save_user(username: str, email: str, fullname: str, password: str, disabled: bool):
    hashed_password = pwd_context.hash(password)  # Hash the password before saving
    user_id = uuid_from_time(datetime.now())
    query = """
    INSERT INTO users (user_id, username, email, fullname, hashed_password, disabled)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    session.execute(query, (user_id, username, email, fullname, hashed_password, disabled))


# GitHub OAuth callback
@router.get("/auth/callback")
async def auth_callback(request: Request, code: str):
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
        username = user_info["login"]
        email = user_info.get("email", None)
        fullname = user_info.get("name", "")

        # Check if user exists in the database
        user = get_user(username)
        if not user:
            save_user(username, email, fullname, password="", disabled=False)

        # Store the user info in the session
        request.session['username'] = username
        request.session['fullname'] = fullname

        return RedirectResponse(url="/", status_code=303)


# Login with GitHub
@router.get("/login/github")
async def login_github():
    redirect_uri = "https://localhost:8000/auth/callback"
    return RedirectResponse(
        url=f"https://github.com/login/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={redirect_uri}&scope=user:email"
    )


@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


# Sign up user
@router.post("/signup")
async def signup(request: Request, username: str = Form(...), email: str = Form(...), fullname: str = Form(...),
                 password: str = Form(...)):
    existing_user = get_user(username)
    if existing_user:
        return templates.TemplateResponse("signup.html", {"request": request, "message": "User already exists"})
    save_user(username, email, fullname, password, False)
    return RedirectResponse(url="/login")


# Login form (GET method)
@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# Login endpoint (POST method)
@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user(username)
    if not user or not pwd_context.verify(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "message": "Invalid credentials"})
    request.session['username'] = user.username
    request.session['fullname'] = user.fullname
    return RedirectResponse(url="/", status_code=303)


# Logout endpoint
@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")


# Retrieve current user from session
@router.get("/me", response_class=HTMLResponse)
async def get_current_user(request: Request):
    if "username" not in request.session:
        return RedirectResponse(url="/login")
    username = request.session.get("username")
    fullname = request.session.get("fullname")
    return templates.TemplateResponse("me.html", {"request": request, "username": username, "fullname": fullname})
