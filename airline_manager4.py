import json
import os
import requests
from datetime import datetime, timezone
import math
import random

from flask import Flask

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options as ChromeOptions

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from google.cloud import storage
from google.cloud.exceptions import NotFound

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
low_fuel_level = os.environ.get('LOW_FUEL_LEVEL', 30000000)
low_fuel_price_threshold = os.environ.get('MAX_BUY_LOW_FUEL_PRICE', 800)
co2_price_threshold = os.environ.get('MAX_BUY_CO2_PRICE', 111)
low_co2_level = os.environ.get('LOW_CO2_LEVEL', 40000000)
low_co2_price_threshold = os.environ.get('MAX_BUY_LOW_CO2_PRICE', 140)
pax_plane_to_buy = os.environ.get('PAX_PLANE_SHORT_NAME_TO_BUY', 'a388')
cargo_plane_to_buy = os.environ.get('CARGO_PLANE_SHORT_NAME_TO_BUY', 'a388f')
bucket_name = os.environ.get('BUCKET_NAME', 'cloud-run-am4')
lounge_maintanance_threshold = os.environ.get('LOUNGE_MAINTANANCE_THRESHOLD', 10)

LOGGER.info(
    f'fuel tank will be filled if the price is less than ${fuel_price_threshold}')
LOGGER.info(f'if the fuel tank has less than {low_fuel_level} lbs, difference will be purchased if the fuel price is '
            f'below ${low_fuel_price_threshold}')
LOGGER.info(
    f'co2 quota will be filled if the price is less than ${co2_price_threshold}')
LOGGER.info(f'if the co2 quota is less than {low_co2_level} lbs, difference will be purchased if the co2 quota price '
            f'is below ${low_co2_price_threshold}')

w_driver = None


def save_screenshot_to_bucket(file_name):
    screenshot_folder = 'screenshots'
    date_string = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%H:%M:%S')
    try:
        client = storage.Client()
        bucket = client.get_bucket(bucket_name)
        new_blob = bucket.blob(f"{screenshot_folder}/{date_string}/{file_name.replace('.png', f'{timestamp}.png')}")
        LOGGER.info(f'uploading {file_name} to the bucket')
        new_blob.upload_from_filename(filename=file_name)
    except Exception as e:
        LOGGER.exception(f'error uploading {file_name} to the bucket', e)


def get_driver():
    global w_driver
    if w_driver is None:
        options = ChromeOptions()
        options.headless = True
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(
            'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36')
        w_driver = webdriver.Chrome(options=options)
        w_driver.maximize_window()
        return w_driver
    return w_driver


def login(u_name, p_word):
    driver = get_driver()
    # check if the user is already logged in
    try:
        driver.get('https://www.airlinemanager.com/banking_account.php?id=0')
        driver.find_element(By.ID, 'bankDetailAction').text
        LOGGER.debug('already logged in, logging out')
        logout()
    except Exception as e:
        LOGGER.debug('user not logged in')
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/')
    # /html/body/div[4]/div/div[2]/div[1]/div/button[2]
    m_login_btn = None
    try:
        WebDriverWait(driver, 60).until(EC.element_to_be_clickable(
            (By.XPATH, "/html/body/div[4]/div/div[2]/div[1]/div/button[2]")))
        m_login_btn = driver.find_element(
            By.XPATH, "/html/body/div[4]/div/div[2]/div[1]/div/button[2]")
    except TimeoutException as e:
        LOGGER.exception(f'login button not found. waiting timed out.', e)
        driver.get('https://www.airlinemanager.com/')

    if m_login_btn is not None and m_login_btn.is_displayed():
        m_login_btn.click()
        email_field = driver.find_element(By.ID, 'lEmail')
        email_field.send_keys(u_name)
        pass_field = driver.find_element(By.ID, 'lPass')
        pass_field.send_keys(p_word)
        login_btn = driver.find_element(By.ID, 'btnLogin')
        login_btn.click()
        try:
            WebDriverWait(driver, 60).until(
                EC.element_to_be_clickable((By.ID, 'flightInfoToggleIcon')))
        except TimeoutException as e:
            LOGGER.exception(f'login button not found. waiting timed out.', e)
            driver.get(
                'https://www.airlinemanager.com/banking_account.php?id=0')
            if driver.find_element(By.XPATH, '/html/body/div[4]').text == 'Transaction history':
                LOGGER.info('login successful')
            else:
                LOGGER.error('login failed')
                raise Exception('login failed. Automation will exit.')
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


