import sys
import time
import subprocess
import re
import RPi.GPIO as GPIO
#import gpiozero

TEST_PIN = 32

def main(argv):
    GPIO.setmode(GPIO.BOARD)
    #GPIO.setmode(GPIO.BCM)
    #GPIO.setwarnings(False)
    GPIO.setup(TEST_PIN, GPIO.OUT, initial=GPIO.HIGH)
    #GPIO.output(LED_PIN, 0)
    #led = GPIO.PWM(LED_PIN, MIN_FLASH_FREQUENCY)
    #led.start(MIN_ON_CYCLE)

    while True:
      time.sleep(0.01)
      GPIO.output(TEST_PIN, GPIO.LOW)
      time.sleep(0.0005)
      GPIO.output(TEST_PIN, GPIO.HIGH)


main("")
