/**
 * LiveAirMic Automatic Clip Latency Compensator (Max for Live JS / LiveAPI)
 * Automatically advances start_marker & loop_start on recorded audio clips
 * to compensate for round-trip mobile/USB microphone latency when recording
 * via internal track routing (e.g. 3-Audio -> 4-Audio).
 */

autowatch = 1;
inlets = 1;
outlets = 1;

var latencyCompMs = 0.0;
var alignedClipIds = {};
var wasRecording = false;

var statusCommentObj = null;

function set_status_led(isOnline) {
    try {
        if (!statusCommentObj) {
            simplify_m4l_ui();
        }
        if (statusCommentObj) {
            if (isOnline) {
                try { statusCommentObj.message("set", "● ONLINE"); } catch (e1) {}
                try { statusCommentObj.setattr("textcolor", 0.06, 0.85, 0.50, 1.0); } catch (e2) {}
                try { statusCommentObj.message("textcolor", 0.06, 0.85, 0.50, 1.0); } catch (e3) {}
            } else {
                try { statusCommentObj.message("set", "● OFFLINE"); } catch (e4) {}
                try { statusCommentObj.setattr("textcolor", 0.95, 0.28, 0.28, 1.0); } catch (e5) {}
                try { statusCommentObj.message("textcolor", 0.95, 0.28, 0.28, 1.0); } catch (e6) {}
            }
        }
    } catch (e) {}
}

function simplify_m4l_ui() {
    try {
        try { this.patcher.setattr("devicewidth", 150.0); } catch (ep1) {}
        try { this.patcher.message("devicewidth", 150.0); } catch (ep2) {}
        var b = this.patcher.firstobject;
        while (b) {
            var mc = String(b.maxclass || "");
            var r = b.rect || [0, 0, 0, 0];
            var x = r[0] || 0;
            var y = r[1] || 0;

            if (mc === "live.text" || mc === "live.numbox") {
                try { b.setattr("presentation", 0); } catch (e1) {}
                try { b.message("presentation", 0); } catch (e2) {}
            } else if (mc === "textbutton") {
                if (Math.abs(x - 510) < 20) {
                    // Connect Button (obj-ui-btn-usb)
                    try { b.setattr("text", "CONNECT"); } catch (e3) {}
                    try { b.message("text", "CONNECT"); } catch (e4) {}
                    try { b.setattr("presentation", 1); } catch (e5) {}
                    try { b.message("presentation_rect", 12.0, 92.0, 88.0, 36.0); } catch (e6) {}
                } else {
                    try { b.setattr("presentation", 0); } catch (e7) {}
                    try { b.message("presentation", 0); } catch (e8) {}
                }
            } else if (mc === "comment") {
                if (Math.abs(y - 40) < 8 && Math.abs(x - 310) < 20) {
                    // Title (obj-title)
                    try { b.setattr("presentation", 1); } catch (e9) {}
                    try { b.message("presentation_rect", 12.0, 16.0, 95.0, 20.0); } catch (e10) {}
                } else if (Math.abs(y - 70) < 8) {
                    // Status Light (obj-ui-status)
                    statusCommentObj = b;
                    try { b.setattr("presentation", 1); } catch (e11) {}
                    try { b.message("presentation_rect", 12.0, 50.0, 92.0, 24.0); } catch (e12) {}
                    try { b.message("fontsize", 11.5); } catch (e13) {}
                } else {
                    // Hide version badge, latency text, and meter text from presentation
                    try { b.setattr("presentation", 0); } catch (e14) {}
                    try { b.message("presentation", 0); } catch (e15) {}
                }
            } else if (mc === "live.meter~") {
                try { b.setattr("presentation", 1); } catch (e16) {}
                try { b.message("presentation_rect", 112.0, 16.0, 26.0, 136.0); } catch (e17) {}
            } else if (mc === "panel") {
                try { b.setattr("presentation", 1); } catch (e18) {}
                try { b.message("presentation_rect", 0.0, 0.0, 150.0, 169.0); } catch (e19) {}
            }
            b = b.nextobject;
        }
    } catch (e) {}
}

function lock_jitter_release_fifo() {
    try {
        simplify_m4l_ui();
        var b = this.patcher.firstobject;
        var logLines = [];
        var routeObj = null;
        var jsObj = null;
        while (b) {
            var mc = String(b.maxclass || "");
            var bt = String(b.getattr ? (b.getattr("boxtext") || "") : "");
            if (mc === "jit.release~" || mc === "jit.matrix" || mc === "udpreceive") {
                var beforeMode = b.getattr ? b.getattr("mode") : "n/a";
                var beforeLat = b.getattr ? b.getattr("latency") : "n/a";
                if (mc === "jit.release~") {
                    try { b.setattr("mode", 0); } catch (e1) {}
                    try { b.message("mode", 0); } catch (e2) {}
                    try { b.setattr("latency", 12.0); } catch (e3) {}
                    try { b.message("latency", 12.0); } catch (e4) {}
                }
                if (mc === "udpreceive") {
                    try { b.message("maxqueuesize", 64); } catch (e5) {}
                }
                var afterMode = b.getattr ? b.getattr("mode") : "n/a";
                var afterLat = b.getattr ? b.getattr("latency") : "n/a";
                logLines.push(mc + " before(mode=" + beforeMode + ",lat=" + beforeLat + ") after(mode=" + afterMode + ",lat=" + afterLat + ")");
            } else if (mc === "route") {
                routeObj = b;
            } else if (mc === "js") {
                jsObj = b;
            }
            b = b.nextobject;
        }
        // Connect route outlet 11 (/airmic/fx_ctl) directly to js clip_align.js inlet 0 for 0ms OSC FX execution!
        if (routeObj && jsObj) {
            try { this.patcher.connect(routeObj, 11, jsObj, 0); } catch (eConn) {}
        }
        var f = new File("/tmp/airmic_patcher_diag.txt", "write");
        if (f.isopen) {
            f.writeline(logLines.join(" | "));
            f.close();
        }
    } catch (e) {}
}
lock_jitter_release_fifo();

// Start a fast 25ms Task timer inside js so even if the patcher precedes outlet 11,
// FX commands are picked up in <25ms instead of waiting for the 1000ms metro!
var fastFxTask = new Task( poll_fx_file, this );
fastFxTask.interval = 25;
fastFxTask.repeat();

function set_latency_ms(v) {
    // Clip start-marker shifting is disabled so clips reflect true real-time stream latency
    latencyCompMs = 0.0;
}

function align_now() {
    alignedClipIds = {};
    scan_and_align(true);
}

function forEachVocalDevice(trackPath, callback) {
    var track = new LiveAPI(trackPath);
    if (!track || !track.id) return;
    var devCount = track.getcount("devices");
    for (var d = 0; d < devCount; d++) {
        var devPath = trackPath + " devices " + d;
        var dev = new LiveAPI(devPath);
        if (!dev || !dev.id) continue;
        var isRack = parseInt(dev.get("can_have_chains")) === 1;
        callback(dev, devPath, isRack, false);
        if (isRack) {
            var chainCount = dev.getcount("chains");
            for (var c = 0; c < chainCount; c++) {
                var chainPath = devPath + " chains " + c;
                var chain = new LiveAPI(chainPath);
                if (!chain || !chain.id) continue;
                var cDevCount = chain.getcount("devices");
                for (var cd = 0; cd < cDevCount; cd++) {
                    var cDevPath = chainPath + " devices " + cd;
                    var cDev = new LiveAPI(cDevPath);
                    if (cDev && cDev.id) {
                        callback(cDev, cDevPath, false, true);
                    }
                }
            }
        }
    }
}