def get_airline_status():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/co2.php')
    classes = driver.find_element(By.ID, 'eco-state-1').get_attribute('class').split(' ')
    if 'hidden' in classes:
        return 'Eco-unfriendly'
    else:
        return 'Eco-friendly'


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
    pax_rep, cargo_rep = get_reputation()
    if get_airline_status() == 'Eco-unfriendly':
        LOGGER.warning('Airline status is "Eco-unfriendly". Not departing planes')
        return False
    if pax_rep < 80:
        LOGGER.warning(f'Airline Reputation (PAX) is {pax_rep}. Not departing planes.')
        return False
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/route_depart.php?mode=all&ids=x')
    LOGGER.info('all planes departed')
    return True


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
        if ((co2_capacity_num if co2_holding_num > 0 else co2_capacity_num - co2_holding_num) * co2_price_num)/1000 < balance:
            buy_co2(co2_capacity_num if co2_holding_num > 0 else co2_capacity_num - co2_holding_num)
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


def get_current_time_window():
    now = datetime.now(timezone.utc)
    if now.minute < 30:
        return now.strftime('%Y-%m-%d'), now.replace(minute=0, second=0, microsecond=0).strftime("%H:%M:%S %Z")
    else:
        return now.strftime('%Y-%m-%d'), now.replace(minute=30, second=0, microsecond=0).strftime("%H:%M:%S %Z")


def log_fuel_stats():
    current_month = datetime.now(timezone.utc).strftime("%b")
    current_year = datetime.now(timezone.utc).strftime("%Y")
    fuel_log_file = f'fuel_log/{current_year}/{current_month}_fuel_stats.json'
    fuel_price, _, _ = get_fuel_stats()
    co2_price, _, _ = get_co2_stats()
    LOGGER.debug(f'Fuel Price: {fuel_price}')
    LOGGER.debug(f'CO2 Price: {co2_price}')
    client = storage.Client()
    bucket = client.get_bucket(bucket_name)
    new_blob = bucket.blob(fuel_log_file)
    try:
        fuel_stats = json.loads(new_blob.download_as_text())
    except NotFound as e:
        LOGGER.exception('Fuel stats file not found in the bucket', e)
        fuel_stats = {}

    date_string, time_string = get_current_time_window()

    if date_string not in fuel_stats:
        fuel_stats[date_string] = {}
    if time_string in fuel_stats[date_string]:
        # prices already updated, so no action needed
        pass
    else:
        fuel_stats[date_string][time_string] = {
            'fuel_price': int(fuel_price.replace('$', '').replace(',', '').replace(' ', '')),
            'co2_price': int(co2_price.replace('$', '').replace(',', '').replace(' ', ''))
        }
        LOGGER.info(f'uploading {fuel_log_file} to the bucket')
        new_blob.upload_from_string(
            data=json.dumps(fuel_stats), content_type='application/json')


def maintain_lounges():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/hubs_lounge_manage.php')
    LOGGER.info('maintaining lounges')
    # get the table, loop through each row, and check the percetnage and maintain if the percentage is higher than a threshold.
    # table class is table
    table = driver.find_element_by_class_name('table')
    # get the rows, loop through each row, and check the percetnage and maintain if the percentage is higher than a threshold.
    rows = table.find_elements_by_tag_name('tr')
    for row in rows:
        lounge_id = int(row.get_attribute('id').replace('lList', ''))
        percentage = int(row.find_element(By.XPATH, 'td[2]/b').text.replace('%', ''))
        LOGGER.info(f'lounge {lounge_id} has {percentage}%')
        if percentage > lounge_maintanance_threshold:
            LOGGER.info(f'maintaining lounge {lounge_id}')
            driver.get(f'https://www.airlinemanager.com/lounge_action.php?id={lounge_id}&ref=manage')
            # call the maintaince api


