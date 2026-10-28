# Copyright 2026 Michael Lovci
# SPDX-License-Identifier: Apache-2.0
"""
Generator for LiveAirMic Max for Live device (.amxd and .maxpat).
Creates a fully functional M4L Audio Effect device with OSC communication,
live transport synchronization, VU metering, and presentation UI.
"""

import json
import struct
from pathlib import Path

def generate_patcher():
    patcher = {
        "patcher": {
            "fileversion": 1,
            "appversion": {
                "major": 8,
                "minor": 5,
                "revision": 7,
                "architecture": "x64",
                "modernui": 1
            },
            "classnamespace": "box",
            "rect": [100.0, 100.0, 850.0, 680.0],
            "openrect": [0.0, 0.0, 346.0, 169.0],
            "bglocked": 0,
            "openinpresentation": 1,
            "default_fontsize": 11.0,
            "default_fontface": 0,
            "default_fontname": "Ableton Sans Medium",
            "locked_bgcolor": [0.11, 0.13, 0.17, 1.0],
            "editing_bgcolor": [0.11, 0.13, 0.17, 1.0],
            "gridonopen": 1,
            "gridsize": [10.0, 10.0],
            "gridsnaponopen": 1,
            "objectsnaponopen": 1,
            "statusbarvisible": 2,
            "toolbarvisible": 1,
            "lefttoolbarpinned": 0,
            "toptoolbarpinned": 0,
            "righttoolbarpinned": 0,
            "bottomtoolbarpinned": 0,
            "toolbars_unpinned_last_save": 0,
            "tallnewobj": 0,
            "boxanimatetime": 200,
            "enablehscroll": 1,
            "enablevscroll": 1,
            "devicewidth": 346.0,
            "description": "LiveAirMic Wireless Studio Microphone Receiver for Ableton Live",
            "digest": "High-Speed Mobile Mic Bridge",
            "tags": "Audio Effect, Utility, Network, Wireless",
            "boxes": [
                # --- DIRECT JITTER-TO-MSP AUDIO STREAM (jit.fill -> jit.matrix -> jit.release~) ---
                {
                    "box": {
                        "id": "obj-plugin",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 2,
                        "outlettype": ["signal", "signal"],
                        "patching_rect": [30.0, 20.0, 50.0, 21.0],
                        "text": "plugin~"
                    }
                },
                {
                    "box": {
                        "id": "obj-jit-fill",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 2,
                        "outlettype": ["bang", ""],
                        "patching_rect": [100.0, 20.0, 120.0, 21.0],
                        "text": "jit.fill airmic_mat 0"
                    }
                },
                {
                    "box": {
                        "id": "obj-jit-mat",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 2,
                        "outlettype": ["jit_matrix", ""],
                        "patching_rect": [100.0, 48.0, 195.0, 21.0],
                        "text": "jit.matrix airmic_mat 1 float32 128"
                    }
                },
                {
                    "box": {
                        "id": "obj-jit-rel",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 2,
                        "outlettype": ["signal", ""],
                        "patching_rect": [100.0, 76.0, 185.0, 21.0],
                        "text": "jit.release~ 1 @mode 0 @latency 12."
                    }
                },
                {
                    "box": {
                        "id": "obj-msg-qsize",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [300.0, 212.0, 100.0, 21.0],
                        "text": "maxqueuesize 64"
                    }
                },
                {
                    "box": {
                        "id": "obj-bitsafe",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": ["signal"],
                        "patching_rect": [100.0, 100.0, 55.0, 21.0],
                        "text": "bitsafe~"
                    }
                },
                {
                    "box": {
                        "id": "obj-clip",
                        "maxclass": "newobj",
                        "numinlets": 3,
                        "numoutlets": 1,
                        "outlettype": ["signal"],
                        "patching_rect": [160.0, 100.0, 95.0, 21.0],
                        "text": "clip~ -0.98 0.98"
                    }
                },
                {
                    "box": {
                        "id": "obj-gate-sig",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": ["signal"],
                        "patching_rect": [260.0, 100.0, 36.0, 21.0],
                        "text": "*~ 0."
                    }
                },
                {
                    "box": {
                        "id": "obj-msg-clear",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [230.0, 20.0, 38.0, 21.0],
                        "text": "clear"
                    }
                },
                {
                    "box": {
                        "id": "obj-mix-l",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": ["signal"],
                        "patching_rect": [30.0, 60.0, 32.0, 21.0],
                        "text": "+~"
                    }
                },
                {
                    "box": {
                        "id": "obj-mix-r",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": ["signal"],
                        "patching_rect": [65.0, 60.0, 32.0, 21.0],
                        "text": "+~"
                    }
                },
                {
                    "box": {
                        "id": "obj-plugout",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 2,
                        "outlettype": ["signal", "signal"],
                        "patching_rect": [30.0, 95.0, 50.0, 21.0],
                        "text": "plugout~"
                    }
                },

                # --- PRESENTATION UI ELEMENTS (Studio Console: Telemetry, Meter, Server & USB Controls) ---
                # Title
                {
                    "box": {
                        "id": "obj-title",
                        "maxclass": "comment",
                        "numinlets": 1,
                        "numoutlets": 0,
                        "patching_rect": [310.0, 40.0, 120.0, 20.0],
                        "presentation": 1,
                        "presentation_rect": [12.0, 14.0, 115.0, 20.0],
                        "text": "LIVE AIR MIC",
                        "fontname": "Ableton Sans Bold",
                        "fontsize": 12.0,
                        "textcolor": [1.0, 1.0, 1.0, 1.0]
                    }
                },
                # Version / Badge
                {
                    "box": {
                        "id": "obj-version-badge",
                        "maxclass": "comment",
                        "numinlets": 1,
                        "numoutlets": 0,
                        "patching_rect": [430.0, 40.0, 80.0, 18.0],
                        "presentation": 1,
                        "presentation_rect": [128.0, 16.0, 82.0, 18.0],
                        "text": "48kHz AAudio",
                        "fontname": "Ableton Sans Medium",
                        "fontsize": 9.5,
                        "textcolor": [0.22, 0.74, 0.97, 1.0]
                    }
                },
                # Green / Red Connection Status Indicator
                {
                    "box": {
                        "id": "obj-ui-status",
                        "maxclass": "comment",
                        "numinlets": 1,
                        "numoutlets": 0,
                        "patching_rect": [310.0, 70.0, 220.0, 20.0],
                        "presentation": 1,
                        "presentation_rect": [12.0, 34.0, 128.0, 20.0],
                        "text": "● ONLINE (2.7ms)",
                        "fontname": "Ableton Sans Bold",
                        "fontsize": 10.5,
                        "textcolor": [0.06, 0.85, 0.50, 1.0]
                    }
                },
                # Latency & Buffer Telemetry Readout
                {
                    "box": {
                        "id": "obj-ui-latency",
                        "maxclass": "comment",
                        "numinlets": 1,
                        "numoutlets": 0,
                        "patching_rect": [310.0, 95.0, 200.0, 18.0],
                        "presentation": 1,
                        "presentation_rect": [12.0, 52.0, 198.0, 16.0],
                        "text": "Latency: 2.7 ms | AFC: CLEAR",
                        "fontname": "Ableton Sans Medium",
                        "fontsize": 9.0,
                        "textcolor": [0.75, 0.82, 0.90, 1.0]
                    }
                },
                # Device & Channel Route Info (hidden behind or below VU)
                {
                    "box": {
                        "id": "obj-ui-route",
                        "maxclass": "comment",
                        "numinlets": 1,
                        "numoutlets": 0,
                        "patching_rect": [310.0, 115.0, 200.0, 18.0],
                        "presentation": 0,
                        "presentation_rect": [12.0, 90.0, 198.0, 18.0],
                        "text": "Mic: -- dB Peak | -- dB RMS",
                        "fontname": "Ableton Sans Medium",
                        "fontsize": 9.5,
                        "textcolor": [0.58, 0.64, 0.72, 1.0]
                    }
                },
                # Vintage Analog Backlit VU Meter (jsui @filename vu_meter.js)
                {
                    "box": {
                        "id": "obj-vu-peakamp",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": ["float"],
                        "patching_rect": [60.0, 120.0, 75.0, 21.0],
                        "text": "peakamp~ 33"
                    }
                },
                {
                    "box": {
                        "id": "obj-ui-analog-vu",
                        "maxclass": "jsui",
                        "filename": "vu_meter.js",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [60.0, 145.0, 198.0, 52.0],
                        "presentation": 1,
                        "presentation_rect": [12.0, 68.0, 198.0, 50.0]
                    }
                },
                # Peak / RMS Meter Display (live.meter~)
                {
                    "box": {
                        "id": "obj-ui-meter",
                        "maxclass": "live.meter~",
                        "numinlets": 2,
                        "numoutlets": 2,
                        "outlettype": ["float", "int"],
                        "patching_rect": [30.0, 120.0, 20.0, 80.0],
                        "presentation": 1,
                        "presentation_rect": [220.0, 14.0, 26.0, 136.0]
                    }
                },
                # Embedded Server Start/Stop Toggle Button (autostart=1)
                {
                    "box": {
                        "id": "obj-ui-srv-btn",
                        "maxclass": "live.text",
                        "numinlets": 1,
                        "numoutlets": 2,
                        "outlettype": ["", ""],
                        "parameter_enable": 1,
                        "patching_rect": [390.0, 140.0, 75.0, 25.0],
                        "presentation": 1,
                        "presentation_rect": [256.0, 14.0, 78.0, 24.0],
                        "saved_attribute_attributes": {
                            "valueof": {
                                "parameter_enum": ["off", "on"],
                                "parameter_initial": [1.0],
                                "parameter_initial_enable": 1,
                                "parameter_longname": "Bridge Server Power",
                                "parameter_mmax": 1.0,
                                "parameter_shortname": "SRV",
                                "parameter_type": 2
                            }
                        },
                        "text": "SERVER OFF",
                        "texton": "SERVER ON",
                        "activebgcolor": [0.15, 0.18, 0.22, 1.0],
                        "activebgoncolor": [0.06, 0.72, 0.48, 1.0],
                        "textcolor": [0.85, 0.85, 0.85, 1.0],
                        "textoncolor": [1.0, 1.0, 1.0, 1.0]
                    }
                },
                # Direct Clip Record Button & Phone Rec Status
                {
                    "box": {
                        "id": "obj-ui-rec-led",
                        "maxclass": "live.text",
                        "numinlets": 1,
                        "numoutlets": 2,
                        "outlettype": ["", ""],
                        "parameter_enable": 1,
                        "patching_rect": [310.0, 140.0, 70.0, 25.0],
                        "presentation": 1,
                        "presentation_rect": [256.0, 42.0, 78.0, 24.0],
                        "saved_attribute_attributes": {
                            "valueof": {
                                "parameter_enum": ["off", "on"],
                                "parameter_longname": "Phone Rec Status",
                                "parameter_mmax": 1.0,
                                "parameter_shortname": "REC",
                                "parameter_type": 2
                            }
                        },
                        "text": "REC CLIP",
                        "texton": "STOP REC",
                        "activebgcolor": [0.15, 0.18, 0.22, 1.0],
                        "activebgoncolor": [0.93, 0.27, 0.27, 1.0],
                        "textcolor": [0.85, 0.85, 0.85, 1.0],
                        "textoncolor": [1.0, 1.0, 1.0, 1.0]
                    }
                },
                # Connect Phone Button
                {
                    "box": {
                        "id": "obj-ui-btn-usb",
                        "maxclass": "textbutton",
                        "numinlets": 1,
                        "numoutlets": 3,
                        "outlettype": ["", "", "int"],
                        "patching_rect": [510.0, 175.0, 90.0, 20.0],
                        "presentation": 1,
                        "presentation_rect": [256.0, 70.0, 78.0, 26.0],
                        "text": "CONNECT",
                        "bgcolor": [0.02, 0.52, 0.78, 1.0],
                        "bgoncolor": [0.06, 0.65, 0.91, 1.0],
                        "textcolor": [1.0, 1.0, 1.0, 1.0],
                        "textoncolor": [1.0, 1.0, 1.0, 1.0],
                        "textcolor_inverse": [1.0, 1.0, 1.0, 1.0],
                        "fontname": "Ableton Sans Bold",
                        "fontsize": 10.0,
                        "rounded": 6.0
                    }
                },
                {
                    "box": {
                        "id": "obj-usb-url",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [510.0, 205.0, 215.0, 21.0],
                        "text": "get http://127.0.0.1:8765/api/usb_connect"
                    }
                },
                {
                    "box": {
                        "id": "obj-maxurl-usb",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 2,
                        "outlettype": ["dictionary", ""],
                        "patching_rect": [510.0, 232.0, 55.0, 21.0],
                        "text": "maxurl"
                    }
                },
                # Align Recorded Clips Button
                {
                    "box": {
                        "id": "obj-ui-btn-align",
                        "maxclass": "textbutton",
                        "numinlets": 1,
                        "numoutlets": 3,
                        "outlettype": ["", "", "int"],
                        "patching_rect": [610.0, 175.0, 90.0, 20.0],
                        "presentation": 1,
                        "presentation_rect": [256.0, 100.0, 78.0, 24.0],
                        "text": "Align Clips",
                        "bgcolor": [0.16, 0.34, 0.28, 1.0],
                        "textcolor": [1.0, 1.0, 1.0, 1.0],
                        "textcolor_inverse": [1.0, 1.0, 1.0, 1.0],
                        "fontname": "Ableton Sans Medium",
                        "fontsize": 9.5,
                        "rounded": 6.0
                    }
                },
                # Latency Compensation Offset (ms)
                {
                    "box": {
                        "id": "obj-ui-latcomp",
                        "maxclass": "live.numbox",
                        "numinlets": 1,
                        "numoutlets": 2,
                        "outlettype": ["", "float"],
                        "parameter_enable": 1,
                        "patching_rect": [610.0, 140.0, 50.0, 15.0],
                        "presentation": 1,
                        "presentation_rect": [256.0, 130.0, 78.0, 18.0],
                        "saved_attribute_attributes": {
                            "valueof": {
                                "parameter_initial": [85.0],
                                "parameter_initial_enable": 1,
                                "parameter_longname": "Clip Latency Comp",
                                "parameter_mmax": 300.0,
                                "parameter_mmin": 0.0,
                                "parameter_shortname": "Comp",
                                "parameter_type": 0,
                                "parameter_unitstyle": 2
                            }
                        }
                    }
                },
                # Open Web QR Code Button
                {
                    "box": {
                        "id": "obj-ui-btn-qr",
                        "maxclass": "textbutton",
                        "numinlets": 1,
                        "numoutlets": 3,
                        "outlettype": ["", "", "int"],
                        "patching_rect": [310.0, 175.0, 90.0, 20.0],
                        "presentation": 1,
                        "presentation_rect": [12.0, 122.0, 96.0, 28.0],
                        "text": "Open Web App",
                        "bgcolor": [0.16, 0.20, 0.28, 1.0],
                        "textcolor": [0.90, 0.94, 0.98, 1.0],
                        "textcolor_inverse": [0.90, 0.94, 0.98, 1.0],
                        "fontname": "Ableton Sans Medium",
                        "fontsize": 9.5,
                        "rounded": 6.0
                    }
                },
                # Copy IP URL Button
                {
                    "box": {
                        "id": "obj-ui-btn-copy",
                        "maxclass": "textbutton",
                        "numinlets": 1,
                        "numoutlets": 3,
                        "outlettype": ["", "", "int"],
                        "patching_rect": [410.0, 175.0, 90.0, 20.0],
                        "presentation": 1,
                        "presentation_rect": [114.0, 122.0, 96.0, 28.0],
                        "text": "Server Status",
                        "bgcolor": [0.16, 0.20, 0.28, 1.0],
                        "textcolor": [0.90, 0.94, 0.98, 1.0],
                        "textcolor_inverse": [0.90, 0.94, 0.98, 1.0],
                        "fontname": "Ableton Sans Medium",
                        "fontsize": 9.5,
                        "rounded": 6.0
                    }
                },

                # --- EMBEDDED NODE FOR MAX SERVER & ADB CONTROLLER ---
                {
                    "box": {
                        "id": "obj-nodescript",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 2,
                        "outlettype": ["", ""],
                        "patching_rect": [30.0, 560.0, 420.0, 21.0],
                        "text": "node.script server_ctl.js @autostart 1"
                    }
                },
                {
                    "box": {
                        "id": "obj-prep-srvtoggle",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [30.0, 530.0, 125.0, 21.0],
                        "text": "prepend server_toggle"
                    }
                },
                {
                    "box": {
                        "id": "obj-msg-usb",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [165.0, 530.0, 80.0, 21.0],
                        "text": "usb_connect"
                    }
                },
                {
                    "box": {
                        "id": "obj-route-node",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 4,
                        "outlettype": ["", "", "", ""],
                        "patching_rect": [30.0, 590.0, 240.0, 21.0],
                        "text": "route srv_state status_msg active_gate"
                    }
                },
                {
                    "box": {
                        "id": "obj-set-srv-btn",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [30.0, 620.0, 75.0, 21.0],
                        "text": "prepend set"
                    }
                },
                {
                    "box": {
                        "id": "obj-js-align",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [460.0, 560.0, 320.0, 21.0],
                        "text": "js clip_align.js"
                    }
                },
                {
                    "box": {
                        "id": "obj-msg-alignnow",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [460.0, 530.0, 65.0, 21.0],
                        "text": "align_now"
                    }
                },
                {
                    "box": {
                        "id": "obj-prep-latms",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [540.0, 530.0, 130.0, 21.0],
                        "text": "prepend set_latency_ms"
                    }
                },

                # --- OSC RECEIVER ENGINE ---
                # udpreceive on port 9002 (Python -> Max for Live)
                {
                    "box": {
                        "id": "obj-udprecv",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [30.0, 240.0, 100.0, 21.0],
                        "text": "udpreceive 9002"
                    }
                },
                # Native OSC route
                {
                    "box": {
                        "id": "obj-route-native",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 13,
                        "outlettype": ["", "", "", "", "", "", "", "", "", "", "", "", ""],
                        "patching_rect": [30.0, 280.0, 860.0, 21.0],
                        "text": "route /airmic/meter /airmic/status /airmic/remote_rec /airmic/pcm /airmic/status_text /airmic/latency_text /airmic/meter_text /airmic/active /airmic/rel_ctl /airmic/udp_ctl /airmic/mat_ctl /airmic/fx_ctl"
                    }
                },
                # Direct prepend set boxes for pre-formatted telemetry strings from Python
                {
                    "box": {
                        "id": "obj-prep-status",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [205.0, 340.0, 75.0, 21.0],
                        "text": "prepend set"
                    }
                },
                {
                    "box": {
                        "id": "obj-prep-latency",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [290.0, 340.0, 75.0, 21.0],
                        "text": "prepend set"
                    }
                },
                {
                    "box": {
                        "id": "obj-prep-meter",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [375.0, 340.0, 75.0, 21.0],
                        "text": "prepend set"
                    }
                },
                {
                    "box": {
                        "id": "obj-set-rec-led",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [120.0, 340.0, 75.0, 21.0],
                        "text": "prepend set"
                    }
                },
                {
                    "box": {
                        "id": "obj-prep-rectoggle",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [310.0, 450.0, 145.0, 21.0],
                        "text": "prepend /live/rec_toggle"
                    }
                },

                # --- LIVE OBJECT MODEL (LOM) INITIALIZATION & DYNAMIC UDP PORT BINDING ---
                {
                    "box": {
                        "id": "obj-thisdevice",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 3,
                        "outlettype": ["bang", "int", "int"],
                        "patching_rect": [480.0, 160.0, 85.0, 21.0],
                        "text": "live.thisdevice"
                    }
                },
                {
                    "box": {
                        "id": "obj-rand-port",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": ["int"],
                        "patching_rect": [30.0, 160.0, 75.0, 21.0],
                        "text": "random 800"
                    }
                },
                {
                    "box": {
                        "id": "obj-add-port",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": ["int"],
                        "patching_rect": [30.0, 185.0, 55.0, 21.0],
                        "text": "+ 9100"
                    }
                },
                {
                    "box": {
                        "id": "obj-prep-uport",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [30.0, 212.0, 80.0, 21.0],
                        "text": "prepend port"
                    }
                },
                {
                    "box": {
                        "id": "obj-metro-port",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": ["bang"],
                        "patching_rect": [125.0, 160.0, 130.0, 21.0],
                        "text": "metro 1000 @active 1"
                    }
                },
                {
                    "box": {
                        "id": "obj-store-port",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": ["int"],
                        "patching_rect": [125.0, 185.0, 50.0, 21.0],
                        "text": "i 9002"
                    }
                },
                {
                    "box": {
                        "id": "obj-prep-lport",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [125.0, 212.0, 110.0, 21.0],
                        "text": "prepend /live/port"
                    }
                },
                {
                    "box": {
                        "id": "obj-sel-deleted",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 2,
                        "outlettype": ["bang", ""],
                        "patching_rect": [240.0, 185.0, 45.0, 21.0],
                        "text": "sel 0"
                    }
                },
                {
                    "box": {
                        "id": "obj-msg-relport",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [240.0, 212.0, 50.0, 21.0],
                        "text": "port 0"
                    }
                },
                {
                    "box": {
                        "id": "obj-msg-liveset",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [480.0, 190.0, 75.0, 21.0],
                        "text": "path live_set"
                    }
                },
                {
                    "box": {
                        "id": "obj-path-liveset",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 3,
                        "outlettype": ["", "", ""],
                        "patching_rect": [480.0, 220.0, 65.0, 21.0],
                        "text": "live.path"
                    }
                },
                {
                    "box": {
                        "id": "obj-msg-track",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [660.0, 190.0, 175.0, 21.0],
                        "text": "path this_device canonical_parent"
                    }
                },
                {
                    "box": {
                        "id": "obj-path-track",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 3,
                        "outlettype": ["", "", ""],
                        "patching_rect": [660.0, 220.0, 65.0, 21.0],
                        "text": "live.path"
                    }
                },

                # Remote REC handler (toggles Ableton live_set record_mode)
                {
                    "box": {
                        "id": "obj-rec-trigger",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [200.0, 450.0, 140.0, 21.0],
                        "text": "prepend set record_mode"
                    }
                },
                {
                    "box": {
                        "id": "obj-obj-liveset",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [200.0, 510.0, 90.0, 21.0],
                        "text": "live.object"
                    }
                },

                # --- ABLETON TRANSPORT MONITOR & OSC SENDER ---
                # Monitor is_playing
                {
                    "box": {
                        "id": "obj-obs-playing",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 2,
                        "outlettype": ["", ""],
                        "patching_rect": [480.0, 260.0, 130.0, 21.0],
                        "text": "live.observer is_playing"
                    }
                },
                # Monitor record_mode
                {
                    "box": {
                        "id": "obj-obs-recmode",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 2,
                        "outlettype": ["", ""],
                        "patching_rect": [480.0, 290.0, 130.0, 21.0],
                        "text": "live.observer record_mode"
                    }
                },
                # Monitor tempo
                {
                    "box": {
                        "id": "obj-obs-tempo",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 2,
                        "outlettype": ["", ""],
                        "patching_rect": [480.0, 320.0, 110.0, 21.0],
                        "text": "live.observer tempo"
                    }
                },
                # Monitor song position / beat (throttled when idle to avoid flooding Max main thread)
                {
                    "box": {
                        "id": "obj-obs-beat",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": ["int"],
                        "patching_rect": [480.0, 350.0, 40.0, 21.0],
                        "text": "i 1"
                    }
                },
                # Monitor track arm
                {
                    "box": {
                        "id": "obj-obs-arm",
                        "maxclass": "newobj",
                        "numinlets": 2,
                        "numoutlets": 2,
                        "outlettype": ["", ""],
                        "patching_rect": [660.0, 260.0, 105.0, 21.0],
                        "text": "live.observer arm"
                    }
                },
                {
                    "box": {
                        "id": "obj-prep-arm",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [660.0, 380.0, 115.0, 21.0],
                        "text": "prepend /live/arm"
                    }
                },
                # Pack Transport state
                {
                    "box": {
                        "id": "obj-pack-trans",
                        "maxclass": "newobj",
                        "numinlets": 4,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [480.0, 385.0, 140.0, 21.0],
                        "text": "pak 0 0 120. 0."
                    }
                },
                {
                    "box": {
                        "id": "obj-prep-trans",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [480.0, 415.0, 150.0, 21.0],
                        "text": "prepend /live/transport"
                    }
                },
                # udpsend to Python bridge on port 9003
                {
                    "box": {
                        "id": "obj-udpsend",
                        "maxclass": "newobj",
                        "numinlets": 1,
                        "numoutlets": 0,
                        "patching_rect": [480.0, 450.0, 140.0, 21.0],
                        "text": "udpsend 127.0.0.1 9003"
                    }
                },

                # Browser Launcher Scripts
                {
                    "box": {
                        "id": "obj-open-url",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [310.0, 210.0, 150.0, 21.0],
                        "text": "; max launchbrowser http://localhost:8765"
                    }
                },
                {
                    "box": {
                        "id": "obj-open-status",
                        "maxclass": "message",
                        "numinlets": 2,
                        "numoutlets": 1,
                        "outlettype": [""],
                        "patching_rect": [470.0, 210.0, 180.0, 21.0],
                        "text": "; max launchbrowser http://localhost:8765/api/status"
                    }
                }
            ],
            "lines": [
                # Direct Jitter-to-MSP stream (jit.fill -> jit.matrix -> jit.release~ -> bitsafe~ -> clip~ -> *~) + plugin~ passthrough
                {"patchline": {"destination": ["obj-jit-fill", 0], "source": ["obj-route-native", 3]}},
                {"patchline": {"destination": ["obj-jit-mat", 0], "source": ["obj-jit-fill", 0]}},
                {"patchline": {"destination": ["obj-msg-clear", 0], "source": ["obj-thisdevice", 0]}},
                {"patchline": {"destination": ["obj-jit-mat", 0], "source": ["obj-msg-clear", 0]}},
                {"patchline": {"destination": ["obj-jit-rel", 0], "source": ["obj-jit-mat", 0]}},
                {"patchline": {"destination": ["obj-bitsafe", 0], "source": ["obj-jit-rel", 0]}},
                {"patchline": {"destination": ["obj-clip", 0], "source": ["obj-bitsafe", 0]}},
                {"patchline": {"destination": ["obj-gate-sig", 0], "source": ["obj-clip", 0]}},
                {"patchline": {"destination": ["obj-gate-sig", 1], "source": ["obj-route-native", 7]}},
                {"patchline": {"destination": ["obj-jit-rel", 0], "source": ["obj-route-native", 8]}},
                {"patchline": {"destination": ["obj-udprecv", 0], "source": ["obj-route-native", 9]}},
                {"patchline": {"destination": ["obj-jit-mat", 0], "source": ["obj-route-native", 10]}},
                {"patchline": {"destination": ["obj-js-align", 0], "source": ["obj-route-native", 11]}},
                {"patchline": {"destination": ["obj-mix-l", 0], "source": ["obj-plugin", 0]}},
                {"patchline": {"destination": ["obj-mix-l", 1], "source": ["obj-gate-sig", 0]}},
                {"patchline": {"destination": ["obj-mix-r", 0], "source": ["obj-plugin", 1]}},
                {"patchline": {"destination": ["obj-mix-r", 1], "source": ["obj-gate-sig", 0]}},
                {"patchline": {"destination": ["obj-plugout", 0], "source": ["obj-mix-l", 0]}},
                {"patchline": {"destination": ["obj-plugout", 1], "source": ["obj-mix-r", 0]}},
                {"patchline": {"destination": ["obj-ui-meter", 0], "source": ["obj-mix-l", 0]}},
                {"patchline": {"destination": ["obj-ui-meter", 1], "source": ["obj-mix-r", 0]}},
                {"patchline": {"destination": ["obj-vu-peakamp", 0], "source": ["obj-mix-l", 0]}},
                {"patchline": {"destination": ["obj-ui-analog-vu", 0], "source": ["obj-vu-peakamp", 0]}},
                {"patchline": {"destination": ["obj-ui-analog-vu", 0], "source": ["obj-route-native", 0]}},

                # LOM initialization & Dynamic UDP port binding via live.thisdevice
                {"patchline": {"destination": ["obj-msg-qsize", 0], "source": ["obj-thisdevice", 0]}},
                {"patchline": {"destination": ["obj-udprecv", 0], "source": ["obj-msg-qsize", 0]}},
                {"patchline": {"destination": ["obj-rand-port", 0], "source": ["obj-thisdevice", 0]}},
                {"patchline": {"destination": ["obj-add-port", 0], "source": ["obj-rand-port", 0]}},
                {"patchline": {"destination": ["obj-prep-uport", 0], "source": ["obj-add-port", 0]}},
                {"patchline": {"destination": ["obj-udprecv", 0], "source": ["obj-prep-uport", 0]}},
                {"patchline": {"destination": ["obj-store-port", 0], "source": ["obj-add-port", 0]}},
                {"patchline": {"destination": ["obj-store-port", 0], "source": ["obj-metro-port", 0]}},
                {"patchline": {"destination": ["obj-prep-lport", 0], "source": ["obj-store-port", 0]}},
                {"patchline": {"destination": ["obj-udpsend", 0], "source": ["obj-prep-lport", 0]}},
                {"patchline": {"destination": ["obj-metro-port", 0], "source": ["obj-thisdevice", 1]}},
                {"patchline": {"destination": ["obj-sel-deleted", 0], "source": ["obj-thisdevice", 1]}},
                {"patchline": {"destination": ["obj-msg-relport", 0], "source": ["obj-sel-deleted", 0]}},
                {"patchline": {"destination": ["obj-udprecv", 0], "source": ["obj-msg-relport", 0]}},
                {"patchline": {"destination": ["obj-msg-liveset", 0], "source": ["obj-thisdevice", 0]}},
                {"patchline": {"destination": ["obj-path-liveset", 0], "source": ["obj-msg-liveset", 0]}},
                {"patchline": {"destination": ["obj-obj-liveset", 1], "source": ["obj-path-liveset", 0]}},
                {"patchline": {"destination": ["obj-obs-playing", 1], "source": ["obj-path-liveset", 0]}},
                {"patchline": {"destination": ["obj-obs-recmode", 1], "source": ["obj-path-liveset", 0]}},
                {"patchline": {"destination": ["obj-obs-tempo", 1], "source": ["obj-path-liveset", 0]}},
                {"patchline": {"destination": ["obj-obs-beat", 1], "source": ["obj-path-liveset", 0]}},

                # Track arm LOM observer
                {"patchline": {"destination": ["obj-msg-track", 0], "source": ["obj-thisdevice", 0]}},
                {"patchline": {"destination": ["obj-path-track", 0], "source": ["obj-msg-track", 0]}},
                {"patchline": {"destination": ["obj-obs-arm", 1], "source": ["obj-path-track", 0]}},
                {"patchline": {"destination": ["obj-prep-arm", 0], "source": ["obj-obs-arm", 0]}},
                {"patchline": {"destination": ["obj-udpsend", 0], "source": ["obj-prep-arm", 0]}},

                # OSC receive to routes
                {"patchline": {"destination": ["obj-route-native", 0], "source": ["obj-udprecv", 0]}},

                # Direct telemetry text updates (status_text, latency_text, meter_text)
                {"patchline": {"destination": ["obj-prep-status", 0], "source": ["obj-route-native", 4]}},
                {"patchline": {"destination": ["obj-ui-status", 0], "source": ["obj-prep-status", 0]}},
                {"patchline": {"destination": ["obj-prep-latency", 0], "source": ["obj-route-native", 5]}},
                {"patchline": {"destination": ["obj-ui-latency", 0], "source": ["obj-prep-latency", 0]}},
                {"patchline": {"destination": ["obj-prep-meter", 0], "source": ["obj-route-native", 6]}},
                {"patchline": {"destination": ["obj-ui-route", 0], "source": ["obj-prep-meter", 0]}},

                # Remote REC trigger & Direct Clip REC button
                {"patchline": {"destination": ["obj-rec-trigger", 0], "source": ["obj-route-native", 2]}},
                {"patchline": {"destination": ["obj-set-rec-led", 0], "source": ["obj-route-native", 2]}},
                {"patchline": {"destination": ["obj-ui-rec-led", 0], "source": ["obj-set-rec-led", 0]}},
                {"patchline": {"destination": ["obj-obj-liveset", 0], "source": ["obj-rec-trigger", 0]}},
                {"patchline": {"destination": ["obj-prep-rectoggle", 0], "source": ["obj-ui-rec-led", 0]}},
                {"patchline": {"destination": ["obj-udpsend", 0], "source": ["obj-prep-rectoggle", 0]}},

                # Transport observers to pack
                {"patchline": {"destination": ["obj-pack-trans", 0], "source": ["obj-obs-playing", 0]}},
                {"patchline": {"destination": ["obj-pack-trans", 1], "source": ["obj-obs-recmode", 0]}},
                {"patchline": {"destination": ["obj-pack-trans", 2], "source": ["obj-obs-tempo", 0]}},
                {"patchline": {"destination": ["obj-pack-trans", 3], "source": ["obj-obs-beat", 0]}},
                {"patchline": {"destination": ["obj-prep-trans", 0], "source": ["obj-pack-trans", 0]}},
                {"patchline": {"destination": ["obj-udpsend", 0], "source": ["obj-prep-trans", 0]}},

                # Open browser buttons
                {"patchline": {"destination": ["obj-open-url", 0], "source": ["obj-ui-btn-qr", 0]}},
                {"patchline": {"destination": ["obj-open-status", 0], "source": ["obj-ui-btn-copy", 0]}},

                # Embedded Node for Max Server & ADB Controller lines
                {"patchline": {"destination": ["obj-prep-srvtoggle", 0], "source": ["obj-ui-srv-btn", 0]}},
                {"patchline": {"destination": ["obj-nodescript", 0], "source": ["obj-prep-srvtoggle", 0]}},
                {"patchline": {"destination": ["obj-msg-usb", 0], "source": ["obj-ui-btn-usb", 0]}},
                {"patchline": {"destination": ["obj-usb-url", 0], "source": ["obj-ui-btn-usb", 0]}},
                {"patchline": {"destination": ["obj-maxurl-usb", 0], "source": ["obj-usb-url", 0]}},
                {"patchline": {"destination": ["obj-nodescript", 0], "source": ["obj-msg-usb", 0]}},
                {"patchline": {"destination": ["obj-route-node", 0], "source": ["obj-nodescript", 0]}},
                {"patchline": {"destination": ["obj-set-srv-btn", 0], "source": ["obj-route-node", 0]}},
                {"patchline": {"destination": ["obj-ui-srv-btn", 0], "source": ["obj-set-srv-btn", 0]}},
                {"patchline": {"destination": ["obj-prep-status", 0], "source": ["obj-route-node", 1]}},
                {"patchline": {"destination": ["obj-gate-sig", 1], "source": ["obj-route-node", 2]}},

                # Automatic & Manual Clip Latency Compensator (js clip_align.js)
                {"patchline": {"destination": ["obj-msg-alignnow", 0], "source": ["obj-ui-btn-align", 0]}},
                {"patchline": {"destination": ["obj-js-align", 0], "source": ["obj-msg-alignnow", 0]}},
                {"patchline": {"destination": ["obj-prep-latms", 0], "source": ["obj-ui-latcomp", 0]}},
                {"patchline": {"destination": ["obj-js-align", 0], "source": ["obj-prep-latms", 0]}}
            ],
            "parameters": {
                "obj-ui-rec-led": ["Phone Rec Status", "REC", 0],
                "obj-ui-srv-btn": ["Bridge Server Power", "SRV", 0],
                "obj-ui-latcomp": ["Clip Latency Comp", "Comp", 0],
                "inherited_shortname": 1
            }
        }
    }
    return patcher


