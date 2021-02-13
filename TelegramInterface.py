from telegram import (
	InlineKeyboardMarkup,
	InlineKeyboardButton,
	ReplyKeyboardMarkup,
	ReplyKeyboardRemove,
	Update,
	ParseMode
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
ALERTS, COUNTIES, VACCINES = range(3)

class TelegramInterface:
	def __init__(self):
		self.updater = Updater("")
		self.dispatcher = self.updater.dispatcher
		conv_handler = ConversationHandler(entry_points=[CommandHandler('preferinte', self.preferences)], 
			states={
				ALERTS: [
					MessageHandler(Filters.regex('^(da|dA|Da|DA)$'), self.alerts),
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
					CommandHandler("gata", self.end_state_handler)
				]
			}, fallbacks=[CommandHandler('anuleaza', self.cancel)],
			)
		self.dispatcher.add_handler(conv_handler)
		self.dispatcher.add_handler(CommandHandler("start", self.start))
		self.dispatcher.add_handler(CommandHandler("vezi", self.get_county_slots))

		self.manager = Manager()
		self.get_queue = JoinableQueue()
		self.c = Controller(session_cookie="MmMzYjdlZTMtYTE2My00NjcwLWIwYzQtNDgzNDc5YjY2YWY4",
				interface_queue=self.get_queue, verbose=False)
		self.counties = self.c.get_dictionary()
		self.reverse_counties = self.reverse_counties()
		self.vaccines = self.c.get_vaccines()

		self.updater.start_polling()
		self.updater.idle()
		self.c.join()

	def reverse_counties(self):
		reverse_counties = dict()
		for county_key, county_val in dict(self.c.dictionary).items():
			reverse_counties[county_val["shortName"]] = county_key
		return reverse_counties

	def start(self, update, context):
		update.message.reply_text(
			'Beep beep boop, sunt doar un robot. Uite ce știu să fac:'
		)
		update.message.reply_text(
			'    /preferinte: reglează-ți preferințele de vaccinare\n\n'
		)
		update.message.reply_text(
			'    /vezi [-j id_judet] [-v id_vaccin]: vezi situatia locurilor libere\n'
			'      dacă ai preferințele reglate, "/vezi" îți arată locuri conform preferințelor\n'
			'      dacă nu ai preferințele reglate, "/vezi" îți arată toate locurile din țară\n'
			'        pt. a limita numărul rezultatelor, poti adauga parametrii optionali -j sau -v\n'
			'		   -j: rezultate doar din judetele alese, -v: doar vaccinurile alese\n\n'
			'      ex.: "/vezi -j CL AB IF -v 1 3" va intoarce toate locurile pt. BioNTech sau AstraZeneca din Călărași, Alba sau Ilfov\n\n'
			'	   notă: parametrii opționali id_judet și id_vaccin au prioritate în fața preferințelor\n\n'
			'      legendă:\n     id_judet: codurile auto ale judetelor\n'
			'     id_vaccin: BioNTech=1, Moderna=2, AstraZeneca=3\n\n'
		)
		update.message.reply_text(
			'	/alerte: va urma...',
		)
		return

	def cancel(self, update, context):
		return

	def preferences(self, update, context):
		reply_options = [['Da', 'Nu']]
		update.message.reply_text(
			#'Salut! Vrei să primești alerte în timp real în legătură cu situația locurilor noi la vaccinuri?\n'
			'Vrei să îți reglezi preferințele de vaccinuri?\n'
			'Scrie /anuleaza pentru a încheia conversația cu mine.\n',
			reply_markup=ReplyKeyboardMarkup(reply_options, one_time_keyboard=True),
		)
		return ALERTS

	def alerts(self, update, context):
		logging.info(update.message.text)
		context.user_data["updates"] = True

		update.message.reply_text('În ce județe te interesează să găsești loc de vaccinare?', 
			reply_markup=self.make_county_reply_markup(update, context))
		update.message.reply_text('Apasă pe numele județelor care te interesează. Apasă încă o dată pentru a deselecta.\n'
			'Când ai terminat de selectat, apasă aici: /gata')
		return COUNTIES

	def counties2vaccines_handler(self, update, context):
		logging.info("ZAHAR VANILAT")
		context.user_data["vaccines"] = dict()
		for vax in self.vaccines:
			context.user_data["vaccines"][vax] = True

		update.message.reply_text('Stocurile căror vaccinuri vrei să le urmărești?', 
			reply_markup=self.make_vaccine_reply_markup(update, context))
		update.message.reply_text('Apasă pentru a deselecta.\n'
			'Când ai terminat de selectat, apasă aici: /gata')
		update.message.reply_text('<b>ATENȚIE</b>:\nÎn România, vaccinul AstraZeneca <b>nu</b> se administrează persoanelor '
			'în vârstă de 55 de ani sau mai mult!\n', parse_mode=ParseMode.HTML)
		return VACCINES

	def end_state_handler(self, update, context):
		update.message.reply_text("This is the end!")
		return ConversationHandler.END

	def make_county_reply_markup(self, update, context):
		county_buttons = []
		butt = []
		for k, v in self.counties.items():
			if "strain" not in v["name"].lower():
				button_text = v["name"]
				if "counties" in context.user_data and k in context.user_data["counties"]:
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
			if "vaccines" in context.user_data and k in context.user_data["vaccines"]:
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
	
			if "counties" not in context.user_data:
				context.user_data["counties"] = dict({ countyID: True })
			else:
				if countyID not in context.user_data["counties"]:
					context.user_data["counties"][countyID] = True
				else:
					del context.user_data["counties"][countyID]

			logging.info(context.user_data["counties"])
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
	
			if "vaccines" not in context.user_data:
				context.user_data["vaccines"] = dict({ vaxID: True })
			else:
				if vaxID not in context.user_data["vaccines"]:
					context.user_data["vaccines"][vaxID] = True
				else:
					del context.user_data["vaccines"][vaxID]

			logging.info(context.user_data["vaccines"])
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