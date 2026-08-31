"use strict";


/* ============================================================
   RING HISTORY
   ============================================================ */

console.log("====================================");
console.log("[HISTORY] history.js v30 loaded");
console.log("====================================");


/* ============================================================
   ELEMENTS
   ============================================================ */

const deviceSelect =
    document.getElementById("deviceSelect");

const refreshButton =
    document.getElementById("refreshButton");

const errorRetryButton =
    document.getElementById("errorRetryButton");

const statusEl =
    document.getElementById("status");

const selectedCameraEl =
    document.getElementById("selectedCamera");

const eventCountEl =
    document.getElementById("eventCount");

const historyStatusEl =
    document.getElementById("historyStatus");

const lastUpdatedEl =
    document.getElementById("lastUpdated");

const loadingState =
    document.getElementById("loadingState");

const errorState =
    document.getElementById("errorState");

const emptyState =
    document.getElementById("emptyState");

const errorMessage =
    document.getElementById("errorMessage");

const eventsContainer =
    document.getElementById("eventsContainer");


/* ============================================================
   MODAL
   ============================================================ */

const eventModal =
    document.getElementById("eventModal");

const modalBackdrop =
    document.getElementById("modalBackdrop");

const closeModalButton =
    document.getElementById("closeModalButton");

const modalCloseFooterButton =
    document.getElementById(
        "modalCloseFooterButton"
    );

const modalTitle =
    document.getElementById("modalTitle");

const modalCamera =
    document.getElementById("modalCamera");

const modalEventType =
    document.getElementById("modalEventType");

const modalStart =
    document.getElementById("modalStart");

const modalEnd =
    document.getElementById("modalEnd");

const modalDuration =
    document.getElementById("modalDuration");


/* ============================================================
   VIDEO
   ============================================================ */

const eventVideo =
    document.getElementById("eventVideo");

const videoLoading =
    document.getElementById("videoLoading");

const videoUnavailable =
    document.getElementById(
        "videoUnavailable"
    );

const videoErrorMessage =
    document.getElementById(
        "videoErrorMessage"
    );

const modalPlayButton =
    document.getElementById(
        "modalPlayButton"
    );


/* ============================================================
   STATE
   ============================================================ */

let devices = [];

let historyEvents = [];

let currentDeviceId = "";

let currentDeviceName = "";

let currentEvent = null;


/* ============================================================
   STATUS
   ============================================================ */

function setStatus(
    text,
    state = "ready"
) {

    if (!statusEl) {
        return;
    }

    statusEl.textContent = text;

    statusEl.className =
        "status status--" + state;
}


/* ============================================================
   LOADING / ERROR / EMPTY
   ============================================================ */

function showLoading() {

    if (loadingState) {
        loadingState.hidden = false;
    }

    if (errorState) {
        errorState.hidden = true;
    }

    if (emptyState) {
        emptyState.hidden = true;
    }

    if (eventsContainer) {
        eventsContainer.innerHTML = "";
    }

    if (historyStatusEl) {
        historyStatusEl.textContent =
            "Loading";
    }
}


function showError(message) {

    console.error(
        "[HISTORY] ERROR:",
        message
    );

    if (loadingState) {
        loadingState.hidden = true;
    }

    if (emptyState) {
        emptyState.hidden = true;
    }

    if (eventsContainer) {
        eventsContainer.innerHTML = "";
    }

    if (errorState) {
        errorState.hidden = false;
    }

    if (errorMessage) {
        errorMessage.textContent =
            message;
    }

    if (historyStatusEl) {
        historyStatusEl.textContent =
            "Error";
    }

    setStatus(
        "History error",
        "error"
    );
}


function showEmpty() {

    if (loadingState) {
        loadingState.hidden = true;
    }

    if (errorState) {
        errorState.hidden = true;
    }

    if (emptyState) {
        emptyState.hidden = false;
    }

    if (historyStatusEl) {
        historyStatusEl.textContent =
            "No events";
    }

    setStatus(
        "No events",
        "ready"
    );
}


