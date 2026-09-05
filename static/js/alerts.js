"use strict";

/* ============================================================
   RING ALERTS

   ALERT
      ↓
   DEVICE ID
      ↓
   OPEN ALERT
      ↓
   ALERT VIDEO ENDPOINT
      ↓
   STORED RECORDING
      ↓
   VIDEO

   IMPORTANT:
   ------------------------------------------------------------
   Alert rows use openAlert() to load the matching recording.

   No History endpoint.
   No alert video endpoint.
   No History video.
   ============================================================ */

console.log("====================================");
console.log("[ALERTS] alerts.js loaded");
console.log("[ALERTS] ALERT -> DEVICE -> OPEN ALERT -> LIVE");
console.log("[ALERTS] WebRTC race protection enabled");
console.log("[ALERTS] STUN / ICE diagnostics enabled");
console.log("[ALERTS] Alert clicks play the associated recording");
console.log("[ALERTS] DIAGNOSTIC LOGGING ENABLED");
console.log("====================================");


/* ============================================================
   CONFIG
   ============================================================ */

const ALERT_POLL_INTERVAL = 5000;

const ICE_GATHER_TIMEOUT = 10000;

const VIDEO_START_DELAY = 5000;

const VIDEO_PLAY_MAX_ATTEMPTS = 5;


/*
 * Ring's WebRTC documentation recommends STUN.
 *
 * IMPORTANT:
 *
 * We are NOT using TURN here.
 * This remains unchanged.
 */
const ICE_SERVERS = [
    {
        urls: "stun:stun.l.google.com:19302"
    }
];


/* ============================================================
   DOM
   ============================================================ */

const alertsContainer =
    document.getElementById("alertsContainer");

const alertsList =
    document.getElementById("alertsList");

const liveVideo =
    document.getElementById("liveVideo");

const noStreamOverlay =
    document.getElementById("noStreamOverlay");

const videoLoading =
    document.getElementById("videoLoading");

const liveIndicator =
    document.getElementById("liveIndicator");

const statusEl =
    document.getElementById("status");

const connectionStatus =
    document.getElementById("connectionStatus");

const currentDevice =
    document.getElementById("currentDevice");

const currentAlert =
    document.getElementById("currentAlert");

const alertTitle =
    document.getElementById("alertTitle");

const alertMessage =
    document.getElementById("alertMessage");

const alertTime =
    document.getElementById("alertTime");

const alertDevice =
    document.getElementById("alertDevice");

const alertType =
    document.getElementById("alertType");

const stopLiveButton =
    document.getElementById("stopLiveButton");

const closeLiveButton =
    document.getElementById("closeLiveButton");

const refreshButton =
    document.getElementById("refreshButton");

const soundButton =
    document.getElementById("soundButton");

const errorRetryButton =
    document.getElementById("errorRetryButton");

const errorState =
    document.getElementById("errorState");

const errorMessage =
    document.getElementById("errorMessage");

const emptyState =
    document.getElementById("emptyState");


/* ============================================================
   STATE
   ============================================================ */

let alerts = [];

let lastAlertId = null;

let pageInitialised = false;

let pollTimer = null;

let pollInProgress = false;

let pollingPaused = false;


/* ============================================================
   WEBRTC STATE
   ============================================================ */

let peerConnection = null;

let currentDeviceId = null;

let currentDeviceName = null;

let currentSessionUrl = null;

let liveStarting = false;

let liveActive = false;


/*
 * Every live attempt gets a generation.
 */

let liveGeneration = 0;


/*
 * Current MediaStream.
 */

let currentMediaStream = null;


/*
 * Prevent multiple stop calls.
 */

let stopInProgress = false;


/*
 * Current video play promise.
 */

let playPromise = null;


/*
 * Abort controller for WHEP.
 */

let liveAbortController = null;


/*
 * Current alert.
 */

let activeAlert = null;

let alertVideoUrl = null;

let liveAutoStopTimer = null;


/*
 * VIDEO PLAYBACK RETRY STATE
 */

let videoPlayAttempt = 0;

let videoPlayTimer = null;


/* ============================================================
   LOG
   ============================================================ */

function log() {

    console.log(
        "[ALERTS]",
        ...arguments
    );

}


/* ============================================================
   WEBRTC DIAGNOSTICS
   ============================================================ */

function logVideoDiagnostics(label) {

    if (!liveVideo) {
        return;
    }

    console.log(
        `[ALERT LIVE][DIAG] ${label}`,
        {
            readyState:
                liveVideo.readyState,

            networkState:
                liveVideo.networkState,

            paused:
                liveVideo.paused,

            ended:
                liveVideo.ended,

            currentTime:
                liveVideo.currentTime,

            duration:
                liveVideo.duration,

            videoWidth:
                liveVideo.videoWidth,

            videoHeight:
                liveVideo.videoHeight,

            srcObject:
                liveVideo.srcObject,

            error:
                liveVideo.error,

            bufferedLen:
                liveVideo.buffered
                    ? liveVideo.buffered.length
                    : null
        }
    );

}


function logTrackDiagnostics(
    label,
    track
) {

    if (!track) {
        return;
    }

    console.log(
        `[ALERT LIVE][DIAG] ${label}`,
        {
            readyState:
                track.readyState,

            enabled:
                track.enabled,

            muted:
                track.muted,

            kind:
                track.kind,

            id:
                track.id
        }
    );

}


function logIceCandidate(
    candidate
) {

    if (!candidate) {

        console.log(
            "[ALERT LIVE][ICE] Candidate gathering complete."
        );

        return;
    }

    console.log(
        "[ALERT LIVE][ICE] Local candidate:",
        candidate.candidate
    );

    console.log(
        "[ALERT LIVE][ICE] Candidate details:",
        {
            protocol:
                candidate.protocol,

            address:
                candidate.address,

            port:
                candidate.port,

            type:
                candidate.type,

            tcpType:
                candidate.tcpType,

            foundation:
                candidate.foundation,

            priority:
                candidate.priority
        }
    );

}


async function logSelectedCandidatePair(
    connection,
    label = "ICE candidate pair"
) {

    if (
        !connection ||
        typeof connection.getStats !==
            "function"
    ) {
        return;
    }

    try {

        const stats =
            await connection.getStats();

        let selectedPair =
            null;

        let candidateMap =
            new Map();

        stats.forEach(
            function(report) {

                if (
                    report.type ===
                    "candidate-pair"
                ) {

                    if (
                        report.state ===
                        "succeeded" &&
                        (
                            report.nominated ===
                                true ||
                            report.selected ===
                                true
                        )
                    ) {

                        selectedPair =
                            report;

                    }

                }

                if (
                    report.type ===
                    "local-candidate"
                ) {

                    candidateMap.set(
                        report.id,
                        report
                    );

                }

                if (
                    report.type ===
                    "remote-candidate"
                ) {

                    candidateMap.set(
                        report.id,
                        report
                    );

                }

            }
        );


        if (!selectedPair) {

            stats.forEach(
                function(report) {

                    if (
                        report.type ===
                        "candidate-pair" &&
                        report.state ===
                        "succeeded"
                    ) {

                        selectedPair =
                            report;

                    }

                }
            );

        }


        if (!selectedPair) {

            console.warn(
                `[ALERT LIVE][ICE] ${label}: no selected/succeeded candidate pair found.`
            );

            return;

        }


        const localCandidate =
            candidateMap.get(
                selectedPair.localCandidateId
            );

        const remoteCandidate =
            candidateMap.get(
                selectedPair.remoteCandidateId
            );


        console.log(
            `[ALERT LIVE][ICE] ${label}:`,
            {
                state:
                    selectedPair.state,

                nominated:
                    selectedPair.nominated,

                selected:
                    selectedPair.selected,

                localCandidate:
                    localCandidate
                        ? {
                            type:
                                localCandidate.candidateType,

                            protocol:
                                localCandidate.protocol,

                            address:
                                localCandidate.address,

                            port:
                                localCandidate.port
                        }
                        : null,

                remoteCandidate:
                    remoteCandidate
                        ? {
                            type:
                                remoteCandidate.candidateType,

                            protocol:
                                remoteCandidate.protocol,

                            address:
                                remoteCandidate.address,

                            port:
                                remoteCandidate.port
                        }
                        : null,

                bytesSent:
                    selectedPair.bytesSent,

                bytesReceived:
                    selectedPair.bytesReceived,

                packetsSent:
                    selectedPair.packetsSent,

                packetsReceived:
                    selectedPair.packetsReceived
            }
        );

    } catch (error) {

        console.warn(
            "[ALERT LIVE][ICE] Candidate pair diagnostics failed:",
            error
        );

    }

}


async function probeInboundVideoStats(
    connection,
    sampleMs = 1500
) {

    if (
        !connection ||
        typeof connection.getStats !==
            "function"
    ) {

        console.warn(
            "[ALERT LIVE][DIAG] getStats() unavailable."
        );

        return;

    }


    try {

        const before =
            await connection.getStats();


        let beforeInbound =
            null;


        before.forEach(
            function(report) {

                if (
                    report.type ===
                        "inbound-rtp" &&
                    (
                        report.kind ===
                            "video" ||
                        report.mediaType ===
                            "video"
                    )
                ) {

                    beforeInbound =
                        report;

                }

            }
        );


        await new Promise(
            function(resolve) {

                setTimeout(
                    resolve,
                    sampleMs
                );

            }
        );


        const after =
            await connection.getStats();


        let afterInbound =
            null;


        after.forEach(
            function(report) {

                if (
                    report.type ===
                        "inbound-rtp" &&
                    (
                        report.kind ===
                            "video" ||
                        report.mediaType ===
                            "video"
                    )
                ) {

                    afterInbound =
                        report;

                }

            }
        );


        if (
            !beforeInbound ||
            !afterInbound
        ) {

            console.warn(
                "[ALERT LIVE][DIAG] No inbound-rtp video stats report available."
            );


            console.log(
                "[ALERT LIVE][DIAG] Available WebRTC stats:"
            );


            after.forEach(
                function(report) {

                    if (
                        report.type ===
                            "inbound-rtp" ||
                        report.type ===
                            "candidate-pair" ||
                        report.type ===
                            "remote-inbound-rtp"
                    ) {

                        console.log(
                            "[ALERT LIVE][DIAG] STAT:",
                            report
                        );

                    }

                }
            );


            return;

        }


        const packetsBefore =
            Number(
                beforeInbound.packetsReceived ||
                0
            );


        const packetsAfter =
            Number(
                afterInbound.packetsReceived ||
                0
            );


        const framesBefore =
            Number(
                beforeInbound.framesDecoded ||
                0
            );


        const framesAfter =
            Number(
                afterInbound.framesDecoded ||
                0
            );


        const packetsDelta =
            packetsAfter -
            packetsBefore;


        const framesDelta =
            framesAfter -
            framesBefore;


        console.log(
            `[ALERT LIVE][DIAG] Inbound video RTP over ${sampleMs}ms:`,
            {
                packetsReceived_delta:
                    packetsDelta,

                framesDecoded_delta:
                    framesDelta,

                packetsReceived:
                    packetsAfter,

                framesDecoded:
                    framesAfter,

                packetsLost:
                    afterInbound.packetsLost,

                jitter:
                    afterInbound.jitter,

                bytesReceived:
                    afterInbound.bytesReceived
            }
        );


        if (
            packetsDelta ===
            0
        ) {

            console.warn(
                "[ALERT LIVE] No RTP video packets arrived during the sample window."
            );

        } else if (
            framesDelta ===
            0
        ) {

            console.warn(
                "[ALERT LIVE] RTP packets are arriving but no video frames are being decoded."
            );

        } else {

            console.log(
                "[ALERT LIVE] RTP packets and decoded frames are arriving."
            );

        }


    } catch (error) {

        console.warn(
            "[ALERT LIVE][DIAG] RTP stats probe failed:",
            error
        );

    }

}


