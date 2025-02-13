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
SLACK_VERIFICATION_TOKEN = os.getenv("SLACK_VERIFICATION_TOKEN")

@app.route("/slack", methods=["POST"])
def slack_command():
    data = request.form
    logging.debug(f"Received Slack request: {data}")
    
    if "command" not in data:
        logging.error("Invalid request: Missing command field")
        return jsonify({"error": "Invalid request: No command received"}), 400
    
    if data.get("token") != SLACK_VERIFICATION_TOKEN:
        logging.error("Invalid Slack token received")
        return jsonify({"error": "Invalid request: Token mismatch"}), 403
    
    logging.info("Valid Slack request received")
    
    response_message = {
        "response_type": "in_channel",
        "text": "Processing your Zoom report request... ⏳"
    }
    
    process_zoom_reports()
    
    return jsonify(response_message)

def process_zoom_reports():
    try:
        meeting_uuids = get_recent_meetings()
        reports = []
        
        for meeting_uuid in meeting_uuids:
            participants = get_zoom_meeting_report(meeting_uuid)
            if participants:
                sanitized_uuid = sanitize_filename(meeting_uuid)
                report_filename = f"zoom_report_{sanitized_uuid}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
                save_report_to_csv(participants, report_filename)
                reports.append(f"Report for meeting {sanitized_uuid} generated successfully!")
        
        if reports:
            logging.info(f"Reports generated: {reports}")
        else:
            logging.info("No meetings found in the specified timeframe.")
    except Exception as e:
        logging.error(f"Error processing Slack command: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
