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
from kafka import KafkaConsumer
from aiokafka import AIOKafkaConsumer


from pydantic import BaseModel

cluster = Cluster(['127.0.0.1'], port=9042)
session = cluster.connect('chat_app')
from kafka.admin import KafkaAdminClient, NewTopic
from kafka import KafkaProducer
import json
import uvicorn
import configparser

import asyncio
import platform

# Set up router
router = APIRouter()


def get_user_info(username: str):
    query = "SELECT * FROM users WHERE username = %s ALLOW FILTERING"
    user_row = session.execute(query, (username,)).one()
    return user_row


def create_kafka_topic(topic_uuid, num_partitions=1, replication_factor=1):
    # Initialize KafkaAdminClient
    admin_client = KafkaAdminClient(
        bootstrap_servers="localhost:9092",  # Replace with your Kafka broker(s)
        client_id="topic_creator"
    )

    # Define a new topic
    topic = NewTopic(
        name=topic_uuid,
        num_partitions=num_partitions,
        replication_factor=replication_factor
    )

    # Create the topic
    try:
        admin_client.create_topics([topic])
        print(f"Created topic '{topic_uuid}'")
    except Exception as e:
        print(f"Failed to create topic '{topic_uuid}': {e}")
    finally:
        # Close the admin client
        admin_client.close()


def fetch_kafka_topics():
    admin_client = KafkaAdminClient(
        bootstrap_servers="localhost:9092",
        client_id="topic_fetcher"
    )
    topics = admin_client.list_topics()
    return topics


def json_serializer(data):
    return json.dumps(data).encode("utf-8")


producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=json_serializer)


def convert_to_tuple(data):
    return tuple(data)


class MessagePayload(BaseModel):
    message: str
    chat_uuid: str


@router.post('/send_message')
async def send_message(request: Request, data: MessagePayload):
    print("Message func called")
    message = data.get('message')
    print(f"Message: {message}")

    username = request.session.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Not authenticated')
    chat_uuid = data.get('chat_uuid')
    user_uuid = get_user_info(username).user_id
    time_uuid = uuid_from_time(datetime.now())
    producer.send(str(chat_uuid), {'message_id': str(time_uuid), 'message': str(message)})
    request.session['current_chat_uuid'] = chat_uuid
    query = """
        INSERT INTO messages (message_id, chat_id, sent_at, created_by, message)
        VALUES (%s, %s, %s, %s, %s)
        """
    session.execute(query, (time_uuid, chat_uuid, datetime.now(), user_uuid, message))

    return RedirectResponse(url='/chat', status_code=303)


@router.post('/create_chat')
async def create_chat(request: Request, chat_with: str = Form(...)):
    username = request.session.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Not authenticated')

    second_user_uuid = get_user_info(chat_with).user_id
    user_uuid = get_user_info(username).user_id
    time_uuid = uuid_from_time(datetime.now())
    access_ids = [user_uuid, second_user_uuid]
    create_kafka_topic(time_uuid, num_partitions=1, replication_factor=1)

    if not second_user_uuid:
        raise HTTPException(status_code=404, detail='User not found')

    request.session['current_chat_uuid'] = str(time_uuid)

    query = """
        INSERT INTO chats (chat_id, created_at, created_by_id, access_ids)
        VALUES (%s, %s, %s, %s)
        """
    session.execute(query, (time_uuid, datetime.now(), user_uuid, access_ids))

    return RedirectResponse(url='/chat', status_code=303)


# DB query
@router.post('/available_chat')
async def available_chat(request: Request):
    username = request.session.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Not authenticated')

    user_uuid = get_user_info(username).user_id
    query = "SELECT * FROM chats WHERE access_ids CONTAINS %s ALLOW FILTERING"
    chat_rows = session.execute(query, (user_uuid,)).all()
    # add to session
    chats = [{'chat_id': str(chat.chat_id), 'other_user': chat.created_by_id} for chat in chat_rows]

    # Add chats to session (if needed)
    request.session['chat_uuid'] = [chat['chat_id'] for chat in chats]

    return chats


# @router.post('/available_chat')
# async def available_chat(request: Request):
#     username = request.session.get('username')
#     if not username:
#         raise HTTPException(status_code=401, detail='Not authenticated')
#
#     user_uuid = get_user_info(username).user_id
#     query = "SELECT * FROM chats WHERE access_ids CONTAINS %s ALLOW FILTERING"
#     chat_row = session.execute(query, (user_uuid,)).all()
#     request.session['available_chats_uuid'] = chat_row
#
#     chats = [{'chat_id': str(chat.chat_id), 'other_user': str(chat.created_by_id)} for chat in chat_row]
#
#     return chats


@router.post('/chat_messages')
async def chat_messages(request: Request):
    try:
        username = request.session.get('username')
        if not username:
            raise HTTPException(status_code=401, detail='Not authenticated')

        chat_uuid = request.session.get('current_chat_uuid')
        if not chat_uuid:
            raise HTTPException(status_code=404, detail='Chat not found')

        print(f"Chat UUID: {chat_uuid}")

        consumer = AIOKafkaConsumer(
            str(chat_uuid),
            bootstrap_servers='localhost:9092',
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            # Only decode if necessary
            value_deserializer=lambda x: json.loads(x.decode('utf-8')) if isinstance(x, bytes) else json.loads(x),
            consumer_timeout_ms=5000,
        )
        await consumer.start()
        messages = []

        try:
            # Set a timeout for reading messages
            read_timeout = 5  # seconds
            start_time = asyncio.get_event_loop().time()

            # Read messages asynchronously
            async for message in consumer:
                if len(messages) >= 20 or (asyncio.get_event_loop().time() - start_time) > read_timeout:
                    break

                # Directly access message.value for debugging
                print(f"Raw message type: {type(message.value)}")
                print(f"Raw message content: {message.value}")

                try:
                    # Deserialize here, now it handles both bytes and str
                    decoded_message = json.loads(message.value.decode('utf-8') if isinstance(message.value, bytes) else message.value)
                    messages.append(decoded_message)
                    print(f"Decoded message: {decoded_message}")
                except json.JSONDecodeError:
                    print(f"Failed to decode message: {message.value}")
        except asyncio.CancelledError:
            print("Consumer was cancelled.")

        finally:
            print("Stopping consumer")
            await consumer.stop()
            print("Consumer stopped")

        print(f"Messages: {messages}")  # This will show the final messages collected
        return messages if messages else []

    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}

# @router.post('/chat_messages')
# async def chat_messages(request: Request):
#     username = request.session.get('username')
#     if not username:
#         raise HTTPException(status_code=401, detail='Not authenticated')
#
#     chat_uuid = request.session.get('chat_uuid')
#     consumer = KafkaConsumer(chat_uuid, bootstrap_servers=['localhost:9092'], auto_offset_reset='earliest')
#     messages = []
#
#     for message in consumer:
#         raw_message = message.value.decode('utf-8')
#         valid_json_message = raw_message.replace("'", '"')
#         try:
#             decoded_message = json.loads(valid_json_message)
#             messages.append(decoded_message)
#         except json.JSONDecodeError as e:
#             print(f"Failed to decode message: {valid_json_message} - Error: {e}")
#
#     return messages