function dial_reggae_vocal() {
    try {
        var liveSet = new LiveAPI("live_set");
        if (!liveSet || !liveSet.id) return;
        var trackCount = liveSet.getcount("tracks");
        for (var t = 0; t < trackCount; t++) {
            var trackPath = "live_set tracks " + t;
            var track = new LiveAPI(trackPath);
            var tname = String(track.get("name") || "").replace(/^"+|"+$/g, "");
            if (tname.indexOf("Guitar") !== -1) {
                // Remove any Gate accidentally placed on a Guitar track
                var gTopCount = track.getcount("devices");
                for (var gDel = gTopCount - 1; gDel >= 0; gDel--) {
                    var gd = new LiveAPI(trackPath + " devices " + gDel);
                    var gdClass = String(gd.get("class_name") || "").replace(/^"+|"+$/g, "");
                    if (gdClass === "Gate") {
                        try { track.call("delete_device", gDel); } catch (eGd) {}
                    }
                }
                continue;
            }
            if (tname.indexOf("Vocal") === -1 && t !== 3) continue;

            // Step 1: Clean up disabled legacy devices ("Vocal Presence", "Ambience") if at top level
            var topCount = track.getcount("devices");
            for (var delIdx = topCount - 1; delIdx >= 0; delIdx--) {
                var td = new LiveAPI(trackPath + " devices " + delIdx);
                var tdName = String(td.get("name") || "").replace(/^"+|"+$/g, "");
                if (tdName === "Vocal Presence" || tdName === "Ambience") {
                    try { track.call("delete_device", delIdx); } catch (eDel) {}
                }
            }

            // Step 2: Check if the natively-mapped "Reggae Vocal Chain" (with "Dub Filter" inside chains 0) is present.
            // If so, remove any legacy duplicate racks or top-level Gate so only the natively-mapped Rack remains!
            topCount = track.getcount("devices");
            var nativeMappedRackIdx = -1;
            for (var nrIdx = 0; nrIdx < topCount; nrIdx++) {
                var nrd = new LiveAPI(trackPath + " devices " + nrIdx);
                if (parseInt(nrd.get("can_have_chains")) === 1 && nrd.getcount("chains") > 0) {
                    var nch0Path = trackPath + " devices " + nrIdx + " chains 0";
                    var nch0 = new LiveAPI(nch0Path);
                    var nchCount = nch0.getcount("devices");
                    for (var ndi = 0; ndi < nchCount; ndi++) {
                        var nd = new LiveAPI(nch0Path + " devices " + ndi);
                        var ndName = String(nd.get("name") || "").replace(/^"+|"+$/g, "");
                        if (ndName === "Dub Filter") {
                            nativeMappedRackIdx = nrIdx;
                            break;
                        }
                    }
                }
            }

            if (nativeMappedRackIdx !== -1) {
                for (var delTop = topCount - 1; delTop >= 0; delTop--) {
                    if (delTop !== nativeMappedRackIdx) {
                        try { track.call("delete_device", delTop); } catch (eDelOld) {}
                    }
                }
                // Set clean, feedback-safe Macro defaults & smooth Gate floor (-14 dB)
                try {
                    var defaultMacros = [0, 32.0, 38.0, 0.0, 28.0, 38.0, 50.0, 45.0, 12.0];
                    for (var mi = 1; mi <= 8; mi++) {
                        var mp = new LiveAPI(trackPath + " devices 0 parameters " + mi);
                        if (mp && mp.id) mp.set("value", defaultMacros[mi]);
                    }
                    var vgDev = new LiveAPI(trackPath + " devices 0 chains 0 devices 0");
                    if (vgDev && vgDev.id) {
                        var vgPCount = vgDev.getcount("parameters");
                        for (var vgp = 0; vgp < vgPCount; vgp++) {
                            var vgPar = new LiveAPI(trackPath + " devices 0 chains 0 devices 0 parameters " + vgp);
                            var vgPName = String(vgPar.get("name") || "").replace(/^"+|"+$/g, "");
                            if (vgPName === "Floor") vgPar.set("value", -14.0);
                            if (vgPName === "Hold") vgPar.set("value", 260.0);
                            if (vgPName === "Release") vgPar.set("value", 420.0);
                            if (vgPName === "Return") vgPar.set("value", 6.0);
                        }
                    }
                } catch (eGateLow) {}
                continue;
            }

            // Fallback consolidation if only legacy racks exist
            topCount = track.getcount("devices");
            for (var gIdx = 1; gIdx < topCount; gIdx++) {
                var gdTop = new LiveAPI(trackPath + " devices " + gIdx);
                var gdTopName = String(gdTop.get("name") || "").replace(/^"+|"+$/g, "");
                var gdTopClass = String(gdTop.get("class_name") || "").replace(/^"+|"+$/g, "");
                if (gdTopClass === "Gate" || gdTopName === "Vocal Gate" || gdTopName === "Gate") {
                    try {
                        liveSet.call("move_device", "id", gdTop.id, "id", track.id, 0);
                    } catch (eMoveG) {}
                    break;
                }
            }

            // Step 2b: Consolidate into the "Reggae Vocal Chain" rack (with Dub Echo Mix macro) and enforce signal flow order
            topCount = track.getcount("devices");
            var targetRackIdx = -1;
            var legacyRackIdx = -1;
            for (var rIdx = 0; rIdx < topCount; rIdx++) {
                var rd = new LiveAPI(trackPath + " devices " + rIdx);
                if (parseInt(rd.get("can_have_chains")) === 1) {
                    var m1 = new LiveAPI(trackPath + " devices " + rIdx + " parameters 1");
                    var m1Name = String(m1.get("name") || "").replace(/^"+|"+$/g, "");
                    if (m1Name === "Dub Echo Mix") {
                        targetRackIdx = rIdx;
                    } else {
                        legacyRackIdx = rIdx;
                    }
                }
            }
            if (targetRackIdx === -1 && legacyRackIdx !== -1) {
                targetRackIdx = legacyRackIdx;
                legacyRackIdx = -1;
            }
            if (targetRackIdx !== -1 && legacyRackIdx !== -1) {
                var targetChain0 = new LiveAPI(trackPath + " devices " + targetRackIdx + " chains 0");
                var legChain0Path = trackPath + " devices " + legacyRackIdx + " chains 0";
                var legChain0 = new LiveAPI(legChain0Path);
                if (targetChain0 && targetChain0.id && legChain0 && legChain0.id) {
                    var wantedOrder = ["Tune Smooth", "Vocal Curve", "Sustained Lead Vocal", "Warm Tube", "Dub Syndicate", "Spring Parade"];
                    for (var wo = 0; wo < wantedOrder.length; wo++) {
                        var wantName = wantedOrder[wo];
                        var lcCount = legChain0.getcount("devices");
                        for (var lci = 0; lci < lcCount; lci++) {
                            var lDev = new LiveAPI(legChain0Path + " devices " + lci);
                            var lName = String(lDev.get("name") || "").replace(/^"+|"+$/g, "");
                            if (lName === wantName) {
                                try {
                                    liveSet.call("move_device", "id", lDev.id, "id", targetChain0.id, targetChain0.getcount("devices"));
                                } catch (eMvL) {}
                                break;
                            }
                        }
                    }
                    try { track.call("delete_device", legacyRackIdx); } catch (eDelLeg) {}
                }
            }

            topCount = track.getcount("devices");
            var rackIdx = -1;
            for (var rIdx2 = 0; rIdx2 < topCount; rIdx2++) {
                var rd2 = new LiveAPI(trackPath + " devices " + rIdx2);
                if (parseInt(rd2.get("can_have_chains")) === 1) {
                    rackIdx = rIdx2;
                    break;
                }
            }
            if (rackIdx !== -1) {
                var rackPath = trackPath + " devices " + rackIdx;
                var rackDev = new LiveAPI(rackPath);
                try { rackDev.set("name", "Reggae Vocal Chain"); } catch (eRn0) {}
                if (rackDev.getcount("chains") > 0) {
                    var chain0Path = rackPath + " chains 0";
                    var chain0 = new LiveAPI(chain0Path);
                    try { chain0.set("name", "Warm Reggae + Tune"); } catch (eCn) {}
                    // Remove legacy disabled devices (De-esser, A Bit Warmer) and pull any Gate to top-level index 0
                    var chCount = chain0.getcount("devices");
                    for (var gi = chCount - 1; gi >= 0; gi--) {
                        var gCand = new LiveAPI(chain0Path + " devices " + gi);
                        var gClass = String(gCand.get("class_name") || "").replace(/^"+|"+$/g, "");
                        var gName = String(gCand.get("name") || "").replace(/^"+|"+$/g, "");
                        if (gClass === "Gate") {
                            try {
                                liveSet.call("move_device", "id", gCand.id, "id", track.id, 0);
                            } catch (eMvG) {}
                        } else if (gName === "De-esser" || gName === "A Bit Warmer") {
                            try { chain0.call("delete_device", gi); } catch (eDelCh) {}
                        }
                    }
                    // Move any other non-rack, non-Gate top-level device into chain0
                    var safety = 20;
                    while (track.getcount("devices") > 2 && safety-- > 0) {
                        var movedOne = false;
                        var curTop = track.getcount("devices");
                        for (var ti = 0; ti < curTop; ti++) {
                            var cand = new LiveAPI(trackPath + " devices " + ti);
                            var candClass = String(cand.get("class_name") || "").replace(/^"+|"+$/g, "");
                            if (parseInt(cand.get("can_have_chains")) !== 1 && candClass !== "Gate") {
                                var destIdx = (candClass === "AutoShift") ? 0 : chain0.getcount("devices");
                                try {
                                    liveSet.call("move_device", "id", cand.id, "id", chain0.id, destIdx);
                                    movedOne = true;
                                } catch (eMv) {}
                                break;
                            }
                        }
                        if (!movedOne) break;
                    }
                    // Enforce true Reggae Studio Signal Chain Order inside chain0:
                    // 0: Tune Smooth -> 1: Vocal Curve -> 2: Sustained Lead Vocal -> 3: Warm Tube -> 4: Dub Syndicate -> 5: Spring Parade
                    var desiredChainOrder = ["Tune Smooth", "Vocal Curve", "Sustained Lead Vocal", "Warm Tube", "Dub Syndicate", "Spring Parade"];
                    for (var targetPos = 0; targetPos < desiredChainOrder.length; targetPos++) {
                        var targetName = desiredChainOrder[targetPos];
                        var curChainCount = chain0.getcount("devices");
                        for (var cIdx = 0; cIdx < curChainCount; cIdx++) {
                            var cDev = new LiveAPI(chain0Path + " devices " + cIdx);
                            var cDevName = String(cDev.get("name") || "").replace(/^"+|"+$/g, "");
                            if (cDevName === targetName) {
                                if (cIdx !== targetPos) {
                                    try {
                                        liveSet.call("move_device", "id", cDev.id, "id", chain0.id, targetPos);
                                    } catch (eOrd) {}
                                }
                                break;
                            }
                        }
                    }
                }
            }

            // Step 3: Dial parameters on all vocal devices (whether top-level or inside Audio Effect Rack)
            forEachVocalDevice(trackPath, function(dev, devPath, isRack, isNested) {
                var dname = String(dev.get("name") || "").replace(/^"+|"+$/g, "");
                var dclass = String(dev.get("class_name") || "").replace(/^"+|"+$/g, "");
                var pCount = dev.getcount("parameters");

                if (isRack) {
                    try { dev.set("name", "Reggae Vocal Chain"); } catch (eRn) {}
                } else if (dclass === "Gate" || dname === "Vocal Gate" || dname === "Gate") {
                    // Studio Vocal Noise Gate calibrated for UNPROCESSED mobile MEMS capsule:
                    // Threshold 0.14 (~ -58 dB) with +16 dB S/C detector boost (S/C Gain = 0.85)
                    // so singing at -35 dB opens the gate effortlessly while room silence stays gated at -42 dB!
                    try { dev.set("name", "Vocal Gate"); } catch (eGn) {}
                    for (var pg = 0; pg < pCount; pg++) {
                        var parg = new LiveAPI(devPath + " parameters " + pg);
                        var pnameg = String(parg.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnameg === "Device On") parg.set("value", 1);
                        if (pnameg === "Threshold") parg.set("value", 0.14); // ~ -58 dB vocal gate threshold
                        if (pnameg === "Return") parg.set("value", 4.0);     // 4 dB hysteresis prevents chatter
                        if (pnameg === "Attack") parg.set("value", 1.5);     // 1.5 ms instant vocal opening
                        if (pnameg === "Hold") parg.set("value", 0.45);      // ~ 100 ms hold
                        if (pnameg === "Release") parg.set("value", 0.60);   // ~ 280 ms smooth decay
                        if (pnameg === "Floor") parg.set("value", -42.0);    // -42 dB gate attenuation floor
                        if (pnameg === "S/C Gain") parg.set("value", 0.85);  // Boost gate sidechain detector sensitivity
                        if (pnameg === "LookAhead") parg.set("value", 0);    // 0 ms lookahead for zero live latency
                        if (pnameg === "FlipMode") parg.set("value", 0);
                    }
                } else if (dname === "Tune Smooth" || dclass === "AutoShift") {
                    // Enable Auto Shift (Auto-Tune) ON by default to match phone dashboard (TUNE ON = 65%)
                    for (var pt = 0; pt < pCount; pt++) {
                        var part = new LiveAPI(devPath + " parameters " + pt);
                        var pnamet = String(part.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnamet === "Device On") part.set("value", 1);
                        if (pnamet === "Live") part.set("value", 1);
                        if (pnamet === "Quantizer On") part.set("value", 1);
                        if (pnamet === "Smooth On") part.set("value", 1);
                        if (pnamet === "Formant Follow") part.set("value", 0);
                        if (pnamet === "Strength") part.set("value", 0.65);
                        if (pnamet === "Smooth Time") part.set("value", 0.45);
                        if (pnamet === "LFO On") part.set("value", 0);
                        if (pnamet === "Vibrato Amt") part.set("value", 0.0);
                        if (pnamet === "Dry/Wet") part.set("value", 0.80);
                    }
                } else if (dname === "De-esser" || dname === "A Bit Warmer") {
                    // Turn off fast-attack expansion compressor & waveshaper saturator that cause modulation/chopping
                    var pOff = new LiveAPI(devPath + " parameters 0");
                    pOff.set("value", 0);
                } else if (dname === "Vocal Curve") {
                    // Warm up low-mids, smooth mids, gentle silk top end
                    for (var p = 0; p < pCount; p++) {
                        var par = new LiveAPI(devPath + " parameters " + p);
                        var pname = String(par.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pname === "Device On") par.set("value", 1);
                        if (pname === "Highpass On") par.set("value", 1);
                        if (pname === "Low Gain") par.set("value", 0.56);
                        if (pname === "Mid Gain") par.set("value", 0.52);
                        if (pname === "Mid Freq") par.set("value", 0.46);
                        if (pname === "High Gain") par.set("value", 0.46);
                    }
                } else if (dname === "Sustained Lead Vocal") {
                    // Smooth optical-style leveling with 0ms LookAhead, NO expansion gate, and NO fast-attack pumping
                    for (var pc = 0; pc < pCount; pc++) {
                        var parc = new LiveAPI(devPath + " parameters " + pc);
                        var pnamec = String(parc.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnamec === "Device On") parc.set("value", 1);
                        if (pnamec === "Threshold") parc.set("value", 0.52);
                        if (pnamec === "Ratio") parc.set("value", 0.45);
                        if (pnamec === "Expansion Ratio") parc.set("value", 1.0);
                        if (pnamec === "Attack") parc.set("value", 0.48);
                        if (pnamec === "Release") parc.set("value", 0.55);
                        if (pnamec === "Auto Release On/Off") parc.set("value", 1);
                        if (pnamec === "LookAhead") parc.set("value", 0);
                        if (pnamec === "Makeup") parc.set("value", 0);
                        if (pnamec === "Output") parc.set("value", 0.0);
                        if (pnamec === "S/C EQ On") parc.set("value", 0);
                    }
                } else if (dname === "Warm Tube") {
                    // Studio Kingston tube preamp warmth with zero envelope follower modulation
                    for (var p2 = 0; p2 < pCount; p2++) {
                        var par2 = new LiveAPI(devPath + " parameters " + p2);
                        var pname2 = String(par2.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pname2 === "Device On") par2.set("value", 1);
                        if (pname2 === "Dry/Wet") par2.set("value", 0.35);
                        if (pname2 === "Tone") par2.set("value", -0.15);
                        if (pname2 === "Drive") par2.set("value", 2.0);
                        if (pname2 === "Bias") par2.set("value", 0.18);
                        if (pname2 === "Tube Type") par2.set("value", 1);
                        if (pname2 === "Envelope") par2.set("value", 0.0);
                    }
                } else if (dname === "Dub Syndicate") {
                    // Authentic Reggae Space Echo: Dotted-8th skank sync, resonant dub bandpass filter, subtle tape wobble, ducking
                    for (var p3 = 0; p3 < pCount; p3++) {
                        var par3 = new LiveAPI(devPath + " parameters " + p3);
                        var pname3 = String(par3.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pname3 === "Device On") par3.set("value", 1);
                        if (pname3 === "Gate On") par3.set("value", 0);
                        if (pname3 === "Flt < Mod") par3.set("value", 0.0);
                        if (pname3 === "Dly < Mod") par3.set("value", 0.0);
                        if (pname3 === "Env Mix") par3.set("value", 0.0);
                        if (pname3 === "Wobble On") par3.set("value", 1);
                        if (pname3 === "Wobble Amt") par3.set("value", 0.08);
                        if (pname3 === "Noise On") par3.set("value", 0);
                        if (pname3 === "Repitch") par3.set("value", 0);
                        if (pname3 === "FB Invert") par3.set("value", 0);
                        if (pname3 === "Link") par3.set("value", 1);
                        if (pname3 === "Filter On") par3.set("value", 1);
                        if (pname3 === "LP Res") par3.set("value", 0.14);
                        if (pname3 === "HP Res") par3.set("value", 0.14);
                        if (pname3 === "LP Freq") par3.set("value", 0.56);
                        if (pname3 === "HP Freq") par3.set("value", 0.32);
                        if (pname3 === "Dry Wet") par3.set("value", 0.21);
                        if (pname3 === "Feedback") par3.set("value", 0.35);
                        if (pname3 === "Reverb Level") par3.set("value", 0.20);
                        if (pname3 === "Duck On") par3.set("value", 1);
                    }
                } else if (dname === "Spring Parade") {
                    // King Tubby Spring Reverb Tank (post-echo): warm spring convolution + vintage algorithm blend
                    for (var p4 = 0; p4 < pCount; p4++) {
                        var par4 = new LiveAPI(devPath + " parameters " + p4);
                        var pname4 = String(par4.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pname4 === "Device On") par4.set("value", 1);
                        if (pname4 === "Predelay Sync") par4.set("value", 0);
                        if (pname4 === "Predelay") par4.set("value", 0.015);
                        if (pname4 === "Predelay FB") par4.set("value", 0.0);
                        if (pname4 === "Decay") par4.set("value", 0.32);
                        if (pname4 === "Size") par4.set("value", 0.28);
                        if (pname4 === "Damping") par4.set("value", 0.35);
                        if (pname4 === "Blend") par4.set("value", 0.25);
                        if (pname4 === "Modulation") par4.set("value", 0.0);
                        if (pname4 === "Ti Tide") par4.set("value", 0.0);
                        if (pname4 === "Vintage") par4.set("value", 1);
                        if (pname4 === "Bass Mono") par4.set("value", 1);
                        if (pname4 === "Dry/Wet") par4.set("value", 0.18);
                    }
                }
            });
        }
    } catch (e) {}
}

