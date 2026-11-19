// Valve control with a normal POSITIONAL servo, e.g. a 9g micro servo (GPIO13).
// Library (Library Manager): "ESP32Servo" by Kevin Harrington.
// Serial Monitor: 115200 baud, line ending "Newline".
//
// Teach it the two valve positions once; they are saved in flash and survive power-off.
//   g<deg>   go to an angle, e.g.  g90
//   +  / -   nudge 3 degrees (+10, -1 and so on also work)
//   sc       SAVE the current angle as CLOSED   (valve exactly closed)
//   so       SAVE the current angle as OPEN     (valve exactly open)
//   o / c    move slowly to the saved OPEN / CLOSED angle
//   d        servo limp (the handle turns freely by hand)
//   p        print the angle and the saved positions
//   x        forget the saved positions
//
// The servo is limp until the first command that moves it. If it buzzes or the valve does not
// move, it is straining: send d at once. A 9g servo is weak, which also means it cannot force
// the valve hard.

#include <ESP32Servo.h>
#include <Preferences.h>

const int PIN_SERVO = 13;
const int ANGLE_MIN = 5;
const int ANGLE_MAX = 175;
const int STEP_DELAY_MS = 30;   // larger = slower, gentler on the valve

Servo servo;
Preferences prefs;
bool attached = false;
int angle = 90;
int closedAngle = -1;           // -1 = not saved yet
int openAngle = -1;

int clampAngle(int a) { return a < ANGLE_MIN ? ANGLE_MIN : (a > ANGLE_MAX ? ANGLE_MAX : a); }

void ensureAttached() {
  if (!attached) {
    servo.setPeriodHertz(50);
    servo.attach(PIN_SERVO, 500, 2400);
    servo.write(angle);
    attached = true;
    delay(300);
  }
}

void moveTo(int target) {
  target = clampAngle(target);
  ensureAttached();
  int step = (target >= angle) ? 1 : -1;
  while (angle != target) {
    angle += step;
    servo.write(angle);
    delay(STEP_DELAY_MS);
  }
  Serial.print("angle = ");
  Serial.println(angle);
}

void printSaved() {
  Serial.print("saved CLOSED = ");
  if (closedAngle < 0) Serial.print("none"); else Serial.print(closedAngle);
  Serial.print("   saved OPEN = ");
  if (openAngle < 0) Serial.println("none"); else Serial.println(openAngle);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  prefs.begin("valvepos", false);
  closedAngle = prefs.getInt("closed", -1);
  openAngle = prefs.getInt("open", -1);
  Serial.println("Positional valve servo ready. Servo is limp. Commands: g<deg> +/-[n] sc so o c d p x");
  printSaved();
}

void loop() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd == "sc" || cmd == "so") {
    if (!attached) {
      Serial.println("servo is limp, so the angle is unknown. Nudge it with + or - first, then save (do not send d before saving)");
      return;
    }
    if (cmd == "sc") { closedAngle = angle; prefs.putInt("closed", angle); Serial.print("saved CLOSED = "); }
    else { openAngle = angle; prefs.putInt("open", angle); Serial.print("saved OPEN = "); }
    Serial.println(angle);
  } else if (cmd == "o") {
    if (openAngle < 0) Serial.println("OPEN not saved yet: find it with + / - then send so");
    else moveTo(openAngle);
  } else if (cmd == "c") {
    if (closedAngle < 0) Serial.println("CLOSED not saved yet: find it with + / - then send sc");
    else moveTo(closedAngle);
  } else if (cmd == "d") {
    servo.detach();
    attached = false;
    Serial.println("servo limp (detached)");
  } else if (cmd == "p") {
    Serial.print("angle = ");
    Serial.print(angle);
    Serial.println(attached ? "  (powered)" : "  (limp)");
    printSaved();
  } else if (cmd == "x") {
    prefs.clear();
    closedAngle = -1;
    openAngle = -1;
    Serial.println("saved positions cleared");
  } else if (cmd.charAt(0) == 'g') {
    moveTo(cmd.substring(1).toInt());
  } else if (cmd.charAt(0) == '+' || cmd.charAt(0) == '-') {
    int n = cmd.substring(1).toInt();
    if (n == 0) n = 3;
    moveTo(angle + (cmd.charAt(0) == '+' ? n : -n));
  } else {
    Serial.println("unknown command");
  }
}
