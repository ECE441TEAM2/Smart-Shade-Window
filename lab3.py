import socket
import thingspeak

# Your HC-06 MAC Address
bluetooth_addr = "0022020146E9"
bluetooth_port = 1 # RFCOMM channel 1

# Thingspeak information
channel_id = 3098272
key = "3JKMGDAIA64481F5"
url = "https://api.thingspeak.com/update"

# Initialize Thingspeak channel
ts = thingspeak.Channel(channel_id, key, url)

# Create a Bluetooth socket
bluetooth_socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO.RFCOMM)
bluetooth_socket.connect((bluetooth_addr, bluetooth_port))

try:
    while True:
        received_data = bluetooth_socket.recv(1)
        temperature = int.from_bytes(received_data, byteorder='big')
        print("Current Temperature: %d" % temperature)
        thingspeak_field1 = {"field1": temperature}
        ts.update(thingspeak_field1)

except KeyboardInterrupt:
    print("Keyboard interrupt detected")
    
except Exception as e:
    print(f"An error occurred: {e}")

finally:
    bluetooth_socket.close()