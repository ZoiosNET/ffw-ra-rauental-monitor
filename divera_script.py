#!/usr/bin/env python3

import subprocess
import datetime
import requests
#import serial
import time
import os

ACCESS_KEY = ""
TELEGRAM_CHAT_ID = ""

with open('settings.propperties', 'r') as config_file:
    config_lines = config_file.readlines()
    for config_line in config_lines:
        config_property = config_line.split('=')
        config_key = config_property[0]
        config_value = config_property[1]
        if config_key == 'api_key':
            ACCESS_KEY = config_value
        elif config_key == 'telegram_chat_id':
            TELEGRAM_CHAT_ID = config_value

BASE_URL = "https://www.divera247.com/api"
ALARM_URL = BASE_URL + "/v2/alarms?accesskey=" + ACCESS_KEY
APPOINTMENT_URL = BASE_URL + "/v2/events?accesskey=" + ACCESS_KEY
PRE_APPOINTMENT_TIME = 30 * 60  # First Number is the Time in Minutes to turn display on before an appointment
SUF_APPOINTMENT_TIME = 90 * 60  # First Number is the Time in Minutes to turn display off after an appointment
screen_active = False

#border_conn = serial.Serial(
#    port='/dev/ttyUSB0'
#)


class HdmiCec:

    def __init__(self, device_no):
        self.device_no = device_no
        self.last_command = ""
        os.system("echo 'scan' | cec-client -s -d 1")

    def on(self):
        print("DISPLAY ON")
        if self.last_command == "on":
            return
        self.last_command = "on"
        os.system("echo 'on " + self.device_no + "' | cec-client -s -d 1")
#        border_conn.write(b'\xA0\x01\x01\xA2')

    def standby(self):
        print("DISPLAY OFF")
        if self.last_command == "standby":
            return
        self.last_command = "standby"
        os.system("echo 'standby " + self.device_no + "' | cec-client -s -d 1")
#        border_conn.write(b'\xA0\x01\x00\xA1')


hdmi_cec = HdmiCec('0')

while True:

    alarm_active = True
    appointment_time = False

    # check current active alert
    response = requests.get(ALARM_URL)
    if response.status_code == 200:
        alert = response.json()
        if alert["success"]:
            alert_list = alert["data"]["items"]
            if len(alert_list) == 0:
                alarm_active = False

    # get current date
    now = datetime.datetime.now()
    day_of_week = now.weekday() + 1  # 1 = Monday
    hour = now.hour
    minutes = now.minute

    # check current active appointment
    response = requests.get(APPOINTMENT_URL)
    if response.status_code == 200:
        data = response.json()
        if data["success"]:
            for appointment_id in data["data"]["items"]:
                appointment = data["data"]["items"][appointment_id]
                start_time = datetime.datetime.fromtimestamp(appointment["start"] - PRE_APPOINTMENT_TIME)
                end_time = datetime.datetime.fromtimestamp(appointment["end"] + SUF_APPOINTMENT_TIME)
                if start_time < now < end_time:
                    appointment_time = True

    # case: active alert or appointment time
    if alarm_active is True or appointment_time is True:
        hdmi_cec.on()
        screen_active = True

    # case: no active alert and no appointment time
    elif alarm_active is False and appointment_time is False:
        hdmi_cec.standby()
        screen_active = False

    # case: monitor off an no mission and it is night time so make updates
    elif alarm_active is False and screen_active is False and hour == 3 and minutes == 5:
        # wait a moment that he wont do two updates when he is faster then a minute with update and reboot
        time.sleep(60)
        subprocess.Popen(['sudo', 'apt', 'update']).wait()
        subprocess.Popen(['sudo', 'apt', '--yes', '--force-yes', 'upgrade']).wait()
        subprocess.Popen(['sudo', 'reboot'])

    # sleeps 30 seconds and starts again
    time.sleep(30)
