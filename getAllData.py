import serial
import time
import argparse
import paho.mqtt.client as mqtt
import signal
import sys

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

def parse_total_voltage(response):
    start_time = time.time()
    try:
        index_of_83 = response.index(0x83)
        print(f"Found 0x83 at position: {index_of_83}")
        total_voltage_high = response[index_of_83 + 1]
        total_voltage_low = response[index_of_83 + 2]
        total_voltage = ((total_voltage_high << 8) | total_voltage_low) * 0.01
        print(f"Total voltage (V): {total_voltage}")
        print(f"Total voltage parsing took: {time.time() - start_time:.4f} seconds")
        return total_voltage
    except ValueError:
        print("0x83 not found in the response.")
        return None

def parse_soc(response):
    start_time = time.time()
    try:
        index_of_85 = response.index(0x85)
        print(f"Found 0x85 at position: {index_of_85}")
        soc_value = response[index_of_85 + 1]
        print(f"SOC (State of Charge): {soc_value}%")
        print(f"SOC parsing took: {time.time() - start_time:.4f} seconds")
        return soc_value
    except ValueError:
        print("0x85 not found in the response.")
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
        print("0x84 not found in the response.")
        return None
    finally:
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
        print(f"Battery strings parsing took: {time.time() - start_time:.4f} seconds")
        return total_strings
    except ValueError:
        print("0x8A not found in the response.")
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
        print(f"Cell voltage parsing took: {time.time() - start_time:.4f} seconds")
        return cell_voltages
    except ValueError:
        print("0x79 not found in the response.")
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

# Funkce pro sběr a odesílání dat
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

        full_response = s.read(100)
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

            if args.output == "mqtt":
                send_data_to_mqtt(total_voltage, current_value, delta_voltage, cell_voltages, soc_value)

        interpret_time = time.time() - interpret_start_time
        print(f"Data interpretation took: {interpret_time:.4f} seconds")

# Parsing command-line arguments
parser = argparse.ArgumentParser(description="Monitor BMS data and optionally send it via MQTT.")
parser.add_argument("-o", "--output", choices=["mqtt", "none"], default="none", help="Send output to MQTT")
parser.add_argument("-d", "--daemon", action="store_true", help="Run script as daemon")
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
