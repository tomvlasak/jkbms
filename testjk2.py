import serial
import time

# Funkce pro výpočet kontrolního součtu (CRC)
def crc(byteData):
    CRC = 0
    for b in byteData:
        CRC += b
    crc_byte4 = CRC & 0xFF
    crc_byte3 = (CRC >> 8) & 0xFF
    print(f"CRC: {crc_byte3:02x} {crc_byte4:02x}")
    return [crc_byte3, crc_byte4]

# Funkce pro čtení celé odpovědi
def read_full_response(serial_port):
    response = bytearray()
    start_time = time.time()
    serial_port.timeout = 0.5  # Nastavíme kratší timeout pro čtení
    while True:
        data = serial_port.read(212)  # Čteme až 1024 bajtů najednou
        response.extend(data)
        if len(data) < 212:
            # Pokud jsme přečetli méně než 1024 bajtů, pravděpodobně už žádná data nejsou
            break
        # Přidáme kontrolu, aby smyčka neskončila nekonečně
        if time.time() - start_time > 2:
            break
    print(f"Got response: {response.hex()}")
    return response

# Nastavení rámce pro čtení dat
command_READ_ALL_DATA = b'\x06'
source_HOST_PC = b'\x03'
tx_type_READ_DATA = b'\x00'
frame_STX = b'\x4E\x57'
frame_LENGTH = b'\x00\x13'
frame_BMS_ID = b'\x00\x00\x00\x00'
frame_INFO_READ = b'\x00'
frame_REC_NUM = b'\x00\x00\x00\x00'
frame_END_FLAG = b'\x68'

# Vytvoření rámce
request_FRAME = bytearray()
request_FRAME += frame_STX
request_FRAME += frame_LENGTH
request_FRAME += frame_BMS_ID
request_FRAME += command_READ_ALL_DATA
request_FRAME += source_HOST_PC
request_FRAME += tx_type_READ_DATA
request_FRAME += frame_INFO_READ
request_FRAME += frame_REC_NUM
request_FRAME += frame_END_FLAG

# Výpočet a přidání CRC do rámce
crc_byte3, crc_byte4 = crc(request_FRAME)
request_FRAME += b'\x00\x00'  # frame_CRC_HIGH
request_FRAME += bytes([crc_byte3, crc_byte4])  # frame_CRC_LOW

# Nastavení sériového portu
port = "/dev/ttyUSB0"  # Uprav dle potřeby
baud = 115200

with serial.Serial(port, baudrate=baud, timeout=1) as s:
    s.flushInput()
    s.flushOutput()
    print(f"sending command: {request_FRAME.hex()}")
    bytes_written = s.write(request_FRAME)
    print(f"wrote {bytes_written} bytes")

    # Čtení celé odpovědi
    full_response = read_full_response(s)

    # Výpis odpovědi po částech pro lepší přehled
    print("Hex response (split by bytes):")
    for i in range(0, len(full_response), 16):
        print(full_response[i:i+16].hex())

    # Pokus o nalezení SW verze
    if len(full_response) > 0:
        try:
            # Hledání indexu 0xB7
            index_of_b7 = full_response.index(0xB7)
            # Čtení následujících bajtů jako SW verzi
            sw_version_bytes = full_response[index_of_b7 + 1:index_of_b7 + 16]
            sw_version = sw_version_bytes.decode('ascii', errors='replace').strip('\x00')
            print(f"SW Version: {sw_version}")
        except ValueError:
            print("SW version not found in the response.")
    else:
        print("No response received.")
