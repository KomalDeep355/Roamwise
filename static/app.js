
"use strict";

const $ = (sel) => document.querySelector(sel);
const SVG_NS = "http://www.w3.org/2000/svg";

const PRESETS = [
  { name: "Delhi", lat: 28.6139, lon: 77.209 },
  { name: "Gurugram", lat: 28.4595, lon: 77.0266 },
  { name: "Noida", lat: 28.5355, lon: 77.391 },
  { name: "Ghaziabad", lat: 28.6692, lon: 77.4538 },
  { name: "Faridabad", lat: 28.4089, lon: 77.3178 },
  { name: "Panipat", lat: 29.3909, lon: 76.9635 },
];

const VERDICT_LABEL = {
  go: "Good to go",
  caution: "Go easy",
  avoid: "Better to stay in",
  unknown: "No reading for this hour",
};

const WHO = {
  general: "most adults",
  sensitive: "children, older adults and people with heart or lung conditions",
};

const WHAT = {
  light: "a walk or easy activity",
  vigorous: "a run or hard exercise",
};

let place = null;
let requestId = 0;
let explainId = 0;
let map = null;
let mapLayer = null;
let lastPlan = null;

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") {
      node.textContent = value;
    } else if (key === "class") {
      node.className = value;
    } else {
      node.setAttribute(key, value);
    }
  }

  node.append(...kids);
  return node;
}

function svg(tag, attrs = {}, text) {
  const node = document.createElementNS(SVG_NS, tag);

  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }

  if (text !== undefined) {
    node.textContent = text;
  }

  return node;
}

function setStatus(message, isError = false) {
  const status = $("#status");

  status.textContent = message;
  status.classList.toggle("error", isError);
}

async function getJSON(url) {
  const response = await fetch(url);

  let body = null;

  try {
    body = await response.json();
  } catch {
  }

  if (!response.ok) {
    throw new Error(
      (body && body.detail) || `Request failed (${response.status})`
    );
  }

  return body;
}

function controls() {
  return {
    profile: $("#profile").value,
    intensity: $("#intensity").value,
    daylight_only: $("#daylight").checked,
  };
}

function query(extra = {}) {
  return new URLSearchParams({
    lat: place.lat,
    lon: place.lon,
    name: place.name,
    ...controls(),
    ...extra,
  });
}

function fmtHour(iso, todayIso) {
  const hour = parseInt(iso.slice(11, 13), 10);
  const minute = iso.slice(14, 16);

  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  const suffix = hour < 12 ? "am" : "pm";

  const clock = minute === "00"
    ? `${hour12} ${suffix}`
    : `${hour12}:${minute} ${suffix}`;

  return iso.slice(0, 10) === todayIso.slice(0, 10)
    ? clock
    : `${clock} tomorrow`;
}

function describeSettings(plan) {
  return `${WHAT[plan.intensity]} for ${WHO[plan.profile]}`;
}

function renderHero(plan) {
  const current = plan.current;

  $("#hero").dataset.verdict = current.verdict;
  $("#place").textContent = plan.location.name || "Selected location";

  $("#verdict").textContent =
    VERDICT_LABEL[current.verdict] || VERDICT_LABEL.unknown;

  const pm = current.pm25 == null
    ? "unavailable"
    : `${Math.round(current.pm25)} µg/m³ (${current.band.toLowerCase()})`;

  $("#reading").textContent =
    `PM2.5 right now: ${pm}. Showing advice for ${describeSettings(plan)}.`;

  const bestWindow = plan.best_window;
  const windowText = $("#window");

  if (bestWindow) {
    const label = bestWindow.level === "go"
      ? "Cleanest window"
      : "Least bad window";

    windowText.textContent =
      `${label}: ${fmtHour(bestWindow.start, plan.now_local)} to ` +
      `${fmtHour(bestWindow.end, plan.now_local)}, average PM2.5 ` +
      `${Math.round(bestWindow.mean_pm25)} µg/m³.`;
  } else {
    windowText.textContent =
      "No window in the next 24 hours looks acceptable for these settings. " +
      "Consider an indoor alternative.";
  }
}

