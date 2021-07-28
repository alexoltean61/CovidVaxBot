# TODO:
#
#	Alerting system... DONE
#
#	Make a new bot, CovidVaxMaster, which gives you on-the-fly control over
#		debugging the main bot: DONE
#	It should:
#		be the logging interface for all the exceptions raised by the main bot: DONE
#			(it sends you a message every time there's an exception)
#		be able to remotely inject:
#			new session cookies DONE
#			new vaccines!!!!;
#				and edit vaccine IDs in case what was inserted was wrong
#		be able to output messages on the main bot's chat DONE
#			("Hi, admin speaking. There will be some maintenanace to the bot tomorrow. Thx!")
#		be able to SIGKILL from a distance DONE
#	All from a dedicated chat of its own, which you can easily control even from your phone. DONE
#
#	PERSISTENT STORAGE OF USER DATA!!!! DONE
#
#	When editing preferences:
#		edit A COPY of context.user_data !!! DONE
#		which you write over the original iff user doesn't cancel the action!!! DONE
#
#	Tidy everything up, don't repeat yourself etc...

from Server import Server
from telegram import (
	InlineKeyboardMarkup,
	InlineKeyboardButton,
	ReplyKeyboardMarkup,
	ReplyKeyboardRemove,
	Update,
	ParseMode,
	Bot,
)
from telegram.ext import (
	Updater,
	CommandHandler,
	MessageHandler,
	Filters,
	ConversationHandler,
	CallbackQueryHandler,
	CallbackContext,
)
from telegram import Update
from flask import Flask, request
from multiprocessing import Manager, JoinableQueue, Process
from Controller import Controller
from datetime import datetime
import logging
import traceback
import time
import copy
import pickle
import os, signal

INITIAL, COUNTIES, VACCINES, ALERTS = range(4)

