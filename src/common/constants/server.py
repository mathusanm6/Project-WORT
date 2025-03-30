"""This module contains the constants for the server of the Rasptank.
This module contains the MQTT topics used for communication between the
Rasptank and the server. The topics are used to publish and subscribe to
"""

# MQTT topics for communication with the server
INIT_TOPIC = lambda tank_id: f"tanks/{tank_id}/init"
FLAG_TOPIC = lambda tank_id: f"tanks/{tank_id}/flag"
SHOTIN_TOPIC = lambda tank_id: f"tanks/{tank_id}/shots/in"
SHOTOUT_TOPIC = lambda tank_id: f"tanks/{tank_id}/shots/out"
QR_TOPIC = lambda tank_id: f"tanks/{tank_id}/qr_code"
