import json
import requests
import datetime
import re
import pytz

def get_flights(direction_str):
    """
    Get flight information from Katowice Airport API.
    
    Args:
        direction_str: "departure" or "arrival"
        
    Returns:
        List of flight dictionaries filtered by ±12 hour window
    """
    # Validate direction
    global warsaw_tz
    warsaw_tz = pytz.timezone('Europe/Warsaw')
    direction = validate_direction(direction_str)

    # Base URL
    base_url = "https://www.katowice-airport.com/pl/api/flight-board/list/"

    # Airport codes
    airport_codes = {
        "Katowice": "KTW", "Frankfurt": "FRA", "Warsaw": "WAW",
        "Munich": "MUC", "Split": "SPU", "Reykjavík": "KEF",
        "Katania": "CTA", "Larnaka": "LCA", "Alghero": "AHO",
        "Teneryfa": "TFS", "Rzym": "FCO", "Mediolan Bergamo": "BGY",
        "Londyn Luton": "LTN"
    }

    warsaw_tz = pytz.timezone('Europe/Warsaw')
    now = datetime.datetime.now(warsaw_tz)
    dates_to_query = calculate_date_window(now)

    all_flights = []

    with requests.Session() as session:
        session.headers.update(get_headers())

        for query_date in dates_to_query:
            date_str = query_date.strftime("%Y-%m-%d")
            time_from, time_to = get_time_range(query_date, now)

            params = {
                'direction': direction,
                'date': date_str,
                'time_from': time_from,
                'time_to': time_to
            }

            try:
                response = session.get(base_url, params=params)
                
                response.raise_for_status()
                data = response.json()

                for flight_data in data.get("data", []):
                    flight = process_flight(flight_data, direction, airport_codes, warsaw_tz, query_date)
                    if flight:
                        all_flights.append(flight)

            except requests.RequestException as e:
                print(f"Error fetching {direction_str} for date {date_str}: {e}")

    return all_flights


# Helper Functions

def validate_direction(direction_str):
    direction_str = direction_str.lower().strip()
    if direction_str == "departure" or direction_str == "departures":
        return 1
    elif direction_str == "arrival" or direction_str == "arrivals":
        return 2
    else:
        raise ValueError("Direction must be 'departure' or 'arrival'")


def calculate_date_window(now):
    time_window_start = now - datetime.timedelta(hours=12)
    time_window_end = now + datetime.timedelta(hours=12)

    current_date = time_window_start.date()
    end_date = time_window_end.date()
    dates = set()

    while current_date <= end_date:
        dates.add(current_date)
        current_date += datetime.timedelta(days=1)

    return dates


def get_time_range(query_date, now):
    time_window_start = now - datetime.timedelta(hours=12)
    time_window_end = now + datetime.timedelta(hours=12)

    if query_date == time_window_start.date():
        time_from = time_window_start.strftime("%H:%M")
    else:
        time_from = "00:00"

    if query_date == time_window_end.date():
        time_to = time_window_end.strftime("%H:%M")
    else:
        time_to = "23:59"

    return time_from, time_to


def clean_flight_number(flight_number_raw) -> str:
    if not flight_number_raw:
        return "N/A"
    flight_number_raw = flight_number_raw.strip()
    if " " in flight_number_raw:
        parts = flight_number_raw.split(" ")
        code = parts[0]
        number = parts[-1]
        if number.startswith('0'):
            number = number[1:]
        return f"{code}{number}"
    elif flight_number_raw[2:].startswith('0'):
        return f"{flight_number_raw[:2]}{flight_number_raw[3:]}"
    return flight_number_raw

def parse_flight_time(time_str, date, tz):
    if not time_str:
        return "N/A"
    try:
        hour, minute = map(int, time_str.split(":"))
        dt = datetime.datetime.combine(date, datetime.time(hour, minute))
        return tz.localize(dt).isoformat(timespec='milliseconds')
    except Exception as e:
        print(f"Error parsing flight time '{time_str}': {e}")
        return "N/A"