/* ============================================================
   STATUS
   ============================================================ */

function setStatus(
    message,
    type = "idle"
) {

    if (statusEl) {

        statusEl.textContent =
            message;

        statusEl.className =
            "status status--" +
            type;

    }


    if (connectionStatus) {

        connectionStatus.textContent =
            message;

    }


    if (liveIndicator) {

        liveIndicator.className =
            "live-indicator live-indicator--" +
            type;


        if (
            type ===
            "live"
        ) {

            liveIndicator.textContent =
                "LIVE";

        } else if (
            type ===
            "loading"
        ) {

            liveIndicator.textContent =
                "CONNECTING";

        } else if (
            type ===
            "error"
        ) {

            liveIndicator.textContent =
                "ERROR";

        } else {

            liveIndicator.textContent =
                "STANDBY";

        }

    }

}


/* ============================================================
   HTML ESCAPE
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
   TIME
   ============================================================ */

function normaliseTimestamp(
    value
) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {

        return null;

    }


    const numeric =
        Number(
            value
        );


    if (
        Number.isFinite(
            numeric
        )
    ) {

        if (
            Math.abs(
                numeric
            ) <
            100000000000
        ) {

            return numeric * 1000;

        }


        return numeric;

    }


    const parsed =
        Date.parse(
            String(
                value
            )
        );


    if (
        Number.isFinite(
            parsed
        )
    ) {

        return parsed;

    }


    return null;

}


function formatDate(
    value
) {

    const timestamp =
        normaliseTimestamp(
            value
        );


    if (
        timestamp === null
    ) {

        return "Unknown time";

    }


    return new Intl.DateTimeFormat(
        "en-GB",
        {
            timeZone:
                "Europe/London",

            weekday:
                "short",

            day:
                "2-digit",

            month:
                "short",

            year:
                "numeric",

            hour:
                "2-digit",

            minute:
                "2-digit",

            second:
                "2-digit",

            hour12:
                false
        }
    ).format(
        new Date(
            timestamp
        )
    );

}


function formatShortTime(
    value
) {

    const timestamp =
        normaliseTimestamp(
            value
        );


    if (
        timestamp === null
    ) {

        return "Unknown";

    }


    return new Intl.DateTimeFormat(
        "en-GB",
        {
            timeZone:
                "Europe/London",

            hour:
                "2-digit",

            minute:
                "2-digit",

            second:
                "2-digit",

            hour12:
                false
        }
    ).format(
        new Date(
            timestamp
        )
    );

}


/* ============================================================
   EVENT TYPE
   ============================================================ */

function cleanEventType(
    value
) {

    if (!value) {

        return "Ring Alert";

    }


    return String(
        value
    )
        .replace(
            /[:_-]+/g,
            " "
        )
        .replace(
            /\s+/g,
            " "
        )
        .trim()
        .replace(
            /\b\w/g,
            function(letter) {

                return letter.toUpperCase();

            }
        );

}


/* ============================================================
   ALERT HELPERS
   ============================================================ */

function getAlertId(
    alert
) {

    if (!alert) {

        return "";

    }


    return String(
        alert.id ||
        alert.event_id ||
        alert.eventId ||
        ""
    );

}


function getAlertDeviceId(
    alert
) {

    if (!alert) {

        return "";

    }


    const value =
        alert.device_id ||
        alert.deviceId ||
        (
            alert.device &&
            alert.device.id
        ) ||
        (
            alert.device &&
            alert.device.device_id
        ) ||
        (
            alert.data &&
            alert.data.device_id
        ) ||
        "";


    return String(
        value
    );

}


function getAlertDeviceName(
    alert
) {

    if (!alert) {

        return "Ring Camera";

    }


    return (
        alert.device_name ||
        alert.deviceName ||
        (
            alert.device &&
            alert.device.name
        ) ||
        alert.camera_name ||
        alert.cameraName ||
        "Ring Camera"
    );

}


function getAlertType(
    alert
) {

    if (!alert) {

        return "Ring Alert";

    }


    return (
        alert.event_type ||
        alert.eventType ||
        alert.type ||
        "Ring Alert"
    );

}


function getAlertTimestamp(
    alert
) {

    if (!alert) {

        return null;

    }


    return (
        alert.timestamp ||
        alert.occurred_at ||
        alert.occurredAt ||
        alert.created_at ||
        alert.createdAt ||
        null
    );

}


/* ============================================================
   ALERT EXTRACTION
   ============================================================ */

function extractAlerts(
    payload
) {

    console.log(
        "[DEBUG][EXTRACT] extractAlerts() called"
    );

    console.log(
        "[DEBUG][EXTRACT] Payload:",
        payload
    );


    if (!payload) {

        console.warn(
            "[DEBUG][EXTRACT] No payload received."
        );

        return [];

    }


    if (
        Array.isArray(
            payload.alerts
        )
    ) {

        console.log(
            "[DEBUG][EXTRACT] Using payload.alerts:",
            payload.alerts.length
        );

        return payload.alerts;

    }


    if (
        Array.isArray(
            payload.data
        )
    ) {

        console.log(
            "[DEBUG][EXTRACT] Using payload.data:",
            payload.data.length
        );

        return payload.data;

    }


    if (
        payload.data &&
        Array.isArray(
            payload.data.alerts
        )
    ) {

        console.log(
            "[DEBUG][EXTRACT] Using payload.data.alerts:",
            payload.data.alerts.length
        );

        return payload.data.alerts;

    }


    if (
        payload.data &&
        Array.isArray(
            payload.data.data
        )
    ) {

        console.log(
            "[DEBUG][EXTRACT] Using payload.data.data:",
            payload.data.data.length
        );

        return payload.data.data;

    }


    console.warn(
        "[DEBUG][EXTRACT] Could not find alert array in payload."
    );


    return [];

}


/* ============================================================
   CLEAR VIDEO PLAY RETRY
   ============================================================ */

function clearVideoPlayRetry() {

    if (videoPlayTimer) {

        clearTimeout(
            videoPlayTimer
        );


        videoPlayTimer =
            null;

    }

}


/* ============================================================
   SHOW BLACK VIDEO
   ============================================================ */

function showBlackVideo() {

    if (!liveVideo) {

        return;

    }


    clearVideoPlayRetry();

    videoPlayAttempt =
        0;


    log(
        "[ALERT LIVE] VIDEO -> BLACK"
    );


    try {

        liveVideo.pause();

    } catch (error) {

        console.warn(
            "[ALERT LIVE] Video pause warning:",
            error
        );

    }


    if (currentMediaStream) {

        currentMediaStream
            .getTracks()
            .forEach(
                function(track) {

                    try {

                        track.stop();

                    } catch (error) {

                    }

                }
            );


        currentMediaStream =
            null;

    }


    liveVideo.srcObject =
        null;

    if (alertVideoUrl) {
        URL.revokeObjectURL(alertVideoUrl);
        alertVideoUrl = null;
    }

    liveVideo.removeAttribute("src");
    liveVideo.controls = false;

    if (soundButton) {
        soundButton.hidden = true;
        soundButton.textContent = "Enable Sound";
    }


    liveVideo.hidden =
        false;

    liveVideo.autoplay =
        true;

    liveVideo.playsInline =
        true;

    liveVideo.muted =
        true;

    liveVideo.style.display =
        "block";

    liveVideo.style.background =
        "#05070a";


    if (noStreamOverlay) {

        noStreamOverlay.hidden =
            false;

        noStreamOverlay.classList.remove(
            "is-hidden"
        );

        noStreamOverlay.classList.add(
            "is-visible"
        );

        noStreamOverlay.style.display =
            "flex";


        log(
            "[ALERT LIVE] Overlay -> DISPLAY FLEX"
        );

    }


    if (videoLoading) {

        videoLoading.hidden =
            true;

        videoLoading.style.display =
            "none";

    }


    playPromise =
        null;

}


/* ============================================================
   SHOW VIDEO CONNECTING
   ============================================================ */

function showVideoConnecting() {

    if (!liveVideo) {

        return;

    }


    clearVideoPlayRetry();

    videoPlayAttempt =
        0;


    log(
        "[ALERT LIVE] VIDEO -> CONNECTING"
    );


    liveVideo.hidden =
        false;

    liveVideo.autoplay =
        true;

    liveVideo.playsInline =
        true;

    liveVideo.muted =
        true;

    liveVideo.style.display =
        "block";

    liveVideo.style.background =
        "#05070a";


    if (noStreamOverlay) {

        noStreamOverlay.hidden =
            false;

        noStreamOverlay.classList.remove(
            "is-visible"
        );

        noStreamOverlay.classList.add(
            "is-hidden"
        );

        noStreamOverlay.style.display =
            "none";


        log(
            "[ALERT LIVE] Overlay -> DISPLAY NONE"
        );

    }


    if (videoLoading) {

        videoLoading.hidden =
            false;

        videoLoading.style.display =
            "flex";

    }

}


/* ============================================================
   SHOW VIDEO LIVE
   ============================================================ */

