import json
import os
import requests
from datetime import datetime
import math

from flask import Flask

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from google.cloud import storage

import logging
from logging.config import fileConfig


fileConfig('logger.cfg')
LOGGER = logging.getLogger()

if 'LOG_LEVEL' in os.environ:
    log_levels = {'NOTSET': 0, 'DEBUG': 10, 'INFO': 20,
                  'WARN': 30, 'ERROR': 40, 'CRITICAL': 50}
    if os.environ.get('LOG_LEVEL') in log_levels:
        LOGGER.setLevel(log_levels[os.environ.get('LOG_LEVEL')])
    else:
        LOGGER.error(
            f'LOG_LEVEL {os.environ.get("LOG_LEVEL")} is not a valid level. using {LOGGER.level}')
else:
    LOGGER.warning(f'LOG_LEVEL not set. current log level is {LOGGER.level}')


app_name = 'Airline Manager Automation'

app = Flask(app_name)

username = os.environ.get('USERNAME')
password = os.environ.get('PASSWORD')
fuel_price_threshold = os.environ.get('MAX_BUY_FUEL_PRICE', 400)
low_fuel_level = os.environ.get('LOW_FUEL_LEVEL', 20000000)
low_fuel_price_threshold = os.environ.get('MAX_BUY_LOW_FUEL_PRICE', 800)
co2_price_threshold = os.environ.get('MAX_BUY_CO2_PRICE', 111)
low_co2_level = os.environ.get('LOW_CO2_LEVEL', 20000000)
low_co2_price_threshold = os.environ.get('MAX_BUY_LOW_CO2_PRICE', 140)
plane_to_buy = os.environ.get('PLANE_SHORT_NAME_TO_BUY', 'a339')

LOGGER.info(
    f'fuel tank will be filled if the price is less than ${fuel_price_threshold}')
LOGGER.info(f'if the fuel tank has less than {low_fuel_level} lbs, difference will be purchased if the fuel price is '
            f'below ${low_fuel_price_threshold}')
LOGGER.info(
    f'co2 quota will be filled if the price is less than ${co2_price_threshold}')
LOGGER.info(f'if the co2 quota is less than {low_co2_level} lbs, difference will be purchased if the co2 quota price '
            f'is below ${low_co2_price_threshold}')

w_driver = None


def save_screenshot_to_bucket(bucket_name, file_name):
    LOGGER.debug(f'current directory is {os.getcwd()}')
    files = [f for f in os.listdir('.')]
    LOGGER.debug(f'Following files are in the current directory')
    LOGGER.debug(', '.join(files))
    try:
        client = storage.Client()
        bucket = client.get_bucket(bucket_name)
        new_blob = bucket.blob(file_name.replace('.png', f'{datetime.now()}.png'))
        file_upload = os.path.join(os.getcwd(), file_name)
        LOGGER.info(f'uploading {file_upload} to the bucket')
        new_blob.upload_from_filename(filename=file_upload)
    except Exception as e:
        LOGGER.exception(f'error uploading {file_upload} to the bucket')


def get_driver():
    global w_driver
    if w_driver is None:
        options = Options()
        options.headless = True
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        w_driver = webdriver.Chrome(options=options)
        w_driver.maximize_window()
        return w_driver
    return w_driver


def login(u_name, p_word):
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/')
    # /html/body/div[4]/div/div[2]/div[1]/div/button[2]
    try:
        WebDriverWait(driver, 120).until(EC.element_to_be_clickable(
            (By.XPATH, "/html/body/div[4]/div/div[2]/div[1]/div/button[2]")))
    except TimeoutException as e:
        LOGGER.exception(f'login button not found. waiting timed out.')
        driver.save_screenshot('login_page_error.png')
        save_screenshot_to_bucket('cloud-run-am4', 'login_page_error.png')
        driver.get('https://www.airlinemanager.com/')

    m_login_btn = driver.find_element(
        By.XPATH, "/html/body/div[4]/div/div[2]/div[1]/div/button[2]")
    if m_login_btn is not None and m_login_btn.is_displayed():
        m_login_btn.click()
        email_field = driver.find_element(By.ID, 'lEmail')
        email_field.send_keys(u_name)
        pass_field = driver.find_element(By.ID, 'lPass')
        pass_field.send_keys(p_word)
        login_btn = driver.find_element(By.ID, 'btnLogin')
        login_btn.click()
        try:
            WebDriverWait(driver, 120).until(
                EC.element_to_be_clickable((By.ID, 'flightInfoToggleIcon')))
        except TimeoutException as e:
            LOGGER.exception(f'login button not found. waiting timed out.')
            driver.save_screenshot('/app/login_error.png')
            save_screenshot_to_bucket('cloud-run-am4', 'login_error.png')
            driver.get('https://www.airlinemanager.com/banking_account.php?id=0')
            if driver.find_element(By.XPATH, '/html/body/div[4]').text == 'Transaction history':
                LOGGER.info('login successful')
            else:
                LOGGER.error('login failed')
                raise Exception('login failed. Automation will exit.')
                


