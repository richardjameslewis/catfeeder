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
# BOARD numbers for outputs
ANTI_FLIP_PWM = ((2.0/20.0) * 100)
CLOCK_FLIP_PWM = ((1.0/20.0) * 100)
ANTI_FLIP_TIME = 0.33
CLOCK_FLIP_TIME = 0.3
ANTI_WIGGLE_PWM = (2.0/20.0) * 100
CLOCK_WIGGLE_PWM = (1.0/20.0) * 100
ANTI_WIGGLE_TIME = 0.36
CLOCK_WIGGLE_TIME = 0.3
#MIN_ANALOG = 0.05
FED_TIMEOUT_SECS = 5
EMPTY_TIME = 1.5
EMPTY_TEST_SECS = 15
EMPTY_TIMEOUT_SECS = 35
DEBUG_PIN = 6
# The feeder always overfeeds, scale back the target
OVERFEED_FACTOR = 0.9
# The feeder underestimates by ~10%, adjust here?
SCALE_SCALE = 1.0   # 1.1

GPIO.setup(DEBUG_PIN, GPIO.OUT)
GPIO.output(DEBUG_PIN, False)

verbose = False

class MotorState(Enum):
  START = 0
  LEFTWIGGLE = 1
  RIGHTWIGGLE = 2
  #WAIT1 = 
  LEFT = 3
  #LEFTWAIT = 3
  RIGHT = 4
  #RIGHTWAIT = 5
  #COMPLETE = 5
  LEFTEMPTY = 5
  RIGHTEMPTY = 6

states2 = {
    MotorState.START:       { "pwm": 0, "duration":  0, "repeat": 0, "next1": MotorState.LEFTWIGGLE, "next2": MotorState.RIGHTWIGGLE },
    #MotorState.LEFTWIGGLE:  { "pwm": ANTI_FLIP_PWM, "duration":  ANTI_FLIP_TIME, "repeat": 4, "next1": MotorState.RIGHTWIGGLE, "next2": MotorState.RIGHTWIGGLE },
    #MotorState.RIGHTWIGGLE: { "pwm": CLOCK_FLIP_PWM, "duration":  CLOCK_FLIP_TIME, "repeat": 4, "next1": MotorState.LEFTWIGGLE, "next2": MotorState.LEFTWIGGLE },
    MotorState.LEFTWIGGLE:  { "pwm": ANTI_WIGGLE_PWM, "duration":  5, "repeat": 0, "next2": MotorState.RIGHTWIGGLE, "next1": None },
    MotorState.RIGHTWIGGLE: { "pwm": CLOCK_WIGGLE_PWM, "duration":  5, "repeat": 0, "next2": MotorState.LEFTWIGGLE, "next1": None },
    MotorState.LEFT:        { "pwm": 0, "duration":  ANTI_FLIP_TIME, "repeat": 0, "next1": MotorState.RIGHT, "next2": MotorState.RIGHTWIGGLE},
    MotorState.RIGHT:       { "pwm": 0, "duration":  CLOCK_FLIP_TIME, "repeat": 0, "next1": MotorState.LEFT, "next2": MotorState.LEFTWIGGLE},
    #MotorState.COMPLETE:    { "pwm": 0, "duration":  0, "repeat": 0, "next1": MotorState.START }
}

states = {
    MotorState.START:       { "pwm": 0, "duration":  0, "repeat": 0, "next1": MotorState.LEFTWIGGLE, "next2": MotorState.RIGHTWIGGLE },
    #MotorState.LEFTWIGGLE:  { "pwm": ANTI_FLIP_PWM, "duration":  ANTI_FLIP_TIME, "repeat": 4, "next1": MotorState.RIGHTWIGGLE, "next2": MotorState.RIGHTWIGGLE },
    #MotorState.RIGHTWIGGLE: { "pwm": CLOCK_FLIP_PWM, "duration":  CLOCK_FLIP_TIME, "repeat": 4, "next1": MotorState.LEFTWIGGLE, "next2": MotorState.LEFTWIGGLE },
    MotorState.LEFTWIGGLE:  { "pwm": ANTI_WIGGLE_PWM, "duration":  ANTI_WIGGLE_TIME, "repeat": 4, "next1": MotorState.RIGHTWIGGLE, "next2": MotorState.RIGHT },
    MotorState.RIGHTWIGGLE: { "pwm": CLOCK_WIGGLE_PWM, "duration":  CLOCK_WIGGLE_TIME, "repeat": 4, "next1": MotorState.LEFTWIGGLE, "next2": MotorState.LEFT },
    MotorState.LEFT:        { "pwm": ANTI_FLIP_PWM, "duration":  ANTI_FLIP_TIME, "repeat": 4, "next1": MotorState.RIGHT, "next2": MotorState.RIGHTWIGGLE},
    MotorState.RIGHT:       { "pwm": CLOCK_FLIP_PWM, "duration":  CLOCK_FLIP_TIME, "repeat": 4, "next1": MotorState.LEFT, "next2": MotorState.LEFTWIGGLE},
    MotorState.LEFTEMPTY:   { "pwm": ANTI_FLIP_PWM, "duration":  EMPTY_TIME, "repeat": 0, "next1": MotorState.RIGHT, "next2": MotorState.RIGHT},
    MotorState.RIGHTEMPTY:  { "pwm": CLOCK_FLIP_PWM, "duration":  EMPTY_TIME, "repeat": 0, "next1": MotorState.LEFT, "next2": MotorState.LEFT},
    #MotorState.COMPLETE:   { "pwm": 0, "duration":  0, "repeat": 0, "next1": MotorState.START }
}