function showVideoLive(
    stream
) {

    if (!liveVideo) {

        console.error(
            "[ALERT LIVE] #liveVideo missing."
        );

        return;

    }


    if (!stream) {

        console.error(
            "[ALERT LIVE] No MediaStream received."
        );

        return;

    }


    log(
        "===================================="
    );

    log(
        "[ALERT LIVE] VIDEO STREAM RECEIVED"
    );

    log(
        "[ALERT LIVE] Video tracks:",
        stream.getVideoTracks().length
    );

    log(
        "[ALERT LIVE] Audio tracks:",
        stream.getAudioTracks().length
    );

    log(
        "===================================="
    );


    currentMediaStream =
        stream;


    liveVideo.srcObject =
        stream;

    liveVideo.hidden =
        false;

    liveVideo.autoplay =
        true;

    liveVideo.playsInline =
        true;

    liveVideo.muted =
        true;

    liveVideo.style.display =
        "block";

    liveVideo.style.background =
        "#05070a";


    if (noStreamOverlay) {

        noStreamOverlay.hidden =
            true;

        noStreamOverlay.classList.remove(
            "is-visible"
        );

        noStreamOverlay.classList.add(
            "is-hidden"
        );

        noStreamOverlay.style.display =
            "none";

    }


    if (videoLoading) {

        videoLoading.hidden =
            true;

        videoLoading.style.display =
            "none";

    }


    log(
        "[ALERT LIVE] MediaStream attached."
    );

}


/* ============================================================
   WAIT FOR TRACK READY
   ============================================================ */

function waitForTrackReadyThenPlay(
    track,
    generation
) {

    let settled =
        false;


    const cleanup =
        function() {

            if (track) {

                track.removeEventListener(
                    "unmute",
                    onUnmute
                );

            }


            if (liveVideo) {

                liveVideo.removeEventListener(
                    "loadedmetadata",
                    onLoadedMetadata
                );

                liveVideo.removeEventListener(
                    "playing",
                    onPlaying
                );

            }

        };


    const attemptPlay =
        function(reason) {

            if (
                settled ||
                generation !==
                    liveGeneration
            ) {

                return;

            }


            settled =
                true;


            cleanup();


            console.log(
                `[ALERT LIVE] Media ready (${reason}) — attempting play().`
            );


            logTrackDiagnostics(
                "track state at play attempt",
                track
            );


            logVideoDiagnostics(
                "video state at play attempt"
            );


            safePlayVideo(
                generation,
                1
            );

        };


    const onUnmute =
        function() {

            attemptPlay(
                "track unmuted"
            );

        };


    const onLoadedMetadata =
        function() {

            attemptPlay(
                "loadedmetadata"
            );

        };


    const onPlaying =
        function() {

            attemptPlay(
                "playing event"
            );

        };


    track.addEventListener(
        "unmute",
        onUnmute
    );


    if (liveVideo) {

        liveVideo.addEventListener(
            "loadedmetadata",
            onLoadedMetadata
        );

        liveVideo.addEventListener(
            "playing",
            onPlaying
        );

    }


    if (
        track.muted ===
            false ||
        (
            liveVideo &&
            liveVideo.readyState >= 1
        )
    ) {

        attemptPlay(
            "already ready"
        );


        return;

    }


    setTimeout(
        function() {

            if (
                settled ||
                generation !==
                    liveGeneration
            ) {

                return;

            }


            console.warn(
                "[ALERT LIVE] Track never unmuted / video never got metadata after 5s."
            );


            console.warn(
                "[ALERT LIVE] Falling back to playback attempt and RTP diagnostics."
            );


            probeInboundVideoStats(
                peerConnection
            );


            logSelectedCandidatePair(
                peerConnection,
                "5-second fallback"
            );


            attemptPlay(
                "timeout fallback"
            );

        },
        5000
    );

}


/* ============================================================
   SAFE VIDEO PLAY
   ============================================================ */

async function safePlayVideo(
    generation,
    attempt = 1
) {

    if (!liveVideo) {

        return;

    }


    if (
        generation !==
        liveGeneration
    ) {

        return;

    }


    if (
        !liveVideo.srcObject
    ) {

        console.warn(
            "[ALERT LIVE] No MediaStream attached."
        );

        return;

    }


    const maxAttempts =
        VIDEO_PLAY_MAX_ATTEMPTS;


    console.log(
        `[ALERT LIVE] Attempting video.play() — attempt ${attempt} / ${maxAttempts}`
    );


    logVideoDiagnostics(
        `before play() attempt ${attempt}`
    );


    if (playPromise) {

        console.log(
            "[ALERT LIVE] play() already running."
        );

        return;

    }


    liveVideo.muted =
        true;

    liveVideo.autoplay =
        true;

    liveVideo.playsInline =
        true;

    liveVideo.hidden =
        false;

    liveVideo.style.display =
        "block";

    liveVideo.style.visibility =
        "visible";


    const stream =
        liveVideo.srcObject;


    const videoTracks =
        stream.getVideoTracks();


    const audioTracks =
        stream.getAudioTracks();


    console.log(
        "[ALERT LIVE] Video tracks:",
        videoTracks.length
    );


    console.log(
        "[ALERT LIVE] Audio tracks:",
        audioTracks.length
    );


    if (
        videoTracks.length ===
        0
    ) {

        console.warn(
            "[ALERT LIVE] No video track available yet."
        );

        return;

    }


    const videoTrack =
        videoTracks[0];


    logTrackDiagnostics(
        "video track before play",
        videoTrack
    );


    try {

        playPromise =
            liveVideo.play();


        await playPromise;


        playPromise =
            null;


        if (
            generation !==
            liveGeneration
        ) {

            return;

        }


        console.log(
            "[ALERT LIVE] ===================================="
        );

        console.log(
            "[ALERT LIVE] VIDEO PLAYING"
        );


        logVideoDiagnostics(
            "after play() success"
        );


        console.log(
            "[ALERT LIVE] ===================================="
        );


        if (
            liveVideo.paused
        ) {

            console.warn(
                "[ALERT LIVE] play() resolved but video is still paused."
            );


            if (
                attempt <
                maxAttempts
            ) {

                videoPlayTimer =
                    setTimeout(
                        function() {

                            videoPlayTimer =
                                null;


                            if (
                                generation !==
                                liveGeneration
                            ) {

                                return;

                            }


                            safePlayVideo(
                                generation,
                                attempt + 1
                            );

                        },
                        1500
                    );

                return;

            }

        }


        liveStarting =
            false;

        liveActive =
            true;

        liveVideo.muted = false;

        if (soundButton) {
            soundButton.hidden = false;
            soundButton.textContent = "Mute Sound";
        }

        if (liveAutoStopTimer) {
            clearTimeout(liveAutoStopTimer);
        }

        liveAutoStopTimer = setTimeout(
            function() {
                if (liveActive) {
                    log("[ALERT LIVE] 60-second limit reached; stopping live.");
                    stopLive(true);
                }
            },
            60 * 1000
        );


        if (noStreamOverlay) {

            noStreamOverlay.hidden =
                true;

            noStreamOverlay.style.display =
                "none";

        }


        if (videoLoading) {

            videoLoading.hidden =
                true;

            videoLoading.style.display =
                "none";

        }


        liveVideo.hidden =
            false;

        liveVideo.style.display =
            "block";

        liveVideo.style.visibility =
            "visible";


        setStatus(
            "LIVE — " +
            currentDeviceName,
            "live"
        );


        if (liveIndicator) {

            liveIndicator.className =
                "live-indicator live-indicator--live";

            liveIndicator.textContent =
                "LIVE";

        }


    } catch (error) {

        playPromise =
            null;


        console.warn(
            `[ALERT LIVE] play() attempt ${attempt} failed:`,
            error
        );


        if (
            generation !==
            liveGeneration
        ) {

            return;

        }


        if (
            attempt >=
            maxAttempts
        ) {

            console.error(
                "[ALERT LIVE] Exhausted play() retries."
            );


            console.error(
                "[ALERT LIVE] WebRTC connection will NOT be restarted automatically."
            );


            await logSelectedCandidatePair(
                peerConnection,
                "Final playback attempt"
            );


            await probeInboundVideoStats(
                peerConnection
            );


            if (
                videoTrack.muted
            ) {

                console.warn(
                    "[ALERT LIVE] Video track is still muted after playback attempts."
                );

            }


            return;

        }


        videoPlayTimer =
            setTimeout(
                function() {

                    videoPlayTimer =
                        null;


                    if (
                        generation !==
                        liveGeneration
                    ) {

                        return;

                    }


                    if (
                        !liveVideo ||
                        !liveVideo.srcObject
                    ) {

                        return;

                    }


                    safePlayVideo(
                        generation,
                        attempt + 1
                    );

                },
                1500
            );

    }

}


/* ============================================================
   ALERT RENDER
   ============================================================ */

function renderAlerts() {

    const container =
        alertsContainer ||
        alertsList;


    if (!container) {

        return;

    }


    if (
        !alerts.length
    ) {

        container.innerHTML =
            `
            <div class="alerts-empty">
                No alerts yet.
            </div>
            `;


        if (emptyState) {

            emptyState.hidden =
                false;

        }


        return;

    }


    if (emptyState) {

        emptyState.hidden =
            true;

    }


    container.innerHTML =
        alerts
            .map(
                function(alert) {

                    return createAlertCard(
                        alert
                    );

                }
            )
            .join("");


    /*
     * IMPORTANT:
     *
     * This is the existing working path.
     *
     * Clicking a row calls:
     *
     *     openAlert(selected)
     *
     * We leave that unchanged.
     */

    container
        .querySelectorAll(
            "[data-alert-id]"
        )
        .forEach(
            function(card) {

                card.addEventListener(
                    "click",
                    function() {

                        console.log(
                            "[DEBUG][ROW CLICK] Alert row clicked."
                        );

                        const id =
                            card.dataset.alertId;


                        console.log(
                            "[DEBUG][ROW CLICK] Clicked alert ID:",
                            id
                        );


                        const selected =
                            alerts.find(
                                function(item) {

                                    return (
                                        getAlertId(
                                            item
                                        ) ===
                                        id
                                    );

                                }
                            );


                        console.log(
                            "[DEBUG][ROW CLICK] Selected alert object:",
                            selected
                        );


                        if (
                            selected
                        ) {

                            console.log(
                                "[DEBUG][ROW CLICK] Calling openAlert(selected)."
                            );

                            /*
                             * EXISTING WORKING PATH.
                             *
                             * DO NOT CHANGE.
                             */

                            openAlert(
                                selected
                            );

                        } else {

                            console.warn(
                                "[DEBUG][ROW CLICK] Could not find selected alert."
                            );

                        }

                    }
                );

            }
        );

}


/* ============================================================
   ALERT CARD
   ============================================================ */

