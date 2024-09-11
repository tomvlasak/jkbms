import serial
import time
import argparse
import paho.mqtt.client as mqtt
import signal
import sys
import struct

# Checksum 4bytes, bytes 1-2 0000 not used, bytes 3-4 cumulative total
def crc(byteData):
    start_time = time.time()
    CRC = 0
    for b in byteData:
        CRC += b
    crc_byte4 = CRC & 0xFF
    crc_byte3 = (CRC >> 8) & 0xFF
    print(f"CRC calculation took: {time.time() - start_time:.4f} seconds")
    return [crc_byte3, crc_byte4]

def decode_temperature(temp_raw):
    if temp_raw <= 100:
        return temp_raw  # Kladná teplota
    else:
        return -(temp_raw - 100)  # Záporná teplota

def parse_temperature_sensor_count(response):
    try:
        index_of_86 = response.index(0x86)
        sensor_count = response[index_of_86 + 1]
        print(f"Number of temperature sensors: {sensor_count}")
        return sensor_count
    except ValueError:
        print("\033[91m0x86 not found in the response.\033[0m")
        return None

def parse_temperature_sensors(response):
    try:
        index_of_80 = response.index(0x80)
        power_tube_temp = struct.unpack('>H', response[index_of_80 + 1:index_of_80 + 3])[0]
        power_tube_temp_c = decode_temperature(power_tube_temp)
        print(f"Power tube temperature: {power_tube_temp_c} °C")

        index_of_81 = response.index(0x81)
        battery_box_temp = struct.unpack('>H', response[index_of_81 + 1:index_of_81 + 3])[0]
        battery_box_temp_c = decode_temperature(battery_box_temp)
        print(f"Battery box temperature: {battery_box_temp_c} °C")

        index_of_82 = response.index(0x82)
        battery_temp = struct.unpack('>H', response[index_of_82 + 1:index_of_82 + 3])[0]
        battery_temp_c = decode_temperature(battery_temp)
        print(f"Battery temperature: {battery_temp_c} °C")

        return power_tube_temp_c, battery_box_temp_c, battery_temp_c
    except ValueError:
        print("Temperature data not found in the response.")
        return None, None, None

def parse_total_voltage(response):
    start_time = time.time()
    try:
        index_of_83 = response.index(0x83)
        print(f"Found 0x83 at position: {index_of_83}")
        
        # Využití struct pro přečtení 2 bajtů jako unsigned short (16 bitů) big-endian
        total_voltage_raw = struct.unpack_from('>H', response, index_of_83 + 1)[0]
        total_voltage = total_voltage_raw * 0.01
        
        print(f"Total voltage (V): {total_voltage}")
        if args.ptime == "show":
         print(f"Total voltage parsing took: {time.time() - start_time:.4f} seconds")
        return total_voltage
    except ValueError:
        print("\033[91m0x83 not found in the response.\033[0m")
        return None

def parse_soc(response):
    start_time = time.time()
    try:
        index_of_85 = response.index(0x85)
        print(f"Found 0x85 at position: {index_of_85}")
        soc_value = response[index_of_85 + 1]
        print(f"SOC (State of Charge): {soc_value}%")
        if args.ptime == "show":
         print(f"SOC parsing took: {time.time() - start_time:.4f} seconds")
        return soc_value
    except ValueError:
        print("\033[91m0x85 not found in the response.\033[0m")
        return None

def parse_current(response):
    start_time = time.time()
    try:
        index_of_84 = response.index(0x84)
        print(f"Found 0x84 at position: {index_of_84}")
        current_high = response[index_of_84 + 1]
        current_low = response[index_of_84 + 2]
        current_raw = (current_high << 8) | current_low

        print(f"Current high byte: {current_high} (hex: {hex(current_high)})")
        print(f"Current low byte: {current_low} (hex: {hex(current_low)})")
        print(f"Raw current data: {current_raw} (hex: {hex(current_raw)})")

        if current_raw <= 10000:
            current = ((10000 - current_raw) * 0.01) - 100
            print(f"Current (discharging): {current} A")
            return -current
        elif current_raw >= 32768:
            current = (current_raw - 32768 - 10000) * 0.01
            if current_raw > 32768:
                current = (current_raw - 32768) * 0.01
            print(f"Current (charging): {current} A")
            return current
        else:
            print("Current data outside expected range")
            return None
    except ValueError:
        print("\033[91m0x84 not found in the response.\033[0m")
        return None
    finally:
        if args.ptime == "show":
         print(f"Current parsing took: {time.time() - start_time:.4f} seconds")

