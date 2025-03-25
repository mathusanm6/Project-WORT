"""This module contains the MQTT topics used by the Rasptank project."""

# Movement topics
MOVEMENT_COMMAND_TOPIC = "rasptank/movement/command"
MOVEMENT_STATE_TOPIC = "rasptank/movement/state"
INIT_TOPIC = lambda tank_id: f"tanks/{tank_id}/init"
FLAG_TOPIC = lambda tank_id: f"tanks/{tank_id}/flag"
SHOTIN_TOPIC = lambda tank_id: f"tanks/{tank_id}/shots/in"
SHOTOUT_TOPIC = lambda tank_id: f"tanks/{tank_id}/shots/out"
QR_TOPIC = lambda tank_id: f"tanks/{tank_id}/qr_code"