function createAlertCard(
    alert
) {

    const id =
        getAlertId(
            alert
        );


    const type =
        getAlertType(
            alert
        );


    const deviceName =
        getAlertDeviceName(
            alert
        );


    const timestamp =
        getAlertTimestamp(
            alert
        );


    const message =
        alert.message ||
        cleanEventType(
            type
        );


    return `
        <article
            class="alert-card"
            data-alert-id="${escapeHtml(id)}"
        >

            <div class="alert-card-icon">
                !
            </div>

            <div class="alert-card-body">

                <div class="alert-card-top">

                    <strong>
                        ${escapeHtml(
                            cleanEventType(type)
                        )}
                    </strong>

                    <span>
                        ${escapeHtml(
                            formatShortTime(
                                timestamp
                            )
                        )}
                    </span>

                </div>

                <div class="alert-card-device">
                    ${escapeHtml(
                        deviceName
                    )}
                </div>

                <div class="alert-card-message">
                    ${escapeHtml(
                        message
                    )}
                </div>

                <div class="alert-card-date">
                    ${escapeHtml(
                        formatDate(
                            timestamp
                        )
                    )}
                </div>

            </div>

            <div class="alert-card-arrow">
                →
            </div>

        </article>
    `;

}


/* ============================================================
   ACTIVE ALERT
   ============================================================ */

function renderActiveAlert(
    alert
) {

    if (currentAlert) {

        currentAlert.hidden =
            false;

    }


    if (alertTitle) {

        alertTitle.textContent =
            cleanEventType(
                getAlertType(
                    alert
                )
            );

    }


    if (alertMessage) {

        alertMessage.textContent =
            alert.message ||
            "Ring alert detected.";

    }


    if (alertTime) {

        alertTime.textContent =
            formatDate(
                getAlertTimestamp(
                    alert
                )
            );

    }


    if (alertDevice) {

        alertDevice.textContent =
            getAlertDeviceName(
                alert
            );

    }


    if (alertType) {

        alertType.textContent =
            cleanEventType(
                getAlertType(
                    alert
                )
            );

    }


    if (currentDevice) {

        currentDevice.textContent =
            getAlertDeviceName(
                alert
            );

    }

}


async function playAlertVideo(alert) {
    if (!alert || !getAlertId(alert)) {
        return;
    }

    if (!liveVideo) {
        return;
    }

    const endpoint =
        "/ring/alerts/" +
        encodeURIComponent(getAlertId(alert)) +
        "/video/";

    showBlackVideo();
    liveVideo.controls = true;
    liveVideo.muted = false;
    showVideoConnecting();
    setStatus("Loading alert recording...", "loading");

    try {
        const response = await fetch(endpoint, {
            method: "GET",
            headers: {"Accept": "video/mp4,video/*,*/*"},
            credentials: "same-origin",
            cache: "no-store"
        });

        if (!response.ok) {
            let message = "Alert recording unavailable.";

            try {
                const data = await response.json();
                message = data.message || data.details || data.error || message;
            } catch (error) {
                // Keep the generic message when the response is not JSON.
            }

            throw new Error(message);
        }

        const blob = await response.blob();

        if (!blob.size || (blob.type && blob.type.includes("application/json"))) {
            throw new Error("Ring returned no playable alert recording.");
        }

        alertVideoUrl = URL.createObjectURL(blob);
        liveVideo.srcObject = null;
        liveVideo.src = alertVideoUrl;
        liveVideo.hidden = false;
        liveVideo.controls = true;
        liveVideo.muted = false;

        if (noStreamOverlay) {
            noStreamOverlay.hidden = true;
            noStreamOverlay.style.display = "none";
        }

        if (videoLoading) {
            videoLoading.hidden = true;
            videoLoading.style.display = "none";
        }

        setStatus("Playing alert recording", "ready");

        try {
            await liveVideo.play();
        } catch (error) {
            log("Alert recording loaded; press play to start.");
        }
    } catch (error) {
        showBlackVideo();
        setStatus(error.message || "Unable to load alert recording.", "error");
    }
}


/* ============================================================
   LOAD ALERTS
   ============================================================ */

async function loadAlerts(
    options = {}
) {

    console.log(
        "===================================="
    );

    console.log(
        "[DEBUG][LOAD] loadAlerts() ENTERED"
    );

    console.log(
        "[DEBUG][LOAD] Options:",
        options
    );

    console.log(
        "[DEBUG][LOAD] pollingPaused:",
        pollingPaused
    );

    console.log(
        "[DEBUG][LOAD] liveStarting:",
        liveStarting
    );

    console.log(
        "[DEBUG][LOAD] liveActive:",
        liveActive
    );

    console.log(
        "[DEBUG][LOAD] pollInProgress:",
        pollInProgress
    );

    console.log(
        "===================================="
    );


    if (
        pollingPaused &&
        !options.force
    ) {

        console.log(
            "[DEBUG][LOAD] EXIT — polling is paused."
        );

        return;

    }


    if (
        liveStarting ||
        liveActive
    ) {

        console.log(
            "[DEBUG][LOAD] EXIT — live is active/starting."
        );

        return;

    }


    if (
        pollInProgress
    ) {

        console.log(
            "[DEBUG][LOAD] EXIT — poll already in progress."
        );

        return;

    }


    pollInProgress =
        true;


    try {

        log(
            "GET /ring/alerts/api/"
        );


        console.log(
            "[DEBUG][LOAD] About to fetch alert API."
        );


        const response =
            await fetch(
                "/ring/alerts/api/",
                {
                    method:
                        "GET",

                    headers: {
                        "Accept":
                            "application/json"
                    },

                    credentials:
                        "same-origin",

                    cache:
                        "no-store"
                }
            );


        console.log(
            "[DEBUG][LOAD] Alert API response received."
        );

        console.log(
            "[DEBUG][LOAD] HTTP status:",
            response.status
        );

        console.log(
            "[DEBUG][LOAD] HTTP ok:",
            response.ok
        );


        const text =
            await response.text();


        console.log(
            "[DEBUG][LOAD] Raw alert API response text:",
            text
        );


        let payload;


        try {

            payload =
                JSON.parse(
                    text
                );

        } catch (error) {

            console.error(
                "[DEBUG][LOAD] Failed to parse alert API JSON:",
                error
            );

            throw new Error(
                "Alert API returned invalid JSON."
            );

        }


        console.log(
            "[DEBUG][LOAD] Parsed alert API payload:",
            payload
        );


        if (
            !response.ok
        ) {

            console.error(
                "[DEBUG][LOAD] Alert API returned HTTP error:",
                response.status
            );


            throw new Error(
                payload.error ||
                payload.message ||
                "Alert API request failed."
            );

        }


        const newAlerts =
            extractAlerts(
                payload
            );


        log(
            "Alerts received:",
            newAlerts.length
        );


        /*
         * DEBUG:
         *
         * This lets us confirm exactly what the API gave us.
         *
         * It does NOT change the data.
         */

        console.log(
            "[ALERTS][API] Raw alert objects:",
            newAlerts
        );


        console.log(
            "[DEBUG][LOAD] Previous alerts:",
            alerts
        );


        console.log(
            "[DEBUG][LOAD] Previous alert IDs:",
            alerts.map(
                function(alert) {
                    return getAlertId(alert);
                }
            )
        );


        console.log(
            "[DEBUG][LOAD] New API alert IDs:",
            newAlerts.map(
                function(alert) {
                    return getAlertId(alert);
                }
            )
        );


        const previousAlerts =
            alerts;


        alerts =
            newAlerts;


        console.log(
            "[DEBUG][LOAD] alerts[] replaced with new API alerts."
        );


        renderAlerts();


        hideError();


        if (
            pageInitialised
        ) {

            console.log(
                "[DEBUG][LOAD] Page initialised — calling detectNewAlert()."
            );


            await detectNewAlert(
                previousAlerts,
                newAlerts
            );

        } else {

            console.log(
                "[DEBUG][LOAD] Page not previously initialised — skipping new-alert detection."
            );

        }


        pageInitialised =
            true;


        console.log(
            "[DEBUG][LOAD] loadAlerts() completed successfully."
        );


    } catch (error) {

        console.error(
            "[ALERTS] Alert API error:",
            error
        );


        console.error(
            "[DEBUG][LOAD] loadAlerts() FAILED:",
            error
        );


        showError(
            error.message ||
            "Unable to load alerts."
        );


    } finally {

        pollInProgress =
            false;


        console.log(
            "[DEBUG][LOAD] pollInProgress reset to false."
        );

    }

}


/* ============================================================
   DETECT NEW ALERT
   ============================================================ */

