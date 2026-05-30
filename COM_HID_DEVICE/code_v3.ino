#include <Keyboard.h>
#include <Mouse.h>

static const unsigned long SERIAL_BAUD = 9600;
static const char* FW_VERSION = "HID_BRIDGE 2.1";

String g_lineBuffer;

String trimCopy(String s) {
  s.trim();
  return s;
}

String upperCopy(String s) {
  s.trim();
  s.toUpperCase();
  return s;
}

bool splitFirstToken(const String& line, String& head, String& tail) {
  String s = trimCopy(line);
  if (s.length() == 0) {
    head = "";
    tail = "";
    return false;
  }

  int sp = s.indexOf(' ');
  if (sp < 0) {
    head = s;
    tail = "";
    return true;
  }

  head = s.substring(0, sp);
  tail = s.substring(sp + 1);
  tail.trim();
  return true;
}

bool readCommandLine(String& outLine) {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\r') {
      continue;
    }

    if (c == '\n') {
      outLine = g_lineBuffer;
      g_lineBuffer = "";
      outLine.trim();
      return outLine.length() > 0;
    }

    g_lineBuffer += c;

    if (g_lineBuffer.length() > 256) {
      g_lineBuffer = "";
      Serial.println("ERROR BUFFER_OVERFLOW");
      return false;
    }
  }

  return false;
}

void replyOK() {
  Serial.println("OK");
}

void replyError(const char* msg) {
  Serial.print("ERROR ");
  Serial.println(msg);
}

bool parseIntStrict(const String& s, int& out) {
  String t = trimCopy(s);
  if (t.length() == 0) {
    return false;
  }

  int start = 0;
  if (t[0] == '+' || t[0] == '-') {
    if (t.length() == 1) return false;
    start = 1;
  }

  for (int i = start; i < t.length(); ++i) {
    if (!isDigit((unsigned char)t[i])) {
      return false;
    }
  }

  out = t.toInt();
  return true;
}

bool parseTwoInts(const String& args, int& a, int& b) {
  String left, right;
  int sp = args.indexOf(' ');
  if (sp < 0) return false;

  left = args.substring(0, sp);
  right = args.substring(sp + 1);
  left.trim();
  right.trim();

  return parseIntStrict(left, a) && parseIntStrict(right, b);
}

bool parseOneInt(const String& args, int& value) {
  return parseIntStrict(args, value);
}

bool isSinglePrintableKeyName(const String& keyName) {
  return keyName.length() == 1;
}

bool resolveSpecialKey(const String& rawName, uint8_t& outKey) {
  String name = upperCopy(rawName);

  if (name == "ENTER" || name == "RETURN")         { outKey = KEY_RETURN; return true; }
  if (name == "TAB")                               { outKey = KEY_TAB; return true; }
  if (name == "ESC" || name == "ESCAPE")           { outKey = KEY_ESC; return true; }
  if (name == "BACKSPACE" || name == "BKSP")       { outKey = KEY_BACKSPACE; return true; }
  if (name == "DELETE" || name == "DEL")           { outKey = KEY_DELETE; return true; }
  if (name == "INSERT" || name == "INS")           { outKey = KEY_INSERT; return true; }
  if (name == "HOME")                              { outKey = KEY_HOME; return true; }
  if (name == "END")                               { outKey = KEY_END; return true; }
  if (name == "PAGEUP" || name == "PGUP")          { outKey = KEY_PAGE_UP; return true; }
  if (name == "PAGEDOWN" || name == "PGDN")        { outKey = KEY_PAGE_DOWN; return true; }

  if (name == "UP")                                { outKey = KEY_UP_ARROW; return true; }
  if (name == "DOWN")                              { outKey = KEY_DOWN_ARROW; return true; }
  if (name == "LEFT")                              { outKey = KEY_LEFT_ARROW; return true; }
  if (name == "RIGHT")                             { outKey = KEY_RIGHT_ARROW; return true; }

  if (name == "CTRL" || name == "CONTROL")         { outKey = KEY_LEFT_CTRL; return true; }
  if (name == "SHIFT")                             { outKey = KEY_LEFT_SHIFT; return true; }
  if (name == "ALT")                               { outKey = KEY_LEFT_ALT; return true; }
  if (name == "WIN" || name == "GUI" || name == "WINDOWS") {
    outKey = KEY_LEFT_GUI;
    return true;
  }

  if (name == "SPACE") {
    outKey = ' ';
    return true;
  }

  if (name == "F1")  { outKey = KEY_F1;  return true; }
  if (name == "F2")  { outKey = KEY_F2;  return true; }
  if (name == "F3")  { outKey = KEY_F3;  return true; }
  if (name == "F4")  { outKey = KEY_F4;  return true; }
  if (name == "F5")  { outKey = KEY_F5;  return true; }
  if (name == "F6")  { outKey = KEY_F6;  return true; }
  if (name == "F7")  { outKey = KEY_F7;  return true; }
  if (name == "F8")  { outKey = KEY_F8;  return true; }
  if (name == "F9")  { outKey = KEY_F9;  return true; }
  if (name == "F10") { outKey = KEY_F10; return true; }
  if (name == "F11") { outKey = KEY_F11; return true; }
  if (name == "F12") { outKey = KEY_F12; return true; }

  return false;
}

bool pressKeyByName(const String& rawName) {
  String keyName = trimCopy(rawName);
  if (keyName.length() == 0) return false;

  if (isSinglePrintableKeyName(keyName)) {
    Keyboard.press(keyName[0]);
    return true;
  }

  uint8_t key = 0;
  if (resolveSpecialKey(keyName, key)) {
    Keyboard.press(key);
    return true;
  }

  return false;
}

