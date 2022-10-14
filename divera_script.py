#!/usr/bin/env python3

import json
import subprocess
import datetime
import requests
import urllib
import socket
import time
import os

from playsound import playsound

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

BASE_URL = 'https://app.divera247.com/api'
ALARM_URL = BASE_URL + '/v2/alarms?accesskey=' + ACCESS_KEY
INFO_URL = BASE_URL + '/v2/pull/all?accesskey=' + ACCESS_KEY
APPOINTMENT_URL = BASE_URL + '/v2/events?accesskey=' + ACCESS_KEY
TTS_URL = 'https://tts.zoios.net/api/tts?'
TTS_FILE_PATH = '/opt/display-controller/alert_sound.mp3'
PRE_APPOINTMENT_TIME = 30 * 60  # First Number is the Time in Minutes to turn display on before an appointment
SUF_APPOINTMENT_TIME = 60 * 60  # First Number is the Time in Minutes to turn display off after an appointment
SUF_ALERT_SOUND_TIME = 6 * 60 # First Number is the Time in Minutes to play sound after an alert
screen_active = False
DEP_NAME = ''

with requests.get(INFO_URL) as response:
    if response.status_code == 200:
        user_info = response.json()
        if user_info['success']:
            ucr_id = user_info['data']['ucr_active']
            DEP_NAME = user_info['data']['ucr'][str(ucr_id)]['name']
        else:
            print('Could not fetch common data from ' + BASE_URL)
            exit(-1)
    else:
        print('Could not fetch common data from ' + BASE_URL)
        exit(-1)


border_conn = None
if BORDER_CONTROL:
    import serial
    border_conn = serial.Serial(port='/dev/ttyUSB0')


def send_telegram_message(text):
    requests.get(TELEGRAM_MSG_URL + '[' + HOSTNAME + '] ' + text)


def download_alert_sound(text):
    params = {'text': text, 'speaker_id': '', 'style_wav': ''}
    url = TTS_URL + urllib.parse.urlencode(params)
    r = requests.get(url, stream=True)
    with open(TTS_FILE_PATH, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=128):
            fd.write(chunk)


def parse_alert_sound_text(alert_item):
    alert_type = 'Einsatz'
    alert_addressed = ' für die Freiwillige Feuerwehr ' + DEP_NAME + '. '
    alert_keyword = alert_item['title'] + '; '
    alert_address = str(alert_item['address'])
    if alert_item['priority'] is True:
        alert_type = 'Einsatz mit Sonderrechten'
    if alert_item['priority'] is False:
        alert_type = 'Einsatz ohne Eile'
    alert_address = alert_address.replace(alert_address.split(', ')[1].split(' ')[0], '')
    return alert_type + alert_addressed + alert_keyword + alert_address


class HdmiCec:

    def __init__(self, device_no):
        self.device_no = device_no
        self.last_command = ''
        send_telegram_message('Starte Raspberry Pi...')
        os.system("echo 'scan' | cec-client -s -d 1")

    def on(self):
        if self.last_command == 'on':
            return
        self.last_command = 'on'
        send_telegram_message('DISPLAY ON')
        os.system("echo 'on " + self.device_no + "' | cec-client -s -d 1")

    def standby(self):
        if self.last_command == 'standby':
            return
        self.last_command = 'standby'
        send_telegram_message('DISPLAY OFF')
        os.system("echo 'standby " + self.device_no + "' | cec-client -s -d 1")


class BorderRelais:

    def __init__(self):
        self.border_status = ''
    
    def open(self, tts_text):
        if BORDER_CONTROL:
            border_conn.write(b'\xA0\x01\x01\xA2')
        if self.border_status == 'open':
            return
        self.border_status = 'open'
        if BORDER_CONTROL:
            send_telegram_message("border open")
        download_alert_sound(tts_text)
        send_telegram_message('downloaded alert sound')
    
    def close(self):
        if BORDER_CONTROL:
            border_conn.write(b'\xA0\x01\x00\xA1')
        if self.border_status == 'close':
            return
        self.border_status = 'close'
        if BORDER_CONTROL:
            send_telegram_message("border close")


hdmi_cec = HdmiCec('0')
border_relais = BorderRelais()

while True:

    alert_active = True
    alert_left = False
    appointment_time = False
    border_open = False
    play_sound = False
    alert_sound_text = ''

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
                for alert_id in alerts['data']['sorting']:
                    alert = alert_list[str(alert_id)]
                    if alert['closed']:
                        close_time = datetime.datetime.fromtimestamp(alert['ts_close'] + SUF_APPOINTMENT_TIME)
                        if now > close_time:
                            alert_active = False
                        else:
                            alert_left = True
                    else:
                        alert_left = True
                        border_open = True
                        create_time = datetime.datetime.fromtimestamp(alert['ts_publish'] + SUF_ALERT_SOUND_TIME)
                        alert_sound_text = parse_alert_sound_text(alert)
                        if now < create_time:
                            play_sound = True

    # check current active appointment
    response = requests.get(APPOINTMENT_URL)
    if response.status_code == 200:
        data = response.json()
        if data['success']:
            for appointment_id in data['data']['sorting']:
                appointment = data['data']['items'][str(appointment_id)]
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
            send_telegram_message('rebooting...')
            subprocess.Popen(['sudo', 'reboot'])
    
    # set border to open/close
    if border_open:
        border_relais.open(alert_sound_text)
    else:
        border_relais.close()

    # sleeps and starts again
    if play_sound:
        try:
            playsound(TTS_FILE_PATH)
        except Exception as e:
            print('Error playing alert_sound:')
            print(e)
        time.sleep(20)
    else:
        time.sleep(30)