function showEvents() {

    if (loadingState) {
        loadingState.hidden = true;
    }

    if (errorState) {
        errorState.hidden = true;
    }

    if (emptyState) {
        emptyState.hidden = true;
    }

    if (historyStatusEl) {
        historyStatusEl.textContent =
            "Connected";
    }

    setStatus(
        "Ring connected",
        "ready"
    );
}


/* ============================================================
   TIME HELPERS
   ============================================================ */

function normaliseTimestamp(timestamp) {

    let value =
        Number(timestamp);

    if (!Number.isFinite(value)) {
        return null;
    }

    if (value < 100000000000) {
        value *= 1000;
    }

    return value;
}


function formatDate(timestamp) {

    const value =
        normaliseTimestamp(timestamp);

    if (value === null) {
        return "Unknown";
    }

    const date =
        new Date(value);

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return "Unknown";
    }

    return new Intl.DateTimeFormat(
        undefined,
        {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false
        }
    ).format(date);
}


function formatShortDate(timestamp) {

    const value =
        normaliseTimestamp(timestamp);

    if (value === null) {
        return "Unknown";
    }

    return new Intl.DateTimeFormat(
        undefined,
        {
            day: "2-digit",
            month: "short",
            year: "numeric"
        }
    ).format(
        new Date(value)
    );
}


function formatDuration(
    start,
    end
) {

    const startValue =
        normaliseTimestamp(start);

    const endValue =
        normaliseTimestamp(end);

    if (
        startValue === null ||
        endValue === null
    ) {
        return "Unknown";
    }

    let seconds =
        Math.round(
            Math.max(
                0,
                endValue - startValue
            ) / 1000
        );

    const minutes =
        Math.floor(
            seconds / 60
        );

    seconds =
        seconds % 60;

    if (minutes > 0) {

        return (
            minutes +
            "m " +
            seconds +
            "s"
        );
    }

    return seconds + "s";
}


/* ============================================================
   EVENT TYPE
   ============================================================ */

function cleanEventType(
    eventType
) {

    if (!eventType) {
        return "Unknown event";
    }

    return String(eventType)
        .replace(
            /[_-]+/g,
            " "
        )
        .replace(
            /\b\w/g,
            function(letter) {
                return letter.toUpperCase();
            }
        );
}


/* ============================================================
   DEVICE HELPERS
   ============================================================ */

function getDeviceId(device) {

    if (!device) {
        return "";
    }

    if (device.id) {
        return String(
            device.id
        );
    }

    if (
        device.data &&
        device.data.id
    ) {
        return String(
            device.data.id
        );
    }

    return "";
}


function getDeviceName(device) {

    if (!device) {
        return "Unknown camera";
    }

    const attributes =
        device.attributes || {};

    return (
        attributes.description ||
        attributes.name ||
        attributes.device_name ||
        attributes.nickname ||
        attributes.location ||
        device.name ||
        device.description ||
        "Ring camera"
    );
}


/* ============================================================
   LOAD DEVICES
   ============================================================ */

