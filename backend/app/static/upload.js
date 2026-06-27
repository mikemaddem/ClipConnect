const uploadApp = document.getElementById("upload-app");
const initialSessionId = uploadApp.dataset.sessionId || null;
const sessionSetup = document.getElementById("session-setup");
const titleInput = document.getElementById("session-title");
const btnCreateSession = document.getElementById("btn-create-session");
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const fileList = document.getElementById("file-list");
const uploadActions = document.getElementById("upload-actions");
const btnUpload = document.getElementById("btn-upload");
const btnAlign = document.getElementById("btn-align");
const statusArea = document.getElementById("status-area");
const statusText = document.getElementById("status-text");
const progressContainer = document.getElementById("progress-container");

let sessionId = initialSessionId;
let selectedFiles = [];

if (sessionId) {
    sessionSetup.classList.add("hidden");
}

btnCreateSession.addEventListener("click", async () => {
    const title = titleInput.value.trim() || null;
    try {
        const resp = await fetch("/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title }),
        });
        if (!resp.ok) throw new Error("Failed to create session");
        const data = await resp.json();
        sessionId = data.id;
        sessionSetup.classList.add("hidden");
        const url = new URL(window.location);
        url.pathname = `/sessions/${sessionId}/upload`;
        window.history.replaceState(null, "", url);
    } catch (e) {
        alert("Failed to create session: " + e.message);
    }
});

dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    addFiles(e.dataTransfer.files);
});

fileInput.addEventListener("change", () => {
    addFiles(fileInput.files);
    fileInput.value = "";
});

function addFiles(files) {
    for (const f of files) {
        selectedFiles.push(f);
    }
    renderFileList();
    btnUpload.disabled = !sessionId;
    uploadActions.classList.remove("hidden");
}

function renderFileList() {
    fileList.innerHTML = "";
    selectedFiles.forEach((f, i) => {
        const item = document.createElement("div");
        item.className = "file-item";
        item.innerHTML = `<span class="file-name">${f.name}</span><span class="file-size">${(f.size / 1048576).toFixed(1)} MB</span><button type="button" class="btn-remove" data-index="${i}">&times;</button>`;
        fileList.appendChild(item);
    });
    fileList.querySelectorAll(".btn-remove").forEach((btn) => {
        btn.addEventListener("click", () => {
            selectedFiles.splice(parseInt(btn.dataset.index), 1);
            renderFileList();
            if (selectedFiles.length === 0) {
                uploadActions.classList.add("hidden");
            }
        });
    });
}

btnUpload.addEventListener("click", async () => {
    if (!sessionId || selectedFiles.length === 0) return;

    btnUpload.disabled = true;
    statusArea.classList.remove("hidden");
    statusText.textContent = "Uploading...";

    progressContainer.innerHTML = "";
    const progressBars = selectedFiles.map((f) => {
        const wrapper = document.createElement("div");
        wrapper.className = "progress-item";
        wrapper.innerHTML = `<span class="progress-label">${f.name}</span><div class="progress-bar"><div class="progress-fill" style="width:0%"></div></div>`;
        progressContainer.appendChild(wrapper);
        return wrapper.querySelector(".progress-fill");
    });

    const formData = new FormData();
    selectedFiles.forEach((f) => formData.append("files", f));

    try {
        await new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", `/sessions/${sessionId}/clips/`);

            xhr.upload.addEventListener("progress", (e) => {
                if (e.lengthComputable) {
                    const pct = (e.loaded / e.total) * 100;
                    const perFile = pct / selectedFiles.length;
                    progressBars.forEach((bar, i) => {
                        const filePct = Math.min(100, Math.max(0, (pct - i * (100 / selectedFiles.length)) * (selectedFiles.length / 1)));
                        bar.style.width = Math.min(100, filePct) + "%";
                    });
                }
            });

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    progressBars.forEach((bar) => { bar.style.width = "100%"; });
                    resolve();
                } else {
                    reject(new Error(`Upload failed: ${xhr.status}`));
                }
            };
            xhr.onerror = () => reject(new Error("Upload network error"));
            xhr.send(formData);
        });

        statusText.textContent = "Upload complete!";
        selectedFiles = [];
        renderFileList();

        if (btnAlign.classList.contains("hidden")) {
            btnAlign.classList.remove("hidden");
        }
    } catch (e) {
        statusText.textContent = e.message;
        btnUpload.disabled = false;
    }
});

btnAlign.addEventListener("click", async () => {
    if (!sessionId) return;

    btnAlign.disabled = true;
    statusText.textContent = "Starting alignment...";

    try {
        const resp = await fetch(`/sessions/${sessionId}/align`, { method: "POST" });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Failed to start alignment");
        }
        const { job_id } = await resp.json();
        statusText.textContent = "Aligning clips...";
        pollJob(job_id);
    } catch (e) {
        statusText.textContent = e.message;
        btnAlign.disabled = false;
    }
});

async function pollJob(jobId) {
    const poll = async () => {
        try {
            const resp = await fetch(`/jobs/${jobId}`);
            if (!resp.ok) throw new Error("Poll failed");
            const data = await resp.json();

            if (data.status === "done") {
                statusText.textContent = "Alignment complete! Redirecting...";
                setTimeout(() => {
                    window.location.href = `/play/${sessionId}`;
                }, 1000);
                return;
            }

            if (data.status === "failed") {
                statusText.textContent = `Alignment failed: ${data.detail?.error || "unknown error"}`;
                btnAlign.disabled = false;
                return;
            }

            statusText.textContent = `Aligning... ${data.progress}%`;
            setTimeout(poll, 1500);
        } catch (e) {
            statusText.textContent = "Polling error: " + e.message;
            setTimeout(poll, 3000);
        }
    };

    poll();
}
