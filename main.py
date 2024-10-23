from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext

import templates
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2AuthorizationCodeBearer
from httpx import AsyncClient
from fastapi import FastAPI, Depends, HTTPException, Form, Request
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from httpx import AsyncClient
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from sqlalchemy import create_engine, Column, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from sqlalchemy.orm import Session

app = FastAPI()

SECRET_KEY = "cb598c51889059611b4c3bfdecf0ba06cd4b4ac7b47e9e03c9674895b94e33eb"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

# fake_db = {
#     "ivan": {
#         "username": "ivan",
#         "full_name": "Ivan Ivanov",
#         "email": "ivan@gmail.com",
#         "hashed_password": "$2b$12$w0z8y4Z1XV5Vv3w8uFfV1uHj1XJ5PmJ3Q7W7kq7YQj8fZ9jV9kP7G",
#         "disabled": False,
#     }
# }

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# SQLAlchemy Models
class UserModel(Base):
    __tablename__ = "users"

    username = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    disabled = Column(Boolean, default=False)


# Create the database tables
Base.metadata.create_all(bind=engine)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


CLIENT_ID = "Iv23liAxUCpqD2GzvkYQ"
CLIENT_SECRET = "f0d7896168f9b1fe697248e8b81afa4edfa3e8e4"

# oauth2_scheme = OAuth2AuthorizationCodeBearer(
#     authorizationUrl="https://github.com/login/oauth/authorize",
#     tokenUrl="https://github.com/login/oauth/access_token",
# )
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

oauth2_jwt_scheme = OAuth2PasswordBearer(tokenUrl="token")
oauth2_github_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl="https://github.com/login/oauth/authorize",
    tokenUrl="https://github.com/login/oauth/access_token",
)
# app.add_middleware(SessionMiddleware, secret_key="your_secret_key")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str


class User(BaseModel):
    username: str
    email: str or None = None
    full_name: str or None = None
    disabled: bool or None = None


class UserInDB(User):
    hashed_password: str


def save_user(db, username: str, email: str, full_name: str, password: str, disabled: bool):
    hashed_password = get_password_hash(password)
    db_user = UserModel(username=username, email=email, full_name=full_name, hashed_password=hashed_password,
                        disabled=disabled)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user(db: Session, username: str):
    user = db.query(UserModel).filter(UserModel.username == username).first()
    print(f"User (get-userfunc) -> {user}")
    return user


def authenticate_user(db, username: str, password: str):
    user = get_user(db, username)
    print(f"Fetched user: {user}")  # Check if this fetches a valid user object

    if not user:
        print("User not found")
        return False

    if not verify_password(password, user.hashed_password):
        print("Password verification failed")
        return False

    return user


# @app.get("/auth/callback")
# async def auth_callback(code: str, db: Session = Depends(get_db)):
#     async with AsyncClient() as client:
#         response = await client.post(
#             "https://github.com/login/oauth/access_token",
#             data={
#                 "client_id": CLIENT_ID,
#                 "client_secret": CLIENT_SECRET,
#                 "code": code,
#
#             },
#             headers={"Accept": "application/json"},
#         )
#         response_data = response.json()
#         if "access_token" not in response_data:
#             raise HTTPException(status_code=400, detail="Invalid code")
#
#         access_token = response_data["access_token"]
#         user_info_response = await client.get(
#             "https://api.github.com/user",
#             headers={"Authorization": f"token {access_token}"},
#
#         )
#
#         user_info = user_info_response.json()
#         access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
#         access_token = create_access_token(data={"sub": user_info['login']}, expires_delta=access_token_expires)
#         return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/callback")
async def auth_callback(code: str, db: Session = Depends(get_db)):
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
        email = user_info.get("email", None)  # GitHub doesn't always provide email
        full_name = user_info.get("name", "")

        # Check if user exists in the database
        user = get_user(db, username=username)
        if not user:
            # If user doesn't exist, create a new one
            save_user(db, username, email, full_name, password="", disabled=False)

        # Create JWT token
        jwt_token = create_access_token(data={"sub": username})

        # Return JWT token as a response
        return {"access_token": jwt_token, "token_type": "bearer"}


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    print(f"Payload before adding expiration: {to_encode}")
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    print(f"Expire -> {expire}")
    to_encode.update({"exp": expire})
    print(f"Payload before encoding (with expiration): {to_encode}")
    if "sub" not in to_encode:
        raise ValueError("Subject (sub) required in token payload")

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    print(f"Encoded JWT: {encoded_jwt}")
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_jwt_scheme), db: Session = Depends(get_db)) -> dict:
    print(f"Token received in header: {token}")  # Log the received token

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        print(f"Decoding token: {token}")
        print(f"Secret key: {SECRET_KEY}")

        # Decode the token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"Decoded payload: {payload}")  # Log the decoded payload

        username: str = payload.get("sub")
        # if username is None:
        #     raise credentials_exception
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token: missing 'sub'")
        token_data = TokenData(username=username)

    except jwt.ExpiredSignatureError:
        print("Token has expired.")
        raise credentials_exception
    except jwt.InvalidTokenError as e:
        print(f"Invalid token error: {e}")
        raise credentials_exception
    except Exception as e:
        print(f"Unexpected error while decoding token: {e}")
        raise credentials_exception

    user = get_user(db, username=token_data.username)
    # if user is None:
    #     raise credentials_exception
    print(f"Current User -> {user}")

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    print("i got called")
    # if current_user.disabled:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    print(f"Current User -> {current_user}")
    return current_user