async function loadDevices() {

    console.log(
        "[HISTORY] Loading devices"
    );

    setStatus(
        "Loading devices...",
        "loading"
    );

    try {

        const response =
            await fetch(
                "/ring/devices/",
                {
                    method: "GET",
                    headers: {
                        "Accept":
                            "application/json"
                    },
                    cache: "no-store"
                }
            );

        const text =
            await response.text();

        let payload;

        try {

            payload =
                JSON.parse(text);

        } catch (error) {

            console.error(
                "[HISTORY] Device raw response:",
                text.substring(
                    0,
                    1000
                )
            );

            throw new Error(
                "Device API returned invalid JSON."
            );
        }

        if (!response.ok) {

            throw new Error(
                payload.message ||
                payload.error ||
                "Device request failed."
            );
        }

        devices =
            extractDevices(
                payload
            );

        console.log(
            "[HISTORY] Devices:",
            devices
        );

        populateDeviceSelect();

        if (
            devices.length === 0
        ) {

            if (deviceSelect) {

                deviceSelect.innerHTML =
                    `
                    <option value="">
                        No cameras found
                    </option>
                    `;
            }

            if (selectedCameraEl) {
                selectedCameraEl.textContent =
                    "No cameras";
            }

            if (eventCountEl) {
                eventCountEl.textContent =
                    "0";
            }

            showEmpty();

            return;
        }


        /*
         * Preserve the currently selected
         * camera where possible.
         */

        let selectedDevice =
            devices.find(
                function(device) {

                    return (
                        getDeviceId(device) ===
                        currentDeviceId
                    );
                }
            );


        /*
         * Otherwise select first camera.
         */

        if (!selectedDevice) {

            selectedDevice =
                devices[0];
        }


        currentDeviceId =
            getDeviceId(
                selectedDevice
            );

        currentDeviceName =
            getDeviceName(
                selectedDevice
            );


        if (deviceSelect) {

            deviceSelect.value =
                currentDeviceId;
        }


        updateSelectedCamera();

        await loadHistory();

    } catch (error) {

        console.error(
            "[HISTORY] Device error:",
            error
        );

        showError(
            error.message ||
            "Unable to load Ring devices."
        );
    }
}


/* ============================================================
   EXTRACT DEVICES
   ============================================================ */

function extractDevices(payload) {

    if (!payload) {
        return [];
    }

    if (
        Array.isArray(
            payload.data
        )
    ) {
        return payload.data;
    }

    if (
        Array.isArray(
            payload.devices
        )
    ) {
        return payload.devices;
    }

    if (
        payload.data &&
        Array.isArray(
            payload.data.data
        )
    ) {
        return payload.data.data;
    }

    return [];
}


/* ============================================================
   POPULATE DEVICE SELECT
   ============================================================ */

function populateDeviceSelect() {

    if (!deviceSelect) {

        console.error(
            "[HISTORY] #deviceSelect missing"
        );

        return;
    }

    deviceSelect.innerHTML = "";

    devices.forEach(
        function(device) {

            const id =
                getDeviceId(
                    device
                );

            if (!id) {
                return;
            }

            const option =
                document.createElement(
                    "option"
                );

            option.value =
                id;

            option.textContent =
                getDeviceName(
                    device
                );

            deviceSelect.appendChild(
                option
            );
        }
    );

    console.log(
        "[HISTORY] Device options:",
        deviceSelect.options.length
    );
}


/* ============================================================
   DEVICE CHANGE
   ============================================================ */

if (deviceSelect) {

    deviceSelect.addEventListener(
        "change",
        async function() {

            const selectedId =
                deviceSelect.value;

            const device =
                devices.find(
                    function(item) {

                        return (
                            getDeviceId(item) ===
                            selectedId
                        );
                    }
                );

            if (!device) {

                console.error(
                    "[HISTORY] Selected device not found"
                );

                return;
            }

            currentDeviceId =
                selectedId;

            currentDeviceName =
                getDeviceName(
                    device
                );

            updateSelectedCamera();

            await loadHistory();
        }
    );
}


/* ============================================================
   UPDATE CAMERA
   ============================================================ */

function updateSelectedCamera() {

    if (!selectedCameraEl) {
        return;
    }

    selectedCameraEl.textContent =
        currentDeviceName ||
        "No camera selected";
}


/* ============================================================
   LOAD HISTORY
   ============================================================ */