bool releaseKeyByName(const String& rawName) {
  String keyName = trimCopy(rawName);
  if (keyName.length() == 0) return false;

  if (isSinglePrintableKeyName(keyName)) {
    Keyboard.release(keyName[0]);
    return true;
  }

  uint8_t key = 0;
  if (resolveSpecialKey(keyName, key)) {
    Keyboard.release(key);
    return true;
  }

  return false;
}

bool clickKeyByName(const String& rawName) {
  if (!pressKeyByName(rawName)) return false;
  delay(25);
  if (!releaseKeyByName(rawName)) {
    Keyboard.releaseAll();
    return false;
  }
  return true;
}

bool resolveMouseButton(const String& rawName, uint8_t& outButton) {
  String name = upperCopy(rawName);

  if (name == "LEFT")   { outButton = MOUSE_LEFT; return true; }
  if (name == "RIGHT")  { outButton = MOUSE_RIGHT; return true; }
  if (name == "MIDDLE") { outButton = MOUSE_MIDDLE; return true; }

  return false;
}

void releaseAllInputs() {
  Keyboard.releaseAll();
  Mouse.release(MOUSE_LEFT);
  Mouse.release(MOUSE_RIGHT);
  Mouse.release(MOUSE_MIDDLE);
}

bool handleKeyDown(const String& args) {
  if (!pressKeyByName(args)) {
    replyError("BAD_KEY");
    return true;
  }
  replyOK();
  return true;
}

bool handleKeyUp(const String& args) {
  if (!releaseKeyByName(args)) {
    replyError("BAD_KEY");
    return true;
  }
  replyOK();
  return true;
}

bool handleKeyPress(const String& args) {
  if (!clickKeyByName(args)) {
    replyError("BAD_KEY");
    return true;
  }
  replyOK();
  return true;
}

bool handleMouseMove(const String& args) {
  int dx = 0;
  int dy = 0;
  if (!parseTwoInts(args, dx, dy)) {
    replyError("BAD_ARGS");
    return true;
  }

  dx = constrain(dx, -127, 127);
  dy = constrain(dy, -127, 127);
  Mouse.move(dx, dy, 0);
  replyOK();
  return true;
}

bool handleMouseWheel(const String& args) {
  int wheel = 0;
  if (!parseOneInt(args, wheel)) {
    replyError("BAD_ARGS");
    return true;
  }

  wheel = constrain(wheel, -50, 50);

  if (wheel > 0) {
    for (int i = 0; i < wheel; ++i) {
      Mouse.move(0, 0, 1);
      delay(15);
    }
  } else if (wheel < 0) {
    for (int i = 0; i < -wheel; ++i) {
      Mouse.move(0, 0, -1);
      delay(15);
    }
  }

  replyOK();
  return true;
}

bool handleMousePress(const String& args) {
  uint8_t button = 0;
  if (!resolveMouseButton(args, button)) {
    replyError("BAD_BUTTON");
    return true;
  }

  Mouse.press(button);
  replyOK();
  return true;
}

bool handleMouseRelease(const String& args) {
  uint8_t button = 0;
  if (!resolveMouseButton(args, button)) {
    replyError("BAD_BUTTON");
    return true;
  }

  Mouse.release(button);
  replyOK();
  return true;
}

bool handleMouseClick(const String& args) {
  uint8_t button = 0;
  if (!resolveMouseButton(args, button)) {
    replyError("BAD_BUTTON");
    return true;
  }

  Mouse.press(button);
  delay(25);
  Mouse.release(button);
  replyOK();
  return true;
}

bool handleTypeText(const String& args) {
  Keyboard.print(args);
  replyOK();
  return true;
}

bool handleHotkey(const String& args) {
  String modName, keyName;
  if (!splitFirstToken(args, modName, keyName) || keyName.length() == 0) {
    replyError("BAD_ARGS");
    return true;
  }

  if (!pressKeyByName(modName)) {
    replyError("BAD_KEY");
    return true;
  }

  delay(20);

  if (!clickKeyByName(keyName)) {
    Keyboard.releaseAll();
    replyError("BAD_KEY");
    return true;
  }

  delay(20);
  releaseKeyByName(modName);
  replyOK();
  return true;
}

void handleCommand(const String& rawLine) {
  String cmd, args;
  if (!splitFirstToken(rawLine, cmd, args)) {
    return;
  }

  cmd = upperCopy(cmd);

  if (cmd == "PING") {
    Serial.println("PONG");
    return;
  }

  if (cmd == "VERSION") {
    Serial.println(FW_VERSION);
    return;
  }

  if (cmd == "RELEASE_ALL") {
    releaseAllInputs();
    replyOK();
    return;
  }

  if (cmd == "KEY_DOWN") {
    handleKeyDown(args);
    return;
  }

  if (cmd == "KEY_UP") {
    handleKeyUp(args);
    return;
  }

  if (cmd == "KEY_PRESS") {
    handleKeyPress(args);
    return;
  }

  if (cmd == "MOUSE_MOVE") {
    handleMouseMove(args);
    return;
  }

  if (cmd == "MOUSE_SCROLL") {
    handleMouseWheel(args);
    return;
  }

  if (cmd == "MOUSE_PRESS") {
    handleMousePress(args);
    return;
  }

  if (cmd == "MOUSE_RELEASE") {
    handleMouseRelease(args);
    return;
  }

  if (cmd == "MOUSE_CLICK") {
    handleMouseClick(args);
    return;
  }

  if (cmd == "TYPE_TEXT") {
    handleTypeText(args);
    return;
  }

  if (cmd == "HOTKEY") {
    handleHotkey(args);
    return;
  }

  replyError("UNKNOWN_COMMAND");
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  Keyboard.begin();
  Mouse.begin();
  delay(300);
}

void loop() {
  String line;
  if (readCommandLine(line)) {
    handleCommand(line);
  }
}                 