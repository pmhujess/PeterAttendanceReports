import requests
import csv
import smtplib
import base64
import urllib.parse
import re
import os
import logging
from flask import Flask, request, jsonify
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta, timezone

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

@app.route("/")
def home():
    return "Zoom Report Bot is running successfully!"

# Zoom API Credentials
ZOOM_ACCOUNT_ID = "bVpWBvoVTdeRlnfMBxfTJQ"
ZOOM_CLIENT_ID = "jAlEOB2cRHugcQt2bTjGAA"
ZOOM_CLIENT_SECRET = "s6VQLn3iHqgXfcUPRLikX9UIMvQgzg7N"
BASE_URL = 'https://api.zoom.us/v2'
TARGET_DAYS = [0, 1]  # Monday = 0, Tuesday = 1
TARGET_START_HOUR = 5  # 5 AM EST
TARGET_END_HOUR = 9  # 9 AM EST
SLACK_VERIFICATION_TOKEN = "your_slack_verification_token"

@app.route("/slack", methods=["POST"])
def slack_command():
    data = request.form
    logging.debug(f"Received Slack request: {data}")
    
    if data.get("token") != SLACK_VERIFICATION_TOKEN:
        logging.error("Invalid Slack token received")
        return jsonify({"error": "Invalid request"}), 403
    
    meeting_uuids = get_recent_meetings()
    for meeting_uuid in meeting_uuids:
        participants = get_zoom_meeting_report(meeting_uuid)
        
        if participants:
            sanitized_uuid = sanitize_filename(meeting_uuid)
            report_filename = f"zoom_report_{sanitized_uuid}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
            save_report_to_csv(participants, report_filename)
            
            return jsonify({"text": f"Report for meeting {sanitized_uuid} generated successfully!"})
    
    return jsonify({"text": "No meetings found in the specified timeframe."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
