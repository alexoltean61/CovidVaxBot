import requests
import json
import time
from datetime import datetime
import copy
import logging
import signal
import sys
import traceback
import os
import pickle
from collections import OrderedDict
from multiprocessing import Queue, Process

class Crawler:
	def __init__(self, session_cookie=None, working_dict=None, vaccines=None, main_URL=None, auth_URL=None, counties_URL=None, headers=None, payload=None, updated=None, new_slots=None, new_slots_condition=None, alert_treshold=0.33, logging_queue=None, verbose=False):
		self.read_config()
		if logging_queue != None:
			self.logging_queue = logging_queue
			self.format = "%Y-%m-%d %H:%M:%S"
		else:
			self.logging_queue = Queue()
		if session_cookie != None:
			self.session_cookie = {"SESSION": session_cookie}
		if vaccines != None:
			self.vaccines = vaccines
		if main_URL != None:
			self.main_URL = main_URL
		if counties_URL != None:
			self.counties_URL = counties_URL
		if auth_URL != None:
			self.auth_URL = auth_URL
		if headers != None:
			self.headers = headers
		if payload != None:
			self.payload = payload
		self.verbose = verbose
		self.working_updated = updated
		self.sleep_time = 15
		self.new_slots = new_slots
		self.new_slots_condition = new_slots_condition
		self.alert_treshold = alert_treshold
		self.history = OrderedDict()
		if working_dict == None:
			self.main_dict = dict()
			self.working_dict = None
			self.get_counties()
		else:
			self.main_dict = dict()
			self.working_dict = working_dict

	def read_config(self):
		file = open("config.init", "r")
		config = file.readlines()
		self.session_cookie = {"SESSION": config[0][:-1]}
		self.vaccines = json.loads(config[1])
		self.vaccines = {int(k):v for k, v in self.vaccines.items()}
		self.main_URL = config[2][:-1]
		self.counties_URL = config[3][:-1]
		self.auth_URL = config[4][:-1]
		self.headers = json.loads(config[5])
		self.payload = json.loads(config[6])
		file.close()

	def work(self):
		self.logging_queue.put(f"CRAWLER {os.getpid()}")
		last_saved_history = datetime.now()
		while True:
			self.main_dict = self.get_slots(0)
			self.last_updated = datetime.now()
			self.history[self.last_updated.strftime(self.format)] = copy.deepcopy(self.main_dict)
			if self.working_updated != None:
				self.working_updated.value = self.last_updated.timestamp()
			if self.working_dict != None:
				self.copy_main_to_working_dict()
				#with self.new_slots_condition:
				#	del self.new_slots[:]
			if (self.last_updated - last_saved_history).total_seconds() > 14400:
				self.dump_history()
				last_saved_history = self.last_updated
				self.logging_queue.put("CRAWLER: saved history!")
			self.cleanup_and_print(self.verbose)
			time.sleep(self.sleep_time)

	def dump_history(self):
		with open("history/" + str(self.last_updated), "wb") as file:
			pickle.dump(self.history, file)
		self.history = OrderedDict()

	def cleanup_and_print(self, verbose):
		if verbose == False:
			for county in self.main_dict:
				for vaccine_key, vaccine_name in self.vaccines.items():
					county_vaccine_slots = self.main_dict[county][vaccine_name]
					for centre in county_vaccine_slots["centres"]:
						centre_dict = county_vaccine_slots["centres"][centre]
						if centre_dict['waitingListSize'] != 0:
							centre_dict['waitingListSize'] = 0
						if centre_dict['availableSlots'] != 0:
							centre_dict['availableSlots'] = 0
					county_vaccine_slots['waitingListSize'] = 0
					county_vaccine_slots['availableSlots'] = 0
				self.main_dict[county]['waitingListSize'] = 0
				self.main_dict[county]['availableSlots'] = 0
				#self.update_history(free)
			return

		free = 0
		waiting = 0
		for county in self.main_dict:
			print(f"{self.main_dict[county]['name']} - {self.main_dict[county]['availableSlots']} libere, {self.main_dict[county]['waitingListSize']} în așteptare:")
			for vaccine_key, vaccine_name in self.vaccines.items():
				county_vaccine_slots = self.main_dict[county][vaccine_name]
				print(f"\tVaccin {vaccine_name} - {county_vaccine_slots['availableSlots']} libere, {county_vaccine_slots['waitingListSize']} în așteptare:")
				for centre in county_vaccine_slots["centres"]:
					centre_dict = county_vaccine_slots["centres"][centre]
					if centre_dict['waitingListSize'] != 0:
						print(f"\t\t{centre_dict['name']}, localitate {centre_dict['localityName']}, în așteptare: {centre_dict['waitingListSize']}")
						waiting += centre_dict['waitingListSize']
						centre_dict['waitingListSize'] = 0
					if centre_dict['availableSlots'] != 0:
						print(f"\t\t{centre_dict['name']}, localitate {centre_dict['localityName']}, {centre_dict['availableSlots']} locuri libere")
						free += centre_dict['availableSlots']
						centre_dict['availableSlots'] = 0
				county_vaccine_slots['waitingListSize'] = 0
				county_vaccine_slots['availableSlots'] = 0
			countyName = self.main_dict[county]['shortName']
			self.main_dict[county]['waitingListSize'] = 0
			self.main_dict[county]['availableSlots'] = 0
		print(f"Total libere țară: {free}")
		print(f"Total în așteptare țară: {waiting}")
		print(f"Ultima actualizare: {self.last_updated}\n")


	def check_and_load_response(self, URL, method="POST"):
		if method == "GET":
			response = requests.get(URL, json=self.payload, cookies=self.session_cookie, headers=self.headers, timeout=8)
		else:
			response = requests.post(URL, json=self.payload, cookies=self.session_cookie, headers=self.headers, timeout=8)
		if response.url == self.auth_URL:
			raise requests.exceptions.InvalidHeader("Session cookie expired!")
		if response.url == "https://vaccinare-covid.gov.ro":
			raise requests.exceptions.HTTPError(f"Website redirects to homepage!")
		if response.status_code != 200:
			raise requests.exceptions.HTTPError(f"URL {URL}, status {response.status_code}")
		return response.content

	def get_counties(self):
		try:
			self.logging_queue.put("crawler trying to get")
			content = self.check_and_load_response(self.counties_URL, method="GET")
			self.logging_queue.put(str(content))
			json_response = json.loads(content)
			for county in json_response:
				if "trainatate" in county["name"]:
					continue
				self.main_dict[county["countyID"]] = {"shortName": county["shortName"], "name": county["name"], 'waitingListSize': 0, 'availableSlots': 0}
				for vax_key, vax_name in self.vaccines.items():
					self.main_dict[county["countyID"]][vax_name] = {"centres": dict(), 'waitingListSize': 0, 'availableSlots': 0}
				if self.working_dict != None:
					self.working_dict[county["countyID"]] = copy.deepcopy(self.main_dict[county["countyID"]])
		except Exception as err:
			self.logging_queue.put(f"{datetime.now().strftime(self.format)} get_counties: {traceback.format_exc()}")
			self.logging_queue.put(f"{datetime.now().strftime(self.format)} get_counties: Retrying...\n")
			time.sleep(self.sleep_time * 2)
			self.read_config()
			self.get_counties()


	def get_slots(self, page):
		try:
			content = self.check_and_load_response(self.main_URL + "?page=" + str(page) + "&size=20&sort=,")
			json_response = json.loads(content)

			for centre in json_response["content"]:
				vaccineName = self.vaccines[centre["boosterID"]]
				vaccine_entry = self.main_dict[centre['countyID']][vaccineName]
				availableSlots  = centre['availableSlots']
				waitingListSize = centre['waitingListSize']
				#print(f"{centre['countyName']}: {centre['name']}, {centre['localityName']}, vaccin {vaccineName} locuri {centre['waitingListSize']}, asteptare {centre['waitingListSize']}")
				if centre['code'] not in vaccine_entry['centres']:
					vaccine_entry["centres"][centre['code']] = {"ID": centre['code'], "name": centre['name'], "localityName": centre['localityName'], "waitingListSize": waitingListSize, "availableSlots": availableSlots}
					self.main_dict[centre['countyID']]['waitingListSize'] += waitingListSize
					self.main_dict[centre['countyID']]['availableSlots']  += availableSlots
					vaccine_entry['waitingListSize'] += waitingListSize
					vaccine_entry['availableSlots']  += availableSlots
				else:
					nullWaiting = (vaccine_entry['centres'][centre['code']]['waitingListSize'] == 0)
					nullAvailable = (vaccine_entry['centres'][centre['code']]['availableSlots'] == 0)
					if nullWaiting:
						vaccine_entry['waitingListSize'] += waitingListSize
						self.main_dict[centre['countyID']]['waitingListSize'] += waitingListSize
					if nullAvailable:
						vaccine_entry['availableSlots']  += availableSlots
						self.main_dict[centre['countyID']]['availableSlots']  += availableSlots
					if nullWaiting or nullAvailable:
						vaccine_entry["centres"][centre['code']] = {"ID": centre['code'], "name": centre['name'], "localityName": centre['localityName'], "waitingListSize": waitingListSize, "availableSlots": availableSlots}

			if json_response["last"] == True:
				return self.main_dict
			return self.get_slots(page+1)
		except requests.exceptions.ConnectionError as err:
				self.logging_queue.put(f"{datetime.now().strftime(self.format)} get_slots: {traceback.format_exc()}")
				self.logging_queue.put(f"{datetime.now().strftime(self.format)} get_slots: Retrying...\n")
				# if there is a connection error, START OVER FROM THE BEGINNING
				# 	because page may be updated as you crawl it, and that might cause the error
				self.cleanup_and_print(verbose=False)
				time.sleep(2*self.sleep_time)
				self.read_config()
				return self.get_slots(0)
		except Exception as err:
				self.logging_queue.put(f"{datetime.now().strftime(self.format)} get_slots: {traceback.format_exc()}")
				self.logging_queue.put(f"{datetime.now().strftime(self.format)} get_slots: Retrying...\n")
				time.sleep(2*self.sleep_time)
				self.read_config()
				return self.get_slots(page)

	def share_working_dict(self, dictionary):
		self.working_dict = dictionary

	def copy_main_to_working_dict(self):
		# check for changes
		with self.new_slots_condition:
			changed = False
			for county in self.main_dict:
				for vaccine_key, vaccine_name in self.vaccines.items():
					'''
					current_slots = self.main_dict[county][vaccine_name]["availableSlots"]
					old_slots = self.working_dict[county][vaccine_name]["availableSlots"]
					if current_slots > 0 and old_slots <= 100 and ((current_slots - old_slots) > self.alert_treshold * old_slots):
						self.new_slots.append((county, vaccine_key, current_slots - old_slots))
						changed = True
					'''
					for centre_key, centre in self.main_dict[county][vaccine_name]["centres"].items():
						if centre_key not in dict(self.working_dict[county][vaccine_name]["centres"]):
							self.new_slots.append((county, vaccine_key, centre['localityName'] + ": " + centre['name']))
							changed = True
			if changed == True:
				self.new_slots_condition.notify_all()


			# cleanup all of working_dict
			for county in dict(self.working_dict):
				for vaccine_key, vaccine_name in self.vaccines.items():
					county_vaccine_slots = self.working_dict[county][vaccine_name]
					for centre in dict(county_vaccine_slots["centres"]):
						centre_dict = county_vaccine_slots["centres"][centre]
						if centre_dict["availableSlots"] != 0:
							centre_dict["availableSlots"] = 0
							county_vaccine_slots["centres"][centre] = centre_dict
					county_vaccine_slots['availableSlots'] = 0
					self.working_dict[county][vaccine_name] = county_vaccine_slots
			self.working_dict[county]["availableSlots"] = 0

			# copy all of main_dict into working_dict
			for county in self.main_dict:
				for vaccine_key, vaccine_name in self.vaccines.items():
					county_vaccine_slots = self.main_dict[county][vaccine_name]
					for centre in dict(county_vaccine_slots["centres"]):
						self.working_dict[county][vaccine_name]["centres"][centre] = county_vaccine_slots["centres"][centre]
					self.working_dict[county][vaccine_name]['availableSlots'] = county_vaccine_slots['availableSlots']
			self.working_dict[county]["availableSlots"] = self.main_dict[county]["availableSlots"]

if __name__ == "__main__":
	Crawler(session_cookie="ZDljYzBlYjYtNTA1YS00MGM1LWFiMzAtMmYyYmUwY2NhYzI2", verbose=True).work()
# {"centerID":93,"currentDate":"13-02-2021 02:00:00.000","forBooster":true,"recipientID":1454918,"masterPersonnelCategoryID":-2,"boosterDays":21,"identificationCode":"2340111400428"}
