from gpiozero import MCP3008
import time

adc = MCP3008(channel=1, device=0)
while True:
  print(adc.value)
  time.sleep(1)