def perform_routine_ops():
    # store fuel and CO2 prices
    log_fuel_stats()
    # check and perform marketing
    marketing()
    # perform fuel ops
    perform_fuel_ops()
    # perform co2 ops
    perform_co2_ops()
    # depart planes
    if depart_planes():
        # this is to handle departing more than 20 planes in one run
        depart_planes()
    # perform fuel ops
    perform_fuel_ops()
    # perform co2 ops
    perform_co2_ops()
    # perform maintenance, if needed
    check_aircrafts()
    # maintain lounges
    maintain_lounges()
    # route parked planes, if any
    route_pax_aircrafts()
    # route parked planes, if any
    route_cargo_aircrafts()
    # buy planes if there is enough money
    # buy pax planes
    buy_pax_aircrafts()
    # buy cargo planes
    buy_cargo_aircrafts()


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
                ' - ')[0], route_desc.split(' - ')[1], 'pax')[1]['realism']
            route_list.append(
                {'route_id': route_id, 'route_desc': route_desc, 'ticket_price': ticket_price})

    return route_list


def get_route_details(departure, arrival, type='pax'):
    response = requests.get(
        f'https://am4help.com/route/ticket?type={type}&mode=normal&departure={departure}&arrival={arrival}')
    if response.status_code == 200:
        route_details = json.loads(response.text)
    else:
        route_details = None
    return route_details['routes'][0], route_details['ticket']


def create_route(plane_id, route_name, destination_airport_id, economy_price, business_price, first_price):
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/new_route_info.php?mode=do&id={plane_id}&airportId={destination_airport_id}&reg={route_name}&e={economy_price}&b={business_price}&f={first_price}&stopoverId=0&ferry=0&intro=0')
    LOGGER.info(f'created pax route {route_name}')


def create_cargo_route(plane_id, route_name, destination_airport_id, large_ticket, heavy_ticket):
    driver = get_driver()
    # curl 'https://www.airlinemanager.com/new_route_info.php?mode=do&id=31068418&airportId=3568&reg=FRA-MLE&e=7.66&b=4.34&f=1&stopoverId=0&ferry=0&intro=0'
    driver.get(
        f'https://www.airlinemanager.com/new_route_info.php?mode=do&id={plane_id}&airportId={destination_airport_id}&reg={route_name}&e={large_ticket}&b={heavy_ticket}&f=1&stopoverId=0&ferry=0&intro=0')
    LOGGER.info(f'created cargo route {route_name}')


def buy_pax_aircraft(plane_id, hub_id, engine_id, plane_name, economy, business, first):
    driver = get_driver()
    driver.get(f'https://www.airlinemanager.com/ac_order_do.php?id={plane_id}&hub={hub_id}&e={economy}&b={business}&'
               f'f={first}&r={plane_name}&engine={engine_id}&amount=1')
    LOGGER.info(f'https://www.airlinemanager.com/ac_order_do.php?id={plane_id}&hub={hub_id}&e={economy}&b={business}&'
               f'f={first}&r={plane_name}&engine={engine_id}&amount=1')
    LOGGER.info(f'bought pax plane {plane_name}')


def buy_cargo_aircraft(plane_id, hub_id, engine_id, plane_name, aft, forward):
    driver = get_driver()
    driver.get(f'https://www.airlinemanager.com/ac_order_do_cargo.php?engine={engine_id}&reg={plane_name}&hub={hub_id}&acId={plane_id}&aft={aft}&fwd={forward}')
    LOGGER.info(f'bought cargo plane {plane_name}')


