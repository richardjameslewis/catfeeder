import sys
import threading
import time
import RPi.GPIO as GPIO
from enum import Enum
from feeder import Feeder
from feedercollection import FeederCollection

# Constants
PWM_FREQUENCY = 50
# BOARD numbers for outputs
# Nala left
LEFT_RESET_PIN = 12   # 32
LEFT_DATA_PIN = 16    # 36
LEFT_PWM_PIN = 19     # 35
LEFT_ADC_CHAN = 0

# Rosie right
RIGHT_RESET_PIN = 24  # 18
RIGHT_DATA_PIN = 25   # 22
RIGHT_PWM_PIN = 18    # 12
RIGHT_ADC_CHAN = 1

feeders = FeederCollection()
#feeders.append(Feeder("Nala", LEFT_PWM_PIN, LEFT_RESET_PIN, LEFT_DATA_PIN, LEFT_ADC_CHAN))
#feeders.append(Feeder("Rosie", RIGHT_PWM_PIN, RIGHT_RESET_PIN, RIGHT_DATA_PIN, RIGHT_ADC_CHAN))

nala = None
rosie = None

def main(argv):
  print("Cat Feeder 0.3")
  argc = len(argv)

  if argc == 2 and argv[1] == "--help":
    help()
  elif argc == 2 and argv[1] == "--init":
    init()
  elif argc == 2 and argv[1] == "--info":
    init()
    nala.info()
  elif argc == 2 and argv[1] == "--reset":
    init()
    reset()
  elif argc == 2 and argv[1] == "--cal":
    init()
    cal2()
  elif argc == 3 and argv[1] == "--feed":
    init()
    feed(float(argv[2]))
  #elif argv[1] == "--left":
  #  init()
  #  feed(False)
  #elif argv[1] == "--right":
  #  init()
  #  feed(True)
  else:
    help()

  # Don't call GPIO.cleanup, leave pins setup
  #GPIO.cleanup()
  return

def help():
  print("--init - Initialize the GPIO pins for the cat feeder")
  print("--reset - Reset feeder histrory. Sets excess and average to 0.")
  print("--cal - Calibrate the cat feeder, needs 250g of food loaded into feeder.")
  print("--feed N - Feed N grams of food")
  #print("--left - Feed the cats. Start turning left.")
  #print("--right - Feed the cats. Start turning right.")
  print("--help - Print this message")

def init():
  global nala, rosie, startstate

  #GPIO.setmode(GPIO.BOARD)
  GPIO.setmode(GPIO.BCM)
  GPIO.setwarnings(False)
  startstate = None
  # nala = Feeder("nala", 25, 6.2, LEFT_PWM_PIN, LEFT_RESET_PIN, LEFT_DATA_PIN, LEFT_ADC_CHAN)
  nala = Feeder("nala", LEFT_PWM_PIN, LEFT_RESET_PIN, LEFT_DATA_PIN, LEFT_ADC_CHAN)
  #rosie = Feeder(RIGHT_PWM_PIN)

def feed(weight):
  nala.startFeed(weight)
  #rosie.startFeed(100)
  nala.join()
  #rosie.join()
  if nala.empty:
    print("Warning: Nala's feeder is empty")
  nala.info()

def cal():
  sums = 0
  # remove any excess
  nala.resetSettings()
  # feed in big chunks (possibly a mistake)
  nala.resetCalibration()
  while not nala.empty:
    nala.startFeed(25.0)
    nala.join()
    sums += nala.sums
    #time.sleep(5)
  nala.calibrate(250.0, sums)
  nala.resetSettings()
  nala.save()


sums = 0
calibrating = True

def cal2():
  global sums, calibrating
  sums = 0
  calibrating = True
  cal = threading.Thread(target=calThread)
  cal.daemon = True
  cal.start()
  input("Press return when around 250g has been dispensed")
  calibrating = False
  nala.stop()
  cal.join()
  done = False
  while not done:
    text = input("Exact amount dispensed in grammes")
    try:
      amount = float(text)
      done = True
    except:
      pass
  nala.calibrate(amount, sums)
  nala.resetSettings()
  nala.save()

def calThread():
  global sums, calibrating
  sums = 0
  nala.resetSettings()
  # feed in big chunks (possibly a mistake)
  nala.resetCalibration()
  while not nala.empty and calibrating:
    nala.startFeed(25.0)
    nala.join()
    sums += nala.sums
    print("{0} {1}".format(sums, nala.sums))
    #time.sleep(5)

def reset():
  nala.resetSettings()
  nala.save()

def info():
  nala.info()
  
if __name__ == "__main__":
    main(sys.argv)