function renderChart(plan) {
  const hours = plan.hours;

  const width = 720;
  const height = 240;
  const left = 34;
  const right = 8;
  const top = 12;
  const bottom = 30;

  const count = hours.length;
  const barSlot = (width - left - right) / count;

  const pmValues = hours.map((hour) => hour.pm25 ?? 0);
  const maxPm = Math.max(...pmValues);

  const yMax = Math.min(
    400,
    Math.max(
      plan.thresholds.caution_max * 1.8,
      Math.ceil(maxPm / 10) * 10
    )
  );

  const chartY = (value) =>
    top +
    (height - top - bottom) *
    (1 - Math.min(value, yMax) / yMax);

  const root = svg("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": `Hourly PM2.5 forecast for the next ${count} hours`,
  });

  const bestWindow = plan.best_window;

  if (bestWindow) {
    const startIndex = hours.findIndex(
      (hour) => hour.time === bestWindow.start
    );

    if (startIndex >= 0) {
      root.append(
        svg("rect", {
          class: "best",
          x: left + startIndex * barSlot,
          y: top,
          width: barSlot * bestWindow.hours,
          height: height - top - bottom,
        })
      );
    }
  }

  for (const value of [
    plan.thresholds.go_max,
    plan.thresholds.caution_max,
  ]) {
    const lineY = chartY(value);

    root.append(
      svg("line", {
        class: "guide",
        x1: left,
        x2: width - right,
        y1: lineY,
        y2: lineY,
      })
    );

    root.append(
      svg(
        "text",
        {
          x: left - 4,
          y: lineY + 4,
          "text-anchor": "end",
        },
        String(value)
      )
    );
  }

  hours.forEach((hour, index) => {
    const value = hour.pm25 ?? 0;
    const barTop = chartY(value);

    const bar = svg("rect", {
      class: `bar ${hour.verdict}${hour.daylight ? "" : " night"}`,
      x: left + index * barSlot + barSlot * 0.11,
      y: barTop,
      width: barSlot * 0.78,
      height: Math.max(1, height - bottom - barTop),
      rx: 3,
    });

    const readableValue = hour.pm25 == null
      ? "unavailable"
      : `${Math.round(hour.pm25)} µg/m³`;

    bar.append(
      svg(
        "title",
        {},
        `${fmtHour(hour.time, plan.now_local)}: PM2.5 ${readableValue}`
      )
    );

    root.append(bar);

    if (index % 3 === 0) {
      root.append(
        svg(
          "text",
          {
            x: left + index * barSlot + barSlot / 2,
            y: height - 10,
            "text-anchor": "middle",
          },
          fmtHour(hour.time, plan.now_local).replace(" tomorrow", "")
        )
      );
    }
  });

  root.append(
    svg("line", {
      x1: left,
      x2: width - right,
      y1: height - bottom,
      y2: height - bottom,
      stroke: "currentColor",
      opacity: 0.25,
    })
  );

  $("#chart").replaceChildren(root);
}

function renderParks(plan) {
  const list = $("#parks");
  list.replaceChildren();

  if (!plan.parks.length) {
    list.append(
      el("li", {
        text: "No named parks found within 3 km. Try another nearby location.",
      })
    );
    return;
  }

  for (const park of plan.parks) {
    const link = el("a", {
      href: park.osm_url,
      target: "_blank",
      rel: "noopener noreferrer",
      text: park.name,
    });

    const distance = park.distance_m >= 1000
      ? `${(park.distance_m / 1000).toFixed(1)} km`
      : `${park.distance_m} m`;

    const meta = el("span", {
      class: "meta",
      text: `${park.walk_min} min on foot · ${distance}`,
    });

    list.append(el("li", {}, link, meta));
  }
}

function renderWarnings(plan) {
  const list = $("#warnings");

  list.replaceChildren(
    ...plan.warnings.map((warning) => el("li", { text: warning }))
  );
}