def extract_times(status, scheduled_time, tz, query_date):
    estimated_time = "N/A"
    actual_time = "N/A"

    # Get time from status if available
    status_parts = status.split()
    if len(status_parts) > 1 and re.match(r'^\d{2}:\d{2}$', status_parts[-1]):
        time_part = status_parts[-1]
        # For both arrival and departure, status time is both estimated and actual
        time_parsed = parse_flight_time(time_part, query_date, tz)
        estimated_time = time_parsed
        actual_time = time_parsed

    # Always parse scheduled time from the scheduled_time field
    scheduled_time_parsed = parse_flight_time(scheduled_time, query_date, tz)

    return scheduled_time_parsed, estimated_time, actual_time


def is_third_char_alphabet(text):
    # Check if string has at least 3 characters
    if len(text) < 3:
        return False
    third_char = text[2]
    
    return not(third_char.isalpha())


def get_flight_iata(flight_number):
    return flight_number[:2]

def process_flight(flight_data, direction, airport_codes, tz, query_date):
    raw_flight_number = flight_data.get("flight_number", "")
    formatted_flight_number = clean_flight_number(raw_flight_number)

    # Clean airport name and airline name by removing spaces and dots
    airport_name = flight_data.get("airport", "").strip().replace(".", "")
    airline_name = flight_data.get("airline_name", "").strip().replace(".", "")
    scheduled_time = flight_data.get("scheduled_time", "")

    status = flight_data.get("status", "").strip()
    scheduled, estimated, actual = extract_times(status, scheduled_time, tz, query_date)

    if direction == 2:  # Arrival
        arrival_airport = "KTW"
        departure_airport = airport_codes.get(airport_name, airport_name.replace(" ", ""))
        return {
            "flight_number": formatted_flight_number,
            "is_flight_number": is_third_char_alphabet(formatted_flight_number),
            "callsign": formatted_flight_number,
            "airline": airline_name,
            "departure_airport": departure_airport.upper(),
            "arrival_airport": arrival_airport.upper(),
            "scheduled_arrival_time": scheduled,
            "estimated_arrival_time": estimated,
            "actual_arrival_time": actual,
            "status": status if status else "N/A",
            "airline_iata_code": get_flight_iata(formatted_flight_number) if is_third_char_alphabet(formatted_flight_number) else "N/A"
        }
    else:  # Departure
        departure_airport = "KTW"
        arrival_airport = airport_codes.get(airport_name, airport_name.replace(" ", ""))
        return {
            "flight_number": formatted_flight_number,
            "is_flight_number": is_third_char_alphabet(formatted_flight_number),
            "callsign": formatted_flight_number,
            "airline": airline_name,
            "departure_airport": departure_airport.upper(),
            "arrival_airport": arrival_airport.upper(),
            "scheduled_departure_time": scheduled,
            "estimated_departure_time": estimated,
            "actual_departure_time": actual,
            "status": status if status else "N/A",
            "airline_iata_code": get_flight_iata(formatted_flight_number) if is_third_char_alphabet(formatted_flight_number) else "N/A"
        }


def get_headers():
    return {
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json;charset=utf-8',
        'Referer': 'https://www.katowice-airport.com/pl/dla-pasazera/tablica-lotow-online ',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36'
    }


if __name__ == "__main__":
    try:
        arrivals = get_flights("arrival")
        print(f"\nTotal Arrivals: {len(arrivals)}")
        if arrivals:
            with open('arrivals.json', 'w', encoding="utf-8") as file:
                json.dump(arrivals, file, indent=4, ensure_ascii=False)
    except Exception as e:
        print("An error occurred:", e)

    try: 
        departures = get_flights("departure")
        print(f"\nTotal Departures: {len(departures)}")
        if departures:
            with open('departures.json', 'w', encoding="utf-8") as file:
                json.dump(departures, file, indent=4, ensure_ascii=False)
    except Exception as e:
        print("An error occurred:", e)