def logout():
    global w_driver
    if w_driver is not None:
        w_driver.get('https://www.airlinemanager.com/weblogin/logout.php')
        w_driver.quit()
        w_driver = None


def get_fuel_stats():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/fuel.php')
    price = driver.find_element(
        By.XPATH, '/html/body/div/div/div[1]/span[2]/b').text
    capacity = driver.find_element(By.ID, 'remCapacity').text
    holding = driver.find_element(By.ID, 'holding').text
    LOGGER.info(
        f'Holding {holding} and capacity Remaining is {capacity} and current fuel price is {price}')
    return price, capacity, holding


def get_co2_stats():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/co2.php')
    price = driver.find_element(
        By.XPATH, '/html/body/div/div/div[2]/span[2]/b').text
    capacity = driver.find_element(By.ID, 'remCapacity').text
    holding = driver.find_element(By.ID, 'holding').text
    LOGGER.info(
        f'Holding {holding} and capacity Remaining is {capacity} and current co2 price is {price}')
    return price, capacity, holding


def depart_planes():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/route_depart.php?mode=all&ids=x')
    LOGGER.info('all planes departed')


def get_balance():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/banking_account.php?id=0')
    balance = driver.find_element(By.XPATH, '/html/body/div[1]/div').text
    LOGGER.info(f'Account balance is {balance}')
    return int(balance.replace('$', '').replace(',', '').strip())


def buy_fuel(quantity):
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/fuel.php?mode=do&amount={quantity}')
    LOGGER.info(f'bought {quantity} fuel')


def buy_co2(quantity):
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/co2.php?mode=do&amount={quantity}')
    LOGGER.info(f'bought {quantity} co2 quota')


def perform_fuel_ops():
    # fuel checks
    fuel_price, fuel_capacity, fuel_holding = get_fuel_stats()
    fuel_price_num = int(fuel_price.replace(
        '$', '').replace(',', '').replace(' ', ''))
    fuel_capacity_num = int(fuel_capacity.replace(',', '').replace(' ', ''))
    fuel_holding_num = int(fuel_holding.replace(',', '').replace(' ', ''))
    if fuel_price_num < int(fuel_price_threshold):
        balance = get_balance()
        if (fuel_capacity_num * fuel_price_num)/1000 < balance:
            buy_fuel(fuel_capacity_num)
        else:
            purchase_qty = (balance * 1000) / fuel_price_num
            buy_fuel(purchase_qty)
    elif fuel_holding_num < int(low_fuel_level) and fuel_price_num < int(low_fuel_price_threshold):
        balance = get_balance()
        if ((int(low_fuel_level) - fuel_holding_num) * fuel_price_num) / 1000 < balance:
            buy_fuel(int(low_fuel_level) - fuel_holding_num)
        else:
            purchase_qty = (balance * 1000) / fuel_price_num
            buy_fuel(purchase_qty)
    else:
        LOGGER.info(f'fuel price is too high to buy...')


def perform_co2_ops():
    # co2 checks
    co2_price, co2_capacity, co2_holding = get_co2_stats()
    co2_price_num = int(co2_price.replace(
        '$', '').replace(',', '').replace(' ', ''))
    co2_capacity_num = int(co2_capacity.replace(',', '').replace(' ', ''))
    co2_holding_num = int(co2_holding.replace(',', '').replace(' ', ''))
    if co2_price_num < (111 if co2_price_threshold is None else int(co2_price_threshold)):
        balance = get_balance()
        if (co2_capacity_num * co2_price_num)/1000 < balance:
            buy_co2(co2_capacity_num)
        else:
            purchase_qty = (balance * 1000)/co2_price_num
            buy_co2(purchase_qty)
    elif co2_holding_num < int(low_co2_level) and co2_price_num < int(low_co2_price_threshold):
        balance = get_balance()
        if ((int(low_co2_level) - co2_holding_num) * co2_price_num) / 1000 < balance:
            buy_co2(int(low_co2_level) - co2_holding_num)
        else:
            purchase_qty = (balance * 1000) / co2_price_num
            buy_co2(purchase_qty)
    else:
        LOGGER.info(f'co2 price is too high to buy...')


