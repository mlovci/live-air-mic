package com.liveairmic.pro;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.Bundle;
import android.os.Process;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URL;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int SAMPLE_RATE = 48000;
    private static final int QUANTUM_FRAMES = 128; // 2.67 ms per packet
    private static final int BYTES_PER_QUANTUM = QUANTUM_FRAMES * 2;
    private static final int TCP_PORT = 8766;

    private volatile boolean isRunning = false;
    private volatile boolean isConnected = false;
    private volatile boolean isMuted = false;
    private volatile boolean isRecordingClip = false;
    private volatile boolean isDryBypass = false;
    private volatile boolean isGateOn = true;
    private volatile boolean isPitchOn = true;
    private volatile boolean isEchoOn = true;
    private volatile boolean isSpringOn = true;
    private volatile boolean isWarmOn = true;
    private volatile boolean isVocalIsoOn = true;
    private volatile float gainLinear = 1.0f;
    private volatile float livePeak = 0.0f;
    private volatile float liveRms = 0.0f;
    private volatile int hwFramesPerBurst = 128;
    private volatile int actualAudioSource = MediaRecorder.AudioSource.UNPROCESSED;
    private volatile long packetsSent = 0;

    private Thread audioThread;
    private TextView latencyBadge;
    private TextView dbLabel;
    private TextView afcStatusBadge;
    private TextView afcMetricsLabel;
    private final TextView[] notchBadges = new TextView[4];
    private FastMeterView meterView;
    private Button muteBtn;
    private Button recBtn;
    private final short[] afcStatsBuf = new short[12];

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window win = getWindow();
        win.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            win.setStatusBarColor(Color.parseColor("#070A0F"));
            win.setNavigationBarColor(Color.parseColor("#070A0F"));
        }

        try {
            AudioManager am = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
            if (am != null) {
                String fpb = am.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER);
                if (fpb != null) {
                    hwFramesPerBurst = Integer.parseInt(fpb);
                }
            }
        } catch (Exception ignored) {}

        buildStudioUi();

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 1001);
        } else {
            startFastTrackEngine();
        }
    }

    private volatile long lastAudioReadMs = 0;
    private final Object engineRunLock = new Object();

    @Override
    protected void onResume() {
        super.onResume();
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            long now = System.currentTimeMillis();
            if (!isRunning || (lastAudioReadMs > 0 && (now - lastAudioReadMs) > 1500)) {
                restartFastTrackEngine();
            }
        }
    }

    @Override
    protected void onNewIntent(android.content.Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            long now = System.currentTimeMillis();
            if (!isRunning || (lastAudioReadMs > 0 && (now - lastAudioReadMs) > 1500)) {
                restartFastTrackEngine();
            }
        }
    }

    private synchronized void restartFastTrackEngine() {
        isRunning = false;
        activeEngineGen++;
        if (audioThread != null && audioThread.isAlive()) {
            try {
                audioThread.join(600);
            } catch (InterruptedException ignored) {}
        }
        startFastTrackEngine();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (requestCode == 1001 && grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startFastTrackEngine();
        }
    }

    private GradientDrawable roundedBg(String hexColor, int radiusDp, String strokeHex) {
        return roundedBgStroke(hexColor, radiusDp, strokeHex, 1);
    }

    private GradientDrawable roundedBgStroke(String hexColor, int radiusDp, String strokeHex, int strokeDp) {
        GradientDrawable gd = new GradientDrawable();
        gd.setColor(Color.parseColor(hexColor));
        gd.setCornerRadius(dp(radiusDp));
        if (strokeHex != null) {
            gd.setStroke(dp(strokeDp), Color.parseColor(strokeHex));
        }
        return gd;
    }

    private GradientDrawable roundedGradientBg(String topHex, String bottomHex, int radiusDp, String strokeHex, int strokeDp) {
        GradientDrawable gd = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{Color.parseColor(topHex), Color.parseColor(bottomHex)}
        );
        gd.setCornerRadius(dp(radiusDp));
        if (strokeHex != null) {
            gd.setStroke(dp(strokeDp), Color.parseColor(strokeHex));
        }
        return gd;
    }

    private void stripButtonShadow(Button b) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            b.setStateListAnimator(null);
            b.setElevation(0f);
        }
        b.setIncludeFontPadding(false);
    }

    private void buildStudioUi() {
        final LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor("#070A0F"));
        final int basePadH = dp(16);
        final int basePadTop = dp(46);
        final int basePadBot = dp(20);
        root.setPadding(basePadH, basePadTop, basePadH, basePadBot);

        root.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
            @Override
            public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                int topInset = insets.getSystemWindowInsetTop();
                int botInset = insets.getSystemWindowInsetBottom();
                int leftInset = insets.getSystemWindowInsetLeft();
                int rightInset = insets.getSystemWindowInsetRight();
                v.setPadding(
                        basePadH + leftInset,
                        Math.max(dp(14), topInset + dp(8)),
                        basePadH + rightInset,
                        Math.max(dp(14), botInset + dp(8))
                );
                return insets;
            }
        });

        final LinearLayout mainPage = new LinearLayout(this);
        mainPage.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams pageLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.MATCH_PARENT);

        final LinearLayout mixerPage = new LinearLayout(this);
        mixerPage.setOrientation(LinearLayout.VERTICAL);
        mixerPage.setVisibility(View.GONE);

        // ====================================================================
        // 1. STUDIO TOP HEADER BAR: Brand Identity + Latency Pill + Mixer Switch
        // ====================================================================
        LinearLayout headerRow = new LinearLayout(this);
        headerRow.setOrientation(LinearLayout.HORIZONTAL);
        headerRow.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams headerLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        headerLp.bottomMargin = dp(8);

        LinearLayout brandCol = new LinearLayout(this);
        brandCol.setOrientation(LinearLayout.VERTICAL);

        TextView title = new TextView(this);
        title.setText("LIVE AIR MIC");
        title.setTextColor(Color.parseColor("#F8FAFC"));
        title.setTextSize(17.0f);
        title.setTypeface(Typeface.create("sans-serif-black", Typeface.BOLD));
        title.setLetterSpacing(0.06f);
        title.setIncludeFontPadding(false);
        brandCol.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("48kHz AAUDIO  •  ZERO-LATENCY DSP");
        subtitle.setTextColor(Color.parseColor("#64748B"));
        subtitle.setTextSize(8.5f);
        subtitle.setTypeface(Typeface.MONOSPACE);
        subtitle.setSingleLine(true);
        subtitle.setIncludeFontPadding(false);
        brandCol.addView(subtitle);

        headerRow.addView(brandCol, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f));

        latencyBadge = new TextView(this);
        latencyBadge.setText("● 2.7ms");
        latencyBadge.setTextColor(Color.parseColor("#052E16"));
        latencyBadge.setTextSize(10.0f);
        latencyBadge.setTypeface(Typeface.DEFAULT_BOLD);
        latencyBadge.setPadding(dp(10), dp(5), dp(10), dp(5));
        latencyBadge.setBackground(roundedBg("#10B981", 12, "#34D399"));
        LinearLayout.LayoutParams latLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        latLp.rightMargin = dp(6);
        headerRow.addView(latencyBadge, latLp);

        Button topMixerBtn = new Button(this);
        stripButtonShadow(topMixerBtn);
        topMixerBtn.setText("MIXER ▸");
        topMixerBtn.setTextColor(Color.parseColor("#E2E8F0"));
        topMixerBtn.setTextSize(10.0f);
        topMixerBtn.setTypeface(Typeface.DEFAULT_BOLD);
        topMixerBtn.setAllCaps(false);
        topMixerBtn.setMinHeight(0);
        topMixerBtn.setMinimumHeight(0);
        topMixerBtn.setMinWidth(0);
        topMixerBtn.setMinimumWidth(0);
        topMixerBtn.setPadding(dp(11), dp(6), dp(11), dp(6));
        topMixerBtn.setBackground(roundedGradientBg("#1E293B", "#0F172A", 10, "#334155", 1));
        headerRow.addView(topMixerBtn);

        mainPage.addView(headerRow, headerLp);

        // ====================================================================
        // 2. VINTAGE ANALOG BACKLIT VU METER BRIDGE CARD
        // ====================================================================
        LinearLayout meterCard = new LinearLayout(this);
        meterCard.setOrientation(LinearLayout.VERTICAL);
        meterCard.setPadding(dp(10), dp(7), dp(10), dp(8));
        meterCard.setBackground(roundedGradientBg("#18130E", "#0E0B08", 12, "#4A3723", 1));
        LinearLayout.LayoutParams meterCardLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.55f);
        meterCardLp.bottomMargin = dp(7);

        LinearLayout meterHeaderRow = new LinearLayout(this);
        meterHeaderRow.setOrientation(LinearLayout.HORIZONTAL);
        meterHeaderRow.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams mhRowLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        mhRowLp.bottomMargin = dp(4);

        TextView meterTitle = new TextView(this);
        meterTitle.setText("VINTAGE ANALOG VU");
        meterTitle.setTextColor(Color.parseColor("#EAB308"));
        meterTitle.setTextSize(9.0f);
        meterTitle.setTypeface(Typeface.DEFAULT_BOLD);
        meterTitle.setLetterSpacing(0.08f);
        meterHeaderRow.addView(meterTitle, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f));

        dbLabel = new TextView(this);
        dbLabel.setText("PK -∞  |  RMS -∞ dB");
        dbLabel.setTextColor(Color.parseColor("#FDE68A"));
        dbLabel.setTextSize(10.0f);
        dbLabel.setTypeface(Typeface.MONOSPACE);
        meterHeaderRow.addView(dbLabel);
        meterCard.addView(meterHeaderRow, mhRowLp);

        meterView = new FastMeterView(this);
        LinearLayout.LayoutParams meterLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.0f);
        meterCard.addView(meterView, meterLp);
        mainPage.addView(meterCard, meterCardLp);

        // ====================================================================
        // 3. FEEDBACK DETECTION & AFC MONITOR MODULE (PEM PAPR + 4x Q=45 Notches)
        // ====================================================================
        LinearLayout afcCard = new LinearLayout(this);
        afcCard.setOrientation(LinearLayout.VERTICAL);
        afcCard.setGravity(Gravity.CENTER_VERTICAL);
        afcCard.setPadding(dp(12), dp(8), dp(12), dp(8));
        afcCard.setBackground(roundedGradientBg("#111726", "#0B0F19", 12, "#1E293B", 1));
        LinearLayout.LayoutParams afcCardLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.0f);
        afcCardLp.bottomMargin = dp(7);

        LinearLayout afcTopRow = new LinearLayout(this);
        afcTopRow.setOrientation(LinearLayout.HORIZONTAL);
        afcTopRow.setGravity(Gravity.CENTER_VERTICAL);

        afcStatusBadge = new TextView(this);
        afcStatusBadge.setText("AFC: CLEAR");
        afcStatusBadge.setTextColor(Color.parseColor("#052E16"));
        afcStatusBadge.setTextSize(9.5f);
        afcStatusBadge.setTypeface(Typeface.DEFAULT_BOLD);
        afcStatusBadge.setPadding(dp(8), dp(2), dp(8), dp(2));
        afcStatusBadge.setBackground(roundedBg("#10B981", 6, null));
        afcTopRow.addView(afcStatusBadge);

        afcMetricsLabel = new TextView(this);
        afcMetricsLabel.setText("PAPR 1.0/42 | --Hz | ISO 0dB | 0µs");
        afcMetricsLabel.setTextColor(Color.parseColor("#94A3B8"));
        afcMetricsLabel.setTextSize(8.8f);
        afcMetricsLabel.setTypeface(Typeface.MONOSPACE);
        afcMetricsLabel.setSingleLine(true);
        afcMetricsLabel.setGravity(Gravity.END);
        LinearLayout.LayoutParams afcMetLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f);
        afcMetLp.leftMargin = dp(6);
        afcTopRow.addView(afcMetricsLabel, afcMetLp);
        afcCard.addView(afcTopRow);

        LinearLayout notchRow = new LinearLayout(this);
        notchRow.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams notchRowLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        notchRowLp.topMargin = dp(6);

        for (int n = 0; n < 4; n++) {
            TextView nb = new TextView(this);
            nb.setText("○ N" + (n + 1) + " IDLE");
            nb.setTextColor(Color.parseColor("#64748B"));
            nb.setTextSize(9.0f);
            nb.setTypeface(Typeface.MONOSPACE);
            nb.setGravity(Gravity.CENTER);
            nb.setPadding(dp(4), dp(4), dp(4), dp(4));
            nb.setBackground(roundedBg("#080B12", 6, "#1E293B"));
            LinearLayout.LayoutParams nbLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f);
            if (n > 0) nbLp.leftMargin = dp(5);
            notchBadges[n] = nb;
            notchRow.addView(nb, nbLp);
        }
        afcCard.addView(notchRow, notchRowLp);
        mainPage.addView(afcCard, afcCardLp);

        // ====================================================================
        // 4. REGGAE DUB PERFORMANCE PADS (2x2 Tactile Studio Pad Matrix)
        // ====================================================================
        LinearLayout padRow1 = new LinearLayout(this);
        padRow1.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams padRow1Lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 0.88f);
        padRow1Lp.bottomMargin = dp(6);

        final StudioPadView dubThrowPad = new StudioPadView(
                this, "MOMENTARY SEND", "HOLD: DUB THROW", "#A855F7", false);
        dubThrowPad.setOnTouchListener(new View.OnTouchListener() {
            @Override
            public boolean onTouch(View v, MotionEvent event) {
                int a = event.getActionMasked();
                if (a == MotionEvent.ACTION_DOWN) {
                    dubThrowPad.setPadState("SENDING ECHO THROW", "DUB THROWING!", "#EC4899", true);
                    sendFxCommand("dub_throw", 1.0f);
                    return true;
                } else if (a == MotionEvent.ACTION_UP || a == MotionEvent.ACTION_CANCEL) {
                    dubThrowPad.setPadState("MOMENTARY SEND", "HOLD: DUB THROW", "#A855F7", false);
                    sendFxCommand("dub_throw", 0.0f);
                    return true;
                }
                return false;
            }
        });
        LinearLayout.LayoutParams pLeftLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1.0f);
        pLeftLp.rightMargin = dp(4);
        padRow1.addView(dubThrowPad, pLeftLp);

        final StudioPadView springSplashPad = new StudioPadView(
                this, "MOMENTARY TANK", "HOLD: SPRING SPLASH", "#14B8A6", false);
        springSplashPad.setOnTouchListener(new View.OnTouchListener() {
            @Override
            public boolean onTouch(View v, MotionEvent event) {
                int a = event.getActionMasked();
                if (a == MotionEvent.ACTION_DOWN) {
                    springSplashPad.setPadState("TANK MAXIMUM", "SPRING SPLASH!", "#14B8A6", true);
                    sendFxCommand("spring_splash", 1.0f);
                    return true;
                } else if (a == MotionEvent.ACTION_UP || a == MotionEvent.ACTION_CANCEL) {
                    springSplashPad.setPadState("MOMENTARY TANK", "HOLD: SPRING SPLASH", "#14B8A6", false);
                    sendFxCommand("spring_splash", 0.0f);
                    return true;
                }
                return false;
            }
        });
        LinearLayout.LayoutParams pRightLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1.0f);
        pRightLp.leftMargin = dp(4);
        padRow1.addView(springSplashPad, pRightLp);
        mainPage.addView(padRow1, padRow1Lp);

        LinearLayout padRow2 = new LinearLayout(this);
        padRow2.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams padRow2Lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 0.88f);
        padRow2Lp.bottomMargin = dp(7);

        final StudioPadView dubHornPad = new StudioPadView(
                this, "KING TUBBY HPF", "HOLD: DUB HORN EQ", "#F59E0B", false);
        dubHornPad.setOnTouchListener(new View.OnTouchListener() {
            @Override
            public boolean onTouch(View v, MotionEvent event) {
                int a = event.getActionMasked();
                if (a == MotionEvent.ACTION_DOWN) {
                    dubHornPad.setPadState("1.35kHz RESONANCE", "HORN EQ ACTIVE", "#F59E0B", true);
                    sendFxCommand("dub_horn", 1.0f);
                    return true;
                } else if (a == MotionEvent.ACTION_UP || a == MotionEvent.ACTION_CANCEL) {
                    dubHornPad.setPadState("KING TUBBY HPF", "HOLD: DUB HORN EQ", "#F59E0B", false);
                    sendFxCommand("dub_horn", 0.0f);
                    return true;
                }
                return false;
            }
        });
        padRow2.addView(dubHornPad, pLeftLp);

        final StudioPadView dryPad = new StudioPadView(
                this, "MASTER FX ENGINE", "FX ACTIVE (TAP DRY)", "#10B981", false);
        dryPad.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                isDryBypass = !isDryBypass;
                if (isDryBypass) {
                    dryPad.setPadState("BYPASS ENGAGED", "DRY VOCAL (FX CUT)", "#F97316", true);
                    sendFxCommand("bypass_all", 1.0f);
                } else {
                    dryPad.setPadState("MASTER FX ENGINE", "FX ACTIVE (TAP DRY)", "#10B981", false);
                    sendFxCommand("bypass_all", 0.0f);
                }
            }
        });
        padRow2.addView(dryPad, pRightLp);
        mainPage.addView(padRow2, padRow2Lp);

        // ====================================================================
        // 5. DUB ECHO RHYTHM SUBDIVISION SELECTOR (Recessed Segmented Capsule)
        // ====================================================================
        LinearLayout rateRow = new LinearLayout(this);
        rateRow.setOrientation(LinearLayout.HORIZONTAL);
        rateRow.setPadding(dp(3), dp(3), dp(3), dp(3));
        rateRow.setBackground(roundedBg("#0B0F19", 10, "#1E293B"));
        LinearLayout.LayoutParams rateRowLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 0.56f);
        rateRowLp.bottomMargin = dp(7);

        final Button[] rateBtns = new Button[3];
        final String[] rateLabels = new String[]{"1/8D SKANK", "1/4 ROOTS", "1/8T STEPPAS"};
        for (int rIdx = 0; rIdx < 3; rIdx++) {
            final int mode = rIdx;
            Button rb = new Button(this);
            stripButtonShadow(rb);
            rb.setText(rateLabels[rIdx]);
            rb.setTextSize(10.0f);
            rb.setTypeface(Typeface.DEFAULT_BOLD);
            rb.setAllCaps(false);
            rb.setMinHeight(0);
            rb.setMinimumHeight(0);
            rb.setPadding(dp(4), 0, dp(4), 0);
            boolean active = (rIdx == 0);
            rb.setTextColor(active ? Color.parseColor("#041E2B") : Color.parseColor("#94A3B8"));
            rb.setBackground(roundedBg(active ? "#38BDF8" : "#00000000", 7, active ? "#7DD3FC" : null));
            rb.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    for (int k = 0; k < 3; k++) {
                        boolean sel = (k == mode);
                        rateBtns[k].setTextColor(sel ? Color.parseColor("#041E2B") : Color.parseColor("#94A3B8"));
                        rateBtns[k].setBackground(roundedBg(sel ? "#38BDF8" : "#00000000", 7, sel ? "#7DD3FC" : null));
                    }
                    sendFxCommand("echo_rate", (float) mode);
                }
            });
            rateBtns[rIdx] = rb;
            LinearLayout.LayoutParams rLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1.0f);
            if (rIdx > 0) rLp.leftMargin = dp(3);
            rateRow.addView(rb, rLp);
        }
        mainPage.addView(rateRow, rateRowLp);

        // ====================================================================
        // 6. TACTILE STUDIO RIBBON MACRO FADERS (1-to-1 with Ableton Rack Macros)
        // ====================================================================
        LinearLayout slidersCard = new LinearLayout(this);
        slidersCard.setOrientation(LinearLayout.VERTICAL);
        slidersCard.setPadding(dp(10), dp(8), dp(10), dp(8));
        slidersCard.setBackground(roundedGradientBg("#111726", "#0B0F19", 12, "#1E293B", 1));
        LinearLayout.LayoutParams slidersCardLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 4.35f);
        slidersCardLp.bottomMargin = dp(7);

        LinearLayout rackHeader = new LinearLayout(this);
        rackHeader.setOrientation(LinearLayout.HORIZONTAL);
        rackHeader.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams rhLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        rhLp.bottomMargin = dp(5);

        TextView rackTitle = new TextView(this);
        rackTitle.setText("DUB FX MACRO RACK  •  TOUCH RIBBON FADERS");
        rackTitle.setTextColor(Color.parseColor("#64748B"));
        rackTitle.setTextSize(8.8f);
        rackTitle.setTypeface(Typeface.DEFAULT_BOLD);
        rackTitle.setLetterSpacing(0.08f);
        rackHeader.addView(rackTitle, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f));
        slidersCard.addView(rackHeader, rhLp);

        // Macro 1: Dub Echo Mix
        addCompactMacroSlider(slidersCard, "DUB ECHO", "%", 35, "#38BDF8", "echo_mix");
        // Macro 2: Echo Feedback
        addCompactMacroSlider(slidersCard, "ECHO FDBK", "%", 35, "#A78BFA", "echo_fb");
        // Macro 3: Dub Filter Sweep
        addCompactMacroSlider(slidersCard, "DUB FILTER", "%", 0, "#FACC15", "dub_filter");
        // Macro 4: Spring Reverb
        addCompactMacroSlider(slidersCard, "SPRING REV", "%", 30, "#2DD4BF", "spring_wet");
        // Macro 5 & 6: Tube Warmth & Reggae Tone
        addCompactDualMacroSlider(slidersCard, "TUBE & TONE", "%", 45, "#FB923C", "tube_warm", "reggae_tone");
        // Macro 8: Noise Gate Threshold
        addCompactMacroSlider(slidersCard, "NOISE GATE", "%", 28, "#34D399", "gate_thresh");

        // Preamp Gain (-12dB to +24dB, default +0.0dB)
        gainLinear = 1.0f;
        final TextView gainLabel = new TextView(this);
        gainLabel.setText("MIC GAIN: +0dB");

        StudioRibbonFader gainFader = new StudioRibbonFader(
                this,
                "MIC PREAMP GAIN",
                "+0dB",
                72,
                24,
                "#60A5FA",
                new OnFaderChangeListener() {
                    @Override
                    public String onValueChanged(int progress, boolean isFinal) {
                        float db = (progress - 24) * 0.5f;
                        gainLinear = (float) Math.pow(10.0, db / 20.0);
                        String formatted = String.format("%s%.0fdB", (db >= 0 ? "+" : ""), db);
                        gainLabel.setText("MIC GAIN: " + formatted);
                        return formatted;
                    }
                }
        );
        LinearLayout.LayoutParams gainLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.0f);
        slidersCard.addView(gainFader, gainLp);
        mainPage.addView(slidersCard, slidersCardLp);

        // ====================================================================
        // 7. HARDWARE DSP BYPASS STRIP (GATE | TUNE | ECHO | SPRING | TUBE | AFC)
        // ====================================================================
        LinearLayout fxToggleRow = new LinearLayout(this);
        fxToggleRow.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams toggleRowLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 0.64f);
        toggleRowLp.bottomMargin = dp(7);

        final StudioToggleView gateBtn = new StudioToggleView(this, "GATE", true, "#10B981");
        gateBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                isGateOn = !isGateOn;
                gateBtn.setActive(isGateOn);
                sendFxCommand("gate_on", isGateOn ? 1.0f : 0.0f);
            }
        });
        addWeightedToggle(fxToggleRow, gateBtn, false);

        final StudioToggleView pitchBtn = new StudioToggleView(this, "TUNE", true, "#A855F7");
        pitchBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                isPitchOn = !isPitchOn;
                pitchBtn.setActive(isPitchOn);
                sendFxCommand("pitch_on", isPitchOn ? 1.0f : 0.0f);
            }
        });
        addWeightedToggle(fxToggleRow, pitchBtn, true);

        final StudioToggleView echoBtn = new StudioToggleView(this, "ECHO", true, "#38BDF8");
        echoBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                isEchoOn = !isEchoOn;
                echoBtn.setActive(isEchoOn);
                sendFxCommand("echo_on", isEchoOn ? 1.0f : 0.0f);
            }
        });
        addWeightedToggle(fxToggleRow, echoBtn, true);

        final StudioToggleView springBtn = new StudioToggleView(this, "SPRING", true, "#2DD4BF");
        springBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                isSpringOn = !isSpringOn;
                springBtn.setActive(isSpringOn);
                sendFxCommand("spring_on", isSpringOn ? 1.0f : 0.0f);
            }
        });
        addWeightedToggle(fxToggleRow, springBtn, true);

        final StudioToggleView warmBtn = new StudioToggleView(this, "TUBE", true, "#FB923C");
        warmBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                isWarmOn = !isWarmOn;
                warmBtn.setActive(isWarmOn);
                sendFxCommand("warm_on", isWarmOn ? 1.0f : 0.0f);
            }
        });
        addWeightedToggle(fxToggleRow, warmBtn, true);

        final StudioToggleView isoBtn = new StudioToggleView(this, "AFC", true, "#F43F5E");
        isoBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                isVocalIsoOn = !isVocalIsoOn;
                isoBtn.setActive(isVocalIsoOn);
                try {
                    nativeSetVocalIso(isVocalIsoOn ? 1 : 0);
                } catch (Throwable ignored) {}
            }
        });
        addWeightedToggle(fxToggleRow, isoBtn, true);
        mainPage.addView(fxToggleRow, toggleRowLp);

        // ====================================================================
        // 8. MASTER STAGE TRANSPORT DOCK: [ MIC ON / MUTE ] + [ REC ABLETON ]
        // ====================================================================
        LinearLayout bottomRow = new LinearLayout(this);
        bottomRow.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams bottomRowLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 0.82f);

        muteBtn = new Button(this);
        stripButtonShadow(muteBtn);
        muteBtn.setText("● MIC LIVE (TAP MUTE)");
        muteBtn.setTextColor(Color.WHITE);
        muteBtn.setTextSize(11.5f);
        muteBtn.setTypeface(Typeface.DEFAULT_BOLD);
        muteBtn.setAllCaps(false);
        muteBtn.setBackground(roundedGradientBg("#0284C7", "#0369A1", 10, "#38BDF8", 1));
        muteBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                isMuted = !isMuted;
                if (isMuted) {
                    muteBtn.setText("MUTED (TAP UNMUTE)");
                    muteBtn.setBackground(roundedGradientBg("#DC2626", "#991B1B", 10, "#F87171", 1));
                } else {
                    muteBtn.setText("● MIC LIVE (TAP MUTE)");
                    muteBtn.setBackground(roundedGradientBg("#0284C7", "#0369A1", 10, "#38BDF8", 1));
                }
            }
        });
        LinearLayout.LayoutParams muteLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1.15f);
        muteLp.rightMargin = dp(5);
        bottomRow.addView(muteBtn, muteLp);

        recBtn = new Button(this);
        stripButtonShadow(recBtn);
        recBtn.setText("● REC ABLETON");
        recBtn.setTextColor(Color.parseColor("#F8FAFC"));
        recBtn.setTextSize(11.5f);
        recBtn.setTypeface(Typeface.DEFAULT_BOLD);
        recBtn.setAllCaps(false);
        recBtn.setBackground(roundedGradientBg("#1E293B", "#0F172A", 10, "#475569", 1));
        recBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                isRecordingClip = !isRecordingClip;
                if (isRecordingClip) {
                    recBtn.setText("■ STOP RECORDING");
                    recBtn.setBackground(roundedGradientBg("#EF4444", "#B91C1C", 10, "#FCA5A5", 1));
                    sendFxCommand("remote_rec", 1.0f);
                } else {
                    recBtn.setText("● REC ABLETON");
                    recBtn.setBackground(roundedGradientBg("#1E293B", "#0F172A", 10, "#475569", 1));
                    sendFxCommand("remote_rec", 0.0f);
                }
            }
        });
        LinearLayout.LayoutParams recLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1.0f);
        recLp.leftMargin = dp(5);
        bottomRow.addView(recBtn, recLp);

        mainPage.addView(bottomRow, bottomRowLp);

        // ====================================================================
        // SECONDARY PAGE: 7-TRACK ABLETON SESSION MIXER (Full-Height Studio Strips)
        // ====================================================================
        LinearLayout mixerHeader = new LinearLayout(this);
        mixerHeader.setOrientation(LinearLayout.HORIZONTAL);
        mixerHeader.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams mhLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        mhLp.bottomMargin = dp(10);

        LinearLayout mixerTitleCol = new LinearLayout(this);
        mixerTitleCol.setOrientation(LinearLayout.VERTICAL);

        TextView mixerTitle = new TextView(this);
        mixerTitle.setText("ABLETON SESSION MIXER");
        mixerTitle.setTextColor(Color.WHITE);
        mixerTitle.setTextSize(16.0f);
        mixerTitle.setTypeface(Typeface.create("sans-serif-black", Typeface.BOLD));
        mixerTitle.setLetterSpacing(0.05f);
        mixerTitleCol.addView(mixerTitle);

        TextView mixerSub = new TextView(this);
        mixerSub.setText("7 LIVE TRACKS  •  BIDIRECTIONAL OSC BRIDGE");
        mixerSub.setTextColor(Color.parseColor("#64748B"));
        mixerSub.setTextSize(8.5f);
        mixerSub.setTypeface(Typeface.MONOSPACE);
        mixerTitleCol.addView(mixerSub);

        mixerHeader.addView(mixerTitleCol, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f));

        Button topBackBtn = new Button(this);
        stripButtonShadow(topBackBtn);
        topBackBtn.setText("◂ FX CONSOLE");
        topBackBtn.setTextColor(Color.parseColor("#0B0E14"));
        topBackBtn.setTextSize(10.0f);
        topBackBtn.setTypeface(Typeface.DEFAULT_BOLD);
        topBackBtn.setAllCaps(false);
        topBackBtn.setMinHeight(0);
        topBackBtn.setMinimumHeight(0);
        topBackBtn.setPadding(dp(12), dp(6), dp(12), dp(6));
        topBackBtn.setBackground(roundedBg("#38BDF8", 10, "#7DD3FC"));
        mixerHeader.addView(topBackBtn);

        mixerPage.addView(mixerHeader, mhLp);

        Button backToFxBtn = new Button(this);
        stripButtonShadow(backToFxBtn);
        backToFxBtn.setText("◂ BACK TO REGGAE DUB CONSOLE");
        backToFxBtn.setTextColor(Color.parseColor("#0B0E14"));
        backToFxBtn.setTextSize(11.5f);
        backToFxBtn.setTypeface(Typeface.DEFAULT_BOLD);
        backToFxBtn.setAllCaps(false);
        backToFxBtn.setBackground(roundedBg("#FACC15", 10, "#FDE047"));

        View.OnClickListener openMixerListener = new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                mainPage.setVisibility(View.GONE);
                mixerPage.setVisibility(View.VISIBLE);
            }
        };
        View.OnClickListener closeMixerListener = new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                mixerPage.setVisibility(View.GONE);
                mainPage.setVisibility(View.VISIBLE);
            }
        };
        topMixerBtn.setOnClickListener(openMixerListener);
        topBackBtn.setOnClickListener(closeMixerListener);
        backToFxBtn.setOnClickListener(closeMixerListener);

        final String[] trackNames = new String[]{
                "1: Taxi Kit",
                "2: Meld Bass",
                "3: LiveMic In",
                "4: Lead Vocal",
                "5: Guitar",
                "6: Main",
                "7: Audio"
        };
        final String[] trackAccents = new String[]{
                "#38BDF8",
                "#A78BFA",
                "#34D399",
                "#FACC15",
                "#FB923C",
                "#F43F5E",
                "#2DD4BF"
        };
        final boolean[] trackMuted = new boolean[]{false, false, true, false, false, false, false};
        final boolean[] trackSolo = new boolean[]{false, false, false, false, false, false, false};

        for (int i = 0; i < trackNames.length; i++) {
            final int tIdx = i;
            LinearLayout trkRow = new LinearLayout(this);
            trkRow.setOrientation(LinearLayout.HORIZONTAL);
            trkRow.setGravity(Gravity.CENTER_VERTICAL);
            trkRow.setPadding(dp(8), dp(6), dp(8), dp(6));
            trkRow.setBackground(roundedGradientBg("#111726", "#0B0F19", 10, "#1E293B", 1));
            LinearLayout.LayoutParams trkRowLp = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.0f);
            trkRowLp.bottomMargin = dp(6);

            StudioRibbonFader volFader = new StudioRibbonFader(
                    this,
                    trackNames[i].toUpperCase(),
                    "85%",
                    100,
                    85,
                    trackAccents[i],
                    new OnFaderChangeListener() {
                        private long lastVolSent = 0;
                        @Override
                        public String onValueChanged(int progress, boolean isFinal) {
                            long now = System.currentTimeMillis();
                            if (isFinal || now - lastVolSent > 35 || progress == 0 || progress == 85 || progress == 100) {
                                lastVolSent = now;
                                sendFxCommand("trk_vol_" + tIdx, progress / 100.0f);
                            }
                            return progress + "%";
                        }
                    }
            );
            trkRow.addView(volFader, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1.0f));

            final Button mBtn = new Button(this);
            stripButtonShadow(mBtn);
            mBtn.setText(trackMuted[i] ? "MUTE" : "ON");
            mBtn.setTextColor(Color.WHITE);
            mBtn.setTextSize(9.5f);
            mBtn.setTypeface(Typeface.DEFAULT_BOLD);
            mBtn.setPadding(0, 0, 0, 0);
            mBtn.setBackground(roundedBg(trackMuted[i] ? "#EF4444" : "#10B981", 8, null));
            LinearLayout.LayoutParams mLp = new LinearLayout.LayoutParams(dp(46), LinearLayout.LayoutParams.MATCH_PARENT);
            mLp.leftMargin = dp(6);
            mBtn.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    trackMuted[tIdx] = !trackMuted[tIdx];
                    mBtn.setText(trackMuted[tIdx] ? "MUTE" : "ON");
                    mBtn.setBackground(roundedBg(trackMuted[tIdx] ? "#EF4444" : "#10B981", 8, null));
                    sendFxCommand("trk_mute_" + tIdx, trackMuted[tIdx] ? 1.0f : 0.0f);
                }
            });
            trkRow.addView(mBtn, mLp);

            final Button sBtn = new Button(this);
            stripButtonShadow(sBtn);
            sBtn.setText("SOLO");
            sBtn.setTextColor(Color.WHITE);
            sBtn.setTextSize(9.5f);
            sBtn.setTypeface(Typeface.DEFAULT_BOLD);
            sBtn.setPadding(0, 0, 0, 0);
            sBtn.setBackground(roundedBg("#1E293B", 8, "#334155"));
            LinearLayout.LayoutParams sLp = new LinearLayout.LayoutParams(dp(44), LinearLayout.LayoutParams.MATCH_PARENT);
            sLp.leftMargin = dp(5);
            sBtn.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    trackSolo[tIdx] = !trackSolo[tIdx];
                    sBtn.setBackground(roundedBg(trackSolo[tIdx] ? "#0284C7" : "#1E293B", 8,
                            trackSolo[tIdx] ? "#38BDF8" : "#334155"));
                    sendFxCommand("trk_solo_" + tIdx, trackSolo[tIdx] ? 1.0f : 0.0f);
                }
            });
            trkRow.addView(sBtn, sLp);

            mixerPage.addView(trkRow, trkRowLp);
        }

        LinearLayout.LayoutParams backBtnLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(48));
        backBtnLp.topMargin = dp(2);
        mixerPage.addView(backToFxBtn, backBtnLp);

        root.addView(mainPage, pageLp);
        root.addView(mixerPage, pageLp);
        setContentView(root);
    }

    private void addWeightedToggle(LinearLayout row, View v, boolean leftGap) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1.0f);
        if (leftGap) lp.leftMargin = dp(4);
        row.addView(v, lp);
    }

    /**
     * Custom-Drawn Hardware Performance Pad (Dark Anodized Surface + Top Glowing LED Strip).
     */
    private class StudioPadView extends View {
        private String subLabel;
        private String mainLabel;
        private int accentColor;
        private boolean isActive;

        private final Paint bgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint borderPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint ledPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint subPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint mainPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF rect = new RectF();
        private final RectF ledRect = new RectF();

        public StudioPadView(Context ctx, String subLabel, String mainLabel, String accentHex, boolean active) {
            super(ctx);
            borderPaint.setStyle(Paint.Style.STROKE);
            borderPaint.setStrokeWidth(dp(1));

            subPaint.setTextSize(dp(8.5f));
            subPaint.setTypeface(Typeface.create(Typeface.MONOSPACE, Typeface.BOLD));
            subPaint.setTextAlign(Paint.Align.CENTER);

            mainPaint.setColor(Color.WHITE);
            mainPaint.setTextSize(dp(11.5f));
            mainPaint.setTypeface(Typeface.create(Typeface.DEFAULT, Typeface.BOLD));
            mainPaint.setTextAlign(Paint.Align.CENTER);

            setPadState(subLabel, mainLabel, accentHex, active);
        }

        public void setPadState(String sub, String main, String accentHex, boolean active) {
            this.subLabel = sub;
            this.mainLabel = main;
            this.accentColor = Color.parseColor(accentHex);
            this.isActive = active;
            invalidate();
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            int w = getWidth();
            int h = getHeight();
            if (w <= 0 || h <= 0) return;

            float pad = dp(1);
            float r = dp(10);
            rect.set(pad, pad, w - pad, h - pad);

            int topColor = isActive
                    ? Color.argb(190, Color.red(accentColor), Color.green(accentColor), Color.blue(accentColor))
                    : Color.argb(38, Color.red(accentColor), Color.green(accentColor), Color.blue(accentColor));
            int botColor = isActive
                    ? Color.parseColor("#0F172A")
                    : Color.parseColor("#0B0F19");
            bgPaint.setShader(new LinearGradient(0, 0, 0, h, topColor, botColor, Shader.TileMode.CLAMP));
            canvas.drawRoundRect(rect, r, r, bgPaint);

            // Top illuminated LED bar
            float ledW = w * 0.42f;
            float ledH = dp(3);
            ledRect.set((w - ledW) * 0.5f, pad + dp(1), (w + ledW) * 0.5f, pad + dp(1) + ledH);
            ledPaint.setColor(isActive ? Color.WHITE : accentColor);
            canvas.drawRoundRect(ledRect, dp(2), dp(2), ledPaint);

            borderPaint.setColor(isActive ? accentColor : Color.parseColor("#243044"));
            canvas.drawRoundRect(rect, r, r, borderPaint);

            subPaint.setColor(isActive ? Color.WHITE : accentColor);
            canvas.drawText(subLabel, w * 0.5f, h * 0.41f, subPaint);
            canvas.drawText(mainLabel, w * 0.5f, h * 0.72f, mainPaint);
        }
    }

    /**
     * Custom-Drawn Hardware DSP Bypass Switch (Unified Dark Chassis + Top LED Indicator).
     */
    private class StudioToggleView extends View {
        private final String name;
        private boolean isOn;
        private final int accentColor;

        private final Paint bgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint borderPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint ledPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint namePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint statePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF rect = new RectF();
        private final RectF ledRect = new RectF();

        public StudioToggleView(Context ctx, String name, boolean on, String accentHex) {
            super(ctx);
            this.name = name;
            this.isOn = on;
            this.accentColor = Color.parseColor(accentHex);

            borderPaint.setStyle(Paint.Style.STROKE);
            borderPaint.setStrokeWidth(dp(1));

            namePaint.setTextSize(dp(10.0f));
            namePaint.setTypeface(Typeface.create(Typeface.DEFAULT, Typeface.BOLD));
            namePaint.setTextAlign(Paint.Align.CENTER);

            statePaint.setTextSize(dp(7.5f));
            statePaint.setTypeface(Typeface.create(Typeface.MONOSPACE, Typeface.BOLD));
            statePaint.setTextAlign(Paint.Align.CENTER);
        }

        public void setActive(boolean on) {
            this.isOn = on;
            invalidate();
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            int w = getWidth();
            int h = getHeight();
            if (w <= 0 || h <= 0) return;

            float pad = dp(1);
            float r = dp(8);
            rect.set(pad, pad, w - pad, h - pad);

            int topC = isOn
                    ? Color.argb(42, Color.red(accentColor), Color.green(accentColor), Color.blue(accentColor))
                    : Color.parseColor("#0B0F19");
            int botC = Color.parseColor("#0B0F19");
            bgPaint.setShader(new LinearGradient(0, 0, 0, h, topC, botC, Shader.TileMode.CLAMP));
            canvas.drawRoundRect(rect, r, r, bgPaint);

            // Top glowing hardware LED bar
            float ledW = w * 0.48f;
            float ledH = dp(2.5f);
            ledRect.set((w - ledW) * 0.5f, pad + dp(3), (w + ledW) * 0.5f, pad + dp(3) + ledH);
            ledPaint.setColor(isOn ? accentColor : Color.parseColor("#1E293B"));
            canvas.drawRoundRect(ledRect, dp(2), dp(2), ledPaint);

            borderPaint.setColor(isOn ? Color.parseColor("#28354C") : Color.parseColor("#161E2E"));
            canvas.drawRoundRect(rect, r, r, borderPaint);

            namePaint.setColor(isOn ? Color.parseColor("#F8FAFC") : Color.parseColor("#475569"));
            statePaint.setColor(isOn ? accentColor : Color.parseColor("#334155"));

            canvas.drawText(name, w * 0.5f, h * 0.55f, namePaint);
            canvas.drawText(isOn ? "ACTIVE" : "BYPASS", w * 0.5f, h * 0.83f, statePaint);
        }
    }

    private interface OnFaderChangeListener {
        String onValueChanged(int progress, boolean isFinal);
    }

    private void addCompactMacroSlider(
            LinearLayout parent,
            final String title,
            final String unit,
            int initialProgress,
            String colorHex,
            final String fxCmd) {
        StudioRibbonFader fader = new StudioRibbonFader(
                this,
                title,
                initialProgress + unit,
                100,
                initialProgress,
                colorHex,
                new OnFaderChangeListener() {
                    private long lastSent = 0;
                    @Override
                    public String onValueChanged(int progress, boolean isFinal) {
                        long now = System.currentTimeMillis();
                        if (isFinal || now - lastSent > 25 || progress == 0 || progress == 100) {
                            lastSent = now;
                            sendFxCommand(fxCmd, progress / 100.0f);
                        }
                        return progress + unit;
                    }
                }
        );
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.0f);
        lp.bottomMargin = dp(4);
        parent.addView(fader, lp);
    }

    private void addCompactDualMacroSlider(
            LinearLayout parent,
            final String title,
            final String unit,
            int initialProgress,
            String colorHex,
            final String fxCmd1,
            final String fxCmd2) {
        StudioRibbonFader fader = new StudioRibbonFader(
                this,
                title,
                initialProgress + unit,
                100,
                initialProgress,
                colorHex,
                new OnFaderChangeListener() {
                    private long lastSent = 0;
                    @Override
                    public String onValueChanged(int progress, boolean isFinal) {
                        long now = System.currentTimeMillis();
                        if (isFinal || now - lastSent > 30 || progress == 0 || progress == 100) {
                            lastSent = now;
                            float v = progress / 100.0f;
                            sendFxCommand(fxCmd1, v);
                            sendFxCommand(fxCmd2, v);
                        }
                        return progress + unit;
                    }
                }
        );
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.0f);
        lp.bottomMargin = dp(4);
        parent.addView(fader, lp);
    }

    /**
     * Custom Hardware-Accelerated Tactile Ribbon Fader View (Ableton / FabFilter style).
     */
    private class StudioRibbonFader extends View {
        private final String title;
        private String valueText;
        private final int max;
        private int progress;
        private final int accentColor;
        private final int fillStartColor;
        private final int fillEndColor;
        private final OnFaderChangeListener listener;

        private final Paint trackPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint tickPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint fillPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint borderPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint thumbPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint titlePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint valuePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF rect = new RectF();
        private final RectF fillRect = new RectF();
        private boolean isDragging = false;

        public StudioRibbonFader(
                Context ctx,
                String title,
                String initialValueText,
                int max,
                int initialProgress,
                String accentHex,
                OnFaderChangeListener listener) {
            super(ctx);
            this.title = title;
            this.valueText = initialValueText;
            this.max = Math.max(1, max);
            this.progress = initialProgress;
            this.accentColor = Color.parseColor(accentHex);
            this.fillStartColor = Color.argb(38, Color.red(accentColor), Color.green(accentColor), Color.blue(accentColor));
            this.fillEndColor = Color.argb(115, Color.red(accentColor), Color.green(accentColor), Color.blue(accentColor));
            this.listener = listener;

            trackPaint.setColor(Color.parseColor("#080B12"));
            trackPaint.setStyle(Paint.Style.FILL);

            tickPaint.setColor(Color.parseColor("#131B2B"));
            tickPaint.setStrokeWidth(dp(1));

            borderPaint.setStyle(Paint.Style.STROKE);
            borderPaint.setStrokeWidth(dp(1));
            borderPaint.setColor(Color.parseColor("#1E293B"));

            thumbPaint.setColor(accentColor);
            thumbPaint.setStyle(Paint.Style.FILL);

            titlePaint.setColor(Color.parseColor("#E2E8F0"));
            titlePaint.setTextSize(dp(10));
            titlePaint.setTypeface(Typeface.create(Typeface.DEFAULT, Typeface.BOLD));

            valuePaint.setColor(accentColor);
            valuePaint.setTextSize(dp(11));
            valuePaint.setTypeface(Typeface.create(Typeface.MONOSPACE, Typeface.BOLD));
            valuePaint.setTextAlign(Paint.Align.RIGHT);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            int w = getWidth();
            int h = getHeight();
            if (w <= 0 || h <= 0) return;

            float pad = dp(1);
            float r = dp(7);
            rect.set(pad, pad, w - pad, h - pad);

            // 1. Recessed studio well
            canvas.drawRoundRect(rect, r, r, trackPaint);

            // Subtle 25%, 50%, 75% calibration ticks
            for (int t = 1; t <= 3; t++) {
                float tx = w * (t * 0.25f);
                canvas.drawLine(tx, pad + dp(4), tx, h - pad - dp(4), tickPaint);
            }

            // 2. Luminous ribbon fill proportional to progress
            float norm = Math.max(0f, Math.min(1f, (float) progress / (float) max));
            float fillRight = pad + norm * (w - 2 * pad);
            if (fillRight > pad + dp(2)) {
                fillRect.set(pad, pad, fillRight, h - pad);
                fillPaint.setShader(new LinearGradient(
                        pad, 0, fillRight, 0,
                        fillStartColor, fillEndColor, Shader.TileMode.CLAMP));
                canvas.drawRoundRect(fillRect, r, r, fillPaint);

                // Vertical glowing thumb indicator bar at fill edge
                float thumbW = dp(3);
                float thumbX = Math.max(pad + r * 0.5f, Math.min(w - pad - thumbW, fillRight - thumbW));
                canvas.drawRoundRect(thumbX, pad + dp(3), thumbX + thumbW, h - pad - dp(3), dp(2), dp(2), thumbPaint);
            }

            // 3. Outer border (highlights in accent color while dragging)
            borderPaint.setColor(isDragging ? accentColor : Color.parseColor("#1E293B"));
            canvas.drawRoundRect(rect, r, r, borderPaint);

            // 4. Crisp overlaid title (left) and live tabular readout (right)
            Paint.FontMetrics fm = titlePaint.getFontMetrics();
            float textY = h * 0.5f - (fm.ascent + fm.descent) * 0.5f;
            canvas.drawText(title, dp(11), textY, titlePaint);
            canvas.drawText(valueText, w - dp(11), textY, valuePaint);
        }

        @Override
        public boolean onTouchEvent(MotionEvent event) {
            int action = event.getActionMasked();
            if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_MOVE || action == MotionEvent.ACTION_UP) {
                if (action == MotionEvent.ACTION_DOWN && getParent() != null) {
                    getParent().requestDisallowInterceptTouchEvent(true);
                    isDragging = true;
                }
                int w = getWidth();
                if (w > 0) {
                    float norm = Math.max(0f, Math.min(1f, event.getX() / (float) w));
                    int newProg = Math.round(norm * max);
                    boolean isFinal = (action == MotionEvent.ACTION_UP);
                    if (newProg != progress || isFinal) {
                        progress = newProg;
                        if (listener != null) {
                            valueText = listener.onValueChanged(progress, isFinal);
                        }
                    }
                }
                if (action == MotionEvent.ACTION_UP) {
                    isDragging = false;
                }
                invalidate();
                return true;
            } else if (action == MotionEvent.ACTION_CANCEL) {
                isDragging = false;
                invalidate();
                return true;
            }
            return super.onTouchEvent(event);
        }
    }

    private final ExecutorService fxExecutor = Executors.newSingleThreadExecutor();

    private void sendFxCommand(final String cmd, final float val) {
        fxExecutor.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    URL url = new URL("http://127.0.0.1:8765/api/fx?cmd=" + cmd + "&val=" + val);
                    HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                    conn.setConnectTimeout(150);
                    conn.setReadTimeout(150);
                    conn.getResponseCode();
                } catch (Exception ignored) {}
            }
        });
    }

    static {
        try {
            System.loadLibrary("aaudiomic");
        } catch (Throwable ignored) {}
    }

    private static volatile int activeEngineGen = 0;

    private native int nativeStartAAudio();
    private native int nativeReadAAudio(short[] outArray, int numFrames);
    private native void nativeStopAAudio();
    private native void nativeSetVocalIso(int enabled);
    private native int nativeGetDspTimeUs();
    private native int nativeGetFeedbackStats(short[] outStats);

    private synchronized void startFastTrackEngine() {
        if (isRunning && audioThread != null && audioThread.isAlive()) return;
        isRunning = true;
        final int myGen = ++activeEngineGen;

        audioThread = new Thread(new Runnable() {
            @Override
            public void run() {
                Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO);
                runLowLatencyCaptureLoop(myGen);
            }
        }, "LiveAirMic-UrgentAudio");
        audioThread.start();
    }

    private AudioRecord createFastTrackAudioRecord() {
        int minBuf = AudioRecord.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT
        );
        int targetBufBytes = Math.max(minBuf, BYTES_PER_QUANTUM * 2);

        int[] sourcesToTry = new int[]{
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                MediaRecorder.AudioSource.UNPROCESSED,
                MediaRecorder.AudioSource.MIC
        };

        for (int src : sourcesToTry) {
            try {
                AudioRecord rec = new AudioRecord(
                        src,
                        SAMPLE_RATE,
                        AudioFormat.CHANNEL_IN_MONO,
                        AudioFormat.ENCODING_PCM_16BIT,
                        targetBufBytes
                );
                if (rec.getState() == AudioRecord.STATE_INITIALIZED) {
                    actualAudioSource = src;
                    return rec;
                }
                rec.release();
            } catch (Exception ignored) {}
        }
        return null;
    }

    private void runLowLatencyCaptureLoop(final int myGen) {
        synchronized (engineRunLock) {
            if (!isRunning || myGen != activeEngineGen) {
                return;
            }
            runLowLatencyCaptureLoopLocked(myGen);
        }
    }

    private void runLowLatencyCaptureLoopLocked(final int myGen) {
        boolean usingAAudio = false;
        AudioRecord recorder = null;
        try {
            int burst = nativeStartAAudio();
            if (burst > 0) {
                usingAAudio = true;
                hwFramesPerBurst = burst;
                actualAudioSource = MediaRecorder.AudioSource.UNPROCESSED;
            }
        } catch (Throwable ignored) {}

        if (!usingAAudio) {
            recorder = createFastTrackAudioRecord();
            if (recorder == null) {
                return;
            }
            recorder.startRecording();
        }

        short[] pcmShorts = new short[QUANTUM_FRAMES];
        byte[] outBytes = new byte[BYTES_PER_QUANTUM];
        ByteBuffer byteBuf = ByteBuffer.wrap(outBytes).order(ByteOrder.LITTLE_ENDIAN);

        Socket socket = null;
        OutputStream out = null;
        long lastConnectAttempt = 0;

        float hpPrevX = 0.0f;
        float hpPrevY = 0.0f;
        float lpStage1 = 0.0f;
        float lpStage2 = 0.0f;

        while (isRunning && myGen == activeEngineGen) {
            int r;
            if (usingAAudio) {
                r = nativeReadAAudio(pcmShorts, QUANTUM_FRAMES);
                if (r < 0) {
                    if (!isRunning || myGen != activeEngineGen) {
                        break;
                    }
                    try {
                        nativeStopAAudio();
                        Thread.sleep(80);
                        if (!isRunning || myGen != activeEngineGen) {
                            break;
                        }
                        int burst = nativeStartAAudio();
                        if (burst > 0) {
                            hwFramesPerBurst = burst;
                            continue;
                        }
                    } catch (Throwable ignored) {}
                    usingAAudio = false;
                    recorder = createFastTrackAudioRecord();
                    if (recorder != null) {
                        recorder.startRecording();
                    }
                    continue;
                }
            } else {
                if (recorder == null) {
                    recorder = createFastTrackAudioRecord();
                    if (recorder != null) {
                        recorder.startRecording();
                    } else {
                        try { Thread.sleep(100); } catch (InterruptedException ignored) {}
                        continue;
                    }
                }
                r = recorder.read(pcmShorts, 0, QUANTUM_FRAMES, AudioRecord.READ_BLOCKING);
                if (r < 0) {
                    try {
                        recorder.stop();
                        recorder.release();
                    } catch (Exception ignored) {}
                    recorder = null;
                    continue;
                }
            }
            if (r == 0) continue;
            lastAudioReadMs = System.currentTimeMillis();

            float peak = 0.0f;
            float sumSq = 0.0f;
            float g = isMuted ? 0.0f : gainLinear;
            byteBuf.clear();

            for (int i = 0; i < r; i++) {
                float raw = pcmShorts[i] / 32768.0f;
                float hp = 0.9889f * (hpPrevY + raw - hpPrevX);
                hpPrevX = raw;
                hpPrevY = hp;

                lpStage1 += 0.52f * (hp - lpStage1);
                lpStage2 += 0.52f * (lpStage1 - lpStage2);

                float s = lpStage2 * g;
                if (s > 0.98f) s = 0.98f;
                else if (s < -0.98f) s = -0.98f;

                float abs = Math.abs(s);
                if (abs > peak) peak = abs;
                sumSq += s * s;

                short outSample = (short) (s * 32767.0f);
                byteBuf.putShort(outSample);
            }

            if (out == null) {
                long now = System.currentTimeMillis();
                if (now - lastConnectAttempt > 400) {
                    lastConnectAttempt = now;
                    try {
                        socket = new Socket();
                        socket.setTcpNoDelay(true);
                        socket.setSendBufferSize(16384);
                        socket.connect(new InetSocketAddress("127.0.0.1", TCP_PORT), 300);
                        out = socket.getOutputStream();
                        isConnected = true;
                    } catch (Exception e) {
                        isConnected = false;
                        out = null;
                    }
                }
            }

            if (out != null) {
                try {
                    out.write(outBytes, 0, r * 2);
                    packetsSent++;
                } catch (Exception e) {
                    isConnected = false;
                    try { socket.close(); } catch (Exception ignored) {}
                    out = null;
                    socket = null;
                }
            }

            if (peak >= livePeak) {
                livePeak = peak;
            } else {
                livePeak = livePeak * 0.92f;
            }
            float rms = (float) Math.sqrt(sumSq / r);
            liveRms = rms > liveRms ? rms : (liveRms * 0.90f + rms * 0.10f);
            meterView.postInvalidateOnAnimation();
        }

        try {
            if (out != null) out.close();
            if (socket != null) socket.close();
        } catch (Exception ignored) {}
        try {
            if (usingAAudio) {
                if (!isRunning && myGen == activeEngineGen) {
                    nativeStopAAudio();
                }
            } else if (recorder != null) {
                recorder.stop();
                recorder.release();
            }
        } catch (Exception ignored) {}
    }

    @Override
    protected void onDestroy() {
        isRunning = false;
        super.onDestroy();
    }

    private int dp(float v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    /**
     * Vintage Analog Backlit VU Meter (Warm Incandescent Faceplate + Sweeping Needle + Ruby Peak Lamp).
     */
    private class FastMeterView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint arcPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint vuLogoPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint needlePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint shadowPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF rect = new RectF();
        private final RectF arcRect = new RectF();
        private long lastTextUpdate = 0;
        private float smoothVuNorm = 0.0f;

        private final float[] tickNorms = new float[]{
                0.00f, 0.18f, 0.31f, 0.43f, 0.56f, 0.68f, 0.75f, 0.83f, 0.91f, 1.00f
        };
        private final String[] tickLabels = new String[]{
                "-20", "-10", "-7", "-5", "-3", "-1", "0", "+1", "+2", "+3"
        };

        public FastMeterView(Context ctx) {
            super(ctx);
            arcPaint.setStyle(Paint.Style.STROKE);
            arcPaint.setStrokeCap(Paint.Cap.BUTT);

            textPaint.setTypeface(Typeface.create(Typeface.SERIF, Typeface.BOLD));
            textPaint.setTextAlign(Paint.Align.CENTER);

            vuLogoPaint.setTypeface(Typeface.create(Typeface.SERIF, Typeface.BOLD));
            vuLogoPaint.setTextAlign(Paint.Align.CENTER);
            vuLogoPaint.setColor(Color.parseColor("#3E2723"));

            needlePaint.setStyle(Paint.Style.STROKE);
            needlePaint.setStrokeCap(Paint.Cap.ROUND);

            shadowPaint.setStyle(Paint.Style.STROKE);
            shadowPaint.setStrokeCap(Paint.Cap.ROUND);
            shadowPaint.setColor(Color.argb(55, 35, 20, 5));
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            int w = getWidth();
            int h = getHeight();
            if (w <= 0 || h <= 0) return;

            float peak = livePeak;
            float rms = liveRms;
            float peakDb = peak > 1e-4f ? (float) (20.0 * Math.log10(peak)) : -96.0f;
            float rmsDb = rms > 1e-4f ? (float) (20.0 * Math.log10(rms)) : -96.0f;

            // Blend RMS + Peak so needle dances responsively with classic analog inertia
            float vuDb = rmsDb * 0.55f + peakDb * 0.45f + 3.0f;
            float targetNorm = (Math.max(-45.0f, Math.min(3.0f, vuDb)) + 45.0f) / 48.0f;
            if (targetNorm > smoothVuNorm) {
                smoothVuNorm += (targetNorm - smoothVuNorm) * 0.38f;
            } else {
                smoothVuNorm += (targetNorm - smoothVuNorm) * 0.18f;
            }

            // 1. Warm backlit incandescent amber faceplate
            float pad = dp(2);
            float cornerR = dp(8);
            rect.set(pad, pad, w - pad, h - pad);
            paint.setStyle(Paint.Style.FILL);
            paint.setShader(new LinearGradient(
                    0, 0, 0, h,
                    Color.parseColor("#FFF4D4"),
                    Color.parseColor("#DFB976"),
                    Shader.TileMode.CLAMP
            ));
            canvas.drawRoundRect(rect, cornerR, cornerR, paint);
            paint.setShader(null);

            canvas.save();
            canvas.clipRect(rect);

            // Top warm bulb glow highlight
            paint.setColor(Color.argb(45, 255, 250, 220));
            canvas.drawOval(w * 0.15f, -h * 0.35f, w * 0.85f, h * 0.55f, paint);

            // 2. Curved VU Scale Geometry (wide-angle studio arc spanning the full faceplate)
            float cx = w * 0.5f;
            float pivotY = h * 2.55f;
            float radius = h * 2.18f;
            float startDeg = -36.0f;
            float spanDeg = 72.0f;
            float zeroNorm = 0.75f; // 0 VU at 75% of scale
            float zeroDeg = startDeg + zeroNorm * spanDeg;

            arcRect.set(cx - radius, pivotY - radius, cx + radius, pivotY + radius);

            // Normal black scale arc (-20 to 0 VU)
            arcPaint.setStrokeWidth(dp(1.8f));
            arcPaint.setColor(Color.parseColor("#271B10"));
            canvas.drawArc(arcRect, -90.0f + startDeg, zeroNorm * spanDeg, false, arcPaint);

            // Red overload band (0 to +3 VU)
            arcPaint.setStrokeWidth(dp(4.0f));
            arcPaint.setColor(Color.parseColor("#C81E1E"));
            canvas.drawArc(arcRect, -90.0f + zeroDeg, (1.0f - zeroNorm) * spanDeg, false, arcPaint);

            // 3. Radial Tick Marks & Vintage Scale Numbers
            textPaint.setTextSize(dp(8.5f));
            for (int i = 0; i < tickNorms.length; i++) {
                float tn = tickNorms[i];
                float deg = startDeg + tn * spanDeg;
                double rad = Math.toRadians(deg);
                boolean isRed = tn > zeroNorm + 0.001f;
                boolean isMajor = (i == 0 || i == 1 || i == 4 || i == 6 || i == 9);

                float rInner = radius - dp(2);
                float rOuter = radius + dp(isMajor ? 6.5f : 4.0f);
                float x1 = cx + (float) (rInner * Math.sin(rad));
                float y1 = pivotY - (float) (rInner * Math.cos(rad));
                float x2 = cx + (float) (rOuter * Math.sin(rad));
                float y2 = pivotY - (float) (rOuter * Math.cos(rad));

                arcPaint.setStrokeWidth(dp(isMajor ? 1.8f : 1.1f));
                arcPaint.setColor(isRed ? Color.parseColor("#B91C1C") : Color.parseColor("#271B10"));
                canvas.drawLine(x1, y1, x2, y2, arcPaint);

                float rText = radius + dp(14.5f);
                float tx = cx + (float) (rText * Math.sin(rad));
                float ty = pivotY - (float) (rText * Math.cos(rad)) + dp(3);
                textPaint.setColor(isRed ? Color.parseColor("#B91C1C") : Color.parseColor("#271B10"));
                canvas.drawText(tickLabels[i], tx, ty, textPaint);
            }

            // 4. Classic "VU" Emblem & "100%" Sub-mark
            vuLogoPaint.setTextSize(dp(13.0f));
            vuLogoPaint.setLetterSpacing(0.14f);
            canvas.drawText("VU", cx, h * 0.76f, vuLogoPaint);

            // 5. Ruby "PEAK" Jewel Indicator Lamp (Top Right)
            boolean isClipping = peakDb > -6.0f;
            float lampX = w - dp(20);
            float lampY = dp(14);
            if (isClipping) {
                paint.setColor(Color.argb(95, 239, 68, 68));
                canvas.drawCircle(lampX, lampY, dp(8.0f), paint);
                paint.setColor(Color.parseColor("#FF2A2A"));
            } else {
                paint.setColor(Color.parseColor("#4A1818"));
            }
            canvas.drawCircle(lampX, lampY, dp(4.5f), paint);
            arcPaint.setStrokeWidth(dp(1.0f));
            arcPaint.setColor(Color.parseColor("#5C4028"));
            canvas.drawCircle(lampX, lampY, dp(4.5f), arcPaint);

            textPaint.setTextSize(dp(7.0f));
            textPaint.setColor(Color.parseColor("#4E342E"));
            canvas.drawText("PEAK", lampX - dp(18), lampY + dp(2.5f), textPaint);

            // 6. Sweeping Physical Needle + Drop Shadow
            float needleDeg = startDeg + smoothVuNorm * spanDeg;
            double needleRad = Math.toRadians(needleDeg);
            float needleLen = radius + dp(8);
            float tipX = cx + (float) (needleLen * Math.sin(needleRad));
            float tipY = pivotY - (float) (needleLen * Math.cos(needleRad));

            shadowPaint.setStrokeWidth(dp(2.4f));
            canvas.drawLine(cx + dp(2.5f), pivotY + dp(2.5f), tipX + dp(2.5f), tipY + dp(2.5f), shadowPaint);

            needlePaint.setStrokeWidth(dp(2.0f));
            needlePaint.setColor(Color.parseColor("#1A120B"));
            canvas.drawLine(cx, pivotY, tipX, tipY, needlePaint);

            // Orange-red precision pointer tip
            float tipStartLen = radius - dp(8);
            float tipStartX = cx + (float) (tipStartLen * Math.sin(needleRad));
            float tipStartY = pivotY - (float) (tipStartLen * Math.cos(needleRad));
            needlePaint.setColor(Color.parseColor("#DC2626"));
            canvas.drawLine(tipStartX, tipStartY, tipX, tipY, needlePaint);

            // 7. Brushed Bakelite Bottom Pivot Cap
            paint.setColor(Color.parseColor("#1C140D"));
            canvas.drawCircle(cx, h + dp(6), dp(18), paint);
            arcPaint.setStrokeWidth(dp(1.5f));
            arcPaint.setColor(Color.parseColor("#78552B"));
            canvas.drawCircle(cx, h + dp(6), dp(18), arcPaint);

            canvas.restore();

            // 8. Inner Brass/Bakelite Bezel Frame
            arcPaint.setStrokeWidth(dp(2.0f));
            arcPaint.setColor(Color.parseColor("#6B4C2B"));
            canvas.drawRoundRect(rect, cornerR, cornerR, arcPaint);

            long now = System.currentTimeMillis();
            if (now - lastTextUpdate > 60) {
                lastTextUpdate = now;
                String pStr = peakDb > -90f ? String.format("%.0f", peakDb) : "-∞";
                String rStr = rmsDb > -90f ? String.format("%.0f", rmsDb) : "-∞";
                dbLabel.setText("PK " + pStr + "  |  RMS " + rStr + " dB");

                if (isConnected && hwFramesPerBurst <= 192) {
                    latencyBadge.setText("● GREEN (2.7ms)");
                    latencyBadge.setTextColor(Color.parseColor("#052E16"));
                    latencyBadge.setBackground(roundedBg("#10B981", 12, "#34D399"));
                } else if (isConnected) {
                    latencyBadge.setText("● YELLOW");
                    latencyBadge.setTextColor(Color.parseColor("#0B0E14"));
                    latencyBadge.setBackground(roundedBg("#FACC15", 12, null));
                } else {
                    latencyBadge.setText("● OFFLINE");
                    latencyBadge.setTextColor(Color.WHITE);
                    latencyBadge.setBackground(roundedBg("#EF4444", 12, null));
                }

                try {
                    nativeGetFeedbackStats(afcStatsBuf);
                    boolean afcOn = afcStatsBuf[0] != 0;
                    int activeNotches = afcStatsBuf[1];
                    float papr = afcStatsBuf[2] / 10.0f;
                    int streak = afcStatsBuf[3];
                    int peakHz = afcStatsBuf[4];
                    int envGainPct = afcStatsBuf[9];
                    int dspUs = afcStatsBuf[11];

                    float isoDb = envGainPct > 1 ? (float) (20.0 * Math.log10(envGainPct / 100.0)) : -15.0f;

                    if (!afcOn) {
                        afcStatusBadge.setText("AFC: OFF");
                        afcStatusBadge.setTextColor(Color.WHITE);
                        afcStatusBadge.setBackground(roundedBg("#475569", 6, null));
                    } else if (activeNotches > 0) {
                        afcStatusBadge.setText("NOTCH LOCKED (" + activeNotches + ")");
                        afcStatusBadge.setTextColor(Color.WHITE);
                        afcStatusBadge.setBackground(roundedBg("#F43F5E", 6, null));
                    } else if (streak > 0 || papr > 28.0f) {
                        afcStatusBadge.setText("HOWL TRACKING");
                        afcStatusBadge.setTextColor(Color.parseColor("#0B0E14"));
                        afcStatusBadge.setBackground(roundedBg("#FACC15", 6, null));
                    } else {
                        afcStatusBadge.setText("AFC: CLEAR");
                        afcStatusBadge.setTextColor(Color.parseColor("#052E16"));
                        afcStatusBadge.setBackground(roundedBg("#10B981", 6, null));
                    }

                    afcMetricsLabel.setText(String.format(
                            "PAPR %.1f/42 | %dHz | ISO %.0fdB | %dµs",
                            papr, peakHz, isoDb, dspUs
                    ));

                    for (int k = 0; k < 4; k++) {
                        int nHz = afcStatsBuf[5 + k];
                        if (nHz > 0) {
                            notchBadges[k].setText("● N" + (k + 1) + " " + nHz + "Hz");
                            notchBadges[k].setTextColor(Color.WHITE);
                            notchBadges[k].setBackground(roundedBg("#881337", 6, "#F43F5E"));
                        } else {
                            notchBadges[k].setText("○ N" + (k + 1) + " IDLE");
                            notchBadges[k].setTextColor(Color.parseColor("#64748B"));
                            notchBadges[k].setBackground(roundedBg("#080B12", 6, "#1E293B"));
                        }
                    }
                } catch (Throwable ignored) {}
            }
        }
    }
}
