import time
from rasptank.movement.movement_factory import MovementFactory, MovementControllerType
from rasptank.movement.default_movement_controller import DefaultMovementController
from rasptank.movement.movement_api import ThrustDirection, TurnDirection

def setup():
    return MovementFactory.create_movement_controller(MovementControllerType.DEFAULT)
    
def do_stunt(default_movement_controller: DefaultMovementController):
    try:
        # Move forward at 50% speed
        print("Moving forward at 50% speed...")
        default_movement_controller.move(ThrustDirection.FORWARD, TurnDirection.NONE, 50.0, 0.0)
        time.sleep(2)
        
        # Turn right while moving forward
        print("Turning right...")
        default_movement_controller.move(ThrustDirection.FORWARD, TurnDirection.RIGHT, 50.0, 0.8)
        time.sleep(2)
        
        # Turn left while moving forward
        print("Turning left...")
        default_movement_controller.move(ThrustDirection.FORWARD, TurnDirection.LEFT, 50.0, 0.8)
        time.sleep(2)
        
        # Spin in place (left)
        print("Spinning left...")
        default_movement_controller.move(ThrustDirection.NONE, TurnDirection.LEFT, 50.0, 1.0)
        time.sleep(2)
        
        # Timed movement (move backward for 1.5 seconds)
        print("Moving backward for 1.5 seconds...")
        default_movement_controller.move(ThrustDirection.BACKWARD, TurnDirection.NONE, 50.0, 0.0)
        time.sleep(2)  # Wait for the timed movement to complete
        
        # Stop
        print("Stopping...")
        default_movement_controller.stop()
        
    except KeyboardInterrupt:
        print("Program interrupted")
    finally:
        # Clean up
        default_movement_controller.cleanup()

if __name__ == "__main__":
    default_movement_controller = setup()
    do_stunt(default_movement_controller)