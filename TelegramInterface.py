# TODO:
#
#	Alerting system...
#
#	Make a new bot, CovidVaxMaster, which gives you on-the-fly control over
#		debugging the main bot
#	It should:
#		be the logging interface for all the exceptions raised by the main bot
#			(it sends you a message every time there's an exception)
#		be able to remotely inject:
#			new session cookies
#			new vaccines!!!!;
#				and edit vaccine IDs in case what was inserted was wrong
#		be able to output messages on the main bot's chat
#			("Hi, admin speaking. There will be some maintenanace to the bot tomorrow. Thx!")
#		be able to SIGKILL from a distance
#	All from a dedicated chat of its own, which you can easily control even from your phone.
#
#	PERSISTENT STORAGE OF USER DATA!!!!
#
#	When editing preferences:
#		edit A COPY of context.user_data !!!
#		which you write over the original iff user doesn't cancel the action!!!
#
#	Tidy everything up, don't repeat yourself etc...

from telegram import (
	InlineKeyboardMarkup,
	InlineKeyboardButton,
	ReplyKeyboardMarkup,
	ReplyKeyboardRemove,
	Update,
	ParseMode,
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
from multiprocessing import Manager, JoinableQueue, Process
from Controller import Controller
import logging
import time
import copy

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
INITIAL, COUNTIES, VACCINES, ALERTS = range(4)

class TelegramInterface:
	def __init__(self):
		self.updater = Updater("")
		self.dispatcher = self.updater.dispatcher
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
					MessageHandler(Filters.regex('^(nu|nU|Nu|NU)$'), self.end_state_handler)
				]
			}, fallbacks=[CommandHandler('anuleaza', self.cancel)],
			)
		self.dispatcher.add_handler(conv_handler)
		self.dispatcher.add_handler(CommandHandler("start", self.help))
		self.dispatcher.add_handler(CommandHandler("ajutor", self.help))
		self.dispatcher.add_handler(CommandHandler("ce_preferinte_am", self.get_preferences))
		self.dispatcher.add_handler(CommandHandler("alerte", self.switch_and_update_alerts_dict))
		self.dispatcher.add_handler(CommandHandler("vezi", self.get_county_slots))

		self.manager = Manager()
		self.get_queue = JoinableQueue()
		self.c = Controller(session_cookie="OGVhN2YzNTctM2ZmMi00MWNiLTkyMjktMmNkMmUwM2NhNzJm",
				interface_queue=self.get_queue, verbose=False)
		self.counties = self.c.get_dictionary()
		self.reverse_counties = self.reverse_counties()
		self.vaccines = self.c.get_vaccines()

		self.alerts_dict = self.create_or_load_alerts()
		self.updater.start_polling()
		self.updater.idle()
		self.c.join()

	def reverse_counties(self):
		reverse_counties = dict()
		for county_key, county_val in dict(self.c.dictionary).items():
			reverse_counties[county_val["shortName"]] = county_key
		return reverse_counties

	def create_or_load_alerts(self):
		# TODO: load from persistent storage
		alerts = dict()
		for c in self.counties:
			alerts[c] = dict()
			for v in self.vaccines:
				alerts[c][v] = dict()
		return alerts

	def help(self, update, context):
		update.message.reply_text(
			'Beep beep boop, sunt doar un robot. Uite ce știu să fac:'
		)
		update.message.reply_text(
			'    /preferinte: reglează-ți preferințele de vaccinare\n\n'
		)
		update.message.reply_text(
			'	/ce_preferinte_am: vezi preferințele asociate contului tău\n\n'
		)
		update.message.reply_text(
			'	/alerte: pornește-ți sau oprește-ți alertele\n\n'
		)
		update.message.reply_text(
			'    /vezi [-j id_judet] [-v id_vaccin]: vezi situatia locurilor libere\n'
			'      dacă ai preferințele reglate, "/vezi" îți arată locuri conform preferințelor\n'
			'      dacă nu ai preferințele reglate, "/vezi" îți arată toate locurile din țară\n'
			'        pt. a limita numărul rezultatelor, poti adauga parametrii optionali -j sau -v\n'
			'		   -j: rezultate doar din județele alese, -v: doar vaccinurile alese\n\n'
			'      ex.: "/vezi -j CL AB IF -v 1 3" va intoarce toate locurile pt. BioNTech sau AstraZeneca din Călărași, Alba sau Ilfov\n\n'
			'	   notă: parametrii opționali id_judet și id_vaccin au prioritate în fața preferințelor\n\n'
			'      legendă:\n     id_judet: codurile auto ale judetelor\n'
			'     id_vaccin: BioNTech=1, Moderna=2, AstraZeneca=3\n\n'
		)
		update.message.reply_text(
			'	/ajutor: afișează exact acest mesaj'
		)
		return

	def get_preferences(self, update, context):
		if "counties" not in context.user_data or len(context.user_data["counties"]) == 0:
			update.message.reply_text(
			'🇷🇴🇷🇴\nNu ai selectat niciun județ pe care îl urmărești.\n'
			'În mod implicit, vezi rezultatele de la nivel național.'
		)
		else:
			update.message.reply_text(
			'🇷🇴🇷🇴\nUrmărești județele: ' + 
			' '.join([self.counties[judetID]["name"] for judetID in context.user_data["counties"]])
			)
		if "vaccines" not in context.user_data or len(context.user_data["vaccines"]) == 0:
			update.message.reply_text(
			'💉💉\nNu ai selectat niciun vaccin pe care îl urmărești.\n'
			'În mod implicit, vezi rezultatele pentru toate vaccinurile din România.'
		)
		else:
			update.message.reply_text(
			'💉💉\nUrmărești vaccinurile: ' + 
			' '.join([self.vaccines[vaccinID] for vaccinID in context.user_data["vaccines"]])
			)
		if "alerts" not in context.user_data or context.user_data["alerts"] == False:
			update.message.reply_text(
			'🚨🚨 ❌❌\nNu ești abonat la alerte.'
			'Dacă vrei să te abonezi, scrie /alerte.'
			)
		else:
			update.message.reply_text(
			'🚨🚨 ✅✅\nEști abonat la alerte.\n'
			'Dacă vrei să te dezabonezi, scrie /alerte.'
			)
		update.message.reply_text(
			'	Vrei să schimbi setările? Apelează /preferinte!'
		)

	def preferences(self, update, context):
		context.user_data["temp"] = copy.deepcopy(context.user_data)
		reply_options = [['Da', 'Nu']]
		update.message.reply_text(
			#'Salut! Vrei să primești alerte în timp real în legătură cu situația locurilor noi la vaccinuri?\n'
			'Vrei să îți reglezi preferințele de vaccinuri?\n'
			'Scrie /anuleaza dacă nu mai vrei să continui.\n',
			reply_markup=ReplyKeyboardMarkup(reply_options, one_time_keyboard=True),
		)
		return INITIAL

	def get_counties(self, update, context):
		logging.info(update.message.text)
		context.user_data["temp"]["updates"] = True

		update.message.reply_text('🇷🇴🇷🇴 În ce județe te interesează să găsești loc de vaccinare?', 
			reply_markup=self.make_county_reply_markup(update, context))
		update.message.reply_text('Apasă pe numele județelor care te interesează. Apasă încă o dată pentru a deselecta.')
		update.message.reply_text(
			'Când ai terminat de selectat, apasă aici: /gata\n'
			'Sau scrie /anuleaza dacă nu mai vrei să continui.\n')
		return COUNTIES

	def counties2vaccines_handler(self, update, context):
		logging.info(context.user_data)
		logging.info(context)
		context.user_data["temp"]["vaccines"] = dict()
		for vax in self.vaccines:
			context.user_data["temp"]["vaccines"][vax] = True

		update.message.reply_text('💉💉 Stocurile căror vaccinuri vrei să le urmărești?', 
			reply_markup=self.make_vaccine_reply_markup(update, context))
		update.message.reply_text('Apasă pentru a deselecta.\n')
		update.message.reply_text('<b>ATENȚIE</b>:\nÎn România, vaccinul AstraZeneca <b>nu</b> se administrează persoanelor '
			'în vârstă de 55 de ani sau mai mult!\n', parse_mode=ParseMode.HTML)
		update.message.reply_text(
			'Când ai terminat de selectat, apasă aici: /gata\n'
			'Sau scrie /anuleaza dacă nu mai vrei să continui.\n')
		return VACCINES

	def vaccines2alerts_handler(self, update, context):
		reply_options = [["Da", "Nu"]]
		if "alerts" not in context.user_data or context.user_data["alerts"] == False:
			update.message.reply_text(
				'🚨🚨 ❌❌\nÎn acest moment <b>NU EȘTI ABONAT</b> la alerte despre situația vaccinurilor'
				' care corespund preferințelor tale.',
				parse_mode=ParseMode.HTML
			), 
			update.message.reply_text(
				'Vrei să te abonezi?',
				reply_markup=ReplyKeyboardMarkup(reply_options, one_time_keyboard=True),
			)
		else:
			update.message.reply_text(
				'🚨🚨 ✅✅\nEști <b>ABONAT</b> la alerte despre situația vaccinurilor'
				' care corespund preferințelor tale.',
				parse_mode=ParseMode.HTML
			), 
			update.message.reply_text(
				'Vrei să te dezabonezi?',
				reply_markup=ReplyKeyboardMarkup(reply_options, one_time_keyboard=True),
			)
		return ALERTS

	def switch_and_update_alerts_dict(self, update, context):
		if "temp" in context.user_data:
			# "alerts" was called from the preferences conversation handler
			# if so, only switch state, and let end_state_handler do the updating
			user_data = context.user_data["temp"]
			if "alerts" not in user_data:
				user_data["alerts"] = True
			else:
				user_data["alerts"] = not user_data["alerts"]
			return self.end_state_handler(update, context)


		user_data = context.user_data
		if "counties" not in user_data and "vaccines" not in user_data:
			update.message.reply_text("Nu te poți abona la alerte dacă nu îți setezi preferințele. Apelează /preferinte.")
			return

		if "alerts" not in user_data:
			user_data["alerts"] = True
			alerts_value = True
		else:
			alerts_value  = user_data["alerts"]
			alerts_value  = not alerts_value
			user_data["alerts"] = alerts_value

		chat_id = update.message.chat_id
		if alerts_value == True:
			for judetID in self.counties:
				for vaccineID in self.vaccines:
					logging.info(f"j {judetID} v {vaccineID} c {chat_id}")
					self.alerts_dict[judetID][vaccineID][chat_id] = True
			update.message.reply_text(
				'🚨🚨✅✅ Ai <b>PORNIT</b> alertele.',
				parse_mode=ParseMode.HTML
			)
		else:
			for judetID in self.counties:
				for vaccineID in self.vaccines:
					if update.message.chat_id in self.alerts_dict[judetID][vaccineID]:
						del self.alerts_dict[judetID][vaccineID][chat_id]
			update.message.reply_text(
				'🚨🚨❌❌ Ai <b>OPRIT</b> alertele.',
				parse_mode=ParseMode.HTML
			)

		logging.info(self.alerts_dict)
		update.message.reply_text("Îți poți vedea toate preferințele apelând /ce_preferinte_am.")


	def end_state_handler(self, update, context):
		reference = context.user_data["temp"]

		chat_id = update.message.chat_id
		if "counties" in context.user_data:
			for judetID in self.counties:
				for vaccineID in self.vaccines:
					logging.info(f'j {judetID} v {vaccineID} not in counties {judetID not in reference["counties"]} not in vaccines {vaccineID not in reference["vaccines"]} chat in dict {chat_id in self.alerts_dict[judetID][vaccineID]}')
					if judetID not in reference["counties"] or vaccineID not in reference["vaccines"] and chat_id in self.alerts_dict[judetID][vaccineID]:
							del self.alerts_dict[judetID][vaccineID][chat_id]
		
		if "alerts" in reference:
			if reference["alerts"] == True:
				if 'counties' in reference and len(reference['counties']):
					counties = reference["counties"]
				else:
					counties = self.counties
				if 'vaccines' in reference and len(reference['vaccines']):
					vaccines = reference["vaccines"]
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

		logging.info(self.alerts_dict)

		for key, val in reference.items():
			context.user_data[key] = val
		del context.user_data["temp"]
		del reference
		update.message.reply_text("Ți-am salvat preferințele. Le poți revedea oricând apelând /ce_preferinte_am.")
		return ConversationHandler.END

	def cancel(self, update, context):
		del context.user_data["temp"]
		update.message.reply_text("Ți-am anulat modificările, dacă ai făcut vreuna.")
		return ConversationHandler.END


	def make_county_reply_markup(self, update, context):
		county_buttons = []
		butt = []
		for k, v in self.counties.items():
			if "strain" not in v["name"].lower():
				button_text = v["name"]
				if "counties" in context.user_data["temp"] and k in context.user_data["temp"]["counties"]:
					logging.info(k)
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
				logging.info(k)
				button_text += " ✅"
			butt.append(InlineKeyboardButton(button_text, callback_data=k))
			if len(butt) == 1:
				county_buttons.append(copy.copy(butt))
				butt.clear()
		return InlineKeyboardMarkup(county_buttons)

	def select_button_county(self, update, context):
		query = update.callback_query
		query.answer()
		try:
			countyID = int(query.data)
			logging.info(self.counties)
			logging.info(countyID)
			assert countyID in self.counties
	
			if "counties" not in context.user_data["temp"]:
				context.user_data["temp"]["counties"] = dict({ countyID: True })
			else:
				if countyID not in context.user_data["temp"]["counties"]:
					context.user_data["temp"]["counties"][countyID] = True
				else:
					del context.user_data["temp"]["counties"][countyID]

			logging.info(context.user_data["temp"]["counties"])
			query.edit_message_reply_markup(reply_markup=self.make_county_reply_markup(update, context))
		except AssertionError as err:
			query.edit_message_text(text=f"A apărut o eroare, contactează adminul și spune-i:\n"
				f"{type(err)} in select_button\nScrie /start pentru a reporni botul.\n"
				"Scz.")

	def select_button_vaccine(self, update, context):
		logging.info("FORZA STEAUA HEI")
		query = update.callback_query
		query.answer()
		try:
			countyID = int(query.data)
			logging.info("cplm")
			logging.info(self.vaccines)
			vaxID = int(query.data)
			assert vaxID in self.vaccines
	
			if "vaccines" not in context.user_data["temp"]:
				context.user_data["temp"]["vaccines"] = dict({ vaxID: True })
			else:
				if vaxID not in context.user_data["temp"]["vaccines"]:
					context.user_data["temp"]["vaccines"][vaxID] = True
				else:
					del context.user_data["temp"]["vaccines"][vaxID]

			logging.info(context.user_data["temp"]["vaccines"])
			query.edit_message_reply_markup(reply_markup=self.make_vaccine_reply_markup(update, context))
		except AssertionError as err:
			query.edit_message_text(text=f"A apărut o eroare, contactează adminul și spune-i:\n"
				f"{type(err)} in select_button\nScrie /start pentru a reporni botul.\n"
				"Scz.")

	def validate_n_prelucrate_args(self, args):
		def split(lst, token):
			i = 0
			while i < len(lst) and lst[i] != token:
				yield lst[i]
				i += 1
		try:
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
			if len(counties) == 0:
				counties = [i for key, i in self.reverse_counties.items()]
			if len(vaccines) == 0:
				vaccines = self.vaccines
			return (counties, vaccines)
		except:
			raise

	def validate_n_prelucrate_state(self, update, context):
		if "counties" in context.user_data:
			counties = [key for key in context.user_data["counties"]]
		else:
			counties = [i for key, i in self.reverse_counties.items()]
		if "vaccines" in context.user_data:
			vaccines = dict()
			for vax in context.user_data["vaccines"]:
				vaccines[int(vax)] = self.vaccines[int(vax)]
		else:
			vaccines = self.vaccines()
		return (counties, vaccines)

	def get_county_slots(self, update, context):
		try:
			if (len(context.args) > 0) or (("counties" not in context.user_data 
				or len(context.user_data["counties"]) == 0)
					and ("vaccines" not in context.user_data or len(context.user_data["vaccines"]) == 0)):

					counties, vaccines = self.validate_n_prelucrate_args(context.args)
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
				update.message.reply_text(full_msg[i:i+last_enter])
				i += last_enter + 1
		except KeyError:
			update.message.reply_text("Ai introdus greșit prescurtarea unui județ! Verifică din nou.")


if __name__ == "__main__":
	TelegramInterface()