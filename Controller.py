from multiprocessing import Process, Manager, Queue
from Crawler import Crawler
import time
import copy
from datetime import datetime

class Controller:
	def __init__(self, session_cookie, interface_queue, vaccines=None, main_URL=None, 
			auth_URL=None, counties_URL=None, headers=None, payload=None, verbose=False):
		self.manager = Manager()
		self.dictionary = dict()
		self.last_updated = self.manager.Value(float, 0.0)
		self.crawler = Crawler(session_cookie, working_dict=self.dictionary, vaccines=vaccines, main_URL=main_URL, 
			auth_URL=auth_URL, counties_URL=counties_URL, headers=headers, payload=payload, updated=self.last_updated, verbose=verbose)
		self.vaccines = self.crawler.vaccines
		self.populate_nested_dictionary(self.crawler)
		self.crawler.share_working_dict(self.dictionary)

		self.c_proc = Process(target=self.crawler.work, args=())
		self.listen_proc = Process(target=self.interface_event_listener, args=(interface_queue,))
		self.c_proc.start()
		self.listen_proc.start()
	
	def get_dictionary(self):
		return copy.copy(self.dictionary)

	def get_vaccines(self):
		return copy.copy(self.vaccines)

	def populate_nested_dictionary(self, crawler):
		crawler.get_counties()
		for county_key, county_val in self.dictionary.items():
			for key, val in county_val.items():
				if type(val) is dict:
					val['centres'] = self.manager.dict(val['centres'])
					self.dictionary[county_key][key] = self.manager.dict(self.dictionary[county_key][key])
			self.dictionary[county_key] = self.manager.dict(self.dictionary[county_key])
		self.dictionary = self.manager.dict(self.dictionary)

	def get_slots(self, county, vaccines):
		main_msg = self.dictionary[county]["name"].upper()
		msg = ""
		free = 0
		if self.dictionary[county]["availableSlots"] > 0:
			for vaccine_key in vaccines:
				vaccine_name = vaccines[vaccine_key]
				county_vaccine_slots = self.dictionary[county][vaccine_name]
				if county_vaccine_slots['availableSlots'] > 0:
					for centre in dict(county_vaccine_slots["centres"]):
						centre_dict = county_vaccine_slots["centres"][centre]
						if centre_dict["availableSlots"] != 0:
							msg += f"    {centre_dict['localityName']}: {centre_dict['name']}, nr. locuri: {centre_dict['availableSlots']}, vaccin {vaccine_name}\n"
							free += centre_dict["availableSlots"]
		main_msg += f" - {free} locuri\n"
		main_msg += msg
		main_msg += f"Ultima actualizare: {datetime.fromtimestamp(self.last_updated.value).strftime('%d.%m.%Y %H:%M:%S')}\n\n"
		if free == 0:
			main_msg = ""
		return (main_msg, free)

	def interface_event_listener(self, interface_queue):
		f = open("alexandru", "a")
		while True:
			task = interface_queue.get()
			num_counties = len(task[0])
			num_vaccines = len(task[1])
			counties = task[0]
			vaccines = task[1]
			ret_msg = "Locuri libere în județele "

			free = 0
			print_msg = ""
			for i in range(num_counties - 1):
				f.write(f"{counties[i]}\n")
				ret_msg += self.dictionary[counties[i]]["name"] + ", "
				msg_county, free_county = self.get_slots(counties[i], vaccines)
				print_msg += msg_county
				free += free_county
			msg_county, free_county = self.get_slots(counties[num_counties-1], vaccines)
			print_msg += msg_county
			free += free_county

			ret_msg += self.dictionary[counties[num_counties-1]]["name"] + ",\n"
			ret_msg += "    cu vaccinurile "
			for key, val in vaccines.items():
				ret_msg += val + " "
			ret_msg += ":\n\n"

			if free == 0:
				ret_msg += "Nu există locuri libere!"
				task[2].value = ret_msg
				interface_queue.task_done()
				continue
			
			ret_msg += print_msg
			ret_msg += f"Total: {free} locuri"

			task[2].value = ret_msg
			interface_queue.task_done()
		f.close()

	def join(self):
		self.c_proc.join()


	def __getstate__(self):
		del self.__dict__["manager"]
		del self.__dict__["c_proc"]
		del self.__dict__["listen_proc"]
		f = open("alexandru", "a")
		f.close()
		return self.__dict__


if __name__ == "__main__":
	c = Controller(session_cookie="", interface_queue=Queue(), verbose=True)
	c.join()