async function loadHistory() {

    if (!currentDeviceId) {

        showError(
            "No Ring camera has been selected."
        );

        return;
    }

    showLoading();

    const endpoint =
        "/ring/history/" +
        encodeURIComponent(
            currentDeviceId
        ) +
        "/";

    console.log(
        "[HISTORY] GET:",
        endpoint
    );

    try {

        const response =
            await fetch(
                endpoint,
                {
                    method: "GET",
                    headers: {
                        "Accept":
                            "application/json"
                    },
                    cache: "no-store"
                }
            );

        const text =
            await response.text();

        let payload;

        try {

            payload =
                JSON.parse(text);

        } catch (error) {

            console.error(
                "[HISTORY] Raw response:",
                text.substring(
                    0,
                    2000
                )
            );

            throw new Error(
                "History API returned HTML instead of JSON."
            );
        }

        if (!response.ok) {

            throw new Error(
                payload.details ||
                payload.error ||
                "History request failed: HTTP " +
                response.status
            );
        }

        historyEvents =
            extractHistoryEvents(
                payload
            );

        console.log(
            "[HISTORY] Events:",
            historyEvents
        );

        if (
            !historyEvents.length
        ) {

            if (eventCountEl) {
                eventCountEl.textContent =
                    "0";
            }

            showEmpty();

            return;
        }

        if (eventCountEl) {

            eventCountEl.textContent =
                historyEvents.length;
        }

        renderEvents(
            historyEvents
        );

        showEvents();

        if (lastUpdatedEl) {

            lastUpdatedEl.textContent =
                "Updated " +
                new Intl.DateTimeFormat(
                    undefined,
                    {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                        hour12: false
                    }
                ).format(
                    new Date()
                );
        }

    } catch (error) {

        console.error(
            "[HISTORY] History error:",
            error
        );

        showError(
            error.message ||
            "Unable to load Ring history."
        );
    }
}


/* ============================================================
   EXTRACT HISTORY
   ============================================================ */

function extractHistoryEvents(
    payload
) {

    if (!payload) {
        return [];
    }

    if (
        Array.isArray(
            payload.data
        )
    ) {
        return payload.data;
    }

    if (
        payload.data &&
        Array.isArray(
            payload.data.data
        )
    ) {
        return payload.data.data;
    }

    if (
        Array.isArray(
            payload.events
        )
    ) {
        return payload.events;
    }

    return [];
}


/* ============================================================
   RENDER EVENTS
   ============================================================ */

function renderEvents(
    events
) {

    if (!eventsContainer) {
        return;
    }

    eventsContainer.innerHTML = "";

    events.forEach(
        function(event, index) {

            eventsContainer.appendChild(
                createEventCard(
                    event,
                    index
                )
            );
        }
    );
}


/* ============================================================
   EVENT CARD
   ============================================================ */

function createEventCard(
    event,
    index
) {

    const attributes =
        event.attributes || {};

    const eventType =
        attributes.event_type ||
        attributes.type ||
        "event";

    const start =
        attributes.start;

    const end =
        attributes.end;


    const article =
        document.createElement(
            "article"
        );

    article.className =
        "event-card";


    article.innerHTML = `

        <div class="event-icon">
            ${getEventIcon(eventType)}
        </div>


        <div class="event-main">

            <div class="event-title-row">

                <h3 class="event-title">
                    ${escapeHtml(
                        cleanEventType(
                            eventType
                        )
                    )}
                </h3>

                <span class="event-badge">
                    Ring
                </span>

            </div>


            <div class="event-meta">

                <span>
                    ${escapeHtml(
                        formatShortDate(
                            start
                        )
                    )}
                </span>

                <span>
                    ${escapeHtml(
                        formatDate(
                            start
                        )
                    )}
                </span>

                <span>
                    Duration:
                    ${escapeHtml(
                        formatDuration(
                            start,
                            end
                        )
                    )}
                </span>

            </div>

        </div>


        <div class="event-action">

            <button
                class="view-event"
                type="button"
            >
                ▶ View Event
            </button>

        </div>
    `;


    const button =
        article.querySelector(
            ".view-event"
        );


    if (button) {

        button.addEventListener(
            "click",
            function() {

                openEventModal(
                    event
                );
            }
        );
    }


    return article;
}


/* ============================================================
   EVENT ICON
   ============================================================ */

