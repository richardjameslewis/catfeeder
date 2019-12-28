import sys
import time
import subprocess
import re
import RPi.GPIO as GPIO

LED_PIN = 33
LED_ON = 1
LED_OFF = 0
MIN_ON_CYCLE = 0.01
MAX_ON_CYCLE = 90
MIN_FLASH_FREQUENCY = 0.1
MAX_FLASH_FREQUENCY = 5
MAX_HOURS = 12

def main(argv):
    GPIO.setmode(GPIO.BOARD)
    #GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(LED_PIN, GPIO.OUT)
    #GPIO.output(LED_PIN, 0)
    led = GPIO.PWM(LED_PIN, MIN_FLASH_FREQUENCY)
    led.start(MIN_ON_CYCLE)

    while True:
      text = subprocess.check_output("cat /etc/crontab | grep catfeeder", shell=True)
      text = str(text, encoding="utf-8")
      print("Subprocess returned:" + text);
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
        #GPIO.output(LED_PIN, LED_ON)
        f = MIN_FLASH_FREQUENCY
        #c = MIN_ON_CYCLE        # Equivalent to fully on
        #c = MAX_ON_CYCLE
        c = 99.99
      else:
        #f = (MAX_FLASH_FREQUENCY * (1 - (minhours/MAX_HOURS))) + (MIN_FLASH_FREQUENCY * (minhours/MAX_HOURS))
        f = MAX_FLASH_FREQUENCY / (2 * minhours)
        c = 75 - ((minhours/MAX_HOURS) * 75)
      c = (MAX_ON_CYCLE if c > MAX_ON_CYCLE else c) if c >= MIN_ON_CYCLE else MIN_ON_CYCLE
      f = (MAX_FLASH_FREQUENCY  if f > MAX_FLASH_FREQUENCY  else f) if f >= MIN_FLASH_FREQUENCY else MIN_FLASH_FREQUENCY
      print("f {0} c {1}".format(f,c))
      led.ChangeFrequency(f)
      led.ChangeDutyCycle(c)
      time.sleep(60)


if __name__ == "__main__":
    main(sys.argv)