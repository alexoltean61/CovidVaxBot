from Server import Server
from TelegramInterface import TelegramInterface
from telegram.ext import (
	Updater,
	CommandHandler,
	PicklePersistence
)
from telegram import Update, ParseMode
from flask import Flask, request
from multiprocessing import Process, Queue, Manager
import json
import signal
import os
import time
import traceback
from datetime import datetime

PORT =   # port number
SERVER = # server URL
TOKEN =  # telegram bot token
CHAIN =  # path to ssl fullchain.pem
KEY   =  # path to ssl privkey.pem

interface = TelegramInterface(pickle_persistence=PicklePersistence(filename='states/states_file'))
manager = Manager()
time_to_kill = manager.Condition()
logging = Queue()
announcements = Queue()
is_bot_on = False
proc = None

def write_to_config():
	vaccines = {1: "BioNTech", 2: "Moderna", 3: "AstraZeneca"}
	main_URL = "https://programare.vaccinare-covid.gov.ro/scheduling/api/centres"
	counties_URL = "https://programare.vaccinare-covid.gov.ro/nomenclatures/api/county"
	auth_URL = "https://programare.vaccinare-covid.gov.ro/auth/login"
	headers = {
		"Accept": "application/json",
		"Content-Type": "application/json", 
	}
	payload = {
		"countyID": None,
		"localityID":None,
		"name":None,
		"identificationCode":"2701104019729",
		"recipientID":None,
		"masterPersonnelCategoryID":-3,
		"personnelCategoryID":27
	}

	config = open("config.init", "w")
	config.write("NDBlNmJjZDEtNmEzMC00NDA2LWE0ZDUtYTg3YmEzMTEyYjM5\n")
	config.write(json.dumps(vaccines)+"\n")
	config.write(str(main_URL)+"\n")
	config.write(str(counties_URL)+"\n")
	config.write(str(auth_URL)+"\n")
	config.write(json.dumps(headers)+"\n")
	config.write(json.dumps(payload)+"\n")

	config.close()

def start(update, context):
	chat_id = update.message.chat_id
	logproc = Process(target=logging_listener, args=(updater.bot, chat_id))
	logproc.start()
	logging.put("Started logging")

def bot_on(update, context):
	global is_bot_on
	global proc
	if is_bot_on == True:
		return
	proc = Process(target=interface.work, args=(logging, time_to_kill, announcements))
	proc.start()
	is_bot_on = True

def bot_off(update, context):
	global is_bot_on
	global proc
	if is_bot_on == False:
		return
	with time_to_kill:
		logging.put("Starting to kill")
		time_to_kill.notify_all()

	with time_to_kill:
		time_to_kill.wait()
		os.kill(proc.pid, signal.SIGKILL)
		proc.join()

	logging.put("done")
	is_bot_on = False

def new_cookie(update, context):
	print(context.bot)
	print(update)
	with open("config.init", "r") as f:
		config = f.readlines()
	with open("config.init", "w") as f:
		f.write(context.args[0] + "\n")
		f.writelines(config[1:])

def announce(update, context):
	msg = " ".join(context.args)
	logging.put(msg)
	announcements.put(msg)

def error(update, context):
	logging.put(str(context.error))

def logging_listener(bot, chat_id):
	logging.put(f"MASTER: logger {os.getpid()}")
	while True:
		full_msg = logging.get()
		print(full_msg)
		i = 0
		try:
			if len(full_msg) >= 4096:
				while i < len(full_msg):
					last_enter = full_msg[i:min(len(full_msg), i+4096)].rfind("}")
					if last_enter <= 0:
						last_enter = full_msg[i:min(len(full_msg), i+4096)].rfind(" ")
						if last_enter <= 0:
							last_enter = len(full_msg) - i
					bot.send_message(chat_id, full_msg[i:i+last_enter])
					i += last_enter + 1
			else:
				bot.send_message(chat_id, full_msg)
		except Exception as e:
			bot.send_message(chat_id, str(e))

if __name__ == "__main__":
	global updater
	try:
		#write_to_config()
		logging.put(f"MASTER: main {os.getpid()}")
		pid = 0
		updater = Updater(TOKEN)
		dispatcher = updater.dispatcher
		dispatcher.add_handler(CommandHandler("start", start))
		dispatcher.add_handler(CommandHandler("bot_on", bot_on))
		dispatcher.add_handler(CommandHandler("bot_off", bot_off))
		dispatcher.add_handler(CommandHandler("new_cookie", new_cookie))
		dispatcher.add_handler(CommandHandler("announce", announce))
		dispatcher.add_error_handler(error)
		webhook = Server(updater, TOKEN, '0.0.0.0', PORT, (CHAIN, KEY))
		updater.bot.delete_webhook()
		updater.bot.set_webhook(SERVER + TOKEN)

		webhook.start()

		updater.idle()
	except Exception as e:
		print(traceback.format_exc())
		logging.put(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Master: {traceback.format_exc()}")
