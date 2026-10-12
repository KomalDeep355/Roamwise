# Roamwise 🌿

**Check the air before you go touch grass.**

Roamwise helps you decide whether it is a good time to go outdoors by showing current air-quality conditions, the cleanest daylight window in the next 24 hours, and nearby parks.

Built with Delhi NCR in mind, where "go outside" can be bad advice around Diwali, Roamwise is designed to work for other cities too.

**Live demo:** [https://roamwise-4e26.onrender.com](https://roamwise-4e26.onrender.com)

**Write-up on DEV:** https://dev.to/komal_deep_355/in-delhi-ncr-go-touch-grass-can-be-bad-advice-so-i-built-a-tool-that-checks-the-air-first-355j


## The one design rule

The **go / go easy / stay in verdict is computed using fixed PM2.5 rules, not a language model.**

An open-weight language model explains that verdict in plain language in English, Hinglish or Hindi. If the generated explanation contradicts the verdict or makes a medical claim, Roamwise replaces it with a template explanation.

For a health-adjacent application, the language model explains the decision; it does not make the underlying safety decision.

## Features

- **Air-quality forecast:** Hour-by-hour PM2.5 information for the next 24 hours.
- **Best outdoor window:** Highlights the cleanest suitable daylight window.
- **Personalized guidance:** Considers the selected user profile and activity intensity.
- **Weather awareness:** Excludes unsuitable windows during heavy rain or extreme heat.
- **Nearby parks:** Finds parks using OpenStreetMap data and ranks them by distance.
- **Map and walking information:** Helps users explore nearby outdoor locations.
- **AI-powered explanations:** Uses an open-weight model to explain the verdict in plain language.
- **Multilingual explanations:** Supports English, Hinglish and Hindi.
- **Ask Roamwise:** An in-page assistant for questions about an outdoor outing.
- **Voice input:** Microphone controls for place search and the in-page assistant.
- **Practical tips:** Provides general precautions for spending time outdoors.
- **Fallback behavior:** Supports cached data when configured sources are unavailable and template explanations when the language model cannot be used.

## How it works

```text
Open-Meteo (air quality + weather) ─┐
                                    │
OpenStreetMap / Overpass (parks) ───┤
                                    ▼
                       Data retrieval and cache
                                    ▼
              Exposure engine: PM2.5 thresholds,
                 daylight, rain and heat rules
                                    ▼
                 Verdict + suitable time windows
                       + ranked nearby parks
                                    ▼
                  Open-weight LLM explanation
                     (template fallback)
                                    ▼
                          FastAPI backend
                                    ▼
                    Frontend, chart, parks and map
```

The exposure engine determines the verdict using predefined rules. The language model provides an explanation of the result rather than replacing the deterministic decision logic.

## Project structure

```text
Roamwise/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application and API endpoints
│   ├── agent.py                # Ask Roamwise assistant logic
│   ├── cache.py                # Caching and stale-data fallback
│   ├── config.py               # Environment-based configuration
│   ├── explain.py              # LLM explanations and template fallback
│   ├── exposure.py             # PM2.5 rules, verdicts and time windows
│   ├── main_helpers.py         # Shared application helpers
│   ├── partner_integrations.py # External service integrations
│   └── sources.py              # Air quality, weather and location data
├── static/
│   ├── index.html              # Main web interface
│   ├── style.css               # Frontend styling
│   └── app.js                  # Frontend interactions and API calls
├── tests/
│   ├── __init__.py
│   ├── test_api.py             # API endpoint tests
│   ├── test_explain.py         # Explanation and fallback tests
│   └── test_exposure.py        # Exposure logic and ranking tests
├── .env.example                # Example environment variables
├── .gitignore                  # Files excluded from Git
├── render.yaml                 # Render deployment configuration
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

### Main components

| Component | Responsibility |
|---|---|
| `app/main.py` | Exposes the FastAPI application and API endpoints. |
| `app/exposure.py` | Evaluates PM2.5 thresholds, exposure verdicts, weather constraints and outdoor windows. |
| `app/sources.py` | Retrieves air-quality, weather, geocoding and park data. |
| `app/cache.py` | Handles data caching and fallback behavior. |
| `app/explain.py` | Produces explanations and applies safeguards against contradictory or medically unsupported output. |
| `app/agent.py` | Implements the Ask Roamwise assistant. |
| `app/config.py` | Reads environment-based settings for the LLM, API and cache. |
| `app/partner_integrations.py` | Handles external service integrations. |
| `static/` | Contains the frontend HTML, CSS and JavaScript. |
| `tests/` | Contains API, explanation and exposure tests. |
| `render.yaml` | Defines the Render web service configuration. |

## Forecasting

Roamwise includes a PM2.5 forecasting step built with `pandas` and `scikit-learn`. Its evaluation uses a time-based split and compares the model against baseline forecasts.

<!-- Replace the placeholders below with results from your actual backtest. -->

| Model | MAE (µg/m³), next 24 hours |
|---|---:|
| Persistence — repeat the last value | *Add measured result* |
| Open-Meteo forecast | *Add measured result* |
| Roamwise forecasting model | *Add measured result* |

**Evaluation summary:** Add an honest description of the results, including whether the Roamwise model outperformed either baseline.

No performance claim should be made until the evaluation has been run and the results recorded.

## Voice input and Ask Roamwise

Roamwise includes microphone controls for place search and the in-page assistant.

Speech is transcribed into text and passed into the application's question-and-answer flow. The underlying outdoor verdict remains determined by fixed PM2.5 rules.

<!-- Document the exact speech-to-text provider, voice-output provider and assistant model after verifying the implementation. -->

## Run locally

### Prerequisites

- Python 3.12 or another Python version compatible with the project's dependencies.
- Git.
- [Ollama](https://ollama.com/) if you want to run the language model locally.
- An API key from a compatible hosted model provider if you want to use a hosted model.

### 1. Clone the repository

Open Windows PowerShell:

```powershell
git clone https://github.com/KomalDeep355/Roamwise.git
cd Roamwise
```

### 2. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell prevents activation, review your local execution policy or activate the environment using another supported method.

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install pytest if it is not already included or available in the environment:

```powershell
python -m pip install pytest
```

### 4. Configure environment variables

Create a local `.env` file from the example:

```powershell
copy .env.example .env
```

Edit `.env` with your chosen configuration. Never put real credentials in `.env.example` or commit your `.env` file.

### 5. Start the application

```powershell
uvicorn app.main:app --reload
```

Open the application at:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

If FastAPI's interactive API documentation is enabled, it is usually available at:

[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Configure the language model

Roamwise supports the following provider modes through its environment-based configuration.

### Option 1: Ollama — local model

The default settings in `app/config.py` are:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
LLM_MODEL=gemma3:4b
```

Install Ollama and pull the default model:

```powershell
ollama pull gemma3:4b
```

Make sure Ollama is running locally before using model-powered explanations.

### Option 2: Hosted OpenAI-compatible API

To use a hosted model provider, configure the following in `.env`:

```dotenv
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=your-provider-model-id
LLM_API_KEY=your-api-key
```

The URL above is an example. Replace the base URL, model ID and API key with the values provided by your chosen provider.

The model must be supported by that provider's API.

### Option 3: No language model

To disable LLM calls and use template explanations:

```dotenv
LLM_PROVIDER=none
```

This mode is useful for testing the deterministic decision logic independently of a language model.

## Environment variables

The following table reflects the settings read by `app/config.py`.

| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | Selects `ollama`, `openai_compat` or `none` | `ollama` |
| `OLLAMA_URL` | Base URL for the local Ollama server | `http://localhost:11434` |
| `LLM_MODEL` | Local model tag or hosted model ID | `gemma3:4b` |
| `LLM_BASE_URL` | Base URL for a hosted OpenAI-compatible API | Empty |
| `LLM_API_KEY` | API key for the hosted model provider | Empty |
| `LLM_TIMEOUT` | LLM request timeout, in seconds | `60` |
| `DB_PATH` | SQLite cache database path | `cache.db` |

The actual default values are defined in `app/config.py`. Values supplied through environment variables override those defaults.

**Security reminder:** Keep `.env` in `.gitignore`. Never commit API keys, tokens or other credentials to GitHub.

## Run tests

Run the test suite from the project root:

```powershell
python -m pytest -q
```

The test suite is organized into:

- `tests/test_api.py` — API behavior and request validation.
- `tests/test_explain.py` — explanation generation and fallback safeguards.
- `tests/test_exposure.py` — PM2.5 rules, time windows and park ranking.

If a test fails, review the error output before committing changes. A successful test run is not a substitute for testing the deployed application against real data sources.

## Deploy on Render

Roamwise includes a `render.yaml` Blueprint configuration for deployment as a Python web service.

### Deployment configuration

| Setting | Value |
|---|---|
| Service name | `saaf-ghaas` |
| Runtime | Python |
| Plan | Free |
| Python version | `3.12.3` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |

### Deploy using the Blueprint

1. Push your latest changes to GitHub.
2. Sign in to [Render](https://dashboard.render.com/).
3. Choose **New + → Blueprint**.
4. Connect the repository `KomalDeep355/Roamwise`.
5. Select the `main` branch and allow Render to read `render.yaml`.
6. Supply the required hosted-model environment variables.
7. Start the deployment and monitor the build and runtime logs.
8. Once deployed, check the health endpoint and open the application URL.

Alternatively, create a Web Service manually and enter the build and start commands from the table above.

### Configure the hosted model on Render

The supplied `render.yaml` sets:

```yaml
LLM_PROVIDER: openai_compat
```

It also declares the following variables with `sync: false`, so you must supply their values through Render:

| Variable | Value |
|---|---|
| `LLM_BASE_URL` | Your provider's OpenAI-compatible API base URL |
| `LLM_MODEL` | The model ID supported by your provider |
| `LLM_API_KEY` | Your provider's API key |

The hosted deployment uses the configured API provider rather than the local Ollama default. Do not enter secrets directly into a public repository.

**Live demo:** [https://roamwise-4e26.onrender.com](https://roamwise-4e26.onrender.com)

Free hosting may spin down after periods of inactivity, which can make the first request slower. The Blueprint service name and the public URL can differ.

## Why open?

- **Swappable models:** Run Gemma locally or configure a compatible hosted open-weight model.
- **Local execution option:** Local runs can use Ollama on the user's own machine.
- **Transparent safety logic:** Deterministic rules control the outdoor verdict instead of relying on LLM judgment.
- **Accessible data sources:** The project's primary air-quality, weather and geocoding data sources can be used without an API key for ordinary requests.
- **Testable components:** The exposure rules and explanation safeguards can be tested independently.

<!-- Add an honest comparison with a closed model only if you have conducted and documented that evaluation. -->

## Data sources and attribution

- **Air quality, weather and geocoding:** [Open-Meteo](https://open-meteo.com/)
- **Parks and map data:** [OpenStreetMap contributors](https://www.openstreetmap.org/), using the Overpass API.

Please follow the relevant provider terms and attribution requirements when using or redistributing data.

## Limitations

- **Regional air-quality data:** The air-quality value comes from a regional model grid. It describes the surrounding area, not the exact air at an individual park.
- **Distance-based park ranking:** Parks are ranked by distance. The nearest park is not necessarily the cleanest.
- **Hourly versus daily values:** India's CPCB PM2.5 bands are defined for 24-hour averages, while this application applies thresholds to hourly values. This is a practical heuristic, not a medical limit.
- **Weather uncertainty:** Forecasts and weather data may change, and unavailable sources can affect the information shown.
- **Model-generated explanations:** LLM output can be imperfect, which is why the app applies safeguards and template fallbacks.
- **Not medical advice:** Roamwise provides general outdoor guidance. People with heart or lung conditions should consult a healthcare professional about appropriate activity levels.

Thresholds can be inspected and adjusted in `app/exposure.py`.

## Contributing

Contributions, bug reports, tests and documentation improvements are welcome.

1. Fork the repository.
2. Create a branch for your change.
3. Make your changes and run the relevant tests.
4. Submit a pull request describing the change and its purpose.

Please avoid committing secrets, unmeasured performance claims or unsupported health claims.