function renderMap(plan) {
  if (typeof L === "undefined") {
    return;
  }

  if (!map) {
    map = L.map("map");

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors",
    }).addTo(map);
  }

  if (mapLayer) {
    mapLayer.remove();
  }

  mapLayer = L.layerGroup().addTo(map);

  const points = [[plan.location.lat, plan.location.lon]];

  L.circleMarker(points[0], {
    radius: 8,
    weight: 3,
    color: "#315c43",
    fillColor: "#89a875",
    fillOpacity: 1,
  })
    .bindPopup("Selected location")
    .addTo(mapLayer);

  for (const park of plan.parks) {
    const popup = el(
      "div",
      {},
      el("strong", { text: park.name }),
      el("br"),
      `${park.walk_min} min on foot`
    );

    L.marker([park.lat, park.lon])
      .bindPopup(popup)
      .addTo(mapLayer);

    points.push([park.lat, park.lon]);
  }

  map.invalidateSize();
  map.fitBounds(points, {
    padding: [24, 24],
    maxZoom: 15,
  });
}

function renderTips(plan) {
  const list = $("#tips");
  if (!list) return;

  const verdict = plan.current.verdict;
  const tips = [];

  if (verdict === "avoid") {
    tips.push([
      "↗",
      "Choose indoors",
      "Consider an indoor activity instead of an outdoor workout while pollution is elevated.",
    ]);
    tips.push([
      "✳",
      "Check a well-fitting mask",
      "If you must go outside during high particle pollution, a well-fitting N95/FFP2 respirator can reduce particle exposure. Fit matters.",
    ]);
  } else if (verdict === "caution") {
    tips.push([
      "↘",
      "Take it easier",
      "Consider a shorter, less intense outing, especially if you are sensitive to air pollution.",
    ]);
    tips.push([
      "◷",
      "Check another hour",
      "Compare the hourly forecast and consider rescheduling if a lower-pollution window is available.",
    ]);
  } else if (verdict === "go") {
    tips.push([
      "♧",
      "Enjoy your green time",
      "A relaxed walk or your usual outdoor activity may be reasonable based on this forecast.",
    ]);
    tips.push([
      "◷",
      "Check before heading out",
      "Conditions can change, so check the latest forecast near your departure time.",
    ]);
  } else {
    tips.push([
      "ⓘ",
      "Don't guess",
      "Air-quality data is unavailable for this hour. Check a trusted local source before planning strenuous outdoor activity.",
    ]);
  }

  if (plan.profile === "sensitive") {
    tips.push([
      "♡",
      "Know your limits",
      "If you have a heart or lung condition, follow your clinician's advice and any local air-quality alerts.",
    ]);
  }

  if (plan.intensity === "vigorous") {
    tips.push([
      "↘",
      "Adjust your workout",
      "When particle pollution is elevated, consider reducing intensity or exercising indoors.",
    ]);
  }

  tips.push([
    "🐾",
    "Out with your dog?",
    "Pets can also be affected by poor air quality. Keep walks gentle and shorter when conditions are poor, and follow veterinary advice if your pet has symptoms.",
  ]);

  list.replaceChildren(
    ...tips.map(([icon, title, description]) => {
      const content = document.createElement("div");
      content.append(
        Object.assign(document.createElement("strong"), {
          textContent: `${title} — `,
        }),
        document.createTextNode(description)
      );

      const item = document.createElement("li");
      const badge = document.createElement("span");
      badge.className = "tip-icon";
      badge.setAttribute("aria-hidden", "true");
      badge.textContent = icon;

      item.append(badge, content);
      return item;
    })
  );
}

function render(plan) {
  lastPlan = plan;

  $("#results").hidden = false;

  renderHero(plan);
  renderChart(plan);
  renderParks(plan);
  renderWarnings(plan);
  renderTips(plan);
  renderMap(plan);
}

async function loadExplanation() {
  const id = ++explainId;

  const box = $("#explanation");
  const source = $("#explain-source");

  box.textContent = "Preparing your summary…";
  source.textContent = "";

  try {
    const data = await getJSON(
      `/api/explain?${query({ lang: $("#lang").value })}`
    );

    if (id !== explainId) {
      return;
    }

    box.textContent = data.text;

    source.textContent = data.source.startsWith("llm:")
      ? `Explanation generated by an open model (${data.source.slice(4)}) from the rule-based result.`
      : "Showing standard guidance because the language model was not available.";
  } catch {
    if (id !== explainId) {
      return;
    }

    box.textContent =
      "The summary is unavailable right now. The air-quality result above is still shown.";

    source.textContent = "";
  }
}

