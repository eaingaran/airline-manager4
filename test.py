import json
import time
import traceback
import math
import timeit
import os

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

def do_marketing():
    am4.login(am4.username, am4.password)
    am4.marketing()
    am4.logout()


def get_all_routes():
    p_routes = []
    am4.login(am4.username, am4.password)
    planes = []
    hubs = []
    with open('planes.json', 'r') as planes_json:
        planes = json.load(planes_json)['pax']
    with open('hubs.json', 'r') as hubs_json:
        hubs = json.load(hubs_json)
    plane = [plane for plane in planes if plane['shortname'] == 'a388'][0]
    balance = am4.get_balance()
    # if balance > plane['price'] * 1.3:
    for hub in hubs:
        print(f'processing hub {hub["iata"]}')
        routes = am4.find_pax_routes(plane, hub['iata'], 100)
        if routes is None or len(routes) == 0:
            continue
        for name, route in routes.items():
            print(f'can buy {name}')
            print(f"{plane['id']}, {hub['hub_id']}, {plane['engine']['id']}, {name}, {route['economy']}, {route['business']}, {route['first']}")
            p_routes.append(f"{plane['id']}, {hub['hub_id']}, {plane['engine']['id']}, {name}, {route['economy']}, {route['business']}, {route['first']}, {route['distance']}, {route['trips']} \n")
    am4.logout()
    with open('routes_to_buy.txt', 'w+') as routes_file:
        routes_file.writelines(p_routes)


def get_all_cargo_routes():
    p_routes = []
    am4.login(am4.username, am4.password)
    planes = []
    hubs = []
    with open('planes.json', 'r') as planes_json:
        planes = json.load(planes_json)['cargo']
    with open('hubs.json', 'r') as hubs_json:
        hubs = json.load(hubs_json)
    plane = [plane for plane in planes if plane['shortname'] == 'a388f'][0]
    balance = am4.get_balance()
    # if balance > plane['price'] * 1.3:
    for hub in hubs:
        print(f'processing hub {hub["iata"]}')
        routes = am4.find_cargo_routes(plane, hub['iata'], 100)
        if routes is None or len(routes) == 0:
            continue
        for name, route in routes.items():
            print(f'can buy {name}')
            print(f"{plane['id']}, {hub['hub_id']}, {plane['engine']['id']}, {name}, {route['aft']}, {route['fwd']}")
            p_routes.append(f"{plane['id']}, {hub['hub_id']}, {plane['engine']['id']}, {name}, {route['aft']}, {route['fwd']}, {route['distance']}, {route['trips']} \n")
    am4.logout()
    with open('routes_to_buy.txt', 'w+') as routes_file:
        routes_file.writelines(p_routes)


def check_available_380_routes():
    planes = []
    hubs = []
    with open('planes.json', 'r') as planes_json:
        planes = json.load(planes_json)['pax']
    with open('hubs.json', 'r') as hubs_json:
        hubs = json.load(hubs_json)
    plane = [plane for plane in planes if plane['shortname'] == 'a388'][0]
    plane_details = am4.get_pax_plane_details(2)

    # include a339 routes in check as well...
    plane_details.extend(am4.get_pax_plane_details(308))
    all_routes = []

    for hub in hubs:
        routes = am4.find_pax_routes(plane, hub['iata'], plane_details, 1000)
        all_routes.extend(routes)
    
    print(f'found {len(all_routes)} routes for A380-800')


def check_plane_profits(aircraft_type_id):
    planes_data = []

    driver = am4.get_driver()

    driver.get(
        f'https://www.airlinemanager.com/fleet.php?type={aircraft_type_id}')

    elements = driver.find_elements(By.XPATH, '/html/body/div[2]/div/div')

    for element in elements:
        try:
            plane_id = element.find_element(
                By.XPATH, f'.//div[1]/span').get_attribute("onclick").split(',')[1]
            plane_name = element.find_element(
                By.XPATH, f'.//div[2]/a').text
            plane_link = f'https://www.airlinemanager.com/fleet_details.php?id={plane_id}&returnType={aircraft_type_id}'

        except Exception as e:
            print(e)

        planes_data.append({'id': plane_id, 'name': plane_name, 'url': plane_link})

    for plane in planes_data:
        driver.get(plane['url'])
        age = driver.find_element(By.XPATH, f'//*[@id="detailsGroundedBg"]/div[4]/div/div[1]/span[4]').text
        count = 0
        total = 0
        for i in range(1, 21):
            try:
                revenue = int(driver.find_element(By.XPATH, f'//*[@id="flight-history"]/div[{i}]/div[4]').text.replace('$', '').replace(',', ''))
                total += revenue
                count += 1
            except Exception as e:
                traceback.print_exc()
                break
        if count != 0:
            average_revenue = total / count
        else:
            average_revenue = 0
        plane['avg_revenue'] = average_revenue
        plane['age'] = age
    
    sorted_plane_data = sorted(planes_data, key=lambda d: d['avg_revenue']) 

    for plane in sorted_plane_data:
        print(f'{plane["name"]} bought {plane["age"]} has an average revenue of {plane["avg_revenue"]}')

if __name__ == '__main__':
    am4.username = os.getenv("AM_USERNAME", "")
    am4.password = os.getenv("AM_PASS", "")
    am4.fuel_price_threshold = '100'
    am4.co2_price_threshold = '100'

    options = Options()
    options.headless = False
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    w_driver = webdriver.Chrome(options=options,
                                executable_path='~/Sources/PycharmProjects/am4/drivers/chromedriver')
    w_driver.maximize_window()

    am4.w_driver = w_driver

    starttime = timeit.default_timer()
    print("The start time is :",starttime)
    # get_all_routes()
    # am4.run_app()
    # get_all_cargo_routes()
    # get_all_routes()
    
    am4.login(am4.username, am4.password)
    # planes_data = am4.get_cargo_plane_details(358)
    #print(planes_data.__repr__())
    # am4.buy_pax_aircrafts()

    #check_available_380_routes()
    check_plane_profits(308)
    
    am4.logout()

    print("The time difference is :", timeit.default_timer() - starttime)

    #get_all_routes()

    # hangars.php?mode=upgrade&amount=10&type=
    # hangars.php?mode=upgrade&amount=10&type=cargo

    # 'https://www.airlinemanager.com/ac_order_do_cargo.php?engine=336&reg=TEST&hub=3353515&acId=365&aft=20&fwd=10'

    # am4.run_app()
    # do_marketing()
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

