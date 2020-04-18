import faulthandler
import sys
import threading
import time
import RPi.GPIO as GPIO
from enum import Enum
from feeder import Feeder
from feedercollection import FeederCollection

# Constants
PWM_FREQUENCY = 50
# BCM numbers for outputs (BOARD numbers in comment)
# Nala left
LEFT_RESET_PIN = 12   # 32
LEFT_PWM_PIN = 19     # 35
LEFT_ADC_CHAN = 0     # 1

# Rosie right
RIGHT_RESET_PIN = 24  # 18
RIGHT_PWM_PIN = 18    # 12
RIGHT_ADC_CHAN = 1    # 2

# Our servos behave slightly differently, normalize this here
LEFT_CLOCK_PWM = 5
LEFT_ANTI_PWM = 9
RIGHT_CLOCK_PWM = 5
RIGHT_ANTI_PWM = 10

faulthandler.enable()
feeder = None
# 0,1,2
verbose = 0

def main(argv):
  global feeder, verbose
  print("Cat Feeder 0.3")
  
  # pop program name
  argv.pop(0)
  op = None
  weight = 0
  resetcalibration = False

  while len(argv) > 0:
    argc = len(argv)
    if argc >= 1 and argv[0] == "--help":
      help()
      return
    elif argc >= 1 and argv[0] == "-v":
      verbose += 1
    elif argc >= 2 and argv[0] == "--left":
      feeder = Feeder(argv[1], LEFT_PWM_PIN, LEFT_RESET_PIN, LEFT_ADC_CHAN, 
                      LEFT_CLOCK_PWM, LEFT_ANTI_PWM, verbose)
      argv.pop(0)
    elif argc >= 2 and argv[0] == "--right":
      feeder = Feeder(argv[1], RIGHT_PWM_PIN, RIGHT_RESET_PIN, RIGHT_ADC_CHAN, 
                      RIGHT_CLOCK_PWM, RIGHT_ANTI_PWM, verbose)
      argv.pop(0)
    elif argc >= 1 and argv[0] == "--info":
      op = argv[0]
    elif argc >= 1 and argv[0] == "--reset":
      op = argv[0]
    elif argc >= 1 and argv[0] == "--resetcal":
      resetcalibration = True
    elif argc >= 1 and argv[0] == "--cal":
      op = argv[0]
    elif argc >= 2 and argv[0] == "--feed":
      weight = float(argv[1])
      op = argv[0]
      argv.pop(0)
    else:
      help()
      return
    argv.pop(0)

  if feeder == None:
      help()
      return
  init()
  if op == "--info":
    feeder.info()
  elif op == "--reset":
    feeder.resetSettings()
    feeder.save()
  elif op == "--cal":
    cal2(feeder, resetcalibration)
  elif op == "--feed":
    feed(weight)
  else:
    help()
  # Wait for threads to really end
  feeder = None
  time.sleep(5)

  GPIO.cleanup()
  return

def help():
  print("--help          Print this message.")
  print("--left <name>   Use the left hand feeder for cat <name>.")
  print("--right <name>  Use the right hand feeder for cat <name>.")
  print("--reset         Reset feeder history. Sets excess and average to 0.")
  print("--info          Print feeder info.")
  print("--cal           Calibrate the cat feeder, needs >200g of food loaded into feeder.")
  print("--resetcal      Reset the calibration before starting measurement.")
  print("--feed <N>      Feed <N> grams of food.")
  print("-v              More detail.")
  print("-v -v           Even More detail.")

def init():
  #GPIO.setmode(GPIO.BOARD)
  GPIO.setmode(GPIO.BCM)
  GPIO.setwarnings(True)

def feed(weight):
  feeder.initFeed(weight)
  feeder.startFeed()
  feeder.join()
  if feeder.empty:
    print("Warning: {0}'s feeder is empty".format(feeder.name))
  feeder.info()

sums = 0
calibrating = True

def cal2(f, resetcalibration):
  global sums, calibrating
  sums = 0
  calibrating = True
  f.resetSettings()
  if resetcalibration:
    f.resetCalibration()
  f.calms = 0
  cal = threading.Thread(target=calThread)
  cal.daemon = True
  cal.start()
  input("Press return when around 200g has been dispensed")
  calibrating = False
  f.stop()
  cal.join()
  done = False
  while not done:
    text = input("Exact amount dispensed in grammes")
    try:
      amount = float(text)
      done = True
    except:
      pass
  f.calibrate(amount, sums)
  f.calms = f.ms
  f.resetSettings()
  f.save()

def calThread():
  global sums, calibrating
  f = feeder
  print("Cal thread for {0}".format(f.name))
  sums = 0
  # feed in 25g chunks
  while not f.empty and calibrating:
    f.initFeed(25.0)
    f.startFeed()
    f.join()
    sums += f.sums
    print("{0} {1}".format(sums, f.sums))

if __name__ == "__main__":
    main(sys.argv)