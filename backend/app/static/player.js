const app = document.getElementById("app");
const sessionId = app.dataset.sessionId;
const videoGrid = document.getElementById("video-grid");
const btnPlay = document.getElementById("btn-play");
const seekBar = document.getElementById("seek-bar");
const timeDisplay = document.getElementById("time-display");
const audioSourceSelect = document.getElementById("audio-source");
const warningsEl = document.getElementById("warnings");

let syncData = null;
let clips = [];
let masterTime = 0;
let playing = false;
let lastTimestamp = null;
let animFrameId = null;
let totalDuration = 0;

function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = (sec % 60).toFixed(1);
    return `${m}:${s.padStart(4, "0")}`;
}

async function fetchSync() {
    const resp = await fetch(`/sessions/${sessionId}/sync`);
    if (!resp.ok) throw new Error("Failed to fetch sync data");
    return resp.json();
}

function createClipPanel(clip, index) {
    const panel = document.createElement("div");
    panel.className = "clip-panel";
    panel.dataset.clipId = clip.id;

    const label = document.createElement("div");
    label.className = "clip-label";
    label.textContent = clip.label;
    panel.appendChild(label);

    const video = document.createElement("video");
    video.src = clip.media_url;
    video.muted = true;
    video.preload = "auto";
    video.className = "clip-video";
    panel.appendChild(video);

    const controls = document.createElement("div");
    controls.className = "clip-controls";

    const offsetRow = document.createElement("div");
    offsetRow.className = "offset-row";

    const offsetLabel = document.createElement("span");
    offsetLabel.className = "offset-label";
    offsetLabel.textContent = `Offset: ${clip.offset_sec.toFixed(2)}s`;
    offsetRow.appendChild(offsetLabel);

    const slider = document.createElement("input");
    slider.type = "range";
    slider.className = "nudge-slider";
    slider.min = "-5";
    slider.max = "5";
    slider.step = "0.01";
    slider.value = clip.offset_sec;
    slider.dataset.clipId = clip.id;
    offsetRow.appendChild(slider);

    const resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.className = "btn-reset-offset";
    resetBtn.textContent = "Reset to auto";
    resetBtn.dataset.clipId = clip.id;
    resetBtn.disabled = clip.offset_source === "auto";
    offsetRow.appendChild(resetBtn);

    controls.appendChild(offsetRow);
    panel.appendChild(controls);

    return { panel, video, slider, offsetLabel, resetBtn };
}

function buildUI() {
    videoGrid.innerHTML = "";
    audioSourceSelect.innerHTML = "";
    clips = [];

    syncData.clips.forEach((clip, i) => {
        const { panel, video, slider, offsetLabel, resetBtn } = createClipPanel(clip, i);
        videoGrid.appendChild(panel);

        audioSourceSelect.add(new Option(clip.label, clip.id));

        clips.push({ ...clip, video, slider, offsetLabel, resetBtn, panel });

        slider.addEventListener("input", () => {
            offsetLabel.textContent = `Offset: ${parseFloat(slider.value).toFixed(2)}s`;
        });

        slider.addEventListener("change", async () => {
            const newOffset = parseFloat(slider.value);
            try {
                const resp = await fetch(`/sessions/${sessionId}/clips/${clip.id}/offset`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ offset_sec: newOffset }),
                });
                if (resp.ok) {
                    const updated = await resp.json();
                    applySyncUpdate(updated);
                }
            } catch (e) {
                console.error("Nudge failed", e);
            }
        });

        resetBtn.addEventListener("click", async () => {
            try {
                const resp = await fetch(`/sessions/${sessionId}/clips/${clip.id}/offset`, {
                    method: "DELETE",
                });
                if (resp.ok) {
                    const updated = await resp.json();
                    applySyncUpdate(updated);
                }
            } catch (e) {
                console.error("Reset failed", e);
            }
        });
    });

    if (syncData.audio_source_clip_id) {
        audioSourceSelect.value = syncData.audio_source_clip_id;
    }

    totalDuration = syncData.total_duration_sec || 0;
    seekBar.max = totalDuration;
    seekBar.value = 0;
    masterTime = 0;
    updateTimeDisplay();

    if (syncData.warnings && syncData.warnings.length > 0) {
        warningsEl.textContent = syncData.warnings.join(" | ");
        warningsEl.classList.remove("hidden");
    } else {
        warningsEl.classList.add("hidden");
    }

    applyAudioSource();
}