class TelegramInterface:
	def __init__(self, pickle_persistence=None):
		self.pickle_persistence = pickle_persistence

	def work(self, logging_queue, time_to_kill, announcement_queue=None):
		global updater
		logging_queue.put(f"INTERFACE: work {os.getpid()}")
		try:
			SERVER =  # server URL
			PORT =    # port number
			CHAIN =   # path to ssl fullchain.pem
			KEY   =   # path to ssl privkey.pem
			TOKEN =   # telegram bot token
			self.updater = Updater(TOKEN, persistence=self.pickle_persistence)
			updater = self.updater
			self.dispatcher = self.updater.dispatcher
			logging_queue.put("passed")

			conv_handler = ConversationHandler(entry_points=[CommandHandler('preferinte', self.preferences)], 
				states={
					INITIAL: [
						MessageHandler(Filters.regex('^(da|dA|Da|DA)$'), self.get_counties),
						MessageHandler(Filters.regex('^(nu|nU|Nu|NU)$'), self.cancel)
					],
					COUNTIES:
					[
						CallbackQueryHandler(self.select_button_county),
						CommandHandler("gata", self.counties2vaccines_handler)
					],
					VACCINES:
					[
						CallbackQueryHandler(self.select_button_vaccine),
						CommandHandler("gata", self.vaccines2alerts_handler)
					],
					ALERTS:
					[
						MessageHandler(Filters.regex('^(da|dA|Da|DA)$'), self.switch_and_update_alerts_dict),
						MessageHandler(Filters.regex('^(nu|nU|Nu|NU)$'), self.update_alerts)
					]
				}, fallbacks=[CommandHandler('anuleaza', self.cancel)],
				)
			self.dispatcher.add_handler(conv_handler)
			self.dispatcher.add_handler(CommandHandler("start", self.help))
			self.dispatcher.add_handler(CommandHandler("ajutor", self.help))
			self.dispatcher.add_handler(CommandHandler("ce_preferinte_am", self.get_preferences))
			self.dispatcher.add_handler(CommandHandler("alerte", self.switch_and_update_alerts_dict))
			self.dispatcher.add_handler(CommandHandler("vezi", self.get_county_slots))
			logging_queue.put("passed again")

			if logging_queue == None:
				logging_queue = JoinableQueue()
			self.logging_queue = logging_queue
			self.format = "%Y-%m-%d %H:%M:%S"
			self.killing_condition = time_to_kill
			self.manager = Manager()
			self.get_queue = JoinableQueue()
			self.alerts_queue = JoinableQueue()

			logging_queue.put("yes passed")
			self.c = Controller(interface_queue=self.get_queue, alerts_queue = self.alerts_queue, logging_queue=logging_queue, time_to_kill=time_to_kill, verbose=False)
			logging_queue.put("passed?")
			self.counties = self.c.get_dictionary()
			self.reverse_counties = self.reverse_counties()
			self.vaccines = self.c.get_vaccines()

			self.alerts_dict = self.create_or_load_alerts()
			self.alerts_proc = Process(target=self.alerts_listener, args=(self.updater.bot,self.alerts_dict))
			self.announcement_proc = Process(target=self.send_announcement, args=(self.updater.bot, self.alerts_dict, announcement_queue))
			self.killer_proc = Process(target=self.sleeping_killer, args=())
			self.alerts_proc.start()
			self.announcement_proc.start()
			self.killer_proc.start()
			self.webhook = Server(self.updater, TOKEN, '0.0.0.0', PORT, (CHAIN, KEY))
			self.updater.bot.delete_webhook()
			self.updater.bot.setWebhook(SERVER + TOKEN)
			self.webhook.start()
			self.c.join()
			self.alerts_proc.join()
			self.announcement_proc.join()
			self.killer_proc.join()
			self.updater.stop()
			with self.killing_condition:
				self.killing_condition.notify_all()
		except Exception as e:
			logging_queue.put(f"{datetime.now().strftime(self.format)} TelegramInterface: {traceback.format_exc()}")


	def send_announcement(self, bot, alerts_dict, ann_queue):
		if ann_queue == None:
			return
		while True:
			msg = ann_queue.get()
			subscribers = dict()
			for county, vax in dict(alerts_dict).items():
				for usrs_key, usrs_val in dict(vax).items():
					for usr in dict(usrs_val):
						subscribers[usr] = True
			for usr in subscribers:
				bot.send_message(usr, msg, parse_mode=ParseMode.HTML)

	def reverse_counties(self):
		reverse_counties = dict()
		for county_key, county_val in dict(self.c.dictionary).items():
			reverse_counties[county_val["shortName"]] = county_key
		self.logging_queue.put(str(reverse_counties))
		return reverse_counties

	def create_or_load_alerts(self):
		alerts = self.manager.dict()
		for c in self.counties:
			alerts[c] = self.manager.dict()
			for v in self.vaccines:
				alerts[c][v] = self.manager.dict()
		'''
		alerts[5][1] = {248916262: True}
		'''
		try:
			self.logging_queue.put("Let's try to load alerts_dict")
			with open(self.pickle_persistence.filename + "_alerts", "rb") as file:
				alerts_file = pickle.load(file)
				self.logging_queue.put(str(alerts_file))
				for c in self.counties:
					for v in self.vaccines:
						alerts[c][v] = self.manager.dict(alerts_file[c][v])
		except Exception as e:
			self.logging_queue.put(traceback.format_exc())

		self.logging_queue.put(str(dict(alerts[5][1])))
		return alerts

	def save_alerts(self):
		alerts = dict()
		for c in self.counties:
			alerts[c] = dict()
			for v in self.vaccines:
				alerts[c][v] = dict(self.alerts_dict[c][v])
		self.logging_queue.put(str(alerts))
		print(str(alerts))
		with open(self.pickle_persistence.filename + "_alerts", "wb") as file:
			pickle.dump(alerts, file)

	def help(self, update, context):
		update.effective_message.reply_text(
			'Beep beep boop, sunt doar un robot. Uite ce știu să fac:'
		)
		update.effective_message.reply_text(
			'    /preferinte: reglează-ți preferințele de vaccinare\n\n'
		)
		update.effective_message.reply_text(
			'	/ce_preferinte_am: vezi preferințele asociate contului tău\n\n'
		)
		update.effective_message.reply_text(
			'	/alerte: pornește-ți sau oprește-ți alertele\n\n'
		)
		update.effective_message.reply_text(
			'    /vezi [-j id_judet] [-v id_vaccin]: vezi situatia locurilor libere\n'
			'      dacă ai preferințele reglate, "/vezi" îți arată locuri conform preferințelor\n'
			'      dacă nu ai preferințele reglate, "/vezi" nu îți arată niciun loc\n'
			'      poți adăuga parametrii opționali -j sau -v\n'
			'		-j: rezultate doar din județele alese (vaccinurile rămân conform preferințelor),\n'
			'		-v: doar vaccinurile alese (județele rămân conform preferințelor)\n\n'
			'      ex.: "/vezi -j CL AB IF -v 1 3" va intoarce toate locurile pt. Pfizer sau AstraZeneca din Călărași, Alba sau Ilfov\n\n'
			'           "/vezi -v 1 3" va întoarce toate locurile pt. Pfizer sau AstraZeneca din județele alese în preferințe\n\n'
			'      legendă:\n     id_judet: codurile auto ale judetelor\n'
			'     id_vaccin: Pfizer=1, Moderna=2, AstraZeneca=3\n\n'
		)
		update.effective_message.reply_text(
			'	/ajutor: afișează exact acest mesaj'
		)
		update.effective_message.reply_text(
			'	Dacă ceva nu funcționează cum ar trebui sau ai dificultăți în folosirea botului, îl poți contacta pe admin aici: @talania'
		)
		return

	def get_preferences(self, update, context):
		if "counties" not in context.user_data or len(context.user_data["counties"]) == 0:
			update.effective_message.reply_text(
			'🇷🇴🇷🇴\nNu ai selectat niciun județ pe care îl urmărești.\n'
			'Nu poți primi alerte dacă nu îți alegi măcar un județ.'
		)
		else:
			update.effective_message.reply_text(
			'🇷🇴🇷🇴\nUrmărești județele: ' + 
			' '.join([self.counties[judetID]["name"] for judetID in context.user_data["counties"]])
			)
		if "vaccines" not in context.user_data or len(context.user_data["vaccines"]) == 0:
			update.effective_message.reply_text(
			'💉💉\nNu ai selectat niciun vaccin pe care îl urmărești.\n'
			'Nu poți primi alerte dacă nu îți alegi măcar un vaccin.'
		)
		else:
			update.effective_message.reply_text(
			'💉💉\nUrmărești vaccinurile: ' + 
			' '.join([self.vaccines[vaccinID] for vaccinID in context.user_data["vaccines"]])
			)
		if "alerts" not in context.user_data or context.user_data["alerts"] == False:
			update.effective_message.reply_text(
			'🚨🚨 ❌❌\nNu ești abonat la alerte.'
			'Dacă vrei să te abonezi, scrie /alerte.'
			)
		else:
			update.effective_message.reply_text(
			'🚨🚨 ✅✅\nEști abonat la alerte.\n'
			'Dacă vrei să te dezabonezi, scrie /alerte.'
			)
		update.effective_message.reply_text(
			'	Vrei să schimbi setările? Apelează /preferinte!'
		)

	def preferences(self, update, context):
		context.user_data["temp"] = copy.deepcopy(context.user_data)
		reply_options = [['Da', 'Nu']]
		update.effective_message.reply_text(
			#'Salut! Vrei să primești alerte în timp real în legătură cu situația locurilor noi la vaccinuri?\n'
			'Vrei să îți reglezi preferințele de vaccinuri?\n'
			'Scrie /anuleaza dacă nu mai vrei să continui.\n',
			reply_markup=ReplyKeyboardMarkup(reply_options, one_time_keyboard=True),
		)
		return INITIAL

	def get_counties(self, update, context):
		context.user_data["temp"]["updates"] = True

		update.effective_message.reply_text('🇷🇴🇷🇴 În ce județe te interesează să găsești loc de vaccinare?', 
			reply_markup=self.make_county_reply_markup(update, context))
		update.effective_message.reply_text('Apasă pe numele județelor care te interesează. Apasă încă o dată pentru a deselecta.')
		update.effective_message.reply_text(
			'Când ai terminat de selectat, apasă aici: /gata\n'
			'Sau scrie /anuleaza dacă nu mai vrei să continui.\n')
		return COUNTIES

	def counties2vaccines_handler(self, update, context):

		'''
		context.user_data["temp"]["vaccines"] = dict()
		for vax in self.vaccines:
			context.user_data["temp"]["vaccines"][vax] = True
		'''
		update.effective_message.reply_text('💉💉 Stocurile căror vaccinuri vrei să le urmărești?', 
			reply_markup=self.make_vaccine_reply_markup(update, context))
		update.effective_message.reply_text('Apasă pentru a selecta.\n')
		#update.message.reply_text('<b>ATENȚIE</b>:\nÎn România, vaccinul AstraZeneca <b>nu</b> se administrează persoanelor '
		#	'în vârstă de 55 de ani sau mai mult!\n', parse_mode=ParseMode.HTML)
		update.effective_message.reply_text(
			'Când ai terminat de selectat, apasă aici: /gata\n'
			'Sau scrie /anuleaza dacă nu mai vrei să continui.\n')
		return VACCINES

	def vaccines2alerts_handler(self, update, context):
		reply_options = [["Da", "Nu"]]
		if "alerts" not in context.user_data or context.user_data["alerts"] == False:
			update.effective_message.reply_text(
				'🚨🚨 ❌❌\nÎn acest moment <b>NU EȘTI ABONAT</b> la alerte despre situația vaccinurilor'
				' care corespund preferințelor tale.',
				parse_mode=ParseMode.HTML
			), 
			update.effective_message.reply_text(
				'Vrei să te abonezi?',
				reply_markup=ReplyKeyboardMarkup(reply_options, one_time_keyboard=True),
			)
		else:
			update.effective_message.reply_text(
				'🚨🚨 ✅✅\nEști <b>ABONAT</b> la alerte despre situația vaccinurilor'
				' care corespund preferințelor tale.',
				parse_mode=ParseMode.HTML
			), 
			update.effective_message.reply_text(
				'Vrei să te dezabonezi?',
				reply_markup=ReplyKeyboardMarkup(reply_options, one_time_keyboard=True),
			)
		return ALERTS

	def switch_and_update_alerts_dict(self, update, context):
		if "temp" in context.user_data:
			# "alerts" was called from the preferences conversation handler
			# if so, only switch state, and let end_state_handler do the updating
			temp_data = context.user_data["temp"]
			if "counties" not in temp_data or len(temp_data["counties"]) == 0:
				if "vaccines" not in temp_data or len(temp_data["vaccines"]) == 0:
					if "alerts" not in temp_data or temp_data["alerts"] == False:
						update.effective_message.reply_text("Nu te poți abona la alerte dacă nu îți alegi măcar un județ și măcar un vaccin!")
					else:
						update.effective_message.reply_text("Oricum nu ai vreun vaccin sau județ selectat, vei fi dezabonat automat.")
					return self.end_state_handler(update, context)
				if "alerts" not in temp_data or temp_data["alerts"] == False:
					update.effective_message.reply_text("Nu te poți abona la alerte dacă nu îți alegi măcar un județ!")
				else:
					update.effective_message.reply_text("Oricum nu ai vreun județ selectat, vei fi dezabonat automat.")
				temp_data["alerts"] = False
				return self.end_state_handler(update, context)
			if "vaccines" not in temp_data or len(temp_data["vaccines"]) == 0:
				if "alerts" not in temp_data or temp_data["alerts"] == False:
					update.effective_message.reply_text("Nu te poți abona la alerte dacă nu îți alegi măcar un vaccin!")
				else:
					update.effective_message.reply_text("Oricum nu ai vreun vaccin selectat, vei fi dezabonat automat.")
				temp_data["alerts"] = False
				return self.end_state_handler(update, context)

			if "alerts" not in temp_data:
				temp_data["alerts"] = True
			else:
				temp_data["alerts"] = not temp_data["alerts"]
			return self.update_alerts(update, context)


		user_data = context.user_data

		if "counties" not in user_data or len(user_data["counties"]) == 0:
			if "vaccines" not in user_data or len(user_data["vaccines"]) == 0:
				update.effective_message.reply_text("Nu te poți abona la alerte dacă nu îți setezi preferințele. Apelează /preferinte.")
				return
			update.effective_message.reply_text("Nu te poți abona la alerte dacă nu îți alegi măcar un județ pentru care să fii alertat. Apelează /preferinte.")
			return
		if "vaccines" not in user_data or len(user_data["vaccines"]) == 0:
			update.effective_message.reply_text("Nu te poți abona la alerte dacă nu îți alegi măcar un vaccin pentru care să fii alertat. Apelează /preferinte.")
			return

		if "alerts" not in user_data:
			user_data["alerts"] = True
			alerts_value = True
		else:
			alerts_value  = user_data["alerts"]
			alerts_value  = not alerts_value
			user_data["alerts"] = alerts_value

		chat_id = update.effective_message.chat_id
		counties = user_data["counties"]
		vaccines = user_data["vaccines"]
		if alerts_value == True:
			for judetID in counties:
				for vaccineID in vaccines:
					self.alerts_dict[judetID][vaccineID][chat_id] = True
			update.effective_message.reply_text(
				'🚨🚨✅✅ Ai <b>PORNIT</b> alertele.',
				parse_mode=ParseMode.HTML
			)
		else:
			for judetID in self.counties:
				for vaccineID in self.vaccines:
					if update.effective_message.chat_id in self.alerts_dict[judetID][vaccineID]:
						del self.alerts_dict[judetID][vaccineID][chat_id]
			update.effective_message.reply_text(
				'🚨🚨❌❌ Ai <b>OPRIT</b> alertele.',
				parse_mode=ParseMode.HTML
			)

		self.save_alerts()
		#context.bot_data["alerts_dict"] = dict(self.alerts_dict)
		update.effective_message.reply_text("Îți poți vedea toate preferințele apelând /ce_preferinte_am.")

	def update_alerts(self, update, context):
		temp_data = context.user_data["temp"]

		chat_id = update.effective_message.chat_id
		if "counties" in context.user_data:
			for judetID in self.counties:
				for vaccineID in self.vaccines:
					if (judetID not in temp_data["counties"] or vaccineID not in temp_data["vaccines"]) and chat_id in self.alerts_dict[judetID][vaccineID]:
							del self.alerts_dict[judetID][vaccineID][chat_id]
		
		if "alerts" in temp_data and temp_data["alerts"] == True:
			if 'counties' in temp_data and len(temp_data['counties']):
				counties = temp_data["counties"]
			else:
				counties = self.counties
			if 'vaccines' in temp_data and len(temp_data['vaccines']):
				vaccines = temp_data["vaccines"]
			else:
				vaccines = self.vaccines
			for judetID in counties:
				for vaccineID in vaccines:
					self.alerts_dict[judetID][vaccineID][chat_id] = True
		else:
			for judetID in self.counties:
				for vaccineID in self.vaccines:
					if chat_id in self.alerts_dict[judetID][vaccineID]:
						del self.alerts_dict[judetID][vaccineID][chat_id]
		#context.bot_data["alerts_dict"] = dict(self.alerts_dict)
		return self.end_state_handler(update, context)

	def end_state_handler(self, update, context):
		reference = context.user_data["temp"]
		for key, val in reference.items():
			context.user_data[key] = val
		del context.user_data["temp"]
		del reference
		self.save_alerts()
		update.effective_message.reply_text("Ți-am salvat preferințele. Le poți revedea oricând apelând /ce_preferinte_am.")
		return ConversationHandler.END

	def cancel(self, update, context):
		if "temp" in context.user_data:
			del context.user_data["temp"]
		update.effective_message.reply_text("Ți-am anulat modificările, dacă ai făcut vreuna.")
		return ConversationHandler.END


	def make_county_reply_markup(self, update, context):
		county_buttons = []
		butt = []
		for k, v in self.counties.items():
			if "strain" not in v["name"].lower():
				button_text = v["name"]
				if "counties" in context.user_data["temp"] and k in context.user_data["temp"]["counties"]:
					button_text += " ✅"
				butt.append(InlineKeyboardButton(button_text, callback_data=k))
				if len(butt) == 2:
					county_buttons.append(copy.copy(butt))
					butt.clear()
		return InlineKeyboardMarkup(county_buttons)

	def make_vaccine_reply_markup(self, update, context):
		county_buttons = []
		butt = []
		for k, v in self.vaccines.items():
			button_text = v
			if "vaccines" in context.user_data["temp"] and k in context.user_data["temp"]["vaccines"]:
				button_text += " ✅"
			butt.append(InlineKeyboardButton(button_text, callback_data=k))
			if len(butt) == 1:
				county_buttons.append(copy.copy(butt))
				butt.clear()
		return InlineKeyboardMarkup(county_buttons)

	def select_button_county(self, update, context):
		try:
			query = update.callback_query
			query.answer()
			countyID = int(query.data)
			assert countyID in self.counties
	
			if "counties" not in context.user_data["temp"]:
				context.user_data["temp"]["counties"] = dict({ countyID: True })
			else:
				if countyID not in context.user_data["temp"]["counties"]:
					context.user_data["temp"]["counties"][countyID] = True
				else:
					del context.user_data["temp"]["counties"][countyID]

			query.edit_message_reply_markup(reply_markup=self.make_county_reply_markup(update, context))
		except Exception as err:
			query.edit_message_text(text=f"A apărut o eroare, contactează adminul (@talania) și spune-i:\n"
				f"{type(err)} in select_button\n"
				"Scz.")
			self.logging_queue.put(f"{datetime.now().strftime(self.format)} TelegramInterface: {traceback.format_exc()}")
			self.logging_queue.put(f"{str(err)}")
			return self.cancel(update, context)

	def select_button_vaccine(self, update, context):
		try:
			query = update.callback_query
			query.answer()
			countyID = int(query.data)

			vaxID = int(query.data)
			assert vaxID in self.vaccines
	
			if "vaccines" not in context.user_data["temp"]:
				context.user_data["temp"]["vaccines"] = dict({ vaxID: True })
			else:
				if vaxID not in context.user_data["temp"]["vaccines"]:
					context.user_data["temp"]["vaccines"][vaxID] = True
				else:
					del context.user_data["temp"]["vaccines"][vaxID]

			query.edit_message_reply_markup(reply_markup=self.make_vaccine_reply_markup(update, context))
		except Exception as err:
			query.edit_message_text(text=f"A apărut o eroare, contactează adminul (@talania) și spune-i:\n"
				f"{type(err)} in select_button\n"
				"Scz.")
			self.logging_queue.put(f"{datetime.now().strftime(self.format)} TelegramInterface: {traceback.format_exc()}")
			self.logging_queue.put(f"{str(err)}")
			return self.cancel(update, context)

	def validate_n_prelucrate_args(self, update, context):
		def valid(element, token):
			if token == "-v" and element.upper() in self.reverse_counties:
				return True
			if token == "-j" and element.isnumeric():
				return True
			return False
		def split(lst, token):
			i = 0
			while i < len(lst) and lst[i] != token and valid(lst[i], token):
				yield lst[i]
				i += 1
		try:
			args = context.args
			counties = []
			vaccines = dict()
			if len(args) > 0:
				if args[0] == "-j":
					counties = [self.reverse_counties[j.upper()] for j in split(args[1:], "-v")]
					for vax in args[len(counties)+2:]:
						vaccines[int(vax)] = self.vaccines[int(vax)]
				elif args[0] == "-v":
					for vax in split(args[1:], "-j"):
						vaccines[int(vax)] = self.vaccines[int(vax)]
					counties = [self.reverse_counties[j.upper()] for j in args[len(vaccines)+2:]]
				else:
					counties = [self.reverse_counties[j.upper()] for j in args]
			if len(counties) == 0 and "counties" in context.user_data:
				counties = [j for j in context.user_data["counties"]]
			if len(vaccines) == 0 and "vaccines" in context.user_data:
				for v in context.user_data["vaccines"]:
					vaccines[v] = self.vaccines[int(v)]
			if len(counties) == 0:
				raise ValueError("Nu ai județe selectate!")
			if len(vaccines) == 0:
				raise ValueError("Nu ai vaccinuri selectate!")
			return (counties, vaccines)
		except:
			raise

	def validate_n_prelucrate_state(self, update, context):
		if "counties" in context.user_data and len(context.user_data["counties"]):
			counties = [key for key in context.user_data["counties"]]
		else:
			raise ValueError("Nu ai județe selectate!")
		if "vaccines" in context.user_data and len(context.user_data["vaccines"]):
			vaccines = dict()
			for vax in context.user_data["vaccines"]:
				vaccines[int(vax)] = self.vaccines[int(vax)]
		else:
			raise ValueError("Nu ai vaccinuri selectate!")
		return (counties, vaccines)

	def get_county_slots(self, update, context):
		try:
			if (len(context.args) > 0):
				counties, vaccines = self.validate_n_prelucrate_args(update, context)
			else: 
				counties, vaccines = self.validate_n_prelucrate_state(update, context)

			done_msg = self.manager.Value(str, None)
			self.get_queue.put((counties, vaccines, done_msg))
			#logging.info(self.c.dictionary[self.validate_n_prelucrate(context.args)[0]])
			while done_msg.value == None:
				pass

			i = 0
			full_msg = str(done_msg.value)
			while i < len(full_msg):
				last_enter = full_msg[i:min(len(full_msg), i+4096)].rfind("\n")
				update.effective_message.reply_text(full_msg[i:i+last_enter])
				i += last_enter + 1
		except KeyError:
			try:
				update.effective_message.reply_text("Ai introdus greșit prescurtarea unui județ! Verifică din nou.")
			except:
				pass
		except ValueError as e:
			try:
				update.effective_message.reply_text(str(e))
			except:
				pass
		except Exception as e:
			self.logging_queue.put(traceback.format_exc())

	def alerts_listener(self, bot, alerts_dict):
		self.logging_queue.put(f"INTERFACE: print alerts {os.getpid()}")
		while True:
			county, vaccine, added_slots, msg = self.alerts_queue.get()
			if added_slots != -1:
				header = f"🚨🚨{added_slots} <b>LOCURI NOI DE VACCINARE!\n🚨🚨{self.counties[county]['name'].upper()} - {self.vaccines[vaccine].upper()}</b>\n\n"
			else:
				header = f"🚨🚨<b>CENTRU NOU DE VACCINARE!\n🚨🚨{self.counties[county]['name'].upper()} - {self.vaccines[vaccine].upper()}</b>\n\n"
			msg = header + msg
			for chat_id in dict(alerts_dict[county][vaccine]):
				bot.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
#			bot.send_message(248916262, msg, parse_mode=ParseMode.HTML)

	def sleeping_killer(self):
		self.logging_queue.put(f"INTERFACE: killer {os.getpid()}")
		with self.killing_condition:
			self.killing_condition.wait()
			self.save_alerts()
			self.logging_queue.put("saved alerts file")
			os.kill(self.alerts_proc.pid, signal.SIGKILL)
			os.kill(self.announcement_proc.pid, signal.SIGKILL)
		os.kill(os.getpid(), signal.SIGKILL)

if __name__ == "__main__":
	try:
		ti = TelegramInterface()
	except Exception as e:
		ti.logging_queue.put(f"{datetime.now().strftime(self.format)} TelegramInterface: {traceback.format_exc()}")
