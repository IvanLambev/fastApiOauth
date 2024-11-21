# Use the official Python 3.11 image as a base
FROM python:3.10

# Set the working directory in the container
WORKDIR /app

# Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose the port that the app will run on
EXPOSE 8000

# Define the command to run your app
CMD ["uvicorn", "sessionBasedLogic:app", "--host", "0.0.0.0", "--port", "8000", "--ssl-ca-certs", "./certs/myCA.pem", "--ssl-keyfile", "./certs/newPrivateKey.key", "--ssl-certfile", "./certs/newCert.crt"]