def check_aircrafts():
    aircrafts_to_check = []
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/maint_plan.php')
    aircraft_list = driver.find_element(By.ID, 'acListView')
    aircrafts = aircraft_list.find_elements(By.CLASS_NAME, 'maint-list-sort')
    for aircraft in aircrafts:
        try:
            aircraft_id = aircraft.find_element(
                By.XPATH, './/div[3]') .get_property('id').replace('controls', '')
            aircraft_location = aircraft.text.split('\n')[4]
            if 'a330' in aircraft.find_element(By.XPATH, './/div[1]/img') .get_property('src'):
                # plan is to decommission these plane. no need to maintain them
                continue
            if aircraft_location == 'Not at base':
                continue
            time_to_check = aircraft.text.split('\n')[6]
            if int(time_to_check) < 20:
                aircrafts_to_check.append(aircraft_id)
        except NoSuchElementException as e:
            LOGGER.exception(
                'something went wrong when checking aircraft for maintenance', e)
    for aircraft_id in aircrafts_to_check:
        check_aircraft(aircraft_id)


def get_cargo_plane_details(aircraft_type_id):
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

        large = plane_seats.split('\n')[0].split(': ')[1].replace(' Lbs', '').replace(',', '')
        heavy = plane_seats.split('\n')[1].split(': ')[1].replace(' Lbs', '').replace(',', '')

        planes_data.append({'id': plane_id, 'name': plane_name, 'departure': plane_name.split(
            '-')[0], 'arrival': plane_name.split('-')[1], 'status': plane_status, 'large': large, 'heavy': heavy})

    return planes_data


def get_pax_plane_details(aircraft_type_id):
    planes_data = []

    driver = get_driver()

    driver.get(
        f'https://www.airlinemanager.com/fleet.php?type={aircraft_type_id}')

    elements = driver.find_elements(By.XPATH, '/html/body/div[2]/div/div')

    for element in elements:
        try:
            plane_id = element.find_element(
                By.XPATH, f'.//div[1]/span').get_attribute("onclick").split(',')[1]
            plane_name = element.find_element(
                By.XPATH, f'.//div[2]/a').text
            plane_status = element.find_element(
                By.XPATH, f'.//div[4]/span').text
            plane_seats = element.find_element(
                By.XPATH, f'.//div[3]').text

            economy = plane_seats.split('\n')[0].split(': ')[1]
            business = plane_seats.split('\n')[1].split(': ')[1]
            first = plane_seats.split('\n')[2].split(': ')[1]
        except Exception as e:
            LOGGER.exception(
                'something went wrong when getting plane details', e)
            LOGGER.info(element.text)
            raise e

        planes_data.append({'id': plane_id, 'name': plane_name, 'departure': plane_name.split(
            '-')[0], 'arrival': plane_name.split('-')[1], 'status': plane_status, 'economy': economy, 'business': business, 'first': first})

    return planes_data


def get_seat_configuration(departure, arrival, max_seat_capacity, trips):
    route_details, _ = get_route_details(departure, arrival, 'pax')

    f = math.ceil(route_details['first_class_demand']/trips * 1.1) 
    b = math.ceil(route_details['business_demand']/trips * 1.1)
    e = math.ceil(route_details['economic_demand']/trips * 1.1)

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


def create_pax_routes(aircraft_type_id):
    for plane_data in get_pax_plane_details(aircraft_type_id):
        # possible vales are ['Maintenance', 'Routed', 'Pending', 'Grounded', 'Parked']
        if plane_data['status'] in ['Parked']:
            route_details, ticket_prices = get_route_details(
                plane_data['departure'], plane_data['arrival'], 'pax')
            create_route(plane_data['id'],
                         plane_data['name'], route_details['arrival']['id'], ticket_prices['realism']['ticketY'],
                         ticket_prices['realism']['ticketJ'], ticket_prices['realism']['ticketF'])