def perform_routine_ops():
    # depart planes
    depart_planes()
    # perform fuel ops
    perform_fuel_ops()
    # perform co2 ops
    perform_co2_ops()
    # perform maintenance, if needed
    check_aircrafts()
    # buy planes if there is enough money
    buy_aircrafts()
    # route parked planes, if any
    route_aircrafts()


def set_ticket_price(route_id, e, b, f):
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/set_ticket_prices.php?e={e}&b={b}&f={f}&id={route_id}')


def get_routes():
    route_list = []
    driver = get_driver()
    start = 0
    while True:
        driver.get(f'https://www.airlinemanager.com/routes.php?start={start}')
        routes_container = driver.find_element(By.ID, 'routesContainer')
        elements = routes_container.find_elements(
            by=By.CLASS_NAME, value='m-text')
        if len(elements) == 0:
            LOGGER.info('no more routes found...')
            break
        else:
            LOGGER.debug(f'found routes {len(elements)}')
            start += len(elements)
        for element in elements:
            route_id = element.get_property('id').replace('routeMainList', '')
            route_desc = element.find_element(
                By.XPATH, f'//*[@id="routeMainList{route_id}"]/div[1]/div/div[2]/span').text
            ticket_price = get_route_details(route_desc.split(
                ' - ')[0], route_desc.split(' - ')[1])[1]['realism']
            route_list.append(
                {'route_id': route_id, 'route_desc': route_desc, 'ticket_price': ticket_price})

    return route_list


def get_route_details(departure, arrival):
    response = requests.get(
        f'https://am4tools.com/route/ticket?type=pax&mode=normal&departure={departure}&arrival={arrival}')
    if response.status_code == 200:
        route_details = json.loads(response.text)
    else:
        route_details = None
    return route_details['routes'][0], route_details['ticket']


def create_route(plane_id, route_name, destination_airport_id, economy_price, business_price, first_price):
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/new_route_info.php?mode=do&id={plane_id}&airportId={destination_airport_id}&reg={route_name}&e={economy_price}&b={business_price}&f={first_price}&stopoverId=0&ferry=0&intro=0&fbSig=false')
    LOGGER.info(f'created route {route_name}')


def buy_aircraft(plane_id, hub_id, engine_id, plane_name, economy, business, first):
    driver = get_driver()
    driver.get(f'https://www.airlinemanager.com/ac_order_do.php?id={plane_id}&hub={hub_id}&e={economy}&b={business}&'
               f'f={first}&r={plane_name}&engine={engine_id}&amount=1&fbSig=false')
    LOGGER.info(f'bought plane {plane_name}')


def check_aircrafts():
    aircrafts_to_check = []
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/maint_plan.php')
    aircraft_list = driver.find_element(By.ID, 'acListView')
    aircrafts = aircraft_list.find_elements(By.CLASS_NAME, 'maint-list-sort')
    for aircraft in aircrafts:
        try:
            aircraft_id = aircraft.find_element(By.XPATH, './/div[3]') .get_property('id').replace('controls', '')
            aircraft_location = aircraft.text.split('\n')[4]
            if aircraft_location == 'Not at base':
                continue
            time_to_check = aircraft.text.split('\n')[6]
            if int(time_to_check) < 20:
                aircrafts_to_check.append(aircraft_id)
        except NoSuchElementException:
            LOGGER.exception('something went wrong when checking aircraft for maintenance')
    for aircraft_id in aircrafts_to_check:
        check_aircraft(aircraft_id)


def get_plane_details(aircraft_type_id):
    planes_data = []

    driver = get_driver()

    driver.get(
        f'https://www.airlinemanager.com/fleet.php?type={aircraft_type_id}')

    elements = driver.find_elements(By.XPATH, '/html/body/div[2]/div/div')

    for element in elements:

        plane_id = element.find_element(
            By.XPATH, f'.//div[1]/span').get_attribute("onclick").split(',')[1]
        plane_name = element.find_element(
            By.XPATH, f'.//div[2]/a').text
        plane_status = element.find_element(
            By.XPATH, f'.//div[4]/span').text
        plane_seats = element.find_element(
            By.XPATH, f'.//div[3]').text
        
        LOGGER.debug(f"{plane_name} with id {plane_id} has the status {plane_status}")

        economy = plane_seats.split('\n')[0].split(': ')[1]
        business = plane_seats.split('\n')[1].split(': ')[1]
        first = plane_seats.split('\n')[2].split(': ')[1]

        planes_data.append({'id': plane_id, 'name': plane_name, 'departure': plane_name.split(
            '-')[0], 'arrival': plane_name.split('-')[1], 'status': plane_status, 'economy': economy, 'business': business, 'first': first})
        
    return planes_data


