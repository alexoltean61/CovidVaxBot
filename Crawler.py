import requests
import json
import time
from datetime import datetime
import copy
import logging

class Crawler:
	def __init__(self, session_cookie, working_dict=None, vaccines=None, main_URL=None, auth_URL=None, counties_URL=None, headers=None, payload=None, updated=None, verbose=False):
		self.session_cookie = {"SESSION": session_cookie}
		if verbose == True:
			logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

		if vaccines == None:
			vaccines = {1: "BioNTech", 2: "Moderna", 3: "AstraZeneca"}
		if main_URL == None:
			main_URL = "https://programare.vaccinare-covid.gov.ro/scheduling/api/centres"
		if counties_URL == None:
			counties_URL = "https://programare.vaccinare-covid.gov.ro/nomenclatures/api/county"
		if auth_URL == None:
			auth_URL = "https://programare.vaccinare-covid.gov.ro/auth/login"
		if headers == None:
			headers = {
				"Accept": "application/json",
				"Content-Type": "application/json", 
			}
		if payload == None:
			payload = {
				"countyID": None,
				"localityID":None,
				"name":None,
				"identificationCode":"x",
				"recipientID":None,
				"masterPersonnelCategoryID":-1
			}
		self.working_updated = updated
		self.sleep_time = 120
		self.vaccines = vaccines
		self.main_URL = main_URL
		self.counties_URL = counties_URL
		self.auth_URL = auth_URL
		self.headers = headers
		self.payload = payload
		self.verbose = verbose
		if working_dict == None:
			self.main_dict = dict()
			self.working_dict = None
			self.get_counties()
		else:
			self.main_dict = dict()
			self.working_dict = working_dict

	def work(self):
		while True:
			self.main_dict = self.get_slots(0)
			self.last_updated = datetime.now()
			if self.working_updated != None:
				self.working_updated.value = self.last_updated.timestamp()
			if self.working_dict != None:
				self.copy_main_to_working_dict()
			self.cleanup_and_print(self.verbose)
			time.sleep(self.sleep_time)


	def cleanup_and_print(self, verbose):
		if verbose == False:
				for county in self.main_dict:
					if self.main_dict[county]["availableSlots"] > 0:
						for vaccine_key, vaccine_name in self.vaccines.items():
							county_vaccine_slots = self.main_dict[county][vaccine_name]
							if county_vaccine_slots['availableSlots'] > 0:
								for centre in county_vaccine_slots["centres"]:
									centre_dict = county_vaccine_slots["centres"][centre]
									if centre_dict["availableSlots"] != 0:
										centre_dict["availableSlots"] = 0
								county_vaccine_slots['availableSlots'] = 0
						self.main_dict[county]["availableSlots"] = 0
				return

		free = 0
		for county in self.main_dict:
			if self.main_dict[county]["availableSlots"] > 0:
				logging.info(f"{self.main_dict[county]['name']} - {self.main_dict[county]['availableSlots']} locuri:")
				for vaccine_key, vaccine_name in self.vaccines.items():
					county_vaccine_slots = self.main_dict[county][vaccine_name]
					if county_vaccine_slots['availableSlots'] > 0:
						logging.info(f"\tVaccin {vaccine_name} - {county_vaccine_slots['availableSlots']} locuri:")
						for centre in county_vaccine_slots["centres"]:
							centre_dict = county_vaccine_slots["centres"][centre]
							if centre_dict["availableSlots"] != 0:
								logging.info(f"\t\t{centre_dict['name']}, localitate {centre_dict['localityName']}, locuri: {centre_dict['availableSlots']}")
								free += centre_dict["availableSlots"]
								centre_dict["availableSlots"] = 0
						county_vaccine_slots['availableSlots'] = 0
				self.main_dict[county]["availableSlots"] = 0
		logging.info(f"Total locuri libere țară: {free}")
		logging.info(f"Ultima actualizare: {self.last_updated}\n")


	def check_and_load_response(self, URL, method="POST"):
		if method == "GET":
			response = requests.get(URL, json=self.payload, cookies=self.session_cookie, headers=self.headers)
		else:
			response = requests.post(URL, json=self.payload, cookies=self.session_cookie, headers=self.headers)
		if response.url == self.auth_URL:
			raise requests.exceptions.InvalidHeader("Session cookie expired!")
		if response.status_code != 200:
			raise requests.exceptions.HTTPError(f"URL {URL}, status {response.status_code}")
		return response.content

	def get_counties(self):
		try:
			content = self.check_and_load_response(self.counties_URL, method="GET")
			json_response = json.loads(content)
			for county in json_response:
				if "trainatate" in county["name"]:
					continue
				self.main_dict[county["countyID"]] = {"shortName": county["shortName"], "name": county["name"], "availableSlots": 0}
				for vax_key, vax_name in self.vaccines.items():
					self.main_dict[county["countyID"]][vax_name] = {"centres": dict(), "availableSlots": 0}
				if self.working_dict != None:
					self.working_dict[county["countyID"]] = copy.deepcopy(self.main_dict[county["countyID"]])
		except Exception as err:
			logging.warning(f"get_counties: {err}")
			logging.warning(f"get_counties: Retrying...\n")
			time.sleep(self.sleep_time * 2)
			self.get_counties()


	def get_slots(self, page):
		try:
			content = self.check_and_load_response(self.main_URL + "?page=" + str(page) + "&size=20&sort=,")
			json_response = json.loads(content)
			logging.debug(json_response)
			if json_response["last"] == True:
				return self.main_dict
			for centre in json_response["content"]:
					vaccineName = self.vaccines[centre["boosterID"]]
					vaccine_entry = self.main_dict[centre['countyID']][vaccineName]
					if centre['availableSlots'] != 0 and (centre['code'] not in vaccine_entry['centres'] or vaccine_entry['centres'][centre['code']]['availableSlots'] == 0):
						vaccine_entry["centres"][centre['code']] = {"ID": centre['code'], "name": centre['name'], "localityName": centre['localityName'], "availableSlots": centre['availableSlots']}
						vaccine_entry["availableSlots"] += centre['availableSlots']
						self.main_dict[centre['countyID']]['availableSlots'] += centre['availableSlots']
					#print(centre['name'])
			return self.get_slots(page+1)
		except requests.exceptions.ConnectionError as err:
				logging.warning(f"get_slots: {err}")
				logging.warning(f"get_slots: Retrying...\n")
				# if there is a connection error, START OVER FROM THE BEGINNING
				# 	because page may be updated as you crawl it, and that might cause the error
				self.cleanup_and_print(verbose=False)
				time.sleep(2*self.sleep_time)
				return self.get_slots(0)
		except Exception as err:
				logging.warning(f"get_slots: {err}")
				logging.warning(f"get_slots: Retrying...\n")
				time.sleep(30)
				return self.get_slots(page)

	def share_working_dict(self, dictionary):
		self.working_dict = dictionary

	def copy_main_to_working_dict(self):
		# cleanup all of working_dict
		for county in dict(self.working_dict):
			if self.working_dict[county]["availableSlots"] > 0:
				for vaccine_key, vaccine_name in self.vaccines.items():
					county_vaccine_slots = self.working_dict[county][vaccine_name]
					if county_vaccine_slots['availableSlots'] > 0:
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
			if self.main_dict[county]["availableSlots"] > 0:
				for vaccine_key, vaccine_name in self.vaccines.items():
					county_vaccine_slots = self.main_dict[county][vaccine_name]
					if county_vaccine_slots['availableSlots'] > 0:
						for centre in dict(county_vaccine_slots["centres"]):
							self.working_dict[county][vaccine_name]["centres"][centre] = county_vaccine_slots["centres"][centre]
						self.working_dict[county][vaccine_name]['availableSlots'] = county_vaccine_slots['availableSlots']
				self.working_dict[county]["availableSlots"] = self.main_dict[county]["availableSlots"]


if __name__ == "__main__":
	Crawler(session_cookie="", verbose=True).work()
# {"centerID":93,"currentDate":"13-02-2021 02:00:00.000","forBooster":true,"recipientID":1454918,"masterPersonnelCategoryID":-2,"boosterDays":21,"identificationCode":"2340111400428"}
