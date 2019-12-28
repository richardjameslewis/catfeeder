import sys
import time
import RPi.GPIO as GPIO
from enum import Enum

# Constants
PWM_FREQUENCY = 50
# BOARD numbers for outputs
NALA_PWM_PIN = 35
ROSIE_PWM_PIN = 12
NALA_TIME = 1.2      # 1.2
#ROSIE_TIME = 1.55     # 1.5
ROSIE_TIME = 1.0     # 1.5
FLIP_LEFT = (2.0/20.0) * 100
FLIP_RIGHT = (1.0/20.0) * 100
LEFT_FLIP_TIME = 0.35
RIGHT_FLIP_TIME = 0.3
FLIP_DELAY = 1
WIGGLE_LEFT = (2.0/20.0) * 100
WIGGLE_RIGHT = (1.0/20.0) * 100
WIGGLE_COUNT = 2
WIGGLE_TIME = 0.3

# Vegetables...sorry, variables
nala = None
rosie = None

def main(argv):
  print("Cat Feeder 0.2")
  argc = len(argv)

  if argc != 2 or argv[1] == "--help":
    help()
  elif argv[1] == "--init":
    init()
  elif argv[1] == "--left":
    init()
    feed(MotorState.LEFT)
  elif argv[1] == "--right":
    init()
    feed(MotorState.RIGHT)
  else:
    help()

  # Don't call GPIO.cleanup, leave pins setup
  #GPIO.cleanup()
  return

def help():
  print("--init - Initialize the GPIO pins for the cat feeder")
  print("--left - Feed the cats. Start turning left.")
  print("--right - Feed the cats. Start turning right.")
  print("--help - Print this message")

class Stage(Enum):
    WIGGLE1 = 0
    PAUSE1 = 1
    FLIP1 = 2
    PAUSE2 = 3
    WIGGLE2 = 4
    PAUSE3 = 5
    FLIP2 = 6
    PAUSE4 = 7
    COMPLETE = 8
    START = 9


class MotorState(Enum):
    LEFT = 0
    LEFTWAIT = 1
    RIGHT = 2
    RIGHTWAIT = 3
    COMPLETE = 4
    START = 5
    RIGHTWIGGLE = 6
    LEFTWIGGLE = 7

stateparams = {
    MotorState.LEFT:      { "cycle": FLIP_LEFT, "duration": LEFT_FLIP_TIME},
    MotorState.LEFTWAIT:  { "cycle": 0, "duration": FLIP_DELAY },
    MotorState.RIGHT:     { "cycle": FLIP_RIGHT, "duration": RIGHT_FLIP_TIME },
    MotorState.RIGHTWAIT: { "cycle": 0, "duration": FLIP_DELAY },
    MotorState.COMPLETE:  { "cycle": 0, "duration": 0 },
    MotorState.START:     { "cycle": 0, "duration": 0 },
    MotorState.LEFTWIGGLE: { "cycle": WIGGLE_LEFT, "duration": WIGGLE_TIME },
    MotorState.RIGHTWIGGLE: { "cycle": WIGGLE_RIGHT, "duration": WIGGLE_TIME },
}

def init():
  global nala, rosie, startstate

  GPIO.setmode(GPIO.BOARD)
  GPIO.setwarnings(False)
  startstate = None
  nala = HungryCat(NALA_PWM_PIN, NALA_TIME, FLIP_LEFT, FLIP_RIGHT)
  rosie = HungryCat(ROSIE_PWM_PIN, ROSIE_TIME, FLIP_LEFT, FLIP_RIGHT)

def feed(state):
  global startstate
  startstate = state

  nala.startFeed()
  rosie.startFeed()
  while True:
    n = nala.feed()
    r = rosie.feed()
    if n == 0 and r == 0:
      break
    elif n == 0:
      time.sleep(r)
    elif r == 0:
      time.sleep(n)
    else:
      time.sleep(min(n, r))

class HungryCat:
  def __init__(self, pin, total_time, left, right):
    self.PIN = pin
    self.TOTAL_TIME = total_time
    self.LEFT_CYCLE = left
    self.RIGHT_CYCLE = right
    self.motorstate = MotorState.LEFT
    self.next_time = 0
    self.time_left = 0
    self.count = 0

    GPIO.setup(self.PIN, GPIO.OUT)
    self.pwm = GPIO.PWM(self.PIN, PWM_FREQUENCY)
    self.pwm.start(0)

  def startFeed(self):
    self.motorstate = MotorState.START

  def done(self):
    if self.time_left == 0:
      return True
    if self.motorstate == MotorState.LEFT or self.motorstate == MotorState.RIGHT:
      t = time.time()
      return self.time_left <= (t - self.last_time)
    return False

  def feed(self):


    return self.doMotor()

  def doMotor(self):
    if self.motorstate == MotorState.COMPLETE:
        return 0

    t = time.time()
    print("feed {0}".format(t));

    if self.motorstate != MotorState.START and self.done():
      print("{0} Complete".format(self.PIN))
      self.motorstate = MotorState.COMPLETE
      self.pwm.ChangeDutyCycle(0)
      return 0

    if t >= self.next_time or self.motorstate == MotorState.START:
      adjustTime = False
      if self.motorstate == MotorState.START:
        #self.motorstate = startstate
        #self.time_left = self.TOTAL_TIME
        self.motorstate = MotorState.LEFTWIGGLE
        self.wiggle_count = WIGGLE_COUNT
        self.time_left = self.TOTAL_TIME + WIGGLE_TIME * WIGGLE_COUNT * 2
        print("Start {0}".format(self.motorstate))
      elif self.motorstate == MotorState.LEFTWIGGLE:
        self.motorstate = MotorState.RIGHTWIGGLE
        adjustTime = True
      elif self.motorstate == MotorState.RIGHTWIGGLE:
        self.wiggle_count = self.wiggle_count - 1
        self.motorstate = startstate if self.wiggle_count == 0 else MotorState.LEFTWIGGLE
        adjustTime = True
      elif self.motorstate == MotorState.LEFT:
        self.motorstate = MotorState.LEFTWAIT
        adjustTime = True
      elif self.motorstate == MotorState.LEFTWAIT:
        #self.motorstate = MotorState.RIGHT
        self.motorstate = MotorState.LEFT
      elif self.motorstate == MotorState.RIGHT:
        self.motorstate = MotorState.RIGHTWAIT
        adjustTime = True
      else:              # RIGHTWAIT
        #self.motorstate = MotorState.LEFT
        self.motorstate = MotorState.RIGHT

      if adjustTime:
        self.time_left -= t - self.last_time
        if self.time_left < 0:
           self.time_left = 0

      #print("MotorState {0}".format(self.motorstate))
      #print("Params {0}".format(stateparams))
      #print("Param {0}".format(stateparams[self.motorstate]))
      #print("Cycle {0}".format(stateparams[self.motorstate]["cycle"]))

      cycle = stateparams[self.motorstate]["cycle"]
      delta = stateparams[self.motorstate]["duration"]
      print("{0} MotorState change to {1} cycle {2}".format(self.PIN, self.motorstate, cycle))
      self.pwm.ChangeDutyCycle(cycle)
      self.last_time = t
      self.next_time = t + delta

    ret = min(self.time_left, self.next_time - t)
    print("{0} returning {1}".format(self.PIN, ret))
    return ret

if __name__ == "__main__":
    main(sys.argv)