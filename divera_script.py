#!/usr/bin/env python3

import json
import subprocess
import datetime
import requests
import socket
import time
import os

ACCESS_KEY = ''
TELEGRAM_BOT_TOKEN = ''
TELEGRAM_CHAT_ID = ''

with open('settings.propperties', 'r') as config_file:
    config_lines = config_file.readlines()
    for config_line in config_lines:
        config_property = config_line.split('=')
        config_key = config_property[0]
        config_value = config_property[1].replace('\n', '')
        if config_key == 'api_key':
            ACCESS_KEY = config_value
        elif config_key == 'telegram_bot_token':
            TELEGRAM_BOT_TOKEN = config_value
        elif config_key == 'telegram_chat_id':
            TELEGRAM_CHAT_ID = config_value

BORDER_CONTROL = False

if os.path.exists('/etc/divera/config.json'):
    with open('/etc/divera/config.json') as config_file:
        json_conf = json.load(config_file)
        BORDER_CONTROL = json_conf.get('border', False)

HOSTNAME = socket.gethostname()
TELEGRAM_MSG_URL = 'https://api.telegram.org/bot' + TELEGRAM_BOT_TOKEN \
                        + '/sendMessage?chat_id=' + TELEGRAM_CHAT_ID + '&text='

BASE_URL = 'https://www.divera247.com/api'
ALARM_URL = BASE_URL + '/v2/alarms?accesskey=' + ACCESS_KEY
APPOINTMENT_URL = BASE_URL + '/v2/events?accesskey=' + ACCESS_KEY
PRE_APPOINTMENT_TIME = 30 * 60  # First Number is the Time in Minutes to turn display on before an appointment
SUF_APPOINTMENT_TIME = 60 * 60  # First Number is the Time in Minutes to turn display off after an appointment
screen_active = False

border_conn = None
if BORDER_CONTROL:
    import serial
    border_conn = serial.Serial(port='/dev/ttyUSB0')

def sendTelegramMessage(text):
    requests.get(TELEGRAM_MSG_URL + '[' + HOSTNAME + '] ' + text)


class HdmiCec:

    def __init__(self, device_no):
        self.device_no = device_no
        self.last_command = ''
        sendTelegramMessage('Starte Raspberry Pi...')
        os.system("echo 'scan' | cec-client -s -d 1")

    def on(self):
        if self.last_command == 'on':
            return
        self.last_command = 'on'
        sendTelegramMessage('DISPLAY ON')
        os.system("echo 'on " + self.device_no + "' | cec-client -s -d 1")

    def standby(self):
        if self.last_command == 'standby':
            return
        self.last_command = 'standby'
        sendTelegramMessage('DISPLAY OFF')
        os.system("echo 'standby " + self.device_no + "' | cec-client -s -d 1")

class BorderRelais:

    def __init__(self):
        self.border_status = ''
    
    def open(self):
        border_conn.write(b'\xA0\x01\x01\xA2')
        if self.border_status == 'open':
            return
        self.border_status = 'open'
        sendTelegramMessage("BORDER OPEN")
    
    def close(self):
        border_conn.write(b'\xA0\x01\x00\xA1')
        if self.border_status == 'close':
            return
        self.border_status = 'close'
        sendTelegramMessage("BORDER CLOSE")


hdmi_cec = HdmiCec('0')
border_relais = BorderRelais()

while True:

    alert_active = True
    alert_left = False
    appointment_time = False
    border_open = False

    # get current date
    now = datetime.datetime.now()
    day_of_week = now.weekday() + 1  # 1 = Monday
    hour = now.hour
    minutes = now.minute

    # check current active alert
    response = requests.get(ALARM_URL)
    if response.status_code == 200:
        alerts = response.json()
        if alerts['success']:
            alert_list = alerts['data']['items']
            if len(alert_list) == 0:
                alert_active = False
            else:
                for alert_id in alert_list:
                    alert = alert_list[alert_id]
                    if alert['closed']:
                        close_time = datetime.datetime.fromtimestamp(alert['ts_close'] + SUF_APPOINTMENT_TIME)
                        if now > close_time:
                            alert_active = False
                    else:
                        alert_left = True
                        border_open = True

    # check current active appointment
    response = requests.get(APPOINTMENT_URL)
    if response.status_code == 200:
        data = response.json()
        if data['success']:
            for appointment_id in data['data']['items']:
                appointment = data['data']['items'][appointment_id]
                start_time = datetime.datetime.fromtimestamp(appointment['start'] - PRE_APPOINTMENT_TIME)
                end_time = datetime.datetime.fromtimestamp(appointment['end'] + SUF_APPOINTMENT_TIME)
                if start_time < now < end_time:
                    appointment_time = True

    # case: active alert or appointment time
    if alert_active is True or alert_left is True or appointment_time is True:
        hdmi_cec.on()
        screen_active = True

    # case: no active alert and no appointment time
    elif alert_active is False and alert_left is False and appointment_time is False:
        hdmi_cec.standby()
        screen_active = False
        
        # case: monitor off an no mission and it is night time so make updates
        if hour == 3 and minutes == 5:
            sendTelegramMessage('rebooting...')
            subprocess.Popen(['sudo', 'reboot'])
    
    # set border to open/close
    if BORDER_CONTROL:
        if border_open:
            border_relais.open()
        else:
            border_relais.close()

    # sleeps 30 seconds and starts again
    time.sleep(30)