def parse_total_battery_strings(response):
    start_time = time.time()
    try:
        index_of_8a = response.index(0x8a)
        print(f"Found 0x8A at position: {index_of_8a}")
        strings_high = response[index_of_8a + 1]
        strings_low = response[index_of_8a + 2]
        total_strings = (strings_high << 8) | strings_low
        print(f"Total number of battery strings: {total_strings}")
        if args.ptime == "show":
         print(f"Battery strings parsing took: {time.time() - start_time:.4f} seconds")
        return total_strings
    except ValueError:
        print("\033[91m0x8A not found in the response.\033[0m")
        return None

def parse_individual_cell_voltage(response):
    start_time = time.time()
    try:
        index_of_79 = response.index(0x79)
        print(f"Found 0x79 at position: {index_of_79}")
        length_of_data = response[index_of_79 + 1]
        cell_voltages = []
        for i in range(0, length_of_data, 3):
            cell_number = response[index_of_79 + 2 + i]
            voltage_high = response[index_of_79 + 2 + i + 1]
            voltage_low = response[index_of_79 + 2 + i + 2]
            voltage_mv = (voltage_high << 8) | voltage_low
            voltage_v = voltage_mv / 1000.0
            cell_voltages.append((cell_number, voltage_v))
            print(f"Cell {cell_number} voltage: {voltage_v} V")
        if args.ptime == "show":
         print(f"Cell voltage parsing took: {time.time() - start_time:.4f} seconds")
        return cell_voltages
    except ValueError:
        print("\033[91m0x79 not found in the response.\033[0m")
        return None

def calculate_delta_voltage(cell_voltages):
    if not cell_voltages:
        print("No cell voltage data available.")
        return None

    min_cell = min(cell_voltages, key=lambda x: x[1])
    max_cell = max(cell_voltages, key=lambda x: x[1])
    delta_voltage = max_cell[1] - min_cell[1]
    print(f"Delta voltage: {delta_voltage:.3f} V (Max: Cell {max_cell[0]} - {max_cell[1]:.3f} V, Min: Cell {min_cell[0]} - {min_cell[1]:.3f} V)")
    return delta_voltage

def parse_software_version(response):
    start_time = time.time()
    try:
        index_of_b7 = response.index(0xb7)
        print(f"Found 0xB7 at position: {index_of_b7}")
        version_data = response[index_of_b7 + 1:index_of_b7 + 16].decode("utf-8")
        print(f"Software version number: {version_data}")
        if args.ptime == "show":
         print(f"Software version parsing took: {time.time() - start_time:.4f} seconds")
        return version_data
    except ValueError:
        print("\033[91m0xB7 not found in the response.\033[0m")
        return None

def parse_actual_battery_capacity(response):
    start_time = time.time()
    try:
        index_of_b9 = response.index(0xb9)
        print(f"Found 0xB9 at position: {index_of_b9}")
        capacity_high = response[index_of_b9 + 1]
        capacity_low = response[index_of_b9 + 2]
        actual_capacity = (capacity_high << 8) | capacity_low
        print(f"Actual battery capacity: {actual_capacity} AH")
        if args.ptime == "show":
         print(f"Actual battery capacity parsing took: {time.time() - start_time:.4f} seconds")
        return actual_capacity
    except ValueError:
        print("\033[91m0xB9 not found in the response.\033[0m")
        return None

def parse_protocol_version(response):
    start_time = time.time()
    try:
        index_of_c0 = response.index(0xc0)
        print(f"Found 0xC0 at position: {index_of_c0}")
        protocol_version = response[index_of_c0 + 1]
        print(f"Protocol version number: {protocol_version}")
        if args.ptime == "show":
         print(f"Protocol version parsing took: {time.time() - start_time:.4f} seconds")
        return protocol_version
    except ValueError:
        print("\033[91m0xC0 not found in the response.\033[0m")
        return None