def build_amxd_binary(patcher_data: dict, device_type: bytes = b"aaaa") -> bytes:
    """
    Pack a Max JSON patcher dictionary into Ableton's binary .amxd container format:
      - 'ampf' + uint32_le(4) + device_type ('aaaa' = Audio Effect)
      - 'meta' + uint32_le(4) + uint32_le(0)
      - 'ptch' + uint32_le(len(payload)) + json_utf8 + '\\n\\x00'
    """
    json_bytes = json.dumps(patcher_data, indent=2).encode("utf-8") + b"\n\x00"
    header = (
        b"ampf"
        + struct.pack("<I", 4)
        + device_type
        + b"meta"
        + struct.pack("<I", 4)
        + struct.pack("<I", 0)
        + b"ptch"
        + struct.pack("<I", len(json_bytes))
    )
    return header + json_bytes


def main():
    out_dir = Path(__file__).resolve().parent
    patcher_data = generate_patcher()

    maxpat_path = out_dir / "LiveAirMic.maxpat"
    amxd_path = out_dir / "LiveAirMic.amxd"

    # Write .maxpat (plain JSON)
    with open(maxpat_path, "w", encoding="utf-8") as f:
        json.dump(patcher_data, f, indent=2)

    # Write .amxd (binary Max for Live container with 'ampf' / 'aaaa' / 'meta' / 'ptch' header)
    amxd_bytes = build_amxd_binary(patcher_data, device_type=b"aaaa")
    with open(amxd_path, "wb") as f:
        f.write(amxd_bytes)

    print(f"Generated Max for Live devices:\n  Maxpat: {maxpat_path}\n  AMXD:   {amxd_path} ({len(amxd_bytes)} bytes)")

if __name__ == "__main__":
    main()
