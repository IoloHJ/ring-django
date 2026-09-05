"use strict";

console.log("====================================");
console.log("RING LIVE JS LOADED - VERSION 5");
console.log("====================================");


document.addEventListener("DOMContentLoaded", function () {

    console.log("[RING LIVE] DOM READY");

    const deviceSelect = document.getElementById("deviceSelect");
    const startButton = document.getElementById("startButton");
    const stopButton = document.getElementById("stopButton");
    const soundButton = document.getElementById("soundButton");
    const video = document.getElementById("liveVideo");
    const status = document.getElementById("status");
    const cameraStatus = document.getElementById("cameraStatus");
    const liveIndicator = document.getElementById("liveIndicator");
    const noStreamOverlay = document.getElementById("noStreamOverlay");

    console.log("[RING LIVE] Elements:");
    console.log("deviceSelect:", deviceSelect);
    console.log("startButton:", startButton);
    console.log("stopButton:", stopButton);
    console.log("soundButton:", soundButton);
    console.log("video:", video);
    console.log("status:", status);
    console.log("cameraStatus:", cameraStatus);
    console.log("liveIndicator:", liveIndicator);
    console.log("noStreamOverlay:", noStreamOverlay);


    if (!deviceSelect) {
        console.error("[RING LIVE] ERROR: #deviceSelect not found");
        return;
    }


    let peerConnection = null;
    let currentDeviceId = null;


    // ============================================================
    // STATUS
    // ============================================================

    function setStatus(message, state) {

        if (!status) {
            return;
        }

        status.textContent = message;

        status.className = "status";

        if (state) {
            status.classList.add("status--" + state);
        }

        console.log("[RING LIVE] STATUS:", message);
    }


    // ============================================================
    // CAMERA STATUS
    // ============================================================

    function setCameraStatus(message) {

        if (!cameraStatus) {
            return;
        }

        cameraStatus.textContent = message;

        console.log("[RING LIVE] CAMERA STATUS:", message);
    }


    // ============================================================
    // LOAD DEVICES
    // ============================================================

    function loadDevices() {

        console.log("[RING LIVE] Loading devices...");

        setStatus("Loading Ring devices...", "loading");

        fetch("/ring/devices/", {
            method: "GET",
            headers: {
                "Accept": "application/json"
            },
            cache: "no-store"
        })

        .then(function (response) {

            console.log(
                "[RING LIVE] /ring/devices/ HTTP:",
                response.status
            );

            if (!response.ok) {

                throw new Error(
                    "Ring devices request failed: HTTP " +
                    response.status
                );
            }

            return response.json();
        })

        .then(function (response) {

            console.log(
                "===================================="
            );

            console.log(
                "[RING LIVE] FULL DEVICES RESPONSE:"
            );

            console.log(response);

            console.log(
                "===================================="
            );

            populateDevices(response);
        })

        .catch(function (error) {

            console.error(
                "[RING LIVE] DEVICE LOAD ERROR:",
                error
            );

            setStatus(
                "Failed to load Ring devices.",
                "error"
            );

            deviceSelect.innerHTML = "";

            const option = document.createElement("option");

            option.value = "";
            option.textContent = "Failed to load devices";

            deviceSelect.appendChild(option);
        });
    }


    // ============================================================
    // POPULATE DEVICES
    // ============================================================

    function populateDevices(response) {

        console.log("[RING LIVE] populateDevices()");

        let devices = [];


        /*
         * Ring API response currently looks like:
         *
         * {
         *     status_code: 200,
         *     data: {
         *         data: [
         *             {
         *                 type: "devices",
         *                 id: "...",
         *                 attributes: {
         *                     name: "Downstairs",
         *                     image_url: "..."
         *                 }
         *             }
         *         ]
         *     }
         * }
         */


        if (
            response &&
            response.data &&
            Array.isArray(response.data.data)
        ) {

            devices = response.data.data;

        }


        console.log(
            "[RING LIVE] Extracted devices:",
            devices
        );

        console.log(
            "[RING LIVE] Device count:",
            devices.length
        );


        deviceSelect.innerHTML = "";


        if (devices.length === 0) {

            const option = document.createElement("option");

            option.value = "";
            option.textContent = "No devices found";

            deviceSelect.appendChild(option);

            if (startButton) {
                startButton.disabled = true;
            }

            setStatus(
                "No Ring devices found.",
                "error"
            );

            return;
        }


        // Placeholder

        const placeholder = document.createElement("option");

        placeholder.value = "";
        placeholder.textContent = "Select a Ring device";

        deviceSelect.appendChild(placeholder);


        // Add devices

        devices.forEach(function (device, index) {

            console.log(
                "[RING LIVE] Processing device:",
                index,
                device
            );


            const attributes = device.attributes || {};

            const name =
                attributes.name ||
                "Ring Device " + (index + 1);

            const id = device.id;


            if (!id) {

                console.warn(
                    "[RING LIVE] Device has no ID:",
                    device
                );

                return;
            }


            const option =
                document.createElement("option");

            option.value = id;
            option.textContent = name;

            deviceSelect.appendChild(option);


            console.log(
                "[RING LIVE] Added:",
                name,
                id
            );
        });


        setStatus(
            devices.length +
            " Ring device" +
            (devices.length === 1 ? "" : "s") +
            " available.",
            "ready"
        );


        console.log(
            "[RING LIVE] Dropdown options:",
            deviceSelect.options.length
        );
    }


    // ============================================================
    // DEVICE SELECTED
    // ============================================================

    deviceSelect.addEventListener(
        "change",
        function () {

            const deviceId = deviceSelect.value;

            console.log(
                "===================================="
            );

            console.log(
                "[RING LIVE] DEVICE SELECT CHANGED"
            );

            console.log(
                "[RING LIVE] Selected ID:",
                deviceId
            );

            console.log(
                "[RING LIVE] Selected text:",
                deviceSelect.options[
                    deviceSelect.selectedIndex
                ]?.text
            );

            console.log(
                "===================================="
            );


            currentDeviceId = deviceId;


            if (!deviceId) {

                setCameraStatus(
                    "No camera selected"
                );

                if (startButton) {
                    startButton.disabled = true;
                }

                return;
            }


            const selectedOption =
                deviceSelect.options[
                    deviceSelect.selectedIndex
                ];


            const deviceName =
                selectedOption.textContent;


            setCameraStatus(
                deviceName
            );


            setStatus(
                deviceName + " selected.",
                "ready"
            );


            if (startButton) {
                startButton.disabled = false;
            }


            console.log(
                "[RING LIVE] Camera selected:",
                deviceName
            );
        }
    );


    // ============================================================
    // START BUTTON
    // ============================================================

    if (startButton) {

        startButton.addEventListener(
            "click",
            function () {

                console.log(
                    "[RING LIVE] START LIVE CLICKED"
                );


                const deviceId =
                    deviceSelect.value;


                if (!deviceId) {

                    console.warn(
                        "[RING LIVE] No device selected"
                    );

                    return;
                }


                startLive(deviceId);
            }
        );
    }


    // ============================================================
    // STOP BUTTON
    // ============================================================

    if (stopButton) {

        stopButton.addEventListener(
            "click",
            function () {

                console.log(
                    "[RING LIVE] STOP CLICKED"
                );

                stopLive();
            }
        );
    }


    if (soundButton) {
        soundButton.addEventListener(
            "click",
            function () {
                if (!video) {
                    return;
                }

                video.muted = !video.muted;
                video.volume = 1;
                soundButton.textContent = video.muted
                    ? "Enable Sound"
                    : "Mute Sound";

                if (!video.muted) {
                    video.play().catch(function (error) {
                        console.warn(
                            "[RING LIVE] Audio enable failed:",
                            error
                        );
                    });
                }
            }
        );
    }


    // ============================================================
    // START LIVE
    // ============================================================

    function startLive(deviceId) {

        console.log(
            "===================================="
        );

        console.log(
            "[RING LIVE] STARTING LIVE"
        );

        console.log(
            "[RING LIVE] Device ID:",
            deviceId
        );

        console.log(
            "===================================="
        );


        currentDeviceId = deviceId;


        const selectedOption =
            deviceSelect.options[
                deviceSelect.selectedIndex
            ];


        const deviceName =
            selectedOption
                ? selectedOption.textContent
                : "Ring Camera";


        setCameraStatus(
            "Starting " + deviceName + "..."
        );


        setStatus(
            "Starting live feed...",
            "loading"
        );


        if (startButton) {
            startButton.disabled = true;
        }


        if (stopButton) {
            stopButton.disabled = false;
        }


        hideOverlay();


        /*
         * Create a WebRTC peer connection.
         */

        peerConnection =
            new RTCPeerConnection({
                iceServers: []
            });


        console.log(
            "[RING LIVE] RTCPeerConnection created"
        );


        // ========================================================
        // REMOTE TRACK
        // ========================================================

        peerConnection.ontrack =
            function (event) {

                console.log(
                    "[RING LIVE] REMOTE TRACK RECEIVED",
                    event
                );


                if (!video) {

                    console.error(
                        "[RING LIVE] Video element missing"
                    );

                    return;
                }


                if (
                    event.streams &&
                    event.streams.length > 0
                ) {

                    console.log(
                        "[RING LIVE] Attaching remote stream"
                    );


                    video.srcObject =
                        event.streams[0];


                    hideOverlay();


                    video.play()
                        .then(function () {

                            video.muted = false;
                            video.volume = 1;

                            if (soundButton) {
                                soundButton.hidden = false;
                                soundButton.textContent = "Mute Sound";
                            }

                            console.log(
                                "[RING LIVE] Video playback started"
                            );

                        })
                        .catch(function (error) {

                            console.warn(
                                "[RING LIVE] Video play warning:",
                                error
                            );
                        });


                    setCameraStatus(
                        deviceName
                    );


                    setStatus(
                        "Live: " + deviceName,
                        "live"
                    );


                    showLiveIndicator();
                }
            };


        // ========================================================
        // ICE STATE
        // ========================================================

        peerConnection.oniceconnectionstatechange =
            function () {

                console.log(
                    "[RING LIVE] ICE state:",
                    peerConnection.iceConnectionState
                );


                if (
                    peerConnection.iceConnectionState ===
                    "connected"
                ) {

                    setStatus(
                        "Connected: " + deviceName,
                        "live"
                    );

                }


                if (
                    peerConnection.iceConnectionState ===
                    "failed"
                ) {

                    console.error(
                        "[RING LIVE] ICE connection failed"
                    );

                    setStatus(
                        "Live connection failed.",
                        "error"
                    );

                    setCameraStatus(
                        deviceName +
                        " — connection failed"
                    );

                    showOverlay();
                }
            };


        // ========================================================
        // CONNECTION STATE
        // ========================================================

        peerConnection.onconnectionstatechange =
            function () {

                console.log(
                    "[RING LIVE] Connection state:",
                    peerConnection.connectionState
                );


                if (
                    peerConnection.connectionState ===
                    "connected"
                ) {

                    setStatus(
                        "Live: " + deviceName,
                        "live"
                    );

                }


                if (
                    peerConnection.connectionState ===
                    "failed"
                ) {

                    setStatus(
                        "Live connection failed.",
                        "error"
                    );
                }
            };


        // ========================================================
        // WHEP RECEIVER
        // ========================================================

        peerConnection.addTransceiver(
            "video",
            {
                direction: "recvonly"
            }
        );


        peerConnection.addTransceiver(
            "audio",
            {
                direction: "recvonly"
            }
        );


        console.log(
            "[RING LIVE] Added recvonly transceivers"
        );


        // ========================================================
        // CREATE SDP OFFER
        // ========================================================

        peerConnection.createOffer()
            .then(function (offer) {

                console.log(
                    "[RING LIVE] SDP offer created"
                );


                return peerConnection.setLocalDescription(
                    offer
                );
            })

            .then(function () {

                console.log(
                    "[RING LIVE] Local SDP set"
                );


                const localDescription =
                    peerConnection.localDescription;


                if (!localDescription) {

                    throw new Error(
                        "No local SDP description"
                    );
                }


                const endpoint =
                    "/ring/live/" +
                    encodeURIComponent(deviceId) +
                    "/start/";


                console.log(
                    "[RING LIVE] WHEP endpoint:",
                    endpoint
                );


                return fetch(
                    endpoint,
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/sdp",

                            "Accept":
                                "application/sdp"
                        },

                        body:
                            localDescription.sdp
                    }
                );
            })

            .then(function (response) {

                console.log(
                    "[RING LIVE] WHEP HTTP status:",
                    response.status
                );


                return response.text()
                    .then(function (sdp) {

                        console.log(
                            "[RING LIVE] WHEP response SDP:",
                            sdp
                        );


                        if (!response.ok) {

                            throw new Error(
                                "WHEP request failed: HTTP " +
                                response.status +
                                " - " +
                                sdp
                            );
                        }


                        return sdp;
                    });
            })

            .then(function (sdp) {

                console.log(
                    "[RING LIVE] Setting remote SDP"
                );


                return peerConnection.setRemoteDescription(
                    {
                        type: "answer",
                        sdp: sdp
                    }
                );
            })

            .then(function () {

                console.log(
                    "[RING LIVE] Remote SDP description set"
                );


                setCameraStatus(
                    deviceName
                );
            })

            .catch(function (error) {

                console.error(
                    "===================================="
                );

                console.error(
                    "[RING LIVE] LIVE START ERROR"
                );

                console.error(error);

                console.error(
                    "===================================="
                );


                setStatus(
                    "Unable to start live feed.",
                    "error"
                );


                setCameraStatus(
                    deviceName +
                    " — failed to start"
                );


                showOverlay();


                if (startButton) {
                    startButton.disabled = false;
                }


                if (stopButton) {
                    stopButton.disabled = true;
                }
            });
    }


    // ============================================================
    // STOP LIVE
    // ============================================================

    function stopLive() {

        console.log(
            "[RING LIVE] Stopping live feed"
        );


        if (peerConnection) {

            peerConnection.close();

            peerConnection = null;
        }


        if (video) {

            video.pause();

            video.muted = true;

            video.srcObject = null;
        }


        if (soundButton) {
            soundButton.hidden = true;
            soundButton.textContent = "Enable Sound";
        }


        hideLiveIndicator();

        showOverlay();


        if (currentDeviceId) {

            const selectedOption =
                deviceSelect.options[
                    deviceSelect.selectedIndex
                ];


            const deviceName =
                selectedOption
                    ? selectedOption.textContent
                    : "Ring Camera";


            setCameraStatus(
                deviceName
            );

            setStatus(
                deviceName + " selected.",
                "ready"
            );

        } else {

            setCameraStatus(
                "No camera selected"
            );

            setStatus(
                "Select a Ring device.",
                "ready"
            );
        }


        if (startButton) {
            startButton.disabled =
                !deviceSelect.value;
        }


        if (stopButton) {
            stopButton.disabled = true;
        }
    }


    // ============================================================
    // OVERLAY
    // ============================================================

    function showOverlay() {

        if (noStreamOverlay) {
            noStreamOverlay.style.display = "flex";
        }
    }


    function hideOverlay() {

        if (noStreamOverlay) {
            noStreamOverlay.style.display = "none";
        }
    }


    // ============================================================
    // LIVE INDICATOR
    // ============================================================

    function showLiveIndicator() {

        if (liveIndicator) {

            liveIndicator.hidden = false;
        }
    }


    function hideLiveIndicator() {

        if (liveIndicator) {

            liveIndicator.hidden = true;
        }
    }


    // ============================================================
    // INITIAL LOAD
    // ============================================================

    loadDevices();

});
