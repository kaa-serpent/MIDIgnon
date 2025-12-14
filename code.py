import board
import digitalio
import analogio
import pwmio
import usb_midi
import adafruit_midi
from adafruit_midi.note_on import NoteOn
from adafruit_midi.note_off import NoteOff
from adafruit_midi.control_change import ControlChange
import time
import math

DEBUG = False  # Set to False to disable serial debug prints

# Initialize MIDI
midi = adafruit_midi.MIDI(
    midi_out=usb_midi.ports[1],
    out_channel=0
)
pot_buffers = [[0, 0, 0, 0] for _ in range(3)]

# LED setup
# GP9: Simple on/off for 12V LED strip (no PWM dimming without MOSFET)
try:
    led_strip = digitalio.DigitalInOut(board.GP9)
    led_strip.direction = digitalio.Direction.OUTPUT
    has_gp9 = True
    print("GP9 LED initialized (on/off mode)")
except Exception as e:
    has_gp9 = False
    print(f"GP9 not available: {e}")

# Onboard LED: PWM for smooth breathing
try:
    led_onboard = pwmio.PWMOut(board.LED, frequency=1000, duty_cycle=0)
    has_onboard = True
    print("Onboard LED initialized (PWM mode)")
except Exception as e:
    has_onboard = False
    print(f"Onboard LED not available: {e}")

# LED animation variables
led_brightness = 0
led_direction = 1
breathing_speed = 0.01
blink_timer = 0
blink_duration = 0.6  # Total blink duration
blink_fade_speed = 0.05  # Speed of fade in/out

# Button setup (GP0-GP8)
buttons = []
button_pins = [board.GP0, board.GP1, board.GP2, board.GP3, board.GP4,
               board.GP5, board.GP6, board.GP7, board.GP8]
button_states = [False] * 9
note_numbers = [60, 62, 64, 65, 67, 69, 71, 72, 74]  # C major scale

for pin in button_pins:
    btn = digitalio.DigitalInOut(pin)
    btn.direction = digitalio.Direction.INPUT
    btn.pull = digitalio.Pull.DOWN
    buttons.append(btn)

# Potentiometer setup (GP26-GP28)
pots = []
pot_pins = [board.GP26, board.GP27, board.GP28]
pot_values = [0] * 3
cc_numbers = [1, 2, 3]

for pin in pot_pins:
    pot = analogio.AnalogIn(pin)
    pots.append(pot)


MIN_ADC = [4080, 4080, 4080]  # replace with measured min for each pot
MAX_ADC = [65535, 65535, 65535]  # replace with measured max

def read_pot(pot, index):
    buf = pot_buffers[index]
    buf.pop(0)
    buf.append(pot.value)
    raw = sum(buf) // len(buf)

    # Map actual min/max → 0–127
    value = int((raw - MIN_ADC[index]) * 127 / (MAX_ADC[index] - MIN_ADC[index]))
    value = max(0, min(127, value))
    return value

def set_led_brightness(brightness):
    """Set LED brightness - GP9 on/off, onboard LED smooth PWM"""
    # GP9: Simple on/off (turns on above 30% brightness)
    if has_gp9:
        led_strip.value = brightness > 0.3
    
    # Onboard LED: Smooth PWM dimming
    if has_onboard:
        led_onboard.duty_cycle = int(brightness * 65535)

def trigger_blink():
    """Trigger a slow fade blink"""
    global blink_timer, led_brightness
    blink_timer = time.monotonic()
    led_brightness = 0.0  # Start fade from current position

def update_led():
    """Update LED animation - breathing effect or slow fade blink"""
    global led_brightness, led_direction, blink_timer
    
    current_time = time.monotonic()
    
    # Check if we're in a blink
    if current_time - blink_timer < blink_duration:
        # Slow fade in and out
        progress = (current_time - blink_timer) / blink_duration
        
        if progress < 0.5:
            # Fade in (first half)
            led_brightness = progress * 2  # 0 to 1
        else:
            # Fade out (second half)
            led_brightness = 2 - (progress * 2)  # 1 to 0
        
        set_led_brightness(led_brightness)
    else:
        # Smooth breathing effect using sine wave
        led_brightness += led_direction * breathing_speed
        
        if led_brightness >= 1.0:
            led_brightness = 1.0
            led_direction = -1
        elif led_brightness <= 0.2:
            led_brightness = 0.2
            led_direction = 1
        
        smooth_brightness = (math.sin((led_brightness - 0.5) * math.pi) + 1) / 2
        set_led_brightness(smooth_brightness * 0.3 + 0.1)

# Startup animation
for i in range(20):
    set_led_brightness(i / 20)
    time.sleep(0.02)
for i in range(20, 0, -1):
    set_led_brightness(i / 20)
    time.sleep(0.02)

print("MIDI Controller Ready!")
print(f"Buttons: 9 (GP0-GP8)")
print(f"Pots: 3 (GP26-GP28)")
led_status = []
if has_gp9:
    led_status.append("GP9")
if has_onboard:
    led_status.append("Onboard")
print(f"LEDs: {', '.join(led_status) if led_status else 'None'}")

while True:
    update_led()
    
    # Check buttons
    for i, btn in enumerate(buttons):
        pressed = btn.value
        
        if pressed != button_states[i]:
            button_states[i] = pressed

            if pressed:
                trigger_blink()
                midi.send(NoteOn(note_numbers[i], 127))

                if DEBUG:
                    print(f"[DEBUG] Button {i+1} PRESSED → Note {note_numbers[i]}")
            else:
                midi.send(NoteOff(note_numbers[i], 0))
    
    # Check potentiometers
    for i, pot in enumerate(pots):
        new_value = read_pot(pot, i)

        if abs(new_value - pot_values[i]) >= 1:
            pot_values[i] = new_value
            midi.send(ControlChange(cc_numbers[i], new_value))
            if DEBUG:
                print(f"Pot {i+1} → CC{cc_numbers[i]} = {new_value}")
    
    time.sleep(0.01)