async function detectNewAlert(
    previousAlerts,
    newAlerts
) {

    console.log(
        "===================================="
    );

    console.log(
        "[DEBUG][DETECT] detectNewAlert() ENTERED"
    );

    console.log(
        "[DEBUG][DETECT] Previous alerts:",
        previousAlerts
    );

    console.log(
        "[DEBUG][DETECT] New alerts:",
        newAlerts
    );

    console.log(
        "[DEBUG][DETECT] Previous IDs:",
        (previousAlerts || []).map(
            function(alert) {
                return getAlertId(alert);
            }
        )
    );

    console.log(
        "[DEBUG][DETECT] New IDs:",
        (newAlerts || []).map(
            function(alert) {
                return getAlertId(alert);
            }
        )
    );

    console.log(
        "[DEBUG][DETECT] lastAlertId:",
        lastAlertId
    );

    console.log(
        "===================================="
    );


    if (
        !newAlerts ||
        !newAlerts.length
    ) {

        console.log(
            "[DEBUG][DETECT] EXIT — no new alerts."
        );

        return;

    }


    /*
     * --------------------------------------------------------
     * IMPORTANT CHANGE
     * --------------------------------------------------------
     *
     * Instead of blindly assuming the first API alert is the
     * new alert, compare the IDs.
     *
     * This makes the automatic API path more reliable if the
     * backend changes the order of the returned alerts.
     */

    const previousIds =
        new Set(
            (previousAlerts || [])
                .map(
                    function(alert) {

                        return getAlertId(
                            alert
                        );

                    }
                )
                .filter(
                    function(id) {

                        return Boolean(id);

                    }
                )
        );


    console.log(
        "[DEBUG][DETECT] previousIds Set:",
        Array.from(previousIds)
    );


    /*
     * Find the first alert that wasn't present in the previous
     * API response.
     */

    let newest =
        null;


    for (
        const alert of newAlerts
    ) {

        const id =
            getAlertId(
                alert
            );


        console.log(
            "[DEBUG][DETECT] Checking alert:",
            {
                alert: alert,
                id: id,
                wasPreviouslySeen:
                    previousIds.has(id)
            }
        );


        if (
            id &&
            !previousIds.has(id)
        ) {

            newest =
                alert;

            console.log(
                "[DEBUG][DETECT] NEW ALERT FOUND:",
                newest
            );

            break;

        }

    }


    /*
     * If no genuinely new ID was found, don't start live.
     */

    if (!newest) {

        console.log(
            "[DEBUG][DETECT] EXIT — no genuinely new alert ID found."
        );

        return;

    }


    const newestId =
        getAlertId(
            newest
        );


    console.log(
        "[DEBUG][DETECT] Newest alert ID:",
        newestId
    );


    if (!newestId) {

        console.warn(
            "[ALERTS] New alert has no ID:",
            newest
        );

        return;

    }


    /*
     * Additional duplicate protection.
     */

    if (
        newestId ===
        lastAlertId
    ) {

        log(
            "[ALERTS] Alert already handled:",
            newestId
        );


        console.log(
            "[DEBUG][DETECT] EXIT — duplicate lastAlertId."
        );


        return;

    }


    log(
        "===================================="
    );

    log(
        "[ALERTS] NEW ALERT DETECTED FROM API"
    );

    log(
        "[ALERTS] Alert ID:",
        newestId
    );

    log(
        "[ALERTS] Device ID:",
        getAlertDeviceId(
            newest
        )
    );

    log(
        "[ALERTS] Device:",
        getAlertDeviceName(
            newest
        )
    );

    log(
        "[ALERTS] Type:",
        getAlertType(
            newest
        )
    );

    log(
        "[ALERTS] Timestamp:",
        getAlertTimestamp(
            newest
        )
    );

    log(
        "[ALERTS] Genuine new alert will replace playback with live."
    );

    log(
        "===================================="
    );


    console.log(
        "[DEBUG][DETECT] Full newest alert before handleNewAlert():",
        newest
    );


    lastAlertId =
        newestId;


    console.log(
        "[DEBUG][DETECT] lastAlertId updated:",
        lastAlertId
    );


    console.log(
        "[DEBUG][DETECT] Calling handleNewAlert(newest)."
    );


    await handleNewAlert(
        newest
    );


    console.log(
        "[DEBUG][DETECT] handleNewAlert() completed."
    );

}


/* ============================================================
   HANDLE NEW ALERT
   ============================================================ */

async function handleNewAlert(
    alert
) {

    console.log(
        "===================================="
    );

    console.log(
        "[DEBUG][HANDLE] handleNewAlert() ENTERED"
    );

    console.log(
        "[DEBUG][HANDLE] Alert:",
        alert
    );

    console.log(
        "[DEBUG][HANDLE] Alert ID:",
        getAlertId(alert)
    );

    console.log(
        "[DEBUG][HANDLE] Device ID:",
        getAlertDeviceId(alert)
    );

    console.log(
        "[DEBUG][HANDLE] Device Name:",
        getAlertDeviceName(alert)
    );

    console.log(
        "[DEBUG][HANDLE] Type:",
        getAlertType(alert)
    );

    console.log(
        "===================================="
    );


    if (!alert) {

        console.warn(
            "[DEBUG][HANDLE] EXIT — alert is null/undefined."
        );

        return;

    }


    if (
        liveStarting ||
        liveActive
    ) {

        log(
            "[ALERTS] Live already active; ignoring duplicate API alert."
        );


        console.log(
            "[DEBUG][HANDLE] EXIT — liveStarting/liveActive already true."
        );


        return;

    }


    /*
     * Store the exact API alert object.
     */

    activeAlert =
        alert;


    console.log(
        "[DEBUG][HANDLE] activeAlert set to API alert."
    );


    /*
     * Show the exact same alert information that would be
     * displayed when the user clicks the row.
     */

    renderActiveAlert(
        alert
    );


    console.log(
        "[DEBUG][HANDLE] renderActiveAlert() completed."
    );


    const deviceId =
        getAlertDeviceId(
            alert
        );


    console.log(
        "[DEBUG][HANDLE] Extracted deviceId:",
        deviceId
    );


    if (!deviceId) {

        console.error(
            "[ALERTS] API alert has no device ID:",
            alert
        );


        console.error(
            "[DEBUG][HANDLE] Cannot continue because deviceId is empty."
        );


        setStatus(
            "Alert received — no device ID",
            "error"
        );


        return;

    }


    const deviceName =
        getAlertDeviceName(
            alert
        );


    console.log(
        "[DEBUG][HANDLE] Extracted deviceName:",
        deviceName
    );


    /*
     * --------------------------------------------------------
     * IMPORTANT FIX
     * --------------------------------------------------------
     *
     * A newly detected alert is different from a past alert click:
     * stop any recording playback and open the live camera.
     */

    log(
        "[ALERTS] New API alert -> live camera"
    );


    log(
        "[ALERTS] API device ID:",
        deviceId
    );


    log(
        "[ALERTS] API device name:",
        deviceName
    );


    pausePolling();


    console.log(
        "[DEBUG][HANDLE] Polling paused."
    );


    console.log(
        "[DEBUG][HANDLE] ABOUT TO CALL startLive(alert)."
    );

    console.log(
        "[DEBUG][HANDLE] Alert object being passed:",
        alert
    );

    console.log(
        "[DEBUG][HANDLE] Device ID before openAlert:",
        getAlertDeviceId(alert)
    );

    console.log(
        "[DEBUG][HANDLE] Device Name before openAlert:",
        getAlertDeviceName(alert)
    );


    /*
     * A new alert supersedes a past-alert recording currently on screen.
     */

    showBlackVideo();

    await startLive(
        deviceId,
        deviceName,
        alert
    );


    console.log(
        "[DEBUG][HANDLE] startLive(alert) completed."
    );

}


/* ============================================================
   PAUSE POLLING
   ============================================================ */

function pausePolling() {

    pollingPaused =
        true;


    if (pollTimer) {

        clearTimeout(
            pollTimer
        );


        pollTimer =
            null;

    }


    log(
        "[ALERTS] Polling PAUSED"
    );

}


/* ============================================================
   RESUME POLLING
   ============================================================ */

function resumePolling() {

    if (
        liveStarting ||
        liveActive
    ) {

        return;

    }


    pollingPaused =
        false;


    log(
        "[ALERTS] Polling RESUMED"
    );


    scheduleNextPoll(
        500
    );

}


/* ============================================================
   POLL SCHEDULER
   ============================================================ */

function scheduleNextPoll(
    delay = ALERT_POLL_INTERVAL
) {

    if (
        pollingPaused ||
        liveStarting ||
        liveActive
    ) {

        return;

    }


    if (pollTimer) {

        clearTimeout(
            pollTimer
        );

    }


    pollTimer =
        setTimeout(
            async function() {

                if (
                    pollingPaused ||
                    liveStarting ||
                    liveActive
                ) {

                    return;

                }


                await loadAlerts();


                if (
                    !pollingPaused &&
                    !liveStarting &&
                    !liveActive
                ) {

                    scheduleNextPoll();

                }

            },
            delay
        );

}


/* ============================================================
   START LIVE
   ============================================================ */

