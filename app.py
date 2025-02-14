import os
import requests
import base64
import urllib.parse
import re
import smtplib
import csv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify

# Flask app setup
app = Flask(__name__)

# Zoom API Credentials (Replace with actual credentials)
ZOOM_ACCOUNT_ID = "bVpWBvoVTdeRlnfMBxfTJQ"
ZOOM_CLIENT_ID = "jAlEOB2cRHugcQt2bTjGAA"
ZOOM_CLIENT_SECRET = "s6VQLn3iHqgXfcUPRLikX9UIMvQgzg7N"
BASE_URL = 'https://api.zoom.us/v2'
TARGET_DAYS = [0, 1]  # Monday = 0, Tuesday = 1
TARGET_START_HOUR = 5  # 5 AM EST
TARGET_END_HOUR = 9  # 9 AM EST

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "jessica@pmhu.org"  # 🔹 Change this
SENDER_PASSWORD = "zeaj jskj lfsf rvld"  # 🔹 Change this (Use App Password)
RECIPIENT_EMAIL = "jessicaboykin@gmail.com"  # 🔹 Change this

# 🔹 Function: Get Zoom API Access Token
def get_zoom_access_token():
    url = "https://zoom.us/oauth/token"
    payload = {"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID}
    headers = {"Authorization": f"Basic {get_basic_auth_token()}", "Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to get access token: {response.text}")

# 🔹 Function: Encode API Credentials
def get_basic_auth_token():
    credentials = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
    return base64.b64encode(credentials.encode()).decode()

# 🔹 Function: Get Zoom User ID
def get_zoom_user_id():
    url = f"{BASE_URL}/users/me"
    headers = {"Authorization": f"Bearer {get_zoom_access_token()}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("id")
    else:
        raise Exception(f"Failed to fetch user ID: {response.text}")

# 🔹 Function: Get Zoom Meetings from the Past Week
def get_recent_meetings():
    zoom_user_id = get_zoom_user_id()
    one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    url = f"{BASE_URL}/report/users/{zoom_user_id}/meetings?from={one_week_ago}&to={today}"
    headers = {"Authorization": f"Bearer {get_zoom_access_token()}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        meetings = response.json().get("meetings", [])
        filtered_meetings = []
        
        for meeting in meetings:
            start_time_str = meeting.get("start_time", "")
            if start_time_str:
                start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                est_time = start_time.astimezone(timezone(timedelta(hours=-5)))  # Convert UTC to EST
           
