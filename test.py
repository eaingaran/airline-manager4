import airline_manager4 as am4
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def print_routes():
    am4.login(am4.username, am4.password)

    routes = am4.get_routes()
    del_map = {}
    fra_map = {}
    lax_map = {}
    for route in routes:
        print(route['route_desc'])
        arrival = route['route_desc'].split(' - ')[1]
        departure = route['route_desc'].split(' - ')[0]
        if 'EDDF' in [arrival, departure]:
            if arrival == 'EDDF':
                if departure in fra_map:
                    fra_map[departure] = fra_map[departure] + 1
                else:
                    fra_map[departure] = 1
            else:
                if arrival in fra_map:
                    fra_map[arrival] = fra_map[arrival] + 1
                else:
                    fra_map[arrival] = 1
        elif 'KLAX' in [arrival, departure]:
            if arrival == 'KLAX':
                if departure in lax_map:
                    lax_map[departure] = lax_map[departure] + 1
                else:
                    lax_map[departure] = 1
            else:
                if arrival in lax_map:
                    lax_map[arrival] = lax_map[arrival] + 1
                else:
                    lax_map[arrival] = 1
        elif 'VIDP' in [arrival, departure]:
            if arrival == 'VIDP':
                if departure in del_map:
                    del_map[departure] = del_map[departure] + 1
                else:
                    del_map[departure] = 1
            else:
                if arrival in del_map:
                    del_map[arrival] = del_map[arrival] + 1
                else:
                    del_map[arrival] = 1
        else:
            print(f'route {route["route_desc"]} is not from any hub')

    print('Delhi airport departures')
    for k, v in del_map.items():
        print(f'{k} has {v} flights')
    print('LAX airport departures')
    for k, v in lax_map.items():
        print(f'{k} has {v} flights')
    print('FRA airport departures')
    for k, v in fra_map.items():
        print(f'{k} has {v} flights')

    am4.logout()


def buy_planes():
    hubs = {
        'London Heathrow intl': 3582640,
        'Frankfurt intl': 3353515,
        'Los Angeles': 3458942,
        'New Delhi': 3502287,
        'Abu Dhabi Int': 3523007,
        'St. Petersburg': 3538538,
        'Long Beach': 3541183,
        'Chennai': 3541222,
        'Conakry': 3648482
    }
    planes = {
        'MC-21-400': 344,
        'A330-900neo': 308,
    }
    am4.login(am4.username, am4.password)

    with open('new_planes.txt', 'r') as planes:
        for plane in planes:
            all_val = plane.split(' - ')
            plane_val = all_val[2].split(',')
            am4.buy_aircraft(344, 3648482, 312, f'{all_val[0]}', int(plane_val[0]), int(plane_val[1]),
                             int(plane_val[2]))

    am4.logout()


def update_ticket_price():
    am4.update_ticket_price()


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

    # update_ticket_price()
    # buy_planes()
    # print_routes()