function getEventIcon(
    eventType
) {

    const type =
        String(
            eventType || ""
        ).toLowerCase();

    if (
        type.includes("motion")
    ) {
        return "◉";
    }

    if (
        type.includes("ding") ||
        type.includes("doorbell")
    ) {
        return "⌂";
    }

    if (
        type.includes("person")
    ) {
        return "●";
    }

    return "•";
}


/* ============================================================
   OPEN MODAL
   ============================================================ */

function openEventModal(
    event
) {

    currentEvent =
        event;


    const attributes =
        event.attributes || {};


    const eventType =
        attributes.event_type ||
        attributes.type ||
        "Event";


    const start =
        attributes.start;

    const end =
        attributes.end;


    if (modalTitle) {

        modalTitle.textContent =
            cleanEventType(
                eventType
            );
    }


    if (modalCamera) {

        modalCamera.textContent =
            currentDeviceName ||
            "Unknown camera";
    }


    if (modalEventType) {

        modalEventType.textContent =
            cleanEventType(
                eventType
            );
    }


    if (modalStart) {

        modalStart.textContent =
            formatDate(
                start
            );
    }


    if (modalEnd) {

        modalEnd.textContent =
            formatDate(
                end
            );
    }


    if (modalDuration) {

        modalDuration.textContent =
            formatDuration(
                start,
                end
            );
    }


    resetVideo();


    if (!eventModal) {
        return;
    }


    eventModal.hidden =
        false;

    eventModal.setAttribute(
        "aria-hidden",
        "false"
    );


    document.body.style.overflow =
        "hidden";


    if (closeModalButton) {

        setTimeout(
            function() {

                closeModalButton.focus();

            },
            50
        );
    }


    /*
     * Load the recording immediately.
     *
     * IMPORTANT:
     * The event ID comes from event.id.
     * The device ID comes from the selected
     * camera.
     */

    loadEventVideo(
        event
    );
}


/* ============================================================
   RESET VIDEO
   ============================================================ */

function resetVideo() {

    if (eventVideo) {

        eventVideo.pause();

        eventVideo.removeAttribute(
            "src"
        );

        eventVideo.load();

        eventVideo.hidden =
            true;
    }


    if (videoLoading) {

        videoLoading.hidden =
            true;
    }


    if (videoUnavailable) {

        videoUnavailable.hidden =
            false;
    }


    if (videoErrorMessage) {

        videoErrorMessage.textContent =
            "The recording could not be loaded.";
    }


    if (modalPlayButton) {

        modalPlayButton.hidden =
            true;
    }
}


/* ============================================================
   LOAD EVENT VIDEO
   ============================================================ */

