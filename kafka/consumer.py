import json
from kafka import KafkaConsumer

if __name__ == "__main__":
    consumer = KafkaConsumer('messages', bootstrap_servers=['localhost:9092'], auto_offset_reset='earliest')

    for message in consumer:
        raw_message = message.value.decode('utf-8')
        print(f"Raw message: {raw_message}")

        # Replace single quotes with double quotes to create valid JSON
        valid_json_message = raw_message.replace("'", '"')

        try:
            decoded_message = json.loads(valid_json_message)
            print(f"Consumed message: {decoded_message}")
        except json.JSONDecodeError as e:
            print(f"Failed to decode message: {valid_json_message} - Error: {e}")