async function loadPlan() {
  if (!place) {
    return;
  }

  const id = ++requestId;

  setStatus("Checking the forecast for your location…");

  try {
    const requestUrl = `/api/plan?${query()}`;
    console.log("Roamwise plan request:", requestUrl);

    const plan = await getJSON(requestUrl);

    console.log("Roamwise plan response:", {
      location: plan.location,
      current: plan.current,
      firstHour: plan.hours?.[0],
    });

    if (id !== requestId) {
      return;
    }

    render(plan);
    setStatus("");

    loadExplanation();
  } catch (error) {
    if (id !== requestId) {
      return;
    }

    setStatus(error.message, true);
  }
}

function choose(result) {
  place = {
    name: result.admin1 && result.name
      ? `${result.name}, ${result.admin1}`
      : result.name,
    lat: result.lat,
    lon: result.lon,
  };

  $("#q").value = place.name;
  $("#matches").hidden = true;

  updateSelectedPreset();
  loadPlan();
}

async function searchPlace(text) {
  setStatus("Finding your place…");

  try {
    const data = await getJSON(
      `/api/geocode?q=${encodeURIComponent(text)}`
    );

    const results = data.results || [];

    if (!results.length) {
      setStatus(
        "No place found. Check the spelling or try a nearby city.",
        true
      );
      return;
    }

    setStatus("");

    if (results.length === 1) {
      choose(results[0]);
      return;
    }

    const list = $("#matches");

    list.replaceChildren(
      ...results.map((result) => {
        const label = [
          result.name,
          result.admin1,
          result.country,
        ].filter(Boolean).join(", ");

        const button = el("button", {
          type: "button",
          text: label,
        });

        button.addEventListener("click", () => choose(result));

        return el("li", {}, button);
      })
    );

    list.hidden = false;
  } catch (error) {
    setStatus(error.message, true);
  }
}

const presetButtons = new Map();