def modify_pax_aircraft(aircraft_id, economy, business, first):
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/maint_plan_do.php?mode=do&modType=pax&id={aircraft_id}&type=modify&eSeat={economy}&bSeat={business}&fSeat={first}&mod1=1&mod2=1&mod3=1')
    LOGGER.info(f'Modification scheduled for pax aircraft {aircraft_id}')


def modify_cargo_aircraft(aircraft_id, large, heavy):
    LOGGER.info(f'modifying cargo aircraft {aircraft_id} with heavy {heavy} and large {large}')
    if large != 330000:
        large = 330000
    driver = get_driver()
    # 'https://www.airlinemanager.com/maint_plan_do.php?mode=do&modType=cargo&id=31068059&type=modify&large=0&heavy=303700&mod1=1&mod2=1&mod3=1'
    driver.get(
        f'https://www.airlinemanager.com/maint_plan_do.php?mode=do&modType=cargo&id={aircraft_id}&type=modify&large={large}&heavy={heavy}&mod1=1&mod2=1&mod3=1')
    LOGGER.info(f'https://www.airlinemanager.com/maint_plan_do.php?mode=do&modType=cargo&id={aircraft_id}&type=modify&large={large}&heavy={heavy}&mod1=1&mod2=1&mod3=1')
    LOGGER.info(f'Modification scheduled for cargo aircraft {aircraft_id}')


def check_aircraft(aircraft_id):
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/maint_plan_do.php?mode=do&type=check&id={aircraft_id}')
    LOGGER.info(f'A-Check scheduled for {aircraft_id}')


def find_pax_routes(plane, hub_iata_code, plane_details, limit=1):
    airports = []

    with open('airports.json', 'r') as airports_file:
        airports = json.load(airports_file)

    routes = {}

    destinations = [plane['arrival']
                    for plane in plane_details if plane['departure'] == hub_iata_code]
    destinations.extend([plane['departure']
                    for plane in plane_details if plane['arrival'] == hub_iata_code])

    for page_number in range(1, 500):
        try:
            response = requests.get(
                f'https://am4help.com/route/search?departure={hub_iata_code}&sort=firstClass&order=desc&page={page_number}&mode=hub')
            if response.status_code == 404:
                return routes
            if response.status_code == 200 and 'routes' in response.json():
                potential_routes = response.json()['routes']
                for route in potential_routes:
                    try:
                        if route['arrival']['iata'] in destinations:
                            # this route already exists
                            continue
                        if route['distance'] > plane['range']:
                            # this route is too long for this plane
                            continue
                        trips = math.ceil(
                            23/(route['distance']/(plane['engine']['speed'] * 1.1)))
                        airport = [
                            airport for airport in airports if airport['iata'] == route['arrival']['iata']][0]
                        if airport['runway'] < plane['runway']:
                            # runway in the destination is too short for this plane
                            continue
                        if route['first_class_demand'] + route['business_demand'] + route['economic_demand'] < trips * plane['capacity']:
                            # if the combined demand is more than n*capacity, the trip is worth it. (n is the number of trips)
                            continue
                        if route['first_class_demand'] <= plane['capacity'] * 0.14 * trips * 0.95:
                            # if the first class demand is less than 18% of the capacity, the trip is not very profitable.
                            # since the routes are ordered by first class demand, it makes sense to continue checking for this hub anymore.
                            return routes
                        if route['first_class_demand'] + route['business_demand'] <= plane['capacity'] * 0.35 * trips * 0.95:
                            # the combined demand of first and business class is less than 45% of the capacity, the trip is not very profitable.
                            continue
                        e, b, f = get_seat_configuration(
                            route['departure']['iata'], route['arrival']['iata'], plane['capacity'], trips)

                        routes[f"{route['departure']['iata']}-{route['arrival']['iata']}"] = {
                            'name': f"{route['departure']['iata']}-{route['arrival']['iata']}", 'economy': e, 'business': b, 'first': f, 'distance': route['distance'], 'trips': trips}
                        if len(routes) == limit:
                            return routes
                    except Exception as e:
                        LOGGER.exception(
                            'Error processing a route from am4help', e)
        except Exception as e:
            LOGGER.exception('Error getting routes from am4help', e)
    return routes