# @app.get("/", response_class=HTMLResponse)
# async def read_root(request: Request, current_user: User = Depends(get_current_active_user)):
#     print("home page")
#     return templates.TemplateResponse("index.html", {"request": request, "user": current_user})

@app.get("/")
async def read_root(token: str = Depends(oauth2_jwt_scheme)):
    print(f"Token received in header: {token}")
    return {"message": "Hello, world!"}


@app.get("/login")
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    print(f"Authenticated User -> {user.username}")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # access_token = create_access_token(data={"sub": user}, expires_delta=access_token_expires)
    print(f"User object before token generation: {user}")  # Add this line to check

    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}



@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@app.get("/signup", response_class=HTMLResponse)
async def signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup")
async def signup(request: Request, username: str = Form(...), email: str = Form(...), full_name: str = Form(...),
                 password: str = Form(...), db: SessionLocal = Depends(get_db)):
    existing_user = get_user(db, username)
    if existing_user:
        return templates.TemplateResponse("signup.html", {"request": request, "message": "User already exists"})
    save_user(db, username, email, full_name, password, False)

    return RedirectResponse(url="/login")


# @app.get("/test")
# async def test_token(request: Request):
#     print(f"Headers received: {request.headers}")  # Log all headers for inspection
#     token = request.headers.get("Authorization")
#     print(f"Token received in header: {token}")
#
#     if token:
#         token = token.split(" ")[1]  # Extract only the token part
#         print(f"Extracted Token: {token}")  # Log the extracted token
#     else:
#         raise HTTPException(status_code=401, detail="Token missing")
#
#     # Proceed with decoding
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         print(f"Decoded payload: {payload}")
#     except Exception as e:
#         print(f"Error decoding token: {e}")
#         raise HTTPException(status_code=401, detail="Could not validate credentials")
#     print
#     return {"message": "Token processed successfully"}

@app.get("/test")
async def test_token(request: Request):
    print(f"Headers received: {request.headers}")  # Log all headers
    token = request.headers.get("Authorization")
    print(f"Token received in header: {token}")

    if token:
        token = token.split(" ")[1]  # Extract only the token part
        print(f"Extracted Token: {token}")
    else:
        raise HTTPException(status_code=401, detail="Token missing")

    # Further decoding/validation...



@app.get("/test-create-token")
async def test_create_token():
    test_payload = {
        "sub": "ivan",
        "some_other_claim": "value",
        "exp": datetime.utcnow() + timedelta(minutes=30)  # Ensure you have an expiration
    }
    token = create_access_token(test_payload)
    print(f"Created Token: {token}")

    # Decode the token immediately to verify the payload
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"Decoded payload: {payload}")
    except Exception as e:
        return {"error": str(e)}

    return {"token": token, "payload": payload}


@app.get("/idk")
async def idk(User=Depends(get_current_active_user)):
    return {"message": f"Hello {User.username}", "user": User}