var reggaeDialed = false;
var bangTick = 0;
var lastFxCmd = "";
var lastMacroVals = [-1, -1, -1, -1, -1, -1, -1, -1, -1];
var savedState = {
    echoMix: 0.35,
    echoFb: 0.35,
    dubFilter: 0.0,
    springWet: 0.30,
    tubeWarm: 0.41,
    reggaeTone: 0.50,
    vocalComp: 0.50,
    gateThresh: 0.10
};

var macroPollTick = 0;

function poll_fx_file() {
    try {
        var f = new File("/tmp/airmic_fx_cmd.txt", "read");
        if (f.isopen) {
            var line = f.readline();
            f.close();
            if (line && line.length > 0 && line !== lastFxCmd) {
                lastFxCmd = line;
                var parts = line.split(" ");
                if (parts.length >= 2) {
                    apply_vocal_fx(parts[0], parseFloat(parts[1]));
                }
            }
        }
        if ((++macroPollTick & 7) === 0) {
            poll_rack_macros();
        }
    } catch (e) {}
}

function poll_rack_macros() {
    if (!fxCache || !fxCache.macros || fxCache.macros.length < 9) return;
    for (var m = 1; m <= 8; m++) {
        var mp = fxCache.macros[m];
        if (!mp || !mp.id || parseInt(mp.id) === 0) continue;
        var curVal = parseFloat(mp.get("value"));
        if (isNaN(curVal)) continue;
        if (lastMacroVals[m] < 0) {
            lastMacroVals[m] = curVal;
            continue;
        }
        if (Math.abs(curVal - lastMacroVals[m]) > 0.35) {
            lastMacroVals[m] = curVal;
            var norm = Math.max(0.0, Math.min(1.0, curVal / 127.0));
            apply_macro_index(m, norm, false);
        }
    }
}

