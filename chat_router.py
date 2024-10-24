from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

from passlib.context import CryptContext
from httpx import AsyncClient

import configparser
from starlette.templating import Jinja2Templates

from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse


from httpx import AsyncClient
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from cassandra.util import uuid_from_time
from datetime import datetime
from cassandra.cluster import Cluster


cluster = Cluster(['127.0.0.1'], port=9042)
session = cluster.connect('chat_app')


import uvicorn
import configparser

import asyncio
import platform
# Set up router
router = APIRouter()


@router.post('/send_message')
async def send_message(request: Request, message: str = Form(...), send_to: str = Form(...), ):
    username = request.session.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Not authenticated')
    query = "INSERT INTO messages (username, message) VALUES (?, ?)"
    session.execute(query, (username, message))
    return RedirectResponse(url='/')