import uuid

tank_id = hex(uuid.getnode())
TANK_ID = (
    str(tank_id)[:15]
    if len(str(tank_id)) > 15
    else (
        str(tank_id) if len(str(tank_id)) == 15 else str(tank_id) + ("0" * (15 - len(str(tank_id))))
    )
)
