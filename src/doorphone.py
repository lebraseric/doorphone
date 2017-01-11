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

led = port.PA7
call_button = port.PA13

LOG_LEVEL=3

# Logging callback
def log_cb(level, str, len):
    print str,

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
        print "Call is ", self.call.info().state_text,
        print "last code =", self.call.info().last_code, 
        print "(" + self.call.info().last_reason + ")"
        
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

    def on_state(self):
        global acc
        if self.call.info().state == pj.CallState.DISCONNECTED:
            acc.delete()
    
    def on_dtmf_digit(self, digits):
        print "DTMF received, digit=", digits

def call_button_handler(signum, frame):
    global acc
    global call
    acc_cb = MyAccountCallback()
    acc = lib.create_account(acc_cfg, cb=acc_cb)
    acc_cb.wait()
    # Call user
    call = acc.make_call(os.getenv('SIP_CALL_URI'), MyCallCallback())
    
# Initialize the GPIO module
gpio.init()

# Setup ports
gpio.setcfg(led, gpio.OUTPUT)
gpio.setcfg(call_button, gpio.INPUT)

# Enable pull-up resistor
gpio.pullup(call_button, gpio.PULLUP)

# Turn off led
gpio.output(led, gpio.LOW)

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

    # Blink led 3 times to confirm init
    """
    for i in range(3):
        gpio.output(led, gpio.HIGH)
        sleep(0.3)
        gpio.output(led, gpio.LOW)
        sleep(0.3)
    """
    gpio.output(led, gpio.HIGH)
    
    signal.signal(signal.SIGUSR1, call_button_handler)

    call_start = None
    call_timeout = datetime.timedelta(seconds=int(os.getenv('CALL_TIMEOUT', '120')))

    while True:
        state = gpio.input(call_button)
        if not state:
            # Make call
            call_button_handler(0, None)
        if call_start <> None:
            if (datetime.datetime.today() - call_start) > call_timeout:
                call.hangup()
                call_start = None
        sleep(0.2)

except pj.Error, e:
    print "Exception: " + str(e)
    gpio.output(led, gpio.LOW)
    lib.destroy()
    lib = None
    sys.exit(1)

except KeyboardInterrupt:
    print "Killed by user"
    gpio.output(led, gpio.LOW)
    lib.destroy()
    lib = None
    sys.exit(0)