function applySyncUpdate(updated) {
    syncData = updated;
    totalDuration = updated.total_duration_sec || 0;
    seekBar.max = totalDuration;

    updated.clips.forEach((uc) => {
        const c = clips.find((x) => x.id === uc.id);
        if (!c) return;
        c.offset_sec = uc.offset_sec;
        c.offset_source = uc.offset_source;
        c.moment_local_sec = uc.moment_local_sec;
        c.slider.value = uc.offset_sec;
        c.offsetLabel.textContent = `Offset: ${uc.offset_sec.toFixed(2)}s`;
        c.resetBtn.disabled = uc.offset_source === "auto";
    });

    seekAllToMasterTime(masterTime);
    updateTimeDisplay();
}

function applyAudioSource() {
    const selectedId = audioSourceSelect.value;
    clips.forEach((c) => {
        c.video.muted = c.id !== selectedId;
    });
}

function seekAllToMasterTime(t) {
    clips.forEach((c) => {
        const target = (c.moment_local_sec || 0) + t;
        const dur = c.duration_sec;
        if (dur != null && target > dur) {
            c.video.currentTime = dur;
        } else if (target < 0) {
            c.video.currentTime = 0;
        } else {
            c.video.currentTime = target;
        }
    });
}

function updateTimeDisplay() {
    timeDisplay.textContent = `${formatTime(masterTime)} / ${formatTime(totalDuration)}`;
}

function syncLoop(timestamp) {
    if (!playing) return;

    if (lastTimestamp === null) {
        lastTimestamp = timestamp;
    }

    const elapsed = (timestamp - lastTimestamp) / 1000;
    lastTimestamp = timestamp;
    masterTime += elapsed;

    if (masterTime >= totalDuration) {
        masterTime = totalDuration;
        pauseAll();
    }

    seekBar.value = masterTime;
    updateTimeDisplay();

    clips.forEach((c) => {
        const expected = (c.moment_local_sec || 0) + masterTime;
        const actual = c.video.currentTime;
        if (Math.abs(actual - expected) > 0.15) {
            const dur = c.duration_sec;
            if (dur != null && expected > dur) {
                c.video.currentTime = dur;
            } else if (expected < 0) {
                c.video.currentTime = 0;
            } else {
                c.video.currentTime = expected;
            }
        }
    });

    animFrameId = requestAnimationFrame(syncLoop);
}

function playAll() {
    playing = true;
    lastTimestamp = null;
    btnPlay.textContent = "Pause";
    clips.forEach((c) => {
        c.video.play().catch(() => {});
    });
    animFrameId = requestAnimationFrame(syncLoop);
}

function pauseAll() {
    playing = false;
    btnPlay.textContent = "Play";
    clips.forEach((c) => {
        c.video.pause();
    });
    if (animFrameId) {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
    }
    lastTimestamp = null;
}

btnPlay.addEventListener("click", () => {
    if (playing) {
        pauseAll();
    } else {
        playAll();
    }
});

seekBar.addEventListener("input", () => {
    masterTime = parseFloat(seekBar.value);
    seekAllToMasterTime(masterTime);
    updateTimeDisplay();
});

audioSourceSelect.addEventListener("change", applyAudioSource);

async function init() {
    try {
        syncData = await fetchSync();
        buildUI();
    } catch (e) {
        console.error("Init failed", e);
        warningsEl.textContent = "Failed to load session data.";
        warningsEl.classList.remove("hidden");
    }
}

init();
