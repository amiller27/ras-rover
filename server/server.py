import tornado.ioloop
import tornado.web
import tornado.websocket
from tornado.websocket import websocket_connect

import RPIO as GPIO
import RPIO.PWM as PWM

import json
import serial
import struct
import time
import threading

from collections import deque

# Threads currently open in this application
open_threads = []
# Messages needed to be processed
messages = deque()

#-----------------------------------------------------
# set_camera_servo_position
# Sets the camera servo to a specified angle
#-----------------------------------------------------
#def set_camera_servo_position(servo, position):
	#pulse = camera_servo_pulse[servo] + float(camera_servo_pulse[servo+2] - camera_servo_pulse[servo]) * (position - camera_servo_angle[servo]) / (camera_servo_angle[servo+1] - camera_servo_angle[servo])
	#pulse = (pulse//10)*10
	#camera_servo1.set_servo(camera_servo_pins[servo], pulse)
def v_servo_write(position):
	#print("updating servo1: " + str(position))
	arduino_serial.write('sv' + 'v') # extra v is dummy character
	#The offset is because 120 degrees is actually 0 its constrained on the arduino
	for b in struct.pack('f', position):
		arduino_serial.write(b)
	arduino_serial.write(':')
	

def h_servo_write(position):
	#print("updating servo2: " + str(position))
	arduino_serial.write('sh' + 'h') #extra h is dummy character
	#The offset is because 150 degrees is actually 0 its constrained on the arduino
	for b in struct.pack('f', position):
		arduino_serial.write(b)
	arduino_serial.write(':')

#-----------------------------------------------------
# cleanup
# Shut everything down
#-----------------------------------------------------
def cleanup():
	PWM.cleanup()
	GPIO.cleanup()
	for thread in open_threads:
		thread.stop()
		thread.join()

#-----------------------------------------------------
# poll
# Poll the stopable thread
#-----------------------------------------------------
def poll(ws):
	while True:
		# Can't do anything if the websocket closed or the thread
		# has already been stopped
		if ws._closed or threading.current_thread().stopped():
			break
		#ws.write_message(u'send_input')
		time.sleep(polling_time)
	# Thread is dead, remove
	open_threads.remove(threading.current_thread())

#=========================================================
# StoppableThread
#---------------------------------------------------------
# The thread kept alive in the background
#=========================================================
class StoppableThread(threading.Thread):

	#-----------------------------------------------------
	# __init__
	# Start a new stoppable thread
	#-----------------------------------------------------
	def __init__(self, *args, **kwargs):
		super(StoppableThread, self).__init__(*args, **kwargs)
		self._stop = threading.Event()

	#-----------------------------------------------------
	# stop
	# Stop the thread
	#-----------------------------------------------------
	def stop(self):
		self._stop.set()

	#-----------------------------------------------------
	# stopped
	# Check if the thread is stopped
	#-----------------------------------------------------
	def stopped(self):
		return self._stop.isSet()

#=========================================================
# KeyPressHandler
#---------------------------------------------------------
# Handles all of the input from the web app
#=========================================================
class KeyPressHandler(tornado.websocket.WebSocketHandler):

	throttle = 1.0	# The speed multiplier for the entire robot's motors
	servoPos1 = 0		# The old position of the first servo
	servoPos2 = 0		# The old position of the second servo

	#-----------------------------------------------------
	# open
	# Opens the websocket, connecting to the app
	#-----------------------------------------------------
	def open(self):
		self._closed = False
		print('Websocket Opened')
		new_thread = StoppableThread(target = poll, args = (self,))
		open_threads.append(new_thread)
		new_thread.start()

	#-----------------------------------------------------
	# on_message
	# Handles input from the app
	#-----------------------------------------------------
	def on_message(self, message):
		print("received message")
		msg = json.loads(message)
		# Arrow key input for motors
		if (msg.has_key('Keys')):
			# Arrow keys are sent in a binary format:
			# 1 - Up, 2 - Down, 4 - Left, 8 - Right
			arrows = msg['Keys']
			direction = [arrows & 1, (arrows & 2) >> 1, (arrows & 4) >> 2, (arrows & 8) >> 3]
			wheels = [-direction[0]+direction[1]+direction[2]-direction[3],direction[0]-direction[1]+direction[2]-direction[3]]
			# The left and right sets of wheels will always move in the same direction.
			# If a specific wheel needs to be addressed instead, use mfl or mbl
			# Write the values to the arduino
			#print('writing some velocity or something')
			arduino_serial.write('mal')
                        for b in struct.pack('f', wheels[0] * self.throttle):
                            arduino_serial.write(b)
                        arduino_serial.write(':')
			arduino_serial.write('mar')
                        for b in struct.pack('f', wheels[1] * self.throttle):
                            arduino_serial.write(b)
                        arduino_serial.write(':')
			#print(arduino_serial.readline())

		# Slider used to adjust throttle for all motors
		if (msg.has_key('Thr')):
			self.throttle = msg['Thr'] / 256.0
		# Tilt used to adjust camera position
		if (msg.has_key('Tilt')):
			orientation = msg['Tilt']
			v_servo_write(orientation[2])
			h_servo_write(orientation[3])

	#-----------------------------------------------------
	# check_origin
	# Set to true to allow all cross-origin traffic
	#-----------------------------------------------------
	def check_origin(self, origin):
		return True

	#-----------------------------------------------------
	# on_close
	# Close the socket (ignore errors)
	#-----------------------------------------------------
	def on_close(self):
		self._closed = True

#-----------------------------------------------------
# Program starts here
#-----------------------------------------------------
if __name__ == '__main__':
	# Start the websocket
	application = tornado.web.Application([
		(r'/keysocket', KeyPressHandler),
		(r'/(.*)', tornado.web.StaticFileHandler, { 'path': './www', 'default_filename': 'index.html' })
	])
	# Set up connection to Arduino on the USB port
	arduino_serial = serial.Serial('/dev/ttyAMA0', 115200);
	# Time in between thread polling
	polling_time = 0.1

	#conn = websocket_connect('ws://aftersomemath.com:8888/rover', on_message_callback = data_received)

	application.listen(80)
	try:
		tornado.ioloop.IOLoop.instance().start()
	except KeyboardInterrupt:
		cleanup()
	finally:
		cleanup()