function set_macro_knob(mIdx, norm) {
    if (!fxCache || !fxCache.macros || !fxCache.macros[mIdx]) return;
    var v127 = Math.max(0.0, Math.min(127.0, norm * 127.0));
    lastMacroVals[mIdx] = v127;
    try { fxCache.macros[mIdx].set("value", v127); } catch (eM) {}
}

function apply_macro_index(mIdx, norm, updateKnob) {
    var c = fxCache;
    if (!c) return;
    norm = Math.max(0.0, Math.min(1.0, norm));
    if (updateKnob) set_macro_knob(mIdx, norm);

    if (mIdx === 1) savedState.echoMix = norm;
    else if (mIdx === 2) savedState.echoFb = norm;
    else if (mIdx === 3) savedState.dubFilter = norm;
    else if (mIdx === 4) savedState.springWet = norm;
    else if (mIdx === 5) savedState.tubeWarm = norm;
    else if (mIdx === 6) savedState.reggaeTone = norm;
    else if (mIdx === 7) savedState.vocalComp = norm;
    else if (mIdx === 8) savedState.gateThresh = norm;

    // When Reggae Vocal Chain is natively mapped via <KeyMidi>, setting the Macro knob
    // drives all child parameters along their exact MidiControllerRange in Ableton's C++ engine.
    if (c.macros && c.macros[mIdx] && c.macros[mIdx].id && parseInt(c.macros[mIdx].id) !== 0) {
        return;
    }

    if (mIdx === 1) {
        // Macro 1: Dub Echo Mix
        savedState.echoMix = norm;
        if (c.echoOn) c.echoOn.set("value", norm > 0.01 ? 1 : 0);
        if (c.echoWet) c.echoWet.set("value", norm * 0.60);
    } else if (mIdx === 2) {
        // Macro 2: Echo Feedback
        savedState.echoFb = norm;
        if (c.echoFb) c.echoFb.set("value", 0.12 + norm * 0.76);
        if (c.echoRevLvl) c.echoRevLvl.set("value", 0.08 + norm * 0.35);
        if (c.echoWobbleAmt) c.echoWobbleAmt.set("value", 0.04 + norm * 0.18);
    } else if (mIdx === 3) {
        // Macro 3: Dub Filter (King Tubby Resonant High-Pass / Bandpass Sweep)
        savedState.dubFilter = norm;
        if (c.echoHpFreq) c.echoHpFreq.set("value", 0.20 + norm * 0.42);
        if (c.echoLpFreq) c.echoLpFreq.set("value", 0.38 + norm * 0.38);
        var res = 0.10 + Math.abs(norm - 0.5) * 0.32;
        if (c.echoHpRes) c.echoHpRes.set("value", res);
        if (c.echoLpRes) c.echoLpRes.set("value", res);
    } else if (mIdx === 4) {
        // Macro 4: Spring Reverb
        savedState.springWet = norm;
        if (c.springOn) c.springOn.set("value", norm > 0.01 ? 1 : 0);
        if (c.springWet) c.springWet.set("value", norm * 0.55);
        if (c.springDecay) c.springDecay.set("value", 0.18 + norm * 0.42);
    } else if (mIdx === 5) {
        // Macro 5: Tube Warmth
        savedState.tubeWarm = norm;
        if (c.tubeOn) c.tubeOn.set("value", norm > 0.01 ? 1 : 0);
        if (c.tubeWet) c.tubeWet.set("value", norm * 0.65);
        if (c.tubeDrive) c.tubeDrive.set("value", -1.5 + norm * 9.0);
        if (c.tubeBias) c.tubeBias.set("value", 0.08 + norm * 0.28);
    } else if (mIdx === 6) {
        // Macro 6: Reggae Tone (Channel EQ Roots Chest & Silky Top)
        savedState.reggaeTone = norm;
        if (c.eqOn) c.eqOn.set("value", 1);
        if (c.eqLow) c.eqLow.set("value", 0.46 + norm * 0.22);
        if (c.eqMid) c.eqMid.set("value", 0.48 + norm * 0.12);
        if (c.eqMidFreq) c.eqMidFreq.set("value", 0.46);
        if (c.eqHigh) c.eqHigh.set("value", 0.56 - norm * 0.18);
    } else if (mIdx === 7) {
        // Macro 7: Vocal Comp (Optical Leveling)
        savedState.vocalComp = norm;
        if (c.compOn) c.compOn.set("value", norm > 0.01 ? 1 : 0);
        if (c.compThresh) c.compThresh.set("value", 0.72 - norm * 0.36);
        if (c.compRatio) c.compRatio.set("value", 0.30 + norm * 0.35);
    } else if (mIdx === 8) {
        // Macro 8: Gate Thresh (Studio Noise Gate inside Rack)
        savedState.gateThresh = norm;
        if (c.gateOn) c.gateOn.set("value", norm > 0.01 ? 1 : 0);
        if (c.gateScGain) c.gateScGain.set("value", 0.85);
        if (c.gateFloor) c.gateFloor.set("value", -20.0);
    }
}