def find_cargo_routes(plane, hub_iata_code, limit=1):
    airports = []

    with open('airports.json', 'r') as airports_file:
        airports = json.load(airports_file)

    plane_details = get_cargo_plane_details(plane['id'])

    destinations = [plane['arrival']
                    for plane in plane_details if plane['departure'] == hub_iata_code]
    destinations.extend([plane['departure']
                    for plane in plane_details if plane['arrival'] == hub_iata_code])
    routes = {}

    for page_number in range(1, 500):
        try:
            response = requests.get(
                f'https://am4help.com/route/search?departure={hub_iata_code}&sort=large&order=desc&page={page_number}&mode=hub')
            if response.status_code == 404:
                return routes
            if response.status_code == 200 and 'routes' in response.json():
                potential_routes = response.json()['routes']
                for route in potential_routes:
                    try:
                        if route['arrival']['iata'] in destinations:
                            # this route already exists
                            continue
                        if route['distance'] > plane['range']:
                            # this route is too long for this plane
                            continue
                        trips = math.ceil(
                            24/(route['distance']/(plane['engine']['speed'] * 1.1)))
                        airport = [
                            airport for airport in airports if airport['iata'] == route['arrival']['iata']][0]
                        if airport['runway'] < plane['runway']:
                            # runway in the destination is too short for this plane
                            continue
                        if ((route['large_demand'] * 1.06) / 0.7) + (route['heavy_demand'] * 1.06) < trips * plane['capacity']:
                            # if the combined demand is more than trip*capacity, the trip is worth it.
                            continue
                        if route['large_demand'] * 1.06 < plane['capacity'] * 0.7 * 0.87 * trips:
                            # if the large demand is less than 75% of the capacity, the trip is not very profitable.
                            # since the routes are ordered by first class demand, it makes sense to continue checking for this hub anymore.
                            return routes
                        if (route['large_demand'] * 1.06) / trips > plane['capacity'] * 0.7:
                            a, f = 0, 0
                        else:
                            continue
                            large_demand = (route['large_demand'] * 1.06) / trips
                            heavy_demand_pct = math.floor(((plane['capacity'] - (large_demand / 0.7))/plane['capacity'])*100)
                            a, f = math.floor(heavy_demand_pct/2), math.ceil(heavy_demand_pct/2)

                        routes[f"{route['departure']['iata']}-{route['arrival']['iata']}"] = {
                            'name': f"{route['departure']['iata']}-{route['arrival']['iata']}", 'aft': a, 'fwd': f, 'distance': route['distance'], 'trips': trips}
                        if len(routes) == limit:
                            return routes
                    except Exception as e:
                        LOGGER.exception(
                            'Error processing a route from am4help', e)
        except Exception as e:
            LOGGER.exception('Error getting routes from am4help', e)
    return routes


def get_hanger_capacity(plane_type='pax'):
    if plane_type not in ['pax', 'cargo']:
        LOGGER.exception(f'unknown plane_type {plane_type}')
        LOGGER.exception(e)
        return 0
    try:
        driver = get_driver()
        driver.get(f'https://www.airlinemanager.com/hangars.php?type={plane_type}')
        return int(driver.find_element(By.XPATH, '/html/body/div[3]/div[2]/table/tbody/tr[2]/td[3]/span').text)
    except Exception as e:
        LOGGER.exception('Error getting hanger capacity')
        LOGGER.exception(e)
        return 0


