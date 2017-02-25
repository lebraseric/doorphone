#!/usr/bin/env python

import os
import sys
import pjsua as pj
import threading
import signal
import datetime
from pyA20.gpio import gpio
from pyA20.gpio import port
from time import sleep

if not os.getegid() == 0:
    sys.exit('Script must be run as root')

led_yellow = port.PA7
led_red = port.PA11
led_green = port.PA12
relay_0 = port.PA15
relay_1 = port.PA16
call_button = port.PA13

LOG_LEVEL=3

# Logging callback
def log_cb(level, str, len):
    print str,

# Handle TERM signal
class GracefulKiller:
    kill_now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self,signum, frame):
        self.kill_now = True

# Callback to receive events from account
class MyAccountCallback(pj.AccountCallback):
    sem = None

    def __init__(self, account=None):
        pj.AccountCallback.__init__(self, account)

    def wait(self):
        self.sem = threading.Semaphore(0)
        self.sem.acquire()

    def on_reg_state(self):
        if self.sem:
            if self.account.info().reg_status >= 200:
                self.sem.release()

# Callback to receive events from Call
class MyCallCallback(pj.CallCallback):
    def __init__(self, call=None):
        pj.CallCallback.__init__(self, call)

    # Notification when call state has changed
    def on_state(self):
        global acc
        global call_start
        global call_nb
        print "Call is ", self.call.info().state_text,
        print "last code =", self.call.info().last_code, 
        print "(" + self.call.info().last_reason + ")"
        if self.call.info().state == pj.CallState.DISCONNECTED:
            acc.delete()
            call_start = None
            call_nb -= 1
        
    # Notification when call's media state has changed.
    def on_media_state(self):
        global lib
        global call_start
        if self.call.info().media_state == pj.MediaState.ACTIVE:
            # Connect the call to sound device
            call_slot = self.call.info().conf_slot
            lib.conf_connect(call_slot, 0)
            lib.conf_connect(0, call_slot)
            call_start = datetime.datetime.today()

    def on_dtmf_digit(self, digits):
        global relay_0
        global relay_1
        print "DTMF received, digit=", str(digits)
        if digits == "#":
            relay = relay_0
        elif digits == "*":
            relay = relay_1
        else:
            return
        # Ouverture portail ou gache : fermer le contact pendant 1 s
        gpio.output(relay, gpio.LOW)
        sleep(1)
        gpio.output(relay, gpio.HIGH)

def call_button_handler():
    global lib
    global acc
    global call
    global call_nb
    if call_nb == 0:
        call_nb += 1
        acc_cb = MyAccountCallback()
        acc = lib.create_account(acc_cfg, cb=acc_cb)
        acc_cb.wait()
        # Call user
        call = acc.make_call(os.getenv('SIP_DEST_URI'), MyCallCallback())
    
def signal_handler(signum, frame):
    if signum == signal.SIGUSR1:
        call_button_handler()

# Initialize the GPIO module
gpio.init()

# Setup ports
gpio.setcfg(led_yellow, gpio.OUTPUT)
gpio.setcfg(led_red, gpio.OUTPUT)
gpio.setcfg(led_green, gpio.OUTPUT)
gpio.setcfg(relay_0, gpio.OUTPUT)
gpio.setcfg(relay_1, gpio.OUTPUT)
gpio.setcfg(call_button, gpio.INPUT)

# Enable pull-up resistor
gpio.pullup(call_button, gpio.PULLUP)

# Light off bicolor led
gpio.output(led_red, gpio.HIGH)
gpio.output(led_green, gpio.HIGH)

# Light up the doorphone
gpio.output(led_yellow, gpio.HIGH)

# Initialize relays
gpio.output(relay_0, gpio.HIGH)
gpio.output(relay_1, gpio.HIGH)

# Create library instance
lib = pj.Lib()

try:
    # Init library with default config and some customized
    # logging config.
    lib.init(log_cfg = pj.LogConfig(level=LOG_LEVEL, callback=log_cb))

    # Create UDP transport which listens to any available port
    transport = lib.create_transport(pj.TransportType.UDP)
    print "\nListening on", transport.info().host, 
    print "port", transport.info().port, "\n"
    
    # Start the library
    lib.start()

    # Create account
    acc_cfg = pj.AccountConfig()
    acc_cfg.id = os.getenv('SIP_ID')
    acc_cfg.reg_uri = os.getenv('SIP_REGISTRAR')
    acc_cfg.auth_cred = [ pj.AuthCred(os.getenv('SIP_REALM', '*'), os.getenv('SIP_USERNAME'), os.getenv('SIP_PASSWORD')) ]
    acc_cfg.reg_timeout = int(os.getenv('SIP_REG_TIMEOUT', '300'))

except pj.Error, e:
    print "Exception: " + str(e)
    gpio.output(led_yellow, gpio.LOW)
    lib.destroy()
    lib = None
    sys.exit(1)

# kill -SIGUSR1 to simulate call button pressed
signal.signal(signal.SIGUSR1, signal_handler)

call_start = None
call_timeout = datetime.timedelta(seconds=int(os.getenv('CALL_TIMEOUT', '120')))
call_nb = 0
bt_prev_state = 1
killer = GracefulKiller()
while True:
    bt_state = gpio.input(call_button)
    if bt_state != bt_prev_state:
        bt_prev_state = bt_state
        if bt_state == 0:
            # Make call
            call_button_handler()
    if call_start <> None and (datetime.datetime.today() - call_start) > call_timeout:
        call.hangup()
    if killer.kill_now:
        break
    sleep(0.2)

gpio.output(led_yellow, gpio.LOW)
lib.destroy()
lib = None
print "Doorphone shut down"
sys.exit(0)
