"""
    Project: Measure Temperature and Humidity and publish on a MQTT channel
    File: main.py
    Author: Georg Edelmann
    Version: 1.4
    Date: Sep 27, 2025
    Description: Main code
    Release Notes:
      1.1: added watchdog timer
      1.2: added uptime 
      1.3: now using InfluxDB 2 and Telegraf
      1.4: using the watchdog timer to check connection to MQTT broker. Hardening WiFi connecting after signal loss.

"""

import config
import network
import socket
import time
from umqtt.robust import MQTTClient
from machine import Pin, I2C, WDT
import dht20
import json
import sys

# For uptime 
boot_time = time.time()  

# Onboard temperature
adcpin = 4
sensor = machine.ADC(adcpin)

# Logging
def log(level, msg):

    if config.LOG_LEVEL >= level:
        print(f"DEBUG({level}) {CalcUptime(time.time())}. {msg}")


# Calculate uptime, and return uptime string with days, hours, minutes, and seconds
def CalcUptime(t):  
    timeDiff = t-boot_time  
    (minutes, seconds) = divmod(timeDiff, 60)  
    (hours, minutes) = divmod(minutes, 60)  
    (days,hours) = divmod(hours, 24)
    return(str(days)+":"+f"{hours:02d}"+":"+f"{minutes:02d}"+":"+f"{seconds:02d}") 

# Read temp and return in Celsius
def ReadTemperature():
    adc_value = sensor.read_u16()
    volt = (3.3/65535) * adc_value
    temperature = 27 - (volt - 0.706)/0.001721
    return round(temperature, 1)


def watchdog_task():

    log(3, f"In watchdog_task().")

    # we're checking if the connecttion to the MQTT server is still operational
    try:
        # Use the socket module to perform the ping
        addr = socket.getaddrinfo(config.MQTT_BROKER, config.MQTT_PORT)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(addr)
        s.close()

        log(3, f"In watchdog_task(). Connection to MQTT broker at {config.MQTT_BROKER} successful.")
        wdt.feed()
        log(3, f"In watchdog_task(). Feeding WDT.")

    except OSError as e:
    
        log(3, f"In watchdog_task(). Connection to MQTT broker at {config.MQTT_BROKER} failed.")


# we're underclocking to save power
cur_frequency=machine.freq()
new_frequency=12000000*6 
machine.freq(new_frequency)

print("-" * 80)
print(f"------  Welcome to the Raspberry Pico W based solar controller            ------")
print(f"------  Device name: {config.MQTT_CLIENT_ID:<10}   Version: {config.VERSION:<4}                           ------")
print("-" * 80)

print(f"Setting processor frequency from {cur_frequency/1000000} MHz to {new_frequency/1000000} MHz")

# Wifi details
wifi_ssid = config.WIFI_SSID
wifi_password = config.WIFI_PASSWORD

# Connect to WiFi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

for _ in range(10):
    
    wlan.connect(wifi_ssid, wifi_password)
    time.sleep(1)

    if wlan.isconnected():
        print(f'Connected to Wifi. Status: {wlan.status()}')
        break

    print(f'Waiting for Wifi connection. Status: {wlan.status()}...')
    time.sleep(11)

ip_address = wlan.ifconfig()[0]
mac_address=wlan.config('mac').hex()

print(f"Connected to WiFi. IP address: {ip_address}. MAC address: {mac_address}")

mqtt_host = config.MQTT_BROKER
mqtt_port = config.MQTT_PORT
mqtt_username = config.MQTT_USER
mqtt_password = config.MQTT_PASSWD
mqtt_publish_topic = config.MQTT_PUBLISH_TOPIC    # The MQTT topic

# watchdog timer
wdt = WDT(timeout=5000)  # enable timer for 5 sec intervals

# Enter a ID for this MQTT Client.
mqtt_client_id = config.MQTT_CLIENT_ID

# Initialize our MQTTClient and connect to the MQTT server
mqtt_client = MQTTClient(
        client_id=mqtt_client_id,
        server=mqtt_host,
        port=mqtt_port,
        user=mqtt_username,
        password=mqtt_password)

try:
        mqtt_client.connect()
        print(f"Connected to MQTT broker {config.MQTT_BROKER}")
except:
        print(f"Connection to MQTT broker {config.MQTT_BROKER} failed. Resetting")
        machine.reset()

i2c0_sda = Pin(0)
i2c0_scl = Pin(1)
i2c0 = I2C(0, sda=i2c0_sda, scl=i2c0_scl)

if(config.SENSOR_IN_USE):
    dht20 = dht20.DHT20(0x38, i2c0)

# Publish MQTT message
def mqtt_publish(topic, category, message):

    try:
        m = f"{category},deviceId={config.MQTT_CLIENT_ID},deviceType={config.DEVICE_TYPE},deviceVersion={config.VERSION} {message}"
        log(3, f"In mqtt_pushlish(). Message: {m}.")

        mqtt_client.publish(config.MQTT_PUBLISH_TOPIC, m)

    except Exception as e:
        log(1, f"In mqtt_pushlish(). Exception: {e}")
        log(1, f"Rebooting.")
        sys.exit()

# Calculate uptime, and return uptime string with days, hours, minutes, and seconds
def CalcUptime(t):  
    timeDiff = t-boot_time  
    (minutes, seconds) = divmod(timeDiff, 60)  
    (hours, minutes) = divmod(minutes, 60)  
    (days,hours) = divmod(hours, 24)
    return(str(days)+":"+f"{hours:02d}"+":"+f"{minutes:02d}"+":"+f"{seconds:02d}") 

# Publish a data point to the MQTT server every config.PUBLISH_INTERVAL seconds
try:
    while True:

        print(f"{'-' * 80}")

        if(config.SENSOR_IN_USE):
            measurements = dht20.measurements
            log(3, f"In main loop. We're using a sensor.")
        else:
            log(3, f"In main loop. We're simulating a sensor.")
            measurements = {
                 "t" : 21.0,
                "rh" : 50.0
            }
       
        uptime = CalcUptime(time.time())

        s = '{"Version":' + str(config.VERSION) + ', "Uptime":"' + uptime + '","Temperature":"' + str(ReadTemperature()) + '" }'

        telemetry_message = f"uptime=\"{uptime}\",internal_temperature={str(ReadTemperature())},MAC_address=\"{mac_address}\",IP_address=\"{ip_address}\""

        log(3, f"In main loop. Telemetry message: {telemetry_message}")

        mqtt_publish(mqtt_publish_topic, "telemetry", f"{telemetry_message}")

        temp_C = measurements['t']       # we measure and report in Celsius
        temp_F = (temp_C * 9/5) + 32
        humidity = measurements['rh']

        log(1, f"In main loop. Temperature: {temp_C} degC, humidity: {measurements['rh']} %RH")

        mqtt_publish(mqtt_publish_topic, "measurement", f'temperature={temp_C:.1f},humidity={humidity:.1f}')
        
        interval = 0

        print(f'Waiting for next interval, while feeding the watchdog timer: 0', end="")
                        
        while interval < config.PUBLISH_INTERVAL:
            time.sleep(1)
            watchdog_task()
            interval = interval + 1

            if (interval % 5):
                print(f'.', end="")
            else:
                print(f'{interval}', end="")

        print('\n')

except Exception as e:
    print(f'Failure in main loop: {e}')
finally:
    mqtt_client.disconnect()
    machine.reset()