def buy_cargo_aircrafts():
    hanger_capacity = get_hanger_capacity('cargo')
    if hanger_capacity == 0:
        LOGGER.warning('No hanger capacity available. Cannot buy new cargo planes.')
        return
    planes = []
    hubs = []
    with open('planes.json', 'r') as planes_json:
        planes = json.load(planes_json)['cargo']
    with open('hubs.json', 'r') as hubs_json:
        hubs = json.load(hubs_json)
    plane = [plane for plane in planes if plane['shortname'] == cargo_plane_to_buy][0]
    random.shuffle(hubs)
    balance = get_balance()
    if balance > plane['price'] * 1.2:
        quantity = math.floor(balance / (plane['price'] * 1.1))
        if quantity > hanger_capacity:
            quantity = hanger_capacity
        LOGGER.info(f'Buying {quantity} {plane["model"]}')
        for hub in hubs:
            routes = find_cargo_routes(plane, hub['iata'], quantity)
            if routes is None or len(routes) == 0:
                continue
            if len(routes) <= quantity:
                quantity -= len(routes)
            for name, route in routes.items():
                buy_cargo_aircraft(plane['id'], hub['hub_id'], plane['engine']['id'],
                             name, route['aft'], route['fwd'])
            if quantity == 0:
                break
        if quantity != 0:
            LOGGER.info(
                f'Could not buy {quantity} {plane["model"]} as there are no possible routes left.')


def buy_pax_aircrafts():
    hanger_capacity = get_hanger_capacity('pax')
    if hanger_capacity == 0:
        LOGGER.warning('No hanger capacity available. Cannot buy new pax planes.')
        return
    planes = []
    hubs = []
    with open('planes.json', 'r') as planes_json:
        planes = json.load(planes_json)['pax']
    with open('hubs.json', 'r') as hubs_json:
        hubs = json.load(hubs_json)
    plane = [plane for plane in planes if plane['shortname'] == pax_plane_to_buy][0]
    random.shuffle(hubs)
    balance = get_balance()
    if balance > plane['price'] * 1.5:
        quantity = math.floor(balance / (plane['price'] * 1.5))
        if quantity > hanger_capacity:
            quantity = hanger_capacity
        LOGGER.info(f'Buying {quantity} {plane["model"]}')
        plane_details = get_pax_plane_details(plane['id'])

        # include a339 routes in check as well...
        plane_details.extend(get_pax_plane_details(308))

        for hub in hubs:
            routes = find_pax_routes(plane, hub['iata'], plane_details, quantity)
            if routes is None or len(routes) == 0:
                continue
            if len(routes) <= quantity:
                quantity -= len(routes)
            for name, route in routes.items():
                buy_pax_aircraft(plane['id'], hub['hub_id'], plane['engine']['id'],
                             name, route['economy'], route['business'], route['first'])
            if quantity == 0:
                break
        if quantity != 0:
            LOGGER.info(
                f'Could not buy {quantity} {plane["model"]} as there are no possible routes left.')


def route_pax_aircrafts():
    planes = []
    with open('planes.json', 'r') as planes_json:
        planes = json.load(planes_json)['pax']
    plane = [plane for plane in planes if plane['shortname'] == pax_plane_to_buy][0]
    for plane_data in get_pax_plane_details(plane['id']):
        # possible vales are ['Maintenance', 'Routed', 'Pending', 'Grounded', 'Parked']
        if plane_data['status'] in ['Parked']:
            modify_pax_aircraft(plane_data['id'], plane_data['economy'],
                            plane_data['business'], plane_data['first'])
            route_details, ticket_prices = get_route_details(
                plane_data['departure'], plane_data['arrival'], 'pax')
            create_route(plane_data['id'],
                         plane_data['name'], route_details['arrival']['id'], ticket_prices['realism']['ticketY'],
                         ticket_prices['realism']['ticketJ'], ticket_prices['realism']['ticketF'])


def route_cargo_aircrafts():
    planes = []
    with open('planes.json', 'r') as planes_json:
        planes = json.load(planes_json)['cargo']
    plane = [plane for plane in planes if plane['shortname'] == cargo_plane_to_buy][0]
    for plane_data in get_cargo_plane_details(plane['id']):
        # possible vales are ['Maintenance', 'Routed', 'Pending', 'Grounded', 'Parked']
        if plane_data['status'] in ['Parked']:
            modify_cargo_aircraft(plane_data['id'], plane_data['large'],
                            plane_data['heavy'])
            route_details, ticket_prices = get_route_details(
                plane_data['departure'], plane_data['arrival'], 'cargo')
            create_cargo_route(plane_data['id'],
                         plane_data['name'], route_details['arrival']['id'], ticket_prices['realism']['ticketL'],
                         ticket_prices['realism']['ticketH'])