def get_seat_configuration(departure, arrival, max_seat_capacity, trips):
    route_details, _ = get_route_details(departure, arrival)
        
    f = math.ceil(route_details['first_class_demand']/trips) + 1
    b = math.ceil(route_details['business_demand']/trips) + 1
    e = math.ceil(route_details['economic_demand']/trips) + 1

    if f >= max_seat_capacity:
        _e = 0
        _b = 0
        _f = max_seat_capacity
    elif f + b >= max_seat_capacity:
        _e = 0
        _b = max_seat_capacity - f
        _f = f
    else:
        _e = max_seat_capacity - (b + f)
        _b = b
        _f = f
    
    return _e, _b, _f


def create_routes(aircraft_type_id):
    for plane_data in get_plane_details(aircraft_type_id):
        # possible vales are ['Maintenance', 'Routed', 'Pending', 'Grounded', 'Parked']
        if plane_data['status'] in ['Parked']:
            route_details, ticket_prices = get_route_details(plane_data['departure'], plane_data['arrival'])
            create_route(plane_data['id'],
                         plane_data['name'], route_details['arrival']['id'], ticket_prices['realism']['ticketY'],
                         ticket_prices['realism']['ticketJ'], ticket_prices['realism']['ticketF'])


def modify_aircraft(aircraft_id, economy, business, first):
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/maint_plan_do.php?mode=do&modType=pax&id={aircraft_id}&type=modify&eSeat={economy}&bSeat={business}&fSeat={first}&mod1=1&mod2=1&mod3=1&fbSig=false')
    LOGGER.info(f'Modification scheduled for aircraft {aircraft_id}')


def check_aircraft(aircraft_id):
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/maint_plan_do.php?mode=do&type=check&id={aircraft_id}')
    LOGGER.info(f'A-Check scheduled for {aircraft_id}')


def find_routes(plane, hub_iata_code, limit=1):
    airports = []

    with open('airports.json', 'r') as airports_file:
        airports = json.load(airports_file)

    plane_details = get_plane_details(plane['id'])

    destinations = [plane['arrival'] for plane in plane_details if plane['departure'] == hub_iata_code]
    routes = {}

    for page_number in range(1, 500):
        try:
            response = requests.get(f'https://am4tools.com/route/search?departure={hub_iata_code}&sort=firstClass&order=desc&page={page_number}&mode=hub')
            if response.status_code == 404:
                break
            if response.status_code == 200:
                potential_routes = response.json()['routes']
                for route in potential_routes:
                    try:
                        if route['arrival']['iata'] in destinations:
                            # this route already exists
                            continue
                        if route['distance'] > plane['range']:
                            # this route is too long for this plane
                            continue
                        if route['distance'] < plane['engine']['speed'] * 12 * 1.1:
                            # this route is too short for this plane (each trip will be less than 12 hours)
                            # this also includes 10% higher speed after the engine modification
                            continue
                        airport = [airport for airport in airports if airport['iata'] == route['arrival']['iata']][0]
                        if airport['runway'] < plane['runway']:
                            # runway in the destination is too short for this plane
                            continue
                        # both a330-900neo and a380-800 can make 2 trips a day. 
                        if route['first_class_demand'] + route['business_demand'] + route['economic_demand'] < 2 * plane['capacity']:
                            # if the combined demand is more than 2*capacity, the trip is worth it.
                            continue
                        if route['first_class_demand'] < plane['capacity'] * 0.25 * 2 or (route['first_class_demand'] + route['business_demand']) < plane['capacity'] * 0.7 * 2:
                            # if the first class demand is less than 25% of the capacity or the combined demand of first and business class is less than 70% of the capacity, the trip is not very profitable.
                            continue
                        e, b, f = get_seat_configuration(route['departure']['iata'], route['arrival']['iata'], plane['capacity'], 2)
                        
                        routes[f"{route['departure']['iata']}-{route['arrival']['iata']}"] = {'name': f"{route['departure']['iata']}-{route['arrival']['iata']}", 'economy': e, 'business': b, 'first': f}
                        if len(routes) == limit:
                            return routes
                    except Exception as e:
                        LOGGER.exception('Error processing a route from am4tools')
        except Exception as e:
            LOGGER.exception('Error getting routes from am4tools')