function updateSelectedPreset() {
  for (const preset of PRESETS) {
    const button = presetButtons.get(preset.name);
    if (!button) continue;

    const selected = Boolean(
      place &&
      Math.abs(place.lat - preset.lat) < 0.00001 &&
      Math.abs(place.lon - preset.lon) < 0.00001
    );

    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

for (const p of PRESETS) {
  const button = el("button", {
    type: "button",
    text: p.name,
    class: "preset-button",
    "aria-pressed": "false",
  });

  button.addEventListener("click", () => {
    place = { ...p };

    $("#q").value = p.name;
    $("#matches").hidden = true;

    updateSelectedPreset();
    loadPlan();
  });

  presetButtons.set(p.name, button);
  $("#presets").append(button);
}

$("#search").addEventListener("submit", (event) => {
  event.preventDefault();
  searchPlace($("#q").value.trim());
});

$("#locate").addEventListener("click", () => {
  if (!navigator.geolocation) {
    setStatus(
      "Your browser does not support location sharing. Search for a place instead.",
      true
    );
    return;
  }

  setStatus("Finding your location…");

  navigator.geolocation.getCurrentPosition(
    (position) => {
      place = {
        name: "Your location",
        lat: +position.coords.latitude.toFixed(4),
        lon: +position.coords.longitude.toFixed(4),
      };

      updateSelectedPreset();
      loadPlan();
    },
    () => {
      setStatus(
        "Location permission was denied. Search for a place instead.",
        true
      );
    },
    { timeout: 10000 }
  );
});

for (const selector of ["#profile", "#intensity", "#daylight"]) {
  $(selector).addEventListener("change", loadPlan);
}

$("#lang").addEventListener("change", () => {
  if (place && lastPlan) {
    loadExplanation();
  }
});

const voiceButton = $("#voice-search");
const agentForm = $("#agent-form");
const agentInput = $("#agent-input");
const agentSend = $("#agent-send");
const agentMessages = $("#agent-messages");
const agentStatus = $("#agent-status");
const chatWindow = $("#chat-window");
const chatToggle = $("#chat-toggle");
const chatClose = $("#chat-close");
const chatGreeting = $("#chat-greeting");
const chatSuggestions = $("#chat-suggestions");

const CHAT_PROMPTS = [
  {
    label: "Best time for a walk",
    prompt: "When is the best time to go for a walk?",
  },
  {
    label: "Places to visit",
    prompt: "What nearby parks or outdoor places can I visit?",
  },
  {
    label: "Outdoor precautions",
    prompt: "What precautions should I take before going outside?",
  },
];

for (const { label, prompt } of CHAT_PROMPTS) {
  chatSuggestions.append(
    el("button", {
      type: "button",
      text: label,
      "data-agent-prompt": prompt,
    })
  );
}

function setChatOpen(open) {
  chatWindow.hidden = !open;
  chatWindow.setAttribute("aria-hidden", String(!open));
  chatToggle.setAttribute("aria-expanded", String(open));
  chatToggle.setAttribute(
    "aria-label",
    open ? "Close Roamwise assistant" : "Open Roamwise assistant"
  );
  chatGreeting.hidden = open;

  if (open) {
    agentInput.focus();
  } else {
    chatToggle.focus();
  }
}

chatToggle.addEventListener("click", () => {
  setChatOpen(chatWindow.hidden);
});

chatClose.addEventListener("click", () => {
  setChatOpen(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !chatWindow.hidden) {
    setChatOpen(false);
  }
});

function addAgentMessage(message, role, meta = "") {
  const bubble = el("div", {
    class: `agent-message ${
      role === "user" ? "user-message" : "assistant-message"
    }`,
    text: message,
  });

  if (meta) {
    bubble.append(
      el("span", {
        class: "agent-message-meta",
        text: meta,
      })
    );
  }

  agentMessages.append(bubble);
  agentMessages.scrollTop = agentMessages.scrollHeight;

  return bubble;
}

function setAgentStatus(message, isError = false) {
  agentStatus.textContent = message;
  agentStatus.classList.toggle("error", isError);
}

function getAgentLanguage() {
  const language = $("#lang").value;

  if (["en", "hi", "hinglish"].includes(language)) {
    return language;
  }

  return "en";
}

async function askRoamwise(message) {
  if (!place) {
    throw new Error("Please select a location first.");
  }

  const settings = controls();

  const payload = {
    message,
    lat: Number(place.lat),
    lon: Number(place.lon),
    name: place.name,
    profile: settings.profile,
    intensity: settings.intensity,
    horizon: 24,
    daylight_only: settings.daylight_only,
    lang: getAgentLanguage(),
  };

  const response = await fetch("/api/agent", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  let data;

  try {
    data = await response.json();
  } catch {
    throw new Error("The server returned an invalid response.");
  }

  if (!response.ok) {
    const detail = typeof data.detail === "string"
      ? data.detail
      : "The assistant could not answer your question.";

    throw new Error(detail);
  }

  if (typeof data.answer !== "string" || !data.answer.trim()) {
    throw new Error("The assistant returned an empty answer.");
  }

  return data;
}

async function submitAgentQuestion(question) {
  const message = question.trim();

  if (!message || agentSend.disabled) return;

  addAgentMessage(message, "user");

  agentInput.value = "";
  agentSend.disabled = true;
  agentSend.textContent = "…";
  setAgentStatus("Checking your outdoor plan…");

  const loadingBubble = addAgentMessage(
    "Looking at your location and outdoor conditions…",
    "assistant"
  );

  try {
    const data = await askRoamwise(message);

    loadingBubble.remove();

    const toolNames = Array.isArray(data.tools_used)
      ? data.tools_used.join(", ")
      : "";

    const sourceLabel = data.source === "rules_fallback"
      ? "Rule-based fallback"
      : data.source
        ? `Source: ${data.source}`
        : "";

    const metadata = [
      data.location?.name || place.name,
      sourceLabel,
      toolNames ? `Tools: ${toolNames}` : "",
    ].filter(Boolean).join(" · ");

    const assistantBubble = addAgentMessage(
      data.answer,
      "assistant",
      metadata
    );

    const listenButton = el("button", {
      type: "button",
      class: "agent-speak-button",
      text: "🔊 Listen",
    });

    listenButton.addEventListener("click", async () => {
      listenButton.disabled = true;
      listenButton.textContent = "Generating audio…";
      setAgentStatus("Generating voice…");

      let audioUrl = "";

      try {
        const response = await fetch("/api/voice", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ text: data.answer }),
        });

        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.detail || "Voice generation failed.");
        }

        audioUrl = URL.createObjectURL(await response.blob());
        const audio = new Audio(audioUrl);

        audio.addEventListener("ended", () => {
          URL.revokeObjectURL(audioUrl);
        }, { once: true });

        audio.addEventListener("error", () => {
          URL.revokeObjectURL(audioUrl);
        }, { once: true });

        await audio.play();
        listenButton.textContent = "🔊 Listen again";
        setAgentStatus("");
      } catch (error) {
        if (audioUrl) {
          URL.revokeObjectURL(audioUrl);
        }
        listenButton.textContent = "Voice unavailable";
        setAgentStatus(
          error.message || "Voice generation failed. Please try again.",
          true
        );
      } finally {
        listenButton.disabled = false;
      }
    });

    assistantBubble.append(listenButton);
    setAgentStatus("");
  } catch (error) {
    loadingBubble.remove();

    setAgentStatus(
      error.message || "Something went wrong. Please try again.",
      true
    );
  } finally {
    agentSend.disabled = false;
    agentSend.textContent = "↗";
    agentInput.focus();
  }
}