def parse_current_calibration(response):
    start_time = time.time()
    try:
        index_of_ad = response.index(0xad)
        print(f"Found 0xAD at position: {index_of_ad}")
        calibration_high = response[index_of_ad + 1]
        calibration_low = response[index_of_ad + 2]
        calibration_value = (calibration_high << 8) | calibration_low
        print(f"Current calibration: {calibration_value} mA")
        if args.ptime == "show":
         print(f"Current calibration parsing took: {time.time() - start_time:.4f} seconds")
        return calibration_value
    except ValueError:
        print("\033[91m0xAD not found in the response.\033[0m")
        return None

def parse_current_calibration_status(response):
    start_time = time.time()
    try:
        # Najdeme index 0xB8 v odpovědi
        index_of_b8 = response.index(0xb8)
        print(f"Found 0xB8 at position: {index_of_b8}")

        # Čteme 1 bajt, který udává stav kalibrace
        calibration_status = response[index_of_b8 + 1]

        # Vyhodnotíme stav kalibrace
        if calibration_status == 1:
            print(f"Current calibration: STARTED")
        elif calibration_status == 0:
            print(f"Current calibration: STOPPED")
        else:
            print(f"Unknown calibration status: {calibration_status}")
        if args.ptime == "show":
         print(f"Current calibration status parsing took: {time.time() - start_time:.4f} seconds")
        return calibration_status
    except ValueError:
        print("\033[91m0xB8 not found in the response.\033[0m")  # Červeně pro chybovou zprávu
        return None

def parse_active_balance_switch(response):
    start_time = time.time()
    try:
        index_of_9d = response.index(0x9d)
        print(f"Found 0x9D at position: {index_of_9d}")
        active_balance_switch = response[index_of_9d + 1]
        print(f"Active balance switch: {'ON' if active_balance_switch == 1 else 'OFF'}")
        if args.ptime == "show":
         print(f"Active balance switch parsing took: {time.time() - start_time:.4f} seconds")
        return active_balance_switch
    except ValueError:
        print("\033[91m0x9D not found in the response.\033[0m")
        return None



def parse_battery_warning(response):
    try:
        index_of_8b = response.index(0x8B)
        print(f"Found 0x8B at position: {index_of_8b}")
        warning_high = response[index_of_8b + 1]
        warning_low = response[index_of_8b + 2]
        warning_raw = (warning_high << 8) | warning_low

        print(f"Battery warning raw data: {warning_raw} (hex: {hex(warning_raw)})")

        # Dekódování jednotlivých bitů
        warning_messages = {
            0: "Low capacity alarm",
            1: "MOS tube overtemperature alarm",
            2: "Charging overvoltage alarm",
            3: "Discharge undervoltage alarm",
            4: "Battery over temperature alarm",
            5: "Charging overcurrent alarm",
            6: "Discharge overcurrent alarm",
            7: "Cell differential pressure alarm",
            8: "Overtemperature alarm in battery box",
            9: "Battery low temperature alarm",
            10: "Monomer overvoltage alarm",
            11: "Monomer undervoltage alarm",
            12: "309_A protection alarm",
            13: "309_B protection alarm",
            14: "Reserved",
            15: "Reserved"
        }

        for bit, message in warning_messages.items():
            if warning_raw & (1 << bit):
                print(f"Warning: {message}")
            else:
                print(f"Normal: {message}")

        return warning_raw
    except ValueError:
        print("\033[91m0x8B not found in the response.\033[0m")
        return None


def send_data_to_mqtt(voltage, current, delta_voltage, cell_voltages, soc):
    mqtt_broker = "127.0.0.1"
    mqtt_port = 1883
    mqtt_topic = "jkbms-test"

    client = mqtt.Client()
    client.connect(mqtt_broker, mqtt_port, 60)

    # Rozbalíme jednotlivé napětí článků pro odeslání
    cell_voltage_data = ",".join([f"voltage_cell{cell[0]}={cell[1]}" for cell in cell_voltages])

    # Přidáme SOC do zprávy
    data = f"battery_measurements voltage={voltage},current={current},delta_voltage={delta_voltage},soc={soc},{cell_voltage_data}"
    client.publish(mqtt_topic, data)
    print(f"Data o napětí {voltage} V, proudu {current} A, delta napětí {delta_voltage} V, SOC {soc}% a napětí článků byla odeslána na MQTT téma '{mqtt_topic}'.")

    client.disconnect()




# Přidáme funkci pro zachycení signálu ukončení (Ctrl+C)
def signal_handler(sig, frame):
    print("Exiting daemon...")
    sys.exit(0)