async function startLive(
    deviceId,
    deviceName = "Ring Camera",
    alert = null
) {

    console.log(
        "===================================="
    );

    console.log(
        "[DEBUG][START LIVE] startLive() ENTERED"
    );

    console.log(
        "[DEBUG][START LIVE] deviceId:",
        deviceId
    );

    console.log(
        "[DEBUG][START LIVE] deviceName:",
        deviceName
    );

    console.log(
        "[DEBUG][START LIVE] alert:",
        alert
    );

    console.log(
        "[DEBUG][START LIVE] alert ID:",
        alert
            ? getAlertId(alert)
            : null
    );

    console.log(
        "[DEBUG][START LIVE] liveStarting:",
        liveStarting
    );

    console.log(
        "[DEBUG][START LIVE] liveActive:",
        liveActive
    );

    console.log(
        "[DEBUG][START LIVE] currentDeviceId:",
        currentDeviceId
    );

    console.log(
        "[DEBUG][START LIVE] currentDeviceName:",
        currentDeviceName
    );

    console.log(
        "===================================="
    );


    deviceId =
        String(
            deviceId
        );


    if (
        liveStarting
    ) {

        log(
            "[ALERT LIVE] Start already running."
        );

        console.log(
            "[DEBUG][START LIVE] EXIT — liveStarting already true."
        );

        return;

    }


    if (
        liveActive &&
        currentDeviceId ===
        deviceId
    ) {

        log(
            "[ALERT LIVE] Device already live."
        );

        console.log(
            "[DEBUG][START LIVE] EXIT — requested device already active."
        );

        return;

    }


    if (
        peerConnection ||
        currentDeviceId
    ) {

        log(
            "[ALERT LIVE] Stopping previous connection."
        );


        await stopLive(
            false
        );

    }


    const generation =
        ++liveGeneration;


    liveStarting =
        true;

    liveActive =
        false;


    currentDeviceId =
        deviceId;


    currentDeviceName =
        deviceName ||
        "Ring Camera";


    activeAlert =
        alert ||
        activeAlert;


    clearVideoPlayRetry();


    videoPlayAttempt =
        0;


    log(
        "===================================="
    );

    log(
        "[ALERT LIVE] STARTING LIVE"
    );

    log(
        "[ALERT LIVE] Device:",
        currentDeviceName
    );

    log(
        "[ALERT LIVE] Device ID:",
        currentDeviceId
    );

    log(
        "[ALERT LIVE] Generation:",
        generation
    );

    log(
        "===================================="
    );


    console.log(
        "[DEBUG][START LIVE] WebRTC start state established."
    );

    console.log(
        "[DEBUG][START LIVE] currentDeviceId:",
        currentDeviceId
    );

    console.log(
        "[DEBUG][START LIVE] currentDeviceName:",
        currentDeviceName
    );

    console.log(
        "[DEBUG][START LIVE] activeAlert:",
        activeAlert
    );


    pausePolling();


    showVideoConnecting();


    setStatus(
        "Starting " +
        currentDeviceName +
        "...",
        "loading"
    );


    if (currentDevice) {

        currentDevice.textContent =
            currentDeviceName;

    }


    liveAbortController =
        new AbortController();


    try {

        const connection =
            new RTCPeerConnection(
                {
                    iceServers:
                        ICE_SERVERS
                }
            );


        peerConnection =
            connection;


        console.log(
            "[DEBUG][START LIVE] RTCPeerConnection created."
        );

        console.log(
            "[DEBUG][START LIVE] Generation:",
            generation
        );


        console.log(
            "[ALERT LIVE] RTCPeerConnection created."
        );


        console.log(
            "[ALERT LIVE] ICE servers:",
            ICE_SERVERS
        );


        /*
         * ====================================================
         * ONTRACK
         * ====================================================
         */

        connection.ontrack =
            function(event) {

                if (
                    generation !==
                        liveGeneration ||
                    peerConnection !==
                        connection
                ) {

                    console.warn(
                        "[ALERT LIVE] Ignoring stale track."
                    );

                    return;

                }


                const track =
                    event.track;


                if (!track) {

                    return;

                }


                console.log(
                    "[ALERT LIVE] ===================================="
                );

                console.log(
                    "[ALERT LIVE] REMOTE TRACK RECEIVED"
                );

                console.log(
                    "[ALERT LIVE] Kind:",
                    track.kind
                );

                console.log(
                    "[ALERT LIVE] ID:",
                    track.id
                );

                console.log(
                    "[ALERT LIVE] Ready state:",
                    track.readyState
                );

                console.log(
                    "[ALERT LIVE] Enabled:",
                    track.enabled
                );

                console.log(
                    "[ALERT LIVE] Muted:",
                    track.muted
                );

                console.log(
                    "[ALERT LIVE] Streams:",
                    event.streams
                );

                console.log(
                    "[ALERT LIVE] ===================================="
                );


                logTrackDiagnostics(
                    "REMOTE TRACK RECEIVED",
                    track
                );


                let targetStream;


                if (
                    event.streams &&
                    event.streams.length > 0
                ) {

                    targetStream =
                        event.streams[0];


                    console.log(
                        "[ALERT LIVE] Using MediaStream supplied by WebRTC event."
                    );

                } else {

                    if (
                        !currentMediaStream
                    ) {

                        currentMediaStream =
                            new MediaStream();

                    }


                    const alreadyAdded =
                        currentMediaStream
                            .getTracks()
                            .some(
                                function(existingTrack) {

                                    return (
                                        existingTrack.id ===
                                        track.id
                                    );

                                }
                            );


                    if (
                        !alreadyAdded
                    ) {

                        currentMediaStream.addTrack(
                            track
                        );

                    }


                    targetStream =
                        currentMediaStream;


                    console.log(
                        "[ALERT LIVE] Created fallback MediaStream."
                    );

                }


                currentMediaStream =
                    targetStream;


                if (
                    liveVideo &&
                    liveVideo.srcObject !==
                        currentMediaStream
                ) {

                    liveVideo.srcObject =
                        currentMediaStream;


                    liveVideo.autoplay =
                        true;


                    liveVideo.playsInline =
                        true;


                    liveVideo.muted =
                        true;


                    liveVideo.hidden =
                        false;


                    liveVideo.style.display =
                        "block";


                    liveVideo.style.visibility =
                        "visible";


                    console.log(
                        "[ALERT LIVE] MediaStream attached to #liveVideo."
                    );


                    logVideoDiagnostics(
                        "after srcObject assigned"
                    );

                }


                if (
                    track.kind ===
                    "video"
                ) {

                    console.log(
                        "[ALERT LIVE] VIDEO TRACK RECEIVED."
                    );


                    if (liveVideo) {

                        liveVideo.hidden =
                            false;

                        liveVideo.style.display =
                            "block";

                        liveVideo.style.visibility =
                            "visible";

                    }


                    if (videoLoading) {

                        videoLoading.hidden =
                            false;

                        videoLoading.style.display =
                            "flex";

                    }


                    setStatus(
                        "Video track received — waiting for video...",
                        "loading"
                    );


                    waitForTrackReadyThenPlay(
                        track,
                        generation
                    );

                }


                if (
                    track.kind ===
                    "audio"
                ) {

                    console.log(
                        "[ALERT LIVE] AUDIO TRACK RECEIVED."
                    );

                }

            };


        /*
         * ====================================================
         * ICE CANDIDATES
         * ====================================================
         */

        connection.onicecandidate =
            function(event) {

                if (
                    generation !==
                    liveGeneration
                ) {

                    return;

                }


                logIceCandidate(
                    event.candidate
                );

            };


        /*
         * ====================================================
         * ICE CONNECTION STATE
         * ====================================================
         */

        connection.oniceconnectionstatechange =
            function() {

                if (
                    generation !==
                    liveGeneration
                ) {

                    return;

                }


                const state =
                    connection.iceConnectionState;


                log(
                    "[ALERT LIVE] ICE:",
                    state
                );


                if (
                    state ===
                        "connected" ||
                    state ===
                        "completed"
                ) {

                    setStatus(
                        "Connected: " +
                        currentDeviceName +
                        " — waiting for video...",
                        "loading"
                    );


                    setTimeout(
                        function() {

                            if (
                                generation !==
                                liveGeneration
                            ) {

                                return;

                            }


                            logSelectedCandidatePair(
                                connection,
                                "ICE connected"
                            );

                        },
                        500
                    );

                }


                if (
                    state ===
                    "checking"
                ) {

                    setStatus(
                        "Checking camera connection...",
                        "loading"
                    );

                }


                if (
                    state ===
                    "disconnected"
                ) {

                    console.warn(
                        "[ALERT LIVE] ICE disconnected."
                    );


                    logSelectedCandidatePair(
                        connection,
                        "ICE disconnected"
                    );


                    probeInboundVideoStats(
                        connection
                    );

                }


                if (
                    state ===
                    "failed"
                ) {

                    console.error(
                        "[ALERT LIVE] ICE connection failed."
                    );


                    logSelectedCandidatePair(
                        connection,
                        "ICE failed"
                    );


                    probeInboundVideoStats(
                        connection
                    );


                    setStatus(
                        "Live connection failed.",
                        "error"
                    );


                    setTimeout(
                        function() {

                            if (
                                generation ===
                                liveGeneration
                            ) {

                                stopLive(
                                    true
                                );

                            }

                        },
                        100
                    );

                }

            };


        /*
         * ====================================================
         * CONNECTION STATE
         * ====================================================
         */

        connection.onconnectionstatechange =
            function() {

                if (
                    generation !==
                    liveGeneration
                ) {

                    return;

                }


                const state =
                    connection.connectionState;


                log(
                    "[ALERT LIVE] Connection:",
                    state
                );


                if (
                    state ===
                    "connected"
                ) {

                    liveStarting =
                        true;

                    liveActive =
                        false;


                    setStatus(
                        "Connected: " +
                        currentDeviceName +
                        " — waiting for video...",
                        "loading"
                    );


                    logSelectedCandidatePair(
                        connection,
                        "WebRTC connected"
                    );

                }


                if (
                    state ===
                    "disconnected"
                ) {

                    console.warn(
                        "[ALERT LIVE] WebRTC connection disconnected."
                    );


                    logSelectedCandidatePair(
                        connection,
                        "WebRTC disconnected"
                    );


                    probeInboundVideoStats(
                        connection
                    );

                }


                if (
                    state ===
                    "failed"
                ) {

                    console.error(
                        "[ALERT LIVE] WebRTC connection failed."
                    );


                    logSelectedCandidatePair(
                        connection,
                        "WebRTC failed"
                    );


                    probeInboundVideoStats(
                        connection
                    );


                    setStatus(
                        "Live connection failed.",
                        "error"
                    );


                    setTimeout(
                        function() {

                            if (
                                generation ===
                                liveGeneration
                            ) {

                                stopLive(
                                    true
                                );

                            }

                        },
                        100
                    );

                }

            };


        /*
         * ====================================================
         * ICE GATHERING
         * ====================================================
         */

        connection.onicegatheringstatechange =
            function() {

                if (
                    generation !==
                    liveGeneration
                ) {

                    return;

                }


                log(
                    "[ALERT LIVE] ICE gathering:",
                    connection.iceGatheringState
                );

            };


        /*
         * ====================================================
         * TRANSCEIVERS
         * ====================================================
         */

        connection.addTransceiver(
            "video",
            {
                direction:
                    "recvonly"
            }
        );


        connection.addTransceiver(
            "audio",
            {
                direction:
                    "recvonly"
            }
        );


        log(
            "[ALERT LIVE] Added recvonly video/audio."
        );


        /*
         * ====================================================
         * CREATE OFFER
         * ====================================================
         */

        console.log(
            "[DEBUG][START LIVE] About to create WebRTC offer."
        );


        const offer =
            await connection.createOffer();


        console.log(
            "[DEBUG][START LIVE] WebRTC offer created."
        );

        console.log(
            "[DEBUG][START LIVE] Offer SDP length:",
            offer &&
            offer.sdp
                ? offer.sdp.length
                : 0
        );


        if (
            generation !==
                liveGeneration ||
            peerConnection !==
                connection
        ) {

            throw new Error(
                "Live connection became stale during offer creation."
            );

        }


        await connection.setLocalDescription(
            offer
        );


        log(
            "[ALERT LIVE] Local SDP set."
        );


        console.log(
            "[DEBUG][START LIVE] Local SDP set."
        );

        console.log(
            "[DEBUG][START LIVE] Signaling state:",
            connection.signalingState
        );

        console.log(
            "[DEBUG][START LIVE] ICE gathering state:",
            connection.iceGatheringState
        );


        /*
         * ====================================================
         * WAIT ICE
         * ====================================================
         */

        console.log(
            "[DEBUG][START LIVE] Waiting for ICE gathering."
        );


        await waitForIceGathering(
            connection
        );


        console.log(
            "[DEBUG][START LIVE] ICE gathering wait completed."
        );

        console.log(
            "[DEBUG][START LIVE] ICE gathering state:",
            connection.iceGatheringState
        );


        if (
            generation !==
                liveGeneration ||
            peerConnection !==
                connection
        ) {

            throw new Error(
                "Live connection became stale during ICE gathering."
            );

        }


        const localDescription =
            connection.localDescription;


        if (
            !localDescription ||
            !localDescription.sdp
        ) {

            throw new Error(
                "No local SDP description."
            );

        }


        console.log(
            "[DEBUG][START LIVE] Local SDP available."
        );

        console.log(
            "[DEBUG][START LIVE] Local SDP length:",
            localDescription.sdp.length
        );


        /*
         * ====================================================
         * WHEP ENDPOINT
         * ====================================================
         */

        const endpoint =
            "/ring/alerts/" +
            encodeURIComponent(
                deviceId
            ) +
            "/live/start/";


        log(
            "[ALERT LIVE] WHEP endpoint:",
            endpoint
        );


        console.log(
            "===================================="
        );

        console.log(
            "[DEBUG][WHEP] ABOUT TO POST TO LIVE ENDPOINT"
        );

        console.log(
            "[DEBUG][WHEP] Device ID:",
            deviceId
        );

        console.log(
            "[DEBUG][WHEP] Device Name:",
            deviceName
        );

        console.log(
            "[DEBUG][WHEP] Endpoint:",
            endpoint
        );

        console.log(
            "[DEBUG][WHEP] HTTP method: POST"
        );

        console.log(
            "[DEBUG][WHEP] Content-Type: application/sdp"
        );

        console.log(
            "[DEBUG][WHEP] SDP length:",
            localDescription.sdp.length
        );

        console.log(
            "[DEBUG][WHEP] Signaling state:",
            connection.signalingState
        );

        console.log(
            "[DEBUG][WHEP] ICE connection state:",
            connection.iceConnectionState
        );

        console.log(
            "[DEBUG][WHEP] ICE gathering state:",
            connection.iceGatheringState
        );

        console.log(
            "[DEBUG][WHEP] Full local SDP:",
            localDescription.sdp
        );

        console.log(
            "===================================="
        );


        setStatus(
            "Requesting camera stream...",
            "loading"
        );


        /*
         * ====================================================
         * WHEP REQUEST
         * ====================================================
         */

        const requestStartTime =
            Date.now();


        console.log(
            "[DEBUG][WHEP] fetch() starting at:",
            new Date(
                requestStartTime
            ).toISOString()
        );


        const response =
            await fetch(
                endpoint,
                {
                    method:
                        "POST",

                    headers: {

                        "Content-Type":
                            "application/sdp",

                        "Accept":
                            "application/sdp"

                    },

                    body:
                        localDescription.sdp,

                    credentials:
                        "same-origin",

                    cache:
                        "no-store",

                    signal:
                        liveAbortController.signal
                }
            );


        const responseEndTime =
            Date.now();


        console.log(
            "[DEBUG][WHEP] fetch() completed."
        );

        console.log(
            "[DEBUG][WHEP] Request duration:",
            responseEndTime -
            requestStartTime,
            "ms"
        );

        console.log(
            "[DEBUG][WHEP] HTTP status:",
            response.status
        );

        console.log(
            "[DEBUG][WHEP] HTTP status text:",
            response.statusText
        );

        console.log(
            "[DEBUG][WHEP] response.ok:",
            response.ok
        );

        console.log(
            "[DEBUG][WHEP] response.url:",
            response.url
        );


        const responseHeaders = {};


        response.headers.forEach(
            function(value, key) {

                responseHeaders[key] =
                    value;

            }
        );


        console.log(
            "[DEBUG][WHEP] Response headers:",
            responseHeaders
        );


        const responseText =
            await response.text();


        console.log(
            "[DEBUG][WHEP] Response body length:",
            responseText
                ? responseText.length
                : 0
        );


        console.log(
            "[DEBUG][WHEP] Response body:",
            responseText
        );


        log(
            "[ALERT LIVE] WHEP HTTP:",
            response.status
        );


        if (
            !response.ok
        ) {

            console.error(
                "[ALERT LIVE] WHEP response:",
                responseText
            );


            console.error(
                "[DEBUG][WHEP] WHEP REQUEST FAILED."
            );

            console.error(
                "[DEBUG][WHEP] Status:",
                response.status
            );

            console.error(
                "[DEBUG][WHEP] Response:",
                responseText
            );


            throw new Error(
                "WHEP request failed: HTTP " +
                response.status
            );

        }


        if (
            !responseText ||
            !responseText.trim()
        ) {

            console.error(
                "[DEBUG][WHEP] Ring returned empty response body."
            );


            throw new Error(
                "Ring returned an empty SDP answer."
            );

        }


        /*
         * ====================================================
         * SESSION URL
         * ====================================================
         */

        currentSessionUrl =
        response.headers.get(
            "X-Ring-Alert-Session-URL"
        ) ||
        response.headers.get(
            "X-Ring-Session-URL"
        ) ||
        response.headers.get(
            "Location"
        );


        log(
            "[ALERT LIVE] Session URL:",
            currentSessionUrl
        );


        console.log(
            "[DEBUG][WHEP] Session URL:",
            currentSessionUrl
        );


        /*
         * ====================================================
         * CLEAN SDP
         * ====================================================
 */

        console.log(
            "[DEBUG][SDP] About to clean Ring SDP."
        );

        console.log(
            "[DEBUG][SDP] Raw SDP length:",
            responseText.length
        );


        const cleanedSdp =
            cleanRingSdp(
                responseText
            );


        console.log(
            "[DEBUG][SDP] Cleaned SDP length:",
            cleanedSdp.length
        );


        /*
         * ====================================================
         * SIGNALLING CHECK
         * ====================================================
 */

        console.log(
            "[DEBUG][SDP] Signaling state before remote description:",
            connection.signalingState
        );


        if (
            connection.signalingState !==
            "have-local-offer"
        ) {

            throw new Error(
                "WebRTC is not ready for Ring's answer. State: " +
                connection.signalingState
            );

        }


        /*
         * ====================================================
         * SET REMOTE DESCRIPTION
         * ====================================================
 */

        console.log(
            "[DEBUG][SDP] About to call setRemoteDescription()."
        );


        console.log(
            "[DEBUG][SDP] Remote SDP:",
            cleanedSdp
        );


        await connection.setRemoteDescription(
            {
                type:
                    "answer",

                sdp:
                    cleanedSdp
            }
        );


        console.log(
            "[DEBUG][SDP] setRemoteDescription() SUCCESS."
        );

        console.log(
            "[DEBUG][SDP] New signaling state:",
            connection.signalingState
        );


        log(
            "[ALERT LIVE] Remote SDP successfully set."
        );


        console.log(
            "[ALERT LIVE] Remote SDP:",
            cleanedSdp
        );


        setStatus(
            "Waiting for camera video...",
            "loading"
        );


        console.log(
            "[DEBUG][START LIVE] startLive() signalling phase completed."
        );

        console.log(
            "[DEBUG][START LIVE] Waiting for ontrack."
        );


    } catch (error) {

        if (
            error &&
            error.name ===
            "AbortError"
        ) {

            log(
                "[ALERT LIVE] Live request aborted."
            );

            console.log(
                "[DEBUG][START LIVE] Request aborted."
            );

            return;

        }


        if (
            generation !==
            liveGeneration
        ) {

            log(
                "[ALERT LIVE] Ignoring stale error:",
                error
            );

            console.log(
                "[DEBUG][START LIVE] Ignoring stale error."
            );

            return;

        }


        console.error(
            "===================================="
        );

        console.error(
            "[ALERT LIVE] START FAILED"
        );

        console.error(
            "[DEBUG][START LIVE] Error name:",
            error &&
            error.name
        );

        console.error(
            "[DEBUG][START LIVE] Error message:",
            error &&
            error.message
        );

        console.error(
            "[DEBUG][START LIVE] Full error:",
            error
        );

        console.error(
            "===================================="
        );


        liveStarting =
            false;

        liveActive =
            false;


        setStatus(
            "Live feed unavailable",
            "error"
        );


        await stopLive(
            false
        );


        resumePolling();

    }

}