function bang() {
    if (!reggaeDialed) {
        reggaeDialed = true;
        dial_reggae_vocal();
        fxCache = buildFxCache();
        scan_and_align(false);
    }
    if ((++bangTick % 20) === 0) {
        scan_and_align(false);
    }
    poll_fx_file();
}

function fx_ctl(cmd, val) {
    apply_vocal_fx(String(cmd), parseFloat(val));
}

// Cached LOM parameter map for 0ms instant FX triggers & bidirectional 8-Macro sync
var fxCache = null;

function buildFxCache() {
    var cache = {
        macros: [null, null, null, null, null, null, null, null, null],
        gateOn: null,
        gateThresh: null,
        gateFloor: null,
        gateScGain: null,
        pitchOn: null,
        pitchLive: null,
        pitchQuant: null,
        pitchStrength: null,
        pitchSmooth: null,
        pitchWet: null,
        eqOn: null,
        eqLow: null,
        eqMid: null,
        eqMidFreq: null,
        eqHigh: null,
        compOn: null,
        compThresh: null,
        compRatio: null,
        tubeOn: null,
        tubeWet: null,
        tubeDrive: null,
        tubeBias: null,
        echoOn: null,
        echoWet: null,
        echoFb: null,
        echoDuck: null,
        echoRevLvl: null,
        echoHpFreq: null,
        echoLpFreq: null,
        echoHpRes: null,
        echoLpRes: null,
        echoWobbleAmt: null,
        echoLSyncMode: null,
        echoL16th: null,
        echoLSynced: null,
        springOn: null,
        springWet: null,
        springDecay: null,
        warmOnList: [],
        rackOn: null
    };
    try {
        var liveSet = new LiveAPI("live_set");
        if (!liveSet || !liveSet.id) return null;
        var trackCount = liveSet.getcount("tracks");
        for (var t = 0; t < trackCount; t++) {
            var trackPath = "live_set tracks " + t;
            var track = new LiveAPI(trackPath);
            var tname = String(track.get("name") || "").replace(/^"+|"+$/g, "");
            if (tname.indexOf("Vocal") === -1 && t !== 3) continue;

            forEachVocalDevice(trackPath, function(dev, devPath, isRack, isNested) {
                var dname = String(dev.get("name") || "").replace(/^"+|"+$/g, "");
                var dclass = String(dev.get("class_name") || "").replace(/^"+|"+$/g, "");
                var pCount = dev.getcount("parameters");

                if (isRack) {
                    cache.rackOn = new LiveAPI(devPath + " parameters 0");
                    for (var m = 1; m <= 8; m++) {
                        cache.macros[m] = new LiveAPI(devPath + " parameters " + m);
                    }
                } else if (dclass === "Gate" || dname === "Vocal Gate" || dname === "Gate") {
                    cache.gateOn = new LiveAPI(devPath + " parameters 0");
                    for (var pg = 0; pg < pCount; pg++) {
                        var parg = new LiveAPI(devPath + " parameters " + pg);
                        var png = String(parg.get("name") || "").replace(/^"+|"+$/g, "");
                        if (png === "Threshold") cache.gateThresh = parg;
                        else if (png === "Floor") cache.gateFloor = parg;
                        else if (png === "S/C Gain") cache.gateScGain = parg;
                    }
                } else if (dname === "Tune Smooth" || dclass === "AutoShift") {
                    cache.pitchOn = new LiveAPI(devPath + " parameters 0");
                    for (var pt = 0; pt < pCount; pt++) {
                        var part = new LiveAPI(devPath + " parameters " + pt);
                        var pnt = String(part.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnt === "Live") cache.pitchLive = part;
                        else if (pnt === "Quantizer On") cache.pitchQuant = part;
                        else if (pnt === "Strength") cache.pitchStrength = part;
                        else if (pnt === "Smooth Time") cache.pitchSmooth = part;
                        else if (pnt === "Dry/Wet") cache.pitchWet = part;
                    }
                } else if (dname === "Vocal Curve" || dclass === "ChannelEq") {
                    cache.eqOn = new LiveAPI(devPath + " parameters 0");
                    cache.warmOnList.push(cache.eqOn);
                    for (var pq = 0; pq < pCount; pq++) {
                        var parq = new LiveAPI(devPath + " parameters " + pq);
                        var pnq = String(parq.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnq === "Low Gain") cache.eqLow = parq;
                        else if (pnq === "Mid Gain") cache.eqMid = parq;
                        else if (pnq === "Mid Freq") cache.eqMidFreq = parq;
                        else if (pnq === "High Gain") cache.eqHigh = parq;
                    }
                } else if (dname === "Sustained Lead Vocal" || dclass === "Compressor2") {
                    cache.compOn = new LiveAPI(devPath + " parameters 0");
                    for (var pc = 0; pc < pCount; pc++) {
                        var parc = new LiveAPI(devPath + " parameters " + pc);
                        var pnc = String(parc.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnc === "Threshold") cache.compThresh = parc;
                        else if (pnc === "Ratio") cache.compRatio = parc;
                    }
                } else if (dname === "Warm Tube" || dclass === "Tube") {
                    cache.tubeOn = new LiveAPI(devPath + " parameters 0");
                    cache.warmOnList.push(cache.tubeOn);
                    for (var pw = 0; pw < pCount; pw++) {
                        var parw = new LiveAPI(devPath + " parameters " + pw);
                        var pnw = String(parw.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnw === "Dry/Wet") cache.tubeWet = parw;
                        else if (pnw === "Drive") cache.tubeDrive = parw;
                        else if (pnw === "Bias") cache.tubeBias = parw;
                    }
                } else if (dname === "Dub Syndicate" || dclass === "Echo") {
                    cache.echoOn = new LiveAPI(devPath + " parameters 0");
                    for (var pe = 0; pe < pCount; pe++) {
                        var pare = new LiveAPI(devPath + " parameters " + pe);
                        var pne = String(pare.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pne === "Dry Wet") cache.echoWet = pare;
                        else if (pne === "Feedback") cache.echoFb = pare;
                        else if (pne === "Duck On") cache.echoDuck = pare;
                        else if (pne === "Reverb Level") cache.echoRevLvl = pare;
                        else if (pne === "HP Freq") cache.echoHpFreq = pare;
                        else if (pne === "LP Freq") cache.echoLpFreq = pare;
                        else if (pne === "HP Res") cache.echoHpRes = pare;
                        else if (pne === "LP Res") cache.echoLpRes = pare;
                        else if (pne === "Wobble Amt") cache.echoWobbleAmt = pare;
                        else if (pne === "L Sync Mode") cache.echoLSyncMode = pare;
                        else if (pne === "L 16th") cache.echoL16th = pare;
                        else if (pne === "L Synced") cache.echoLSynced = pare;
                    }
                } else if (dname === "Spring Parade" || dclass === "Hybrid") {
                    cache.springOn = new LiveAPI(devPath + " parameters 0");
                    for (var ps = 0; ps < pCount; ps++) {
                        var pars = new LiveAPI(devPath + " parameters " + ps);
                        var pns = String(pars.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pns === "Dry/Wet") cache.springWet = pars;
                        else if (pns === "Decay") cache.springDecay = pars;
                    }
                }
            });
        }
    } catch (e) {}
    return cache;
}

