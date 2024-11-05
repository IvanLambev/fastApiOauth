import time
import json
import random

from datetime import datetime
from data_generation import generate_message
from kafka import KafkaProducer


def json_serializer(data):
    return json.dumps(data).encode("utf-8")


producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=json_serializer)

if __name__ == "__main__":
    while True:
        message = generate_message()
        print(f"Producing message @ {datetime.now()}: {message}")

        producer.send("messages", message)

        time.sleep(random.randint(1, 5))
