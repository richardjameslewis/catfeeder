import json
import math
import os.path
import sys
import threading
import time
import RPi.GPIO as GPIO
from gpiozero import MCP3008
from enum import Enum

# Constants
PWM_FREQUENCY = 50

FLIPS = 6
ANTI_FLIP_MAX = 0.88
ANTI_FLIP_TIME = 0.33
CLOCK_FLIP_MAX = 0.8
CLOCK_FLIP_TIME = 0.3

WIGGLES = 6
ANTI_WIGGLE_TIME = 0.3 # 0.36
CLOCK_WIGGLE_TIME = 0.3

FED_TIMEOUT_SECS = 10
EMPTY_TIME = 1.5

LOW_POWER_SECS = 30
HIGH_POWER_SECS = 90
EMPTY_TEST_SECS = 180
JIGGLE_INTERVAL = 15

DEBUG_PIN = 6     # 31

GPIO.setup(DEBUG_PIN, GPIO.OUT)
GPIO.output(DEBUG_PIN, False)

class MotorState(Enum):
  START = 0
  LEFTWIGGLE = 1
  RIGHTWIGGLE = 2
  LEFT = 3
  RIGHT = 4
  LEFTEMPTY = 5
  RIGHTEMPTY = 6
  COMPLETE = 7

class Feeder:
  def __init__(self, name, pwmpin, resetpin, adcchannel, clockwise, anticlockwise, verbose):
    self.name = name

    self.empty = False
    self.running = False

    self.resetSettings()
    self.resetCalibration()

    self.resetpin = resetpin
    GPIO.setup(self.resetpin, GPIO.OUT)
    # Keep high to reduce current, power
    GPIO.output(self.resetpin, True)

    self.pwmpin = pwmpin
    GPIO.setup(pwmpin, GPIO.OUT)
    self.pwm = GPIO.PWM(pwmpin, PWM_FREQUENCY)
    self.pwm.start(0)
    self.motorstate = MotorState.START
    self.motorstatecounter = 0

    self.adcchannel = adcchannel
    self.adc = MCP3008(channel=adcchannel, device=0)
    self.adcevent = threading.Event()
    self.motorevent = threading.Event()

    self.clockwise = clockwise
    self.anticlockwise = anticlockwise

    self.verbose = verbose

    self.load()

  def setupStates(self):
    self.states = {
        MotorState.START:       { "pwm": 0, "duration":  0, "repeat": 0, "right": True, "fn": self.stateStart },
        MotorState.LEFTWIGGLE:  { "pwm": self.anticlockwise, "duration":  ANTI_WIGGLE_TIME, "repeat": WIGGLES, "right": False, "fn": self.stateWiggle  },
        MotorState.RIGHTWIGGLE: { "pwm": self.clockwise, "duration":  CLOCK_WIGGLE_TIME, "repeat": WIGGLES, "right": True, "fn": self.stateWiggle },
        MotorState.LEFT:        { "pwm": self.anticlockwise, "duration":  ANTI_FLIP_TIME, "repeat": FLIPS, "right": False, "fn": self.stateFlip },
        MotorState.RIGHT:       { "pwm": self.clockwise, "duration":  CLOCK_FLIP_TIME, "repeat": FLIPS, "right": True, "fn": self.stateFlip},
        MotorState.LEFTEMPTY:   { "pwm": self.anticlockwise, "duration":  EMPTY_TIME, "repeat": 0, "right": False, "fn": self.stateEmpty   },
        MotorState.RIGHTEMPTY:  { "pwm": self.clockwise, "duration":  EMPTY_TIME, "repeat": 0, "right": True, "fn": self.stateEmpty },
        MotorState.COMPLETE:    { "pwm": 0, "duration":  0, "repeat": 0, "fn": None }
    }

  def initFeed(self, weight):
    self.running = True
    self.lastempty = self.lasttime = time.time()
    self.setupStates()
    self.sums = 0
    self.counts = 0
    self.total = 0
    self.ms = 0
    self.right = not self.right
    self.motor = None
    self.motorstate = MotorState.START
    self.weight = weight
    self.feeding = False
    self.error = False

    excess = self.excess
    # Limit the excess each time to half a meal either way
    # We should eventually catch up
    excess = max(min(excess, weight/2), -weight/2)
    self.target = self.targetFromWeight(weight - excess)
    if self.verbose > 0:
      print("Current target {0:.2f} which is {1:.2f}g total excess {2:.2f}".format(self.target, weight - excess, self.excess))
    self.motorevent.clear()

    self.adcthread = threading.Thread(target=self.adcThread)
    #self.adcthread.daemon = True
    self.adcthread.start()

    self.measure = threading.Thread(target=self.measureThread)
    self.measure.start()
    time.sleep(5)
    self.meansquared()

    self.motor = threading.Thread(target=self.motorThread)
    #self.motor.daemon = True

    if self.verbose:
      print("Init feed done {0}".format(self.name))

  def startFeed(self):
    self.motor.start()

  def join(self):
    self.measure.join()
    self.motor.join()
    self.adcthread.join()

  def stop(self):
    self.motorevent.set()
    self.lasttime = time.time()     # ???
    if self.verbose > 0:
      print("stop(): self.motorevent.set()")

  def meansquared(self):
    self.ms = self.sums / self.counts
    self.sums = 0
    self.counts = 0
    # Ensure calms cannot be 0 before divide
    if not self.calms:
      self.calms = self.ms
    if self.verbose:
      print("Mean squared {0:.2e} cal {1:.2e} ratio {2:.2e}".format(self.ms, self.calms, self.ms / self.calms))
    return self.ms

  def measureThread(self):
    if self.verbose:
      print("measureThread {0} {1}".format(self.resetpin, self.adcchannel))
    while self.running:
      if self.running:
        GPIO.output(self.resetpin, False)
        time.sleep(0.0005)
      GPIO.output(self.resetpin, True)
      time.sleep(0.0095 - 0.0005)

      self.adcevent.set()
      time.sleep(0.0005)

      # Don't check the event if the motor isn't running
      if self.motor != None and not self.motorevent.is_set() and self.sums >= self.target:
        self.motorevent.set()
        self.lasttime = time.time()     # ???
        if self.verbose > 0:
          print("measureThread() 1: self.motorevent.set()")
      
      if self.running:
        # Cope with timeout
        self.running = not (self.motorevent.is_set() and (time.time() - self.lasttime) > FED_TIMEOUT_SECS)
        if not self.running:
          #print("sumb {0} suma {1} sums {2} total {3} counts {4}".format(self.sumb, self.suma, self.sums, self.total, self.counts))
          self.motorevent.set()
          self.adcevent.set()
          if self.verbose > 0:
            print("measureThread() 2: self.motorevent.set()")
    
    # Keep high to reduce current, power
    GPIO.output(self.resetpin, True)

    self.dispensed = self.weightFromTarget(self.sums)
    self.excess = self.dispensed - (self.weight - self.excess)
    self.avg = self.dispensed if self.avg == 0 else (self.avg * 0.8) + (self.dispensed * 0.2)
    #print("right {0} dispensed {1} excess {2} avg {3}".format(self.right, self.dispensed, self.excess, self.avg))
    self.save()

    if self.verbose:
      print("measureThread ends {0}".format(self.running))
      #print("sumb {0} suma {1} sums {2} total {3} counts {4}".format(self.sumb, self.suma, self.sums, self.total, self.counts))

  def adcThread(self):
    if self.verbose:
      print("adcThread reset {0} adc {1}".format(self.resetpin, self.adcchannel))
    while self.running:
      self.adcevent.wait()
      self.adcevent.clear()
      GPIO.output(DEBUG_PIN, True)

      a = self.adc.value
      a2 = a * a
      #if a2 > self.ms:
      #  # Square Analogue
      #  self.sums += a2 - self.ms
      #  self.counts += 1
      # Count all datapoints minus mean squared noise
      self.sums += a2 - self.ms
      self.counts += 1
      if a > 0.5:
        self.lastempty = self.lasttime = time.time()
        self.states[MotorState.LEFT]["duration"] = ANTI_FLIP_TIME
        self.states[MotorState.RIGHT]["duration"] = CLOCK_FLIP_TIME
      self.total += 1
      GPIO.output(DEBUG_PIN, False)
    if self.verbose:
      print("adcThread ends")

  def motorThread(self):
    if self.verbose:
      print("motorThread {0}".format(self.pwmpin))

    self.feeding = True
    self.save()
    while not self.motorevent.is_set():
      state = self.states[self.motorstate]
      state["fn"](state)
      state = self.states[self.motorstate]
      if self.verbose > 1:
        print("{0} {1} {2} {3}".format(self.motorstate, state["pwm"], state["duration"], self.motorstatecounter))
      self.pwm.ChangeDutyCycle(state["pwm"])
      self.motorevent.wait(state["duration"])

    self.feeding = False
    # Whatever state we end in set pwm to 0
    self.pwm.ChangeDutyCycle(0)

  def stateStart(self, state):
    self.motorstate = MotorState.RIGHTWIGGLE if self.right else  MotorState.LEFTWIGGLE
    self.motorstatecounter = self.states[self.motorstate]["repeat"]

  def stateWiggle(self, state):
    if self.checkCounter():
      self.motorstate = MotorState.LEFT if state["right"] else MotorState.RIGHT
      self.motorstatecounter = self.states[self.motorstate]["repeat"]
    else:
      self.motorstate = MotorState.LEFTWIGGLE if state["right"] else MotorState.RIGHTWIGGLE

  def stateFlip(self, state):
    if self.checkEmpty(state):
      return
    if self.checkCounter():
      self.motorstate = MotorState.LEFTWIGGLE if state["right"] else MotorState.RIGHTWIGGLE
      self.motorstatecounter = self.states[self.motorstate]["repeat"]
    else:
      self.motorstate = MotorState.LEFT if state["right"] else MotorState.RIGHT

  def stateEmpty(self, state):
    # Guard just in case event has been set asynchronously
    if not self.motorevent.set():
      self.lasttime = time.time()     # ???
      self.motorevent.set()
      self.empty = True
      self.error = True
      if self.verbose > 0:
        print("stateEmpty(): self.motorevent.set()")
    self.motorstate = MotorState.COMPLETE

  def checkCounter(self):
    if self.motorstatecounter > 1:
      self.motorstatecounter -= 1
      return False
    else:
      return True

  def checkEmpty(self, state):
    dt = time.time() - self.lastempty
    if dt > EMPTY_TEST_SECS:
      self.motorstate = MotorState.LEFTEMPTY if self.motorstate == MotorState.RIGHT else MotorState.RIGHTEMPTY
      self.motorstatecounter = self.states[self.motorstate]["repeat"]
      self.lastempty = time.time()
      return True
    elif dt > HIGH_POWER_SECS:
      #self.states[MotorState.LEFT]["duration"] = ANTI_FLIP_MAX
      #self.states[MotorState.RIGHT]["duration"] = CLOCK_FLIP_MAX
      if int(dt / JIGGLE_INTERVAL) % 2 == 0:
        self.states[MotorState.LEFT]["duration"] = ANTI_FLIP_MAX
        self.states[MotorState.RIGHT]["duration"] = CLOCK_FLIP_TIME
      else:
        self.states[MotorState.LEFT]["duration"] = ANTI_FLIP_TIME
        self.states[MotorState.RIGHT]["duration"] = CLOCK_FLIP_MAX
    elif dt > LOW_POWER_SECS and dt <= HIGH_POWER_SECS:
      # Pull left for a bit, then right
      if int(dt / JIGGLE_INTERVAL) % 2 == 0:
        self.states[MotorState.LEFT]["duration"] = ((ANTI_FLIP_MAX - ANTI_FLIP_TIME) * (dt - LOW_POWER_SECS)/(HIGH_POWER_SECS - LOW_POWER_SECS)) + ANTI_FLIP_TIME
        self.states[MotorState.RIGHT]["duration"] = CLOCK_FLIP_TIME
      else:
        self.states[MotorState.LEFT]["duration"] = ANTI_FLIP_TIME
        self.states[MotorState.RIGHT]["duration"] = ((CLOCK_FLIP_MAX - CLOCK_FLIP_TIME) * (dt - LOW_POWER_SECS)/(HIGH_POWER_SECS - LOW_POWER_SECS)) + CLOCK_FLIP_TIME
    return False
    
  def targetFromWeight(self, weight):
    return (weight * self.scaletarget) / self.scaleweight

  def weightFromTarget(self, target):
    return (target * self.scaleweight) / self.scaletarget

  def load(self):
    n = self.name + ".conf"
    if not os.path.exists(n):
      return
    s = ""
    with open(n) as f:
      s = f.read()
    settings = json.loads(s)
    self.right = settings["right"]
    self.excess = settings["excess"]
    self.avg = settings["avg"]
    self.scaleweight = settings["scaleweight"]
    self.scaletarget = settings["scaletarget"]
    self.calms = settings["calms"]
    self.feeding = settings["feeding"]
    self.error = settings["error"]

  def save(self):
    settings = { 
      "right": self.right, 
      "excess": self.excess, 
      "avg": self.avg, 
      "scaleweight": self.scaleweight,
      "scaletarget": self.scaletarget,
      "calms": self.calms,
      "feeding": self.feeding,
      "error": self.error
    }
    with open(self.name + ".conf", "w") as f:
      f.write(json.dumps(settings))
  
  def resetSettings(self):
    self.right = False
    self.excess = 0.0
    self.avg = 0.0
    self.dispensed = 0.0
    self.feeding = False
    self.error = False

  def resetCalibration(self):
    self.scaleweight = 25.0
    self.scaletarget = 3  # 10 # 30  # 6
    #self.calms = 0
  
  def calibrate(self, weight, target):
    self.scaleweight = weight
    self.scaletarget = target

  def info(self):
    print("{0} dispensed {1:.2f} average {2:.2f} excess {3:.2f} scaleweight {4:.2f}  scaletarget {5:.2f} calms {6:.2e} error {7}".
      format(self.name, self.dispensed, self.avg, self.excess, self.scaleweight, self.scaletarget, self.calms, self.error))

def __init__():
  return
