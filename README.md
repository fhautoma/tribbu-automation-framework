# Tribbu Automation Framework

Mobile test automation framework for Android and iOS built on top of Appium. The idea is simple: you record your interactions in Appium Inspector, export them as a JSONL file, and the framework generates all the boilerplate — page objects, test files, locators — so you can focus on what matters.

## How it works

You drop a `.jsonl` recording into the `recordings/` folder, run one command, and get a fully working pytest test with page objects ready to execute.

```
recordings/onboarding_test.jsonl  →  tribbu generate  →  tests/generated/
                                                           ├── pages/
                                                           │   ├── onboarding_page.py
                                                           │   ├── otp_page.py
                                                           │   └── ...
                                                           └── test_onboarding_test.py
```

---

## Requirements

- Python 3.11+
- Appium 2.x
- Android SDK / Xcode (depending on platform)
- Allure CLI (`brew install allure`)
- A real device or emulator connected and visible to `adb devices`

---

## Setup

```bash
git clone https://github.com/fhautoma/tribbu-automation-framework.git
cd tribbu-automation-framework
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

---

## JSONL recording format

Each line in the recording is one action. The framework understands these fields:

```json
{
  "ts": "2026-04-28T10:54:26.425Z",
  "action": "tap",
  "platform": "android",
  "screen": "Onboarding",
  "key": "passenger_option",
  "method": "select_going_to_be_option",
  "locator": { "strategy": "-android uiautomator", "value": "new UiSelector().text(\"Passenger\")" }
}
```

| Field | Required | Description |
|---|---|---|
| `action` | ✓ | `tap`, `send_keys`, `assert_visible`, `clear`, `long_press` |
| `screen` | ✓ | Groups actions into page objects |
| `locator` | ✓ | Appium locator strategy + value |
| `key` | — | Human-readable name for the locator (e.g. `login_button`) |
| `method` | — | Custom method name (e.g. `tap_login`) |
| `value` | — | Text to type for `send_keys` |
| `context` | — | Metadata for code generation (see below) |

### Context field

The `context` field drives special behavior during generation:

| Context value | Effect |
|---|---|
| `${var} = Enter a random name` | Generates `fake.first_name()` |
| `${var} = Enter a random last name` | Generates `fake.last_name()` |
| `${var} = Enter a random phone number` | Generates `fake.numerify("6########")` |
| `${var} = Call using GET https://...` | Generates an API call before typing the value |
| `must equal "Expected text"` | Generates `assert_text()` instead of `assert_visible()` |
| `no_hide_keyboard` | Keeps the keyboard open after `send_keys` |

---

## Generating tests

```bash
# Android
tribbu generate --android recordings/onboarding_test.jsonl --name onboarding_test

# iOS
tribbu generate --ios recordings/login_test.jsonl --name login_test

# Both platforms
tribbu generate \
  --android recordings/onboarding_android.jsonl \
  --ios recordings/onboarding_ios.jsonl \
  --name onboarding_test
```

Output goes to `tests/generated/` by default. You can change it with `--output`.

---

## Running tests

### All tests

```bash
tribbu run --platform android
```

### Specific test

```bash
tribbu run --platform android --test onboarding_test
```

This runs pytest, generates the Allure report and opens it in the browser automatically. Screenshots are saved to `reports/screenshots/` on failures.

### Direct pytest (without report)

```bash
pytest tests/generated/ --platform android --config config/capabilities/android.yaml -v
```

---

## Capabilities config

Device capabilities live in `config/capabilities/`. Create one per platform:

```yaml
# config/capabilities/android.yaml
platformName: Android
appium:automationName: UiAutomator2
appium:deviceName: "Your Device Name"
appium:udid: "your-device-udid"
appium:appPackage: "com.your.app"
appium:appActivity: "com.your.app/.MainActivity"
appium:noReset: true
appium:newCommandTimeout: 300
```

Get your device UDID with `adb devices`.

---

## Reports

After running, the Allure report opens automatically. Each test shows:

- Step-by-step execution with readable names
- Screenshot after every tap and assertion
- Screenshot on failure with exact state of the app
- Execution history across runs

The report is also published to GitHub Pages after every CI run:

```
https://fhautoma.github.io/tribbu-automation-framework/
```

---

## CI / GitHub Actions

The workflow triggers via the GitHub API or manually from the Actions tab. It runs on a self-hosted runner (your Mac) so it has access to the connected device.

### Trigger via API

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/fhautoma/tribbu-automation-framework/actions/workflows/run_tests.yml/dispatches \
  -d '{
    "ref": "main",
    "inputs": {
      "platform": "android",
      "test": "onboarding_test"
    }
  }'
```

Leave `test` empty to run everything.

### Setting up the self-hosted runner

Go to your repo → **Settings → Actions → Runners → New self-hosted runner** and follow the instructions for macOS. Once configured:

```bash
cd ~/actions-runner && ./run.sh
```

Make sure Appium is installed globally (`npm install -g appium`) and the device is connected before triggering a run.

---

## Project structure

```
tribbu/
├── recordings/          # JSONL source recordings
├── config/
│   └── capabilities/    # Device capabilities per platform
├── tests/
│   ├── conftest.py      # Driver setup, fixtures, screenshot on failure
│   └── generated/       # Auto-generated tests and page objects
├── tribbu/
│   ├── core/
│   │   └── driver/      # Appium driver factory
│   ├── generator/       # JSONL parser, code generator, CLI
│   │   └── templates/   # Jinja2 templates for page objects and tests
│   └── pages/
│       └── base_page.py # Base class with all Appium interactions
└── reports/
    ├── allure-results/  # Raw test results
    ├── allure-report/   # Generated HTML report
    └── screenshots/     # Failure screenshots
```

---

## Adding a new test

1. Record your flow in Appium Inspector and export as JSONL
2. Add `key` and `method` fields to give locators and methods readable names
3. Drop the file in `recordings/`
4. Run `tribbu generate --android recordings/your_flow.jsonl --name your_flow`
5. Review the generated files in `tests/generated/`
6. Run it with `tribbu run --platform android --test your_flow`