async function loadEventVideo(
    event
) {

    if (!event) {
        return;
    }


    const eventId =
        event.id ||
        "";


    if (!eventId) {

        console.error(
            "[HISTORY VIDEO] Event has no ID:",
            event
        );

        showVideoUnavailable(
            "This event does not contain a recording ID."
        );

        return;
    }


    if (!currentDeviceId) {

        showVideoUnavailable(
            "No camera is selected."
        );

        return;
    }


    const attributes =
        event.attributes || {};


    const start =
        normaliseTimestamp(
            attributes.start
        );


    const end =
        normaliseTimestamp(
            attributes.end
        );


    if (!start) {

        showVideoUnavailable(
            "The event does not contain a valid start time."
        );

        return;
    }


    let duration =
        60000;


    if (
        end &&
        end > start
    ) {

        duration =
            end - start;
    }


    /*
     * Keep duration within Ring's allowed
     * historical clip range.
     */

    duration =
        Math.min(
            Math.max(
                duration,
                1000
            ),
            15 * 60 * 1000
        );


    /*
     * IMPORTANT:
     *
     * We call the dedicated Django video
     * endpoint.
     *
     * This MUST NOT be the history endpoint.
     */

    const videoEndpoint =
        "/ring/history/" +
        encodeURIComponent(
            currentDeviceId
        ) +
        "/video/" +
        encodeURIComponent(
            eventId
        ) +
        "/?start=" +
        encodeURIComponent(
            start
        ) +
        "&duration=" +
        encodeURIComponent(
            duration
        );


    console.log(
        "===================================="
    );

    console.log(
        "[HISTORY VIDEO] Event:",
        eventId
    );

    console.log(
        "[HISTORY VIDEO] Device:",
        currentDeviceId
    );

    console.log(
        "[HISTORY VIDEO] Start:",
        start
    );

    console.log(
        "[HISTORY VIDEO] Duration:",
        duration
    );

    console.log(
        "[HISTORY VIDEO] Endpoint:",
        videoEndpoint
    );

    console.log(
        "===================================="
    );


    if (videoLoading) {

        videoLoading.hidden =
            false;
    }


    if (videoUnavailable) {

        videoUnavailable.hidden =
            true;
    }


    try {

        /*
         * Ask Django whether the recording
         * can be retrieved.
         */

        const response =
            await fetch(
                videoEndpoint,
                {
                    method: "GET",
                    headers: {
                        "Accept":
                            "video/mp4,video/*,*/*"
                    },
                    cache: "no-store"
                }
            );


        console.log(
            "[HISTORY VIDEO] HTTP:",
            response.status
        );


        if (!response.ok) {

            let message =
                "Recording unavailable.";


            try {

                const contentType =
                    response.headers.get(
                        "content-type"
                    ) || "";


                if (
                    contentType.includes(
                        "application/json"
                    )
                ) {

                    const errorData =
                        await response.json();


                    message =
                        errorData.details ||
                        errorData.error ||
                        message;
                }

            } catch (error) {
                // Ignore JSON parsing errors.
            }


            throw new Error(
                message
            );
        }


        /*
         * Django should return the actual
         * video bytes.
         */

        const blob =
            await response.blob();


        console.log(
            "[HISTORY VIDEO] Blob:",
            blob.type,
            blob.size
        );


        if (
            !blob ||
            blob.size === 0
        ) {

            throw new Error(
                "Ring returned an empty recording."
            );
        }


        const contentType =
            blob.type ||
            "";


        /*
         * If Django accidentally returns JSON
         * instead of video, don't feed it into
         * the video element.
         */

        if (
            contentType.includes(
                "application/json"
            )
        ) {

            const text =
                await blob.text();

            let data;

            try {
                data =
                    JSON.parse(text);
            } catch (error) {
                data = null;
            }

            throw new Error(
                data?.details ||
                data?.error ||
                "Ring returned an error instead of video."
            );
        }


        const objectUrl =
            URL.createObjectURL(
                blob
            );


        if (!eventVideo) {

            throw new Error(
                "Video player is missing from the page."
            );
        }


        eventVideo.src =
            objectUrl;


        eventVideo.hidden =
            false;


        if (videoLoading) {

            videoLoading.hidden =
                true;
        }


        if (videoUnavailable) {

            videoUnavailable.hidden =
                true;
        }


        if (modalPlayButton) {

            modalPlayButton.hidden =
                false;
        }


        /*
         * Revoke the object URL after the
         * video element has loaded it.
         */

        eventVideo.addEventListener(
            "loadedmetadata",
            function() {

                console.log(
                    "[HISTORY VIDEO] Metadata loaded"
                );

            },
            {
                once: true
            }
        );


        eventVideo.addEventListener(
            "error",
            function() {

                console.error(
                    "[HISTORY VIDEO] Browser could not decode recording"
                );

                showVideoUnavailable(
                    "The recording was returned but your browser could not play it."
                );

            },
            {
                once: true
            }
        );


    } catch (error) {

        console.error(
            "[HISTORY VIDEO] ERROR:",
            error
        );


        showVideoUnavailable(
            error.message ||
            "Unable to load recording."
        );
    }
}


/* ============================================================
   VIDEO UNAVAILABLE
   ============================================================ */