function apply_vocal_fx(cmd, val) {
    try {
        if (cmd === "status_led") {
            set_status_led(val > 0.5);
            return;
        }
        if (cmd === "dial_vocal") {
            lock_jitter_release_fifo();
            set_status_led(true);
            dial_reggae_vocal();
            fxCache = buildFxCache();
            return;
        }

        if (!fxCache || !fxCache.echoWet || parseInt(fxCache.echoWet.id) === 0) {
            fxCache = buildFxCache();
        }
        var c = fxCache;
        if (c && c.echoWet && parseInt(c.echoWet.id) !== 0) {
            // Direct 1-to-1 Macro & Phone Reggae Controls
            if (cmd === "echo_mix") {
                apply_macro_index(1, val, true);
                return;
            } else if (cmd === "echo_fb") {
                apply_macro_index(2, val, true);
                return;
            } else if (cmd === "dub_filter") {
                apply_macro_index(3, val, true);
                return;
            } else if (cmd === "spring_wet") {
                apply_macro_index(4, val, true);
                return;
            } else if (cmd === "tube_warm") {
                apply_macro_index(5, val, true);
                return;
            } else if (cmd === "reggae_tone") {
                apply_macro_index(6, val, true);
                return;
            } else if (cmd === "vocal_comp") {
                apply_macro_index(7, val, true);
                return;
            } else if (cmd === "gate_thresh") {
                apply_macro_index(8, val, true);
                return;
            } else if (cmd === "space_mix") {
                var amt = Math.max(0.0, Math.min(1.0, val));
                apply_macro_index(1, amt, true);
                apply_macro_index(4, amt * 0.85, true);
                return;
            } else if (cmd === "dub_throw") {
                // Momentary Space Echo Dub Throw Pad
                var isHeld = val > 0.5;
                if (isHeld) {
                    if (c.echoOn) c.echoOn.set("value", 1);
                    if (c.echoWet) c.echoWet.set("value", 0.52);
                    if (c.echoFb) c.echoFb.set("value", 0.74);
                    if (c.echoRevLvl) c.echoRevLvl.set("value", 0.36);
                    if (c.echoDuck) c.echoDuck.set("value", 1);
                    set_macro_knob(1, 0.85);
                    set_macro_knob(2, 0.82);
                } else {
                    apply_macro_index(1, savedState.echoMix, true);
                    apply_macro_index(2, savedState.echoFb, true);
                }
                return;
            } else if (cmd === "spring_splash") {
                // Momentary King Tubby Spring Reverb Tank Splash Pad
                var isSplash = val > 0.5;
                if (isSplash) {
                    if (c.springOn) c.springOn.set("value", 1);
                    if (c.springWet) c.springWet.set("value", 0.58);
                    if (c.springDecay) c.springDecay.set("value", 0.65);
                    set_macro_knob(4, 0.92);
                } else {
                    apply_macro_index(4, savedState.springWet, true);
                }
                return;
            } else if (cmd === "dub_horn") {
                // Momentary Sound System Horn / Megaphone Bandpass Vocal Effect via Native Macro 3 (Dub Filter) + Macro 5 (Tube Warmth)
                var isHorn = val > 0.5;
                if (isHorn) {
                    set_macro_knob(3, 0.72);
                    set_macro_knob(5, 0.78);
                } else {
                    apply_macro_index(3, savedState.dubFilter, true);
                    apply_macro_index(5, savedState.tubeWarm, true);
                }
                return;
            } else if (cmd === "echo_rate") {
                // 0 = 1/8D Dotted Skank, 1 = 1/4 Roots, 2 = 1/8T Steppas Triplet
                var mode = Math.round(val);
                if (mode === 0) {
                    if (c.echoLSyncMode) c.echoLSyncMode.set("value", 1); // Dotted
                    if (c.echoLSynced) c.echoLSynced.set("value", -4);    // 1/8
                } else if (mode === 1) {
                    if (c.echoLSyncMode) c.echoLSyncMode.set("value", 0); // Straight
                    if (c.echoLSynced) c.echoLSynced.set("value", -3);    // 1/4
                } else if (mode === 2) {
                    if (c.echoLSyncMode) c.echoLSyncMode.set("value", 2); // Triplet
                    if (c.echoLSynced) c.echoLSynced.set("value", -4);    // 1/8T
                }
                return;
            } else if (cmd === "pitch_on" && c.pitchOn) {
                var pOn = val > 0.5 ? 1 : 0;
                c.pitchOn.set("value", pOn);
                if (pOn) {
                    if (c.pitchLive) c.pitchLive.set("value", 1);
                    if (c.pitchQuant) c.pitchQuant.set("value", 1);
                    if (c.pitchStrength) c.pitchStrength.set("value", 0.65);
                    if (c.pitchSmooth) c.pitchSmooth.set("value", 0.45);
                    if (c.pitchWet) c.pitchWet.set("value", 0.80);
                }
                return;
            } else if (cmd === "tune_amt" && c.pitchStrength) {
                var tAmt = Math.max(0.0, Math.min(1.0, val));
                if (c.pitchOn) c.pitchOn.set("value", tAmt > 0.02 ? 1 : 0);
                if (c.pitchLive) c.pitchLive.set("value", 1);
                if (c.pitchQuant) c.pitchQuant.set("value", 1);
                c.pitchStrength.set("value", tAmt);
                if (c.pitchSmooth) c.pitchSmooth.set("value", Math.max(0.05, 0.85 - (tAmt * 0.70)));
                if (c.pitchWet) c.pitchWet.set("value", Math.min(1.0, 0.40 + (tAmt * 0.60)));
                return;
            } else if (cmd === "gate_on" && c.gateOn) {
                c.gateOn.set("value", val > 0.5 ? 1 : 0);
                return;
            } else if (cmd === "echo_on" && c.echoOn) {
                c.echoOn.set("value", val > 0.5 ? 1 : 0);
                return;
            } else if (cmd === "spring_on" && c.springOn) {
                c.springOn.set("value", val > 0.5 ? 1 : 0);
                return;
            } else if (cmd === "warm_on" && c.warmOnList && c.warmOnList.length > 0) {
                var wVal = val > 0.5 ? 1 : 0;
                for (var wi = 0; wi < c.warmOnList.length; wi++) {
                    c.warmOnList[wi].set("value", wVal);
                }
                return;
            } else if (cmd === "bypass_all") {
                var fxOn = val > 0.5 ? 0 : 1;
                if (c.rackOn) c.rackOn.set("value", fxOn);
                if (c.gateOn) c.gateOn.set("value", fxOn);
                return;
            }
        }

        var liveSet = new LiveAPI("live_set");
        if (!liveSet || !liveSet.id) return;
        var trackCount = liveSet.getcount("tracks");
        // Multi-Track Mixer Controls (trk_vol_<idx>, trk_pan_<idx>, trk_mute_<idx>, trk_solo_<idx>, master_vol)
        if (cmd === "master_vol") {
            var mVol = new LiveAPI("live_set master_track mixer_device volume");
            if (mVol && mVol.id) mVol.set("value", Math.max(0.0, Math.min(1.0, val)));
            return;
        }
        if (cmd.indexOf("trk_") === 0) {
            var parts = cmd.split("_");
            if (parts.length >= 3) {
                var action = parts[1];
                var tIdx = parseInt(parts[2]);
                if (!isNaN(tIdx) && tIdx >= 0 && tIdx < trackCount) {
                    var mTrackPath = "live_set tracks " + tIdx;
                    var mTrack = new LiveAPI(mTrackPath);
                    if (mTrack && mTrack.id) {
                        if (action === "vol") {
                            var vPar = new LiveAPI(mTrackPath + " mixer_device volume");
                            if (vPar && vPar.id) vPar.set("value", Math.max(0.0, Math.min(1.0, val)));
                        } else if (action === "pan") {
                            var pPar = new LiveAPI(mTrackPath + " mixer_device panning");
                            if (pPar && pPar.id) pPar.set("value", Math.max(-1.0, Math.min(1.0, val)));
                        } else if (action === "mute") {
                            mTrack.set("mute", val > 0.5 ? 1 : 0);
                        } else if (action === "solo") {
                            mTrack.set("solo", val > 0.5 ? 1 : 0);
                        }
                    }
                }
                return;
            }
        }

        for (var t = 0; t < trackCount; t++) {
            var trackPath = "live_set tracks " + t;
            var track = new LiveAPI(trackPath);
            var tname = String(track.get("name") || "").replace(/^"+|"+$/g, "");
            if (tname.indexOf("Guitar") !== -1) {
                // Remove any Gate accidentally placed on a Guitar track
                var gTopCount = track.getcount("devices");
                for (var gDel = gTopCount - 1; gDel >= 0; gDel--) {
                    var gd = new LiveAPI(trackPath + " devices " + gDel);
                    var gdClass = String(gd.get("class_name") || "").replace(/^"+|"+$/g, "");
                    if (gdClass === "Gate") {
                        try { track.call("delete_device", gDel); } catch (eGd) {}
                    }
                }
                continue;
            }
            if (tname.indexOf("Vocal") === -1 && t !== 3) continue;

            forEachVocalDevice(trackPath, function(dev, devPath, isRack, isNested) {
                var dname = String(dev.get("name") || "").replace(/^"+|"+$/g, "");
                var dclass = String(dev.get("class_name") || "").replace(/^"+|"+$/g, "");
                var pCount = dev.getcount("parameters");

                if (cmd === "bypass_all") {
                    // val = 1 means DRY (all FX off), val = 0 means FX ON
                    var fxOn = val > 0.5 ? 0 : 1;
                    if (isRack) {
                        var pRackOn = new LiveAPI(devPath + " parameters 0");
                        pRackOn.set("value", fxOn);
                    } else if (!isNested && dname !== "Vocal Presence" && dname !== "Ambience") {
                        var pDevOn = new LiveAPI(devPath + " parameters 0");
                        pDevOn.set("value", fxOn);
                    }
                } else if (cmd === "gate_on" && (dclass === "Gate" || dname === "Vocal Gate" || dname === "Gate")) {
                    var pGateOn = new LiveAPI(devPath + " parameters 0");
                    pGateOn.set("value", val > 0.5 ? 1 : 0);
                } else if (cmd === "gate_thresh" && (dclass === "Gate" || dname === "Vocal Gate" || dname === "Gate")) {
                    var gAmt = Math.max(0.0, Math.min(1.0, val));
                    for (var pgt = 0; pgt < pCount; pgt++) {
                        var pargt = new LiveAPI(devPath + " parameters " + pgt);
                        var pnamegt = String(pargt.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnamegt === "Device On") pargt.set("value", gAmt > 0.01 ? 1 : 0);
                        if (pnamegt === "Threshold") pargt.set("value", gAmt);
                        if (pnamegt === "S/C Gain") pargt.set("value", 0.85);
                        if (pnamegt === "Floor") pargt.set("value", -42.0);
                    }
                } else if (cmd === "pitch_on" && (dname === "Tune Smooth" || dclass === "AutoShift")) {
                    var pPitchOn = new LiveAPI(devPath + " parameters 0");
                    pPitchOn.set("value", val > 0.5 ? 1 : 0);
                } else if (cmd === "tune_amt" && (dname === "Tune Smooth" || dclass === "AutoShift")) {
                    // Smooth 0.0 to 1.0 slider controlling Auto-Tune pitch correction strength, speed, and wet mix
                    var tAmt = Math.max(0.0, Math.min(1.0, val));
                    for (var pta = 0; pta < pCount; pta++) {
                        var parta = new LiveAPI(devPath + " parameters " + pta);
                        var pnameta = String(parta.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnameta === "Device On") parta.set("value", tAmt > 0.02 ? 1 : 0);
                        if (pnameta === "Live") parta.set("value", 1);
                        if (pnameta === "Quantizer On") parta.set("value", 1);
                        if (pnameta === "Strength") parta.set("value", tAmt);
                        if (pnameta === "Smooth Time") parta.set("value", Math.max(0.05, 0.85 - (tAmt * 0.70)));
                        if (pnameta === "Dry/Wet") parta.set("value", Math.min(1.0, 0.40 + (tAmt * 0.60)));
                    }
                } else if (cmd === "echo_on" && dname === "Dub Syndicate") {
                    var pEchoOn = new LiveAPI(devPath + " parameters 0");
                    pEchoOn.set("value", val > 0.5 ? 1 : 0);
                } else if (cmd === "spring_on" && dname === "Spring Parade") {
                    var pSprOn = new LiveAPI(devPath + " parameters 0");
                    pSprOn.set("value", val > 0.5 ? 1 : 0);
                } else if (cmd === "warm_on" && (dname === "Warm Tube" || dname === "A Bit Warmer" || dname === "Vocal Curve")) {
                    var pWarmOn = new LiveAPI(devPath + " parameters 0");
                    pWarmOn.set("value", val > 0.5 ? 1 : 0);
                } else if (cmd === "dub_throw" && dname === "Dub Syndicate") {
                    // Tamed Dub Lift: smooth musical lift (Wet 36%, Feedback 52%) so it never runs away
                    var isHeld = val > 0.5;
                    for (var p = 0; p < pCount; p++) {
                        var par = new LiveAPI(devPath + " parameters " + p);
                        var pname = String(par.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pname === "Device On" && isHeld) par.set("value", 1);
                        if (pname === "Dry Wet") par.set("value", isHeld ? 0.36 : 0.18);
                        if (pname === "Feedback") par.set("value", isHeld ? 0.52 : 0.32);
                        if (pname === "Duck On") par.set("value", 1);
                    }
                } else if (cmd === "space_mix") {
                    // Smooth single-slider control (0.0 to 1.0) over both Dub Echo & Spring Reverb wet mix
                    var amt = Math.max(0.0, Math.min(1.0, val));
                    if (dname === "Dub Syndicate") {
                        for (var pe2 = 0; pe2 < pCount; pe2++) {
                            var pare2 = new LiveAPI(devPath + " parameters " + pe2);
                            var pnamee2 = String(pare2.get("name") || "").replace(/^"+|"+$/g, "");
                            if (pnamee2 === "Device On") pare2.set("value", amt > 0.01 ? 1 : 0);
                            if (pnamee2 === "Dry Wet") pare2.set("value", amt * 0.40);
                            if (pnamee2 === "Feedback") pare2.set("value", 0.25 + amt * 0.28);
                        }
                    } else if (dname === "Spring Parade") {
                        for (var ps2 = 0; ps2 < pCount; ps2++) {
                            var pars2 = new LiveAPI(devPath + " parameters " + ps2);
                            var pnames2 = String(pars2.get("name") || "").replace(/^"+|"+$/g, "");
                            if (pnames2 === "Device On") pars2.set("value", amt > 0.01 ? 1 : 0);
                            if (pnames2 === "Dry/Wet") pars2.set("value", amt * 0.32);
                        }
                    }
                } else if (cmd === "echo_wet" && dname === "Dub Syndicate") {
                    for (var pe = 0; pe < pCount; pe++) {
                        var pare = new LiveAPI(devPath + " parameters " + pe);
                        var pnamee = String(pare.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnamee === "Dry Wet") pare.set("value", Math.max(0.0, Math.min(1.0, val)));
                    }
                } else if (cmd === "spring_wet" && dname === "Spring Parade") {
                    for (var ps = 0; ps < pCount; ps++) {
                        var pars = new LiveAPI(devPath + " parameters " + ps);
                        var pnames = String(pars.get("name") || "").replace(/^"+|"+$/g, "");
                        if (pnames === "Dry/Wet") pars.set("value", Math.max(0.0, Math.min(1.0, val)));
                    }
                }
            });
        }
    } catch (e) {}
}
dial_reggae_vocal();

