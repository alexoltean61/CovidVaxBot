from flask import Flask, request
from telegram.ext import Updater
from telegram import Update

class Server():
	def __init__(self, updater, token, host, port, ssl_context):
		self.app = Flask(token)
		self.updater = updater
		self.token   = token
		self.host    = host
		self.port    = port
		self.ssl_context = ssl_context
		self.app.add_url_rule(f"/{self.token}", endpoint=self.token, view_func=self.flask_handler, methods=["POST"])

	def start(self):
		self.app.run(host=self.host,
			port=self.port,
			debug=True,
			ssl_context=self.ssl_context,
			threaded=True)

	def flask_handler(self):
		update = Update.de_json(request.get_json(), self.updater.bot)
		try:
			self.updater.dispatcher.process_update(update)
		except:
			pass
		finally:
			return 'OK'