if (agentForm) {
  agentForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitAgentQuestion(agentInput.value);
  });
}

document.querySelectorAll("[data-agent-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    const question = button.dataset.agentPrompt;
    setChatOpen(true);
    agentInput.value = question;
    submitAgentQuestion(question);
  });
});

const voiceStatus = $("#voice-status");

if (voiceButton && voiceStatus) {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    voiceButton.title = "Voice search is not supported in this browser";
    voiceStatus.textContent =
      "Voice search is not supported here. You can type your destination.";
    voiceButton.disabled = true;
  } else {
    const recognition = new SpeechRecognition();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    voiceButton.addEventListener("click", () => {
      voiceStatus.textContent = "Listening… Say your destination.";
      voiceButton.classList.add("listening");
      voiceButton.disabled = true;

      try {
        recognition.start();
      } catch {
        voiceStatus.textContent =
          "Voice search could not start. Please try again.";
        voiceButton.classList.remove("listening");
        voiceButton.disabled = false;
      }
    });

    recognition.addEventListener("result", (event) => {
      const transcript = event.results[0][0].transcript.trim();

      $("#q").value = transcript;
      voiceStatus.textContent = `Searching for “${transcript}”…`;
      searchPlace(transcript);
    });

    recognition.addEventListener("error", (event) => {
      voiceStatus.textContent =
        event.error === "not-allowed"
          ? "Microphone permission was denied. You can type your destination instead."
          : "We couldn't hear that clearly. Please try again or type your destination.";
    });

    recognition.addEventListener("end", () => {
      voiceButton.classList.remove("listening");
      voiceButton.disabled = false;
    });
  }
}

const agentMic = document.querySelector("#agent-mic");

if (agentMic) {
  const SpeechRecognition =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    agentMic.disabled = true;
    agentMic.title = "Speech recognition is not supported in this browser.";
  } else {
    const agentRecognition = new SpeechRecognition();

    agentRecognition.interimResults = false;
    agentRecognition.maxAlternatives = 1;

    agentMic.addEventListener("click", () => {
      agentRecognition.lang = {
        en: "en-IN",
        hi: "hi-IN",
        hinglish: "en-IN",
      }[getAgentLanguage()] || "en-IN";

      setAgentStatus("Listening… Speak your question.");
      agentMic.classList.add("listening");
      agentMic.disabled = true;

      try {
        agentRecognition.start();
      } catch {
        agentMic.classList.remove("listening");
        agentMic.disabled = false;
        setAgentStatus("Couldn't start the microphone. Try again.", true);
      }
    });

    agentRecognition.addEventListener("result", (event) => {
      const transcript = event.results[0][0].transcript.trim();

      if (!transcript) return;

      agentInput.value = transcript;
      setAgentStatus("");
      submitAgentQuestion(transcript);
    });

    agentRecognition.addEventListener("error", (event) => {
      const message = event.error === "not-allowed"
        ? "Microphone permission was denied."
        : "Couldn't recognize your speech. Please try again.";

      setAgentStatus(message, true);
    });

    agentRecognition.addEventListener("end", () => {
      agentMic.classList.remove("listening");
      agentMic.disabled = false;
    });
  }
}


place = { ...PRESETS[0] };
$("#q").value = place.name;
updateSelectedPreset();
loadPlan();