# Hlavní funkce pro interpretaci všech dat
def gather_and_send_data():
    with serial.serial_for_url(port, baud) as s:
        s.timeout = 0.5
        s.write_timeout = 0.5
        s.flushInput()
        s.flushOutput()

        read_start_time = time.time()
        print(f"sending command: {request_FRAME.hex()}")
        bytes_written = s.write(request_FRAME)
        print(f"wrote {bytes_written} bytes")

        full_response = s.read(300)
        read_time = time.time() - read_start_time
        print(f"Full response: {full_response.hex()}")
        print(f"Response read took: {read_time:.4f} seconds")

        interpret_start_time = time.time()

        if len(full_response) > 38:
            total_voltage = parse_total_voltage(full_response)
            soc_value = parse_soc(full_response)
            current_value = parse_current(full_response)
            total_strings = parse_total_battery_strings(full_response)
            cell_voltages = parse_individual_cell_voltage(full_response)
            delta_voltage = calculate_delta_voltage(cell_voltages)

            # Nové funkce pro čtení dalších dat
            software_version = parse_software_version(full_response)
            actual_battery_capacity = parse_actual_battery_capacity(full_response)
            protocol_version = parse_protocol_version(full_response)
            current_calibration = parse_current_calibration(full_response)
            current_calibration_status=parse_current_calibration_status(full_response)
            active_balance_switch = parse_active_balance_switch(full_response)
            battery_warn = parse_battery_warning(full_response)
            temp_data=parse_temperature_sensors(full_response)
            temp_sensor_count=parse_temperature_sensor_count(full_response)

            if args.output == "mqtt":
                send_data_to_mqtt(total_voltage, current_value, delta_voltage, cell_voltages, soc_value)

        interpret_time = time.time() - interpret_start_time
        print(f"Data interpretation took: {interpret_time:.4f} seconds")

# Parsing command-line arguments
parser = argparse.ArgumentParser(description="Monitor BMS data and optionally send it via MQTT.")
parser.add_argument("-o", "--output", choices=["mqtt", "none"], default="none", help="Send output to MQTT")
parser.add_argument("-d", "--daemon", action="store_true", help="Run script as daemon")
parser.add_argument("-t", "--ptime", choices=["show", "none"], default="none", help="Print time")
args = parser.parse_args()

# Zaregistrujeme signal handler pro Ctrl+C
signal.signal(signal.SIGINT, signal_handler)


# 4.2.4 COMMAND codes
command_READ_ALL_DATA = b'\x06'
source_HOST_PC = b'\x03'
tx_type_READ_DATA = b'\x00'
frame_STX = b'\x4E\x57'
frame_LENGTH = b'\x00\x13'
frame_BMS_ID = b'\x00\x00\x00\x00'
frame_INFO_READ = b'\x00'
frame_REC_NUM = b'\x00\x00\x00\x00'
frame_END_FLAG = b'\x68'
frame_CRC_HIGH = b'\x00\x00'
frame_CRC_LOW = bytearray(2)

# Start script execution
script_start_time = time.time()

# Create the request frame
request_FRAME = bytearray()
request_FRAME[0:2] = frame_STX
request_FRAME[2:2] = frame_LENGTH
request_FRAME[4:4] = frame_BMS_ID
request_FRAME[8:1] = command_READ_ALL_DATA
request_FRAME[9:1] = source_HOST_PC
request_FRAME[10:1] = tx_type_READ_DATA
request_FRAME[11:1] = frame_INFO_READ
request_FRAME[12:4] = frame_REC_NUM
request_FRAME[16:1] = frame_END_FLAG

# Calculate CRC and insert into the frame
crc_byte3, crc_byte4 = crc(request_FRAME[0:17])
frame_CRC_LOW[0] = crc_byte3
frame_CRC_LOW[1] = crc_byte4
request_FRAME[17:2] = frame_CRC_HIGH
request_FRAME[19:2] = frame_CRC_LOW

port = "/dev/ttyUSB0"
baud = 115200

# Hlavní smyčka skriptu
if args.daemon:
    print("Running in daemon mode...")
    while True:
        gather_and_send_data()
        time.sleep(0.2)  # 5x za sekundu
else:
    print("Running once...")
    gather_and_send_data()

print(f"Total script execution time: {time.time() - script_start_time:.4f} seconds")