function isTrackRoutedFromThisDevice(track, sourceTrackName, sourceTrackId) {
    try {
        if (String(track.id) === String(sourceTrackId)) return true;
        var rt = track.get("input_routing_type");
        // In LiveAPI, input_routing_type returns a JSON string or display_name matching the source track name
        var rtStr = typeof rt === "object" ? JSON.stringify(rt) : String(rt || "");
        if (sourceTrackName && rtStr.indexOf(sourceTrackName) !== -1) {
            return true;
        }
    } catch (e) {}
    return false;
}

function scan_and_align(forceRealign) {
    if (latencyCompMs <= 0.5) return;
    try {
        var liveSet = new LiveAPI("live_set");
        if (!liveSet || !liveSet.id || parseInt(liveSet.id) === 0) return;

        var myTrack = new LiveAPI("this_device canonical_parent");
        var myTrackId = myTrack && myTrack.id ? String(myTrack.id) : "";
        var myTrackName = myTrack ? String(myTrack.get("name") || "") : "";
        // Strip surrounding quotes if LiveAPI returns a quoted string
        myTrackName = myTrackName.replace(/^"+|"+$/g, "");

        var tempo = parseFloat(liveSet.get("tempo")) || 120.0;
        var offsetBeats = (latencyCompMs / 1000.0) * (tempo / 60.0);

        var trackCount = liveSet.getcount("tracks");
        for (var t = 0; t < trackCount; t++) {
            var track = new LiveAPI("live_set tracks " + t);
            if (!track || parseInt(track.get("has_audio_input")) !== 1) continue;
            // ONLY touch tracks that explicitly take their audio input from the LiveAirMic track!
            if (!isTrackRoutedFromThisDevice(track, myTrackName, myTrackId)) continue;

            var slotCount = track.getcount("clip_slots");
            for (var s = 0; s < slotCount; s++) {
                var slot = new LiveAPI("live_set tracks " + t + " clip_slots " + s);
                if (!slot || parseInt(slot.get("has_clip")) !== 1) continue;

                var clip = new LiveAPI("live_set tracks " + t + " clip_slots " + s + " clip");
                if (!clip || !clip.id || parseInt(clip.id) === 0) continue;
                if (parseInt(clip.get("is_audio_clip")) !== 1) continue;
                if (parseInt(clip.get("is_recording")) === 1) continue;

                var cid = String(clip.id);
                // CRITICAL: Switch any recorded vocal clip out of Ableton's default "Beats" Warp Mode (0),
                // which slices sustained vocals into 16th-note transient grains and loops them forward/back
                // like a spinning fan whenever tempo or markers change! Use Complex mode (4) instead.
                try {
                    if (parseInt(clip.get("warping")) === 1 && parseInt(clip.get("warp_mode")) === 0) {
                        clip.set("warp_mode", 4);
                    }
                } catch (eWarp) {}

                var curStart = parseFloat(clip.get("start_marker")) || 0.0;
                var curEnd = parseFloat(clip.get("end_marker")) || 4.0;
                var curLoopStart = parseFloat(clip.get("loop_start")) || 0.0;
                var curLoopEnd = parseFloat(clip.get("loop_end")) || curEnd;

                // Determine the un-shifted beat boundaries (e.g. Bar 1 = 0.0, Bar 3 = 8.0, etc.)
                var baseStart = Math.round(curStart - (alignedClipIds[cid] ? offsetBeats : 0.0));
                if (Math.abs(curStart - Math.round(curStart)) < 0.005) {
                    baseStart = Math.round(curStart);
                } else if (Math.abs((curStart - offsetBeats) - Math.round(curStart - offsetBeats)) < 0.02) {
                    baseStart = Math.round(curStart - offsetBeats);
                } else {
                    // Check if previously shifted by an older offset (e.g. 85ms)
                    baseStart = Math.floor(curStart + 0.05);
                }
                var rawDuration = Math.round((curEnd - curStart));
                if (rawDuration < 1) rawDuration = Math.max(1, Math.round(curEnd - baseStart));
                var baseEnd = baseStart + rawDuration;

                var targetStart = baseStart + offsetBeats;
                var targetEnd = baseEnd + offsetBeats;
                var isUnshifted = Math.abs(curStart - baseStart) < 0.005;

                if (forceRealign || (!alignedClipIds[cid] && isUnshifted)) {
                    alignedClipIds[cid] = true;
                    var isLooping = parseInt(clip.get("looping")) === 1;

                    if (!isLooping) {
                        clip.set("looping", 1);
                        clip.set("loop_end", targetEnd);
                        clip.set("end_marker", targetEnd);
                        clip.set("loop_start", targetStart);
                        clip.set("start_marker", targetStart);
                        clip.set("looping", 0);
                    } else {
                        clip.set("loop_end", targetEnd);
                        clip.set("end_marker", targetEnd);
                        clip.set("loop_start", targetStart);
                        clip.set("start_marker", targetStart);
                    }
                    try {
                        var fc = new File("/tmp/airmic_clip_diag.txt", "write");
                        if (fc.isopen) {
                            fc.writeline("Aligned clip " + cid + " on track " + t + " slot " + s + ": curStart=" + curStart + " -> targetStart=" + targetStart + " (baseStart=" + baseStart + ", offsetBeats=" + offsetBeats + ", latencyCompMs=" + latencyCompMs + ")");
                            fc.close();
                        }
                    } catch (eLog) {}
                }
            }
        }
    } catch (e) {
        // Ignore transient LOM errors while Live Set is changing
    }
}
// Note: autoAlignTask disabled — we fix latency in the real-time audio path rather than shifting clip markers.
