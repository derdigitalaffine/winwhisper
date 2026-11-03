(function () {
  "use strict";
  const C = window.StudioCore,
    $ = (id) => document.getElementById(id),
    api = window.studio;
  let S = {
    project: false,
    segments: [],
    reports: [],
    speakers: {},
    recent: [],
    models: [],
    profiles: [],
    settings: {},
    microphones: [{ name: "Standardmikrofon", value: "" }],
    busy: false,
    recording: false,
    duration: 0,
    spans: [],
  };
  let view = "transcript",
    selectedSegment = null,
    selectedReport = null,
    selectedKind = "minutes",
    compareView = true;
  let wavePeaks = [],
    viewStart = 0,
    zoomLevel = 0,
    position = 0,
    selection = null,
    drag = null,
    sourceIndex = 0,
    playing = false;
  let audioKey = "",
    waveTicket = 0,
    waveTimer = null,
    editTimer = null,
    toastTimer = null,
    editorID = null,
    editorDirty = false,
    saveFlight = null,
    backendDown = false,
    visibleLimit = 180,
    lastListKey = "",
    lastReportsKey = "";
  let liveSegments = [],
    recordElapsed = 0,
    speakerDraft = {},
    speakerListKey = "",
    logs = [];
  const audio = $("audio"),
    canvas = $("waveform"),
    ctx = canvas.getContext("2d");

  function hydrate(root = document) {
    for (const span of root.querySelectorAll("[data-icon]"))
      span.innerHTML = C.icon(span.dataset.icon);
  }
  function toast(message, error = false) {
    $("toast").textContent = String(message);
    $("toast").classList.toggle("error", error);
    $("toast").hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(
      () => ($("toast").hidden = true),
      error ? 7500 : 4000,
    );
  }
  async function command(action, data = {}) {
    if (!api) {
      toast(
        "Die Desktop-Verbindung ist nicht verfügbar. Bitte über WhisperX Studio starten.",
        true,
      );
      return false;
    }
    if (backendDown && action !== "refresh" && action !== "init") {
      toast("Bitte zuerst über ‚Verbindung prüfen‘ den Hintergrunddienst wiederherstellen.", true);
      return false;
    }
    try {
      if (action === "record_start") return await window.NativeRecorder.start(S.settings);
      if (action === "record_stop") return await window.NativeRecorder.stop();
      return await api.command(action, data);
    } catch (e) {
      toast(e.message || String(e), true);
      return false;
    }
  }
  function closeDialogs() {
    document.querySelectorAll("dialog[open]").forEach((d) => d.close());
  }
  function showDialog(id) {
    $("overflowMenu").hidden = true;
    if (!$(id).open) $(id).showModal();
  }
  async function chooseFile(mode, data = {}) {
    if (S.busy || S.recording) {
      toast("Bitte die laufende Verarbeitung oder Aufnahme zuerst beenden.");
      return;
    }
    if ((await flushEditor()) === false) return;
    closeDialogs();
    try {
      await api.chooseFile(mode, data);
    } catch (e) {
      toast(e.message, true);
    }
  }
  function name(speaker) {
    return S.speakers[speaker] || speaker;
  }
  function speakerIDs() {
    return [
      ...new Set([
        ...S.segments.map((s) => s.speaker),
        ...Object.keys(S.speakers),
      ]),
    ].sort();
  }
  function initial(speaker) {
    let label = name(speaker);
    if (label === "UNBEKANNT") return "?";
    if (/^SPEAKER_/.test(label))
      return String(Number(label.split("_")[1]) + 1).padStart(2, "0");
    return label
      .split(/\s+/)
      .slice(0, 2)
      .map((x) => x[0])
      .join("")
      .toUpperCase();
  }
  function duration() {
    return S.recording ? recordElapsed : S.duration || 0;
  }
  function visibleDuration() {
    return Math.max(0.1, duration() / 10 ** zoomLevel);
  }
  function empty(icon, title, description, button = "") {
    return `<div class="empty-state"><span class="empty-icon">${C.icon(icon)}</span><h3>${C.escape(title)}</h3><p>${C.escape(description)}</p>${button}</div>`;
  }

  function renderState(state) {
    const previous = S;
    S = state;
    if (previous.project_path !== S.project_path) {
      selectedSegment = null;
      editorID = null;
      editorDirty = false;
      selectedReport = null;
      lastListKey = "";
      lastReportsKey = "";
      speakerListKey = "";
    }
    $("projectTitle").textContent = S.title || "Neue Aufnahme";
    $("breadcrumbTitle").textContent = S.title || "Neue Aufnahme";
    $("projectDate").textContent = S.project
      ? formatDate(S.date)
      : S.recording
        ? "Du sprichst. Studio hält deine Gedanken fest."
        : "Besprechungen, Interviews und deine Ideen.";
    $("savedIndicator").hidden = !S.project || S.busy || editorDirty;
    $("editMetadata").disabled = !S.project || S.busy || S.recording;
    $("reportCount").textContent = S.reports.length;
    $("segmentCount").textContent = S.segments.length;
    $("languageChip").textContent =
      { de: "Deutsch", en: "Englisch", auto: "Automatisch" }[
        S.settings.language
      ] || "Deutsch";
    $("speakerChip").textContent = S.settings.diarize
      ? S.settings.speaker_count === "auto"
        ? "Sprecher automatisch"
        : S.settings.speaker_count + " Sprecher"
      : "Sprecher optional";
    $("statusText").textContent = S.status || "Bereit.";
    $("statusDot").classList.toggle("busy", S.busy);
    $("statusDot").classList.toggle(
      "error",
      String(S.status).startsWith("Fehler:"),
    );
    $("progressBar").hidden = !S.busy;
    $("cancelButton").hidden = !S.busy || S.cancelable === false;
    $("connectionStatus").innerHTML =
      C.icon("server") + `<span>${C.escape(S.model_status || "Lokal")}</span>`;
    const blocked = S.busy || S.recording;
    $("transcribeButton").disabled = !S.project || blocked;
    $("transcribeButton").innerHTML =
      C.icon("sparkles") +
      "<span>" +
      (S.segments.length ? "Neu transkribieren" : "Transkribieren") +
      "</span>";
    $("recordButton").disabled = S.busy;
    $("recordButton").classList.toggle("recording", S.recording);
    $("recordButton").innerHTML =
      '<span class="record-dot"></span><span>' +
      (S.recording ? "Aufnahme beenden" : "Aufnehmen") +
      "</span>";
    document
      .querySelectorAll('.header-actions [data-action="open"]')
      .forEach((e) => (e.disabled = blocked));
    $("audioFileName").textContent = S.recording
      ? "Deine Aufnahme läuft."
      : S.file || "Deine Aufnahme, im Überblick.";
    $("audioFileInfo").textContent = S.recording
      ? S.settings.live
        ? "Mit vorläufiger Live-Textvorschau"
        : "Die Waveform wächst mit deinem Gespräch."
      : S.project
        ? S.preliminary
          ? "Vorläufiger Live-Text · noch nicht abschließend transkribiert"
          : `${C.stamp(S.duration)} · Original bleibt unverändert`
        : "Eine Datei öffnen oder mit dem Mikrofon aufnehmen.";
    $("originalBadge").hidden = !S.project;
    $("recordingBadge").hidden = !S.recording;
    $("audioDuration").innerHTML =
      C.icon("clock") +
      "<span>" +
      (S.project
        ? C.stamp(S.duration) + " Aufnahme"
        : S.recording
          ? "Aufnahme läuft"
          : "Bereit für deine Aufnahme") +
      "</span>";
    $("playButton").disabled = !S.project || S.recording;
    $("backButton").disabled = !S.project || S.recording;
    $("zoom").disabled = !S.project || S.recording;
    $("undoButton").disabled = !S.can_undo || blocked;
    $("deleteSelection").disabled = !selection || blocked;
    $("trimSelection").disabled = !selection || blocked;
    if (
      $("recordDialog").open &&
      JSON.stringify(previous.microphones) !== JSON.stringify(S.microphones)
    )
      fillMicrophones();
    if (S.project) {
      const key = S.audio_url + "|" + JSON.stringify(S.spans);
      if (key !== audioKey) {
        selectedSegment = null;
        editorID = null;
        editorDirty = false;
        waveTicket++;
        lastListKey = "";
        speakerListKey = "";
        pause();
        audioKey = key;
        position = 0;
        selection = null;
        viewStart = 0;
        zoomLevel = 0;
        $("zoom").value = "0";
        if (audio.src !== S.audio_url) audio.src = S.audio_url;
        sourceIndex = 0;
        updateSelection();
        requestPeaks();
      }
    } else if (!S.recording) {
      waveTicket++;
      clearTimeout(waveTimer);
      pause();
      wavePeaks = [];
      drawWave();
    }
    if (S.recording && !previous.recording) {
      waveTicket++;
      clearTimeout(waveTimer);
      pause();
      audioKey = "";
      wavePeaks = [];
      selection = null;
      position = 0;
      recordElapsed = 0;
      viewStart = 0;
      zoomLevel = 0;
      liveSegments = [];
      selectedSegment = null;
      lastListKey = "";
      renderInspector();
    }
    if (!S.recording && previous.recording) {
      liveSegments = [];
      lastListKey = "";
    }
    if (selectedSegment && !S.segments.some((s) => s.id === selectedSegment))
      selectedSegment = null;
    if (selectedReport !== null && !S.reports[selectedReport])
      selectedReport = null;
    renderRecent();
    renderTranscript();
    renderInspector();
    renderReports();
    updateTransport();
    hydrate();
  }

  function formatDate(value) {
    if (!value) return "Sitzung";
    const date = new Date(value + "T12:00:00");
    return Number.isNaN(date.valueOf())
      ? value
      : date.toLocaleDateString("de-DE", {
          day: "numeric",
          month: "long",
          year: "numeric",
        });
  }
  function renderRecent() {
    let key = JSON.stringify(S.recent.map((p) => [p.path, p.title, p.date]));
    if ($("recentProjects").dataset.key === key) return;
    $("recentProjects").dataset.key = key;
    $("recentProjects").innerHTML = S.recent.length
      ? S.recent
          .slice(0, 6)
          .map(
            (p) =>
              `<button class="recent-project" data-project="${C.escape(p.path)}"><span data-icon="audio-file"></span><div><strong>${C.escape(p.title)}</strong><small>${C.escape(formatDate(p.date))}</small></div></button>`,
          )
          .join("")
      : '<p class="recent-empty">Deine Aufnahmen und Projekte finden hier ihren Platz.</p>';
  }
  function switchView(next) {
    view = next;
    $("overflowMenu").hidden = true;
    document
      .querySelectorAll("[data-nav]")
      .forEach((b) => b.classList.toggle("active", b.dataset.nav === next));
    $("transcriptView").hidden = next !== "transcript";
    $("reportsView").hidden = next !== "reports";
    if (next === "reports") renderReports(true);
  }
  function getSegments() {
    return S.recording
      ? liveSegments.map((s, i) => ({ ...s, id: "live" + i, speaker: "LIVE" }))
      : S.segments;
  }
  function renderTranscript(force = false) {
    const query = $("transcriptSearch").value.trim(),
      all = getSegments();
    const filtered = all.filter((s) =>
      (s.text + " " + name(s.speaker))
        .toLocaleLowerCase()
        .includes(query.toLocaleLowerCase()),
    );
    const key = JSON.stringify([
      filtered.map((s) => [s.id, s.text, s.speaker]),
      S.speakers,
      selectedSegment,
      visibleLimit,
      query,
      S.project,
      S.recording,
      S.busy,
    ]);
    $("transcriptMeta").textContent = S.recording
      ? "Vorläufiger Live-Text"
      : filtered.length
        ? `${filtered.length} ${filtered.length === 1 ? "Abschnitt" : "Abschnitte"} · ${speakerIDs().length} Stimmen`
        : "Noch keine Abschnitte";
    if (key === lastListKey && !force) return;
    lastListKey = key;
    if (!filtered.length) {
      if (query)
        $("transcriptList").innerHTML = empty(
          "search",
          "Keine passende Stelle.",
          "Versuche einen anderen Suchbegriff oder einen Sprechernamen.",
        );
      else if (S.recording)
        $("transcriptList").innerHTML = empty(
          "waveform",
          "Deine Worte kommen an.",
          S.settings.live
            ? "Die Live-Vorschau erscheint nach dem Modellstart."
            : "Die Aufnahme läuft. Nach dem Stoppen kannst du transkribieren.",
        );
      else if (S.project)
        $("transcriptList").innerHTML = empty(
          "text",
          "Bereit für die richtigen Worte.",
          "Audio bei Bedarf bearbeiten und anschließend transkribieren.",
          `<button class="btn btn-mint" data-action="transcribe" ${S.busy ? "disabled" : ""}>${C.icon("sparkles")}Transkribieren</button>`,
        );
      else
        $("transcriptList").innerHTML = empty(
          "audio-file",
          "Hier beginnt dein Gespräch.",
          "Öffne eine Aufnahme oder nimm direkt auf. Dein Audio und deine Gedanken bleiben auf deinem Rechner.",
          `<button class="btn btn-mint" data-action="open">${C.icon("upload")}Audio oder Video öffnen</button>`,
        );
    } else {
      const scroll = $("transcriptList").scrollTop;
      $("transcriptList").innerHTML =
        filtered
          .slice(0, visibleLimit)
          .map(
            (s) =>
              `<article class="transcript-row ${s.id === selectedSegment ? "active" : ""}" data-segment="${C.escape(s.id)}" tabindex="0" role="button" aria-label="${C.escape(name(s.speaker) + " " + C.stamp(s.start))}"><span class="speaker-avatar">${C.escape(S.recording ? "●" : initial(s.speaker))}</span><div class="transcript-row-body"><div class="transcript-row-heading"><strong>${C.escape(S.recording ? "Live-Vorschau" : name(s.speaker))}</strong><time>${C.stamp(s.start)} — ${C.stamp(s.end)}</time></div><p>${C.highlight(s.text, query)}</p></div></article>`,
          )
          .join("") +
        (filtered.length > visibleLimit
          ? `<button class="text-button transcript-load-more" data-action="moreSegments">Weitere Abschnitte anzeigen (${filtered.length - visibleLimit})</button>`
          : "");
      $("transcriptList").scrollTop = scroll;
      if (S.recording)
        $("transcriptList").scrollTop = $("transcriptList").scrollHeight;
    }
    hydrate($("transcriptList"));
  }
  function renderInspector() {
    const item = S.segments.find((s) => s.id === selectedSegment);
    $("inspectorEmpty").hidden = !!item;
    $("inspectorEditor").hidden = !item;
    if (!item) {
      editorID = null;
      editorDirty = false;
      return;
    }
    if (editorID !== item.id) editorDirty = false;
    $("selectedTime").textContent =
      C.stamp(item.start) + " — " + C.stamp(item.end);
    const ids = speakerIDs(),
      key = JSON.stringify([ids, S.speakers]);
    if (key !== speakerListKey) {
      const draftSpeaker = $("segmentSpeaker").value;
      $("segmentSpeaker").innerHTML = ids
        .map(
          (id) =>
            `<option value="${C.escape(id)}">${C.escape(name(id))}</option>`,
        )
        .join("");
      speakerListKey = key;
      if (editorDirty && ids.includes(draftSpeaker)) $("segmentSpeaker").value = draftSpeaker;
    }
    if (editorID !== item.id || !editorDirty)
      $("segmentSpeaker").value = item.speaker;
    if (editorID !== item.id || !editorDirty)
      $("segmentText").value = item.text;
    editorID = item.id;
    $("segmentText").disabled = S.busy;
    $("segmentSpeaker").disabled = S.busy;
  }
  async function flushEditor() {
    if (saveFlight) {
      await saveFlight;
      return flushEditor();
    }
    clearTimeout(editTimer);
    editTimer = null;
    const item = S.segments.find((s) => s.id === editorID);
    if (!item || S.busy) return true;
    const text = $("segmentText").value,
      speaker = $("segmentSpeaker").value;
    if (text.trim() === item.text && speaker === item.speaker) return true;
    $("editSaveStatus").textContent = "Wird gespeichert …";
    saveFlight = command("update_segment", {
      id: item.id,
      text,
      speaker,
    });
    const success = await saveFlight;
    saveFlight = null;
    if (success && editorID === item.id && $("segmentText").value === text && $("segmentSpeaker").value === speaker) {
      editorDirty = false;
      renderInspector();
    }
    $("savedIndicator").hidden = !S.project || S.busy || editorDirty;
    $("editSaveStatus").textContent = success
      ? "Gespeichert"
      : "Speichern fehlgeschlagen";
    return success;
  }
  async function selectSegment(id, play = false) {
    if (S.recording) return;
    if ((await flushEditor()) === false) return;
    selectedSegment = id;
    renderTranscript();
    renderInspector();
    if (play) {
      const item = S.segments.find((s) => s.id === id);
      if (item) seek(item.start);
    }
  }

  function profileIcon(kind) {
    return S.profiles.find((p) => p.kind === kind)?.icon || "document";
  }
  function renderReports(force = false) {
    if (selectedReport === null && S.reports.length)
      selectedReport = S.reports.length - 1;
    const key = JSON.stringify([
      S.reports.map((r) => [r.index, r.created, r.stale, r.kind, r.model]),
      selectedReport,
      compareView,
    ]);
    if (key === lastReportsKey && !force) return;
    lastReportsKey = key;
    $("resultList").innerHTML = S.reports.length
      ? [...S.reports]
          .reverse()
          .map(
            (r) =>
              `<button class="result-item ${r.index === selectedReport ? "active" : ""}" data-report="${r.index}"><span class="result-icon">${C.icon(profileIcon(r.kind))}</span><div><strong>${C.escape(r.label || "Auswertung")}</strong><small>${C.escape(r.model)}</small><small class="${r.stale ? "stale-tag" : ""}">${r.stale ? "Älterer Stand" : C.escape(r.created.replace("T", " · ").slice(0, 18))}</small></div></button>`,
          )
          .join("")
      : '<div class="recent-empty">Noch keine Auswertung.<br>Du wählst, was du brauchst.</div>';
    const report = S.reports[selectedReport];
    if (!report) {
      $("resultWorkspace").innerHTML =
        `<div class="empty-state"><span class="empty-icon">${C.icon("sparkles")}</span><h2>Dein Gespräch.<br>Genau die Auswertung, die du brauchst.</h2><p>Ein ausführliches Protokoll, ein kurzer Überblick oder konkrete Aufgaben. Du wählst den Auftrag.</p><button class="btn btn-teal" data-action="newReport">${C.icon("plus")}Auswertung auswählen</button></div>`;
      return;
    }
    const group = report.group
      ? S.reports.filter(
          (r) => r.group === report.group && r.kind === report.kind,
        )
      : [report];
    const pair = compareView && group.length === 2 ? group : [report];
    $("resultWorkspace").classList.toggle("compare", pair.length > 1);
    $("resultWorkspace").innerHTML = pair
      .map(
        (r, i) =>
          `<article class="report-reader"><div class="report-reader-toolbar"><div><strong>${C.escape(r.label)}</strong><small>${C.escape(r.model)} · ${r.options?.verify ? "mit Belegprüfung" : "KI-Entwurf"}</small></div><div class="report-toolbar-actions">${i === 0 && group.length === 2 ? `<button class="icon-btn" data-action="toggleCompare" title="${pair.length === 2 ? "Einzeln anzeigen" : "Nebeneinander vergleichen"}" aria-label="Modellvergleich umschalten">${C.icon("columns")}</button>` : ""}<button class="btn btn-white" data-export-report="${r.index}">${C.icon("download")}Markdown</button></div></div>${r.stale ? '<div class="report-stale">Älterer Stand · Das Transkript oder die Sitzungsangaben wurden seit dieser Auswertung geändert.</div>' : ""}<div class="report-body ${pair.length > 1 ? "compare" : ""}" data-report-body="${r.index}">${C.markdown(r.markdown)}</div></article>`,
      )
      .join("");
  }

  function openAnalysis() {
    if (S.busy || S.recording) {
      toast("Bitte die laufende Verarbeitung zuerst beenden.");
      return;
    }
    if (!S.segments.length) {
      toast(
        "Bitte zuerst transkribieren oder ein WhisperX-Transkript importieren.",
      );
      return;
    }
    $("profileGrid").innerHTML = S.profiles
      .map(
        (p) =>
          `<button type="button" class="profile-choice ${p.kind === selectedKind ? "selected" : ""}" data-kind="${C.escape(p.kind)}" aria-pressed="${p.kind === selectedKind}"><span class="profile-icon">${C.icon(p.icon)}</span><div><strong>${C.escape(p.label)}</strong><small>${C.escape(p.description)}</small></div><span class="profile-radio"></span></button>`,
      )
      .join("");
    const primary =
      $("primaryModel").value ||
      S.models.find((m) => m.startsWith("gemma")) ||
      S.models[0];
    const secondary =
      $("secondaryModel").value ||
      S.models.find((m) => m.startsWith("qwen3:")) ||
      S.models.find((m) => m !== primary) ||
      primary;
    const options = S.models
      .map((m) => `<option value="${C.escape(m)}">${C.escape(m)}</option>`)
      .join("");
    $("primaryModel").innerHTML = options;
    $("secondaryModel").innerHTML = options;
    $("primaryModel").value = primary;
    $("secondaryModel").value = secondary;
    updateReportChoice();
    showDialog("analysisDialog");
  }
  function updateReportChoice() {
    document.querySelectorAll("[data-kind]").forEach((b) => {
      b.classList.toggle("selected", b.dataset.kind === selectedKind);
      b.setAttribute("aria-pressed", b.dataset.kind === selectedKind);
    });
    const label =
      S.profiles.find((p) => p.kind === selectedKind)?.label || "Auswertung";
    $("generateReportButton").innerHTML =
      C.icon("sparkles") + "<span>" + C.escape(label) + " erstellen</span>";
    $("generateReportButton").disabled = !S.models.length;
    $("secondaryModelGroup").hidden = !$("compareModels").checked;
  }
  function openSettings() {
    if (S.busy || S.recording) {
      toast("Einstellungen sind während der Verarbeitung gesperrt.");
      return;
    }
    $("asrLanguage").value = S.settings.language;
    $("asrModel").value = S.settings.asr_model;
    $("asrDevice").value = S.settings.device;
    $("asrSpeakers").value = S.settings.speaker_count;
    $("asrDiarize").checked = S.settings.diarize;
    showDialog("settingsDialog");
  }
  async function fillMicrophones() {
    try { S.microphones = await window.NativeRecorder.listDevices(); } catch (e) { toast("Mikrofone konnten nicht gelesen werden: " + e.message, true); }
    const selected = $("microphoneSelect").value || S.settings.microphone || "";
    $("microphoneSelect").innerHTML = S.microphones
      .map(
        (m) =>
          `<option value="${C.escape(m.value)}">${C.escape(m.name)}</option>`,
      )
      .join("");
    $("microphoneSelect").value = S.microphones.some(
      (m) => m.value === selected,
    )
      ? selected
      : "";
  }
  async function openRecording() {
    if (S.recording) {
      pause();
      return command("record_stop");
    }
    if (S.busy) return;
    await fillMicrophones();
    $("liveEnabled").checked = S.settings.live;
    $("liveFinalize").checked = S.settings.finalize_live;
    showDialog("recordDialog");
  }
  function openSpeakers(add = false) {
    if (!S.project || S.busy) {
      toast("Zuerst ein Transkript öffnen.");
      return;
    }
    speakerDraft = Object.fromEntries(speakerIDs().map((id) => [id, name(id)]));
    if (add) addSpeakerRow(false);
    renderSpeakerNames(false);
    showDialog("speakersDialog");
  }
  function addSpeakerRow(render = true) {
    if (
      Object.keys(speakerDraft).filter((x) => x !== "UNBEKANNT").length >= 15
    ) {
      toast("Es sind bereits 15 Sprecher angelegt.");
      return;
    }
    for (let i = 0; i < 100; i++) {
      const id = "SPEAKER_" + String(i).padStart(2, "0");
      if (!(id in speakerDraft)) {
        speakerDraft[id] = "";
        break;
      }
    }
    if (render) renderSpeakerNames();
  }
  function renderSpeakerNames(preserve = true) {
    if (preserve) {
      const current = [
        ...$("speakerNames").querySelectorAll("[data-speaker-name]"),
      ];
      for (const input of current)
        speakerDraft[input.dataset.speakerName] = input.value;
    }
    $("speakerNames").innerHTML = Object.entries(speakerDraft)
      .map(
        ([id, value], i) =>
          `<div class="speaker-name-row"><span class="speaker-avatar">${String(i + 1).padStart(2, "0")}</span><label for="name_${C.escape(id)}">${C.escape(id)}</label><input id="name_${C.escape(id)}" data-speaker-name="${C.escape(id)}" value="${C.escape(value)}" placeholder="Name oder Rolle"></div>`,
      )
      .join("");
  }
  function openLibrary() {
    $("libraryList").innerHTML = S.recent.length
      ? S.recent
          .map(
            (p) =>
              `<button class="library-entry" data-project="${C.escape(p.path)}"><span class="library-icon">${C.icon("audio-file")}</span><div><strong>${C.escape(p.title)}</strong><small>${C.escape(formatDate(p.date))} · ${C.stamp(p.duration)}</small></div><span class="arrow">${C.icon("arrow-right")}</span></button>`,
          )
          .join("")
      : empty(
          "folder",
          "Platz für deine Gespräche.",
          "Jede geöffnete Aufnahme wird automatisch als Projekt gespeichert.",
        );
    showDialog("libraryDialog");
  }

  function updateSelection() {
    const selected = !!selection;
    $("selectionTimes").hidden = !selected;
    $("selectionHint").hidden = selected;
    if (selected) {
      $("selectionStart").value = C.stamp(selection[0], true);
      $("selectionEnd").value = C.stamp(selection[1], true);
    }
    $("deleteSelection").disabled = !selected || S.busy || S.recording;
    $("trimSelection").disabled = !selected || S.busy || S.recording;
    drawWave();
  }
  function eventTime(event) {
    const rect = canvas.getBoundingClientRect();
    return Math.max(
      0,
      Math.min(
        duration(),
        viewStart +
          ((event.clientX - rect.left) / Math.max(1, rect.width)) *
            visibleDuration(),
      ),
    );
  }
  function requestPeaks() {
    clearTimeout(waveTimer);
    const ticket = ++waveTicket;
    waveTimer = setTimeout(async () => {
      if (!S.project || S.recording) {
        drawWave();
        return;
      }
      const peaks = await command("waveform", {
        start: viewStart,
        end: Math.min(S.duration, viewStart + visibleDuration()),
        width: Math.min(1800, Math.max(100, Math.round(canvas.clientWidth))),
      });
      if (ticket === waveTicket && Array.isArray(peaks)) {
        wavePeaks = peaks;
        drawWave();
      }
    }, 40);
  }
  function drawWave() {
    const rect = canvas.getBoundingClientRect(),
      dpr = window.devicePixelRatio || 1,
      w = Math.max(1, rect.width),
      h = Math.max(1, rect.height);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const total = duration(),
      visible = visibleDuration(),
      mid = 24 + (h - 26) / 2,
      amp = (h - 35) / 2;
    ctx.font = "8px Studio, sans-serif";
    ctx.fillStyle = "#b4c2bf";
    for (let i = 0; i <= 6; i++) {
      const x = (i * w) / 6;
      ctx.textAlign = i === 0 ? "left" : i === 6 ? "right" : "center";
      ctx.fillText(
        C.stamp(Math.min(total, viewStart + (visible * i) / 6)),
        x,
        14,
      );
      ctx.strokeStyle = "#f0f5f2";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, 24);
      ctx.lineTo(x, h - 6);
      ctx.stroke();
    }
    ctx.strokeStyle = "#eaf2ed";
    ctx.beginPath();
    ctx.moveTo(0, mid);
    ctx.lineTo(w, mid);
    ctx.stroke();
    $("waveformEmpty").hidden = !!total || S.recording;
    if (wavePeaks.length) {
      const count = Math.floor(w / 3);
      for (let i = 0; i < count; i++) {
        const from = Math.floor((i / count) * wavePeaks.length),
          to = Math.max(
            from + 1,
            Math.floor(((i + 1) / count) * wavePeaks.length),
          );
        let peak = 0;
        for (let j = from; j < to; j++)
          peak = Math.max(peak, wavePeaks[j] || 0);
        const value = Math.max(1.2, peak ** 0.65 * amp),
          x = (i / count) * w;
        ctx.fillStyle = S.recording ? "#95c2ad" : "#9ccfb9";
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x, mid - value, 1.8, value * 2, 1);
        else ctx.rect(x, mid - value, 1.8, value * 2);
        ctx.fill();
      }
    }
    if (selection) {
      const x = ((selection[0] - viewStart) / visible) * w,
        x2 = ((selection[1] - viewStart) / visible) * w;
      ctx.fillStyle = "#2c957724";
      ctx.fillRect(x, 25, x2 - x, h - 31);
      ctx.strokeStyle = "#5baa8b";
      ctx.lineWidth = 1;
      ctx.strokeRect(x, 25, x2 - x, h - 31);
    }
    const scroll = $("waveScroll");
    scroll.hidden = zoomLevel < 0.01 || !S.project;
    scroll.value = Math.max(
      0,
      Math.min(1, viewStart / Math.max(0.01, total - visible)),
    );
    updatePlayhead();
  }
  function updatePlayhead() {
    let head = $("playhead");
    if (!head) {
      head = document.createElement("div");
      head.id = "playhead";
      head.className = "playhead";
      canvas.parentElement.appendChild(head);
    }
    const ratio = (position - viewStart) / visibleDuration();
    head.hidden = !S.project || ratio < 0 || ratio > 1;
    head.style.left = ratio * 100 + "%";
  }
  function updateTransport() {
    $("playTime").innerHTML =
      C.stamp(position) + " <span>/ " + C.stamp(duration()) + "</span>";
    $("playButton").innerHTML = C.icon(playing ? "pause" : "play");
    $("playButton").setAttribute("aria-label", playing ? "Pause" : "Abspielen");
    updatePlayhead();
  }
  function pause() {
    audio.pause();
    playing = false;
    updateTransport();
  }
  function seek(t) {
    if (!S.project) return;
    position = Math.max(0, Math.min(S.duration, t));
    const value = C.editedToSource(position, S.spans);
    sourceIndex = value.index;
    audio.currentTime = value.time;
    if (position < viewStart || position > viewStart + visibleDuration()) {
      viewStart = Math.max(
        0,
        Math.min(
          S.duration - visibleDuration(),
          position - visibleDuration() * 0.15,
        ),
      );
      requestPeaks();
    }
    updateTransport();
  }
  async function togglePlay() {
    if (!S.project || S.recording) return;
    if (playing) {
      pause();
      return;
    }
    if (position >= S.duration - 0.02) seek(selection ? selection[0] : 0);
    else if (selection && (position < selection[0] || position >= selection[1]))
      seek(selection[0]);
    else seek(position);
    audio.playbackRate = Number($("playbackSpeed").value);
    try {
      await audio.play();
      playing = true;
      updateTransport();
    } catch (error) {
      toast("Audio konnte nicht abgespielt werden: " + error.message, true);
    }
  }
  function tick() {
    if (playing && !audio.seeking) {
      let span = S.spans[sourceIndex];
      if (span) {
        if (audio.currentTime >= span[1] - 0.012) {
          if (sourceIndex < S.spans.length - 1) {
            sourceIndex++;
            audio.currentTime = S.spans[sourceIndex][0];
          } else {
            position = S.duration;
            pause();
          }
        }
        position = C.sourceToEdited(audio.currentTime, S.spans);
        if (selection && position >= selection[1]) {
          pause();
          seek(selection[1]);
        }
        if (position > viewStart + visibleDuration()) {
          viewStart = Math.max(
            0,
            Math.min(
              S.duration - visibleDuration(),
              position - visibleDuration() * 0.15,
            ),
          );
          requestPeaks();
        }
        updateTransport();
      }
    }
    requestAnimationFrame(tick);
  }

  async function action(which) {
    $("overflowMenu").hidden =
      which === "more" ? !$("overflowMenu").hidden : true;
    if (which === "open") return chooseFile("audio");
    if (which === "openProject") return chooseFile("project");
    if (which === "saveProject") return chooseFile("save_project");
    if (which === "exportAudio") return chooseFile("audio_export");
    if (which === "importTranscript") return chooseFile("transcript");
    if (which === "exportTranscript") return chooseFile("transcript_export");
    if (which === "record") return openRecording();
    if (which === "play") return togglePlay();
    if (which === "back") return seek(position - 10);
    if (which === "settings") return openSettings();
    if (which === "newReport") {
      if ((await flushEditor()) === false) return;
      return openAnalysis();
    }
    if (which === "speakers") return openSpeakers();
    if (which === "addSpeaker") return openSpeakers(true);
    if (which === "addSpeakerRow") return addSpeakerRow();
    if (which === "library") return openLibrary();
    if (which === "help") return api?.help();
    if (which === "refresh") {
      if (await command("refresh")) {
        backendDown = false;
        await flushEditor();
        toast("Lokale Verbindung wiederhergestellt; Modelle und Mikrofone werden geprüft.");
      }
      return;
    }
    if (which === "transcribe") {
      if ((await flushEditor()) === false) return;
      return command("transcribe");
    }
    if (which === "cancel") return command("cancel");
    if (which === "cut" || which === "trim") {
      if (!selection) return;
      if ((await flushEditor()) === false) return;
      pause();
      return command(which, { start: selection[0], end: selection[1] });
    }
    if (which === "undo") {
      if ((await flushEditor()) === false) return;
      pause();
      return command("undo");
    }
    if (which === "seekSelected") {
      const s = S.segments.find((s) => s.id === selectedSegment);
      if (s) seek(s.start);
      return;
    }
    if (which === "setSelection") {
      try {
        let a = C.parseTime($("selectionStart").value),
          b = C.parseTime($("selectionEnd").value);
        if (!(0 <= a && a < b && b <= S.duration + 0.001))
          throw new Error("Die Auswahl muss innerhalb der Aufnahme liegen.");
        selection = [a, Math.min(b, S.duration)];
        updateSelection();
        seek(a);
      } catch (e) {
        toast(e.message, true);
      }
      return;
    }
    if (which === "zoomReset") {
      zoomLevel = 0;
      viewStart = 0;
      $("zoom").value = "0";
      requestPeaks();
      return;
    }
    if (which === "toggleCompare") {
      compareView = !compareView;
      renderReports(true);
      return;
    }
    if (which === "moreSegments") {
      visibleLimit += 180;
      renderTranscript(true);
      return;
    }
    if (which === "metadata") {
      if (!S.project || S.busy) return;
      $("metadataTitle").value = S.title;
      $("metadataDate").value = S.date;
      $("metadataContext").value = S.context;
      showDialog("metadataDialog");
      return;
    }
    if (which === "setupSpeakers") {
      closeDialogs();
      showDialog("setupDialog");
      return;
    }
    if (which === "activity") {
      logs = (await command("logs")) || logs;
      $("activityLog").textContent = logs.join("\n") || "Noch keine Aktivität.";
      $("activityConnection").textContent = S.model_status || "Lokal";
      showDialog("activityDialog");
    }
  }

  document.addEventListener("click", async (event) => {
    const close = event.target.closest("[data-close]");
    if (close) {
      $(close.dataset.close).close();
      return;
    }
    const windowAction = event.target.closest("[data-window]");
    if (windowAction) {
      if (
        windowAction.dataset.window === "close" &&
        (await flushEditor()) === false
      )
        return;
      api?.window(windowAction.dataset.window);
      return;
    }
    const link = event.target.closest("[data-link]");
    if (link) {
      api?.openLink(link.dataset.link);
      return;
    }
    const nav = event.target.closest("[data-nav]");
    if (nav) {
      if ((await flushEditor()) === false) return;
      switchView(nav.dataset.nav);
      return;
    }
    const profile = event.target.closest("[data-kind]");
    if (profile) {
      selectedKind = profile.dataset.kind;
      updateReportChoice();
      return;
    }
    const project = event.target.closest("[data-project]");
    if (project) {
      if (S.busy || S.recording) {
        toast("Bitte die laufende Verarbeitung zuerst beenden.");
        return;
      }
      if ((await flushEditor()) === false) return;
      closeDialogs();
      pause();
      try {
        await api.openRecent(project.dataset.project);
      } catch (e) {
        toast(e.message, true);
      }
      return;
    }
    const segment = event.target.closest("[data-segment]");
    if (segment) {
      selectSegment(segment.dataset.segment);
      return;
    }
    const report = event.target.closest("[data-report]");
    if (report) {
      selectedReport = Number(report.dataset.report);
      renderReports(true);
      return;
    }
    const exporter = event.target.closest("[data-export-report]");
    if (exporter) {
      const index = Number(exporter.dataset.exportReport);
      return chooseFile("report_export", {
        index,
        label: S.reports[index].label,
      });
    }
    const source = event.target.closest("[data-source]");
    if (source) {
      event.preventDefault();
      const index = Number(
        source.closest("[data-report-body]").dataset.reportBody,
      );
      if (S.reports[index].stale) {
        toast(
          "Diese Fundstelle gehört zu einem älteren Stand. Die ursprünglichen Auszüge stehen im Markdown.",
        );
        return;
      }
      const id = source.dataset.source,
        item = S.segments.find((s) => s.id === id);
      if (item) {
        $("transcriptSearch").value = "";
        visibleLimit = Math.max(visibleLimit, S.segments.indexOf(item) + 25);
        switchView("transcript");
        await selectSegment(id, true);
        document
          .querySelector(`[data-segment="${id}"]`)
          ?.scrollIntoView({ block: "center" });
      }
      return;
    }
    const target = event.target.closest("[data-action]");
    if (target) {
      await action(target.dataset.action);
      return;
    }
    if (!event.target.closest("#overflowMenu")) $("overflowMenu").hidden = true;
  });
  document.addEventListener("dblclick", (event) => {
    const target = event.target.closest("[data-segment]");
    if (target) selectSegment(target.dataset.segment, true);
  });
  document.addEventListener("keydown", async (event) => {
    const input = /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName),
      button = event.target.tagName === "BUTTON";
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "o") {
      event.preventDefault();
      return chooseFile("audio");
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      return chooseFile("save_project");
    }
    if (
      (event.ctrlKey || event.metaKey) &&
      event.key.toLowerCase() === "z" &&
      !input
    ) {
      event.preventDefault();
      return action("undo");
    }
    if (
      event.code === "Space" &&
      !input &&
      !button &&
      !document.querySelector("dialog[open]")
    ) {
      event.preventDefault();
      return togglePlay();
    }
    if (
      event.key === "Delete" &&
      !input &&
      selection &&
      !document.querySelector("dialog[open]")
    ) {
      event.preventDefault();
      return action("cut");
    }
    if (event.key === "Escape" && !document.querySelector("dialog[open]")) {
      pause();
      selection = null;
      updateSelection();
      $("overflowMenu").hidden = true;
    }
    if (
      (event.key === "Enter" || event.key === " ") &&
      event.target.matches("[data-segment]")
    ) {
      event.preventDefault();
      selectSegment(event.target.dataset.segment, true);
    }
  });
  $("transcriptSearch").addEventListener("input", () => {
    visibleLimit = 180;
    renderTranscript();
  });
  $("transcriptList").addEventListener("scroll", () => {
    const e = $("transcriptList");
    if (
      e.scrollHeight - e.scrollTop - e.clientHeight < 180 &&
      e.querySelector(".transcript-load-more")
    ) {
      visibleLimit += 180;
      renderTranscript();
    }
  });
  $("segmentText").addEventListener("input", () => {
    clearTimeout(editTimer);
    $("editSaveStatus").textContent = "Noch nicht gespeichert";
    editTimer = setTimeout(flushEditor, 650);
  });
  $("segmentText").addEventListener("input", () => {
    editorDirty = true;
    $("savedIndicator").hidden = true;
    $("editSaveStatus").textContent = "Änderungen noch nicht gespeichert";
  });
  $("segmentText").addEventListener("blur", flushEditor);
  $("segmentSpeaker").addEventListener("change", () => { editorDirty = true; flushEditor(); });
  $("compareModels").addEventListener("change", updateReportChoice);
  $("analysisForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    if ((await flushEditor()) === false) return;
    const models = [$("primaryModel").value];
    if ($("compareModels").checked) models.push($("secondaryModel").value);
    if (models.some((x) => !x)) {
      toast("Bitte ein lokales Modell auswählen.");
      return;
    }
    if (models.length === 2 && models[0] === models[1]) {
      toast("Für den Vergleich bitte zwei unterschiedliche Modelle wählen.");
      return;
    }
    $("analysisDialog").close();
    switchView("reports");
    await command("generate", {
      kind: selectedKind,
      models,
      options: {
        language: $("reportLanguage").value,
        detail: $("reportDetail").value,
        focus: $("reportFocus").value,
        verify: $("verifyEvidence").checked,
        include_sources: $("includeSources").checked,
      },
    });
  });
  $("settingsForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const ok = await command("settings", {
      language: $("asrLanguage").value,
      asr_model: $("asrModel").value,
      device: $("asrDevice").value,
      speaker_count: $("asrSpeakers").value,
      diarize: $("asrDiarize").checked,
    });
    if (ok) $("settingsDialog").close();
  });
  $("recordForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    if ((await flushEditor()) === false) return;
    const ok = await command("settings", {
      microphone: $("microphoneSelect").value,
      live: $("liveEnabled").checked,
      finalize_live: $("liveFinalize").checked,
    });
    if (ok) {
      $("recordDialog").close();
      pause();
      await command("record_start");
    }
  });
  $("metadataForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const ok = await command("metadata", {
      title: $("metadataTitle").value,
      date: $("metadataDate").value,
      context: $("metadataContext").value,
    });
    if (ok) $("metadataDialog").close();
  });
  $("speakersForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const names = Object.fromEntries(
      [...$("speakerNames").querySelectorAll("[data-speaker-name]")].map(
        (input) => [
          input.dataset.speakerName,
          input.value.trim() || input.dataset.speakerName,
        ],
      ),
    );
    const ok = await command("speakers", { names });
    if (ok) $("speakersDialog").close();
  });
  $("setupForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const token = $("hfToken").value;
    $("hfToken").value = "";
    $("setupDialog").close();
    await command("setup_speakers", { token });
  });
  for (let i = 1; i <= 15; i++)
    $("asrSpeakers").add(new Option(String(i) + " Sprecher", String(i)));
  $("zoom").addEventListener("input", () => {
    const center =
      position >= viewStart && position <= viewStart + visibleDuration()
        ? position
        : viewStart + visibleDuration() / 2;
    zoomLevel = Number($("zoom").value);
    viewStart = Math.max(
      0,
      Math.min(S.duration - visibleDuration(), center - visibleDuration() / 2),
    );
    requestPeaks();
  });
  $("waveScroll").addEventListener("input", () => {
    viewStart =
      Number($("waveScroll").value) *
      Math.max(0, S.duration - visibleDuration());
    requestPeaks();
  });
  $("playbackSpeed").addEventListener(
    "change",
    () => (audio.playbackRate = Number($("playbackSpeed").value)),
  );
  audio.addEventListener("ended", () => {
    position = S.duration;
    pause();
  });
  audio.addEventListener("error", () => {
    if (S.project)
      toast(
        "Die Audio-Arbeitskopie konnte nicht geladen werden. Bitte das Projekt neu öffnen.",
        true,
      );
  });
  canvas.addEventListener("pointerdown", (event) => {
    if (!S.project || S.recording || event.button !== 0) return;
    canvas.setPointerCapture(event.pointerId);
    drag = { start: eventTime(event), x: event.clientX };
    selection = null;
    seek(drag.start);
    updateSelection();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (drag) {
      let end = eventTime(event);
      selection = [Math.min(drag.start, end), Math.max(drag.start, end)];
      updateSelection();
    } else if (S.project) {
      $("hoverTime").hidden = false;
      $("hoverTime").textContent = C.stamp(eventTime(event));
      $("hoverTime").style.left =
        Math.max(25, Math.min(canvas.clientWidth - 25, event.offsetX)) + "px";
    }
  });
  canvas.addEventListener("pointerup", (event) => {
    if (!drag) return;
    if (Math.abs(event.clientX - drag.x) < 4) {
      selection = null;
      updateSelection();
    }
    drag = null;
  });
  canvas.addEventListener("pointerleave", () => ($("hoverTime").hidden = true));
  canvas.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    selection = null;
    updateSelection();
  });
  new ResizeObserver(() => {
    drawWave();
    if (S.project) requestPeaks();
  }).observe(canvas.parentElement);
  if (api) {
    api.onEvent((event) => {
      if (event.type === "prepare_close") {
        (async () => { await window.NativeRecorder.stop(); return flushEditor(); })().then((saved) =>
          api.window(saved === false ? "close-cancel" : "close-ready"),
        ).catch(error => { toast(error.message, true); api.window("close-cancel"); });
        return;
      }
      if (event.type === "state") renderState(event.data);
      else if (event.type === "backend_up") {
        backendDown = false;
        flushEditor();
      }
      else if (event.type === "backend_down") {
        backendDown = true;
        pause();
        renderState({ ...S, busy: false, recording: false, status: "Fehler: " + event.data });
        toast(event.data, true);
      }
      else if (event.type === "progress") {
        $("statusText").textContent = event.data.text;
      } else if (event.type === "error") {
        toast(event.data, true);
        $("statusDot").classList.add("error");
      } else if (event.type === "log") {
        logs.push(String(event.data));
        logs = logs.slice(-350);
        if ($("activityDialog").open)
          $("activityLog").textContent = logs.join("\n");
      } else if (event.type === "record_wave") {
        recordElapsed = event.data.elapsed;
        wavePeaks = event.data.peaks;
        position = recordElapsed;
        drawWave();
        updateTransport();
        $("audioDuration").innerHTML =
          C.icon("clock") +
          "<span>" +
          C.stamp(recordElapsed) +
          " Aufnahme</span>";
      } else if (event.type === "live") {
        liveSegments.push(event.data);
        renderTranscript();
      } else if (event.type === "report_ready") {
        selectedReport = event.data.index;
        compareView = true;
        switchView("reports");
        renderReports(true);
        toast(
          "Auswertung fertig: " +
            (S.profiles.find((p) => p.kind === event.data.kind)?.label ||
              "Auswertung"),
        );
      }
    });
    command("init");
  } else {
    $("statusText").textContent =
      "Vorschau ohne Desktop-Verbindung · zum Arbeiten über WhisperX Studio starten.";
  }
  window.addEventListener("native-recording-error", event => toast(event.detail, true));
  window.StudioActions = { flushEditor };
  hydrate();
  renderRecent();
  renderTranscript();
  renderReports();
  drawWave();
  requestAnimationFrame(tick);
})();