/* ============================================================
   WAIT FOR ICE GATHERING
   ============================================================ */

function waitForIceGathering(
    connection
) {

    return new Promise(
        function(resolve) {

            if (!connection) {

                resolve();

                return;

            }


            if (
                connection.iceGatheringState ===
                "complete"
            ) {

                resolve();

                return;

            }


            let finished =
                false;


            const timeout =
                setTimeout(
                    function() {

                        if (
                            finished
                        ) {

                            return;

                        }


                        finished =
                            true;


                        connection.removeEventListener(
                            "icegatheringstatechange",
                            checkState
                        );


                        console.warn(
                            "[ALERT LIVE] ICE gathering timeout; continuing."
                        );


                        resolve();

                    },
                    ICE_GATHER_TIMEOUT
                );


            function checkState() {

                if (
                    connection.iceGatheringState !==
                    "complete"
                ) {

                    return;

                }


                if (
                    finished
                ) {

                    return;

                }


                finished =
                    true;


                clearTimeout(
                    timeout
                );


                connection.removeEventListener(
                    "icegatheringstatechange",
                    checkState
                );


                resolve();

            }


            connection.addEventListener(
                "icegatheringstatechange",
                checkState
            );

        }
    );

}


/* ============================================================
   RING SDP CLEANER
   ============================================================ */

function cleanRingSdp(
    sdp
) {

    if (!sdp) {

        throw new Error(
            "Ring returned empty SDP."
        );

    }


    const lines =
        String(
            sdp
        )
            .replace(
                /\r\n/g,
                "\n"
            )
            .replace(
                /\r/g,
                "\n"
            )
            .split(
                "\n"
            );


    const cleaned =
        [];


    for (
        const rawLine of lines
    ) {

        let line =
            rawLine.trim();


        if (!line) {

            continue;

        }


        if (
            line.includes(
                "Invalid SDP line."
            )
        ) {

            const diagnosticIndex =
                line.indexOf(
                    "Invalid SDP line."
                );


            line =
                line
                    .slice(
                        0,
                        diagnosticIndex
                    )
                    .trim();


            if (!line) {

                continue;

            }

        }


        if (
            line.startsWith(
                "a=ssrc:"
            )
        ) {

            const match =
                line.match(
                    /^a=ssrc:\d+\s+[A-Za-z0-9_-]+:.+$/
                );


            if (!match) {

                console.warn(
                    "[ALERT LIVE] Removing malformed SSRC line:",
                    line
                );


                continue;

            }

        }


        cleaned.push(
            line
        );

    }


    let result =
        cleaned.join(
            "\r\n"
        );


    if (
        !result.endsWith(
            "\r\n"
        )
    ) {

        result +=
            "\r\n";

    }


    if (
        !result.includes(
            "v=0"
        )
    ) {

        throw new Error(
            "Ring SDP does not contain v=0."
        );

    }


    if (
        !result.includes(
            "m="
        )
    ) {

        throw new Error(
            "Ring SDP does not contain a media section."
        );

    }


    return result;

}


/* ============================================================
   STOP LIVE
   ============================================================ */

