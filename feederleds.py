import json
import inotify.adapters
import inotify.constants
import os.path
import sys
import threading
import time
import subprocess
import re
import RPi.GPIO as GPIO

LEFT_BLUE = 13
RIGHT_BLUE = 5
LEFT_RED = 6
RIGHT_RED = 27

PATH = '/home/pi/catfeeder/git/'

leftName = ""
rightName = ""
leftFeeder = { "error": False, "feeding": False }
rightFeeder = { "error": False, "feeding": False }
leftblue = None
rightblue = None
leftred = None
rightred = None

# 'Normal' flash the LED according to how long before the next feed
MIN_ON_CYCLE = 0.01
MAX_ON_CYCLE = 90
FULL_ON = 99.99
MIN_FLASH_FREQUENCY = 0.1
MAX_FLASH_FREQUENCY = 5
MAX_HOURS = 12

# Feeding and Error flash
ERROR_FREQUENCY = 1
ERROR_ON_CYCLE = 50

def main(argv):
    global leftName, rightName
    if len(argv) != 3:
      print("Usage: python3 feederleds.py <left name> <right name>")
      return
    # Program name
    argv.pop(0)
    leftName = argv.pop(0) + ".conf"
    rightName = argv.pop(0) + ".conf"

    global leftblue, rightblue, leftred, rightred
    #GPIO.setmode(GPIO.BOARD)
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(LEFT_BLUE, GPIO.OUT)
    leftblue = GPIO.PWM(LEFT_BLUE, MIN_FLASH_FREQUENCY)
    leftblue.start(MIN_ON_CYCLE)

    GPIO.setup(RIGHT_BLUE, GPIO.OUT)
    rightblue = GPIO.PWM(RIGHT_BLUE, MIN_FLASH_FREQUENCY)
    rightblue.start(MIN_ON_CYCLE)

    GPIO.setup(LEFT_RED, GPIO.OUT)
    leftred = GPIO.PWM(LEFT_RED, MIN_FLASH_FREQUENCY)
    leftred.start(0)

    GPIO.setup(RIGHT_RED, GPIO.OUT)
    rightred = GPIO.PWM(RIGHT_RED, MIN_FLASH_FREQUENCY)
    rightred.start(0)

    errorthread = threading.Thread(target=errorLEDs)
    errorthread.daemon = True
    errorthread.start()

    normalLEDs()

def errorLEDs():
    global leftName, rightName
    global leftFeeder, rightFeeder
    global leftblue, rightblue, leftred, rightred

    i = inotify.adapters.Inotify()
    i.add_watch(PATH + leftName, mask=inotify.constants.IN_MODIFY)
    i.add_watch(PATH + rightName, mask=inotify.constants.IN_MODIFY)

    for event in i.event_gen(yield_nones=False):
      (_, type_names, path, filename) = event
      print("event '" + path + "'")
      if path == PATH + leftName:
        leftFeeder = load(PATH, leftName)
        updateStatusLEDs(leftFeeder, leftred, leftblue)    
      elif path == PATH + rightName:
        rightFeeder = load(PATH, rightName)
        updateStatusLEDs(rightFeeder, rightred, rightblue)    
     
def load(path, name):
    n = path + name
    if not os.path.exists(n):
      return
    s = ""
    with open(n) as f:
      s = f.read()
    return json.loads(s)

def updateStatusLEDs(settings, red, blue):
    if settings["feeding"]:
      print("feeding")
      on = red if settings["error"] else blue
      flash = blue if settings["error"] else red
      on.ChangeFrequency(MIN_FLASH_FREQUENCY)
      on.ChangeDutyCycle(FULL_ON)
      flash.ChangeFrequency(ERROR_FREQUENCY)
      flash.ChangeDutyCycle(ERROR_ON_CYCLE)
    elif settings["error"]:
      print("error")
      blue.ChangeDutyCycle(0)
      red.ChangeFrequency(ERROR_FREQUENCY)
      red.ChangeDutyCycle(ERROR_ON_CYCLE)
    else:
      # Set both to off: normalLEDs() will override this
      blue.ChangeDutyCycle(0)
      red.ChangeDutyCycle(0)
      print("normal")

def normalLEDs():
    while True:
      text = subprocess.check_output("cat /etc/crontab | grep catfeeder", shell=True)
      text = str(text, encoding="utf-8")
      print("Subprocess returned:" + text)
      now = time.gmtime()
      now = now.tm_hour + (now.tm_min/60)
      minhours = None
      lines = text.splitlines()
      for line in lines:
        fields = re.split("\s", line)
        hours = int(fields[1]) + int(fields[0])/60
        hours -= now
        hours = hours if hours > 0.0 else hours + 24
        print("fields {0} {1} {2} {3}".format(fields[0], fields[1], hours, minhours))
        if minhours == None or minhours > hours:
            minhours = hours

      if minhours < 0.25:
        f = MIN_FLASH_FREQUENCY
        c = FULL_ON
      else:
        #f = (MAX_FLASH_FREQUENCY * (1 - (minhours/MAX_HOURS))) + (MIN_FLASH_FREQUENCY * (minhours/MAX_HOURS))
        f = MAX_FLASH_FREQUENCY / (2 * minhours)
        c = 75 - ((minhours/MAX_HOURS) * 75)
      c = (MAX_ON_CYCLE if c > MAX_ON_CYCLE else c) if c >= MIN_ON_CYCLE else MIN_ON_CYCLE
      f = (MAX_FLASH_FREQUENCY  if f > MAX_FLASH_FREQUENCY  else f) if f >= MIN_FLASH_FREQUENCY else MIN_FLASH_FREQUENCY
      #print("f {0} c {1}".format(f,c))
      if not leftFeeder["feeding"] and not leftFeeder["error"]:
        leftblue.ChangeFrequency(f)
        leftblue.ChangeDutyCycle(c)
      if not rightFeeder["feeding"] and not rightFeeder["error"]:
        rightblue.ChangeFrequency(f)
        rightblue.ChangeDutyCycle(c)
      time.sleep(60)
      
if __name__ == "__main__":
    main(sys.argv)