def buy_aircrafts():
    planes = []
    hubs = []
    with open('planes.json', 'r') as planes_json:
        planes = json.load(planes_json)['pax']
    with open('hubs.json', 'r') as hubs_json:
        hubs = json.load(hubs_json)
    plane = [plane for plane in planes if plane['shortname'] == plane_to_buy][0]
    balance = get_balance()
    if balance > plane['price'] * 1.3:
        quantity = math.floor(balance / (plane['price'] * 1.2))
        LOGGER.info(f'Buying {quantity} {plane["model"]}')
        for hub in hubs:
            routes = find_routes(plane, hub['iata'], quantity)
            if len(routes) == 0:
                continue
            if len(routes) <= quantity:
                quantity -= len(routes)
            for name, route in routes.items():
                buy_aircraft(plane['id'], hub['hub_id'], plane['engine']['id'], name, route['economy'], route['business'], route['first'])
            if quantity == 0:
                break


def route_aircrafts():
    planes = []
    with open('planes.json', 'r') as planes_json:
        planes = json.load(planes_json)['pax']
    plane = [plane for plane in planes if plane['shortname'] == plane_to_buy][0]
    for plane_data in get_plane_details(plane['id']):
        # possible vales are ['Maintenance', 'Routed', 'Pending', 'Grounded', 'Parked']
        if plane_data['status'] in ['Parked']:
            modify_aircraft(plane_data['id'], plane_data['economy'], plane_data['business'], plane_data['first'])
            route_details, ticket_prices = get_route_details(plane_data['departure'], plane_data['arrival'])
            create_route(plane_data['id'],
                         plane_data['name'], route_details['arrival']['id'], ticket_prices['realism']['ticketY'],
                         ticket_prices['realism']['ticketJ'], ticket_prices['realism']['ticketF'])


@app.route('/')
def run_app():
    login(username, password)
    perform_routine_ops()
    logout()
    return 'All Done!', 200


@app.route('/depart')
def depart():
    login(username, password)
    depart_planes()
    logout()
    return 'Planes Departed (Max. 20)!', 200


@app.route('/maintain')
def do_maintanance():
    login(username, password)
    check_aircrafts()
    logout()
    return 'Maintanance scheduled for planes in base', 200


@app.route('/update_ticket_price')
def update_ticket_price():
    login(username, password)
    route_list = get_routes()
    for route in route_list:
        set_ticket_price(route['route_id'], route['ticket_price']['ticketY'],
                         route['ticket_price']['ticketJ'], route['ticket_price']['ticketF'])
    logout()
    return 'ticket prices updated', 200


@app.route('/update_fleet/<aircraft_type_id>/<max_seat_capacity>/<trips>')
def update_fleet(aircraft_type_id, max_seat_capacity, trips):
    login(username, password)

    for plane_data in get_plane_details(aircraft_type_id):
        # possible vales are ['Maintenance', 'Routed', 'Pending', 'Grounded', 'Parked']
        if plane_data['status'] in ['Pending', 'Grounded', 'Maintenance']:
            continue
        if int(plane_data['economy']) + int(plane_data['business']) + int(plane_data['first']) == max_seat_capacity and int(plane_data['economy']) != max_seat_capacity and plane_data['name'] != 'DEL-ICN':
            continue
        
        e, b, f = get_seat_configuration(plane_data['departure'], plane_data['arrival'], max_seat_capacity, trips)

        if plane_data['status'] in ['Parked']:
            route_details, ticket_prices = get_route_details(plane_data['departure'], plane_data['arrival'])
            create_route(plane_data['id'],
                         plane_data['name'], route_details['arrival']['id'], ticket_prices['realism']['ticketY'],
                         ticket_prices['realism']['ticketJ'], ticket_prices['realism']['ticketF'])

        if abs(e - int(plane_data['economy'])) < 5 and abs(b - int(plane_data['business'])) < 5 and abs(f - int(plane_data['first'])) < 5:
            continue

        modify_aircraft(plane_data['id'], e, b, f)

    logout()

if __name__ == '__main__':
    from waitress import serve

    serve(app, host='0.0.0.0', port=8080)