class Feeder:
  #def __init__(self, name, scaleweight, scaletarget, pwmpin, resetpin, datapin, adcchannel):
  def __init__(self, name, pwmpin, resetpin, datapin, adcchannel):
    self.name = name

    #self.scaleweight = scaleweight
    #self.scaletarget = scaletarget
    self.empty = False
    self.running = False

    #self.excess = 0
    #self.avg = 0
    #self.right = False
    self.resetSettings()
    self.resetCalibration()

    self.resetpin = resetpin
    self.datapin = datapin
    GPIO.setup(self.resetpin, GPIO.OUT)
    # Keep high to reduce current, power
    GPIO.output(self.resetpin, True)
    GPIO.setup(self.datapin, GPIO.IN)

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

    self.load()

  def startFeed(self, weight):
    self.running = True
    self.lastempty = self.lasttime = time.time()
    self.sumb = 0
    self.suma = 0
    self.sums = 0
    self.counts = 0
    self.total = 0
    self.ms = 0
    #self.excess = 0
    self.right = not self.right
    #self.avg = 0
    self.motorstate = MotorState.START
    self.weight = weight
    self.target = self.targetFromWeight(weight - self.excess)
    #self.target *= OVERFEED_FACTOR
    #self.right = right
    self.motorevent.clear()

    self.adcthread = threading.Thread(target=self.adcThread)
    self.adcthread.daemon = True
    self.adcthread.start()

    self.measure = threading.Thread(target=self.measureThread)
    self.measure.daemon = True
    self.measure.start()
    time.sleep(5)
    noise = self.meansquared()
    if verbose:
      print("Mean squared noise {0}".format(noise))

    self.motor = threading.Thread(target=self.motorThread)
    self.motor.daemon = True
    self.motor.start()

  def join(self):
    self.measure.join()
    self.motor.join()

  def stop(self):
    self.motorevent.set()

  def meansquared(self):
    self.ms = self.sums / self.counts
    self.sums = 0
    self.counts = 0
    return self.ms

  #def isempty(self):
  #  return self.empty

  def measureThread(self):
    if verbose:
      print("measureThread {0} {1} {2}".format(self.datapin, self.resetpin, self.adcchannel))
    while self.running:
      if self.running:      # xxx
        GPIO.output(self.resetpin, False)
        #self.running = not self.motorevent.wait(0.0005)
        time.sleep(0.0005)
      GPIO.output(self.resetpin, True)
      #self.running = not self.motorevent.wait(0.0095 - 0.004)
      #time.sleep(0.0095 - 0.003)
      time.sleep(0.0095 - 0.0005)

      ## Analogue estimate
      #a = self.adc.value 
      ##if a > MIN_ANALOG:
      #self.suma += a
      ## Square Analogue
      #self.sums += (a * a) - self.ms
      #self.counts += 1
      self.adcevent.set()
      time.sleep(0.0005)
      #time.sleep(0)

      # Binary estimate
      b = GPIO.input(self.datapin)
      self.sumb += b

      #if b > 0 or a > MIN_ANALOG:
      #if b > 0:
      #  self.lasttime = time.time()
      #  #print("{0} {1} {2} {3}".format(self.sumb, self.suma, self.sums, self.counts))

      #if not self.motorevent.is_set() and self.sumb >= self.target:
      if not self.motorevent.is_set() and self.sums >= self.target:
        #self.motorrunning = False
        self.motorevent.set()
      
      if self.running:      # bogus?
        # Cope with timeout
        #self.running = (time.time() - self.starttime) < TIMEOUT_SECS
        self.running = (time.time() - self.lasttime) < (FED_TIMEOUT_SECS if self.motorevent.is_set() else EMPTY_TIMEOUT_SECS)
        #if not self.running:
        if not self.running:
          #print("sumb {0} suma {1} sums {2} total {3} counts {4}".format(self.sumb, self.suma, self.sums, self.total, self.counts))
          if not self.motorevent.is_set():
            self.empty = True
          self.motorevent.set()
          self.adcevent.set()
      #if self.running:
      #  GPIO.output(self.resetpin, False)
      #  #self.running = not self.motorevent.wait(0.0005)
      #  time.sleep(0.0005)
      #else:
      #  self.motorevent.set()
    
    # Keep high to reduce current, power
    GPIO.output(self.resetpin, True)

    self.dispensed = self.weightFromTarget(self.sums)
    self.excess = self.dispensed - (self.weight - self.excess)
    self.avg = self.dispensed if self.avg == 0 else (self.avg * 0.8) + (self.dispensed * 0.2)
    #print("right {0} dispensed {1} excess {2} avg {3}".format(self.right, self.dispensed, self.excess, self.avg))
    self.save()

    if verbose:
      print("measureThread ends {0}".format(self.running))
      print("sumb {0} suma {1} sums {2} total {3} counts {4}".format(self.sumb, self.suma, self.sums, self.total, self.counts))

  def adcThread(self):
    if verbose:
      print("adcThread {0} {1} {2}".format(self.datapin, self.resetpin, self.adcchannel))
    while self.running:
      self.adcevent.wait()
      self.adcevent.clear()
      GPIO.output(DEBUG_PIN, True)

      # Analogue estimate
      a = self.adc.value 
      a2 = a * a
      #if a > MIN_ANALOG:
      if a2 > self.ms:
        self.suma += a
        # Square Analogue
        self.sums += a2 - self.ms
        self.counts += 1
      if a > 0.5:
        self.lastempty = self.lasttime = time.time()
      self.total += 1
      GPIO.output(DEBUG_PIN, False)
    if verbose:
      print("adcThread {0} {1} {2}".format(self.datapin, self.resetpin, self.adcchannel))


  def motorThread(self):
    if verbose:
      print("motorThread {0}".format(self.pwmpin))

    while not self.motorevent.is_set():
      state = states[self.motorstate]
      if self.motorstatecounter > 1:
        self.motorstatecounter -= 1
        self.motorstate = state["next1"]
        state = states[self.motorstate]
      else:
        if self.motorstate == MotorState.START and not self.right:
          self.motorstate = state["next1"] 
        elif ((time.time() - self.lastempty) > EMPTY_TEST_SECS
             and (self.motorstate == MotorState.LEFT 
             or self.motorstate == MotorState.RIGHT)):
          self.motorstate = MotorState.LEFTEMPTY if self.motorstate == MotorState.RIGHT else MotorState.RIGHTEMPTY
          self.lastempty = time.time()
        else:        
          self.motorstate = state["next2"]

        if self.motorstate == None:
          # allow state machines to terminate themselves
          self.motorevent.set()
        else:
          state = states[self.motorstate]
          self.motorstatecounter = state["repeat"]

      #print("{0} {1} {2} {3}".format(self.motorstate, state["pwm"], state["duration"], self.motorstatecounter))

      self.pwm.ChangeDutyCycle(state["pwm"])
      self.motorevent.wait(state["duration"])

    if verbose:
      print("motorThread ends {0}".format(self.running))

    # Whatever state we end in set pwm to 0
    self.pwm.ChangeDutyCycle(0)

  def targetFromWeight(self, weight):
    return (weight * self.scaletarget) / (self.scaleweight * SCALE_SCALE)

  def weightFromTarget(self, target):
    return (SCALE_SCALE * target * self.scaleweight) / self.scaletarget

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

  def save(self):
    settings = { 
      "right": self.right, 
      "excess": self.excess, 
      "avg": self.avg, 
      "scaleweight": self.scaleweight,
      "scaletarget": self.scaletarget,
    }
    with open(self.name + ".conf", "w") as f:
      f.write(json.dumps(settings))
  
  def resetSettings(self):
    self.right = False
    self.excess = 0.0
    self.avg = 0.0
    self.dispensed = 0.0

  def resetCalibration(self):
    self.scaleweight = 25.0
    self.scaletarget = 18
  
  def calibrate(self, weight, target):
    self.scaleweight = weight
    self.scaletarget = target
    #self.save()
    #settings = { 
    #  "scaleweight": self.scaleweight, 
    #  "scaletarget": self.scaletarget, 
    #}
    #with open("catfeeder.json", "w") as f:
    #  f.write(json.dumps(settings))


  def info(self):
    print("{0} dispensed {1:.2f} average {2:.2f} excess {3:.2f} scaleweight {4:.2f}  scaletarget {5:.2f}".
      format(self.name, self.dispensed, self.avg, self.excess, self.scaleweight, self.scaletarget))

def __init__():
  return
