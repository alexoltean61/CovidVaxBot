from multiprocessing import Process, Manager, Queue
from Crawler import Crawler
import time
import copy
from datetime import datetime
import traceback
import os, signal

class Controller:
	def __init__(self, interface_queue, alerts_queue, session_cookie=None, vaccines=None, main_URL=None, 
			auth_URL=None, counties_URL=None, headers=None, payload=None, logging_queue=None, time_to_kill=None, verbose=False):
		try:
			self.logging_queue = logging_queue
			self.format = "%Y-%m-%d %H:%M:%S"
			self.killing_condition = time_to_kill
			self.alerts_queue = alerts_queue
			self.manager = Manager()
			self.dictionary = dict()
			self.last_updated = self.manager.Value(float, 0.0)
			self.new_slots    = self.manager.list()
			self.new_slots_condition = self.manager.Condition()
			self.logging_queue.put("controller passed")
			self.crawler = Crawler(session_cookie=session_cookie, working_dict=self.dictionary, vaccines=vaccines, main_URL=main_URL, 
				auth_URL=auth_URL, counties_URL=counties_URL, headers=headers, payload=payload, updated=self.last_updated,
				new_slots = self.new_slots, new_slots_condition=self.new_slots_condition, logging_queue=logging_queue)
			self.logging_queue.put("controller passed crawler")
			self.vaccines = self.crawler.vaccines
			self.logging_queue.put("a")
			self.populate_nested_dictionary(self.crawler)
			self.logging_queue.put("b")
			self.crawler.share_working_dict(self.dictionary)

			self.logging_queue.put("controller passed populating")
			self.c_proc = Process(target=self.crawler.work, args=())
			self.listen_proc1 = Process(target=self.interface_event_listener, args=(interface_queue,))
			self.listen_proc2 = Process(target=self.new_slots_event_listener, args=())
			self.killer_proc = Process(target=self.sleeping_killer, args=())
			self.c_proc.start()
			self.listen_proc1.start()
			self.listen_proc2.start()
			self.killer_proc.start()
			self.logging_queue.put("controller passed it all")
		except Exception as e:
			self.logging_queue.put(f"{datetime.now().strftime(self.format)} Controller: {traceback.format_exc()}")


	def get_dictionary(self):
		return dict(copy.copy(self.dictionary))

	def get_vaccines(self):
		return dict(copy.copy(self.vaccines))

	def populate_nested_dictionary(self, crawler):
		self.logging_queue.put("counties")
		crawler.get_counties()
		self.logging_queue.put("got counties")
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
		self.logging_queue.put(f"CONTROLLER: listen from interface {os.getpid()}")
		while True:
			task = interface_queue.get()
			if task == None:
				interface_queue.task_done()
				return
			num_counties = len(task[0])
			num_vaccines = len(task[1])
			counties = task[0]
			vaccines = task[1]
			ret_msg = "Locuri libere în județele "

			free = 0
			print_msg = ""
			for i in range(num_counties - 1):
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
				ret_msg += "Nu există locuri libere!\n"
				task[2].value = ret_msg
				interface_queue.task_done()
				continue

			ret_msg += print_msg
			ret_msg += f"Total: {free} locuri\n"

			task[2].value = ret_msg
			interface_queue.task_done()

	def new_slots_event_listener(self):
		self.logging_queue.put(f"CONTROLLER: listen for alerts {os.getpid()}")
		with self.new_slots_condition:
			self.new_slots_condition.wait()
		del self.new_slots[:]
		while True:
			with self.new_slots_condition:
				self.new_slots_condition.wait()
				for county, vaccine, action in self.new_slots:
					if type(action) == str:
						centre_name = action
						self.alerts_queue.put((county, vaccine, -1, centre_name))
					else:
						added_slots = action
						msg = self.get_slots(county, dict( {vaccine: self.vaccines[vaccine] } ))
						self.alerts_queue.put((county, vaccine, added_slots, msg[0]))
				del self.new_slots[:]

	def sleeping_killer(self):
		self.logging_queue.put(f"CONTROLLER: sleeping killer {os.getpid()}")
		with self.killing_condition:
			self.killing_condition.wait()
			os.kill(self.listen_proc2.pid, signal.SIGKILL)
			os.kill(self.listen_proc1.pid, signal.SIGKILL)
			os.kill(self.c_proc.pid, signal.SIGKILL)
		os.kill(os.getpid(), signal.SIGKILL)


	def join(self):
		self.c_proc.join()
		self.listen_proc1.join()
		self.listen_proc2.join()
		self.killer_proc.join()

	def __getstate__(self):
		del self.__dict__["manager"]
		del self.__dict__["c_proc"]
		del self.__dict__["listen_proc"]
		return self.__dict__


if __name__ == "__main__":
	c = Controller(session_cookie="MjZmZjMwMWItMGM2Zi00NWFiLTg5ZWEtYTkyMTgyOGEzOGVm", interface_queue=Queue(), verbose=True)
	c.join()
