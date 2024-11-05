import random
import string


user_ids = list(range(1, 101))
recipient_ids = list(range(1, 101))

def generate_message() -> dict:
    random_user_id = random.choice(user_ids)
    recipient_ids_copy = recipient_ids.copy()
    recipient_ids_copy.remove(random_user_id)
    random_recipient_id = random.choice(recipient_ids_copy)
    message = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
    return {
        "sender_id": random_user_id,
        "recipient_id": random_recipient_id,
        "message": message
    }

if __name__ == "__main__":
    for i in range(100):
        print(generate_message())