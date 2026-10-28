// Copyright 2026 Michael Lovci
// SPDX-License-Identifier: Apache-2.0
/**
 * LiveAirMic — Vintage Analog Backlit VU Meter (Max for Live jsui / mgraphics)
 * Renders an authentic warm-backlit analog VU dial with -20..0..+3 dB scale,
 * sweeping needle with ballistics + drop shadow, and ruby PEAK jewel lamp.
 */

autowatch = 1;
inlets = 1;
outlets = 1;

mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;

var smoothNorm = 0.0;
var peakLin = 0.0;

var tickNorms = [0.00, 0.18, 0.31, 0.43, 0.56, 0.68, 0.75, 0.83, 0.91, 1.00];
var tickLabels = ["-20", "-10", "-7", "-5", "-3", "-1", "0", "+1", "+2", "+3"];

function msg_float(v) {
    if (v < 0.0) v = 0.0;
    peakLin = v;
    var db = v > 0.0001 ? (20.0 * Math.log(v) / Math.LN10) : -96.0;
    var vuDb = db + 3.0;
    var target = (Math.max(-45.0, Math.min(3.0, vuDb)) + 45.0) / 48.0;
    if (target > smoothNorm) {
        smoothNorm += (target - smoothNorm) * 0.42;
    } else {
        smoothNorm += (target - smoothNorm) * 0.20;
    }
    mgraphics.redraw();
}

function list() {
    var a = arrayfromargs(arguments);
    if (a.length > 0) {
        msg_float(Number(a[0]));
    }
}