async function stopLive(
    resumeAfter = true
) {

    if (
        stopInProgress
    ) {

        return;

    }


    stopInProgress =
        true;

    if (liveAutoStopTimer) {
        clearTimeout(liveAutoStopTimer);
        liveAutoStopTimer = null;
    }


    clearVideoPlayRetry();

    videoPlayAttempt =
        0;


    log(
        "===================================="
    );

    log(
        "[ALERT LIVE] STOPPING LIVE"
    );

    log(
        "[ALERT LIVE] Device:",
        currentDeviceId
    );

    log(
        "===================================="
    );


    ++liveGeneration;


    liveStarting =
        false;

    liveActive =
        false;


    const oldDeviceId =
        currentDeviceId;


    const oldSessionUrl =
        currentSessionUrl;


    if (
        liveAbortController
    ) {

        try {

            liveAbortController.abort();

        } catch (error) {

            console.warn(
                "[ALERT LIVE] Abort warning:",
                error
            );

        }


        liveAbortController =
            null;

    }


    currentDeviceId =
        null;

    currentDeviceName =
        null;

    currentSessionUrl =
        null;


    const oldPeer =
        peerConnection;


    peerConnection =
        null;


    if (
        oldPeer
    ) {

        try {

            oldPeer.ontrack =
                null;

            oldPeer.onicecandidate =
                null;

            oldPeer.oniceconnectionstatechange =
                null;

            oldPeer.onconnectionstatechange =
                null;

            oldPeer.onicegatheringstatechange =
                null;


            oldPeer.close();

        } catch (error) {

            console.warn(
                "[ALERT LIVE] Peer close warning:",
                error
            );

        }

    }


    if (
        currentMediaStream
    ) {

        currentMediaStream
            .getTracks()
            .forEach(
                function(track) {

                    try {

                        track.stop();

                    } catch (error) {

                    }

                }
            );


        currentMediaStream =
            null;

    }


    showBlackVideo();


    if (
        oldDeviceId
    ) {

        const endpoint =
            "/ring/live/" +
            encodeURIComponent(
                oldDeviceId
            ) +
            "/stop/";


        try {

            const options = {

                method:
                    "POST",

                headers: {

                    "Accept":
                        "application/json",

                    "Content-Type":
                        "application/json"

                },

                credentials:
                    "same-origin"

            };


            if (
                oldSessionUrl
            ) {

                options.body =
                    JSON.stringify(
                        {
                            session_url:
                                oldSessionUrl
                        }
                    );

            }


            const response =
                await fetch(
                    endpoint,
                    options
                );


            log(
                "[ALERT LIVE] STOP HTTP:",
                response.status
            );


        } catch (error) {

            console.warn(
                "[ALERT LIVE] Stop request failed:",
                error
            );

        }

    }


    if (liveIndicator) {

        liveIndicator.className =
            "live-indicator live-indicator--idle";

        liveIndicator.textContent =
            "STANDBY";

    }


    setStatus(
        "Waiting for alert...",
        "idle"
    );


    if (currentDevice) {

        currentDevice.textContent =
            "Waiting for alert...";

    }


    stopInProgress =
        false;


    if (
        resumeAfter
    ) {

        resumePolling();

    }

}


/* ============================================================
   OPEN EXISTING ALERT
   ============================================================ */

async function openAlert(
    alert
) {

    console.log(
        "===================================="
    );

    console.log(
        "[DEBUG][OPEN ALERT] openAlert() ENTERED"
    );

    console.log(
        "[DEBUG][OPEN ALERT] Alert:",
        alert
    );

    console.log(
        "[DEBUG][OPEN ALERT] Alert ID:",
        getAlertId(alert)
    );

    console.log(
        "[DEBUG][OPEN ALERT] Device ID:",
        getAlertDeviceId(alert)
    );

    console.log(
        "[DEBUG][OPEN ALERT] Device Name:",
        getAlertDeviceName(alert)
    );

    console.log(
        "[DEBUG][OPEN ALERT] liveStarting:",
        liveStarting
    );

    console.log(
        "[DEBUG][OPEN ALERT] liveActive:",
        liveActive
    );

    console.log(
        "===================================="
    );


    if (!alert) {

        console.warn(
            "[DEBUG][OPEN ALERT] EXIT — alert is null/undefined."
        );

        return;

    }


    if (
        liveStarting ||
        liveActive
    ) {

        log(
            "[ALERTS] Live already active."
        );

        console.log(
            "[DEBUG][OPEN ALERT] EXIT — live already active."
        );

        return;

    }


    /*
     * THIS IS THE EXISTING WORKING TABLE-ROW PATH.
     *
     * Both:
     *
     *     table click
     *
     * and
     *
     *     API detected alert
     *
     * arrive here.
     */

    log(
        "===================================="
    );

    log(
        "[ALERTS] OPEN ALERT"
    );

    log(
        "[ALERTS] Same path used by table-row click."
    );

    log(
        "[ALERTS] Alert ID:",
        getAlertId(
            alert
        )
    );

    log(
        "[ALERTS] Device ID:",
        getAlertDeviceId(
            alert
        )
    );

    log(
        "[ALERTS] Device:",
        getAlertDeviceName(
            alert
        )
    );

    log(
        "===================================="
    );


    activeAlert =
        alert;


    console.log(
        "[DEBUG][OPEN ALERT] activeAlert assigned."
    );


    renderActiveAlert(
        alert
    );


    console.log(
        "[DEBUG][OPEN ALERT] renderActiveAlert() completed."
    );


    const deviceId =
        getAlertDeviceId(
            alert
        );


    console.log(
        "[DEBUG][OPEN ALERT] Extracted deviceId:",
        deviceId
    );


    if (!deviceId) {

        setStatus(
            "Alert has no device ID.",
            "error"
        );


        console.error(
            "[ALERTS] openAlert() received alert without device ID:",
            alert
        );


        console.error(
            "[DEBUG][OPEN ALERT] STOP — deviceId is empty."
        );


        return;

    }


    const deviceName =
        getAlertDeviceName(
            alert
        );


    console.log(
        "[DEBUG][OPEN ALERT] Extracted deviceName:",
        deviceName
    );


    pausePolling();


    console.log(
        "[DEBUG][OPEN ALERT] Polling paused."
    );


    /*
     * Play the recording associated with this alert.
     */

    console.log(
        "===================================="
    );

    console.log(
        "[DEBUG][OPEN ALERT] ABOUT TO PLAY ALERT VIDEO"
    );

    console.log(
        "[DEBUG][OPEN ALERT] alert:",
        alert
    );

    console.log(
        "===================================="
    );


    await playAlertVideo(alert);


    console.log(
        "[DEBUG][OPEN ALERT] Alert video playback returned."
    );

}


/* ============================================================
   STOP BUTTON
   ============================================================ */

if (
    stopLiveButton
) {

    stopLiveButton.addEventListener(
        "click",
        async function(event) {

            event.preventDefault();


            await stopLive(
                true
            );

        }
    );

}


if (soundButton) {
    soundButton.addEventListener(
        "click",
        async function(event) {
            event.preventDefault();

            if (!liveVideo) {
                return;
            }

            if (liveVideo.muted) {
                liveVideo.muted = false;
                liveVideo.volume = 1;
                soundButton.textContent = "Mute Sound";

                try {
                    await liveVideo.play();
                } catch (error) {
                    console.warn("[ALERT LIVE] Audio enable failed:", error);
                }
            } else {
                liveVideo.muted = true;
                soundButton.textContent = "Enable Sound";
            }
        }
    );
}


/* ============================================================
   CLOSE BUTTON
   ============================================================ */

if (
    closeLiveButton
) {

    closeLiveButton.addEventListener(
        "click",
        async function(event) {

            event.preventDefault();


            await stopLive(
                true
            );

        }
    );

}


/* ============================================================
   REFRESH BUTTON
   ============================================================ */

if (
    refreshButton
) {

    refreshButton.addEventListener(
        "click",
        async function(event) {

            event.preventDefault();


            if (
                liveStarting ||
                liveActive
            ) {

                log(
                    "[ALERTS] Refresh ignored while live is active."
                );


                return;

            }


            refreshButton.disabled =
                true;


            try {

                await loadAlerts(
                    {
                        force:
                            true
                    }
                );

            } finally {

                refreshButton.disabled =
                    false;

            }

        }
    );

}


/* ============================================================
   ERROR RETRY
   ============================================================ */

if (
    errorRetryButton
) {

    errorRetryButton.addEventListener(
        "click",
        async function(event) {

            event.preventDefault();


            await loadAlerts(
                {
                    force:
                        true
                }
            );

        }
    );

}


/* ============================================================
   ERROR
   ============================================================ */

function showError(
    message
) {

    if (errorState) {

        errorState.hidden =
            false;

    }


    if (errorMessage) {

        errorMessage.textContent =
            message;

    }

}


function hideError() {

    if (errorState) {

        errorState.hidden =
            true;

    }

}


/* ============================================================
   VISIBILITY
   ============================================================ */

document.addEventListener(
    "visibilitychange",
    function() {

        if (
            document.hidden
        ) {

            return;

        }


        if (
            liveStarting ||
            liveActive
        ) {

            return;

        }


        if (
            !pollingPaused
        ) {

            scheduleNextPoll(
                500
            );

        }

    }
);


/* ============================================================
   PAGE CLEANUP
   ============================================================ */

window.addEventListener(
    "beforeunload",
    function() {

        ++liveGeneration;


        clearVideoPlayRetry();


        if (
            liveAbortController
        ) {

            try {

                liveAbortController.abort();

            } catch (error) {

            }

        }


        if (
            peerConnection
        ) {

            try {

                peerConnection.close();

            } catch (error) {

            }

        }


        if (
            currentMediaStream
        ) {

            currentMediaStream
                .getTracks()
                .forEach(
                    function(track) {

                        try {

                            track.stop();

                        } catch (error) {

                        }

                    }
                );

        }


        if (
            liveVideo
        ) {

            try {

                liveVideo.pause();

                liveVideo.srcObject =
                    null;

            } catch (error) {

            }

        }

    }
);


/* ============================================================
   INITIALISE
   ============================================================ */

document.addEventListener(
    "DOMContentLoaded",
    async function() {

        console.log(
            "===================================="
        );

        console.log(
            "[ALERTS] DOM READY"
        );

        console.log(
            "[ALERTS] Initialising..."
        );

        console.log(
            "[ALERTS] Diagnostic logging active."
        );

        console.log(
            "===================================="
        );


        showBlackVideo();


        if (liveIndicator) {

            liveIndicator.className =
                "live-indicator live-indicator--idle";

            liveIndicator.textContent =
                "STANDBY";

        }


        setStatus(
            "Waiting for alert...",
            "idle"
        );


        console.log(
            "[DEBUG][INIT] Calling initial loadAlerts()."
        );


        await loadAlerts();


        pageInitialised =
            true;


        scheduleNextPoll(
            ALERT_POLL_INTERVAL
        );


        log(
            "[ALERTS] Initialisation complete."
        );


        log(
            "[ALERTS] Waiting for NEW alert..."
        );


        console.log(
            "[DEBUG][INIT] Polling scheduled."
        );

    }
);
