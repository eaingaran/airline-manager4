import json
import time
import traceback

import requests

import airline_manager4 as am4
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from enum import Enum


class Hubs(Enum):
    London_Heathrow_Int = 3582640
    Frankfurt_Int = 3353515
    Los_Angeles = 3458942
    New_Delhi = 3502287
    Abu_Dhabi_Int = 3523007
    St_Petersburg = 3538538
    Long_Beach = 3541183
    Chennai = 3541222
    Conakry = 3648482


class Planes(Enum):
    MC_21_400 = 344
    A330_900neo = 308
    A380_800neo = 2


class Engines(Enum):
    PW1400G = 312           # used in MC-21-400
    RR_Trent_7000 = 294     # used in A330-900neo
    RR_Trent_972 = 7        # used in A380-800


def buy_planes(plane_model, hub_id, engine_model):
    am4.login(am4.username, am4.password)

    # https://www.airlinemanager.com/ac_order_do.php?id=308&hub=3523007&e=185&b=110&f=145&r=AUH-CLT&engine=294&amount=1&fbSig=false

    with open('new_planes.txt', 'r') as planes:
        for plane in planes:
            all_val = plane.split(' - ')
            plane_val = all_val[2].split(',')
            am4.buy_aircraft(plane_model, hub_id, engine_model,
                             f'{all_val[0]}',
                             int(plane_val[0]), int(plane_val[1]), int(plane_val[2]))
            time.sleep(5)

    am4.logout()


def update_planes_json():
    with open('planes.json', 'r') as planes_file:
        planes = json.load(planes_file)
        pax_planes = planes['pax']
        for pax_plane in pax_planes:
            del pax_plane['active_engine']
            engines = pax_plane['engines']
            max_speed = 0
            max_speed_engine = 0
            for index, engine in enumerate(engines):
                if engine['speed'] > max_speed:
                    max_speed = engine['speed']
                    max_speed_engine = index
            pax_plane['engine'] = engines[max_speed_engine]
            pax_plane['engine']['id'] = 0
            del pax_plane['engines']
        planes['pax'] = pax_planes
    cargo_planes = planes['cargo']
    for cargo_plane in cargo_planes:
        del cargo_plane['active_engine']
        engines = cargo_plane['engines']
        max_speed = 0
        max_speed_engine = 0
        for index, engine in enumerate(engines):
            if engine['speed'] > max_speed:
                max_speed = engine['speed']
                max_speed_engine = index
        cargo_plane['engine'] = engines[max_speed_engine]
        cargo_plane['engine']['id'] = 0
        del cargo_plane['engines']
    planes['cargo'] = cargo_planes
    with open('planes_updated.json', 'w+') as planes_n_file:
        planes_n_file.write(json.dumps(planes))


def create_hubs():
    with open('airports.json', 'r') as airports_file:
        airports = json.load(airports_file)
        hubs_list = ['FRA', 'LAX', 'MAA', 'DEL', 'AUH', 'CKY', 'LGB', 'LED', 'LHR']
        hubs = [airport for airport in airports if airport['iata'] in hubs_list]
        with open('hubs.json', 'w+') as hubs_file:
            hubs_file.write(json.dumps(hubs))


def update_ticket_price():
    am4.update_ticket_price()


def update_mc21_fleet():
    am4.update_fleet(Planes.MC_21_400.value, 230, 5)


def update_a330_fleet():
    am4.update_fleet(Planes.A330_900neo.value, 440, 2)


def update_a380_fleet():
    am4.update_fleet(Planes.A380_800neo.value, 600, 2)


def create_mc21_routes():
    am4.create_routes(Planes.MC_21_400.value)

def create_a380_routes():
    am4.create_routes(Planes.A380_800neo.value)

def create_a330_routes():
    am4.create_routes(Planes.A330_900neo.value)

def do_maintanance():
    am4.do_maintanance()


if __name__ == '__main__':
    am4.username = ''
    am4.password = ''
    am4.fuel_price_threshold = '100'
    am4.co2_price_threshold = '100'

    options = Options()
    options.headless = False
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    w_driver = webdriver.Chrome(options=options,
                                executable_path='')
    w_driver.maximize_window()

    am4.w_driver = w_driver

    # am4.run_app()

    # update_ticket_price()
    # buy_planes(Planes.A330_900neo.value, Hubs.Los_Angeles.value, Engines.RR_Trent_7000.value)
    # print_routes()
    # update_mc21_fleet()
    # update_a330_fleet()
    # update_a380_fleet()
    # create_mc21_routes()
    # create_a330_routes()
    # create_a380_routes()
    # do_maintanance()
    # find_routes(Planes.A330_900neo.value, 'LAX')