function showVideoUnavailable(
    message
) {

    if (videoLoading) {

        videoLoading.hidden =
            true;
    }


    if (eventVideo) {

        eventVideo.pause();

        eventVideo.hidden =
            true;
    }


    if (videoUnavailable) {

        videoUnavailable.hidden =
            false;
    }


    if (videoErrorMessage) {

        videoErrorMessage.textContent =
            message;
    }


    if (modalPlayButton) {

        modalPlayButton.hidden =
            true;
    }
}


/* ============================================================
   PLAY BUTTON
   ============================================================ */

if (modalPlayButton) {

    modalPlayButton.addEventListener(
        "click",
        function() {

            if (!eventVideo) {
                return;
            }


            if (
                eventVideo.hidden ||
                !eventVideo.src
            ) {

                if (currentEvent) {

                    loadEventVideo(
                        currentEvent
                    );
                }

                return;
            }


            eventVideo.play()
                .then(
                    function() {

                        console.log(
                            "[HISTORY VIDEO] Playing"
                        );

                    }
                )
                .catch(
                    function(error) {

                        console.error(
                            "[HISTORY VIDEO] Play failed:",
                            error
                        );

                    }
                );
        }
    );
}


/* ============================================================
   CLOSE MODAL
   ============================================================ */

function closeEventModal() {

    if (!eventModal) {
        return;
    }


    if (eventVideo) {

        eventVideo.pause();

        /*
         * Release blob URL.
         */

        if (
            eventVideo.src &&
            eventVideo.src.startsWith(
                "blob:"
            )
        ) {

            URL.revokeObjectURL(
                eventVideo.src
            );
        }

        eventVideo.removeAttribute(
            "src"
        );

        eventVideo.load();

        eventVideo.hidden =
            true;
    }


    eventModal.hidden =
        true;


    eventModal.setAttribute(
        "aria-hidden",
        "true"
    );


    document.body.style.overflow =
        "";


    currentEvent =
        null;
}


/* ============================================================
   CLOSE BUTTONS
   ============================================================ */

if (closeModalButton) {

    closeModalButton.addEventListener(
        "click",
        function(event) {

            event.preventDefault();

            event.stopPropagation();

            closeEventModal();
        }
    );
}


if (modalCloseFooterButton) {

    modalCloseFooterButton.addEventListener(
        "click",
        function(event) {

            event.preventDefault();

            event.stopPropagation();

            closeEventModal();
        }
    );
}


if (modalBackdrop) {

    modalBackdrop.addEventListener(
        "click",
        function(event) {

            event.preventDefault();

            event.stopPropagation();

            closeEventModal();
        }
    );
}


/* ============================================================
   ESCAPE
   ============================================================ */

document.addEventListener(
    "keydown",
    function(event) {

        if (
            event.key === "Escape" &&
            eventModal &&
            !eventModal.hidden
        ) {

            closeEventModal();
        }
    }
);


/* ============================================================
   REFRESH
   ============================================================ */

if (refreshButton) {

    refreshButton.addEventListener(
        "click",
        async function() {

            refreshButton.disabled =
                true;

            try {

                await loadDevices();

            } finally {

                refreshButton.disabled =
                    false;
            }
        }
    );
}


if (errorRetryButton) {

    errorRetryButton.addEventListener(
        "click",
        async function() {

            await loadDevices();
        }
    );
}


/* ============================================================
   HTML ESCAPING
   ============================================================ */

function escapeHtml(
    value
) {

    return String(
        value ?? ""
    )
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );
}


/* ============================================================
   START
   ============================================================ */

document.addEventListener(
    "DOMContentLoaded",
    function() {

        console.log(
            "[HISTORY] DOM ready"
        );


        if (!deviceSelect) {

            console.error(
                "[HISTORY] CRITICAL: #deviceSelect missing"
            );

            return;
        }


        if (!eventsContainer) {

            console.error(
                "[HISTORY] CRITICAL: #eventsContainer missing"
            );

            return;
        }


        loadDevices();
    }
);