import os

from flask import Flask

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


app_name = 'Airline Manager Automation'

app = Flask(app_name)

username = os.environ.get('USERNAME')
password = os.environ.get('PASSWORD')
fuel_price_threshold = os.environ.get('MAX_BUY_FUEL_PRICE')
co2_price_threshold = os.environ.get('MAX_BUY_CO2_PRICE')

w_driver = None


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
    driver.get('https://www.airline4.net/')
    m_login_btn = driver.find_element(By.XPATH, '/html/body/div[3]/div[1]/div[5]/button[1]')
    if m_login_btn is not None and m_login_btn.is_displayed():
        m_login_btn.click()
        email_field = driver.find_element(By.ID, 'lEmail')
        email_field.send_keys(u_name)
        pass_field = driver.find_element(By.ID, 'lPass')
        pass_field.send_keys(p_word)
        login_btn = driver.find_element(By.ID, 'btnLogin')
        login_btn.click()
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, 'flightInfoToggleIcon')))


def logout():
    global w_driver
    if w_driver is not None:
        w_driver.get('https://www.airline4.net/weblogin/logout.php')
        w_driver.quit()
        w_driver = None


def get_fuel_stats():
    driver = get_driver()
    driver.get('https://www.airline4.net/fuel.php')
    price = driver.find_element(By.XPATH, '/html/body/div/div/div[1]/span[2]/b').text
    capacity = driver.find_element(By.ID, 'remCapacity').text
    print(f'Capacity Remaining is {capacity} and current fuel price is {price}')
    return price, capacity


def get_co2_stats():
    driver = get_driver()
    driver.get('https://www.airline4.net/co2.php')
    price = driver.find_element(By.XPATH, '/html/body/div/div/div[2]/span[2]/b').text
    capacity = driver.find_element(By.ID, 'remCapacity').text
    print(f'Capacity Remaining is {capacity} and current co2 price is {price}')
    return price, capacity


def depart_planes():
    driver = get_driver()
    driver.get('https://www.airline4.net/route_depart.php?mode=all&ids=x')
    print('all planes departed')


def get_balance():
    driver = get_driver()
    driver.get('https://www.airline4.net/')
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, 'headerAccount')))
    balance = driver.find_element(By.ID, 'headerAccount').text
    print(f'Account balance is {balance}')
    return int(balance.replace(',', ''))


def buy_fuel(quantity):
    driver = get_driver()
    driver.get(f'https://www.airline4.net/fuel.php?mode=do&amount={quantity}')
    print(f'bought {quantity} fuel')


def buy_co2(quantity):
    driver = get_driver()
    driver.get(f'https://www.airline4.net/co2.php?mode=do&amount={quantity}')
    print(f'bought {quantity} co2 quota')


def perform_routine_ops():
    # depart planes
    depart_planes()

    # fuel checks
    fuel_price, fuel_capacity = get_fuel_stats()
    fuel_price_num = int(fuel_price.replace('$', '').replace(',', '').replace(' ', ''))
    fuel_capacity_num = int(fuel_capacity.replace(',', '').replace(' ', ''))
    if fuel_price_num < 400 if fuel_price_threshold is None else int(fuel_price_threshold):
        balance = get_balance()
        if (fuel_capacity_num * fuel_price_num)/1000 < balance:
            buy_fuel(fuel_capacity_num)
            pass
        else:
            purchase_qty = (balance * 1000) / fuel_price_num
            buy_fuel(purchase_qty)
    else:
        print(f'fuel price is too high to buy...')

    # co2 checks
    co2_price, co2_capacity = get_co2_stats()
    co2_price_num = int(co2_price.replace('$', '').replace(',', '').replace(' ', ''))
    co2_capacity_num = int(co2_capacity.replace(',', '').replace(' ', ''))
    if co2_price_num < 111 if co2_price_threshold is None else int(co2_price_threshold):
        balance = get_balance()
        if (co2_capacity_num * co2_price_num)/1000 < balance:
            buy_co2(co2_capacity_num)
            pass
        else:
            purchase_qty = (balance * 1000)/co2_price_num
            buy_co2(purchase_qty)
    else:
        print(f'co2 price is too high to buy...')


@app.route('/')
def run_app():
    login(username, password)
    perform_routine_ops()
    logout()
    return 'All Done!', 200


if __name__ == '__main__':
    from waitress import serve

    serve(app, host='0.0.0.0', port=8080)