def start_marketing_campaign(type, campaign, duration):
    campaign_map = {'type': {1: 'Airline', 2: 'Cargo', 5: 'Eco Friendly'},
                    'campaign': {1: '5-10%', 2: '10-18%', 3: '19-25%', 4: '25-35%'},
                    'duration': {1: '4', 2: '8', 3: '12', 4: '16', 5: '20', 6: '24'}}
    driver = get_driver()
    driver.get(
        f'https://www.airlinemanager.com/marketing_new.php?type={type}&c={campaign}&mode=do&d={duration}')
    LOGGER.info(
        f'{campaign_map["type"][type]} campaign started for {campaign_map["campaign"][campaign]} with duration {campaign_map["duration"][duration]} hours')


def get_reputation():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/marketing.php')
    pax_rep = int(driver.find_element(By.XPATH, '/html/body/div/div[1]/div[1]/div').text)
    cargo_rep = int(driver.find_element(By.XPATH, '/html/body/div/div[1]/div[2]/div').text)
    # /html/body/div/div[1]/div[1]/div
    # /html/body/div/div[1]/div[2]/div
    return pax_rep, cargo_rep


def marketing():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/marketing.php')
    campaign_table = driver.find_element(By.ID, 'active-campaigns')
    campaigns = campaign_table.find_elements(
        by=By.TAG_NAME, value='td')
    if len(campaigns) == 0:
        # start all campaigns
        start_marketing_campaign(1, 4, 3)
        start_marketing_campaign(5, 4, 3)
        # cargo marketing is not worth at this point. 
        # start_marketing_campaign(2, 4, 3)
    else:
        active_campaign = [campaign.text.strip()
                           for campaign in campaigns if campaign.text.strip() != '']
        if 'Airline reputation' not in active_campaign:
            # start airlines campaign
            start_marketing_campaign(1, 4, 3)
        if 'Eco friendly' not in active_campaign:
            # start aircraft campaign
            start_marketing_campaign(5, 4, 3)
        # cargo marketing is not worth at this point. 
        # if 'Cargo reputation' not in active_campaign:
        #     # start cargo campaign
        #     start_marketing_campaign(2, 4, 3)


@app.route('/')
def run_app():
    logout()
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

    for plane_data in get_pax_plane_details(aircraft_type_id):
        # possible vales are ['Maintenance', 'Routed', 'Pending', 'Grounded', 'Parked']
        if plane_data['status'] in ['Pending', 'Grounded', 'Maintenance']:
            continue
        if int(plane_data['economy']) + int(plane_data['business']) + int(plane_data['first']) == max_seat_capacity and int(plane_data['economy']) != max_seat_capacity and plane_data['name'] != 'DEL-ICN':
            continue

        e, b, f = get_seat_configuration(
            plane_data['departure'], plane_data['arrival'], max_seat_capacity, trips)

        if plane_data['status'] in ['Parked']:
            route_details, ticket_prices = get_route_details(
                plane_data['departure'], plane_data['arrival'], 'pax')
            create_route(plane_data['id'],
                         plane_data['name'], route_details['arrival']['id'], ticket_prices['realism']['ticketY'],
                         ticket_prices['realism']['ticketJ'], ticket_prices['realism']['ticketF'])

        if abs(e - int(plane_data['economy'])) < 5 and abs(b - int(plane_data['business'])) < 5 and abs(f - int(plane_data['first'])) < 5:
            continue

        modify_pax_aircraft(plane_data['id'], e, b, f)

    logout()


if __name__ == '__main__':
    from waitress import serve

    serve(app, host='0.0.0.0', port=8080)