function paint() {
    var size = mgraphics.size;
    var w = size[0];
    var h = size[1];
    if (w <= 0 || h <= 0) return;

    var pad = 2.0;
    var r = 6.0;

    // 0. Match Ableton M4L device surface background outside rounded bezel corners
    mgraphics.set_source_rgba(0.22, 0.24, 0.27, 1.0);
    mgraphics.rectangle(0.0, 0.0, w, h);
    mgraphics.fill();

    // 1. Warm incandescent amber faceplate
    mgraphics.set_source_rgba(0.96, 0.88, 0.68, 1.0);
    mgraphics.rectangle_rounded(pad, pad, w - 2.0 * pad, h - 2.0 * pad, r, r);
    mgraphics.fill();

    // Subtle warm top bulb highlight (strictly inside faceplate bounds)
    mgraphics.set_source_rgba(1.0, 0.97, 0.86, 0.45);
    mgraphics.ellipse(w * 0.15, pad + 1.0, w * 0.70, h * 0.38);
    mgraphics.fill();

    // 2. Curved VU Scale Arc (-20 to +3 VU) centered at bottom pivot cap
    var cx = w * 0.5;
    var pivotY = h + 2.0;
    var radius = h * 0.74;
    var startDeg = -48.0;
    var spanDeg = 96.0;
    var zeroNorm = 0.75;
    var degToRad = Math.PI / 180.0;

    var aStart = (-90.0 + startDeg) * degToRad;
    var aZero = (-90.0 + startDeg + zeroNorm * spanDeg) * degToRad;
    var aEnd = (-90.0 + startDeg + spanDeg) * degToRad;

    // Normal zone arc (-20 to 0 VU)
    mgraphics.set_line_width(1.6);
    mgraphics.set_source_rgba(0.16, 0.11, 0.06, 1.0);
    mgraphics.arc(cx, pivotY, radius, aStart, aZero);
    mgraphics.stroke();

    // Red overload band (0 to +3 VU)
    mgraphics.set_line_width(3.2);
    mgraphics.set_source_rgba(0.78, 0.12, 0.12, 1.0);
    mgraphics.arc(cx, pivotY, radius, aZero, aEnd);
    mgraphics.stroke();

    // 3. Radial Tick Marks & Numbers
    mgraphics.select_font_face("Georgia", "normal", "bold");
    mgraphics.set_font_size(7.5);

    for (var i = 0; i < tickNorms.length; i++) {
        var tn = tickNorms[i];
        var deg = startDeg + tn * spanDeg;
        var rad = deg * degToRad;
        var isRed = tn > zeroNorm + 0.001;
        var isMajor = (i === 0 || i === 1 || i === 4 || i === 6 || i === 9);

        var rInner = radius - 1.5;
        var rOuter = radius + (isMajor ? 5.2 : 3.2);
        var x1 = cx + rInner * Math.sin(rad);
        var y1 = pivotY - rInner * Math.cos(rad);
        var x2 = cx + rOuter * Math.sin(rad);
        var y2 = pivotY - rOuter * Math.cos(rad);

        mgraphics.set_line_width(isMajor ? 1.5 : 1.0);
        if (isRed) {
            mgraphics.set_source_rgba(0.75, 0.11, 0.11, 1.0);
        } else {
            mgraphics.set_source_rgba(0.16, 0.11, 0.06, 1.0);
        }
        mgraphics.move_to(x1, y1);
        mgraphics.line_to(x2, y2);
        mgraphics.stroke();

        if (isMajor || i === 7) {
            var rText = radius + 11.2;
            var tx = cx + rText * Math.sin(rad) - 5.5;
            var ty = pivotY - rText * Math.cos(rad) + 2.5;
            mgraphics.move_to(tx, ty);
            mgraphics.show_text(tickLabels[i]);
        }
    }

    // 4. Classic "VU" Emblem
    mgraphics.set_font_size(10.5);
    mgraphics.set_source_rgba(0.24, 0.15, 0.09, 0.90);
    mgraphics.move_to(cx - 8.5, h * 0.68);
    mgraphics.show_text("VU");

    // 5. Ruby PEAK Jewel Indicator Lamp
    var lampX = w - 13.0;
    var lampY = 11.0;
    if (peakLin > 0.5) {
        mgraphics.set_source_rgba(1.0, 0.16, 0.16, 1.0);
    } else {
        mgraphics.set_source_rgba(0.32, 0.10, 0.10, 1.0);
    }
    mgraphics.arc(lampX, lampY, 3.6, 0, Math.PI * 2.0);
    mgraphics.fill();

    // 6. Sweeping Analog Needle + Shadow (emanating from inside the center Bakelite pivot cap)
    var needleDeg = startDeg + smoothNorm * spanDeg;
    var needleRad = needleDeg * degToRad;
    var rStart = 9.0;
    var needleLen = radius + 4.2;
    var sx = cx + rStart * Math.sin(needleRad);
    var sy = pivotY - rStart * Math.cos(needleRad);
    var tipX = cx + needleLen * Math.sin(needleRad);
    var tipY = pivotY - needleLen * Math.cos(needleRad);

    // Shadow
    mgraphics.set_line_width(2.0);
    mgraphics.set_source_rgba(0.14, 0.08, 0.02, 0.24);
    mgraphics.move_to(sx + 1.5, sy + 1.0);
    mgraphics.line_to(tipX + 1.5, tipY + 1.5);
    mgraphics.stroke();

    // Needle shaft
    mgraphics.set_line_width(1.7);
    mgraphics.set_source_rgba(0.10, 0.07, 0.04, 1.0);
    mgraphics.move_to(sx, sy);
    mgraphics.line_to(tipX, tipY);
    mgraphics.stroke();

    // 7. Bottom Bakelite Pivot Cap (sits flush on inner bottom bezel)
    mgraphics.set_source_rgba(0.12, 0.09, 0.06, 1.0);
    mgraphics.arc(cx, h - pad, 12.5, Math.PI, Math.PI * 2.0);
    mgraphics.fill();

    // 8. Outer Vintage Brass/Bakelite Bezel
    mgraphics.set_line_width(2.0);
    mgraphics.set_source_rgba(0.42, 0.30, 0.17, 1.0);
    mgraphics.rectangle_rounded(pad, pad, w - 2.0 * pad, h - 2.0 * pad, r, r);
    mgraphics.stroke();
}
