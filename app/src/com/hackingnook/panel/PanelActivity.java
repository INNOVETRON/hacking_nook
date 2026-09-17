package com.hackingnook.panel;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.BatteryManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.PowerManager;
import android.os.SystemClock;
import android.text.format.DateFormat;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.TextView;
import java.util.Date;

/** Fetch, preserve the dashboard as a screensaver, and sleep until an RTC alarm. */
public class PanelActivity extends Activity {
    private static final int AWAKE_FLAGS = WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
            | WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
            | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON;
    private static final long MANUAL_IDLE_MS = 60000L;
    private final Handler handler = new Handler();
    private ImageView image;
    private TextView status;
    private BatteryView battery;
    private View panel;
    private boolean resumed, sleeping, automatic, destroyed, fetching;
    private boolean requestedRefresh;
    private String fetchUrl;
    private volatile int requestId;

    private final Runnable idleSleep = new Runnable() {
        public void run() {
            if (resumed && !fetching) sleepNow();
        }
    };
    private final Runnable watchdog = new Runnable() {
        public void run() {
            if (!fetching) return;
            requestId++; // Discard any eventual completion from this timed-out request.
            Log.w("NookPanel", "refresh exceeded 75 seconds; retaining previous frame");
            finishRefresh(null);
        }
    };
    private final BroadcastReceiver batteryReceiver = new BroadcastReceiver() {
        public void onReceive(Context context, Intent intent) {
            int level = intent.getIntExtra("level", -1);
            int scale = intent.getIntExtra("scale", -1);
            int state = intent.getIntExtra("status", BatteryManager.BATTERY_STATUS_UNKNOWN);
            battery.setBattery(level >= 0 && scale > 0
                    ? (int) Math.min(100L, level * 100L / scale) : -1,
                    state == BatteryManager.BATTERY_STATUS_CHARGING);
        }
    };
    private final BroadcastReceiver screenReceiver = new BroadcastReceiver() {
        public void onReceive(Context context, Intent intent) {
            if (Intent.ACTION_SCREEN_OFF.equals(intent.getAction())) {
                sleeping = true;
                handler.removeCallbacks(idleSleep);
                getWindow().clearFlags(AWAKE_FLAGS);
                PowerCycle.restoreTimeout(PanelActivity.this);
                if (!fetching && !PowerCycle.settingsOpen) PowerCycle.wifi(PanelActivity.this, false);
                Log.i("NookPanel", "screen off; original timeout restored");
            } else if (sleeping && !PowerCycle.alarmStarting) {
                sleeping = false;
                automatic = false;
                requestedRefresh = true;
                PowerCycle.restoreTimeout(PanelActivity.this);
                if (resumed) foreground();
                Log.i("NookPanel", "manual wake; refresh requested");
            }
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        PowerCycle.restoreTimeout(this);
        setContentView(R.layout.panel);
        image = (ImageView) findViewById(R.id.panel_image);
        status = (TextView) findViewById(R.id.panel_status);
        battery = (BatteryView) findViewById(R.id.panel_battery);
        panel = (View) image.getParent();
        acceptIntent(getIntent());
        getWindow().addFlags(AWAKE_FLAGS);
        registerReceiver(batteryReceiver, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        IntentFilter filter = new IntentFilter(Intent.ACTION_SCREEN_OFF);
        filter.addAction(Intent.ACTION_SCREEN_ON);
        registerReceiver(screenReceiver, filter);
        try {
            Bitmap cached = FrameStore.load(this);
            if (cached != null) show(cached);
        } catch (Throwable e) { Log.w("NookPanel", "could not load cached image", e); }
    }

    private void acceptIntent(Intent intent) {
        automatic = intent.getBooleanExtra(PowerCycle.AUTOMATIC, false);
        // A manual launch (including the n button) must also fetch immediately.
        requestedRefresh = true;
        intent.removeExtra(PowerCycle.AUTOMATIC);
        sleeping = false;
        PowerCycle.alarmStarting = false;
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        acceptIntent(intent);
        if (resumed) foreground();
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        if (sleeping && !pm.isScreenOn()) return;
        if (sleeping && !PowerCycle.alarmStarting) {
            sleeping = false;
            automatic = false;
            // Resume can arrive before SCREEN_ON; consume the wake only once.
            requestedRefresh = true;
        }
        foreground();
    }

    private void foreground() {
        PowerCycle.restoreTimeout(this);
        getWindow().addFlags(AWAKE_FLAGS);
        PowerCycle.wifi(this, true);
        long last = Config.prefs(this).getLong("last_attempt_at", 0L);
        boolean changed = !Config.url(this).equals(Config.prefs(this).getString("last_attempt_url", ""));
        boolean due = System.currentTimeMillis() >= last + Config.intervalSeconds(this) * 1000L;
        if (requestedRefresh || last == 0 || changed || due) {
            requestedRefresh = false;
            refresh();
        } else {
            PowerCycle.schedule(this, last + Config.intervalSeconds(this) * 1000L);
            armIdle();
        }
    }

    @Override
    protected void onPause() {
        resumed = false;
        handler.removeCallbacks(idleSleep);
        super.onPause();
    }

    @Override
    public boolean dispatchTouchEvent(android.view.MotionEvent event) {
        return true; // Display appliance: touches never wake controls or extend idle time.
    }

    @Override
    protected void onDestroy() {
        destroyed = true;
        requestId++;
        handler.removeCallbacksAndMessages(null);
        unregisterReceiver(batteryReceiver);
        unregisterReceiver(screenReceiver);
        PowerCycle.release();
        PowerCycle.restoreTimeout(this);
        super.onDestroy();
    }

    private void armIdle() {
        handler.removeCallbacks(idleSleep);
        if (!resumed || fetching || sleeping || Config.url(this).length() == 0) return;
        handler.postDelayed(idleSleep, automatic ? 5000L : MANUAL_IDLE_MS);
    }

    private void refresh() {
        if (fetching) return;
        final String url = Config.url(this);
        if (url.length() == 0) { showStatus(getString(R.string.waiting)); return; }
        sleeping = false;
        getWindow().addFlags(AWAKE_FLAGS);
        handler.removeCallbacks(idleSleep);
        fetching = true;
        fetchUrl = url;
        final int id = ++requestId;
        PowerCycle.acquire(this);
        PowerCycle.wifi(this, true);
        PowerCycle.schedule(this, System.currentTimeMillis() + Config.intervalSeconds(this) * 1000L);
        handler.postDelayed(watchdog, 75000L);
        Log.i("NookPanel", "refresh starting; automatic=" + automatic);
        new Thread(new Runnable() {
            public void run() {
                Bitmap result = null;
                try {
                    WifiManager wifi = (WifiManager) getSystemService(WIFI_SERVICE);
                    long deadline = SystemClock.elapsedRealtime() + 25000L;
                    while (id == requestId && SystemClock.elapsedRealtime() < deadline) {
                        WifiInfo info = wifi == null ? null : wifi.getConnectionInfo();
                        if (wifi != null && wifi.isWifiEnabled() && info != null && info.getIpAddress() != 0) {
                            result = ImageFetcher.fetch(url, PanelActivity.this);
                            break;
                        }
                        SystemClock.sleep(500L);
                    }
                } catch (Throwable e) { Log.w("NookPanel", "refresh failed", e); }
                final Bitmap bitmap = result;
                handler.post(new Runnable() {
                    public void run() {
                        if (destroyed || id != requestId) {
                            if (bitmap != null) bitmap.recycle();
                            return;
                        }
                        finishRefresh(bitmap);
                    }
                });
            }
        }, "NookPanel-fetch").start();
    }

    private void finishRefresh(Bitmap bitmap) {
        handler.removeCallbacks(watchdog);
        fetching = false;
        if (bitmap == null) {
            Config.prefs(this).edit().putInt("failed_fetches",
                    Config.prefs(this).getInt("failed_fetches", 0) + 1).commit();
        }
        long now = System.currentTimeMillis();
        Config.prefs(this).edit().putLong("last_attempt_at", now)
                .putString("last_attempt_url", fetchUrl).commit();
        PowerCycle.schedule(this, now + Config.intervalSeconds(this) * 1000L);
        if (!fetchUrl.equals(Config.url(this))) {
            if (bitmap != null) bitmap.recycle();
            PowerCycle.release();
            if (resumed) foreground();
            return;
        }
        if (bitmap != null) {
            show(bitmap);
            try { FrameStore.save(this, bitmap); }
            catch (Throwable e) { Log.w("NookPanel", "cache write failed", e); }
            Log.i("NookPanel", "refresh succeeded");
        } else if (image.getDrawable() == null) {
            showStatus("Could not fetch an image.\n\nLast try: "
                    + DateFormat.getTimeFormat(this).format(new Date())
                    + "\n\nConfigure this display through the server dashboard.");
        } else {
            Log.i("NookPanel", "refresh failed; retained previous picture");
        }
        PowerCycle.release();
        if (!resumed && !PowerCycle.settingsOpen) sleepNow();
        else armIdle();
    }

    private void sleepNow() {
        if (fetching || PowerCycle.settingsOpen || destroyed) return;
        handler.removeCallbacks(idleSleep);
        Bitmap screenshot = null;
        try {
            if (panel.getWidth() <= 0 || panel.getHeight() <= 0) throw new IllegalStateException("Panel not laid out");
            screenshot = Bitmap.createBitmap(panel.getWidth(), panel.getHeight(), Bitmap.Config.RGB_565);
            panel.draw(new Canvas(screenshot)); // Includes the battery indicator, without menus.
            FrameStore.screensaver(this, screenshot);
        } catch (Throwable e) {
            Log.w("NookPanel", "screensaver write failed; keeping previous screensaver", e);
        } finally {
            if (screenshot != null) screenshot.recycle();
        }
        sleeping = true;
        getWindow().clearFlags(AWAKE_FLAGS);
        PowerCycle.release();
        PowerCycle.wifi(this, false);
        PowerCycle.forceSleep(this);
        Log.i("NookPanel", "sleep requested; Wi-Fi off, RTC alarm armed");
    }

    private void show(Bitmap bitmap) {
        battery.setVisibility(View.VISIBLE);
        status.setVisibility(View.GONE);
        image.setVisibility(View.VISIBLE);
        Bitmap old = image.getDrawable() instanceof android.graphics.drawable.BitmapDrawable
                ? ((android.graphics.drawable.BitmapDrawable) image.getDrawable()).getBitmap() : null;
        image.setImageBitmap(bitmap);
        if (old != null && old != bitmap) old.recycle();
    }

    private void showStatus(String text) {
        battery.setVisibility(View.GONE);
        image.setVisibility(View.GONE);
        status.setVisibility(View.VISIBLE);
        status.setText(text);
    }

}
